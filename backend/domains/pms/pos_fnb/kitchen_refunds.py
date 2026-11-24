"""Read-only compatibility for old refunded checks left in the kitchen queue."""
from fastapi import HTTPException


async def actionable_kitchen_orders(database, tenant_id, rows):
    ids = list({row['order_id'] for row in rows if row.get('order_id')})
    if not ids:
        return rows
    refunds = {row['id'] async for row in database.pos_orders.find(
        {'tenant_id': tenant_id, 'id': {'$in': ids}, 'payment_status': 'refunded'}, {'_id': 0, 'id': 1})}
    # Never rewrite historical tickets during a read. Preparing/served food is
    # not automatically undone by a monetary refund; keep its real lifecycle.
    return [{**row, **({'financial_refund_status': 'full'} if row.get('order_id') in refunds else {})}
            for row in rows if not (row.get('status') == 'pending' and row.get('order_id') in refunds)]


async def reject_refunded_pending(database, tenant_id, ticket):
    if ticket.get('status') != 'pending' or not ticket.get('order_id'):
        return
    order = await database.pos_orders.find_one(
        {'tenant_id': tenant_id, 'id': ticket['order_id'], 'payment_status': 'refunded'}, {'_id': 0, 'id': 1})
    if order:
        raise HTTPException(409, 'Adisyonun tamamı iade edildi; hazırlanmasına başlanamaz. Listeyi yenileyin.')
