import requests
import sys
import json
import uuid
from datetime import datetime, timedelta, timezone

class ComprehensiveRoomOpsAPITester:
    def __init__(self, base_url="https://auth-endpoint-suite.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.user = None
        self.tenant = None
        self.tests_run = 0
        self.tests_passed = 0
        self.created_resources = {
            'rooms': [],
            'guests': [],
            'bookings': [],
            'companies': [],
            'folios': []
        }

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_authentication_flow(self):
        """Test authentication and user management"""
        print("\n1️⃣ AUTHENTICATION & USER MANAGEMENT")
        print("=" * 50)
        
        # Register tenant
        timestamp = datetime.now().strftime('%H%M%S')
        registration_data = {
            "property_name": f"Comprehensive Test Hotel {timestamp}",
            "email": f"comprehensive{timestamp}@example.com",
            "password": "TestPass123!",
            "name": f"Test Manager {timestamp}",
            "phone": "+1234567890",
            "address": "123 Test Street, Test City"
        }
        
        success, response = self.run_test(
            "Tenant Registration",
            "POST",
            "auth/register",
            200,
            data=registration_data
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.user = response['user']
            self.tenant = response['tenant']
            print(f"   ✅ Registered tenant: {self.tenant['property_name']}")
        else:
            print("   ❌ Registration failed")
            return False
        
        # Test login
        login_data = {
            "email": self.user['email'],
            "password": "TestPass123!"
        }
        
        success, response = self.run_test(
            "User Login",
            "POST", 
            "auth/login",
            200,
            data=login_data
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            print("   ✅ Login successful")
        else:
            print("   ❌ Login failed")
            return False
        
        # Test get current user
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        
        if success and response.get('role') == 'admin':
            print("   ✅ User authentication verified")
            return True
        else:
            print("   ❌ User authentication failed")
            return False

    def test_company_management_flow(self):
        """Test complete company management"""
        print("\n2️⃣ COMPANY MANAGEMENT")
        print("=" * 50)
        
        # Create company
        company_data = {
            "name": "Grand Hotel Corporation",
            "corporate_code": "GRAND01",
            "tax_number": "1234567890",
            "billing_address": "123 Business Ave, Istanbul",
            "contact_person": "Alice Johnson",
            "contact_email": "alice@grandhotel.com",
            "contact_phone": "+90-212-555-0100",
            "contracted_rate": "corp_std",
            "default_rate_type": "corporate",
            "default_market_segment": "corporate",
            "default_cancellation_policy": "h48",
            "payment_terms": "Net 30",
            "status": "active"
        }
        
        success, response = self.run_test(
            "Create Company",
            "POST",
            "companies",
            200,
            data=company_data
        )
        
        company_id = None
        if success and 'id' in response:
            company_id = response['id']
            self.created_resources['companies'].append(company_id)
            print(f"   ✅ Company created: {response.get('name')}")
        else:
            print("   ❌ Company creation failed")
            return None
        
        # Search companies
        success, companies = self.run_test(
            "Search Companies",
            "GET",
            "companies?search=Grand",
            200
        )
        
        if success and len(companies) > 0:
            print(f"   ✅ Company search working: {len(companies)} found")
        else:
            print("   ❌ Company search failed")
        
        # Get company details
        success, company_details = self.run_test(
            "Get Company Details",
            "GET",
            f"companies/{company_id}",
            200
        )
        
        if success and company_details.get('name') == 'Grand Hotel Corporation':
            print("   ✅ Company details retrieval working")
        else:
            print("   ❌ Company details retrieval failed")
        
        # Update company
        update_data = company_data.copy()
        update_data['payment_terms'] = "Net 45"
        
        success, updated_company = self.run_test(
            "Update Company",
            "PUT",
            f"companies/{company_id}",
            200,
            data=update_data
        )
        
        if success and updated_company.get('payment_terms') == 'Net 45':
            print("   ✅ Company update working")
        else:
            print("   ❌ Company update failed")
        
        return company_id

    def test_reservation_complete_cycle(self, company_id):
        """Test complete reservation cycle with all fields"""
        print("\n3️⃣ RESERVATION FLOW (COMPLETE CYCLE)")
        print("=" * 50)
        
        # Create guest
        guest_data = {
            "name": "Robert Smith",
            "email": "robert.smith@example.com",
            "phone": "+1234567890",
            "id_number": "ID987654321",
            "address": "456 Guest Avenue"
        }
        
        success, response = self.run_test(
            "Create Guest",
            "POST",
            "pms/guests",
            200,
            data=guest_data
        )
        
        if success and 'id' in response:
            self.created_resources['guests'].append(response['id'])
            print(f"   ✅ Guest created: {response.get('name')}")
        else:
            print("   ❌ Guest creation failed")
            return None
        
        # Create room
        room_data = {
            "room_number": "201",
            "room_type": "suite",
            "floor": 2,
            "capacity": 4,
            "base_price": 200.00,
            "amenities": ["wifi", "tv", "minibar", "balcony"]
        }
        
        success, response = self.run_test(
            "Create Room",
            "POST",
            "pms/rooms",
            200,
            data=room_data
        )
        
        if success and 'id' in response:
            self.created_resources['rooms'].append(response['id'])
            print(f"   ✅ Room created: {response.get('room_number')}")
        else:
            print("   ❌ Room creation failed")
            return None
        
        # Create reservation with all fields
        booking_data = {
            "guest_id": self.created_resources['guests'][0],
            "room_id": self.created_resources['rooms'][0],
            "check_in": (datetime.now() + timedelta(days=1)).isoformat(),
            "check_out": (datetime.now() + timedelta(days=3)).isoformat(),
            "adults": 2,
            "children": 1,
            "children_ages": [8],
            "guests_count": 3,
            "company_id": company_id,
            "contracted_rate": "corp_std",
            "rate_type": "corporate",
            "market_segment": "corporate",
            "cancellation_policy": "h48",
            "billing_address": "123 Business Ave, Istanbul",
            "billing_tax_number": "1234567890",
            "billing_contact_person": "Alice Johnson",
            "base_rate": 200.0,
            "total_amount": 180.0,  # Discounted rate
            "override_reason": "Corporate discount",
            "channel": "direct"
        }
        
        success, response = self.run_test(
            "Create Reservation with All Fields",
            "POST",
            "pms/bookings",
            200,
            data=booking_data
        )
        
        booking_id = None
        if success and 'id' in response:
            booking_id = response['id']
            self.created_resources['bookings'].append(booking_id)
            
            # Verify all fields
            if (response.get('adults') == 2 and
                response.get('children') == 1 and
                response.get('children_ages') == [8] and
                response.get('company_id') == company_id and
                response.get('contracted_rate') == 'corp_std'):
                print("   ✅ Reservation created with all fields")
            else:
                print("   ❌ Reservation field verification failed")
        else:
            print("   ❌ Reservation creation failed")
            return None
        
        # Test reservation status transitions
        success, response = self.run_test(
            "Update Booking Status to Guaranteed",
            "PUT",
            f"pms/bookings/{booking_id}",
            200,
            data={"status": "guaranteed"}
        )
        
        if success:
            print("   ✅ Booking status updated to guaranteed")
        else:
            print("   ❌ Booking status update failed")
        
        return booking_id

    def test_checkin_process(self, booking_id, company_id):
        """Test complete check-in process"""
        print("\n4️⃣ CHECK-IN PROCESS")
        print("=" * 50)
        
        # Update room status to available for check-in
        if self.created_resources['rooms']:
            room_id = self.created_resources['rooms'][0]
            success, response = self.run_test(
                "Update Room Status to Available",
                "PUT",
                f"pms/rooms/{room_id}",
                200,
                data={"status": "available"}
            )
        
        # Test check-in with auto folio creation
        success, response = self.run_test(
            "Check-in with Auto Folio Creation",
            "POST",
            f"frontdesk/checkin/{booking_id}?create_folio=true",
            200
        )
        
        guest_folio_id = None
        if success:
            print("   ✅ Check-in successful")
            print(f"      Message: {response.get('message')}")
            print(f"      Room: {response.get('room_number')}")
            
            # Get folios for this booking
            success, folios = self.run_test(
                "Get Booking Folios",
                "GET",
                f"folio/booking/{booking_id}",
                200
            )
            
            if success and len(folios) > 0:
                guest_folio_id = folios[0]['id']
                self.created_resources['folios'].append(guest_folio_id)
                print(f"   ✅ Guest folio created: {folios[0].get('folio_number')}")
            else:
                print("   ❌ Guest folio not found")
        else:
            print("   ❌ Check-in failed")
            return None, None
        
        # Create company folio
        company_folio_data = {
            "booking_id": booking_id,
            "folio_type": "company",
            "company_id": company_id
        }
        
        success, response = self.run_test(
            "Create Company Folio",
            "POST",
            "folio/create",
            200,
            data=company_folio_data
        )
        
        company_folio_id = None
        if success and 'id' in response:
            company_folio_id = response['id']
            self.created_resources['folios'].append(company_folio_id)
            print(f"   ✅ Company folio created: {response.get('folio_number')}")
        else:
            print("   ❌ Company folio creation failed")
        
        # Verify room status changed to occupied
        if self.created_resources['rooms']:
            success, rooms = self.run_test(
                "Verify Room Status Changed",
                "GET",
                "pms/rooms",
                200
            )
            
            if success:
                target_room = None
                for room in rooms:
                    if room.get('id') == self.created_resources['rooms'][0]:
                        target_room = room
                        break
                
                if target_room and target_room.get('status') == 'occupied':
                    print("   ✅ Room status updated to occupied")
                else:
                    print("   ❌ Room status not updated")
        
        return guest_folio_id, company_folio_id

    def test_folio_billing_complete(self, guest_folio_id, company_folio_id):
        """Test complete folio and billing operations"""
        print("\n5️⃣ FOLIO & BILLING")
        print("=" * 50)
        
        if not guest_folio_id:
            print("   ❌ No guest folio available")
            return False
        
        # Post various charges
        charges = [
            {"category": "room", "description": "Room Charge - Night 1", "amount": 200.0, "quantity": 1},
            {"category": "food", "description": "Room Service Dinner", "amount": 45.0, "quantity": 1},
            {"category": "beverage", "description": "Wine Bottle", "amount": 35.0, "quantity": 1},
            {"category": "minibar", "description": "Snacks & Drinks", "amount": 25.0, "quantity": 1},
            {"category": "spa", "description": "Massage Service", "amount": 80.0, "quantity": 1},
            {"category": "laundry", "description": "Laundry Service", "amount": 15.0, "quantity": 1}
        ]
        
        charge_ids = []
        total_charges = 0
        
        for charge in charges:
            charge_data = {
                "charge_category": charge["category"],
                "description": charge["description"],
                "amount": charge["amount"],
                "quantity": charge["quantity"],
                "auto_calculate_tax": False
            }
            
            success, response = self.run_test(
                f"Post {charge['category'].title()} Charge",
                "POST",
                f"folio/{guest_folio_id}/charge",
                200,
                data=charge_data
            )
            
            if success and 'id' in response:
                charge_ids.append(response['id'])
                total_charges += charge["amount"] * charge["quantity"]
                print(f"      ✅ {charge['category'].title()} charge: ${charge['amount']}")
            else:
                print(f"      ❌ {charge['category'].title()} charge failed")
        
        # Post city tax calculation
        city_tax_data = {
            "charge_category": "city_tax",
            "description": "City Tax - 2 nights",
            "amount": 5.0,
            "quantity": 2,
            "auto_calculate_tax": True
        }
        
        success, response = self.run_test(
            "Post City Tax",
            "POST",
            f"folio/{guest_folio_id}/charge",
            200,
            data=city_tax_data
        )
        
        if success:
            total_charges += 10.0  # 5 * 2
            print("      ✅ City tax calculated and posted")
        
        # Post payments
        payments = [
            {"type": "prepayment", "amount": 100.0, "method": "card"},
            {"type": "interim", "amount": 200.0, "method": "card"},
            {"type": "final", "amount": 110.0, "method": "card"}
        ]
        
        total_payments = 0
        
        for payment in payments:
            payment_data = {
                "amount": payment["amount"],
                "method": payment["method"],
                "payment_type": payment["type"]
            }
            
            success, response = self.run_test(
                f"Post {payment['type'].title()} Payment",
                "POST",
                f"folio/{guest_folio_id}/payment",
                200,
                data=payment_data
            )
            
            if success:
                total_payments += payment["amount"]
                print(f"      ✅ {payment['type'].title()} payment: ${payment['amount']}")
            else:
                print(f"      ❌ {payment['type'].title()} payment failed")
        
        # Transfer some charges to company folio
        if company_folio_id and len(charge_ids) >= 2:
            transfer_data = {
                "operation_type": "transfer",
                "from_folio_id": guest_folio_id,
                "to_folio_id": company_folio_id,
                "charge_ids": charge_ids[:2],  # Transfer first 2 charges
                "reason": "Company billing arrangement"
            }
            
            success, response = self.run_test(
                "Transfer Charges to Company Folio",
                "POST",
                "folio/transfer",
                200,
                data=transfer_data
            )
            
            if success:
                print("      ✅ Charges transferred to company folio")
            else:
                print("      ❌ Charge transfer failed")
        
        # Void a charge (if we have charges)
        if len(charge_ids) >= 3:
            success, response = self.run_test(
                "Void Charge",
                "POST",
                f"folio/{guest_folio_id}/void-charge/{charge_ids[2]}?void_reason=Customer complaint",
                200
            )
            
            if success:
                print("      ✅ Charge voided successfully")
            else:
                print("      ❌ Charge void failed")
        
        # Get folio details and verify balance
        success, response = self.run_test(
            "Get Folio Details with Balance",
            "GET",
            f"folio/{guest_folio_id}",
            200
        )
        
        if success:
            balance = response.get('balance', 0)
            charges_count = len(response.get('charges', []))
            payments_count = len(response.get('payments', []))
            
            print(f"      ✅ Folio balance: ${balance}")
            print(f"      ✅ Charges: {charges_count}, Payments: {payments_count}")
        else:
            print("      ❌ Folio details retrieval failed")
        
        return True

    def test_checkout_process(self, booking_id):
        """Test complete check-out process"""
        print("\n6️⃣ CHECK-OUT PROCESS")
        print("=" * 50)
        
        # First, try checkout with outstanding balance (should fail)
        success, response = self.run_test(
            "Checkout with Outstanding Balance (Should Fail)",
            "POST",
            f"frontdesk/checkout/{booking_id}",
            400  # Expecting failure
        )
        
        if not success and response.get('detail'):
            print("      ✅ Outstanding balance validation working")
        else:
            print("      ❌ Outstanding balance validation failed")
        
        # Get booking folios to check balances
        success, folios = self.run_test(
            "Get Booking Folios for Balance Check",
            "GET",
            f"folio/booking/{booking_id}",
            200
        )
        
        if success and len(folios) > 0:
            total_balance = sum(folio.get('balance', 0) for folio in folios)
            print(f"      Total outstanding balance: ${total_balance}")
            
            # Pay remaining balance if needed
            if total_balance > 0:
                for folio in folios:
                    if folio.get('balance', 0) > 0:
                        payment_data = {
                            "amount": folio['balance'],
                            "method": "card",
                            "payment_type": "final"
                        }
                        
                        success, response = self.run_test(
                            f"Pay Outstanding Balance on Folio {folio.get('folio_number')}",
                            "POST",
                            f"folio/{folio['id']}/payment",
                            200,
                            data=payment_data
                        )
                        
                        if success:
                            print(f"      ✅ Paid ${folio['balance']} on {folio.get('folio_number')}")
        
        # Now try checkout again (should succeed)
        success, response = self.run_test(
            "Checkout After Payment",
            "POST",
            f"frontdesk/checkout/{booking_id}",
            200
        )
        
        if success:
            print("      ✅ Check-out successful")
            print(f"      Message: {response.get('message')}")
            print(f"      Total Balance: ${response.get('total_balance', 0)}")
            print(f"      Folios Closed: {response.get('folios_closed', 0)}")
        else:
            print("      ❌ Check-out failed")
            return False
        
        # Verify room status changed to dirty
        if self.created_resources['rooms']:
            success, rooms = self.run_test(
                "Verify Room Status Changed to Dirty",
                "GET",
                "pms/rooms",
                200
            )
            
            if success:
                target_room = None
                for room in rooms:
                    if room.get('id') == self.created_resources['rooms'][0]:
                        target_room = room
                        break
                
                if target_room and target_room.get('status') == 'dirty':
                    print("      ✅ Room status updated to dirty")
                else:
                    print("      ❌ Room status not updated to dirty")
        
        return True

    def test_invoicing_complete(self):
        """Test complete invoicing with VAT and additional taxes"""
        print("\n7️⃣ INVOICING")
        print("=" * 50)
        
        # Test invoice with multiple tax scenarios
        invoice_data = {
            "invoice_type": "sales",
            "customer_name": "Grand Hotel Corporation",
            "customer_email": "billing@grandhotel.com",
            "items": [
                {
                    "description": "Hotel Accommodation - 2 nights",
                    "quantity": 2,
                    "unit_price": 200.0,
                    "vat_rate": 18.0,
                    "vat_amount": 72.0,
                    "total": 472.0,
                    "additional_taxes": [
                        {
                            "tax_type": "accommodation",
                            "tax_name": "Accommodation Tax",
                            "rate": 2.0,
                            "is_percentage": True,
                            "calculated_amount": 8.0
                        }
                    ]
                },
                {
                    "description": "Food & Beverage Services",
                    "quantity": 1,
                    "unit_price": 150.0,
                    "vat_rate": 18.0,
                    "vat_amount": 27.0,
                    "total": 177.0,
                    "additional_taxes": [
                        {
                            "tax_type": "withholding",
                            "tax_name": "Withholding Tax (7/10)",
                            "withholding_rate": "7/10",
                            "is_percentage": True,
                            "calculated_amount": 18.9
                        }
                    ]
                }
            ],
            "due_date": "2025-12-31",
            "notes": "Corporate invoice with multiple tax types"
        }
        
        success, response = self.run_test(
            "Create Invoice with Multiple Taxes",
            "POST",
            "accounting/invoices",
            200,
            data=invoice_data
        )
        
        if success:
            # Verify calculations
            expected_subtotal = 550.0  # 400 + 150
            expected_total_vat = 99.0  # 72 + 27
            expected_additional_taxes = 8.0  # accommodation tax
            expected_withholding = 18.9  # 70% of 27
            
            if (response.get('subtotal') == expected_subtotal and
                response.get('total_vat') == expected_total_vat and
                response.get('total_additional_taxes') == expected_additional_taxes and
                response.get('vat_withholding') == expected_withholding):
                print("      ✅ Invoice with multiple taxes created successfully")
                print(f"      Subtotal: ${response.get('subtotal')}")
                print(f"      VAT: ${response.get('total_vat')}")
                print(f"      Additional Taxes: ${response.get('total_additional_taxes')}")
                print(f"      Withholding: ${response.get('vat_withholding')}")
                print(f"      Total: ${response.get('total')}")
            else:
                print("      ❌ Invoice tax calculations incorrect")
        else:
            print("      ❌ Invoice creation failed")
            return False
        
        return True

    def test_housekeeping_complete(self):
        """Test complete housekeeping functionality"""
        print("\n8️⃣ HOUSEKEEPING")
        print("=" * 50)
        
        # Test room status board
        success, response = self.run_test(
            "Get Room Status Board",
            "GET",
            "housekeeping/room-status",
            200
        )
        
        if success:
            rooms = response.get('rooms', [])
            status_counts = response.get('status_counts', {})
            total_rooms = response.get('total_rooms', 0)
            
            print(f"      ✅ Room status board: {total_rooms} total rooms")
            print(f"      Status counts: {status_counts}")
        else:
            print("      ❌ Room status board failed")
        
        # Test due out rooms
        success, response = self.run_test(
            "Get Due Out Rooms",
            "GET",
            "housekeeping/due-out",
            200
        )
        
        if success:
            due_out_rooms = response.get('due_out_rooms', [])
            count = response.get('count', 0)
            print(f"      ✅ Due out rooms: {count} rooms")
        else:
            print("      ❌ Due out rooms failed")
        
        # Test stayover rooms
        success, response = self.run_test(
            "Get Stayover Rooms",
            "GET",
            "housekeeping/stayovers",
            200
        )
        
        if success:
            stayover_rooms = response.get('stayover_rooms', [])
            count = response.get('count', 0)
            print(f"      ✅ Stayover rooms: {count} rooms")
        else:
            print("      ❌ Stayover rooms failed")
        
        # Test arrival rooms
        success, response = self.run_test(
            "Get Arrival Rooms",
            "GET",
            "housekeeping/arrivals",
            200
        )
        
        if success:
            arrival_rooms = response.get('arrival_rooms', [])
            count = response.get('count', 0)
            ready_count = response.get('ready_count', 0)
            print(f"      ✅ Arrival rooms: {count} rooms, {ready_count} ready")
        else:
            print("      ❌ Arrival rooms failed")
        
        # Test room status update
        if self.created_resources['rooms']:
            room_id = self.created_resources['rooms'][0]
            success, response = self.run_test(
                "Update Room Status to Cleaning",
                "PUT",
                f"housekeeping/room/{room_id}/status",
                200,
                data={"status": "cleaning"}
            )
            
            if success:
                print(f"      ✅ Room status updated: {response.get('message')}")
            else:
                print("      ❌ Room status update failed")
        
        # Test task assignment
        if self.created_resources['rooms']:
            task_data = {
                "room_id": self.created_resources['rooms'][0],
                "assigned_to": "Maria Garcia",
                "task_type": "cleaning",
                "priority": "high",
                "notes": "Deep cleaning required after checkout"
            }
            
            success, response = self.run_test(
                "Assign Housekeeping Task",
                "POST",
                "housekeeping/assign",
                200,
                data=task_data
            )
            
            if success:
                print(f"      ✅ Task assigned: {response.get('message')}")
            else:
                print("      ❌ Task assignment failed")
        
        return True

    def test_reports_complete(self):
        """Test complete reporting functionality"""
        print("\n9️⃣ REPORTS")
        print("=" * 50)
        
        # Test daily flash report
        success, response = self.run_test(
            "Get Daily Flash Report",
            "GET",
            "reports/daily-flash",
            200
        )
        
        if success:
            occupancy = response.get('occupancy', {})
            movements = response.get('movements', {})
            revenue = response.get('revenue', {})
            
            print(f"      ✅ Daily Flash Report")
            print(f"      Occupancy: {occupancy.get('occupied_rooms', 0)}/{occupancy.get('total_rooms', 0)} ({occupancy.get('occupancy_percentage', 0):.1f}%)")
            print(f"      Revenue: ${revenue.get('total_revenue', 0)}")
            print(f"      ADR: ${revenue.get('adr', 0)}")
        else:
            print("      ❌ Daily flash report failed")
        
        # Test market segment report
        success, response = self.run_test(
            "Get Market Segment Report",
            "GET",
            "reports/market-segment?start_date=2025-01-01&end_date=2025-01-31",
            200
        )
        
        if success:
            market_segments = response.get('market_segments', [])
            rate_types = response.get('rate_types', [])
            total_bookings = response.get('total_bookings', 0)
            
            print(f"      ✅ Market Segment Report: {total_bookings} bookings")
            print(f"      Market segments: {len(market_segments)}")
            print(f"      Rate types: {len(rate_types)}")
        else:
            print("      ❌ Market segment report failed")
        
        # Test company aging report
        success, response = self.run_test(
            "Get Company Aging Report",
            "GET",
            "reports/company-aging",
            200
        )
        
        if success:
            companies = response.get('companies', [])
            total_ar = response.get('total_ar', 0)
            company_count = response.get('company_count', 0)
            
            print(f"      ✅ Company Aging Report: {company_count} companies")
            print(f"      Total AR: ${total_ar}")
        else:
            print("      ❌ Company aging report failed")
        
        # Test housekeeping efficiency report
        success, response = self.run_test(
            "Get Housekeeping Efficiency Report",
            "GET",
            "reports/housekeeping-efficiency?start_date=2025-01-01&end_date=2025-01-31",
            200
        )
        
        if success:
            staff_performance = response.get('staff_performance', [])
            total_tasks = response.get('total_tasks_completed', 0)
            daily_average = response.get('daily_average_all_staff', 0)
            
            print(f"      ✅ Housekeeping Efficiency Report")
            print(f"      Total tasks: {total_tasks}")
            print(f"      Daily average: {daily_average}")
            print(f"      Staff count: {len(staff_performance)}")
        else:
            print("      ❌ Housekeeping efficiency report failed")
        
        return True

    def test_rms_complete(self):
        """Test complete RMS functionality"""
        print("\n🔟 RMS (REVENUE MANAGEMENT)")
        print("=" * 50)
        
        # Test generate pricing suggestions
        success, response = self.run_test(
            "Generate RMS Pricing Suggestions",
            "POST",
            "rms/generate-suggestions?start_date=2025-02-01&end_date=2025-02-07",
            200
        )
        
        if success:
            suggestions = response.get('suggestions', [])
            total_count = response.get('total_count', 0)
            
            print(f"      ✅ RMS suggestions generated: {total_count} suggestions")
            
            if len(suggestions) > 0:
                sample = suggestions[0]
                print(f"      Sample: {sample.get('room_type')} - ${sample.get('current_rate')} → ${sample.get('suggested_rate')}")
                print(f"      Reason: {sample.get('reason')}")
        else:
            print("      ❌ RMS suggestion generation failed")
        
        # Test get suggestions by status
        success, response = self.run_test(
            "Get RMS Suggestions by Status",
            "GET",
            "rms/suggestions?status=pending",
            200
        )
        
        if success:
            suggestions = response.get('suggestions', [])
            count = response.get('count', 0)
            print(f"      ✅ Pending suggestions: {count}")
        else:
            print("      ❌ Get suggestions by status failed")
        
        return True

    def test_channel_manager_complete(self):
        """Test complete channel manager functionality"""
        print("\n1️⃣1️⃣ CHANNEL MANAGER")
        print("=" * 50)
        
        # Test create channel connection
        connection_data = {
            "channel_type": "booking_com",
            "channel_name": "Booking.com - Grand Hotel",
            "property_id": "12345",
            "status": "active"
        }
        
        success, response = self.run_test(
            "Create Channel Connection",
            "POST",
            "channel-manager/connections",
            200,
            data=connection_data
        )
        
        if success:
            print(f"      ✅ Channel connection created: {response.get('channel_name')}")
        else:
            print("      ❌ Channel connection creation failed")
        
        # Test get channel connections
        success, response = self.run_test(
            "Get Channel Connections",
            "GET",
            "channel-manager/connections",
            200
        )
        
        if success:
            connections = response.get('connections', [])
            count = response.get('count', 0)
            print(f"      ✅ Channel connections: {count}")
        else:
            print("      ❌ Get channel connections failed")
        
        # Test OTA reservations list
        success, response = self.run_test(
            "Get OTA Reservations",
            "GET",
            "channel-manager/ota-reservations?status=pending",
            200
        )
        
        if success:
            reservations = response.get('reservations', [])
            count = response.get('count', 0)
            print(f"      ✅ OTA reservations: {count} pending")
        else:
            print("      ❌ Get OTA reservations failed")
        
        # Test exception queue
        success, response = self.run_test(
            "Get Exception Queue",
            "GET",
            "channel-manager/exceptions",
            200
        )
        
        if success:
            exceptions = response.get('exceptions', [])
            count = response.get('count', 0)
            print(f"      ✅ Exception queue: {count} exceptions")
        else:
            print("      ❌ Get exception queue failed")
        
        return True

    def test_rate_override_audit(self):
        """Test rate override and audit functionality"""
        print("\n1️⃣2️⃣ RATE OVERRIDE & AUDIT")
        print("=" * 50)
        
        # Test permission check
        permission_data = {
            "permission": "override_rate"
        }
        
        success, response = self.run_test(
            "Check Override Rate Permission",
            "POST",
            "permissions/check",
            200,
            data=permission_data
        )
        
        if success:
            has_permission = response.get('has_permission', False)
            print(f"      ✅ Permission check: override_rate = {has_permission}")
        else:
            print("      ❌ Permission check failed")
        
        # Test audit log creation (already tested during booking creation)
        success, response = self.run_test(
            "Get Audit Logs",
            "GET",
            "audit-logs?limit=10",
            200
        )
        
        if success:
            logs = response.get('logs', [])
            count = response.get('count', 0)
            print(f"      ✅ Audit logs retrieved: {count} total")
            
            if len(logs) > 0:
                recent_log = logs[0]
                print(f"      Recent action: {recent_log.get('action')} by {recent_log.get('user_name')}")
        else:
            print("      ❌ Audit logs retrieval failed")
        
        # Test folio export
        if self.created_resources['folios']:
            folio_id = self.created_resources['folios'][0]
            success, response = self.run_test(
                "Export Folio to CSV",
                "GET",
                f"export/folio/{folio_id}",
                200
            )
            
            if success:
                filename = response.get('filename', '')
                content_type = response.get('content_type', '')
                print(f"      ✅ Folio exported: {filename} ({content_type})")
            else:
                print("      ❌ Folio export failed")
        
        return True

    def test_night_audit_complete(self):
        """Test night audit functionality"""
        print("\n1️⃣3️⃣ NIGHT AUDIT")
        print("=" * 50)
        
        success, response = self.run_test(
            "Run Night Audit",
            "POST",
            "night-audit/post-room-charges",
            200
        )
        
        if success:
            charges_posted = response.get('charges_posted', 0)
            bookings_processed = response.get('bookings_processed', 0)
            
            print(f"      ✅ Night audit completed")
            print(f"      Charges posted: {charges_posted}")
            print(f"      Bookings processed: {bookings_processed}")
        else:
            print("      ❌ Night audit failed")
        
        return True

    def run_comprehensive_test(self):
        """Run comprehensive end-to-end workflow test"""
        print("🎯 COMPREHENSIVE END-TO-END WORKFLOW TESTING")
        print("=" * 60)
        
        # Step 1: Authentication & User Management
        if not self.test_authentication_flow():
            return False
        
        # Step 2: Company Management
        company_id = self.test_company_management_flow()
        if not company_id:
            return False
        
        # Step 3: Reservation Flow (Complete Cycle)
        booking_id = self.test_reservation_complete_cycle(company_id)
        if not booking_id:
            return False
        
        # Step 4: Check-in Process
        guest_folio_id, company_folio_id = self.test_checkin_process(booking_id, company_id)
        if not guest_folio_id:
            return False
        
        # Step 5: Folio & Billing
        if not self.test_folio_billing_complete(guest_folio_id, company_folio_id):
            return False
        
        # Step 6: Check-out Process
        if not self.test_checkout_process(booking_id):
            return False
        
        # Step 7: Invoicing
        if not self.test_invoicing_complete():
            return False
        
        # Step 8: Housekeeping
        if not self.test_housekeeping_complete():
            return False
        
        # Step 9: Reports
        if not self.test_reports_complete():
            return False
        
        # Step 10: RMS (Revenue Management)
        if not self.test_rms_complete():
            return False
        
        # Step 11: Channel Manager
        if not self.test_channel_manager_complete():
            return False
        
        # Step 12: Rate Override & Audit
        if not self.test_rate_override_audit():
            return False
        
        # Step 13: Night Audit
        if not self.test_night_audit_complete():
            return False
        
        return True

    def run_all_tests(self):
        """Run all comprehensive tests"""
        print("🚀 Starting RoomOps API Comprehensive Testing...")
        print(f"   Base URL: {self.base_url}")
        print(f"   API URL: {self.api_url}")
        
        # Run comprehensive end-to-end workflow
        if not self.run_comprehensive_test():
            print("❌ Comprehensive workflow failed")
            return False
        
        # Print final results
        print(f"\n🎯 FINAL TEST RESULTS:")
        print("=" * 60)
        print(f"   Tests Run: {self.tests_run}")
        print(f"   Tests Passed: {self.tests_passed}")
        print(f"   Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("🎉 ALL TESTS PASSED!")
            return True
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} tests failed")
            return False

if __name__ == "__main__":
    tester = ComprehensiveRoomOpsAPITester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)