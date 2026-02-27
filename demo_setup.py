"""
DEMO SETUP SCRIPT - ROOMOPS HOTEL PMS
Creates realistic sample data for demo purposes
"""

import requests
import json
from datetime import datetime, timedelta
import random

BASE_URL = "https://appstore-preview-1.preview.emergentagent.com/api"
TOKEN = None

def register_demo_hotel():
    """Register demo hotel account"""
    global TOKEN
    
    data = {
        "property_name": "Grand Hotel Istanbul",
        "email": "demo@grandhotel.com",
        "password": "Demo123!",
        "name": "Demo Manager",
        "phone": "+90-212-555-0100",
        "address": "Taksim Square, Istanbul, Turkey"
    }
    
    response = requests.post(f"{BASE_URL}/auth/register", json=data)
    if response.status_code == 200:
        result = response.json()
        TOKEN = result['access_token']
        print("✅ Demo hotel registered successfully")
        print(f"   Email: {data['email']}")
        print(f"   Password: {data['password']}")
        return TOKEN
    else:
        print(f"❌ Registration failed: {response.text}")
        return None

def create_rooms():
    """Create sample rooms"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    
    rooms = [
        # Standard Rooms
        {"room_number": "101", "room_type": "standard", "floor": 1, "capacity": 2, "base_price": 100.00, "amenities": ["wifi", "tv"]},
        {"room_number": "102", "room_type": "standard", "floor": 1, "capacity": 2, "base_price": 100.00, "amenities": ["wifi", "tv"]},
        {"room_number": "103", "room_type": "standard", "floor": 1, "capacity": 2, "base_price": 100.00, "amenities": ["wifi", "tv"]},
        {"room_number": "104", "room_type": "standard", "floor": 1, "capacity": 2, "base_price": 100.00, "amenities": ["wifi", "tv"]},
        # Deluxe Rooms
        {"room_number": "201", "room_type": "deluxe", "floor": 2, "capacity": 2, "base_price": 150.00, "amenities": ["wifi", "tv", "minibar", "balcony"]},
        {"room_number": "202", "room_type": "deluxe", "floor": 2, "capacity": 2, "base_price": 150.00, "amenities": ["wifi", "tv", "minibar", "balcony"]},
        {"room_number": "203", "room_type": "deluxe", "floor": 2, "capacity": 2, "base_price": 150.00, "amenities": ["wifi", "tv", "minibar", "balcony"]},
        # Suites
        {"room_number": "301", "room_type": "suite", "floor": 3, "capacity": 4, "base_price": 250.00, "amenities": ["wifi", "tv", "minibar", "balcony", "living_room", "jacuzzi"]},
        {"room_number": "302", "room_type": "suite", "floor": 3, "capacity": 4, "base_price": 250.00, "amenities": ["wifi", "tv", "minibar", "balcony", "living_room", "jacuzzi"]},
        {"room_number": "303", "room_type": "suite", "floor": 3, "capacity": 4, "base_price": 250.00, "amenities": ["wifi", "tv", "minibar", "balcony", "living_room", "jacuzzi"]},
    ]
    
    created_rooms = []
    for room in rooms:
        response = requests.post(f"{BASE_URL}/pms/rooms", json=room, headers=headers)
        if response.status_code == 200:
            created_rooms.append(response.json())
            print(f"✅ Created room {room['room_number']} ({room['room_type']})")
        else:
            print(f"❌ Failed to create room {room['room_number']}")
    
    return created_rooms

def create_guests():
    """Create sample guests"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    
    guests = [
        {"name": "John Smith", "email": "john.smith@email.com", "phone": "+1-555-0101", "id_number": "P12345678", "address": "New York, USA"},
        {"name": "Emma Wilson", "email": "emma.wilson@email.com", "phone": "+1-555-0102", "id_number": "P23456789", "address": "London, UK"},
        {"name": "Mohammed Al-Rashid", "email": "m.rashid@email.com", "phone": "+971-555-0103", "id_number": "P34567890", "address": "Dubai, UAE"},
        {"name": "Maria Garcia", "email": "maria.garcia@email.com", "phone": "+34-555-0104", "id_number": "P45678901", "address": "Madrid, Spain"},
        {"name": "Chen Wei", "email": "chen.wei@email.com", "phone": "+86-555-0105", "id_number": "P56789012", "address": "Shanghai, China"},
        {"name": "Anna Müller", "email": "anna.muller@email.com", "phone": "+49-555-0106", "id_number": "P67890123", "address": "Berlin, Germany"},
        {"name": "Takeshi Yamamoto", "email": "t.yamamoto@email.com", "phone": "+81-555-0107", "id_number": "P78901234", "address": "Tokyo, Japan"},
        {"name": "Sophie Dubois", "email": "sophie.dubois@email.com", "phone": "+33-555-0108", "id_number": "P89012345", "address": "Paris, France"},
    ]
    
    created_guests = []
    for guest in guests:
        response = requests.post(f"{BASE_URL}/pms/guests", json=guest, headers=headers)
        if response.status_code == 200:
            created_guests.append(response.json())
            print(f"✅ Created guest {guest['name']}")
        else:
            print(f"❌ Failed to create guest {guest['name']}")
    
    return created_guests

def create_company():
    """Create sample company"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    
    company = {
        "name": "TechCorp International",
        "corporate_code": "TECH001",
        "tax_number": "1234567890",
        "billing_address": "Silicon Valley, CA 94025, USA",
        "contact_person": "Robert Johnson",
        "contact_email": "accounting@techcorp.com",
        "contact_phone": "+1-650-555-0100",
        "contracted_rate": "corp_std",
        "default_rate_type": "corporate",
        "default_market_segment": "corporate",
        "default_cancellation_policy": "h48",
        "payment_terms": "Net 30",
        "status": "active"
    }
    
    response = requests.post(f"{BASE_URL}/companies", json=company, headers=headers)
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Created company {company['name']}")
        return result
    else:
        print(f"❌ Failed to create company: {response.text}")
        return None

def create_bookings(rooms, guests, company):
    """Create sample bookings with various statuses"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    
    today = datetime.now()
    
    bookings = [
        # Checked-in bookings (in-house guests)
        {
            "guest_id": guests[0]['id'],
            "room_id": rooms[0]['id'],
            "check_in": (today - timedelta(days=1)).isoformat(),
            "check_out": (today + timedelta(days=2)).isoformat(),
            "guests_count": 2,
            "adults": 2,
            "children": 0,
            "children_ages": [],
            "total_amount": 100.00,
            "status": "checked_in"
        },
        {
            "guest_id": guests[1]['id'],
            "room_id": rooms[4]['id'],
            "check_in": (today - timedelta(days=2)).isoformat(),
            "check_out": (today + timedelta(days=1)).isoformat(),
            "guests_count": 3,
            "adults": 2,
            "children": 1,
            "children_ages": [8],
            "total_amount": 150.00,
            "status": "checked_in"
        },
        # Today's arrivals
        {
            "guest_id": guests[2]['id'],
            "room_id": rooms[1]['id'],
            "check_in": today.isoformat(),
            "check_out": (today + timedelta(days=3)).isoformat(),
            "guests_count": 1,
            "adults": 1,
            "children": 0,
            "children_ages": [],
            "total_amount": 100.00,
            "status": "confirmed"
        },
        # Future bookings
        {
            "guest_id": guests[3]['id'],
            "room_id": rooms[2]['id'],
            "check_in": (today + timedelta(days=2)).isoformat(),
            "check_out": (today + timedelta(days=5)).isoformat(),
            "guests_count": 4,
            "adults": 2,
            "children": 2,
            "children_ages": [5, 10],
            "total_amount": 100.00,
            "status": "confirmed"
        },
        # Corporate booking with company
        {
            "guest_id": guests[4]['id'],
            "room_id": rooms[7]['id'],
            "check_in": (today + timedelta(days=1)).isoformat(),
            "check_out": (today + timedelta(days=4)).isoformat(),
            "guests_count": 2,
            "adults": 2,
            "children": 0,
            "children_ages": [],
            "company_id": company['id'],
            "contracted_rate": "corp_std",
            "rate_type": "corporate",
            "market_segment": "corporate",
            "total_amount": 200.00,
            "status": "confirmed"
        },
    ]
    
    created_bookings = []
    for booking in bookings:
        response = requests.post(f"{BASE_URL}/pms/bookings", json=booking, headers=headers)
        if response.status_code == 200:
            result = response.json()
            created_bookings.append(result)
            print(f"✅ Created booking for {booking.get('check_in', '')} - Status: {booking['status']}")
        else:
            print(f"❌ Failed to create booking: {response.text}")
    
    return created_bookings

def create_folio_data(bookings):
    """Create sample folio charges and payments"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    
    # For each checked-in booking, add charges and payments
    for booking in bookings:
        if booking.get('status') == 'checked_in':
            booking_id = booking['id']
            
            # Get folios for this booking
            response = requests.get(f"{BASE_URL}/folio/booking/{booking_id}", headers=headers)
            if response.status_code == 200:
                folios = response.json()
                if folios:
                    folio_id = folios[0]['id']
                    
                    # Add room charge
                    requests.post(f"{BASE_URL}/folio/{folio_id}/charge", json={
                        "charge_category": "room",
                        "description": "Room charge",
                        "quantity": 1,
                        "unit_price": 100.00
                    }, headers=headers)
                    
                    # Add minibar charge
                    requests.post(f"{BASE_URL}/folio/{folio_id}/charge", json={
                        "charge_category": "minibar",
                        "description": "Minibar items",
                        "quantity": 1,
                        "unit_price": 25.00
                    }, headers=headers)
                    
                    # Add payment
                    requests.post(f"{BASE_URL}/folio/{folio_id}/payment", json={
                        "payment_type": "prepayment",
                        "payment_method": "card",
                        "amount": 50.00
                    }, headers=headers)
                    
                    print(f"✅ Added charges and payments to folio {folio_id}")

def create_channel_connections():
    """Create sample channel connections"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    
    connections = [
        {
            "channel_type": "booking_com",
            "channel_name": "Grand Hotel Istanbul - Booking.com",
            "property_id": "GHI-BCM-12345",
            "status": "active"
        },
        {
            "channel_type": "expedia",
            "channel_name": "Grand Hotel Istanbul - Expedia",
            "property_id": "GHI-EXP-67890",
            "status": "active"
        }
    ]
    
    for conn in connections:
        response = requests.post(f"{BASE_URL}/channel-manager/connections", json=conn, headers=headers)
        if response.status_code == 200:
            print(f"✅ Created channel connection: {conn['channel_name']}")
        else:
            print(f"❌ Failed to create connection: {response.text}")

def generate_rms_suggestions():
    """Generate RMS pricing suggestions"""
    headers = {'Authorization': f'Bearer {TOKEN}'}
    
    today = datetime.now()
    start_date = today.strftime('%Y-%m-%d')
    end_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')
    
    response = requests.post(
        f"{BASE_URL}/rms/generate-suggestions",
        params={"start_date": start_date, "end_date": end_date},
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Generated {result.get('total_count', 0)} RMS suggestions")
    else:
        print(f"❌ Failed to generate RMS suggestions: {response.text}")

def main():
    """Main setup function"""
    print("="*60)
    print("ROOMOPS DEMO SETUP")
    print("="*60)
    print()
    
    # Step 1: Register demo hotel
    print("Step 1: Registering demo hotel...")
    token = register_demo_hotel()
    if not token:
        print("❌ Setup failed. Could not register hotel.")
        return
    print()
    
    # Step 2: Create rooms
    print("Step 2: Creating rooms...")
    rooms = create_rooms()
    print()
    
    # Step 3: Create guests
    print("Step 3: Creating guests...")
    guests = create_guests()
    print()
    
    # Step 4: Create company
    print("Step 4: Creating company...")
    company = create_company()
    print()
    
    # Step 5: Create bookings
    print("Step 5: Creating bookings...")
    bookings = create_bookings(rooms, guests, company)
    print()
    
    # Step 6: Add folio data
    print("Step 6: Adding folio charges and payments...")
    create_folio_data(bookings)
    print()
    
    # Step 7: Create channel connections
    print("Step 7: Creating channel connections...")
    create_channel_connections()
    print()
    
    # Step 8: Generate RMS suggestions
    print("Step 8: Generating RMS suggestions...")
    generate_rms_suggestions()
    print()
    
    print("="*60)
    print("✅ DEMO SETUP COMPLETED SUCCESSFULLY!")
    print("="*60)
    print()
    print("LOGIN CREDENTIALS:")
    print("  Email: demo@grandhotel.com")
    print("  Password: Demo123!")
    print()
    print("DEMO DATA SUMMARY:")
    print(f"  Rooms: {len(rooms)}")
    print(f"  Guests: {len(guests)}")
    print(f"  Bookings: {len(bookings)}")
    print(f"  Company: 1 (TechCorp International)")
    print(f"  Channel Connections: 2 (Booking.com, Expedia)")
    print()

if __name__ == "__main__":
    main()
