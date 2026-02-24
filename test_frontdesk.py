import requests
import json
from datetime import datetime, timedelta

def test_frontdesk_operations():
    # Test Front Desk Operations
    base_url = 'https://improvement-guide-1.preview.emergentagent.com/api'

    # First register a hotel and get token
    timestamp = datetime.now().strftime('%H%M%S')
    registration_data = {
        'property_name': f'Test Hotel FD {timestamp}',
        'email': f'testfd{timestamp}@example.com',
        'password': 'TestPass123!',
        'name': f'Test Manager FD {timestamp}',
        'phone': '+1234567890',
        'address': '123 Test Street, Test City'
    }

    print('=== Testing Front Desk Operations ===')
    print('Registering hotel...')
    response = requests.post(f'{base_url}/auth/register', json=registration_data)
    if response.status_code == 200:
        data = response.json()
        token = data['access_token']
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        print('✅ Hotel registered successfully')
        
        # Create a room
        room_data = {
            'room_number': '201',
            'room_type': 'deluxe',
            'floor': 2,
            'capacity': 2,
            'base_price': 200.00,
            'amenities': ['wifi', 'tv', 'minibar']
        }
        
        room_response = requests.post(f'{base_url}/pms/rooms', json=room_data, headers=headers)
        if room_response.status_code == 200:
            room = room_response.json()
            room_id = room['id']
            print('✅ Room created successfully')
            
            # Create a guest
            guest_data = {
                'name': 'John Smith',
                'email': 'john.smith@example.com',
                'phone': '+1234567890',
                'id_number': 'ID987654321',
                'address': '789 Guest Avenue'
            }
            
            guest_response = requests.post(f'{base_url}/pms/guests', json=guest_data, headers=headers)
            if guest_response.status_code == 200:
                guest = guest_response.json()
                guest_id = guest['id']
                print('✅ Guest created successfully')
                
                # Create a booking
                booking_data = {
                    'guest_id': guest_id,
                    'room_id': room_id,
                    'check_in': (datetime.now() + timedelta(days=1)).isoformat(),
                    'check_out': (datetime.now() + timedelta(days=3)).isoformat(),
                    'guests_count': 2,
                    'total_amount': 400.00,
                    'channel': 'direct'
                }
                
                booking_response = requests.post(f'{base_url}/pms/bookings', json=booking_data, headers=headers)
                if booking_response.status_code == 200:
                    booking = booking_response.json()
                    booking_id = booking['id']
                    print('✅ Booking created successfully')
                    print(f'   QR Code generated: {"Yes" if booking.get("qr_code") else "No"}')
                    
                    # First update booking status to confirmed
                    booking_update = requests.put(f'{base_url}/pms/bookings/{booking_id}', 
                                                json={'status': 'confirmed'}, headers=headers)
                    print(f'Booking status update: {booking_update.status_code}')
                    
                    # Test Front Desk Check-in
                    checkin_response = requests.post(f'{base_url}/frontdesk/checkin/{booking_id}', headers=headers)
                    print(f'Check-in response: {checkin_response.status_code} - {checkin_response.text}')
                    if checkin_response.status_code == 200:
                        print('✅ Check-in completed successfully')
                        checkin_data = checkin_response.json()
                        print(f'   Checked in at: {checkin_data.get("checked_in_at")}')
                        
                        # Test adding folio charges
                        charge_params = {
                            'charge_type': 'food',
                            'description': 'Room Service Dinner',
                            'amount': 45.99,
                            'quantity': 1
                        }
                        charge_response = requests.post(f'{base_url}/frontdesk/folio/{booking_id}/charge', 
                                                      params=charge_params, headers=headers)
                        if charge_response.status_code == 200:
                            print('✅ Folio charge added successfully')
                            
                            # Get folio details
                            folio_response = requests.get(f'{base_url}/frontdesk/folio/{booking_id}', headers=headers)
                            if folio_response.status_code == 200:
                                folio = folio_response.json()
                                print(f'✅ Folio retrieved - Total charges: ${folio["total_charges"]}, Balance: ${folio["balance"]}')
                                
                                # Process payment
                                payment_params = {
                                    'amount': folio["total_charges"],
                                    'method': 'card',
                                    'reference': 'CARD123456'
                                }
                                payment_response = requests.post(f'{base_url}/frontdesk/payment/{booking_id}',
                                                               params=payment_params, headers=headers)
                                if payment_response.status_code == 200:
                                    print('✅ Payment processed successfully')
                                    
                                    # Test Front Desk Check-out
                                    checkout_response = requests.post(f'{base_url}/frontdesk/checkout/{booking_id}', headers=headers)
                                    if checkout_response.status_code == 200:
                                        print('✅ Check-out completed successfully')
                                        checkout_data = checkout_response.json()
                                        print(f'   Final balance: ${checkout_data.get("balance", 0)}')
                                        
                                        # Test housekeeping tasks
                                        print('\n--- Testing Housekeeping ---')
                                        tasks_response = requests.get(f'{base_url}/housekeeping/tasks', headers=headers)
                                        if tasks_response.status_code == 200:
                                            tasks = tasks_response.json()
                                            print(f'✅ Found {len(tasks)} housekeeping tasks')
                                            
                                            if tasks:
                                                # Update first task status
                                                task_id = tasks[0]['id']
                                                update_params = {'status': 'in_progress', 'assigned_to': 'Housekeeper 1'}
                                                update_response = requests.put(f'{base_url}/housekeeping/tasks/{task_id}',
                                                                             params=update_params, headers=headers)
                                                if update_response.status_code == 200:
                                                    print('✅ Housekeeping task updated successfully')
                                                else:
                                                    print(f'❌ Task update failed: {update_response.status_code}')
                                        
                                        # Test reporting
                                        print('\n--- Testing Reporting ---')
                                        today = datetime.now().date().isoformat()
                                        tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
                                        
                                        # Occupancy report
                                        occ_response = requests.get(f'{base_url}/reports/occupancy',
                                                                  params={'start_date': today, 'end_date': tomorrow},
                                                                  headers=headers)
                                        if occ_response.status_code == 200:
                                            occ_data = occ_response.json()
                                            print(f'✅ Occupancy report: {occ_data["occupancy_rate"]}%')
                                        
                                        # Revenue report
                                        rev_response = requests.get(f'{base_url}/reports/revenue',
                                                                  params={'start_date': today, 'end_date': tomorrow},
                                                                  headers=headers)
                                        if rev_response.status_code == 200:
                                            rev_data = rev_response.json()
                                            print(f'✅ Revenue report: ${rev_data["total_revenue"]}, ADR: ${rev_data["adr"]}')
                                        
                                        # Daily summary
                                        daily_response = requests.get(f'{base_url}/reports/daily-summary',
                                                                    params={'date_str': today}, headers=headers)
                                        if daily_response.status_code == 200:
                                            daily_data = daily_response.json()
                                            print(f'✅ Daily summary: {daily_data["arrivals"]} arrivals, {daily_data["departures"]} departures')
                                        
                                        return True
                                    else:
                                        print(f'❌ Check-out failed: {checkout_response.status_code} - {checkout_response.text}')
                                else:
                                    print(f'❌ Payment failed: {payment_response.status_code} - {payment_response.text}')
                            else:
                                print(f'❌ Folio retrieval failed: {folio_response.status_code}')
                        else:
                            print(f'❌ Folio charge failed: {charge_response.status_code} - {charge_response.text}')
                    else:
                        print(f'❌ Check-in failed: {checkin_response.status_code} - {checkin_response.text}')
                else:
                    print(f'❌ Booking creation failed: {booking_response.status_code}')
            else:
                print(f'❌ Guest creation failed: {guest_response.status_code}')
        else:
            print(f'❌ Room creation failed: {room_response.status_code}')
    else:
        print(f'❌ Hotel registration failed: {response.status_code}')

    print('=== Front Desk Operations Test Complete ===')
    return False

if __name__ == "__main__":
    test_frontdesk_operations()