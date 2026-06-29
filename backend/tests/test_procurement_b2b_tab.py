import pytest
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.procurement_b2b import router as procurement_router
from models.schemas import User

app = FastAPI()
app.include_router(procurement_router)
client = TestClient(app)


@pytest.fixture
def override_deps():
    from core.security import get_current_user
    
    async def mock_user():
        return User(
            id="user-1",
            tenant_id="tenant-1",
            email="procurement@example.com",
            name="Procurement Officer",
            role="procurement",
            roles=["procurement"]
        )
        
    app.dependency_overrides[get_current_user] = mock_user
    yield
    app.dependency_overrides = {}


@patch("routers.procurement_b2b.get_system_db")
@pytest.mark.asyncio
async def test_get_proposals_permission_and_structure(mock_get_db, override_deps):
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    mock_db.inventory_items = MagicMock()
    mock_db.mp_products = MagicMock()
    mock_db.mp_vendors = MagicMock()
    
    # Mock database queries
    # 1. Fetch inventory items
    mock_inventory_cursor = AsyncMock()
    mock_inventory_cursor.to_list.return_value = [
        {
            "id": "item-1",
            "tenant_id": "tenant-1",
            "name": "Domates",
            "sku": "DOM-1",
            "quantity": 2.0,
            "reorder_level": 5.0
        }
    ]
    mock_db.inventory_items.find.return_value = mock_inventory_cursor
    
    # 2. Match with mp_products
    mock_db.mp_products.find_one = AsyncMock()
    mock_db.mp_products.find_one.return_value = {
        "id": "mp-1",
        "vendor_id": "vendor-1",
        "name": "Domates",
        "sku": "DOM-1",
        "moq": 5,
        "unit": "kg",
        "price_try": 25.0,
        "is_active": True
    }
    
    # 3. Fetch mp_vendors
    mock_db.mp_vendors.find_one = AsyncMock()
    mock_db.mp_vendors.find_one.return_value = {
        "id": "vendor-1",
        "company_name": "Tedarikçi A",
        "status": "approved"
    }
    
    # Test endpoint
    response = client.get("/api/procurement/b2b/proposals")
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure (it must be array of objects)
    assert "proposals" in data
    assert isinstance(data["proposals"], list)
    assert len(data["proposals"]) == 1
    assert data["proposals"][0]["vendor_id"] == "vendor-1"
    assert data["proposals"][0]["vendor_name"] == "Tedarikçi A"
    assert len(data["proposals"][0]["lines"]) == 1
    assert data["proposals"][0]["lines"][0]["name"] == "Domates"
    assert data["proposals"][0]["lines"][0]["proposed_qty"] == 8  # 5 * 2 - 2 = 8


@patch("routers.procurement_b2b.place_order")
@patch("routers.procurement_b2b.get_system_db")
@pytest.mark.asyncio
async def test_approve_orders_payload(mock_get_db, mock_place_order, override_deps):
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_get_db.return_value = mock_db
    
    mock_db.mp_products = MagicMock()
    mock_db.procurement_b2b_replenishments = MagicMock()
    
    # Mock mp_products find
    mock_products_cursor = AsyncMock()
    mock_products_cursor.to_list.return_value = [
        {
            "id": "mp-1",
            "vendor_id": "vendor-1",
            "is_active": True
        }
    ]
    mock_db.mp_products.find.return_value = mock_products_cursor
    
    # Mock place_order return
    mock_place_order.return_value = {
        "id": "order-1",
        "order_no": "ORD-2026-0001",
        "vendor_name": "Tedarikçi A",
        "total": 200.0
    }
    
    mock_db.procurement_b2b_replenishments.insert_one = AsyncMock()
    
    payload = {
        "lines": [
            {
                "inventory_item_id": "item-1",
                "mp_product_id": "mp-1",
                "quantity": 8
            }
        ],
        "shipping_address": "Otel Merkez Depo, Kat -1",
        "contact_name": "Satın Alma Sorumlusu",
        "contact_phone": "05551234567",
        "payment_method": "bank_transfer",
        "notes": "Otomatik sipariş"
    }
    
    response = client.post("/api/procurement/b2b/orders/approve", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert mock_place_order.call_count == 1
    mock_db.procurement_b2b_replenishments.insert_one.assert_called_once()
