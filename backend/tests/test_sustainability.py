import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.sustainability import router

@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)

def test_list_factors(client):
    response = client.get("/api/sustainability/factors")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["name"] == "Purchased Electricity"

def test_create_record(client):
    payload = {
        "consumption_type": "electricity",
        "period_start": "2026-07-01",
        "period_end": "2026-07-31",
        "amount": 1000.0,
        "evidence_url": "http://example.com/invoice.pdf"
    }
    response = client.post("/api/sustainability/records", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == 2
    assert data["emissions_kg_co2e"] == 429.0

def test_create_record_invalid_type(client):
    payload = {
        "consumption_type": "invalid_type",
        "period_start": "2026-07-01",
        "period_end": "2026-07-31",
        "amount": 1000.0
    }
    response = client.post("/api/sustainability/records", json=payload)
    assert response.status_code == 400

def test_list_records(client):
    response = client.get("/api/sustainability/records")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1

def test_generate_report(client):
    client.post("/api/sustainability/records", json={
        "consumption_type": "natural_gas",
        "period_start": "2026-07-01",
        "period_end": "2026-07-31",
        "amount": 500.0
    })
    
    response = client.get("/api/sustainability/report?start_date=2026-07-01&end_date=2026-07-31")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_scope_1"] > 0
    assert data["total_scope_2"] > 0
    assert data["total_emissions"] == data["total_scope_1"] + data["total_scope_2"] + data["total_scope_3"]
    assert data["total_room_nights"] == 3100
    assert data["emissions_per_room_night"] > 0
