from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from routers import agency_contracts
from routers import marketplace_b2b as m


def collection(rows):
    return SimpleNamespace(find=lambda *args: SimpleNamespace(to_list=AsyncMock(return_value=rows)))


def test_proposal_requires_plan_and_valid_dates():
    payload = {'check_in':'2027-01-01', 'check_out':'2027-01-02', 'room_type':'standard', 'reason':'Guest request'}
    with pytest.raises(ValidationError):
        m.ModificationProposalCreate(**payload)
    assert m.ModificationProposalCreate(**payload, rate_plan_code='BB').rate_plan_code == 'BB'
    with pytest.raises(ValidationError):
        m.ModificationProposalCreate(**{**payload, 'check_out': '2027-01-01'}, rate_plan_code='BB')


@pytest.mark.asyncio
async def test_quote_excludes_self_and_applies_occupancy(monkeypatch):
    bookings = SimpleNamespace(count_documents=AsyncMock(return_value=0))
    monkeypatch.setattr(m, 'db', SimpleNamespace(bookings=bookings,
        agency_rate_calendar=collection([{'date':'2027-01-01', 'rate_plan_code':'BB', 'rate':100, 'availability':1}]),
        hr_rate_calendar=collection([]), rate_calendar=collection([])))
    occupancy = AsyncMock(side_effect=lambda **kw: {**kw['pricing'], 'total_price':130})
    monkeypatch.setattr(m, '_marketplace_occupancy_price', occupancy)
    result = await m._validated_agency_quote(tenant_id='t', agency_id='a',
        room={'room_type':'standard', 'capacity':3}, check_in='2027-01-01', check_out='2027-01-02',
        rate_plan_code='BB', adults=2, children=1, child_ages=[7], exclude_booking_id='b')
    assert result['total_price'] == 130
    assert bookings.count_documents.call_args.args[0]['id'] == {'$ne':'b'}
    assert occupancy.call_args.kwargs['child_ages'] == [7]


@pytest.mark.asyncio
async def test_credit_replaces_old_booking_not_double_counts(monkeypatch):
    queries = []
    def run(query, *_args):
        queries.append(query)
        return SimpleNamespace(to_list=AsyncMock(return_value=[{'currency': 'TRY', 'net_to_hotel': 40}]))
    monkeypatch.setattr(m, 'db', SimpleNamespace(bookings=SimpleNamespace(find=run)))
    contract = {'credit_limit': 100, 'credit_currency': 'TRY'}
    await m._check_agency_credit(tenant_id='t', agency_id='a', contract=contract, net_to_hotel=60, booking_currency='TRY', exclude_booking_id='b')
    assert queries[0]['id'] == {'$ne':'b'}
    with pytest.raises(HTTPException):
        await m._check_agency_credit(tenant_id='t', agency_id='a', contract=contract, net_to_hotel=61, booking_currency='TRY', exclude_booking_id='b')


@pytest.fixture
def decision(monkeypatch):
    proposal = {'id':'p','tenant_id':'t','agency_id':'a','reservation_id':'b',
        'type':'agency_modification','status':'awaiting_hotel',
        'requested':{'check_in':'2027-01-01','check_out':'2027-01-02','room_type':'standard','rate_plan_code':'BB'}}
    booking = {'id':'b','agency_id':'a','status':'confirmed','adults':2,'children':1,'child_ages':[7], 'syroce_b2b_fee_pct':2}
    rooms = collection([{'id':'r','room_type':'standard','capacity':3,'base_price':100}])
    database = SimpleNamespace(rooms=rooms, bookings=SimpleNamespace(find_one=AsyncMock(return_value=booking),update_one=AsyncMock()),
        marketplace_negotiations=SimpleNamespace(find_one=AsyncMock(return_value=proposal),update_one=AsyncMock()),
        marketplace_bookings=SimpleNamespace(update_one=AsyncMock()))
    monkeypatch.setattr(m,'db',database)
    monkeypatch.setattr(m,'get_system_db',lambda:database)
    monkeypatch.setattr(m,'_require_hotel_admin',lambda user:'t')
    monkeypatch.setattr(agency_contracts,'has_active_contract',AsyncMock(return_value={'status':'approved','commission_pct':10}))
    monkeypatch.setattr(m,'_get_listing_or_404',AsyncMock(return_value={}))
    monkeypatch.setattr(m,'_validated_agency_quote',AsyncMock(return_value={'total_price':130,'nightly_rates':[{'date':'2027-01-01','rate':130}], 'meal_plan':'BB'}))
    monkeypatch.setattr(m,'_check_agency_credit',AsyncMock())
    monkeypatch.setattr(m,'assign_room_atomic',AsyncMock())
    return database, proposal, booking


@pytest.mark.asyncio
async def test_decision_persists_product_and_checks_before_assignment(decision):
    database, _, _ = decision
    await m._decide_marketplace_modification_locked('p', m.CancellationProposalDecision(accept=True), object())
    quote = m._validated_agency_quote.call_args.kwargs
    assert quote['rate_plan_code']=='BB' and quote['exclude_booking_id']=='b' and quote['child_ages']==[7]
    assert m._check_agency_credit.call_args.kwargs['net_to_hotel']==117
    changes=database.bookings.update_one.call_args.args[1]['$set']
    assert changes['rate_plan_code']=='BB' and changes['meal_plan']=='BB' and changes['net_to_hotel']==117
    assert changes['credit_exposure_amount'] == 117
    assert changes['credit_exposure_currency'] == 'TRY'
    assert changes['syroce_b2b_fee_amount']==2.6
    assert m.assign_room_atomic.call_args_list[0].kwargs['release_obsolete'] is False
    assert 'release_obsolete' not in m.assign_room_atomic.call_args_list[1].kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['credit','plan','capacity','blocked','ages'])
async def test_rejected_change_does_not_move_room_or_update_booking(decision, monkeypatch, failure):
    database, proposal, booking=decision
    if failure=='credit':
        m._check_agency_credit.side_effect=HTTPException(409,'limit')
    elif failure=='plan':
        proposal['requested'].pop('rate_plan_code')
    elif failure=='capacity':
        booking['adults']=10
    elif failure=='blocked':
        m._get_listing_or_404.return_value={'blocked_dates':['2027-01-01']}
    else:
        m._validated_agency_quote.side_effect=HTTPException(422,'ages')
    with pytest.raises(HTTPException):
        await m._decide_marketplace_modification_locked('p',m.CancellationProposalDecision(accept=True),object())
    m.assign_room_atomic.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_failure_does_not_release_original_nights(decision):
    database, _, _ = decision
    database.bookings.update_one.side_effect = RuntimeError('storage unavailable')
    with pytest.raises(RuntimeError):
        await m._decide_marketplace_modification_locked('p',m.CancellationProposalDecision(accept=True),object())
    assert m.assign_room_atomic.await_count == 1
    assert m.assign_room_atomic.call_args.kwargs['release_obsolete'] is False


@pytest.mark.asyncio
async def test_decision_uses_same_admission_fence_as_creation(decision, monkeypatch):
    from core.agency_sales_guard import agency_sale_guard
    database, _, _ = decision
    occupied = set()
    async def insert(row):
        if row['_id'] in occupied:
            raise DuplicateKeyError('busy')
        occupied.add(row['_id'])
    async def delete(query):
        occupied.remove(query['_id'])
    database.agency_sale_mutexes = SimpleNamespace(insert_one=insert, delete_one=delete)
    internal = AsyncMock(return_value={'ok':True})
    monkeypatch.setattr(m, '_decide_marketplace_modification_locked', internal)
    async with agency_sale_guard(database, 't', 'a'):
        with pytest.raises(HTTPException) as error:
            await m.hotel_decide_marketplace_modification('p',m.CancellationProposalDecision(accept=True),object())
        assert error.value.status_code == 409
    internal.assert_not_awaited()
    await m.hotel_decide_marketplace_modification('p',m.CancellationProposalDecision(accept=True),object())
    internal.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('children,ages,capacity', [(1,[],3),(1,[18],3),(0,[],1)])
async def test_real_quote_rejects_missing_ages_and_capacity(children,ages,capacity):
    with pytest.raises(HTTPException):
        await m._validated_agency_quote(tenant_id='t', agency_id='a', room={'capacity':capacity},
            check_in='2027-01-01',check_out='2027-01-02',rate_plan_code='BB',adults=2,children=children,child_ages=ages)


@pytest.mark.asyncio
async def test_room_claim_can_retain_original_locks_until_commit(monkeypatch):
    from core import atomic_booking as atomic
    monkeypatch.setattr(atomic, '_find_overlapping_active_booking', AsyncMock(return_value=None))
    monkeypatch.setattr(atomic, '_claim_night_or_get_owner', AsyncMock(return_value=(True,None)))
    locks=SimpleNamespace(delete_many=AsyncMock())
    monkeypatch.setattr(atomic,'db',SimpleNamespace(room_night_locks=locks))
    result=await atomic.assign_room_atomic(tenant_id='t',booking_id='b',room_id='r',
        check_in='2027-01-01T14:00:00',check_out='2027-01-02T11:00:00',release_obsolete=False)
    assert result['success']
    locks.delete_many.assert_not_awaited()
