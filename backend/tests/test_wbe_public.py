from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.wbe_public import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)

def test_wbe_availability(client):
    tenant_id = "test_hotel"
    check_in = date.today()
    check_out = check_in + timedelta(days=2)

    response = client.get(f"/api/wbe/{tenant_id}/availability?check_in={check_in}&check_out={check_out}&adults=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["price_per_night"] > 0
    assert data[0]["total_price"] == data[0]["price_per_night"] * 2

def test_wbe_booking(client):
    tenant_id = "test_hotel"
    check_in = date.today()
    check_out = check_in + timedelta(days=2)

    payload = {
        "room_type_id": "rt_std_01",
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "adults": 2,
        "children": 0,
        "guest_name": "Test User",
        "guest_email": "test@example.com",
        "guest_phone": "1234567890",
        "special_requests": "Late check-in"
    }

    response = client.post(f"/api/wbe/{tenant_id}/book", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert "booking_id" in data
    assert "confirmation_number" in data

def test_wbe_invalid_dates(client):
    tenant_id = "test_hotel"
    check_in = date.today()
    check_out = check_in - timedelta(days=2)

    response = client.get(f"/api/wbe/{tenant_id}/availability?check_in={check_in}&check_out={check_out}")
    assert response.status_code == 400
