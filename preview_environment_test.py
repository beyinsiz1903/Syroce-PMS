#!/usr/bin/env python3
"""
Preview Environment Health Check and Auth Test
Tests connectivity and auth login endpoint
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Test Configuration
BASE_URL = "https://ai-feature-test.preview.emergentagent.com"
API_BASE_URL = f"{BASE_URL}/api"

async def test_connectivity():
    """Test basic connectivity to the preview environment"""
    print("🌐 CONNECTIVITY TEST")
    print("=" * 50)
    
    endpoints_to_test = [
        ("Landing Page", BASE_URL),
        ("API Health", f"{API_BASE_URL}/health"),
        ("API Health (alt)", f"{API_BASE_URL}/health/"),
    ]
    
    results = []
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        for name, url in endpoints_to_test:
            try:
                start_time = time.time()
                async with session.get(url) as response:
                    response_time = (time.time() - start_time) * 1000
                    status = response.status
                    content_type = response.headers.get('content-type', 'N/A')
                    
                    print(f"{name}: HTTP {status} ({response_time:.1f}ms) - {content_type}")
                    results.append((name, status, response_time))
                    
                    if status == 200:
                        try:
                            text = await response.text()
                            if len(text) < 200:
                                print(f"  Response: {text}")
                        except:
                            pass
                    
            except asyncio.TimeoutError:
                print(f"{name}: TIMEOUT")
                results.append((name, "TIMEOUT", 0))
            except Exception as e:
                print(f"{name}: ERROR - {e}")
                results.append((name, "ERROR", 0))
    
    print()
    return results

async def test_auth_login():
    """Test the auth login endpoint"""
    print("🔐 AUTH LOGIN TEST")
    print("=" * 50)
    
    login_url = f"{API_BASE_URL}/auth/login"
    credentials = {
        "email": "demo@hotel.com",
        "password": "demo123"
    }
    
    print(f"URL: {login_url}")
    print(f"Credentials: {credentials['email']} / {credentials['password']}")
    print()
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        try:
            start_time = time.time()
            
            async with session.post(
                login_url,
                json=credentials,
                headers={"Content-Type": "application/json"}
            ) as response:
                response_time = (time.time() - start_time) * 1000
                status_code = response.status
                content_type = response.headers.get('content-type', 'N/A')
                response_text = await response.text()
                
                print(f"📊 RESPONSE:")
                print(f"  Status: HTTP {status_code}")
                print(f"  Time: {response_time:.1f}ms")
                print(f"  Content-Type: {content_type}")
                print()
                
                # Try to parse response
                try:
                    if response_text:
                        response_data = json.loads(response_text)
                        print(f"📋 RESPONSE BODY:")
                        print(json.dumps(response_data, indent=2, ensure_ascii=False))
                        
                        if status_code == 200:
                            print("\n✅ LOGIN SUCCESSFUL")
                            
                            # Extract key info
                            user = response_data.get('user', {})
                            tenant = response_data.get('tenant', {})
                            
                            print(f"\n👤 USER INFO:")
                            print(f"  Email: {user.get('email', 'N/A')}")
                            print(f"  Role: {user.get('role', 'N/A')}")
                            
                            print(f"\n🏨 TENANT INFO:")
                            print(f"  Subscription Plan: {tenant.get('subscription_plan', 'N/A')}")
                            
                            return True
                        else:
                            print(f"\n❌ LOGIN FAILED: HTTP {status_code}")
                            return False
                    else:
                        print("📋 EMPTY RESPONSE")
                        return False
                        
                except json.JSONDecodeError:
                    print(f"📋 RAW RESPONSE (Non-JSON):")
                    print(f"  {response_text}")
                    return False
                    
        except asyncio.TimeoutError:
            print("❌ REQUEST TIMEOUT")
            return False
        except Exception as e:
            print(f"❌ REQUEST ERROR: {e}")
            return False

async def main():
    """Main test function"""
    print("🏨 PREVIEW ENVIRONMENT TEST")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()
    
    # Test connectivity first
    connectivity_results = await test_connectivity()
    print()
    
    # Test auth login
    login_success = await test_auth_login()
    print()
    
    # Summary
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    # Check if any connectivity test passed
    connectivity_ok = any(result[1] == 200 for result in connectivity_results)
    
    if connectivity_ok:
        print("✅ Connectivity: OK")
    else:
        print("❌ Connectivity: FAILED")
    
    if login_success:
        print("✅ Auth Login: SUCCESS")
        print("\n🎉 RESULT: Login akışı tekrar başarılı!")
    else:
        print("❌ Auth Login: FAILED")
        print("\n💥 RESULT: Login akışı hala başarısız!")
    
    return login_success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)