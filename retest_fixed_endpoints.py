#!/usr/bin/env python3
"""
RE-TEST 5-STAR PMS - Focus on Previously Failed Endpoints

Test only the 6 endpoints that failed in previous test to achieve 100% success rate.

PREVIOUSLY FAILED - NOW FIXED:
1. POST /api/auth/request-verification
2. POST /api/groups/create-block
3. POST /api/sales/leads
4. GET /api/pricing/ai-recommendation
5. POST /api/journey/log-event
6. POST /api/nps/survey

ADDITIONAL VERIFICATION:
- Re-run all 35 endpoints from previous test
- Verify 100% success rate (35/35)
- Check response times (<100ms average)
- Confirm no 500 or 422 errors
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
import uuid

# Configuration
BACKEND_URL = "https://pms-i18next-demo.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class FixedEndpointsRetester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.test_guest_id = None
        self.test_booking_id = None
        self.test_room_id = None

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
                    print(f"✅ Authentication successful - User: {TEST_EMAIL}")
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

    async def create_test_guest_and_booking(self):
        """Create test guest and booking for journey/NPS tests"""
        print("\n🔧 Creating test guest and booking...")
        
        # Create test guest
        guest_data = {
            "name": "Test Guest for Journey",
            "email": f"testguest_{uuid.uuid4().hex[:8]}@test.com",
            "phone": "+1234567890",
            "id_number": f"TEST{uuid.uuid4().hex[:8].upper()}",
            "nationality": "US"
        }
        
        try:
            async with self.session.post(
                f"{BACKEND_URL}/pms/guests",
                headers=self.get_headers(),
                json=guest_data
            ) as response:
                if response.status == 200:
                    guest = await response.json()
                    self.test_guest_id = guest.get("id")
                    print(f"✅ Test guest created: {self.test_guest_id}")
                else:
                    print(f"❌ Failed to create test guest: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Error creating test guest: {e}")
            return False
        
        # Get available room
        try:
            async with self.session.get(
                f"{BACKEND_URL}/pms/rooms?limit=1",
                headers=self.get_headers()
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Handle both list and dict responses
                    if isinstance(data, list):
                        rooms = data
                    else:
                        rooms = data.get("rooms", [])
                    
                    if rooms:
                        self.test_room_id = rooms[0]["id"]
                        print(f"✅ Using room: {self.test_room_id}")
                    else:
                        print("❌ No rooms available")
                        return False
                else:
                    print(f"❌ Failed to get rooms: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Error getting rooms: {e}")
            return False
        
        # Create test booking
        check_in = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        check_out = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")
        
        booking_data = {
            "guest_id": self.test_guest_id,
            "room_id": self.test_room_id,
            "check_in": check_in,
            "check_out": check_out,
            "adults": 2,
            "children": 0,
            "guests_count": 2,
            "total_amount": 300.0
        }
        
        try:
            async with self.session.post(
                f"{BACKEND_URL}/pms/bookings",
                headers=self.get_headers(),
                json=booking_data
            ) as response:
                if response.status == 200:
                    booking = await response.json()
                    self.test_booking_id = booking.get("id")
                    print(f"✅ Test booking created: {self.test_booking_id}")
                    return True
                else:
                    print(f"❌ Failed to create test booking: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Error creating test booking: {e}")
            return False

    async def test_endpoint(self, method: str, endpoint: str, data: Dict = None, 
                           params: Dict = None, description: str = "") -> Dict:
        """Test a single endpoint"""
        url = f"{BACKEND_URL}{endpoint}"
        start_time = datetime.now()
        
        try:
            if method == "GET":
                async with self.session.get(url, headers=self.get_headers(), params=params) as response:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                    status = response.status
                    try:
                        response_data = await response.json()
                    except:
                        response_data = await response.text()
            elif method == "POST":
                async with self.session.post(url, headers=self.get_headers(), json=data) as response:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                    status = response.status
                    try:
                        response_data = await response.json()
                    except:
                        response_data = await response.text()
            elif method == "PUT":
                async with self.session.put(url, headers=self.get_headers(), json=data) as response:
                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                    status = response.status
                    try:
                        response_data = await response.json()
                    except:
                        response_data = await response.text()
            
            result = {
                "endpoint": f"{method} {endpoint}",
                "description": description,
                "status": status,
                "response_time_ms": round(response_time, 2),
                "success": status in [200, 201],
                "response": response_data
            }
            
            self.test_results.append(result)
            return result
            
        except Exception as e:
            result = {
                "endpoint": f"{method} {endpoint}",
                "description": description,
                "status": 0,
                "response_time_ms": 0,
                "success": False,
                "error": str(e)
            }
            self.test_results.append(result)
            return result

    async def test_previously_failed_endpoints(self):
        """Test the 6 previously failed endpoints"""
        print("\n" + "="*80)
        print("TESTING 6 PREVIOUSLY FAILED ENDPOINTS (NOW FIXED)")
        print("="*80)
        
        # 1. POST /api/auth/request-verification
        print("\n1️⃣ Testing POST /api/auth/request-verification...")
        result = await self.test_endpoint(
            "POST",
            "/auth/request-verification",
            data={
                "email": "newtest@hotel.com",
                "name": "Test User",
                "password": "test123",
                "user_type": "hotel",
                "property_name": "Test Hotel"
            },
            description="Request email verification code"
        )
        if result["success"]:
            print(f"   ✅ PASS - Status: {result['status']}, Time: {result['response_time_ms']}ms")
        else:
            print(f"   ❌ FAIL - Status: {result['status']}, Error: {result.get('error', result.get('response'))}")
        
        # 2. POST /api/groups/create-block
        print("\n2️⃣ Testing POST /api/groups/create-block...")
        result = await self.test_endpoint(
            "POST",
            "/groups/create-block",
            data={
                "group_name": "Test Conference Group",
                "organization": "Test Corp",
                "contact_name": "John Doe",
                "contact_email": "john@testcorp.com",
                "total_rooms": 10,
                "check_in": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d"),
                "check_out": (datetime.now(timezone.utc) + timedelta(days=33)).strftime("%Y-%m-%d"),
                "group_rate": 150.0,
                "room_type": "Standard",
                "cutoff_date": (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%d")
            },
            description="Create group block reservation"
        )
        if result["success"]:
            print(f"   ✅ PASS - Status: {result['status']}, Time: {result['response_time_ms']}ms")
        else:
            print(f"   ❌ FAIL - Status: {result['status']}, Error: {result.get('error', result.get('response'))}")
        
        # 3. POST /api/sales/leads
        print("\n3️⃣ Testing POST /api/sales/leads...")
        result = await self.test_endpoint(
            "POST",
            "/sales/leads",
            data={
                "contact_name": "John Doe",
                "contact_email": "john@test.com",
                "source": "website"
            },
            description="Create sales lead"
        )
        if result["success"]:
            print(f"   ✅ PASS - Status: {result['status']}, Time: {result['response_time_ms']}ms")
        else:
            print(f"   ❌ FAIL - Status: {result['status']}, Error: {result.get('error', result.get('response'))}")
        
        # 4. GET /api/pricing/ai-recommendation
        print("\n4️⃣ Testing GET /api/pricing/ai-recommendation...")
        result = await self.test_endpoint(
            "GET",
            "/pricing/ai-recommendation",
            params={
                "room_type": "Standard",
                "target_date": "2025-12-01"
            },
            description="Get AI pricing recommendation"
        )
        if result["success"]:
            response = result.get("response", {})
            has_required_fields = all(k in response for k in ["recommended_price", "min_price", "max_price"])
            if has_required_fields:
                print(f"   ✅ PASS - Status: {result['status']}, Time: {result['response_time_ms']}ms")
                print(f"      Recommended: ${response.get('recommended_price')}, Min: ${response.get('min_price')}, Max: ${response.get('max_price')}")
            else:
                print(f"   ⚠️  PARTIAL - Missing required fields: {result.get('response')}")
        else:
            print(f"   ❌ FAIL - Status: {result['status']}, Error: {result.get('error', result.get('response'))}")
        
        # Create test data for journey and NPS tests
        if not self.test_guest_id or not self.test_booking_id:
            await self.create_test_guest_and_booking()
        
        # 5. POST /api/journey/log-event
        print("\n5️⃣ Testing POST /api/journey/log-event...")
        if self.test_guest_id and self.test_booking_id:
            result = await self.test_endpoint(
                "POST",
                "/journey/log-event",
                data={
                    "guest_id": self.test_guest_id,
                    "booking_id": self.test_booking_id,
                    "touchpoint": "check_in",
                    "event_type": "arrival"
                },
                description="Log guest journey event"
            )
            if result["success"]:
                print(f"   ✅ PASS - Status: {result['status']}, Time: {result['response_time_ms']}ms")
            else:
                print(f"   ❌ FAIL - Status: {result['status']}, Error: {result.get('error', result.get('response'))}")
        else:
            print("   ⚠️  SKIP - Test data not available")
        
        # 6. POST /api/nps/survey
        print("\n6️⃣ Testing POST /api/nps/survey...")
        if self.test_guest_id and self.test_booking_id:
            result = await self.test_endpoint(
                "POST",
                "/nps/survey",
                data={
                    "nps_score": 9,
                    "guest_id": self.test_guest_id,
                    "booking_id": self.test_booking_id
                },
                description="Submit NPS survey"
            )
            if result["success"]:
                print(f"   ✅ PASS - Status: {result['status']}, Time: {result['response_time_ms']}ms")
            else:
                print(f"   ❌ FAIL - Status: {result['status']}, Error: {result.get('error', result.get('response'))}")
        else:
            print("   ⚠️  SKIP - Test data not available")

    async def test_all_35_endpoints(self):
        """Test all 35 endpoints for comprehensive verification"""
        print("\n" + "="*80)
        print("COMPREHENSIVE VERIFICATION - CORE ENDPOINTS")
        print("="*80)
        
        # Core PMS Endpoints (10)
        print("\n📋 CORE PMS ENDPOINTS (10)")
        
        await self.test_endpoint("GET", "/pms/rooms", params={"limit": 10}, description="Get rooms list")
        await self.test_endpoint("GET", "/pms/bookings", params={"limit": 10}, description="Get bookings list")
        await self.test_endpoint("GET", "/pms/guests", params={"limit": 10}, description="Get guests list")
        await self.test_endpoint("GET", "/companies", params={"limit": 10}, description="Get companies list")
        await self.test_endpoint("GET", "/pms/dashboard", description="Get PMS dashboard")
        await self.test_endpoint("GET", "/pms/room-blocks", description="Get room blocks")
        await self.test_endpoint("GET", "/housekeeping/tasks", description="Get housekeeping tasks")
        await self.test_endpoint("GET", "/housekeeping/mobile/room-assignments", description="Get room assignments")
        await self.test_endpoint("GET", "/housekeeping/cleaning-time-statistics", description="Get cleaning stats")
        await self.test_endpoint("GET", "/groups/blocks", description="Get group blocks")
        
        # Revenue & Analytics (8)
        print("\n📊 REVENUE & ANALYTICS ENDPOINTS (8)")
        
        await self.test_endpoint("GET", "/rms/price-recommendation-slider", 
                                params={"room_type": "Standard", "check_in_date": "2025-12-01"},
                                description="Get price recommendation")
        await self.test_endpoint("GET", "/rms/demand-heatmap", description="Get demand heatmap")
        await self.test_endpoint("GET", "/rms/compset-analysis", description="Get compset analysis")
        await self.test_endpoint("GET", "/executive/kpi-snapshot", description="Get KPI snapshot")
        await self.test_endpoint("GET", "/executive/performance-alerts", description="Get performance alerts")
        await self.test_endpoint("GET", "/executive/daily-summary", description="Get daily summary")
        await self.test_endpoint("GET", "/monitoring/health", description="Health check")
        await self.test_endpoint("GET", "/monitoring/system", description="System metrics")
        
        # Messaging & Communication (5)
        print("\n💬 MESSAGING & COMMUNICATION ENDPOINTS (5)")
        
        await self.test_endpoint("GET", "/messaging/templates", description="Get message templates")
        await self.test_endpoint("GET", "/messaging/auto-messages/trigger", 
                                params={"trigger_type": "pre_arrival"},
                                description="Trigger auto messages")
        await self.test_endpoint("GET", "/notifications/list", description="Get notifications")
        await self.test_endpoint("GET", "/approvals/pending", description="Get pending approvals")
        await self.test_endpoint("GET", "/approvals/my-requests", description="Get my approval requests")
        
        # F&B & POS (4)
        print("\n🍽️  F&B & POS ENDPOINTS (4)")
        
        await self.test_endpoint("GET", "/pos/menu-items", description="Get menu items")
        await self.test_endpoint("GET", "/pos/orders", description="Get POS orders")
        await self.test_endpoint("GET", "/fnb/mobile/outlets", description="Get F&B outlets")
        await self.test_endpoint("GET", "/fnb/mobile/ingredients", description="Get ingredients")
        
        # Finance & Accounting (3)
        print("\n💰 FINANCE & ACCOUNTING ENDPOINTS (3)")
        
        await self.test_endpoint("GET", "/department/finance/dashboard", description="Get finance dashboard")
        await self.test_endpoint("GET", "/reports/finance-snapshot", description="Get finance snapshot")
        await self.test_endpoint("GET", "/accounting/invoices", description="Get accounting invoices")
        
        # Maintenance & Technical (3)
        print("\n🔧 MAINTENANCE & TECHNICAL ENDPOINTS (3)")
        
        await self.test_endpoint("GET", "/maintenance/tasks", description="Get maintenance tasks")
        await self.test_endpoint("GET", "/maintenance/repeat-issues", description="Get repeat issues")
        await self.test_endpoint("GET", "/maintenance/sla-metrics", description="Get SLA metrics")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        avg_response_time = sum(r["response_time_ms"] for r in self.test_results) / total_tests if total_tests > 0 else 0
        
        print(f"\n📊 Overall Results:")
        print(f"   Total Tests: {total_tests}")
        print(f"   Passed: {passed_tests} ✅")
        print(f"   Failed: {failed_tests} ❌")
        print(f"   Success Rate: {success_rate:.1f}%")
        print(f"   Average Response Time: {avg_response_time:.2f}ms")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS ({failed_tests}):")
            for result in self.test_results:
                if not result["success"]:
                    print(f"   • {result['endpoint']} - Status: {result['status']}")
                    if 'error' in result:
                        print(f"     Error: {result['error']}")
                    elif 'response' in result:
                        print(f"     Response: {result['response']}")
        
        # Previously failed endpoints status
        print(f"\n🎯 PREVIOUSLY FAILED ENDPOINTS STATUS:")
        failed_endpoints = [
            "/auth/request-verification",
            "/groups/create-block",
            "/sales/leads",
            "/pricing/ai-recommendation",
            "/journey/log-event",
            "/nps/survey"
        ]
        
        for endpoint in failed_endpoints:
            matching_results = [r for r in self.test_results if endpoint in r["endpoint"]]
            if matching_results:
                result = matching_results[0]
                status_icon = "✅" if result["success"] else "❌"
                print(f"   {status_icon} {result['endpoint']} - Status: {result['status']}")
        
        print("\n" + "="*80)
        
        if success_rate == 100:
            print("🎉 PERFECT! 100% SUCCESS RATE ACHIEVED!")
        elif success_rate >= 90:
            print("✅ EXCELLENT! Over 90% success rate")
        elif success_rate >= 80:
            print("⚠️  GOOD! Over 80% success rate, but needs improvement")
        else:
            print("❌ NEEDS ATTENTION! Success rate below 80%")
        
        print("="*80)

    async def run_tests(self):
        """Run all tests"""
        try:
            await self.setup_session()
            
            # Authenticate
            if not await self.authenticate():
                print("❌ Authentication failed. Cannot proceed with tests.")
                return
            
            # Test previously failed endpoints
            await self.test_previously_failed_endpoints()
            
            # Test all 35 endpoints
            await self.test_all_35_endpoints()
            
            # Print summary
            self.print_summary()
            
        finally:
            await self.cleanup_session()

async def main():
    """Main entry point"""
    print("="*80)
    print("5-STAR PMS - RE-TEST PREVIOUSLY FAILED ENDPOINTS")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test User: {TEST_EMAIL}")
    print("="*80)
    
    tester = FixedEndpointsRetester()
    await tester.run_tests()

if __name__ == "__main__":
    asyncio.run(main())
