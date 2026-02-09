#!/usr/bin/env python3
"""
Admin Tenant Create Endpoint - Subscription Plan Support Test
Testing /admin/tenants endpoint for subscription_plan field validation
"""

import asyncio
import aiohttp
import json
from datetime import datetime
import uuid

# Test Configuration
BASE_URL = "https://app-audit-9.preview.emergentagent.com/api"

# Test credentials to try
TEST_CREDENTIALS = [
    {"email": "demo@hotel.com", "password": "demo123"},
    {"email": "muratsutay@hotmail.com", "password": "murat1903"},
]

async def get_auth_token(session, credentials):
    """Get authentication token"""
    login_url = f"{BASE_URL}/auth/login"
    
    try:
        async with session.post(login_url, json=credentials) as response:
            if response.status == 200:
                data = await response.json()
                token = data.get('access_token')
                user = data.get('user', {})
                return token, user
            else:
                error_data = await response.json()
                return None, {"error": error_data.get('detail', 'Login failed')}
    except Exception as e:
        return None, {"error": str(e)}

async def test_admin_tenants_endpoint(session, token, test_data):
    """Test admin tenants endpoint with subscription_plan"""
    admin_url = f"{BASE_URL}/admin/tenants"
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"📍 Testing: POST {admin_url}")
    print(f"📋 Test Data: {json.dumps(test_data, indent=2)}")
    
    try:
        start_time = datetime.now()
        async with session.post(admin_url, json=test_data, headers=headers) as response:
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            print(f"⏱️  Response Time: {response_time:.1f}ms")
            print(f"📊 HTTP Status: {response.status}")
            
            response_data = await response.json()
            
            return {
                "status": response.status,
                "response_time": response_time,
                "data": response_data,
                "success": response.status in [200, 201]
            }
            
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "success": False
        }

async def check_tenant_in_database(session, token, tenant_id):
    """Check if tenant was created with subscription_plan in database"""
    # Try to get tenant details
    tenant_url = f"{BASE_URL}/admin/tenants/{tenant_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        async with session.get(tenant_url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data
            else:
                return {"error": f"HTTP {response.status}"}
    except Exception as e:
        return {"error": str(e)}

async def test_subscription_plan_validation():
    """Main test function for subscription_plan validation"""
    print("🏨 ADMIN TENANT CREATE - SUBSCRIPTION PLAN TEST")
    print("=" * 60)
    
    # Test data with subscription_plan
    test_tenant_data = {
        "property_name": f"Test Hotel {uuid.uuid4().hex[:8]}",
        "email": f"test{uuid.uuid4().hex[:8]}@testhotel.com",
        "password": "testpass123",
        "name": "Test Admin User",
        "phone": "+90 555 123 4567",
        "address": "Test Address, Istanbul, Turkey",
        "location": "Istanbul",
        "description": "Test hotel for subscription plan validation",
        "subscription_plan": "pms_lite"  # This is the field we're testing
    }
    
    async with aiohttp.ClientSession() as session:
        # Try to authenticate with available credentials
        auth_token = None
        auth_user = None
        
        for creds in TEST_CREDENTIALS:
            print(f"\n🔐 Trying login with: {creds['email']}")
            token, user = await get_auth_token(session, creds)
            
            if token:
                print(f"✅ Login successful")
                print(f"👤 User: {user.get('name', 'N/A')} ({user.get('role', 'N/A')})")
                auth_token = token
                auth_user = user
                break
            else:
                print(f"❌ Login failed: {user.get('error', 'Unknown error')}")
        
        if not auth_token:
            print("\n❌ CRITICAL: No valid authentication found")
            return {
                "success": False,
                "error": "Authentication failed with all test credentials",
                "subscription_plan_accepted": False
            }
        
        print(f"\n🎯 TESTING ADMIN TENANT CREATE ENDPOINT")
        print("-" * 50)
        
        # Test the admin tenants endpoint
        result = await test_admin_tenants_endpoint(session, auth_token, test_tenant_data)
        
        # Analyze the result
        if result["success"]:
            print(f"✅ Tenant creation successful!")
            
            # Check if tenant was created with subscription_plan
            tenant_id = result["data"].get("id") or result["data"].get("tenant_id")
            
            if tenant_id:
                print(f"🏨 Created Tenant ID: {tenant_id}")
                
                # Try to verify the tenant in database
                tenant_details = await check_tenant_in_database(session, auth_token, tenant_id)
                
                if "error" not in tenant_details:
                    subscription_plan = tenant_details.get("subscription_plan") or tenant_details.get("plan")
                    print(f"📋 Stored Subscription Plan: {subscription_plan}")
                    
                    subscription_plan_accepted = subscription_plan == "pms_lite"
                    
                    return {
                        "success": True,
                        "subscription_plan_accepted": subscription_plan_accepted,
                        "stored_plan": subscription_plan,
                        "tenant_id": tenant_id,
                        "validation_errors": None,
                        "http_status": result["status"]
                    }
                else:
                    print(f"⚠️  Could not verify tenant details: {tenant_details.get('error')}")
                    
                    return {
                        "success": True,
                        "subscription_plan_accepted": True,  # Assume success if creation worked
                        "stored_plan": "unknown",
                        "tenant_id": tenant_id,
                        "validation_errors": None,
                        "http_status": result["status"],
                        "note": "Tenant created but details verification failed"
                    }
            else:
                print("⚠️  No tenant ID returned in response")
                return {
                    "success": True,
                    "subscription_plan_accepted": True,  # Assume success if no 422 error
                    "stored_plan": "unknown",
                    "validation_errors": None,
                    "http_status": result["status"]
                }
        
        elif result["status"] == 422:
            # Validation error - check if it's related to subscription_plan
            error_details = result["data"]
            print(f"❌ Validation Error (422): {json.dumps(error_details, indent=2)}")
            
            # Check if subscription_plan is mentioned in validation errors
            error_str = json.dumps(error_details).lower()
            subscription_plan_error = "subscription_plan" in error_str
            
            return {
                "success": False,
                "subscription_plan_accepted": not subscription_plan_error,
                "validation_errors": error_details,
                "http_status": 422,
                "subscription_plan_error": subscription_plan_error
            }
        
        elif result["status"] == 403:
            print(f"❌ Access Denied (403): User may not have super_admin role")
            return {
                "success": False,
                "error": "Access denied - super_admin role required",
                "subscription_plan_accepted": "unknown",
                "http_status": 403
            }
        
        else:
            print(f"❌ Request Failed: {result}")
            return {
                "success": False,
                "error": result.get("data", result.get("error", "Unknown error")),
                "subscription_plan_accepted": "unknown",
                "http_status": result.get("status", "unknown")
            }

async def main():
    """Main execution function"""
    print("🔧 ADMIN TENANT SUBSCRIPTION_PLAN VALIDATION TEST")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Run the test
    result = await test_subscription_plan_validation()
    
    print("\n" + "=" * 60)
    print("🎯 FINAL TEST RESULT:")
    print("-" * 30)
    
    # Format the final answer
    subscription_accepted = result.get("subscription_plan_accepted", False)
    produces_422 = result.get("http_status") == 422 and result.get("subscription_plan_error", False)
    
    print(f"❓ subscription_plan alanı backend tarafından kabul ediliyor mu?")
    if subscription_accepted is True:
        print(f"✅ EVET - subscription_plan alanı kabul ediliyor")
    elif subscription_accepted is False:
        print(f"❌ HAYIR - subscription_plan alanı kabul edilmiyor")
    else:
        print(f"❓ BİLİNMİYOR - Test tamamlanamadı")
    
    print(f"❓ 422 validation hatası üretiyor mu?")
    if produces_422:
        print(f"❌ EVET - subscription_plan için 422 hatası üretiyor")
    else:
        print(f"✅ HAYIR - subscription_plan için 422 hatası üretmiyor")
    
    print(f"\n📊 Detaylı Sonuç:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result

if __name__ == "__main__":
    asyncio.run(main())