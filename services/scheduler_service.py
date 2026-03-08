"""Scheduler service for background jobs."""
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from models import Setting
from services.automation_service import run_automation

# Single background scheduler instance
scheduler = BackgroundScheduler()

def init_scheduler(app):
    """Initialize the scheduler on startup, reading from Settings."""
    if not scheduler.running:
        scheduler.start()
        # Ensure scheduler shuts down when the app exits
        atexit.register(lambda: scheduler.shutdown(wait=False))

    with app.app_context():
        enabled = Setting.get("schedule_enabled", "false") == "true"
        frequency = int(Setting.get("schedule_frequency", "60"))

        if enabled:
            start_schedule(app, frequency)

def _job_wrapper(app):
    """Wrap the job to run inside a Flask app context."""
    with app.app_context():
        run_automation(auto_push=False)

def start_schedule(app, frequency_minutes: int):
    """Start or reschedule the automation job."""
    # Remove existing job if any
    stop_schedule()
    
    scheduler.add_job(
        func=_job_wrapper,
        args=[app],
        trigger="interval",
        minutes=frequency_minutes,
        id="automation_job",
        replace_existing=True
    )
    print(f"[Scheduler] Automation job scheduled every {frequency_minutes} minutes.")

def stop_schedule():
    """Stop the automation job if it exists."""
    if scheduler.get_job("automation_job"):
        scheduler.remove_job("automation_job")
        print("[Scheduler] Automation job stopped.")

