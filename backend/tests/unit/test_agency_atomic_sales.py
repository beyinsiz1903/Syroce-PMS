import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from core.agency_sales_guard import agency_sale_guard, durable_agency_replay
from routers import marketplace_b2b as marketplace


class Mutexes:
    def __init__(self):
        self.rows = {}

    async def insert_one(self, row):
        if row['_id'] in self.rows:
            raise DuplicateKeyError('occupied')
        self.rows[row['_id']] = row

    async def delete_one(self, query):
        row = self.rows.get(query['_id'])
        if row and row['owner'] == query['owner']:
            del self.rows[query['_id']]


@pytest.mark.asyncio
async def test_cross_request_serialization_and_uncertain_write_fails_closed():
    database = SimpleNamespace(agency_sale_mutexes=Mutexes())
    async with agency_sale_guard(database, 't', 'a'):
        with pytest.raises(HTTPException) as exc:
            async with agency_sale_guard(database, 't', 'a'):
                pytest.fail('two writers admitted')
        assert exc.value.status_code == 409
        async with agency_sale_guard(database, 'other-hotel', 'a'):
            pass
    assert not database.agency_sale_mutexes.rows
    with pytest.raises(RuntimeError):
        async with agency_sale_guard(database, 't', 'a'):
            raise RuntimeError('unknown commit result')
    assert database.agency_sale_mutexes.rows


@pytest.mark.asyncio
async def test_uncertain_lock_keeps_recovery_context_without_sensitive_request_data():
    database = SimpleNamespace(agency_sale_mutexes=Mutexes())
    with pytest.raises(RuntimeError):
        async with agency_sale_guard(
            database, 'hotel-1', 'agency-1', operation='marketplace_reservation',
            idempotency_key='client-key', reference_id='request-1',
        ):
            raise RuntimeError('database result unknown')
    lock = next(iter(database.agency_sale_mutexes.rows.values()))
    assert lock['recovery_state'] == 'active'
    assert lock['operation'] == 'marketplace_reservation'
    assert lock['idempotency_key'] == 'client-key'
    assert lock['reference_id'] == 'request-1'


@pytest.mark.asyncio
async def test_one_allotment_concurrent_sales_and_retry(monkeypatch):
    database = SimpleNamespace(agency_sale_mutexes=Mutexes())
    occupied = []
    collection = lambda rows: SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=rows)))
    bookings = SimpleNamespace(count_documents=AsyncMock(side_effect=lambda *a: len(occupied)))
    monkeypatch.setattr(marketplace, 'db', SimpleNamespace(bookings=bookings,
        agency_rate_calendar=collection([{'date': '2027-01-01', 'rate_plan_code': 'RO', 'rate': 100, 'availability': 1}]),
        hr_rate_calendar=collection([]), rate_calendar=collection([])))

    async def sale():
        async with agency_sale_guard(database, 't', 'a'):
            quote = await marketplace._marketplace_stay_price(tenant_id='t', agency_id='a', room_type='standard', check_in='2027-01-01', check_out='2027-01-02', fallback_rate=100, rate_plan_code='RO')
            if not quote['sellable']:
                raise HTTPException(409, 'quota')
            await asyncio.sleep(0)
            occupied.append('booking')
            return 'created'
    results = await asyncio.gather(sale(), sale(), return_exceptions=True)
    assert results.count('created') == 1 and len(occupied) == 1
    with pytest.raises(HTTPException):
        await sale()
    occupied.clear()  # Cancellation restores quota through canonical rows.
    assert await sale() == 'created'


@pytest.mark.asyncio
async def test_credit_admission_serializes_different_booking_keys():
    database = SimpleNamespace(agency_sale_mutexes=Mutexes())
    debts = []
    async def sale():
        async with agency_sale_guard(database, 't', 'a'):
            if sum(debts) + 60 > 100:
                raise HTTPException(409, 'credit')
            await asyncio.sleep(0)
            debts.append(60)
    results = await asyncio.gather(sale(), sale(), return_exceptions=True)
    assert len(debts) == 1
    assert sum(isinstance(result, HTTPException) for result in results) == 1
    with pytest.raises(HTTPException):
        await sale()


@pytest.mark.asyncio
async def test_durable_replay_survives_ledger_failure_and_rejects_changed_request():
    database = SimpleNamespace(bookings=SimpleNamespace(find_one=AsyncMock(return_value={'id': 'booking', 'agency_request_hash': 'hash'})))
    result = await durable_agency_replay(database, 't', 'a', 'key', 'hash')
    assert result['idempotent_replay'] and result['reservation']['id'] == 'booking'
    with pytest.raises(HTTPException):
        await durable_agency_replay(database, 't', 'a', 'key', 'different')
