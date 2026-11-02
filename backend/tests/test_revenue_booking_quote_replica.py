"""Explicit pricing selection and its real booking/folio readback contract."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from core.channel_room_charge_pricing import calculate_room_charge
from core.provider_nightly_rates import booking_daily_rate_plan
from core.security import get_current_user
from domains.pms import operations_router as ops
from modules.pms_core.revenue_booking_quote import accept_quote, quote
from routers import pms_bookings, reservation_detail
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pricing(acceptance, monkeypatch):
    a = acceptance
    start = datetime.now(UTC).date() + timedelta(days=20)
    await a.db.rooms.update_one({'id': 'synthetic-room'}, {'$set': {'room_type': 'Standard', 'is_active': True, 'status': 'available'}})
    await a.db.guests.insert_one({'tenant_id': 'qa', 'id': 'synthetic-guest', 'name': 'Yapay Misafir'})
    await a.db.hotel_settings.insert_one({'tenant_id': 'qa', 'currency': 'USD'})
    await a.db.revenue_settings.insert_one({'tenant_id': 'qa',
        'hurdle_rates': {'Standard': {'min_rate': 90, 'bar': 100, 'active': True}},
        'day_pricing': {'Standard': {('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')[start.weekday()]: {'rate': 80, 'min_stay': 2}}}})
    monkeypatch.setattr(ops, 'db', a.db)
    monkeypatch.setattr(pms_bookings, 'db', a.db)
    monkeypatch.setattr(pms_bookings, 'get_db_for_tenant', lambda tenant: a.db)
    monkeypatch.setattr(pms_bookings, 'record_booking_consent', AsyncMock())
    monkeypatch.setattr(pms_bookings, 'generate_folio_number', AsyncMock(return_value='LOCAL-REVENUE-FOLIO'))
    monkeypatch.setattr(pms_bookings, '_publish_multi_room_booking_created_events', AsyncMock())
    from core import atomic_booking
    monkeypatch.setattr(atomic_booking, 'db', a.db)
    app = FastAPI()
    app.include_router(ops.router)
    app.include_router(pms_bookings.router)
    app.dependency_overrides[get_current_user] = lambda: a.user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-price-acceptance') as api:
        yield a, api, start


async def calculate(a, start, **extra):
    return await quote(a.db, 'qa', 'synthetic-room', start.isoformat(), (start + timedelta(days=2)).isoformat(), extra.get('currency', 'USD'))


async def test_explicit_bar_day_floor_and_arrival_minimum_produce_a_complete_plan(pricing):
    a, api, start = pricing
    result = await calculate(a, start)
    assert [r['amount'] for r in result['daily_rates']] == [90, 100]
    assert result['total_amount'] == 190 and result['currency'] == 'USD'
    assert not result['provider_write'] and result['currency_confirmation_required']
    booking = {'pricing_source': 'revenue_controls', 'revenue_quote_snapshot': result,
        'check_in': start.isoformat(), 'check_out': (start + timedelta(days=2)).isoformat(), 'total_amount': 190, 'currency': 'USD'}
    assert list(booking_daily_rate_plan(booking).values()) == [9000, 10000]
    # Source per-night prices survive both detail and the shared audit engine;
    # never silently average 90/100 to 95/95.
    assert [r['rate'] for r in reservation_detail._complete_daily_rates_for_stay([], booking)] == [90, 100]
    assert calculate_room_charge(booking, start.isoformat())['total'] == 90
    assert calculate_room_charge(booking, (start + timedelta(days=1)).isoformat())['total'] == 100


async def test_stale_plan_different_total_currency_and_under_minimum_cannot_be_accepted(pricing):
    from fastapi import HTTPException

    a, api, start = pricing
    result = await calculate(a, start)
    for amount, code in [(189, 'USD'), (190, 'EUR'), (True, 'USD')]:
        with pytest.raises(HTTPException):
            await accept_quote(a.db, 'qa', 'synthetic-room', start.isoformat(), (start + timedelta(days=2)).isoformat(), code, amount, result['quote_hash'])
    with pytest.raises(HTTPException) as error:
        await quote(a.db, 'qa', 'synthetic-room', start.isoformat(), (start + timedelta(days=1)).isoformat(), 'USD')
    assert error.value.status_code == 409
    await a.db.revenue_settings.update_one({'tenant_id': 'qa'}, {'$set': {'hurdle_rates.Standard.bar': 120}})
    with pytest.raises(HTTPException) as error:
        await accept_quote(a.db, 'qa', 'synthetic-room', start.isoformat(), (start + timedelta(days=2)).isoformat(), 'USD', 190, result['quote_hash'])
    assert error.value.status_code == 409


@pytest.mark.parametrize('code', [None, 'EUR'])
async def test_missing_or_changed_hotel_currency_never_relabels_plan_money(pricing, code):
    from fastapi import HTTPException

    a, api, start = pricing
    await a.db.hotel_settings.update_one({'tenant_id': 'qa'}, {'$set': {'currency': code}})
    with pytest.raises(HTTPException) as error:
        await calculate(a, start)
    assert error.value.status_code == 409


async def test_quote_http_requires_currency_confirmation_and_booking_permission(pricing):
    a, api, start = pricing
    body = {'room_id': 'synthetic-room', 'check_in': start.isoformat(),
        'check_out': (start + timedelta(days=2)).isoformat(), 'currency': 'USD', 'confirm_currency': False}
    assert (await api.post('/api/revenue/booking-quote', json=body)).status_code == 422
    body['confirm_currency'] = True
    assert (await api.post('/api/revenue/booking-quote', json=body)).status_code == 200
    a.user.role = 'housekeeping'
    assert (await api.post('/api/revenue/booking-quote', json=body)).status_code == 403
    a.user.role = 'admin'; a.user.tenant_id = 'foreign'
    assert (await api.post('/api/revenue/booking-quote', json=body)).status_code == 404


async def test_multi_room_path_retains_confirmed_plan_and_folio_currency(pricing):
    a, api, start = pricing
    result = await calculate(a, start)
    body = {'guest_id': 'synthetic-guest', 'arrival_date': start.isoformat(),
        'departure_date': (start + timedelta(days=2)).isoformat(), 'currency': 'USD', 'rooms': [
            {'room_id': 'synthetic-room', 'adults': 1, 'children': 0, 'total_amount': 190,
                'apply_revenue_pricing': True, 'revenue_quote_hash': result['quote_hash']}]}
    response = await api.post('/api/pms/bookings/multi-room', json=body, headers={'Idempotency-Key': 'quote-multi'})
    assert response.status_code == 200, response.text
    booking = response.json()[0]
    assert booking['currency'] == 'USD' and booking['revenue_quote_snapshot'] == result
    folio = await a.db.folios.find_one({'booking_id': booking['id']})
    assert folio['currency'] == 'USD'
    replay = await api.post('/api/pms/bookings/multi-room', json=body, headers={'Idempotency-Key': 'quote-multi'})
    assert replay.status_code == 200 and replay.json()[0]['id'] == booking['id']


async def test_multi_room_folio_currency_is_correct_even_without_using_a_revenue_plan(pricing):
    a, api, start = pricing
    body = {'guest_id': 'synthetic-guest', 'arrival_date': start.isoformat(),
        'departure_date': (start + timedelta(days=2)).isoformat(), 'currency': 'EUR', 'rooms': [
            {'room_id': 'synthetic-room', 'adults': 1, 'children': 0, 'total_amount': 200}]}
    response = await api.post('/api/pms/bookings/multi-room', json=body)
    assert response.status_code == 200, response.text
    assert (await a.db.folios.find_one({'booking_id': response.json()[0]['id']}))['currency'] == 'EUR'


@pytest.mark.parametrize('change', [
    {'adults': True}, {'adults': 1.5}, {'children': -1}, {'children_ages': [True]},
    {'total_amount': -1}, {'total_amount': 'NaN'}, {'total_amount': 'Infinity'},
    {'total_amount': True}, {'total_amount': 1.001}, {'apply_revenue_pricing': 'true'},
])
async def test_multi_room_invalid_terms_never_create_guest_booking_or_folio(pricing, change):
    a, api, start = pricing
    before = {name: await a.db[name].count_documents({}) for name in ('guests', 'bookings', 'folios')}
    body = {'guest': {'name': 'Never persist invalid guest', 'email': 'invalid@example.invalid'},
        'arrival_date': start.isoformat(), 'departure_date': (start + timedelta(days=2)).isoformat(),
        'currency': 'USD', 'rooms': [{'room_id': 'synthetic-room', 'adults': 1, 'total_amount': 200, **change}]}
    result = await api.post('/api/pms/bookings/multi-room', json=body)
    assert result.status_code == 422, result.text
    for name, count in before.items():
        assert await a.db[name].count_documents({}) == count


async def test_multi_room_foreign_guest_and_duplicate_physical_room_are_rejected(pricing):
    a, api, start = pricing
    body = {'guest_id': 'foreign-guest', 'arrival_date': start.isoformat(),
        'departure_date': (start + timedelta(days=2)).isoformat(), 'currency': 'USD',
        'rooms': [{'room_id': 'synthetic-room', 'adults': 1, 'total_amount': 200}]}
    assert (await api.post('/api/pms/bookings/multi-room', json=body)).status_code == 404
    body['guest_id'] = 'synthetic-guest'; body['rooms'] *= 2
    assert (await api.post('/api/pms/bookings/multi-room', json=body)).status_code == 409


async def test_multi_room_denies_role_without_create_permission_and_inactive_rooms(pricing):
    a, api, start = pricing
    body = {'guest_id': 'synthetic-guest', 'arrival_date': start.isoformat(),
        'departure_date': (start + timedelta(days=2)).isoformat(), 'currency': 'USD',
        'rooms': [{'room_id': 'synthetic-room', 'adults': 1, 'total_amount': 200}]}
    a.user.role = 'housekeeping'
    assert (await api.post('/api/pms/bookings/multi-room', json=body)).status_code == 403
    a.user.role = 'admin'
    await a.db.rooms.update_one({'id': 'synthetic-room'}, {'$set': {'is_active': False}})
    assert (await api.post('/api/pms/bookings/multi-room', json=body)).status_code == 404
    assert await a.db.bookings.count_documents({}) == 1


@pytest.mark.parametrize('change', [{'currency': 'EUR'}, {'daily_rates': []}, {'daily_rates': [
    {'date': '2000-01-01', 'amount': 190}]}])
async def test_incomplete_or_mismatched_quote_snapshot_is_not_authoritative(pricing, change):
    a, api, start = pricing
    result = {**await calculate(a, start), **change}
    booking = {'pricing_source': 'revenue_controls', 'revenue_quote_snapshot': result,
        'check_in': start.isoformat(), 'check_out': (start + timedelta(days=2)).isoformat(),
        'total_amount': 190, 'currency': 'USD'}
    assert booking_daily_rate_plan(booking) is None


@pytest.mark.parametrize('missing', ['booking', 'folio'])
async def test_incomplete_multi_room_retry_never_reports_partial_group_as_success(pricing, missing):
    a, api, start = pricing
    await a.db.rooms.insert_one({'id': 'second-room', 'tenant_id': 'qa', 'is_active': True, 'room_type': 'Standard'})
    body = {'guest_id': 'synthetic-guest', 'arrival_date': start.isoformat(),
        'departure_date': (start + timedelta(days=2)).isoformat(), 'currency': 'USD',
        'rooms': [{'room_id': rid, 'adults': 1, 'total_amount': 200} for rid in ('synthetic-room', 'second-room')]}
    headers = {'Idempotency-Key': 'partial-group-recovery'}
    first = await api.post('/api/pms/bookings/multi-room', json=body, headers=headers)
    assert first.status_code == 200, first.text
    bid = first.json()[1]['id']
    # Crash/failed-compensation fixture, confined to the generated local DB.
    await a.db['bookings' if missing == 'booking' else 'folios'].delete_one(
        {'id': bid} if missing == 'booking' else {'booking_id': bid})
    before = {name: await a.db[name].count_documents({}) for name in ('bookings', 'folios', 'room_night_locks')}
    retry = await api.post('/api/pms/bookings/multi-room', json=body, headers=headers)
    assert retry.status_code == 409, retry.text
    for name, count in before.items():
        assert await a.db[name].count_documents({}) == count
