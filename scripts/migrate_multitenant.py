import sqlite3, os

def run_migration():
    db_path = os.path.join(os.getcwd(), 'contexta.db')
    print(f"Opening DB: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 1. Update users table
    cur.execute("PRAGMA table_info(users)")
    user_cols = [c[1] for c in cur.fetchall()]
    
    if "wp_url" not in user_cols:
        print("Adding wp_url to users...")
        cur.execute("ALTER TABLE users ADD COLUMN wp_url VARCHAR(500)")
    if "wp_user" not in user_cols:
        print("Adding wp_user to users...")
        cur.execute("ALTER TABLE users ADD COLUMN wp_user VARCHAR(100)")
    if "wp_password" not in user_cols:
        print("Adding wp_password to users...")
        cur.execute("ALTER TABLE users ADD COLUMN wp_password VARCHAR(200)")
    if "wp_default_category" not in user_cols:
        print("Adding wp_default_category to users...")
        cur.execute("ALTER TABLE users ADD COLUMN wp_default_category INTEGER")

    # 2. Update logs table
    cur.execute("PRAGMA table_info(logs)")
    log_cols = [c[1] for c in cur.fetchall()]
    
    if "user_id" not in log_cols:
        print("Adding user_id to logs...")
        cur.execute("ALTER TABLE logs ADD COLUMN user_id INTEGER REFERENCES users(id)")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    run_migration()
