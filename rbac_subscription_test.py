#!/usr/bin/env python3
"""
Enhanced 3-Segment Subscription System with RBAC Backend Test

Tests the specific endpoints and credentials mentioned in the review request:

Test Credentials:
- Super Admin: superadmin@syroce.com / Admin123!
- Basic hotel: demo@butikotel.com / demo123
- Professional: demo@grandcity.com / demo123
- Enterprise: demo@rixos.com / demo123

Test Endpoints:
1. GET /api/rbac/roles (as different user types)
2. GET /api/subscription/current (as different user types)
3. GET /api/subscription/plan-modules
4. Module toggle test as super admin
5. Plan change test as super admin
"""

import requests
import json
from datetime import datetime
import os

# Configuration
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pms-feature-test.preview.emergentagent.com') + '/api'

# Test Credentials from review request
CREDENTIALS = {
    'super_admin': {
        'email': 'superadmin@syroce.com',
        'password': 'Admin123!',
        'expected_tier': 'enterprise'  # Super admin typically has enterprise access
    },
    'basic': {
        'email': 'demo@butikotel.com',
        'password': 'demo123',
        'expected_tier': 'basic',
        'expected_roles': ['admin']
    },
    'professional': {
        'email': 'demo@grandcity.com',
        'password': 'demo123',
        'expected_tier': 'professional',
        'expected_roles': ['admin', 'supervisor', 'front_desk', 'housekeeping', 'finance']
    },
    'enterprise': {
        'email': 'demo@rixos.com',
        'password': 'demo123',
        'expected_tier': 'enterprise',
        'expected_roles': ['admin', 'supervisor', 'front_desk', 'housekeeping', 'finance', 'sales', 'revenue', 'maintenance', 'fnb', 'spa', 'concierge', 'night_auditor', 'staff']
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

def login_user(user_type):
    """Login as specified user type and return token and user data"""
    creds = CREDENTIALS.get(user_type)
    if not creds:
        print_result(f"Login {user_type}", False, "Invalid user type")
        return None, None
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": creds['email'],
                "password": creds['password']
            },
            timeout=30
        )
        
        print(f"Request: POST /api/auth/login (as {user_type})")
        print(f"Email: {creds['email']}")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            tenant = data.get("tenant", {})
            
            print_result(f"Login {user_type}", True, 
                        f"User: {user.get('name')}, Role: {user.get('role')}, Tenant: {tenant.get('property_name', 'N/A')}")
            
            return token, {"user": user, "tenant": tenant}
        else:
            print_result(f"Login {user_type}", False, 
                        f"HTTP {response.status_code}: {response.text}")
            return None, None
            
    except Exception as e:
        print_result(f"Login {user_type}", False, f"Exception: {str(e)}")
        return None, None

def test_rbac_roles(user_type, token):
    """Test GET /api/rbac/roles for specific user type"""
    print_section(f"RBAC ROLES TEST - {user_type.upper()}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/rbac/roles", headers=headers, timeout=30)
        
        print(f"Request: GET /api/rbac/roles (as {user_type})")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            tier = data.get('tier')
            allowed_roles = data.get('allowed_roles', [])
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            creds = CREDENTIALS.get(user_type, {})
            expected_tier = creds.get('expected_tier')
            expected_roles = creds.get('expected_roles', [])
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Has tier field": tier is not None,
                "Has allowed_roles field": allowed_roles is not None,
            }
            
            if expected_tier:
                checks[f"Tier is {expected_tier}"] = tier == expected_tier
            
            if expected_roles:
                for role in expected_roles:
                    checks[f"Has {role} role"] = role in allowed_roles
                
                # Check Basic hotel only has admin role
                if user_type == 'basic':
                    checks["Basic has only admin role"] = len(allowed_roles) == 1 and allowed_roles[0] == 'admin'
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result(f"RBAC roles {user_type}", False, 
                        f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result(f"RBAC roles {user_type}", False, f"Exception: {str(e)}")
        return False, {}

def test_subscription_current(user_type, token):
    """Test GET /api/subscription/current for specific user type"""
    print_section(f"SUBSCRIPTION CURRENT TEST - {user_type.upper()}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/subscription/current", headers=headers, timeout=30)
        
        print(f"Request: GET /api/subscription/current (as {user_type})")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            tier = data.get('tier')
            plan = data.get('plan', {})
            modules = data.get('modules', {})
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            creds = CREDENTIALS.get(user_type, {})
            expected_tier = creds.get('expected_tier')
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Has tier field": tier is not None,
                "Has plan field": plan is not None,
                "Has modules field": modules is not None,
            }
            
            if expected_tier:
                checks[f"Tier is {expected_tier}"] = tier == expected_tier
            
            # Count enabled modules by tier
            enabled_modules = sum(1 for v in modules.values() if v is True)
            
            if user_type == 'basic':
                checks["Basic has ~9 modules enabled"] = 7 <= enabled_modules <= 12  # Allow some variance
            elif user_type == 'professional':
                checks["Professional has ~19 modules enabled"] = 15 <= enabled_modules <= 25  # Allow some variance
            elif user_type == 'enterprise':
                checks["Enterprise has ~38 modules enabled"] = 30 <= enabled_modules <= 45  # Allow some variance
            
            print(f"Enabled modules count: {enabled_modules}")
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result(f"Subscription current {user_type}", False, 
                        f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result(f"Subscription current {user_type}", False, f"Exception: {str(e)}")
        return False, {}

def test_plan_modules():
    """Test GET /api/subscription/plan-modules"""
    print_section("PLAN MODULES TEST")
    
    try:
        response = requests.get(f"{BASE_URL}/subscription/plan-modules", timeout=30)
        
        print(f"Request: GET /api/subscription/plan-modules")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            plan_modules = data.get('plan_modules', {})
            tiers = data.get('tiers', [])
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Has plan_modules": len(plan_modules) > 0,
                "Has all 3 tiers": len(tiers) == 3,
                "Has basic tier": 'basic' in plan_modules,
                "Has professional tier": 'professional' in plan_modules,
                "Has enterprise tier": 'enterprise' in plan_modules,
            }
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result("Plan modules", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("Plan modules", False, f"Exception: {str(e)}")
        return False, {}

def test_module_toggle_as_super_admin(super_admin_token):
    """Test module toggle as super admin"""
    print_section("MODULE TOGGLE TEST (Super Admin)")
    
    try:
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # First, get list of tenants to find Basic hotel
        tenants_response = requests.get(f"{BASE_URL}/admin/tenants", headers=headers, timeout=30)
        
        if tenants_response.status_code != 200:
            print_result("Get tenants for module toggle", False, f"HTTP {tenants_response.status_code}")
            return False, {}
        
        tenants = tenants_response.json().get('tenants', [])
        
        # Find Basic hotel tenant
        basic_tenant = None
        for tenant in tenants:
            # Look for the demo basic hotel or first basic tier hotel
            if (tenant.get('subscription_tier') == 'basic' or 
                'demo@butikotel.com' in str(tenant) or
                'Butik' in tenant.get('property_name', '')):
                basic_tenant = tenant
                break
        
        if not basic_tenant:
            # Use first tenant if no basic found
            basic_tenant = tenants[0] if tenants else None
        
        if not basic_tenant:
            print_result("Find Basic tenant for module toggle", False, "No tenant found")
            return False, {}
        
        tenant_id = basic_tenant.get('id')
        print(f"Testing module toggle on: {basic_tenant.get('property_name')} (ID: {tenant_id})")
        
        # Test toggling channel_manager to True (should work even if not in Basic plan)
        current_modules = basic_tenant.get('modules', {})
        new_modules = current_modules.copy()
        new_modules['channel_manager'] = True
        
        payload = {"modules": new_modules}
        
        response = requests.patch(
            f"{BASE_URL}/admin/tenants/{tenant_id}/modules",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Request: PATCH /api/admin/tenants/{tenant_id}/modules")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            updated_modules = data.get('modules', {})
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Modules field exists": 'modules' in data,
                "Channel manager toggled on": updated_modules.get('channel_manager') == True,
            }
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result("Module toggle", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("Module toggle", False, f"Exception: {str(e)}")
        return False, {}

def test_plan_change_as_super_admin(super_admin_token):
    """Test plan change as super admin"""
    print_section("PLAN CHANGE TEST (Super Admin)")
    
    try:
        headers = {"Authorization": f"Bearer {super_admin_token}"}
        
        # Get list of tenants to find Basic hotel
        tenants_response = requests.get(f"{BASE_URL}/admin/tenants", headers=headers, timeout=30)
        
        if tenants_response.status_code != 200:
            print_result("Get tenants for plan change", False, f"HTTP {tenants_response.status_code}")
            return False, {}
        
        tenants = tenants_response.json().get('tenants', [])
        
        # Find Basic hotel tenant
        basic_tenant = None
        for tenant in tenants:
            if (tenant.get('subscription_tier') == 'basic' or 
                'demo@butikotel.com' in str(tenant) or
                'Butik' in tenant.get('property_name', '')):
                basic_tenant = tenant
                break
        
        if not basic_tenant:
            basic_tenant = tenants[0] if tenants else None
        
        if not basic_tenant:
            print_result("Find Basic tenant for plan change", False, "No tenant found")
            return False, {}
        
        tenant_id = basic_tenant.get('id')
        print(f"Testing plan change on: {basic_tenant.get('property_name')} (ID: {tenant_id})")
        
        # Test 1: Change Basic to Professional
        print("\n--- Step 1: Change Basic → Professional ---")
        
        payload = {
            "tier": "professional",
            "reset_modules": True
        }
        
        response = requests.patch(
            f"{BASE_URL}/admin/tenants/{tenant_id}/tier",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Request: PATCH /api/admin/tenants/{tenant_id}/tier")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            tenant = data.get('tenant', {})
            modules = tenant.get('modules', {})
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            enabled_modules = sum(1 for v in modules.values() if v is True)
            
            checks_1 = {
                "HTTP 200": response.status_code == 200,
                "Tier changed to professional": tenant.get('subscription_tier') == 'professional',
                "Professional modules enabled": enabled_modules >= 15,  # Professional should have ~19 modules
                "Channel manager enabled": modules.get('channel_manager') == True,
                "Reports enabled": modules.get('reports') == True,
            }
            
            all_passed_1 = all(checks_1.values())
            for check, passed in checks_1.items():
                print_result(check, passed)
            
            # Test 2: Change Professional back to Basic
            print("\n--- Step 2: Change Professional → Basic ---")
            
            payload_2 = {
                "tier": "basic",
                "reset_modules": True
            }
            
            response_2 = requests.patch(
                f"{BASE_URL}/admin/tenants/{tenant_id}/tier",
                json=payload_2,
                headers=headers,
                timeout=30
            )
            
            print(f"Request: PATCH /api/admin/tenants/{tenant_id}/tier")
            print(f"Payload: {json.dumps(payload_2, indent=2)}")
            print(f"Response Status: HTTP {response_2.status_code}")
            
            if response_2.status_code == 200:
                data_2 = response_2.json()
                tenant_2 = data_2.get('tenant', {})
                modules_2 = tenant_2.get('modules', {})
                
                print(f"Response: {json.dumps(data_2, indent=2)}")
                
                enabled_modules_2 = sum(1 for v in modules_2.values() if v is True)
                
                checks_2 = {
                    "HTTP 200": response_2.status_code == 200,
                    "Tier changed back to basic": tenant_2.get('subscription_tier') == 'basic',
                    "Basic modules enabled": enabled_modules_2 <= 12,  # Basic should have ~9 modules
                    "Channel manager disabled": modules_2.get('channel_manager') == False,
                    "AI disabled": modules_2.get('ai') == False,
                }
                
                all_passed_2 = all(checks_2.values())
                for check, passed in checks_2.items():
                    print_result(check, passed)
                
                return all_passed_1 and all_passed_2, {"step_1": data, "step_2": data_2}
            else:
                print_result("Plan change back to basic", False, f"HTTP {response_2.status_code}: {response_2.text}")
                return False, {}
        else:
            print_result("Plan change to professional", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("Plan change", False, f"Exception: {str(e)}")
        return False, {}

def main():
    """Main test execution following the review request specification"""
    print("\n" + "="*80)
    print("  ENHANCED 3-SEGMENT SUBSCRIPTION SYSTEM WITH RBAC TEST")
    print("  Testing tier-based role access and subscription features")
    print("="*80)
    
    results = {}
    tokens = {}
    
    # Step 1: Login all users and collect tokens
    print_section("USER AUTHENTICATION")
    
    for user_type in ['super_admin', 'basic', 'professional', 'enterprise']:
        token, user_data = login_user(user_type)
        tokens[user_type] = token
        results[f"login_{user_type}"] = token is not None
        
        if not token:
            print(f"⚠️  Failed to login {user_type}, skipping related tests")
    
    # Step 2: Test RBAC roles for each user type
    print_section("RBAC ROLES TESTING")
    
    for user_type in ['basic', 'professional', 'enterprise']:
        if tokens.get(user_type):
            success, data = test_rbac_roles(user_type, tokens[user_type])
            results[f"rbac_roles_{user_type}"] = success
        else:
            results[f"rbac_roles_{user_type}"] = False
    
    # Step 3: Test subscription current for each user type  
    print_section("SUBSCRIPTION CURRENT TESTING")
    
    for user_type in ['basic', 'professional', 'enterprise']:
        if tokens.get(user_type):
            success, data = test_subscription_current(user_type, tokens[user_type])
            results[f"subscription_current_{user_type}"] = success
        else:
            results[f"subscription_current_{user_type}"] = False
    
    # Step 4: Test plan-modules endpoint
    success, data = test_plan_modules()
    results["plan_modules"] = success
    
    # Step 5: Test module toggle as super admin
    if tokens.get('super_admin'):
        success, data = test_module_toggle_as_super_admin(tokens['super_admin'])
        results["module_toggle"] = success
    else:
        results["module_toggle"] = False
    
    # Step 6: Test plan change as super admin
    if tokens.get('super_admin'):
        success, data = test_plan_change_as_super_admin(tokens['super_admin'])
        results["plan_change"] = success
    else:
        results["plan_change"] = False
    
    # Print final summary
    print_final_summary(results)

def print_final_summary(results):
    """Print final test summary"""
    print_section("FINAL TEST SUMMARY")
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {success_rate:.1f}%\n")
    
    # Group results by category
    categories = {
        "Authentication": [k for k in results.keys() if k.startswith('login_')],
        "RBAC Roles": [k for k in results.keys() if k.startswith('rbac_roles_')],
        "Subscription Current": [k for k in results.keys() if k.startswith('subscription_current_')],
        "Admin Operations": [k for k in results.keys() if k in ['plan_modules', 'module_toggle', 'plan_change']]
    }
    
    for category, tests in categories.items():
        print(f"\n{category}:")
        for test in tests:
            status = "✅" if results.get(test) else "❌"
            print(f"  {status} {test.replace('_', ' ').title()}")
    
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED! Enhanced RBAC subscription system is working correctly!")
    else:
        failed_tests = [name for name, passed in results.items() if not passed]
        print(f"\n⚠️  FAILED TESTS: {', '.join(failed_tests)}")
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