"""
Erken Giris / Gec Cikis Otomatik Fiyat Kurallari.
Saat-bazli ucret kurallari tenant_settings.early_late_pricing'de tutulur.
"""
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/pms", tags=["pms"])

CHARGE_TYPES = ("flat", "percent_of_nightly", "percent_of_total", "free")


class PricingRule(BaseModel):
    id: str | None = None
    label: str
    from_hour: int = Field(..., ge=0, le=23)
    to_hour: int = Field(..., ge=0, le=23)
    charge_type: str = "flat"
    charge_value: float = 0.0


class PricingConfig(BaseModel):
    early_checkin: list[PricingRule] = Field(default_factory=list)
    late_checkout: list[PricingRule] = Field(default_factory=list)
    standard_checkin_hour: int = 14
    standard_checkout_hour: int = 12


def _default_config() -> dict:
    return {
        "early_checkin": [
            {"id": str(uuid4()), "label": "08:00 oncesi", "from_hour": 0, "to_hour": 8, "charge_type": "flat", "charge_value": 800},
            {"id": str(uuid4()), "label": "08:00–12:00", "from_hour": 8, "to_hour": 12, "charge_type": "percent_of_nightly", "charge_value": 50},
            {"id": str(uuid4()), "label": "12:00–14:00", "from_hour": 12, "to_hour": 14, "charge_type": "free", "charge_value": 0},
        ],
        "late_checkout": [
            {"id": str(uuid4()), "label": "12:00–14:00", "from_hour": 12, "to_hour": 14, "charge_type": "free", "charge_value": 0},
            {"id": str(uuid4()), "label": "14:00–18:00", "from_hour": 14, "to_hour": 18, "charge_type": "percent_of_nightly", "charge_value": 50},
            {"id": str(uuid4()), "label": "18:00 sonrasi", "from_hour": 18, "to_hour": 23, "charge_type": "percent_of_nightly", "charge_value": 100},
        ],
        "standard_checkin_hour": 14,
        "standard_checkout_hour": 12,
    }


@router.get("/settings/early-late-pricing")
async def get_pricing(current_user: User = Depends(get_current_user)):
    settings = await db.tenant_settings.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0}) or {}
    cfg = settings.get("early_late_pricing")
    if not cfg:
        cfg = _default_config()
    return cfg


@router.put("/settings/early-late-pricing")
async def update_pricing(payload: PricingConfig, current_user: User = Depends(get_current_user)):
    cfg = payload.model_dump()
    # ID'leri koru/uret
    for section in ("early_checkin", "late_checkout"):
        for r in cfg[section]:
            if not r.get("id"):
                r["id"] = str(uuid4())
            if r["charge_type"] not in CHARGE_TYPES:
                raise HTTPException(400, f"charge_type {CHARGE_TYPES} olmali")
            if r["from_hour"] >= r["to_hour"]:
                raise HTTPException(400, f"from_hour < to_hour olmali ({r['label']})")
    await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {"early_late_pricing": cfg, "updated_at": datetime.now(UTC).isoformat()}},
        upsert=True,
    )
    return cfg


class CalcRequest(BaseModel):
    booking_id: str
    direction: str  # "early_checkin" | "late_checkout"
    actual_hour: int = Field(..., ge=0, le=23)


@router.post("/early-late/calculate")
async def calculate(payload: CalcRequest, current_user: User = Depends(get_current_user)):
    if payload.direction not in ("early_checkin", "late_checkout"):
        raise HTTPException(400, "direction early_checkin|late_checkout olmali")

    booking = await db.bookings.find_one({"id": payload.booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadi")

    settings = await db.tenant_settings.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0}) or {}
    cfg = settings.get("early_late_pricing") or _default_config()
    rules = cfg.get(payload.direction, [])
    rule = next((r for r in rules if r["from_hour"] <= payload.actual_hour < r["to_hour"]), None)
    if not rule:
        return {
            "applicable": False,
            "amount": 0.0,
            "reason": "Standart saat araliginda — ek ucret yok",
            "rule": None,
            "actual_hour": payload.actual_hour,
        }

    nights = max(int(booking.get("nights") or 1), 1)
    total = float(booking.get("total_amount") or booking.get("total_price") or 0)
    nightly = total / nights if nights else total

    ct = rule["charge_type"]
    val = float(rule["charge_value"])
    if ct == "free":
        amount = 0.0
    elif ct == "flat":
        amount = val
    elif ct == "percent_of_nightly":
        amount = round(nightly * val / 100, 2)
    elif ct == "percent_of_total":
        amount = round(total * val / 100, 2)
    else:
        amount = 0.0

    return {
        "applicable": True,
        "amount": amount,
        "currency": booking.get("currency", "TRY"),
        "rule": rule,
        "actual_hour": payload.actual_hour,
        "nightly_rate": round(nightly, 2),
        "total": total,
        "nights": nights,
        "label": ("Erken Giris" if payload.direction == "early_checkin" else "Gec Cikis") + " — " + rule["label"],
    }
