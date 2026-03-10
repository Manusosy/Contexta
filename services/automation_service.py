"""
Automation Service — orchestrates the 6-node pipeline.
Nodes: RSS Fetcher (1), Worker (2), Extractor (3), Claude (4), WP (5), Error (6).
"""
import time
from datetime import datetime, timezone, timedelta
from models import db, Article, Setting
from services import rss_service, scraper_service, ai_service, wordpress_service
from utils.logger import log_event as _log
from config import get_config

config = get_config()


def run_node_1_rss_fetcher():
    """Trigger Node 1: Fetch all active feeds and queue new articles."""
    try:
        _log("Automation: Starting Node 1 (RSS Fetcher)", "info")
        new_count = rss_service.fetch_all_active_feeds()
        _log(f"Automation: Node 1 complete. {new_count} new articles pending.", "success")
        return new_count
    except Exception as e:
        _log("Automation: Node 1 failed", "error", str(e))
        return 0


def run_node_2_worker():
    """
    Node 2: Queue Worker Loop.
    Polls for PENDING articles, and processes ALL of them sequentially until the queue is empty.
    Runs nodes 3-5 for each article.
    """
    processed_count = 0
    from models import Setting as _S

    while True:
        # 1. Pick one pending article
        article = Article.query.filter_by(status="pending").order_by(Article.created_at.asc()).first()
        
        if not article:
            break # No more work to do

        _log(f"Worker: Picking article '{article.original_title[:40]}'", "info")

        # Track which article is being processed
        try:
            _S.set("current_processing_article", article.original_title[:60] if article.original_title else "Unknown")
        except Exception:
            pass

        # 2. Lock it
        article.status = "processing"
        article.locked_at = datetime.now(timezone.utc)
        db.session.commit()

        try:
            # Node 3: Extraction
            article.status = "extracting"
            db.session.commit()
            
            scrape_result = scraper_service.scrape_article(article.source_url)
            
            if scrape_result.get("status") == "skipped":
                article.status = "skipped"
                article.error_log = scrape_result.get("reason")
                db.session.commit()
                continue
                
            if not scrape_result or not scrape_result.get("text"):
                article.status = "failed"
                article.error_log = "Extraction yielded no text or failed"
                db.session.commit()
                continue

            # Update article with extracted data
            article.extracted_body = scrape_result["text"]
            article.author = scrape_result.get("author") or article.author
            article.main_image_url = scrape_result.get("image")
            article.word_count = scrape_result.get("word_count", 0)
            db.session.commit()

            # Node 4: Rewriting
            article.status = "rewriting"
            db.session.commit()
            
            rewritten_data = ai_service.rewrite_article(article)
            
            if not rewritten_data or not rewritten_data.get("body_html"):
                article.status = "failed"
                # error_log is now set via the exception or kept as default
                if not article.error_log:
                    article.error_log = "AI rewriter failed to produce valid JSON"
                db.session.commit()
                continue

            # Cache rewrite results into Article
            article.generated_title = rewritten_data["headline"]
            article.content = rewritten_data["body_html"]
            article.meta_description = rewritten_data.get("meta_description")
            article.slug = rewritten_data.get("slug")
            article.primary_keyword = rewritten_data.get("focus_keyword")
            article.word_count = rewritten_data.get("word_count", article.word_count)
            db.session.commit()

            # Node 5: Publishing
            article.status = "publishing"
            db.session.commit()
            
            wp_result = wordpress_service.push_to_wordpress(article, rewritten_data)
            
            if wp_result.get("success"):
                article.status = "published"
                article.wordpress_id = wp_result.get("wp_id")
                article.error_log = None
            else:
                article.status = "failed"
                article.error_log = f"WP: {wp_result.get('error')}"
            
            db.session.commit()
            processed_count += 1
            _log(f"Worker: Processed '{article.original_title[:30]}' -> {article.status}", "success")
            
            # Short sleep to respect rate limits if looping quickly
            time.sleep(2)

        except Exception as e:
            # Node 6: Error Handler
            _log(f"Worker Error: {str(e)}", "error")
            article.status = "failed"
            article.error_log = f"System Error: {str(e)}"
            article.retry_count += 1
            db.session.commit()
            time.sleep(2) # Backoff slightly on error

    return processed_count

def cleanup_stale_locks():
    """Reset articles that have been 'processing' for too long (> 10 mins)."""
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    stale_articles = Article.query.filter(
        Article.status.in_(["processing", "extracting", "rewriting", "publishing"]),
        Article.locked_at < stale_time
    ).all()
    
    for article in stale_articles:
        _log(f"Resetting stale lock for article {article.id}", "warning")
        article.status = "pending"
        article.locked_at = None
    db.session.commit()


def run_automation(auto_push: bool = False):
    """
    Called by the 'Trigger Automation' button in UI.
    Runs Node 1 once, then processes ONE article if any are pending.
    Updates automation_status in Settings for the live-status endpoint.
    """
    from models import Setting as _Setting

    try:
        _Setting.set("automation_status", "running")
        _Setting.set("current_processing_article", "Fetching RSS feeds...")

        cleanup_stale_locks()
        queued = run_node_1_rss_fetcher()

        _Setting.set("current_processing_article", f"Processing queue ({queued} new)...")
        run_node_2_worker()

        _Setting.set("automation_status", "idle")
        _Setting.set("current_processing_article", "")
        _Setting.set("last_run", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    except Exception as e:
        _log(f"run_automation top-level error: {e}", "error")
        try:
            from models import Setting as _S
            _S.set("automation_status", "idle")
            _S.set("current_processing_article", "")
        except Exception:
            pass
    return True
