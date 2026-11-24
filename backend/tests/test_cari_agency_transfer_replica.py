"""Agency reassignment regressions; disposable LOCAL Mongo only."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from routers import reservation_detail as route
from tests import test_pos_final_consistency_replica as replica_fixtures

db = replica_fixtures.db


async def seed(database, monkeypatch, **target):
    monkeypatch.setattr(route, 'db', database)
    monkeypatch.setattr(route, '_enforce_perm', lambda *_: None)
    await database.cari_accounts.insert_many([
        {'id': 'company', 'tenant_id': 't', 'account_type': 'company', 'currency': 'TRY', 'status': 'active', 'balance': 100, 'current_balance': 100},
        {'id': 'agency', 'tenant_id': 't', 'account_type': 'agency', 'currency': 'TRY', 'status': 'active', 'balance': 0, 'current_balance': 0, **target},
    ])
    await database.tenant_settings.update_one({'tenant_id': 't'}, {'$set': {'business_date': '2026-11-12'}}, upsert=True)
    return SimpleNamespace(tenant_id='t', id='manager', name='Operator', email='operator@example.invalid', role='manager')


def payload(**values):
    model = getattr(route, 'CariAgencyTransfer', route.CariTransfer)
    return model.model_validate({'amount': 25, 'cari_account_id': 'agency', 'description': 'Şirket alacağının acenteye devri', 'request_id': str(uuid4()), **values})


@pytest.mark.asyncio
async def test_foreign_currency_rejected_without_any_writes(db, monkeypatch):
    actor = await seed(db, monkeypatch, currency='USD')
    with pytest.raises(HTTPException) as exc:
        await route.transfer_cari_to_agency('company', payload(), actor, None)
    assert exc.value.status_code == 409
    assert await db.cari_transactions.count_documents({}) == 0
    assert (await db.cari_accounts.find_one({'id': 'company'}))['balance'] == 100


@pytest.mark.asyncio
async def test_atomic_pair_replay_business_day_and_no_collection(db, monkeypatch):
    actor = await seed(db, monkeypatch)
    body = payload()
    first = await route.transfer_cari_to_agency('company', body, actor, None)
    again = await route.transfer_cari_to_agency('company', body, actor, None)
    assert first['after'] == {'company': 75, 'agency': 25}
    assert again['replayed'] and first['transfer_id'] == again['transfer_id']
    assert await db.cari_transactions.count_documents({}) == 2
    assert await db.cari_transfer_operations.count_documents({}) == 1
    for row in await db.cari_transactions.find({}).to_list(None):
        assert row['business_date'] == '2026-11-12' and row['currency'] == 'TRY'
        assert row['transfer_id'] == str(body.request_id)
    assert await db.payments.count_documents({}) == 0
    with pytest.raises(HTTPException) as exc:
        await route.transfer_cari_to_agency('company', payload(request_id=str(body.request_id), amount=26), actor, None)
    assert exc.value.status_code == 409
    assert await db.cari_transactions.count_documents({}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('target', [{'account_type': 'company'}, {'status': 'inactive'}, {'is_active': False}, {'deleted': True}, {'deleted_at': '2026-11-01'}, {'currency': None}, {'credit_limit': 20}, {'tenant_id': 'other'}])
async def test_invalid_target_never_changes_either_account(db, monkeypatch, target):
    actor = await seed(db, monkeypatch, **target)
    with pytest.raises(HTTPException):
        await route.transfer_cari_to_agency('company', payload(), actor, None)
    assert await db.cari_transactions.count_documents({}) == 0
    assert (await db.cari_accounts.find_one({'id': 'company'}))['balance'] == 100


@pytest.mark.asyncio
async def test_concurrent_spending_rechecks_balance_inside_transaction(db, monkeypatch):
    import asyncio
    actor = await seed(db, monkeypatch)
    results = await asyncio.gather(*[route.transfer_cari_to_agency('company', payload(amount=75), actor, None) for _ in range(2)], return_exceptions=True)
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, HTTPException) and item.status_code == 422 for item in results) == 1
    assert (await db.cari_accounts.find_one({'id': 'company'}))['balance'] == 25
    assert (await db.cari_accounts.find_one({'id': 'agency'}))['balance'] == 75
    assert await db.cari_transactions.count_documents({}) == 2


@pytest.mark.asyncio
async def test_concurrent_identical_request_commits_once(db, monkeypatch):
    import asyncio
    actor = await seed(db, monkeypatch)
    body = payload()
    results = await asyncio.gather(*[route.transfer_cari_to_agency('company', body, actor, None) for _ in range(2)])
    assert sum(bool(row.get('replayed')) for row in results) == 1
    assert await db.cari_transactions.count_documents({}) == 2
    assert (await db.cari_accounts.find_one({'id': 'agency'}))['balance'] == 25


@pytest.mark.asyncio
async def test_partial_write_failure_rolls_back_pair_and_source_balance(db, monkeypatch):
    actor = await seed(db, monkeypatch)
    class FailingAccounts:
        def __getattr__(self, key):
            return getattr(db.cari_accounts, key)
        async def update_one(self, query, *args, **kwargs):
            if query['id'] == 'agency':
                raise RuntimeError('Injected failure after source update')
            return await db.cari_accounts.update_one(query, *args, **kwargs)
    class FailingDatabase:
        cari_accounts = FailingAccounts()
        def __getattr__(self, key):
            return getattr(db, key)
        def __getitem__(self, key):
            return db[key]
    monkeypatch.setattr(route, 'db', FailingDatabase())
    with pytest.raises(RuntimeError):
        await route.transfer_cari_to_agency('company', payload(), actor, None)
    assert await db.cari_transactions.count_documents({}) == 0
    assert await db.cari_transfer_operations.count_documents({}) == 0
    assert (await db.cari_accounts.find_one({'id': 'company'}))['balance'] == 100
    assert (await db.cari_accounts.find_one({'id': 'agency'}))['balance'] == 0


@pytest.mark.asyncio
async def test_unreconciled_projection_and_missing_business_day_fail_closed(db, monkeypatch):
    actor = await seed(db, monkeypatch)
    await db.cari_accounts.update_one({'id': 'company'}, {'$set': {'current_balance': 101}})
    with pytest.raises(HTTPException):
        await route.transfer_cari_to_agency('company', payload(), actor, None)
    await db.cari_accounts.update_one({'id': 'company'}, {'$set': {'current_balance': 100}})
    await db.tenant_settings.delete_many({})
    with pytest.raises(HTTPException):
        await route.transfer_cari_to_agency('company', payload(), actor, None)
    assert await db.cari_transactions.count_documents({}) == 0


@pytest.mark.parametrize('amount', [0, -1, 'NaN', 'Infinity', '0.001'])
def test_precision_and_invalid_amounts_are_rejected(amount):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        payload(amount=amount)
