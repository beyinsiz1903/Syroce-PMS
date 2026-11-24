"""Atomic, same-currency reassignment of a receivable; never a collection."""
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from core.booking_atomicity import with_resource_locks


def _money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount != amount.quantize(Decimal('0.01')):
            raise ValueError
        return amount
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(409, 'Cari tutarı kuruş hassasiyetinde ve sonlu olmalı') from None


def _balance(account):
    values = [_money(account[key]) for key in ('balance', 'current_balance') if account.get(key) is not None]
    if not values or len(set(values)) != 1:
        raise HTTPException(409, 'Cari bakiye alanları uyuşmuyor; önce kaynak hareketlerle uzlaştırın')
    return values[0]


def _currency(account):
    code = str(account.get('currency') or '').strip().upper()
    if code == 'TL':
        code = 'TRY'
    if len(code) != 3 or not code.isalpha():
        raise HTTPException(409, 'Cari hesabın para birimi doğrulanamadı')
    return code


async def transfer_to_agency(database, actor, source_id, body):
    tenant = actor.tenant_id
    target_id = body.cari_account_id
    if source_id == target_id:
        raise HTTPException(422, 'Kaynak ve hedef cari hesap farklı olmalı')
    amount = _money(body.amount)
    if amount <= 0:
        raise HTTPException(422, 'Aktarım tutarı pozitif olmalı')
    request_id = str(body.request_id)
    fingerprint = hashlib.sha256(json.dumps([source_id, target_id, f'{amount:.2f}', body.description or ''], ensure_ascii=False).encode()).hexdigest()
    operation_id = f'cari-agency:{tenant}:{request_id}'
    # Create transaction collections and serialize both accounts and retries.
    await database.cari_agency_transfer_locks.create_index([('tenant_id', 1), ('kind', 1), ('resource_id', 1)], unique=True)
    await database.cari_transfer_operations.create_index([('tenant_id', 1), ('request_id', 1)], unique=True)
    await database.cari_transactions.create_index([('tenant_id', 1), ('cari_account_id', 1)])

    async def commit(session):
        previous = await database.cari_transfer_operations.find_one({'_id': operation_id, 'tenant_id': tenant}, session=session)
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise HTTPException(409, 'İşlem anahtarı başka bir cari aktarımı için kullanılmış')
            return {**previous['result'], 'replayed': True}
        accounts = []
        for account_id in (source_id, target_id):
            account = await database.cari_accounts.find_one({'id': account_id, 'tenant_id': tenant}, {'_id': 0}, session=session)
            if not account:
                raise HTTPException(404, 'Kaynak veya hedef cari hesap bulunamadı')
            if account.get('is_active') is False or str(account.get('status', 'active')).lower() != 'active' or account.get('deleted') or account.get('deleted_at'):
                raise HTTPException(409, 'Yalnız aktif cari hesaplar arasında aktarım yapılabilir')
            accounts.append(account)
        source, target = accounts
        if target.get('account_type') != 'agency':
            raise HTTPException(409, 'Hedef cari hesap acente hesabı olmalı')
        currency = _currency(source)
        if _currency(target) != currency:
            raise HTTPException(409, 'Farklı para birimleri arasında cari aktarımı yapılamaz')
        before = [_balance(source), _balance(target)]
        if amount > before[0]:
            raise HTTPException(422, 'Aktarım tutarı kaynak cari bakiyeyi aşamaz')
        after = [before[0] - amount, before[1] + amount]
        limit = _money(target.get('credit_limit') or 0)
        if limit > 0 and after[1] > limit:
            raise HTTPException(409, 'Hedef acentenin kredi limiti aşılır')
        settings = await database.tenant_settings.find_one({'tenant_id': tenant}, {'_id': 0, 'business_date': 1}, session=session)
        try:
            business_date = date.fromisoformat(str((settings or {}).get('business_date'))).isoformat()
        except ValueError:
            raise HTTPException(409, 'Açık PMS iş günü doğrulanamadı') from None
        now = datetime.now(UTC).isoformat()
        rows = []
        for index, kind in enumerate(('transfer_out', 'transfer_in')):
            rows.append({'id': f'{request_id}:{kind}', 'tenant_id': tenant, 'cari_account_id': accounts[index]['id'],
                'counterparty_account_id': accounts[1-index]['id'], 'booking_id': None, 'transaction_type': kind,
                'amount': float(amount), 'currency': currency, 'business_date': business_date,
                'description': body.description or 'Cari alacağın acenteye devri (tahsilat değil)',
                'transfer_id': request_id, 'posted_by': actor.name or actor.email, 'actor_id': actor.id,
                'created_at': now})
        await database.cari_transactions.insert_many([dict(row) for row in rows], session=session)
        for index, account in enumerate(accounts):
            changed = await database.cari_accounts.update_one({'tenant_id': tenant, 'id': account['id']},
                {'$set': {'balance': float(after[index]), 'current_balance': float(after[index])}}, session=session)
            if changed.matched_count != 1:
                raise HTTPException(409, 'Cari hesap eşzamanlı değişti; aktarım iptal edildi')
        result = {'success': True, 'debit': rows[0], 'credit': rows[1], 'currency': currency,
            'business_date': business_date, 'transfer_id': request_id,
            'before': {source_id: float(before[0]), target_id: float(before[1])},
            'after': {source_id: float(after[0]), target_id: float(after[1])}}
        await database.cari_transfer_operations.insert_one({'_id': operation_id, 'tenant_id': tenant,
            'request_id': request_id, 'fingerprint': fingerprint, 'actor_id': actor.id, 'created_at': now,
            'result': result}, session=session)
        return result

    return await with_resource_locks(client=database.client, db=database, tenant_id=tenant,
        locks_collection='cari_agency_transfer_locks', resources=[('cari', key) for key in sorted({source_id, target_id})] + [('cari_request', request_id)], callback=commit)
