"""API routes — AJAX endpoints for automation, scheduling, WP test."""
import threading
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import db, Setting, Log, Article, Feed
from services.wordpress_service import test_connection
from services.scheduler_service import start_schedule, stop_schedule

api_bp = Blueprint("api", __name__)


@api_bp.route("/run-automation", methods=["POST"])
@login_required
def run_automation_endpoint():
    """Trigger automation in a background thread."""
    if not request.is_json:
        return jsonify({"success": False, "error": "Content-Type must be application/json"}), 415
    status = Setting.get("automation_status", "idle")
    if status == "running":
        # Check if it's genuinely stuck by checking last_run delta (optional) or just bypass it occasionally.
        # But for now, since there's a explicit "Reset Engine" button in the template, we'll let it return 409.
        return jsonify({"success": False, "error": "Automation is already running."}), 409

    auto_push = request.json.get("auto_push", False) if request.is_json else False

    # Run in background thread to avoid request timeout
    Setting.set("automation_status", "running")
    if current_user.role != "admin":
        Setting.set(f"auth_status_{current_user.id}", "running")
        
    from services.automation_service import run_automation_async
    app = current_app._get_current_object()
    user_id = current_user.id if current_user.role != "admin" else None
    run_automation_async(app, auto_push=auto_push, user_id=user_id)

    return jsonify({"success": True, "message": "Automation started in background."})


# _run_in_context is now redundant as it's handled in automation_service.py


@api_bp.route("/toggle-schedule", methods=["POST"])
@login_required
def toggle_schedule():
    """Enable or disable scheduled automation."""
    data = request.json or {}
    enabled = data.get("enabled", False)
    frequency = data.get("frequency", 60)

    Setting.set("schedule_enabled", "true" if enabled else "false")
    Setting.set("schedule_frequency", str(frequency))

    app = current_app._get_current_object()
    if enabled:
        start_schedule(app)
        log = Log(action=f"Schedule enabled: every {frequency} minutes.", status="info")
    else:
        stop_schedule()
        log = Log(action="Schedule disabled.", status="info")

    db.session.add(log)
    db.session.commit()

    return jsonify({"success": True})


@api_bp.route("/reset-automation", methods=["POST"])
@login_required
def reset_automation():
    """Force reset stuck automation status to idle."""
    if current_user.role == "admin":
        Setting.set("automation_status", "idle")
        Setting.set("current_processing_article", "")
    
    # Always reset the user's specific status if tagged
    Setting.set(f"auth_status_{current_user.id}", "idle")
    Setting.set(f"curr_art_{current_user.id}", "")
    
    log = Log(action="Automation status forcibly reset to idle.", status="warning", user_id=current_user.id)
    db.session.add(log)
    db.session.commit()
    return jsonify({"success": True, "message": "Automation status reset to idle."})


@api_bp.route("/test-wp", methods=["POST"])
@login_required
def test_wp():
    """Test WordPress connection and return result."""
    result = test_connection()
    return jsonify(result)


@api_bp.route("/wp-categories", methods=["GET"])
@login_required
def get_wp_categories():
    """Fetch WordPress categories."""
    from services.wordpress_service import get_categories
    result = get_categories()
    return jsonify(result)


@api_bp.route("/status", methods=["GET"])
@login_required
def automation_status():
    """Return current automation status and last run."""
    return jsonify({
        "status": Setting.get("automation_status", "idle"),
        "last_run": Setting.get("last_run", "Never"),
        "current_article": Setting.get("current_processing_article", ""),
        "schedule_enabled": Setting.get("schedule_enabled", "false") == "true",
        "schedule_frequency": Setting.get("schedule_frequency", "60"),
    })


@api_bp.route("/logs", methods=["GET"])
@login_required
def get_logs():
    """Return recent logs as JSON with pagination."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    
    query = Log.query
    if current_user.role != "admin":
        query = query.filter_by(user_id=current_user.id)
    else:
        query = query.filter_by(user_id=None)
        
    logs = query.order_by(Log.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False).items
    return jsonify([log.to_dict() for log in logs])


@api_bp.route("/logs/clear", methods=["DELETE"])
@login_required
def clear_logs():
    """Clear all logs."""
    try:
        Log.query.delete()
        db.session.commit()
        log = Log(action="All logs cleared", status="info")
        db.session.add(log)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/articles/bulk-delete", methods=["POST"])
@login_required
def bulk_delete_articles():
    """Bulk delete articles by ID, with ownership check."""
    data = request.json or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"success": False, "error": "No articles selected"}), 400

    try:
        # Build the deletion query
        query = Article.query.filter(Article.id.in_(ids))

        # If not admin, restrict to articles belonging to the user's feeds
        if current_user.role != "admin":
            query = query.join(Feed, Article.feed_id == Feed.id).filter(Feed.user_id == current_user.id)

        deleted_count = query.delete(synchronize_session=False)
        db.session.commit()

        if deleted_count > 0:
            log = Log(
                action=f"Bulk deleted {deleted_count} articles",
                status="info",
                user_id=current_user.id
            )
            db.session.add(log)
            db.session.commit()

        return jsonify({"success": True, "deleted_count": deleted_count})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
