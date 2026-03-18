"""
Night Audit — Background Scheduler
Runs as an asyncio background task during the FastAPI lifespan.
Checks every 60 seconds if any tenant's scheduled audit time has arrived.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_scheduler_task = None
_scheduler_running = False


async def _scheduler_loop():
    """Main scheduler loop — checks every 60s for due audit schedules."""
    global _scheduler_running
    _scheduler_running = True
    logger.info("Night Audit Scheduler started")

    from core.database import db
    from domains.pms.night_audit.service import night_audit_core_service

    while _scheduler_running:
        try:
            now_utc = datetime.now(timezone.utc)

            # Find all enabled schedules
            schedules = await db.night_audit_schedules.find(
                {"enabled": True}, {"_id": 0}
            ).to_list(500)

            for schedule in schedules:
                tenant_id = schedule.get("tenant_id")
                sched_hour = schedule.get("scheduled_hour", 0)
                sched_minute = schedule.get("scheduled_minute", 0)
                tz_name = schedule.get("timezone", "Europe/Istanbul")

                # Calculate the local time for this tenant
                local_now = _utc_to_local(now_utc, tz_name)
                local_hour = local_now.hour
                local_minute = local_now.minute

                # Check if it's time (within the same minute window)
                if local_hour == sched_hour and local_minute == sched_minute:
                    # Check if already ran today
                    last_auto_run = schedule.get("last_auto_run")
                    if last_auto_run:
                        last_run_dt = datetime.fromisoformat(last_auto_run.replace("Z", "+00:00"))
                        last_run_local = _utc_to_local(last_run_dt, tz_name)
                        if last_run_local.date() == local_now.date():
                            continue  # Already ran today

                    logger.info(
                        f"Triggering scheduled night audit for tenant {tenant_id} "
                        f"at {local_hour:02d}:{local_minute:02d} ({tz_name})"
                    )
                    # Run in background to not block the loop
                    asyncio.create_task(
                        _safe_run_audit(night_audit_core_service, tenant_id)
                    )

        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")

        # Sleep 60 seconds between checks
        await asyncio.sleep(60)


async def _safe_run_audit(service, tenant_id: str):
    """Safely execute scheduled audit with error handling."""
    try:
        result = await service.run_scheduled_audit(tenant_id)
        logger.info(f"Scheduled audit for {tenant_id}: {result.get('status', 'unknown')}")
    except Exception as e:
        logger.exception(f"Scheduled audit error for {tenant_id}: {e}")


def _utc_to_local(utc_dt: datetime, tz_name: str) -> datetime:
    """Convert UTC datetime to local time using offset mapping."""
    offsets = {
        "Europe/Istanbul": 3,
        "Europe/London": 0,
        "Europe/Berlin": 1,
        "Europe/Paris": 1,
        "Europe/Moscow": 3,
        "Asia/Dubai": 4,
        "Asia/Tokyo": 9,
        "America/New_York": -5,
        "America/Chicago": -6,
        "America/Los_Angeles": -8,
        "UTC": 0,
    }
    offset_hours = offsets.get(tz_name, 3)  # Default to Istanbul
    return utc_dt + timedelta(hours=offset_hours)


def start_scheduler():
    """Start the scheduler background task."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        logger.info("Night Audit Scheduler task created")


def stop_scheduler():
    """Stop the scheduler background task."""
    global _scheduler_running, _scheduler_task
    _scheduler_running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    logger.info("Night Audit Scheduler stopped")
