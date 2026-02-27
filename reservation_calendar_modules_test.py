#!/usr/bin/env python3
"""
Reservation Calendar Enterprise/AI/Deluxe+ Modules Data Verification Test

This test verifies whether the Reservation Calendar Enterprise/AI/Deluxe+ modules 
are using real data or returning empty due to tenant/date range issues.

Test Steps:
1. Login as demo@hotel.com / demo123
2. Call /api/pms/bookings with date range 2024-01-01 to 2024-02-15 and confirm count > 0
3. Call Enterprise/Deluxe endpoints with same date range and verify data
4. Test future date range to confirm proper date filtering
5. Analyze why UI may show 40% direct_booking_gap and $0 savings
"""

import requests
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

class ReservationCalendarModulesTest:
    def __init__(self):
        self.base_url = "https://pms-i18next-demo.preview.emergentagent.com/api"
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self.token = None
        self.tenant_id = None
        
        # Test date ranges
        self.historical_start = "2024-01-01"
        self.historical_end = "2024-02-15"
        self.future_start = "2025-12-01"
        self.future_end = "2025-12-15"
        
        # Results tracking
        self.results = {
            'authentication': False,
            'pms_bookings_historical': {'count': 0, 'success': False},
            'deluxe_oversell_protection': {'protection_map_length': 0, 'success': False},
            'deluxe_optimize_channel_mix_historical': {'total_bookings': 0, 'success': False},
            'enterprise_availability_heatmap': {'heatmap_length': 0, 'success': False},
            'deluxe_optimize_channel_mix_future': {'total_bookings': 0, 'success': False},
            'conclusions': []
        }

    def authenticate(self) -> bool:
        """Authenticate with demo@hotel.com / demo123"""
        print("🔐 Authenticating with demo@hotel.com / demo123...")
        
        try:
            response = self.session.post(f"{self.base_url}/auth/login", json={
                "email": "demo@hotel.com",
                "password": "demo123"
            })
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                self.tenant_id = data.get('user', {}).get('tenant_id')
                
                if self.token:
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.token}'
                    })
                    print(f"✅ Authentication successful")
                    print(f"   User: {data.get('user', {}).get('name')}")
                    print(f"   Tenant ID: {self.tenant_id}")
                    self.results['authentication'] = True
                    return True
                else:
                    print("❌ No access token in response")
                    return False
            else:
                print(f"❌ Authentication failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def test_pms_bookings_historical(self) -> bool:
        """Test /api/pms/bookings with historical date range"""
        print(f"\n📊 Testing PMS Bookings ({self.historical_start} to {self.historical_end})...")
        
        try:
            response = self.session.get(
                f"{self.base_url}/pms/bookings",
                params={
                    'start_date': self.historical_start,
                    'end_date': self.historical_end,
                    'limit': 1000  # Get all bookings in range
                }
            )
            
            if response.status_code == 200:
                bookings = response.json()
                count = len(bookings) if isinstance(bookings, list) else 0
                
                print(f"✅ PMS Bookings API successful")
                print(f"   Bookings found: {count}")
                print(f"   Date range: {self.historical_start} to {self.historical_end}")
                
                if count > 0:
                    # Show sample booking data
                    sample = bookings[0]
                    print(f"   Sample booking: {sample.get('id', 'N/A')} - {sample.get('guest_name', 'N/A')}")
                    print(f"   Check-in: {sample.get('check_in', 'N/A')}")
                    print(f"   Status: {sample.get('status', 'N/A')}")
                
                self.results['pms_bookings_historical'] = {
                    'count': count,
                    'success': True,
                    'bookings_sample': bookings[:3] if count > 0 else []
                }
                return count > 0
            else:
                print(f"❌ PMS Bookings failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ PMS Bookings error: {e}")
            return False

    def test_deluxe_oversell_protection(self) -> bool:
        """Test /api/deluxe/oversell-protection endpoint"""
        print(f"\n🛡️ Testing Deluxe Oversell Protection ({self.historical_start} to {self.historical_end})...")
        
        try:
            response = self.session.get(
                f"{self.base_url}/deluxe/oversell-protection",
                params={
                    'start_date': self.historical_start,
                    'end_date': self.historical_end
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                protection_map = data.get('protection_map', [])
                protection_map_length = len(protection_map) if isinstance(protection_map, list) else 0
                
                print(f"✅ Deluxe Oversell Protection API successful")
                print(f"   Protection map entries: {protection_map_length}")
                print(f"   Date range: {self.historical_start} to {self.historical_end}")
                
                if protection_map_length > 0:
                    # Show sample protection data
                    sample = protection_map[0]
                    print(f"   Sample protection: Date {sample.get('date', 'N/A')}")
                    print(f"   Room type: {sample.get('room_type', 'N/A')}")
                    print(f"   Protection level: {sample.get('protection_level', 'N/A')}")
                
                # Show other relevant data
                print(f"   Total rooms: {data.get('total_rooms', 0)}")
                print(f"   Risk level: {data.get('risk_level', 'N/A')}")
                
                self.results['deluxe_oversell_protection'] = {
                    'protection_map_length': protection_map_length,
                    'success': True,
                    'total_rooms': data.get('total_rooms', 0),
                    'risk_level': data.get('risk_level', 'N/A')
                }
                return protection_map_length > 0
            else:
                print(f"❌ Deluxe Oversell Protection failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Deluxe Oversell Protection error: {e}")
            return False

    def test_deluxe_optimize_channel_mix(self, start_date: str, end_date: str, is_future: bool = False) -> bool:
        """Test /api/deluxe/optimize-channel-mix endpoint"""
        period_type = "future" if is_future else "historical"
        print(f"\n🎯 Testing Deluxe Optimize Channel Mix - {period_type} ({start_date} to {end_date})...")
        
        try:
            response = self.session.post(
                f"{self.base_url}/deluxe/optimize-channel-mix",
                json={
                    'start_date': start_date,
                    'end_date': end_date
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                analysis = data.get('analysis', {})
                total_bookings = analysis.get('total_bookings', 0)
                
                print(f"✅ Deluxe Optimize Channel Mix API successful")
                print(f"   Total bookings in analysis: {total_bookings}")
                print(f"   Date range: {start_date} to {end_date}")
                
                # Show detailed analysis
                if 'channel_performance' in analysis:
                    print(f"   Channel performance data available: {len(analysis['channel_performance'])} channels")
                
                if 'recommendations' in data:
                    recommendations = data['recommendations']
                    print(f"   Recommendations: {len(recommendations)} items")
                    if recommendations:
                        print(f"   Top recommendation: {recommendations[0].get('action', 'N/A')}")
                
                # Show revenue impact
                revenue_impact = data.get('revenue_impact', {})
                if revenue_impact:
                    if isinstance(revenue_impact, dict):
                        print(f"   Potential savings: ${revenue_impact.get('potential_savings', 0)}")
                        print(f"   Direct booking gap: {revenue_impact.get('direct_booking_gap', 0)}%")
                    else:
                        print(f"   Revenue impact (raw): {revenue_impact}")
                else:
                    print("   No revenue impact data available")
                
                result_key = 'deluxe_optimize_channel_mix_future' if is_future else 'deluxe_optimize_channel_mix_historical'
                self.results[result_key] = {
                    'total_bookings': total_bookings,
                    'success': True,
                    'analysis': analysis,
                    'revenue_impact': revenue_impact if isinstance(revenue_impact, dict) else {},
                    'recommendations_count': len(data.get('recommendations', [])),
                    'raw_response': data  # Store full response for debugging
                }
                
                return True
            else:
                print(f"❌ Deluxe Optimize Channel Mix failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Deluxe Optimize Channel Mix error: {e}")
            return False

    def test_enterprise_availability_heatmap(self) -> bool:
        """Test /api/enterprise/availability-heatmap endpoint"""
        print(f"\n🗺️ Testing Enterprise Availability Heatmap ({self.historical_start} to {self.historical_end})...")
        
        try:
            response = self.session.get(
                f"{self.base_url}/enterprise/availability-heatmap",
                params={
                    'start_date': self.historical_start,
                    'end_date': self.historical_end
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                heatmap = data.get('heatmap', [])
                heatmap_length = len(heatmap) if isinstance(heatmap, list) else 0
                
                print(f"✅ Enterprise Availability Heatmap API successful")
                print(f"   Heatmap entries: {heatmap_length}")
                print(f"   Date range: {self.historical_start} to {self.historical_end}")
                
                if heatmap_length > 0:
                    # Show sample heatmap data
                    sample = heatmap[0]
                    print(f"   Sample heatmap: Date {sample.get('date', 'N/A')}")
                    print(f"   Availability: {sample.get('availability', 'N/A')}%")
                    print(f"   Demand level: {sample.get('demand_level', 'N/A')}")
                
                # Show summary statistics
                summary = data.get('summary', {})
                if summary:
                    print(f"   Average availability: {summary.get('avg_availability', 0)}%")
                    print(f"   Peak demand date: {summary.get('peak_demand_date', 'N/A')}")
                
                self.results['enterprise_availability_heatmap'] = {
                    'heatmap_length': heatmap_length,
                    'success': True,
                    'summary': summary,
                    'sample_data': heatmap[:3] if heatmap_length > 0 else []
                }
                return heatmap_length > 0
            else:
                print(f"❌ Enterprise Availability Heatmap failed: HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Enterprise Availability Heatmap error: {e}")
            return False

    def analyze_ui_issues(self):
        """Analyze why UI may show 40% direct_booking_gap and $0 savings"""
        print(f"\n🔍 ANALYZING UI ISSUES: 40% direct_booking_gap and $0 savings...")
        
        conclusions = []
        
        # Check if we have booking data
        pms_bookings = self.results['pms_bookings_historical']
        if not pms_bookings['success'] or pms_bookings['count'] == 0:
            conclusions.append("❌ NO HISTORICAL BOOKING DATA: PMS bookings API returned 0 bookings for 2024-01-01 to 2024-02-15")
            conclusions.append("   → This explains $0 savings - no data to analyze")
            conclusions.append("   → UI cannot calculate meaningful metrics without booking history")
        else:
            conclusions.append(f"✅ BOOKING DATA AVAILABLE: {pms_bookings['count']} bookings found in historical range")
        
        # Check deluxe channel mix optimization
        channel_mix = self.results['deluxe_optimize_channel_mix_historical']
        if channel_mix['success']:
            total_bookings = channel_mix['total_bookings']
            revenue_impact = channel_mix.get('revenue_impact', {})
            
            if total_bookings == 0:
                conclusions.append("❌ CHANNEL MIX ANALYSIS EMPTY: optimize-channel-mix returned 0 total_bookings")
                conclusions.append("   → This explains both $0 savings and 40% direct_booking_gap")
                conclusions.append("   → Algorithm cannot calculate channel performance without booking data")
            else:
                conclusions.append(f"✅ CHANNEL MIX DATA: {total_bookings} bookings analyzed")
                
                # Check specific metrics
                if isinstance(revenue_impact, dict):
                    direct_gap = revenue_impact.get('direct_booking_gap', 0)
                    potential_savings = revenue_impact.get('potential_savings', 0)
                    
                    conclusions.append(f"   → Direct booking gap: {direct_gap}%")
                    conclusions.append(f"   → Potential savings: ${potential_savings}")
                    
                    if direct_gap == 40:
                        conclusions.append("✅ CONFIRMED: API returns 40% direct_booking_gap - UI is displaying correct backend data")
                    
                    if potential_savings == 0:
                        conclusions.append("✅ CONFIRMED: API returns $0 potential_savings - UI is displaying correct backend data")
                else:
                    conclusions.append(f"   → Revenue impact data format issue: {type(revenue_impact)}")
        else:
            conclusions.append("❌ CHANNEL MIX API FAILED: Could not retrieve channel optimization data")
        
        # Check enterprise heatmap
        heatmap = self.results['enterprise_availability_heatmap']
        if heatmap['success'] and heatmap['heatmap_length'] > 0:
            conclusions.append(f"✅ ENTERPRISE HEATMAP: {heatmap['heatmap_length']} entries available")
        else:
            conclusions.append("❌ ENTERPRISE HEATMAP EMPTY: No availability heatmap data")
        
        # Check oversell protection
        oversell = self.results['deluxe_oversell_protection']
        if oversell['success'] and oversell['protection_map_length'] > 0:
            conclusions.append(f"✅ OVERSELL PROTECTION: {oversell['protection_map_length']} protection entries")
        else:
            conclusions.append("❌ OVERSELL PROTECTION EMPTY: No protection map data")
        
        # Date range validation
        future_mix = self.results['deluxe_optimize_channel_mix_future']
        if future_mix['success']:
            future_bookings = future_mix['total_bookings']
            if future_bookings == 0:
                conclusions.append("✅ DATE FILTERING WORKS: Future date range (2025-12-01 to 2025-12-15) correctly returns 0 bookings")
            else:
                conclusions.append(f"⚠️ UNEXPECTED FUTURE DATA: Future range returned {future_bookings} bookings (should be 0)")
        
        # Final diagnosis
        if pms_bookings['count'] == 0:
            conclusions.append("\n🎯 ROOT CAUSE DIAGNOSIS:")
            conclusions.append("   The UI shows 40% direct_booking_gap and $0 savings because:")
            conclusions.append("   1. No booking data exists in the specified date range (2024-01-01 to 2024-02-15)")
            conclusions.append("   2. Without historical bookings, channel optimization algorithms return default/empty values")
            conclusions.append("   3. The 40% gap may be a default placeholder when no data is available")
            conclusions.append("   4. $0 savings is correct - no bookings means no optimization opportunities")
        else:
            conclusions.append("\n🎯 ROOT CAUSE DIAGNOSIS:")
            conclusions.append("   The modules are working with real data:")
            conclusions.append(f"   1. {pms_bookings['count']} bookings available for analysis")
            conclusions.append("   2. UI metrics reflect actual backend calculations")
            conclusions.append("   3. 40% direct_booking_gap and $0 savings are legitimate business metrics")
            conclusions.append("   4. Consider checking if date range in UI matches backend expectations")
        
        self.results['conclusions'] = conclusions
        
        for conclusion in conclusions:
            print(conclusion)

    def run_comprehensive_test(self):
        """Run all tests in sequence"""
        print("🏨 RESERVATION CALENDAR ENTERPRISE/AI/DELUXE+ MODULES DATA VERIFICATION")
        print("=" * 80)
        
        # Step 1: Authentication
        if not self.authenticate():
            print("\n❌ CRITICAL: Authentication failed - cannot proceed with tests")
            return False
        
        # Step 2: Test PMS bookings with historical date range
        pms_success = self.test_pms_bookings_historical()
        
        # Step 3: Test Deluxe oversell protection
        oversell_success = self.test_deluxe_oversell_protection()
        
        # Step 4: Test Deluxe channel mix optimization (historical)
        channel_mix_historical_success = self.test_deluxe_optimize_channel_mix(
            self.historical_start, self.historical_end, is_future=False
        )
        
        # Step 5: Test Enterprise availability heatmap
        heatmap_success = self.test_enterprise_availability_heatmap()
        
        # Step 6: Test Deluxe channel mix optimization (future - should return 0)
        channel_mix_future_success = self.test_deluxe_optimize_channel_mix(
            self.future_start, self.future_end, is_future=True
        )
        
        # Step 7: Analyze UI issues
        self.analyze_ui_issues()
        
        # Final summary
        self.print_final_summary()
        
        return True

    def print_final_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📋 COMPREHENSIVE TEST SUMMARY")
        print("=" * 80)
        
        # Authentication
        auth_status = "✅ PASSED" if self.results['authentication'] else "❌ FAILED"
        print(f"🔐 Authentication (demo@hotel.com): {auth_status}")
        
        # PMS Bookings
        pms = self.results['pms_bookings_historical']
        pms_status = "✅ PASSED" if pms['success'] and pms['count'] > 0 else "❌ FAILED"
        print(f"📊 PMS Bookings (2024-01-01 to 2024-02-15): {pms_status}")
        print(f"    → Bookings found: {pms['count']}")
        
        # Deluxe Oversell Protection
        oversell = self.results['deluxe_oversell_protection']
        oversell_status = "✅ PASSED" if oversell['success'] and oversell['protection_map_length'] > 0 else "❌ FAILED"
        print(f"🛡️ Deluxe Oversell Protection: {oversell_status}")
        print(f"    → Protection map entries: {oversell['protection_map_length']}")
        
        # Deluxe Channel Mix (Historical)
        channel_hist = self.results['deluxe_optimize_channel_mix_historical']
        channel_hist_status = "✅ PASSED" if channel_hist['success'] and channel_hist['total_bookings'] > 0 else "❌ FAILED"
        print(f"🎯 Deluxe Channel Mix (Historical): {channel_hist_status}")
        print(f"    → Total bookings analyzed: {channel_hist['total_bookings']}")
        
        # Enterprise Availability Heatmap
        heatmap = self.results['enterprise_availability_heatmap']
        heatmap_status = "✅ PASSED" if heatmap['success'] and heatmap['heatmap_length'] > 0 else "❌ FAILED"
        print(f"🗺️ Enterprise Availability Heatmap: {heatmap_status}")
        print(f"    → Heatmap entries: {heatmap['heatmap_length']}")
        
        # Deluxe Channel Mix (Future)
        channel_future = self.results['deluxe_optimize_channel_mix_future']
        channel_future_status = "✅ PASSED" if channel_future['success'] and channel_future['total_bookings'] == 0 else "❌ FAILED"
        print(f"🎯 Deluxe Channel Mix (Future - should be 0): {channel_future_status}")
        print(f"    → Total bookings analyzed: {channel_future['total_bookings']}")
        
        # Overall success rate
        total_tests = 5
        passed_tests = sum([
            pms['success'] and pms['count'] > 0,
            oversell['success'] and oversell['protection_map_length'] > 0,
            channel_hist['success'] and channel_hist['total_bookings'] > 0,
            heatmap['success'] and heatmap['heatmap_length'] > 0,
            channel_future['success'] and channel_future['total_bookings'] == 0
        ])
        
        success_rate = (passed_tests / total_tests) * 100
        print(f"\n🎯 OVERALL SUCCESS RATE: {passed_tests}/{total_tests} ({success_rate:.1f}%)")
        
        if success_rate == 100:
            print("🎉 ALL TESTS PASSED - Modules are working with real data!")
        elif success_rate >= 80:
            print("⚠️ MOSTLY WORKING - Some modules may have data issues")
        else:
            print("❌ CRITICAL ISSUES - Multiple modules returning empty data")
        
        print("\n📝 KEY FINDINGS:")
        for conclusion in self.results['conclusions'][-5:]:  # Show last 5 conclusions
            print(f"   {conclusion}")

if __name__ == "__main__":
    test = ReservationCalendarModulesTest()
    test.run_comprehensive_test()