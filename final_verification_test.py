#!/usr/bin/env python3
"""
FINAL VERIFICATION - Complete System Test

**FIXES COMPLETED:**
1. ✅ RateType enum - Added 'standard' value
2. ✅ /tasks/delayed endpoint - Fixed routing conflict (moved before /tasks/{task_id})
3. ✅ test@test.com user created with 25,236+ demo data

**CRITICAL TEST POINTS:**

1. **Login Test:**
   - Email: test@test.com
   - Password: test123
   - Expected: Successful authentication

2. **Data Verification:**
   - /api/pms/rooms - Should return 85 rooms
   - /api/pms/guests - Should return 500 guests
   - /api/pms/bookings?limit=100 - Should return 100 bookings (no 500 error)
   - /api/companies - Should return 50 companies

3. **GM Dashboard APIs (9 endpoints):**
   - /api/reports/daily-flash
   - /api/pms/dashboard
   - /api/folio/dashboard-stats
   - /api/reports/finance-snapshot
   - /api/reports/cost-summary
   - /api/finance/expense-summary?period=today
   - /api/analytics/7day-trend
   - /api/settings/sla
   - /api/tasks/delayed (CRITICAL - just fixed!)

4. **Previously Fixed Endpoints:**
   - /api/housekeeping/mobile/room-assignments
   - /api/pms/companies
   - /api/contracted-rates

**SUCCESS CRITERIA:**
- 100% of endpoints working
- No 500 Internal Server Errors
- No 404 Not Found errors
- All demo data accessible

Please run comprehensive test and confirm 100% success rate.
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
BACKEND_URL = "https://auth-endpoint-suite.preview.emergentagent.com/api"
TEST_EMAIL = "test@test.com"
TEST_PASSWORD = "test123"

class FinalVerificationTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.critical_failures = []

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate with test@test.com credentials"""
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
                    self.critical_failures.append(f"Login failed with test@test.com: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            self.critical_failures.append(f"Login error: {e}")
            return False

    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    async def test_data_verification(self):
        """Test data verification endpoints"""
        print("\n📊 Testing Data Verification Endpoints...")
        
        data_tests = [
            {
                "name": "PMS Rooms Count",
                "url": f"{BACKEND_URL}/pms/rooms",
                "expected_count": 85,
                "count_field": "rooms"
            },
            {
                "name": "PMS Guests Count", 
                "url": f"{BACKEND_URL}/pms/guests",
                "expected_count": 500,
                "count_field": "guests"
            },
            {
                "name": "PMS Bookings (limit=100)",
                "url": f"{BACKEND_URL}/pms/bookings?limit=100",
                "expected_count": 100,
                "count_field": "bookings"
            },
            {
                "name": "Companies Count",
                "url": f"{BACKEND_URL}/companies",
                "expected_count": 50,
                "count_field": "companies"
            }
        ]
        
        passed = 0
        total = len(data_tests)
        
        for test in data_tests:
            try:
                async with self.session.get(test["url"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check if it's an array or object with count
                        if isinstance(data, list):
                            actual_count = len(data)
                        elif isinstance(data, dict):
                            # Try different possible count fields
                            actual_count = len(data.get(test["count_field"], []))
                            if actual_count == 0 and "count" in data:
                                actual_count = data["count"]
                        else:
                            actual_count = 0
                        
                        if actual_count >= test["expected_count"]:
                            print(f"  ✅ {test['name']}: {actual_count} items (expected ≥{test['expected_count']})")
                            passed += 1
                        else:
                            print(f"  ❌ {test['name']}: {actual_count} items (expected ≥{test['expected_count']})")
                            self.critical_failures.append(f"{test['name']}: Only {actual_count} items, expected ≥{test['expected_count']}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test['name']}: HTTP {response.status} - {error_text[:100]}")
                        self.critical_failures.append(f"{test['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test['name']}: Error {e}")
                self.critical_failures.append(f"{test['name']}: {e}")
        
        self.test_results.append({
            "category": "Data Verification",
            "passed": passed, 
            "total": total, 
            "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_gm_dashboard_apis(self):
        """Test GM Dashboard APIs (9 endpoints)"""
        print("\n📈 Testing GM Dashboard APIs (9 endpoints)...")
        
        gm_dashboard_tests = [
            {
                "name": "Daily Flash Report",
                "url": f"{BACKEND_URL}/reports/daily-flash"
            },
            {
                "name": "PMS Dashboard",
                "url": f"{BACKEND_URL}/pms/dashboard"
            },
            {
                "name": "Folio Dashboard Stats",
                "url": f"{BACKEND_URL}/folio/dashboard-stats"
            },
            {
                "name": "Finance Snapshot",
                "url": f"{BACKEND_URL}/reports/finance-snapshot"
            },
            {
                "name": "Cost Summary",
                "url": f"{BACKEND_URL}/reports/cost-summary"
            },
            {
                "name": "Expense Summary (Today)",
                "url": f"{BACKEND_URL}/finance/expense-summary?period=today"
            },
            {
                "name": "7-Day Analytics Trend",
                "url": f"{BACKEND_URL}/analytics/7day-trend"
            },
            {
                "name": "SLA Settings",
                "url": f"{BACKEND_URL}/settings/sla"
            },
            {
                "name": "Delayed Tasks (CRITICAL FIX)",
                "url": f"{BACKEND_URL}/tasks/delayed"
            }
        ]
        
        passed = 0
        total = len(gm_dashboard_tests)
        
        for test in gm_dashboard_tests:
            try:
                async with self.session.get(test["url"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"  ✅ {test['name']}: HTTP 200 - Data received")
                        passed += 1
                    elif response.status == 404:
                        print(f"  ❌ {test['name']}: HTTP 404 - Endpoint not found")
                        self.critical_failures.append(f"{test['name']}: 404 Not Found")
                    elif response.status == 500:
                        error_text = await response.text()
                        print(f"  ❌ {test['name']}: HTTP 500 - Internal Server Error")
                        print(f"      Error details: {error_text[:200]}...")
                        self.critical_failures.append(f"{test['name']}: 500 Internal Server Error")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test['name']}: HTTP {response.status} - {error_text[:100]}")
                        self.critical_failures.append(f"{test['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test['name']}: Error {e}")
                self.critical_failures.append(f"{test['name']}: {e}")
        
        self.test_results.append({
            "category": "GM Dashboard APIs",
            "passed": passed, 
            "total": total, 
            "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_previously_fixed_endpoints(self):
        """Test Previously Fixed Endpoints"""
        print("\n🔧 Testing Previously Fixed Endpoints...")
        
        fixed_endpoints_tests = [
            {
                "name": "Housekeeping Mobile Room Assignments",
                "url": f"{BACKEND_URL}/housekeeping/mobile/room-assignments"
            },
            {
                "name": "PMS Companies",
                "url": f"{BACKEND_URL}/pms/companies"
            },
            {
                "name": "Contracted Rates",
                "url": f"{BACKEND_URL}/contracted-rates"
            }
        ]
        
        passed = 0
        total = len(fixed_endpoints_tests)
        
        for test in fixed_endpoints_tests:
            try:
                async with self.session.get(test["url"], headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"  ✅ {test['name']}: HTTP 200 - Working correctly")
                        passed += 1
                    elif response.status == 404:
                        print(f"  ❌ {test['name']}: HTTP 404 - Endpoint not found")
                        self.critical_failures.append(f"{test['name']}: 404 Not Found")
                    elif response.status == 500:
                        error_text = await response.text()
                        print(f"  ❌ {test['name']}: HTTP 500 - Internal Server Error")
                        print(f"      Error details: {error_text[:200]}...")
                        self.critical_failures.append(f"{test['name']}: 500 Internal Server Error")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test['name']}: HTTP {response.status} - {error_text[:100]}")
                        self.critical_failures.append(f"{test['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test['name']}: Error {e}")
                self.critical_failures.append(f"{test['name']}: {e}")
        
        self.test_results.append({
            "category": "Previously Fixed Endpoints",
            "passed": passed, 
            "total": total, 
            "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_rate_type_enum_fix(self):
        """Test RateType enum fix - verify 'standard' value exists"""
        print("\n🔧 Testing RateType Enum Fix...")
        
        # Test by creating a booking with 'standard' rate type
        try:
            # First get a guest and room
            async with self.session.get(f"{BACKEND_URL}/pms/guests", headers=self.get_headers()) as response:
                if response.status == 200:
                    guests = await response.json()
                    if isinstance(guests, list) and guests:
                        guest_id = guests[0]["id"]
                    elif isinstance(guests, dict) and guests.get("guests"):
                        guest_id = guests["guests"][0]["id"]
                    else:
                        print("  ❌ RateType Enum Test: No guests available")
                        self.critical_failures.append("RateType Enum Test: No guests available")
                        return
                else:
                    print("  ❌ RateType Enum Test: Cannot get guests")
                    self.critical_failures.append("RateType Enum Test: Cannot get guests")
                    return

            async with self.session.get(f"{BACKEND_URL}/pms/rooms", headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    if isinstance(rooms, list) and rooms:
                        room_id = rooms[0]["id"]
                    elif isinstance(rooms, dict) and rooms.get("rooms"):
                        room_id = rooms["rooms"][0]["id"]
                    else:
                        print("  ❌ RateType Enum Test: No rooms available")
                        self.critical_failures.append("RateType Enum Test: No rooms available")
                        return
                else:
                    print("  ❌ RateType Enum Test: Cannot get rooms")
                    self.critical_failures.append("RateType Enum Test: Cannot get rooms")
                    return

            # Try to create a booking with 'standard' rate type
            booking_data = {
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "check_out": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "adults": 2,
                "children": 0,
                "guests_count": 2,
                "total_amount": 200.0,
                "rate_type": "standard"  # Testing the fix
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/bookings", 
                                       json=booking_data, 
                                       headers=self.get_headers()) as response:
                if response.status == 200:
                    print("  ✅ RateType Enum Fix: 'standard' value accepted successfully")
                    self.test_results.append({
                        "category": "RateType Enum Fix",
                        "passed": 1, 
                        "total": 1, 
                        "success_rate": "100.0%"
                    })
                else:
                    error_text = await response.text()
                    print(f"  ❌ RateType Enum Fix: HTTP {response.status} - {error_text[:200]}")
                    self.critical_failures.append(f"RateType Enum Fix: HTTP {response.status}")
                    self.test_results.append({
                        "category": "RateType Enum Fix",
                        "passed": 0, 
                        "total": 1, 
                        "success_rate": "0.0%"
                    })
                    
        except Exception as e:
            print(f"  ❌ RateType Enum Fix: Error {e}")
            self.critical_failures.append(f"RateType Enum Fix: {e}")
            self.test_results.append({
                "category": "RateType Enum Fix",
                "passed": 0, 
                "total": 1, 
                "success_rate": "0.0%"
            })

    async def run_final_verification(self):
        """Run complete final verification test"""
        print("🚀 FINAL VERIFICATION - Complete System Test")
        print("Testing critical fixes and 100% system functionality")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        # Critical Test 1: Login with test@test.com
        print("\n🔐 CRITICAL TEST 1: Login Authentication")
        if not await self.authenticate():
            print("❌ CRITICAL FAILURE: Cannot authenticate with test@test.com")
            await self.cleanup_session()
            return
        
        # Critical Test 2: Data Verification
        print("\n📊 CRITICAL TEST 2: Data Verification")
        await self.test_data_verification()
        
        # Critical Test 3: GM Dashboard APIs
        print("\n📈 CRITICAL TEST 3: GM Dashboard APIs")
        await self.test_gm_dashboard_apis()
        
        # Critical Test 4: Previously Fixed Endpoints
        print("\n🔧 CRITICAL TEST 4: Previously Fixed Endpoints")
        await self.test_previously_fixed_endpoints()
        
        # Critical Test 5: RateType Enum Fix
        print("\n🔧 CRITICAL TEST 5: RateType Enum Fix")
        await self.test_rate_type_enum_fix()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print final results
        self.print_final_results()

    def print_final_results(self):
        """Print comprehensive final verification results"""
        print("\n" + "=" * 80)
        print("📊 FINAL VERIFICATION RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        print("\n📋 RESULTS BY CATEGORY:")
        print("-" * 60)
        
        for result in self.test_results:
            category_rate = float(result["success_rate"].replace("%", ""))
            status = "✅" if category_rate == 100 else "⚠️" if category_rate >= 50 else "❌"
            print(f"{status} {result['category']}: {result['passed']}/{result['total']} ({result['success_rate']})")
            
            total_passed += result["passed"]
            total_tests += result["total"]
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        # Final verdict
        if overall_success_rate == 100 and not self.critical_failures:
            print("\n🎉 SUCCESS: 100% SYSTEM VERIFICATION COMPLETE!")
            print("✅ All fixes working correctly")
            print("✅ All endpoints responding properly")
            print("✅ All demo data accessible")
            print("✅ No critical failures detected")
        elif overall_success_rate >= 90:
            print("\n✅ MOSTLY SUCCESSFUL: System mostly working with minor issues")
        elif overall_success_rate >= 75:
            print("\n⚠️ PARTIAL SUCCESS: Some issues remain")
        else:
            print("\n❌ CRITICAL ISSUES: Major problems detected")
        
        # Print critical failures if any
        if self.critical_failures:
            print("\n🚨 CRITICAL FAILURES DETECTED:")
            print("-" * 40)
            for i, failure in enumerate(self.critical_failures, 1):
                print(f"{i}. {failure}")
        
        print("\n🔍 FIXES VERIFIED:")
        print("• Login with test@test.com credentials")
        print("• RateType enum 'standard' value")
        print("• /tasks/delayed endpoint routing")
        print("• Demo data counts (85 rooms, 500 guests, etc.)")
        print("• GM Dashboard APIs (9 endpoints)")
        print("• Previously fixed endpoints")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = FinalVerificationTester()
    await tester.run_final_verification()

if __name__ == "__main__":
    asyncio.run(main())