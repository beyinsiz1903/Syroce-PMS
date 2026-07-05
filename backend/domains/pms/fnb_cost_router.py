"""
PMS / F&B Cost Controller — Reçete-bazlı maliyet + yield varyansı
=================================================================
Menü maddelerini (pos_menu_items) hammaddeye (inventory_items) bağlayan reçeteler;
reçeteden gerçek porsiyon maliyeti hesabı (menu engineering'in %35 fallback'i
yerine) ve teorik (reçeteye göre olması gereken) vs fiili (inventory_movements
"out") tüketim varyans raporu.

Tasarım:
  1. Tüm uçlar tenant-scoped; reçete mutasyonları yönetici seviyesi RBAC.
  2. Maliyet SUNUCUDA inventory_items.unit_cost'tan hesaplanır (client'a güvenilmez).
  3. Varyans = fiili - teorik (miktar ve tutar); pozitif = beklenenden fazla
     tüketim (fire/kayıp), negatif = beklenenden az.
  4. PII/secret loglanmaz.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger("domains.pms.fnb_cost")

router = APIRouter(prefix="/api/fnb-cost", tags=["PMS / F&B Cost"])

_RECIPE_ROLES = {"super_admin", "admin", "supervisor"}
_READ_ROLES = {
    "super_admin",
    "admin",
    "supervisor",
    "front_desk",
    "staff",
    "accountant",
}

# inventory_movements'ta tüketim/çıkış sayılan tipler (sunucu otoritedir).
_CONSUMPTION_TYPES = {"out", "consumption", "usage", "sale", "waste", "depletion"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _tenant_of(user: User) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant bulunamadı")
    return tid


def _role_of(user: User) -> str:
    role = getattr(user, "role", None)
    return getattr(role, "value", role) or ""


def _require_role(user: User, allowed: set[str]) -> None:
    if getattr(user, "is_super_admin", False):
        return
    if _role_of(user) not in allowed:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")


def _actor_id(user: User) -> str:
    return getattr(user, "id", None) or getattr(user, "user_id", None) or "system"


def _serialize(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    d = dict(doc)
    d.pop("_id", None)
    return d


# ─────────────────────────────────────────────────────────────────────
# Şemalar
# ─────────────────────────────────────────────────────────────────────
class Ingredient(BaseModel):
    inventory_item_id: str = Field(..., min_length=1, max_length=64)
    name: str | None = Field(None, max_length=200)
    quantity: float = Field(..., gt=0)
    unit: str | None = Field(None, max_length=20)


class RecipeIn(BaseModel):
    menu_item_name: str | None = Field(None, max_length=200)
    yield_portions: int = Field(1, ge=1, le=10000)
    ingredients: list[Ingredient] = Field(..., min_length=1, max_length=200)


async def _unit_cost_map(tenant_id: str, item_ids: list[str]) -> dict[str, dict]:
    """inventory_item_id -> {unit_cost, name, unit}. Tenant-scoped."""
    if not item_ids:
        return {}
    rows = await db.inventory_items.find({"tenant_id": tenant_id, "id": {"$in": item_ids}}, {"_id": 0}).to_list(1000)
    out: dict[str, dict] = {}
    for r in rows:
        out[r["id"]] = {
            "unit_cost": float(r.get("unit_cost", 0) or 0),
            "name": r.get("name") or r.get("product_name") or "",
            "unit": r.get("unit") or r.get("unit_of_measure") or "",
        }
    return out


def _compute_recipe_cost(recipe: dict, cost_map: dict[str, dict]) -> dict:
    """Reçete porsiyon maliyetini ve satır kırılımını döner."""
    breakdown = []
    raw_total = 0.0
    for ing in recipe.get("ingredients", []):
        iid = ing.get("inventory_item_id")
        info = cost_map.get(iid, {})
        unit_cost = float(info.get("unit_cost", 0) or 0)
        qty = float(ing.get("quantity", 0) or 0)
        line_cost = round(unit_cost * qty, 4)
        raw_total += line_cost
        breakdown.append(
            {
                "inventory_item_id": iid,
                "name": ing.get("name") or info.get("name") or iid,
                "quantity": qty,
                "unit": ing.get("unit") or info.get("unit") or "",
                "unit_cost": round(unit_cost, 4),
                "line_cost": line_cost,
                "cost_known": iid in cost_map,
            }
        )
    portions = max(int(recipe.get("yield_portions", 1) or 1), 1)
    per_portion = round(raw_total / portions, 4)
    return {
        "batch_cost": round(raw_total, 4),
        "yield_portions": portions,
        "cost_per_portion": per_portion,
        "ingredients": breakdown,
        "missing_costs": any(not b["cost_known"] for b in breakdown),
    }


# ─────────────────────────────────────────────────────────────────────
# Reçete CRUD
# ─────────────────────────────────────────────────────────────────────
@router.get("/recipes")
async def list_recipes(
    limit: int = Query(500, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _tenant_of(current_user)
    rows = await db.fnb_recipes.find({"tenant_id": tenant_id}, {"_id": 0}).sort("menu_item_name", 1).to_list(limit)
    return {"recipes": rows}


@router.get("/recipes/{menu_item_id}")
async def get_recipe(menu_item_id: str, current_user: User = Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    doc = await db.fnb_recipes.find_one({"tenant_id": tenant_id, "menu_item_id": menu_item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Reçete bulunamadı")
    return {"recipe": doc}


@router.put("/recipes/{menu_item_id}")
async def upsert_recipe(
    menu_item_id: str,
    payload: RecipeIn,
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _RECIPE_ROLES)
    tenant_id = _tenant_of(current_user)

    menu_item = await db.pos_menu_items.find_one({"tenant_id": tenant_id, "id": menu_item_id}, {"_id": 0})
    menu_name = payload.menu_item_name or (menu_item.get("name") if menu_item else None) or (menu_item.get("item_name") if menu_item else None) or menu_item_id

    now = _now_iso()
    ingredients = [
        {
            "inventory_item_id": ing.inventory_item_id.strip(),
            "name": (ing.name or "").strip() or None,
            "quantity": round(float(ing.quantity), 4),
            "unit": (ing.unit or "").strip() or None,
        }
        for ing in payload.ingredients
    ]
    doc_set = {
        "tenant_id": tenant_id,
        "menu_item_id": menu_item_id,
        "menu_item_name": menu_name,
        "yield_portions": payload.yield_portions,
        "ingredients": ingredients,
        "updated_at": now,
        "updated_by": _actor_id(current_user),
    }
    await db.fnb_recipes.update_one(
        {"tenant_id": tenant_id, "menu_item_id": menu_item_id},
        {"$set": doc_set, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
        upsert=True,
    )
    doc = await db.fnb_recipes.find_one({"tenant_id": tenant_id, "menu_item_id": menu_item_id}, {"_id": 0})
    return {"recipe": doc}


@router.delete("/recipes/{menu_item_id}")
async def delete_recipe(menu_item_id: str, current_user: User = Depends(get_current_user)):
    _require_role(current_user, _RECIPE_ROLES)
    tenant_id = _tenant_of(current_user)
    res = await db.fnb_recipes.delete_one({"tenant_id": tenant_id, "menu_item_id": menu_item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Reçete bulunamadı")
    return {"ok": True, "menu_item_id": menu_item_id}


@router.get("/recipes/{menu_item_id}/cost")
async def recipe_cost(menu_item_id: str, current_user: User = Depends(get_current_user)):
    tenant_id = _tenant_of(current_user)
    recipe = await db.fnb_recipes.find_one({"tenant_id": tenant_id, "menu_item_id": menu_item_id}, {"_id": 0})
    if not recipe:
        raise HTTPException(status_code=404, detail="Reçete bulunamadı")

    item_ids = [i["inventory_item_id"] for i in recipe.get("ingredients", [])]
    cost_map = await _unit_cost_map(tenant_id, item_ids)
    cost = _compute_recipe_cost(recipe, cost_map)

    menu_item = await db.pos_menu_items.find_one({"tenant_id": tenant_id, "id": menu_item_id}, {"_id": 0})
    menu_price = float((menu_item or {}).get("price", 0) or 0)
    food_cost_pct = round(cost["cost_per_portion"] / menu_price * 100, 2) if menu_price > 0 else None
    return {
        "menu_item_id": menu_item_id,
        "menu_item_name": recipe.get("menu_item_name"),
        "menu_price": menu_price,
        "food_cost_pct": food_cost_pct,
        **cost,
    }


# ─────────────────────────────────────────────────────────────────────
# Teorik vs fiili varyans
# ─────────────────────────────────────────────────────────────────────
@router.get("/variance")
async def yield_variance(
    start: str = Query(..., description="ISO başlangıç (gte)"),
    end: str = Query(..., description="ISO bitiş (lte)"),
    outlet_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    _require_role(current_user, _READ_ROLES)
    tenant_id = _tenant_of(current_user)

    recipes = await db.fnb_recipes.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(2000)
    by_id = {r["menu_item_id"]: r for r in recipes}
    by_name = {(r.get("menu_item_name") or "").strip().lower(): r for r in recipes if r.get("menu_item_name")}

    order_filter: dict = {
        "tenant_id": tenant_id,
        "created_at": {"$gte": start, "$lte": end},
    }
    if outlet_id:
        order_filter["outlet_id"] = outlet_id
    orders = await db.pos_orders.find(order_filter, {"_id": 0, "items": 1}).to_list(50000)

    # Teorik tüketim: satılan menü × reçete bileşeni.
    theoretical: dict[str, float] = {}
    matched_lines = 0
    unmatched_names: set[str] = set()
    for order in orders:
        for line in order.get("items", []) or []:
            qty = float(line.get("quantity", 1) or 1)
            mid = line.get("menu_item_id") or line.get("item_id")
            name = (line.get("item_name") or line.get("name") or "").strip().lower()
            recipe = by_id.get(mid) if mid else None
            if recipe is None and name:
                recipe = by_name.get(name)
            if recipe is None:
                if name:
                    unmatched_names.add(name)
                continue
            matched_lines += 1
            for ing in recipe.get("ingredients", []):
                iid = ing.get("inventory_item_id")
                theoretical[iid] = theoretical.get(iid, 0.0) + qty * float(ing.get("quantity", 0) or 0)

    # Fiili tüketim: inventory_movements çıkış hareketleri (product_id/item_id).
    mv_filter: dict = {
        "tenant_id": tenant_id,
        "movement_type": {"$in": list(_CONSUMPTION_TYPES)},
        "timestamp": {"$gte": start, "$lte": end},
    }
    movements = await db.inventory_movements.find(mv_filter, {"_id": 0}).to_list(100000)
    actual: dict[str, float] = {}
    for mv in movements:
        iid = mv.get("product_id") or mv.get("item_id")
        if not iid:
            continue
        actual[iid] = actual.get(iid, 0.0) + abs(float(mv.get("quantity", 0) or 0))

    all_ids = sorted(set(theoretical) | set(actual))
    cost_map = await _unit_cost_map(tenant_id, all_ids)

    rows = []
    tot_theo_cost = tot_act_cost = 0.0
    for iid in all_ids:
        info = cost_map.get(iid, {})
        unit_cost = float(info.get("unit_cost", 0) or 0)
        theo_qty = round(theoretical.get(iid, 0.0), 4)
        act_qty = round(actual.get(iid, 0.0), 4)
        var_qty = round(act_qty - theo_qty, 4)
        theo_cost = round(theo_qty * unit_cost, 2)
        act_cost = round(act_qty * unit_cost, 2)
        tot_theo_cost += theo_cost
        tot_act_cost += act_cost
        rows.append(
            {
                "inventory_item_id": iid,
                "name": info.get("name") or iid,
                "unit": info.get("unit") or "",
                "unit_cost": round(unit_cost, 4),
                "theoretical_qty": theo_qty,
                "actual_qty": act_qty,
                "variance_qty": var_qty,
                "theoretical_cost": theo_cost,
                "actual_cost": act_cost,
                "variance_cost": round(act_cost - theo_cost, 2),
                "cost_known": iid in cost_map,
            }
        )

    rows.sort(key=lambda r: abs(r["variance_cost"]), reverse=True)
    return {
        "period": {"start": start, "end": end},
        "outlet_id": outlet_id,
        "rows": rows,
        "totals": {
            "theoretical_cost": round(tot_theo_cost, 2),
            "actual_cost": round(tot_act_cost, 2),
            "variance_cost": round(tot_act_cost - tot_theo_cost, 2),
            "matched_order_lines": matched_lines,
            "unmatched_item_names": sorted(unmatched_names)[:50],
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Maliyet Yansıtma (Cost to GL)
# ─────────────────────────────────────────────────────────────────────
@router.post("/post-to-gl")
async def post_fnb_cost_to_gl(
    start: str = Query(..., description="ISO başlangıç (gte)"),
    end: str = Query(..., description="ISO bitiş (lte)"),
    current_user: User = Depends(get_current_user),
):
    """
    Belirli bir tarih aralığındaki toplam 'Satılan Malın Maliyetini' (Teorik veya Fiili)
    hesaplayarak Genel Muhasebeye (740 Borç / 150 Alacak) Yevmiye Fişi (Mahsup) atar.
    """
    _require_role(current_user, _READ_ROLES)
    # Re-use the variance logic to get total cost
    v = await yield_variance(start, end, None, current_user)
    total_cost = v["totals"]["actual_cost"] if v["totals"]["actual_cost"] > 0 else v["totals"]["theoretical_cost"]

    if total_cost <= 0:
        return {"status": "error", "message": "Yansıtılacak bir maliyet bulunamadı."}

    try:
        import uuid
        from datetime import datetime

        from routers.finance.general_ledger import mock_db as gl_db

        journal_entry = {
            "id": str(uuid.uuid4()),
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "type": "Mahsup",
            "description": f"F&B Maliyet Yansıtma ({start} - {end})",
            "total": total_cost,
            "timestamp": datetime.utcnow().isoformat(),
            "lines": [
                {
                    "account_code": "740",
                    "debit": total_cost,
                    "credit": 0.0,
                    "description": "Hizmet Üretim Maliyeti (F&B)"
                },
                {
                    "account_code": "150",
                    "debit": 0.0,
                    "credit": total_cost,
                    "description": "İlk Madde ve Malzeme Çıkışı"
                }
            ]
        }
        gl_db["journals"].append(journal_entry)
        return {"status": "success", "message": f"{total_cost} TL tutarında maliyet başarıyla yansıtıldı ve Mahsup fişi kesildi."}
    except Exception as e:
        return {"status": "error", "message": f"Muhasebe entegrasyon hatası: {str(e)}"}
