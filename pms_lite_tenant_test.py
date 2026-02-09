#!/usr/bin/env python3
"""
PMS Lite Tenant Login Response Validation Test
Testing subscription_plan and features fields for PMS Lite tenant
"""

import asyncio
import aiohttp
import json
from datetime import datetime

# Test Configuration
BASE_URL = "https://app-audit-9.preview.emergentagent.com/api"

# Test credentials to try
TEST_CREDENTIALS = [
    {"email": "demo@hotel.com", "password": "demo123"},
    {"email": "muratsutay@hotmail.com", "password": "murat1903"},
    {"email": "test@test.com", "password": "test123"},
    {"email": "demo@demo.com", "password": "demo123"},
    {"email": "patron@hotel.com", "password": "patron123"},
    {"email": "admin@hoteltest.com", "password": "admin123"}
]

# PMS Lite tenant creation data
PMS_LITE_TENANT_DATA = {
    "property_name": "PMS Lite Hotel E2E",
    "email": "pmslite-e2e@testhotel.com",
    "password": "testpass123",
    "name": "PMS Lite Admin",
    "phone": "+90 555 000 0000",
    "address": "Test Address, Istanbul",
    "location": "Istanbul",
    "description": "E2E PMS Lite tenant",
    "subscription_plan": "pms_lite"
}

async def test_admin_tenant_creation(session):
    """Try to create a PMS Lite tenant via admin endpoint"""
    print("\n🔧 ATTEMPTING ADMIN TENANT CREATION")
    print("-" * 50)
    
    # First try to login with potential admin credentials
    admin_token = None
    for creds in TEST_CREDENTIALS:
        try:
            login_url = f"{BASE_URL}/auth/login"
            async with session.post(login_url, json=creds) as response:
                if response.status == 200:
                    data = await response.json()
                    user = data.get('user', {})
                    if user.get('role') in ['super_admin', 'admin']:
                        admin_token = data.get('access_token')
                        print(f"✅ Admin login successful: {creds['email']} (role: {user.get('role')})")
                        break
        except Exception as e:
            continue
    
    if not admin_token:
        print("❌ No admin credentials found - cannot create tenant")
        return None
    
    # Try to create PMS Lite tenant
    try:
        create_url = f"{BASE_URL}/admin/tenants"
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        print(f"📍 Creating tenant: POST {create_url}")
        print(f"📋 Tenant data: {PMS_LITE_TENANT_DATA['property_name']} (plan: {PMS_LITE_TENANT_DATA['subscription_plan']})")
        
        async with session.post(create_url, json=PMS_LITE_TENANT_DATA, headers=headers) as response:
            print(f"📊 HTTP Status: {response.status}")
            
            if response.status in [200, 201]:
                data = await response.json()
                print(f"✅ Tenant created successfully")
                print(f"🏨 Tenant ID: {data.get('tenant_id', 'N/A')}")
                return {
                    "email": PMS_LITE_TENANT_DATA['email'],
                    "password": PMS_LITE_TENANT_DATA['password'],
                    "tenant_id": data.get('tenant_id')
                }
            else:
                error_text = await response.text()
                print(f"❌ Tenant creation failed: {error_text}")
                return None
                
    except Exception as e:
        print(f"❌ Tenant creation error: {str(e)}")
        return None

async def test_login_response(session, credentials):
    """Test login and analyze response structure"""
    print(f"\n🔐 TESTING LOGIN: {credentials['email']}")
    print("-" * 50)
    
    try:
        login_url = f"{BASE_URL}/auth/login"
        
        start_time = datetime.now()
        async with session.post(login_url, json=credentials) as response:
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            print(f"⏱️  Response Time: {response_time:.1f}ms")
            print(f"📊 HTTP Status: {response.status}")
            
            if response.status == 200:
                data = await response.json()
                
                # Extract tenant information
                tenant = data.get('tenant', {})
                user = data.get('user', {})
                
                subscription_plan = tenant.get('subscription_plan')
                plan = tenant.get('plan')
                features = tenant.get('features', {})
                
                print(f"✅ Login Successful")
                print(f"👤 User: {user.get('name', 'N/A')} ({user.get('role', 'N/A')})")
                print(f"🏨 Tenant ID: {tenant.get('id', 'N/A')}")
                print(f"🏢 Property Name: {tenant.get('property_name', 'N/A')}")
                print(f"📋 Subscription Plan: {subscription_plan}")
                print(f"📋 Plan (fallback): {plan}")
                
                # Check for PMS Lite specific features
                pms_lite_features = {
                    "dashboard": features.get("dashboard"),
                    "pms": features.get("pms"),
                    "reservation_calendar": features.get("reservation_calendar"),
                    "reports_lite": features.get("reports_lite"),
                    "settings_lite": features.get("settings_lite")
                }
                
                print(f"\n📋 PMS LITE FEATURES ANALYSIS:")
                print("-" * 40)
                
                has_features = bool(features)
                print(f"Features field present: {has_features}")
                print(f"Total features count: {len(features)}")
                
                if pms_lite_features:
                    print("\nPMS Lite specific features:")
                    for key, value in pms_lite_features.items():
                        status = "✅" if value else "❌" if value is False else "❓"
                        print(f"  {key}: {value} {status}")
                
                # Create summary response
                summary = {
                    "plan": subscription_plan or plan,
                    "hasFeatures": has_features,
                    "sampleFeatures": pms_lite_features if any(v is not None for v in pms_lite_features.values()) else dict(list(features.items())[:5])
                }
                
                return {
                    "success": True,
                    "credentials": credentials['email'],
                    "summary": summary,
                    "full_tenant": tenant
                }
                
            elif response.status == 401:
                error_data = await response.json()
                print(f"❌ Authentication Failed: {error_data.get('detail', 'Invalid credentials')}")
                return {
                    "success": False,
                    "credentials": credentials['email'],
                    "error": "Invalid credentials"
                }
            else:
                error_text = await response.text()
                print(f"❌ HTTP {response.status}: {error_text}")
                return {
                    "success": False,
                    "credentials": credentials['email'],
                    "error": f"HTTP {response.status}"
                }
                
    except Exception as e:
        print(f"❌ Request Failed: {str(e)}")
        return {
            "success": False,
            "credentials": credentials['email'],
            "error": str(e)
        }

async def main():
    """Main test execution"""
    print("🏨 PMS LITE TENANT LOGIN RESPONSE VALIDATION")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = []
    
    async with aiohttp.ClientSession() as session:
        # Step 1: Try to create PMS Lite tenant
        new_tenant = await test_admin_tenant_creation(session)
        
        # Step 2: Test login with all available credentials
        test_creds = TEST_CREDENTIALS.copy()
        if new_tenant:
            test_creds.insert(0, {"email": new_tenant["email"], "password": new_tenant["password"]})
        
        print(f"\n🔍 TESTING {len(test_creds)} CREDENTIAL SETS")
        print("=" * 60)
        
        for creds in test_creds:
            result = await test_login_response(session, creds)
            results.append(result)
            
            # If we found a successful login, analyze it in detail
            if result.get("success"):
                print(f"\n🎯 DETAILED ANALYSIS FOR: {creds['email']}")
                print("-" * 50)
                
                tenant = result.get("full_tenant", {})
                summary = result.get("summary", {})
                
                print(f"Subscription Plan Field: {'✅ Present' if tenant.get('subscription_plan') is not None else '❌ Missing'}")
                print(f"Subscription Plan Value: {tenant.get('subscription_plan', 'N/A')}")
                print(f"Plan Field (fallback): {tenant.get('plan', 'N/A')}")
                print(f"Features Field: {'✅ Present' if tenant.get('features') else '❌ Missing'}")
                
                features = tenant.get('features', {})
                if features:
                    print(f"Features Type: {type(features).__name__}")
                    print(f"Features Count: {len(features)}")
                    
                    # Check if it's PMS Lite
                    plan_value = tenant.get('subscription_plan') or tenant.get('plan')
                    if plan_value == 'pms_lite':
                        print(f"\n🎉 PMS LITE TENANT FOUND!")
                        print("PMS Lite Features Validation:")
                        
                        expected_keys = ["dashboard", "pms", "reservation_calendar", "reports_lite", "settings_lite"]
                        for key in expected_keys:
                            value = features.get(key)
                            if value is not None:
                                print(f"  ✅ {key}: {value} (boolean: {isinstance(value, bool)})")
                            else:
                                print(f"  ❌ {key}: Missing")
                
                break  # Stop after first successful login for detailed analysis
    
    # Final Summary
    print("\n" + "=" * 60)
    print("🎯 FINAL SUMMARY")
    print("=" * 60)
    
    successful_logins = [r for r in results if r.get("success")]
    failed_logins = [r for r in results if not r.get("success")]
    
    print(f"Total Credentials Tested: {len(results)}")
    print(f"Successful Logins: {len(successful_logins)}")
    print(f"Failed Logins: {len(failed_logins)}")
    
    if successful_logins:
        best_result = successful_logins[0]
        final_summary = best_result.get("summary", {})
        
        print(f"\n📋 LOGIN RESPONSE STRUCTURE VALIDATION:")
        print(f"Plan: {final_summary.get('plan', 'N/A')}")
        print(f"Has Features: {final_summary.get('hasFeatures', False)}")
        print(f"Sample Features: {json.dumps(final_summary.get('sampleFeatures', {}), indent=2)}")
        
        return final_summary
    else:
        print("\n❌ NO SUCCESSFUL LOGINS - CANNOT VALIDATE RESPONSE STRUCTURE")
        return {
            "plan": "N/A",
            "hasFeatures": False,
            "error": "No successful authentication"
        }

if __name__ == "__main__":
    asyncio.run(main())