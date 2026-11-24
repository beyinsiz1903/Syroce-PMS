"""Atomic group collection; account ownership and cashier evidence are inseparable."""
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException


def _cents(value):
    amount = Decimal(str(value)) * 100
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise HTTPException(422, 'Tutar en fazla iki ondalık basamak içermeli')
    return int(amount)


def allocate_collection(total, balances, distribution):
    """Allocate integer cents, cap at each debt, never lose rounding pennies."""
    capacities = [max(0, _cents(balance)) for balance in balances]
    requested = _cents(total)
    if requested <= 0 or requested > sum(capacities):
        raise HTTPException(409, 'Toplu ödeme grubun açık borcunu aşamaz')
    amounts = [0] * len(capacities)
    remaining = requested
    if distribution == 'balance_only':
        for i, capacity in enumerate(capacities):
            amounts[i] = min(capacity, remaining)
            remaining -= amounts[i]
    else:
        while remaining:
            active = [i for i, cap in enumerate(capacities) if cap > amounts[i]]
            weights = {i: capacities[i] if distribution == 'proportional' else 1 for i in active}
            denominator = sum(weights.values())
            fractions = {}
            budget = remaining
            for i in active:
                numerator = budget * weights[i]
                share = min(capacities[i] - amounts[i], numerator // denominator)
                fractions[i] = numerator % denominator
                amounts[i] += share
                remaining -= share
            for i in sorted(active, key=lambda idx: (-fractions[idx], idx)):
                if remaining and amounts[i] < capacities[i]:
                    amounts[i] += 1
                    remaining -= 1
    return [amount / 100 for amount in amounts]


async def collect_group_payment(database, data, actor, *, load_rows):
    from core.booking_atomicity import with_resource_locks
    from core.booking_payment_state import refresh_booking_payment_state
    from core.business_date_service import stamp_open_business_date
    from domains.pms.cashier_service import record_cash_transaction
    from modules.pms_core.enterprise_billing import manual_collection_method
    from modules.pms_core.folio_selection import select_booking_folio
    from modules.pms_core.payment_cashier_snapshot import cashier_values
    from modules.pms_core.receivable_reporting import folio_snapshots

    tid = actor.tenant_id
    method = manual_collection_method(data.method)
    group = await database.group_bookings.find_one({'id': data.group_id, 'tenant_id': tid}, {'_id': 0})
    if not group:
        raise HTTPException(404, 'Grup bulunamadı')
    ids = sorted(set(group.get('booking_ids') or []))
    if not ids or len(ids) > 100:
        raise HTTPException(409, 'Grup rezervasyonlarını misafir kartından inceleyin')
    intent = {'group_id': data.group_id, 'amount_cents': _cents(data.total_amount),
        'method': method, 'distribution': data.distribution}
    operation_id = sha256(f'{tid}|{data.group_id}|{data.reference}'.encode()).hexdigest()
    day = {}
    await stamp_open_business_date(database, tid, day)

    async def post(session):
        kw = {'session': session}
        previous = await database.group_bulk_payment_operations.find_one({'_id': operation_id}, **kw)
        if previous:
            if previous['intent'] != intent:
                raise HTTPException(409, 'Aynı toplu ödeme referansı farklı işlem için kullanılamaz')
            return {**previous['response'], 'idempotent': True}
        current = await database.group_bookings.find_one({'id': data.group_id, 'tenant_id': tid}, {'_id': 0}, **kw)
        if not current or sorted(set(current.get('booking_ids') or [])) != ids:
            raise HTTPException(409, 'Grup üyeleri değişti; yenileyip tekrar inceleyin')
        rows = await load_rows(tid, ids, session=session)
        if len(rows) != len(ids):
            raise HTTPException(409, 'Grubun bazı rezervasyonları bulunamadı; önce uzlaştırın')
        rows = [r for r in rows if not r.get('folio_merged_to')]
        if not rows:
            raise HTTPException(409, 'Aktif grup hesabı bulunamadı')
        if {r['currency'] for r in rows} != {'TRY'}:
            raise HTTPException(422, 'Dövizli grupta kur ve hedef hesap misafir kartından seçilmelidir; varsayılan 1:1 kur kullanılmaz')
        shares = allocate_collection(data.total_amount, [r['balance'] for r in rows], data.distribution)
        targets = []
        for row, amount in zip(rows, shares, strict=True):
            if not amount:
                continue
            if row['booking'].get('status') in {'checked_out', 'cancelled', 'no_show'}:
                raise HTTPException(409, 'Kapalı/iptal konaklamanın hesabını misafir kartından uzlaştırın')
            folio = await select_booking_folio(database, tid, row['booking_id'], session=session)
            if not folio or folio.get('invoice_id') or folio.get('currency', 'TRY') != 'TRY':
                raise HTTPException(409, 'Her ödeme için açık, faturasız TRY folyosunu misafir kartından hazırlayın')
            targets.append((row, amount, folio))
        now = datetime.now(UTC).isoformat()
        payments = []
        for row, amount, folio in targets:
            payment = {'id': str(uuid4()), 'tenant_id': tid, 'booking_id': row['booking_id'],
                'folio_id': folio['id'], 'amount': amount, 'currency': 'TRY',
                'received_currency': 'TRY', 'received_amount': amount, 'exchange_rate': 1,
                'method': method, 'payment_type': 'interim', 'status': 'paid', 'voided': False,
                'reference': f'group-bulk:{operation_id}:{row["booking_id"]}',
                'notes': data.reference, 'group_bulk_operation_id': operation_id,
                'processed_by': actor.name, 'processed_at': now, **day}
            cash = cashier_values(payment)
            await database.payments.insert_one({**payment}, **kw)
            txn = await record_cash_transaction(tenant_id=tid, **cash, method=method,
                direction='in', description=f'Grup ödemesi: {data.reference}',
                ref_type='payment', ref_id=payment['id'], txn_type='folio_payment',
                created_by=getattr(actor, 'email', None) or actor.id, created_by_name=actor.name,
                idempotency_key=f'payment:{payment["id"]}', require_open_shift=True, session=session)
            if not txn:
                raise HTTPException(409, 'Toplu ödeme için açık kasa vardiyası gereklidir')
            snapshots = await folio_snapshots(database, tid, [folio], fallback_currency='TRY',
                include_booking_extras=True, session=session)
            snapshot = snapshots[folio['id']]
            if any(code != 'TRY' and value for code, value in snapshot['balance_by_currency'].items()):
                raise HTTPException(409, 'Folyonun para birimleri önce uzlaştırılmalıdır')
            await database.folios.update_one({'id': folio['id'], 'tenant_id': tid},
                {'$set': {'balance': snapshot['balance_by_currency'].get('TRY', 0)}}, **kw)
            await refresh_booking_payment_state(database, tid, row['booking_id'], session=session, strict=True)
            await database.reservation_activity_log.insert_one({'id': str(uuid4()), 'tenant_id': tid,
                'booking_id': row['booking_id'], 'action': 'payment_recorded', 'actor': actor.name,
                'created_at': now, 'details': {'amount': amount, 'currency': 'TRY', 'method': method,
                    'payment_id': payment['id'], 'folio_id': folio['id'], 'group_bulk_operation_id': operation_id}}, **kw)
            payments.append({**payment, 'guest_name': row['guest_name']})
        response = {'success': True, 'total_distributed': data.total_amount,
            'payments_count': len(payments), 'currency': 'TRY', 'payments': payments}
        await database.group_bulk_payment_operations.insert_one({'_id': operation_id,
            'tenant_id': tid, 'intent': intent, 'response': response}, **kw)
        return response

    return await with_resource_locks(client=database.client, db=database, tenant_id=tid,
        locks_collection='reservation_financial_locks',
        resources=[('group', data.group_id), *[('booking', bid) for bid in ids]], callback=post)
