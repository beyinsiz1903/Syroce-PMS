#!/usr/bin/env python3
"""
User Role Management Endpoint Testing
Tests admin user role management endpoints for super admin functionality
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://improvement-guide-1.preview.emergentagent.com/api"
SUPER_ADMIN_EMAIL = "demo@hotel.com"
SUPER_ADMIN_PASSWORD = "demo123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_test(message, status="info"):
    colors = {"success": Colors.GREEN, "error": Colors.RED, "info": Colors.BLUE, "warning": Colors.YELLOW}
    color = colors.get(status, Colors.BLUE)
    symbol = {"success": "✅", "error": "❌", "info": "ℹ️", "warning": "⚠️"}
    print(f"{color}{symbol.get(status, 'ℹ️')} {message}{Colors.END}")

def login(email, password):
    """Login and get JWT token"""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            print_test(f"Login successful: {user.get('name')} ({user.get('role')})", "success")
            return token
        else:
            print_test(f"Login failed: HTTP {response.status_code}", "error")
            return None
    except Exception as e:
        print_test(f"Login error: {str(e)}", "error")
        return None

def test_list_all_users(token):
    """Test 1: List all users"""
    print_test("\n=== TEST 1: List All Users ===", "info")
    
    try:
        response = requests.get(
            f"{BASE_URL}/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print_test(f"Status Code: {response.status_code}", "info")
        
        if response.status_code == 200:
            data = response.json()
            users = data.get("users", [])
            count = data.get("count", 0)
            
            print_test(f"Total users: {count}", "success")
            print_test(f"Users returned: {len(users)}", "success")
            
            # Display first 3 users
            for i, user in enumerate(users[:3], 1):
                print_test(f"  User {i}: {user.get('email')} - {user.get('role')}", "info")
            
            return True, users
        else:
            print_test(f"Failed: HTTP {response.status_code} - {response.text}", "error")
            return False, []
            
    except Exception as e:
        print_test(f"Error: {str(e)}", "error")
        return False, []

def test_filter_users_by_email(token, email_filter):
    """Test 2: Filter users by email"""
    print_test(f"\n=== TEST 2: Filter Users by Email (filter='{email_filter}') ===", "info")
    
    try:
        response = requests.get(
            f"{BASE_URL}/admin/users",
            params={"email_filter": email_filter},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print_test(f"Status Code: {response.status_code}", "info")
        
        if response.status_code == 200:
            data = response.json()
            users = data.get("users", [])
            count = data.get("count", 0)
            
            print_test(f"Filtered users count: {count}", "success")
            
            # Display filtered users
            for user in users:
                print_test(f"  Found: {user.get('email')} - {user.get('role')} - ID: {user.get('id')}", "info")
            
            return True, users
        else:
            print_test(f"Failed: HTTP {response.status_code} - {response.text}", "error")
            return False, []
            
    except Exception as e:
        print_test(f"Error: {str(e)}", "error")
        return False, []

def test_update_user_role(token, user_id, new_role, user_email):
    """Test 3 & 4: Update user role"""
    print_test(f"\n=== TEST: Update User Role to '{new_role}' ===", "info")
    print_test(f"User ID: {user_id}", "info")
    print_test(f"User Email: {user_email}", "info")
    
    try:
        response = requests.patch(
            f"{BASE_URL}/admin/users/{user_id}/role",
            json={"role": new_role},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print_test(f"Status Code: {response.status_code}", "info")
        
        if response.status_code == 200:
            data = response.json()
            print_test(f"Success: {data.get('message')}", "success")
            print_test(f"Old Role: {data.get('old_role')}", "info")
            print_test(f"New Role: {data.get('new_role')}", "success")
            return True
        else:
            print_test(f"Failed: HTTP {response.status_code} - {response.text}", "error")
            return False
            
    except Exception as e:
        print_test(f"Error: {str(e)}", "error")
        return False

def main():
    print_test("=" * 80, "info")
    print_test("USER ROLE MANAGEMENT ENDPOINT TESTING", "info")
    print_test("=" * 80, "info")
    print_test(f"Base URL: {BASE_URL}", "info")
    print_test(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "info")
    
    # Step 1: Super Admin Login
    print_test("\n=== STEP 1: Super Admin Login ===", "info")
    token = login(SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)
    
    if not token:
        print_test("Cannot proceed without authentication", "error")
        sys.exit(1)
    
    # Step 2: List all users
    success_list, all_users = test_list_all_users(token)
    
    # Step 3: Filter users by email (demo)
    success_filter_demo, demo_users = test_filter_users_by_email(token, "demo")
    
    # Step 4: Filter users by email (feith)
    success_filter_feith, feith_users = test_filter_users_by_email(token, "feith")
    
    # Step 5: Update user role to supervisor
    if feith_users:
        target_user = feith_users[0]
        user_id = target_user.get("id")
        user_email = target_user.get("email")
        
        if user_id:
            success_update_supervisor = test_update_user_role(token, user_id, "supervisor", user_email)
            
            # Step 6: Update back to admin
            if success_update_supervisor:
                success_update_admin = test_update_user_role(token, user_id, "admin", user_email)
            else:
                success_update_admin = False
        else:
            print_test("No user ID found for feith user", "error")
            success_update_supervisor = False
            success_update_admin = False
    else:
        print_test("No users found with 'feith' in email", "warning")
        success_update_supervisor = False
        success_update_admin = False
    
    # Summary
    print_test("\n" + "=" * 80, "info")
    print_test("TEST SUMMARY", "info")
    print_test("=" * 80, "info")
    
    tests = [
        ("Super Admin Login", token is not None),
        ("List All Users", success_list),
        ("Filter Users by Email (demo)", success_filter_demo),
        ("Filter Users by Email (feith)", success_filter_feith),
        ("Update User Role to Supervisor", success_update_supervisor),
        ("Update User Role back to Admin", success_update_admin),
    ]
    
    passed = sum(1 for _, result in tests if result)
    total = len(tests)
    
    for test_name, result in tests:
        status = "success" if result else "error"
        print_test(f"{test_name}: {'PASSED' if result else 'FAILED'}", status)
    
    print_test(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.1f}%)", 
               "success" if passed == total else "warning")
    
    if passed == total:
        print_test("\n🎉 ALL TESTS PASSED - User role management endpoints working correctly!", "success")
        return 0
    else:
        print_test(f"\n⚠️ {total - passed} test(s) failed", "error")
        return 1

if __name__ == "__main__":
    sys.exit(main())
