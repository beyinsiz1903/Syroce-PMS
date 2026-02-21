#!/usr/bin/env python3
"""
SIMPLE MONITORING ENDPOINTS TEST (No Authentication Required)
Testing the monitoring endpoints that should be publicly accessible for health checks
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Configuration
BACKEND_URL = "https://guest-unified.preview.emergentagent.com/api"

class SimpleMonitoringTester:
    def __init__(self):
        self.session = None
        self.test_results = []

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def measure_response_time(self, url: str) -> tuple:
        """Measure response time for an endpoint"""
        start_time = time.time()
        try:
            async with self.session.get(url) as response:
                response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                end_time = time.time()
                response_time = (end_time - start_time) * 1000  # Convert to milliseconds
                return response.status, response_data, response_time
        except Exception as e:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            return 500, {"error": str(e)}, response_time

    async def test_monitoring_health(self):
        """Test GET /api/monitoring/health"""
        print("\n🏥 Testing Health Check Endpoint...")
        
        url = f"{BACKEND_URL}/monitoring/health"
        status, data, response_time = await self.measure_response_time(url)
        
        test_result = {
            "endpoint": "GET /api/monitoring/health",
            "status": status,
            "response_time_ms": response_time,
            "passed": False,
            "data": data
        }
        
        if status == 200:
            print(f"  ✅ Health check: HTTP 200 - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {json.dumps(data, indent=2)}")
            test_result["passed"] = True
        else:
            print(f"  ❌ Health check: HTTP {status} - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {data}")
        
        self.test_results.append(test_result)

    async def test_monitoring_system(self):
        """Test GET /api/monitoring/system"""
        print("\n💻 Testing System Metrics Endpoint...")
        
        url = f"{BACKEND_URL}/monitoring/system"
        status, data, response_time = await self.measure_response_time(url)
        
        test_result = {
            "endpoint": "GET /api/monitoring/system",
            "status": status,
            "response_time_ms": response_time,
            "passed": False,
            "data": data
        }
        
        if status == 200:
            print(f"  ✅ System metrics: HTTP 200 - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {json.dumps(data, indent=2)}")
            test_result["passed"] = True
        else:
            print(f"  ❌ System metrics: HTTP {status} - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {data}")
        
        self.test_results.append(test_result)

    async def test_monitoring_database(self):
        """Test GET /api/monitoring/database"""
        print("\n🗄️ Testing Database Monitoring Endpoint...")
        
        url = f"{BACKEND_URL}/monitoring/database"
        status, data, response_time = await self.measure_response_time(url)
        
        test_result = {
            "endpoint": "GET /api/monitoring/database",
            "status": status,
            "response_time_ms": response_time,
            "passed": False,
            "data": data
        }
        
        if status == 200:
            print(f"  ✅ Database metrics: HTTP 200 - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {json.dumps(data, indent=2)}")
            test_result["passed"] = True
        else:
            print(f"  ❌ Database metrics: HTTP {status} - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {data}")
        
        self.test_results.append(test_result)

    async def test_monitoring_alerts(self):
        """Test GET /api/monitoring/alerts"""
        print("\n🚨 Testing Monitoring Alerts Endpoint...")
        
        url = f"{BACKEND_URL}/monitoring/alerts"
        status, data, response_time = await self.measure_response_time(url)
        
        test_result = {
            "endpoint": "GET /api/monitoring/alerts",
            "status": status,
            "response_time_ms": response_time,
            "passed": False,
            "data": data
        }
        
        if status == 200:
            print(f"  ✅ Monitoring alerts: HTTP 200 - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {json.dumps(data, indent=2)}")
            test_result["passed"] = True
        else:
            print(f"  ❌ Monitoring alerts: HTTP {status} - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {data}")
        
        self.test_results.append(test_result)

    async def test_monitoring_metrics(self):
        """Test GET /api/monitoring/metrics"""
        print("\n📊 Testing Monitoring Metrics Endpoint...")
        
        url = f"{BACKEND_URL}/monitoring/metrics"
        status, data, response_time = await self.measure_response_time(url)
        
        test_result = {
            "endpoint": "GET /api/monitoring/metrics",
            "status": status,
            "response_time_ms": response_time,
            "passed": False,
            "data": data
        }
        
        if status == 200:
            print(f"  ✅ Monitoring metrics: HTTP 200 - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {json.dumps(data, indent=2)}")
            test_result["passed"] = True
        else:
            print(f"  ❌ Monitoring metrics: HTTP {status} - Response time: {response_time:.1f}ms")
            print(f"  📄 Response: {data}")
        
        self.test_results.append(test_result)

    async def run_all_tests(self):
        """Run all monitoring tests"""
        print("🚀 SIMPLE MONITORING ENDPOINTS TEST")
        print("Testing monitoring endpoints without authentication")
        print("=" * 60)
        
        await self.setup_session()
        
        await self.test_monitoring_health()
        await self.test_monitoring_system()
        await self.test_monitoring_database()
        await self.test_monitoring_alerts()
        await self.test_monitoring_metrics()
        
        await self.cleanup_session()
        
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 MONITORING TEST RESULTS")
        print("=" * 60)
        
        passed = sum(1 for r in self.test_results if r["passed"])
        total = len(self.test_results)
        success_rate = (passed / total * 100) if total > 0 else 0
        
        print(f"\n📈 SUCCESS RATE: {passed}/{total} ({success_rate:.1f}%)")
        
        for result in self.test_results:
            status_icon = "✅" if result["passed"] else "❌"
            print(f"{status_icon} {result['endpoint']}: {result['response_time_ms']:.1f}ms")
        
        # Performance analysis
        response_times = [r["response_time_ms"] for r in self.test_results if r["passed"]]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
            
            print(f"\n🎯 PERFORMANCE METRICS:")
            print(f"• Average Response Time: {avg_time:.1f}ms")
            print(f"• Fastest Response: {min_time:.1f}ms")
            print(f"• Slowest Response: {max_time:.1f}ms")
            
            if avg_time < 500:
                print("✅ Performance target met: Average response time < 500ms")
            else:
                print("⚠️ Performance target missed: Average response time >= 500ms")
        
        print("\n" + "=" * 60)

async def main():
    """Main test execution"""
    tester = SimpleMonitoringTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())