"""Regression tests for Idempotency-Key handling on the PMS-core folio
refund / void endpoints.

Task #80: POST /api/pms-core/folio/refund, /void-charge and /void-payment
must honour a client-supplied Idempotency-Key header so a cashier
double-click / network retry does not post the same negative-payment row,
or flip the same charge / payment twice. Pinned contract mirrors
test_folio_idempotency.py (task #60):

  * First call with a key performs the operation and caches the response.
  * A replay with the same key returns the cached response — no second
    insert (refund) and no second void flip.
  * In-flight collision returns 409.
  * Different scopes (per-folio for refund, per-resource for void) stay
    independent.
  * No header → classic behaviour; nothing is cached.
  * Failure path releases the slot so the same key can be retried.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from routers import pms_hardening as router_mod
from modules.pms_core import folio_hardening_service as fhs_mod


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []
        self.insert_calls = 0
        self.update_calls = 0

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return {k: v for k, v in d.items()}
        return None

    async def insert_one(self, doc):
        self.insert_calls += 1
        if "_id" in doc:
            for d in self.docs:
                if d.get("_id") == doc["_id"]:
                    raise DuplicateKeyError("duplicate _id")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("_id", "x"))

    async def update_one(self, flt, update, upsert=False):
        self.update_calls += 1
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                if "$set" in update:
                    d.update(update["$set"])
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, flt):
        for i, d in enumerate(list(self.docs)):
            if all(d.get(k) == v for k, v in flt.items()):
                self.docs.pop(i)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self):
        self.folios = _Coll()
        self.folio_charges = _Coll()
        self.payments = _Coll()
        self.idempotency_keys = _Coll()


class _FakeRequest:
    def __init__(self, idem: str | None = None, *, header: str = "Idempotency-Key"):
        self.headers = {}
        if idem:
            self.headers[header] = idem


@pytest.fixture
def fake_user():
    return SimpleNamespace(
        id="u1",
        tenant_id="tenant-A",
        role="manager",
        name="Cashier One",
        email="cashier@example.com",
    )


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    fake_db = _FakeDB()
    # Pre-seed an open folio for refund / void paths.
    fake_db.folios.docs.append({
        "id": "F1",
        "tenant_id": "tenant-A",
        "status": "open",
        "booking_id": "B1",
        "folio_number": "1001",
    })
    fake_db.folios.docs.append({
        "id": "F2",
        "tenant_id": "tenant-A",
        "status": "open",
        "booking_id": "B2",
        "folio_number": "1002",
    })
    # Pre-seed a chargeable line + a payment row to void.
    fake_db.folio_charges.docs.append({
        "id": "C1",
        "tenant_id": "tenant-A",
        "folio_id": "F1",
        "voided": False,
        "total": 100.0,
    })
    fake_db.payments.docs.append({
        "id": "P1",
        "tenant_id": "tenant-A",
        "folio_id": "F1",
        "voided": False,
        "amount": 100.0,
    })

    # Router and service both reach for `db` at module scope.
    monkeypatch.setattr(router_mod, "db", fake_db)
    monkeypatch.setattr(fhs_mod, "db", fake_db)

    # Bypass permission enforcement on the singleton used by the router.
    monkeypatch.setattr(
        router_mod.perm_svc, "enforce_permission", lambda *a, **kw: None
    )

    # Stub the service's best-effort balance + audit helpers.
    async def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(
        fhs_mod.FolioHardeningService, "_recalculate_folio_balance", _noop
    )
    monkeypatch.setattr(fhs_mod.FolioHardeningService, "_log_audit", _noop)

    # Cache-invalidation import in the router pulls in night_audit — stub it.
    import sys
    import types as _types

    stub_pkg = _types.ModuleType("domains.pms.night_audit.router")
    stub_pkg.invalidate_finance_cache = lambda *_a, **_kw: None
    sys.modules.setdefault("domains.pms.night_audit", _types.ModuleType("domains.pms.night_audit"))
    sys.modules["domains.pms.night_audit.router"] = stub_pkg

    return fake_db


# ---------------------------------------------------------------------------
# REFUND
# ---------------------------------------------------------------------------


def _refund_req():
    return router_mod.RefundRequest(
        folio_id="F1", booking_id="B1", amount=50.0, reason="oops", method="cash"
    )


async def test_refund_replay_with_same_key_returns_same_row(_patch, fake_user):
    r1 = await router_mod.api_post_refund(
        req=_refund_req(),
        request=_FakeRequest("IDEM-REF-1"),
        current_user=fake_user,
    )
    r2 = await router_mod.api_post_refund(
        req=_refund_req(),
        request=_FakeRequest("IDEM-REF-1"),
        current_user=fake_user,
    )
    # Same payload back, and only ONE negative payment row inserted.
    assert r1["refund"]["id"] == r2["refund"]["id"]
    refund_rows = [d for d in _patch.payments.docs if d.get("payment_type") == "refund"]
    assert len(refund_rows) == 1


async def test_refund_no_key_creates_two_rows(_patch, fake_user):
    await router_mod.api_post_refund(
        req=_refund_req(), request=_FakeRequest(), current_user=fake_user
    )
    await router_mod.api_post_refund(
        req=_refund_req(), request=_FakeRequest(), current_user=fake_user
    )
    refund_rows = [d for d in _patch.payments.docs if d.get("payment_type") == "refund"]
    assert len(refund_rows) == 2


async def test_refund_in_flight_same_key_returns_409(_patch, fake_user):
    from shared_kernel.idempotency import _lock_id

    seeded = _lock_id("tenant-A", "folio_refund:F1", "REF-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_refund:F1",
        "idempotency_key": "REF-INFLIGHT",
        "status": "processing",
    })
    before = len(_patch.payments.docs)
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_post_refund(
            req=_refund_req(),
            request=_FakeRequest("REF-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    # No new refund row inserted while the lock is processing.
    assert len(_patch.payments.docs) == before


async def test_refund_failure_releases_lock(_patch, fake_user):
    # Drop the folio so post_refund returns success=False → 400 raised.
    _patch.folios.docs.clear()
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_post_refund(
            req=_refund_req(),
            request=_FakeRequest("REF-FAIL"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 400
    # Slot released so the same key can be retried with valid state.
    assert len(_patch.idempotency_keys.docs) == 0


async def test_refund_replay_with_x_prefixed_header(_patch, fake_user):
    r1 = await router_mod.api_post_refund(
        req=_refund_req(),
        request=_FakeRequest("REF-X-1", header="X-Idempotency-Key"),
        current_user=fake_user,
    )
    r2 = await router_mod.api_post_refund(
        req=_refund_req(),
        request=_FakeRequest("REF-X-1", header="X-Idempotency-Key"),
        current_user=fake_user,
    )
    assert r1["refund"]["id"] == r2["refund"]["id"]
    refund_rows = [d for d in _patch.payments.docs if d.get("payment_type") == "refund"]
    assert len(refund_rows) == 1


async def test_refund_key_scoped_per_folio(_patch, fake_user):
    r1 = await router_mod.api_post_refund(
        req=router_mod.RefundRequest(
            folio_id="F1", booking_id="B1", amount=20.0, reason="r", method="cash"
        ),
        request=_FakeRequest("SAME"),
        current_user=fake_user,
    )
    r2 = await router_mod.api_post_refund(
        req=router_mod.RefundRequest(
            folio_id="F2", booking_id="B2", amount=20.0, reason="r", method="cash"
        ),
        request=_FakeRequest("SAME"),
        current_user=fake_user,
    )
    # Same idempotency-key but different folio scope -> two distinct rows.
    assert r1["refund"]["id"] != r2["refund"]["id"]
    refund_rows = [d for d in _patch.payments.docs if d.get("payment_type") == "refund"]
    assert len(refund_rows) == 2


# ---------------------------------------------------------------------------
# VOID CHARGE
# ---------------------------------------------------------------------------


async def test_void_charge_replay_with_same_key_returns_cached(_patch, fake_user):
    req = router_mod.VoidRequest(charge_id="C1", reason="mistake")
    r1 = await router_mod.api_void_charge(
        req=req, request=_FakeRequest("VC-1"), current_user=fake_user
    )
    # Reset the voided flag so a real second call WOULD flip it again —
    # the cache must short-circuit before the service runs.
    _patch.folio_charges.docs[0]["voided"] = False
    updates_before = _patch.folio_charges.update_calls
    r2 = await router_mod.api_void_charge(
        req=req, request=_FakeRequest("VC-1"), current_user=fake_user
    )
    assert r1 == r2
    # No additional update_one ran on folio_charges — replay was served.
    assert _patch.folio_charges.update_calls == updates_before


async def test_void_charge_in_flight_returns_409(_patch, fake_user):
    from shared_kernel.idempotency import _lock_id

    seeded = _lock_id("tenant-A", "folio_void_charge:C1", "VC-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_void_charge:C1",
        "idempotency_key": "VC-INFLIGHT",
        "status": "processing",
    })
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_void_charge(
            req=router_mod.VoidRequest(charge_id="C1", reason="r"),
            request=_FakeRequest("VC-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    # Original row still untouched.
    assert _patch.folio_charges.docs[0]["voided"] is False


async def test_void_charge_failure_releases_lock(_patch, fake_user):
    # Charge does not exist → service returns success=False → 400 raised.
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_void_charge(
            req=router_mod.VoidRequest(charge_id="MISSING", reason="r"),
            request=_FakeRequest("VC-FAIL"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 400
    assert len(_patch.idempotency_keys.docs) == 0


# ---------------------------------------------------------------------------
# VOID PAYMENT
# ---------------------------------------------------------------------------


async def test_void_payment_replay_with_same_key_returns_cached(_patch, fake_user):
    req = router_mod.VoidRequest(payment_id="P1", reason="reversed")
    r1 = await router_mod.api_void_payment(
        req=req, request=_FakeRequest("VP-1"), current_user=fake_user
    )
    _patch.payments.docs[0]["voided"] = False
    updates_before = _patch.payments.update_calls
    r2 = await router_mod.api_void_payment(
        req=req, request=_FakeRequest("VP-1"), current_user=fake_user
    )
    assert r1 == r2
    assert _patch.payments.update_calls == updates_before


async def test_void_payment_in_flight_returns_409(_patch, fake_user):
    from shared_kernel.idempotency import _lock_id

    seeded = _lock_id("tenant-A", "folio_void_payment:P1", "VP-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_void_payment:P1",
        "idempotency_key": "VP-INFLIGHT",
        "status": "processing",
    })
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_void_payment(
            req=router_mod.VoidRequest(payment_id="P1", reason="r"),
            request=_FakeRequest("VP-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    assert _patch.payments.docs[0]["voided"] is False


async def test_void_payment_no_key_runs_classic_path(_patch, fake_user):
    req = router_mod.VoidRequest(payment_id="P1", reason="reversed")
    r1 = await router_mod.api_void_payment(
        req=req, request=_FakeRequest(), current_user=fake_user
    )
    assert r1["success"] is True
    # Second call hits "already voided" guard — proves classic path ran,
    # nothing got cached, and the second request was NOT short-circuited.
    with pytest.raises(HTTPException) as exc:
        await router_mod.api_void_payment(
            req=req, request=_FakeRequest(), current_user=fake_user
        )
    assert exc.value.status_code == 400
