"""Settings routes."""
import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Setting
from services.ai_service import list_available_models

settings_bp = Blueprint("settings", __name__)


@settings_bp.before_request
@login_required
def require_admin():
    """Settings are admin-only."""
    if current_user.role != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("dashboard.index"))

AI_KEYS = [
    "ai_api_key", "ai_model", "ai_trial_model", "ai_temperature", "ai_max_tokens",
    "ai_style_instructions", "ai_preserve_tone", "ai_avoid_generic",
    "ai_no_long_dashes", "ai_regional_insight",
]
WP_KEYS = ["wp_url", "wp_user", "wp_password", "wp_default_category", "wp_verify_publish"]
SEO_KEYS = ["seo_meta_length", "seo_faq_schema", "seo_auto_slug"]
BILLING_KEYS = [
    "paypal_client_id", "paypal_secret", "paypal_mode",
    "mpesa_consumer_key", "mpesa_consumer_secret", "mpesa_shortcode", "mpesa_passkey", "mpesa_mode",
    "mpesa_callback_url"
]


@settings_bp.route("/")
@login_required
def index():
    s = Setting.get_all_as_dict()
    models, fallback = list_available_models()
    return render_template("settings/index.html", s=s, models=models, fallback=fallback)


@settings_bp.route("/ai", methods=["POST"])
@login_required
def save_ai():
    checkboxes = {"ai_preserve_tone", "ai_avoid_generic", "ai_no_long_dashes", "ai_regional_insight"}
    
    api_key = request.form.get("ai_api_key", "").strip()
    key_status = "none"
    if api_key:
        try:
            import requests
            resp = requests.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5
            )
            if resp.status_code == 200:
                key_status = "valid"
                flash("AI settings saved. API Key is valid.", "success")
            else:
                key_status = "invalid"
                flash("AI settings saved, but API Key appears invalid.", "warning")
        except:
            key_status = "invalid"
            flash("AI settings saved, but couldn't reach OpenRouter to validate key.", "warning")
    else:
        flash("AI settings saved.", "success")
        
    Setting.set("ai_api_key_status", key_status)

    for key in AI_KEYS:
        if key in checkboxes:
            Setting.set(key, "true" if request.form.get(key) == "on" else "false")
        else:
            Setting.set(key, request.form.get(key, "").strip())
            
    return redirect(url_for("settings.index") + "#ai")


@settings_bp.route("/automation", methods=["POST"])
@login_required
def save_automation():
    """Save automation/queue settings (articles per run, word count)."""
    keys = ["ai_max_articles_per_run", "ai_word_count_min", "ai_word_count_target", "ai_custom_prompt"]
    for key in keys:
        Setting.set(key, request.form.get(key, "").strip())
    flash("Automation settings saved.", "success")
    return redirect(url_for("settings.index") + "#automation")


@settings_bp.route("/wordpress", methods=["POST"])
@login_required
def save_wordpress():
    checkboxes = {"wp_verify_publish"}
    for key in WP_KEYS:
        if key in checkboxes:
            Setting.set(key, "true" if request.form.get(key) == "on" else "false")
        else:
            Setting.set(key, request.form.get(key, "").strip())
    flash("WordPress settings saved.", "success")
    return redirect(url_for("settings.index") + "#wordpress")


@settings_bp.route("/seo", methods=["POST"])
@login_required
def save_seo():
    checkboxes = {"seo_faq_schema", "seo_auto_slug"}
    for key in SEO_KEYS:
        if key in checkboxes:
            Setting.set(key, "true" if request.form.get(key) == "on" else "false")
        else:
            Setting.set(key, request.form.get(key, "").strip())
    flash("SEO settings saved.", "success")
    return redirect(url_for("settings.index") + "#seo")


@settings_bp.route("/billing", methods=["POST"])
@login_required
def save_billing():
    """Save PayPal and M-Pesa configuration."""
    for key in BILLING_KEYS:
        if key in request.form:
            Setting.set(key, request.form.get(key, "").strip())
    flash("Billing configuration saved.", "success")
    # Redirect back to where they came from (Settings or Admin Pricing)
    return redirect(request.referrer or url_for("settings.index"))
@settings_bp.route("/save-branding", methods=["POST"])
@login_required
def save_branding():
    site_name = request.form.get("site_name")
    if site_name:
        Setting.set("site_name", site_name)
    
    if "site_logo" in request.files:
        file = request.files["site_logo"]
        if file and file.filename:
            filename = secure_filename(file.filename)
            # Ensure upload folder exists
            upload_folder = os.path.join(current_app.static_folder, "uploads", "branding")
            os.makedirs(upload_folder, exist_ok=True)
            
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            # Save the relative path for the frontend
            Setting.set("site_logo", f"/static/uploads/branding/{filename}")
            
    flash("Branding settings updated.", "success")
    return redirect(url_for("settings.index") + "#branding")
