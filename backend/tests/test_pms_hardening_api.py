"""
PMS Core Hardening API Tests - Tests all production-grade PMS endpoints.
Covers: Reservation state machine, Front desk, Folio/Billing, Housekeeping, Night Audit, Dashboard, RBAC.
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")


class TestPMSAuth:
    """Test authentication for PMS endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class") 
    def headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_login_success(self):
        """Test login endpoint"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"


# ══════════════════════════════════════════════
# DASHBOARD TESTS
# ══════════════════════════════════════════════

class TestDashboard:
    """Test PMS Dashboard endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_operational_dashboard(self, headers):
        """Test /api/pms-core/dashboard/operational returns correct data structure"""
        response = requests.get(f"{BASE_URL}/api/pms-core/dashboard/operational", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify all required fields present
        assert "business_date" in data
        assert "arrivals_today" in data
        assert "departures_today" in data
        assert "in_house_guests" in data
        assert "room_status" in data
        assert "pending_folio_issues" in data
        assert "audit_exceptions" in data
        assert "blocked_checkins" in data
        
        # Verify nested structures
        assert "total" in data["arrivals_today"]
        assert "total" in data["departures_today"]
        assert "count" in data["in_house_guests"]
        assert "available" in data["room_status"]
        assert "occupied" in data["room_status"]
    
    def test_dashboard_unauthorized(self):
        """Test dashboard requires authentication"""
        response = requests.get(f"{BASE_URL}/api/pms-core/dashboard/operational")
        assert response.status_code in [401, 403]  # Either unauthorized or forbidden


# ══════════════════════════════════════════════
# PERMISSIONS TESTS
# ══════════════════════════════════════════════

class TestPermissions:
    """Test RBAC permission endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_permissions_me(self, headers):
        """Test /api/pms-core/permissions/me returns user role and permissions"""
        response = requests.get(f"{BASE_URL}/api/pms-core/permissions/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "role" in data
        assert "permissions" in data
        assert isinstance(data["permissions"], list)
        assert len(data["permissions"]) > 0  # Admin should have permissions


# ══════════════════════════════════════════════
# HOUSEKEEPING TESTS
# ══════════════════════════════════════════════

class TestHousekeeping:
    """Test housekeeping state endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_room_summary(self, headers):
        """Test /api/pms-core/housekeeping/room-summary returns status breakdown"""
        response = requests.get(f"{BASE_URL}/api/pms-core/housekeeping/room-summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "total_rooms" in data
        assert "available" in data
        assert "occupied" in data
        assert "dirty" in data
        assert "cleaning" in data
        assert "ready_rooms" in data
        assert "dirty_rooms" in data
        
        # Verify math: ready = available + inspected
        assert data["ready_rooms"] == data["available"] + data.get("inspected", 0)
    
    def test_room_readiness(self, headers):
        """Test /api/pms-core/housekeeping/room-readiness/{room_id}"""
        # First get a room ID from summary
        rooms_response = requests.get(f"{BASE_URL}/api/rooms", headers=headers)
        if rooms_response.status_code == 200 and rooms_response.json():
            room_id = rooms_response.json()[0].get("id")
            
            response = requests.get(f"{BASE_URL}/api/pms-core/housekeeping/room-readiness/{room_id}", headers=headers)
            assert response.status_code == 200
            data = response.json()
            
            assert "ready" in data
            assert "room_status" in data
            assert "room_number" in data
    
    def test_room_status_update(self, headers):
        """Test /api/pms-core/housekeeping/room-status POST"""
        # First find a dirty room to transition to cleaning
        rooms_response = requests.get(f"{BASE_URL}/api/rooms", headers=headers)
        if rooms_response.status_code == 200:
            rooms = rooms_response.json()
            dirty_room = next((r for r in rooms if r.get("status") == "dirty"), None)
            
            if dirty_room:
                # Test valid transition: dirty -> cleaning
                response = requests.post(
                    f"{BASE_URL}/api/pms-core/housekeeping/room-status",
                    headers=headers,
                    json={
                        "room_id": dirty_room["id"],
                        "new_status": "cleaning",
                        "notes": "Test transition"
                    }
                )
                assert response.status_code in [200, 400]  # 400 if already cleaning


# ══════════════════════════════════════════════
# NIGHT AUDIT TESTS
# ══════════════════════════════════════════════

class TestNightAudit:
    """Test night audit endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_business_date(self, headers):
        """Test /api/pms-core/night-audit/business-date returns current business date"""
        response = requests.get(f"{BASE_URL}/api/pms-core/night-audit/business-date", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "business_date" in data
        # Verify it's a valid date format
        datetime.fromisoformat(data["business_date"])
    
    def test_exceptions_list(self, headers):
        """Test /api/pms-core/night-audit/exceptions returns list"""
        response = requests.get(f"{BASE_URL}/api/pms-core/night-audit/exceptions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_run_night_audit(self, headers):
        """Test /api/pms-core/night-audit/run executes audit"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/night-audit/run",
            headers=headers,
            json={}  # Use default business date
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert data["status"] in ["completed", "failed", "in_progress"]
        if data["status"] == "completed":
            assert "steps" in data


# ══════════════════════════════════════════════
# AUDIT TRAIL TESTS
# ══════════════════════════════════════════════

class TestAuditTrail:
    """Test audit trail endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_audit_trail(self, headers):
        """Test /api/pms-core/audit-trail returns trail entries"""
        response = requests.get(f"{BASE_URL}/api/pms-core/audit-trail?limit=10", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "count" in data
        assert "trail" in data
        assert isinstance(data["trail"], list)
    
    def test_audit_trail_filter(self, headers):
        """Test /api/pms-core/audit-trail with entity_type filter"""
        response = requests.get(
            f"{BASE_URL}/api/pms-core/audit-trail?entity_type=reservation&limit=5",
            headers=headers
        )
        assert response.status_code == 200


# ══════════════════════════════════════════════
# OVERBOOKING CHECK TESTS
# ══════════════════════════════════════════════

class TestOverbooking:
    """Test overbooking prevention endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_overbooking_check(self, headers):
        """Test /api/pms-core/overbooking-check with query params"""
        # Get a room first
        rooms_response = requests.get(f"{BASE_URL}/api/rooms", headers=headers)
        if rooms_response.status_code == 200 and rooms_response.json():
            room_id = rooms_response.json()[0].get("id")
            
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT14:00:00")
            day_after = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT12:00:00")
            
            response = requests.get(
                f"{BASE_URL}/api/pms-core/overbooking-check",
                headers=headers,
                params={
                    "room_id": room_id,
                    "check_in": tomorrow,
                    "check_out": day_after
                }
            )
            assert response.status_code == 200
            data = response.json()
            
            assert "has_conflict" in data
            assert "conflicts" in data
            assert isinstance(data["conflicts"], list)


# ══════════════════════════════════════════════
# FRONT DESK - CHECKOUT PREVIEW TESTS
# ══════════════════════════════════════════════

class TestCheckoutPreview:
    """Test checkout preview endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_checkout_preview_valid_booking(self, headers):
        """Test /api/pms-core/checkout-preview/{booking_id}"""
        # Get a checked-in booking
        bookings_response = requests.get(f"{BASE_URL}/api/bookings", headers=headers)
        if bookings_response.status_code == 200:
            bookings = bookings_response.json()
            checked_in = next((b for b in bookings if b.get("status") == "checked_in"), None)
            
            if checked_in:
                response = requests.get(
                    f"{BASE_URL}/api/pms-core/checkout-preview/{checked_in['id']}",
                    headers=headers
                )
                assert response.status_code == 200
                data = response.json()
                
                assert "booking_id" in data
                assert "folios" in data
                assert "balance_due" in data
                assert "blockers" in data
                assert "can_checkout" in data
    
    def test_checkout_preview_not_found(self, headers):
        """Test checkout preview with non-existent booking"""
        response = requests.get(
            f"{BASE_URL}/api/pms-core/checkout-preview/non-existent-booking-id",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data


# ══════════════════════════════════════════════
# RESERVATION STATE MACHINE - CANCEL/NO-SHOW TESTS
# ══════════════════════════════════════════════

class TestReservationStateTransitions:
    """Test reservation state transitions via API"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_cancel_invalid_booking(self, headers):
        """Test /api/pms-core/cancel with non-existent booking"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/cancel",
            headers=headers,
            json={
                "booking_id": "non-existent-id",
                "reason": "Test cancellation"
            }
        )
        assert response.status_code == 404
    
    def test_no_show_invalid_booking(self, headers):
        """Test /api/pms-core/no-show with non-existent booking"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/no-show",
            headers=headers,
            json={"booking_id": "non-existent-id"}
        )
        assert response.status_code == 404


# ══════════════════════════════════════════════
# FOLIO OPERATIONS TESTS
# ══════════════════════════════════════════════

class TestFolioOperations:
    """Test folio charge, payment, void endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_tax_breakdown(self, headers):
        """Test /api/pms-core/folio/tax-breakdown/{folio_id}"""
        # Get folios first
        folios_response = requests.get(f"{BASE_URL}/api/folios", headers=headers)
        if folios_response.status_code == 200 and folios_response.json():
            folio_id = folios_response.json()[0].get("id")
            
            response = requests.get(
                f"{BASE_URL}/api/pms-core/folio/tax-breakdown/{folio_id}",
                headers=headers
            )
            assert response.status_code == 200
            data = response.json()
            
            assert "folio_id" in data
            assert "by_category" in data
            assert "total_net" in data
            assert "total_tax" in data
            assert "total_gross" in data
    
    def test_post_charge_invalid_folio(self, headers):
        """Test charge posting to non-existent folio"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/folio/charge",
            headers=headers,
            json={
                "folio_id": "invalid-folio",
                "booking_id": "invalid-booking",
                "amount": 50.0,
                "description": "Test charge"
            }
        )
        assert response.status_code == 400
    
    def test_post_payment_invalid_folio(self, headers):
        """Test payment posting to non-existent folio"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/folio/payment",
            headers=headers,
            json={
                "folio_id": "invalid-folio",
                "booking_id": "invalid-booking",
                "amount": 100.0,
                "method": "cash"
            }
        )
        assert response.status_code == 400
    
    def test_void_charge_invalid(self, headers):
        """Test voiding non-existent charge"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/folio/void-charge",
            headers=headers,
            json={
                "charge_id": "invalid-charge",
                "reason": "Test void"
            }
        )
        assert response.status_code == 400


# ══════════════════════════════════════════════
# FRONT DESK WORKFLOW TESTS
# ══════════════════════════════════════════════

class TestFrontDeskWorkflows:
    """Test front desk check-in, checkout, walk-in endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_checkin_invalid_booking(self, headers):
        """Test /api/pms-core/check-in with invalid booking"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/check-in",
            headers=headers,
            json={"booking_id": "invalid-booking-id"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
    
    def test_checkout_invalid_booking(self, headers):
        """Test /api/pms-core/checkout with invalid booking"""
        response = requests.post(
            f"{BASE_URL}/api/pms-core/checkout",
            headers=headers,
            json={"booking_id": "invalid-booking-id"}
        )
        assert response.status_code == 400
    
    def test_walkin_requires_available_room(self, headers):
        """Test /api/pms-core/walk-in with occupied room"""
        # Get an occupied room
        rooms_response = requests.get(f"{BASE_URL}/api/rooms", headers=headers)
        if rooms_response.status_code == 200:
            rooms = rooms_response.json()
            occupied = next((r for r in rooms if r.get("status") == "occupied"), None)
            
            if occupied:
                response = requests.post(
                    f"{BASE_URL}/api/pms-core/walk-in",
                    headers=headers,
                    json={
                        "room_id": occupied["id"],
                        "nights": 1,
                        "rate": 100.0,
                        "guest_name": "Test Walk-in"
                    }
                )
                assert response.status_code == 400
    
    def test_walkin_available_room(self, headers):
        """Test /api/pms-core/walk-in with available room"""
        # Get an available room
        rooms_response = requests.get(f"{BASE_URL}/api/rooms", headers=headers)
        if rooms_response.status_code == 200:
            rooms = rooms_response.json()
            available = next((r for r in rooms if r.get("status") == "available"), None)
            
            if available:
                response = requests.post(
                    f"{BASE_URL}/api/pms-core/walk-in",
                    headers=headers,
                    json={
                        "room_id": available["id"],
                        "nights": 1,
                        "rate": 100.0,
                        "guest_name": f"TEST_Walk-in-{uuid.uuid4().hex[:6]}",
                        "guest_phone": "555-TEST",
                        "adults": 1
                    }
                )
                # Should succeed or fail due to business rules
                assert response.status_code in [200, 400]
                if response.status_code == 200:
                    data = response.json()
                    assert "success" in data
                    assert data["success"] is True
                    assert "booking_id" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
