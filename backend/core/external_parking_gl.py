"""Explicit, idempotent GL recognition of the isolated manual parking ledger.

No guest folio, bank balance or payment source is rewritten. Refunds reverse the
original journal's exact accounts; net-zero days still retain both source rows.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException

from core.integrations.operational_gl_bridge import _payment_account, get_operational_mapping
from shared_kernel.gl_posting import GLPostingError, post_journal_entry, verify_journal_entry_hash


def payment_snapshot(row):
    fields = ('id', 'transport_booking_id', 'kind', 'original_receipt_id', 'business_date',
              'currency', 'method', 'amount', 'net', 'vat_amount', 'reference')
    return {key: row.get(key) for key in fields}


def _minor(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number * 100 != (number * 100).to_integral_value():
            raise ValueError
        return int(number * 100)
    except (ValueError, InvalidOperation):
        raise HTTPException(409, 'Otopark kaynak tutarı geçersiz; mutabakat gerekli') from None


async def linked_journal(db, tenant_id, payment):
    entry = await db.gl_journal_entries.find_one({'tenant_id': tenant_id,
        'idempotency_key': 'external-parking-gl:' + payment['id']}, {'_id': 0})
    if entry and (entry.get('status') != 'posted' or not verify_journal_entry_hash(entry)
            or entry.get('source') != 'external_parking_payment' or entry.get('source_ref') != payment['id']
            or entry.get('reversal_status') or entry.get('source_manifest', {}).get('payment') != payment_snapshot(payment)):
        raise HTTPException(409, 'Otopark muhasebe kaynağı veya fiş mührü uyuşmuyor')
    return entry


async def post_parking_payment_to_gl(db, tenant_id, payment_id, actor):
    payment = await db.transport_payments.find_one({'tenant_id': tenant_id, 'id': payment_id}, {'_id': 0})
    if not payment or not payment.get('manual_record'):
        raise HTTPException(404, 'Manuel otopark ödeme kaydı bulunamadı')
    existing = await linked_journal(db, tenant_id, payment)
    if existing:
        return {'journal': existing, 'replayed': True}
    source = await db.transport_bookings.find_one({'tenant_id': tenant_id, 'id': payment['transport_booking_id']})
    if not source or source.get('customer_type') != 'external' or source.get('kind') != 'parking_spot' or any(
            source.get(key) for key in ('room_number', 'booking_id', 'folio_id', 'folio_charged')):
        raise HTTPException(409, 'Otopark kaynağı bağımsız dış müşteri kaydı değil')
    if payment.get('currency') != 'TRY':
        raise HTTPException(409, 'Döviz otopark kaydı için kaynak günü değerlemesi gerekli; kur varsayılmaz')
    gross, net, vat = (_minor(payment.get(key)) for key in ('amount', 'net', 'vat_amount'))
    if not gross or net + vat != gross or gross != _minor(source.get('total')) or source.get('currency') != 'TRY':
        raise HTTPException(409, 'Otopark kaynak tutarı ve KDV kırılımı uyuşmuyor')
    mapping = await get_operational_mapping(db, tenant_id)
    if not mapping.get('enabled'):
        raise HTTPException(409, 'Operasyon muhasebe eşleştirmesi etkin değil')
    try:
        rate = Decimal(str(source['vat_rate']))
        if not rate.is_finite() or not 0 <= rate <= 100:
            raise ValueError
        expected_net = int((Decimal(gross) / (1 + rate / 100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (KeyError, InvalidOperation, ValueError):
        raise HTTPException(409, 'Kaynak KDV oranı doğrulanamadı') from None
    if net != expected_net:
        raise HTTPException(409, 'KDV matrahı otopark kaynağıyla uyuşmuyor')
    kind = payment.get('kind')
    if source.get('receipt_id' if kind == 'receipt' else 'refund_id') != payment_id:
        raise HTTPException(409, 'Ödeme otopark kaynağının özgün hareketi değil')
    reverses = None
    if kind == 'receipt':
        # Multi-day accruals and prepayments need their own source-day schedule.
        # Never silently treat a future service payment as earned revenue.
        if (source.get('schedule') or {}).get('start_date') != payment.get('business_date') or (source.get('schedule') or {}).get('num_days') != 1:
            raise HTTPException(409, 'Çok günlük veya farklı gündeki otopark hizmeti için dönemsel gelir/ön ödeme değerlemesi gerekli')
        try:
            cash = _payment_account(mapping, payment.get('method'))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        lines = [{'account_code': cash, 'debit': gross / 100},
                 {'account_code': mapping['revenue_account_code'], 'credit': net / 100}]
        if vat:
            lines.append({'account_code': mapping['tax_account_code'], 'credit': vat / 100})
    elif kind == 'refund':
        original = await db.transport_payments.find_one({'tenant_id': tenant_id,
            'id': payment.get('original_receipt_id'), 'kind': 'receipt',
            'transport_booking_id': payment['transport_booking_id']}, {'_id': 0})
        if not original or any(original.get(key) != payment.get(key) for key in ('amount', 'net', 'vat_amount', 'currency', 'method')):
            raise HTTPException(409, 'İade özgün otopark tahsilatıyla uyuşmuyor')
        original_journal = await linked_journal(db, tenant_id, original)
        if not original_journal:
            raise HTTPException(409, 'Önce özgün otopark tahsilatını muhasebeye aktarın')
        reverses = original_journal['id']
        lines = [{'account_code': line['account_code'], 'debit': line.get('credit', 0),
                  'credit': line.get('debit', 0)} for line in original_journal['lines']]
    else:
        raise HTTPException(409, 'Bilinmeyen otopark ödeme türü')
    try:
        entry = await post_journal_entry(db, tenant_id, date=payment['business_date'],
            memo=f"Otopark {'iade' if kind == 'refund' else 'tahsilat'}: {payment['reference']}",
            lines=lines, source='external_parking_payment', source_ref=payment_id, actor=actor,
            idempotency_key='external-parking-gl:' + payment_id, reverses_entry_id=reverses,
            reversal_reason=payment['reference'] if reverses else None,
            source_manifest={'version': 1, 'payment': payment_snapshot(payment)})
    except GLPostingError as exc:
        raise HTTPException(409, f'Otopark muhasebe kaydı tamamlanamadı: {exc}') from exc
    return {'journal': entry, 'replayed': False}
