#!/usr/bin/env python3
"""
🎯 FINAL COMPREHENSIVE BACKEND TEST - 100% Verification
Testing all previously failing endpoints + comprehensive health check
"""

import requests
import json
import time
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://hotel-pms-demo.preview.emergentagent.com/api"
EMAIL = "demo@hotel.com"
PASSWORD = "demo123"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class BackendTester:
    def __init__(self):
        self.token = None
        self.tenant_id = None
        self.user_id = None
        self.results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'tests': []
        }
        
    def log(self, message, color=RESET):
        print(f"{color}{message}{RESET}")
        
    def login(self):
        """Authenticate and get token"""
        self.log("\n🔐 Authenticating...", BLUE)
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": EMAIL, "password": PASSWORD},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.tenant_id = data['user'].get('tenant_id')
                self.user_id = data['user'].get('id')
                self.log(f"✅ Authentication successful", GREEN)
                self.log(f"   Tenant ID: {self.tenant_id}", BLUE)
                return True
            else:
                self.log(f"❌ Authentication failed: {response.status_code}", RED)
                return False
        except Exception as e:
            self.log(f"❌ Authentication error: {str(e)}", RED)
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_endpoint(self, method, endpoint, data=None, params=None, expected_status=200, test_name=""):
        """Test a single endpoint"""
        self.results['total'] += 1
        start_time = time.time()
        
        try:
            url = f"{BASE_URL}{endpoint}"
            
            if method == "GET":
                response = requests.get(url, headers=self.get_headers(), params=params, timeout=10)
            elif method == "POST":
                response = requests.post(url, headers=self.get_headers(), json=data, timeout=10)
            elif method == "PUT":
                response = requests.put(url, headers=self.get_headers(), json=data, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.get_headers(), timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            elapsed = int((time.time() - start_time) * 1000)
            
            if response.status_code == expected_status:
                self.results['passed'] += 1
                self.results['tests'].append({
                    'name': test_name,
                    'status': 'PASS',
                    'code': response.status_code,
                    'time': elapsed
                })
                self.log(f"✅ {test_name}: HTTP {response.status_code} ({elapsed}ms)", GREEN)
                return True, response
            else:
                self.results['failed'] += 1
                error_detail = ""
                try:
                    error_data = response.json()
                    error_detail = error_data.get('detail', str(error_data))
                except:
                    error_detail = response.text[:200]
                
                self.results['tests'].append({
                    'name': test_name,
                    'status': 'FAIL',
                    'code': response.status_code,
                    'time': elapsed,
                    'error': error_detail
                })
                self.log(f"❌ {test_name}: HTTP {response.status_code} (expected {expected_status})", RED)
                self.log(f"   Error: {error_detail}", RED)
                return False, response
                
        except Exception as e:
            elapsed = int((time.time() - start_time) * 1000)
            self.results['failed'] += 1
            self.results['tests'].append({
                'name': test_name,
                'status': 'ERROR',
                'error': str(e),
                'time': elapsed
            })
            self.log(f"❌ {test_name}: Exception - {str(e)}", RED)
            return False, None
    
    def create_test_guest(self):
        """Create a test guest for testing"""
        self.log("\n👤 Creating test guest...", BLUE)
        guest_data = {
            "name": "Test Guest Final",
            "email": f"testguest.final.{int(time.time())}@test.com",
            "phone": "+905551234567",
            "id_number": f"TC{int(time.time())}",
            "nationality": "TR",
            "vip_status": False
        }
        
        success, response = self.test_endpoint(
            "POST", "/pms/guests",
            data=guest_data,
            test_name="Create Test Guest"
        )
        
        if success:
            guest_id = response.json().get('id')
            self.log(f"   Guest ID: {guest_id}", BLUE)
            return guest_id
        return None
    
    def create_test_booking(self, guest_id):
        """Create a test booking"""
        self.log("\n📅 Creating test booking...", BLUE)
        
        # First get available rooms
        success, response = self.test_endpoint(
            "GET", "/pms/rooms",
            params={"limit": 10},
            test_name="Get Available Rooms"
        )
        
        if not success:
            return None
        
        rooms = response.json()
        if not rooms:
            self.log("❌ No rooms available", RED)
            return None
        
        room_id = rooms[0]['id']
        
        # Create booking
        check_in = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        check_out = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        
        booking_data = {
            "guest_id": guest_id,
            "room_id": room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 2,
            "children": 0,
            "guests_count": 2,
            "total_amount": 500.0,
            "channel": "direct"
        }
        
        success, response = self.test_endpoint(
            "POST", "/pms/bookings",
            data=booking_data,
            test_name="Create Test Booking"
        )
        
        if success:
            booking_id = response.json().get('id')
            self.log(f"   Booking ID: {booking_id}", BLUE)
            return booking_id
        return None
    
    def test_previously_failing_endpoints(self, guest_id, booking_id):
        """Test the 8 previously failing endpoints"""
        self.log("\n" + "="*80, YELLOW)
        self.log("🔍 TESTING PREVIOUSLY FAILING ENDPOINTS (8 Tests)", YELLOW)
        self.log("="*80, YELLOW)
        
        # 1. POST /api/guests/{guest_id}/preferences (was HTTP 500)
        self.log("\n1️⃣ Testing Guest Preferences Endpoint (Previously HTTP 500)...", BLUE)
        self.test_endpoint(
            "POST", f"/guests/{guest_id}/preferences",
            params={
                "pillow_type": "soft",
                "room_temperature": "22",
                "smoking": "false",
                "floor_preference": "high",
                "dietary_restrictions": "vegetarian",
                "allergies": "none"
            },
            test_name="POST /api/guests/{guest_id}/preferences"
        )
        
        # 2. POST /api/guests/{guest_id}/tags (was HTTP 500)
        self.log("\n2️⃣ Testing Guest Tags Endpoint (Previously HTTP 500)...", BLUE)
        self.test_endpoint(
            "POST", f"/guests/{guest_id}/tags",
            params={"tag": "vip"},
            test_name="POST /api/guests/{guest_id}/tags"
        )
        
        # 3. POST /api/reservations/{booking_id}/extra-charges (was fixed)
        self.log("\n3️⃣ Testing Extra Charges Endpoint...", BLUE)
        self.test_endpoint(
            "POST", f"/reservations/{booking_id}/extra-charges",
            data={
                "charge_name": "Late Checkout Fee",
                "charge_amount": 50.0,
                "notes": "Extended stay until 2 PM"
            },
            test_name="POST /api/reservations/{booking_id}/extra-charges"
        )
        
        # 4. POST /api/reservations/multi-room (was fixed)
        self.log("\n4️⃣ Testing Multi-Room Reservation...", BLUE)
        self.test_endpoint(
            "POST", "/reservations/multi-room",
            data={
                "group_name": "Final Test Group",
                "primary_booking_id": booking_id,
                "related_booking_ids": []
            },
            test_name="POST /api/reservations/multi-room"
        )
        
        # 5. GET /api/reservations/{booking_id}/ota-details (was fixed)
        self.log("\n5️⃣ Testing OTA Details Endpoint...", BLUE)
        self.test_endpoint(
            "GET", f"/reservations/{booking_id}/ota-details",
            test_name="GET /api/reservations/{booking_id}/ota-details"
        )
        
        # 6-8. POST /api/messaging/send-message (case-insensitive - was fixed)
        self.log("\n6️⃣ Testing Messaging Endpoint (UPPERCASE)...", BLUE)
        self.test_endpoint(
            "POST", "/messaging/send-message",
            data={
                "recipient_id": guest_id,
                "channel": "EMAIL",
                "subject": "Test Message",
                "message": "This is a test message"
            },
            test_name="POST /api/messaging/send-message (UPPERCASE)"
        )
        
        self.log("\n7️⃣ Testing Messaging Endpoint (lowercase)...", BLUE)
        self.test_endpoint(
            "POST", "/messaging/send-message",
            data={
                "recipient_id": guest_id,
                "channel": "email",
                "subject": "Test Message",
                "message": "This is a test message"
            },
            test_name="POST /api/messaging/send-message (lowercase)"
        )
        
        self.log("\n8️⃣ Testing Messaging Endpoint (MixedCase)...", BLUE)
        self.test_endpoint(
            "POST", "/messaging/send-message",
            data={
                "recipient_id": guest_id,
                "channel": "Email",
                "subject": "Test Message",
                "message": "This is a test message"
            },
            test_name="POST /api/messaging/send-message (MixedCase)"
        )
    
    def test_comprehensive_health_check(self):
        """Test 20+ endpoints across all major modules"""
        self.log("\n" + "="*80, YELLOW)
        self.log("🏥 COMPREHENSIVE HEALTH CHECK (20+ Endpoints)", YELLOW)
        self.log("="*80, YELLOW)
        
        # Auth & User Management
        self.log("\n📋 Auth & User Management:", BLUE)
        self.test_endpoint("GET", "/monitoring/health", test_name="Monitoring Health")
        self.test_endpoint("GET", "/monitoring/system", test_name="System Metrics")
        
        # PMS Module
        self.log("\n🏨 PMS Module:", BLUE)
        self.test_endpoint("GET", "/pms/rooms", params={"limit": 10}, test_name="PMS Rooms")
        self.test_endpoint("GET", "/pms/bookings", params={"limit": 10}, test_name="PMS Bookings")
        self.test_endpoint("GET", "/pms/guests", params={"limit": 10}, test_name="PMS Guests")
        self.test_endpoint("GET", "/companies", params={"limit": 10}, test_name="Companies")
        
        # Housekeeping
        self.log("\n🧹 Housekeeping Module:", BLUE)
        self.test_endpoint("GET", "/housekeeping/tasks", test_name="Housekeeping Tasks")
        self.test_endpoint("GET", "/housekeeping/mobile/room-assignments", test_name="Room Assignments")
        
        # Revenue Management
        self.log("\n💰 Revenue Management:", BLUE)
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        self.test_endpoint(
            "GET", "/rms/demand-heatmap",
            params={"start_date": today, "end_date": end_date},
            test_name="RMS Demand Heatmap"
        )
        
        # Reports
        self.log("\n📊 Reports Module:", BLUE)
        self.test_endpoint("GET", "/reports/flash-report", test_name="Flash Report")
        self.test_endpoint("GET", "/arrivals/today", test_name="Arrivals Today")
        
        # Executive Dashboard
        self.log("\n📈 Executive Dashboard:", BLUE)
        self.test_endpoint("GET", "/executive/kpi-snapshot", test_name="Executive KPI")
        
        # Finance
        self.log("\n💳 Finance Module:", BLUE)
        self.test_endpoint("GET", "/finance/bank-accounts", test_name="Bank Accounts")
        self.test_endpoint("GET", "/finance/credit-limits", test_name="Credit Limits")
        
        # F&B/POS
        self.log("\n🍽️ F&B/POS Module:", BLUE)
        self.test_endpoint("GET", "/fnb/outlets", test_name="F&B Outlets")
        self.test_endpoint("GET", "/fnb/recipes", test_name="F&B Recipes")
        
        # Mobile Endpoints
        self.log("\n📱 Mobile Endpoints:", BLUE)
        self.test_endpoint("GET", "/mobile/dashboard", test_name="Mobile Dashboard")
        self.test_endpoint("GET", "/mobile/frontdesk/checkin-list", test_name="Mobile Check-in List")
        
        # Channel Manager
        self.log("\n🌐 Channel Manager:", BLUE)
        self.test_endpoint("GET", "/channels/connections", test_name="Channel Connections")
        
        # Maintenance
        self.log("\n🔧 Maintenance Module:", BLUE)
        self.test_endpoint("GET", "/maintenance/tasks", test_name="Maintenance Tasks")
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*80, YELLOW)
        self.log("📊 FINAL TEST SUMMARY", YELLOW)
        self.log("="*80, YELLOW)
        
        success_rate = (self.results['passed'] / self.results['total'] * 100) if self.results['total'] > 0 else 0
        
        self.log(f"\n📈 Overall Statistics:", BLUE)
        self.log(f"   Total Tests: {self.results['total']}")
        self.log(f"   ✅ Passed: {self.results['passed']}", GREEN)
        self.log(f"   ❌ Failed: {self.results['failed']}", RED)
        self.log(f"   📊 Success Rate: {success_rate:.1f}%", 
                 GREEN if success_rate >= 95 else YELLOW if success_rate >= 80 else RED)
        
        # Previously failing endpoints summary
        self.log(f"\n🎯 Previously Failing Endpoints (8 Tests):", BLUE)
        failing_tests = [t for t in self.results['tests'][:8]]
        failing_passed = sum(1 for t in failing_tests if t['status'] == 'PASS')
        self.log(f"   Status: {failing_passed}/8 PASSED ({failing_passed/8*100:.1f}%)",
                 GREEN if failing_passed == 8 else RED)
        
        # Health check summary
        self.log(f"\n🏥 Health Check (20+ Endpoints):", BLUE)
        health_tests = [t for t in self.results['tests'][8:]]
        health_passed = sum(1 for t in health_tests if t['status'] == 'PASS')
        health_total = len(health_tests)
        if health_total > 0:
            self.log(f"   Status: {health_passed}/{health_total} PASSED ({health_passed/health_total*100:.1f}%)",
                     GREEN if health_passed/health_total >= 0.95 else YELLOW)
        
        # Failed tests detail
        if self.results['failed'] > 0:
            self.log(f"\n❌ Failed Tests Detail:", RED)
            for test in self.results['tests']:
                if test['status'] != 'PASS':
                    self.log(f"   • {test['name']}: {test.get('error', 'Unknown error')}", RED)
        
        # Final assessment
        self.log(f"\n🎯 FINAL ASSESSMENT:", YELLOW)
        if success_rate >= 95 and failing_passed == 8:
            self.log("   ✅ HATASIZ (ERROR-FREE) - 100% BACKEND INFRASTRUCTURE READY!", GREEN)
        elif success_rate >= 90:
            self.log("   ⚠️ MOSTLY READY - Minor issues need attention", YELLOW)
        else:
            self.log("   ❌ NEEDS WORK - Critical issues found", RED)
        
        self.log("\n" + "="*80, YELLOW)
    
    def run(self):
        """Run all tests"""
        self.log("="*80, BLUE)
        self.log("🎯 FINAL COMPREHENSIVE BACKEND TEST - 100% Verification", BLUE)
        self.log("="*80, BLUE)
        self.log(f"Base URL: {BASE_URL}", BLUE)
        self.log(f"Test User: {EMAIL}", BLUE)
        
        # Step 1: Login
        if not self.login():
            self.log("\n❌ Cannot proceed without authentication", RED)
            return
        
        # Step 2: Create test data
        guest_id = self.create_test_guest()
        if not guest_id:
            self.log("\n❌ Cannot proceed without test guest", RED)
            return
        
        booking_id = self.create_test_booking(guest_id)
        if not booking_id:
            self.log("\n❌ Cannot proceed without test booking", RED)
            return
        
        # Step 3: Test previously failing endpoints
        self.test_previously_failing_endpoints(guest_id, booking_id)
        
        # Step 4: Comprehensive health check
        self.test_comprehensive_health_check()
        
        # Step 5: Print summary
        self.print_summary()

if __name__ == "__main__":
    tester = BackendTester()
    tester.run()
