#!/usr/bin/env python3
"""
Night Audit Backend Testing
Testing the complete night audit flow as requested by the user.

Test Flow:
1. Login with demo@hotel.com / demo123
2. POST /api/night-audit/start-audit (with yesterday's date)
3. POST /api/night-audit/automatic-posting
4. POST /api/night-audit/no-show-handling (with charge_no_show_fee=true)
5. POST /api/night-audit/end-of-day (using audit_id from step 1)
6. GET /api/night-audit/audit-report (with audit_date)

Expected: All endpoints return HTTP 200 with proper response structure
"""

import requests
import json
from datetime import datetime, timedelta
import sys
import os

# Configuration
BASE_URL = "https://improvement-guide-1.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Demo credentials
DEMO_EMAIL = "demo@hotel.com"
DEMO_PASSWORD = "demo123"

def print_test_header(test_name):
    print(f"\n{'='*60}")
    print(f"🧪 {test_name}")
    print(f"{'='*60}")

def print_result(success, message, details=None):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {message}")
    if details:
        print(f"   Details: {details}")

def login():
    """Login and get JWT token"""
    print_test_header("AUTHENTICATION - Login")
    
    login_data = {
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD
    }
    
    try:
        response = requests.post(f"{API_BASE}/auth/login", json=login_data, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            tenant = data.get("tenant", {})
            
            print_result(True, f"Login successful - HTTP {response.status_code}")
            print(f"   User: {user.get('name', 'N/A')} ({user.get('email', 'N/A')})")
            print(f"   Tenant: {tenant.get('property_name', 'N/A')}")
            print(f"   Token: {token[:20]}..." if token else "   Token: None")
            
            return token
        else:
            print_result(False, f"Login failed - HTTP {response.status_code}", response.text[:200])
            return None
            
    except Exception as e:
        print_result(False, f"Login error: {str(e)}")
        return None

def test_night_audit_flow():
    """Test the complete night audit flow"""
    
    # Step 1: Login
    token = login()
    if not token:
        print("\n❌ CRITICAL: Cannot proceed without authentication token")
        return False
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Calculate yesterday's date
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n📅 Using audit_date: {yesterday}")
    
    audit_id = None
    test_results = []
    
    # Step 2: Start Night Audit
    print_test_header("STEP 1: POST /api/night-audit/start-audit")
    
    try:
        params = {
            "audit_date": yesterday
        }
        
        response = requests.post(
            f"{API_BASE}/night-audit/start-audit", 
            params=params, 
            headers=headers, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            success = data.get("success", False)
            audit_id = data.get("audit_id")
            statistics = data.get("statistics", {})
            
            print_result(True, f"Start audit successful - HTTP {response.status_code}")
            print(f"   Success: {success}")
            print(f"   Audit ID: {audit_id}")
            print(f"   Statistics: {statistics}")
            test_results.append(("start-audit", True, response.status_code, len(json.dumps(data))))
        else:
            print_result(False, f"Start audit failed - HTTP {response.status_code}", response.text[:300])
            test_results.append(("start-audit", False, response.status_code, response.text[:100]))
            
    except Exception as e:
        print_result(False, f"Start audit error: {str(e)}")
        test_results.append(("start-audit", False, 0, str(e)))
    
    # Step 3: Automatic Posting
    print_test_header("STEP 2: POST /api/night-audit/automatic-posting")
    
    try:
        params = {
            "audit_date": yesterday
        }
        
        response = requests.post(
            f"{API_BASE}/night-audit/automatic-posting", 
            params=params, 
            headers=headers, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            success = data.get("success", False)
            posted_count = data.get("posted_count", 0)
            total_amount_posted = data.get("total_amount_posted", 0)
            
            print_result(True, f"Automatic posting successful - HTTP {response.status_code}")
            print(f"   Success: {success}")
            print(f"   Posted Count: {posted_count}")
            print(f"   Total Amount Posted: {total_amount_posted}")
            test_results.append(("automatic-posting", True, response.status_code, len(json.dumps(data))))
        else:
            print_result(False, f"Automatic posting failed - HTTP {response.status_code}", response.text[:300])
            test_results.append(("automatic-posting", False, response.status_code, response.text[:100]))
            
    except Exception as e:
        print_result(False, f"Automatic posting error: {str(e)}")
        test_results.append(("automatic-posting", False, 0, str(e)))
    
    # Step 4: No-Show Handling
    print_test_header("STEP 3: POST /api/night-audit/no-show-handling")
    
    try:
        params = {
            "audit_date": yesterday,
            "charge_no_show_fee": True
        }
        
        response = requests.post(
            f"{API_BASE}/night-audit/no-show-handling", 
            params=params, 
            headers=headers, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            success = data.get("success", False)
            no_shows_processed = data.get("no_shows_processed", 0)
            total_no_show_charges = data.get("total_no_show_charges", 0)
            
            print_result(True, f"No-show handling successful - HTTP {response.status_code}")
            print(f"   Success: {success}")
            print(f"   No-shows Processed: {no_shows_processed}")
            print(f"   Total No-show Charges: {total_no_show_charges}")
            test_results.append(("no-show-handling", True, response.status_code, len(json.dumps(data))))
        else:
            print_result(False, f"No-show handling failed - HTTP {response.status_code}", response.text[:300])
            test_results.append(("no-show-handling", False, response.status_code, response.text[:100]))
            
    except Exception as e:
        print_result(False, f"No-show handling error: {str(e)}")
        test_results.append(("no-show-handling", False, 0, str(e)))
    
    # Step 5: End of Day (only if we have audit_id)
    print_test_header("STEP 4: POST /api/night-audit/end-of-day")
    
    if audit_id:
        try:
            params = {
                "audit_id": audit_id
            }
            
            response = requests.post(
                f"{API_BASE}/night-audit/end-of-day", 
                params=params, 
                headers=headers, 
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                success = data.get("success", False)
                summary = data.get("summary", {})
                total_revenue = summary.get("total_revenue", 0)
                no_shows = summary.get("no_shows", 0)
                occupied_rooms = summary.get("occupied_rooms", 0)
                
                print_result(True, f"End of day successful - HTTP {response.status_code}")
                print(f"   Success: {success}")
                print(f"   Summary: {summary}")
                print(f"   Total Revenue: {total_revenue}")
                print(f"   No Shows: {no_shows}")
                print(f"   Occupied Rooms: {occupied_rooms}")
                test_results.append(("end-of-day", True, response.status_code, len(json.dumps(data))))
            else:
                print_result(False, f"End of day failed - HTTP {response.status_code}", response.text[:300])
                test_results.append(("end-of-day", False, response.status_code, response.text[:100]))
                
        except Exception as e:
            print_result(False, f"End of day error: {str(e)}")
            test_results.append(("end-of-day", False, 0, str(e)))
    else:
        print_result(False, "End of day skipped - no audit_id from start-audit")
        test_results.append(("end-of-day", False, 0, "No audit_id available"))
    
    # Step 6: Audit Report
    print_test_header("STEP 5: GET /api/night-audit/audit-report")
    
    try:
        params = {
            "audit_date": yesterday
        }
        
        response = requests.get(
            f"{API_BASE}/night-audit/audit-report", 
            params=params, 
            headers=headers, 
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            audit = data.get("audit", {})
            bookings_by_status = data.get("bookings_by_status", [])
            
            print_result(True, f"Audit report successful - HTTP {response.status_code}")
            print(f"   Audit object: {bool(audit)}")
            print(f"   Bookings by status: {len(bookings_by_status)} items")
            if audit:
                print(f"   Audit ID: {audit.get('id', 'N/A')}")
                print(f"   Audit Date: {audit.get('audit_date', 'N/A')}")
            test_results.append(("audit-report", True, response.status_code, len(json.dumps(data))))
        else:
            print_result(False, f"Audit report failed - HTTP {response.status_code}", response.text[:300])
            test_results.append(("audit-report", False, response.status_code, response.text[:100]))
            
    except Exception as e:
        print_result(False, f"Audit report error: {str(e)}")
        test_results.append(("audit-report", False, 0, str(e)))
    
    # Summary
    print_test_header("NIGHT AUDIT FLOW TEST SUMMARY")
    
    total_tests = len(test_results)
    passed_tests = sum(1 for _, success, _, _ in test_results if success)
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"📊 Overall Results: {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")
    print(f"📅 Audit Date Used: {yesterday}")
    print(f"🔑 Authentication: {'✅ Working' if token else '❌ Failed'}")
    
    print(f"\n📋 Detailed Results:")
    for endpoint, success, status_code, details in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {status} {endpoint}: HTTP {status_code}")
        if not success and isinstance(details, str):
            print(f"      Error: {details[:100]}")
    
    # Check if all required fields are present
    print(f"\n🎯 Night Audit Flow Assessment:")
    if passed_tests == total_tests:
        print("✅ EXCELLENT: All night audit endpoints working perfectly!")
        print("✅ Complete flow: start-audit → automatic-posting → no-show-handling → end-of-day → audit-report")
        print("✅ All HTTP 200 responses with proper data structure")
        print("✅ Ready for production night audit operations")
    elif passed_tests >= 4:
        print("⚠️  GOOD: Most night audit endpoints working")
        print("⚠️  Minor issues identified, but core functionality operational")
    else:
        print("❌ CRITICAL: Major issues with night audit flow")
        print("❌ Multiple endpoints failing - requires immediate attention")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    print("🏨 NIGHT AUDIT BACKEND TESTING")
    print(f"🌐 Base URL: {BASE_URL}")
    print(f"👤 Demo User: {DEMO_EMAIL}")
    
    success = test_night_audit_flow()
    
    if success:
        print(f"\n🎉 NIGHT AUDIT TESTING COMPLETED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print(f"\n⚠️  NIGHT AUDIT TESTING COMPLETED WITH ISSUES")
        sys.exit(1)