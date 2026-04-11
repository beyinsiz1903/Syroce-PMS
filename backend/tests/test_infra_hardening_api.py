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


async def _get_client_and_token():
    from server import app
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    resp = await client.post("/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    token = resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


# ── Summary Endpoint ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_infra_summary():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/summary", headers=headers)
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
    await client.aclose()


# ── Redis Endpoints ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_redis_health():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/redis/health", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "mode" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_redis_metrics():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/redis/metrics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "connected" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_redis_locks():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/redis/locks", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "active_locks" in data
    await client.aclose()


# ── Worker Endpoints ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_workers_summary():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/workers/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "queues" in data
    assert "total_submitted" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_workers_queues():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/workers/queues", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "default" in data
    assert "ml" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_workers_failures():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/workers/failures", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    await client.aclose()


@pytest.mark.asyncio
async def test_workers_stuck():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/workers/stuck", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    await client.aclose()


# ── Secrets Endpoints ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_secrets_health():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/secrets/health", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "env"
    assert data["status"] == "healthy"
    await client.aclose()


@pytest.mark.asyncio
async def test_secrets_audit():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/secrets/audit", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_log" in data
    assert "metrics" in data
    await client.aclose()


# ── Backup Endpoints ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backup_status():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/backup/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "enabled" in data
    assert "rpo_target" in data
    assert "critical_collections" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_backup_history():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/backup/history", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    await client.aclose()


@pytest.mark.asyncio
async def test_backup_trigger():
    client, headers = await _get_client_and_token()
    resp = await client.post("/api/infra/backup/trigger", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "backup_triggered"
    await client.aclose()


@pytest.mark.asyncio
async def test_backup_cleanup():
    client, headers = await _get_client_and_token()
    resp = await client.post("/api/infra/backup/cleanup", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "removed" in data
    await client.aclose()


# ── Observability Endpoints ────────────────────────────────────────

@pytest.mark.asyncio
async def test_observability_status():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/observability/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "otel" in data
    assert "sentry" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_observability_metrics():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/observability/metrics", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "latency" in data
    assert "counters" in data
    await client.aclose()


# ── Scaling Endpoints ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scaling_summary():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/scaling/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "scaling_mode" in data
    assert "total_instances" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_scaling_instances():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/scaling/instances", headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    await client.aclose()


@pytest.mark.asyncio
async def test_stateless_check():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/scaling/stateless-check", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "ready_for_scaling" in data
    assert "checks" in data
    await client.aclose()


@pytest.mark.asyncio
async def test_scaling_readiness_no_auth():
    """Readiness probe should work without auth for load balancers."""
    from server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/infra/scaling/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True


# ── Container Endpoint ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_container_info():
    client, headers = await _get_client_and_token()
    resp = await client.get("/api/infra/container/info", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "is_containerized" in data
    assert "python_version" in data
    assert "environment_vars_present" in data
    await client.aclose()


# ── Auth Required ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_requires_auth():
    from server import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/infra/summary")
        assert resp.status_code in (401, 403)
