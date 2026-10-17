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

The hotel may correct one line with a signed amount and a reason
(``apply_adjustment``): positive = the agency owes the hotel more, negative =
less. The computed values are kept on the line, so a correction can be
changed or removed and is always visible.
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


def apply_adjustment(line: dict, amount: float, reason: str, *, actor: str | None = None, at: str | None = None) -> dict:
    """Correct a line by a signed amount (0 removes the correction)."""
    previous = line.get("adjustment") or {}
    base = previous.get("computed") or {"agency_owes_hotel": _money(line.get("agency_owes_hotel")),
                                        "hotel_owes_agency": _money(line.get("hotel_owes_agency"))}
    amount = _money(amount)
    balance = round(base["agency_owes_hotel"] - base["hotel_owes_agency"] + amount, 2)
    line = {k: v for k, v in line.items() if k != "adjustment"}
    line["agency_owes_hotel"] = balance if balance > 0 else 0.0
    line["hotel_owes_agency"] = -balance if balance < 0 else 0.0
    if abs(amount) >= 0.01:
        line["adjustment"] = {"amount": amount, "reason": reason.strip(), "by": actor, "at": at, "computed": base}
    return line


def hotel_agreed(statement: dict) -> bool:
    """The hotel agreed to the statement's current revision (statements
    from before agreements were tracked were issued by the hotel)."""
    agreements = statement.get("agreements")
    if not isinstance(agreements, dict):
        return True
    return agreements.get("hotel") == (statement.get("revision") or 1)


def credit_view(statement: dict) -> dict:
    """The statement as the hotel's credit control may trust it: a
    correction that lowers the agency's debt counts only once the hotel
    agreed to it (the hotel made it, or agreed to that revision). Without
    this an agency could free its own credit limit by proposing a discount."""
    if hotel_agreed(statement):
        return statement
    lines = []
    for line in statement.get("lines") or []:
        adjustment = line.get("adjustment") or {}
        untrusted = adjustment and adjustment.get("side") != "hotel" and float(adjustment.get("amount") or 0) < 0
        if untrusted and adjustment.get("computed"):
            line = {**{k: v for k, v in line.items() if k != "adjustment"}, **adjustment["computed"]}
        lines.append(line)
    return {**statement, "lines": lines, "totals": statement_totals(lines)}


def statement_totals(lines: list[dict]) -> dict:
    keys = ("gross", "penalty", "commission", "platform_fee", "net_to_hotel", "hotel_owes_agency", "agency_owes_hotel")
    totals = {key: round(sum(_money(line.get(key)) for line in lines), 2) for key in keys}
    totals["adjustments"] = round(sum(_money((line.get("adjustment") or {}).get("amount")) for line in lines), 2)
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


def settled_by_booking(statement: dict) -> dict[str, float]:
    """How much of each booking's debt to the hotel this statement has cleared.

    Clearing credit = commissions the hotel owes the agency on the same
    statement (set off) + agency payments - hotel payments. It is applied to
    the lines the agency owes, in statement order, so partial payments clear
    the oldest stays first and a settled statement clears every line.
    """
    if statement.get("status") == "void":
        return {}
    totals = statement.get("totals") or {}
    credit = _money(totals.get("hotel_owes_agency"))
    for payment in statement.get("payments") or []:
        amount = _money(payment.get("amount"))
        credit += amount if payment.get("direction") == "agency_to_hotel" else -amount
    cleared: dict[str, float] = {}
    for line in statement.get("lines") or []:
        owed = _money(line.get("agency_owes_hotel"))
        booking_id = line.get("booking_id")
        if owed <= 0 or not booking_id or credit <= 0:
            continue
        portion = round(min(owed, credit), 2)
        cleared[booking_id] = round(cleared.get(booking_id, 0.0) + portion, 2)
        credit = round(credit - portion, 2)
    return cleared


async def build_statement(sysdb, *, tenant_id: str, agency_id: str, period_start: str, period_end: str, currency: str) -> dict:
    from core.marketplace_ledger_sync import ledger_rows_for_period

    rows = await ledger_rows_for_period(sysdb, {"tenant_id": tenant_id, "agency_id": agency_id}, period_start, period_end)
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
