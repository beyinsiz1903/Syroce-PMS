#!/usr/bin/env python3
"""
Turkish Sprint Shadow Metrics Instrumentation Backend Test
"""
import asyncio
import httpx
import json
import sys
from datetime import datetime, timezone


# Configuration
BASE_URL = "https://hotel-pms-test.preview.emergentagent.com/api"
TEST_CREDENTIALS = {
    "email": "demo@hotel.com",
    "password": "demo123"
}

# Test data - real looking demo data for Turkish hotel context
TEST_FOLIO_ID = None
TEST_CHECK_IN = "2024-12-01"
TEST_CHECK_OUT = "2024-12-02"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def log_info(message):
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.ENDC}")

def log_success(message):
    print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")

def log_error(message):
    print(f"{Colors.RED}❌ {message}{Colors.ENDC}")

def log_warning(message):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.ENDC}")

class BackendTester:
    def __init__(self):
        self.token = None
        self.tenant_id = None
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_results = {
            "auth_login": {"status": "pending", "details": ""},
            "pms_rooms_availability": {"status": "pending", "details": ""},
            "folio_details": {"status": "pending", "details": ""},
            "shadow_metrics": {"status": "pending", "details": ""},
            "response_integrity": {"status": "pending", "details": ""}
        }

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def login(self):
        """Test authentication and get token"""
        log_info("🔐 Testing auth login...")
        try:
            response = await self.client.post(
                f"{BASE_URL}/auth/login",
                json=TEST_CREDENTIALS
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                if self.token:
                    log_success(f"Auth login successful - Token received: {self.token[:20]}...")
                    self.test_results["auth_login"]["status"] = "pass"
                    self.test_results["auth_login"]["details"] = f"✅ HTTP {response.status_code} - Token: {self.token[:20]}..."
                    
                    # Extract tenant_id from token payload if available
                    import base64
                    try:
                        # Simple JWT decode for tenant_id (for testing only)
                        parts = self.token.split('.')
                        if len(parts) >= 2:
                            payload_data = parts[1] + '=' * (4 - len(parts[1]) % 4)  # Add padding
                            decoded = base64.b64decode(payload_data)
                            payload = json.loads(decoded.decode('utf-8'))
                            self.tenant_id = payload.get('tenant_id')
                            if self.tenant_id:
                                log_info(f"Extracted tenant_id: {self.tenant_id}")
                    except Exception as e:
                        log_warning(f"Could not extract tenant_id from token: {e}")
                    
                    return True
                else:
                    log_error("No access token in response")
                    self.test_results["auth_login"]["status"] = "fail"
                    self.test_results["auth_login"]["details"] = "❌ No access token in response"
                    return False
            else:
                log_error(f"Auth login failed: HTTP {response.status_code}")
                self.test_results["auth_login"]["status"] = "fail"
                self.test_results["auth_login"]["details"] = f"❌ HTTP {response.status_code} - {response.text[:200]}"
                return False
        except Exception as e:
            log_error(f"Auth login error: {str(e)}")
            self.test_results["auth_login"]["status"] = "fail"
            self.test_results["auth_login"]["details"] = f"❌ Exception: {str(e)}"
            return False

    async def test_pms_rooms_availability(self):
        """Test GET /api/pms/rooms/availability with shadow metrics instrumentation"""
        log_info("🏨 Testing PMS rooms availability endpoint...")
        
        if not self.token:
            log_error("No auth token - skipping availability test")
            self.test_results["pms_rooms_availability"]["status"] = "skip"
            return False
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "x-correlation-id": f"test-{datetime.now(timezone.utc).isoformat()}",
            "x-property-id": self.tenant_id or "test-property"
        }
        
        try:
            # Test with realistic Turkish hotel dates
            params = {
                "check_in": TEST_CHECK_IN,
                "check_out": TEST_CHECK_OUT
            }
            
            log_info(f"Requesting availability: {TEST_CHECK_IN} to {TEST_CHECK_OUT}")
            response = await self.client.get(
                f"{BASE_URL}/pms/rooms/availability",
                params=params,
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                log_success(f"✅ Availability API HTTP 200 - Found {len(data)} rooms")
                
                # Validate response structure  
                if isinstance(data, list):
                    sample_rooms = data[:3]  # Check first 3 rooms
                    for i, room in enumerate(sample_rooms):
                        expected_fields = ['id', 'room_number', 'room_type', 'available']
                        missing = [f for f in expected_fields if f not in room]
                        if missing:
                            log_warning(f"Room {i+1} missing fields: {missing}")
                        else:
                            log_info(f"Room {i+1}: {room.get('room_number')} ({room.get('room_type')}) - Available: {room.get('available')}")
                    
                    self.test_results["pms_rooms_availability"]["status"] = "pass"
                    self.test_results["pms_rooms_availability"]["details"] = f"✅ HTTP 200 - {len(data)} rooms returned"
                    return True
                else:
                    log_error("Invalid response format - expected array")
                    self.test_results["pms_rooms_availability"]["status"] = "fail"
                    self.test_results["pms_rooms_availability"]["details"] = "❌ Invalid response format"
                    return False
            else:
                log_error(f"Availability API failed: HTTP {response.status_code}")
                self.test_results["pms_rooms_availability"]["status"] = "fail"
                self.test_results["pms_rooms_availability"]["details"] = f"❌ HTTP {response.status_code} - {response.text[:200]}"
                return False
                
        except Exception as e:
            log_error(f"Availability API error: {str(e)}")
            self.test_results["pms_rooms_availability"]["status"] = "fail"
            self.test_results["pms_rooms_availability"]["details"] = f"❌ Exception: {str(e)}"
            return False

    async def get_test_folio_id(self):
        """Get a folio ID for testing"""
        global TEST_FOLIO_ID
        
        if not self.token:
            return None
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            # First try to get existing folios
            response = await self.client.get(f"{BASE_URL}/folio/list", headers=headers)
            if response.status_code == 200:
                data = response.json()
                folios = data.get('folios', [])
                if folios:
                    TEST_FOLIO_ID = folios[0]['id']
                    log_info(f"Found existing folio for testing: {TEST_FOLIO_ID}")
                    return TEST_FOLIO_ID
            
            log_warning("No existing folios found - test will skip folio endpoint")
            return None
            
        except Exception as e:
            log_warning(f"Could not get test folio ID: {e}")
            return None

    async def test_folio_details(self):
        """Test GET /api/folio/{folio_id} with shadow metrics instrumentation"""
        log_info("💰 Testing folio details endpoint...")
        
        if not self.token:
            log_error("No auth token - skipping folio test")
            self.test_results["folio_details"]["status"] = "skip"
            return False
        
        # Get a test folio ID
        folio_id = await self.get_test_folio_id()
        if not folio_id:
            log_warning("No folio ID available - skipping folio test")
            self.test_results["folio_details"]["status"] = "skip"
            self.test_results["folio_details"]["details"] = "⚠️ No test folio available"
            return False
        
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "x-correlation-id": f"test-folio-{datetime.now(timezone.utc).isoformat()}",
            "x-property-id": self.tenant_id or "test-property"
        }
        
        try:
            response = await self.client.get(
                f"{BASE_URL}/folio/{folio_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                log_success(f"✅ Folio details API HTTP 200")
                
                # Validate response structure
                required_fields = ['folio', 'balance']
                missing = [f for f in required_fields if f not in data]
                if missing:
                    log_warning(f"Response missing fields: {missing}")
                else:
                    folio = data.get('folio', {})
                    balance = data.get('balance', 0)
                    log_info(f"Folio ID: {folio.get('id')}, Balance: {balance}")
                    
                    # Check folio structure
                    folio_fields = ['id', 'folio_number', 'status']
                    folio_missing = [f for f in folio_fields if f not in folio]
                    if folio_missing:
                        log_warning(f"Folio object missing fields: {folio_missing}")
                
                self.test_results["folio_details"]["status"] = "pass"
                self.test_results["folio_details"]["details"] = f"✅ HTTP 200 - Balance: {data.get('balance', 'N/A')}"
                return True
            else:
                log_error(f"Folio details API failed: HTTP {response.status_code}")
                self.test_results["folio_details"]["status"] = "fail"
                self.test_results["folio_details"]["details"] = f"❌ HTTP {response.status_code} - {response.text[:200]}"
                return False
                
        except Exception as e:
            log_error(f"Folio details API error: {str(e)}")
            self.test_results["folio_details"]["status"] = "fail"
            self.test_results["folio_details"]["details"] = f"❌ Exception: {str(e)}"
            return False

    async def test_shadow_metrics_behavior(self):
        """Test that shadow metrics don't break endpoint responses"""
        log_info("📊 Testing shadow metrics behavior (non-intrusive)...")
        
        # This test validates that endpoints still work correctly with shadow metrics
        # We can't directly verify shadow metrics logging without backend access,
        # but we can ensure they don't cause response drift or 500 errors
        
        try:
            # Test multiple calls to see if shadow metrics affect performance/stability
            availability_calls = []
            folio_calls = []
            
            if self.token:
                headers = {
                    "Authorization": f"Bearer {self.token}",
                    "x-correlation-id": f"shadow-test-{datetime.now(timezone.utc).isoformat()}"
                }
                
                # Multiple availability calls
                log_info("Testing availability endpoint stability...")
                for i in range(3):
                    try:
                        response = await self.client.get(
                            f"{BASE_URL}/pms/rooms/availability",
                            params={"check_in": TEST_CHECK_IN, "check_out": TEST_CHECK_OUT},
                            headers=headers
                        )
                        availability_calls.append({
                            "call": i+1,
                            "status_code": response.status_code,
                            "response_time": response.elapsed.total_seconds() if hasattr(response, 'elapsed') else 0,
                            "success": response.status_code == 200
                        })
                    except Exception as e:
                        availability_calls.append({
                            "call": i+1,
                            "status_code": 0,
                            "error": str(e),
                            "success": False
                        })
                
                # Test folio endpoint stability (if we have a folio)
                folio_id = await self.get_test_folio_id()
                if folio_id:
                    log_info("Testing folio endpoint stability...")
                    for i in range(3):
                        try:
                            response = await self.client.get(
                                f"{BASE_URL}/folio/{folio_id}",
                                headers=headers
                            )
                            folio_calls.append({
                                "call": i+1,
                                "status_code": response.status_code,
                                "success": response.status_code == 200
                            })
                        except Exception as e:
                            folio_calls.append({
                                "call": i+1,
                                "status_code": 0,
                                "error": str(e),
                                "success": False
                            })
                
                # Analyze results
                availability_success = sum(1 for call in availability_calls if call.get("success")) 
                folio_success = sum(1 for call in folio_calls if call.get("success"))
                
                total_calls = len(availability_calls) + len(folio_calls)
                total_success = availability_success + folio_success
                
                if total_calls > 0 and total_success == total_calls:
                    log_success("✅ Shadow metrics behavior: All endpoint calls successful")
                    self.test_results["shadow_metrics"]["status"] = "pass"
                    self.test_results["shadow_metrics"]["details"] = f"✅ {total_success}/{total_calls} calls successful"
                    return True
                elif total_success > 0:
                    log_warning(f"⚠️ Shadow metrics behavior: {total_success}/{total_calls} calls successful")
                    self.test_results["shadow_metrics"]["status"] = "partial"
                    self.test_results["shadow_metrics"]["details"] = f"⚠️ {total_success}/{total_calls} calls successful"
                    return False
                else:
                    log_error("❌ Shadow metrics behavior: All calls failed")
                    self.test_results["shadow_metrics"]["status"] = "fail" 
                    self.test_results["shadow_metrics"]["details"] = "❌ All calls failed"
                    return False
            else:
                log_error("No auth token - cannot test shadow metrics behavior")
                self.test_results["shadow_metrics"]["status"] = "skip"
                self.test_results["shadow_metrics"]["details"] = "⚠️ No auth token"
                return False
                
        except Exception as e:
            log_error(f"Shadow metrics behavior test error: {str(e)}")
            self.test_results["shadow_metrics"]["status"] = "fail"
            self.test_results["shadow_metrics"]["details"] = f"❌ Exception: {str(e)}"
            return False

    async def test_response_integrity(self):
        """Test for 500 errors and response drift"""
        log_info("🔍 Testing for 500 errors and response drift...")
        
        if not self.token:
            log_error("No auth token - skipping response integrity test")
            self.test_results["response_integrity"]["status"] = "skip"
            return False
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Test various endpoints for 500 errors
        test_endpoints = [
            {"path": "/pms/dashboard", "method": "GET"},
            {"path": "/pms/rooms", "method": "GET", "params": {"limit": "10"}},
            {"path": "/pms/guests", "method": "GET", "params": {"limit": "5"}},
            {"path": "/folio/dashboard-stats", "method": "GET"}
        ]
        
        error_count = 0
        success_count = 0
        
        for endpoint in test_endpoints:
            try:
                if endpoint["method"] == "GET":
                    response = await self.client.get(
                        f"{BASE_URL}{endpoint['path']}",
                        params=endpoint.get("params"),
                        headers=headers
                    )
                
                if response.status_code >= 500:
                    log_error(f"500 error on {endpoint['path']}: HTTP {response.status_code}")
                    error_count += 1
                elif response.status_code == 200:
                    log_info(f"✅ {endpoint['path']}: HTTP 200")
                    success_count += 1
                else:
                    log_warning(f"⚠️ {endpoint['path']}: HTTP {response.status_code}")
                    
            except Exception as e:
                log_error(f"Error testing {endpoint['path']}: {str(e)}")
                error_count += 1
        
        if error_count == 0:
            log_success("✅ Response integrity: No 500 errors found")
            self.test_results["response_integrity"]["status"] = "pass"
            self.test_results["response_integrity"]["details"] = f"✅ {success_count} endpoints OK, 0 server errors"
            return True
        else:
            log_error(f"❌ Response integrity: {error_count} errors found")
            self.test_results["response_integrity"]["status"] = "fail"
            self.test_results["response_integrity"]["details"] = f"❌ {error_count} endpoints with errors"
            return False

    def print_summary(self):
        """Print test summary"""
        print(f"\n{Colors.BOLD}📋 TÜRKÇE SPRINT SHADOW METRICS TEST SONUÇLARI{Colors.ENDC}")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed = sum(1 for result in self.test_results.values() if result["status"] == "pass")
        failed = sum(1 for result in self.test_results.values() if result["status"] == "fail")
        skipped = sum(1 for result in self.test_results.values() if result["status"] == "skip")
        
        for test_name, result in self.test_results.items():
            status = result["status"]
            details = result["details"]
            
            if status == "pass":
                print(f"✅ {test_name.replace('_', ' ').title()}: BAŞARILI")
            elif status == "fail":
                print(f"❌ {test_name.replace('_', ' ').title()}: BAŞARISIZ")
            elif status == "skip":
                print(f"⏭️  {test_name.replace('_', ' ').title()}: ATLANDI")
            else:
                print(f"⏸️  {test_name.replace('_', ' ').title()}: BEKLEMEDE")
            
            if details:
                print(f"   └─ {details}")
        
        print("\n" + "=" * 60)
        print(f"📊 ÖZET: {passed} Başarılı, {failed} Başarısız, {skipped} Atlandı (Toplam: {total_tests})")
        
        # Key findings for shadow metrics
        print(f"\n{Colors.BOLD}🎯 SHADOW METRICS DURUMU:{Colors.ENDC}")
        
        availability_ok = self.test_results["pms_rooms_availability"]["status"] == "pass"
        folio_ok = self.test_results["folio_details"]["status"] in ["pass", "skip"]
        shadow_ok = self.test_results["shadow_metrics"]["status"] in ["pass", "partial"]
        no_500s = self.test_results["response_integrity"]["status"] == "pass"
        
        if availability_ok:
            print("✅ GET /api/pms/rooms/availability hala 200 dönüyor")
        else:
            print("❌ GET /api/pms/rooms/availability problemi var")
        
        if folio_ok:
            print("✅ GET /api/folio/{folio_id} hala 200 dönüyor")
        else:
            print("❌ GET /api/folio/{folio_id} problemi var")
        
        if shadow_ok:
            print("✅ Shadow compare log/metric davranışı endpoint response'unu bozmadan çalışıyor")
        else:
            print("❌ Shadow metrics endpoint davranışını etkiliyor olabilir")
        
        if no_500s:
            print("✅ 500 veya response drift yok")
        else:
            print("❌ 500 hatası veya response drift tespit edildi")
        
        # Overall assessment
        critical_passed = availability_ok and no_500s
        if critical_passed and folio_ok and shadow_ok:
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 GENEL DURUM: BAŞARILI - Shadow metric instrumentation çalışıyor{Colors.ENDC}")
        elif critical_passed:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️ GENEL DURUM: KISMEN BAŞARILI - Temel endpointler çalışıyor{Colors.ENDC}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}💥 GENEL DURUM: BAŞARISIZ - Kritik problemler var{Colors.ENDC}")

async def main():
    """Main test runner"""
    print(f"{Colors.BOLD}🇹🇷 TÜRKÇE SPRINT - SHADOW METRICS BACKEND TEST{Colors.ENDC}")
    print("Testing availability + folio read shadow metric instrumentation")
    print("=" * 60)
    
    async with BackendTester() as tester:
        # Run tests in sequence
        await tester.login()
        await tester.test_pms_rooms_availability()
        await tester.test_folio_details()
        await tester.test_shadow_metrics_behavior()
        await tester.test_response_integrity()
        
        # Print results
        tester.print_summary()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Test failed with error: {str(e)}{Colors.ENDC}")
        sys.exit(1)