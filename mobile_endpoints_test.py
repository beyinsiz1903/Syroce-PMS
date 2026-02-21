#!/usr/bin/env python3
"""
Comprehensive Mobile Endpoints Testing for Hotel PMS
Testing ALL NEW MOBILE ENDPOINTS across 7 categories:
1. GM Mobile Dashboard (3 endpoints)
2. Front Desk Mobile (5 endpoints)
3. Housekeeping Mobile (4 endpoints)
4. Maintenance Mobile (3 endpoints)
5. F&B Mobile (3 endpoints)
6. Finance Mobile (6 endpoints) - NEW
7. Security/IT Mobile (4 endpoints) - NEW
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
BACKEND_URL = "https://perf-boost-37.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class MobileEndpointsTester:
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
            'folios': [],
            'menu_items': [],
            'outlets': []
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
        """Create comprehensive test data for mobile endpoint testing"""
        print("\n🔧 Creating test data for mobile endpoints...")
        
        try:
            # Create test guest
            guest_data = {
                "name": "Michael Thompson",
                "email": "michael.thompson@hotel.com",
                "phone": "+1-555-0199",
                "id_number": "ID987654321",
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

            # Get available room
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", 
                                      headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    if rooms:
                        room_id = rooms[0]["id"]
                        self.created_test_data['rooms'].append(room_id)
                        print(f"✅ Using room: {room_id}")
                    else:
                        print("⚠️ No rooms available")
                        return False
                else:
                    print(f"⚠️ Failed to get rooms: {response.status}")
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

    # ============= GM MOBILE DASHBOARD TESTS (3 endpoints) =============

    async def test_gm_critical_issues(self):
        """Test GET /api/dashboard/mobile/critical-issues"""
        print("\n📋 Testing GM Critical Issues Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get critical issues for GM dashboard",
                "expected_fields": ["critical_issues", "total_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/dashboard/mobile/critical-issues"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/dashboard/mobile/critical-issues",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_gm_recent_complaints(self):
        """Test GET /api/dashboard/mobile/recent-complaints"""
        print("\n📋 Testing GM Recent Complaints Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get recent complaints for GM dashboard",
                "expected_fields": ["complaints", "total_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/dashboard/mobile/recent-complaints"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/dashboard/mobile/recent-complaints",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_gm_notifications(self):
        """Test GET /api/notifications/mobile/gm"""
        print("\n📋 Testing GM Mobile Notifications Endpoint...")
        
        test_cases = [
            {
                "name": "Get GM mobile notifications",
                "expected_fields": ["notifications", "unread_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/mobile/gm"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/notifications/mobile/gm",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= FRONT DESK MOBILE TESTS (5 endpoints) =============

    async def test_frontdesk_early_checkin_requests(self):
        """Test GET /api/frontdesk/mobile/early-checkin-requests"""
        print("\n📋 Testing Front Desk Early Check-in Requests Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get early check-in requests",
                "expected_fields": ["requests", "total_count", "pending_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/frontdesk/mobile/early-checkin-requests"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/frontdesk/mobile/early-checkin-requests",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_frontdesk_late_checkout_requests(self):
        """Test GET /api/frontdesk/mobile/late-checkout-requests"""
        print("\n📋 Testing Front Desk Late Checkout Requests Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get late checkout requests",
                "expected_fields": ["requests", "total_count", "pending_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/frontdesk/mobile/late-checkout-requests"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/frontdesk/mobile/late-checkout-requests",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_frontdesk_process_no_show(self):
        """Test POST /api/frontdesk/mobile/process-no-show"""
        print("\n📋 Testing Front Desk Process No-Show Mobile Endpoint...")
        
        if not self.created_test_data['bookings']:
            print("❌ No test bookings available")
            self.test_results.append({
                "endpoint": "POST /api/frontdesk/mobile/process-no-show",
                "passed": 0, "total": 1, "success_rate": "0.0%"
            })
            return

        test_cases = [
            {
                "name": "Process no-show booking",
                "data": {
                    "booking_id": self.created_test_data['bookings'][0],
                    "notes": "Guest did not arrive, no contact made"
                },
                "expected_fields": ["success", "message", "booking_id", "status"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/frontdesk/mobile/process-no-show"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/frontdesk/mobile/process-no-show",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_frontdesk_change_room(self):
        """Test POST /api/frontdesk/mobile/change-room"""
        print("\n📋 Testing Front Desk Change Room Mobile Endpoint...")
        
        if not self.created_test_data['bookings'] or not self.created_test_data['rooms']:
            print("❌ No test bookings or rooms available")
            self.test_results.append({
                "endpoint": "POST /api/frontdesk/mobile/change-room",
                "passed": 0, "total": 1, "success_rate": "0.0%"
            })
            return

        test_cases = [
            {
                "name": "Change room for booking",
                "data": {
                    "booking_id": self.created_test_data['bookings'][0],
                    "new_room_id": self.created_test_data['rooms'][0],
                    "reason": "Guest requested room change due to noise"
                },
                "expected_fields": ["success", "message", "booking_id", "old_room", "new_room"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/frontdesk/mobile/change-room"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/frontdesk/mobile/change-room",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_frontdesk_notifications(self):
        """Test GET /api/notifications/mobile/frontdesk"""
        print("\n📋 Testing Front Desk Mobile Notifications Endpoint...")
        
        test_cases = [
            {
                "name": "Get front desk mobile notifications",
                "expected_fields": ["notifications", "unread_count", "categories"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/mobile/frontdesk"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/notifications/mobile/frontdesk",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= HOUSEKEEPING MOBILE TESTS (4 endpoints) =============

    async def test_housekeeping_sla_delayed_rooms(self):
        """Test GET /api/housekeeping/mobile/sla-delayed-rooms"""
        print("\n📋 Testing Housekeeping SLA Delayed Rooms Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get SLA delayed rooms",
                "expected_fields": ["delayed_rooms", "total_count", "sla_breach_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/housekeeping/mobile/sla-delayed-rooms"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/mobile/sla-delayed-rooms",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_housekeeping_team_assignments(self):
        """Test GET /api/housekeeping/mobile/team-assignments"""
        print("\n📋 Testing Housekeeping Team Assignments Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get team assignments",
                "expected_fields": ["assignments", "team_members", "total_tasks"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/housekeeping/mobile/team-assignments"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/mobile/team-assignments",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_housekeeping_quick_task(self):
        """Test POST /api/housekeeping/mobile/quick-task"""
        print("\n📋 Testing Housekeeping Quick Task Mobile Endpoint...")
        
        if not self.created_test_data['rooms']:
            print("❌ No test rooms available")
            self.test_results.append({
                "endpoint": "POST /api/housekeeping/mobile/quick-task",
                "passed": 0, "total": 1, "success_rate": "0.0%"
            })
            return

        test_cases = [
            {
                "name": "Create quick housekeeping task",
                "data": {
                    "room_id": self.created_test_data['rooms'][0],
                    "task_type": "maintenance",
                    "description": "Bathroom faucet needs repair",
                    "priority": "high"
                },
                "expected_fields": ["success", "message", "task_id", "room_number"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/housekeeping/mobile/quick-task"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/housekeeping/mobile/quick-task",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_housekeeping_notifications(self):
        """Test GET /api/notifications/mobile/housekeeping"""
        print("\n📋 Testing Housekeeping Mobile Notifications Endpoint...")
        
        test_cases = [
            {
                "name": "Get housekeeping mobile notifications",
                "expected_fields": ["notifications", "unread_count", "categories"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/mobile/housekeeping"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/notifications/mobile/housekeeping",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MAINTENANCE MOBILE TESTS (3 endpoints) =============

    async def test_maintenance_preventive_schedule(self):
        """Test GET /api/maintenance/mobile/preventive-maintenance-schedule"""
        print("\n📋 Testing Maintenance Preventive Schedule Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get preventive maintenance schedule",
                "expected_fields": ["schedule", "upcoming_count", "overdue_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/maintenance/mobile/preventive-maintenance-schedule"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/maintenance/mobile/preventive-maintenance-schedule",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_maintenance_quick_issue(self):
        """Test POST /api/maintenance/mobile/quick-issue"""
        print("\n📋 Testing Maintenance Quick Issue Mobile Endpoint...")
        
        if not self.created_test_data['rooms']:
            print("❌ No test rooms available")
            self.test_results.append({
                "endpoint": "POST /api/maintenance/mobile/quick-issue",
                "passed": 0, "total": 1, "success_rate": "0.0%"
            })
            return

        test_cases = [
            {
                "name": "Report quick maintenance issue",
                "data": {
                    "room_id": self.created_test_data['rooms'][0],
                    "issue_type": "electrical",
                    "description": "Light fixture not working in bathroom",
                    "priority": "medium"
                },
                "expected_fields": ["success", "message", "issue_id", "room_number"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/maintenance/mobile/quick-issue"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/maintenance/mobile/quick-issue",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_maintenance_notifications(self):
        """Test GET /api/notifications/mobile/maintenance"""
        print("\n📋 Testing Maintenance Mobile Notifications Endpoint...")
        
        test_cases = [
            {
                "name": "Get maintenance mobile notifications",
                "expected_fields": ["notifications", "unread_count", "categories"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/mobile/maintenance"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/notifications/mobile/maintenance",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= F&B MOBILE TESTS (3 endpoints) =============

    async def test_pos_mobile_quick_order(self):
        """Test POST /api/pos/mobile/quick-order"""
        print("\n📋 Testing POS Mobile Quick Order Endpoint...")
        
        test_cases = [
            {
                "name": "Create quick POS order",
                "data": {
                    "outlet_id": "restaurant_main",
                    "items": [
                        {"name": "Caesar Salad", "quantity": 1, "price": 14.50},
                        {"name": "Grilled Chicken", "quantity": 1, "price": 22.00}
                    ],
                    "payment_method": "card",
                    "table_number": "15"
                },
                "expected_fields": ["success", "message", "order_id", "total_amount"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/pos/mobile/quick-order"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/pos/mobile/quick-order",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_pos_mobile_menu_item_price_update(self):
        """Test PUT /api/pos/mobile/menu-items/{item_id}/price"""
        print("\n📋 Testing POS Mobile Menu Item Price Update Endpoint...")
        
        # First, get a menu item to update
        try:
            async with self.session.get(f"{BACKEND_URL}/pos/menu-items", headers=self.get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    menu_items = data.get("menu_items", [])
                    if menu_items:
                        item_id = menu_items[0].get("id", "caesar_salad")
                    else:
                        item_id = "caesar_salad"  # fallback
                else:
                    item_id = "caesar_salad"  # fallback
        except:
            item_id = "caesar_salad"  # fallback

        test_cases = [
            {
                "name": "Update menu item price",
                "item_id": item_id,
                "data": {
                    "new_price": 16.50,
                    "reason": "Ingredient cost increase"
                },
                "expected_fields": ["success", "message", "item_id", "old_price", "new_price"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/pos/mobile/menu-items/{test_case['item_id']}/price"
                
                async with self.session.put(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "PUT /api/pos/mobile/menu-items/{item_id}/price",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_fnb_notifications(self):
        """Test GET /api/notifications/mobile/fnb"""
        print("\n📋 Testing F&B Mobile Notifications Endpoint...")
        
        test_cases = [
            {
                "name": "Get F&B mobile notifications",
                "expected_fields": ["notifications", "unread_count", "categories"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/mobile/fnb"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/notifications/mobile/fnb",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= FINANCE MOBILE TESTS (6 endpoints) - NEW =============

    async def test_finance_daily_collections(self):
        """Test GET /api/finance/mobile/daily-collections"""
        print("\n📋 Testing Finance Daily Collections Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get daily collections",
                "expected_fields": ["collections", "total_amount", "payment_methods", "date"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/finance/mobile/daily-collections"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/finance/mobile/daily-collections",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_finance_monthly_collections(self):
        """Test GET /api/finance/mobile/monthly-collections"""
        print("\n📋 Testing Finance Monthly Collections Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get monthly collections",
                "expected_fields": ["collections", "total_amount", "monthly_trend", "comparison"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/finance/mobile/monthly-collections"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/finance/mobile/monthly-collections",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_finance_pending_receivables(self):
        """Test GET /api/finance/mobile/pending-receivables"""
        print("\n📋 Testing Finance Pending Receivables Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get pending receivables",
                "expected_fields": ["receivables", "total_amount", "aging_breakdown", "overdue_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/finance/mobile/pending-receivables"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/finance/mobile/pending-receivables",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_finance_monthly_costs(self):
        """Test GET /api/finance/mobile/monthly-costs"""
        print("\n📋 Testing Finance Monthly Costs Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get monthly costs",
                "expected_fields": ["costs", "total_amount", "category_breakdown", "trend"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/finance/mobile/monthly-costs"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/finance/mobile/monthly-costs",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_finance_record_payment(self):
        """Test POST /api/finance/mobile/record-payment"""
        print("\n📋 Testing Finance Record Payment Mobile Endpoint...")
        
        # First create a folio to record payment against
        folio_id = None
        if self.created_test_data['bookings']:
            try:
                folio_data = {
                    "booking_id": self.created_test_data['bookings'][0],
                    "folio_type": "guest"
                }
                async with self.session.post(f"{BACKEND_URL}/folio/create", 
                                           json=folio_data, headers=self.get_headers()) as response:
                    if response.status == 200:
                        folio = await response.json()
                        folio_id = folio["id"]
                        self.created_test_data['folios'].append(folio_id)
            except:
                pass

        if not folio_id:
            folio_id = "test_folio_id"  # fallback

        test_cases = [
            {
                "name": "Record payment",
                "data": {
                    "folio_id": folio_id,
                    "amount": 150.00,
                    "payment_method": "card",
                    "reference": "CARD123456",
                    "notes": "Payment recorded via mobile app"
                },
                "expected_fields": ["success", "message", "payment_id", "folio_balance"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/finance/mobile/record-payment"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/finance/mobile/record-payment",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_finance_notifications(self):
        """Test GET /api/notifications/mobile/finance"""
        print("\n📋 Testing Finance Mobile Notifications Endpoint...")
        
        test_cases = [
            {
                "name": "Get finance mobile notifications",
                "expected_fields": ["notifications", "unread_count", "categories"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/mobile/finance"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/notifications/mobile/finance",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= SECURITY/IT MOBILE TESTS (4 endpoints) - NEW =============

    async def test_security_system_status(self):
        """Test GET /api/security/mobile/system-status"""
        print("\n📋 Testing Security System Status Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get system status",
                "expected_fields": ["systems", "overall_status", "critical_alerts", "last_updated"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/security/mobile/system-status"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/security/mobile/system-status",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_security_connection_status(self):
        """Test GET /api/security/mobile/connection-status"""
        print("\n📋 Testing Security Connection Status Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get connection status",
                "expected_fields": ["connections", "active_count", "failed_count", "network_health"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/security/mobile/connection-status"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/security/mobile/connection-status",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_security_alerts(self):
        """Test GET /api/security/mobile/security-alerts"""
        print("\n📋 Testing Security Alerts Mobile Endpoint...")
        
        test_cases = [
            {
                "name": "Get security alerts",
                "expected_fields": ["alerts", "critical_count", "warning_count", "resolved_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/security/mobile/security-alerts"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/security/mobile/security-alerts",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_security_notifications(self):
        """Test GET /api/notifications/mobile/security"""
        print("\n📋 Testing Security Mobile Notifications Endpoint...")
        
        test_cases = [
            {
                "name": "Get security mobile notifications",
                "expected_fields": ["notifications", "unread_count", "categories"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/mobile/security"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/notifications/mobile/security",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MAIN TEST EXECUTION =============

    async def run_all_tests(self):
        """Run all mobile endpoint tests"""
        print("🚀 Starting Comprehensive Mobile Endpoints Testing")
        print("Testing ALL NEW MOBILE ENDPOINTS across 7 categories")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # Phase 1: GM Mobile Dashboard (3 endpoints)
        print("\n" + "="*50)
        print("👔 PHASE 1: GM MOBILE DASHBOARD (3 endpoints)")
        print("="*50)
        await self.test_gm_critical_issues()
        await self.test_gm_recent_complaints()
        await self.test_gm_notifications()
        
        # Phase 2: Front Desk Mobile (5 endpoints)
        print("\n" + "="*50)
        print("🏨 PHASE 2: FRONT DESK MOBILE (5 endpoints)")
        print("="*50)
        await self.test_frontdesk_early_checkin_requests()
        await self.test_frontdesk_late_checkout_requests()
        await self.test_frontdesk_process_no_show()
        await self.test_frontdesk_change_room()
        await self.test_frontdesk_notifications()
        
        # Phase 3: Housekeeping Mobile (4 endpoints)
        print("\n" + "="*50)
        print("🧹 PHASE 3: HOUSEKEEPING MOBILE (4 endpoints)")
        print("="*50)
        await self.test_housekeeping_sla_delayed_rooms()
        await self.test_housekeeping_team_assignments()
        await self.test_housekeeping_quick_task()
        await self.test_housekeeping_notifications()
        
        # Phase 4: Maintenance Mobile (3 endpoints)
        print("\n" + "="*50)
        print("🔧 PHASE 4: MAINTENANCE MOBILE (3 endpoints)")
        print("="*50)
        await self.test_maintenance_preventive_schedule()
        await self.test_maintenance_quick_issue()
        await self.test_maintenance_notifications()
        
        # Phase 5: F&B Mobile (3 endpoints)
        print("\n" + "="*50)
        print("🍽️ PHASE 5: F&B MOBILE (3 endpoints)")
        print("="*50)
        await self.test_pos_mobile_quick_order()
        await self.test_pos_mobile_menu_item_price_update()
        await self.test_fnb_notifications()
        
        # Phase 6: Finance Mobile (6 endpoints) - NEW
        print("\n" + "="*50)
        print("💰 PHASE 6: FINANCE MOBILE (6 endpoints) - NEW")
        print("="*50)
        await self.test_finance_daily_collections()
        await self.test_finance_monthly_collections()
        await self.test_finance_pending_receivables()
        await self.test_finance_monthly_costs()
        await self.test_finance_record_payment()
        await self.test_finance_notifications()
        
        # Phase 7: Security/IT Mobile (4 endpoints) - NEW
        print("\n" + "="*50)
        print("🔒 PHASE 7: SECURITY/IT MOBILE (4 endpoints) - NEW")
        print("="*50)
        await self.test_security_system_status()
        await self.test_security_connection_status()
        await self.test_security_alerts()
        await self.test_security_notifications()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 MOBILE ENDPOINTS TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        # Group results by category
        categories = {
            "GM Mobile Dashboard": [],
            "Front Desk Mobile": [],
            "Housekeeping Mobile": [],
            "Maintenance Mobile": [],
            "F&B Mobile": [],
            "Finance Mobile (NEW)": [],
            "Security/IT Mobile (NEW)": []
        }
        
        for result in self.test_results:
            endpoint = result["endpoint"]
            if "dashboard/mobile" in endpoint or "notifications/mobile/gm" in endpoint:
                categories["GM Mobile Dashboard"].append(result)
            elif "frontdesk/mobile" in endpoint or "notifications/mobile/frontdesk" in endpoint:
                categories["Front Desk Mobile"].append(result)
            elif "housekeeping/mobile" in endpoint or "notifications/mobile/housekeeping" in endpoint:
                categories["Housekeeping Mobile"].append(result)
            elif "maintenance/mobile" in endpoint or "notifications/mobile/maintenance" in endpoint:
                categories["Maintenance Mobile"].append(result)
            elif "pos/mobile" in endpoint or "notifications/mobile/fnb" in endpoint:
                categories["F&B Mobile"].append(result)
            elif "finance/mobile" in endpoint or "notifications/mobile/finance" in endpoint:
                categories["Finance Mobile (NEW)"].append(result)
            elif "security/mobile" in endpoint or "notifications/mobile/security" in endpoint:
                categories["Security/IT Mobile (NEW)"].append(result)
        
        print("\n📋 RESULTS BY CATEGORY:")
        print("-" * 60)
        
        for category, results in categories.items():
            if results:
                category_passed = sum(r["passed"] for r in results)
                category_total = sum(r["total"] for r in results)
                category_rate = (category_passed / category_total * 100) if category_total > 0 else 0
                
                status = "✅" if category_rate == 100 else "⚠️" if category_rate >= 50 else "❌"
                print(f"\n{status} {category}: {category_passed}/{category_total} ({category_rate:.1f}%)")
                
                for result in results:
                    endpoint_status = "✅" if result["passed"] == result["total"] else "❌"
                    print(f"   {endpoint_status} {result['endpoint']}: {result['success_rate']}")
                
                total_passed += category_passed
                total_tests += category_total
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: Mobile endpoints are working perfectly!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most mobile endpoints are working correctly")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some mobile endpoints need attention")
        else:
            print("❌ CRITICAL: Major issues with mobile endpoints")
        
        print("\n🔍 KEY MOBILE FEATURES TESTED:")
        print("• GM Dashboard: Critical issues, complaints, notifications")
        print("• Front Desk: Check-in/out requests, no-shows, room changes")
        print("• Housekeeping: SLA monitoring, team assignments, quick tasks")
        print("• Maintenance: Preventive schedules, quick issue reporting")
        print("• F&B: Quick orders, menu price updates, notifications")
        print("• Finance (NEW): Collections, receivables, costs, payments")
        print("• Security/IT (NEW): System status, connections, alerts")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = MobileEndpointsTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())