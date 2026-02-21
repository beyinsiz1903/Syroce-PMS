#!/usr/bin/env python3
"""
REALISTIC PMS COMPREHENSIVE TEST
Testing actual implemented endpoints in the backend
"""

import requests
import time
import json
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://guest-unified.preview.emergentagent.com/api"
EMAIL = "demo@hotel.com"
PASSWORD = "demo123"

token = None
tenant_id = None
test_results = []

def login():
    """Login and get JWT token"""
    global token, tenant_id
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
        print(f"✅ Login successful - Tenant: {tenant_id}\n")
        return True
    return False

def test(name, method, endpoint, **kwargs):
    """Test endpoint and record result"""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}{endpoint}"
    
    start = time.time()
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=10, **kwargs)
        elif method == "POST":
            r = requests.post(url, headers=headers, timeout=10, **kwargs)
        elif method == "PUT":
            r = requests.put(url, headers=headers, timeout=10, **kwargs)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=10, **kwargs)
        
        elapsed = (time.time() - start) * 1000
        success = 200 <= r.status_code < 300
        
        result = {
            "name": name,
            "endpoint": endpoint,
            "status": r.status_code,
            "time_ms": round(elapsed, 1),
            "success": success
        }
        test_results.append(result)
        
        icon = "✅" if success else "❌"
        print(f"{icon} {name}: {r.status_code} ({elapsed:.0f}ms)")
        
        return success, r.status_code
    except Exception as e:
        print(f"❌ {name}: ERROR - {str(e)}")
        test_results.append({
            "name": name,
            "endpoint": endpoint,
            "status": 0,
            "time_ms": 0,
            "success": False,
            "error": str(e)
        })
        return False, 0

def main():
    if not login():
        print("❌ Login failed")
        return
    
    print("="*80)
    print("🏨 CORE PMS ENDPOINTS")
    print("="*80)
    test("PMS - Rooms", "GET", "/pms/rooms", params={"limit": 100})
    test("PMS - Bookings", "GET", "/pms/bookings", params={"limit": 100})
    test("PMS - Guests", "GET", "/pms/guests", params={"limit": 100})
    test("PMS - Dashboard", "GET", "/pms/dashboard")
    test("PMS - Room Blocks", "GET", "/pms/room-blocks")
    
    print("\n" + "="*80)
    print("💓 MONITORING & HEALTH")
    print("="*80)
    test("Monitoring - Health", "GET", "/monitoring/health")
    test("Monitoring - System", "GET", "/monitoring/system")
    test("Monitoring - Database", "GET", "/monitoring/database")
    test("Monitoring - Alerts", "GET", "/monitoring/alerts")
    test("Monitoring - Metrics", "GET", "/monitoring/metrics")
    
    print("\n" + "="*80)
    print("🏢 COMPANIES & CONTRACTS")
    print("="*80)
    test("Companies - List", "GET", "/companies", params={"limit": 50})
    test("Contracted Rates - List", "GET", "/contracted-rates")
    test("Contracted Rates - Allotment", "GET", "/contracted-rates/allotment-utilization")
    
    print("\n" + "="*80)
    print("🧹 HOUSEKEEPING")
    print("="*80)
    test("Housekeeping - Tasks", "GET", "/housekeeping/tasks")
    test("Housekeeping - Room Assignments", "GET", "/housekeeping/mobile/room-assignments")
    test("Housekeeping - Cleaning Stats", "GET", "/housekeeping/cleaning-time-statistics")
    test("Housekeeping - Linen Inventory", "GET", "/housekeeping/linen-inventory")
    test("Housekeeping - Lost & Found", "GET", "/housekeeping/lost-found")
    
    print("\n" + "="*80)
    print("💰 REVENUE MANAGEMENT")
    print("="*80)
    test("RMS - Demand Heatmap", "GET", "/rms/demand-heatmap")
    test("RMS - Demand Forecast", "GET", "/rms/demand-forecast")
    test("RMS - Rate Calendar", "GET", "/rms/rate-calendar")
    test("RMS - Pickup Report", "GET", "/rms/pickup-report")
    
    print("\n" + "="*80)
    print("📊 REPORTS & ANALYTICS")
    print("="*80)
    test("Reports - Flash Report", "GET", "/reports/flash-report")
    test("Reports - Forecast", "GET", "/reports/forecast")
    test("Arrivals - Today", "GET", "/arrivals/today")
    test("Executive - KPI Snapshot", "GET", "/executive/kpi-snapshot")
    test("Executive - Dashboard", "GET", "/executive/dashboard")
    
    print("\n" + "="*80)
    print("🌐 CHANNEL MANAGER")
    print("="*80)
    test("Channels - Rate Parity", "GET", "/channels/rate-parity")
    test("Channels - Sync History", "GET", "/channels/sync-history")
    test("Channels - OTA Reservations", "GET", "/channels/ota-reservations")
    
    print("\n" + "="*80)
    print("💳 FOLIO & PAYMENTS")
    print("="*80)
    test("Accounting - Invoices", "GET", "/accounting/invoices")
    test("Accounting - Bank Accounts", "GET", "/accounting/bank-accounts")
    test("Accounting - Expenses", "GET", "/accounting/expenses")
    test("AR - Aging Report", "GET", "/ar/aging-report")
    test("AR - Outstanding", "GET", "/ar/outstanding")
    
    print("\n" + "="*80)
    print("⭐ LOYALTY & GUEST SERVICES")
    print("="*80)
    test("Loyalty - Programs", "GET", "/loyalty/programs")
    test("Guest - Loyalty", "GET", "/guest/loyalty")
    test("Guest Services - Amenities", "GET", "/guest-services/amenities")
    test("Guest Services - Concierge", "GET", "/guest-services/concierge")
    
    print("\n" + "="*80)
    print("🔧 MAINTENANCE")
    print("="*80)
    test("Maintenance - Tasks", "GET", "/maintenance/tasks")
    test("Maintenance - Planned", "GET", "/maintenance/planned")
    test("Maintenance - Asset History", "GET", "/maintenance/asset-history")
    
    print("\n" + "="*80)
    print("🍽️ F&B MANAGEMENT")
    print("="*80)
    test("F&B - Recipes", "GET", "/fnb/recipes")
    test("F&B - Kitchen Display", "GET", "/fnb/kitchen-display")
    test("F&B - Ingredients", "GET", "/fnb/ingredients")
    test("POS - Outlets", "GET", "/pos/outlets")
    test("POS - Orders", "GET", "/pos/orders")
    
    print("\n" + "="*80)
    print("👥 HR & STAFF")
    print("="*80)
    test("HR - Payroll", "GET", "/hr/payroll/2025-11")
    test("Staff - Performance", "GET", "/staff/performance")
    test("Staff - Attendance", "GET", "/staff/attendance")
    
    print("\n" + "="*80)
    print("💵 FINANCE")
    print("="*80)
    test("Finance - Budget vs Actual", "GET", "/finance/budget-vs-actual", params={"month": "2025-11"})
    test("Finance - Cash Flow", "GET", "/finance/cash-flow")
    test("Finance - P&L", "GET", "/finance/profit-loss")
    
    print("\n" + "="*80)
    print("🤖 AI & PREDICTIONS")
    print("="*80)
    test("AI - No-Show Predictions", "GET", "/predictions/no-shows")
    test("AI - Social Media Mentions", "GET", "/social-media/mentions")
    test("AI - Staffing Optimal", "GET", "/staffing-ai/optimal")
    test("AI - Guest DNA", "GET", "/guest-dna/guest-001")
    test("AI - Autopilot", "POST", "/autopilot/run-cycle", json={})
    
    print("\n" + "="*80)
    print("🏢 EVENTS & GROUPS")
    print("="*80)
    test("Groups - List", "GET", "/groups")
    test("Groups - Room Blocks", "GET", "/groups/room-blocks")
    test("Events - Meeting Rooms", "GET", "/events/meeting-rooms")
    test("Events - BEO", "GET", "/events/beo")
    
    print("\n" + "="*80)
    print("📱 MOBILE ENDPOINTS")
    print("="*80)
    test("Mobile - Dashboard", "GET", "/mobile/dashboard")
    test("Mobile - Revenue", "GET", "/mobile/revenue")
    test("Mobile - Housekeeping", "GET", "/mobile/housekeeping")
    test("Mobile - Maintenance", "GET", "/mobile/maintenance")
    test("Mobile - Front Desk", "GET", "/mobile/frontdesk")
    
    # Print Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    total = len(test_results)
    passed = sum(1 for r in test_results if r["success"])
    failed = total - passed
    success_rate = (passed / total * 100) if total > 0 else 0
    
    avg_time = sum(r["time_ms"] for r in test_results if r["time_ms"] > 0) / len([r for r in test_results if r["time_ms"] > 0])
    
    print(f"\nTotal Endpoints: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Success Rate: {success_rate:.1f}%")
    print(f"⚡ Avg Response Time: {avg_time:.1f}ms")
    
    if failed > 0:
        print(f"\n❌ FAILED ENDPOINTS:")
        for r in test_results:
            if not r["success"]:
                print(f"   • {r['name']}: HTTP {r['status']} - {r['endpoint']}")
    
    # Save results
    with open("/app/realistic_test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "success_rate": success_rate,
                "avg_time_ms": avg_time
            },
            "results": test_results
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: /app/realistic_test_results.json")
    print("="*80)

if __name__ == "__main__":
    main()
