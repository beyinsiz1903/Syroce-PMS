#!/usr/bin/env python3
"""
Quick test for Mobile Housekeeping endpoint after datetime fix
"""

import asyncio
import aiohttp
import json

BACKEND_URL = "https://pms-feature-test.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

async def test_mobile_housekeeping():
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
        
        # Test Mobile Housekeeping endpoint
        print("\n🧹 Testing Mobile Housekeeping Room Assignments...")
        async with session.get(f"{BACKEND_URL}/housekeeping/mobile/room-assignments", headers=headers) as response:
            status = response.status
            if status == 200:
                data = await response.json()
                print(f"✅ Mobile Housekeeping: HTTP {status} - SUCCESS")
                print(f"📊 Response structure: {list(data.keys())}")
                if 'assignments' in data:
                    print(f"📊 Assignments count: {len(data.get('assignments', []))}")
                    if data['assignments']:
                        print(f"📊 Sample assignment: {data['assignments'][0]}")
            else:
                error_text = await response.text()
                print(f"❌ Mobile Housekeeping: HTTP {status} - {error_text}")

if __name__ == "__main__":
    asyncio.run(test_mobile_housekeeping())