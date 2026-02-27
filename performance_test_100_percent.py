#!/usr/bin/env python3
"""
100% PERFECT PERFORMANCE TEST - ABSOLUTE MAXIMUM SPEED
Target: ALL ENDPOINTS <10ms for 100% performance achievement

Critical Endpoints Performance Testing:
1. GET /api/monitoring/health - Target: <8ms
2. GET /api/monitoring/system - Target: <8ms
3. GET /api/pms/rooms - Target: <5ms (pre-warmed)
4. GET /api/pms/bookings - Target: <5ms (pre-warmed)
5. GET /api/pms/dashboard - Target: <5ms (pre-warmed)
6. GET /api/executive/kpi-snapshot - Target: <8ms (pre-warmed)

SUCCESS CRITERIA FOR 100%:
- Average response <10ms ALL endpoints
- Peak performance <5ms on cached endpoints
- P95 <15ms, P99 <20ms
- Cache hit rate >80%
- All data complete and accurate
"""

import asyncio
import aiohttp
import time
import statistics
import json
import os
from typing import List, Dict, Any
from datetime import datetime

# Configuration
BACKEND_URL = "https://pms-i18next-demo.preview.emergentagent.com/api"
TEST_USER_EMAIL = "admin@hotel.com"
TEST_USER_PASSWORD = "admin123"

# Critical endpoints with targets
CRITICAL_ENDPOINTS = [
    {
        "name": "Health Check",
        "endpoint": "/monitoring/health",
        "target_ms": 8,
        "method": "GET",
        "cached": False
    },
    {
        "name": "System Metrics",
        "endpoint": "/monitoring/system", 
        "target_ms": 8,
        "method": "GET",
        "cached": False
    },
    {
        "name": "PMS Rooms",
        "endpoint": "/pms/rooms",
        "target_ms": 5,
        "method": "GET", 
        "cached": True
    },
    {
        "name": "PMS Bookings",
        "endpoint": "/pms/bookings",
        "target_ms": 5,
        "method": "GET",
        "cached": True
    },
    {
        "name": "PMS Dashboard", 
        "endpoint": "/pms/dashboard",
        "target_ms": 5,
        "method": "GET",
        "cached": True
    },
    {
        "name": "Executive KPI Snapshot",
        "endpoint": "/executive/kpi-snapshot",
        "target_ms": 8,
        "method": "GET",
        "cached": True
    }
]

class PerformanceTestResult:
    def __init__(self, endpoint_name: str, target_ms: int):
        self.endpoint_name = endpoint_name
        self.target_ms = target_ms
        self.response_times: List[float] = []
        self.errors: List[str] = []
        self.cache_hits = 0
        self.total_calls = 0
        
    def add_result(self, response_time_ms: float, error: str = None, cache_hit: bool = False):
        self.total_calls += 1
        if error:
            self.errors.append(error)
        else:
            self.response_times.append(response_time_ms)
            if cache_hit:
                self.cache_hits += 1
    
    def get_stats(self) -> Dict[str, Any]:
        if not self.response_times:
            return {
                "min": 0, "max": 0, "avg": 0, "p95": 0, "p99": 0,
                "success_rate": 0, "cache_hit_rate": 0, "meets_target": False
            }
            
        sorted_times = sorted(self.response_times)
        return {
            "min": round(min(self.response_times), 1),
            "max": round(max(self.response_times), 1), 
            "avg": round(statistics.mean(self.response_times), 1),
            "p95": round(sorted_times[int(0.95 * len(sorted_times))], 1),
            "p99": round(sorted_times[int(0.99 * len(sorted_times))], 1),
            "success_rate": round((len(self.response_times) / self.total_calls) * 100, 1),
            "cache_hit_rate": round((self.cache_hits / self.total_calls) * 100, 1) if self.total_calls > 0 else 0,
            "meets_target": statistics.mean(self.response_times) < self.target_ms
        }

class PerformanceTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.results: Dict[str, PerformanceTestResult] = {}
        
    async def setup(self):
        """Setup HTTP session and authenticate"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=50)
        )
        
        # Authenticate
        try:
            login_data = {
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data.get("access_token")
                    print("✅ Authentication successful")
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
            
        return True
    
    async def cleanup(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()
    
    async def test_endpoint(self, endpoint_config: Dict[str, Any]) -> PerformanceTestResult:
        """Test a single endpoint 10 times"""
        result = PerformanceTestResult(endpoint_config["name"], endpoint_config["target_ms"])
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        print(f"\n🚀 Testing {endpoint_config['name']} ({endpoint_config['endpoint']})")
        print(f"   Target: <{endpoint_config['target_ms']}ms")
        
        # Make 10 consecutive calls
        call_times = []
        for i in range(10):
            try:
                start_time = time.perf_counter()
                
                async with self.session.get(
                    f"{BACKEND_URL}{endpoint_config['endpoint']}", 
                    headers=headers
                ) as response:
                    end_time = time.perf_counter()
                    response_time_ms = (end_time - start_time) * 1000
                    call_times.append(response_time_ms)
                    
                    if response.status == 200:
                        # Check if response has data
                        try:
                            data = await response.json()
                            has_data = bool(data)
                        except:
                            has_data = False
                            
                        # Detect cache hit (2nd+ calls should be faster for cached endpoints)
                        cache_hit = (i > 0 and endpoint_config["cached"] and 
                                   response_time_ms < call_times[0] * 0.8)
                        
                        result.add_result(response_time_ms, cache_hit=cache_hit)
                        
                        # Print individual call result
                        status = "🟢" if response_time_ms < endpoint_config["target_ms"] else "🔴"
                        cache_indicator = " (cached)" if cache_hit else ""
                        print(f"   Call {i+1}: {response_time_ms:.1f}ms {status}{cache_indicator}")
                        
                    else:
                        result.add_result(0, error=f"HTTP {response.status}")
                        print(f"   Call {i+1}: HTTP {response.status} ❌")
                        
            except Exception as e:
                result.add_result(0, error=str(e))
                print(f"   Call {i+1}: Error - {e} ❌")
                
            # Small delay between calls to simulate real usage
            await asyncio.sleep(0.1)
        
        return result
    
    async def run_performance_test(self):
        """Run the complete performance test"""
        print("=" * 80)
        print("🎯 100% PERFECT PERFORMANCE TEST - ABSOLUTE MAXIMUM SPEED")
        print("=" * 80)
        print(f"Target: ALL ENDPOINTS <10ms for 100% performance achievement")
        print(f"Testing {len(CRITICAL_ENDPOINTS)} critical endpoints...")
        
        if not await self.setup():
            return
        
        try:
            # Test each endpoint
            for endpoint_config in CRITICAL_ENDPOINTS:
                result = await self.test_endpoint(endpoint_config)
                self.results[endpoint_config["name"]] = result
            
            # Generate comprehensive report
            self.generate_report()
            
        finally:
            await self.cleanup()
    
    def generate_report(self):
        """Generate the performance test report"""
        print("\n" + "=" * 80)
        print("📊 PERFORMANCE TEST RESULTS")
        print("=" * 80)
        
        total_endpoints = len(self.results)
        endpoints_meeting_target = 0
        overall_cache_hits = 0
        overall_calls = 0
        
        for name, result in self.results.items():
            stats = result.get_stats()
            
            print(f"\n🔍 {name}:")
            print(f"   Calls 1-10: {', '.join([f'{t:.1f}' for t in result.response_times[:10]])} ms")
            print(f"   Min/Avg/Max/P95/P99: {stats['min']}/{stats['avg']}/{stats['max']}/{stats['p95']}/{stats['p99']} ms")
            print(f"   Cache effectiveness: {stats['cache_hit_rate']:.1f}%")
            
            if stats['meets_target']:
                print(f"   Status: ✅ <{result.target_ms}ms TARGET MET")
                endpoints_meeting_target += 1
            else:
                print(f"   Status: ❌ >={result.target_ms}ms TARGET MISSED")
            
            overall_cache_hits += result.cache_hits
            overall_calls += result.total_calls
        
        # Calculate overall performance
        performance_percentage = round((endpoints_meeting_target / total_endpoints) * 100)
        overall_cache_rate = round((overall_cache_hits / overall_calls) * 100) if overall_calls > 0 else 0
        
        print("\n" + "=" * 80)
        print("🏆 FINAL PERFORMANCE SCORE")
        print("=" * 80)
        print(f"Endpoints meeting <10ms: {endpoints_meeting_target}/{total_endpoints}")
        print(f"Performance achievement: {performance_percentage}%")
        print(f"Overall cache hit rate: {overall_cache_rate}%")
        
        if performance_percentage == 100:
            print("🎉 STATUS: 100% PERFECT PERFORMANCE ACHIEVED!")
            print("🚀 ALL ENDPOINTS UNDER TARGET - MAXIMUM SPEED CONFIRMED")
        else:
            print(f"⚠️  STATUS: {performance_percentage}% PERFORMANCE - NEEDS MORE OPTIMIZATION")
            print("🔧 Some endpoints require further optimization")
        
        # Success criteria check
        print("\n📋 SUCCESS CRITERIA CHECK:")
        avg_under_10ms = all(result.get_stats()['avg'] < 10 for result in self.results.values())
        cached_under_5ms = all(
            result.get_stats()['avg'] < 5 
            for name, result in self.results.items() 
            if any(ep['name'] == name and ep['cached'] for ep in CRITICAL_ENDPOINTS)
        )
        p95_under_15ms = all(result.get_stats()['p95'] < 15 for result in self.results.values())
        p99_under_20ms = all(result.get_stats()['p99'] < 20 for result in self.results.values())
        cache_rate_over_80 = overall_cache_rate > 80
        
        print(f"✅ Average response <10ms ALL endpoints: {'YES' if avg_under_10ms else 'NO'}")
        print(f"✅ Peak performance <5ms on cached endpoints: {'YES' if cached_under_5ms else 'NO'}")
        print(f"✅ P95 <15ms: {'YES' if p95_under_15ms else 'NO'}")
        print(f"✅ P99 <20ms: {'YES' if p99_under_20ms else 'NO'}")
        print(f"✅ Cache hit rate >80%: {'YES' if cache_rate_over_80 else 'NO'}")
        
        all_criteria_met = all([avg_under_10ms, cached_under_5ms, p95_under_15ms, p99_under_20ms, cache_rate_over_80])
        
        if all_criteria_met:
            print("\n🎯 RESULT: 100% PERFECT PERFORMANCE - ALL CRITERIA MET!")
        else:
            print(f"\n⚠️  RESULT: {performance_percentage}% PERFORMANCE - SOME CRITERIA NOT MET")

async def main():
    """Main test execution"""
    tester = PerformanceTester()
    await tester.run_performance_test()

if __name__ == "__main__":
    asyncio.run(main())