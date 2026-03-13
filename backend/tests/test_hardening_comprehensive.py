"""
Comprehensive Hardening Tests — validates real logic in CMRuntime, WorkerRuntime,
SecurityRuntime services, normalized health API, role-based dashboard, audit metrics,
and WebSocket event publishing.

All API tests use a shared HTTPX AsyncClient fixture to avoid Motor event-loop issues.
Requires running MongoDB instance - skip in CI.
"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

if not os.environ.get("MONGO_URL"):
    pytest.skip("Requires MONGO_URL (skipped in CI)", allow_module_level=True)

from server import app


# ── Session-scoped fixtures ──

@pytest_asyncio.fixture(scope="module")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(scope="module")
async def auth_headers(client):
    resp = await client.post("/api/auth/login", json={"email": "demo@hotel.com", "password": "demo123"})
    token = resp.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


# ── CMRuntimeService ──

@pytest.mark.asyncio(loop_scope="module")
async def test_cm_runtime_status_real_fields(client, auth_headers):
    resp = await client.get("/api/channel-manager/runtime/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["health", "severity", "sync_stats", "drift", "reconciliation", "circuit_breakers", "providers"]:
        assert key in d, f"Missing CM field: {key}"
    assert d["health"] in ("healthy", "degraded", "critical", "unknown")


@pytest.mark.asyncio(loop_scope="module")
async def test_cm_sync_stats_structure(client, auth_headers):
    resp = await client.get("/api/channel-manager/runtime/status", headers=auth_headers)
    ss = resp.json().get("sync_stats", {})
    for key in ["total_24h", "failed_24h", "success_rate", "retry_backlog"]:
        assert key in ss, f"Missing sync_stats field: {key}"


@pytest.mark.asyncio(loop_scope="module")
async def test_cm_drift_data(client, auth_headers):
    resp = await client.get("/api/channel-manager/runtime/status", headers=auth_headers)
    drift = resp.json().get("drift", {})
    assert "active_drifts" in drift
    assert "critical_drifts" in drift


@pytest.mark.asyncio(loop_scope="module")
async def test_cm_providers_data(client, auth_headers):
    resp = await client.get("/api/channel-manager/runtime/status", headers=auth_headers)
    providers = resp.json().get("providers", {})
    assert "total" in providers
    assert "healthy" in providers


# ── WorkerRuntimeService ──

@pytest.mark.asyncio(loop_scope="module")
async def test_queue_health_real_fields(client, auth_headers):
    resp = await client.get("/api/workers/queues/health", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["health", "severity", "per_queue", "dead_letter", "worker_heartbeat", "retry_pressure", "recommendations"]:
        assert key in d, f"Missing queue health field: {key}"


@pytest.mark.asyncio(loop_scope="module")
async def test_worker_per_queue_breakdown(client, auth_headers):
    resp = await client.get("/api/workers/queues/health", headers=auth_headers)
    per_queue = resp.json().get("per_queue", [])
    assert isinstance(per_queue, list)
    for q in per_queue:
        for key in ["queue", "health", "pending"]:
            assert key in q


@pytest.mark.asyncio(loop_scope="module")
async def test_dead_letter_structure(client, auth_headers):
    resp = await client.get("/api/workers/queues/health", headers=auth_headers)
    dl = resp.json().get("dead_letter", {})
    for key in ["total", "today", "replay_candidates"]:
        assert key in dl


@pytest.mark.asyncio(loop_scope="module")
async def test_stuck_tasks_grouping(client, auth_headers):
    resp = await client.get("/api/workers/tasks/stuck", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["stuck_tasks", "count", "by_type"]:
        assert key in d


@pytest.mark.asyncio(loop_scope="module")
async def test_worker_severity_on_no_activity(client, auth_headers):
    resp = await client.get("/api/workers/queues/health", headers=auth_headers)
    d = resp.json()
    if not d.get("worker_heartbeat", {}).get("responding"):
        assert d["severity"] == "critical"


# ── SecurityRuntimeService ──

@pytest.mark.asyncio(loop_scope="module")
async def test_audit_status_real_fields(client, auth_headers):
    resp = await client.get("/api/security/audit/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["completeness", "completeness_score", "severity"]:
        assert key in d


@pytest.mark.asyncio(loop_scope="module")
async def test_rate_limit_real_fields(client, auth_headers):
    resp = await client.get("/api/security/rate-limit/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["enforcement", "burst_detected", "severity", "rejection_rate"]:
        assert key in d


@pytest.mark.asyncio(loop_scope="module")
async def test_tenant_guard_status(client, auth_headers):
    resp = await client.get("/api/security/tenant-guard/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "severity" in d
    assert "enforcement" in d


@pytest.mark.asyncio(loop_scope="module")
async def test_log_sanitization_coverage(client, auth_headers):
    resp = await client.get("/api/security/log-sanitization/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "coverage_pct" in d
    assert "all_patterns_working" in d


@pytest.mark.asyncio(loop_scope="module")
async def test_security_severity_no_violations(client, auth_headers):
    resp = await client.get("/api/security/tenant-guard/status", headers=auth_headers)
    d = resp.json()
    if d.get("total_violations", 0) == 0:
        assert d["severity"] == "info"


# ── Normalized Health Contract ──

@pytest.mark.asyncio(loop_scope="module")
async def test_normalized_cm_enriched_contract(client, auth_headers):
    resp = await client.get("/api/system-health/normalized/channel-manager", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["status", "severity", "data_freshness", "evidence_summary", "detail", "live_capable",
                 "degraded_reason", "critical_blockers"]:
        assert key in d, f"Missing normalized field: {key}"
    assert d["live_capable"] is True
    assert d["data_freshness"] == "real-time"


@pytest.mark.asyncio(loop_scope="module")
async def test_normalized_workers_contract(client, auth_headers):
    resp = await client.get("/api/system-health/normalized/workers", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "worker_responding" in d["detail"]


@pytest.mark.asyncio(loop_scope="module")
async def test_normalized_security_contract(client, auth_headers):
    resp = await client.get("/api/system-health/normalized/security", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "audit_completeness_score" in d["detail"]


@pytest.mark.asyncio(loop_scope="module")
async def test_normalized_overview_all_subsystems(client, auth_headers):
    resp = await client.get("/api/system-health/normalized/overview", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "subsystems" in d
    for sub in ["channel_manager", "workers", "security", "observability", "alerts"]:
        assert sub in d["subsystems"], f"Missing subsystem: {sub}"
    assert d["data_freshness"] == "real-time"


@pytest.mark.asyncio(loop_scope="module")
async def test_normalized_alerts(client, auth_headers):
    resp = await client.get("/api/system-health/normalized/alerts", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "total_active" in d["detail"]


@pytest.mark.asyncio(loop_scope="module")
async def test_normalized_observability(client, auth_headers):
    resp = await client.get("/api/system-health/normalized/observability", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "unresolved_errors" in d["detail"]


# ── Role-Based Dashboard ──

@pytest.mark.asyncio(loop_scope="module")
async def test_role_dashboard_admin_panels(client, auth_headers):
    resp = await client.get("/api/system-health/role-dashboard", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["role", "panels", "scope"]:
        assert key in d
    panels = d["panels"]
    for panel in ["queue_health", "security", "workers", "drift_summary", "sync_summary"]:
        assert panel in panels, f"Missing admin panel: {panel}"


@pytest.mark.asyncio(loop_scope="module")
async def test_role_dashboard_drift_data(client, auth_headers):
    resp = await client.get("/api/system-health/role-dashboard", headers=auth_headers)
    drift = resp.json()["panels"]["drift_summary"]
    for key in ["drift_count", "critical_drifts", "status"]:
        assert key in drift


@pytest.mark.asyncio(loop_scope="module")
async def test_role_dashboard_queue_health(client, auth_headers):
    resp = await client.get("/api/system-health/role-dashboard", headers=auth_headers)
    qh = resp.json()["panels"]["queue_health"]
    assert "severity" in qh
    assert "stuck_tasks" in qh


# ── Audit Metrics ──

@pytest.mark.asyncio(loop_scope="module")
async def test_audit_metrics_endpoint(client, auth_headers):
    resp = await client.get("/api/system-health/audit/metrics", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["drift", "reconciliation", "queue", "security", "dead_letter"]:
        assert key in d, f"Missing audit metric: {key}"


@pytest.mark.asyncio(loop_scope="module")
async def test_audit_metrics_recon(client, auth_headers):
    resp = await client.get("/api/system-health/audit/metrics", headers=auth_headers)
    recon = resp.json()["reconciliation"]
    for key in ["total_runs", "success_count", "success_rate"]:
        assert key in recon


# ── Live Events ──

@pytest.mark.asyncio(loop_scope="module")
async def test_live_status(client, auth_headers):
    resp = await client.get("/api/system-health/live/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "ws_available" in d
    assert "ws_connected_clients" in d


@pytest.mark.asyncio(loop_scope="module")
async def test_live_events(client, auth_headers):
    resp = await client.get("/api/system-health/live/events", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "events" in d
    assert "count" in d


# ── WebSocket Broadcasting ──

def test_connected_clients_has_health_room():
    from websocket_server import connected_clients
    assert "system-health" in connected_clients


@pytest.mark.asyncio(loop_scope="module")
async def test_broadcast_system_health_event():
    from websocket_server import broadcast_system_health_event
    await broadcast_system_health_event("test_event", {"test": True}, tenant_id="t", severity="info")


@pytest.mark.asyncio(loop_scope="module")
async def test_broadcast_health_metric_update():
    from websocket_server import broadcast_health_metric_update
    await broadcast_health_metric_update("queue_depth", {"pending": 5}, tenant_id="t")
