"""POS Happy Hour — zaman-bazlı fiyat kuralları (mevcut menü fiyatı değiştirilmez).

Mevcut sipariş akışı korunur: `apply` endpoint'i bir items[] listesi alır,
saate uygun aktif kuralları bulur, indirimli fiyatları döner. Frontend
sipariş oluşturmadan önce bu endpoint'i çağırıp `unit_price`'ı override
edebilir. Menü item dokümanlarına YAZILMAZ.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/pos/ext/happy-hour", tags=["pos-ext-happy-hour"])

_VALID_DOW = {0, 1, 2, 3, 4, 5, 6}  # Monday=0 .. Sunday=6


class HappyHourRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=120)
    outlet_id: str | None = None
    category: str | None = None  # menu item category filter; None = all
    item_ids: list[str] | None = None  # specific items; None = all in category
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    discount_type: str = Field(default="percent", pattern="^(percent|amount)$")
    discount_value: float = Field(gt=0)
    active: bool = True


class ApplyRequest(BaseModel):
    items: list[dict]
    outlet_id: str | None = None
    at: str | None = None  # ISO timestamp; default = now


def _parse_hhmm(s: str) -> time:
    try:
        h, m = s.split(":", 1)
        return time(hour=int(h), minute=int(m))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid HH:MM '{s}': {e}")


def _within_window(now: datetime, start: time, end: time) -> bool:
    t = now.time().replace(second=0, microsecond=0)
    if start <= end:
        return start <= t <= end
    # Overnight window (e.g. 22:00 → 02:00)
    return t >= start or t <= end


def _rule_matches(rule: dict, now: datetime, outlet_id: str | None, item: dict) -> bool:
    if not rule.get("active", True):
        return False
    # Outlet-specific rule must match an explicit outlet in the request; if the
    # request omits outlet_id we cannot safely apply an outlet-targeted rule.
    if rule.get("outlet_id"):
        if not outlet_id or rule["outlet_id"] != outlet_id:
            return False
    dow = now.weekday()
    if dow not in (rule.get("days_of_week") or []):
        return False
    try:
        st = _parse_hhmm(rule["start_time"])
        et = _parse_hhmm(rule["end_time"])
    except HTTPException:
        return False
    if not _within_window(now, st, et):
        return False
    if rule.get("category") and item.get("category") and rule["category"] != item["category"]:
        return False
    rule_items = rule.get("item_ids") or []
    if rule_items and item.get("item_id") not in rule_items:
        return False
    return True


def _apply_discount(unit_price: float, rule: dict) -> float:
    if rule["discount_type"] == "percent":
        pct = max(0.0, min(100.0, float(rule["discount_value"])))
        return round(unit_price * (1.0 - pct / 100.0), 2)
    amt = max(0.0, float(rule["discount_value"]))
    return max(0.0, round(unit_price - amt, 2))


@router.post("/rules")
async def create_rule(body: HappyHourRule, current_user: User = Depends(get_current_user)):
    _parse_hhmm(body.start_time)
    _parse_hhmm(body.end_time)
    if not set(body.days_of_week).issubset(_VALID_DOW):
        raise HTTPException(status_code=400, detail="days_of_week must be 0..6")
    doc = body.model_dump()
    doc.update(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "created_at": datetime.now(UTC),
            "created_by": current_user.id,
        }
    )
    await db.pos_happy_hour_rules.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "rule": doc}


@router.get("/rules")
async def list_rules(
    active_only: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if active_only:
        q["active"] = True
    rows = await db.pos_happy_hour_rules.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"rules": rows, "count": len(rows)}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, current_user: User = Depends(get_current_user)):
    res = await db.pos_happy_hour_rules.delete_one({"id": rule_id, "tenant_id": current_user.tenant_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"success": True, "deleted": rule_id}


@router.post("/apply")
async def apply_rules(body: ApplyRequest, current_user: User = Depends(get_current_user)):
    now = datetime.now(UTC)
    if body.at:
        try:
            now = datetime.fromisoformat(body.at.replace("Z", "+00:00"))
            if now.tzinfo is None:
                now = now.replace(tzinfo=UTC)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid 'at' timestamp")

    active = await db.pos_happy_hour_rules.find({"tenant_id": current_user.tenant_id, "active": True}, {"_id": 0}).to_list(200)

    out = []
    total_orig = 0.0
    total_disc = 0.0
    for item in body.items:
        unit_price = float(item.get("price") or item.get("unit_price") or 0)
        qty = int(item.get("quantity") or 1)
        original = round(unit_price * qty, 2)
        total_orig += original
        applied_rule_id = None
        new_unit = unit_price
        for rule in active:
            if _rule_matches(rule, now, body.outlet_id, item):
                new_unit = _apply_discount(unit_price, rule)
                applied_rule_id = rule["id"]
                break  # first-match wins (deterministic)
        final = round(new_unit * qty, 2)
        total_disc += final
        out.append(
            {
                **{k: v for k, v in item.items() if k != "price"},
                "original_unit_price": unit_price,
                "unit_price": new_unit,
                "quantity": qty,
                "line_total": final,
                "applied_rule_id": applied_rule_id,
            }
        )
    return {
        "evaluated_at": now.isoformat(),
        "items": out,
        "total_original": round(total_orig, 2),
        "total_discounted": round(total_disc, 2),
        "savings": round(total_orig - total_disc, 2),
    }
