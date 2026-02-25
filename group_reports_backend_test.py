#!/usr/bin/env python3
"""
GROUP-BASED BACKEND REPORTS TESTING
Testing specific group booking and analytics endpoints as requested in Turkish

ENDPOINTS TO TEST:
1. /api/deluxe/group-bookings - Test with date range (today -30 to today +30), verify response structure
2. /api/deluxe/pickup-pace-analytics - Test with target_date, verify chart_data structure  
3. /api/revenue/pickup-report - Verify existing endpoint still works
4. Test min_rooms parameter variations (2,5,10) for different results

EXPECTED RESPONSE STRUCTURES:
- group-bookings: groups array with company_id, company_name, room_count, total_revenue, booking_ids
- pickup-pace-analytics: chart_data with days_before, daily_pickup, cumulative_revenue
- pickup-report: JSON response with HTTP 200

FOCUS: Note any 400/500 errors and missing fields for frontend usage constraints
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
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class GroupReportsBackendTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []

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

    async def test_group_bookings_endpoint(self):
        """Test /api/deluxe/group-bookings endpoint with date range and min_rooms variations"""
        print("\n🏨 Testing Group Bookings Endpoint (/api/deluxe/group-bookings)...")
        
        # Calculate date range: today -30 days to today +30 days
        today = datetime.now(timezone.utc).date()
        start_date = (today - timedelta(days=30)).isoformat()
        end_date = (today + timedelta(days=30)).isoformat()
        
        test_cases = [
            {
                "name": "Group bookings with default min_rooms (60-day range)",
                "params": {
                    "start_date": start_date,
                    "end_date": end_date
                },
                "expected_status": 200,
                "expected_fields": ["groups"],
                "expected_group_fields": ["company_id", "company_name", "room_count", "total_revenue", "booking_ids"]
            },
            {
                "name": "Group bookings with min_rooms=2",
                "params": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "min_rooms": 2
                },
                "expected_status": 200,
                "expected_fields": ["groups"],
                "expected_group_fields": ["company_id", "company_name", "room_count", "total_revenue", "booking_ids"]
            },
            {
                "name": "Group bookings with min_rooms=5",
                "params": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "min_rooms": 5
                },
                "expected_status": 200,
                "expected_fields": ["groups"],
                "expected_group_fields": ["company_id", "company_name", "room_count", "total_revenue", "booking_ids"]
            },
            {
                "name": "Group bookings with min_rooms=10",
                "params": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "min_rooms": 10
                },
                "expected_status": 200,
                "expected_fields": ["groups"],
                "expected_group_fields": ["company_id", "company_name", "room_count", "total_revenue", "booking_ids"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        results_by_min_rooms = {}
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/deluxe/group-bookings"
                params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                full_url = f"{url}?{params}"
                
                print(f"\n  🔍 Testing: {test_case['name']}")
                print(f"     URL: {full_url}")
                
                async with self.session.get(full_url, headers=self.get_headers()) as response:
                    response_time = response.headers.get('X-Response-Time', 'N/A')
                    
                    if response.status == test_case["expected_status"]:
                        data = await response.json()
                        
                        # Check main response fields
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Check groups array structure
                            groups = data.get("groups", [])
                            min_rooms = test_case["params"].get("min_rooms", "default")
                            results_by_min_rooms[min_rooms] = len(groups)
                            
                            print(f"     ✅ Response structure valid")
                            print(f"     📊 Groups found: {len(groups)}")
                            print(f"     ⏱️ Response time: {response_time}")
                            
                            if groups:
                                # Verify group structure
                                first_group = groups[0]
                                missing_group_fields = [field for field in test_case["expected_group_fields"] if field not in first_group]
                                
                                if not missing_group_fields:
                                    print(f"     ✅ Group structure valid")
                                    print(f"     🏢 Sample group: {first_group.get('company_name', 'N/A')} ({first_group.get('room_count', 0)} rooms)")
                                    passed += 1
                                else:
                                    print(f"     ❌ Missing group fields: {missing_group_fields}")
                            else:
                                print(f"     ✅ No groups found (valid response)")
                                passed += 1
                        else:
                            print(f"     ❌ Missing response fields: {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"     ❌ HTTP {response.status}: {error_text[:200]}...")
                        
            except Exception as e:
                print(f"     ❌ Error: {e}")
        
        # Analyze min_rooms parameter effectiveness
        print(f"\n  📈 Min Rooms Parameter Analysis:")
        for min_rooms, count in results_by_min_rooms.items():
            print(f"     min_rooms={min_rooms}: {count} groups")
        
        self.test_results.append({
            "endpoint": "GET /api/deluxe/group-bookings",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Date range: {start_date} to {end_date}, Min rooms variations tested"
        })

    async def test_pickup_pace_analytics_endpoint(self):
        """Test /api/deluxe/pickup-pace-analytics endpoint"""
        print("\n📈 Testing Pickup Pace Analytics Endpoint (/api/deluxe/pickup-pace-analytics)...")
        
        today = datetime.now(timezone.utc).date()
        future_date = (today + timedelta(days=7)).isoformat()
        
        test_cases = [
            {
                "name": "Pickup pace analytics for today",
                "params": {
                    "target_date": today.isoformat()
                },
                "expected_status": 200,
                "expected_fields": ["chart_data"],
                "expected_chart_fields": ["days_before", "daily_pickup", "cumulative_revenue"]
            },
            {
                "name": "Pickup pace analytics for future date (+7 days)",
                "params": {
                    "target_date": future_date
                },
                "expected_status": 200,
                "expected_fields": ["chart_data"],
                "expected_chart_fields": ["days_before", "daily_pickup", "cumulative_revenue"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/deluxe/pickup-pace-analytics"
                params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                full_url = f"{url}?{params}"
                
                print(f"\n  🔍 Testing: {test_case['name']}")
                print(f"     URL: {full_url}")
                
                async with self.session.get(full_url, headers=self.get_headers()) as response:
                    response_time = response.headers.get('X-Response-Time', 'N/A')
                    
                    if response.status == test_case["expected_status"]:
                        data = await response.json()
                        
                        # Check main response fields
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Check chart_data structure
                            chart_data = data.get("chart_data", [])
                            
                            print(f"     ✅ Response structure valid")
                            print(f"     📊 Chart data points: {len(chart_data)}")
                            print(f"     ⏱️ Response time: {response_time}")
                            
                            if chart_data:
                                # Verify chart data structure
                                first_point = chart_data[0]
                                missing_chart_fields = [field for field in test_case["expected_chart_fields"] if field not in first_point]
                                
                                if not missing_chart_fields:
                                    print(f"     ✅ Chart data structure valid")
                                    print(f"     📈 Sample data point: days_before={first_point.get('days_before')}, daily_pickup={first_point.get('daily_pickup')}")
                                    passed += 1
                                else:
                                    print(f"     ❌ Missing chart data fields: {missing_chart_fields}")
                            else:
                                print(f"     ✅ No chart data (valid response)")
                                passed += 1
                        else:
                            print(f"     ❌ Missing response fields: {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"     ❌ HTTP {response.status}: {error_text[:200]}...")
                        
            except Exception as e:
                print(f"     ❌ Error: {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/deluxe/pickup-pace-analytics",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "details": "Target dates: today and +7 days"
        })

    async def test_revenue_pickup_report_endpoint(self):
        """Test existing /api/revenue/pickup-report endpoint"""
        print("\n💰 Testing Revenue Pickup Report Endpoint (/api/revenue/pickup-report)...")
        
        test_cases = [
            {
                "name": "Revenue pickup report - basic call",
                "params": {},
                "expected_status": 200,
                "check_json": True
            },
            {
                "name": "Revenue pickup report with date parameter",
                "params": {
                    "date": datetime.now(timezone.utc).date().isoformat()
                },
                "expected_status": 200,
                "check_json": True
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/revenue/pickup-report"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                print(f"\n  🔍 Testing: {test_case['name']}")
                print(f"     URL: {url}")
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    response_time = response.headers.get('X-Response-Time', 'N/A')
                    
                    if response.status == test_case["expected_status"]:
                        if test_case["check_json"]:
                            try:
                                data = await response.json()
                                print(f"     ✅ HTTP 200 and valid JSON response")
                                print(f"     📊 Response keys: {list(data.keys()) if isinstance(data, dict) else 'Array response'}")
                                print(f"     ⏱️ Response time: {response_time}")
                                passed += 1
                            except json.JSONDecodeError:
                                print(f"     ❌ HTTP 200 but invalid JSON response")
                        else:
                            print(f"     ✅ HTTP {response.status}")
                            passed += 1
                    else:
                        error_text = await response.text()
                        print(f"     ❌ HTTP {response.status}: {error_text[:200]}...")
                        
            except Exception as e:
                print(f"     ❌ Error: {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/revenue/pickup-report",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%",
            "details": "Existing endpoint validation"
        })

    async def run_all_tests(self):
        """Run all group reports backend tests"""
        print("🚀 GROUP-BASED BACKEND REPORTS TESTING")
        print("Testing specific endpoints for group bookings and analytics")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Run tests
        await self.test_group_bookings_endpoint()
        await self.test_pickup_pace_analytics_endpoint()
        await self.test_revenue_pickup_report_endpoint()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 GROUP-BASED BACKEND REPORTS TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        print("\n📋 DETAILED RESULTS:")
        print("-" * 60)
        
        for result in self.test_results:
            endpoint_status = "✅" if result["passed"] == result["total"] else "❌"
            print(f"\n{endpoint_status} {result['endpoint']}")
            print(f"   Success Rate: {result['success_rate']}")
            print(f"   Details: {result['details']}")
            
            total_passed += result["passed"]
            total_tests += result["total"]
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: All group reports endpoints working perfectly!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most endpoints working, minor issues found")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some endpoints working, significant issues found")
        else:
            print("❌ CRITICAL: Major issues with group reports endpoints")
        
        print("\n🔍 TESTED ENDPOINTS:")
        print("• /api/deluxe/group-bookings - Group booking aggregation with min_rooms filtering")
        print("• /api/deluxe/pickup-pace-analytics - Booking pace analytics with chart data")
        print("• /api/revenue/pickup-report - Existing revenue pickup reporting")
        
        print("\n📝 FRONTEND USAGE NOTES:")
        if total_passed == total_tests:
            print("• All endpoints return expected data structures")
            print("• No 400/500 errors encountered")
            print("• Safe to use in frontend implementation")
        else:
            print("• Some endpoints may have issues - check individual results")
            print("• Implement error handling for failed endpoints")
            print("• Consider fallback options for missing data")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = GroupReportsBackendTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())