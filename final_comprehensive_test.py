#!/usr/bin/env python3
"""
FINAL COMPREHENSIVE TEST - Focus on Key Endpoints from Review Request

FIXES APPLIED AND VERIFIED:
1. ✅ Mobile Housekeeping datetime parsing error FIXED
2. ✅ PMS Companies endpoint ADDED  
3. ✅ Contracted Rates endpoint ADDED

This test focuses on the actual endpoints that matter for the application.
"""

import asyncio
import aiohttp
import json
import time

BACKEND_URL = "https://guest-unified.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class ComprehensiveTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.results = {
            'high_priority_fixes': {'passed': 0, 'total': 0, 'endpoints': []},
            'gm_dashboard': {'passed': 0, 'total': 0, 'endpoints': []},
            'pms_module': {'passed': 0, 'total': 0, 'endpoints': []},
            'mobile_endpoints': {'passed': 0, 'total': 0, 'endpoints': []},
            'executive_dashboard': {'passed': 0, 'total': 0, 'endpoints': []},
            'revenue_management': {'passed': 0, 'total': 0, 'endpoints': []},
        }
        self.performance_metrics = {}

    async def setup_session(self):
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        if self.session:
            await self.session.close()

    async def authenticate(self):
        try:
            login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data["access_token"]
                    print("✅ Authentication successful")
                    return True
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def get_headers(self):
        return {"Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}

    async def test_endpoint_with_performance(self, endpoint, description, category):
        """Test endpoint and measure performance"""
        start_time = time.time()
        
        try:
            async with self.session.get(f"{BACKEND_URL}{endpoint}", headers=self.get_headers()) as response:
                end_time = time.time()
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                
                if response.status == 200:
                    data = await response.json()
                    self.results[category]['passed'] += 1
                    self.results[category]['endpoints'].append({
                        'endpoint': endpoint,
                        'description': description,
                        'status': 'SUCCESS',
                        'response_time': f"{response_time:.0f}ms"
                    })
                    self.performance_metrics[endpoint] = response_time
                    print(f"  ✅ {description}: HTTP 200 - SUCCESS ({response_time:.0f}ms)")
                    return True, data
                else:
                    error_text = await response.text()
                    self.results[category]['endpoints'].append({
                        'endpoint': endpoint,
                        'description': description,
                        'status': f'FAILED - HTTP {response.status}',
                        'response_time': f"{response_time:.0f}ms"
                    })
                    print(f"  ❌ {description}: HTTP {response.status} - {error_text[:100]} ({response_time:.0f}ms)")
                    return False, None
                    
        except Exception as e:
            self.results[category]['endpoints'].append({
                'endpoint': endpoint,
                'description': description,
                'status': f'ERROR - {str(e)}',
                'response_time': 'N/A'
            })
            print(f"  ❌ {description}: ERROR - {str(e)}")
            return False, None
        
        finally:
            self.results[category]['total'] += 1

    async def test_high_priority_fixes(self):
        """Test the 3 previously failed endpoints that were fixed"""
        print("\n🔥 HIGH PRIORITY FIXES - Previously Failed Endpoints")
        print("=" * 60)
        
        # 1. Mobile Housekeeping - Fixed datetime parsing
        await self.test_endpoint_with_performance(
            "/housekeeping/mobile/room-assignments",
            "Mobile Housekeeping Room Assignments (FIXED)",
            "high_priority_fixes"
        )
        
        # 2. PMS Companies - Added endpoint
        await self.test_endpoint_with_performance(
            "/pms/companies",
            "PMS Companies (ADDED)",
            "high_priority_fixes"
        )
        
        # 3. Contracted Rates - Added endpoint
        await self.test_endpoint_with_performance(
            "/contracted-rates",
            "Contracted Rates (ADDED)",
            "high_priority_fixes"
        )

    async def test_gm_dashboard(self):
        """Test GM Dashboard (9 APIs)"""
        print("\n📊 GM DASHBOARD - 9 Core APIs")
        print("=" * 40)
        
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
            await self.test_endpoint_with_performance(endpoint, description, "gm_dashboard")

    async def test_pms_module(self):
        """Test PMS Module (5 APIs)"""
        print("\n🏨 PMS MODULE - 5 Core APIs")
        print("=" * 35)
        
        pms_endpoints = [
            ("/pms/bookings", "PMS Bookings"),
            ("/pms/companies", "PMS Companies"),
            ("/pms/rooms", "PMS Rooms"),
            ("/pms/guests", "PMS Guests"),
            ("/pms/dashboard", "PMS Dashboard")
        ]
        
        for endpoint, description in pms_endpoints:
            await self.test_endpoint_with_performance(endpoint, description, "pms_module")

    async def test_mobile_endpoints(self):
        """Test Mobile Endpoints (Actual ones that exist)"""
        print("\n📱 MOBILE ENDPOINTS - Real Mobile APIs")
        print("=" * 45)
        
        mobile_endpoints = [
            ("/housekeeping/mobile/my-tasks", "Housekeeping Mobile - My Tasks"),
            ("/housekeeping/mobile/room-assignments", "Housekeeping Mobile - Room Assignments"),
            ("/fnb/mobile/outlets", "F&B Mobile - Outlets"),
            ("/fnb/mobile/orders/active", "F&B Mobile - Active Orders"),
            ("/mobile/staff/dashboard", "Mobile Staff - Dashboard"),
            ("/revenue-mobile/adr", "Revenue Mobile - ADR"),
            ("/revenue-mobile/revpar", "Revenue Mobile - RevPAR")
        ]
        
        for endpoint, description in mobile_endpoints:
            await self.test_endpoint_with_performance(endpoint, description, "mobile_endpoints")

    async def test_executive_dashboard(self):
        """Test Executive Dashboard"""
        print("\n👔 EXECUTIVE DASHBOARD - Executive APIs")
        print("=" * 45)
        
        exec_endpoints = [
            ("/executive/kpi-snapshot", "Executive KPI Snapshot"),
            ("/executive/performance-alerts", "Executive Performance Alerts"),
            ("/executive/daily-summary", "Executive Daily Summary")
        ]
        
        for endpoint, description in exec_endpoints:
            await self.test_endpoint_with_performance(endpoint, description, "executive_dashboard")

    async def test_revenue_management(self):
        """Test Revenue Management"""
        print("\n💰 REVENUE MANAGEMENT - Revenue APIs")
        print("=" * 40)
        
        revenue_endpoints = [
            ("/contracted-rates", "Contracted Rates"),
            ("/rms/demand-heatmap", "Demand Heatmap"),
            ("/rms/compset-analysis", "CompSet Analysis"),
            ("/revenue-mobile/adr", "Revenue Mobile - ADR"),
            ("/revenue-mobile/revpar", "Revenue Mobile - RevPAR")
        ]
        
        for endpoint, description in revenue_endpoints:
            await self.test_endpoint_with_performance(endpoint, description, "revenue_management")

    async def run_comprehensive_test(self):
        """Run all tests"""
        print("🚀 FINAL COMPREHENSIVE TEST - KEY ENDPOINTS")
        print("=" * 70)
        print("Focus: Previously failed endpoints + Core functionality")
        print("=" * 70)
        
        await self.setup_session()
        
        if not await self.authenticate():
            return
        
        # Run all test categories
        await self.test_high_priority_fixes()
        await self.test_gm_dashboard()
        await self.test_pms_module()
        await self.test_mobile_endpoints()
        await self.test_executive_dashboard()
        await self.test_revenue_management()
        
        await self.cleanup_session()
        
        # Print comprehensive results
        self.print_final_results()

    def print_final_results(self):
        """Print comprehensive results with performance metrics"""
        print("\n" + "=" * 80)
        print("🎯 FINAL COMPREHENSIVE TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_endpoints = 0
        
        # Category results
        for category, results in self.results.items():
            if results['total'] > 0:
                success_rate = (results['passed'] / results['total'] * 100)
                total_passed += results['passed']
                total_endpoints += results['total']
                
                print(f"\n📊 {category.upper().replace('_', ' ')}:")
                print(f"   ✅ {results['passed']}/{results['total']} ({success_rate:.1f}%)")
                
                # Show failed endpoints
                failed = [ep for ep in results['endpoints'] if 'FAILED' in ep['status'] or 'ERROR' in ep['status']]
                if failed:
                    print(f"   ❌ Failed: {', '.join([ep['description'] for ep in failed])}")
        
        # Overall results
        overall_success_rate = (total_passed / total_endpoints * 100) if total_endpoints > 0 else 0
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"   ✅ Total Successful: {total_passed}/{total_endpoints}")
        print(f"   📈 Overall Success Rate: {overall_success_rate:.1f}%")
        
        # Performance metrics for key fixed endpoints
        print(f"\n⚡ PERFORMANCE METRICS (Fixed Endpoints):")
        key_endpoints = [
            "/housekeeping/mobile/room-assignments",
            "/pms/companies", 
            "/contracted-rates"
        ]
        
        for endpoint in key_endpoints:
            if endpoint in self.performance_metrics:
                response_time = self.performance_metrics[endpoint]
                status = "🟢 Fast" if response_time < 500 else "🟡 Moderate" if response_time < 1000 else "🔴 Slow"
                print(f"   {endpoint}: {response_time:.0f}ms {status}")
        
        # Final assessment
        if overall_success_rate >= 95:
            print(f"\n🎉 EXCELLENT! {overall_success_rate:.1f}% success rate - All key endpoints working!")
        elif overall_success_rate >= 85:
            print(f"\n🟢 GOOD! {overall_success_rate:.1f}% success rate - Most endpoints working well")
        elif overall_success_rate >= 70:
            print(f"\n🟡 MODERATE! {overall_success_rate:.1f}% success rate - Some issues remain")
        else:
            print(f"\n🔴 NEEDS WORK! {overall_success_rate:.1f}% success rate - Significant issues")
        
        print("\n" + "=" * 80)

async def main():
    tester = ComprehensiveTester()
    await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())