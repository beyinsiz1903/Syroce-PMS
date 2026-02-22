#!/usr/bin/env python3
"""
Auth Endpoint Suite Backend Test - 42 Test Cases
Testing all security and compliance endpoints as specified in review request.

Login: demo@hotel.com / demo123
Target: 42/42 = 100% pass rate
"""

import requests
import json
from datetime import datetime
import os

# Configuration
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://auth-endpoint-suite.preview.emergentagent.com')
BASE_URL = f"{BACKEND_URL}/api"
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

class TestResults:
    def __init__(self):
        self.results = []
        self.total_tests = 42
        self.passed = 0
        self.failed = 0
    
    def add_result(self, test_num, endpoint, expected_status, actual_status, passed, details=""):
        result = {
            'test_num': test_num,
            'endpoint': endpoint,
            'expected_status': expected_status,
            'actual_status': actual_status,
            'passed': passed,
            'details': details
        }
        self.results.append(result)
        if passed:
            self.passed += 1
        else:
            self.failed += 1
    
    def print_summary(self):
        print(f"\n{'='*80}")
        print(f"  FINAL TEST RESULTS: {self.passed}/{self.total_tests} = {(self.passed/self.total_tests*100):.1f}%")
        print(f"{'='*80}")
        
        # Group results by pass/fail
        failed_tests = [r for r in self.results if not r['passed']]
        passed_tests = [r for r in self.results if r['passed']]
        
        if failed_tests:
            print(f"\n❌ FAILED TESTS ({len(failed_tests)}):")
            for result in failed_tests:
                print(f"  {result['test_num']:2d}. {result['endpoint']} → Expected {result['expected_status']}, Got {result['actual_status']} - {result['details']}")
        
        if passed_tests:
            print(f"\n✅ PASSED TESTS ({len(passed_tests)}):")
            for result in passed_tests:
                print(f"  {result['test_num']:2d}. {result['endpoint']} → {result['actual_status']} ✓")

def print_test_header(test_num, endpoint, description):
    """Print formatted test header"""
    print(f"\n{test_num:2d}. {endpoint}")
    print(f"    {description}")
    print(f"    {'-' * 60}")

def make_request(method, endpoint, token=None, json_data=None, params=None, expected_status=200):
    """Make HTTP request and return response info"""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=json_data, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=json_data, params=params, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        success = response.status_code == expected_status
        
        # Print request details
        print(f"    Request: {method.upper()} {endpoint}")
        if json_data:
            print(f"    Body: {json.dumps(json_data)}")
        if params:
            print(f"    Params: {params}")
        print(f"    Response: HTTP {response.status_code}")
        
        # Print response preview
        try:
            resp_data = response.json()
            if isinstance(resp_data, dict) and len(str(resp_data)) < 200:
                print(f"    Data: {resp_data}")
            else:
                print(f"    Data: {str(resp_data)[:150]}...")
        except:
            print(f"    Data: {response.text[:150]}...")
        
        return response, success
        
    except Exception as e:
        print(f"    ERROR: {str(e)}")
        return None, False

def main():
    """Execute all 42 tests as specified in review request"""
    print("="*80)
    print("  AUTH ENDPOINT SUITE - BACKEND API TEST")
    print("  42 Tests for 2FA, IP Control, GDPR, PCI DSS, Tenant Isolation, Central Office")
    print("="*80)
    
    results = TestResults()
    token = None
    
    # Test 1: Login
    print_test_header(1, "POST /api/auth/login", "Login with demo@hotel.com / demo123")
    login_data = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
    response, success = make_request("POST", "/auth/login", json_data=login_data, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            token = data.get("access_token")
            details = f"Got access_token: {token[:20] if token else 'None'}..."
        except:
            success = False
            details = "No access_token in response"
    else:
        details = "Login failed"
    
    results.add_result(1, "POST /api/auth/login", 200, response.status_code if response else 0, success, details)
    
    if not token:
        print("\n❌ CRITICAL: Login failed. Cannot continue with authenticated tests.")
        results.print_summary()
        return
    
    # Test 2: Get user profile
    print_test_header(2, "GET /api/auth/me", "Get current user profile")
    response, success = make_request("GET", "/auth/me", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_email = "email" in data
            has_id = "id" in data
            has_tenant_id = "tenant_id" in data
            success = has_email and has_id and has_tenant_id
            details = f"Email: {has_email}, ID: {has_id}, Tenant: {has_tenant_id}"
        except:
            success = False
            details = "Invalid JSON response"
    else:
        details = "Request failed"
    
    results.add_result(2, "GET /api/auth/me", 200, response.status_code if response else 0, success, details)
    
    # Test 3: 2FA Status
    print_test_header(3, "GET /api/security/2fa/status", "Get 2FA status")
    response, success = make_request("GET", "/security/2fa/status", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_enabled = "enabled" in data
            has_enforced = "enforced_by_policy" in data
            success = has_enabled and has_enforced
            details = f"Enabled field: {has_enabled}, Enforced field: {has_enforced}"
        except:
            success = False
            details = "Missing required fields"
    else:
        details = "Request failed"
    
    results.add_result(3, "GET /api/security/2fa/status", 200, response.status_code if response else 0, success, details)
    
    # Test 4: 2FA Setup
    print_test_header(4, "POST /api/security/2fa/setup", "Setup 2FA")
    response, success = make_request("POST", "/security/2fa/setup", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_secret = "secret" in data
            has_qr = "qr_code" in data
            success = has_secret and has_qr
            details = f"Secret: {has_secret}, QR Code: {has_qr}"
        except:
            success = False
            details = "Missing required fields"
    else:
        details = "Request failed"
    
    results.add_result(4, "POST /api/security/2fa/setup", 200, response.status_code if response else 0, success, details)
    
    # Test 5: 2FA Verify (invalid code)
    print_test_header(5, "POST /api/security/2fa/verify", "Verify 2FA with invalid code")
    verify_data = {"code": "000000"}
    response, success = make_request("POST", "/security/2fa/verify", token=token, json_data=verify_data, expected_status=400)
    details = "Invalid code correctly rejected" if success else "Should reject invalid code"
    results.add_result(5, "POST /api/security/2fa/verify", 400, response.status_code if response else 0, success, details)
    
    # Test 6: 2FA Tenant Policy
    print_test_header(6, "GET /api/security/2fa/tenant-policy", "Get tenant 2FA policy")
    response, success = make_request("GET", "/security/2fa/tenant-policy", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_require = "require_2fa" in data
            details = f"Require 2FA field: {has_require}"
        except:
            success = False
            details = "Missing required fields"
    else:
        details = "Request failed"
    
    results.add_result(6, "GET /api/security/2fa/tenant-policy", 200, response.status_code if response else 0, success, details)
    
    # Test 7: Update 2FA Tenant Policy
    print_test_header(7, "PUT /api/security/2fa/tenant-policy", "Update tenant 2FA policy")
    policy_data = {
        "require_2fa": False,
        "require_2fa_roles": ["admin"],
        "enforce_after_days": 7,
        "max_failed_attempts": 5,
        "lockout_duration_minutes": 30,
        "trusted_device_days": 30,
        "require_2fa_for_sensitive_ops": True
    }
    response, success = make_request("PUT", "/security/2fa/tenant-policy", token=token, json_data=policy_data, expected_status=200)
    details = "Policy updated successfully" if success else "Policy update failed"
    results.add_result(7, "PUT /api/security/2fa/tenant-policy", 200, response.status_code if response else 0, success, details)
    
    # Test 8: 2FA Stats
    print_test_header(8, "GET /api/security/2fa/stats", "Get 2FA adoption stats")
    response, success = make_request("GET", "/security/2fa/stats", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_total = "total_users" in data
            has_adoption = "adoption_rate" in data
            success = has_total and has_adoption
            details = f"Total users: {has_total}, Adoption rate: {has_adoption}"
        except:
            success = False
            details = "Missing required fields"
    else:
        details = "Request failed"
    
    results.add_result(8, "GET /api/security/2fa/stats", 200, response.status_code if response else 0, success, details)
    
    # Test 9: Trusted Devices
    print_test_header(9, "GET /api/security/2fa/trusted-devices", "Get trusted devices")
    response, success = make_request("GET", "/security/2fa/trusted-devices", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_devices = "devices" in data
            success = has_devices
            details = f"Devices field: {has_devices}"
        except:
            success = False
            details = "Missing devices field"
    else:
        details = "Request failed"
    
    results.add_result(9, "GET /api/security/2fa/trusted-devices", 200, response.status_code if response else 0, success, details)
    
    # Test 10: IP Rules List
    print_test_header(10, "GET /api/security/ip/rules", "Get IP access rules")
    response, success = make_request("GET", "/security/ip/rules", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_rules = "rules" in data
            success = has_rules
            details = f"Rules field: {has_rules}"
        except:
            success = False
            details = "Missing rules field"
    else:
        details = "Request failed"
    
    results.add_result(10, "GET /api/security/ip/rules", 200, response.status_code if response else 0, success, details)
    
    # Test 11: Create IP Rule (MUST use "whitelist")
    print_test_header(11, "POST /api/security/ip/rules", "Create IP rule with whitelist")
    ip_rule_data = {
        "ip_address": "10.20.30.40",
        "rule_type": "whitelist",
        "description": "Test rule"
    }
    response, success = make_request("POST", "/security/ip/rules", token=token, json_data=ip_rule_data, expected_status=200)
    details = "IP rule created successfully" if success else "IP rule creation failed"
    results.add_result(11, "POST /api/security/ip/rules", 200, response.status_code if response else 0, success, details)
    
    # Test 12: Check IP
    print_test_header(12, "POST /api/security/ip/check", "Check current IP")
    response, success = make_request("POST", "/security/ip/check", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_client_ip = "client_ip" in data
            has_allowed = "allowed" in data
            success = has_client_ip and has_allowed
            details = f"Client IP: {has_client_ip}, Allowed: {has_allowed}"
        except:
            success = False
            details = "Missing required fields"
    else:
        details = "Request failed"
    
    results.add_result(12, "POST /api/security/ip/check", 200, response.status_code if response else 0, success, details)
    
    # Test 13: GDPR Compliance Status
    print_test_header(13, "GET /api/gdpr/compliance-status", "Get GDPR compliance status")
    response, success = make_request("GET", "/gdpr/compliance-status", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_score = "compliance_score" in data
            has_checks = "compliance_checks" in data
            success = has_score and has_checks
            details = f"Compliance score: {has_score}, Checks: {has_checks}"
        except:
            success = False
            details = "Missing required fields"
    else:
        details = "Request failed"
    
    results.add_result(13, "GET /api/gdpr/compliance-status", 200, response.status_code if response else 0, success, details)
    
    # Test 14: GDPR Retention Policy
    print_test_header(14, "GET /api/gdpr/retention-policy", "Get GDPR retention policy")
    response, success = make_request("GET", "/gdpr/retention-policy", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_retention = "guest_data_retention_days" in data
            success = has_retention
            details = f"Guest data retention days: {has_retention}"
        except:
            success = False
            details = "Missing retention field"
    else:
        details = "Request failed"
    
    results.add_result(14, "GET /api/gdpr/retention-policy", 200, response.status_code if response else 0, success, details)
    
    # Test 15: GDPR DPA List
    print_test_header(15, "GET /api/gdpr/dpa", "Get data processing agreements")
    response, success = make_request("GET", "/gdpr/dpa", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_agreements = "agreements" in data
            success = has_agreements
            details = f"Agreements field: {has_agreements}"
        except:
            success = False
            details = "Missing agreements field"
    else:
        details = "Request failed"
    
    results.add_result(15, "GET /api/gdpr/dpa", 200, response.status_code if response else 0, success, details)
    
    # Test 16: Create GDPR DPA
    print_test_header(16, "POST /api/gdpr/dpa", "Create data processing agreement")
    dpa_data = {
        "processor_name": "Test Processor",
        "purpose": "Data analytics",
        "data_categories": ["guest_info", "booking_data"],
        "retention_period_days": 365,
        "security_measures": ["encryption", "access_control"],
        "cross_border_transfer": False
    }
    response, success = make_request("POST", "/gdpr/dpa", token=token, json_data=dpa_data, expected_status=200)
    details = "DPA created successfully" if success else "DPA creation failed"
    results.add_result(16, "POST /api/gdpr/dpa", 200, response.status_code if response else 0, success, details)
    
    # Test 17: Update GDPR Retention Policy
    print_test_header(17, "PUT /api/gdpr/retention-policy", "Update retention policy")
    params = {"guest_data_days": 1095, "auto_anonymize": False}
    response, success = make_request("PUT", "/gdpr/retention-policy", token=token, params=params, expected_status=200)
    details = "Retention policy updated" if success else "Retention policy update failed"
    results.add_result(17, "PUT /api/gdpr/retention-policy", 200, response.status_code if response else 0, success, details)
    
    # Test 18: PCI DSS Compliance Status
    print_test_header(18, "GET /api/pci-dss/compliance-status", "Get PCI DSS compliance status")
    response, success = make_request("GET", "/pci-dss/compliance-status", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_score = "compliance_score" in data
            has_requirements = "requirements" in data
            success = has_score and has_requirements
            details = f"Compliance score: {has_score}, Requirements: {has_requirements}"
        except:
            success = False
            details = "Missing required fields"
    else:
        details = "Request failed"
    
    results.add_result(18, "GET /api/pci-dss/compliance-status", 200, response.status_code if response else 0, success, details)
    
    # Test 19: PCI DSS Requirements
    print_test_header(19, "GET /api/pci-dss/requirements", "Get PCI DSS requirements")
    response, success = make_request("GET", "/pci-dss/requirements", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            total_reqs = data.get("total_requirements")
            success = total_reqs == 24
            details = f"Total requirements: {total_reqs} (expected 24)"
        except:
            success = False
            details = "Missing total_requirements field"
    else:
        details = "Request failed"
    
    results.add_result(19, "GET /api/pci-dss/requirements", 200, response.status_code if response else 0, success, details)
    
    # Test 20: PCI DSS Tokenize
    print_test_header(20, "POST /api/pci-dss/tokenize", "Tokenize credit card")
    card_data = {
        "card_number": "4111111111111111",
        "card_holder": "Test User",
        "expiry_month": 12,
        "expiry_year": 2028
    }
    response, success = make_request("POST", "/pci-dss/tokenize", token=token, json_data=card_data, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            last_four = data.get("last_four")
            card_brand = data.get("card_brand")
            success = last_four == "1111" and card_brand == "Visa"
            details = f"Last four: {last_four}, Brand: {card_brand}"
        except:
            success = False
            details = "Missing tokenization fields"
    else:
        details = "Request failed"
    
    results.add_result(20, "POST /api/pci-dss/tokenize", 200, response.status_code if response else 0, success, details)
    
    # Test 21: PCI DSS Tokens
    print_test_header(21, "GET /api/pci-dss/tokens", "Get tokenized cards")
    response, success = make_request("GET", "/pci-dss/tokens", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_tokens = "tokens" in data
            success = has_tokens
            details = f"Tokens field: {has_tokens}"
        except:
            success = False
            details = "Missing tokens field"
    else:
        details = "Request failed"
    
    results.add_result(21, "GET /api/pci-dss/tokens", 200, response.status_code if response else 0, success, details)
    
    # Test 22: PCI DSS Security Scan
    print_test_header(22, "POST /api/pci-dss/security-scan", "Run security scan")
    response, success = make_request("POST", "/pci-dss/security-scan", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_risk = "risk_level" in data
            has_findings = "findings" in data
            success = has_risk and has_findings
            details = f"Risk level: {has_risk}, Findings: {has_findings}"
        except:
            success = False
            details = "Missing scan fields"
    else:
        details = "Request failed"
    
    results.add_result(22, "POST /api/pci-dss/security-scan", 200, response.status_code if response else 0, success, details)
    
    # Test 23: PCI DSS PAN Scan
    print_test_header(23, "POST /api/pci-dss/pan-scan", "Run PAN exposure scan")
    response, success = make_request("POST", "/pci-dss/pan-scan", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_pan_count = "exposed_pan_count" in data
            success = has_pan_count
            details = f"Exposed PAN count: {has_pan_count}"
        except:
            success = False
            details = "Missing PAN count field"
    else:
        details = "Request failed"
    
    results.add_result(23, "POST /api/pci-dss/pan-scan", 200, response.status_code if response else 0, success, details)
    
    # Test 24: PCI DSS Scan History
    print_test_header(24, "GET /api/pci-dss/scan-history", "Get scan history")
    response, success = make_request("GET", "/pci-dss/scan-history", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_scans = "scans" in data
            success = has_scans
            details = f"Scans field: {has_scans}"
        except:
            success = False
            details = "Missing scans field"
    else:
        details = "Request failed"
    
    results.add_result(24, "GET /api/pci-dss/scan-history", 200, response.status_code if response else 0, success, details)
    
    # Test 25: PCI DSS Audit Update
    print_test_header(25, "PUT /api/pci-dss/audit/1.1", "Update audit requirement 1.1")
    params = {"audit_status": "compliant", "evidence": "Firewall active"}
    response, success = make_request("PUT", "/pci-dss/audit/1.1", token=token, params=params, expected_status=200)
    details = "Audit requirement updated" if success else "Audit update failed"
    results.add_result(25, "PUT /api/pci-dss/audit/1.1", 200, response.status_code if response else 0, success, details)
    
    # Test 26: Tenant Isolation Health
    print_test_header(26, "GET /api/tenant-isolation/health", "Get tenant isolation health")
    response, success = make_request("GET", "/tenant-isolation/health", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_score = "isolation_score" in data
            success = has_score
            details = f"Isolation score: {has_score}"
        except:
            success = False
            details = "Missing isolation score"
    else:
        details = "Request failed"
    
    results.add_result(26, "GET /api/tenant-isolation/health", 200, response.status_code if response else 0, success, details)
    
    # Test 27: Tenant Isolation Policy
    print_test_header(27, "GET /api/tenant-isolation/policy", "Get isolation policy")
    response, success = make_request("GET", "/tenant-isolation/policy", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_strict = "strict_mode" in data
            success = has_strict
            details = f"Strict mode: {has_strict}"
        except:
            success = False
            details = "Missing strict mode"
    else:
        details = "Request failed"
    
    results.add_result(27, "GET /api/tenant-isolation/policy", 200, response.status_code if response else 0, success, details)
    
    # Test 28: Update Tenant Isolation Policy
    print_test_header(28, "PUT /api/tenant-isolation/policy", "Update isolation policy")
    params = {"strict_mode": True, "pii_masking_enabled": True}
    response, success = make_request("PUT", "/tenant-isolation/policy", token=token, params=params, expected_status=200)
    details = "Isolation policy updated" if success else "Policy update failed"
    results.add_result(28, "PUT /api/tenant-isolation/policy", 200, response.status_code if response else 0, success, details)
    
    # Test 29: Tenant Data Summary
    print_test_header(29, "GET /api/tenant-isolation/data-summary", "Get data summary")
    response, success = make_request("GET", "/tenant-isolation/data-summary", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            total_records = data.get("total_records", 0)
            success = total_records > 0
            details = f"Total records: {total_records}"
        except:
            success = False
            details = "Missing total records"
    else:
        details = "Request failed"
    
    results.add_result(29, "GET /api/tenant-isolation/data-summary", 200, response.status_code if response else 0, success, details)
    
    # Test 30: Data Classification
    print_test_header(30, "GET /api/tenant-isolation/data-classification", "Get data classification")
    response, success = make_request("GET", "/tenant-isolation/data-classification", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_classifications = "classifications" in data
            success = has_classifications
            details = f"Classifications field: {has_classifications}"
        except:
            success = False
            details = "Missing classifications"
    else:
        details = "Request failed"
    
    results.add_result(30, "GET /api/tenant-isolation/data-classification", 200, response.status_code if response else 0, success, details)
    
    # Test 31: PII Scan
    print_test_header(31, "GET /api/tenant-isolation/pii-scan", "Get PII scan results")
    response, success = make_request("GET", "/tenant-isolation/pii-scan", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_risk = "overall_risk" in data
            success = has_risk
            details = f"Overall risk: {has_risk}"
        except:
            success = False
            details = "Missing overall risk"
    else:
        details = "Request failed"
    
    results.add_result(31, "GET /api/tenant-isolation/pii-scan", 200, response.status_code if response else 0, success, details)
    
    # Test 32: Audit Trail
    print_test_header(32, "GET /api/tenant-isolation/audit-trail", "Get audit trail")
    params = {"days": 30}
    response, success = make_request("GET", "/tenant-isolation/audit-trail", token=token, params=params, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_events = "events" in data
            success = has_events
            details = f"Events field: {has_events}"
        except:
            success = False
            details = "Missing events"
    else:
        details = "Request failed"
    
    results.add_result(32, "GET /api/tenant-isolation/audit-trail", 200, response.status_code if response else 0, success, details)
    
    # Test 33: Access Logs
    print_test_header(33, "GET /api/tenant-isolation/access-logs", "Get access logs")
    response, success = make_request("GET", "/tenant-isolation/access-logs", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_logs = "logs" in data
            success = has_logs
            details = f"Logs field: {has_logs}"
        except:
            success = False
            details = "Missing logs"
    else:
        details = "Request failed"
    
    results.add_result(33, "GET /api/tenant-isolation/access-logs", 200, response.status_code if response else 0, success, details)
    
    # Test 34: Central Office Dashboard
    print_test_header(34, "GET /api/central-office/dashboard", "Get central office dashboard")
    response, success = make_request("GET", "/central-office/dashboard", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            chain_kpi = data.get("chain_kpi", {})
            chain_adr = chain_kpi.get("chain_adr", 0)
            chain_revpar = chain_kpi.get("chain_revpar", 0)
            total_revenue = chain_kpi.get("total_revenue", 0)
            success = chain_adr > 0 and chain_revpar > 0 and total_revenue > 0
            details = f"ADR: {chain_adr}, RevPAR: {chain_revpar}, Revenue: {total_revenue}"
        except:
            success = False
            details = "Missing KPI fields"
    else:
        details = "Request failed"
    
    results.add_result(34, "GET /api/central-office/dashboard", 200, response.status_code if response else 0, success, details)
    
    # Test 35: Central Office Properties
    print_test_header(35, "GET /api/central-office/properties", "Get properties")
    response, success = make_request("GET", "/central-office/properties", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            total = data.get("total", 0)
            success = total >= 1
            details = f"Total properties: {total}"
        except:
            success = False
            details = "Missing total field"
    else:
        details = "Request failed"
    
    results.add_result(35, "GET /api/central-office/properties", 200, response.status_code if response else 0, success, details)
    
    # Test 36: Occupancy Comparison
    print_test_header(36, "GET /api/central-office/occupancy-comparison", "Get occupancy comparison")
    params = {"days": 30}
    response, success = make_request("GET", "/central-office/occupancy-comparison", token=token, params=params, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_chain_avg = "chain_average" in data
            success = has_chain_avg
            details = f"Chain average: {has_chain_avg}"
        except:
            success = False
            details = "Missing chain average"
    else:
        details = "Request failed"
    
    results.add_result(36, "GET /api/central-office/occupancy-comparison", 200, response.status_code if response else 0, success, details)
    
    # Test 37: Revenue Report
    print_test_header(37, "GET /api/central-office/revenue-report", "Get revenue report")
    response, success = make_request("GET", "/central-office/revenue-report", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_adr = "chain_adr" in data
            has_revpar = "chain_revpar" in data
            success = has_adr and has_revpar
            details = f"Chain ADR: {has_adr}, Chain RevPAR: {has_revpar}"
        except:
            success = False
            details = "Missing revenue fields"
    else:
        details = "Request failed"
    
    results.add_result(37, "GET /api/central-office/revenue-report", 200, response.status_code if response else 0, success, details)
    
    # Test 38: Trends
    print_test_header(38, "GET /api/central-office/trends", "Get occupancy trends")
    params = {"metric": "occupancy", "days": 7}
    response, success = make_request("GET", "/central-office/trends", token=token, params=params, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_data_points = "data_points" in data
            success = has_data_points
            details = f"Data points: {has_data_points}"
        except:
            success = False
            details = "Missing data points"
    else:
        details = "Request failed"
    
    results.add_result(38, "GET /api/central-office/trends", 200, response.status_code if response else 0, success, details)
    
    # Test 39: Property Health
    print_test_header(39, "GET /api/central-office/property-health", "Get property health")
    response, success = make_request("GET", "/central-office/property-health", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_avg_score = "chain_average_score" in data
            success = has_avg_score
            details = f"Chain average score: {has_avg_score}"
        except:
            success = False
            details = "Missing average score"
    else:
        details = "Request failed"
    
    results.add_result(39, "GET /api/central-office/property-health", 200, response.status_code if response else 0, success, details)
    
    # Test 40: Budget Tracking
    print_test_header(40, "GET /api/central-office/budget-tracking", "Get budget tracking")
    response, success = make_request("GET", "/central-office/budget-tracking", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_chain_summary = "chain_summary" in data
            success = has_chain_summary
            details = f"Chain summary: {has_chain_summary}"
        except:
            success = False
            details = "Missing chain summary"
    else:
        details = "Request failed"
    
    results.add_result(40, "GET /api/central-office/budget-tracking", 200, response.status_code if response else 0, success, details)
    
    # Test 41: Alerts
    print_test_header(41, "GET /api/central-office/alerts", "Get alerts")
    response, success = make_request("GET", "/central-office/alerts", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_alerts = "alerts" in data
            has_critical = "critical_count" in data
            success = has_alerts and has_critical
            details = f"Alerts: {has_alerts}, Critical count: {has_critical}"
        except:
            success = False
            details = "Missing alert fields"
    else:
        details = "Request failed"
    
    results.add_result(41, "GET /api/central-office/alerts", 200, response.status_code if response else 0, success, details)
    
    # Test 42: Department Comparison
    print_test_header(42, "GET /api/central-office/department-comparison", "Get department comparison")
    response, success = make_request("GET", "/central-office/department-comparison", token=token, expected_status=200)
    
    if success and response:
        try:
            data = response.json()
            has_chain_avg = "chain_averages" in data
            success = has_chain_avg
            details = f"Chain averages: {has_chain_avg}"
        except:
            success = False
            details = "Missing chain averages"
    else:
        details = "Request failed"
    
    results.add_result(42, "GET /api/central-office/department-comparison", 200, response.status_code if response else 0, success, details)
    
    # Print final summary
    results.print_summary()
    
    if results.passed == 42:
        print(f"\n🎉 SUCCESS: All 42 tests passed! Backend is 100% functional.")
    else:
        print(f"\n⚠️ {results.failed} tests failed. Please review the details above.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Test execution interrupted by user.")
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()