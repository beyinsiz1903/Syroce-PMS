#!/usr/bin/env python3
"""
Auth Login Flow Test - Turkish Request
Testing POST /auth/login endpoint for preview backend status
"""

import asyncio
import aiohttp
import json
from datetime import datetime

# Test Configuration
BASE_URL = "https://unitcare-1.preview.emergentagent.com/api"
TEST_CREDENTIALS = {
    "email": "demo@hotel.com",
    "password": "demo123"
}

async def test_auth_login():
    """Test auth login endpoint as requested in Turkish"""
    print("🔐 AUTH LOGIN AKIŞI TEST - PREVIEW BACKEND DURUMU")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        try:
            # Test login endpoint
            login_url = f"{BASE_URL}/auth/login"
            print(f"📍 Test Edilen Endpoint: POST {login_url}")
            print(f"📧 Kimlik Bilgileri: {TEST_CREDENTIALS['email']} / {TEST_CREDENTIALS['password']}")
            print()
            
            start_time = datetime.now()
            async with session.post(login_url, json=TEST_CREDENTIALS) as response:
                end_time = datetime.now()
                response_time = (end_time - start_time).total_seconds() * 1000
                
                print(f"⏱️  Yanıt Süresi: {response_time:.1f}ms")
                print(f"📊 HTTP Status: {response.status}")
                print()
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract requested fields
                    user = data.get('user', {})
                    tenant = data.get('tenant', {})
                    
                    user_email = user.get('email', 'N/A')
                    user_role = user.get('role', 'N/A')
                    tenant_subscription_plan = tenant.get('subscription_plan') or tenant.get('plan', 'N/A')
                    
                    print("✅ LOGIN BAŞARILI!")
                    print("=" * 40)
                    print("📋 İSTENEN ALANLAR:")
                    print(f"   user.email: {user_email}")
                    print(f"   user.role: {user_role}")
                    print(f"   tenant.subscription_plan: {tenant_subscription_plan}")
                    print()
                    
                    # Additional context
                    print("📋 EK BİLGİLER:")
                    print(f"   user.name: {user.get('name', 'N/A')}")
                    print(f"   user.tenant_id: {user.get('tenant_id', 'N/A')}")
                    print(f"   tenant.id: {tenant.get('id', 'N/A')}")
                    print(f"   tenant.property_name: {tenant.get('property_name', 'N/A')}")
                    print()
                    
                    # Create result summary
                    result = {
                        "status": "success",
                        "http_status": response.status,
                        "response_time_ms": round(response_time, 1),
                        "user": {
                            "email": user_email,
                            "role": user_role,
                            "name": user.get('name'),
                            "tenant_id": user.get('tenant_id')
                        },
                        "tenant": {
                            "subscription_plan": tenant_subscription_plan,
                            "id": tenant.get('id'),
                            "property_name": tenant.get('property_name')
                        }
                    }
                    
                    print("🎯 SONUÇ ÖZETİ:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    
                    return result
                        
                elif response.status == 401:
                    try:
                        error_data = await response.json()
                        error_detail = error_data.get('detail', 'Invalid credentials')
                    except:
                        error_detail = 'Authentication failed'
                    
                    print("❌ KİMLİK DOĞRULAMA HATASI!")
                    print(f"   Hata: {error_detail}")
                    print()
                    
                    result = {
                        "status": "failed",
                        "http_status": response.status,
                        "response_time_ms": round(response_time, 1),
                        "error": "Authentication failed",
                        "detail": error_detail
                    }
                    
                    print("🎯 HATA ÖZETİ:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    
                    return result
                    
                else:
                    try:
                        error_text = await response.text()
                    except:
                        error_text = f"HTTP {response.status} error"
                    
                    print(f"❌ HTTP HATASI: {response.status}")
                    print(f"   Detay: {error_text}")
                    print()
                    
                    result = {
                        "status": "failed",
                        "http_status": response.status,
                        "response_time_ms": round(response_time, 1),
                        "error": f"HTTP {response.status}",
                        "detail": error_text
                    }
                    
                    print("🎯 HATA ÖZETİ:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    
                    return result
                    
        except Exception as e:
            print(f"❌ İSTEK HATASI: {str(e)}")
            print()
            
            result = {
                "status": "failed",
                "http_status": None,
                "response_time_ms": None,
                "error": "Request failed",
                "detail": str(e)
            }
            
            print("🎯 HATA ÖZETİ:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            return result

async def main():
    """Main test execution"""
    print("🏨 HOTEL PMS AUTH LOGIN TEST - PREVIEW BACKEND DURUMU")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"📅 Test Tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("🎯 HEDEF: Preview backend tekrar ayakta mı, login başarılı mı?")
    print("📋 Döndürülecek Alanlar:")
    print("   - HTTP status")
    print("   - user.email")
    print("   - user.role") 
    print("   - tenant.subscription_plan")
    print()
    
    # Run the test
    result = await test_auth_login()
    
    print("\n" + "=" * 60)
    print("🎯 FİNAL SONUÇ:")
    
    if result.get("status") == "success":
        print("✅ PREVIEW BACKEND ÇALIŞIYOR!")
        print("✅ LOGIN BAŞARILI!")
        print()
        print("📊 Döndürülen Değerler:")
        print(f"   HTTP Status: {result.get('http_status')}")
        print(f"   user.email: {result['user']['email']}")
        print(f"   user.role: {result['user']['role']}")
        print(f"   tenant.subscription_plan: {result['tenant']['subscription_plan']}")
    else:
        print("❌ PREVIEW BACKEND SORUNU VAR!")
        print(f"   HTTP Status: {result.get('http_status', 'N/A')}")
        print(f"   Hata: {result.get('error', 'N/A')}")
        print(f"   Detay: {result.get('detail', 'N/A')}")
    
    return result

if __name__ == "__main__":
    asyncio.run(main())