"""
Bootstrap: Worker Registry
Celery workers, background tasks, and scheduled jobs initialization.
"""
import logging

logger = logging.getLogger(__name__)


def init_workers() -> None:
    """Initialize Celery workers and background schedulers.

    This is called during app startup. It does NOT block –
    it simply ensures Celery configuration is loaded and
    beat schedules are registered.
    """
    try:
        from celery_app import celery_app
        logger.info(f"Celery app configured: broker={celery_app.conf.broker_url}")
    except ImportError:
        logger.warning("celery_app not importable – workers disabled")

    # Ensure tasks module is imported so Celery discovers tasks
    try:
        import celery_tasks  # noqa: F401
        logger.info("Celery tasks registered")
    except ImportError:
        logger.warning("celery_tasks not importable")
