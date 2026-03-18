"""
Night Audit Financial Module API Tests
Tests for the 4 new financial reporting endpoints:
- GET /api/night-audit/financial-summary
- GET /api/night-audit/payment-reconciliation
- GET /api/night-audit/integrity-check
- GET /api/night-audit/financial-report
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token - note: returns 'access_token' not 'token'."""
    response = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    token = data.get("access_token")
    assert token, "No access_token in login response"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


# ═══════════════════════════════════════════════════════════════════
# Financial Summary Endpoint Tests
# ═══════════════════════════════════════════════════════════════════

class TestFinancialSummary:
    """Tests for GET /api/night-audit/financial-summary"""

    def test_returns_200(self, api_client, auth_headers):
        """GET /api/night-audit/financial-summary returns 200."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-summary",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_structure(self, api_client, auth_headers):
        """Financial summary returns correct JSON structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-summary",
            headers=auth_headers
        )
        data = response.json()
        
        # Check top-level keys
        assert "business_date" in data, "Missing business_date"
        assert "revenue" in data, "Missing revenue"
        assert "tax" in data, "Missing tax"
        assert "payments" in data, "Missing payments"
        assert "open_folios" in data, "Missing open_folios"
        assert "net_position" in data, "Missing net_position"
        assert "audit_status" in data, "Missing audit_status"

    def test_revenue_structure(self, api_client, auth_headers):
        """Financial summary revenue has correct structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-summary",
            headers=auth_headers
        )
        data = response.json()
        
        revenue = data["revenue"]
        assert "total" in revenue, "Revenue missing total"
        assert "total_with_tax" in revenue, "Revenue missing total_with_tax"
        assert "by_category" in revenue, "Revenue missing by_category"
        assert "charges_count" in revenue, "Revenue missing charges_count"
        assert isinstance(revenue["by_category"], dict), "by_category should be dict"

    def test_tax_structure(self, api_client, auth_headers):
        """Financial summary tax has correct structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-summary",
            headers=auth_headers
        )
        data = response.json()
        
        tax = data["tax"]
        assert "total" in tax, "Tax missing total"
        assert "breakdown" in tax, "Tax missing breakdown"
        breakdown = tax["breakdown"]
        assert "vat" in breakdown, "Tax breakdown missing vat"
        assert "accommodation_tax" in breakdown, "Tax breakdown missing accommodation_tax"

    def test_payments_structure(self, api_client, auth_headers):
        """Financial summary payments has correct structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-summary",
            headers=auth_headers
        )
        data = response.json()
        
        payments = data["payments"]
        assert "total" in payments, "Payments missing total"
        assert "by_method" in payments, "Payments missing by_method"
        assert "payments_count" in payments, "Payments missing payments_count"
        assert isinstance(payments["by_method"], dict), "by_method should be dict"

    def test_open_folios_structure(self, api_client, auth_headers):
        """Financial summary open_folios has correct structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-summary",
            headers=auth_headers
        )
        data = response.json()
        
        open_folios = data["open_folios"]
        assert "count" in open_folios, "open_folios missing count"
        assert "balance" in open_folios, "open_folios missing balance"
        balance = open_folios["balance"]
        assert "total" in balance, "Balance missing total"
        assert "receivable" in balance, "Balance missing receivable"
        assert "overpayment" in balance, "Balance missing overpayment"

    def test_with_date_param(self, api_client, auth_headers):
        """Financial summary accepts date query parameter."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-summary?date=2026-03-10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["business_date"] == "2026-03-10"

    def test_requires_auth(self, api_client):
        """Financial summary returns 401/403 without auth."""
        response = api_client.get(f"{BASE_URL}/api/night-audit/financial-summary")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


# ═══════════════════════════════════════════════════════════════════
# Payment Reconciliation Endpoint Tests
# ═══════════════════════════════════════════════════════════════════

class TestPaymentReconciliation:
    """Tests for GET /api/night-audit/payment-reconciliation"""

    def test_returns_200(self, api_client, auth_headers):
        """GET /api/night-audit/payment-reconciliation returns 200."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/payment-reconciliation",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_structure(self, api_client, auth_headers):
        """Payment reconciliation returns correct JSON structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/payment-reconciliation",
            headers=auth_headers
        )
        data = response.json()
        
        # Check top-level keys
        assert "business_date" in data, "Missing business_date"
        assert "charges_total" in data, "Missing charges_total"
        assert "charges_count" in data, "Missing charges_count"
        assert "payments_total" in data, "Missing payments_total"
        assert "payments_count" in data, "Missing payments_count"
        assert "variance" in data, "Missing variance"
        assert "is_balanced" in data, "Missing is_balanced"
        assert "discrepancies" in data, "Missing discrepancies"
        assert "discrepancy_count" in data, "Missing discrepancy_count"

    def test_discrepancies_is_list(self, api_client, auth_headers):
        """Payment reconciliation discrepancies is a list."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/payment-reconciliation",
            headers=auth_headers
        )
        data = response.json()
        assert isinstance(data["discrepancies"], list), "discrepancies should be a list"

    def test_has_high_balance_info(self, api_client, auth_headers):
        """Payment reconciliation includes high balance folio info."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/payment-reconciliation",
            headers=auth_headers
        )
        data = response.json()
        assert "high_balance_folios" in data, "Missing high_balance_folios"
        assert "high_balance_count" in data, "Missing high_balance_count"
        assert isinstance(data["high_balance_folios"], list), "high_balance_folios should be a list"

    def test_with_date_param(self, api_client, auth_headers):
        """Payment reconciliation accepts date query parameter."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/payment-reconciliation?date=2026-03-10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["business_date"] == "2026-03-10"

    def test_is_balanced_is_boolean(self, api_client, auth_headers):
        """Payment reconciliation is_balanced is a boolean."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/payment-reconciliation",
            headers=auth_headers
        )
        data = response.json()
        assert isinstance(data["is_balanced"], bool), "is_balanced should be boolean"

    def test_requires_auth(self, api_client):
        """Payment reconciliation returns 401/403 without auth."""
        response = api_client.get(f"{BASE_URL}/api/night-audit/payment-reconciliation")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


# ═══════════════════════════════════════════════════════════════════
# Integrity Check Endpoint Tests
# ═══════════════════════════════════════════════════════════════════

class TestIntegrityCheck:
    """Tests for GET /api/night-audit/integrity-check"""

    def test_returns_200(self, api_client, auth_headers):
        """GET /api/night-audit/integrity-check returns 200."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/integrity-check",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_structure(self, api_client, auth_headers):
        """Integrity check returns correct JSON structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/integrity-check",
            headers=auth_headers
        )
        data = response.json()
        
        # Check top-level keys
        assert "business_date" in data, "Missing business_date"
        assert "checks" in data, "Missing checks"
        assert "summary" in data, "Missing summary"

    def test_checks_is_array(self, api_client, auth_headers):
        """Integrity check checks is an array."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/integrity-check",
            headers=auth_headers
        )
        data = response.json()
        assert isinstance(data["checks"], list), "checks should be a list"

    def test_has_check_items(self, api_client, auth_headers):
        """Integrity check array has check items with status."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/integrity-check",
            headers=auth_headers
        )
        data = response.json()
        
        checks = data["checks"]
        assert len(checks) > 0, "Should have at least one check"
        
        # Verify each check has required fields
        for check in checks:
            assert "check" in check, "Check missing 'check' field"
            assert "label" in check, "Check missing 'label' field"
            assert "status" in check, "Check missing 'status' field"
            assert "detail" in check, "Check missing 'detail' field"
            assert check["status"] in ["pass", "warning", "error", "fail"], \
                f"Invalid status: {check['status']}"

    def test_summary_structure(self, api_client, auth_headers):
        """Integrity check summary has correct structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/integrity-check",
            headers=auth_headers
        )
        data = response.json()
        
        summary = data["summary"]
        assert "total" in summary, "Summary missing total"
        assert "passed" in summary, "Summary missing passed"
        assert "warnings" in summary, "Summary missing warnings"
        assert "failures" in summary, "Summary missing failures"
        assert "overall_status" in summary, "Summary missing overall_status"
        
        # Verify overall_status is valid
        assert summary["overall_status"] in ["pass", "warning", "fail"], \
            f"Invalid overall_status: {summary['overall_status']}"

    def test_with_date_param(self, api_client, auth_headers):
        """Integrity check accepts date query parameter."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/integrity-check?date=2026-03-10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["business_date"] == "2026-03-10"

    def test_requires_auth(self, api_client):
        """Integrity check returns 401/403 without auth."""
        response = api_client.get(f"{BASE_URL}/api/night-audit/integrity-check")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


# ═══════════════════════════════════════════════════════════════════
# Financial Report Endpoint Tests
# ═══════════════════════════════════════════════════════════════════

class TestFinancialReport:
    """Tests for GET /api/night-audit/financial-report"""

    def test_returns_200(self, api_client, auth_headers):
        """GET /api/night-audit/financial-report returns 200 with valid dates."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01&end_date=2026-03-18",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_structure(self, api_client, auth_headers):
        """Financial report returns correct JSON structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01&end_date=2026-03-18",
            headers=auth_headers
        )
        data = response.json()
        
        # Check top-level keys
        assert "start_date" in data, "Missing start_date"
        assert "end_date" in data, "Missing end_date"
        assert "summary" in data, "Missing summary"
        assert "revenue_by_category" in data, "Missing revenue_by_category"
        assert "revenue_by_date" in data, "Missing revenue_by_date"
        assert "payments_by_method" in data, "Missing payments_by_method"
        assert "audit_runs" in data, "Missing audit_runs"

    def test_summary_structure(self, api_client, auth_headers):
        """Financial report summary has correct structure."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01&end_date=2026-03-18",
            headers=auth_headers
        )
        data = response.json()
        
        summary = data["summary"]
        assert "total_revenue" in summary, "Summary missing total_revenue"
        assert "total_tax" in summary, "Summary missing total_tax"
        assert "total_with_tax" in summary, "Summary missing total_with_tax"
        assert "total_payments" in summary, "Summary missing total_payments"
        assert "net_position" in summary, "Summary missing net_position"
        assert "total_bookings" in summary, "Summary missing total_bookings"
        assert "total_rooms" in summary, "Summary missing total_rooms"

    def test_dates_in_response(self, api_client, auth_headers):
        """Financial report includes the queried date range."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01&end_date=2026-03-18",
            headers=auth_headers
        )
        data = response.json()
        assert data["start_date"] == "2026-03-01"
        assert data["end_date"] == "2026-03-18"

    def test_revenue_by_date_is_list(self, api_client, auth_headers):
        """Financial report revenue_by_date is a list."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01&end_date=2026-03-18",
            headers=auth_headers
        )
        data = response.json()
        assert isinstance(data["revenue_by_date"], list), "revenue_by_date should be a list"

    def test_audit_runs_is_list(self, api_client, auth_headers):
        """Financial report audit_runs is a list."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01&end_date=2026-03-18",
            headers=auth_headers
        )
        data = response.json()
        assert isinstance(data["audit_runs"], list), "audit_runs should be a list"

    def test_requires_start_date(self, api_client, auth_headers):
        """Financial report returns 422 without start_date."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?end_date=2026-03-18",
            headers=auth_headers
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_requires_end_date(self, api_client, auth_headers):
        """Financial report returns 422 without end_date."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01",
            headers=auth_headers
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_requires_auth(self, api_client):
        """Financial report returns 401/403 without auth."""
        response = api_client.get(
            f"{BASE_URL}/api/night-audit/financial-report?start_date=2026-03-01&end_date=2026-03-18"
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
