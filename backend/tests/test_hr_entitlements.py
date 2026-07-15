
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
    return User(id="user123", tenant_id="tenant_hr_basic", role=UserRole.ADMIN, name="Test", email="test@test.com", password_hash="123", active=True, created_at=datetime.now(UTC).isoformat(), updated_at=datetime.now(UTC).isoformat())

def mock_get_current_user_pro():
    return User(id="user456", tenant_id="tenant_hr_pro", role=UserRole.ADMIN, name="Test", email="test@test.com", password_hash="123", active=True, created_at=datetime.now(UTC).isoformat(), updated_at=datetime.now(UTC).isoformat())

def mock_require_op():
    return True

@pytest.fixture
def mock_auth_basic():
    app.dependency_overrides[get_current_user] = mock_get_current_user_basic
    app.dependency_overrides[require_op("manage_hr")] = mock_require_op
    yield
    app.dependency_overrides = {}

@pytest.fixture
def mock_auth_pro():
    app.dependency_overrides[get_current_user] = mock_get_current_user_pro
    app.dependency_overrides[require_op("manage_hr")] = mock_require_op
    yield
    app.dependency_overrides = {}

class DummyCursor:
    def __init__(self, items):
        self.items = items
    def sort(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def skip(self, *args, **kwargs): return self
    async def to_list(self, length=None): return self.items

@pytest.fixture
def mock_router_db():
    mock_db = MagicMock()
    mock_db.staff_members.count_documents = AsyncMock(return_value=0)
    mock_db.staff_members.insert_one = AsyncMock()
    mock_db.staff_members.find_one = AsyncMock(return_value=None)

    mock_db.users.count_documents = AsyncMock(return_value=0)
    mock_db.job_postings.count_documents = AsyncMock(return_value=0)

    mock_update_result = MagicMock()
    mock_update_result.matched_count = 1
    mock_update_result.modified_count = 1
    mock_db.staff_members.update_one = AsyncMock(return_value=mock_update_result)
    mock_db.shift_schedules.update_one = AsyncMock(return_value=mock_update_result)

    mock_delete_result = MagicMock()
    mock_delete_result.deleted_count = 1
    mock_db.staff_members.delete_one = AsyncMock(return_value=mock_delete_result)

    mock_db.attendance_records.find.return_value = DummyCursor([])
    mock_db.staff_members.find.return_value = DummyCursor([])
    mock_db.job_postings.find.return_value = DummyCursor([])

    with patch("domains.hr.router.db", mock_db):
        yield mock_db

@pytest.fixture
def mock_active_editions_basic():
    with patch("core.entitlements.enforcement.get_tenant_active_editions", new_callable=AsyncMock) as m:
        m.return_value = ["basic"]
        yield m

@pytest.fixture
def mock_active_editions_pro():
    with patch("core.entitlements.enforcement.get_tenant_active_editions", new_callable=AsyncMock) as m:
        m.return_value = ["pro"]
        yield m

@pytest.fixture
def mock_entitlement_registry():
    from core.entitlements.registry import ENTITLEMENT_REGISTRY
    original = ENTITLEMENT_REGISTRY.copy()
    ENTITLEMENT_REGISTRY["hr"] = MagicMock(editions={
        "basic": MagicMock(features=["shift"], limits={"employees": 50}),
        "pro": MagicMock(features=["shift", "payroll", "leave", "recruitment"], limits={"employees": 200})
    })
    yield
    ENTITLEMENT_REGISTRY.clear()
    ENTITLEMENT_REGISTRY.update(original)

@pytest.fixture
def mock_quota():
    with patch("domains.hr.router.reserve_quota", new_callable=AsyncMock) as reserve_m:
        with patch("domains.hr.router.release_quota", new_callable=AsyncMock) as release_m:
            yield reserve_m, release_m

@pytest.mark.asyncio
async def test_hr_basic_permissions(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db):
    res = client.get("/api/hr/attendance/summary")
    assert res.status_code == 200

    res = client.get("/api/hr/payroll/2026-07")
    assert res.status_code == 403

    res = client.get("/api/hr/leave-requests")
    assert res.status_code == 403

    res = client.get("/api/hr/job-postings")
    assert res.status_code == 403

@pytest.mark.asyncio
async def test_hr_pro_permissions(mock_auth_pro, mock_active_editions_pro, mock_entitlement_registry, mock_router_db):
    res = client.get("/api/hr/attendance/summary")
    assert res.status_code == 200

    res = client.get("/api/hr/job-postings")
    assert res.status_code == 200

@pytest.mark.asyncio
async def test_hr_basic_quota_allowed(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    payload = {"name": "Allowed Employee"}
    with patch("domains.hr.router._audit", new_callable=AsyncMock):
        res = client.post("/api/hr/staff", json=payload)

    assert res.status_code == 200
    reserve_m.assert_called_once()
    assert reserve_m.call_args[0][0] == "tenant_hr_basic"
    assert reserve_m.call_args[0][4] == 50
    release_m.assert_not_called()

@pytest.mark.asyncio
async def test_hr_basic_quota_denied(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota
    reserve_m.side_effect = QuotaExceededException("Maksimum limit (50) asildi.")

    payload = {"name": "Denied Employee"}
    with patch("domains.hr.router._audit", new_callable=AsyncMock):
        res = client.post("/api/hr/staff", json=payload)

    assert res.status_code == 403
    assert "limit" in res.json()["detail"].lower()
    release_m.assert_not_called()

@pytest.mark.asyncio
async def test_hr_pro_quota_denied(mock_auth_pro, mock_active_editions_pro, mock_entitlement_registry, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota
    reserve_m.side_effect = QuotaExceededException("Maksimum limit (200) asildi.")

    payload = {"name": "Pro Denied"}
    with patch("domains.hr.router._audit", new_callable=AsyncMock):
        res = client.post("/api/hr/staff", json=payload)

    assert res.status_code == 403
    assert "200" in res.json()["detail"]

@pytest.mark.asyncio
async def test_hr_rollback_on_db_failure(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    mock_router_db.staff_members.insert_one.side_effect = Exception("DB Connection Error")

    payload = {"name": "Rollback Employee"}
    with patch("domains.hr.router._audit", new_callable=AsyncMock):
        res = client.post("/api/hr/staff", json=payload)

    # We use raise_server_exceptions=False in the global client, so this returns 500
    assert res.status_code == 500
    reserve_m.assert_called_once()
    release_m.assert_called_once()
    assert reserve_m.call_args[0][3] == release_m.call_args[0][3]

@pytest.mark.asyncio
async def test_hr_staff_deactivate_release(mock_auth_basic, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    mock_router_db.staff_members.find_one = AsyncMock(return_value={"id": "stf_123", "active": True})

    with patch("domains.hr.router._authorize_staff_access", new_callable=AsyncMock):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            res = client.put("/api/hr/staff/stf_123", json={"active": False})

    assert res.status_code == 200
    release_m.assert_called_once_with("tenant_hr_basic", "hr", "employees", "stf_123")
    reserve_m.assert_not_called()

@pytest.mark.asyncio
async def test_hr_staff_reactivate_consume(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    mock_router_db.staff_members.find_one = AsyncMock(return_value={"id": "stf_123", "active": False})

    with patch("domains.hr.router._authorize_staff_access", new_callable=AsyncMock):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            res = client.put("/api/hr/staff/stf_123", json={"active": True})

    assert res.status_code == 200
    reserve_m.assert_called_once_with("tenant_hr_basic", "hr", "employees", "stf_123", 50)
    release_m.assert_not_called()

@pytest.mark.asyncio
async def test_hr_staff_delete_release(mock_auth_basic, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    with patch("domains.hr.router._authorize_staff_access", new_callable=AsyncMock):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            res = client.delete("/api/hr/staff/stf_123")

    assert res.status_code == 200
    release_m.assert_called_once_with("tenant_hr_basic", "hr", "employees", "stf_123")

@pytest.mark.asyncio
async def test_hr_double_release_prevention(mock_auth_basic, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    mock_router_db.staff_members.find_one = AsyncMock(return_value={"id": "stf_123", "active": False})

    with patch("domains.hr.router._authorize_staff_access", new_callable=AsyncMock):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            res = client.put("/api/hr/staff/stf_123", json={"active": False})

    assert res.status_code == 200
    release_m.assert_not_called()
    reserve_m.assert_not_called()

import asyncio
from httpx import AsyncClient, ASGITransport

class FakeAtomicQuota:
    def __init__(self, initial_used=49, limit=50):
        self.used = initial_used
        self.limit = limit
        self.resources = set()
        self._lock = asyncio.Lock()

    async def reserve_quota(self, tenant_id, module_key, metric, resource_id, limit, force=False):
        async with self._lock:
            # Simulate DB processing time to ensure race window
            await asyncio.sleep(0.01)
            if resource_id in self.resources:
                return {"used": self.used, "resources": list(self.resources)}
            if self.used >= self.limit and not force:
                raise QuotaExceededException("Limit reached")
            self.used += 1
            self.resources.add(resource_id)
            return {"used": self.used, "resources": list(self.resources)}

@pytest.mark.asyncio
async def test_atomic_concurrency_simulation(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db):
    fake_quota = FakeAtomicQuota(initial_used=49, limit=50)

    payload = {"name": "Concurrent"}

    with patch("domains.hr.router.reserve_quota", side_effect=fake_quota.reserve_quota) as reserve_m:
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 123)), base_url="http://test") as ac:
                # Fire 2 concurrent POST requests
                req1 = ac.post("/api/hr/staff", json=payload)
                req2 = ac.post("/api/hr/staff", json=payload)

                res1, res2 = await asyncio.gather(req1, req2)

    # One should succeed (200), one should fail (403)
    statuses = [res1.status_code, res2.status_code]
    assert 200 in statuses
    assert 403 in statuses

    # Final used should be 50
    assert fake_quota.used == 50

    # DB insert should only be called once
    assert mock_router_db.staff_members.insert_one.call_count == 1


from pymongo.errors import DuplicateKeyError

@pytest.mark.asyncio
async def test_idempotent_creation_concurrent(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db):
    fake_quota = FakeAtomicQuota(initial_used=10, limit=50)

    payload = {"name": "Idempotent Staff", "client_request_id": "req-concurrent-123"}

    # Setup DB simulation for DuplicateKeyError
    db_lock = asyncio.Lock()
    inserted_keys = set()

    async def fake_update_one(filter_doc, update_doc, upsert=False):
        async with db_lock:
            await asyncio.sleep(0.01)
            # Check unique index constraint
            key = (filter_doc.get("tenant_id"), filter_doc.get("client_request_id"))
            if key in inserted_keys:
                raise DuplicateKeyError("E11000 duplicate key error")

            inserted_keys.add(key)
            mock_res = MagicMock()
            mock_res.upserted_id = "some_upsert_id"
            return mock_res

    mock_router_db.staff_members.update_one.side_effect = fake_update_one
    mock_router_db.staff_members.find_one.return_value = {"id": "stf_concurrent_123"}

    with patch("domains.hr.router.reserve_quota", side_effect=fake_quota.reserve_quota) as reserve_m:
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app, client=("127.0.0.1", 123)), base_url="http://test") as ac:
                req1 = ac.post("/api/hr/staff", json=payload)
                req2 = ac.post("/api/hr/staff", json=payload)

                res1, res2 = await asyncio.gather(req1, req2)

    # Both should be 200 or 409 (wait, we return 409 in the endpoint if no client_request_id, but here there is)
    assert res1.status_code == 200
    assert res2.status_code == 200

    # One should be normal success, the other idempotent
    responses = [res1.json(), res2.json()]
    assert any(r.get("source") == "idempotent" for r in responses)
    assert any(r.get("source") != "idempotent" for r in responses)

    # Quota should only increase by 1
    assert fake_quota.used == 11

    # DB update should only succeed once (the other threw DuplicateKeyError)
    assert len(inserted_keys) == 1

@pytest.mark.asyncio
async def test_idempotency_cross_tenant_isolation(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db):
    fake_quota = FakeAtomicQuota(initial_used=10, limit=50)

    payload = {"name": "Tenant A Staff", "client_request_id": "req-shared"}

    inserted_keys = set()
    async def fake_update_one(filter_doc, update_doc, upsert=False):
        key = (filter_doc.get("tenant_id"), filter_doc.get("client_request_id"))
        if key in inserted_keys:
            raise DuplicateKeyError("E11000")
        inserted_keys.add(key)
        mock_res = MagicMock()
        mock_res.upserted_id = "upserted"
        return mock_res

    mock_router_db.staff_members.update_one.side_effect = fake_update_one
    mock_router_db.staff_members.find_one.return_value = {"id": "stf_isolated_123"}

    async def fake_get_current_user_A():
        user = MagicMock()
        user.tenant_id = "tenant_A"
        user.is_active = True
        user.role = UserRole.ADMIN
        return user

    async def fake_get_current_user_B():
        user = MagicMock()
        user.tenant_id = "tenant_B"
        user.is_active = True
        user.role = UserRole.ADMIN
        return user

    from server import app
    from core.security import get_current_user
    from modules.pms_core.role_permission_service import require_op

    app.dependency_overrides[get_current_user] = fake_get_current_user_A
    app.dependency_overrides[require_op("manage_hr")] = lambda: True
    with patch("domains.hr.router.reserve_quota", side_effect=fake_quota.reserve_quota):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            resA = client.post("/api/hr/staff", json=payload)

    app.dependency_overrides[get_current_user] = fake_get_current_user_B
    payload["name"] = "Tenant B Staff"
    with patch("domains.hr.router.reserve_quota", side_effect=fake_quota.reserve_quota):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            resB = client.post("/api/hr/staff", json=payload)

    app.dependency_overrides.clear()

    assert resA.status_code == 200, resA.text
    assert resB.status_code == 200, resB.text

    assert len(inserted_keys) == 2
    assert ("tenant_A", "req-shared") in inserted_keys
    assert ("tenant_B", "req-shared") in inserted_keys

@pytest.mark.asyncio
async def test_reactivate_db_failure_rollback(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    mock_router_db.staff_members.find_one.return_value = {"id": "stf_123", "active": False}
    mock_router_db.staff_members.update_one.side_effect = Exception("DB update failed")

    with patch("domains.hr.router._authorize_staff_access", new_callable=AsyncMock):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            res = client.put("/api/hr/staff/stf_123", json={"active": True})

    assert res.status_code == 500
    reserve_m.assert_called_once()
    release_m.assert_called_once_with("tenant_hr_basic", "hr", "employees", "stf_123")

@pytest.mark.asyncio
async def test_deactivate_db_failure_no_release(mock_auth_basic, mock_active_editions_basic, mock_entitlement_registry, mock_router_db, mock_quota):
    reserve_m, release_m = mock_quota

    mock_router_db.staff_members.find_one.return_value = {"id": "stf_123", "active": True}
    mock_router_db.staff_members.update_one.side_effect = Exception("DB update failed")

    with patch("domains.hr.router._authorize_staff_access", new_callable=AsyncMock):
        with patch("domains.hr.router._audit", new_callable=AsyncMock):
            res = client.put("/api/hr/staff/stf_123", json={"active": False})

    assert res.status_code == 500
    release_m.assert_not_called()
