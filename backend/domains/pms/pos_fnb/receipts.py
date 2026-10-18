"""Private, server-snapshotted customer receipt (not a fiscal document)."""
from fastapi import HTTPException


async def receipt_payload(database, tenant_id, order_id):
    order = await database.pos_orders.find_one({'tenant_id': tenant_id, 'id': order_id}, {'_id': 0})
    sale = await database.pos_transactions.find_one({'tenant_id': tenant_id, 'order_id': order_id, 'status': 'completed'}, {'_id': 0})
    if not order or not sale:
        raise HTTPException(404, 'Kapatılmış adisyon bulunamadı.')
    settings = await database.hotel_settings.find_one({'tenant_id': tenant_id}, {'_id': 0, 'currency': 1, 'hotel_name': 1}) or {}
    quote = sale.get('checkout_quote') or {}
    return {
        'order_id': order_id, 'order_number': sale.get('order_number') or order.get('order_number') or order_id,
        'business_date': sale.get('transaction_date'), 'currency': quote.get('base_currency') or sale.get('currency') or settings.get('currency') or 'TRY',
        'header': settings.get('hotel_name') or 'SYROCE · Müşteri Hesap Fişi',
        'subheader': sale.get('order_number') or order.get('order_number') or order_id,
        'table': order.get('table_number'), 'payment_method': sale.get('payment_method'),
        'items': [{'name': row.get('item_name') or row.get('name') or 'Ürün', 'quantity': row.get('quantity', 1),
                   'price': row.get('unit_price', row.get('price', 0)), 'line_total': row.get('total', row.get('total_price', 0))}
                  for row in sale.get('order_items') or sale.get('items') or order.get('order_items') or []],
        'tax_amount': sale.get('tax_amount', 0), 'discount_amount': sale.get('discount_amount', 0),
        'service_charge_amount': sale.get('service_charge_amount', 0), 'tip_amount': sale.get('tip_amount', 0),
        'total': sale.get('total_amount', 0), 'refunded_amount': sale.get('refunded_amount', 0),
        'footer': 'Müşteri hesap fişidir. Mali belge değildir.',
    }
