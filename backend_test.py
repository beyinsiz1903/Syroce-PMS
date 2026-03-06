#!/usr/bin/env python3
"""
Backend API Test Suite for Turkish Sprint Testing
Test Turkish requirements:
1. Auth login works: demo@hotel.com / demo123  
2. GET /api/pms/bookings works and returns list
3. GET /api/pms/rooms/availability?check_in=today&check_out=tomorrow works
4. GET /api/folio/list works
5. If folio found, GET /api/folio/{folio_id} works and returns balance field
6. Foundation changes should not break backend; no 500 errors
"""

import asyncio
import json
import aiohttp
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Get backend URL from frontend .env
BACKEND_URL = "https://hotel-pms-test.preview.emergentagent.com"
BACKEND_API_URL = f"{BACKEND_URL}/api"

class BackendTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.results = []
        
    async def setup(self):
        """Setup test session"""
        self.session = aiohttp.ClientSession()
        
    async def teardown(self):
        """Cleanup test session"""
        if self.session:
            await self.session.close()
            
    def log_result(self, test_name: str, passed: bool, error: str = None, details: Any = None):
        """Log test result"""
        result = {
            "test": test_name,
            "passed": passed,
            "error": error,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
        if error:
            print(f"   Error: {error}")
        if details and not passed:
            print(f"   Details: {details}")
            
    async def test_auth_login(self):
        """Test 1: Auth login çalışıyor: demo@hotel.com / demo123"""
        try:
            login_url = f"{BACKEND_API_URL}/auth/login"
            payload = {
                "email": "demo@hotel.com",
                "password": "demo123"
            }
            
            async with self.session.post(login_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if "access_token" in data:
                        self.auth_token = data["access_token"]
                        self.log_result("Auth Login", True, details={"token_received": True})
                        return True
                    else:
                        self.log_result("Auth Login", False, "No access_token in response", data)
                        return False
                else:
                    error_text = await response.text()
                    self.log_result("Auth Login", False, f"HTTP {response.status}", error_text)
                    return False
                    
        except Exception as e:
            self.log_result("Auth Login", False, str(e))
            return False
            
    async def test_pms_bookings_list(self):
        """Test 2: GET /api/pms/bookings çalışıyor ve liste dönüyor"""
        if not self.auth_token:
            self.log_result("PMS Bookings List", False, "No auth token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            bookings_url = f"{BACKEND_API_URL}/pms/bookings"
            
            async with self.session.get(bookings_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        self.log_result("PMS Bookings List", True, details={"count": len(data)})
                        return True
                    else:
                        self.log_result("PMS Bookings List", False, "Response is not a list", type(data))
                        return False
                else:
                    error_text = await response.text()
                    self.log_result("PMS Bookings List", False, f"HTTP {response.status}", error_text)
                    return False
                    
        except Exception as e:
            self.log_result("PMS Bookings List", False, str(e))
            return False
            
    async def test_room_availability(self):
        """Test 3: GET /api/pms/rooms/availability?check_in=today&check_out=tomorrow çalışıyor"""
        if not self.auth_token:
            self.log_result("Room Availability", False, "No auth token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            today = datetime.now().date().isoformat()
            tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
            
            availability_url = f"{BACKEND_API_URL}/pms/rooms/availability?check_in={today}&check_out={tomorrow}"
            
            async with self.session.get(availability_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    # Should return some availability data structure
                    self.log_result("Room Availability", True, details={"response_type": type(data).__name__})
                    return True
                else:
                    error_text = await response.text()
                    self.log_result("Room Availability", False, f"HTTP {response.status}", error_text)
                    return False
                    
        except Exception as e:
            self.log_result("Room Availability", False, str(e))
            return False
            
    async def test_folio_list(self):
        """Test 4: GET /api/folio/list çalışıyor"""
        if not self.auth_token:
            self.log_result("Folio List", False, "No auth token available")
            return False, None
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            folio_url = f"{BACKEND_API_URL}/folio/list"
            
            async with self.session.get(folio_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    folios = data.get("folios", []) if isinstance(data, dict) else data
                    
                    if isinstance(folios, list):
                        self.log_result("Folio List", True, details={"count": len(folios)})
                        return True, folios
                    else:
                        self.log_result("Folio List", False, "Response folios is not a list", type(folios))
                        return False, None
                else:
                    error_text = await response.text()
                    self.log_result("Folio List", False, f"HTTP {response.status}", error_text)
                    return False, None
                    
        except Exception as e:
            self.log_result("Folio List", False, str(e))
            return False, None
            
    async def test_folio_details(self, folios):
        """Test 5: Listeden bir folio bulunursa GET /api/folio/{folio_id} çalışıyor ve balance alanı dönüyor"""
        if not self.auth_token:
            self.log_result("Folio Details", False, "No auth token available")
            return False
            
        if not folios or len(folios) == 0:
            self.log_result("Folio Details", True, "No folios to test - skipped")
            return True
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            # Test the first folio
            folio = folios[0]
            folio_id = folio.get("id")
            
            if not folio_id:
                self.log_result("Folio Details", False, "No folio ID found in first folio")
                return False
                
            folio_details_url = f"{BACKEND_API_URL}/folio/{folio_id}"
            
            async with self.session.get(folio_details_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Check if balance field is present
                    balance = data.get("balance")
                    if balance is not None:
                        self.log_result("Folio Details", True, details={"folio_id": folio_id, "balance": balance})
                        return True
                    else:
                        self.log_result("Folio Details", False, "No balance field in response", list(data.keys()))
                        return False
                else:
                    error_text = await response.text()
                    self.log_result("Folio Details", False, f"HTTP {response.status}", error_text)
                    return False
                    
        except Exception as e:
            self.log_result("Folio Details", False, str(e))
            return False
            
    async def test_foundation_regression(self):
        """Test 6: Foundation değişiklikleri backend'i kırmamış olmalı; 500 hatası olmamalı"""
        if not self.auth_token:
            self.log_result("Foundation Regression", False, "No auth token available")
            return False
            
        endpoints_to_test = [
            "/pms/rooms",
            "/pms/guests", 
            "/pms/dashboard",
            "/folio/dashboard-stats"
        ]
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        all_passed = True
        errors = []
        
        for endpoint in endpoints_to_test:
            try:
                url = f"{BACKEND_API_URL}{endpoint}"
                async with self.session.get(url, headers=headers) as response:
                    if response.status >= 500:
                        all_passed = False
                        errors.append(f"{endpoint}: HTTP {response.status}")
                        
            except Exception as e:
                all_passed = False
                errors.append(f"{endpoint}: {str(e)}")
                
        if all_passed:
            self.log_result("Foundation Regression", True, details={"tested_endpoints": len(endpoints_to_test)})
        else:
            self.log_result("Foundation Regression", False, "Found 500+ errors", errors)
            
        return all_passed
        
    async def run_all_tests(self):
        """Run all tests in sequence"""
        print("=== Backend Test Suite - Turkish Sprint Validation ===")
        print(f"Testing against: {BACKEND_API_URL}")
        print()
        
        await self.setup()
        
        try:
            # Test 1: Auth
            auth_success = await self.test_auth_login()
            
            if auth_success:
                # Test 2: Bookings
                await self.test_pms_bookings_list()
                
                # Test 3: Room Availability 
                await self.test_room_availability()
                
                # Test 4 & 5: Folio tests
                folio_success, folios = await self.test_folio_list()
                if folio_success:
                    await self.test_folio_details(folios)
                    
                # Test 6: Foundation regression
                await self.test_foundation_regression()
            else:
                print("❌ Authentication failed - skipping remaining tests")
                
        finally:
            await self.teardown()
            
        # Summary
        print()
        print("=== Test Summary ===")
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        print(f"Tests: {passed}/{total} passed")
        
        if passed < total:
            print("\n❌ Failed Tests:")
            for result in self.results:
                if not result["passed"]:
                    print(f"  - {result['test']}: {result['error']}")
        else:
            print("\n✅ All tests passed!")
            
        return passed == total

async def main():
    """Main test runner"""
    tester = BackendTester()
    success = await tester.run_all_tests()
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)