#!/usr/bin/env python3
"""
Backend API Test Suite for Ops Events & Telemetry
=================================================

Tests all ops events endpoints with proper authentication.
Uses real backend URL from frontend/.env configuration.
"""
import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, Any

import aiohttp


class OpsEventsAPITester:
    def __init__(self):
        # Use the actual backend URL from frontend/.env
        self.base_url = "https://ops-dashboard-148.preview.emergentagent.com"
        self.api_base = f"{self.base_url}/api"
        self.session = None
        self.auth_token = None
        
        # Test credentials from /app/memory/test_credentials.md
        self.test_email = "demo@hotel.com"
        self.test_password = "demo123"
        
        self.test_results = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def log_test(self, endpoint: str, status: str, details: str = ""):
        """Log test result"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        result = {
            "timestamp": timestamp,
            "endpoint": endpoint,
            "status": status,
            "details": details
        }
        self.test_results.append(result)
        
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"[{timestamp}] {status_icon} {endpoint} - {status}")
        if details:
            print(f"    {details}")
    
    async def authenticate(self) -> bool:
        """Authenticate and get JWT token"""
        print(f"\n🔐 Authenticating with {self.test_email}...")
        
        login_data = {
            "email": self.test_email,
            "password": self.test_password
        }
        
        try:
            async with self.session.post(
                f"{self.api_base}/auth/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Token is in 'access_token' field per test credentials
                    self.auth_token = data.get("access_token")
                    if self.auth_token:
                        self.log_test("POST /api/auth/login", "PASS", "Authentication successful")
                        return True
                    else:
                        self.log_test("POST /api/auth/login", "FAIL", "No access_token in response")
                        return False
                else:
                    error_text = await response.text()
                    self.log_test("POST /api/auth/login", "FAIL", f"Status {response.status}: {error_text}")
                    return False
                    
        except Exception as e:
            self.log_test("POST /api/auth/login", "FAIL", f"Exception: {str(e)}")
            return False
    
    def get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        if not self.auth_token:
            return {}
        return {"Authorization": f"Bearer {self.auth_token}"}
    
    async def test_endpoint(self, method: str, endpoint: str, expected_fields: list = None, params: dict = None) -> Dict[str, Any]:
        """Test a single endpoint"""
        url = f"{self.api_base}{endpoint}"
        headers = self.get_auth_headers()
        
        try:
            async with self.session.request(method, url, headers=headers, params=params) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    try:
                        data = json.loads(response_text)
                        
                        # Check expected fields if provided
                        missing_fields = []
                        if expected_fields:
                            for field in expected_fields:
                                if field not in data:
                                    missing_fields.append(field)
                        
                        if missing_fields:
                            self.log_test(f"{method} {endpoint}", "FAIL", f"Missing fields: {missing_fields}")
                        else:
                            details = f"Response structure OK"
                            if params:
                                details += f" (params: {params})"
                            self.log_test(f"{method} {endpoint}", "PASS", details)
                        
                        return {"status": "success", "data": data, "missing_fields": missing_fields}
                        
                    except json.JSONDecodeError:
                        self.log_test(f"{method} {endpoint}", "FAIL", "Invalid JSON response")
                        return {"status": "error", "error": "Invalid JSON"}
                else:
                    self.log_test(f"{method} {endpoint}", "FAIL", f"Status {response.status}: {response_text}")
                    return {"status": "error", "status_code": response.status, "error": response_text}
                    
        except Exception as e:
            self.log_test(f"{method} {endpoint}", "FAIL", f"Exception: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    async def run_ops_events_tests(self):
        """Run all ops events endpoint tests"""
        print(f"\n🧪 Testing Ops Events & Telemetry Endpoints")
        print(f"Backend URL: {self.base_url}")
        print("=" * 60)
        
        # Test 1: List operational events
        await self.test_endpoint(
            "GET", "/ops-events/list",
            expected_fields=["events", "count", "severity_counts_24h"]
        )
        
        # Test 2: List operational events with severity filter
        await self.test_endpoint(
            "GET", "/ops-events/list",
            expected_fields=["events", "count", "severity_counts_24h"],
            params={"severity": "critical"}
        )
        
        # Test 3: List operational events with event_type filter
        await self.test_endpoint(
            "GET", "/ops-events/list",
            expected_fields=["events", "count", "severity_counts_24h"],
            params={"event_type": "webhook.delivery"}
        )
        
        # Test 4: Webhook deliveries
        await self.test_endpoint(
            "GET", "/ops-events/webhook-deliveries",
            expected_fields=["deliveries", "count", "summary"]
        )
        
        # Test 5: Webhook deliveries with status filter
        await self.test_endpoint(
            "GET", "/ops-events/webhook-deliveries",
            expected_fields=["deliveries", "count", "summary"],
            params={"status": "succeeded"}
        )
        
        # Test 6: Webhook DLQ
        await self.test_endpoint(
            "GET", "/ops-events/webhook-dlq",
            expected_fields=["items", "count", "pending_count", "total_count"]
        )
        
        # Test 7: Rate limit status
        await self.test_endpoint(
            "GET", "/ops-events/rate-limit-status",
            expected_fields=["provider", "status", "throttle_events_24h", "rate_limited_pushes_24h"]
        )
        
        # Test 8: Channel health
        await self.test_endpoint(
            "GET", "/ops-events/channel-health",
            expected_fields=["channels", "total_channels"]
        )
        
        # Test 9: Dashboard summary
        await self.test_endpoint(
            "GET", "/ops-events/dashboard-summary",
            expected_fields=["webhook_delivery", "rate_limit", "channels", "recent_events", "recent_imports", "last_successful_pushes", "generated_at"]
        )
        
        # Test 10: DLQ retry with invalid ID (should return 400)
        print(f"\n🧪 Testing DLQ retry with invalid ID (expecting 400)...")
        try:
            async with self.session.post(
                f"{self.api_base}/ops-events/webhook-dlq/fake-id/retry",
                headers=self.get_auth_headers()
            ) as response:
                if response.status == 400:
                    self.log_test("POST /ops-events/webhook-dlq/fake-id/retry", "PASS", "Correctly returned 400 for invalid ID")
                else:
                    error_text = await response.text()
                    self.log_test("POST /ops-events/webhook-dlq/fake-id/retry", "FAIL", f"Expected 400, got {response.status}: {error_text}")
        except Exception as e:
            self.log_test("POST /ops-events/webhook-dlq/fake-id/retry", "FAIL", f"Exception: {str(e)}")
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("🏁 TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed = sum(1 for r in self.test_results if r["status"] == "FAIL")
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "0%")
        
        if failed > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"  • {result['endpoint']} - {result['details']}")
        
        print(f"\n📊 DETAILED RESULTS:")
        for result in self.test_results:
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            print(f"  {status_icon} {result['endpoint']}")
            if result["details"]:
                print(f"      {result['details']}")


async def main():
    """Main test runner"""
    print("🚀 Starting Ops Events & Telemetry Backend API Tests")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with OpsEventsAPITester() as tester:
        # Step 1: Authenticate
        if not await tester.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            sys.exit(1)
        
        # Step 2: Run all ops events tests
        await tester.run_ops_events_tests()
        
        # Step 3: Print summary
        tester.print_summary()
        
        # Return exit code based on results
        failed_count = sum(1 for r in tester.test_results if r["status"] == "FAIL")
        if failed_count > 0:
            print(f"\n❌ {failed_count} tests failed")
            sys.exit(1)
        else:
            print(f"\n✅ All tests passed!")
            sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())