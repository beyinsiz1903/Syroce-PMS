"""Availability must offer the same active physical rooms as reservations."""
import pytest

from modules.inventory import repository as inventory
from modules.inventory.services.availability_read_service import AvailabilityReadService
from routers import pms_availability
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401


@pytest.mark.asyncio
async def test_deleted_inactive_virtual_and_foreign_rooms_never_appear_as_bookable(acceptance, monkeypatch):
    a = acceptance
    monkeypatch.setattr(inventory, 'db', a.db)
    monkeypatch.setattr(pms_availability, 'db', a.db)
    await a.db.rooms.update_one({'id': 'synthetic-room'}, {'$set': {'room_type': 'Standard'}})
    for rid, extra in [('inactive', {'is_active': False}), ('deleted', {'deleted_at': '2026-08-14'}),
        ('virtual', {'is_virtual': True}), ('foreign', {'tenant_id': 'other'}), ('active', {'is_active': True})]:
        await a.db.rooms.insert_one({'id': rid, 'tenant_id': 'qa', 'room_type': 'Standard', 'status': 'available', **extra})
    service = AvailabilityReadService()
    semantic = await service.get_availability('qa', '2026-11-20', '2026-11-21', 'Standard')
    legacy = await pms_availability._legacy_check_room_availability('qa', '2026-11-20', '2026-11-21', 'Standard')
    assert {r['id'] for r in semantic} == {r['id'] for r in legacy} == {'synthetic-room', 'active'}
    assert all(r['available'] for r in semantic)
    assert await service.get_availability('qa', '2026-11-20', '2026-11-21', 'Missing') == []
