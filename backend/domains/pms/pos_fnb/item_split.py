"""Partition unpaid checks and existing kitchen quantities in one transaction."""
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from core.booking_atomicity import is_replica_set_unavailable, with_resource_locks
from domains.pms.pos_fnb.checkout_benefits import fingerprint
from domains.pms.pos_fnb.order_pricing import decimal, reprice_order, rounded


async def split_items(db, tenant, actor, source_id, target_number, quantities, request_id):
    key, digest = f"item-split:{tenant}:{request_id}", fingerprint([source_id, target_number, quantities])

    async def commit(session):
        if session is None:
            raise HTTPException(503, "Adisyon bölme için transaction desteği gerekli.")
        prior = await db.pos_order_item_batches.find_one({"_id": key, "tenant_id": tenant}, session=session)
        if prior:
            if prior["fingerprint"] != digest:
                raise HTTPException(409, "Bölme anahtarı farklı içerikle kullanılmış.")
            return {**prior["result"], "idempotent": True}
        order = await db.pos_orders.find_one({"tenant_id": tenant, "id": source_id}, session=session)
        if not order:
            raise HTTPException(404, "Adisyon bulunamadı.")
        settings = await db.tenant_settings.find_one({"tenant_id": tenant}, session=session)
        day = str((settings or {}).get("business_date") or "")[:10]
        if (not day or str(order.get("business_date") or "")[:10] != day or order.get("status") not in {"pending", "preparing", "ready"}
                or order.get("payment_status") != "unpaid" or order.get("order_type") != "dine_in" or order.get("booking_id")
                or not order.get("table_number") or not order.get("outlet_id") or not order.get("currency")):
            raise HTTPException(409, "Yalnız açık iş günündeki ödenmemiş restoran adisyonu bölünebilir.")
        if order.get("adjustments") or any(order.get(f) for f in ("discount_amount", "service_charge_amount", "tip_amount", "stock_consumption_status", "stock_restore_status")):
            raise HTTPException(409, "İndirim, servis veya stok işlemi olan adisyon önce mutabık hale getirilmeli.")
        if await db.pos_transactions.find_one({"tenant_id": tenant, "order_id": source_id}, session=session):
            raise HTTPException(409, "Finansal hareketi olan adisyon bölünemez.")
        source_table = await db.table_layouts.find_one({"tenant_id": tenant, "outlet_id": order["outlet_id"], "table_number": str(order["table_number"])}, session=session)
        target = await db.table_layouts.find_one({"tenant_id": tenant, "outlet_id": order["outlet_id"], "table_number": str(target_number)}, session=session)
        if (str(target_number) == str(order["table_number"]) or not source_table or source_table.get("status") != "occupied"
                or source_table.get("current_order_id") != source_id or source_table.get("current_transaction_id") or not target
                or target.get("status") != "available" or target.get("current_order_id") or target.get("current_transaction_id")):
            raise HTTPException(409, "Farklı boş masa seçin; kaynak veya hedef masa değişmiş olabilir.")
        lines = order.get("order_items") or []
        ids = [r.get("line_id") for r in lines]
        if not lines or any(not v for v in ids) or len(set(ids)) != len(ids):
            raise HTTPException(409, "Kalem kimlikleri doğrulanamadı.")
        if not quantities or set(quantities) - set(ids) or any(type(q) is not int or q <= 0 for q in quantities.values()):
            raise HTTPException(422, "Mevcut kalemlerden pozitif tam adet seçin.")
        left_items, right_items, tickets = [], [], []
        for line in lines:
            qty, original = quantities.get(line["line_id"], 0), line.get("quantity")
            if type(original) is not int or original <= 0 or qty > original:
                raise HTTPException(422, "Bölünecek adet mevcut adedi aşamaz.")
            if not qty:
                left_items.append(deepcopy(line))
                continue
            rows = await db.kitchen_orders.find({"tenant_id": tenant, "order_id": source_id, "line_id": line["line_id"]}, session=session).to_list(None)
            if len(rows) != 1 or rows[0].get("quantity") != original or rows[0].get("items") or rows[0].get("status") not in {"pending", "preparing", "ready", "served"}:
                raise HTTPException(409, "Mutfak kalem adedi doğrulanamadı; bölme yapılmadı.")
            total = rounded(line.get("total", decimal(line.get("unit_price")) * original))
            amount = rounded(total * qty / original)
            piece = {**line, "quantity": qty, "total": float(amount), "split_from_order_id": source_id}
            if qty < original:
                piece["line_id"] = str(uuid4())
                left_items.append({**line, "quantity": original - qty, "total": float(total - amount)})
            right_items.append(piece)
            tickets.append((rows[0], piece, original - qty))
        if not left_items:
            raise HTTPException(422, "Kaynakta en az bir ürün bırakın; tamamı için masa aktarımını kullanın.")
        before, left, right = reprice_order(order), reprice_order(order, left_items), reprice_order(order, right_items)
        if rounded(before["grand_total"]) != rounded(order.get("grand_total")) or any(rounded(left[f]) + rounded(right[f]) != rounded(before[f]) for f in ("total_amount", "tax_amount", "grand_total")):
            raise HTTPException(409, "Bölme toplamı veya vergisi özgün adisyonla uyuşmuyor.")
        target_id, now, number = str(uuid4()), datetime.now(UTC).isoformat(), f"ORD-SPLIT-{uuid4().hex[:12].upper()}"
        event = {"id": key, "source_order_id": source_id, "target_order_id": target_id, "quantities": quantities, "actor_id": actor, "at": now, "before_items": lines}
        new_order = {f: deepcopy(order[f]) for f in ("tenant_id", "outlet_id", "order_type", "guest_name", "currency", "business_date") if f in order}
        new_order.update({"id": target_id, "order_number": number, "table_number": str(target_number), "order_items": right_items, **right,
            "status": order["status"], "payment_status": "unpaid", "created_by": actor, "created_at": now, "split_from_order_id": source_id})
        changed = await db.pos_orders.update_one({"tenant_id": tenant, "id": source_id, "status": order["status"], "payment_status": "unpaid", "order_items": lines, "grand_total": order["grand_total"], "adjustments": order.get("adjustments")},
            {"$set": {"order_items": left_items, **left, "updated_at": now}, "$unset": {"stock_requirements": ""}, "$push": {"item_splits": event}}, session=session)
        if changed.matched_count != 1:
            raise HTTPException(409, "Adisyon değişti; bölme iptal edildi.")
        await db.pos_orders.insert_one(new_order, session=session)
        claimed = await db.table_layouts.update_one({"tenant_id": tenant, "id": target["id"], "status": "available", "current_order_id": target.get("current_order_id"), "current_transaction_id": target.get("current_transaction_id")},
            {"$set": {"status": "occupied", "current_order_id": target_id, "opened_at": now}}, session=session)
        touched = await db.table_layouts.update_one({"tenant_id": tenant, "id": source_table["id"], "status": "occupied", "current_order_id": source_id}, {"$set": {"updated_at": now}}, session=session)
        if claimed.matched_count != 1 or touched.matched_count != 1:
            raise HTTPException(409, "Masa değişti; bölme iptal edildi.")
        for ticket, piece, remaining in tickets:
            match = {"tenant_id": tenant, "id": ticket["id"], "order_id": source_id, "quantity": ticket["quantity"], "status": ticket["status"]}
            fields = {"order_id": target_id, "order_number": number, "table_number": str(target_number), "line_id": piece["line_id"], "quantity": piece["quantity"], "split_from_order_id": source_id, "split_request_id": key, "updated_at": now}
            if remaining:
                changed = await db.kitchen_orders.update_one(match, {"$set": {"quantity": remaining, "updated_at": now}}, session=session)
                copy = {k: deepcopy(v) for k, v in ticket.items() if k != "_id"}
                copy.update({"id": str(uuid4()), **fields, "split_from_ticket_id": ticket["id"]})
                await db.kitchen_orders.insert_one(copy, session=session)
            else:
                changed = await db.kitchen_orders.update_one(match, {"$set": fields}, session=session)
            if changed.matched_count != 1:
                raise HTTPException(409, "Mutfak kaydı değişti; bölme iptal edildi.")
        result = {"source_order_id": source_id, "target_order_id": target_id, "source_total": left["grand_total"], "target_total": right["grand_total"], "to_table": str(target_number), "idempotent": False}
        await db.pos_order_item_batches.insert_one({"_id": key, "tenant_id": tenant, "fingerprint": digest, "event": event, "result": result}, session=session)
        return result

    try:
        return await with_resource_locks(client=db.client, db=db, tenant_id=tenant, locks_collection="folio_locks", resources=[("pos_order", source_id)], callback=commit)
    except Exception as exc:
        if is_replica_set_unavailable(exc):
            raise HTTPException(503, "Adisyon bölme için transaction desteği gerekli.") from exc
        raise
