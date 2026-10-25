"""Explicit, source-day TRY valuation and append-only operational corrections.

No current-rate lookup, receipt-rate inversion, source mutation or arbitrary
journal input. A correction is ONE balanced entry: contra of the old posting
and the newly valued source lines together. A failed insert can never leave a
standalone reversal behind. The old posting core remains untouched.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from modules.pms_core.report_money import resolve_ledger_currencies
from modules.pms_core.reporting_financials import deduplicate_report_payments, effective_collection, effective_folio_payment, is_non_cash_adjustment, report_payment_period_match
from shared_kernel.gl_posting import GLPostingError, normalize_journal_lines, post_journal_entry, verify_journal_entry_hash


class OperationalValuationError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()).hexdigest()


def minor(value):
    try:
        number = Decimal(str(value if value is not None else 0))
        if not number.is_finite():
            raise ValueError
        return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise OperationalValuationError("Invalid source monetary amount") from exc


def amount(value):
    return float(Decimal(value) / 100)


def normalized_valuation(business_date, valuation):
    try:
        if date.fromisoformat(business_date).isoformat() != business_date:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise OperationalValuationError("Invalid source business date") from exc
    if valuation.get("business_date") != business_date or valuation.get("base_currency") != "TRY":
        raise OperationalValuationError("Valuation must belong to this source day and use TRY")
    reference = str(valuation.get("reference") or "").strip()
    if not 3 <= len(reference) <= 240:
        raise OperationalValuationError("An explicit source-day rate reference is required")
    rates = {"TRY": "1"}
    for code, value in sorted((valuation.get("rates_to_try") or {}).items()):
        if code == "TRY" and str(value) == "1":
            continue  # Rebuild an already normalized immutable manifest.
        if code not in {"USD", "EUR", "GBP", "CHF"}:
            raise OperationalValuationError("Unsupported source valuation currency: " + str(code))
        try:
            rate = Decimal(str(value))
            if not rate.is_finite() or not 0 < rate <= 1000000 or rate != rate.quantize(Decimal(".000001")):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise OperationalValuationError("Source rates must be positive, finite and at most six decimals") from exc
        rates[code] = format(rate.normalize(), "f")
    return {"business_date": business_date, "base_currency": "TRY", "reference": reference, "rates_to_try": rates}


async def daily_sources(db, tenant_id, business_date):
    charges = await db.folio_charges.find({"tenant_id": tenant_id, "voided": {"$ne": True},
        **report_payment_period_match(business_date, business_date, date_fields=("date", "charge_date", "posted_at", "created_at"))}, {"_id": 0}).to_list(None)
    payments = await db.payments.find({"tenant_id": tenant_id, "voided": {"$ne": True},
        **report_payment_period_match(business_date, business_date)}, {"_id": 0}).to_list(None)
    charges = [r for r in charges if not r.get("deleted") and not r.get("voided")
        and str(r.get("charge_category") or r.get("category") or "").strip().lower() not in {"split_adjustment", "opening_balance"}
        and (minor(r.get("total", r.get("amount"))) or minor(r.get("tax_amount")))]
    payments = [r for r in deduplicate_report_payments(payments) if (effective_collection(r) or (is_non_cash_adjustment(r) and effective_folio_payment(r)))
        and not (r.get("mice_event_id") and r.get("gl_journal_entry_id"))]
    security = await db.security_fund_operations.find({"tenant_id": tenant_id, "business_date": business_date}).to_list(None)
    fund_ids = sorted({r["fund_id"] for r in security})
    funds = await db.security_funds.find({"tenant_id": tenant_id, "id": {"$in": fund_ids}}, {"_id": 0}).to_list(None) if fund_ids else []
    fund_map = {r["id"]: r for r in funds}
    for row in security:
        fund = fund_map.get(row["fund_id"])
        if not fund or fund["currency"] != row["currency"] or fund["booking_id"] != row["booking_id"]:
            raise OperationalValuationError("Security operation has no consistent tenant-scoped liability source")
        row["id"], row["method"] = str(row["_id"]), fund["method"]
        # Foreign held funds carry the rate sealed on their receipt day. A
        # different settlement-day rate requires realised FX lines, not a
        # silent change in the liability's carrying amount.
        if row["currency"] != "TRY" and row["action"] != "received" and fund["business_date"] != business_date:
            receipt_entry = await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "status": "posted",
                "source_manifest.sources": {"$elemMatch": {"kind": "security", "fund_id": fund["id"], "action": "received"}}}, {"_id": 0})
            if not receipt_entry or not verify_journal_entry_hash(receipt_entry):
                raise OperationalValuationError("Value the foreign security receipt day before its later application/refund")
            row["receipt_rate_to_try"] = receipt_entry["source_manifest"]["valuation"]["rates_to_try"][row["currency"]]
    return (await resolve_ledger_currencies(charges, tenant_id, database=db, fallback_currency="UNKNOWN"),
            await resolve_ledger_currencies(payments, tenant_id, database=db, fallback_currency="UNKNOWN"), security)


def build_plan(charges, payments, mapping, valuation, security=()):
    """Deterministic source/FX/account snapshot; no access to a clock or DB."""
    from core.integrations.operational_gl_bridge import _payment_account

    rates = valuation["rates_to_try"]
    rows, charge_groups, payment_groups = [], {}, {}
    payment_base_groups, adjustment_groups = {}, {}
    for kind, sources in (("charge", charges), ("payment", payments)):
        for source in sources:
            code = "TRY" if source["currency"] in {"TL", "TRL"} else source["currency"]
            if code not in rates:
                raise OperationalValuationError("Source-day TRY valuation required before GL posting: " + code)
            if not source.get("id"):
                raise OperationalValuationError("Stable source IDs are required for valued posting")
            row = {"kind": kind, "id": str(source["id"]), "currency": code,
                   "folio_id": source.get("folio_id"), "booking_id": source.get("booking_id")}
            if kind == "payment" and is_non_cash_adjustment(source):
                payment_type = str(source.get("payment_type") or "").strip().lower()
                if payment_type not in {"discount", "comp_adjustment", "rate_correction"}:
                    raise OperationalValuationError("Unsupported non-cash adjustment type: " + payment_type)
                if not mapping.get("adjustment_account_code"):
                    raise OperationalValuationError("An explicit non-cash sales-adjustment account is required")
                if mapping["adjustment_account_code"] in {value for key, value in mapping.items()
                        if key.endswith("_account_code") and key != "adjustment_account_code"}:
                    raise OperationalValuationError("Non-cash sales adjustments require a separate contra-sales account")
                value = minor(effective_folio_payment(source))
                if not value:
                    raise OperationalValuationError("A non-cash adjustment must have a signed amount")
                row.update(kind="adjustment", amount_minor=value, payment_type=payment_type,
                    concession_id=source.get("concession_id"), charge_ids=sorted(source.get("charge_ids") or []))
                adjustment_groups[code] = adjustment_groups.get(code, 0) + value
                rows.append(row)
                continue
            if kind == "charge":
                if source.get("tax_amount") is None:
                    raise OperationalValuationError("Unknown source tax must be resolved, not assumed zero: " + row["id"])
                gross, tax = minor(source.get("total", source.get("amount"))), minor(source["tax_amount"])
                if (gross >= 0 and not 0 <= tax <= gross) or (gross < 0 and not gross <= tax <= 0):
                    raise OperationalValuationError("Source tax is outside its signed charge total")
                breakdown = source.get("tax_breakdown") or {}
                if not isinstance(breakdown, dict):
                    raise OperationalValuationError("Invalid source tax breakdown")
                accommodation = minor(breakdown.get("accommodation_tax"))
                if breakdown and (set(breakdown) - {"vat", "accommodation_tax"} or minor(breakdown.get("vat")) + accommodation != tax):
                    raise OperationalValuationError("Unsupported or inconsistent source tax breakdown")
                if breakdown and ((tax >= 0 and (minor(breakdown.get("vat")) < 0 or accommodation < 0))
                                  or (tax < 0 and (minor(breakdown.get("vat")) > 0 or accommodation > 0))):
                    raise OperationalValuationError("Source tax components must have the signed tax direction")
                if accommodation and not mapping.get("accommodation_tax_account_code"):
                    raise OperationalValuationError("An explicit accommodation-tax account is required; do not merge it into VAT")
                row.update(gross_minor=gross, tax_minor=tax, accommodation_tax_minor=accommodation)
                group = charge_groups.setdefault(code, [0, 0, 0])
                group[0] += gross
                group[1] += tax
                group[2] += accommodation
            else:
                method = str(source.get("method") or source.get("payment_method") or "").strip().lower()
                if method not in {"cash", "nakit", "card", "credit_card", "debit_card", "kredi_karti", "pos", "bank", "bank_transfer", "transfer", "online", "eft", "wire", "havale"}:
                    raise OperationalValuationError("Unmapped collection method: " + method)
                paid = minor(effective_collection(source))
                base_paid = int((Decimal(paid) * Decimal(rates[code])).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                row.update(amount_minor=paid, method=method)
                # An immutable actual TRY receipt must agree with the proposed
                # source-day valuation. A realised FX difference needs its own
                # gain/loss accounting; never bury it in sales or round it away.
                if source.get("reporting_amount") is not None:
                    if source.get("reporting_currency") != "TRY" or source.get("exchange_rate_date") != valuation["business_date"]:
                        raise OperationalValuationError("Receipt TRY snapshot is not bound to this source day")
                    receipt = abs(minor(source["reporting_amount"])) * (1 if paid > 0 else -1)
                    if receipt != base_paid:
                        raise OperationalValuationError("Receipt/source valuation difference requires explicit realised FX accounting")
                    row.update(reporting_amount_minor=receipt, received_currency=source.get("received_currency"),
                               received_amount_minor=minor(source["received_amount"]) if source.get("received_amount") is not None else None)
                account = _payment_account(mapping, method)
                payment_groups[(code, account)] = payment_groups.get((code, account), 0) + paid
                payment_base_groups[(code, account)] = payment_base_groups.get((code, account), 0) + base_paid
            rows.append(row)
    lines = []

    def line(account, native, code, side, memo, base=None):
        if not native:
            return
        rate = Decimal(rates[code])
        base = int((Decimal(native) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if base is None else base
        if not base:
            raise OperationalValuationError("Source valuation rounds a non-zero amount to zero")
        value = {"account_code": account, (side if base > 0 else ("credit" if side == "debit" else "debit")): amount(abs(base)), "memo": memo}
        if code != "TRY":
            value.update(currency=code, foreign_amount=amount(abs(native)), exchange_rate=rates[code])
        lines.append(value)

    charge_total, payment_total, adjustment_total = 0, 0, 0
    payment_by_account, security_by_account = {}, {}
    for code, (gross, tax, accommodation) in sorted(charge_groups.items()):
        rate = Decimal(rates[code])
        base_gross, base_tax, base_accommodation = [int((Decimal(n) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) for n in (gross, tax, accommodation)]
        line(mapping["receivable_account_code"], gross, code, "debit", "Günlük folyo tahakkuku", base_gross)
        line(mapping["revenue_account_code"], gross - tax, code, "credit", "Günlük PMS net geliri", base_gross - base_tax)
        line(mapping["tax_account_code"], tax - accommodation, code, "credit", "Kaynakta kayıtlı KDV / genel vergi", base_tax - base_accommodation)
        if accommodation:
            line(mapping["accommodation_tax_account_code"], accommodation, code, "credit", "Kaynakta kayıtlı konaklama vergisi", base_accommodation)
        charge_total += base_gross
    for (code, account), paid in sorted(payment_groups.items()):
        base_paid = payment_base_groups[(code, account)]
        if not paid and base_paid:
            raise OperationalValuationError("Net-zero foreign receipts have a TRY rounding difference requiring explicit accounting")
        line(account, paid, code, "debit", "Günlük tahsilat / iade", base_paid)
        line(mapping["receivable_account_code"], paid, code, "credit", "Folyo tahsilat kapaması", base_paid)
        payment_total += base_paid
        payment_by_account[account] = payment_by_account.get(account, 0) + base_paid
    # Folio offsets are not receipts or a fiscal credit note. Preserve the
    # original charge/tax rows; post a distinct contra-sales/receivable pair.
    for code, value in sorted(adjustment_groups.items()):
        line(mapping["adjustment_account_code"], value, code, "debit", "İkram/indirim; tahsilat değildir")
        line(mapping["receivable_account_code"], value, code, "credit", "Nakit dışı folyo alacak kapaması")
        adjustment_total += int((Decimal(value) * Decimal(rates[code])).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    for movement in security:
        code = movement["currency"]
        if code not in rates:
            raise OperationalValuationError("Source-day TRY valuation required before GL posting: " + code)
        if movement.get("receipt_rate_to_try") and Decimal(movement["receipt_rate_to_try"]) != Decimal(rates[code]):
            raise OperationalValuationError("Foreign security settlement needs explicit realised FX accounting")
        liability = mapping.get("security_deposit_account_code")
        if not liability:
            raise OperationalValuationError("An explicit refundable security-deposit liability account is required")
        native, action = movement["amount_minor"], movement["action"]
        if isinstance(native, bool) or not isinstance(native, int) or native <= 0 or action not in {"received", "refund", "apply"}:
            raise OperationalValuationError("Invalid immutable security movement")
        method = movement["method"]
        if method not in {"cash", "card", "bank_transfer"}:
            raise OperationalValuationError("Unmapped security receipt method")
        target = mapping["receivable_account_code"] if action == "apply" else _payment_account(mapping, method)
        line(liability, native, code, "credit" if action == "received" else "debit", "İade edilebilir güvence yükümlülüğü")
        line(target, native, code, "debit" if action == "received" else "credit", "Güvence " + action + "; satış geliri değildir")
        if action != "apply":
            base = int((Decimal(native) * Decimal(rates[code])).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * (1 if action == "received" else -1)
            security_by_account[target] = security_by_account.get(target, 0) + base
        rows.append({"kind": "security", "id": movement["id"], "currency": code,
            "amount_minor": native, "action": action, "method": method,
            "fund_id": movement["fund_id"], "booking_id": movement["booking_id"], "folio_id": movement.get("folio_id")})
    if len({(r["kind"], r["id"]) for r in rows}) != len(rows):
        raise OperationalValuationError("Duplicate canonical source ID")
    if lines:
        try:
            normalize_journal_lines(lines)
        except GLPostingError as exc:
            raise OperationalValuationError(str(exc)) from exc
    # An optional new mapping must not invalidate previously sealed days that
    # contain no adjustment. Include it only when this source batch uses it.
    manifest = {"version": 1, "valuation": valuation, "mapping": {k: mapping[k] for k in sorted(mapping)
                if k.endswith("_account_code") and (k != "adjustment_account_code" or adjustment_groups)},
                "sources": sorted(rows, key=lambda r: (r["kind"], r["id"]))}
    manifest["source_hash"] = digest(manifest)
    return {"lines": lines, "manifest": manifest, "charge_total_try": amount(charge_total), "payment_total_try": amount(payment_total),
            "payment_by_account_minor": payment_by_account, "security_settlement_by_account_minor": security_by_account,
            "adjustment_total_try": amount(adjustment_total)}


async def preview_daily_valuation(db, tenant_id, run_id, valuation):
    from core.integrations.operational_gl_bridge import get_operational_mapping

    run = await db.night_audit_runs.find_one({"tenant_id": tenant_id, "id": run_id, "status": "completed"}, {"_id": 0})
    if not run:
        raise OperationalValuationError("Completed source night audit not found")
    mapping = await get_operational_mapping(db, tenant_id)
    if not mapping["enabled"] or not mapping["auto_night_audit"]:
        raise OperationalValuationError("Operational night-audit mapping is disabled")
    normalized = normalized_valuation(run["business_date"], valuation)
    charges, payments, security = await daily_sources(db, tenant_id, run["business_date"])
    plan = build_plan(charges, payments, mapping, normalized, security)
    by_key = await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "idempotency_key": "operational-daily:" + run["business_date"]}, {"_id": 0})
    candidates = await db.gl_journal_entries.find({"tenant_id": tenant_id, "source": "night_audit", "source_ref": run_id}, {"_id": 0}).to_list(2)
    if len(candidates) > 1:
        raise OperationalValuationError("Multiple original source journals; reconcile duplicates before any correction")
    original = candidates[0] if candidates else by_key
    if by_key and original and by_key["id"] != original["id"]:
        raise OperationalValuationError("Source journal idempotency/link conflict")
    if run.get("gl_journal_entry_id") and (not original or original["id"] != run["gl_journal_entry_id"]):
        raise OperationalValuationError("Source run has a different or dangling journal link")
    correction = await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "idempotency_key": "operational-correction:" + run_id}, {"_id": 0})
    if original and (original.get("source") != "night_audit" or original.get("source_ref") != run_id or not verify_journal_entry_hash(original)):
        raise OperationalValuationError("Original source journal link/integrity mismatch")
    if original and not plan["manifest"]["sources"] and any(minor(row.get("debit")) or minor(row.get("credit")) for row in original.get("lines", [])):
        # Missing source history is not proof that an old posted receipt or
        # revenue never happened. Do not erase it via an empty-source contra.
        raise OperationalValuationError("Source history missing for nonzero original journal; manual source reconciliation required")
    if original and (original.get("reversal_status") or original.get("reverses_entry_id") or
                     await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "reverses_entry_id": original["id"]}, {"id": 1})):
        raise OperationalValuationError("Original journal already reversed; manual reconciliation required")
    if correction and (not original or correction.get("source") != "night_audit_correction" or correction.get("source_ref") != run_id
                       or correction.get("date") != run["business_date"] or correction.get("reversal_status")
                       or correction.get("memo") != "Bağlı kaynak düzeltmesi " + original["id"] + " — " + plan["manifest"]["source_hash"]
                       or await db.gl_journal_entries.find_one({"tenant_id": tenant_id, "reverses_entry_id": correction["id"]}, {"id": 1})
                       or not verify_journal_entry_hash(correction) or correction.get("source_manifest") != plan["manifest"]):
        raise OperationalValuationError("Posted correction differs from current sources/valuation; manual reconciliation required")
    if original and original.get("source_manifest") == plan["manifest"]:
        action = "already_posted"
    else:
        action = "already_corrected" if correction else "correct" if original else "post" if plan["lines"] else "no_activity"
    posting_lines = list(plan["lines"])
    if action == "correct":
        contra = [{"account_code": r["account_code"], "debit": r.get("credit", 0), "credit": r.get("debit", 0),
                   "memo": "Önceki aktarımın bağlı ters bileşeni",
                   **({k: r[k] for k in ("currency", "foreign_amount", "exchange_rate")} if r.get("currency") else {})}
                  for r in original["lines"]]
        posting_lines = contra + posting_lines
        normalize_journal_lines(posting_lines)
    preview_hash = digest({"tenant_id": tenant_id, "run_id": run_id, "action": action,
                           "source_hash": plan["manifest"]["source_hash"], "original_hash": (original or {}).get("entry_hash")})
    return {**plan, "run_id": run_id, "business_date": run["business_date"], "action": action,
            "original_entry_id": (original or {}).get("id"), "correction_entry_id": (correction or {}).get("id"),
            "preview_hash": preview_hash, "posting_lines": posting_lines}


async def post_daily_valuation(db, tenant_id, run_id, valuation, expected_hash, actor):
    # Exact replay is checked against a freshly built source manifest. Posting
    # and correction use fixed source keys, not user-supplied random keys.
    preview = await preview_daily_valuation(db, tenant_id, run_id, valuation)
    if preview["action"] in {"already_posted", "already_corrected"}:
        entry_id = preview["correction_entry_id"] or preview["original_entry_id"]
        await db.night_audit_runs.update_one({"tenant_id": tenant_id, "id": run_id}, {"$set": {
            "gl_bridge_status": "posted", "gl_valued_entry_id": entry_id}})
        return {"status": preview["action"], "entry_id": entry_id, "source_hash": preview["manifest"]["source_hash"]}
    if expected_hash != preview["preview_hash"]:
        raise OperationalValuationError("Preview changed; refresh and review source, mapping and valuation before posting")
    if preview["action"] == "no_activity":
        await db.night_audit_runs.update_one({"tenant_id": tenant_id, "id": run_id}, {"$set": {"gl_bridge_status": "no_activity"}})
        return {"status": "no_activity"}
    correcting = preview["action"] == "correct"
    entry = await post_journal_entry(db, tenant_id, date=preview["business_date"],
        memo=("Bağlı kaynak düzeltmesi " + preview["original_entry_id"] if correcting else "Değerlenmiş günlük PMS aktarımı")
             + " — " + preview["manifest"]["source_hash"],
        lines=preview["posting_lines"], source="night_audit_correction" if correcting else "night_audit",
        source_ref=run_id, actor=actor,
        idempotency_key="operational-correction:" + run_id if correcting else "operational-daily:" + preview["business_date"],
        source_manifest=preview["manifest"])
    # If a response/link update fails after the single durable insert, the
    # fixed idempotency key recovers it without inserting another journal.
    await db.night_audit_runs.update_one({"tenant_id": tenant_id, "id": run_id}, {"$set": {
        "gl_bridge_status": "posted", "gl_valued_entry_id": entry["id"],
        "gl_valuation_source_hash": preview["manifest"]["source_hash"],
        **({"gl_correction_entry_id": entry["id"]} if correcting else {"gl_journal_entry_id": entry["id"], "gl_entry_no": entry.get("entry_no")})}})
    return {"status": "corrected" if correcting else "posted", "entry_id": entry["id"],
            "original_entry_id": preview["original_entry_id"], "source_hash": preview["manifest"]["source_hash"]}
