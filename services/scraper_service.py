"""Scraper Service — extracts clean article content from URLs."""
import time
import requests
from bs4 import BeautifulSoup
from readability import Document
from models import db
from utils.logger import log_event as _log

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15


def scrape_article(url: str) -> dict:
    """
    Fetch and clean article content from a URL.
    Returns dict with keys: title, text, html.
    Returns empty dict on failure.
    """
    for attempt in range(2):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            break
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            _log(f"Failed to fetch URL: {url}", "error", str(e))
            return {}

    try:
        doc = Document(response.text)
        title = doc.title()
        raw_html = doc.summary(html_partial=True)

        soup = BeautifulSoup(raw_html, "lxml")
        _strip_junk(soup)

        clean_text = soup.get_text(separator="\n", strip=True)
        clean_html = str(soup)

        _log(f"Scraped: {url[:60]}...", "success", f"{len(clean_text)} chars extracted")
        return {
            "title": title,
            "text": clean_text,
            "html": clean_html,
        }
    except Exception as e:
        _log(f"Parse error for: {url}", "error", str(e))
        return {}


def _strip_junk(soup: BeautifulSoup):
    """Remove unwanted tags from parsed HTML."""
    junk_tags = [
        "script", "style", "noscript", "iframe",
        "form", "input", "button", "aside",
        "nav", "footer", "header", "figure"
    ]
    for tag in junk_tags:
        for el in soup.find_all(tag):
            el.decompose()

    # Remove elements with ad/promo class names
    for el in soup.find_all(True):
        classes = el.get("class", [])
        class_str = " ".join(classes).lower()
        if any(k in class_str for k in ["ad", "promo", "newsletter", "popup", "cookie", "social"]):
            el.decompose()
