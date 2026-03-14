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


def run_node_2_worker(user_id=None):
    """
    Node 2: Queue Worker Loop.
    Polls for PENDING articles, and processes ALL of them sequentially until the queue is empty.
    Runs nodes 3-5 for each article.
    If user_id is provided, only processes articles for that user's feeds.
    """
    processed_count = 0
    from models import Setting as _S, Feed

    while True:
        # 1. Pick one pending article
        query = Article.query.filter_by(status="pending")
        
        if user_id:
            # Join with Feed to filter by user_id
            query = query.join(Feed).filter(Feed.user_id == user_id)
        else:
            # Global run: typically admin feeds (user_id is None)
            query = query.join(Feed).filter(Feed.user_id == None)

        article = query.order_by(Article.created_at.asc()).first()
        
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

            # Node 3.5: Context Analysis
            article.status = "analyzing"
            db.session.commit()
            
            from services.context_engine import analyze_article_context, detect_duplicates
            
            if detect_duplicates(article):
                article.status = "skipped"
                article.error_log = "Context Engine: Duplicate content skipped."
                db.session.commit()
                continue
                
            context_data = analyze_article_context(article)
            article.content_strategy = context_data.get("recommended_strategy", "News Article")
            db.session.commit()
            
            # Content Strategy Filtering
            if article.relevance_score < 50 or article.content_strategy.lower() == "skip":
                article.status = "skipped"
                article.error_log = f"Context Engine: Skipped. Score: {article.relevance_score}, Strategy: {article.content_strategy}"
                db.session.commit()
                continue

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

def cleanup_stale_locks(user_id=None):
    """Reset articles that have been 'processing' for too long (> 10 mins)."""
    from models import Feed
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    query = Article.query.filter(
        Article.status.in_(["processing", "extracting", "rewriting", "publishing"]),
        Article.locked_at < stale_time
    )
    
    if user_id:
        query = query.join(Feed).filter(Feed.user_id == user_id)
    else:
        query = query.join(Feed).filter(Feed.user_id == None)

    stale_articles = query.all()
    
    for article in stale_articles:
        _log(f"Resetting stale lock for article {article.id}", "warning")
        article.status = "pending"
        article.locked_at = None
    db.session.commit()


def run_automation(auto_push: bool = False, user_id=None):
    """
    Called by the 'Trigger Automation' button in UI.
    Runs Node 1 once, then processes ONE article if any are pending.
    Updates automation_status in Settings for the live-status endpoint.
    """
    from models import Setting as _Setting

    try:
        # Note: automation_status and current_processing_article are global settings.
        # In a multi-user environment, these should ideally be per-user. 
        # For now, we'll prefix them if it's a specific user to avoid total overlap,
        # but the logic remains simple.
        status_key = "automation_status" if not user_id else f"auth_status_{user_id}"
        article_key = "current_processing_article" if not user_id else f"curr_art_{user_id}"

        _Setting.set(status_key, "running")
        _Setting.set(article_key, "Fetching RSS feeds...")

        cleanup_stale_locks(user_id=user_id)
        
        # Node 1: Fetch feeds
        from models import Feed
        if user_id:
            feeds = Feed.query.filter_by(user_id=user_id, active=True).all()
        else:
            feeds = Feed.query.filter_by(user_id=None, active=True).all()
            
        queued = 0
        for feed in feeds:
            queued += len(rss_service.fetch_feed(feed))

        _Setting.set(article_key, f"Processing queue ({queued} new)...")
        run_node_2_worker(user_id=user_id)

        _Setting.set(status_key, "idle")
        _Setting.set(article_key, "")
        if not user_id:
            _Setting.set("last_run", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        else:
            _Setting.set(f"last_run_{user_id}", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    except Exception as e:
        _log(f"run_automation error for user {user_id}: {e}", "error")
        try:
            from models import Setting as _S
            status_key = "automation_status" if not user_id else f"auth_status_{user_id}"
            article_key = "current_processing_article" if not user_id else f"curr_art_{user_id}"
            _S.set(status_key, "idle")
            _S.set(article_key, "")
        except Exception:
            pass
    return True

def run_automation_async(app, auto_push=False, user_id=None):
    """Trigger automation in a non-blocking background thread."""
    import threading
    thread = threading.Thread(
        target=_run_in_app_context,
        args=(app, auto_push, user_id),
        daemon=True
    )
    thread.start()
    return thread

def _run_in_app_context(app, auto_push, user_id):
    """Wrapper to run automation with app context."""
    with app.app_context():
        run_automation(auto_push=auto_push, user_id=user_id)
