"""Regression: close_order MUST refuse to close a voided order.

CI 2026-05-25 (98-pos-deep-lifecycle G "Terminal-state guard") failed
because close_order silently succeeded on an order with status='voided'.
Void is a terminal state — close must 4xx (router maps the fail to 400).
"""
from types import SimpleNamespace

import pytest

from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2


class _FakeColl:
    def __init__(self, doc=None):
        self._doc = doc

    async def find_one(self, *_a, **_kw):
        return self._doc

    async def insert_one(self, *_a, **_kw):
        return None

    async def update_one(self, *_a, **_kw):
        return SimpleNamespace(modified_count=1)


def _ctx():
    return SimpleNamespace(
        tenant_id="t1",
        actor_id="u1",
        actor_role="admin",
        actor_is_super_admin=False,
    )


async def test_close_order_rejects_voided_order():
    voided_order = {
        "id": "ord1",
        "tenant_id": "t1",
        "status": "voided",
        "payment_status": "unpaid",
        "grand_total": 100.0,
        "order_items": [],
    }
    db = SimpleNamespace(
        pos_transactions=_FakeColl(None),
        pos_orders=_FakeColl(voided_order),
        folios=_FakeColl(None),
        folio_charges=_FakeColl(None),
        table_layouts=_FakeColl(None),
        audit_logs=_FakeColl(None),
    )
    svc = PosFnbServiceV2()
    svc._db = db

    result = await svc.close_order(_ctx(), order_id="ord1", payment_method="cash")
    assert result.ok is False
    assert result.code == "ORDER_VOIDED"


async def test_close_order_still_idempotent_when_already_closed():
    closed_order = {
        "id": "ord1",
        "tenant_id": "t1",
        "status": "closed",
        "payment_status": "paid",
        "grand_total": 100.0,
    }
    db = SimpleNamespace(
        pos_transactions=_FakeColl(None),
        pos_orders=_FakeColl(closed_order),
        folios=_FakeColl(None),
        folio_charges=_FakeColl(None),
        table_layouts=_FakeColl(None),
        audit_logs=_FakeColl(None),
    )
    svc = PosFnbServiceV2()
    svc._db = db

    result = await svc.close_order(_ctx(), order_id="ord1", payment_method="cash")
    assert result.ok is True
    assert result.data.get("idempotent") is True


async def test_close_order_returns_not_found_for_missing_order():
    db = SimpleNamespace(
        pos_transactions=_FakeColl(None),
        pos_orders=_FakeColl(None),
        folios=_FakeColl(None),
        folio_charges=_FakeColl(None),
        table_layouts=_FakeColl(None),
        audit_logs=_FakeColl(None),
    )
    svc = PosFnbServiceV2()
    svc._db = db

    result = await svc.close_order(_ctx(), order_id="missing", payment_method="cash")
    assert result.ok is False
    assert result.code == "NOT_FOUND"
