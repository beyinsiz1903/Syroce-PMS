"""Cancel an unpaid, unsealed laundry charge atomically; preserve physical delivery."""
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.audit_chain import append_audit_log
from core.booking_payment_state import refresh_booking_payment_state
from core.tenant_db import tenant_context
from modules.pms_core.receivable_reporting import folio_snapshots


class LaundryChargeVoid(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: uuid.UUID
    expected_amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    reason: str = Field(min_length=3, max_length=500)


async def void_laundry_charge(db, tenant_id, order_id, actor, body):
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()

    async def commit(session):
        kw = {'session': session}
        settings = await db.tenant_settings.find_one({'tenant_id': tenant_id}, **kw) or {}
        order = next((row for row in settings.get('laundry_orders', []) if row.get('id') == order_id), None)
        if not order:
            raise HTTPException(404, 'Çamaşırhane siparişi bulunamadı')
        if order.get('financial_voided'):
            if order.get('financial_void_fingerprint') != fingerprint:
                raise HTTPException(409, 'Bu hizmetin ücreti zaten iptal edildi; özgün işlem kaydını kontrol edin')
            return {**order['financial_void_result'], 'replayed': True}
        if order.get('status') != 'delivered' or not order.get('folio_charged'):
            raise HTTPException(409, 'Bu işlem yalnız teslim edilmiş ve folyoya yazılmış hizmetin ücretini iptal eder')
        charge = await db.folio_charges.find_one({'tenant_id': tenant_id, 'id': order.get('folio_charge_id'),
            'source_laundry_order_id': order_id, 'voided': {'$ne': True}}, **kw)
        if not charge:
            raise HTTPException(409, 'Özgün çamaşırhane ücret kaydı doğrulanamadı')
        bid, fid = charge.get('booking_id'), charge.get('folio_id')
        booking = await db.bookings.find_one({'tenant_id': tenant_id, 'id': bid}, **kw)
        folio = await db.folios.find_one({'tenant_id': tenant_id, 'id': fid, 'booking_id': bid, 'status': 'open'}, **kw)
        if not booking or booking.get('status') not in {'checked_in', 'in_house'} or not folio:
            raise HTTPException(409, 'Ücret iptali için aynı konaklamanın açık hesabı ve içeride misafir gerekli')
        ledger = await db.folio_ledger.find_one({'tenant_id': tenant_id, 'id': charge.get('source_ledger_entry_id'),
            'folio_id': fid, 'booking_id': bid, 'entry_type': 'charge', 'is_voided': {'$ne': True}}, **kw)
        if not ledger or ledger.get('metadata', {}).get('laundry_order_id') != order_id:
            raise HTTPException(409, 'Aktarılmış veya birleştirilmiş hizmetin asıl hesap kaydı önce uzlaştırılmalı')
        day = settings.get('business_date')
        try:
            if date.fromisoformat(str(day)).isoformat() != day:
                raise ValueError
        except ValueError:
            raise HTTPException(409, 'Açık iş günü doğrulanamadı') from None
        period = await db.gl_periods.find_one({'tenant_id': tenant_id,
            'start_date': {'$lte': day}, 'end_date': {'$gte': day}}, **kw)
        if period:
            if period.get('status') != 'open':
                raise HTTPException(409, 'Muhasebe dönemi kapalı; hizmet ücretini değiştirmeyin')
            await db.gl_periods.update_one({'_id': period['_id'], 'tenant_id': tenant_id, 'status': 'open'},
                {'$inc': {'source_revision': 1}}, **kw)
        if not day or charge.get('business_date') != day or ledger.get('business_date') != day:
            raise HTTPException(409, 'Geçmiş iş günü ücreti burada değiştirilemez; ilgili düzeltme akışını kullanın')
        if await db.night_audit_runs.find_one({'tenant_id': tenant_id, 'business_date': day,
                'status': {'$in': ['completed', 'completed_with_exceptions']}}, **kw):
            raise HTTPException(409, 'Kapalı iş gününün hizmet ücreti değiştirilemez')
        if charge.get('invoice_id') or folio.get('invoice_id') or await db.invoices.find_one({'tenant_id': tenant_id,
                'status': {'$ne': 'cancelled'}, '$or': [{'booking_id': bid}, {'folio_id': fid}, {'folio_ids': fid}]}, **kw):
            raise HTTPException(409, 'Faturalı hizmetin belge düzeltme akışını kullanın')
        if charge.get('gl_journal_entry_id') or await db.gl_journal_entries.find_one({'tenant_id': tenant_id,
                '$or': [{'idempotency_key': f'operational-daily:{day}'}, {'source_ref': {'$in': [order_id, charge['id']]}}]}, **kw):
            raise HTTPException(409, 'Muhasebeye aktarılmış hizmet önce muhasebe düzeltme akışında uzlaştırılmalı')
        if await db.billing_concessions.find_one({'tenant_id': tenant_id, 'folio_id': fid,
                'status': {'$in': ['requested', 'applied']}}, **kw):
            raise HTTPException(409, 'İkram veya indirim uygulanmış hesabı önce uzlaştırın')
        try:
            amount = Decimal(str(charge['total']))
            if not amount.is_finite() or amount != body.expected_amount or amount <= 0 or Decimal(str(ledger['amount'])) != amount:
                raise ValueError
        except (ValueError, InvalidOperation, KeyError):
            raise HTTPException(409, 'Hizmet tutarı değişti; yenileyip özgün tutarı doğrulayın') from None
        code = charge.get('currency')
        if code != body.currency or code != folio.get('currency') or code != ledger.get('currency'):
            raise HTTPException(409, 'Hizmet ve hesap para birimleri uyuşmuyor')
        before = (await folio_snapshots(db, tenant_id, [folio], fallback_currency=code,
            include_booking_extras=True, session=session))[fid]
        if any(value > 0 for value in before['payments_by_currency'].values()):
            raise HTTPException(409, 'Hesapta tahsilat veya mahsup var; önce özgün ödeme ve iade akışını uzlaştırın')
        if any(c != code and value for c, value in before['balance_by_currency'].items()) or Decimal(str(before['balance_by_currency'].get(code, 0))) < amount:
            raise HTTPException(409, 'Hizmetin tamamı açık borç olmalı; tahsil edilmiş tutar için ayrı ödeme iadesini kullanın')
        await db.bookings.update_one({'tenant_id': tenant_id, 'id': bid}, {'$inc': {'laundry_post_revision': 1}}, **kw)
        await db.folios.update_one({'tenant_id': tenant_id, 'id': fid}, {'$inc': {'laundry_post_revision': 1}}, **kw)
        now = datetime.now(UTC).isoformat()
        reversal_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'syroce:laundry-void:{tenant_id}:{order_id}'))
        last = await db.folio_ledger.find_one({'tenant_id': tenant_id, 'folio_id': fid}, sort=[('sequence_number', -1)], **kw)
        reversal = {'id': reversal_id, 'tenant_id': tenant_id, 'booking_id': bid, 'folio_id': fid,
            'sequence_number': (last or {}).get('sequence_number', 0) + 1, 'entry_type': 'void',
            'amount': -float(amount), 'currency': code, 'description': 'Ücret iptali: ' + ledger.get('description', '') + ' — ' + body.reason,
            'charge_code': 'LAUNDRY', 'reference_id': ledger['id'], 'is_voided': False,
            'idempotency_key': f'laundry-void:{order_id}', 'posted_at': now, 'posted_by': actor.id, 'business_date': day,
            'metadata': {'laundry_order_id': order_id, 'source_charge_id': charge['id'], 'reason': body.reason}}
        for field in ('net_amount', 'vat_amount', 'tax_amount'):
            if ledger.get(field) is not None:
                reversal[field] = -float(ledger[field])
        await db.folio_ledger.insert_one(reversal, **kw)
        await db.folio_ledger.update_one({'tenant_id': tenant_id, 'id': ledger['id']}, {'$set': {
            'is_voided': True, 'voided_by_entry_id': reversal_id, 'voided_at': now, 'voided_reason': body.reason}}, **kw)
        await db.folio_charges.update_one({'tenant_id': tenant_id, 'id': charge['id']}, {'$set': {
            'voided': True, 'voided_at': now, 'voided_by': actor.id, 'void_reason': body.reason,
            'source_void_ledger_entry_id': reversal_id}}, **kw)
        after = (await folio_snapshots(db, tenant_id, [folio], fallback_currency=code,
            include_booking_extras=True, session=session))[fid]
        balance = after['balance_by_currency'].get(code, 0)
        await db.folios.update_one({'tenant_id': tenant_id, 'id': fid}, {'$set': {'balance': balance}}, **kw)
        await refresh_booking_payment_state(db, tenant_id, bid, session=session, strict=True)
        result = {'success': True, 'id': order_id, 'status': 'delivered', 'financial_voided': True,
            'voided_amount': float(amount), 'currency': code, 'folio_id': fid, 'folio_balance': balance,
            'reversal_entry_id': reversal_id, 'new_payment_or_refund': False, 'replayed': False}
        await db.tenant_settings.update_one({'tenant_id': tenant_id, 'laundry_orders.id': order_id}, {'$set': {
            'laundry_orders.$.financial_voided': True, 'laundry_orders.$.financial_void_reason': body.reason,
            'laundry_orders.$.financial_voided_at': now, 'laundry_orders.$.financial_voided_by': actor.id,
            'laundry_orders.$.financial_void_fingerprint': fingerprint, 'laundry_orders.$.financial_void_result': result,
            'laundry_orders.$.folio_financial_total': 0.0}}, **kw)
        await append_audit_log(db, {'id': str(body.request_id), 'tenant_id': tenant_id, 'user_id': actor.id,
            'action': 'laundry_charge_voided', 'entity_type': 'laundry_order', 'entity_id': order_id,
            'timestamp': now, 'metadata': {'charge_id': charge['id'], 'reversal_entry_id': reversal_id,
                'amount': float(amount), 'currency': code, 'reason': body.reason, 'business_date': day,
                'physical_delivery_preserved': True, 'new_payment_or_refund': False}}, session=session, require_chain=True)
        return result

    with tenant_context(tenant_id):
        async with await db.client.start_session() as session:
            return await session.with_transaction(commit)
