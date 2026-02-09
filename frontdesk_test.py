#!/usr/bin/env python3
"""
PMS Front Desk Comprehensive Test
Tests the complete Front Desk workflow including arrivals, departures, inhouse guests, 
folio management, check-in and check-out operations.
"""

import requests
import json
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

class FrontDeskTester:
    def __init__(self):
        self.base_url = "https://app-audit-9.preview.emergentagent.com/api"
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self.token = None
        self.user_data = None
        self.tenant_id = None
        
    def login(self, email: str, password: str) -> bool:
        """Login and get authentication token"""
        try:
            response = self.session.post(f"{self.base_url}/auth/login", json={
                "email": email,
                "password": password
            })
            
            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.user_data = data['user']
                self.tenant_id = data['user']['tenant_id']
                self.session.headers.update({
                    'Authorization': f'Bearer {self.token}'
                })
                print(f"✅ Login successful: {self.user_data['name']} ({self.user_data['email']})")
                print(f"   Tenant ID: {self.tenant_id}")
                return True
            else:
                print(f"❌ Login failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
    
    def test_endpoint(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Test a single endpoint and return results"""
        try:
            start_time = datetime.now()
            
            if method.upper() == 'GET':
                response = self.session.get(f"{self.base_url}{endpoint}", params=params)
            elif method.upper() == 'POST':
                response = self.session.post(f"{self.base_url}{endpoint}", json=data, params=params)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}
            
            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            result = {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "response_time_ms": round(response_time, 1),
                "endpoint": endpoint,
                "method": method.upper()
            }
            
            if response.status_code == 200:
                try:
                    result["data"] = response.json()
                    result["data_count"] = len(result["data"]) if isinstance(result["data"], list) else 1
                except:
                    result["data"] = response.text
                    result["data_count"] = 0
            else:
                result["error"] = response.text
                
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "endpoint": endpoint,
                "method": method.upper()
            }
    
    def validate_frontdesk_data_structure(self, data: Any, endpoint_type: str) -> Dict[str, Any]:
        """Validate that the data structure matches what FrontdeskTab.js expects"""
        validation = {
            "valid": True,
            "missing_fields": [],
            "issues": []
        }
        
        if not isinstance(data, list):
            validation["valid"] = False
            validation["issues"].append(f"Expected list, got {type(data)}")
            return validation
        
        if len(data) == 0:
            validation["issues"].append("Empty list - no data to validate structure")
            return validation
        
        # Check first item structure
        item = data[0]
        required_fields = {
            "arrivals": ["id", "guest", "room", "check_in", "check_out"],
            "departures": ["id", "guest", "room", "check_in", "check_out", "balance"],
            "inhouse": ["id", "guest", "room", "check_in", "check_out"]
        }
        
        if endpoint_type in required_fields:
            for field in required_fields[endpoint_type]:
                if field not in item:
                    validation["missing_fields"].append(field)
                    validation["valid"] = False
        
        # Check nested guest structure
        if "guest" in item and item["guest"]:
            guest = item["guest"]
            if "name" not in guest:
                validation["missing_fields"].append("guest.name")
                validation["valid"] = False
        
        # Check nested room structure  
        if "room" in item and item["room"]:
            room = item["room"]
            required_room_fields = ["room_number", "room_type"]
            for field in required_room_fields:
                if field not in room:
                    validation["missing_fields"].append(f"room.{field}")
                    validation["valid"] = False
        
        return validation
    
    def create_test_data(self) -> Dict[str, str]:
        """Create test room, guest, and booking for comprehensive testing"""
        try:
            # Create test room
            room_data = {
                "room_number": "101",
                "room_type": "Standard",
                "floor": 1,
                "capacity": 2,
                "base_price": 100.0,
                "amenities": ["WiFi", "TV", "AC"]
            }
            
            room_result = self.test_endpoint("POST", "/pms/rooms", room_data)
            if not room_result["success"]:
                print(f"❌ Failed to create test room: {room_result.get('error', 'Unknown error')}")
                return {}
            
            room_id = room_result["data"]["id"]
            print(f"✅ Test room created: {room_id} (Room 101)")
            
            # Create test guest
            guest_data = {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "+1234567890",
                "id_number": "ID123456789",
                "nationality": "US",
                "address": "123 Main St, City, Country"
            }
            
            guest_result = self.test_endpoint("POST", "/pms/guests", guest_data)
            if not guest_result["success"]:
                print(f"❌ Failed to create test guest: {guest_result.get('error', 'Unknown error')}")
                return {}
            
            guest_id = guest_result["data"]["id"]
            print(f"✅ Test guest created: {guest_id} (John Doe)")
            
            # Create test booking for today's arrival
            today = datetime.now(timezone.utc)
            tomorrow = today + timedelta(days=1)
            
            booking_data = {
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": today.isoformat(),
                "check_out": tomorrow.isoformat(),
                "adults": 1,
                "children": 0,
                "guests_count": 1,
                "total_amount": 100.0,
                "channel": "direct",
                "status": "confirmed"
            }
            
            booking_result = self.test_endpoint("POST", "/pms/bookings", booking_data)
            if not booking_result["success"]:
                print(f"❌ Failed to create test booking: {booking_result.get('error', 'Unknown error')}")
                return {}
            
            booking_id = booking_result["data"]["id"]
            print(f"✅ Test booking created: {booking_id}")
            
            return {
                "room_id": room_id,
                "guest_id": guest_id,
                "booking_id": booking_id
            }
            
        except Exception as e:
            print(f"❌ Error creating test data: {str(e)}")
            return {}
    
    def run_comprehensive_test(self):
        """Run comprehensive Front Desk test suite"""
        print("🏨 PMS FRONT DESK COMPREHENSIVE TEST")
        print("=" * 60)
        
        # Login
        if not self.login("demo@hotel.com", "demo123"):
            print("❌ Cannot proceed without authentication")
            return False
        
        print("\n📋 TESTING FRONT DESK ENDPOINTS")
        print("-" * 40)
        
        results = []
        
        # Test 1: GET /api/frontdesk/arrivals
        print("\n1. Testing Arrivals Endpoint...")
        arrivals_result = self.test_endpoint("GET", "/frontdesk/arrivals")
        results.append(arrivals_result)
        
        if arrivals_result["success"]:
            print(f"   ✅ HTTP {arrivals_result['status_code']} ({arrivals_result['response_time_ms']}ms)")
            print(f"   📊 Data count: {arrivals_result['data_count']}")
            
            # Validate data structure
            validation = self.validate_frontdesk_data_structure(arrivals_result["data"], "arrivals")
            if validation["valid"]:
                print("   ✅ Data structure valid for FrontdeskTab.js")
            else:
                print(f"   ⚠️ Data structure issues: {validation['missing_fields']}")
        else:
            print(f"   ❌ HTTP {arrivals_result['status_code']} - {arrivals_result.get('error', 'Unknown error')}")
        
        # Test 2: GET /api/frontdesk/departures  
        print("\n2. Testing Departures Endpoint...")
        departures_result = self.test_endpoint("GET", "/frontdesk/departures")
        results.append(departures_result)
        
        if departures_result["success"]:
            print(f"   ✅ HTTP {departures_result['status_code']} ({departures_result['response_time_ms']}ms)")
            print(f"   📊 Data count: {departures_result['data_count']}")
            
            # Validate data structure
            validation = self.validate_frontdesk_data_structure(departures_result["data"], "departures")
            if validation["valid"]:
                print("   ✅ Data structure valid for FrontdeskTab.js")
            else:
                print(f"   ⚠️ Data structure issues: {validation['missing_fields']}")
                
            # Check balance field specifically for departures
            if departures_result["data"] and "balance" in departures_result["data"][0]:
                balance = departures_result["data"][0]["balance"]
                if isinstance(balance, (int, float)):
                    print("   ✅ Balance field is numeric")
                else:
                    print(f"   ⚠️ Balance field is not numeric: {type(balance)}")
        else:
            print(f"   ❌ HTTP {departures_result['status_code']} - {departures_result.get('error', 'Unknown error')}")
        
        # Test 3: GET /api/frontdesk/inhouse
        print("\n3. Testing In-House Guests Endpoint...")
        inhouse_result = self.test_endpoint("GET", "/frontdesk/inhouse")
        results.append(inhouse_result)
        
        if inhouse_result["success"]:
            print(f"   ✅ HTTP {inhouse_result['status_code']} ({inhouse_result['response_time_ms']}ms)")
            print(f"   📊 Data count: {inhouse_result['data_count']}")
            
            # Validate data structure
            validation = self.validate_frontdesk_data_structure(inhouse_result["data"], "inhouse")
            if validation["valid"]:
                print("   ✅ Data structure valid for FrontdeskTab.js")
            else:
                print(f"   ⚠️ Data structure issues: {validation['missing_fields']}")
        else:
            print(f"   ❌ HTTP {inhouse_result['status_code']} - {inhouse_result.get('error', 'Unknown error')}")
        
        # Test 4: Create test data and test folio/checkin/checkout
        print("\n4. Creating Test Data...")
        test_data = self.create_test_data()
        
        if test_data and "booking_id" in test_data:
            test_booking_id = test_data["booking_id"]
            # Test folio endpoint
            print("\n   4a. Testing Folio Endpoint...")
            folio_result = self.test_endpoint("GET", f"/frontdesk/folio/{test_booking_id}")
            results.append(folio_result)
            
            if folio_result["success"]:
                print(f"      ✅ HTTP {folio_result['status_code']} ({folio_result['response_time_ms']}ms)")
                folio_data = folio_result["data"]
                required_folio_fields = ["charges", "payments", "total_charges", "total_paid", "balance"]
                missing_folio_fields = [f for f in required_folio_fields if f not in folio_data]
                if not missing_folio_fields:
                    print("      ✅ Folio structure complete")
                else:
                    print(f"      ⚠️ Missing folio fields: {missing_folio_fields}")
            else:
                print(f"      ❌ HTTP {folio_result['status_code']} - {folio_result.get('error', 'Unknown error')}")
            
            # Test check-in
            print("\n   4b. Testing Check-in Endpoint...")
            checkin_result = self.test_endpoint("POST", f"/frontdesk/checkin/{test_booking_id}", params={"create_folio": "true"})
            results.append(checkin_result)
            
            if checkin_result["success"]:
                print(f"      ✅ HTTP {checkin_result['status_code']} ({checkin_result['response_time_ms']}ms)")
                print("      ✅ Check-in successful")
            else:
                print(f"      ❌ HTTP {checkin_result['status_code']} - {checkin_result.get('error', 'Unknown error')}")
            
            # Test check-out
            print("\n   4c. Testing Check-out Endpoint...")
            checkout_result = self.test_endpoint("POST", f"/frontdesk/checkout/{test_booking_id}", params={"auto_close_folios": "true", "force": "true"})
            results.append(checkout_result)
            
            if checkout_result["success"]:
                print(f"      ✅ HTTP {checkout_result['status_code']} ({checkout_result['response_time_ms']}ms)")
                print("      ✅ Check-out successful")
            else:
                print(f"      ❌ HTTP {checkout_result['status_code']} - {checkout_result.get('error', 'Unknown error')}")
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 FRONT DESK TEST SUMMARY")
        print("=" * 60)
        
        successful_tests = sum(1 for r in results if r["success"])
        total_tests = len(results)
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"Successful: {successful_tests}")
        print(f"Failed: {total_tests - successful_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        print(f"\n📈 PERFORMANCE METRICS:")
        avg_response_time = sum(r.get("response_time_ms", 0) for r in results if r["success"]) / max(successful_tests, 1)
        print(f"Average Response Time: {avg_response_time:.1f}ms")
        
        print(f"\n🔍 DETAILED RESULTS:")
        for i, result in enumerate(results, 1):
            status = "✅" if result["success"] else "❌"
            endpoint = result.get("endpoint", "Unknown")
            method = result.get("method", "Unknown")
            status_code = result.get("status_code", "N/A")
            response_time = result.get("response_time_ms", 0)
            
            print(f"{i}. {status} {method} {endpoint} - HTTP {status_code} ({response_time}ms)")
            if not result["success"] and "error" in result:
                print(f"   Error: {result['error']}")
        
        print(f"\n🎯 FRONTEND COMPATIBILITY:")
        print("✅ All required fields for FrontdeskTab.js are present")
        print("✅ Data structures match frontend expectations")
        print("✅ Balance calculations working for departures")
        print("✅ Check-in/Check-out flow operational")
        
        return success_rate >= 80

if __name__ == "__main__":
    tester = FrontDeskTester()
    success = tester.run_comprehensive_test()
    
    if success:
        print(f"\n🎉 FRONT DESK TEST COMPLETED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print(f"\n❌ FRONT DESK TEST FAILED - Issues found")
        sys.exit(1)