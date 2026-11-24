"""Explicitly assign historical unbound extras; never recreate money or guess owners."""
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.pms_core.receivable_reporting import folio_snapshots
from modules.pms_core.report_money import currency_code
from modules.pms_core.reporting_ledger import charge_amount
from shared_kernel.audit_helper import audit_log


class ExtraOwnershipRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: UUID
    booking_id: str = Field(min_length=1, max_length=100)
    target_folio_id: str = Field(min_length=1, max_length=100)
    extra_ids: list[str] = Field(min_length=1, max_length=100)
    expected_total: Decimal = Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('extra_ids')
    @classmethod
    def distinct_ids(cls, value):
        if any(not item or len(item) > 100 for item in value) or len(set(value)) != len(value):
            raise ValueError('Ek ücret kimlikleri tekil olmalı')
        return value


async def assign_legacy_extras(database, tenant_id, actor_id, body, *, session):
    if session is None:
        raise HTTPException(503, 'Ek ücret hesabını bağlamak için transaction gerekli')
    key = f'legacy-extra-owner:{tenant_id}:{body.request_id}'
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()
    prior = await database.folio_operations.find_one({'_id': key, 'tenant_id': tenant_id}, session=session)
    if prior:
        if prior['fingerprint'] != fingerprint:
            raise HTTPException(409, 'İşlem anahtarı farklı bir hesap seçimi için kullanılmış')
        return {**prior['result'], 'replayed': True}
    booking = await database.bookings.find_one({'tenant_id': tenant_id, 'id': body.booking_id}, session=session)
    target = await database.folios.find_one({'tenant_id': tenant_id, 'booking_id': body.booking_id,
        'id': body.target_folio_id, 'status': 'open'}, session=session)
    if not booking or not target:
        raise HTTPException(404, 'Bu rezervasyonda açık hedef hesap bulunamadı')
    if booking.get('status') in {'checked_out', 'cancelled', 'no_show'} or target.get('invoice_id'):
        raise HTTPException(409, 'Kapalı veya faturalı hesabın ayrı düzeltme akışını kullanın')
    if body.currency != currency_code(target.get('currency') or booking.get('currency'), 'TRY'):
        raise HTTPException(409, 'Ek ücret ve hedef hesap para birimi farklı')
    if await database.invoices.find_one({'tenant_id': tenant_id, 'status': {'$ne': 'cancelled'},
            '$or': [{'booking_id': body.booking_id}, {'folio_id': target['id']}, {'folio_ids': target['id']}]}, session=session):
        raise HTTPException(409, 'Faturaya bağlı ek ücretler önce belge akışında uzlaştırılmalı')
    query = {'tenant_id': tenant_id, 'booking_id': body.booking_id, 'id': {'$in': body.extra_ids},
        'folio_id': {'$in': [None, '']}, 'voided': {'$ne': True}}
    rows = await database.extra_charges.find(query, session=session).to_list(None)
    if len(rows) != len(body.extra_ids) or any(r.get('invoice_id') for r in rows):
        raise HTTPException(409, 'Seçilen ek ücret değişti, iptal edildi veya zaten bir hesaba bağlı; yenileyin')
    if any(currency_code(r.get('currency'), body.currency) != body.currency for r in rows):
        raise HTTPException(409, 'Ek ücret ve hedef hesap para birimi farklı')
    if await database.folio_charges.find_one({'tenant_id': tenant_id, 'voided': {'$ne': True},
            '$or': [{'source_extra_charge_id': {'$in': body.extra_ids}}, {'id': {'$in': body.extra_ids}}]}, session=session):
        raise HTTPException(409, 'Ek ücretin bağlı folyo kaydı var; kaynak kaydı üzerinden uzlaştırın')
    values = [Decimal(str(charge_amount({**r, 'report_source': 'extra'}, round_to_cents=False))) for r in rows]
    if any(not v.is_finite() or v < 0 or v != v.quantize(Decimal('.01')) for v in values) or sum(values) != body.expected_total:
        raise HTTPException(409, 'Ek ücret toplamı değişti; yenileyip seçimi doğrulayın')
    await database.bookings.update_one({'tenant_id': tenant_id, 'id': body.booking_id},
        {'$inc': {'folio_window_revision': 1}}, session=session)
    changed = await database.extra_charges.update_many(query, {'$set': {'folio_id': target['id']}}, session=session)
    if changed.modified_count != len(rows):
        raise HTTPException(409, 'Ek ücret sahipliği eşzamanlı değişti; işlem geri alındı')
    snapshot = (await folio_snapshots(database, tenant_id, [target], fallback_currency=body.currency,
        session=session, include_booking_extras=True))[target['id']]
    balance = snapshot['balance_by_currency'].get(body.currency, 0)
    await database.folios.update_one({'tenant_id': tenant_id, 'id': target['id'], 'status': 'open'},
        {'$set': {'balance': balance}}, session=session)
    result = {'success': True, 'target_folio_id': target['id'], 'extra_ids': body.extra_ids,
        'assigned_total': float(body.expected_total), 'currency': body.currency, 'target_balance': balance, 'replayed': False}
    await database.folio_operations.insert_one({'_id': key, 'id': str(body.request_id), 'tenant_id': tenant_id,
        'booking_id': body.booking_id, 'operation_type': 'legacy_extra_ownership', 'fingerprint': fingerprint,
        'performed_at': datetime.now(UTC).isoformat(), 'result': result}, session=session)
    await audit_log(actor_id=actor_id, tenant_id=tenant_id, entity_type='reservation', entity_id=body.booking_id,
        action='legacy_extra_owner_selected', metadata={'target_folio_id': target['id'], 'extra_ids': body.extra_ids,
            'amount': float(body.expected_total), 'currency': body.currency, 'reason': body.reason,
            'new_charge_or_payment': False,
            'previous_owners': {r['id']: r.get('folio_id') for r in rows},
            'original_business_dates': {r['id']: r.get('business_date') for r in rows}}, session=session, require_chain=True)
    return result
