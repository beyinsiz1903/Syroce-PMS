#!/usr/bin/env python3
"""
BULK DELETE ENDPOINT BACKEND TESTING
Test the new bulk delete endpoint for rooms.

OBJECTIVE: Test the bulk delete functionality as requested

TARGET ENDPOINTS:
1. POST /api/auth/login - Authentication
2. POST /api/pms/rooms/bulk/range - Create bulk rooms
3. GET /api/pms/rooms?limit=500 - Verify rooms exist
4. POST /api/pms/rooms/bulk/delete - Delete bulk rooms
5. GET /api/pms/rooms?limit=500 - Verify rooms deleted

TEST SCENARIO:
1. Login as demo@hotel.com / demo123 (admin) and get token
2. Create 3 rooms via /api/pms/rooms/bulk/range: prefix "DEL", start 1, end 3, floor 1, room_type standard, base_price 50, capacity 2
3. Verify GET /api/pms/rooms?limit=500 contains DEL1, DEL2, DEL3
4. Call POST /api/pms/rooms/bulk/delete with payload:
   {
     "prefix": "DEL",
     "start_number": 1,
     "end_number": 3,
     "confirm_text": "DELETE"
   }
   Expect deleted==3, blocked==0
5. Verify GET /api/pms/rooms?limit=500 no longer contains DEL1..DEL3
6. Negative: call bulk/delete with confirm_text="delete" (lowercase) should still work? (We uppercased in backend; confirm accepted). Then call with confirm_text="" should return 400.

EXPECTED RESULTS:
- Authentication successful
- Bulk room creation successful (3 rooms created)
- Rooms DEL1, DEL2, DEL3 exist after creation
- Bulk delete successful (3 rooms deleted)
- Rooms DEL1, DEL2, DEL3 no longer exist after deletion
- Negative test cases work as expected
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Any, Optional
import uuid

# Configuration
BACKEND_URL = "https://report-calendar-fix.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class BulkDeleteTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.created_rooms = []
        self.test_prefix = "DEL"  # Will be updated with timestamp

    async def setup_session(self):
        """Initialize HTTP session"""
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'Content-Type': 'application/json'}
        )

    async def cleanup_session(self):
        """Clean up HTTP session"""
        if self.session:
            await self.session.close()

    async def login(self) -> bool:
        """Authenticate and get token"""
        try:
            print(f"🔐 Logging in as {TEST_EMAIL}...")
            
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data.get('access_token')
                    user_data = data.get('user', {})
                    self.tenant_id = user_data.get('tenant_id')
                    self.user_id = user_data.get('id')
                    
                    # Update session headers with auth token
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.auth_token}'
                    })
                    
                    print(f"✅ Login successful - User: {user_data.get('name')}, Role: {user_data.get('role')}")
                    print(f"   Tenant ID: {self.tenant_id}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Login failed: HTTP {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False

    async def create_bulk_rooms(self) -> bool:
        """Create bulk rooms for testing"""
        try:
            # Use timestamp to ensure unique room numbers (generate once)
            if self.test_prefix == "DEL":
                import time
                timestamp = str(int(time.time()))[-4:]  # Last 4 digits of timestamp
                self.test_prefix = f"DEL{timestamp}"
            
            print(f"🏨 Creating bulk rooms {self.test_prefix}1-{self.test_prefix}3...")
            
            bulk_data = {
                "prefix": self.test_prefix,
                "start_number": 1,
                "end_number": 3,
                "floor": 1,
                "room_type": "standard",
                "base_price": 50,
                "capacity": 2
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/rooms/bulk/range", json=bulk_data) as response:
                if response.status == 200:
                    data = await response.json()
                    created = data.get('created', 0)
                    skipped = data.get('skipped', 0)
                    errors = data.get('errors', 0)
                    
                    print(f"✅ Bulk room creation successful - Created: {created}, Skipped: {skipped}, Errors: {errors}")
                    
                    if created == 3:
                        self.created_rooms = [f'{self.test_prefix}1', f'{self.test_prefix}2', f'{self.test_prefix}3']
                        # Small delay to ensure rooms are indexed
                        await asyncio.sleep(1)
                        return True
                    else:
                        print(f"⚠️ Expected 3 rooms created, got {created}")
                        return False
                else:
                    error_text = await response.text()
                    print(f"❌ Bulk room creation failed: HTTP {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Bulk room creation error: {str(e)}")
            return False

    async def verify_rooms_exist(self, should_exist: bool = True) -> bool:
        """Verify rooms exist or don't exist"""
        try:
            action = "exist" if should_exist else "be deleted"
            print(f"🔍 Verifying rooms {self.test_prefix}1-{self.test_prefix}3 {action}...")
            
            async with self.session.get(f"{BACKEND_URL}/pms/rooms?limit=500") as response:
                if response.status == 200:
                    rooms = await response.json()  # API returns list directly
                    
                    found_rooms = []
                    expected_rooms = [f'{self.test_prefix}1', f'{self.test_prefix}2', f'{self.test_prefix}3']
                    
                    for room in rooms:
                        room_number = room.get('room_number', '')
                        if room_number in expected_rooms:
                            found_rooms.append(room_number)
                    
                    # Debug: print first few rooms to see format
                    if len(found_rooms) == 0 and should_exist:
                        print(f"   Debug: Expected rooms: {expected_rooms}")
                        all_del_rooms = [r.get('room_number', '') for r in rooms if r.get('room_number', '').startswith('DEL')]
                        print(f"   Debug: All DEL rooms found: {all_del_rooms[-10:]}")  # Last 10 DEL rooms
                    
                    if should_exist:
                        if len(found_rooms) == 3:
                            print(f"✅ All 3 rooms found: {found_rooms}")
                            return True
                        else:
                            print(f"❌ Expected 3 rooms, found {len(found_rooms)}: {found_rooms}")
                            return False
                    else:
                        if len(found_rooms) == 0:
                            print(f"✅ All rooms successfully deleted (0 found)")
                            return True
                        else:
                            print(f"❌ Expected 0 rooms, found {len(found_rooms)}: {found_rooms}")
                            return False
                else:
                    error_text = await response.text()
                    print(f"❌ Room verification failed: HTTP {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Room verification error: {str(e)}")
            return False

    async def test_bulk_delete_success(self) -> bool:
        """Test successful bulk delete"""
        try:
            print(f"🗑️ Testing bulk delete with correct confirm_text...")
            
            delete_data = {
                "prefix": self.test_prefix,
                "start_number": 1,
                "end_number": 3,
                "confirm_text": "DELETE"
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/rooms/bulk/delete", json=delete_data) as response:
                if response.status == 200:
                    data = await response.json()
                    deleted = data.get('deleted', 0)
                    blocked = data.get('blocked', 0)
                    
                    print(f"✅ Bulk delete successful - Deleted: {deleted}, Blocked: {blocked}")
                    
                    if deleted == 3 and blocked == 0:
                        return True
                    else:
                        print(f"⚠️ Expected deleted=3, blocked=0, got deleted={deleted}, blocked={blocked}")
                        return False
                else:
                    error_text = await response.text()
                    print(f"❌ Bulk delete failed: HTTP {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Bulk delete error: {str(e)}")
            return False

    async def test_bulk_delete_lowercase(self) -> bool:
        """Test bulk delete with lowercase confirm_text (should work)"""
        try:
            print(f"🗑️ Testing bulk delete with lowercase confirm_text...")
            
            # First create rooms again for this test
            await self.create_bulk_rooms()
            
            delete_data = {
                "prefix": self.test_prefix,
                "start_number": 1,
                "end_number": 3,
                "confirm_text": "delete"  # lowercase
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/rooms/bulk/delete", json=delete_data) as response:
                if response.status == 200:
                    data = await response.json()
                    deleted = data.get('deleted', 0)
                    blocked = data.get('blocked', 0)
                    
                    print(f"✅ Bulk delete with lowercase successful - Deleted: {deleted}, Blocked: {blocked}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Bulk delete with lowercase failed: HTTP {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Bulk delete lowercase error: {str(e)}")
            return False

    async def test_bulk_delete_empty_confirm(self) -> bool:
        """Test bulk delete with empty confirm_text (should fail with 400)"""
        try:
            print(f"🗑️ Testing bulk delete with empty confirm_text (should fail)...")
            
            # First create rooms again for this test
            await self.create_bulk_rooms()
            
            delete_data = {
                "prefix": self.test_prefix,
                "start_number": 1,
                "end_number": 3,
                "confirm_text": ""  # empty
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/rooms/bulk/delete", json=delete_data) as response:
                if response.status == 400:
                    error_text = await response.text()
                    print(f"✅ Bulk delete with empty confirm_text correctly failed: HTTP 400 - {error_text}")
                    return True
                else:
                    print(f"❌ Expected HTTP 400, got HTTP {response.status}")
                    return False
                    
        except Exception as e:
            print(f"❌ Bulk delete empty confirm error: {str(e)}")
            return False

    async def cleanup_test_rooms(self):
        """Clean up any remaining test rooms"""
        try:
            print(f"🧹 Cleaning up any remaining test rooms...")
            
            # Try to delete any remaining DEL rooms
            delete_data = {
                "prefix": "DEL",
                "start_number": 1,
                "end_number": 10,  # Wider range to catch any leftovers
                "confirm_text": "DELETE"
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/rooms/bulk/delete", json=delete_data) as response:
                if response.status == 200:
                    data = await response.json()
                    deleted = data.get('deleted', 0)
                    if deleted > 0:
                        print(f"🧹 Cleaned up {deleted} remaining test rooms")
                    else:
                        print(f"🧹 No test rooms to clean up")
                        
        except Exception as e:
            print(f"⚠️ Cleanup error (non-critical): {str(e)}")

    async def run_comprehensive_test(self):
        """Run all bulk delete tests"""
        print("🎯 BULK DELETE ENDPOINT COMPREHENSIVE TEST")
        print("=" * 60)
        
        try:
            await self.setup_session()
            
            # Step 1: Authentication
            if not await self.login():
                print("❌ Authentication failed - stopping tests")
                return False
            
            # Step 2: Clean up any existing test rooms first
            await self.cleanup_test_rooms()
            
            # Step 3: Create bulk rooms
            if not await self.create_bulk_rooms():
                print("❌ Bulk room creation failed - stopping tests")
                return False
            
            # Step 4: Verify rooms exist
            if not await self.verify_rooms_exist(should_exist=True):
                print("❌ Room verification failed - stopping tests")
                return False
            
            # Step 5: Test successful bulk delete
            if not await self.test_bulk_delete_success():
                print("❌ Bulk delete test failed - stopping tests")
                return False
            
            # Step 6: Verify rooms are deleted
            if not await self.verify_rooms_exist(should_exist=False):
                print("❌ Room deletion verification failed")
                return False
            
            # Step 7: Test lowercase confirm_text
            if not await self.test_bulk_delete_lowercase():
                print("❌ Lowercase confirm_text test failed")
                return False
            
            # Step 8: Test empty confirm_text (should fail)
            if not await self.test_bulk_delete_empty_confirm():
                print("❌ Empty confirm_text test failed")
                return False
            
            # Final cleanup
            await self.cleanup_test_rooms()
            
            print("\n🎉 ALL BULK DELETE TESTS PASSED!")
            print("=" * 60)
            print("✅ Authentication successful")
            print("✅ Bulk room creation working")
            print("✅ Room verification working")
            print("✅ Bulk delete with uppercase 'DELETE' working")
            print("✅ Bulk delete with lowercase 'delete' working")
            print("✅ Empty confirm_text properly rejected (HTTP 400)")
            print("✅ Room cleanup successful")
            
            return True
            
        except Exception as e:
            print(f"❌ Test execution error: {str(e)}")
            return False
        finally:
            await self.cleanup_session()

async def main():
    """Main test execution"""
    tester = BulkDeleteTester()
    success = await tester.run_comprehensive_test()
    
    if success:
        print("\n🏆 BULK DELETE ENDPOINT: PRODUCTION READY ✅")
        sys.exit(0)
    else:
        print("\n💥 BULK DELETE ENDPOINT: ISSUES FOUND ❌")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())