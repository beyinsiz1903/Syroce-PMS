"""API Integration Tests - Unit Test Coverage for Core Endpoints
Target: 80%+ coverage for critical paths
"""
import pytest
import httpx
import asyncio
import os
import json
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8001")

# Test data
TEST_ADMIN = {"email": "demo@hotel.com", "password": "demo123"}


class TestAuth:
    """Authentication endpoint tests"""

    def test_login_success(self):
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.post("/api/auth/login", json=TEST_ADMIN)
            assert r.status_code == 200
            data = r.json()
            assert "access_token" in data
            assert data["user"]["email"] == TEST_ADMIN["email"]

    def test_login_invalid_credentials(self):
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.post("/api/auth/login", json={"email": "wrong@test.com", "password": "wrong"})
            assert r.status_code in [401, 422]

    def test_auth_me(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            token = login.json()["access_token"]
            r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200

    def test_unauthorized_access(self):
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/pms/dashboard")
            assert r.status_code in [401, 403]


class TestPMS:
    """PMS Core endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_dashboard(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/pms/dashboard", headers=self.headers)
            assert r.status_code == 200
            data = r.json()
            assert "total_rooms" in data

    def test_rooms_list(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/pms/rooms", headers=self.headers)
            assert r.status_code == 200

    def test_bookings_list(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/pms/bookings", headers=self.headers)
            assert r.status_code == 200

    def test_guests_list(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/pms/guests", headers=self.headers)
            assert r.status_code == 200


class TestSecurity2FA:
    """2FA Security endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_2fa_status(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/security/2fa/status", headers=self.headers)
            assert r.status_code == 200
            assert "enabled" in r.json()

    def test_2fa_setup(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.post("/api/security/2fa/setup", headers=self.headers)
            assert r.status_code == 200
            data = r.json()
            assert "secret" in data
            assert "qr_code" in data

    def test_2fa_tenant_policy(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/security/2fa/tenant-policy", headers=self.headers)
            assert r.status_code == 200


class TestIPAccess:
    """IP Access Control endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_list_ip_rules(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/security/ip/rules", headers=self.headers)
            assert r.status_code == 200
            assert "rules" in r.json()

    def test_create_ip_rule(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.post("/api/security/ip/rules", headers=self.headers, json={
                "ip_address": "10.0.0.1",
                "rule_type": "whitelist",
                "description": "Test rule"
            })
            assert r.status_code == 200

    def test_check_ip(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.post("/api/security/ip/check", headers=self.headers)
            assert r.status_code == 200
            assert "allowed" in r.json()


class TestGDPR:
    """GDPR/KVKK Compliance endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_compliance_status(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/gdpr/compliance-status", headers=self.headers)
            assert r.status_code == 200
            assert "compliance_score" in r.json()

    def test_retention_policy(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/gdpr/retention-policy", headers=self.headers)
            assert r.status_code == 200

    def test_dpa_list(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/gdpr/dpa", headers=self.headers)
            assert r.status_code == 200


class TestCentralOffice:
    """Central Office Dashboard tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_central_dashboard(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-office/dashboard", headers=self.headers)
            assert r.status_code == 200

    def test_properties_list(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-office/properties", headers=self.headers)
            assert r.status_code == 200

    def test_occupancy_comparison(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-office/occupancy-comparison", headers=self.headers)
            assert r.status_code == 200

    def test_revenue_report(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-office/revenue-report", headers=self.headers)
            assert r.status_code == 200

    def test_chain_alerts(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-office/alerts", headers=self.headers)
            assert r.status_code == 200


class TestCentralPricing:
    """Central Pricing Management tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_chain_rates(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-pricing/rates", headers=self.headers)
            assert r.status_code == 200

    def test_rate_templates(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-pricing/rate-templates", headers=self.headers)
            assert r.status_code == 200

    def test_rate_history(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/central-pricing/rate-history", headers=self.headers)
            assert r.status_code == 200


class TestCrossPropertyGuests:
    """Cross-Property Guest Profile tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_global_guest_search(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/cross-property/guests/search", headers=self.headers)
            assert r.status_code == 200
            assert "guests" in r.json()

    def test_loyalty_summary(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/cross-property/guests/loyalty-summary", headers=self.headers)
            assert r.status_code == 200


class TestMLModels:
    """ML/AI Model endpoint tests"""

    @pytest.fixture(autouse=True)
    def setup(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                self.token = login.json()["access_token"]
                self.headers = {"Authorization": f"Bearer {self.token}"}
            else:
                self.token = None
                self.headers = {}

    def test_ml_models_status(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/ml/models/status", headers=self.headers)
            assert r.status_code == 200
            data = r.json()
            assert "models" in data

    def test_sentiment_analysis(self):
        if not self.token:
            pytest.skip("No auth token")
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.post(
                "/api/ml/sentiment/analyze",
                headers=self.headers,
                params={"text": "This hotel was absolutely amazing! Great service and beautiful rooms."}
            )
            assert r.status_code == 200


class TestHealthAndDocs:
    """Health and documentation tests"""

    def test_health(self):
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/health")
            assert r.status_code == 200

    def test_openapi_docs(self):
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/openapi.json")
            assert r.status_code == 200
            data = r.json()
            assert "paths" in data
            assert len(data["paths"]) > 100

    def test_swagger_ui(self):
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/docs")
            assert r.status_code == 200

    def test_redoc(self):
        with httpx.Client(base_url=BASE_URL) as client:
            r = client.get("/api/redoc")
            assert r.status_code == 200


class TestRateLimiting:
    """Rate limiting tests"""

    def test_rate_limit_headers(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                token = login.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                r = client.get("/api/pms/rooms", headers=headers)
                assert "x-ratelimit-limit" in r.headers
                assert "x-ratelimit-remaining" in r.headers

    def test_system_rate_limits(self):
        with httpx.Client(base_url=BASE_URL) as client:
            login = client.post("/api/auth/login", json=TEST_ADMIN)
            if login.status_code == 200:
                token = login.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                r = client.get("/api/system/rate-limits", headers=headers)
                assert r.status_code == 200
