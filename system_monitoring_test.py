#!/usr/bin/env python3
"""
System Monitoring & Performance Features Testing
Tests 4 new endpoints:
1. GET /api/system/performance - System performance monitoring
2. GET /api/system/logs - Log viewer with filters  
3. POST /api/network/ping - Network ping test
4. GET /api/system/health - Endpoint health check
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BACKEND_URL = "https://appstore-preview-1.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class SystemMonitoringTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.test_results = {
            'system_performance': {'passed': 0, 'failed': 0, 'details': []},
            'log_viewer': {'passed': 0, 'failed': 0, 'details': []},
            'network_ping': {'passed': 0, 'failed': 0, 'details': []},
            'endpoint_health': {'passed': 0, 'failed': 0, 'details': []}
        }
    
    def authenticate(self):
        """Authenticate and get token"""
        try:
            response = self.session.post(f"{BACKEND_URL}/auth/login", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})
                print("✅ Authentication successful")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False
    
    def test_system_performance(self):
        """Test GET /api/system/performance endpoint"""
        print("\n🔍 Testing System Performance Monitoring...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/system/performance")
            
            if response.status_code == 200:
                data = response.json()
                
                # Test 1: Response structure completeness
                required_fields = ['system', 'api_metrics', 'timeline', 'health_status', 'timestamp']
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.test_results['system_performance']['passed'] += 1
                    self.test_results['system_performance']['details'].append("✅ Response structure complete")
                else:
                    self.test_results['system_performance']['failed'] += 1
                    self.test_results['system_performance']['details'].append(f"❌ Missing fields: {missing_fields}")
                
                # Test 2: System metrics validation
                system = data.get('system', {})
                system_fields = ['cpu_percent', 'memory_percent', 'memory_used_gb', 'memory_total_gb', 
                               'disk_percent', 'disk_used_gb', 'disk_total_gb']
                
                valid_system_metrics = True
                for field in system_fields:
                    if field not in system or not isinstance(system[field], (int, float)):
                        valid_system_metrics = False
                        break
                    
                    # Validate percentage fields are 0-100
                    if 'percent' in field and not (0 <= system[field] <= 100):
                        valid_system_metrics = False
                        break
                
                if valid_system_metrics:
                    self.test_results['system_performance']['passed'] += 1
                    self.test_results['system_performance']['details'].append(f"✅ System metrics valid - CPU: {system.get('cpu_percent')}%, RAM: {system.get('memory_percent')}%")
                else:
                    self.test_results['system_performance']['failed'] += 1
                    self.test_results['system_performance']['details'].append("❌ Invalid system metrics")
                
                # Test 3: API metrics validation
                api_metrics = data.get('api_metrics', {})
                api_fields = ['avg_response_time_ms', 'requests_per_minute', 'total_requests_tracked', 'endpoints']
                
                valid_api_metrics = all(field in api_metrics for field in api_fields)
                if valid_api_metrics and isinstance(api_metrics.get('endpoints'), list):
                    self.test_results['system_performance']['passed'] += 1
                    self.test_results['system_performance']['details'].append(f"✅ API metrics valid - Avg response: {api_metrics.get('avg_response_time_ms')}ms")
                else:
                    self.test_results['system_performance']['failed'] += 1
                    self.test_results['system_performance']['details'].append("❌ Invalid API metrics")
                
                # Test 4: Health status calculation
                cpu_percent = system.get('cpu_percent', 0)
                memory_percent = system.get('memory_percent', 0)
                expected_health = 'healthy' if cpu_percent < 80 and memory_percent < 80 else 'degraded'
                actual_health = data.get('health_status')
                
                if actual_health == expected_health:
                    self.test_results['system_performance']['passed'] += 1
                    self.test_results['system_performance']['details'].append(f"✅ Health status correct: {actual_health}")
                else:
                    self.test_results['system_performance']['failed'] += 1
                    self.test_results['system_performance']['details'].append(f"❌ Health status mismatch: expected {expected_health}, got {actual_health}")
                
                # Test 5: Timeline data structure
                timeline = data.get('timeline', [])
                if isinstance(timeline, list):
                    self.test_results['system_performance']['passed'] += 1
                    self.test_results['system_performance']['details'].append(f"✅ Timeline data valid - {len(timeline)} data points")
                else:
                    self.test_results['system_performance']['failed'] += 1
                    self.test_results['system_performance']['details'].append("❌ Invalid timeline data")
                
            else:
                self.test_results['system_performance']['failed'] += 1
                self.test_results['system_performance']['details'].append(f"❌ HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.test_results['system_performance']['failed'] += 1
            self.test_results['system_performance']['details'].append(f"❌ Exception: {str(e)}")
    
    def test_log_viewer(self):
        """Test GET /api/system/logs endpoint with filters"""
        print("\n🔍 Testing Log Viewer...")
        
        # Test 1: Get all logs (no filter)
        try:
            response = self.session.get(f"{BACKEND_URL}/system/logs")
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['logs', 'count', 'filters', 'log_levels']
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.test_results['log_viewer']['passed'] += 1
                    self.test_results['log_viewer']['details'].append("✅ All logs response structure complete")
                else:
                    self.test_results['log_viewer']['failed'] += 1
                    self.test_results['log_viewer']['details'].append(f"❌ Missing fields: {missing_fields}")
                
                # Validate log levels count
                log_levels = data.get('log_levels', {})
                expected_levels = ['ERROR', 'WARN', 'INFO', 'DEBUG']
                if all(level in log_levels for level in expected_levels):
                    self.test_results['log_viewer']['passed'] += 1
                    self.test_results['log_viewer']['details'].append(f"✅ Log levels count valid: {log_levels}")
                else:
                    self.test_results['log_viewer']['failed'] += 1
                    self.test_results['log_viewer']['details'].append("❌ Invalid log levels structure")
                    
            else:
                self.test_results['log_viewer']['failed'] += 1
                self.test_results['log_viewer']['details'].append(f"❌ All logs HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.test_results['log_viewer']['failed'] += 1
            self.test_results['log_viewer']['details'].append(f"❌ All logs exception: {str(e)}")
        
        # Test 2: Filter by ERROR level
        try:
            response = self.session.get(f"{BACKEND_URL}/system/logs?level=ERROR")
            
            if response.status_code == 200:
                data = response.json()
                logs = data.get('logs', [])
                
                # Check if all returned logs are ERROR level (empty is valid if no ERROR logs exist)
                all_error = all(log.get('level') == 'ERROR' for log in logs) if logs else True
                
                if all_error:
                    self.test_results['log_viewer']['passed'] += 1
                    self.test_results['log_viewer']['details'].append(f"✅ ERROR level filter working - {len(logs)} logs (empty is valid)")
                else:
                    self.test_results['log_viewer']['failed'] += 1
                    self.test_results['log_viewer']['details'].append("❌ ERROR level filter not working properly")
                    
            else:
                self.test_results['log_viewer']['failed'] += 1
                self.test_results['log_viewer']['details'].append(f"❌ ERROR filter HTTP {response.status_code}")
                
        except Exception as e:
            self.test_results['log_viewer']['failed'] += 1
            self.test_results['log_viewer']['details'].append(f"❌ ERROR filter exception: {str(e)}")
        
        # Test 3: Filter by WARN level
        try:
            response = self.session.get(f"{BACKEND_URL}/system/logs?level=WARN")
            
            if response.status_code == 200:
                data = response.json()
                logs = data.get('logs', [])
                
                all_warn = all(log.get('level') == 'WARN' for log in logs) if logs else True
                
                if all_warn:
                    self.test_results['log_viewer']['passed'] += 1
                    self.test_results['log_viewer']['details'].append(f"✅ WARN level filter working - {len(logs)} logs (empty is valid)")
                else:
                    self.test_results['log_viewer']['failed'] += 1
                    self.test_results['log_viewer']['details'].append("❌ WARN level filter not working properly")
                    
        except Exception as e:
            self.test_results['log_viewer']['failed'] += 1
            self.test_results['log_viewer']['details'].append(f"❌ WARN filter exception: {str(e)}")
        
        # Test 4: Search functionality
        try:
            response = self.session.get(f"{BACKEND_URL}/system/logs?search=system")
            
            if response.status_code == 200:
                data = response.json()
                self.test_results['log_viewer']['passed'] += 1
                self.test_results['log_viewer']['details'].append(f"✅ Search functionality working - {data.get('count', 0)} results")
            else:
                self.test_results['log_viewer']['failed'] += 1
                self.test_results['log_viewer']['details'].append(f"❌ Search HTTP {response.status_code}")
                
        except Exception as e:
            self.test_results['log_viewer']['failed'] += 1
            self.test_results['log_viewer']['details'].append(f"❌ Search exception: {str(e)}")
        
        # Test 5: Limit parameter
        try:
            response = self.session.get(f"{BACKEND_URL}/system/logs?limit=10")
            
            if response.status_code == 200:
                data = response.json()
                logs = data.get('logs', [])
                
                if len(logs) <= 10:
                    self.test_results['log_viewer']['passed'] += 1
                    self.test_results['log_viewer']['details'].append(f"✅ Limit parameter working - {len(logs)} logs returned")
                else:
                    self.test_results['log_viewer']['failed'] += 1
                    self.test_results['log_viewer']['details'].append(f"❌ Limit not respected - {len(logs)} logs returned")
                    
        except Exception as e:
            self.test_results['log_viewer']['failed'] += 1
            self.test_results['log_viewer']['details'].append(f"❌ Limit test exception: {str(e)}")
    
    def test_network_ping(self):
        """Test POST /api/network/ping endpoint"""
        print("\n🔍 Testing Network Ping Test...")
        
        # Test 1: Default ping (8.8.8.8)
        try:
            response = self.session.post(f"{BACKEND_URL}/network/ping", json={})
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['target', 'packets_sent', 'packets_received', 'packet_loss_percent', 
                                 'latency', 'quality', 'ping_times', 'timestamp', 'status']
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.test_results['network_ping']['passed'] += 1
                    self.test_results['network_ping']['details'].append("✅ Default ping response structure complete")
                else:
                    self.test_results['network_ping']['failed'] += 1
                    self.test_results['network_ping']['details'].append(f"❌ Missing fields: {missing_fields}")
                
                # Validate latency metrics
                latency = data.get('latency', {})
                latency_fields = ['min_ms', 'avg_ms', 'max_ms']
                
                if all(field in latency for field in latency_fields):
                    self.test_results['network_ping']['passed'] += 1
                    self.test_results['network_ping']['details'].append(f"✅ Latency metrics valid - Avg: {latency.get('avg_ms')}ms")
                else:
                    self.test_results['network_ping']['failed'] += 1
                    self.test_results['network_ping']['details'].append("❌ Invalid latency metrics")
                
                # Validate quality determination
                avg_ms = latency.get('avg_ms', 0)
                expected_quality = 'excellent' if avg_ms < 50 else 'good' if avg_ms < 100 else 'fair' if avg_ms < 200 else 'poor'
                actual_quality = data.get('quality')
                
                if actual_quality in ['excellent', 'good', 'fair', 'poor', 'no_connection']:
                    self.test_results['network_ping']['passed'] += 1
                    self.test_results['network_ping']['details'].append(f"✅ Quality determination valid: {actual_quality}")
                else:
                    self.test_results['network_ping']['failed'] += 1
                    self.test_results['network_ping']['details'].append(f"❌ Invalid quality: {actual_quality}")
                
                # Validate packet loss calculation
                packets_sent = data.get('packets_sent', 0)
                packets_received = data.get('packets_received', 0)
                expected_loss = ((packets_sent - packets_received) / packets_sent) * 100 if packets_sent > 0 else 0
                actual_loss = data.get('packet_loss_percent', 0)
                
                if abs(expected_loss - actual_loss) < 0.1:  # Allow small rounding differences
                    self.test_results['network_ping']['passed'] += 1
                    self.test_results['network_ping']['details'].append(f"✅ Packet loss calculation correct: {actual_loss}%")
                else:
                    self.test_results['network_ping']['failed'] += 1
                    self.test_results['network_ping']['details'].append(f"❌ Packet loss mismatch: expected {expected_loss}%, got {actual_loss}%")
                    
            else:
                self.test_results['network_ping']['failed'] += 1
                self.test_results['network_ping']['details'].append(f"❌ Default ping HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.test_results['network_ping']['failed'] += 1
            self.test_results['network_ping']['details'].append(f"❌ Default ping exception: {str(e)}")
        
        # Test 2: Custom target ping
        try:
            response = self.session.post(f"{BACKEND_URL}/network/ping", json={
                "target": "1.1.1.1",  # Cloudflare DNS
                "count": 3
            })
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('target') == '1.1.1.1' and data.get('packets_sent') == 3:
                    self.test_results['network_ping']['passed'] += 1
                    self.test_results['network_ping']['details'].append("✅ Custom target ping working")
                else:
                    self.test_results['network_ping']['failed'] += 1
                    self.test_results['network_ping']['details'].append("❌ Custom target parameters not respected")
                    
        except Exception as e:
            self.test_results['network_ping']['failed'] += 1
            self.test_results['network_ping']['details'].append(f"❌ Custom ping exception: {str(e)}")
        
        # Test 3: Invalid target handling
        try:
            response = self.session.post(f"{BACKEND_URL}/network/ping", json={
                "target": "192.168.255.255",  # Unreachable private IP
                "count": 2
            })
            
            if response.status_code == 200:
                data = response.json()
                
                # Should handle gracefully with failed status or high packet loss
                if data.get('status') == 'failed' or data.get('packet_loss_percent', 0) == 100:
                    self.test_results['network_ping']['passed'] += 1
                    self.test_results['network_ping']['details'].append("✅ Invalid target handled gracefully")
                else:
                    self.test_results['network_ping']['failed'] += 1
                    self.test_results['network_ping']['details'].append("❌ Invalid target not handled properly")
                    
        except Exception as e:
            self.test_results['network_ping']['failed'] += 1
            self.test_results['network_ping']['details'].append(f"❌ Invalid target test exception: {str(e)}")
    
    def test_endpoint_health(self):
        """Test GET /api/system/health endpoint"""
        print("\n🔍 Testing Endpoint Health Check...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/system/health")
            
            if response.status_code == 200:
                data = response.json()
                
                # Test 1: Response structure
                required_fields = ['overall_status', 'checks', 'total_checks', 'healthy_count', 'unhealthy_count', 'timestamp']
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.test_results['endpoint_health']['passed'] += 1
                    self.test_results['endpoint_health']['details'].append("✅ Health check response structure complete")
                else:
                    self.test_results['endpoint_health']['failed'] += 1
                    self.test_results['endpoint_health']['details'].append(f"❌ Missing fields: {missing_fields}")
                
                # Test 2: MongoDB health check
                checks = data.get('checks', [])
                mongodb_check = next((check for check in checks if check.get('service') == 'MongoDB'), None)
                
                if mongodb_check:
                    if mongodb_check.get('status') == 'healthy' and 'latency_ms' in mongodb_check:
                        self.test_results['endpoint_health']['passed'] += 1
                        self.test_results['endpoint_health']['details'].append(f"✅ MongoDB health check working - {mongodb_check.get('latency_ms')}ms")
                    else:
                        self.test_results['endpoint_health']['failed'] += 1
                        self.test_results['endpoint_health']['details'].append(f"❌ MongoDB health check failed: {mongodb_check}")
                else:
                    self.test_results['endpoint_health']['failed'] += 1
                    self.test_results['endpoint_health']['details'].append("❌ MongoDB health check missing")
                
                # Test 3: Critical endpoints verification
                expected_services = ['Authentication', 'Bookings', 'Rooms', 'Guests']
                found_services = [check.get('service') for check in checks if check.get('service') in expected_services]
                
                if len(found_services) == len(expected_services):
                    self.test_results['endpoint_health']['passed'] += 1
                    self.test_results['endpoint_health']['details'].append(f"✅ All critical endpoints checked: {found_services}")
                else:
                    self.test_results['endpoint_health']['failed'] += 1
                    self.test_results['endpoint_health']['details'].append(f"❌ Missing endpoint checks. Found: {found_services}, Expected: {expected_services}")
                
                # Test 4: Overall status calculation
                unhealthy_count = data.get('unhealthy_count', 0)
                expected_status = 'healthy' if unhealthy_count == 0 else 'degraded' if unhealthy_count < 2 else 'critical'
                actual_status = data.get('overall_status')
                
                if actual_status == expected_status:
                    self.test_results['endpoint_health']['passed'] += 1
                    self.test_results['endpoint_health']['details'].append(f"✅ Overall status calculation correct: {actual_status}")
                else:
                    self.test_results['endpoint_health']['failed'] += 1
                    self.test_results['endpoint_health']['details'].append(f"❌ Overall status mismatch: expected {expected_status}, got {actual_status}")
                
                # Test 5: Latency measurements
                checks_with_latency = [check for check in checks if 'latency_ms' in check and check.get('status') == 'healthy']
                
                if len(checks_with_latency) > 0:
                    avg_latency = sum(check['latency_ms'] for check in checks_with_latency) / len(checks_with_latency)
                    self.test_results['endpoint_health']['passed'] += 1
                    self.test_results['endpoint_health']['details'].append(f"✅ Latency measurements working - Avg: {avg_latency:.2f}ms")
                else:
                    self.test_results['endpoint_health']['failed'] += 1
                    self.test_results['endpoint_health']['details'].append("❌ No latency measurements found")
                
                # Test 6: Record counts
                checks_with_counts = [check for check in checks if 'record_count' in check]
                
                if len(checks_with_counts) > 0:
                    total_records = sum(check['record_count'] for check in checks_with_counts)
                    self.test_results['endpoint_health']['passed'] += 1
                    self.test_results['endpoint_health']['details'].append(f"✅ Record counts included - Total: {total_records} records")
                else:
                    self.test_results['endpoint_health']['failed'] += 1
                    self.test_results['endpoint_health']['details'].append("❌ No record counts found")
                    
            else:
                self.test_results['endpoint_health']['failed'] += 1
                self.test_results['endpoint_health']['details'].append(f"❌ Health check HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.test_results['endpoint_health']['failed'] += 1
            self.test_results['endpoint_health']['details'].append(f"❌ Health check exception: {str(e)}")
    
    def run_all_tests(self):
        """Run all system monitoring tests"""
        print("🚀 Starting System Monitoring & Performance Features Testing...")
        print(f"Backend URL: {BACKEND_URL}")
        
        if not self.authenticate():
            print("❌ Cannot proceed without authentication")
            return
        
        # Run all tests
        self.test_system_performance()
        self.test_log_viewer()
        self.test_network_ping()
        self.test_endpoint_health()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary"""
        print("\n" + "="*80)
        print("📊 SYSTEM MONITORING & PERFORMANCE TESTING SUMMARY")
        print("="*80)
        
        total_passed = 0
        total_failed = 0
        
        for feature, results in self.test_results.items():
            passed = results['passed']
            failed = results['failed']
            total_passed += passed
            total_failed += failed
            
            status = "✅ PASS" if failed == 0 else "❌ FAIL" if passed == 0 else "⚠️ PARTIAL"
            print(f"\n{feature.upper().replace('_', ' ')}: {status}")
            print(f"  Passed: {passed}, Failed: {failed}")
            
            for detail in results['details']:
                print(f"  {detail}")
        
        print(f"\n{'='*80}")
        print(f"OVERALL RESULTS: {total_passed} PASSED, {total_failed} FAILED")
        
        if total_failed == 0:
            print("🎉 ALL SYSTEM MONITORING FEATURES WORKING PERFECTLY!")
        elif total_passed > total_failed:
            print("⚠️ MOST FEATURES WORKING - SOME ISSUES NEED ATTENTION")
        else:
            print("❌ SIGNIFICANT ISSUES FOUND - REQUIRES IMMEDIATE ATTENTION")
        
        print("="*80)

if __name__ == "__main__":
    tester = SystemMonitoringTester()
    tester.run_all_tests()