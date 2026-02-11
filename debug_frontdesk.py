import requests
import json
from datetime import datetime, timedelta

def debug_frontdesk():
    base_url = 'https://bug-fix-update.preview.emergentagent.com/api'
    
    # Register hotel
    timestamp = datetime.now().strftime('%H%M%S')
    registration_data = {
        'property_name': f'Debug Hotel {timestamp}',
        'email': f'debug{timestamp}@example.com',
        'password': 'TestPass123!',
        'name': f'Debug Manager {timestamp}',
        'phone': '+1234567890',
        'address': '123 Debug Street'
    }
    
    print('=== Debugging Front Desk Operations ===')
    
    # Register
    response = requests.post(f'{base_url}/auth/register', json=registration_data)
    if response.status_code != 200:
        print(f'❌ Registration failed: {response.status_code}')
        return
    
    data = response.json()
    token = data['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    print('✅ Hotel registered')
    
    # Create room
    room_data = {
        'room_number': '301',
        'room_type': 'standard',
        'floor': 3,
        'capacity': 2,
        'base_price': 150.00
    }
    
    room_response = requests.post(f'{base_url}/pms/rooms', json=room_data, headers=headers)
    if room_response.status_code != 200:
        print(f'❌ Room creation failed: {room_response.status_code}')
        return
    
    room = room_response.json()
    room_id = room['id']
    print(f'✅ Room created: {room_id}')
    
    # Create guest
    guest_data = {
        'name': 'Debug Guest',
        'email': 'debug.guest@example.com',
        'phone': '+1234567890',
        'id_number': 'DEBUG123'
    }
    
    guest_response = requests.post(f'{base_url}/pms/guests', json=guest_data, headers=headers)
    if guest_response.status_code != 200:
        print(f'❌ Guest creation failed: {guest_response.status_code}')
        return
    
    guest = guest_response.json()
    guest_id = guest['id']
    print(f'✅ Guest created: {guest_id}')
    
    # Create booking
    booking_data = {
        'guest_id': guest_id,
        'room_id': room_id,
        'check_in': datetime.now().isoformat(),  # Today
        'check_out': (datetime.now() + timedelta(days=2)).isoformat(),
        'guests_count': 1,
        'total_amount': 300.00,
        'channel': 'direct'
    }
    
    booking_response = requests.post(f'{base_url}/pms/bookings', json=booking_data, headers=headers)
    if booking_response.status_code != 200:
        print(f'❌ Booking creation failed: {booking_response.status_code}')
        print(f'Response: {booking_response.text}')
        return
    
    booking = booking_response.json()
    booking_id = booking['id']
    print(f'✅ Booking created: {booking_id}')
    print(f'   Status: {booking.get("status")}')
    
    # Get all bookings to verify
    all_bookings = requests.get(f'{base_url}/pms/bookings', headers=headers)
    if all_bookings.status_code == 200:
        bookings = all_bookings.json()
        print(f'✅ Found {len(bookings)} total bookings')
        for b in bookings:
            if b['id'] == booking_id:
                print(f'   Our booking found with status: {b.get("status")}')
    
    # Try check-in
    print(f'Attempting check-in for booking: {booking_id}')
    checkin_response = requests.post(f'{base_url}/frontdesk/checkin/{booking_id}', headers=headers)
    print(f'Check-in response: {checkin_response.status_code}')
    print(f'Response text: {checkin_response.text}')
    
    if checkin_response.status_code == 200:
        print('✅ Check-in successful!')
        checkin_data = checkin_response.json()
        print(f'   Message: {checkin_data.get("message")}')
        
        # Test folio operations
        print('\n--- Testing Folio Operations ---')
        
        # Get folio
        folio_response = requests.get(f'{base_url}/frontdesk/folio/{booking_id}', headers=headers)
        print(f'Folio response: {folio_response.status_code}')
        if folio_response.status_code == 200:
            folio = folio_response.json()
            print(f'✅ Folio retrieved - Balance: ${folio.get("balance", 0)}')
            
            # Add charge
            charge_params = {
                'charge_type': 'minibar',
                'description': 'Minibar consumption',
                'amount': 25.50,
                'quantity': 1
            }
            charge_response = requests.post(f'{base_url}/frontdesk/folio/{booking_id}/charge',
                                          params=charge_params, headers=headers)
            print(f'Charge response: {charge_response.status_code}')
            if charge_response.status_code == 200:
                print('✅ Charge added successfully')
                
                # Get updated folio
                folio_response2 = requests.get(f'{base_url}/frontdesk/folio/{booking_id}', headers=headers)
                if folio_response2.status_code == 200:
                    folio2 = folio_response2.json()
                    print(f'✅ Updated folio - Balance: ${folio2.get("balance", 0)}')
    else:
        print(f'❌ Check-in failed: {checkin_response.status_code}')
        print(f'Error: {checkin_response.text}')

if __name__ == "__main__":
    debug_frontdesk()