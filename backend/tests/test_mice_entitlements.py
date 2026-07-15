import pytest
import uuid
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from server import app
from core.security import get_current_user
from core.entitlements.quota import QuotaExceededException
from core.tenant_db import get_system_db
from models.schemas.identity import User

client = TestClient(app, raise_server_exceptions=False)

class FakeCursor:
    def __aiter__(self):
        self.idx = 0
        return self
    async def __anext__(self):
        if self.idx < len(self.items):
            val = self.items[self.idx]
            self.idx += 1
            return val
        raise StopAsyncIteration
    def __init__(self, items):
        self.items = items
    async def to_list(self, length=None):
        return self.items

@pytest.fixture
def mock_db():
    with patch("routers.mice.get_system_db") as m_db, patch("core.tenant_db.get_system_db") as m_db_tenant, patch("core.database.db") as m_db_default:
        db = MagicMock()
        db.mice_spaces.find_one = AsyncMock(return_value=None)
        db.mice_spaces.insert_one = AsyncMock()
        db.mice_spaces.find.return_value = FakeCursor([])
        
        db.mice_events.find_one = AsyncMock(return_value=None)
        db.mice_events.insert_one = AsyncMock()
        db.mice_events.update_one = AsyncMock()
        db.mice_events.delete_one = AsyncMock()
        db.mice_events.find.return_value = FakeCursor([])
        db.audit_logs.insert_one = AsyncMock()
        
        db.tenant_features.find_one = AsyncMock(return_value=None)
        
        m_db.return_value = db
        m_db_tenant.return_value = db
        m_db_default.audit_logs.insert_one = AsyncMock()
        db.audit_logs.find_one = AsyncMock(return_value=None)
        yield db

@pytest.fixture
def mock_get_tenant_limit():
    with patch("routers.mice.get_tenant_limit") as m_limit:
        m_limit.return_value = 5  # arbitrary
        yield m_limit

@pytest.fixture
def mock_quota():
    with patch("routers.mice.reserve_quota") as m_res, \
         patch("routers.mice.release_quota") as m_rel:
        yield m_res, m_rel

@pytest.fixture
def override_auth_basic():
    async def override():
        return User(
            id="usr1",
            username="testuser",
            tenant_id="t1",
            roles=[],
            email="test@test.com",
            name="Test User",
            role="admin",
            subscription_tier="basic",
            is_active=True,
            created_at="2026-01-01"
        )
    app.dependency_overrides[get_current_user] = override
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture
def override_auth_pro():
    async def override():
        return User(
            id="usr2",
            username="testuser",
            tenant_id="t1",
            roles=[],
            email="test@test.com",
            name="Test User",
            role="admin",
            subscription_tier="pro",
            is_active=True,
            created_at="2026-01-01"
        )
    app.dependency_overrides[get_current_user] = override
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture
def mock_feature():
    with patch("core.entitlements.enforcement.tenant_has_feature", new_callable=AsyncMock) as m:
        async def fake_has_feature(tenant_id, feature):
            return True if "pro" in tenant_id else False
        m.side_effect = fake_has_feature
        yield m

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

def test_event_insert_failure_rollback(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(callback, **kwargs):
            raise Exception("DB lock error")
        m_lock.side_effect = fake_lock

        res = client.post("/api/mice/events", json={"name": "Fail", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
        assert res.status_code == 500
        
        m_rel.assert_called_once()

# NEW QUOTA TESTS

def test_event_status_counted_to_uncounted_release(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    # from 'confirmed' to 'completed'
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "confirmed"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one.return_value.modified_count = 1
    
    res = client.post("/api/mice/events/ev123/status", json={"status": "completed"})
    assert res.status_code == 200
    m_rel.assert_called_once()
    m_res.assert_not_called()

def test_event_status_counted_to_uncounted_cancelled_release(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    # from 'tentative' to 'cancelled'
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "tentative"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one.return_value.modified_count = 1
    
    res = client.post("/api/mice/events/ev123/status", json={"status": "lead", "reason": "Cok pahali buldular iptal ettik"})
    assert res.status_code == 200
    m_rel.assert_called_once()

def test_event_status_uncounted_to_counted_reserve(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    # from 'cancelled' to 'lead'
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "lead"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    mock_db.mice_events.update_one.return_value.modified_count = 1
    
    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(callback, **kwargs):
            return await callback(session=None)
        m_lock.side_effect = fake_lock
        
        res = client.post("/api/mice/events/ev123/status", json={"status": "tentative"})
    assert res.status_code == 200
    m_res.assert_called_once()
    m_rel.assert_not_called()

def test_event_status_uncounted_to_counted_db_failure_rollback(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    # from 'cancelled' to 'tentative'
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "lead"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    
    # Simulate DB update failure (Exception inside with_resource_locks)
    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(callback, **kwargs):
            raise Exception("DB update error")
        m_lock.side_effect = fake_lock
    
        res = client.post("/api/mice/events/ev123/status", json={"status": "tentative"})
        assert res.status_code == 500
        # reserve was called, so release must be called in rollback
        m_res.assert_called_once()
        m_rel.assert_called_once()

def test_event_status_counted_to_counted_no_double_consume(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota
    
    # from 'tentative' to 'definite'
    async def fake_find_one(query, *args, **kwargs):
        return {"id": "ev123", "status": "tentative"}
    mock_db.mice_events.find_one.side_effect = fake_find_one
    
    with patch("routers.mice.with_resource_locks") as m_lock:
        async def fake_lock(callback, **kwargs):
            return await callback(session=None)
        m_lock.side_effect = fake_lock
        
        res = client.post("/api/mice/events/ev123/status", json={"status": "definite"})
        assert res.status_code == 200
        m_res.assert_not_called()
        m_rel.assert_not_called()

# FALLBACK TESTS

def test_event_fallback_success_keeps_quota_reserved(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    with patch("routers.mice.with_resource_locks") as m_lock, \
         patch("routers.mice.is_replica_set_unavailable") as m_is_rep, \
         patch("routers.mice.standalone_fallback_allowed") as m_fallback:
        
        m_lock.side_effect = Exception("Tx error")
        m_is_rep.return_value = True
        m_fallback.return_value = True
        
        # fallback succeeds!
        mock_db.mice_events.insert_one = AsyncMock()

        res = client.post("/api/mice/events", json={"name": "Fallback", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
        assert res.status_code == 200
        m_res.assert_called_once()
        # Should NOT release quota because the fallback succeeded!
        m_rel.assert_not_called()

def test_event_fallback_failure_rollbacks_quota(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    m_res, m_rel = mock_quota

    with patch("routers.mice.with_resource_locks") as m_lock, \
         patch("routers.mice.is_replica_set_unavailable") as m_is_rep, \
         patch("routers.mice.standalone_fallback_allowed") as m_fallback:
        
        m_lock.side_effect = Exception("Tx error")
        m_is_rep.return_value = True
        m_fallback.return_value = True
        
        # fallback fails!
        mock_db.mice_events.insert_one.side_effect = Exception("Fallback insert error")

        res = client.post("/api/mice/events", json={"name": "FallbackFail", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative"})
        assert res.status_code == 500
        m_res.assert_called_once()
        # SHOULD release quota because both tx and fallback failed
        m_rel.assert_called_once()

def test_event_fallback_duplicate_idempotent_keeps_quota(override_auth_basic, mock_db, mock_get_tenant_limit, mock_quota):
    from pymongo.errors import DuplicateKeyError
    m_res, m_rel = mock_quota
    req_id = str(uuid.uuid4())

    with patch("routers.mice.with_resource_locks") as m_lock, \
         patch("routers.mice.is_replica_set_unavailable") as m_is_rep, \
         patch("routers.mice.standalone_fallback_allowed") as m_fallback:
        
        m_lock.side_effect = Exception("Tx error")
        m_is_rep.return_value = True
        m_fallback.return_value = True
        
        # fallback hits duplicate key!
        mock_db.mice_events.insert_one.side_effect = DuplicateKeyError("dup")
        async def fake_find_one(query, *args, **kwargs):
            if "client_request_id" in query:
                return {"id": "ev999", "client_request_id": req_id}
            return None
        mock_db.mice_events.find_one.side_effect = fake_find_one

        res = client.post("/api/mice/events", json={"name": "FallbackDup", "client_name": "Test", "start_date": "2026-08-01", "end_date": "2026-08-02", "status": "tentative", "client_request_id": req_id})
        assert res.status_code == 200
        m_res.assert_called_once()
        # Should NOT release quota because we successfully fetched the existing record
        m_rel.assert_not_called()

