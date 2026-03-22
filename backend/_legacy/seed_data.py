"""
Automatic Database Seeding for Hotel PMS
Runs on startup to create test data
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
import uuid
from datetime import datetime, timezone, timedelta
import random

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class HotelSeeder:
    def __init__(self):
        self.client = AsyncIOMotorClient('mongodb://localhost:27017')
        self.db = self.client.hotel_pms
        self.tenant_id = "hotel-demo-tenant"
        
    async def clear_database(self):
        """Clear all collections"""
        collections = await self.db.list_collection_names()
        for collection in collections:
            await self.db[collection].delete_many({})
        print("✓ Database cleared")
    
    async def create_users(self):
        """Create admin and staff users"""
        users = [
            {
                'id': str(uuid.uuid4()),
                'email': 'admin@hotel.com',
                'name': 'Hotel Admin',
                'role': 'admin',
                'hashed_password': pwd_context.hash("admin123"),
                'tenant_id': self.tenant_id,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'is_active': True
            },
            {
                'id': str(uuid.uuid4()),
                'email': 'frontdesk@hotel.com',
                'name': 'Ayşe Yılmaz',
                'role': 'front_desk',
                'hashed_password': pwd_context.hash("frontdesk123"),
                'tenant_id': self.tenant_id,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'is_active': True
            },
            {
                'id': str(uuid.uuid4()),
                'email': 'housekeeping@hotel.com',
                'name': 'Fatma Demir',
                'role': 'housekeeping',
                'hashed_password': pwd_context.hash("housekeeping123"),
                'tenant_id': self.tenant_id,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'is_active': True
            },
            {
                'id': str(uuid.uuid4()),
                'email': 'finance@hotel.com',
                'name': 'Mehmet Kaya',
                'role': 'finance',
                'hashed_password': pwd_context.hash("finance123"),
                'tenant_id': self.tenant_id,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'is_active': True
            }
        ]
        await self.db.users.insert_many(users)
        print(f"✓ Created {len(users)} users")
        return users
    
    async def create_rooms(self):
        """Create hotel rooms"""
        rooms = []
        room_types = [
            {'type': 'Standard', 'rate': 100.0, 'count': 10},
            {'type': 'Deluxe', 'rate': 150.0, 'count': 8},
            {'type': 'Suite', 'rate': 250.0, 'count': 4},
            {'type': 'Presidential', 'rate': 500.0, 'count': 2}
        ]
        
        room_counter = 101
        for room_type_info in room_types:
            for _ in range(room_type_info['count']):
                floor = int(str(room_counter)[0])
                rooms.append({
                    'id': str(uuid.uuid4()),
                    'tenant_id': self.tenant_id,
                    'room_number': str(room_counter),
                    'room_type': room_type_info['type'],
                    'status': random.choice(['available', 'occupied', 'dirty', 'cleaning', 'inspected']),
                    'floor': floor,
                    'capacity': 2 if room_type_info['type'] in ['Standard', 'Deluxe'] else 4,
                    'bed_type': random.choice(['single', 'double', 'king', 'twin']),
                    'max_occupancy': 2 if room_type_info['type'] in ['Standard', 'Deluxe'] else 4,
                    'base_price': room_type_info['rate'],
                    'current_booking_id': None,
                    'is_active': True,
                    'amenities': ['TV', 'WiFi', 'Air Conditioning', 'Mini Bar'],
                    'created_at': datetime.now(timezone.utc).isoformat()
                })
                room_counter += 1
        
        await self.db.rooms.insert_many(rooms)
        print(f"✓ Created {len(rooms)} rooms")
        return rooms
    
    async def create_guests(self):
        """Create guest profiles"""
        turkish_names = [
            ('Ahmet', 'Yılmaz'), ('Mehmet', 'Demir'), ('Ayşe', 'Çelik'),
            ('Fatma', 'Şahin'), ('Ali', 'Öztürk'), ('Zeynep', 'Kaya'),
            ('Mustafa', 'Aydın'), ('Elif', 'Arslan'), ('Hasan', 'Yıldız'),
            ('Emine', 'Koç'), ('Can', 'Kurt'), ('Selin', 'Özdemir'),
            ('Burak', 'Aksoy'), ('Deniz', 'Çetin'), ('Ece', 'Karataş')
        ]
        
        guests = []
        for first_name, last_name in turkish_names:
            email = f"{first_name.lower()}.{last_name.lower()}@email.com"
            guests.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'name': f"{first_name} {last_name}",
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': f"+90 5{random.randint(10, 99)} {random.randint(100, 999)} {random.randint(10, 99)} {random.randint(10, 99)}",
                'id_number': f'TR{random.randint(100000, 999999)}',
                'nationality': 'TR',
                'passport_number': f'TR{random.randint(100000, 999999)}',
                'date_of_birth': (datetime.now() - timedelta(days=random.randint(8000, 20000))).date().isoformat(),
                'address': 'İstanbul, Türkiye',
                'total_stays': random.randint(1, 10),
                'total_spend': round(random.uniform(500, 5000), 2),
                'vip_status': random.choice([True, False]),
                'preferences': {
                    'pillow_type': random.choice(['soft', 'firm']),
                    'floor_preference': random.choice(['low', 'high', 'any']),
                    'smoking': False
                },
                'created_at': datetime.now(timezone.utc).isoformat()
            })
        
        await self.db.guests.insert_many(guests)
        print(f"✓ Created {len(guests)} guests")
        return guests
    
    async def create_bookings(self, rooms, guests):
        """Create bookings (past, current, future) with realistic test data"""
        bookings = []
        now = datetime.now(timezone.utc)
        today = now.date()
        
        print(f"📅 Bugünün tarihi: {today.isoformat()}")
        
        # 1. BUGÜN GİRİŞ YAPACAK REZERVASYONLAR (6 adet)
        print("  → Bugün giriş yapacak rezervasyonlar oluşturuluyor...")
        available_rooms = [r for r in rooms if r['status'] == 'available'][:6]
        for i, room in enumerate(available_rooms):
            guest = guests[i]
            check_out = today + timedelta(days=random.randint(2, 7))
            nights = (check_out - today).days
            
            bookings.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'booking_number': f'BK{now.year}{7000 + i}',
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': today.isoformat(),
                'check_out': check_out.isoformat(),
                'status': 'confirmed',  # Giriş bekliyor
                'adults': random.randint(1, 2),
                'children': random.randint(0, 1),
                'guests_count': random.randint(1, 3),
                'total_amount': room['base_price'] * nights,
                'paid_amount': 0.0,
                'rate_code': random.choice(['BAR', 'ADVANCE', 'CORPORATE']),
                'source': random.choice(['Direct', 'Booking.com', 'Expedia']),
                'special_requests': random.choice(['Erken giriş talep edildi', 'Sessiz oda', 'Yüksek kat', '']),
                'created_at': (now - timedelta(days=random.randint(7, 30))).isoformat()
            })
        
        # 2. BUGÜN ÇIKIŞ YAPACAK REZERVASYONLAR (5 adet)
        print("  → Bugün çıkış yapacak rezervasyonlar oluşturuluyor...")
        occupied_rooms = [r for r in rooms if r['status'] == 'occupied'][:5]
        for i, room in enumerate(occupied_rooms):
            guest = guests[6 + i]
            check_in = today - timedelta(days=random.randint(2, 7))
            nights = (today - check_in).days
            
            booking_id = str(uuid.uuid4())
            bookings.append({
                'id': booking_id,
                'tenant_id': self.tenant_id,
                'booking_number': f'BK{now.year}{8000 + i}',
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': check_in.isoformat(),
                'check_out': today.isoformat(),
                'status': 'checked_in',  # Çıkış bekliyor
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'guests_count': random.randint(1, 3),
                'total_amount': room['base_price'] * nights,
                'paid_amount': round(room['base_price'] * nights * 0.8, 2),
                'rate_code': 'BAR',
                'source': random.choice(['Direct', 'Booking.com', 'Expedia']),
                'special_requests': random.choice(['Geç çıkış talep edildi', 'Taksi rezervasyonu', '']),
                'created_at': (check_in - timedelta(days=random.randint(10, 40))).isoformat()
            })
            
            # Update room with current booking
            await self.db.rooms.update_one(
                {'id': room['id']},
                {'$set': {'current_booking_id': booking_id, 'status': 'occupied'}}
            )
        
        # 3. YARIN GİRİŞ YAPACAK REZERVASYONLAR (4 adet)
        print("  → Yarın giriş yapacak rezervasyonlar oluşturuluyor...")
        tomorrow = today + timedelta(days=1)
        for i in range(4):
            guest = guests[11 + i]
            room = rooms[11 + i]
            check_out = tomorrow + timedelta(days=random.randint(2, 5))
            nights = (check_out - tomorrow).days
            
            bookings.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'booking_number': f'BK{now.year}{8100 + i}',
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': tomorrow.isoformat(),
                'check_out': check_out.isoformat(),
                'status': 'confirmed',
                'adults': random.randint(1, 2),
                'children': random.randint(0, 1),
                'guests_count': random.randint(1, 3),
                'total_amount': room['base_price'] * nights,
                'paid_amount': round(room['base_price'] * nights * 0.3, 2),
                'rate_code': random.choice(['BAR', 'ADVANCE']),
                'source': random.choice(['Direct', 'Booking.com']),
                'special_requests': '',
                'created_at': (now - timedelta(days=random.randint(5, 20))).isoformat()
            })
        
        # 4. 2-3 GÜN SONRA GİRİŞ YAPACAK REZERVASYONLAR (5 adet)
        print("  → 2-3 gün sonra giriş yapacak rezervasyonlar oluşturuluyor...")
        for i in range(5):
            guest = guests[15 + i] if 15 + i < len(guests) else random.choice(guests)
            room = rooms[15 + i] if 15 + i < len(rooms) else random.choice(rooms)
            check_in = today + timedelta(days=random.randint(2, 3))
            check_out = check_in + timedelta(days=random.randint(2, 5))
            nights = (check_out - check_in).days
            
            bookings.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'booking_number': f'BK{now.year}{8200 + i}',
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'status': 'guaranteed',
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'guests_count': random.randint(1, 3),
                'total_amount': room['base_price'] * nights,
                'paid_amount': room['base_price'] * nights * 0.5,
                'rate_code': random.choice(['ADVANCE', 'CORPORATE']),
                'source': random.choice(['Direct', 'Expedia', 'Phone']),
                'special_requests': random.choice(['', 'İş seyahati', 'Toplantı odası gerekli']),
                'created_at': (now - timedelta(days=random.randint(10, 30))).isoformat()
            })
        
        # 5. GELECEKTEKİ REZERVASYONLAR (1 hafta - 1 ay arası, 8 adet)
        print("  → Gelecekteki rezervasyonlar oluşturuluyor...")
        for i in range(8):
            guest = guests[20 + i] if 20 + i < len(guests) else random.choice(guests)
            room = rooms[20 + i] if 20 + i < len(rooms) else random.choice(rooms)
            check_in = today + timedelta(days=random.randint(7, 30))
            check_out = check_in + timedelta(days=random.randint(2, 7))
            nights = (check_out - check_in).days
            
            bookings.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'booking_number': f'BK{now.year}{8300 + i}',
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'status': random.choice(['confirmed', 'guaranteed']),
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'guests_count': random.randint(1, 3),
                'total_amount': room['base_price'] * nights,
                'paid_amount': 0.0 if random.random() < 0.5 else round(room['base_price'] * nights * 0.3, 2),
                'rate_code': random.choice(['BAR', 'ADVANCE', 'CORPORATE']),
                'source': random.choice(['Direct', 'Booking.com', 'Expedia', 'Phone']),
                'special_requests': random.choice(['', 'Balayı paketi', 'Yıl dönümü', 'Doğum günü']),
                'created_at': (now - timedelta(days=random.randint(1, 15))).isoformat()
            })
        
        # 6. ŞU AN KONAKLAYAN MİSAFİRLER (BUGÜN ÇIKMAYANLAR, 3 adet)
        print("  → Şu an konaklayan misafirler oluşturululuyor...")
        remaining_occupied = [r for r in rooms if r['status'] == 'occupied'][5:8]
        for i, room in enumerate(remaining_occupied):
            guest = guests[28 + i] if 28 + i < len(guests) else random.choice(guests)
            check_in = today - timedelta(days=random.randint(1, 3))
            check_out = today + timedelta(days=random.randint(2, 7))
            nights = (check_out - check_in).days
            
            booking_id = str(uuid.uuid4())
            bookings.append({
                'id': booking_id,
                'tenant_id': self.tenant_id,
                'booking_number': f'BK{now.year}{8400 + i}',
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'status': 'checked_in',
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'guests_count': random.randint(1, 3),
                'total_amount': room['base_price'] * nights,
                'paid_amount': round(room['base_price'] * nights * 0.5, 2),
                'rate_code': 'BAR',
                'source': random.choice(['Direct', 'Booking.com']),
                'special_requests': '',
                'created_at': (check_in - timedelta(days=random.randint(10, 40))).isoformat()
            })
            
            # Update room with current booking
            await self.db.rooms.update_one(
                {'id': room['id']},
                {'$set': {'current_booking_id': booking_id, 'status': 'occupied'}}
            )
        
        # 7. GEÇMİŞ REZERVASYONLAR (5 adet)
        print("  → Geçmiş rezervasyonlar oluşturuluyor...")
        for i in range(5):
            guest = random.choice(guests)
            room = random.choice(rooms)
            check_in = today - timedelta(days=random.randint(10, 60))
            check_out = check_in + timedelta(days=random.randint(2, 7))
            nights = (check_out - check_in).days
            
            bookings.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'booking_number': f'BK{now.year}{6000 + i}',
                'guest_id': guest['id'],
                'guest_name': guest['name'],
                'room_id': room['id'],
                'room_number': room['room_number'],
                'check_in': check_in.isoformat(),
                'check_out': check_out.isoformat(),
                'status': 'checked_out',
                'adults': random.randint(1, 2),
                'children': random.randint(0, 2),
                'guests_count': random.randint(1, 3),
                'total_amount': room['base_price'] * nights,
                'paid_amount': room['base_price'] * nights,
                'rate_code': 'BAR',
                'source': random.choice(['Direct', 'Booking.com', 'Expedia', 'Walk-in']),
                'special_requests': '',
                'created_at': (check_in - timedelta(days=random.randint(5, 30))).isoformat()
            })
        
        await self.db.bookings.insert_many(bookings)
        
        # Özet yazdır
        print(f"\n✓ TOPLAM {len(bookings)} REZERVASYON OLUŞTURULDU:")
        print("  📥 Bugün giriş: 6 adet")
        print("  📤 Bugün çıkış: 5 adet")
        print("  📅 Yarın giriş: 4 adet")
        print("  📅 2-3 gün sonra: 5 adet")
        print("  📆 Gelecek (1 hafta - 1 ay): 8 adet")
        print("  🏨 Şu an konaklayan: 3 adet")
        print("  ✅ Geçmiş: 5 adet")
        
        return bookings
    
    async def create_folios(self, bookings):
        """Create folios for checked-in bookings"""
        folios = []
        folio_charges = []
        
        checked_in_bookings = [b for b in bookings if b['status'] == 'checked_in']
        
        for booking in checked_in_bookings:
            # Create guest folio
            folio_id = str(uuid.uuid4())
            folio_number = f"F-{datetime.now().year}-{random.randint(10000, 99999)}"
            
            folios.append({
                'id': folio_id,
                'tenant_id': self.tenant_id,
                'folio_number': folio_number,
                'booking_id': booking['id'],
                'guest_id': booking['guest_id'],
                'folio_type': 'guest',
                'status': 'open',
                'balance': round(random.uniform(100, 500), 2),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'closed_at': None
            })
            
            # Add room charges
            check_in_date = datetime.fromisoformat(booking['check_in']).date() if isinstance(booking['check_in'], str) else booking['check_in']
            nights_stayed = (datetime.now().date() - check_in_date).days
            for night in range(max(1, nights_stayed)):
                folio_charges.append({
                    'id': str(uuid.uuid4()),
                    'tenant_id': self.tenant_id,
                    'folio_id': folio_id,
                    'booking_id': booking['id'],
                    'charge_date': (datetime.now() - timedelta(days=nights_stayed - night)).date().isoformat(),
                    'charge_category': 'room',
                    'description': f"Room Charge - Night {night + 1}",
                    'quantity': 1,
                    'unit_price': booking['total_amount'] / max(1, (datetime.fromisoformat(booking['check_out']).date() - datetime.fromisoformat(booking['check_in']).date()).days),
                    'amount': booking['total_amount'] / max(1, (datetime.fromisoformat(booking['check_out']).date() - datetime.fromisoformat(booking['check_in']).date()).days),
                    'tax_amount': 0.0,
                    'total': booking['total_amount'] / max(1, (datetime.fromisoformat(booking['check_out']).date() - datetime.fromisoformat(booking['check_in']).date()).days),
                    'voided': False,
                    'posted_by': 'System',
                    'created_at': datetime.now(timezone.utc).isoformat()
                })
            
            # Add F&B charges
            if random.random() > 0.5:
                folio_charges.append({
                    'id': str(uuid.uuid4()),
                    'tenant_id': self.tenant_id,
                    'folio_id': folio_id,
                    'booking_id': booking['id'],
                    'charge_date': datetime.now().date().isoformat(),
                    'charge_category': 'food',
                    'description': 'Restaurant - Breakfast',
                    'quantity': 2,
                    'unit_price': 25.0,
                    'amount': 50.0,
                    'tax_amount': 9.0,
                    'total': 59.0,
                    'voided': False,
                    'posted_by': 'POS System',
                    'created_at': datetime.now(timezone.utc).isoformat()
                })
            
            # Add minibar charges
            if random.random() > 0.6:
                folio_charges.append({
                    'id': str(uuid.uuid4()),
                    'tenant_id': self.tenant_id,
                    'folio_id': folio_id,
                    'booking_id': booking['id'],
                    'charge_date': datetime.now().date().isoformat(),
                    'charge_category': 'minibar',
                    'description': 'Minibar - Beverages',
                    'quantity': 1,
                    'unit_price': 35.0,
                    'amount': 35.0,
                    'tax_amount': 6.3,
                    'total': 41.3,
                    'voided': False,
                    'posted_by': 'Housekeeping',
                    'created_at': datetime.now(timezone.utc).isoformat()
                })
        
        if folios:
            await self.db.folios.insert_many(folios)
            print(f"✓ Created {len(folios)} folios")
        
        if folio_charges:
            await self.db.folio_charges.insert_many(folio_charges)
            print(f"✓ Created {len(folio_charges)} folio charges")
        
        return folios
    
    async def create_housekeeping_tasks(self, rooms):
        """Create housekeeping tasks"""
        tasks = []
        staff_names = ['Fatma', 'Ayşe', 'Zeynep', 'Elif', 'Emine']
        
        dirty_rooms = [r for r in rooms if r['status'] in ['dirty', 'cleaning']]
        
        for room in dirty_rooms[:15]:
            tasks.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'room_id': room['id'],
                'room_number': room['room_number'],
                'task_type': 'cleaning',
                'status': random.choice(['pending', 'in_progress', 'completed']),
                'priority': random.choice(['low', 'normal', 'high']),
                'assigned_to': random.choice(staff_names),
                'assigned_at': (datetime.now() - timedelta(hours=random.randint(0, 8))).isoformat(),
                'started_at': (datetime.now() - timedelta(hours=random.randint(0, 4))).isoformat() if random.random() > 0.5 else None,
                'completed_at': None,
                'notes': random.choice(['', 'Extra cleaning required', 'Guest requested deep clean']),
                'created_at': datetime.now(timezone.utc).isoformat()
            })
        
        if tasks:
            await self.db.housekeeping_tasks.insert_many(tasks)
            print(f"✓ Created {len(tasks)} housekeeping tasks")
        
        return tasks
    
    async def create_pos_data(self):
        """Create POS menu items and orders"""
        menu_items = [
            {'name': 'Türk Kahvesi', 'category': 'beverage', 'price': 25.0},
            {'name': 'Cappuccino', 'category': 'beverage', 'price': 30.0},
            {'name': 'Çay', 'category': 'beverage', 'price': 15.0},
            {'name': 'Menemen', 'category': 'food', 'price': 45.0},
            {'name': 'Serpme Kahvaltı', 'category': 'food', 'price': 120.0},
            {'name': 'İzgara Köfte', 'category': 'food', 'price': 85.0},
            {'name': 'Karışık Izgara', 'category': 'food', 'price': 150.0},
            {'name': 'Salata', 'category': 'food', 'price': 35.0},
            {'name': 'Baklava', 'category': 'dessert', 'price': 40.0},
            {'name': 'Künefe', 'category': 'dessert', 'price': 50.0},
            {'name': 'Rakı', 'category': 'alcohol', 'price': 180.0},
            {'name': 'Şarap (Şişe)', 'category': 'alcohol', 'price': 250.0}
        ]
        
        items = []
        for item_data in menu_items:
            items.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'name': item_data['name'],
                'category': item_data['category'],
                'price': item_data['price'],
                'cost': round(item_data['price'] * 0.4, 2),
                'is_active': True,
                'description': '',
                'created_at': datetime.now(timezone.utc).isoformat()
            })
        
        await self.db.pos_menu_items.insert_many(items)
        print(f"✓ Created {len(items)} menu items")
        return items
    
    async def create_feedback(self, guests):
        """Create guest feedback and reviews"""
        feedback_list = []
        comments_positive = [
            'Harika bir konaklama deneyimi yaşadık!',
            'Personel çok ilgili ve yardımcı.',
            'Odalar tertemiz ve konforlu.',
            'Kahvaltı muhteşemdi!',
            'Kesinlikle tekrar geleceğiz.'
        ]
        comments_negative = [
            'WiFi biraz yavaştı.',
            'Odada klima gürültülüydü.',
            'Kahvaltı çeşitliliği artırılabilir.',
            'Check-in süreci biraz uzun sürdü.'
        ]
        
        for guest in random.sample(guests, min(20, len(guests))):
            is_positive = random.random() > 0.3
            rating = random.randint(4, 5) if is_positive else random.randint(2, 3)
            
            feedback_list.append({
                'id': str(uuid.uuid4()),
                'tenant_id': self.tenant_id,
                'guest_id': guest['id'],
                'rating': rating,
                'comment': random.choice(comments_positive if is_positive else comments_negative),
                'sentiment': 'positive' if is_positive else 'negative',
                'category': random.choice(['overall', 'cleanliness', 'service', 'food']),
                'source': random.choice(['Direct', 'Google', 'TripAdvisor', 'Booking.com']),
                'created_at': (datetime.now() - timedelta(days=random.randint(0, 30))).isoformat()
            })
        
        if feedback_list:
            await self.db.feedback.insert_many(feedback_list)
            print(f"✓ Created {len(feedback_list)} feedback entries")
        
        return feedback_list
    
    async def seed_all(self):
        """Seed all data"""
        print("\n🌱 Starting Hotel PMS Database Seeding...")
        print("=" * 50)
        
        try:
            # Clear existing data
            await self.clear_database()
            
            # Create data in order
            users = await self.create_users()
            rooms = await self.create_rooms()
            guests = await self.create_guests()
            bookings = await self.create_bookings(rooms, guests)
            folios = await self.create_folios(bookings)
            tasks = await self.create_housekeeping_tasks(rooms)
            menu_items = await self.create_pos_data()
            feedback = await self.create_feedback(guests)
            
            print("=" * 50)
            print("✅ Database seeding completed successfully!")
            print("\n📊 Summary:")
            print(f"  - Users: {len(users)}")
            print(f"  - Rooms: {len(rooms)}")
            print(f"  - Guests: {len(guests)}")
            print(f"  - Bookings: {len(bookings)}")
            print(f"  - Folios: {len(folios)}")
            print(f"  - Housekeeping Tasks: {len(tasks)}")
            print(f"  - Menu Items: {len(menu_items)}")
            print(f"  - Feedback: {len(feedback)}")
            print("\n🔐 Login Credentials:")
            print("  Admin: admin@hotel.com / admin123")
            print("  Front Desk: frontdesk@hotel.com / frontdesk123")
            print("  Housekeeping: housekeeping@hotel.com / housekeeping123")
            print("  Finance: finance@hotel.com / finance123")
            print("\n")
            
        except Exception as e:
            print(f"❌ Error during seeding: {str(e)}")
            raise
        finally:
            self.client.close()

async def main():
    seeder = HotelSeeder()
    await seeder.seed_all()

if __name__ == '__main__':
    asyncio.run(main())
