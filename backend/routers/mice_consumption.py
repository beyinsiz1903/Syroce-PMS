"""Confirmed kitchen production -> shared ingredient stock and frozen costs."""
import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.booking_atomicity import with_resource_locks
from core.entitlements.enforcement import require_feature
from core.mice_integrity import money, rounded
from core.security import get_current_user
from core.spa_mice_authz import require_finance
from core.tenant_currency import get_tenant_currency
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(dependencies=[Depends(require_feature("mice", "advanced_reporting"))])


class ConsumeIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True, extra="forbid")
    order_id: str = Field(min_length=1)
    line_index: int = Field(ge=0)
    recipe_id: str = Field(min_length=1)
    batches: float = Field(gt=0, le=100000)
    reason: str = Field(min_length=10, max_length=1000)


@router.get("/events/{event_id}/consumption-options")
async def consumption_options(event_id: str, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_finance_reports"))):
    require_finance(current_user)
    db, tid = get_system_db(), current_user.tenant_id
    event = await db.mice_events.find_one({"tenant_id": tid, "id": event_id})
    if not event:
        raise HTTPException(404, "Etkinlik bulunamadı")
    orders = await db.mice_fnb_orders.find({"tenant_id": tid, "event_id": event_id, "status": "completed"}, {"_id": 0, "id": 1, "lines": 1}).to_list(None)
    recipes = await db.recipes.find({"tenant_id": tid}, {"_id": 0, "id": 1, "menu_item_name": 1, "serving_size": 1}).to_list(None)
    costs = event.get("stock_consumption_jobs") or []
    return {"orders": orders, "recipes": recipes, "consumptions": costs,
            "notice": "Yalnız tamamlanmış üretim için fiilen kullanılan reçete parti sayısını kaydedin. Bir parti, reçetedeki malzeme miktarlarının tamamıdır; kişi sayısı değildir. Otomatik stok düşer; yenmiş/bozulmuş ürün otomatik iade edilmez."}


@router.post("/events/{event_id}/stock-consumptions")
async def consume_recipe(event_id: str, body: ConsumeIn, current_user: User = Depends(get_current_user), _perm=Depends(require_op("view_finance_reports"))):
    require_finance(current_user)
    db, tid = get_system_db(), current_user.tenant_id
    default_currency, _ = await get_tenant_currency(tid)
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    source_id = f"mice-consumption:{tid}:{event_id}:{body.order_id}:{body.line_index}"
    async def consume(session):
        event = await db.mice_events.find_one({"tenant_id": tid, "id": event_id}, session=session)
        existing = next((job for job in (event or {}).get("stock_consumption_jobs") or [] if job["id"] == source_id), None)
        if existing:
            if existing["request_fingerprint"] != fingerprint:
                raise HTTPException(409, "Bu üretim satırının sarfı kaydedildi; aynı satır ikinci kez tüketilemez")
            return {"consumption": existing, "replayed": True}
        order = await db.mice_fnb_orders.find_one({"tenant_id": tid, "event_id": event_id, "id": body.order_id, "status": "completed"}, session=session)
        if not event or not order or body.line_index >= len(order.get("lines") or []):
            raise HTTPException(422, "Tamamlanmış üretim satırı bu etkinlikte bulunamadı")
        recipe = await db.recipes.find_one({"tenant_id": tid, "id": body.recipe_id}, session=session)
        if not recipe or not recipe.get("ingredients"):
            raise HTTPException(422, "Malzemeleri tanımlı reçete bulunamadı")
        if len(recipe["ingredients"]) > 200:
            raise HTTPException(422, "Bir banket sarfı en fazla 200 reçete malzemesi içerebilir")
        if len(event.get("generated_costs") or []) >= 100:
            raise HTTPException(409, "Etkinlik otomatik maliyet kalemi sınırına ulaştı")
        rows = []
        now = datetime.now(UTC).isoformat()
        for part in recipe["ingredients"]:
            qty = money(part.get("quantity")) * money(body.batches)
            if not qty:
                continue
            item = await db.ingredients.find_one({"tenant_id": tid, "id": part.get("ingredient_id")}, session=session)
            if not item or item.get("unit") != part.get("unit"):
                raise HTTPException(409, "Malzeme veya reçete birimi uyumsuz; stok tanımını düzeltin")
            currency = str(item.get("currency") or default_currency).upper()
            if currency != event.get("currency") or item.get("unit_cost") is None:
                raise HTTPException(409, "Malzeme maliyeti etkinlik dövizinde tanımlı olmalıdır; kur varsayılmaz")
            unit_cost = money(item["unit_cost"])
            changed = await db.ingredients.update_one({"tenant_id": tid, "id": item["id"], "current_stock": {"$gte": float(qty)}}, {"$inc": {"current_stock": -float(qty)}, "$set": {"updated_at": now}}, session=session)
            if changed.matched_count != 1:
                raise HTTPException(409, f"Malzeme stoğu yetersiz: {item.get('name')}")
            rows.append({"ingredient_id": item["id"], "name": item.get("name"), "quantity": float(qty), "unit": part["unit"], "unit_cost": float(unit_cost), "cost": rounded(qty * unit_cost), "currency": currency})
        if not rows:
            raise HTTPException(422, "Reçetede pozitif sarf miktarı yok")
        total = rounded(sum((money(r["cost"]) for r in rows), money(0)))
        record = {"id": source_id, "tenant_id": tid, "mice_event_id": event_id,
                  "order_id": body.order_id, "line_index": body.line_index, "recipe_id": body.recipe_id,
                  "recipe_snapshot": {"id": recipe["id"], "name": recipe.get("menu_item_name"), "ingredients": recipe["ingredients"], "serving_size": recipe.get("serving_size")},
                  "batches": body.batches, "ingredients": rows, "total_cost": total, "currency": event["currency"],
                  "reason": body.reason, "created_at": now, "created_by": current_user.username, "request_fingerprint": fingerprint}
        for index, row in enumerate(rows):
            await db.stock_consumptions.insert_one({"_id": f"{source_id}:{index}", "id": f"{source_id}:{index}", "tenant_id": tid, "source": "mice",
                                                    "mice_event_id": event_id, "mice_order_id": body.order_id, "order_id": f"mice:{body.order_id}",
                                                    "ingredient_id": row["ingredient_id"], "required_quantity": row["quantity"], "consumed_quantity": row["quantity"],
                                                    "unit": row["unit"], "unit_cost": row["unit_cost"], "total_cost": row["cost"], "currency": row["currency"],
                                                    "overdraft_quantity": 0, "reversed": False, "created_at": now, "created_by": current_user.username}, session=session)
        cost = {"id": source_id, "name": f"Reçete sarfı: {recipe.get('menu_item_name') or body.recipe_id}", "category": "food", "quantity": 1, "unit_cost": total, "source": "ingredient_stock", "recorded_at": now}
        values = {"updated_at": now}
        if isinstance(event.get("actuals"), dict):
            values["actuals.costs_complete"] = False
        else:
            values["actuals"] = {"costs": [], "costs_complete": False}
        await db.mice_events.update_one({"tenant_id": tid, "id": event_id}, {"$push": {"generated_costs": cost, "stock_consumption_jobs": record}, "$set": values}, session=session)
        return {"consumption": record, "replayed": False}
    return await with_resource_locks(client=db.client, db=db, tenant_id=tid, locks_collection="mice_locks", resources=[("event", event_id)], callback=consume)
