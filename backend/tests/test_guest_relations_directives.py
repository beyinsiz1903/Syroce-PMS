"""Backend tests for the Guest Relations Smart Profile Entegrasyonu.

Locks in regressions for:
1. Historical preference analytics (SPA service/notes extraction, Minibar consumption patterns).
2. Automated prep directive document generation.
3. Automated task delegation to Housekeeping.
4. Booking alert synchronization for Front Desk review.
"""
from __future__ import annotations

import sys
import datetime as dt
if not hasattr(dt, "UTC"):
    dt.UTC = dt.timezone.utc

from types import SimpleNamespace
from typing import Any
import pytest
from datetime import datetime, timedelta, timezone
from datetime import timezone as dt_timezone
UTC = dt_timezone.utc
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import guest_relations as gr_router
from routers.guest_relations import router as gr_api_router

TENANT_ID = "t-gr-1"
_GUEST_ID = "guest-gr-1"
_BOOKING_ID = "booking-gr-1"


class _FakeCursor:
    def __init__(self, docs): self._docs = list(docs)
    def sort(self, *_a, **_kw): return self
    def __aiter__(self):
        self._it = iter(self._docs); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration
    async def to_list(self, *args, **kwargs): return list(self._docs)


class _MockCollection:
    def __init__(self, name, initial_docs=None):
        self.name = name
        self.docs = {d["id"]: dict(d) for d in (initial_docs or [])}

    async def find_one(self, flt, _proj=None):
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                match = True
                for k, v in flt.items():
                    if k in ("tenant_id", "pillow_type", "status", "description"):
                        continue
                    val = d.get(k)
                    if isinstance(v, dict) and "$in" in v:
                        if val not in v["$in"]:
                            match = False
                    elif val != v:
                        match = False
                if match:
                    return dict(d)
        return None

    def find(self, flt, *_a, **_kw):
        matching = []
        for d in self.docs.values():
            if flt.get("tenant_id") == flt.get("tenant_id"):
                match = True
                for k, v in flt.items():
                    if k in ("tenant_id", "description", "status"):
                        continue
                    val = d.get(k)
                    if isinstance(v, dict) and "$in" in v:
                        if val not in v["$in"]:
                            match = False
                    elif val != v:
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
            if d.get("tenant_id") == flt.get("tenant_id") and d.get("id") == flt.get("id"):
                target = d
        if target:
            if "$set" in update:
                target.update(update["$set"])
            return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


class _FakeDB:
    def __init__(self):
        self.guests = _MockCollection("guests", [
            {
                "id": _GUEST_ID,
                "tenant_id": TENANT_ID,
                "name": "Jane Doe",
                "pillow_preference": "Kaz tüyü"
            }
        ])
        self.bookings = _MockCollection("bookings", [
            {
                "id": _BOOKING_ID,
                "tenant_id": TENANT_ID,
                "guest_id": _GUEST_ID,
                "guest_name": "Jane Doe",
                "room_id": "104",
                "check_in": (datetime.now(UTC) + timedelta(hours=24)).isoformat(),
                "status": "confirmed",
                "special_requests": ""
            }
        ])
        self.spa_appointments = _MockCollection("spa_appointments", [
            {
                "id": "spa-1",
                "tenant_id": TENANT_ID,
                "guest_id": _GUEST_ID,
                "guest_name": "Jane Doe",
                "service_name": "Derin Doku Masajı",
                "notes": "lavanta yağı ile ovalama yapıldı"
            }
        ])
        self.folios = _MockCollection("folios", [
            {
                "id": "folio-gr-1",
                "tenant_id": TENANT_ID,
                "booking_id": _BOOKING_ID
            }
        ])
        self.folio_postings = _MockCollection("folio_postings", [
            {
                "id": "post-1",
                "tenant_id": TENANT_ID,
                "folio_id": "folio-gr-1",
                "description": "Minibar: Soda tüketimi"
            }
        ])
        self.guest_prep_directives = _MockCollection("guest_prep_directives")
        self.housekeeping_tasks = _MockCollection("housekeeping_tasks")


@pytest.fixture
def env(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(gr_router, "db", fake_db)

    app = FastAPI()
    app.include_router(gr_api_router)

    from core.security import get_current_user
    async def _admin_user():
        return SimpleNamespace(
            id="u1", username="admin",
            tenant_id=TENANT_ID, role="admin",
            granted_permissions=None,
        )
    app.dependency_overrides[get_current_user] = _admin_user

    from modules.pms_core.role_permission_service import require_op
    async def _fake_require_op(*args, **kwargs):
        return True
    app.dependency_overrides[require_op] = _fake_require_op

    client = TestClient(app)
    return SimpleNamespace(client=client, db=fake_db, app=app)


def test_get_guest_profile_analysis(env):
    r = env.client.get(f"/api/guest-relations/profiles/{_GUEST_ID}/analysis")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["guest_id"] == _GUEST_ID
    assert data["pillow_preference"] == "Kaz tüyü"
    assert "Derin Doku Masajı" in data["spa_preference"]
    assert "lavanta" in data["spa_preference"]
    assert "Soda" in data["minibar_preference"]


def test_trigger_room_preparations(env):
    r = env.client.post("/api/guest-relations/preparations/trigger")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["success"] is True
    assert res["directives_generated"] == 1

    # Verify Directive created
    assert len(env.db.guest_prep_directives.docs) == 1
    dir_doc = list(env.db.guest_prep_directives.docs.values())[0]
    assert dir_doc["guest_name"] == "Jane Doe"
    assert dir_doc["pillow_preference"] == "Kaz tüyü"

    # Verify Housekeeping Task created
    assert len(env.db.housekeeping_tasks.docs) == 1
    task = list(env.db.housekeeping_tasks.docs.values())[0]
    assert task["task_type"] == "special_setup"
    assert "Kaz tüyü" in task["description"]
    assert "Soda" in task["description"]
    assert "Derin Doku" in task["description"]

    # Verify booking special requests updated
    booking = env.db.bookings.docs[_BOOKING_ID]
    assert "[MİSAFİR İLİŞKİLERİ DİREKTİFİ]" in booking["special_requests"]
