import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
import uuid

from server import app
from routers.uploads import get_optional_user, get_optional_vendor
from models.schemas import User

client = TestClient(app)

def mock_get_current_user(role="admin", tenant_id="hotel_A"):
    def _mock():
        return User(id="user123", tenant_id=tenant_id, email="hotel@test.com", name="Hotel User", role=role, is_active=True)
    return _mock

def mock_get_current_vendor(vendor_id="vendor_A"):
    def _mock():
        return vendor_id
    return _mock

@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()

def test_vendor_access_own_legacy_file():
    # Vendor accesses their own file via legacy path
    app.dependency_overrides[get_optional_vendor] = mock_get_current_vendor(vendor_id="vendor_A")
    app.dependency_overrides[get_optional_user] = lambda: None
    
    response = client.get("/api/uploads/vendors/vendor_A/products/file.jpg")
    # Returns 404 because file isn't on disk, but NOT 401/403
    assert response.status_code == 404

def test_vendor_access_other_legacy_file():
    # Vendor A tries to access Vendor B's file
    app.dependency_overrides[get_optional_vendor] = mock_get_current_vendor(vendor_id="vendor_A")
    app.dependency_overrides[get_optional_user] = lambda: None
    
    response = client.get("/api/uploads/vendors/vendor_B/products/file.jpg")
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]

def test_user_access_vendor_legacy_file():
    # Hotel User tries to access Vendor A's file (Marketplace public)
    app.dependency_overrides[get_optional_user] = mock_get_current_user(tenant_id="hotel_A")
    app.dependency_overrides[get_optional_vendor] = lambda: None
    
    response = client.get("/api/uploads/vendors/vendor_A/products/file.jpg")
    # Returns 404 because file isn't on disk, but NOT 403
    assert response.status_code == 404

def test_vendor_access_tenant_legacy_file():
    # Vendor tries to access a hotel tenant's file
    app.dependency_overrides[get_optional_vendor] = mock_get_current_vendor(vendor_id="vendor_A")
    app.dependency_overrides[get_optional_user] = lambda: None
    
    response = client.get("/api/uploads/hotel_A/rooms/123/file.jpg")
    assert response.status_code == 403
    assert "Vendors cannot access tenant files" in response.json()["detail"]

@patch("routers.uploads.db")
def test_vendor_access_own_db_file(mock_db):
    app.dependency_overrides[get_optional_vendor] = mock_get_current_vendor(vendor_id="vendor_A")
    app.dependency_overrides[get_optional_user] = lambda: None
    
    upload_id = str(uuid.uuid4())
    mock_db.uploads.find_one = AsyncMock(return_value={
        "_id": upload_id,
        "owner_type": "vendor",
        "vendor_id": "vendor_A",
        "relative_path": "vendors/vendor_A/products/file.jpg"
    })
    
    response = client.get(f"/api/uploads/{upload_id}")
    assert response.status_code == 404 # file not on disk

@patch("routers.uploads.db")
def test_vendor_access_other_db_file_audit(mock_db):
    app.dependency_overrides[get_optional_vendor] = mock_get_current_vendor(vendor_id="vendor_A")
    app.dependency_overrides[get_optional_user] = lambda: None
    
    upload_id = str(uuid.uuid4())
    mock_db.uploads.find_one = AsyncMock(return_value={
        "_id": upload_id,
        "owner_type": "vendor",
        "vendor_id": "vendor_B",
        "relative_path": "vendors/vendor_B/products/file.jpg"
    })
    mock_db.audit_logs.insert_one = AsyncMock()
    
    response = client.get(f"/api/uploads/{upload_id}")
    assert response.status_code == 403
    
    mock_db.audit_logs.insert_one.assert_called_once()
    call_args = mock_db.audit_logs.insert_one.call_args[0][0]
    assert call_args["action"] == "unauthorized_vendor_file_access"
    assert call_args["vendor_id"] == "vendor_A"
    assert call_args["target_vendor_id"] == "vendor_B"
