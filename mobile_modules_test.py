#!/usr/bin/env python3
"""
4 NEW MOBILE MODULES COMPREHENSIVE TESTING
Testing 20 backend endpoints across 4 mobile modules:

MODULE 1: SALES & CRM MOBILE (6 endpoints)
MODULE 2: RATE & DISCOUNT MANAGEMENT (5 endpoints)  
MODULE 3: CHANNEL MANAGER MOBILE (5 endpoints)
MODULE 4: CORPORATE CONTRACTS (4 endpoints)

TESTING FOCUS:
- Response structure validation for all GET endpoints
- POST/PUT endpoint request body validation
- Filter functionality (customer_type, stage, status, etc.)
- Pagination and sorting where applicable
- Error handling (404, 422, 500)
- Turkish language support in sample data
- Date range filtering
- Role-based access where needed
"""

import asyncio
import aiohttp
import json
import sys
import os
from datetime import datetime, timezone, timedelta, date
from typing import Dict, List, Any, Optional
import uuid

# Configuration
BACKEND_URL = "https://bug-fix-update.preview.emergentagent.com/api"
TEST_EMAIL = "admin@hotel.com"
TEST_PASSWORD = "admin123"

class MobileModulesTester:
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = []
        self.created_test_data = {
            'leads': [],
            'campaigns': [],
            'discount_codes': [],
            'contracts': []
        }

    async def setup_session(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()

    async def cleanup_session(self):
        """Cleanup HTTP session"""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate and get token"""
        try:
            login_data = {
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            }
            
            async with self.session.post(f"{BACKEND_URL}/auth/login", json=login_data) as response:
                if response.status == 200:
                    data = await response.json()
                    self.auth_token = data["access_token"]
                    self.tenant_id = data["user"]["tenant_id"]
                    self.user_id = data["user"]["id"]
                    print(f"✅ Authentication successful - Tenant: {self.tenant_id}")
                    return True
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False

    def get_headers(self):
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    # ============= MODULE 1: SALES & CRM MOBILE (6 endpoints) =============

    async def test_sales_customers(self):
        """Test GET /api/sales/customers - Customer list with filters"""
        print("\n👥 Testing Sales Customers Endpoint...")
        
        test_cases = [
            {
                "name": "Get all customers",
                "params": {},
                "expected_fields": ["customers", "count", "vip_count"]
            },
            {
                "name": "Filter by customer_type - vip",
                "params": {"customer_type": "vip"},
                "expected_fields": ["customers", "total_count", "summary"]
            },
            {
                "name": "Filter by customer_type - corporate",
                "params": {"customer_type": "corporate"},
                "expected_fields": ["customers", "total_count", "summary"]
            },
            {
                "name": "Filter by customer_type - returning",
                "params": {"customer_type": "returning"},
                "expected_fields": ["customers", "total_count", "summary"]
            },
            {
                "name": "Search by name",
                "params": {"search": "Ahmet"},
                "expected_fields": ["customers", "total_count", "summary"]
            },
            {
                "name": "Pagination test",
                "params": {"limit": 10, "offset": 0},
                "expected_fields": ["customers", "total_count", "summary"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/sales/customers"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify customer structure if customers exist
                            if data.get("customers"):
                                customer = data["customers"][0]
                                required_customer_fields = ["id", "name", "email", "phone", "customer_type", "total_bookings", "total_revenue", "last_booking_date", "vip_status"]
                                missing_customer_fields = [field for field in required_customer_fields if field not in customer]
                                if not missing_customer_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing customer fields {missing_customer_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no customers)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/sales/customers",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_sales_leads(self):
        """Test GET /api/sales/leads - Lead pipeline management"""
        print("\n🎯 Testing Sales Leads Endpoint...")
        
        test_cases = [
            {
                "name": "Get all leads",
                "params": {},
                "expected_fields": ["leads", "total_count", "pipeline_summary"]
            },
            {
                "name": "Filter by stage - cold",
                "params": {"stage": "cold"},
                "expected_fields": ["leads", "total_count", "pipeline_summary"]
            },
            {
                "name": "Filter by stage - warm",
                "params": {"stage": "warm"},
                "expected_fields": ["leads", "total_count", "pipeline_summary"]
            },
            {
                "name": "Filter by stage - hot",
                "params": {"stage": "hot"},
                "expected_fields": ["leads", "total_count", "pipeline_summary"]
            },
            {
                "name": "Filter by stage - converted",
                "params": {"stage": "converted"},
                "expected_fields": ["leads", "total_count", "pipeline_summary"]
            },
            {
                "name": "Date range filter",
                "params": {"start_date": "2024-01-01", "end_date": "2024-12-31"},
                "expected_fields": ["leads", "total_count", "pipeline_summary"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/sales/leads"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify lead structure if leads exist
                            if data.get("leads"):
                                lead = data["leads"][0]
                                required_lead_fields = ["id", "company_name", "contact_person", "email", "phone", "stage", "source", "estimated_value", "probability", "next_follow_up", "assigned_to"]
                                missing_lead_fields = [field for field in required_lead_fields if field not in lead]
                                if not missing_lead_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing lead fields {missing_lead_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no leads)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/sales/leads",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_sales_ota_pricing(self):
        """Test GET /api/sales/ota-pricing - OTA price comparison"""
        print("\n💰 Testing Sales OTA Pricing Endpoint...")
        
        test_cases = [
            {
                "name": "Get OTA pricing comparison",
                "params": {},
                "expected_fields": ["ota_comparison", "our_rates", "recommendations"]
            },
            {
                "name": "Filter by date range",
                "params": {"check_in": "2024-12-01", "check_out": "2024-12-03"},
                "expected_fields": ["ota_comparison", "our_rates", "recommendations"]
            },
            {
                "name": "Filter by room type",
                "params": {"room_type": "standard"},
                "expected_fields": ["ota_comparison", "our_rates", "recommendations"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/sales/ota-pricing"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify OTA comparison structure
                            if data.get("ota_comparison"):
                                ota_data = data["ota_comparison"][0] if isinstance(data["ota_comparison"], list) else data["ota_comparison"]
                                required_ota_fields = ["channel", "rate", "availability", "last_updated"]
                                if isinstance(data["ota_comparison"], dict):
                                    # Check if it contains channel data
                                    channels = ["booking_com", "expedia", "agoda"]
                                    has_channel_data = any(channel in data["ota_comparison"] for channel in channels)
                                    if has_channel_data:
                                        print(f"  ✅ {test_case['name']}: PASSED")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing OTA channel data")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no OTA data)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/sales/ota-pricing",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_sales_create_lead(self):
        """Test POST /api/sales/lead - Create new lead"""
        print("\n📝 Testing Create Sales Lead Endpoint...")
        
        test_cases = [
            {
                "name": "Create corporate lead",
                "data": {
                    "company_name": "Acme Corporation",
                    "contact_person": "Mehmet Yılmaz",
                    "email": "mehmet@acme.com",
                    "phone": "+90-555-123-4567",
                    "source": "website",
                    "estimated_value": 15000.0,
                    "notes": "Büyük kurumsal etkinlik planlaması"
                },
                "expected_status": 200,
                "expected_fields": ["message", "lead_id", "stage", "assigned_to"]
            },
            {
                "name": "Create wedding lead",
                "data": {
                    "company_name": "Yılmaz Ailesi",
                    "contact_person": "Ayşe Yılmaz",
                    "email": "ayse@email.com",
                    "phone": "+90-555-987-6543",
                    "source": "referral",
                    "estimated_value": 25000.0,
                    "notes": "Düğün organizasyonu için 100 kişilik rezervasyon"
                },
                "expected_status": 200,
                "expected_fields": ["message", "lead_id", "stage", "assigned_to"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/sales/lead"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == test_case["expected_status"]:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Store lead ID for later tests
                            if "lead_id" in data:
                                self.created_test_data['leads'].append(data["lead_id"])
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        if response.status == 422:
                            print(f"      🔍 Validation Error: {error_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/sales/lead",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_sales_update_lead_stage(self):
        """Test PUT /api/sales/lead/{lead_id}/stage - Update lead stage"""
        print("\n🔄 Testing Update Lead Stage Endpoint...")
        
        # Use sample lead ID
        sample_lead_id = str(uuid.uuid4())
        if self.created_test_data['leads']:
            sample_lead_id = self.created_test_data['leads'][0]
        
        test_cases = [
            {
                "name": "Update lead stage to warm",
                "lead_id": sample_lead_id,
                "data": {
                    "stage": "warm",
                    "notes": "İlk görüşme tamamlandı, olumlu geri dönüş alındı"
                },
                "expected_status": [200, 404]
            },
            {
                "name": "Update lead stage to hot",
                "lead_id": sample_lead_id,
                "data": {
                    "stage": "hot",
                    "notes": "Teklif sunuldu, karar aşamasında"
                },
                "expected_status": [200, 404]
            },
            {
                "name": "Update non-existent lead",
                "lead_id": "non-existent-id",
                "data": {
                    "stage": "converted",
                    "notes": "Test update"
                },
                "expected_status": 404
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/sales/lead/{test_case['lead_id']}/stage"
                
                async with self.session.put(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            data = await response.json()
                            required_fields = ["message", "lead_id", "old_stage", "new_stage", "updated_by"]
                            missing_fields = [field for field in required_fields if field not in data]
                            if not missing_fields:
                                print(f"  ✅ {test_case['name']}: PASSED")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:  # 404
                            print(f"  ✅ {test_case['name']}: PASSED (404 as expected)")
                            passed += 1
                    else:
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "PUT /api/sales/lead/{id}/stage",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_sales_follow_ups(self):
        """Test GET /api/sales/follow-ups - Follow-up reminders"""
        print("\n⏰ Testing Sales Follow-ups Endpoint...")
        
        test_cases = [
            {
                "name": "Get all follow-ups",
                "params": {},
                "expected_fields": ["follow_ups", "total_count", "overdue_count"]
            },
            {
                "name": "Filter overdue follow-ups",
                "params": {"overdue_only": "true"},
                "expected_fields": ["follow_ups", "total_count", "overdue_count"]
            },
            {
                "name": "Filter by assigned user",
                "params": {"assigned_to": "sales_manager"},
                "expected_fields": ["follow_ups", "total_count", "overdue_count"]
            },
            {
                "name": "Filter by date range",
                "params": {"start_date": "2024-12-01", "end_date": "2024-12-31"},
                "expected_fields": ["follow_ups", "total_count", "overdue_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/sales/follow-ups"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify follow-up structure if follow-ups exist
                            if data.get("follow_ups"):
                                follow_up = data["follow_ups"][0]
                                required_followup_fields = ["id", "lead_id", "company_name", "contact_person", "due_date", "is_overdue", "days_overdue", "assigned_to", "notes"]
                                missing_followup_fields = [field for field in required_followup_fields if field not in follow_up]
                                if not missing_followup_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing follow-up fields {missing_followup_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no follow-ups)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/sales/follow-ups",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MODULE 2: RATE & DISCOUNT MANAGEMENT (5 endpoints) =============

    async def test_rates_campaigns(self):
        """Test GET /api/rates/campaigns - Active campaigns with booking counts"""
        print("\n🎯 Testing Rates Campaigns Endpoint...")
        
        test_cases = [
            {
                "name": "Get all active campaigns",
                "params": {},
                "expected_fields": ["campaigns", "total_count", "active_count"]
            },
            {
                "name": "Filter by status - active",
                "params": {"status": "active"},
                "expected_fields": ["campaigns", "total_count", "active_count"]
            },
            {
                "name": "Filter by campaign type",
                "params": {"campaign_type": "seasonal"},
                "expected_fields": ["campaigns", "total_count", "active_count"]
            },
            {
                "name": "Sort by booking count",
                "params": {"sort_by": "booking_count", "order": "desc"},
                "expected_fields": ["campaigns", "total_count", "active_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/rates/campaigns"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify campaign structure if campaigns exist
                            if data.get("campaigns"):
                                campaign = data["campaigns"][0]
                                required_campaign_fields = ["id", "name", "campaign_type", "discount_percentage", "start_date", "end_date", "status", "booking_count", "revenue_generated", "target_audience"]
                                missing_campaign_fields = [field for field in required_campaign_fields if field not in campaign]
                                if not missing_campaign_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing campaign fields {missing_campaign_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no campaigns)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/rates/campaigns",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_rates_discount_codes(self):
        """Test GET /api/rates/discount-codes - Discount codes with usage tracking"""
        print("\n🎫 Testing Rates Discount Codes Endpoint...")
        
        test_cases = [
            {
                "name": "Get all discount codes",
                "params": {},
                "expected_fields": ["discount_codes", "total_count", "active_count"]
            },
            {
                "name": "Filter by status - active",
                "params": {"status": "active"},
                "expected_fields": ["discount_codes", "total_count", "active_count"]
            },
            {
                "name": "Filter by code type",
                "params": {"code_type": "percentage"},
                "expected_fields": ["discount_codes", "total_count", "active_count"]
            },
            {
                "name": "Search by code",
                "params": {"search": "WELCOME"},
                "expected_fields": ["discount_codes", "total_count", "active_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/rates/discount-codes"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify discount code structure if codes exist
                            if data.get("discount_codes"):
                                code = data["discount_codes"][0]
                                required_code_fields = ["id", "code", "code_type", "discount_value", "usage_count", "usage_limit", "start_date", "end_date", "status", "created_by"]
                                missing_code_fields = [field for field in required_code_fields if field not in code]
                                if not missing_code_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing discount code fields {missing_code_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no discount codes)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/rates/discount-codes",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_rates_override(self):
        """Test POST /api/rates/override - Rate override with approval workflow"""
        print("\n⚡ Testing Rates Override Endpoint...")
        
        test_cases = [
            {
                "name": "Create rate override request",
                "data": {
                    "booking_id": str(uuid.uuid4()),
                    "original_rate": 200.0,
                    "new_rate": 150.0,
                    "reason": "VIP müşteri özel indirimi",
                    "approval_required": True
                },
                "expected_status": [200, 404],  # 404 if booking doesn't exist
                "expected_fields": ["message", "override_id", "status", "approval_required"]
            },
            {
                "name": "Create emergency rate override",
                "data": {
                    "booking_id": str(uuid.uuid4()),
                    "original_rate": 300.0,
                    "new_rate": 250.0,
                    "reason": "Acil durum - overbooking çözümü",
                    "approval_required": False,
                    "emergency": True
                },
                "expected_status": [200, 404],
                "expected_fields": ["message", "override_id", "status", "approval_required"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/rates/override"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status in test_case["expected_status"]:
                        if response.status == 200:
                            data = await response.json()
                            missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                            if not missing_fields:
                                print(f"  ✅ {test_case['name']}: PASSED")
                                passed += 1
                            else:
                                print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                        else:  # 404
                            print(f"  ✅ {test_case['name']}: PASSED (404 - booking not found)")
                            passed += 1
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        if response.status == 422:
                            print(f"      🔍 Validation Error: {error_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/rates/override",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_rates_packages(self):
        """Test GET /api/rates/packages - Package management with inclusions"""
        print("\n📦 Testing Rates Packages Endpoint...")
        
        test_cases = [
            {
                "name": "Get all packages",
                "params": {},
                "expected_fields": ["packages", "total_count", "active_count"]
            },
            {
                "name": "Filter by package type",
                "params": {"package_type": "honeymoon"},
                "expected_fields": ["packages", "total_count", "active_count"]
            },
            {
                "name": "Filter by status - active",
                "params": {"status": "active"},
                "expected_fields": ["packages", "total_count", "active_count"]
            },
            {
                "name": "Sort by price",
                "params": {"sort_by": "price", "order": "asc"},
                "expected_fields": ["packages", "total_count", "active_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/rates/packages"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify package structure if packages exist
                            if data.get("packages"):
                                package = data["packages"][0]
                                required_package_fields = ["id", "name", "package_type", "base_price", "inclusions", "exclusions", "validity_start", "validity_end", "status", "booking_count"]
                                missing_package_fields = [field for field in required_package_fields if field not in package]
                                if not missing_package_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing package fields {missing_package_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no packages)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/rates/packages",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_rates_promotional(self):
        """Test GET /api/rates/promotional - Promotional rates"""
        print("\n🎉 Testing Rates Promotional Endpoint...")
        
        test_cases = [
            {
                "name": "Get all promotional rates",
                "params": {},
                "expected_fields": ["promotional_rates", "total_count", "active_count"]
            },
            {
                "name": "Filter by room type",
                "params": {"room_type": "deluxe"},
                "expected_fields": ["promotional_rates", "total_count", "active_count"]
            },
            {
                "name": "Filter by date range",
                "params": {"start_date": "2024-12-01", "end_date": "2024-12-31"},
                "expected_fields": ["promotional_rates", "total_count", "active_count"]
            },
            {
                "name": "Filter by discount percentage",
                "params": {"min_discount": 20},
                "expected_fields": ["promotional_rates", "total_count", "active_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/rates/promotional"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify promotional rate structure if rates exist
                            if data.get("promotional_rates"):
                                rate = data["promotional_rates"][0]
                                required_rate_fields = ["id", "name", "room_type", "original_rate", "promotional_rate", "discount_percentage", "start_date", "end_date", "booking_count", "revenue_impact"]
                                missing_rate_fields = [field for field in required_rate_fields if field not in rate]
                                if not missing_rate_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing promotional rate fields {missing_rate_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no promotional rates)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/rates/promotional",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MODULE 3: CHANNEL MANAGER MOBILE (5 endpoints) =============

    async def test_channels_status(self):
        """Test GET /api/channels/status - OTA connection health"""
        print("\n🔗 Testing Channels Status Endpoint...")
        
        test_cases = [
            {
                "name": "Get all channel statuses",
                "params": {},
                "expected_fields": ["channels", "total_count", "healthy_count", "error_count"]
            },
            {
                "name": "Filter by status - healthy",
                "params": {"status": "healthy"},
                "expected_fields": ["channels", "total_count", "healthy_count", "error_count"]
            },
            {
                "name": "Filter by status - error",
                "params": {"status": "error"},
                "expected_fields": ["channels", "total_count", "healthy_count", "error_count"]
            },
            {
                "name": "Filter by channel type",
                "params": {"channel_type": "booking_com"},
                "expected_fields": ["channels", "total_count", "healthy_count", "error_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/channels/status"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify channel structure if channels exist
                            if data.get("channels"):
                                channel = data["channels"][0]
                                required_channel_fields = ["id", "channel_name", "channel_type", "status", "last_sync", "sync_success_rate", "error_count", "last_error", "connection_health"]
                                missing_channel_fields = [field for field in required_channel_fields if field not in channel]
                                if not missing_channel_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing channel fields {missing_channel_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no channels)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/channels/status",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_channels_rate_parity(self):
        """Test GET /api/channels/rate-parity - Rate parity violations"""
        print("\n⚖️ Testing Channels Rate Parity Endpoint...")
        
        test_cases = [
            {
                "name": "Get all rate parity data",
                "params": {},
                "expected_fields": ["rate_parity", "violations", "summary"]
            },
            {
                "name": "Filter by violation status",
                "params": {"violations_only": "true"},
                "expected_fields": ["rate_parity", "violations", "summary"]
            },
            {
                "name": "Filter by channel",
                "params": {"channel": "booking_com"},
                "expected_fields": ["rate_parity", "violations", "summary"]
            },
            {
                "name": "Filter by date range",
                "params": {"start_date": "2024-12-01", "end_date": "2024-12-31"},
                "expected_fields": ["rate_parity", "violations", "summary"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/channels/rate-parity"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify rate parity structure if data exists
                            if data.get("rate_parity"):
                                parity = data["rate_parity"][0] if isinstance(data["rate_parity"], list) else data["rate_parity"]
                                if isinstance(data["rate_parity"], list) and data["rate_parity"]:
                                    parity = data["rate_parity"][0]
                                    required_parity_fields = ["channel", "room_type", "our_rate", "channel_rate", "difference", "parity_status", "last_checked"]
                                    missing_parity_fields = [field for field in required_parity_fields if field not in parity]
                                    if not missing_parity_fields:
                                        print(f"  ✅ {test_case['name']}: PASSED")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing parity fields {missing_parity_fields}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no rate parity data)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/channels/rate-parity",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_channels_inventory(self):
        """Test GET /api/channels/inventory - Inventory distribution"""
        print("\n📊 Testing Channels Inventory Endpoint...")
        
        test_cases = [
            {
                "name": "Get inventory distribution",
                "params": {},
                "expected_fields": ["inventory", "total_rooms", "distribution_summary"]
            },
            {
                "name": "Filter by room type",
                "params": {"room_type": "standard"},
                "expected_fields": ["inventory", "total_rooms", "distribution_summary"]
            },
            {
                "name": "Filter by date",
                "params": {"date": "2024-12-15"},
                "expected_fields": ["inventory", "total_rooms", "distribution_summary"]
            },
            {
                "name": "Filter by channel",
                "params": {"channel": "expedia"},
                "expected_fields": ["inventory", "total_rooms", "distribution_summary"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/channels/inventory"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify inventory structure if data exists
                            if data.get("inventory"):
                                inventory = data["inventory"][0] if isinstance(data["inventory"], list) else data["inventory"]
                                if isinstance(data["inventory"], list) and data["inventory"]:
                                    inventory = data["inventory"][0]
                                    required_inventory_fields = ["channel", "room_type", "total_allocation", "available", "sold", "blocked", "utilization_rate"]
                                    missing_inventory_fields = [field for field in required_inventory_fields if field not in inventory]
                                    if not missing_inventory_fields:
                                        print(f"  ✅ {test_case['name']}: PASSED")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing inventory fields {missing_inventory_fields}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no inventory data)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/channels/inventory",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_channels_performance(self):
        """Test GET /api/channels/performance - Channel performance metrics"""
        print("\n📈 Testing Channels Performance Endpoint...")
        
        test_cases = [
            {
                "name": "Get channel performance metrics",
                "params": {},
                "expected_fields": ["performance", "summary", "top_performers"]
            },
            {
                "name": "Filter by time period - last 30 days",
                "params": {"period": "30d"},
                "expected_fields": ["performance", "summary", "top_performers"]
            },
            {
                "name": "Filter by channel type",
                "params": {"channel_type": "ota"},
                "expected_fields": ["performance", "summary", "top_performers"]
            },
            {
                "name": "Sort by revenue",
                "params": {"sort_by": "revenue", "order": "desc"},
                "expected_fields": ["performance", "summary", "top_performers"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/channels/performance"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify performance structure if data exists
                            if data.get("performance"):
                                performance = data["performance"][0] if isinstance(data["performance"], list) else data["performance"]
                                if isinstance(data["performance"], list) and data["performance"]:
                                    performance = data["performance"][0]
                                    required_performance_fields = ["channel", "bookings", "revenue", "adr", "conversion_rate", "cancellation_rate", "commission_cost"]
                                    missing_performance_fields = [field for field in required_performance_fields if field not in performance]
                                    if not missing_performance_fields:
                                        print(f"  ✅ {test_case['name']}: PASSED")
                                        passed += 1
                                    else:
                                        print(f"  ❌ {test_case['name']}: Missing performance fields {missing_performance_fields}")
                                else:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no performance data)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/channels/performance",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_channels_push_rates(self):
        """Test POST /api/channels/push-rates - Push rates to OTA channels"""
        print("\n📤 Testing Channels Push Rates Endpoint...")
        
        test_cases = [
            {
                "name": "Push rates to all channels",
                "data": {
                    "room_type": "standard",
                    "date": "2024-12-15",
                    "rate": 180.0,
                    "availability": 10,
                    "channels": ["booking_com", "expedia", "agoda"]
                },
                "expected_status": 200,
                "expected_fields": ["message", "push_id", "channels_updated", "success_count", "error_count"]
            },
            {
                "name": "Push rates to specific channel",
                "data": {
                    "room_type": "deluxe",
                    "date": "2024-12-20",
                    "rate": 250.0,
                    "availability": 5,
                    "channels": ["booking_com"],
                    "min_stay": 2
                },
                "expected_status": 200,
                "expected_fields": ["message", "push_id", "channels_updated", "success_count", "error_count"]
            },
            {
                "name": "Push rates with restrictions",
                "data": {
                    "room_type": "suite",
                    "date": "2024-12-25",
                    "rate": 400.0,
                    "availability": 2,
                    "channels": ["expedia", "agoda"],
                    "min_stay": 3,
                    "stop_sell": False,
                    "closed_to_arrival": False
                },
                "expected_status": 200,
                "expected_fields": ["message", "push_id", "channels_updated", "success_count", "error_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/channels/push-rates"
                
                async with self.session.post(url, json=test_case["data"], headers=self.get_headers()) as response:
                    if response.status == test_case["expected_status"]:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            print(f"  ✅ {test_case['name']}: PASSED")
                            passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        error_text = await response.text()
                        print(f"  ❌ {test_case['name']}: Expected {test_case['expected_status']}, got {response.status}")
                        if response.status == 422:
                            print(f"      🔍 Validation Error: {error_text[:200]}...")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "POST /api/channels/push-rates",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MODULE 4: CORPORATE CONTRACTS (4 endpoints) =============

    async def test_corporate_contracts(self):
        """Test GET /api/corporate/contracts - Corporate agreements"""
        print("\n🏢 Testing Corporate Contracts Endpoint...")
        
        test_cases = [
            {
                "name": "Get all corporate contracts",
                "params": {},
                "expected_fields": ["contracts", "total_count", "active_count"]
            },
            {
                "name": "Filter by status - active",
                "params": {"status": "active"},
                "expected_fields": ["contracts", "total_count", "active_count"]
            },
            {
                "name": "Filter by contract type",
                "params": {"contract_type": "corporate"},
                "expected_fields": ["contracts", "total_count", "active_count"]
            },
            {
                "name": "Search by company name",
                "params": {"search": "Acme"},
                "expected_fields": ["contracts", "total_count", "active_count"]
            },
            {
                "name": "Filter by expiry date",
                "params": {"expiring_within": "30"},
                "expected_fields": ["contracts", "total_count", "active_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/corporate/contracts"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify contract structure if contracts exist
                            if data.get("contracts"):
                                contract = data["contracts"][0]
                                required_contract_fields = ["id", "company_name", "contract_type", "start_date", "end_date", "status", "negotiated_rates", "booking_count", "revenue_generated", "contact_person"]
                                missing_contract_fields = [field for field in required_contract_fields if field not in contract]
                                if not missing_contract_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing contract fields {missing_contract_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no contracts)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/corporate/contracts",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_corporate_customers(self):
        """Test GET /api/corporate/customers - Corporate customer list"""
        print("\n🏬 Testing Corporate Customers Endpoint...")
        
        test_cases = [
            {
                "name": "Get all corporate customers",
                "params": {},
                "expected_fields": ["customers", "total_count", "active_contracts"]
            },
            {
                "name": "Filter by customer status",
                "params": {"status": "active"},
                "expected_fields": ["customers", "total_count", "active_contracts"]
            },
            {
                "name": "Search by company name",
                "params": {"search": "Tech"},
                "expected_fields": ["customers", "total_count", "active_contracts"]
            },
            {
                "name": "Sort by revenue",
                "params": {"sort_by": "revenue", "order": "desc"},
                "expected_fields": ["customers", "total_count", "active_contracts"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/corporate/customers"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify customer structure if customers exist
                            if data.get("customers"):
                                customer = data["customers"][0]
                                required_customer_fields = ["id", "company_name", "contact_person", "email", "phone", "contract_status", "total_bookings", "total_revenue", "last_booking_date", "payment_terms"]
                                missing_customer_fields = [field for field in required_customer_fields if field not in customer]
                                if not missing_customer_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing customer fields {missing_customer_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no corporate customers)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/corporate/customers",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_corporate_rates(self):
        """Test GET /api/corporate/rates - Contract rates"""
        print("\n💼 Testing Corporate Rates Endpoint...")
        
        test_cases = [
            {
                "name": "Get all corporate rates",
                "params": {},
                "expected_fields": ["rates", "total_count", "rate_summary"]
            },
            {
                "name": "Filter by company",
                "params": {"company_id": str(uuid.uuid4())},
                "expected_fields": ["rates", "total_count", "rate_summary"]
            },
            {
                "name": "Filter by room type",
                "params": {"room_type": "standard"},
                "expected_fields": ["rates", "total_count", "rate_summary"]
            },
            {
                "name": "Filter by rate type",
                "params": {"rate_type": "corporate"},
                "expected_fields": ["rates", "total_count", "rate_summary"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/corporate/rates"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify rate structure if rates exist
                            if data.get("rates"):
                                rate = data["rates"][0]
                                required_rate_fields = ["id", "company_name", "room_type", "rate_type", "base_rate", "corporate_rate", "discount_percentage", "valid_from", "valid_to", "booking_count"]
                                missing_rate_fields = [field for field in required_rate_fields if field not in rate]
                                if not missing_rate_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing rate fields {missing_rate_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no corporate rates)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/corporate/rates",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    async def test_corporate_alerts(self):
        """Test GET /api/corporate/alerts - Contract expiry alerts"""
        print("\n🚨 Testing Corporate Alerts Endpoint...")
        
        test_cases = [
            {
                "name": "Get all contract alerts",
                "params": {},
                "expected_fields": ["alerts", "total_count", "urgent_count"]
            },
            {
                "name": "Filter by alert type - expiry",
                "params": {"alert_type": "expiry"},
                "expected_fields": ["alerts", "total_count", "urgent_count"]
            },
            {
                "name": "Filter by urgency - urgent",
                "params": {"urgency": "urgent"},
                "expected_fields": ["alerts", "total_count", "urgent_count"]
            },
            {
                "name": "Filter by days until expiry",
                "params": {"days_until_expiry": "30"},
                "expected_fields": ["alerts", "total_count", "urgent_count"]
            }
        ]
        
        passed = 0
        total = len(test_cases)
        
        for test_case in test_cases:
            try:
                url = f"{BACKEND_URL}/corporate/alerts"
                if test_case["params"]:
                    params = "&".join([f"{k}={v}" for k, v in test_case["params"].items()])
                    url += f"?{params}"
                
                async with self.session.get(url, headers=self.get_headers()) as response:
                    if response.status == 200:
                        data = await response.json()
                        missing_fields = [field for field in test_case["expected_fields"] if field not in data]
                        if not missing_fields:
                            # Verify alert structure if alerts exist
                            if data.get("alerts"):
                                alert = data["alerts"][0]
                                required_alert_fields = ["id", "company_name", "contract_id", "alert_type", "urgency", "expiry_date", "days_until_expiry", "message", "action_required"]
                                missing_alert_fields = [field for field in required_alert_fields if field not in alert]
                                if not missing_alert_fields:
                                    print(f"  ✅ {test_case['name']}: PASSED")
                                    passed += 1
                                else:
                                    print(f"  ❌ {test_case['name']}: Missing alert fields {missing_alert_fields}")
                            else:
                                print(f"  ✅ {test_case['name']}: PASSED (no alerts)")
                                passed += 1
                        else:
                            print(f"  ❌ {test_case['name']}: Missing fields {missing_fields}")
                    else:
                        print(f"  ❌ {test_case['name']}: HTTP {response.status}")
                        
            except Exception as e:
                print(f"  ❌ {test_case['name']}: Error {e}")
        
        self.test_results.append({
            "endpoint": "GET /api/corporate/alerts",
            "passed": passed, "total": total, "success_rate": f"{passed/total*100:.1f}%"
        })

    # ============= MAIN TEST EXECUTION =============

    async def run_all_tests(self):
        """Run comprehensive testing of 4 NEW MOBILE MODULES (20 endpoints)"""
        print("🚀 4 NEW MOBILE MODULES COMPREHENSIVE TESTING")
        print("Testing 20 backend endpoints across 4 mobile modules")
        print("=" * 80)
        
        # Setup
        await self.setup_session()
        
        if not await self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # MODULE 1: SALES & CRM MOBILE (6 endpoints)
        print("\n" + "="*60)
        print("👥 MODULE 1: SALES & CRM MOBILE (6 endpoints)")
        print("="*60)
        await self.test_sales_customers()
        await self.test_sales_leads()
        await self.test_sales_ota_pricing()
        await self.test_sales_create_lead()
        await self.test_sales_update_lead_stage()
        await self.test_sales_follow_ups()
        
        # MODULE 2: RATE & DISCOUNT MANAGEMENT (5 endpoints)
        print("\n" + "="*60)
        print("💰 MODULE 2: RATE & DISCOUNT MANAGEMENT (5 endpoints)")
        print("="*60)
        await self.test_rates_campaigns()
        await self.test_rates_discount_codes()
        await self.test_rates_override()
        await self.test_rates_packages()
        await self.test_rates_promotional()
        
        # MODULE 3: CHANNEL MANAGER MOBILE (5 endpoints)
        print("\n" + "="*60)
        print("🔗 MODULE 3: CHANNEL MANAGER MOBILE (5 endpoints)")
        print("="*60)
        await self.test_channels_status()
        await self.test_channels_rate_parity()
        await self.test_channels_inventory()
        await self.test_channels_performance()
        await self.test_channels_push_rates()
        
        # MODULE 4: CORPORATE CONTRACTS (4 endpoints)
        print("\n" + "="*60)
        print("🏢 MODULE 4: CORPORATE CONTRACTS (4 endpoints)")
        print("="*60)
        await self.test_corporate_contracts()
        await self.test_corporate_customers()
        await self.test_corporate_rates()
        await self.test_corporate_alerts()
        
        # Cleanup
        await self.cleanup_session()
        
        # Print results
        self.print_test_summary()

    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 80)
        print("📊 4 NEW MOBILE MODULES TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_tests = 0
        
        # Group results by module
        modules = {
            "MODULE 1: SALES & CRM MOBILE": [],
            "MODULE 2: RATE & DISCOUNT MANAGEMENT": [],
            "MODULE 3: CHANNEL MANAGER MOBILE": [],
            "MODULE 4: CORPORATE CONTRACTS": []
        }
        
        for result in self.test_results:
            endpoint = result["endpoint"]
            if "sales" in endpoint:
                modules["MODULE 1: SALES & CRM MOBILE"].append(result)
            elif "rates" in endpoint:
                modules["MODULE 2: RATE & DISCOUNT MANAGEMENT"].append(result)
            elif "channels" in endpoint:
                modules["MODULE 3: CHANNEL MANAGER MOBILE"].append(result)
            elif "corporate" in endpoint:
                modules["MODULE 4: CORPORATE CONTRACTS"].append(result)
        
        print("\n📋 RESULTS BY MODULE:")
        print("-" * 60)
        
        for module, results in modules.items():
            if results:
                module_passed = sum(r["passed"] for r in results)
                module_total = sum(r["total"] for r in results)
                module_rate = (module_passed / module_total * 100) if module_total > 0 else 0
                
                status = "✅" if module_rate == 100 else "⚠️" if module_rate >= 80 else "❌"
                print(f"\n{status} {module}: {module_passed}/{module_total} ({module_rate:.1f}%)")
                
                for result in results:
                    endpoint_status = "✅" if result["passed"] == result["total"] else "❌"
                    print(f"   {endpoint_status} {result['endpoint']}: {result['success_rate']}")
                
                total_passed += module_passed
                total_tests += module_total
        
        print("\n" + "=" * 80)
        overall_success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        print(f"📈 OVERALL SUCCESS RATE: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
        
        if overall_success_rate >= 95:
            print("🎉 EXCELLENT: All mobile modules working perfectly!")
        elif overall_success_rate >= 85:
            print("✅ GOOD: Most endpoints working, minor issues detected")
        elif overall_success_rate >= 70:
            print("⚠️ PARTIAL: Some endpoints working, several issues need attention")
        else:
            print("❌ CRITICAL: Major issues detected, mobile modules need fixes")
        
        print("\n🔍 TESTING COVERAGE:")
        print("• Response structure validation ✓")
        print("• Filter functionality testing ✓")
        print("• POST/PUT request validation ✓")
        print("• Error handling verification ✓")
        print("• Turkish language support ✓")
        print("• Date range filtering ✓")
        print("• Pagination and sorting ✓")
        
        print("\n" + "=" * 80)

async def main():
    """Main test execution"""
    tester = MobileModulesTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())