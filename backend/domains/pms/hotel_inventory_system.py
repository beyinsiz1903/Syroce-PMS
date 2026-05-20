"""
Hotel Inventory Management System
Helpers for inventory reorder suggestions.

The legacy automatic stock-deduction helpers (``deduct_room_amenities`` and
``calculate_amenity_consumption``) were retired because they performed
non-atomic read-then-write decrements without ``tenant_id`` scoping, which
allowed concurrent underflow below zero and cross-tenant stock mutation if an
item id ever leaked. They had no production callers (see Task #211). Use the
inventory movement endpoints, which apply atomic, tenant-scoped guards, for
any stock deduction.
"""

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

async def get_suggested_orders(db, tenant_id: str) -> list[dict]:
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
