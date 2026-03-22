"""
Battle Tests: Learning Loop
=============================
Tests for incident auto-classification, recurrence detection, RCA, and never-again rules.
"""
import pytest
import httpx
import os
import uuid

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")

_cached_headers = None


async def get_auth_headers():
    global _cached_headers
    if _cached_headers:
        return _cached_headers
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{API_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123",
        })
        data = resp.json()
        token = data.get("access_token") or data.get("token", "")
        _cached_headers = {"Authorization": f"Bearer {token}"}
        return _cached_headers


@pytest.mark.asyncio
async def test_create_incident_auto_classifies():
    """Creating an incident should auto-classify based on keywords."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/api/ops/learning/incidents",
            headers=headers,
            json={
                "title": "Exely reservation pull timeout spike",
                "description": "50% of Exely reservation pulls timed out between 14:00-14:30",
                "severity": "P1",
                "affected_service": "channel_manager",
            },
        )
        assert resp.status_code == 200, f"Create failed: {resp.text}"
        data = resp.json()
        assert "incident_id" in data
        assert "classification" in data
        cls = data["classification"]
        assert cls["auto_classified"] is True
        assert cls["category"] in ("provider", "infrastructure")
        assert "exely" in cls["tags"]


@pytest.mark.asyncio
async def test_create_incident_with_security_keywords():
    """Security-related keywords should classify as security."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{API_URL}/api/ops/learning/incidents",
            headers=headers,
            json={
                "title": "Unauthorized access attempt detected",
                "description": "Multiple forbidden requests with invalid token from suspicious IP",
                "severity": "P1",
                "affected_service": "security",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        cls = data["classification"]
        assert cls["category"] == "security"


@pytest.mark.asyncio
async def test_rca_workflow():
    """Full RCA workflow: create incident -> add RCA -> track fix."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        # Create incident
        create_resp = await client.post(
            f"{API_URL}/api/ops/learning/incidents",
            headers=headers,
            json={
                "title": "MongoDB connection pool exhaustion",
                "description": "Connection pool full, redis cluster rebalance caused cascading timeout",
                "severity": "P2",
                "affected_service": "infrastructure",
            },
        )
        assert create_resp.status_code == 200
        incident_id = create_resp.json()["incident_id"]

        # Add RCA
        rca_resp = await client.put(
            f"{API_URL}/api/ops/learning/incidents/{incident_id}/rca",
            headers=headers,
            json={
                "summary": "Connection pool max was 10, needs 50 for peak load",
                "contributing_factors": [
                    "Pool size too small",
                    "No circuit breaker on DB layer",
                ],
                "five_whys": [
                    "Why did connections exhaust? Pool max=10",
                    "Why so low? Default config never changed",
                ],
                "root_cause_type": "configuration",
            },
        )
        assert rca_resp.status_code == 200
        assert rca_resp.json()["status"] == "in_progress"

        # Track fix
        fix_resp = await client.put(
            f"{API_URL}/api/ops/learning/incidents/{incident_id}/fix",
            headers=headers,
            json={"fix_applied": "Increased pool to 50, added circuit breaker"},
        )
        assert fix_resp.status_code == 200


@pytest.mark.asyncio
async def test_never_again_rule():
    """Add and verify never-again rules."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        # Create incident
        create_resp = await client.post(
            f"{API_URL}/api/ops/learning/incidents",
            headers=headers,
            json={
                "title": "Duplicate reservation import",
                "description": "Same reservation imported twice due to idempotency bypass",
                "severity": "P3",
                "affected_service": "channel_manager",
            },
        )
        assert create_resp.status_code == 200
        incident_id = create_resp.json()["incident_id"]

        # Add never-again rule
        rule_resp = await client.post(
            f"{API_URL}/api/ops/learning/incidents/{incident_id}/never-again",
            headers=headers,
            json={
                "rule_type": "test_case",
                "description": "Add test for duplicate import detection",
                "implementation": "tests/battle/test_duplicate_import.py",
                "verification_type": "test_exists",
                "verification_detail": "test_duplicate_import_rejected",
            },
        )
        assert rule_resp.status_code == 200
        assert rule_resp.json()["status"] == "pending"

        # Verify prevention
        verify_resp = await client.post(
            f"{API_URL}/api/ops/learning/incidents/{incident_id}/verify-prevention",
            headers=headers,
        )
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["all_verified"] is False  # Rule is still "pending"
        assert data["total_rules"] == 1


@pytest.mark.asyncio
async def test_recurrence_detection():
    """Second incident with same pattern should detect recurrence."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        # Create first incident
        resp1 = await client.post(
            f"{API_URL}/api/ops/learning/incidents",
            headers=headers,
            json={
                "title": f"HotelRunner sync timeout {uuid.uuid4().hex[:6]}",
                "description": "Provider timeout during rate sync with hotelrunner",
                "severity": "P2",
                "affected_service": "channel_manager",
            },
        )
        assert resp1.status_code == 200
        incident1_id = resp1.json()["incident_id"]

        # Resolve first incident via RCA + fix workflow
        await client.put(
            f"{API_URL}/api/ops/learning/incidents/{incident1_id}/rca",
            headers=headers,
            json={
                "summary": "Provider timeout",
                "contributing_factors": ["Slow provider"],
                "root_cause_type": "external_dependency",
            },
        )
        await client.put(
            f"{API_URL}/api/ops/learning/incidents/{incident1_id}/fix",
            headers=headers,
            json={"fix_applied": "Increased timeout"},
        )

        # Create second similar incident
        resp2 = await client.post(
            f"{API_URL}/api/ops/learning/incidents",
            headers=headers,
            json={
                "title": f"HotelRunner rate push timeout again {uuid.uuid4().hex[:6]}",
                "description": "Another provider timeout with hotelrunner rate push",
                "severity": "P2",
                "affected_service": "channel_manager",
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        recurrence = data2["recurrence"]
        # The RCA workflow sets status to "postmortem" which qualifies for recurrence detection
        assert recurrence["is_recurrence"] is True
        assert incident1_id in recurrence["previous_incident_ids"]


@pytest.mark.asyncio
async def test_learning_dashboard():
    """Learning dashboard should return metrics."""
    headers = await get_auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{API_URL}/api/ops/learning/dashboard",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_incidents" in data
        assert "recurrence_rate" in data
        assert "never_again_rules_total" in data
