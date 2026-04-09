"""
CI Load Tests & Ruff UP Auto-fix Verification
==============================================
Tests to verify:
1. Backend health check endpoint /health/ returns 200
2. Login endpoint POST /api/auth/login with demo@hotel.com / demo123 returns access_token
3. Dashboard endpoint GET /api/pms/dashboard with auth returns 200
4. CI load tests pass: 11 tests with @pytest.mark.ci_load marker
5. Ruff linting passes: 0 errors with UP rules
6. CI YAML is valid: load-test job exists with correct dependencies
7. Booking creation via API still works (POST /api/pms/bookings)
8. Room availability endpoint GET /api/pms/rooms/availability returns 200
"""
import os
import subprocess
import pytest
import requests
import yaml

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://channel-sync-15.preview.emergentagent.com").rstrip("/")


class TestHealthAndAuth:
    """Test health check and authentication endpoints."""

    def test_health_endpoint_returns_200(self):
        """Health endpoint /health/ returns 200."""
        # Note: /health/ is not prefixed with /api in the router
        # External URL may route /health/ to frontend, so use internal URL
        response = requests.get("http://localhost:8001/health/", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        data = response.json()
        assert data.get("status") == "healthy", f"Health status not healthy: {data}"

    def test_login_returns_access_token(self):
        """Login with demo@hotel.com / demo123 returns access_token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=10,
        )
        assert response.status_code == 200, f"Login failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        assert len(data["access_token"]) > 0, "access_token is empty"


class TestAuthenticatedEndpoints:
    """Test endpoints that require authentication."""

    @pytest.fixture
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@hotel.com", "password": "demo123"},
            timeout=10,
        )
        if response.status_code != 200:
            pytest.skip("Authentication failed")
        return response.json()["access_token"]

    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {auth_token}"}

    def test_dashboard_returns_200(self, auth_headers):
        """Dashboard endpoint GET /api/pms/dashboard returns 200."""
        response = requests.get(
            f"{BASE_URL}/api/pms/dashboard",
            headers=auth_headers,
            timeout=10,
        )
        assert response.status_code == 200, f"Dashboard failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "total_rooms" in data, f"Dashboard missing total_rooms: {data}"

    def test_room_availability_returns_200(self, auth_headers):
        """Room availability endpoint GET /api/pms/rooms/availability returns 200."""
        response = requests.get(
            f"{BASE_URL}/api/pms/rooms/availability",
            params={"check_in": "2026-05-01", "check_out": "2026-05-03"},
            headers=auth_headers,
            timeout=10,
        )
        assert response.status_code == 200, f"Availability failed: {response.status_code} - {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Availability should return list: {type(data)}"

    def test_booking_creation_works(self, auth_headers):
        """Booking creation via API still works (POST /api/pms/bookings)."""
        # First get a guest and room
        guests_resp = requests.get(
            f"{BASE_URL}/api/pms/guests",
            headers=auth_headers,
            timeout=10,
        )
        rooms_resp = requests.get(
            f"{BASE_URL}/api/pms/rooms",
            headers=auth_headers,
            timeout=10,
        )
        
        if guests_resp.status_code != 200 or rooms_resp.status_code != 200:
            pytest.skip("Could not fetch guests or rooms")
        
        guests = guests_resp.json()
        rooms = rooms_resp.json()
        
        if not guests or not rooms:
            pytest.skip("No guests or rooms available")
        
        # Find an available room
        available_room = None
        for room in rooms:
            if room.get("status") == "available":
                available_room = room
                break
        
        if not available_room:
            available_room = rooms[0]  # Use first room if none available
        
        guest = guests[0]
        
        # Create booking
        import uuid
        booking_payload = {
            "guest_id": guest["id"],
            "room_id": available_room["id"],
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
            "adults": 1,
            "children": 0,
            "guests_count": 1,
            "status": "confirmed",
            "total_amount": 200,
            "source": "test_verification",
        }
        
        response = requests.post(
            f"{BASE_URL}/api/pms/bookings",
            json=booking_payload,
            headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            timeout=10,
        )
        
        # Accept 200, 201, or 409 (conflict if room already booked)
        assert response.status_code in (200, 201, 409), (
            f"Booking creation failed: {response.status_code} - {response.text}"
        )


class TestCILoadTests:
    """Verify CI load tests pass."""

    def test_ci_load_tests_pass(self):
        """CI load tests pass: run pytest load_tests/ -m ci_load."""
        result = subprocess.run(
            ["python", "-m", "pytest", "load_tests/", "-m", "ci_load", "-v", "--timeout=60"],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        # Check for 11 passed tests
        assert "11 passed" in result.stdout, (
            f"Expected 11 passed tests, got:\n{result.stdout}\n{result.stderr}"
        )
        assert result.returncode == 0, (
            f"CI load tests failed with code {result.returncode}:\n{result.stdout}\n{result.stderr}"
        )


class TestRuffLinting:
    """Verify ruff linting passes."""

    def test_ruff_check_passes(self):
        """Ruff linting passes: run ruff check . in /app/backend."""
        result = subprocess.run(
            ["ruff", "check", "."],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        assert result.returncode == 0, (
            f"Ruff check failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "All checks passed" in result.stdout or result.stdout.strip() == "", (
            f"Ruff check had issues:\n{result.stdout}"
        )


class TestCIYAMLValidation:
    """Verify CI YAML is valid."""

    def test_ci_yaml_load_test_job_exists(self):
        """CI YAML is valid: load-test job exists with correct dependencies."""
        with open("/app/.github/workflows/ci-cd.yml") as f:
            ci_config = yaml.safe_load(f)
        
        jobs = ci_config.get("jobs", {})
        
        # Verify load-test job exists
        assert "load-test" in jobs, f"load-test job not found. Jobs: {list(jobs.keys())}"
        
        load_test_job = jobs["load-test"]
        
        # Verify load-test depends on backend-lint
        needs = load_test_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "backend-lint" in needs, f"load-test should depend on backend-lint. Needs: {needs}"
        
        # Verify timeout is set
        assert load_test_job.get("timeout-minutes") == 10, (
            f"load-test timeout should be 10 minutes: {load_test_job.get('timeout-minutes')}"
        )
        
        # Verify docker-build depends on load-test (hard gate)
        docker_build = jobs.get("docker-build", {})
        docker_needs = docker_build.get("needs", [])
        if isinstance(docker_needs, str):
            docker_needs = [docker_needs]
        assert "load-test" in docker_needs, (
            f"docker-build should depend on load-test (hard gate). Needs: {docker_needs}"
        )

    def test_ci_yaml_has_ci_load_marker_in_pytest_command(self):
        """CI YAML load-test job uses -m ci_load marker."""
        with open("/app/.github/workflows/ci-cd.yml") as f:
            content = f.read()
        
        assert "-m ci_load" in content, "CI YAML should use -m ci_load marker for load tests"


class TestPyprojectConfig:
    """Verify pyproject.toml configuration."""

    def test_ci_load_marker_defined(self):
        """ci_load marker is defined in pyproject.toml."""
        with open("/app/backend/pyproject.toml") as f:
            content = f.read()
        
        assert "ci_load" in content, "ci_load marker should be defined in pyproject.toml"

    def test_up_rules_in_ruff_config(self):
        """UP rules are in ruff select list."""
        with open("/app/backend/pyproject.toml") as f:
            content = f.read()
        
        # Check for UP rules
        up_rules = ["UP006", "UP012", "UP015", "UP017", "UP024", "UP034", "UP041", "UP045"]
        for rule in up_rules:
            assert rule in content, f"UP rule {rule} should be in ruff select list"
