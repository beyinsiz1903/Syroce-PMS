#!/usr/bin/env python3
"""
FIX VERIFICATION TEST - RE-TEST PREVIOUSLY FAILED ENDPOINTS

PREVIOUS RESULTS: 10/13 pages working (76.9%)

FIXES APPLIED:
1. ✅ Mobile Housekeeping datetime parsing error FIXED
   - Added proper datetime parsing for started_at field
   
2. ✅ PMS Companies endpoint ADDED
   - Created /api/pms/companies alias endpoint
   
3. ✅ Contracted Rates endpoint ADDED
   - Created /api/contracted-rates list endpoint

RE-TEST PRIORITY:

HIGH PRIORITY (Previously Failed - Now Fixed):
1. Mobile Housekeeping (/api/housekeeping/mobile/room-assignments)
   - Expected: HTTP 200 (was HTTP 500)
   - Verify datetime parsing works correctly
   
2. PMS Companies (/api/pms/companies)
   - Expected: HTTP 200 (was HTTP 404)
   - Verify companies list returns
   
3. Contracted Rates (/api/contracted-rates)
   - Expected: HTTP 200 (was HTTP 404)
   - Verify contracted rates list returns

REGRESSION CHECK (Should Still Work):
4. GM Dashboard (9 APIs)
5. PMS Module (5 APIs)
6. All Mobile Pages
7. Executive Dashboard
8. Channels
9. Rate Management

EXPECTED RESULT: 13/13 pages working (100% success rate)
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
BACKEND_URL = "https://locust-load-test.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class FixVerificationTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.failed_endpoints = []
        self.success_count = 0
        self.total_count = 0

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

    async def test_endpoint(self, method: str, endpoint: str, description: str, expected_status: int = 200, payload: dict = None, params: dict = None):
        """Generic endpoint tester"""
        self.total_count += 1
        
        try:
            url = f"{BACKEND_URL}{endpoint}"
            if params:
                param_str = "&".join([f"{k}={v}" for k, v in params.items()])
                url += f"?{param_str}"
            
            headers = self.get_headers()
            
            if method.upper() == "GET":
                async with self.session.get(url, headers=headers) as response:
                    status = response.status
                    if status == expected_status:
                        data = await response.json()
                        print(f"  ✅ {description}: HTTP {status} - SUCCESS")
                        self.success_count += 1
                        return True, data
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {description}: HTTP {status} (expected {expected_status}) - {error_text[:200]}")
                        self.failed_endpoints.append(f"{method} {endpoint} - HTTP {status}")
                        return False, None
                        
            elif method.upper() == "POST":
                async with self.session.post(url, headers=headers, json=payload) as response:
                    status = response.status
                    if status == expected_status:
                        data = await response.json()
                        print(f"  ✅ {description}: HTTP {status} - SUCCESS")
                        self.success_count += 1
                        return True, data
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {description}: HTTP {status} (expected {expected_status}) - {error_text[:200]}")
                        self.failed_endpoints.append(f"{method} {endpoint} - HTTP {status}")
                        return False, None
                        
        except Exception as e:
            print(f"  ❌ {description}: ERROR - {str(e)}")
            self.failed_endpoints.append(f"{method} {endpoint} - ERROR: {str(e)}")
            return False, None

    async def test_high_priority_fixes(self):
        """Test the 3 previously failed endpoints that were supposedly fixed"""
        print("\n🔥 HIGH PRIORITY - Testing Previously Failed Endpoints (Now Fixed)")
        print("=" * 70)
        
        # 1. Mobile Housekeeping - was HTTP 500, should now be HTTP 200
        print("\n1. Mobile Housekeeping Room Assignments")
        success, data = await self.test_endpoint(
            "GET", 
            "/housekeeping/mobile/room-assignments",
            "Mobile Housekeeping Room Assignments",
            200
        )
        if success and data:
            print(f"     📊 Response structure: {list(data.keys())}")
            if 'assignments' in data:
                print(f"     📊 Assignments count: {len(data.get('assignments', []))}")
        
        # Test with staff_name filter
        success, data = await self.test_endpoint(
            "GET", 
            "/housekeeping/mobile/room-assignments",
            "Mobile Housekeeping with staff filter",
            200,
            params={"staff_name": "John Doe"}
        )
        
        # 2. PMS Companies - was HTTP 404, should now be HTTP 200
        print("\n2. PMS Companies Endpoint")
        success, data = await self.test_endpoint(
            "GET", 
            "/pms/companies",
            "PMS Companies List",
            200
        )
        if success and data:
            print(f"     📊 Response structure: {list(data.keys())}")
            if 'companies' in data:
                print(f"     📊 Companies count: {len(data.get('companies', []))}")
        
        # 3. Contracted Rates - was HTTP 404, should now be HTTP 200
        print("\n3. Contracted Rates Endpoint")
        success, data = await self.test_endpoint(
            "GET", 
            "/contracted-rates",
            "Contracted Rates List",
            200
        )
        if success and data:
            print(f"     📊 Response structure: {list(data.keys())}")
            if 'rates' in data:
                print(f"     📊 Rates count: {len(data.get('rates', []))}")

    async def test_gm_dashboard_regression(self):
        """Test GM Dashboard (9 APIs) - Regression Check"""
        print("\n📊 GM DASHBOARD - Regression Check (9 APIs)")
        print("=" * 50)
        
        gm_endpoints = [
            ("/dashboard/employee-performance", "Employee Performance"),
            ("/dashboard/guest-satisfaction-trends", "Guest Satisfaction Trends"),
            ("/dashboard/ota-cancellation-rate", "OTA Cancellation Rate"),
            ("/executive/kpi-snapshot", "KPI Snapshot"),
            ("/executive/performance-alerts", "Performance Alerts"),
            ("/executive/daily-summary", "Daily Summary"),
            ("/housekeeping/cleaning-time-statistics", "Cleaning Time Statistics"),
            ("/rms/demand-heatmap", "Demand Heatmap"),
            ("/rms/compset-analysis", "CompSet Analysis")
        ]
        
        for endpoint, description in gm_endpoints:
            await self.test_endpoint("GET", endpoint, f"GM Dashboard - {description}", 200)

    async def test_pms_module_regression(self):
        """Test PMS Module (5 APIs) - Regression Check"""
        print("\n🏨 PMS MODULE - Regression Check (5 APIs)")
        print("=" * 45)
        
        pms_endpoints = [
            ("/pms/bookings", "PMS Bookings"),
            ("/pms/companies", "PMS Companies"),  # This was the fixed one
            ("/pms/rooms", "PMS Rooms"),
            ("/pms/guests", "PMS Guests"),
            ("/pms/dashboard", "PMS Dashboard")
        ]
        
        for endpoint, description in pms_endpoints:
            await self.test_endpoint("GET", endpoint, f"PMS - {description}", 200)

    async def test_mobile_pages_regression(self):
        """Test All Mobile Pages - Regression Check"""
        print("\n📱 MOBILE PAGES - Regression Check")
        print("=" * 40)
        
        mobile_endpoints = [
            ("/mobile/dashboard", "Mobile Dashboard"),
            ("/mobile/revenue", "Mobile Revenue"),
            ("/mobile/fnb", "Mobile F&B"),
            ("/mobile/housekeeping", "Mobile Housekeeping"),
            ("/mobile/maintenance", "Mobile Maintenance"),
            ("/mobile/frontdesk", "Mobile Front Desk"),
            ("/mobile/gm", "Mobile GM"),
            ("/mobile/channels", "Mobile Channels"),
            ("/mobile/contracts", "Mobile Contracts"),
            ("/mobile/rate-management", "Mobile Rate Management")
        ]
        
        for endpoint, description in mobile_endpoints:
            await self.test_endpoint("GET", endpoint, description, 200)

    async def test_executive_dashboard_regression(self):
        """Test Executive Dashboard - Regression Check"""
        print("\n👔 EXECUTIVE DASHBOARD - Regression Check")
        print("=" * 45)
        
        exec_endpoints = [
            ("/executive/kpi-snapshot", "Executive KPI Snapshot"),
            ("/executive/performance-alerts", "Executive Performance Alerts"),
            ("/executive/daily-summary", "Executive Daily Summary")
        ]
        
        for endpoint, description in exec_endpoints:
            await self.test_endpoint("GET", endpoint, description, 200)

    async def test_channels_regression(self):
        """Test Channels - Regression Check"""
        print("\n📡 CHANNELS - Regression Check")
        print("=" * 35)
        
        await self.test_endpoint("GET", "/mobile/channels", "Channels", 200)

    async def test_rate_management_regression(self):
        """Test Rate Management - Regression Check"""
        print("\n💰 RATE MANAGEMENT - Regression Check")
        print("=" * 40)
        
        rate_endpoints = [
            ("/mobile/rate-management", "Rate Management"),
            ("/contracted-rates", "Contracted Rates"),  # This was the fixed one
            ("/rms/price-recommendation-slider", "Price Recommendation"),
            ("/rms/demand-heatmap", "Demand Heatmap"),
            ("/rms/compset-analysis", "CompSet Analysis")
        ]
        
        for endpoint, description in rate_endpoints:
            await self.test_endpoint("GET", endpoint, description, 200)

    async def run_comprehensive_test(self):
        """Run all tests in sequence"""
        print("🚀 STARTING FIX VERIFICATION TEST")
        print("=" * 60)
        print("Target: 13/13 pages working (100% success rate)")
        print("Previous: 10/13 pages working (76.9% success rate)")
        print("=" * 60)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Run tests in priority order
        await self.test_high_priority_fixes()
        await self.test_gm_dashboard_regression()
        await self.test_pms_module_regression()
        await self.test_mobile_pages_regression()
        await self.test_executive_dashboard_regression()
        await self.test_channels_regression()
        await self.test_rate_management_regression()
        
        # Cleanup
        await self.cleanup_session()
        
        # Final Results
        self.print_final_results()

    def print_final_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 80)
        print("🎯 FIX VERIFICATION TEST RESULTS")
        print("=" * 80)
        
        success_rate = (self.success_count / self.total_count * 100) if self.total_count > 0 else 0
        
        print(f"📊 OVERALL RESULTS:")
        print(f"   ✅ Successful: {self.success_count}/{self.total_count}")
        print(f"   📈 Success Rate: {success_rate:.1f}%")
        print(f"   🎯 Target: 100% (13/13 pages)")
        print(f"   📊 Previous: 76.9% (10/13 pages)")
        
        if success_rate >= 100:
            print(f"\n🎉 SUCCESS! Target achieved: {success_rate:.1f}% success rate")
        elif success_rate >= 90:
            print(f"\n🟡 NEAR SUCCESS: {success_rate:.1f}% success rate (target: 100%)")
        else:
            print(f"\n🔴 NEEDS WORK: {success_rate:.1f}% success rate (target: 100%)")
        
        if self.failed_endpoints:
            print(f"\n❌ FAILED ENDPOINTS ({len(self.failed_endpoints)}):")
            for i, endpoint in enumerate(self.failed_endpoints, 1):
                print(f"   {i}. {endpoint}")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = FixVerificationTester()
    await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())