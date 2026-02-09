#!/usr/bin/env python3
"""
PMS ROOMS PERFORMANCE TESTING
Measure response times for all PMS Rooms endpoints with demo@hotel.com / demo123
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime, timezone, timedelta
from statistics import mean, median

# Configuration
BACKEND_URL = "https://app-audit-9.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class PMSRoomsPerformanceTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.results = {}

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
                    print(f"✅ Authentication successful - User: {data['user']['name']}")
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

    async def measure_endpoint_performance(self, endpoint_name, url, method="GET", data=None, calls=20):
        """Measure endpoint performance with multiple calls"""
        print(f"\n📊 Testing {endpoint_name} ({calls} calls)...")
        
        response_times = []
        http_codes = []
        
        for i in range(calls):
            try:
                start_time = time.time()
                
                if method == "GET":
                    async with self.session.get(url, headers=self.get_headers()) as response:
                        end_time = time.time()
                        response_time = (end_time - start_time) * 1000  # Convert to ms
                        response_times.append(response_time)
                        http_codes.append(response.status)
                        
                        if i == 0:  # Show sample response for first call
                            if response.status == 200:
                                response_data = await response.json()
                                print(f"   📋 Sample response structure: {type(response_data)}")
                                if isinstance(response_data, list) and response_data:
                                    print(f"   📋 Sample item keys: {list(response_data[0].keys())}")
                                elif isinstance(response_data, dict):
                                    print(f"   📋 Response keys: {list(response_data.keys())}")
                
                elif method == "PUT":
                    async with self.session.put(url, json=data, headers=self.get_headers()) as response:
                        end_time = time.time()
                        response_time = (end_time - start_time) * 1000
                        response_times.append(response_time)
                        http_codes.append(response.status)
                
                elif method == "POST":
                    async with self.session.post(url, json=data, headers=self.get_headers()) as response:
                        end_time = time.time()
                        response_time = (end_time - start_time) * 1000
                        response_times.append(response_time)
                        http_codes.append(response.status)
                
                # Small delay between requests
                await asyncio.sleep(0.1)
                
            except Exception as e:
                print(f"   ❌ Call {i+1} failed: {e}")
        
        if response_times:
            avg_time = mean(response_times)
            median_time = median(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            success_rate = (http_codes.count(200) / len(http_codes)) * 100
            
            self.results[endpoint_name] = {
                "avg_ms": avg_time,
                "median_ms": median_time,
                "min_ms": min_time,
                "max_ms": max_time,
                "success_rate": success_rate,
                "total_calls": len(response_times)
            }
            
            print(f"   ✅ Average: {avg_time:.1f}ms | Median: {median_time:.1f}ms | Min: {min_time:.1f}ms | Max: {max_time:.1f}ms")
            print(f"   📈 Success Rate: {success_rate:.1f}% ({http_codes.count(200)}/{len(http_codes)})")
        else:
            print(f"   ❌ No successful calls")

    async def run_performance_tests(self):
        """Run performance tests for all PMS Rooms endpoints"""
        print("🚀 PMS ROOMS PERFORMANCE TESTING")
        print("Testing with demo@hotel.com / demo123")
        print("=" * 60)
        
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Get room and booking IDs for parameterized tests
        room_id = None
        booking_id = None
        
        # Get room ID
        try:
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    if rooms:
                        room_id = rooms[0]["id"]
        except:
            pass
        
        # Get booking ID
        try:
            async with self.session.get(f"{BACKEND_URL}/pms/bookings", headers=self.get_headers()) as response:
                if response.status == 200:
                    bookings = await response.json()
                    if bookings:
                        booking_id = bookings[0]["id"]
        except:
            pass
        
        # Test all endpoints
        await self.measure_endpoint_performance(
            "GET /api/pms/rooms",
            f"{BACKEND_URL}/pms/rooms"
        )
        
        await self.measure_endpoint_performance(
            "GET /api/pms/room-blocks",
            f"{BACKEND_URL}/pms/room-blocks"
        )
        
        await self.measure_endpoint_performance(
            "GET /api/pms/bookings",
            f"{BACKEND_URL}/pms/bookings"
        )
        
        await self.measure_endpoint_performance(
            "GET /api/pms/guests",
            f"{BACKEND_URL}/pms/guests"
        )
        
        if room_id:
            await self.measure_endpoint_performance(
                "PUT /api/pms/rooms/{room_id}",
                f"{BACKEND_URL}/pms/rooms/{room_id}",
                method="PUT",
                data={"status": "available"},
                calls=5  # Fewer calls for update operations
            )
        
        if booking_id:
            await self.measure_endpoint_performance(
                "GET /api/folio/booking/{booking_id}",
                f"{BACKEND_URL}/folio/booking/{booking_id}"
            )
        
        await self.cleanup_session()
        self.print_performance_summary()

    def print_performance_summary(self):
        """Print performance test summary"""
        print("\n" + "=" * 60)
        print("📊 PMS ROOMS PERFORMANCE TEST RESULTS")
        print("=" * 60)
        
        print(f"\n{'Endpoint':<35} {'Avg (ms)':<10} {'Success':<8} {'Status'}")
        print("-" * 60)
        
        for endpoint, metrics in self.results.items():
            avg_ms = metrics["avg_ms"]
            success_rate = metrics["success_rate"]
            
            # Performance status
            if avg_ms < 20:
                status = "🟢 Excellent"
            elif avg_ms < 50:
                status = "🟡 Good"
            elif avg_ms < 100:
                status = "🟠 Acceptable"
            else:
                status = "🔴 Slow"
            
            print(f"{endpoint:<35} {avg_ms:<10.1f} {success_rate:<8.1f}% {status}")
        
        # Overall assessment
        if self.results:
            avg_response_time = mean([metrics["avg_ms"] for metrics in self.results.values()])
            overall_success = mean([metrics["success_rate"] for metrics in self.results.values()])
            
            print(f"\n📈 OVERALL PERFORMANCE:")
            print(f"   Average Response Time: {avg_response_time:.1f}ms")
            print(f"   Overall Success Rate: {overall_success:.1f}%")
            
            if avg_response_time < 30 and overall_success >= 95:
                print("   🎉 EXCELLENT: PMS Rooms backend performance is outstanding!")
            elif avg_response_time < 50 and overall_success >= 90:
                print("   ✅ GOOD: PMS Rooms backend performance is solid")
            elif avg_response_time < 100 and overall_success >= 80:
                print("   ⚠️ ACCEPTABLE: PMS Rooms backend performance is adequate")
            else:
                print("   ❌ NEEDS IMPROVEMENT: PMS Rooms backend performance issues detected")
        
        print("\n" + "=" * 60)

async def main():
    """Main test execution"""
    tester = PMSRoomsPerformanceTester()
    await tester.run_performance_tests()

if __name__ == "__main__":
    asyncio.run(main())