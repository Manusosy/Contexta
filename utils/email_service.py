import os
from flask_mail import Mail, Message
from utils.logger import log_event

mail = Mail()

def init_mail(app):
    """Initialize the Flask-Mail extension"""
    mail.init_app(app)

def send_email(subject, recipient, body_text):
    """Send a simple text email"""
    try:
        msg = Message(
            subject=subject,
            recipients=[recipient],
            body=body_text
        )
        mail.send(msg)
        return True
    except Exception as e:
        log_event("Email Delivery", "error", f"Failed to send email to {recipient}: {str(e)}")
        print(f"Error sending email: {e}")
        return False
