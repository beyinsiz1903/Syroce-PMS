"""
Pre-Arrival Scheduler — Daily Background Worker
=================================================

Scans bookings collection for check-ins happening tomorrow
and triggers 'pre_arrival' automation events (WhatsApp directions, facility info).

Runs as a background asyncio task, configurable interval.
Also provides manual trigger endpoint.
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

logger = logging.getLogger("messaging.pre_arrival_scheduler")


class PreArrivalScheduler:
    """Background scheduler that fires pre_arrival events for tomorrow's check-ins."""

    def __init__(self, interval_hours: float = 6.0):
        self._interval_hours = interval_hours
        self._running = False
        self._task: asyncio.Task | None = None
        self._started_at: str | None = None
        self._last_run_at: str | None = None
        self._last_run_result: dict | None = None
        self._total_runs: int = 0
        self._total_sent: int = 0
        self._total_skipped: int = 0
        self._total_errors: int = 0

    @property
    def status(self) -> str:
        if self._running:
            return "running"
        return "stopped"

    async def start(self):
        if self._running:
            return
        self._running = True
        self._started_at = datetime.now(UTC).isoformat()
        self._task = asyncio.create_task(self._loop())
        logger.info("Pre-arrival scheduler started (interval=%sh)", self._interval_hours)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Pre-arrival scheduler stopped")

    async def _loop(self):
        while self._running:
            try:
                await self.run_scan()
                await asyncio.sleep(self._interval_hours * 3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Pre-arrival scheduler loop error: {e}")
                await asyncio.sleep(300)  # retry in 5min on error

    async def run_scan(self) -> dict:
        """Scan all tenants for tomorrow's check-ins and fire pre_arrival events."""
        # v42 round-3: cross-tenant scan; manual `tenant_id` filters preserved.
        from core.tenant_db import get_system_db
        db = get_system_db()

        now = datetime.now(UTC)
        self._last_run_at = now.isoformat()
        self._total_runs += 1

        # Tomorrow date range (00:00 to 23:59)
        tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow_start + timedelta(days=1)

        result = {
            "run_id": str(uuid.uuid4())[:8],
            "run_at": now.isoformat(),
            "bookings_scanned": 0,
            "events_fired": 0,
            "already_sent": 0,
            "errors": 0,
            "details": [],
        }

        try:
            # Get all tenants that have pre_arrival automation rules enabled
            active_tenants = await db.messaging_automation_rules.distinct(
                "tenant_id",
                {"trigger_event": "pre_arrival", "enabled": True},
            )

            if not active_tenants:
                result["details"].append("Aktif pre_arrival kurali olan tenant yok")
                self._last_run_result = result
                return result

            for tenant_id in active_tenants:
                try:
                    await self._scan_tenant(
                        db, tenant_id, tomorrow_start, tomorrow_end, result
                    )
                except Exception as e:
                    logger.exception(f"Pre-arrival scan error for tenant {tenant_id}: {e}")
                    result["errors"] += 1
                    self._total_errors += 1

        except Exception as e:
            logger.exception(f"Pre-arrival global scan error: {e}")
            result["errors"] += 1
            self._total_errors += 1

        self._last_run_result = result
        logger.info(
            "Pre-arrival scan complete: scanned=%d fired=%d skipped=%d errors=%d",
            result["bookings_scanned"], result["events_fired"],
            result["already_sent"], result["errors"],
        )
        return result

    async def _scan_tenant(self, db, tenant_id: str, tomorrow_start, tomorrow_end, result: dict):
        """Scan a single tenant's bookings for tomorrow's check-ins."""
        from modules.messaging.automation import process_booking_event

        # Query bookings with check_in tomorrow and status = confirmed
        # check_in is stored as ISO string, so we compare string ranges
        start_str = tomorrow_start.isoformat()
        end_str = tomorrow_end.isoformat()

        bookings = await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": "confirmed",
                "check_in": {"$gte": start_str, "$lt": end_str},
            },
            {"_id": 0},
        ).to_list(200)

        result["bookings_scanned"] += len(bookings)

        for booking in bookings:
            booking_id = booking.get("id", "")
            try:
                # Check if pre_arrival was already sent for this booking
                already = await db.messaging_delivery_logs.find_one(
                    {
                        "tenant_id": tenant_id,
                        "booking_id": booking_id,
                        "use_case": "pre_arrival",
                        "status": {"$in": ["sent", "delivered"]},
                    },
                )
                if already:
                    result["already_sent"] += 1
                    self._total_skipped += 1
                    continue

                # v42 round-4: process_booking_event() touches tenant-scoped
                # collections via the proxy. Establish tenant_context so the
                # downstream proxy auto-injects tenant_id (and STRICT mode
                # is satisfied). The async ContextVar persists across the
                # awaited call within the same task.
                from core.tenant_db import tenant_context
                with tenant_context(tenant_id):
                    await process_booking_event(tenant_id, "pre_arrival", booking)
                result["events_fired"] += 1
                self._total_sent += 1

                # Create in-app notification
                await _create_notification(
                    db, tenant_id,
                    title="Pre-Arrival Mesaji Gonderildi",
                    message=f"{booking.get('guest_name', 'Misafir')} icin yarin check-in oncesi mesaj gonderildi (Oda {booking.get('room_number', '?')})",
                    notif_type="messaging_automation",
                    action_url="/messaging-dashboard",
                )

            except Exception as e:
                logger.warning(f"Pre-arrival event error for booking {booking_id}: {e}")
                result["errors"] += 1
                self._total_errors += 1

    def get_status(self) -> dict:
        return {
            "status": self.status,
            "started_at": self._started_at,
            "interval_hours": self._interval_hours,
            "last_run_at": self._last_run_at,
            "last_run_result": self._last_run_result,
            "total_runs": self._total_runs,
            "total_sent": self._total_sent,
            "total_skipped": self._total_skipped,
            "total_errors": self._total_errors,
        }


# ── Singleton ──
_scheduler: PreArrivalScheduler | None = None


def get_pre_arrival_scheduler() -> PreArrivalScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = PreArrivalScheduler()
    return _scheduler


# ── Shared notification helper ──
async def _create_notification(
    db, tenant_id: str, title: str, message: str,
    notif_type: str = "info", action_url: str | None = None,
    priority: str = "normal",
):
    """Create an in-app notification visible in the NotificationBell."""
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "user_id": None,  # tenant-wide (visible to all users)
        "type": notif_type,
        "title": title,
        "message": message,
        "priority": priority,
        "read": False,
        "action_url": action_url,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.notifications.insert_one(doc)
    return doc
