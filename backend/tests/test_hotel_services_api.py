"""
Backend API Tests for Hotel Services - 5 New Features
1. Housekeeping Status Management
2. Wake-up Call Management
3. Lost & Found Module
4. Hotel Settings (Invoice Settings)
5. Group Folio Merging & PDF Invoice
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for hotel user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ==================== HOUSEKEEPING STATUS TESTS ====================
class TestHousekeepingStatus:
    """Housekeeping Status Management API Tests"""
    
    def test_get_housekeeping_rooms(self, auth_headers):
        """Test GET /api/pms/housekeeping/rooms - returns rooms with housekeeping status"""
        response = requests.get(f"{BASE_URL}/api/pms/housekeeping/rooms", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "rooms" in data
        assert "summary" in data
        assert "total" in data
        print(f"PASS: GET /api/pms/housekeeping/rooms - {data['total']} rooms found")
    
    def test_get_housekeeping_rooms_filtered_by_status(self, auth_headers):
        """Test GET /api/pms/housekeeping/rooms with status filter"""
        response = requests.get(f"{BASE_URL}/api/pms/housekeeping/rooms", 
                              params={"status_filter": "clean"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "rooms" in data
        # All returned rooms should be clean (or default to clean)
        for room in data.get("rooms", []):
            status = room.get("housekeeping_status", "clean")
            assert status == "clean", f"Expected clean, got {status}"
        print(f"PASS: GET /api/pms/housekeeping/rooms with status_filter=clean - {len(data['rooms'])} rooms")
    
    def test_update_room_housekeeping_status(self, auth_headers):
        """Test PUT /api/pms/housekeeping/rooms/{room_id}/status - update room status"""
        # First get a room
        rooms_res = requests.get(f"{BASE_URL}/api/pms/housekeeping/rooms", headers=auth_headers)
        rooms = rooms_res.json().get("rooms", [])
        if not rooms:
            pytest.skip("No rooms available to test status update")
        
        room = rooms[0]
        room_id = room["id"]
        original_status = room.get("housekeeping_status", "clean")
        
        # Update status to 'dirty'
        response = requests.put(f"{BASE_URL}/api/pms/housekeeping/rooms/{room_id}/status",
                               json={"status": "dirty", "notes": "TEST_status_update"},
                               headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("new_status") == "dirty"
        
        # Revert to original status
        requests.put(f"{BASE_URL}/api/pms/housekeeping/rooms/{room_id}/status",
                    json={"status": original_status}, headers=auth_headers)
        print(f"PASS: PUT /api/pms/housekeeping/rooms/{room_id}/status - updated to dirty, reverted to {original_status}")


# ==================== WAKE-UP CALLS TESTS ====================
class TestWakeUpCalls:
    """Wake-up Call Management API Tests"""
    
    def test_get_wake_up_calls(self, auth_headers):
        """Test GET /api/pms/wake-up-calls - returns wake-up calls"""
        response = requests.get(f"{BASE_URL}/api/pms/wake-up-calls", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "calls" in data
        assert "stats" in data
        print(f"PASS: GET /api/pms/wake-up-calls - {len(data['calls'])} calls, stats: {data['stats']}")
    
    def test_create_and_manage_wake_up_call(self, auth_headers):
        """Test full CRUD for wake-up calls: create, update status, delete"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # CREATE
        payload = {
            "room_number": "TEST_101",
            "guest_name": "TEST_Guest",
            "wake_time": "07:30",
            "wake_date": tomorrow,
            "notes": "TEST_wake_up_call",
            "method": "phone"
        }
        create_res = requests.post(f"{BASE_URL}/api/pms/wake-up-calls", json=payload, headers=auth_headers)
        assert create_res.status_code == 200
        data = create_res.json()
        assert data.get("success") == True
        call = data["call"]
        call_id = call["id"]
        assert call["room_number"] == "TEST_101"
        assert call["status"] == "pending"
        print(f"PASS: POST /api/pms/wake-up-calls - created call {call_id}")
        
        # UPDATE STATUS to completed
        update_res = requests.put(f"{BASE_URL}/api/pms/wake-up-calls/{call_id}",
                                 json={"status": "completed", "response": "answered"},
                                 headers=auth_headers)
        assert update_res.status_code == 200
        assert update_res.json()["call"]["status"] == "completed"
        print(f"PASS: PUT /api/pms/wake-up-calls/{call_id} - status updated to completed")
        
        # DELETE
        delete_res = requests.delete(f"{BASE_URL}/api/pms/wake-up-calls/{call_id}", headers=auth_headers)
        assert delete_res.status_code == 200
        assert delete_res.json().get("success") == True
        print(f"PASS: DELETE /api/pms/wake-up-calls/{call_id} - deleted")


# ==================== LOST & FOUND TESTS ====================
class TestLostFound:
    """Lost & Found Module API Tests"""
    
    def test_get_lost_found_items(self, auth_headers):
        """Test GET /api/pms/lost-found - returns lost & found items"""
        response = requests.get(f"{BASE_URL}/api/pms/lost-found", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "stats" in data
        print(f"PASS: GET /api/pms/lost-found - {len(data['items'])} items, stats: {data['stats']}")
    
    def test_create_update_match_delete_lost_found_item(self, auth_headers):
        """Test full workflow for lost & found: create, update, match guest, delete"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # CREATE
        payload = {
            "item_name": "TEST_Black Wallet",
            "description": "Leather wallet with ID cards",
            "category": "other",
            "found_location": "Lobby",
            "found_date": today,
            "room_number": "105"
        }
        create_res = requests.post(f"{BASE_URL}/api/pms/lost-found", json=payload, headers=auth_headers)
        assert create_res.status_code == 200
        data = create_res.json()
        assert data.get("success") == True
        item = data["item"]
        item_id = item["id"]
        assert item["item_name"] == "TEST_Black Wallet"
        assert item["status"] == "found"
        print(f"PASS: POST /api/pms/lost-found - created item {item_id}")
        
        # UPDATE STATUS to stored
        update_res = requests.put(f"{BASE_URL}/api/pms/lost-found/{item_id}",
                                 json={"status": "stored", "notes": "Stored in safe"},
                                 headers=auth_headers)
        assert update_res.status_code == 200
        assert update_res.json()["item"]["status"] == "stored"
        print(f"PASS: PUT /api/pms/lost-found/{item_id} - status updated to stored")
        
        # MATCH GUEST
        match_res = requests.post(f"{BASE_URL}/api/pms/lost-found/{item_id}/match-guest",
                                 params={"guest_name": "TEST_John Doe", "guest_contact": "+90555123456"},
                                 headers=auth_headers)
        assert match_res.status_code == 200
        assert match_res.json()["item"]["guest_name"] == "TEST_John Doe"
        print(f"PASS: POST /api/pms/lost-found/{item_id}/match-guest - guest matched")
        
        # DELETE
        delete_res = requests.delete(f"{BASE_URL}/api/pms/lost-found/{item_id}", headers=auth_headers)
        assert delete_res.status_code == 200
        assert delete_res.json().get("success") == True
        print(f"PASS: DELETE /api/pms/lost-found/{item_id} - deleted")


# ==================== HOTEL SETTINGS TESTS ====================
class TestHotelSettings:
    """Hotel Settings (Invoice Settings) API Tests"""
    
    def test_get_hotel_settings(self, auth_headers):
        """Test GET /api/pms/hotel-settings - returns hotel settings"""
        response = requests.get(f"{BASE_URL}/api/pms/hotel-settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should have standard fields
        assert "tenant_id" in data or "hotel_name" in data or "currency" in data
        print(f"PASS: GET /api/pms/hotel-settings - settings retrieved")
    
    def test_update_hotel_settings(self, auth_headers):
        """Test PUT /api/pms/hotel-settings - update settings and verify"""
        payload = {
            "tax_id": "TEST_1234567890",
            "tax_office": "TEST_Beyoglu",
            "invoice_footer": "TEST_Thank you for staying with us"
        }
        response = requests.put(f"{BASE_URL}/api/pms/hotel-settings", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "settings" in data
        settings = data["settings"]
        assert settings.get("tax_id") == "TEST_1234567890"
        print(f"PASS: PUT /api/pms/hotel-settings - settings updated with tax_id, tax_office, invoice_footer")
        
        # Verify by GET
        verify_res = requests.get(f"{BASE_URL}/api/pms/hotel-settings", headers=auth_headers)
        verify_data = verify_res.json()
        assert verify_data.get("tax_id") == "TEST_1234567890"
        print(f"PASS: GET /api/pms/hotel-settings - verified updated settings persisted")


# ==================== PDF INVOICE TESTS ====================
class TestInvoicePDF:
    """PDF Invoice Generation Tests"""
    
    def test_generate_invoice_pdf(self, auth_headers):
        """Test GET /api/pms/reservations/{booking_id}/invoice-pdf - generate invoice HTML"""
        # First get a booking
        bookings_res = requests.get(f"{BASE_URL}/api/pms/bookings", headers=auth_headers)
        if bookings_res.status_code != 200:
            pytest.skip("Cannot fetch bookings")
        
        data = bookings_res.json()
        # Handle both list and dict response formats
        if isinstance(data, list):
            bookings = data
        else:
            bookings = data.get("bookings", [])
        if not bookings:
            pytest.skip("No bookings available to generate invoice")
        
        booking_id = bookings[0]["id"]
        
        response = requests.get(f"{BASE_URL}/api/pms/reservations/{booking_id}/invoice-pdf",
                               headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "invoice_html" in data
        assert "invoice_number" in data
        assert "total_charges" in data
        assert "total_payments" in data
        assert "balance" in data
        assert len(data["invoice_html"]) > 100  # Should have substantial HTML content
        assert "<!DOCTYPE html>" in data["invoice_html"]
        print(f"PASS: GET /api/pms/reservations/{booking_id}/invoice-pdf - invoice generated with number {data['invoice_number']}")
    
    def test_invoice_pdf_nonexistent_booking(self, auth_headers):
        """Test invoice generation for non-existent booking returns 404"""
        response = requests.get(f"{BASE_URL}/api/pms/reservations/nonexistent-booking-id/invoice-pdf",
                               headers=auth_headers)
        assert response.status_code == 404
        print(f"PASS: GET /api/pms/reservations/nonexistent/invoice-pdf - returns 404 as expected")


# ==================== GROUP FOLIO TESTS ====================
class TestGroupFolio:
    """Group Folio API Tests"""
    
    def test_get_group_bookings_list(self, auth_headers):
        """Test GET /api/pms/group-bookings - get list of group bookings"""
        response = requests.get(f"{BASE_URL}/api/pms/group-bookings", headers=auth_headers)
        # Should return 200 even if empty
        assert response.status_code == 200
        data = response.json()
        groups = data.get("groups", data if isinstance(data, list) else [])
        print(f"PASS: GET /api/pms/group-bookings - {len(groups)} groups found")
    
    def test_get_group_folio_status(self, auth_headers):
        """Test GET /api/pms/group-folio/{group_id} - get group folio status"""
        # First get group bookings
        groups_res = requests.get(f"{BASE_URL}/api/pms/group-bookings", headers=auth_headers)
        if groups_res.status_code != 200:
            pytest.skip("Cannot fetch group bookings")
        
        data = groups_res.json()
        groups = data.get("groups", data if isinstance(data, list) else [])
        if not groups:
            pytest.skip("No group bookings available for testing")
        
        group_id = groups[0]["id"]
        
        response = requests.get(f"{BASE_URL}/api/pms/group-folio/{group_id}", headers=auth_headers)
        assert response.status_code == 200
        folio_data = response.json()
        assert "group" in folio_data
        assert "bookings" in folio_data
        print(f"PASS: GET /api/pms/group-folio/{group_id} - group folio status retrieved with {len(folio_data['bookings'])} bookings")
    
    def test_group_folio_nonexistent(self, auth_headers):
        """Test group folio for non-existent group returns 404"""
        response = requests.get(f"{BASE_URL}/api/pms/group-folio/nonexistent-group-id",
                               headers=auth_headers)
        assert response.status_code == 404
        print(f"PASS: GET /api/pms/group-folio/nonexistent - returns 404 as expected")


# ==================== NAVIGATION ROUTES VERIFICATION ====================
class TestNavigationRoutesAPI:
    """Verify new pages can load by checking their APIs are accessible"""
    
    def test_housekeeping_api_accessible(self, auth_headers):
        """Housekeeping page backend API works"""
        response = requests.get(f"{BASE_URL}/api/pms/housekeeping/rooms", headers=auth_headers)
        assert response.status_code == 200
        print("PASS: /housekeeping-status page API accessible")
    
    def test_wakeup_calls_api_accessible(self, auth_headers):
        """Wake-up calls page backend API works"""
        response = requests.get(f"{BASE_URL}/api/pms/wake-up-calls", headers=auth_headers)
        assert response.status_code == 200
        print("PASS: /wake-up-calls page API accessible")
    
    def test_lost_found_api_accessible(self, auth_headers):
        """Lost & Found page backend API works"""
        response = requests.get(f"{BASE_URL}/api/pms/lost-found", headers=auth_headers)
        assert response.status_code == 200
        print("PASS: /lost-found page API accessible")
    
    def test_hotel_settings_api_accessible(self, auth_headers):
        """Settings Invoice tab backend API works"""
        response = requests.get(f"{BASE_URL}/api/pms/hotel-settings", headers=auth_headers)
        assert response.status_code == 200
        print("PASS: Settings Invoice tab API accessible")
    
    def test_group_bookings_api_accessible(self, auth_headers):
        """Group Folio page backend API works"""
        response = requests.get(f"{BASE_URL}/api/pms/group-bookings", headers=auth_headers)
        assert response.status_code == 200
        print("PASS: /group-folio page API accessible")
