"""Snapshot-only, cent-exact POS → folio allocation. Never consult today's rates."""

from decimal import Decimal

from fastapi import HTTPException

from .order_pricing import rounded


def allocate(total, weights):
    cents = int(rounded(total) * 100)
    values = [max(Decimal(0), Decimal(str(value or 0))) for value in weights]
    denominator = sum(values)
    if cents < 0 or not values or (cents and not denominator):
        raise HTTPException(422, "POS satır dağılımı doğrulanamadı.")
    if not denominator:
        return [0.0] * len(values)
    raw = [Decimal(cents) * value / denominator for value in values]
    result = [int(value) for value in raw]
    indices = sorted(range(len(values)), key=lambda i: (-(raw[i] - result[i]), i))
    for index in indices[: cents - sum(result)]:
        result[index] += 1
    return [value / 100 for value in result]


def checkout_lines(transaction):
    """Return net/VAT/gross/category lines from the immutable sale snapshot."""
    rows = transaction.get("order_items") or transaction.get("items") or []
    gross = rounded(transaction.get("amount", transaction.get("total_amount", 0)))
    # amount is net of tip on canonical sales; legacy rows may only have total.
    if transaction.get("amount") is None:
        gross -= rounded(transaction.get("tip_amount"))
    tax = rounded(transaction.get("tax_amount"))
    service = rounded(transaction.get("service_charge_amount"))
    discount = rounded(transaction.get("discount_amount"))
    if min(gross, tax, service) < 0 or tax + service > gross:
        raise HTTPException(422, "POS net/vergi/toplamı doğrulanamadı.")
    if not rows:
        rows = [{"category": "fnb", "item_name": "Yiyecek–içecek", "quantity": 1, "total": float(gross - tax - service), "tax_rate": None}]
    nets = [rounded(row.get("total", row.get("total_price", Decimal(str(row.get("unit_price", row.get("price", 0)) or 0)) * Decimal(str(row.get("quantity", 1) or 0))))) for row in rows]
    original_taxes = [rounded(net * Decimal(str(row.get("tax_rate") or 0))) for row, net in zip(rows, nets)]
    weights = [net + vat for net, vat in zip(nets, original_taxes)]
    if not sum(weights):
        weights = [1] * len(rows)
    amounts = allocate(gross - service, weights)
    taxes = allocate(tax, original_taxes if sum(original_taxes) else weights)
    # Checkout discounts include the released VAT, whereas a folio's discount
    # is net. Service is kept as a separate, explicitly untaxed policy line.
    net_discount = max(Decimal(0), discount - max(Decimal(0), sum(original_taxes) - tax))
    discounts = allocate(net_discount, weights)
    result = []
    for index, (row, total, vat, reduction) in enumerate(zip(rows, amounts, taxes, discounts)):
        net = rounded(Decimal(str(total)) - Decimal(str(vat)))
        if net < 0:
            raise HTTPException(422, "POS satırının vergisi toplamını aşıyor.")
        result.append(
            {
                "line_no": index,
                "charge_category": row.get("category") or "fnb",
                "item_id": row.get("item_id"),
                "description": row.get("item_name") or row.get("name") or "Yiyecek–içecek",
                "quantity": row.get("quantity", 1),
                "amount": float(net),
                "subtotal": float(net + Decimal(str(reduction))),
                "discount_amount": reduction,
                "vat_amount": vat,
                "tax_amount": 0,
                "tax_breakdown": {"vat": vat},
                "total": total,
            }
        )
    if service:
        result.append(
            {
                "line_no": len(result),
                "charge_category": "service_charge",
                "description": "Servis bedeli",
                "quantity": 1,
                "amount": float(service),
                "subtotal": float(service),
                "discount_amount": 0,
                "vat_amount": 0,
                "tax_amount": 0,
                "tax_breakdown": {"vat": 0},
                "total": float(service),
            }
        )
    return result
