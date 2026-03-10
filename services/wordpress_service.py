"""WordPress Service — pushes articles to WordPress via REST API with Yoast SEO support."""
import requests
from requests.auth import HTTPBasicAuth
from models import Setting, db
from utils.logger import log_event as _log
from config import get_config

config = get_config()


def push_to_wordpress(article, rewritten_data: dict) -> dict:
    """
    Push rewritten content to WordPress via REST API.
    Node 5 Specification: Map fields → categories/tags → meta → publish (draft).
    """
    wp_url = (getattr(config, "WP_URL", "") or Setting.get("wp_url", "")).rstrip("/")
    wp_user = getattr(config, "WP_USER", "") or Setting.get("wp_user", "")
    wp_password = getattr(config, "WP_APP_PASSWORD", "") or Setting.get("wp_password", "")
    
    if not all([wp_url, wp_user, wp_password]):
        _log("WordPress push skipped — incomplete credentials", "warning")
        return {"success": False, "error": "WP Credentials missing"}

    auth = HTTPBasicAuth(wp_user, wp_password)
    headers = {"User-Agent": "Contexta/2.0 Automation Pipeline"}

    # 1. Resolve Categories & Tags (Name to ID)
    cat_ids = _resolve_ids(wp_url, auth, "categories", rewritten_data.get("suggested_categories", []))
    tag_ids = _resolve_ids(wp_url, auth, "tags", rewritten_data.get("suggested_tags", []))

    # 2. Build Payload
    payload = {
        "title": rewritten_data.get("headline", article.original_title),
        "content": rewritten_data.get("body_html", ""),
        "excerpt": rewritten_data.get("excerpt", ""),
        "slug": rewritten_data.get("slug", ""),
        "status": getattr(config, "WP_DEFAULT_STATUS", "draft"),
        "categories": cat_ids,
        "tags": tag_ids,
        "meta": {
            "_yoast_wpseo_metadesc": rewritten_data.get("meta_description", ""),
            "_yoast_wpseo_focuskw": rewritten_data.get("focus_keyword", ""),
        }
    }

    try:
        response = requests.post(
            f"{wp_url}/wp-json/wp/v2/posts",
            json=payload,
            auth=auth,
            headers=headers,
            timeout=45
        )
        
        if response.status_code in (200, 201):
            wp_id = response.json().get("id")
            _log(f"Published to WP: {wp_id}", "success")
            return {"success": True, "wp_id": wp_id}
        else:
            _log(f"WP Publish failed: {response.status_code}", "error", response.text[:200])
            return {"success": False, "error": response.text[:200]}
            
    except Exception as e:
        _log("WP Service exception", "error", str(e))
        return {"success": False, "error": str(e)}


def _resolve_ids(wp_url, auth, endpoint_type, names) -> list[int]:
    """Helper to find or create ID for a given name in WP (categories/tags)."""
    if not names:
        return []
    
    resolved_ids = []
    headers = {"User-Agent": "Contexta/2.0 Automation Pipeline"}
    
    for name in names:
        try:
            # Check if exists
            search_resp = requests.get(
                f"{wp_url}/wp-json/wp/v2/{endpoint_type}?search={name}",
                auth=auth,
                headers=headers
            )
            data = search_resp.json()
            
            # Exact match check
            found_id = next((item["id"] for item in data if item["name"].lower() == name.lower()), None)
            
            if found_id:
                resolved_ids.append(found_id)
            else:
                # Create new
                create_resp = requests.post(
                    f"{wp_url}/wp-json/wp/v2/{endpoint_type}",
                    json={"name": name},
                    auth=auth,
                    headers=headers
                )
                if create_resp.status_code in (200, 201):
                    resolved_ids.append(create_resp.json().get("id"))
        except:
            continue
            
    return resolved_ids


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
