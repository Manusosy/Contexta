import sqlite3, os

def run_fix():
    db_path = os.path.join(os.getcwd(), 'contexta.db')
    print(f"Opening DB: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    tables = ["users", "pricing_tiers", "subscriptions"]
    
    for table in tables:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [c[1] for c in cur.fetchall()]
        print(f"Table {table} columns: {cols}")
        
        if table == "users" and "created_at" not in cols:
            print("Adding users.created_at...")
            # Use simple ADD COLUMN without dynamic default to avoid SQLite limitations
            cur.execute("ALTER TABLE users ADD COLUMN created_at DATETIME")
            cur.execute("UPDATE users SET created_at = CURRENT_TIMESTAMP")
        
        if table == "pricing_tiers":
            if "article_limit" not in cols:
                print("Adding pricing_tiers.article_limit...")
                cur.execute("ALTER TABLE pricing_tiers ADD COLUMN article_limit INTEGER DEFAULT 20")
            if "feed_limit" not in cols:
                print("Adding pricing_tiers.feed_limit...")
                cur.execute("ALTER TABLE pricing_tiers ADD COLUMN feed_limit INTEGER DEFAULT 1")
                
        if table == "subscriptions":
            if "pricing_tier_id" not in cols:
                print("Adding subscriptions.pricing_tier_id...")
                cur.execute("ALTER TABLE subscriptions ADD COLUMN pricing_tier_id INTEGER")
            if "preferred_payment_method" not in cols:
                print("Adding subscriptions.preferred_payment_method...")
                cur.execute("ALTER TABLE subscriptions ADD COLUMN preferred_payment_method VARCHAR(50)")
            if "auto_renew" not in cols:
                print("Adding subscriptions.auto_renew...")
                cur.execute("ALTER TABLE subscriptions ADD COLUMN auto_renew BOOLEAN DEFAULT 0")

        if table == "pricing_tiers":
            if "is_featured" not in cols:
                print("Adding pricing_tiers.is_featured...")
                cur.execute("ALTER TABLE pricing_tiers ADD COLUMN is_featured BOOLEAN DEFAULT 0")
            if "has_free_trial" not in cols:
                print("Adding pricing_tiers.has_free_trial...")
                cur.execute("ALTER TABLE pricing_tiers ADD COLUMN has_free_trial BOOLEAN DEFAULT 0")

    # Seed Tiers
    print("Seeding Pricing Tiers...")
    # Clear existing to ensure clean slate for refined tiers
    cur.execute("DELETE FROM pricing_features")
    cur.execute("DELETE FROM pricing_tiers")
    
    tiers = [
        # Starter
        ("Starter", 3.50, "USD", "monthly", 20, 1, 0, 1, 1, [
            "2 Articles Free Trial",
            "1 Active RSS Feed",
            "Automation Heartbeat",
            "WP Integration",
            "Standard Support"
        ]),
        ("Starter Annual", 35.0, "USD", "yearly", 20, 1, 0, 0, 2, [
            "20 Articles / Mo",
            "1 Active RSS Feed",
            "2 Months Free",
            "WP Integration",
            "Standard Support"
        ]),
        # Growth
        ("Growth", 9.50, "USD", "monthly", 100, 5, 1, 0, 3, [
            "100 Articles / Mo",
            "5 Active RSS Feeds",
            "Priority Processing",
            "SEO Optimization",
            "Premium Support"
        ]),
        ("Growth Annual", 95.0, "USD", "yearly", 100, 5, 0, 0, 4, [
            "100 Articles / Mo",
            "5 Active RSS Feeds",
            "SEO Optimization",
            "2 Months Free",
            "Priority Support"
        ]),
        # Pro
        ("Pro", 19.0, "USD", "monthly", -1, -1, 0, 0, 5, [
            "Unlimited Articles",
            "Unlimited RSS Feeds",
            "White-label Branding",
            "Custom Logic",
            "24/7 VIP Support"
        ]),
        ("Pro Annual", 190.0, "USD", "yearly", -1, -1, 0, 0, 6, [
            "Unlimited Articles",
            "Unlimited RSS Feeds",
            "White-label Branding",
            "Custom Logic",
            "24/7 VIP Support"
        ])
    ]

    for name, price, curr, interval, art_lim, feed_lim, feat, trial, order, features in tiers:
        cur.execute("""
            INSERT INTO pricing_tiers (name, price, currency, interval, article_limit, feed_limit, is_featured, has_free_trial, display_order, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (name, price, curr, interval, art_lim, feed_lim, feat, trial, order))
        tier_id = cur.lastrowid
        for f_text in features:
            cur.execute("INSERT INTO pricing_features (tier_id, feature_text) VALUES (?, ?)", (tier_id, f_text))

    conn.commit()
    
    # Verification
    print("\nVerification:")
    for table in tables:
        cur.execute(f"SELECT * FROM {table} LIMIT 1")
        col_names = [description[0] for description in cur.description]
        print(f"Table {table} verified columns: {col_names}")
    
    conn.close()
    print("\nDone.")

if __name__ == "__main__":
    run_fix()
