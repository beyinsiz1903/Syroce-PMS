#!/usr/bin/env python3
"""
Backend Testing for Dashboard Enhancement and F&B Module Endpoints
Testing Agent - Comprehensive API Testing
"""

import requests
import json
import sys
from datetime import datetime, timedelta
import time

class DashboardFnBTester:
    def __init__(self):
        # Get backend URL from frontend env
        try:
            with open('/app/frontend/.env', 'r') as f:
                for line in f:
                    if line.startswith('REACT_APP_BACKEND_URL='):
                        self.base_url = line.split('=')[1].strip() + '/api'
                        break
        except:
            self.base_url = "https://pms-i18next-demo.preview.emergentagent.com/api"
        
        self.token = None
        self.tenant_id = None
        self.test_results = []
        
        print(f"🔧 Backend URL: {self.base_url}")
    
    def log_result(self, test_name, success, details="", response_data=None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'response_data': response_data
        }
        self.test_results.append(result)
        print(f"{status} {test_name}: {details}")
        if response_data and not success:
            print(f"   Response: {json.dumps(response_data, indent=2)}")
    
    def register_and_login(self):
        """Register tenant and login"""
        try:
            # Register tenant
            register_data = {
                "property_name": "Dashboard Test Hotel",
                "email": "dashboard@testhotel.com",
                "password": "testpass123",
                "name": "Dashboard Tester",
                "phone": "+1234567890",
                "address": "123 Test Street",
                "location": "Test City"
            }
            
            response = requests.post(f"{self.base_url}/auth/register", json=register_data)
            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.tenant_id = data['user']['tenant_id']
                self.log_result("Authentication", True, "Successfully registered and logged in")
                return True
            else:
                # Try login if already registered
                login_data = {
                    "email": "dashboard@testhotel.com",
                    "password": "testpass123"
                }
                response = requests.post(f"{self.base_url}/auth/login", json=login_data)
                if response.status_code == 200:
                    data = response.json()
                    self.token = data['access_token']
                    self.tenant_id = data['user']['tenant_id']
                    self.log_result("Authentication", True, "Successfully logged in")
                    return True
                else:
                    self.log_result("Authentication", False, f"Login failed: {response.status_code}", response.json())
                    return False
        except Exception as e:
            self.log_result("Authentication", False, f"Auth error: {str(e)}")
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def test_dashboard_revenue_expense_chart(self):
        """Test GET /dashboard/revenue-expense-chart"""
        print("\n🔍 Testing Dashboard Revenue-Expense Chart...")
        
        # Test with different periods
        periods = ["30days", "90days", "12months"]
        
        for period in periods:
            try:
                response = requests.get(
                    f"{self.base_url}/dashboard/revenue-expense-chart?period={period}",
                    headers=self.get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Validate response structure
                    required_fields = ['period', 'interval', 'chart_data', 'summary']
                    summary_fields = ['total_revenue', 'total_expense', 'total_profit', 'avg_profit_margin']
                    
                    if all(field in data for field in required_fields):
                        if all(field in data['summary'] for field in summary_fields):
                            # Validate chart_data structure
                            if data['chart_data'] and isinstance(data['chart_data'], list):
                                chart_item = data['chart_data'][0]
                                chart_fields = ['period', 'revenue', 'expense', 'profit', 'profit_margin']
                                if all(field in chart_item for field in chart_fields):
                                    self.log_result(
                                        f"Revenue-Expense Chart ({period})", 
                                        True, 
                                        f"Returns proper structure with {len(data['chart_data'])} data points, interval: {data['interval']}"
                                    )
                                else:
                                    self.log_result(f"Revenue-Expense Chart ({period})", False, "Chart data missing required fields", data)
                            else:
                                self.log_result(f"Revenue-Expense Chart ({period})", True, "Empty chart data but proper structure")
                        else:
                            self.log_result(f"Revenue-Expense Chart ({period})", False, "Summary missing required fields", data)
                    else:
                        self.log_result(f"Revenue-Expense Chart ({period})", False, "Response missing required fields", data)
                else:
                    self.log_result(f"Revenue-Expense Chart ({period})", False, f"HTTP {response.status_code}", response.json())
                    
            except Exception as e:
                self.log_result(f"Revenue-Expense Chart ({period})", False, f"Exception: {str(e)}")
    
    def test_dashboard_budget_vs_actual(self):
        """Test GET /dashboard/budget-vs-actual"""
        print("\n🔍 Testing Dashboard Budget vs Actual...")
        
        # Test with default month
        try:
            response = requests.get(
                f"{self.base_url}/dashboard/budget-vs-actual",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['month', 'categories']
                if all(field in data for field in required_fields):
                    if data['categories'] and isinstance(data['categories'], list):
                        category = data['categories'][0]
                        category_fields = ['name', 'budget', 'actual', 'variance', 'status']
                        if all(field in category for field in category_fields):
                            expected_categories = ['Revenue', 'Expense', 'Occupancy (%)', 'ADR']
                            category_names = [cat['name'] for cat in data['categories']]
                            if all(name in category_names for name in expected_categories):
                                self.log_result(
                                    "Budget vs Actual (default)", 
                                    True, 
                                    f"Returns {len(data['categories'])} categories for month {data['month']}"
                                )
                            else:
                                self.log_result("Budget vs Actual (default)", False, "Missing expected categories", data)
                        else:
                            self.log_result("Budget vs Actual (default)", False, "Category missing required fields", data)
                    else:
                        self.log_result("Budget vs Actual (default)", False, "Categories not a list or empty", data)
                else:
                    self.log_result("Budget vs Actual (default)", False, "Response missing required fields", data)
            else:
                self.log_result("Budget vs Actual (default)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("Budget vs Actual (default)", False, f"Exception: {str(e)}")
        
        # Test with specific month
        try:
            test_month = "2025-01"
            response = requests.get(
                f"{self.base_url}/dashboard/budget-vs-actual?month={test_month}",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('month') == test_month:
                    self.log_result("Budget vs Actual (specific month)", True, f"Returns data for {test_month}")
                else:
                    self.log_result("Budget vs Actual (specific month)", False, "Month parameter not working", data)
            else:
                self.log_result("Budget vs Actual (specific month)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("Budget vs Actual (specific month)", False, f"Exception: {str(e)}")
    
    def test_dashboard_monthly_profitability(self):
        """Test GET /dashboard/monthly-profitability"""
        print("\n🔍 Testing Dashboard Monthly Profitability...")
        
        # Test with default months (6)
        try:
            response = requests.get(
                f"{self.base_url}/dashboard/monthly-profitability",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['months_data', 'current_month', 'averages']
                if all(field in data for field in required_fields):
                    if data['months_data'] and isinstance(data['months_data'], list):
                        month_data = data['months_data'][0]
                        month_fields = ['month', 'month_name', 'revenue', 'expense', 'profit', 'profit_margin']
                        if all(field in month_data for field in month_fields):
                            avg_fields = ['avg_revenue', 'avg_expense', 'avg_profit', 'avg_profit_margin']
                            if all(field in data['averages'] for field in avg_fields):
                                self.log_result(
                                    "Monthly Profitability (default)", 
                                    True, 
                                    f"Returns {len(data['months_data'])} months with averages"
                                )
                            else:
                                self.log_result("Monthly Profitability (default)", False, "Averages missing required fields", data)
                        else:
                            self.log_result("Monthly Profitability (default)", False, "Month data missing required fields", data)
                    else:
                        self.log_result("Monthly Profitability (default)", True, "Empty months data but proper structure")
                else:
                    self.log_result("Monthly Profitability (default)", False, "Response missing required fields", data)
            else:
                self.log_result("Monthly Profitability (default)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("Monthly Profitability (default)", False, f"Exception: {str(e)}")
        
        # Test with custom months parameter
        try:
            response = requests.get(
                f"{self.base_url}/dashboard/monthly-profitability?months=12",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if len(data.get('months_data', [])) <= 12:  # Should be 12 or less
                    self.log_result("Monthly Profitability (12 months)", True, f"Returns {len(data.get('months_data', []))} months")
                else:
                    self.log_result("Monthly Profitability (12 months)", False, "Too many months returned", data)
            else:
                self.log_result("Monthly Profitability (12 months)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("Monthly Profitability (12 months)", False, f"Exception: {str(e)}")
    
    def test_dashboard_trend_kpis(self):
        """Test GET /dashboard/trend-kpis"""
        print("\n🔍 Testing Dashboard Trend KPIs...")
        
        # Test with different periods
        periods = ["7days", "30days", "90days"]
        
        for period in periods:
            try:
                response = requests.get(
                    f"{self.base_url}/dashboard/trend-kpis?period={period}",
                    headers=self.get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Validate response structure
                    required_fields = ['period', 'kpis']
                    if all(field in data for field in required_fields):
                        if data['kpis'] and isinstance(data['kpis'], list):
                            kpi = data['kpis'][0]
                            kpi_fields = ['name', 'current', 'previous', 'trend', 'unit', 'icon']
                            if all(field in kpi for field in kpi_fields):
                                expected_kpis = ['Revenue', 'Bookings', 'Occupancy', 'ADR', 'RevPAR', 'Guest Rating']
                                kpi_names = [k['name'] for k in data['kpis']]
                                if all(name in kpi_names for name in expected_kpis):
                                    self.log_result(
                                        f"Trend KPIs ({period})", 
                                        True, 
                                        f"Returns {len(data['kpis'])} KPIs with trend calculations"
                                    )
                                else:
                                    self.log_result(f"Trend KPIs ({period})", False, "Missing expected KPIs", data)
                            else:
                                self.log_result(f"Trend KPIs ({period})", False, "KPI missing required fields", data)
                        else:
                            self.log_result(f"Trend KPIs ({period})", True, "Empty KPIs but proper structure")
                    else:
                        self.log_result(f"Trend KPIs ({period})", False, "Response missing required fields", data)
                else:
                    self.log_result(f"Trend KPIs ({period})", False, f"HTTP {response.status_code}", response.json())
                    
            except Exception as e:
                self.log_result(f"Trend KPIs ({period})", False, f"Exception: {str(e)}")
    
    def test_fnb_dashboard(self):
        """Test GET /fnb/dashboard"""
        print("\n🔍 Testing F&B Dashboard...")
        
        # Test with default date (today)
        try:
            response = requests.get(
                f"{self.base_url}/fnb/dashboard",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['date', 'summary']
                if all(field in data for field in required_fields):
                    summary_fields = ['total_revenue', 'food_revenue', 'beverage_revenue', 'orders_count', 'avg_order_value', 'tables_used', 'revenue_change']
                    if all(field in data['summary'] for field in summary_fields):
                        self.log_result(
                            "F&B Dashboard (default)", 
                            True, 
                            f"Returns summary for {data['date']} with revenue: {data['summary']['total_revenue']}"
                        )
                    else:
                        self.log_result("F&B Dashboard (default)", False, "Summary missing required fields", data)
                else:
                    self.log_result("F&B Dashboard (default)", False, "Response missing required fields", data)
            else:
                self.log_result("F&B Dashboard (default)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("F&B Dashboard (default)", False, f"Exception: {str(e)}")
        
        # Test with specific date
        try:
            test_date = "2025-01-15"
            response = requests.get(
                f"{self.base_url}/fnb/dashboard?date={test_date}",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('date') == test_date:
                    self.log_result("F&B Dashboard (specific date)", True, f"Returns data for {test_date}")
                else:
                    self.log_result("F&B Dashboard (specific date)", False, "Date parameter not working", data)
            else:
                self.log_result("F&B Dashboard (specific date)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("F&B Dashboard (specific date)", False, f"Exception: {str(e)}")
    
    def test_fnb_sales_report(self):
        """Test GET /fnb/sales-report"""
        print("\n🔍 Testing F&B Sales Report...")
        
        # Test with default date range (last 30 days)
        try:
            response = requests.get(
                f"{self.base_url}/fnb/sales-report",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['period', 'summary', 'daily_sales']
                if all(field in data for field in required_fields):
                    period_fields = ['start_date', 'end_date']
                    summary_fields = ['total_sales', 'food_sales', 'beverage_sales', 'food_percentage', 'beverage_percentage']
                    
                    if (all(field in data['period'] for field in period_fields) and
                        all(field in data['summary'] for field in summary_fields)):
                        
                        # Check daily_sales structure if not empty
                        if data['daily_sales']:
                            daily_fields = ['date', 'food', 'beverage', 'total']
                            if all(field in data['daily_sales'][0] for field in daily_fields):
                                self.log_result(
                                    "F&B Sales Report (default)", 
                                    True, 
                                    f"Returns {len(data['daily_sales'])} days, total sales: {data['summary']['total_sales']}"
                                )
                            else:
                                self.log_result("F&B Sales Report (default)", False, "Daily sales missing required fields", data)
                        else:
                            self.log_result("F&B Sales Report (default)", True, "Empty daily sales but proper structure")
                    else:
                        self.log_result("F&B Sales Report (default)", False, "Period or summary missing required fields", data)
                else:
                    self.log_result("F&B Sales Report (default)", False, "Response missing required fields", data)
            else:
                self.log_result("F&B Sales Report (default)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("F&B Sales Report (default)", False, f"Exception: {str(e)}")
        
        # Test with custom date range
        try:
            start_date = "2025-01-01"
            end_date = "2025-01-15"
            response = requests.get(
                f"{self.base_url}/fnb/sales-report?start_date={start_date}&end_date={end_date}",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('period', {}).get('start_date') == start_date and 
                    data.get('period', {}).get('end_date') == end_date):
                    self.log_result("F&B Sales Report (custom range)", True, f"Returns data for {start_date} to {end_date}")
                else:
                    self.log_result("F&B Sales Report (custom range)", False, "Date range parameters not working", data)
            else:
                self.log_result("F&B Sales Report (custom range)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("F&B Sales Report (custom range)", False, f"Exception: {str(e)}")
    
    def test_fnb_menu_performance(self):
        """Test GET /fnb/menu-performance"""
        print("\n🔍 Testing F&B Menu Performance...")
        
        # Test with default date range
        try:
            response = requests.get(
                f"{self.base_url}/fnb/menu-performance",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['period', 'total_items', 'total_revenue', 'top_performers', 'bottom_performers']
                if all(field in data for field in required_fields):
                    period_fields = ['start_date', 'end_date']
                    if all(field in data['period'] for field in period_fields):
                        # Check top_performers structure if not empty
                        if data['top_performers']:
                            performer_fields = ['item_name', 'quantity_sold', 'revenue', 'orders_count', 'avg_price']
                            if all(field in data['top_performers'][0] for field in performer_fields):
                                self.log_result(
                                    "F&B Menu Performance (default)", 
                                    True, 
                                    f"Returns {data['total_items']} items, {len(data['top_performers'])} top performers"
                                )
                            else:
                                self.log_result("F&B Menu Performance (default)", False, "Top performers missing required fields", data)
                        else:
                            self.log_result("F&B Menu Performance (default)", True, "Empty menu performance but proper structure")
                    else:
                        self.log_result("F&B Menu Performance (default)", False, "Period missing required fields", data)
                else:
                    self.log_result("F&B Menu Performance (default)", False, "Response missing required fields", data)
            else:
                self.log_result("F&B Menu Performance (default)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("F&B Menu Performance (default)", False, f"Exception: {str(e)}")
        
        # Test with custom date range
        try:
            start_date = "2025-01-01"
            end_date = "2025-01-15"
            response = requests.get(
                f"{self.base_url}/fnb/menu-performance?start_date={start_date}&end_date={end_date}",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                data = response.json()
                if (data.get('period', {}).get('start_date') == start_date and 
                    data.get('period', {}).get('end_date') == end_date):
                    self.log_result("F&B Menu Performance (custom range)", True, f"Returns data for {start_date} to {end_date}")
                else:
                    self.log_result("F&B Menu Performance (custom range)", False, "Date range parameters not working", data)
            else:
                self.log_result("F&B Menu Performance (custom range)", False, f"HTTP {response.status_code}", response.json())
                
        except Exception as e:
            self.log_result("F&B Menu Performance (custom range)", False, f"Exception: {str(e)}")
    
    def test_fnb_revenue_chart(self):
        """Test GET /fnb/revenue-chart"""
        print("\n🔍 Testing F&B Revenue Chart...")
        
        # Test with different periods
        periods = ["7days", "30days", "90days"]
        
        for period in periods:
            try:
                response = requests.get(
                    f"{self.base_url}/fnb/revenue-chart?period={period}",
                    headers=self.get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Validate response structure
                    required_fields = ['period', 'chart_data', 'summary']
                    if all(field in data for field in required_fields):
                        summary_fields = ['total_food', 'total_beverage', 'total_revenue']
                        if all(field in data['summary'] for field in summary_fields):
                            # Check chart_data structure if not empty
                            if data['chart_data']:
                                chart_fields = ['date', 'food', 'beverage', 'total']
                                if all(field in data['chart_data'][0] for field in chart_fields):
                                    self.log_result(
                                        f"F&B Revenue Chart ({period})", 
                                        True, 
                                        f"Returns {len(data['chart_data'])} data points, total revenue: {data['summary']['total_revenue']}"
                                    )
                                else:
                                    self.log_result(f"F&B Revenue Chart ({period})", False, "Chart data missing required fields", data)
                            else:
                                self.log_result(f"F&B Revenue Chart ({period})", True, "Empty chart data but proper structure")
                        else:
                            self.log_result(f"F&B Revenue Chart ({period})", False, "Summary missing required fields", data)
                    else:
                        self.log_result(f"F&B Revenue Chart ({period})", False, "Response missing required fields", data)
                else:
                    self.log_result(f"F&B Revenue Chart ({period})", False, f"HTTP {response.status_code}", response.json())
                    
            except Exception as e:
                self.log_result(f"F&B Revenue Chart ({period})", False, f"Exception: {str(e)}")
    
    def test_edge_cases(self):
        """Test edge cases and error handling"""
        print("\n🔍 Testing Edge Cases...")
        
        # Test invalid period parameter
        try:
            response = requests.get(
                f"{self.base_url}/dashboard/revenue-expense-chart?period=invalid",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                # Should handle gracefully, likely default to 30days
                self.log_result("Invalid period parameter", True, "Handles invalid period gracefully")
            else:
                self.log_result("Invalid period parameter", True, f"Returns error {response.status_code} as expected")
                
        except Exception as e:
            self.log_result("Invalid period parameter", False, f"Exception: {str(e)}")
        
        # Test invalid date format
        try:
            response = requests.get(
                f"{self.base_url}/dashboard/budget-vs-actual?month=invalid-date",
                headers=self.get_headers()
            )
            
            if response.status_code in [400, 422]:
                self.log_result("Invalid date format", True, f"Returns error {response.status_code} as expected")
            else:
                self.log_result("Invalid date format", True, "Handles invalid date gracefully")
                
        except Exception as e:
            self.log_result("Invalid date format", False, f"Exception: {str(e)}")
        
        # Test unauthorized access
        try:
            response = requests.get(f"{self.base_url}/dashboard/revenue-expense-chart")
            
            if response.status_code in [401, 403]:
                self.log_result("Unauthorized access", True, f"Returns {response.status_code} as expected")
            else:
                self.log_result("Unauthorized access", False, f"Should require authentication, got {response.status_code}")
                
        except Exception as e:
            self.log_result("Unauthorized access", False, f"Exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting Dashboard Enhancement and F&B Module Testing...")
        print("=" * 80)
        
        # Authentication
        if not self.register_and_login():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Dashboard Enhancement Tests
        print("\n📊 DASHBOARD ENHANCEMENT TESTS")
        print("-" * 50)
        self.test_dashboard_revenue_expense_chart()
        self.test_dashboard_budget_vs_actual()
        self.test_dashboard_monthly_profitability()
        self.test_dashboard_trend_kpis()
        
        # F&B Module Tests
        print("\n🍽️ F&B MODULE TESTS")
        print("-" * 50)
        self.test_fnb_dashboard()
        self.test_fnb_sales_report()
        self.test_fnb_menu_performance()
        self.test_fnb_revenue_chart()
        
        # Edge Cases
        print("\n⚠️ EDGE CASE TESTS")
        print("-" * 50)
        self.test_edge_cases()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("📋 TEST SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result['success']:
                    print(f"   • {result['test']}: {result['details']}")
        
        print("\n🎯 ENDPOINT TESTING COMPLETED")
        
        # Dashboard Enhancement Summary
        dashboard_tests = [r for r in self.test_results if 'Revenue-Expense Chart' in r['test'] or 'Budget vs Actual' in r['test'] or 'Monthly Profitability' in r['test'] or 'Trend KPIs' in r['test']]
        dashboard_passed = sum(1 for r in dashboard_tests if r['success'])
        
        # F&B Module Summary  
        fnb_tests = [r for r in self.test_results if 'F&B' in r['test']]
        fnb_passed = sum(1 for r in fnb_tests if r['success'])
        
        print(f"\n📊 Dashboard Enhancement: {dashboard_passed}/{len(dashboard_tests)} tests passed")
        print(f"🍽️ F&B Module: {fnb_passed}/{len(fnb_tests)} tests passed")

if __name__ == "__main__":
    tester = DashboardFnBTester()
    tester.run_all_tests()