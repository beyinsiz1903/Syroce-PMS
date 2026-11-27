"""Read-only base-currency presentation for the financial dashboard."""
import asyncio
from copy import deepcopy
from datetime import date

from modules.pms_core.property_report_projections import property_income_report
from modules.pms_core.property_reporting_currency import PropertyAccumulator, load_historical_rates, source_day


async def property_financial_summary(database, tenant_id, payload, business_day):
    from domains.pms.night_audit.financial_sources import payment_rows, revenue_rows
    from modules.pms_core.receivable_reporting import folio_snapshots
    last = date.fromisoformat(business_day)
    charges, payments, folios, rates = await asyncio.gather(
        revenue_rows(database, tenant_id, business_day, business_day),
        payment_rows(database, tenant_id, business_day, business_day),
        database.folios.find({"tenant_id": tenant_id, "status": "open"}, {"_id": 0}).to_list(None),
        load_historical_rates(database, tenant_id, last, last),
    )
    snapshots = await folio_snapshots(database, tenant_id, folios,
        fallback_currency=rates.currency, include_booking_extras=True)
    days = [source_day(row) for snap in snapshots.values() for row in snap["charges"] + snap["payments"]]
    days += [source_day({"business_date": snap["folio"].get("opening_balance_date")}) for snap in snapshots.values() if snap["opening_by_currency"]]
    first, latest = min([business_day] + [day for day in days if day]), max([business_day] + [day for day in days if day])
    if first != business_day or latest != business_day:
        rates = await load_historical_rates(database, tenant_id, date.fromisoformat(first), date.fromisoformat(latest), base_currency=rates.currency)
    report = property_income_report(charges, last, last, rates)
    base = rates.currency
    result = deepcopy(payload)
    acc = PropertyAccumulator(rates)
    for payment in payments:
        method = str(payment.get("payment_method") or payment.get("method") or "other")
        for key in ("payments", "payment:" + method):
            acc.add(key, payment["amount"], payment)
    balances = []
    for snap in snapshots.values():
        # Preserve debit and credit buckets across native currencies. A net
        # base-currency zero is not proof that unlike debts were settled.
        for code, native_balance in snap["balance_by_currency"].items():
            if not native_balance:
                continue
            ledger = PropertyAccumulator(rates)
            candidates = ([row for row in snap["charges"] if row["currency"] == code]
                if native_balance > 0 else [row for row in snap["payments"] if row["currency"] == code])
            if code in snap["opening_by_currency"]:
                candidates.append({"id": snap["folio"].get("id"), "currency": code, "business_date": snap["folio"].get("opening_balance_date")})
            if code == base:
                ledger.add("balance", native_balance, {"currency": base})
            else:
                quotes = [(source, rates.quote(code, source_day(source), source)) for source in candidates]
                known = {quote[0] for _, quote in quotes if quote is not None}
                missing = not quotes or any(quote is None for _, quote in quotes)
                if missing or len(known) != 1:
                    ledger.unavailable.add("balance")
                    ledger.issues.append({"id": snap["folio"].get("id"), "currency": code,
                        "reason": "historical_exchange_rate_missing" if missing else "receivable_allocation_valuation_unverified",
                        "reporting_currency": base})
                else:
                    ledger.add("balance", native_balance, quotes[0][0])
            balances.append(ledger.total("balance"))
            acc.issues.extend(issue for issue in ledger.issues if issue not in acc.issues)
    balance = dict.fromkeys(("total", "receivable", "overpayment")) if any(value is None for value in balances) else {
        "total": round(sum(balances), 2), "receivable": round(sum(max(value, 0) for value in balances), 2),
        "overpayment": round(sum(min(value, 0) for value in balances), 2)}
    total = report["totals"]
    tax = None if any(total[key] is None for key in ("vat", "city_tax", "other_tax")) else round(sum(total[key] for key in ("vat", "city_tax", "other_tax")), 2)
    result["currency"] = result["reporting_currency"] = base
    result["currency_policy"] = {**acc.metadata(), "revenue": report["currency_policy"],
        "complete": acc.metadata()["complete"] and report["currency_policy"]["complete"] and balance["total"] is not None,
        "missing_rate_count": sum(issue["reason"] == "historical_exchange_rate_missing" for issue in acc.issues) + report["currency_policy"]["missing_rate_count"],
        "unverified_valuation_count": sum(issue["reason"] == "receivable_allocation_valuation_unverified" for issue in acc.issues)}
    result["revenue"].update(charges_count=total["count"], total=total["verified_net"], total_by_currency={base: total["verified_net"]},
        verified_total_by_currency={base: total["verified_net"]}, total_with_tax=total["total"],
        total_with_tax_by_currency={base: total["total"]},
        by_category={row["category"]: {"amount": row["by_currency"][base]["verified_net"],
            "total": row["total"], "tax": None if any(row[key] is None for key in ("vat", "city_tax", "other_tax")) else round(sum(row[key] for key in ("vat", "city_tax", "other_tax")), 2),
            "count": row["count"]} for row in report["rows"]})
    if report.get("original_currency_breakdown"):
        result["revenue"]["original_currency_breakdown"] = report["original_currency_breakdown"]
    result["tax"].update(total=tax, total_by_currency={base: tax}, verified_total_by_currency={base: tax},
        breakdown={"vat": total["vat"], "accommodation_tax": total["city_tax"], "other_tax": total["other_tax"]})
    paid = acc.total("payments")
    result["payments"].update(payments_count=len(payments), total=paid, total_by_currency={base: paid},
        by_method={method: {**row, "amount": acc.total("payment:" + method), "amount_by_currency": {base: acc.total("payment:" + method)}}
            for method, row in result["payments"]["by_method"].items()})
    result["open_folios"].update(balance=balance, balance_by_currency={base: balance}, balance_basis="current_open_folio_carrying_value",
        count=len(snapshots), receivable_count=sum(any(value > 0 for value in snap["balance_by_currency"].values()) for snap in snapshots.values()),
        overpayment_count=sum(any(value < 0 for value in snap["balance_by_currency"].values()) for snap in snapshots.values()))
    result["net_position"] = None if total["total"] is None or paid is None else round(total["total"]-paid, 2)
    result["net_position_by_currency"] = {base: result["net_position"]}
    return result
