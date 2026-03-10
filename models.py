from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Feed(db.Model):
    """RSS Feed source."""
    __tablename__ = "feeds"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True) # None means global admin feed
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True) # Pipeline bio/summary
    url = db.Column(db.String(500), unique=True, nullable=False)
    category = db.Column(db.String(100), default="Tech News")
    fetch_interval = db.Column(db.Integer, default=60) # Minutes
    rewrite_profile = db.Column(db.String(100), default="Default") # AI Profile
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, onupdate=lambda: datetime.now(timezone.utc))

    articles = db.relationship("Article", backref="feed", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Feed {self.name}>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "category": self.category,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }


class Article(db.Model):
    """Generated article from RSS source."""
    __tablename__ = "articles"

    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.Integer, db.ForeignKey("feeds.id"), nullable=True)
    source_url = db.Column(db.String(1000), nullable=False)
    original_title = db.Column(db.String(500))
    generated_title = db.Column(db.String(500))
    content = db.Column(db.Text)
    meta_description = db.Column(db.String(300))
    slug = db.Column(db.String(300))
    primary_keyword = db.Column(db.String(200))
    seo_score = db.Column(db.Integer, default=0)
    # Status: pending | processing | extracting | rewriting | publishing | published | failed | skipped | permanently_failed
    status = db.Column(db.String(50), default="pending")
    wordpress_id = db.Column(db.Integer, nullable=True)
    word_count = db.Column(db.Integer, default=0)
    retry_count = db.Column(db.Integer, default=0)
    locked_at = db.Column(db.DateTime, nullable=True)
    extracted_body = db.Column(db.Text, nullable=True)
    source_tags = db.Column(db.String(500), nullable=True)
    original_pub_date = db.Column(db.DateTime, nullable=True)
    author = db.Column(db.String(200), nullable=True)
    guid = db.Column(db.String(500), nullable=True)
    main_image_url = db.Column(db.String(500), nullable=True)
    error_log = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Article {self.original_title}>"

    def to_dict(self):
        return {
            "id": self.id,
            "feed_id": self.feed_id,
            "source_url": self.source_url,
            "original_title": self.original_title,
            "generated_title": self.generated_title,
            "seo_score": self.seo_score,
            "status": self.status,
            "wordpress_id": self.wordpress_id,
            "created_at": self.created_at.isoformat(),
        }


class Subscription(db.Model):
    """User subscription details."""
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    pricing_tier_id = db.Column(db.Integer, db.ForeignKey("pricing_tiers.id"), nullable=True)
    plan_name = db.Column(db.String(100), default="Free")
    status = db.Column(db.String(50), default="inactive") # active, cancelled, expired
    payment_method = db.Column(db.String(50)) # paypal, mpesa
    preferred_payment_method = db.Column(db.String(50))  # saved preference
    payment_details = db.Column(db.String(255)) # e.g. phone number, masked email
    auto_renew = db.Column(db.Boolean, default=False)
    gateway_ref_id = db.Column(db.String(200)) # paypal_sub_id or mpesa_checkout_id
    current_period_end = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tier = db.relationship("PricingTier", foreign_keys=[pricing_tier_id], lazy=True)


class Transaction(db.Model):
    """Payment history."""
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD")
    provider = db.Column(db.String(50)) # paypal, mpesa
    status = db.Column(db.String(50), default="completed") # completed, failed, pending
    external_id = db.Column(db.String(200)) # external reference
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Coupon(db.Model):
    """Discount coupon code logic."""
    __tablename__ = "coupons"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_percent = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=True)


class PricingTier(db.Model):
    """Product pricing tiers."""
    __tablename__ = "pricing_tiers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD")
    interval = db.Column(db.String(20), default="monthly") # monthly, yearly, lifetime
    article_limit = db.Column(db.Integer, default=20)  # -1 = unlimited
    feed_limit = db.Column(db.Integer, default=1)       # -1 = unlimited
    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)  # "Most Popular"
    has_free_trial = db.Column(db.Boolean, default=False)
    display_order = db.Column(db.Integer, default=0)

    features = db.relationship("PricingFeature", backref="tier", lazy=True, cascade="all, delete-orphan")


class PricingFeature(db.Model):
    """Features listed under a pricing tier."""
    __tablename__ = "pricing_features"

    id = db.Column(db.Integer, primary_key=True)
    tier_id = db.Column(db.Integer, db.ForeignKey("pricing_tiers.id"), nullable=False)
    feature_text = db.Column(db.String(255), nullable=False)
    is_included = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)


class Setting(db.Model):
    """Key-value settings store (singleton per key)."""
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default="")

    @classmethod
    def get(cls, key, default=""):
        """Get a setting value by key."""
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        """Set a setting value, insert or update."""
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))
        db.session.commit()

    @classmethod
    def get_all_as_dict(cls):
        """Return all settings as a plain dict."""
        return {row.key: row.value for row in cls.query.all()}

    def __repr__(self):
        return f"<Setting {self.key}={self.value[:30]}>"


class Log(db.Model):
    """Automation activity log."""
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True) # None = Admin/Global
    action = db.Column(db.String(200), nullable=False)
    # Status: info | success | error | warning
    status = db.Column(db.String(50), default="info")
    message = db.Column(db.Text, default="")
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("logs", lazy=True))

    def __repr__(self):
        return f"<Log [{self.status}] {self.action}>"

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


class Announcement(db.Model):
    """Site-wide announcements for public or client users."""
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    link_text = db.Column(db.String(100))
    link_url = db.Column(db.String(500))
    # target: public | client | both
    target = db.Column(db.String(50), default="public")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Announcement {self.title}>"


class Notification(db.Model):
    """Direct notifications for specific users."""
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Notification for User {self.user_id}>"


class Feedback(db.Model):
    """User feedback submitted to the platform admin."""
    __tablename__ = "feedbacks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    # Status: pending | reviewed | resolved
    status = db.Column(db.String(50), default="pending")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref=db.backref("feedbacks", lazy=True))

    def __repr__(self):
        return f"<Feedback from User {self.user_id}>"


class User(UserMixin, db.Model):
    """Application user — supports admin and client roles."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    onboarding_completed = db.Column(db.Boolean, default=False)
    heard_from = db.Column(db.String(200), nullable=True)
    role = db.Column(db.String(50), default="client") # admin, client
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # WordPress Settings (Per User)
    wp_url = db.Column(db.String(500))
    wp_user = db.Column(db.String(100))
    wp_password = db.Column(db.String(200))
    wp_default_category = db.Column(db.Integer)

    # Billing Profile
    billing_company = db.Column(db.String(200))
    billing_address = db.Column(db.String(500))
    billing_city = db.Column(db.String(100))
    billing_country = db.Column(db.String(100))
    billing_zip = db.Column(db.String(20))
    billing_tax_id = db.Column(db.String(100))

    feeds = db.relationship("Feed", backref="user", lazy=True, cascade="all, delete-orphan")
    subscriptions = db.relationship("Subscription", backref="user", lazy=True, cascade="all, delete-orphan")
    transactions = db.relationship("Transaction", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"
