"""Read-only folio ledger snapshots shared by receivable and risk reports.

Stored folio balances are projections and can lag payments. Reports use posted
charges minus effective ledger offsets; cash collection is a different measure.
No live FX and no cancellation of one currency's debt with another's credit.
"""
from datetime import date, datetime

from modules.pms_core.report_money import add_amount, currency_code, rounded_totals, single_amount
from modules.pms_core.reporting_financials import deduplicate_report_payments, effective_folio_payment, is_valid_payment
from modules.pms_core.reporting_ledger import charge_amount


def iso_value(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def report_day(value):
    try:
        return date.fromisoformat(str(iso_value(value))[:10])
    except (TypeError, ValueError):
        return None


async def folio_snapshots(database, tenant_id, folios, *, fallback_currency, session=None):
    """Batch-read uncapped, tenant-scoped ledger data, including legacy rows."""
    ids = list({f["id"] for f in folios if f.get("id")})
    booking_ids = list({f["booking_id"] for f in folios if f.get("booking_id")})
    kwargs = {"session": session} if session is not None else {}
    bookings = await database.bookings.find({"tenant_id": tenant_id, "id": {"$in": booking_ids}}, {"_id": 0}, **kwargs).to_list(None) if booking_ids else []
    booking_map = {b["id"]: b for b in bookings}
    snapshots = {}
    for folio in folios:
        booking = booking_map.get(folio.get("booking_id"), {})
        code = currency_code(folio.get("currency") or booking.get("currency"), fallback_currency)
        snapshots[folio["id"]] = {"folio": folio, "booking": booking, "currency": code, "charges": [], "payments": [], "charges_by_currency": {}, "payments_by_currency": {}}
    if not ids:
        return snapshots
    async for row in database.folio_charges.find({"tenant_id": tenant_id, "folio_id": {"$in": ids}, "voided": {"$ne": True}}, {"_id": 0}, **kwargs):
        snap = snapshots[row["folio_id"]]
        code = currency_code(row.get("currency"), snap["currency"])
        amount = charge_amount(row)
        snap["charges"].append({**row, "currency": code, "total": amount})
        add_amount(snap["charges_by_currency"], code, amount)
    payments = await database.payments.find({"tenant_id": tenant_id, "folio_id": {"$in": ids}}, {"_id": 0}, **kwargs).to_list(None)
    for row in deduplicate_report_payments(payments):
        if not is_valid_payment(row):
            continue
        snap = snapshots[row["folio_id"]]
        code = currency_code(row.get("currency"), snap["currency"])
        amount = effective_folio_payment(row)
        snap["payments"].append({**row, "currency": code, "amount": amount})
        add_amount(snap["payments_by_currency"], code, amount)
    for snap in snapshots.values():
        charges, payments = snap["charges_by_currency"], snap["payments_by_currency"]
        # A source-PMS closing balance is neither new revenue nor a payment.
        # Keep it separate in the folio but include it in live debt settlement.
        from modules.pms_core.report_money import money

        opening = money(snap["folio"].get("opening_balance") or 0)
        snap["opening_by_currency"] = {snap["currency"]: opening} if opening else {}
        snap["balance_by_currency"] = rounded_totals({code: charges.get(code, 0) - payments.get(code, 0) + (opening if code == snap["currency"] else 0)
                                                     for code in charges.keys() | payments.keys() | snap["opening_by_currency"].keys()})
        snap["charges_by_currency"] = rounded_totals(charges)
        snap["payments_by_currency"] = rounded_totals(payments)
    return snapshots


async def receivable_rows(database, tenant_id, as_of_day, *, fallback_currency, company_id=None):
    query = {"tenant_id": tenant_id, "status": "open"}
    if company_id:
        query["company_id"] = company_id
    folios = await database.folios.find(query, {"_id": 0}).to_list(None)
    snapshots = await folio_snapshots(database, tenant_id, folios, fallback_currency=fallback_currency)
    rows = []
    for snap in snapshots.values():
        balances = {code: amount for code, amount in snap["balance_by_currency"].items() if amount > 0}
        if not balances:
            continue
        folio, booking = snap["folio"], snap["booking"]
        checkout = report_day(booking.get("check_out"))
        days = max((as_of_day - checkout).days, 0) if checkout else 0
        code = next(iter(balances)) if len(balances) == 1 else None
        rows.append({"folio_id": folio["id"], "folio_number": folio.get("folio_number"), "booking_id": folio.get("booking_id"),
                     "company_id": folio.get("company_id"), "guest_id": booking.get("guest_id"),
                     "guest_name": booking.get("guest_name") or folio.get("guest_name") or "—", "room_number": booking.get("room_number") or folio.get("room_number"),
                     "reservation_number": booking.get("reservation_number") or booking.get("confirmation_number"), "check_in": iso_value(booking.get("check_in")),
                     "checkout_date": checkout.isoformat() if checkout else None, "days_overdue": days, "is_overdue": days > 0,
                     "created_at": iso_value(folio.get("created_at")), "balance": single_amount(balances), "currency": code,
                     "balance_by_currency": balances, "mixed_currency": len(balances) > 1,
                     "manual_collection_allowed": snap["currency"] == "TRY" and all(code == "TRY" or amount == 0 for code, amount in snap["balance_by_currency"].items()),
                     "ledger_payment_count": len(snap["payments"]), "balance_basis": "posted_folio_ledger"})
    # Age is comparable; nominal amounts in different currencies are not.
    return sorted(rows, key=lambda row: (-row["days_overdue"], str(row["created_at"] or ""), row["folio_id"]))


def row_totals(rows, field="balance_by_currency"):
    totals = {}
    for row in rows:
        for code, amount in row.get(field, {}).items():
            add_amount(totals, code, amount)
    return rounded_totals(totals)


def outstanding_invoice(invoice):
    """Document debt, not its gross original amount or a failed payment."""
    from modules.pms_core.report_money import money, rounded

    status = str(invoice.get("status") or "pending").lower()
    if status in {"cancelled", "canceled", "void", "voided", "draft", "paid"} or invoice.get("voided"):
        return 0.0
    total = money(invoice.get("total") or 0)
    paid = money(invoice.get("amount_paid") if invoice.get("amount_paid") is not None else invoice.get("paid_amount") or 0)
    return rounded(max(total - paid, 0))
