"""
Demo Data Generator
Generates realistic demo data for new tenants
"""

import random
import uuid
from datetime import UTC, datetime, timedelta


class DemoDataGenerator:
    """Generate demo data for hotel PMS"""

    @staticmethod
    def generate_demo_hotel(tenant_id: str, hotel_type: str = "boutique") -> dict:
        """Generate complete demo hotel data"""

        if hotel_type == "boutique":
            config = {
                'name': 'The Pearl Boutique Hotel',
                'room_count': 25,
                'room_types': ['Standard Room', 'Deluxe Room', 'Junior Suite', 'Executive Suite'],
                'base_rate': 180
            }
        elif hotel_type == "resort":
            config = {
                'name': 'Paradise Beach Resort',
                'room_count': 120,
                'room_types': ['Standard Room', 'Ocean View Room', 'Deluxe Suite', 'Villa'],
                'base_rate': 220
            }
        else:  # city
            config = {
                'name': 'Metropolitan Business Hotel',
                'room_count': 80,
                'room_types': ['Standard Room', 'Executive Room', 'Business Suite'],
                'base_rate': 150
            }

        demo_data = {
            'tenant_id': tenant_id,
            'hotel_name': config['name'],
            'rooms': DemoDataGenerator._generate_rooms(tenant_id, config),
            'guests': DemoDataGenerator._generate_guests(tenant_id, 50),
            'bookings': [],  # Will be generated after rooms and guests
            'staff': DemoDataGenerator._generate_staff(tenant_id),
            'inventory': DemoDataGenerator._generate_inventory(tenant_id)
        }

        # Generate bookings with room and guest data
        demo_data['bookings'] = DemoDataGenerator._generate_bookings(
            tenant_id,
            demo_data['rooms'],
            demo_data['guests']
        )

        return demo_data

    @staticmethod
    def _generate_rooms(tenant_id: str, config: dict) -> list[dict]:
        """Generate demo rooms"""
        rooms = []
        room_number = 101
        room_types = config['room_types']
        total_rooms = config['room_count']
        base_rate = config['base_rate']

        rooms_per_type = total_rooms // len(room_types)

        for room_type in room_types:
            # Calculate rate multiplier
            if 'Suite' in room_type or 'Villa' in room_type:
                rate_multiplier = 1.8
                max_occupancy = 4
            elif 'Deluxe' in room_type or 'Executive' in room_type:
                rate_multiplier = 1.4
                max_occupancy = 3
            elif 'Ocean View' in room_type:
                rate_multiplier = 1.3
                max_occupancy = 2
            else:
                rate_multiplier = 1.0
                max_occupancy = 2

            for _ in range(rooms_per_type):
                status = random.choice(['available'] * 7 + ['occupied'] * 2 + ['cleaning'])

                room = {
                    'id': str(uuid.uuid4()),
                    'tenant_id': tenant_id,
                    'room_number': str(room_number),
                    'room_type': room_type,
                    'floor': room_number // 100,
                    'status': status,
                    'base_rate': round(base_rate * rate_multiplier, 2),
                    'max_occupancy': max_occupancy,
                    'amenities': ['WiFi', 'TV', 'AC', 'Minibar', 'Safe'],
                    'features': ['City View'] if 'Standard' in room_type else ['Sea View', 'Balcony'],
                    'bed_type': 'King' if 'Suite' in room_type else random.choice(['Queen', 'Twin']),
                    'smoking': False
                }

                rooms.append(room)
                room_number += 1

        return rooms

    @staticmethod
    def _generate_guests(tenant_id: str, count: int) -> list[dict]:
        """Generate demo guests"""
        first_names = ['John', 'Emma', 'Michael', 'Sophia', 'William', 'Olivia', 'James', 'Ava', 'Robert', 'Isabella']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']

        guests = []
        for i in range(count):
            first = random.choice(first_names)
            last = random.choice(last_names)

            guest = {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'name': f'{first} {last}',
                'email': f'{first.lower()}.{last.lower()}{i}@email.com',
                'phone': f'+1{random.randint(2000000000, 9999999999)}',
                'nationality': random.choice(['US', 'UK', 'CA', 'AU', 'DE', 'FR']),
                'id_number': f'{random.randint(100000000, 999999999)}',
                'date_of_birth': (datetime.now(UTC) - timedelta(days=random.randint(8000, 20000))).date().isoformat(),
                'loyalty_tier': random.choice(['bronze', 'silver', 'gold', 'platinum']),
                'loyalty_points': random.randint(0, 5000),
                'vip': random.random() < 0.1,
                'preferences': {
                    'room_type': random.choice(['quiet', 'high_floor', 'near_elevator']),
                    'pillow_type': random.choice(['soft', 'firm']),
                    'special_requests': []
                },
                'created_at': datetime.now(UTC).isoformat()
            }

            guests.append(guest)

        return guests

    @staticmethod
    def _generate_bookings(tenant_id: str, rooms: list[dict], guests: list[dict]) -> list[dict]:
        """Generate demo bookings"""
        bookings = []

        # Generate some past bookings
        for _ in range(15):
            guest = random.choice(guests)
            room = random.choice(rooms)

            check_in = datetime.now(UTC) - timedelta(days=random.randint(1, 30))
            nights = random.randint(1, 5)
            check_out = check_in + timedelta(days=nights)

            booking = {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'guest_id': guest['id'],
                'room_id': room['id'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'total_amount': room['base_rate'] * nights,
                'status': 'checked_out',
                'channel': random.choice(['direct', 'booking_com', 'expedia', 'airbnb']),
                'created_at': (check_in - timedelta(days=random.randint(1, 30))).isoformat()
            }

            bookings.append(booking)

        # Generate current bookings (checked in)
        for _ in range(10):
            guest = random.choice(guests)
            room = random.choice([r for r in rooms if r['status'] == 'occupied'][:10])

            check_in = datetime.now(UTC) - timedelta(days=random.randint(0, 3))
            nights = random.randint(2, 7)
            check_out = check_in + timedelta(days=nights)

            booking = {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'guest_id': guest['id'],
                'room_id': room['id'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'total_amount': room['base_rate'] * nights,
                'status': 'checked_in',
                'channel': random.choice(['direct', 'booking_com', 'expedia']),
                'created_at': (check_in - timedelta(days=random.randint(7, 60))).isoformat()
            }

            bookings.append(booking)

        # Generate future bookings (confirmed)
        for _ in range(20):
            guest = random.choice(guests)
            room = random.choice(rooms)

            check_in = datetime.now(UTC) + timedelta(days=random.randint(1, 60))
            nights = random.randint(1, 5)
            check_out = check_in + timedelta(days=nights)

            booking = {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'guest_id': guest['id'],
                'room_id': room['id'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'total_amount': room['base_rate'] * nights,
                'status': 'confirmed',
                'channel': random.choice(['direct', 'booking_com', 'expedia', 'airbnb']),
                'created_at': (check_in - timedelta(days=random.randint(1, 90))).isoformat()
            }

            bookings.append(booking)

        return bookings

    @staticmethod
    def _generate_staff(tenant_id: str) -> list[dict]:
        """Generate demo staff"""
        staff_members = [
            {'name': 'Sarah Manager', 'role': 'General Manager', 'department': 'management'},
            {'name': 'Mike Frontdesk', 'role': 'Front Desk Agent', 'department': 'front_desk'},
            {'name': 'Lisa Frontdesk', 'role': 'Front Desk Agent', 'department': 'front_desk'},
            {'name': 'Maria Housekeeper', 'role': 'Housekeeping Supervisor', 'department': 'housekeeping'},
            {'name': 'Ana Cleaner', 'role': 'Room Attendant', 'department': 'housekeeping'},
            {'name': 'Carlos Cleaner', 'role': 'Room Attendant', 'department': 'housekeeping'},
            {'name': 'Tom Engineer', 'role': 'Chief Engineer', 'department': 'engineering'},
            {'name': 'Bob Technician', 'role': 'Maintenance Technician', 'department': 'engineering'}
        ]

        staff = []
        for member in staff_members:
            staff.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'name': member['name'],
                'role': member['role'],
                'department': member['department'],
                'email': f"{member['name'].lower().replace(' ', '.')}@hotel.com",
                'phone': f'+1{random.randint(2000000000, 9999999999)}',
                'active': True,
                'created_at': datetime.now(UTC).isoformat()
            })

        return staff

    @staticmethod
    def _generate_inventory(tenant_id: str) -> list[dict]:
        """Generate demo inventory items"""
        items = [
            {'name': 'Bed Sheets', 'category': 'Linen', 'unit': 'pcs', 'stock': 150, 'min_stock': 50},
            {'name': 'Towels', 'category': 'Linen', 'unit': 'pcs', 'stock': 200, 'min_stock': 80},
            {'name': 'Pillows', 'category': 'Linen', 'unit': 'pcs', 'stock': 80, 'min_stock': 30},
            {'name': 'Toilet Paper', 'category': 'Amenities', 'unit': 'rolls', 'stock': 500, 'min_stock': 200},
            {'name': 'Shampoo', 'category': 'Amenities', 'unit': 'bottles', 'stock': 300, 'min_stock': 100},
            {'name': 'Soap', 'category': 'Amenities', 'unit': 'bars', 'stock': 400, 'min_stock': 150},
            {'name': 'Coffee', 'category': 'Minibar', 'unit': 'kg', 'stock': 25, 'min_stock': 10},
            {'name': 'Water Bottles', 'category': 'Minibar', 'unit': 'bottles', 'stock': 600, 'min_stock': 200}
        ]

        inventory = []
        for item in items:
            inventory.append({
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'item_name': item['name'],
                'category': item['category'],
                'unit_of_measure': item['unit'],
                'current_stock': item['stock'],
                'reorder_level': item['min_stock'],
                'unit_cost': round(random.uniform(1.0, 50.0), 2),
                'supplier': random.choice(['Hotel Supplies Co', 'Linen Express', 'Amenity World']),
                'last_updated': datetime.now(UTC).isoformat()
            })

        return inventory
