"""Combine two unpaid dine-in checks without creating a sale or another KOT."""

from datetime import UTC, datetime

from fastapi import HTTPException

from core.booking_atomicity import is_replica_set_unavailable, with_resource_locks
from domains.pms.pos_fnb.order_pricing import reprice_order, rounded


async def merge_open_checks(database, tenant_id, actor_id, source_id, target_id):
    if source_id == target_id:
        raise HTTPException(422, "Birleştirilecek adisyonlar farklı olmalı.")

    async def commit(session):
        if session is None:
            raise HTTPException(503, "Masa birleştirme için transaction desteği gerekli.")
        orders = []
        for key in (source_id, target_id):
            order = await database.pos_orders.find_one({"tenant_id": tenant_id, "id": key}, session=session)
            if not order:
                raise HTTPException(404, "Adisyon bulunamadı.")
            orders.append(order)
        source, target = orders
        if source.get("status") == "merged":
            if source.get("merged_into_order_id") != target_id:
                raise HTTPException(409, "Adisyon başka bir masaya birleştirilmiş.")
            return {"source_order_id": source_id, "target_order_id": target_id,
                    "to_table": target.get("table_number"), "idempotent": True}

        settings = await database.tenant_settings.find_one({"tenant_id": tenant_id}, session=session)
        day = str((settings or {}).get("business_date") or "")[:10]
        if not day:
            raise HTTPException(409, "Açık iş günü doğrulanamadı.")
        if not source.get("outlet_id") or source.get("outlet_id") != target.get("outlet_id"):
            raise HTTPException(409, "Yalnız aynı satış noktasının masaları birleştirilebilir.")
        if not source.get("currency") or source.get("currency") != target.get("currency"):
            raise HTTPException(409, "Adisyon para birimleri aynı olmalı.")

        tables = []
        for order in orders:
            if order.get("status") not in {"pending", "preparing", "ready"} or order.get("payment_status") != "unpaid":
                raise HTTPException(409, "Yalnız açık ve ödenmemiş adisyonlar birleştirilebilir.")
            if order.get("order_type") != "dine_in" or not order.get("table_number") or order.get("booking_id"):
                raise HTTPException(409, "Yalnız masaya ait restoran adisyonları birleştirilebilir.")
            if str(order.get("business_date") or "")[:10] != day:
                raise HTTPException(409, "Adisyonlar açık iş gününe ait olmalı.")
            if order.get("adjustments") or any(order.get(field) for field in
                    ("discount_amount", "service_charge_amount", "tip_amount", "stock_consumption_status", "stock_restore_status")):
                raise HTTPException(409, "İndirim, servis bedeli veya ödeme/stok işlemi olan adisyon ayrı sonuçlandırılmalı.")
            sale = await database.pos_transactions.find_one({"tenant_id": tenant_id, "order_id": order["id"]}, session=session)
            if sale:
                raise HTTPException(409, "Finansal hareketi bulunan adisyon birleştirilemez.")
            table = await database.table_layouts.find_one({"tenant_id": tenant_id, "outlet_id": order["outlet_id"],
                "table_number": str(order["table_number"])}, session=session)
            if not table or table.get("current_order_id") != order["id"] or table.get("current_transaction_id") or table.get("status") != "occupied":
                raise HTTPException(409, "Masa veya adisyon değişti; yenileyin.")
            tables.append(table)
            pricing = reprice_order(order)
            if not order.get("order_items") or rounded(pricing["grand_total"]) != rounded(order.get("grand_total")):
                raise HTTPException(409, "Adisyon kalemleri ve toplamı uyuşmuyor; önce mutabakat yapın.")

        source_lines, target_lines = source["order_items"], target["order_items"]
        # Keep every line identity (including modifiers/notes/tax) intact.
        # Repeated products are separate services, not quantities to collapse.
        items = [*target_lines, *[{**line, "merged_from_order_id": source_id} for line in source_lines]]
        line_ids = [line.get("line_id") for line in items]
        if any(not key for key in line_ids) or len(set(line_ids)) != len(line_ids):
            raise HTTPException(409, "Adisyon kalem kimlikleri doğrulanamadı.")
        pricing = reprice_order(target, items)
        if rounded(pricing["grand_total"]) != rounded(source["grand_total"]) + rounded(target["grand_total"]):
            raise HTTPException(409, "Birleştirme toplamı önceki iki adisyonla eşleşmiyor.")
        now = datetime.now(UTC).isoformat()
        event = {"source_order_id": source_id, "source_order_number": source.get("order_number"),
                 "from_table": source["table_number"], "amount": source["grand_total"], "currency": source["currency"],
                 "business_date": day, "merged_at": now, "merged_by": actor_id}
        changed = await database.pos_orders.update_one({"tenant_id": tenant_id, "id": target_id,
            "status": target["status"], "payment_status": "unpaid", "order_items": target_lines,
            "grand_total": target["grand_total"], "adjustments": target.get("adjustments")},
            {"$set": {"order_items": items, **pricing, "updated_at": now}, "$unset": {"stock_requirements": ""},
             "$push": {"merged_checks": event}}, session=session)
        if changed.matched_count != 1:
            raise HTTPException(409, "Hedef adisyon değişti; birleştirme iptal edildi.")
        changed = await database.pos_orders.update_one({"tenant_id": tenant_id, "id": source_id,
            "status": source["status"], "payment_status": "unpaid", "order_items": source_lines,
            "grand_total": source["grand_total"], "adjustments": source.get("adjustments")},
            {"$set": {"status": "merged", "merged_into_order_id": target_id, "merge_event": event, "updated_at": now}}, session=session)
        if changed.matched_count != 1:
            raise HTTPException(409, "Kaynak adisyon değişti; birleştirme iptal edildi.")
        released = await database.table_layouts.update_one({"tenant_id": tenant_id, "id": tables[0]["id"],
            "current_order_id": source_id, "status": "occupied"},
            {"$set": {"status": "available", "current_order_id": None, "opened_at": None}}, session=session)
        if released.matched_count != 1:
            raise HTTPException(409, "Kaynak masa değişti; birleştirme iptal edildi.")
        # Update the target table too: this conflicts with a concurrent table
        # move, while the order CAS conflicts with concurrent payment/void.
        touched = await database.table_layouts.update_one({"tenant_id": tenant_id, "id": tables[1]["id"],
            "current_order_id": target_id, "status": "occupied"}, {"$set": {"updated_at": now}}, session=session)
        if touched.matched_count != 1:
            raise HTTPException(409, "Hedef masa değişti; birleştirme iptal edildi.")
        await database.kitchen_orders.update_many({"tenant_id": tenant_id, "order_id": source_id,
            "status": {"$in": ["pending", "preparing", "ready"]}}, {"$set": {"order_id": target_id,
            "order_number": target.get("order_number"), "merged_from_order_id": source_id,
            "merged_from_order_number": source.get("order_number"),
            "table_number": target["table_number"], "updated_at": now}}, session=session)
        return {"source_order_id": source_id, "target_order_id": target_id, "from_table": source["table_number"],
                "to_table": target["table_number"], "grand_total": pricing["grand_total"], "idempotent": False}

    try:
        return await with_resource_locks(client=database.client, db=database, tenant_id=tenant_id,
            locks_collection="folio_locks", resources=[("pos_order", key) for key in sorted((source_id, target_id))], callback=commit)
    except Exception as exc:
        if is_replica_set_unavailable(exc):
            raise HTTPException(503, "Masa birleştirme için transaction desteği gerekli.") from exc
        raise
