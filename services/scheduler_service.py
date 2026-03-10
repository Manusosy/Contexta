"""Scheduler service for background jobs."""
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from models import Setting
from services.automation_service import run_node_1_rss_fetcher, run_node_2_worker, cleanup_stale_locks
from config import get_config

config = get_config()

# Single background scheduler instance
scheduler = BackgroundScheduler()

def init_scheduler(app):
    """Initialize the scheduler on startup, reading from Settings."""
    if not scheduler.running:
        scheduler.start()
        # Ensure scheduler shuts down when the app exits
        atexit.register(lambda: scheduler.shutdown(wait=False))

    with app.app_context():
        # Global toggle for automation
        enabled = Setting.get("schedule_enabled", "false") == "true"

        if enabled:
            start_schedule(app)

def _rss_job(app):
    with app.app_context():
        run_node_1_rss_fetcher()

def _worker_job(app):
    with app.app_context():
        # Cleanup stale locks before running worker
        cleanup_stale_locks()
        run_node_2_worker()

def start_schedule(app):
    """Start or reschedule the automation jobs for Nodes 1 and 2."""
    stop_schedule()
    
    # Node 1: RSS Fetcher (Every 30 mins by default)
    rss_interval = getattr(config, "RSS_POLL_INTERVAL_MIN", 30)
    scheduler.add_job(
        func=_rss_job,
        args=[app],
        trigger="interval",
        minutes=rss_interval,
        id="node_1_rss_fetcher",
        replace_existing=True
    )
    
    # Node 2: Queue Worker (Every 60s by default)
    worker_interval = getattr(config, "WORKER_SLEEP_SECONDS", 60)
    scheduler.add_job(
        func=_worker_job,
        args=[app],
        trigger="interval",
        seconds=worker_interval,
        id="node_2_queue_worker",
        replace_existing=True
    )
    
    print(f"[Scheduler] Node 1 (RSS) every {rss_interval}m, Node 2 (Worker) every {worker_interval}s.")

def stop_schedule():
    """Stop all automation jobs."""
    if scheduler.get_job("node_1_rss_fetcher"):
        scheduler.remove_job("node_1_rss_fetcher")
    if scheduler.get_job("node_2_queue_worker"):
        scheduler.remove_job("node_2_queue_worker")
    print("[Scheduler] All automation jobs stopped.")
