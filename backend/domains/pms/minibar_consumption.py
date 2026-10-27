"""Atomic minibar debt + source log + sealed operator audit.

The catalog price is VAT-inclusive and has an explicit currency. Stock remains
the existing, separately reported best-effort inventory operation.
"""
import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from core.booking_atomicity import with_resource_locks
from core.booking_payment_state import refresh_booking_payment_state
from core.business_date_service import stamp_open_business_date
from core.report_cache import invalidate_financial_report_caches
from modules.pms_core.receivable_reporting import folio_snapshots
from shared_kernel.audit_helper import audit_log


def line_values(item, quantity, complimentary):
    try:
        price, rate = Decimal(str(item['price'])), Decimal(str(item['tax_rate']))
        if not price.is_finite() or not rate.is_finite() or price < 0 or not 0 <= rate <= 1:
            raise ValueError
    except (KeyError, ValueError, TypeError, ArithmeticError):
        raise HTTPException(409, 'Minibar ürün fiyatı/vergi oranı eksik veya geçersiz; kataloğu doğrulayın') from None
    gross = (price * quantity).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    net = (gross / (1 + rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return (Decimal(0), Decimal(0), Decimal(0), gross) if complimentary else (net, gross - net, gross, gross)


async def consume_to_folio(database, payload, current_user):
    from domains.pms import minibar_router as m

    tid, actor = m._tenant_of(current_user), m._actor_id(current_user)
    try:
        await m._ensure_minibar_charge_index()
        await m._ensure_minibar_consumption_index()
        await database.minibar_locks.create_index([('tenant_id', 1), ('kind', 1), ('resource_id', 1)], unique=True)
    except Exception as exc:
        raise HTTPException(503, 'Minibar faturalama tekillik koruması hazır değil') from exc
    log_id = m._stable_log_id(tid, payload.idempotency_key) if payload.idempotency_key else str(uuid4())
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()

    async def commit(session):
        prior_query = {'tenant_id': tid, 'idempotency_key': payload.idempotency_key} if payload.idempotency_key else {'tenant_id': tid, 'id': log_id}
        prior = await database.minibar_consumptions.find_one(prior_query, {'_id': 0}, session=session)
        if prior:
            original_lines = [(row['item_id'], row['quantity']) for row in prior.get('lines', [])]
            requested_lines = [(row.item_id, row.quantity) for row in payload.lines]
            if prior.get('room_id') != payload.room_id or original_lines != requested_lines or prior.get('fingerprint', fingerprint) != fingerprint:
                raise HTTPException(409, 'Minibar işlem anahtarı farklı bilgilerle kullanılmış')
            if prior.get('status') == 'posted' and prior.get('booking_id'):
                # Replay repairs pre-upgrade derived fields without replaying
                # stock, revenue, audit consumption or the original charges.
                await refresh_booking_payment_state(database, tid, prior['booking_id'], session=session, strict=True)
            return {'consumption': prior, 'idempotent': True, 'posted_to_folio': prior.get('status') == 'posted', 'stock': []}
        room = await database.rooms.find_one({'id': payload.room_id, 'tenant_id': tid}, session=session)
        if not room:
            raise HTTPException(404, 'Oda bulunamadı')
        bookings = await database.bookings.find({'tenant_id': tid, 'room_id': payload.room_id,
            'status': {'$in': ['checked_in', 'in_house']}}, session=session).to_list(2)
        if len(bookings) != 1:
            raise HTTPException(409, 'Odada tek bir aktif konaklama doğrulanamadı — minibar faturalanamaz')
        booking = bookings[0]
        code = str(booking.get('currency') or 'TRY').upper()
        folios = await database.folios.find({'tenant_id': tid, 'booking_id': booking['id'],
            'folio_type': 'guest', 'status': 'open'}, session=session).to_list(2)
        if len(folios) > 1:
            raise HTTPException(409, 'Birden fazla misafir folyosu var; hedef pencere önce uzlaştırılmalı')
        folio = folios[0] if folios else None
        if folio and str(folio.get('currency') or code).upper() != code:
            raise HTTPException(409, 'Minibar rezervasyonu ve folyo para birimi uyuşmuyor')
        ids = list({row.item_id for row in payload.lines})
        catalog = await database.minibar_items.find({'tenant_id': tid, 'id': {'$in': ids}}, {'_id': 0}, session=session).to_list(1000)
        items = {item['id']: item for item in catalog}
        now = datetime.now(UTC).isoformat()
        lines, charge_ids = [], []
        comp = booking.get('is_complimentary') and booking.get('complimentary_scope') == 'full'
        for number, row in enumerate(payload.lines):
            item = items.get(row.item_id)
            if not item or item.get('active') is False:
                raise HTTPException(400, 'Geçersiz veya pasif minibar ürünü')
            if str(item.get('currency') or '').upper() != code:
                raise HTTPException(409, 'Minibar ürünü ve folyo para birimi farklı veya eksik; kur tahminiyle aktarım yapılamaz')
            net, vat, gross, original = line_values(item, row.quantity, comp)
            line = {'line_no': number, 'item_id': row.item_id, 'item_name': item['name'], 'category': item.get('category'),
                'quantity': row.quantity, 'unit_price': item['price'], 'amount': float(net), 'vat_amount': float(vat),
                'tax_rate': item['tax_rate'], 'total': float(gross), 'currency': code,
                'original_total': float(original), 'inventory_product_id': item.get('inventory_product_id')}
            lines.append(line)
            if folio:
                cid = str(uuid5(NAMESPACE_URL, f'minibar:{tid}:{log_id}:{number}'))
                charge = {'_id': f'minibar:{tid}:{log_id}:{number}', 'id': cid, 'tenant_id': tid,
                    'booking_id': booking['id'], 'folio_id': folio['id'], 'guest_id': booking.get('guest_id'),
                    'charge_type': 'minibar', 'charge_category': 'minibar', 'description': f"Minibar - {item['name']} x{row.quantity}",
                    'amount': float(net), 'subtotal': float(net), 'discount_amount': 0, 'vat_amount': float(vat),
                    'tax_amount': 0, 'tax_breakdown': {'vat': float(vat)}, 'total': float(gross), 'currency': code,
                    'voided': False, 'date': now, 'posted_at': now, 'posted_by': actor, 'created_at': now,
                    'source_minibar_log_id': log_id, 'line_no': number,
                    'is_complimentary': bool(comp), 'complimentary_original_amount': float(original) if comp else None}
                await stamp_open_business_date(database, tid, charge)
                # A conflicting unrelated index is NOT proof that this line
                # posted. Abort the transaction instead of acknowledging loss.
                await database.folio_charges.insert_one(dict(charge), session=session)
                charge_ids.append(cid)
        doc = {'id': log_id, 'tenant_id': tid, 'room_id': payload.room_id, 'room_number': room.get('room_number'),
            'booking_id': booking['id'], 'guest_id': booking.get('guest_id'), 'lines': lines,
            'total': float(sum((Decimal(str(row['total'])) for row in lines), Decimal(0))), 'currency': code,
            'note': payload.note, 'idempotency_key': payload.idempotency_key, 'fingerprint': fingerprint,
            'posted_by': actor, 'created_at': now, 'status': 'posted' if folio else 'late_charge', 'charge_ids': charge_ids}
        await stamp_open_business_date(database, tid, doc)
        if folio:
            snap = (await folio_snapshots(database, tid, [folio], fallback_currency=code, session=session))[folio['id']]
            if any(value and currency != code for currency, value in snap['balance_by_currency'].items()):
                raise HTTPException(409, 'Minibar öncesi folyo para birimi mutabakatı gerekli')
            balance = float(snap['balance_by_currency'].get(code, 0))
            await database.folios.update_one({'tenant_id': tid, 'id': folio['id']}, {'$set': {'balance': balance}}, session=session)
            await refresh_booking_payment_state(database, tid, booking['id'], session=session, strict=True)
            doc.update(folio_id=folio['id'], folio_balance=balance)
        else:
            latest = await database.folios.find_one({'tenant_id': tid, 'booking_id': booking['id'], 'folio_type': 'guest'}, sort=[('created_at', -1)], session=session)
            doc['folio_id'] = (latest or {}).get('id')
            await database.minibar_late_charges.update_one({'tenant_id': tid, 'source_minibar_log_id': log_id},
                {'$set': {**doc, 'source_minibar_log_id': log_id, 'status': 'pending_review', 'updated_at': now}}, upsert=True, session=session)
        await database.minibar_consumptions.insert_one(dict(doc), session=session)
        await audit_log(actor_id=actor, tenant_id=tid, entity_type='reservation', entity_id=booking['id'],
            action='minibar_consumed' if folio else 'minibar_late_charge', metadata={'room_number': room.get('room_number'),
                'source_minibar_log_id': log_id, 'folio_id': doc['folio_id'], 'charge_ids': charge_ids, 'lines': lines,
                'amount': doc['total'], 'currency': code, 'business_date': doc['business_date'], 'reason': payload.note},
            session=session, require_chain=True)
        return {'consumption': doc, 'posted_to_folio': bool(folio), 'folio_status': 'open' if folio else 'late_charge',
            '_items': items, 'stock': []}

    try:
        result = await with_resource_locks(client=database.client, db=database, tenant_id=tid, locks_collection='minibar_locks',
            resources=[('room', payload.room_id), ('consumption', log_id)], callback=commit)
    except DuplicateKeyError as exc:
        raise HTTPException(409, 'Minibar tekillik çakışması; hiçbir yeni ücret kaydedilmedi. Kaynak kayıtları kontrol edin.') from exc
    if result.get('idempotent'):
        return result
    invalidate_financial_report_caches(tid)
    items = result.pop('_items')
    for line in result['consumption']['lines']:
        try:
            stock = await m._deplete_stock_best_effort(tid, actor, items[line['item_id']], line['quantity'], log_id, line['line_no'])
        except Exception:
            m.logger.exception('Minibar stok hareketi tamamlanamadı source=%s', log_id)
            stock = {'status': 'error'}
        result['stock'].append({'item_id': line['item_id'], **stock})
    return result
