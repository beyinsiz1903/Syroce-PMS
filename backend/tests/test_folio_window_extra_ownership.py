"""Opening another account must preserve the sole account's legacy extras."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.pms import folio_window_router as routes
from modules.pms_core.receivable_reporting import folio_snapshots
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest_asyncio.fixture
async def accounts(db, monkeypatch):  # noqa: F811
    for name in ('bookings', 'folios', 'extra_charges', 'folio_charges', 'payments', 'reservation_financial_locks'):
        await db.create_collection(name)
    await db.bookings.insert_one({'id': 'b', 'tenant_id': 't', 'currency': 'TRY'})
    await db.folios.insert_one({'id': 'first', 'tenant_id': 't', 'booking_id': 'b', 'currency': 'TRY', 'status': 'open'})
    await db.extra_charges.insert_many([
        {'id': 'e1', 'tenant_id': 't', 'booking_id': 'b', 'amount': 120, 'currency': 'TRY'},
        {'id': 'e2', 'tenant_id': 't', 'booking_id': 'b', 'amount': 80, 'currency': 'TRY', 'folio_id': ''},
        {'id': 'foreign', 'tenant_id': 'other', 'booking_id': 'b', 'amount': 900},
        {'id': 'void', 'tenant_id': 't', 'booking_id': 'b', 'amount': 60, 'voided': True},
    ])
    monkeypatch.setattr(routes, 'db', db)
    monkeypatch.setattr(routes, '_INDEX_DONE', False)
    monkeypatch.setattr(routes, 'generate_folio_number', AsyncMock(return_value='F-NEW'))
    monkeypatch.setattr(routes, 'audit_log', AsyncMock())
    return db


async def open_account():
    return await routes.open_window(routes.WindowCreate(booking_id='b', payor_type='guest'),
        SimpleNamespace(id='operator', tenant_id='t'), None)


async def test_second_account_preserves_original_extra_ids_amounts_and_owner(accounts):
    result = await open_account()
    rows = await accounts.folios.find({'tenant_id': 't'}).to_list(None)
    snaps = await folio_snapshots(accounts, 't', rows, fallback_currency='TRY', include_booking_extras=True)
    assert snaps['first']['balance_by_currency'] == {'TRY': 200}
    assert snaps[result.folio_id]['balance_by_currency'] == {}
    assert await accounts.extra_charges.count_documents({'tenant_id': 't', 'folio_id': 'first'}) == 2
    assert (await accounts.extra_charges.find_one({'id': 'foreign'})).get('folio_id') is None
    assert (await accounts.extra_charges.find_one({'id': 'void'})).get('folio_id') is None
    assert await accounts.extra_charges.count_documents({}) == 4
    assert await accounts.payments.count_documents({}) == 0
    routes.audit_log.assert_awaited_once()
    assert routes.audit_log.call_args.kwargs['metadata']['legacy_extras_bound'] == 2


async def test_audit_failure_rolls_back_both_binding_and_account(accounts, monkeypatch):
    monkeypatch.setattr(routes, 'audit_log', AsyncMock(side_effect=RuntimeError('audit unavailable')))
    with pytest.raises(RuntimeError, match='audit unavailable'):
        await open_account()
    assert await accounts.folios.count_documents({'tenant_id': 't'}) == 1
    assert (await accounts.extra_charges.find_one({'id': 'e1'})).get('folio_id') is None
    assert (await accounts.extra_charges.find_one({'id': 'e2'}))['folio_id'] == ''


async def test_ambiguous_historical_extras_block_new_account_without_guessing(accounts):
    await accounts.folios.insert_one({'id': 'second', 'tenant_id': 't', 'booking_id': 'b', 'status': 'open'})
    with pytest.raises(HTTPException) as error:
        await open_account()
    assert error.value.status_code == 409
    assert await accounts.folios.count_documents({'tenant_id': 't'}) == 2
    assert (await accounts.extra_charges.find_one({'id': 'e1'})).get('folio_id') is None


async def test_parallel_account_opening_does_not_reassign_or_duplicate_extras(accounts):
    results = await asyncio.gather(open_account(), open_account(), return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]
    assert successes
    assert all(not isinstance(r, Exception) or isinstance(r, HTTPException) and r.status_code == 409 for r in results)
    assert await accounts.extra_charges.count_documents({'tenant_id': 't', 'folio_id': 'first'}) == 2
    assert await accounts.extra_charges.count_documents({}) == 4
    windows = await accounts.folios.find({'tenant_id': 't'}).to_list(None)
    assert len({routes._resolve_window_number(w, windows) for w in windows}) == len(windows)
