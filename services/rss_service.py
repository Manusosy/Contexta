"""RSS Feed Service — fetches and parses feeds via feedparser."""
import feedparser
import urllib.parse
from datetime import datetime
from models import db, Feed, Article
from utils.logger import log_event as _log
from config import get_config

config = get_config()


def fetch_feed(feed: Feed) -> list[dict]:
    """
    Parse an RSS feed and return NEW entries not already in the DB.
    Returns a list of dicts with keys: title, url, summary, published.
    Nodes 1 Specification: Fetch feed → deduplicate → save max 5 new → status: pending.
    """
    try:
        parsed = feedparser.parse(feed.url)
        # Capture feed-level description if we don't have one
        if not feed.description and 'description' in parsed.feed:
            feed.description = parsed.feed.description
            db.session.add(feed)
    except Exception as e:
        _log(f"Failed to parse feed '{feed.name}'", "error", str(e))
        return []

    new_entries = []
    limit = getattr(config, "RSS_BATCH_LIMIT", 5)
    count = 0

    for entry in parsed.entries:
        if count >= limit:
            break

        url = _get_entry_url(entry)
        if not url:
            continue
            
        url = _normalize_url(url)
        guid = entry.get("id") or entry.get("guid") or url

        # Duplicate check (URL or GUID)
        exists = Article.query.filter(
            (Article.source_url == url) | (Article.guid == guid)
        ).first()
        
        if exists:
            continue

        title = entry.get("title", "Untitled")
        summary = entry.get("summary", entry.get("description", ""))
        author = entry.get("author", "")
        
        # Capture tags/categories to guide AI
        tags = [t.get("term") for t in entry.get("tags", []) if t.get("term")]
        source_tags = ", ".join(tags) if tags else ""

        pub_date = _parse_date(entry)

        # Save to DB as pending
        article = Article(
            feed_id=feed.id,
            source_url=url,
            guid=guid,
            original_title=title,
            original_pub_date=pub_date,
            author=author,
            source_tags=source_tags,
            extracted_body=summary, # Initial excerpt from RSS
            status="pending",
        )
        db.session.add(article)
        new_entries.append({"title": title, "url": url})
        count += 1

    db.session.commit()
    if count > 0:
        _log(f"Feed '{feed.name}': {count} new entries queued", "info")
    return new_entries


def fetch_all_active_feeds() -> int:
    """Fetch entries for all active feeds, save as pending. Returns total new queued."""
    feeds = Feed.query.filter_by(active=True).all()
    total_queued = 0
    for feed in feeds:
        entries = fetch_feed(feed)
        total_queued += len(entries)
    return total_queued


def _get_entry_url(entry) -> str | None:
    return entry.get("link") or entry.get("url") or None


def _normalize_url(url: str) -> str:
    """Normalize URL by stripping common tracking parameters to improve deduplication."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qsl(parsed.query)
        # Filter out utm_ and other common tracking params
        clean_params = [(k, v) for k, v in params if not (k.startswith('utm_') or k in ('ref', 'source'))]
        clean_query = urllib.parse.urlencode(clean_params)
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, parsed.fragment))
    except Exception:
        return url


def _parse_date(entry) -> datetime:
    try:
        struct = entry.get("published_parsed") or entry.get("updated_parsed")
        if struct:
            return datetime(*struct[:6])
    except Exception:
        pass
    return datetime.utcnow()
