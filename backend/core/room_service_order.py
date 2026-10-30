"""Authenticated guest orders use a persisted menu, never browser prices/tax."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException

from core.booking_atomicity import with_resource_locks
from core.department_folio import money, post_source_charge
from core.guest_property import room_property_id
from core.guest_service_folio import _fingerprint, inclusive_tax
from core.report_cache import invalidate_financial_report_caches
from core.scheduled_guest_services import timezone_for


async def property_for_booking(db, tenant_id, booking, session=None):
    room = await db.rooms.find_one({"tenant_id": tenant_id, "id": booking.get("room_id")}, session=session) or {}
    if not room or room.get("is_active") is False:
        return None
    return room_property_id(tenant_id, room, booking)


def qr_menu_item(row):
    return {
        "id": f"qr:{row['property_id']}:{row['service_code']}",
        "name": (row.get("labels") or {}).get("tr") or (row.get("labels") or {}).get("en") or row["service_code"],
        "price": float(Decimal(row["unit_price_minor"]) / 100),
        "currency": row["currency"],
        "tax_rate": row.get("tax_rate"),
        "category": "Oda servisi",
        "available": True,
    }


async def menu_for_booking(db, tenant_id, booking=None):
    items = await db.room_service_menu.find({"tenant_id": tenant_id, "available": True}, {"_id": 0}).to_list(501)
    if booking:
        pid = await property_for_booking(db, tenant_id, booking)
        if pid:
            rows = await db.guest_service_items.find({"tenant_id": tenant_id, "property_id": pid, "enabled": True, "room_charge_enabled": True, "department_code": "fnb"}, {"_id": 0}).to_list(501)
            items.extend(qr_menu_item(row) for row in rows)
    if len(items) > 500:
        raise HTTPException(503, "Menü sorgu sınırına ulaştı; kısmi menü gösterilmedi")
    return items


async def place_order(db, tenant_id, body, actor_id, expected_guest_id=None):
    if not body.request_id or body.confirm_room_charge is not True:
        raise HTTPException(409, "Sipariş anahtarı ve oda hesabına yazım onayı gerekli; uygulamayı güncelleyin")
    oid = str(uuid5(NAMESPACE_URL, f"syroce:room-order:{tenant_id}:{body.booking_id}:{body.request_id}"))
    request_hash = _fingerprint(body.model_dump())
    await db.room_service_orders.create_index([("tenant_id", 1), ("id", 1)], unique=True)

    async def transaction(session):
        prior = await db.room_service_orders.find_one({"tenant_id": tenant_id, "id": oid}, session=session)
        if prior:
            if prior.get("request_hash") != request_hash:
                raise HTTPException(409, "Aynı sipariş anahtarı farklı içerikle kullanılamaz")
            prior.pop("_id", None)
            return prior, True
        booking = await db.bookings.find_one({"tenant_id": tenant_id, "id": body.booking_id, "status": "checked_in"}, session=session)
        if not booking:
            raise HTTPException(409, "Sipariş için aynı tesiste aktif konaklama gerekli")
        if expected_guest_id is not None and booking.get("guest_id") != expected_guest_id:
            raise HTTPException(409, "Konaklamanın misafir bağlantısı değişti; hesabı yenileyin")
        items, charges, seen = [], [], set()
        now = datetime.now(UTC)
        service_at = datetime.fromisoformat(body.service_at).astimezone(await timezone_for(db, tenant_id, session)) if body.service_at else None
        for line in body.items:
            item_id, quantity = line.get("id"), line.get("quantity")
            if not isinstance(item_id, str) or not item_id or item_id in seen or type(quantity) is not int or not 1 <= quantity <= 20:
                raise HTTPException(422, "Sipariş ürünleri tekil ve miktar 1–20 arasında olmalı")
            seen.add(item_id)
            menu = await db.room_service_menu.find_one({"tenant_id": tenant_id, "id": item_id, "available": True}, session=session)
            if item_id.startswith("qr:"):
                parts = item_id.split(":", 2)
                if len(parts) != 3:
                    raise HTTPException(422, "Ürün kimliği geçersiz")
                _, pid, code = parts
                if pid != await property_for_booking(db, tenant_id, booking, session):
                    raise HTTPException(409, "Oda servisi menüsü konaklamanın tesisine ait değil")
                product = await db.guest_service_items.find_one(
                    {"tenant_id": tenant_id, "property_id": pid, "service_code": code, "enabled": True, "room_charge_enabled": True, "department_code": "fnb"}, session=session
                )
                menu = qr_menu_item(product) if product else None
            if not menu:
                raise HTTPException(409, "Ürün menüde yok veya satışa kapalı; menüyü yenileyin")
            code = menu.get("currency")
            if not code or str(line.get("currency") or "").upper() != str(code).upper() or money(line.get("price")) != money(menu.get("price")):
                raise HTTPException(409, "Onaylanan fiyat/para birimi güncel menüyle uyuşmuyor; menüyü yenileyin")
            gross = money(menu["price"]) * quantity
            tax = inclusive_tax(gross, menu.get("tax_rate"))
            source = {
                "kind": "room_service_order",
                "id": f"{oid}:{item_id}",
                "booking_id": body.booking_id,
                "folio_id": body.folio_id,
                "currency": code,
                "gross": str(gross),
                "tax": str(tax) if tax is not None else None,
                "category": "room_service",
                "description": "Oda servisi — " + str(menu.get("name") or item_id),
                "reason": "Misafir sipariş ve oda hesabına yazım onayı; " + oid,
                "service_date": service_at.date().isoformat() if service_at else None,
                "service_time": service_at.strftime("%H:%M") if service_at else None,
            }
            posted = await post_source_charge(db, tenant_id, source, actor_id, session=session)
            charges.append(posted["charge"])
            items.append(
                {
                    "id": item_id,
                    "name": menu.get("name"),
                    "price": float(money(menu["price"])),
                    "quantity": quantity,
                    "currency": code,
                    "tax_rate": menu.get("tax_rate"),
                    "menu_snapshot_hash": _fingerprint(menu),
                }
            )
        if not items:
            raise HTTPException(422, "Boş sipariş gönderilemez")
        order = {
            "_id": f"room-order:{tenant_id}:{oid}",
            "id": oid,
            "tenant_id": tenant_id,
            "booking_id": body.booking_id,
            "room_id": booking.get("room_id"),
            "guest_id": booking.get("guest_id"),
            "created_by": actor_id,
            "items": items,
            "total_amount": float(sum(Decimal(str(row["total"])) for row in charges)),
            "currency": charges[0]["currency"],
            "folio_id": charges[0]["folio_id"],
            "folio_charge_ids": [row["id"] for row in charges],
            "business_date": charges[0]["business_date"],
            "request_hash": request_hash,
            "request_id": body.request_id,
            "room_charge_consent": True,
            "special_instructions": body.special_instructions,
            "service_at": body.service_at,
            "status": "pending",
            "ordered_at": now.isoformat(),
            "estimated_delivery": (now + timedelta(minutes=30)).isoformat(),
        }
        await db.room_service_orders.insert_one(dict(order), session=session)
        order.pop("_id")
        return order, False

    result = await with_resource_locks(
        client=db.client, db=db, tenant_id=tenant_id, locks_collection="folio_locks", resources=[("room_service_order", oid), ("booking", body.booking_id)], callback=transaction
    )
    invalidate_financial_report_caches(tenant_id)
    return result


async def change_order_status(db, tenant_id, order_id, status, actor_id):
    from core.audit_chain import append_audit_log
    from shared_kernel.audit_helper import build_audit_entry

    async def transaction(session):
        row = await db.room_service_orders.find_one({"tenant_id": tenant_id, "id": order_id}, session=session)
        if not row:
            raise HTTPException(404, "Sipariş bulunamadı")
        previous = row.get("status")
        if previous == status:
            row.pop("_id", None)
            return row, True
        ranks = {"pending": 0, "confirmed": 1, "preparing": 2, "delivered": 3}
        if previous in {"cancelled", "delivered"} or (status != "cancelled" and ranks.get(status, -1) <= ranks.get(previous, -1)):
            raise HTTPException(409, "Sipariş durumu geri alınamaz")
        if status == "cancelled":
            ids = row.get("folio_charge_ids") or []
            charges = await db.folio_charges.find({"tenant_id": tenant_id, "id": {"$in": ids}}, session=session).to_list(len(ids))
            if len(charges) != len(ids) or any(not charge.get("voided") for charge in charges):
                raise HTTPException(409, "Önce yetkili folyo kalem iptal/iade akışı tamamlanmalı; ücretler değiştirilmedi")
        update = {"status": status, "updated_at": datetime.now(UTC).isoformat(), "updated_by": actor_id}
        if status == "delivered":
            update["delivered_at"] = update["updated_at"]
        await db.room_service_orders.update_one({"_id": row["_id"]}, {"$set": update}, session=session)
        await append_audit_log(
            db,
            build_audit_entry(
                actor_id,
                tenant_id,
                "room_service_order",
                order_id,
                "room_service_order_status_changed",
                {"before_status": previous, "after_status": status, "delivered_at": update.get("delivered_at"), "reason": "Operatör sipariş durum geçişi"},
            ),
            session=session,
            require_chain=True,
        )
        row.update(update)
        row.pop("_id", None)
        return row, False

    return await with_resource_locks(client=db.client, db=db, tenant_id=tenant_id, locks_collection="folio_locks", resources=[("room_service_order", order_id)], callback=transaction)
