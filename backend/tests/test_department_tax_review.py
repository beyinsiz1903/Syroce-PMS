from copy import deepcopy

import pytest
from fastapi import HTTPException

from core.integrations import department_tax_review as review
from core.integrations.operational_gl_valuation import source_tax_components

pytest_plugins = ('tests.test_report_ledger_mongo_acceptance',)

SOURCE = {'id': 'parking-charge', 'tenant_id': 'hotel', 'booking_id': 'stay', 'folio_id': 'folio',
          'source_transport_booking_id': 'parking', 'charge_category': 'parking', 'amount': 150,
          'total': 150, 'currency': 'TRY', 'business_date': '2026-11-10'}
REF = 'User-authorized synthetic inclusive VAT20 test, not fiscal certification'


def test_inclusive_tax_preserves_gross_and_requires_missing_source_evidence():
    source = deepcopy(SOURCE)
    plan = review.tax_plan(source, '20', REF)
    assert source == SOURCE
    assert (plan['gross'], plan['net'], plan['vat']) == (150, 125, 25)
    assert source_tax_components({**source, **plan['patch']}) == (2500, 0)
    for change in ({'tax_amount': 0}, {'vat_amount': 0}, {'tax_breakdown': {'vat': 0}},
                   {'voided': True}, {'total': 149}, {'charge_category': 'laundry'}):
        with pytest.raises(HTTPException):
            review.tax_plan({**source, **change}, '20', REF)


@pytest.mark.asyncio
async def test_transactional_review_replay_scope_drift_and_no_money_creation(ledger_db, monkeypatch):
    db = ledger_db
    from core import audit_chain
    monkeypatch.setattr(audit_chain, '_system_db', lambda: db)
    await db.night_audit_runs.insert_one({'tenant_id': 'hotel', 'id': 'run', 'business_date': '2026-11-10', 'status': 'completed'})
    await db.folio_charges.insert_one(deepcopy(SOURCE))
    await db.transport_bookings.insert_one({'tenant_id': 'hotel', 'id': 'parking', 'kind': 'parking_spot', 'status': 'reserved', 'currency': 'TRY', 'total': 150, 'booking_id': 'stay'})
    plan, _ = await review.preview(db, 'hotel', 'run', SOURCE['id'], '20', REF)
    payload = {'source_id': SOURCE['id'], 'vat_rate': '20', 'reference': REF, 'expected_preview_hash': plan['preview_hash']}
    bad = {**payload, 'expected_preview_hash': '0' * 64}
    with pytest.raises(HTTPException):
        await review.apply(db, 'hotel', 'run', bad, 'operator')
    assert (await db.folio_charges.find_one({'id': SOURCE['id']}))['amount'] == 150
    result = await review.apply(db, 'hotel', 'run', payload, 'operator')
    assert result['status'] == 'applied'
    assert (await review.apply(db, 'hotel', 'run', payload, 'operator'))['status'] == 'already_applied'
    changed = await db.folio_charges.find_one({'id': SOURCE['id']})
    assert (changed['amount'], changed['total'], changed['vat_amount']) == (125, 150, 25)
    assert await db.audit_logs.count_documents({'action': 'department_tax_reviewed'}) == 1
    assert await db.payments.count_documents({}) == await db.gl_journal_entries.count_documents({}) == 0
    with pytest.raises(HTTPException):
        await review.preview(db, 'other', 'run', SOURCE['id'], '20', REF)
    await db.folio_charges.update_one({'id': SOURCE['id']}, {'$set': {'total': 151}})
    with pytest.raises(HTTPException):
        await review.apply(db, 'hotel', 'run', payload, 'operator')


@pytest.mark.asyncio
async def test_posted_source_is_never_rewritten(ledger_db):
    db = ledger_db
    await db.night_audit_runs.insert_one({'tenant_id': 'hotel', 'id': 'run', 'business_date': '2026-11-10', 'status': 'completed'})
    await db.folio_charges.insert_one(deepcopy(SOURCE))
    await db.transport_bookings.insert_one({'tenant_id': 'hotel', 'id': 'parking', 'kind': 'parking_spot', 'status': 'reserved', 'currency': 'TRY', 'total': 150, 'booking_id': 'stay'})
    await db.gl_journal_entries.insert_one({'tenant_id': 'hotel', 'status': 'posted', 'source_manifest': {'sources': [{'id': SOURCE['id']}]}})
    with pytest.raises(HTTPException, match='Muhasebeleşmiş'):
        await review.preview(db, 'hotel', 'run', SOURCE['id'], '20', REF)
    assert (await db.folio_charges.find_one({'id': SOURCE['id']}))['amount'] == 150


@pytest.mark.asyncio
async def test_closed_period_and_wrong_source_day_stay_read_only(ledger_db):
    db = ledger_db
    await db.night_audit_runs.insert_one({'tenant_id': 'hotel', 'id': 'run', 'business_date': '2026-11-10', 'status': 'completed'})
    await db.folio_charges.insert_one(deepcopy(SOURCE))
    await db.transport_bookings.insert_one({'tenant_id': 'hotel', 'id': 'parking', 'kind': 'parking_spot', 'status': 'reserved', 'currency': 'TRY', 'total': 150, 'booking_id': 'stay'})
    await db.gl_periods.insert_one({'tenant_id': 'hotel', 'start_date': '2026-11-01', 'end_date': '2026-11-30', 'status': 'closed'})
    with pytest.raises(HTTPException, match='Kapalı mali'):
        await review.preview(db, 'hotel', 'run', SOURCE['id'], '20', REF)
    assert await db.department_tax_reviews.count_documents({}) == 0


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_tax_completion(ledger_db, monkeypatch):
    db = ledger_db
    await db.night_audit_runs.insert_one({'tenant_id': 'hotel', 'id': 'run', 'business_date': '2026-11-10', 'status': 'completed'})
    await db.folio_charges.insert_one(deepcopy(SOURCE))
    await db.transport_bookings.insert_one({'tenant_id': 'hotel', 'id': 'parking', 'kind': 'parking_spot', 'status': 'reserved', 'currency': 'TRY', 'total': 150})
    plan, _ = await review.preview(db, 'hotel', 'run', SOURCE['id'], '20', REF)
    async def failed(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(review, 'append_audit_log', failed)
    with pytest.raises(RuntimeError):
        await review.apply(db, 'hotel', 'run', {'source_id': SOURCE['id'], 'vat_rate': '20', 'reference': REF, 'expected_preview_hash': plan['preview_hash']}, 'operator')
    assert (await db.folio_charges.find_one({'id': SOURCE['id']}))['amount'] == 150
    assert await db.department_tax_reviews.count_documents({}) == 0
