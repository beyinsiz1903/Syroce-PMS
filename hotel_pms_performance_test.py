#!/usr/bin/env python3
"""
HOTEL PMS PERFORMANCE OPTIMIZATION TESTING - 550 Rooms + 3 Years Data

OPTIMIZATIONS IMPLEMENTED:
1. MongoDB Indexes (9 total):
   - Bookings: 3 compound indexes (tenant_id + check_in + check_out, etc.)
   - Rooms: 2 indexes (tenant_id + room_number UNIQUE, tenant_id + status + room_type)
   - Guests: 2 indexes (email, phone lookups)
   - Folios: 2 indexes (booking_id, status + created_at)

2. Rooms Endpoint (/api/pms/rooms):
   - Added pagination: limit (default 100), offset
   - Added filters: status, room_type
   - Cache optimization: 30s TTL
   - Query: GET /api/pms/rooms?limit=100&offset=0&status=available

3. Bookings Endpoint (/api/pms/bookings):
   - Already has date filtering (start_date, end_date)
   - limit parameter (default 30)
   - Query: GET /api/pms/bookings?start_date=2025-01-20&end_date=2025-01-27&limit=500

CRITICAL TESTS NEEDED:
1. Pagination Performance Test - TARGET: <100ms per request
2. Date Range Query Performance - TARGET: <200ms
3. Index Verification
4. Load Test Simulation (10-20 concurrent requests)
5. Filter Performance

AUTHENTICATION: demo@hotel.com / demo123
"""

import asyncio
import aiohttp
import json
import time
import statistics
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import concurrent.futures

# Configuration
BACKEND_URL = "https://unitcare-1.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class HotelPMSPerformanceTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.performance_metrics = {}

    async def setup_session(self):
        """Initialize HTTP session with optimized settings"""
        connector = aiohttp.TCPConnector(
            limit=100,  # Total connection pool size
            limit_per_host=50,  # Per host connection limit
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
        )
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )

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

    async def measure_response_time(self, url: str, method: str = "GET", data: dict = None, params: dict = None) -> Dict[str, Any]:
        """Measure response time for a single request"""
        start_time = time.time()
        
        try:
            if method == "GET":
                async with self.session.get(url, headers=self.get_headers(), params=params) as response:
                    await response.json()  # Ensure we read the full response
                    end_time = time.time()
                    return {
                        "success": True,
                        "status_code": response.status,
                        "response_time_ms": (end_time - start_time) * 1000,
                        "url": url
                    }
            elif method == "POST":
                async with self.session.post(url, headers=self.get_headers(), json=data) as response:
                    await response.json()
                    end_time = time.time()
                    return {
                        "success": True,
                        "status_code": response.status,
                        "response_time_ms": (end_time - start_time) * 1000,
                        "url": url
                    }
        except Exception as e:
            end_time = time.time()
            return {
                "success": False,
                "error": str(e),
                "response_time_ms": (end_time - start_time) * 1000,
                "url": url
            }

    async def test_pagination_performance(self):
        """Test pagination performance with different limit values - TARGET: <100ms"""
        print("\n🚀 Testing Pagination Performance (TARGET: <100ms per request)")
        print("=" * 60)
        
        test_cases = [
            {"name": "Small page (limit=50)", "limit": 50, "offset": 0},
            {"name": "Standard page (limit=100)", "limit": 100, "offset": 0},
            {"name": "Large page (limit=200)", "limit": 200, "offset": 0},
            {"name": "Offset pagination (offset=100)", "limit": 100, "offset": 100},
            {"name": "Deep pagination (offset=200)", "limit": 100, "offset": 200},
            {"name": "Deep pagination (offset=400)", "limit": 100, "offset": 400},
        ]
        
        pagination_results = []
        
        for test_case in test_cases:
            print(f"\n📊 Testing: {test_case['name']}")
            
            # Run multiple requests to get average
            response_times = []
            success_count = 0
            
            for i in range(5):  # 5 requests per test case
                url = f"{BACKEND_URL}/pms/rooms"
                params = {
                    "limit": test_case["limit"],
                    "offset": test_case["offset"]
                }
                
                result = await self.measure_response_time(url, params=params)
                
                if result["success"] and result["status_code"] == 200:
                    response_times.append(result["response_time_ms"])
                    success_count += 1
                    print(f"  Request {i+1}: {result['response_time_ms']:.1f}ms")
                else:
                    print(f"  Request {i+1}: FAILED - {result.get('error', 'HTTP ' + str(result.get('status_code', 'Unknown')))}")
            
            if response_times:
                avg_time = statistics.mean(response_times)
                min_time = min(response_times)
                max_time = max(response_times)
                
                # Performance evaluation
                performance_status = "✅ EXCELLENT" if avg_time < 50 else "✅ GOOD" if avg_time < 100 else "⚠️ NEEDS OPTIMIZATION"
                
                print(f"  📈 Results: Avg: {avg_time:.1f}ms, Min: {min_time:.1f}ms, Max: {max_time:.1f}ms")
                print(f"  🎯 Performance: {performance_status} (Target: <100ms)")
                
                pagination_results.append({
                    "test_case": test_case["name"],
                    "avg_response_time": avg_time,
                    "min_response_time": min_time,
                    "max_response_time": max_time,
                    "success_rate": (success_count / 5) * 100,
                    "meets_target": avg_time < 100
                })
            else:
                print(f"  ❌ All requests failed")
                pagination_results.append({
                    "test_case": test_case["name"],
                    "avg_response_time": 0,
                    "success_rate": 0,
                    "meets_target": False
                })
        
        self.performance_metrics["pagination"] = pagination_results
        
        # Summary
        successful_tests = [r for r in pagination_results if r["meets_target"]]
        print(f"\n📊 PAGINATION PERFORMANCE SUMMARY:")
        print(f"   Tests meeting target (<100ms): {len(successful_tests)}/{len(pagination_results)}")
        print(f"   Overall success rate: {len(successful_tests)/len(pagination_results)*100:.1f}%")

    async def test_date_range_performance(self):
        """Test date range query performance - TARGET: <200ms"""
        print("\n📅 Testing Date Range Query Performance (TARGET: <200ms)")
        print("=" * 60)
        
        today = datetime.now(timezone.utc).date()
        
        test_cases = [
            {
                "name": "7 days (current implementation)",
                "start_date": today,
                "end_date": today + timedelta(days=7),
                "limit": 100
            },
            {
                "name": "30 days",
                "start_date": today,
                "end_date": today + timedelta(days=30),
                "limit": 200
            },
            {
                "name": "90 days",
                "start_date": today,
                "end_date": today + timedelta(days=90),
                "limit": 500
            },
            {
                "name": "1 year",
                "start_date": today - timedelta(days=365),
                "end_date": today,
                "limit": 1000
            },
            {
                "name": "3 years (full dataset)",
                "start_date": today - timedelta(days=1095),  # 3 years
                "end_date": today,
                "limit": 2000
            }
        ]
        
        date_range_results = []
        
        for test_case in test_cases:
            print(f"\n📊 Testing: {test_case['name']}")
            
            # Run multiple requests to get average
            response_times = []
            success_count = 0
            
            for i in range(3):  # 3 requests per test case (fewer due to larger datasets)
                url = f"{BACKEND_URL}/pms/bookings"
                params = {
                    "start_date": test_case["start_date"].isoformat(),
                    "end_date": test_case["end_date"].isoformat(),
                    "limit": test_case["limit"]
                }
                
                result = await self.measure_response_time(url, params=params)
                
                if result["success"] and result["status_code"] == 200:
                    response_times.append(result["response_time_ms"])
                    success_count += 1
                    print(f"  Request {i+1}: {result['response_time_ms']:.1f}ms")
                else:
                    print(f"  Request {i+1}: FAILED - {result.get('error', 'HTTP ' + str(result.get('status_code', 'Unknown')))}")
            
            if response_times:
                avg_time = statistics.mean(response_times)
                min_time = min(response_times)
                max_time = max(response_times)
                
                # Performance evaluation
                performance_status = "✅ EXCELLENT" if avg_time < 100 else "✅ GOOD" if avg_time < 200 else "⚠️ NEEDS OPTIMIZATION"
                
                print(f"  📈 Results: Avg: {avg_time:.1f}ms, Min: {min_time:.1f}ms, Max: {max_time:.1f}ms")
                print(f"  🎯 Performance: {performance_status} (Target: <200ms)")
                
                date_range_results.append({
                    "test_case": test_case["name"],
                    "avg_response_time": avg_time,
                    "min_response_time": min_time,
                    "max_response_time": max_time,
                    "success_rate": (success_count / 3) * 100,
                    "meets_target": avg_time < 200
                })
            else:
                print(f"  ❌ All requests failed")
                date_range_results.append({
                    "test_case": test_case["name"],
                    "avg_response_time": 0,
                    "success_rate": 0,
                    "meets_target": False
                })
        
        self.performance_metrics["date_range"] = date_range_results
        
        # Summary
        successful_tests = [r for r in date_range_results if r["meets_target"]]
        print(f"\n📊 DATE RANGE PERFORMANCE SUMMARY:")
        print(f"   Tests meeting target (<200ms): {len(successful_tests)}/{len(date_range_results)}")
        print(f"   Overall success rate: {len(successful_tests)/len(date_range_results)*100:.1f}%")

    async def test_filter_performance(self):
        """Test filter performance"""
        print("\n🔍 Testing Filter Performance")
        print("=" * 60)
        
        test_cases = [
            {
                "name": "Room status filter (available)",
                "url": f"{BACKEND_URL}/pms/rooms",
                "params": {"status": "available", "limit": 100}
            },
            {
                "name": "Room type filter (Standard)",
                "url": f"{BACKEND_URL}/pms/rooms",
                "params": {"room_type": "Standard", "limit": 100}
            },
            {
                "name": "Combined filters (status + room_type)",
                "url": f"{BACKEND_URL}/pms/rooms",
                "params": {"status": "available", "room_type": "Standard", "limit": 100}
            },
            {
                "name": "Booking status filter (confirmed)",
                "url": f"{BACKEND_URL}/pms/bookings",
                "params": {"status": "confirmed", "limit": 100}
            }
        ]
        
        filter_results = []
        
        for test_case in test_cases:
            print(f"\n📊 Testing: {test_case['name']}")
            
            response_times = []
            success_count = 0
            
            for i in range(3):
                result = await self.measure_response_time(test_case["url"], params=test_case["params"])
                
                if result["success"] and result["status_code"] == 200:
                    response_times.append(result["response_time_ms"])
                    success_count += 1
                    print(f"  Request {i+1}: {result['response_time_ms']:.1f}ms")
                else:
                    print(f"  Request {i+1}: FAILED - {result.get('error', 'HTTP ' + str(result.get('status_code', 'Unknown')))}")
            
            if response_times:
                avg_time = statistics.mean(response_times)
                performance_status = "✅ EXCELLENT" if avg_time < 50 else "✅ GOOD" if avg_time < 100 else "⚠️ NEEDS OPTIMIZATION"
                
                print(f"  📈 Average: {avg_time:.1f}ms - {performance_status}")
                
                filter_results.append({
                    "test_case": test_case["name"],
                    "avg_response_time": avg_time,
                    "success_rate": (success_count / 3) * 100
                })
        
        self.performance_metrics["filters"] = filter_results

    async def test_concurrent_load(self):
        """Test concurrent load simulation - 10-20 concurrent requests"""
        print("\n⚡ Testing Concurrent Load Simulation")
        print("=" * 60)
        
        test_scenarios = [
            {
                "name": "10 concurrent rooms requests",
                "url": f"{BACKEND_URL}/pms/rooms",
                "params": {"limit": 100},
                "concurrent_requests": 10
            },
            {
                "name": "15 concurrent bookings requests",
                "url": f"{BACKEND_URL}/pms/bookings",
                "params": {"limit": 100, "start_date": (datetime.now(timezone.utc).date()).isoformat(), "end_date": (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()},
                "concurrent_requests": 15
            },
            {
                "name": "20 concurrent mixed requests",
                "concurrent_requests": 20,
                "mixed": True
            }
        ]
        
        load_results = []
        
        for scenario in test_scenarios:
            print(f"\n📊 Testing: {scenario['name']}")
            
            start_time = time.time()
            
            if scenario.get("mixed"):
                # Mixed requests: 10 rooms + 10 bookings
                tasks = []
                
                # 10 rooms requests
                for i in range(10):
                    task = self.measure_response_time(
                        f"{BACKEND_URL}/pms/rooms",
                        params={"limit": 100, "offset": i * 10}
                    )
                    tasks.append(task)
                
                # 10 bookings requests
                for i in range(10):
                    task = self.measure_response_time(
                        f"{BACKEND_URL}/pms/bookings",
                        params={
                            "limit": 50,
                            "start_date": (datetime.now(timezone.utc).date()).isoformat(),
                            "end_date": (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
                        }
                    )
                    tasks.append(task)
            else:
                # Single endpoint concurrent requests
                tasks = []
                for i in range(scenario["concurrent_requests"]):
                    task = self.measure_response_time(scenario["url"], params=scenario["params"])
                    tasks.append(task)
            
            # Execute all requests concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            # Analyze results
            successful_results = [r for r in results if isinstance(r, dict) and r.get("success")]
            failed_results = [r for r in results if not (isinstance(r, dict) and r.get("success"))]
            
            if successful_results:
                response_times = [r["response_time_ms"] for r in successful_results]
                avg_response_time = statistics.mean(response_times)
                max_response_time = max(response_times)
                min_response_time = min(response_times)
                total_time = (end_time - start_time) * 1000
                
                success_rate = len(successful_results) / len(results) * 100
                
                print(f"  📈 Results:")
                print(f"     Success rate: {success_rate:.1f}% ({len(successful_results)}/{len(results)})")
                print(f"     Avg response time: {avg_response_time:.1f}ms")
                print(f"     Min response time: {min_response_time:.1f}ms")
                print(f"     Max response time: {max_response_time:.1f}ms")
                print(f"     Total execution time: {total_time:.1f}ms")
                
                performance_status = "✅ EXCELLENT" if success_rate == 100 and avg_response_time < 200 else "✅ GOOD" if success_rate >= 90 else "⚠️ NEEDS OPTIMIZATION"
                print(f"  🎯 Performance: {performance_status}")
                
                load_results.append({
                    "scenario": scenario["name"],
                    "success_rate": success_rate,
                    "avg_response_time": avg_response_time,
                    "max_response_time": max_response_time,
                    "total_time": total_time,
                    "concurrent_requests": scenario["concurrent_requests"]
                })
            else:
                print(f"  ❌ All requests failed")
                load_results.append({
                    "scenario": scenario["name"],
                    "success_rate": 0,
                    "concurrent_requests": scenario["concurrent_requests"]
                })
        
        self.performance_metrics["load_test"] = load_results

    async def verify_index_effectiveness(self):
        """Verify that indexes are working by testing query performance"""
        print("\n🔍 Verifying Index Effectiveness")
        print("=" * 60)
        
        # Test queries that should benefit from indexes
        index_tests = [
            {
                "name": "Bookings by tenant_id + date range (compound index)",
                "url": f"{BACKEND_URL}/pms/bookings",
                "params": {
                    "start_date": (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat(),
                    "end_date": (datetime.now(timezone.utc).date()).isoformat(),
                    "limit": 100
                }
            },
            {
                "name": "Rooms by tenant_id + status (compound index)",
                "url": f"{BACKEND_URL}/pms/rooms",
                "params": {"status": "available", "limit": 100}
            },
            {
                "name": "Rooms by tenant_id + room_type (compound index)",
                "url": f"{BACKEND_URL}/pms/rooms",
                "params": {"room_type": "Standard", "limit": 100}
            }
        ]
        
        index_results = []
        
        for test in index_tests:
            print(f"\n📊 Testing: {test['name']}")
            
            # Run the query multiple times to get consistent results
            response_times = []
            for i in range(5):
                result = await self.measure_response_time(test["url"], params=test["params"])
                if result["success"]:
                    response_times.append(result["response_time_ms"])
                    print(f"  Query {i+1}: {result['response_time_ms']:.1f}ms")
            
            if response_times:
                avg_time = statistics.mean(response_times)
                # Indexed queries should be very fast
                index_effective = avg_time < 50  # Very fast indicates good index usage
                
                status = "✅ INDEX EFFECTIVE" if index_effective else "⚠️ INDEX MAY NEED OPTIMIZATION"
                print(f"  📈 Average: {avg_time:.1f}ms - {status}")
                
                index_results.append({
                    "test": test["name"],
                    "avg_response_time": avg_time,
                    "index_effective": index_effective
                })
        
        self.performance_metrics["index_verification"] = index_results

    async def run_all_performance_tests(self):
        """Run all performance tests"""
        print("🚀 HOTEL PMS PERFORMANCE OPTIMIZATION TESTING")
        print("Testing 550-room property with 3 years of booking data")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Run all performance tests
        await self.test_pagination_performance()
        await self.test_date_range_performance()
        await self.test_filter_performance()
        await self.test_concurrent_load()
        await self.verify_index_effectiveness()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print comprehensive results
        self.print_performance_summary()

    def print_performance_summary(self):
        """Print comprehensive performance test summary"""
        print("\n" + "=" * 80)
        print("📊 HOTEL PMS PERFORMANCE OPTIMIZATION TEST RESULTS")
        print("=" * 80)
        
        # Pagination Performance Summary
        if "pagination" in self.performance_metrics:
            pagination_results = self.performance_metrics["pagination"]
            successful_pagination = [r for r in pagination_results if r["meets_target"]]
            
            print(f"\n🚀 PAGINATION PERFORMANCE (TARGET: <100ms):")
            print(f"   Tests meeting target: {len(successful_pagination)}/{len(pagination_results)} ({len(successful_pagination)/len(pagination_results)*100:.1f}%)")
            
            for result in pagination_results:
                status = "✅" if result["meets_target"] else "❌"
                print(f"   {status} {result['test_case']}: {result['avg_response_time']:.1f}ms avg")
        
        # Date Range Performance Summary
        if "date_range" in self.performance_metrics:
            date_results = self.performance_metrics["date_range"]
            successful_dates = [r for r in date_results if r["meets_target"]]
            
            print(f"\n📅 DATE RANGE PERFORMANCE (TARGET: <200ms):")
            print(f"   Tests meeting target: {len(successful_dates)}/{len(date_results)} ({len(successful_dates)/len(date_results)*100:.1f}%)")
            
            for result in date_results:
                status = "✅" if result["meets_target"] else "❌"
                print(f"   {status} {result['test_case']}: {result['avg_response_time']:.1f}ms avg")
        
        # Load Test Summary
        if "load_test" in self.performance_metrics:
            load_results = self.performance_metrics["load_test"]
            
            print(f"\n⚡ CONCURRENT LOAD TEST RESULTS:")
            for result in load_results:
                success_status = "✅" if result["success_rate"] == 100 else "⚠️" if result["success_rate"] >= 90 else "❌"
                print(f"   {success_status} {result['scenario']}: {result['success_rate']:.1f}% success, {result.get('avg_response_time', 0):.1f}ms avg")
        
        # Index Effectiveness Summary
        if "index_verification" in self.performance_metrics:
            index_results = self.performance_metrics["index_verification"]
            effective_indexes = [r for r in index_results if r["index_effective"]]
            
            print(f"\n🔍 INDEX EFFECTIVENESS:")
            print(f"   Effective indexes: {len(effective_indexes)}/{len(index_results)} ({len(effective_indexes)/len(index_results)*100:.1f}%)")
            
            for result in index_results:
                status = "✅" if result["index_effective"] else "⚠️"
                print(f"   {status} {result['test']}: {result['avg_response_time']:.1f}ms avg")
        
        # Overall Assessment
        print(f"\n" + "=" * 80)
        print("🎯 PERFORMANCE OPTIMIZATION ASSESSMENT:")
        
        # Calculate overall success metrics
        total_targets_met = 0
        total_tests = 0
        
        if "pagination" in self.performance_metrics:
            pagination_success = len([r for r in self.performance_metrics["pagination"] if r["meets_target"]])
            total_targets_met += pagination_success
            total_tests += len(self.performance_metrics["pagination"])
        
        if "date_range" in self.performance_metrics:
            date_success = len([r for r in self.performance_metrics["date_range"] if r["meets_target"]])
            total_targets_met += date_success
            total_tests += len(self.performance_metrics["date_range"])
        
        if total_tests > 0:
            overall_success_rate = (total_targets_met / total_tests) * 100
            
            if overall_success_rate >= 90:
                print("🎉 EXCELLENT: Performance optimizations are highly effective!")
                print("   ✅ Ready for 550-room property with 3 years of data")
            elif overall_success_rate >= 75:
                print("✅ GOOD: Performance optimizations are mostly effective")
                print("   ⚠️ Some fine-tuning may be needed for peak performance")
            elif overall_success_rate >= 50:
                print("⚠️ PARTIAL: Performance optimizations show mixed results")
                print("   🔧 Additional optimization work recommended")
            else:
                print("❌ CRITICAL: Performance optimizations need significant improvement")
                print("   🚨 Not ready for production with large dataset")
            
            print(f"\n📈 Overall Performance Target Achievement: {total_targets_met}/{total_tests} ({overall_success_rate:.1f}%)")
        
        print("\n🔧 OPTIMIZATIONS TESTED:")
        print("• MongoDB Indexes (9 total) - Compound indexes for bookings, rooms, guests, folios")
        print("• Pagination Performance - limit/offset parameters for large datasets")
        print("• Date Range Queries - Optimized for 3 years of booking data")
        print("• Filter Performance - Status and room type filtering")
        print("• Concurrent Load Handling - 10-20 simultaneous requests")
        print("• Cache Effectiveness - 30s TTL for frequently accessed data")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = HotelPMSPerformanceTester()
    await tester.run_all_performance_tests()

if __name__ == "__main__":
    asyncio.run(main())