"""
Konaklama Vergisi (Turkey Accommodation Tax) automation module.

Türkiye Konaklama Vergisi Kanunu (7194 sayılı):
- Oran: %2 (varsayılan)
- Matrah: Konaklama bedeli (KDV hariç)
- Beyanname: Takip eden ayın 26'sına kadar
- Muafiyet: Diplomatik, öğrenci yurdu, sağlık tesisi vb.

Bu modül `db.city_tax_rules` (mevcut config koleksiyonu) ve
`ChargeCategory.CITY_TAX` (mevcut enum) üzerine kuruludur.
Posting izi `db.accommodation_tax_postings` koleksiyonunda tutulur.
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.enums import ChargeCategory
from models.schemas import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/finance/konaklama-vergisi", tags=["konaklama-vergisi"])

DEFAULT_RATE_PERCENT = 2.0


class KonaklamaVergisiConfig(BaseModel):
    rate_percent: float = Field(default=DEFAULT_RATE_PERCENT, ge=0, le=100)
    active: bool = True
    auto_post: bool = False
    effective_from: str | None = None  # ISO date
    notes: str | None = None
    exempt_segments: list[str] = Field(default_factory=list)


class CalculateRequest(BaseModel):
    amount: float = Field(gt=0)
    nights: int = Field(default=1, ge=1)
    exempt: bool = False


def _config_query(tenant_id: str) -> dict[str, Any]:
    return {"tenant_id": tenant_id, "active": True}


async def _load_config(tenant_id: str) -> dict[str, Any]:
    doc = await db.city_tax_rules.find_one(_config_query(tenant_id))
    if not doc:
        return {
            "tenant_id": tenant_id,
            "rate_percent": DEFAULT_RATE_PERCENT,
            "active": True,
            "auto_post": False,
            "effective_from": None,
            "notes": None,
            "exempt_segments": [],
        }
    doc.pop("_id", None)
    doc.setdefault("rate_percent", doc.get("tax_percentage", DEFAULT_RATE_PERCENT))
    doc.setdefault("auto_post", False)
    doc.setdefault("exempt_segments", [])
    return doc


@router.get("/config")
async def get_config(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return await _load_config(current_user.tenant_id)


@router.put("/config")
async def update_config(
    cfg: KonaklamaVergisiConfig,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    payload = {
        "tenant_id": current_user.tenant_id,
        "rate_percent": cfg.rate_percent,
        "tax_percentage": cfg.rate_percent,  # legacy field for folio.py
        "active": cfg.active,
        "auto_post": cfg.auto_post,
        "effective_from": cfg.effective_from,
        "notes": cfg.notes,
        "exempt_segments": cfg.exempt_segments,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": current_user.id,
    }
    await db.city_tax_rules.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": payload, "$setOnInsert": {"created_at": datetime.now(UTC).isoformat()}},
        upsert=True,
    )
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="UPDATE_KONAKLAMA_VERGISI_CONFIG",
        entity_type="city_tax_rules",
        entity_id=current_user.tenant_id,
        changes=payload,
    )
    return await _load_config(current_user.tenant_id)


@router.post("/calculate")
async def calculate(
    req: CalculateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cfg = await _load_config(current_user.tenant_id)
    rate = float(cfg.get("rate_percent", DEFAULT_RATE_PERCENT))
    base = round(req.amount * req.nights, 2)
    tax = 0.0 if req.exempt else round(base * (rate / 100.0), 2)
    return {
        "rate_percent": rate,
        "base_amount": base,
        "tax_amount": tax,
        "total_with_tax": round(base + tax, 2),
        "exempt": req.exempt,
        "nights": req.nights,
    }


def _period_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="month must be 1-12")
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


async def _aggregate_period(tenant_id: str, year: int, month: int) -> dict[str, Any]:
    start, end = _period_bounds(year, month)
    cfg = await _load_config(tenant_id)
    rate = float(cfg.get("rate_percent", DEFAULT_RATE_PERCENT))

    pipeline: list[dict[str, Any]] = [
        {
            "$match": {
                "tenant_id": tenant_id,
                "voided": {"$ne": True},
                "charge_category": ChargeCategory.ROOM.value,
                "date": {
                    "$gte": start.isoformat(),
                    "$lt": end.isoformat(),
                },
            }
        },
        {
            "$group": {
                "_id": "$folio_id",
                "base_amount": {"$sum": "$amount"},
                "nights": {"$sum": "$quantity"},
                "booking_id": {"$first": "$booking_id"},
            }
        },
    ]
    rows = await db.folio_charges.aggregate(pipeline).to_list(length=None)
    total_base = round(sum(r.get("base_amount", 0.0) for r in rows), 2)
    total_nights = round(sum(r.get("nights", 0.0) for r in rows), 2)
    total_tax = round(total_base * (rate / 100.0), 2)
    return {
        "year": year,
        "month": month,
        "rate_percent": rate,
        "folio_count": len(rows),
        "total_nights": total_nights,
        "total_base": total_base,
        "total_tax": total_tax,
        "rows": rows,
    }


@router.get("/report")
async def report(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await _aggregate_period(current_user.tenant_id, year, month)


@router.get("/declaration")
async def declaration(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """GİB beyanname özeti — aylık konaklama vergisi beyannamesi."""
    agg = await _aggregate_period(current_user.tenant_id, year, month)
    tenant = await db.tenants.find_one(
        {"id": current_user.tenant_id}, {"_id": 0, "hotel_name": 1, "tax_no": 1, "hotel_id": 1}
    ) or {}
    due_day = 26
    due_month = month + 1 if month < 12 else 1
    due_year = year if month < 12 else year + 1
    return {
        "period": f"{year}-{month:02d}",
        "due_date": f"{due_year}-{due_month:02d}-{due_day:02d}",
        "tenant": tenant,
        "rate_percent": agg["rate_percent"],
        "total_base": agg["total_base"],
        "total_tax": agg["total_tax"],
        "folio_count": agg["folio_count"],
        "total_nights": agg["total_nights"],
        "currency": "TRY",
        "law_reference": "7194 sayılı Kanun — Konaklama Vergisi",
    }


@router.post("/post-folio/{folio_id}")
async def post_to_folio(
    folio_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Bir folio için konaklama vergisi satırını idempotent olarak ekle."""
    folio = await db.folios.find_one(
        {"id": folio_id, "tenant_id": current_user.tenant_id}
    )
    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    existing = await db.accommodation_tax_postings.find_one(
        {"tenant_id": current_user.tenant_id, "folio_id": folio_id}
    )
    if existing:
        return {"posted": False, "already_posted": True, "posting_id": existing["id"]}

    cfg = await _load_config(current_user.tenant_id)
    if not cfg.get("active", True):
        raise HTTPException(status_code=400, detail="Konaklama Vergisi devre dışı")
    rate = float(cfg.get("rate_percent", DEFAULT_RATE_PERCENT))

    room_charges = await db.folio_charges.find(
        {
            "tenant_id": current_user.tenant_id,
            "folio_id": folio_id,
            "charge_category": ChargeCategory.ROOM.value,
            "voided": {"$ne": True},
        }
    ).to_list(length=None)
    base = round(sum(c.get("amount", 0.0) for c in room_charges), 2)
    if base <= 0:
        raise HTTPException(status_code=400, detail="Vergilenecek oda satırı yok")
    tax_amount = round(base * (rate / 100.0), 2)

    charge_id = str(uuid.uuid4())
    now_iso = datetime.now(UTC).isoformat()
    charge_doc = {
        "id": charge_id,
        "tenant_id": current_user.tenant_id,
        "folio_id": folio_id,
        "booking_id": folio.get("booking_id"),
        "charge_category": ChargeCategory.CITY_TAX.value,
        "description": f"Konaklama Vergisi (%{rate})",
        "unit_price": tax_amount,
        "quantity": 1.0,
        "amount": tax_amount,
        "tax_amount": 0.0,
        "total": tax_amount,
        "date": now_iso,
        "posted_by": current_user.id,
        "voided": False,
        "konaklama_vergisi": True,
    }
    await db.folio_charges.insert_one(charge_doc)

    posting_id = str(uuid.uuid4())
    await db.accommodation_tax_postings.insert_one(
        {
            "id": posting_id,
            "tenant_id": current_user.tenant_id,
            "folio_id": folio_id,
            "charge_id": charge_id,
            "base_amount": base,
            "rate_percent": rate,
            "tax_amount": tax_amount,
            "posted_at": now_iso,
            "posted_by": current_user.id,
        }
    )

    new_balance = (folio.get("balance") or 0.0) + tax_amount
    await db.folios.update_one(
        {"id": folio_id}, {"$set": {"balance": round(new_balance, 2)}}
    )

    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="POST_KONAKLAMA_VERGISI",
        entity_type="folio_charge",
        entity_id=charge_id,
        changes={"folio_id": folio_id, "base": base, "tax": tax_amount, "rate": rate},
    )
    return {
        "posted": True,
        "posting_id": posting_id,
        "charge_id": charge_id,
        "base_amount": base,
        "tax_amount": tax_amount,
        "rate_percent": rate,
    }


@router.get("/postings")
async def list_postings(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cursor = db.accommodation_tax_postings.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("posted_at", -1).limit(max(1, min(limit, 500)))
    items = await cursor.to_list(length=None)
    return {"count": len(items), "items": items}
