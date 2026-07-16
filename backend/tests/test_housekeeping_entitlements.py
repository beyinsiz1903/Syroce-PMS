from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.entitlements.quota import QuotaExceededException
from core.security import get_current_user
from server import app

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
    client.delete("/api/housekeeping/tasks/task_1")
    mock_db.housekeeping_tasks.find_one.assert_any_call({"id": "task_1", "tenant_id": "tenant_1"})

def test_hk_create_concurrent_same_idempotency_key(mock_db, override_auth, mock_require_module):
    # This is basically the same as in-flight
    with patch("routers.housekeeping.claim_idempotency", new_callable=AsyncMock) as m_claim, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        m_claim.return_value = {"status": "in_flight"}

        payload = {"room_id": "room_1", "task_type": "cleaning"}
        res = client.post("/api/housekeeping/tasks", json=payload, headers={"Idempotency-Key": "concurrentkey"})

        assert res.status_code == 409
        m_res.assert_not_called()


# ── /housekeeping/assign — quota + idempotency tests ──────────────────────────


def test_assign_reserves_active_task_quota(mock_db, override_auth, mock_require_module):
    """/assign yeni aktif task oluşturduğu için insert öncesi reserve_quota çağrılmalı."""
    with patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib, \
         patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        mock_guard = MagicMock()
        mock_guard.complete = AsyncMock()
        mock_guard.release = AsyncMock()
        m_ib.return_value = (mock_guard, None)
        m_limit.return_value = 10
        mock_db.rooms.find_one.return_value = {"id": "room_1", "tenant_id": "tenant_1", "room_number": "101"}

        res = client.post("/api/housekeeping/assign", params={"room_id": "room_1", "assigned_to": "staff_1"})

        assert res.status_code == 200
        m_res.assert_called_once()
        args = m_res.call_args[0]
        assert args[0] == "tenant_1"
        assert args[1] == "housekeeping"
        assert args[2] == "active_tasks"


def test_assign_quota_exceeded_returns_403(mock_db, override_auth, mock_require_module):
    """/assign kota doluysa 403 dönmeli ve insert çağrılmamalı."""
    with patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib, \
         patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        mock_guard = MagicMock()
        mock_guard.complete = AsyncMock()
        mock_guard.release = AsyncMock()
        m_ib.return_value = (mock_guard, None)
        m_limit.return_value = 5
        m_res.side_effect = QuotaExceededException("Aktif görev kotası doldu")
        mock_db.rooms.find_one.return_value = {"id": "room_1", "tenant_id": "tenant_1", "room_number": "101"}

        res = client.post("/api/housekeeping/assign", params={"room_id": "room_1", "assigned_to": "staff_1"})

        assert res.status_code == 403
        mock_db.housekeeping_tasks.insert_one.assert_not_called()
        mock_guard.release.assert_called_once()


def test_assign_insert_failure_rolls_back_quota(mock_db, override_auth, mock_require_module):
    """Insert başarısız olursa quota rollback yapılmalı."""
    with patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib, \
         patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        mock_guard = MagicMock()
        mock_guard.complete = AsyncMock()
        mock_guard.release = AsyncMock()
        m_ib.return_value = (mock_guard, None)
        m_limit.return_value = 10
        mock_db.rooms.find_one.return_value = {"id": "room_1", "tenant_id": "tenant_1", "room_number": "101"}
        mock_db.housekeeping_tasks.insert_one.side_effect = Exception("DB Error")

        res = client.post("/api/housekeeping/assign", params={"room_id": "room_1", "assigned_to": "staff_1"})

        assert res.status_code == 500
        m_res.assert_called_once()
        m_rel.assert_called_once()


def test_assign_idempotency_replay_no_double_reserve(mock_db, override_auth, mock_require_module):
    """Idempotency replay: aynı anahtar tekrar geldiğinde quota reserve edilmemeli."""
    with patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        cached = {"message": "Task assigned to staff_1", "task": {"id": "task_1"}}
        mock_guard = MagicMock()
        mock_guard.complete = AsyncMock()
        mock_guard.release = AsyncMock()
        # Replay: begin_idempotency döner (guard, cached_response)
        m_ib.return_value = (mock_guard, cached)
        mock_db.rooms.find_one.return_value = {"id": "room_1", "tenant_id": "tenant_1", "room_number": "101"}

        res = client.post("/api/housekeeping/assign",
                          params={"room_id": "room_1", "assigned_to": "staff_1"},
                          headers={"Idempotency-Key": "key-abc"})

        # Replay yanıtı cached dict'tir; quota ve insert atlanmalı
        assert res.status_code == 200
        m_res.assert_not_called()
        mock_db.housekeeping_tasks.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_assign_idempotency_in_flight_returns_409():
    """Aynı Idempotency-Key ile in-flight istek varsa 409 dönmeli."""
    from fastapi import HTTPException as _HTTPException

    from routers.housekeeping import assign_housekeeping_task

    with patch("routers.housekeeping.db") as m_db, \
         patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib:

        m_db.rooms.find_one = AsyncMock(return_value={"id": "room_1", "tenant_id": "t1", "room_number": "101"})
        m_ib.side_effect = _HTTPException(status_code=409, detail="In flight")

        request = MagicMock()
        request.headers = {}

        class _User:
            tenant_id = "t1"
            id = "u1"
            role = "admin"

        with pytest.raises(_HTTPException) as exc:
            await assign_housekeeping_task(
                request=request,
                room_id="room_1",
                assigned_to="staff_1",
                current_user=_User(),
                _perm=None,
            )
        assert exc.value.status_code == 409


def test_assign_tenant_isolation(mock_db, override_auth, mock_require_module):
    """/assign room lookup tenant_id ile scope'lanmış olmalı."""
    with patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib, \
         patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock):

        mock_guard = MagicMock()
        mock_guard.complete = AsyncMock()
        mock_guard.release = AsyncMock()
        m_ib.return_value = (mock_guard, None)
        m_limit.return_value = 10
        # Simüle: farklı tenant'ın odası bulunamıyor
        mock_db.rooms.find_one.return_value = None

        res = client.post("/api/housekeeping/assign", params={"room_id": "other_room", "assigned_to": "staff_1"})

        assert res.status_code == 404
        mock_db.rooms.find_one.assert_called_once_with({"id": "other_room", "tenant_id": "tenant_1"})

def test_assign_insert_failure_releases_idempotency_lock(mock_db, override_auth, mock_require_module):
    """Insert hatası hem quota hem idempotency guard.release()'i tetiklemeli."""
    with patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib, \
         patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res, \
         patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:

        mock_guard = MagicMock()
        mock_guard.complete = AsyncMock()
        mock_guard.release = AsyncMock()
        m_ib.return_value = (mock_guard, None)
        m_limit.return_value = 10
        mock_db.rooms.find_one.return_value = {"id": "room_1", "tenant_id": "tenant_1", "room_number": "101"}
        mock_db.housekeeping_tasks.insert_one.side_effect = Exception("DB write failed")

        res = client.post("/api/housekeeping/assign", params={"room_id": "room_1", "assigned_to": "staff_1"})

        assert res.status_code == 500
        # Quota must be rolled back
        m_res.assert_called_once()
        m_rel.assert_called_once()
        # Idempotency guard must be released (not completed) on error
        mock_guard.release.assert_called_once()
        mock_guard.complete.assert_not_called()


def test_assign_without_key_no_replay(mock_db, override_auth, mock_require_module):
    """Idempotency-Key header yoksa replay=None → her istek unique işlenir."""
    with patch("routers.housekeeping.begin_idempotency", new_callable=AsyncMock) as m_ib, \
         patch("routers.housekeeping.get_tenant_limit", new_callable=AsyncMock) as m_limit, \
         patch("routers.housekeeping.reserve_quota", new_callable=AsyncMock) as m_res:

        mock_guard = MagicMock()
        mock_guard.complete = AsyncMock()
        mock_guard.release = AsyncMock()
        m_ib.return_value = (mock_guard, None)  # No cached replay
        m_limit.return_value = 10
        mock_db.rooms.find_one.return_value = {"id": "room_1", "tenant_id": "tenant_1", "room_number": "101"}

        res = client.post("/api/housekeeping/assign", params={"room_id": "room_1", "assigned_to": "staff_1"})

        assert res.status_code == 200
        # Normal flow: reserve then complete
        m_res.assert_called_once()
        mock_guard.complete.assert_called_once()
        mock_guard.release.assert_not_called()


def test_complete_then_delete_no_double_release(mock_db, override_auth, mock_require_module):
    """Completed task silinince release_quota ÇAĞRILMAMALI (status geçişinde zaten serbest bırakıldı)."""
    with patch("routers.housekeeping.release_quota", new_callable=AsyncMock) as m_rel:
        mock_db.housekeeping_tasks.find_one.return_value = {
            "id": "task_completed",
            "tenant_id": "tenant_1",
            "status": "completed",
            "room_id": "room_1",
        }

        res = client.delete("/api/housekeeping/tasks/task_completed")

        assert res.status_code == 200
        m_rel.assert_not_called()
