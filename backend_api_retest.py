#!/usr/bin/env python3
"""
BACKEND API RE-TESTING - Focus on Previously Failed Endpoints

This script tests the specific endpoints mentioned in the review request:

FIXED ENDPOINTS TO VERIFY:
1. POST /api/notifications/send-system-alert - Now has SystemAlertRequest model
2. PUT /api/notifications/preferences - Now returns updated_preference field

ENDPOINTS TO INVESTIGATE (422 ERRORS):
3. POST /api/reservations/{booking_id}/extra-charges
4. POST /api/reservations/multi-room
5. POST /api/guests/{guest_id}/preferences
6. POST /api/guests/{guest_id}/tags
7. POST /api/messaging/send-message
8. POST /api/pos/create-order
9. GET /api/rms/price-recommendation-slider

500 ERROR TO DEBUG:
10. GET /api/guests/{guest_id}/profile-complete

FIELD MISMATCH TO VERIFY:
11. GET /api/approvals/pending - Should return urgent_count field
12. GET /api/approvals/my-requests - Should return 'requests' field (not 'approvals')
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
BACKEND_URL = "https://code-cleanup-135.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class BackendAPIRetester:
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
        """Create comprehensive test data for API testing"""
        print("\n🔧 Creating test data for API endpoint testing...")
        
        try:
            # Create test guest
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
                "check_in": (datetime.now(timezone.utc)).isoformat(),
                "check_out": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "adults": 2,
                "children": 0,
                "children_ages": [],
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

    # ============= FIXED ENDPOINTS TO VERIFY =============

    async def test_send_system_alert_fixed(self):
        """Test POST /api/notifications/send-system-alert - FIXED with SystemAlertRequest model"""
        print("\n🔔 Testing Send System Alert Endpoint (FIXED)...")
        print("🔧 EXPECTED FIX: Now has SystemAlertRequest model")
        
        test_cases = [
            {
                "name": "Send maintenance alert with new model structure",
                "data": {
                    "type": "maintenance",
                    "title": "Test Alert",
                    "message": "Test message",
                    "priority": "high",
                    "target_roles": ["admin"]
                },
                "expected_status": [200, 403, 422],
                "expected_fields": ["message", "notifications_sent", "target_roles"]
            },
            {
                "name": "Send system alert with all fields",
                "data": {
                    "type": "system",
                    "title": "System Update Alert",
                    "message": "System will be updated tonight",
                    "priority": "normal",
                    "target_roles": ["admin", "supervisor"]
                },
                "expected_status": [200, 403, 422],
                "expected_fields": ["message", "notifications_sent", "target_roles"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/send-system-alert"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            try:
                                data = await response.json() if response.content_type == 'application/json' else {}
                                missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                                if not missing_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED - SystemAlertRequest model working")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            except:
                                print(f"  ❌ {test_case['name']}: Invalid JSON response")
                        elif response.status == 422:
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:200]}...")
                        else:  # 403
                            print(f"  ✅ {test_case['name']}: PASSED (403 - access control working)")
                            passed += 1
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/notifications/send-system-alert",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_update_notification_preferences_fixed(self):
        """Test PUT /api/notifications/preferences - FIXED with updated_preference field"""
        print("\n🔔 Testing Update Notification Preferences Endpoint (FIXED)...")
        print("🔧 EXPECTED FIX: Now returns updated_preference field")
        
        test_cases = [
            {
                "name": "Update approval request notifications",
                "data": {
                    "notification_type": "approval_request",
                    "enabled": True,
                    "channels": ["in_app", "email"]
                },
                "expected_status": 200,
                "expected_fields": ["message", "updated_preference"]
            },
            {
                "name": "Update maintenance alerts",
                "data": {
                    "notification_type": "maintenance_alerts",
                    "enabled": False,
                    "channels": ["in_app"]
                },
                "expected_status": 200,
                "expected_fields": ["message", "updated_preference"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/notifications/preferences"
                
                async with self.session.put(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status == test_case["expected_status"]:
                        try:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                print(f"  ✅ {test_case['name']}: PASSED - updated_preference field present")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        except:
                            print(f"  ❌ {test_case['name']}: Invalid JSON response")
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "PUT /api/notifications/preferences",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= ENDPOINTS TO INVESTIGATE (422 ERRORS) =============

    async def test_extra_charges_422_investigation(self):
        """Test POST /api/reservations/{booking_id}/extra-charges - 422 ERROR INVESTIGATION"""
        print("\n💰 Testing Extra Charges Endpoint (422 ERROR INVESTIGATION)...")
        print("🔧 ISSUE: ExtraChargeCreate model validation failing")
        
        if not self.created_test_data['bookings']:
            print("  ⚠️ No test booking available, skipping test")
            return
        
        booking_id = self.created_test_data['bookings'][0]
        
        test_cases = [
            {
                "name": "Add extra charge with ExtraChargeCreate model",
                "data": {
                    "charge_name": "Late checkout fee",
                    "charge_amount": 50.0,
                    "notes": "Guest requested late checkout"
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Add extra charge with alternative field names",
                "data": {
                    "name": "Minibar charges",
                    "amount": 25.0,
                    "description": "Minibar consumption"
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Add extra charge with minimal fields",
                "data": {
                    "charge_name": "Parking fee",
                    "charge_amount": 15.0
                },
                "expected_status": [200, 422]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/reservations/{booking_id}/extra-charges"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - Extra charge added successfully")
                            passed += 1
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/reservations/{booking_id}/extra-charges",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_multi_room_reservation_422_investigation(self):
        """Test POST /api/reservations/multi-room - 422 ERROR INVESTIGATION"""
        print("\n🏨 Testing Multi-Room Reservation Endpoint (422 ERROR INVESTIGATION)...")
        print("🔧 ISSUE: MultiRoomReservationCreate model validation failing")
        
        if not self.created_test_data['bookings']:
            print("  ⚠️ No test booking available, skipping test")
            return
        
        primary_booking_id = self.created_test_data['bookings'][0]
        
        test_cases = [
            {
                "name": "Create multi-room reservation with MultiRoomReservationCreate model",
                "data": {
                    "group_name": "Johnson Family Reunion",
                    "primary_booking_id": primary_booking_id,
                    "related_booking_ids": [str(uuid.uuid4()), str(uuid.uuid4())]
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Create multi-room reservation with alternative field names",
                "data": {
                    "name": "Corporate Event Group",
                    "main_booking": primary_booking_id,
                    "additional_bookings": [str(uuid.uuid4())]
                },
                "expected_status": [200, 422]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/reservations/multi-room"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - Multi-room reservation created")
                            passed += 1
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/reservations/multi-room",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_guest_preferences_422_investigation(self):
        """Test POST /api/guests/{guest_id}/preferences - 422 ERROR INVESTIGATION"""
        print("\n👤 Testing Guest Preferences Endpoint (422 ERROR INVESTIGATION)...")
        print("🔧 ISSUE: GuestPreferenceUpdate model validation failing")
        
        if not self.created_test_data['guests']:
            print("  ⚠️ No test guest available, skipping test")
            return
        
        guest_id = self.created_test_data['guests'][0]
        
        test_cases = [
            {
                "name": "Update guest preferences with GuestPreferenceUpdate model",
                "data": {
                    "pillow_type": "soft",
                    "floor_preference": "high",
                    "room_temperature": "cool",
                    "smoking": False,
                    "special_needs": "wheelchair accessible",
                    "dietary_restrictions": "vegetarian",
                    "newspaper_preference": "none"
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Update guest preferences with minimal fields",
                "data": {
                    "pillow_type": "firm",
                    "floor_preference": "low"
                },
                "expected_status": [200, 422]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/guests/{guest_id}/preferences"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - Guest preferences updated")
                            passed += 1
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/guests/{guest_id}/preferences",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_guest_tags_422_investigation(self):
        """Test POST /api/guests/{guest_id}/tags - 422 ERROR INVESTIGATION"""
        print("\n🏷️ Testing Guest Tags Endpoint (422 ERROR INVESTIGATION)...")
        print("🔧 ISSUE: GuestTagsUpdate model validation failing")
        
        if not self.created_test_data['guests']:
            print("  ⚠️ No test guest available, skipping test")
            return
        
        guest_id = self.created_test_data['guests'][0]
        
        test_cases = [
            {
                "name": "Update guest tags with GuestTagsUpdate model",
                "data": {
                    "tags": ["vip", "honeymoon", "frequent_guest", "high_spender"]
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Update guest tags with alternative structure",
                "data": {
                    "tag_list": ["business_traveler", "complainer"]
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Update guest tags with single tag",
                "data": {
                    "tags": ["anniversary"]
                },
                "expected_status": [200, 422]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/guests/{guest_id}/tags"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - Guest tags updated")
                            passed += 1
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/guests/{guest_id}/tags",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_messaging_send_message_422_investigation(self):
        """Test POST /api/messaging/send-message - 422 ERROR INVESTIGATION"""
        print("\n💬 Testing Messaging Send Message Endpoint (422 ERROR INVESTIGATION)...")
        print("🔧 ISSUE: SendMessageRequest model validation failing")
        
        if not self.created_test_data['guests']:
            print("  ⚠️ No test guest available, skipping test")
            return
        
        guest_id = self.created_test_data['guests'][0]
        
        test_cases = [
            {
                "name": "Send message with SendMessageRequest model",
                "data": {
                    "guest_id": guest_id,
                    "message_type": "whatsapp",
                    "recipient": "+1-555-0199",
                    "message_content": "Welcome to our hotel!"
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Send SMS message",
                "data": {
                    "guest_id": guest_id,
                    "message_type": "sms",
                    "recipient": "+1-555-0199",
                    "message_content": "Your room is ready for check-in"
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Send email message",
                "data": {
                    "guest_id": guest_id,
                    "message_type": "email",
                    "recipient": "sarah.johnson@hotel.com",
                    "message_content": "Thank you for staying with us",
                    "subject": "Thank You"
                },
                "expected_status": [200, 422]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/messaging/send-message"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - Message sent successfully")
                            passed += 1
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/messaging/send-message",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_pos_create_order_422_investigation(self):
        """Test POST /api/pos/create-order - 422 ERROR INVESTIGATION"""
        print("\n🍽️ Testing POS Create Order Endpoint (422 ERROR INVESTIGATION)...")
        print("🔧 ISSUE: POSOrderCreateRequest model validation failing")
        
        if not self.created_test_data['bookings'] or not self.created_test_data['folios']:
            print("  ⚠️ No test booking/folio available, creating minimal test data...")
            booking_id = self.created_test_data['bookings'][0] if self.created_test_data['bookings'] else str(uuid.uuid4())
            folio_id = str(uuid.uuid4())  # Use dummy folio ID
        else:
            booking_id = self.created_test_data['bookings'][0]
            folio_id = self.created_test_data['folios'][0]
        
        test_cases = [
            {
                "name": "Create POS order with POSOrderCreateRequest model",
                "data": {
                    "booking_id": booking_id,
                    "folio_id": folio_id,
                    "order_items": [
                        {
                            "item_name": "Caesar Salad",
                            "quantity": 2,
                            "unit_price": 15.0
                        },
                        {
                            "item_name": "Grilled Salmon",
                            "quantity": 1,
                            "unit_price": 28.0
                        }
                    ]
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Create POS order with alternative field names",
                "data": {
                    "booking": booking_id,
                    "folio": folio_id,
                    "items": [
                        {
                            "name": "Coffee",
                            "qty": 2,
                            "price": 5.0
                        }
                    ]
                },
                "expected_status": [200, 422]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/pos/create-order"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - POS order created successfully")
                            passed += 1
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/pos/create-order",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_rms_price_recommendation_slider_422_investigation(self):
        """Test GET /api/rms/price-recommendation-slider - 422 ERROR INVESTIGATION"""
        print("\n📊 Testing RMS Price Recommendation Slider Endpoint (422 ERROR INVESTIGATION)...")
        print("🔧 ISSUE: Query parameter validation failing")
        
        test_cases = [
            {
                "name": "Get price recommendation with required parameters",
                "params": {
                    "room_type": "Standard",
                    "check_in_date": "2025-12-01"
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Get price recommendation with alternative parameter names",
                "params": {
                    "roomType": "Deluxe",
                    "date": "2025-12-15"
                },
                "expected_status": [200, 422]
            },
            {
                "name": "Get price recommendation with minimal parameters",
                "params": {
                    "room_type": "Suite"
                },
                "expected_status": [200, 422]
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
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - Price recommendation retrieved")
                            passed += 1
                        else:  # 422
                            print(f"  ❌ {test_case['name']}: Still has validation issues (422)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/rms/price-recommendation-slider",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= 500 ERROR TO DEBUG =============

    async def test_guest_profile_complete_500_debug(self):
        """Test GET /api/guests/{guest_id}/profile-complete - 500 ERROR DEBUG"""
        print("\n👤 Testing Guest Profile Complete Endpoint (500 ERROR DEBUG)...")
        print("🔧 ISSUE: Returns 500 internal server error")
        
        if not self.created_test_data['guests']:
            print("  ⚠️ No test guest available, skipping test")
            return
        
        guest_id = self.created_test_data['guests'][0]
        
        test_cases = [
            {
                "name": "Get complete profile for existing guest",
                "guest_id": guest_id,
                "expected_status": [200, 500]
            },
            {
                "name": "Get complete profile for non-existent guest",
                "guest_id": "non-existent-guest-id",
                "expected_status": [404, 500]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/guests/{test_case['guest_id']}/profile-complete"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            print(f"  ✅ {test_case['name']}: PASSED - Profile retrieved successfully")
                            passed += 1
                        elif response.status == 404:
                            print(f"  ✅ {test_case['name']}: PASSED - 404 for non-existent guest")
                            passed += 1
                        else:  # 500
                            print(f"  ❌ {test_case['name']}: Still has server error (500)")
                            print(f"      Response: {response_text[:300]}...")
                    else:
                        print(f"  ❌ {test_case['name']}: Unexpected status {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/guests/{guest_id}/profile-complete",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= FIELD MISMATCH TO VERIFY =============

    async def test_approvals_pending_field_mismatch(self):
        """Test GET /api/approvals/pending - Should return urgent_count field"""
        print("\n📋 Testing Approvals Pending Endpoint (FIELD MISMATCH VERIFICATION)...")
        print("🔧 EXPECTED: Should return urgent_count field")
        
        test_cases = [
            {
                "name": "Get pending approvals - verify urgent_count field",
                "params": {},
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
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status == 200:
                        try:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                print(f"  ✅ {test_case['name']}: PASSED - urgent_count field present")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                                print(f"      Available fields: {list(data.keys())}")
                        except:
                            print(f"  ❌ {test_case['name']}: Invalid JSON response")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/approvals/pending",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_approvals_my_requests_field_mismatch(self):
        """Test GET /api/approvals/my-requests - Should return 'requests' field (not 'approvals')"""
        print("\n📋 Testing Approvals My Requests Endpoint (FIELD MISMATCH VERIFICATION)...")
        print("🔧 EXPECTED: Should return 'requests' field (not 'approvals')")
        
        test_cases = [
            {
                "name": "Get my requests - verify 'requests' field name",
                "params": {},
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
                    response_text = await response.text()
                    print(f"  📝 {test_case['name']}: HTTP {response.status}")
                    
                    if response.status == 200:
                        try:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                print(f"  ✅ {test_case['name']}: PASSED - 'requests' field present")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                                print(f"      Available fields: {list(data.keys())}")
                                # Check if it's using 'approvals' instead of 'requests'
                                if 'approvals' in data:
                                    print(f"      ⚠️ Using 'approvals' field instead of 'requests'")
                        except:
                            print(f"  ❌ {test_case['name']}: Invalid JSON response")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        print(f"      Response: {response_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/approvals/my-requests",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MAIN TEST EXECUTION =============

    async def run_all_tests(self):
        """Run comprehensive testing of previously failed endpoints"""
        print("🚀 BACKEND API RE-TESTING - Previously Failed Endpoints")
        print("Testing 12 ENDPOINTS (2 Fixed + 7 422 Errors + 1 500 Error + 2 Field Mismatches)")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # Phase 1: Fixed Endpoints (2 endpoints)
        print("\n" + "="*60)
        print("✅ PHASE 1: FIXED ENDPOINTS TO VERIFY (2 endpoints)")
        print("="*60)
        await self.test_send_system_alert_fixed()
        await self.test_update_notification_preferences_fixed()
        
        # Phase 2: 422 Error Investigation (7 endpoints)
        print("\n" + "="*60)
        print("🔍 PHASE 2: 422 ERROR INVESTIGATION (7 endpoints)")
        print("="*60)
        await self.test_extra_charges_422_investigation()
        await self.test_multi_room_reservation_422_investigation()
        await self.test_guest_preferences_422_investigation()
        await self.test_guest_tags_422_investigation()
        await self.test_messaging_send_message_422_investigation()
        await self.test_pos_create_order_422_investigation()
        await self.test_rms_price_recommendation_slider_422_investigation()
        
        # Phase 3: 500 Error Debug (1 endpoint)
        print("\n" + "="*60)
        print("🐛 PHASE 3: 500 ERROR DEBUG (1 endpoint)")
        print("="*60)
        await self.test_guest_profile_complete_500_debug()
        
        # Phase 4: Field Mismatch Verification (2 endpoints)
        print("\n" + "="*60)
        print("🔧 PHASE 4: FIELD MISMATCH VERIFICATION (2 endpoints)")
        print("="*60)
        await self.test_approvals_pending_field_mismatch()
        await self.test_approvals_my_requests_field_mismatch()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 BACKEND API RE-TESTING RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        # Group results by category
        categories = {
            "Fixed Endpoints": [],
            "422 Error Investigation": [],
            "500 Error Debug": [],
            "Field Mismatch Verification": []
        }
        
        for result in self.test_results:
            endpoint = result["endpoint"]
            if "notifications" in endpoint and ("send-system-alert" in endpoint or "preferences" in endpoint):
                categories["Fixed Endpoints"].append(result)
            elif any(x in endpoint for x in ["extra-charges", "multi-room", "preferences", "tags", "messaging", "pos", "rms"]):
                categories["422 Error Investigation"].append(result)
            elif "profile-complete" in endpoint:
                categories["500 Error Debug"].append(result)
            elif "approvals" in endpoint:
                categories["Field Mismatch Verification"].append(result)
        
        print("\n📋 RESULTS BY CATEGORY:")
        print("-" * 60)
        
        critical_issues = []
        
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
                    
                    # Track critical issues
                    if result["passed"] == 0:
                        critical_issues.append(result["endpoint"])
                
                total_passed += category_passed
                total_tests += category_total
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: Most endpoints working correctly!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most endpoints working, minor issues remain")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some endpoints working, significant issues remain")
        else:
            print("❌ CRITICAL: Major issues persist across multiple endpoints")
        
        if critical_issues:
            print(f"\n🚨 CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:")
            for issue in critical_issues:
                print(f"   • {issue}")
        
        print("\n🔍 INVESTIGATION SUMMARY:")
        print("• Fixed Endpoints: Verify SystemAlertRequest model and updated_preference field")
        print("• 422 Errors: Model validation issues - check Pydantic model definitions")
        print("• 500 Error: Server-side runtime error in guest profile endpoint")
        print("• Field Mismatches: Response structure inconsistencies")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = BackendAPIRetester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())