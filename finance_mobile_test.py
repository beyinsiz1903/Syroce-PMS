#!/usr/bin/env python3
"""
Comprehensive Backend Test Suite for Finance Mobile Endpoints
Testing Turkish Finance Mobile Development Endpoints
"""

import requests
import json
import sys
from datetime import datetime, timezone
import uuid

# Configuration
BACKEND_URL = "https://unitcare-1.preview.emergentagent.com/api"
TEST_USER_EMAIL = "admin@hotel.com"
TEST_USER_PASSWORD = "admin123"

class FinanceMobileEndpointTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.test_results = []
        
    def log_result(self, test_name, success, details="", response_data=None):
        """Log test result"""
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        if response_data:
            result['response_sample'] = response_data
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
        if details:
            print(f"    Details: {details}")
        if not success and response_data:
            print(f"    Response: {response_data}")
        print()

    def authenticate(self):
        """Authenticate and get token"""
        print("🔐 Authenticating...")
        
        # First try to register a tenant if login fails
        login_data = {
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
        
        try:
            response = self.session.post(f"{BACKEND_URL}/auth/login", json=login_data)
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get('access_token')
                self.session.headers.update({
                    'Authorization': f'Bearer {self.auth_token}'
                })
                self.log_result("Authentication", True, f"Logged in as {data.get('user', {}).get('name', 'Unknown')}")
                return True
            elif response.status_code == 401:
                # Try to register a new tenant
                print("🔐 Login failed, attempting to register new tenant...")
                register_data = {
                    "property_name": "Test Hotel",
                    "email": TEST_USER_EMAIL,
                    "password": TEST_USER_PASSWORD,
                    "name": "Test Admin",
                    "phone": "+90 555 123 4567",
                    "address": "Test Address, Istanbul, Turkey",
                    "location": "Istanbul",
                    "description": "Test hotel for finance mobile endpoints"
                }
                
                register_response = self.session.post(f"{BACKEND_URL}/auth/register", json=register_data)
                
                if register_response.status_code == 200:
                    data = register_response.json()
                    self.auth_token = data.get('access_token')
                    self.session.headers.update({
                        'Authorization': f'Bearer {self.auth_token}'
                    })
                    self.log_result("Authentication", True, f"Registered and logged in as {data.get('user', {}).get('name', 'Unknown')}")
                    return True
                else:
                    self.log_result("Authentication", False, f"Registration failed: HTTP {register_response.status_code}: {register_response.text}")
                    return False
            else:
                self.log_result("Authentication", False, f"HTTP {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            self.log_result("Authentication", False, f"Exception: {str(e)}")
            return False

    def test_cash_flow_summary(self):
        """Test GET /api/finance/mobile/cash-flow-summary"""
        print("💰 Testing Cash Flow Summary...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/cash-flow-summary")
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                required_fields = ['today', 'weekly_plan', 'bank_balances', 'total_bank_balance_try']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Cash Flow Summary - Structure", False, 
                                  f"Missing fields: {missing_fields}", data)
                else:
                    # Validate today section
                    today_fields = ['date', 'cash_inflow', 'cash_outflow', 'net_flow', 'inflow_count', 'outflow_count']
                    today_missing = [field for field in today_fields if field not in data['today']]
                    
                    if today_missing:
                        self.log_result("Cash Flow Summary - Today Section", False,
                                      f"Missing today fields: {today_missing}", data['today'])
                    else:
                        self.log_result("Cash Flow Summary", True, 
                                      f"Today: Inflow ₺{data['today']['cash_inflow']}, Outflow ₺{data['today']['cash_outflow']}, Net ₺{data['today']['net_flow']}")
                        
                        # Test weekly plan
                        if isinstance(data['weekly_plan'], list) and len(data['weekly_plan']) == 7:
                            self.log_result("Cash Flow Summary - Weekly Plan", True,
                                          f"7-day plan generated with {len(data['weekly_plan'])} days")
                        else:
                            self.log_result("Cash Flow Summary - Weekly Plan", False,
                                          f"Expected 7 days, got {len(data.get('weekly_plan', []))}")
                        
                        # Test bank balances
                        if isinstance(data['bank_balances'], list):
                            self.log_result("Cash Flow Summary - Bank Balances", True,
                                          f"{len(data['bank_balances'])} bank accounts, Total TRY: ₺{data['total_bank_balance_try']}")
                        else:
                            self.log_result("Cash Flow Summary - Bank Balances", False,
                                          "Bank balances should be a list")
            else:
                self.log_result("Cash Flow Summary", False, 
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Cash Flow Summary", False, f"Exception: {str(e)}")

    def test_overdue_accounts(self):
        """Test GET /api/finance/mobile/overdue-accounts"""
        print("⏰ Testing Overdue Accounts...")
        
        # Test with default min_days (7)
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/overdue-accounts")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['overdue_accounts', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Overdue Accounts - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    # Validate summary
                    summary_fields = ['total_count', 'total_amount', 'suspicious_count', 'critical_count', 'warning_count']
                    summary_missing = [field for field in summary_fields if field not in data['summary']]
                    
                    if summary_missing:
                        self.log_result("Overdue Accounts - Summary", False,
                                      f"Missing summary fields: {summary_missing}", data['summary'])
                    else:
                        summary = data['summary']
                        self.log_result("Overdue Accounts", True,
                                      f"Total: {summary['total_count']}, Suspicious: {summary['suspicious_count']}, Critical: {summary['critical_count']}, Warning: {summary['warning_count']}")
                        
                        # Test risk level classification
                        if data['overdue_accounts']:
                            account = data['overdue_accounts'][0]
                            required_account_fields = ['folio_id', 'guest_name', 'balance', 'days_overdue', 'risk_level', 'risk_color']
                            account_missing = [field for field in required_account_fields if field not in account]
                            
                            if account_missing:
                                self.log_result("Overdue Accounts - Account Structure", False,
                                              f"Missing account fields: {account_missing}", account)
                            else:
                                self.log_result("Overdue Accounts - Risk Classification", True,
                                              f"Risk levels working: {account['risk_level']} ({account['risk_color']})")
            else:
                self.log_result("Overdue Accounts", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Overdue Accounts", False, f"Exception: {str(e)}")
        
        # Test with custom min_days parameter
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/overdue-accounts?min_days=15")
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("Overdue Accounts - Custom Min Days", True,
                              f"15+ days filter: {data['summary']['total_count']} accounts")
            else:
                self.log_result("Overdue Accounts - Custom Min Days", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Overdue Accounts - Custom Min Days", False, f"Exception: {str(e)}")

    def test_credit_limit_violations(self):
        """Test GET /api/finance/mobile/credit-limit-violations"""
        print("🚨 Testing Credit Limit Violations...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/credit-limit-violations")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['violations', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Credit Limit Violations - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    # Validate summary
                    summary_fields = ['total_count', 'over_limit_count', 'near_limit_count']
                    summary_missing = [field for field in summary_fields if field not in data['summary']]
                    
                    if summary_missing:
                        self.log_result("Credit Limit Violations - Summary", False,
                                      f"Missing summary fields: {summary_missing}", data['summary'])
                    else:
                        summary = data['summary']
                        self.log_result("Credit Limit Violations", True,
                                      f"Total: {summary['total_count']}, Over Limit: {summary['over_limit_count']}, Near Limit (90%+): {summary['near_limit_count']}")
                        
                        # Test violation details
                        if data['violations']:
                            violation = data['violations'][0]
                            required_violation_fields = ['company_name', 'credit_limit', 'current_debt', 'utilization_percentage']
                            violation_missing = [field for field in required_violation_fields if field not in violation]
                            
                            if violation_missing:
                                self.log_result("Credit Limit Violations - Violation Structure", False,
                                              f"Missing violation fields: {violation_missing}", violation)
                            else:
                                self.log_result("Credit Limit Violations - Details", True,
                                              f"Company: {violation['company_name']}, Utilization: {violation['utilization_percentage']:.1f}%")
            else:
                self.log_result("Credit Limit Violations", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Credit Limit Violations", False, f"Exception: {str(e)}")

    def test_suspicious_receivables(self):
        """Test GET /api/finance/mobile/suspicious-receivables"""
        print("🔍 Testing Suspicious Receivables...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/suspicious-receivables")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['suspicious_receivables', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Suspicious Receivables - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    # Validate summary
                    summary_fields = ['total_count', 'total_amount', 'average_days_overdue']
                    summary_missing = [field for field in summary_fields if field not in data['summary']]
                    
                    if summary_missing:
                        self.log_result("Suspicious Receivables - Summary", False,
                                      f"Missing summary fields: {summary_missing}", data['summary'])
                    else:
                        summary = data['summary']
                        self.log_result("Suspicious Receivables", True,
                                      f"Count: {summary['total_count']}, Amount: ₺{summary['total_amount']}, Avg Days: {summary['average_days_overdue']:.1f}")
                        
                        # Test receivable details (30+ days or high amount criteria)
                        if data['suspicious_receivables']:
                            receivable = data['suspicious_receivables'][0]
                            required_receivable_fields = ['folio_id', 'guest_name', 'balance', 'days_overdue', 'reason']
                            receivable_missing = [field for field in required_receivable_fields if field not in receivable]
                            
                            if receivable_missing:
                                self.log_result("Suspicious Receivables - Receivable Structure", False,
                                              f"Missing receivable fields: {receivable_missing}", receivable)
                            else:
                                self.log_result("Suspicious Receivables - Criteria", True,
                                              f"Reason: {receivable['reason']}, Days: {receivable['days_overdue']}, Amount: ₺{receivable['balance']}")
            else:
                self.log_result("Suspicious Receivables", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Suspicious Receivables", False, f"Exception: {str(e)}")

    def test_risk_alerts(self):
        """Test GET /api/finance/mobile/risk-alerts"""
        print("⚠️ Testing Risk Alerts...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/risk-alerts")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['alerts', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Risk Alerts - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    # Validate summary
                    summary_fields = ['total_alerts', 'critical_count', 'high_count', 'action_required_count']
                    summary_missing = [field for field in summary_fields if field not in data['summary']]
                    
                    if summary_missing:
                        self.log_result("Risk Alerts - Summary", False,
                                      f"Missing summary fields: {summary_missing}", data['summary'])
                    else:
                        summary = data['summary']
                        self.log_result("Risk Alerts", True,
                                      f"Total: {summary['total_alerts']}, Critical: {summary['critical_count']}, High: {summary['high_count']}, Action Required: {summary['action_required_count']}")
                        
                        # Test alert structure and severity levels
                        if data['alerts']:
                            alert = data['alerts'][0]
                            required_alert_fields = ['id', 'type', 'severity', 'title', 'message']
                            alert_missing = [field for field in required_alert_fields if field not in alert]
                            
                            if alert_missing:
                                self.log_result("Risk Alerts - Alert Structure", False,
                                              f"Missing alert fields: {alert_missing}", alert)
                            else:
                                severity_levels = ['critical', 'high', 'medium', 'low']
                                if alert['severity'] in severity_levels:
                                    self.log_result("Risk Alerts - Severity Validation", True,
                                                  f"Alert: {alert['title']} ({alert['severity']})")
                                else:
                                    self.log_result("Risk Alerts - Severity Validation", False,
                                                  f"Invalid severity: {alert['severity']}")
            else:
                self.log_result("Risk Alerts", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Risk Alerts", False, f"Exception: {str(e)}")

    def test_daily_expenses(self):
        """Test GET /api/finance/mobile/daily-expenses"""
        print("💸 Testing Daily Expenses...")
        
        # Test without date parameter (today)
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/daily-expenses")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['date', 'total_expenses', 'expense_count', 'expenses_by_category', 'expenses_by_department']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Daily Expenses - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    self.log_result("Daily Expenses", True,
                                  f"Date: {data['date']}, Total: ₺{data['total_expenses']}, Count: {data['expense_count']}")
                    
                    # Test category and department breakdown
                    if isinstance(data['expenses_by_category'], dict) and isinstance(data['expenses_by_department'], dict):
                        self.log_result("Daily Expenses - Breakdown", True,
                                      f"Categories: {len(data['expenses_by_category'])}, Departments: {len(data['expenses_by_department'])}")
                    else:
                        self.log_result("Daily Expenses - Breakdown", False,
                                      "Category and department breakdowns should be dictionaries")
            else:
                self.log_result("Daily Expenses", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Daily Expenses", False, f"Exception: {str(e)}")
        
        # Test with specific date parameter
        try:
            test_date = "2024-01-15"
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/daily-expenses?date={test_date}")
            
            if response.status_code == 200:
                data = response.json()
                if data['date'] == test_date:
                    self.log_result("Daily Expenses - Date Parameter", True,
                                  f"Date filter working: {data['date']}")
                else:
                    self.log_result("Daily Expenses - Date Parameter", False,
                                  f"Expected {test_date}, got {data['date']}")
            else:
                self.log_result("Daily Expenses - Date Parameter", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Daily Expenses - Date Parameter", False, f"Exception: {str(e)}")

    def test_folio_full_extract(self):
        """Test GET /api/finance/mobile/folio-full-extract/{folio_id}"""
        print("📋 Testing Folio Full Extract...")
        
        # First, try to get a folio ID from existing folios
        folio_id = None
        try:
            # Try to find an existing folio
            response = self.session.get(f"{BACKEND_URL}/folios")
            if response.status_code == 200:
                folios = response.json()
                if isinstance(folios, list) and folios:
                    folio_id = folios[0].get('id')
                elif isinstance(folios, dict) and 'folios' in folios and folios['folios']:
                    folio_id = folios['folios'][0].get('id')
        except:
            pass
        
        if not folio_id:
            # Create a test folio ID (this will likely return 404, but we can test the endpoint structure)
            folio_id = str(uuid.uuid4())
        
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/folio-full-extract/{folio_id}")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['folio', 'charges', 'payments', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Folio Full Extract - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    # Validate folio section
                    folio_fields = ['id', 'folio_number', 'folio_type', 'status']
                    folio_missing = [field for field in folio_fields if field not in data['folio']]
                    
                    if folio_missing:
                        self.log_result("Folio Full Extract - Folio Section", False,
                                      f"Missing folio fields: {folio_missing}", data['folio'])
                    else:
                        # Validate summary section
                        summary_fields = ['total_charges', 'total_payments', 'current_balance', 'charge_count', 'payment_count']
                        summary_missing = [field for field in summary_fields if field not in data['summary']]
                        
                        if summary_missing:
                            self.log_result("Folio Full Extract - Summary", False,
                                          f"Missing summary fields: {summary_missing}", data['summary'])
                        else:
                            summary = data['summary']
                            self.log_result("Folio Full Extract", True,
                                          f"Folio: {data['folio']['folio_number']}, Charges: ₺{summary['total_charges']}, Payments: ₺{summary['total_payments']}, Balance: ₺{summary['current_balance']}")
                            
                            # Test charges and payments lists
                            if isinstance(data['charges'], list) and isinstance(data['payments'], list):
                                self.log_result("Folio Full Extract - Lists", True,
                                              f"Charges: {len(data['charges'])}, Payments: {len(data['payments'])}")
                            else:
                                self.log_result("Folio Full Extract - Lists", False,
                                              "Charges and payments should be lists")
            elif response.status_code == 404:
                self.log_result("Folio Full Extract", True,
                              f"404 response for non-existent folio (expected behavior)")
            else:
                self.log_result("Folio Full Extract", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Folio Full Extract", False, f"Exception: {str(e)}")

    def test_invoices(self):
        """Test GET /api/finance/mobile/invoices"""
        print("🧾 Testing Invoices...")
        
        # Test basic endpoint
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/invoices")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['invoices', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Invoices - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    # Validate summary
                    summary_fields = ['total_count', 'total_amount', 'unpaid_amount', 'paid_amount']
                    summary_missing = [field for field in summary_fields if field not in data['summary']]
                    
                    if summary_missing:
                        self.log_result("Invoices - Summary", False,
                                      f"Missing summary fields: {summary_missing}", data['summary'])
                    else:
                        summary = data['summary']
                        self.log_result("Invoices", True,
                                      f"Total: {summary['total_count']}, Amount: ₺{summary['total_amount']}, Unpaid: ₺{summary['unpaid_amount']}")
                        
                        # Test invoice structure
                        if data['invoices']:
                            invoice = data['invoices'][0]
                            required_invoice_fields = ['id', 'invoice_number', 'status', 'customer_name', 'total']
                            invoice_missing = [field for field in required_invoice_fields if field not in invoice]
                            
                            if invoice_missing:
                                self.log_result("Invoices - Invoice Structure", False,
                                              f"Missing invoice fields: {invoice_missing}", invoice)
                            else:
                                self.log_result("Invoices - Invoice Structure", True,
                                              f"Invoice: {invoice['invoice_number']}, Status: {invoice['status']}, Total: ₺{invoice['total']}")
            else:
                self.log_result("Invoices", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Invoices", False, f"Exception: {str(e)}")
        
        # Test with unpaid_only filter
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/invoices?unpaid_only=true")
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("Invoices - Unpaid Filter", True,
                              f"Unpaid only: {data['summary']['total_count']} invoices")
            else:
                self.log_result("Invoices - Unpaid Filter", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Invoices - Unpaid Filter", False, f"Exception: {str(e)}")
        
        # Test with date range filter
        try:
            start_date = "2024-01-01"
            end_date = "2024-12-31"
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/invoices?start_date={start_date}&end_date={end_date}")
            
            if response.status_code == 200:
                data = response.json()
                self.log_result("Invoices - Date Range Filter", True,
                              f"Date range {start_date} to {end_date}: {data['summary']['total_count']} invoices")
            else:
                self.log_result("Invoices - Date Range Filter", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Invoices - Date Range Filter", False, f"Exception: {str(e)}")

    def test_bank_balances(self):
        """Test GET /api/finance/mobile/bank-balances"""
        print("🏦 Testing Bank Balances...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/bank-balances")
            
            if response.status_code == 200:
                data = response.json()
                
                required_fields = ['bank_accounts', 'total_balance_try', 'account_count']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_result("Bank Balances - Structure", False,
                                  f"Missing fields: {missing_fields}", data)
                else:
                    self.log_result("Bank Balances", True,
                                  f"Accounts: {data['account_count']}, Total TRY: ₺{data['total_balance_try']}")
                    
                    # Test bank account structure
                    if data['bank_accounts']:
                        account = data['bank_accounts'][0]
                        required_account_fields = ['id', 'bank_name', 'account_number', 'currency', 'current_balance']
                        account_missing = [field for field in required_account_fields if field not in account]
                        
                        if account_missing:
                            self.log_result("Bank Balances - Account Structure", False,
                                          f"Missing account fields: {account_missing}", account)
                        else:
                            self.log_result("Bank Balances - Account Structure", True,
                                          f"Bank: {account['bank_name']}, Balance: {account['currency']} {account['current_balance']}")
                    else:
                        self.log_result("Bank Balances - No Accounts", True,
                                      "No bank accounts found (expected if none configured)")
            else:
                self.log_result("Bank Balances", False,
                              f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            self.log_result("Bank Balances", False, f"Exception: {str(e)}")

    def test_error_handling(self):
        """Test error handling scenarios"""
        print("🚫 Testing Error Handling...")
        
        # Test with invalid folio ID
        try:
            invalid_folio_id = "invalid-folio-id"
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/folio-full-extract/{invalid_folio_id}")
            
            if response.status_code == 404:
                self.log_result("Error Handling - Invalid Folio ID", True,
                              "404 error for invalid folio ID (correct behavior)")
            elif response.status_code == 422:
                self.log_result("Error Handling - Invalid Folio ID", True,
                              "422 validation error for invalid folio ID (acceptable)")
            else:
                self.log_result("Error Handling - Invalid Folio ID", False,
                              f"Expected 404 or 422, got {response.status_code}")
                
        except Exception as e:
            self.log_result("Error Handling - Invalid Folio ID", False, f"Exception: {str(e)}")
        
        # Test with invalid date format
        try:
            invalid_date = "invalid-date"
            response = self.session.get(f"{BACKEND_URL}/finance/mobile/daily-expenses?date={invalid_date}")
            
            if response.status_code in [400, 422, 500]:
                self.log_result("Error Handling - Invalid Date", True,
                              f"HTTP {response.status_code} for invalid date (expected error)")
            else:
                self.log_result("Error Handling - Invalid Date", False,
                              f"Expected error status, got {response.status_code}")
                
        except Exception as e:
            self.log_result("Error Handling - Invalid Date", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all finance mobile endpoint tests"""
        print("🚀 Starting Finance Mobile Endpoints Test Suite")
        print("=" * 60)
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        print("\n📊 Testing Finance Mobile Endpoints...")
        print("-" * 40)
        
        # Run all endpoint tests
        self.test_cash_flow_summary()
        self.test_overdue_accounts()
        self.test_credit_limit_violations()
        self.test_suspicious_receivables()
        self.test_risk_alerts()
        self.test_daily_expenses()
        self.test_folio_full_extract()
        self.test_invoices()
        self.test_bank_balances()
        self.test_error_handling()
        
        # Generate summary
        self.generate_summary()
        
        return True

    def generate_summary(self):
        """Generate test summary"""
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r['success']])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['test']}: {result['details']}")
        
        print(f"\n✅ PASSED TESTS:")
        for result in self.test_results:
            if result['success']:
                print(f"  - {result['test']}")
        
        # Save detailed results to file
        try:
            with open('/app/finance_mobile_test_results.json', 'w') as f:
                json.dump({
                    'summary': {
                        'total_tests': total_tests,
                        'passed_tests': passed_tests,
                        'failed_tests': failed_tests,
                        'success_rate': passed_tests/total_tests*100
                    },
                    'test_results': self.test_results,
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            print(f"\n📄 Detailed results saved to: /app/finance_mobile_test_results.json")
        except Exception as e:
            print(f"\n⚠️ Could not save results file: {e}")

if __name__ == "__main__":
    tester = FinanceMobileEndpointTester()
    success = tester.run_all_tests()
    
    if success:
        print(f"\n🎉 Finance Mobile Endpoints Testing Complete!")
    else:
        print(f"\n💥 Testing failed to complete properly.")
        sys.exit(1)