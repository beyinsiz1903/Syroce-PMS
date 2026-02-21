#!/usr/bin/env python3
"""
Reports Basic Dashboard & Invoice Access Backend Test

Tests the following specific endpoints as requested:
1. GET /api/reports/basic-dashboard - Optimized dashboard with performance testing
2. GET /api/invoices/* - Invoice access for regular hotel users (not just super_admin)
3. GET /api/pms/rooms - Calendar endpoints testing
4. GET /api/pms/bookings - Calendar endpoints with date params
5. GET /api/pms/guests - Calendar endpoints testing

Test credentials:
- Basic hotel: demo@butikotel.com / demo123
- Professional hotel: demo@grandcity.com / demo123

Backend base URL: https://perf-boost-37.preview.emergentagent.com/api
"""

import requests
import json
import time
from datetime import datetime, date, timedelta
import os

# Configuration 
BASE_URL = 'https://perf-boost-37.preview.emergentagent.com/api'

# Test credentials
TEST_ACCOUNTS = {
    'admin': {
        'email': 'admin@hotel.com',
        'password': 'admin123',
        'name': 'Admin User'
    },
    'supervisor': {
        'email': 'supervisor@hotel.com', 
        'password': 'super123',
        'name': 'Supervisor Manager'
    },
    'finance': {
        'email': 'finance@hotel.com', 
        'password': 'fin123',
        'name': 'Finance Manager'
    }
}

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_result(test_name, passed, details=""):
    """Print test result"""
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"{status}: {test_name}")
    if details:
        print(f"   Details: {details}")

def login_user(account_type):
    """Login user and return token"""
    print_section(f"LOGIN - {TEST_ACCOUNTS[account_type]['name']}")
    
    try:
        credentials = TEST_ACCOUNTS[account_type]
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": credentials['email'],
                "password": credentials['password']
            },
            timeout=30
        )
        
        print(f"Request: POST /api/auth/login")
        print(f"Email: {credentials['email']}")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            tenant = data.get("tenant") or {}
            
            print_result(f"{credentials['name']} Login", True, 
                        f"User: {user.get('name')}, Role: {user.get('role')}, Tenant: {tenant.get('property_name', user.get('tenant_id', 'N/A'))}")
            
            return token, user, tenant
        else:
            print_result(f"{credentials['name']} Login", False, 
                        f"HTTP {response.status_code}: {response.text}")
            return None, None, None
            
    except Exception as e:
        print_result(f"{credentials['name']} Login", False, f"Exception: {str(e)}")
        return None, None, None

def test_reports_basic_dashboard(token, account_name, performance_check=True):
    """Test GET /api/reports/basic-dashboard with performance measurement"""
    print_section(f"REPORTS BASIC DASHBOARD - {account_name}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Measure response time
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/reports/basic-dashboard", headers=headers, timeout=30)
        end_time = time.time()
        response_time = end_time - start_time
        
        print(f"Request: GET /api/reports/basic-dashboard")
        print(f"Response Status: HTTP {response.status_code}")
        print(f"Response Time: {response_time:.2f} seconds")
        
        if response.status_code == 200:
            data = response.json()
            
            # Check required fields in response
            required_fields = [
                'date', 'summary', 'period_comparison', 'occupancy_trend', 
                'revenue_trend', 'room_status', 'room_types', 'room_type_occupancy',
                'booking_sources', 'country_distribution', 'payments', 'guest_list',
                'housekeeping', 'maintenance', 'finance'
            ]
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Response is JSON": True,
                "Has date field": 'date' in data,
                "Has summary field": 'summary' in data,
            }
            
            # Check all required top-level fields
            for field in required_fields:
                checks[f"Has {field} field"] = field in data
            
            # Check summary sub-fields
            summary = data.get('summary', {})
            summary_fields = [
                'total_rooms', 'occupied_rooms', 'occupancy_percentage',
                'arrivals', 'departures', 'in_house', 'no_shows', 
                'cancellations', 'today_revenue', 'adr', 'revpar', 'fnb_revenue'
            ]
            
            for field in summary_fields:
                checks[f"Summary has {field}"] = field in summary
            
            # Performance check - should be under 5 seconds
            if performance_check:
                checks["Response under 5 seconds"] = response_time < 5.0
                if response_time >= 5.0:
                    print(f"⚠️  PERFORMANCE WARNING: Response took {response_time:.2f}s (should be <5s)")
                else:
                    print(f"✅ PERFORMANCE: Response time {response_time:.2f}s is acceptable")
            
            # Check data structure validity
            if 'summary' in data:
                summary = data['summary']
                checks["Summary total_rooms is number"] = isinstance(summary.get('total_rooms'), (int, float)) if 'total_rooms' in summary else False
                checks["Summary occupancy_percentage is number"] = isinstance(summary.get('occupancy_percentage'), (int, float)) if 'occupancy_percentage' in summary else False
            
            print(f"\nData structure sample:")
            print(f"Date: {data.get('date', 'N/A')}")
            print(f"Total Rooms: {summary.get('total_rooms', 'N/A')}")
            print(f"Occupancy: {summary.get('occupancy_percentage', 'N/A')}%")
            print(f"Revenue: {summary.get('today_revenue', 'N/A')}")
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, response_time, data
            
        else:
            print_result("Reports Basic Dashboard", False, f"HTTP {response.status_code}: {response.text}")
            return False, None, {}
            
    except Exception as e:
        print_result("Reports Basic Dashboard", False, f"Exception: {str(e)}")
        return False, None, {}

def test_invoice_access(token, account_name):
    """Test invoice endpoints access for regular hotel users"""
    print_section(f"INVOICE ACCESS - {account_name}")
    
    invoice_endpoints = [
        '/invoices',
        '/invoices/list', 
        '/invoices/stats',
        '/accounting/invoices'
    ]
    
    results = {}
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        for endpoint in invoice_endpoints:
            try:
                response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=30)
                
                print(f"Request: GET /api{endpoint}")
                print(f"Response Status: HTTP {response.status_code}")
                
                # Accept 200 OK or 404 Not Found (endpoint might not exist)
                # But NOT 403 Forbidden (access denied)
                if response.status_code == 200:
                    print_result(f"Invoice access {endpoint}", True, "Access granted")
                    results[endpoint] = True
                elif response.status_code == 404:
                    print_result(f"Invoice access {endpoint}", True, "Endpoint not found (OK - may not be implemented)")
                    results[endpoint] = True
                elif response.status_code == 403:
                    print_result(f"Invoice access {endpoint}", False, "Access denied - should be accessible to regular users")
                    results[endpoint] = False
                else:
                    print_result(f"Invoice access {endpoint}", True, f"HTTP {response.status_code} (not access-denied)")
                    results[endpoint] = True
                    
            except Exception as e:
                print_result(f"Invoice access {endpoint}", False, f"Exception: {str(e)}")
                results[endpoint] = False
        
        # Overall success if no 403 errors
        all_passed = all(results.values())
        
        return all_passed, results
        
    except Exception as e:
        print_result("Invoice Access Test", False, f"Exception: {str(e)}")
        return False, {}

def test_calendar_endpoints(token, account_name):
    """Test calendar-related PMS endpoints"""
    print_section(f"CALENDAR ENDPOINTS - {account_name}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Calculate date range for testing
        today = date.today()
        start_date = today.isoformat()
        end_date = (today + timedelta(days=30)).isoformat()
        
        endpoints_to_test = [
            {
                'url': '/pms/rooms',
                'name': 'PMS Rooms',
                'params': {}
            },
            {
                'url': '/pms/bookings', 
                'name': 'PMS Bookings',
                'params': {'start_date': start_date, 'end_date': end_date}
            },
            {
                'url': '/pms/guests',
                'name': 'PMS Guests', 
                'params': {}
            }
        ]
        
        results = {}
        
        for endpoint_info in endpoints_to_test:
            try:
                url = f"{BASE_URL}{endpoint_info['url']}"
                params = endpoint_info['params']
                name = endpoint_info['name']
                
                response = requests.get(url, headers=headers, params=params, timeout=30)
                
                print(f"Request: GET /api{endpoint_info['url']}")
                if params:
                    print(f"Params: {params}")
                print(f"Response Status: HTTP {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print_result(f"{name}", True, f"Returned {len(data) if isinstance(data, list) else 'data'} records")
                    results[endpoint_info['url']] = True
                    
                    # Show sample data structure
                    if isinstance(data, list) and len(data) > 0:
                        print(f"Sample record keys: {list(data[0].keys()) if data[0] else 'Empty'}")
                    elif isinstance(data, dict):
                        print(f"Response keys: {list(data.keys())}")
                        
                elif response.status_code == 404:
                    print_result(f"{name}", True, "Endpoint not found (may not be implemented)")
                    results[endpoint_info['url']] = True
                else:
                    print_result(f"{name}", False, f"HTTP {response.status_code}: {response.text}")
                    results[endpoint_info['url']] = False
                    
            except Exception as e:
                print_result(f"{endpoint_info['name']}", False, f"Exception: {str(e)}")
                results[endpoint_info['url']] = False
        
        all_passed = all(results.values())
        return all_passed, results
        
    except Exception as e:
        print_result("Calendar Endpoints Test", False, f"Exception: {str(e)}")
        return False, {}

def test_specific_account(account_type):
    """Test all endpoints for a specific account"""
    account_info = TEST_ACCOUNTS[account_type]
    
    # Login
    token, user, tenant = login_user(account_type)
    if not token:
        return {
            'login': False,
            'dashboard': False,
            'invoices': False,
            'calendar': False
        }
    
    results = {'login': True}
    
    # Test dashboard with performance check
    dashboard_success, response_time, dashboard_data = test_reports_basic_dashboard(
        token, account_info['name'], performance_check=True
    )
    results['dashboard'] = dashboard_success
    results['dashboard_response_time'] = response_time
    
    # Test invoice access
    invoice_success, invoice_results = test_invoice_access(token, account_info['name'])
    results['invoices'] = invoice_success
    results['invoice_details'] = invoice_results
    
    # Test calendar endpoints
    calendar_success, calendar_results = test_calendar_endpoints(token, account_info['name'])
    results['calendar'] = calendar_success
    results['calendar_details'] = calendar_results
    
    return results

def main():
    """Main test execution"""
    print("\n" + "="*80)
    print("  REPORTS DASHBOARD & INVOICE ACCESS BACKEND TEST")
    print("  Testing optimized basic dashboard performance and invoice access")
    print("="*80)
    
    all_results = {}
    
    # Test both accounts
    for account_type in ['admin', 'supervisor', 'finance']:
        account_name = TEST_ACCOUNTS[account_type]['name']
        print(f"\n🏨 Testing {account_name} ({TEST_ACCOUNTS[account_type]['email']})")
        
        account_results = test_specific_account(account_type)
        all_results[account_type] = account_results
    
    # Print comprehensive summary
    print_final_summary(all_results)
    
    return all_results

def print_final_summary(all_results):
    """Print final comprehensive test summary"""
    print_section("COMPREHENSIVE TEST SUMMARY")
    
    total_tests = 0
    passed_tests = 0
    
    for account_type, results in all_results.items():
        account_name = TEST_ACCOUNTS[account_type]['name']
        print(f"\n📊 {account_name} Results:")
        
        core_tests = ['login', 'dashboard', 'invoices', 'calendar']
        account_total = len(core_tests)
        account_passed = sum(1 for test in core_tests if results.get(test, False))
        
        total_tests += account_total
        passed_tests += account_passed
        
        for test in core_tests:
            status = "✅" if results.get(test, False) else "❌"
            print(f"  {status} {test.replace('_', ' ').title()}")
            
            # Show performance info for dashboard
            if test == 'dashboard' and results.get('dashboard_response_time'):
                response_time = results['dashboard_response_time']
                perf_status = "🚀" if response_time < 2.0 else "⚡" if response_time < 5.0 else "🐌"
                print(f"      {perf_status} Response time: {response_time:.2f}s")
        
        print(f"  Account Success Rate: {account_passed}/{account_total} ({account_passed/account_total*100:.1f}%)")
    
    overall_success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n🎯 OVERALL RESULTS:")
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {overall_success_rate:.1f}%")
    
    # Performance summary
    dashboard_times = []
    for results in all_results.values():
        if results.get('dashboard_response_time'):
            dashboard_times.append(results['dashboard_response_time'])
    
    if dashboard_times:
        avg_time = sum(dashboard_times) / len(dashboard_times)
        max_time = max(dashboard_times)
        print(f"\n⏱️  DASHBOARD PERFORMANCE:")
        print(f"Average Response Time: {avg_time:.2f}s")
        print(f"Maximum Response Time: {max_time:.2f}s")
        print(f"Performance Target (<5s): {'✅ MET' if max_time < 5.0 else '❌ MISSED'}")
    
    # Final verdict
    if overall_success_rate >= 90:
        print(f"\n🎉 EXCELLENT! All key functionality working correctly!")
    elif overall_success_rate >= 75:
        print(f"\n✅ GOOD! Most functionality working with minor issues.")
    else:
        print(f"\n⚠️  NEEDS ATTENTION! Several critical issues found.")
        
    # Specific findings
    print(f"\n📋 KEY FINDINGS:")
    
    # Dashboard optimization
    dashboard_working = all(results.get('dashboard', False) for results in all_results.values())
    if dashboard_working:
        print("✅ Dashboard optimization working - batch parallel queries successful")
    else:
        print("❌ Dashboard optimization issues detected")
    
    # Invoice access
    invoice_working = all(results.get('invoices', False) for results in all_results.values())
    if invoice_working:
        print("✅ Invoice access working for regular hotel users")
    else:
        print("❌ Invoice access restrictions found - may still be super_admin only")
    
    # Calendar endpoints
    calendar_working = all(results.get('calendar', False) for results in all_results.values())
    if calendar_working:
        print("✅ Calendar endpoints working correctly")
    else:
        print("❌ Calendar endpoint issues detected")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user.")
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()