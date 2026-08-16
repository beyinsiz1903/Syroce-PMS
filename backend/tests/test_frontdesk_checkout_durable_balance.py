from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.context import OperationContext
from domains.pms.frontdesk_service import FrontdeskService


class _Cursor:
    def __init__(self, documents):
        self._documents = documents

    async def to_list(self, _limit):
        return self._documents


def _collection(*, found=None, documents=None):
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=found)
    collection.find.return_value = _Cursor(documents or [])
    collection.update_one = AsyncMock()
    collection.insert_one = AsyncMock()
    return collection


@pytest.mark.asyncio
async def test_checkout_blocks_on_durable_extra_charge_when_cached_balances_are_zero(monkeypatch):
    from routers.finance import konaklama_vergisi_core

    monkeypatch.setattr(
        konaklama_vergisi_core,
        "load_tax_config",
        AsyncMock(return_value={"active": False}),
    )

    booking = {
        "id": "booking-1",
        "tenant_id": "tenant-1",
        "room_id": "room-1",
        "status": "checked_in",
        "total_amount": 100,
        "paid_amount": 100,
    }
    service = FrontdeskService.__new__(FrontdeskService)
    service._db = SimpleNamespace(
        bookings=_collection(found=booking),
        folios=_collection(documents=[{"id": "folio-1", "balance": 0, "status": "open"}]),
        folio_charges=_collection(documents=[]),
        payments=_collection(documents=[{"amount": 100, "status": "paid"}]),
        extra_charges=_collection(documents=[{"charge_amount": 25}]),
        rooms=_collection(),
        housekeeping_tasks=_collection(),
    )
    ctx = OperationContext(tenant_id="tenant-1", actor_id="actor-1")

    result = await FrontdeskService.checkout.__wrapped__(service, ctx, "booking-1")

    assert result.ok is False
    assert result.code == "OUTSTANDING_BALANCE"
    assert result.meta["durable_balance"] == 25.0
    service._db.bookings.update_one.assert_not_awaited()
    service._db.rooms.update_one.assert_not_awaited()
    service._db.housekeeping_tasks.insert_one.assert_not_awaited()
