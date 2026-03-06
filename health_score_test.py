#!/usr/bin/env python3
"""
Comprehensive Backend Testing for Mini Migration Health Score Feature
Test Cases from Review Request:
1. Authenticate and call GET /api/reports/migration-observability
2. Verify HTTP 200 and presence of top-level keys: generated_at, health_score, outbox, audit, shadow
3. Validate health_score contains at least: status, display_status, calculated_at, time_window, time_window_label, reasons, operational_guidance, signals
4. Validate signals contains: failed_outbox_count, stale_pending_count, audit_gap_count, compare_error_count, max_mismatch_rate_percent
5. Confirm scoring logic is operationally coherent with current live data
6. Verify audit gap count is exposed in the response and no malformed fields are returned
7. Report any backend issue, malformed contract, or scoring inconsistency
"""

import os
import sys
import json
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List


class MigrationHealthScoreTest:
    def __init__(self):
        # Get backend URL from environment
        self.backend_url = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
        if not self.backend_url:
            raise Exception("REACT_APP_BACKEND_URL not found in environment")
        
        print(f"🔗 Backend URL: {self.backend_url}")
        
        # Test session
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        # Test credentials from review request
        self.email = "demo@hotel.com"
        self.password = "demo123"
        
        # Test state
        self.token = None
        self.tenant_id = None
        
        # Results tracking
        self.results = []
        self.critical_issues = []
        self.minor_issues = []
    
    def log_result(self, test_name: str, passed: bool, details: str = "", critical: bool = False):
        """Log test result and categorize issues"""
        result = {
            'test': test_name,
            'passed': passed,
            'details': details,
            'critical': critical
        }
        self.results.append(result)
        
        if not passed:
            if critical:
                self.critical_issues.append(f"❌ CRITICAL: {test_name} - {details}")
            else:
                self.minor_issues.append(f"⚠️  Minor: {test_name} - {details}")
        
        print(f"{'✅' if passed else ('❌' if critical else '⚠️ ')} {test_name}: {'PASS' if passed else 'FAIL'}")
        if details and not passed:
            print(f"   Details: {details}")
    
    def authenticate(self) -> bool:
        """Test Case 1: Authenticate with demo@hotel.com / demo123"""
        try:
            print("\n🔐 Testing Authentication with demo@hotel.com / demo123...")
            
            response = self.session.post(f'{self.backend_url}/api/auth/login', json={
                'email': self.email,
                'password': self.password
            })
            
            if response.status_code != 200:
                self.log_result("Authentication", False, 
                              f"Login failed with status {response.status_code}: {response.text}", 
                              critical=True)
                return False
            
            data = response.json()
            if 'access_token' not in data or 'user' not in data:
                self.log_result("Authentication", False, 
                              f"Invalid login response structure: {data}", 
                              critical=True)
                return False
            
            self.token = data['access_token']
            self.tenant_id = data['user']['tenant_id']
            
            # Update session with bearer token
            self.session.headers.update({'Authorization': f'Bearer {self.token}'})
            
            self.log_result("Authentication", True, 
                          f"Token obtained, tenant_id: {self.tenant_id}")
            return True
            
        except Exception as e:
            self.log_result("Authentication", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def call_migration_observability_api(self) -> Dict[str, Any]:
        """Test Case 1: Call GET /api/reports/migration-observability and verify HTTP 200"""
        try:
            print("\n📡 Calling GET /api/reports/migration-observability...")
            
            response = self.session.get(f'{self.backend_url}/api/reports/migration-observability')
            
            if response.status_code != 200:
                self.log_result("Migration Observability API Call", False, 
                              f"API returned status {response.status_code}: {response.text}", 
                              critical=True)
                return {}
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                self.log_result("Migration Observability API Response JSON", False, 
                              f"Invalid JSON response: {str(e)}", 
                              critical=True)
                return {}
            
            self.log_result("Migration Observability API Call", True, 
                          f"HTTP 200 received with valid JSON response")
            return data
            
        except Exception as e:
            self.log_result("Migration Observability API Call", False, f"Exception: {str(e)}", critical=True)
            return {}
    
    def validate_top_level_keys(self, data: Dict[str, Any]) -> bool:
        """Test Case 2: Verify presence of top-level keys: generated_at, health_score, outbox, audit, shadow"""
        try:
            print("\n🔍 Validating Top-Level Keys...")
            
            required_keys = ['generated_at', 'health_score', 'outbox', 'audit', 'shadow']
            missing_keys = []
            
            for key in required_keys:
                if key not in data:
                    missing_keys.append(key)
            
            if missing_keys:
                self.log_result("Top-Level Keys", False, 
                              f"Missing required top-level keys: {missing_keys}", 
                              critical=True)
                return False
            
            # Validate generated_at is a valid ISO datetime
            try:
                generated_at = data['generated_at']
                datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
                self.log_result("Generated At Format", True, f"Valid ISO datetime: {generated_at}")
            except Exception as e:
                self.log_result("Generated At Format", False, f"Invalid datetime format: {generated_at}", critical=True)
                return False
            
            self.log_result("Top-Level Keys", True, 
                          f"All required keys present: {required_keys}")
            return True
            
        except Exception as e:
            self.log_result("Top-Level Keys Validation", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def validate_health_score_structure(self, health_score: Dict[str, Any]) -> bool:
        """Test Case 3: Validate health_score contains required fields"""
        try:
            print("\n🩺 Validating Health Score Structure...")
            
            required_fields = [
                'status', 'display_status', 'calculated_at', 'time_window', 
                'time_window_label', 'reasons', 'operational_guidance', 'signals'
            ]
            
            missing_fields = []
            for field in required_fields:
                if field not in health_score:
                    missing_fields.append(field)
            
            if missing_fields:
                self.log_result("Health Score Structure", False, 
                              f"Missing required health_score fields: {missing_fields}", 
                              critical=True)
                return False
            
            # Validate field types and values
            validations = []
            
            # Status should be green/yellow/red
            status = health_score.get('status')
            if status not in ['green', 'yellow', 'red']:
                validations.append(f"status '{status}' not in [green, yellow, red]")
            
            # Display status should be capitalized status
            display_status = health_score.get('display_status')
            expected_display = status.capitalize() if status else "Unknown"
            if display_status != expected_display:
                validations.append(f"display_status '{display_status}' doesn't match expected '{expected_display}'")
            
            # Calculated_at should be valid datetime
            try:
                calculated_at = health_score.get('calculated_at')
                datetime.fromisoformat(calculated_at.replace('Z', '+00:00'))
            except Exception:
                validations.append(f"calculated_at '{calculated_at}' is not valid ISO datetime")
            
            # Time window should be reasonable
            time_window = health_score.get('time_window')
            if time_window != 'last_24h':
                validations.append(f"time_window '{time_window}' unexpected")
            
            # Time window label should match
            time_window_label = health_score.get('time_window_label')
            if time_window_label != 'Last 24h':
                validations.append(f"time_window_label '{time_window_label}' unexpected")
            
            # Reasons should be a list
            reasons = health_score.get('reasons')
            if not isinstance(reasons, list):
                validations.append(f"reasons is not a list: {type(reasons)}")
            
            # Operational guidance should be non-empty string
            guidance = health_score.get('operational_guidance')
            if not isinstance(guidance, str) or not guidance.strip():
                validations.append(f"operational_guidance is not valid: {guidance}")
            
            if validations:
                self.log_result("Health Score Field Validation", False, 
                              f"Field validation failures: {validations}", critical=True)
                return False
            
            self.log_result("Health Score Structure", True, 
                          f"All required fields present and valid")
            return True
            
        except Exception as e:
            self.log_result("Health Score Structure Validation", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def validate_signals_structure(self, signals: Dict[str, Any]) -> bool:
        """Test Case 4: Validate signals contains required fields"""
        try:
            print("\n📊 Validating Signals Structure...")
            
            required_signals = [
                'failed_outbox_count', 'stale_pending_count', 'audit_gap_count', 
                'compare_error_count', 'max_mismatch_rate_percent'
            ]
            
            missing_signals = []
            for signal in required_signals:
                if signal not in signals:
                    missing_signals.append(signal)
            
            if missing_signals:
                self.log_result("Signals Structure", False, 
                              f"Missing required signals: {missing_signals}", 
                              critical=True)
                return False
            
            # Validate signal types and ranges
            validations = []
            
            # All counts should be non-negative integers
            count_fields = ['failed_outbox_count', 'stale_pending_count', 'audit_gap_count', 'compare_error_count']
            for field in count_fields:
                value = signals.get(field)
                if not isinstance(value, int) or value < 0:
                    validations.append(f"{field} '{value}' is not non-negative integer")
            
            # Mismatch rate should be non-negative float
            mismatch_rate = signals.get('max_mismatch_rate_percent')
            if not isinstance(mismatch_rate, (int, float)) or mismatch_rate < 0:
                validations.append(f"max_mismatch_rate_percent '{mismatch_rate}' is not non-negative number")
            
            if validations:
                self.log_result("Signals Field Validation", False, 
                              f"Signal validation failures: {validations}", critical=True)
                return False
            
            self.log_result("Signals Structure", True, 
                          f"All required signals present and valid")
            return True
            
        except Exception as e:
            self.log_result("Signals Structure Validation", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def validate_scoring_logic_coherence(self, health_score: Dict[str, Any], 
                                       outbox: Dict[str, Any], shadow: Dict[str, Any]) -> bool:
        """Test Case 5: Confirm scoring logic is operationally coherent with current live data"""
        try:
            print("\n🧠 Validating Scoring Logic Coherence...")
            
            status = health_score.get('status')
            signals = health_score.get('signals', {})
            reasons = health_score.get('reasons', [])
            
            failed_outbox_count = signals.get('failed_outbox_count', 0)
            stale_pending_count = signals.get('stale_pending_count', 0)
            audit_gap_count = signals.get('audit_gap_count', 0)
            compare_error_count = signals.get('compare_error_count', 0)
            max_mismatch_rate_percent = signals.get('max_mismatch_rate_percent', 0.0)
            
            coherence_issues = []
            
            # Red status logic validation
            if status == 'red':
                red_triggers = []
                if failed_outbox_count > 0:
                    red_triggers.append("failed_outbox_count > 0")
                if audit_gap_count > 0:
                    red_triggers.append("audit_gap_count > 0")
                if max_mismatch_rate_percent > 5.0:
                    red_triggers.append("max_mismatch_rate_percent > 5%")
                
                if not red_triggers:
                    coherence_issues.append(f"Status 'red' but no red triggers found")
                else:
                    self.log_result("Red Status Logic", True, f"Red triggered by: {red_triggers}")
            
            # Yellow status logic validation  
            elif status == 'yellow':
                yellow_triggers = []
                if stale_pending_count > 0:
                    yellow_triggers.append("stale_pending_count > 0")
                if 1.0 <= max_mismatch_rate_percent <= 5.0:
                    yellow_triggers.append("mismatch_rate 1-5%")
                if compare_error_count > 0:
                    yellow_triggers.append("compare_error_count > 0")
                
                # Yellow should not exist if red conditions are present
                red_blockers = []
                if failed_outbox_count > 0:
                    red_blockers.append("failed_outbox_count > 0")
                if audit_gap_count > 0:
                    red_blockers.append("audit_gap_count > 0")
                if max_mismatch_rate_percent > 5.0:
                    red_blockers.append("max_mismatch_rate_percent > 5%")
                
                if red_blockers:
                    coherence_issues.append(f"Status 'yellow' but red conditions present: {red_blockers}")
                elif not yellow_triggers:
                    coherence_issues.append(f"Status 'yellow' but no yellow triggers found")
                else:
                    self.log_result("Yellow Status Logic", True, f"Yellow triggered by: {yellow_triggers}")
            
            # Green status logic validation
            elif status == 'green':
                # Green should have no red or yellow triggers
                blocking_conditions = []
                if failed_outbox_count > 0:
                    blocking_conditions.append("failed_outbox_count > 0")
                if audit_gap_count > 0:
                    blocking_conditions.append("audit_gap_count > 0")
                if stale_pending_count > 0:
                    blocking_conditions.append("stale_pending_count > 0")
                if max_mismatch_rate_percent >= 1.0:
                    blocking_conditions.append("mismatch_rate >= 1%")
                if compare_error_count > 0:
                    blocking_conditions.append("compare_error_count > 0")
                
                if blocking_conditions:
                    coherence_issues.append(f"Status 'green' but blocking conditions present: {blocking_conditions}")
                else:
                    self.log_result("Green Status Logic", True, "Green status with no blocking conditions")
            
            # Validate reasons match the status logic
            reason_validation = []
            if stale_pending_count > 0 and status != 'green':
                expected_reason = f"{stale_pending_count} stale pending event"
                if not any(expected_reason in reason for reason in reasons):
                    reason_validation.append(f"Missing stale pending reason for count {stale_pending_count}")
            
            if failed_outbox_count > 0:
                expected_reason = f"{failed_outbox_count} failed outbox event"
                if not any(expected_reason in reason for reason in reasons):
                    reason_validation.append(f"Missing failed outbox reason for count {failed_outbox_count}")
            
            if audit_gap_count > 0:
                expected_reason = f"{audit_gap_count} audit gap detected"
                if not any(expected_reason in reason for reason in reasons):
                    reason_validation.append(f"Missing audit gap reason for count {audit_gap_count}")
            
            if reason_validation:
                coherence_issues.append(f"Reason validation issues: {reason_validation}")
            
            if coherence_issues:
                self.log_result("Scoring Logic Coherence", False, 
                              f"Coherence issues: {coherence_issues}", critical=True)
                return False
            
            self.log_result("Scoring Logic Coherence", True, 
                          f"Status '{status}' is coherent with current data")
            return True
            
        except Exception as e:
            self.log_result("Scoring Logic Coherence", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def validate_audit_gap_exposure(self, data: Dict[str, Any]) -> bool:
        """Test Case 6: Verify audit gap count is exposed in the response"""
        try:
            print("\n🔍 Validating Audit Gap Count Exposure...")
            
            # Check health_score.signals.audit_gap_count
            health_score = data.get('health_score', {})
            signals = health_score.get('signals', {})
            health_audit_gap = signals.get('audit_gap_count')
            
            # Check audit.audit_gap_count
            audit = data.get('audit', {})
            audit_gap_count = audit.get('audit_gap_count')
            
            validations = []
            
            if health_audit_gap is None:
                validations.append("health_score.signals.audit_gap_count is missing")
            elif not isinstance(health_audit_gap, int) or health_audit_gap < 0:
                validations.append(f"health_score.signals.audit_gap_count is invalid: {health_audit_gap}")
            
            if audit_gap_count is None:
                validations.append("audit.audit_gap_count is missing")
            elif not isinstance(audit_gap_count, int) or audit_gap_count < 0:
                validations.append(f"audit.audit_gap_count is invalid: {audit_gap_count}")
            
            # Both should be the same value
            if health_audit_gap is not None and audit_gap_count is not None:
                if health_audit_gap != audit_gap_count:
                    validations.append(f"audit gap counts don't match: health={health_audit_gap}, audit={audit_gap_count}")
            
            if validations:
                self.log_result("Audit Gap Count Exposure", False, 
                              f"Audit gap exposure issues: {validations}", critical=True)
                return False
            
            self.log_result("Audit Gap Count Exposure", True, 
                          f"Audit gap count properly exposed: {health_audit_gap}")
            return True
            
        except Exception as e:
            self.log_result("Audit Gap Count Exposure", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def validate_no_malformed_fields(self, data: Dict[str, Any]) -> bool:
        """Test Case 7: Verify no malformed fields are returned"""
        try:
            print("\n🔍 Validating No Malformed Fields...")
            
            malformed_issues = []
            
            def check_dict_recursive(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        current_path = f"{path}.{key}" if path else key
                        
                        # Check for null/None values in required fields
                        if key in ['status', 'display_status', 'calculated_at', 'generated_at'] and value is None:
                            malformed_issues.append(f"{current_path} is None")
                        
                        # Check for empty strings in required fields
                        if key in ['status', 'display_status', 'operational_guidance'] and value == "":
                            malformed_issues.append(f"{current_path} is empty string")
                        
                        # Check for NaN or infinite numbers
                        if isinstance(value, float) and (value != value or value == float('inf') or value == float('-inf')):
                            malformed_issues.append(f"{current_path} is NaN or infinite")
                        
                        # Recursively check nested objects
                        check_dict_recursive(value, current_path)
                
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        check_dict_recursive(item, f"{path}[{i}]")
            
            check_dict_recursive(data)
            
            # Additional specific checks
            health_score = data.get('health_score', {})
            
            # Check timestamp formats
            for field in ['generated_at', 'calculated_at']:
                if field in data:
                    try:
                        datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                    except Exception:
                        malformed_issues.append(f"{field} has invalid datetime format: {data[field]}")
                
                if field in health_score:
                    try:
                        datetime.fromisoformat(health_score[field].replace('Z', '+00:00'))
                    except Exception:
                        malformed_issues.append(f"health_score.{field} has invalid datetime format: {health_score[field]}")
            
            if malformed_issues:
                self.log_result("No Malformed Fields", False, 
                              f"Malformed fields detected: {malformed_issues}", critical=True)
                return False
            
            self.log_result("No Malformed Fields", True, 
                          "All fields properly formatted")
            return True
            
        except Exception as e:
            self.log_result("No Malformed Fields Validation", False, f"Exception: {str(e)}", critical=True)
            return False
    
    def run_comprehensive_test(self) -> bool:
        """Run all test cases in sequence per review request"""
        print("🚀 Starting Mini Migration Health Score Feature Test Suite")
        print("=" * 70)
        
        # Test Case: Authentication
        if not self.authenticate():
            return False
        
        # Test Case 1: Call API and verify HTTP 200
        data = self.call_migration_observability_api()
        if not data:
            return False
        
        # Test Case 2: Verify top-level keys
        if not self.validate_top_level_keys(data):
            return False
        
        # Test Case 3: Validate health_score structure
        health_score = data.get('health_score', {})
        if not self.validate_health_score_structure(health_score):
            return False
        
        # Test Case 4: Validate signals structure
        signals = health_score.get('signals', {})
        if not self.validate_signals_structure(signals):
            return False
        
        # Test Case 5: Validate scoring logic coherence
        outbox = data.get('outbox', {})
        shadow = data.get('shadow', {})
        if not self.validate_scoring_logic_coherence(health_score, outbox, shadow):
            return False
        
        # Test Case 6: Validate audit gap count exposure
        if not self.validate_audit_gap_exposure(data):
            return False
        
        # Test Case 7: Validate no malformed fields
        if not self.validate_no_malformed_fields(data):
            return False
        
        return True
    
    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 70)
        print("🎯 MINI MIGRATION HEALTH SCORE FEATURE TEST SUMMARY")
        print("=" * 70)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r['passed'])
        failed_tests = total_tests - passed_tests
        
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"🎯 Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if self.critical_issues:
            print(f"\n🚨 CRITICAL ISSUES ({len(self.critical_issues)}):")
            for issue in self.critical_issues:
                print(f"  {issue}")
        
        if self.minor_issues:
            print(f"\n⚠️  MINOR ISSUES ({len(self.minor_issues)}):")
            for issue in self.minor_issues:
                print(f"  {issue}")
        
        if not self.critical_issues and not self.minor_issues:
            print("\n🎉 ALL TESTS PASSED - Mini Migration Health Score feature is working correctly!")
        
        print("\n📋 DETAILED TEST RESULTS:")
        for result in self.results:
            status = "✅ PASS" if result['passed'] else ("❌ CRITICAL FAIL" if result['critical'] else "⚠️  MINOR FAIL")
            print(f"  {status:<16} {result['test']}")
            if result['details'] and not result['passed']:
                print(f"    └─ {result['details']}")


def main():
    """Main test execution"""
    try:
        tester = MigrationHealthScoreTest()
        success = tester.run_comprehensive_test()
        tester.print_summary()
        
        # Return appropriate exit code
        if tester.critical_issues:
            print("\n❌ CRITICAL ISSUES DETECTED - HEALTH SCORE FEATURE HAS PROBLEMS")
            sys.exit(1)
        elif not success:
            print("\n⚠️  SOME TESTS FAILED - CHECK SUMMARY ABOVE")
            sys.exit(1)
        else:
            print("\n✅ ALL TESTS PASSED - MINI MIGRATION HEALTH SCORE FEATURE WORKING")
            sys.exit(0)
            
    except Exception as e:
        print(f"\n💥 FATAL ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()