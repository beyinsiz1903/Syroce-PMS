import pytest
import uuid
import jwt
from datetime import datetime, UTC, timedelta
from pathlib import Path
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from server import app
from core.security import JWT_SECRET as USER_JWT_SECRET, JWT_ALGORITHM
from modules.supplies_market.vendor_auth import JWT_SECRET as VENDOR_JWT_SECRET
from routers.uploads import UPLOAD_DIR

client = TestClient(app)

def create_user_token(user_id="user123", tenant_id="hotel_A"):
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": "admin",
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=15)
    }
    return jwt.encode(payload, USER_JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_vendor_token(vendor_id="vendor_A"):
    payload = {
        "sub": "vendor@test.com",
        "vendor_id": vendor_id,
        "scope": "vendor",
        "exp": datetime.now(UTC) + timedelta(minutes=15)
    }
    return jwt.encode(payload, VENDOR_JWT_SECRET, algorithm=JWT_ALGORITHM)

@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def temp_vendor_file():
    vendor_dir = UPLOAD_DIR / "vendors" / "vendor_A" / "products"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    file_path = vendor_dir / "real_test.jpg"
    file_path.write_text("dummy image content")
    
    yield file_path
    
    # cleanup
    try:
        file_path.unlink()
    except:
        pass

def test_real_auth_separation_user_token(temp_vendor_file):
    token = create_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    with patch("core.security._user_doc_cache_get") as mock_cache:
        mock_cache.return_value = {"_id": "user123", "tenant_id": "hotel_A", "email": "hotel@test.com", "name": "Hotel User", "role": "admin", "is_active": True, "failed_login_attempts": 0}
        with patch("infra.auth_cache_pubsub.auth_cache_pubsub"):
            response = client.get("/api/uploads/vendors/vendor_A/products/real_test.jpg", headers=headers)
            assert response.status_code == 200
            assert response.text == "dummy image content"

def test_real_auth_separation_vendor_token(temp_vendor_file):
    token = create_vendor_token("vendor_A")
    headers = {"Authorization": f"Bearer {token}"}
    
    with patch("security.encrypted_lookup.decrypt_user_doc", new_callable=AsyncMock) as mock_decrypt:
        # Vendor token doesn't even hit decrypt_user_doc because it lacks type=access or user_id
        response = client.get("/api/uploads/vendors/vendor_A/products/real_test.jpg", headers=headers)
        assert response.status_code == 200
        assert response.text == "dummy image content"
    
def test_real_auth_invalid_token(temp_vendor_file):
    headers = {"Authorization": "Bearer invalid_token"}
    response = client.get("/api/uploads/vendors/vendor_A/products/real_test.jpg", headers=headers)
    assert response.status_code == 401

@patch("routers.uploads.db")
def test_visibility_user_access_private_file(mock_db):
    token = create_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    upload_id = str(uuid.uuid4())
    mock_db.uploads.find_one = AsyncMock(return_value={
        "_id": upload_id,
        "owner_type": "vendor",
        "vendor_id": "vendor_A",
        "visibility": "vendor_private",
        "relative_path": "vendors/vendor_A/products/private.jpg"
    })
    
    with patch("core.security._user_doc_cache_get") as mock_cache:
        mock_cache.return_value = {"_id": "user123", "tenant_id": "hotel_A", "email": "hotel@test.com", "name": "Hotel User", "role": "admin", "is_active": True, "failed_login_attempts": 0}
        with patch("infra.auth_cache_pubsub.auth_cache_pubsub"):
            response = client.get(f"/api/uploads/{upload_id}", headers=headers)
            assert response.status_code == 403
            assert "not public" in response.json()["detail"]

def test_vendor_path_traversal():
    token = create_vendor_token("vendor_A")
    headers = {"Authorization": f"Bearer {token}"}
    
    # URL encoded traversal %2F..%2F..%2F..%2Fetc%2Fpasswd
    response = client.get("/api/uploads/vendors/vendor_A%2F..%2F..%2F..%2Fetc%2Fpasswd", headers=headers)
    assert response.status_code in (400, 403, 404)

@patch("routers.uploads.db")
def test_legacy_path_audit_log(mock_db, temp_vendor_file):
    token = create_vendor_token("vendor_A")
    headers = {"Authorization": f"Bearer {token}"}
    
    mock_db.audit_logs.insert_one = AsyncMock()
    
    response = client.get("/api/uploads/vendors/vendor_B/products/real_test.jpg", headers=headers)
    assert response.status_code == 403
    
    mock_db.audit_logs.insert_one.assert_called_once()
    call_args = mock_db.audit_logs.insert_one.call_args[0][0]
    assert call_args["action"] == "unauthorized_vendor_file_access"
    assert call_args["vendor_id"] == "vendor_A"
    assert call_args["target_vendor_id"] == "vendor_B"
