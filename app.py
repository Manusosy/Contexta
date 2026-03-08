import os
from flask import Flask, request, redirect, url_for
from flask_login import LoginManager, current_user
from models import db, Setting, User
from config import get_config
from services.scheduler_service import init_scheduler
from flask_wtf.csrf import CSRFProtect
from utils.email_service import init_mail

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config())

    if not app.config.get("DEBUG") and app.config.get("SECRET_KEY") == "contexta-dev-secret-change-in-prod":
        raise RuntimeError("CRITICAL: Default SECRET_KEY is used in Production! Please set SECRET_KEY environment variable.")

    # Init extensions
    db.init_app(app)
    csrf.init_app(app)
    init_mail(app)

    # Init Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to access this page."
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.feeds import feeds_bp
    from routes.articles import articles_bp
    from routes.settings import settings_bp
    from routes.public import public_bp
    from routes.onboarding import onboarding_bp
    from routes.api import api_bp
    from routes.client import client_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(onboarding_bp, url_prefix="/onboarding")
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp, url_prefix="/admin-portal")
    app.register_blueprint(feeds_bp, url_prefix="/feeds")
    app.register_blueprint(articles_bp, url_prefix="/articles")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(client_bp, url_prefix="/portal")

    @app.before_request
    def check_onboarding():
        """Ensure authenticated users verify email and complete onboarding."""
        if current_user.is_authenticated:
            # Bypass static files, the onboarding route itself, logout, and verify email
            if request.endpoint and (
                request.endpoint.startswith("static")
                or request.endpoint.startswith("onboarding.")
                or request.endpoint == "auth.verify_email"
                or request.endpoint == "auth.logout"
            ):
                return
            if not getattr(current_user, 'is_verified', True):  # Fallback to True if not migrated yet
                return redirect(url_for("auth.verify_email"))
            if not current_user.onboarding_completed:
                return redirect(url_for("onboarding.index"))

    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from models import Announcement, Setting, User
        from flask_wtf.csrf import generate_csrf
        return {
            'now': datetime.utcnow(),
            'app_version': Setting.get('app_version', '1.1.0'),
            'Announcement': Announcement,
            'Setting': Setting,
            'User': User,
            'csrf_token': generate_csrf
        }

    # Create tables and seed defaults
    with app.app_context():
        db.create_all()
        _seed_defaults()
        _seed_pricing()
        _seed_admin()

    # Init the background scheduler
    init_scheduler(app)

    return app


def _seed_admin():
    """Create default admin user from env vars if no users exist."""
    if User.query.count() == 0:
        username = os.environ.get("ADMIN_USER", "admin@kazinikazi.co.ke")
        password = os.environ.get("ADMIN_PASSWORD", "Demo@12345")
        user = User(username=username, email=username, full_name="System Admin", role="admin")
        user.set_password(password)
        user.is_verified = True
        db.session.add(user)
        db.session.commit()
        print(f"[Contexta] Default admin created: username/email='{username}' — change the password in production!")


def _seed_defaults():
    """Insert default settings if they don't exist."""
    defaults = {
        "ai_api_key": "",
        "ai_model": "openai/gpt-4o-mini",
        "ai_temperature": "0.7",
        "ai_max_tokens": "2000",
        "ai_style_instructions": "",
        "ai_preserve_tone": "true",
        "ai_avoid_generic": "true",
        "ai_no_long_dashes": "true",
        "ai_regional_insight": "false",
        "wp_url": "",
        "wp_user": "",
        "wp_password": "",
        "wp_default_category": "1",
        "seo_meta_length": "160",
        "seo_faq_schema": "false",
        "seo_auto_slug": "true",
        "schedule_enabled": "false",
        "schedule_frequency": "60",
        "site_name": "Contexta",
        "site_logo": "/static/img/logo.png",
        "last_run": "",
        "automation_status": "idle",
        "ai_word_count_min": "350",
        "ai_word_count_target": "600",
        "ai_custom_prompt": "",
        "ai_max_articles_per_run": "1",
        "wp_verify_publish": "true",
    }
    for key, value in defaults.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key, value=value))
    db.session.commit()


def _seed_pricing():
    """Insert default pricing tiers and features if they don't exist."""
    from models import PricingTier, PricingFeature
    if PricingTier.query.count() == 0:
        tiers_data = [
            {
                "name": "Starter", "price": 3.50, "currency": "USD", "interval": "monthly",
                "article_limit": 20, "feed_limit": 1, "is_featured": False, "has_free_trial": True,
                "display_order": 1,
                "features": [
                    "2 Articles Free Trial",
                    "1 Active RSS Feed",
                    "Automation Heartbeat",
                    "WP Integration",
                    "Standard Support"
                ],
            },
            {
                "name": "Starter Annual", "price": 35.0, "currency": "USD", "interval": "yearly",
                "article_limit": 20, "feed_limit": 1, "is_featured": False, "has_free_trial": False,
                "display_order": 2,
                "features": [
                    "20 Articles / Mo",
                    "1 Active RSS Feed",
                    "2 Months Free",
                    "WP Integration",
                    "Standard Support"
                ],
            },
            {
                "name": "Growth", "price": 9.50, "currency": "USD", "interval": "monthly",
                "article_limit": 100, "feed_limit": 5, "is_featured": True, "has_free_trial": False,
                "display_order": 3,
                "features": [
                    "100 Articles / Mo",
                    "5 Active RSS Feeds",
                    "Priority Processing",
                    "SEO Optimization",
                    "Premium Support"
                ],
            },
            {
                "name": "Growth Annual", "price": 95.0, "currency": "USD", "interval": "yearly",
                "article_limit": 100, "feed_limit": 5, "is_featured": False, "has_free_trial": False,
                "display_order": 4,
                "features": [
                    "100 Articles / Mo",
                    "5 Active RSS Feeds",
                    "SEO Optimization",
                    "2 Months Free",
                    "Priority Support"
                ],
            },
            {
                "name": "Pro", "price": 19.0, "currency": "USD", "interval": "monthly",
                "article_limit": -1, "feed_limit": -1, "is_featured": False, "has_free_trial": False,
                "display_order": 5,
                "features": [
                    "Unlimited Articles",
                    "Unlimited RSS Feeds",
                    "White-label Branding",
                    "Custom Logic",
                    "24/7 VIP Support"
                ],
            },
            {
                "name": "Pro Annual", "price": 190.0, "currency": "USD", "interval": "yearly",
                "article_limit": -1, "feed_limit": -1, "is_featured": False, "has_free_trial": False,
                "display_order": 6,
                "features": [
                    "Unlimited Articles",
                    "Unlimited RSS Feeds",
                    "White-label Branding",
                    "Custom Logic",
                    "24/7 VIP Support"
                ],
            }
        ]
        for td in tiers_data:
            feats = td.pop("features")
            tier = PricingTier(**td)
            db.session.add(tier)
            db.session.flush()
            for i, text in enumerate(feats):
                db.session.add(PricingFeature(tier_id=tier.id, feature_text=text, display_order=i))

        db.session.commit()
        print("[Contexta] Default pricing tiers seeded: Starter, Growth, Pro.")


app = create_app()

if __name__ == "__main__":
    app.run(
        debug=app.config.get("DEBUG", False),
        host="0.0.0.0",
        port=5000,
    )
