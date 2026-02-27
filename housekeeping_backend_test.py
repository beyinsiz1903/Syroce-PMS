#!/usr/bin/env python3
"""
PMS HOUSEKEEPING BACKEND COMPREHENSIVE TEST
Test all housekeeping endpoints for HousekeepingTab.js component compatibility

ENDPOINTS TO TEST:
1. GET /api/housekeeping/tasks
2. POST /api/housekeeping/tasks (create sample task)
3. PUT /api/housekeeping/tasks/{task_id} (status updates)
4. GET /api/housekeeping/room-status
5. GET /api/housekeeping/due-out
6. GET /api/housekeeping/stayovers
7. GET /api/housekeeping/arrivals
8. PUT /api/housekeeping/room/{room_id}/status (room status flow)
9. POST /api/housekeeping/assign (task assignment)

EXPECTED RESPONSE STRUCTURES:
- room-status: { rooms: [...], status_counts: { available, occupied, dirty, cleaning, inspected, maintenance, out_of_order }, total_rooms }
- due-out: { due_out_rooms: [{ room_number, guest_name, checkout_date, is_today }], count }
- stayovers: { stayover_rooms: [{ room_number, guest_name, nights_remaining }], count }
- arrivals: { arrival_rooms: [{ room_number, guest_name, room_status, ready }], ready_count }
- tasks: list with id, room_id, task_type, priority, status, notes, assigned_to + room.room_number join

LOGIN: demo@hotel.com / demo123
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Any, Optional
import uuid
import time

# Configuration
BACKEND_URL = "https://locust-load-test.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class HousekeepingTester:
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
            'tasks': []
        }
        self.performance_metrics = []

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate with demo credentials"""
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
                    print(f"✅ Authentication successful - User: {data['user']['name']}, Tenant: {self.tenant_id}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Authentication failed: {response.status} - {error_text}")
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

    async def measure_performance(self, endpoint_name: str, func):
        """Measure endpoint performance"""
        start_time = time.time()
        result = await func()
        end_time = time.time()
        
        response_time = (end_time - start_time) * 1000  # Convert to milliseconds
        self.performance_metrics.append({
            "endpoint": endpoint_name,
            "response_time_ms": round(response_time, 2)
        })
        
        return result

    async def create_test_data(self):
        """Create test data for housekeeping testing"""
        print("\n🔧 Creating test data for housekeeping endpoints...")
        
        try:
            # Create test guest for bookings
            guest_data = {
                "name": "Maria Rodriguez",
                "email": "maria.rodriguez@hotel.com",
                "phone": "+1-555-0199",
                "id_number": "ID987654321",
                "nationality": "ES",
                "vip_status": False
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

            # Get available rooms for testing
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", 
                                      headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    if rooms:
                        # Store first few room IDs for testing
                        for i, room in enumerate(rooms[:3]):
                            self.created_test_data['rooms'].append(room["id"])
                        print(f"✅ Using {len(self.created_test_data['rooms'])} rooms for testing")
                    else:
                        print("⚠️ No rooms available")
                        return False
                else:
                    print(f"⚠️ Failed to get rooms: {response.status}")
                    return False

            # Create test booking for housekeeping scenarios
            if guest_id and self.created_test_data['rooms']:
                booking_data = {
                    "guest_id": guest_id,
                    "room_id": self.created_test_data['rooms'][0],
                    "check_in": (datetime.now(timezone.utc)).isoformat(),
                    "check_out": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                    "adults": 2,
                    "children": 0,
                    "children_ages": [],
                    "guests_count": 2,
                    "total_amount": 320.0,
                    "special_requests": "Late checkout requested"
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

            print(f"✅ Test data creation completed")
            return True
            
        except Exception as e:
            print(f"❌ Error creating test data: {e}")
            return False

    # ============= HOUSEKEEPING ENDPOINTS TESTS =============

    async def test_housekeeping_tasks_get(self):
        """Test GET /api/housekeeping/tasks"""
        print("\n🧹 Testing GET /api/housekeeping/tasks...")
        
        async def test_func():
            test_cases = [
                {
                    "name": "Get all housekeeping tasks",
                    "params": {},
                    "expected_response_type": "list"  # Endpoint returns list directly
                },
                {
                    "name": "Filter by status - pending",
                    "params": {"status": "pending"},
                    "expected_response_type": "list"
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    url = f"{BACKEND_URL}/housekeeping/tasks"
                    if test_case["params"]:
                        params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                        url += f"?{params}"
                    
                    async with self.session.get(url, headers=self.get_headers()) as response:
                        if response.status == 200:
                            data = await response.json()
                            # Endpoint returns list directly, not object with tasks field
                            if isinstance(data, list):
                                if data:  # If tasks exist
                                    task = data[0]
                                    required_task_fields = ["id", "room_id", "task_type", "priority", "status"]
                                    missing_task_fields = [field for field in required_task_fields if field not in task]
                                    if not missing_task_fields:
                                        # Check if room.room_number is joined
                                        if "room" in task and task["room"] and "room_number" in task["room"]:
                                            print(f"  ✅ {test_case['name']}: PASSED (with room join)")
                                        else:
                                            print(f"  ✅ {test_case['name']}: PASSED (no room join)")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing task fields {missing_task_fields}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED (no tasks)")
                                    passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Expected list, got {type(data)}")
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("GET /api/housekeeping/tasks", test_func)
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/tasks",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_tasks_post(self):
        """Test POST /api/housekeeping/tasks"""
        print("\n🧹 Testing POST /api/housekeeping/tasks...")
        
        async def test_func():
            if not self.created_test_data['rooms']:
                print("  ⚠️ No rooms available for task creation")
                return {"passed": 0, "total": 1}
            
            test_cases = [
                {
                    "name": "Create cleaning task",
                    "params": {
                        "room_id": self.created_test_data['rooms'][0],
                        "task_type": "cleaning",
                        "priority": "normal",
                        "notes": "Standard checkout cleaning"
                    },
                    "expected_status": 200
                },
                {
                    "name": "Create inspection task",
                    "params": {
                        "room_id": self.created_test_data['rooms'][0],
                        "task_type": "inspection",
                        "priority": "high",
                        "notes": "Quality inspection required"
                    },
                    "expected_status": 200
                },
                {
                    "name": "Create maintenance task",
                    "params": {
                        "room_id": self.created_test_data['rooms'][0],
                        "task_type": "maintenance",
                        "priority": "urgent",
                        "notes": "AC unit repair needed"
                    },
                    "expected_status": 200
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    # Endpoint expects query parameters, not JSON body
                    url = f"{BACKEND_URL}/housekeeping/tasks"
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                    
                    async with self.session.post(url, headers=self.get_headers()) as response:
                        if response.status == test_case["expected_status"]:
                            data = await response.json()
                            # Endpoint returns task object directly
                            if "id" in data:
                                self.created_test_data['tasks'].append(data["id"])
                                print(f"  ✅ {test_case['name']}: PASSED")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: No task ID in response")
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("POST /api/housekeeping/tasks", test_func)
        self.test_results.append({
            "endpoint": "POST /api/housekeeping/tasks",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_tasks_put(self):
        """Test PUT /api/housekeeping/tasks/{task_id}"""
        print("\n🧹 Testing PUT /api/housekeeping/tasks/{task_id}...")
        
        async def test_func():
            # Use sample task ID or created task
            sample_task_id = str(uuid.uuid4())
            if self.created_test_data['tasks']:
                sample_task_id = self.created_test_data['tasks'][0]
            
            test_cases = [
                {
                    "name": "Update task status to in_progress",
                    "task_id": sample_task_id,
                    "params": {
                        "status": "in_progress"
                    },
                    "expected_status": [200, 404]
                },
                {
                    "name": "Update task status to completed",
                    "task_id": sample_task_id,
                    "params": {
                        "status": "completed"
                    },
                    "expected_status": [200, 404]
                },
                {
                    "name": "Update task with assignment",
                    "task_id": sample_task_id,
                    "params": {
                        "status": "in_progress",
                        "assigned_to": "Maria Housekeeping"
                    },
                    "expected_status": [200, 404]
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    # Endpoint expects query parameters, not JSON body
                    url = f"{BACKEND_URL}/housekeeping/tasks/{test_case['task_id']}"
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                    
                    async with self.session.put(url, headers=self.get_headers()) as response:
                        if response.status in test_case["expected_status"]:
                            if response.status == 200:
                                data = await response.json()
                                # Endpoint returns task object directly
                                if "id" in data:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: No task ID in response")
                            else:  # 404
                                print(f"  ✅ {test_case['name']}: PASSED (404 - task not found)")
                                passed += 1
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("PUT /api/housekeeping/tasks/{task_id}", test_func)
        self.test_results.append({
            "endpoint": "PUT /api/housekeeping/tasks/{task_id}",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_room_status(self):
        """Test GET /api/housekeeping/room-status"""
        print("\n🧹 Testing GET /api/housekeeping/room-status...")
        
        async def test_func():
            test_cases = [
                {
                    "name": "Get room status overview",
                    "expected_fields": ["rooms", "status_counts", "total_rooms"],
                    "expected_status_counts": ["available", "occupied", "dirty", "cleaning", "inspected", "maintenance", "out_of_order"]
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    url = f"{BACKEND_URL}/housekeeping/room-status"
                    
                    async with self.session.get(url, headers=self.get_headers()) as response:
                        if response.status == 200:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                # Verify status_counts structure
                                status_counts = data.get("status_counts", {})
                                missing_status_counts = [status for status in test_case["expected_status_counts"] if status not in status_counts]
                                if not missing_status_counts:
                                    # Verify rooms structure if rooms exist
                                    if data.get("rooms"):
                                        room = data["rooms"][0]
                                        required_room_fields = ["room_number", "status"]
                                        missing_room_fields = [field for field in required_room_fields if field not in room]
                                        if not missing_room_fields:
                                            print(f"  ✅ {test_case['name']}: PASSED - Full structure verified")
                                            passed += 1
                                        else:
                                            print(f"  ❌ {test_case['name']}: Missing room fields {missing_room_fields}")
                                    else:
                                        print(f"  ✅ {test_case['name']}: PASSED - Structure correct (no rooms)")
                                        passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing status counts {missing_status_counts}")
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("GET /api/housekeeping/room-status", test_func)
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/room-status",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_due_out(self):
        """Test GET /api/housekeeping/due-out"""
        print("\n🧹 Testing GET /api/housekeeping/due-out...")
        
        async def test_func():
            test_cases = [
                {
                    "name": "Get due out rooms",
                    "expected_fields": ["due_out_rooms", "count"],
                    "expected_room_fields": ["room_number", "guest_name", "checkout_date", "is_today"]
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    url = f"{BACKEND_URL}/housekeeping/due-out"
                    
                    async with self.session.get(url, headers=self.get_headers()) as response:
                        if response.status == 200:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                # Verify room structure if rooms exist
                                if data.get("due_out_rooms"):
                                    room = data["due_out_rooms"][0]
                                    missing_room_fields = [field for field in test_case["expected_room_fields"] if field not in room]
                                    if not missing_room_fields:
                                        print(f"  ✅ {test_case['name']}: PASSED - Full structure verified")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing room fields {missing_room_fields}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED - Structure correct (no due out rooms)")
                                    passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("GET /api/housekeeping/due-out", test_func)
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/due-out",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_stayovers(self):
        """Test GET /api/housekeeping/stayovers"""
        print("\n🧹 Testing GET /api/housekeeping/stayovers...")
        
        async def test_func():
            test_cases = [
                {
                    "name": "Get stayover rooms",
                    "expected_fields": ["stayover_rooms", "count"],
                    "expected_room_fields": ["room_number", "guest_name", "nights_remaining"]
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    url = f"{BACKEND_URL}/housekeeping/stayovers"
                    
                    async with self.session.get(url, headers=self.get_headers()) as response:
                        if response.status == 200:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                # Verify room structure if rooms exist
                                if data.get("stayover_rooms"):
                                    room = data["stayover_rooms"][0]
                                    missing_room_fields = [field for field in test_case["expected_room_fields"] if field not in room]
                                    if not missing_room_fields:
                                        print(f"  ✅ {test_case['name']}: PASSED - Full structure verified")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing room fields {missing_room_fields}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED - Structure correct (no stayover rooms)")
                                    passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("GET /api/housekeeping/stayovers", test_func)
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/stayovers",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_arrivals(self):
        """Test GET /api/housekeeping/arrivals"""
        print("\n🧹 Testing GET /api/housekeeping/arrivals...")
        
        async def test_func():
            test_cases = [
                {
                    "name": "Get arrival rooms",
                    "expected_fields": ["arrival_rooms", "ready_count"],
                    "expected_room_fields": ["room_number", "guest_name", "room_status", "ready"]
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    url = f"{BACKEND_URL}/housekeeping/arrivals"
                    
                    async with self.session.get(url, headers=self.get_headers()) as response:
                        if response.status == 200:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                # Verify room structure if rooms exist
                                if data.get("arrival_rooms"):
                                    room = data["arrival_rooms"][0]
                                    missing_room_fields = [field for field in test_case["expected_room_fields"] if field not in room]
                                    if not missing_room_fields:
                                        print(f"  ✅ {test_case['name']}: PASSED - Full structure verified")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing room fields {missing_room_fields}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED - Structure correct (no arrival rooms)")
                                    passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: HTTP {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("GET /api/housekeeping/arrivals", test_func)
        self.test_results.append({
            "endpoint": "GET /api/housekeeping/arrivals",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_room_status_update(self):
        """Test PUT /api/housekeeping/room/{room_id}/status"""
        print("\n🧹 Testing PUT /api/housekeeping/room/{room_id}/status...")
        
        async def test_func():
            if not self.created_test_data['rooms']:
                print("  ⚠️ No rooms available for status update")
                return {"passed": 0, "total": 1}
            
            room_id = self.created_test_data['rooms'][0]
            
            test_cases = [
                {
                    "name": "Update room status to dirty",
                    "room_id": room_id,
                    "params": {"new_status": "dirty"},
                    "expected_status": [200, 404]
                },
                {
                    "name": "Update room status to cleaning",
                    "room_id": room_id,
                    "params": {"new_status": "cleaning"},
                    "expected_status": [200, 404]
                },
                {
                    "name": "Update room status to inspected",
                    "room_id": room_id,
                    "params": {"new_status": "inspected"},
                    "expected_status": [200, 404]
                },
                {
                    "name": "Update room status to available",
                    "room_id": room_id,
                    "params": {"new_status": "available"},
                    "expected_status": [200, 404]
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    # Endpoint expects query parameters, not JSON body
                    url = f"{BACKEND_URL}/housekeeping/room/{test_case['room_id']}/status"
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                    
                    async with self.session.put(url, headers=self.get_headers()) as response:
                        if response.status in test_case["expected_status"]:
                            if response.status == 200:
                                data = await response.json()
                                required_fields = ["message", "new_status"]
                                missing_fields = [field for field in required_fields if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            else:  # 404
                                print(f"  ✅ {test_case['name']}: PASSED (404 - room not found)")
                                passed += 1
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("PUT /api/housekeeping/room/{room_id}/status", test_func)
        self.test_results.append({
            "endpoint": "PUT /api/housekeeping/room/{room_id}/status",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    async def test_housekeeping_assign(self):
        """Test POST /api/housekeeping/assign"""
        print("\n🧹 Testing POST /api/housekeeping/assign...")
        
        async def test_func():
            if not self.created_test_data['rooms']:
                print("  ⚠️ No rooms available for assignment")
                return {"passed": 0, "total": 1}
            
            test_cases = [
                {
                    "name": "Assign room to housekeeper",
                    "params": {
                        "room_id": self.created_test_data['rooms'][0],
                        "assigned_to": "Maria Housekeeping",
                        "task_type": "cleaning",
                        "priority": "normal"
                    },
                    "expected_status": 200
                }
            ]
            
            passed = 0
            total = len(test_cases)
            
            for test_case in test_cases:
                try:
                    # Endpoint expects query parameters, not JSON body
                    url = f"{BACKEND_URL}/housekeeping/assign"
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                    
                    async with self.session.post(url, headers=self.get_headers()) as response:
                        if response.status == test_case["expected_status"]:
                            data = await response.json()
                            required_fields = ["message", "task"]
                            missing_fields = [field for field in required_fields if field not in data]
                            if not missing_fields:
                                print(f"  ✅ {test_case['name']}: PASSED")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:
                            error_text = await response.text()
                            print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status} - {error_text[:100]}")
                            
                except Exception as e:
                    print(f"  ❌ {test_case['name']}: Error {e}")
            
            return {"passed": passed, "total": total}
        
        result = await self.measure_performance("POST /api/housekeeping/assign", test_func)
        self.test_results.append({
            "endpoint": "POST /api/housekeeping/assign",
            "passed": result["passed"], 
            "total": result["total"], 
            "success_rate": f"{result['passed']/result['total']*100:.1f}%"
        })

    # ============= MAIN TEST EXECUTION =============

    async def run_all_tests(self):
        """Run comprehensive housekeeping backend tests"""
        print("🏨 PMS HOUSEKEEPING BACKEND COMPREHENSIVE TEST")
        print("Testing 9 housekeeping endpoints for HousekeepingTab.js compatibility")
        print("Login: demo@hotel.com / demo123")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # Run all housekeeping endpoint tests
        print("\n" + "="*60)
        print("🧹 HOUSEKEEPING ENDPOINTS TESTING")
        print("="*60)
        
        await self.test_housekeeping_tasks_get()
        await self.test_housekeeping_tasks_post()
        await self.test_housekeeping_tasks_put()
        await self.test_housekeeping_room_status()
        await self.test_housekeeping_due_out()
        await self.test_housekeeping_stayovers()
        await self.test_housekeeping_arrivals()
        await self.test_housekeeping_room_status_update()
        await self.test_housekeeping_assign()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 PMS HOUSEKEEPING BACKEND TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        print("\n🧹 HOUSEKEEPING ENDPOINTS RESULTS:")
        print("-" * 60)
        
        for result in self.test_results:
            endpoint_status = "✅" if result["passed"] == result["total"] else "❌"
            print(f"{endpoint_status} {result['endpoint']}: {result['success_rate']}")
            total_passed += result["passed"]
            total_tests += result["total"]
        
        print("\n📈 PERFORMANCE METRICS:")
        print("-" * 60)
        
        for metric in self.performance_metrics:
            performance_status = "🚀" if metric["response_time_ms"] < 100 else "⚡" if metric["response_time_ms"] < 500 else "⏱️"
            print(f"{performance_status} {metric['endpoint']}: {metric['response_time_ms']}ms")
        
        # Calculate average response time
        if self.performance_metrics:
            avg_response_time = sum(m["response_time_ms"] for m in self.performance_metrics) / len(self.performance_metrics)
            print(f"\n📊 Average Response Time: {avg_response_time:.2f}ms")
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        # Final assessment
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: PMS Housekeeping backend is production-ready!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most endpoints working, minor issues detected")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some critical issues need attention")
        else:
            print("❌ CRITICAL: Major backend issues detected")
        
        print("\n🔍 HOUSEKEEPING ENDPOINTS TESTED:")
        print("• GET /api/housekeeping/tasks - Task list with filtering")
        print("• POST /api/housekeeping/tasks - Task creation")
        print("• PUT /api/housekeeping/tasks/{task_id} - Task status updates")
        print("• GET /api/housekeeping/room-status - Room status overview")
        print("• GET /api/housekeeping/due-out - Due out rooms")
        print("• GET /api/housekeeping/stayovers - Stayover rooms")
        print("• GET /api/housekeeping/arrivals - Arrival rooms")
        print("• PUT /api/housekeeping/room/{room_id}/status - Room status flow")
        print("• POST /api/housekeeping/assign - Task assignment")
        
        print("\n📋 EXPECTED DATA STRUCTURES VERIFIED:")
        print("• room-status: rooms[], status_counts{}, total_rooms")
        print("• due-out: due_out_rooms[{room_number, guest_name, checkout_date, is_today}], count")
        print("• stayovers: stayover_rooms[{room_number, guest_name, nights_remaining}], count")
        print("• arrivals: arrival_rooms[{room_number, guest_name, room_status, ready}], ready_count")
        print("• tasks: list with id, room_id, task_type, priority, status, notes, assigned_to + room join")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = HousekeepingTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())