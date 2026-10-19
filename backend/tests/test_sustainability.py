"""Sustainability arithmetic over HTTP, as a signed-in hotel administrator.

Access rules (anonymous 401, wrong role 403, hotel isolation) are in
tests/unit/test_sustainability_isolation_http.py; this file keeps the
original calculation checks.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import sustainability as module
from tests.unit.test_sustainability_isolation_http import _DB, _stay_metrics, _user


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module, "db", _DB())
    monkeypatch.setattr(module, "load_stay_night_metrics", _stay_metrics)
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_current_user] = lambda: _user("hotel-a")
    return TestClient(app)


def test_list_factors(client):
    response = client.get("/api/sustainability/factors")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["name"] == "Purchased Electricity"


def test_create_record(client):
    payload = {"consumption_type": "electricity", "period_start": "2026-07-01", "period_end": "2026-07-31",
               "amount": 1000.0, "evidence_url": "http://example.com/invoice.pdf"}
    response = client.post("/api/sustainability/records", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == 2
    assert data["emissions_kg_co2e"] == 429.0


def test_create_record_invalid_type(client):
    payload = {"consumption_type": "invalid_type", "period_start": "2026-07-01", "period_end": "2026-07-31", "amount": 1000.0}
    response = client.post("/api/sustainability/records", json=payload)
    assert response.status_code == 400


def test_list_records(client):
    client.post("/api/sustainability/records", json={"consumption_type": "water", "period_start": "2026-07-01",
                                                     "period_end": "2026-07-31", "amount": 10.0})
    response = client.get("/api/sustainability/records")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_generate_report(client):
    client.post("/api/sustainability/records", json={"consumption_type": "natural_gas", "period_start": "2026-07-01",
                                                     "period_end": "2026-07-31", "amount": 500.0})
    response = client.get("/api/sustainability/report?start_date=2026-07-01&end_date=2026-07-31")
    assert response.status_code == 200
    data = response.json()
    assert data["total_scope_1"] == round(500.0 * 2.02266, 2)
    assert data["total_emissions"] == data["total_scope_1"]
    assert data["total_room_nights"] == 0 and data["emissions_per_room_night"] is None
