"""
P1 Tests: Room Move History Bug Fix & CI Guards
================================================
Tests for:
1. POST /api/pms/room-move-history - full payload with all fields
2. POST /api/pms/room-move-history - minimal payload with missing optional fields
3. Response uses canonical field names (from_room_number, to_room_number, moved_at)
4. CI guard: check_orphan_files.py exits 0
5. CI guard: check_import_boundaries.py exits 0
6. Login with demo@hotel.com / demo123 works
7. GET /api/pms/dashboard returns valid data with auth
8. GET /api/pms/bookings returns bookings list
"""
import os
import subprocess
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback for local testing
    BASE_URL = "https://saas-pms-preview.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestAuthAndBasicEndpoints:
    """Test authentication and basic PMS endpoints."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for demo user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        return data["access_token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Return headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_login_with_demo_credentials(self):
        """Test login with demo@hotel.com / demo123 works."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Missing access_token"
        assert "user" in data, "Missing user info"
        assert data["user"]["email"] == TEST_EMAIL, "Email mismatch"
        print(f"\n[AUTH] Login successful for {TEST_EMAIL}")

    def test_dashboard_returns_valid_data(self, auth_headers):
        """Test GET /api/pms/dashboard returns valid data with auth."""
        response = requests.get(
            f"{BASE_URL}/api/pms/dashboard",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        # Dashboard should have some expected fields
        assert isinstance(data, dict), "Dashboard should return a dict"
        print(f"\n[DASHBOARD] Returned {len(data)} keys")

    def test_bookings_returns_list(self, auth_headers):
        """Test GET /api/pms/bookings returns bookings list."""
        response = requests.get(
            f"{BASE_URL}/api/pms/bookings",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Bookings failed: {response.text}"
        data = response.json()
        # Should be a list or dict with bookings
        if isinstance(data, dict):
            assert "bookings" in data or isinstance(data.get("bookings"), list), (
                f"Unexpected bookings response: {data}"
            )
        print(f"\n[BOOKINGS] Returned data type: {type(data).__name__}")


class TestRoomMoveHistoryEndpoint:
    """Test POST /api/pms/room-move-history endpoint."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for demo user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Return headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_room_move_history_full_payload(self, auth_headers):
        """Test POST /api/pms/room-move-history with full payload."""
        payload = {
            "booking_id": f"test-booking-{uuid.uuid4().hex[:8]}",
            "old_room": "101",
            "new_room": "102",
            "from_room_id": f"room-{uuid.uuid4().hex[:8]}",
            "to_room_id": f"room-{uuid.uuid4().hex[:8]}",
            "reason": "Guest requested upgrade",
            "moved_by": "Test User",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = requests.post(
            f"{BASE_URL}/api/pms/room-move-history",
            json=payload,
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code in (200, 201), f"Room move history failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "history" in data, f"Missing 'history' in response: {data}"
        history = data["history"]
        
        # Verify canonical field names are used
        assert "from_room_number" in history, f"Missing 'from_room_number': {history}"
        assert "to_room_number" in history, f"Missing 'to_room_number': {history}"
        assert "moved_at" in history, f"Missing 'moved_at': {history}"
        
        # Verify values match input
        assert history["from_room_number"] == payload["old_room"], (
            f"from_room_number mismatch: expected {payload['old_room']}, got {history['from_room_number']}"
        )
        assert history["to_room_number"] == payload["new_room"], (
            f"to_room_number mismatch: expected {payload['new_room']}, got {history['to_room_number']}"
        )
        assert history["booking_id"] == payload["booking_id"], "booking_id mismatch"
        assert history["reason"] == payload["reason"], "reason mismatch"
        
        print(f"\n[ROOM MOVE FULL] Created history with canonical fields: "
              f"from={history['from_room_number']}, to={history['to_room_number']}")

    def test_room_move_history_minimal_payload(self, auth_headers):
        """Test POST /api/pms/room-move-history with minimal payload (missing optional fields)."""
        payload = {
            "booking_id": f"test-booking-{uuid.uuid4().hex[:8]}",
            "old_room": "201",
            "new_room": "202",
            # Missing: from_room_id, to_room_id, reason, moved_by, timestamp
        }
        response = requests.post(
            f"{BASE_URL}/api/pms/room-move-history",
            json=payload,
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code in (200, 201), f"Room move history (minimal) failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "history" in data, f"Missing 'history' in response: {data}"
        history = data["history"]
        
        # Verify canonical field names are used
        assert "from_room_number" in history, f"Missing 'from_room_number': {history}"
        assert "to_room_number" in history, f"Missing 'to_room_number': {history}"
        assert "moved_at" in history, f"Missing 'moved_at': {history}"
        
        # Verify values
        assert history["from_room_number"] == payload["old_room"], "from_room_number mismatch"
        assert history["to_room_number"] == payload["new_room"], "to_room_number mismatch"
        
        # moved_at should be auto-generated
        assert history["moved_at"] is not None, "moved_at should be auto-generated"
        
        print(f"\n[ROOM MOVE MINIMAL] Created history with auto-generated moved_at: {history['moved_at']}")

    def test_room_move_history_response_uses_canonical_field_names(self, auth_headers):
        """Verify response uses canonical field names (from_room_number, to_room_number, moved_at)."""
        payload = {
            "booking_id": f"test-booking-{uuid.uuid4().hex[:8]}",
            "old_room": "301",
            "new_room": "302",
        }
        response = requests.post(
            f"{BASE_URL}/api/pms/room-move-history",
            json=payload,
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code in (200, 201), f"Room move history failed: {response.text}"
        data = response.json()
        history = data["history"]
        
        # These are the canonical field names expected by the reader in reservation_detail.py
        canonical_fields = ["from_room_number", "to_room_number", "moved_at"]
        for field in canonical_fields:
            assert field in history, f"Missing canonical field '{field}' in response: {history}"
        
        # Verify old field names are NOT used
        old_field_names = ["old_room", "new_room", "timestamp"]
        for old_field in old_field_names:
            assert old_field not in history, (
                f"Response should NOT contain old field name '{old_field}': {history}"
            )
        
        print(f"\n[CANONICAL FIELDS] Response uses correct field names: {canonical_fields}")


class TestCIGuards:
    """Test CI guard scripts exit with code 0."""

    def test_check_orphan_files_exits_zero(self):
        """Test python scripts/check_orphan_files.py exits 0."""
        result = subprocess.run(
            ["python", "scripts/check_orphan_files.py"],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"check_orphan_files.py failed with code {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        print(f"\n[CI GUARD] check_orphan_files.py: {result.stdout.strip()}")

    def test_check_import_boundaries_exits_zero(self):
        """Test python scripts/check_import_boundaries.py exits 0 with no known exceptions."""
        result = subprocess.run(
            ["python", "scripts/check_import_boundaries.py"],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"check_import_boundaries.py failed with code {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # Verify no known exceptions message (should be clean)
        assert "known exception" not in result.stdout.lower() or "0 known" in result.stdout.lower(), (
            f"Unexpected known exceptions in output: {result.stdout}"
        )
        print(f"\n[CI GUARD] check_import_boundaries.py: {result.stdout.strip()}")


class TestHealthEndpoint:
    """Test health endpoint."""

    def test_health_endpoint_returns_200(self):
        """Test /health endpoint returns 200."""
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        print(f"\n[HEALTH] /health returned 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
