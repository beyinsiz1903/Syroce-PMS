"""Resolve new charge ownership inside the posting transaction, without reposting revenue."""
from datetime import date

from fastapi import HTTPException

from modules.pms_core.report_money import currency_code


async def route_new_charge(database, tenant_id, charge, *, session=None):
    """Mutate only a not-yet-inserted charge; never move payments or old sources.

    Legacy rules remain manual unless explicitly opted in. One hop is intentional:
    a destination's rules cannot silently change a source's operator-approved target.
    """
    kwargs = {"session": session} if session is not None else {}
    source_id = charge.get("folio_id")
    if not source_id or charge.get("routing_rule_id"):
        return None
    rules = await database.folio_routing.find({"tenant_id": tenant_id,
        "source_folio_id": source_id, "active": True, "apply_to_future": True}, **kwargs).to_list(501)
    if not rules:
        return None
    codes = {str(charge.get(k) or "").upper() for k in ("charge_code", "charge_category", "category", "charge_type")} - {""}
    candidates = [r for r in rules if not r.get("charge_codes") or codes.intersection(str(c).upper() for c in r["charge_codes"])]
    if not candidates:
        return None
    try:
        day = date.fromisoformat(str(charge.get("business_date") or "")).isoformat()
    except ValueError:
        raise HTTPException(409, "Otomatik yönlendirme için masrafın iş günü gerekli") from None
    matched = [r for r in candidates if (not r.get("from_date") or day >= r["from_date"])
        and (not r.get("to_date") or day <= r["to_date"])]
    if not matched:
        return None
    if len(matched) != 1 or len(rules) > 500:
        raise HTTPException(409, "Otomatik yönlendirme kuralları çakışıyor; ücret işlenmedi")
    if session is None:
        raise HTTPException(503, "Otomatik yönlendirme için atomik işlem desteği gerekli")
    rule = matched[0]
    business_day = await database.tenant_settings.update_one({"tenant_id": tenant_id, "business_date": day},
        {"$inc": {"automatic_routing_revision": 1}}, **kwargs)
    if business_day.matched_count != 1:
        raise HTTPException(409, "Masrafın açık iş günü değişti; yönlendirme yapılmadı")
    source = await database.folios.find_one({"tenant_id": tenant_id, "id": source_id}, **kwargs)
    target = await database.folios.find_one({"tenant_id": tenant_id, "id": rule["dest_folio_id"]}, **kwargs)
    booking_id = charge.get("booking_id")
    if not source or not target or source_id == target["id"] or not booking_id or any(
        f.get("status") != "open" or f.get("booking_id") != booking_id or f.get("invoice_id") for f in (source, target)
    ):
        raise HTTPException(409, "Yönlendirme hedefi açık, faturasız ve aynı rezervasyonda olmalı")
    if not charge.get("currency") or any(not f.get("currency") or currency_code(f["currency"]) != currency_code(charge["currency"]) for f in (source, target)):
        raise HTTPException(409, "Yönlendirme para birimleri doğrulanamadı veya farklı")
    invoice = await database.invoices.find_one({"tenant_id": tenant_id, "$or": [{"booking_id": booking_id},
            {"folio_id": {"$in": [source_id, target["id"]]}},
            {"folio_ids": {"$in": [source_id, target["id"]]}}],
        "voided": {"$ne": True}, "status": {"$nin": ["cancelled", "canceled", "void", "voided"]}}, **kwargs)
    if invoice:
        raise HTTPException(409, "Faturalı rezervasyonda önce fatura düzeltme akışını tamamlayın")
    # Write conflicts serialize rule removal, account closure and simultaneous posts.
    changed = await database.folio_routing.update_one({"tenant_id": tenant_id, "id": rule["id"], "active": True,
        "apply_to_future": True}, {"$inc": {"posting_revision": 1}}, **kwargs)
    if changed.matched_count != 1:
        raise HTTPException(409, "Yönlendirme kuralı değişti; yeniden deneyin")
    for folio in (source, target):
        updated = await database.folios.update_one({"tenant_id": tenant_id, "id": folio["id"], "status": "open"},
            {"$inc": {"routing_post_revision": 1}}, **kwargs)
        if updated.matched_count != 1:
            raise HTTPException(409, "Yönlendirme hesabı değişti; ücret işlenmedi")
    charge.update(folio_id=target["id"], routing_source_folio_id=source_id,
        routing_rule_id=rule["id"], routing_execution="automatic_new_charge")
    return target


def original_folio_id(charge):
    """Source identity stays stable on retries after an automatic routing decision."""
    return charge.get("routing_source_folio_id") or charge.get("folio_id")


async def post_automatic_pos_charges(database, tenant_id, source_folio, order_id, charges):
    """POS outbox delivery: all lines and target balances share one transaction."""
    from core.booking_payment_state import refresh_booking_payment_state
    from core.business_date_service import stamp_open_business_date
    from modules.pms_core.receivable_reporting import folio_snapshots

    async def commit(session):
        affected = {source_folio['id']: source_folio}
        for original in charges:
            previous = await database.folio_charges.find_one({'tenant_id': tenant_id,
                'source_pos_order_id': order_id, 'line_no': original.get('line_no')}, session=session)
            if previous:
                fields = ('booking_id', 'charge_category', 'amount', 'total', 'currency',
                    'vat_amount', 'tax_amount', 'subtotal', 'discount_amount', 'tax_breakdown')
                if original_folio_id(previous) != source_folio['id'] or any(previous.get(k) != original.get(k) for k in fields):
                    raise HTTPException(409, 'Önceki POS kaynak satırıyla yönlendirme uyuşmuyor')
                target = await database.folios.find_one({'tenant_id': tenant_id, 'id': previous['folio_id']}, session=session)
                if target:
                    affected[target['id']] = target
                continue
            charge = dict(original)
            await stamp_open_business_date(database, tenant_id, charge)
            target = await route_new_charge(database, tenant_id, charge, session=session) or source_folio
            # Even an unmatched category must not post to an account closed concurrently.
            changed = await database.folios.update_one({'tenant_id': tenant_id, 'id': target['id'], 'status': 'open'},
                {'$inc': {'routing_post_revision': 1}}, session=session)
            if changed.matched_count != 1:
                raise HTTPException(409, 'POS hedef hesabı kapandı; hiçbir satır işlenmedi')
            await database.folio_charges.insert_one(charge, session=session)
            affected[target['id']] = target
        snapshots = await folio_snapshots(database, tenant_id, list(affected.values()),
            fallback_currency=source_folio.get('currency'), include_booking_extras=True, session=session)
        for fid, snap in snapshots.items():
            await database.folios.update_one({'tenant_id': tenant_id, 'id': fid},
                {'$set': {'balance': snap['balance_by_currency'].get(snap['currency'], 0)}}, session=session)
        await refresh_booking_payment_state(database, tenant_id, source_folio['booking_id'], session=session, strict=True)

    async with await database.client.start_session() as session:
        await session.with_transaction(commit)


async def insert_booking_extra(database, tenant_id, charge):
    """Booking-card extras have no explicit window; match a unique opted-in source."""
    from core.booking_payment_state import refresh_booking_payment_state
    from modules.pms_core.receivable_reporting import folio_snapshots

    # Modern sources need an owner even after the last routing destination
    # was merged. Only historical sources with no windows may stay unassigned.
    has_routing = await database.folio_routing.find_one({'tenant_id': tenant_id, 'active': True, 'apply_to_future': True})
    if not has_routing and not await database.folios.find_one({
        'tenant_id': tenant_id, 'booking_id': charge['booking_id'], 'status': 'open',
    }):
        if await database.folios.find_one({'tenant_id': tenant_id, 'booking_id': charge['booking_id'], 'status': {'$exists': True}}):
            raise HTTPException(409, 'Ek ücret için açık folyo bulunamadı; ücret işlenmedi')
        await database.extra_charges.insert_one(dict(charge))
        return charge

    async def commit(session):
        booking = await database.bookings.find_one({'tenant_id': tenant_id, 'id': charge['booking_id']}, session=session)
        if not booking:
            raise HTTPException(404, 'Rezervasyon bulunamadı')
        folios = await database.folios.find({'tenant_id': tenant_id, 'booking_id': charge['booking_id'], 'status': 'open'}, session=session).to_list(501)
        rules = await database.folio_routing.find({'tenant_id': tenant_id, 'source_folio_id': {'$in': [f['id'] for f in folios]},
            'active': True, 'apply_to_future': True}, session=session).to_list(501)
        codes = {str(charge.get(k) or '').upper() for k in ('category', 'charge_category', 'charge_code')}
        day = charge.get('business_date') or ''
        matched = [r for r in rules if (not r.get('charge_codes') or codes.intersection(r['charge_codes']))
            and (not r.get('from_date') or day >= r['from_date']) and (not r.get('to_date') or day <= r['to_date'])]
        if len(matched) > 1 or len(rules) > 500:
            raise HTTPException(409, 'Ek ücret için yönlendirme kaynakları çakışıyor; ücret işlenmedi')
        posted = dict(charge)
        target = None
        source_ids = {r['source_folio_id'] for r in rules}
        source_id = matched[0]['source_folio_id'] if matched else next(iter(source_ids)) if len(source_ids) == 1 else None
        if not source_id and not rules and len(folios) == 1:
            source_id = folios[0]['id']
        if rules and not source_id:
            raise HTTPException(409, 'Eşleşmeyen ek ücret için kaynak hesap belirsiz; ücret işlenmedi')
        if folios and not source_id:
            raise HTTPException(409, 'Birden fazla açık folyo var. Masrafı ilgili folyonun İşlem Ekle alanından girin; ücret işlenmedi')
        if source_id:
            source = next(f for f in folios if f['id'] == source_id)
            code = currency_code(charge.get('currency') or booking.get('currency'))
            if source.get('invoice_id') or currency_code(source.get('currency') or booking.get('currency')) != code:
                raise HTTPException(409, 'Ek ücretin kaynak folyosu faturasız ve aynı para biriminde olmalı')
            posted.update(folio_id=source_id, currency=code)
            target = await route_new_charge(database, tenant_id, posted, session=session)
            target = target or next(f for f in folios if f['id'] == source_id)
        await database.extra_charges.insert_one(dict(posted), session=session)
        if target:
            snap = (await folio_snapshots(database, tenant_id, [target], fallback_currency=posted['currency'], include_booking_extras=True, session=session))[target['id']]
            await database.folios.update_one({'tenant_id': tenant_id, 'id': target['id']},
                {'$set': {'balance': snap['balance_by_currency'].get(snap['currency'], 0)}}, session=session)
        await refresh_booking_payment_state(database, tenant_id, charge['booking_id'], session=session, strict=True)
        return posted

    async with await database.client.start_session() as session:
        return await session.with_transaction(commit)
