"""Base-currency company aging, preserving source debt and uncertainty."""
from copy import deepcopy
from datetime import date

from modules.pms_core.property_financial_summary import folio_carrying_values
from modules.pms_core.property_position_values import property_position_value
from modules.pms_core.property_reporting_currency import PropertyAccumulator, load_historical_rates, source_day
from modules.pms_core.receivable_reporting import folio_snapshots, report_day
from modules.pms_core.report_money import currency_code


async def property_company_aging(database, tenant_id, payload, positions, folios, original_groups, today, base):
    try:
        snapshots = await folio_snapshots(database, tenant_id, folios, fallback_currency=base, include_booking_extras=True)
    except (ValueError, TypeError, ArithmeticError, KeyError):
        snapshots = {}
    days = [source_day(row) for snap in snapshots.values() for row in snap["charges"] + snap["payments"]]
    days += [source_day({"business_date": snap["folio"].get("opening_balance_date")}) for snap in snapshots.values()]
    days += [source_day({**row, "business_date": row.get("business_date") or row.get("transaction_date")}) for position in positions for row in [*[part["source"] for part in position.get("valuation_parts", [])], *position.get("valuation_candidates", [])]]
    dates = [day for day in days if day] + [today.isoformat()]
    rates = await load_historical_rates(database, tenant_id, date.fromisoformat(min(dates)), date.fromisoformat(max(dates)),
        base_currency=base, currencies={row["currency"] for row in positions})
    ar_rates = []
    carrying, issues = folio_carrying_values(snapshots, rates, evidence=ar_rates)
    acc, groups = PropertyAccumulator(rates), {}
    for position in positions:
        folio, code = position["folio"], currency_code(position["currency"])
        identity = position.get("account_key") or folio.get("company_id")
        group_identity = (type(identity).__name__, identity)
        source_group = original_groups[(identity, code)]
        if group_identity not in groups:
            groups[group_identity] = {**deepcopy(source_group), "currency": base, "_folio_ids": set(), "_metric_key": "group:"+str(len(groups))}
        group = groups[group_identity]
        key = group["_metric_key"]
        if source_group.get("demo_reconstructed"):
            group.update(demo_reconstructed=True, historical_source_verified=False)
        value = property_position_value(position, rates, carrying, ar_rates)
        if value is None:
            issues.append({"id": folio.get("id"), "currency": code, "reason": "receivable_carrying_value_unverified"})
        if position.get("account_key"):
            age = position.get("age_days")
        else:
            anchor = report_day(folio.get("due_date") or folio.get("invoice_date") or folio.get("created_at"))
            age = max((today-anchor).days, 0) if anchor else 99999
            group["_folio_ids"].add(str(folio.get("id")))
        bucket = "unaged" if age is None else "0-7 days" if age <= 7 else "8-14 days" if age <= 14 else "15-30 days" if age <= 30 else "30+ days"
        for metric in ("total", key+":total", key+":"+bucket):
            acc.add(metric, value, {"currency": base})
    companies = []
    for group in groups.values():
        key = group.pop("_metric_key")
        group.update(total_balance=acc.total(key+":total"),
            aging={bucket: acc.total(key+":"+bucket) for bucket in group["aging"]},
            unaged_balance=acc.total(key+":unaged"), folio_count=len(group.pop("_folio_ids")))
        companies.append(group)
    companies.sort(key=lambda row: (row["total_balance"] is None, -(row["total_balance"] or 0), row["company_name"]))
    result = deepcopy(payload)
    valuation_complete = acc.total("total") is not None
    result.update(reporting_currency=base, currency_policy={**acc.metadata(), "rates": ar_rates}, total_ar=acc.total("total") if payload["complete"] else None,
        total_ar_by_currency={base: acc.total("total") if payload["complete"] else None},
        companies=companies, company_count=len(groups), source_complete=payload["complete"],
        valuation_complete=valuation_complete, complete=payload["complete"] and valuation_complete,
        aging_complete=payload["aging_complete"] and valuation_complete,
        source_issues=[*payload.get("source_issues", []), *issues],
        balance_basis="property_currency_remaining_company_ledger_carrying_values")
    return result
