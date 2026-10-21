"""Backend tests for the BEO client signature portal.

Locks in regressions for:
1. `POST /api/mice/events/{id}/signature/request` (generates token, saves request info)
2. `GET /api/mice/public/beo/verify` (verifies token, returns BEO summary)
3. `POST /api/mice/public/beo/sign` (verifies token, enforces transition, updates status, saves signature, logs audit)
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.security import JWT_ALGORITHM, JWT_SECRET
from routers import mice as mice_router
from routers.mice import router as mice_api_router

TENANT_ID = "t-sig-1"
OTHER_TENANT = "t-sig-2"

_EVENT_ID = "evt-sig-test"
_BASE_EVENT = {
    "id": _EVENT_ID,
    "tenant_id": TENANT_ID,
    "name": "Sig Conference",
    "client_name": "Acme Corp",
    "client_email": "client@example.com",
    "status": "definite",
    "space_bookings": [],
    "resources": [],
}


class _FakeCursor:
    async def to_list(self, length=None):
        return list(self._docs)
    def __init__(self, docs): self._docs = list(docs)
    def __aiter__(self):
        self._it = iter(self._docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration


class _EventsCollection:
    def __init__(self, events):
        self._events = {e["id"]: deepcopy(e) for e in events}

    async def find_one(self, flt, _proj=None):
        for e in self._events.values():
            if e["id"] == flt.get("id") and e["tenant_id"] == flt.get("tenant_id"):
                return dict(e)
        return None

    async def update_one(self, flt, update, session=None):
        for e in self._events.values():
            if e["id"] == flt.get("id") and e["tenant_id"] == flt.get("tenant_id"):
                if "$set" in update:
                    e.update(update["$set"])
                for key, value in update.get("$push", {}).items():
                    e.setdefault(key, []).append(deepcopy(value))
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _SpacesCollection:
    def find(self, flt, *_a, **_kw):
        return _FakeCursor([])


class _AuditCollection:
    def __init__(self): self.inserted = []
    async def insert_one(self, doc):
        self.inserted.append(doc)
        return SimpleNamespace(inserted_id=str(len(self.inserted)))


class _FakeDB:
    def __init__(self):
        self.mice_events = _EventsCollection([_BASE_EVENT])
        self.mice_spaces = _SpacesCollection()
        self.audit_logs = _AuditCollection()
        self.client = SimpleNamespace()


@pytest.fixture
def env(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(mice_router, "get_system_db", lambda: fake_db)
    monkeypatch.setattr(mice_router, "_tenant_currency_code", AsyncMock(return_value="TRY"))
    monkeypatch.setattr("core.entitlements.enforcement.tenant_has_feature", AsyncMock(return_value=True))

    # Patch with_resource_locks to directly call the callback (standalone fallback or direct callback execution)
    async def _fake_locks(*args, callback, **kwargs):
        await callback(None)
    monkeypatch.setattr(mice_router, "with_resource_locks", _fake_locks)


    app = FastAPI()
    app.include_router(mice_api_router)

    from core.security import get_current_user
    async def _admin_user():
        return SimpleNamespace(
            id="u1", username="tester",
            tenant_id=TENANT_ID, role="admin",
            granted_permissions=None,
        )
    app.dependency_overrides[get_current_user] = _admin_user

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=fake_db, app=app)


def test_signature_workflow_happy_path(env):
    # 1. Request signature token
    req_res = env.client.post(
        f"/api/mice/events/{_EVENT_ID}/signature/request",
        json={"client_email": "client@example.com", "expires_in_days": 5}
    )
    assert req_res.status_code == 200, req_res.text
    token = req_res.json()["token"]
    assert token is not None

    # Verify that request was saved in event doc
    event_doc = env.db.mice_events._events[_EVENT_ID]
    assert event_doc["signature_request"]["client_email"] == "client@example.com"
    assert event_doc["signature_request"]["token"] == token

    # 2. Public verify BEO
    verify_res = env.client.get(f"/api/mice/public/beo/verify?token={token}")
    assert verify_res.status_code == 200, verify_res.text
    data = verify_res.json()
    assert data["event"]["name"] == "Sig Conference"
    assert data["signed"] is False

    # 3. Submit signature
    sign_res = env.client.post(
        "/api/mice/public/beo/sign",
        json={
            "token": token,
            "signature_name": "John Doe",
            "signature_data": "drawn-sig-data",
            "ip_address": "127.0.0.1",
            "user_agent": "Mozilla/5.0"
        }
    )
    assert sign_res.status_code == 200, sign_res.text
    assert sign_res.json()["success"] is True

    # Verify event document is updated
    updated_doc = env.db.mice_events._events[_EVENT_ID]
    assert updated_doc["status"] == "confirmed"
    assert updated_doc["signature"]["name"] == "John Doe"
    assert updated_doc["signature"]["signature_data"] == "drawn-sig-data"

    # Verify audit log was written
    assert len(env.db.audit_logs.inserted) == 1
    audit_row = env.db.audit_logs.inserted[0]
    assert audit_row["action"] == "beo.sign"
    assert audit_row["entity_id"] == _EVENT_ID


def test_approval_request_and_amendment_cannot_bypass_banquet_entitlement(env, monkeypatch):
    monkeypatch.setattr("core.entitlements.enforcement.tenant_has_feature", AsyncMock(return_value=False))
    for suffix, body in [("signature/request", {"client_email": "client@example.com"}),
                         ("amendment", {"reason": "Customer requested a change", "expected_revision": "revision"})]:
        response = env.client.post(f"/api/mice/events/{_EVENT_ID}/{suffix}", json=body)
        assert response.status_code == 403, response.text


def test_public_verify_invalid_token_returns_400(env):
    verify_res = env.client.get("/api/mice/public/beo/verify?token=invalid-token-here")
    assert verify_res.status_code == 400
    assert "Geçersiz" in verify_res.json()["detail"]


def test_public_verify_expired_token_returns_400(env):
    # Create expired token
    claims = {
        "event_id": _EVENT_ID,
        "tenant_id": TENANT_ID,
        "client_email": "client@example.com",
        "exp": datetime.now(UTC) - timedelta(hours=1)
    }
    expired_token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)

    verify_res = env.client.get(f"/api/mice/public/beo/verify?token={expired_token}")
    assert verify_res.status_code == 400
    assert "dolmuş" in verify_res.json()["detail"]


def test_sign_invalid_status_returns_409(env):
    req_res = env.client.post(
        f"/api/mice/events/{_EVENT_ID}/signature/request",
        json={"client_email": "client@example.com"}
    )
    token = req_res.json()["token"]
    # A previously valid invitation cannot be used after cancellation.
    env.db.mice_events._events[_EVENT_ID]["status"] = "cancelled"

    sign_res = env.client.post(
        "/api/mice/public/beo/sign",
        json={
            "token": token,
            "signature_name": "John Doe",
            "signature_data": "drawn-sig-data"
        }
    )
    assert sign_res.status_code == 409
    assert "Mevcut durum: cancelled" in sign_res.json()["detail"]
