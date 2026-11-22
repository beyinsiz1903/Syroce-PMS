"""Check-in account currency remains usable by department posting guards; LOCAL replica only."""
from unittest.mock import AsyncMock

import pytest

from common.context import OperationContext
from core import atomic_checkin_checkout as atomic
from domains.pms import frontdesk_router, frontdesk_service
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['atomic', 'service', 'ensure'])
@pytest.mark.parametrize('currency', ['TRY', 'USD', 'EUR', 'TL'])
async def test_new_checkin_folio_keeps_booking_currency(acceptance, monkeypatch, path, currency):
    a = acceptance
    await a.db.folios.delete_many({})
    await a.db.folio_charges.delete_many({})
    await a.db.bookings.update_one({'id': 'synthetic-stay'}, {'$set': {'currency': currency, 'status': 'confirmed', 'check_in': '2026-10-26', 'check_out': '2026-10-28'}})
    await a.db.rooms.update_one({'id': 'synthetic-room'}, {'$set': {'status': 'available', 'current_booking_id': None}})
    monkeypatch.setattr(atomic, 'db', a.db)
    monkeypatch.setattr(atomic, 'client', a.db.client)
    monkeypatch.setattr(atomic, 'audit_log', AsyncMock())
    monkeypatch.setattr('core.kbs_auto_enqueue.auto_enqueue_kbs', AsyncMock(return_value=False))
    if path == 'atomic':
        await atomic.check_in_booking_atomic('synthetic-stay', 'qa', a.user.id)
    elif path == 'service':
        service = frontdesk_service.frontdesk_service
        result = await service.checkin(OperationContext.from_user(a.user), 'synthetic-stay')
        assert result.ok, result
    else:
        await frontdesk_router._ensure_open_folio('qa', 'synthetic-stay', 'synthetic-guest')
    folios = await a.db.folios.find({'tenant_id': 'qa', 'booking_id': 'synthetic-stay'}).to_list(None)
    assert len(folios) == 1
    assert folios[0]['currency'] == ('TRY' if currency == 'TL' else currency)
    assert folios[0]['balance'] == 0
    assert await a.db.folio_payments.count_documents({}) == 0


@pytest.mark.asyncio
async def test_existing_unknown_currency_account_is_not_silently_rewritten(acceptance):
    a = acceptance
    await a.db.folios.update_one({'id': 'synthetic-folio'}, {'$unset': {'currency': ''}})
    before = await a.db.folios.find_one({'id': 'synthetic-folio'})
    result = await frontdesk_router._ensure_open_folio('qa', 'synthetic-stay', 'synthetic-guest')
    assert 'currency' not in result
    assert await a.db.folios.find_one({'id': 'synthetic-folio'}) == before
