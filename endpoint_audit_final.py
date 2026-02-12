#!/usr/bin/env python3
"""
Comprehensive Backend Endpoint Audit for Turkish Hotel PMS (Syroce)
Testing all failing endpoints and sample endpoints from each module
"""

import requests
import json
from datetime import datetime, timedelta
import sys

# Configuration
BASE_URL = "https://ai-feature-test.preview.emergentagent.com/api"
AUTH_EMAIL = "demo@hotel.com"
AUTH_PASSWORD = "demo123"

# Test data IDs (created earlier)
TEST_GUEST_ID = "680f2508-9bc2-421a-afb0-94fec09eb792"
TEST_BOOKING_ID = "875afccb-acc7-438d-98b2-070e320f28f0"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class EndpointAuditor:
    def __init__(self):
        self.token = None
        self.tenant_id = None
        self.results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'failing_endpoints': [],
            'working_endpoints': []
        }
        
    def login(self):
        """Authenticate and get JWT token"""
        print(f"\n{BLUE}=== AUTHENTICATION ==={RESET}")
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": AUTH_EMAIL, "password": AUTH_PASSWORD},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.tenant_id = data.get('tenant', {}).get('id')
                print(f"{GREEN}✓ Authentication successful{RESET}")
                print(f"  Token: {self.token[:20]}...")
                print(f"  Tenant ID: {self.tenant_id}")
                return True
            else:
                print(f"{RED}✗ Authentication failed: {response.status_code}{RESET}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"{RED}✗ Authentication error: {str(e)}{RESET}")
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def test_endpoint(self, method, endpoint, data=None, params=None, expected_status=200, description=""):
        """Test a single endpoint"""
        self.results['total'] += 1
        url = f"{BASE_URL}{endpoint}"
        
        print(f"\n{BLUE}Testing: {method} {endpoint}{RESET}")
        if description:
            print(f"  Description: {description}")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=self.get_headers(), params=params, timeout=15)
            elif method == "POST":
                response = requests.post(url, headers=self.get_headers(), json=data, timeout=15)
            elif method == "PUT":
                response = requests.put(url, headers=self.get_headers(), json=data, timeout=15)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.get_headers(), timeout=15)
            else:
                print(f"{RED}✗ Unsupported method: {method}{RESET}")
                return False
            
            # Print request details
            if data:
                print(f"  Request Body: {json.dumps(data, indent=2)}")
            if params:
                print(f"  Query Params: {params}")
            
            # Print response details
            print(f"  Status Code: {response.status_code}")
            
            if response.status_code == expected_status:
                print(f"{GREEN}✓ PASSED - Status {response.status_code}{RESET}")
                try:
                    response_data = response.json()
                    print(f"  Response: {json.dumps(response_data, indent=2)[:500]}")
                except:
                    print(f"  Response: {response.text[:500]}")
                
                self.results['passed'] += 1
                self.results['working_endpoints'].append({
                    'method': method,
                    'endpoint': endpoint,
                    'status': response.status_code
                })
                return True
            else:
                print(f"{RED}✗ FAILED - Expected {expected_status}, got {response.status_code}{RESET}")
                print(f"  Response: {response.text[:1000]}")
                
                self.results['failed'] += 1
                self.results['failing_endpoints'].append({
                    'method': method,
                    'endpoint': endpoint,
                    'expected_status': expected_status,
                    'actual_status': response.status_code,
                    'error': response.text[:500],
                    'request_body': data
                })
                return False
                
        except Exception as e:
            print(f"{RED}✗ ERROR: {str(e)}{RESET}")
            self.results['failed'] += 1
            self.results['failing_endpoints'].append({
                'method': method,
                'endpoint': endpoint,
                'error': str(e),
                'request_body': data
            })
            return False
    
    def test_failing_endpoints(self):
        """Test all failing endpoints identified in test_result.md"""
        print(f"\n{BLUE}{'='*80}{RESET}")
        print(f"{BLUE}=== TESTING FAILING ENDPOINTS ==={RESET}")
        print(f"{BLUE}{'='*80}{RESET}")
        
        # 1. POST /api/reservations/{booking_id}/extra-charges (HTTP 422)
        print(f"\n{YELLOW}--- Test 1: Extra Charges Endpoint ---{RESET}")
        self.test_endpoint(
            "POST",
            f"/reservations/{TEST_BOOKING_ID}/extra-charges",
            data={
                "charge_name": "Late Checkout Fee",
                "charge_amount": 50.0,
                "notes": "Guest requested late checkout"
            },
            expected_status=200,
            description="Add extra charge to reservation"
        )
        
        # 2. POST /api/reservations/multi-room (HTTP 422)
        print(f"\n{YELLOW}--- Test 2: Multi-Room Reservation Endpoint ---{RESET}")
        self.test_endpoint(
            "POST",
            "/reservations/multi-room",
            data={
                "group_name": "Smith Family Reunion",
                "primary_booking_id": TEST_BOOKING_ID,
                "related_booking_ids": [TEST_BOOKING_ID]
            },
            expected_status=200,
            description="Create multi-room reservation"
        )
        
        # 3. POST /api/guests/{guest_id}/preferences (HTTP 422)
        print(f"\n{YELLOW}--- Test 3: Guest Preferences Endpoint ---{RESET}")
        self.test_endpoint(
            "POST",
            f"/guests/{TEST_GUEST_ID}/preferences",
            data={
                "pillow_type": "soft",
                "floor_preference": "high",
                "room_temperature": "cool",
                "smoking": False,
                "special_needs": "wheelchair accessible",
                "dietary_restrictions": "vegetarian",
                "newspaper_preference": "daily"
            },
            expected_status=200,
            description="Update guest preferences"
        )
        
        # 4. POST /api/guests/{guest_id}/tags (HTTP 422)
        print(f"\n{YELLOW}--- Test 4: Guest Tags Endpoint ---{RESET}")
        self.test_endpoint(
            "POST",
            f"/guests/{TEST_GUEST_ID}/tags",
            data={
                "tags": ["vip", "frequent_guest", "high_spender"]
            },
            expected_status=200,
            description="Update guest tags"
        )
    
    def test_sample_endpoints(self):
        """Test sample endpoints from each module"""
        print(f"\n{BLUE}{'='*80}{RESET}")
        print(f"{BLUE}=== TESTING SAMPLE ENDPOINTS FROM EACH MODULE ==={RESET}")
        print(f"{BLUE}{'='*80}{RESET}")
        
        # 1. OTA Reservations
        print(f"\n{YELLOW}--- Module 1: OTA Reservations ---{RESET}")
        self.test_endpoint(
            "GET",
            f"/reservations/{TEST_BOOKING_ID}/ota-details",
            expected_status=200,
            description="Get OTA reservation details"
        )
        
        # 2. Housekeeping
        print(f"\n{YELLOW}--- Module 2: Housekeeping ---{RESET}")
        self.test_endpoint(
            "GET",
            "/housekeeping/mobile/room-assignments",
            expected_status=200,
            description="Get housekeeping room assignments"
        )
        
        # 3. Revenue Management
        print(f"\n{YELLOW}--- Module 3: Revenue Management ---{RESET}")
        self.test_endpoint(
            "GET",
            "/rms/price-recommendation-slider",
            params={
                "room_type": "Standard",
                "check_in_date": "2025-12-01"
            },
            expected_status=200,
            description="Get price recommendation slider"
        )
        
        # 4. Messaging
        print(f"\n{YELLOW}--- Module 4: Messaging ---{RESET}")
        self.test_endpoint(
            "POST",
            "/messaging/send-message",
            data={
                "guest_id": TEST_GUEST_ID,
                "message_type": "WHATSAPP",
                "recipient": "+905551234567",
                "message_content": "Welcome to our hotel!",
                "booking_id": TEST_BOOKING_ID
            },
            expected_status=200,
            description="Send message to guest"
        )
        
        # 5. POS
        print(f"\n{YELLOW}--- Module 5: POS ---{RESET}")
        self.test_endpoint(
            "GET",
            "/pos/menu-items",
            expected_status=200,
            description="Get POS menu items"
        )
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n{BLUE}{'='*80}{RESET}")
        print(f"{BLUE}=== TEST SUMMARY ==={RESET}")
        print(f"{BLUE}{'='*80}{RESET}")
        
        total = self.results['total']
        passed = self.results['passed']
        failed = self.results['failed']
        success_rate = (passed / total * 100) if total > 0 else 0
        
        print(f"\nTotal Endpoints Tested: {total}")
        print(f"{GREEN}Passed: {passed}{RESET}")
        print(f"{RED}Failed: {failed}{RESET}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.results['failing_endpoints']:
            print(f"\n{RED}=== FAILING ENDPOINTS DETAILS ==={RESET}")
            for i, endpoint in enumerate(self.results['failing_endpoints'], 1):
                print(f"\n{i}. {endpoint['method']} {endpoint['endpoint']}")
                print(f"   Expected Status: {endpoint.get('expected_status', 'N/A')}")
                print(f"   Actual Status: {endpoint.get('actual_status', 'N/A')}")
                if endpoint.get('request_body'):
                    print(f"   Request Body: {json.dumps(endpoint['request_body'], indent=6)}")
                print(f"   Error: {endpoint.get('error', 'N/A')[:300]}")
        
        if self.results['working_endpoints']:
            print(f"\n{GREEN}=== WORKING ENDPOINTS ==={RESET}")
            for i, endpoint in enumerate(self.results['working_endpoints'], 1):
                print(f"{i}. {GREEN}✓{RESET} {endpoint['method']} {endpoint['endpoint']} (Status: {endpoint['status']})")
        
        print(f"\n{BLUE}{'='*80}{RESET}")
        print(f"{BLUE}Overall Backend Health: {success_rate:.1f}% ({passed}/{total} endpoints working){RESET}")
        print(f"{BLUE}{'='*80}{RESET}\n")
    
    def run(self):
        """Run the complete audit"""
        print(f"{BLUE}{'='*80}{RESET}")
        print(f"{BLUE}COMPREHENSIVE BACKEND ENDPOINT AUDIT{RESET}")
        print(f"{BLUE}Turkish Hotel PMS (Syroce){RESET}")
        print(f"{BLUE}{'='*80}{RESET}")
        
        # Step 1: Authenticate
        if not self.login():
            print(f"{RED}Authentication failed. Cannot proceed with tests.{RESET}")
            return
        
        # Step 2: Test failing endpoints
        self.test_failing_endpoints()
        
        # Step 3: Test sample endpoints from each module
        self.test_sample_endpoints()
        
        # Step 4: Print summary
        self.print_summary()

if __name__ == "__main__":
    auditor = EndpointAuditor()
    auditor.run()
