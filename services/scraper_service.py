"""Scraper Service — extracts clean article content from URLs using trafilatura."""
import trafilatura
from models import db
from utils.logger import log_event as _log
from config import get_config

config = get_config()


def scrape_article(url: str) -> dict:
    """
    Fetch and clean article content from a URL using trafilatura.
    Returns dict with keys: title, text, author, date, image, status.
    Node 3 Specification: Extract full body text, author, publish date, main image URL, canonical URL.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            _log(f"Trafilatura failed to download: {url}", "warning")
            return {"status": "skipped", "reason": "download_failed"}

        # Extract with all metadata
        # output_format='txt' for the body text
        result = trafilatura.extract(
            downloaded, 
            include_comments=False, 
            include_tables=True,
            include_images=True,
            include_formatting=True,
            with_metadata=True
        )
        
        if not result:
            _log(f"Extraction failed for: {url}", "warning")
            return {"status": "skipped", "reason": "extraction_failed"}

        # Trafilatura metadata extraction
        import json
        metadata = trafilatura.extract_metadata(downloaded)
        
        # Word count check
        word_count = len(result.split())
        min_words = getattr(config, "MIN_WORD_COUNT", 200)
        
        if word_count < min_words:
            _log(f"Article too short ({word_count} words): {url}", "info")
            return {"status": "skipped", "reason": f"content_too_short_{word_count}"}

        _log(f"Scraped: {url[:60]}...", "success", f"{word_count} words extracted")
        
        return {
            "title": metadata.title if metadata else None,
            "text": result,
            "author": metadata.author if metadata else None,
            "date": metadata.date if metadata else None,
            "image": metadata.image if metadata else None,
            "url": url,
            "word_count": word_count,
            "status": "extracting" # Intermediate state if needed, but worker handles final status
        }

    except Exception as e:
        _log(f"Scraper error for {url}", "error", str(e))
        return {"status": "failed", "reason": str(e)}
