"""
Task #54 — Channel monitoring endpoints auth guards.

Verifies the role gates added to `/api/channel-manager/monitoring/*`:

- Unauthenticated callers get 401/403.
- A non-admin tenant user (front desk) is rejected with 403 on every
  endpoint, including the tenant-scoped dispatch-config ones.
- A super_admin (demo user) can call all endpoints (200/4xx-by-payload,
  but never an auth-related rejection).

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
# The current seed data only includes super_admin and non-admin staff users
# (no plain `admin` role user), so we cover the auth gate via super_admin
# (which bypasses the operation guard) — this still proves the endpoint
# is reachable for an authorized caller and that the unauth/front_desk
# rejections above are real, not collateral from a broken handler.

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
