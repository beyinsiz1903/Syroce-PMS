"""Regression tests for Idempotency-Key handling on folio finance endpoints.

Task #60: POST /api/folio/{id}/charge and /api/folio/{id}/payment must honor
a client-supplied `Idempotency-Key` header so that a cashier double-click or
retry loop does not double-post a charge / payment. Pinned contract:

  * First call with a key inserts a row and caches the response.
  * A replay with the same key returns the original payload (same row id),
    never a second insert.
  * In-flight collision on the same key returns 409.
  * Keys are scoped per-tenant AND per-folio (different scopes -> independent).
  * No header -> classic behaviour, every call inserts a fresh row.
  * Failure path releases the slot so the client can retry the same key.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from routers.finance import folio as folio_router


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class _Coll:
    def __init__(self):
        self.docs: list[dict] = []
        self.insert_calls = 0

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in flt.items()):
                return {k: v for k, v in d.items()}
        return None

    async def insert_one(self, doc):
        self.insert_calls += 1
        # Honour unique _id semantics (claim_idempotency relies on this).
        if "_id" in doc:
            for d in self.docs:
                if d.get("_id") == doc["_id"]:
                    raise DuplicateKeyError("duplicate _id")
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=doc.get("_id", "x"))

    async def update_one(self, flt, update, upsert=False):
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
        self.city_tax_rules = _Coll()


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
    # Pre-seed an open folio so the handler proceeds.
    fake_db.folios.docs.append({
        "id": "F1",
        "tenant_id": "tenant-A",
        "status": "open",
        "booking_id": "B1",
        "folio_number": "1001",
    })

    monkeypatch.setattr(folio_router, "db", fake_db)
    # The idempotency helpers import db lazily inside shared_kernel; they
    # accept whatever handle we pass, so we hand them our fake explicitly
    # via the folio_router.db reference used in claim_idempotency calls.

    # Permission guard is enforced via RolePermissionService — bypass.
    from modules.pms_core import role_permission_service as rps_mod

    class _NoopRPS:
        def enforce_permission(self, *a, **kw):
            return None

    monkeypatch.setattr(rps_mod, "RolePermissionService", _NoopRPS)

    # Calculate balance helper hits Mongo — stub it.
    async def _balance(folio_id, tenant_id):
        return 0.0

    monkeypatch.setattr(folio_router, "calculate_folio_balance", _balance)

    # Audit log writes to Mongo — stub.
    async def _audit(**_kw):
        return None

    monkeypatch.setattr(folio_router, "create_audit_log", _audit)

    # Cashier service: skip shift check + cash recording.
    from domains.pms import cashier_service as cs

    async def _ok_shift(*_a, **_kw):
        return None

    async def _ok_cash(*_a, **_kw):
        return None

    monkeypatch.setattr(cs, "ensure_active_shift", _ok_shift)
    monkeypatch.setattr(cs, "record_cash_transaction", _ok_cash)

    # Webhook scheduler is fire-and-forget — stub.
    from routers import webhook_retry_service as wrs

    def _noop(*_a, **_kw):
        return None

    monkeypatch.setattr(wrs, "schedule_emit_reservation_updated", _noop)

    # Cache invalidation is optional.
    monkeypatch.setattr(folio_router, "cache", None, raising=False)

    return fake_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _charge_payload(amount=100.0):
    from models.schemas import ChargeCreate
    from models.enums import ChargeCategory

    return ChargeCreate(
        charge_category=ChargeCategory.FOOD,
        description="Room service",
        amount=amount,
        quantity=1,
    )


def _payment_payload(amount=100.0):
    from models.schemas import PaymentCreate
    from models.enums import PaymentMethod, PaymentType

    return PaymentCreate(
        amount=amount,
        method=PaymentMethod.CARD,
        payment_type=PaymentType.DEPOSIT,
    )


# ---------------------------------------------------------------------------
# Charge tests
# ---------------------------------------------------------------------------


async def test_charge_replay_with_same_key_returns_same_row(_patch, fake_user):
    req = _FakeRequest("IDEM-CHG-1")
    r1 = await folio_router.post_charge_to_folio(
        folio_id="F1",
        charge_data=_charge_payload(),
        request=req,
        current_user=fake_user,
    )
    # Same key → must replay the cached row, no new insert.
    r2 = await folio_router.post_charge_to_folio(
        folio_id="F1",
        charge_data=_charge_payload(),
        request=_FakeRequest("IDEM-CHG-1"),
        current_user=fake_user,
    )
    r1_id = r1.id if hasattr(r1, "id") else r1["id"]
    r2_id = r2["id"] if isinstance(r2, dict) else r2.id
    assert r1_id == r2_id
    assert _patch.folio_charges.insert_calls == 1


async def test_charge_no_key_creates_two_rows(_patch, fake_user):
    r1 = await folio_router.post_charge_to_folio(
        folio_id="F1",
        charge_data=_charge_payload(),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    r2 = await folio_router.post_charge_to_folio(
        folio_id="F1",
        charge_data=_charge_payload(),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    assert r1.id != r2.id
    assert _patch.folio_charges.insert_calls == 2


async def test_charge_failure_releases_lock(_patch, fake_user):
    # Drop the open folio so the handler raises 404 mid-request.
    _patch.folios.docs.clear()
    req = _FakeRequest("IDEM-CHG-FAIL")
    with pytest.raises(HTTPException) as exc:
        await folio_router.post_charge_to_folio(
            folio_id="F1",
            charge_data=_charge_payload(),
            request=req,
            current_user=fake_user,
        )
    assert exc.value.status_code == 404
    # Slot must be released so the same key can be retried.
    assert len(_patch.idempotency_keys.docs) == 0


# ---------------------------------------------------------------------------
# Payment tests
# ---------------------------------------------------------------------------


async def test_payment_replay_with_same_key_returns_same_row(_patch, fake_user):
    r1 = await folio_router.post_payment_to_folio(
        folio_id="F1",
        payment_data=_payment_payload(),
        request=_FakeRequest("IDEM-PAY-1"),
        current_user=fake_user,
    )
    r2 = await folio_router.post_payment_to_folio(
        folio_id="F1",
        payment_data=_payment_payload(),
        request=_FakeRequest("IDEM-PAY-1"),
        current_user=fake_user,
    )
    r1_id = r1.id if hasattr(r1, "id") else r1["id"]
    r2_id = r2["id"] if isinstance(r2, dict) else r2.id
    assert r1_id == r2_id
    assert _patch.payments.insert_calls == 1


async def test_payment_no_key_creates_two_rows(_patch, fake_user):
    r1 = await folio_router.post_payment_to_folio(
        folio_id="F1",
        payment_data=_payment_payload(),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    r2 = await folio_router.post_payment_to_folio(
        folio_id="F1",
        payment_data=_payment_payload(),
        request=_FakeRequest(),
        current_user=fake_user,
    )
    assert r1.id != r2.id
    assert _patch.payments.insert_calls == 2


async def test_charge_replay_with_x_prefixed_header(_patch, fake_user):
    """X-Idempotency-Key (RFC-style prefix the stress harness uses) must
    be treated identically to Idempotency-Key."""
    r1 = await folio_router.post_charge_to_folio(
        folio_id="F1",
        charge_data=_charge_payload(),
        request=_FakeRequest("X-IDEM-1", header="X-Idempotency-Key"),
        current_user=fake_user,
    )
    r2 = await folio_router.post_charge_to_folio(
        folio_id="F1",
        charge_data=_charge_payload(),
        request=_FakeRequest("X-IDEM-1", header="X-Idempotency-Key"),
        current_user=fake_user,
    )
    r2_id = r2["id"] if isinstance(r2, dict) else r2.id
    assert r1.id == r2_id
    assert _patch.folio_charges.insert_calls == 1


async def test_charge_in_flight_same_key_returns_409(_patch, fake_user):
    """A concurrent retry that lands while the original is still
    processing must see a 409, not a duplicate insert."""
    # Seed a processing lock with the exact id claim_idempotency would build.
    from shared_kernel.idempotency import _lock_id
    seeded = _lock_id("tenant-A", "folio_charge:F1", "IDEM-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_charge:F1",
        "idempotency_key": "IDEM-INFLIGHT",
        "status": "processing",
    })
    with pytest.raises(HTTPException) as exc:
        await folio_router.post_charge_to_folio(
            folio_id="F1",
            charge_data=_charge_payload(),
            request=_FakeRequest("IDEM-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    assert _patch.folio_charges.insert_calls == 0


async def test_charge_post_insert_failure_replays_same_id(monkeypatch, _patch, fake_user):
    """If a best-effort side-effect (audit, webhook, balance update) raises
    AFTER the durable insert, a retry with the same key must replay the
    cached row — never insert a second one."""
    boom = {"raised": False}

    async def _flaky_audit(**_kw):
        if not boom["raised"]:
            boom["raised"] = True
            raise RuntimeError("audit sink down")

    monkeypatch.setattr(folio_router, "create_audit_log", _flaky_audit)

    with pytest.raises(RuntimeError):
        await folio_router.post_charge_to_folio(
            folio_id="F1",
            charge_data=_charge_payload(),
            request=_FakeRequest("IDEM-POSTFAIL"),
            current_user=fake_user,
        )
    # Exactly one row exists; the lock must NOT have been released, so a
    # retry replays the cached body (no second insert).
    assert _patch.folio_charges.insert_calls == 1
    original_id = _patch.folio_charges.docs[0]["id"]

    replay = await folio_router.post_charge_to_folio(
        folio_id="F1",
        charge_data=_charge_payload(),
        request=_FakeRequest("IDEM-POSTFAIL"),
        current_user=fake_user,
    )
    replay_id = replay["id"] if isinstance(replay, dict) else replay.id
    assert replay_id == original_id
    assert _patch.folio_charges.insert_calls == 1


async def test_payment_replay_with_x_prefixed_header(_patch, fake_user):
    r1 = await folio_router.post_payment_to_folio(
        folio_id="F1",
        payment_data=_payment_payload(),
        request=_FakeRequest("X-PAY-1", header="X-Idempotency-Key"),
        current_user=fake_user,
    )
    r2 = await folio_router.post_payment_to_folio(
        folio_id="F1",
        payment_data=_payment_payload(),
        request=_FakeRequest("X-PAY-1", header="X-Idempotency-Key"),
        current_user=fake_user,
    )
    r2_id = r2["id"] if isinstance(r2, dict) else r2.id
    assert r1.id == r2_id
    assert _patch.payments.insert_calls == 1


async def test_payment_in_flight_same_key_returns_409(_patch, fake_user):
    from shared_kernel.idempotency import _lock_id
    seeded = _lock_id("tenant-A", "folio_payment:F1", "PAY-INFLIGHT")
    _patch.idempotency_keys.docs.append({
        "_id": seeded,
        "tenant_id": "tenant-A",
        "scope": "folio_payment:F1",
        "idempotency_key": "PAY-INFLIGHT",
        "status": "processing",
    })
    with pytest.raises(HTTPException) as exc:
        await folio_router.post_payment_to_folio(
            folio_id="F1",
            payment_data=_payment_payload(),
            request=_FakeRequest("PAY-INFLIGHT", header="X-Idempotency-Key"),
            current_user=fake_user,
        )
    assert exc.value.status_code == 409
    assert _patch.payments.insert_calls == 0


async def test_payment_key_scoped_per_folio(_patch, fake_user):
    # Seed a second folio.
    _patch.folios.docs.append({
        "id": "F2",
        "tenant_id": "tenant-A",
        "status": "open",
        "booking_id": "B2",
        "folio_number": "1002",
    })
    r1 = await folio_router.post_payment_to_folio(
        folio_id="F1",
        payment_data=_payment_payload(),
        request=_FakeRequest("SAME"),
        current_user=fake_user,
    )
    r2 = await folio_router.post_payment_to_folio(
        folio_id="F2",
        payment_data=_payment_payload(),
        request=_FakeRequest("SAME"),
        current_user=fake_user,
    )
    # Same idempotency-key but different folio scope -> two distinct rows.
    assert r1.id != r2.id
    assert _patch.payments.insert_calls == 2
