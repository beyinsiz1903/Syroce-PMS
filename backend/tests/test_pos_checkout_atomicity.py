"""Regression coverage for atomic POS checkout state transitions."""

from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2, PosOrderStateChanged


class _Transactions:
    async def find_one(self, *_args, **_kwargs):
        return None


class _OrdersThatBecomeVoided:
    def __init__(self):
        self.calls = 0

    async def find_one(self, *_args, **_kwargs):
        self.calls += 1
        status = "pending" if self.calls == 1 else "voided"
        return {
            "id": "order-1",
            "tenant_id": "tenant-1",
            "status": status,
            "payment_status": "unpaid",
            "grand_total": 100.0,
            "order_items": [],
        }


def _context():
    return SimpleNamespace(
        tenant_id="tenant-1",
        actor_id="manager-1",
        actor_role="admin",
        actor_is_super_admin=False,
    )


@pytest.mark.asyncio
async def test_close_returns_business_error_when_order_is_voided_during_checkout(monkeypatch):
    """A race with void must not become a paid sale or an HTTP 500."""
    service = PosFnbServiceV2()
    service._db = SimpleNamespace(pos_transactions=_Transactions(), pos_orders=_OrdersThatBecomeVoided())

    async def loses_race(*_args, **_kwargs):
        raise PosOrderStateChanged("order-1")

    monkeypatch.setattr(service, "_persist_txn_and_intent", loses_race)
    result = await PosFnbServiceV2.close_order.__wrapped__(service, _context(), "order-1")

    assert result.ok is False
    assert result.code == "ORDER_VOIDED"
