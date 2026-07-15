import pytest
import os
os.environ["ENTITLEMENT_ENFORCEMENT_MODE"] = "enforce"

from unittest.mock import AsyncMock, patch, MagicMock
import uuid
from datetime import datetime, UTC

import sys
sys.path.append("backend")

import app as myapp
myapp._startup_callbacks = []
myapp._shutdown_callbacks = []

from fastapi.testclient import TestClient
from server import app
client = TestClient(app, raise_server_exceptions=False)

from models.schemas import User, UserRole
from core.entitlements.quota import QuotaExceededException
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op

def mock_get_current_user_basic():
    return User(id="user123", tenant_id="tenant_mice_basic", role=UserRole.ADMIN, name="Test", email="test@test.com", password_hash="123", active=True, created_at=datetime.now(UTC).isoformat(), updated_at=datetime.now(UTC).isoformat())

def mock_get_current_user_pro():
    return User(id="user456", tenant_id="tenant_mice_pro", role=UserRole.ADMIN, name="Test", email="test@test.com", password_hash="123", active=True, created_at=datetime.now(UTC).isoformat(), updated_at=datetime.now(UTC).isoformat())

def mock_require_op():
    return True

class FakeCursor:
    async def to_list(self, *args, **kwargs):
        return []

@pytest.fixture
def mock_db():
    with patch("routers.mice.get_system_db") as mock, patch("routers.sales_catering.db") as mock_sc:
        db = MagicMock()
        
        # We need MagicMock for synchronous find() which returns a cursor
        db.mice_spaces = MagicMock()
        db.mice_events = MagicMock()
        
        db.mice_spaces.insert_one = AsyncMock()
        db.mice_spaces.find_one = AsyncMock()
        db.mice_spaces.update_one = AsyncMock()
        db.mice_spaces.delete_one = AsyncMock()
        
        db.mice_events.insert_one = AsyncMock()
        db.mice_events.find_one = AsyncMock()
        db.mice_events.update_one = AsyncMock()
        db.mice_events.delete_one = AsyncMock()
        
        db.mice_spaces.find.return_value = FakeCursor()
        db.mice_events.find.return_value = FakeCursor()
        
        mock.return_value = db
        mock_sc.return_value = db
        yield db

@pytest.fixture
def override_auth_basic():
    app.dependency_overrides[get_current_user] = mock_get_current_user_basic
    app.dependency_overrides[require_op("manage_sales")] = mock_require_op
    yield
    app.dependency_overrides = {}

@pytest.fixture
def override_auth_pro():
    app.dependency_overrides[get_current_user] = mock_get_current_user_pro
    app.dependency_overrides[require_op("manage_sales")] = mock_require_op
    yield
    app.dependency_overrides = {}

@pytest.fixture
def mock_get_tenant_limit():
    with patch("routers.mice.get_tenant_limit") as m:
        async def fake_limit(tenant_id, module, metric):
            if tenant_id == "tenant_mice_basic":
                if metric == "spaces_limit": return 2
                if metric == "concurrent_events": return 5
            if tenant_id == "tenant_mice_pro":
                if metric == "spaces_limit": return 10
                if metric == "concurrent_events": return 50
            return None
        m.side_effect = fake_limit
        yield m

@pytest.fixture
def mock_feature():
    with patch("core.entitlements.enforcement.tenant_has_feature") as m:
        async def fake_check(tenant_id, module, feature):
            if tenant_id == "tenant_mice_basic": return False
            if tenant_id == "tenant_mice_pro": return True
            return False
        m.side_effect = fake_check
        yield m

@pytest.fixture
def mock_quota():
    with patch("routers.mice.reserve_quota") as m_res, \
         patch("routers.mice.release_quota") as m_rel:
        yield m_res, m_rel


def test_basic_spaces_limit(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    # First insert is ok
    res = client.post("/api/mice/spaces", json={"name": "Space 1", "area_m2": 100})
    assert res.status_code == 200
    
    # Third should fail because we mock the reserve to throw QuotaExceededException for 3rd time
    # Actually wait, our router doesn't check the current count, `reserve_quota` does that.
    # So we need to make `reserve_quota` throw on 3rd call.
    call_count = [0]
    async def fake_reserve(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 2:
            raise QuotaExceededException("Limit aşıldı")
    m_res.side_effect = fake_reserve

    # reset count
    call_count[0] = 0
    client.post("/api/mice/spaces", json={"name": "Space 1", "area_m2": 100})
    client.post("/api/mice/spaces", json={"name": "Space 2", "area_m2": 100})
    res = client.post("/api/mice/spaces", json={"name": "Space 3", "area_m2": 100})
    assert res.status_code == 403

def test_pro_spaces_limit(override_auth_pro, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    call_count = [0]
    async def fake_reserve(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 10:
            raise QuotaExceededException("Limit aşıldı")
    m_res.side_effect = fake_reserve

    for i in range(10):
        client.post("/api/mice/spaces", json={"name": f"Space {i}", "area_m2": 100})
        
    res = client.post("/api/mice/spaces", json={"name": "Space 11", "area_m2": 100})
    assert res.status_code == 403

def test_basic_events_limit(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    call_count = [0]
    async def fake_reserve(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 5:
            raise QuotaExceededException("Limit aşıldı")
    m_res.side_effect = fake_reserve

    # Mock with_resource_locks
    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(callback, **kwargs):
            return await callback(session=None)
        m_lock.side_effect = fake_lock

        for i in range(5):
            client.post("/api/mice/events", json={"name": f"Ev {i}", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
            
        res = client.post("/api/mice/events", json={"name": "Ev 6", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
        assert res.status_code == 403

def test_pro_events_limit(override_auth_pro, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    call_count = [0]
    async def fake_reserve(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] > 50:
            raise QuotaExceededException("Limit aşıldı")
    m_res.side_effect = fake_reserve

    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(callback, **kwargs):
            return await callback(session=None)
        m_lock.side_effect = fake_lock

        for i in range(50):
            client.post("/api/mice/events", json={"name": f"Ev {i}", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
            
        res = client.post("/api/mice/events", json={"name": "Ev 51", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
        assert res.status_code == 403

def test_space_idempotency(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    from pymongo.errors import DuplicateKeyError
    m_res, m_rel = mock_quota
    
    req_id = str(uuid.uuid4())
    mock_db.mice_spaces.insert_one.side_effect = DuplicateKeyError("dup")
    async def fake_find_one(query, *args, **kwargs):
        if "client_request_id" in query:
            return {"id": "space123", "client_request_id": req_id}
        return None
    mock_db.mice_spaces.find_one.side_effect = fake_find_one

    res = client.post("/api/mice/spaces", json={"name": "Idem", "area_m2": 100, "client_request_id": req_id})
    assert res.status_code == 200
    assert res.json()["id"] == "space123"
    
    # Should not call release_quota because it was an idempotent success
    m_rel.assert_not_called()

def test_space_insert_failure_rollback(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    mock_db.mice_spaces.insert_one.side_effect = Exception("DB error")
    
    res = client.post("/api/mice/spaces", json={"name": "Fail", "area_m2": 100})
    assert res.status_code == 500
    
    m_rel.assert_called_once()

def test_event_insert_failure_rollback(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(callback, **kwargs):
            raise Exception("DB lock error")
        m_lock.side_effect = fake_lock

        res = client.post("/api/mice/events", json={"name": "Fail", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
        assert res.status_code == 500
        
        m_rel.assert_called_once()

def test_event_cancel_completed_release(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    # Test delete
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "tentative"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.delete_one.return_value.deleted_count = 1

    res = client.delete("/api/mice/events/ev123")
    assert res.status_code == 200
    m_rel.assert_called_once()

    m_rel.reset_mock()
    # Test status change to cancelled
    mock_db.mice_events.update_one.return_value.modified_count = 1
    res = client.post("/api/mice/events/ev123/status", json={"status": "cancelled"})
    assert res.status_code == 200
    m_rel.assert_called_once()

def test_event_same_status_no_double_release(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "cancelled"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    
    mock_db.mice_events.update_one.return_value.modified_count = 1
    res = client.post("/api/mice/events/ev123/status", json={"status": "cancelled"})
    assert res.status_code == 200
    m_rel.assert_not_called()

def test_event_reactivate_reserve(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "cancelled"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one.return_value.modified_count = 1
    
    res = client.post("/api/mice/events/ev123/status", json={"status": "tentative"})
    assert res.status_code == 200
    m_res.assert_called_once()
    m_rel.assert_not_called()

def test_event_reactivate_reserve_fail_rollback(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "cancelled"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one.return_value.modified_count = 1
    
    m_res.side_effect = QuotaExceededException("Limit aşıldı")
    
    res = client.post("/api/mice/events/ev123/status", json={"status": "tentative"})
    assert res.status_code == 403
    # Check if rollback update was called (second update_one call)
    assert mock_db.mice_events.update_one.call_count == 2

def test_feature_guards_sales_pipeline_basic(override_auth_basic, mock_feature):
    res = client.get("/api/sales/pipeline")
    assert res.status_code == 403

def test_feature_guards_sales_pipeline_pro(override_auth_pro, mock_feature):
    res = client.get("/api/sales/pipeline")
    # Pipeline returns 200 or 500 but NOT 403
    assert res.status_code != 403

def test_feature_guards_beo_basic(override_auth_basic, mock_feature, mock_db):
    res = client.get("/api/mice/events/ev123/beo")
    assert res.status_code == 403

def test_feature_guards_beo_pro(override_auth_pro, mock_feature, mock_db):
    mock_db.mice_events.find_one.return_value = None
    res = client.get("/api/mice/events/ev123/beo")
    assert res.status_code != 403

