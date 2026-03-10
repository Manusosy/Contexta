import sqlite3, os
db_path = os.path.join(os.path.dirname(__file__), 'contexta.db')
con = sqlite3.connect(db_path)
cur = con.cursor()
cur.execute("PRAGMA table_info(users)")
cols = [c[1] for c in cur.fetchall()]
required = [
    "billing_company", "billing_address", "billing_city", 
    "billing_country", "billing_zip", "billing_tax_id"
]
missing = [r for r in required if r not in cols]
if not missing:
    print("ALL_COLUMNS_PRESENT")
else:
    print(f"MISSING_COLUMNS: {missing}")
con.close()
