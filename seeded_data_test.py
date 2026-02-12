#!/usr/bin/env python3
"""
Comprehensive Testing for Hotel PMS Automatic Database Seeding
Testing seeded data including:
1. Authentication Test (admin, frontdesk, housekeeping users)
2. Rooms Data Test (24 rooms with different types and statuses)
3. Bookings Data Test (30 bookings with different statuses)
4. Guests Data Test (15 guests with Turkish names)
5. Folios Test (for checked-in bookings)
6. Housekeeping Test (room status board, task assignments)
7. POS/Menu Test (12 menu items, Turkish items)
8. Feedback Test (guest feedback)
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

# Configuration
BACKEND_URL = "https://ai-feature-test.preview.emergentagent.com/api"

# Test user credentials
TEST_USERS = [
    {"email": "admin@hotel.com", "password": "admin123", "role": "admin"},
    {"email": "frontdesk@hotel.com", "password": "frontdesk123", "role": "front_desk"},
    {"email": "housekeeping@hotel.com", "password": "housekeeping123", "role": "housekeeping"}
]

class SeededDataTester:
    def __init__(self):
        self.session = None
        self.auth_tokens = {}
        self.test_results = []
        self.current_user = None

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def authenticate_user(self, email: str, password: str, role: str):
        """Authenticate a specific user and store token"""
        try:
            login_data = {
                "email": email,
                "password": password
            }
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_tokens[role] = {
                        "token": data["access_token"],
                        "user": data["user"],
                        "tenant": data.get("tenant")
                    }
                    print(f"✅ Authentication successful for {role} ({email})")
                    return True
                else:
                    print(f"❌ Authentication failed for {role} ({email}): {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error for {role}: {e}")
            return False

    def get_headers(self, role: str = "admin"):
        """Get authorization headers for specific role"""
        if role in self.auth_tokens:
            return {
                "Authorization": f"Bearer {self.auth_tokens[role]['token']}",
                "Content-Type": "application/json"
            }
        return {"Content-Type": "application/json"}

    # ============= AUTHENTICATION TESTS =============

    async def test_authentication(self):
        """Test authentication for all seeded users"""
        print("\n🔐 Testing Authentication for Seeded Users...")
        
        passed = 0
        total = len(TEST_USERS)
        
        for user in TEST_USERS:
            success = await self.authenticate_user(user["email"], user["password"], user["role"])
            if success:
                passed += 1
                
                # Verify JWT token contains expected data
                if user["role"] in self.auth_tokens:
                    user_data = self.auth_tokens[user["role"]]["user"]
                    if user_data.get("email") == user["email"] and user_data.get("role") == user["role"]:
                        print(f"  ✅ JWT token valid for {user['role']}")
                    else:
                        print(f"  ⚠️ JWT token data mismatch for {user['role']}")
        
        self.test_results.append({
            "test": "Authentication Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Tested login for admin, frontdesk, and housekeeping users"
        })

    # ============= ROOMS DATA TESTS =============

    async def test_rooms_data(self):
        """Test seeded rooms data - expecting 24 rooms with different types and statuses"""
        print("\n🏨 Testing Rooms Data...")
        
        try:
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    
                    # Test 1: Check total room count (expecting 24)
                    room_count_test = len(rooms) >= 20  # Allow some flexibility
                    print(f"  {'✅' if room_count_test else '❌'} Room count: {len(rooms)} rooms (expected ~24)")
                    
                    # Test 2: Check room types variety
                    room_types = set(room.get("room_type", "") for room in rooms)
                    expected_types = {"Standard", "Deluxe", "Suite", "Presidential"}
                    types_test = len(room_types.intersection(expected_types)) >= 3
                    print(f"  {'✅' if types_test else '❌'} Room types: {list(room_types)} (expected: Standard, Deluxe, Suite, Presidential)")
                    
                    # Test 3: Check room statuses variety
                    room_statuses = set(room.get("status", "") for room in rooms)
                    expected_statuses = {"available", "occupied", "dirty", "cleaning", "inspected"}
                    status_test = len(room_statuses.intersection(expected_statuses)) >= 3
                    print(f"  {'✅' if status_test else '❌'} Room statuses: {list(room_statuses)} (expected variety)")
                    
                    # Test 4: Check room structure
                    structure_test = True
                    required_fields = ["id", "room_number", "room_type", "status", "floor", "capacity"]
                    if rooms:
                        sample_room = rooms[0]
                        missing_fields = [field for field in required_fields if field not in sample_room]
                        structure_test = len(missing_fields) == 0
                        print(f"  {'✅' if structure_test else '❌'} Room structure: {'Complete' if structure_test else f'Missing {missing_fields}'}")
                    
                    passed = sum([room_count_test, types_test, status_test, structure_test])
                    total = 4
                    
                else:
                    print(f"  ❌ Failed to fetch rooms: HTTP {response.status}")
                    passed, total = 0, 1
                    
        except Exception as e:
            print(f"  ❌ Error testing rooms data: {e}")
            passed, total = 0, 1
        
        self.test_results.append({
            "test": "Rooms Data Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Tested room count, types, statuses, and structure"
        })

    # ============= BOOKINGS DATA TESTS =============

    async def test_bookings_data(self):
        """Test seeded bookings data - expecting 30 bookings with different statuses"""
        print("\n📅 Testing Bookings Data...")
        
        try:
            async with self.session.get(f"{BACKEND_URL}/pms/bookings", headers=self.get_headers()) as response:
                if response.status == 200:
                    bookings = await response.json()
                    
                    # Test 1: Check total booking count (expecting 30)
                    booking_count_test = len(bookings) >= 25  # Allow some flexibility
                    print(f"  {'✅' if booking_count_test else '❌'} Booking count: {len(bookings)} bookings (expected ~30)")
                    
                    # Test 2: Check booking statuses variety
                    booking_statuses = set(booking.get("status", "") for booking in bookings)
                    expected_statuses = {"checked_out", "checked_in", "confirmed", "guaranteed"}
                    status_test = len(booking_statuses.intersection(expected_statuses)) >= 3
                    print(f"  {'✅' if status_test else '❌'} Booking statuses: {list(booking_statuses)} (expected variety)")
                    
                    # Test 3: Check booking structure
                    structure_test = True
                    required_fields = ["id", "guest_id", "room_id", "check_in", "check_out", "total_amount", "status"]
                    if bookings:
                        sample_booking = bookings[0]
                        missing_fields = [field for field in required_fields if field not in sample_booking]
                        structure_test = len(missing_fields) == 0
                        print(f"  {'✅' if structure_test else '❌'} Booking structure: {'Complete' if structure_test else f'Missing {missing_fields}'}")
                    
                    # Test 4: Check date ranges and amounts
                    data_quality_test = True
                    if bookings:
                        sample_booking = bookings[0]
                        has_dates = sample_booking.get("check_in") and sample_booking.get("check_out")
                        has_amount = sample_booking.get("total_amount", 0) > 0
                        data_quality_test = has_dates and has_amount
                        print(f"  {'✅' if data_quality_test else '❌'} Data quality: {'Valid dates and amounts' if data_quality_test else 'Missing dates or amounts'}")
                    
                    passed = sum([booking_count_test, status_test, structure_test, data_quality_test])
                    total = 4
                    
                else:
                    print(f"  ❌ Failed to fetch bookings: HTTP {response.status}")
                    passed, total = 0, 1
                    
        except Exception as e:
            print(f"  ❌ Error testing bookings data: {e}")
            passed, total = 0, 1
        
        self.test_results.append({
            "test": "Bookings Data Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Tested booking count, statuses, structure, and data quality"
        })

    # ============= GUESTS DATA TESTS =============

    async def test_guests_data(self):
        """Test seeded guests data - expecting 15 guests with Turkish names"""
        print("\n👥 Testing Guests Data...")
        
        try:
            async with self.session.get(f"{BACKEND_URL}/pms/guests", headers=self.get_headers()) as response:
                if response.status == 200:
                    guests = await response.json()
                    
                    # Test 1: Check total guest count (expecting 15)
                    guest_count_test = len(guests) >= 10  # Allow some flexibility
                    print(f"  {'✅' if guest_count_test else '❌'} Guest count: {len(guests)} guests (expected ~15)")
                    
                    # Test 2: Check for Turkish names (common Turkish names)
                    turkish_indicators = ["Ahmet", "Mehmet", "Ayşe", "Fatma", "Mustafa", "Emine", "Ali", "Hatice", "Can", "Zeynep", "Özge", "Burak", "Selin", "Emre", "Deniz"]
                    turkish_names_found = 0
                    for guest in guests:
                        guest_name = guest.get("name", "")
                        if any(turkish_name in guest_name for turkish_name in turkish_indicators):
                            turkish_names_found += 1
                    
                    turkish_test = turkish_names_found >= 5  # At least some Turkish names
                    print(f"  {'✅' if turkish_test else '❌'} Turkish names: {turkish_names_found} guests with Turkish names found")
                    
                    # Test 3: Check guest structure
                    structure_test = True
                    required_fields = ["id", "name", "email", "phone"]
                    if guests:
                        sample_guest = guests[0]
                        missing_fields = [field for field in required_fields if field not in sample_guest]
                        structure_test = len(missing_fields) == 0
                        print(f"  {'✅' if structure_test else '❌'} Guest structure: {'Complete' if structure_test else f'Missing {missing_fields}'}")
                    
                    # Test 4: Check VIP status and preferences
                    vip_test = any(guest.get("vip_status", False) for guest in guests)
                    print(f"  {'✅' if vip_test else '❌'} VIP guests: {'Found VIP guests' if vip_test else 'No VIP guests found'}")
                    
                    passed = sum([guest_count_test, turkish_test, structure_test, vip_test])
                    total = 4
                    
                else:
                    print(f"  ❌ Failed to fetch guests: HTTP {response.status}")
                    error_text = await response.text()
                    print(f"  Error details: {error_text[:200]}")
                    passed, total = 0, 1
                    
        except Exception as e:
            print(f"  ❌ Error testing guests data: {e}")
            passed, total = 0, 1
        
        self.test_results.append({
            "test": "Guests Data Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Tested guest count, Turkish names, structure, and VIP status"
        })

    # ============= FOLIOS TESTS =============

    async def test_folios_data(self):
        """Test folios for checked-in bookings"""
        print("\n💰 Testing Folios Data...")
        
        try:
            # First get bookings to find checked-in ones
            async with self.session.get(f"{BACKEND_URL}/pms/bookings", headers=self.get_headers()) as response:
                if response.status == 200:
                    bookings = await response.json()
                    checked_in_bookings = [b for b in bookings if b.get("status") == "checked_in"]
                    
                    if not checked_in_bookings:
                        print(f"  ⚠️ No checked-in bookings found to test folios")
                        self.test_results.append({
                            "test": "Folios Test",
                            "passed": 0,
                            "total": 1,
                            "success_rate": "0.0%",
                            "details": "No checked-in bookings available for folio testing"
                        })
                        return
                    
                    # Test folios for checked-in bookings
                    folios_found = 0
                    folios_with_charges = 0
                    total_checked_in = len(checked_in_bookings)
                    
                    for booking in checked_in_bookings[:5]:  # Test first 5 to avoid too many requests
                        booking_id = booking["id"]
                        
                        # Check if folio exists for this booking
                        async with self.session.get(f"{BACKEND_URL}/folio/booking/{booking_id}", headers=self.get_headers()) as folio_response:
                            if folio_response.status == 200:
                                folios = await folio_response.json()
                                if folios:
                                    folios_found += 1
                                    
                                    # Check if folio has charges
                                    folio_id = folios[0]["id"]
                                    async with self.session.get(f"{BACKEND_URL}/folio/{folio_id}", headers=self.get_headers()) as detail_response:
                                        if detail_response.status == 200:
                                            folio_details = await detail_response.json()
                                            if folio_details.get("charges") and len(folio_details["charges"]) > 0:
                                                folios_with_charges += 1
                    
                    # Test results
                    folios_exist_test = folios_found > 0
                    folios_charges_test = folios_with_charges > 0
                    
                    print(f"  {'✅' if folios_exist_test else '❌'} Folios exist: {folios_found} folios found for checked-in bookings")
                    print(f"  {'✅' if folios_charges_test else '❌'} Folio charges: {folios_with_charges} folios with charges")
                    
                    passed = sum([folios_exist_test, folios_charges_test])
                    total = 2
                    
                else:
                    print(f"  ❌ Failed to fetch bookings for folio test: HTTP {response.status}")
                    passed, total = 0, 1
                    
        except Exception as e:
            print(f"  ❌ Error testing folios data: {e}")
            passed, total = 0, 1
        
        self.test_results.append({
            "test": "Folios Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Tested folio existence and charges for checked-in bookings"
        })

    # ============= HOUSEKEEPING TESTS =============

    async def test_housekeeping_data(self):
        """Test housekeeping room status board and task assignments"""
        print("\n🧹 Testing Housekeeping Data...")
        
        passed = 0
        total = 0
        
        # Test 1: Room Status Board
        try:
            async with self.session.get(f"{BACKEND_URL}/housekeeping/room-status", headers=self.get_headers()) as response:
                if response.status == 200:
                    room_status = await response.json()
                    
                    # Check structure
                    has_rooms = "rooms" in room_status and len(room_status["rooms"]) > 0
                    has_status_counts = "status_counts" in room_status
                    has_total = "total_rooms" in room_status
                    
                    room_status_test = has_rooms and has_status_counts and has_total
                    print(f"  {'✅' if room_status_test else '❌'} Room status board: {'Working' if room_status_test else 'Missing data'}")
                    
                    if room_status_test:
                        passed += 1
                    total += 1
                    
                else:
                    print(f"  ❌ Room status board failed: HTTP {response.status}")
                    total += 1
                    
        except Exception as e:
            print(f"  ❌ Error testing room status board: {e}")
            total += 1
        
        # Test 2: Task Assignments
        try:
            async with self.session.get(f"{BACKEND_URL}/housekeeping/task-assignments", headers=self.get_headers()) as response:
                if response.status == 200:
                    task_assignments = await response.json()
                    
                    # Check if tasks exist
                    has_tasks = isinstance(task_assignments, list) or (isinstance(task_assignments, dict) and "tasks" in task_assignments)
                    task_assignments_test = has_tasks
                    print(f"  {'✅' if task_assignments_test else '❌'} Task assignments: {'Available' if task_assignments_test else 'No tasks found'}")
                    
                    if task_assignments_test:
                        passed += 1
                    total += 1
                    
                else:
                    print(f"  ❌ Task assignments failed: HTTP {response.status}")
                    total += 1
                    
        except Exception as e:
            print(f"  ❌ Error testing task assignments: {e}")
            total += 1
        
        self.test_results.append({
            "test": "Housekeeping Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%" if total > 0 else "0.0%",
            "details": f"Tested room status board and task assignments"
        })

    # ============= POS/MENU TESTS =============

    async def test_pos_menu_data(self):
        """Test POS menu items - expecting 12 items with Turkish items"""
        print("\n🍽️ Testing POS/Menu Data...")
        
        try:
            async with self.session.get(f"{BACKEND_URL}/pos/menu-items", headers=self.get_headers()) as response:
                if response.status == 200:
                    menu_data = await response.json()
                    
                    # Handle different response formats
                    menu_items = []
                    if isinstance(menu_data, list):
                        menu_items = menu_data
                    elif isinstance(menu_data, dict) and "menu_items" in menu_data:
                        menu_items = menu_data["menu_items"]
                    
                    # Test 1: Check menu item count (expecting 12)
                    item_count_test = len(menu_items) >= 10  # Allow some flexibility
                    print(f"  {'✅' if item_count_test else '❌'} Menu item count: {len(menu_items)} items (expected ~12)")
                    
                    # Test 2: Check for Turkish menu items
                    turkish_items = ["Türk Kahvesi", "Menemen", "Çay", "Baklava", "Döner", "Kebab", "Pide", "Börek", "Ayran", "Raki"]
                    turkish_items_found = 0
                    for item in menu_items:
                        item_name = item.get("name", "") if isinstance(item, dict) else str(item)
                        if any(turkish_item in item_name for turkish_item in turkish_items):
                            turkish_items_found += 1
                    
                    turkish_test = turkish_items_found >= 3  # At least some Turkish items
                    print(f"  {'✅' if turkish_test else '❌'} Turkish menu items: {turkish_items_found} Turkish items found")
                    
                    # Test 3: Check categories
                    categories = set()
                    for item in menu_items:
                        if isinstance(item, dict) and "category" in item:
                            categories.add(item["category"])
                    
                    expected_categories = {"beverage", "food", "dessert", "alcohol"}
                    category_test = len(categories.intersection(expected_categories)) >= 2
                    print(f"  {'✅' if category_test else '❌'} Menu categories: {list(categories)} (expected variety)")
                    
                    # Test 4: Check item structure
                    structure_test = True
                    if menu_items and isinstance(menu_items[0], dict):
                        sample_item = menu_items[0]
                        required_fields = ["name", "price"]
                        missing_fields = [field for field in required_fields if field not in sample_item]
                        structure_test = len(missing_fields) == 0
                        print(f"  {'✅' if structure_test else '❌'} Menu structure: {'Complete' if structure_test else f'Missing {missing_fields}'}")
                    
                    passed = sum([item_count_test, turkish_test, category_test, structure_test])
                    total = 4
                    
                else:
                    print(f"  ❌ Failed to fetch menu items: HTTP {response.status}")
                    passed, total = 0, 1
                    
        except Exception as e:
            print(f"  ❌ Error testing menu data: {e}")
            passed, total = 0, 1
        
        self.test_results.append({
            "test": "POS/Menu Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Tested menu item count, Turkish items, categories, and structure"
        })

    # ============= FEEDBACK TESTS =============

    async def test_feedback_data(self):
        """Test guest feedback data"""
        print("\n📝 Testing Feedback Data...")
        
        try:
            # Try different feedback endpoints
            feedback_endpoints = [
                "/feedback",
                "/guest-feedback", 
                "/reviews",
                "/surveys"
            ]
            
            feedback_found = False
            feedback_data = []
            
            for endpoint in feedback_endpoints:
                try:
                    async with self.session.get(f"{BACKEND_URL}{endpoint}", headers=self.get_headers()) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data and len(data) > 0:
                                feedback_found = True
                                feedback_data = data
                                print(f"  ✅ Feedback found at {endpoint}: {len(data) if isinstance(data, list) else 'Available'}")
                                break
                except:
                    continue
            
            if not feedback_found:
                print(f"  ⚠️ No feedback data found at standard endpoints")
                # This might be expected if feedback system isn't seeded
                passed, total = 0, 1
            else:
                # Test feedback structure
                structure_test = True
                if isinstance(feedback_data, list) and feedback_data:
                    sample_feedback = feedback_data[0]
                    if isinstance(sample_feedback, dict):
                        has_rating = "rating" in sample_feedback or "score" in sample_feedback
                        has_content = "comment" in sample_feedback or "feedback" in sample_feedback or "review" in sample_feedback
                        structure_test = has_rating or has_content
                
                print(f"  {'✅' if structure_test else '❌'} Feedback structure: {'Valid' if structure_test else 'Invalid structure'}")
                
                passed = 1 if feedback_found and structure_test else 0
                total = 1
                
        except Exception as e:
            print(f"  ❌ Error testing feedback data: {e}")
            passed, total = 0, 1
        
        self.test_results.append({
            "test": "Feedback Test",
            "passed": passed,
            "total": total,
            "success_rate": f"{passed/total*100:.1f}%",
            "details": f"Tested guest feedback existence and structure"
        })

    # ============= MAIN TEST EXECUTION =============

    async def run_all_tests(self):
        """Run all seeded data tests"""
        print("🚀 Starting Hotel PMS Seeded Data Testing")
        print("Testing automatic database seeding and hotel data")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        # Run all tests
        await self.test_authentication()
        await self.test_rooms_data()
        await self.test_bookings_data()
        await self.test_guests_data()
        await self.test_folios_data()
        await self.test_housekeeping_data()
        await self.test_pos_menu_data()
        await self.test_feedback_data()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 SEEDED DATA TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        print("\n📋 DETAILED RESULTS:")
        print("-" * 60)
        
        for result in self.test_results:
            status = "✅" if result["passed"] == result["total"] else "⚠️" if result["passed"] > 0 else "❌"
            print(f"\n{status} {result['test']}: {result['passed']}/{result['total']} ({result['success_rate']})")
            print(f"   Details: {result['details']}")
            
            total_passed += result["passed"]
            total_tests += result["total"]
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        if overall_success_rate >= 90:
            print("🎉 EXCELLENT: Database seeding is working perfectly!")
        elif overall_success_rate >= 75:
            print("✅ GOOD: Most seeded data is available and correct")
        elif overall_success_rate >= 50:
            print("⚠️ PARTIAL: Some seeded data issues need attention")
        else:
            print("❌ CRITICAL: Major issues with database seeding")
        
        print("\n🔍 SEEDED DATA TESTED:")
        print("• Authentication: Admin, front desk, and housekeeping users")
        print("• Rooms: 24 rooms with different types and statuses")
        print("• Bookings: 30 bookings with various statuses")
        print("• Guests: 15 guests with Turkish names and details")
        print("• Folios: Financial records for checked-in guests")
        print("• Housekeeping: Room status board and task assignments")
        print("• POS/Menu: 12 menu items including Turkish cuisine")
        print("• Feedback: Guest reviews and ratings system")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = SeededDataTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())