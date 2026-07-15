from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.security import get_current_user
from server import app

client = TestClient(app, raise_server_exceptions=True)

class FakeCursor:
    def __init__(self, items):
        self.items = items
    def __aiter__(self):
        self.idx = 0
        return self
    async def __anext__(self):
        import asyncio
        await asyncio.sleep(0)
        if self.idx < len(self.items):
            val = self.items[self.idx]
            self.idx += 1
            return val
        raise StopAsyncIteration
    async def to_list(self, length=None):
        return self.items

@pytest.fixture
def mock_db():
    with patch("routers.housekeeping.db") as m_db, \
         patch("core.entitlements.quota.db", create=True) as m_quota_db:

        db = MagicMock()
        db.rooms.find_one = AsyncMock(return_value={"id": "room_1", "tenant_id": "tenant_1"})
        db.housekeeping_tasks.find_one = AsyncMock(return_value={"id": "task_1", "task_type": "cleaning", "status": "pending"})
        db.housekeeping_tasks.insert_one = AsyncMock()
        db.housekeeping_tasks.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        db.housekeeping_tasks.update_one = AsyncMock()
        db.housekeeping_tasks.find = MagicMock(return_value=FakeCursor([]))
        db.users.find_one = AsyncMock(return_value={"id": "user_1", "name": "Test User", "is_active": True})

        m_db.rooms = db.rooms
        m_db.housekeeping_tasks = db.housekeeping_tasks
        m_db.users = db.users
        m_quota_db.tenant_quotas = MagicMock()
        m_quota_db.tenant_quotas.find_one = AsyncMock(return_value=None)
        m_quota_db.tenant_quotas.update_one = AsyncMock()

        yield db

@pytest.fixture
def override_auth():
    def get_test_user():
        from models.schemas import User
        return User(id="user_1", tenant_id="tenant_1", name="Test User", role="admin", email="test@test.com")

    app.dependency_overrides[get_current_user] = get_test_user
    yield
    app.dependency_overrides.pop(get_current_user, None)

@pytest.fixture
def mock_require_module():
    with patch("routers.housekeeping.require_module_v99") as m_mod, \
         patch("routers.housekeeping.require_op") as m_op:
        def fake_dep(mod):
            async def dep(): return True
            return dep
        m_mod.side_effect = fake_dep
        m_op.side_effect = fake_dep
        yield m_mod

# --- TESTS ---

def test_housekeeping_create_task_basic(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        m_limit.return_value = 100
        m_res.return_value = {"status": "success"}

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload)
        assert res.status_code == 200

def test_housekeeping_create_inspection_task_basic(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("routers.housekeeping.require_feature") as m_feat:

        # When require_feature is called, it returns a dependency function
        # We need that dependency function to raise an HTTPException
        async def fake_dependency(request, user):
            raise HTTPException(status_code=403, detail="housekeeping: quality_control")

        m_feat.return_value = fake_dependency

        payload = {"room_id": "room_1", "task_type": "inspection"}
        res = client.post("/api/housekeeping/tasks", json=payload)
        assert res.status_code == 403
        assert "housekeeping: quality_control" in res.json()["detail"]

def test_housekeeping_create_inspection_task_pro(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("routers.housekeeping.require_feature") as m_feat:

        m_limit.return_value = 100

        async def fake_dependency(request, user):
            return True

        m_feat.return_value = fake_dependency

        payload = {"room_id": "room_1", "task_type": "inspection"}
        res = client.post("/api/housekeeping/tasks", json=payload)
        assert res.status_code == 200

def test_housekeeping_quota_limit(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        m_limit.return_value = 100
        m_res.side_effect = HTTPException(status_code=403, detail="Kota limiti asildi")

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload)
        assert res.status_code == 403
        assert "Kota limiti" in res.json()["detail"]

def test_housekeeping_staff_performance_basic(mock_db, override_auth, mock_require_module):
    # For GET requests with Depends(), we can mock the actual dependency in app.dependency_overrides
    # But since it's a dynamic dependency `require_feature("housekeeping", "advanced_reporting")`
    # it's easier to mock `core.entitlements.enforcement.tenant_has_feature` because `require_feature` evaluates it at request time.
    with patch("core.entitlements.enforcement.tenant_has_feature", new_callable=AsyncMock) as m_feat, \
         patch.dict("os.environ", {"ENTITLEMENT_ENFORCEMENT_MODE": "strict"}):
        m_feat.return_value = False

        res = client.get("/api/housekeeping/staff-performance-detailed")
        assert res.status_code == 403

def test_housekeeping_staff_performance_pro(mock_db, override_auth, mock_require_module):
    with patch("core.entitlements.enforcement.tenant_has_feature", new_callable=AsyncMock) as m_feat:
        m_feat.return_value = True

        res = client.get("/api/housekeeping/staff-performance-detailed")
        assert res.status_code == 200
