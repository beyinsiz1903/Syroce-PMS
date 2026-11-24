"""Native operator ownership correction, using disposable local transactions."""
import asyncio
from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.pms import folio_window_router as routes
from modules.pms_core import legacy_extra_ownership as service
from tests.test_folio_window_extra_ownership import accounts, db  # noqa: F401


@pytest_asyncio.fixture
async def owned(accounts, monkeypatch):  # noqa: F811
    for name in ('invoices', 'folio_operations'):
        await accounts.create_collection(name)
    await accounts.folios.insert_one({'id': 'second', 'tenant_id': 't', 'booking_id': 'b', 'currency': 'TRY', 'status': 'open'})
    monkeypatch.setattr(service, 'audit_log', AsyncMock())
    monkeypatch.setattr('core.report_cache.invalidate_financial_report_caches', lambda *_: None)
    return accounts


def body(**changes):
    return service.ExtraOwnershipRequest(request_id=uuid4(), booking_id='b', target_folio_id='first',
        extra_ids=['e1', 'e2'], expected_total=200, currency='TRY', reason='Misafirin ilk hesabına ait eski minibar', **changes)


async def assign(request):
    from types import SimpleNamespace
    return await routes.assign_extra_owners(request, SimpleNamespace(id='operator', tenant_id='t'), None)


async def test_explicit_assignment_retains_original_sources_and_retries_once(owned):
    original = await owned.extra_charges.find({'tenant_id': 't', 'id': {'$in': ['e1', 'e2']}}).to_list(None)
    request = body()
    result = await assign(request)
    assert result['assigned_total'] == result['target_balance'] == 200
    assert not result['replayed'] and (await assign(request))['replayed']
    for row in original:
        current = await owned.extra_charges.find_one({'_id': row['_id']})
        assert current == {**row, 'folio_id': 'first'}
    assert await owned.folio_charges.count_documents({}) == await owned.payments.count_documents({}) == 0
    assert await owned.folio_operations.count_documents({}) == 1
    assert (await owned.folios.find_one({'id': 'first'}))['balance'] == 200
    assert (await owned.extra_charges.find_one({'id': 'foreign'})).get('folio_id') is None
    assert (await owned.extra_charges.find_one({'id': 'void'})).get('folio_id') is None


@pytest.mark.parametrize('change', [
    {'expected_total': Decimal('201')}, {'target_folio_id': 'foreign'}, {'currency': 'EUR'},
    {'extra_ids': ['void']}, {'extra_ids': ['foreign']}, {'extra_ids': ['missing']},
])
async def test_invalid_source_or_target_has_no_side_effects(owned, change):
    request = body().model_copy(update=change)
    before = await owned.extra_charges.find({}).to_list(None)
    with pytest.raises(HTTPException):
        await assign(request)
    assert await owned.extra_charges.find({}).to_list(None) == before
    assert await owned.folio_operations.count_documents({}) == 0


@pytest.mark.parametrize('blocker', ['closed', 'checked_out', 'invoice', 'mirrored', 'already_bound'])
async def test_financial_and_ownership_boundaries_reject(owned, blocker):
    if blocker == 'closed':
        await owned.folios.update_one({'id': 'first'}, {'$set': {'status': 'closed'}})
    elif blocker == 'checked_out':
        await owned.bookings.update_one({'id': 'b'}, {'$set': {'status': 'checked_out'}})
    elif blocker == 'invoice':
        await owned.invoices.insert_one({'tenant_id': 't', 'booking_id': 'b', 'status': 'issued'})
    elif blocker == 'mirrored':
        await owned.folio_charges.insert_one({'tenant_id': 't', 'source_extra_charge_id': 'e1'})
    else:
        await owned.extra_charges.update_one({'id': 'e1'}, {'$set': {'folio_id': 'second'}})
    before = deepcopy(await owned.extra_charges.find({}).to_list(None))
    with pytest.raises(HTTPException):
        await assign(body())
    assert await owned.extra_charges.find({}).to_list(None) == before
    assert await owned.folio_operations.count_documents({}) == 0


async def test_audit_failure_rolls_back_and_changed_retry_is_rejected(owned, monkeypatch):
    request = body()
    monkeypatch.setattr(service, 'audit_log', AsyncMock(side_effect=RuntimeError('audit failure')))
    with pytest.raises(RuntimeError, match='audit failure'):
        await assign(request)
    assert await owned.folio_operations.count_documents({}) == 0
    assert (await owned.extra_charges.find_one({'id': 'e1'})).get('folio_id') is None
    monkeypatch.setattr(service, 'audit_log', AsyncMock())
    await assign(request)
    with pytest.raises(HTTPException) as error:
        await assign(request.model_copy(update={'target_folio_id': 'second'}))
    assert error.value.status_code == 409


async def test_concurrent_replay_creates_one_ownership_operation(owned):
    request = body()
    results = await asyncio.gather(assign(request), assign(request))
    assert sum(not result['replayed'] for result in results) == 1
    assert await owned.folio_operations.count_documents({}) == 1
    assert await owned.payments.count_documents({}) == 0
    assert await owned.extra_charges.count_documents({'tenant_id': 't', 'folio_id': 'first'}) == 2
