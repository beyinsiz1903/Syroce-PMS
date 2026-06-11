"""Task #373 — Mobile POS quick-order idempotency.

Pinned contract:
  * Same idempotency_key replay (retry / double-tap / network replay) -> one
    pos_order; second response is an idempotent replay (idempotent_replay=True).
  * No idempotency_key -> classic behaviour, every call inserts a fresh order.
  * Index ensure failure is fail-closed (503), never a silent non-idempotent
    write.

Runs against an in-memory fake that mimics Mongo's unique partial index +
DuplicateKeyError, exercising the shared `idempotent_insert` helper that the
mobile quick-order endpoint now uses (same `pos_orders` index as create-order).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError

from domains.pms.mobile_router import pos as mobile_pos
from domains.pms.pos_extensions import _idem


class _Coll:
    def __init__(self, name):
        self.name = name
        self.docs: list[dict] = []
        self.insert_calls = 0
        self._uniques: list[tuple[tuple[str, ...], str | None]] = []

    async def create_index(self, keys, *_a, **kw):
        if kw.get("unique"):
            fields = tuple(k for k, _ in keys)
            pfe = kw.get("partialFilterExpression") or {}
            partial_field = next(iter(pfe.keys()), None)
            self._uniques.append((fields, partial_field))
        return "idx"

    def _violates_unique(self, doc) -> bool:
        for fields, pf in self._uniques:
            if pf is not None and not isinstance(doc.get(pf), str):
                continue
            if not all(f in doc for f in fields):
                continue
            for d in self.docs:
                if all(d.get(f) == doc.get(f) for f in fields):
                    return True
        return False

    async def insert_one(self, doc, session=None):
        if self._violates_unique(doc):
            raise DuplicateKeyError("dup")
        self.insert_calls += 1
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")

    async def find_one(self, flt, proj=None, session=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                r = dict(d)
                r.pop("_id", None)
                return r
        return None


class _FakeDB:
    def __init__(self):
        self._colls: dict[str, _Coll] = {}

    def _get(self, name) -> _Coll:
        if name not in self._colls:
            self._colls[name] = _Coll(name)
        return self._colls[name]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._get(name)


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake_db = _FakeDB()
    fake_db.pos_outlets.docs.append(
        {"id": "O1", "tenant_id": "tenant-A", "name": "Lobby Bar"}
    )
    fake_db.pos_menu_items.docs.extend([
        {"id": "m1", "tenant_id": "tenant-A", "name": "Burger", "price": 100.0},
        {"id": "m2", "tenant_id": "tenant-A", "name": "Cola", "price": 50.0},
    ])

    monkeypatch.setattr(mobile_pos, "db", fake_db)

    async def _user(_creds):
        return SimpleNamespace(
            user_id="u1", tenant_id="tenant-A", role="manager",
            username="cashier",
        )

    monkeypatch.setattr(mobile_pos, "get_current_user", _user)
    _idem._INDEXES_READY.clear()
    return fake_db


def _req(items, *, idem=None):
    return mobile_pos.QuickOrderRequest(
        outlet_id="O1",
        table_number="5",
        items=[mobile_pos.QuickOrderItem(item_id=i, quantity=q) for i, q in items],
        notes="",
        idempotency_key=idem,
    )


async def test_same_key_replay_single_order(_patch):
    r1 = await mobile_pos.create_quick_order_mobile(
        request=_req([("m1", 1), ("m2", 2)], idem="MORDER-1"), credentials=None, _perm=None
    )
    r2 = await mobile_pos.create_quick_order_mobile(
        request=_req([("m1", 1), ("m2", 2)], idem="MORDER-1"), credentials=None, _perm=None
    )

    assert r1["idempotent_replay"] is False
    assert r2["idempotent_replay"] is True
    assert r1["order_id"] == r2["order_id"]
    assert _patch.pos_orders.insert_calls == 1


async def test_no_key_creates_two_orders(_patch):
    r1 = await mobile_pos.create_quick_order_mobile(
        request=_req([("m1", 1)]), credentials=None, _perm=None
    )
    r2 = await mobile_pos.create_quick_order_mobile(
        request=_req([("m1", 1)]), credentials=None, _perm=None
    )
    assert r1["order_id"] != r2["order_id"]
    assert r1["idempotent_replay"] is False
    assert r2["idempotent_replay"] is False
    assert _patch.pos_orders.insert_calls == 2


async def test_index_ensure_failure_is_fail_closed_503(_patch, monkeypatch):
    from fastapi import HTTPException

    async def _boom(*_a, **_kw):
        raise RuntimeError("index perms lost")

    monkeypatch.setattr(_idem, "ensure_idem_index", _boom)
    with pytest.raises(HTTPException) as exc:
        await mobile_pos.create_quick_order_mobile(
            request=_req([("m1", 1)], idem="K"), credentials=None, _perm=None
        )
    assert exc.value.status_code == 503


async def test_idempotency_key_too_long_is_400(_patch):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await mobile_pos.create_quick_order_mobile(
            request=_req([("m1", 1)], idem="x" * 129), credentials=None, _perm=None
        )
    assert exc.value.status_code == 400
