from cryptography.fernet import Fernet
import base64
import hashlib
import os

def get_cipher(secret_key):
    """Derive a Fernet key from the application's SECRET_KEY."""
    # Ensure the key is 32 bytes and URL-safe base64 encoded
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key)

def encrypt_data(data, secret_key):
    """Encrypt a string using the provided secret key."""
    if not data:
        return None
    try:
        cipher = get_cipher(secret_key)
        # Fernet expects bytes
        return cipher.encrypt(data.encode()).decode()
    except Exception:
        return None

def decrypt_data(encrypted_data, secret_key):
    """Decrypt a string using the provided secret key. Returns original if not encrypted or decryption fails."""
    if not encrypted_data:
        return None
    try:
        cipher = get_cipher(secret_key)
        # Fernet expects bytes
        return cipher.decrypt(encrypted_data.encode()).decode()
    except Exception:
        # If decryption fails, it might be plain text (for existing records)
        # or encrypted with a different key.
        return encrypted_data
