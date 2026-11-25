"""Non-ready rooms must never fall through the v2 check-in guard."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from tests.test_offline_checkin_idempotency import _ctx, _make_service, _seed_ready_booking


@pytest.fixture(autouse=True)
def no_external_kbs(monkeypatch):
    monkeypatch.setattr('domains.pms.frontdesk_service._enqueue_kbs_after_frontdesk_transition', AsyncMock(return_value=[]))


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['out_of_order', 'out_of_service', 'blocked', 'cleaning', 'unknown', '', None])
async def test_non_ready_status_creates_no_folio_booking_guest_or_room_mutation(status):
    service = _make_service()
    _seed_ready_booking(service._db, room_status=status)
    before = {name: deepcopy(service._db[name].docs) for name in ('bookings', 'rooms', 'guests', 'folios')}
    result = await service._do_checkin(_ctx(), 'bk-1', True, 'holder')
    assert not result.ok
    assert result.code == 'ROOM_NOT_READY'
    for name, rows in before.items():
        assert service._db[name].docs == rows


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['available', 'clean', 'inspected'])
async def test_readiness_whitelist_keeps_normal_checkin(status):
    service = _make_service()
    _seed_ready_booking(service._db, room_status=status)
    result = await service._do_checkin(_ctx(), 'bk-1', True, 'holder')
    assert result.ok
    assert service._db.bookings.docs[0]['status'] == 'checked_in'
    assert service._db.folios.insert_calls == 1
