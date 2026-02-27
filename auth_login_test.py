#!/usr/bin/env python3
"""
Auth Login Test for Preview Environment
Tests the /auth/login endpoint with demo@hotel.com credentials
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Test Configuration
BASE_URL = "https://appstore-preview-1.preview.emergentagent.com/api"
LOGIN_ENDPOINT = f"{BASE_URL}/auth/login"

# Test Credentials
TEST_CREDENTIALS = {
    "email": "demo@hotel.com",
    "password": "demo123"
}

async def test_auth_login():
    """Test the auth login endpoint with demo credentials"""
    print("🔐 AUTH LOGIN TEST - Preview Environment")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Endpoint: {LOGIN_ENDPOINT}")
    print(f"Credentials: {TEST_CREDENTIALS['email']} / {TEST_CREDENTIALS['password']}")
    print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            # Record start time
            start_time = time.time()
            
            # Make login request
            async with session.post(
                LOGIN_ENDPOINT,
                json=TEST_CREDENTIALS,
                headers={"Content-Type": "application/json"}
            ) as response:
                # Record response time
                response_time = (time.time() - start_time) * 1000
                
                # Get response data
                status_code = response.status
                response_text = await response.text()
                
                print(f"📊 RESPONSE DETAILS:")
                print(f"HTTP Status: {status_code}")
                print(f"Response Time: {response_time:.1f}ms")
                print(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
                print()
                
                # Try to parse JSON response
                try:
                    response_data = json.loads(response_text)
                    print(f"📋 RESPONSE BODY:")
                    print(json.dumps(response_data, indent=2, ensure_ascii=False))
                    print()
                    
                    # Analyze response based on status
                    if status_code == 200:
                        print("✅ LOGIN SUCCESSFUL")
                        
                        # Extract key information
                        user = response_data.get('user', {})
                        tenant = response_data.get('tenant', {})
                        
                        print(f"👤 USER INFO:")
                        print(f"  Email: {user.get('email', 'N/A')}")
                        print(f"  Name: {user.get('name', 'N/A')}")
                        print(f"  Role: {user.get('role', 'N/A')}")
                        print(f"  Tenant ID: {user.get('tenant_id', 'N/A')}")
                        print()
                        
                        print(f"🏨 TENANT INFO:")
                        print(f"  Property Name: {tenant.get('property_name', 'N/A')}")
                        print(f"  Subscription Plan: {tenant.get('subscription_plan', 'N/A')}")
                        print(f"  Plan: {tenant.get('plan', 'N/A')}")
                        print(f"  Subscription Tier: {tenant.get('subscription_tier', 'N/A')}")
                        print()
                        
                        print(f"🔑 TOKEN INFO:")
                        token = response_data.get('access_token', '')
                        if token:
                            print(f"  Token Length: {len(token)} characters")
                            print(f"  Token Preview: {token[:20]}...{token[-10:] if len(token) > 30 else token[20:]}")
                        else:
                            print("  No access token found")
                        
                    elif status_code == 401:
                        print("❌ LOGIN FAILED - Invalid Credentials")
                        error_detail = response_data.get('detail', 'No error detail provided')
                        print(f"Error: {error_detail}")
                        
                    else:
                        print(f"⚠️ UNEXPECTED STATUS CODE: {status_code}")
                        error_detail = response_data.get('detail', 'No error detail provided')
                        print(f"Error: {error_detail}")
                        
                except json.JSONDecodeError:
                    print(f"❌ INVALID JSON RESPONSE:")
                    print(f"Raw Response: {response_text}")
                
                print()
                print("=" * 60)
                
                # Summary
                if status_code == 200:
                    print("🎉 RESULT: Login akışı başarılı - Authentication working!")
                else:
                    print("💥 RESULT: Login akışı başarısız - Authentication broken!")
                
                return status_code == 200
                
        except aiohttp.ClientError as e:
            print(f"❌ CONNECTION ERROR: {e}")
            return False
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR: {e}")
            return False

async def main():
    """Main test function"""
    success = await test_auth_login()
    
    if success:
        print("\n✅ Test completed successfully")
        exit(0)
    else:
        print("\n❌ Test failed")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())