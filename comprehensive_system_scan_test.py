#!/usr/bin/env python3
"""
COMPREHENSIVE SYSTEM SCAN - Find Any Remaining Issues

This test performs a comprehensive scan of ALL major endpoints to find any remaining issues:

**TEST ALL MAJOR MODULES (Sample 5-10 endpoints from each):**

1. **PMS Module:**
   - GET /api/pms/rooms
   - GET /api/pms/bookings
   - GET /api/pms/guests
   - POST /api/pms/check-in/{booking_id}
   - POST /api/pms/check-out/{booking_id}

2. **Folio System:**
   - GET /api/folio/booking/{booking_id}
   - POST /api/folio/create
   - POST /api/folio/{folio_id}/charge
   - POST /api/folio/{folio_id}/payment

3. **Housekeeping:**
   - GET /api/housekeeping/tasks
   - GET /api/housekeeping/room-status
   - POST /api/housekeeping/task/{task_id}/complete

4. **Revenue Management:**
   - GET /api/revenue/pickup-analysis
   - GET /api/revenue/pace-report
   - GET /api/rms/demand-heatmap

5. **Mobile Endpoints:**
   - GET /api/pos/mobile/active-orders
   - GET /api/pos/mobile/stock-levels
   - GET /api/housekeeping/mobile/room-assignments

6. **Executive/GM Dashboard:**
   - GET /api/executive/kpi-snapshot
   - GET /api/executive/performance-alerts
   - GET /api/gm/team-performance

7. **Performance Check:**
   - Measure response times for all endpoints
   - Identify any slow endpoints (>500ms)
   - Check for any timeout issues

**REPORT:**
- Total endpoints tested
- Success rate
- Any failing endpoints with details
- Slow endpoints (>500ms) that need optimization
- Any 422, 500, or timeout errors

Target: 100% success, all responses <500ms
"""

import asyncio
import aiohttp
import json
import sys
import os
import time
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Any, Optional
import uuid

# Configuration
BACKEND_URL = "https://guest-messaging-1.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class ComprehensiveSystemScanner:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.slow_endpoints = []
        self.failed_endpoints = []
        self.created_test_data = {
            'guests': [],
            'bookings': [],
            'rooms': [],
            'folios': [],
            'tasks': []
        }

    async def setup_session(self):
        """Initialize HTTP session"""
        timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
        self.session = aiohttp.ClientSession(timeout=timeout)

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

    async def make_request(self, method: str, endpoint: str, data: dict = None, params: dict = None):
        """Make HTTP request and measure response time"""
        start_time = time.time()
        url = f"{BACKEND_URL}{endpoint}"
        
        try:
            if method.upper() == "GET":
                async with self.session.get(url, headers=self.get_headers(), params=params) as response:
                    response_time = (time.time() - start_time) * 1000  # Convert to ms
                    response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                    return {
                        "status": response.status,
                        "data": response_data,
                        "response_time": response_time,
                        "success": 200 <= response.status < 300
                    }
            elif method.upper() == "POST":
                async with self.session.post(url, json=data, headers=self.get_headers(), params=params) as response:
                    response_time = (time.time() - start_time) * 1000
                    response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                    return {
                        "status": response.status,
                        "data": response_data,
                        "response_time": response_time,
                        "success": 200 <= response.status < 300
                    }
            elif method.upper() == "PUT":
                async with self.session.put(url, json=data, headers=self.get_headers(), params=params) as response:
                    response_time = (time.time() - start_time) * 1000
                    response_data = await response.json() if response.content_type == 'application/json' else await response.text()
                    return {
                        "status": response.status,
                        "data": response_data,
                        "response_time": response_time,
                        "success": 200 <= response.status < 300
                    }
        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return {
                "status": 408,
                "data": "Request timeout",
                "response_time": response_time,
                "success": False
            }
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {
                "status": 500,
                "data": str(e),
                "response_time": response_time,
                "success": False
            }

    async def create_test_data(self):
        """Create comprehensive test data for all modules"""
        print("\n🔧 Creating test data for comprehensive system scan...")
        
        try:
            # Create test guest
            guest_data = {
                "name": "System Test Guest",
                "email": "systemtest@hotel.com",
                "phone": "+1-555-9999",
                "id_number": "SYS123456789",
                "nationality": "US",
                "vip_status": False
            }
            
            result = await self.make_request("POST", "/pms/guests", guest_data)
            if result["success"]:
                guest_id = result["data"]["id"]
                self.created_test_data['guests'].append(guest_id)
                print(f"✅ Test guest created: {guest_id}")
            else:
                print(f"⚠️ Guest creation failed: {result['status']}")
                return False

            # Get available room
            result = await self.make_request("GET", "/pms/rooms")
            if result["success"] and result["data"]:
                room_id = result["data"][0]["id"]
                self.created_test_data['rooms'].append(room_id)
                print(f"✅ Using room: {room_id}")
            else:
                print("⚠️ No rooms available")
                return False

            # Create test booking
            booking_data = {
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": (datetime.now(timezone.utc)).isoformat(),
                "check_out": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "adults": 2,
                "children": 0,
                "children_ages": [],
                "guests_count": 2,
                "total_amount": 300.0,
                "special_requests": "System test booking"
            }
            
            result = await self.make_request("POST", "/pms/bookings", booking_data)
            if result["success"]:
                booking_id = result["data"]["id"]
                self.created_test_data['bookings'].append(booking_id)
                print(f"✅ Test booking created: {booking_id}")
            else:
                print(f"⚠️ Booking creation failed: {result['status']}")
                return False

            # Create folio for booking
            folio_data = {
                "booking_id": booking_id,
                "folio_type": "guest"
            }
            
            result = await self.make_request("POST", "/folio/create", folio_data)
            if result["success"]:
                folio_id = result["data"]["id"]
                self.created_test_data['folios'].append(folio_id)
                print(f"✅ Test folio created: {folio_id}")
            else:
                print(f"⚠️ Folio creation failed: {result['status']}")

            print(f"✅ Test data creation completed")
            return True
            
        except Exception as e:
            print(f"❌ Error creating test data: {e}")
            return False

    # ============= PMS MODULE TESTS =============

    async def test_pms_module(self):
        """Test PMS Module endpoints"""
        print("\n🏨 Testing PMS Module (5 endpoints)...")
        
        endpoints = [
            {
                "name": "Get Rooms",
                "method": "GET",
                "endpoint": "/pms/rooms",
                "expected_fields": ["id", "room_number", "room_type", "status"]
            },
            {
                "name": "Get Bookings",
                "method": "GET", 
                "endpoint": "/pms/bookings",
                "params": {"limit": 10},
                "expected_fields": ["id", "guest_id", "room_id", "status"]
            },
            {
                "name": "Get Guests",
                "method": "GET",
                "endpoint": "/pms/guests",
                "expected_fields": ["id", "name", "email", "phone"]
            }
        ]

        # Add check-in/check-out tests if we have bookings
        if self.created_test_data['bookings']:
            booking_id = self.created_test_data['bookings'][0]
            endpoints.extend([
                {
                    "name": "Check-in Booking",
                    "method": "POST",
                    "endpoint": f"/pms/check-in/{booking_id}",
                    "data": {"notes": "System test check-in"}
                },
                {
                    "name": "Check-out Booking", 
                    "method": "POST",
                    "endpoint": f"/pms/check-out/{booking_id}",
                    "data": {"notes": "System test check-out"}
                }
            ])

        return await self.test_endpoints("PMS Module", endpoints)

    # ============= FOLIO SYSTEM TESTS =============

    async def test_folio_system(self):
        """Test Folio System endpoints"""
        print("\n💰 Testing Folio System (4 endpoints)...")
        
        endpoints = []
        
        if self.created_test_data['bookings']:
            booking_id = self.created_test_data['bookings'][0]
            endpoints.append({
                "name": "Get Folio by Booking",
                "method": "GET",
                "endpoint": f"/folio/booking/{booking_id}",
                "expected_fields": ["id", "folio_number", "balance"]
            })

        endpoints.append({
            "name": "Create Folio",
            "method": "POST",
            "endpoint": "/folio/create",
            "data": {
                "booking_id": self.created_test_data['bookings'][0] if self.created_test_data['bookings'] else str(uuid.uuid4()),
                "folio_type": "guest"
            }
        })

        if self.created_test_data['folios']:
            folio_id = self.created_test_data['folios'][0]
            endpoints.extend([
                {
                    "name": "Post Charge to Folio",
                    "method": "POST",
                    "endpoint": f"/folio/{folio_id}/charge",
                    "data": {
                        "charge_category": "room",
                        "description": "Room charge",
                        "amount": 100.0,
                        "quantity": 1.0
                    }
                },
                {
                    "name": "Post Payment to Folio",
                    "method": "POST", 
                    "endpoint": f"/folio/{folio_id}/payment",
                    "data": {
                        "amount": 50.0,
                        "method": "card",
                        "payment_type": "interim"
                    }
                }
            ])

        return await self.test_endpoints("Folio System", endpoints)

    # ============= HOUSEKEEPING TESTS =============

    async def test_housekeeping_module(self):
        """Test Housekeeping Module endpoints"""
        print("\n🧹 Testing Housekeeping Module (3 endpoints)...")
        
        endpoints = [
            {
                "name": "Get Housekeeping Tasks",
                "method": "GET",
                "endpoint": "/housekeeping/tasks",
                "expected_fields": ["id", "room_id", "task_type", "status"]
            },
            {
                "name": "Get Room Status",
                "method": "GET",
                "endpoint": "/housekeeping/room-status",
                "expected_fields": ["room_id", "status", "last_cleaned"]
            },
            {
                "name": "Get Mobile Room Assignments",
                "method": "GET",
                "endpoint": "/housekeeping/mobile/room-assignments",
                "expected_fields": ["assignments", "total_count"]
            }
        ]

        return await self.test_endpoints("Housekeeping Module", endpoints)

    # ============= REVENUE MANAGEMENT TESTS =============

    async def test_revenue_management(self):
        """Test Revenue Management endpoints"""
        print("\n📊 Testing Revenue Management (3 endpoints)...")
        
        endpoints = [
            {
                "name": "Get Demand Heatmap",
                "method": "GET",
                "endpoint": "/rms/demand-heatmap",
                "expected_fields": ["heatmap_data"]
            },
            {
                "name": "Get Revenue Pickup Analysis",
                "method": "GET",
                "endpoint": "/revenue/pickup-analysis",
                "params": {"days": 30}
            },
            {
                "name": "Get Revenue Pace Report",
                "method": "GET",
                "endpoint": "/revenue/pace-report",
                "params": {"period": "weekly"}
            }
        ]

        return await self.test_endpoints("Revenue Management", endpoints)

    # ============= MOBILE ENDPOINTS TESTS =============

    async def test_mobile_endpoints(self):
        """Test Mobile endpoints"""
        print("\n📱 Testing Mobile Endpoints (3 endpoints)...")
        
        endpoints = [
            {
                "name": "Get POS Mobile Active Orders",
                "method": "GET",
                "endpoint": "/pos/mobile/active-orders"
            },
            {
                "name": "Get POS Mobile Stock Levels",
                "method": "GET",
                "endpoint": "/pos/mobile/stock-levels"
            },
            {
                "name": "Get Housekeeping Mobile Room Assignments",
                "method": "GET",
                "endpoint": "/housekeeping/mobile/room-assignments"
            }
        ]

        return await self.test_endpoints("Mobile Endpoints", endpoints)

    # ============= EXECUTIVE/GM DASHBOARD TESTS =============

    async def test_executive_dashboard(self):
        """Test Executive/GM Dashboard endpoints"""
        print("\n👔 Testing Executive/GM Dashboard (3 endpoints)...")
        
        endpoints = [
            {
                "name": "Get Executive KPI Snapshot",
                "method": "GET",
                "endpoint": "/executive/kpi-snapshot",
                "expected_fields": ["kpis", "summary"]
            },
            {
                "name": "Get Executive Performance Alerts",
                "method": "GET",
                "endpoint": "/executive/performance-alerts",
                "expected_fields": ["alerts", "count"]
            },
            {
                "name": "Get GM Team Performance",
                "method": "GET",
                "endpoint": "/gm/team-performance"
            }
        ]

        return await self.test_endpoints("Executive/GM Dashboard", endpoints)

    # ============= ADDITIONAL CRITICAL ENDPOINTS =============

    async def test_additional_endpoints(self):
        """Test additional critical endpoints"""
        print("\n🔧 Testing Additional Critical Endpoints (10 endpoints)...")
        
        endpoints = [
            # Monitoring endpoints
            {
                "name": "Health Check",
                "method": "GET",
                "endpoint": "/monitoring/health",
                "expected_fields": ["status", "components"]
            },
            {
                "name": "System Metrics",
                "method": "GET", 
                "endpoint": "/monitoring/system",
                "expected_fields": ["cpu_usage", "memory", "disk"]
            },
            {
                "name": "Database Metrics",
                "method": "GET",
                "endpoint": "/monitoring/database"
            },
            # Dashboard endpoints
            {
                "name": "Employee Performance Dashboard",
                "method": "GET",
                "endpoint": "/dashboard/employee-performance"
            },
            {
                "name": "Guest Satisfaction Trends",
                "method": "GET",
                "endpoint": "/dashboard/guest-satisfaction-trends"
            },
            {
                "name": "OTA Cancellation Rate",
                "method": "GET",
                "endpoint": "/dashboard/ota-cancellation-rate"
            },
            # Messaging endpoints
            {
                "name": "Message Templates",
                "method": "GET",
                "endpoint": "/messaging/templates"
            },
            # POS endpoints
            {
                "name": "POS Menu Items",
                "method": "GET",
                "endpoint": "/pos/menu-items"
            },
            {
                "name": "POS Orders",
                "method": "GET",
                "endpoint": "/pos/orders"
            },
            # Approval system
            {
                "name": "Pending Approvals",
                "method": "GET",
                "endpoint": "/approvals/pending"
            }
        ]

        return await self.test_endpoints("Additional Critical Endpoints", endpoints)

    # ============= HELPER METHODS =============

    async def test_endpoints(self, module_name: str, endpoints: List[Dict]) -> Dict:
        """Test a list of endpoints and return results"""
        results = {
            "module": module_name,
            "total": len(endpoints),
            "passed": 0,
            "failed": 0,
            "slow": 0,
            "endpoints": []
        }

        for endpoint_config in endpoints:
            try:
                result = await self.make_request(
                    endpoint_config["method"],
                    endpoint_config["endpoint"],
                    endpoint_config.get("data"),
                    endpoint_config.get("params")
                )

                endpoint_result = {
                    "name": endpoint_config["name"],
                    "endpoint": endpoint_config["endpoint"],
                    "method": endpoint_config["method"],
                    "status": result["status"],
                    "response_time": result["response_time"],
                    "success": result["success"]
                }

                # Check if response is slow (>500ms)
                if result["response_time"] > 500:
                    results["slow"] += 1
                    self.slow_endpoints.append({
                        "endpoint": f"{endpoint_config['method']} {endpoint_config['endpoint']}",
                        "response_time": result["response_time"]
                    })
                    endpoint_result["slow"] = True

                # Validate expected fields if specified
                if result["success"] and "expected_fields" in endpoint_config:
                    if isinstance(result["data"], dict):
                        missing_fields = []
                        for field in endpoint_config["expected_fields"]:
                            if field not in result["data"]:
                                missing_fields.append(field)
                        
                        if missing_fields:
                            endpoint_result["missing_fields"] = missing_fields
                            endpoint_result["success"] = False
                            result["success"] = False

                if result["success"]:
                    results["passed"] += 1
                    status_icon = "✅"
                else:
                    results["failed"] += 1
                    status_icon = "❌"
                    self.failed_endpoints.append({
                        "endpoint": f"{endpoint_config['method']} {endpoint_config['endpoint']}",
                        "status": result["status"],
                        "error": result["data"] if not result["success"] else None
                    })

                # Print result
                time_color = "🐌" if result["response_time"] > 500 else "⚡"
                print(f"  {status_icon} {endpoint_config['name']}: {result['status']} ({result['response_time']:.1f}ms) {time_color}")
                
                if not result["success"] and isinstance(result["data"], str):
                    print(f"      Error: {result['data'][:100]}...")

                results["endpoints"].append(endpoint_result)

            except Exception as e:
                results["failed"] += 1
                print(f"  ❌ {endpoint_config['name']}: Exception - {str(e)}")
                self.failed_endpoints.append({
                    "endpoint": f"{endpoint_config['method']} {endpoint_config['endpoint']}",
                    "status": "Exception",
                    "error": str(e)
                })

        return results

    # ============= MAIN TEST EXECUTION =============

    async def run_comprehensive_scan(self):
        """Run comprehensive system scan"""
        print("🚀 COMPREHENSIVE SYSTEM SCAN - Find Any Remaining Issues")
        print("Testing ALL major modules with 5-10 endpoints each")
        print("Target: 100% success, all responses <500ms")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Create test data
        if not await self.create_test_data():
            print("⚠️ Test data creation failed. Some tests may not work properly.")
        
        # Test all modules
        module_results = []
        
        module_results.append(await self.test_pms_module())
        module_results.append(await self.test_folio_system())
        module_results.append(await self.test_housekeeping_module())
        module_results.append(await self.test_revenue_management())
        module_results.append(await self.test_mobile_endpoints())
        module_results.append(await self.test_executive_dashboard())
        module_results.append(await self.test_additional_endpoints())
        
        # Cleanup
        await self.cleanup_session()
        
        # Print comprehensive results
        self.print_comprehensive_results(module_results)

    def print_comprehensive_results(self, module_results: List[Dict]):
        """Print comprehensive test results"""
        print("\n" + "=" * 80)
        print("📊 COMPREHENSIVE SYSTEM SCAN RESULTS")
        print("=" * 80)
        
        total_endpoints = 0
        total_passed = 0
        total_failed = 0
        total_slow = 0
        
        print("\n📋 RESULTS BY MODULE:")
        print("-" * 60)
        
        for result in module_results:
            total_endpoints += result["total"]
            total_passed += result["passed"]
            total_failed += result["failed"]
            total_slow += result["slow"]
            
            success_rate = (result["passed"] / result["total"] * 100) if result["total"] > 0 else 0
            status = "✅" if success_rate == 100 else "⚠️" if success_rate >= 80 else "❌"
            
            print(f"\n{status} {result['module']}: {result['passed']}/{result['total']} ({success_rate:.1f}%)")
            if result["slow"] > 0:
                print(f"   🐌 Slow endpoints: {result['slow']}")
            if result["failed"] > 0:
                print(f"   ❌ Failed endpoints: {result['failed']}")

        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_endpoints * 100) if total_endpoints > 0 else 0
        print(f"📈 OVERALL RESULTS:")
        print(f"   Total endpoints tested: {total_endpoints}")
        print(f"   Successful: {total_passed} ({overall_success_rate:.1f}%)")
        print(f"   Failed: {total_failed}")
        print(f"   Slow (>500ms): {total_slow}")

        # Performance analysis
        if self.slow_endpoints:
            print(f"\n🐌 SLOW ENDPOINTS (>{500}ms):")
            print("-" * 40)
            for endpoint in self.slow_endpoints:
                print(f"   {endpoint['endpoint']}: {endpoint['response_time']:.1f}ms")

        # Failed endpoints analysis
        if self.failed_endpoints:
            print(f"\n❌ FAILED ENDPOINTS:")
            print("-" * 40)
            for endpoint in self.failed_endpoints:
                print(f"   {endpoint['endpoint']}: {endpoint['status']}")
                if endpoint.get('error'):
                    error_msg = str(endpoint['error'])[:100]
                    print(f"      Error: {error_msg}...")

        # Final assessment
        print("\n" + "=" * 80)
        if overall_success_rate >= 95 and total_slow == 0:
            print("🎉 EXCELLENT: System is performing perfectly!")
        elif overall_success_rate >= 90:
            print("✅ GOOD: System is mostly working well, minor issues detected")
        elif overall_success_rate >= 75:
            print("⚠️ MODERATE: System has some issues that need attention")
        else:
            print("❌ CRITICAL: System has major issues requiring immediate attention")

        print(f"\n🎯 TARGET ACHIEVEMENT:")
        print(f"   Success Rate Target (100%): {'✅ ACHIEVED' if overall_success_rate == 100 else '❌ NOT ACHIEVED'}")
        print(f"   Performance Target (<500ms): {'✅ ACHIEVED' if total_slow == 0 else '❌ NOT ACHIEVED'}")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    scanner = ComprehensiveSystemScanner()
    await scanner.run_comprehensive_scan()

if __name__ == "__main__":
    asyncio.run(main())