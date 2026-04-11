"""
Night Audit — Background Scheduler (NA-001/NA-002 Hardened)
Uses the hardened engine for all scheduled runs.
Checks every 60 seconds if any tenant's scheduled audit time has arrived.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

_scheduler_task = None
_scheduler_running = False


async def _scheduler_loop():
    global _scheduler_running
    _scheduler_running = True
    logger.info("Night Audit Scheduler started (hardened)")

    from core.database import db

    while _scheduler_running:
        try:
            now_utc = datetime.now(UTC)

            schedules = await db.night_audit_schedules.find(
                {"enabled": True}, {"_id": 0}
            ).to_list(500)

            for schedule in schedules:
                tenant_id = schedule.get("tenant_id")
                sched_hour = schedule.get("scheduled_hour", 0)
                sched_minute = schedule.get("scheduled_minute", 0)
                tz_name = schedule.get("timezone", "Europe/Istanbul")

                local_now = _utc_to_local(now_utc, tz_name)

                if local_now.hour == sched_hour and local_now.minute == sched_minute:
                    last_auto_run = schedule.get("last_auto_run")
                    if last_auto_run:
                        last_run_dt = datetime.fromisoformat(last_auto_run.replace("Z", "+00:00"))
                        last_run_local = _utc_to_local(last_run_dt, tz_name)
                        if last_run_local.date() == local_now.date():
                            continue

                    logger.info(
                        "Triggering scheduled night audit for tenant %s at %02d:%02d (%s)",
                        tenant_id, sched_hour, sched_minute, tz_name,
                    )
                    asyncio.create_task(_safe_run_audit(tenant_id, db))

        except Exception as e:
            logger.error("Scheduler loop error: %s", e)

        await asyncio.sleep(60)


async def _safe_run_audit(tenant_id: str, db):
    """Execute scheduled audit using the hardened engine."""
    try:
        from core.night_audit_hardened import start_night_audit

        # Get current business date
        settings = await db.tenant_settings.find_one(
            {"tenant_id": tenant_id}, {"_id": 0, "business_date": 1}
        )
        bd = (settings or {}).get("business_date", datetime.now(UTC).date().isoformat())

        result = await start_night_audit(
            tenant_id=tenant_id,
            business_date=bd,
            trigger_source="scheduler",
            actor={"id": "system_scheduler", "email": "system"},
        )

        status = "completed" if result.get("success") else "failed"
        error_msg = None if result.get("success") else result.get("error")
        run_id = None
        if result.get("success") and result.get("run"):
            run_id = result["run"].get("id")
        elif result.get("run_id"):
            run_id = result["run_id"]

        # Update schedule log
        now = datetime.now(UTC).isoformat()
        await db.night_audit_schedule_logs.insert_one({
            "id": str(__import__("uuid").uuid4()),
            "tenant_id": tenant_id,
            "triggered_at": now,
            "business_date": bd,
            "trigger_type": "automatic",
            "status": status,
            "run_id": run_id,
            "error": error_msg,
            "completed_at": now,
        })
        await db.night_audit_schedules.update_one(
            {"tenant_id": tenant_id},
            {"$set": {"last_auto_run": now, "last_auto_run_status": status}},
        )

        logger.info("Scheduled audit for %s: %s (run: %s)", tenant_id, status, run_id)

    except Exception as e:
        logger.exception("Scheduled audit error for %s: %s", tenant_id, e)


def _utc_to_local(utc_dt: datetime, tz_name: str) -> datetime:
    offsets = {
        "Europe/Istanbul": 3, "Europe/London": 0, "Europe/Berlin": 1,
        "Europe/Paris": 1, "Europe/Moscow": 3, "Asia/Dubai": 4,
        "Asia/Tokyo": 9, "America/New_York": -5, "America/Chicago": -6,
        "America/Los_Angeles": -8, "UTC": 0,
    }
    offset_hours = offsets.get(tz_name, 3)
    return utc_dt + timedelta(hours=offset_hours)


def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        logger.info("Night Audit Scheduler task created (hardened)")


def stop_scheduler():
    global _scheduler_running, _scheduler_task
    _scheduler_running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    logger.info("Night Audit Scheduler stopped")
