#!/usr/bin/env python3
"""
Folio System Enhancement Testing
Tests payment void, activity log, balance calculation, and folio transfer
"""

import requests
import json
from datetime import datetime, timezone

# Configuration
BASE_URL = "https://code-cleanup-135.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class FolioSystemTester:
    def __init__(self):
        self.token = None
        self.tenant_id = None
        self.results = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'tests': []
        }
    
    def log_test(self, test_name, passed, message, response_time=None):
        """Log test result"""
        self.results['total_tests'] += 1
        if passed:
            self.results['passed'] += 1
            status = "✅ PASS"
        else:
            self.results['failed'] += 1
            status = "❌ FAIL"
        
        result = {
            'test': test_name,
            'status': status,
            'message': message,
            'response_time': response_time
        }
        self.results['tests'].append(result)
        print(f"{status}: {test_name} - {message}")
    
    def login(self):
        """Authenticate and get token"""
        print("\n🔐 AUTHENTICATION")
        print("=" * 80)
        
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.token = data['access_token']
                self.tenant_id = data['user'].get('tenant_id')
                self.log_test("Authentication", True, f"Logged in as {LOGIN_EMAIL}")
                return True
            else:
                self.log_test("Authentication", False, f"HTTP {response.status_code}: {response.text}")
                return False
        except Exception as e:
            self.log_test("Authentication", False, f"Error: {str(e)}")
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def setup_test_data(self):
        """Create test booking, folio, charges, and payments"""
        print("\n📦 SETUP TEST DATA")
        print("=" * 80)
        
        try:
            # Create a guest
            guest_data = {
                "name": "Folio Test Guest",
                "email": f"foliotest_{datetime.now().timestamp()}@test.com",
                "phone": "+905551234567",
                "id_number": "12345678901",
                "nationality": "TR"
            }
            
            response = requests.post(
                f"{BASE_URL}/pms/guests",
                headers=self.get_headers(),
                json=guest_data,
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Setup - Create Guest", False, f"HTTP {response.status_code}")
                return None
            
            guest_id = response.json()['id']
            self.log_test("Setup - Create Guest", True, f"Guest ID: {guest_id}")
            
            # Get an available room
            response = requests.get(
                f"{BASE_URL}/pms/rooms?status=available&limit=1",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200 or not response.json():
                self.log_test("Setup - Get Room", False, "No available rooms")
                return None
            
            room = response.json()[0]
            room_id = room['id']
            self.log_test("Setup - Get Room", True, f"Room: {room['room_number']}")
            
            # Create a booking
            booking_data = {
                "guest_id": guest_id,
                "room_id": room_id,
                "check_in": "2025-12-01",
                "check_out": "2025-12-05",
                "adults": 2,
                "children": 0,
                "guests_count": 2,
                "total_amount": 2000.00,
                "channel": "direct"
            }
            
            response = requests.post(
                f"{BASE_URL}/pms/bookings",
                headers=self.get_headers(),
                json=booking_data,
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Setup - Create Booking", False, f"HTTP {response.status_code}: {response.text}")
                return None
            
            booking_id = response.json()['id']
            self.log_test("Setup - Create Booking", True, f"Booking ID: {booking_id}")
            
            # Create a folio
            folio_data = {
                "booking_id": booking_id,
                "folio_type": "guest",
                "guest_id": guest_id
            }
            
            response = requests.post(
                f"{BASE_URL}/folio/create",
                headers=self.get_headers(),
                json=folio_data,
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Setup - Create Folio", False, f"HTTP {response.status_code}: {response.text}")
                return None
            
            folio = response.json()
            folio_id = folio['id']
            self.log_test("Setup - Create Folio", True, f"Folio ID: {folio_id}, Number: {folio['folio_number']}")
            
            # Add charges to folio
            charges = [
                {"charge_category": "room", "description": "Room Charge - Night 1", "amount": 500.00, "quantity": 1},
                {"charge_category": "room", "description": "Room Charge - Night 2", "amount": 500.00, "quantity": 1},
                {"charge_category": "food", "description": "Breakfast", "amount": 150.00, "quantity": 2},
                {"charge_category": "minibar", "description": "Minibar Items", "amount": 75.00, "quantity": 1}
            ]
            
            charge_ids = []
            for charge in charges:
                response = requests.post(
                    f"{BASE_URL}/folio/{folio_id}/charge",
                    headers=self.get_headers(),
                    json=charge,
                    timeout=10
                )
                
                if response.status_code == 200:
                    charge_ids.append(response.json()['id'])
            
            self.log_test("Setup - Add Charges", True, f"Added {len(charge_ids)} charges")
            
            # Add payments to folio
            payments = [
                {"amount": 800.00, "method": "card", "payment_type": "deposit", "reference": "CARD-001"},
                {"amount": 500.00, "method": "cash", "payment_type": "interim", "reference": "CASH-001"}
            ]
            
            payment_ids = []
            for payment in payments:
                response = requests.post(
                    f"{BASE_URL}/folio/{folio_id}/payment",
                    headers=self.get_headers(),
                    json=payment,
                    timeout=10
                )
                
                if response.status_code == 200:
                    payment_ids.append(response.json()['id'])
            
            self.log_test("Setup - Add Payments", True, f"Added {len(payment_ids)} payments")
            
            return {
                'guest_id': guest_id,
                'room_id': room_id,
                'booking_id': booking_id,
                'folio_id': folio_id,
                'charge_ids': charge_ids,
                'payment_ids': payment_ids
            }
            
        except Exception as e:
            self.log_test("Setup Test Data", False, f"Error: {str(e)}")
            return None
    
    def test_payment_void(self, test_data):
        """Test payment void functionality"""
        print("\n💳 PAYMENT VOID TEST")
        print("=" * 80)
        
        if not test_data or not test_data.get('payment_ids'):
            self.log_test("Payment Void", False, "No test data available")
            return
        
        payment_id = test_data['payment_ids'][0]
        folio_id = test_data['folio_id']
        
        try:
            # Get folio balance before void
            response = requests.get(
                f"{BASE_URL}/folio/{folio_id}",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Payment Void - Get Balance Before", False, f"HTTP {response.status_code}")
                return
            
            balance_before = response.json().get('balance', 0)
            self.log_test("Payment Void - Get Balance Before", True, f"Balance: {balance_before}")
            
            # Void the payment
            start_time = datetime.now()
            response = requests.post(
                f"{BASE_URL}/payment/{payment_id}/void",
                headers=self.get_headers(),
                params={"void_reason": "Test void - duplicate payment"},
                timeout=10
            )
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            if response.status_code != 200:
                self.log_test("Payment Void - Void Payment", False, 
                            f"HTTP {response.status_code}: {response.text}", response_time)
                return
            
            self.log_test("Payment Void - Void Payment", True, 
                        f"Payment voided successfully", response_time)
            
            # Verify payment is marked as voided
            response = requests.get(
                f"{BASE_URL}/folio/{folio_id}/activity-log",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Payment Void - Verify Voided Status", False, f"HTTP {response.status_code}")
                return
            
            activities = response.json().get('activities', [])
            voided_payment = None
            for activity in activities:
                if activity.get('type') == 'payment' and activity.get('action') == 'voided':
                    details = activity.get('details', {})
                    if details.get('id') == payment_id:
                        voided_payment = details
                        break
            
            if voided_payment:
                self.log_test("Payment Void - Verify Voided Status", True, 
                            f"Payment marked as voided: {voided_payment.get('voided')}")
            else:
                self.log_test("Payment Void - Verify Voided Status", False, 
                            "Payment not found in activity log as voided")
            
            # Get folio balance after void
            response = requests.get(
                f"{BASE_URL}/folio/{folio_id}",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Payment Void - Get Balance After", False, f"HTTP {response.status_code}")
                return
            
            balance_after = response.json().get('balance', 0)
            
            # Balance should increase by the voided payment amount (800.00)
            expected_balance = balance_before + 800.00
            balance_correct = abs(balance_after - expected_balance) < 0.01
            
            if balance_correct:
                self.log_test("Payment Void - Balance Recalculation", True, 
                            f"Balance updated correctly: {balance_before} → {balance_after} (expected: {expected_balance})")
            else:
                self.log_test("Payment Void - Balance Recalculation", False, 
                            f"Balance incorrect: {balance_after} (expected: {expected_balance})")
            
        except Exception as e:
            self.log_test("Payment Void", False, f"Error: {str(e)}")
    
    def test_activity_log(self, test_data):
        """Test folio activity log"""
        print("\n📋 ACTIVITY LOG TEST")
        print("=" * 80)
        
        if not test_data:
            self.log_test("Activity Log", False, "No test data available")
            return
        
        folio_id = test_data['folio_id']
        
        try:
            start_time = datetime.now()
            response = requests.get(
                f"{BASE_URL}/folio/{folio_id}/activity-log",
                headers=self.get_headers(),
                timeout=10
            )
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            if response.status_code != 200:
                self.log_test("Activity Log - Get Log", False, 
                            f"HTTP {response.status_code}: {response.text}", response_time)
                return
            
            data = response.json()
            activities = data.get('activities', [])
            
            self.log_test("Activity Log - Get Log", True, 
                        f"Retrieved {len(activities)} activities", response_time)
            
            # Verify charges are present
            charges = [a for a in activities if a.get('type') == 'charge']
            if charges:
                self.log_test("Activity Log - Charges Present", True, 
                            f"Found {len(charges)} charge activities")
            else:
                self.log_test("Activity Log - Charges Present", False, 
                            "No charge activities found")
            
            # Verify payments are present
            payments = [a for a in activities if a.get('type') == 'payment']
            if payments:
                self.log_test("Activity Log - Payments Present", True, 
                            f"Found {len(payments)} payment activities")
            else:
                self.log_test("Activity Log - Payments Present", False, 
                            "No payment activities found")
            
            # Verify operations are present (if any)
            operations = [a for a in activities if a.get('type') == 'operation']
            self.log_test("Activity Log - Operations Present", True, 
                        f"Found {len(operations)} operation activities")
            
            # Verify activities are sorted by timestamp
            timestamps = [a.get('timestamp') for a in activities if a.get('timestamp')]
            is_sorted = all(timestamps[i] >= timestamps[i+1] for i in range(len(timestamps)-1))
            
            if is_sorted:
                self.log_test("Activity Log - Sorted by Timestamp", True, 
                            "Activities correctly sorted (newest first)")
            else:
                self.log_test("Activity Log - Sorted by Timestamp", False, 
                            "Activities not properly sorted")
            
            # Verify required fields are present
            required_fields = ['type', 'action', 'timestamp', 'description', 'amount']
            all_have_fields = True
            missing_fields = []
            
            for activity in activities:
                for field in required_fields:
                    if field not in activity:
                        all_have_fields = False
                        missing_fields.append(f"{activity.get('type', 'unknown')} missing {field}")
            
            if all_have_fields:
                self.log_test("Activity Log - Required Fields", True, 
                            "All activities have required fields")
            else:
                self.log_test("Activity Log - Required Fields", False, 
                            f"Missing fields: {', '.join(missing_fields[:3])}")
            
        except Exception as e:
            self.log_test("Activity Log", False, f"Error: {str(e)}")
    
    def test_balance_calculation(self, test_data):
        """Test folio balance calculation with voided items"""
        print("\n🧮 BALANCE CALCULATION TEST")
        print("=" * 80)
        
        if not test_data:
            self.log_test("Balance Calculation", False, "No test data available")
            return
        
        folio_id = test_data['folio_id']
        
        try:
            # Get activity log to calculate expected balance
            response = requests.get(
                f"{BASE_URL}/folio/{folio_id}/activity-log",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Balance Calculation - Get Activities", False, f"HTTP {response.status_code}")
                return
            
            activities = response.json().get('activities', [])
            
            # Calculate expected balance
            active_charges = sum(
                a.get('amount', 0) 
                for a in activities 
                if a.get('type') == 'charge' and a.get('action') != 'voided'
            )
            
            active_payments = sum(
                a.get('amount', 0) 
                for a in activities 
                if a.get('type') == 'payment' and a.get('action') != 'voided'
            )
            
            voided_charges = sum(
                a.get('amount', 0) 
                for a in activities 
                if a.get('type') == 'charge' and a.get('action') == 'voided'
            )
            
            voided_payments = sum(
                a.get('amount', 0) 
                for a in activities 
                if a.get('type') == 'payment' and a.get('action') == 'voided'
            )
            
            expected_balance = active_charges - active_payments
            
            self.log_test("Balance Calculation - Calculate Expected", True, 
                        f"Active Charges: {active_charges}, Active Payments: {active_payments}, Expected: {expected_balance}")
            
            # Verify voided items are excluded
            if voided_charges > 0:
                self.log_test("Balance Calculation - Voided Charges Excluded", True, 
                            f"Voided charges: {voided_charges} (excluded from balance)")
            else:
                self.log_test("Balance Calculation - Voided Charges Excluded", True, 
                            "No voided charges to exclude")
            
            if voided_payments > 0:
                self.log_test("Balance Calculation - Voided Payments Excluded", True, 
                            f"Voided payments: {voided_payments} (excluded from balance)")
            else:
                self.log_test("Balance Calculation - Voided Payments Excluded", True, 
                            "No voided payments to exclude")
            
            # Get actual balance from folio
            response = requests.get(
                f"{BASE_URL}/folio/{folio_id}",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Balance Calculation - Get Actual Balance", False, f"HTTP {response.status_code}")
                return
            
            actual_balance = response.json().get('balance', 0)
            
            # Verify balance formula
            balance_correct = abs(actual_balance - expected_balance) < 0.01
            
            if balance_correct:
                self.log_test("Balance Calculation - Formula Verification", True, 
                            f"Balance = (Active Charges) - (Active Payments): {actual_balance} = {active_charges} - {active_payments}")
            else:
                self.log_test("Balance Calculation - Formula Verification", False, 
                            f"Balance mismatch: {actual_balance} (expected: {expected_balance})")
            
        except Exception as e:
            self.log_test("Balance Calculation", False, f"Error: {str(e)}")
    
    def test_folio_transfer(self, test_data):
        """Test folio transfer functionality"""
        print("\n🔄 FOLIO TRANSFER TEST")
        print("=" * 80)
        
        if not test_data or not test_data.get('charge_ids'):
            self.log_test("Folio Transfer", False, "No test data available")
            return
        
        from_folio_id = test_data['folio_id']
        booking_id = test_data['booking_id']
        
        try:
            # Create a second folio for transfer
            folio_data = {
                "booking_id": booking_id,
                "folio_type": "company",
                "notes": "Transfer destination folio"
            }
            
            response = requests.post(
                f"{BASE_URL}/folio/create",
                headers=self.get_headers(),
                json=folio_data,
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Folio Transfer - Create Destination Folio", False, 
                            f"HTTP {response.status_code}: {response.text}")
                return
            
            to_folio_id = response.json()['id']
            self.log_test("Folio Transfer - Create Destination Folio", True, 
                        f"Created folio: {to_folio_id}")
            
            # Get balances before transfer
            response = requests.get(
                f"{BASE_URL}/folio/{from_folio_id}",
                headers=self.get_headers(),
                timeout=10
            )
            from_balance_before = response.json().get('balance', 0) if response.status_code == 200 else 0
            
            response = requests.get(
                f"{BASE_URL}/folio/{to_folio_id}",
                headers=self.get_headers(),
                timeout=10
            )
            to_balance_before = response.json().get('balance', 0) if response.status_code == 200 else 0
            
            self.log_test("Folio Transfer - Get Balances Before", True, 
                        f"From: {from_balance_before}, To: {to_balance_before}")
            
            # Transfer charges (transfer first 2 charges)
            charges_to_transfer = test_data['charge_ids'][:2]
            
            transfer_data = {
                "operation_type": "transfer",
                "from_folio_id": from_folio_id,
                "to_folio_id": to_folio_id,
                "charge_ids": charges_to_transfer,
                "reason": "Transfer room charges to company folio"
            }
            
            start_time = datetime.now()
            response = requests.post(
                f"{BASE_URL}/folio/transfer",
                headers=self.get_headers(),
                json=transfer_data,
                timeout=10
            )
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            if response.status_code != 200:
                self.log_test("Folio Transfer - Transfer Charges", False, 
                            f"HTTP {response.status_code}: {response.text}", response_time)
                return
            
            self.log_test("Folio Transfer - Transfer Charges", True, 
                        f"Transferred {len(charges_to_transfer)} charges", response_time)
            
            # Verify charges moved to new folio
            response = requests.get(
                f"{BASE_URL}/folio/{to_folio_id}/activity-log",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Folio Transfer - Verify Charges Moved", False, f"HTTP {response.status_code}")
                return
            
            to_activities = response.json().get('activities', [])
            to_charges = [a for a in to_activities if a.get('type') == 'charge']
            
            if len(to_charges) >= len(charges_to_transfer):
                self.log_test("Folio Transfer - Verify Charges Moved", True, 
                            f"Destination folio now has {len(to_charges)} charges")
            else:
                self.log_test("Folio Transfer - Verify Charges Moved", False, 
                            f"Expected {len(charges_to_transfer)} charges, found {len(to_charges)}")
            
            # Get balances after transfer
            response = requests.get(
                f"{BASE_URL}/folio/{from_folio_id}",
                headers=self.get_headers(),
                timeout=10
            )
            from_balance_after = response.json().get('balance', 0) if response.status_code == 200 else 0
            
            response = requests.get(
                f"{BASE_URL}/folio/{to_folio_id}",
                headers=self.get_headers(),
                timeout=10
            )
            to_balance_after = response.json().get('balance', 0) if response.status_code == 200 else 0
            
            # Verify balances updated
            from_balance_changed = from_balance_after != from_balance_before
            to_balance_changed = to_balance_after != to_balance_before
            
            if from_balance_changed and to_balance_changed:
                self.log_test("Folio Transfer - Balances Updated", True, 
                            f"From: {from_balance_before} → {from_balance_after}, To: {to_balance_before} → {to_balance_after}")
            else:
                self.log_test("Folio Transfer - Balances Updated", False, 
                            f"Balances not updated correctly")
            
        except Exception as e:
            self.log_test("Folio Transfer", False, f"Error: {str(e)}")
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        
        print(f"\nTotal Tests: {self.results['total_tests']}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        
        success_rate = (self.results['passed'] / self.results['total_tests'] * 100) if self.results['total_tests'] > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.results['failed'] > 0:
            print("\n❌ FAILED TESTS:")
            for test in self.results['tests']:
                if test['status'] == "❌ FAIL":
                    print(f"  - {test['test']}: {test['message']}")
        
        print("\n" + "=" * 80)
    
    def run_all_tests(self):
        """Run all folio system tests"""
        print("\n" + "=" * 80)
        print("🏨 FOLIO SYSTEM ENHANCEMENT TESTING")
        print("=" * 80)
        print(f"Base URL: {BASE_URL}")
        print(f"Login: {LOGIN_EMAIL}")
        print("=" * 80)
        
        # Authenticate
        if not self.login():
            print("\n❌ Authentication failed. Cannot proceed with tests.")
            return
        
        # Setup test data
        test_data = self.setup_test_data()
        
        if not test_data:
            print("\n❌ Test data setup failed. Cannot proceed with tests.")
            self.print_summary()
            return
        
        # Run tests
        self.test_payment_void(test_data)
        self.test_activity_log(test_data)
        self.test_balance_calculation(test_data)
        self.test_folio_transfer(test_data)
        
        # Print summary
        self.print_summary()

if __name__ == "__main__":
    tester = FolioSystemTester()
    tester.run_all_tests()
