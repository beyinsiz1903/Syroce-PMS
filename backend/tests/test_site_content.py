"""Live-integration tests for the public landing content API.

  GET  /api/site-content        — public, always 200, JSON object
  PUT  /api/admin/site-content  — super_admin only, plain-text + length guards

Mirrors the repo convention: hit the running backend on VITE_BACKEND_URL via
``requests`` (see conftest). Writes target the GLOBAL ``site_content`` singleton
(no tenant scoping, no pilot mutation); the suite resets it to empty at the end
so the landing falls back to its built-in defaults.
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "http://localhost:8000").rstrip("/")


def _login(email: str, password: str):
    try:
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=10,
        )
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    return resp.json().get("access_token")


@pytest.fixture(scope="module")
def super_token():
    """Super-admin token via the always-seeded demo super_admin account."""
    token = _login("demo@syroce.com", "demo123")
    if not token:
        token = _login("demo@hotel.com", "demo123")
    if not token:
        pytest.skip("No super_admin login available")
    return token


def test_public_get_is_200_and_object():
    resp = requests.get(f"{BASE_URL}/api/site-content", timeout=10)
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_put_requires_auth():
    resp = requests.put(
        f"{BASE_URL}/api/admin/site-content",
        json={"brandName": "Hacker"},
        timeout=10,
    )
    assert resp.status_code in (401, 403)


def test_put_rejects_tenant_admin():
    """A non-super-admin (stress tenant admin) must be denied (403)."""
    email = os.environ.get("E2E_STRESS_ADMIN_EMAIL")
    password = os.environ.get("E2E_STRESS_ADMIN_PASSWORD")
    if not email or not password:
        pytest.skip("E2E_STRESS_ADMIN_* not set")
    token = _login(email, password)
    if not token:
        pytest.skip("stress admin login failed")
    resp = requests.put(
        f"{BASE_URL}/api/admin/site-content",
        json={"brandName": "Hacker"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert resp.status_code == 403


def test_super_admin_upsert_and_readback(super_token):
    headers = {"Authorization": f"Bearer {super_token}"}
    payload = {
        "brandName": "Syroce Test",
        "hero": {"badge": "TEST BADGE", "titlePre": "A", "titleAccent": "B", "titlePost": "C"},
        "contact": {"phone": "+90 000", "email": "t@test.com", "address": "Test"},
        "solutions": [{"title": "S1", "desc": "D1"}],
        "faqs": [{"q": "Q1", "a": "A1"}],
    }
    resp = requests.put(
        f"{BASE_URL}/api/admin/site-content", json=payload, headers=headers, timeout=10
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["brandName"] == "Syroce Test"
    assert body["hero"]["badge"] == "TEST BADGE"

    # Public read reflects the write.
    got = requests.get(f"{BASE_URL}/api/site-content", timeout=10).json()
    assert got["brandName"] == "Syroce Test"
    assert got["solutions"][0]["title"] == "S1"
    # Public GET must NOT leak admin metadata/PII (allowlist only).
    assert "updated_by" not in got
    assert "updated_at" not in got
    assert "_id" not in got


def test_super_admin_length_validation_422(super_token):
    headers = {"Authorization": f"Bearer {super_token}"}
    resp = requests.put(
        f"{BASE_URL}/api/admin/site-content",
        json={"brandName": "X" * 200},
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 422


def test_super_admin_html_rejected_422(super_token):
    headers = {"Authorization": f"Bearer {super_token}"}
    resp = requests.put(
        f"{BASE_URL}/api/admin/site-content",
        json={"hero": {"badge": "<script>alert(1)</script>"}},
        headers=headers,
        timeout=10,
    )
    assert resp.status_code == 422


def test_zz_reset_to_defaults(super_token):
    """Cleanup: blank the singleton so landing falls back to defaults."""
    headers = {"Authorization": f"Bearer {super_token}"}
    resp = requests.put(
        f"{BASE_URL}/api/admin/site-content", json={}, headers=headers, timeout=10
    )
    assert resp.status_code == 200
