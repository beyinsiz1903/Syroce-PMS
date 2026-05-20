"""
Celery Configuration for Background Jobs
Handles long-running tasks, periodic jobs, and async processing
"""

import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

# Redis as message broker
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'hotel_pms',
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3000,  # 50 minutes warning

    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,

    # Result backend
    result_expires=86400,  # 24 hours
    result_backend_transport_options={
        'master_name': 'mymaster'
    },

    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,

    # Beat schedule for periodic tasks
    beat_schedule={
        # Night audit - runs at 2 AM daily
        'night-audit': {
            'task': 'celery_tasks.night_audit_task',
            'schedule': crontab(hour=2, minute=0),
        },

        # Data archival - runs weekly on Sunday at 3 AM
        'archive-old-data': {
            'task': 'celery_tasks.archive_old_data_task',
            'schedule': crontab(day_of_week=0, hour=3, minute=0),
        },

        # Clean old notifications - runs daily at 4 AM
        'clean-notifications': {
            'task': 'celery_tasks.clean_old_notifications_task',
            'schedule': crontab(hour=4, minute=0),
        },

        # Generate daily reports - runs at 1 AM
        'generate-daily-reports': {
            'task': 'celery_tasks.generate_daily_reports_task',
            'schedule': crontab(hour=1, minute=0),
        },

        # Check maintenance SLA - runs every hour
        'check-maintenance-sla': {
            'task': 'celery_tasks.check_maintenance_sla_task',
            'schedule': crontab(minute=0),  # Every hour at :00
        },

        # Update occupancy forecast - runs every 6 hours
        'update-occupancy-forecast': {
            'task': 'celery_tasks.update_occupancy_forecast_task',
            'schedule': crontab(minute=0, hour='*/6'),  # 0, 6, 12, 18
        },

        # Process pending e-faturas - runs every 30 minutes
        'process-efaturas': {
            'task': 'celery_tasks.process_pending_efaturas_task',
            'schedule': crontab(minute='*/30'),
        },

        # Cache warming - runs every 10 minutes
        'warm-cache': {
            'task': 'celery_tasks.warm_cache_task',
            'schedule': crontab(minute='*/10'),
        },

        # Database health check - runs every 5 minutes
        'db-health-check': {
            'task': 'celery_tasks.database_health_check_task',
            'schedule': crontab(minute='*/5'),
        },

        # HRv2 Shadow Automation — 6 saatte bir snapshot
        'hrv2-shadow-snapshot': {
            'task': 'celery_tasks.hrv2_shadow_snapshot_task',
            'schedule': crontab(minute=0, hour='*/6'),
        },

        # HRv2 Shadow Automation — Gunluk ozet (00:00 UTC)
        'hrv2-daily-summary': {
            'task': 'celery_tasks.hrv2_daily_summary_task',
            'schedule': crontab(hour=0, minute=0),
        },

        # HRv2 Shadow Automation — Retention cleanup (Pazar 05:00 UTC)
        'hrv2-retention-cleanup': {
            'task': 'celery_tasks.hrv2_retention_cleanup_task',
            'schedule': crontab(day_of_week=0, hour=5, minute=0),
        },

        # F8N Task #224 — Auto-resolve duplicate room-night locks (daily 03:30 UTC).
        # Touches only auto_safe / auto_safe_all_inactive groups; manual_required
        # groups are logged so monitoring can alert if they accumulate.
        # Retention (Task #237): the `rnl_auto_resolve_runs` history collection
        # is pruned inline at the end of each run (default 365 days, overridable
        # via `RNL_AUTO_RESOLVE_RUN_RETENTION_DAYS`). No separate beat entry.
        'rnl-duplicate-auto-resolve': {
            'task': 'celery_tasks.rnl_duplicate_auto_resolve_task',
            'schedule': crontab(hour=3, minute=30),
        },

        # F8N Task #234 — Heartbeat monitor for the daily RNL duplicate
        # auto-resolve job. Alerts when no successful run has happened in
        # ~36h (silent dead-scheduler failure mode that the outcome-based
        # Task #228 alert can't see). Runs hourly at :15.
        'rnl-duplicate-heartbeat-check': {
            'task': 'celery_tasks.rnl_duplicate_heartbeat_check_task',
            'schedule': crontab(minute=15),
        },
    }
)

# Import tasks directly (celery_tasks is a module, not a package)
try:
    import celery_tasks  # noqa: F401
except ImportError as e:
    import logging
    logging.getLogger(__name__).warning(f"celery_tasks import failed: {e}")

if __name__ == '__main__':
    celery_app.start()
