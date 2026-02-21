#!/usr/bin/env python3
"""
Final Comprehensive Test for subscription_plan Support
Testing both creation and retrieval of subscription_plan field
"""

import asyncio
import aiohttp
import json
from datetime import datetime
import uuid

BASE_URL = "https://guest-unified.preview.emergentagent.com/api"
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

async def test_subscription_plan_comprehensive():
    """Comprehensive test of subscription_plan support"""
    print("🔧 COMPREHENSIVE SUBSCRIPTION_PLAN TEST")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # Get authentication
        token, user = await get_auth_token(session)
        
        if not token:
            print("❌ Authentication failed")
            return {"error": "Authentication failed"}
        
        print(f"✅ Authenticated as: {user.get('name')} ({user.get('role')})")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test 1: Create tenant with subscription_plan: "pms_lite"
        print(f"\n🎯 TEST 1: Creating tenant with subscription_plan: 'pms_lite'")
        print("-" * 50)
        
        test_data = {
            "property_name": f"PMS Lite Hotel {uuid.uuid4().hex[:6]}",
            "email": f"pmslite{uuid.uuid4().hex[:6]}@test.com",
            "password": "testpass123",
            "name": "PMS Lite Admin",
            "phone": "+90 555 111 2233",
            "address": "Test Address, Istanbul",
            "location": "Istanbul",
            "description": "PMS Lite subscription test",
            "subscription_plan": "pms_lite"
        }
        
        create_url = f"{BASE_URL}/admin/tenants"
        
        try:
            async with session.post(create_url, json=test_data, headers=headers) as response:
                print(f"📊 HTTP Status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    tenant_id = result.get("id") or result.get("tenant_id")
                    print(f"✅ Tenant created successfully")
                    print(f"🏨 Tenant ID: {tenant_id}")
                    
                    # Test 2: Verify tenant in admin list
                    print(f"\n🎯 TEST 2: Verifying tenant in admin list")
                    print("-" * 50)
                    
                    list_url = f"{BASE_URL}/admin/tenants"
                    async with session.get(list_url, headers=headers) as list_response:
                        if list_response.status == 200:
                            list_data = await list_response.json()
                            tenants = list_data.get("tenants", [])
                            
                            # Find our created tenant
                            created_tenant = None
                            for tenant in tenants:
                                if tenant.get("id") == tenant_id:
                                    created_tenant = tenant
                                    break
                            
                            if created_tenant:
                                subscription_plan = created_tenant.get("subscription_plan")
                                plan = created_tenant.get("plan")
                                
                                print(f"✅ Tenant found in list")
                                print(f"📋 subscription_plan field: {subscription_plan}")
                                print(f"📋 plan field: {plan}")
                                
                                # Test 3: Check if subscription_plan is exactly "pms_lite"
                                print(f"\n🎯 TEST 3: Validation Results")
                                print("-" * 50)
                                
                                subscription_plan_correct = subscription_plan == "pms_lite"
                                plan_fallback = plan == "pms_lite" if subscription_plan is None else False
                                
                                print(f"❓ subscription_plan == 'pms_lite': {subscription_plan_correct}")
                                print(f"❓ plan == 'pms_lite' (fallback): {plan_fallback}")
                                
                                # Final assessment
                                field_accepted = subscription_plan_correct or plan_fallback
                                field_stored = subscription_plan is not None or plan == "pms_lite"
                                
                                return {
                                    "success": True,
                                    "subscription_plan_accepted": True,  # No 422 error means accepted
                                    "subscription_plan_stored": field_stored,
                                    "subscription_plan_value": subscription_plan,
                                    "plan_value": plan,
                                    "correct_value_stored": field_accepted,
                                    "tenant_id": tenant_id,
                                    "validation_errors": None
                                }
                            else:
                                print(f"❌ Created tenant not found in list")
                                return {
                                    "success": True,
                                    "subscription_plan_accepted": True,
                                    "error": "Tenant not found in list after creation"
                                }
                        else:
                            print(f"❌ Failed to list tenants: HTTP {list_response.status}")
                            return {
                                "success": True,
                                "subscription_plan_accepted": True,
                                "error": "Could not verify tenant list"
                            }
                
                elif response.status == 422:
                    error_data = await response.json()
                    print(f"❌ Validation Error (422)")
                    print(f"📋 Error Details: {json.dumps(error_data, indent=2)}")
                    
                    # Check if subscription_plan caused the error
                    error_str = json.dumps(error_data).lower()
                    subscription_plan_error = "subscription_plan" in error_str
                    
                    return {
                        "success": False,
                        "subscription_plan_accepted": not subscription_plan_error,
                        "validation_errors": error_data,
                        "subscription_plan_error": subscription_plan_error
                    }
                
                else:
                    error_data = await response.text()
                    print(f"❌ HTTP {response.status}: {error_data}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {error_data}",
                        "subscription_plan_accepted": "unknown"
                    }
                    
        except Exception as e:
            print(f"❌ Request failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "subscription_plan_accepted": "unknown"
            }

async def main():
    """Main execution"""
    print("🏨 FINAL SUBSCRIPTION_PLAN VALIDATION TEST")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    result = await test_subscription_plan_comprehensive()
    
    print("\n" + "=" * 60)
    print("🎯 FINAL ASSESSMENT:")
    print("-" * 30)
    
    # Extract key findings
    accepted = result.get("subscription_plan_accepted", False)
    stored = result.get("subscription_plan_stored", False)
    correct_value = result.get("correct_value_stored", False)
    produces_422 = result.get("validation_errors") is not None
    
    print(f"❓ subscription_plan alanı backend tarafından kabul ediliyor mu?")
    if accepted is True:
        print(f"✅ EVET - subscription_plan alanı kabul ediliyor")
    elif accepted is False:
        print(f"❌ HAYIR - subscription_plan alanı kabul edilmiyor")
    else:
        print(f"❓ BİLİNMİYOR - Test tamamlanamadı")
    
    print(f"❓ 422 validation hatası üretiyor mu?")
    if produces_422:
        print(f"❌ EVET - subscription_plan için 422 hatası üretiyor")
    else:
        print(f"✅ HAYIR - subscription_plan için 422 hatası üretmiyor")
    
    if stored:
        print(f"✅ subscription_plan değeri veritabanında saklanıyor")
        if correct_value:
            print(f"✅ 'pms_lite' değeri doğru şekilde saklandı")
        else:
            print(f"⚠️  Değer saklandı ama 'pms_lite' olarak değil")
    else:
        print(f"⚠️  subscription_plan değeri saklanma durumu belirsiz")
    
    print(f"\n📊 Detaylı Sonuç:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result

if __name__ == "__main__":
    asyncio.run(main())