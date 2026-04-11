"""
Runtime Stress Tests — POS/F&B Mutation Burst
Simulates concurrent POS transactions, kitchen orders, and stock adjustments.
"""
import asyncio
import uuid
from datetime import datetime, timezone


async def test_pos_transaction_burst(db):
    """Burst 50 POS transactions concurrently and verify persistence."""
    tid = f"stress-pos-{uuid.uuid4().hex[:8]}"

    async def create_txn(idx):
        txn = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "amount": 25.0 + idx,
            "payment_method": "cash" if idx % 2 == 0 else "card",
            "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": f"staff-{idx % 5}",
        }
        await db.pos_transactions.insert_one(txn)
        return txn

    tasks = [create_txn(i) for i in range(50)]
    results = await asyncio.gather(*tasks)
    assert len(results) == 50

    count = await db.pos_transactions.count_documents({"tenant_id": tid})
    assert count == 50

    await db.pos_transactions.delete_many({"tenant_id": tid})


async def test_kitchen_order_concurrent_status_updates(db):
    """Multiple concurrent status transitions on the same order."""
    tid = f"stress-kitchen-{uuid.uuid4().hex[:8]}"
    order_id = str(uuid.uuid4())

    await db.kitchen_orders.insert_one({
        "id": order_id,
        "tenant_id": tid,
        "status": "new",
        "items": [{"name": "Burger", "qty": 2}],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    statuses = ["preparing", "ready", "served"]

    async def update_status(new_status, delay):
        await asyncio.sleep(delay * 0.01)
        await db.kitchen_orders.update_one(
            {"id": order_id, "tenant_id": tid},
            {"$set": {"status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )

    await asyncio.gather(*[update_status(s, i) for i, s in enumerate(statuses)])

    order = await db.kitchen_orders.find_one({"id": order_id}, {"_id": 0})
    assert order["status"] in statuses

    await db.kitchen_orders.delete_many({"tenant_id": tid})


async def test_stock_adjustment_race(db):
    """Concurrent stock decrease operations should not go below zero with proper checks."""
    tid = f"stress-stock-{uuid.uuid4().hex[:8]}"
    product_id = str(uuid.uuid4())

    await db.fnb_products.insert_one({
        "id": product_id,
        "tenant_id": tid,
        "name": "Premium Water",
        "stock_quantity": 10,
    })

    async def decrease_stock():
        product = await db.fnb_products.find_one({"id": product_id})
        if product and product.get("stock_quantity", 0) >= 1:
            await db.fnb_products.update_one(
                {"id": product_id, "stock_quantity": {"$gte": 1}},
                {"$inc": {"stock_quantity": -1}},
            )
            return True
        return False

    tasks = [decrease_stock() for _ in range(15)]
    await asyncio.gather(*tasks)

    product = await db.fnb_products.find_one({"id": product_id}, {"_id": 0})
    assert product["stock_quantity"] >= 0

    await db.fnb_products.delete_many({"tenant_id": tid})


async def test_table_reservation_contention(db):
    """Two guests trying to reserve the same table simultaneously."""
    tid = f"stress-table-{uuid.uuid4().hex[:8]}"
    table_id = str(uuid.uuid4())

    await db.pos_tables.insert_one({
        "id": table_id,
        "tenant_id": tid,
        "table_number": "T-01",
        "status": "available",
        "capacity": 4,
    })

    async def reserve_table(guest_name):
        table = await db.pos_tables.find_one({"id": table_id, "status": "available"})
        if table:
            result = await db.pos_tables.update_one(
                {"id": table_id, "status": "available"},
                {"$set": {"status": "reserved", "reserved_by": guest_name}},
            )
            return result.modified_count > 0
        return False

    r1, r2 = await asyncio.gather(reserve_table("Alice"), reserve_table("Bob"))

    table = await db.pos_tables.find_one({"id": table_id}, {"_id": 0})
    assert table["status"] == "reserved"
    assert table["reserved_by"] in ("Alice", "Bob")

    await db.pos_tables.delete_many({"tenant_id": tid})
