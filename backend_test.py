#!/usr/bin/env python3
"""
3-Segment Subscription & Module Management System Backend Test

Tests the following endpoints:
1. POST /api/auth/login - Super admin authentication
2. GET /api/subscription/plans - Get subscription plans (basic, professional, enterprise)
3. GET /api/subscription/plan-modules - Get module defaults per tier
4. GET /api/admin/tenants - List all tenants with subscription info
5. PATCH /api/admin/tenants/{tenant_id}/modules - Toggle modules per tenant
6. PATCH /api/admin/tenants/{tenant_id}/tier - Change subscription tier
7. GET /api/subscription/current - Get current user subscription
"""

import requests
import json
from datetime import datetime
import os

# Configuration from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://guest-unified.preview.emergentagent.com') + '/api'
SUPER_ADMIN_EMAIL = "superadmin@syroce.com"
SUPER_ADMIN_PASSWORD = "Admin123!"

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

def login_super_admin():
    """Login as super admin and return token"""
    print_section("1. SUPER ADMIN LOGIN")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": SUPER_ADMIN_EMAIL,
                "password": SUPER_ADMIN_PASSWORD
            },
            timeout=30
        )
        
        print(f"Request: POST /api/auth/login")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            print_result("Super Admin Login", True, f"User: {user.get('name')}, Role: {user.get('role')}")
            print(f"Token preview: {token[:20]}..." if token else "No token")
            return token
        else:
            print_result("Super Admin Login", False, f"HTTP {response.status_code}: {response.text}")
            return None
            
    except Exception as e:
        print_result("Super Admin Login", False, f"Exception: {str(e)}")
        return None

def test_subscription_plans():
    """Test GET /api/subscription/plans"""
    print_section("2. GET SUBSCRIPTION PLANS")
    
    try:
        response = requests.get(f"{BASE_URL}/subscription/plans", timeout=30)
        
        print(f"Request: GET /api/subscription/plans")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            plans = data.get('plans', [])
            currency = data.get('currency')
            tiers = data.get('tiers', [])
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Has 3 plans": len(plans) == 3,
                "Currency is EUR": currency == "EUR",
                "Has tiers": len(tiers) == 3,
                "Basic plan exists": any(p.get('tier') == 'basic' for p in plans),
                "Professional plan exists": any(p.get('tier') == 'professional' for p in plans),
                "Enterprise plan exists": any(p.get('tier') == 'enterprise' for p in plans),
            }
            
            # Check pricing
            basic_plan = next((p for p in plans if p.get('tier') == 'basic'), None)
            pro_plan = next((p for p in plans if p.get('tier') == 'professional'), None)
            enterprise_plan = next((p for p in plans if p.get('tier') == 'enterprise'), None)
            
            if basic_plan:
                checks["Basic price 79€"] = basic_plan.get('price_monthly') == 79.0
            if pro_plan:
                checks["Professional price 299€"] = pro_plan.get('price_monthly') == 299.0
            if enterprise_plan:
                checks["Enterprise price 799€"] = enterprise_plan.get('price_monthly') == 799.0
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, plans
            
        else:
            print_result("Get Subscription Plans", False, f"HTTP {response.status_code}: {response.text}")
            return False, []
            
    except Exception as e:
        print_result("Get Subscription Plans", False, f"Exception: {str(e)}")
        return False, []

def test_plan_modules():
    """Test GET /api/subscription/plan-modules"""
    print_section("3. GET PLAN MODULE DEFAULTS")
    
    try:
        response = requests.get(f"{BASE_URL}/subscription/plan-modules", timeout=30)
        
        print(f"Request: GET /api/subscription/plan-modules")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            plan_modules = data.get('plan_modules', {})
            tiers = data.get('tiers', [])
            all_module_keys = data.get('all_module_keys', [])
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Has plan_modules": len(plan_modules) > 0,
                "Has basic plan modules": 'basic' in plan_modules,
                "Has professional plan modules": 'professional' in plan_modules,
                "Has enterprise plan modules": 'enterprise' in plan_modules,
                "Has tiers": len(tiers) == 3,
                "Has module keys": len(all_module_keys) > 0,
            }
            
            # Check basic plan has core modules enabled
            basic_modules = plan_modules.get('basic', {})
            if basic_modules:
                checks["Basic has PMS enabled"] = basic_modules.get('pms') == True
                checks["Basic has dashboard enabled"] = basic_modules.get('dashboard') == True
                checks["Basic has channel_manager disabled"] = basic_modules.get('channel_manager') == False
            
            # Check professional plan has more modules
            pro_modules = plan_modules.get('professional', {})
            if pro_modules:
                checks["Professional has PMS enabled"] = pro_modules.get('pms') == True
                checks["Professional has channel_manager enabled"] = pro_modules.get('channel_manager') == True
                checks["Professional has reports enabled"] = pro_modules.get('reports') == True
            
            # Check enterprise plan has all modules
            enterprise_modules = plan_modules.get('enterprise', {})
            if enterprise_modules:
                checks["Enterprise has AI enabled"] = enterprise_modules.get('ai') == True
                checks["Enterprise has revenue_management enabled"] = enterprise_modules.get('revenue_management') == True
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, plan_modules
            
        else:
            print_result("Get Plan Modules", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("Get Plan Modules", False, f"Exception: {str(e)}")
        return False, {}

def test_list_tenants(token):
    """Test GET /api/admin/tenants"""
    print_section("4. GET ADMIN TENANTS")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/admin/tenants", headers=headers, timeout=30)
        
        print(f"Request: GET /api/admin/tenants")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            tenants = data.get('tenants', [])
            
            print(f"Found {len(tenants)} tenants")
            if tenants:
                print("Sample tenant data:")
                print(json.dumps(tenants[0], indent=2))
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Has tenants": len(tenants) > 0,
                "At least 4 tenants": len(tenants) >= 4,
            }
            
            # Check tenant structure
            if tenants:
                sample_tenant = tenants[0]
                checks["Tenant has subscription_tier"] = 'subscription_tier' in sample_tenant
                checks["Tenant has modules"] = 'modules' in sample_tenant
                checks["Tenant has property_name"] = 'property_name' in sample_tenant
                
                # Look for a Basic hotel (specifically Butik Otel Antalya)
                basic_hotel = None
                for tenant in tenants:
                    if tenant.get('subscription_tier') == 'basic' or 'Butik' in tenant.get('property_name', ''):
                        basic_hotel = tenant
                        break
                
                if basic_hotel:
                    checks["Found Basic hotel"] = True
                    print(f"Found Basic hotel: {basic_hotel.get('property_name')} (ID: {basic_hotel.get('id')})")
                else:
                    checks["Found Basic hotel"] = False
                    print("Available hotels:")
                    for tenant in tenants[:5]:  # Show first 5
                        print(f"  - {tenant.get('property_name')} (tier: {tenant.get('subscription_tier', 'unknown')})")
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, tenants
            
        else:
            print_result("Get Admin Tenants", False, f"HTTP {response.status_code}: {response.text}")
            return False, []
            
    except Exception as e:
        print_result("Get Admin Tenants", False, f"Exception: {str(e)}")
        return False, []

def test_change_tier(token, tenant_id, new_tier="professional", reset_modules=True):
    """Test PATCH /api/admin/tenants/{tenant_id}/tier"""
    print_section(f"5. CHANGE SUBSCRIPTION TIER TO {new_tier.upper()}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "tier": new_tier,
            "reset_modules": reset_modules
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
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Success message": data.get('success') == True,
                "Tenant returned": 'tenant' in data,
                f"Tier changed to {new_tier}": tenant.get('subscription_tier') == new_tier,
                "Modules field exists": 'modules' in tenant,
            }
            
            # Check modules were reset to professional defaults
            if new_tier == "professional" and tenant.get('modules'):
                modules = tenant.get('modules', {})
                checks["PMS still enabled"] = modules.get('pms') == True
                checks["Channel manager now enabled"] = modules.get('channel_manager') == True
                checks["Reports now enabled"] = modules.get('reports') == True
                checks["AI still disabled (pro tier)"] = modules.get('ai') == False
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, tenant
            
        else:
            print_result("Change Subscription Tier", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("Change Subscription Tier", False, f"Exception: {str(e)}")
        return False, {}

def test_toggle_module(token, tenant_id, module_name="invoices", enable=True):
    """Test PATCH /api/admin/tenants/{tenant_id}/modules"""
    print_section(f"6. TOGGLE MODULE ({module_name} = {enable})")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # First get current modules
        tenants_response = requests.get(f"{BASE_URL}/admin/tenants", headers=headers, timeout=30)
        if tenants_response.status_code == 200:
            tenants = tenants_response.json().get('tenants', [])
            current_tenant = next((t for t in tenants if t.get('id') == tenant_id), None)
            if current_tenant:
                current_modules = current_tenant.get('modules', {})
                # Toggle the specific module
                new_modules = current_modules.copy()
                new_modules[module_name] = enable
                
                payload = {
                    "modules": new_modules
                }
                
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
                    modules = data.get('modules', {})
                    
                    print(f"Response: {json.dumps(data, indent=2)}")
                    
                    checks = {
                        "HTTP 200": response.status_code == 200,
                        "Modules field exists": 'modules' in data,
                        f"{module_name} = {enable}": modules.get(module_name) == enable,
                    }
                    
                    all_passed = all(checks.values())
                    for check, passed in checks.items():
                        print_result(check, passed)
                    
                    return all_passed, data
                else:
                    print_result("Toggle Module", False, f"HTTP {response.status_code}: {response.text}")
                    return False, {}
            else:
                print_result("Find tenant for module toggle", False, f"Tenant {tenant_id} not found")
                return False, {}
        else:
            print_result("Get current tenant modules", False, f"HTTP {tenants_response.status_code}")
            return False, {}
            
    except Exception as e:
        print_result("Toggle Module", False, f"Exception: {str(e)}")
        return False, {}

def test_current_subscription(token):
    """Test GET /api/subscription/current"""
    print_section("7. GET CURRENT SUBSCRIPTION")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/subscription/current", headers=headers, timeout=30)
        
        print(f"Request: GET /api/subscription/current")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": response.status_code == 200,
                "Has plan field": 'plan' in data or 'tier' in data,
                "Has modules field": 'modules' in data,
            }
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result("Get Current Subscription", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("Get Current Subscription", False, f"Exception: {str(e)}")
        return False, {}

def verify_final_state(token, tenant_id):
    """Verify final tenant state after all changes"""
    print_section("8. VERIFY FINAL TENANT STATE")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/admin/tenants", headers=headers, timeout=30)
        
        if response.status_code == 200:
            tenants = response.json().get('tenants', [])
            target_tenant = next((t for t in tenants if t.get('id') == tenant_id), None)
            
            if target_tenant:
                print(f"Final tenant state: {json.dumps(target_tenant, indent=2)}")
                
                checks = {
                    "Tenant found": True,
                    "Is professional tier": target_tenant.get('subscription_tier') == 'professional',
                    "Has modules": 'modules' in target_tenant,
                    "PMS enabled": target_tenant.get('modules', {}).get('pms') == True,
                    "Channel manager enabled": target_tenant.get('modules', {}).get('channel_manager') == True,
                    "Reports enabled": target_tenant.get('modules', {}).get('reports') == True,
                }
                
                all_passed = all(checks.values())
                for check, passed in checks.items():
                    print_result(check, passed)
                
                return all_passed
            else:
                print_result("Find target tenant", False, f"Tenant {tenant_id} not found")
                return False
        else:
            print_result("Get tenants for verification", False, f"HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print_result("Verify Final State", False, f"Exception: {str(e)}")
        return False

def main():
    """Main test execution following the test flow specified in the review request"""
    print("\n" + "="*80)
    print("  3-SEGMENT SUBSCRIPTION & MODULE MANAGEMENT BACKEND TEST")
    print("  Testing subscription plans, module defaults, and tenant management")
    print("="*80)
    
    results = {
        "super_admin_login": False,
        "get_subscription_plans": False,
        "get_plan_modules": False,
        "list_tenants": False,
        "change_tier": False,
        "toggle_module": False,
        "current_subscription": False,
        "verify_final_state": False,
    }
    
    # Step 1: Login as superadmin
    token = login_super_admin()
    if not token:
        print("\n❌ CRITICAL: Super admin login failed. Cannot continue tests.")
        print_final_summary(results)
        return
    results["super_admin_login"] = True
    
    # Step 2: GET /api/subscription/plans → verify 3 tiers
    plans_success, plans = test_subscription_plans()
    results["get_subscription_plans"] = plans_success
    
    # Step 3: GET /api/subscription/plan-modules → verify module defaults
    modules_success, plan_modules = test_plan_modules()
    results["get_plan_modules"] = modules_success
    
    # Step 4: GET /api/admin/tenants → find the Basic hotel (Butik Otel Antalya)
    tenants_success, tenants = test_list_tenants(token)
    results["list_tenants"] = tenants_success
    
    if not tenants:
        print("\n❌ CRITICAL: No tenants found. Cannot continue tenant-specific tests.")
        print_final_summary(results)
        return
    
    # Find a basic hotel to test with
    basic_hotel = None
    for tenant in tenants:
        # Look for basic tier or specifically named hotel
        if tenant.get('subscription_tier') == 'basic' or 'Butik' in tenant.get('property_name', ''):
            basic_hotel = tenant
            break
    
    # If no basic hotel, use first available tenant
    if not basic_hotel and tenants:
        basic_hotel = tenants[0]
        print(f"⚠️  No basic tier hotel found. Using first available: {basic_hotel.get('property_name')}")
    
    if not basic_hotel:
        print("\n❌ CRITICAL: No suitable hotel found for testing. Cannot continue.")
        print_final_summary(results)
        return
    
    tenant_id = basic_hotel.get('id')
    print(f"Using hotel for testing: {basic_hotel.get('property_name')} (ID: {tenant_id})")
    
    # Step 5: PATCH /api/admin/tenants/{basic_hotel_id}/tier → change to professional
    tier_success, updated_tenant = test_change_tier(token, tenant_id, "professional", True)
    results["change_tier"] = tier_success
    
    # Step 6: PATCH /api/admin/tenants/{basic_hotel_id}/modules → toggle a module manually
    module_success, _ = test_toggle_module(token, tenant_id, "invoices", True)
    results["toggle_module"] = module_success
    
    # Step 7: GET /api/subscription/current → return current user's subscription with modules
    current_success, current_data = test_current_subscription(token)
    results["current_subscription"] = current_success
    
    # Step 8: GET /api/admin/tenants → verify the hotel is now professional with correct modules
    verify_success = verify_final_state(token, tenant_id)
    results["verify_final_state"] = verify_success
    
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
    
    for test_name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {test_name.replace('_', ' ').title()}")
    
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED! 3-segment subscription system is working correctly!")
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