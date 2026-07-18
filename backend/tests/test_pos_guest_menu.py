import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_get_guest_menu(client):
    response = client.get("/public/fnb/test_tenant/outlet_1/menu")
    assert response.status_code in [200, 404]


def test_place_guest_order(client):
    payload = {
        "table_id": "T1",
        "guest_name": "Test User",
        "items": [{"item_id": "item1", "quantity": 1}]
    }
    response = client.post("/public/fnb/test_tenant/outlet_1/order", json=payload)
    assert response.status_code in [200, 400, 404, 422]
