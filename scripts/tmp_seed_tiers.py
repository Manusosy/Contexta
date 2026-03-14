"""
Seed proper pricing tiers into the DB.
Adds new columns to existing tables and replaces the incorrect "Enterprise Core" tier.

Run with:  python tmp_seed_tiers.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db, PricingTier, PricingFeature
import sqlite3

def add_missing_columns():
    """Add new columns to existing SQLite tables if they don't already exist."""
    db_path = os.path.join(os.path.dirname(__file__), 'contexta.db')
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    migrations = [
        # PricingTier
        ("pricing_tiers", "article_limit", "INTEGER DEFAULT 20"),
        ("pricing_tiers", "feed_limit",    "INTEGER DEFAULT 1"),
        # Subscription
        ("subscriptions", "pricing_tier_id",         "INTEGER REFERENCES pricing_tiers(id)"),
        ("subscriptions", "preferred_payment_method", "VARCHAR(50)"),
        ("subscriptions", "auto_renew",               "BOOLEAN DEFAULT 0"),
        # User
        ("users", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
    ]

    for table, col, col_def in migrations:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            print(f"  ✓ Added {table}.{col}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"  – {table}.{col} already exists, skipping.")
            else:
                raise

    con.commit()
    con.close()


def seed_tiers():
    """Delete the old placeholder tier and seed the 3 real tiers."""
    with app.app_context():
        # Remove existing tiers (and their features via cascade)
        PricingTier.query.delete()
        db.session.commit()
        print("  ✓ Cleared old tiers.")

        tiers_data = [
            {
                "name": "Starter",
                "price": 3.50,
                "interval": "monthly",
                "article_limit": 20,
                "feed_limit": 1,
                "display_order": 1,
                "features": [
                    "1 RSS feed source",
                    "20 AI-generated articles per month",
                    "SEO optimization included",
                    "Email support",
                ],
            },
            {
                "name": "Growth",
                "price": 9.00,
                "interval": "monthly",
                "article_limit": 100,
                "feed_limit": 5,
                "display_order": 2,
                "features": [
                    "5 RSS feed sources",
                    "100 AI-generated articles per month",
                    "Advanced SEO + meta optimization",
                    "WordPress auto-publish",
                    "Priority support",
                ],
            },
            {
                "name": "Pro",
                "price": 19.00,
                "interval": "monthly",
                "article_limit": -1,  # unlimited
                "feed_limit": -1,     # unlimited
                "display_order": 3,
                "features": [
                    "Unlimited RSS feed sources",
                    "Unlimited AI-generated articles",
                    "Full SEO + JSON-LD schema",
                    "WordPress auto-publish",
                    "Custom AI writing style",
                    "Dedicated account manager",
                ],
            },
        ]

        for td in tiers_data:
            features = td.pop("features")
            tier = PricingTier(**td)
            db.session.add(tier)
            db.session.flush()  # get the id

            for i, text in enumerate(features):
                feat = PricingFeature(tier_id=tier.id, feature_text=text, display_order=i)
                db.session.add(feat)
            print(f"  ✓ Created tier: {tier.name} (${tier.price}/mo, {tier.article_limit} articles, {tier.feed_limit} feeds)")

        db.session.commit()
        print("\n✅ Pricing tiers seeded successfully!")


if __name__ == "__main__":
    print("\n[1/2] Applying DB column migrations...")
    add_missing_columns()
    print("\n[2/2] Seeding pricing tiers...")
    seed_tiers()
