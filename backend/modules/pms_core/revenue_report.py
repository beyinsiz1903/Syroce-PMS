"""Read-only, cent-exact revenue breakdown over the shared posted ledger.

Missing tax evidence is not a zero tax rate. Historical inconsistencies are
reported, never repaired by inventing a discount or using today's tax rules.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from modules.pms_core.report_money import currency_code, money, rounded, single_amount
from modules.pms_core.reporting_ledger import charge_amount, charge_category
from modules.pms_core.revenue_categories import LABELS, revenue_department

FIELDS = ("subtotal", "discount", "net", "vat", "city_tax", "other_tax", "difference", "total")


def revenue_day(row):
    value = next((row[key] for key in ("business_date", "date", "charge_date", "posted_at", "created_at") if row.get(key)), None)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def charge_breakdown(row):
    total = money(charge_amount(row))
    category = charge_category(row)
    tax = row.get("tax_breakdown")
    tax = tax if isinstance(tax, dict) else {}
    refund = row.get("report_refund") or total < 0

    def signed(value):
        value = money(rounded(value))
        return -abs(value) if refund else value

    # Explicit tax_breakdown takes priority: night audit's tax_amount already
    # contains VAT + accommodation tax. Never put that sum in city_tax.
    tax_known = bool(tax) or row.get("vat_amount") is not None or row.get("tax_amount") is not None
    vat = signed(tax.get("vat", row.get("vat_amount") or 0)) if tax_known else None
    city = signed(tax.get("accommodation_tax", tax.get("city_tax", 0))) if tax_known else None
    other = Decimal(0) if tax_known else None
    if tax_known and not tax:
        aggregate = row.get("report_tax_kind") == "aggregate" or "night_audit" in str(row.get("posted_by") or "")
        if aggregate:
            if row.get("vat_amount") is None:
                vat = None
            city = None  # aggregate tax does not identify a city-tax component
            other = signed(row.get("tax_amount")) - (vat or 0) if row.get("tax_amount") is not None else Decimal(0)
        else:
            city = signed(row.get("tax_amount") or 0)
    elif tax:
        other = sum((signed(value) for key, value in tax.items() if key not in {"vat", "accommodation_tax", "city_tax"}), Decimal(0))
    discount = signed(row.get("discount_amount") or 0)
    # Extra charge_amount/amount is commonly a gross UNIT price, not a net
    # line amount. Derive net only from evidence, not the collection name.
    net = total - (vat or 0) - (city or 0) - (other or 0) if tax_known else None
    if category == "city_tax":
        # A standalone tax posting is not room/F&B income. Its category is
        # explicit evidence; do not treat the tax itself as net revenue.
        tax_known, net, vat, city, other = True, Decimal(0), Decimal(0), total, Decimal(0)
    difference = Decimal(0)
    if category != "city_tax" and tax_known and row.get("report_source") == "folio" and row.get("amount") is not None:
        net = signed(row["amount"])
        difference = total - net - (vat or 0) - (city or 0) - (other or 0)
    elif row.get("report_source") == "folio" and row.get("amount") is not None and total < money(rounded(row["amount"])) and total >= 0:
        # A smaller gross than an explicitly stored net cannot be explained
        # by missing positive taxes (e.g. amount=1, total=0). Surface it.
        difference = total - money(rounded(row["amount"]))
    subtotal = signed(row["subtotal"]) if row.get("subtotal") is not None else net + discount if net is not None else None
    subtotal_difference = subtotal - discount - net if subtotal is not None and net is not None else Decimal(0)
    issues = []
    if difference:
        issues.append("Net + vergi ile toplam uyuşmuyor")
    if subtotal_difference:
        issues.append("Ara toplam − indirim ile net uyuşmuyor")
    return {"subtotal": subtotal, "discount": discount, "net": net, "vat": vat, "city_tax": city,
        "other_tax": other, "difference": difference, "total": total, "issues": issues,
        "tax_unknown": not tax_known, "category": category}


def _bucket():
    return {**dict.fromkeys(FIELDS, Decimal(0)), "count": 0, "tax_unknown_count": 0, "issue_count": 0}


def _add(bucket, values):
    bucket["count"] += 1
    bucket["tax_unknown_count"] += int(values["tax_unknown"])
    bucket["issue_count"] += bool(values["issues"])
    for field in FIELDS:
        if values[field] is None or bucket[field] is None:
            bucket[field] = None
        else:
            bucket[field] += values[field]


def _serialize(bucket):
    values = {**bucket, "verified_net": bucket["net"] if not bucket["issue_count"] else None}
    return {key: rounded(value) if isinstance(value, Decimal) else value for key, value in values.items()}


def build_revenue_report(charges, first, last):
    grouped, totals, departments, days = {}, {}, {}, {}
    issues, issue_count, unknown_count = [], 0, 0
    for row in charges:
        day = revenue_day(row)
        if day is None or not first <= day <= last:
            continue
        values = charge_breakdown(row)
        category, code = values["category"], currency_code(row.get("currency"))
        item = grouped.setdefault(category, {"category": category, "label": LABELS[category],
            "department": revenue_department(category), "count": 0, "by_currency": {}, "source_categories": set()})
        item["source_categories"].add(str(row.get("charge_category") or row.get("category") or row.get("charge_type") or "other"))
        item["count"] += 1
        _add(item["by_currency"].setdefault(code, _bucket()), values)
        _add(totals.setdefault(code, _bucket()), values)
        dept = departments.setdefault(revenue_department(category), {})
        dept[code] = dept.get(code, Decimal(0)) + values["total"]
        by_day = days.setdefault(day.isoformat(), {})
        by_day[code] = by_day.get(code, Decimal(0)) + values["total"]
        unknown_count += values["tax_unknown"]
        if values["issues"]:
            issue_count += 1
            if len(issues) < 100:
                issues.append({"source": row.get("report_source"), "id": str(row.get("id") or ""),
                    "date": day.isoformat(), "currency": code, "category": category,
                    "difference": rounded(values["difference"]), "reasons": values["issues"]})
    rows = []
    for item in grouped.values():
        item["source_categories"] = sorted(item["source_categories"])
        item["by_currency"] = {code: _serialize(bucket) for code, bucket in sorted(item["by_currency"].items())}
        # Legacy scalars are only meaningful within ONE currency.
        for field in FIELDS:
            values = {code: bucket[field] for code, bucket in item["by_currency"].items()}
            item[field] = single_amount(values) if all(value is not None for value in values.values()) else None
        rows.append(item)
    rows.sort(key=lambda item: (item["department"], item["label"]))
    totals = {code: _serialize(bucket) for code, bucket in sorted(totals.items())}
    legacy = {field: single_amount({code: bucket[field] for code, bucket in totals.items()})
        if all(bucket[field] is not None for bucket in totals.values()) else None for field in FIELDS}
    legacy["count"] = sum(bucket["count"] for bucket in totals.values())
    trend = []
    for index in range((last - first).days + 1):
        day = (first + timedelta(days=index)).isoformat()
        values = {code: rounded(value) for code, value in days.get(day, {}).items()}
        trend.append({"date": day, "revenue_by_currency": values, "revenue": single_amount(values)})
    return {"date_from": first.isoformat(), "date_to": last.isoformat(), "rows": rows,
        "totals": legacy, "totals_by_currency": totals, "revenue_trend": trend,
        "departments_by_currency": {dept: {code: rounded(value) for code, value in sorted(values.items())} for dept, values in departments.items()},
        "reconciliation": {"issue_count": issue_count, "tax_unknown_count": unknown_count, "issues": issues},
        "basis": "posted_ledger_gross", "definitions": {
            "total": "İade düşülmüş işlenen tutar; mevcut vergiler dahil, bahşiş hariç. Tahsilat değildir.",
            "net": "Vergi hariç tutar. Vergi kırılımı eksikse doğrulanamadı gösterilir; bugünkü oranlarla tahmin edilmez.",
            "fnb": "Yiyecek–içecek; minibar ayrı departmandır ve tekrar eklenmez.",
            "difference": "Kaynak kayıttaki net/vergi/toplam uyumsuzluğu; muhasebe düzeltmesi veya indirim değildir.",
        }}
