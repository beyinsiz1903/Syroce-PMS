#!/usr/bin/env python3
"""
Cost Summary Endpoint Testing for GM Dashboard
Testing GET /api/reports/cost-summary endpoint
"""

import requests
import json
import sys
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://guest-unified.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class CostSummaryTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []

    def authenticate(self):
        """Authenticate with the backend"""
        print("🔐 Authenticating...")
        try:
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
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False

    def log_test_result(self, test_name, success, details="", response_data=None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "response_data": response_data
        }
        self.test_results.append(result)
        print(f"  {status}: {test_name} - {details}")

    def setup_test_data(self):
        """Setup test data for cost summary testing"""
        print("\n🔧 Setting up test data...")
        
        # Create some purchase orders for testing
        test_pos = [
            {
                "supplier": "CleanCorp",
                "category": "cleaning",
                "items": [{"product_name": "All-purpose cleaner", "quantity": 10, "unit_price": 15.0}],
                "total_amount": 150.0,
                "delivery_location": "Housekeeping Storage",
                "status": "approved"
            },
            {
                "supplier": "FoodSupply Inc",
                "category": "food",
                "items": [{"product_name": "Fresh vegetables", "quantity": 50, "unit_price": 8.0}],
                "total_amount": 400.0,
                "delivery_location": "Kitchen",
                "status": "received"
            },
            {
                "supplier": "TechFix Ltd",
                "category": "maintenance",
                "items": [{"product_name": "HVAC filters", "quantity": 5, "unit_price": 25.0}],
                "total_amount": 125.0,
                "delivery_location": "Maintenance Room",
                "status": "completed"
            },
            {
                "supplier": "Office Supplies Co",
                "category": "office",
                "items": [{"product_name": "Printer paper", "quantity": 20, "unit_price": 12.0}],
                "total_amount": 240.0,
                "delivery_location": "Front Office",
                "status": "approved"
            }
        ]
        
        created_pos = []
        for po_data in test_pos:
            try:
                response = self.session.post(f"{BACKEND_URL}/marketplace/purchase-orders", json=po_data)
                if response.status_code in [200, 201]:
                    po = response.json()
                    created_pos.append(po.get('id'))
                    print(f"  ✅ Created PO: {po_data['supplier']} - ${po_data['total_amount']}")
                else:
                    print(f"  ⚠️ Failed to create PO for {po_data['supplier']}: {response.status_code}")
            except Exception as e:
                print(f"  ⚠️ Error creating PO for {po_data['supplier']}: {str(e)}")
        
        print(f"  📊 Created {len(created_pos)} purchase orders for testing")
        return created_pos

    def test_basic_cost_summary_retrieval(self):
        """Test Case 1: Basic Cost Summary Retrieval"""
        print("\n📊 Test Case 1: Basic Cost Summary Retrieval")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/cost-summary")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                
                # Verify response structure
                required_fields = [
                    'report_date', 'period', 'total_mtd_costs', 'cost_categories',
                    'top_3_categories', 'per_room_metrics', 'financial_metrics'
                ]
                
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    success = False
                    details = f"Missing required fields: {missing_fields}"
                else:
                    # Check cost_categories structure
                    cost_categories = data.get('cost_categories', {})
                    expected_categories = ['housekeeping', 'fnb', 'technical', 'general_expenses']
                    missing_categories = [cat for cat in expected_categories if cat not in cost_categories]
                    
                    if missing_categories:
                        success = False
                        details = f"Missing cost categories: {missing_categories}"
                    else:
                        # Check top_3_categories structure
                        top_3 = data.get('top_3_categories', [])
                        if len(top_3) > 3:
                            success = False
                            details = f"top_3_categories has {len(top_3)} items, should be max 3"
                        else:
                            # Verify top_3 structure
                            for i, cat in enumerate(top_3):
                                required_cat_fields = ['name', 'amount', 'percentage']
                                missing_cat_fields = [field for field in required_cat_fields if field not in cat]
                                if missing_cat_fields:
                                    success = False
                                    details = f"top_3_categories[{i}] missing fields: {missing_cat_fields}"
                                    break
                            
                            if success:
                                # Check per_room_metrics structure
                                per_room = data.get('per_room_metrics', {})
                                required_per_room = ['total_room_nights', 'cost_per_room_night', 'mtd_revpar', 'cost_to_revpar_ratio']
                                missing_per_room = [field for field in required_per_room if field not in per_room]
                                
                                if missing_per_room:
                                    success = False
                                    details = f"per_room_metrics missing fields: {missing_per_room}"
                                else:
                                    # Check financial_metrics structure
                                    financial = data.get('financial_metrics', {})
                                    required_financial = ['mtd_revenue', 'mtd_costs', 'gross_profit', 'profit_margin_percentage', 'cost_to_revenue_ratio']
                                    missing_financial = [field for field in required_financial if field not in financial]
                                    
                                    if missing_financial:
                                        success = False
                                        details = f"financial_metrics missing fields: {missing_financial}"
                                    else:
                                        details = f"All required fields present. Total MTD costs: ${data.get('total_mtd_costs', 0)}"
                
                self.log_test_result("Basic Cost Summary Retrieval", success, details, data)
            else:
                details = f"HTTP {response.status_code}: {response.text}"
                self.log_test_result("Basic Cost Summary Retrieval", success, details)
                
        except Exception as e:
            self.log_test_result("Basic Cost Summary Retrieval", False, f"Error: {str(e)}")

    def test_data_accuracy(self):
        """Test Case 2: Data Accuracy"""
        print("\n🔍 Test Case 2: Data Accuracy")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/cost-summary")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                issues = []
                
                # Check numerical rounding (amounts to 2 decimal places)
                total_costs = data.get('total_mtd_costs', 0)
                if not isinstance(total_costs, (int, float)) or round(total_costs, 2) != total_costs:
                    issues.append(f"total_mtd_costs not properly rounded: {total_costs}")
                
                # Check cost categories rounding
                cost_categories = data.get('cost_categories', {})
                for cat_name, amount in cost_categories.items():
                    if not isinstance(amount, (int, float)) or round(amount, 2) != amount:
                        issues.append(f"{cat_name} not properly rounded: {amount}")
                
                # Check top_3_categories sorting and rounding
                top_3 = data.get('top_3_categories', [])
                for i, cat in enumerate(top_3):
                    amount = cat.get('amount', 0)
                    percentage = cat.get('percentage', 0)
                    
                    # Check amount rounding (2 decimal places)
                    if not isinstance(amount, (int, float)) or round(amount, 2) != amount:
                        issues.append(f"top_3_categories[{i}] amount not properly rounded: {amount}")
                    
                    # Check percentage rounding (1 decimal place)
                    if not isinstance(percentage, (int, float)) or round(percentage, 1) != percentage:
                        issues.append(f"top_3_categories[{i}] percentage not properly rounded: {percentage}")
                    
                    # Check sorting (descending by amount)
                    if i > 0:
                        prev_amount = top_3[i-1].get('amount', 0)
                        if amount > prev_amount:
                            issues.append(f"top_3_categories not sorted correctly: {amount} > {prev_amount}")
                
                # Check per-room metrics rounding
                per_room = data.get('per_room_metrics', {})
                for metric, value in per_room.items():
                    if metric in ['cost_per_room_night', 'mtd_revpar']:
                        if not isinstance(value, (int, float)) or round(value, 2) != value:
                            issues.append(f"{metric} not properly rounded: {value}")
                    elif metric == 'cost_to_revpar_ratio':
                        if not isinstance(value, (int, float)) or round(value, 1) != value:
                            issues.append(f"{metric} not properly rounded: {value}")
                
                # Check financial metrics rounding
                financial = data.get('financial_metrics', {})
                for metric, value in financial.items():
                    if metric in ['mtd_revenue', 'mtd_costs', 'gross_profit']:
                        if not isinstance(value, (int, float)) or round(value, 2) != value:
                            issues.append(f"{metric} not properly rounded: {value}")
                    elif metric in ['profit_margin_percentage', 'cost_to_revenue_ratio']:
                        if not isinstance(value, (int, float)) or round(value, 1) != value:
                            issues.append(f"{metric} not properly rounded: {value}")
                
                if issues:
                    success = False
                    details = f"Data accuracy issues: {'; '.join(issues)}"
                else:
                    details = "All numerical values properly rounded and sorted"
                
                self.log_test_result("Data Accuracy", success, details)
            else:
                details = f"HTTP {response.status_code}: {response.text}"
                self.log_test_result("Data Accuracy", success, details)
                
        except Exception as e:
            self.log_test_result("Data Accuracy", False, f"Error: {str(e)}")

    def test_cost_category_mapping(self):
        """Test Case 3: Cost Category Mapping"""
        print("\n🗂️ Test Case 3: Cost Category Mapping")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/cost-summary")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                
                # Expected mapping from the endpoint code:
                expected_mapping = {
                    'cleaning': 'Housekeeping',
                    'linens': 'Housekeeping', 
                    'amenities': 'Housekeeping',
                    'food': 'F&B',
                    'beverage': 'F&B',
                    'kitchen': 'F&B',
                    'maintenance': 'Technical',
                    'electrical': 'Technical',
                    'plumbing': 'Technical',
                    'hvac': 'Technical',
                    'furniture': 'General Expenses',
                    'office': 'General Expenses',
                    'it': 'General Expenses',
                    'other': 'General Expenses'
                }
                
                cost_categories = data.get('cost_categories', {})
                
                # Verify all expected categories are present
                expected_categories = ['housekeeping', 'fnb', 'technical', 'general_expenses']
                missing_categories = [cat for cat in expected_categories if cat not in cost_categories]
                
                if missing_categories:
                    success = False
                    details = f"Missing cost categories: {missing_categories}"
                else:
                    # Check if categories have reasonable values (non-negative)
                    invalid_values = []
                    for cat, amount in cost_categories.items():
                        if not isinstance(amount, (int, float)) or amount < 0:
                            invalid_values.append(f"{cat}: {amount}")
                    
                    if invalid_values:
                        success = False
                        details = f"Invalid category values: {invalid_values}"
                    else:
                        # Verify top_3_categories names match the cost categories
                        top_3 = data.get('top_3_categories', [])
                        valid_category_names = ['Housekeeping', 'F&B', 'Technical', 'General Expenses']
                        
                        invalid_top_categories = []
                        for cat in top_3:
                            cat_name = cat.get('name', '')
                            if cat_name not in valid_category_names:
                                invalid_top_categories.append(cat_name)
                        
                        if invalid_top_categories:
                            success = False
                            details = f"Invalid top category names: {invalid_top_categories}"
                        else:
                            details = f"Cost category mapping verified. Categories: {list(cost_categories.keys())}"
                
                self.log_test_result("Cost Category Mapping", success, details)
            else:
                details = f"HTTP {response.status_code}: {response.text}"
                self.log_test_result("Cost Category Mapping", success, details)
                
        except Exception as e:
            self.log_test_result("Cost Category Mapping", False, f"Error: {str(e)}")

    def test_per_room_calculations(self):
        """Test Case 4: Per-Room Calculations"""
        print("\n🏨 Test Case 4: Per-Room Calculations")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/cost-summary")
            success = response.status_code == 200
            
            if success:
                data = response.json()
                issues = []
                
                per_room = data.get('per_room_metrics', {})
                financial = data.get('financial_metrics', {})
                
                total_room_nights = per_room.get('total_room_nights', 0)
                cost_per_room_night = per_room.get('cost_per_room_night', 0)
                mtd_revpar = per_room.get('mtd_revpar', 0)
                cost_to_revpar_ratio = per_room.get('cost_to_revpar_ratio', 0)
                
                total_costs = data.get('total_mtd_costs', 0)
                mtd_revenue = financial.get('mtd_revenue', 0)
                gross_profit = financial.get('gross_profit', 0)
                profit_margin = financial.get('profit_margin_percentage', 0)
                
                # Verify cost_per_room_night calculation
                if total_room_nights > 0:
                    expected_cost_per_room = total_costs / total_room_nights
                    if abs(cost_per_room_night - expected_cost_per_room) > 0.01:
                        issues.append(f"cost_per_room_night calculation error: {cost_per_room_night} != {expected_cost_per_room}")
                else:
                    if cost_per_room_night != 0:
                        issues.append(f"cost_per_room_night should be 0 when no room nights: {cost_per_room_night}")
                
                # Verify cost_to_revpar_ratio calculation
                if mtd_revpar > 0:
                    expected_ratio = (cost_per_room_night / mtd_revpar) * 100
                    if abs(cost_to_revpar_ratio - expected_ratio) > 0.1:
                        issues.append(f"cost_to_revpar_ratio calculation error: {cost_to_revpar_ratio} != {expected_ratio}")
                else:
                    if cost_to_revpar_ratio != 0:
                        issues.append(f"cost_to_revpar_ratio should be 0 when RevPAR is 0: {cost_to_revpar_ratio}")
                
                # Verify profit margin calculation
                if mtd_revenue > 0:
                    expected_profit_margin = (gross_profit / mtd_revenue) * 100
                    if abs(profit_margin - expected_profit_margin) > 0.1:
                        issues.append(f"profit_margin calculation error: {profit_margin} != {expected_profit_margin}")
                else:
                    if profit_margin != 0:
                        issues.append(f"profit_margin should be 0 when revenue is 0: {profit_margin}")
                
                # Verify gross profit calculation
                expected_gross_profit = mtd_revenue - total_costs
                if abs(gross_profit - expected_gross_profit) > 0.01:
                    issues.append(f"gross_profit calculation error: {gross_profit} != {expected_gross_profit}")
                
                if issues:
                    success = False
                    details = f"Calculation errors: {'; '.join(issues)}"
                else:
                    details = f"All calculations verified. Room nights: {total_room_nights}, Cost/room: ${cost_per_room_night}"
                
                self.log_test_result("Per-Room Calculations", success, details)
            else:
                details = f"HTTP {response.status_code}: {response.text}"
                self.log_test_result("Per-Room Calculations", success, details)
                
        except Exception as e:
            self.log_test_result("Per-Room Calculations", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all cost summary tests"""
        print("🧪 Starting Cost Summary Endpoint Testing...")
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Setup test data
        self.setup_test_data()
        
        # Run all test cases
        self.test_basic_cost_summary_retrieval()
        self.test_data_accuracy()
        self.test_cost_category_mapping()
        self.test_per_room_calculations()
        
        # Print summary
        print("\n" + "="*60)
        print("📊 COST SUMMARY ENDPOINT TEST RESULTS")
        print("="*60)
        
        passed = sum(1 for result in self.test_results if "✅ PASS" in result["status"])
        failed = sum(1 for result in self.test_results if "❌ FAIL" in result["status"])
        
        for result in self.test_results:
            print(f"{result['status']}: {result['test']}")
            if result['details']:
                print(f"    Details: {result['details']}")
        
        print(f"\n📈 SUMMARY: {passed} passed, {failed} failed out of {len(self.test_results)} tests")
        
        if failed == 0:
            print("🎉 All Cost Summary endpoint tests PASSED!")
            return True
        else:
            print(f"⚠️ {failed} test(s) FAILED. Please review the issues above.")
            return False

if __name__ == "__main__":
    tester = CostSummaryTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)