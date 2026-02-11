#!/usr/bin/env python3
"""
FINAL COMPREHENSIVE BACKEND TEST - Verify All Fixed Endpoints

This test focuses on the specific endpoints mentioned in the review request:

PRIORITY 1 - RECENTLY FIXED:
1. POST /api/notifications/send-system-alert 
   - Verify SystemAlertRequest model works
   - Test with: {"type": "maintenance", "title": "Test", "message": "Test message", "priority": "high", "target_roles": ["admin"]}

2. PUT /api/notifications/preferences
   - Verify updated_preference field is returned
   - Test with: {"notification_type": "approval_request", "enabled": true, "channels": ["in_app"]}

3. GET /api/guests/{guest_id}/profile-complete
   - Verify 500 error is fixed (removed @cached decorator)
   - Test with any existing guest_id

PRIORITY 2 - VERIFY WORKING:
4. GET /api/approvals/pending - Confirm urgent_count field exists
5. GET /api/approvals/my-requests - Confirm returns 'requests' field
6. POST /api/messaging/send-message - Verify working with correct model
7. POST /api/pos/create-order - Verify model validation
8. GET /api/rms/price-recommendation-slider?room_type=Standard&check_in_date=2025-12-01

PERFORMANCE CHECK:
9. GET /api/monitoring/health - Should return healthy
10. GET /api/monitoring/system - Check CPU/Memory metrics
11. GET /api/monitoring/database - Check connection pool stats

Use admin@hotel.com / admin123 for authentication.
Report success rate and any remaining issues.
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
BACKEND_URL = "https://unitcare-1.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class FinalComprehensiveTester:
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
            'approval_requests': [],
            'notifications': []
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
        """Create test data needed for comprehensive testing"""
        print("\n🔧 Creating test data for comprehensive endpoint testing...")
        
        try:
            # Create test guest for profile testing
            guest_data = {
                "name": "Sarah Johnson",
                "email": "sarah.johnson@hotel.com",
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

            # Get available room for booking tests
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

            # Create test booking for POS testing
            booking_data = {
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": (datetime.now(timezone.utc)).isoformat(),
                "check_out": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "adults": 2,
                "children": 0,
                "guests_count": 2,
                "total_amount": 300.0,
                "special_requests": "Late checkout preferred"
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

    # ============= PRIORITY 1 - RECENTLY FIXED ENDPOINTS =============

    async def test_send_system_alert(self):
        """Test POST /api/notifications/send-system-alert - RECENTLY FIXED"""
        print("\n🔔 Testing Send System Alert Endpoint (PRIORITY 1 - RECENTLY FIXED)...")
        print("🔧 EXPECTED FIX: SystemAlertRequest model should work correctly")
        
        test_cases = [
            {
                "name": "Send maintenance alert to admin roles",
                "data": {
                    "type": "maintenance",
                    "title": "Test Maintenance Alert",
                    "message": "Test message for maintenance alert",
                    "priority": "high",
                    "target_roles": ["admin"]
                },
                "expected_status": [200, 422],  # 200 if fixed, 422 if still has validation issues
                "expected_fields": ["message", "notifications_sent", "target_roles"] if 200 else []
            },
            {
                "name": "Send system alert with different priority",
                "data": {
                    "type": "system",
                    "title": "System Update",
                    "message": "System will be updated tonight",
                    "priority": "normal",
                    "target_roles": ["admin", "supervisor"]
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "notifications_sent", "target_roles"] if 200 else []
            },
            {
                "name": "Send urgent alert to multiple roles",
                "data": {
                    "type": "emergency",
                    "title": "Emergency Alert",
                    "message": "Emergency procedures activated",
                    "priority": "urgent",
                    "target_roles": ["admin", "supervisor", "front_desk"]
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "notifications_sent", "target_roles"] if 200 else []
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/send-system-alert"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            try:
                                data = await response.json() if response_text else {}
                                missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED - SystemAlertRequest model working")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            except:
                                print(f"  ❌ {test_case['name']}: Invalid JSON response")
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: STILL FAILING - Validation error (422)")
                            print(f"      Response: {response_text[:200]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/notifications/send-system-alert",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "HIGH - RECENTLY FIXED"
        })

    async def test_update_notification_preferences(self):
        """Test PUT /api/notifications/preferences - RECENTLY FIXED"""
        print("\n🔔 Testing Update Notification Preferences Endpoint (PRIORITY 1 - RECENTLY FIXED)...")
        print("🔧 EXPECTED FIX: Should return updated_preference field")
        
        test_cases = [
            {
                "name": "Update approval_request notification preference",
                "data": {
                    "notification_type": "approval_request",
                    "enabled": True,
                    "channels": ["in_app"]
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "updated_preference"] if 200 else []
            },
            {
                "name": "Update booking_updates notification preference",
                "data": {
                    "notification_type": "booking_updates",
                    "enabled": True,
                    "channels": ["in_app", "email"]
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "updated_preference"] if 200 else []
            },
            {
                "name": "Disable maintenance_alerts notification",
                "data": {
                    "notification_type": "maintenance_alerts",
                    "enabled": False,
                    "channels": ["in_app"]
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "updated_preference"] if 200 else []
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/preferences"
                
                async with self.session.put(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            try:
                                data = await response.json() if response_text else {}
                                missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED - updated_preference field returned")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            except:
                                print(f"  ❌ {test_case['name']}: Invalid JSON response")
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: STILL FAILING - Validation error (422)")
                            print(f"      Response: {response_text[:200]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "PUT /api/notifications/preferences",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "HIGH - RECENTLY FIXED"
        })

    async def test_guest_profile_complete(self):
        """Test GET /api/guests/{guest_id}/profile-complete - RECENTLY FIXED"""
        print("\n👤 Testing Guest Profile Complete Endpoint (PRIORITY 1 - RECENTLY FIXED)...")
        print("🔧 EXPECTED FIX: 500 error should be fixed (removed @cached decorator)")
        
        # Use created test guest
        guest_id = self.created_test_data['guests'][0] if self.created_test_data['guests'] else str(uuid.uuid4())
        
        test_cases = [
            {
                "name": "Get complete profile for existing guest",
                "guest_id": guest_id,
                "expected_status": [200, 500],  # 200 if fixed, 500 if still broken
                "expected_fields": ["guest_id", "stay_history", "preferences", "tags", "total_stays", "vip_status", "blacklist_status"] if 200 else []
            },
            {
                "name": "Get complete profile for non-existent guest",
                "guest_id": "non-existent-guest-id",
                "expected_status": 404,
                "expected_fields": []
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/guests/{test_case['guest_id']}/profile-complete"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    response_text = await response.text()
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            try:
                                data = await response.json() if response_text else {}
                                missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED - 500 error fixed!")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            except:
                                print(f"  ❌ {test_case['name']}: Invalid JSON response")
                        elif response.status == 404:
                            print(f"  ✅ {test_case['name']}: PASSED (404 as expected)")
                            passed += 1
                        else:  # 500
                            print(f"  ❌ {test_case['name']}: STILL FAILING - 500 error persists")
                            print(f"      Response: {response_text[:200]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/guests/{guest_id}/profile-complete",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "HIGH - RECENTLY FIXED"
        })

    # ============= PRIORITY 2 - VERIFY WORKING ENDPOINTS =============

    async def test_approvals_pending(self):
        """Test GET /api/approvals/pending - Confirm urgent_count field exists"""
        print("\n📋 Testing Approvals Pending Endpoint (PRIORITY 2 - VERIFY WORKING)...")
        print("🔧 VERIFICATION: Confirm urgent_count field exists in response")
        
        test_cases = [
            {
                "name": "Get pending approvals - verify urgent_count field",
                "params": {},
                "expected_fields": ["approvals", "count", "urgent_count"]
            },
            {
                "name": "Filter by priority - urgent",
                "params": {"priority": "urgent"},
                "expected_fields": ["approvals", "count", "urgent_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/approvals/pending"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED - urgent_count field exists")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/approvals/pending",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "MEDIUM - VERIFY WORKING"
        })

    async def test_approvals_my_requests(self):
        """Test GET /api/approvals/my-requests - Confirm returns 'requests' field"""
        print("\n📋 Testing Approvals My Requests Endpoint (PRIORITY 2 - VERIFY WORKING)...")
        print("🔧 VERIFICATION: Confirm returns 'requests' field (not 'approvals')")
        
        test_cases = [
            {
                "name": "Get my requests - verify 'requests' field name",
                "params": {},
                "expected_fields": ["requests", "count"]
            },
            {
                "name": "Filter by status - pending",
                "params": {"status": "pending"},
                "expected_fields": ["requests", "count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/approvals/my-requests"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED - returns 'requests' field")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            # Check if it returns 'approvals' instead
                            if 'approvals' in data:
                                print(f"      ⚠️ Returns 'approvals' field instead of 'requests'")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/approvals/my-requests",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "MEDIUM - VERIFY WORKING"
        })

    async def test_messaging_send_message(self):
        """Test POST /api/messaging/send-message - Verify working with correct model"""
        print("\n💬 Testing Messaging Send Message Endpoint (PRIORITY 2 - VERIFY WORKING)...")
        print("🔧 VERIFICATION: Verify working with correct model validation")
        
        test_cases = [
            {
                "name": "Send WhatsApp message",
                "data": {
                    "channel": "whatsapp",
                    "to": "+1-555-0123",
                    "message": "Test WhatsApp message",
                    "booking_id": self.created_test_data['bookings'][0] if self.created_test_data['bookings'] else None
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "message_id", "status", "channel"] if 200 else []
            },
            {
                "name": "Send SMS message",
                "data": {
                    "channel": "sms",
                    "to": "+1-555-0123",
                    "message": "Test SMS message"
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "message_id", "status", "channel"] if 200 else []
            },
            {
                "name": "Send Email message",
                "data": {
                    "channel": "email",
                    "to": "test@hotel.com",
                    "message": "Test email message",
                    "subject": "Test Subject"
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "message_id", "status", "channel"] if 200 else []
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/messaging/send-message"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            try:
                                data = await response.json() if response_text else {}
                                missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED - model validation working")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            except:
                                print(f"  ❌ {test_case['name']}: Invalid JSON response")
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: STILL FAILING - Validation error (422)")
                            print(f"      Response: {response_text[:200]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/messaging/send-message",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "MEDIUM - VERIFY WORKING"
        })

    async def test_pos_create_order(self):
        """Test POST /api/pos/create-order - Verify model validation"""
        print("\n🍽️ Testing POS Create Order Endpoint (PRIORITY 2 - VERIFY WORKING)...")
        print("🔧 VERIFICATION: Verify model validation working correctly")
        
        booking_id = self.created_test_data['bookings'][0] if self.created_test_data['bookings'] else str(uuid.uuid4())
        
        test_cases = [
            {
                "name": "Create POS order with multiple items",
                "data": {
                    "booking_id": booking_id,
                    "items": [
                        {"name": "Burger", "quantity": 2, "price": 15.0},
                        {"name": "Fries", "quantity": 2, "price": 5.0},
                        {"name": "Coke", "quantity": 2, "price": 3.0}
                    ],
                    "table_number": "T-12",
                    "server_name": "John Doe",
                    "post_to_folio": True,
                    "notes": "Extra ketchup"
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "order_id", "total_amount", "items"] if 200 else []
            },
            {
                "name": "Create simple POS order",
                "data": {
                    "booking_id": booking_id,
                    "items": [
                        {"name": "Coffee", "quantity": 1, "price": 4.0}
                    ],
                    "server_name": "Jane Smith",
                    "post_to_folio": False
                },
                "expected_status": [200, 422],
                "expected_fields": ["message", "order_id", "total_amount", "items"] if 200 else []
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/pos/create-order"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            try:
                                data = await response.json() if response_text else {}
                                missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED - model validation working")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            except:
                                print(f"  ❌ {test_case['name']}: Invalid JSON response")
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: STILL FAILING - Validation error (422)")
                            print(f"      Response: {response_text[:200]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/pos/create-order",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "MEDIUM - VERIFY WORKING"
        })

    async def test_rms_price_recommendation_slider(self):
        """Test GET /api/rms/price-recommendation-slider - Verify working"""
        print("\n💰 Testing RMS Price Recommendation Slider Endpoint (PRIORITY 2 - VERIFY WORKING)...")
        print("🔧 VERIFICATION: Verify endpoint working with correct parameters")
        
        test_cases = [
            {
                "name": "Get price recommendation for Standard room",
                "params": {
                    "room_type": "Standard",
                    "check_in_date": "2025-12-01"
                },
                "expected_status": [200, 422],
                "expected_fields": ["min_price", "recommended_price", "max_price", "occupancy_analysis"] if 200 else []
            },
            {
                "name": "Get price recommendation for Deluxe room",
                "params": {
                    "room_type": "Deluxe",
                    "check_in_date": "2025-12-15"
                },
                "expected_status": [200, 422],
                "expected_fields": ["min_price", "recommended_price", "max_price", "occupancy_analysis"] if 200 else []
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/rms/price-recommendation-slider"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    response_text = await response.text()
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            try:
                                data = await response.json() if response_text else {}
                                missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED - endpoint working")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            except:
                                print(f"  ❌ {test_case['name']}: Invalid JSON response")
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: STILL FAILING - Validation error (422)")
                            print(f"      Response: {response_text[:200]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/rms/price-recommendation-slider",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "MEDIUM - VERIFY WORKING"
        })

    # ============= PERFORMANCE CHECK ENDPOINTS =============

    async def test_monitoring_health(self):
        """Test GET /api/monitoring/health - Should return healthy"""
        print("\n🏥 Testing Monitoring Health Endpoint (PERFORMANCE CHECK)...")
        print("🔧 VERIFICATION: Should return healthy status")
        
        test_cases = [
            {
                "name": "Get system health status",
                "expected_fields": ["status", "database", "cache", "system_metrics", "timestamp"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/monitoring/health"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            status = data.get("status", "unknown")
                            if status == "healthy":
                                print(f"  ✅ {test_case['name']}: PASSED - System is healthy")
                                passed += 1
                            else:
                                print(f"  ⚠️ {test_case['name']}: System status is '{status}' (not healthy)")
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/monitoring/health",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "LOW - PERFORMANCE CHECK"
        })

    async def test_monitoring_system(self):
        """Test GET /api/monitoring/system - Check CPU/Memory metrics"""
        print("\n💻 Testing Monitoring System Endpoint (PERFORMANCE CHECK)...")
        print("🔧 VERIFICATION: Check CPU/Memory metrics are returned")
        
        test_cases = [
            {
                "name": "Get system metrics",
                "expected_fields": ["cpu", "memory", "disk", "network", "timestamp"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/monitoring/system"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            cpu_usage = data.get("cpu", {}).get("usage_percent", 0)
                            memory_usage = data.get("memory", {}).get("usage_percent", 0)
                            print(f"  ✅ {test_case['name']}: PASSED - CPU: {cpu_usage}%, Memory: {memory_usage}%")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/monitoring/system",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "LOW - PERFORMANCE CHECK"
        })

    async def test_monitoring_database(self):
        """Test GET /api/monitoring/database - Check connection pool stats"""
        print("\n🗄️ Testing Monitoring Database Endpoint (PERFORMANCE CHECK)...")
        print("🔧 VERIFICATION: Check connection pool stats are returned")
        
        test_cases = [
            {
                "name": "Get database connection pool stats",
                "expected_fields": ["connection_pool", "collections", "network_stats", "timestamp"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/monitoring/database"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            pool = data.get("connection_pool", {})
                            current_connections = pool.get("current_connections", 0)
                            available_connections = pool.get("available_connections", 0)
                            print(f"  ✅ {test_case['name']}: PASSED - Current: {current_connections}, Available: {available_connections}")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/monitoring/database",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "priority": "LOW - PERFORMANCE CHECK"
        })

    # ============= MAIN TEST EXECUTION =============

    async def run_all_tests(self):
        """Run comprehensive testing of all specified endpoints"""
        print("🚀 FINAL COMPREHENSIVE BACKEND TEST - Verify All Fixed Endpoints")
        print("Testing 11 CRITICAL ENDPOINTS as specified in review request")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # PRIORITY 1 - RECENTLY FIXED ENDPOINTS
        print("\n" + "="*60)
        print("🔥 PRIORITY 1 - RECENTLY FIXED ENDPOINTS (3 endpoints)")
        print("="*60)
        await self.test_send_system_alert()
        await self.test_update_notification_preferences()
        await self.test_guest_profile_complete()
        
        # PRIORITY 2 - VERIFY WORKING ENDPOINTS
        print("\n" + "="*60)
        print("✅ PRIORITY 2 - VERIFY WORKING ENDPOINTS (5 endpoints)")
        print("="*60)
        await self.test_approvals_pending()
        await self.test_approvals_my_requests()
        await self.test_messaging_send_message()
        await self.test_pos_create_order()
        await self.test_rms_price_recommendation_slider()
        
        # PERFORMANCE CHECK ENDPOINTS
        print("\n" + "="*60)
        print("📊 PERFORMANCE CHECK ENDPOINTS (3 endpoints)")
        print("="*60)
        await self.test_monitoring_health()
        await self.test_monitoring_system()
        await self.test_monitoring_database()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 FINAL COMPREHENSIVE BACKEND TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        # Group results by priority
        priorities = {
            "HIGH - RECENTLY FIXED": [],
            "MEDIUM - VERIFY WORKING": [],
            "LOW - PERFORMANCE CHECK": []
        }
        
        for result in self.test_results:
            priority = result.get("priority", "UNKNOWN")
            priorities[priority].append(result)
        
        print("\n🎯 RESULTS BY PRIORITY:")
        print("-" * 60)
        
        for priority, results in priorities.items():
            if results:
                priority_passed = sum(r["passed"] for r in results)
                priority_total = sum(r["total"] for r in results)
                priority_rate = (priority_passed / priority_total * 100) if priority_total > 0 else 0
                
                status = "✅" if priority_rate == 100 else "⚠️" if priority_rate >= 50 else "❌"
                print(f"\n{status} {priority}: {priority_passed}/{priority_total} ({priority_rate:.1f}%)")
                
                for result in results:
                    endpoint_status = "✅" if result["passed"] == result["total"] else "❌"
                    print(f"   {endpoint_status} {result['endpoint']}: {result['success_rate']}")
                
                total_passed += priority_passed
                total_tests += priority_total
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: All fixes successful! Backend endpoints working perfectly!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most fixes successful, minor issues remain")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some fixes successful, but critical issues remain")
        else:
            print("❌ CRITICAL: Major fixes not successful, significant issues persist")
        
        print("\n🔍 KEY ENDPOINTS TESTED:")
        print("• POST /api/notifications/send-system-alert - SystemAlertRequest model fix")
        print("• PUT /api/notifications/preferences - updated_preference field fix")
        print("• GET /api/guests/{guest_id}/profile-complete - 500 error fix (@cached decorator)")
        print("• GET /api/approvals/pending - urgent_count field verification")
        print("• GET /api/approvals/my-requests - 'requests' field verification")
        print("• POST /api/messaging/send-message - model validation verification")
        print("• POST /api/pos/create-order - model validation verification")
        print("• GET /api/rms/price-recommendation-slider - parameter validation verification")
        print("• GET /api/monitoring/health - system health check")
        print("• GET /api/monitoring/system - CPU/Memory metrics check")
        print("• GET /api/monitoring/database - connection pool stats check")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = FinalComprehensiveTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())