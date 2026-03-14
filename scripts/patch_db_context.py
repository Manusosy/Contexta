import sqlite3
import os

db_path = r'c:\Users\ADMIN\Desktop\CONTEXTA\contexta\contexta.db'

def patch_db():
    if not os.path.exists(db_path):
        print("DB not found.")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN relevance_score INTEGER;")
        print("Added relevance_score")
    except Exception as e:
        print(f"Error (maybe already exists): {e}")
        
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN topic_category VARCHAR(100);")
        print("Added topic_category")
    except Exception as e:
        print(f"Error (maybe already exists): {e}")

    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN content_strategy VARCHAR(100);")
        print("Added content_strategy")
    except Exception as e:
        print(f"Error (maybe already exists): {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    patch_db()
