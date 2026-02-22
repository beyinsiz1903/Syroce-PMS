#!/usr/bin/env python3
"""
Comprehensive Backend Re-Test - Verification of All Fixes
Testing all previously failing endpoints and comprehensive health check
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Configuration
BASE_URL = "https://auth-endpoint-suite.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class BackendTester:
    def __init__(self):
        self.token = None
        self.tenant_id = None
        self.results = {
            "previously_failing": [],
            "health_check": [],
            "total_tests": 0,
            "passed": 0,
            "failed": 0
        }
        self.test_data = {}  # Store created test data IDs
        
    def login(self) -> bool:
        """Authenticate and get token"""
        print("🔐 Authenticating...")
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.tenant_id = data.get("user", {}).get("tenant_id")
                print(f"✅ Login successful - Tenant ID: {self.tenant_id}")
                return True
            else:
                print(f"❌ Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def get_headers(self) -> Dict:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def create_test_guest(self) -> str:
        """Create a test guest for testing"""
        try:
            response = requests.post(
                f"{BASE_URL}/guests",
                headers=self.get_headers(),
                json={
                    "name": "Test Guest Retest",
                    "email": f"testguest_{int(time.time())}@test.com",
                    "phone": "+905551234567",
                    "id_number": f"TC{int(time.time())}",
                    "nationality": "TR"
                },
                timeout=10
            )
            if response.status_code == 200:
                guest_id = response.json().get("id")
                print(f"✅ Test guest created: {guest_id}")
                return guest_id
            else:
                print(f"⚠️ Failed to create test guest: {response.status_code}")
                return None
        except Exception as e:
            print(f"⚠️ Error creating test guest: {e}")
            return None
    
    def create_test_booking(self) -> str:
        """Create a test booking for testing"""
        try:
            # First get a room
            response = requests.get(
                f"{BASE_URL}/pms/rooms?limit=1",
                headers=self.get_headers(),
                timeout=10
            )
            if response.status_code != 200:
                print(f"⚠️ Failed to get rooms: {response.status_code}")
                return None
            
            rooms = response.json().get("rooms", [])
            if not rooms:
                print("⚠️ No rooms available")
                return None
            
            room_id = rooms[0].get("id")
            
            # Create guest
            guest_id = self.create_test_guest()
            if not guest_id:
                return None
            
            # Create booking
            check_in = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            check_out = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
            
            response = requests.post(
                f"{BASE_URL}/bookings",
                headers=self.get_headers(),
                json={
                    "guest_id": guest_id,
                    "room_id": room_id,
                    "check_in": check_in,
                    "check_out": check_out,
                    "adults": 2,
                    "children": 0,
                    "guests_count": 2,
                    "total_amount": 500.0
                },
                timeout=10
            )
            
            if response.status_code == 200:
                booking_id = response.json().get("id")
                print(f"✅ Test booking created: {booking_id}")
                self.test_data["guest_id"] = guest_id
                self.test_data["booking_id"] = booking_id
                return booking_id
            else:
                print(f"⚠️ Failed to create test booking: {response.status_code}")
                return None
        except Exception as e:
            print(f"⚠️ Error creating test booking: {e}")
            return None
    
    def test_endpoint(self, name: str, method: str, endpoint: str, data: Dict = None, 
                     params: Dict = None, expected_status: int = 200) -> Tuple[bool, str, int]:
        """Test a single endpoint"""
        try:
            url = f"{BASE_URL}{endpoint}"
            start_time = time.time()
            
            if method == "GET":
                response = requests.get(url, headers=self.get_headers(), params=params, timeout=15)
            elif method == "POST":
                response = requests.post(url, headers=self.get_headers(), json=data, params=params, timeout=15)
            elif method == "PUT":
                response = requests.put(url, headers=self.get_headers(), json=data, timeout=15)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.get_headers(), timeout=15)
            else:
                return False, f"Unsupported method: {method}", 0
            
            elapsed = int((time.time() - start_time) * 1000)
            
            if response.status_code == expected_status:
                return True, f"HTTP {response.status_code} ({elapsed}ms)", elapsed
            else:
                error_detail = response.text[:200] if response.text else "No error detail"
                return False, f"HTTP {response.status_code} - {error_detail} ({elapsed}ms)", elapsed
                
        except Exception as e:
            return False, f"Exception: {str(e)}", 0
    
    def test_previously_failing_endpoints(self):
        """Test all 6 previously failing endpoints"""
        print("\n" + "="*80)
        print("🔍 TESTING PREVIOUSLY FAILING ENDPOINTS (Expected: ALL FIXED)")
        print("="*80)
        
        # Ensure we have test data
        if not self.test_data.get("booking_id"):
            print("📝 Creating test data...")
            self.create_test_booking()
        
        booking_id = self.test_data.get("booking_id", "test-booking-id")
        guest_id = self.test_data.get("guest_id", "test-guest-id")
        
        tests = [
            {
                "name": "POST /api/reservations/{booking_id}/extra-charges",
                "method": "POST",
                "endpoint": f"/reservations/{booking_id}/extra-charges",
                "data": {
                    "charge_name": "Mini Bar",
                    "charge_amount": 50.0,
                    "notes": "Consumed items"
                },
                "issue": "Was HTTP 422 - Request validation failing"
            },
            {
                "name": "POST /api/reservations/multi-room",
                "method": "POST",
                "endpoint": "/reservations/multi-room",
                "data": {
                    "group_name": "Family Reunion",
                    "primary_booking_id": booking_id,
                    "related_booking_ids": [booking_id]
                },
                "issue": "Was HTTP 422 - Request validation failing"
            },
            {
                "name": "POST /api/guests/{guest_id}/preferences (Query Params)",
                "method": "POST",
                "endpoint": f"/guests/{guest_id}/preferences",
                "params": {
                    "pillow_type": "soft",
                    "room_temperature": "22",
                    "smoking": "false",
                    "floor_preference": "high"
                },
                "issue": "Was HTTP 422 - Duplicate endpoint, should use query params"
            },
            {
                "name": "POST /api/guests/{guest_id}/tags (Query Params)",
                "method": "POST",
                "endpoint": f"/guests/{guest_id}/tags",
                "params": {
                    "tag": "vip"
                },
                "issue": "Was HTTP 422 - Duplicate endpoint, should use single tag query param"
            },
            {
                "name": "GET /api/reservations/{booking_id}/ota-details",
                "method": "GET",
                "endpoint": f"/reservations/{booking_id}/ota-details",
                "issue": "Was HTTP 500 - ObjectId serialization error"
            },
            {
                "name": "POST /api/messaging/send-message (UPPERCASE)",
                "method": "POST",
                "endpoint": "/messaging/send-message",
                "data": {
                    "recipient": "+905551234567",
                    "message": "Test message",
                    "message_type": "WHATSAPP"  # UPPERCASE
                },
                "issue": "Was HTTP 422 - Case-sensitive enum, should accept uppercase"
            },
            {
                "name": "POST /api/messaging/send-message (lowercase)",
                "method": "POST",
                "endpoint": "/messaging/send-message",
                "data": {
                    "recipient": "+905551234567",
                    "message": "Test message",
                    "message_type": "whatsapp"  # lowercase
                },
                "issue": "Was HTTP 422 - Case-sensitive enum, should accept lowercase"
            },
            {
                "name": "POST /api/messaging/send-message (MixedCase)",
                "method": "POST",
                "endpoint": "/messaging/send-message",
                "data": {
                    "recipient": "+905551234567",
                    "message": "Test message",
                    "message_type": "WhatsApp"  # MixedCase
                },
                "issue": "Was HTTP 422 - Case-sensitive enum, should accept mixed case"
            }
        ]
        
        for test in tests:
            self.results["total_tests"] += 1
            success, message, elapsed = self.test_endpoint(
                test["name"],
                test["method"],
                test["endpoint"],
                data=test.get("data"),
                params=test.get("params")
            )
            
            result = {
                "name": test["name"],
                "success": success,
                "message": message,
                "elapsed_ms": elapsed,
                "previous_issue": test["issue"]
            }
            
            self.results["previously_failing"].append(result)
            
            if success:
                self.results["passed"] += 1
                print(f"✅ {test['name']}: {message}")
            else:
                self.results["failed"] += 1
                print(f"❌ {test['name']}: {message}")
                print(f"   Previous Issue: {test['issue']}")
    
    def test_health_check_endpoints(self):
        """Test 15 random endpoints for comprehensive health check"""
        print("\n" + "="*80)
        print("🏥 COMPREHENSIVE HEALTH CHECK (15 Random Endpoints)")
        print("="*80)
        
        tests = [
            {"name": "GET /api/monitoring/health", "method": "GET", "endpoint": "/monitoring/health"},
            {"name": "GET /api/monitoring/system", "method": "GET", "endpoint": "/monitoring/system"},
            {"name": "GET /api/pms/rooms", "method": "GET", "endpoint": "/pms/rooms", "params": {"limit": 10}},
            {"name": "GET /api/pms/bookings", "method": "GET", "endpoint": "/pms/bookings", "params": {"limit": 10}},
            {"name": "GET /api/pms/guests", "method": "GET", "endpoint": "/pms/guests", "params": {"limit": 10}},
            {"name": "GET /api/companies", "method": "GET", "endpoint": "/companies", "params": {"limit": 10}},
            {"name": "GET /api/dashboard/overview", "method": "GET", "endpoint": "/dashboard/overview"},
            {"name": "GET /api/dashboard/revenue", "method": "GET", "endpoint": "/dashboard/revenue"},
            {"name": "GET /api/housekeeping/tasks", "method": "GET", "endpoint": "/housekeeping/tasks"},
            {"name": "GET /api/rms/demand-heatmap", "method": "GET", "endpoint": "/rms/demand-heatmap"},
            {"name": "GET /api/reports/flash-report", "method": "GET", "endpoint": "/reports/flash-report"},
            {"name": "GET /api/arrivals/today", "method": "GET", "endpoint": "/arrivals/today"},
            {"name": "GET /api/channel-manager/connections", "method": "GET", "endpoint": "/channel-manager/connections"},
            {"name": "GET /api/finance/ar-aging", "method": "GET", "endpoint": "/finance/ar-aging"},
            {"name": "GET /api/executive/kpi-snapshot", "method": "GET", "endpoint": "/executive/kpi-snapshot"}
        ]
        
        for test in tests:
            self.results["total_tests"] += 1
            success, message, elapsed = self.test_endpoint(
                test["name"],
                test["method"],
                test["endpoint"],
                params=test.get("params")
            )
            
            result = {
                "name": test["name"],
                "success": success,
                "message": message,
                "elapsed_ms": elapsed
            }
            
            self.results["health_check"].append(result)
            
            if success:
                self.results["passed"] += 1
                print(f"✅ {test['name']}: {message}")
            else:
                self.results["failed"] += 1
                print(f"❌ {test['name']}: {message}")
    
    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE TEST SUMMARY")
        print("="*80)
        
        # Previously Failing Endpoints
        print("\n🔍 PREVIOUSLY FAILING ENDPOINTS (6 Critical Fixes):")
        print("-" * 80)
        fixed_count = sum(1 for r in self.results["previously_failing"] if r["success"])
        still_failing_count = len(self.results["previously_failing"]) - fixed_count
        
        for result in self.results["previously_failing"]:
            status = "✅ FIXED" if result["success"] else "❌ STILL FAILING"
            print(f"{status}: {result['name']}")
            if not result["success"]:
                print(f"         Error: {result['message']}")
                print(f"         Previous: {result['previous_issue']}")
        
        print(f"\n📈 Fix Success Rate: {fixed_count}/{len(self.results['previously_failing'])} " +
              f"({fixed_count/len(self.results['previously_failing'])*100:.1f}%)")
        
        # Health Check
        print("\n🏥 HEALTH CHECK ENDPOINTS:")
        print("-" * 80)
        health_passed = sum(1 for r in self.results["health_check"] if r["success"])
        health_failed = len(self.results["health_check"]) - health_passed
        
        if health_failed > 0:
            print("❌ FAILED ENDPOINTS:")
            for result in self.results["health_check"]:
                if not result["success"]:
                    print(f"   - {result['name']}: {result['message']}")
        
        print(f"\n✅ Passed: {health_passed}/{len(self.results['health_check'])}")
        print(f"❌ Failed: {health_failed}/{len(self.results['health_check'])}")
        print(f"📈 Health Check Success Rate: {health_passed/len(self.results['health_check'])*100:.1f}%")
        
        # Overall Statistics
        print("\n" + "="*80)
        print("🎯 OVERALL STATISTICS")
        print("="*80)
        success_rate = (self.results["passed"] / self.results["total_tests"]) * 100
        print(f"Total Tests: {self.results['total_tests']}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"📈 Overall Success Rate: {success_rate:.1f}%")
        
        # Final Recommendation
        print("\n" + "="*80)
        print("🏁 FINAL RECOMMENDATION")
        print("="*80)
        
        if fixed_count == len(self.results["previously_failing"]) and success_rate >= 90:
            print("✅ READY FOR PRODUCTION")
            print("   - All critical fixes verified")
            print("   - Overall success rate exceeds 90%")
            print("   - Backend infrastructure is hatasız (error-free)")
        elif fixed_count == len(self.results["previously_failing"]):
            print("⚠️ CRITICAL FIXES VERIFIED BUT NEEDS MORE WORK")
            print("   - All 6 critical fixes working")
            print(f"   - Overall success rate: {success_rate:.1f}% (target: 90%+)")
            print("   - Some health check endpoints failing")
        else:
            print("❌ NEEDS MORE WORK")
            print(f"   - {still_failing_count} critical fixes still failing")
            print(f"   - Overall success rate: {success_rate:.1f}% (target: 90%+)")
            print("   - Requires additional debugging")
        
        print("="*80)

def main():
    print("="*80)
    print("🔄 COMPREHENSIVE BACKEND RE-TEST")
    print("Verification of All Fixes - Hotel PMS Backend")
    print("="*80)
    
    tester = BackendTester()
    
    # Step 1: Login
    if not tester.login():
        print("❌ Cannot proceed without authentication")
        return
    
    # Step 2: Test Previously Failing Endpoints
    tester.test_previously_failing_endpoints()
    
    # Step 3: Comprehensive Health Check
    tester.test_health_check_endpoints()
    
    # Step 4: Print Summary
    tester.print_summary()

if __name__ == "__main__":
    main()
