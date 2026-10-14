"""Deactivate (never delete) test and junk records left in a production tenant.

Found during the 2026-10-14 agency audit on the Demo Hotel tenant:

* hotel-bound agencies named with spreadsheet-formula payloads
  (``=cmd|'/c calc'!A1``) or ``TEST_*`` prefixes from automated suites;
* bookings scheduled years ahead (2039–2048) by test runs.

What it does
------------
* Agencies: ``status`` → ``inactive`` and ``cleanup`` metadata (tag, run id,
  previous status). Users, bookings and history are untouched.
* Bookings: active far-future bookings → ``cancelled`` with
  ``cancellation_reason = test_data_cleanup`` and their room-night locks
  released, so they stop blocking availability. Nothing is deleted.

Safety contract
---------------
* ``--tenant-id`` is mandatory: one tenant per run, no cross-tenant scan.
* Default is a dry run that prints every matching record.
* ``--apply`` additionally requires ``ALLOW_TEST_DATA_DEACTIVATION=true``.
* Every run writes a summary to ``test_data_cleanup_runs``; ``--undo RUN_ID``
  restores the agencies a run deactivated (cancelled bookings stay cancelled
  and are listed for manual review).

Usage
-----
    python -m scripts.deactivate_test_records --tenant-id <id>
    ALLOW_TEST_DATA_DEACTIVATION=true python -m scripts.deactivate_test_records --tenant-id <id> --apply
    python -m scripts.deactivate_test_records --tenant-id <id> --bookings-after 2035-01-01
    ALLOW_TEST_DATA_DEACTIVATION=true python -m scripts.deactivate_test_records --tenant-id <id> --undo <run_id>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("deactivate_test_records")

CLEANUP_TAG = "test_data_cleanup"
# Formula-injection payloads and automated-suite names.
JUNK_AGENCY_NAME = re.compile(r"^\s*[=+\-@]|^TEST_", re.IGNORECASE)
ACTIVE_BOOKING_STATUSES = ["confirmed", "guaranteed", "pending", "no_show"]


def is_junk_agency(name: str | None) -> bool:
    return bool(JUNK_AGENCY_NAME.search(str(name or "")))


async def find_targets(database, tenant_id: str, bookings_after: str) -> dict:
    agencies = [
        agency async for agency in database.agencies.find(
            {"tenant_id": tenant_id, "status": {"$ne": "inactive"}}, {"_id": 0, "id": 1, "name": 1, "status": 1}
        )
        if is_junk_agency(agency.get("name"))
    ]
    bookings = await database.bookings.find(
        {"tenant_id": tenant_id, "status": {"$in": ACTIVE_BOOKING_STATUSES},
         # Far-future arrivals, and stays left open for decades (e.g. 2026 → 2048).
         "$or": [{"check_in": {"$gte": bookings_after}}, {"check_out": {"$gte": bookings_after}}]},
        {"_id": 0, "id": 1, "check_in": 1, "check_out": 1, "status": 1, "room_number": 1},
    ).to_list(None)
    return {"agencies": agencies, "bookings": bookings}


async def apply_targets(database, tenant_id: str, targets: dict, run_id: str) -> dict:
    from core.atomic_booking import release_booking_nights
    from core.tenant_db import tenant_context

    now = datetime.now(UTC).isoformat()
    for agency in targets["agencies"]:
        await database.agencies.update_one(
            {"id": agency["id"], "tenant_id": tenant_id},
            {"$set": {"status": "inactive", "updated_at": now,
                      "cleanup": {"tag": CLEANUP_TAG, "run_id": run_id, "previous_status": agency.get("status"), "at": now}}},
        )
    released = 0
    for booking in targets["bookings"]:
        await database.bookings.update_one(
            {"id": booking["id"], "tenant_id": tenant_id},
            {"$set": {"status": "cancelled", "cancellation_reason": CLEANUP_TAG, "cancelled_at": now, "updated_at": now,
                      "cleanup": {"tag": CLEANUP_TAG, "run_id": run_id, "previous_status": booking.get("status"), "at": now}}},
        )
        with tenant_context(tenant_id):
            released += await release_booking_nights(tenant_id, booking["id"], reason=CLEANUP_TAG)
    return {"agencies": len(targets["agencies"]), "bookings": len(targets["bookings"]), "released_nights": released}


async def undo_run(database, tenant_id: str, run_id: str) -> dict:
    restored = 0
    async for agency in database.agencies.find({"tenant_id": tenant_id, "cleanup.run_id": run_id}, {"_id": 0, "id": 1, "cleanup": 1}):
        await database.agencies.update_one(
            {"id": agency["id"], "tenant_id": tenant_id},
            {"$set": {"status": agency["cleanup"].get("previous_status") or "active"}, "$unset": {"cleanup": ""}},
        )
        restored += 1
    bookings = await database.bookings.count_documents({"tenant_id": tenant_id, "cleanup.run_id": run_id})
    return {"agencies_restored": restored, "bookings_left_cancelled": bookings}


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--bookings-after", default="2035-01-01", help="Check-in on/after this date counts as test data")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", metavar="RUN_ID")
    args = parser.parse_args(argv)

    allowed = os.environ.get("ALLOW_TEST_DATA_DEACTIVATION", "").lower() == "true"
    if (args.apply or args.undo) and not allowed:
        logger.error("--apply/--undo için ALLOW_TEST_DATA_DEACTIVATION=true gerekli; hiçbir değişiklik yapılmadı.")
        return 2

    from core.tenant_db import get_system_db

    database = get_system_db()
    if args.undo:
        result = await undo_run(database, args.tenant_id, args.undo)
        logger.info("Geri alındı: %s", result)
        return 0

    targets = await find_targets(database, args.tenant_id, args.bookings_after)
    for agency in targets["agencies"]:
        logger.info("ACENTE  %s  %r  (%s)", agency["id"], agency.get("name"), agency.get("status"))
    for booking in targets["bookings"]:
        logger.info("REZERV  %s  oda %s  %s → %s  (%s)", booking["id"], booking.get("room_number"),
                    str(booking.get("check_in"))[:10], str(booking.get("check_out"))[:10], booking.get("status"))
    logger.info("Toplam: %d acente, %d rezervasyon", len(targets["agencies"]), len(targets["bookings"]))

    run_id = str(uuid.uuid4())
    summary = {"run_id": run_id, "tenant_id": args.tenant_id, "mode": "apply" if args.apply else "dry_run",
               "bookings_after": args.bookings_after, "found": {k: len(v) for k, v in targets.items()},
               "at": datetime.now(UTC).isoformat()}
    if args.apply:
        summary["applied"] = await apply_targets(database, args.tenant_id, targets, run_id)
        logger.info("Uygulandı (run_id=%s): %s", run_id, summary["applied"])
    else:
        logger.info("Kuru çalıştırma: değişiklik yapılmadı. Uygulamak için --apply kullanın.")
    await database.test_data_cleanup_runs.insert_one(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
