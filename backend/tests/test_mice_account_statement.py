"""Isolated local Mongo: corporate quotes must never become receivables."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import mice_finance as finance
from tests.test_mice_mongo_acceptance import USER, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


@pytest.fixture
async def setup(wired, monkeypatch):  # noqa: F811
    monkeypatch.setattr(finance, 'get_system_db', lambda: wired)
    await wired.mice_accounts.insert_one({'tenant_id': 'A', 'id': 'company'})
    return wired


async def sale(db, eid, currency='TRY', total=3000, **extra):
    await db.mice_events.insert_one({'tenant_id': 'A', 'id': eid, 'client_account_id': 'company', 'name': eid, 'currency': currency, 'totals': {'grand_total': total}, 'gl_journal_entry_id': eid, **extra})
    await db.gl_journal_entries.insert_one({'tenant_id': 'A', 'id': eid, 'source': 'mice', 'source_ref': eid, 'status': 'posted', 'lines': [{'account_code': '120', 'debit': total if currency == 'TRY' else total * 40, 'currency': currency, 'foreign_amount': total}]})


@pytest.mark.asyncio
async def test_posted_sale_refund_and_currencies_stay_separate(setup):
    await sale(setup, 'try')
    await sale(setup, 'usd', 'USD', 100)
    for pid, value, refund in [('pay', 1000, False), ('refund', 200, True)]:
        await setup.payments.insert_one({'tenant_id': 'A', 'id': pid, 'mice_event_id': 'try', 'currency': 'TRY', 'amount': -value if refund else value, 'status': 'refunded' if refund else 'paid', 'payment_type': 'refund' if refund else 'deposit', 'gl_journal_entry_id': pid})
        await setup.gl_journal_entries.insert_one({'tenant_id': 'A', 'id': pid, 'source': 'mice_settlement', 'source_ref': 'try', 'status': 'posted', 'lines': [{'account_code': '120', 'debit' if refund else 'credit': value}]})
    result = await finance.account_statement('company', USER)
    assert result['totals_by_currency']['TRY'] == {'posted_total': 3000, 'net_collected': 800, 'outstanding': 2200, 'customer_credit': 0}
    assert result['totals_by_currency']['USD']['outstanding'] == 100
    assert result['excluded_count'] == 0


@pytest.mark.asyncio
async def test_quotes_pending_folio_and_foreign_journal_excluded(setup):
    await sale(setup, 'quote', gl_journal_entry_id=None)
    await sale(setup, 'pending', finance_pending={'request': 'pending'})
    await sale(setup, 'folio', reservation_id='booking')
    await sale(setup, 'wrong')
    await setup.gl_journal_entries.update_one({'id': 'wrong'}, {'$set': {'tenant_id': 'B'}})
    result = await finance.account_statement('company', USER)
    assert result['totals_by_currency'] == {}
    assert result['excluded_count'] == 4
    assert all(row['outstanding'] is None for row in result['rows'])


@pytest.mark.asyncio
async def test_unverified_receipt_does_not_silently_reduce_debt(setup):
    await sale(setup, 'event')
    await setup.payments.insert_one({'tenant_id': 'A', 'mice_event_id': 'event', 'amount': 100, 'currency': 'TRY', 'status': 'paid'})
    result = await finance.account_statement('company', USER)
    assert result['rows'][0]['net_collected'] is None
    assert result['rows'][0]['outstanding'] is None
    assert result['totals_by_currency'] == {}


@pytest.mark.asyncio
async def test_tenant_and_finance_access(setup):
    with pytest.raises(HTTPException) as error:
        await finance.account_statement('company', SimpleNamespace(tenant_id='B', role='admin', roles=['admin']))
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await finance.account_statement('company', SimpleNamespace(tenant_id='A', role='housekeeping', roles=['housekeeping']))
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_folio_charge_conflict_and_reversed_sale_not_counted(setup):
    await sale(setup, 'conflict')
    await setup.folio_charges.insert_one({'tenant_id': 'A', 'mice_event_id': 'conflict', 'amount': 3000})
    await sale(setup, 'reversed')
    await setup.gl_journal_entries.update_one({'id': 'reversed'}, {'$set': {'reversal_status': 'reversed'}})
    result = await finance.account_statement('company', USER)
    assert result['excluded_count'] == 2
    assert result['totals_by_currency'] == {}


@pytest.mark.asyncio
async def test_duplicate_receipt_journal_excluded_and_voids_ignored(setup):
    await sale(setup, 'event')
    await setup.gl_journal_entries.insert_one({'tenant_id': 'A', 'id': 'payment', 'source': 'mice_settlement', 'source_ref': 'event', 'status': 'posted', 'lines': [{'account_code': '120', 'credit': 100}]})
    for pid in ['p1', 'p2']:
        await setup.payments.insert_one({'tenant_id': 'A', 'id': pid, 'mice_event_id': 'event', 'currency': 'TRY', 'amount': 100, 'status': 'paid', 'gl_journal_entry_id': 'payment'})
    result = await finance.account_statement('company', USER)
    assert result['totals_by_currency'] == {}
    await setup.payments.update_one({'id': 'p2'}, {'$set': {'voided': True}})
    result = await finance.account_statement('company', USER)
    assert result['totals_by_currency']['TRY']['outstanding'] == 2900
