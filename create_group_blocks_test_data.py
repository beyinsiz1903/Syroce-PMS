#!/usr/bin/env python3
"""
Create Group Blocks Test Data
Creates sample group blocks with different statuses and dates for testing filters
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timezone, timedelta

# Configuration
BACKEND_URL = "https://unitcare-1.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class GroupBlocksDataCreator:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate and get token"""
        try:
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data["access_token"]
                    self.tenant_id = data["user"]["tenant_id"]
                    print(f"✅ Authentication successful - Tenant: {self.tenant_id}")
                    return True
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    async def create_group_blocks_test_data(self):
        """Create comprehensive group blocks test data"""
        print("\n🏨 Creating Group Blocks Test Data...")
        
        # Test data scenarios
        today = datetime.now().strftime("%Y-%m-%d")
        this_month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        this_month_end = datetime.now().replace(day=28).strftime("%Y-%m-%d")
        next_month = (datetime.now() + timedelta(days=32)).strftime("%Y-%m-%d")
        
        test_blocks = [
            # Today's blocks with different statuses
            {
                "block_name": "Corporate Meeting Today - Tentative",
                "room_type": "Standard",
                "check_in_date": today,
                "check_out_date": today,
                "total_rooms": 5,
                "block_type": "tentative",
                "status": "tentative",
                "release_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                "contact_person": "John Manager",
                "contact_email": "john@corporate.com",
                "notes": "Corporate meeting block for today"
            },
            {
                "block_name": "Wedding Party Today - Definite",
                "room_type": "Deluxe",
                "check_in_date": today,
                "check_out_date": today,
                "total_rooms": 8,
                "block_type": "definite",
                "status": "definite",
                "contact_person": "Sarah Wedding",
                "contact_email": "sarah@wedding.com",
                "notes": "Wedding party block for today"
            },
            
            # This month blocks
            {
                "block_name": "Conference This Month - Tentative",
                "room_type": "Suite",
                "check_in_date": this_month_start,
                "check_out_date": this_month_end,
                "total_rooms": 10,
                "block_type": "tentative",
                "status": "tentative",
                "release_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "contact_person": "Mike Conference",
                "contact_email": "mike@conference.com",
                "notes": "Conference block for this month"
            },
            {
                "block_name": "Business Group This Month - Definite",
                "room_type": "Standard",
                "check_in_date": this_month_start,
                "check_out_date": this_month_end,
                "total_rooms": 15,
                "block_type": "definite",
                "status": "definite",
                "contact_person": "Lisa Business",
                "contact_email": "lisa@business.com",
                "notes": "Business group block for this month"
            },
            
            # Custom date range (November 2025)
            {
                "block_name": "November Event - Tentative",
                "room_type": "Deluxe",
                "check_in_date": "2025-11-15",
                "check_out_date": "2025-11-20",
                "total_rooms": 12,
                "block_type": "tentative",
                "status": "tentative",
                "release_date": "2025-11-10",
                "contact_person": "David Event",
                "contact_email": "david@event.com",
                "notes": "November event block"
            },
            {
                "block_name": "November Training - Definite",
                "room_type": "Standard",
                "check_in_date": "2025-11-25",
                "check_out_date": "2025-11-27",
                "total_rooms": 6,
                "block_type": "definite",
                "status": "definite",
                "contact_person": "Emma Training",
                "contact_email": "emma@training.com",
                "notes": "November training block"
            },
            
            # Next month blocks (for negative testing)
            {
                "block_name": "Future Event - Tentative",
                "room_type": "Suite",
                "check_in_date": next_month,
                "check_out_date": next_month,
                "total_rooms": 4,
                "block_type": "tentative",
                "status": "tentative",
                "release_date": (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d"),
                "contact_person": "Future Planner",
                "contact_email": "future@planner.com",
                "notes": "Future event block"
            },
            
            # Cancelled blocks (for status testing)
            {
                "block_name": "Cancelled Event This Month",
                "room_type": "Standard",
                "check_in_date": this_month_start,
                "check_out_date": this_month_end,
                "total_rooms": 3,
                "block_type": "cancelled",
                "status": "cancelled",
                "contact_person": "Cancelled Event",
                "contact_email": "cancelled@event.com",
                "notes": "Cancelled event block"
            }
        ]
        
        created_blocks = []
        
        for i, block_data in enumerate(test_blocks):
            try:
                print(f"\n  Creating block {i+1}/{len(test_blocks)}: {block_data['block_name']}")
                
                async with self.session.post(f"{BACKEND_URL}/groups/create-block", 
                                           json=block_data, 
                                           headers=self.get_headers()) as response:
                    if response.status == 200:
                        result = await response.json()
                        created_blocks.append(result)
                        print(f"    ✅ Created: {block_data['block_name']} (status: {block_data['status']}, date: {block_data['start_date']})")
                    else:
                        error_text = await response.text()
                        print(f"    ❌ Failed to create block: HTTP {response.status}")
                        print(f"       Error: {error_text}")
                        
            except Exception as e:
                print(f"    ❌ Exception creating block: {e}")
        
        print(f"\n✅ Created {len(created_blocks)}/{len(test_blocks)} group blocks successfully")
        return created_blocks

    async def verify_created_blocks(self):
        """Verify the created blocks by listing all blocks"""
        print("\n🔍 Verifying created blocks...")
        
        try:
            async with self.session.get(f"{BACKEND_URL}/groups/blocks", 
                                      headers=self.get_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    blocks = data.get("blocks", [])
                    total = data.get("total", 0)
                    
                    print(f"  ✅ Total blocks in system: {total}")
                    
                    if blocks:
                        print("  📋 Block summary:")
                        status_counts = {}
                        date_counts = {}
                        
                        for block in blocks:
                            status = block.get("status", "unknown")
                            check_in = block.get("check_in", "unknown")
                            
                            status_counts[status] = status_counts.get(status, 0) + 1
                            date_counts[check_in] = date_counts.get(check_in, 0) + 1
                        
                        print("    Status distribution:")
                        for status, count in status_counts.items():
                            print(f"      {status}: {count}")
                        
                        print("    Date distribution:")
                        for date, count in sorted(date_counts.items()):
                            print(f"      {date}: {count}")
                    
                    return True
                else:
                    error_text = await response.text()
                    print(f"  ❌ Failed to verify blocks: HTTP {response.status}")
                    print(f"     Error: {error_text}")
                    return False
                    
        except Exception as e:
            print(f"  ❌ Exception verifying blocks: {e}")
            return False

    async def run(self):
        """Run the data creation process"""
        print("🚀 GROUP BLOCKS TEST DATA CREATION")
        print("=" * 60)
        
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed.")
            return
        
        # Create test data
        created_blocks = await self.create_group_blocks_test_data()
        
        # Verify created data
        await self.verify_created_blocks()
        
        await self.cleanup_session()
        
        print("\n" + "=" * 60)
        print("✅ GROUP BLOCKS TEST DATA CREATION COMPLETED")
        print("=" * 60)
        print("\nNow you can run the filter tests to verify the filtering logic works correctly!")

async def main():
    """Main execution"""
    creator = GroupBlocksDataCreator()
    await creator.run()

if __name__ == "__main__":
    asyncio.run(main())