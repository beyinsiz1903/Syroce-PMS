"""Independent nonresident receivable; never invent a room/folio to take money."""
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from core.business_date_service import stamp_open_business_date
from domains.spa.folio import amounts


async def post_external_charge(database, tenant_id, appt, *, session, actor):
    if session is None:
        raise HTTPException(503, 'SPA satış kaydı için atomik işlem desteği gerekli')
    if any(appt.get(key) for key in ('reservation_id', 'folio_id', 'folio_charge_id', 'charge_to_room')):
        raise HTTPException(409, 'Konaklamaya bağlı hizmette oda folyosu akışını kullanın; dış misafir tahsilatıyla karıştırılamaz')
    net, vat, gross, _ = amounts(appt)
    currency = str(appt.get('currency') or '').upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(409, 'Randevunun kayıtlı para birimi eksik')
    identity = f'spa-external:{tenant_id}:{appt["id"]}'
    charge_id = str(uuid5(NAMESPACE_URL, identity))
    existing = await database.extra_charges.find_one({'tenant_id': tenant_id, 'id': charge_id}, session=session)
    if existing:
        if existing.get('voided') or any(existing.get(k) != v for k, v in {
            'source_spa_appointment_id': appt['id'], 'currency': currency, 'total': float(gross),
            'amount': float(net), 'vat_amount': float(vat),
        }.items()):
            raise HTTPException(409, 'SPA kaynak satış kaydı tutar/vergiyle uyuşmuyor; mutabakat gerekli')
        return charge_id
    charge = {
        '_id': identity, 'id': charge_id, 'tenant_id': tenant_id,
        'source_spa_appointment_id': appt['id'], 'source': 'spa_external',
        'charge_category': 'spa', 'charge_type': 'spa', 'quantity': 1,
        'description': 'SPA: ' + str(appt.get('service_name') or 'Hizmet'),
        'guest_name': appt.get('guest_name'), 'amount': float(net), 'subtotal': float(net),
        'total': float(gross), 'vat_amount': float(vat), 'tax_amount': 0,
        'tax_breakdown': {'vat': float(vat)}, 'discount_amount': 0,
        'currency': currency, 'voided': False, 'posted_by': actor,
        'date': appt['completed_at'], 'posted_at': appt['completed_at'],
    }
    await stamp_open_business_date(database, tenant_id, charge)
    await database.extra_charges.insert_one(charge, session=session)
    return charge_id
