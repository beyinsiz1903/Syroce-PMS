"""Agency performance and receivables, per hotel–agency pair and currency.

Answers, for either party: where do I sell, who owes whom and since when,
what is waiting, and what is coming. Built from the same sources as the
statements so the numbers agree with them:

* performance, forward bookings and pickup from the agency ledger
  (refreshed from the PMS), the commission / net amounts from
  ``statement_line`` (the statement formula);
* receivables from open statements: agreed ones age from the agreement
  date plus the payment term (0 days for prepaid / pay at hotel, 7/15/30
  for net terms); statements not yet agreed by both are listed apart;
* "unbilled": stays already started that no statement contains yet.

Amounts are never summed across currencies. "Net to hotel" is the sales
amount after commission, not a profit.
"""

from __future__ import annotations

from datetime import date, timedelta

from core.agency_statements import NON_REVENUE, outstanding, statement_line

TERM_DAYS = {"net_7": 7, "net_15": 15, "net_30": 30}
FORWARD_WINDOWS = (30, 60, 90)
BUCKETS = ("not_due", "overdue_1_30", "overdue_31_60", "overdue_61_90", "overdue_90_plus")


def _day(value) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _nights(row: dict) -> int:
    start, end = _day(row.get("check_in")), _day(row.get("check_out"))
    return max(0, (end - start).days) if start and end else 0


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def due_date(statement: dict) -> date | None:
    """Agreement date + the longest payment term among its lines."""
    agreed = _day(statement.get("agreed_at"))
    if not agreed:
        return None
    days = max([TERM_DAYS.get(line.get("payment_terms"), 0) for line in statement.get("lines") or []] or [0])
    return agreed + timedelta(days=days)


def aging_bucket(due: date, today: date) -> str:
    late = (today - due).days
    if late <= 0:
        return "not_due"
    if late <= 30:
        return "overdue_1_30"
    if late <= 60:
        return "overdue_31_60"
    if late <= 90:
        return "overdue_61_90"
    return "overdue_90_plus"


def _empty_row(key: tuple, name: str | None) -> dict:
    party_id, currency = key
    return {
        "party_id": party_id, "party_name": name, "currency": currency,
        "performance": {"bookings": 0, "cancelled": 0, "room_nights": 0, "gross": 0.0, "commission": 0.0, "net_to_hotel": 0.0, "cancel_rate": 0.0},
        # Positive: the agency owes the hotel; each side shown separately.
        "receivables": {"agency_owes_hotel": 0.0, "hotel_owes_agency": 0.0, "awaiting_agreement": 0.0,
                        "aging": dict.fromkeys(BUCKETS, 0.0), "open_statements": 0,
                        "pending_notices": {"agency_to_hotel": 0.0, "hotel_to_agency": 0.0, "count": 0}},
        "unbilled": {"bookings": 0, "agency_owes_hotel": 0.0, "hotel_owes_agency": 0.0},
        "forward": {str(days): {"bookings": 0, "room_nights": 0, "gross": 0.0} for days in FORWARD_WINDOWS},
        "pickup_7d": {"bookings": 0, "gross": 0.0, "cancelled": 0},
    }


async def build_report(sysdb, *, side: str, scope: dict, period_start: str, period_end: str, today: date) -> dict:
    """``side``: whose view ("hotel" sees agencies, "agency" sees hotels);
    ``scope``: {"tenant_id": ...} or {"agency_id": ...}."""
    from core.marketplace_ledger_sync import refresh_ledger_from_pms

    party_key = "agency_id" if side == "hotel" else "tenant_id"
    name_key = "agency_name" if side == "hotel" else "hotel_name"
    rows: dict[tuple, dict] = {}
    names: dict[str, str] = {}

    def row_for(party_id: str, currency: str) -> dict:
        key = (party_id, (currency or "TRY").upper())
        if key not in rows:
            rows[key] = _empty_row(key, names.get(party_id))
        return rows[key]

    async for contract in sysdb.agency_contracts.find({**scope, "contract_code": {"$type": "string"}}, {"_id": 0, party_key: 1, name_key: 1}):
        if contract.get(party_key):
            names.setdefault(contract[party_key], contract.get(name_key))

    ledger = await sysdb.marketplace_bookings.find(scope, {"_id": 0}).to_list(None)
    ledger = await refresh_ledger_from_pms(sysdb, ledger)
    ids = [row["id"] for row in ledger if row.get("id")]
    pms = {}
    if ids:
        async for booking in sysdb.bookings.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "cancelled_at": 1, "no_show_at": 1}):
            pms[booking["id"]] = booking
    statements = await sysdb.agency_statements.find({**scope, "status": {"$ne": "void"}}, {"_id": 0}).to_list(None)
    billed = {line.get("booking_id") for statement in statements for line in statement.get("lines") or []}

    start, end = _day(period_start), _day(period_end)
    week_ago = today - timedelta(days=7)
    for booking in ledger:
        party = booking.get(party_key)
        if not party:
            continue
        names.setdefault(party, booking.get(name_key))
        row = row_for(party, booking.get("currency"))
        check_in = _day(booking.get("check_in"))
        cancelled = booking.get("status") in NON_REVENUE
        gross = _money(booking.get("total_amount"))
        line = statement_line(booking, pms.get(booking.get("id")))
        if check_in and start <= check_in <= end:
            perf = row["performance"]
            if booking.get("status") == "cancelled":
                perf["cancelled"] += 1
            else:
                perf["bookings"] += 1
                perf["room_nights"] += _nights(booking)
                perf["gross"] = round(perf["gross"] + gross, 2)
                perf["commission"] = round(perf["commission"] + _money(line.get("commission")), 2)
                perf["net_to_hotel"] = round(perf["net_to_hotel"] + _money(line.get("net_to_hotel")), 2)
        if check_in and check_in > today and not cancelled:
            for days in FORWARD_WINDOWS:
                if check_in <= today + timedelta(days=days):
                    window = row["forward"][str(days)]
                    window["bookings"] += 1
                    window["room_nights"] += _nights(booking)
                    window["gross"] = round(window["gross"] + gross, 2)
        created = _day(booking.get("created_at"))
        if created and created > week_ago:
            row["pickup_7d"]["bookings"] += 1
            row["pickup_7d"]["gross"] = round(row["pickup_7d"]["gross"] + gross, 2)
        cancelled_on = _day((pms.get(booking.get("id")) or {}).get("cancelled_at") or booking.get("cancelled_at"))
        if booking.get("status") == "cancelled" and cancelled_on and cancelled_on > week_ago:
            row["pickup_7d"]["cancelled"] += 1
        if check_in and check_in <= today and booking.get("id") not in billed:
            unbilled = row["unbilled"]
            owes, owed = _money(line.get("agency_owes_hotel")), _money(line.get("hotel_owes_agency"))
            if owes or owed:
                unbilled["bookings"] += 1
                unbilled["agency_owes_hotel"] = round(unbilled["agency_owes_hotel"] + owes, 2)
                unbilled["hotel_owes_agency"] = round(unbilled["hotel_owes_agency"] + owed, 2)

    for statement in statements:
        if statement.get("status") == "settled" or not statement.get(party_key):
            continue
        row = row_for(statement[party_key], statement.get("currency"))
        balance = outstanding(statement)
        receivables = row["receivables"]
        receivables["open_statements"] += 1
        if balance > 0:
            receivables["agency_owes_hotel"] = round(receivables["agency_owes_hotel"] + balance, 2)
        elif balance < 0:
            receivables["hotel_owes_agency"] = round(receivables["hotel_owes_agency"] - balance, 2)
        due = due_date(statement) if statement.get("status") == "agreed" else None
        if due is None:
            receivables["awaiting_agreement"] = round(receivables["awaiting_agreement"] + abs(balance), 2)
        elif abs(balance) >= 0.01:
            bucket = aging_bucket(due, today)
            receivables["aging"][bucket] = round(receivables["aging"][bucket] + abs(balance), 2)
        for notice in statement.get("payment_notices") or []:
            if notice.get("status") == "pending":
                direction = notice.get("direction") or "agency_to_hotel"
                receivables["pending_notices"][direction] = round(receivables["pending_notices"][direction] + _money(notice.get("amount")), 2)
                receivables["pending_notices"]["count"] += 1

    for row in rows.values():
        row["party_name"] = row["party_name"] or names.get(row["party_id"])
        perf = row["performance"]
        total = perf["bookings"] + perf["cancelled"]
        perf["cancel_rate"] = round(perf["cancelled"] / total, 4) if total else 0.0

    ordered = sorted(rows.values(), key=lambda row: (row["currency"], -row["performance"]["gross"], str(row["party_name"])))
    return {"side": side, "period_start": period_start, "period_end": period_end, "as_of": today.isoformat(),
            "rows": ordered, "totals": _totals(ordered)}


def _totals(rows: list[dict]) -> list[dict]:
    """Per currency sums of the numeric fields (never across currencies)."""
    by_currency: dict[str, dict] = {}

    def add(target: dict, source: dict) -> None:
        for key, value in source.items():
            if isinstance(value, dict):
                add(target.setdefault(key, {}), value)
            elif isinstance(value, (int, float)) and key != "cancel_rate":
                target[key] = round(target.get(key, 0) + value, 2)

    for row in rows:
        total = by_currency.setdefault(row["currency"], {"currency": row["currency"]})
        for section in ("performance", "receivables", "unbilled", "forward", "pickup_7d"):
            add(total.setdefault(section, {}), row[section])
    for total in by_currency.values():
        perf = total.get("performance", {})
        count = perf.get("bookings", 0) + perf.get("cancelled", 0)
        perf["cancel_rate"] = round(perf.get("cancelled", 0) / count, 4) if count else 0.0
    return list(by_currency.values())
