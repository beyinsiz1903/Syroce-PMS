#!/usr/bin/env python3
"""
Opera Cloud Parity Features - Comprehensive Backend Test
Tests 3 critical feature sets: Night Audit, Cashiering & City Ledger, Queue Rooms
Total: 26 endpoints
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Configuration
BACKEND_URL = "https://app-audit-9.preview.emergentagent.com/api"
AUTH_EMAIL = "demo@hotel.com"
AUTH_PASSWORD = "demo123"

# Test results tracking
test_results = {
    "night_audit": [],
    "cashiering": [],
    "queue_rooms": [],
    "flows": []
}

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}\n")

def print_test(name: str, status: str, time_ms: float, details: str = ""):
    """Print test result"""
    icon = "✅" if status == "PASS" else "❌"
    print(f"{icon} {name}: {status} ({time_ms:.0f}ms)")
    if details:
        print(f"   {details}")

def login() -> str:
    """Login and get JWT token"""
    print_header("AUTHENTICATION")
    start = time.time()
    
    response = requests.post(
        f"{BACKEND_URL}/auth/login",
        json={"email": AUTH_EMAIL, "password": AUTH_PASSWORD},
        timeout=10
    )
    
    elapsed = (time.time() - start) * 1000
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        print_test("Login", "PASS", elapsed, f"Token obtained for {AUTH_EMAIL}")
        return token
    else:
        print_test("Login", "FAIL", elapsed, f"HTTP {response.status_code}")
        raise Exception("Authentication failed")

def test_endpoint(
    name: str,
    method: str,
    endpoint: str,
    headers: Dict,
    data: Dict = None,
    params: Dict = None,
    expected_status: int = 200
) -> Tuple[bool, float, Dict]:
    """Test a single endpoint"""
    start = time.time()
    
    try:
        url = f"{BACKEND_URL}{endpoint}"
        
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        elapsed = (time.time() - start) * 1000
        
        success = response.status_code == expected_status
        status = "PASS" if success else "FAIL"
        
        details = ""
        if not success:
            details = f"Expected HTTP {expected_status}, got {response.status_code}"
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    details += f" - {error_data.get('detail', 'No error details')}"
                except:
                    details += f" - {response.text[:100]}"
        
        print_test(name, status, elapsed, details)
        
        result_data = {}
        if response.status_code == 200:
            try:
                result_data = response.json()
            except:
                pass
        
        return success, elapsed, result_data
    
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print_test(name, "FAIL", elapsed, f"Exception: {str(e)}")
        return False, elapsed, {}

def test_night_audit_module(headers: Dict):
    """Test Night Audit Module (11 endpoints)"""
    print_header("NIGHT AUDIT MODULE - 11 ENDPOINTS")
    
    audit_date = "2025-11-26"
    audit_id = None
    
    # 1. Start Audit
    success, elapsed, data = test_endpoint(
        "1. POST /night-audit/start-audit",
        "POST",
        f"/night-audit/start-audit?audit_date={audit_date}",
        headers
    )
    test_results["night_audit"].append(("start-audit", success, elapsed))
    if success and data:
        audit_id = data.get("audit_id")
    
    # 2. Get Audit Status
    success, elapsed, data = test_endpoint(
        "2. GET /night-audit/status",
        "GET",
        f"/night-audit/status?audit_date={audit_date}",
        headers
    )
    test_results["night_audit"].append(("status", success, elapsed))
    
    # 3. Room Rate Posting
    success, elapsed, data = test_endpoint(
        "3. POST /night-audit/room-rate-posting",
        "POST",
        f"/night-audit/room-rate-posting?audit_date={audit_date}",
        headers
    )
    test_results["night_audit"].append(("room-rate-posting", success, elapsed))
    
    # 4. Tax Posting
    success, elapsed, data = test_endpoint(
        "4. POST /night-audit/tax-posting",
        "POST",
        f"/night-audit/tax-posting?audit_date={audit_date}&tax_rate=0.10",
        headers
    )
    test_results["night_audit"].append(("tax-posting", success, elapsed))
    
    # 5. Automatic Posting
    success, elapsed, data = test_endpoint(
        "5. POST /night-audit/automatic-posting",
        "POST",
        f"/night-audit/automatic-posting?audit_date={audit_date}",
        headers
    )
    test_results["night_audit"].append(("automatic-posting", success, elapsed))
    
    # 6. No-Show Handling
    success, elapsed, data = test_endpoint(
        "6. POST /night-audit/no-show-handling",
        "POST",
        f"/night-audit/no-show-handling?audit_date={audit_date}",
        headers
    )
    test_results["night_audit"].append(("no-show-handling", success, elapsed))
    
    # 7. Get Audit Report
    success, elapsed, data = test_endpoint(
        "7. GET /night-audit/audit-report",
        "GET",
        f"/night-audit/audit-report?audit_date={audit_date}",
        headers
    )
    test_results["night_audit"].append(("audit-report", success, elapsed))
    
    # 8. Get Audit Trail
    success, elapsed, data = test_endpoint(
        "8. GET /night-audit/audit-trail",
        "GET",
        "/night-audit/audit-trail",
        headers
    )
    test_results["night_audit"].append(("audit-trail", success, elapsed))
    
    # 9. Get Audit History
    success, elapsed, data = test_endpoint(
        "9. GET /night-audit/audit-history",
        "GET",
        "/night-audit/audit-history?limit=30",
        headers
    )
    test_results["night_audit"].append(("audit-history", success, elapsed))
    
    # 10. End of Day
    success, elapsed, data = test_endpoint(
        "10. POST /night-audit/end-of-day",
        "POST",
        f"/night-audit/end-of-day?audit_id={audit_id if audit_id else 'test-audit-id'}",
        headers
    )
    test_results["night_audit"].append(("end-of-day", success, elapsed))
    
    # 11. Rollback (if needed)
    success, elapsed, data = test_endpoint(
        "11. POST /night-audit/rollback",
        "POST",
        f"/night-audit/rollback?audit_id={audit_id if audit_id else 'test-audit-id'}",
        headers
    )
    test_results["night_audit"].append(("rollback", success, elapsed))

def test_cashiering_module(headers: Dict):
    """Test Cashiering & City Ledger Module (10 endpoints)"""
    print_header("CASHIERING & CITY LEDGER MODULE - 10 ENDPOINTS")
    
    account_id = None
    
    # 1. Create City Ledger Account
    success, elapsed, data = test_endpoint(
        "1. POST /cashiering/city-ledger",
        "POST",
        "/cashiering/city-ledger",
        headers,
        data={
            "account_name": "Test Corporate Account",
            "company_name": "Test Corp Ltd",
            "contact_person": "John Doe",
            "email": "john@testcorp.com",
            "phone": "+1234567890",
            "credit_limit": 50000.0,
            "payment_terms": 30
        }
    )
    test_results["cashiering"].append(("create-city-ledger", success, elapsed))
    if success and data:
        account_id = data.get("account_id") or data.get("id")
    
    # 2. List City Ledger Accounts
    success, elapsed, data = test_endpoint(
        "2. GET /cashiering/city-ledger",
        "GET",
        "/cashiering/city-ledger",
        headers
    )
    test_results["cashiering"].append(("list-city-ledger", success, elapsed))
    
    # If we don't have account_id from creation, try to get one from the list
    if not account_id and success and data:
        accounts = data.get("accounts", [])
        if accounts:
            account_id = accounts[0].get("id")
    
    # 3. Set Credit Limit (uses query parameters, not body)
    success, elapsed, data = test_endpoint(
        "3. POST /cashiering/credit-limit",
        "POST",
        f"/cashiering/credit-limit?account_id={account_id if account_id else 'test-account-id'}&credit_limit=75000.0",
        headers
    )
    test_results["cashiering"].append(("set-credit-limit", success, elapsed))
    
    # 4. Get Credit Limit
    success, elapsed, data = test_endpoint(
        "4. GET /cashiering/credit-limit/{account_id}",
        "GET",
        f"/cashiering/credit-limit/{account_id if account_id else 'test-account-id'}",
        headers
    )
    test_results["cashiering"].append(("get-credit-limit", success, elapsed))
    
    # 5. Direct Bill Posting (uses query parameters)
    success, elapsed, data = test_endpoint(
        "5. POST /cashiering/direct-bill",
        "POST",
        f"/cashiering/direct-bill?booking_id=test-booking-001&account_id={account_id if account_id else 'test-account-id'}&amount=1500.0&description=Room+charges+for+corporate+booking",
        headers
    )
    test_results["cashiering"].append(("direct-bill", success, elapsed))
    
    # 6. Split Payment (uses query parameter for booking_id and list of payments in body)
    success, elapsed, data = test_endpoint(
        "6. POST /cashiering/split-payment",
        "POST",
        "/cashiering/split-payment?booking_id=test-booking-001",
        headers,
        data=[
            {"payment_method": "cash", "amount": 500.0},
            {"payment_method": "card", "amount": 1000.0}
        ]
    )
    test_results["cashiering"].append(("split-payment", success, elapsed))
    
    # 7. Get Outstanding Balance
    success, elapsed, data = test_endpoint(
        "7. GET /cashiering/outstanding-balance",
        "GET",
        "/cashiering/outstanding-balance",
        headers
    )
    test_results["cashiering"].append(("outstanding-balance", success, elapsed))
    
    # 8. Get AR Aging Report
    success, elapsed, data = test_endpoint(
        "8. GET /cashiering/ar-aging-report",
        "GET",
        "/cashiering/ar-aging-report",
        headers
    )
    test_results["cashiering"].append(("ar-aging-report", success, elapsed))
    
    # 9. Post City Ledger Payment (uses query parameters)
    success, elapsed, data = test_endpoint(
        "9. POST /cashiering/city-ledger-payment",
        "POST",
        f"/cashiering/city-ledger-payment?account_id={account_id if account_id else 'test-account-id'}&amount=1000.0&payment_method=bank_transfer&reference=WIRE-2025-001",
        headers
    )
    test_results["cashiering"].append(("city-ledger-payment", success, elapsed))
    
    # 10. Get Account Transactions
    success, elapsed, data = test_endpoint(
        "10. GET /cashiering/city-ledger/{account_id}/transactions",
        "GET",
        f"/cashiering/city-ledger/{account_id if account_id else 'test-account-id'}/transactions",
        headers
    )
    test_results["cashiering"].append(("account-transactions", success, elapsed))

def test_queue_rooms_module(headers: Dict):
    """Test Queue Rooms Module (5 endpoints)"""
    print_header("QUEUE ROOMS MODULE - 5 ENDPOINTS")
    
    queue_id = None
    booking_id = None
    
    # First, create a test booking for the queue
    print("  Creating test booking for queue...")
    try:
        # Get a guest and room first
        guests_response = requests.get(
            f"{BACKEND_URL}/pms/guests?limit=1",
            headers=headers,
            timeout=10
        )
        rooms_response = requests.get(
            f"{BACKEND_URL}/pms/rooms?limit=1",
            headers=headers,
            timeout=10
        )
        
        if guests_response.status_code == 200 and rooms_response.status_code == 200:
            guests = guests_response.json().get("guests", [])
            rooms = rooms_response.json().get("rooms", [])
            
            if guests and rooms:
                guest_id = guests[0].get("id")
                room_id = rooms[0].get("id")
                
                # Create a booking
                booking_response = requests.post(
                    f"{BACKEND_URL}/pms/bookings",
                    headers=headers,
                    json={
                        "guest_id": guest_id,
                        "room_id": room_id,
                        "check_in": "2025-11-27",
                        "check_out": "2025-11-30",
                        "adults": 2,
                        "children": 0,
                        "guests_count": 2,
                        "total_amount": 1500.0,
                        "channel": "direct"
                    },
                    timeout=10
                )
                
                if booking_response.status_code == 200:
                    booking_data = booking_response.json()
                    booking_id = booking_data.get("booking", {}).get("id")
                    print(f"  ✅ Test booking created: {booking_id}")
    except Exception as e:
        print(f"  ⚠️  Could not create test booking: {e}")
    
    # 1. Add Guest to Queue (requires booking_id)
    success, elapsed, data = test_endpoint(
        "1. POST /rooms/queue/add",
        "POST",
        "/rooms/queue/add",
        headers,
        data={
            "booking_id": booking_id if booking_id else "test-booking-queue-001",
            "requested_room": "101",
            "arrival_time": "14:00",
            "special_requests": "Early check-in requested",
            "priority": 3
        }
    )
    test_results["queue_rooms"].append(("add-to-queue", success, elapsed))
    if success and data:
        queue_id = data.get("queue_id") or data.get("id")
    
    # 2. List Queue
    success, elapsed, data = test_endpoint(
        "2. GET /rooms/queue/list",
        "GET",
        "/rooms/queue/list",
        headers
    )
    test_results["queue_rooms"].append(("list-queue", success, elapsed))
    
    # If we don't have queue_id from creation, try to get one from the list
    if not queue_id and success and data:
        queue_items = data.get("queue", []) or data.get("items", [])
        if queue_items:
            queue_id = queue_items[0].get("id") or queue_items[0].get("queue_id")
    
    # 3. Assign Priority (uses query parameters)
    success, elapsed, data = test_endpoint(
        "3. POST /rooms/queue/assign-priority",
        "POST",
        f"/rooms/queue/assign-priority?queue_id={queue_id if queue_id else 'test-queue-id'}&priority=1",
        headers
    )
    test_results["queue_rooms"].append(("assign-priority", success, elapsed))
    
    # 4. Notify Guest (uses query parameters)
    success, elapsed, data = test_endpoint(
        "4. POST /rooms/queue/notify-guest",
        "POST",
        f"/rooms/queue/notify-guest?queue_id={queue_id if queue_id else 'test-queue-id'}&room_number=101",
        headers
    )
    test_results["queue_rooms"].append(("notify-guest", success, elapsed))
    
    # 5. Remove from Queue
    success, elapsed, data = test_endpoint(
        "5. DELETE /rooms/queue/{queue_id}",
        "DELETE",
        f"/rooms/queue/{queue_id if queue_id else 'test-queue-id'}",
        headers
    )
    test_results["queue_rooms"].append(("remove-from-queue", success, elapsed))

def test_complete_flows(headers: Dict):
    """Test complete business flows"""
    print_header("COMPLETE FLOW TESTING")
    
    # Flow 1: Night Audit Complete Flow
    print("\n📋 Flow 1: Night Audit Complete Cycle")
    audit_date = "2025-11-27"
    flow_success = True
    
    steps = [
        ("Start Audit", "POST", f"/night-audit/start-audit?audit_date={audit_date}"),
        ("Post Room Rates", "POST", f"/night-audit/room-rate-posting?audit_date={audit_date}"),
        ("Post Taxes", "POST", f"/night-audit/tax-posting?audit_date={audit_date}&tax_rate=0.10"),
        ("Handle No-Shows", "POST", f"/night-audit/no-show-handling?audit_date={audit_date}"),
        ("Get Report", "GET", f"/night-audit/audit-report?audit_date={audit_date}"),
    ]
    
    for step_name, method, endpoint in steps:
        success, elapsed, _ = test_endpoint(f"  {step_name}", method, endpoint, headers)
        if not success:
            flow_success = False
    
    test_results["flows"].append(("Night Audit Flow", flow_success))
    
    # Flow 2: City Ledger Complete Flow
    print("\n📋 Flow 2: City Ledger Account Management")
    flow_success = True
    
    # Create account
    success, elapsed, data = test_endpoint(
        "  Create Account",
        "POST",
        "/cashiering/city-ledger",
        headers,
        data={
            "account_name": "Flow Test Corp",
            "company_name": "Flow Test Ltd",
            "contact_person": "Test Manager",
            "email": "manager@flowtest.com",
            "phone": "+1234567890",
            "credit_limit": 100000.0,
            "payment_terms": 30
        }
    )
    if not success:
        flow_success = False
    
    account_id = data.get("account_id") or data.get("id") if data else "test-id"
    
    # Post charges
    success, elapsed, _ = test_endpoint(
        "  Post Charges",
        "POST",
        f"/cashiering/direct-bill?booking_id=flow-test-booking&account_id={account_id}&amount=5000.0&description=Monthly+corporate+charges",
        headers
    )
    if not success:
        flow_success = False
    
    # Check balance
    success, elapsed, _ = test_endpoint(
        "  Check Balance",
        "GET",
        "/cashiering/outstanding-balance",
        headers
    )
    if not success:
        flow_success = False
    
    # Post payment
    success, elapsed, _ = test_endpoint(
        "  Post Payment",
        "POST",
        f"/cashiering/city-ledger-payment?account_id={account_id}&amount=5000.0&payment_method=bank_transfer&reference=FLOW-PAY-001",
        headers
    )
    if not success:
        flow_success = False
    
    test_results["flows"].append(("City Ledger Flow", flow_success))
    
    # Flow 3: Queue Rooms Complete Flow
    print("\n📋 Flow 3: Queue Rooms Management")
    flow_success = True
    
    # Get a test booking for queue
    try:
        guests_response = requests.get(f"{BACKEND_URL}/pms/guests?limit=1", headers=headers, timeout=10)
        rooms_response = requests.get(f"{BACKEND_URL}/pms/rooms?limit=1", headers=headers, timeout=10)
        
        flow_booking_id = None
        if guests_response.status_code == 200 and rooms_response.status_code == 200:
            guests = guests_response.json().get("guests", [])
            rooms = rooms_response.json().get("rooms", [])
            
            if guests and rooms:
                booking_response = requests.post(
                    f"{BACKEND_URL}/pms/bookings",
                    headers=headers,
                    json={
                        "guest_id": guests[0].get("id"),
                        "room_id": rooms[0].get("id"),
                        "check_in": "2025-11-28",
                        "check_out": "2025-11-30",
                        "adults": 2,
                        "children": 0,
                        "guests_count": 2,
                        "total_amount": 1200.0,
                        "channel": "direct"
                    },
                    timeout=10
                )
                if booking_response.status_code == 200:
                    flow_booking_id = booking_response.json().get("booking", {}).get("id")
    except:
        pass
    
    # Add to queue
    success, elapsed, data = test_endpoint(
        "  Add to Queue",
        "POST",
        "/rooms/queue/add",
        headers,
        data={
            "booking_id": flow_booking_id if flow_booking_id else "flow-test-booking",
            "requested_room": "102",
            "arrival_time": "15:00",
            "special_requests": "VIP guest",
            "priority": 2
        }
    )
    if not success:
        flow_success = False
    
    queue_id = data.get("queue_id") or data.get("id") if data else "test-queue-id"
    
    # Check list
    success, elapsed, _ = test_endpoint(
        "  Check Queue List",
        "GET",
        "/rooms/queue/list",
        headers
    )
    if not success:
        flow_success = False
    
    # Assign priority
    success, elapsed, _ = test_endpoint(
        "  Assign Priority",
        "POST",
        f"/rooms/queue/assign-priority?queue_id={queue_id}&priority=1",
        headers
    )
    if not success:
        flow_success = False
    
    # Notify guest
    success, elapsed, _ = test_endpoint(
        "  Notify Guest",
        "POST",
        f"/rooms/queue/notify-guest?queue_id={queue_id}&room_number=102",
        headers
    )
    if not success:
        flow_success = False
    
    test_results["flows"].append(("Queue Rooms Flow", flow_success))

def print_summary():
    """Print comprehensive test summary"""
    print_header("TEST SUMMARY - OPERA CLOUD PARITY FEATURES")
    
    # Night Audit Summary
    print("\n🌙 NIGHT AUDIT MODULE (11 endpoints):")
    passed = sum(1 for _, success, _ in test_results["night_audit"] if success)
    total = len(test_results["night_audit"])
    avg_time = sum(elapsed for _, _, elapsed in test_results["night_audit"]) / total if total > 0 else 0
    
    for name, success, elapsed in test_results["night_audit"]:
        status = "✅ WORKING" if success else "❌ FAILING"
        print(f"  {status}: {name} ({elapsed:.0f}ms)")
    
    print(f"\n  Success Rate: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  Average Response Time: {avg_time:.0f}ms")
    
    # Cashiering Summary
    print("\n💰 CASHIERING & CITY LEDGER MODULE (10 endpoints):")
    passed = sum(1 for _, success, _ in test_results["cashiering"] if success)
    total = len(test_results["cashiering"])
    avg_time = sum(elapsed for _, _, elapsed in test_results["cashiering"]) / total if total > 0 else 0
    
    for name, success, elapsed in test_results["cashiering"]:
        status = "✅ WORKING" if success else "❌ FAILING"
        print(f"  {status}: {name} ({elapsed:.0f}ms)")
    
    print(f"\n  Success Rate: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  Average Response Time: {avg_time:.0f}ms")
    
    # Queue Rooms Summary
    print("\n🚪 QUEUE ROOMS MODULE (5 endpoints):")
    passed = sum(1 for _, success, _ in test_results["queue_rooms"] if success)
    total = len(test_results["queue_rooms"])
    avg_time = sum(elapsed for _, _, elapsed in test_results["queue_rooms"]) / total if total > 0 else 0
    
    for name, success, elapsed in test_results["queue_rooms"]:
        status = "✅ WORKING" if success else "❌ FAILING"
        print(f"  {status}: {name} ({elapsed:.0f}ms)")
    
    print(f"\n  Success Rate: {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"  Average Response Time: {avg_time:.0f}ms")
    
    # Flow Testing Summary
    print("\n🔄 COMPLETE FLOW TESTING:")
    for flow_name, success in test_results["flows"]:
        status = "✅ WORKING" if success else "❌ FAILING"
        print(f"  {status}: {flow_name}")
    
    # Overall Summary
    print("\n" + "="*80)
    total_endpoints = (
        len(test_results["night_audit"]) +
        len(test_results["cashiering"]) +
        len(test_results["queue_rooms"])
    )
    total_passed = (
        sum(1 for _, success, _ in test_results["night_audit"] if success) +
        sum(1 for _, success, _ in test_results["cashiering"] if success) +
        sum(1 for _, success, _ in test_results["queue_rooms"] if success)
    )
    
    all_times = (
        [elapsed for _, _, elapsed in test_results["night_audit"]] +
        [elapsed for _, _, elapsed in test_results["cashiering"]] +
        [elapsed for _, _, elapsed in test_results["queue_rooms"]]
    )
    overall_avg_time = sum(all_times) / len(all_times) if all_times else 0
    
    print(f"\n📊 OVERALL RESULTS:")
    print(f"  Total Endpoints Tested: {total_endpoints}")
    print(f"  Endpoints Passing: {total_passed}")
    print(f"  Endpoints Failing: {total_endpoints - total_passed}")
    print(f"  Success Rate: {total_passed}/{total_endpoints} ({total_passed/total_endpoints*100:.1f}%)")
    print(f"  Average Response Time: {overall_avg_time:.0f}ms")
    print(f"  Performance Target (<100ms): {'✅ ACHIEVED' if overall_avg_time < 100 else '❌ NOT MET'}")
    
    flows_passed = sum(1 for _, success in test_results["flows"] if success)
    flows_total = len(test_results["flows"])
    print(f"\n  Complete Flows Passing: {flows_passed}/{flows_total}")
    
    if total_passed == total_endpoints and flows_passed == flows_total:
        print(f"\n🎉 OPERA CLOUD PARITY ACHIEVED - 100% SUCCESS RATE! 🚀")
    elif total_passed / total_endpoints >= 0.9:
        print(f"\n⚠️  MOSTLY READY - {total_endpoints - total_passed} endpoints need attention")
    else:
        print(f"\n❌ CRITICAL ISSUES - {total_endpoints - total_passed} endpoints failing")
    
    print("="*80 + "\n")

def main():
    """Main test execution"""
    print_header("OPERA CLOUD PARITY FEATURES - COMPREHENSIVE TEST")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Authentication: {AUTH_EMAIL}")
    
    try:
        # Login
        token = login()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test all modules
        test_night_audit_module(headers)
        test_cashiering_module(headers)
        test_queue_rooms_module(headers)
        
        # Test complete flows
        test_complete_flows(headers)
        
        # Print summary
        print_summary()
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
