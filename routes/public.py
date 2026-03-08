from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def index():
    if current_user.is_authenticated:
        if not current_user.onboarding_completed:
            return redirect(url_for("onboarding.index"))
        # Role-based redirect
        if current_user.role == "admin":
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("client.index"))

    from models import PricingTier, Setting
    tiers = PricingTier.query.filter_by(is_active=True).order_by(PricingTier.display_order).all()
    currency = Setting.get("currency", "USD")
    return render_template("public/index.html", tiers=tiers, currency=currency)
