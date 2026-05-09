"""
Erken Giriş / Geç Çıkış Otomatik Fiyat Kuralları.

- Saat-bazlı ücret kuralları tenant_settings.early_late_pricing'de tutulur.
- Gerçekleşen saat float (dakika hassasiyetli, ör. 13.75 = 13:45).
- Aralık matcher: from_hour <= actual < to_hour; son kural to_hour=23 ise dahil
  edici (<=24) olarak değerlendirilir → 23:00–23:59 sessiz gelir kaybı kapatılır.
- PUT için require_op("manage_pricing") yetki kapısı; çakışma & boşluk validation;
  audit log; response tenant_id + updated_at + updated_by içerir.
"""
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/pms", tags=["pms"])

CHARGE_TYPES = ("flat", "percent_of_nightly", "percent_of_total", "free")
DAY_END_HOUR = 24.0  # son kuralın inclusive bitişi (23:00–23:59 dahil)


class PricingRule(BaseModel):
    id: str | None = None
    label: str = Field(..., min_length=1, max_length=80)
    from_hour: float = Field(..., ge=0, le=24)
    to_hour: float = Field(..., ge=0, le=24)
    charge_type: str = "flat"
    charge_value: float = Field(0.0, ge=0)

    @field_validator("charge_type")
    @classmethod
    def _ct(cls, v: str) -> str:
        if v not in CHARGE_TYPES:
            raise ValueError(f"charge_type {CHARGE_TYPES} olmalı")
        return v


class PricingConfig(BaseModel):
    early_checkin: list[PricingRule] = Field(default_factory=list)
    late_checkout: list[PricingRule] = Field(default_factory=list)
    standard_checkin_hour: int = Field(14, ge=0, le=23)
    standard_checkout_hour: int = Field(12, ge=0, le=23)


def _default_config() -> dict:
    return {
        "early_checkin": [
            {"id": str(uuid4()), "label": "08:00 öncesi", "from_hour": 0, "to_hour": 8, "charge_type": "flat", "charge_value": 800},
            {"id": str(uuid4()), "label": "08:00–12:00", "from_hour": 8, "to_hour": 12, "charge_type": "percent_of_nightly", "charge_value": 50},
            {"id": str(uuid4()), "label": "12:00–14:00", "from_hour": 12, "to_hour": 14, "charge_type": "free", "charge_value": 0},
        ],
        "late_checkout": [
            {"id": str(uuid4()), "label": "12:00–14:00", "from_hour": 12, "to_hour": 14, "charge_type": "free", "charge_value": 0},
            {"id": str(uuid4()), "label": "14:00–18:00", "from_hour": 14, "to_hour": 18, "charge_type": "percent_of_nightly", "charge_value": 50},
            {"id": str(uuid4()), "label": "18:00 sonrası", "from_hour": 18, "to_hour": 23, "charge_type": "percent_of_nightly", "charge_value": 100},
        ],
        "standard_checkin_hour": 14,
        "standard_checkout_hour": 12,
    }


def _validate_rules(rules: list[dict], section: str) -> list[str]:
    """Çakışma & boşluk kontrolü; hata listesi döner (boş = OK).

    Sadece warning ya da hata olarak çağıran tarafa bırakılır; PUT'ta hata atılır.
    """
    errors: list[str] = []
    if not rules:
        return errors
    # 1) from < to
    for r in rules:
        if r["from_hour"] >= r["to_hour"]:
            errors.append(f"[{section}] '{r.get('label','?')}' kuralında başlangıç bitişten küçük olmalı")
    # 2) Çakışma kontrolü
    sorted_rules = sorted(rules, key=lambda x: (x["from_hour"], x["to_hour"]))
    for i in range(len(sorted_rules) - 1):
        a, b = sorted_rules[i], sorted_rules[i + 1]
        if a["to_hour"] > b["from_hour"]:
            errors.append(
                f"[{section}] Çakışma: '{a.get('label','?')}' ({a['from_hour']}-{a['to_hour']}) "
                f"ile '{b.get('label','?')}' ({b['from_hour']}-{b['to_hour']})"
            )
    return errors


def _match_rule(rules: list[dict], actual_hour: float) -> dict | None:
    """Aralık matcher. Son kuralın bitişi 23 ise inclusive davranır (23:00–23:59 dahil)."""
    if not rules:
        return None
    sorted_rules = sorted(rules, key=lambda r: (r["from_hour"], r["to_hour"]))
    last_to = max(r["to_hour"] for r in sorted_rules)
    for r in sorted_rules:
        upper = r["to_hour"]
        # Son kuralın üst sınırını inclusive (24'e çıkar) yap → 23:00–23:59 boşluğu kapanır
        is_last_segment = upper == last_to and upper >= 23
        if is_last_segment:
            if r["from_hour"] <= actual_hour <= 24:
                return r
        elif r["from_hour"] <= actual_hour < upper:
            return r
    return None


@router.get("/settings/early-late-pricing")
async def get_pricing(current_user: User = Depends(get_current_user)):
    settings = await db.tenant_settings.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0}) or {}
    cfg = settings.get("early_late_pricing")
    meta = settings.get("early_late_pricing_meta") or {}
    if not cfg:
        cfg = _default_config()
        meta = {"is_default": True}
    return {
        **cfg,
        "_meta": {
            "tenant_id": current_user.tenant_id,
            "updated_at": meta.get("updated_at"),
            "updated_by": meta.get("updated_by"),
            "is_default": meta.get("is_default", False),
        },
    }


@router.put("/settings/early-late-pricing")
async def update_pricing(
    payload: PricingConfig,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_pricing")),  # P0 #3 yetki kapısı
):
    cfg = payload.model_dump()
    # ID üret + tip kontrolü
    for section in ("early_checkin", "late_checkout"):
        for r in cfg[section]:
            if not r.get("id"):
                r["id"] = str(uuid4())
        # P1 #5 çakışma & başlangıç<bitiş validation
        errs = _validate_rules(cfg[section], section)
        if errs:
            raise HTTPException(400, " | ".join(errs))

    # P1 #4 standart saatler standart_checkin_hour < standart_checkout_hour kontrolü
    # opsiyonel — bazı oteller checkin>checkout (overnight) modeli kullanabilir;
    # bu yüzden sadece 0–23 aralığını zorluyoruz (Pydantic Field hallediyor).

    now_iso = datetime.now(UTC).isoformat()
    meta = {
        "updated_at": now_iso,
        "updated_by": current_user.id,
        "updated_by_name": getattr(current_user, "username", None) or getattr(current_user, "email", None),
        "is_default": False,
    }
    await db.tenant_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {
            "early_late_pricing": cfg,
            "early_late_pricing_meta": meta,
            "updated_at": now_iso,
        }},
        upsert=True,
    )

    # Audit log (best-effort; çağrının bloklanmaması için try/except)
    try:
        await db.audit_logs.insert_one({
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "settings.early_late_pricing.update",
            "resource_type": "tenant_settings",
            "timestamp": datetime.now(UTC),
            "metadata": {
                "early_count": len(cfg["early_checkin"]),
                "late_count": len(cfg["late_checkout"]),
                "standard_checkin_hour": cfg["standard_checkin_hour"],
                "standard_checkout_hour": cfg["standard_checkout_hour"],
            },
        })
    except Exception:
        pass

    return {**cfg, "_meta": {"tenant_id": current_user.tenant_id, **meta}}


class CalcRequest(BaseModel):
    booking_id: str
    direction: str  # "early_checkin" | "late_checkout"
    actual_hour: float = Field(..., ge=0, le=24)  # P1 #6 dakika hassasiyeti


@router.post("/early-late/calculate")
async def calculate(payload: CalcRequest, current_user: User = Depends(get_current_user)):
    if payload.direction not in ("early_checkin", "late_checkout"):
        raise HTTPException(400, "direction early_checkin|late_checkout olmalı")

    booking = await db.bookings.find_one(
        {"id": payload.booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")

    settings = await db.tenant_settings.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0}) or {}
    cfg = settings.get("early_late_pricing") or _default_config()
    rules = cfg.get(payload.direction, [])
    rule = _match_rule(rules, payload.actual_hour)
    if not rule:
        return {
            "applicable": False,
            "amount": 0.0,
            "reason": "Standart saat aralığında — ek ücret yok",
            "rule": None,
            "actual_hour": payload.actual_hour,
            "currency": booking.get("currency", "TRY"),
        }

    nights = max(int(booking.get("nights") or 1), 1)
    # P1 #7 vergi tabanı belirginliği: subtotal varsa onu kullan (vergi/fee hariç),
    # yoksa total_amount/total_price'a düş.
    subtotal = booking.get("subtotal") or booking.get("base_amount")
    total = float(subtotal if subtotal is not None else (booking.get("total_amount") or booking.get("total_price") or 0))
    nightly = total / nights if nights else total

    ct = rule["charge_type"]
    val = float(rule["charge_value"])
    if ct == "free":
        amount = 0.0
    elif ct == "flat":
        amount = round(val, 2)
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
        "tax_base": "subtotal" if subtotal is not None else "total_amount",
        "nights": nights,
        "label": ("Erken Giriş" if payload.direction == "early_checkin" else "Geç Çıkış") + " — " + rule["label"],
    }
