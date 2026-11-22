"""Manual parking receipts/refunds for external customers; never touch guest folios."""
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.audit_chain import append_audit_log
from core.booking_atomicity import with_resource_locks
from core.tenant_db import tenant_context
from shared_kernel.audit_helper import build_audit_entry


class ParkingSettlement(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    method: Literal['cash', 'card', 'bank_transfer']
    reference: str = Field(min_length=3, max_length=240)


async def record_parking_settlement(database, tenant_id, booking_id, actor_id, body, *, refund=False):
    kind = 'refund' if refund else 'receipt'
    key = f'parking:{tenant_id}:{kind}:{body.request_id}'
    payload = {'booking_id': booking_id, **body.model_dump(mode='json', exclude={'request_id'})}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    async def commit(session):
        previous = await database.transport_payments.find_one({'tenant_id': tenant_id, 'id': key}, session=session)
        if previous:
            if previous.get('fingerprint') != fingerprint:
                raise HTTPException(409, 'İşlem anahtarı farklı bir otopark ödemesi için kullanılmış')
            return {'payment': {k: v for k, v in previous.items() if k != '_id'}, 'replayed': True}
        source = await database.transport_bookings.find_one({'tenant_id': tenant_id, 'id': booking_id}, session=session)
        if not source or source.get('customer_type') != 'external' or source.get('kind') != 'parking_spot':
            raise HTTPException(404, 'Dış müşteri otopark kaydı bulunamadı')
        if source.get('room_number') or source.get('booking_id') or source.get('folio_id') or source.get('folio_charged'):
            raise HTTPException(409, 'Bu kaynak bir oda/folyo ile bağlı; dış ödeme kaydedilemez')
        if source.get('status') != 'reserved':
            raise HTTPException(409, 'İptal edilmiş otopark kaydına ödeme işlenemez')
        code = source.get('currency')
        gross = Decimal(str(source['total'])).quantize(Decimal('.01'))
        if code != body.currency or gross != body.amount:
            raise HTTPException(409, 'Ödeme tutarı veya para birimi kaynakla uyuşmuyor')
        if source.get('vat_rate') is None:
            raise HTTPException(409, 'Otopark kaynağının toplama dahil KDV oranı gerekli')
        rate = Decimal(str(source['vat_rate'])) / 100
        net = (gross / (1 + rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        if refund:
            if source.get('payment_status') != 'paid' or not source.get('receipt_id'):
                raise HTTPException(409, 'İade için önce tek bir kayıtlı ödeme olmalı')
            original = await database.transport_payments.find_one({'tenant_id': tenant_id, 'id': source['receipt_id'],
                'transport_booking_id': booking_id, 'kind': 'receipt'}, session=session)
            if not original or original['method'] != body.method:
                raise HTTPException(409, 'İade yöntemi kayıtlı ödeme ile aynı olmalı')
        elif source.get('payment_status') not in {None, 'unpaid'}:
            raise HTTPException(409, 'Bu otopark ödemesi zaten kaydedilmiş')
        settings = await database.tenant_settings.find_one({'tenant_id': tenant_id}, session=session) or {}
        try:
            day = date.fromisoformat(settings.get('business_date', '')).isoformat()
        except (TypeError, ValueError):
            raise HTTPException(409, 'Açık iş günü doğrulanamadı') from None
        if await database.night_audit_runs.find_one({'tenant_id': tenant_id, 'business_date': day,
            'status': {'$in': ['completed', 'completed_with_exceptions']}}, session=session):
            raise HTTPException(409, 'Kapalı iş gününe otopark ödemesi kaydedilemez')
        changed = await database.tenant_settings.update_one({'tenant_id': tenant_id, 'business_date': day},
            {'$inc': {'parking_payment_revision': 1}}, session=session)
        if changed.matched_count != 1:
            raise HTTPException(409, 'İş günü değişti; ödeme kaydedilmedi')
        now = datetime.now(UTC).isoformat()
        payment = {'_id': key, 'id': key, 'tenant_id': tenant_id, 'transport_booking_id': booking_id,
            'kind': kind, 'amount': float(gross), 'net': float(net), 'vat_amount': float(gross - net),
            'currency': code, 'method': body.method, 'reference': body.reference, 'business_date': day,
            'created_at': now, 'created_by': actor_id, 'fingerprint': fingerprint,
            'original_receipt_id': source.get('receipt_id') if refund else None, 'manual_record': True}
        await database.transport_payments.insert_one(dict(payment), session=session)
        update = {'payment_status': 'refunded' if refund else 'paid', 'payment_method': body.method, 'updated_at': now,
            'refund_id' if refund else 'receipt_id': key}
        await database.transport_bookings.update_one({'tenant_id': tenant_id, 'id': booking_id}, {'$set': update}, session=session)
        await append_audit_log(database, build_audit_entry(actor_id, tenant_id, 'transport_booking', booking_id,
            'external_parking_' + kind, {'payment_id': key, 'amount': float(gross), 'currency': code,
                'method': body.method, 'reference': body.reference, 'business_date': day}), session=session, require_chain=True)
        payment.pop('_id')
        return {'payment': payment, 'replayed': False}

    with tenant_context(tenant_id):
        return await with_resource_locks(client=database.client, db=database, tenant_id=tenant_id,
            locks_collection='transport_payment_locks', resources=[('transport_booking', booking_id)], callback=commit)
