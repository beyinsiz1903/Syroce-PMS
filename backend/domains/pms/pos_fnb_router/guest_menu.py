"""Public menu and signed-table ordering, backed by the canonical POS service."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError

from common.context import OperationContext
from core.database import db
from core.entitlement import require_tenant_module
from core.tenant_currency import get_tenant_currency
from core.tenant_db import tenant_context
from domains.pms.pos_extensions.pos_happy_hour import _apply_discount, _rule_matches, hotel_local_time
from domains.pms.pos_fnb.checkout_benefits import fingerprint
from domains.pms.pos_fnb.guest_qr import verify_table_token
from domains.pms.pos_fnb.pos_fnb_service_v2 import PosFnbServiceV2


async def public_tenant_scope(tenant_id: str):
    # No login authority is granted. Reads remain tenant-scoped, writes still
    # require the signed table capability below. Restore context on all exits.
    with tenant_context(tenant_id):
        yield


router = APIRouter(prefix='/api/public/fnb', tags=['guest_menu'], dependencies=[Depends(public_tenant_scope)])


class GuestOrderItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item_id: str = Field(min_length=1, max_length=128)
    quantity: int = Field(ge=1, le=100, strict=True)
    notes: str | None = Field(default=None, max_length=500)


class GuestOrderRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    table_id: str = Field(min_length=1, max_length=128)
    table_token: str = Field(min_length=1, max_length=2048)
    idempotency_key: str = Field(min_length=8, max_length=128)
    items: list[GuestOrderItem] = Field(min_length=1, max_length=50)
    guest_name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    expected_total: float | None = Field(default=None, ge=0, allow_inf_nan=False)


async def _active_outlet(tenant_id, outlet_id):
    await require_tenant_module(tenant_id, 'pos_fnb', 'Bu tesisin restoran sipariş kanalı aktif değil.')
    outlet = await db.pos_outlets.find_one({
        'tenant_id': tenant_id, 'id': outlet_id, 'is_active': {'$ne': False},
        'status': {'$nin': ['inactive', 'deleted', 'archived']},
    }, {'_id': 0, 'id': 1})
    if not outlet:
        raise HTTPException(404, 'Aktif satış noktası bulunamadı.')
    return outlet


@router.get('/{tenant_id}/{outlet_id}/menu')
async def get_guest_menu(tenant_id: str, outlet_id: str):
    await _active_outlet(tenant_id, outlet_id)
    items = await db.pos_menu_items.find({
        'tenant_id': tenant_id, 'outlet_id': outlet_id, 'is_active': {'$ne': False},
        'available': {'$ne': False}, 'status': {'$nin': ['inactive', 'deleted', 'archived']},
    }, {'_id': 0}).to_list(1000)
    currency, _ = await get_tenant_currency(tenant_id)
    now = await hotel_local_time(db, tenant_id, datetime.now(UTC))
    rules = await db.pos_happy_hour_rules.find({'tenant_id': tenant_id, 'active': True}, {'_id': 0}).sort('created_at', 1).to_list(200)
    categories = {}
    for item in items:
        if str(item.get('currency') or currency).upper() != currency:
            continue
        # A public endpoint must never expose internal cost, recipe, staffing
        # or accounting fields from the full menu document.
        price = float(item.get('unit_price', item.get('price', 0)))
        for rule in rules:
            if _rule_matches(rule, now, outlet_id, {'item_id': item['id'], 'category': item.get('category')}):
                price = _apply_discount(price, rule)
                break
        public = {key: item.get(key) for key in ('id', 'category', 'description', 'image_url')}
        public.update(item_name=item.get('item_name') or item.get('name') or 'Ürün', unit_price=price,
                      tax_rate=float(item.get('tax_rate', .10) or 0), currency=currency)
        categories.setdefault(item.get('category') or 'Diğer', []).append(public)
    return {'categories': [{'name': name, 'items': rows} for name, rows in categories.items()], 'currency': currency}


@router.post('/{tenant_id}/{outlet_id}/order')
async def place_guest_order(tenant_id: str, outlet_id: str, req: GuestOrderRequest):
    await _active_outlet(tenant_id, outlet_id)
    table = await db.table_layouts.find_one({'tenant_id': tenant_id, 'outlet_id': outlet_id, 'id': req.table_id}, {'_id': 0})
    if not table:
        raise HTTPException(404, 'Masa bulunamadı.')
    verify_table_token(req.table_token, tenant_id, outlet_id, table)
    key = 'guest-qr:' + fingerprint([tenant_id, outlet_id, req.table_id, req.idempotency_key])
    request_hash = fingerprint(req.model_dump(exclude={'table_token'}))
    # Persist the dispatch choice before calling the shared service. A retry
    # must not switch from 'create' to 'append' after the table was claimed.
    intent = {'_id': key, 'tenant_id': tenant_id, 'request_hash': request_hash,
              'order_id': table.get('current_order_id'), 'created_at': datetime.now(UTC)}
    try:
        await db.pos_guest_requests.insert_one(dict(intent))
    except DuplicateKeyError:
        intent = await db.pos_guest_requests.find_one({'_id': key, 'tenant_id': tenant_id})
        if not intent or intent['request_hash'] != request_hash:
            raise HTTPException(409, 'Sipariş anahtarı başka bir istek için kullanılmış.') from None
    for collection in (db.pos_orders, db.pos_order_item_batches):
        previous = await collection.find_one({'tenant_id': tenant_id, 'idempotency_key': key}, {'_id': 0})
        if previous:
            if previous.get('guest_request_hash') != request_hash:
                raise HTTPException(409, 'Sipariş anahtarı başka bir istek için kullanılmış.')
            return {'success': True, 'order_id': previous.get('order_id') or previous['id'], 'idempotent': True,
                    'message': 'Siparişiniz daha önce alındı; yeniden oluşturulmadı.'}
    # A copied physical QR must not allow unbounded kitchen spam. Replays
    # above do not consume the limit and another table has a separate budget.
    now = datetime.now(UTC)
    await db.pos_guest_limits.create_index('expires_at', expireAfterSeconds=0)
    bucket = fingerprint([tenant_id, outlet_id, table['id'], now.strftime('%Y%m%d%H%M')])
    try:
        await db.pos_guest_limits.update_one({'_id': bucket}, {'$setOnInsert': {
            'tenant_id': tenant_id, 'count': 0, 'expires_at': now + timedelta(minutes=2)}}, upsert=True)
    except DuplicateKeyError:
        pass  # Another request initialized the same minute's bucket.
    allowed = await db.pos_guest_limits.find_one_and_update({'_id': bucket, 'count': {'$lt': 10}}, {'$inc': {'count': 1}})
    if not allowed:
        raise HTTPException(429, 'Bu masa için kısa sürede çok sipariş alındı; bir dakika sonra tekrar deneyin.')
    service = PosFnbServiceV2()
    service._db = db
    # Public actors can only submit priced items to this signed table. There
    # is no public checkout/void/refund or access to private order details.
    ctx = OperationContext(tenant_id=tenant_id, actor_id='guest-qr:' + table['id'], actor_role='guest_qr')
    items = [{'item_id': item.item_id, 'quantity': item.quantity,
              'special_instructions': item.notes or req.notes} for item in req.items]
    if table.get('current_transaction_id'):
        raise HTTPException(409, 'Bu masanın eski adisyonuna personel üzerinden sipariş ekleyin.')
    if intent.get('order_id'):
        target = await db.pos_orders.find_one({'id': intent['order_id'], 'tenant_id': tenant_id,
            'outlet_id': outlet_id, 'table_number': str(table['table_number'])}, {'_id': 0, 'id': 1})
        if not target:
            raise HTTPException(409, 'Masanın adisyonu değişti; personelden yardım isteyin.')
        result = await service.add_order_items(ctx, intent['order_id'], items, key,
            guest_request_hash=request_hash, expected_table_number=str(table['table_number']), expected_total=req.expected_total)
        order_id = intent['order_id']
    else:
        result = await service.create_order(ctx, outlet_id, str(table['table_number']), items,
            guest_name=req.guest_name, idempotency_key=key, source='guest_qr',
            guest_request_hash=request_hash, expected_total=req.expected_total)
        order_id = (result.data or {}).get('order_id')
    if not result.ok:
        raise HTTPException(409 if result.code in {'PRICE_CHANGED', 'TABLE_UNAVAILABLE', 'ORDER_NOT_OPEN'} else 422, result.error)
    return {'success': True, 'order_id': order_id, 'idempotent': bool((result.data or {}).get('idempotent')),
            'message': 'Siparişiniz alındı ve mutfak kuyruğuna kaydedildi.'}
