"""Article management routes."""
import csv
import io
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from models import db, Article
from services.wordpress_service import push_to_wordpress
from services.seo_service import process_article as seo_process

articles_bp = Blueprint("articles", __name__)


@articles_bp.before_request
@login_required
def require_admin():
    """All article management routes require admin access."""
    if current_user.role != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("dashboard.index"))


@articles_bp.route("/")
@login_required
def index():
    status_filter = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Article.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if q:
        query = query.filter(
            db.or_(
                Article.generated_title.ilike(f"%{q}%"),
                Article.original_title.ilike(f"%{q}%"),
            )
        )
    pagination = query.order_by(Article.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    articles = pagination.items
    return render_template("articles/index.html", articles=articles, pagination=pagination,
                           current_status=status_filter, q=q)


def _get_export_query():
    status_filter = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    query = Article.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if q:
        query = query.filter(
            db.or_(
                Article.generated_title.ilike(f"%{q}%"),
                Article.original_title.ilike(f"%{q}%"),
            )
        )
    return query.order_by(Article.created_at.desc()).all()


@articles_bp.route("/export.csv")
@login_required
def export_csv():
    articles = _get_export_query()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Generated Title', 'Original Title', 'Source URL', 'Status', 'SEO Score', 'Word Count', 'Primary Keyword', 'Date'])
    
    for a in articles:
        writer.writerow([
            a.id,
            a.generated_title,
            a.original_title,
            a.source_url,
            a.status,
            a.seo_score,
            a.word_count,
            a.primary_keyword,
            a.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ])
        
    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=articles_export.csv"
    return response


@articles_bp.route("/export.json")
@login_required
def export_json():
    articles = _get_export_query()
    
    data = []
    for a in articles:
        data.append({
            "id": a.id,
            "generated_title": a.generated_title,
            "original_title": a.original_title,
            "source_url": a.source_url,
            "status": a.status,
            "seo_score": a.seo_score,
            "word_count": a.word_count,
            "primary_keyword": a.primary_keyword,
            "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
        
    response = Response(json.dumps(data, indent=2), mimetype="application/json")
    response.headers["Content-Disposition"] = "attachment; filename=articles_export.json"
    return response


@articles_bp.route("/<int:article_id>")
@login_required
def view(article_id):
    article = db.get_or_404(Article, article_id)
    return render_template("articles/view.html", article=article)


@articles_bp.route("/<int:article_id>/save", methods=["POST"])
@login_required
def save(article_id):
    article = db.get_or_404(Article, article_id)
    article.generated_title = request.form.get("generated_title", article.generated_title).strip()
    article.content = request.form.get("content", article.content)
    article.meta_description = request.form.get("meta_description", article.meta_description or "").strip()
    article.slug = request.form.get("slug", article.slug or "").strip()

    # Re-run SEO score on saved content
    if article.content:
        seo_data = seo_process(article.content, article.generated_title or "")
        article.seo_score = seo_data["seo_score"]
        if not article.primary_keyword:
            article.primary_keyword = seo_data["primary_keyword"]

    db.session.commit()
    flash("Article saved successfully.", "success")
    return redirect(url_for("articles.view", article_id=article_id))


@articles_bp.route("/<int:article_id>/push", methods=["POST"])
@login_required
def push(article_id):
    article = db.get_or_404(Article, article_id)
    result = push_to_wordpress(article)

    if result.get("success"):
        article.wordpress_id = result["wp_id"]
        article.status = "pushed"
        db.session.commit()
        flash(f"Article pushed to WordPress (ID: {result['wp_id']}).", "success")
    else:
        flash(f"WordPress push failed: {result.get('error', 'Unknown error')}", "error")

    return redirect(url_for("articles.view", article_id=article_id))


@articles_bp.route("/<int:article_id>/delete", methods=["POST"])
@login_required
def delete(article_id):
    article = db.get_or_404(Article, article_id)
    db.session.delete(article)
    db.session.commit()
    flash("Article deleted.", "success")
    return redirect(url_for("articles.index"))


@articles_bp.route("/<int:article_id>/retry", methods=["POST"])
@login_required
def retry(article_id):
    """Reset a failed article back to pending for re-processing."""
    article = db.get_or_404(Article, article_id)
    article.status = "pending"
    article.content = None
    article.generated_title = None
    article.meta_description = None
    article.slug = None
    article.seo_score = 0
    article.word_count = 0
    article.wordpress_id = None
    db.session.commit()
    flash("Article queued for retry.", "success")
    return redirect(url_for("articles.view", article_id=article_id))
