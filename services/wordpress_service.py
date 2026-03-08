"""WordPress Service — pushes articles to WordPress via REST API."""
import requests
from requests.auth import HTTPBasicAuth
from models import Setting, db
from utils.logger import log_event as _log


def push_to_wordpress(article) -> dict:
    """
    Push an Article instance to WordPress as a draft.
    Returns dict with success bool and optional wp_id.
    """
    wp_url = Setting.get("wp_url", "").rstrip("/")
    wp_user = Setting.get("wp_user", "")
    wp_password = Setting.get("wp_password", "")
    default_category = int(Setting.get("wp_default_category", "1"))

    if not all([wp_url, wp_user, wp_password]):
        _log("WordPress push skipped — credentials not configured", "warning")
        return {"success": False, "error": "WordPress credentials not configured."}

    endpoint = f"{wp_url}/wp-json/wp/v2/posts"
    auth = HTTPBasicAuth(wp_user, wp_password)

    title = article.generated_title or article.original_title or "Untitled"
    payload = {
        "title": title,
        "content": article.content or "",
        "status": "draft",
        "categories": [default_category],
        "meta": {
            "_yoast_wpseo_metadesc": article.meta_description or "",
            "_yoast_wpseo_focuskw": article.primary_keyword or "",
        },
        "slug": article.slug or "",
    }

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Contexta/1.0"
        }
        response = requests.post(endpoint, json=payload, auth=auth, headers=headers, timeout=30)
        if response.status_code in (200, 201):
            data = response.json()
            wp_id = data.get("id")
            _log(f"Pushed to WordPress: '{title}' (WP ID: {wp_id})", "success")
            return {"success": True, "wp_id": wp_id}
        else:
            error_msg = response.text[:200]
            _log(f"WordPress push failed: {response.status_code}", "error", error_msg)
            return {"success": False, "error": f"HTTP {response.status_code}: {error_msg}"}
    except Exception as e:
        _log("WordPress push exception", "error", str(e))
        return {"success": False, "error": str(e)}


def test_connection() -> dict:
    """Test WordPress credentials by fetching /wp-json/wp/v2/users/me."""
    wp_url = Setting.get("wp_url", "").rstrip("/")
    wp_user = Setting.get("wp_user", "")
    wp_password = Setting.get("wp_password", "")

    if not all([wp_url, wp_user, wp_password]):
        return {"success": False, "error": "WordPress credentials not configured."}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Contexta/1.0"
        }
        response = requests.get(
            f"{wp_url}/wp-json/wp/v2/users/me",
            auth=HTTPBasicAuth(wp_user, wp_password),
            headers=headers,
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            return {"success": True, "user": data.get("name", "Unknown")}
        elif response.status_code == 401:
            return {"success": False, "error": "Authentication failed — check credentials."}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_categories() -> dict:
    """Fetch categories from WordPress via REST API."""
    wp_url = Setting.get("wp_url", "").rstrip("/")
    wp_user = Setting.get("wp_user", "")
    wp_password = Setting.get("wp_password", "")

    if not all([wp_url, wp_user, wp_password]):
        return {"success": False, "error": "WordPress credentials not configured."}

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Contexta/1.0"
        }
        response = requests.get(
            f"{wp_url}/wp-json/wp/v2/categories?per_page=100",
            auth=HTTPBasicAuth(wp_user, wp_password),
            headers=headers,
            timeout=15,
        )
        if response.status_code == 200:
            categories = response.json()
            # Map to simpler dict
            cats = [{"id": c.get("id"), "name": c.get("name")} for c in categories]
            return {"success": True, "categories": cats}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
