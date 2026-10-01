from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.wbe_public as wbe


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _length):
        return self.rows


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.inserted = []

    async def find_one(self, query, _projection=None):
        return next((row for row in self.rows if all(row.get(k) == v for k, v in query.items())), None)

    def find(self, query, _projection=None):
        rows = [row for row in self.rows if all(row.get(k) == v for k, v in query.items())]
        return FakeCursor(rows)

    async def count_documents(self, _query):
        return 0

    async def insert_one(self, document):
        self.inserted.append(document)

    async def delete_one(self, _query):
        return None


@pytest.fixture
def client(monkeypatch):
    fake_db = SimpleNamespace(
        tenants=FakeCollection([{"id": "test_hotel", "property_name": "Test Otel", "currency": "TRY", "subscription_status": "active", "modules": {"booking_engine": True}}]),
        rooms=FakeCollection([
            {"id": "room-101", "tenant_id": "test_hotel", "room_number": "101", "room_type": "Standart", "capacity": 2, "base_price": 1500, "status": "available"},
            {"id": "room-102", "tenant_id": "test_hotel", "room_number": "102", "room_type": "Standart", "capacity": 2, "base_price": 1600, "status": "available"},
        ]),
        bookings=FakeCollection(),
        guests=FakeCollection(),
        folios=FakeCollection(),
        audit_logs=FakeCollection(),
    )
    monkeypatch.setattr(wbe, "db", fake_db)
    monkeypatch.setattr(wbe, "create_booking_atomic", AsyncMock())
    monkeypatch.setattr(wbe, "release_booking_nights", AsyncMock())
    monkeypatch.setattr(wbe, "generate_folio_number", AsyncMock(return_value="F-2026-0001"))
    monkeypatch.setattr(wbe, "encrypt_guest_insert", lambda value: value)
    app = FastAPI()
    app.include_router(wbe.router)
    return TestClient(app), fake_db


def test_wbe_availability_uses_real_hotel_rooms(client):
    http, _db = client
    check_in = date.today()
    check_out = check_in + timedelta(days=2)
    response = http.get(f"/api/wbe/test_hotel/availability?check_in={check_in}&check_out={check_out}&adults=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["room_type_id"] == "Standart"
    assert data[0]["available_count"] == 2
    assert data[0]["price_per_night"] == 1500
    assert data[0]["total_price"] == 3000
    assert data[0]["currency"] == "TRY"


def test_wbe_booking_creates_guest_booking_folio_and_audit(client):
    http, fake_db = client
    check_in = date.today()
    check_out = check_in + timedelta(days=2)
    payload = {"room_type_id": "Standart", "check_in": check_in.isoformat(), "check_out": check_out.isoformat(), "adults": 2, "children": 0, "guest_name": "Test User", "guest_email": "test@example.com", "guest_phone": "1234567890", "special_requests": "Late check-in"}
    response = http.post("/api/wbe/test_hotel/book", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["total_price"] == 3000
    assert fake_db.guests.inserted
    assert fake_db.folios.inserted
    assert fake_db.audit_logs.inserted[0]["action"] == "wbe_booking_created"
    wbe.create_booking_atomic.assert_awaited_once()


def test_wbe_invalid_dates(client):
    http, _db = client
    check_in = date.today()
    response = http.get(f"/api/wbe/test_hotel/availability?check_in={check_in}&check_out={check_in - timedelta(days=2)}")
    assert response.status_code == 400


def test_wbe_unknown_tenant_is_not_public(client):
    http, _db = client
    check_in = date.today()
    response = http.get(f"/api/wbe/unknown/availability?check_in={check_in}&check_out={check_in + timedelta(days=1)}")
    assert response.status_code == 404
