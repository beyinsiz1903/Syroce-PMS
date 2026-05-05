"""V3 — Syroce mobil push scheduler for VIP arrivals + no-show risk.

The polling endpoints `/api/notifications/mobile/frontdesk` already surface
both event types but only when staff actively open the mobile app. To make
them real OS-level push notifications (so a phone vibrates regardless of
app state), this worker periodically scans every active tenant and fires
a push via `services.expo_push.fire_and_forget_expo_push`.

De-duplication
--------------
A `mobile_push_dedupe` collection holds one row per
`(tenant_id, type, target_id, day)`. The unique compound index ensures
two scheduler ticks (or two pods) won't double-push the same booking on
the same calendar day. Rows expire automatically via a TTL on `expires_at`.

Scheduling
----------
Started from `bootstrap.phases.c_domain` with a 15-min interval (env
`MOBILE_PUSH_SCAN_SECONDS`). Each tick is best-effort: an exception in
one tenant scan never aborts the loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Default cadence: 15 minutes. Set MOBILE_PUSH_SCAN_SECONDS=0 to disable.
DEFAULT_INTERVAL_SECONDS = int(os.environ.get("MOBILE_PUSH_SCAN_SECONDS", "900"))
# V3 acceptance — "VIP geliyor (60 dk önce)". The scheduler ticks every 15 min
# and fires once per arrival when its check-in falls within this window. With a
# 60-min default + 15-min cadence, the push lands in the [-60min, -45min] band
# before the actual check-in time. Dedupe (per booking + check-in date) ensures
# only the FIRST tick that observes the arrival in-window actually pushes.
VIP_WINDOW_MINUTES = int(os.environ.get("MOBILE_PUSH_VIP_WINDOW_MINUTES", "60"))
# A booking with check-in >= this many minutes ago that is still
# `confirmed`/`guaranteed` (i.e. nobody arrived) is considered at no-show
# risk.
NO_SHOW_GRACE_MINUTES = int(os.environ.get("MOBILE_PUSH_NO_SHOW_GRACE_MINUTES", "120"))
# How long dedupe rows live (slightly longer than a day so an event near
# midnight isn't re-fired the next morning).
_DEDUPE_TTL_DAYS = 2

_started = False


def _db():
    from server import db
    return db


async def _ensure_indexes() -> None:
    db = _db()
    try:
        await db.mobile_push_dedupe.create_index(
            [("tenant_id", 1), ("type", 1), ("target_id", 1), ("day", 1)],
            unique=True,
            name="mobile_push_dedupe_unique",
        )
        await db.mobile_push_dedupe.create_index(
            "expires_at",
            expireAfterSeconds=0,
            name="mobile_push_dedupe_ttl",
        )
    except Exception as e:
        logger.warning("[mobile-push-scheduler] dedupe index ensure failed: %s", e)


async def _claim_dedupe(tenant_id: str, kind: str, target_id: str, day: str) -> bool:
    """Atomically claim a (type, target, day) slot. Returns True if THIS
    call is allowed to send the push, False if a previous tick already did."""
    from pymongo.errors import DuplicateKeyError
    db = _db()
    expires_at = datetime.now(UTC) + timedelta(days=_DEDUPE_TTL_DAYS)
    try:
        await db.mobile_push_dedupe.insert_one({
            "tenant_id": tenant_id,
            "type": kind,
            "target_id": target_id,
            "day": day,
            "claimed_at": datetime.now(UTC),
            "expires_at": expires_at,
        })
        return True
    except DuplicateKeyError:
        return False
    except Exception as e:
        logger.warning("[mobile-push-scheduler] dedupe claim failed: %s", e)
        # On unexpected DB errors, return False so we don't risk spamming.
        return False


def _date_range_or(field: str, lo: datetime, hi: datetime) -> dict[str, Any]:
    """Build a Mongo `$or` clause that matches `field` whether it is stored
    as a real `datetime` (preferred) or as an ISO-8601 string. Some legacy
    tenants persist `check_in`/`check_out` as ISO strings (e.g. when the
    booking was imported from a CSV or a third-party PMS). String range
    comparison is reliable for ISO-8601 only when both bounds are
    formatted identically — we use `isoformat()` on UTC `datetime`s, so
    lexicographic ordering matches chronological ordering. Without this
    helper the scheduler would silently miss those bookings.
    """
    return {
        "$or": [
            {field: {"$gte": lo, "$lte": hi}},
            {field: {"$gte": lo.isoformat(), "$lte": hi.isoformat()}},
        ],
    }


def _coerce_datetime(value: Any) -> datetime | None:
    """Best-effort parse of a stored check-in/check-out value into a UTC
    `datetime`. Accepts real `datetime` instances and ISO-8601 strings.
    Returns `None` if the value is unusable so the caller can skip it
    instead of raising mid-loop."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            # `fromisoformat` handles both `2026-05-04T12:00:00+00:00` and
            # `2026-05-04T12:00:00`. The trailing `Z` shorthand is not
            # accepted before Python 3.11, so normalise it.
            v = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(v)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None
    return None


async def _scan_tenant_vip_arrivals(tenant_id: str, fire) -> int:
    """Fire push ~60 min before a VIP guest's check-in.

    The acceptance criterion is "VIP geliyor (60 dk önce)" — a single push
    that lands shortly before the guest reaches the desk. We scan a tight
    window (`now` → `now + VIP_WINDOW_MINUTES`) so a booking 6 hours away
    does NOT fire prematurely. Dedupe is keyed per booking + the booking's
    check-in date, so:
      * a single arrival fires exactly one push (the first tick that sees
        the booking inside the window claims the slot)
      * if the booking is rescheduled to a different day, that new arrival
        gets its own push
    """
    db = _db()
    now = datetime.now(UTC)
    horizon = now + timedelta(minutes=VIP_WINDOW_MINUTES)

    query: dict[str, Any] = {
        "tenant_id": tenant_id,
        "status": {"$in": ["confirmed", "guaranteed"]},
    }
    # Tolerate tenants that store `check_in` as ISO strings (CSV imports,
    # third-party PMS sync). See _date_range_or for the contract.
    query.update(_date_range_or("check_in", now, horizon))
    bookings = await db.bookings.find(query).to_list(500)
    if not bookings:
        return 0

    guest_ids = [b.get("guest_id") for b in bookings if b.get("guest_id")]
    if not guest_ids:
        return 0
    guest_map: dict[str, dict[str, Any]] = {}
    async for g in db.guests.find({
        "id": {"$in": guest_ids},
        "tenant_id": tenant_id,
        "vip_status": {"$ne": False},
    }, {"_id": 0, "id": 1, "vip_status": 1, "first_name": 1, "last_name": 1}):
        if g.get("vip_status"):
            guest_map[g["id"]] = g

    fired = 0
    for b in bookings:
        gid = b.get("guest_id")
        guest = guest_map.get(gid)
        if not guest:
            continue
        # Normalise check_in once so dedupe-day + display HH:MM are
        # consistent regardless of storage format (datetime vs ISO string).
        check_in_raw = b.get("check_in")
        check_in = _coerce_datetime(check_in_raw)
        if check_in is None:
            # Unparseable — skip rather than risk a wrong dedupe slot.
            continue
        # Dedupe day = the BOOKING'S check-in date (not "today"). Otherwise
        # an arrival straddling midnight could be re-fired on the next day.
        arrival_day = check_in.date().isoformat()
        if not await _claim_dedupe(tenant_id, "vip_arrival", b.get("id"), arrival_day):
            continue
        guest_name = b.get("guest_name") or f"{guest.get('first_name','')} {guest.get('last_name','')}".strip()
        fire(
            tenant_id,
            title=f"VIP gelis · {guest_name}",
            body=(
                f"Oda {b.get('room_number') or '?'} · "
                f"{check_in.strftime('%H:%M')}"
            ).strip(' ·'),
            data={
                "type": "vip_arrival",
                "booking_id": b.get("id"),
                "guest_id": gid,
                "room_number": b.get("room_number"),
            },
            departments=["front_desk", "reception", "supervisor", "gm"],
            priority="high",
        )
        fired += 1
    return fired


async def _scan_tenant_no_show_risk(tenant_id: str, fire) -> int:
    """Fire push for bookings whose check-in time has passed by the grace
    period and are still confirmed (i.e. nobody arrived)."""
    db = _db()
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=NO_SHOW_GRACE_MINUTES)
    today = now.date().isoformat()

    # Same ISO-string tolerance as the VIP scan. We need BOTH `check_in`
    # past the no-show grace AND `check_out` still in the future, so we
    # combine two `$or` ranges via `$and`.
    bookings = await db.bookings.find({
        "tenant_id": tenant_id,
        "status": {"$in": ["confirmed", "guaranteed"]},
        "$and": [
            {"$or": [
                {"check_in": {"$lte": cutoff}},
                {"check_in": {"$lte": cutoff.isoformat()}},
            ]},
            {"$or": [
                {"check_out": {"$gte": now}},
                {"check_out": {"$gte": now.isoformat()}},
            ]},
        ],
    }).to_list(500)
    if not bookings:
        return 0

    fired = 0
    for b in bookings:
        if not await _claim_dedupe(tenant_id, "no_show_risk", b.get("id"), today):
            continue
        guest_name = b.get("guest_name") or "Misafir"
        fire(
            tenant_id,
            title=f"No-show riski · {guest_name}",
            body=(
                f"Oda {b.get('room_number') or '?'} · "
                f"giris saati {NO_SHOW_GRACE_MINUTES} dk once gecti, hala check-in olmadi"
            ),
            data={
                "type": "no_show_risk",
                "booking_id": b.get("id"),
                "room_number": b.get("room_number"),
            },
            departments=["front_desk", "reception", "supervisor"],
            priority="high",
        )
        fired += 1
    return fired


async def _tick() -> None:
    """One full scan over every tenant that has any registered push device."""
    db = _db()
    try:
        from services.expo_push import fire_and_forget_expo_push as fire
    except Exception:
        logger.exception("[mobile-push-scheduler] expo_push import failed; skipping tick")
        return

    # Only scan tenants that have at least one Expo token registered — this
    # keeps the scheduler proportional to actual mobile usage instead of
    # iterating every tenant in the system.
    try:
        tenant_ids = await db.push_device_tokens.distinct("tenant_id")
    except Exception as e:
        logger.warning("[mobile-push-scheduler] tenant enumeration failed: %s", e)
        return

    total_vip = 0
    total_no_show = 0
    for tid in tenant_ids:
        if not tid:
            continue
        try:
            total_vip += await _scan_tenant_vip_arrivals(tid, fire)
        except Exception as e:
            logger.warning("[mobile-push-scheduler] vip scan failed for %s: %s", tid, e)
        try:
            total_no_show += await _scan_tenant_no_show_risk(tid, fire)
        except Exception as e:
            logger.warning("[mobile-push-scheduler] no-show scan failed for %s: %s", tid, e)
    if total_vip or total_no_show:
        logger.info(
            "[mobile-push-scheduler] dispatched vip=%d no_show=%d across %d tenant(s)",
            total_vip, total_no_show, len(tenant_ids),
        )


async def _run_loop(interval_seconds: int) -> None:
    await _ensure_indexes()
    logger.info("[mobile-push-scheduler] loop started (interval=%ds)", interval_seconds)
    # Stagger the first run so the loop doesn't compete with hot startup work.
    await asyncio.sleep(min(60, interval_seconds))
    while True:
        try:
            await _tick()
        except Exception:
            logger.exception("[mobile-push-scheduler] tick crashed")
        await asyncio.sleep(interval_seconds)


def start(interval_seconds: int | None = None) -> bool:
    """Spawn the scheduler task. Idempotent. Returns True if started."""
    global _started
    if _started:
        return False
    interval = interval_seconds if interval_seconds is not None else DEFAULT_INTERVAL_SECONDS
    if interval <= 0:
        logger.info("[mobile-push-scheduler] disabled (interval<=0)")
        return False
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_run_loop(interval), name="mobile-push-scheduler")
        _started = True
        return True
    except Exception:
        logger.exception("[mobile-push-scheduler] failed to start")
        return False
