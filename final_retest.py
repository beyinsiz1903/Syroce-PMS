#!/usr/bin/env python3
"""
FINAL Comprehensive Backend Re-Test
Testing all previously failing endpoints with REAL data
"""

import requests
import json
import time
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://perf-boost-37.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

def login():
    """Authenticate and get token"""
    print("🔐 Authenticating...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        tenant_id = data.get("user", {}).get("tenant_id")
        print(f"✅ Login successful - Tenant ID: {tenant_id}")
        return token, tenant_id
    else:
        print(f"❌ Login failed: {response.status_code}")
        return None, None

def get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_test_data(token):
    """Get existing guest and booking IDs"""
    headers = get_headers(token)
    
    # Get guest
    response = requests.get(f"{BASE_URL}/pms/guests?limit=1", headers=headers, timeout=10)
    guests = response.json() if response.status_code == 200 else []
    guest_id = guests[0]["id"] if guests else None
    
    # Get booking
    response = requests.get(f"{BASE_URL}/pms/bookings?limit=1", headers=headers, timeout=10)
    bookings = response.json() if response.status_code == 200 else []
    booking_id = bookings[0]["id"] if bookings else None
    
    print(f"✅ Test Data - Guest ID: {guest_id}, Booking ID: {booking_id}")
    return guest_id, booking_id

def test_endpoint(name, method, url, headers, data=None, params=None):
    """Test a single endpoint"""
    try:
        start = time.time()
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=15)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, params=params, timeout=15)
        elapsed = int((time.time() - start) * 1000)
        
        success = response.status_code == 200
        status_msg = f"HTTP {response.status_code} ({elapsed}ms)"
        
        if not success and response.text:
            error = response.text[:200]
            status_msg += f" - {error}"
        
        return success, status_msg
    except Exception as e:
        return False, f"Exception: {str(e)}"

def main():
    print("="*80)
    print("🔄 FINAL COMPREHENSIVE BACKEND RE-TEST")
    print("="*80)
    
    # Login
    token, tenant_id = login()
    if not token:
        return
    
    headers = get_headers(token)
    guest_id, booking_id = get_test_data(token)
    
    if not guest_id or not booking_id:
        print("❌ Cannot proceed without test data")
        return
    
    # Test Results
    results = {"passed": 0, "failed": 0, "tests": []}
    
    print("\n" + "="*80)
    print("🔍 TESTING PREVIOUSLY FAILING ENDPOINTS")
    print("="*80)
    
    # Test 1: Extra Charges
    print("\n1️⃣  POST /api/reservations/{booking_id}/extra-charges")
    success, msg = test_endpoint(
        "Extra Charges",
        "POST",
        f"{BASE_URL}/reservations/{booking_id}/extra-charges",
        headers,
        data={"charge_name": "Mini Bar", "charge_amount": 50.0, "notes": "Test"}
    )
    results["tests"].append(("Extra Charges", success, msg))
    if success:
        results["passed"] += 1
        print(f"   ✅ FIXED: {msg}")
    else:
        results["failed"] += 1
        print(f"   ❌ STILL FAILING: {msg}")
    
    # Test 2: Multi-Room
    print("\n2️⃣  POST /api/reservations/multi-room")
    success, msg = test_endpoint(
        "Multi-Room",
        "POST",
        f"{BASE_URL}/reservations/multi-room",
        headers,
        data={
            "group_name": "Family Reunion",
            "primary_booking_id": booking_id,
            "related_booking_ids": [booking_id]
        }
    )
    results["tests"].append(("Multi-Room", success, msg))
    if success:
        results["passed"] += 1
        print(f"   ✅ FIXED: {msg}")
    else:
        results["failed"] += 1
        print(f"   ❌ STILL FAILING: {msg}")
    
    # Test 3: Guest Preferences (Query Params)
    print("\n3️⃣  POST /api/guests/{guest_id}/preferences (Query Params)")
    success, msg = test_endpoint(
        "Guest Preferences",
        "POST",
        f"{BASE_URL}/guests/{guest_id}/preferences",
        headers,
        params={
            "pillow_type": "soft",
            "room_temperature": "22",
            "smoking": "false",
            "floor_preference": "high"
        }
    )
    results["tests"].append(("Guest Preferences", success, msg))
    if success:
        results["passed"] += 1
        print(f"   ✅ FIXED: {msg}")
    else:
        results["failed"] += 1
        print(f"   ❌ STILL FAILING: {msg}")
    
    # Test 4: Guest Tags (Query Params)
    print("\n4️⃣  POST /api/guests/{guest_id}/tags (Query Params)")
    success, msg = test_endpoint(
        "Guest Tags",
        "POST",
        f"{BASE_URL}/guests/{guest_id}/tags",
        headers,
        params={"tag": "vip"}
    )
    results["tests"].append(("Guest Tags", success, msg))
    if success:
        results["passed"] += 1
        print(f"   ✅ FIXED: {msg}")
    else:
        results["failed"] += 1
        print(f"   ❌ STILL FAILING: {msg}")
    
    # Test 5: OTA Details
    print("\n5️⃣  GET /api/reservations/{booking_id}/ota-details")
    success, msg = test_endpoint(
        "OTA Details",
        "GET",
        f"{BASE_URL}/reservations/{booking_id}/ota-details",
        headers
    )
    results["tests"].append(("OTA Details", success, msg))
    if success:
        results["passed"] += 1
        print(f"   ✅ FIXED: {msg}")
    else:
        results["failed"] += 1
        print(f"   ❌ STILL FAILING: {msg}")
    
    # Test 6: Messaging - Case Insensitive
    print("\n6️⃣  POST /api/messaging/send-message (Case-Insensitive Enum)")
    
    # 6a: UPPERCASE
    print("   6a. Testing UPPERCASE (WHATSAPP)")
    success_upper, msg_upper = test_endpoint(
        "Messaging UPPERCASE",
        "POST",
        f"{BASE_URL}/messaging/send-message",
        headers,
        data={
            "guest_id": guest_id,
            "message_type": "WHATSAPP",
            "recipient": "+905551234567",
            "message_content": "Test uppercase"
        }
    )
    results["tests"].append(("Messaging UPPERCASE", success_upper, msg_upper))
    if success_upper:
        results["passed"] += 1
        print(f"      ✅ FIXED: {msg_upper}")
    else:
        results["failed"] += 1
        print(f"      ❌ STILL FAILING: {msg_upper}")
    
    # 6b: lowercase
    print("   6b. Testing lowercase (whatsapp)")
    success_lower, msg_lower = test_endpoint(
        "Messaging lowercase",
        "POST",
        f"{BASE_URL}/messaging/send-message",
        headers,
        data={
            "guest_id": guest_id,
            "message_type": "whatsapp",
            "recipient": "+905551234567",
            "message_content": "Test lowercase"
        }
    )
    results["tests"].append(("Messaging lowercase", success_lower, msg_lower))
    if success_lower:
        results["passed"] += 1
        print(f"      ✅ FIXED: {msg_lower}")
    else:
        results["failed"] += 1
        print(f"      ❌ STILL FAILING: {msg_lower}")
    
    # 6c: MixedCase
    print("   6c. Testing MixedCase (WhatsApp)")
    success_mixed, msg_mixed = test_endpoint(
        "Messaging MixedCase",
        "POST",
        f"{BASE_URL}/messaging/send-message",
        headers,
        data={
            "guest_id": guest_id,
            "message_type": "WhatsApp",
            "recipient": "+905551234567",
            "message_content": "Test mixed"
        }
    )
    results["tests"].append(("Messaging MixedCase", success_mixed, msg_mixed))
    if success_mixed:
        results["passed"] += 1
        print(f"      ✅ FIXED: {msg_mixed}")
    else:
        results["failed"] += 1
        print(f"      ❌ STILL FAILING: {msg_mixed}")
    
    # Health Check
    print("\n" + "="*80)
    print("🏥 COMPREHENSIVE HEALTH CHECK (10 Endpoints)")
    print("="*80)
    
    health_tests = [
        ("Monitoring Health", "GET", f"{BASE_URL}/monitoring/health", None, None),
        ("PMS Rooms", "GET", f"{BASE_URL}/pms/rooms", None, {"limit": 10}),
        ("PMS Bookings", "GET", f"{BASE_URL}/pms/bookings", None, {"limit": 10}),
        ("PMS Guests", "GET", f"{BASE_URL}/pms/guests", None, {"limit": 10}),
        ("Companies", "GET", f"{BASE_URL}/companies", None, {"limit": 10}),
        ("Housekeeping Tasks", "GET", f"{BASE_URL}/housekeeping/tasks", None, None),
        ("RMS Demand Heatmap", "GET", f"{BASE_URL}/rms/demand-heatmap", None, None),
        ("Flash Report", "GET", f"{BASE_URL}/reports/flash-report", None, None),
        ("Arrivals Today", "GET", f"{BASE_URL}/arrivals/today", None, None),
        ("Executive KPI", "GET", f"{BASE_URL}/executive/kpi-snapshot", None, None)
    ]
    
    for name, method, url, data, params in health_tests:
        success, msg = test_endpoint(name, method, url, headers, data, params)
        results["tests"].append((name, success, msg))
        if success:
            results["passed"] += 1
            print(f"✅ {name}: {msg}")
        else:
            results["failed"] += 1
            print(f"❌ {name}: {msg}")
    
    # Summary
    print("\n" + "="*80)
    print("📊 FINAL SUMMARY")
    print("="*80)
    
    total = results["passed"] + results["failed"]
    success_rate = (results["passed"] / total * 100) if total > 0 else 0
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"📈 Success Rate: {success_rate:.1f}%")
    
    # Critical Fixes Status
    critical_tests = results["tests"][:8]  # First 8 are the critical ones
    critical_passed = sum(1 for _, success, _ in critical_tests if success)
    
    print(f"\n🔍 CRITICAL FIXES: {critical_passed}/8 Working ({critical_passed/8*100:.1f}%)")
    
    print("\n" + "="*80)
    print("🏁 RECOMMENDATION")
    print("="*80)
    
    if critical_passed == 8 and success_rate >= 90:
        print("✅ READY FOR PRODUCTION")
        print("   - All 8 critical fixes verified")
        print("   - Overall success rate exceeds 90%")
    elif critical_passed >= 6 and success_rate >= 85:
        print("⚠️  MOSTLY READY - Minor Issues")
        print(f"   - {critical_passed}/8 critical fixes working")
        print(f"   - Success rate: {success_rate:.1f}%")
    else:
        print("❌ NEEDS MORE WORK")
        print(f"   - Only {critical_passed}/8 critical fixes working")
        print(f"   - Success rate: {success_rate:.1f}%")
    
    print("="*80)

if __name__ == "__main__":
    main()
