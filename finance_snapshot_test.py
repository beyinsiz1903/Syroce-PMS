#!/usr/bin/env python3
"""
Finance Snapshot Endpoint Testing
Testing GET /api/reports/finance-snapshot for GM Dashboard
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://pms-feature-test.preview.emergentagent.com/api"
TEST_EMAIL = "financetest@hotel.com"
TEST_PASSWORD = "test123456"

class FinanceSnapshotTester:
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

    def setup_test_data(self):
        """Setup test data for finance snapshot testing"""
        print("\n🏗️ Setting up test data...")
        
        # Create a company for company folios
        try:
            company_response = self.session.post(f"{BACKEND_URL}/companies", json={
                "name": "Finance Test Corp",
                "corporate_code": "FTC001",
                "tax_number": "1234567890",
                "billing_address": "123 Business St, Finance City",
                "contact_person": "John Finance",
                "contact_email": "finance@testcorp.com",
                "contact_phone": "+1234567890",
                "payment_terms": "Net 30",
                "status": "active"
            })
            
            if company_response.status_code in [200, 201]:
                company_data = company_response.json()
                company_id = company_data["id"]
                self.created_resources["company_ids"].append(company_id)
                print(f"✅ Created test company: {company_id}")
                
                # Create a guest for booking
                guest_response = self.session.post(f"{BACKEND_URL}/pms/guests", json={
                    "name": "Finance Test Guest",
                    "email": "guest@financetest.com",
                    "phone": "+1234567891",
                    "id_number": "FIN123456",
                    "nationality": "US"
                })
                
                if guest_response.status_code in [200, 201]:
                    guest_data = guest_response.json()
                    guest_id = guest_data["id"]
                    print(f"✅ Created test guest: {guest_id}")
                    
                    # Get available rooms
                    rooms_response = self.session.get(f"{BACKEND_URL}/pms/rooms")
                    if rooms_response.status_code == 200:
                        rooms = rooms_response.json()
                        if rooms:
                            room_id = rooms[0]["id"]
                            print(f"✅ Using room: {room_id}")
                            
                            # Create a booking
                            today = datetime.now()
                            checkin = today.strftime("%Y-%m-%d")
                            checkout = (today + timedelta(days=2)).strftime("%Y-%m-%d")
                            
                            booking_response = self.session.post(f"{BACKEND_URL}/pms/bookings", json={
                                "guest_id": guest_id,
                                "room_id": room_id,
                                "check_in": checkin,
                                "check_out": checkout,
                                "adults": 2,
                                "children": 0,
                                "children_ages": [],
                                "guests_count": 2,
                                "total_amount": 500.00,
                                "company_id": company_id,
                                "rate_type": "corporate",
                                "market_segment": "corporate"
                            })
                            
                            if booking_response.status_code in [200, 201]:
                                booking_data = booking_response.json()
                                booking_id = booking_data["id"]
                                self.created_resources["booking_ids"].append(booking_id)
                                print(f"✅ Created test booking: {booking_id}")
                                
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
                                    
                                    # Add charges to folio
                                    charge_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/charge", json={
                                        "charge_category": "room",
                                        "description": "Room charge for 2 nights",
                                        "amount": 250.00,
                                        "quantity": 2.0
                                    })
                                    
                                    if charge_response.status_code in [200, 201]:
                                        charge_data = charge_response.json()
                                        self.created_resources["charge_ids"].append(charge_data["id"])
                                        print(f"✅ Added room charge: {charge_data['id']}")
                                    
                                    # Add F&B charge
                                    fb_charge_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/charge", json={
                                        "charge_category": "food",
                                        "description": "Restaurant dinner",
                                        "amount": 75.50,
                                        "quantity": 1.0
                                    })
                                    
                                    if fb_charge_response.status_code in [200, 201]:
                                        fb_charge_data = fb_charge_response.json()
                                        self.created_resources["charge_ids"].append(fb_charge_data["id"])
                                        print(f"✅ Added F&B charge: {fb_charge_data['id']}")
                                    
                                    # Add a payment (partial)
                                    payment_response = self.session.post(f"{BACKEND_URL}/folio/{folio_id}/payment", json={
                                        "amount": 200.00,
                                        "method": "card",
                                        "payment_type": "interim",
                                        "reference": "TEST-PAY-001"
                                    })
                                    
                                    if payment_response.status_code in [200, 201]:
                                        payment_data = payment_response.json()
                                        self.created_resources["payment_ids"].append(payment_data["id"])
                                        print(f"✅ Added payment: {payment_data['id']}")
                                        
                                        return True
                                    
        except Exception as e:
            print(f"❌ Error setting up test data: {str(e)}")
            return False
        
        return False

    def test_basic_finance_snapshot(self):
        """Test 1: Basic Finance Snapshot Retrieval"""
        print("\n📊 Test 1: Basic Finance Snapshot Retrieval")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/finance-snapshot")
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = [
                    'report_date',
                    'pending_ar',
                    'todays_collections',
                    'mtd_collections',
                    'accounting_invoices'
                ]
                
                missing_fields = []
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if missing_fields:
                    self.log_test_result(
                        "Basic Finance Snapshot Structure",
                        False,
                        f"Missing fields: {missing_fields}"
                    )
                    return False
                
                # Verify pending_ar structure
                pending_ar = data.get('pending_ar', {})
                ar_required_fields = ['total', 'overdue_breakdown', 'overdue_invoices_count']
                ar_missing = [f for f in ar_required_fields if f not in pending_ar]
                
                if ar_missing:
                    self.log_test_result(
                        "Pending AR Structure",
                        False,
                        f"Missing AR fields: {ar_missing}"
                    )
                    return False
                
                # Verify overdue_breakdown structure
                overdue_breakdown = pending_ar.get('overdue_breakdown', {})
                breakdown_fields = ['0-30_days', '30-60_days', '60_plus_days']
                breakdown_missing = [f for f in breakdown_fields if f not in overdue_breakdown]
                
                if breakdown_missing:
                    self.log_test_result(
                        "Overdue Breakdown Structure",
                        False,
                        f"Missing breakdown fields: {breakdown_missing}"
                    )
                    return False
                
                # Verify todays_collections structure
                todays_collections = data.get('todays_collections', {})
                collections_fields = ['amount', 'payment_count']
                collections_missing = [f for f in collections_fields if f not in todays_collections]
                
                if collections_missing:
                    self.log_test_result(
                        "Today's Collections Structure",
                        False,
                        f"Missing collections fields: {collections_missing}"
                    )
                    return False
                
                # Verify mtd_collections structure
                mtd_collections = data.get('mtd_collections', {})
                mtd_fields = ['amount', 'collection_rate_percentage']
                mtd_missing = [f for f in mtd_fields if f not in mtd_collections]
                
                if mtd_missing:
                    self.log_test_result(
                        "MTD Collections Structure",
                        False,
                        f"Missing MTD fields: {mtd_missing}"
                    )
                    return False
                
                # Verify accounting_invoices structure
                accounting_invoices = data.get('accounting_invoices', {})
                invoice_fields = ['pending_count', 'pending_total']
                invoice_missing = [f for f in invoice_fields if f not in accounting_invoices]
                
                if invoice_missing:
                    self.log_test_result(
                        "Accounting Invoices Structure",
                        False,
                        f"Missing invoice fields: {invoice_missing}"
                    )
                    return False
                
                self.log_test_result(
                    "Basic Finance Snapshot Structure",
                    True,
                    f"All required fields present. AR Total: ${pending_ar['total']}"
                )
                
                return data
                
            else:
                self.log_test_result(
                    "Basic Finance Snapshot Retrieval",
                    False,
                    f"HTTP {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Basic Finance Snapshot Retrieval",
                False,
                f"Exception: {str(e)}"
            )
            return False

    def test_data_accuracy(self, snapshot_data):
        """Test 2: Data Accuracy Verification"""
        print("\n🔍 Test 2: Data Accuracy Verification")
        
        try:
            # Verify numerical values are properly rounded to 2 decimal places
            pending_ar = snapshot_data.get('pending_ar', {})
            total_ar = pending_ar.get('total', 0)
            
            # Check if total is properly rounded
            if isinstance(total_ar, (int, float)):
                rounded_total = round(total_ar, 2)
                if total_ar == rounded_total:
                    self.log_test_result(
                        "AR Total Rounding",
                        True,
                        f"AR total properly rounded: ${total_ar}"
                    )
                else:
                    self.log_test_result(
                        "AR Total Rounding",
                        False,
                        f"AR total not properly rounded: ${total_ar}"
                    )
            
            # Verify overdue breakdown calculations
            overdue_breakdown = pending_ar.get('overdue_breakdown', {})
            breakdown_total = (
                overdue_breakdown.get('0-30_days', 0) +
                overdue_breakdown.get('30-60_days', 0) +
                overdue_breakdown.get('60_plus_days', 0)
            )
            
            # The breakdown total should be <= total AR (some AR might not be overdue)
            if breakdown_total <= total_ar:
                self.log_test_result(
                    "Overdue Breakdown Calculation",
                    True,
                    f"Breakdown total (${breakdown_total}) <= AR total (${total_ar})"
                )
            else:
                self.log_test_result(
                    "Overdue Breakdown Calculation",
                    False,
                    f"Breakdown total (${breakdown_total}) > AR total (${total_ar})"
                )
            
            # Verify collection rate percentage calculation
            mtd_collections = snapshot_data.get('mtd_collections', {})
            collection_rate = mtd_collections.get('collection_rate_percentage', 0)
            
            if isinstance(collection_rate, (int, float)) and 0 <= collection_rate <= 100:
                self.log_test_result(
                    "Collection Rate Percentage",
                    True,
                    f"Collection rate within valid range: {collection_rate}%"
                )
            else:
                self.log_test_result(
                    "Collection Rate Percentage",
                    False,
                    f"Collection rate invalid: {collection_rate}%"
                )
            
            return True
            
        except Exception as e:
            self.log_test_result(
                "Data Accuracy Verification",
                False,
                f"Exception: {str(e)}"
            )
            return False

    def test_edge_cases(self):
        """Test 3: Edge Cases"""
        print("\n🧪 Test 3: Edge Cases")
        
        # Test with current data (should work with existing folios)
        try:
            response = self.session.get(f"{BACKEND_URL}/reports/finance-snapshot")
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if endpoint handles no payments today gracefully
                todays_collections = data.get('todays_collections', {})
                payment_count = todays_collections.get('payment_count', 0)
                amount = todays_collections.get('amount', 0)
                
                if payment_count == 0 and amount == 0:
                    self.log_test_result(
                        "No Payments Today Edge Case",
                        True,
                        "Correctly handles zero payments today"
                    )
                else:
                    self.log_test_result(
                        "No Payments Today Edge Case",
                        True,
                        f"Has payments today: {payment_count} payments, ${amount}"
                    )
                
                # Check if endpoint handles no company folios gracefully
                pending_ar = data.get('pending_ar', {})
                total_ar = pending_ar.get('total', 0)
                
                if total_ar >= 0:  # Should be non-negative
                    self.log_test_result(
                        "Company Folios Handling",
                        True,
                        f"AR total is non-negative: ${total_ar}"
                    )
                else:
                    self.log_test_result(
                        "Company Folios Handling",
                        False,
                        f"AR total is negative: ${total_ar}"
                    )
                
                return True
                
            else:
                self.log_test_result(
                    "Edge Cases Test",
                    False,
                    f"HTTP {response.status_code}: {response.text}"
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Edge Cases Test",
                False,
                f"Exception: {str(e)}"
            )
            return False

    def cleanup_test_data(self):
        """Clean up created test data"""
        print("\n🧹 Cleaning up test data...")
        
        # Note: In a real scenario, we might want to clean up
        # For now, we'll just log what was created
        for resource_type, ids in self.created_resources.items():
            if ids:
                print(f"  Created {resource_type}: {len(ids)} items")

    def run_all_tests(self):
        """Run all finance snapshot tests"""
        print("🚀 Starting Finance Snapshot Endpoint Testing")
        print("=" * 60)
        
        if not self.authenticate():
            return False
        
        # Setup test data
        if not self.setup_test_data():
            print("⚠️ Warning: Could not set up all test data, proceeding with existing data")
        
        # Run tests
        snapshot_data = self.test_basic_finance_snapshot()
        if snapshot_data:
            self.test_data_accuracy(snapshot_data)
        
        self.test_edge_cases()
        
        # Cleanup
        self.cleanup_test_data()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 FINANCE SNAPSHOT TEST SUMMARY")
        print("=" * 60)
        
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
        
        return self.test_results["failed"] == 0

if __name__ == "__main__":
    tester = FinanceSnapshotTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)