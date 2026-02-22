#!/usr/bin/env python3
"""
Hotel PMS Backend Test - 3 New Features
Tests the following newly implemented features:
1. API Rate Limiting
2. Performance Optimization (Database Indexes)  
3. Monitoring/APM Dashboard

Login Credentials: email: admin@hotel.com, password: admin123
"""

import requests
import json
import time
from datetime import datetime
import os

# Configuration from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://auth-endpoint-suite.preview.emergentagent.com')
API_BASE_URL = BASE_URL + '/api'

# Test credentials
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

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

def login_and_get_token():
    """Login with admin credentials and return token"""
    print_section("LOGIN AND GET TOKEN")
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            },
            timeout=30
        )
        
        print(f"Request: POST /api/auth/login")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            print_result("Login", True, f"User: {user.get('name')}, Role: {user.get('role')}")
            print(f"Token preview: {token[:20]}..." if token else "No token")
            return token
        else:
            print_result("Login", False, f"HTTP {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print_result("Login", False, f"Exception: {str(e)}")
        return None

def test_rate_limiting(token):
    """Test API Rate Limiting feature"""
    print_section("TEST 1: API RATE LIMITING")
    
    results = {}
    
    # Test 1a: Check rate limit headers on login
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            },
            timeout=30
        )
        
        print(f"Request: POST /api/auth/login (checking headers)")
        print(f"Response Status: HTTP {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        # Check for rate limit headers
        rate_limit_headers = {
            'X-RateLimit-Limit': response.headers.get('X-RateLimit-Limit'),
            'X-RateLimit-Remaining': response.headers.get('X-RateLimit-Remaining'),  
            'X-RateLimit-Reset': response.headers.get('X-RateLimit-Reset')
        }
        
        print(f"Rate Limit Headers: {rate_limit_headers}")
        
        checks = {
            "Login successful": response.status_code == 200,
            "X-RateLimit-Limit header present": 'X-RateLimit-Limit' in response.headers,
            "X-RateLimit-Remaining header present": 'X-RateLimit-Remaining' in response.headers,
            "X-RateLimit-Reset header present": 'X-RateLimit-Reset' in response.headers,
        }
        
        for check, passed in checks.items():
            print_result(check, passed)
            
        results['rate_limit_headers'] = all(checks.values())
        
    except Exception as e:
        print_result("Rate Limit Headers Test", False, f"Exception: {str(e)}")
        results['rate_limit_headers'] = False
    
    # Test 1b: Get rate limits status
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{API_BASE_URL}/system/rate-limits", headers=headers, timeout=30)
        
        print(f"\nRequest: GET /api/system/rate-limits")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "enabled = true": data.get('enabled') == True,
                "mode = in-memory": data.get('mode') == "in-memory",
                "stats field exists": 'stats' in data,
                "limits_config exists": 'limits_config' in data.get('stats', {}),
            }
            
            stats = data.get('stats', {})
            limits_config = stats.get('limits_config', {})
            
            # Check required rate limit categories
            required_categories = ['auth', 'export', 'report', 'write', 'default', 'anonymous']
            for category in required_categories:
                checks[f"Category '{category}' exists"] = category in limits_config
                if category in limits_config:
                    category_config = limits_config[category]
                    checks[f"Category '{category}' has max_requests"] = 'max_requests' in category_config
                    checks[f"Category '{category}' has window_seconds"] = 'window_seconds' in category_config
                    
            for check, passed in checks.items():
                print_result(check, passed)
                
            results['rate_limits_status'] = all(checks.values())
            
        else:
            print_result("Rate Limits Status", False, f"HTTP {response.status_code}: {response.text}")
            results['rate_limits_status'] = False
            
    except Exception as e:
        print_result("Rate Limits Status Test", False, f"Exception: {str(e)}")
        results['rate_limits_status'] = False
    
    return results

def test_database_performance(token):
    """Test Performance Optimization (Database Indexes)"""
    print_section("TEST 2: PERFORMANCE OPTIMIZATION (DATABASE INDEXES)")
    
    results = {}
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{API_BASE_URL}/system/db-stats", headers=headers, timeout=30)
        
        print(f"Request: GET /api/system/db-stats")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "connections field exists": 'connections' in data,
                "pool_config field exists": 'pool_config' in data,
                "operations field exists": 'operations' in data,
                "indexes field exists": 'indexes' in data,
                "collections field exists": 'collections' in data,
            }
            
            # Check connections
            connections = data.get('connections', {})
            if connections:
                checks["connections has current"] = 'current' in connections
                checks["connections has available"] = 'available' in connections
                checks["connections has total_created"] = 'total_created' in connections
            
            # Check pool_config
            pool_config = data.get('pool_config', {})
            if pool_config:
                checks["pool max_pool_size = 500"] = pool_config.get('max_pool_size') == 500
                checks["pool min_pool_size = 50"] = pool_config.get('min_pool_size') == 50
            
            # Check operations
            operations = data.get('operations', {})
            if operations:
                checks["operations has insert"] = 'insert' in operations
                checks["operations has query"] = 'query' in operations
                checks["operations has update"] = 'update' in operations
                checks["operations has delete"] = 'delete' in operations
            
            # Check indexes - multiple collections with indexes
            indexes = data.get('indexes', {})
            if indexes:
                # Bookings should have 15+ indexes
                bookings_indexes = indexes.get('bookings', {}).get('count', 0)
                checks["bookings has 15+ indexes"] = bookings_indexes >= 15
                
                # Guests should have 6+ indexes
                guests_indexes = indexes.get('guests', {}).get('count', 0)
                checks["guests has 6+ indexes"] = guests_indexes >= 6
                
                # Rooms should have 4+ indexes
                rooms_indexes = indexes.get('rooms', {}).get('count', 0)
                checks["rooms has 4+ indexes"] = rooms_indexes >= 4
                
                # Folios should have 6+ indexes
                folios_indexes = indexes.get('folios', {}).get('count', 0)
                checks["folios has 6+ indexes"] = folios_indexes >= 6
            
            # Check collections stats
            collections = data.get('collections', {})
            if collections:
                for collection_name in ['bookings', 'guests', 'rooms', 'folios']:
                    if collection_name in collections:
                        collection_stats = collections[collection_name]
                        checks[f"{collection_name} has count"] = 'count' in collection_stats
                        checks[f"{collection_name} has size_mb"] = 'size_mb' in collection_stats
                        checks[f"{collection_name} has indexes"] = 'indexes' in collection_stats
            
            for check, passed in checks.items():
                print_result(check, passed)
                
            results['db_stats'] = all(checks.values())
            
        else:
            print_result("Database Stats", False, f"HTTP {response.status_code}: {response.text}")
            results['db_stats'] = False
            
    except Exception as e:
        print_result("Database Stats Test", False, f"Exception: {str(e)}")
        results['db_stats'] = False
    
    return results

def generate_traffic(token):
    """Generate some API traffic for APM testing"""
    print_section("GENERATING TRAFFIC FOR APM")
    
    headers = {"Authorization": f"Bearer {token}"}
    endpoints_to_call = [
        f"{API_BASE_URL}/pms/dashboard",
        f"{API_BASE_URL}/pms/rooms", 
        f"{API_BASE_URL}/pms/guests"
    ]
    
    print("Generating traffic by calling endpoints multiple times...")
    
    for i in range(3):
        for endpoint in endpoints_to_call:
            try:
                response = requests.get(endpoint, headers=headers, timeout=10)
                print(f"  Called {endpoint} -> HTTP {response.status_code}")
                time.sleep(0.1)  # Small delay between calls
            except Exception as e:
                print(f"  Failed to call {endpoint}: {e}")
    
    print("Traffic generation completed. Waiting 2 seconds for metrics to update...")
    time.sleep(2)

def test_monitoring_apm(token):
    """Test Monitoring/APM Dashboard"""
    print_section("TEST 3: MONITORING/APM DASHBOARD")
    
    results = {}
    
    # First generate some traffic
    generate_traffic(token)
    
    # Test 3a: GET /api/system/performance
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{API_BASE_URL}/system/performance", headers=headers, timeout=30)
        
        print(f"Request: GET /api/system/performance")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "system field exists": 'system' in data,
                "api_metrics field exists": 'api_metrics' in data,
                "rate_limiting field exists": 'rate_limiting' in data,
                "database field exists": 'database' in data,
                "timeline field exists": 'timeline' in data,
                "health_status field exists": 'health_status' in data,
                "uptime_seconds field exists": 'uptime_seconds' in data,
            }
            
            # Check system metrics
            system = data.get('system', {})
            if system:
                checks["system has cpu_percent"] = 'cpu_percent' in system
                checks["system has memory_percent"] = 'memory_percent' in system
                checks["system has disk_percent"] = 'disk_percent' in system
            
            # Check api_metrics
            api_metrics = data.get('api_metrics', {})
            if api_metrics:
                checks["api_metrics has avg_response_time_ms"] = 'avg_response_time_ms' in api_metrics
                checks["api_metrics has p50_ms"] = 'p50_ms' in api_metrics
                checks["api_metrics has p95_ms"] = 'p95_ms' in api_metrics
                checks["api_metrics has p99_ms"] = 'p99_ms' in api_metrics
                checks["api_metrics has requests_per_minute"] = 'requests_per_minute' in api_metrics
                checks["api_metrics has error_rate_percent"] = 'error_rate_percent' in api_metrics
                checks["api_metrics has slow_requests"] = 'slow_requests' in api_metrics
                checks["api_metrics has endpoints list"] = 'endpoints' in api_metrics
            
            # Check rate_limiting
            rate_limiting = data.get('rate_limiting', {})
            if rate_limiting:
                checks["rate_limiting has active_clients"] = 'active_clients' in rate_limiting
                checks["rate_limiting has total_rate_limit_hits"] = 'total_rate_limit_hits' in rate_limiting
                checks["rate_limiting has limits_config"] = 'limits_config' in rate_limiting
            
            # Check database
            database = data.get('database', {})
            if database:
                checks["database has connections"] = 'connections' in database
                checks["database has opcounters"] = 'opcounters' in database
            
            # Check timeline (array of per-minute buckets)
            timeline = data.get('timeline', [])
            if timeline:
                checks["timeline is array"] = isinstance(timeline, list)
                if timeline:
                    checks["timeline buckets have timestamp"] = 'timestamp' in timeline[0] if len(timeline) > 0 else False
            
            # Check health_status
            health_status = data.get('health_status')
            if health_status:
                checks["health_status is healthy or degraded"] = health_status in ["healthy", "degraded"]
            
            # Check uptime_seconds
            uptime_seconds = data.get('uptime_seconds')
            if uptime_seconds is not None:
                checks["uptime_seconds > 0"] = uptime_seconds > 0
            
            for check, passed in checks.items():
                print_result(check, passed)
                
            results['system_performance'] = all(checks.values())
            
        else:
            print_result("System Performance", False, f"HTTP {response.status_code}: {response.text}")
            results['system_performance'] = False
            
    except Exception as e:
        print_result("System Performance Test", False, f"Exception: {str(e)}")
        results['system_performance'] = False
    
    # Test 3b: GET /api/system/apm/endpoints
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{API_BASE_URL}/system/apm/endpoints", headers=headers, timeout=30)
        
        print(f"\nRequest: GET /api/system/apm/endpoints")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "top_endpoints field exists": 'top_endpoints' in data,
                "slowest_endpoints field exists": 'slowest_endpoints' in data,
                "error_endpoints field exists": 'error_endpoints' in data,
            }
            
            # Check that endpoints are arrays
            if 'top_endpoints' in data:
                checks["top_endpoints is array"] = isinstance(data['top_endpoints'], list)
            if 'slowest_endpoints' in data:
                checks["slowest_endpoints is array"] = isinstance(data['slowest_endpoints'], list)  
            if 'error_endpoints' in data:
                checks["error_endpoints is array"] = isinstance(data['error_endpoints'], list)
            
            for check, passed in checks.items():
                print_result(check, passed)
                
            results['apm_endpoints'] = all(checks.values())
            
        else:
            print_result("APM Endpoints", False, f"HTTP {response.status_code}: {response.text}")
            results['apm_endpoints'] = False
            
    except Exception as e:
        print_result("APM Endpoints Test", False, f"Exception: {str(e)}")
        results['apm_endpoints'] = False
    
    # Test 3c: GET /api/system/errors
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{API_BASE_URL}/system/errors", headers=headers, timeout=30)
        
        print(f"\nRequest: GET /api/system/errors")  
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "errors field exists": 'errors' in data,
                "errors is array": isinstance(data.get('errors', []), list),
            }
            
            for check, passed in checks.items():
                print_result(check, passed)
                
            results['system_errors'] = all(checks.values())
            
        else:
            print_result("System Errors", False, f"HTTP {response.status_code}: {response.text}")
            results['system_errors'] = False
            
    except Exception as e:
        print_result("System Errors Test", False, f"Exception: {str(e)}")
        results['system_errors'] = False
    
    return results

def main():
    """Main test execution"""
    print("\n" + "="*80)
    print("  HOTEL PMS BACKEND TEST - 3 NEW FEATURES")
    print("  Testing: Rate Limiting, Performance Optimization, Monitoring/APM")
    print("="*80)
    
    results = {
        "login": False,
        "rate_limiting": {},
        "database_performance": {},
        "monitoring_apm": {},
    }
    
    # Step 1: Login and get token
    token = login_and_get_token()
    if not token:
        print("\n❌ CRITICAL: Login failed. Cannot continue tests.")
        print_final_summary(results)
        return
    results["login"] = True
    
    # Step 2: Test API Rate Limiting
    rate_limiting_results = test_rate_limiting(token)
    results["rate_limiting"] = rate_limiting_results
    
    # Step 3: Test Database Performance Optimization
    db_performance_results = test_database_performance(token)  
    results["database_performance"] = db_performance_results
    
    # Step 4: Test Monitoring/APM Dashboard
    apm_results = test_monitoring_apm(token)
    results["monitoring_apm"] = apm_results
    
    # Print final summary
    print_final_summary(results)

def print_final_summary(results):
    """Print final test summary"""
    print_section("FINAL TEST SUMMARY")
    
    # Count individual test results
    all_checks = []
    
    if results["login"]:
        all_checks.append(("Login", True))
    else:
        all_checks.append(("Login", False))
    
    # Rate limiting checks
    for test_name, result in results.get("rate_limiting", {}).items():
        all_checks.append((f"Rate Limiting - {test_name}", result))
    
    # Database performance checks  
    for test_name, result in results.get("database_performance", {}).items():
        all_checks.append((f"DB Performance - {test_name}", result))
    
    # APM checks
    for test_name, result in results.get("monitoring_apm", {}).items():
        all_checks.append((f"APM/Monitoring - {test_name}", result))
    
    total_tests = len(all_checks)
    passed_tests = sum(1 for _, passed in all_checks if passed)
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {success_rate:.1f}%\n")
    
    for test_name, passed in all_checks:
        status = "✅" if passed else "❌"
        print(f"{status} {test_name}")
    
    # Summary by feature
    print("\nFEATURE SUMMARY:")
    
    rate_limiting_passed = all(results.get("rate_limiting", {}).values()) if results.get("rate_limiting") else False
    db_performance_passed = all(results.get("database_performance", {}).values()) if results.get("database_performance") else False
    apm_passed = all(results.get("monitoring_apm", {}).values()) if results.get("monitoring_apm") else False
    
    features = [
        ("API Rate Limiting", rate_limiting_passed),
        ("Database Performance Optimization", db_performance_passed), 
        ("Monitoring/APM Dashboard", apm_passed),
    ]
    
    for feature_name, passed in features:
        status = "✅" if passed else "❌"
        print(f"{status} {feature_name}")
    
    if all(passed for _, passed in features):
        print(f"\n🎉 ALL 3 FEATURES PASSED! Hotel PMS performance enhancements working correctly!")
    else:
        failed_features = [name for name, passed in features if not passed]
        print(f"\n⚠️  FAILED FEATURES: {', '.join(failed_features)}")
        print("Please review the details above for specific failures.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user.")
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()