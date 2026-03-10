import sqlite3, os
db_path = os.path.join(os.path.dirname(__file__), 'contexta.db')
print(f"Checking DB: {db_path}")

try:
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Define desired schema additions
    schema_additions = {
        "users": [
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("billing_company", "VARCHAR(200)"),
            ("billing_address", "VARCHAR(500)"),
            ("billing_city", "VARCHAR(100)"),
            ("billing_country", "VARCHAR(100)"),
            ("billing_zip", "VARCHAR(20)"),
            ("billing_tax_id", "VARCHAR(100)")
        ],
        "pricing_tiers": [
            ("article_limit", "INTEGER DEFAULT 20"),
            ("feed_limit", "INTEGER DEFAULT 1")
        ],
        "subscriptions": [
            ("pricing_tier_id", "INTEGER REFERENCES pricing_tiers(id)"),
            ("preferred_payment_method", "VARCHAR(50)"),
            ("payment_details", "VARCHAR(255)"),
            ("auto_renew", "BOOLEAN DEFAULT 0")
        ]
    }

    for table, columns in schema_additions.items():
        cur.execute(f"PRAGMA table_info({table})")
        existing_cols = [c[1] for c in cur.fetchall()]
        print(f"Table {table} existing columns: {existing_cols}")

        for col_name, col_def in columns:
            if col_name not in existing_cols:
                try:
                    query = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
                    print(f"Running: {query}")
                    cur.execute(query)
                    print(f"  ✓ Added {col_name} to {table}")
                except Exception as e:
                    print(f"  ❌ Error adding {col_name} to {table}: {e}")
            else:
                print(f"  - Column {col_name} already exists in {table}")

    con.commit()
    con.close()
    print("Migration check complete.")

except Exception as e:
    print(f"Critical error: {e}")
