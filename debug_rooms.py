#!/usr/bin/env python3
"""
Debug script to check what rooms exist after CSV import
"""

import asyncio
import aiohttp
import json

BACKEND_URL = "https://guest-unified.preview.emergentagent.com/api"
TEST_EMAIL = "muratsutay@hotmail.com"
TEST_PASSWORD = "murat1903"

async def debug_rooms():
    session = aiohttp.ClientSession()
    
    # Authenticate
    login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
    async with session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
        if response.status == 200:
            data = await response.json()
            auth_token = data["access_token"]
            print(f"✅ Authentication successful")
        else:
            print(f"❌ Authentication failed: {response.status}")
            await session.close()
            return
    
    # Get all rooms
    headers = {"Authorization": f"Bearer {auth_token}"}
    async with session.get(f"{BACKEND_URL}/pms/rooms?limit=300", headers=headers) as response:
        if response.status == 200:
            rooms = await response.json()
            print(f"\n📊 Total rooms found: {len(rooms)}")
            
            # Show all room numbers
            room_numbers = [room.get('room_number') for room in rooms]
            print(f"📊 All room numbers: {sorted(room_numbers)}")
            
            # Look for C101 and C102
            c_rooms = [room for room in rooms if room.get('room_number', '').startswith('C10')]
            print(f"📊 C10x rooms found: {len(c_rooms)}")
            
            # Look for any C rooms
            c_any_rooms = [room for room in rooms if room.get('room_number', '').startswith('C')]
            print(f"📊 Any C rooms found: {len(c_any_rooms)}")
            
            for room in c_any_rooms:
                print(f"\n🏨 Room: {room.get('room_number')}")
                print(f"   Type: {room.get('room_type')}")
                print(f"   View: {room.get('view')}")
                print(f"   Bed Type: {room.get('bed_type')}")
                print(f"   Amenities: {room.get('amenities')}")
                print(f"   Floor: {room.get('floor')}")
                print(f"   Capacity: {room.get('capacity')}")
                print(f"   Base Price: {room.get('base_price')}")
        else:
            error_text = await response.text()
            print(f"❌ Failed to get rooms: {response.status}")
            print(f"Error: {error_text}")
    
    await session.close()

if __name__ == "__main__":
    asyncio.run(debug_rooms())