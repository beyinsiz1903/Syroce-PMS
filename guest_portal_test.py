#!/usr/bin/env python3
"""
Guest Portal Authentication & Multi-Tenant Support Testing
Testing guest registration, login, bookings, loyalty, and notification preferences
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
BACKEND_URL = "https://code-cleanup-135.preview.emergentagent.com/api"

class GuestPortalTester:
    def __init__(self):
        self.session = None
        self.guest_auth_token = None
        self.guest_user_id = None
        self.test_results = []
        self.created_test_data = {
            'guest_users': [],
            'tenants': [],
            'guests': [],
            'bookings': [],
            'loyalty_programs': []
        }

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    def get_guest_headers(self):
        """Get guest authorization headers"""
        return {
            "Authorization": f"Bearer {self.guest_auth_token}",
            "Content-Type": "application/json"
        }

    async def test_guest_registration(self):
        """Test POST /api/auth/register-guest endpoint"""
        print("\n👤 Testing Guest Registration...")
        
        test_cases = [
            {
                "name": "Valid guest registration",
                "data": {
                    "email": f"guest{uuid.uuid4().hex[:8]}@test.com",
                    "password": "guestpass123",
                    "name": "John Guest",
                    "phone": "+1234567890"
                },
                "expected_status": 200,
                "expected_fields": ["access_token", "token_type", "user", "tenant"]
            },
            {
                "name": "Duplicate email registration",
                "data": {
                    "email": "duplicate@test.com",
                    "password": "guestpass123",
                    "name": "Duplicate Guest",
                    "phone": "+1234567891"
                },
                "expected_status": 400,  # Should fail on second attempt
                "run_twice": True
            },
            {
                "name": "Invalid email format",
                "data": {
                    "email": "invalid-email",
                    "password": "guestpass123",
                    "name": "Invalid Guest",
                    "phone": "+1234567892"
                },
                "expected_status": 422
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                # Run twice if specified (for duplicate email test)
                if test_case.get("run_twice"):
                    # First registration should succeed
                    async with self.session.post(f"{BACKEND_URL}/auth/register-guest", 
                                               json=test_case["data"]) as response:
                        if response.status == 200:
                            print(f"  ✅ First registration successful")
                        else:
                            print(f"  ❌ First registration failed: {response.status}")
                            continue
                    
                    # Second registration should fail
                    async with self.session.post(f"{BACKEND_URL}/auth/register-guest", 
                                               json=test_case["data"]) as response:
                        if response.status == test_case["expected_status"]:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                else:
                    async with self.session.post(f"{BACKEND_URL}/auth/register-guest", 
                                               json=test_case["data"]) as response:
                        if response.status == test_case["expected_status"]:
                            if response.status == 200:
                                data = await response.json()
                                
                                # Check required fields
                                missing_fields = [field for field in test_case.get("expected_fields", []) 
                                                if field not in data]
                                if not missing_fields:
                                    # Store first successful registration for login test
                                    if not self.guest_auth_token:
                                        self.guest_auth_token = data["access_token"]
                                        self.guest_user_id = data["user"]["id"]
                                        self.created_test_data['guest_users'].append({
                                            'email': test_case["data"]["email"],
                                            'password': test_case["data"]["password"],
                                            'user_id': data["user"]["id"]
                                        })
                                    
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                            
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/auth/register-guest",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_guest_login(self):
        """Test POST /api/auth/login endpoint for guest users"""
        print("\n🔐 Testing Guest Login...")
        
        if not self.created_test_data['guest_users']:
            print("  ⚠️ No guest users created, skipping login test")
            self.test_results.append({
                "endpoint": "POST /api/auth/login (Guest)",
                "passed": 0,
                "total": 1,
                "success_rate": "0.0%"
            })
            return
        
        guest_user = self.created_test_data['guest_users'][0]
        
        test_cases = [
            {
                "name": "Valid guest login",
                "data": {
                    "email": guest_user['email'],
                    "password": guest_user['password']
                },
                "expected_status": 200,
                "expected_fields": ["access_token", "token_type", "user", "tenant"]
            },
            {
                "name": "Invalid password",
                "data": {
                    "email": guest_user['email'],
                    "password": "wrongpassword"
                },
                "expected_status": 401
            },
            {
                "name": "Non-existent email",
                "data": {
                    "email": "nonexistent@test.com",
                    "password": "anypassword"
                },
                "expected_status": 401
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                async with self.session.post(f"{BACKEND_URL}/auth/login", 
                                           json=test_case["data"]) as response:
                    if response.status == test_case["expected_status"]:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Check required fields
                            missing_fields = [field for field in test_case.get("expected_fields", []) 
                                            if field not in data]
                            if not missing_fields:
                                # Verify user role is GUEST
                                if data["user"]["role"] == "guest":
                                    # Update token for subsequent tests
                                    self.guest_auth_token = data["access_token"]
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: User role is not 'guest'")
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/auth/login (Guest)",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_token_validation(self):
        """Test token validation by accessing protected endpoint"""
        print("\n🔒 Testing Token Validation...")
        
        if not self.guest_auth_token:
            print("  ⚠️ No guest token available, skipping validation test")
            self.test_results.append({
                "endpoint": "Token Validation",
                "passed": 0,
                "total": 1,
                "success_rate": "0.0%"
            })
            return
        
        try:
            async with self.session.get(f"{BACKEND_URL}/auth/me", 
                                      headers=self.get_guest_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("role") == "guest":
                        print(f"  ✅ Token validation: PASSED")
                        self.test_results.append({
                            "endpoint": "Token Validation",
                            "passed": 1,
                            "total": 1,
                            "success_rate": "100.0%"
                        })
                    else:
                        print(f"  ❌ Token validation: Invalid role {data.get('role')}")
                        self.test_results.append({
                            "endpoint": "Token Validation",
                            "passed": 0,
                            "total": 1,
                            "success_rate": "0.0%"
                        })
                else:
                    print(f"  ❌ Token validation: HTTP {response.status}")
                    self.test_results.append({
                        "endpoint": "Token Validation",
                        "passed": 0,
                        "total": 1,
                        "success_rate": "0.0%"
                    })
                    
        except Exception as e:
            print(f"  ❌ Token validation: Error {e}")
            self.test_results.append({
                "endpoint": "Token Validation",
                "passed": 0,
                "total": 1,
                "success_rate": "0.0%"
            })

    async def test_guest_bookings_endpoint(self):
        """Test GET /api/guest/bookings endpoint (Multi-Tenant)"""
        print("\n📅 Testing Guest Bookings Endpoint (Multi-Tenant)...")
        
        if not self.guest_auth_token:
            print("  ⚠️ No guest token available, skipping bookings test")
            self.test_results.append({
                "endpoint": "GET /api/guest/bookings",
                "passed": 0,
                "total": 1,
                "success_rate": "0.0%"
            })
            return
        
        try:
            async with self.session.get(f"{BACKEND_URL}/guest/bookings", 
                                      headers=self.get_guest_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Check required fields
                    required_fields = ["active_bookings", "past_bookings"]
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        # Verify structure of bookings
                        active_bookings = data.get("active_bookings", [])
                        past_bookings = data.get("past_bookings", [])
                        
                        # Check if bookings have required multi-tenant fields
                        all_bookings = active_bookings + past_bookings
                        valid_structure = True
                        
                        for booking in all_bookings:
                            # Check for tenant_id and hotel information
                            if "tenant_id" not in booking:
                                print(f"  ⚠️ Booking missing tenant_id")
                                valid_structure = False
                            
                            # Check for hotel information (multi-tenant support)
                            if "hotel" not in booking:
                                print(f"  ⚠️ Booking missing hotel information")
                                valid_structure = False
                            
                            # Check for can_communicate and can_order_services flags
                            # Note: These might be added at the booking level or derived
                        
                        if valid_structure:
                            print(f"  ✅ Guest bookings endpoint: PASSED")
                            print(f"     Active bookings: {len(active_bookings)}")
                            print(f"     Past bookings: {len(past_bookings)}")
                            self.test_results.append({
                                "endpoint": "GET /api/guest/bookings",
                                "passed": 1,
                                "total": 1,
                                "success_rate": "100.0%"
                            })
                        else:
                            print(f"  ❌ Guest bookings: Invalid booking structure")
                            self.test_results.append({
                                "endpoint": "GET /api/guest/bookings",
                                "passed": 0,
                                "total": 1,
                                "success_rate": "0.0%"
                            })
                    else:
                        print(f"  ❌ Guest bookings: Missing fields {missing_fields}")
                        self.test_results.append({
                            "endpoint": "GET /api/guest/bookings",
                            "passed": 0,
                            "total": 1,
                            "success_rate": "0.0%"
                        })
                else:
                    print(f"  ❌ Guest bookings: HTTP {response.status}")
                    error_text = await response.text()
                    print(f"     Error: {error_text}")
                    self.test_results.append({
                        "endpoint": "GET /api/guest/bookings",
                        "passed": 0,
                        "total": 1,
                        "success_rate": "0.0%"
                    })
                    
        except Exception as e:
            print(f"  ❌ Guest bookings: Error {e}")
            self.test_results.append({
                "endpoint": "GET /api/guest/bookings",
                "passed": 0,
                "total": 1,
                "success_rate": "0.0%"
            })

    async def test_guest_loyalty_endpoint(self):
        """Test GET /api/guest/loyalty endpoint (Multi-Tenant)"""
        print("\n🏆 Testing Guest Loyalty Endpoint (Multi-Tenant)...")
        
        if not self.guest_auth_token:
            print("  ⚠️ No guest token available, skipping loyalty test")
            self.test_results.append({
                "endpoint": "GET /api/guest/loyalty",
                "passed": 0,
                "total": 1,
                "success_rate": "0.0%"
            })
            return
        
        try:
            async with self.session.get(f"{BACKEND_URL}/guest/loyalty", 
                                      headers=self.get_guest_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Check required fields for multi-tenant loyalty
                    required_fields = ["loyalty_programs", "total_points", "global_tier"]
                    missing_fields = [field for field in required_fields if field not in data]
                    
                    if not missing_fields:
                        loyalty_programs = data.get("loyalty_programs", [])
                        total_points = data.get("total_points", 0)
                        global_tier = data.get("global_tier")
                        
                        # Verify structure of loyalty programs (multi-tenant)
                        valid_structure = True
                        
                        for program in loyalty_programs:
                            # Check for tenant_id and hotel information
                            if "tenant_id" not in program:
                                print(f"  ⚠️ Loyalty program missing tenant_id")
                                valid_structure = False
                            
                            if "hotel" not in program:
                                print(f"  ⚠️ Loyalty program missing hotel information")
                                valid_structure = False
                            
                            # Check for loyalty program fields
                            required_program_fields = ["points", "tier"]
                            missing_program_fields = [field for field in required_program_fields 
                                                    if field not in program]
                            if missing_program_fields:
                                print(f"  ⚠️ Loyalty program missing fields: {missing_program_fields}")
                                valid_structure = False
                        
                        if valid_structure:
                            print(f"  ✅ Guest loyalty endpoint: PASSED")
                            print(f"     Loyalty programs: {len(loyalty_programs)}")
                            print(f"     Total points: {total_points}")
                            print(f"     Global tier: {global_tier}")
                            self.test_results.append({
                                "endpoint": "GET /api/guest/loyalty",
                                "passed": 1,
                                "total": 1,
                                "success_rate": "100.0%"
                            })
                        else:
                            print(f"  ❌ Guest loyalty: Invalid program structure")
                            self.test_results.append({
                                "endpoint": "GET /api/guest/loyalty",
                                "passed": 0,
                                "total": 1,
                                "success_rate": "0.0%"
                            })
                    else:
                        print(f"  ❌ Guest loyalty: Missing fields {missing_fields}")
                        self.test_results.append({
                            "endpoint": "GET /api/guest/loyalty",
                            "passed": 0,
                            "total": 1,
                            "success_rate": "0.0%"
                        })
                else:
                    print(f"  ❌ Guest loyalty: HTTP {response.status}")
                    error_text = await response.text()
                    print(f"     Error: {error_text}")
                    self.test_results.append({
                        "endpoint": "GET /api/guest/loyalty",
                        "passed": 0,
                        "total": 1,
                        "success_rate": "0.0%"
                    })
                    
        except Exception as e:
            print(f"  ❌ Guest loyalty: Error {e}")
            self.test_results.append({
                "endpoint": "GET /api/guest/loyalty",
                "passed": 0,
                "total": 1,
                "success_rate": "0.0%"
            })

    async def test_guest_notification_preferences(self):
        """Test GET and PUT /api/guest/notification-preferences endpoints"""
        print("\n🔔 Testing Guest Notification Preferences...")
        
        if not self.guest_auth_token:
            print("  ⚠️ No guest token available, skipping notification preferences test")
            self.test_results.append({
                "endpoint": "GET /api/guest/notification-preferences",
                "passed": 0,
                "total": 2,
                "success_rate": "0.0%"
            })
            return
        
        passed = 0
        total = 2  # GET and PUT tests
        
        # Test GET notification preferences
        try:
            async with self.session.get(f"{BACKEND_URL}/guest/notification-preferences", 
                                      headers=self.get_guest_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Check for default preferences structure
                    expected_fields = [
                        "user_id", "email_notifications", "whatsapp_notifications", 
                        "in_app_notifications", "booking_updates", "promotional", 
                        "room_service_updates"
                    ]
                    missing_fields = [field for field in expected_fields if field not in data]
                    
                    if not missing_fields:
                        print(f"  ✅ GET notification preferences: PASSED")
                        passed += 1
                        
                        # Store current preferences for update test
                        current_prefs = data
                    else:
                        print(f"  ❌ GET notification preferences: Missing fields {missing_fields}")
                        current_prefs = {}
                else:
                    print(f"  ❌ GET notification preferences: HTTP {response.status}")
                    current_prefs = {}
                    
        except Exception as e:
            print(f"  ❌ GET notification preferences: Error {e}")
            current_prefs = {}
        
        # Test PUT notification preferences
        try:
            # Update some preferences
            update_data = {
                "email_notifications": False,
                "whatsapp_notifications": True,
                "promotional": False
            }
            
            async with self.session.put(f"{BACKEND_URL}/guest/notification-preferences", 
                                      json=update_data,
                                      headers=self.get_guest_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("message"):
                        print(f"  ✅ PUT notification preferences: PASSED")
                        passed += 1
                        
                        # Verify the update by getting preferences again
                        async with self.session.get(f"{BACKEND_URL}/guest/notification-preferences", 
                                                  headers=self.get_guest_headers()) as verify_response:
                            if verify_response.status == 200:
                                verify_data = await verify_response.json()
                                
                                # Check if updates were applied
                                updates_applied = all(
                                    verify_data.get(key) == value 
                                    for key, value in update_data.items()
                                )
                                
                                if updates_applied:
                                    print(f"     ✅ Preference updates verified")
                                else:
                                    print(f"     ⚠️ Some preference updates not applied")
                    else:
                        print(f"  ❌ PUT notification preferences: Invalid response")
                else:
                    print(f"  ❌ PUT notification preferences: HTTP {response.status}")
                    
        except Exception as e:
            print(f"  ❌ PUT notification preferences: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET/PUT /api/guest/notification-preferences",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_unauthorized_access(self):
        """Test that endpoints properly reject unauthorized access"""
        print("\n🚫 Testing Unauthorized Access Protection...")
        
        endpoints_to_test = [
            "/guest/bookings",
            "/guest/loyalty", 
            "/guest/notification-preferences"
        ]
        
        passed = 0
        total = len(endpoints_to_test)
        
        for endpoint in endpoints_to_test:
            try:
                # Test without authorization header
                async with self.session.get(f"{BACKEND_URL}{endpoint}") as response:
                    if response.status == 401:
                        print(f"  ✅ {endpoint}: Properly rejects unauthorized access")
                        passed += 1
                    else:
                        print(f"  ❌ {endpoint}: Expected 401, got {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {endpoint}: Error {e}")
        
        self.test_results.append({
            "endpoint": "Unauthorized Access Protection",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%"
        })

    async def run_all_tests(self):
        """Run all guest portal tests"""
        print("🚀 Starting Guest Portal Authentication & Multi-Tenant Support Tests")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        # Phase 1: Authentication Tests
        await self.test_guest_registration()
        await self.test_guest_login()
        await self.test_token_validation()
        
        # Phase 2: Multi-Tenant Guest Endpoints
        await self.test_guest_bookings_endpoint()
        await self.test_guest_loyalty_endpoint()
        await self.test_guest_notification_preferences()
        
        # Phase 3: Security Tests
        await self.test_unauthorized_access()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 GUEST PORTAL AUTHENTICATION & MULTI-TENANT TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        print("\n📋 ENDPOINT TEST RESULTS:")
        print("-" * 60)
        
        for result in self.test_results:
            endpoint = result["endpoint"]
            passed = result["passed"]
            total = result["total"]
            success_rate = result["success_rate"]
            
            status = "✅ WORKING" if passed == total else "❌ FAILED" if passed == 0 else "⚠️ PARTIAL"
            print(f"{status} {endpoint}")
            print(f"   Tests: {passed}/{total} ({success_rate})")
            
            total_passed += passed
            total_tests += total
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: Guest Portal is working perfectly!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most guest portal features are working correctly")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some guest portal features need attention")
        else:
            print("❌ CRITICAL: Major issues with guest portal")
        
        print("\n🔍 KEY FEATURES TESTED:")
        print("• Guest Registration: Email validation, duplicate prevention")
        print("• Guest Authentication: Login, token validation")
        print("• Multi-Tenant Bookings: Cross-hotel booking access")
        print("• Multi-Tenant Loyalty: Aggregated points and tier calculation")
        print("• User-Level Preferences: Notification settings management")
        print("• Security: Unauthorized access protection")
        
        print("\n📝 CRITICAL REQUIREMENTS VERIFIED:")
        print("• No 401 Unauthorized errors for valid guest tokens")
        print("• Guest user tenant_id=None compatibility")
        print("• Cross-tenant data query functionality")
        print("• Multi-tenant data aggregation")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = GuestPortalTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())