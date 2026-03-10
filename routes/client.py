"""Client (subscriber) portal routes."""
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from models import db, User, Subscription, Transaction, PricingTier, Setting, Feed, Article, Notification, Coupon, Log, Feedback
from services.wordpress_service import push_to_wordpress, test_connection as wp_test_connection, get_categories as wp_get_categories
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime, timedelta, timezone

client_bp = Blueprint("client", __name__)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _get_active_sub():
    return Subscription.query.filter_by(
        user_id=current_user.id, status="active"
    ).first()


def _get_tier_limits(sub):
    """Return (article_limit, feed_limit) for the user's active subscription.
    Returns (2, 1) for trial users (no active subscription). -1 means unlimited."""
    if sub and sub.tier:
        return sub.tier.article_limit, sub.tier.feed_limit
    # Default trial limits for new accounts
    return 2, 1


def _check_and_notify_limit(sub, article_count, article_limit, feed_count, feed_limit):
    """Fire a notification when user reaches 80% of their article or feed quota."""
    if article_limit == -1 and feed_limit == -1:
        return  # Unlimited, no warnings needed

    messages = []
    if article_limit > 0:
        ratio = article_count / article_limit
        if ratio >= 0.8 and ratio < 1.0:
            messages.append(
                f"⚠️ You have used {article_count}/{article_limit} articles "
                f"({int(ratio*100)}% of your monthly limit). Consider upgrading."
            )
        elif ratio >= 1.0:
            messages.append(
                f"🚫 You've reached your article limit ({article_limit}/month). "
                f"Upgrade your plan to generate more."
            )

    if feed_limit > 0:
        ratio = feed_count / feed_limit
        if ratio >= 0.8 and ratio < 1.0:
            messages.append(
                f"⚠️ You've added {feed_count}/{feed_limit} allowed RSS feeds."
            )
        elif ratio >= 1.0:
            messages.append(
                f"🚫 You've reached your feed limit ({feed_limit}). "
                f"Upgrade your plan to add more feeds."
            )

    for msg in messages:
        # Avoid duplicate notifications — check if an identical unread one exists
        existing = Notification.query.filter_by(
            user_id=current_user.id, message=msg, is_read=False
        ).first()
        if not existing:
            db.session.add(Notification(user_id=current_user.id, message=msg))
    if messages:
        db.session.commit()


def _get_starter_tier():
    """Return the first active paid tier (for upgrade links)."""
    return PricingTier.query.filter_by(is_active=True).order_by(PricingTier.display_order).first()


# ─────────────────────────────────────────────────────────────
# Before request
# ─────────────────────────────────────────────────────────────

@client_bp.before_request
@login_required
def require_client():
    """Client portal is accessible to all authenticated users."""
    pass


# ─────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────

@client_bp.route("/")
@login_required
def index():
    """Client portal home page — shows subscription status and quick actions."""
    sub = _get_active_sub()
    article_limit, feed_limit = _get_tier_limits(sub)

    user_feed_ids = [f.id for f in Feed.query.filter_by(user_id=current_user.id).all()]
    article_count = Article.query.filter(Article.feed_id.in_(user_feed_ids)).count() if user_feed_ids else 0
    feed_count = len(user_feed_ids)

    recent_transactions = (
        Transaction.query.filter_by(user_id=current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(3)
        .all()
    )

    # Fetch user-specific logs
    recent_activities = (
        Log.query.filter_by(user_id=current_user.id)
        .order_by(Log.timestamp.desc())
        .limit(5)
        .all()
    )

    # Fetch data for new FeedForge layout cards
    recent_feeds = Feed.query.filter_by(user_id=current_user.id).order_by(Feed.created_at.desc()).limit(5).all()
    
    recently_published_articles = []
    queued_articles = []
    if user_feed_ids:
        recently_published_articles = (
            Article.query.filter(Article.feed_id.in_(user_feed_ids), Article.status == 'pushed')
            .order_by(Article.created_at.desc())
            .limit(5)
            .all()
        )
        queued_articles = (
            Article.query.filter(Article.feed_id.in_(user_feed_ids), Article.status.in_(['pending', 'generated']))
            .order_by(Article.created_at.desc())
            .limit(5)
            .all()
        )

    # Check limits and fire notifications if approaching
    _check_and_notify_limit(sub, article_count, article_limit, feed_count, feed_limit)

    # WordPress Connection Status for Overview Card
    wp_connected = False
    if current_user.wp_url and current_user.wp_user and current_user.wp_password:
        wp_connected = True

    return render_template(
        "client/index.html",
        sub=sub,
        recent_transactions=recent_transactions,
        recent_activities=recent_activities,
        recent_feeds=recent_feeds,
        recently_published_articles=recently_published_articles,
        queued_articles=queued_articles,
        article_count=article_count,
        article_limit=article_limit,
        feed_count=feed_count,
        feed_limit=feed_limit,
        wp_connected=wp_connected,
        upgrade_tier=_get_starter_tier(),
        active_model=Setting.get("ai_model", "openai/gpt-4o-mini"),
        schedule_enabled=Setting.get("schedule_enabled") == "true",
        schedule_frequency=Setting.get("schedule_frequency", "60"),
        automation_status=Setting.get("automation_status", "idle"),
    )


# ─────────────────────────────────────────────────────────────
# Feeds
# ─────────────────────────────────────────────────────────────

@client_bp.route("/feeds/<int:feed_id>/toggle")
@login_required
def feed_toggle(feed_id):
    """Toggle a feed's active status."""
    feed = Feed.query.filter_by(id=feed_id, user_id=current_user.id).first_or_404()
    feed.active = not feed.active
    db.session.commit()
    flash(f"Feed '{feed.name}' is now {'active' if feed.active else 'paused'}.", "success")
    return redirect(request.referrer or url_for("client.index"))

@client_bp.route("/feeds", methods=["GET", "POST"])
@login_required
def feeds():
    """Manage RSS feeds — limits enforced per tier."""
    sub = _get_active_sub()
    article_limit, feed_limit = _get_tier_limits(sub)
    user_feeds = Feed.query.filter_by(user_id=current_user.id).all()

    if request.method == "POST":
        if feed_limit != -1 and len(user_feeds) >= feed_limit:
            flash(
                f"Your plan is limited to {feed_limit} RSS feed{'s' if feed_limit > 1 else ''}. "
                f"Upgrade to add more.",
                "error"
            )
            return redirect(url_for("client.feeds"))

        name = request.form.get("name", "").strip()
        url = request.form.get("url", "").strip()

        if not name or not url:
            flash("Name and URL are required.", "error")
        else:
            existing = Feed.query.filter_by(user_id=current_user.id, url=url).first()
            if existing:
                flash("You already added this feed.", "error")
            else:
                feed = Feed(name=name, url=url, user_id=current_user.id)
                db.session.add(feed)
                db.session.commit()
                flash("Feed added successfully!", "success")

        return redirect(url_for("client.feeds"))

    return render_template(
        "client/feeds.html",
        sub=sub,
        feeds=user_feeds,
        feed_limit=feed_limit,
        upgrade_tier=_get_starter_tier(),
    )


# ─────────────────────────────────────────────────────────────
# Articles
# ─────────────────────────────────────────────────────────────

@client_bp.route("/articles")
@login_required
def articles():
    """View generated articles for this user's feeds only."""
    sub = _get_active_sub()
    article_limit, feed_limit = _get_tier_limits(sub)

    user_feed_ids = [f.id for f in Feed.query.filter_by(user_id=current_user.id).all()]

    if user_feed_ids:
        user_articles = (
            Article.query.filter(Article.feed_id.in_(user_feed_ids))
            .order_by(Article.created_at.desc())
            .all()
        )
    else:
        user_articles = []

    article_count = len(user_articles)
    _check_and_notify_limit(sub, article_count, article_limit,
                            len(user_feed_ids), feed_limit)

    return render_template(
        "client/articles.html",
        sub=sub,
        articles=user_articles,
        article_count=article_count,
        article_limit=article_limit,
        upgrade_tier=_get_starter_tier(),
    )


# ─────────────────────────────────────────────────────────────
# Automation
# ─────────────────────────────────────────────────────────────

@client_bp.route("/automation", methods=["GET", "POST"])
@login_required
def automation():
    """Automation control panel. Gated for paid users."""
    sub = _get_active_sub()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "run_now":
            from services.automation_service import run_node_1_rss_fetcher, run_node_2_worker, cleanup_stale_locks
            cleanup_stale_locks()
            run_node_1_rss_fetcher()
            run_node_2_worker()
            flash("Automation heartbeat triggered successfully!", "success")
        return redirect(url_for("client.automation"))

    user_feed_ids = [f.id for f in Feed.query.filter_by(user_id=current_user.id).all()]
    
    # Simple metrics for the UI
    pending_count = Article.query.filter(
        Article.feed_id.in_(user_feed_ids), Article.status == "pending"
    ).count() if user_feed_ids else 0

    # Fetch recent activity for this user specifically
    articles = []
    if user_feed_ids:
        articles = Article.query.filter(Article.feed_id.in_(user_feed_ids)).order_by(Article.created_at.desc()).limit(15).all()

    return render_template(
        "client/automation.html",
        sub=sub,
        pending_count=pending_count,
        articles=articles,
        upgrade_tier=_get_starter_tier(),
    )


# ─────────────────────────────────────────────────────────────
# Subscription
# ─────────────────────────────────────────────────────────────

@client_bp.route("/subscription")
@login_required
def subscription():
    """Show the user's subscription details."""
    sub = _get_active_sub()
    article_limit, feed_limit = _get_tier_limits(sub)
    all_subs = Subscription.query.filter_by(user_id=current_user.id).order_by(
        Subscription.created_at.desc()
    ).all()
    tiers = PricingTier.query.filter_by(is_active=True).order_by(PricingTier.display_order).all()

    user_feed_ids = [f.id for f in Feed.query.filter_by(user_id=current_user.id).all()]
    article_count = Article.query.filter(Article.feed_id.in_(user_feed_ids)).count() if user_feed_ids else 0

    return render_template(
        "client/subscription.html",
        sub=sub,
        all_subs=all_subs,
        tiers=tiers,
        article_limit=article_limit,
        feed_limit=feed_limit,
        article_count=article_count,
        feed_count=len(user_feed_ids),
    )


@client_bp.route("/subscription/cancel", methods=["POST"])
@login_required
def cancel_subscription():
    """Cancel the active subscription."""
    sub = _get_active_sub()
    if not sub:
        flash("No active subscription to cancel.", "info")
        return redirect(url_for("client.subscription"))

    sub.status = "cancelled"
    sub.auto_renew = False
    db.session.commit()

    # Notify user
    note = Notification(
        user_id=current_user.id,
        message="Your subscription has been cancelled. You'll retain access until the current period ends."
    )
    db.session.add(note)
    db.session.commit()

    flash("Subscription cancelled. You'll retain access until the end of your billing period.", "success")
    return redirect(url_for("client.subscription"))


@client_bp.route("/subscription/toggle-renew", methods=["POST"])
@login_required
def toggle_auto_renew():
    """Toggle auto-renewal on the active subscription."""
    sub = _get_active_sub()
    if not sub:
        return jsonify({"success": False, "error": "No active subscription"}), 400
    sub.auto_renew = not sub.auto_renew
    db.session.commit()
    return jsonify({"success": True, "auto_renew": sub.auto_renew})


# ─────────────────────────────────────────────────────────────
# Billing
# ─────────────────────────────────────────────────────────────

@client_bp.route("/billing", methods=["GET", "POST"])
@login_required
def billing():
    """Show the user's transaction history and manage billing profile."""
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.billing_company = request.form.get("billing_company", "").strip()
        current_user.billing_address = request.form.get("billing_address", "").strip()
        current_user.billing_city = request.form.get("billing_city", "").strip()
        current_user.billing_country = request.form.get("billing_country", "").strip()
        current_user.billing_zip = request.form.get("billing_zip", "").strip()
        current_user.billing_tax_id = request.form.get("billing_tax_id", "").strip()
        db.session.commit()
        flash("Billing profile updated successfully.", "success")
        return redirect(url_for("client.billing"))

    transactions = (
        Transaction.query.filter_by(user_id=current_user.id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    
    sub = _get_active_sub()
    article_limit, feed_limit = _get_tier_limits(sub)
    
    # Usage Stats
    user_feed_ids = [f.id for f in current_user.feeds]
    if user_feed_ids:
        # All generated articles
        all_articles = Article.query.filter(Article.feed_id.in_(user_feed_ids)).all()
        article_count = len([a for a in all_articles if a.status == "published"])
        rewrite_count = len([a for a in all_articles if a.status in ["rewriting", "published", "publishing"]])
    else:
        article_count = 0
        rewrite_count = 0
    
    feed_count = len(current_user.feeds)

    # Rewrite limit (arbitrarily 2x article limit or similar if not defined, 
    # but the design shows specific numbers like 847 / 1,000)
    # I'll use 2x article_limit as a placeholder if article_limit is set, otherwise 1000.
    rewrite_limit = article_limit * 2 if article_limit != -1 else -1

    return render_template(
        "client/billing.html", 
        transactions=transactions,
        sub=sub,
        article_count=article_count,
        article_limit=article_limit,
        rewrite_count=rewrite_count,
        rewrite_limit=rewrite_limit,
        feed_count=feed_count,
        feed_limit=feed_limit
    )


@client_bp.route("/billing/receipt/<int:tx_id>")
@login_required
def receipt(tx_id):
    """Show a payment receipt for a specific transaction."""
    tx = Transaction.query.filter_by(id=tx_id, user_id=current_user.id).first_or_404()
    sub = Subscription.query.filter_by(
        user_id=current_user.id, gateway_ref_id=tx.external_id
    ).first()
    return render_template("client/receipt.html", tx=tx, sub=sub)


# ─────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# Checkout
# ─────────────────────────────────────────────────────────────

@client_bp.route("/checkout")
@login_required
def checkout():
    """Checkout page where user pays via M-Pesa or PayPal."""
    tier_id = request.args.get("tier_id")
    if not tier_id:
        flash("Please select a pricing plan first.", "error")
        return redirect(url_for("client.subscription"))

    tier = PricingTier.query.get_or_404(tier_id)
    currency = Setting.get("currency", "USD")
    paypal_client_id = Setting.get("paypal_client_id", "")

    # KES conversion: 1 USD ≈ 129 KES (approximate; can be set in settings)
    kes_rate = float(Setting.get("kes_rate", "129"))
    kes_price = round(tier.price * kes_rate, 0)

    # If it's a trial and user hasn't used one, they can activate directly.
    # However, we often still want them to go to checkout to see the "Start Trial" option.

    return render_template(
        "client/checkout.html",
        tier=tier,
        currency=currency,
        paypal_client_id=paypal_client_id,
        kes_price=kes_price,
    )


@client_bp.route("/activate-trial")
@login_required
def activate_trial():
    """Immediately activate the 2-article free trial for the Starter tier."""
    tier_id = request.args.get("tier_id")
    tier = PricingTier.query.get_or_404(tier_id)
    
    if not tier.has_free_trial:
        flash("This plan does not support a free trial.", "error")
        return redirect(url_for("client.subscription"))

    # Check if they already have an active sub
    if current_user.subscription and current_user.subscription.status == "active" and current_user.subscription.pricing_tier_id:
        flash("You already have an active subscription.", "info")
        return redirect(url_for("client.index"))

    from datetime import timedelta
    
    # Activate / Update sub
    if not current_user.subscription:
        from models import Subscription
        current_user.subscription = Subscription(user_id=current_user.id)
    
    sub = current_user.subscription
    sub.pricing_tier_id = tier.id
    sub.status = "active"
    sub.plan_name = f"{tier.name} (Trial)"
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=7) # 7 day trial or until 2 articles used
    
    db.session.commit()
    flash(f"Success! Your {tier.name} trial is active. You can generate up to 2 articles.", "success")
    return redirect(url_for("client.index"))


@client_bp.route("/checkout/mpesa", methods=["POST"])
@login_required
def checkout_mpesa():
    """Handle M-Pesa STK Push initiation."""
    tier_id = request.form.get("tier_id")
    phone_number = request.form.get("phone_number")
    auto_renew = request.form.get("auto_renew") == "on"

    tier = PricingTier.query.get_or_404(tier_id)
    coupon_code = request.form.get("coupon_code", "").upper().strip()
    
    # Strict Coupon Validation
    final_price = tier.price
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon:
            now = datetime.now(timezone.utc)
            expires_at = coupon.expires_at.replace(tzinfo=timezone.utc) if coupon.expires_at else None
            
            if not expires_at or expires_at > now:
                final_price = tier.price * (1 - coupon.discount_percent / 100)
            else:
                # Coupon expired
                coupon.is_active = False
                db.session.commit()
                flash("The coupon code has expired.", "error")
                return redirect(url_for("client.checkout", tier_id=tier.id))
        else:
            flash("Invalid coupon code.", "error")
            return redirect(url_for("client.checkout", tier_id=tier.id))

    tx_ref = f"CTX-{uuid.uuid4().hex[:8].upper()}"

    kes_rate = float(Setting.get("kes_rate", "129"))
    kes_amount = round(final_price * kes_rate, 2)

    tx = Transaction(
        user_id=current_user.id,
        amount=kes_amount,
        currency="KES",
        provider="mpesa",
        status="pending",
        external_id=tx_ref
    )
    db.session.add(tx)

    sub = _get_active_sub()
    if not sub:
        sub = Subscription(user_id=current_user.id, status="inactive")
        db.session.add(sub)

    sub.plan_name = tier.name
    sub.pricing_tier_id = tier.id
    sub.payment_method = "mpesa"
    sub.preferred_payment_method = "mpesa"
    sub.payment_details = phone_number
    sub.auto_renew = auto_renew
    sub.gateway_ref_id = tx_ref

    if tier.interval == "yearly":
        sub.current_period_end = datetime.utcnow() + timedelta(days=365)
    else:
        sub.current_period_end = datetime.utcnow() + timedelta(days=30)

    db.session.commit()

    flash(
        f"M-Pesa STK Push sent to {phone_number}. "
        f"Your {tier.name} plan will activate upon payment confirmation.",
        "info"
    )
    return redirect(url_for("client.index"))


@client_bp.route("/checkout/paypal", methods=["POST"])
@login_required
def checkout_paypal():
    """Handle PayPal success callback from JS SDK."""
    data = request.get_json() or {}
    tier_id = data.get("tier_id")
    order_id = data.get("order_id")
    coupon_code = data.get("coupon_code", "").upper().strip()
    auto_renew = data.get("auto_renew", False)

    if not tier_id or not order_id:
        return {"success": False, "error": "Missing parameters"}, 400

    tier = PricingTier.query.get_or_404(tier_id)

    # Strict Coupon Validation
    final_price = tier.price
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon:
            now = datetime.now(timezone.utc)
            expires_at = coupon.expires_at.replace(tzinfo=timezone.utc) if coupon.expires_at else None

            if not expires_at or expires_at > now:
                final_price = tier.price * (1 - coupon.discount_percent / 100)
            else:
                # Coupon expired
                coupon.is_active = False
                db.session.commit()
                return {"success": False, "error": "Coupon expired"}, 400
        else:
            return {"success": False, "error": "Invalid coupon"}, 400

    tx = Transaction(
        user_id=current_user.id,
        amount=final_price,
        currency="USD",
        provider="paypal",
        status="pending",
        external_id=order_id
    )
    db.session.add(tx)

    sub = _get_active_sub()
    if not sub:
        sub = Subscription(user_id=current_user.id, status="inactive")
        db.session.add(sub)

    sub.plan_name = tier.name
    sub.pricing_tier_id = tier.id
    sub.payment_method = "paypal"
    sub.preferred_payment_method = "paypal"
    sub.payment_details = "PayPal Account"
    sub.auto_renew = auto_renew
    sub.gateway_ref_id = order_id

    if tier.interval == "yearly":
        sub.current_period_end = datetime.utcnow() + timedelta(days=365)
    else:
        sub.current_period_end = datetime.utcnow() + timedelta(days=30)

    db.session.commit()

    flash(f"PayPal payment recorded. Your {tier.name} plan will activate shortly.", "info")
    return {"success": True}


# ─────────────────────────────────────────────────────────────
# Notifications API
# ─────────────────────────────────────────────────────────────

@client_bp.route("/api/notifications")
@login_required
def get_notifications_api():
    """Fetch unread notifications for current user."""
    notes = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(10).all()
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


@client_bp.route("/api/apply-coupon", methods=["POST"])
@login_required
def apply_coupon():
    """Validate a coupon code and return the discount percentage."""
    data = request.get_json() or {}
    code = data.get("code", "").upper().strip()
    
    if not code:
        return jsonify({"success": False, "error": "No code provided"}), 400
        
    coupon = Coupon.query.filter_by(code=code, is_active=True).first()
    
    if not coupon:
        return jsonify({"success": False, "error": "Invalid or expired coupon code."})
        
    # Check expiry
    if coupon.expires_at and coupon.expires_at.replace(tzinfo=None) < datetime.utcnow():
        coupon.is_active = False
        db.session.commit()
        return jsonify({"success": False, "error": "This coupon code has expired."})
        
    return jsonify({
        "success": True,
        "discount_percent": coupon.discount_percent,
        "code": coupon.code
    })

@client_bp.route("/api/feedback", methods=["POST"])
@login_required
def submit_feedback():
    """Handle user feedback submission."""
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"success": False, "error": "Message is required"}), 400
        
    feedback = Feedback(user_id=current_user.id, message=message)
    db.session.add(feedback)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Thank you for your feedback!"})

# ─────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────

@client_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Client-side settings for WordPress and other preferences."""
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_wordpress":
            current_user.wp_url = request.form.get("wp_url", "").strip()
            current_user.wp_user = request.form.get("wp_user", "").strip()
            
            # Only update password if provided
            new_password = request.form.get("wp_password", "").strip()
            if new_password:
                current_user.wp_password = new_password
                
            db.session.commit()
            flash("WordPress settings updated successfully.", "success")
            
        elif action == "update_wp_category":
            cat_id = request.form.get("wp_default_category")
            if cat_id:
                current_user.wp_default_category = int(cat_id)
                db.session.commit()
                flash("Default WordPress category updated.", "success")
                
        return redirect(url_for("client.settings"))

    # Fetch WP categories if credentials exist
    wp_categories = []
    if current_user.wp_url and current_user.wp_user and current_user.wp_password:
        res = wp_get_categories(user=current_user)
        if res.get("success"):
            wp_categories = res.get("categories", [])

    return render_template(
        "client/settings.html",
        wp_categories=wp_categories
    )


@client_bp.route("/settings/test-wp", methods=["POST"])
@login_required
def test_wp_connection():
    """Test the WordPress credentials for the current user."""
    res = wp_test_connection(user=current_user)
    return jsonify(res)
