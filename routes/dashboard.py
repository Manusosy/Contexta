from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone, timedelta
from models import db, Feed, Article, Setting, Log, User, Transaction, Coupon, PricingTier, PricingFeature, Announcement, Notification, Feedback
from services.billing_service import get_revenue_metrics

dashboard_bp = Blueprint("dashboard", __name__)


def admin_required(f):
    """Decorator to ensure only admins can access a route."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Access denied. Admins only.", "error")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated_function


@dashboard_bp.route("/")
@login_required
def index():
    if current_user.role != "admin":
        return redirect(url_for("client.index"))

    # Recent activity for the admin dashboard should focus on ADMIN/SYSTEM feeds
    admin_feed_ids = [f.id for f in Feed.query.filter_by(user_id=None).all()]
    recent_articles = Article.query.filter(Article.feed_id.in_(admin_feed_ids)).order_by(Article.created_at.desc()).limit(10).all()
    recent_logs = Log.query.filter_by(user_id=None).order_by(Log.timestamp.desc()).limit(8).all()
    
    # Platform Analytics (Already implemented correctly for all clients)
    total_clients = User.query.filter_by(role="client").count()
    active_clients = User.query.filter_by(role="client", is_active=True).count()
    
    # Paying members (active subscriptions)
    from models import Subscription
    paying_members = Subscription.query.filter_by(status="active").count()
    
    # Registrations trend (last 30 days)
    now = datetime.now(timezone.utc)
    
    # New user growth (this week)
    seven_days_ago = now - timedelta(days=7)
    new_users_week = User.query.filter(User.role == "client", User.created_at >= seven_days_ago).count()
    
    # Weekly growth percentage
    prev_week_start = now - timedelta(days=14)
    prev_week_users = User.query.filter(User.role == "client", User.created_at >= prev_week_start, User.created_at < seven_days_ago).count()
    growth_pct = 0
    if prev_week_users > 0:
        growth_pct = int(((new_users_week - prev_week_users) / prev_week_users) * 100)
    elif new_users_week > 0:
        growth_pct = 100

    # Trend data points for frontend
    trend_data = []
    for i in range(29, -1, -1):
        day = (now - timedelta(days=i)).date()
        count = User.query.filter(User.role == "client", db.func.date(User.created_at) == day).count()
        trend_data.append({"date": day.strftime('%b %d'), "count": count})

    return render_template(
        "dashboard/index.html",
        total_feeds=len(admin_feed_ids),
        queued_articles=Article.query.filter(Article.feed_id.in_(admin_feed_ids), Article.status=="pending").count(),
        total_articles=Article.query.filter(Article.feed_id.in_(admin_feed_ids)).count(),
        active_model=Setting.get("ai_model", "openai/gpt-4o-mini"),
        schedule_enabled=Setting.get("schedule_enabled") == "true",
        schedule_frequency=Setting.get("schedule_frequency", "60"),
        automation_status=Setting.get("automation_status", "idle"),
        recent_articles=recent_articles,
        recent_logs=recent_logs,
        # Analytics
        total_clients=total_clients,
        active_clients=active_clients,
        paying_members=paying_members,
        new_users_week=new_users_week,
        growth_pct=growth_pct,
        trend_data=trend_data
    )


@dashboard_bp.route("/automation", methods=["GET", "POST"])
@login_required
@admin_required
def automation():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "run_now":
            from services.automation_service import run_node_1_rss_fetcher, run_node_2_worker, cleanup_stale_locks
            cleanup_stale_locks()
            run_node_1_rss_fetcher()
            run_node_2_worker()
            flash("System heartbeat triggered! Node 1 and next Node 2 cycle processed.", "success")
        return redirect(url_for("dashboard.automation"))

    # Metrics specific to the automation center
    stats = {
        "pending": Article.query.filter_by(status="pending").count(),
        "processing": Article.query.filter(Article.status.in_(["processing", "extracting", "rewriting", "publishing"])).count(),
        "published_today": Article.query.filter(
            Article.status == "published", 
            Article.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        ).count(),
        "failed": Article.query.filter_by(status="failed").count(),
    }
    
    articles = Article.query.order_by(Article.created_at.desc()).limit(15).all()
    
    return render_template("admin/automation.html", stats=stats, articles=articles)


@dashboard_bp.route("/search")
@login_required
@admin_required
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect(url_for("dashboard.index"))
    
    # Simple multi-model search for MVP
    articles = Article.query.filter(Article.original_title.ilike(f"%{query}%")).limit(10).all()
    users = User.query.filter(User.role == "client").filter(
        db.or_(User.username.ilike(f"%{query}%"), User.email.ilike(f"%{query}%"))
    ).limit(10).all()
    logs = Log.query.filter(Log.message.ilike(f"%{query}%")).limit(10).all()
    
    return render_template("dashboard/search_results.html", query=query, articles=articles, users=users, logs=logs)


@dashboard_bp.route("/subscribers")
@login_required
@admin_required
def subscribers():
    users = User.query.filter_by(role="client").all()
    return render_template("dashboard/subscribers.html", users=users)


@dashboard_bp.route("/revenue")
@login_required
@admin_required
def revenue():
    metrics = get_revenue_metrics()
    transactions = Transaction.query.order_by(Transaction.created_at.desc()).limit(100).all()
    return render_template("dashboard/revenue.html", metrics=metrics, transactions=transactions)


@dashboard_bp.route("/pricing", methods=["GET", "POST"])
@login_required
@admin_required
def pricing():
    if request.method == "POST":
        # Handle add/edit/delete tier logic
        action = request.form.get("action")
        if action == "add_tier":
            name = request.form.get("name", "").strip()
            price = request.form.get("price", 0)
            interval = request.form.get("interval", "lifetime")
            if name and price:
                tier = PricingTier(name=name, price=float(price), interval=interval)
                db.session.add(tier)
                db.session.commit()
                flash(f"Tier '{name}' created.", "success")
        elif action == "delete_tier":
            tier_id = request.form.get("tier_id")
            tier = PricingTier.query.get(tier_id)
            if tier:
                db.session.delete(tier)
                db.session.commit()
                flash("Tier deleted.", "success")
        elif action == "toggle_tier":
            tier_id = request.form.get("tier_id")
            tier = PricingTier.query.get(tier_id)
            if tier:
                tier.is_active = not tier.is_active
                db.session.commit()
                flash("Tier visibility updated.", "success")
        return redirect(url_for("dashboard.pricing"))

    tiers = PricingTier.query.order_by(PricingTier.display_order).all()
    s = Setting.get_all_as_dict()
    return render_template("dashboard/pricing.html", s=s, tiers=tiers)


@dashboard_bp.route("/subscribers/cancellations")
@login_required
@admin_required
def subscriber_cancellations():
    from models import Subscription
    cancelled_subs = Subscription.query.filter_by(status="cancelled").all()
    return render_template("dashboard/subscribers_cancellations.html", subs=cancelled_subs)


@dashboard_bp.route("/pricing/settings", methods=["GET", "POST"])
@login_required
@admin_required
def pricing_settings():
    if request.method == "POST":
        for key, value in request.form.items():
            Setting.set(key, value)
        flash("Pricing settings updated.", "success")
        return redirect(url_for("dashboard.pricing_settings"))
    
    # Ensure some default billing settings exist
    if not Setting.get("currency"):
        Setting.set("currency", "USD")
    if not Setting.get("billing_provider"):
        Setting.set("billing_provider", "paypal")
        
    s = Setting.get_all_as_dict()
    return render_template("dashboard/pricing_settings.html", s=s)


@dashboard_bp.route("/pricing/features", methods=["GET", "POST"])
@login_required
@admin_required
def pricing_features():
    if request.method == "POST":
        tier_id = request.form.get("tier_id")
        feature_text = request.form.get("feature_text")
        if tier_id and feature_text:
            new_feature = PricingFeature(tier_id=tier_id, feature_text=feature_text)
            db.session.add(new_feature)
            db.session.commit()
            flash("Feature added.", "success")
        return redirect(url_for("dashboard.pricing_features"))
    
    tiers = PricingTier.query.all()
    return render_template("dashboard/pricing_features.html", tiers=tiers)


@dashboard_bp.route("/pricing/discounts", methods=["GET", "POST"])
@login_required
@admin_required
def pricing_discounts():
    from datetime import datetime, timezone
    if request.method == "POST":
        code = request.form.get("code")
        discount = request.form.get("discount_percent")
        expires_at_str = request.form.get("expires_at", "").strip()
        if code and discount:
            expires_at = None
            if expires_at_str:
                try:
                    expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d")
                except ValueError:
                    expires_at = None
            # Check for duplicate
            if Coupon.query.filter_by(code=code.upper()).first():
                flash(f"Coupon '{code.upper()}' already exists.", "error")
            else:
                new_coupon = Coupon(code=code.upper(), discount_percent=int(discount), expires_at=expires_at)
                db.session.add(new_coupon)
                db.session.commit()
                flash(f"Coupon {code.upper()} created.", "success")
        elif request.form.get("delete_id"):
            coupon = Coupon.query.get(request.form.get("delete_id"))
            if coupon:
                db.session.delete(coupon)
                db.session.commit()
                flash("Coupon deleted.", "success")
        elif request.form.get("toggle_id"):
            coupon = Coupon.query.get(request.form.get("toggle_id"))
            if coupon:
                coupon.is_active = not coupon.is_active
                db.session.commit()
                flash("Coupon status updated.", "success")
        return redirect(url_for("dashboard.pricing_discounts"))

    now = datetime.utcnow()
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    # Auto-mark expired coupons as inactive and normalize tz for template
    for c in coupons:
        if c.expires_at:
            c.expires_at = c.expires_at.replace(tzinfo=None)
            if c.expires_at < now and c.is_active:
                c.is_active = False
    db.session.commit()
    return render_template("dashboard/discounts.html", coupons=coupons, now=now)


@dashboard_bp.route("/pricing/adjustments")
@login_required
@admin_required
def pricing_adjustments():
    return render_template("dashboard/adjustments.html")


@dashboard_bp.route("/user/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def toggle_user_active(user_id):
    user = db.get_or_404(User, user_id)
    user.is_active = not user.is_active
    db.session.commit()
    return jsonify({"success": True, "is_active": user.is_active})


@dashboard_bp.route("/announcements", methods=["GET", "POST"])
@login_required
@admin_required
def announcements():
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        link_text = request.form.get("link_text")
        link_url = request.form.get("link_url")
        target = request.form.get("target", "public")
        
        announcement = Announcement(
            title=title, 
            content=content, 
            link_text=link_text, 
            link_url=link_url,
            target=target
        )
        db.session.add(announcement)
        db.session.commit()
        flash("Announcement published successfully.", "success")
        return redirect(url_for("dashboard.announcements"))
        
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template("dashboard/announcements.html", announcements=announcements)


@dashboard_bp.route("/announcement/<int:id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_announcement(id):
    announcement = db.get_or_404(Announcement, id)
    announcement.is_active = not announcement.is_active
    db.session.commit()
    return jsonify({"success": True, "is_active": announcement.is_active})


@dashboard_bp.route("/notify-user", methods=["POST"])
@login_required
@admin_required
def notify_user_route():
    user_id = request.form.get("user_id")
    message = request.form.get("message")
    
    if not user_id or not message:
        return jsonify({"success": False, "error": "Missing user_id or message"}), 400
        
    notification = Notification(user_id=user_id, message=message)
    db.session.add(notification)
    db.session.commit()
    return jsonify({"success": True})
@dashboard_bp.route("/feedback")
@login_required
@admin_required
def feedback():
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()
    return render_template("dashboard/feedback.html", feedbacks=feedbacks)


@dashboard_bp.route("/feedback/<int:id>/status", methods=["POST"])
@login_required
@admin_required
def update_feedback_status(id):
    fb = db.get_or_404(Feedback, id)
    status = request.form.get("status")
    if status in ["pending", "reviewed", "resolved"]:
        fb.status = status
        db.session.commit()
        return jsonify({"success": True, "status": fb.status})
    return jsonify({"success": False, "error": "Invalid status"}), 400
