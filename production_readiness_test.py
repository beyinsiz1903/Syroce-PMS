#!/usr/bin/env python3
"""
ULTIMATE FINAL PRODUCTION READINESS TEST
Testing 24 endpoints across 6 departments for 100% production readiness
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Configuration
BACKEND_URL = "https://perf-boost-37.preview.emergentagent.com/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class ProductionReadinessTest:
    def __init__(self):
        self.token = None
        self.tenant_id = None
        self.results = {
            "hr": [],
            "fnb": [],
            "finance": [],
            "frontdesk": [],
            "game_changers": [],
            "previously_added": []
        }
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        
    def login(self):
        """Authenticate and get token"""
        print(f"\n{BLUE}=== AUTHENTICATION ==={RESET}")
        try:
            response = requests.post(
                f"{BACKEND_URL}/auth/login",
                json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.tenant_id = data.get("tenant", {}).get("id")
                print(f"{GREEN}✅ Login successful{RESET}")
                print(f"   Token: {self.token[:20]}...")
                print(f"   Tenant ID: {self.tenant_id}")
                return True
            else:
                print(f"{RED}❌ Login failed: {response.status_code}{RESET}")
                return False
        except Exception as e:
            print(f"{RED}❌ Login error: {str(e)}{RESET}")
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_endpoint(self, method: str, endpoint: str, data: dict = None, 
                     expected_status: int = 200, category: str = "general") -> Tuple[bool, str, float]:
        """Test a single endpoint"""
        self.total_tests += 1
        url = f"{BACKEND_URL}{endpoint}"
        start_time = time.time()
        
        try:
            if method == "GET":
                response = requests.get(url, headers=self.get_headers(), timeout=15)
            elif method == "POST":
                response = requests.post(url, headers=self.get_headers(), json=data, timeout=15)
            else:
                return False, f"Unsupported method: {method}", 0
            
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            if response.status_code == expected_status:
                self.passed_tests += 1
                self.results[category].append({
                    "endpoint": endpoint,
                    "status": "PASS",
                    "response_time": response_time,
                    "status_code": response.status_code
                })
                return True, f"HTTP {response.status_code}", response_time
            else:
                self.failed_tests += 1
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_detail = response.json()
                    if "detail" in error_detail:
                        error_msg += f" - {error_detail['detail']}"
                except:
                    pass
                
                self.results[category].append({
                    "endpoint": endpoint,
                    "status": "FAIL",
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "error": error_msg
                })
                return False, error_msg, response_time
                
        except requests.exceptions.Timeout:
            self.failed_tests += 1
            self.results[category].append({
                "endpoint": endpoint,
                "status": "FAIL",
                "error": "Timeout (>15s)"
            })
            return False, "Timeout (>15s)", 0
        except Exception as e:
            self.failed_tests += 1
            self.results[category].append({
                "endpoint": endpoint,
                "status": "FAIL",
                "error": str(e)
            })
            return False, str(e), 0
    
    def test_hr_suite(self):
        """Test HR Complete Suite (5 endpoints)"""
        print(f"\n{BLUE}=== 1. HR COMPLETE SUITE (İK Müdürü - Elif için) ==={RESET}")
        
        # 1. Clock In
        success, msg, rt = self.test_endpoint(
            "POST", "/hr/clock-in",
            data={"staff_id": "staff-001", "staff_name": "Ahmet Yılmaz"},
            category="hr"
        )
        print(f"{'✅' if success else '❌'} POST /api/hr/clock-in - {msg} ({rt:.0f}ms)")
        
        # 2. Clock Out
        success, msg, rt = self.test_endpoint(
            "POST", "/hr/clock-out",
            data={"staff_id": "staff-001", "staff_name": "Ahmet Yılmaz"},
            category="hr"
        )
        print(f"{'✅' if success else '❌'} POST /api/hr/clock-out - {msg} ({rt:.0f}ms)")
        
        # 3. Leave Request
        success, msg, rt = self.test_endpoint(
            "POST", "/hr/leave-request",
            data={
                "staff_id": "staff-001",
                "staff_name": "Ahmet Yılmaz",
                "leave_type": "annual",
                "start_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "end_date": (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d"),
                "reason": "Yıllık izin"
            },
            category="hr"
        )
        print(f"{'✅' if success else '❌'} POST /api/hr/leave-request - {msg} ({rt:.0f}ms)")
        
        # 4. Payroll
        current_month = datetime.now().strftime("%Y-%m")
        success, msg, rt = self.test_endpoint(
            "GET", f"/hr/payroll/{current_month}",
            category="hr"
        )
        print(f"{'✅' if success else '❌'} GET /api/hr/payroll/{current_month} - {msg} ({rt:.0f}ms)")
        
        # 5. Job Posting
        success, msg, rt = self.test_endpoint(
            "POST", "/hr/job-posting",
            data={
                "title": "Front Desk Agent",
                "department": "Front Office",
                "description": "Experienced front desk agent needed",
                "requirements": "2+ years experience",
                "salary_range": "25000-35000 TRY"
            },
            category="hr"
        )
        print(f"{'✅' if success else '❌'} POST /api/hr/job-posting - {msg} ({rt:.0f}ms)")
        
        hr_passed = len([r for r in self.results["hr"] if r["status"] == "PASS"])
        print(f"\n{YELLOW}HR Suite Result: {hr_passed}/5 endpoints working{RESET}")
    
    def test_fnb_suite(self):
        """Test F&B Complete Suite (5 endpoints)"""
        print(f"\n{BLUE}=== 2. F&B COMPLETE SUITE (Chef Marco için) ==={RESET}")
        
        # 1. Create Recipe
        success, msg, rt = self.test_endpoint(
            "POST", "/fnb/recipes",
            data={
                "recipe_name": "Izgara Köfte",
                "ingredients": [
                    {"name": "Kıyma", "quantity": 500, "unit": "gram", "cost": 75.0},
                    {"name": "Soğan", "quantity": 2, "unit": "piece", "cost": 5.0}
                ],
                "selling_price": 120.0,
                "category": "main_course"
            },
            category="fnb"
        )
        print(f"{'✅' if success else '❌'} POST /api/fnb/recipes - {msg} ({rt:.0f}ms)")
        
        # 2. Get Recipes
        success, msg, rt = self.test_endpoint(
            "GET", "/fnb/recipes",
            category="fnb"
        )
        print(f"{'✅' if success else '❌'} GET /api/fnb/recipes - {msg} ({rt:.0f}ms)")
        
        # 3. Create BEO
        success, msg, rt = self.test_endpoint(
            "POST", "/fnb/beo",
            data={
                "event_name": "Düğün Yemeği",
                "event_date": (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d"),
                "guest_count": 150,
                "menu_items": ["Izgara Köfte", "Pilav", "Salata"]
            },
            category="fnb"
        )
        print(f"{'✅' if success else '❌'} POST /api/fnb/beo - {msg} ({rt:.0f}ms)")
        
        # 4. Kitchen Display
        success, msg, rt = self.test_endpoint(
            "GET", "/fnb/kitchen-display",
            category="fnb"
        )
        print(f"{'✅' if success else '❌'} GET /api/fnb/kitchen-display - {msg} ({rt:.0f}ms)")
        
        # 5. Add Ingredient
        success, msg, rt = self.test_endpoint(
            "POST", "/fnb/ingredients",
            data={
                "ingredient_name": "Domates",
                "category": "vegetables",
                "unit": "kg",
                "current_stock": 50.0,
                "minimum_stock": 10.0,
                "unit_cost": 15.0
            },
            category="fnb"
        )
        print(f"{'✅' if success else '❌'} POST /api/fnb/ingredients - {msg} ({rt:.0f}ms)")
        
        fnb_passed = len([r for r in self.results["fnb"] if r["status"] == "PASS"])
        print(f"\n{YELLOW}F&B Suite Result: {fnb_passed}/5 endpoints working{RESET}")
    
    def test_finance_integration(self):
        """Test Finance Integration (2 endpoints)"""
        print(f"\n{BLUE}=== 3. FINANCE INTEGRATION (Cem için) ==={RESET}")
        
        # 1. Logo Integration Sync
        success, msg, rt = self.test_endpoint(
            "POST", "/finance/logo-integration/sync",
            data={"sync_type": "full", "date_range": "last_7_days"},
            category="finance"
        )
        print(f"{'✅' if success else '❌'} POST /api/finance/logo-integration/sync - {msg} ({rt:.0f}ms)")
        
        # 2. Budget vs Actual
        current_month = datetime.now().strftime("%Y-%m")
        success, msg, rt = self.test_endpoint(
            "GET", f"/finance/budget-vs-actual?month={current_month}",
            category="finance"
        )
        print(f"{'✅' if success else '❌'} GET /api/finance/budget-vs-actual?month={current_month} - {msg} ({rt:.0f}ms)")
        
        finance_passed = len([r for r in self.results["finance"] if r["status"] == "PASS"])
        print(f"\n{YELLOW}Finance Integration Result: {finance_passed}/2 endpoints working{RESET}")
    
    def test_frontdesk_express(self):
        """Test Front Office Express (2 endpoints)"""
        print(f"\n{BLUE}=== 4. FRONT OFFICE EXPRESS (Mehmet için) ==={RESET}")
        
        # 1. Express Check-in
        success, msg, rt = self.test_endpoint(
            "POST", "/frontdesk/express-checkin",
            data={
                "booking_id": "test-booking-001",
                "qr_code": "QR123456789",
                "signature": "base64_signature_data"
            },
            category="frontdesk"
        )
        print(f"{'✅' if success else '❌'} POST /api/frontdesk/express-checkin - {msg} ({rt:.0f}ms)")
        
        # 2. Kiosk Check-in
        success, msg, rt = self.test_endpoint(
            "POST", "/frontdesk/kiosk-checkin",
            data={
                "confirmation_number": "CONF123456",
                "id_scan_data": "passport_scan_data",
                "room_preference": "high_floor"
            },
            category="frontdesk"
        )
        print(f"{'✅' if success else '❌'} POST /api/frontdesk/kiosk-checkin - {msg} ({rt:.0f}ms)")
        
        frontdesk_passed = len([r for r in self.results["frontdesk"] if r["status"] == "PASS"])
        print(f"\n{YELLOW}Front Office Express Result: {frontdesk_passed}/2 endpoints working{RESET}")
    
    def test_game_changers(self):
        """Test Game-Changer Modules (6 endpoints)"""
        print(f"\n{BLUE}=== 5. GAME-CHANGER MODULES ==={RESET}")
        
        # 1. AI WhatsApp Concierge
        success, msg, rt = self.test_endpoint(
            "POST", "/ai-concierge/whatsapp",
            data={
                "guest_phone": "+905551234567",
                "message": "Havuz saat kaçta açık?",
                "guest_id": "guest-001"
            },
            category="game_changers"
        )
        print(f"{'✅' if success else '❌'} POST /api/ai-concierge/whatsapp - {msg} ({rt:.0f}ms)")
        
        # 2. Predictive No-Shows
        success, msg, rt = self.test_endpoint(
            "GET", "/predictions/no-shows",
            category="game_changers"
        )
        print(f"{'✅' if success else '❌'} GET /api/predictions/no-shows - {msg} ({rt:.0f}ms)")
        
        # 3. Social Media Mentions
        success, msg, rt = self.test_endpoint(
            "GET", "/social-media/mentions",
            category="game_changers"
        )
        print(f"{'✅' if success else '❌'} GET /api/social-media/mentions - {msg} ({rt:.0f}ms)")
        
        # 4. Revenue Autopilot
        success, msg, rt = self.test_endpoint(
            "POST", "/autopilot/run-cycle",
            data={"mode": "aggressive", "apply_changes": False},
            category="game_changers"
        )
        print(f"{'✅' if success else '❌'} POST /api/autopilot/run-cycle - {msg} ({rt:.0f}ms)")
        
        # 5. Guest DNA
        success, msg, rt = self.test_endpoint(
            "GET", "/guest-dna/guest-001",
            category="game_changers"
        )
        print(f"{'✅' if success else '❌'} GET /api/guest-dna/guest-001 - {msg} ({rt:.0f}ms)")
        
        # 6. Staffing AI
        success, msg, rt = self.test_endpoint(
            "GET", "/staffing-ai/optimal",
            category="game_changers"
        )
        print(f"{'✅' if success else '❌'} GET /api/staffing-ai/optimal - {msg} ({rt:.0f}ms)")
        
        gc_passed = len([r for r in self.results["game_changers"] if r["status"] == "PASS"])
        print(f"\n{YELLOW}Game-Changer Modules Result: {gc_passed}/6 endpoints working{RESET}")
    
    def test_previously_added(self):
        """Test Previously Added Features (4 endpoints)"""
        print(f"\n{BLUE}=== 6. PREVIOUSLY ADDED (Verify Still Working) ==={RESET}")
        
        # 1. Flash Report
        success, msg, rt = self.test_endpoint(
            "GET", "/reports/flash-report",
            category="previously_added"
        )
        print(f"{'✅' if success else '❌'} GET /api/reports/flash-report - {msg} ({rt:.0f}ms)")
        
        # 2. Group Block Creation
        success, msg, rt = self.test_endpoint(
            "POST", "/groups/create-block",
            data={
                "block_name": "Corporate Event 2025",
                "company_name": "ABC Corporation",
                "start_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "end_date": (datetime.now() + timedelta(days=33)).strftime("%Y-%m-%d"),
                "room_type": "Standard",
                "total_rooms": 20,
                "rate": 150.0
            },
            category="previously_added"
        )
        print(f"{'✅' if success else '❌'} POST /api/groups/create-block - {msg} ({rt:.0f}ms)")
        
        # 3. Today's Arrivals
        success, msg, rt = self.test_endpoint(
            "GET", "/arrivals/today",
            category="previously_added"
        )
        print(f"{'✅' if success else '❌'} GET /api/arrivals/today - {msg} ({rt:.0f}ms)")
        
        # 4. RMS Update Rate
        success, msg, rt = self.test_endpoint(
            "POST", "/rms/update-rate",
            data={
                "room_type": "Standard",
                "date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
                "new_rate": 180.0,
                "reason": "High demand period"
            },
            category="previously_added"
        )
        print(f"{'✅' if success else '❌'} POST /api/rms/update-rate - {msg} ({rt:.0f}ms)")
        
        prev_passed = len([r for r in self.results["previously_added"] if r["status"] == "PASS"])
        print(f"\n{YELLOW}Previously Added Result: {prev_passed}/4 endpoints working{RESET}")
    
    def print_final_report(self):
        """Print comprehensive final report"""
        print(f"\n{'='*80}")
        print(f"{BLUE}ULTIMATE FINAL PRODUCTION READINESS TEST - RESULTS{RESET}")
        print(f"{'='*80}\n")
        
        # Department-wise results
        departments = [
            ("HR Complete Suite", "hr", 5),
            ("F&B Complete Suite", "fnb", 5),
            ("Finance Integration", "finance", 2),
            ("Front Office Express", "frontdesk", 2),
            ("Game-Changer Modules", "game_changers", 6),
            ("Previously Added", "previously_added", 4)
        ]
        
        for dept_name, dept_key, expected in departments:
            passed = len([r for r in self.results[dept_key] if r["status"] == "PASS"])
            failed = len([r for r in self.results[dept_key] if r["status"] == "FAIL"])
            
            status_icon = "✅" if passed == expected else "❌"
            print(f"{status_icon} {dept_name}: {passed}/{expected} endpoints working")
            
            # Show failed endpoints
            if failed > 0:
                for result in self.results[dept_key]:
                    if result["status"] == "FAIL":
                        print(f"   {RED}❌ {result['endpoint']} - {result.get('error', 'Unknown error')}{RESET}")
        
        # Overall statistics
        print(f"\n{BLUE}OVERALL STATISTICS:{RESET}")
        print(f"Total Endpoints Tested: {self.total_tests}")
        print(f"Passed: {GREEN}{self.passed_tests}{RESET}")
        print(f"Failed: {RED}{self.failed_tests}{RESET}")
        
        success_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        # Performance metrics
        all_response_times = []
        for category in self.results.values():
            for result in category:
                if "response_time" in result:
                    all_response_times.append(result["response_time"])
        
        if all_response_times:
            avg_response_time = sum(all_response_times) / len(all_response_times)
            max_response_time = max(all_response_times)
            print(f"\n{BLUE}PERFORMANCE METRICS:{RESET}")
            print(f"Average Response Time: {avg_response_time:.0f}ms")
            print(f"Max Response Time: {max_response_time:.0f}ms")
            
            if avg_response_time < 100:
                print(f"{GREEN}✅ Average response time <100ms - EXCELLENT{RESET}")
            else:
                print(f"{YELLOW}⚠️ Average response time >{avg_response_time:.0f}ms - NEEDS OPTIMIZATION{RESET}")
        
        # Production readiness verdict
        print(f"\n{BLUE}PRODUCTION READINESS VERDICT:{RESET}")
        if self.passed_tests == 24:
            print(f"{GREEN}🎉 100% SUCCESS - SYSTEM IS PRODUCTION READY!{RESET}")
            print(f"{GREEN}✅ All 24 endpoints working correctly{RESET}")
            print(f"{GREEN}✅ All departments' critical features operational{RESET}")
            print(f"{GREEN}✅ System stable and ready for launch{RESET}")
        elif self.passed_tests >= 20:
            print(f"{YELLOW}⚠️ MOSTLY READY - {self.failed_tests} endpoints need attention{RESET}")
            print(f"{YELLOW}Core functionality working, minor fixes needed{RESET}")
        else:
            print(f"{RED}❌ NOT READY - {self.failed_tests} critical endpoints failing{RESET}")
            print(f"{RED}Significant issues need to be resolved before production{RESET}")
        
        print(f"\n{'='*80}\n")

def main():
    """Main test execution"""
    print(f"{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}ULTIMATE FINAL PRODUCTION READINESS TEST{RESET}")
    print(f"{BLUE}Testing 24 endpoints across 6 departments{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    tester = ProductionReadinessTest()
    
    # Step 1: Login
    if not tester.login():
        print(f"\n{RED}❌ Authentication failed. Cannot proceed with tests.{RESET}")
        return
    
    # Step 2: Run all department tests
    tester.test_hr_suite()
    tester.test_fnb_suite()
    tester.test_finance_integration()
    tester.test_frontdesk_express()
    tester.test_game_changers()
    tester.test_previously_added()
    
    # Step 3: Print final report
    tester.print_final_report()

if __name__ == "__main__":
    main()
