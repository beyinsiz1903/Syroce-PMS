"""Manual nonresident SPA receipts. Never calls a bank/PSP or a room folio.

GL has its own durable idempotency boundary. A pending claim therefore survives
uncertain posting; only the same request can finish the atomic cash/payment step.
The service sale is accrued separately by normal night audit, like PMS charges.
"""
import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from cache_manager import cache
from core.booking_atomicity import is_replica_set_unavailable, with_resource_locks
from core.business_date_service import ensure_business_date_initialized
from core.integrations.operational_gl_bridge import _payment_account, get_operational_mapping
from core.mice_integrity import money, rounded
from core.security import get_current_user
from core.spa_mice_authz import require_finance
from core.tenant_db import get_system_db
from domains.spa.folio import amounts
from models.schemas import User
from modules.pms_core.reporting_financials import stamp_reporting_values
from modules.pms_core.role_permission_service import RolePermissionService, require_op
from shared_kernel.audit_helper import audit_log
from shared_kernel.gl_posting import GLPostingError, post_journal_entry, verify_journal_entry_hash

router = APIRouter()


class SettlementIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True, extra='forbid')
    request_id: str = Field(min_length=8, max_length=100)
    kind: str = Field('collection', pattern='^(collection|refund)$')
    amount: float = Field(gt=0, le=1_000_000_000)
    method: str = Field(pattern='^(cash|card|bank_transfer)$')
    bank_account_id: str | None = None
    original_payment_id: str | None = None
    reference: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=10, max_length=1000)
    exchange_rate: float | None = Field(None, gt=0, le=1_000_000)


def settlement_totals(charge, rows):
    posted = [r for r in rows if r.get('status') in {'paid', 'refunded'} and not r.get('voided')]
    collected = sum((money(r['amount']) for r in posted if r.get('payment_type') != 'refund'), money(0))
    refunded = sum((money(abs(r['amount'])) for r in posted if r.get('payment_type') == 'refund'), money(0))
    total = money(charge['total'])
    return {'service_total': float(total), 'collected': float(collected), 'refunded': float(refunded),
            'net_collected': float(collected - refunded), 'outstanding': float(max(money(0), total - collected + refunded))}


async def _source(db, tid, appt_id, session=None):
    appt = await db.spa_appointments.find_one({'tenant_id': tid, 'id': appt_id}, session=session)
    if not appt:
        raise HTTPException(404, 'Randevu bulunamadı')
    if appt.get('status') != 'completed' or not appt.get('external_charge_id') or any(
        appt.get(k) for k in ('charge_to_room', 'reservation_id', 'folio_id', 'folio_charge_id')
    ):
        raise HTTPException(409, 'Bağımsız tahsilat için dış misafirin hizmeti tamamlanmış ve satış kaydı oluşmuş olmalıdır; oda hesabından ödeme alınamaz')
    charge = await db.extra_charges.find_one({'tenant_id': tid, 'id': appt['external_charge_id'],
        'source': 'spa_external', 'source_spa_appointment_id': appt_id, 'voided': {'$ne': True}}, session=session)
    net, vat, gross, _ = amounts(appt)
    if not charge or any(charge.get(k) != value for k, value in {
        'amount': float(net), 'total': float(gross), 'vat_amount': float(vat), 'currency': appt.get('currency'),
    }.items()) or charge.get('booking_id') or charge.get('folio_id'):
        raise HTTPException(409, 'SPA satış kaydı tutar/vergi/para birimiyle uyuşmuyor; önce mutabakat gerekli')
    return appt, charge


async def _foreign_carrying_rate(db, tid, charge, session):
    """Require a sealed source-day valuation; never guess foreign AR's rate."""
    run = await db.night_audit_runs.find_one({'tenant_id': tid, 'business_date': charge['business_date'],
        'gl_valued_entry_id': {'$exists': True}}, session=session)
    entry = await db.gl_journal_entries.find_one({'tenant_id': tid, 'id': (run or {}).get('gl_valued_entry_id'),
        'status': 'posted'}, session=session) if run else None
    if (not entry or not verify_journal_entry_hash(entry) or entry.get('reversal_status') or entry.get('reverses_entry_id')
        or entry.get('date') != charge['business_date'] or entry.get('source_ref') != run['id']
        or entry.get('source') not in {'night_audit', 'night_audit_correction'}):
        raise HTTPException(409, 'Döviz SPA satışının kaynak günü muhasebe değerlemesini önce tamamlayın; tahsilat kuru satış kuru yerine kullanılamaz')
    source = next((s for s in entry.get('source_manifest', {}).get('sources', []) if s.get('kind') == 'charge'
        and s.get('id') == charge['id'] and s.get('currency') == charge['currency']), None)
    rate = entry.get('source_manifest', {}).get('valuation', {}).get('rates_to_try', {}).get(charge['currency'])
    if not rate or not source or source.get('gross_minor') != round(charge['total'] * 100) or source.get('tax_minor') != round(charge['vat_amount'] * 100):
        raise HTTPException(409, 'Döviz SPA satışının mühürlü kaynak değeri uyuşmuyor; mutabakat gerekli')
    receivable = entry.get('source_manifest', {}).get('mapping', {}).get('receivable_account_code')
    if not receivable:
        raise HTTPException(409, 'Döviz SPA kaynak alacak hesabı eksik; mutabakat gerekli')
    return money(rate), receivable


@router.get('/appointments/{appt_id}/settlements')
async def list_settlements(appt_id: str, current_user: User = Depends(get_current_user),
                           _perm=Depends(require_op('view_finance_reports'))):
    require_finance(current_user)
    db, tid = get_system_db(), current_user.tenant_id
    appt, charge = await _source(db, tid, appt_id)
    rows = await db.payments.find({'tenant_id': tid, 'source_spa_appointment_id': appt_id}, {'_id': 0}).sort('processed_at', 1).to_list(None)
    accounts = await db.bank_accounts.find({'tenant_id': tid, 'is_active': {'$ne': False}, 'currency': charge['currency']},
        {'_id': 0, 'id': 1, 'name': 1, 'currency': 1}).to_list(None)
    pending = appt.get('finance_pending')
    return {'currency': charge['currency'], 'guest_name': appt.get('guest_name'), 'service_name': appt.get('service_name'),
        'charge_id': charge['id'], 'payments': rows, 'totals': settlement_totals(charge, rows), 'bank_accounts': accounts,
        'pending': {k: pending[k] for k in ('request', 'payment_id', 'started_at')} if pending else None,
        'notice': 'Alınmış veya iade edilmiş paranın manuel kaydıdır. Bankaya/karta ödeme emri göndermez; mali fatura değildir. Oda hesabını değiştirmez. Açık kasa vardiyası gerekir. Dövizde önce kaynak gününün muhasebe değerlemesi tamamlanmalı; farklı kur için ayrı mutabakat gerekir.'}


@router.post('/appointments/{appt_id}/settlements')
async def record_settlement(appt_id: str, body: SettlementIn, current_user: User = Depends(get_current_user),
                            _perm=Depends(require_op('post_payment'))):
    require_finance(current_user)
    if body.kind == 'refund':
        RolePermissionService().enforce_user_permission(current_user, 'void_payment')
    if body.kind == 'collection' and body.original_payment_id:
        raise HTTPException(422, 'Asıl tahsilat yalnız iadede seçilir')
    if money(body.amount) != money(rounded(body.amount)):
        raise HTTPException(422, 'Tutar en fazla iki ondalık basamak içermelidir')
    db, tid = get_system_db(), current_user.tenant_id
    payload = body.model_dump()
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    payment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'spa-settlement:{tid}:{appt_id}:{body.request_id}'))
    scope = {'tenant_id': tid, 'id': appt_id}

    async def claim(session):
        appt, charge = await _source(db, tid, appt_id, session)
        existing = await db.payments.find_one({'tenant_id': tid, 'id': payment_id}, {'_id': 0}, session=session)
        if existing:
            if existing.get('request_fingerprint') != fingerprint:
                raise HTTPException(409, 'İstek anahtarı farklı işlemde kullanılamaz')
            return {'existing': existing}
        pending = appt.get('finance_pending')
        if pending:
            if pending['payment_id'] != payment_id or pending['fingerprint'] != fingerprint:
                raise HTTPException(409, 'Bekleyen finans işlemini aynı istekle tamamlayın')
            return pending
        rows = await db.payments.find({'tenant_id': tid, 'source_spa_appointment_id': appt_id}, session=session).to_list(None)
        amount = money(rounded(body.amount))
        currency = charge['currency']
        if body.kind == 'collection' and amount > money(settlement_totals(charge, rows)['outstanding']):
            raise HTTPException(409, 'Tahsilat hizmetin açık tutarını aşamaz')
        rate = body.exchange_rate or (1 if currency == 'TRY' else None)
        base = rounded(amount * money(rate)) if rate else None
        mapping = await get_operational_mapping(db, tid)
        if not mapping['enabled'] or not mapping['auto_night_audit']:
            raise HTTPException(409, 'SPA tahsilatından önce operasyon muhasebe bağlantısını etkinleştirin')
        accounts = {'settlement': _payment_account(mapping, body.method), 'receivable': mapping['receivable_account_code']}
        if currency == 'TRY' and body.exchange_rate not in {None, 1}:
            raise HTTPException(422, 'TRY için kur 1 olmalıdır')
        if currency != 'TRY' and body.kind == 'collection':
            carrying_rate, accounts['receivable'] = await _foreign_carrying_rate(db, tid, charge, session)
            if rate is None or money(rate) != carrying_rate:
                raise HTTPException(409, 'Tahsilat kuru kayıtlı satış kurundan farklı; kur farkı muhasebesi için yetkili mutabakatı gerekli')
        if body.kind == 'refund':
            original = next((r for r in rows if r['id'] == body.original_payment_id and r.get('status') == 'paid'
                and not r.get('voided') and r.get('payment_type') != 'refund'), None)
            if not original:
                raise HTTPException(422, 'Bu hizmetin geçerli asıl tahsilatını seçin')
            previous = [r for r in rows if r.get('original_payment_id') == original['id'] and r.get('status') == 'refunded' and not r.get('voided')]
            remaining = money(original['amount']) - sum((money(abs(r['amount'])) for r in previous), money(0))
            if amount > remaining:
                raise HTTPException(409, 'İade kalan asıl tahsilatı aşamaz')
            if body.method != original['method'] or body.bank_account_id != original.get('bank_account_id'):
                raise HTTPException(422, 'İade asıl tahsilatın yöntemi ve hesabına yapılmalıdır')
            rate = original['gl_exchange_rate']
            accounts = original['gl_accounts']
            if body.exchange_rate not in {None, rate}:
                raise HTTPException(422, 'İade asıl tahsilatın kayıtlı kurunu kullanır')
            remaining_base = money(original['gl_base_amount']) - sum((money(r['gl_base_amount']) for r in previous), money(0))
            base = rounded(remaining_base) if amount == remaining else rounded(amount * money(rate))
            if amount < remaining and money(base) >= remaining_base:
                raise HTTPException(422, 'Kur yuvarlaması nedeniyle kalan tahsilatı tek işlemde iade edin')
        if rate is None or not base:
            raise HTTPException(422, 'Döviz için TRY muhasebe kuru gereklidir; TRY karşılığı en az bir kuruş olmalıdır')
        if body.method != 'cash':
            bank = await db.bank_accounts.find_one({'tenant_id': tid, 'id': body.bank_account_id,
                'currency': currency, 'is_active': {'$ne': False}}, session=session)
            if not bank:
                raise HTTPException(422, 'Aynı para biriminde aktif banka/kart hesabı seçin')
        elif body.bank_account_id:
            raise HTTPException(422, 'Nakit işleminde banka hesabı seçilemez')
        day = (await ensure_business_date_initialized(db, tid))['business_date']
        shift = await db.cashier_shifts.find_one({'tenant_id': tid, 'status': 'open'}, sort=[('opened_at', -1)], session=session)
        if not shift or shift.get('business_date') not in {None, day}:
            raise HTTPException(409, 'Geçerli iş gününde kasa vardiyasını açın')
        claimed = await db.cashier_shifts.update_one({'_id': shift['_id'], 'tenant_id': tid, 'status': 'open'},
            {'$addToSet': {'spa_pending_ids': payment_id}}, session=session)
        if claimed.matched_count != 1:
            raise HTTPException(409, 'Kasa vardiyası değişti; yenileyin')
        pending = {'payment_id': payment_id, 'fingerprint': fingerprint, 'request': payload, 'currency': currency,
            'amount': float(amount), 'rate': rate, 'base': base, 'business_date': day, 'charge_id': charge['id'],
            'cashier_shift_id': shift['_id'], 'started_at': datetime.now(UTC).isoformat(),
            'actor': getattr(current_user, 'username', None) or current_user.name or current_user.id,
            'actor_id': current_user.id, 'gl_accounts': accounts}
        await db.spa_appointments.update_one(scope, {'$set': {'finance_pending': pending}}, session=session)
        return pending

    async def locked(callback):
        try:
            return await with_resource_locks(client=db.client, db=db, tenant_id=tid,
                locks_collection='spa_locks', resources=[('appointment', appt_id)], callback=callback)
        except Exception as exc:
            if is_replica_set_unavailable(exc):
                raise HTTPException(503, 'SPA tahsilatı için işlem destekleyen veritabanı gereklidir') from exc
            raise

    pending = await locked(claim)
    if 'existing' in pending:
        return {'payment': pending['existing'], 'replayed': True}
    refund = body.kind == 'refund'
    amount = pending['amount']
    code = pending['gl_accounts']['settlement']
    foreign = {'currency': pending['currency'], 'foreign_amount': amount, 'exchange_rate': pending['rate']} if pending['currency'] != 'TRY' else {}
    lines = [{'account_code': code, 'credit' if refund else 'debit': pending['base'], **foreign},
        {'account_code': pending['gl_accounts']['receivable'], 'debit' if refund else 'credit': pending['base'], **foreign}]
    try:
        journal = await post_journal_entry(db, tid, date=pending['business_date'],
            memo=f"SPA {'iade' if refund else 'tahsilat'}: {appt_id} / {body.reference}", lines=lines,
            source='spa_settlement', source_ref=appt_id, actor=pending['actor'], idempotency_key=f'spa-settlement:{payment_id}')
    except GLPostingError as exc:
        raise HTTPException(409, f'Muhasebe kaydı tamamlanamadı; aynı isteği tekrar deneyin: {exc}') from exc
    now = datetime.now(UTC).isoformat()
    payment = {'_id': f'spa-settlement:{payment_id}', 'id': payment_id, 'tenant_id': tid,
        'source_spa_appointment_id': appt_id, 'source_spa_charge_id': pending['charge_id'],
        'receipt_number': 'SPA-' + payment_id.upper(), 'amount': -amount if refund else amount,
        'currency': pending['currency'], 'method': body.method, 'payment_type': 'refund' if refund else 'payment',
        'status': 'refunded' if refund else 'paid', 'reference': body.reference, 'notes': body.reason,
        'bank_account_id': body.bank_account_id, 'original_payment_id': body.original_payment_id,
        'request_id': body.request_id, 'request_fingerprint': fingerprint, 'idempotency_key': f'spa-settlement:{payment_id}',
        'processed_at': now, 'processed_by': pending['actor'], 'business_date': pending['business_date'],
        'gl_journal_entry_id': journal['id'], 'gl_exchange_rate': pending['rate'], 'gl_base_amount': pending['base'],
        'gl_accounts': pending['gl_accounts'],
        'reporting_amount': -pending['base'] if refund else pending['base'], 'reporting_currency': 'TRY', 'voided': False}
    stamp_reporting_values(payment)

    async def finish(session):
        existing = await db.payments.find_one({'tenant_id': tid, 'id': payment_id}, {'_id': 0}, session=session)
        if existing:
            return existing
        appt, _ = await _source(db, tid, appt_id, session)
        if (appt.get('finance_pending') or {}).get('payment_id') != payment_id:
            raise HTTPException(409, 'Bekleyen SPA finans işlemi değişti; yetkili mutabakatı gerekli')
        await db.payments.insert_one(dict(payment), session=session)
        await db.cash_flow.insert_one({'_id': f'spa-settlement:{payment_id}', 'id': payment_id, 'tenant_id': tid,
            'transaction_type': 'expense' if refund else 'income', 'category': 'spa_refund' if refund else 'spa_collection',
            'amount': amount, 'currency': pending['currency'], 'description': body.reason, 'reference_id': payment_id,
            'reference_type': 'payment', 'source_spa_appointment_id': appt_id,
            'date': pending['business_date'], 'created_at': now, 'created_by': pending['actor']}, session=session)
        if body.bank_account_id:
            bank = await db.bank_accounts.update_one({'tenant_id': tid, 'id': body.bank_account_id, 'currency': pending['currency']},
                {'$inc': {'balance': -amount if refund else amount}}, session=session)
            if bank.matched_count != 1:
                raise HTTPException(409, 'Banka hesabı değişti; finans işlemi mutabakat bekliyor')
        transaction = {'id': payment_id, 'amount': pending['base'], 'original_amount': amount, 'currency': pending['currency'],
            'fx_rate': pending['rate'], 'method': body.method, 'direction': 'out' if refund else 'in',
            'type': 'refund' if refund else 'spa_payment', 'description': body.reason, 'ref_type': 'payment', 'ref_id': payment_id,
            'created_at': now, 'timestamp': now, 'created_by': pending['actor'], 'business_date': pending['business_date'],
            'idempotency_key': f'payment:{payment_id}'}
        update = {'$push': {'transactions': transaction}, '$pull': {'spa_pending_ids': payment_id}}
        if body.method == 'cash':
            update['$inc'] = {'cash_out' if refund else 'cash_in': pending['base']}
        shift = await db.cashier_shifts.update_one({'_id': pending['cashier_shift_id'], 'tenant_id': tid, 'status': 'open'}, update, session=session)
        if shift.matched_count != 1:
            raise HTTPException(409, 'Kasa vardiyası kapanmış; finans işlemi mutabakat bekliyor')
        await db.spa_appointments.update_one(scope, {'$unset': {'finance_pending': ''}, '$inc': {'settlement_count': 1}}, session=session)
        await audit_log(actor_id=pending['actor_id'], tenant_id=tid, entity_type='spa_appointment', entity_id=appt_id,
            action=f'spa_{body.kind}', metadata={'payment_id': payment_id, 'charge_id': pending['charge_id'],
                'journal_entry_id': journal['id'], 'amount': amount, 'currency': pending['currency'],
                'business_date': pending['business_date'], 'reason': body.reason}, session=session, require_chain=True)
        return {k: v for k, v in payment.items() if k != '_id'}

    result = await locked(finish)
    for prefix in ('accounting_dashboard', 'report_balance_sheet', 'reports_basic_dashboard_v2'):
        cache.safe_invalidate(tid, prefix)
    return {'payment': result, 'replayed': False}
