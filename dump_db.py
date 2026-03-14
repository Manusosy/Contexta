import sqlite3
import os

db_path = r'c:\Users\ADMIN\Desktop\CONTEXTA\contexta\contexta.db'

def dump_table(table_name):
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        print(f"--- {table_name} ---")
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error reading {table_name}: {e}")
    finally:
        conn.close()

dump_table('feedbacks')
dump_table('logs')
