import requests
import sys
import json
from datetime import datetime, timedelta

class HousekeepingTester:
    def __init__(self, base_url="https://improvement-guide-1.preview.emergentagent.com"):
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
            'companies': []
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
        print(f"\n🔍 Testing {name}...")
        
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

    def setup_auth(self):
        """Setup authentication"""
        timestamp = datetime.now().strftime('%H%M%S')
        registration_data = {
            "property_name": f"Housekeeping Test Hotel {timestamp}",
            "email": f"hktest{timestamp}@example.com",
            "password": "TestPass123!",
            "name": f"HK Test Manager {timestamp}",
            "phone": "+1234567890",
            "address": "123 Housekeeping Test Street"
        }
        
        success, response = self.run_test(
            "Register Test Tenant",
            "POST",
            "auth/register",
            200,
            data=registration_data
        )
        
        if success and 'access_token' in response:
            self.token = response['access_token']
            self.user = response['user']
            self.tenant = response['tenant']
            return True
        return False

    def create_test_data(self):
        """Create comprehensive test data for housekeeping scenarios"""
        print("\n🏗️ Creating Test Data...")
        
        # Create rooms with different statuses
        room_data_list = [
            {"room_number": "301", "status": "available"},
            {"room_number": "302", "status": "dirty"}, 
            {"room_number": "303", "status": "occupied"},
            {"room_number": "304", "status": "cleaning"},
            {"room_number": "305", "status": "inspected"},
            {"room_number": "306", "status": "available"}  # For arrivals
        ]
        
        for room_info in room_data_list:
            room_data = {
                "room_number": room_info["room_number"],
                "room_type": "deluxe",
                "floor": 3,
                "capacity": 2,
                "base_price": 150.00,
                "amenities": ["wifi", "tv", "minibar"]
            }
            
            success, response = self.run_test(
                f"Create Room {room_info['room_number']}",
                "POST",
                "pms/rooms",
                200,
                data=room_data
            )
            
            if success and 'id' in response:
                room_id = response['id']
                self.created_resources['rooms'].append(room_id)
                
                # Set room status if not available
                if room_info["status"] != "available":
                    success, _ = self.run_test(
                        f"Set Room {room_info['room_number']} Status",
                        "PUT",
                        f"pms/rooms/{room_id}",
                        200,
                        data={"status": room_info["status"]}
                    )
        
        # Create test guests
        guest_names = ["Emma Wilson", "James Brown", "Sophia Davis", "Michael Johnson", "Olivia Garcia", "William Miller"]
        for i, name in enumerate(guest_names):
            guest_data = {
                "name": name,
                "email": f"hkguest{i+1}@example.com",
                "phone": f"+1234567{i:03d}",
                "id_number": f"HKG{i+1:03d}",
                "address": f"{i+1}00 Housekeeping Street"
            }
            
            success, response = self.run_test(
                f"Create Guest {name}",
                "POST",
                "pms/guests",
                200,
                data=guest_data
            )
            
            if success and 'id' in response:
                self.created_resources['guests'].append(response['id'])
        
        # Create bookings for different scenarios
        if len(self.created_resources['rooms']) >= 6 and len(self.created_resources['guests']) >= 6:
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            future_date = today + timedelta(days=3)
            
            # Scenario 1: Due out today (checked-in guest)
            booking_data = {
                "guest_id": self.created_resources['guests'][0],
                "room_id": self.created_resources['rooms'][0],
                "check_in": (today - timedelta(days=1)).isoformat(),
                "check_out": today.isoformat(),
                "adults": 2,
                "children": 0,
                "children_ages": [],
                "guests_count": 2,
                "total_amount": 150.0,
                "channel": "direct"
            }
            
            success, response = self.run_test(
                "Create Due Out Today Booking",
                "POST",
                "pms/bookings",
                200,
                data=booking_data
            )
            
            if success and 'id' in response:
                booking_id = response['id']
                self.created_resources['bookings'].append(booking_id)
                
                # Check-in the guest
                success, _ = self.run_test(
                    "Check-in Due Out Today Guest",
                    "POST",
                    f"frontdesk/checkin/{booking_id}",
                    200
                )
            
            # Scenario 2: Due out tomorrow (checked-in guest)
            booking_data = {
                "guest_id": self.created_resources['guests'][1],
                "room_id": self.created_resources['rooms'][1],
                "check_in": today.isoformat(),
                "check_out": tomorrow.isoformat(),
                "adults": 1,
                "children": 1,
                "children_ages": [8],
                "guests_count": 2,
                "total_amount": 150.0,
                "channel": "direct"
            }
            
            success, response = self.run_test(
                "Create Due Out Tomorrow Booking",
                "POST",
                "pms/bookings",
                200,
                data=booking_data
            )
            
            if success and 'id' in response:
                booking_id = response['id']
                self.created_resources['bookings'].append(booking_id)
                
                # Set room to available first, then check-in
                success, _ = self.run_test(
                    "Set Room Available for Check-in",
                    "PUT",
                    f"pms/rooms/{self.created_resources['rooms'][1]}",
                    200,
                    data={"status": "available"}
                )
                
                success, _ = self.run_test(
                    "Check-in Due Out Tomorrow Guest",
                    "POST",
                    f"frontdesk/checkin/{booking_id}",
                    200
                )
            
            # Scenario 3: Stayover (checked-in, checking out in 3 days)
            booking_data = {
                "guest_id": self.created_resources['guests'][2],
                "room_id": self.created_resources['rooms'][2],
                "check_in": today.isoformat(),
                "check_out": future_date.isoformat(),
                "adults": 2,
                "children": 0,
                "children_ages": [],
                "guests_count": 2,
                "total_amount": 450.0,  # 3 nights
                "channel": "direct"
            }
            
            success, response = self.run_test(
                "Create Stayover Booking",
                "POST",
                "pms/bookings",
                200,
                data=booking_data
            )
            
            if success and 'id' in response:
                booking_id = response['id']
                self.created_resources['bookings'].append(booking_id)
                
                # Set room to available first, then check-in
                success, _ = self.run_test(
                    "Set Room Available for Stayover Check-in",
                    "PUT",
                    f"pms/rooms/{self.created_resources['rooms'][2]}",
                    200,
                    data={"status": "available"}
                )
                
                success, _ = self.run_test(
                    "Check-in Stayover Guest",
                    "POST",
                    f"frontdesk/checkin/{booking_id}",
                    200
                )
            
            # Scenario 4: Arrival today (confirmed, room available)
            booking_data = {
                "guest_id": self.created_resources['guests'][3],
                "room_id": self.created_resources['rooms'][5],  # Room 306 - available
                "check_in": today.isoformat(),
                "check_out": tomorrow.isoformat(),
                "adults": 1,
                "children": 0,
                "children_ages": [],
                "guests_count": 1,
                "total_amount": 150.0,
                "channel": "direct"
            }
            
            success, response = self.run_test(
                "Create Arrival Today Booking (Room Ready)",
                "POST",
                "pms/bookings",
                200,
                data=booking_data
            )
            
            if success and 'id' in response:
                self.created_resources['bookings'].append(response['id'])
            
            # Scenario 5: Arrival today (confirmed, room dirty - not ready)
            booking_data = {
                "guest_id": self.created_resources['guests'][4],
                "room_id": self.created_resources['rooms'][1],  # Room 302 - dirty
                "check_in": today.isoformat(),
                "check_out": (today + timedelta(days=2)).isoformat(),
                "adults": 2,
                "children": 1,
                "children_ages": [12],
                "guests_count": 3,
                "total_amount": 300.0,
                "channel": "direct"
            }
            
            success, response = self.run_test(
                "Create Arrival Today Booking (Room Not Ready)",
                "POST",
                "pms/bookings",
                200,
                data=booking_data
            )
            
            if success and 'id' in response:
                self.created_resources['bookings'].append(response['id'])

    def test_housekeeping_endpoints(self):
        """Test all housekeeping endpoints comprehensively"""
        print("\n🧹 Testing Housekeeping Board Endpoints...")
        
        # Test 1: Room Status Board
        print("\n📋 Test 1: Room Status Board")
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
            
            print(f"   📊 Total Rooms: {total_rooms}")
            print(f"   📊 Status Counts: {status_counts}")
            
            # Verify all required statuses are present
            required_statuses = ['available', 'occupied', 'dirty', 'cleaning', 'inspected', 'maintenance', 'out_of_order']
            if all(status in status_counts for status in required_statuses):
                print("   ✅ All status categories present")
                self.tests_passed += 1
            else:
                print("   ❌ Missing status categories")
        else:
            print("   ❌ Room status board failed")
        self.tests_run += 1
        
        # Test 2: Due Out Rooms
        print("\n📋 Test 2: Due Out Rooms")
        success, response = self.run_test(
            "Get Due Out Rooms",
            "GET",
            "housekeeping/due-out",
            200
        )
        
        if success:
            due_out_rooms = response.get('due_out_rooms', [])
            count = response.get('count', 0)
            
            print(f"   📊 Due Out Count: {count}")
            
            # Verify structure and data
            today_count = 0
            tomorrow_count = 0
            for room in due_out_rooms:
                if room.get('is_today'):
                    today_count += 1
                else:
                    tomorrow_count += 1
                print(f"   🏠 Room {room.get('room_number')}: {room.get('guest_name')} - {'Today' if room.get('is_today') else 'Tomorrow'}")
            
            print(f"   📊 Today: {today_count}, Tomorrow: {tomorrow_count}")
            
            # Check required fields
            if due_out_rooms:
                required_fields = ['room_number', 'room_type', 'guest_name', 'checkout_date', 'booking_id', 'is_today']
                if all(field in due_out_rooms[0] for field in required_fields):
                    print("   ✅ Due out rooms structure verified")
                    self.tests_passed += 1
                else:
                    print("   ❌ Due out rooms missing required fields")
            else:
                print("   ✅ No due out rooms (valid scenario)")
                self.tests_passed += 1
        else:
            print("   ❌ Due out rooms failed")
        self.tests_run += 1
        
        # Test 3: Stayover Rooms
        print("\n📋 Test 3: Stayover Rooms")
        success, response = self.run_test(
            "Get Stayover Rooms",
            "GET",
            "housekeeping/stayovers",
            200
        )
        
        if success:
            stayover_rooms = response.get('stayover_rooms', [])
            count = response.get('count', 0)
            
            print(f"   📊 Stayover Count: {count}")
            
            for room in stayover_rooms:
                nights = room.get('nights_remaining', 0)
                print(f"   🏠 Room {room.get('room_number')}: {room.get('guest_name')} - {nights} nights remaining")
                
                # Verify nights calculation is positive
                if nights <= 0:
                    print(f"   ❌ Invalid nights remaining: {nights}")
                    break
            else:
                if stayover_rooms:
                    required_fields = ['room_number', 'guest_name', 'nights_remaining']
                    if all(field in stayover_rooms[0] for field in required_fields):
                        print("   ✅ Stayover rooms structure verified")
                        self.tests_passed += 1
                    else:
                        print("   ❌ Stayover rooms missing required fields")
                else:
                    print("   ✅ No stayover rooms (valid scenario)")
                    self.tests_passed += 1
        else:
            print("   ❌ Stayover rooms failed")
        self.tests_run += 1
        
        # Test 4: Arrival Rooms
        print("\n📋 Test 4: Arrival Rooms")
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
            
            print(f"   📊 Arrival Count: {count}, Ready: {ready_count}")
            
            actual_ready = 0
            for room in arrival_rooms:
                room_status = room.get('room_status', '')
                is_ready = room.get('ready', False)
                expected_ready = room_status in ['available', 'inspected']
                
                print(f"   🏠 Room {room.get('room_number')}: {room.get('guest_name')} - Status: {room_status}, Ready: {is_ready}")
                
                if is_ready == expected_ready:
                    if is_ready:
                        actual_ready += 1
                else:
                    print(f"   ❌ Ready logic error: status={room_status}, ready={is_ready}, expected={expected_ready}")
                    break
            else:
                if actual_ready == ready_count:
                    print("   ✅ Arrival rooms ready count verified")
                    self.tests_passed += 1
                else:
                    print(f"   ❌ Ready count mismatch: expected {ready_count}, calculated {actual_ready}")
        else:
            print("   ❌ Arrival rooms failed")
        self.tests_run += 1
        
        # Test 5: Quick Room Status Update
        print("\n📋 Test 5: Quick Room Status Update")
        if self.created_resources['rooms']:
            room_id = self.created_resources['rooms'][0]
            
            # Valid status update
            success, response = self.run_test(
                "Update Room Status to Inspected",
                "PUT",
                f"housekeeping/room/{room_id}/status?new_status=inspected",
                200
            )
            
            if success:
                message = response.get('message', '')
                new_status = response.get('new_status', '')
                room_number = response.get('room_number', '')
                
                if new_status == 'inspected' and room_number:
                    print(f"   ✅ Status update successful: {message}")
                    self.tests_passed += 1
                else:
                    print("   ❌ Status update response invalid")
            else:
                print("   ❌ Status update failed")
            self.tests_run += 1
            
            # Invalid status
            success, response = self.run_test(
                "Update Room Status to Invalid",
                "PUT",
                f"housekeeping/room/{room_id}/status?new_status=invalid_status",
                400
            )
            
            if not success:  # Expected to fail
                print("   ✅ Invalid status correctly rejected")
                self.tests_passed += 1
            else:
                print("   ❌ Invalid status should have been rejected")
            self.tests_run += 1
            
            # Non-existent room
            success, response = self.run_test(
                "Update Non-existent Room Status",
                "PUT",
                "housekeeping/room/non-existent-id/status?new_status=cleaning",
                404
            )
            
            if not success:  # Expected to fail
                print("   ✅ Non-existent room correctly rejected")
                self.tests_passed += 1
            else:
                print("   ❌ Non-existent room should have been rejected")
            self.tests_run += 1
        
        # Test 6: Task Assignment
        print("\n📋 Test 6: Task Assignment")
        if self.created_resources['rooms']:
            room_id = self.created_resources['rooms'][0]
            
            success, response = self.run_test(
                "Assign Cleaning Task",
                "POST",
                f"housekeeping/assign?room_id={room_id}&assigned_to=Sarah&task_type=cleaning&priority=high",
                200
            )
            
            if success:
                message = response.get('message', '')
                task = response.get('task', {})
                
                if ('Sarah' in message and 
                    task.get('assigned_to') == 'Sarah' and
                    task.get('task_type') == 'cleaning' and
                    task.get('priority') == 'high'):
                    print(f"   ✅ Task assignment successful: {message}")
                    print(f"   📋 Task ID: {task.get('id')}")
                    self.tests_passed += 1
                else:
                    print("   ❌ Task assignment response invalid")
            else:
                print("   ❌ Task assignment failed")
            self.tests_run += 1

    def run_all_tests(self):
        """Run all housekeeping tests"""
        print("🧹 Starting Housekeeping Board API Testing...")
        print("=" * 60)
        
        if not self.setup_auth():
            print("❌ Authentication setup failed")
            return 1
        
        self.create_test_data()
        self.test_housekeeping_endpoints()
        
        # Print results
        print("\n" + "=" * 60)
        print(f"📊 Final Results: {self.tests_passed}/{self.tests_run} tests passed")
        print(f"🎯 Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All housekeeping tests passed!")
            return 0
        else:
            print("⚠️ Some housekeeping tests failed")
            return 1

if __name__ == "__main__":
    tester = HousekeepingTester()
    sys.exit(tester.run_all_tests())