import sqlite3, os
db_path = os.path.join(os.path.dirname(__file__), 'contexta.db')
con = sqlite3.connect(db_path)
cur = con.cursor()
cur.execute("PRAGMA table_info(users)")
cols = [c[1] for c in cur.fetchall()]
print(f"Users columns: {cols}")
cur.execute("PRAGMA table_info(pricing_tiers)")
cols = [c[1] for c in cur.fetchall()]
print(f"PricingTier columns: {cols}")
cur.execute("PRAGMA table_info(subscriptions)")
cols = [c[1] for c in cur.fetchall()]
print(f"Subscription columns: {cols}")
con.close()
