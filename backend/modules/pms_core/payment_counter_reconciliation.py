"""Audited repair of a derived legacy counter, never a payment/FX backfill."""
import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException

from core.booking_payment_state import is_effective
from modules.pms_core.report_money import currency_code, money, rounded

COLLECTION_METHODS = {'cash', 'card', 'bank_transfer', 'online'}


async def preview(database, tenant_id, booking_id, *, session=None):
    kwargs = {'session': session} if session is not None else {}
    booking = await database.bookings.find_one({'tenant_id': tenant_id, 'id': booking_id}, {'_id': 0}, **kwargs)
    if not booking:
        raise HTTPException(404, 'Rezervasyon bulunamadı')
    folios = await database.folios.find({'tenant_id': tenant_id, 'booking_id': booking_id},
        {'_id': 0, 'id': 1, 'currency': 1, 'status': 1}, **kwargs).to_list(None)
    folio_map = {row['id']: row for row in folios}
    payments = await database.payments.find({'tenant_id': tenant_id, '$or': [
        {'booking_id': booking_id}, {'folio_id': {'$in': list(folio_map)}}]}, {'_id': 0}, **kwargs).to_list(None)
    reasons, total = set(), Decimal('0')
    if booking.get('status') not in {'checked_out', 'cancelled', 'no_show'} or not folios or any(row.get('status') != 'closed' for row in folios):
        reasons.add('active_financial_workflow_requires_review')
    code = currency_code(booking.get('currency'), '')
    if not code:
        reasons.add('missing_booking_currency')
    if booking.get('migration_financial_snapshot') or booking.get('migration_cutover_date'):
        reasons.add('imported_opening_credit_requires_review')
    references, ids = set(), set()
    for payment in payments:
        if not is_effective(payment):
            continue
        pid = payment.get('id')
        if not pid or pid in ids:
            reasons.add('missing_or_duplicate_payment_identity')
        ids.add(pid)
        if payment.get('booking_id') not in (None, '', booking_id):
            reasons.add('ambiguous_payment_owner')
        if payment.get('folio_id') and payment['folio_id'] not in folio_map:
            reasons.add('ambiguous_payment_owner')
        folio = folio_map.get(payment.get('folio_id')) or {}
        payment_code = currency_code(payment.get('currency') or folio.get('currency'), '')
        if not payment_code or payment_code != code:
            reasons.add('mixed_or_unknown_currency')
        if str(payment.get('method') or '').lower() not in COLLECTION_METHODS:
            reasons.add('noncash_settlement_requires_review')
        if payment.get('reference'):
            if payment['reference'] in references:
                reasons.add('duplicate_payment_reference')
            references.add(payment['reference'])
        try:
            amount = money(payment.get('amount'))
            if amount != money(rounded(amount)):
                raise ValueError
            if payment.get('payment_type') == 'refund' or payment.get('status') == 'refunded':
                amount = -abs(amount)
            elif amount <= 0:
                raise ValueError
            total += amount
        except (ValueError, ArithmeticError, TypeError):
            reasons.add('invalid_payment_amount')
    try:
        current = money(booking.get('paid_amount'))
        if current < 0 or current != money(rounded(current)):
            raise ValueError
    except (ValueError, ArithmeticError, TypeError):
        reasons.add('invalid_existing_counter')
        current = Decimal('0')
    if total < 0 or current > total:
        # A larger counter can be an imported opening credit not represented
        # in the current ledger. Never erase it based on an incomplete history.
        reasons.add('unexplained_existing_credit')
    source = {'booking_id': booking_id, 'currency': code, 'paid_amount': booking.get('paid_amount'),
        'migration_financial_snapshot': booking.get('migration_financial_snapshot'),
        'migration_cutover_date': booking.get('migration_cutover_date'), 'status': booking.get('status'),
        'folios': sorted(folios, key=lambda row: row['id']),
        'payments': sorted(payments, key=lambda row: str(row.get('id', '')))}
    revision = hashlib.sha256(json.dumps(source, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()
    return {'booking_id': booking_id, 'currency': code, 'current_paid_amount': rounded(current),
        'ledger_paid_amount': rounded(total), 'difference': rounded(total - current),
        'eligible': not reasons, 'blockers': sorted(reasons), 'source_revision': revision,
        'payment_count': len(payments), 'changes_money': False}


async def reconcile(database, tenant_id, booking_id, expected_revision, reason, actor_id):
    from core.audit_chain import append_audit_log
    from shared_kernel.audit_helper import build_audit_entry

    async with await database.client.start_session() as session:
        async with session.start_transaction():
            plan = await preview(database, tenant_id, booking_id, session=session)
            if not plan['eligible']:
                raise HTTPException(409, {'message': 'Kaynak mutabakatı gerekli; sayaç değiştirilmedi', 'blockers': plan['blockers']})
            if expected_revision != plan['source_revision']:
                raise HTTPException(409, 'Ödeme kaynağı değişti; önizlemeyi yenileyin')
            if plan['difference'] == 0:
                return {**plan, 'applied': False}
            result = await database.bookings.update_one({'tenant_id': tenant_id, 'id': booking_id,
                '$or': [{'paid_amount': plan['current_paid_amount']},
                    {'paid_amount': None}] if plan['current_paid_amount'] == 0 else [{'paid_amount': plan['current_paid_amount']}]},
                {'$set': {'paid_amount': plan['ledger_paid_amount']}}, session=session)
            if result.matched_count != 1:
                raise HTTPException(409, 'Sayaç eşzamanlı değişti; önizlemeyi yenileyin')
            entry = build_audit_entry(actor_id, tenant_id, 'reservation', booking_id,
                'payment_counter_reconciled', {'before_paid_amount': plan['current_paid_amount'],
                    'after_paid_amount': plan['ledger_paid_amount'], 'currency': plan['currency'],
                    'source_revision': plan['source_revision'], 'reason': reason, 'money_posted': False})
            await append_audit_log(database, entry, session=session, require_chain=True)
    return {**plan, 'applied': True}
