"""Canonical open-check repricing and cumulative minor-unit allocations.

Menu prices remain tax-exclusive. Preserve the existing service-charge tax
policy; this module does not invent a new fiscal/tax policy for the property.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException


def decimal(value):
    try:
        result = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, "Adisyon tutarı geçersiz.") from None
    if not result.is_finite():
        raise HTTPException(422, "Adisyon tutarı geçersiz.")
    return result


def rounded(value):
    return decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def reprice_order(order, items=None):
    lines = order.get('order_items') if items is None else items
    if lines:
        subtotal = sum((rounded(line.get('total', decimal(line.get('unit_price')) * decimal(line.get('quantity', 1)))) for line in lines), Decimal(0))
        tax = sum((rounded(decimal(line.get('total', decimal(line.get('unit_price')) * decimal(line.get('quantity', 1)))) * decimal(line.get('tax_rate'))) for line in lines), Decimal(0))
    elif items is not None:
        subtotal = tax = Decimal(0)
    else:
        subtotal = rounded(order.get('total_amount'))
        tax = rounded(order.get('original_tax_amount', order.get('tax_amount')))
    base = rounded(subtotal + tax)
    policies = {event['type']: event for event in order.get('adjustments', []) if event.get('type') in {'discount', 'service_charge'}}
    amounts = {}
    for kind, field in (('discount', 'discount_amount'), ('service_charge', 'service_charge_amount')):
        policy = policies.get(kind)
        if policy:
            value = decimal(policy.get('value'))
            amount = rounded(base * value / 100 if policy.get('calculation') == 'percentage' else value)
        else:
            amount = rounded(order.get(field))
        if amount < 0 or (kind == 'discount' and amount > base):
            raise HTTPException(422, "İndirim kalan adisyon tutarını aşamaz; önce indirim politikasını düzeltin.")
        amounts[field] = amount
    discounted = base - amounts['discount_amount']
    effective_tax = rounded(tax * discounted / base) if base else Decimal(0)
    return {key: float(value) for key, value in {
        'total_amount': subtotal, 'tax_amount': tax, 'pre_adjustment_total': base,
        'original_tax_amount': tax, 'effective_tax_amount': effective_tax,
        **amounts, 'grand_total': rounded(discounted + amounts['service_charge_amount']),
    }.items()}


def allocate_parts(remaining, amount):
    """Allocate cents against REMAINING tenders inside the sale transaction.

    Never round each refund against the original tender independently. The
    caller persists consumed capacities, so retries/parallel refunds cannot
    over-refund a tender and the last refund exactly exhausts all tenders.
    """
    capacities = [int(rounded(value) * 100) for value in remaining]
    cents = int(rounded(amount) * 100)
    total = sum(capacities)
    if any(value < 0 for value in capacities) or cents < 0 or cents > total:
        raise HTTPException(409, "İade ödeme dağılımı kalan tahsilatla uyuşmuyor.")
    if not total:
        return [0.0 for _ in capacities]
    result = [value * cents // total for value in capacities]
    order = sorted(range(len(capacities)), key=lambda i: (-(capacities[i] * cents % total), i))
    for index in order[:cents - sum(result)]:
        result[index] += 1
    return [value / 100 for value in result]
