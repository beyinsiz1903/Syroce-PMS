"""Property-currency views over original, unchanged report sources."""
from copy import deepcopy
from datetime import timedelta

from modules.pms_core.property_reporting_currency import PropertyAccumulator
from modules.pms_core.report_money import currency_code, money, rounded
from modules.pms_core.reporting_ledger import charge_amount
from modules.pms_core.revenue_categories import is_revenue_charge, revenue_department
from modules.pms_core.revenue_report import FIELDS, build_revenue_report, charge_breakdown, revenue_day


def property_income_report(charges, first, last, rates):
    original = build_revenue_report(charges, first, last)
    result = deepcopy(original)
    acc = PropertyAccumulator(rates)
    for source in charges:
        day = revenue_day(source)
        if not is_revenue_charge(source) or day is None or not first <= day <= last:
            continue
        values = charge_breakdown(source)
        category = values["category"]
        for field in FIELDS:
            for key in ("total", "category:" + category):
                acc.add(key + ":" + field, values[field], source)
        for key in ("total", "category:" + category):
            verified = not values["issues"] and values["net"] is not None
            tax = None if any(values[field] is None for field in ("vat", "city_tax", "other_tax")) else sum(values[field] for field in ("vat", "city_tax", "other_tax"))
            acc.add(key + ":proof_gross", values["total"] if verified else None, source)
            acc.add(key + ":proof_tax", tax if verified else None, source)
        acc.add("day:" + day.isoformat(), values["total"], source)
        acc.add("department:" + revenue_department(category), values["total"], source)
        acc.add("verified_net", None if values["issues"] else values["net"], source)
        acc.add("category_verified_net:" + category, None if values["issues"] else values["net"], source)
    base = rates.currency
    def monetary_bucket(key):
        bucket = {field: acc.total(key + ":" + field) for field in FIELDS}
        gross, tax = acc.total(key + ":proof_gross"), acc.total(key + ":proof_tax")
        # Same identity as the sealed GL: round gross and aggregate tax first,
        # then derive net. Independently rounding native net can differ a cent.
        bucket["net"] = None if gross is None or tax is None else rounded(money(gross)-money(tax))
        city, other = bucket["city_tax"], bucket["other_tax"]
        bucket["vat"] = None if tax is None or city is None or other is None else rounded(money(tax)-money(city)-money(other))
        bucket["verified_net"] = bucket["net"]
        bucket["verified_tax"] = tax
        return bucket
    for row in result["rows"]:
        old = list(row["by_currency"].values())
        bucket = monetary_bucket("category:" + row["category"])
        bucket.update(count=row["count"],
            tax_unknown_count=sum(x.get("tax_unknown_count", 0) for x in old),
            issue_count=sum(x.get("issue_count", 0) for x in old))
        row.update({field: bucket[field] for field in FIELDS})
        row["by_currency"] = {base: bucket}
    total = monetary_bucket("total")
    total.update(count=original["totals"]["count"],
        tax_unknown_count=original["reconciliation"]["tax_unknown_count"],
        issue_count=original["reconciliation"]["issue_count"])
    result.update(totals=total, totals_by_currency={base: total}, reporting_currency=base,
        currency_policy=acc.metadata())
    result["departments_by_currency"] = {dept: {base: acc.total("department:" + dept)}
        for dept in original["departments_by_currency"]}
    result["revenue_trend"] = [{"date": (first + timedelta(days=i)).isoformat(),
        "revenue": acc.total("day:" + (first + timedelta(days=i)).isoformat()),
        "revenue_by_currency": {base: acc.total("day:" + (first + timedelta(days=i)).isoformat())}}
        for i in range((last-first).days + 1)]
    rounding = {}
    for field in FIELDS:
        values = [row[field] for row in result["rows"]]
        if total[field] is not None and all(value is not None for value in values):
            delta = rounded(money(total[field])-sum((money(value) for value in values), money(0)))
            if delta:
                rounding[field] = delta
    result["currency_policy"]["rounding_difference_by_field"] = rounding
    result["currency_policy"]["rounding_basis"] = "daily_currency_rate_group_then_period_sum"
    # Native currency is a drill-down only, never the headline display.
    if any(code != base and values.get("count", 0) for code, values in original["totals_by_currency"].items()):
        result["original_currency_breakdown"] = original["totals_by_currency"]
    return result


def property_revenue_kpis(charges, metrics, first, last, rates):
    report = property_income_report(charges, first, last, rates)
    acc = PropertyAccumulator(rates)
    for source in charges:
        day = revenue_day(source)
        if day is None or not first <= day <= last or not is_revenue_charge(source):
            continue
        values = charge_breakdown(source)
        category = values["category"]
        acc.add("total_revenue", charge_amount(source), source)
        if category == "room":
            acc.add("room_revenue", charge_amount(source), source)
            verified = not values["issues"] and values["net"] is not None
            acc.add("room_proof_gross", values["total"] if verified else None, source)
            acc.add("room_proof_tax", values["total"]-values["net"] if verified else None, source)
        if revenue_department(category) == "fnb":
            acc.add("fb_revenue", charge_amount(source), source)
    sold = sum(int(row.get("sold_rooms", row.get("occupied_rooms")) or 0) for row in metrics)
    capacity = sum(int(row.get("total_rooms") or 0) for row in metrics)
    posted = {(revenue_day(source).isoformat(), currency_code(source.get("currency")))
        for source in charges if revenue_day(source) is not None and charge_breakdown(source)["category"] == "room"}
    pending_days = []
    for metric in metrics:
        day = str(metric.get("date") or "")[:10]
        if not day or not int(metric.get("sold_rooms", metric.get("occupied_rooms")) or 0):
            continue
        codes = {currency_code(code) for code, count in (metric.get("sold_rooms_by_currency") or {}).items() if count}
        missing = any((day, code) not in posted for code in codes) if codes else not any(key[0] == day for key in posted)
        if missing:
            pending_days.append(day)
    gross, tax = acc.total("room_proof_gross"), acc.total("room_proof_tax")
    room_net = None if pending_days or gross is None or tax is None else rounded(money(gross)-money(tax))
    result = {"currency": rates.currency, "currency_policy": acc.metadata(),
        "room_nights_sold": sold, "available_room_nights": capacity,
        "posting_pending": bool(pending_days), "posting_gap_days": pending_days}
    for key in ("total_revenue", "room_revenue", "room_revenue_net", "fb_revenue"):
        result[key] = room_net if key == "room_revenue_net" else acc.total(key)
        result[key + "_by_currency"] = {rates.currency: result[key]}
    for key, denominator in (("adr", sold), ("rev_par", capacity)):
        result[key] = None if room_net is None else rounded(money(room_net)/denominator) if denominator else 0.0
        result[key + "_by_currency"] = {rates.currency: result[key]}
    result["adr_basis"] = "posted_room_net_excluding_recorded_taxes_per_paid_room_night"
    result["category_revenue_by_currency"] = {row["category"]: {rates.currency: row["total"]} for row in report["rows"]}
    result["original_currency_breakdown"] = report.get("original_currency_breakdown")
    return result

