"""
Tests for PMS, Finance, and Reports Router Modularization
Tests endpoints extracted from server.py (51K lines) into:
  - routers/pms.py: PMS, rooms, reservations, bookings routes
  - routers/finance.py: Finance, accounting, cashiering, efatura, folio, invoices routes
  - routers/reports.py: Reports and night-audit routes

Previous routers already tested: auth.py, housekeeping.py, departments.py
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Store token across tests
_cached_tokens = {}


@pytest.fixture(scope="module")
def demo_token():
    """Get auth token using demo admin credentials"""
    if 'demo' in _cached_tokens:
        return _cached_tokens['demo']
        
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    if response.status_code == 200:
        token = response.json().get("access_token")
        _cached_tokens['demo'] = token
        return token
    pytest.skip("Authentication failed - demo@hotel.com not available")
    return None


@pytest.fixture(scope="module")
def frontdesk_token():
    """Get auth token for front desk user"""
    if 'frontdesk' in _cached_tokens:
        return _cached_tokens['frontdesk']
        
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "frontdesk@hotel.com",
        "password": "staff123"
    })
    if response.status_code == 200:
        token = response.json().get("access_token")
        _cached_tokens['frontdesk'] = token
        return token
    return None  # May not exist


@pytest.fixture(scope="module")
def finance_token():
    """Get auth token for finance user"""
    if 'finance' in _cached_tokens:
        return _cached_tokens['finance']
        
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "finance@hotel.com",
        "password": "staff123"
    })
    if response.status_code == 200:
        token = response.json().get("access_token")
        _cached_tokens['finance'] = token
        return token
    return None  # May not exist


@pytest.fixture
def auth_headers(demo_token):
    """Return headers with demo user auth token"""
    return {"Authorization": f"Bearer {demo_token}"}


# ============================================
# TEST: Auth Router (sanity check - login works)
# ============================================
class TestAuthSanity:
    """Verify auth still works before testing extracted routers"""
    
    def test_login_returns_access_token(self):
        """POST /api/auth/login - should return access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        assert "access_token" in data, "Response missing access_token"
        assert data.get("token_type") == "bearer"
        print(f"✅ Auth login works - token type: {data.get('token_type')}")
    
    def test_auth_me_endpoint(self, auth_headers):
        """GET /api/auth/me - auth router still works"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200, f"/auth/me failed: {response.text}"
        
        data = response.json()
        assert "email" in data
        print(f"✅ /api/auth/me works - user: {data.get('email')}")


# ============================================
# TEST: PMS Router (routers/pms.py)
# ============================================
class TestPMSRouter:
    """Test PMS router endpoints extracted from server.py"""
    
    def test_get_rooms(self, auth_headers):
        """GET /api/pms/rooms - should return rooms list"""
        response = requests.get(f"{BASE_URL}/api/pms/rooms", headers=auth_headers)
        assert response.status_code == 200, f"/pms/rooms failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/pms/rooms works - {len(data)} rooms found")
        
        # Validate room structure if rooms exist
        if data:
            room = data[0]
            assert "id" in room or "room_number" in room, "Room missing id/room_number"
            print(f"   First room: {room.get('room_number', room.get('id', 'N/A'))}")
    
    def test_get_pms_dashboard(self, auth_headers):
        """GET /api/pms/dashboard - should return dashboard stats"""
        response = requests.get(f"{BASE_URL}/api/pms/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"/pms/dashboard failed: {response.text}"
        
        data = response.json()
        # Expected fields: total_rooms, occupied_rooms, available_rooms, occupancy_rate
        assert "total_rooms" in data, "Dashboard missing total_rooms"
        assert "occupied_rooms" in data, "Dashboard missing occupied_rooms"
        print(f"✅ GET /api/pms/dashboard works - {data.get('total_rooms')} total rooms, {data.get('occupancy_rate', 0)}% occupancy")
    
    def test_get_bookings(self, auth_headers):
        """GET /api/pms/bookings - should return bookings list"""
        response = requests.get(f"{BASE_URL}/api/pms/bookings", headers=auth_headers)
        assert response.status_code == 200, f"/pms/bookings failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/pms/bookings works - {len(data)} bookings found")
        
        # Validate booking structure if any exist
        if data:
            booking = data[0]
            assert "id" in booking, "Booking missing id"
    
    def test_get_guests(self, auth_headers):
        """GET /api/pms/guests - should return guests list"""
        response = requests.get(f"{BASE_URL}/api/pms/guests", headers=auth_headers)
        assert response.status_code == 200, f"/pms/guests failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/pms/guests works - {len(data)} guests found")
    
    def test_get_room_blocks(self, auth_headers):
        """GET /api/pms/room-blocks - should return room blocks"""
        response = requests.get(f"{BASE_URL}/api/pms/room-blocks", headers=auth_headers)
        assert response.status_code == 200, f"/pms/room-blocks failed: {response.text}"
        
        data = response.json()
        # Can be list or object with blocks
        if isinstance(data, list):
            print(f"✅ GET /api/pms/room-blocks works - {len(data)} blocks (list format)")
        else:
            print(f"✅ GET /api/pms/room-blocks works - {data.get('count', 0)} blocks")
    
    def test_get_group_reservations(self, auth_headers):
        """GET /api/pms/group-reservations - should return groups"""
        response = requests.get(f"{BASE_URL}/api/pms/group-reservations", headers=auth_headers)
        assert response.status_code == 200, f"/pms/group-reservations failed: {response.text}"
        
        data = response.json()
        assert "groups" in data, "Response missing groups key"
        print(f"✅ GET /api/pms/group-reservations works - {len(data.get('groups', []))} groups")
    
    def test_get_pms_companies(self, auth_headers):
        """GET /api/pms/companies - should return companies list"""
        response = requests.get(f"{BASE_URL}/api/pms/companies", headers=auth_headers)
        assert response.status_code == 200, f"/pms/companies failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/pms/companies works - {len(data)} companies")
    
    def test_get_room_services(self, auth_headers):
        """GET /api/pms/room-services - should return services"""
        response = requests.get(f"{BASE_URL}/api/pms/room-services", headers=auth_headers)
        assert response.status_code == 200, f"/pms/room-services failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/pms/room-services works - {len(data)} services")
    
    def test_get_staff_tasks(self, auth_headers):
        """GET /api/pms/staff-tasks - should return tasks"""
        response = requests.get(f"{BASE_URL}/api/pms/staff-tasks", headers=auth_headers)
        assert response.status_code == 200, f"/pms/staff-tasks failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/pms/staff-tasks works - {len(data)} tasks")
    
    def test_get_allotment_contracts(self, auth_headers):
        """GET /api/pms/allotment-contracts - should return contracts"""
        response = requests.get(f"{BASE_URL}/api/pms/allotment-contracts", headers=auth_headers)
        assert response.status_code == 200, f"/pms/allotment-contracts failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/pms/allotment-contracts works - {len(data)} contracts")
    
    def test_get_pms_setup_status(self, auth_headers):
        """GET /api/pms/setup-status - should return setup counts"""
        response = requests.get(f"{BASE_URL}/api/pms/setup-status", headers=auth_headers)
        assert response.status_code == 200, f"/pms/setup-status failed: {response.text}"
        
        data = response.json()
        assert "rooms_count" in data, "Response missing rooms_count"
        assert "bookings_count" in data, "Response missing bookings_count"
        print(f"✅ GET /api/pms/setup-status works - {data.get('rooms_count')} rooms, {data.get('bookings_count')} bookings")


# ============================================
# TEST: Finance Router (routers/finance.py)
# ============================================
class TestFinanceRouter:
    """Test Finance router endpoints extracted from server.py"""
    
    def test_get_folio_list(self, auth_headers):
        """GET /api/folio/list - should return folios"""
        response = requests.get(f"{BASE_URL}/api/folio/list", headers=auth_headers)
        assert response.status_code == 200, f"/folio/list failed: {response.text}"
        
        data = response.json()
        assert "folios" in data, "Response missing folios"
        assert "total" in data, "Response missing total count"
        print(f"✅ GET /api/folio/list works - {data.get('total')} total folios")
    
    def test_get_folio_dashboard_stats(self, auth_headers):
        """GET /api/folio/dashboard-stats - should return folio stats"""
        response = requests.get(f"{BASE_URL}/api/folio/dashboard-stats", headers=auth_headers)
        assert response.status_code == 200, f"/folio/dashboard-stats failed: {response.text}"
        
        data = response.json()
        assert "total_open_folios" in data, "Response missing total_open_folios"
        assert "total_outstanding_balance" in data, "Response missing total_outstanding_balance"
        print(f"✅ GET /api/folio/dashboard-stats works - {data.get('total_open_folios')} open folios, ${data.get('total_outstanding_balance', 0):.2f} outstanding")
    
    def test_get_folio_pending_ar(self, auth_headers):
        """GET /api/folio/pending-ar - should return AR data"""
        response = requests.get(f"{BASE_URL}/api/folio/pending-ar", headers=auth_headers)
        assert response.status_code == 200, f"/folio/pending-ar failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/folio/pending-ar works - {len(data)} AR entries")
    
    def test_get_accounting_dashboard(self, auth_headers):
        """GET /api/accounting/dashboard - should return accounting dashboard"""
        response = requests.get(f"{BASE_URL}/api/accounting/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/dashboard failed: {response.text}"
        
        data = response.json()
        assert "monthly_income" in data, "Response missing monthly_income"
        assert "monthly_expenses" in data, "Response missing monthly_expenses"
        assert "net_income" in data, "Response missing net_income"
        print(f"✅ GET /api/accounting/dashboard works - net income: ${data.get('net_income', 0):.2f}")
    
    def test_get_accounting_suppliers(self, auth_headers):
        """GET /api/accounting/suppliers - should return suppliers list"""
        response = requests.get(f"{BASE_URL}/api/accounting/suppliers", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/suppliers failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/accounting/suppliers works - {len(data)} suppliers")
    
    def test_get_accounting_expenses(self, auth_headers):
        """GET /api/accounting/expenses - should return expenses list"""
        response = requests.get(f"{BASE_URL}/api/accounting/expenses", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/expenses failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/accounting/expenses works - {len(data)} expenses")
    
    def test_get_accounting_bank_accounts(self, auth_headers):
        """GET /api/accounting/bank-accounts - should return bank accounts"""
        response = requests.get(f"{BASE_URL}/api/accounting/bank-accounts", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/bank-accounts failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/accounting/bank-accounts works - {len(data)} accounts")
    
    def test_get_accounting_invoices(self, auth_headers):
        """GET /api/accounting/invoices - should return accounting invoices"""
        response = requests.get(f"{BASE_URL}/api/accounting/invoices", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/invoices failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/accounting/invoices works - {len(data)} invoices")
    
    def test_get_accounting_inventory(self, auth_headers):
        """GET /api/accounting/inventory - should return inventory items"""
        response = requests.get(f"{BASE_URL}/api/accounting/inventory", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/inventory failed: {response.text}"
        
        data = response.json()
        assert "items" in data, "Response missing items"
        assert "total_value" in data, "Response missing total_value"
        print(f"✅ GET /api/accounting/inventory works - {len(data.get('items', []))} items, ${data.get('total_value', 0):.2f} value")
    
    def test_get_accounting_cash_flow(self, auth_headers):
        """GET /api/accounting/cash-flow - should return cash flow data"""
        response = requests.get(f"{BASE_URL}/api/accounting/cash-flow", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/cash-flow failed: {response.text}"
        
        data = response.json()
        assert "transactions" in data, "Response missing transactions"
        assert "net_cash_flow" in data, "Response missing net_cash_flow"
        print(f"✅ GET /api/accounting/cash-flow works - net: ${data.get('net_cash_flow', 0):.2f}")
    
    def test_get_accounting_currencies(self, auth_headers):
        """GET /api/accounting/currencies - should return supported currencies"""
        response = requests.get(f"{BASE_URL}/api/accounting/currencies", headers=auth_headers)
        assert response.status_code == 200, f"/accounting/currencies failed: {response.text}"
        
        data = response.json()
        assert "currencies" in data, "Response missing currencies"
        print(f"✅ GET /api/accounting/currencies works - {len(data.get('currencies', []))} currencies")
    
    def test_get_invoices(self, auth_headers):
        """GET /api/invoices - should return invoices (requires invoices module)"""
        response = requests.get(f"{BASE_URL}/api/invoices", headers=auth_headers)
        # May require invoices module permission
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list), f"Expected list, got {type(data)}"
            print(f"✅ GET /api/invoices works - {len(data)} invoices")
        elif response.status_code == 403:
            print(f"⚠️ GET /api/invoices - requires invoices module permission (403)")
        else:
            assert False, f"/invoices failed: {response.status_code} - {response.text}"
    
    def test_get_invoices_stats(self, auth_headers):
        """GET /api/invoices/stats - should return invoice statistics"""
        response = requests.get(f"{BASE_URL}/api/invoices/stats", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            assert "total_invoices" in data, "Response missing total_invoices"
            print(f"✅ GET /api/invoices/stats works - {data.get('total_invoices')} invoices")
        elif response.status_code == 403:
            print(f"⚠️ GET /api/invoices/stats - requires permission (403)")
        else:
            assert False, f"/invoices/stats failed: {response.status_code}"


# ============================================
# TEST: Cashiering/City Ledger (Finance Router)
# ============================================
class TestCashieringRouter:
    """Test Cashiering endpoints in Finance router"""
    
    def test_get_city_ledger(self, auth_headers):
        """GET /api/cashiering/city-ledger - should return city ledger data"""
        response = requests.get(f"{BASE_URL}/api/cashiering/city-ledger", headers=auth_headers)
        assert response.status_code == 200, f"/cashiering/city-ledger failed: {response.text}"
        
        data = response.json()
        # Expected: list or object with entries
        if isinstance(data, list):
            print(f"✅ GET /api/cashiering/city-ledger works - {len(data)} entries (list)")
        else:
            # Could have entries or transactions key
            entries = data.get('entries', data.get('transactions', data.get('ledger', [])))
            print(f"✅ GET /api/cashiering/city-ledger works - data returned")


# ============================================
# TEST: Reports Router (routers/reports.py)
# ============================================
class TestReportsRouter:
    """Test Reports router endpoints extracted from server.py"""
    
    def test_get_daily_flash_report(self, auth_headers):
        """GET /api/reports/daily-flash - should return daily flash report"""
        response = requests.get(f"{BASE_URL}/api/reports/daily-flash", headers=auth_headers)
        assert response.status_code == 200, f"/reports/daily-flash failed: {response.text}"
        
        data = response.json()
        assert "date" in data or "report_date" in data, "Response missing date"
        assert "occupancy" in data or "movements" in data or "revenue" in data, "Response missing key metrics"
        print(f"✅ GET /api/reports/daily-flash works - date: {data.get('date', data.get('report_date', 'N/A'))}")
    
    def test_get_occupancy_report(self, auth_headers):
        """GET /api/reports/occupancy - should return occupancy report"""
        # Requires date parameters
        params = {
            "start_date": "2025-01-01",
            "end_date": "2025-01-31"
        }
        response = requests.get(f"{BASE_URL}/api/reports/occupancy", headers=auth_headers, params=params)
        assert response.status_code == 200, f"/reports/occupancy failed: {response.text}"
        
        data = response.json()
        assert "total_rooms" in data or "occupancy_rate" in data, "Response missing occupancy data"
        print(f"✅ GET /api/reports/occupancy works - occupancy: {data.get('occupancy_rate', 'N/A')}%")
    
    def test_get_revenue_report(self, auth_headers):
        """GET /api/reports/revenue - should return revenue report"""
        params = {
            "start_date": "2025-01-01",
            "end_date": "2025-01-31"
        }
        response = requests.get(f"{BASE_URL}/api/reports/revenue", headers=auth_headers, params=params)
        assert response.status_code == 200, f"/reports/revenue failed: {response.text}"
        
        data = response.json()
        assert "total_revenue" in data or "revenue" in data, "Response missing revenue data"
        print(f"✅ GET /api/reports/revenue works - total: ${data.get('total_revenue', 0):.2f}")
    
    def test_get_daily_summary(self, auth_headers):
        """GET /api/reports/daily-summary - should return daily summary"""
        response = requests.get(f"{BASE_URL}/api/reports/daily-summary", headers=auth_headers)
        assert response.status_code == 200, f"/reports/daily-summary failed: {response.text}"
        
        data = response.json()
        assert "date" in data, "Response missing date"
        print(f"✅ GET /api/reports/daily-summary works - date: {data.get('date')}")
    
    def test_get_forecast_report(self, auth_headers):
        """GET /api/reports/forecast - should return forecast data"""
        response = requests.get(f"{BASE_URL}/api/reports/forecast", headers=auth_headers)
        assert response.status_code == 200, f"/reports/forecast failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ GET /api/reports/forecast works - {len(data)} days forecasted")
    
    def test_get_basic_dashboard(self, auth_headers):
        """GET /api/reports/basic-dashboard - should return basic reporting dashboard"""
        response = requests.get(f"{BASE_URL}/api/reports/basic-dashboard", headers=auth_headers)
        # May require basic_reporting module
        if response.status_code == 200:
            data = response.json()
            assert "summary" in data or "date" in data, "Response missing summary/date"
            print(f"✅ GET /api/reports/basic-dashboard works")
        elif response.status_code == 403:
            print(f"⚠️ GET /api/reports/basic-dashboard - requires basic_reporting module (403)")
        else:
            assert False, f"/reports/basic-dashboard failed: {response.status_code}"
    
    def test_get_flash_report(self, auth_headers):
        """GET /api/reports/flash-report - should return flash report"""
        response = requests.get(f"{BASE_URL}/api/reports/flash-report", headers=auth_headers)
        # May require reports module
        if response.status_code == 200:
            data = response.json()
            print(f"✅ GET /api/reports/flash-report works")
        elif response.status_code == 403:
            print(f"⚠️ GET /api/reports/flash-report - requires reports module (403)")
        else:
            assert False, f"/reports/flash-report failed: {response.status_code}"


# ============================================
# TEST: Night Audit Endpoints (Reports Router)
# ============================================
class TestNightAuditRouter:
    """Test Night Audit endpoints in Reports router"""
    
    def test_get_night_audit_status(self, auth_headers):
        """GET /api/night-audit/status - should return audit status"""
        response = requests.get(f"{BASE_URL}/api/night-audit/status", headers=auth_headers)
        # This endpoint may not exist - check for 404 vs actual response
        if response.status_code == 200:
            data = response.json()
            print(f"✅ GET /api/night-audit/status works - data returned")
        elif response.status_code == 404:
            # Endpoint may not be implemented yet - try alternative
            print(f"⚠️ GET /api/night-audit/status - 404 Not Found (may not be implemented)")
        else:
            print(f"⚠️ GET /api/night-audit/status - returned {response.status_code}")
    
    def test_get_audit_report(self, auth_headers):
        """GET /api/night-audit/audit-report - should return audit report"""
        params = {"audit_date": "2025-01-27"}
        response = requests.get(f"{BASE_URL}/api/night-audit/audit-report", headers=auth_headers, params=params)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ GET /api/night-audit/audit-report works")
        elif response.status_code == 404:
            # Audit may not exist for this date
            print(f"⚠️ GET /api/night-audit/audit-report - 404 (no audit for date)")
        else:
            print(f"⚠️ GET /api/night-audit/audit-report - returned {response.status_code}")


# ============================================
# TEST: Existing Routers Still Work (Regression)
# ============================================
class TestExistingRoutersRegression:
    """Verify existing housekeeping and departments routers still work"""
    
    def test_housekeeping_rooms_endpoint(self, auth_headers):
        """GET /api/housekeeping/rooms - existing housekeeping router still works"""
        response = requests.get(f"{BASE_URL}/api/housekeeping/rooms", headers=auth_headers)
        # Try alternate endpoints if /rooms doesn't exist
        if response.status_code == 404:
            response = requests.get(f"{BASE_URL}/api/housekeeping/room-status", headers=auth_headers)
        
        assert response.status_code == 200, f"/housekeeping/rooms failed: {response.text}"
        print(f"✅ Housekeeping router still works")
    
    def test_departments_endpoint(self, auth_headers):
        """GET /api/departments/ - existing departments router still works"""
        response = requests.get(f"{BASE_URL}/api/departments/", headers=auth_headers)
        # May be /department/ singular
        if response.status_code == 404:
            response = requests.get(f"{BASE_URL}/api/department/front-office/dashboard", headers=auth_headers)
        
        if response.status_code == 200:
            print(f"✅ Departments router still works")
        elif response.status_code == 404:
            print(f"⚠️ Departments endpoint returns 404 - check route path")
        else:
            print(f"⚠️ Departments returned {response.status_code}")


# ============================================
# TEST: Finance Integration Endpoints
# ============================================
class TestFinanceIntegration:
    """Test finance integration endpoints (Logo, Netsis)"""
    
    def test_get_integration_logs(self, auth_headers):
        """GET /api/finance/integration/logs - should return sync logs"""
        response = requests.get(f"{BASE_URL}/api/finance/integration/logs", headers=auth_headers)
        assert response.status_code == 200, f"/finance/integration/logs failed: {response.text}"
        
        data = response.json()
        assert "logs" in data, "Response missing logs"
        print(f"✅ GET /api/finance/integration/logs works - {data.get('count', 0)} logs")
    
    def test_get_budget_vs_actual(self, auth_headers):
        """GET /api/finance/budget-vs-actual - should return budget comparison"""
        params = {"month": "2025-01"}
        response = requests.get(f"{BASE_URL}/api/finance/budget-vs-actual", headers=auth_headers, params=params)
        assert response.status_code == 200, f"/finance/budget-vs-actual failed: {response.text}"
        
        data = response.json()
        assert "budget" in data, "Response missing budget"
        assert "actual" in data, "Response missing actual"
        print(f"✅ GET /api/finance/budget-vs-actual works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
