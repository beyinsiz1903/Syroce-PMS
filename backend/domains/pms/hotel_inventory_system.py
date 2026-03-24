"""
Hotel Inventory Management System
Automatic stock deduction for room amenities based on guest count
"""

from typing import Dict, List
import uuid
from datetime import datetime, timezone

# Room amenity consumption rules - per guest
AMENITY_CONSUMPTION_RULES = {
    # Single-use items (per guest)
    "single_use": {
        "Şampuan": {"quantity_per_guest": 1, "unit": "adet"},
        "Duş Jeli": {"quantity_per_guest": 1, "unit": "adet"},
        "Terlik": {"quantity_per_guest": 1, "unit": "çift"},
        "Islak Mendil": {"quantity_per_guest": 2, "unit": "paket"},
        "Diş Fırçası": {"quantity_per_guest": 1, "unit": "adet"},
        "Tıraş Seti": {"quantity_per_guest": 0.5, "unit": "adet"},  # Not all guests
        "Duş Bonesi": {"quantity_per_guest": 1, "unit": "adet"},
        "Sabun": {"quantity_per_guest": 2, "unit": "adet"},
        "Kulak Çubuğu": {"quantity_per_guest": 1, "unit": "paket"},
    },
    
    # Room-based items (per room, not per guest)
    "room_based": {
        "Çarşaf Takımı": {"quantity_per_room": 1, "unit": "takım"},
        "Havlu Seti": {"quantity_per_guest": 1, "unit": "takım"},  # Per guest
        "Yüz Havlusu": {"quantity_per_guest": 2, "unit": "adet"},
        "El Havlusu": {"quantity_per_guest": 2, "unit": "adet"},
        "Bornoz": {"quantity_per_guest": 1, "unit": "adet"},
        "Yastık": {"quantity_per_guest": 2, "unit": "adet"},
        "Battaniye": {"quantity_per_room": 2, "unit": "adet"},
        "Yatak Örtüsü": {"quantity_per_room": 1, "unit": "adet"},
    },
    
    # Cleaning supplies (per room)
    "cleaning": {
        "Tuvalet Kağıdı": {"quantity_per_room": 4, "unit": "rulo"},
        "Kağıt Havlu": {"quantity_per_room": 2, "unit": "rulo"},
        "Çöp Poşeti": {"quantity_per_room": 3, "unit": "adet"},
        "Deterjan": {"quantity_per_room": 0.1, "unit": "litre"},
        "Cam Temizleyici": {"quantity_per_room": 0.05, "unit": "litre"},
    }
}

# Critical stock levels (minimum quantity before alert)
CRITICAL_STOCK_LEVELS = {
    "Şampuan": 50,
    "Duş Jeli": 50,
    "Terlik": 30,
    "Islak Mendil": 40,
    "Çarşaf Takımı": 20,
    "Havlu Seti": 25,
    "Tuvalet Kağıdı": 100,
    "Sabun": 60,
    "Bornoz": 15,
}

async def calculate_amenity_consumption(guest_count: int, room_type: str = "standard") -> Dict[str, float]:
    """
    Calculate amenity consumption based on guest count
    
    Args:
        guest_count: Number of guests in the room
        room_type: Type of room (affects consumption)
    
    Returns:
        Dictionary of item names and quantities to deduct
    """
    consumption = {}
    
    # Single-use items (per guest)
    for item, rule in AMENITY_CONSUMPTION_RULES["single_use"].items():
        consumption[item] = rule["quantity_per_guest"] * guest_count
    
    # Room-based items (per guest for some, per room for others)
    for item, rule in AMENITY_CONSUMPTION_RULES["room_based"].items():
        if "quantity_per_guest" in rule:
            consumption[item] = rule["quantity_per_guest"] * guest_count
        else:
            consumption[item] = rule["quantity_per_room"]
    
    # Cleaning supplies (per room)
    for item, rule in AMENITY_CONSUMPTION_RULES["cleaning"].items():
        consumption[item] = rule["quantity_per_room"]
    
    return consumption

async def deduct_room_amenities(db, tenant_id: str, guest_count: int, room_type: str, booking_id: str, user_name: str):
    """
    Deduct room amenities from inventory after check-in
    
    Args:
        db: Database connection
        tenant_id: Hotel tenant ID
        guest_count: Number of guests
        room_type: Room type
        booking_id: Booking reference
        user_name: User performing check-in
    
    Returns:
        Dictionary with deduction results and alerts
    """
    consumption = await calculate_amenity_consumption(guest_count, room_type)
    
    results = {
        "deducted_items": [],
        "failed_items": [],
        "low_stock_alerts": [],
        "out_of_stock_alerts": []
    }
    
    for item_name, quantity in consumption.items():
        # Find inventory item
        inventory_item = await db.inventory_items.find_one({
            'tenant_id': tenant_id,
            'name': item_name
        })
        
        if not inventory_item:
            results["failed_items"].append({
                "item": item_name,
                "reason": "Item not found in inventory",
                "quantity": quantity
            })
            continue
        
        current_stock = inventory_item.get('quantity', 0)
        
        # Check if enough stock
        if current_stock < quantity:
            results["out_of_stock_alerts"].append({
                "item": item_name,
                "required": quantity,
                "available": current_stock,
                "shortage": quantity - current_stock
            })
            # Deduct what's available
            quantity = current_stock
        
        if quantity > 0:
            # Deduct from inventory
            await db.inventory_items.update_one(
                {'id': inventory_item['id']},
                {'$inc': {'quantity': -quantity}}
            )
            
            # Create stock movement record
            movement = {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'item_id': inventory_item['id'],
                'movement_type': 'out',
                'quantity': quantity,
                'unit_cost': inventory_item.get('unit_cost', 0),
                'reference': f"Check-in: {booking_id}",
                'notes': f"Auto deduction for {guest_count} guests",
                'created_by': user_name,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            await db.stock_movements.insert_one(movement)
            
            # Check critical level
            new_stock = current_stock - quantity
            critical_level = CRITICAL_STOCK_LEVELS.get(item_name, 10)
            
            if new_stock <= critical_level:
                results["low_stock_alerts"].append({
                    "item": item_name,
                    "current_stock": new_stock,
                    "critical_level": critical_level,
                    "recommended_order": critical_level * 3  # Order 3x critical level
                })
            
            results["deducted_items"].append({
                "item": item_name,
                "quantity": quantity,
                "remaining_stock": new_stock
            })
    
    return results

async def get_suggested_orders(db, tenant_id: str) -> List[Dict]:
    """
    Get suggested orders for low stock items
    
    Returns:
        List of items that need to be ordered
    """
    items = await db.inventory_items.find({'tenant_id': tenant_id}, {'_id': 0}).to_list(1000)
    
    suggestions = []
    for item in items:
        current_stock = item.get('quantity', 0)
        reorder_level = item.get('reorder_level', 10)
        critical_level = CRITICAL_STOCK_LEVELS.get(item['name'], reorder_level)
        
        if current_stock <= critical_level:
            # Calculate suggested order quantity
            suggested_qty = max(critical_level * 3, reorder_level * 2)
            
            suggestions.append({
                "item_id": item['id'],
                "item_name": item['name'],
                "current_stock": current_stock,
                "critical_level": critical_level,
                "suggested_order_quantity": suggested_qty,
                "estimated_cost": suggested_qty * item.get('unit_cost', 0),
                "priority": "URGENT" if current_stock == 0 else "HIGH" if current_stock < critical_level / 2 else "MEDIUM"
            })
    
    # Sort by priority
    priority_order = {"URGENT": 0, "HIGH": 1, "MEDIUM": 2}
    suggestions.sort(key=lambda x: priority_order[x['priority']])
    
    return suggestions
