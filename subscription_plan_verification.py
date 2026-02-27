#!/usr/bin/env python3
"""
Database Verification Test for subscription_plan field
Direct MongoDB query to verify subscription_plan storage
"""

import asyncio
import aiohttp
import json
from datetime import datetime

# Test Configuration
BASE_URL = "https://guest-messaging-1.preview.emergentagent.com/api"
TEST_CREDENTIALS = {"email": "demo@hotel.com", "password": "demo123"}

async def get_auth_token(session):
    """Get authentication token"""
    login_url = f"{BASE_URL}/auth/login"
    
    try:
        async with session.post(login_url, json=TEST_CREDENTIALS) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('access_token'), data.get('user', {})
            else:
                return None, None
    except Exception as e:
        return None, None

async def test_tenant_list_with_subscription_plan():
    """Test tenant listing to see subscription_plan field"""
    print("🔍 DATABASE VERIFICATION - SUBSCRIPTION_PLAN FIELD")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # Get authentication
        token, user = await get_auth_token(session)
        
        if not token:
            print("❌ Authentication failed")
            return {"error": "Authentication failed"}
        
        print(f"✅ Authenticated as: {user.get('name')} ({user.get('role')})")
        
        # Try to list tenants to see the structure
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test different endpoints that might show tenant data
        endpoints_to_test = [
            "/admin/tenants",
            "/tenants",
            "/auth/me",  # This might include tenant info
        ]
        
        results = {}
        
        for endpoint in endpoints_to_test:
            url = f"{BASE_URL}{endpoint}"
            print(f"\n📍 Testing: GET {url}")
            
            try:
                async with session.get(url, headers=headers) as response:
                    print(f"📊 HTTP Status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Look for subscription_plan in the response
                        data_str = json.dumps(data)
                        has_subscription_plan = "subscription_plan" in data_str
                        
                        print(f"🔍 Contains 'subscription_plan': {has_subscription_plan}")
                        
                        if has_subscription_plan:
                            print("✅ Found subscription_plan field in response!")
                            
                            # Try to extract and show subscription_plan values
                            if isinstance(data, dict):
                                if "subscription_plan" in data:
                                    print(f"📋 Direct subscription_plan: {data['subscription_plan']}")
                                
                                # Check if it's a list of tenants
                                if "tenants" in data:
                                    tenants = data["tenants"]
                                    if isinstance(tenants, list) and tenants:
                                        print(f"🏨 Found {len(tenants)} tenants")
                                        for i, tenant in enumerate(tenants[:3]):  # Show first 3
                                            plan = tenant.get("subscription_plan") or tenant.get("plan", "N/A")
                                            print(f"   {i+1}. {tenant.get('property_name', 'N/A')}: {plan}")
                                
                                # Check if it's user data with tenant
                                if "tenant" in data:
                                    tenant = data["tenant"]
                                    plan = tenant.get("subscription_plan") or tenant.get("plan", "N/A")
                                    print(f"🏨 User's tenant plan: {plan}")
                        
                        results[endpoint] = {
                            "status": response.status,
                            "has_subscription_plan": has_subscription_plan,
                            "data_sample": str(data)[:500] + "..." if len(str(data)) > 500 else str(data)
                        }
                    
                    elif response.status == 403:
                        print("❌ Access denied (403)")
                        results[endpoint] = {"status": 403, "error": "Access denied"}
                    
                    elif response.status == 404:
                        print("❌ Not found (404)")
                        results[endpoint] = {"status": 404, "error": "Not found"}
                    
                    else:
                        error_data = await response.text()
                        print(f"❌ HTTP {response.status}: {error_data[:200]}")
                        results[endpoint] = {"status": response.status, "error": error_data[:200]}
                        
            except Exception as e:
                print(f"❌ Request failed: {str(e)}")
                results[endpoint] = {"error": str(e)}
        
        return results

async def test_specific_tenant_query():
    """Test querying a specific tenant that we know has subscription_plan"""
    print("\n🎯 SPECIFIC TENANT QUERY TEST")
    print("-" * 40)
    
    async with aiohttp.ClientSession() as session:
        token, user = await get_auth_token(session)
        
        if not token:
            return {"error": "Authentication failed"}
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get current user's tenant info (this should include subscription_plan)
        me_url = f"{BASE_URL}/auth/me"
        
        try:
            async with session.get(me_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract tenant information
                    tenant = data.get("tenant", {})
                    user_info = data.get("user", {})
                    
                    print(f"👤 User: {user_info.get('name')} ({user_info.get('role')})")
                    print(f"🏨 Tenant: {tenant.get('property_name', 'N/A')}")
                    
                    # Check for subscription_plan field
                    subscription_plan = tenant.get("subscription_plan")
                    plan = tenant.get("plan")
                    
                    print(f"📋 subscription_plan field: {subscription_plan}")
                    print(f"📋 plan field: {plan}")
                    
                    # Determine the effective plan
                    effective_plan = subscription_plan or plan or "N/A"
                    print(f"🎯 Effective Plan: {effective_plan}")
                    
                    return {
                        "subscription_plan": subscription_plan,
                        "plan": plan,
                        "effective_plan": effective_plan,
                        "tenant_id": tenant.get("id"),
                        "property_name": tenant.get("property_name")
                    }
                else:
                    error_data = await response.text()
                    return {"error": f"HTTP {response.status}: {error_data}"}
                    
        except Exception as e:
            return {"error": str(e)}

async def main():
    """Main execution"""
    print("🔍 SUBSCRIPTION_PLAN DATABASE VERIFICATION")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test endpoint access
    endpoint_results = await test_tenant_list_with_subscription_plan()
    
    # Test specific tenant query
    tenant_result = await test_specific_tenant_query()
    
    print("\n" + "=" * 60)
    print("🎯 VERIFICATION SUMMARY:")
    print("-" * 30)
    
    # Analyze results
    subscription_plan_found = False
    
    for endpoint, result in endpoint_results.items():
        if result.get("has_subscription_plan"):
            subscription_plan_found = True
            print(f"✅ {endpoint}: subscription_plan field found")
        elif result.get("status") == 200:
            print(f"⚠️  {endpoint}: No subscription_plan field")
        else:
            print(f"❌ {endpoint}: {result.get('error', 'Failed')}")
    
    # Check tenant-specific result
    if tenant_result.get("subscription_plan") is not None:
        print(f"✅ Current tenant has subscription_plan: {tenant_result['subscription_plan']}")
        subscription_plan_found = True
    elif tenant_result.get("plan") is not None:
        print(f"⚠️  Current tenant has plan field: {tenant_result['plan']}")
    
    print(f"\n🎯 FINAL VERIFICATION:")
    if subscription_plan_found:
        print("✅ subscription_plan field is supported and stored in database")
    else:
        print("⚠️  subscription_plan field support unclear - may use 'plan' field instead")
    
    return {
        "subscription_plan_supported": subscription_plan_found,
        "endpoint_results": endpoint_results,
        "tenant_result": tenant_result
    }

if __name__ == "__main__":
    asyncio.run(main())