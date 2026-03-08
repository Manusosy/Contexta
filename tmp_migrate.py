"""Standalone SQLite migration - adds new columns directly."""
import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), 'contexta.db')
con = sqlite3.connect(db_path)
cur = con.cursor()

migrations = [
    ("pricing_tiers", "article_limit", "INTEGER DEFAULT 20"),
    ("pricing_tiers", "feed_limit",    "INTEGER DEFAULT 1"),
    ("subscriptions", "pricing_tier_id",          "INTEGER"),
    ("subscriptions", "preferred_payment_method",  "VARCHAR(50)"),
    ("subscriptions", "auto_renew",                "BOOLEAN DEFAULT 0"),
    ("users",         "created_at",                "DATETIME DEFAULT CURRENT_TIMESTAMP"),
]

for table, col, col_def in migrations:
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        print(f"  Added {table}.{col}")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print(f"  Skip {table}.{col} (exists)")
        else:
            print(f"  ERROR {table}.{col}: {e}")

# Replace existing tiers with 3 correct ones
cur.execute("DELETE FROM pricing_features")
cur.execute("DELETE FROM pricing_tiers")

tiers = [
    (1, "Starter", 3.50, "USD", "monthly", 20, 1, 1, 1),
    (2, "Growth",  9.00, "USD", "monthly", 100, 5, 1, 2),
    (3, "Pro",    19.00, "USD", "monthly", -1, -1, 1, 3),
]
cur.executemany(
    "INSERT INTO pricing_tiers (id, name, price, currency, interval, article_limit, feed_limit, is_active, display_order) VALUES (?,?,?,?,?,?,?,?,?)",
    tiers
)

features = [
    # Starter - tier_id=1
    (1, "1 RSS feed source",                    0),
    (1, "20 AI-generated articles per month",   1),
    (1, "SEO optimization included",            2),
    (1, "Email support",                        3),
    # Growth - tier_id=2
    (2, "5 RSS feed sources",                   0),
    (2, "100 AI-generated articles per month",  1),
    (2, "Advanced SEO + meta optimization",     2),
    (2, "WordPress auto-publish",               3),
    (2, "Priority support",                     4),
    # Pro - tier_id=3
    (3, "Unlimited RSS feed sources",           0),
    (3, "Unlimited AI-generated articles",      1),
    (3, "Full SEO + JSON-LD schema",            2),
    (3, "WordPress auto-publish",               3),
    (3, "Custom AI writing style",              4),
    (3, "Dedicated account manager",            5),
]
cur.executemany(
    "INSERT INTO pricing_features (tier_id, feature_text, display_order, is_included) VALUES (?,?,?,1)",
    features
)

con.commit()
con.close()
print("\nDone! Seeded 3 pricing tiers: Starter $3.50, Growth $9, Pro $19/mo")
