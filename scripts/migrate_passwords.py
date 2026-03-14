import sys
import os

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from models import db, User, Setting

app = create_app()

def migrate_passwords():
    with app.app_context():
        # 1. Encrypt User WP Passwords
        users = User.query.filter(User._wp_password != None).all()
        for user in users:
            # The setter handles encryption if not already encrypted
            # But wait, how do we know if it's already encrypted?
            # Our decrypt_data returns the original if it fails.
            # So we can just try to re-set it.
            # But the setter will ALWAYS encrypt what we give it.
            # If we give it an already encrypted string, it will double-encrypt.
            
            # Better check in utils/security or here.
            from utils.security import decrypt_data
            secret = app.config.get("SECRET_KEY", "dev-secret")
            
            # If it's pure plain text, it's definitely not a valid Fernet token (usually starts with gAAAA)
            if user._wp_password and not user._wp_password.startswith("gAAAA"):
                print(f"Encrypting plain-text password for user {user.email}")
                user.wp_password = user._wp_password # Setter handles it
        
        # 2. Encrypt Global WP Password in Settings
        wp_pw = Setting.query.filter_by(key="wp_password").first()
        if wp_pw and wp_pw.value and not wp_pw.value.startswith("gAAAA"):
             print("Encrypting global WP password in settings")
             from utils.security import encrypt_data
             wp_pw.value = encrypt_data(wp_pw.value, app.config.get("SECRET_KEY", "dev-secret"))

        db.session.commit()
        print("Migration complete.")

if __name__ == "__main__":
    migrate_passwords()
