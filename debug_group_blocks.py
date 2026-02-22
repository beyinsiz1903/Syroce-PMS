#!/usr/bin/env python3
"""
Debug Group Blocks Data Structure
Check the actual structure of group blocks data to understand filtering issues
"""

import asyncio
import aiohttp
import json

# Configuration
BACKEND_URL = "https://auth-endpoint-suite.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

async def debug_group_blocks():
    """Debug group blocks data structure"""
    
    session = aiohttp.ClientSession()
    
    try:
        # Authenticate
        login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
        async with session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
            if response.status != 200:
                print("❌ Authentication failed")
                return
            
            data = await response.json()
            auth_token = data["access_token"]
            headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
        
        # Get all blocks
        async with session.get(f"{BACKEND_URL}/groups/blocks", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                blocks = data.get("blocks", [])
                
                print(f"🔍 Found {len(blocks)} blocks")
                print("=" * 60)
                
                for i, block in enumerate(blocks):
                    print(f"\nBlock {i+1}:")
                    print(f"  ID: {block.get('id', 'N/A')}")
                    print(f"  Block Name: {block.get('block_name', 'N/A')}")
                    print(f"  Status: {block.get('status', 'N/A')}")
                    print(f"  Check-in: {block.get('check_in', 'N/A')}")
                    print(f"  Start Date: {block.get('start_date', 'N/A')}")
                    print(f"  End Date: {block.get('end_date', 'N/A')}")
                    print(f"  Room Type: {block.get('room_type', 'N/A')}")
                    print(f"  Total Rooms: {block.get('total_rooms', 'N/A')}")
                    print(f"  All Fields: {list(block.keys())}")
                    
                    if i == 2:  # Show first 3 blocks in detail
                        break
                
                print("\n" + "=" * 60)
                print("🔍 FIELD ANALYSIS:")
                
                # Analyze field usage
                all_fields = set()
                for block in blocks:
                    all_fields.update(block.keys())
                
                print(f"All unique fields found: {sorted(all_fields)}")
                
                # Check date fields specifically
                date_fields = ['check_in', 'start_date', 'end_date', 'created_at']
                print(f"\nDate field analysis:")
                for field in date_fields:
                    values = [block.get(field) for block in blocks]
                    unique_values = set(values)
                    print(f"  {field}: {unique_values}")
                
                # Check status field
                statuses = [block.get('status') for block in blocks]
                unique_statuses = set(statuses)
                print(f"\nStatus field analysis:")
                print(f"  Unique statuses: {unique_statuses}")
                
            else:
                print(f"❌ Failed to get blocks: HTTP {response.status}")
                error_text = await response.text()
                print(f"Error: {error_text}")
    
    finally:
        await session.close()

if __name__ == "__main__":
    asyncio.run(debug_group_blocks())