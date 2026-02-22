#!/usr/bin/env python3
"""
Debug notification preferences endpoint
"""

import asyncio
import aiohttp
import json
import uuid

BACKEND_URL = "https://auth-endpoint-suite.preview.emergentagent.com/api"

async def debug_notification_prefs():
    session = aiohttp.ClientSession()
    
    # Register a guest user
    guest_email = f"debugguest{uuid.uuid4().hex[:8]}@hotel.com"
    registration_data = {
        "email": guest_email,
        "password": "testpass123",
        "name": "Debug Guest User",
        "phone": "+1234567890"
    }
    
    async with session.post(f"{BACKEND_URL}/auth/register-guest", json=registration_data) as response:
        if response.status == 200:
            data = await response.json()
            token = data["access_token"]
            print(f"✅ Guest registered successfully")
        else:
            print(f"❌ Guest registration failed: {response.status}")
            await session.close()
            return
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Test GET notification preferences
    async with session.get(f"{BACKEND_URL}/guest/notification-preferences", headers=headers) as response:
        print(f"\nGET /guest/notification-preferences")
        print(f"Status: {response.status}")
        if response.status == 200:
            data = await response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
        else:
            error_text = await response.text()
            print(f"Error: {error_text}")
    
    await session.close()

if __name__ == "__main__":
    asyncio.run(debug_notification_prefs())