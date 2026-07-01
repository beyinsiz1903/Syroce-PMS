"""
Comprehensive Hardening Tests — validates real logic in CMRuntime, WorkerRuntime,
SecurityRuntime services, normalized health API, role-based dashboard, audit metrics,
and WebSocket event publishing.

Uses HTTP requests against the running backend server for true end-to-end validation.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/") or "http://localhost:8000"


@pytest.fixture(scope="module")
def auth_headers():
    try:
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=5,
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        pytest.skip(f"Backend not reachable at {BASE_URL}: {e}")
    if resp.status_code != 200:
        pytest.skip("Authentication failed for demo@hotel.com")
    token = resp.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── CMRuntimeService ──

def test_cm_runtime_status_real_fields(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/channel-manager/runtime/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["health", "severity", "sync_stats", "drift", "reconciliation", "circuit_breakers", "providers"]:
        assert key in d, f"Missing CM field: {key}"
    assert d["health"] in ("healthy", "degraded", "critical", "unknown")


def test_cm_sync_stats_structure(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/channel-manager/runtime/status", headers=auth_headers)
    ss = resp.json().get("sync_stats", {})
    for key in ["total_24h", "failed_24h", "success_rate", "retry_backlog"]:
        assert key in ss, f"Missing sync_stats field: {key}"


def test_cm_drift_data(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/channel-manager/runtime/status", headers=auth_headers)
    drift = resp.json().get("drift", {})
    assert "active_drifts" in drift
    assert "critical_drifts" in drift


def test_cm_providers_data(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/channel-manager/runtime/status", headers=auth_headers)
    providers = resp.json().get("providers", {})
    assert "total" in providers
    assert "healthy" in providers


# ── WorkerRuntimeService ──

def test_queue_health_real_fields(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/workers/queues/health", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["health", "severity", "per_queue", "dead_letter", "worker_heartbeat", "retry_pressure", "recommendations"]:
        assert key in d, f"Missing queue health field: {key}"


def test_worker_per_queue_breakdown(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/workers/queues/health", headers=auth_headers)
    per_queue = resp.json().get("per_queue", [])
    assert isinstance(per_queue, list)
    for q in per_queue:
        for key in ["queue", "health", "pending"]:
            assert key in q


def test_dead_letter_structure(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/workers/queues/health", headers=auth_headers)
    dl = resp.json().get("dead_letter", {})
    for key in ["total", "today", "replay_candidates"]:
        assert key in dl


def test_stuck_tasks_grouping(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/workers/tasks/stuck", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["stuck_tasks", "count", "by_type"]:
        assert key in d


def test_worker_severity_on_no_activity(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/workers/queues/health", headers=auth_headers)
    d = resp.json()
    if not d.get("worker_heartbeat", {}).get("responding"):
        assert d["severity"] == "critical"


# ── SecurityRuntimeService ──

def test_audit_status_real_fields(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/security/audit/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["completeness", "completeness_score", "severity"]:
        assert key in d


def test_rate_limit_real_fields(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/security/rate-limit/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["enforcement", "burst_detected", "severity", "rejection_rate"]:
        assert key in d


def test_tenant_guard_status(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/security/tenant-guard/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "severity" in d
    assert "enforcement" in d


def test_log_sanitization_coverage(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/security/log-sanitization/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "coverage_pct" in d
    assert "all_patterns_working" in d


def test_security_severity_no_violations(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/security/tenant-guard/status", headers=auth_headers)
    d = resp.json()
    if d.get("total_violations", 0) == 0:
        assert d["severity"] == "info"


# ── Normalized Health Contract ──

def test_normalized_cm_enriched_contract(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/normalized/channel-manager", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["status", "severity", "data_freshness", "evidence_summary", "detail", "live_capable",
                 "degraded_reason", "critical_blockers"]:
        assert key in d, f"Missing normalized field: {key}"
    assert d["live_capable"] is True
    assert d["data_freshness"] == "real-time"


def test_normalized_workers_contract(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/normalized/workers", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "worker_responding" in d["detail"]


def test_normalized_security_contract(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/normalized/security", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "audit_completeness_score" in d["detail"]


def test_normalized_overview_all_subsystems(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/normalized/overview", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "subsystems" in d
    for sub in ["channel_manager", "workers", "security", "observability", "alerts"]:
        assert sub in d["subsystems"], f"Missing subsystem: {sub}"
    assert d["data_freshness"] == "real-time"


def test_normalized_alerts(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/normalized/alerts", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "total_active" in d["detail"]


def test_normalized_observability(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/normalized/observability", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "detail" in d
    assert "unresolved_errors" in d["detail"]


# ── Role-Based Dashboard ──

def test_role_dashboard_admin_panels(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/role-dashboard", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["role", "panels", "scope"]:
        assert key in d
    panels = d["panels"]
    for panel in ["queue_health", "security", "workers", "drift_summary", "sync_summary"]:
        assert panel in panels, f"Missing admin panel: {panel}"


def test_role_dashboard_drift_data(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/role-dashboard", headers=auth_headers)
    drift = resp.json()["panels"]["drift_summary"]
    for key in ["drift_count", "critical_drifts", "status"]:
        assert key in drift


def test_role_dashboard_queue_health(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/role-dashboard", headers=auth_headers)
    qh = resp.json()["panels"]["queue_health"]
    assert "severity" in qh
    assert "stuck_tasks" in qh


# ── Audit Metrics ──

def test_audit_metrics_endpoint(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/audit/metrics", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    for key in ["drift", "reconciliation", "queue", "security", "dead_letter"]:
        assert key in d, f"Missing audit metric: {key}"


def test_audit_metrics_recon(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/audit/metrics", headers=auth_headers)
    recon = resp.json()["reconciliation"]
    for key in ["total_runs", "success_count", "success_rate"]:
        assert key in recon


# ── Live Events ──

def test_live_status(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/live/status", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "ws_available" in d
    assert "ws_connected_clients" in d


def test_live_events(auth_headers):
    resp = requests.get(f"{BASE_URL}/api/system-health/live/events", headers=auth_headers)
    assert resp.status_code == 200
    d = resp.json()
    assert "events" in d
    assert "count" in d


# ── WebSocket Broadcasting ──

def test_connected_clients_has_health_room():
    from websocket_server import connected_clients
    assert "system-health" in connected_clients


@pytest.mark.asyncio
async def test_broadcast_system_health_event():
    from websocket_server import broadcast_system_health_event
    await broadcast_system_health_event("test_event", {"test": True}, tenant_id="t", severity="info")


@pytest.mark.asyncio
async def test_broadcast_health_metric_update():
    from websocket_server import broadcast_health_metric_update
    await broadcast_health_metric_update("queue_depth", {"pending": 5}, tenant_id="t")
