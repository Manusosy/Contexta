import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "contexta-dev-secret-change-in-prod")
    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True  # Ensure it protects all POSTs by default
    WTF_CSRF_TIME_LIMIT = None     # Disable expiration for now to rule it out
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = False
    TESTING = False

    # Database — SQLite by default; override via DATABASE_URL env var for MySQL/Postgres
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'contexta.db')}"
    )

    # Mail Settings
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "mail.kazinikazi.co.ke")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 465))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "False").lower() == "true"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "True").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "noreply@kazinikazi.co.ke")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "#@ConTexta+254#@")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@kazinikazi.co.ke")
    
    # Automation Specification
    RSS_BATCH_LIMIT = int(os.environ.get("RSS_BATCH_LIMIT", 5))
    RSS_POLL_INTERVAL_MIN = int(os.environ.get("RSS_POLL_INTERVAL_MIN", 30))
    
    WORKER_SLEEP_SECONDS = int(os.environ.get("WORKER_SLEEP_SECONDS", 60))
    WORKER_ARTICLE_DELAY = int(os.environ.get("WORKER_ARTICLE_DELAY", 5))
    MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
    
    MIN_WORD_COUNT = int(os.environ.get("MIN_WORD_COUNT", 200))
    TARGET_WORD_COUNT = int(os.environ.get("TARGET_WORD_COUNT", 800))
    
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_DEFAULT_MODEL = os.environ.get("OPENROUTER_DEFAULT_MODEL", "openai/gpt-4o-mini")
    AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", 4096))
    
    SITE_NICHE = os.environ.get("SITE_NICHE", "Technology / AI")
    TARGET_AUDIENCE = os.environ.get("TARGET_AUDIENCE", "tech-savvy professionals aged 25-45")
    TONE = os.environ.get("TONE", "authoritative but approachable")
    
    WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")
    WP_DEFAULT_STATUS = os.environ.get("WP_DEFAULT_STATUS", "draft")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}

def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return config_map.get(env, DevelopmentConfig)
