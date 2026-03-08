from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from models import db

onboarding_bp = Blueprint("onboarding", __name__)


@onboarding_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if current_user.onboarding_completed:
        if current_user.role == "admin":
            return redirect(url_for("dashboard.index"))
        t_id = session.pop("checkout_tier_id", None)
        if t_id:
            return redirect(url_for("client.checkout", tier_id=t_id))
        return redirect(url_for("client.index"))

    if request.method == "POST":
        heard_from = request.form.get("heard_from", "").strip()
        current_user.heard_from = heard_from
        current_user.onboarding_completed = True
        db.session.commit()
        flash("Welcome to Contexta! Your onboarding is complete.", "success")
        # Role-based redirect after onboarding
        if current_user.role == "admin":
            return redirect(url_for("dashboard.index"))
        t_id = session.pop("checkout_tier_id", None)
        if t_id:
            return redirect(url_for("client.checkout", tier_id=t_id))
        return redirect(url_for("client.index"))

    return render_template("onboarding/index.html")
