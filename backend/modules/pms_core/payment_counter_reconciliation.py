"""Audited repair of a derived legacy counter, never a payment/FX backfill."""
import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException

from core.booking_payment_state import is_effective
from modules.pms_core.report_money import currency_code, money, rounded

COLLECTION_METHODS = {'cash', 'card', 'bank_transfer', 'online'}


async def preview(database, tenant_id, booking_id, *, session=None, review_closed_folios=False):
    kwargs = {'session': session} if session is not None else {}
    booking = await database.bookings.find_one({'tenant_id': tenant_id, 'id': booking_id}, {'_id': 0}, **kwargs)
    if not booking:
        raise HTTPException(404, 'Rezervasyon bulunamadı')
    projection = {'_id': 0} if review_closed_folios else {'_id': 0, 'id': 1, 'currency': 1, 'status': 1}
    folios = await database.folios.find({'tenant_id': tenant_id, 'booking_id': booking_id}, projection, **kwargs).to_list(None)
    folio_map = {row['id']: row for row in folios if isinstance(row.get('id'), str) and row['id'].strip()}
    payments = await database.payments.find({'tenant_id': tenant_id, '$or': [
        {'booking_id': booking_id}, {'folio_id': {'$in': list(folio_map)}}]}, {'_id': 0}, **kwargs).to_list(None)
    reasons, total = set(), Decimal('0')
    if len(folio_map) != len(folios):
        reasons.add('missing_or_duplicate_folio_identity')
    terminal = booking.get('status') in {'checked_out', 'cancelled', 'no_show'}
    closed = bool(folios) and all(row.get('status') == 'closed' for row in folios)
    # A confirmed future stay can already have sealed, fully settled folios.
    # It must NOT be cancelled/checked out just to repair a derived counter.
    # Default historical repair remains unchanged; the reviewed path requires
    # a distinct preview, closed balanced ledgers and no unresolved PSP intent.
    if not closed or (not terminal and not (review_closed_folios and booking.get('status') == 'confirmed')):
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
        if review_closed_folios and payment.get('folio_id') not in folio_map:
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
        'folios': sorted(folios, key=lambda row: str(row.get('id', ''))),
        'payments': sorted(payments, key=lambda row: str(row.get('id', '')))}
    if review_closed_folios:
        from modules.pms_core.receivable_reporting import folio_snapshots
        from modules.pms_core.reporting_financials import deduplicate_report_payments

        if booking.get('status') != 'confirmed':
            reasons.add('sealed_review_requires_confirmed_reservation')
        effective_payments = [row for row in payments if is_effective(row)]
        if len(deduplicate_report_payments(effective_payments)) != len(effective_payments):
            reasons.add('duplicate_payment_transaction_requires_review')
        related = {'tenant_id': tenant_id, '$or': [{'booking_id': booking_id}, {'folio_id': {'$in': list(folio_map)}}]}
        charges = await database.folio_charges.find(related, {'_id': 0}, **kwargs).to_list(None)
        extras = await database.extra_charges.find(related, {'_id': 0}, **kwargs).to_list(None)
        intents = await database.payment_intents.find({'tenant_id': tenant_id, 'booking_id': booking_id}, {'_id': 0}, **kwargs).to_list(None)
        for rows in (charges, extras):
            identities = set()
            for row in rows:
                if row.get('voided') is True:
                    continue
                identity = row.get('id')
                if not isinstance(identity, str) or not identity.strip() or identity in identities:
                    reasons.add('missing_or_duplicate_charge_identity')
                identities.add(str(identity))
        if any(row.get('status') not in {'paid', 'failed', 'cancelled', 'refunded'} for row in intents):
            reasons.add('unresolved_provider_payment_requires_review')
        for row in [*charges, *extras]:
            if row.get('voided') is True:
                continue
            if row.get('booking_id') not in (None, '', booking_id) or row.get('folio_id') not in folio_map:
                reasons.add('ambiguous_charge_owner')
        # Unlike the historical counter-only repair, this opt-in path checks
        # every closed window's authoritative charge/payment/opening ledger.
        # A zero STORED balance is not proof that the window is settled.
        try:
            snapshots = await folio_snapshots(database, tenant_id, list(folio_map.values()), fallback_currency=code,
                                             session=session, include_booking_extras=True)
            for snap in snapshots.values():
                if snap['folio'].get('balance') is None or money(snap['folio']['balance']) != 0:
                    reasons.add('closed_folio_stored_balance_not_zero')
                if snap['currency'] != code or any(currency != code for currency in (
                    snap['charges_by_currency'].keys() | snap['payments_by_currency'].keys() | snap['balance_by_currency'].keys()
                )):
                    reasons.add('mixed_or_unknown_currency')
                if any(money(value) != 0 for value in snap['balance_by_currency'].values()):
                    reasons.add('closed_folio_ledger_not_balanced')
                if money(snap['folio'].get('opening_balance') or 0) != 0:
                    reasons.add('imported_opening_credit_requires_review')
                if any(money(row['total']) != money(rounded(money(row['total']))) for row in snap['charges']):
                    reasons.add('invalid_charge_amount')
        except (ValueError, ArithmeticError, TypeError, KeyError):
            reasons.add('invalid_closed_folio_ledger')
        source['review_mode'] = 'sealed_confirmed'
        source['charges'] = sorted(charges, key=lambda row: str(row.get('id', '')))
        source['extras'] = sorted(extras, key=lambda row: str(row.get('id', '')))
        source['payment_intents'] = sorted(intents, key=lambda row: str(row.get('id', '')))
    revision = hashlib.sha256(json.dumps(source, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()
    return {'booking_id': booking_id, 'currency': code, 'current_paid_amount': rounded(current),
        'ledger_paid_amount': rounded(total), 'difference': rounded(total - current),
        'eligible': not reasons, 'blockers': sorted(reasons), 'source_revision': revision,
        'payment_count': len(payments), 'changes_money': False,
        'review_closed_folios': review_closed_folios}


async def reconcile(database, tenant_id, booking_id, expected_revision, reason, actor_id, *, review_closed_folios=False):
    from core.audit_chain import append_audit_log
    from shared_kernel.audit_helper import build_audit_entry

    async with await database.client.start_session() as session:
        async with session.start_transaction():
            plan = await preview(database, tenant_id, booking_id, session=session, review_closed_folios=review_closed_folios)
            if not plan['eligible']:
                raise HTTPException(409, {'message': 'Kaynak mutabakatı gerekli; sayaç değiştirilmedi', 'blockers': plan['blockers']})
            if expected_revision != plan['source_revision']:
                raise HTTPException(409, 'Ödeme kaynağı değişti; önizlemeyi yenileyin')
            if plan['difference'] == 0:
                return {**plan, 'applied': False}
            result = await database.bookings.update_one({'tenant_id': tenant_id, 'id': booking_id,
                **({'status': 'confirmed'} if review_closed_folios else {}),
                '$or': [{'paid_amount': plan['current_paid_amount']},
                    {'paid_amount': None}] if plan['current_paid_amount'] == 0 else [{'paid_amount': plan['current_paid_amount']}]},
                {'$set': {'paid_amount': plan['ledger_paid_amount']}}, session=session)
            if result.matched_count != 1:
                raise HTTPException(409, 'Sayaç eşzamanlı değişti; önizlemeyi yenileyin')
            entry = build_audit_entry(actor_id, tenant_id, 'reservation', booking_id,
                'payment_counter_reconciled', {'before_paid_amount': plan['current_paid_amount'],
                    'after_paid_amount': plan['ledger_paid_amount'], 'currency': plan['currency'],
                    'source_revision': plan['source_revision'], 'reason': reason, 'money_posted': False,
                    'review_closed_folios': review_closed_folios})
            await append_audit_log(database, entry, session=session, require_chain=True)
    return {**plan, 'applied': True}
