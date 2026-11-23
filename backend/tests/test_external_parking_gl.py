"""Real local Mongo journal acceptance; historical transport rows stay unchanged."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

from core.external_parking_gl import post_parking_payment_to_gl
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def seed(db, method='cash'):
    await db.gl_operational_mappings.insert_one({'tenant_id': 't', 'enabled': True})
    await db.gl_accounts.insert_many([{'tenant_id': 't', 'code': code, 'name': code, 'type': kind, 'active': True}
        for code, kind in [('100', 'asset'), ('108', 'asset'), ('102', 'asset'), ('600', 'revenue'), ('391', 'liability')]])
    await db.transport_bookings.insert_one({'tenant_id': 't', 'id': 'parking', 'kind': 'parking_spot',
        'customer_type': 'external', 'currency': 'TRY', 'total': 150, 'vat_rate': 20,
        'schedule': {'start_date': '2026-11-12', 'num_days': 1}, 'receipt_id': 'receipt', 'refund_id': 'refund', 'status': 'cancelled'})
    common = {'tenant_id': 't', 'transport_booking_id': 'parking', 'currency': 'TRY', 'amount': 150,
        'net': 125, 'vat_amount': 25, 'business_date': '2026-11-12', 'method': method, 'manual_record': True}
    await db.transport_payments.insert_many([{**common, 'id': 'receipt', 'kind': 'receipt', 'reference': 'Original receipt'},
        {**common, 'id': 'refund', 'kind': 'refund', 'reference': 'Full refund', 'original_receipt_id': 'receipt'}])


@pytest.mark.parametrize('method,account', [('cash', '100'), ('card', '108'), ('bank_transfer', '102')])
async def test_receipt_refund_and_retries_preserve_sources_and_net_zero(ledger_db, method, account):  # noqa: F811
    db = ledger_db
    await seed(db, method)
    before = deepcopy(await db.transport_payments.find({}).to_list(None))
    with pytest.raises(HTTPException, match='Önce özgün'):
        await post_parking_payment_to_gl(db, 't', 'refund', 'manager')
    receipt = await post_parking_payment_to_gl(db, 't', 'receipt', 'manager')
    assert receipt['journal']['total_debit'] == receipt['journal']['total_credit'] == 150
    lines = {r['account_code']: r for r in receipt['journal']['lines']}
    assert lines[account]['debit'] == 150 and lines['600']['credit'] == 125 and lines['391']['credit'] == 25
    # A mapping change cannot revalue the original refund or create a new receipt.
    await db.gl_operational_mappings.update_one({'tenant_id': 't'}, {'$set': {'cash_account_code': 'not-used'}})
    refund = await post_parking_payment_to_gl(db, 't', 'refund', 'manager')
    assert refund['journal']['reverses_entry_id'] == receipt['journal']['id']
    for original, reversed_line in zip(receipt['journal']['lines'], refund['journal']['lines']):
        assert original['account_code'] == reversed_line['account_code']
        assert original['debit'] == reversed_line['credit'] and original['credit'] == reversed_line['debit']
    for key in ('receipt', 'refund'):
        assert (await post_parking_payment_to_gl(db, 't', key, 'manager'))['replayed']
    assert await db.gl_journal_entries.count_documents({}) == 2
    assert await db.transport_payments.find({}).to_list(None) == before
    assert await db.folio_charges.count_documents({}) == await db.payments.count_documents({}) == 0


@pytest.mark.parametrize('change', [{'currency': 'USD'}, {'net': 150, 'vat_amount': 0}, {'amount': 151}, {'net': float('nan')}])
async def test_bad_or_foreign_evidence_cannot_post(ledger_db, change):  # noqa: F811
    await seed(ledger_db)
    await ledger_db.transport_payments.update_one({'id': 'receipt'}, {'$set': change})
    with pytest.raises(HTTPException):
        await post_parking_payment_to_gl(ledger_db, 't', 'receipt', 'manager')
    assert await ledger_db.gl_journal_entries.count_documents({}) == 0


async def test_closed_period_foreign_tenant_and_future_service_fail_closed(ledger_db):  # noqa: F811
    await seed(ledger_db)
    with pytest.raises(HTTPException) as missing:
        await post_parking_payment_to_gl(ledger_db, 'other', 'receipt', 'manager')
    assert missing.value.status_code == 404
    await ledger_db.transport_bookings.update_one({'id': 'parking'}, {'$set': {'schedule.start_date': '2026-11-13'}})
    with pytest.raises(HTTPException, match='dönemsel'):
        await post_parking_payment_to_gl(ledger_db, 't', 'receipt', 'manager')
    await ledger_db.transport_bookings.update_one({'id': 'parking'}, {'$set': {'schedule.start_date': '2026-11-12'}})
    await ledger_db.gl_periods.insert_one({'tenant_id': 't', 'start_date': '2026-11-01', 'end_date': '2026-11-30', 'status': 'closed'})
    with pytest.raises(HTTPException):
        await post_parking_payment_to_gl(ledger_db, 't', 'receipt', 'manager')
    assert await ledger_db.gl_journal_entries.count_documents({}) == 0


async def test_changed_source_after_post_is_conflict_not_second_journal(ledger_db):  # noqa: F811
    await seed(ledger_db)
    await post_parking_payment_to_gl(ledger_db, 't', 'receipt', 'manager')
    await ledger_db.transport_payments.update_one({'id': 'receipt'}, {'$set': {'amount': 160}})
    with pytest.raises(HTTPException, match='mührü'):
        await post_parking_payment_to_gl(ledger_db, 't', 'receipt', 'manager')
    assert await ledger_db.gl_journal_entries.count_documents({}) == 1


async def test_parallel_retry_only_posts_one_receipt_and_closed_retry_is_safe(ledger_db):  # noqa: F811
    import asyncio
    await seed(ledger_db)
    results = await asyncio.gather(*(post_parking_payment_to_gl(ledger_db, 't', 'receipt', 'manager') for _ in range(2)))
    assert results[0]['journal']['id'] == results[1]['journal']['id']
    assert await ledger_db.gl_journal_entries.count_documents({}) == 1
    await ledger_db.gl_periods.update_many({}, {'$set': {'status': 'closed'}})
    assert (await post_parking_payment_to_gl(ledger_db, 't', 'receipt', 'manager'))['replayed']


async def test_accounting_role_boundary_and_no_generic_reversal(ledger_db, monkeypatch):  # noqa: F811
    from types import SimpleNamespace

    from domains.accounting.gl_router import _journal_reversal_blocker
    from domains.pms import transfer_parking_router as parking
    monkeypatch.setattr(parking, 'db', ledger_db)
    with pytest.raises(HTTPException) as denied:
        await parking.post_external_parking_gl('receipt', SimpleNamespace(id='desk', tenant_id='t', role='front_desk', is_super_admin=False))
    assert denied.value.status_code == 403
    assert _journal_reversal_blocker({'source': 'external_parking_payment'}, False)
    assert await ledger_db.gl_journal_entries.count_documents({}) == 0
