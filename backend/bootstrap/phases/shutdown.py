"""Graceful shutdown — closes connections and stops workers (mirrors original on_shutdown)."""
import logging

from core.database import client

logger = logging.getLogger(__name__)


async def shutdown_all(app):
    # Infrastructure cleanup
    try:
        from infra.horizontal_scaling import scaling_manager
        await scaling_manager.deregister()
        from infra.ws_redis_adapter import ws_redis_adapter
        await ws_redis_adapter.close()
        try:
            from infra.auth_cache_pubsub import auth_cache_pubsub
            await auth_cache_pubsub.close()
        except Exception as e:
            logger.warning(f"Auth cache pub/sub shutdown warning: {e}")
        try:
            from infra.kbs_queue_pubsub import kbs_queue_pubsub
            await kbs_queue_pubsub.close()
        except Exception as e:
            logger.warning(f"KBS queue pub/sub shutdown warning: {e}")
        from infra.redis_cluster import redis_cluster
        await redis_cluster.close()
    except Exception as e:
        logger.warning(f"Infrastructure shutdown warning: {e}")

    # Dashboard snapshot worker
    snapshot_worker = getattr(app.state, "dashboard_snapshot_worker", None)
    if snapshot_worker is not None:
        try:
            await snapshot_worker.stop()
        except Exception as e:
            logger.warning(f"Dashboard snapshot worker shutdown warning: {e}")

    # Room-Type Inventory worker
    inv_worker = getattr(app.state, "room_type_inventory_worker", None)
    if inv_worker is not None:
        try:
            await inv_worker.stop()
        except Exception as e:
            logger.warning(f"Room-type inventory worker shutdown warning: {e}")

    # Af-sadakat outbound dispatcher
    afs_task = getattr(app.state, "afsadakat_dispatcher_task", None)
    if afs_task is not None and not afs_task.done():
        try:
            afs_task.cancel()
            try:
                await afs_task
            except (Exception, BaseException):
                pass
        except Exception as e:
            logger.warning(f"Af-sadakat dispatcher shutdown warning: {e}")

    # OTA Outbox Worker
    ota_worker = getattr(app.state, "outbox_ota_worker", None)
    if ota_worker is not None:
        try:
            await ota_worker.stop()
        except Exception as e:
            logger.warning(f"OTA Outbox Worker shutdown warning: {e}")

    # Import Retry worker
    import_worker = getattr(app.state, "import_retry_worker", None)
    if import_worker is not None:
        try:
            await import_worker.stop()
        except Exception as e:
            logger.warning(f"Import Retry Worker shutdown warning: {e}")

    # Outbox lifecycle worker
    worker = getattr(app.state, "outbox_lifecycle_worker", None)
    if worker is not None:
        try:
            await worker.stop()
        except Exception as e:
            logger.warning(f"Outbox lifecycle worker shutdown warning: {e}")

    # Monitoring worker
    try:
        from domains.channel_manager.monitoring.monitoring_worker import stop_monitoring_worker
        await stop_monitoring_worker()
    except Exception as e:
        logger.warning(f"Monitoring worker shutdown warning: {e}")

    # Cockpit snapshot worker
    try:
        from domains.channel_manager.cockpit_snapshot_worker import stop_cockpit_worker
        stop_cockpit_worker()
    except Exception as e:
        logger.warning(f"Cockpit snapshot worker shutdown warning: {e}")

    # Exely Pull Scheduler
    scheduler = getattr(app.state, "exely_pull_scheduler", None)
    if scheduler is not None:
        try:
            await scheduler.stop()
        except Exception as e:
            logger.warning(f"Exely Pull Scheduler shutdown warning: {e}")

    # HotelRunner Pull Scheduler
    hr_scheduler = getattr(app.state, "hr_pull_scheduler", None)
    if hr_scheduler is not None:
        try:
            await hr_scheduler.stop()
        except Exception as e:
            logger.warning(f"HotelRunner Pull Scheduler shutdown warning: {e}")

    # HotelRunner Push Queue Worker
    hr_push = getattr(app.state, "hr_push_queue_worker", None)
    if hr_push is not None:
        try:
            await hr_push.stop()
        except Exception as e:
            logger.warning(f"HotelRunner Push Queue Worker shutdown warning: {e}")

    # Night Audit Scheduler
    try:
        from domains.pms.night_audit.scheduler import stop_scheduler
        stop_scheduler()
    except Exception as e:
        logger.warning(f"Night Audit Scheduler shutdown warning: {e}")

    # Web Push cleanup worker
    try:
        from domains.guest.messaging.web_push_cleanup import (
            stop_web_push_cleanup_worker,
        )
        await stop_web_push_cleanup_worker()
    except Exception as e:
        logger.warning(f"Web Push cleanup worker shutdown warning: {e}")

    # Availability Reconciliation Worker
    recon_worker = getattr(app.state, "availability_reconciliation_worker", None)
    if recon_worker is not None:
        try:
            await recon_worker.stop()
        except Exception as e:
            logger.warning(f"Availability Reconciliation Worker shutdown warning: {e}")

    # Close MongoDB client
    client.close()
