"""Deactivate (never delete) records left under a tenant_id that belongs to no hotel.

Found on 2026-10-16: 146 bookings (with payments, folios, ...) under
``tenant_id: "343281"``. That is a 6-digit hotel_id, not a tenant UUID, and
no tenant has it as id or hotel_id. The stress seed resolved
``E2E_STRESS_TENANT_ID`` (a hotel_id) to a tenant and, when none matched,
silently wrote with the raw value; the seed now refuses that.

What it does
------------
* Refuses to run if any tenant has this id or hotel_id: a real hotel's data
  is never touched.
* Bookings still open (confirmed, guaranteed, pending, checked_in, no_show)
  → ``cancelled`` with ``cancellation_reason = orphan_tenant_cleanup``, and
  their room-night locks are released. Every booking of the tenant gets a
  ``cleanup`` marker (tag, run id, previous status).
* Nothing is deleted; other collections are only counted and reported.

Safety contract
---------------
* ``--tenant-id`` is mandatory: one orphan tenant id per run.
* Default is a dry run that prints the counts.
* ``--apply`` / ``--undo`` additionally require ``ALLOW_ORPHAN_DEACTIVATION=true``.
* ``--undo RUN_ID`` restores the previous status of bookings still exactly as
  that run left them; anything changed since is reported, not touched.
* Every run writes a summary to ``test_data_cleanup_runs``.

Usage
-----
    python -m scripts.deactivate_orphan_tenant_records --tenant-id 343281
    ALLOW_ORPHAN_DEACTIVATION=true python -m scripts.deactivate_orphan_tenant_records --tenant-id 343281 --apply
    ALLOW_ORPHAN_DEACTIVATION=true python -m scripts.deactivate_orphan_tenant_records --tenant-id 343281 --undo <run_id>
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("deactivate_orphan_tenant_records")

CLEANUP_TAG = "orphan_tenant_cleanup"
OPEN_STATUSES = ["confirmed", "guaranteed", "pending", "checked_in", "no_show"]


class RealTenantError(RuntimeError):
    pass


async def assert_orphan(database, tenant_id: str) -> None:
    owner = await database.tenants.find_one({"$or": [{"id": tenant_id}, {"hotel_id": tenant_id}]},
                                            {"_id": 0, "id": 1, "property_name": 1})
    if owner:
        raise RealTenantError(f"{tenant_id!r} bir otele ait ({owner.get('property_name') or owner.get('id')}); hiçbir şey yapılmadı.")


async def survey(database, tenant_id: str) -> dict:
    counts = {}
    for name in sorted(await database.list_collection_names()):
        try:
            found = await database[name].count_documents({"tenant_id": tenant_id})
        except Exception:  # noqa: BLE001 - views / restricted collections
            continue
        if found:
            counts[name] = found
    statuses = collections.Counter()
    async for row in database.bookings.find({"tenant_id": tenant_id}, {"_id": 0, "status": 1}):
        statuses[str(row.get("status"))] += 1
    return {"collections": counts, "booking_statuses": dict(statuses)}


async def apply_run(database, tenant_id: str, run_id: str) -> dict:
    from core.atomic_booking import release_booking_nights
    from core.tenant_db import tenant_context

    now = datetime.now(UTC).isoformat()
    cancelled = marked = released = 0
    async for booking in database.bookings.find({"tenant_id": tenant_id, "cleanup.tag": {"$ne": CLEANUP_TAG}},
                                                {"_id": 0, "id": 1, "status": 1}):
        previous = booking.get("status")
        is_open = previous in OPEN_STATUSES
        update: dict = {"cleanup": {"tag": CLEANUP_TAG, "run_id": run_id, "previous_status": previous, "at": now}}
        if is_open:
            update.update(status="cancelled", cancellation_reason=CLEANUP_TAG, cancelled_at=now, updated_at=now)
        result = await database.bookings.update_one(
            {"id": booking["id"], "tenant_id": tenant_id, "status": previous}, {"$set": update})
        if not getattr(result, "modified_count", 0):
            continue  # changed meanwhile: left for the next run
        marked += 1
        if is_open:
            cancelled += 1
            with tenant_context(tenant_id):
                released += await release_booking_nights(tenant_id, booking["id"], reason=CLEANUP_TAG)
    return {"marked": marked, "cancelled": cancelled, "released_nights": released}


async def undo_run(database, tenant_id: str, run_id: str) -> dict:
    restored, conflicts = 0, []
    async for booking in database.bookings.find({"tenant_id": tenant_id, "cleanup.run_id": run_id},
                                                {"_id": 0, "id": 1, "status": 1, "cleanup": 1}):
        previous = booking["cleanup"].get("previous_status")
        expected = "cancelled" if previous in OPEN_STATUSES else previous
        result = await database.bookings.update_one(
            {"id": booking["id"], "tenant_id": tenant_id, "cleanup.run_id": run_id, "status": expected},
            {"$set": {"status": previous}, "$unset": {"cleanup": "", "cancellation_reason": "", "cancelled_at": ""}}
            if previous in OPEN_STATUSES else {"$unset": {"cleanup": ""}},
        )
        if getattr(result, "modified_count", 0):
            restored += 1
        else:
            conflicts.append(booking["id"])
    # Released room nights are not re-locked: an orphan tenant sells nothing.
    return {"restored": restored, "conflicts": conflicts}


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", metavar="RUN_ID")
    args = parser.parse_args(argv)

    allowed = os.environ.get("ALLOW_ORPHAN_DEACTIVATION", "").lower() == "true"
    if (args.apply or args.undo) and not allowed:
        logger.error("--apply/--undo için ALLOW_ORPHAN_DEACTIVATION=true gerekli; hiçbir değişiklik yapılmadı.")
        return 2

    from core.tenant_db import get_system_db

    database = get_system_db()
    try:
        await assert_orphan(database, args.tenant_id)
    except RealTenantError as exc:
        logger.error(str(exc))
        return 3

    if args.undo:
        result = await undo_run(database, args.tenant_id, args.undo)
        logger.info("Geri alındı: %d rezervasyon, %d çatışma (run_id=%s)", result["restored"], len(result["conflicts"]), args.undo)
        return 0

    found = await survey(database, args.tenant_id)
    logger.info("Koleksiyonlar: %s", found["collections"])
    logger.info("Rezervasyon durumları: %s", found["booking_statuses"])
    run_id = str(uuid.uuid4())
    summary = {"run_id": run_id, "tag": CLEANUP_TAG, "tenant_id": args.tenant_id,
               "mode": "apply" if args.apply else "dry_run", "found": found, "at": datetime.now(UTC).isoformat()}
    if args.apply:
        summary["applied"] = await apply_run(database, args.tenant_id, run_id)
        logger.info("Uygulandı (run_id=%s): %s", run_id, summary["applied"])
    else:
        logger.info("Kuru çalıştırma: değişiklik yapılmadı. Uygulamak için --apply kullanın.")
    await database.test_data_cleanup_runs.insert_one(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
