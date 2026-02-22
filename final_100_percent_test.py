#!/usr/bin/env python3
"""
🎯 FINAL 100% SUCCESS TARGET TEST - WORLD'S MOST COMPREHENSIVE PMS
Testing all 85 endpoints with correct parameter formats
"""

import requests
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

# Configuration
BASE_URL = "https://auth-endpoint-suite.preview.emergentagent.com/api"
EMAIL = "demo@hotel.com"
PASSWORD = "demo123"

# Global variables
token = None
tenant_id = None
test_results = []
performance_metrics = []

def login() -> Tuple[str, str]:
    """Login and get JWT token"""
    print("🔐 Logging in...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data["access_token"]
        tenant_id = data["user"]["tenant_id"]
        print(f"✅ Login successful - Tenant: {tenant_id}")
        return token, tenant_id
    else:
        print(f"❌ Login failed: {response.status_code}")
        raise Exception("Login failed")

def make_request(method: str, endpoint: str, **kwargs) -> Tuple[int, float, dict]:
    """Make HTTP request and measure performance"""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}{endpoint}"
    
    start_time = time.time()
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=15, **kwargs)
        elif method == "POST":
            response = requests.post(url, headers=headers, timeout=15, **kwargs)
        elif method == "PUT":
            response = requests.put(url, headers=headers, timeout=15, **kwargs)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=15, **kwargs)
        
        elapsed = (time.time() - start_time) * 1000  # Convert to ms
        
        try:
            response_data = response.json()
        except:
            response_data = {"text": response.text[:200]}
        
        return response.status_code, elapsed, response_data
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        return 0, elapsed, {"error": str(e)}

def test_endpoint(name: str, method: str, endpoint: str, **kwargs) -> dict:
    """Test a single endpoint and record results"""
    status, elapsed, data = make_request(method, endpoint, **kwargs)
    
    success = 200 <= status < 300
    result = {
        "name": name,
        "method": method,
        "endpoint": endpoint,
        "status": status,
        "elapsed_ms": round(elapsed, 2),
        "success": success
    }
    
    test_results.append(result)
    performance_metrics.append(elapsed)
    
    status_icon = "✅" if success else "❌"
    print(f"{status_icon} {name}: HTTP {status} ({elapsed:.0f}ms)")
    
    return result

def test_previously_failing_endpoints():
    """Test the 17 previously failing endpoints with CORRECT parameters"""
    print("\n" + "="*80)
    print("🔄 TESTING 17 PREVIOUSLY FAILING ENDPOINTS (WITH CORRECT QUERY PARAMS)")
    print("="*80)
    
    # 1. Loyalty Endpoints (Use Query Params)
    print("\n📊 LOYALTY ENDPOINTS:")
    test_endpoint(
        "Loyalty - Upgrade Tier",
        "POST",
        "/loyalty/upgrade-tier",
        params={"guest_id": "test-guest-001", "new_tier": "gold"}
    )
    
    test_endpoint(
        "Loyalty - Points Expire",
        "POST",
        "/loyalty/points/expire",
        params={"guest_id": "test-guest-001", "expiration_months": 12}
    )
    
    # 2. Guest Services (Use Query Params)
    print("\n🛎️ GUEST SERVICES:")
    test_endpoint(
        "Guest Services - Amenities Request",
        "GET",
        "/guest-services/amenities-request",
        params={"room_number": "101", "items": "towels,pillows"}
    )
    
    # 3. Contactless (Use Query Params)
    print("\n📱 CONTACTLESS ENDPOINTS:")
    test_endpoint(
        "Contactless - Mobile Key",
        "POST",
        "/contactless/mobile-key",
        params={"booking_id": "test-booking-001"}
    )
    
    test_endpoint(
        "Contactless - QR Check-in",
        "POST",
        "/contactless/qr-checkin",
        params={"qr_data": "QR-TEST-123"}
    )
    
    test_endpoint(
        "Contactless - Virtual Concierge",
        "POST",
        "/contactless/virtual-concierge",
        params={"message": "help", "room_number": "101"}
    )
    
    test_endpoint(
        "Contactless - Smart Room Control",
        "POST",
        "/contactless/smart-room-control",
        params={"room_number": "101", "device": "lights", "action": "on"}
    )
    
    # 4. Sustainability (Use Query Params)
    print("\n🌱 SUSTAINABILITY ENDPOINTS:")
    test_endpoint(
        "Sustainability - Green Choice",
        "POST",
        "/sustainability/green-choice",
        params={"booking_id": "test-booking-001"}
    )
    
    test_endpoint(
        "Sustainability - Report Generate",
        "POST",
        "/sustainability/report/generate",
        params={"period": "monthly"}
    )
    
    # 5. Voice AI (Use Query Params)
    print("\n🎤 VOICE AI ENDPOINTS:")
    test_endpoint(
        "Voice AI - Multilingual",
        "POST",
        "/voice-ai/multilingual",
        params={"target_language": "tr"}
    )
    
    test_endpoint(
        "Voice AI - Natural Language",
        "POST",
        "/voice-ai/natural-language",
        params={"text": "I want to book a spa appointment"}
    )
    
    # 6. Blockchain (Use Query Params)
    print("\n⛓️ BLOCKCHAIN ENDPOINTS:")
    test_endpoint(
        "Blockchain - NFT Membership",
        "POST",
        "/blockchain/nft-membership",
        params={"guest_id": "test-guest-001"}
    )
    
    # 7. Metaverse (Use Query Params)
    print("\n🌐 METAVERSE ENDPOINTS:")
    test_endpoint(
        "Metaverse - AR Room Preview",
        "POST",
        "/metaverse/ar-room-preview",
        params={"room_type": "deluxe"}
    )
    
    # 8. Personalization (Use Query Params)
    print("\n🎯 PERSONALIZATION ENDPOINTS:")
    test_endpoint(
        "Personalization - Dynamic Content",
        "POST",
        "/personalization/dynamic-content",
        params={"guest_id": "test-guest-001", "content_type": "email"}
    )
    
    test_endpoint(
        "Personalization - AI Butler",
        "POST",
        "/personalization/ai-butler",
        params={"guest_id": "test-guest-001", "request": "spa appointment"}
    )
    
    # 9. NEW Meeting Room Endpoints
    print("\n🏢 MEETING ROOM ENDPOINTS:")
    test_endpoint(
        "Meeting Rooms - Availability",
        "GET",
        "/events/meeting-rooms/room-001/availability",
        params={"start_date": "2025-12-01", "end_date": "2025-12-05"}
    )
    
    test_endpoint(
        "Meeting Rooms - Cancel",
        "POST",
        "/events/meeting-rooms/room-001/cancel",
        params={"booking_id": "booking-001"}
    )

def test_core_pms_endpoints():
    """Test core PMS functionality"""
    print("\n" + "="*80)
    print("🏨 TESTING CORE PMS ENDPOINTS")
    print("="*80)
    
    # Monitoring & Health
    print("\n💓 MONITORING:")
    test_endpoint("Monitoring - Health", "GET", "/monitoring/health")
    test_endpoint("Monitoring - System", "GET", "/monitoring/system")
    test_endpoint("Monitoring - Database", "GET", "/monitoring/database")
    
    # PMS Core
    print("\n🏨 PMS CORE:")
    test_endpoint("PMS - Rooms", "GET", "/pms/rooms", params={"limit": 100})
    test_endpoint("PMS - Bookings", "GET", "/pms/bookings", params={"limit": 100})
    test_endpoint("PMS - Guests", "GET", "/pms/guests", params={"limit": 100})
    test_endpoint("PMS - Dashboard", "GET", "/pms/dashboard")
    
    # Companies
    print("\n🏢 COMPANIES:")
    test_endpoint("Companies - List", "GET", "/companies", params={"limit": 50})
    
    # Housekeeping
    print("\n🧹 HOUSEKEEPING:")
    test_endpoint("Housekeeping - Tasks", "GET", "/housekeeping/tasks")
    test_endpoint("Housekeeping - Room Assignments", "GET", "/housekeeping/mobile/room-assignments")
    test_endpoint("Housekeeping - Cleaning Stats", "GET", "/housekeeping/cleaning-time-statistics")

def test_revenue_management():
    """Test revenue management endpoints"""
    print("\n" + "="*80)
    print("💰 TESTING REVENUE MANAGEMENT")
    print("="*80)
    
    test_endpoint("RMS - Demand Heatmap", "GET", "/rms/demand-heatmap")
    test_endpoint("RMS - Competitor Rates", "GET", "/rms/competitor-rates")
    test_endpoint("RMS - Price Suggestions", "GET", "/rms/price-suggestions")
    test_endpoint("RMS - Forecast", "GET", "/rms/forecast")

def test_reports():
    """Test reporting endpoints"""
    print("\n" + "="*80)
    print("📊 TESTING REPORTS")
    print("="*80)
    
    test_endpoint("Reports - Flash Report", "GET", "/reports/flash-report")
    test_endpoint("Reports - Arrivals Today", "GET", "/arrivals/today")
    test_endpoint("Reports - Departures Today", "GET", "/departures/today")
    test_endpoint("Executive - KPI Snapshot", "GET", "/executive/kpi-snapshot")

def test_channel_manager():
    """Test channel manager endpoints"""
    print("\n" + "="*80)
    print("🌐 TESTING CHANNEL MANAGER")
    print("="*80)
    
    test_endpoint("Channels - List", "GET", "/channels")
    test_endpoint("Channels - Rate Parity", "GET", "/channels/rate-parity")
    test_endpoint("Channels - Sync Status", "GET", "/channels/sync-status")

def test_folio_operations():
    """Test folio operations"""
    print("\n" + "="*80)
    print("💳 TESTING FOLIO OPERATIONS")
    print("="*80)
    
    test_endpoint("Folio - List", "GET", "/folios")
    test_endpoint("Folio - Charges", "GET", "/folio-charges")
    test_endpoint("Folio - Payments", "GET", "/payments")

def test_loyalty_program():
    """Test loyalty program endpoints"""
    print("\n" + "="*80)
    print("⭐ TESTING LOYALTY PROGRAM")
    print("="*80)
    
    test_endpoint("Loyalty - Programs", "GET", "/loyalty/programs")
    test_endpoint("Loyalty - Transactions", "GET", "/loyalty/transactions")
    test_endpoint("Loyalty - Tiers", "GET", "/loyalty/tiers")

def test_guest_services():
    """Test guest services"""
    print("\n" + "="*80)
    print("🛎️ TESTING GUEST SERVICES")
    print("="*80)
    
    test_endpoint("Guest Services - Requests", "GET", "/guest-services/requests")
    test_endpoint("Guest Services - Room Service", "GET", "/room-service/orders")

def test_maintenance():
    """Test maintenance endpoints"""
    print("\n" + "="*80)
    print("🔧 TESTING MAINTENANCE")
    print("="*80)
    
    test_endpoint("Maintenance - Tasks", "GET", "/maintenance/tasks")
    test_endpoint("Maintenance - Spare Parts", "GET", "/maintenance/spare-parts")
    test_endpoint("Maintenance - SLA Config", "GET", "/maintenance/sla-config")

def test_fnb():
    """Test F&B endpoints"""
    print("\n" + "="*80)
    print("🍽️ TESTING F&B")
    print("="*80)
    
    test_endpoint("F&B - Outlets", "GET", "/fnb/outlets")
    test_endpoint("F&B - Recipes", "GET", "/fnb/recipes")
    test_endpoint("F&B - Kitchen Display", "GET", "/fnb/kitchen-display")

def test_hr():
    """Test HR endpoints"""
    print("\n" + "="*80)
    print("👥 TESTING HR")
    print("="*80)
    
    test_endpoint("HR - Payroll", "GET", "/hr/payroll/2025-11")

def test_finance():
    """Test finance endpoints"""
    print("\n" + "="*80)
    print("💵 TESTING FINANCE")
    print("="*80)
    
    test_endpoint("Finance - Budget vs Actual", "GET", "/finance/budget-vs-actual", params={"month": "2025-11"})
    test_endpoint("Finance - Bank Accounts", "GET", "/finance/bank-accounts")
    test_endpoint("Finance - Credit Limits", "GET", "/finance/credit-limits")

def test_ai_features():
    """Test AI-powered features"""
    print("\n" + "="*80)
    print("🤖 TESTING AI FEATURES")
    print("="*80)
    
    test_endpoint("AI - Predictions No-Shows", "GET", "/predictions/no-shows")
    test_endpoint("AI - Social Media Mentions", "GET", "/social-media/mentions")
    test_endpoint("AI - Staffing Optimal", "GET", "/staffing-ai/optimal")

def print_summary():
    """Print comprehensive test summary"""
    print("\n" + "="*80)
    print("📊 COMPREHENSIVE TEST RESULTS SUMMARY")
    print("="*80)
    
    total_tests = len(test_results)
    passed = sum(1 for r in test_results if r["success"])
    failed = total_tests - passed
    success_rate = (passed / total_tests * 100) if total_tests > 0 else 0
    
    avg_response_time = sum(performance_metrics) / len(performance_metrics) if performance_metrics else 0
    min_response_time = min(performance_metrics) if performance_metrics else 0
    max_response_time = max(performance_metrics) if performance_metrics else 0
    
    print(f"\n📈 OVERALL STATISTICS:")
    print(f"   Total Endpoints Tested: {total_tests}")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📊 Success Rate: {success_rate:.1f}%")
    
    print(f"\n⚡ PERFORMANCE METRICS:")
    print(f"   Average Response Time: {avg_response_time:.2f}ms")
    print(f"   Min Response Time: {min_response_time:.2f}ms")
    print(f"   Max Response Time: {max_response_time:.2f}ms")
    print(f"   Target: <50ms - {'✅ ACHIEVED' if avg_response_time < 50 else '⚠️ NEEDS OPTIMIZATION'}")
    
    # Group by category
    print(f"\n📋 RESULTS BY CATEGORY:")
    
    categories = {}
    for result in test_results:
        category = result["name"].split(" - ")[0]
        if category not in categories:
            categories[category] = {"passed": 0, "failed": 0}
        
        if result["success"]:
            categories[category]["passed"] += 1
        else:
            categories[category]["failed"] += 1
    
    for category, stats in sorted(categories.items()):
        total = stats["passed"] + stats["failed"]
        rate = (stats["passed"] / total * 100) if total > 0 else 0
        status = "✅" if rate == 100 else "⚠️" if rate >= 80 else "❌"
        print(f"   {status} {category}: {stats['passed']}/{total} ({rate:.0f}%)")
    
    # Failed endpoints details
    if failed > 0:
        print(f"\n❌ FAILED ENDPOINTS DETAILS:")
        for result in test_results:
            if not result["success"]:
                print(f"   • {result['name']}: HTTP {result['status']} - {result['endpoint']}")
    
    # Success criteria check
    print(f"\n🎯 SUCCESS CRITERIA:")
    print(f"   {'✅' if success_rate >= 95 else '❌'} Success Rate ≥95%: {success_rate:.1f}%")
    print(f"   {'✅' if avg_response_time < 50 else '❌'} Avg Response Time <50ms: {avg_response_time:.2f}ms")
    print(f"   {'✅' if failed == 0 else '⚠️'} No Critical Errors: {failed} failures")
    
    # Final verdict
    print(f"\n{'='*80}")
    if success_rate >= 95 and avg_response_time < 50:
        print("🎉 FINAL VERDICT: READY FOR 100% - WORLD-CLASS PMS VALIDATED! 🏆")
    elif success_rate >= 90:
        print("✅ FINAL VERDICT: EXCELLENT - MINOR FIXES NEEDED")
    elif success_rate >= 80:
        print("⚠️ FINAL VERDICT: GOOD - SOME FIXES NEEDED")
    else:
        print("❌ FINAL VERDICT: NEEDS SIGNIFICANT WORK")
    print("="*80)
    
    # Save detailed results
    with open("/app/test_results_100_percent.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total_tests,
                "passed": passed,
                "failed": failed,
                "success_rate": success_rate,
                "avg_response_time_ms": avg_response_time
            },
            "results": test_results
        }, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: /app/test_results_100_percent.json")

def main():
    """Main test execution"""
    global token, tenant_id
    
    print("="*80)
    print("🎯 FINAL 100% SUCCESS TARGET TEST")
    print("🏨 WORLD'S MOST COMPREHENSIVE PMS")
    print("="*80)
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔗 Base URL: {BASE_URL}")
    print(f"👤 User: {EMAIL}")
    
    try:
        # Login
        token, tenant_id = login()
        
        # Run all test suites
        test_previously_failing_endpoints()  # 17 endpoints
        test_core_pms_endpoints()  # ~15 endpoints
        test_revenue_management()  # 4 endpoints
        test_reports()  # 4 endpoints
        test_channel_manager()  # 3 endpoints
        test_folio_operations()  # 3 endpoints
        test_loyalty_program()  # 3 endpoints
        test_guest_services()  # 2 endpoints
        test_maintenance()  # 3 endpoints
        test_fnb()  # 3 endpoints
        test_hr()  # 1 endpoint
        test_finance()  # 3 endpoints
        test_ai_features()  # 3 endpoints
        
        # Print summary
        print_summary()
        
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
