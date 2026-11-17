from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from domains.pms import frontdesk_router as frontdesk
from routers import walkin


def request(key='walkin-1'):
    return Request({'type': 'http', 'headers': [(b'idempotency-key', key.encode())]})


@pytest.mark.asyncio
async def test_legacy_walkin_delegates_without_creating_a_second_folio(monkeypatch):
    canonical = AsyncMock(return_value={'booking_id': 'b', 'total_amount': 900})
    monkeypatch.setattr(frontdesk, 'create_walk_in_booking', canonical)
    user = SimpleNamespace(tenant_id='hotel')
    result = await walkin.walkin_checkin(walkin.WalkinRequest(guest_name='Deniz Aksoy', room_id='r', nights=3, currency='USD', total_amount=900), request(), user)
    payload = canonical.await_args.args[0]
    assert (payload.rate_per_night, payload.nights, payload.guest_name) == (300, 3, 'Deniz Aksoy')
    assert payload.currency == 'USD'
    assert result['balance'] == 900 and result['booking_id'] == 'b'
    assert canonical.await_args.kwargs['http_request'].headers['Idempotency-Key'] == 'walkin-1'


@pytest.mark.asyncio
@pytest.mark.parametrize('paid', [1, -1, float('nan'), float('inf')])
async def test_legacy_walkin_never_writes_unguarded_payments(monkeypatch, paid):
    canonical = AsyncMock()
    monkeypatch.setattr(frontdesk, 'create_walk_in_booking', canonical)
    with pytest.raises(HTTPException):
        await walkin.walkin_checkin(walkin.WalkinRequest(guest_name='Deniz Aksoy', room_id='r', total_amount=900, payment_amount=paid), request(), SimpleNamespace(tenant_id='hotel'))
    canonical.assert_not_awaited()


@pytest.mark.asyncio
async def test_room_search_uses_open_day_full_fourteen_nights_and_physical_readiness(monkeypatch):
    rooms = MagicMock()
    rooms.find.return_value.to_list = AsyncMock(return_value=[])
    bookings = MagicMock()
    bookings.find.return_value.__aiter__.return_value = []
    monkeypatch.setattr(walkin, 'db', SimpleNamespace(rooms=rooms, bookings=bookings))
    monkeypatch.setattr(walkin, 'ensure_business_date_initialized', AsyncMock(return_value={'business_date': '2026-11-12'}))
    result = await walkin.available_rooms(14, SimpleNamespace(tenant_id='hotel'))
    assert (result['business_date'], result['check_out']) == ('2026-11-12', '2026-11-26')
    room_filter = rooms.find.call_args.args[0]
    assert room_filter['is_virtual'] == {'$ne': True}
    assert room_filter['status']['$in'] == ['available', 'inspected', 'clean']
    assert bookings.find.call_args.args[0]['check_out'] == {'$gt': '2026-11-12'}


@pytest.mark.asyncio
@pytest.mark.parametrize("nights", [1, 2, 14])
async def test_canonical_walkin_uses_business_day_atomic_booking_and_checkin(monkeypatch, nights):
    from datetime import date, timedelta

    from core import atomic_booking, atomic_checkin_checkout
    from shared_kernel import idempotency
    guard = SimpleNamespace(release=AsyncMock(), complete=AsyncMock())
    monkeypatch.setattr(idempotency, 'begin_idempotency', AsyncMock(return_value=(guard, None)))
    db = SimpleNamespace(rooms=SimpleNamespace(find_one=AsyncMock(return_value={'id':'r','room_number':'101','status':'clean'})),
        kbs_cloud_configs=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        guests=SimpleNamespace(find_one=AsyncMock(return_value={'id':'g'})))
    monkeypatch.setattr(frontdesk, 'db', db)
    monkeypatch.setattr(frontdesk, 'ensure_business_date_initialized', AsyncMock(return_value={'business_date':'2026-11-12'}))
    async def assert_atomic_date_contract(**kwargs):
        booking = kwargs['booking_doc']
        # Exercise the real downstream parser instead of accepting any mock payload.
        assert atomic_booking._night_dates(booking['check_in'], booking['check_out']) == [(date(2026, 11, 12) + timedelta(days=n)).isoformat() for n in range(nights)]

    create = AsyncMock(side_effect=assert_atomic_date_contract)
    checkin = AsyncMock(return_value={'checked_in_at':'2026-11-16T15:00:00Z'})
    monkeypatch.setattr(atomic_booking, 'create_booking_atomic', create)
    monkeypatch.setattr(atomic_checkin_checkout, 'check_in_booking_atomic', checkin)
    user=SimpleNamespace(tenant_id='hotel',id='operator',name='Operator')
    payload=frontdesk.WalkInBookingRequest(guest_name='Deniz Aksoy',guest_email='deniz@example.invalid',guest_phone='',room_id='r',nights=nights,rate_per_night=450)
    result=await frontdesk.create_walk_in_booking(payload,request(),user)
    booking=create.await_args.kwargs['booking_doc']
    assert (booking['check_in'],booking['check_out'],booking['total_amount']) == ('2026-11-12',(date(2026, 11, 12) + timedelta(days=nights)).isoformat(),450 * nights)
    assert checkin.await_args.kwargs['booking_id'] == result['booking_id']
    # Empty phone must not select an unrelated anonymous guest.
    assert len(db.guests.find_one.await_args.args[0]['$or']) == 2
    guard.complete.assert_awaited_once()
