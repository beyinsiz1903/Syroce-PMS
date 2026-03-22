#!/usr/bin/env python3
"""
Demo Data Generator for F&B Mobile Features
Creates comprehensive F&B data including outlets, orders, recipes, ingredients, and stock consumption
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import uuid
import random

# MongoDB connection
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "hotel_pms"

async def create_demo_data():
    """Create demo data for F&B features"""
    
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print("🍽️  Creating F&B Demo Data...")
    
    # Get first tenant
    tenant = await db.tenants.find_one()
    if not tenant:
        print("❌ No tenant found. Please register a tenant first.")
        return
    
    tenant_id = tenant['id']
    print(f"✅ Using tenant: {tenant.get('hotel_name', 'Unknown')}")
    
    # 1. Create Outlets
    print("\n🏪 Creating Outlets...")
    
    outlets = [
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Main Restaurant',
            'outlet_type': 'restaurant',
            'department': 'F&B',
            'location': 'Ground Floor',
            'capacity': 80,
            'is_active': True,
            'opening_time': '07:00',
            'closing_time': '23:00',
            'contact_phone': '+90 212 555 1111',
            'manager': 'Ahmet Yılmaz',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Lobby Bar',
            'outlet_type': 'bar',
            'department': 'F&B',
            'location': 'Lobby Level',
            'capacity': 40,
            'is_active': True,
            'opening_time': '10:00',
            'closing_time': '02:00',
            'contact_phone': '+90 212 555 1112',
            'manager': 'Ayşe Demir',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Room Service',
            'outlet_type': 'room_service',
            'department': 'F&B',
            'location': 'Central Kitchen',
            'capacity': 999,
            'is_active': True,
            'opening_time': '00:00',
            'closing_time': '23:59',
            'contact_phone': '+90 212 555 1113',
            'manager': 'Mehmet Kaya',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': 'Pool Bar',
            'outlet_type': 'poolside',
            'department': 'F&B',
            'location': 'Pool Area',
            'capacity': 30,
            'is_active': True,
            'opening_time': '09:00',
            'closing_time': '20:00',
            'contact_phone': '+90 212 555 1114',
            'manager': 'Fatma Öz',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
    ]
    
    await db.outlets.delete_many({'tenant_id': tenant_id})
    await db.outlets.insert_many(outlets)
    print(f"✅ Created {len(outlets)} outlets")
    
    # 2. Create Ingredients
    print("\n🥗 Creating Ingredients...")
    
    ingredients = [
        # Meat & Protein
        {'name': 'Tavuk Göğsü', 'category': 'Meat', 'unit': 'kg', 'current_stock': 25.0, 'minimum_stock': 10.0, 'unit_cost': 45.00, 'supplier': 'Et Deposu Ltd.'},
        {'name': 'Dana Eti', 'category': 'Meat', 'unit': 'kg', 'current_stock': 15.0, 'minimum_stock': 8.0, 'unit_cost': 120.00, 'supplier': 'Et Deposu Ltd.'},
        {'name': 'Somon Balığı', 'category': 'Seafood', 'unit': 'kg', 'current_stock': 8.0, 'minimum_stock': 5.0, 'unit_cost': 180.00, 'supplier': 'Deniz Ürünleri A.Ş.'},
        
        # Vegetables
        {'name': 'Domates', 'category': 'Vegetables', 'unit': 'kg', 'current_stock': 40.0, 'minimum_stock': 20.0, 'unit_cost': 8.00, 'supplier': 'Taze Sebze Pazarı'},
        {'name': 'Soğan', 'category': 'Vegetables', 'unit': 'kg', 'current_stock': 30.0, 'minimum_stock': 15.0, 'unit_cost': 5.00, 'supplier': 'Taze Sebze Pazarı'},
        {'name': 'Patates', 'category': 'Vegetables', 'unit': 'kg', 'current_stock': 50.0, 'minimum_stock': 25.0, 'unit_cost': 6.00, 'supplier': 'Taze Sebze Pazarı'},
        {'name': 'Salata Yeşilliği', 'category': 'Vegetables', 'unit': 'kg', 'current_stock': 12.0, 'minimum_stock': 8.0, 'unit_cost': 15.00, 'supplier': 'Taze Sebze Pazarı'},
        
        # Dairy
        {'name': 'Süt', 'category': 'Dairy', 'unit': 'liter', 'current_stock': 60.0, 'minimum_stock': 30.0, 'unit_cost': 12.00, 'supplier': 'Süt Fabrikası'},
        {'name': 'Kaşar Peyniri', 'category': 'Dairy', 'unit': 'kg', 'current_stock': 8.0, 'minimum_stock': 5.0, 'unit_cost': 95.00, 'supplier': 'Süt Fabrikası'},
        {'name': 'Tereyağı', 'category': 'Dairy', 'unit': 'kg', 'current_stock': 10.0, 'minimum_stock': 5.0, 'unit_cost': 85.00, 'supplier': 'Süt Fabrikası'},
        
        # Beverages
        {'name': 'Kahve Çekirdeği', 'category': 'Beverages', 'unit': 'kg', 'current_stock': 15.0, 'minimum_stock': 10.0, 'unit_cost': 220.00, 'supplier': 'Kahve Dünyası'},
        {'name': 'Çay (Demlik)', 'category': 'Beverages', 'unit': 'kg', 'current_stock': 20.0, 'minimum_stock': 10.0, 'unit_cost': 65.00, 'supplier': 'Çaykur'},
        {'name': 'Portakal Suyu', 'category': 'Beverages', 'unit': 'liter', 'current_stock': 40.0, 'minimum_stock': 25.0, 'unit_cost': 18.00, 'supplier': 'Meyve Suları A.Ş.'},
        
        # Pantry
        {'name': 'Makarna', 'category': 'Pantry', 'unit': 'kg', 'current_stock': 35.0, 'minimum_stock': 20.0, 'unit_cost': 15.00, 'supplier': 'Gıda Market'},
        {'name': 'Pirinç', 'category': 'Pantry', 'unit': 'kg', 'current_stock': 45.0, 'minimum_stock': 25.0, 'unit_cost': 18.00, 'supplier': 'Gıda Market'},
        {'name': 'Zeytinyağı', 'category': 'Pantry', 'unit': 'liter', 'current_stock': 25.0, 'minimum_stock': 15.0, 'unit_cost': 75.00, 'supplier': 'Zeytin İşleme A.Ş.'},
        
        # Low stock items (critical)
        {'name': 'Yumurta', 'category': 'Dairy', 'unit': 'piece', 'current_stock': 80.0, 'minimum_stock': 200.0, 'unit_cost': 2.50, 'supplier': 'Çiftlik Ürünleri'},
        {'name': 'Ekmek', 'category': 'Bakery', 'unit': 'piece', 'current_stock': 30.0, 'minimum_stock': 100.0, 'unit_cost': 3.00, 'supplier': 'Fırın'},
    ]
    
    ingredient_docs = []
    for ing in ingredients:
        ingredient_docs.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'name': ing['name'],
            'category': ing['category'],
            'unit': ing['unit'],
            'current_stock': ing['current_stock'],
            'minimum_stock': ing['minimum_stock'],
            'unit_cost': ing['unit_cost'],
            'supplier': ing['supplier'],
            'storage_location': 'main_kitchen',
            'last_restocked': datetime.now(timezone.utc) - timedelta(days=random.randint(1, 7)),
            'expiry_date': datetime.now(timezone.utc) + timedelta(days=random.randint(7, 30)) if ing['category'] in ['Meat', 'Seafood', 'Dairy'] else None,
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        })
    
    await db.ingredients.delete_many({'tenant_id': tenant_id})
    await db.ingredients.insert_many(ingredient_docs)
    print(f"✅ Created {len(ingredient_docs)} ingredients (2 low stock)")
    
    # 3. Create Recipes
    print("\n📖 Creating Recipes...")
    
    recipes = [
        {
            'menu_item_name': 'Izgara Tavuk',
            'ingredients': [
                {'ingredient_name': 'Tavuk Göğsü', 'quantity': 0.25, 'unit': 'kg', 'cost': 11.25},
                {'ingredient_name': 'Zeytinyağı', 'quantity': 0.02, 'unit': 'liter', 'cost': 1.50},
                {'ingredient_name': 'Salata Yeşilliği', 'quantity': 0.05, 'unit': 'kg', 'cost': 0.75}
            ],
            'preparation_time_minutes': 20,
            'selling_price': 85.00
        },
        {
            'menu_item_name': 'Spagetti Carbonara',
            'ingredients': [
                {'ingredient_name': 'Makarna', 'quantity': 0.15, 'unit': 'kg', 'cost': 2.25},
                {'ingredient_name': 'Kaşar Peyniri', 'quantity': 0.05, 'unit': 'kg', 'cost': 4.75},
                {'ingredient_name': 'Yumurta', 'quantity': 2.0, 'unit': 'piece', 'cost': 5.00},
                {'ingredient_name': 'Tereyağı', 'quantity': 0.02, 'unit': 'kg', 'cost': 1.70}
            ],
            'preparation_time_minutes': 15,
            'selling_price': 75.00
        },
        {
            'menu_item_name': 'Somon Izgara',
            'ingredients': [
                {'ingredient_name': 'Somon Balığı', 'quantity': 0.20, 'unit': 'kg', 'cost': 36.00},
                {'ingredient_name': 'Zeytinyağı', 'quantity': 0.01, 'unit': 'liter', 'cost': 0.75},
                {'ingredient_name': 'Patates', 'quantity': 0.15, 'unit': 'kg', 'cost': 0.90}
            ],
            'preparation_time_minutes': 25,
            'selling_price': 145.00
        }
    ]
    
    recipe_docs = []
    for recipe in recipes:
        total_cost = sum(ing['cost'] for ing in recipe['ingredients'])
        profit_margin = ((recipe['selling_price'] - total_cost) / recipe['selling_price'] * 100) if recipe['selling_price'] > 0 else 0
        
        recipe_docs.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'menu_item_id': str(uuid.uuid4()),
            'menu_item_name': recipe['menu_item_name'],
            'ingredients': recipe['ingredients'],
            'preparation_time_minutes': recipe['preparation_time_minutes'],
            'serving_size': 1,
            'total_cost': total_cost,
            'selling_price': recipe['selling_price'],
            'profit_margin': profit_margin,
            'created_by': 'admin@hotel.com',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        })
    
    await db.recipes.delete_many({'tenant_id': tenant_id})
    await db.recipes.insert_many(recipe_docs)
    print(f"✅ Created {len(recipe_docs)} recipes")
    
    # 4. Create POS Orders
    print("\n📱 Creating POS Orders...")
    
    order_statuses = ['pending', 'preparing', 'ready', 'served', 'served']  # More served for realism
    menu_items = [
        {'name': 'Izgara Tavuk', 'price': 85.00},
        {'name': 'Spagetti Carbonara', 'price': 75.00},
        {'name': 'Somon Izgara', 'price': 145.00},
        {'name': 'Türk Kahvesi', 'price': 25.00},
        {'name': 'Taze Sıkılmış Portakal Suyu', 'price': 35.00},
        {'name': 'Caesar Salata', 'price': 55.00},
        {'name': 'Patates Kızartması', 'price': 30.00}
    ]
    
    orders = []
    today = datetime.now(timezone.utc)
    
    for i in range(25):  # Create 25 orders
        outlet = random.choice(outlets)
        order_time = today - timedelta(hours=random.randint(0, 12), minutes=random.randint(0, 59))
        
        # Random items for order
        num_items = random.randint(1, 4)
        order_items = []
        subtotal = 0.0
        
        for _ in range(num_items):
            item = random.choice(menu_items)
            quantity = random.randint(1, 2)
            item_total = item['price'] * quantity
            subtotal += item_total
            
            order_items.append({
                'name': item['name'],
                'quantity': quantity,
                'unit_price': item['price'],
                'total': item_total
            })
        
        tax = subtotal * 0.18
        service_charge = subtotal * 0.10
        total = subtotal + tax + service_charge
        
        status = random.choice(order_statuses)
        
        order = {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'order_number': f'ORD-{10000 + i}',
            'outlet_id': outlet['id'],
            'outlet_name': outlet['name'],
            'table_number': f'T-{random.randint(1, 20)}' if outlet['outlet_type'] == 'restaurant' else None,
            'room_number': f'{random.randint(101, 350)}' if outlet['outlet_type'] == 'room_service' else None,
            'order_type': 'dine_in' if outlet['outlet_type'] in ['restaurant', 'bar'] else 'room_service',
            'items': order_items,
            'subtotal': subtotal,
            'tax': tax,
            'service_charge': service_charge,
            'total': total,
            'status': status,
            'waiter': random.choice(['Ali', 'Ayşe', 'Mehmet', 'Fatma', 'Ahmet']),
            'chef': random.choice(['Chef Kemal', 'Chef Zeynep', 'Chef Mustafa']),
            'created_at': order_time,
            'started_at': order_time + timedelta(minutes=2) if status in ['preparing', 'ready', 'served'] else None,
            'ready_at': order_time + timedelta(minutes=random.randint(15, 30)) if status in ['ready', 'served'] else None,
            'served_at': order_time + timedelta(minutes=random.randint(35, 50)) if status == 'served' else None,
            'notes': 'Demo order' if i % 5 == 0 else None
        }
        
        orders.append(order)
    
    await db.pos_orders.delete_many({'tenant_id': tenant_id})
    await db.pos_orders.insert_many(orders)
    print(f"✅ Created {len(orders)} POS orders")
    
    # 5. Create Stock Consumption Records
    print("\n📊 Creating Stock Consumption Records...")
    
    consumptions = []
    
    for i in range(40):  # 40 consumption records
        outlet = random.choice(outlets)
        ingredient = random.choice(ingredient_docs)
        consumed_time = today - timedelta(hours=random.randint(0, 48))
        
        consumed_qty = round(random.uniform(0.5, 5.0), 2)
        cost = consumed_qty * ingredient['unit_cost']
        
        consumptions.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'ingredient_id': ingredient['id'],
            'ingredient_name': ingredient['name'],
            'consumed_quantity': consumed_qty,
            'unit': ingredient['unit'],
            'outlet_id': outlet['id'],
            'outlet_name': outlet['name'],
            'cost': cost,
            'consumed_at': consumed_time,
            'recorded_by': 'admin@hotel.com'
        })
    
    await db.stock_consumption.delete_many({'tenant_id': tenant_id})
    await db.stock_consumption.insert_many(consumptions)
    print(f"✅ Created {len(consumptions)} stock consumption records")
    
    print("\n✅ F&B Demo data creation complete!")
    print("\n📊 Summary:")
    print(f"   - Outlets: {len(outlets)}")
    print(f"   - Ingredients: {len(ingredient_docs)} (2 low stock)")
    print(f"   - Recipes: {len(recipe_docs)}")
    print(f"   - POS Orders: {len(orders)}")
    print(f"   - Stock Consumptions: {len(consumptions)}")
    print("\n🎉 You can now test the F&B Mobile features!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_demo_data())
