"""Recompute reservation balance / payment status for records paid before #1320.

Since #1320 every payment path refreshes ``bookings.balance``,
``payment_status`` and ``collected_amount`` from the reservation's payments
(``core.booking_payment_state``). Reservations paid earlier keep the stale
values until their next payment event: e.g. paid 8.000 in cash, still
``balance: 8000, payment_status: pending``. PMS lists, reports and the agency
ledger read those fields.

What it does
------------
For every reservation that has at least one payment row it derives the three
fields exactly as a payment would and writes only the ones that differ. The
previous values are kept on the booking (``payment_state_backfill``) so a run
can be undone. Nothing else is touched; no payment, folio or ledger row is
written.

Safety contract
---------------
* ``--tenant-id`` (repeatable) or ``--all-tenants`` is mandatory.
* Default is a dry run that prints every reservation that would change.
* ``--apply`` / ``--undo`` additionally require
  ``ALLOW_PAYMENT_STATE_BACKFILL=true``.
* Every run writes a summary to ``booking_payment_state_backfill_runs``.

Usage
-----
    python -m scripts.backfill_booking_payment_state --tenant-id <id>
    python -m scripts.backfill_booking_payment_state --all-tenants
    ALLOW_PAYMENT_STATE_BACKFILL=true python -m scripts.backfill_booking_payment_state --all-tenants --apply
    ALLOW_PAYMENT_STATE_BACKFILL=true python -m scripts.backfill_booking_payment_state --all-tenants --undo <run_id>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_booking_payment_state")

FIELDS = ("balance", "payment_status", "collected_amount")


def changed_fields(current: dict, fresh: dict) -> dict:
    """The derived fields whose stored value differs from the fresh one."""
    diff = {}
    for key in FIELDS:
        old, new = current.get(key), fresh.get(key)
        if isinstance(new, (int, float)) and not isinstance(new, bool):
            try:
                same = old is not None and abs(float(old) - float(new)) < 0.01
            except (TypeError, ValueError):
                same = False
        else:
            same = old == new
        if not same:
            diff[key] = new
    return diff


async def tenants_with_payments(database) -> list[str]:
    return sorted(t for t in await database.payments.distinct("tenant_id") if t)


async def plan_tenant(database, tenant_id: str) -> list[dict]:
    """Reservations of one tenant whose stored payment state is stale."""
    from core.booking_payment_state import PAYMENT_FIELDS, compute_booking_payment_state
    from core.tenant_db import tenant_context

    payments: dict[str, list[dict]] = {}
    async for row in database.payments.find({"tenant_id": tenant_id, "booking_id": {"$nin": [None, ""]}},
                                            {**PAYMENT_FIELDS, "booking_id": 1}):
        payments.setdefault(row["booking_id"], []).append(row)
    plan = []
    for booking_id, rows in payments.items():
        booking = await database.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            continue
        try:
            with tenant_context(tenant_id):
                fresh = await compute_booking_payment_state(database, tenant_id, booking, rows)
        except Exception as exc:  # noqa: BLE001 - one bad record must not stop the run
            logger.warning("ATLANDI  %s  %s: %s", tenant_id, booking_id, type(exc).__name__)
            continue
        diff = changed_fields(booking, fresh)
        if diff:
            plan.append({"tenant_id": tenant_id, "booking_id": booking_id, "code": booking.get("confirmation_code"),
                         "previous": {key: booking.get(key) for key in FIELDS}, "set": diff})
    return plan


async def apply_plan(database, plan: list[dict], run_id: str) -> int:
    now = datetime.now(UTC).isoformat()
    written = 0
    for item in plan:
        result = await database.bookings.update_one(
            {"id": item["booking_id"], "tenant_id": item["tenant_id"]},
            {"$set": {**item["set"], "payment_state_backfill": {"run_id": run_id, "previous": item["previous"], "at": now}}},
        )
        written += getattr(result, "modified_count", 1)
    return written


async def undo_run(database, tenant_ids: list[str] | None, run_id: str) -> int:
    query: dict = {"payment_state_backfill.run_id": run_id}
    if tenant_ids:
        query["tenant_id"] = {"$in": tenant_ids}
    restored = 0
    async for booking in database.bookings.find(query, {"_id": 0, "id": 1, "tenant_id": 1, "payment_state_backfill": 1}):
        previous = booking["payment_state_backfill"].get("previous") or {}
        restore = {key: previous[key] for key in FIELDS if previous.get(key) is not None}
        unset = {key: "" for key in FIELDS if previous.get(key) is None}
        update: dict = {"$unset": {**unset, "payment_state_backfill": ""}}
        if restore:
            update["$set"] = restore
        await database.bookings.update_one({"id": booking["id"], "tenant_id": booking["tenant_id"]}, update)
        restored += 1
    return restored


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--tenant-id", action="append", dest="tenant_ids")
    scope.add_argument("--all-tenants", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", metavar="RUN_ID")
    args = parser.parse_args(argv)

    allowed = os.environ.get("ALLOW_PAYMENT_STATE_BACKFILL", "").lower() == "true"
    if (args.apply or args.undo) and not allowed:
        logger.error("--apply/--undo için ALLOW_PAYMENT_STATE_BACKFILL=true gerekli; hiçbir değişiklik yapılmadı.")
        return 2

    from core.tenant_db import get_system_db

    database = get_system_db()
    if args.undo:
        restored = await undo_run(database, args.tenant_ids, args.undo)
        logger.info("Geri alındı: %d rezervasyon (run_id=%s)", restored, args.undo)
        return 0

    tenant_ids = args.tenant_ids or await tenants_with_payments(database)
    plan: list[dict] = []
    for tenant_id in tenant_ids:
        tenant_plan = await plan_tenant(database, tenant_id)
        for item in tenant_plan:
            logger.info("REZERV  %s  %s  %s → %s", tenant_id, item["code"] or item["booking_id"],
                        {k: item["previous"][k] for k in item["set"]}, item["set"])
        plan.extend(tenant_plan)
    logger.info("Toplam: %d otel tarandı, %d rezervasyon güncellenecek", len(tenant_ids), len(plan))

    run_id = str(uuid.uuid4())
    summary = {"run_id": run_id, "mode": "apply" if args.apply else "dry_run", "tenants": len(tenant_ids),
               "found": len(plan), "at": datetime.now(UTC).isoformat()}
    if args.apply:
        summary["applied"] = await apply_plan(database, plan, run_id)
        logger.info("Uygulandı (run_id=%s): %d rezervasyon", run_id, summary["applied"])
    else:
        logger.info("Kuru çalıştırma: değişiklik yapılmadı. Uygulamak için --apply kullanın.")
    await database.booking_payment_state_backfill_runs.insert_one(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
