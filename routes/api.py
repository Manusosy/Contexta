"""API routes — AJAX endpoints for automation, scheduling, WP test."""
import threading
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required
from models import db, Setting, Log, Article
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
        return jsonify({"success": False, "error": "Automation is already running."}), 409

    auto_push = request.json.get("auto_push", False) if request.is_json else False

    # Run in background thread to avoid request timeout
    app = current_app._get_current_object()
    thread = threading.Thread(target=_run_in_context, args=(app, auto_push), daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Automation started in background."})


def _run_in_context(app, auto_push: bool):
    with app.app_context():
        from services.automation_service import run_automation
        run_automation(auto_push=auto_push)


@api_bp.route("/toggle-schedule", methods=["POST"])
@login_required
def toggle_schedule():
    """Enable or disable scheduled automation."""
    data = request.json or {}
    enabled = data.get("enabled", False)
    frequency = data.get("frequency", 60)

    Setting.set("schedule_enabled", "true" if enabled else "false")
    Setting.set("schedule_frequency", str(frequency))

    if enabled:
        start_schedule(current_app._get_current_object(), frequency)
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
    Setting.set("automation_status", "idle")
    log = Log(action="Automation status forcibly reset to idle.", status="warning")
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
    """Return recent logs as JSON."""
    logs = Log.query.order_by(Log.timestamp.desc()).limit(50).all()
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
    """Bulk delete articles by ID."""
    data = request.json or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"success": False, "error": "No articles selected"}), 400
        
    try:
        Article.query.filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        
        log = Log(action=f"Bulk deleted {len(ids)} articles", status="info")
        db.session.add(log)
        db.session.commit()
        
        return jsonify({"success": True, "deleted_count": len(ids)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
