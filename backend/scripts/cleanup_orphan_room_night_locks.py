"""Maintenance sweep for orphaned room-night locks (Task #435).

Background
----------
Every booking claims one row per night in ``room_night_locks`` via the unique
compound index ``(tenant_id, room_id, night_date)`` (see
``core/atomic_booking.py``). The lock is the *primary* oversell guard: a fresh
reservation on the same room/night is physically blocked by a
``DuplicateKeyError``.

When a booking is cancelled / no-shows / is deleted, its locks are supposed to
be released by ``release_booking_nights``. Some compensation paths delete the
booking row *before* releasing its nights and swallow a failed release (e.g.
the multi-room saga rollback in ``routers/pms_bookings.py``: it runs
``db.bookings.delete_one(...)`` then ``release_booking_nights(...)`` inside a
broad ``try/except: pass`` / logged-only block). If that release raises, the
booking row is gone but its night-lock lingers — an **orphan lock**.

The visible symptom (the one that opened this task) is a consistency gap
between two code paths:

  * ``GET /api/pms/walkin/available-rooms`` and the front-desk grid derive
    "busy" rooms from the ``bookings`` collection only. They never consult
    ``room_night_locks``, so a room whose only claim is an orphan lock shows
    as **AVAILABLE**.
  * The booking-creation night-claim phase in ``create_booking_atomic`` *does*
    hit the lock and rejects the request with ``409 already booked by
    <ghost-booking-id>``.

Net effect for the pilot operator: an empty room looks bookable but every
attempt to book it fails. The concrete instance was booking
``f107faaf-25f9-4b1d-b2cb-3e379abe88b5`` (no longer in ``db.bookings``;
full-detail 404, ``/api/pms/bookings`` window returns 0) whose ``2026-07-11``
night-lock was still present.

Relationship to the F8N duplicate auto-resolver
-----------------------------------------------
The scheduled F8N resolver (``core/atomic_booking.list_room_night_lock_
duplicate_groups`` / ``resolve_room_night_lock_duplicates``) only acts on
groups with **two or more** locks on the same (tenant, room, night). A lone
orphan lock — count == 1, no duplicate sibling — is invisible to it. This
sweep covers exactly that gap.

What counts as an orphan
------------------------
A lock is an orphan when its owning ``booking_id`` no longer points at a live
booking:

  * ``booking_missing``  — no ``bookings`` row for ``(tenant_id, booking_id)``
    (deleted / half-created). This is the f107faaf class.
  * ``booking_terminal`` — the booking exists but is in a terminal state
    (``cancelled`` / ``no_show`` / ``checked_out``) whose nights should have
    been released.
  * ``missing_booking_id`` — the lock has no ``booking_id`` at all.

Locks that are intentional inventory blocks are **never** treated as orphans:

  * ``lock_type`` in {ooo, oos, maintenance, ota_unmatched_hold}, or
  * ``booking_id`` starting with ``OOO:`` / ``OOS:`` / ``MAINT:``.

Active / hold bookings keep their locks. ``ota_unmatched_hold`` sentinel locks
DO reference a real (hold) booking row, but we skip them by type so the
inventory-protection artefact is never disturbed.

Safety contract (pilot_drift = 0 doctrine)
------------------------------------------
* Default is **dry-run**: it lists orphans and writes a metric row, but
  deletes nothing.
* ``--apply`` requires ``ALLOW_ORPHAN_LOCK_CLEANUP=true`` (fail-closed). The
  destructive path is opt-in twice (CLI flag + env var).
* ``--tenant <id>`` scopes the scan to a single tenant. With no tenant filter
  the (read-only) scan covers all tenants; ``--apply`` still only deletes the
  exact orphan rows that were classified.
* ``--hours`` (default 24) is an age guard: only locks older than the cutoff
  are eligible, so an in-flight booking creation that briefly holds a lock
  before its booking row is committed is never raced.
* Every delete is re-scoped to the exact
  ``(tenant_id, room_id, night_date, booking_id)`` tuple — never wider — so a
  concurrent re-lock of that night by a *different* booking can never be
  removed.

Usage
-----
    # Default: dry-run, list orphan locks, no writes
    python -m scripts.cleanup_orphan_room_night_locks

    # Scope to one tenant
    python -m scripts.cleanup_orphan_room_night_locks --tenant <uuid>

    # Focus on a single ghost booking (root-cause confirmation)
    python -m scripts.cleanup_orphan_room_night_locks \
        --booking f107faaf-25f9-4b1d-b2cb-3e379abe88b5

    # Apply (requires ALLOW_ORPHAN_LOCK_CLEANUP=true)
    ALLOW_ORPHAN_LOCK_CLEANUP=true \
        python -m scripts.cleanup_orphan_room_night_locks --apply

    # Custom age window (default 24h)
    python -m scripts.cleanup_orphan_room_night_locks --hours 12

Operational metric
------------------
Every run inserts a summary doc into ``orphan_room_night_lock_scans`` with
timestamp, mode, counts per root-cause class, and applied count. Any row with
``found_total > 0`` after the next sweep is an actionable signal that a
compensation path is leaking locks.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from core.database import db  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cleanup_orphan_room_night_locks")

# Terminal booking statuses whose nights should already be released. Mirrors
# core.atomic_booking.TERMINAL_BOOKING_STATUSES so the orphan definition stays
# consistent with the engine's own oversell-exclusion rule.
TERMINAL_BOOKING_STATUSES = ("cancelled", "no_show", "checked_out")

# Intentional inventory-block lock types — NEVER orphan candidates.
BLOCK_LOCK_TYPES = ("ooo", "oos", "maintenance", "ota_unmatched_hold")

# Block booking_id prefixes (defensive; OOO/OOS/MAINT use these synthetic ids).
BLOCK_BOOKING_PREFIXES = ("OOO:", "OOS:", "MAINT:")


def _is_block_lock(lock: dict) -> bool:
    """True for intentional inventory-block / sentinel locks (skip them)."""
    if (lock.get("lock_type") or "") in BLOCK_LOCK_TYPES:
        return True
    bid = lock.get("booking_id") or ""
    return isinstance(bid, str) and bid.startswith(BLOCK_BOOKING_PREFIXES)


def _is_old_enough(lock: dict, cutoff: datetime, cutoff_iso: str) -> bool:
    """Age guard: a lock with no ``created_at`` is legacy (eligible); otherwise
    it must be at or before the cutoff. Accepts ISO strings or BSON datetimes."""
    created = lock.get("created_at")
    if created is None:
        return True
    try:
        if isinstance(created, str):
            return created <= cutoff_iso
        return created <= cutoff
    except TypeError:
        # Unexpected type — treat as not-eligible (conservative).
        return False


async def _classify_owner(tenant_id: str, booking_id: str | None, cache: dict) -> dict:
    """Classify a lock's owner. Returns dict with ``orphan`` bool, a
    ``root_cause`` label, and the owning ``status`` when known."""
    if not booking_id:
        return {"orphan": True, "root_cause": "missing_booking_id", "status": None}

    cache_key = (tenant_id, booking_id)
    if cache_key in cache:
        return cache[cache_key]

    try:
        doc = await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"_id": 0, "id": 1, "status": 1},
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "owner lookup failed (tenant=%s booking=%s): %s",
            tenant_id,
            booking_id,
            exc,
        )
        # Unknown classification — never retire data we could not read.
        result = {"orphan": False, "root_cause": "lookup_error", "status": None}
        cache[cache_key] = result
        return result

    if not doc:
        result = {"orphan": True, "root_cause": "booking_missing", "status": None}
    else:
        status = (doc.get("status") or "").lower()
        if status in TERMINAL_BOOKING_STATUSES:
            result = {
                "orphan": True,
                "root_cause": "booking_terminal",
                "status": status,
            }
        else:
            result = {"orphan": False, "root_cause": "active", "status": status}
    cache[cache_key] = result
    return result


async def scan(
    tenant_id: str | None,
    hours: int,
    booking_filter: str | None = None,
) -> dict:
    """Find orphan locks. Read-only; never mutates."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    cutoff_iso = cutoff.isoformat()

    query: dict = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    if booking_filter:
        query["booking_id"] = booking_filter
    # Exclude intentional inventory-block lock types at the DB level; the
    # prefix check in ``_is_block_lock`` is the defensive backstop.
    query["lock_type"] = {"$nin": list(BLOCK_LOCK_TYPES)}

    orphans: list[dict] = []
    owner_cache: dict = {}
    # Stream the full result set rather than capping with to_list(length=N):
    # silent truncation would make the sweep permanently fall behind.
    cursor = db.room_night_locks.find(query, {"_id": 0}).max_time_ms(60000)
    async for lock in cursor:
        if _is_block_lock(lock):
            continue
        if not _is_old_enough(lock, cutoff, cutoff_iso):
            continue
        cls = await _classify_owner(lock.get("tenant_id"), lock.get("booking_id"), owner_cache)
        if not cls["orphan"]:
            continue
        orphans.append(
            {
                "tenant_id": lock.get("tenant_id"),
                "room_id": lock.get("room_id"),
                "night_date": lock.get("night_date"),
                "booking_id": lock.get("booking_id"),
                "lock_type": lock.get("lock_type"),
                "created_at": (lock.get("created_at").isoformat() if hasattr(lock.get("created_at"), "isoformat") else lock.get("created_at")),
                "root_cause": cls["root_cause"],
                "owner_status": cls["status"],
            }
        )

    by_cause: dict = {}
    for o in orphans:
        by_cause[o["root_cause"]] = by_cause.get(o["root_cause"], 0) + 1

    return {"cutoff": cutoff_iso, "orphans": orphans, "by_cause": by_cause}


async def apply(orphans: list[dict]) -> int:
    """Delete each orphan lock by its exact identity tuple. Never wider."""
    deleted = 0
    for o in orphans:
        flt = {
            "tenant_id": o["tenant_id"],
            "room_id": o["room_id"],
            "night_date": o["night_date"],
            "booking_id": o["booking_id"],
        }
        try:
            res = await db.room_night_locks.delete_many(flt)
            deleted += res.deleted_count
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("orphan delete failed (%s): %s", flt, exc)
    return deleted


async def record_scan(summary: dict) -> None:
    """Persist a summary row so admin dashboards / alerts can poll it."""
    try:
        await db.orphan_room_night_lock_scans.insert_one(summary)
    except Exception as e:  # pragma: no cover - best-effort metric
        logger.warning("[orphan-locks] metric insert failed: %s", e)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Orphan room-night-lock sweep (Task #435).")
    parser.add_argument(
        "--tenant",
        type=str,
        default=None,
        help="Yalnizca bu tenant'i tara (verilmezse tum tenant'lar; scan salt-okunur).",
    )
    parser.add_argument(
        "--booking",
        type=str,
        default=None,
        help="Yalnizca bu booking_id'ye ait kilitleri tara (kok-neden teyidi icin).",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Yas esigi (saat). Bu sureden eski kilitler hedeflenir.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Bulduklarini uygula (orphan kilitleri sil). Aksi halde dry-run.",
    )
    args = parser.parse_args()

    if args.apply and os.environ.get("ALLOW_ORPHAN_LOCK_CLEANUP", "").lower() != "true":
        logger.error("--apply icin ALLOW_ORPHAN_LOCK_CLEANUP=true gerekli — fail-closed.")
        return 2

    logger.info(
        "[orphan-locks] tenant=%s booking=%s hours=%d mode=%s",
        args.tenant or "ALL",
        args.booking or "ALL",
        args.hours,
        "APPLY" if args.apply else "DRY-RUN",
    )

    found = await scan(args.tenant, args.hours, args.booking)
    orphans = found["orphans"]
    total = len(orphans)

    applied = 0
    if args.apply and total > 0:
        applied = await apply(orphans)

    summary = {
        "scanned_at": datetime.now(UTC).isoformat(),
        "tenant_id": args.tenant,
        "booking_filter": args.booking,
        "hours": args.hours,
        "mode": "apply" if args.apply else "dry_run",
        "cutoff": found["cutoff"],
        "found_total": total,
        "by_cause": found["by_cause"],
        "applied_deleted": applied,
        "sample_orphans": orphans[:20],
    }
    await record_scan(summary)

    print("=" * 60)
    print(f"Orphan room-night-lock sweep ({'APPLY' if args.apply else 'DRY-RUN'}) tenant={args.tenant or 'ALL'}")
    print("=" * 60)
    if found["by_cause"]:
        for cause, n in sorted(found["by_cause"].items()):
            print(f"  {cause:20s} -> {n}")
    print(f"  {'TOPLAM':20s} -> {total}")
    if args.apply:
        print(f"  {'silinen kilit':20s} -> {applied}")
    print(f"  metric row          -> orphan_room_night_lock_scans @ {summary['scanned_at']}")

    if total > 0:
        logger.warning(
            "[orphan-locks] %d orphan kilit bulundu (%s) — bos odalar 'dolu' gorunuyor olabilir; compensation/release yolunu kontrol et.",
            total,
            ", ".join(f"{k}={v}" for k, v in sorted(found["by_cause"].items())),
        )
        # Non-zero exit when orphans exist in dry-run mode so cron/CI can alert.
        # When --apply succeeds we still exit 0 (the orphans were handled).
        if not args.apply:
            return 1
    else:
        logger.info("[orphan-locks] orphan=0, kilit tablosu temiz.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
