"""
Lockdown Router API Tests
=========================

Tests for Core Lockdown endpoints via HTTP:
- GET /api/lockdown/status — System lockdown health check
- GET /api/lockdown/providers/capabilities — Provider capability matrix
- GET /api/lockdown/reconciliation/truth-table — Drift resolution policies
- GET /api/lockdown/health/mapping — Mapping health score
- GET /api/lockdown/metrics/ingest — Ingest pipeline metrics
- GET /api/lockdown/metrics/lineage — Reservation lineage metrics
- GET /api/lockdown/metrics/reconciliation — Reconciliation case metrics
- GET /api/lockdown/trace/reservation/{ext_id} — Reservation traceability
- GET /api/folio/booking/{booking_id} — Folio endpoint (bug fix)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="VITE_BACKEND_URL not set - integration tests require a running server"
)

# ── Auth Fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Login and get auth token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"},
    )
    if response.status_code != 200:
        pytest.skip(f"Auth failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture
def auth_headers(auth_token):
    """Auth headers for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


# ══════════════════════════════════════════════════════════════════════
# 1. SYSTEM LOCKDOWN STATUS
# ══════════════════════════════════════════════════════════════════════

class TestLockdownStatus:
    """Tests for GET /api/lockdown/status endpoint."""

    def test_status_returns_200(self, auth_headers):
        """Status endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/status",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_status_structure(self, auth_headers):
        """Status should have status, checks, and timestamp fields."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/status",
            headers=auth_headers,
        )
        data = response.json()
        
        # Top-level fields
        assert "status" in data, "Missing 'status' field"
        assert "checks" in data, "Missing 'checks' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # Status should be either healthy or degraded
        assert data["status"] in ("healthy", "degraded"), f"Unexpected status: {data['status']}"

    def test_status_checks_structure(self, auth_headers):
        """Status.checks should have ingest, mapping, reconciliation."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/status",
            headers=auth_headers,
        )
        checks = response.json().get("checks", {})
        
        assert "ingest" in checks, "Missing checks.ingest"
        assert "mapping" in checks, "Missing checks.mapping"
        assert "reconciliation" in checks, "Missing checks.reconciliation"
        
        # Each check should have status
        for check_name in ["ingest", "mapping", "reconciliation"]:
            assert "status" in checks[check_name], f"Missing {check_name}.status"


# ══════════════════════════════════════════════════════════════════════
# 2. PROVIDER CAPABILITIES
# ══════════════════════════════════════════════════════════════════════

class TestProviderCapabilities:
    """Tests for GET /api/lockdown/providers/capabilities endpoint."""

    def test_capabilities_returns_200(self, auth_headers):
        """Capabilities endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/providers/capabilities",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_capabilities_has_providers(self, auth_headers):
        """Response should have providers array."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/providers/capabilities",
            headers=auth_headers,
        )
        data = response.json()
        
        assert "providers" in data, "Missing 'providers' field"
        assert isinstance(data["providers"], list), "providers should be a list"
        assert len(data["providers"]) >= 2, "Should have at least exely and hotelrunner"

    def test_exely_provider_exists(self, auth_headers):
        """Exely provider should exist with correct capabilities."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/providers/capabilities",
            headers=auth_headers,
        )
        providers = response.json()["providers"]
        
        exely = next((p for p in providers if p["provider"] == "exely"), None)
        assert exely is not None, "Exely provider not found"
        assert exely["display_name"] == "Exely"
        assert exely["ari"]["push_behavior"] == "split_messages"

    def test_hotelrunner_provider_exists(self, auth_headers):
        """HotelRunner provider should exist with correct capabilities."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/providers/capabilities",
            headers=auth_headers,
        )
        providers = response.json()["providers"]
        
        hotelrunner = next((p for p in providers if p["provider"] == "hotelrunner"), None)
        assert hotelrunner is not None, "HotelRunner provider not found"
        assert hotelrunner["display_name"] == "HotelRunner"
        assert hotelrunner["ari"]["push_behavior"] == "single_message"

    def test_provider_structure(self, auth_headers):
        """Each provider should have complete structure."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/providers/capabilities",
            headers=auth_headers,
        )
        providers = response.json()["providers"]
        
        for provider in providers:
            # Required fields
            assert "provider" in provider
            assert "display_name" in provider
            assert "reservation" in provider
            assert "ari" in provider
            assert "consistency" in provider
            assert "rate_limits" in provider
            assert "retry_policy" in provider
            assert "error_classes" in provider


# ══════════════════════════════════════════════════════════════════════
# 3. RECONCILIATION TRUTH TABLE
# ══════════════════════════════════════════════════════════════════════

class TestReconciliationTruthTable:
    """Tests for GET /api/lockdown/reconciliation/truth-table endpoint."""

    def test_truth_table_returns_200(self, auth_headers):
        """Truth table endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/reconciliation/truth-table",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_truth_table_has_entries(self, auth_headers):
        """Truth table should have drift type entries."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/reconciliation/truth-table",
            headers=auth_headers,
        )
        data = response.json()
        
        assert "truth_table" in data, "Missing 'truth_table' field"
        assert isinstance(data["truth_table"], list), "truth_table should be a list"
        assert len(data["truth_table"]) >= 7, "Should have all drift types defined"

    def test_truth_table_entry_structure(self, auth_headers):
        """Each entry should have drift_type, resolution, gold_source, etc."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/reconciliation/truth-table",
            headers=auth_headers,
        )
        entries = response.json()["truth_table"]
        
        for entry in entries:
            assert "drift_type" in entry, "Missing drift_type"
            assert "resolution" in entry, "Missing resolution"
            assert "gold_source" in entry, "Missing gold_source"
            assert "description" in entry, "Missing description"
            assert "can_auto_heal" in entry, "Missing can_auto_heal"

    def test_known_drift_types_exist(self, auth_headers):
        """Known drift types should exist in truth table."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/reconciliation/truth-table",
            headers=auth_headers,
        )
        entries = response.json()["truth_table"]
        drift_types = [e["drift_type"] for e in entries]
        
        expected = [
            "missing_locally", "missing_remotely", "stale_locally",
            "stale_remotely", "status_mismatch", "financial_mismatch",
            "payload_mismatch",
        ]
        for dt in expected:
            assert dt in drift_types, f"Missing drift type: {dt}"


# ══════════════════════════════════════════════════════════════════════
# 4. MAPPING HEALTH
# ══════════════════════════════════════════════════════════════════════

class TestMappingHealth:
    """Tests for GET /api/lockdown/health/mapping endpoint."""

    def test_mapping_health_returns_200(self, auth_headers):
        """Mapping health endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/health/mapping",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_mapping_health_structure(self, auth_headers):
        """Response should have mapping_health and overall_production_ready."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/health/mapping",
            headers=auth_headers,
        )
        data = response.json()
        
        assert "mapping_health" in data, "Missing 'mapping_health' field"
        assert "overall_production_ready" in data, "Missing 'overall_production_ready'"
        assert isinstance(data["mapping_health"], list), "mapping_health should be a list"

    def test_mapping_health_with_provider_filter(self, auth_headers):
        """Should accept provider query parameter."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/health/mapping?provider=exely",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should return health for exely only
        assert len(data["mapping_health"]) <= 1


# ══════════════════════════════════════════════════════════════════════
# 5. INGEST METRICS
# ══════════════════════════════════════════════════════════════════════

class TestIngestMetrics:
    """Tests for GET /api/lockdown/metrics/ingest endpoint."""

    def test_ingest_metrics_returns_200(self, auth_headers):
        """Ingest metrics endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/ingest",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_ingest_metrics_structure(self, auth_headers):
        """Response should have period_hours, since, totals, rates, decisions."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/ingest",
            headers=auth_headers,
        )
        data = response.json()
        
        assert "period_hours" in data, "Missing 'period_hours'"
        assert "since" in data, "Missing 'since'"
        assert "totals" in data, "Missing 'totals'"
        assert "rates" in data, "Missing 'rates'"
        assert "decisions" in data, "Missing 'decisions'"

    def test_ingest_metrics_totals_structure(self, auth_headers):
        """totals should have event counts."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/ingest",
            headers=auth_headers,
        )
        totals = response.json()["totals"]
        
        assert "total_events" in totals
        assert "processed" in totals
        assert "duplicate" in totals
        assert "stale" in totals
        assert "failed" in totals

    def test_ingest_metrics_rates_structure(self, auth_headers):
        """rates should have percentage metrics."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/ingest",
            headers=auth_headers,
        )
        rates = response.json()["rates"]
        
        assert "success_rate_pct" in rates
        assert "duplicate_rate_pct" in rates
        assert "failure_rate_pct" in rates

    def test_ingest_metrics_hours_param(self, auth_headers):
        """Should accept hours query parameter."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/ingest?hours=48",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_hours"] == 48


# ══════════════════════════════════════════════════════════════════════
# 6. LINEAGE METRICS
# ══════════════════════════════════════════════════════════════════════

class TestLineageMetrics:
    """Tests for GET /api/lockdown/metrics/lineage endpoint."""

    def test_lineage_metrics_returns_200(self, auth_headers):
        """Lineage metrics endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/lineage",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_lineage_metrics_structure(self, auth_headers):
        """Response should have total_lineages, by_status, by_provider, etc."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/lineage",
            headers=auth_headers,
        )
        data = response.json()
        
        assert "total_lineages" in data, "Missing 'total_lineages'"
        assert "by_status" in data, "Missing 'by_status'"
        assert "by_provider" in data, "Missing 'by_provider'"
        assert "reconciled" in data, "Missing 'reconciled'"
        assert "unreconciled" in data, "Missing 'unreconciled'"


# ══════════════════════════════════════════════════════════════════════
# 7. RECONCILIATION METRICS
# ══════════════════════════════════════════════════════════════════════

class TestReconciliationMetrics:
    """Tests for GET /api/lockdown/metrics/reconciliation endpoint."""

    def test_reconciliation_metrics_returns_200(self, auth_headers):
        """Reconciliation metrics endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/reconciliation",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_reconciliation_metrics_has_oldest_age(self, auth_headers):
        """Response should have oldest_unresolved_age_hours field."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/metrics/reconciliation",
            headers=auth_headers,
        )
        data = response.json()
        
        # This field should exist (can be None if no open cases)
        assert "oldest_unresolved_age_hours" in data, "Missing 'oldest_unresolved_age_hours'"


# ══════════════════════════════════════════════════════════════════════
# 8. RESERVATION TRACEABILITY
# ══════════════════════════════════════════════════════════════════════

class TestReservationTrace:
    """Tests for GET /api/lockdown/trace/reservation/{ext_id} endpoint."""

    def test_trace_returns_200(self, auth_headers):
        """Trace endpoint should return 200 even for non-existent reservation."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/trace/reservation/TEST-NONEXISTENT-123",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_trace_structure(self, auth_headers):
        """Response should have external_reservation_id and trace object."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/trace/reservation/TEST-NONEXISTENT-123",
            headers=auth_headers,
        )
        data = response.json()
        
        assert "external_reservation_id" in data
        assert "trace" in data
        assert data["external_reservation_id"] == "TEST-NONEXISTENT-123"

    def test_trace_substructure(self, auth_headers):
        """trace object should have raw_events, lineage, reconciliation_cases."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/trace/reservation/TEST-NONEXISTENT-123",
            headers=auth_headers,
        )
        trace = response.json()["trace"]
        
        assert "raw_events" in trace, "Missing trace.raw_events"
        assert "lineage" in trace, "Missing trace.lineage"
        assert "reconciliation_cases" in trace, "Missing trace.reconciliation_cases"

    def test_trace_with_provider_filter(self, auth_headers):
        """Should accept provider query parameter."""
        response = requests.get(
            f"{BASE_URL}/api/lockdown/trace/reservation/TEST-123?provider=exely",
            headers=auth_headers,
        )
        assert response.status_code == 200


# ══════════════════════════════════════════════════════════════════════
# 9. FOLIO BY BOOKING (Bug Fix Verification)
# ══════════════════════════════════════════════════════════════════════

class TestFolioByBooking:
    """Tests for GET /api/folio/booking/{booking_id} endpoint (bug fix)."""

    def test_folio_by_booking_returns_200(self, auth_headers):
        """Folio by booking endpoint should return 200."""
        response = requests.get(
            f"{BASE_URL}/api/folio/booking/TEST-BOOKING-123",
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"

    def test_folio_by_booking_returns_array(self, auth_headers):
        """Response should be an array of folios."""
        response = requests.get(
            f"{BASE_URL}/api/folio/booking/TEST-BOOKING-123",
            headers=auth_headers,
        )
        data = response.json()
        
        assert isinstance(data, list), "Response should be an array"
        # For non-existent booking, should return empty array
        # This is the expected behavior for the folio bug fix


# ══════════════════════════════════════════════════════════════════════
# 10. AUTH REQUIREMENT TESTS
# ══════════════════════════════════════════════════════════════════════

class TestAuthRequirement:
    """Tests that endpoints require authentication."""

    def test_lockdown_status_requires_auth(self):
        """Status endpoint should return 401/403 without auth."""
        response = requests.get(f"{BASE_URL}/api/lockdown/status")
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}"

    def test_capabilities_requires_auth(self):
        """Capabilities endpoint should return 401/403 without auth."""
        response = requests.get(f"{BASE_URL}/api/lockdown/providers/capabilities")
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}"

    def test_truth_table_requires_auth(self):
        """Truth table endpoint should return 401/403 without auth."""
        response = requests.get(f"{BASE_URL}/api/lockdown/reconciliation/truth-table")
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}"

    def test_folio_by_booking_requires_auth(self):
        """Folio endpoint should return 401/403 without auth."""
        response = requests.get(f"{BASE_URL}/api/folio/booking/test-id")
        assert response.status_code in (401, 403), f"Expected 401/403, got {response.status_code}"
