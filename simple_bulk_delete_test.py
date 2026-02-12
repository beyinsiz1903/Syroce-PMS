#!/usr/bin/env python3
"""
SIMPLE BULK DELETE TEST
Test the bulk delete endpoint with existing rooms
"""

import asyncio
import aiohttp
import json

BACKEND_URL = "https://report-calendar-fix.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

async def test_bulk_delete():
    """Test bulk delete with existing DEL rooms"""
    
    # Setup session
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
    timeout = aiohttp.ClientTimeout(total=30)
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        # Login
        print("🔐 Logging in...")
        login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
        
        async with session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
            if response.status != 200:
                print(f"❌ Login failed: {response.status}")
                return
            
            data = await response.json()
            auth_token = data.get('access_token')
            session.headers.update({'Authorization': f'Bearer {auth_token}'})
            print("✅ Login successful")
        
        # Check existing DEL rooms
        print("🔍 Checking existing DEL rooms...")
        async with session.get(f"{BACKEND_URL}/pms/rooms?limit=500") as response:
            if response.status == 200:
                rooms = await response.json()
                del_rooms = [r.get('room_number', '') for r in rooms if r.get('room_number', '').startswith('DEL')]
                print(f"   Found {len(del_rooms)} DEL rooms: {del_rooms[-10:]}")  # Last 10
            else:
                print(f"❌ Failed to get rooms: {response.status}")
                return
        
        # Test bulk delete with existing rooms (DEL1, DEL2, DEL3)
        print("🗑️ Testing bulk delete with DEL1-DEL3...")
        delete_data = {
            "prefix": "DEL",
            "start_number": 1,
            "end_number": 3,
            "confirm_text": "DELETE"
        }
        
        async with session.post(f"{BACKEND_URL}/pms/rooms/bulk/delete", json=delete_data) as response:
            print(f"   Response status: {response.status}")
            response_text = await response.text()
            print(f"   Response body: {response_text}")
            
            if response.status == 200:
                data = await response.json()
                deleted = data.get('deleted', 0)
                blocked = data.get('blocked', 0)
                print(f"✅ Bulk delete successful - Deleted: {deleted}, Blocked: {blocked}")
            else:
                print(f"❌ Bulk delete failed: HTTP {response.status}")
        
        # Test with lowercase confirm_text
        print("🗑️ Testing bulk delete with lowercase 'delete'...")
        delete_data = {
            "prefix": "DEL1804",  # Use existing prefix
            "start_number": 1,
            "end_number": 3,
            "confirm_text": "delete"  # lowercase
        }
        
        async with session.post(f"{BACKEND_URL}/pms/rooms/bulk/delete", json=delete_data) as response:
            print(f"   Response status: {response.status}")
            response_text = await response.text()
            print(f"   Response body: {response_text}")
        
        # Test with empty confirm_text (should fail)
        print("🗑️ Testing bulk delete with empty confirm_text (should fail)...")
        delete_data = {
            "prefix": "DEL1829",  # Use existing prefix
            "start_number": 1,
            "end_number": 3,
            "confirm_text": ""  # empty
        }
        
        async with session.post(f"{BACKEND_URL}/pms/rooms/bulk/delete", json=delete_data) as response:
            print(f"   Response status: {response.status}")
            response_text = await response.text()
            print(f"   Response body: {response_text}")
            
            if response.status == 400:
                print("✅ Empty confirm_text correctly rejected with HTTP 400")
            else:
                print(f"❌ Expected HTTP 400, got {response.status}")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(test_bulk_delete())