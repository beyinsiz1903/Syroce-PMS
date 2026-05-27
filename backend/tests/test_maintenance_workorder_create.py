"""Task #98 — Maintenance work-order create+list happy path.

Regression guard for the 500 caused by Motor `insert_one` mutating the
payload in-place with a non-JSON-serializable ObjectId `_id`, which FastAPI
then failed to encode on the POST response.

Lives as a live HTTP integration test against the demo backend (port 8000)
to match the existing conftest fixture pattern.
"""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set — integration tests require a running server",
)


class TestMaintenanceWorkOrderCreate:
    def test_a_create_returns_2xx_and_payload(self, demo_auth_headers):
        marker = f"T98_{uuid.uuid4().hex[:10].upper()}"
        body = {
            "issue_type": "plumbing",
            "priority": "normal",
            "description": marker,
        }
        r = requests.post(
            f"{BASE_URL}/api/maintenance/work-orders",
            json=body,
            headers=demo_auth_headers,
            timeout=15,
        )
        if r.status_code in (401, 403):
            pytest.skip(f"demo user lacks perm (status={r.status_code})")
        assert r.status_code in (200, 201), (
            f"create must return 2xx; got {r.status_code} {r.text[:300]}"
        )
        data = r.json()
        assert "_id" not in data, "response must not leak Mongo ObjectId _id"
        assert data.get("id"), f"response missing id: {data}"
        assert data.get("issue_type") == "plumbing"
        assert data.get("priority") == "normal"
        assert data.get("description") == marker
        assert data.get("status") == "open"
        assert data.get("tenant_id"), "tenant_id must be set server-side"
        assert data.get("reported_by_user_id"), "reported_by_user_id default missing"
        assert data.get("created_at"), "created_at missing"

    def test_b_created_order_appears_in_list(self, demo_auth_headers):
        marker = f"T98LIST_{uuid.uuid4().hex[:10].upper()}"
        r = requests.post(
            f"{BASE_URL}/api/maintenance/work-orders",
            json={
                "issue_type": "electrical",
                "priority": "high",
                "description": marker,
            },
            headers=demo_auth_headers,
            timeout=15,
        )
        if r.status_code in (401, 403):
            pytest.skip(f"demo user lacks perm (status={r.status_code})")
        assert r.status_code in (200, 201), (
            f"create failed: {r.status_code} {r.text[:300]}"
        )
        created_id = r.json().get("id")
        assert created_id

        r2 = requests.get(
            f"{BASE_URL}/api/maintenance/work-orders",
            headers=demo_auth_headers,
            timeout=15,
        )
        assert r2.status_code == 200, f"list failed: {r2.status_code}"
        items = r2.json().get("items") or []
        match = next((i for i in items if i.get("id") == created_id), None)
        assert match is not None, (
            f"created work order {created_id} missing from list "
            f"(found {len(items)} items)"
        )
        assert match.get("description") == marker
        assert match.get("issue_type") == "electrical"
