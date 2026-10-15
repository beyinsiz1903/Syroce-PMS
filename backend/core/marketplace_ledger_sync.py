"""Keep the cross-tenant agency ledger aligned with the PMS booking.

`marketplace_bookings` is written once when an agency reservation is created.
The hotel can later cancel, mark no-show, change dates or amount, check out or
collect payment directly in the PMS, and none of those paths write the ledger.
Reconciliation reads therefore refresh the ledger rows from the authoritative
PMS booking first, and persist the refreshed values so every later report,
export and credit view agrees with the PMS.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger("core.marketplace_ledger_sync")

# Statuses that earn no stay revenue; they are counted separately.
NON_REVENUE_STATUSES = frozenset({"cancelled", "no_show"})

_BOOKING_PROJECTION = {
    "_id": 0,
    "id": 1,
    "tenant_id": 1,
    "status": 1,
    "check_in": 1,
    "check_out": 1,
    "total_amount": 1,
    "payment_status": 1,
    "balance": 1,
    "agency_commission_rate": 1,
}


def _money(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def ledger_patch_from_booking(ledger: dict, booking: dict) -> dict:
    """Return ledger fields that differ from the PMS booking (empty if in sync)."""
    patch: dict = {}
    for field in ("status", "payment_status"):
        if booking.get(field) is not None and booking.get(field) != ledger.get(field):
            patch[field] = booking[field]
    for field in ("check_in", "check_out"):
        value = str(booking.get(field) or "")[:10]
        if value and value != str(ledger.get(field) or "")[:10]:
            patch[field] = value
    balance = _money(booking.get("balance"))
    if balance is not None and balance != _money(ledger.get("balance")):
        patch["balance"] = balance

    total = _money(booking.get("total_amount"))
    # An accepted modification rewrites the commission on the PMS booking;
    # statements and reports compute from the ledger's commission_pct.
    booking_pct = _money(booking.get("agency_commission_rate"))
    pct_changed = booking_pct is not None and booking_pct != _money(ledger.get("commission_pct"))
    if pct_changed:
        patch["commission_pct"] = booking_pct
    amount_changed = total is not None and total != _money(ledger.get("total_amount"))
    if amount_changed:
        patch["total_amount"] = total
    if amount_changed or pct_changed:
        effective_total = total if total is not None else _money(ledger.get("total_amount"))
        commission_pct = booking_pct if pct_changed else _money(ledger.get("commission_pct"))
        if commission_pct is not None and effective_total is not None:
            commission = round(effective_total * commission_pct / 100, 2)
            patch["commission_amount"] = commission
            patch["net_to_hotel"] = round(effective_total - commission, 2)
        fee_pct = _money(ledger.get("syroce_b2b_fee_pct"))
        if amount_changed and fee_pct is not None:
            patch["syroce_b2b_fee_amount"] = round(total * fee_pct / 100, 2)
    return patch


async def refresh_ledger_from_pms(sysdb, docs: list[dict]) -> list[dict]:
    """Return ``docs`` updated with the current PMS booking state.

    Rows whose PMS booking cannot be found are returned unchanged. A failed
    write-back is logged and never hides the refreshed values from the caller.
    """
    ids = [doc["id"] for doc in docs if doc.get("id")]
    if not ids:
        return docs
    live = {
        row["id"]: row
        async for row in sysdb.bookings.find({"id": {"$in": ids}}, _BOOKING_PROJECTION)
    }
    now = datetime.now(UTC).isoformat()
    refreshed: list[dict] = []
    for doc in docs:
        booking = live.get(doc.get("id"))
        if not booking or booking.get("tenant_id") != doc.get("tenant_id"):
            refreshed.append(doc)
            continue
        patch = ledger_patch_from_booking(doc, booking)
        if patch:
            try:
                await sysdb.marketplace_bookings.update_one(
                    {"id": doc["id"], "agency_id": doc.get("agency_id")},
                    {"$set": {**patch, "pms_synced_at": now}},
                )
            except Exception as exc:  # noqa: BLE001 - reporting must still answer
                logger.warning("Ledger sync write failed booking=%s error=%s", doc["id"], type(exc).__name__)
            doc = {**doc, **patch, "pms_synced_at": now}
        refreshed.append(doc)
    return refreshed


async def ledger_rows_for_period(sysdb, scope: dict, period_start: str, period_end: str) -> list[dict]:
    """Ledger rows whose *current PMS* check-in falls in [start, end] (dates).

    Period membership follows the authoritative PMS date: rows the ledger
    still files in the period but the PMS moved out are dropped, and rows
    moved into the period from elsewhere are found through the PMS booking.
    ``scope`` is ``{"tenant_id": ...}`` and/or ``{"agency_id": ...}``.
    """
    in_range = {"$gte": period_start, "$lte": period_end + "T23:59:59.999999"}
    rows = await sysdb.marketplace_bookings.find({**scope, "check_in": in_range}, {"_id": 0}).to_list(None)
    # Ledger rows filed outside the period whose PMS date may now be inside
    # it; look them up in the PMS by id (indexed), not by scanning bookings.
    outside = await sysdb.marketplace_bookings.find(
        {**scope, "check_in": {"$not": in_range}}, {"_id": 0, "id": 1}
    ).to_list(None)
    outside_ids = [row["id"] for row in outside if row.get("id")]
    if outside_ids:
        moved_in = [row["id"] async for row in sysdb.bookings.find(
            {"id": {"$in": outside_ids}, "check_in": in_range}, {"_id": 0, "id": 1})]
        if moved_in:
            rows += await sysdb.marketplace_bookings.find({**scope, "id": {"$in": moved_in}}, {"_id": 0}).to_list(None)
    rows = await refresh_ledger_from_pms(sysdb, rows)
    return [row for row in rows if period_start <= str(row.get("check_in") or "")[:10] <= period_end]
