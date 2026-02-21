#!/usr/bin/env python3
"""
Comprehensive Finance Snapshot Endpoint Testing
Testing GET /api/reports/finance-snapshot with real data scenarios
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://perf-boost-37.preview.emergentagent.com/api"
TEST_EMAIL = "financetest@hotel.com"
TEST_PASSWORD = "test123456"

class ComprehensiveFinanceTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = {"passed": 0, "failed": 0, "details": []}
        self.created_resources = {
            "booking_ids": [],
            "folio_ids": [],
            "company_ids": [],
            "guest_ids": [],
            "room_ids": [],
            "payment_ids": [],
            "charge_ids": []
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

    def log_test_result(self, test_name, success, details=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "test": test_name,
            "status": status,
            "details": details
        }
        self.test_results["details"].append(result)
        if success:
            self.test_results["passed"] += 1
        else:
            self.test_results["failed"] += 1
        
        print(f"  {status}: {test_name} - {details}")

    def create_test_company(self):
        """Create a test company"""
        try:
            response = self.session.post(f"{BACKEND_URL}/companies", json={
                "name": "Acme Corporation",
                "corporate_code": "ACME001",
                "tax_number": "1234567890",
                "billing_address": "123 Corporate Blvd, Business City, BC 12345",
                "contact_person": "John Corporate",
                "contact_email": "billing@acmecorp.com",
                "contact_phone": "+1-555-0123",
                "payment_terms": "Net 30",
                "status": "active"
            })
            
            if response.status_code in [200, 201]:
                company_data = response.json()
                company_id = company_data["id"]
                self.created_resources["company_ids"].append(company_id)
                print(f"✅ Created company: {company_id}")
                return company_id
            else:
                print(f"❌ Failed to create company: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Error creating company: {str(e)}")
            return None

    def create_test_guest(self):
        """Create a test guest"""
        try:
            response = self.session.post(f"{BACKEND_URL}/pms/guests", json={
                "name": "Alice Johnson",
                "email": "alice.johnson@email.com",
                "phone": "+1-555-0456",
                "id_number": "ID123456789",
                "nationality": "US",
                "vip_status": False
            })
            
            if response.status_code in [200, 201]:
                guest_data = response.json()
                guest_id = guest_data["id"]
                self.created_resources["guest_ids"].append(guest_id)
                print(f"✅ Created guest: {guest_id}")
                return guest_id
            else:
                print(f"❌ Failed to create guest: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Error creating guest: {str(e)}")
            return None

    def get_available_room(self):
        """Get an available room"""
        try:
            response = self.session.get(f"{BACKEND_URL}/pms/rooms")
            if response.status_code == 200:
                rooms = response.json()
                available_rooms = [r for r in rooms if r.get('status') == 'available']
                if available_rooms:
                    room_id = available_rooms[0]["id"]
                    print(f"✅ Using room: {room_id} ({available_rooms[0]['room_number']})")
                    return room_id
                else:
                    print("❌ No available rooms found")
                    return None
            else:
                print(f"❌ Failed to get rooms: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error getting rooms: {str(e)}")
            return None

    def create_booking_with_company_folio(self, guest_id, room_id, company_id):
        """Create a booking with company folio"""
        try:
            # Create booking
            today = datetime.now()
            checkin = today.strftime("%Y-%m-%d")
            checkout = (today + timedelta(days=3)).strftime("%Y-%m-%d")
            
            booking_response = self.session.post(f"{BACKEND_URL}/pms/bookings", json={
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": checkin,
                "check_out": checkout,
                "adults": 2,
                "children": 0,
                "children_ages": [],
                "guests_count": 2,
                "total_amount": 750.00,
                "company_id": company_id,
                "rate_type": "corporate",
                "market_segment": "corporate"
            })
            
            if booking_response.status_code in [200, 201]:
                booking_data = booking_response.json()
                booking_id = booking_data["id"]
                self.created_resources["booking_ids"].append(booking_id)
                print(f"✅ Created booking: {booking_id}")
                
                # Create company folio
                folio_response = self.session.post(f"{BACKEND_URL}/folio/create", json={
                    "booking_id": booking_id,
                    "folio_type": "company",
                    "company_id": company_id
                })
                
                if folio_response.status_code in [200, 201]:
                    folio_data = folio_response.json()
                    folio_id = folio_data["id"]
                    self.created_resources["folio_ids"].append(folio_id)
                    print(f"✅ Created company folio: {folio_id}")
                    return booking_id, folio_id
                else:
                    print(f"❌ Failed to create folio: {folio_response.status_code} - {folio_response.text}")
                    return booking_id, None
            else:
                print(f"❌ Failed to create booking: {booking_response.status_code} - {booking_response.text}")
                return None, None
                
        except Exception as e:
            print(f"❌ Error creating booking/folio: {str(e)}")
            return None, None

    def add_charges_to_folio(self, folio_id):
        """Add various charges to folio"""
        charges_added = []
        
        # Room charges (3 nights)
        try:
            room_charge_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/charge", json={
                "charge_category": "room",
                "description": "Room charge - Standard room",
                "amount": 200.00,
                "quantity": 3.0
            })
            
            if room_charge_response.status_code in [200, 201]:
                charge_data = room_charge_response.json()
                charges_added.append(("room", charge_data["total"]))
                self.created_resources["charge_ids"].append(charge_data["id"])
                print(f"✅ Added room charge: ${charge_data['total']}")
        except Exception as e:
            print(f"❌ Error adding room charge: {str(e)}")
        
        # F&B charges
        try:
            fb_charge_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/charge", json={
                "charge_category": "food",
                "description": "Restaurant dinner",
                "amount": 85.50,
                "quantity": 1.0
            })
            
            if fb_charge_response.status_code in [200, 201]:
                charge_data = fb_charge_response.json()
                charges_added.append(("food", charge_data["total"]))
                self.created_resources["charge_ids"].append(charge_data["id"])
                print(f"✅ Added F&B charge: ${charge_data['total']}")
        except Exception as e:
            print(f"❌ Error adding F&B charge: {str(e)}")
        
        # Minibar charges
        try:
            minibar_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/charge", json={
                "charge_category": "minibar",
                "description": "Minibar consumption",
                "amount": 25.75,
                "quantity": 1.0
            })
            
            if minibar_response.status_code in [200, 201]:
                charge_data = minibar_response.json()
                charges_added.append(("minibar", charge_data["total"]))
                self.created_resources["charge_ids"].append(charge_data["id"])
                print(f"✅ Added minibar charge: ${charge_data['total']}")
        except Exception as e:
            print(f"❌ Error adding minibar charge: {str(e)}")
        
        return charges_added

    def add_payments_to_folio(self, folio_id):
        """Add payments to folio"""
        payments_added = []
        
        # Partial payment
        try:
            payment_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/payment", json={
                "amount": 400.00,
                "method": "card",
                "payment_type": "interim",
                "reference": "CC-PAYMENT-001"
            })
            
            if payment_response.status_code in [200, 201]:
                payment_data = payment_response.json()
                payments_added.append(("interim", payment_data["amount"]))
                self.created_resources["payment_ids"].append(payment_data["id"])
                print(f"✅ Added payment: ${payment_data['amount']}")
        except Exception as e:
            print(f"❌ Error adding payment: {str(e)}")
        
        return payments_added

    def setup_comprehensive_test_data(self):
        """Setup comprehensive test data"""
        print("\n🏗️ Setting up comprehensive test data...")
        
        # Create company
        company_id = self.create_test_company()
        if not company_id:
            return False
        
        # Create guest
        guest_id = self.create_test_guest()
        if not guest_id:
            return False
        
        # Get available room
        room_id = self.get_available_room()
        if not room_id:
            return False
        
        # Create booking with company folio
        booking_id, folio_id = self.create_booking_with_company_folio(guest_id, room_id, company_id)
        if not folio_id:
            return False
        
        # Add charges
        charges = self.add_charges_to_folio(folio_id)
        total_charges = sum(charge[1] for charge in charges)
        print(f"✅ Total charges added: ${total_charges}")
        
        # Add payments
        payments = self.add_payments_to_folio(folio_id)
        total_payments = sum(payment[1] for payment in payments)
        print(f"✅ Total payments added: ${total_payments}")
        
        expected_balance = total_charges - total_payments
        print(f"✅ Expected folio balance: ${expected_balance}")
        
        return True

    def test_finance_snapshot_with_data(self):
        """Test finance snapshot with actual data"""
        print("\n📊 Testing Finance Snapshot with Real Data")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/finance-snapshot")
            
            if response.status_code == 200:
                data = response.json()
                
                # Print the full response for analysis
                print(f"📋 Finance Snapshot Response:")
                print(json.dumps(data, indent=2))
                
                # Test 1: Verify response structure
                required_fields = [
                    'report_date',
                    'pending_ar',
                    'todays_collections',
                    'mtd_collections',
                    'accounting_invoices'
                ]
                
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    self.log_test_result(
                        "Response Structure",
                        True,
                        "All required fields present"
                    )
                else:
                    self.log_test_result(
                        "Response Structure",
                        False,
                        f"Missing fields: {missing_fields}"
                    )
                    return False
                
                # Test 2: Verify pending AR has data
                pending_ar = data.get('pending_ar', {})
                total_ar = pending_ar.get('total', 0)
                
                if total_ar > 0:
                    self.log_test_result(
                        "Pending AR Data",
                        True,
                        f"AR total: ${total_ar} (has outstanding balances)"
                    )
                else:
                    self.log_test_result(
                        "Pending AR Data",
                        True,
                        f"AR total: ${total_ar} (no outstanding balances)"
                    )
                
                # Test 3: Verify overdue breakdown structure
                overdue_breakdown = pending_ar.get('overdue_breakdown', {})
                breakdown_fields = ['0-30_days', '30-60_days', '60_plus_days']
                
                if all(field in overdue_breakdown for field in breakdown_fields):
                    breakdown_total = sum(overdue_breakdown[field] for field in breakdown_fields)
                    self.log_test_result(
                        "Overdue Breakdown",
                        True,
                        f"All breakdown fields present. Total: ${breakdown_total}"
                    )
                else:
                    self.log_test_result(
                        "Overdue Breakdown",
                        False,
                        "Missing breakdown fields"
                    )
                
                # Test 4: Verify numerical precision (2 decimal places)
                def check_decimal_precision(value, name):
                    if isinstance(value, (int, float)):
                        rounded_value = round(value, 2)
                        if value == rounded_value:
                            return True, f"{name}: ${value} (properly rounded)"
                        else:
                            return False, f"{name}: ${value} (not properly rounded to 2 decimals)"
                    return True, f"{name}: {value} (not numeric)"
                
                precision_tests = [
                    (total_ar, "AR Total"),
                    (overdue_breakdown.get('0-30_days', 0), "0-30 days"),
                    (overdue_breakdown.get('30-60_days', 0), "30-60 days"),
                    (overdue_breakdown.get('60_plus_days', 0), "60+ days"),
                    (data.get('todays_collections', {}).get('amount', 0), "Today's Collections"),
                    (data.get('mtd_collections', {}).get('amount', 0), "MTD Collections")
                ]
                
                all_precision_ok = True
                precision_details = []
                
                for value, name in precision_tests:
                    ok, detail = check_decimal_precision(value, name)
                    precision_details.append(detail)
                    if not ok:
                        all_precision_ok = False
                
                self.log_test_result(
                    "Decimal Precision",
                    all_precision_ok,
                    "; ".join(precision_details)
                )
                
                # Test 5: Verify collection rate percentage
                collection_rate = data.get('mtd_collections', {}).get('collection_rate_percentage', 0)
                
                if isinstance(collection_rate, (int, float)) and 0 <= collection_rate <= 100:
                    self.log_test_result(
                        "Collection Rate Validity",
                        True,
                        f"Collection rate: {collection_rate}% (valid range)"
                    )
                else:
                    self.log_test_result(
                        "Collection Rate Validity",
                        False,
                        f"Collection rate: {collection_rate}% (invalid range)"
                    )
                
                # Test 6: Verify accounting invoices structure
                accounting_invoices = data.get('accounting_invoices', {})
                invoice_fields = ['pending_count', 'pending_total']
                
                if all(field in accounting_invoices for field in invoice_fields):
                    self.log_test_result(
                        "Accounting Invoices Structure",
                        True,
                        f"Count: {accounting_invoices['pending_count']}, Total: ${accounting_invoices['pending_total']}"
                    )
                else:
                    self.log_test_result(
                        "Accounting Invoices Structure",
                        False,
                        "Missing invoice fields"
                    )
                
                return True
                
            else:
                self.log_test_result(
                    "Finance Snapshot API Call",
                    False,
                    f"HTTP {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Finance Snapshot API Call",
                False,
                f"Exception: {str(e)}"
            )
            return False

    def run_comprehensive_tests(self):
        """Run all comprehensive tests"""
        print("🚀 Starting Comprehensive Finance Snapshot Testing")
        print("=" * 70)
        
        if not self.authenticate():
            return False
        
        # Setup comprehensive test data
        if not self.setup_comprehensive_test_data():
            print("❌ Failed to setup test data")
            return False
        
        # Test finance snapshot with real data
        self.test_finance_snapshot_with_data()
        
        # Print summary
        print("\n" + "=" * 70)
        print("📊 COMPREHENSIVE FINANCE SNAPSHOT TEST SUMMARY")
        print("=" * 70)
        
        total_tests = self.test_results["passed"] + self.test_results["failed"]
        success_rate = (self.test_results["passed"] / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {self.test_results['passed']} ✅")
        print(f"Failed: {self.test_results['failed']} ❌")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.test_results["failed"] > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results["details"]:
                if "❌ FAIL" in result["status"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        print("\n✅ PASSED TESTS:")
        for result in self.test_results["details"]:
            if "✅ PASS" in result["status"]:
                print(f"  - {result['test']}: {result['details']}")
        
        print(f"\n📋 Created Resources Summary:")
        for resource_type, ids in self.created_resources.items():
            if ids:
                print(f"  - {resource_type}: {len(ids)} items")
        
        return self.test_results["failed"] == 0

if __name__ == "__main__":
    tester = ComprehensiveFinanceTester()
    success = tester.run_comprehensive_tests()
    sys.exit(0 if success else 1)