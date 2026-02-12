#!/usr/bin/env python3

import requests
import json
import sys
from datetime import datetime, timedelta
import os

# Get backend URL from environment
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://ai-feature-test.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

class RevenueMobileAPITester:
    def __init__(self):
        self.token = None
        self.tenant_id = None
        self.user_id = None
        
    def authenticate(self):
        """Authenticate and get token"""
        print("🔐 Authenticating...")
        
        # Try to login with test user
        login_data = {
            "email": "admin@hoteltest.com",
            "password": "admin123"
        }
        
        try:
            response = requests.post(f"{API_BASE}/auth/login", json=login_data)
            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.tenant_id = data['user']['tenant_id']
                self.user_id = data['user']['id']
                print(f"✅ Authentication successful - User: {data['user']['name']}")
                return True
            else:
                print(f"❌ Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    def get_headers(self):
        """Get headers with authorization"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def test_adr_endpoint(self):
        """Test GET /api/revenue-mobile/adr"""
        print("\n📊 Testing ADR Endpoint...")
        
        # Test without date parameters (default last 30 days)
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/adr", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ ADR: {data.get('adr', 'N/A')}")
                print(f"   ✅ Room nights: {data.get('room_nights', 'N/A')}")
                print(f"   ✅ Room revenue: {data.get('room_revenue', 'N/A')}")
                print(f"   ✅ Period: {data.get('period', {}).get('start_date')} to {data.get('period', {}).get('end_date')}")
                print(f"   ✅ Trend: {data.get('comparison', {}).get('trend', 'N/A')}")
                
                # Validate response structure
                required_fields = ['period', 'adr', 'room_nights', 'room_revenue', 'comparison']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        # Test with custom date range
        try:
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            params = {
                'start_date': start_date,
                'end_date': end_date
            }
            
            response = requests.get(f"{API_BASE}/revenue-mobile/adr", headers=self.get_headers(), params=params)
            print(f"   Custom date range: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Custom period ADR: {data.get('adr', 'N/A')}")
            else:
                print(f"   ❌ Custom date error: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Custom date exception: {e}")
        
        return True
    
    def test_revpar_endpoint(self):
        """Test GET /api/revenue-mobile/revpar"""
        print("\n📈 Testing RevPAR Endpoint...")
        
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/revpar", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ RevPAR: {data.get('revpar', 'N/A')}")
                print(f"   ✅ Room revenue: {data.get('room_revenue', 'N/A')}")
                print(f"   ✅ Available room nights: {data.get('available_room_nights', 'N/A')}")
                print(f"   ✅ Occupied room nights: {data.get('occupied_room_nights', 'N/A')}")
                print(f"   ✅ Occupancy %: {data.get('occupancy_pct', 'N/A')}")
                print(f"   ✅ Trend: {data.get('comparison', {}).get('trend', 'N/A')}")
                
                # Validate response structure
                required_fields = ['period', 'revpar', 'room_revenue', 'available_room_nights', 'occupied_room_nights', 'occupancy_pct', 'comparison']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        return True
    
    def test_total_revenue_endpoint(self):
        """Test GET /api/revenue-mobile/total-revenue"""
        print("\n💰 Testing Total Revenue Endpoint...")
        
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/total-revenue", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Total revenue: {data.get('total_revenue', 'N/A')}")
                
                revenue_by_category = data.get('revenue_by_category', {})
                print(f"   ✅ Room revenue: {revenue_by_category.get('room', 'N/A')}")
                print(f"   ✅ Food revenue: {revenue_by_category.get('food', 'N/A')}")
                print(f"   ✅ Beverage revenue: {revenue_by_category.get('beverage', 'N/A')}")
                print(f"   ✅ Minibar revenue: {revenue_by_category.get('minibar', 'N/A')}")
                
                daily_breakdown = data.get('daily_breakdown', [])
                print(f"   ✅ Daily breakdown entries: {len(daily_breakdown)}")
                
                print(f"   ✅ Trend: {data.get('comparison', {}).get('trend', 'N/A')}")
                
                # Validate response structure
                required_fields = ['period', 'total_revenue', 'revenue_by_category', 'daily_breakdown', 'comparison']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        return True
    
    def test_segment_distribution_endpoint(self):
        """Test GET /api/revenue-mobile/segment-distribution"""
        print("\n🎯 Testing Segment Distribution Endpoint...")
        
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/segment-distribution", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Total revenue: {data.get('total_revenue', 'N/A')}")
                
                segments = data.get('segments', [])
                print(f"   ✅ Number of segments: {len(segments)}")
                
                if segments:
                    top_segment = segments[0]
                    print(f"   ✅ Top segment: {top_segment.get('segment', 'N/A')}")
                    print(f"   ✅ Top segment revenue: {top_segment.get('revenue', 'N/A')}")
                    print(f"   ✅ Top segment percentage: {top_segment.get('percentage', 'N/A')}%")
                    print(f"   ✅ Top segment bookings: {top_segment.get('bookings_count', 'N/A')}")
                
                print(f"   ✅ Top segment name: {data.get('top_segment', 'N/A')}")
                
                # Validate response structure
                required_fields = ['period', 'total_revenue', 'segments', 'top_segment']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        return True
    
    def test_pickup_graph_endpoint(self):
        """Test GET /api/revenue-mobile/pickup-graph"""
        print("\n📊 Testing Pickup Graph Endpoint...")
        
        # Test without target_date (default)
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/pickup-graph", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Target date: {data.get('target_date', 'N/A')}")
                print(f"   ✅ Total rooms: {data.get('total_rooms', 'N/A')}")
                print(f"   ✅ Current bookings: {data.get('current_bookings', 'N/A')}")
                print(f"   ✅ Current occupancy: {data.get('current_occupancy', 'N/A')}%")
                
                pickup_data = data.get('pickup_data', [])
                print(f"   ✅ Pickup data points: {len(pickup_data)}")
                
                pickup_velocity = data.get('pickup_velocity', {})
                print(f"   ✅ Last 7 days velocity: {pickup_velocity.get('last_7_days', 'N/A')}")
                print(f"   ✅ Daily average: {pickup_velocity.get('daily_average', 'N/A')}")
                
                year_over_year = data.get('year_over_year', {})
                print(f"   ✅ YoY trend: {year_over_year.get('trend', 'N/A')}")
                print(f"   ✅ YoY change: {year_over_year.get('change_pct', 'N/A')}%")
                
                # Validate response structure
                required_fields = ['target_date', 'total_rooms', 'current_bookings', 'current_occupancy', 'pickup_data', 'pickup_velocity', 'year_over_year']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        # Test with custom target_date
        try:
            target_date = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
            params = {'target_date': target_date}
            
            response = requests.get(f"{API_BASE}/revenue-mobile/pickup-graph", headers=self.get_headers(), params=params)
            print(f"   Custom target date: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Custom target date: {data.get('target_date', 'N/A')}")
            else:
                print(f"   ❌ Custom target error: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Custom target exception: {e}")
        
        return True
    
    def test_forecast_endpoint(self):
        """Test GET /api/revenue-mobile/forecast"""
        print("\n🔮 Testing Forecast Endpoint...")
        
        # Test with default days_ahead (30)
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/forecast", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                forecast_period = data.get('forecast_period', {})
                print(f"   ✅ Forecast period: {forecast_period.get('start_date')} to {forecast_period.get('end_date')}")
                print(f"   ✅ Days: {forecast_period.get('days', 'N/A')}")
                
                summary = data.get('summary', {})
                print(f"   ✅ Total forecast revenue: {summary.get('total_forecast_revenue', 'N/A')}")
                print(f"   ✅ Total room revenue: {summary.get('total_room_revenue', 'N/A')}")
                print(f"   ✅ Avg occupancy: {summary.get('avg_occupancy_pct', 'N/A')}%")
                print(f"   ✅ Total bookings: {summary.get('total_bookings', 'N/A')}")
                
                daily_forecast = data.get('daily_forecast', [])
                print(f"   ✅ Daily forecast entries: {len(daily_forecast)}")
                
                comparison = data.get('comparison', {})
                print(f"   ✅ YoY variance: {comparison.get('variance_pct', 'N/A')}%")
                print(f"   ✅ Trend: {comparison.get('trend', 'N/A')}")
                
                # Validate response structure
                required_fields = ['forecast_period', 'summary', 'daily_forecast', 'comparison']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        # Test with custom days_ahead
        try:
            params = {'days_ahead': 14}
            response = requests.get(f"{API_BASE}/revenue-mobile/forecast", headers=self.get_headers(), params=params)
            print(f"   Custom days_ahead (14): {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                forecast_period = data.get('forecast_period', {})
                print(f"   ✅ Custom forecast days: {forecast_period.get('days', 'N/A')}")
            else:
                print(f"   ❌ Custom days error: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Custom days exception: {e}")
        
        return True
    
    def test_channel_distribution_endpoint(self):
        """Test GET /api/revenue-mobile/channel-distribution"""
        print("\n🌐 Testing Channel Distribution Endpoint...")
        
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/channel-distribution", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                summary = data.get('summary', {})
                print(f"   ✅ Total gross revenue: {summary.get('total_gross_revenue', 'N/A')}")
                print(f"   ✅ Total commission: {summary.get('total_commission', 'N/A')}")
                print(f"   ✅ Total net revenue: {summary.get('total_net_revenue', 'N/A')}")
                print(f"   ✅ Effective commission %: {summary.get('effective_commission_pct', 'N/A')}%")
                
                channels = data.get('channels', [])
                print(f"   ✅ Number of channels: {len(channels)}")
                
                if channels:
                    top_channel = channels[0]
                    print(f"   ✅ Top channel: {top_channel.get('channel', 'N/A')}")
                    print(f"   ✅ Top channel net revenue: {top_channel.get('net_revenue', 'N/A')}")
                    print(f"   ✅ Top channel commission %: {top_channel.get('commission_pct', 'N/A')}%")
                
                print(f"   ✅ Top channel name: {data.get('top_channel', 'N/A')}")
                
                # Validate response structure
                required_fields = ['period', 'summary', 'channels', 'top_channel']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        return True
    
    def test_cancellation_report_endpoint(self):
        """Test GET /api/revenue-mobile/cancellation-report"""
        print("\n❌ Testing Cancellation Report Endpoint...")
        
        try:
            response = requests.get(f"{API_BASE}/revenue-mobile/cancellation-report", headers=self.get_headers())
            print(f"   Default parameters: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                summary = data.get('summary', {})
                print(f"   ✅ Total bookings: {summary.get('total_bookings', 'N/A')}")
                print(f"   ✅ Cancellations: {summary.get('cancellations', 'N/A')}")
                print(f"   ✅ No shows: {summary.get('no_shows', 'N/A')}")
                print(f"   ✅ Cancellation rate: {summary.get('cancellation_rate', 'N/A')}%")
                print(f"   ✅ No show rate: {summary.get('no_show_rate', 'N/A')}%")
                print(f"   ✅ Total lost revenue: {summary.get('total_lost_revenue', 'N/A')}")
                print(f"   ✅ Cancellation fees collected: {summary.get('cancellation_fees_collected', 'N/A')}")
                print(f"   ✅ Net lost revenue: {summary.get('net_lost_revenue', 'N/A')}")
                
                by_channel = data.get('by_channel', [])
                print(f"   ✅ Channels analyzed: {len(by_channel)}")
                
                lead_time = data.get('cancellation_lead_time', {})
                print(f"   ✅ Same day cancellations: {lead_time.get('same_day', 'N/A')}")
                print(f"   ✅ 1-3 days cancellations: {lead_time.get('1_3_days', 'N/A')}")
                
                print(f"   ✅ Top issue channel: {data.get('top_issue_channel', 'N/A')}")
                
                # Validate response structure
                required_fields = ['period', 'summary', 'by_channel', 'cancellation_lead_time', 'top_issue_channel']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        return True
    
    def test_rate_override_endpoint(self):
        """Test POST /api/revenue-mobile/rate-override"""
        print("\n⚡ Testing Rate Override Endpoint...")
        
        # Test with small change (no approval needed)
        try:
            override_data = {
                "room_type": "Standard",
                "date": (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d'),
                "new_rate": 110.0,
                "reason": "Weekend premium pricing"
            }
            
            response = requests.post(f"{API_BASE}/revenue-mobile/rate-override", 
                                   headers=self.get_headers(), 
                                   json=override_data)
            print(f"   Small change (10%): {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Message: {data.get('message', 'N/A')}")
                print(f"   ✅ Override ID: {data.get('override_id', 'N/A')}")
                print(f"   ✅ Status: {data.get('status', 'N/A')}")
                print(f"   ✅ Needs approval: {data.get('needs_approval', 'N/A')}")
                print(f"   ✅ Change %: {data.get('change_pct', 'N/A')}%")
                print(f"   ✅ New rate: {data.get('new_rate', 'N/A')}")
                
                # Validate response structure
                required_fields = ['message', 'override_id', 'status', 'needs_approval', 'change_pct', 'new_rate']
                missing_fields = [field for field in required_fields if field not in data]
                if missing_fields:
                    print(f"   ⚠️ Missing fields: {missing_fields}")
                else:
                    print("   ✅ Response structure valid")
            else:
                print(f"   ❌ Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return False
        
        # Test with large change (approval needed)
        try:
            override_data = {
                "room_type": "Deluxe",
                "date": (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d'),
                "new_rate": 150.0,
                "reason": "Special event pricing - conference in town"
            }
            
            response = requests.post(f"{API_BASE}/revenue-mobile/rate-override", 
                                   headers=self.get_headers(), 
                                   json=override_data)
            print(f"   Large change (50%): {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Needs approval: {data.get('needs_approval', 'N/A')}")
                print(f"   ✅ Change %: {data.get('change_pct', 'N/A')}%")
            else:
                print(f"   ❌ Large change error: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Large change exception: {e}")
        
        # Test with missing fields
        try:
            invalid_data = {
                "room_type": "Standard",
                "date": (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
                # Missing new_rate and reason
            }
            
            response = requests.post(f"{API_BASE}/revenue-mobile/rate-override", 
                                   headers=self.get_headers(), 
                                   json=invalid_data)
            print(f"   Missing fields validation: {response.status_code}")
            
            if response.status_code == 400:
                print("   ✅ Validation working - missing fields rejected")
            else:
                print(f"   ⚠️ Validation issue: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Validation exception: {e}")
        
        return True
    
    def run_all_tests(self):
        """Run all Revenue Mobile endpoint tests"""
        print("🚀 Starting Revenue Mobile API Tests")
        print(f"🌐 Backend URL: {BACKEND_URL}")
        print("=" * 60)
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        test_results = []
        
        # Run all endpoint tests
        test_methods = [
            ('ADR Endpoint', self.test_adr_endpoint),
            ('RevPAR Endpoint', self.test_revpar_endpoint),
            ('Total Revenue Endpoint', self.test_total_revenue_endpoint),
            ('Segment Distribution Endpoint', self.test_segment_distribution_endpoint),
            ('Pickup Graph Endpoint', self.test_pickup_graph_endpoint),
            ('Forecast Endpoint', self.test_forecast_endpoint),
            ('Channel Distribution Endpoint', self.test_channel_distribution_endpoint),
            ('Cancellation Report Endpoint', self.test_cancellation_report_endpoint),
            ('Rate Override Endpoint', self.test_rate_override_endpoint)
        ]
        
        for test_name, test_method in test_methods:
            try:
                result = test_method()
                test_results.append((test_name, result))
            except Exception as e:
                print(f"❌ {test_name} failed with exception: {e}")
                test_results.append((test_name, False))
        
        # Print summary
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        
        passed = 0
        failed = 0
        
        for test_name, result in test_results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} - {test_name}")
            if result:
                passed += 1
            else:
                failed += 1
        
        print(f"\n📊 Results: {passed} passed, {failed} failed")
        
        if failed == 0:
            print("🎉 All Revenue Mobile endpoints are working correctly!")
            return True
        else:
            print(f"⚠️ {failed} endpoint(s) have issues that need attention.")
            return False

def main():
    """Main function"""
    tester = RevenueMobileAPITester()
    success = tester.run_all_tests()
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()