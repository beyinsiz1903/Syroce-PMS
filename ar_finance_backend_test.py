#!/usr/bin/env python3
"""
AR/Finance Backend Endpoint Testing
Test AR (Accounts Receivable) and City Ledger functionality
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://locust-load-test.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class ARFinanceBackendTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.test_results = []
        
    def log_result(self, test_name, success, response_time, details):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        self.test_results.append({
            'test': test_name,
            'status': status,
            'response_time': f"{response_time:.1f}ms",
            'details': details
        })
        print(f"{status} {test_name} ({response_time:.1f}ms) - {details}")
    
    def authenticate(self):
        """Login and get JWT token"""
        print("🔐 Authenticating...")
        
        login_data = {
            "email": LOGIN_EMAIL,
            "password": LOGIN_PASSWORD
        }
        
        start_time = time.time()
        try:
            response = self.session.post(f"{BASE_URL}/auth/login", json=login_data)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})
                self.log_result("Authentication", True, response_time, f"Logged in as {LOGIN_EMAIL}")
                return True
            else:
                self.log_result("Authentication", False, response_time, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("Authentication", False, response_time, f"Exception: {str(e)}")
            return False
    
    def test_company_aging_report(self):
        """Test GET /reports/company-aging"""
        print("\n📊 Testing Company Aging Report...")
        
        start_time = time.time()
        try:
            response = self.session.get(f"{BASE_URL}/reports/company-aging")
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ['report_date', 'total_ar', 'company_count', 'companies']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Company Aging Report", False, response_time, 
                                  f"Missing fields: {missing_fields}")
                    return False
                
                # Verify companies structure if any exist
                if data['companies']:
                    company = data['companies'][0]
                    company_fields = ['company_name', 'corporate_code', 'total_balance', 'aging', 'folio_count']
                    missing_company_fields = [field for field in company_fields if field not in company]
                    
                    if missing_company_fields:
                        self.log_result("Company Aging Report", False, response_time, 
                                      f"Missing company fields: {missing_company_fields}")
                        return False
                    
                    # Verify aging structure
                    aging = company.get('aging', {})
                    aging_fields = ['0-7 days', '8-14 days', '15-30 days', '30+ days']
                    missing_aging_fields = [field for field in aging_fields if field not in aging]
                    
                    if missing_aging_fields:
                        self.log_result("Company Aging Report", False, response_time, 
                                      f"Missing aging fields: {missing_aging_fields}")
                        return False
                
                self.log_result("Company Aging Report", True, response_time, 
                              f"Report generated: {data['company_count']} companies, Total AR: {data['total_ar']}")
                return True
            else:
                self.log_result("Company Aging Report", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("Company Aging Report", False, response_time, f"Exception: {str(e)}")
            return False
    
    def test_company_aging_excel(self):
        """Test GET /reports/company-aging/excel"""
        print("\n📈 Testing Company Aging Excel Export...")
        
        start_time = time.time()
        try:
            response = self.session.get(f"{BASE_URL}/reports/company-aging/excel")
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                # Check content type
                content_type = response.headers.get('content-type', '')
                expected_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                
                if expected_type in content_type:
                    file_size = len(response.content)
                    self.log_result("Company Aging Excel", True, response_time, 
                                  f"Excel file generated ({file_size} bytes)")
                    return True
                else:
                    self.log_result("Company Aging Excel", False, response_time, 
                                  f"Wrong content type: {content_type}")
                    return False
            else:
                self.log_result("Company Aging Excel", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("Company Aging Excel", False, response_time, f"Exception: {str(e)}")
            return False
    
    def test_pending_ar(self):
        """Test GET /folio/pending-ar"""
        print("\n💰 Testing Pending AR Report...")
        
        start_time = time.time()
        try:
            response = self.session.get(f"{BASE_URL}/folio/pending-ar")
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Should return an array
                if not isinstance(data, list):
                    self.log_result("Pending AR", False, response_time, 
                                  f"Expected array, got {type(data)}")
                    return False
                
                # If data exists, verify structure
                if data:
                    record = data[0]
                    required_fields = ['company_id', 'company_name', 'total_outstanding', 
                                     'open_folios_count', 'days_outstanding', 'aging']
                    missing_fields = [field for field in required_fields if field not in record]
                    
                    if missing_fields:
                        self.log_result("Pending AR", False, response_time, 
                                      f"Missing fields: {missing_fields}")
                        return False
                
                self.log_result("Pending AR", True, response_time, 
                              f"Retrieved {len(data)} pending AR records")
                return True
            else:
                self.log_result("Pending AR", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("Pending AR", False, response_time, f"Exception: {str(e)}")
            return False
    
    def test_city_ledger_accounts(self):
        """Test GET /cashiering/city-ledger"""
        print("\n🏦 Testing City Ledger Accounts...")
        
        start_time = time.time()
        try:
            response = self.session.get(f"{BASE_URL}/cashiering/city-ledger")
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ['accounts', 'total_count']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("City Ledger Accounts", False, response_time, 
                                  f"Missing fields: {missing_fields}")
                    return False
                
                self.log_result("City Ledger Accounts", True, response_time, 
                              f"Retrieved {data['total_count']} city ledger accounts")
                return True
            else:
                self.log_result("City Ledger Accounts", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("City Ledger Accounts", False, response_time, f"Exception: {str(e)}")
            return False
    
    def test_create_city_ledger_account(self):
        """Test POST /cashiering/city-ledger"""
        print("\n➕ Testing Create City Ledger Account...")
        
        account_data = {
            "account_name": "Test Corp AR Finance",
            "company_name": "Test Corp AR Finance", 
            "credit_limit": 10000
        }
        
        start_time = time.time()
        try:
            response = self.session.post(f"{BASE_URL}/cashiering/city-ledger", json=account_data)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ['success', 'account_id', 'credit_limit']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Create City Ledger Account", False, response_time, 
                                  f"Missing fields: {missing_fields}")
                    return False, None
                
                if not data.get('success'):
                    self.log_result("Create City Ledger Account", False, response_time, 
                                  "Success field is False")
                    return False, None
                
                account_id = data.get('account_id')
                self.log_result("Create City Ledger Account", True, response_time, 
                              f"Account created: {account_id}, Credit limit: {data['credit_limit']}")
                return True, account_id
            else:
                self.log_result("Create City Ledger Account", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False, None
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("Create City Ledger Account", False, response_time, f"Exception: {str(e)}")
            return False, None
    
    def test_ar_aging_report(self):
        """Test GET /cashiering/ar-aging-report"""
        print("\n📅 Testing AR Aging Report...")
        
        start_time = time.time()
        try:
            response = self.session.get(f"{BASE_URL}/cashiering/ar-aging-report")
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response structure
                required_fields = ['aging_buckets', 'totals', 'generated_at']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("AR Aging Report", False, response_time, 
                                  f"Missing fields: {missing_fields}")
                    return False
                
                # Verify aging buckets structure
                aging_buckets = data.get('aging_buckets', {})
                bucket_fields = ['current', '30_days', '60_days', '90_plus']
                missing_bucket_fields = [field for field in bucket_fields if field not in aging_buckets]
                
                if missing_bucket_fields:
                    self.log_result("AR Aging Report", False, response_time, 
                                  f"Missing aging bucket fields: {missing_bucket_fields}")
                    return False
                
                # Verify totals structure
                totals = data.get('totals', {})
                total_fields = ['current', '30_days', '60_days', '90_plus', 'total']
                missing_total_fields = [field for field in total_fields if field not in totals]
                
                if missing_total_fields:
                    self.log_result("AR Aging Report", False, response_time, 
                                  f"Missing total fields: {missing_total_fields}")
                    return False
                
                self.log_result("AR Aging Report", True, response_time, 
                              f"Report generated, Total AR: {totals.get('total', 0)}")
                return True
            else:
                self.log_result("AR Aging Report", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("AR Aging Report", False, response_time, f"Exception: {str(e)}")
            return False
    
    def test_city_ledger_payment(self, account_id):
        """Test POST /cashiering/city-ledger-payment"""
        print("\n💳 Testing City Ledger Payment...")
        
        if not account_id:
            self.log_result("City Ledger Payment", False, 0, "No account_id provided")
            return False
        
        # Use query parameters instead of JSON body
        params = {
            "account_id": account_id,
            "amount": 100,
            "payment_method": "bank_transfer"
        }
        
        start_time = time.time()
        try:
            response = self.session.post(f"{BASE_URL}/cashiering/city-ledger-payment", params=params)
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response has new_balance
                if 'new_balance' not in data:
                    self.log_result("City Ledger Payment", False, response_time, 
                                  "Missing new_balance field")
                    return False
                
                new_balance = data.get('new_balance')
                self.log_result("City Ledger Payment", True, response_time, 
                              f"Payment processed: Amount {params['amount']}, New balance: {new_balance}")
                return True
            else:
                self.log_result("City Ledger Payment", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("City Ledger Payment", False, response_time, f"Exception: {str(e)}")
            return False
    
    def test_city_ledger_transactions(self, account_id):
        """Test GET /cashiering/city-ledger/{account_id}/transactions"""
        print("\n📋 Testing City Ledger Transactions...")
        
        if not account_id:
            self.log_result("City Ledger Transactions", False, 0, "No account_id provided")
            return False
        
        start_time = time.time()
        try:
            response = self.session.get(f"{BASE_URL}/cashiering/city-ledger/{account_id}/transactions")
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                
                # Verify response has summary
                if 'summary' not in data:
                    self.log_result("City Ledger Transactions", False, response_time, 
                                  "Missing summary field")
                    return False
                
                summary = data.get('summary', {})
                summary_fields = ['total_charges', 'total_payments', 'current_balance', 'transaction_count']
                missing_summary_fields = [field for field in summary_fields if field not in summary]
                
                if missing_summary_fields:
                    self.log_result("City Ledger Transactions", False, response_time, 
                                  f"Missing summary fields: {missing_summary_fields}")
                    return False
                
                self.log_result("City Ledger Transactions", True, response_time, 
                              f"Transactions retrieved: {summary.get('transaction_count', 0)} transactions, Balance: {summary.get('current_balance', 0)}")
                return True
            else:
                self.log_result("City Ledger Transactions", False, response_time, 
                              f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_result("City Ledger Transactions", False, response_time, f"Exception: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all AR/Finance tests"""
        print("🚀 Starting AR/Finance Backend Testing...")
        print(f"Base URL: {BASE_URL}")
        print(f"Login: {LOGIN_EMAIL}")
        print("=" * 60)
        
        # Authenticate first
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Test results tracking
        total_tests = 0
        passed_tests = 0
        
        # Run all tests
        tests = [
            self.test_company_aging_report,
            self.test_company_aging_excel,
            self.test_pending_ar,
            self.test_city_ledger_accounts,
            self.test_ar_aging_report
        ]
        
        # Run basic tests
        for test in tests:
            total_tests += 1
            if test():
                passed_tests += 1
        
        # Test account creation and related operations
        total_tests += 1
        success, account_id = self.test_create_city_ledger_account()
        if success:
            passed_tests += 1
            
            # Test payment with created account
            total_tests += 1
            if self.test_city_ledger_payment(account_id):
                passed_tests += 1
            
            # Test transactions with created account
            total_tests += 1
            if self.test_city_ledger_transactions(account_id):
                passed_tests += 1
        else:
            # Still test with a dummy account_id to see if endpoint exists
            total_tests += 2
            self.test_city_ledger_payment("dummy-account-id")
            self.test_city_ledger_transactions("dummy-account-id")
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 AR/FINANCE BACKEND TEST SUMMARY")
        print("=" * 60)
        
        for result in self.test_results:
            print(f"{result['status']} {result['test']} ({result['response_time']}) - {result['details']}")
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"\n📈 OVERALL RESULTS:")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("🎉 EXCELLENT: AR/Finance backend is working perfectly!")
        elif success_rate >= 70:
            print("✅ GOOD: AR/Finance backend is mostly working with minor issues")
        else:
            print("⚠️ NEEDS ATTENTION: AR/Finance backend has significant issues")
        
        return success_rate >= 70

if __name__ == "__main__":
    tester = ARFinanceBackendTester()
    tester.run_all_tests()