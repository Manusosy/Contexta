"""Client (subscriber) portal routes."""
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from flask_login import login_required, current_user
from models import db, User, Subscription, Transaction, PricingTier, Setting, Feed, Article

from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime, timedelta

client_bp = Blueprint("client", __name__)

@client_bp.route("/feeds", methods=["GET", "POST"])
@login_required
def feeds():
    """Manage RSS feeds. Free tier restricted to 1 feed."""
    sub = _get_active_sub()
    user_feeds = Feed.query.filter_by(user_id=current_user.id).all()
    
    if request.method == "POST":
        if not sub and len(user_feeds) >= 1:
            flash("Free tier is limited to 1 RSS feed. Please upgrade to add more.", "error")
            return redirect(url_for("client.feeds"))
        
        name = request.form.get("name", "").strip()
        url = request.form.get("url", "").strip()
        
        if not name or not url:
            flash("Name and URL are required.", "error")
        else:
            # Check if feed already exists for this user
            existing = Feed.query.filter_by(user_id=current_user.id, url=url).first()
            if existing:
                flash("You already added this feed.", "error")
            else:
                feed = Feed(name=name, url=url, user_id=current_user.id)
                db.session.add(feed)
                db.session.commit()
                flash("Feed added successfully!", "success")
                
        return redirect(url_for("client.feeds"))
        
    return render_template("client/feeds.html", sub=sub, feeds=user_feeds)


@client_bp.route("/articles")
@login_required
def articles():
    """View generated articles."""
    sub = _get_active_sub()
    user_articles = Article.query.order_by(Article.created_at.desc()).limit(50).all()
    return render_template("client/articles.html", sub=sub, articles=user_articles)


@client_bp.route("/automation", methods=["GET", "POST"])
@login_required
def automation():
    """Automation control panel. Gated for paid users."""
    sub = _get_active_sub()
    
    if request.method == "POST":
        if not sub:
            flash("Automation is only available for Pro subscribers.", "info")
            return redirect(url_for("client.automation"))
            
        action = request.form.get("action")
        if action == "run_now":
            flash("Automation triggered successfully!", "success")
        return redirect(url_for("client.automation"))
        
    return render_template("client/automation.html", sub=sub)


@client_bp.before_request
@login_required
def require_client():
    """Client portal is accessible to all authenticated users.
    Admins can preview it; clients are restricted here."""
    pass  # All authenticated users can access, role-specific content is shown in templates


def _get_active_sub():
    return Subscription.query.filter_by(
        user_id=current_user.id, status="active"
    ).first()


@client_bp.route("/")
@login_required
def index():
    """Client portal home page — shows subscription status and quick actions."""
    sub = _get_active_sub()
    recent_transactions = (
        Transaction.query.filter_by(user_id=current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "client/index.html",
        sub=sub,
        recent_transactions=recent_transactions,
    )


@client_bp.route("/subscription")
@login_required
def subscription():
    """Show the user's subscription details."""
    sub = _get_active_sub()
    all_subs = Subscription.query.filter_by(user_id=current_user.id).order_by(
        Subscription.created_at.desc()
    ).all()
    return render_template("client/subscription.html", sub=sub, all_subs=all_subs)


@client_bp.route("/billing")
@login_required
def billing():
    """Show the user's transaction / payment history."""
    transactions = (
        Transaction.query.filter_by(user_id=current_user.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    return render_template("client/billing.html", transactions=transactions)


@client_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Allow user to update their name, email, and password."""
    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_profile":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()

            if not full_name or not email:
                flash("Name and email are required.", "error")
            elif email != current_user.email and User.query.filter_by(email=email).first():
                flash("That email is already in use.", "error")
            else:
                current_user.full_name = full_name
                current_user.email = email
                db.session.commit()
                flash("Profile updated successfully.", "success")

        elif action == "change_password":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")

            if not current_user.check_password(current_pw):
                flash("Current password is incorrect.", "error")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "error")
            elif len(new_pw) < 8:
                flash("Password must be at least 8 characters.", "error")
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash("Password changed successfully.", "success")

        return redirect(url_for("client.profile"))

    if current_user.role == "admin":
        return render_template("admin/profile.html")
    return render_template("client/profile.html")


@client_bp.route("/checkout")
@login_required
def checkout():
    """Checkout page where user pays via M-Pesa or PayPal."""
    tier_id = request.args.get("tier_id")
    if not tier_id:
        flash("Please select a pricing plan first.", "error")
        return redirect(url_for("public.index", _anchor="pricing"))
        
    tier = PricingTier.query.get_or_404(tier_id)
    currency = Setting.get("currency", "USD")
    paypal_client_id = Setting.get("paypal_client_id", "")
    
    return render_template(
        "client/checkout.html",
        tier=tier,
        currency=currency,
        paypal_client_id=paypal_client_id
    )


@client_bp.route("/checkout/mpesa", methods=["POST"])
@login_required
def checkout_mpesa():
    """Handle M-Pesa STK Push logic and simulate completion for demo."""
    tier_id = request.form.get("tier_id")
    phone_number = request.form.get("phone_number")
    
    tier = PricingTier.query.get_or_404(tier_id)
    tx_ref = f"CTX-{uuid.uuid4().hex[:8].upper()}"
    
    # Store a pending transaction structure
    tx = Transaction(
        user_id=current_user.id,
        amount=tier.price,
        currency="KES",
        provider="mpesa",
        status="pending", # Pending until webhook confirms
        external_id=tx_ref
    )
    db.session.add(tx)
    
    # Update or create subscription
    sub = _get_active_sub()
    if not sub:
        sub = Subscription(user_id=current_user.id, status="inactive") # Inactive until paid
        db.session.add(sub)
        
    sub.plan_name = tier.name
    sub.pricing_tier_id = tier.id
    sub.payment_method = "mpesa"
    sub.gateway_ref_id = tx_ref
    
    if tier.interval == "yearly":
        sub.current_period_end = datetime.utcnow() + timedelta(days=365)
    else:
        sub.current_period_end = datetime.utcnow() + timedelta(days=30)
        
    db.session.commit()
    
    flash(f"STK Push initiated for {tier.name}. Your subscription will activate upon payment confirmation.", "info")
    return redirect(url_for("client.index"))


@client_bp.route("/checkout/paypal", methods=["POST"])
@login_required
def checkout_paypal():
    """Handle PayPal success callback from JS SDK."""
    data = request.get_json() or {}
    tier_id = data.get("tier_id")
    order_id = data.get("order_id")
    
    if not tier_id or not order_id:
        return {"success": False, "error": "Missing parameters"}, 400
        
    tier = PricingTier.query.get_or_404(tier_id)
    
    tx = Transaction(
        user_id=current_user.id,
        amount=tier.price,
        currency="USD",
        provider="paypal",
        status="pending", # Pending until IPN/Webhook confirms
        external_id=order_id
    )
    db.session.add(tx)
    
    sub = _get_active_sub()
    if not sub:
        sub = Subscription(user_id=current_user.id, status="inactive") # Inactive until paid
        db.session.add(sub)
        
    sub.plan_name = tier.name
    sub.pricing_tier_id = tier.id
    sub.payment_method = "paypal"
    sub.gateway_ref_id = order_id
    
    if tier.interval == "yearly":
        sub.current_period_end = datetime.utcnow() + timedelta(days=365)
    else:
        sub.current_period_end = datetime.utcnow() + timedelta(days=30)
        
    db.session.commit()
    
    flash(f"PayPal payment recorded. Your subscription will activate shortly once verified.", "info")
    return {"success": True}


@client_bp.route("/api/notifications")
@login_required
def get_notifications_api():
    """Fetch unread notifications for current user."""
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(10).all()
    return jsonify([
        {
            "id": n.id,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.strftime("%b %d, %H:%M")
        } for n in notes
    ])


@client_bp.route("/api/notifications/mark-read", methods=["POST"])
@login_required
def mark_notifications_read():
    """Mark all notifications as read."""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"success": True})
