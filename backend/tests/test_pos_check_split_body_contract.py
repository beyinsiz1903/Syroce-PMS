"""API-level regression for `/api/pos/check-split` body parsing.

The CI failure of 2026-05-25 (98-pos-deep-lifecycle.spec.js "D)") was a
FastAPI parameter-binding ambiguity: with `split_details: dict | None = None`
and no other body params, FastAPI binds the *whole* request body to
`split_details`. The e2e contract wraps the field
(`{"split_details": {...}}`), so the inner shape leaked into the parser
and produced spurious 400s. The fix pins `Body(default=None, embed=True)`.

This test exercises the FastAPI layer (not the function directly) to lock
the wire contract.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from domains.pms.pos_fnb_router import pos_core
from domains.pms.pos_fnb_router.pos_core import router as pos_router


@pytest.fixture
def client(monkeypatch):
    class _FakeColl:
        async def find_one(self, *_a, **_kw):
            return {
                "id": "tx1",
                "tenant_id": "t1",
                "total_amount": 100.0,
                "order_items": [
                    {"name": "Burger", "price": 40.0},
                    {"name": "Fries", "price": 25.0},
                    {"name": "Soda", "price": 35.0},
                ],
            }

        async def update_one(self, *_a, **_kw):
            return SimpleNamespace(modified_count=1)

    class _FakeDB:
        pos_transactions = _FakeColl()

    monkeypatch.setattr(pos_core, "db", _FakeDB())

    from core.security import get_current_user
    app = FastAPI()
    app.include_router(pos_router)

    async def _fake_user():
        return SimpleNamespace(id="u1", tenant_id="t1")

    async def _fake_perm():
        return None

    app.dependency_overrides[get_current_user] = _fake_user
    # The route declares `_perm=Depends(require_module_v99("pos"))`; resolve
    # the actual dep callable from the route signature so we can override it.
    for route in app.routes:
        if getattr(route, "path", "") == "/api/pos/check-split":
            for param in route.dependant.dependencies:
                if param.name == "_perm":
                    app.dependency_overrides[param.call] = _fake_perm
                    break
            break

    return TestClient(app)


def test_wrapped_split_details_body_is_accepted(client):
    """E2E contract: body is `{"split_details": {...}}`."""
    r = client.post(
        "/api/pos/check-split?transaction_id=tx1&split_type=by_item&split_count=2",
        json={"split_details": {"1": [0], "2": [1]}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    splits = {s["split_number"]: s for s in body["splits"]}
    assert splits[1]["amount"] == 40.0
    assert splits[2]["amount"] == 25.0


def test_bare_dict_body_is_rejected(client):
    """Without `embed=True` FastAPI bound the whole body to `split_details`,
    so a bare `{"1": [0], "2": [1]}` was mis-parsed into iteration over
    split_num='1','2' with item_indices=[0],[1]. With `embed=True`, the
    missing `split_details` key leaves the param as `None`, so the handler
    rejects with 400 'no valid item indices' instead of silently
    succeeding with garbage splits. Either 4xx is acceptable here — the
    key invariant is that a bare dict is NOT accepted as success."""
    r = client.post(
        "/api/pos/check-split?transaction_id=tx1&split_type=by_item&split_count=2",
        json={"1": [0], "2": [1]},
    )
    assert r.status_code in (400, 422)


def test_missing_body_defaults_to_none_for_equal_split(client):
    """`equal` split needs no split_details; missing body must still work."""
    r = client.post(
        "/api/pos/check-split?transaction_id=tx1&split_type=equal&split_count=4",
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["splits"]) == 4
