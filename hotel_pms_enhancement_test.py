#!/usr/bin/env python3
"""
Hotel PMS Enhancement Backend Testing
Testing 23 new backend features as documented in test_result.md
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta
import base64

# Configuration
BACKEND_URL = "https://app-audit-9.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class HotelPMSEnhancementTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = {
            "dashboard": {"passed": 0, "failed": 0, "details": []},
            "checkin": {"passed": 0, "failed": 0, "details": []},
            "housekeeping": {"passed": 0, "failed": 0, "details": []},
            "enhanced_details": {"passed": 0, "failed": 0, "details": []},
            "business_ops": {"passed": 0, "failed": 0, "details": []}
        }
        self.created_resources = {
            "guest_ids": [],
            "booking_ids": [],
            "room_ids": [],
            "folio_ids": []
        }

    def authenticate(self):
        """Authenticate with the backend"""
        print("🔐 Authenticating...")
        try:
            response = self.session.post(f"{BACKEND_URL}/auth/login", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data["access_token"]
                self.tenant_id = data["user"]["tenant_id"]
                self.user_id = data["user"]["id"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                })
                print(f"✅ Authentication successful - User: {data['user']['name']}")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False

    def log_test_result(self, category, endpoint, method, success, details=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "endpoint": f"{method} {endpoint}",
            "status": status,
            "details": details
        }
        self.test_results[category]["details"].append(result)
        if success:
            self.test_results[category]["passed"] += 1
        else:
            self.test_results[category]["failed"] += 1
        
        print(f"  {status}: {method} {endpoint} - {details}")

    def test_dashboard_endpoints(self):
        """Test Dashboard Endpoints (3)"""
        print("\n📊 Testing Dashboard Endpoints...")
        
        # 1. GET /api/dashboard/employee-performance
        try:
            response = self.session.get(f"{BACKEND_URL}/dashboard/employee-performance")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                # Verify response structure
                expected_fields = ['housekeeping_staff', 'front_desk_staff', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    hk_staff = data.get('housekeeping_staff', [])
                    fd_staff = data.get('front_desk_staff', [])
                    summary = data.get('summary', {})
                    
                    details += f" - HK staff: {len(hk_staff)}, FD staff: {len(fd_staff)}"
                    
                    # Check staff performance fields
                    if hk_staff:
                        staff = hk_staff[0]
                        staff_fields = ['staff_name', 'avg_cleaning_time', 'performance_rating', 'efficiency_score']
                        present_fields = [field for field in staff_fields if field in staff]
                        details += f" - HK fields: {len(present_fields)}/{len(staff_fields)}"
                    
                    if fd_staff:
                        staff = fd_staff[0]
                        staff_fields = ['staff_name', 'avg_checkin_duration', 'performance_rating', 'efficiency_score']
                        present_fields = [field for field in staff_fields if field in staff]
                        details += f" - FD fields: {len(present_fields)}/{len(staff_fields)}"
            
            self.log_test_result("dashboard", "/dashboard/employee-performance", "GET", success, details)
        except Exception as e:
            self.log_test_result("dashboard", "/dashboard/employee-performance", "GET", False, f"Error: {str(e)}")

        # 2. GET /api/dashboard/guest-satisfaction-trends (7 days)
        try:
            response = self.session.get(f"{BACKEND_URL}/dashboard/guest-satisfaction-trends?days=7")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - 7 days"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['nps_score', 'avg_rating', 'promoters', 'detractors', 'trend_data']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    nps = data.get('nps_score', 0)
                    avg_rating = data.get('avg_rating', 0)
                    promoters = data.get('promoters', 0)
                    detractors = data.get('detractors', 0)
                    trend_data = data.get('trend_data', [])
                    
                    details += f" - NPS: {nps}, Avg: {avg_rating}, Promoters: {promoters}, Detractors: {detractors}"
                    details += f" - Trend points: {len(trend_data)}"
            
            self.log_test_result("dashboard", "/dashboard/guest-satisfaction-trends?days=7", "GET", success, details)
        except Exception as e:
            self.log_test_result("dashboard", "/dashboard/guest-satisfaction-trends?days=7", "GET", False, f"Error: {str(e)}")

        # 3. GET /api/dashboard/guest-satisfaction-trends (30 days)
        try:
            response = self.session.get(f"{BACKEND_URL}/dashboard/guest-satisfaction-trends?days=30")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - 30 days"
            
            if success and response.json():
                data = response.json()
                trend_data = data.get('trend_data', [])
                details += f" - 30-day trend points: {len(trend_data)}"
                
                # Verify 30-day data has more points than 7-day
                if len(trend_data) >= 7:
                    details += " - Extended period data ✓"
                else:
                    details += " - WARNING: Less data than expected for 30 days"
            
            self.log_test_result("dashboard", "/dashboard/guest-satisfaction-trends?days=30", "GET", success, details)
        except Exception as e:
            self.log_test_result("dashboard", "/dashboard/guest-satisfaction-trends?days=30", "GET", False, f"Error: {str(e)}")

        # 4. GET /api/dashboard/ota-cancellation-rate
        try:
            response = self.session.get(f"{BACKEND_URL}/dashboard/ota-cancellation-rate")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['overall_cancellation_rate', 'ota_breakdown', 'revenue_impact', 'cancellation_patterns']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    overall_rate = data.get('overall_cancellation_rate', 0)
                    ota_breakdown = data.get('ota_breakdown', [])
                    revenue_impact = data.get('revenue_impact', {})
                    patterns = data.get('cancellation_patterns', {})
                    
                    details += f" - Overall rate: {overall_rate}%, OTA channels: {len(ota_breakdown)}"
                    
                    if revenue_impact:
                        lost_revenue = revenue_impact.get('lost_revenue', 0)
                        details += f" - Lost revenue: ${lost_revenue}"
            
            self.log_test_result("dashboard", "/dashboard/ota-cancellation-rate", "GET", success, details)
        except Exception as e:
            self.log_test_result("dashboard", "/dashboard/ota-cancellation-rate", "GET", False, f"Error: {str(e)}")

    def test_checkin_enhancements(self):
        """Test Check-in Enhancements (3)"""
        print("\n🏨 Testing Check-in Enhancements...")
        
        # 1. POST /api/frontdesk/passport-scan
        try:
            # Create a simple base64 image for testing
            test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            
            response = self.session.post(f"{BACKEND_URL}/frontdesk/passport-scan", json={
                "image_base64": test_image_b64,
                "booking_id": None
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['extracted_data', 'confidence', 'processing_time', 'ocr_ready']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    extracted_data = data.get('extracted_data', {})
                    confidence = data.get('confidence', 0)
                    ocr_ready = data.get('ocr_ready', False)
                    
                    details += f" - Confidence: {confidence}%, OCR ready: {ocr_ready}"
                    
                    # Check extracted data fields
                    if extracted_data:
                        data_fields = ['name', 'passport_number', 'nationality', 'date_of_birth', 'expiry_date']
                        present_fields = [field for field in data_fields if field in extracted_data]
                        details += f" - Extracted fields: {len(present_fields)}/{len(data_fields)}"
            
            self.log_test_result("checkin", "/frontdesk/passport-scan", "POST", success, details)
        except Exception as e:
            self.log_test_result("checkin", "/frontdesk/passport-scan", "POST", False, f"Error: {str(e)}")

        # 2. POST /api/frontdesk/walk-in-booking
        try:
            response = self.session.post(f"{BACKEND_URL}/frontdesk/walk-in-booking", json={
                "guest_name": "John Walker",
                "guest_email": "john.walker@email.com",
                "guest_phone": "+1234567890",
                "guest_id_number": "ID123456789",
                "room_type": "standard",
                "nights": 2,
                "adults": 2,
                "children": 0,
                "rate": 120.0,
                "create_folio": True,
                "auto_checkin": True
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['guest_id', 'booking_id', 'folio_id', 'room_number', 'checked_in']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    guest_id = data.get('guest_id')
                    booking_id = data.get('booking_id')
                    folio_id = data.get('folio_id')
                    room_number = data.get('room_number')
                    checked_in = data.get('checked_in', False)
                    
                    # Store created resources
                    if guest_id:
                        self.created_resources["guest_ids"].append(guest_id)
                    if booking_id:
                        self.created_resources["booking_ids"].append(booking_id)
                    if folio_id:
                        self.created_resources["folio_ids"].append(folio_id)
                    
                    details += f" - Room: {room_number}, Checked in: {checked_in}"
                    details += f" - Guest created: {guest_id is not None}"
                    details += f" - Folio created: {folio_id is not None}"
            
            self.log_test_result("checkin", "/frontdesk/walk-in-booking", "POST", success, details)
        except Exception as e:
            self.log_test_result("checkin", "/frontdesk/walk-in-booking", "POST", False, f"Error: {str(e)}")

        # 3. GET /api/frontdesk/guest-alerts/{guest_id}
        if self.created_resources["guest_ids"]:
            try:
                guest_id = self.created_resources["guest_ids"][0]
                response = self.session.get(f"{BACKEND_URL}/frontdesk/guest-alerts/{guest_id}")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    expected_fields = ['vip_status', 'birthday_alert', 'special_requests', 'preferences', 'complaints', 'loyalty_status']
                    missing_fields = [field for field in expected_fields if field not in data]
                    
                    if missing_fields:
                        details += f" - Missing fields: {missing_fields}"
                        success = False
                    else:
                        vip_status = data.get('vip_status', False)
                        birthday_alert = data.get('birthday_alert', False)
                        special_requests = data.get('special_requests', [])
                        preferences = data.get('preferences', [])
                        complaints = data.get('complaints', [])
                        loyalty_status = data.get('loyalty_status', {})
                        
                        details += f" - VIP: {vip_status}, Birthday: {birthday_alert}"
                        details += f" - Requests: {len(special_requests)}, Preferences: {len(preferences)}"
                        details += f" - Complaints: {len(complaints)}"
                        
                        if loyalty_status:
                            tier = loyalty_status.get('tier', 'N/A')
                            points = loyalty_status.get('points', 0)
                            details += f" - Loyalty: {tier} ({points} pts)"
                
                self.log_test_result("checkin", f"/frontdesk/guest-alerts/{guest_id}", "GET", success, details)
            except Exception as e:
                self.log_test_result("checkin", f"/frontdesk/guest-alerts/{guest_id}", "GET", False, f"Error: {str(e)}")
        else:
            self.log_test_result("checkin", "/frontdesk/guest-alerts/{guest_id}", "GET", False, "No guest ID available for testing")

    def test_housekeeping_endpoints(self):
        """Test Housekeeping (3)"""
        print("\n🧹 Testing Housekeeping Endpoints...")
        
        # 1. GET /api/housekeeping/task-timing
        try:
            response = self.session.get(f"{BACKEND_URL}/housekeeping/task-timing")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['avg_duration', 'min_duration', 'max_duration', 'staff_performance', 'task_analysis', 'efficiency_ratings']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    avg_duration = data.get('avg_duration', 0)
                    min_duration = data.get('min_duration', 0)
                    max_duration = data.get('max_duration', 0)
                    staff_performance = data.get('staff_performance', [])
                    task_analysis = data.get('task_analysis', [])
                    
                    details += f" - Avg: {avg_duration}min, Range: {min_duration}-{max_duration}min"
                    details += f" - Staff: {len(staff_performance)}, Tasks: {len(task_analysis)}"
                    
                    # Check staff performance structure
                    if staff_performance:
                        staff = staff_performance[0]
                        staff_fields = ['staff_name', 'avg_time', 'efficiency_score', 'tasks_completed']
                        present_fields = [field for field in staff_fields if field in staff]
                        details += f" - Staff fields: {len(present_fields)}/{len(staff_fields)}"
            
            self.log_test_result("housekeeping", "/housekeeping/task-timing", "GET", success, details)
        except Exception as e:
            self.log_test_result("housekeeping", "/housekeeping/task-timing", "GET", False, f"Error: {str(e)}")

        # 2. GET /api/housekeeping/staff-performance-table
        try:
            response = self.session.get(f"{BACKEND_URL}/housekeeping/staff-performance-table")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['staff_performance', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    staff_performance = data.get('staff_performance', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Staff members: {len(staff_performance)}"
                    
                    # Check detailed staff performance structure
                    if staff_performance:
                        staff = staff_performance[0]
                        staff_fields = ['staff_name', 'quality_score', 'overall_performance', 'tasks_per_day', 'avg_completion_time']
                        present_fields = [field for field in staff_fields if field in staff]
                        details += f" - Performance fields: {len(present_fields)}/{len(staff_fields)}"
                        
                        quality_score = staff.get('quality_score', 0)
                        overall_performance = staff.get('overall_performance', 'N/A')
                        details += f" - Quality: {quality_score}, Performance: {overall_performance}"
                    
                    # Check summary
                    if summary:
                        avg_quality = summary.get('avg_quality_score', 0)
                        top_performer = summary.get('top_performer', 'N/A')
                        details += f" - Avg quality: {avg_quality}, Top: {top_performer}"
            
            self.log_test_result("housekeeping", "/housekeeping/staff-performance-table", "GET", success, details)
        except Exception as e:
            self.log_test_result("housekeeping", "/housekeeping/staff-performance-table", "GET", False, f"Error: {str(e)}")

        # 3. GET /api/housekeeping/linen-inventory
        try:
            response = self.session.get(f"{BACKEND_URL}/housekeeping/linen-inventory")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['inventory', 'low_stock_alerts', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    inventory = data.get('inventory', [])
                    low_stock_alerts = data.get('low_stock_alerts', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Inventory items: {len(inventory)}, Alerts: {len(low_stock_alerts)}"
                    
                    # Check inventory item structure
                    if inventory:
                        item = inventory[0]
                        item_fields = ['item_type', 'stock_quantity', 'in_use_quantity', 'laundry_quantity', 'damaged_quantity']
                        present_fields = [field for field in item_fields if field in item]
                        details += f" - Item fields: {len(present_fields)}/{len(item_fields)}"
                        
                        item_type = item.get('item_type', 'N/A')
                        stock = item.get('stock_quantity', 0)
                        in_use = item.get('in_use_quantity', 0)
                        details += f" - {item_type}: Stock {stock}, In use {in_use}"
                    
                    # Check summary
                    if summary:
                        total_items = summary.get('total_items', 0)
                        critical_items = summary.get('critical_stock_items', 0)
                        details += f" - Total: {total_items}, Critical: {critical_items}"
            
            self.log_test_result("housekeeping", "/housekeeping/linen-inventory", "GET", success, details)
        except Exception as e:
            self.log_test_result("housekeeping", "/housekeeping/linen-inventory", "GET", False, f"Error: {str(e)}")

    def test_enhanced_details_endpoints(self):
        """Test Enhanced Details (3)"""
        print("\n📋 Testing Enhanced Details Endpoints...")
        
        # First, get a room ID for testing
        room_id = None
        try:
            response = self.session.get(f"{BACKEND_URL}/pms/rooms")
            if response.status_code == 200:
                rooms = response.json()
                if rooms:
                    room_id = rooms[0].get('id')
        except:
            pass
        
        # 1. GET /api/rooms/{room_id}/details-enhanced
        if room_id:
            try:
                response = self.session.get(f"{BACKEND_URL}/rooms/{room_id}/details-enhanced")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    expected_fields = ['room_details', 'notes', 'minibar_status', 'maintenance_due', 'last_inspection']
                    missing_fields = [field for field in expected_fields if field not in data]
                    
                    if missing_fields:
                        details += f" - Missing fields: {missing_fields}"
                        success = False
                    else:
                        room_details = data.get('room_details', {})
                        notes = data.get('notes', [])
                        minibar_status = data.get('minibar_status', {})
                        maintenance_due = data.get('maintenance_due', None)
                        
                        details += f" - Notes: {len(notes)}, Maintenance due: {maintenance_due is not None}"
                        
                        # Check minibar status
                        if minibar_status:
                            items = minibar_status.get('items', [])
                            last_restocked = minibar_status.get('last_restocked')
                            details += f" - Minibar items: {len(items)}, Last restocked: {last_restocked is not None}"
                
                self.log_test_result("enhanced_details", f"/rooms/{room_id}/details-enhanced", "GET", success, details)
            except Exception as e:
                self.log_test_result("enhanced_details", f"/rooms/{room_id}/details-enhanced", "GET", False, f"Error: {str(e)}")
        else:
            self.log_test_result("enhanced_details", "/rooms/{room_id}/details-enhanced", "GET", False, "No room ID available for testing")

        # 2. GET /api/guests/{guest_id}/profile-enhanced
        if self.created_resources["guest_ids"]:
            try:
                guest_id = self.created_resources["guest_ids"][0]
                response = self.session.get(f"{BACKEND_URL}/guests/{guest_id}/profile-enhanced")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    expected_fields = ['guest_profile', 'stay_history', 'preferences', 'tags', 'ltv_calculation']
                    missing_fields = [field for field in expected_fields if field not in data]
                    
                    if missing_fields:
                        details += f" - Missing fields: {missing_fields}"
                        success = False
                    else:
                        guest_profile = data.get('guest_profile', {})
                        stay_history = data.get('stay_history', [])
                        preferences = data.get('preferences', {})
                        tags = data.get('tags', [])
                        ltv_calculation = data.get('ltv_calculation', {})
                        
                        details += f" - Stays: {len(stay_history)}, Tags: {len(tags)}"
                        
                        # Check preferences structure
                        if preferences:
                            pref_fields = ['pillow_type', 'room_temperature', 'smoking_preference']
                            present_prefs = [field for field in pref_fields if field in preferences]
                            details += f" - Preferences: {len(present_prefs)}/{len(pref_fields)}"
                        
                        # Check LTV calculation
                        if ltv_calculation:
                            ltv_value = ltv_calculation.get('ltv_value', 0)
                            details += f" - LTV: ${ltv_value}"
                
                self.log_test_result("enhanced_details", f"/guests/{guest_id}/profile-enhanced", "GET", success, details)
            except Exception as e:
                self.log_test_result("enhanced_details", f"/guests/{guest_id}/profile-enhanced", "GET", False, f"Error: {str(e)}")
        else:
            self.log_test_result("enhanced_details", "/guests/{guest_id}/profile-enhanced", "GET", False, "No guest ID available for testing")

        # 3. GET /api/reservations/{booking_id}/details-enhanced
        if self.created_resources["booking_ids"]:
            try:
                booking_id = self.created_resources["booking_ids"][0]
                response = self.session.get(f"{BACKEND_URL}/reservations/{booking_id}/details-enhanced")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    expected_fields = ['reservation_details', 'cancellation_policy', 'ota_commission', 'rate_breakdown']
                    missing_fields = [field for field in expected_fields if field not in data]
                    
                    if missing_fields:
                        details += f" - Missing fields: {missing_fields}"
                        success = False
                    else:
                        reservation_details = data.get('reservation_details', {})
                        cancellation_policy = data.get('cancellation_policy', {})
                        ota_commission = data.get('ota_commission', {})
                        rate_breakdown = data.get('rate_breakdown', {})
                        
                        # Check cancellation policy
                        if cancellation_policy:
                            policy_type = cancellation_policy.get('policy_type', 'N/A')
                            free_cancellation_until = cancellation_policy.get('free_cancellation_until')
                            details += f" - Policy: {policy_type}"
                        
                        # Check OTA commission breakdown
                        if ota_commission:
                            gross_revenue = ota_commission.get('gross_revenue', 0)
                            net_revenue = ota_commission.get('net_revenue', 0)
                            commission_pct = ota_commission.get('commission_pct', 0)
                            details += f" - Gross: ${gross_revenue}, Net: ${net_revenue}, Commission: {commission_pct}%"
                        
                        # Check rate breakdown
                        if rate_breakdown:
                            base_rate = rate_breakdown.get('base_rate', 0)
                            taxes = rate_breakdown.get('taxes', 0)
                            fees = rate_breakdown.get('fees', 0)
                            details += f" - Base: ${base_rate}, Taxes: ${taxes}, Fees: ${fees}"
                
                self.log_test_result("enhanced_details", f"/reservations/{booking_id}/details-enhanced", "GET", success, details)
            except Exception as e:
                self.log_test_result("enhanced_details", f"/reservations/{booking_id}/details-enhanced", "GET", False, f"Error: {str(e)}")
        else:
            self.log_test_result("enhanced_details", "/reservations/{booking_id}/details-enhanced", "GET", False, "No booking ID available for testing")

    def test_business_operations_endpoints(self):
        """Test Business Operations (11)"""
        print("\n💼 Testing Business Operations Endpoints...")
        
        # 1. POST /api/accounting/send-statement
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/send-statement", json={
                "company_id": "test-company-123",
                "statement_period": "2025-01",
                "email": "accounting@company.com",
                "include_details": True
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['statement_sent', 'statement_id', 'email_sent', 'total_amount']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    statement_sent = data.get('statement_sent', False)
                    statement_id = data.get('statement_id')
                    email_sent = data.get('email_sent', False)
                    total_amount = data.get('total_amount', 0)
                    
                    details += f" - Sent: {statement_sent}, Email: {email_sent}, Amount: ${total_amount}"
            
            self.log_test_result("business_ops", "/accounting/send-statement", "POST", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/accounting/send-statement", "POST", False, f"Error: {str(e)}")

        # 2. GET /api/accounting/smart-alerts
        try:
            response = self.session.get(f"{BACKEND_URL}/accounting/smart-alerts")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['overdue_alerts', 'credit_limit_alerts', 'payment_reminders', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    overdue_alerts = data.get('overdue_alerts', [])
                    credit_limit_alerts = data.get('credit_limit_alerts', [])
                    payment_reminders = data.get('payment_reminders', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Overdue: {len(overdue_alerts)}, Credit: {len(credit_limit_alerts)}, Reminders: {len(payment_reminders)}"
                    
                    if summary:
                        total_overdue = summary.get('total_overdue_amount', 0)
                        details += f" - Total overdue: ${total_overdue}"
            
            self.log_test_result("business_ops", "/accounting/smart-alerts", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/accounting/smart-alerts", "GET", False, f"Error: {str(e)}")

        # 3. POST /api/pos/check-split
        try:
            response = self.session.post(f"{BACKEND_URL}/pos/check-split", json={
                "transaction_id": "test-transaction-123",
                "split_type": "equal",
                "split_count": 3,
                "custom_amounts": None
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['split_successful', 'split_transactions', 'original_amount', 'split_amounts']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    split_successful = data.get('split_successful', False)
                    split_transactions = data.get('split_transactions', [])
                    original_amount = data.get('original_amount', 0)
                    split_amounts = data.get('split_amounts', [])
                    
                    details += f" - Split: {split_successful}, Transactions: {len(split_transactions)}"
                    details += f" - Original: ${original_amount}, Splits: {len(split_amounts)}"
            
            self.log_test_result("business_ops", "/pos/check-split", "POST", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/pos/check-split", "POST", False, f"Error: {str(e)}")

        # 4. POST /api/pos/transfer-table
        try:
            response = self.session.post(f"{BACKEND_URL}/pos/transfer-table", json={
                "from_table": "12",
                "to_table": "15",
                "transaction_id": "test-transaction-456",
                "reason": "Guest request"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['transfer_successful', 'new_transaction_id', 'from_table', 'to_table']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    transfer_successful = data.get('transfer_successful', False)
                    new_transaction_id = data.get('new_transaction_id')
                    from_table = data.get('from_table')
                    to_table = data.get('to_table')
                    
                    details += f" - Transfer: {transfer_successful}, From: {from_table}, To: {to_table}"
            
            self.log_test_result("business_ops", "/pos/transfer-table", "POST", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/pos/transfer-table", "POST", False, f"Error: {str(e)}")

        # 5. GET /api/channel-manager/rate-parity-check
        try:
            response = self.session.get(f"{BACKEND_URL}/channel-manager/rate-parity-check")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['parity_results', 'negative_disparity_alerts', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    parity_results = data.get('parity_results', [])
                    negative_alerts = data.get('negative_disparity_alerts', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Parity checks: {len(parity_results)}, Alerts: {len(negative_alerts)}"
                    
                    if summary:
                        avg_disparity = summary.get('avg_disparity_pct', 0)
                        details += f" - Avg disparity: {avg_disparity}%"
            
            self.log_test_result("business_ops", "/channel-manager/rate-parity-check", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/channel-manager/rate-parity-check", "GET", False, f"Error: {str(e)}")

        # 6. GET /api/channel-manager/sync-history
        try:
            response = self.session.get(f"{BACKEND_URL}/channel-manager/sync-history")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['sync_logs', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    sync_logs = data.get('sync_logs', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Sync logs: {len(sync_logs)}"
                    
                    if sync_logs:
                        log = sync_logs[0]
                        log_fields = ['channel', 'sync_type', 'status', 'timestamp', 'records_synced']
                        present_fields = [field for field in log_fields if field in log]
                        details += f" - Log fields: {len(present_fields)}/{len(log_fields)}"
                    
                    if summary:
                        successful_syncs = summary.get('successful_syncs', 0)
                        failed_syncs = summary.get('failed_syncs', 0)
                        details += f" - Success: {successful_syncs}, Failed: {failed_syncs}"
            
            self.log_test_result("business_ops", "/channel-manager/sync-history", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/channel-manager/sync-history", "GET", False, f"Error: {str(e)}")

        # 7. POST /api/rms/restrictions
        try:
            response = self.session.post(f"{BACKEND_URL}/rms/restrictions", json={
                "room_type": "deluxe",
                "date": "2025-02-14",
                "min_los": 2,
                "cta": True,
                "ctd": False,
                "stop_sell": False,
                "reason": "Valentine's Day weekend"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['restriction_applied', 'restriction_id', 'room_type', 'date', 'restrictions']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    restriction_applied = data.get('restriction_applied', False)
                    restriction_id = data.get('restriction_id')
                    restrictions = data.get('restrictions', {})
                    
                    details += f" - Applied: {restriction_applied}, ID: {restriction_id is not None}"
                    
                    if restrictions:
                        min_los = restrictions.get('min_los', 0)
                        cta = restrictions.get('cta', False)
                        ctd = restrictions.get('ctd', False)
                        details += f" - MinLOS: {min_los}, CTA: {cta}, CTD: {ctd}"
            
            self.log_test_result("business_ops", "/rms/restrictions", "POST", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/rms/restrictions", "POST", False, f"Error: {str(e)}")

        # 8. GET /api/rms/market-compression
        try:
            response = self.session.get(f"{BACKEND_URL}/rms/market-compression")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['compression_score', 'pricing_recommendations', 'market_analysis']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    compression_score = data.get('compression_score', 0)
                    pricing_recommendations = data.get('pricing_recommendations', [])
                    market_analysis = data.get('market_analysis', {})
                    
                    details += f" - Compression: {compression_score}, Recommendations: {len(pricing_recommendations)}"
                    
                    if market_analysis:
                        demand_level = market_analysis.get('demand_level', 'N/A')
                        competitor_avg = market_analysis.get('competitor_avg_rate', 0)
                        details += f" - Demand: {demand_level}, Comp avg: ${competitor_avg}"
            
            self.log_test_result("business_ops", "/rms/market-compression", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/rms/market-compression", "GET", False, f"Error: {str(e)}")

        # 9. GET /api/maintenance/repeat-issues
        try:
            response = self.session.get(f"{BACKEND_URL}/maintenance/repeat-issues")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['repeat_issues', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    repeat_issues = data.get('repeat_issues', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Repeat issues: {len(repeat_issues)}"
                    
                    if repeat_issues:
                        issue = repeat_issues[0]
                        issue_fields = ['room_number', 'issue_type', 'occurrence_count', 'last_occurrence', 'avg_resolution_time']
                        present_fields = [field for field in issue_fields if field in issue]
                        details += f" - Issue fields: {len(present_fields)}/{len(issue_fields)}"
                    
                    if summary:
                        total_repeat_issues = summary.get('total_repeat_issues', 0)
                        most_common_issue = summary.get('most_common_issue', 'N/A')
                        details += f" - Total: {total_repeat_issues}, Common: {most_common_issue}"
            
            self.log_test_result("business_ops", "/maintenance/repeat-issues", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/maintenance/repeat-issues", "GET", False, f"Error: {str(e)}")

        # 10. GET /api/maintenance/sla-metrics
        try:
            response = self.session.get(f"{BACKEND_URL}/maintenance/sla-metrics")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['sla_performance', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    sla_performance = data.get('sla_performance', [])
                    summary = data.get('summary', {})
                    
                    details += f" - SLA records: {len(sla_performance)}"
                    
                    if summary:
                        avg_response_time = summary.get('avg_response_time_hours', 0)
                        sla_compliance = summary.get('sla_compliance_pct', 0)
                        overdue_tasks = summary.get('overdue_tasks', 0)
                        details += f" - Avg response: {avg_response_time}h, Compliance: {sla_compliance}%, Overdue: {overdue_tasks}"
            
            self.log_test_result("business_ops", "/maintenance/sla-metrics", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/maintenance/sla-metrics", "GET", False, f"Error: {str(e)}")

        # 11. POST /api/feedback/ai-sentiment-analysis
        try:
            response = self.session.post(f"{BACKEND_URL}/feedback/ai-sentiment-analysis", json={
                "review_text": "The hotel was amazing! Great service, clean rooms, and excellent breakfast. Highly recommend!",
                "source": "booking_com",
                "guest_id": None
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['sentiment_score', 'sentiment_label', 'confidence', 'key_topics', 'ai_ready']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    sentiment_score = data.get('sentiment_score', 0)
                    sentiment_label = data.get('sentiment_label', 'N/A')
                    confidence = data.get('confidence', 0)
                    key_topics = data.get('key_topics', [])
                    ai_ready = data.get('ai_ready', False)
                    
                    details += f" - Sentiment: {sentiment_label} ({sentiment_score}), Confidence: {confidence}%"
                    details += f" - Topics: {len(key_topics)}, AI ready: {ai_ready}"
            
            self.log_test_result("business_ops", "/feedback/ai-sentiment-analysis", "POST", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/feedback/ai-sentiment-analysis", "POST", False, f"Error: {str(e)}")

        # Additional endpoints from the review request...
        
        # 12. GET /api/loyalty/{guest_id}/benefits
        if self.created_resources["guest_ids"]:
            try:
                guest_id = self.created_resources["guest_ids"][0]
                response = self.session.get(f"{BACKEND_URL}/loyalty/{guest_id}/benefits")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    expected_fields = ['tier_benefits', 'points_status', 'ltv_calculation', 'redemption_options']
                    missing_fields = [field for field in expected_fields if field not in data]
                    
                    if missing_fields:
                        details += f" - Missing fields: {missing_fields}"
                        success = False
                    else:
                        tier_benefits = data.get('tier_benefits', {})
                        points_status = data.get('points_status', {})
                        ltv_calculation = data.get('ltv_calculation', {})
                        redemption_options = data.get('redemption_options', [])
                        
                        if tier_benefits:
                            tier = tier_benefits.get('tier', 'N/A')
                            benefits = tier_benefits.get('benefits', [])
                            details += f" - Tier: {tier}, Benefits: {len(benefits)}"
                        
                        if points_status:
                            current_points = points_status.get('current_points', 0)
                            expiring_points = points_status.get('expiring_points', 0)
                            details += f" - Points: {current_points}, Expiring: {expiring_points}"
                
                self.log_test_result("business_ops", f"/loyalty/{guest_id}/benefits", "GET", success, details)
            except Exception as e:
                self.log_test_result("business_ops", f"/loyalty/{guest_id}/benefits", "GET", False, f"Error: {str(e)}")
        else:
            self.log_test_result("business_ops", "/loyalty/{guest_id}/benefits", "GET", False, "No guest ID available for testing")

        # 13. GET /api/procurement/auto-purchase-suggestions
        try:
            response = self.session.get(f"{BACKEND_URL}/procurement/auto-purchase-suggestions")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['purchase_suggestions', 'consumption_analysis', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    suggestions = data.get('purchase_suggestions', [])
                    consumption_analysis = data.get('consumption_analysis', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Suggestions: {len(suggestions)}, Analysis: {len(consumption_analysis)}"
                    
                    if suggestions:
                        suggestion = suggestions[0]
                        sugg_fields = ['item_name', 'suggested_quantity', 'consumption_rate', 'days_until_stockout']
                        present_fields = [field for field in sugg_fields if field in suggestion]
                        details += f" - Suggestion fields: {len(present_fields)}/{len(sugg_fields)}"
            
            self.log_test_result("business_ops", "/procurement/auto-purchase-suggestions", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/procurement/auto-purchase-suggestions", "GET", False, f"Error: {str(e)}")

        # 14. GET /api/contracted-rates/allotment-utilization
        try:
            response = self.session.get(f"{BACKEND_URL}/contracted-rates/allotment-utilization")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['allotment_status', 'utilization_alerts', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    allotment_status = data.get('allotment_status', [])
                    utilization_alerts = data.get('utilization_alerts', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Allotments: {len(allotment_status)}, Alerts: {len(utilization_alerts)}"
                    
                    if allotment_status:
                        allotment = allotment_status[0]
                        allot_fields = ['company_name', 'total_allotment', 'used_rooms', 'utilization_pct']
                        present_fields = [field for field in allot_fields if field in allotment]
                        details += f" - Allotment fields: {len(present_fields)}/{len(allot_fields)}"
            
            self.log_test_result("business_ops", "/contracted-rates/allotment-utilization", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/contracted-rates/allotment-utilization", "GET", False, f"Error: {str(e)}")

        # 15. GET /api/reservations/double-booking-check
        try:
            response = self.session.get(f"{BACKEND_URL}/reservations/double-booking-check")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['conflicts', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    conflicts = data.get('conflicts', [])
                    summary = data.get('summary', {})
                    
                    details += f" - Conflicts: {len(conflicts)}"
                    
                    if conflicts:
                        conflict = conflicts[0]
                        conflict_fields = ['room_number', 'conflicting_bookings', 'conflict_type', 'resolution_needed']
                        present_fields = [field for field in conflict_fields if field in conflict]
                        details += f" - Conflict fields: {len(present_fields)}/{len(conflict_fields)}"
                    
                    if summary:
                        total_conflicts = summary.get('total_conflicts', 0)
                        critical_conflicts = summary.get('critical_conflicts', 0)
                        details += f" - Total: {total_conflicts}, Critical: {critical_conflicts}"
            
            self.log_test_result("business_ops", "/reservations/double-booking-check", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/reservations/double-booking-check", "GET", False, f"Error: {str(e)}")

        # 16. GET /api/reservations/adr-visibility
        try:
            response = self.session.get(f"{BACKEND_URL}/reservations/adr-visibility?start_date=2025-01-01&end_date=2025-01-31")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - Date range"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['adr_by_rate_code', 'adr_by_channel', 'overall_adr', 'summary']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    adr_by_rate_code = data.get('adr_by_rate_code', [])
                    adr_by_channel = data.get('adr_by_channel', [])
                    overall_adr = data.get('overall_adr', 0)
                    summary = data.get('summary', {})
                    
                    details += f" - Rate codes: {len(adr_by_rate_code)}, Channels: {len(adr_by_channel)}"
                    details += f" - Overall ADR: ${overall_adr}"
                    
                    if summary:
                        highest_adr = summary.get('highest_adr_rate_code', 'N/A')
                        lowest_adr = summary.get('lowest_adr_rate_code', 'N/A')
                        details += f" - Highest: {highest_adr}, Lowest: {lowest_adr}"
            
            self.log_test_result("business_ops", "/reservations/adr-visibility", "GET", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/reservations/adr-visibility", "GET", False, f"Error: {str(e)}")

        # 17. POST /api/reservations/rate-override-panel
        try:
            response = self.session.post(f"{BACKEND_URL}/reservations/rate-override-panel", json={
                "booking_id": "test-booking-789",
                "new_rate": 150.0,
                "override_reason": "Manager approval for VIP guest",
                "authorization_code": "MGR001"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                expected_fields = ['override_applied', 'override_log_id', 'old_rate', 'new_rate', 'authorization_required']
                missing_fields = [field for field in expected_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    override_applied = data.get('override_applied', False)
                    override_log_id = data.get('override_log_id')
                    old_rate = data.get('old_rate', 0)
                    new_rate = data.get('new_rate', 0)
                    authorization_required = data.get('authorization_required', False)
                    
                    details += f" - Applied: {override_applied}, Old: ${old_rate}, New: ${new_rate}"
                    details += f" - Auth required: {authorization_required}, Log ID: {override_log_id is not None}"
            
            self.log_test_result("business_ops", "/reservations/rate-override-panel", "POST", success, details)
        except Exception as e:
            self.log_test_result("business_ops", "/reservations/rate-override-panel", "POST", False, f"Error: {str(e)}")

    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*80)
        print("🏨 HOTEL PMS ENHANCEMENT TESTING SUMMARY")
        print("="*80)
        
        total_passed = 0
        total_failed = 0
        
        for category, results in self.test_results.items():
            passed = results["passed"]
            failed = results["failed"]
            total = passed + failed
            
            total_passed += passed
            total_failed += failed
            
            if total > 0:
                success_rate = (passed / total) * 100
                status_icon = "✅" if success_rate >= 80 else "⚠️" if success_rate >= 60 else "❌"
                
                print(f"\n{status_icon} {category.upper().replace('_', ' ')}: {passed}/{total} ({success_rate:.1f}%)")
                
                # Show failed tests
                failed_tests = [detail for detail in results["details"] if "❌ FAIL" in detail["status"]]
                if failed_tests:
                    print("   Failed tests:")
                    for test in failed_tests[:3]:  # Show first 3 failures
                        print(f"     - {test['endpoint']}: {test['details']}")
                    if len(failed_tests) > 3:
                        print(f"     ... and {len(failed_tests) - 3} more")
        
        # Overall summary
        total_tests = total_passed + total_failed
        if total_tests > 0:
            overall_success_rate = (total_passed / total_tests) * 100
            print(f"\n🎯 OVERALL RESULTS: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
            
            if overall_success_rate >= 90:
                print("🌟 EXCELLENT: All major Hotel PMS enhancements are working correctly!")
            elif overall_success_rate >= 80:
                print("✅ GOOD: Most Hotel PMS enhancements are functional with minor issues.")
            elif overall_success_rate >= 60:
                print("⚠️ MODERATE: Several Hotel PMS enhancements need attention.")
            else:
                print("❌ CRITICAL: Major issues found in Hotel PMS enhancements.")
        
        print("\n" + "="*80)
        
        return {
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_failed,
            "success_rate": overall_success_rate if total_tests > 0 else 0,
            "category_results": self.test_results
        }

    def run_all_tests(self):
        """Run all Hotel PMS enhancement tests"""
        print("🚀 Starting Hotel PMS Enhancement Backend Testing...")
        print("Testing 23 new backend features across 5 categories")
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with testing.")
            return False
        
        # Run all test categories
        self.test_dashboard_endpoints()
        self.test_checkin_enhancements()
        self.test_housekeeping_endpoints()
        self.test_enhanced_details_endpoints()
        self.test_business_operations_endpoints()
        
        # Print comprehensive summary
        results = self.print_summary()
        
        return results["success_rate"] >= 80

def main():
    """Main function"""
    tester = HotelPMSEnhancementTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ Hotel PMS Enhancement testing completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Hotel PMS Enhancement testing completed with issues.")
        sys.exit(1)

if __name__ == "__main__":
    main()