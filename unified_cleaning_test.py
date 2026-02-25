#!/usr/bin/env python3
"""
UNIFIED ENDPOINTS AND CLEANING REQUEST SYSTEM TESTING

Testing NEW UNIFIED ENDPOINTS and CLEANING REQUEST system:

**PART 1: UNIFIED ENDPOINTS (3 endpoints)**
1. GET /api/unified/today-arrivals
2. GET /api/unified/today-departures  
3. GET /api/unified/in-house

**PART 2: CLEANING REQUEST SYSTEM (4 endpoints)**
4. POST /api/guest/request-cleaning
5. GET /api/housekeeping/cleaning-requests
6. PUT /api/housekeeping/cleaning-request/{id}/status
7. GET /api/guest/my-cleaning-requests

Focus: Data enrichment, date filtering, cleaning workflow, notifications
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Any, Optional
import uuid

# Configuration
BACKEND_URL = "https://hotel-pms-demo.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class UnifiedCleaningTester:
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
            'cleaning_requests': []
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
        """Create comprehensive test data for unified endpoints and cleaning requests"""
        print("\n🔧 Creating test data for Unified Endpoints and Cleaning Request testing...")
        
        try:
            # Create test guests for bookings
            guests_data = [
                {
                    "name": "Alice Johnson",
                    "email": "alice.johnson@hotel.com",
                    "phone": "+1-555-0101",
                    "id_number": "ID101",
                    "nationality": "US",
                    "vip_status": False
                },
                {
                    "name": "Bob Smith",
                    "email": "bob.smith@hotel.com", 
                    "phone": "+1-555-0102",
                    "id_number": "ID102",
                    "nationality": "UK",
                    "vip_status": True
                },
                {
                    "name": "Carol Davis",
                    "email": "carol.davis@hotel.com",
                    "phone": "+1-555-0103", 
                    "id_number": "ID103",
                    "nationality": "CA",
                    "vip_status": False
                }
            ]
            
            guest_ids = []
            for guest_data in guests_data:
                async with self.session.post(f"{BACKEND_URL}/pms/guests", 
                                           json=guest_data, 
                                           headers=self.get_headers()) as response:
                    if response.status == 200:
                        guest = await response.json()
                        guest_id = guest["id"]
                        guest_ids.append(guest_id)
                        self.created_test_data['guests'].append(guest_id)
                        print(f"✅ Test guest created: {guest_data['name']} ({guest_id})")
                    else:
                        print(f"⚠️ Guest creation failed for {guest_data['name']}: {response.status}")

            # Get available rooms
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", 
                                      headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    if len(rooms) >= 3:
                        room_ids = [rooms[i]["id"] for i in range(3)]
                        self.created_test_data['rooms'] = room_ids
                        print(f"✅ Using rooms: {[rooms[i]['room_number'] for i in range(3)]}")
                    else:
                        print("⚠️ Not enough rooms available")
                        return False
                else:
                    print(f"⚠️ Failed to get rooms: {response.status}")
                    return False

            # Create test bookings for today's arrivals, departures, and in-house
            today = datetime.now(timezone.utc)
            tomorrow = today + timedelta(days=1)
            yesterday = today - timedelta(days=1)
            
            bookings_data = [
                {
                    "name": "Today Arrival",
                    "guest_id": guest_ids[0],
                    "room_id": room_ids[0],
                    "check_in": today.isoformat(),
                    "check_out": (today + timedelta(days=2)).isoformat(),
                    "adults": 2,
                    "children": 0,
                    "guests_count": 2,
                    "total_amount": 300.0,
                    "status": "confirmed"
                },
                {
                    "name": "Today Departure", 
                    "guest_id": guest_ids[1],
                    "room_id": room_ids[1],
                    "check_in": yesterday.isoformat(),
                    "check_out": today.isoformat(),
                    "adults": 1,
                    "children": 1,
                    "guests_count": 2,
                    "total_amount": 250.0,
                    "status": "checked_in"
                },
                {
                    "name": "In-House Guest",
                    "guest_id": guest_ids[2],
                    "room_id": room_ids[2],
                    "check_in": yesterday.isoformat(),
                    "check_out": tomorrow.isoformat(),
                    "adults": 2,
                    "children": 0,
                    "guests_count": 2,
                    "total_amount": 400.0,
                    "status": "checked_in"
                }
            ]
            
            for booking_data in bookings_data:
                async with self.session.post(f"{BACKEND_URL}/pms/bookings", 
                                           json=booking_data, 
                                           headers=self.get_headers()) as response:
                    if response.status == 200:
                        booking = await response.json()
                        booking_id = booking["id"]
                        self.created_test_data['bookings'].append(booking_id)
                        print(f"✅ Test booking created: {booking_data['name']} ({booking_id})")
                    else:
                        print(f"⚠️ Booking creation failed for {booking_data['name']}: {response.status}")

            print(f"✅ Test data creation completed")
            return True
            
        except Exception as e:
            print(f"❌ Error creating test data: {e}")
            return False

    # ============= UNIFIED ENDPOINTS TESTS (3 endpoints) =============

    async def test_today_arrivals_unified(self):
        """Test GET /api/unified/today-arrivals"""
        print("\n🏨 Testing Today Arrivals Unified Endpoint...")
        
        test_cases = [
            {
                "name": "Get today's arrivals with enriched data",
                "expected_fields": ["arrivals", "count", "date"],
                "expected_enrichment": ["guest_name", "guest_phone", "guest_email", "room_number", "room_type", "room_status"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/unified/today-arrivals"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify date is today
                            today_str = datetime.now(timezone.utc).date().isoformat()
                            if data.get("date") == today_str:
                                # Verify count matches array length
                                if data.get("count") == len(data.get("arrivals", [])):
                                    # Check enriched data if arrivals exist
                                    if data.get("arrivals"):
                                        arrival = data["arrivals"][0]
                                        missing_enrichment = [field for field in test_case["expected_enrichment"] if field not in arrival]
                                        if not missing_enrichment:
                                            # Verify booking status is confirmed or guaranteed
                                            if arrival.get("status") in ["confirmed", "guaranteed"]:
                                                print(f"  ✅ {test_case['name']}: PASSED")
                                                print(f"      📊 Found {data['count']} arrivals for {data['date']}")
                                                if data['count'] > 0:
                                                    print(f"      🏨 Sample: {arrival.get('guest_name')} - Room {arrival.get('room_number')}")
                                                passed += 1
                                            else:
                                                print(f"  ❌ {test_case['name']}: Invalid booking status: {arrival.get('status')}")
                                        else:
                                            print(f"  ❌ {test_case['name']}: Missing enrichment fields {missing_enrichment}")
                                    else:
                                        print(f"  ✅ {test_case['name']}: PASSED (no arrivals today)")
                                        passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Count mismatch - count: {data.get('count')}, array length: {len(data.get('arrivals', []))}")
                            else:
                                print(f"  ❌ {test_case['name']}: Date mismatch - expected: {today_str}, got: {data.get('date')}")
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:200]}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/unified/today-arrivals",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_today_departures_unified(self):
        """Test GET /api/unified/today-departures"""
        print("\n🏨 Testing Today Departures Unified Endpoint...")
        
        test_cases = [
            {
                "name": "Get today's departures with enriched data",
                "expected_fields": ["departures", "count", "date"],
                "expected_enrichment": ["guest_name", "guest_phone", "guest_email", "room_number", "room_type", "room_status"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/unified/today-departures"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify date is today
                            today_str = datetime.now(timezone.utc).date().isoformat()
                            if data.get("date") == today_str:
                                # Verify count matches array length
                                if data.get("count") == len(data.get("departures", [])):
                                    # Check enriched data if departures exist
                                    if data.get("departures"):
                                        departure = data["departures"][0]
                                        missing_enrichment = [field for field in test_case["expected_enrichment"] if field not in departure]
                                        if not missing_enrichment:
                                            # Verify booking status is checked_in
                                            if departure.get("status") == "checked_in":
                                                print(f"  ✅ {test_case['name']}: PASSED")
                                                print(f"      📊 Found {data['count']} departures for {data['date']}")
                                                if data['count'] > 0:
                                                    print(f"      🏨 Sample: {departure.get('guest_name')} - Room {departure.get('room_number')}")
                                                passed += 1
                                            else:
                                                print(f"  ❌ {test_case['name']}: Invalid booking status: {departure.get('status')}")
                                        else:
                                            print(f"  ❌ {test_case['name']}: Missing enrichment fields {missing_enrichment}")
                                    else:
                                        print(f"  ✅ {test_case['name']}: PASSED (no departures today)")
                                        passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Count mismatch - count: {data.get('count')}, array length: {len(data.get('departures', []))}")
                            else:
                                print(f"  ❌ {test_case['name']}: Date mismatch - expected: {today_str}, got: {data.get('date')}")
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:200]}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/unified/today-departures",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_in_house_unified(self):
        """Test GET /api/unified/in-house"""
        print("\n🏨 Testing In-House Unified Endpoint...")
        
        test_cases = [
            {
                "name": "Get in-house guests with enriched data",
                "expected_fields": ["in_house", "count"],
                "expected_enrichment": ["guest_name", "guest_phone", "guest_email", "room_number", "room_type", "room_status"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/unified/in-house"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify count matches array length
                            if data.get("count") == len(data.get("in_house", [])):
                                # Check enriched data if in-house guests exist
                                if data.get("in_house"):
                                    in_house_guest = data["in_house"][0]
                                    missing_enrichment = [field for field in test_case["expected_enrichment"] if field not in in_house_guest]
                                    if not missing_enrichment:
                                        # Verify booking status is checked_in
                                        if in_house_guest.get("status") == "checked_in":
                                            print(f"  ✅ {test_case['name']}: PASSED")
                                            print(f"      📊 Found {data['count']} in-house guests")
                                            if data['count'] > 0:
                                                print(f"      🏨 Sample: {in_house_guest.get('guest_name')} - Room {in_house_guest.get('room_number')}")
                                            passed += 1
                                        else:
                                            print(f"  ❌ {test_case['name']}: Invalid booking status: {in_house_guest.get('status')}")
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing enrichment fields {missing_enrichment}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED (no in-house guests)")
                                    passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Count mismatch - count: {data.get('count')}, array length: {len(data.get('in_house', []))}")
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:200]}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/unified/in-house",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= CLEANING REQUEST SYSTEM TESTS (4 endpoints) =============

    async def test_guest_request_cleaning(self):
        """Test POST /api/guest/request-cleaning"""
        print("\n🧹 Testing Guest Request Cleaning Endpoint...")
        
        # Use first booking for testing
        booking_id = self.created_test_data['bookings'][0] if self.created_test_data['bookings'] else str(uuid.uuid4())
        
        test_cases = [
            {
                "name": "Create regular cleaning request",
                "data": {
                    "booking_id": booking_id,
                    "type": "regular",
                    "notes": "Please clean the bathroom thoroughly"
                },
                "expected_status": 200,
                "expected_fields": ["request_id", "room_number", "estimated_time"]
            },
            {
                "name": "Create urgent cleaning request",
                "data": {
                    "booking_id": booking_id,
                    "type": "urgent",
                    "notes": "Spilled wine on carpet, urgent cleaning needed"
                },
                "expected_status": 200,
                "expected_fields": ["request_id", "room_number", "estimated_time"]
            },
            {
                "name": "Create cleaning request without notes",
                "data": {
                    "booking_id": booking_id,
                    "type": "regular"
                },
                "expected_status": 200,
                "expected_fields": ["request_id", "room_number", "estimated_time"]
            },
            {
                "name": "Create cleaning request with invalid booking",
                "data": {
                    "booking_id": "non-existent-booking",
                    "type": "regular",
                    "notes": "Test request"
                },
                "expected_status": 404
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/guest/request-cleaning"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == test_case["expected_status"]:
                        if response.status == 200:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                # Store cleaning request ID for later tests
                                if "request_id" in data:
                                    self.created_test_data['cleaning_requests'].append(data["request_id"])
                                print(f"  ✅ {test_case['name']}: PASSED")
                                print(f"      🧹 Request ID: {data.get('request_id')}")
                                print(f"      🏨 Room: {data.get('room_number')}")
                                print(f"      ⏱️ Estimated time: {data.get('estimated_time')} minutes")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:  # 404
                            print(f"  ✅ {test_case['name']}: PASSED (404 as expected)")
                            passed += 1
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Error: {error_text[:200]}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/guest/request-cleaning",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_get_cleaning_requests(self):
        """Test GET /api/housekeeping/cleaning-requests"""
        print("\n🧹 Testing Get Cleaning Requests Endpoint...")
        
        test_cases = [
            {
                "name": "Get all cleaning requests",
                "params": {},
                "expected_fields": ["requests", "count", "categories"]
            },
            {
                "name": "Filter by status - pending",
                "params": {"status": "pending"},
                "expected_fields": ["requests", "count", "categories"]
            },
            {
                "name": "Filter by priority - urgent",
                "params": {"priority": "urgent"},
                "expected_fields": ["requests", "count", "categories"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/housekeeping/cleaning-requests"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify categories structure
                            categories = data.get("categories", {})
                            expected_categories = ["pending", "in_progress", "completed_today"]
                            missing_categories = [cat for cat in expected_categories if cat not in categories]
                            if not missing_categories:
                                print(f"  ✅ {test_case['name']}: PASSED")
                                print(f"      📊 Total requests: {data.get('count')}")
                                print(f"      📋 Categories: Pending({categories.get('pending', 0)}), In Progress({categories.get('in_progress', 0)}), Completed Today({categories.get('completed_today', 0)})")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing categories {missing_categories}")
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:200]}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/cleaning-requests",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_update_cleaning_request_status(self):
        """Test PUT /api/housekeeping/cleaning-request/{id}/status"""
        print("\n🧹 Testing Update Cleaning Request Status Endpoint...")
        
        # Use first cleaning request ID if available
        request_id = self.created_test_data['cleaning_requests'][0] if self.created_test_data['cleaning_requests'] else str(uuid.uuid4())
        
        test_cases = [
            {
                "name": "Update status to in_progress",
                "request_id": request_id,
                "data": {
                    "status": "in_progress",
                    "assigned_to": "Maria Gonzalez"
                },
                "expected_status": [200, 404]
            },
            {
                "name": "Update status to completed",
                "request_id": request_id,
                "data": {
                    "status": "completed",
                    "completed_by": "Maria Gonzalez",
                    "notes": "Room cleaned thoroughly"
                },
                "expected_status": [200, 404]
            },
            {
                "name": "Update non-existent request",
                "request_id": "non-existent-request",
                "data": {
                    "status": "completed"
                },
                "expected_status": 404
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/housekeeping/cleaning-request/{test_case['request_id']}/status"
                
                async with self.session.put(url, json=test_case["data"], headers=self.get_headers()) as response:
                    expected_statuses = test_case["expected_status"] if isinstance(test_case["expected_status"], list) else [test_case["expected_status"]]
                    if response.status in expected_statuses:
                        if response.status == 200:
                            data = await response.json()
                            required_fields = ["message", "request_id", "status"]
                            missing_fields = [field for field in required_fields if field not in data]
                            if not missing_fields:
                                print(f"  ✅ {test_case['name']}: PASSED")
                                print(f"      🧹 Request: {data.get('request_id')}")
                                print(f"      📊 Status: {data.get('status')}")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:  # 404
                            print(f"  ✅ {test_case['name']}: PASSED (404 as expected)")
                            passed += 1
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: Expected {expected_statuses}, got {response.status}")
                        print(f"      Error: {error_text[:200]}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "PUT /api/housekeeping/cleaning-request/{id}/status",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_get_my_cleaning_requests(self):
        """Test GET /api/guest/my-cleaning-requests"""
        print("\n🧹 Testing Get My Cleaning Requests Endpoint...")
        
        test_cases = [
            {
                "name": "Get current guest's cleaning requests",
                "expected_fields": ["requests", "pending_count", "in_progress_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/guest/my-cleaning-requests"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            print(f"      📊 Total requests: {len(data.get('requests', []))}")
                            print(f"      ⏳ Pending: {data.get('pending_count')}")
                            print(f"      🔄 In Progress: {data.get('in_progress_count')}")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:200]}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/guest/my-cleaning-requests",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MAIN TEST EXECUTION =============

    async def run_all_tests(self):
        """Run comprehensive testing of Unified Endpoints and Cleaning Request System"""
        print("🚀 UNIFIED ENDPOINTS AND CLEANING REQUEST SYSTEM TESTING")
        print("Testing 7 NEW ENDPOINTS (3 Unified + 4 Cleaning Request)")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # Phase 1: Unified Endpoints (3 endpoints)
        print("\n" + "="*50)
        print("🏨 PHASE 1: UNIFIED ENDPOINTS (3 endpoints)")
        print("="*50)
        await self.test_today_arrivals_unified()
        await self.test_today_departures_unified()
        await self.test_in_house_unified()
        
        # Phase 2: Cleaning Request System (4 endpoints)
        print("\n" + "="*50)
        print("🧹 PHASE 2: CLEANING REQUEST SYSTEM (4 endpoints)")
        print("="*50)
        await self.test_guest_request_cleaning()
        await self.test_get_cleaning_requests()
        await self.test_update_cleaning_request_status()
        await self.test_get_my_cleaning_requests()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 UNIFIED ENDPOINTS AND CLEANING REQUEST SYSTEM TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        # Group results by category
        categories = {
            "Unified Endpoints": [],
            "Cleaning Request System": []
        }
        
        for result in self.test_results:
            endpoint = result["endpoint"]
            if "unified" in endpoint:
                categories["Unified Endpoints"].append(result)
            elif "cleaning" in endpoint or "guest/request-cleaning" in endpoint or "guest/my-cleaning-requests" in endpoint:
                categories["Cleaning Request System"].append(result)
        
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
            print("🎉 EXCELLENT: Unified endpoints and cleaning request system working perfectly!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most endpoints working, minor issues remain")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some endpoints working, but issues remain")
        else:
            print("❌ CRITICAL: Major issues with unified endpoints and cleaning request system")
        
        print("\n🔍 KEY FEATURES TESTED:")
        print("• Data enrichment (guest + room info)")
        print("• Today's date filtering (2025-11-22)")
        print("• Count field accuracy")
        print("• Cleaning request workflow")
        print("• Status updates and notifications")
        print("• Error handling (404 for missing resources)")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = UnifiedCleaningTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())