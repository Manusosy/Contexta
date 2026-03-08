"""Feed management routes."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Feed, Article

feeds_bp = Blueprint("feeds", __name__)


@feeds_bp.before_request
@login_required
def require_admin():
    """All feed management routes require admin access."""
    if current_user.role != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("dashboard.index"))


@feeds_bp.route("/")
@login_required
def index():
    feeds = Feed.query.order_by(Feed.created_at.desc()).all()
    # 3.4 Feed Article Count
    counts = dict(db.session.query(Article.feed_id, db.func.count(Article.id)).group_by(Article.feed_id).all())
    
    return render_template("feeds/index.html", feeds=feeds, counts=counts)


@feeds_bp.route("/add", methods=["POST"])
@login_required
def add():
    name = request.form.get("name", "").strip()
    feed_url = request.form.get("url", "").strip()
    category = request.form.get("category", "General").strip()
    active = request.form.get("active") == "on"

    if not name or not feed_url:
        flash("Feed name and URL are required.", "error")
        return redirect(url_for("feeds.index"))

    # Duplicate check
    existing = Feed.query.filter_by(url=feed_url).first()
    if existing:
        flash("A feed with this URL already exists.", "error")
        return redirect(url_for("feeds.index"))

    feed = Feed(name=name, url=feed_url, category=category, active=active)
    db.session.add(feed)
    db.session.commit()
    flash(f"Feed '{name}' added successfully.", "success")
    return redirect(url_for("feeds.index"))


@feeds_bp.route("/<int:feed_id>/edit", methods=["POST"])
@login_required
def edit(feed_id):
    feed = db.get_or_404(Feed, feed_id)
    feed.name = request.form.get("name", feed.name).strip()
    feed.category = request.form.get("category", feed.category).strip()
    feed.active = request.form.get("active") == "on"

    new_url = request.form.get("url", "").strip()
    if new_url and new_url != feed.url:
        duplicate = Feed.query.filter_by(url=new_url).first()
        if duplicate:
            flash("Another feed with this URL already exists.", "error")
            return redirect(url_for("feeds.index"))
        feed.url = new_url

    db.session.commit()
    flash(f"Feed '{feed.name}' updated.", "success")
    return redirect(url_for("feeds.index"))


@feeds_bp.route("/<int:feed_id>/delete", methods=["POST"])
@login_required
def delete(feed_id):
    feed = db.get_or_404(Feed, feed_id)
    name = feed.name
    db.session.delete(feed)
    db.session.commit()
    flash(f"Feed '{name}' deleted.", "success")
    return redirect(url_for("feeds.index"))


@feeds_bp.route("/<int:feed_id>/toggle", methods=["POST"])
@login_required
def toggle(feed_id):
    feed = db.get_or_404(Feed, feed_id)
    feed.active = not feed.active
    db.session.commit()
    state = "activated" if feed.active else "deactivated"
    flash(f"Feed '{feed.name}' {state}.", "success")
    return redirect(url_for("feeds.index"))


@feeds_bp.route("/<int:feed_id>/refresh", methods=["POST"])
@login_required
def refresh(feed_id):
    """Manually fetch new articles for a single feed."""
    feed = db.get_or_404(Feed, feed_id)
    from services.rss_service import fetch_feed
    entries = fetch_feed(feed)
    flash(f"Refreshed '{feed.name}': {len(entries)} new articles queued.", "success")
    return redirect(url_for("feeds.index"))
