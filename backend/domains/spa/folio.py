"""SPA completion posts the real PMS receivable, not only an integration stub.

Called inside the appointment/booking transaction. Prices and VAT are the
appointment's immutable catalog snapshot; never guess historical tax or FX.
"""
from decimal import ROUND_HALF_UP, Decimal
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from core.business_date_service import stamp_open_business_date
from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots
from shared_kernel.audit_helper import audit_log


def amounts(appt, complimentary=False):
    try:
        gross = Decimal(str(appt['price']))
        rate = Decimal(str(appt['tax_rate']))
        if not gross.is_finite() or not rate.is_finite() or gross < 0 or not 0 <= rate <= 1:
            raise ValueError
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise HTTPException(409, 'SPA fiyat/vergi anlık kaydı eksik; hizmet ve randevu fiyatını doğrulayın. Geçmiş vergi tahmin edilmez.') from None
    gross = gross.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    net = (gross / (1 + rate)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    if complimentary:
        return Decimal(0), Decimal(0), Decimal(0), gross
    return net, gross - net, gross, gross


async def post_charge(database, tenant_id, appt, actor_id, actor_name, *, session):
    if session is None:
        raise HTTPException(503, 'SPA folyo aktarımı için atomik transaction desteği gerekli')
    booking_id = appt.get('reservation_id')
    booking = await database.bookings.find_one({'tenant_id': tenant_id, 'id': booking_id}, session=session)
    if not booking:
        raise HTTPException(404, 'SPA rezervasyonuna bağlı otel rezervasyonu bulunamadı')
    if booking.get('status') not in {'checked_in', 'in_house'}:
        raise HTTPException(409, 'SPA bedeli yalnız içeride konaklayan misafire aktarılabilir')
    folio = await select_booking_folio(database, tenant_id, booking_id, appt.get('folio_id'), session=session)
    if not folio:
        raise HTTPException(409, 'SPA aktarımı için açık misafir folyosu gerekli')
    code = str(booking.get('currency') or folio.get('currency') or 'TRY').upper()
    if str(appt.get('currency') or '').upper() != code or str(folio.get('currency') or code).upper() != code:
        raise HTTPException(409, 'SPA hizmeti ve folyo para birimi farklı; kur tahminiyle aktarım yapılamaz')
    net, vat, gross, original = amounts(appt, booking.get('is_complimentary') and booking.get('complimentary_scope') == 'full')
    identity = 'spa:' + tenant_id + ':' + str(appt['id'])
    cid = str(uuid5(NAMESPACE_URL, identity))
    existing = await database.folio_charges.find_one({'tenant_id': tenant_id, 'id': cid}, {'_id': 0}, session=session)
    if existing:
        if any(existing.get(k) != value for k, value in {'booking_id': booking_id, 'folio_id': folio['id'],
                'currency': code, 'total': float(gross), 'amount': float(net), 'vat_amount': float(vat)}.items()):
            raise HTTPException(409, 'SPA kaynak kaydı mevcut folyo tutarıyla uyuşmuyor')
        return {'charge': existing, 'replayed': True}
    charge = {'_id': identity, 'id': cid, 'tenant_id': tenant_id, 'booking_id': booking_id, 'folio_id': folio['id'],
        'charge_type': 'spa', 'charge_category': 'spa', 'description': 'SPA: ' + str(appt.get('service_name') or 'Masaj'),
        'quantity': 1, 'amount': float(net), 'subtotal': float(net), 'discount_amount': 0,
        'vat_amount': float(vat), 'tax_amount': 0, 'tax_breakdown': {'vat': float(vat)}, 'total': float(gross),
        'currency': code, 'voided': False, 'source_spa_appointment_id': appt['id'],
        'posted_by': actor_name, 'posted_by_id': actor_id, 'date': appt['completed_at'], 'posted_at': appt['completed_at'],
        'is_complimentary': gross == 0, 'complimentary_original_amount': float(original) if gross == 0 else None}
    await stamp_open_business_date(database, tenant_id, charge)
    await database.folio_charges.insert_one(dict(charge), session=session)
    posting = {'_id': identity, 'id': cid, 'tenant_id': tenant_id, 'reservation_id': booking_id,
        'folio_id': folio['id'], 'transaction_code': 'SPA', 'description': charge['description'],
        'amount': float(gross), 'currency': code, 'posting_type': 'CHARGE', 'posted_at': charge['posted_at'],
        'source': 'spa_module', 'reference': appt['id'], 'dedup_key': 'spa_module:' + appt['id'], 'folio_charge_id': cid}
    await database.folio_postings.insert_one(posting, session=session)
    snap = (await folio_snapshots(database, tenant_id, [folio], fallback_currency=code, session=session))[folio['id']]
    if any(value and currency != code for currency, value in snap['balance_by_currency'].items()):
        raise HTTPException(409, 'SPA aktarımı öncesinde folyo para birimi mutabakatı gerekli')
    await database.folios.update_one({'tenant_id': tenant_id, 'id': folio['id']},
        {'$set': {'balance': float(snap['balance_by_currency'].get(code, 0))}}, session=session)
    await audit_log(actor_id=actor_id, tenant_id=tenant_id, entity_type='reservation', entity_id=booking_id,
        action='spa_charge_posted', metadata={'source_spa_appointment_id': appt['id'], 'folio_id': folio['id'],
            'charge_id': cid, 'amount': float(net), 'vat_amount': float(vat), 'total': float(gross), 'currency': code,
            'reason': appt.get('notes'), 'actor_name': actor_name, 'business_date': charge['business_date']}, session=session, require_chain=True)
    charge.pop('_id')
    posting.pop('_id')
    return {'charge': charge, 'posting': posting, 'replayed': False}
