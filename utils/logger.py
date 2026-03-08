from models import db, Log

def log_event(action: str, status: str = "info", message: str = ""):
    """Centralized logging utility to record events in the database."""
    try:
        log = Log(action=action, status=status, message=message)
        db.session.add(log)
        db.session.commit()
    except Exception:
        # Failsafe: if logging fails (e.g., db is locked), ignore it
        db.session.rollback()
