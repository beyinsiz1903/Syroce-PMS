#!/usr/bin/env python3
"""
RoomOps PMS Backend Test Suite

Tests all new and enhanced backend modules for RoomOps PMS:
1. Auth (login, me)
2. 2FA Enhanced Security (7 endpoints)
3. IP Access Control (3 endpoints)
4. GDPR Compliance (4 endpoints)
5. PCI DSS Compliance (7 endpoints) - NEW
6. Tenant Data Isolation (6 endpoints) - NEW
7. Central Office Dashboard (9 endpoints) - ENHANCED
8. Cross-Property Guests (2 endpoints)
9. Swagger Documentation (2 endpoints)

Login credentials: demo@hotel.com / demo123
"""

import requests
import json
from datetime import datetime
import os

# Configuration
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://improvement-guide-1.preview.emergentagent.com') + '/api'
DEMO_EMAIL = "demo@hotel.com"
DEMO_PASSWORD = "demo123"

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

def test_login():
    """Test POST /api/auth/login"""
    print_section("1. AUTHENTICATION")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": DEMO_EMAIL,
                "password": DEMO_PASSWORD
            },
            timeout=30
        )
        
        print(f"Request: POST /api/auth/login")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            print_result("Demo User Login", True, f"User: {user.get('name')}, Role: {user.get('role')}")
            return token
        else:
            print_result("Demo User Login", False, f"HTTP {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print_result("Demo User Login", False, f"Exception: {str(e)}")
        return None

def test_auth_me(token):
    """Test GET /api/auth/me"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/auth/me", headers=headers, timeout=30)
        
        print(f"Request: GET /api/auth/me")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print_result("Get Current User", True, f"User ID: {data.get('id')}, Name: {data.get('name')}")
            return True
        else:
            print_result("Get Current User", False, f"HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print_result("Get Current User", False, f"Exception: {str(e)}")
        return False

def test_2fa_security(token):
    """Test 2FA Enhanced Security Module (7 endpoints)"""
    print_section("2. 2FA ENHANCED SECURITY")
    
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    
    # 2.1 GET status
    try:
        response = requests.get(f"{BASE_URL}/security/2fa/status", headers=headers, timeout=30)
        results["2fa_status"] = response.status_code == 200
        print_result("GET 2FA Status", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["2fa_status"] = False
        print_result("GET 2FA Status", False, f"Exception: {str(e)}")
    
    # 2.2 POST setup
    try:
        response = requests.post(f"{BASE_URL}/security/2fa/setup", headers=headers, timeout=30)
        results["2fa_setup"] = response.status_code == 200
        print_result("POST 2FA Setup", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["2fa_setup"] = False
        print_result("POST 2FA Setup", False, f"Exception: {str(e)}")
    
    # 2.3 POST verify (invalid code should return 400)
    try:
        response = requests.post(
            f"{BASE_URL}/security/2fa/verify", 
            headers=headers,
            json={"code": "000000"},  # Invalid code
            timeout=30
        )
        results["2fa_verify"] = response.status_code == 400
        print_result("POST 2FA Verify (Invalid Code)", response.status_code == 400, f"HTTP {response.status_code} (Expected 400)")
    except Exception as e:
        results["2fa_verify"] = False
        print_result("POST 2FA Verify (Invalid Code)", False, f"Exception: {str(e)}")
    
    # 2.4 GET tenant policy
    try:
        response = requests.get(f"{BASE_URL}/security/2fa/tenant-policy", headers=headers, timeout=30)
        results["2fa_tenant_policy_get"] = response.status_code == 200
        print_result("GET 2FA Tenant Policy", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["2fa_tenant_policy_get"] = False
        print_result("GET 2FA Tenant Policy", False, f"Exception: {str(e)}")
    
    # 2.5 PUT tenant policy
    try:
        response = requests.put(
            f"{BASE_URL}/security/2fa/tenant-policy", 
            headers=headers,
            json={"enforce_2fa": True, "grace_period_days": 7},
            timeout=30
        )
        results["2fa_tenant_policy_put"] = response.status_code == 200
        print_result("PUT 2FA Tenant Policy", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["2fa_tenant_policy_put"] = False
        print_result("PUT 2FA Tenant Policy", False, f"Exception: {str(e)}")
    
    # 2.6 GET stats
    try:
        response = requests.get(f"{BASE_URL}/security/2fa/stats", headers=headers, timeout=30)
        results["2fa_stats"] = response.status_code == 200
        print_result("GET 2FA Stats", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["2fa_stats"] = False
        print_result("GET 2FA Stats", False, f"Exception: {str(e)}")
    
    # 2.7 GET trusted devices
    try:
        response = requests.get(f"{BASE_URL}/security/2fa/trusted-devices", headers=headers, timeout=30)
        results["2fa_trusted_devices"] = response.status_code == 200
        print_result("GET 2FA Trusted Devices", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["2fa_trusted_devices"] = False
        print_result("GET 2FA Trusted Devices", False, f"Exception: {str(e)}")
    
    return results

def test_ip_access(token):
    """Test IP Access Control Module (3 endpoints)"""
    print_section("3. IP ACCESS CONTROL")
    
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    
    # 3.1 GET rules
    try:
        response = requests.get(f"{BASE_URL}/security/ip/rules", headers=headers, timeout=30)
        results["ip_rules_get"] = response.status_code == 200
        print_result("GET IP Rules", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["ip_rules_get"] = False
        print_result("GET IP Rules", False, f"Exception: {str(e)}")
    
    # 3.2 POST create rule
    try:
        response = requests.post(
            f"{BASE_URL}/security/ip/rules",
            headers=headers,
            json={
                "ip_address": "192.168.1.100",
                "rule_type": "allow",
                "description": "Test IP rule"
            },
            timeout=30
        )
        results["ip_rules_post"] = response.status_code == 200
        print_result("POST IP Rule", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["ip_rules_post"] = False
        print_result("POST IP Rule", False, f"Exception: {str(e)}")
    
    # 3.3 POST check IP
    try:
        response = requests.post(
            f"{BASE_URL}/security/ip/check",
            headers=headers,
            json={"ip_address": "192.168.1.100"},
            timeout=30
        )
        results["ip_check"] = response.status_code == 200
        print_result("POST IP Check", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["ip_check"] = False
        print_result("POST IP Check", False, f"Exception: {str(e)}")
    
    return results

def test_gdpr_compliance(token):
    """Test GDPR Compliance Module (4 endpoints)"""
    print_section("4. GDPR COMPLIANCE")
    
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    
    # 4.1 GET compliance status
    try:
        response = requests.get(f"{BASE_URL}/gdpr/compliance-status", headers=headers, timeout=30)
        results["gdpr_compliance_status"] = response.status_code == 200
        print_result("GET GDPR Compliance Status", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["gdpr_compliance_status"] = False
        print_result("GET GDPR Compliance Status", False, f"Exception: {str(e)}")
    
    # 4.2 GET retention policy
    try:
        response = requests.get(f"{BASE_URL}/gdpr/retention-policy", headers=headers, timeout=30)
        results["gdpr_retention_policy"] = response.status_code == 200
        print_result("GET GDPR Retention Policy", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["gdpr_retention_policy"] = False
        print_result("GET GDPR Retention Policy", False, f"Exception: {str(e)}")
    
    # 4.3 GET DPA
    try:
        response = requests.get(f"{BASE_URL}/gdpr/dpa", headers=headers, timeout=30)
        results["gdpr_dpa_get"] = response.status_code == 200
        print_result("GET GDPR DPA", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["gdpr_dpa_get"] = False
        print_result("GET GDPR DPA", False, f"Exception: {str(e)}")
    
    # 4.4 POST DPA
    try:
        response = requests.post(
            f"{BASE_URL}/gdpr/dpa",
            headers=headers,
            json={
                "processor_name": "Test Processor",
                "processing_purpose": "Test processing",
                "data_categories": ["personal_data"]
            },
            timeout=30
        )
        results["gdpr_dpa_post"] = response.status_code == 200
        print_result("POST GDPR DPA", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["gdpr_dpa_post"] = False
        print_result("POST GDPR DPA", False, f"Exception: {str(e)}")
    
    return results

def test_pci_dss_compliance(token):
    """Test PCI DSS Compliance Module (7 endpoints) - NEW"""
    print_section("5. PCI DSS COMPLIANCE (NEW)")
    
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    
    # 5.1 GET compliance status
    try:
        response = requests.get(f"{BASE_URL}/pci-dss/compliance-status", headers=headers, timeout=30)
        results["pci_dss_compliance_status"] = response.status_code == 200
        print_result("GET PCI DSS Compliance Status", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["pci_dss_compliance_status"] = False
        print_result("GET PCI DSS Compliance Status", False, f"Exception: {str(e)}")
    
    # 5.2 GET requirements
    try:
        response = requests.get(f"{BASE_URL}/pci-dss/requirements", headers=headers, timeout=30)
        results["pci_dss_requirements"] = response.status_code == 200
        print_result("GET PCI DSS Requirements", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["pci_dss_requirements"] = False
        print_result("GET PCI DSS Requirements", False, f"Exception: {str(e)}")
    
    # 5.3 POST tokenize (Visa test card)
    try:
        response = requests.post(
            f"{BASE_URL}/pci-dss/tokenize",
            headers=headers,
            json={
                "card_number": "4111111111111111",  # Visa test card
                "card_holder": "Test User",
                "expiry_month": "12",
                "expiry_year": "2025"
            },
            timeout=30
        )
        results["pci_dss_tokenize"] = response.status_code == 200
        print_result("POST PCI DSS Tokenize (Visa)", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["pci_dss_tokenize"] = False
        print_result("POST PCI DSS Tokenize (Visa)", False, f"Exception: {str(e)}")
    
    # 5.4 GET tokens
    try:
        response = requests.get(f"{BASE_URL}/pci-dss/tokens", headers=headers, timeout=30)
        results["pci_dss_tokens"] = response.status_code == 200
        print_result("GET PCI DSS Tokens", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["pci_dss_tokens"] = False
        print_result("GET PCI DSS Tokens", False, f"Exception: {str(e)}")
    
    # 5.5 POST security scan
    try:
        response = requests.post(f"{BASE_URL}/pci-dss/security-scan", headers=headers, timeout=30)
        results["pci_dss_security_scan"] = response.status_code == 200
        print_result("POST PCI DSS Security Scan", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["pci_dss_security_scan"] = False
        print_result("POST PCI DSS Security Scan", False, f"Exception: {str(e)}")
    
    # 5.6 POST PAN scan
    try:
        response = requests.post(f"{BASE_URL}/pci-dss/pan-scan", headers=headers, timeout=30)
        results["pci_dss_pan_scan"] = response.status_code == 200
        print_result("POST PCI DSS PAN Scan", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["pci_dss_pan_scan"] = False
        print_result("POST PCI DSS PAN Scan", False, f"Exception: {str(e)}")
    
    # 5.7 GET scan history
    try:
        response = requests.get(f"{BASE_URL}/pci-dss/scan-history", headers=headers, timeout=30)
        results["pci_dss_scan_history"] = response.status_code == 200
        print_result("GET PCI DSS Scan History", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["pci_dss_scan_history"] = False
        print_result("GET PCI DSS Scan History", False, f"Exception: {str(e)}")
    
    return results

def test_tenant_isolation(token):
    """Test Tenant Data Isolation Module (6 endpoints) - NEW"""
    print_section("6. TENANT DATA ISOLATION (NEW)")
    
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    
    # 6.1 GET health
    try:
        response = requests.get(f"{BASE_URL}/tenant-isolation/health", headers=headers, timeout=30)
        results["tenant_isolation_health"] = response.status_code == 200
        print_result("GET Tenant Isolation Health", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["tenant_isolation_health"] = False
        print_result("GET Tenant Isolation Health", False, f"Exception: {str(e)}")
    
    # 6.2 GET policy
    try:
        response = requests.get(f"{BASE_URL}/tenant-isolation/policy", headers=headers, timeout=30)
        results["tenant_isolation_policy"] = response.status_code == 200
        print_result("GET Tenant Isolation Policy", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["tenant_isolation_policy"] = False
        print_result("GET Tenant Isolation Policy", False, f"Exception: {str(e)}")
    
    # 6.3 GET data summary
    try:
        response = requests.get(f"{BASE_URL}/tenant-isolation/data-summary", headers=headers, timeout=30)
        results["tenant_isolation_data_summary"] = response.status_code == 200
        print_result("GET Tenant Isolation Data Summary", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["tenant_isolation_data_summary"] = False
        print_result("GET Tenant Isolation Data Summary", False, f"Exception: {str(e)}")
    
    # 6.4 GET data classification
    try:
        response = requests.get(f"{BASE_URL}/tenant-isolation/data-classification", headers=headers, timeout=30)
        results["tenant_isolation_data_classification"] = response.status_code == 200
        print_result("GET Tenant Isolation Data Classification", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["tenant_isolation_data_classification"] = False
        print_result("GET Tenant Isolation Data Classification", False, f"Exception: {str(e)}")
    
    # 6.5 GET PII scan
    try:
        response = requests.get(f"{BASE_URL}/tenant-isolation/pii-scan", headers=headers, timeout=30)
        results["tenant_isolation_pii_scan"] = response.status_code == 200
        print_result("GET Tenant Isolation PII Scan", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["tenant_isolation_pii_scan"] = False
        print_result("GET Tenant Isolation PII Scan", False, f"Exception: {str(e)}")
    
    # 6.6 GET audit trail
    try:
        response = requests.get(f"{BASE_URL}/tenant-isolation/audit-trail", headers=headers, timeout=30)
        results["tenant_isolation_audit_trail"] = response.status_code == 200
        print_result("GET Tenant Isolation Audit Trail", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["tenant_isolation_audit_trail"] = False
        print_result("GET Tenant Isolation Audit Trail", False, f"Exception: {str(e)}")
    
    return results

def test_central_office_dashboard(token):
    """Test Central Office Dashboard V2 (9 endpoints) - ENHANCED"""
    print_section("7. CENTRAL OFFICE DASHBOARD (ENHANCED)")
    
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    
    # 7.1 GET dashboard (should have chain_adr, chain_revpar)
    try:
        response = requests.get(f"{BASE_URL}/central-office/dashboard", headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            has_chain_adr = 'chain_adr' in data
            has_chain_revpar = 'chain_revpar' in data
            results["central_office_dashboard"] = has_chain_adr and has_chain_revpar
            print_result("GET Central Office Dashboard", has_chain_adr and has_chain_revpar, 
                        f"HTTP {response.status_code}, chain_adr: {has_chain_adr}, chain_revpar: {has_chain_revpar}")
        else:
            results["central_office_dashboard"] = False
            print_result("GET Central Office Dashboard", False, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_dashboard"] = False
        print_result("GET Central Office Dashboard", False, f"Exception: {str(e)}")
    
    # 7.2 GET properties
    try:
        response = requests.get(f"{BASE_URL}/central-office/properties", headers=headers, timeout=30)
        results["central_office_properties"] = response.status_code == 200
        print_result("GET Central Office Properties", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_properties"] = False
        print_result("GET Central Office Properties", False, f"Exception: {str(e)}")
    
    # 7.3 GET occupancy comparison
    try:
        response = requests.get(f"{BASE_URL}/central-office/occupancy-comparison", headers=headers, timeout=30)
        results["central_office_occupancy_comparison"] = response.status_code == 200
        print_result("GET Central Office Occupancy Comparison", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_occupancy_comparison"] = False
        print_result("GET Central Office Occupancy Comparison", False, f"Exception: {str(e)}")
    
    # 7.4 GET revenue report (should have chain_adr)
    try:
        response = requests.get(f"{BASE_URL}/central-office/revenue-report", headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            has_chain_adr = 'chain_adr' in data
            results["central_office_revenue_report"] = has_chain_adr
            print_result("GET Central Office Revenue Report", has_chain_adr, 
                        f"HTTP {response.status_code}, chain_adr: {has_chain_adr}")
        else:
            results["central_office_revenue_report"] = False
            print_result("GET Central Office Revenue Report", False, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_revenue_report"] = False
        print_result("GET Central Office Revenue Report", False, f"Exception: {str(e)}")
    
    # 7.5 GET trends (occupancy, 7 days)
    try:
        response = requests.get(f"{BASE_URL}/central-office/trends?metric=occupancy&days=7", headers=headers, timeout=30)
        results["central_office_trends"] = response.status_code == 200
        print_result("GET Central Office Trends", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_trends"] = False
        print_result("GET Central Office Trends", False, f"Exception: {str(e)}")
    
    # 7.6 GET property health
    try:
        response = requests.get(f"{BASE_URL}/central-office/property-health", headers=headers, timeout=30)
        results["central_office_property_health"] = response.status_code == 200
        print_result("GET Central Office Property Health", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_property_health"] = False
        print_result("GET Central Office Property Health", False, f"Exception: {str(e)}")
    
    # 7.7 GET budget tracking
    try:
        response = requests.get(f"{BASE_URL}/central-office/budget-tracking", headers=headers, timeout=30)
        results["central_office_budget_tracking"] = response.status_code == 200
        print_result("GET Central Office Budget Tracking", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_budget_tracking"] = False
        print_result("GET Central Office Budget Tracking", False, f"Exception: {str(e)}")
    
    # 7.8 GET alerts
    try:
        response = requests.get(f"{BASE_URL}/central-office/alerts", headers=headers, timeout=30)
        results["central_office_alerts"] = response.status_code == 200
        print_result("GET Central Office Alerts", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_alerts"] = False
        print_result("GET Central Office Alerts", False, f"Exception: {str(e)}")
    
    # 7.9 GET department comparison
    try:
        response = requests.get(f"{BASE_URL}/central-office/department-comparison", headers=headers, timeout=30)
        results["central_office_department_comparison"] = response.status_code == 200
        print_result("GET Central Office Department Comparison", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["central_office_department_comparison"] = False
        print_result("GET Central Office Department Comparison", False, f"Exception: {str(e)}")
    
    return results

def test_cross_property_guests(token):
    """Test Cross-Property Guest Profiles (2 endpoints)"""
    print_section("8. CROSS-PROPERTY GUESTS")
    
    headers = {"Authorization": f"Bearer {token}"}
    results = {}
    
    # 8.1 GET guest search
    try:
        response = requests.get(f"{BASE_URL}/cross-property/guests/search?query=Misafir", headers=headers, timeout=30)
        results["cross_property_guest_search"] = response.status_code == 200
        print_result("GET Cross-Property Guest Search", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["cross_property_guest_search"] = False
        print_result("GET Cross-Property Guest Search", False, f"Exception: {str(e)}")
    
    # 8.2 GET loyalty summary
    try:
        response = requests.get(f"{BASE_URL}/cross-property/guests/loyalty-summary", headers=headers, timeout=30)
        results["cross_property_loyalty_summary"] = response.status_code == 200
        print_result("GET Cross-Property Loyalty Summary", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["cross_property_loyalty_summary"] = False
        print_result("GET Cross-Property Loyalty Summary", False, f"Exception: {str(e)}")
    
    return results

def test_swagger_docs():
    """Test Swagger Documentation (2 endpoints)"""
    print_section("9. SWAGGER DOCUMENTATION")
    
    results = {}
    
    # 9.1 GET docs
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=30)
        results["swagger_docs"] = response.status_code == 200
        print_result("GET Swagger Docs", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["swagger_docs"] = False
        print_result("GET Swagger Docs", False, f"Exception: {str(e)}")
    
    # 9.2 GET openapi.json
    try:
        response = requests.get(f"{BASE_URL}/openapi.json", timeout=30)
        results["openapi_json"] = response.status_code == 200
        print_result("GET OpenAPI JSON", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as e:
        results["openapi_json"] = False
        print_result("GET OpenAPI JSON", False, f"Exception: {str(e)}")
    
    return results

def print_final_summary(all_results):
    """Print final test summary"""
    print_section("FINAL TEST SUMMARY")
    
    # Flatten all results
    flat_results = {}
    flat_results["login"] = all_results.get("login", False)
    flat_results["auth_me"] = all_results.get("auth_me", False)
    
    # Add all nested results
    for category, results in all_results.items():
        if isinstance(results, dict):
            for test_name, passed in results.items():
                flat_results[test_name] = passed
    
    total_tests = len(flat_results)
    passed_tests = sum(1 for v in flat_results.values() if v)
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {success_rate:.1f}%\n")
    
    # Group results by category
    categories = {
        "Authentication": ["login", "auth_me"],
        "2FA Security": [k for k in flat_results.keys() if k.startswith("2fa_")],
        "IP Access": [k for k in flat_results.keys() if k.startswith("ip_")],
        "GDPR": [k for k in flat_results.keys() if k.startswith("gdpr_")],
        "PCI DSS": [k for k in flat_results.keys() if k.startswith("pci_dss_")],
        "Tenant Isolation": [k for k in flat_results.keys() if k.startswith("tenant_isolation_")],
        "Central Office": [k for k in flat_results.keys() if k.startswith("central_office_")],
        "Cross-Property": [k for k in flat_results.keys() if k.startswith("cross_property_")],
        "Swagger": [k for k in flat_results.keys() if k.startswith("swagger_") or k.startswith("openapi_")]
    }
    
    for category, test_names in categories.items():
        if test_names:
            category_passed = sum(1 for name in test_names if flat_results.get(name, False))
            category_total = len(test_names)
            category_rate = (category_passed / category_total * 100) if category_total > 0 else 0
            print(f"{category}: {category_passed}/{category_total} ({category_rate:.1f}%)")
            
            for test_name in test_names:
                if test_name in flat_results:
                    status = "✅" if flat_results[test_name] else "❌"
                    print(f"  {status} {test_name}")
    
    if success_rate == 100:
        print("\n🎉 ALL TESTS PASSED! RoomOps PMS backend is fully functional!")
    elif success_rate >= 80:
        print(f"\n✅ MOSTLY PASSED ({success_rate:.1f}%)! Most RoomOps features are working.")
    else:
        failed_tests = [name for name, passed in flat_results.items() if not passed]
        print(f"\n⚠️  MULTIPLE FAILURES ({success_rate:.1f}% pass rate)")
        print(f"Failed tests: {', '.join(failed_tests[:10])}{'...' if len(failed_tests) > 10 else ''}")

def main():
    """Main test execution"""
    print("\n" + "="*80)
    print("  ROOMOPS PMS BACKEND TEST SUITE")
    print("  Testing all new and enhanced backend modules")
    print("="*80)
    
    all_results = {}
    
    # Step 1: Authentication
    token = test_login()
    if not token:
        print("\n❌ CRITICAL: Authentication failed. Cannot continue tests.")
        return
    all_results["login"] = True
    
    # Test auth/me endpoint
    all_results["auth_me"] = test_auth_me(token)
    
    # Step 2-9: Test all modules
    all_results["2fa_security"] = test_2fa_security(token)
    all_results["ip_access"] = test_ip_access(token)
    all_results["gdpr_compliance"] = test_gdpr_compliance(token)
    all_results["pci_dss_compliance"] = test_pci_dss_compliance(token)
    all_results["tenant_isolation"] = test_tenant_isolation(token)
    all_results["central_office"] = test_central_office_dashboard(token)
    all_results["cross_property"] = test_cross_property_guests(token)
    all_results["swagger"] = test_swagger_docs()
    
    # Print final summary
    print_final_summary(all_results)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user.")
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()