#!/usr/bin/env python3
"""
Housekeeping Dashboard Endpoints Test
Tests newly added endpoints for Housekeeping Dashboard
"""

import requests
import json
from datetime import datetime

# Configuration
BASE_URL = "https://error-sweep-audit.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

def login():
    """Login and get JWT token"""
    print("🔐 Logging in...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get('access_token')
        user = data.get('user', {})
        print(f"✅ Login successful: {user.get('name')} ({user.get('email')})")
        print(f"   Tenant ID: {user.get('tenant_id')}")
        return token
    else:
        print(f"❌ Login failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return None

def test_room_status_report(token):
    """Test GET /api/housekeeping/room-status-report"""
    print("\n" + "="*80)
    print("TEST 1: GET /api/housekeeping/room-status-report")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(
            f"{BASE_URL}/housekeeping/room-status-report",
            headers=headers,
            timeout=15
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ HTTP 200 - Success")
            
            # Verify structure
            errors = []
            
            # Check summary object
            if 'summary' not in data:
                errors.append("❌ Missing 'summary' object")
            else:
                summary = data['summary']
                required_summary_fields = ['total_rooms', 'occupied', 'vacant_clean', 'vacant_dirty', 'out_of_order', 'out_of_service']
                for field in required_summary_fields:
                    if field not in summary:
                        errors.append(f"❌ Missing 'summary.{field}'")
                
                if not errors:
                    print(f"✅ Summary object structure correct:")
                    print(f"   - total_rooms: {summary.get('total_rooms')}")
                    print(f"   - occupied: {summary.get('occupied')}")
                    print(f"   - vacant_clean: {summary.get('vacant_clean')}")
                    print(f"   - vacant_dirty: {summary.get('vacant_dirty')}")
                    print(f"   - out_of_order: {summary.get('out_of_order')}")
                    print(f"   - out_of_service: {summary.get('out_of_service')}")
            
            # Check dnd_rooms array
            if 'dnd_rooms' not in data:
                errors.append("❌ Missing 'dnd_rooms' array")
            else:
                dnd_rooms = data['dnd_rooms']
                print(f"✅ dnd_rooms array present: {len(dnd_rooms)} items")
                
                if len(dnd_rooms) > 0:
                    # Check first item structure
                    first_dnd = dnd_rooms[0]
                    required_dnd_fields = ['room', 'guest', 'dnd_since', 'duration_hours']
                    for field in required_dnd_fields:
                        if field not in first_dnd:
                            errors.append(f"❌ DND room missing field '{field}'")
                    
                    if not any(f"DND room missing field" in e for e in errors):
                        print(f"   ✅ DND room structure correct:")
                        print(f"      - room: {first_dnd.get('room')}")
                        print(f"      - guest: {first_dnd.get('guest')}")
                        print(f"      - dnd_since: {first_dnd.get('dnd_since')}")
                        print(f"      - duration_hours: {first_dnd.get('duration_hours')}")
                else:
                    print(f"   ℹ️  No DND rooms (empty array is acceptable)")
            
            # Check sleep_out array
            if 'sleep_out' not in data:
                errors.append("❌ Missing 'sleep_out' array")
            else:
                sleep_out = data['sleep_out']
                print(f"✅ sleep_out array present: {len(sleep_out)} items")
                
                if len(sleep_out) > 0:
                    # Check first item structure
                    first_sleep = sleep_out[0]
                    required_sleep_fields = ['room', 'guest', 'last_activity', 'status']
                    for field in required_sleep_fields:
                        if field not in first_sleep:
                            errors.append(f"❌ Sleep out room missing field '{field}'")
                    
                    if not any(f"Sleep out room missing field" in e for e in errors):
                        print(f"   ✅ Sleep out structure correct:")
                        print(f"      - room: {first_sleep.get('room')}")
                        print(f"      - guest: {first_sleep.get('guest')}")
                        print(f"      - last_activity: {first_sleep.get('last_activity')}")
                        print(f"      - status: {first_sleep.get('status')}")
                else:
                    print(f"   ℹ️  No sleep out rooms (empty array is acceptable)")
            
            # Check out_of_order array
            if 'out_of_order' not in data:
                errors.append("❌ Missing 'out_of_order' array")
            else:
                out_of_order = data['out_of_order']
                print(f"✅ out_of_order array present: {len(out_of_order)} items")
                
                if len(out_of_order) > 0:
                    print(f"   ℹ️  First OOO room: {out_of_order[0]}")
                else:
                    print(f"   ℹ️  No out of order rooms (empty array is acceptable)")
            
            # Print full response for verification
            print(f"\n📋 Full Response:")
            print(json.dumps(data, indent=2))
            
            # Final verdict
            if errors:
                print(f"\n❌ TEST FAILED - Structure issues found:")
                for error in errors:
                    print(f"   {error}")
                return False
            else:
                print(f"\n✅ TEST PASSED - All structure requirements met")
                return True
        else:
            print(f"❌ HTTP {response.status_code} - Failed")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        return False

def test_staff_performance_detailed(token):
    """Test GET /api/housekeeping/staff-performance-detailed"""
    print("\n" + "="*80)
    print("TEST 2: GET /api/housekeeping/staff-performance-detailed")
    print("="*80)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(
            f"{BASE_URL}/housekeeping/staff-performance-detailed",
            headers=headers,
            timeout=15
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ HTTP 200 - Success")
            
            # Verify structure
            errors = []
            
            # Check staff_performance array
            if 'staff_performance' not in data:
                errors.append("❌ Missing 'staff_performance' array")
            else:
                staff_performance = data['staff_performance']
                print(f"✅ staff_performance array present: {len(staff_performance)} items")
                
                if len(staff_performance) > 0:
                    # Check first item structure
                    first_staff = staff_performance[0]
                    required_staff_fields = ['staff_name', 'tasks_completed', 'avg_duration_minutes', 'quality_score', 'speed_rating', 'efficiency_rating']
                    for field in required_staff_fields:
                        if field not in first_staff:
                            errors.append(f"❌ Staff item missing field '{field}'")
                    
                    if not any(f"Staff item missing field" in e for e in errors):
                        print(f"   ✅ Staff item structure correct:")
                        print(f"      - staff_name: {first_staff.get('staff_name')}")
                        print(f"      - tasks_completed: {first_staff.get('tasks_completed')}")
                        print(f"      - avg_duration_minutes: {first_staff.get('avg_duration_minutes')}")
                        print(f"      - quality_score: {first_staff.get('quality_score')}")
                        print(f"      - speed_rating: {first_staff.get('speed_rating')}")
                        print(f"      - efficiency_rating: {first_staff.get('efficiency_rating')}")
                else:
                    print(f"   ℹ️  No staff performance data (empty array is acceptable)")
            
            # Check total_staff
            if 'total_staff' not in data:
                errors.append("❌ Missing 'total_staff' field")
            else:
                print(f"✅ total_staff present: {data.get('total_staff')}")
            
            # Check total_tasks
            if 'total_tasks' not in data:
                errors.append("❌ Missing 'total_tasks' field")
            else:
                print(f"✅ total_tasks present: {data.get('total_tasks')}")
            
            # Print full response for verification
            print(f"\n📋 Full Response:")
            print(json.dumps(data, indent=2))
            
            # Final verdict
            if errors:
                print(f"\n❌ TEST FAILED - Structure issues found:")
                for error in errors:
                    print(f"   {error}")
                return False
            else:
                print(f"\n✅ TEST PASSED - All structure requirements met")
                return True
        else:
            print(f"❌ HTTP {response.status_code} - Failed")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        return False

def main():
    """Main test execution"""
    print("="*80)
    print("HOUSEKEEPING DASHBOARD ENDPOINTS TEST")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Login: {LOGIN_EMAIL}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Login
    token = login()
    if not token:
        print("\n❌ TESTS ABORTED - Login failed")
        return
    
    # Run tests
    results = {}
    results['room_status_report'] = test_room_status_report(token)
    results['staff_performance_detailed'] = test_staff_performance_detailed(token)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n📊 Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print(f"\nDetailed Results:")
    print(f"  1. Room Status Report: {'✅ PASSED' if results['room_status_report'] else '❌ FAILED'}")
    print(f"  2. Staff Performance Detailed: {'✅ PASSED' if results['staff_performance_detailed'] else '❌ FAILED'}")
    
    if passed == total:
        print(f"\n🎉 ALL TESTS PASSED - Housekeeping Dashboard endpoints working correctly!")
    else:
        print(f"\n⚠️  SOME TESTS FAILED - Please review the errors above")
    
    print("="*80)

if __name__ == "__main__":
    main()
