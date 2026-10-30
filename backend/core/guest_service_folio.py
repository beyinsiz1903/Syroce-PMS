"""Source-owned Upsell and confirmed QR room-service financial handoffs.

Do not reinterpret old unknown tax as zero, trust browser amounts, select the
first of multiple folios, or automatically migrate unidentifiable legacy debt.
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import HTTPException

from core.booking_atomicity import with_resource_locks
from core.department_folio import money, post_source_charge
from core.report_cache import invalidate_financial_report_caches
from modules.pms_core.revenue_categories import LABELS


def inclusive_tax(gross, rate):
    if rate is None:
        return None
    try:
        rate = Decimal(str(rate))
        if not rate.is_finite() or not 0 <= rate <= 1:
            raise ValueError
    except (ValueError, InvalidOperation):
        raise HTTPException(409, "Kaynak vergi oranı geçersiz") from None
    return money(gross) - (money(gross) / (1 + rate)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


async def accept_upsell(db, tenant_id, offer_id, actor_id):
    async def transaction(session):
        offer = await db.upsell_offers.find_one({"tenant_id": tenant_id, "id": offer_id}, session=session)
        if not offer:
            raise HTTPException(404, "Teklif bulunamadı")
        if offer.get("status") not in {"pending", "accepted"}:
            raise HTTPException(409, "Bu teklif kabul edilebilir durumda değil")
        if not offer.get("currency"):
            raise HTTPException(409, "Eski teklifin para birimi doğrulanamıyor; açık para birimli yeni teklif gerekli")
        if offer.get("status") == "accepted" and not offer.get("folio_charge_id"):
            raise HTTPException(409, "Eski kabul edilmiş teklif için kaynak mutabakatı gerekli; tekrar ücret yazılmadı")
        expires = offer.get("valid_until")
        if expires and offer.get("status") == "pending":
            try:
                expires = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
            except ValueError:
                raise HTTPException(409, "Teklif geçerlilik tarihi doğrulanamıyor") from None
            if expires < datetime.now(UTC):
                raise HTTPException(409, "Teklifin geçerlilik süresi dolmuş")
        amount = offer.get("price")
        if amount is None:
            amount = offer.get("discounted_price") if offer.get("discounted_price") is not None else offer.get("original_price")
        gross = money(amount)
        category = offer.get("service_category")
        if category is not None and category not in LABELS:
            raise HTTPException(409, "Teklifin hizmet kategorisi doğrulanamıyor")
        source = {
            "kind": "upsell",
            "id": offer_id,
            "booking_id": offer.get("booking_id"),
            "folio_id": offer.get("folio_id"),
            "currency": offer["currency"],
            "gross": str(gross),
            "tax": str(inclusive_tax(gross, offer["tax_rate"])) if offer.get("tax_rate") is not None else None,
            "category": category or "unclassified",
            "description": "Ek hizmet teklifi — " + str(offer.get("target_item") or offer.get("title") or offer.get("type") or "Hizmet"),
            "service_date": offer.get("service_date"),
            "service_time": offer.get("service_time"),
            "reason": offer.get("reason"),
        }
        posted = await post_source_charge(db, tenant_id, source, actor_id, session=session)
        if posted["replayed"] and offer.get("status") != "accepted":
            raise HTTPException(409, "Teklif durumu mevcut ücret kaynağıyla uyuşmuyor")
        if not posted["replayed"]:
            await db.upsell_offers.update_one(
                {"tenant_id": tenant_id, "id": offer_id},
                {
                    "$set": {
                        "status": "accepted",
                        "folio_id": posted["charge"]["folio_id"],
                        "folio_charge_id": posted["charge"]["id"],
                        "updated_at": datetime.now(UTC).isoformat(),
                        "updated_by": actor_id,
                    }
                },
                session=session,
            )
        return {
            "message": "Teklif kabul edildi",
            "offer_id": offer_id,
            "status": "accepted",
            "folio_charge_id": posted["charge"]["id"],
            "replayed": posted["replayed"],
            "total": posted["charge"]["total"],
            "currency": posted["charge"]["currency"],
        }

    offer = await db.upsell_offers.find_one({"tenant_id": tenant_id, "id": offer_id}) or {}
    result = await with_resource_locks(
        client=db.client, db=db, tenant_id=tenant_id, locks_collection="folio_locks", resources=[("upsell", offer_id), ("booking", offer.get("booking_id"))], callback=transaction
    )
    invalidate_financial_report_caches(tenant_id)
    return result


def _fingerprint(value):
    def normalized(item):
        if isinstance(item, datetime):
            item = item.astimezone(UTC) if item.tzinfo else item.replace(tzinfo=UTC)
            return item.replace(microsecond=item.microsecond // 1000 * 1000).isoformat()
        if isinstance(item, dict):
            return {key: normalized(val) for key, val in item.items()}
        if isinstance(item, list):
            return [normalized(val) for val in item]
        return item

    return hashlib.sha256(json.dumps(normalized(value), sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


async def post_qr_submission(db, tenant_id, booking_id, group_id, prepared_items):
    async def transaction(session):
        ledger = await db.guest_service_submissions.find_one({"tenant_id": tenant_id, "booking_id": booking_id, "submission_group_id": group_id}, session=session)
        if not ledger or _fingerprint(ledger.get("prepared_items")) != _fingerprint(prepared_items):
            raise HTTPException(409, "Oda servisi kalıcı kaynak görüntüsü uyuşmuyor")
        if ledger.get("room_charge_consent") is not True:
            raise HTTPException(409, "Oda hesabına yazım için kalıcı misafir onayı gerekli")
        codes = [item.get("service_code") for item in ledger["prepared_items"]]
        if any(not code for code in codes) or len(codes) != len(set(codes)):
            raise HTTPException(409, "Oda servisi kaynak satırları tekil değil")
        posted = []
        for item in ledger["prepared_items"]:
            bill = item.get("room_charge")
            if not bill:
                continue
            if item.get("property_id") != ledger.get("property_id") or item.get("booking_id") != booking_id:
                raise HTTPException(409, "Oda servisi tesis/konaklama kaynağı uyuşmuyor")
            minor, quantity = bill.get("unit_price_minor"), bill.get("quantity")
            if type(minor) is not int or minor <= 0 or type(quantity) is not int or quantity < 1 or bill.get("total_minor") != minor * quantity:
                raise HTTPException(409, "Oda servisi fiyat/miktar kaynağı geçersiz")
            sid = f"{group_id}:{item['service_code']}"
            reference = f"qr-room-service:{sid}"
            legacy = await db.folio_charges.find_one({"tenant_id": tenant_id, "external_reference": reference}, session=session)
            if legacy and legacy.get("source_qr_submission_line_id") != sid:
                raise HTTPException(409, "Eski oda servisi ücreti için kaynak mutabakatı gerekli; tekrar ücret yazılmadı")
            gross = Decimal(minor * quantity) / Decimal(100)
            tax = inclusive_tax(gross, bill.get("tax_rate"))
            snapshot = item.get("catalogue_snapshot") or {}
            when = str(snapshot.get("resolved_local_datetime") or "")
            source = {
                "kind": "room_service",
                "id": sid,
                "booking_id": booking_id,
                "folio_id": ledger.get("folio_id"),
                "currency": bill.get("currency"),
                "gross": str(gross),
                "tax": str(tax) if tax is not None else None,
                "description": "[QR Oda Servisi] " + str(item.get("title") or item["service_code"]),
                "service_date": when[:10] or None,
                "service_time": when[11:16] or None,
                "reason": "Misafirin oda hesabına yazım onayı; " + str(ledger.get("submission_reference") or group_id),
                "external_reference": reference,
            }
            result = await post_source_charge(db, tenant_id, source, "guest-qr-room-service", session=session)
            posted.append({"service_code": item["service_code"], "folio_charge_id": result["charge"]["id"], **bill})
        if posted:
            charge = result["charge"]
            await db.guest_service_submissions.update_one(
                {"_id": ledger["_id"], "tenant_id": tenant_id},
                {"$set": {"room_charge_status": "posted", "room_charge_lines": posted, "folio_id": charge["folio_id"], "updated_at": datetime.now(UTC)}},
                session=session,
            )
        return posted

    result = await with_resource_locks(
        client=db.client, db=db, tenant_id=tenant_id, locks_collection="folio_locks", resources=[("qr_submission", group_id), ("booking", booking_id)], callback=transaction
    )
    invalidate_financial_report_caches(tenant_id)
    return result
