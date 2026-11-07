"""Batched, tenant-scoped financial reads for operational dashboard alerts."""

import asyncio

from domains.pms.frontdesk_financials import calculate_departure_balance
from modules.pms_core.report_money import currency_code
from modules.pms_core.reporting_financials import is_valid_payment


async def load_operational_balances(database, tenant_id: str, bookings: list[dict], *, default_currency: str) -> dict[str, float]:
    """Include legacy folio-only rows without a per-reservation query loop.

    The booking's paid_amount is a cached counter, not a ledger. In particular,
    a fully prepaid stay may still owe extras or an additive room upgrade.
    Read failures deliberately propagate; never turn a missing ledger into an
    empty balance or an "all clear" dashboard.
    """
    booking_map = {booking["id"]: booking for booking in bookings}
    if not booking_map:
        return {}
    booking_ids = sorted(booking_map)
    folios = await database.folios.find(
        {"tenant_id": tenant_id, "booking_id": {"$in": booking_ids}},
        {"_id": 0, "id": 1, "booking_id": 1},
    ).to_list(None)
    folio_owners = {folio["id"]: folio["booking_id"] for folio in folios if folio.get("id")}
    selectors = [{"booking_id": {"$in": booking_ids}}]
    if folio_owners:
        selectors.append({"folio_id": {"$in": sorted(folio_owners)}})
    scope = {"tenant_id": tenant_id, "$or": selectors}

    async def read_rows(collection):
        return await collection.find(scope, {"_id": 0}).to_list(None)

    charges, payments, extras = await asyncio.gather(
        read_rows(database.folio_charges), read_rows(database.payments), read_rows(database.extra_charges),
    )
    grouped = []
    for index, rows in enumerate((charges, payments, extras)):
        by_booking = {booking_id: [] for booking_id in booking_ids}
        for row in rows:
            if row.get("voided") or (index == 1 and not is_valid_payment(row)):
                continue
            booking_id = row.get("booking_id")
            folio_booking_id = folio_owners.get(row.get("folio_id"))
            if booking_id and folio_booking_id and booking_id != folio_booking_id:
                raise ValueError("Financial row booking and folio ownership disagree")
            owner = booking_id or folio_booking_id
            if owner in by_booking:
                ledger_currency = currency_code(booking_map[owner].get("currency"), default_currency)
                # A foreign source amount must already be converted by its
                # posting path. Do not silently relabel malformed ledger rows.
                if row.get("currency") and currency_code(row["currency"]) != ledger_currency:
                    raise ValueError("Financial row currency requires reconciliation")
                by_booking[owner].append(row)
        grouped.append(by_booking)
    return {
        booking_id: round(calculate_departure_balance(
            grouped[0][booking_id], grouped[1][booking_id], grouped[2][booking_id],
            booking_total=booking.get("total_amount"),
        ), 2)
        for booking_id, booking in booking_map.items()
    }
