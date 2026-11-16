"""Reviewed completion of missing department tax, preserving the gross receivable.

Only an unposted source can be completed. The original row and operator's
explicit inclusive-VAT instruction are sealed in the audit in one transaction.
No receipt, service, fiscal invoice or GL journal is created here.
"""
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from core.audit_chain import append_audit_log, compute_record_hash
from core.booking_atomicity import with_resource_locks
from core.integrations.operational_gl_valuation import digest, minor
from modules.pms_core.reporting_financials import report_payment_period_match


def tax_plan(source, rate, reference):
    field = {'parking': 'source_transport_booking_id', 'concierge': 'source_concierge_request_id'}.get(source.get('charge_category'))
    if not field or not source.get(field):
        raise HTTPException(409, 'Yalnız desteklenen hizmetin kaynak bağlantısı olan masrafı incelenebilir')
    if source.get('tax_amount') is not None or source.get('vat_amount') is not None or source.get('tax_breakdown'):
        raise HTTPException(409, 'Mevcut vergi kanıtının üzerine yazılamaz')
    gross = minor(source.get('total'))
    if gross <= 0 or minor(source.get('amount')) != gross or source.get('voided') or source.get('deleted') or not source.get('currency'):
        raise HTTPException(409, 'Kaynak tutarı veya durumu değişti')
    rate = Decimal(str(rate))
    if not rate.is_finite() or rate < 0 or rate > 100 or rate != rate.quantize(Decimal('.01')):
        raise HTTPException(422, 'KDV oranı 0–100 arasında ve en fazla iki ondalık olmalı')
    if len(reference.strip()) < 10:
        raise HTTPException(422, 'Vergi kararının dayanağını en az 10 karakterle belirtin')
    net = int((Decimal(gross) / (1 + rate / 100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    vat = gross - net
    patch = {'amount': net / 100, 'subtotal': net / 100, 'vat_amount': vat / 100,
             'tax_amount': 0, 'tax_breakdown': {'vat': vat / 100, 'accommodation_tax': 0}}
    return {'source_id': source['id'], 'source_hash': digest(source), 'gross': gross / 100,
            'net': net / 100, 'vat': vat / 100, 'currency': source['currency'],
            'vat_rate': str(rate), 'reference': reference.strip(), 'patch': patch}


async def preview(db, tenant, run_id, source_id, rate, reference, session=None):
    kw = {'session': session} if session is not None else {}
    run = await db.night_audit_runs.find_one({'tenant_id': tenant, 'id': run_id, 'status': 'completed'}, {'_id': 0}, **kw)
    if not run:
        raise HTTPException(404, 'Tamamlanmış iş günü bulunamadı')
    period = await db.gl_periods.find_one({'tenant_id': tenant, 'start_date': {'$lte': run['business_date']},
        'end_date': {'$gte': run['business_date']}}, **kw)
    if period and period.get('status') != 'open':
        raise HTTPException(409, 'Kapalı mali dönemin kaynak vergisi değiştirilemez')
    # Use the same source-day membership as GL, including legacy date fields.
    source = await db.folio_charges.find_one({'tenant_id': tenant, 'id': source_id,
        **report_payment_period_match(run['business_date'], run['business_date'], date_fields=('date', 'charge_date', 'posted_at', 'created_at'))}, {'_id': 0}, **kw)
    if not source:
        raise HTTPException(404, 'Bu iş gününe ait kaynak bulunamadı')
    if await db.gl_journal_entries.find_one({'tenant_id': tenant, 'status': 'posted',
            '$or': [{'source_manifest.sources.id': source_id}, {'source_ref': run_id}]}, **kw):
        raise HTTPException(409, 'Muhasebeleşmiş kaynak için bağlı mali düzeltme gerekir')
    category = source.get('charge_category')
    if category == 'concierge':
        linked = await db.concierge_requests.find_one({'tenant_id': tenant, '_id': source.get('source_concierge_request_id')}, **kw)
        if (not linked or linked.get('status') != 'completed' or linked.get('booking_id') != source.get('booking_id')
            or (linked.get('folio_id') and linked['folio_id'] != source.get('folio_id')) or linked.get('folio_charge_id') != source['id']
            or linked.get('currency') != source.get('currency') or minor(linked.get('amount')) != minor(source.get('total'))):
            raise HTTPException(409, 'Concierge kaynağı ve folyo masrafı eşleşmiyor')
    else:
        linked = await db.transport_bookings.find_one({'tenant_id': tenant, 'id': source.get('source_transport_booking_id')}, {'_id': 0}, **kw)
        if (not linked or linked.get('kind') != 'parking_spot' or linked.get('status') == 'cancelled'
            or linked.get('currency') != source.get('currency') or minor(linked.get('total')) != minor(source.get('total'))
            or (linked.get('booking_id') and linked['booking_id'] != source.get('booking_id'))):
            raise HTTPException(409, 'Otopark kaynağı ve folyo masrafı eşleşmiyor')
    plan = tax_plan(source, rate, reference)
    plan.update(run_id=run_id, business_date=run['business_date'], linked_source_hash=digest(linked))
    plan['preview_hash'] = digest(plan)
    return plan, source


async def apply(db, tenant, run_id, payload, actor):
    key = str(uuid5(NAMESPACE_URL, f"department-tax:{tenant}:{payload['expected_preview_hash']}"))

    async def commit(session):
        if session is None:
            raise HTTPException(409, 'Vergi incelemesi atomik işlem gerektirir')
        kw = {'session': session}
        old = await db.department_tax_reviews.find_one({'tenant_id': tenant, 'id': key}, **kw)
        if old:
            current = await db.folio_charges.find_one({'tenant_id': tenant, 'id': old['source_id']}, {'_id': 0}, **kw)
            audit = await db.audit_logs.find_one({'tenant_id': tenant, 'id': key}, {'_id': 0}, **kw)
            sealed = bool(audit and audit.get('seq') and audit.get('record_hash') == old.get('audit_hash')
                and compute_record_hash(audit, audit['seq'], audit.get('prev_hash', '')) == old['audit_hash'])
            if not sealed or old.get('run_id') != run_id or old['request'] != payload or digest(current) != old['after_hash']:
                raise HTTPException(409, 'Önceki inceleme veya kaynak değişti')
            return {'status': 'already_applied', 'review_id': key}
        plan, source = await preview(db, tenant, run_id, payload['source_id'], payload['vat_rate'], payload['reference'], session)
        if plan['preview_hash'] != payload['expected_preview_hash']:
            raise HTTPException(409, 'Kaynak değişti; yeniden önizleyin')
        after = {**source, **plan['patch'], 'tax_review_id': key}
        changed = await db.folio_charges.update_one({'tenant_id': tenant, 'id': source['id'], 'tax_amount': None},
            {'$set': {**plan['patch'], 'tax_review_id': key}}, **kw)
        if changed.modified_count != 1:
            raise HTTPException(409, 'Kaynak eşzamanlı değişti')
        audit = await append_audit_log(db, {'id': key, 'tenant_id': tenant, 'user_id': actor,
            'action': 'department_tax_reviewed', 'entity_type': 'folio_charge', 'entity_id': source['id'],
            'timestamp': datetime.now(UTC).isoformat(), 'before_snapshot': source, 'after_snapshot': after,
            'metadata': {'plan': plan, 'gross_receivable_changed': False, 'receipts_created': 0}}, session=session, require_chain=True)
        await db.department_tax_reviews.insert_one({'id': key, 'tenant_id': tenant, 'source_id': source['id'],
            'run_id': run_id, 'audit_hash': audit['record_hash'], 'request': payload, 'before_hash': digest(source), 'after_hash': digest(after)}, **kw)
        return {'status': 'applied', 'review_id': key}

    result = await with_resource_locks(client=db.client, db=db, tenant_id=tenant, locks_collection='folio_locks',
        resources=[('department_tax', payload['source_id'])], callback=commit)
    from core.report_cache import invalidate_financial_report_caches
    invalidate_financial_report_caches(tenant)
    return result
