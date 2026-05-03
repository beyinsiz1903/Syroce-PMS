"""Opera #13 — Standing / Long-Stay rezervasyon.

Uzun konaklamalar için periyodik (haftalık/aylık) folio kapanışı + yeni cycle açılışı.
Kullanım: aylık kira benzeri konaklamalarda her cycle sonunda mevcut açık folyo kapatılır,
ödeme alınır, yeni folyo açılır.

Endpoint'ler:
  POST   /api/long-stay/configure         → booking için cycle yapılandır
  GET    /api/long-stay                   → aktif konfigürasyon listesi
  GET    /api/long-stay/due               → next_billing_date geçmiş olanlar
  POST   /api/long-stay/{config_id}/close-cycle → mevcut folyoyu kapat, yeni folyo aç
  DELETE /api/long-stay/{config_id}       → deactivate

Tutarlılık:
  - (tenant_id, booking_id) partial unique index → bir booking için tek aktif config
  - Mutating: require_op("post_charge")
  - Listing: require_op("view_finance_reports")
  - audit_log entegrasyonu
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import ReadPreference
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from core.database import client, db
from core.security import get_current_user
from core.utils import generate_folio_number
from models.enums import FolioStatus, FolioType
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from shared_kernel.audit_helper import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/long-stay", tags=["PMS / Long Stay"])

BillingCycle = Literal["weekly", "biweekly", "monthly"]
_INDEX_DONE = False
_INDEX_FAILED_AT: float = 0.0
_INDEX_FAIL_COOLDOWN_SEC = 30.0

CYCLE_DAYS: dict[str, int] = {"weekly": 7, "biweekly": 14}  # monthly → relativedelta(months=1)


def _add_cycle(start: datetime, cycle: str) -> datetime:
    """Calendar-aware: monthly = +1 takvim ayı (relativedelta), diğerleri sabit gün."""
    if cycle == "monthly":
        return start + relativedelta(months=1)
    return start + timedelta(days=CYCLE_DAYS.get(cycle, 7))


class ConfigureCreate(BaseModel):
    booking_id: str
    billing_cycle: BillingCycle = "monthly"
    start_date: str | None = Field(default=None, description="ISO tarih; boşsa bugün")
    notes: str | None = Field(default=None, max_length=500)


class LongStayConfig(BaseModel):
    id: str
    tenant_id: str
    booking_id: str
    billing_cycle: str
    next_billing_date: str
    cycles_closed: int
    active: bool
    notes: str | None = None
    created_by: str | None = None
    created_at: str
    deactivated_at: str | None = None


class CycleCloseResult(BaseModel):
    config_id: str
    closed_folio_id: str | None
    closed_folio_number: str | None
    new_folio_id: str
    new_folio_number: str
    next_billing_date: str
    cycles_closed: int


async def _ensure_indexes() -> None:
    """Partial unique index: (tenant_id, booking_id) bir booking → tek aktif config.
    Fail-closed: index oluşturulamazsa 503 + 30sn cooldown."""
    import time as _time
    global _INDEX_DONE, _INDEX_FAILED_AT
    if _INDEX_DONE:
        return
    now = _time.monotonic()
    if _INDEX_FAILED_AT and (now - _INDEX_FAILED_AT) < _INDEX_FAIL_COOLDOWN_SEC:
        raise HTTPException(503, "Long-stay index hazır değil (cooldown)")
    try:
        await db.long_stay_configs.create_index(
            [("tenant_id", 1), ("booking_id", 1)],
            name="long_stay_active_unique",
            unique=True,
            partialFilterExpression={"active": True},
        )
        await db.long_stay_configs.create_index(
            [("tenant_id", 1), ("active", 1), ("next_billing_date", 1)],
            name="long_stay_due",
        )
        _INDEX_DONE = True
        _INDEX_FAILED_AT = 0.0
    except Exception as exc:
        _INDEX_FAILED_AT = now
        logger.error("long_stay index oluşturulamadı: %s", exc)
        raise HTTPException(503, "Long-stay index hazır değil") from exc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@router.post("/configure", response_model=LongStayConfig, status_code=201)
async def configure_long_stay(
    body: ConfigureCreate,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    await _ensure_indexes()
    booking = await db.bookings.find_one(
        {"id": body.booking_id, "tenant_id": user.tenant_id}, {"_id": 0, "id": 1}
    )
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")

    start = datetime.now(UTC)
    if body.start_date:
        try:
            start = datetime.fromisoformat(body.start_date.replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
        except ValueError as exc:
            raise HTTPException(400, "Geçersiz start_date formatı (ISO bekleniyor)") from exc

    next_billing = _add_cycle(start, body.billing_cycle)
    doc: dict[str, Any] = {
        "id": str(_uuid.uuid4()),
        "tenant_id": user.tenant_id,
        "booking_id": body.booking_id,
        "billing_cycle": body.billing_cycle,
        "next_billing_date": next_billing.isoformat(),
        "cycles_closed": 0,
        "active": True,
        "notes": body.notes,
        "created_by": user.email,
        "created_at": _now_iso(),
        "deactivated_at": None,
    }
    try:
        await db.long_stay_configs.insert_one(doc)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Bu rezervasyon için aktif long-stay konfigürasyonu zaten var") from exc

    await audit_log(
        actor_id=user.id,
        tenant_id=user.tenant_id,
        property_id=user.tenant_id,
        entity_type="long_stay_config",
        entity_id=doc["id"],
        action="long_stay_configured",
        metadata={
            "booking_id": body.booking_id,
            "billing_cycle": body.billing_cycle,
            "next_billing_date": doc["next_billing_date"],
        },
    )
    doc.pop("_id", None)
    return doc


@router.get("", response_model=list[LongStayConfig])
async def list_configs(
    only_active: bool = True,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    await _ensure_indexes()
    q: dict[str, Any] = {"tenant_id": user.tenant_id}
    if only_active:
        q["active"] = True
    docs = await db.long_stay_configs.find(q, {"_id": 0}).sort("next_billing_date", 1).to_list(500)
    return docs


@router.get("/due", response_model=list[LongStayConfig])
async def list_due(
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """next_billing_date'i şimdiden eski olan aktif konfigürasyonlar."""
    await _ensure_indexes()
    now = _now_iso()
    docs = await db.long_stay_configs.find(
        {"tenant_id": user.tenant_id, "active": True, "next_billing_date": {"$lte": now}},
        {"_id": 0},
    ).sort("next_billing_date", 1).to_list(500)
    return docs


@router.post("/{config_id}/close-cycle", response_model=CycleCloseResult)
async def close_cycle(
    config_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("close_folio")),
):
    """Mevcut açık folyoyu kapat (canonical guard'larla), yeni folyo aç,
    next_billing_date'i ileri it. Compare-and-set ile race-safe."""
    await _ensure_indexes()
    cfg = await db.long_stay_configs.find_one(
        {"id": config_id, "tenant_id": user.tenant_id, "active": True}, {"_id": 0}
    )
    if not cfg:
        raise HTTPException(404, "Aktif long-stay konfigürasyonu bulunamadı")

    booking_id = cfg["booking_id"]
    new_folio_no = await generate_folio_number(user.tenant_id)
    new_folio_id = str(_uuid.uuid4())
    closed_folio_id: str | None = None
    closed_folio_number: str | None = None

    # Tek MongoDB transaction: cross-collection atomicity (CAS+close+insert birlikte commit/rollback)
    raw_db = getattr(db, "_db", db)  # TenantAwareDBProxy → raw db
    try:
        prev_due = datetime.fromisoformat(cfg["next_billing_date"].replace("Z", "+00:00"))
    except Exception:
        prev_due = datetime.now(UTC)
    new_due = _add_cycle(prev_due, cfg["billing_cycle"])

    async with await client.start_session() as session:
        async with session.start_transaction(
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
            read_preference=ReadPreference.PRIMARY,
        ):
            # 1) En eski açık folyo (transaction snapshot içinde — TOCTOU-safe)
            open_folio = await raw_db.folios.find_one(
                {
                    "tenant_id": user.tenant_id,
                    "booking_id": booking_id,
                    "status": FolioStatus.OPEN.value,
                },
                {"_id": 0},
                sort=[("created_at", 1)],
                session=session,
            )
            if open_folio:
                # Snapshot içi balance: server-side $group aggregation (tek snapshot read,
                # to_list limit yok). Helper'ın fail-open (0.0) davranışını bypass.
                fid = open_folio["id"]
                ch_pipe = [
                    {"$match": {"folio_id": fid, "tenant_id": user.tenant_id, "voided": False}},
                    {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$total", "$amount"]}}}},
                ]
                pay_pipe = [
                    {"$match": {"folio_id": fid, "tenant_id": user.tenant_id, "voided": False}},
                    {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
                ]
                ch_doc = await raw_db.folio_charges.aggregate(ch_pipe, session=session).to_list(1)
                pay_doc = await raw_db.payments.aggregate(pay_pipe, session=session).to_list(1)
                total_ch = float(ch_doc[0]["total"]) if ch_doc else 0.0
                total_pay = float(pay_doc[0]["total"]) if pay_doc else 0.0
                balance = round(total_ch - total_pay, 2)
                if balance > 0.01:
                    raise HTTPException(
                        400, f"Folyo kapatılamaz, ödenmemiş bakiye: {balance:.2f}",
                    )
                close_res = await raw_db.folios.update_one(
                    {
                        "id": open_folio["id"],
                        "tenant_id": user.tenant_id,
                        "status": FolioStatus.OPEN.value,
                    },
                    {"$set": {
                        "status": FolioStatus.CLOSED.value,
                        "balance": 0.0,
                        "closed_at": _now_iso(),
                    }},
                    session=session,
                )
                if close_res.modified_count == 0:
                    raise HTTPException(409, "Folyo başka bir işlem tarafından kapatıldı")
                closed_folio_id = open_folio["id"]
                closed_folio_number = open_folio.get("folio_number")

            # 2) CAS: cfg değişmediyse cycle'ı ilerlet (eş zamanlı close-cycle korunur)
            cas_res = await raw_db.long_stay_configs.update_one(
                {
                    "id": config_id,
                    "tenant_id": user.tenant_id,
                    "active": True,
                    "next_billing_date": cfg["next_billing_date"],
                    "cycles_closed": cfg["cycles_closed"],
                },
                {"$set": {"next_billing_date": new_due.isoformat()},
                 "$inc": {"cycles_closed": 1}},
                session=session,
            )
            if cas_res.modified_count == 0:
                # Transaction abort → folio close otomatik geri alınır
                raise HTTPException(409, "Eş zamanlı close-cycle algılandı; tekrar deneyin")

            # 3) Yeni cycle folyosu (CAS başarılı sonrası)
            new_folio: dict[str, Any] = {
                "id": new_folio_id,
                "tenant_id": user.tenant_id,
                "booking_id": booking_id,
                "folio_number": new_folio_no,
                "folio_type": FolioType.GUEST.value,
                "status": FolioStatus.OPEN.value,
                "guest_id": (open_folio.get("guest_id") if open_folio else None),
                "company_id": (open_folio.get("company_id") if open_folio else None),
                "balance": 0.0,
                "notes": f"Long-stay cycle #{cfg['cycles_closed'] + 1}",
                "created_at": _now_iso(),
                "closed_at": None,
                "window_number": None,
                "payor_type": None,
                "payor_id": None,
            }
            await raw_db.folios.insert_one(new_folio, session=session)

    await audit_log(
        actor_id=user.id,
        tenant_id=user.tenant_id,
        property_id=user.tenant_id,
        entity_type="long_stay_config",
        entity_id=config_id,
        action="long_stay_cycle_closed",
        metadata={
            "booking_id": booking_id,
            "closed_folio_id": closed_folio_id,
            "new_folio_id": new_folio["id"],
            "next_billing_date": new_due.isoformat(),
        },
    )

    return CycleCloseResult(
        config_id=config_id,
        closed_folio_id=closed_folio_id,
        closed_folio_number=closed_folio_number,
        new_folio_id=new_folio_id,
        new_folio_number=new_folio_no,
        next_billing_date=new_due.isoformat(),
        cycles_closed=cfg["cycles_closed"] + 1,
    )


@router.delete("/{config_id}", status_code=204)
async def deactivate(
    config_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    res = await db.long_stay_configs.update_one(
        {"id": config_id, "tenant_id": user.tenant_id, "active": True},
        {"$set": {"active": False, "deactivated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Aktif konfigürasyon bulunamadı")
    await audit_log(
        actor_id=user.id,
        tenant_id=user.tenant_id,
        property_id=user.tenant_id,
        entity_type="long_stay_config",
        entity_id=config_id,
        action="long_stay_deactivated",
    )
    return None
