from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from routers import agency_portal as portal


def test_portal_requires_product_and_retry_identity():
    with pytest.raises(ValidationError):
        portal.AgencyReservationCreate(room_type_id='s', check_in='2027-01-01',
                                       check_out='2027-01-02', guest_name='Test Guest')


def test_legacy_contract_base_rate_fallback_is_explicitly_opt_in():
    base = {
        'contract_name': 'Acente sözleşmesi', 'start_date': '2027-01-01', 'end_date': '2027-12-31',
        'contract_type': 'commission', 'commission_rate': 10,
    }
    assert portal.AgencyContractCreate(**base).allow_base_rate_fallback is False
    assert portal.AgencyContractCreate(**base, allow_base_rate_fallback=True).allow_base_rate_fallback is True


@pytest.mark.asyncio
async def test_retry_returns_existing_booking_without_second_write(monkeypatch):
    from core import agency_sales_guard, tenant_db

    user = SimpleNamespace(tenant_id='t', agency_id='a')
    data = portal.AgencyReservationCreate(room_type_id='s', rate_plan_code='BB', idempotency_key='attempt',
                                         check_in='2027-01-01', check_out='2027-01-02', guest_name='Test Guest')
    monkeypatch.setattr(portal, '_require_agency_user', lambda user: None)
    monkeypatch.setattr(portal, '_active_agency_for', AsyncMock(return_value={'id': 'a'}))
    database = object()
    monkeypatch.setattr(tenant_db, 'get_system_db', lambda: database)
    entered = []

    @asynccontextmanager
    async def guard(db, tenant, agency, **kwargs):
        assert db is database and (tenant, agency) == ('t', 'a')
        assert kwargs == {'operation': 'hotel_portal_reservation', 'idempotency_key': 'attempt'}
        entered.append(True)
        yield

    monkeypatch.setattr(agency_sales_guard, 'agency_sale_guard', guard)
    result = {'ok': True, 'reservation': {'id': 'existing'}, 'idempotent_replay': True}
    monkeypatch.setattr(agency_sales_guard, 'durable_agency_replay', AsyncMock(return_value=result))
    create = AsyncMock()
    monkeypatch.setattr(portal, 'agency_portal_create_reservation', create)
    assert await portal.agency_portal_create_reservation_endpoint(data, user) == result
    assert entered
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('minimum,expected', [(1, [1000, 1500]), (3, [])])
async def test_legacy_availability_uses_distributed_plans_not_base_price(monkeypatch, minimum, expected):
    from routers import marketplace_b2b as marketplace

    def collection(rows):
        return SimpleNamespace(find=lambda *args: SimpleNamespace(to_list=AsyncMock(return_value=rows)))

    rows = [{'date': '2027-01-01', 'rate_plan_code': plan, 'rate': price, 'min_stay': minimum}
            for plan, price in [('RO', 1000), ('BB', 1500)]]
    database = SimpleNamespace(
        rooms=collection([{'id': 'r', 'room_type': 's', 'capacity': 2, 'base_price': 99}]),
        bookings=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
        tenants=SimpleNamespace(find_one=AsyncMock(return_value={'currency': 'TRY'})),
        agency_contracts=SimpleNamespace(find_one=AsyncMock(return_value={'id': 'signed-legacy', 'contract_type': 'commission', 'commission_rate': 0})),
        agency_rate_calendar=collection(rows), hr_rate_calendar=collection([]), rate_calendar=collection([]),
    )
    monkeypatch.setattr(portal, 'db', database)
    monkeypatch.setattr(marketplace, 'db', database)
    monkeypatch.setattr(portal, '_require_agency_user', lambda user: None)
    monkeypatch.setattr(portal, '_active_agency_for', AsyncMock(return_value={'id': 'a'}))
    monkeypatch.setattr(portal, '_get_b2b_allotment', AsyncMock(return_value=None))
    monkeypatch.setattr(portal, '_get_b2b_price', AsyncMock(return_value=(99, False)))
    response = await portal.agency_portal_availability('2027-01-01', '2027-01-02', 2, 0,
                                                      SimpleNamespace(tenant_id='t', agency_id='a'))
    assert sorted(offer['stay_total'] for offer in response['room_types']) == expected
    if expected:
        assert {offer['rate_plan_code'] for offer in response['room_types']} == {'RO', 'BB'}


@pytest.mark.asyncio
async def test_legacy_availability_uses_the_same_base_rate_contract_option_as_booking(monkeypatch):
    from routers import marketplace_b2b as marketplace

    def collection(rows):
        return SimpleNamespace(find=lambda *args, **kwargs: SimpleNamespace(to_list=AsyncMock(return_value=rows)))

    database = SimpleNamespace(
        rooms=collection([{'id': 'r', 'room_type': 's', 'capacity': 2, 'base_price': 99}]),
        bookings=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
        tenants=SimpleNamespace(find_one=AsyncMock(return_value={'currency': 'TRY'})),
        agency_contracts=SimpleNamespace(find_one=AsyncMock(return_value={'allow_base_rate_fallback': True})),
        agency_rate_calendar=collection([]),
        hr_rate_calendar=collection([{'date': '2027-01-01', 'rate_plan_code': 'BASE', 'rate': 1000}]),
        rate_calendar=collection([]),
    )
    monkeypatch.setattr(portal, 'db', database)
    monkeypatch.setattr(marketplace, 'db', database)
    monkeypatch.setattr(portal, '_require_agency_user', lambda user: None)
    monkeypatch.setattr(portal, '_active_agency_for', AsyncMock(return_value={'id': 'a'}))
    monkeypatch.setattr(portal, '_get_b2b_allotment', AsyncMock(return_value=None))
    monkeypatch.setattr(portal, '_get_b2b_price', AsyncMock(return_value=(99, True)))

    response = await portal.agency_portal_availability('2027-01-01', '2027-01-02', 2, 0,
                                                       SimpleNamespace(tenant_id='t', agency_id='a'))
    assert response['room_types'][0]['rate_plan_code'] == 'BASE'
    assert response['room_types'][0]['stay_total'] == 1000


@pytest.mark.asyncio
@pytest.mark.parametrize('allowed', [True, False])
async def test_empty_calendars_only_offer_base_when_contract_opts_in(monkeypatch, allowed):
    from routers import marketplace_b2b as marketplace
    def collection():
        return SimpleNamespace(find=lambda *args: SimpleNamespace(to_list=AsyncMock(return_value=[])))
    monkeypatch.setattr(marketplace, 'db', SimpleNamespace(agency_rate_calendar=collection(), hr_rate_calendar=collection(), rate_calendar=collection()))
    plans = await marketplace._agency_rate_plans('t', 'a', 's', '2027-01-01', '2027-01-02', allow_base_rate_fallback=allowed)
    result = await marketplace._marketplace_stay_price(tenant_id='t', agency_id='a', room_type='s', check_in='2027-01-01', check_out='2027-01-02', fallback_rate=1000, rate_plan_code='BASE', allow_base_rate_fallback=allowed)
    assert plans == (['BASE'] if allowed else [])
    assert result['sellable'] is allowed
    if allowed:
        assert result['total_price'] == 1000


@pytest.mark.asyncio
@pytest.mark.parametrize('allowed', [True, False])
async def test_booking_passes_contract_policy_to_actual_pricer(monkeypatch, allowed):
    from routers import marketplace_b2b as marketplace
    from security import guest_write
    def collection(rows):
        return SimpleNamespace(find=lambda *args: SimpleNamespace(to_list=AsyncMock(return_value=rows)))
    database = SimpleNamespace(rooms=collection([{'id': 'r', 'room_type': 's', 'base_price': 1000}]),
        bookings=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
        agency_contracts=SimpleNamespace(find_one=AsyncMock(return_value={'allow_base_rate_fallback': allowed})))
    monkeypatch.setattr(portal, 'db', database)
    monkeypatch.setattr(portal, '_require_agency_user', lambda user: None)
    monkeypatch.setattr(portal, '_active_agency_for', AsyncMock(return_value={'id': 'a'}))
    monkeypatch.setattr(portal, '_get_b2b_allotment', AsyncMock(return_value=None))
    monkeypatch.setattr(portal, '_get_b2b_price', AsyncMock(return_value=(1000, True)))
    monkeypatch.setattr(guest_write, 'encrypt_guest_insert', lambda doc: doc)
    pricer = AsyncMock(side_effect=RuntimeError('pricing boundary reached'))
    monkeypatch.setattr(marketplace, '_marketplace_stay_price', pricer)
    data = portal.AgencyReservationCreate(room_type_id='s', rate_plan_code='BASE', idempotency_key='attempt',
        check_in='2027-01-01', check_out='2027-01-02', guest_name='Test Guest')
    with pytest.raises(RuntimeError, match='pricing boundary reached'):
        await portal.agency_portal_create_reservation(data, SimpleNamespace(tenant_id='t', agency_id='a'))
    assert pricer.call_args.kwargs['allow_base_rate_fallback'] is allowed


@pytest.mark.asyncio
async def test_contract_policy_update_scoped_to_hotel_and_agency(monkeypatch):
    update = AsyncMock(return_value=SimpleNamespace(matched_count=1))
    monkeypatch.setattr(portal, 'db', SimpleNamespace(agency_contracts=SimpleNamespace(update_one=update)))
    monkeypatch.setattr(portal, '_require_hotel_staff', lambda user: None)
    await portal.update_agency_rate_policy('a', 'c', portal.AgencyRatePolicy(allow_base_rate_fallback=True), SimpleNamespace(tenant_id='t', id='staff'))
    assert update.call_args.args[0] == {'id': 'c', 'agency_id': 'a', 'tenant_id': 't'}
    assert update.call_args.args[1]['$set']['rate_policy_updated_by'] == 'staff'
