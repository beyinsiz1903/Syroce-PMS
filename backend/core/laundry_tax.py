"""Explicit VAT-included laundry prices; missing rates are never zero tax."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException

CENT = Decimal('0.01')


def laundry_vat_rate(value):
    if value is None:
        return None
    try:
        rate = Decimal(str(value))
        if isinstance(value, bool) or not rate.is_finite() or not 0 <= rate <= 100 or rate != rate.quantize(CENT):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(400, 'KDV oranı 0–100 arasında, en fazla iki ondalıklı olmalıdır') from None
    return float(rate)


def laundry_tax_snapshot(lines, currency):
    gross = sum(Decimal(str(line['total'])) for line in lines)
    rates = [laundry_vat_rate(line.get('vat_rate')) for line in lines]
    known = bool(lines) and all(rate is not None for rate in rates)
    tax = sum((Decimal(str(line['total'])) - (Decimal(str(line['total'])) / (1 + Decimal(str(rate)) / 100)).quantize(CENT, rounding=ROUND_HALF_UP))
        for line, rate in zip(lines, rates, strict=True)) if known else None
    return {'version': 1, 'inclusive': True, 'status': 'verified' if known else 'missing',
        'currency': currency, 'gross': float(gross), 'vat': float(tax) if known else None,
        'net': float(gross - tax) if known else None, 'basis': 'catalog_at_order_creation'}


def laundry_delivery_tax(order, money):
    snapshot = order.get('tax_snapshot')
    # Old orders carry no VAT provenance. They may still be delivered, but tax stays unknown.
    if snapshot is None:
        return {'tax_amount': None, 'vat_amount': None, 'net_amount': None, 'tax_evidence_status': 'missing'}
    expected = laundry_tax_snapshot(order.get('items', []), money['entered_currency'])
    if snapshot != expected or Decimal(str(snapshot['gross'])) != Decimal(str(money['entered_total'])):
        raise HTTPException(409, 'Çamaşırhane vergi kaynağı değişmiş; mali kaydı inceleyin')
    if snapshot['status'] != 'verified':
        return {'tax_amount': None, 'vat_amount': None, 'net_amount': None, 'tax_evidence_status': 'missing', 'tax_snapshot': snapshot}
    vat = (Decimal(str(snapshot['vat'])) * Decimal(str(money['exchange_rate']))).quantize(CENT, rounding=ROUND_HALF_UP)
    net = Decimal(str(money['folio_total'])) - vat
    return {'tax_amount': float(vat), 'vat_amount': float(vat), 'net_amount': float(net),
        'tax_inclusive': True, 'tax_evidence_status': 'verified', 'tax_snapshot': snapshot}
