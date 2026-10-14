"""Period statements between a hotel and a marketplace agency.

A statement is an immutable snapshot of the agency's bookings at one hotel for
one period and currency, built from the PMS-refreshed ledger:

* stayed / active bookings earn the stay amount: the agency commission and the
  Syroce platform fee are computed on it;
* cancelled and no-show bookings earn the penalty of the contract's
  cancellation policy (snapshotted on the booking) and no commission.

Who owes whom depends on the booking's payment terms:

* ``on_arrival``: the guest pays the hotel, so the hotel owes the agency its
  commission;
* ``prepaid`` / ``net_*``: the agency collected from the guest, so it owes the
  hotel the net amount.

Penalties are always owed by the agency (it guarantees its bookings). The
platform fee is the agency's liability to Syroce and is reported, not netted.
"""

from __future__ import annotations

from datetime import date

NON_REVENUE = {"cancelled", "no_show"}


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def penalty_amount(row: dict, booking: dict | None) -> float:
    """Penalty for a cancelled / no-show booking under its cancellation policy."""
    policy = row.get("cancellation_policy") or {}
    total = _money(row.get("total_amount"))
    status = row.get("status")
    if status == "no_show":
        return round(total * _money(policy.get("no_show_penalty_pct", 100)) / 100, 2)
    if status != "cancelled":
        return 0.0
    cancelled_at = str((booking or {}).get("cancelled_at") or row.get("cancelled_at") or "")[:10]
    if not cancelled_at:
        return 0.0  # no evidence of a late cancellation: never invent a charge
    try:
        days_before = (date.fromisoformat(str(row.get("check_in"))[:10]) - date.fromisoformat(cancelled_at)).days
    except ValueError:
        return 0.0
    if days_before >= int(policy.get("free_until_days_before", 0) or 0):
        return 0.0
    return round(total * _money(policy.get("penalty_pct", 0)) / 100, 2)


def statement_line(row: dict, booking: dict | None) -> dict:
    status = row.get("status") or "confirmed"
    terms = row.get("payment_terms") or "on_arrival"
    line = {
        "booking_id": row.get("id"),
        "confirmation_code": row.get("confirmation_code"),
        "guest_name": row.get("guest_name"),
        "check_in": str(row.get("check_in") or "")[:10],
        "check_out": str(row.get("check_out") or "")[:10],
        "status": status,
        "payment_terms": terms,
        "stay_amount": _money(row.get("total_amount")),
    }
    if status in NON_REVENUE:
        penalty = penalty_amount(row, booking)
        line.update(gross=penalty, penalty=penalty, commission=0.0, platform_fee=0.0, net_to_hotel=penalty,
                    hotel_owes_agency=0.0, agency_owes_hotel=penalty)
        return line
    gross = line["stay_amount"]
    commission = round(gross * _money(row.get("commission_pct")) / 100, 2)
    platform_fee = round(gross * _money(row.get("syroce_b2b_fee_pct")) / 100, 2)
    net = round(gross - commission, 2)
    on_arrival = terms == "on_arrival"
    line.update(gross=gross, penalty=0.0, commission=commission, platform_fee=platform_fee, net_to_hotel=net,
                hotel_owes_agency=commission if on_arrival else 0.0,
                agency_owes_hotel=0.0 if on_arrival else net)
    return line


def statement_totals(lines: list[dict]) -> dict:
    keys = ("gross", "penalty", "commission", "platform_fee", "net_to_hotel", "hotel_owes_agency", "agency_owes_hotel")
    totals = {key: round(sum(_money(line.get(key)) for line in lines), 2) for key in keys}
    # Positive: the agency pays the hotel; negative: the hotel pays the agency.
    totals["net_balance"] = round(totals["agency_owes_hotel"] - totals["hotel_owes_agency"], 2)
    totals["bookings"] = sum(1 for line in lines if line["status"] not in NON_REVENUE)
    totals["cancelled"] = sum(1 for line in lines if line["status"] == "cancelled")
    totals["no_show"] = sum(1 for line in lines if line["status"] == "no_show")
    return totals


def outstanding(statement: dict) -> float:
    """Remaining amount after recorded payments, in the net_balance direction."""
    balance = _money((statement.get("totals") or {}).get("net_balance"))
    paid = 0.0
    for payment in statement.get("payments") or []:
        amount = _money(payment.get("amount"))
        paid += amount if payment.get("direction") == "agency_to_hotel" else -amount
    return round(balance - paid, 2)


async def build_statement(sysdb, *, tenant_id: str, agency_id: str, period_start: str, period_end: str, currency: str) -> dict:
    from core.marketplace_ledger_sync import refresh_ledger_from_pms

    rows = await sysdb.marketplace_bookings.find(
        {"tenant_id": tenant_id, "agency_id": agency_id, "check_in": {"$gte": period_start, "$lte": period_end + "T23:59:59"}},
        {"_id": 0},
    ).to_list(None)
    rows = await refresh_ledger_from_pms(sysdb, rows)
    rows = [row for row in rows if str(row.get("currency") or "TRY").upper() == currency]
    ids = [row["id"] for row in rows if row.get("id")]
    bookings = {}
    if ids:
        async for booking in sysdb.bookings.find(
            {"id": {"$in": ids}, "tenant_id": tenant_id}, {"_id": 0, "id": 1, "cancelled_at": 1, "no_show_at": 1}
        ):
            bookings[booking["id"]] = booking
    lines = sorted((statement_line(row, bookings.get(row.get("id"))) for row in rows), key=lambda line: (line["check_in"], line["confirmation_code"] or ""))
    return {"lines": lines, "totals": statement_totals(lines)}
