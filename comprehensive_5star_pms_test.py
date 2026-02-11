#!/usr/bin/env python3
"""
Comprehensive 5-Star Hotel PMS Backend Test
Tests 25+ modules with 50+ endpoints
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Configuration
BASE_URL = "https://error-sweep-audit.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class TestResult:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def add_result(self, endpoint: str, method: str, status: bool, status_code: int, 
                   response_time: float, error: Optional[str] = None, priority: str = "MEDIUM"):
        self.total += 1
        if status:
            self.passed += 1
        else:
            self.failed += 1
        
        self.results.append({
            'endpoint': endpoint,
            'method': method,
            'status': status,
            'status_code': status_code,
            'response_time': response_time,
            'error': error,
            'priority': priority
        })
    
    def print_summary(self):
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}COMPREHENSIVE 5-STAR HOTEL PMS TEST RESULTS{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        
        success_rate = (self.passed / self.total * 100) if self.total > 0 else 0
        
        print(f"Total Endpoints Tested: {self.total}")
        print(f"{Colors.GREEN}✅ Passed: {self.passed}{Colors.RESET}")
        print(f"{Colors.RED}❌ Failed: {self.failed}{Colors.RESET}")
        print(f"Success Rate: {success_rate:.1f}%\n")
        
        # Group by priority
        critical_failed = [r for r in self.results if not r['status'] and r['priority'] == 'CRITICAL']
        high_failed = [r for r in self.results if not r['status'] and r['priority'] == 'HIGH']
        medium_failed = [r for r in self.results if not r['status'] and r['priority'] == 'MEDIUM']
        low_failed = [r for r in self.results if not r['status'] and r['priority'] == 'LOW']
        
        if critical_failed:
            print(f"{Colors.RED}{Colors.BOLD}CRITICAL FAILURES ({len(critical_failed)}):{Colors.RESET}")
            for r in critical_failed:
                print(f"  ❌ {r['method']} {r['endpoint']} - {r['status_code']} - {r['error']}")
            print()
        
        if high_failed:
            print(f"{Colors.RED}HIGH PRIORITY FAILURES ({len(high_failed)}):{Colors.RESET}")
            for r in high_failed:
                print(f"  ❌ {r['method']} {r['endpoint']} - {r['status_code']} - {r['error']}")
            print()
        
        if medium_failed:
            print(f"{Colors.YELLOW}MEDIUM PRIORITY FAILURES ({len(medium_failed)}):{Colors.RESET}")
            for r in medium_failed:
                print(f"  ⚠️  {r['method']} {r['endpoint']} - {r['status_code']} - {r['error']}")
            print()
        
        if low_failed:
            print(f"{Colors.YELLOW}LOW PRIORITY FAILURES ({len(low_failed)}):{Colors.RESET}")
            for r in low_failed:
                print(f"  ⚠️  {r['method']} {r['endpoint']} - {r['status_code']} - {r['error']}")
            print()
        
        # Success criteria check
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        if success_rate >= 90:
            print(f"{Colors.GREEN}{Colors.BOLD}✅ SUCCESS CRITERIA MET: {success_rate:.1f}% >= 90%{Colors.RESET}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}❌ SUCCESS CRITERIA NOT MET: {success_rate:.1f}% < 90%{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")

class HotelPMSTest:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tenant_id = None
        self.results = TestResult()
        self.test_data = {}
    
    def test_endpoint(self, method: str, endpoint: str, priority: str = "MEDIUM", 
                     data: Optional[Dict] = None, params: Optional[Dict] = None,
                     expected_status: int = 200) -> Optional[Dict]:
        """Test an endpoint and record results"""
        url = f"{self.base_url}{endpoint}"
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            start_time = datetime.now()
            
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                headers['Content-Type'] = 'application/json'
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == 'PUT':
                headers['Content-Type'] = 'application/json'
                response = requests.put(url, headers=headers, json=data, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            success = response.status_code == expected_status
            error = None if success else f"Expected {expected_status}, got {response.status_code}"
            
            if not success and response.status_code in [400, 422, 500]:
                try:
                    error_detail = response.json()
                    error = f"{response.status_code} - {error_detail.get('detail', 'Unknown error')}"
                except:
                    error = f"{response.status_code} - {response.text[:100]}"
            
            self.results.add_result(endpoint, method, success, response.status_code, 
                                   response_time, error, priority)
            
            status_icon = f"{Colors.GREEN}✅{Colors.RESET}" if success else f"{Colors.RED}❌{Colors.RESET}"
            print(f"{status_icon} [{priority:8}] {method:6} {endpoint:50} {response.status_code} ({response_time:.0f}ms)")
            
            if success:
                try:
                    return response.json()
                except:
                    return None
            return None
            
        except requests.exceptions.Timeout:
            self.results.add_result(endpoint, method, False, 0, 30000, "Timeout", priority)
            print(f"{Colors.RED}❌{Colors.RESET} [{priority:8}] {method:6} {endpoint:50} TIMEOUT")
            return None
        except Exception as e:
            self.results.add_result(endpoint, method, False, 0, 0, str(e), priority)
            print(f"{Colors.RED}❌{Colors.RESET} [{priority:8}] {method:6} {endpoint:50} ERROR: {str(e)}")
            return None
    
    def run_all_tests(self):
        """Run all comprehensive tests"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}STARTING COMPREHENSIVE 5-STAR HOTEL PMS BACKEND TEST{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}\n")
        
        # CRITICAL PRIORITY - Authentication & Email
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}CRITICAL PRIORITY: AUTHENTICATION & EMAIL{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        
        self.test_authentication()
        self.test_email_verification()
        
        # HIGH PRIORITY
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}HIGH PRIORITY: FLASH REPORT{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_flash_report()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}HIGH PRIORITY: GROUP SALES{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_group_sales()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}HIGH PRIORITY: VIP MANAGEMENT{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_vip_management()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}HIGH PRIORITY: SALES CRM{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_sales_crm()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}HIGH PRIORITY: AI FEATURES{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_ai_features()
        
        # MEDIUM PRIORITY
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}MEDIUM PRIORITY: SERVICE RECOVERY{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_service_recovery()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}MEDIUM PRIORITY: SPA & EVENTS{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_spa_events()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}MEDIUM PRIORITY: ADVANCED FEATURES{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_advanced_features()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}MEDIUM PRIORITY: GUEST JOURNEY{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_guest_journey()
        
        # LOW PRIORITY
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}LOW PRIORITY: GDS & MOBILE{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_gds_mobile()
        
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}LOW PRIORITY: HR & STAFF{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        self.test_hr_staff()
        
        # Print final summary
        self.results.print_summary()
    
    def test_authentication(self):
        """Test authentication endpoints"""
        # 1. Login
        login_data = {
            "email": LOGIN_EMAIL,
            "password": LOGIN_PASSWORD
        }
        response = self.test_endpoint('POST', '/auth/login', 'CRITICAL', data=login_data)
        
        if response and 'access_token' in response:
            self.token = response['access_token']
            if 'tenant' in response and response['tenant']:
                self.tenant_id = response['tenant'].get('id')
            print(f"{Colors.GREEN}✓ Authentication successful - Token obtained{Colors.RESET}\n")
        else:
            print(f"{Colors.RED}✗ Authentication failed - Cannot proceed with tests{Colors.RESET}\n")
            return
        
        # 2. Request verification code
        verification_data = {
            "email": "test@example.com",
            "user_type": "hotel",
            "property_name": "Test Hotel"
        }
        self.test_endpoint('POST', '/auth/request-verification', 'CRITICAL', data=verification_data)
        
        # 3. Forgot password
        forgot_data = {
            "email": LOGIN_EMAIL
        }
        self.test_endpoint('POST', '/auth/forgot-password', 'CRITICAL', data=forgot_data)
    
    def test_email_verification(self):
        """Test email verification system"""
        # Already tested in authentication section
        pass
    
    def test_flash_report(self):
        """Test flash report endpoint"""
        # 4. GET flash report
        self.test_endpoint('GET', '/reports/flash-report', 'HIGH')
    
    def test_group_sales(self):
        """Test group sales endpoints"""
        # Create test guest first
        guest_data = {
            "name": "Group Contact Person",
            "email": f"group_{datetime.now().timestamp()}@test.com",
            "phone": "+1234567890",
            "id_number": f"GRP{int(datetime.now().timestamp())}"
        }
        guest_response = self.test_endpoint('POST', '/pms/guests', 'HIGH', data=guest_data)
        
        if guest_response:
            guest_id = guest_response.get('id')
            self.test_data['group_guest_id'] = guest_id
        
        # 5. Create group block
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        next_week = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        block_data = {
            "block_name": "Corporate Conference 2025",
            "group_type": "corporate",
            "contact_person": "John Smith",
            "contact_email": f"conference_{datetime.now().timestamp()}@company.com",
            "contact_phone": "+1234567890",
            "check_in_date": tomorrow,
            "check_out_date": next_week,
            "total_rooms": 15,
            "adults_per_room": 2,
            "special_requests": "Conference room setup required"
        }
        block_response = self.test_endpoint('POST', '/groups/create-block', 'HIGH', data=block_data)
        
        if block_response:
            block_id = block_response.get('block_id') or block_response.get('id')
            self.test_data['block_id'] = block_id
        
        # 6. List all groups
        self.test_endpoint('GET', '/groups/blocks', 'HIGH')
        
        # 7. Get group details
        if 'block_id' in self.test_data:
            self.test_endpoint('GET', f"/groups/block/{self.test_data['block_id']}", 'HIGH')
    
    def test_vip_management(self):
        """Test VIP management endpoints"""
        # Create test guest if not exists
        if 'group_guest_id' not in self.test_data:
            guest_data = {
                "name": "VIP Guest",
                "email": f"vip_{datetime.now().timestamp()}@test.com",
                "phone": "+1234567890",
                "id_number": f"VIP{int(datetime.now().timestamp())}"
            }
            guest_response = self.test_endpoint('POST', '/pms/guests', 'HIGH', data=guest_data)
            if guest_response:
                self.test_data['vip_guest_id'] = guest_response.get('id')
        
        guest_id = self.test_data.get('vip_guest_id') or self.test_data.get('group_guest_id')
        
        if guest_id:
            # 8. Create VIP protocol
            vip_data = {
                "preferences": {
                    "room_floor": "high",
                    "pillow_type": "soft",
                    "room_temperature": "22C"
                },
                "special_instructions": "Welcome champagne and fruit basket",
                "dietary_restrictions": ["vegetarian"],
                "celebration_type": "birthday",
                "celebration_date": (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
            }
            self.test_endpoint('POST', f'/guests/{guest_id}/vip-protocol', 'HIGH', data=vip_data)
        
        # 9. List VIP guests
        self.test_endpoint('GET', '/vip/list', 'HIGH')
        
        # 10. Upcoming celebrations
        self.test_endpoint('GET', '/celebrations/upcoming', 'HIGH')
    
    def test_sales_crm(self):
        """Test sales CRM endpoints"""
        # 11. Create sales lead
        lead_data = {
            "company_name": "Tech Corp International",
            "contact_person": "Jane Doe",
            "contact_email": f"sales_{datetime.now().timestamp()}@techcorp.com",
            "contact_phone": "+1234567890",
            "lead_source": "website",
            "estimated_rooms": 50,
            "estimated_value": 25000.0,
            "notes": "Interested in quarterly corporate bookings"
        }
        lead_response = self.test_endpoint('POST', '/sales/leads', 'HIGH', data=lead_data)
        
        if lead_response:
            self.test_data['lead_id'] = lead_response.get('id')
        
        # 12. Sales funnel metrics
        self.test_endpoint('GET', '/sales/funnel', 'HIGH')
        
        # 13. Log sales activity
        if 'lead_id' in self.test_data:
            activity_data = {
                "lead_id": self.test_data['lead_id'],
                "activity_type": "call",
                "notes": "Initial discovery call completed",
                "next_action": "Send proposal",
                "next_action_date": (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
            }
            self.test_endpoint('POST', '/sales/activity', 'HIGH', data=activity_data)
    
    def test_service_recovery(self):
        """Test service recovery endpoints"""
        # 14. Create complaint
        complaint_data = {
            "guest_name": "Unhappy Guest",
            "room_number": "101",
            "complaint_type": "noise",
            "description": "Loud noise from adjacent room",
            "severity": "medium",
            "reported_by": "Front Desk"
        }
        complaint_response = self.test_endpoint('POST', '/service/complaints', 'MEDIUM', data=complaint_data)
        
        # 15. List complaints
        self.test_endpoint('GET', '/service/complaints', 'MEDIUM')
    
    def test_ai_features(self):
        """Test AI-powered features"""
        # 16. AI pricing recommendation
        params = {
            "room_type": "Standard",
            "target_date": "2025-12-01"
        }
        self.test_endpoint('GET', '/pricing/ai-recommendation', 'HIGH', params=params)
        
        # 17. Reputation overview
        self.test_endpoint('GET', '/reputation/overview', 'HIGH')
        
        # 18. Reputation trends
        self.test_endpoint('GET', '/reputation/trends', 'HIGH')
        
        # 19. AI chatbot
        chat_data = {
            "message": "What is the occupancy rate for next week?",
            "context": "dashboard"
        }
        self.test_endpoint('POST', '/ai/chat', 'HIGH', data=chat_data)
    
    def test_spa_events(self):
        """Test spa and events endpoints"""
        # 20. Create spa appointment
        spa_data = {
            "guest_name": "Spa Guest",
            "treatment_type": "massage",
            "appointment_date": (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            "appointment_time": "14:00",
            "duration_minutes": 60,
            "therapist": "Maria"
        }
        self.test_endpoint('POST', '/spa/appointments', 'MEDIUM', data=spa_data)
        
        # 21. List spa appointments
        self.test_endpoint('GET', '/spa/appointments', 'MEDIUM')
        
        # 22. Create event booking
        event_data = {
            "event_name": "Corporate Meeting",
            "event_type": "meeting",
            "event_date": (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
            "start_time": "09:00",
            "end_time": "17:00",
            "attendees": 25,
            "room_setup": "theater",
            "catering_required": True
        }
        self.test_endpoint('POST', '/events/bookings', 'MEDIUM', data=event_data)
        
        # 23. List event bookings
        self.test_endpoint('GET', '/events/bookings', 'MEDIUM')
    
    def test_advanced_features(self):
        """Test advanced features"""
        # 24. Multi-property dashboard
        self.test_endpoint('GET', '/multi-property/dashboard', 'MEDIUM')
        
        # 25. Installment calculator
        params = {
            "amount": 1000,
            "months": 6
        }
        self.test_endpoint('GET', '/payments/installment', 'MEDIUM', params=params)
        
        # 26. Add loyalty points
        if 'vip_guest_id' in self.test_data or 'group_guest_id' in self.test_data:
            guest_id = self.test_data.get('vip_guest_id') or self.test_data.get('group_guest_id')
            points_data = {
                "guest_id": guest_id,
                "points": 100,
                "transaction_type": "earn",
                "description": "Stay bonus points"
            }
            self.test_endpoint('POST', '/loyalty/points', 'MEDIUM', data=points_data)
            
            # 27. Get loyalty member details
            self.test_endpoint('GET', f'/loyalty/member/{guest_id}', 'MEDIUM')
    
    def test_gds_mobile(self):
        """Test GDS and mobile endpoints"""
        # 28. Push rate to GDS
        rate_data = {
            "room_type": "Standard",
            "date": (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            "rate": 150.0,
            "availability": 10
        }
        self.test_endpoint('POST', '/gds/push-rate', 'LOW', data=rate_data)
        
        # 29. GDS reservations
        self.test_endpoint('GET', '/gds/reservations', 'LOW')
        
        # 30. Register mobile device
        device_data = {
            "device_id": f"device_{int(datetime.now().timestamp())}",
            "device_type": "ios",
            "push_token": "test_push_token_12345",
            "app_version": "1.0.0"
        }
        self.test_endpoint('POST', '/mobile/register-device', 'LOW', data=device_data)
    
    def test_hr_staff(self):
        """Test HR and staff endpoints"""
        # 31. Add staff member
        staff_data = {
            "name": "John Employee",
            "email": f"staff_{datetime.now().timestamp()}@hotel.com",
            "phone": "+1234567890",
            "department": "housekeeping",
            "position": "Room Attendant",
            "hire_date": datetime.now().strftime('%Y-%m-%d'),
            "salary": 2500.0
        }
        staff_response = self.test_endpoint('POST', '/hr/staff', 'LOW', data=staff_data)
        
        if staff_response:
            self.test_data['staff_id'] = staff_response.get('id')
        
        # 32. List staff
        self.test_endpoint('GET', '/hr/staff', 'LOW')
        
        # 33. Staff performance
        if 'staff_id' in self.test_data:
            self.test_endpoint('GET', f"/hr/performance/{self.test_data['staff_id']}", 'LOW')
    
    def test_guest_journey(self):
        """Test guest journey endpoints"""
        # 34. Log journey event
        event_data = {
            "guest_id": self.test_data.get('vip_guest_id') or self.test_data.get('group_guest_id'),
            "event_type": "check_in",
            "event_data": {
                "room": "101",
                "time": datetime.now().isoformat()
            }
        }
        if event_data['guest_id']:
            self.test_endpoint('POST', '/journey/log-event', 'MEDIUM', data=event_data)
        
        # 35. Submit NPS survey
        nps_data = {
            "score": 9,
            "feedback": "Excellent service and clean rooms",
            "guest_email": "satisfied@guest.com"
        }
        self.test_endpoint('POST', '/nps/survey', 'MEDIUM', data=nps_data)
        
        # 36. Get NPS score
        self.test_endpoint('GET', '/nps/score', 'MEDIUM')

def main():
    """Main test execution"""
    tester = HotelPMSTest()
    tester.run_all_tests()

if __name__ == "__main__":
    main()
