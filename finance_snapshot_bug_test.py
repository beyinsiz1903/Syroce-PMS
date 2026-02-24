#!/usr/bin/env python3
"""
Finance Snapshot Bug Detection Test
Identifies the payment_date vs processed_at field mismatch
"""

import requests
import json
import sys
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://improvement-guide-1.preview.emergentagent.com/api"
TEST_EMAIL = "financetest@hotel.com"
TEST_PASSWORD = "test123456"

class FinanceBugTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.test_results = {"passed": 0, "failed": 0, "details": []}

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
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                })
                print(f"✅ Authentication successful")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code}")
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

    def test_payment_date_field_issue(self):
        """Test to identify the payment_date vs processed_at field mismatch"""
        print("\n🔍 Testing Payment Date Field Issue")
        
        try:
            # Get finance snapshot
            response = self.session.get(f"{BACKEND_URL}/reports/finance-snapshot")
            
            if response.status_code == 200:
                data = response.json()
                
                # Check today's collections
                todays_collections = data.get('todays_collections', {})
                todays_amount = todays_collections.get('amount', 0)
                todays_count = todays_collections.get('payment_count', 0)
                
                # Check MTD collections
                mtd_collections = data.get('mtd_collections', {})
                mtd_amount = mtd_collections.get('amount', 0)
                
                print(f"📊 Finance Snapshot Results:")
                print(f"  Today's Collections: ${todays_amount} ({todays_count} payments)")
                print(f"  MTD Collections: ${mtd_amount}")
                
                # We know we created a payment today, so if collections are 0, there's a bug
                if todays_amount == 0 and todays_count == 0:
                    self.log_test_result(
                        "Payment Date Field Bug Detection",
                        False,
                        "Today's collections are 0 despite having payments today - likely payment_date vs processed_at field mismatch"
                    )
                    
                    # Let's verify by checking the actual payment data
                    print("\n🔍 Investigating payment data structure...")
                    
                    # Get folio details to see payment structure
                    folio_response = self.session.get(f"{BACKEND_URL}/folio/1d11d7d5-48f0-43a7-97b3-34d1e84fe911")
                    if folio_response.status_code == 200:
                        folio_data = folio_response.json()
                        payments = folio_data.get('payments', [])
                        
                        if payments:
                            payment = payments[0]
                            print(f"📋 Payment Structure:")
                            print(f"  Has 'payment_date' field: {'payment_date' in payment}")
                            print(f"  Has 'processed_at' field: {'processed_at' in payment}")
                            
                            if 'processed_at' in payment and 'payment_date' not in payment:
                                self.log_test_result(
                                    "Payment Field Structure Analysis",
                                    False,
                                    "Payment uses 'processed_at' field but Finance Snapshot looks for 'payment_date'"
                                )
                            else:
                                self.log_test_result(
                                    "Payment Field Structure Analysis",
                                    True,
                                    "Payment field structure is correct"
                                )
                        else:
                            self.log_test_result(
                                "Payment Data Availability",
                                False,
                                "No payment data found in folio"
                            )
                    
                else:
                    self.log_test_result(
                        "Payment Date Field Bug Detection",
                        True,
                        f"Collections data looks correct: ${todays_amount} today, ${mtd_amount} MTD"
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
                "Payment Date Field Bug Test",
                False,
                f"Exception: {str(e)}"
            )
            return False

    def run_bug_detection_tests(self):
        """Run bug detection tests"""
        print("🐛 Starting Finance Snapshot Bug Detection")
        print("=" * 60)
        
        if not self.authenticate():
            return False
        
        # Test payment date field issue
        self.test_payment_date_field_issue()
        
        # Print summary
        print("\n" + "=" * 60)
        print("🐛 BUG DETECTION SUMMARY")
        print("=" * 60)
        
        total_tests = self.test_results["passed"] + self.test_results["failed"]
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {self.test_results['passed']} ✅")
        print(f"Failed: {self.test_results['failed']} ❌")
        
        if self.test_results["failed"] > 0:
            print("\n🐛 BUGS DETECTED:")
            for result in self.test_results["details"]:
                if "❌ FAIL" in result["status"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        if self.test_results["passed"] > 0:
            print("\n✅ TESTS PASSED:")
            for result in self.test_results["details"]:
                if "✅ PASS" in result["status"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        return self.test_results["failed"] == 0

if __name__ == "__main__":
    tester = FinanceBugTester()
    success = tester.run_bug_detection_tests()
    sys.exit(0 if success else 1)