"""WordPress Service — pushes articles to WordPress via REST API."""
import requests
from requests.auth import HTTPBasicAuth
from models import Setting, db
from utils.logger import log_event as _log


def push_to_wordpress(article, user=None) -> dict:
    """
    Push an Article instance to WordPress as a draft.
    Returns dict with success bool and optional wp_id.
    """
    # Use user-specific settings if available, else fallback to global Settings
    wp_url = (user.wp_url if user and user.wp_url else Setting.get("wp_url", "")).rstrip("/")
    wp_user = user.wp_user if user and user.wp_user else Setting.get("wp_user", "")
    wp_password = user.wp_password if user and user.wp_password else Setting.get("wp_password", "")
    
    # Use user-specific category if available, else global fallback
    default_category_raw = user.wp_default_category if user and user.wp_default_category else Setting.get("wp_default_category", "1")
    try:
        default_category = int(default_category_raw)
    except (ValueError, TypeError):
        default_category = 1

    if not all([wp_url, wp_user, wp_password]):
        user_msg = f" for user {user.email}" if user else ""
        _log(f"WordPress push skipped — credentials not configured{user_msg}", "warning", user_id=user.id if user else None)
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
            _log(f"Pushed to WordPress: '{title}' (WP ID: {wp_id})", "success", user_id=user.id if user else None)
            return {"success": True, "wp_id": wp_id}
        else:
            error_msg = response.text[:200]
            _log(f"WordPress push failed: {response.status_code}", "error", error_msg, user_id=user.id if user else None)
            return {"success": False, "error": f"HTTP {response.status_code}: {error_msg}"}
    except Exception as e:
        _log("WordPress push exception", "error", str(e), user_id=user.id if user else None)
        return {"success": False, "error": str(e)}


def test_connection(user=None) -> dict:
    """Test WordPress credentials by fetching /wp-json/wp/v2/users/me."""
    wp_url = (user.wp_url if user and user.wp_url else Setting.get("wp_url", "")).rstrip("/")
    wp_user = user.wp_user if user and user.wp_user else Setting.get("wp_user", "")
    wp_password = user.wp_password if user and user.wp_password else Setting.get("wp_password", "")

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


def get_categories(user=None) -> dict:
    """Fetch categories from WordPress via REST API."""
    wp_url = (user.wp_url if user and user.wp_url else Setting.get("wp_url", "")).rstrip("/")
    wp_user = user.wp_user if user and user.wp_user else Setting.get("wp_user", "")
    wp_password = user.wp_password if user and user.wp_password else Setting.get("wp_password", "")

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
