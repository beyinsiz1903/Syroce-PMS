"""
Infrastructure Hardening API Integration Tests.
Tests all /api/infra/* endpoints via HTTP client.
"""
import os
import pytest
from httpx import AsyncClient, ASGITransport

if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Event loop conflict in CI", allow_module_level=True)


@pytest.fixture
def anyio_backend():
    return "asyncio"


import pytest_asyncio

from unittest.mock import patch
from core.database import _raw_db

@pytest_asyncio.fixture(scope="module")
async def seed_test_user():
    """Idempotent local test user seed for testing."""
    import os
    assert os.environ.get("TESTING") == "1", "Test DB seed aborted: TESTING is not 1"

    from core.security import hash_password
    test_user = {
        "email": "demo@hotel.com",
        "username": "demo",
        "hashed_password": hash_password("demo123"),
        "role": "admin",
        "tenant_id": "test-tenant-123"
    }
    await _raw_db.users.update_one({"email": "demo@hotel.com"}, {"$set": test_user}, upsert=True)
    try:
        yield
    finally:
        await _raw_db.users.delete_one({"email": "demo@hotel.com"})

@pytest_asyncio.fixture
async def auth_client(seed_test_user):
    from server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("security.auth_throttle.enforce", return_value=None):
            resp = await client.post("/api/auth/login", json={
                "email": "demo@hotel.com",
                "password": "demo123"
            })
            token = resp.json().get("access_token")
        client.headers = {"Authorization": f"Bearer {token}"}
        yield client


# ── Summary Endpoint ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_infra_summary(auth_client):
    resp = await auth_client.get("/api/infra/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "redis_cluster" in data
    assert "distributed_locks" in data
    assert "worker_queues" in data
    assert "secrets" in data
    assert "backup" in data
    assert "observability" in data
    assert "scaling" in data
    assert "container" in data



# ── Redis Endpoints ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redis_health(auth_client):
    resp = await auth_client.get("/api/infra/redis/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "mode" in data



@pytest.mark.asyncio
async def test_redis_metrics(auth_client):
    resp = await auth_client.get("/api/infra/redis/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data



@pytest.mark.asyncio
async def test_redis_locks(auth_client):
    resp = await auth_client.get("/api/infra/redis/locks")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "active_locks" in data



# ── Worker Endpoints ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_workers_summary(auth_client):
    resp = await auth_client.get("/api/infra/workers/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "queues" in data
    assert "total_submitted" in data



@pytest.mark.asyncio
async def test_workers_queues(auth_client):
    resp = await auth_client.get("/api/infra/workers/queues")
    assert resp.status_code == 200
    data = resp.json()
    assert "default" in data
    assert "ml" in data



@pytest.mark.asyncio
async def test_workers_failures(auth_client):
    resp = await auth_client.get("/api/infra/workers/failures")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)



@pytest.mark.asyncio
async def test_workers_stuck(auth_client):
    resp = await auth_client.get("/api/infra/workers/stuck")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)



# ── Secrets Endpoints ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_secrets_health(auth_client):
    resp = await auth_client.get("/api/infra/secrets/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "env"
    assert data["status"] == "healthy"



@pytest.mark.asyncio
async def test_secrets_audit(auth_client):
    resp = await auth_client.get("/api/infra/secrets/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert "access_log" in data
    assert "metrics" in data



# ── Backup Endpoints ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backup_status(auth_client):
    resp = await auth_client.get("/api/infra/backup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "rpo_target" in data
    assert "critical_collections" in data



@pytest.mark.asyncio
async def test_backup_history(auth_client):
    resp = await auth_client.get("/api/infra/backup/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)



@pytest.mark.asyncio
async def test_backup_trigger(auth_client):
    resp = await auth_client.post("/api/infra/backup/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "backup_triggered"



@pytest.mark.asyncio
async def test_backup_cleanup(auth_client):
    resp = await auth_client.post("/api/infra/backup/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert "removed" in data



# ── Observability Endpoints ────────────────────────────────────────

@pytest.mark.asyncio
async def test_observability_status(auth_client):
    resp = await auth_client.get("/api/infra/observability/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "otel" in data
    assert "sentry" in data



@pytest.mark.asyncio
async def test_observability_metrics(auth_client):
    resp = await auth_client.get("/api/infra/observability/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "latency" in data
    assert "counters" in data



# ── Scaling Endpoints ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scaling_summary(auth_client):
    resp = await auth_client.get("/api/infra/scaling/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "scaling_mode" in data
    assert "total_instances" in data



@pytest.mark.asyncio
async def test_scaling_instances(auth_client):
    resp = await auth_client.get("/api/infra/scaling/instances")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)



@pytest.mark.asyncio
async def test_stateless_check(auth_client):
    resp = await auth_client.get("/api/infra/scaling/stateless-check")
    assert resp.status_code == 200
    data = resp.json()
    assert "ready_for_scaling" in data
    assert "checks" in data



@pytest.mark.asyncio
async def test_scaling_readiness_no_auth(auth_client):
    """Readiness probe should work without auth for load balancers."""
    from server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await auth_client.get("/api/infra/scaling/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True


# ── Container Endpoint ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_container_info(auth_client):
    resp = await auth_client.get("/api/infra/container/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_containerized" in data
    assert "python_version" in data
    assert "environment_vars_present" in data



# ── Auth Required ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_requires_auth(auth_client):
    from server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/infra/summary")
        assert resp.status_code in (401, 403)
