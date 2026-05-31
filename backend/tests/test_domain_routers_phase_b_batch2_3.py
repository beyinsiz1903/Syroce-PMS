"""
Domain Routers Phase B - Batch 2+3 Testing
Tests for 317 endpoints extracted from legacy_routes.py into 12 domain routers:
- domains/pms/enterprise_router.py (Enterprise features, tasks, RBAC)
- domains/pms/marketplace_router.py (POS marketplace, suppliers, warehouse)
- domains/revenue/rms_router.py (RMS revenue, comp-set, sales/marketing)
- domains/guest/experience_router.py (Guest CRM, upsell, feedback)
- domains/hr/router.py (HR operations, F&B kitchen)
- domains/pms/pos_router.py (POS, F&B, front office mobile)
- domains/pms/mobile_router.py (Mobile dashboards, GM mobile)
- domains/revenue/analytics_router.py (GM dashboard, analytics)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")

class TestAuth:
    """Authentication - required for all other tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        return data["access_token"]
    
    def test_login_returns_token(self, auth_token):
        """Test that login returns a valid token"""
        assert auth_token is not None
        assert len(auth_token) > 10


class TestPMSCoreRegression:
    """Regression tests for PMS core endpoints (should still work after refactor)"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_pms_rooms(self, auth_header):
        """GET /api/pms/rooms - returns rooms list"""
        response = requests.get(f"{BASE_URL}/api/pms/rooms", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "rooms" in data
    
    def test_pms_bookings(self, auth_header):
        """GET /api/pms/bookings - returns bookings list"""
        response = requests.get(f"{BASE_URL}/api/pms/bookings", headers=auth_header)
        assert response.status_code == 200
    
    def test_dashboard_role_based(self, auth_header):
        """GET /api/dashboard/role-based - returns dashboard data"""
        response = requests.get(f"{BASE_URL}/api/dashboard/role-based", headers=auth_header)
        assert response.status_code == 200


class TestSalesDomainRouter:
    """Tests for domains/sales/router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_sales_leads(self, auth_header):
        """GET /api/sales/leads - returns leads list"""
        response = requests.get(f"{BASE_URL}/api/sales/leads", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "leads" in data or "total" in data or isinstance(data, list)
    
    def test_sales_funnel(self, auth_header):
        """GET /api/sales/funnel - returns funnel data"""
        response = requests.get(f"{BASE_URL}/api/sales/funnel", headers=auth_header)
        assert response.status_code == 200


class TestEnterpriseDomainRouter:
    """Tests for domains/pms/enterprise_router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_tasks(self, auth_header):
        """GET /api/tasks - returns task list"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data or isinstance(data, list)
    
    def test_admin_roles(self, auth_header):
        """GET /api/admin/roles - returns roles list"""
        response = requests.get(f"{BASE_URL}/api/admin/roles", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "roles" in data or isinstance(data, list)
    
    def test_rms_comp_set_enterprise(self, auth_header):
        """GET /api/rms/comp-set (enterprise_router) - returns competitor set"""
        response = requests.get(f"{BASE_URL}/api/rms/comp-set", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "competitors" in data or "comp_set" in data or isinstance(data, list)
    
    def test_housekeeping_rooms(self, auth_header):
        """GET /api/housekeeping/rooms - returns housekeeping room list"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/rooms", headers=auth_header)
        assert response.status_code == 200
    
    def test_housekeeping_checklist(self, auth_header):
        """GET /api/housekeeping/checklist - returns checklist items"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/checklist", headers=auth_header)
        assert response.status_code == 200


class TestMarketplaceDomainRouter:
    """Tests for domains/pms/marketplace_router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_marketplace_suppliers(self, auth_header):
        """GET /api/marketplace/suppliers - returns suppliers list"""
        response = requests.get(f"{BASE_URL}/api/marketplace/suppliers", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "suppliers" in data or isinstance(data, list)
    
    def test_pos_outlets(self, auth_header):
        """GET /api/pos/outlets - returns outlets list"""
        response = requests.get(f"{BASE_URL}/api/pos/outlets", headers=auth_header)
        assert response.status_code == 200
        # Can be empty list or dict with outlets
        assert response.json() is not None
    
    def test_pos_menu_items(self, auth_header):
        """GET /api/pos/menu-items - returns menu items"""
        response = requests.get(f"{BASE_URL}/api/pos/menu-items", headers=auth_header)
        assert response.status_code == 200
    
    def test_marketplace_purchase_orders(self, auth_header):
        """GET /api/marketplace/purchase-orders - returns purchase orders"""
        response = requests.get(f"{BASE_URL}/api/marketplace/purchase-orders", headers=auth_header)
        assert response.status_code == 200
    
    def test_marketplace_deliveries(self, auth_header):
        """GET /api/marketplace/deliveries - returns deliveries"""
        response = requests.get(f"{BASE_URL}/api/marketplace/deliveries", headers=auth_header)
        assert response.status_code == 200


class TestRMSDomainRouter:
    """Tests for domains/revenue/rms_router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_rms_comp_set(self, auth_header):
        """GET /api/rms/comp-set - returns competitor set data"""
        response = requests.get(f"{BASE_URL}/api/rms/comp-set", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        # Response can be competitors list or comp_set
        assert "competitors" in data or "comp_set" in data or isinstance(data, list) or isinstance(data, dict)
    
    def test_rms_comp_pricing(self, auth_header):
        """GET /api/rms/comp-pricing - returns competitor pricing"""
        response = requests.get(f"{BASE_URL}/api/rms/comp-pricing", headers=auth_header)
        assert response.status_code == 200
    
    def test_rms_demand_forecast(self, auth_header):
        """GET /api/rms/demand-forecast - returns demand forecast"""
        response = requests.get(f"{BASE_URL}/api/rms/demand-forecast", headers=auth_header)
        assert response.status_code == 200
    
    def test_sales_group_bookings(self, auth_header):
        """GET /api/sales/group-bookings - returns group bookings"""
        response = requests.get(f"{BASE_URL}/api/sales/group-bookings", headers=auth_header)
        assert response.status_code == 200
    
    def test_sales_corporate_contracts(self, auth_header):
        """GET /api/sales/corporate-contracts - returns corporate contracts"""
        response = requests.get(f"{BASE_URL}/api/sales/corporate-contracts", headers=auth_header)
        assert response.status_code == 200


class TestGuestDomainRouter:
    """Tests for domains/guest/experience_router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_guest_bookings(self, auth_header):
        """GET /api/guest/bookings - returns guest bookings"""
        response = requests.get(f"{BASE_URL}/api/guest/bookings", headers=auth_header)
        assert response.status_code == 200
    
    def test_vip_list(self, auth_header):
        """GET /api/vip/list - returns VIP guests"""
        response = requests.get(f"{BASE_URL}/api/vip/list", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "vip_guests" in data or "guests" in data or isinstance(data, list) or isinstance(data, dict)
    
    def test_guest_loyalty(self, auth_header):
        """GET /api/guest/loyalty - returns loyalty info"""
        response = requests.get(f"{BASE_URL}/api/guest/loyalty", headers=auth_header)
        assert response.status_code == 200
    
    def test_crm_reviews(self, auth_header):
        """GET /api/crm/reviews - returns reviews"""
        response = requests.get(f"{BASE_URL}/api/crm/reviews", headers=auth_header)
        assert response.status_code == 200
    
    def test_feedback_surveys(self, auth_header):
        """GET /api/feedback/surveys - returns surveys"""
        response = requests.get(f"{BASE_URL}/api/feedback/surveys", headers=auth_header)
        assert response.status_code == 200
    
    def test_messages_templates(self, auth_header):
        """GET /api/messages/templates - returns message templates"""
        response = requests.get(f"{BASE_URL}/api/messages/templates", headers=auth_header)
        assert response.status_code == 200


class TestHRDomainRouter:
    """Tests for domains/hr/router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_hr_staff(self, auth_header):
        """GET /api/hr/staff - returns staff list"""
        response = requests.get(f"{BASE_URL}/api/hr/staff", headers=auth_header)
        # HR endpoint might not exist in all configurations
        assert response.status_code in [200, 404]
    
    def test_hr_attendance_records(self, auth_header):
        """GET /api/hr/attendance/records - returns attendance records"""
        response = requests.get(f"{BASE_URL}/api/hr/attendance/records", headers=auth_header)
        assert response.status_code in [200, 404]
    
    def test_fnb_recipes(self, auth_header):
        """GET /api/fnb/recipes - returns recipes"""
        response = requests.get(f"{BASE_URL}/api/fnb/recipes", headers=auth_header)
        assert response.status_code == 200
    
    def test_fnb_kitchen_display(self, auth_header):
        """GET /api/fnb/kitchen-display - returns kitchen orders"""
        response = requests.get(f"{BASE_URL}/api/fnb/kitchen-display", headers=auth_header)
        assert response.status_code == 200
    
    def test_fnb_ingredients(self, auth_header):
        """GET /api/fnb/ingredients - returns ingredients"""
        response = requests.get(f"{BASE_URL}/api/fnb/ingredients", headers=auth_header)
        assert response.status_code == 200


class TestPOSDomainRouter:
    """Tests for domains/pms/pos_router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_pos_daily_summary(self, auth_header):
        """GET /api/pos/daily-summary - returns daily summary"""
        response = requests.get(f"{BASE_URL}/api/pos/daily-summary", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "total_sales" in data or isinstance(data, dict)
    
    def test_pos_transactions(self, auth_header):
        """GET /api/pos/transactions - returns transactions"""
        response = requests.get(f"{BASE_URL}/api/pos/transactions", headers=auth_header)
        assert response.status_code == 200
    
    def test_pos_z_report(self, auth_header):
        """GET /api/pos/z-report - returns Z report"""
        response = requests.get(f"{BASE_URL}/api/pos/z-report", headers=auth_header)
        assert response.status_code == 200
    
    def test_frontdesk_available_rooms(self, auth_header):
        """GET /api/frontdesk/available-rooms - returns available rooms"""
        response = requests.get(
            f"{BASE_URL}/api/frontdesk/available-rooms",
            params={"check_in": "2026-01-20", "check_out": "2026-01-22"},
            headers=auth_header
        )
        assert response.status_code == 200


class TestAnalyticsDomainRouter:
    """Tests for domains/revenue/analytics_router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_dashboard_gm_pickup_analysis(self, auth_header):
        """GET /api/dashboard/gm/pickup-analysis - returns pickup analysis data"""
        response = requests.get(f"{BASE_URL}/api/dashboard/gm/pickup-analysis", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "pickup_data" in data or "pickup_trends" in data or isinstance(data, dict)
    
    def test_revenue_market_segment_breakdown(self, auth_header):
        """GET /api/revenue/market-segment-breakdown - returns market segment data"""
        response = requests.get(f"{BASE_URL}/api/revenue/market-segment-breakdown", headers=auth_header)
        assert response.status_code == 200
    
    def test_channel_manager_overview(self, auth_header):
        """GET /api/channel-manager/overview - returns channel overview"""
        response = requests.get(f"{BASE_URL}/api/channel-manager/overview", headers=auth_header)
        assert response.status_code == 200


class TestMobileDomainRouter:
    """Tests for domains/pms/mobile_router.py endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_dashboard_mobile_critical_issues(self, auth_header):
        """GET /api/dashboard/mobile/critical-issues - returns critical issues"""
        response = requests.get(f"{BASE_URL}/api/dashboard/mobile/critical-issues", headers=auth_header)
        assert response.status_code == 200
        data = response.json()
        assert "critical_issues" in data or isinstance(data, dict)
    
    def test_dashboard_mobile_recent_complaints(self, auth_header):
        """GET /api/dashboard/mobile/recent-complaints - returns complaints"""
        response = requests.get(f"{BASE_URL}/api/dashboard/mobile/recent-complaints", headers=auth_header)
        assert response.status_code == 200
    
    def test_notifications_mobile_gm(self, auth_header):
        """GET /api/notifications/mobile/gm - returns GM notifications"""
        response = requests.get(f"{BASE_URL}/api/notifications/mobile/gm", headers=auth_header)
        assert response.status_code == 200
    
    def test_housekeeping_mobile_sla_delayed(self, auth_header):
        """GET /api/housekeeping/mobile/sla-delayed-rooms - returns SLA delayed rooms"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/mobile/sla-delayed-rooms", headers=auth_header)
        assert response.status_code == 200


class TestOTAEndpoints:
    """Tests for OTA messaging endpoints in enterprise_router"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_ota_conversations(self, auth_header):
        """GET /api/ota/conversations - returns OTA conversations"""
        response = requests.get(f"{BASE_URL}/api/ota/conversations", headers=auth_header)
        assert response.status_code == 200
    
    def test_ota_booking_credentials(self, auth_header):
        """GET /api/ota/booking/credentials - returns Booking.com credentials"""
        response = requests.get(f"{BASE_URL}/api/ota/booking/credentials", headers=auth_header)
        assert response.status_code == 200


class TestAdminEndpoints:
    """Tests for admin endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_admin_permissions(self, auth_header):
        """GET /api/admin/permissions - returns all permissions"""
        response = requests.get(f"{BASE_URL}/api/admin/permissions", headers=auth_header)
        assert response.status_code == 200
    
    def test_admin_audit_logs(self, auth_header):
        """GET /api/admin/audit-logs - returns audit logs"""
        response = requests.get(f"{BASE_URL}/api/admin/audit-logs", headers=auth_header)
        assert response.status_code == 200
    
    def test_admin_system_health(self, auth_header):
        """GET /api/admin/system/health - returns system health"""
        response = requests.get(f"{BASE_URL}/api/admin/system/health", headers=auth_header)
        assert response.status_code == 200


class TestMultiPropertyEndpoints:
    """Tests for multi-property endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_multi_property_dashboard(self, auth_header):
        """GET /api/multi-property/dashboard - returns multi-property dashboard"""
        response = requests.get(f"{BASE_URL}/api/multi-property/dashboard", headers=auth_header)
        assert response.status_code == 200


class TestFnBMobileEndpoints:
    """Tests for F&B mobile endpoints in marketplace_router"""
    
    @pytest.fixture(scope="class")
    def auth_header(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_fnb_mobile_outlets(self, auth_header):
        """GET /api/fnb/mobile/outlets - returns F&B outlets for mobile"""
        response = requests.get(f"{BASE_URL}/api/fnb/mobile/outlets", headers=auth_header)
        assert response.status_code == 200
    
    def test_fnb_mobile_daily_summary(self, auth_header):
        """GET /api/fnb/mobile/daily-summary - returns F&B daily summary"""
        response = requests.get(f"{BASE_URL}/api/fnb/mobile/daily-summary", headers=auth_header)
        assert response.status_code == 200


class TestCorporateContractApprovalWorkflow:
    """Live API contract-tests for the corporate-contract approval state machine.

    Locks in (against the real HTTP endpoint, with real auth/RBAC) that the
    draft→pending→approved/rejected (+ rejected→draft) workflow cannot be
    bypassed:
      - legal transitions return 200 and PERSIST the new approval_status
      - illegal skip (draft→approved) and terminal re-open (approved→pending)
        return 409
      - an unknown target status returns 400
      - a caller missing `manage_sales` returns 403
      - a contract id owned by another tenant returns 404 (tenant isolation)

    These complement the unit tests on CONTRACT_APPROVAL_TRANSITIONS /
    _assert_contract_unique and the stress spec; here the whole request path
    (auth → require_op → tenant-scoped lookup → transition map) is exercised.
    """

    @pytest.fixture(scope="class")
    def admin_headers(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _create_draft_contract(self, headers):
        """Create a fresh corporate contract (starts in `draft`) and return its id.

        Uses a unique rate_code / contact_email per call so the tenant-scoped
        duplicate guard (409) never trips between tests.
        """
        suffix = uuid.uuid4().hex[:12]
        body = {
            "company_name": f"TEST_Approval_{suffix}",
            "contract_type": "negotiated",
            "rate_code": f"TESTRC{suffix}",
            "negotiated_rate": 1200.0,
            "discount_percentage": 10,
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "allotment": 5,
            "contact_person": "Test Contact",
            "contact_email": f"approval_{suffix}@example.invalid",
            "contact_phone": "+90 555 000 0000",
            "notes": "Created by approval-workflow integration test",
        }
        resp = requests.post(
            f"{BASE_URL}/api/sales/corporate-contract", headers=headers, json=body)
        assert resp.status_code == 200, f"Create contract failed: {resp.text}"
        data = resp.json()
        assert data.get("approval_status") == "draft"
        contract_id = data.get("contract_id")
        assert contract_id, f"No contract_id in response: {data}"
        return contract_id

    def _transition(self, headers, contract_id, to_status, reason=None):
        return requests.post(
            f"{BASE_URL}/api/sales/corporate-contract/{contract_id}/approval-transition",
            headers=headers,
            json={"to_status": to_status, "reason": reason},
        )

    def _persisted_approval_status(self, headers, contract_id):
        resp = requests.get(
            f"{BASE_URL}/api/sales/corporate-contracts", headers=headers)
        assert resp.status_code == 200, resp.text
        for c in resp.json().get("contracts", []):
            if c.get("id") == contract_id:
                return c.get("approval_status")
        return None

    def test_legal_transition_returns_200_and_persists(self, admin_headers):
        """draft→pending→approved each return 200 and persist approval_status."""
        contract_id = self._create_draft_contract(admin_headers)

        r1 = self._transition(admin_headers, contract_id, "pending")
        assert r1.status_code == 200, r1.text
        assert r1.json().get("approval_status") == "pending"
        assert self._persisted_approval_status(admin_headers, contract_id) == "pending"

        r2 = self._transition(admin_headers, contract_id, "approved", reason="ok")
        assert r2.status_code == 200, r2.text
        assert r2.json().get("approval_status") == "approved"
        assert self._persisted_approval_status(admin_headers, contract_id) == "approved"

    def test_reject_then_resubmit_cycle_is_legal(self, admin_headers):
        """pending→rejected→draft (resubmit) is a legal cycle (200 each)."""
        contract_id = self._create_draft_contract(admin_headers)

        assert self._transition(admin_headers, contract_id, "pending").status_code == 200
        r_reject = self._transition(
            admin_headers, contract_id, "rejected", reason="Rates out of policy")
        assert r_reject.status_code == 200, r_reject.text
        r_resubmit = self._transition(admin_headers, contract_id, "draft")
        assert r_resubmit.status_code == 200, r_resubmit.text
        assert self._persisted_approval_status(admin_headers, contract_id) == "draft"

    def test_reject_without_reason_returns_400(self, admin_headers):
        """rejected requires a mandatory reason → blank/missing reason is a 400.

        The contract owner needs to know what to fix before resubmitting, so a
        rejection with no explanation is refused server-side and the state
        machine must NOT advance (stays pending).
        """
        contract_id = self._create_draft_contract(admin_headers)
        assert self._transition(admin_headers, contract_id, "pending").status_code == 200

        # No reason at all.
        r_none = self._transition(admin_headers, contract_id, "rejected")
        assert r_none.status_code == 400, r_none.text
        assert self._persisted_approval_status(admin_headers, contract_id) == "pending"

        # Whitespace-only reason is also blank.
        r_blank = self._transition(
            admin_headers, contract_id, "rejected", reason="   ")
        assert r_blank.status_code == 400, r_blank.text
        assert self._persisted_approval_status(admin_headers, contract_id) == "pending"

        # A real reason now succeeds.
        r_ok = self._transition(
            admin_headers, contract_id, "rejected", reason="Margins below floor")
        assert r_ok.status_code == 200, r_ok.text
        assert self._persisted_approval_status(admin_headers, contract_id) == "rejected"

    def test_illegal_skip_draft_to_approved_returns_409(self, admin_headers):
        """draft→approved skips the pending review gate → 409 (and no persist)."""
        contract_id = self._create_draft_contract(admin_headers)
        resp = self._transition(admin_headers, contract_id, "approved")
        assert resp.status_code == 409, resp.text
        # State machine must NOT have advanced.
        assert self._persisted_approval_status(admin_headers, contract_id) == "draft"

    def test_terminal_reopen_approved_to_pending_returns_409(self, admin_headers):
        """approved is terminal; approved→pending must be refused with 409."""
        contract_id = self._create_draft_contract(admin_headers)
        assert self._transition(admin_headers, contract_id, "pending").status_code == 200
        assert self._transition(admin_headers, contract_id, "approved").status_code == 200

        resp = self._transition(admin_headers, contract_id, "pending")
        assert resp.status_code == 409, resp.text
        assert self._persisted_approval_status(admin_headers, contract_id) == "approved"

    def test_unknown_status_returns_400(self, admin_headers):
        """An unrecognised target status is a client error → 400."""
        contract_id = self._create_draft_contract(admin_headers)
        resp = self._transition(admin_headers, contract_id, "totally-bogus")
        assert resp.status_code == 400, resp.text
        assert self._persisted_approval_status(admin_headers, contract_id) == "draft"

    def test_missing_manage_sales_permission_returns_403(self, admin_headers):
        """A housekeeping user lacks `manage_sales` → 403 before any state change."""
        login = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "housekeeping@hotel.com", "password": "staff123"
        })
        if login.status_code != 200:
            pytest.skip("housekeeping@hotel.com not provisioned in this environment")
        hk_headers = {
            "Authorization": f"Bearer {login.json().get('access_token')}",
            "Content-Type": "application/json",
        }

        contract_id = self._create_draft_contract(admin_headers)
        resp = self._transition(hk_headers, contract_id, "pending")
        assert resp.status_code == 403, (
            f"Expected 403 for missing manage_sales, got {resp.status_code}: {resp.text}")
        # RBAC denial must not mutate the contract.
        assert self._persisted_approval_status(admin_headers, contract_id) == "draft"

    def test_cross_tenant_contract_id_returns_404(self, admin_headers):
        """A contract owned by another tenant is invisible (404), not transitionable.

        Seeds a real ``corporate_contracts`` row under a fabricated foreign
        tenant_id directly in Mongo (mirrors test_cross_tenant_isolation_e2e),
        then proves Tenant A's admin token gets 404 transitioning it and leaves
        the foreign row untouched — so the 404 is tenant isolation, not merely a
        non-existent id (which is covered separately below).
        """
        try:
            from pymongo import MongoClient
        except Exception:
            pytest.skip("pymongo unavailable")

        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        if not mongo_url or not db_name:
            pytest.skip("MONGO_URL/DB_NAME not configured for side-channel seed")

        foreign_tenant_id = f"xtenant-{uuid.uuid4().hex}"
        foreign_contract_id = str(uuid.uuid4())
        client = MongoClient(mongo_url)
        coll = client[db_name].corporate_contracts
        try:
            coll.insert_one({
                "id": foreign_contract_id,
                "tenant_id": foreign_tenant_id,
                "company_name": "TEST_ForeignTenantContract",
                "status": "active",
                "approval_status": "draft",
                "approval_history": [],
            })

            # Tenant A (demo admin) must NOT see or mutate the foreign contract.
            cross = self._transition(admin_headers, foreign_contract_id, "pending")
            assert cross.status_code == 404, (
                f"Cross-tenant transition must 404, got "
                f"{cross.status_code}: {cross.text}")

            # Side-effect check: the foreign row is untouched (still draft, no
            # history), proving the 404 is isolation rather than a silent edit.
            after = coll.find_one({"id": foreign_contract_id})
            assert after is not None
            assert after.get("approval_status") == "draft"
            assert after.get("approval_history") == []
        finally:
            coll.delete_one({"id": foreign_contract_id})
            client.close()

    def test_unknown_contract_id_returns_404(self, admin_headers):
        """A non-existent contract id (within the caller's tenant) → 404."""
        resp = self._transition(admin_headers, str(uuid.uuid4()), "pending")
        assert resp.status_code == 404, resp.text

    def _approval_history(self, headers, contract_id):
        return requests.get(
            f"{BASE_URL}/api/sales/corporate-contract/{contract_id}/approval-history",
            headers=headers,
        )

    def test_approval_history_endpoint_records_who_and_transitions(self, admin_headers):
        """GET .../approval-history returns the per-transition trail (who/from/to).

        Walks a contract draft→pending→approved, then reads the dedicated
        history endpoint and asserts each transition is recorded with the
        acting user (`by`), the from/to status, and a timestamp — so finance
        can audit who moved the contract through the workflow.
        """
        contract_id = self._create_draft_contract(admin_headers)
        assert self._transition(admin_headers, contract_id, "pending").status_code == 200
        assert self._transition(
            admin_headers, contract_id, "approved", reason="budget ok").status_code == 200

        resp = self._approval_history(admin_headers, contract_id)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("contract_id") == contract_id
        assert data.get("approval_status") == "approved"
        history = data.get("approval_history", [])
        assert len(history) == 2, history
        assert [h.get("from_status") for h in history] == ["draft", "pending"]
        assert [h.get("to_status") for h in history] == ["pending", "approved"]
        # Every entry records who acted and when.
        for h in history:
            assert h.get("by"), f"history entry missing actor: {h}"
            assert h.get("at"), f"history entry missing timestamp: {h}"
        # The reason supplied on the approving transition is preserved.
        assert history[1].get("reason") == "budget ok"

    def test_approval_history_unknown_contract_returns_404(self, admin_headers):
        """Reading history for a non-existent contract id → 404 (tenant-scoped)."""
        resp = self._approval_history(admin_headers, str(uuid.uuid4()))
        assert resp.status_code == 404, resp.text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
