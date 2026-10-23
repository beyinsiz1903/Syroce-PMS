"""Resolve a financial target without silently selecting the first window."""
from fastapi import HTTPException


async def select_booking_folio(database, tenant_id, booking_id, folio_id=None, *, session=None):
    query = {"tenant_id": tenant_id, "booking_id": booking_id}
    kwargs = {"session": session} if session is not None else {}
    if folio_id:
        folio = await database.folios.find_one({**query, "id": folio_id}, {"_id": 0}, **kwargs)
        if not folio:
            raise HTTPException(404, "Seçilen folyo bu rezervasyona/tesise ait değil veya bulunamadı")
        if folio.get("status") != "open":
            raise HTTPException(409, "Seçilen folyo açık değil")
        return folio
    folios = await database.folios.find({**query, "status": "open"}, {"_id": 0}, **kwargs).to_list(2)
    if len(folios) > 1:
        raise HTTPException(409, "Birden fazla açık folyo var. Rezervasyon detayı → Folyo/Ödeme ekranından hedef folyoyu seçin.")
    return folios[0] if folios else None


async def ensure_folio_transfer_amount(database, tenant_id, folio, amount, currency, *, session=None):
    """AR transfer may settle only posted debt belonging to this window."""
    from modules.pms_core.receivable_reporting import folio_snapshots

    snapshot = (await folio_snapshots(database, tenant_id, [folio], fallback_currency=currency, session=session))[folio["id"]]
    if any(code != snapshot["currency"] and value for code, value in snapshot["balance_by_currency"].items()):
        raise HTTPException(409, "Çok para birimli folyo önce mutabık hale getirilmelidir")
    balance = snapshot["balance_by_currency"].get(snapshot["currency"], 0)
    if amount - balance > 0.005:
        raise HTTPException(409, "Tutar seçilen folyonun açık tahakkuk bakiyesini aşamaz. Önce kalemleri ilgili folyoya yönlendirin.")
