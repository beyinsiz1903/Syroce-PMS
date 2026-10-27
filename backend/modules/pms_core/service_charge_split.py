"""Atomic service-item split. Never transfer room nights, tax debt or payments.

Original revenue day/category and every known tax component are conserved.
Unknown legacy tax is kept unknown rather than replaced with invented zeroes.
The caller holds both reservation financial locks in one Mongo transaction.
"""
import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException

from modules.pms_core.folio_selection import select_booking_folio
from modules.pms_core.receivable_reporting import folio_snapshots
from modules.pms_core.report_money import currency_code, money
from shared_kernel.audit_helper import audit_log


def public_result(result):
    """Exclude Mongo's private insert identity, including older replay rows.

    Motor/PyMongo adds ``_id`` to an inserted dict in place. That identity
    must never leak into the nested HTTP result (ObjectId is not JSON).
    """
    return {**result, "new_charge": {key: value for key, value in result["new_charge"].items() if key != "_id"}}


def cents(value):
    try:
        number = money(value)
    except (ArithmeticError, ValueError, TypeError):
        raise HTTPException(409, "Masraf tutarı doğrulanamadı; önce mutabakat gerekli") from None
    if number != number.quantize(Decimal(".01"), rounding=ROUND_HALF_UP):
        raise HTTPException(409, "Masraf kuruş hassasiyetinde değil; önce mutabakat gerekli")
    return number


def partition(row, amount, *, extra=False):
    """Return source remainder and target part with exact component sums."""
    # Canonical POS/SPA/minibar lines store VAT separately; tax_amount is
    # non-VAT tax. Older manual lines use tax_amount as the combined tax.
    # Normalize ONLY for the existing cent allocator, then restore the source
    # schema. Never add VAT twice or reject a valid net + VAT = gross line.
    components = row.get('tax_breakdown')
    if isinstance(components, dict) and row.get('vat_amount') is not None and row.get('tax_amount') is not None:
        if any(value is None or isinstance(value, (dict, list, bool)) for value in components.values()):
            raise HTTPException(409, 'Masraf vergi kırılımı doğrulanamadı')
        total_tax = sum((cents(value) for value in components.values()), Decimal(0))
        vat = cents(row['vat_amount'])
        if vat and 'vat' in components and vat == cents(components['vat']) and cents(row['tax_amount']) + vat == total_tax:
            combined = {**row, 'tax_amount': float(total_tax)}
            left, right = partition(combined, amount, extra=extra)
            for part in (left, right):
                part['tax_amount'] = float(money(part['tax_amount']) - money(part['vat_amount']))
            return left, right
    total = cents(next((row[k] for k in ("total", "charge_amount", "amount") if row.get(k) is not None), 0))
    amount = cents(amount)
    if total <= 0 or not 0 < amount <= total:
        raise HTTPException(409, "Aktarım tutarı masrafın kalan tutarını aşamaz")
    left, right = deepcopy(row), deepcopy(row)
    fields = ["total", "amount", "subtotal", "discount_amount", "tax_amount", "vat_amount", "charge_amount", "entered_amount", "entered_total"]
    normalized = dict(row)
    # Booking extras store a unit amount, unlike posted folio net line amounts.
    if extra and row.get("amount") is not None:
        normalized["amount"] = money(row["amount"]) * money(row.get("quantity", 1))
        if row.get("tax_amount") is None and cents(normalized["amount"]) != total:
            raise HTTPException(409, "Eski ek ücretin birim/satır tutarı belirsiz; önce mutabakat gerekli")
    if extra and row.get("entered_amount") is not None:
        normalized["entered_amount"] = money(row["entered_amount"]) * money(row.get("quantity", 1))
    if not extra and row.get("tax_amount") is not None and row.get("amount") is not None:
        if cents(row["amount"]) + cents(row["tax_amount"]) != total:
            raise HTTPException(409, "Masraf net/vergi/toplam tutarları mutabık değil")
    normalized["total"] = total
    for key in fields:
        if normalized.get(key) is None:
            continue
        original = cents(normalized[key])
        if original < 0:
            raise HTTPException(409, "Negatif masraf bileşeni bu akışta taşınamaz")
        part = (original * amount / total).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        left[key], right[key] = float(original - part), float(part)
    # Rounding the net and tax independently can manufacture a cent (e.g.
    # splitting a two-cent line with one-cent tax in half). Tax gets its
    # rounded share; net is the exact residual, with totals conserved.
    if row.get("tax_amount") is not None and normalized.get("amount") is not None:
        if cents(normalized["amount"]) + cents(row["tax_amount"]) != total:
            raise HTTPException(409, "Masraf net/vergi/toplam tutarları mutabık değil")
        for item in (left, right):
            item["amount"] = float(money(item["total"]) - money(item["tax_amount"]))
        if normalized.get("subtotal") is not None:
            if cents(normalized["subtotal"]) - cents(normalized.get("discount_amount", 0)) != cents(normalized["amount"]):
                raise HTTPException(409, "Masraf ara toplam/indirim tutarları mutabık değil")
            for item in (left, right):
                item["subtotal"] = float(money(item["amount"]) + money(item.get("discount_amount", 0)))
    if row.get("tax_breakdown") is not None:
        if not isinstance(row["tax_breakdown"], dict) or any(v is None or isinstance(v, (dict, list, bool)) for v in row["tax_breakdown"].values()):
            raise HTTPException(409, "Bu vergi kırılımı için kontrollü düzeltme gerekli")
        left["tax_breakdown"], right["tax_breakdown"] = {}, {}
        components = row["tax_breakdown"]
        if row.get("tax_amount") is None or sum((cents(v) for v in components.values()), Decimal(0)) != cents(row["tax_amount"]):
            raise HTTPException(409, "Masraf vergi kırılımı mutabık değil")
        originals = {key: int(cents(value) * 100) for key, value in components.items()}
        if any(value < 0 for value in originals.values()):
            raise HTTPException(409, "Negatif vergi bileşeni bu akışta taşınamaz")
        tax_sum, wanted = sum(originals.values()), int(money(right["tax_amount"]) * 100)
        shares = {key: divmod(value * wanted, tax_sum) if tax_sum else (0, 0) for key, value in originals.items()}
        allocated = {key: share[0] for key, share in shares.items()}
        for key in sorted(shares, key=lambda key: (-shares[key][1], key))[:wanted - sum(allocated.values())]:
            allocated[key] += 1
        for key, value in originals.items():
            left["tax_breakdown"][key], right["tax_breakdown"][key] = (value - allocated[key]) / 100, allocated[key] / 100
        for item in (left, right):
            if row.get("vat_amount") is not None and "vat" in components and cents(row["vat_amount"]) == cents(components["vat"]):
                item["vat_amount"] = item["tax_breakdown"]["vat"]
    for item in (left, right):
        item["quantity"] = 1
        item["unit_price"] = item.get("subtotal", item.get("amount", item["total"]))
    return left, right


async def split_service_charge(database, tenant_id, actor, booking_id, body, operation_id, *, session, actor_id=None):
    if session is None:
        raise HTTPException(503, "Masraf aktarımı için transaction desteği gerekli")
    digest = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    op_key = f"service-split:{tenant_id}:{operation_id}"
    previous = await database.folio_operations.find_one({"_id": op_key, "tenant_id": tenant_id}, session=session)
    if previous:
        if previous["fingerprint"] != digest:
            raise HTTPException(409, "Aktarım anahtarı farklı bilgilerle kullanılmış")
        return {**public_result(previous["result"]), "replayed": True}
    query = {"tenant_id": tenant_id, "booking_id": booking_id, "id": body.charge_id, "voided": {"$ne": True}}
    source_collection = database.folio_charges
    charge = await source_collection.find_one(query, {"_id": 0}, session=session)
    extra = charge is None
    if extra:
        source_collection = database.extra_charges
        charge = await source_collection.find_one(query, {"_id": 0}, session=session)
    if not charge:
        raise HTTPException(404, "Masraf bu rezervasyonda bulunamadı veya iptal edilmiş")
    category = str(charge.get("charge_category") or charge.get("category") or "other").lower()
    if category in {"room", "room_charge", "tax", "city_tax", "split_adjustment", "opening_balance"} or charge.get("charge_type") == "room_charge":
        raise HTTPException(409, "Oda gecesi/vergi/açılış borcu bu hizmet aktarımında bölünemez")
    source_booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": booking_id}, session=session)
    target_folio = await database.folios.find_one({"tenant_id": tenant_id, "id": body.target_folio_id}, session=session) if body.target_folio_id else None
    target_id = body.target_booking_id or (target_folio or {}).get("booking_id")
    if not target_id or (target_folio and target_folio.get("booking_id") != target_id):
        raise HTTPException(422, "Hedef rezervasyon/folyo seçimi geçersiz")
    target_booking = await database.bookings.find_one({"tenant_id": tenant_id, "id": target_id}, session=session)
    if not source_booking or not target_booking:
        raise HTTPException(404, "Kaynak veya hedef rezervasyon bulunamadı")
    if any(b.get("status") not in {"confirmed", "guaranteed", "checked_in"} for b in [source_booking, target_booking]):
        raise HTTPException(409, "Yalnız açık rezervasyonlar arasında aktarım yapılabilir")
    if target_booking.get("is_complimentary") and target_booking.get("complimentary_scope") == "full":
        raise HTTPException(409, "Full comp rezervasyona borç aktarılamaz; önce ikram kapsamını uzlaştırın")
    source = await select_booking_folio(database, tenant_id, booking_id, charge.get("folio_id"), session=session)
    target = await select_booking_folio(database, tenant_id, target_id, body.target_folio_id, session=session)
    if not source or not target or source["id"] == target["id"]:
        raise HTTPException(409, "Farklı açık kaynak ve hedef folyolar seçin")
    code = source.get("currency") or source_booking.get("currency")
    target_code = target.get("currency") or target_booking.get("currency")
    if not code or not target_code or currency_code(code) != currency_code(target_code) or (charge.get("currency") and currency_code(charge["currency"]) != currency_code(code)):
        raise HTTPException(409, "Masraf ve folyoların aynı para birimi doğrulanmalı")
    invoice = await database.invoices.find_one({"tenant_id": tenant_id, "voided": {"$ne": True}, "status": {"$nin": ["cancelled", "canceled", "void", "voided"]},
        "$or": [{"booking_id": {"$in": [booking_id, target_id]}}, {"folio_id": {"$in": [source["id"], target["id"]]}},
                {"folio_ids": {"$in": [source["id"], target["id"]]}}]}, session=session)
    if invoice or charge.get("invoice_id") or source.get("invoice_id") or target.get("invoice_id"):
        raise HTTPException(409, "Faturaya bağlı masraf önce fatura düzeltme akışında uzlaştırılmalı")
    try:
        day = date.fromisoformat(str(charge.get("business_date"))[:10]).isoformat()
    except ValueError:
        raise HTTPException(409, "Masrafın muhasebe günü eksik; tarih tahminiyle aktarım yapılamaz") from None
    left, right = partition(charge, body.split_amount, extra=extra)
    before = await folio_snapshots(database, tenant_id, [source, target], fallback_currency=code, session=session)
    source_snap = before[source["id"]]
    if any(c != code and v for snap in before.values() for c, v in snap["balance_by_currency"].items()):
        raise HTTPException(409, "Kaynak folyo önce para birimi mutabakatına alınmalı")
    # Extras are outside the folio projection, but remain part of reservation debt.
    available = money(source_snap["balance_by_currency"].get(code, 0))
    if extra:
        extras = await database.extra_charges.find({"tenant_id": tenant_id, "booking_id": booking_id, "voided": {"$ne": True}}, {"_id": 0}, session=session).to_list(None)
        available += sum((money(next((e[k] for k in ("total", "charge_amount", "amount") if e.get(k) is not None), 0)) for e in extras), Decimal(0))
    if money(body.split_amount) > available:
        raise HTTPException(409, "Tahsil edilmiş masraf borç olarak tekrar aktarılamaz")
    now = datetime.now(UTC).isoformat()
    right.update({"id": str(operation_id), "booking_id": target_id, "folio_id": target["id"], "currency": code,
        "charge_category": category, "business_date": day, "split_from_charge_id": body.charge_id,
        "split_from_booking_id": booking_id, "transferred_by": actor, "transferred_at": now})
    if 'line_no' in charge:
        # Keep canonical source-line keys unchanged. A transfer is a new
        # folio partition, NOT a redelivery of that product line. Retain the
        # order/consumption source so refunds/reporting still find every part.
        # UUID-namespaced identities do not require weakening any unique index.
        right['source_line_no'] = charge.get('source_line_no', charge['line_no'])
        right['line_no'] = 'split:' + str(operation_id)
    right.pop("_id", None)
    changed = await source_collection.update_one(query, {"$set": {key: left[key] for key in ["quantity", "unit_price", "total", "amount", "subtotal", "discount_amount", "tax_amount", "vat_amount", "charge_amount", "tax_breakdown"] if key in left}}, session=session)
    if changed.matched_count != 1:
        raise HTTPException(409, "Masraf değişti; aktarım iptal edildi")
    # Insert a copy: the driver mutates its argument with a private ObjectId.
    await database.folio_charges.insert_one(deepcopy(right), session=session)
    snapshots = await folio_snapshots(database, tenant_id, [source, target], fallback_currency=code, session=session)
    for folio in [source, target]:
        balance = snapshots[folio["id"]]["balance_by_currency"].get(code, 0)
        updated = await database.folios.update_one({"tenant_id": tenant_id, "id": folio["id"], "status": "open"}, {"$set": {"balance": balance}}, session=session)
        if updated.matched_count != 1:
            raise HTTPException(409, "Folyo durumu değişti; aktarım iptal edildi")
    result = {"success": True, "new_charge": right, "remaining_amount": left["total"], "replayed": False}
    await database.folio_operations.insert_one({"_id": op_key, "id": str(operation_id), "tenant_id": tenant_id, "operation_type": "split",
        "from_booking_id": booking_id, "to_booking_id": target_id, "from_folio_id": source["id"], "to_folio_id": target["id"],
        "charge_ids": [body.charge_id], "amount": body.split_amount, "currency": code, "reason": body.reason,
        "performed_by": actor, "performed_at": now, "original_charge": charge, "fingerprint": digest, "result": result}, session=session)
    metadata = {'operation_id': str(operation_id), 'source_booking_id': booking_id, 'target_booking_id': target_id,
        'source_folio_id': source['id'], 'target_folio_id': target['id'], 'source_charge_id': body.charge_id,
        'target_charge_id': right['id'], 'amount': body.split_amount, 'currency': code, 'reason': body.reason,
        'actor_name': actor, 'business_date': day}
    for bid, action in ((booking_id, 'charge_split'), (target_id, 'charge_received')):
        await audit_log(actor_id=actor_id or actor, tenant_id=tenant_id, entity_type='reservation', entity_id=bid,
            action=action, metadata=metadata, session=session, require_chain=True)
    return result
