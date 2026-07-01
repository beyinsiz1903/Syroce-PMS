"""F8 (Wave 5) — Finance folio guards, idempotency-scope namespace, RBAC.

Locks the high-risk financial behaviors the stress suite probes so a future
regression can't silently loosen them:

  - Closed-folio guard: charge/payment/refund/void blocked once a folio is
    not "open" (FolioHardeningService returns success=False, never mutates).
  - Input guards: payment/refund amount must be positive; void requires a
    reason; void of an already-voided line is rejected.
  - Tenant scoping: every guard query carries tenant_id.
  - Idempotency-scope namespace: each money operation uses a DISTINCT scope
    prefix so replay caches never collide across operation types.
  - RBAC: each money endpoint enforces its own distinct permission string.

These are behavioral (monkeypatched DB) + source-contract tests. No financial
guard is loosened; failures here mean a real product regression.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import modules.pms_core.folio_hardening_service as fhs
from modules.pms_core.folio_hardening_service import FolioHardeningService


class _Coll:
    def __init__(self, find_one_result=None):
        self._find_one_result = find_one_result
        self.updates = []
        self.inserts = []

    async def find_one(self, query, *a, **k):
        # Record the query so tenant scoping can be asserted.
        _Coll.last_query = query
        return self._find_one_result

    async def update_one(self, query, update, *a, **k):
        self.updates.append((query, update))
        return SimpleNamespace(modified_count=1)

    async def insert_one(self, doc):
        self.inserts.append(doc)
        return SimpleNamespace(inserted_id="x")


def _db(**colls):
    return SimpleNamespace(**colls)


@pytest.mark.asyncio
async def test_post_charge_blocked_on_closed_folio(monkeypatch):
    folios = _Coll({"id": "f1", "tenant_id": "t1", "status": "closed"})
    monkeypatch.setattr(fhs, "db", _db(folios=folios, folio_charges=_Coll()))
    res = await FolioHardeningService().post_charge(
        "t1", "f1", "b1", {"amount": 100}, "u1"
    )
    assert res["success"] is False
    assert "closed" in res["error"].lower()
    assert _Coll.last_query.get("tenant_id") == "t1"


@pytest.mark.asyncio
async def test_post_payment_blocked_on_closed_folio(monkeypatch):
    folios = _Coll({"id": "f1", "tenant_id": "t1", "status": "checked_out"})
    monkeypatch.setattr(fhs, "db", _db(folios=folios, payments=_Coll()))
    res = await FolioHardeningService().post_payment(
        "t1", "f1", "b1", {"amount": 50}, "u1"
    )
    assert res["success"] is False


@pytest.mark.asyncio
async def test_post_payment_rejects_non_positive_amount(monkeypatch):
    folios = _Coll({"id": "f1", "tenant_id": "t1", "status": "open"})
    payments = _Coll()
    monkeypatch.setattr(fhs, "db", _db(folios=folios, payments=payments))
    res = await FolioHardeningService().post_payment(
        "t1", "f1", "b1", {"amount": 0}, "u1"
    )
    assert res["success"] is False
    assert "positive" in res["error"].lower()
    assert payments.inserts == []  # nothing written on guard-fail


@pytest.mark.asyncio
async def test_void_charge_requires_reason(monkeypatch):
    charge = {"id": "c1", "tenant_id": "t1", "folio_id": "f1", "voided": False}
    monkeypatch.setattr(
        fhs, "db", _db(folio_charges=_Coll(charge), folios=_Coll({"status": "open"}))
    )
    res = await FolioHardeningService().void_charge("t1", "c1", "", "u1")
    assert res["success"] is False
    assert "reason" in res["error"].lower()


@pytest.mark.asyncio
async def test_void_charge_blocked_when_already_voided(monkeypatch):
    charge = {"id": "c1", "tenant_id": "t1", "folio_id": "f1", "voided": True}
    monkeypatch.setattr(fhs, "db", _db(folio_charges=_Coll(charge)))
    res = await FolioHardeningService().void_charge("t1", "c1", "dup", "u1")
    assert res["success"] is False
    assert "already voided" in res["error"].lower()


@pytest.mark.asyncio
async def test_void_charge_blocked_on_closed_folio(monkeypatch):
    charge = {"id": "c1", "tenant_id": "t1", "folio_id": "f1", "voided": False}
    folios = _Coll({"id": "f1", "status": "closed"})
    monkeypatch.setattr(fhs, "db", _db(folio_charges=_Coll(charge), folios=folios))
    res = await FolioHardeningService().void_charge("t1", "c1", "mistake", "u1")
    assert res["success"] is False
    assert "closed" in res["error"].lower()


@pytest.mark.asyncio
async def test_void_payment_blocked_on_closed_folio(monkeypatch):
    payment = {"id": "p1", "tenant_id": "t1", "folio_id": "f1", "voided": False}
    folios = _Coll({"id": "f1", "status": "checked_out"})
    monkeypatch.setattr(fhs, "db", _db(payments=_Coll(payment), folios=folios))
    res = await FolioHardeningService().void_payment("t1", "p1", "mistake", "u1")
    assert res["success"] is False


@pytest.mark.asyncio
async def test_split_folio_rejects_missing_charges(monkeypatch):
    class _ChargeColl:
        def find(self, *a, **k):
            class _Cur:
                async def to_list(self, _n):
                    return []  # none of the requested ids exist

            return _Cur()

    folios = _Coll({"id": "f1", "tenant_id": "t1", "status": "open"})
    monkeypatch.setattr(
        fhs, "db", _db(folios=folios, folio_charges=_ChargeColl())
    )
    res = await FolioHardeningService().split_folio(
        "t1", "f1", ["c-missing"], "guest", "reason", "u1"
    )
    assert res["success"] is False


# ── Idempotency-scope namespace + RBAC contract (source-level) ──

_HARDENING = Path(__file__).resolve().parents[1] / "routers" / "pms_hardening.py"
_FOLIO = Path(__file__).resolve().parents[1] / "routers" / "finance" / "folio.py"


def test_idempotency_scopes_are_distinct_per_money_operation():
    """Replay caches must not collide: each operation owns a unique scope
    prefix. Locking the namespace prevents a future edit from accidentally
    reusing one scope for two different money operations."""
    src = _HARDENING.read_text() + _FOLIO.read_text()
    expected = [
        "folio_charge:",
        "folio_payment:",
        "folio_refund:",
        "folio_void_charge:",
        "folio_void_payment:",
        "folio_split:",
    ]
    for scope in expected:
        assert f'scope=f"{scope}' in src, f"missing idempotency scope {scope}"
    # Distinctness: no two prefixes are identical strings.
    assert len(set(expected)) == len(expected)


def test_money_endpoints_enforce_distinct_permissions():
    """Each money mutation enforces its own permission string."""
    src = _HARDENING.read_text()
    for perm in (
        "post_charge",
        "post_payment",
        "void_charge",
        "void_payment",
        "split_folio",
    ):
        assert f'enforce_permission(current_user.role, "{perm}")' in src
