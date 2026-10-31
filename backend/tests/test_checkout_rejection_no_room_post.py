"""A rejected departure must not pre-post a room remainder for a later audit."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.context import OperationContext
from core import folio_checkout_reconciliation
from domains.pms import frontdesk_service, frontdesk_service_v2


def collection(*, found=None, rows=()):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=found)
    col.find.return_value.to_list = AsyncMock(return_value=list(rows))
    col.update_one = AsyncMock()
    col.insert_one = AsyncMock()
    return col


@pytest.mark.asyncio
@pytest.mark.parametrize('version,guard', [(1, 'balance'), (2, 'balance'), (1, 'business_date'), (2, 'business_date'), (2, 'force_permission')])
async def test_rejected_checkout_never_posts_an_unposted_room_remainder(monkeypatch, version, guard):
    from core import pos_folio_consumer
    from routers.finance import konaklama_vergisi_core
    monkeypatch.setattr(konaklama_vergisi_core, 'load_tax_config', AsyncMock(return_value={'active': False}))
    monkeypatch.setattr(pos_folio_consumer, 'drain_pending_pos_charges', AsyncMock())
    reconcile = AsyncMock(return_value={'posted': False})
    monkeypatch.setattr(folio_checkout_reconciliation, 'reconcile_unposted_room_charge', reconcile)
    booking = {'id': 'booking-1', 'tenant_id': 'tenant-1', 'room_id': 'room-1', 'status': 'checked_in', 'total_amount': 100, 'check_out': '2026-11-01'}
    database = SimpleNamespace(
        bookings=collection(found=booking),
        folios=collection(rows=[{'id': 'folio-1', 'balance': 100 if guard != 'business_date' else 0, 'status': 'open'}]),
        folio_charges=collection(), extra_charges=collection(),
        payments=collection(rows=[{'amount': 100, 'status': 'paid'}] if guard == 'business_date' else []),
        rooms=collection(), housekeeping_tasks=collection(),
    )
    module = frontdesk_service if version == 1 else frontdesk_service_v2
    transition = AsyncMock(return_value=(None, None))
    if guard == 'business_date':
        transition.side_effect = ValueError('Wrong business day')
    monkeypatch.setattr(module, 'enforce_business_date_transition', transition)
    cls = module.FrontdeskService if version == 1 else module.FrontdeskServiceV2
    service = cls.__new__(cls)
    service._db = database
    ctx = OperationContext(tenant_id='tenant-1', actor_id='operator', actor_role='front_desk')
    if version == 1:
        result = await cls.checkout.__wrapped__(service, ctx, 'booking-1')
    else:
        result = await service._do_checkout(ctx, 'booking-1', guard == 'force_permission', True, 'Local QA' if guard == 'force_permission' else None)
    assert not result.ok
    assert result.code == {'balance': 'OUTSTANDING_BALANCE', 'business_date': 'BUSINESS_DATE_MISMATCH', 'force_permission': 'INSUFFICIENT_PERMISSION'}[guard]
    reconcile.assert_not_awaited()
    database.folio_charges.insert_one.assert_not_awaited()
    database.bookings.update_one.assert_not_awaited()
    database.rooms.update_one.assert_not_awaited()
