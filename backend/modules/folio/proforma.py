"""Read-only proforma projection using the same effective ledger as receivables."""
from decimal import Decimal

from modules.pms_core.report_money import money
from modules.pms_core.reporting_financials import effective_collection


def proforma_amounts(snapshot):
    code = snapshot["currency"]
    codes = {row["currency"] for row in snapshot["charges"] + snapshot["payments"]}
    if codes - {code}:
        raise ValueError("Folyoda farklı para birimleri var. Proforma öncesinde para birimi bazlı hesap dökümünü kontrol edin.")
    groups = {}
    sums = dict.fromkeys(("subtotal", "discount_total", "net_total", "vat_total", "city_tax_total", "grand_total"), Decimal(0))
    charges = []
    tax_complete = True
    for source in snapshot["charges"]:
        row = dict(source)
        gross = money(row["total"])
        vat, city, discount = (money(row.get(key) or 0) for key in ("vat_amount", "tax_amount", "discount_amount"))
        net = gross - vat - city
        subtotal = net + discount
        rate = float(row["vat_rate"]) if row.get("vat_rate") is not None else None
        # Missing tax metadata is unknown, never evidence of a zero tax rate.
        row_tax_complete = row.get("vat_amount") is not None
        tax_complete = tax_complete and row_tax_complete
        row.update(total=float(gross), net_amount=float(net) if row_tax_complete else None,
                   subtotal=float(subtotal) if row_tax_complete else None, vat_rate=rate)
        charges.append(row)
        for key, amount in zip(sums, (subtotal, discount, net, vat, city, gross), strict=True):
            sums[key] += amount
        group = groups.setdefault(rate, {"vat_rate": rate, "net": Decimal(0), "vat_amount": Decimal(0), "count": 0})
        group["net"] = group["net"] + net if row_tax_complete and group["net"] is not None else None
        group["vat_amount"] = group["vat_amount"] + vat if row_tax_complete and group["vat_amount"] is not None else None
        group["count"] += 1
    settlements = money(snapshot["payments_by_currency"].get(code, 0))
    collections = sum((money(effective_collection(row)) for row in snapshot["payments"]), Decimal(0))
    opening = money(snapshot["opening_by_currency"].get(code, 0))
    totals = {key: float(money(value)) for key, value in sums.items()}
    if not tax_complete:
        totals.update(subtotal=None, net_total=None, vat_total=None)
    totals.update(opening_balance=float(opening), payments_total=float(settlements), collections_total=float(collections),
                  non_cash_total=float(settlements - collections), balance_due=float(money(opening + sums["grand_total"] - settlements)),
                  tax_breakdown_complete=tax_complete,
                  opening_balance_note="Önceki PMS bakiyesi; hizmet ve vergi toplamına dahil değildir." if opening else None)
    breakdown = [{**group, "net": float(money(group["net"])) if group["net"] is not None else None,
                  "vat_amount": float(money(group["vat_amount"])) if group["vat_amount"] is not None else None}
                 for group in sorted(groups.values(), key=lambda item: (item["vat_rate"] is None, item["vat_rate"] or 0))]
    return charges, breakdown, totals
