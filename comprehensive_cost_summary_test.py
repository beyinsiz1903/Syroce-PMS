#!/usr/bin/env python3
"""
Comprehensive Cost Summary Endpoint Testing
Testing all aspects of GET /api/reports/cost-summary
"""

import requests
import json
from datetime import datetime, timezone, timedelta

BACKEND_URL = 'https://perf-boost-37.preview.emergentagent.com/api'
TEST_EMAIL = 'test@hotel.com'
TEST_PASSWORD = 'test123'

class ComprehensiveCostSummaryTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []

    def authenticate(self):
        """Authenticate with the backend"""
        print("🔐 Authenticating...")
        response = self.session.post(f"{BACKEND_URL}/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if response.status_code == 200:
            data = response.json()
            self.auth_token = data["access_token"]
            self.tenant_id = data["user"]["tenant_id"]
            self.user_id = data["user"]["id"]
            self.session.headers.update({
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            })
            print(f"✅ Authentication successful - User: {data['user']['name']}")
            return True
        else:
            print(f"❌ Authentication failed: {response.status_code} - {response.text}")
            return False

    def log_test_result(self, test_name, success, details=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {"test": test_name, "status": status, "details": details}
        self.test_results.append(result)
        print(f"  {status}: {test_name} - {details}")

    def setup_comprehensive_test_data(self):
        """Setup comprehensive test data covering all categories"""
        print("\n🔧 Setting up comprehensive test data...")
        
        # Create purchase orders for all categories
        test_pos = [
            # Housekeeping category
            {"supplier": "CleanCorp", "category": "cleaning", "items": [{"product_name": "All-purpose cleaner", "quantity": 10, "unit_price": 15.0}], "total_amount": 150.0, "delivery_location": "Housekeeping", "status": "approved"},
            {"supplier": "LinenSupply", "category": "linens", "items": [{"product_name": "Bed sheets", "quantity": 20, "unit_price": 25.0}], "total_amount": 500.0, "delivery_location": "Housekeeping", "status": "received"},
            {"supplier": "AmenityPlus", "category": "amenities", "items": [{"product_name": "Shampoo bottles", "quantity": 50, "unit_price": 3.0}], "total_amount": 150.0, "delivery_location": "Housekeeping", "status": "completed"},
            
            # F&B category  
            {"supplier": "FoodSupply Inc", "category": "food", "items": [{"product_name": "Fresh vegetables", "quantity": 50, "unit_price": 8.0}], "total_amount": 400.0, "delivery_location": "Kitchen", "status": "approved"},
            {"supplier": "BeverageCorp", "category": "beverage", "items": [{"product_name": "Wine bottles", "quantity": 24, "unit_price": 15.0}], "total_amount": 360.0, "delivery_location": "Bar", "status": "received"},
            {"supplier": "KitchenSupply", "category": "kitchen", "items": [{"product_name": "Kitchen utensils", "quantity": 10, "unit_price": 12.0}], "total_amount": 120.0, "delivery_location": "Kitchen", "status": "completed"},
            
            # Technical category
            {"supplier": "TechFix Ltd", "category": "maintenance", "items": [{"product_name": "HVAC filters", "quantity": 5, "unit_price": 25.0}], "total_amount": 125.0, "delivery_location": "Maintenance", "status": "approved"},
            {"supplier": "ElectricPro", "category": "electrical", "items": [{"product_name": "LED bulbs", "quantity": 30, "unit_price": 8.0}], "total_amount": 240.0, "delivery_location": "Maintenance", "status": "received"},
            {"supplier": "PlumbingFix", "category": "plumbing", "items": [{"product_name": "Pipe fittings", "quantity": 15, "unit_price": 6.0}], "total_amount": 90.0, "delivery_location": "Maintenance", "status": "completed"},
            {"supplier": "HVACService", "category": "hvac", "items": [{"product_name": "Air filters", "quantity": 8, "unit_price": 20.0}], "total_amount": 160.0, "delivery_location": "Maintenance", "status": "approved"},
            
            # General Expenses category
            {"supplier": "FurniturePlus", "category": "furniture", "items": [{"product_name": "Office chairs", "quantity": 5, "unit_price": 80.0}], "total_amount": 400.0, "delivery_location": "Office", "status": "approved"},
            {"supplier": "OfficeSupply Co", "category": "office", "items": [{"product_name": "Printer paper", "quantity": 20, "unit_price": 12.0}], "total_amount": 240.0, "delivery_location": "Front Office", "status": "received"},
            {"supplier": "ITSolutions", "category": "it", "items": [{"product_name": "Network cables", "quantity": 10, "unit_price": 15.0}], "total_amount": 150.0, "delivery_location": "IT Room", "status": "completed"},
            {"supplier": "MiscSupplier", "category": "other", "items": [{"product_name": "Miscellaneous items", "quantity": 1, "unit_price": 75.0}], "total_amount": 75.0, "delivery_location": "Storage", "status": "approved"}
        ]
        
        created_pos = []
        total_expected = 0
        
        for po_data in test_pos:
            try:
                response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders", json=po_data)
                if response.status_code in [200, 201]:
                    po = response.json()
                    po_id = po.get('id')
                    
                    # Approve the PO if it was created as pending
                    if po.get('status') == 'pending' and po_data['status'] in ['approved', 'received', 'completed']:
                        approve_response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders/{po_id}/approve", 
                                                           json={"approval_notes": "Test approval"})
                        if approve_response.status_code in [200, 201]:
                            print(f"  ✅ Created & Approved PO: {po_data['supplier']} - ${po_data['total_amount']} ({po_data['category']})")
                            created_pos.append(po_id)
                            total_expected += po_data['total_amount']
                        else:
                            print(f"  ⚠️ Created but failed to approve PO: {po_data['supplier']}")
                    else:
                        print(f"  ✅ Created PO: {po_data['supplier']} - ${po_data['total_amount']} ({po_data['category']})")
                        created_pos.append(po_id)
                        total_expected += po_data['total_amount']
                else:
                    print(f"  ❌ Failed to create PO for {po_data['supplier']}: {response.status_code}")
            except Exception as e:
                print(f"  ❌ Error creating PO for {po_data['supplier']}: {str(e)}")
        
        print(f"  📊 Created {len(created_pos)} purchase orders, Expected total: ${total_expected}")
        
        # Create some rooms and bookings for per-room calculations
        print("\n🏨 Creating rooms and bookings for per-room metrics...")
        
        # Create rooms
        rooms_data = [
            {"room_number": "101", "room_type": "standard", "floor": 1, "capacity": 2, "base_price": 100.0},
            {"room_number": "102", "room_type": "standard", "floor": 1, "capacity": 2, "base_price": 100.0},
            {"room_number": "201", "room_type": "deluxe", "floor": 2, "capacity": 3, "base_price": 150.0}
        ]
        
        room_ids = []
        for room_data in rooms_data:
            try:
                response = self.session.post(f"{BACKEND_URL}/pms/rooms", json=room_data)
                if response.status_code in [200, 201]:
                    room = response.json()
                    room_ids.append(room.get('id'))
                    print(f"  ✅ Created room: {room_data['room_number']}")
            except Exception as e:
                print(f"  ⚠️ Error creating room {room_data['room_number']}: {str(e)}")
        
        # Create guests and bookings
        if room_ids:
            guest_data = {"name": "Test Guest", "email": "guest@test.com", "phone": "+1234567890", "id_number": "ID123456"}
            try:
                response = self.session.post(f"{BACKEND_URL}/pms/guests", json=guest_data)
                if response.status_code in [200, 201]:
                    guest = response.json()
                    guest_id = guest.get('id')
                    print(f"  ✅ Created guest: {guest_data['name']}")
                    
                    # Create bookings for this month
                    today = datetime.now(timezone.utc)
                    check_in = today.replace(day=5)  # 5th of this month
                    check_out = today.replace(day=8)  # 8th of this month (3 nights)
                    
                    booking_data = {
                        "guest_id": guest_id,
                        "room_id": room_ids[0],
                        "check_in": check_in.isoformat(),
                        "check_out": check_out.isoformat(),
                        "adults": 2,
                        "children": 0,
                        "children_ages": [],
                        "guests_count": 2,
                        "total_amount": 300.0
                    }
                    
                    response = self.session.post(f"{BACKEND_URL}/pms/bookings", json=booking_data)
                    if response.status_code in [200, 201]:
                        booking = response.json()
                        booking_id = booking.get('id')
                        print(f"  ✅ Created booking: 3 nights, ${booking_data['total_amount']}")
                        
                        # Check in the booking to make it count for room nights
                        try:
                            checkin_response = self.session.post(f"{BACKEND_URL}/frontdesk/checkin/{booking_id}")
                            if checkin_response.status_code in [200, 201]:
                                print(f"  ✅ Checked in booking")
                            else:
                                print(f"  ⚠️ Failed to check in booking: {checkin_response.status_code}")
                        except Exception as e:
                            print(f"  ⚠️ Error checking in booking: {str(e)}")
                            
                        # Create folio and add room charges for revenue calculation
                        try:
                            folio_data = {"booking_id": booking_id, "folio_type": "guest"}
                            folio_response = self.session.post(f"{BACKEND_URL}/folio/create", json=folio_data)
                            if folio_response.status_code in [200, 201]:
                                folio = folio_response.json()
                                folio_id = folio.get('id')
                                print(f"  ✅ Created folio")
                                
                                # Add room charges
                                charge_data = {
                                    "charge_category": "room",
                                    "description": "Room charge",
                                    "amount": 100.0,
                                    "quantity": 3.0  # 3 nights
                                }
                                charge_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/charge", json=charge_data)
                                if charge_response.status_code in [200, 201]:
                                    print(f"  ✅ Added room charges: $300")
                                else:
                                    print(f"  ⚠️ Failed to add room charges: {charge_response.status_code}")
                            else:
                                print(f"  ⚠️ Failed to create folio: {folio_response.status_code}")
                        except Exception as e:
                            print(f"  ⚠️ Error creating folio/charges: {str(e)}")
                    else:
                        print(f"  ❌ Failed to create booking: {response.status_code}")
                else:
                    print(f"  ❌ Failed to create guest: {response.status_code}")
            except Exception as e:
                print(f"  ❌ Error creating guest: {str(e)}")
        
        return {"expected_total": total_expected, "created_pos": len(created_pos)}

    def test_comprehensive_cost_summary(self):
        """Test comprehensive cost summary with all categories"""
        print("\n📊 Testing Comprehensive Cost Summary...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/cost-summary")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                print(f"\n📋 Cost Summary Response:")
                print(json.dumps(data, indent=2))
                
                issues = []
                
                # Test 1: Basic structure
                required_fields = ['report_date', 'period', 'total_mtd_costs', 'cost_categories', 'top_3_categories', 'per_room_metrics', 'financial_metrics']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    issues.append(f"Missing required fields: {missing_fields}")
                
                # Test 2: Cost categories mapping
                cost_categories = data.get('cost_categories', {})
                expected_categories = ['housekeeping', 'fnb', 'technical', 'general_expenses']
                missing_categories = [cat for cat in expected_categories if cat not in cost_categories]
                if missing_categories:
                    issues.append(f"Missing cost categories: {missing_categories}")
                
                # Test 3: Verify category totals make sense
                total_from_categories = sum(cost_categories.values())
                total_mtd_costs = data.get('total_mtd_costs', 0)
                if abs(total_from_categories - total_mtd_costs) > 0.01:
                    issues.append(f"Category totals ({total_from_categories}) don't match total MTD costs ({total_mtd_costs})")
                
                # Test 4: Top 3 categories validation
                top_3 = data.get('top_3_categories', [])
                if len(top_3) > 3:
                    issues.append(f"top_3_categories has {len(top_3)} items, should be max 3")
                
                # Check sorting (descending by amount)
                for i in range(1, len(top_3)):
                    if top_3[i]['amount'] > top_3[i-1]['amount']:
                        issues.append(f"top_3_categories not sorted correctly")
                        break
                
                # Test 5: Numerical precision
                def check_precision(value, decimal_places, field_name):
                    if isinstance(value, (int, float)) and round(value, decimal_places) != value:
                        return f"{field_name} not rounded to {decimal_places} decimal places: {value}"
                    return None
                
                # Check amounts (2 decimal places)
                precision_issues = []
                precision_issues.append(check_precision(total_mtd_costs, 2, "total_mtd_costs"))
                
                for cat_name, amount in cost_categories.items():
                    precision_issues.append(check_precision(amount, 2, f"cost_categories.{cat_name}"))
                
                for i, cat in enumerate(top_3):
                    precision_issues.append(check_precision(cat.get('amount', 0), 2, f"top_3_categories[{i}].amount"))
                    precision_issues.append(check_precision(cat.get('percentage', 0), 1, f"top_3_categories[{i}].percentage"))
                
                # Check per-room metrics
                per_room = data.get('per_room_metrics', {})
                precision_issues.append(check_precision(per_room.get('cost_per_room_night', 0), 2, "cost_per_room_night"))
                precision_issues.append(check_precision(per_room.get('mtd_revpar', 0), 2, "mtd_revpar"))
                precision_issues.append(check_precision(per_room.get('cost_to_revpar_ratio', 0), 1, "cost_to_revpar_ratio"))
                
                # Check financial metrics
                financial = data.get('financial_metrics', {})
                precision_issues.append(check_precision(financial.get('mtd_revenue', 0), 2, "mtd_revenue"))
                precision_issues.append(check_precision(financial.get('mtd_costs', 0), 2, "mtd_costs"))
                precision_issues.append(check_precision(financial.get('gross_profit', 0), 2, "gross_profit"))
                precision_issues.append(check_precision(financial.get('profit_margin_percentage', 0), 1, "profit_margin_percentage"))
                precision_issues.append(check_precision(financial.get('cost_to_revenue_ratio', 0), 1, "cost_to_revenue_ratio"))
                
                precision_issues = [issue for issue in precision_issues if issue is not None]
                if precision_issues:
                    issues.extend(precision_issues)
                
                # Test 6: Calculation verification
                total_room_nights = per_room.get('total_room_nights', 0)
                cost_per_room_night = per_room.get('cost_per_room_night', 0)
                mtd_revpar = per_room.get('mtd_revpar', 0)
                cost_to_revpar_ratio = per_room.get('cost_to_revpar_ratio', 0)
                
                # Verify cost per room night calculation
                if total_room_nights > 0:
                    expected_cost_per_room = total_mtd_costs / total_room_nights
                    if abs(cost_per_room_night - expected_cost_per_room) > 0.01:
                        issues.append(f"cost_per_room_night calculation error: {cost_per_room_night} != {expected_cost_per_room}")
                
                # Verify cost to RevPAR ratio
                if mtd_revpar > 0:
                    expected_ratio = (cost_per_room_night / mtd_revpar) * 100
                    if abs(cost_to_revpar_ratio - expected_ratio) > 0.1:
                        issues.append(f"cost_to_revpar_ratio calculation error: {cost_to_revpar_ratio} != {expected_ratio}")
                
                # Verify profit calculations
                mtd_revenue = financial.get('mtd_revenue', 0)
                mtd_costs = financial.get('mtd_costs', 0)
                gross_profit = financial.get('gross_profit', 0)
                profit_margin = financial.get('profit_margin_percentage', 0)
                
                expected_gross_profit = mtd_revenue - mtd_costs
                if abs(gross_profit - expected_gross_profit) > 0.01:
                    issues.append(f"gross_profit calculation error: {gross_profit} != {expected_gross_profit}")
                
                if mtd_revenue > 0:
                    expected_profit_margin = (gross_profit / mtd_revenue) * 100
                    if abs(profit_margin - expected_profit_margin) > 0.1:
                        issues.append(f"profit_margin calculation error: {profit_margin} != {expected_profit_margin}")
                
                if issues:
                    success = False
                    details = f"Issues found: {'; '.join(issues)}"
                else:
                    details = f"All tests passed! Total costs: ${total_mtd_costs}, Categories with data: {[k for k, v in cost_categories.items() if v > 0]}"
                
                self.log_test_result("Comprehensive Cost Summary", success, details)
            else:
                details = f"HTTP {response.status_code}: {response.text}"
                self.log_test_result("Comprehensive Cost Summary", success, details)
                
        except Exception as e:
            self.log_test_result("Comprehensive Cost Summary", False, f"Error: {str(e)}")

    def run_comprehensive_test(self):
        """Run comprehensive cost summary test"""
        print("🧪 Starting Comprehensive Cost Summary Testing...")
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Setup comprehensive test data
        setup_result = self.setup_comprehensive_test_data()
        
        # Run comprehensive test
        self.test_comprehensive_cost_summary()
        
        # Print summary
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE COST SUMMARY TEST RESULTS")
        print("="*80)
        
        passed = sum(1 for result in self.test_results if "✅ PASS" in result["status"])
        failed = sum(1 for result in self.test_results if "❌ FAIL" in result["status"])
        
        for result in self.test_results:
            print(f"{result['status']}: {result['test']}")
            if result['details']:
                print(f"    Details: {result['details']}")
        
        print(f"\n📈 SUMMARY: {passed} passed, {failed} failed out of {len(self.test_results)} tests")
        
        if failed == 0:
            print("🎉 All Comprehensive Cost Summary tests PASSED!")
            return True
        else:
            print(f"⚠️ {failed} test(s) FAILED. Please review the issues above.")
            return False

if __name__ == "__main__":
    tester = ComprehensiveCostSummaryTester()
    success = tester.run_comprehensive_test()
    exit(0 if success else 1)