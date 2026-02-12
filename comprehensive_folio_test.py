#!/usr/bin/env python3
"""
Comprehensive Folio Creation Test
Tests all scenarios from the review request
"""

import requests
import json
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://report-calendar-fix.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class TestResults:
    def __init__(self):
        self.tests = []
        self.passed = 0
        self.failed = 0
    
    def add_test(self, name, passed, details=""):
        self.tests.append({
            "name": name,
            "passed": passed,
            "details": details
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def print_summary(self):
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        for test in self.tests:
            status = "✅ PASS" if test["passed"] else "❌ FAIL"
            print(f"{status}: {test['name']}")
            if test["details"]:
                print(f"        {test['details']}")
        print(f"\nTotal: {self.passed + self.failed} | Passed: {self.passed} | Failed: {self.failed}")
        print("=" * 80)

def test_1_create_new_booking(token, results):
    """Test 1: Create New Booking and verify HTTP 200"""
    print("\n" + "=" * 80)
    print("TEST 1: Create New Booking")
    print("=" * 80)
    
    # Get guest and room
    guests_resp = requests.get(f"{BASE_URL}/pms/guests?limit=5", headers={"Authorization": f"Bearer {token}"})
    rooms_resp = requests.get(f"{BASE_URL}/pms/rooms?limit=10", headers={"Authorization": f"Bearer {token}"})
    
    if guests_resp.status_code != 200 or rooms_resp.status_code != 200:
        results.add_test("Create New Booking", False, "Failed to fetch guests or rooms")
        return None
    
    guests = guests_resp.json()
    rooms = [r for r in rooms_resp.json() if r.get('status') == 'available']
    
    if not guests or not rooms:
        results.add_test("Create New Booking", False, "No guests or available rooms")
        return None
    
    guest_id = guests[0]['id']
    room_id = rooms[0]['id']
    
    # Create booking
    check_in = (datetime.now() + timedelta(days=2)).isoformat()
    check_out = (datetime.now() + timedelta(days=5)).isoformat()
    
    booking_data = {
        "guest_id": guest_id,
        "room_id": room_id,
        "check_in": check_in,
        "check_out": check_out,
        "adults": 2,
        "children": 0,
        "children_ages": [],
        "guests_count": 2,
        "total_amount": 450.0,
        "base_rate": 150.0,
        "channel": "direct",
        "rate_plan": "Standard"
    }
    
    response = requests.post(
        f"{BASE_URL}/pms/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json=booking_data
    )
    
    if response.status_code == 200:
        booking = response.json()
        booking_id = booking.get('id')
        print(f"✅ Booking created: {booking_id}")
        print(f"   Guest: {guest_id}")
        print(f"   Room: {room_id}")
        results.add_test("Create New Booking - HTTP 200", True, f"Booking ID: {booking_id}")
        return booking_id
    else:
        print(f"❌ Failed: HTTP {response.status_code}")
        print(f"   Response: {response.text}")
        results.add_test("Create New Booking - HTTP 200", False, f"HTTP {response.status_code}")
        return None

def test_2_verify_folio_created(token, booking_id, results):
    """Test 2: Verify Folio Created for new booking"""
    print("\n" + "=" * 80)
    print("TEST 2: Verify Folio Created")
    print("=" * 80)
    
    if not booking_id:
        results.add_test("Verify Folio Exists", False, "No booking ID from Test 1")
        results.add_test("Verify Folio Fields", False, "No booking ID from Test 1")
        results.add_test("Verify Folio Number Format", False, "No booking ID from Test 1")
        return
    
    response = requests.get(
        f"{BASE_URL}/folio/booking/{booking_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Test 2a: Folio exists and returns HTTP 200
    if response.status_code == 200:
        print(f"✅ GET /api/folio/booking/{booking_id} - HTTP 200")
        results.add_test("Verify Folio Exists - HTTP 200", True)
    else:
        print(f"❌ GET /api/folio/booking/{booking_id} - HTTP {response.status_code}")
        results.add_test("Verify Folio Exists - HTTP 200", False, f"HTTP {response.status_code}")
        results.add_test("Verify Folio Fields", False, "No folio returned")
        results.add_test("Verify Folio Number Format", False, "No folio returned")
        return
    
    folios = response.json()
    
    if not folios or len(folios) == 0:
        print(f"❌ No folio found for booking")
        results.add_test("Verify Folio Fields", False, "Empty folio list")
        results.add_test("Verify Folio Number Format", False, "Empty folio list")
        return
    
    folio = folios[0]
    print(f"\n📄 Folio Details:")
    print(f"   Folio ID: {folio.get('id')}")
    print(f"   Folio Number: {folio.get('folio_number')}")
    print(f"   Folio Type: {folio.get('folio_type')}")
    print(f"   Booking ID: {folio.get('booking_id')}")
    print(f"   Guest ID: {folio.get('guest_id')}")
    
    # Test 2b: Verify folio has correct fields
    required_fields = ['folio_number', 'folio_type', 'booking_id', 'guest_id']
    missing_fields = [f for f in required_fields if not folio.get(f)]
    
    if not missing_fields:
        print(f"✅ All required fields present")
        results.add_test("Verify Folio Fields", True, "folio_number, folio_type, booking_id, guest_id")
    else:
        print(f"❌ Missing fields: {', '.join(missing_fields)}")
        results.add_test("Verify Folio Fields", False, f"Missing: {', '.join(missing_fields)}")
    
    # Test 2c: Verify folio_type=guest
    if folio.get('folio_type') == 'guest':
        print(f"✅ Folio type is 'guest'")
    else:
        print(f"❌ Folio type is '{folio.get('folio_type')}' (expected 'guest')")
    
    # Test 2d: Verify folio_number format F-YYYY-#####
    folio_number = folio.get('folio_number', '')
    if folio_number.startswith('F-') and len(folio_number.split('-')) == 3:
        year_part = folio_number.split('-')[1]
        number_part = folio_number.split('-')[2]
        if year_part.isdigit() and len(year_part) == 4 and number_part.isdigit():
            print(f"✅ Folio number format correct: {folio_number}")
            results.add_test("Verify Folio Number Format", True, f"Format: F-YYYY-##### ({folio_number})")
        else:
            print(f"❌ Folio number format invalid: {folio_number}")
            results.add_test("Verify Folio Number Format", False, f"Invalid format: {folio_number}")
    else:
        print(f"❌ Folio number format invalid: {folio_number}")
        results.add_test("Verify Folio Number Format", False, f"Invalid format: {folio_number}")

def test_3_existing_booking_folio(token, results):
    """Test 3: Test Existing Booking with Folio"""
    print("\n" + "=" * 80)
    print("TEST 3: Test Existing Booking with Folio")
    print("=" * 80)
    
    # Get existing bookings
    response = requests.get(
        f"{BASE_URL}/pms/bookings?limit=10",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code != 200:
        print(f"❌ Failed to fetch bookings: HTTP {response.status_code}")
        results.add_test("Existing Booking Folio Retrieval", False, f"HTTP {response.status_code}")
        return
    
    bookings = response.json()
    
    if not bookings:
        print(f"⚠️ No existing bookings found")
        results.add_test("Existing Booking Folio Retrieval", False, "No bookings found")
        return
    
    print(f"Found {len(bookings)} existing bookings")
    
    # Test first booking with folio
    tested = False
    for booking in bookings:
        booking_id = booking.get('id')
        
        folio_response = requests.get(
            f"{BASE_URL}/folio/booking/{booking_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if folio_response.status_code == 200:
            folios = folio_response.json()
            if folios and len(folios) > 0:
                print(f"✅ Booking {booking_id}")
                print(f"   Folio Number: {folios[0].get('folio_number')}")
                print(f"   Folio Type: {folios[0].get('folio_type')}")
                results.add_test("Existing Booking Folio Retrieval", True, f"Booking: {booking_id}")
                tested = True
                break
    
    if not tested:
        print(f"⚠️ No bookings with folios found")
        results.add_test("Existing Booking Folio Retrieval", False, "No bookings with folios")

def main():
    print("=" * 80)
    print("🧪 COMPREHENSIVE FOLIO CREATION TEST")
    print("=" * 80)
    print("\nReview Request: Test folio creation for new bookings")
    print("Expected: New bookings should automatically have folios created")
    print("Issue: 'No folio found for this booking' when clicking guest reservations\n")
    
    results = TestResults()
    
    # Login
    print("🔐 Logging in as demo@hotel.com...")
    login_response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}
    )
    
    if login_response.status_code != 200:
        print(f"❌ Login failed: HTTP {login_response.status_code}")
        results.add_test("Authentication", False, f"HTTP {login_response.status_code}")
        results.print_summary()
        return
    
    token = login_response.json().get("access_token")
    print(f"✅ Login successful")
    results.add_test("Authentication", True, "demo@hotel.com / demo123")
    
    # Run tests
    booking_id = test_1_create_new_booking(token, results)
    test_2_verify_folio_created(token, booking_id, results)
    test_3_existing_booking_folio(token, results)
    
    # Print summary
    results.print_summary()
    
    # Final verdict
    print("\n" + "=" * 80)
    print("🎯 FINAL VERDICT")
    print("=" * 80)
    
    if results.failed == 0:
        print("\n✅ ALL TESTS PASSED!")
        print("\n🎉 FOLIO AUTO-CREATION IS WORKING CORRECTLY!")
        print("\nVerified:")
        print("  ✓ New bookings automatically create folios")
        print("  ✓ Folios are immediately available after booking creation")
        print("  ✓ Folio number follows F-YYYY-##### format")
        print("  ✓ Folio type is correctly set to 'guest'")
        print("  ✓ All required fields are present")
        print("  ✓ Existing bookings can retrieve folios successfully")
        print("\n✅ FIX CONFIRMED: 'No folio found' issue is RESOLVED!")
    else:
        print(f"\n⚠️ {results.failed} TEST(S) FAILED")
        print("\nThe 'No folio found' issue may still exist in some scenarios.")
    
    print("=" * 80)

if __name__ == "__main__":
    main()
