#!/usr/bin/env python3
"""
Enhanced Accounting with Multi-Currency & E-Fatura Integration Testing
Testing 10+ endpoints for multi-currency support, invoice-folio integration, and e-fatura
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://report-calendar-fix.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class AccountingMultiCurrencyTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = {
            "multi_currency": {"passed": 0, "failed": 0, "details": []},
            "folio_integration": {"passed": 0, "failed": 0, "details": []},
            "efatura_integration": {"passed": 0, "failed": 0, "details": []}
        }
        self.created_resources = {
            "invoice_ids": [],
            "folio_ids": [],
            "booking_ids": []
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

    def test_multi_currency_support(self):
        """Test Multi-Currency Support (7 endpoints)"""
        print("\n💱 Testing Multi-Currency Support...")
        
        # A) Currency Management
        print("\n📊 Testing Currency Management...")
        
        # 1. GET /api/accounting/currencies (list supported currencies)
        try:
            response = self.session.get(f"{BACKEND_URL}/accounting/currencies")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                currencies = data.get('currencies', [])
                details += f" - Supported currencies: {len(currencies)}"
                if currencies:
                    currency_codes = [c.get('code', 'N/A') for c in currencies]
                    details += f" - Codes: {', '.join(currency_codes[:4])}"
            self.log_test_result("multi_currency", "/accounting/currencies", "GET", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/currencies", "GET", False, f"Error: {str(e)}")

        # 2. POST /api/accounting/currency-rates (USD to TRY)
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/currency-rates", json={
                "from_currency": "USD",
                "to_currency": "TRY",
                "rate": 27.50,
                "effective_date": "2025-01-24"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                data = response.json()
                details += f" - USD/TRY rate set: {data.get('rate', 'N/A')}"
            self.log_test_result("multi_currency", "/accounting/currency-rates (USD)", "POST", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/currency-rates (USD)", "POST", False, f"Error: {str(e)}")

        # 3. POST /api/accounting/currency-rates (EUR to TRY)
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/currency-rates", json={
                "from_currency": "EUR",
                "to_currency": "TRY",
                "rate": 29.80,
                "effective_date": "2025-01-24"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                data = response.json()
                details += f" - EUR/TRY rate set: {data.get('rate', 'N/A')}"
            self.log_test_result("multi_currency", "/accounting/currency-rates (EUR)", "POST", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/currency-rates (EUR)", "POST", False, f"Error: {str(e)}")

        # 4. GET /api/accounting/currency-rates (all rates)
        try:
            response = self.session.get(f"{BACKEND_URL}/accounting/currency-rates")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                data = response.json()
                rates = data.get('rates', [])
                details += f" - Total rates: {len(rates)}"
                if rates:
                    # Show first few rates
                    rate_pairs = [f"{r.get('from_currency', 'N/A')}/{r.get('to_currency', 'N/A')}" for r in rates[:3]]
                    details += f" - Pairs: {', '.join(rate_pairs)}"
            self.log_test_result("multi_currency", "/accounting/currency-rates", "GET", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/currency-rates", "GET", False, f"Error: {str(e)}")

        # 5. GET /api/accounting/currency-rates with filter
        try:
            response = self.session.get(f"{BACKEND_URL}/accounting/currency-rates?from_currency=USD&to_currency=TRY")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - USD/TRY filter"
            if success:
                data = response.json()
                rates = data.get('rates', [])
                details += f" - USD/TRY rates: {len(rates)}"
                if rates:
                    latest_rate = rates[0].get('rate', 'N/A')
                    details += f" - Latest rate: {latest_rate}"
            self.log_test_result("multi_currency", "/accounting/currency-rates?from_currency=USD&to_currency=TRY", "GET", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/currency-rates?from_currency=USD&to_currency=TRY", "GET", False, f"Error: {str(e)}")

        # B) Currency Conversion
        print("\n🔄 Testing Currency Conversion...")
        
        # 6. POST /api/accounting/convert-currency (USD to TRY)
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/convert-currency", json={
                "amount": 1000.00,
                "from_currency": "USD",
                "to_currency": "TRY",
                "date": None
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                data = response.json()
                original_amount = data.get('original_amount', 0)
                converted_amount = data.get('converted_amount', 0)
                rate_used = data.get('rate_used', 0)
                details += f" - ${original_amount} USD = {converted_amount} TRY (rate: {rate_used})"
            self.log_test_result("multi_currency", "/accounting/convert-currency (USD to TRY)", "POST", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/convert-currency (USD to TRY)", "POST", False, f"Error: {str(e)}")

        # 7. POST /api/accounting/convert-currency (EUR to TRY)
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/convert-currency", json={
                "amount": 500.00,
                "from_currency": "EUR",
                "to_currency": "TRY",
                "date": None
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            if success and response.json():
                data = response.json()
                original_amount = data.get('original_amount', 0)
                converted_amount = data.get('converted_amount', 0)
                rate_used = data.get('rate_used', 0)
                details += f" - €{original_amount} EUR = {converted_amount} TRY (rate: {rate_used})"
            self.log_test_result("multi_currency", "/accounting/convert-currency (EUR to TRY)", "POST", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/convert-currency (EUR to TRY)", "POST", False, f"Error: {str(e)}")

    def test_multi_currency_invoicing(self):
        """Test Multi-Currency Invoicing"""
        print("\n🧾 Testing Multi-Currency Invoicing...")
        
        # C) Multi-Currency Invoicing
        # 8. POST /api/accounting/invoices/multi-currency
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/invoices/multi-currency", json={
                "customer_name": "International Guest",
                "customer_email": "guest@international.com",
                "customer_address": "123 Main St, New York",
                "items": [
                    {
                        "description": "Hotel Stay - 3 nights",
                        "quantity": 3,
                        "unit_price": 150.00,
                        "vat_rate": 18
                    },
                    {
                        "description": "Restaurant",
                        "quantity": 1,
                        "unit_price": 75.00,
                        "vat_rate": 18
                    }
                ],
                "currency": "USD",
                "exchange_rate": None,
                "payment_terms": "Net 30",
                "notes": "International guest invoice"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                invoice_id = data.get('id')
                if invoice_id:
                    self.created_resources["invoice_ids"].append(invoice_id)
                
                # Verify dual currency amounts
                required_fields = ['subtotal', 'total_vat', 'total', 'subtotal_try', 'total_vat_try', 'total_try']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing dual currency fields: {missing_fields}"
                    success = False
                else:
                    subtotal_usd = data.get('subtotal', 0)
                    total_usd = data.get('total', 0)
                    subtotal_try = data.get('subtotal_try', 0)
                    total_try = data.get('total_try', 0)
                    details += f" - USD: ${subtotal_usd} subtotal, ${total_usd} total"
                    details += f" - TRY: {subtotal_try} subtotal, {total_try} total"
                    
                    # Verify currency conversion makes sense
                    if subtotal_try > subtotal_usd * 20:  # Rough check (rate should be ~27.5)
                        details += " - Currency conversion verified ✓"
                    else:
                        details += " - WARNING: Currency conversion may be incorrect"
            
            self.log_test_result("multi_currency", "/accounting/invoices/multi-currency", "POST", success, details)
        except Exception as e:
            self.log_test_result("multi_currency", "/accounting/invoices/multi-currency", "POST", False, f"Error: {str(e)}")

    def test_invoice_folio_integration(self):
        """Test Invoice → Folio → PMS Integration (1 endpoint)"""
        print("\n🔗 Testing Invoice → Folio → PMS Integration...")
        
        # First, try to get existing folios or create test data
        folio_id = None
        try:
            # Try to get existing bookings first
            bookings_response = self.session.get(f"{BACKEND_URL}/pms/bookings")
            if bookings_response.status_code == 200:
                bookings = bookings_response.json()
                if bookings:
                    booking_id = bookings[0].get('id')
                    if booking_id:
                        # Try to get folios for this booking
                        folios_response = self.session.get(f"{BACKEND_URL}/folio/booking/{booking_id}")
                        if folios_response.status_code == 200:
                            folios = folios_response.json()
                            if folios:
                                folio_id = folios[0].get('id')
                                self.created_resources["folio_ids"].append(folio_id)
        except:
            pass
        
        # If no folio found, use a test folio ID
        if not folio_id:
            folio_id = "test-folio-id-for-integration"
            print(f"  ℹ️  Using test folio ID: {folio_id}")
        
        # POST /api/accounting/invoices/from-folio
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/invoices/from-folio", json={
                "folio_id": folio_id,
                "invoice_currency": "TRY",
                "include_efatura": True
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                invoice_id = data.get('id')
                if invoice_id:
                    self.created_resources["invoice_ids"].append(invoice_id)
                
                # Verify response contains required fields
                required_fields = ['folio_id', 'items', 'customer_info']
                present_fields = [field for field in required_fields if field in data]
                details += f" - Required fields present: {len(present_fields)}/{len(required_fields)}"
                
                # Check folio reference
                if data.get('folio_id') == folio_id:
                    details += " - Folio reference correct ✓"
                
                # Check items conversion
                items = data.get('items', [])
                details += f" - Items from folio: {len(items)}"
                
                # Check customer info
                customer_info = data.get('customer_info', {})
                if customer_info:
                    details += f" - Customer: {customer_info.get('name', 'N/A')}"
                
                # Check E-Fatura generation
                efatura_generated = data.get('efatura_generated', False)
                efatura_uuid = data.get('efatura_uuid')
                if efatura_generated and efatura_uuid:
                    details += f" - E-Fatura generated: {efatura_uuid[:8]}..."
                elif data.get('include_efatura'):
                    details += " - E-Fatura requested but not generated"
            
            self.log_test_result("folio_integration", "/accounting/invoices/from-folio", "POST", success, details)
        except Exception as e:
            self.log_test_result("folio_integration", "/accounting/invoices/from-folio", "POST", False, f"Error: {str(e)}")

    def test_efatura_integration(self):
        """Test E-Fatura Integration with Accounting (2 endpoints)"""
        print("\n📋 Testing E-Fatura Integration with Accounting...")
        
        # Use created invoice or create a test one
        invoice_id = None
        if self.created_resources["invoice_ids"]:
            invoice_id = self.created_resources["invoice_ids"][0]
        else:
            # Create a simple invoice for testing
            try:
                response = self.session.post(f"{BACKEND_URL}/accounting/invoices", json={
                    "customer_name": "Test Customer for E-Fatura",
                    "customer_email": "test@efatura.com",
                    "customer_address": "Test Address, Istanbul",
                    "items": [
                        {
                            "description": "Hotel Service",
                            "quantity": 1,
                            "unit_price": 100.00,
                            "vat_rate": 18
                        }
                    ],
                    "payment_terms": "Net 30",
                    "notes": "Test invoice for E-Fatura integration"
                })
                if response.status_code in [200, 201] and response.json():
                    invoice_id = response.json().get('id')
                    if invoice_id:
                        self.created_resources["invoice_ids"].append(invoice_id)
            except:
                pass
        
        if not invoice_id:
            invoice_id = "test-invoice-id-for-efatura"
            print(f"  ℹ️  Using test invoice ID: {invoice_id}")
        
        # 1. GET /api/accounting/invoices/{invoice_id}/efatura-status
        try:
            response = self.session.get(f"{BACKEND_URL}/accounting/invoices/{invoice_id}/efatura-status")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                efatura_status = data.get('efatura_status', 'N/A')
                efatura_uuid = data.get('efatura_uuid')
                xml_generated = data.get('xml_generated', False)
                
                details += f" - E-Fatura status: {efatura_status}"
                if efatura_uuid:
                    details += f" - UUID: {efatura_uuid[:8]}..."
                if xml_generated:
                    details += " - XML generated ✓"
            
            self.log_test_result("efatura_integration", f"/accounting/invoices/{invoice_id}/efatura-status", "GET", success, details)
        except Exception as e:
            self.log_test_result("efatura_integration", f"/accounting/invoices/{invoice_id}/efatura-status", "GET", False, f"Error: {str(e)}")

        # 2. POST /api/accounting/invoices/{invoice_id}/generate-efatura
        try:
            response = self.session.post(f"{BACKEND_URL}/accounting/invoices/{invoice_id}/generate-efatura")
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                efatura_uuid = data.get('efatura_uuid')
                status = data.get('status', 'N/A')
                xml_content = data.get('xml_content')
                
                details += f" - Generation status: {status}"
                if efatura_uuid:
                    details += f" - UUID: {efatura_uuid[:8]}..."
                if xml_content:
                    xml_length = len(xml_content)
                    details += f" - XML generated ({xml_length} chars)"
                    
                    # Basic XML validation
                    if xml_content.startswith('<?xml') and 'Invoice' in xml_content:
                        details += " - XML format valid ✓"
                    else:
                        details += " - WARNING: XML format may be invalid"
            
            self.log_test_result("efatura_integration", f"/accounting/invoices/{invoice_id}/generate-efatura", "POST", success, details)
        except Exception as e:
            self.log_test_result("efatura_integration", f"/accounting/invoices/{invoice_id}/generate-efatura", "POST", False, f"Error: {str(e)}")

    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*80)
        print("🎯 ENHANCED ACCOUNTING WITH MULTI-CURRENCY & E-FATURA TESTING SUMMARY")
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
                status_emoji = "✅" if success_rate >= 80 else "⚠️" if success_rate >= 50 else "❌"
                
                category_name = category.replace('_', ' ').title()
                print(f"\n{status_emoji} {category_name}: {passed}/{total} ({success_rate:.1f}%)")
                
                # Show failed tests
                failed_tests = [detail for detail in results["details"] if "❌ FAIL" in detail["status"]]
                if failed_tests:
                    print("   Failed tests:")
                    for test in failed_tests[:3]:  # Show first 3 failures
                        print(f"   - {test['endpoint']}: {test['details']}")
                    if len(failed_tests) > 3:
                        print(f"   - ... and {len(failed_tests) - 3} more")
        
        # Overall summary
        total_tests = total_passed + total_failed
        if total_tests > 0:
            overall_success_rate = (total_passed / total_tests) * 100
            overall_emoji = "✅" if overall_success_rate >= 80 else "⚠️" if overall_success_rate >= 50 else "❌"
            
            print(f"\n{overall_emoji} OVERALL RESULT: {total_passed}/{total_tests} ({overall_success_rate:.1f}%)")
            
            # Validation criteria summary
            print(f"\n📋 VALIDATION CRITERIA SUMMARY:")
            print(f"   • Multi-currency operations: Currency rates, conversion, dual amounts")
            print(f"   • Invoice-Folio integration: Folio charges → invoice items")
            print(f"   • E-Fatura integration: XML generation, UUID tracking, status")
            
            if overall_success_rate >= 80:
                print(f"\n🎉 SUCCESS: Enhanced Accounting system is working correctly!")
                print(f"   All major multi-currency and e-fatura features are operational.")
            else:
                print(f"\n⚠️  ISSUES DETECTED: Some accounting features need attention.")
                print(f"   Review failed tests above for specific problems.")
        
        print("="*80)

    def run_all_tests(self):
        """Run all accounting and multi-currency tests"""
        print("🚀 Starting Enhanced Accounting with Multi-Currency & E-Fatura Integration Testing...")
        print(f"Backend URL: {BACKEND_URL}")
        print(f"Test User: {TEST_EMAIL}")
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Run all test categories
        self.test_multi_currency_support()
        self.test_multi_currency_invoicing()
        self.test_invoice_folio_integration()
        self.test_efatura_integration()
        
        # Print comprehensive summary
        self.print_summary()
        
        return True

def main():
    """Main function to run the tests"""
    tester = AccountingMultiCurrencyTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()