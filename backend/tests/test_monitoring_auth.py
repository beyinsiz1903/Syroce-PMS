"""
Task #54 — Channel monitoring endpoints auth guards.
Task #57 — Adds an explicit tenant-admin (role=admin) positive path so the
`require_op("view_system_diagnostics")` gate is exercised on its own
instead of being implicitly covered by super_admin's bypass.

Verifies the role gates added to `/api/channel-manager/monitoring/*`:

- Unauthenticated callers get 401/403.
- A non-admin tenant user (front desk) is rejected with 403 on every
  endpoint, including the tenant-scoped dispatch-config ones.
- A super_admin (demo user) can call all endpoints (200/4xx-by-payload,
  but never an auth-related rejection).
- A tenant admin (role=admin) can call the tenant-scoped dispatch-config
  endpoints (clears auth) AND is rejected with 403 on the cross-tenant
  monitoring endpoints (which require super_admin).

Cross-tenant endpoints (overview, alerts list, metrics, providers,
catchup-dedup, trends, alert ack/resolve) are super_admin-only.
The tenant-scoped dispatch-config endpoints accept tenant admins via
the `view_system_diagnostics` operation guard; we verify the front_desk
user (no SYSTEM_SETTINGS permission) is rejected there too.
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "http://localhost:8000").rstrip("/")
PREFIX = f"{BASE_URL}/api/channel-manager/monitoring"


# Skip the entire module cleanly if the backend isn't reachable, instead of
# letting individual tests fail with ConnectionError. We treat any 2xx/3xx/4xx
# response as "backend is up" — only network-level failures trigger skip.
def _backend_reachable() -> bool:
    try:
        requests.get(f"{BASE_URL}/api/health", timeout=2)
        return True
    except requests.RequestException:
        try:
            requests.get(BASE_URL, timeout=2)
            return True
        except requests.RequestException:
            return False


pytestmark = pytest.mark.skipif(
    not _backend_reachable(),
    reason=f"Backend not reachable at {BASE_URL}",
)


# Auth-gate matrix (for future maintainers):
#   cross-tenant endpoints (super_admin only, 403 for any other role):
#     GET  /overview, /alerts, /metrics, /providers, /catchup-dedup, /trends
#     POST /alerts/{id}/ack, /alerts/{id}/resolve
#   tenant-scoped endpoints (require_op view_system_diagnostics → tenant admin
#   or super_admin), data filtered by current_user.tenant_id:
#     GET  /dispatch-config
#     POST /dispatch-config/slack, /dispatch-config/slack/test

CROSS_TENANT_GET = [
    "/overview",
    "/alerts",
    "/metrics",
    "/providers",
    "/catchup-dedup",
    "/trends",
]

TENANT_SCOPED_GET = [
    "/dispatch-config",
]


def _login(email: str, password: str) -> str | None:
    try:
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=10,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


@pytest.fixture(scope="module")
def super_admin_headers():
    token = _login("demo@hotel.com", "demo123")
    if not token:
        pytest.skip("super_admin login (demo@hotel.com) unavailable")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def front_desk_headers():
    token = _login("frontdesk@hotel.com", "staff123")
    if not token:
        pytest.skip("front_desk login (frontdesk@hotel.com) unavailable")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tenant_admin_headers():
    """Tenant-scoped admin user (role=admin, NOT super_admin).

    Seeded by `auto_seed._ensure_tenant_admin_seeded` on every backend
    startup so this fixture works on existing databases too. Used to
    prove tenant admins still reach the tenant-scoped dispatch-config
    endpoints, while remaining 403 on cross-tenant ones.
    """
    token = _login("tenantadmin@hotel.com", "staff123")
    if not token:
        pytest.skip("tenant_admin login (tenantadmin@hotel.com) unavailable")
    return {"Authorization": f"Bearer {token}"}


# ── 1. Unauthenticated requests are rejected ────────────────────────

@pytest.mark.parametrize("path", CROSS_TENANT_GET + TENANT_SCOPED_GET)
def test_unauthenticated_get_is_rejected(path):
    r = requests.get(f"{PREFIX}{path}", timeout=10)
    assert r.status_code in (401, 403), (
        f"GET {path} without token must be 401/403, got {r.status_code}"
    )


def test_unauthenticated_alert_ack_is_rejected():
    r = requests.post(f"{PREFIX}/alerts/nonexistent-id/ack", json={}, timeout=10)
    assert r.status_code in (401, 403)


def test_unauthenticated_alert_resolve_is_rejected():
    r = requests.post(f"{PREFIX}/alerts/nonexistent-id/resolve", json={}, timeout=10)
    assert r.status_code in (401, 403)


# ── 2. Non-admin (front desk) is rejected with 403 on every endpoint ──

@pytest.mark.parametrize("path", CROSS_TENANT_GET)
def test_front_desk_blocked_on_cross_tenant_get(path, front_desk_headers):
    r = requests.get(f"{PREFIX}{path}", headers=front_desk_headers, timeout=10)
    assert r.status_code == 403, (
        f"front_desk GET {path} must be 403, got {r.status_code}: {r.text[:200]}"
    )


@pytest.mark.parametrize("path", TENANT_SCOPED_GET)
def test_front_desk_blocked_on_tenant_scoped_get(path, front_desk_headers):
    r = requests.get(f"{PREFIX}{path}", headers=front_desk_headers, timeout=10)
    assert r.status_code == 403, (
        f"front_desk GET {path} must be 403, got {r.status_code}: {r.text[:200]}"
    )


def test_front_desk_blocked_on_alert_ack(front_desk_headers):
    r = requests.post(
        f"{PREFIX}/alerts/nonexistent-id/ack",
        json={},
        headers=front_desk_headers,
        timeout=10,
    )
    assert r.status_code == 403


def test_front_desk_blocked_on_alert_resolve(front_desk_headers):
    r = requests.post(
        f"{PREFIX}/alerts/nonexistent-id/resolve",
        json={},
        headers=front_desk_headers,
        timeout=10,
    )
    assert r.status_code == 403


def test_front_desk_blocked_on_slack_config_update(front_desk_headers):
    r = requests.post(
        f"{PREFIX}/dispatch-config/slack",
        json={"enabled": False, "webhook_url": "", "severities": ["critical"], "channel_name": ""},
        headers=front_desk_headers,
        timeout=10,
    )
    assert r.status_code == 403


# ── 3. Super admin is allowed (no auth-rejection on any endpoint) ────

@pytest.mark.parametrize("path", CROSS_TENANT_GET + TENANT_SCOPED_GET)
def test_super_admin_allowed_on_get(path, super_admin_headers):
    r = requests.get(f"{PREFIX}{path}", headers=super_admin_headers, timeout=15)
    assert r.status_code not in (401, 403), (
        f"super_admin GET {path} must not be auth-rejected, got {r.status_code}: {r.text[:200]}"
    )
    # Sanity: a successful GET returns a JSON object (not an error envelope).
    if r.status_code == 200:
        assert isinstance(r.json(), dict)


def test_super_admin_can_call_alert_ack_404(super_admin_headers):
    """Auth passes — handler then returns 404 for the unknown alert id.

    What matters here is *not* the 404; it's that the request was not
    rejected at the auth/role layer.
    """
    r = requests.post(
        f"{PREFIX}/alerts/nonexistent-id-from-test/ack",
        json={},
        headers=super_admin_headers,
        timeout=10,
    )
    assert r.status_code not in (401, 403), (
        f"super_admin ack must clear auth gate, got {r.status_code}: {r.text[:200]}"
    )
    assert r.status_code == 404


def test_super_admin_can_call_alert_resolve_404(super_admin_headers):
    r = requests.post(
        f"{PREFIX}/alerts/nonexistent-id-from-test/resolve",
        json={},
        headers=super_admin_headers,
        timeout=10,
    )
    assert r.status_code not in (401, 403)
    assert r.status_code == 404


# ── 4. Tenant-scoped dispatch-config write endpoints clear auth gate ───
# Both super_admin (which bypasses the operation guard) and a plain tenant
# admin (which clears `require_op("view_system_diagnostics")` via the
# SYSTEM_SETTINGS permission) must reach the handler. Task #57 added the
# tenant_admin path to ensure the gate works for the role real customers
# log in with — not just the super_admin bypass.

def test_super_admin_can_update_slack_config(super_admin_headers):
    r = requests.post(
        f"{PREFIX}/dispatch-config/slack",
        json={
            "enabled": False,
            "webhook_url": "",
            "severities": ["critical"],
            "channel_name": "",
        },
        headers=super_admin_headers,
        timeout=10,
    )
    assert r.status_code not in (401, 403), (
        f"super_admin slack config update must clear auth gate, got {r.status_code}: {r.text[:200]}"
    )


def test_front_desk_blocked_on_slack_test(front_desk_headers):
    r = requests.post(
        f"{PREFIX}/dispatch-config/slack/test",
        json={},
        headers=front_desk_headers,
        timeout=10,
    )
    assert r.status_code == 403


def test_unauthenticated_slack_test_is_rejected():
    r = requests.post(f"{PREFIX}/dispatch-config/slack/test", json={}, timeout=10)
    assert r.status_code in (401, 403)


# ── 5. Tenant admin: positive on tenant-scoped, 403 on cross-tenant ─────
# Closes the gap noted in the task #54 review: prior coverage inferred the
# tenant-admin contract via super_admin (which bypasses every guard). These
# tests use a real role=admin (not super_admin) account seeded by
# `auto_seed._ensure_tenant_admin_seeded` so a regression that breaks the
# `view_system_diagnostics` permission mapping (or accidentally upgrades a
# tenant-scoped endpoint to super-admin-only) is caught immediately.

def test_tenant_admin_can_get_dispatch_config(tenant_admin_headers):
    r = requests.get(
        f"{PREFIX}/dispatch-config", headers=tenant_admin_headers, timeout=10,
    )
    assert r.status_code == 200, (
        f"tenant_admin GET /dispatch-config must be 200, got {r.status_code}: {r.text[:200]}"
    )
    body = r.json()
    assert isinstance(body, dict)


def test_tenant_admin_can_update_slack_config(tenant_admin_headers):
    """Auth gate clears for tenant admin on the slack-config write endpoint.

    We assert "not auth-rejected" rather than strict 200 because the
    underlying dispatch_config Mongo collection may not yet exist on
    storage-constrained environments (e.g. Atlas free tier with a 500-
    collection cap), in which case the handler bubbles up a non-auth 5xx.
    The point of this test is the role gate, mirroring the same pattern
    used for `test_super_admin_can_update_slack_config`. When the call
    does succeed (200), we additionally pin the success-body shape.
    """
    r = requests.post(
        f"{PREFIX}/dispatch-config/slack",
        json={
            "enabled": False,
            "webhook_url": "",
            "severities": ["critical"],
            "channel_name": "",
        },
        headers=tenant_admin_headers,
        timeout=10,
    )
    assert r.status_code not in (401, 403), (
        f"tenant_admin slack config update must clear auth gate, got {r.status_code}: {r.text[:200]}"
    )
    if r.status_code == 200:
        body = r.json()
        assert body.get("success") is True


@pytest.mark.parametrize("path", CROSS_TENANT_GET)
def test_tenant_admin_blocked_on_cross_tenant_get(path, tenant_admin_headers):
    r = requests.get(f"{PREFIX}{path}", headers=tenant_admin_headers, timeout=10)
    assert r.status_code == 403, (
        f"tenant_admin GET {path} must be 403 (cross-tenant), got {r.status_code}: {r.text[:200]}"
    )


def test_tenant_admin_blocked_on_alert_ack(tenant_admin_headers):
    r = requests.post(
        f"{PREFIX}/alerts/nonexistent-id/ack",
        json={},
        headers=tenant_admin_headers,
        timeout=10,
    )
    assert r.status_code == 403


def test_tenant_admin_blocked_on_alert_resolve(tenant_admin_headers):
    r = requests.post(
        f"{PREFIX}/alerts/nonexistent-id/resolve",
        json={},
        headers=tenant_admin_headers,
        timeout=10,
    )
    assert r.status_code == 403


def test_tenant_admin_can_call_slack_test(tenant_admin_headers):
    """Auth gate clears for tenant admin on /dispatch-config/slack/test.

    With no Slack webhook configured, the handler returns 400 ('No Slack
    webhook URL configured'). What this test pins is that the role gate
    accepted the tenant admin — the handler-level 400 is a separate
    contract that lives in the slack-config tests.
    """
    r = requests.post(
        f"{PREFIX}/dispatch-config/slack/test",
        json={},
        headers=tenant_admin_headers,
        timeout=10,
    )
    assert r.status_code not in (401, 403), (
        f"tenant_admin slack test must clear auth gate, got {r.status_code}: {r.text[:200]}"
    )
