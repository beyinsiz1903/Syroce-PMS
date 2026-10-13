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
    async def guard(db, tenant, agency):
        assert db is database and (tenant, agency) == ('t', 'a')
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
