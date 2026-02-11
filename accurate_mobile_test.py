#!/usr/bin/env python3
"""
Accurate Mobile Endpoints Test - Testing actual mobile endpoints that exist
"""

import asyncio
import aiohttp
import json

BACKEND_URL = "https://error-sweep-audit.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

async def test_actual_mobile_endpoints():
    async with aiohttp.ClientSession() as session:
        # Authenticate
        login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
        async with session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
            if response.status != 200:
                print(f"❌ Authentication failed: {response.status}")
                return
            
            data = await response.json()
            auth_token = data["access_token"]
            headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
            print("✅ Authentication successful")
        
        # Test actual mobile endpoints that exist
        mobile_endpoints = [
            # Housekeeping Mobile
            ("/housekeeping/mobile/my-tasks", "Housekeeping Mobile - My Tasks"),
            ("/housekeeping/mobile/room-assignments", "Housekeeping Mobile - Room Assignments"),
            
            # F&B Mobile
            ("/fnb/mobile/outlets", "F&B Mobile - Outlets"),
            ("/fnb/mobile/orders/active", "F&B Mobile - Active Orders"),
            ("/fnb/mobile/recipes", "F&B Mobile - Recipes"),
            ("/fnb/mobile/ingredients", "F&B Mobile - Ingredients"),
            ("/fnb/mobile/stock-consumption", "F&B Mobile - Stock Consumption"),
            ("/fnb/mobile/daily-summary", "F&B Mobile - Daily Summary"),
            
            # Staff Mobile
            ("/mobile/staff/dashboard", "Mobile Staff - Dashboard"),
            
            # Revenue Mobile
            ("/revenue-mobile/adr", "Revenue Mobile - ADR"),
            ("/revenue-mobile/revpar", "Revenue Mobile - RevPAR"),
        ]
        
        success_count = 0
        total_count = len(mobile_endpoints)
        failed_endpoints = []
        
        print(f"\n📱 Testing {total_count} Actual Mobile Endpoints...")
        print("=" * 60)
        
        for endpoint, description in mobile_endpoints:
            try:
                async with session.get(f"{BACKEND_URL}{endpoint}", headers=headers) as response:
                    status = response.status
                    if status == 200:
                        data = await response.json()
                        print(f"  ✅ {description}: HTTP {status} - SUCCESS")
                        success_count += 1
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {description}: HTTP {status} - {error_text[:100]}")
                        failed_endpoints.append(f"{endpoint} - HTTP {status}")
            except Exception as e:
                print(f"  ❌ {description}: ERROR - {str(e)}")
                failed_endpoints.append(f"{endpoint} - ERROR: {str(e)}")
        
        # Results
        success_rate = (success_count / total_count * 100) if total_count > 0 else 0
        print("\n" + "=" * 60)
        print("📊 MOBILE ENDPOINTS TEST RESULTS")
        print("=" * 60)
        print(f"✅ Successful: {success_count}/{total_count}")
        print(f"📈 Success Rate: {success_rate:.1f}%")
        
        if failed_endpoints:
            print(f"\n❌ FAILED ENDPOINTS ({len(failed_endpoints)}):")
            for i, endpoint in enumerate(failed_endpoints, 1):
                print(f"   {i}. {endpoint}")

if __name__ == "__main__":
    asyncio.run(test_actual_mobile_endpoints())