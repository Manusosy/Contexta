"""Automation Service — orchestrates the full RSS → AI → SEO → WP pipeline."""
from datetime import datetime, timezone
from models import db, Feed, Article, Setting
from utils.logger import log_event as _log
from services.rss_service import fetch_all_active_feeds
from services.scraper_service import scrape_article
from services.ai_service import generate_article
from services.seo_service import process_article as seo_process
from services.wordpress_service import push_to_wordpress


def run_automation(auto_push: bool = False) -> dict:
    """
    Run a single cycle of the automation pipeline:
      1. Fetch all active RSS feeds (queues new URLs as 'pending')
      2. Grab exactly 1 'pending' article from the database
      3. Scrape → AI generate → SEO → save as 'generated'
      4. Optionally push to WordPress as draft

    Returns a summary dict.
    """
    # Only mark as running; set last_run at the very end.
    Setting.set("automation_status", "running")
    _log("Automation heartbeat started", "info")

    processed = 0
    pushed = 0
    errors = 0
    queued = 0

    try:
        # Step 1: Always update the queue with new items from RSS
        queued = fetch_all_active_feeds()
        
        # Step 2: Grab pending articles based on max limit
        max_articles_str = Setting.get("ai_max_articles_per_run", "1")
        try:
            max_articles = int(max_articles_str)
        except ValueError:
            max_articles = 1
            
        # If the user wants "one after another til all are done", we can't do INFINITE, 
        # but we can process the current pending batch up to a reasonable limit.
        pending_articles = Article.query.filter_by(status="pending").order_by(Article.created_at.asc()).limit(max_articles).all()

        if not pending_articles:
            _log("No pending articles found to process.", "info")
            Setting.set("automation_status", "idle")
            Setting.set("last_run", datetime.now(timezone.utc).isoformat())
            return {"queued": queued, "processed": 0, "pushed": 0, "errors": 0}

        for pending_article in pending_articles:
            try:
                # Extra check for API Key before starting work
                api_key = Setting.get("ai_api_key")
                if not api_key or api_key.startswith("http") or api_key == "sk-or-v1-REPLACE_ME":
                    _log("Automation aborted — AI API Key is missing or invalid URL", "error")
                    break

                result = _process_article(pending_article, auto_push)
                if result and result.get("success"):
                    if result.get("pushed"):
                        pushed += 1
                    processed += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                _log(f"Article processing error: {pending_article.source_url[:60]}", "error", str(e))

        Setting.set("automation_status", "idle")
        Setting.set("last_run", datetime.now(timezone.utc).isoformat())
        
        msg = f"Automation cycle complete. Queued: {queued}, Processed: {processed}, Pushed: {pushed}, Errors: {errors}"
        _log(msg, "success" if errors == 0 else "warning")
        return {"queued": queued, "processed": processed, "pushed": pushed, "errors": errors}

    except Exception as e:
        Setting.set("automation_status", "failed")
        Setting.set("last_run", datetime.now(timezone.utc).isoformat())
        _log("Automation failed", "error", str(e))
        return {"queued": queued, "processed": processed, "pushed": pushed, "errors": errors + 1, "fatal": str(e)}


def _process_article(article: Article, auto_push: bool) -> dict:
    """Process a single pending Article through the AI/SEO pipeline in-place."""
    url = article.source_url
    original_title = article.original_title

    # Live UI feedback
    Setting.set("current_processing_article", original_title or url)

    # 1. Scrape
    scraped = scrape_article(url)
    if not scraped or not scraped.get("text"):
        _log(f"Scrape failed or empty: {url[:60]}", "warning")
        article.status = "failed_scrape"
        db.session.commit()
        return {"success": False, "pushed": False}

    # 1.5 Relevance Check (New Filter)
    if not check_relevance(scraped["text"]):
        _log(f"Article discarded as irrelevant/low-quality: {url[:60]}", "info")
        article.status = "discarded"
        db.session.commit()
        return {"success": True, "pushed": False, "discarded": True}

    # 2. AI Generate
    generated_html = generate_article(scraped["text"])
    if not generated_html:
        _log(f"AI Generation failed: {url[:60]}", "warning")
        article.status = "failed_ai"
        db.session.commit()
        return {"success": False, "pushed": False}

    # 3. SEO Process
    seo_data = seo_process(generated_html, original_title)

    # 4. Update Article DB
    article.generated_title = seo_data["seo_title"]
    article.content = seo_data.get("content_html", generated_html)  # Use cleaned body (h1 extracted)
    article.meta_description = seo_data["meta_description"]
    article.slug = seo_data["slug"]
    article.primary_keyword = seo_data["primary_keyword"]
    article.seo_score = seo_data["seo_score"]
    article.status = "generated"
    db.session.commit()

    _log(f"Article generated: '{original_title[:60]}' | Words: ~{seo_data.get('word_count','?')} | SEO: {seo_data.get('seo_score','?')}", "success")

    # 5. Pre-Publish Verification & Auto-push
    pushed = False
    if auto_push:
        verify = Setting.get("wp_verify_publish", "true") == "true"
        if verify and not _verify_article(article):
            article.status = "failed_verification"
            db.session.commit()
            _log(f"Article failed pre-publish verification: '{original_title[:40]}'", "warning")
            return {"success": True, "pushed": False, "article_id": article.id}

        result = push_to_wordpress(article)
        if result.get("success"):
            article.wordpress_id = result["wp_id"]
            article.status = "pushed"
            db.session.commit()
            pushed = True
        else:
            _log(f"WP push failed for '{original_title[:40]}'", "error", result.get("error", ""))

    return {"success": True, "pushed": pushed, "article_id": article.id}


def _verify_article(article: Article) -> bool:
    """
    Verify that an article meets minimum standards before pushing to WordPress.
    Checks for: generated_title (H1), meta description, slug, and minimum word count from settings.
    """
    from bs4 import BeautifulSoup

    if not article.generated_title or len(article.generated_title) < 5:
        _log(f"Verification failed — missing title: '{str(article.original_title)[:40]}'", "warning")
        return False
    if not article.meta_description or len(article.meta_description) < 10:
        _log(f"Verification failed — missing meta description: '{str(article.generated_title)[:40]}'", "warning")
        return False
    if not article.slug:
        _log(f"Verification failed — missing slug: '{str(article.generated_title)[:40]}'", "warning")
        return False
    if not article.content:
        _log(f"Verification failed — empty content: '{str(article.generated_title)[:40]}'", "warning")
        return False

    # Count real words from HTML content
    try:
        soup = BeautifulSoup(article.content, "lxml")
        plain_text = soup.get_text(separator=" ", strip=True)
        word_count = len(plain_text.split())
    except Exception:
        word_count = len(article.content.split())

    min_words_str = Setting.get("ai_word_count_min", "350")
    try:
        min_words = int(min_words_str)
    except ValueError:
        min_words = 350

    if word_count < min_words:
        _log(
            f"Verification failed — word count too low ({word_count} < {min_words}): '{str(article.generated_title)[:40]}'",
            "warning"
        )
        return False

    # Check title does not contain generic AI refusal phrases
    title_lower = article.generated_title.lower()
    refusal_phrases = ["i cannot format", "i am an ai", "as an ai", "i'm sorry", "i cannot write", "i apologize"]
    if any(phrase in title_lower for phrase in refusal_phrases):
        _log(f"Verification failed — AI refusal detected in title: '{str(article.generated_title)[:60]}'", "warning")
        return False

    return True
