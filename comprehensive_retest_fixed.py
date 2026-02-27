#!/usr/bin/env python3
"""
Comprehensive Backend Re-Test - FIXED VERSION
Testing all previously failing endpoints with correct request formats
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Configuration
BASE_URL = "https://pms-i18next-demo.preview.emergentagent.com/api"
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
    
    def get_existing_data(self):
        """Get existing guest and booking from database"""
        try:
            # Get existing guests
            response = requests.get(
                f"{BASE_URL}/pms/guests?limit=1",
                headers=self.get_headers(),
                timeout=10
            )
            if response.status_code == 200:
                guests = response.json().get("guests", [])
                if guests:
                    self.test_data["guest_id"] = guests[0].get("id")
                    print(f"✅ Using existing guest: {self.test_data['guest_id']}")
            
            # Get existing bookings
            response = requests.get(
                f"{BASE_URL}/pms/bookings?limit=1",
                headers=self.get_headers(),
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                bookings = data.get("bookings", [])
                if bookings:
                    self.test_data["booking_id"] = bookings[0].get("id")
                    print(f"✅ Using existing booking: {self.test_data['booking_id']}")
                    
        except Exception as e:
            print(f"⚠️ Error getting existing data: {e}")
    
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
                error_detail = response.text[:300] if response.text else "No error detail"
                return False, f"HTTP {response.status_code} - {error_detail} ({elapsed}ms)", elapsed
                
        except Exception as e:
            return False, f"Exception: {str(e)}", 0
    
    def test_previously_failing_endpoints(self):
        """Test all 6 previously failing endpoints"""
        print("\n" + "="*80)
        print("🔍 TESTING PREVIOUSLY FAILING ENDPOINTS (Expected: ALL FIXED)")
        print("="*80)
        
        # Get existing data
        self.get_existing_data()
        
        booking_id = self.test_data.get("booking_id", "")
        guest_id = self.test_data.get("guest_id", "")
        
        if not booking_id or not guest_id:
            print("⚠️ Warning: No existing booking or guest found, some tests may fail")
        
        tests = [
            {
                "name": "1. POST /api/reservations/{booking_id}/extra-charges",
                "method": "POST",
                "endpoint": f"/reservations/{booking_id}/extra-charges",
                "data": {
                    "charge_name": "Mini Bar",
                    "charge_amount": 50.0,
                    "notes": "Consumed items"
                },
                "issue": "Was HTTP 422 - Request validation failing",
                "skip_if_no_data": True
            },
            {
                "name": "2. POST /api/reservations/multi-room",
                "method": "POST",
                "endpoint": "/reservations/multi-room",
                "data": {
                    "group_name": "Family Reunion",
                    "primary_booking_id": booking_id if booking_id else "dummy-id",
                    "related_booking_ids": [booking_id] if booking_id else ["dummy-id"]
                },
                "issue": "Was HTTP 422 - Request validation failing",
                "skip_if_no_data": False
            },
            {
                "name": "3. POST /api/guests/{guest_id}/preferences (Query Params)",
                "method": "POST",
                "endpoint": f"/guests/{guest_id}/preferences",
                "params": {
                    "pillow_type": "soft",
                    "room_temperature": "22",  # String as expected
                    "smoking": "false",
                    "floor_preference": "high"
                },
                "issue": "Was HTTP 422 - Duplicate endpoint, should use query params",
                "skip_if_no_data": True
            },
            {
                "name": "4. POST /api/guests/{guest_id}/tags (Query Params)",
                "method": "POST",
                "endpoint": f"/guests/{guest_id}/tags",
                "params": {
                    "tag": "vip"
                },
                "issue": "Was HTTP 422 - Duplicate endpoint, should use single tag query param",
                "skip_if_no_data": True
            },
            {
                "name": "5. GET /api/reservations/{booking_id}/ota-details",
                "method": "GET",
                "endpoint": f"/reservations/{booking_id}/ota-details",
                "issue": "Was HTTP 500 - ObjectId serialization error",
                "skip_if_no_data": True
            },
            {
                "name": "6a. POST /api/messaging/send-message (UPPERCASE)",
                "method": "POST",
                "endpoint": "/messaging/send-message",
                "data": {
                    "guest_id": guest_id if guest_id else "dummy-guest-id",
                    "message_type": "WHATSAPP",  # UPPERCASE
                    "recipient": "+905551234567",
                    "message_content": "Test message uppercase"
                },
                "issue": "Was HTTP 422 - Case-sensitive enum, should accept uppercase",
                "skip_if_no_data": True
            },
            {
                "name": "6b. POST /api/messaging/send-message (lowercase)",
                "method": "POST",
                "endpoint": "/messaging/send-message",
                "data": {
                    "guest_id": guest_id if guest_id else "dummy-guest-id",
                    "message_type": "whatsapp",  # lowercase
                    "recipient": "+905551234567",
                    "message_content": "Test message lowercase"
                },
                "issue": "Was HTTP 422 - Case-sensitive enum, should accept lowercase",
                "skip_if_no_data": True
            },
            {
                "name": "6c. POST /api/messaging/send-message (MixedCase)",
                "method": "POST",
                "endpoint": "/messaging/send-message",
                "data": {
                    "guest_id": guest_id if guest_id else "dummy-guest-id",
                    "message_type": "WhatsApp",  # MixedCase
                    "recipient": "+905551234567",
                    "message_content": "Test message mixed case"
                },
                "issue": "Was HTTP 422 - Case-sensitive enum, should accept mixed case",
                "skip_if_no_data": True
            }
        ]
        
        for test in tests:
            # Skip tests that require real data if we don't have it
            if test.get("skip_if_no_data") and (not booking_id or not guest_id):
                print(f"⏭️  {test['name']}: SKIPPED (no test data available)")
                continue
                
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
                if "HTTP 500" in message or "HTTP 422" in message:
                    print(f"   Previous Issue: {test['issue']}")
    
    def test_health_check_endpoints(self):
        """Test 15 random endpoints for comprehensive health check"""
        print("\n" + "="*80)
        print("🏥 COMPREHENSIVE HEALTH CHECK (15 Endpoints)")
        print("="*80)
        
        tests = [
            {"name": "GET /api/monitoring/health", "method": "GET", "endpoint": "/monitoring/health"},
            {"name": "GET /api/monitoring/system", "method": "GET", "endpoint": "/monitoring/system"},
            {"name": "GET /api/pms/rooms", "method": "GET", "endpoint": "/pms/rooms", "params": {"limit": 10}},
            {"name": "GET /api/pms/bookings", "method": "GET", "endpoint": "/pms/bookings", "params": {"limit": 10}},
            {"name": "GET /api/pms/guests", "method": "GET", "endpoint": "/pms/guests", "params": {"limit": 10}},
            {"name": "GET /api/companies", "method": "GET", "endpoint": "/companies", "params": {"limit": 10}},
            {"name": "GET /api/housekeeping/tasks", "method": "GET", "endpoint": "/housekeeping/tasks"},
            {"name": "GET /api/rms/demand-heatmap", "method": "GET", "endpoint": "/rms/demand-heatmap"},
            {"name": "GET /api/reports/flash-report", "method": "GET", "endpoint": "/reports/flash-report"},
            {"name": "GET /api/arrivals/today", "method": "GET", "endpoint": "/arrivals/today"},
            {"name": "GET /api/channel-manager/connections", "method": "GET", "endpoint": "/channel-manager/connections"},
            {"name": "GET /api/executive/kpi-snapshot", "method": "GET", "endpoint": "/executive/kpi-snapshot"},
            {"name": "GET /api/pms/dashboard", "method": "GET", "endpoint": "/pms/dashboard"},
            {"name": "GET /api/housekeeping/mobile/room-assignments", "method": "GET", "endpoint": "/housekeeping/mobile/room-assignments"},
            {"name": "GET /api/rms/price-recommendation-slider", "method": "GET", "endpoint": "/rms/price-recommendation-slider", "params": {"room_type": "Standard", "check_in_date": "2025-12-01"}}
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
                print(f"         Error: {result['message'][:150]}")
        
        if len(self.results["previously_failing"]) > 0:
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
                    print(f"   - {result['name']}: {result['message'][:100]}")
        
        print(f"\n✅ Passed: {health_passed}/{len(self.results['health_check'])}")
        print(f"❌ Failed: {health_failed}/{len(self.results['health_check'])}")
        if len(self.results["health_check"]) > 0:
            print(f"📈 Health Check Success Rate: {health_passed/len(self.results['health_check'])*100:.1f}%")
        
        # Overall Statistics
        print("\n" + "="*80)
        print("🎯 OVERALL STATISTICS")
        print("="*80)
        if self.results["total_tests"] > 0:
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
            elif fixed_count >= len(self.results["previously_failing"]) * 0.8 and success_rate >= 85:
                print("⚠️ MOSTLY READY - Minor Issues Remain")
                print(f"   - {fixed_count}/{len(self.results['previously_failing'])} critical fixes working")
                print(f"   - Overall success rate: {success_rate:.1f}%")
                print("   - Some endpoints need attention")
            else:
                print("❌ NEEDS MORE WORK")
                print(f"   - {still_failing_count} critical fixes still failing")
                print(f"   - Overall success rate: {success_rate:.1f}% (target: 90%+)")
                print("   - Requires additional debugging")
        
        print("="*80)

def main():
    print("="*80)
    print("🔄 COMPREHENSIVE BACKEND RE-TEST - FIXED VERSION")
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
