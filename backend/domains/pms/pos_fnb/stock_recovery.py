"""Durable POS stock work stored on the order; safe to retry after a lost response."""
import math
from datetime import UTC, datetime

from fastapi import HTTPException

from core.booking_atomicity import with_resource_locks


async def run_stock_job(db, tenant_id, order_id, actor_id, restore=False):
    field = "stock_restore_status" if restore else "stock_consumption_status"
    async def commit(session):
        query = {"tenant_id": tenant_id, "id": order_id}
        order = await db.pos_orders.find_one(query, session=session)
        if not order:
            raise HTTPException(404, "Adisyon bulunamadı.")
        if order.get(field) == "completed":
            return
        now = datetime.now(UTC).isoformat()
        # Writing the order inside the transaction serializes duplicate retry
        # calls with checkout/refund and with each other.
        await db.pos_orders.update_one(query, {"$set": {field: "running"}}, session=session)
        if restore:
            rows = await db.stock_consumptions.find(
                {"tenant_id": tenant_id, "order_id": order_id, "reversed": {"$ne": True}},
                session=session,
            ).to_list(None)
            for row in rows:
                qty = row.get("consumed_quantity", 0)
                if qty:
                    changed = await db.ingredients.update_one(
                        {"tenant_id": tenant_id, "id": row["ingredient_id"]},
                        {"$inc": {"current_stock": qty}, "$set": {"updated_at": now}}, session=session,
                    )
                    if changed.matched_count != 1:
                        raise HTTPException(409, "İade edilecek stok malzemesi bulunamadı.")
                await db.stock_consumptions.update_one(
                    {"tenant_id": tenant_id, "id": row["id"]},
                    {"$set": {"reversed": True, "reversed_at": now, "reversed_by": actor_id}}, session=session,
                )
        else:
            # A full refund can precede a pending stock retry. Never consume
            # ingredients for a sale that has already been fully reversed.
            if order.get("payment_status") != "refunded":
                needs = order.get("stock_requirements")
                if needs is None:
                    raise HTTPException(409, "Stok gereksinimleri hazırlanamadı; yeniden deneyin.")
                for iid, qty in needs.items():
                    # Legacy consumption rows may predate the durable job.
                    prior = await db.stock_consumptions.find_one(
                        {"tenant_id": tenant_id, "order_id": order_id, "ingredient_id": iid}, session=session,
                    )
                    if prior:
                        continue
                    changed = await db.ingredients.update_one(
                        {"tenant_id": tenant_id, "id": iid, "current_stock": {"$gte": qty}},
                        {"$inc": {"current_stock": -qty}, "$set": {"updated_at": now}}, session=session,
                    )
                    if changed.modified_count != 1:
                        raise HTTPException(409, "Malzeme stoğu yetersiz. Stok girişinden sonra yeniden deneyin.")
                    await db.stock_consumptions.insert_one({
                        "id": f"pos:{order_id}:{iid}", "tenant_id": tenant_id, "order_id": order_id,
                        "ingredient_id": iid, "required_quantity": qty, "consumed_quantity": qty,
                        "overdraft_quantity": 0, "reversed": False, "created_at": now, "created_by": actor_id,
                    }, session=session)
        await db.pos_orders.update_one(query, {"$set": {
            field: "completed", field + "_at": now, field + "_error": None,
        }}, session=session)
    try:
        if not restore:
            order = await db.pos_orders.find_one({"tenant_id": tenant_id, "id": order_id})
            if order and order.get("stock_requirements") is None:
                needs = await stock_requirements(db, tenant_id, order)
                await db.pos_orders.update_one(
                    {"tenant_id": tenant_id, "id": order_id, "stock_requirements": {"$exists": False}},
                    {"$set": {"stock_requirements": needs}},
                )
        await with_resource_locks(client=db.client, db=db, tenant_id=tenant_id,
                                  locks_collection="folio_locks", resources=[], callback=commit)
    except Exception as exc:
        message = exc.detail if isinstance(exc, HTTPException) else "Stok güncellenemedi. Bağlantıyı kontrol edip yeniden deneyin."
        await db.pos_orders.update_one({"tenant_id": tenant_id, "id": order_id, field: {"$ne": "completed"}}, {"$set": {
            field: "failed", field + "_error": message,
        }})
        raise


async def stock_requirements(db, tenant_id, order):
    """Freeze the recipe quantities before the first inventory attempt."""
    if not order.get("order_items"):
        return {}
    recipes = await db.recipes.find({"tenant_id": tenant_id}).to_list(None)
    lookup = {}
    for recipe in recipes:
        for key in (recipe.get("id"), recipe.get("menu_item_id"), recipe.get("dish_name"), recipe.get("menu_item_name")):
            if key:
                lookup[str(key).strip().lower()] = recipe
    needs = {}
    for item in order.get("order_items", []):
        recipe = next((lookup[str(item.get(k) or "").strip().lower()] for k in ("recipe_id", "item_id", "item_name")
                       if str(item.get(k) or "").strip().lower() in lookup), None)
        if recipe:
            for line in recipe.get("ingredients", []):
                iid = line.get("ingredient_id")
                qty = float(line.get("quantity", 0)) * float(item.get("quantity", 0))
                if not math.isfinite(qty) or qty < 0 or (qty > 0 and not iid):
                    raise HTTPException(409, "Reçete malzeme veya miktar tanımı geçersiz. Tanımı düzeltip yeniden deneyin.")
                if iid and qty > 0:
                    needs[iid] = round(needs.get(iid, 0) + qty, 4)
    return needs
