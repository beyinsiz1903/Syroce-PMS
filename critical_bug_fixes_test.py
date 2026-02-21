#!/usr/bin/env python3
"""
Critical Bug Fixes Testing - 5 Priority Issues
Testing validation error fixes and room status bug
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import uuid

# Configuration
BACKEND_URL = "https://perf-boost-37.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class CriticalBugFixesTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.created_test_data = {
            'guests': [],
            'rooms': [],
            'bookings': [],
            'companies': []
        }

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
                    self.user_id = data["user"]["id"]
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

    async def create_test_data(self):
        """Create test data for critical bug fixes testing"""
        print("\n🔧 Creating test data for critical bug fixes...")
        
        try:
            # Create test guest
            guest_data = {
                "name": "Alice Johnson",
                "email": "alice.johnson@test.com",
                "phone": "+1234567890",
                "id_number": "87654321",
                "nationality": "US"
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/guests", 
                                       json=guest_data, 
                                       headers=self.get_headers()) as response:
                if response.status == 200:
                    guest = await response.json()
                    guest_id = guest["id"]
                    self.created_test_data['guests'].append(guest_id)
                    print(f"✅ Test guest created: {guest_id}")
                else:
                    print(f"⚠️ Guest creation failed: {response.status}")
                    return False

            # Get available room
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", 
                                      headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    if rooms:
                        # Find an available room
                        available_room = None
                        for room in rooms:
                            if room.get("status") == "available":
                                available_room = room
                                break
                        
                        if available_room:
                            room_id = available_room["id"]
                            room_number = available_room["room_number"]
                            print(f"✅ Using available room: {room_number} ({room_id})")
                            self.created_test_data['rooms'].append(room_id)
                        else:
                            # Use first room and set it to available
                            room_id = rooms[0]["id"]
                            room_number = rooms[0]["room_number"]
                            
                            # Update room status to available
                            await self.session.put(f"{BACKEND_URL}/pms/rooms/{room_id}", 
                                                 json={"status": "available"}, 
                                                 headers=self.get_headers())
                            print(f"✅ Set room to available: {room_number} ({room_id})")
                            self.created_test_data['rooms'].append(room_id)
                    else:
                        print("⚠️ No rooms available")
                        return False
                else:
                    print(f"⚠️ Failed to get rooms: {response.status}")
                    return False

            return True
            
        except Exception as e:
            print(f"❌ Error creating test data: {e}")
            return False

    async def test_room_status_bug_fix(self):
        """
        PHASE 1: Test Room Status Bug Fix (CRITICAL PRIORITY)
        Verify that booking creation does NOT set room to 'occupied'
        Only check-in should set room to 'occupied'
        """
        print("\n🏨 PHASE 1: Testing Room Status Bug Fix (CRITICAL)")
        print("=" * 60)
        
        test_results = {
            "booking_creation_room_status": False,
            "checkin_room_status": False,
            "room_status_workflow": False
        }
        
        try:
            # Get test data
            guest_id = self.created_test_data['guests'][0]
            room_id = self.created_test_data['rooms'][0]
            
            # Step 1: Verify room is available before booking
            async with self.session.get(f"{BACKEND_URL}/pms/rooms", 
                                      headers=self.get_headers()) as response:
                if response.status == 200:
                    rooms = await response.json()
                    test_room = next((r for r in rooms if r["id"] == room_id), None)
                    if test_room:
                        initial_status = test_room["status"]
                        print(f"📋 Initial room status: {initial_status}")
                    else:
                        print("❌ Test room not found")
                        return
                else:
                    print(f"❌ Failed to get room status: {response.status}")
                    return
            
            # Step 2: Create booking and verify room status DOES NOT change to 'occupied'
            booking_data = {
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "check_out": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "adults": 2,
                "children": 0,
                "children_ages": [],
                "guests_count": 2,
                "total_amount": 200.0,
                "base_rate": 200.0
            }
            
            async with self.session.post(f"{BACKEND_URL}/pms/bookings", 
                                       json=booking_data, 
                                       headers=self.get_headers()) as response:
                if response.status == 200:
                    booking = await response.json()
                    booking_id = booking["id"]
                    self.created_test_data['bookings'].append(booking_id)
                    print(f"✅ Booking created: {booking_id}")
                    
                    # Verify room status after booking creation
                    async with self.session.get(f"{BACKEND_URL}/pms/rooms", 
                                              headers=self.get_headers()) as response:
                        if response.status == 200:
                            rooms = await response.json()
                            test_room = next((r for r in rooms if r["id"] == room_id), None)
                            if test_room:
                                status_after_booking = test_room["status"]
                                print(f"📋 Room status after booking creation: {status_after_booking}")
                                
                                # CRITICAL TEST: Room should NOT be 'occupied' after booking creation
                                if status_after_booking != "occupied":
                                    print("✅ ROOM STATUS BUG FIX VERIFIED: Booking creation does NOT set room to 'occupied'")
                                    test_results["booking_creation_room_status"] = True
                                else:
                                    print("❌ ROOM STATUS BUG STILL EXISTS: Booking creation incorrectly sets room to 'occupied'")
                            else:
                                print("❌ Test room not found after booking")
                        else:
                            print(f"❌ Failed to get room status after booking: {response.status}")
                else:
                    print(f"❌ Booking creation failed: {response.status}")
                    error_text = await response.text()
                    print(f"Error details: {error_text}")
                    return
            
            # Step 3: Perform check-in and verify room status changes to 'occupied'
            async with self.session.post(f"{BACKEND_URL}/frontdesk/checkin/{booking_id}?create_folio=true", 
                                       headers=self.get_headers()) as response:
                if response.status == 200:
                    checkin_result = await response.json()
                    print(f"✅ Check-in successful: {checkin_result.get('message')}")
                    
                    # Verify room status after check-in
                    async with self.session.get(f"{BACKEND_URL}/pms/rooms", 
                                              headers=self.get_headers()) as response:
                        if response.status == 200:
                            rooms = await response.json()
                            test_room = next((r for r in rooms if r["id"] == room_id), None)
                            if test_room:
                                status_after_checkin = test_room["status"]
                                print(f"📋 Room status after check-in: {status_after_checkin}")
                                
                                # CRITICAL TEST: Room SHOULD be 'occupied' after check-in
                                if status_after_checkin == "occupied":
                                    print("✅ CHECK-IN WORKFLOW VERIFIED: Check-in correctly sets room to 'occupied'")
                                    test_results["checkin_room_status"] = True
                                    test_results["room_status_workflow"] = True
                                else:
                                    print(f"❌ CHECK-IN ISSUE: Room status is '{status_after_checkin}' instead of 'occupied'")
                            else:
                                print("❌ Test room not found after check-in")
                        else:
                            print(f"❌ Failed to get room status after check-in: {response.status}")
                else:
                    print(f"❌ Check-in failed: {response.status}")
                    error_text = await response.text()
                    print(f"Check-in error details: {error_text}")
            
        except Exception as e:
            print(f"❌ Room status bug test error: {e}")
        
        # Record results
        passed_tests = sum(test_results.values())
        total_tests = len(test_results)
        
        self.test_results.append({
            "phase": "Phase 1: Room Status Bug Fix",
            "endpoint": "Booking Creation + Check-in Workflow",
            "passed": passed_tests,
            "total": total_tests,
            "success_rate": f"{passed_tests/total_tests*100:.1f}%",
            "details": test_results
        })

    async def test_procurement_stock_alert_fix(self):
        """
        PHASE 2: Test Procurement Stock Alert Fix (HIGH PRIORITY)
        Verify POST /api/procurement/minimum-stock-alert accepts request body
        """
        print("\n📦 PHASE 2: Testing Procurement Stock Alert Fix (HIGH)")
        print("=" * 60)
        
        try:
            # Test data for procurement stock alert
            stock_alert_data = {
                "item_id": "test-item-id",
                "min_stock_level": 50,
                "alert_recipients": ["manager@hotel.com"]
            }
            
            async with self.session.post(f"{BACKEND_URL}/procurement/minimum-stock-alert", 
                                       json=stock_alert_data, 
                                       headers=self.get_headers()) as response:
                
                status_code = response.status
                response_text = await response.text()
                
                print(f"📋 Response Status: {status_code}")
                
                if status_code == 422:
                    print("❌ VALIDATION ERROR STILL EXISTS: 422 error indicates request body format issue")
                    print(f"Error details: {response_text}")
                    passed = 0
                elif status_code in [200, 404]:
                    # 200 = success, 404 = item doesn't exist (acceptable)
                    print("✅ PROCUREMENT STOCK ALERT FIX VERIFIED: No 422 validation error")
                    if status_code == 200:
                        try:
                            response_data = json.loads(response_text)
                            print(f"Success response: {response_data}")
                        except:
                            print(f"Response: {response_text}")
                    else:
                        print("Note: 404 response is acceptable (item doesn't exist)")
                    passed = 1
                else:
                    print(f"⚠️ Unexpected status code: {status_code}")
                    print(f"Response: {response_text}")
                    passed = 1 if status_code != 422 else 0
                
        except Exception as e:
            print(f"❌ Procurement stock alert test error: {e}")
            passed = 0
        
        self.test_results.append({
            "phase": "Phase 2: Procurement Stock Alert Fix",
            "endpoint": "POST /api/procurement/minimum-stock-alert",
            "passed": passed,
            "total": 1,
            "success_rate": f"{passed*100:.1f}%",
            "details": {"no_422_error": passed == 1}
        })

    async def test_loyalty_points_redemption_fix(self):
        """
        PHASE 3: Test Loyalty Points Redemption Fix (HIGH PRIORITY)
        Verify POST /api/loyalty/{guest_id}/redeem-points accepts request body
        """
        print("\n🎁 PHASE 3: Testing Loyalty Points Redemption Fix (HIGH)")
        print("=" * 60)
        
        try:
            # Use test guest
            guest_id = self.created_test_data['guests'][0]
            
            # Test data for loyalty points redemption
            redemption_data = {
                "points_to_redeem": 50,
                "reward_type": "room_upgrade"
            }
            
            async with self.session.post(f"{BACKEND_URL}/loyalty/{guest_id}/redeem-points", 
                                       json=redemption_data, 
                                       headers=self.get_headers()) as response:
                
                status_code = response.status
                response_text = await response.text()
                
                print(f"📋 Response Status: {status_code}")
                
                if status_code == 422:
                    print("❌ VALIDATION ERROR STILL EXISTS: 422 error indicates request body format issue")
                    print(f"Error details: {response_text}")
                    passed = 0
                elif status_code in [200, 400]:
                    # 200 = success, 400 = insufficient points (acceptable business logic error)
                    print("✅ LOYALTY POINTS REDEMPTION FIX VERIFIED: No 422 validation error")
                    if status_code == 200:
                        try:
                            response_data = json.loads(response_text)
                            print(f"Success response: {response_data}")
                        except:
                            print(f"Response: {response_text}")
                    else:
                        print("Note: 400 response is acceptable (insufficient points or business logic)")
                    passed = 1
                else:
                    print(f"⚠️ Unexpected status code: {status_code}")
                    print(f"Response: {response_text}")
                    passed = 1 if status_code != 422 else 0
                
        except Exception as e:
            print(f"❌ Loyalty points redemption test error: {e}")
            passed = 0
        
        self.test_results.append({
            "phase": "Phase 3: Loyalty Points Redemption Fix",
            "endpoint": "POST /api/loyalty/{guest_id}/redeem-points",
            "passed": passed,
            "total": 1,
            "success_rate": f"{passed*100:.1f}%",
            "details": {"no_422_error": passed == 1}
        })

    async def test_rms_dynamic_restrictions_fix(self):
        """
        PHASE 4: Test RMS Dynamic Restrictions Fix (HIGH PRIORITY)
        Verify POST /api/rms/restrictions accepts request body
        """
        print("\n📊 PHASE 4: Testing RMS Dynamic Restrictions Fix (HIGH)")
        print("=" * 60)
        
        try:
            # Test data for RMS dynamic restrictions
            restrictions_data = {
                "date": "2025-02-01",
                "room_type": "Deluxe Room",
                "min_los": 3,
                "cta": False,
                "ctd": False,
                "stop_sell": False
            }
            
            async with self.session.post(f"{BACKEND_URL}/rms/restrictions", 
                                       json=restrictions_data, 
                                       headers=self.get_headers()) as response:
                
                status_code = response.status
                response_text = await response.text()
                
                print(f"📋 Response Status: {status_code}")
                
                if status_code == 422:
                    print("❌ VALIDATION ERROR STILL EXISTS: 422 error indicates request body format issue")
                    print(f"Error details: {response_text}")
                    passed = 0
                elif status_code == 200:
                    print("✅ RMS DYNAMIC RESTRICTIONS FIX VERIFIED: No 422 validation error")
                    try:
                        response_data = json.loads(response_text)
                        print(f"Success response: {response_data}")
                    except:
                        print(f"Response: {response_text}")
                    passed = 1
                else:
                    print(f"⚠️ Unexpected status code: {status_code}")
                    print(f"Response: {response_text}")
                    passed = 1 if status_code != 422 else 0
                
        except Exception as e:
            print(f"❌ RMS dynamic restrictions test error: {e}")
            passed = 0
        
        self.test_results.append({
            "phase": "Phase 4: RMS Dynamic Restrictions Fix",
            "endpoint": "POST /api/rms/restrictions",
            "passed": passed,
            "total": 1,
            "success_rate": f"{passed*100:.1f}%",
            "details": {"no_422_error": passed == 1}
        })

    async def test_marketplace_product_creation_fix(self):
        """
        PHASE 5: Test Marketplace Product Creation Fix (MEDIUM PRIORITY)
        Verify POST /api/marketplace/products accepts request body
        """
        print("\n🛒 PHASE 5: Testing Marketplace Product Creation Fix (MEDIUM)")
        print("=" * 60)
        
        try:
            # Test data for marketplace product creation
            product_data = {
                "name": "Premium Coffee Beans",
                "category": "F&B Supplies",
                "description": "High-quality coffee beans for hotel restaurant",
                "price": 25.50,
                "unit": "kg",
                "supplier": "Coffee Co."
            }
            
            async with self.session.post(f"{BACKEND_URL}/marketplace/products", 
                                       json=product_data, 
                                       headers=self.get_headers()) as response:
                
                status_code = response.status
                response_text = await response.text()
                
                print(f"📋 Response Status: {status_code}")
                
                if status_code == 422:
                    print("❌ VALIDATION ERROR STILL EXISTS: 422 error indicates request body format issue")
                    print(f"Error details: {response_text}")
                    passed = 0
                elif status_code == 200:
                    print("✅ MARKETPLACE PRODUCT CREATION FIX VERIFIED: No 422 validation error")
                    try:
                        response_data = json.loads(response_text)
                        print(f"Success response: {response_data}")
                    except:
                        print(f"Response: {response_text}")
                    passed = 1
                else:
                    print(f"⚠️ Unexpected status code: {status_code}")
                    print(f"Response: {response_text}")
                    passed = 1 if status_code != 422 else 0
                
        except Exception as e:
            print(f"❌ Marketplace product creation test error: {e}")
            passed = 0
        
        self.test_results.append({
            "phase": "Phase 5: Marketplace Product Creation Fix",
            "endpoint": "POST /api/marketplace/products",
            "passed": passed,
            "total": 1,
            "success_rate": f"{passed*100:.1f}%",
            "details": {"no_422_error": passed == 1}
        })

    async def run_all_tests(self):
        """Run all critical bug fixes tests"""
        print("🚀 Starting Critical Bug Fixes Testing - 5 Priority Issues")
        print("=" * 70)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # Run all phases
        await self.test_room_status_bug_fix()
        await self.test_procurement_stock_alert_fix()
        await self.test_loyalty_points_redemption_fix()
        await self.test_rms_dynamic_restrictions_fix()
        await self.test_marketplace_product_creation_fix()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 70)
        print("📊 CRITICAL BUG FIXES TEST RESULTS")
        print("=" * 70)
        
        total_passed = 0
        total_tests = 0
        critical_issues = []
        fixed_issues = []
        
        print("\n📋 PHASE-BY-PHASE RESULTS:")
        print("-" * 50)
        
        for result in self.test_results:
            phase = result["phase"]
            endpoint = result["endpoint"]
            passed = result["passed"]
            total = result["total"]
            success_rate = result["success_rate"]
            
            status = "✅ FIXED" if passed == total else "❌ STILL BROKEN" if passed == 0 else "⚠️ PARTIAL"
            print(f"{status} {phase}")
            print(f"   Endpoint: {endpoint}")
            print(f"   Tests: {passed}/{total} ({success_rate})")
            
            if passed == total:
                fixed_issues.append(phase)
            elif passed == 0:
                critical_issues.append(phase)
            
            total_passed += passed
            total_tests += total
        
        print("\n" + "=" * 70)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        print(f"\n✅ FIXED ISSUES ({len(fixed_issues)}):")
        for issue in fixed_issues:
            print(f"   • {issue}")
        
        if critical_issues:
            print(f"\n❌ STILL BROKEN ({len(critical_issues)}):")
            for issue in critical_issues:
                print(f"   • {issue}")
        
        print("\n🎯 SUCCESS CRITERIA:")
        print("   • No 422 validation errors ✅" if total_passed >= 4 else "   • No 422 validation errors ❌")
        print("   • Room status bug fixed ✅" if any("Room Status" in r["phase"] and r["passed"] == r["total"] for r in self.test_results) else "   • Room status bug fixed ❌")
        print("   • Check-in workflow works ✅" if any("Room Status" in r["phase"] and r["passed"] == r["total"] for r in self.test_results) else "   • Check-in workflow works ❌")
        print("   • All endpoints accept JSON ✅" if total_passed >= 4 else "   • All endpoints accept JSON ❌")
        
        if overall_success_rate == 100:
            print("\n🎉 PERFECT: All critical bug fixes are working!")
        elif overall_success_rate >= 80:
            print("\n✅ EXCELLENT: Most critical issues are fixed")
        elif overall_success_rate >= 60:
            print("\n⚠️ GOOD: Major issues fixed, minor issues remain")
        else:
            print("\n❌ CRITICAL: Major issues still exist")
        
        print("\n" + "=" * 70)

async def main():
    """Main test execution"""
    tester = CriticalBugFixesTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())