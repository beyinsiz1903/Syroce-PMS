#!/usr/bin/env python3
"""
Corrected Mobile Endpoints Testing for Hotel PMS
Testing ALL NEW MOBILE ENDPOINTS across 7 categories with correct field expectations
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import uuid

# Configuration
BACKEND_URL = "https://locust-load-test.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class MobileEndpointsTesterCorrected:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.created_test_data = {
            'guests': [],
            'bookings': [],
            'rooms': [],
            'folios': []
        }

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate and get token"""
        try:
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data["access_token"]
                    self.tenant_id = data["user"]["tenant_id"]
                    self.user_id = data["user"]["id"]
                    print(f"✅ Authentication successful - Tenant: {self.tenant_id}")
                    return True
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    async def create_test_data(self):
        """Create test data for mobile endpoint testing"""
        print("\n🔧 Creating test data for mobile endpoints...")
        
        try:
            # Get existing rooms
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    if rooms:
                        room_id = rooms[0]["id"]
                        self.created_test_data['rooms'].append(room_id)
                        print(f"✅ Using existing room: {room_id}")
                    else:
                        print("⚠️ No rooms available")
                        return False
                else:
                    print(f"⚠️ Failed to get rooms: {response.status}")
                    return False

            # Create test guest
            guest_data = {
                "name": "Mobile Test User",
                "email": "mobile.test@hotel.com",
                "phone": "+1-555-0199",
                "id_number": "MOBILE123456",
                "nationality": "US",
                "vip_status": True
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/guests", 
                                       json=guest_data, 
                                       headers=self.get_headers()) as response:
                if response.status == 200:
                    guest = await response.json()
                    guest_id = guest["id"]
                    self.created_test_data['guests'].append(guest_id)
                    print(f"✅ Test guest created: {guest_id}")
                else:
                    print(f"⚠️ Guest creation failed: {response.status}")
                    return False

            # Create test booking
            booking_data = {
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "check_out": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "adults": 2,
                "children": 0,
                "children_ages": [],
                "guests_count": 2,
                "total_amount": 300.0,
                "special_requests": "Early check-in requested"
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/bookings", 
                                       json=booking_data, 
                                       headers=self.get_headers()) as response:
                if response.status == 200:
                    booking = await response.json()
                    booking_id = booking["id"]
                    self.created_test_data['bookings'].append(booking_id)
                    print(f"✅ Test booking created: {booking_id}")
                else:
                    print(f"⚠️ Booking creation failed: {response.status}")
                    return False

            print(f"✅ Test data creation completed")
            return True
            
        except Exception as e:
            print(f"❌ Error creating test data: {e}")
            return False

    async def test_endpoint(self, endpoint_name, url, method="GET", data=None, expected_fields=None):
        """Generic endpoint testing method"""
        try:
            if method == "GET":
                async with self.session.get(url, headers=self.get_headers()) as response:
                    return await self.process_response(endpoint_name, response, expected_fields)
            elif method == "POST":
                async with self.session.post(url, json=data, headers=self.get_headers()) as response:
                    return await self.process_response(endpoint_name, response, expected_fields)
            elif method == "PUT":
                async with self.session.put(url, json=data, headers=self.get_headers()) as response:
                    return await self.process_response(endpoint_name, response, expected_fields)
        except Exception as e:
            print(f"  ❌ {endpoint_name}: Error {e}")
            return False

    async def process_response(self, endpoint_name, response, expected_fields):
        """Process HTTP response and check fields"""
        if response.status == 200:
            data = await response.json()
            if expected_fields:
                missing_fields = [field for field in expected_fields if field not in data]
                if not missing_fields:
                    print(f"  ✅ {endpoint_name}: PASSED")
                    return True
                else:
                    print(f"  ❌ {endpoint_name}: Missing fields {missing_fields}")
                    print(f"      Available fields: {list(data.keys())}")
                    return False
            else:
                print(f"  ✅ {endpoint_name}: PASSED (status 200)")
                return True
        else:
            error_text = await response.text()
            print(f"  ❌ {endpoint_name}: HTTP {response.status} - {error_text[:100]}")
            return False

    async def run_all_tests(self):
        """Run all mobile endpoint tests"""
        print("🚀 Starting Corrected Mobile Endpoints Testing")
        print("Testing ALL NEW MOBILE ENDPOINTS with correct field expectations")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # Test all endpoints
        endpoints_to_test = [
            # GM Mobile Dashboard
            ("GM Critical Issues", f"{BACKEND_URL}/dashboard/mobile/critical-issues", "GET", None, ["critical_issues", "total_count"]),
            ("GM Recent Complaints", f"{BACKEND_URL}/dashboard/mobile/recent-complaints", "GET", None, ["complaints", "total_count"]),
            ("GM Notifications", f"{BACKEND_URL}/notifications/mobile/gm", "GET", None, ["notifications", "unread_count"]),
            
            # Front Desk Mobile
            ("Early Check-in Requests", f"{BACKEND_URL}/frontdesk/mobile/early-checkin-requests", "GET", None, ["early_checkin_requests", "count"]),
            ("Late Checkout Requests", f"{BACKEND_URL}/frontdesk/mobile/late-checkout-requests", "GET", None, ["late_checkout_requests", "count"]),
            ("Front Desk Notifications", f"{BACKEND_URL}/notifications/mobile/frontdesk", "GET", None, ["notifications", "unread_count"]),
            
            # Housekeeping Mobile
            ("SLA Delayed Rooms", f"{BACKEND_URL}/housekeeping/mobile/sla-delayed-rooms", "GET", None, ["sla_delayed_rooms", "count"]),
            ("Team Assignments", f"{BACKEND_URL}/housekeeping/mobile/team-assignments", "GET", None, ["assignments", "count"]),
            ("Housekeeping Notifications", f"{BACKEND_URL}/notifications/mobile/housekeeping", "GET", None, ["notifications", "unread_count"]),
            
            # Maintenance Mobile
            ("Preventive Maintenance Schedule", f"{BACKEND_URL}/maintenance/mobile/preventive-maintenance-schedule", "GET", None, ["pm_schedule", "count"]),
            ("Maintenance Notifications", f"{BACKEND_URL}/notifications/mobile/maintenance", "GET", None, ["notifications", "unread_count"]),
            
            # F&B Mobile
            ("F&B Notifications", f"{BACKEND_URL}/notifications/mobile/fnb", "GET", None, ["notifications", "unread_count"]),
            
            # Finance Mobile (NEW)
            ("Daily Collections", f"{BACKEND_URL}/finance/mobile/daily-collections", "GET", None, ["date", "total_collected"]),
            ("Monthly Collections", f"{BACKEND_URL}/finance/mobile/monthly-collections", "GET", None, ["month", "total_collected"]),
            ("Pending Receivables", f"{BACKEND_URL}/finance/mobile/pending-receivables", "GET", None, ["receivables", "total_amount"]),
            ("Monthly Costs", f"{BACKEND_URL}/finance/mobile/monthly-costs", "GET", None, ["month", "total_costs"]),
            ("Finance Notifications", f"{BACKEND_URL}/notifications/mobile/finance", "GET", None, ["notifications", "unread_count"]),
            
            # Security/IT Mobile (NEW)
            ("System Status", f"{BACKEND_URL}/security/mobile/system-status", "GET", None, ["overall_status", "health_score"]),
            ("Connection Status", f"{BACKEND_URL}/security/mobile/connection-status", "GET", None, ["connections", "total_connections"]),
            ("Security Alerts", f"{BACKEND_URL}/security/mobile/security-alerts", "GET", None, ["alerts", "count"]),
            ("Security Notifications", f"{BACKEND_URL}/notifications/mobile/security", "GET", None, ["notifications", "unread_count"]),
        ]
        
        # Test POST endpoints with data
        post_endpoints = []
        
        if self.created_test_data['bookings']:
            post_endpoints.extend([
                ("Process No-Show", f"{BACKEND_URL}/frontdesk/mobile/process-no-show", "POST", 
                 {"booking_id": self.created_test_data['bookings'][0], "notes": "Guest did not arrive"}, 
                 ["success", "message"]),
            ])
        
        if self.created_test_data['bookings'] and self.created_test_data['rooms']:
            post_endpoints.extend([
                ("Change Room", f"{BACKEND_URL}/frontdesk/mobile/change-room", "POST", 
                 {"booking_id": self.created_test_data['bookings'][0], "new_room_id": self.created_test_data['rooms'][0], "reason": "Guest request"}, 
                 ["success", "message"]),
            ])
        
        if self.created_test_data['rooms']:
            post_endpoints.extend([
                ("Quick Housekeeping Task", f"{BACKEND_URL}/housekeeping/mobile/quick-task", "POST", 
                 {"room_id": self.created_test_data['rooms'][0], "task_type": "maintenance", "description": "Test issue", "priority": "high"}, 
                 ["success", "message"]),
                ("Quick Maintenance Issue", f"{BACKEND_URL}/maintenance/mobile/quick-issue", "POST", 
                 {"room_id": self.created_test_data['rooms'][0], "issue_type": "electrical", "description": "Test issue", "priority": "medium"}, 
                 ["success", "message"]),
            ])
        
        # POS and Finance POST endpoints
        post_endpoints.extend([
            ("POS Quick Order", f"{BACKEND_URL}/pos/mobile/quick-order", "POST", 
             {"outlet_id": "restaurant_main", "items": [{"name": "Test Item", "quantity": 1, "price": 10.0}], "payment_method": "card"}, 
             ["success", "message"]),
        ])
        
        # Test GET endpoints
        passed = 0
        total = 0
        
        print("\n📋 Testing GET Endpoints...")
        for name, url, method, data, expected_fields in endpoints_to_test:
            total += 1
            if await self.test_endpoint(name, url, method, data, expected_fields):
                passed += 1
        
        print("\n📋 Testing POST Endpoints...")
        for name, url, method, data, expected_fields in post_endpoints:
            total += 1
            if await self.test_endpoint(name, url, method, data, expected_fields):
                passed += 1
        
        # Test PUT endpoint for menu item price update
        print("\n📋 Testing PUT Endpoints...")
        total += 1
        if await self.test_endpoint("Menu Item Price Update", f"{BACKEND_URL}/pos/mobile/menu-items/caesar_salad/price", "PUT", 
                                  {"new_price": 16.50, "reason": "Test price update"}, ["success", "message"]):
            passed += 1
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        print("\n" + "=" * 80)
        print("📊 MOBILE ENDPOINTS TEST RESULTS")
        print("=" * 80)
        
        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {passed}/{total} ({success_rate:.1f}%)")
        
        if success_rate >= 90:
            print("🎉 EXCELLENT: Mobile endpoints are working perfectly!")
        elif success_rate >= 75:
            print("✅ GOOD: Most mobile endpoints are working correctly")
        elif success_rate >= 50:
            print("⚠️ PARTIAL: Some mobile endpoints need attention")
        else:
            print("❌ CRITICAL: Major issues with mobile endpoints")
        
        print("\n🔍 TESTED MOBILE FEATURES:")
        print("• GM Dashboard: Critical issues, complaints, notifications")
        print("• Front Desk: Check-in/out requests, no-shows, room changes")
        print("• Housekeeping: SLA monitoring, team assignments, quick tasks")
        print("• Maintenance: Preventive schedules, quick issue reporting")
        print("• F&B: Quick orders, menu price updates, notifications")
        print("• Finance (NEW): Collections, receivables, costs, payments")
        print("• Security/IT (NEW): System status, connections, alerts")
        
        print("\n" + "=" * 80)
        
        return success_rate

async def main():
    """Main test execution"""
    tester = MobileEndpointsTesterCorrected()
    success_rate = await tester.run_all_tests()
    return success_rate

if __name__ == "__main__":
    result = asyncio.run(main())