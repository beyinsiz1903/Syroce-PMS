#!/usr/bin/env python3
"""
Backend API Test Suite - Post-Modularization Validation
Testing all critical PMS endpoints after code extraction to validate modularization.

Test Coverage:
1. Auth: POST /api/auth/login + GET /api/auth/me
2. PMS Dashboard: GET /api/pms/dashboard  
3. Rooms: GET /api/pms/rooms
4. Bookings: GET /api/pms/bookings
5. Guests: GET /api/pms/guests
6. Housekeeping: GET /api/housekeeping/tasks
7. Folio: GET /api/folio/list
8. Reports: GET /api/reports/daily-flash
9. Channel Manager: GET /api/channel-manager/connections

Login: demo@hotel.com / demo123
"""

import asyncio
import aiohttp
import json
from datetime import datetime

# Configuration
BASE_URL = "https://code-cleanup-135.preview.emergentagent.com"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class SyrocePMSTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.access_token = None
        self.user_data = None
        self.tenant_data = None
        self.results = {}

    async def login(self, session):
        """Authenticate and get JWT token"""
        print("🔐 Testing Authentication...")
        login_url = f"{self.base_url}/api/auth/login"
        login_data = {
            "email": LOGIN_EMAIL,
            "password": LOGIN_PASSWORD
        }
        
        try:
            async with session.post(login_url, json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data.get("access_token")
                    self.user_data = data.get("user")
                    self.tenant_data = data.get("tenant")
                    
                    print(f"✅ LOGIN SUCCESS: {response.status}")
                    print(f"   User: {self.user_data.get('name')} ({self.user_data.get('email')})")
                    print(f"   Tenant: {self.tenant_data.get('property_name')}")
                    
                    self.results["auth_login"] = {
                        "status": response.status,
                        "success": True,
                        "has_token": bool(self.access_token),
                        "has_user": bool(self.user_data),
                        "has_tenant": bool(self.tenant_data)
                    }
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ LOGIN FAILED: {response.status} - {error_text}")
                    self.results["auth_login"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
                    return False
        except Exception as e:
            print(f"❌ LOGIN ERROR: {str(e)}")
            self.results["auth_login"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }
            return False

    async def test_auth_me(self, session):
        """Test GET /api/auth/me"""
        print("\n🔐 Testing Auth Me...")
        url = f"{self.base_url}/api/auth/me"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ AUTH ME SUCCESS: {response.status}")
                    print(f"   Email: {data.get('email')}")
                    print(f"   Role: {data.get('role')}")
                    
                    self.results["auth_me"] = {
                        "status": response.status,
                        "success": True,
                        "email": data.get("email"),
                        "role": data.get("role")
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ AUTH ME FAILED: {response.status} - {error_text}")
                    self.results["auth_me"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ AUTH ME ERROR: {str(e)}")
            self.results["auth_me"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_pms_dashboard(self, session):
        """Test GET /api/pms/dashboard"""
        print("\n📊 Testing PMS Dashboard...")
        url = f"{self.base_url}/api/pms/dashboard"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ DASHBOARD SUCCESS: {response.status}")
                    print(f"   Total Rooms: {data.get('total_rooms')}")
                    print(f"   Occupied Rooms: {data.get('occupied_rooms')}")
                    print(f"   Total Guests: {data.get('total_guests')}")
                    
                    self.results["pms_dashboard"] = {
                        "status": response.status,
                        "success": True,
                        "total_rooms": data.get("total_rooms"),
                        "occupied_rooms": data.get("occupied_rooms"),
                        "total_guests": data.get("total_guests"),
                        "has_data": bool(data.get("total_rooms"))
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ DASHBOARD FAILED: {response.status} - {error_text}")
                    self.results["pms_dashboard"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ DASHBOARD ERROR: {str(e)}")
            self.results["pms_dashboard"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_pms_rooms(self, session):
        """Test GET /api/pms/rooms"""
        print("\n🏨 Testing PMS Rooms...")
        url = f"{self.base_url}/api/pms/rooms?limit=5"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    rooms_list = data if isinstance(data, list) else data.get("rooms", [])
                    print(f"✅ ROOMS SUCCESS: {response.status}")
                    print(f"   Rooms Count: {len(rooms_list)}")
                    if rooms_list:
                        first_room = rooms_list[0]
                        print(f"   First Room: {first_room.get('room_number')} - {first_room.get('room_type')}")
                    
                    self.results["pms_rooms"] = {
                        "status": response.status,
                        "success": True,
                        "count": len(rooms_list),
                        "has_data": len(rooms_list) > 0
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ ROOMS FAILED: {response.status} - {error_text}")
                    self.results["pms_rooms"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ ROOMS ERROR: {str(e)}")
            self.results["pms_rooms"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_pms_bookings(self, session):
        """Test GET /api/pms/bookings"""
        print("\n📋 Testing PMS Bookings...")
        url = f"{self.base_url}/api/pms/bookings?limit=5"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    bookings_list = data if isinstance(data, list) else data.get("bookings", [])
                    print(f"✅ BOOKINGS SUCCESS: {response.status}")
                    print(f"   Bookings Count: {len(bookings_list)}")
                    if bookings_list:
                        first_booking = bookings_list[0]
                        print(f"   First Booking: {first_booking.get('guest_name')} - {first_booking.get('status')}")
                    
                    self.results["pms_bookings"] = {
                        "status": response.status,
                        "success": True,
                        "count": len(bookings_list),
                        "has_data": len(bookings_list) > 0
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ BOOKINGS FAILED: {response.status} - {error_text}")
                    self.results["pms_bookings"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ BOOKINGS ERROR: {str(e)}")
            self.results["pms_bookings"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_pms_guests(self, session):
        """Test GET /api/pms/guests"""
        print("\n👥 Testing PMS Guests...")
        url = f"{self.base_url}/api/pms/guests?limit=5"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    guests_list = data if isinstance(data, list) else data.get("guests", [])
                    print(f"✅ GUESTS SUCCESS: {response.status}")
                    print(f"   Guests Count: {len(guests_list)}")
                    if guests_list:
                        first_guest = guests_list[0]
                        print(f"   First Guest: {first_guest.get('name')} - {first_guest.get('email')}")
                    
                    self.results["pms_guests"] = {
                        "status": response.status,
                        "success": True,
                        "count": len(guests_list),
                        "has_data": len(guests_list) > 0
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ GUESTS FAILED: {response.status} - {error_text}")
                    self.results["pms_guests"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ GUESTS ERROR: {str(e)}")
            self.results["pms_guests"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_housekeeping_tasks(self, session):
        """Test GET /api/housekeeping/tasks"""
        print("\n🧹 Testing Housekeeping Tasks...")
        url = f"{self.base_url}/api/housekeeping/tasks"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    tasks_list = data if isinstance(data, list) else data.get("tasks", [])
                    print(f"✅ HOUSEKEEPING SUCCESS: {response.status}")
                    print(f"   Tasks Count: {len(tasks_list)}")
                    if tasks_list:
                        first_task = tasks_list[0]
                        print(f"   First Task: {first_task.get('room_number')} - {first_task.get('task_type')}")
                    
                    self.results["housekeeping_tasks"] = {
                        "status": response.status,
                        "success": True,
                        "count": len(tasks_list),
                        "has_data": len(tasks_list) > 0
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ HOUSEKEEPING FAILED: {response.status} - {error_text}")
                    self.results["housekeeping_tasks"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ HOUSEKEEPING ERROR: {str(e)}")
            self.results["housekeeping_tasks"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_folio_list(self, session):
        """Test GET /api/folio/list"""
        print("\n💰 Testing Folio List...")
        url = f"{self.base_url}/api/folio/list"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    folios_list = data if isinstance(data, list) else data.get("folios", [])
                    print(f"✅ FOLIO SUCCESS: {response.status}")
                    print(f"   Folios Count: {len(folios_list)}")
                    if folios_list:
                        first_folio = folios_list[0]
                        print(f"   First Folio: {first_folio.get('folio_number')} - {first_folio.get('guest_name')}")
                    
                    self.results["folio_list"] = {
                        "status": response.status,
                        "success": True,
                        "count": len(folios_list),
                        "has_data": len(folios_list) > 0
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ FOLIO FAILED: {response.status} - {error_text}")
                    self.results["folio_list"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ FOLIO ERROR: {str(e)}")
            self.results["folio_list"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_reports_daily_flash(self, session):
        """Test GET /api/reports/daily-flash"""
        print("\n📈 Testing Reports Daily Flash...")
        url = f"{self.base_url}/api/reports/daily-flash"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ DAILY FLASH SUCCESS: {response.status}")
                    print(f"   Report Date: {data.get('date')}")
                    print(f"   Occupancy: {data.get('occupancy_percentage')}%")
                    print(f"   Revenue: {data.get('total_revenue')}")
                    
                    self.results["reports_daily_flash"] = {
                        "status": response.status,
                        "success": True,
                        "has_data": bool(data.get("date") or data.get("occupancy_percentage") is not None),
                        "occupancy": data.get("occupancy_percentage"),
                        "revenue": data.get("total_revenue")
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ DAILY FLASH FAILED: {response.status} - {error_text}")
                    self.results["reports_daily_flash"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ DAILY FLASH ERROR: {str(e)}")
            self.results["reports_daily_flash"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    async def test_channel_manager_connections(self, session):
        """Test GET /api/channel-manager/connections"""
        print("\n🌐 Testing Channel Manager Connections...")
        url = f"{self.base_url}/api/channel-manager/connections"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    connections_list = data if isinstance(data, list) else data.get("connections", [])
                    print(f"✅ CHANNEL MANAGER SUCCESS: {response.status}")
                    print(f"   Connections Count: {len(connections_list)}")
                    if connections_list:
                        first_connection = connections_list[0]
                        print(f"   First Connection: {first_connection.get('channel_name')} - {first_connection.get('status')}")
                    
                    self.results["channel_manager_connections"] = {
                        "status": response.status,
                        "success": True,
                        "count": len(connections_list),
                        "has_data": len(connections_list) > 0
                    }
                else:
                    error_text = await response.text()
                    print(f"❌ CHANNEL MANAGER FAILED: {response.status} - {error_text}")
                    self.results["channel_manager_connections"] = {
                        "status": response.status,
                        "success": False,
                        "error": error_text
                    }
        except Exception as e:
            print(f"❌ CHANNEL MANAGER ERROR: {str(e)}")
            self.results["channel_manager_connections"] = {
                "status": 0,
                "success": False,
                "error": str(e)
            }

    def print_summary(self):
        """Print comprehensive test results summary"""
        print("\n" + "="*80)
        print("🎯 SYROCE PMS POST-MODULARIZATION TEST SUMMARY")
        print("="*80)
        
        total_tests = len(self.results)
        successful_tests = sum(1 for result in self.results.values() if result.get("success", False))
        
        print(f"📊 TOTAL TESTS: {total_tests}")
        print(f"✅ SUCCESSFUL: {successful_tests}")
        print(f"❌ FAILED: {total_tests - successful_tests}")
        print(f"📈 SUCCESS RATE: {(successful_tests/total_tests)*100:.1f}%")
        
        print("\n📋 DETAILED RESULTS:")
        print("-" * 80)
        
        for test_name, result in self.results.items():
            status_emoji = "✅" if result.get("success") else "❌"
            status_code = result.get("status", "N/A")
            
            print(f"{status_emoji} {test_name.upper()}: HTTP {status_code}")
            
            if result.get("success"):
                # Show additional success details
                if test_name == "auth_login":
                    print(f"   └─ Token: {'Yes' if result.get('has_token') else 'No'}")
                    print(f"   └─ User Data: {'Yes' if result.get('has_user') else 'No'}")
                    print(f"   └─ Tenant Data: {'Yes' if result.get('has_tenant') else 'No'}")
                elif "count" in result:
                    print(f"   └─ Records: {result['count']} (Data: {'Yes' if result.get('has_data') else 'No'})")
                elif test_name == "pms_dashboard":
                    print(f"   └─ Rooms: {result.get('total_rooms')}, Occupied: {result.get('occupied_rooms')}, Guests: {result.get('total_guests')}")
                elif test_name == "reports_daily_flash":
                    print(f"   └─ Occupancy: {result.get('occupancy')}%, Revenue: {result.get('revenue')}")
            else:
                # Show error details
                error = result.get("error", "Unknown error")
                if len(error) > 60:
                    error = error[:60] + "..."
                print(f"   └─ Error: {error}")
        
        print("\n🎯 MODULARIZATION VALIDATION:")
        print("-" * 80)
        
        # Critical endpoints that must work after modularization
        critical_endpoints = [
            "auth_login", "auth_me", "pms_dashboard", "pms_rooms", 
            "pms_bookings", "pms_guests", "housekeeping_tasks"
        ]
        
        critical_success = sum(1 for endpoint in critical_endpoints 
                              if self.results.get(endpoint, {}).get("success", False))
        
        print(f"🔑 CRITICAL ENDPOINTS: {critical_success}/{len(critical_endpoints)} working")
        
        if critical_success == len(critical_endpoints):
            print("✅ MODULARIZATION SUCCESSFUL: All core PMS functions operational")
        else:
            failed_critical = [endpoint for endpoint in critical_endpoints 
                             if not self.results.get(endpoint, {}).get("success", False)]
            print(f"❌ MODULARIZATION ISSUES: {failed_critical} endpoints failing")
        
        # Optional endpoints (may not be implemented yet)
        optional_endpoints = ["folio_list", "reports_daily_flash", "channel_manager_connections"]
        optional_success = sum(1 for endpoint in optional_endpoints 
                              if self.results.get(endpoint, {}).get("success", False))
        
        print(f"🔧 OPTIONAL ENDPOINTS: {optional_success}/{len(optional_endpoints)} working")
        
        print("\n" + "="*80)
        return successful_tests == total_tests

    async def run_all_tests(self):
        """Execute all tests in sequence"""
        print("🚀 Starting Syroce PMS API Test Suite...")
        print(f"🎯 Target: {self.base_url}")
        print(f"👤 Login: {LOGIN_EMAIL}")
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            # Step 1: Authentication
            if not await self.login(session):
                print("\n❌ CRITICAL: Login failed - cannot proceed with tests")
                return False
            
            # Step 2: Test auth/me 
            await self.test_auth_me(session)
            
            # Step 3: Test all PMS endpoints
            await self.test_pms_dashboard(session)
            await self.test_pms_rooms(session)
            await self.test_pms_bookings(session)
            await self.test_pms_guests(session)
            await self.test_housekeeping_tasks(session)
            
            # Step 4: Test optional endpoints
            await self.test_folio_list(session)
            await self.test_reports_daily_flash(session)
            await self.test_channel_manager_connections(session)
        
        # Step 5: Print results summary
        return self.print_summary()

async def main():
    """Main test execution"""
    tester = SyrocePMSTester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 ALL TESTS PASSED - Modularization validation successful!")
        exit(0)
    else:
        print("\n⚠️ SOME TESTS FAILED - Check results above for details")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())