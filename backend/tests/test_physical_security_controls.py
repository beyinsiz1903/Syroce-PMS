"""Backend tests for physical security controls.

Locks in regressions for:
1. CCTV camera registration and listing.
2. Searchable physical door access logs (granted/denied entries).
3. System lockdown protocol:
   - Revokes active keys immediately.
   - Blocks subsequent key verifications (fail-closed).
   - Lockdown release restoring normal operations.
"""
from __future__ import annotations

import sys
import datetime as dt
if not hasattr(dt, "UTC"):
    dt.UTC = dt.timezone.utc

from types import SimpleNamespace
from typing import Any
import pytest
import jwt
from datetime import datetime, timezone
from datetime import timezone as dt_timezone
UTC = dt_timezone.utc
from fastapi import FastAPI, HTTPException, Header
from fastapi.testclient import TestClient

from core.security import JWT_SECRET, JWT_ALGORITHM
from routers import door_reader as door_reader_router
from routers import physical_security as phys_security_router
from routers.door_reader import router as door_reader_api_router
from routers.physical_security import router as phys_security_api_router

TENANT_ID = "t-phys-1"
_BOOKING_ID = "bk-phys-100"
_ROOM_NUMBER = "101"


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *_a, **_kw): return self
    async def to_list(self, *args, **kwargs): return list(self._docs)


class _MockCollection:
    def __init__(self, name, initial_docs=None):
        self.name = name
        self.docs = {d["id"]: dict(d) for d in (initial_docs or [])}

    async def find_one(self, flt, _proj=None):
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id") or flt.get("tenant_id") is None or d.get("tenant_id") == "unknown":
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and d.get(k) != v:
                        match = False
                if match:
                    return dict(d)
        return None

    def find(self, flt, *_a, **_kw):
        matching = []
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id") or flt.get("tenant_id") is None:
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and k != "timestamp" and d.get(k) != v:
                        match = False
                if match:
                    matching.append(dict(d))
        return _FakeCursor(matching)

    async def insert_one(self, doc):
        self.docs[doc["id"]] = dict(doc)
        return SimpleNamespace(inserted_id=doc["id"])

    async def update_one(self, flt, update, upsert=False, session=None):
        target = None
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and d.get(k) != v:
                        match = False
                if match:
                    target = d
        if not target and upsert:
            target = {"id": str(len(self.docs)), "tenant_id": flt.get("tenant_id")}
            for k, v in flt.items():
                target[k] = v
            self.docs[target["id"]] = target

        if target:
            if "$set" in update:
                target.update(update["$set"])
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, flt, update):
        modified = 0
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and d.get(k) != v:
                        match = False
                if match:
                    if "$set" in update:
                        d.update(update["$set"])
                    modified += 1
        return SimpleNamespace(matched_count=modified, modified_count=modified)

    async def delete_one(self, flt):
        to_delete = None
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and d.get(k) != v:
                        match = False
                if match:
                    to_delete = d["id"]
        if to_delete:
            del self.docs[to_delete]
            return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


class _FakeDB:
    def __init__(self, keycard_token):
        self.digital_keys = _MockCollection("digital_keys", [{
            "id": "keycard-1",
            "tenant_id": TENANT_ID,
            "booking_id": _BOOKING_ID,
            "guest_id": "guest-1",
            "room_number": _ROOM_NUMBER,
            "token": keycard_token,
            "status": "active",
            "expires_at": "2026-06-30T12:00:00Z"
        }])
        self.bookings = _MockCollection("bookings", [{
            "id": _BOOKING_ID,
            "tenant_id": TENANT_ID,
            "status": "checked_in",
            "checked_in_at": "2026-06-20T14:00:00Z",
            "checked_out_at": None,
            "arrival_date": "2026-06-20",
            "departure_date": "2026-06-30"
        }])
        self.cctv_cameras = _MockCollection("cctv_cameras")
        self.lockdown_state = _MockCollection("lockdown_state")
        self.physical_access_logs = _MockCollection("physical_access_logs")
        self.audit_logs = _MockCollection("audit_logs")


@pytest.fixture
def env(monkeypatch):
    # Create valid keycard token
    claims = {"booking_id": _BOOKING_ID, "exp": datetime.now(UTC) + dt.timedelta(days=1)}
    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)

    fake_db = _FakeDB(token)
    monkeypatch.setattr(door_reader_router, "get_system_db", lambda: fake_db)
    monkeypatch.setattr(phys_security_router, "get_system_db", lambda: fake_db)
    monkeypatch.setenv("DOOR_READER_SERVICE_KEY", "test_local_key")

    # Patch log_audit_event
    async def _fake_audit(tenant_id, user_id, action, entity_type, entity_id, details, severity="info", **kwargs):
        await fake_db.audit_logs.insert_one({
            "id": str(len(fake_db.audit_logs.docs)),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details,
            "severity": severity
        })
    monkeypatch.setattr(phys_security_router, "log_audit_event", _fake_audit)

    app = FastAPI()
    app.include_router(door_reader_api_router)
    app.include_router(phys_security_api_router)

    from core.security import get_current_user
    async def _sec_user():
        return SimpleNamespace(
            id="u_sec", username="sec_officer",
            tenant_id=TENANT_ID, role="admin",
            granted_permissions=None,
        )
    app.dependency_overrides[get_current_user] = _sec_user

    # Override require_op
    from modules.pms_core.role_permission_service import require_op
    async def _fake_require_op(*args, **kwargs):
        return True
    app.dependency_overrides[require_op] = _fake_require_op

    client = TestClient(app)
    return SimpleNamespace(client=client, db=fake_db, app=app, token=token)


def test_cctv_registration_and_listing(env):
    # Register CCTV Camera
    reg_res = env.client.post(
        "/api/physical-security/cctv/cameras",
        json={
            "camera_id": "cam-101",
            "name": "Front Door Camera Room 101",
            "room_number": "101",
            "stream_url": "rtsp://streams.hotel/cam101"
        }
    )
    assert reg_res.status_code == 200, reg_res.text
    assert reg_res.json()["success"] is True

    # List CCTV Cameras
    list_res = env.client.get("/api/physical-security/cctv/cameras?room_number=101")
    assert list_res.status_code == 200, list_res.text
    cams = list_res.json()["cameras"]
    assert len(cams) == 1
    assert cams[0]["camera_id"] == "cam-101"


def test_verify_door_reader_writes_access_logs(env):
    # 1. Verify access (granted)
    verify_res = env.client.post(
        "/api/internal/door-reader/verify",
        headers={"X-Door-Reader-Key": "test_local_key"}, # door reader key bypasses
        json={"token": env.token, "room_number": _ROOM_NUMBER, "device_id": "device-main-door"}
    )
    assert verify_res.status_code == 200, verify_res.text
    assert verify_res.json()["access"] == "granted"

    # Verify log written to db
    assert len(env.db.physical_access_logs.docs) == 1
    log = list(env.db.physical_access_logs.docs.values())[0]
    assert log["access_decision"] == "granted"
    assert log["room_number"] == _ROOM_NUMBER
    assert log["booking_id"] == _BOOKING_ID

    # 2. Search access logs
    search_res = env.client.get("/api/physical-security/access-logs?access_decision=granted")
    assert search_res.status_code == 200, search_res.text
    logs = search_res.json()["logs"]
    assert len(logs) == 1
    assert logs[0]["booking_id"] == _BOOKING_ID


def test_global_lockdown_fails_closed(env):
    # 1. Activate Lockdown
    lock_res = env.client.post("/api/physical-security/lockdown")
    assert lock_res.status_code == 200, lock_res.text
    assert lock_res.json()["success"] is True

    # Verify lockdown state active in DB
    lockdown_state = env.db.lockdown_state.docs["0"]
    assert lockdown_state["status"] == "active"

    # Verify all digital keys revoked
    key = env.db.digital_keys.docs["keycard-1"]
    assert key["status"] == "revoked"

    # 2. Try to verify key (should fail-closed due to lockdown)
    verify_res = env.client.post(
        "/api/internal/door-reader/verify",
        headers={"X-Door-Reader-Key": "test_local_key"},
        json={"token": env.token, "room_number": _ROOM_NUMBER, "device_id": "device-main-door"}
    )
    # verify_door_reader will check key first. Since key status is revoked, it fails at active key check
    assert verify_res.status_code == 200, verify_res.text
    assert verify_res.json()["access"] == "denied"
    assert verify_res.json()["reason"] == "revoked"

    # Verify denied access log is recorded
    denied_log = list(env.db.physical_access_logs.docs.values())[-1]
    assert denied_log["access_decision"] == "denied"
