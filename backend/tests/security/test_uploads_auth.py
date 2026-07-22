import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from fastapi import FastAPI
from routers.uploads import router as uploads_router
from routers.uploads import get_optional_user
from models.schemas import User

def mock_get_current_user(role="admin", tenant_id="tenantA"):
    def _mock():
        return User(id="user123", tenant_id=tenant_id, email="test@hotel.com", name="Test", role=role, is_active=True)
    return _mock

@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(uploads_router)
    yield app
    app.dependency_overrides.clear()

@pytest.fixture
def client(test_app):
    with TestClient(test_app) as test_client:
        yield test_client

def test_upload_anonymous_blocked(test_app, client):
    # Overrides are already isolated by the fixture; test anonymous explicitly
    test_app.dependency_overrides.pop(get_optional_user, None)
    response = client.get("/api/uploads/tenantA/rooms/123/file.jpg")
    assert response.status_code == 401

def test_upload_legacy_tenant_mismatch(test_app, client):
    test_app.dependency_overrides[get_optional_user] = mock_get_current_user(tenant_id="tenantB")
    response = client.get("/api/uploads/tenantA/rooms/123/file.jpg")
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]

def test_upload_legacy_tenant_match(test_app, client):
    test_app.dependency_overrides[get_optional_user] = mock_get_current_user(tenant_id="tenantA")
    response = client.get("/api/uploads/tenantA/rooms/123/file.jpg")
    # File doesn't exist, so we expect 404
    assert response.status_code == 404

def test_upload_path_traversal(test_app, client):
    test_app.dependency_overrides[get_optional_user] = mock_get_current_user(tenant_id="tenantA")
    # We use %2F so TestClient doesn't normalize it to /etc/passwd and hit the React catch-all (200)
    response = client.get("/api/uploads/tenantA%2F..%2F..%2F..%2Fetc%2Fpasswd")
    # Path traversal should be caught before or during path resolution
    assert response.status_code in (400, 403, 404)

def test_upload_super_admin_audit(test_app, client):
    test_app.dependency_overrides[get_optional_user] = mock_get_current_user(role="super_admin", tenant_id="superTenant")
    
    # We patch the database object itself, not the motor collection method
    with patch("routers.uploads.db") as mock_db, patch("pathlib.Path.is_file", return_value=True):
        mock_db.audit_logs.insert_one = AsyncMock()
        mock_db.uploads.find_one = AsyncMock(return_value=None)
        
        try:
            response = client.get("/api/uploads/tenantA/rooms/123/file.jpg")
        except RuntimeError:
            pass
        
        # Since is_file is mocked, it will try to return the FileResponse. It might raise an error or return 200.
        # But we only care that audit_logs.insert_one was called.
        
        mock_db.audit_logs.insert_one.assert_called_once()
        call_args = mock_db.audit_logs.insert_one.call_args[0][0]
        assert call_args["action"] == "super_admin_file_access"
        assert call_args["target_tenant_id"] == "tenantA"

    test_app.dependency_overrides.clear()
