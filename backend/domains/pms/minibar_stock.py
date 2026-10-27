"""Durable minibar stock work; never replay a charge to repair inventory.

The hotel warehouse uses inventory_items/stock_movements. Old links to the
separate mobile inventory are supported explicitly, never guessed on retry.
Stock, its movement, job state and sealed audit commit in one transaction.
"""
import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from core.booking_atomicity import with_resource_locks
from core.business_date_service import stamp_open_business_date
from shared_kernel.audit_helper import audit_log

BACKENDS = {'accounting': ('inventory_items', 'stock_movements'), 'legacy': ('inventory', 'inventory_movements')}
DONE = {'depleted', 'already_applied'}


async def create_stock_product(db, tenant_id, actor_id, data):
    """Audited, idempotent opening in the SAME central warehouse the UI uses."""
    request = data.model_dump(mode='json')
    fingerprint = sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    product_id = str(uuid5(NAMESPACE_URL, f'minibar-inventory:{tenant_id}:{data.request_id}'))
    await ensure_stock_indexes(db)
    await db.inventory_items.create_index([('tenant_id', 1), ('id', 1)])
    await db.minibar_locks.create_index([('tenant_id', 1), ('kind', 1), ('resource_id', 1)], unique=True)

    async def commit(session):
        existing = await db.inventory_items.find_one({'tenant_id': tenant_id, 'id': product_id}, {'_id': 0}, session=session)
        if existing:
            if existing.get('opening_request_hash') != fingerprint:
                raise HTTPException(409, 'Stok açılış anahtarı farklı içerikle kullanılmış')
            return {'item': existing, 'replayed': True}
        now = datetime.now(UTC).isoformat()
        product = {'id': product_id, 'tenant_id': tenant_id, 'name': data.name.strip(), 'category': 'minibar',
            'unit': data.unit.strip(), 'quantity': data.quantity, 'unit_cost': data.unit_cost, 'reorder_level': 0,
            'currency': data.currency, 'sku': data.sku, 'is_consumable': True, 'status': 'active',
            'opening_request_id': str(data.request_id), 'opening_request_hash': fingerprint,
            'notes': data.reason.strip(), 'created_at': now, 'created_by': actor_id}
        if not product['name'] or not product['unit'] or len(product['notes']) < 5:
            raise HTTPException(422, 'Ürün adı, birim ve stok açılış gerekçesi zorunlu')
        await db.inventory_items.insert_one(dict(product), session=session)
        movement_id = None
        if data.quantity:
            movement_id = str(uuid5(NAMESPACE_URL, f'minibar-opening:{tenant_id}:{data.request_id}'))
            movement = {'id': movement_id, 'tenant_id': tenant_id, 'item_id': product_id, 'item_name': product['name'],
                'movement_type': 'in', 'quantity': data.quantity, 'unit_cost': data.unit_cost,
                'total_cost': data.quantity * data.unit_cost, 'previous_quantity': 0, 'new_quantity': data.quantity,
                'reference': str(data.request_id), 'notes': product['notes'], 'created_by': actor_id, 'created_at': now}
            await stamp_open_business_date(db, tenant_id, movement)
            await db.stock_movements.insert_one(movement, session=session)
        await audit_log(actor_id=actor_id, tenant_id=tenant_id, entity_type='inventory_item', entity_id=product_id,
            action='minibar_inventory_opened', metadata={'quantity': data.quantity, 'unit': data.unit,
                'unit_cost': data.unit_cost, 'currency': data.currency, 'movement_id': movement_id,
                'reason': data.reason.strip(), 'request_id': str(data.request_id)}, session=session, require_chain=True)
        return {'item': product, 'replayed': False}

    return await with_resource_locks(client=db.client, db=db, tenant_id=tenant_id, locks_collection='minibar_locks',
        resources=[('inventory_opening', product_id)], callback=commit)


async def validate_link(db, tenant_id, product_id, source=None, session=None):
    if not product_id:
        return {'inventory_product_id': None, 'inventory_source': None}
    if source is not None and source not in BACKENDS:
        raise HTTPException(422, 'Stok kaynağı geçersiz')
    matches = []
    for backend in ([source] if source else BACKENDS):
        product = await db[BACKENDS[backend][0]].find_one({'tenant_id': tenant_id, 'id': product_id}, session=session)
        if product:
            matches.append((backend, product))
    if not matches:
        raise HTTPException(404, 'Stok ürünü bu tesiste bulunamadı')
    if len(matches) != 1:
        raise HTTPException(409, 'Stok ürününün kaynağını açıkça seçin')
    backend, product = matches[0]
    if product.get('active') is False or product.get('is_active') is False or product.get('status') == 'inactive':
        raise HTTPException(409, 'Pasif stok ürünü bağlanamaz')
    return {'inventory_product_id': product_id, 'inventory_source': backend}


def make_jobs(lines):
    return [{
        'line_no': line.get('line_no', index), 'item_id': line['item_id'], 'item_name': line.get('item_name'),
        'quantity': line['quantity'], 'inventory_product_id': line.get('inventory_product_id'),
        # Existing pre-upgrade IDs refer to the legacy mobile collection.
        'inventory_source': line.get('inventory_source') or ('legacy' if line.get('inventory_product_id') else None),
        'status': 'pending' if line.get('inventory_product_id') else 'unlinked',
        'basis': 'consumption_snapshot',
    } for index, line in enumerate(lines)]


def stock_view(consumption):
    jobs = consumption.get('stock_jobs')
    if jobs is None:
        return [{**job, 'status': 'legacy_untracked'} for job in make_jobs(consumption.get('lines', []))]
    return deepcopy(jobs)


def stock_complete(jobs):
    return bool(jobs) and all(job['status'] in DONE for job in jobs)


async def ensure_stock_indexes(db):
    from domains.pms.pos_extensions._idem import ensure_compound_unique

    for _, movements in BACKENDS.values():
        await ensure_compound_unique(db[movements],
            [('tenant_id', 1), ('source_minibar_log_id', 1), ('line_no', 1)],
            partial_filter={'source_minibar_log_id': {'$type': 'string'}}, name='ux_minibar_stock_source')


async def run_stock(db, tenant_id, consumption_id, actor_id, reason='Minibar tüketimi stok aktarımı'):
    """Retry ONLY frozen stock work, including after a lost success response."""
    await ensure_stock_indexes(db)

    async def commit(session):
        query = {'tenant_id': tenant_id, 'id': consumption_id}
        consumption = await db.minibar_consumptions.find_one(query, {'_id': 0}, session=session)
        if not consumption:
            raise HTTPException(404, 'Minibar tüketimi bulunamadı')
        if consumption.get('stock_jobs') is None:
            # The old best-effort decrement could have succeeded before its
            # movement failed. Missing evidence is NOT permission to decrement.
            return stock_view(consumption)
        jobs = deepcopy(consumption['stock_jobs'])
        changed = False
        now = datetime.now(UTC).isoformat()
        for job in jobs:
            if not job.get('inventory_product_id'):
                continue
            backend = job.get('inventory_source')
            if backend not in BACKENDS:
                raise HTTPException(409, 'Stok işinin kaynak tanımı doğrulanamadı')
            products, movements = (db[name] for name in BACKENDS[backend])
            source = {'tenant_id': tenant_id, 'source_minibar_log_id': consumption_id, 'line_no': job['line_no']}
            prior = await movements.find_one(source, session=session)
            if job['status'] in DONE and (not prior or prior.get('id') != job.get('movement_id')):
                raise HTTPException(409, 'Tamamlanmış stok işinin hareket kanıtı bulunamadı; yeniden stok düşülemez')
            if prior:
                product_key = 'item_id' if backend == 'accounting' else 'product_id'
                if prior.get(product_key) != job['inventory_product_id'] or abs(Decimal(str(prior.get('quantity', 0)))) != Decimal(str(job['quantity'])):
                    raise HTTPException(409, 'Minibar stok hareketi kaynak satırıyla uyuşmuyor')
                if job['status'] not in DONE:
                    job.update(status='already_applied', movement_id=prior['id'])
                    changed = True
                continue
            product = await products.find_one({'tenant_id': tenant_id, 'id': job['inventory_product_id']}, session=session)
            status, available = 'product_not_found', None
            if product:
                try:
                    available = Decimal(str(product.get('quantity')))
                    needed = Decimal(str(job['quantity']))
                    valid = available.is_finite() and needed.is_finite() and available >= 0 and needed > 0
                except (InvalidOperation, TypeError, ValueError):
                    valid = False
                if not valid:
                    status = 'invalid_stock_quantity'
                elif product.get('active') is False or product.get('is_active') is False or product.get('status') == 'inactive':
                    status = 'inactive_product'
                elif available < needed:
                    status = 'insufficient_stock'
                else:
                    status = 'depleted'
            if status != 'depleted':
                job.update(status=status, last_attempt_at=now, retryable=True)
                if available is not None and available.is_finite():
                    job['available'] = float(available)
                changed = True
                continue
            remaining = float(available - needed)
            result = await products.update_one({'tenant_id': tenant_id, 'id': product['id'], 'quantity': product['quantity']},
                {'$set': {'quantity': remaining, 'last_updated': now, 'last_updated_by': actor_id}}, session=session)
            if result.modified_count != 1:
                raise HTTPException(409, 'Stok eşzamanlı değişti; kaynak işi yeniden deneyin')
            movement = {**source, 'id': str(uuid5(NAMESPACE_URL, f'minibar-stock:{tenant_id}:{consumption_id}:{job["line_no"]}')),
                'movement_type': 'out', 'quantity': float(needed) if backend == 'accounting' else -float(needed),
                'previous_quantity': float(available), 'new_quantity': remaining, 'reason': 'minibar_consumption',
                'reference': consumption_id, 'notes': reason, 'performed_by': actor_id, 'created_by': actor_id,
                'created_at': now, 'timestamp': now, 'booking_id': consumption.get('booking_id'),
                'consumption_business_date': consumption.get('business_date'), 'stock_basis': job['basis']}
            if backend == 'accounting':
                movement.update(item_id=product['id'], item_name=product.get('name'), unit=product.get('unit'),
                    unit_cost=product.get('unit_cost'), total_cost=None if product.get('unit_cost') is None else float(needed) * product['unit_cost'])
            else:
                movement.update(product_id=product['id'], product_name=product.get('product_name', product.get('name')),
                    unit_of_measure=product.get('unit_of_measure', 'pcs'))
            # A late recovery is recorded on TODAY's open stock business day,
            # retaining the original consumption day without backdating it.
            await stamp_open_business_date(db, tenant_id, movement)
            await movements.insert_one(dict(movement), session=session)
            await audit_log(actor_id=actor_id, tenant_id=tenant_id, entity_type='reservation',
                entity_id=consumption['booking_id'], action='minibar_stock_depleted',
                metadata={**source, 'inventory_source': backend, 'inventory_product_id': product['id'],
                    'quantity': float(needed), 'movement_id': movement['id'], 'reason': reason,
                    'previous_quantity': float(available), 'new_quantity': remaining, 'business_date': movement['business_date']},
                session=session, require_chain=True)
            job.update(status='depleted', movement_id=movement['id'], new_quantity=remaining, completed_at=now, retryable=False)
            job.pop('available', None)
            changed = True
        if changed:
            await db.minibar_consumptions.update_one(query, {'$set': {'stock_jobs': jobs}}, session=session)
        return jobs

    return await with_resource_locks(client=db.client, db=db, tenant_id=tenant_id,
        locks_collection='minibar_locks', resources=[('stock_consumption', consumption_id)], callback=commit)


async def reconcile_bindings(db, tenant_id, consumption_id, bindings, actor_id, reason):
    """Explicit operator mapping for previously untracked lines; preserve debt.

    This is a new current-day inventory instruction, not a claim that an old
    untracked consumption already had a verified physical stock movement.
    """
    await ensure_stock_indexes(db)

    async def commit(session):
        consumption = await db.minibar_consumptions.find_one({'tenant_id': tenant_id, 'id': consumption_id}, {'_id': 0}, session=session)
        if not consumption:
            raise HTTPException(404, 'Minibar tüketimi bulunamadı')
        jobs = deepcopy(consumption.get('stock_jobs'))
        if jobs is None:
            if any(line.get('inventory_product_id') for line in consumption.get('lines', [])):
                raise HTTPException(409, 'Eski bağlı stok satırı ayrıca fiziksel mutabakat gerektiriyor; otomatik tekrar düşülemez')
            jobs = make_jobs(consumption.get('lines', []))
        lookup = {j['line_no']: j for j in jobs}
        if len({b.line_no for b in bindings}) != len(bindings):
            raise HTTPException(422, 'Aynı stok satırı iki kez seçilemez')
        changed = []
        for binding in bindings:
            job = lookup.get(binding.line_no)
            if job is None:
                raise HTTPException(404, 'Minibar kaynak satırı bulunamadı')
            if job.get('inventory_product_id'):
                if job['inventory_product_id'] == binding.inventory_product_id and job['inventory_source'] == binding.inventory_source:
                    continue
                raise HTTPException(409, 'Bağlanmış veya işlenmiş stok işi başka ürüne taşınamaz')
            link = await validate_link(db, tenant_id, binding.inventory_product_id, binding.inventory_source, session)
            # No old movement may be overlooked, including one in the other
            # inventory backend. Require review instead of double consumption.
            for _, collection in BACKENDS.values():
                if await db[collection].find_one({'tenant_id': tenant_id, 'source_minibar_log_id': consumption_id,
                    'line_no': binding.line_no}, session=session):
                    raise HTTPException(409, 'Bu satırın önceki stok hareketi var; yeniden düşülemez')
            job.update(**link, status='pending', basis='explicit_current_day_reconciliation',
                linked_at=datetime.now(UTC).isoformat(), linked_by=actor_id, link_reason=reason)
            changed.append(deepcopy(job))
        if changed:
            await db.minibar_consumptions.update_one({'tenant_id': tenant_id, 'id': consumption_id}, {'$set': {'stock_jobs': jobs}}, session=session)
            await audit_log(actor_id=actor_id, tenant_id=tenant_id, entity_type='reservation', entity_id=consumption['booking_id'],
                action='minibar_stock_linked', metadata={'source_minibar_log_id': consumption_id, 'lines': changed,
                    'reason': reason, 'historical_physical_stock_verified': False}, session=session, require_chain=True)
        return {'bindings_changed': len(changed)}

    result = await with_resource_locks(client=db.client, db=db, tenant_id=tenant_id, locks_collection='minibar_locks',
        resources=[('stock_consumption', consumption_id)], callback=commit)
    result['stock'] = await run_stock(db, tenant_id, consumption_id, actor_id, reason)
    return result
