#!/usr/bin/env python3
"""
Dashboard Backend API Testing
Tests all backend endpoints that support the Dashboard UI functionality
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://error-sweep-audit.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class DashboardBackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.tenant_id = None
        self.user_data = None
        
    def login(self):
        """Authenticate and get token"""
        print("🔐 Authenticating...")
        
        login_data = {
            "email": LOGIN_EMAIL,
            "password": LOGIN_PASSWORD
        }
        
        try:
            response = self.session.post(f"{BASE_URL}/auth/login", json=login_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                self.user_data = data.get('user', {})
                self.tenant_id = self.user_data.get('tenant_id')
                
                # Set authorization header for future requests
                self.session.headers.update({
                    'Authorization': f'Bearer {self.token}',
                    'Content-Type': 'application/json'
                })
                
                print(f"✅ Login successful - User: {self.user_data.get('name', 'Unknown')}")
                print(f"   Tenant ID: {self.tenant_id}")
                return True
            else:
                print(f"❌ Login failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
    
    def test_dashboard_endpoints(self):
        """Test all dashboard-related backend endpoints"""
        print("\n📊 Testing Dashboard Backend Endpoints...")
        
        endpoints_to_test = [
            # Core Dashboard Data
            {
                "name": "PMS Dashboard",
                "url": f"{BASE_URL}/pms/dashboard",
                "method": "GET",
                "expected_fields": ["occupancy_rate", "total_rooms", "available_rooms"]
            },
            
            # AI Dashboard Briefing
            {
                "name": "AI Dashboard Briefing", 
                "url": f"{BASE_URL}/ai/dashboard/briefing",
                "method": "GET",
                "expected_fields": ["briefing_date", "briefing_items"]
            },
            
            # Role-based Dashboard
            {
                "name": "Role-based Dashboard",
                "url": f"{BASE_URL}/dashboard/role-based", 
                "method": "GET",
                "expected_fields": ["dashboard_type", "user_role"]
            },
            
            # Folio Dashboard Stats
            {
                "name": "Folio Dashboard Stats",
                "url": f"{BASE_URL}/folio/dashboard-stats",
                "method": "GET", 
                "expected_fields": ["total_folios", "open_folios"]
            },
            
            # Multi-property Dashboard (if applicable)
            {
                "name": "Multi-property Dashboard",
                "url": f"{BASE_URL}/multi-property/dashboard",
                "method": "GET",
                "expected_fields": []  # May not be applicable for single property
            }
        ]
        
        results = []
        
        for endpoint in endpoints_to_test:
            print(f"\n🔍 Testing: {endpoint['name']}")
            
            try:
                if endpoint['method'] == 'GET':
                    response = self.session.get(endpoint['url'], timeout=15)
                else:
                    response = self.session.post(endpoint['url'], timeout=15)
                
                # Calculate response time
                response_time = response.elapsed.total_seconds() * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check for expected fields
                    missing_fields = []
                    for field in endpoint['expected_fields']:
                        if field not in data:
                            missing_fields.append(field)
                    
                    if missing_fields:
                        print(f"⚠️  {endpoint['name']}: HTTP 200 but missing fields: {missing_fields}")
                        print(f"   Response time: {response_time:.1f}ms")
                        print(f"   Available fields: {list(data.keys())}")
                        results.append({
                            'endpoint': endpoint['name'],
                            'status': 'partial_success',
                            'http_code': 200,
                            'response_time': response_time,
                            'missing_fields': missing_fields,
                            'available_fields': list(data.keys())
                        })
                    else:
                        print(f"✅ {endpoint['name']}: HTTP 200 ({response_time:.1f}ms)")
                        if endpoint['expected_fields']:
                            print(f"   All expected fields present: {endpoint['expected_fields']}")
                        else:
                            print(f"   Response fields: {list(data.keys())}")
                        results.append({
                            'endpoint': endpoint['name'],
                            'status': 'success',
                            'http_code': 200,
                            'response_time': response_time,
                            'data_sample': str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
                        })
                        
                elif response.status_code == 404:
                    print(f"⚠️  {endpoint['name']}: HTTP 404 - Endpoint not found")
                    results.append({
                        'endpoint': endpoint['name'],
                        'status': 'not_found',
                        'http_code': 404,
                        'response_time': response_time
                    })
                    
                else:
                    print(f"❌ {endpoint['name']}: HTTP {response.status_code}")
                    print(f"   Response: {response.text[:200]}")
                    results.append({
                        'endpoint': endpoint['name'],
                        'status': 'failed',
                        'http_code': response.status_code,
                        'response_time': response_time,
                        'error': response.text[:200]
                    })
                    
            except Exception as e:
                print(f"❌ {endpoint['name']}: Exception - {str(e)}")
                results.append({
                    'endpoint': endpoint['name'],
                    'status': 'error',
                    'error': str(e)
                })
        
        return results
    
    def test_dashboard_supporting_endpoints(self):
        """Test endpoints that provide data for dashboard components"""
        print("\n🏨 Testing Dashboard Supporting Endpoints...")
        
        supporting_endpoints = [
            # Quick Stats Data
            {
                "name": "Rooms List (for occupancy stats)",
                "url": f"{BASE_URL}/pms/rooms?limit=100",
                "method": "GET"
            },
            
            # Bookings for today's stats
            {
                "name": "Today's Bookings",
                "url": f"{BASE_URL}/pms/bookings?limit=50",
                "method": "GET"
            },
            
            # Guests data
            {
                "name": "Guests List (for stats)",
                "url": f"{BASE_URL}/pms/guests?limit=50", 
                "method": "GET"
            },
            
            # Companies data
            {
                "name": "Companies List",
                "url": f"{BASE_URL}/companies?limit=50",
                "method": "GET"
            }
        ]
        
        results = []
        
        for endpoint in supporting_endpoints:
            print(f"\n🔍 Testing: {endpoint['name']}")
            
            try:
                response = self.session.get(endpoint['url'], timeout=15)
                response_time = response.elapsed.total_seconds() * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Count items if it's a list
                    item_count = 0
                    if isinstance(data, list):
                        item_count = len(data)
                    elif isinstance(data, dict):
                        if 'rooms' in data:
                            item_count = len(data['rooms'])
                        elif 'bookings' in data:
                            item_count = len(data['bookings'])
                        elif 'guests' in data:
                            item_count = len(data['guests'])
                        elif 'companies' in data:
                            item_count = len(data['companies'])
                    
                    print(f"✅ {endpoint['name']}: HTTP 200 ({response_time:.1f}ms)")
                    print(f"   Items returned: {item_count}")
                    
                    results.append({
                        'endpoint': endpoint['name'],
                        'status': 'success',
                        'http_code': 200,
                        'response_time': response_time,
                        'item_count': item_count
                    })
                    
                else:
                    print(f"❌ {endpoint['name']}: HTTP {response.status_code}")
                    results.append({
                        'endpoint': endpoint['name'],
                        'status': 'failed',
                        'http_code': response.status_code,
                        'response_time': response_time
                    })
                    
            except Exception as e:
                print(f"❌ {endpoint['name']}: Exception - {str(e)}")
                results.append({
                    'endpoint': endpoint['name'],
                    'status': 'error',
                    'error': str(e)
                })
        
        return results
    
    def generate_summary(self, dashboard_results, supporting_results):
        """Generate test summary"""
        print("\n" + "="*60)
        print("📋 DASHBOARD BACKEND TEST SUMMARY")
        print("="*60)
        
        # Dashboard endpoints summary
        dashboard_success = len([r for r in dashboard_results if r['status'] == 'success'])
        dashboard_partial = len([r for r in dashboard_results if r['status'] == 'partial_success'])
        dashboard_total = len(dashboard_results)
        
        print(f"\n🎯 DASHBOARD ENDPOINTS: {dashboard_success}/{dashboard_total} fully working")
        if dashboard_partial > 0:
            print(f"   ⚠️  {dashboard_partial} endpoints with missing fields")
        
        for result in dashboard_results:
            if result['status'] == 'success':
                print(f"   ✅ {result['endpoint']}: Working ({result.get('response_time', 0):.1f}ms)")
            elif result['status'] == 'partial_success':
                print(f"   ⚠️  {result['endpoint']}: Partial (missing: {result.get('missing_fields', [])})")
            elif result['status'] == 'not_found':
                print(f"   ❓ {result['endpoint']}: Not found (HTTP 404)")
            else:
                print(f"   ❌ {result['endpoint']}: Failed")
        
        # Supporting endpoints summary
        supporting_success = len([r for r in supporting_results if r['status'] == 'success'])
        supporting_total = len(supporting_results)
        
        print(f"\n🏗️  SUPPORTING ENDPOINTS: {supporting_success}/{supporting_total} working")
        
        for result in supporting_results:
            if result['status'] == 'success':
                print(f"   ✅ {result['endpoint']}: {result.get('item_count', 0)} items ({result.get('response_time', 0):.1f}ms)")
            else:
                print(f"   ❌ {result['endpoint']}: Failed")
        
        # Overall assessment
        total_success = dashboard_success + supporting_success
        total_endpoints = dashboard_total + supporting_total
        success_rate = (total_success / total_endpoints) * 100 if total_endpoints > 0 else 0
        
        print(f"\n🎯 OVERALL SUCCESS RATE: {total_success}/{total_endpoints} ({success_rate:.1f}%)")
        
        if success_rate >= 90:
            print("🎉 EXCELLENT: Dashboard backend is ready for production!")
        elif success_rate >= 75:
            print("✅ GOOD: Dashboard backend is mostly working with minor issues")
        elif success_rate >= 50:
            print("⚠️  MODERATE: Dashboard backend has significant issues")
        else:
            print("❌ CRITICAL: Dashboard backend has major failures")
        
        return {
            'dashboard_success_rate': (dashboard_success / dashboard_total) * 100 if dashboard_total > 0 else 0,
            'supporting_success_rate': (supporting_success / supporting_total) * 100 if supporting_total > 0 else 0,
            'overall_success_rate': success_rate,
            'total_endpoints_tested': total_endpoints
        }

def main():
    print("🏨 DASHBOARD BACKEND API TESTING")
    print("=" * 50)
    print(f"Target: {BASE_URL}")
    print(f"Login: {LOGIN_EMAIL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tester = DashboardBackendTester()
    
    # Step 1: Login
    if not tester.login():
        print("❌ Cannot proceed without authentication")
        sys.exit(1)
    
    # Step 2: Test dashboard endpoints
    dashboard_results = tester.test_dashboard_endpoints()
    
    # Step 3: Test supporting endpoints
    supporting_results = tester.test_dashboard_supporting_endpoints()
    
    # Step 4: Generate summary
    summary = tester.generate_summary(dashboard_results, supporting_results)
    
    print(f"\n⏰ Test completed at {datetime.now().strftime('%H:%M:%S')}")
    
    return summary['overall_success_rate'] >= 75

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)