#!/usr/bin/env python3
"""
DEMO USER LOGIN ENDPOINT TEST
Test the /auth/login endpoint with demo user credentials in preview environment.

OBJECTIVE: Test if demo user can login successfully

TARGET ENDPOINT:
POST /auth/login
Body: {"email": "demo@hotel.com", "password": "demo123"}

EXPECTED RESPONSE:
- HTTP status code: 200
- Response body should contain:
  - user.email: "demo@hotel.com"
  - user.role: user role
  - tenant_id: tenant identifier
  - access_token: JWT token

TEST SCENARIO:
1. Call POST /api/auth/login with demo credentials
2. Verify HTTP status code
3. Verify response structure
4. Check for required fields (user.email, user.role, tenant_id, access_token)
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime, timezone

# Configuration
BASE_URL = "https://hotel-pms-demo.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class LoginTester:
    def __init__(self):
        self.session = None
        self.test_results = []

    async def create_session(self):
        """Create HTTP session with proper headers"""
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        )

    async def close_session(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()

    async def test_login_endpoint(self):
        """Test the login endpoint with demo credentials"""
        print(f"\n🔐 Testing Login Endpoint")
        print(f"URL: {BASE_URL}/auth/login")
        print(f"Credentials: {TEST_EMAIL} / {TEST_PASSWORD}")
        
        try:
            # Prepare login payload
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            # Make login request
            start_time = datetime.now()
            async with self.session.post(
                f"{BASE_URL}/auth/login",
                json=login_data
            ) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                # Get response data
                status_code = response.status
                response_text = await response.text()
                
                print(f"⏱️  Response Time: {response_time:.1f}ms")
                print(f"📊 HTTP Status: {status_code}")
                
                # Parse response if possible
                response_data = None
                try:
                    response_data = json.loads(response_text)
                    print(f"📄 Response Body: {json.dumps(response_data, indent=2)}")
                except json.JSONDecodeError:
                    print(f"📄 Response Body (raw): {response_text}")
                
                # Analyze results
                success = status_code == 200
                
                result = {
                    "test": "Login Endpoint",
                    "url": f"{BASE_URL}/auth/login",
                    "method": "POST",
                    "credentials": f"{TEST_EMAIL} / {TEST_PASSWORD}",
                    "status_code": status_code,
                    "response_time_ms": round(response_time, 1),
                    "success": success,
                    "response_data": response_data,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Check response structure if successful
                if success and response_data:
                    # Check for required fields
                    user_data = response_data.get('user', {})
                    
                    checks = {
                        "user.email": user_data.get('email'),
                        "user.role": user_data.get('role'),
                        "tenant_id": response_data.get('tenant_id') or user_data.get('tenant_id'),
                        "access_token": response_data.get('access_token')
                    }
                    
                    result["field_checks"] = checks
                    
                    print(f"\n✅ FIELD VERIFICATION:")
                    for field, value in checks.items():
                        status = "✅" if value else "❌"
                        print(f"   {status} {field}: {value}")
                
                self.test_results.append(result)
                
                if success:
                    print(f"\n✅ LOGIN SUCCESS: Demo user can login successfully")
                    return True
                else:
                    print(f"\n❌ LOGIN FAILED: HTTP {status_code}")
                    if response_data and 'detail' in response_data:
                        print(f"   Error: {response_data['detail']}")
                    return False
                    
        except Exception as e:
            print(f"\n❌ LOGIN ERROR: {str(e)}")
            error_result = {
                "test": "Login Endpoint",
                "url": f"{BASE_URL}/auth/login",
                "method": "POST",
                "credentials": f"{TEST_EMAIL} / {TEST_PASSWORD}",
                "error": str(e),
                "success": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.test_results.append(error_result)
            return False

    async def run_test(self):
        """Run the complete login test"""
        print("🏨 DEMO USER LOGIN TEST BAŞLADI")
        print("=" * 60)
        
        await self.create_session()
        
        try:
            # Test login endpoint
            login_success = await self.test_login_endpoint()
            
            # Print summary
            print("\n" + "=" * 60)
            print("📋 TEST SUMMARY")
            print("=" * 60)
            
            if login_success:
                print("✅ RESULT: Login artık başarılı!")
                print("✅ Demo kullanıcı preview ortamında giriş yapabiliyor")
            else:
                print("❌ RESULT: Login başarısız!")
                print("❌ Demo kullanıcı preview ortamında giriş yapamıyor")
            
            # Print detailed results
            print(f"\n📊 DETAILED RESULTS:")
            for result in self.test_results:
                print(f"   Test: {result['test']}")
                print(f"   Status: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")
                if 'status_code' in result:
                    print(f"   HTTP Status: {result['status_code']}")
                if 'response_time_ms' in result:
                    print(f"   Response Time: {result['response_time_ms']}ms")
                if 'error' in result:
                    print(f"   Error: {result['error']}")
                print()
            
        finally:
            await self.close_session()

async def main():
    """Main test function"""
    tester = LoginTester()
    await tester.run_test()

if __name__ == "__main__":
    asyncio.run(main())