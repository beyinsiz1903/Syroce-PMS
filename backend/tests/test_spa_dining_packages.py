"""Backend tests for the SPA & Restaurant Dining Cross-Departmental Package Scheduler.

Locks in regressions for:
1. Retrieval of packages.
2. Cross-departmental conflict checking (overlapping spa times, overlapping dining times).
3. Atomic package booking creation (creation of linked spa, dining, and cross-booking records).
4. Idempotent room folio charge integration.
"""
from __future__ import annotations

import sys
import datetime as dt
if not hasattr(dt, "UTC"):
    dt.UTC = dt.timezone.utc

from types import SimpleNamespace
from typing import Any
import pytest
from datetime import datetime, timezone
from datetime import timezone as dt_timezone
UTC = dt_timezone.utc
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import spa_dining_packages as spa_dining_router
from routers.spa_dining_packages import router as spa_dining_api_router

TENANT_ID = "t-pkg-1"
_THERAPIST_ID = "therapist-1"
_ROOM_ID = "room-1"
_OUTLET_ID = "outlet-1"
_TABLE_NUMBER = "T5"
_RESERVATION_ID = "res-hotel-123"


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
                    if k != "tenant_id" and d.get(k) != v:
                        match = False
                if match:
                    return dict(d)
        return None

    def find(self, flt, *_a, **_kw):
        matching = []
        for d in self.docs.values():
            if d.get("tenant_id") == flt.get("tenant_id"):
                match = True
                for k, v in flt.items():
                    if k != "tenant_id" and d.get(k) != v:
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

    async def create_index(self, keys, **kwargs):
        return "mock_index"


class _FakeDB:
    def __init__(self):
        self.spa_appointments = _MockCollection("spa_appointments")
        self.table_reservations = _MockCollection("table_reservations")
        self.table_layouts = _MockCollection("table_layouts", [{
            "id": "tbl-5",
            "tenant_id": TENANT_ID,
            "outlet_id": _OUTLET_ID,
            "table_number": _TABLE_NUMBER,
            "status": "available"
        }])
        self.bookings = _MockCollection("bookings", [{
            "id": _RESERVATION_ID,
            "tenant_id": TENANT_ID,
            "status": "in_house"
        }])
        self.spa_dining_package_bookings = _MockCollection("spa_dining_package_bookings")
        self.folio_postings = _MockCollection("folio_postings")


@pytest.fixture
def env(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(spa_dining_router, "get_system_db", lambda: fake_db)

    # Mock the SPA conflict checking from domains/spa/router.py
    async def _mock_check_spa_conflict(tenant_id, therapist_id, room_id, start, end, **kwargs):
        # Scan spa_appointments
        for doc in fake_db.spa_appointments.docs.values():
            if doc.get("tenant_id") == tenant_id and doc.get("status") in ("scheduled", "in_progress"):
                doc_start = datetime.fromisoformat(doc["starts_at"])
                doc_end = datetime.fromisoformat(doc["ends_at"])
                if doc_start < end and doc_end > start:
                    if therapist_id and doc.get("therapist_id") == therapist_id:
                        return "Terapist çakışması"
                    if room_id and doc.get("room_id") == room_id:
                        return "Oda çakışması"
        return None

    monkeypatch.setattr(spa_dining_router, "_check_spa_conflict", _mock_check_spa_conflict)

    app = FastAPI()
    app.include_router(spa_dining_api_router)

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

    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=fake_db, app=app)


def test_list_packages(env):
    r = env.client.get("/api/spa-dining/packages")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["packages"]) == 2
    assert data["packages"][0]["id"] == "pkg_zen_dine"


def test_create_package_booking_happy_path(env):
    r = env.client.post(
        "/api/spa-dining/bookings",
        json={
            "package_id": "pkg_zen_dine",
            "spa_therapist_id": _THERAPIST_ID,
            "spa_room_id": _ROOM_ID,
            "dining_outlet_id": _OUTLET_ID,
            "dining_table_number": _TABLE_NUMBER,
            "starts_at": "2026-06-28T16:00:00Z",
            "guest_name": "Alice Smith",
            "guest_phone": "+905555555555",
            "reservation_id": _RESERVATION_ID,
            "charge_to_room": True
        }
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["success"] is True

    # Verify Spa Appt created
    assert len(env.db.spa_appointments.docs) == 1
    spa_appt = list(env.db.spa_appointments.docs.values())[0]
    assert spa_appt["guest_name"] == "Alice Smith"
    assert spa_appt["starts_at"] == "2026-06-28T16:00:00+00:00"

    # Verify Table Res created
    assert len(env.db.table_reservations.docs) == 1
    table_res = list(env.db.table_reservations.docs.values())[0]
    assert table_res["guest_name"] == "Alice Smith"
    # Massages ends at 17:00. Gap 30 min. Dining starts at 17:30.
    assert table_res["reservation_time"] == "2026-06-28T17:30:00+00:00"

    # Verify Table Layout status is reserved
    assert env.db.table_layouts.docs["tbl-5"]["status"] == "reserved"

    # Verify Folio charge created
    assert len(env.db.folio_postings.docs) == 1
    posting = list(env.db.folio_postings.docs.values())[0]
    assert posting["amount"] == 3200.0
    assert posting["reservation_id"] == _RESERVATION_ID


def test_create_package_booking_fails_on_spa_conflict(env):
    # Pre-populate conflicting spa appointment
    env.db.spa_appointments.docs["conflict-spa"] = {
        "id": "conflict-spa",
        "tenant_id": TENANT_ID,
        "starts_at": "2026-06-28T16:00:00+00:00",
        "ends_at": "2026-06-28T17:00:00+00:00",
        "therapist_id": _THERAPIST_ID,
        "status": "scheduled"
    }

    r = env.client.post(
        "/api/spa-dining/bookings",
        json={
            "package_id": "pkg_zen_dine",
            "spa_therapist_id": _THERAPIST_ID,
            "spa_room_id": _ROOM_ID,
            "dining_outlet_id": _OUTLET_ID,
            "dining_table_number": _TABLE_NUMBER,
            "starts_at": "2026-06-28T16:00:00Z",
            "guest_name": "Alice Smith"
        }
    )
    assert r.status_code == 409
    assert "SPA Kaynak Çakışması" in r.json()["detail"]


def test_create_package_booking_fails_on_dining_conflict(env):
    # Pre-populate conflicting dining table reservation
    env.db.table_reservations.docs["conflict-tbl"] = {
        "id": "conflict-tbl",
        "tenant_id": TENANT_ID,
        "outlet_id": _OUTLET_ID,
        "table_number": _TABLE_NUMBER,
        "reservation_time": "2026-06-28T17:30:00+00:00",
        "guest_name": "Bob",
        "status": "confirmed"
    }

    r = env.client.post(
        "/api/spa-dining/bookings",
        json={
            "package_id": "pkg_zen_dine",
            "spa_therapist_id": _THERAPIST_ID,
            "spa_room_id": _ROOM_ID,
            "dining_outlet_id": _OUTLET_ID,
            "dining_table_number": _TABLE_NUMBER,
            "starts_at": "2026-06-28T16:00:00Z",
            "guest_name": "Alice Smith"
        }
    )
    assert r.status_code == 409
    assert "Restoran Masa Çakışması" in r.json()["detail"]
