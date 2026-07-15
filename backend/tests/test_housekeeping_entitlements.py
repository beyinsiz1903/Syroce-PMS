from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from core.security import get_current_user
from server import app
from core.entitlements.quota import QuotaExceededException

client = TestClient(app, raise_server_exceptions=False)

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
    with patch("routers.housekeeping.db") as m_db:

        db = MagicMock()
        db.rooms.find_one = AsyncMock(return_value={"id": "room_1", "tenant_id": "tenant_1"})
        db.housekeeping_tasks.find_one = AsyncMock(return_value={"id": "task_1", "task_type": "cleaning", "status": "pending"})
        db.housekeeping_tasks.insert_one = AsyncMock()
        db.housekeeping_tasks.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        db.housekeeping_tasks.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        db.housekeeping_tasks.find = MagicMock(return_value=FakeCursor([]))
        db.users.find_one = AsyncMock(return_value={"id": "user_1", "name": "Test User", "is_active": True})

        m_db.rooms = db.rooms
        m_db.housekeeping_tasks = db.housekeeping_tasks
        m_db.users = db.users

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
    with patch("routers.housekeeping.require_module_v99") as m_mod,          patch("routers.housekeeping.require_op") as m_op:
        def fake_dep(mod):
            async def dep(): return True
            return dep
        m_mod.side_effect = fake_dep
        m_op.side_effect = fake_dep
        yield m_mod


# --- TESTS ---

def test_hk_create_quota_exceeded(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        m_limit.return_value = 100
        m_res.side_effect = QuotaExceededException("Kota limiti asildi")

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload)
        assert res.status_code == 403
        assert "Kota limiti asildi" in res.json()["detail"]


def test_hk_create_room_not_found_rollback(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        m_limit.return_value = 100
        mock_db.rooms.find_one.return_value = None

        payload = {"room_id": "room_bad", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload)

        assert res.status_code == 404
        m_res.assert_called_once()
        m_rel.assert_called_once()


def test_hk_create_insert_failure_rollback(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        m_limit.return_value = 100
        mock_db.housekeeping_tasks.insert_one.side_effect = Exception("DB Error")

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload)

        assert res.status_code == 500
        m_res.assert_called_once()
        m_rel.assert_called_once()


def test_hk_create_idempotency_replay(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.claim_idempotency", new_callable=AsyncMock) as m_claim,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        m_claim.return_value = {"status": "replay", "response": {"success": True}}

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload, headers={"Idempotency-Key": "testkey"})

        assert res.status_code == 200
        m_res.assert_not_called()


def test_hk_create_idempotency_in_flight(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.claim_idempotency", new_callable=AsyncMock) as m_claim,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        m_claim.return_value = {"status": "in_flight"}

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload, headers={"Idempotency-Key": "testkey"})

        assert res.status_code == 409
        m_res.assert_not_called()


def test_hk_update_pending_to_completed_release_once(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "pending", "tenant_id": "tenant_1"}

        res = client.put("/api/housekeeping/tasks/task_1", params={"status": "completed"})
        assert res.status_code == 200
        m_res.assert_not_called()
        m_rel.assert_called_once()


def test_hk_update_in_progress_to_completed_release_once(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "in_progress", "tenant_id": "tenant_1"}

        res = client.put("/api/housekeeping/tasks/task_1", params={"status": "completed"})
        assert res.status_code == 200
        m_res.assert_not_called()
        m_rel.assert_called_once()


def test_hk_update_completed_to_pending_reserve_once(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        m_limit.return_value = 100
        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "completed", "tenant_id": "tenant_1"}

        res = client.put("/api/housekeeping/tasks/task_1", params={"status": "pending"})
        assert res.status_code == 200
        m_res.assert_called_once()
        m_rel.assert_not_called()


def test_hk_update_reactivation_db_failure_rollback(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        m_limit.return_value = 100
        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "completed", "tenant_id": "tenant_1"}
        mock_db.housekeeping_tasks.update_one.side_effect = Exception("DB error")

        res = client.put("/api/housekeeping/tasks/task_1", params={"status": "pending"})
        assert res.status_code == 500
        m_res.assert_called_once()
        m_rel.assert_called_once()


def test_hk_update_pending_to_in_progress_no_quota_changes(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "pending", "tenant_id": "tenant_1"}

        res = client.put("/api/housekeeping/tasks/task_1", params={"status": "in_progress"})
        assert res.status_code == 200
        m_res.assert_not_called()
        m_rel.assert_not_called()


def test_hk_update_completed_to_completed_no_double_release(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res,          patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "completed", "tenant_id": "tenant_1"}

        res = client.put("/api/housekeeping/tasks/task_1", params={"status": "completed"})
        assert res.status_code == 200
        m_res.assert_not_called()
        m_rel.assert_not_called()


def test_hk_delete_pending_release_once(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:
        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "pending", "tenant_id": "tenant_1"}
        mock_db.housekeeping_tasks.delete_one.return_value = MagicMock(deleted_count=1)

        res = client.delete("/api/housekeeping/tasks/task_1")
        assert res.status_code == 200
        m_rel.assert_called_once()


def test_hk_delete_completed_release_not_called(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:
        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "completed", "tenant_id": "tenant_1"}
        mock_db.housekeeping_tasks.delete_one.return_value = MagicMock(deleted_count=1)

        res = client.delete("/api/housekeeping/tasks/task_1")
        assert res.status_code == 200
        m_rel.assert_not_called()


def test_hk_delete_in_progress_409_release_not_called(mock_db, override_auth, mock_require_module):
    with patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:
        mock_db.housekeeping_tasks.find_one.return_value = {"id": "task_1", "status": "in_progress", "tenant_id": "tenant_1"}
        mock_db.housekeeping_tasks.delete_one.return_value = MagicMock(deleted_count=0)

        res = client.delete("/api/housekeeping/tasks/task_1")
        assert res.status_code == 409
        m_rel.assert_not_called()


def test_hk_tenant_isolation(mock_db, override_auth, mock_require_module):
    # Just verify that find_one is called with tenant_id="tenant_1"
    res = client.delete("/api/housekeeping/tasks/task_1")
    mock_db.housekeeping_tasks.find_one.assert_any_call({"id": "task_1", "tenant_id": "tenant_1"})

def test_hk_create_concurrent_same_idempotency_key(mock_db, override_auth, mock_require_module):
    # This is basically the same as in-flight
    with patch("routers.housekeeping.claim_idempotency", new_callable=AsyncMock) as m_claim,          patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        m_claim.return_value = {"status": "in_flight"}

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload, headers={"Idempotency-Key": "concurrentkey"})

        assert res.status_code == 409
        m_res.assert_not_called()
