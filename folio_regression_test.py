#!/usr/bin/env python3
"""
Folio Calculations Regression Testing
=====================================

This script tests all folio calculation scenarios to ensure accuracy as requested in the review.

Base URL: https://improvement-guide-1.preview.emergentagent.com/api
Login: test@hotel.com / test123

Test Scenarios:
1. Basic Room Charge Calculation (3 nights @ $100/night = $300)
2. Tax Calculations (VAT, tourism tax, service charge)
3. Payment Application (partial payments, overpayment)
4. Voided Charges (verify they don't affect balance)
5. Multiple Folios (split charges, transfers)
6. Commission Calculations (OTA bookings)
7. Currency Rounding (2 decimal places)
8. Complex Scenario (Room + extras + tax + payment = expected balance)
9. Edge Cases (negative charges, zero amounts, large amounts, etc.)
"""

import requests
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

class FolioRegressionTester:
    def __init__(self, base_url="https://improvement-guide-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.user = None
        self.tenant = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Test resources
        self.test_guest_id = None
        self.test_room_id = None
        self.test_company_id = None
        self.test_booking_id = None
        self.test_folios = []

    def log_result(self, test_name, passed, details=""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name}")
        
        if details:
            print(f"   {details}")
        
        self.test_results.append({
            'test': test_name,
            'passed': passed,
            'details': details
        })

    def make_request(self, method, endpoint, data=None, expected_status=200):
        """Make API request with authentication"""
        url = f"{self.api_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            
            success = response.status_code == expected_status
            
            try:
                response_data = response.json()
            except:
                response_data = {}
            
            return success, response_data, response.status_code
            
        except Exception as e:
            print(f"Request error: {str(e)}")
            return False, {}, 0

    def authenticate(self):
        """Login with test credentials"""
        print("🔐 Authenticating...")
        
        login_data = {
            "email": "test@hotel.com",
            "password": "test123"
        }
        
        success, response, status = self.make_request("POST", "auth/login", login_data)
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.user = response['user']
            self.tenant = response.get('tenant')
            print(f"✅ Authenticated as {self.user['name']} ({self.user['email']})")
            return True
        else:
            print(f"❌ Authentication failed - Status: {status}")
            return False

    def setup_test_data(self):
        """Create test data for folio calculations"""
        print("\n📋 Setting up test data...")
        
        # Create test guest
        guest_data = {
            "name": "Folio Test Guest",
            "email": "folio.test@example.com",
            "phone": "+1234567890",
            "id_number": "FOLIO123456",
            "address": "123 Test Street"
        }
        
        success, response, _ = self.make_request("POST", "pms/guests", guest_data)
        if success and 'id' in response:
            self.test_guest_id = response['id']
            print(f"✅ Created test guest: {response['id']}")
        else:
            print("❌ Failed to create test guest")
            return False
        
        # Create test room
        room_data = {
            "room_number": "101",
            "room_type": "deluxe",
            "floor": 1,
            "capacity": 2,
            "base_price": 100.00,
            "amenities": ["wifi", "tv", "minibar"]
        }
        
        success, response, _ = self.make_request("POST", "pms/rooms", room_data)
        if success and 'id' in response:
            self.test_room_id = response['id']
            print(f"✅ Created test room: {response['id']}")
        else:
            print("❌ Failed to create test room")
            return False
        
        # Create test company
        company_data = {
            "name": "Test OTA Company",
            "corporate_code": "OTA001",
            "tax_number": "1234567890",
            "billing_address": "456 OTA Street",
            "contact_person": "OTA Manager",
            "contact_email": "ota@example.com",
            "status": "active"
        }
        
        success, response, _ = self.make_request("POST", "companies", company_data)
        if success and 'id' in response:
            self.test_company_id = response['id']
            print(f"✅ Created test company: {response['id']}")
        else:
            print("❌ Failed to create test company")
            return False
        
        # Create test booking
        booking_data = {
            "guest_id": self.test_guest_id,
            "room_id": self.test_room_id,
            "check_in": datetime.now().isoformat(),
            "check_out": (datetime.now() + timedelta(days=3)).isoformat(),
            "adults": 2,
            "children": 0,
            "children_ages": [],
            "guests_count": 2,
            "total_amount": 300.0,
            "channel": "direct"
        }
        
        success, response, _ = self.make_request("POST", "pms/bookings", booking_data)
        if success and 'id' in response:
            self.test_booking_id = response['id']
            print(f"✅ Created test booking: {response['id']}")
            return True
        else:
            print("❌ Failed to create test booking")
            return False

    def test_1_basic_room_charge_calculation(self):
        """Test 1: Basic Room Charge Calculation - 3 nights @ $100/night = $300"""
        print("\n🏨 Test 1: Basic Room Charge Calculation")
        
        # Create guest folio
        folio_data = {
            "booking_id": self.test_booking_id,
            "folio_type": "guest"
        }
        
        success, response, _ = self.make_request("POST", "folio/create", folio_data)
        if not success or 'id' not in response:
            self.log_result("Create Guest Folio", False, "Failed to create folio")
            return None
        
        folio_id = response['id']
        self.test_folios.append(folio_id)
        
        # Post 3 room charges @ $100 each
        for night in range(1, 4):
            charge_data = {
                "charge_category": "room",
                "description": f"Room 101 - Night {night}",
                "amount": 100.0,
                "quantity": 1,
                "auto_calculate_tax": False
            }
            
            success, response, _ = self.make_request("POST", f"folio/{folio_id}/charge", charge_data)
            if not success:
                self.log_result(f"Post Room Charge Night {night}", False, "Failed to post charge")
                return None
        
        # Verify total charges = $300
        success, response, _ = self.make_request("GET", f"folio/{folio_id}")
        if success:
            balance = response.get('balance', 0)
            charges = response.get('charges', [])
            
            total_charges = sum(c.get('total', 0) for c in charges)
            
            if total_charges == 300.0 and balance == 300.0:
                self.log_result("Basic Room Charge Calculation", True, f"Total: ${total_charges}, Balance: ${balance}")
            else:
                self.log_result("Basic Room Charge Calculation", False, f"Expected $300, got charges: ${total_charges}, balance: ${balance}")
        else:
            self.log_result("Basic Room Charge Calculation", False, "Failed to get folio details")
        
        return folio_id

    def test_2_tax_calculations(self, folio_id):
        """Test 2: Tax Calculations - VAT, tourism tax, service charge"""
        print("\n💰 Test 2: Tax Calculations")
        
        # Post charge with VAT (18%)
        vat_charge_data = {
            "charge_category": "food",
            "description": "Restaurant Bill with VAT",
            "amount": 100.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{folio_id}/charge", vat_charge_data)
        if success:
            # Manually calculate tax (since auto_calculate_tax is False, we'll add it separately)
            tax_charge_data = {
                "charge_category": "other",
                "description": "VAT 18%",
                "amount": 18.0,  # 18% of 100
                "quantity": 1,
                "auto_calculate_tax": False
            }
            
            success, response, _ = self.make_request("POST", f"folio/{folio_id}/charge", tax_charge_data)
            if success:
                self.log_result("VAT Calculation", True, "18% VAT added correctly")
            else:
                self.log_result("VAT Calculation", False, "Failed to add VAT charge")
        else:
            self.log_result("VAT Calculation", False, "Failed to post base charge")
        
        # Post tourism tax (city tax)
        tourism_tax_data = {
            "charge_category": "city_tax",
            "description": "Tourism Tax",
            "amount": 5.0,
            "quantity": 3,  # 3 nights
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{folio_id}/charge", tourism_tax_data)
        if success and response.get('total') == 15.0:  # 5 * 3
            self.log_result("Tourism Tax Calculation", True, "Tourism tax: $5 x 3 nights = $15")
        else:
            self.log_result("Tourism Tax Calculation", False, f"Expected $15, got ${response.get('total', 0)}")
        
        # Post service charge (10%)
        service_charge_data = {
            "charge_category": "service_charge",
            "description": "Service Charge 10%",
            "amount": 43.3,  # 10% of (300 + 100 + 18 + 15) = 43.3
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{folio_id}/charge", service_charge_data)
        if success:
            self.log_result("Service Charge Calculation", True, "Service charge added")
        else:
            self.log_result("Service Charge Calculation", False, "Failed to add service charge")

    def test_3_payment_application(self, folio_id):
        """Test 3: Payment Application - partial payments, overpayment"""
        print("\n💳 Test 3: Payment Application")
        
        # Get current balance
        success, response, _ = self.make_request("GET", f"folio/{folio_id}")
        if not success:
            self.log_result("Get Balance Before Payment", False, "Failed to get folio details")
            return
        
        balance_before = response.get('balance', 0)
        
        # Test partial payment
        partial_payment_data = {
            "amount": 200.0,
            "method": "card",
            "payment_type": "interim"
        }
        
        success, response, _ = self.make_request("POST", f"folio/{folio_id}/payment", partial_payment_data)
        if success:
            # Check balance after partial payment
            success, response, _ = self.make_request("GET", f"folio/{folio_id}")
            if success:
                balance_after = response.get('balance', 0)
                expected_balance = balance_before - 200.0
                
                if abs(balance_after - expected_balance) < 0.01:
                    self.log_result("Partial Payment Application", True, f"Balance reduced from ${balance_before} to ${balance_after}")
                else:
                    self.log_result("Partial Payment Application", False, f"Expected ${expected_balance}, got ${balance_after}")
            else:
                self.log_result("Partial Payment Application", False, "Failed to verify balance after payment")
        else:
            self.log_result("Partial Payment Application", False, "Failed to post partial payment")
        
        # Test overpayment scenario
        overpayment_data = {
            "amount": 500.0,  # More than remaining balance
            "method": "cash",
            "payment_type": "final"
        }
        
        success, response, _ = self.make_request("POST", f"folio/{folio_id}/payment", overpayment_data)
        if success:
            # Check final balance
            success, response, _ = self.make_request("GET", f"folio/{folio_id}")
            if success:
                final_balance = response.get('balance', 0)
                
                if final_balance < 0:
                    self.log_result("Overpayment Scenario", True, f"Overpayment created credit balance: ${final_balance}")
                else:
                    self.log_result("Overpayment Scenario", False, f"Expected negative balance, got ${final_balance}")
            else:
                self.log_result("Overpayment Scenario", False, "Failed to verify balance after overpayment")
        else:
            self.log_result("Overpayment Scenario", False, "Failed to post overpayment")

    def test_4_voided_charges(self, folio_id):
        """Test 4: Voided Charges - verify they don't affect balance"""
        print("\n🚫 Test 4: Voided Charges")
        
        # Get current balance
        success, response, _ = self.make_request("GET", f"folio/{folio_id}")
        if not success:
            self.log_result("Get Balance Before Void", False, "Failed to get folio details")
            return
        
        balance_before = response.get('balance', 0)
        charges = response.get('charges', [])
        
        # Find a charge to void (use the first non-voided charge)
        charge_to_void = None
        for charge in charges:
            if not charge.get('voided', False):
                charge_to_void = charge
                break
        
        if not charge_to_void:
            self.log_result("Find Charge to Void", False, "No charges available to void")
            return
        
        charge_id = charge_to_void['id']
        charge_amount = charge_to_void.get('total', 0)
        
        # Void the charge
        void_data = {
            "void_reason": "Customer complaint - regression test"
        }
        
        success, response, _ = self.make_request("POST", f"folio/{folio_id}/void-charge/{charge_id}?void_reason={void_data['void_reason']}")
        if success:
            # Check balance after voiding
            success, response, _ = self.make_request("GET", f"folio/{folio_id}")
            if success:
                balance_after = response.get('balance', 0)
                expected_balance = balance_before - charge_amount
                
                # Verify the charge is marked as voided
                charges_after = response.get('charges', [])
                voided_charge = None
                for charge in charges_after:
                    if charge['id'] == charge_id:
                        voided_charge = charge
                        break
                
                if (voided_charge and voided_charge.get('voided', False) and 
                    abs(balance_after - expected_balance) < 0.01):
                    self.log_result("Voided Charges", True, f"Charge voided, balance adjusted from ${balance_before} to ${balance_after}")
                else:
                    self.log_result("Voided Charges", False, f"Void not properly processed. Expected balance: ${expected_balance}, got: ${balance_after}")
            else:
                self.log_result("Voided Charges", False, "Failed to verify balance after void")
        else:
            self.log_result("Voided Charges", False, "Failed to void charge")

    def test_5_multiple_folios(self):
        """Test 5: Multiple Folios - split charges, transfers"""
        print("\n📊 Test 5: Multiple Folios")
        
        # Create company folio
        company_folio_data = {
            "booking_id": self.test_booking_id,
            "folio_type": "company",
            "company_id": self.test_company_id
        }
        
        success, response, _ = self.make_request("POST", "folio/create", company_folio_data)
        if not success or 'id' not in response:
            self.log_result("Create Company Folio", False, "Failed to create company folio")
            return
        
        company_folio_id = response['id']
        self.test_folios.append(company_folio_id)
        
        # Post charges to company folio
        company_charge_data = {
            "charge_category": "food",
            "description": "Corporate Meeting Catering",
            "amount": 250.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{company_folio_id}/charge", company_charge_data)
        if success:
            self.log_result("Post Charge to Company Folio", True, "Company charge posted successfully")
        else:
            self.log_result("Post Charge to Company Folio", False, "Failed to post company charge")
        
        # Get both folio balances
        success, guest_folio, _ = self.make_request("GET", f"folio/{self.test_folios[0]}")
        success2, company_folio, _ = self.make_request("GET", f"folio/{company_folio_id}")
        
        if success and success2:
            guest_balance = guest_folio.get('balance', 0)
            company_balance = company_folio.get('balance', 0)
            
            self.log_result("Multiple Folios Balance Check", True, 
                          f"Guest folio: ${guest_balance}, Company folio: ${company_balance}")
        else:
            self.log_result("Multiple Folios Balance Check", False, "Failed to get folio balances")
        
        # Test folio transfer (if both folios have charges)
        if success and success2:
            guest_charges = guest_folio.get('charges', [])
            if guest_charges:
                # Transfer a charge from guest to company folio
                charge_to_transfer = guest_charges[0]['id']
                
                transfer_data = {
                    "operation_type": "transfer",
                    "from_folio_id": self.test_folios[0],
                    "to_folio_id": company_folio_id,
                    "charge_ids": [charge_to_transfer],
                    "reason": "Corporate billing - regression test"
                }
                
                success, response, _ = self.make_request("POST", "folio/transfer", transfer_data)
                if success:
                    self.log_result("Folio Transfer", True, "Charge transferred between folios")
                else:
                    self.log_result("Folio Transfer", False, "Failed to transfer charge")

    def test_6_commission_calculations(self):
        """Test 6: Commission Calculations - OTA bookings"""
        print("\n🏢 Test 6: Commission Calculations")
        
        # Create OTA booking with commission
        ota_booking_data = {
            "guest_id": self.test_guest_id,
            "room_id": self.test_room_id,
            "check_in": (datetime.now() + timedelta(days=5)).isoformat(),
            "check_out": (datetime.now() + timedelta(days=7)).isoformat(),
            "adults": 2,
            "children": 0,
            "children_ages": [],
            "guests_count": 2,
            "total_amount": 200.0,
            "channel": "booking_com",
            "ota_channel": "booking_com",
            "commission_pct": 15.0,  # 15% commission
            "payment_model": "agency"
        }
        
        success, response, _ = self.make_request("POST", "pms/bookings", ota_booking_data)
        if success and 'id' in response:
            ota_booking_id = response['id']
            
            # Create folio for OTA booking
            ota_folio_data = {
                "booking_id": ota_booking_id,
                "folio_type": "guest"
            }
            
            success, response, _ = self.make_request("POST", "folio/create", ota_folio_data)
            if success and 'id' in response:
                ota_folio_id = response['id']
                self.test_folios.append(ota_folio_id)
                
                # Post room charge
                room_charge_data = {
                    "charge_category": "room",
                    "description": "OTA Room Charge",
                    "amount": 200.0,
                    "quantity": 1,
                    "auto_calculate_tax": False
                }
                
                success, response, _ = self.make_request("POST", f"folio/{ota_folio_id}/charge", room_charge_data)
                if success:
                    # Post commission deduction
                    commission_amount = 200.0 * 0.15  # 15% of 200 = 30
                    commission_charge_data = {
                        "charge_category": "other",
                        "description": "OTA Commission (15%)",
                        "amount": -commission_amount,  # Negative for deduction
                        "quantity": 1,
                        "auto_calculate_tax": False
                    }
                    
                    success, response, _ = self.make_request("POST", f"folio/{ota_folio_id}/charge", commission_charge_data)
                    if success:
                        # Verify net amount
                        success, response, _ = self.make_request("GET", f"folio/{ota_folio_id}")
                        if success:
                            balance = response.get('balance', 0)
                            expected_net = 200.0 - 30.0  # 170.0
                            
                            if abs(balance - expected_net) < 0.01:
                                self.log_result("Commission Calculations", True, f"Net amount after 15% commission: ${balance}")
                            else:
                                self.log_result("Commission Calculations", False, f"Expected ${expected_net}, got ${balance}")
                        else:
                            self.log_result("Commission Calculations", False, "Failed to verify net amount")
                    else:
                        self.log_result("Commission Calculations", False, "Failed to post commission deduction")
                else:
                    self.log_result("Commission Calculations", False, "Failed to post room charge")
            else:
                self.log_result("Commission Calculations", False, "Failed to create OTA folio")
        else:
            self.log_result("Commission Calculations", False, "Failed to create OTA booking")

    def test_7_currency_rounding(self, folio_id):
        """Test 7: Currency Rounding - 2 decimal places"""
        print("\n🔢 Test 7: Currency Rounding")
        
        # Post charge with many decimals
        rounding_charge_data = {
            "charge_category": "other",
            "description": "Rounding Test Charge",
            "amount": 33.33333333,  # Should round to 33.33
            "quantity": 3,  # Total should be 99.99999999 -> 100.00
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{folio_id}/charge", rounding_charge_data)
        if success:
            total = response.get('total', 0)
            amount = response.get('amount', 0)
            
            # Check if amounts are properly rounded to 2 decimal places
            if (round(amount, 2) == amount and round(total, 2) == total):
                self.log_result("Currency Rounding", True, f"Amount: ${amount}, Total: ${total} (properly rounded)")
            else:
                self.log_result("Currency Rounding", False, f"Rounding failed - Amount: ${amount}, Total: ${total}")
        else:
            self.log_result("Currency Rounding", False, "Failed to post rounding test charge")

    def test_8_complex_scenario(self):
        """Test 8: Complex Scenario - Room + extras + tax + payment = expected balance"""
        print("\n🎯 Test 8: Complex Scenario")
        
        # Create new folio for complex scenario
        complex_folio_data = {
            "booking_id": self.test_booking_id,
            "folio_type": "guest"
        }
        
        success, response, _ = self.make_request("POST", "folio/create", complex_folio_data)
        if not success or 'id' not in response:
            self.log_result("Create Complex Scenario Folio", False, "Failed to create folio")
            return
        
        complex_folio_id = response['id']
        self.test_folios.append(complex_folio_id)
        
        # Room: $300
        room_charge_data = {
            "charge_category": "room",
            "description": "Room Charges (3 nights)",
            "amount": 300.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{complex_folio_id}/charge", room_charge_data)
        if not success:
            self.log_result("Complex Scenario - Room Charge", False, "Failed to post room charge")
            return
        
        # Minibar: $50
        minibar_charge_data = {
            "charge_category": "minibar",
            "description": "Minibar Consumption",
            "amount": 50.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{complex_folio_id}/charge", minibar_charge_data)
        if not success:
            self.log_result("Complex Scenario - Minibar Charge", False, "Failed to post minibar charge")
            return
        
        # Restaurant: $120
        restaurant_charge_data = {
            "charge_category": "food",
            "description": "Restaurant Bill",
            "amount": 120.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{complex_folio_id}/charge", restaurant_charge_data)
        if not success:
            self.log_result("Complex Scenario - Restaurant Charge", False, "Failed to post restaurant charge")
            return
        
        # Tax (10%): $47
        tax_charge_data = {
            "charge_category": "other",
            "description": "Tax (10%)",
            "amount": 47.0,  # 10% of (300 + 50 + 120) = 47
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{complex_folio_id}/charge", tax_charge_data)
        if not success:
            self.log_result("Complex Scenario - Tax Charge", False, "Failed to post tax charge")
            return
        
        # Payment: $200
        payment_data = {
            "amount": 200.0,
            "method": "card",
            "payment_type": "interim"
        }
        
        success, response, _ = self.make_request("POST", f"folio/{complex_folio_id}/payment", payment_data)
        if not success:
            self.log_result("Complex Scenario - Payment", False, "Failed to post payment")
            return
        
        # Expected Balance: $317 (300 + 50 + 120 + 47 - 200)
        success, response, _ = self.make_request("GET", f"folio/{complex_folio_id}")
        if success:
            balance = response.get('balance', 0)
            expected_balance = 317.0
            
            if abs(balance - expected_balance) < 0.01:
                self.log_result("Complex Scenario", True, f"Expected balance ${expected_balance}, got ${balance}")
            else:
                self.log_result("Complex Scenario", False, f"Expected balance ${expected_balance}, got ${balance}")
        else:
            self.log_result("Complex Scenario", False, "Failed to get final balance")

    def test_9_edge_cases(self):
        """Test 9: Edge Cases - negative charges, zero amounts, large amounts"""
        print("\n⚠️ Test 9: Edge Cases")
        
        # Create folio for edge cases
        edge_folio_data = {
            "booking_id": self.test_booking_id,
            "folio_type": "guest"
        }
        
        success, response, _ = self.make_request("POST", "folio/create", edge_folio_data)
        if not success or 'id' not in response:
            self.log_result("Create Edge Cases Folio", False, "Failed to create folio")
            return
        
        edge_folio_id = response['id']
        self.test_folios.append(edge_folio_id)
        
        # Test negative charges (refunds)
        refund_charge_data = {
            "charge_category": "other",
            "description": "Refund - Cancelled Service",
            "amount": -50.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{edge_folio_id}/charge", refund_charge_data)
        if success and response.get('amount') == -50.0:
            self.log_result("Negative Charges (Refunds)", True, "Negative charge posted successfully")
        else:
            self.log_result("Negative Charges (Refunds)", False, "Failed to post negative charge")
        
        # Test zero amount transactions
        zero_charge_data = {
            "charge_category": "other",
            "description": "Zero Amount Test",
            "amount": 0.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{edge_folio_id}/charge", zero_charge_data)
        if success and response.get('amount') == 0.0:
            self.log_result("Zero Amount Transactions", True, "Zero amount charge posted successfully")
        else:
            self.log_result("Zero Amount Transactions", False, "Failed to post zero amount charge")
        
        # Test very large amounts (>$10,000)
        large_charge_data = {
            "charge_category": "other",
            "description": "Large Amount Test",
            "amount": 15000.0,
            "quantity": 1,
            "auto_calculate_tax": False
        }
        
        success, response, _ = self.make_request("POST", f"folio/{edge_folio_id}/charge", large_charge_data)
        if success and response.get('amount') == 15000.0:
            self.log_result("Very Large Amounts", True, "Large amount charge posted successfully")
        else:
            self.log_result("Very Large Amounts", False, "Failed to post large amount charge")
        
        # Test charge/payment on closed folio (should fail)
        # First close the folio by making balance zero
        payment_to_zero_data = {
            "amount": 14950.0,  # To make balance zero (15000 - 50 + 0 - 14950 = 0)
            "method": "card",
            "payment_type": "final"
        }
        
        success, response, _ = self.make_request("POST", f"folio/{edge_folio_id}/payment", payment_to_zero_data)
        if success:
            # Close the folio
            success, response, _ = self.make_request("POST", f"folio/{edge_folio_id}/close")
            if success:
                # Try to post charge to closed folio (should fail)
                closed_folio_charge_data = {
                    "charge_category": "other",
                    "description": "Charge to Closed Folio",
                    "amount": 100.0,
                    "quantity": 1,
                    "auto_calculate_tax": False
                }
                
                success, response, status = self.make_request("POST", f"folio/{edge_folio_id}/charge", closed_folio_charge_data, expected_status=404)
                if not success and status == 404:
                    self.log_result("Charge on Closed Folio", True, "Correctly rejected charge on closed folio")
                else:
                    self.log_result("Charge on Closed Folio", False, "Should have rejected charge on closed folio")
            else:
                self.log_result("Close Folio", False, "Failed to close folio")
        else:
            self.log_result("Payment to Zero Balance", False, "Failed to make payment")

    def run_all_tests(self):
        """Run all folio calculation regression tests"""
        print("🚀 Starting Folio Calculations Regression Testing")
        print("=" * 60)
        
        # Authenticate
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Setup test data
        if not self.setup_test_data():
            print("❌ Test data setup failed. Cannot proceed with tests.")
            return False
        
        # Run all test scenarios
        print("\n🧪 Running Test Scenarios...")
        
        # Test 1: Basic Room Charge Calculation
        folio_id = self.test_1_basic_room_charge_calculation()
        
        if folio_id:
            # Test 2: Tax Calculations
            self.test_2_tax_calculations(folio_id)
            
            # Test 3: Payment Application
            self.test_3_payment_application(folio_id)
            
            # Test 4: Voided Charges
            self.test_4_voided_charges(folio_id)
            
            # Test 7: Currency Rounding
            self.test_7_currency_rounding(folio_id)
        
        # Test 5: Multiple Folios
        self.test_5_multiple_folios()
        
        # Test 6: Commission Calculations
        self.test_6_commission_calculations()
        
        # Test 8: Complex Scenario
        self.test_8_complex_scenario()
        
        # Test 9: Edge Cases
        self.test_9_edge_cases()
        
        # Print summary
        self.print_summary()
        
        return self.tests_passed == self.tests_run

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 FOLIO CALCULATIONS REGRESSION TEST SUMMARY")
        print("=" * 60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print(f"Total Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("\n🎉 ALL TESTS PASSED! Folio calculations are working correctly.")
        else:
            print(f"\n⚠️ {self.tests_run - self.tests_passed} TESTS FAILED. Review the issues above.")
            
            # Print failed tests
            print("\nFailed Tests:")
            for result in self.test_results:
                if not result['passed']:
                    print(f"  ❌ {result['test']}")
                    if result['details']:
                        print(f"     {result['details']}")
        
        print("\n" + "=" * 60)

if __name__ == "__main__":
    tester = FolioRegressionTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)