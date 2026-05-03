"""Opera #11 — Multi-window Folio.

Bir booking'in folio'sunu 1-8 arası window'a böler. Her window:
  - Ayrı window_number (1-8)
  - Ayrı payor (guest|company|agency|master)
  - Ayrı charges/payments/balance
  - Ayrı checkout

Mevcut Folio modelini genişletir (booking başına birden çok Folio zaten destekleniyordu),
sadece kanonik "window" semantiği + auto-numbering + özet ekler.

Tutarlılık:
  - (tenant_id, booking_id, window_number) partial unique index → race-safe
  - DuplicateKeyError yakalanır, 3x retry
  - Mutating endpoint'lerde require_op("post_charge") yetkisi
  - audit_log entegrasyonu
  - Legacy folios (window_number=None) slot accounting'e dahil edilir
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.security import get_current_user
from core.utils import calculate_folio_balance, generate_folio_number
from models.enums import FolioStatus, FolioType
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from shared_kernel.audit_helper import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/folio-windows", tags=["PMS / Folio Windows"])

PayorType = Literal["guest", "company", "agency", "master"]
MAX_WINDOWS = 8
_INDEX_DONE = False
_INDEX_FAILED_AT: float = 0.0
_INDEX_FAIL_COOLDOWN_SEC = 30.0


class WindowCreate(BaseModel):
    booking_id: str
    payor_type: PayorType
    payor_id: str | None = None  # guest_id / company_id / agency_id; master için None
    notes: str | None = Field(default=None, max_length=500)


class WindowSummary(BaseModel):
    folio_id: str
    folio_number: str
    window_number: int
    payor_type: str | None
    payor_id: str | None
    folio_type: str
    status: str
    balance: float
    charges_count: int
    payments_count: int
    created_at: str | None
    closed_at: str | None


class PayorPatch(BaseModel):
    payor_type: PayorType
    payor_id: str | None = None


def _payor_to_folio_type(payor_type: str) -> FolioType:
    """Payor → FolioType. master için GUEST (group master folyo semantiği),
    payor_type='master' field ayrıca saklanır."""
    if payor_type == "guest":
        return FolioType.GUEST
    if payor_type == "company":
        return FolioType.COMPANY
    if payor_type == "agency":
        return FolioType.AGENCY
    # master → fiziksel folyo tipi GUEST, ama payor_type='master' field'da kalır
    return FolioType.GUEST


async def _ensure_indexes() -> None:
    """Partial unique index: (tenant_id, booking_id, window_number) — race-safe.
    Fail-closed: index oluşturulamazsa mutating endpoint 503 verir.
    Cooldown: hata olursa 30sn boyunca DB'ye yeniden deneme yapılmaz (sadece 503)."""
    import time as _time
    global _INDEX_DONE, _INDEX_FAILED_AT
    if _INDEX_DONE:
        return
    now = _time.monotonic()
    if _INDEX_FAILED_AT and (now - _INDEX_FAILED_AT) < _INDEX_FAIL_COOLDOWN_SEC:
        raise HTTPException(503, "Folio window index hazır değil (cooldown)")
    try:
        await db.folios.create_index(
            [("tenant_id", 1), ("booking_id", 1), ("window_number", 1)],
            name="folio_window_unique",
            unique=True,
            partialFilterExpression={"window_number": {"$gte": 1}},
        )
        _INDEX_DONE = True
        _INDEX_FAILED_AT = 0.0
    except Exception as exc:
        _INDEX_FAILED_AT = now
        logger.error("folio_window_unique index oluşturulamadı: %s", exc)
        raise HTTPException(503, "Folio window index hazır değil") from exc


def _ts_key(value: Any) -> str:
    """created_at için normalize sıralama anahtarı (mixed str/datetime güvenli)."""
    if value is None:
        return ""
    return str(value)


def _resolve_window_number(folio: dict[str, Any], all_folios: list[dict[str, Any]]) -> int:
    """Legacy folios için implicit slot atama. Verilen folio'nun gerçek window#'u
    yoksa, booking'in tüm folios'u arasında eski→yeni sırasıyla ilk boş slot."""
    wn = folio.get("window_number")
    if isinstance(wn, int) and wn >= 1:
        return wn
    used = {f.get("window_number") for f in all_folios
            if isinstance(f.get("window_number"), int) and f.get("window_number") >= 1}
    legacy_sorted = sorted(
        [f for f in all_folios if not (isinstance(f.get("window_number"), int) and f.get("window_number") >= 1)],
        key=lambda x: _ts_key(x.get("created_at")),
    )
    for f in legacy_sorted:
        for n in range(1, MAX_WINDOWS + 1):
            if n not in used:
                used.add(n)
                if f.get("id") == folio.get("id"):
                    return n
                break
    return 0


async def _used_window_numbers(tenant_id: str, booking_id: str) -> set[int]:
    """Booking'in kullanılan tüm window numaralarını topla. Legacy folios
    (window_number=None) yerleşik sıraya göre 1,2,3... implicit slot kabul edilir."""
    docs = await db.folios.find(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0, "window_number": 1, "created_at": 1},
    ).to_list(500)
    used: set[int] = set()
    legacy = []
    for d in docs:
        wn = d.get("window_number")
        if isinstance(wn, int) and wn >= 1:
            used.add(wn)
        else:
            legacy.append(_ts_key(d.get("created_at")))
    # Legacy folios: oldest first, ilk boş slot'lara yerleştir
    legacy.sort()
    for _ in legacy:
        for n in range(1, MAX_WINDOWS + 1):
            if n not in used:
                used.add(n)
                break
    return used


async def _next_window_number(tenant_id: str, booking_id: str) -> int:
    used = await _used_window_numbers(tenant_id, booking_id)
    for n in range(1, MAX_WINDOWS + 1):
        if n not in used:
            return n
    raise HTTPException(409, f"Window limiti doldu (en fazla {MAX_WINDOWS} window)")


@router.post("", response_model=WindowSummary, status_code=201)
async def open_window(
    body: WindowCreate,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    """Yeni window aç (auto-numbering 1-8). Race-safe: unique index + 3x retry."""
    await _ensure_indexes()
    booking = await db.bookings.find_one(
        {"id": body.booking_id, "tenant_id": user.tenant_id}, {"_id": 0, "id": 1}
    )
    if not booking:
        raise HTTPException(404, "Rezervasyon bulunamadı")

    # Payor doğrulama
    if body.payor_type == "guest" and body.payor_id:
        ok = await db.guests.find_one(
            {"id": body.payor_id, "tenant_id": user.tenant_id}, {"_id": 0, "id": 1}
        )
        if not ok:
            raise HTTPException(404, "Misafir bulunamadı")
    elif body.payor_type == "company" and body.payor_id:
        ok = await db.companies.find_one(
            {"id": body.payor_id, "tenant_id": user.tenant_id}, {"_id": 0, "id": 1}
        )
        if not ok:
            raise HTTPException(404, "Şirket bulunamadı")

    folio_type = _payor_to_folio_type(body.payor_type)
    last_err: Exception | None = None
    for _attempt in range(3):
        window_no = await _next_window_number(user.tenant_id, body.booking_id)
        folio_no = await generate_folio_number(user.tenant_id)
        doc: dict[str, Any] = {
            "id": str(_uuid.uuid4()),
            "tenant_id": user.tenant_id,
            "booking_id": body.booking_id,
            "folio_number": folio_no,
            "folio_type": folio_type.value,
            "status": FolioStatus.OPEN.value,
            "guest_id": body.payor_id if body.payor_type == "guest" else None,
            "company_id": body.payor_id if body.payor_type == "company" else None,
            "balance": 0.0,
            "notes": body.notes,
            "created_at": datetime.now(UTC).isoformat(),
            "closed_at": None,
            "window_number": window_no,
            "payor_type": body.payor_type,
            "payor_id": body.payor_id,
        }
        try:
            await db.folios.insert_one(doc)
            break
        except DuplicateKeyError as exc:
            last_err = exc
            continue
    else:
        raise HTTPException(409, f"Window numarası ataması başarısız (race): {last_err}")

    await audit_log(
        actor_id=user.id,
        tenant_id=user.tenant_id,
        property_id=user.tenant_id,
        entity_type="folio",
        entity_id=doc["id"],
        action="folio_window_opened",
        metadata={
            "booking_id": body.booking_id,
            "window_number": window_no,
            "payor_type": body.payor_type,
            "payor_id": body.payor_id,
        },
    )

    doc.pop("_id", None)
    return WindowSummary(
        folio_id=doc["id"],
        folio_number=doc["folio_number"],
        window_number=window_no,
        payor_type=body.payor_type,
        payor_id=body.payor_id,
        folio_type=folio_type.value,
        status=FolioStatus.OPEN.value,
        balance=0.0,
        charges_count=0,
        payments_count=0,
        created_at=doc["created_at"],
        closed_at=None,
    )


@router.get("/booking/{booking_id}", response_model=list[WindowSummary])
async def list_windows(
    booking_id: str,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Booking'in tüm window'larını döner (window_number'a göre sıralı).
    Legacy folios (window_number=None) eski→yeni implicit slot atanır."""
    folios = await db.folios.find(
        {"booking_id": booking_id, "tenant_id": user.tenant_id}, {"_id": 0}
    ).to_list(500)

    # Tek noktadan implicit slot resolve
    for f in folios:
        f["_resolved_window"] = _resolve_window_number(f, folios)

    folios.sort(key=lambda f: (f["_resolved_window"] or 99, _ts_key(f.get("created_at"))))

    out: list[WindowSummary] = []
    for f in folios:
        fid = f["id"]
        bal = await calculate_folio_balance(fid, user.tenant_id)
        c_cnt = await db.folio_charges.count_documents(
            {"tenant_id": user.tenant_id, "folio_id": fid, "voided": {"$ne": True}}
        )
        p_cnt = await db.payments.count_documents(
            {"tenant_id": user.tenant_id, "folio_id": fid, "voided": {"$ne": True}}
        )
        wn = f["_resolved_window"]
        out.append(WindowSummary(
            folio_id=fid,
            folio_number=f.get("folio_number", ""),
            window_number=wn or 0,
            payor_type=f.get("payor_type"),
            payor_id=f.get("payor_id"),
            folio_type=f.get("folio_type", ""),
            status=f.get("status", ""),
            balance=round(bal, 2),
            charges_count=c_cnt,
            payments_count=p_cnt,
            created_at=str(f.get("created_at")) if f.get("created_at") else None,
            closed_at=str(f.get("closed_at")) if f.get("closed_at") else None,
        ))
    return out


@router.patch("/{folio_id}/payor", response_model=WindowSummary)
async def change_payor(
    folio_id: str,
    body: PayorPatch,
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),
):
    """Window'un payor'unu değiştir (örn. guest→company aktarımı)."""
    folio = await db.folios.find_one(
        {"id": folio_id, "tenant_id": user.tenant_id}, {"_id": 0}
    )
    if not folio:
        raise HTTPException(404, "Folio bulunamadı")
    if folio.get("status") != FolioStatus.OPEN.value:
        raise HTTPException(409, "Yalnızca açık folio'nun payor'u değiştirilebilir")

    new_type = _payor_to_folio_type(body.payor_type)
    update = {
        "payor_type": body.payor_type,
        "payor_id": body.payor_id,
        "folio_type": new_type.value,
        "guest_id": body.payor_id if body.payor_type == "guest" else None,
        "company_id": body.payor_id if body.payor_type == "company" else None,
    }
    await db.folios.update_one({"id": folio_id, "tenant_id": user.tenant_id}, {"$set": update})

    await audit_log(
        actor_id=user.id,
        tenant_id=user.tenant_id,
        property_id=user.tenant_id,
        entity_type="folio",
        entity_id=folio_id,
        action="folio_window_payor_changed",
        metadata={
            "old_payor_type": folio.get("payor_type"),
            "old_payor_id": folio.get("payor_id"),
            "new_payor_type": body.payor_type,
            "new_payor_id": body.payor_id,
        },
    )

    bal = await calculate_folio_balance(folio_id, user.tenant_id)
    c_cnt = await db.folio_charges.count_documents(
        {"tenant_id": user.tenant_id, "folio_id": folio_id, "voided": {"$ne": True}}
    )
    p_cnt = await db.payments.count_documents(
        {"tenant_id": user.tenant_id, "folio_id": folio_id, "voided": {"$ne": True}}
    )
    # list_windows ile aynı implicit slot mantığı
    siblings = await db.folios.find(
        {"booking_id": folio.get("booking_id"), "tenant_id": user.tenant_id},
        {"_id": 0, "id": 1, "window_number": 1, "created_at": 1},
    ).to_list(500)
    wn = _resolve_window_number(folio, siblings)
    return WindowSummary(
        folio_id=folio_id,
        folio_number=folio.get("folio_number", ""),
        window_number=wn or 0,
        payor_type=body.payor_type,
        payor_id=body.payor_id,
        folio_type=new_type.value,
        status=folio.get("status", ""),
        balance=round(bal, 2),
        charges_count=c_cnt,
        payments_count=p_cnt,
        created_at=str(folio.get("created_at")) if folio.get("created_at") else None,
        closed_at=str(folio.get("closed_at")) if folio.get("closed_at") else None,
    )
