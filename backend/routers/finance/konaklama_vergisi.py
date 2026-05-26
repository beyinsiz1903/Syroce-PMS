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
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from cache_manager import cached
from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.enums import ChargeCategory
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v98 DW
from routers.finance.konaklama_vergisi_core import (
    DEFAULT_RATE_PERCENT,
    post_konaklama_vergisi_to_folio,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/finance/konaklama-vergisi", tags=["konaklama-vergisi"])


class KonaklamaVergisiConfig(BaseModel):
    rate_percent: float = Field(default=DEFAULT_RATE_PERCENT, ge=0, le=100)
    active: bool = True
    auto_post: bool = False
    effective_from: str | None = None  # ISO date
    notes: str | None = None
    exempt_segments: list[str] = Field(default_factory=list)
    # v95.9 — Otomatik beyanname + PDF e-posta otomasyonu
    auto_finalize: bool = False  # ay başında önceki ayı otomatik kilitle
    auto_finalize_day: int = Field(default=1, ge=1, le=10)
    auto_email: bool = False  # finalize sonrası PDF e-posta gönder
    email_recipients: list[str] = Field(default_factory=list)


class CalculateRequest(BaseModel):
    # F8AH P1 fix — overflow guard. Pre-fix the calculator accepted amount=1e18
    # and nights=1e7 with no upper bound, returning a quietly-truncated 200.
    # That is a fail-OPEN behaviour: a malicious or malformed client could
    # generate astronomical "tax" figures that mask integration bugs or pollute
    # accounting reports. Realistic ceilings:
    #   - amount: per-folio nightly base; 1e9 (1 milyar TL) is already orders
    #     of magnitude beyond any real reservation while staying inside float64
    #     precision and JSON-safe integer range.
    #   - nights: a single calculation covers one stay; 3650 (≈10 yıl) is a
    #     generous upper bound. Anything beyond is data-corruption / abuse.
    amount: float = Field(gt=0, le=1_000_000_000)
    nights: int = Field(default=1, ge=1, le=3650)
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
            "auto_finalize": False,
            "auto_finalize_day": 1,
            "auto_email": False,
            "email_recipients": [],
        }
    doc.pop("_id", None)
    doc.setdefault("rate_percent", doc.get("tax_percentage", DEFAULT_RATE_PERCENT))
    doc.setdefault("auto_post", False)
    doc.setdefault("exempt_segments", [])
    doc.setdefault("auto_finalize", False)
    doc.setdefault("auto_finalize_day", 1)
    doc.setdefault("auto_email", False)
    doc.setdefault("email_recipients", [])
    return doc


@router.get("/config")
@cached(ttl=300, key_prefix="kvb_config")
async def get_config(
    current_user: User = Depends(get_current_user),
    _nocache: bool = Query(False, alias="nocache"),
) -> dict[str, Any]:
    return await _load_config(current_user.tenant_id)


@router.put("/config")
async def update_config(
    cfg: KonaklamaVergisiConfig,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
) -> dict[str, Any]:
    # v95.9 — Alıcı listesini sanitize et (boş + dup + bariz invalid'i at).
    # Backend e-posta katmanı zaten _is_valid_email guard'ı çalıştırır;
    # burada erkenden trim/dedup yapıyoruz ki UI'a kaydedilen liste temiz
    # geri dönsün ve scheduler her tick'te aynı bozuk satırı denemesin.
    raw_recipients = cfg.email_recipients or []
    clean_recipients: list[str] = []
    seen_recipients: set[str] = set()
    for r in raw_recipients:
        if not isinstance(r, str):
            continue
        rs = r.strip()
        if not rs or "@" not in rs:
            continue
        key = rs.lower()
        if key in seen_recipients:
            continue
        seen_recipients.add(key)
        clean_recipients.append(rs)

    payload = {
        "tenant_id": current_user.tenant_id,
        "rate_percent": cfg.rate_percent,
        "tax_percentage": cfg.rate_percent,  # legacy field for folio.py
        "active": cfg.active,
        "auto_post": cfg.auto_post,
        "effective_from": cfg.effective_from,
        "notes": cfg.notes,
        "exempt_segments": cfg.exempt_segments,
        "auto_finalize": cfg.auto_finalize,
        "auto_finalize_day": cfg.auto_finalize_day,
        "auto_email": cfg.auto_email,
        "email_recipients": clean_recipients,
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
    # Invalidate cached config so the next GET reads fresh values.
    try:
        _cache.safe_invalidate(current_user.tenant_id, "kvb_config")
    except Exception as e:  # pragma: no cover
        logger.debug("kvb_config cache invalidation skipped: %s", e)
    return await _load_config(current_user.tenant_id)


@router.post("/calculate")
async def calculate(
    req: CalculateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v101 DW
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


async def _tenant_tz(tenant_id: str):
    """Tenant TZ'sini çöz; konaklama vergisi sadece TR olduğu için
    fallback Europe/Istanbul. tenant_settings.timezone öncelikli."""
    try:
        from zoneinfo import ZoneInfo
    except Exception:  # pragma: no cover
        return UTC
    doc = await db.tenant_settings.find_one(
        {"tenant_id": tenant_id}, {"_id": 0, "timezone": 1}) or {}
    name = doc.get("timezone") or "Europe/Istanbul"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Istanbul")


async def _period_bounds(
    tenant_id: str, year: int, month: int,
) -> tuple[datetime, datetime]:
    """Aylık dönem sınırlarını tenant TZ'ye göre üret; UTC'ye çevir.

    Önceki sürümde sınırlar doğrudan UTC ay başlangıcıydı; bu, TR'deki
    bir otelin ay sonu (ör. 31 Mart 23:30 Europe/Istanbul = 31 Mart 20:30
    UTC) charge'ını **Mart** dönemine değil **Şubat**'a/yanlış aya
    düşürebiliyordu. Şimdi ay TR yereline göre, sonra UTC'ye dönüşüyor.
    """
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="month must be 1-12")
    tz = await _tenant_tz(tenant_id)
    start_local = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=tz)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


async def _tenant_summary(tenant_id: str) -> dict[str, Any]:
    """Beyanname başlığı için tenant alanlarını normalize et.

    Tarihsel tenant şeması heterojen: hotel_name yok ama name veya
    property_name var; tax_no yok ama tax_number olabilir. Frontend
    DeclRow `tenant.hotel_name || '-'` formatıyla okuduğu için boş
    görünmesin diye burada normalize ediyoruz.
    """
    doc = await db.tenants.find_one(
        {"id": tenant_id},
        {"_id": 0, "hotel_name": 1, "name": 1, "property_name": 1,
         "tax_no": 1, "tax_number": 1, "hotel_id": 1},
    ) or {}
    return {
        "hotel_name": (doc.get("hotel_name") or doc.get("name")
                       or doc.get("property_name") or ""),
        "tax_no": doc.get("tax_no") or doc.get("tax_number") or "",
        "hotel_id": doc.get("hotel_id") or "",
    }


async def _aggregate_period(tenant_id: str, year: int, month: int) -> dict[str, Any]:
    start, end = await _period_bounds(tenant_id, year, month)
    cfg = await _load_config(tenant_id)
    rate = float(cfg.get("rate_percent", DEFAULT_RATE_PERCENT))

    # v95.7: effective_from kullanılıyor — yürürlük öncesi charge'lar matraha
    # girmesin (ör. 1 Mart'tan itibaren oran değişimi → Şubat çağrısı boş).
    # TZ-aware: effective_from tenant TZ (TR) gün başlangıcına sabitlenir,
    # sonra UTC'ye dönüşür; aksi halde TR/UTC fark penceresi yanlış dışlanır.
    effective_from = (cfg.get("effective_from") or "").strip()
    if effective_from:
        try:
            from datetime import date as _d
            tz = await _tenant_tz(tenant_id)
            ef_date = _d.fromisoformat(effective_from[:10])
            ef_dt = datetime(
                ef_date.year, ef_date.month, ef_date.day, tzinfo=tz,
            ).astimezone(UTC)
            if ef_dt > start:
                start = ef_dt
        except Exception:
            pass

    if start >= end:
        # effective_from dönemin tamamen ötesinde — boş sonuç dön.
        # v95.8: exempt_count/exempt_base alanları normal path ile aynı
        # şekilde döner; frontend her durumda alan bekleyebilsin.
        return {
            "year": year, "month": month, "rate_percent": rate,
            "folio_count": 0, "total_nights": 0, "total_base": 0.0,
            "total_tax": 0.0, "exempt_count": 0, "exempt_base": 0.0,
            "rows": [],
        }

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

    # v95.7: exempt_segments — booking.segment listede ise matrah dışı.
    # v95.8: muafiyet sayısı/tutarı rapora ayrı alan olarak yansıtılır
    # (denetim/iz için frontend "X folio muaf" notu gösterir).
    exempt = [s for s in (cfg.get("exempt_segments") or []) if s]
    exempt_count = 0
    exempt_base = 0.0
    if exempt and rows:
        booking_ids = [r.get("booking_id") for r in rows if r.get("booking_id")]
        if booking_ids:
            exempt_ids = set()
            async for b in db.bookings.find(
                {"tenant_id": tenant_id, "id": {"$in": booking_ids},
                 "segment": {"$in": exempt}},
                {"_id": 0, "id": 1},
            ):
                exempt_ids.add(b["id"])
            if exempt_ids:
                exempt_rows = [r for r in rows if r.get("booking_id") in exempt_ids]
                exempt_count = len(exempt_rows)
                exempt_base = round(sum(r.get("base_amount", 0.0) for r in exempt_rows), 2)
                rows = [r for r in rows if r.get("booking_id") not in exempt_ids]

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
        "exempt_count": exempt_count,
        "exempt_base": exempt_base,
        "rows": rows,
    }


@router.get("/report")
async def report(
    year: int | None = None,
    month: int | None = None,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    # Tur 3: defaults — current year/month when omitted
    from datetime import date as _d
    today = _d.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    return await _aggregate_period(current_user.tenant_id, year, month)


@router.get("/declaration")
async def declaration(
    year: int | None = None,
    month: int | None = None,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """GİB beyanname özeti — aylık konaklama vergisi beyannamesi."""
    # Tur 3: defaults — current year/month when omitted
    from datetime import date as _d
    today = _d.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    agg = await _aggregate_period(current_user.tenant_id, year, month)
    tenant = await _tenant_summary(current_user.tenant_id)
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


_DECL_INDEXES_READY = False


async def _ensure_declaration_indexes() -> None:
    global _DECL_INDEXES_READY
    if _DECL_INDEXES_READY:
        return
    await db.tax_declarations.create_index(
        [("tenant_id", 1), ("period", 1), ("kind", 1)], unique=True)
    await db.tax_declarations.create_index(
        [("tenant_id", 1), ("status", 1), ("period", -1)])
    _DECL_INDEXES_READY = True


def _gib_xml(decl: dict) -> str:
    """Hand-built GİB-style XML envelope for archival/upload reference.

    NOTE: GİB does not publish a public XSD for konaklama-vergisi
    e-beyanname; operators submit via İVD web form. This XML is a
    reproducible internal representation that mirrors form fields
    1:1, suitable for import into 3rd-party muhasebe software.
    """
    t = decl.get("tenant") or {}

    def _e(v: Any) -> str:
        return xml_escape(str(v if v is not None else "").strip())

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<KonaklamaVergisiBeyannamesi xmlns="urn:syroce:kvb:v1">\n'
        f'  <Donem>{_e(decl.get("period"))}</Donem>\n'
        f'  <SonOdemeTarihi>{_e(decl.get("due_date"))}</SonOdemeTarihi>\n'
        '  <Mukellef>\n'
        f'    <UnvanAdi>{_e(t.get("hotel_name"))}</UnvanAdi>\n'
        f'    <VergiNo>{_e(t.get("tax_no"))}</VergiNo>\n'
        f'    <OtelKodu>{_e(t.get("hotel_id"))}</OtelKodu>\n'
        '  </Mukellef>\n'
        '  <Matrah>\n'
        f'    <FolioSayisi>{int(decl.get("folio_count") or 0)}</FolioSayisi>\n'
        f'    <ToplamGeceleme>{float(decl.get("total_nights") or 0):.2f}'
        '</ToplamGeceleme>\n'
        f'    <ToplamMatrah>{float(decl.get("total_base") or 0):.2f}'
        '</ToplamMatrah>\n'
        '    <ParaBirimi>TRY</ParaBirimi>\n'
        '  </Matrah>\n'
        '  <Vergi>\n'
        f'    <Oran>{float(decl.get("rate_percent") or 0):.2f}</Oran>\n'
        f'    <TahakkukEdenVergi>{float(decl.get("total_tax") or 0):.2f}'
        '</TahakkukEdenVergi>\n'
        '  </Vergi>\n'
        f'  <KanunReferansi>{_e(decl.get("law_reference"))}</KanunReferansi>\n'
        '</KonaklamaVergisiBeyannamesi>\n'
    )


class FinalizeRequest(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)


class SubmitRequest(BaseModel):
    submission_ref: str = Field(min_length=3, max_length=80)
    submitted_at: str | None = None


class PaymentRequest(BaseModel):
    payment_ref: str = Field(min_length=3, max_length=80)
    paid_at: str | None = None
    amount: float | None = None


@router.post("/declaration/finalize")
async def finalize_declaration(
    body: FinalizeRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v101 DW
) -> dict[str, Any]:
    """Snapshot the period and persist a locked declaration record.

    Idempotent: if a declaration for (tenant, period) already exists
    in any non-draft status, returns it unchanged. A draft record is
    overwritten with a fresh snapshot.
    """
    await _ensure_declaration_indexes()
    period = f"{body.year}-{body.month:02d}"
    existing = await db.tax_declarations.find_one(
        {"tenant_id": current_user.tenant_id, "period": period,
         "kind": "konaklama_vergisi"}, {"_id": 0})
    if existing and existing.get("status") not in (None, "draft"):
        return existing

    agg = await _aggregate_period(current_user.tenant_id, body.year,
                                  body.month)
    tenant = await _tenant_summary(current_user.tenant_id)
    due_month = body.month + 1 if body.month < 12 else 1
    due_year = body.year if body.month < 12 else body.year + 1
    snapshot = {
        "id": existing["id"] if existing else str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "kind": "konaklama_vergisi",
        "period": period,
        "year": body.year,
        "month": body.month,
        "due_date": f"{due_year}-{due_month:02d}-26",
        "tenant": tenant,
        "rate_percent": agg["rate_percent"],
        "folio_count": agg["folio_count"],
        "total_nights": agg["total_nights"],
        "total_base": agg["total_base"],
        "total_tax": agg["total_tax"],
        "rows": agg["rows"],
        "currency": "TRY",
        "law_reference": "7194 sayılı Kanun — Konaklama Vergisi",
        "status": "finalized",
        "finalized_at": datetime.now(UTC).isoformat(),
        "finalized_by": current_user.id,
        "submission_ref": None,
        "submitted_at": None,
        "submitted_by": None,
        "payment_ref": None,
        "paid_at": None,
        "paid_by": None,
        "paid_amount": None,
    }
    # Atomic guard: only write if no record exists OR existing is still
    # in draft. Prevents a concurrent/late finalize from regressing a
    # record that another request just promoted (submitted/paid).
    res = await db.tax_declarations.update_one(
        {"tenant_id": current_user.tenant_id, "period": period,
         "kind": "konaklama_vergisi",
         "$or": [{"status": {"$in": [None, "draft"]}},
                 {"status": {"$exists": False}}]},
        {"$set": snapshot}, upsert=True)
    if not (res.matched_count or res.upserted_id):
        # Lost the race — another caller already finalized; return latest.
        latest = await db.tax_declarations.find_one(
            {"tenant_id": current_user.tenant_id, "period": period,
             "kind": "konaklama_vergisi"}, {"_id": 0})
        return latest or snapshot
    await create_audit_log(
        tenant_id=current_user.tenant_id, user=current_user,
        action="FINALIZE_KONAKLAMA_BEYANNAME",
        entity_type="tax_declaration", entity_id=snapshot["id"],
        changes={"period": period, "total_tax": snapshot["total_tax"]})
    return snapshot


@router.get("/declarations")
async def list_declarations(
    limit: int = 24,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cursor = db.tax_declarations.find(
        {"tenant_id": current_user.tenant_id,
         "kind": "konaklama_vergisi"}, {"_id": 0, "rows": 0}
    ).sort("period", -1).limit(max(1, min(limit, 120)))
    items = await cursor.to_list(length=None)
    return {"count": len(items), "items": items}


async def _load_decl(tenant_id: str, decl_id: str) -> dict:
    doc = await db.tax_declarations.find_one(
        {"id": decl_id, "tenant_id": tenant_id,
         "kind": "konaklama_vergisi"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Beyanname bulunamadı")
    return doc


@router.get("/declarations/{decl_id}")
async def get_declaration(
    decl_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await _load_decl(current_user.tenant_id, decl_id)


@router.post("/declarations/{decl_id}/submit")
async def submit_declaration(
    decl_id: str, body: SubmitRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v101 DW
) -> dict[str, Any]:
    decl = await _load_decl(current_user.tenant_id, decl_id)
    if decl.get("status") not in ("finalized",):
        raise HTTPException(
            409, f"Yalnızca onaylanmış (finalized) beyannameler gönderilebilir "
                 f"(mevcut: {decl.get('status')})")
    upd = {
        "status": "submitted",
        "submission_ref": body.submission_ref.strip(),
        "submitted_at": (body.submitted_at
                         or datetime.now(UTC).isoformat()),
        "submitted_by": current_user.id,
    }
    # Atomic transition: only flip if status is still 'finalized'.
    res = await db.tax_declarations.update_one(
        {"id": decl_id, "tenant_id": current_user.tenant_id,
         "status": "finalized"},
        {"$set": upd})
    if not res.matched_count:
        raise HTTPException(409, "Beyanname durumu bu arada değişti")
    await create_audit_log(
        tenant_id=current_user.tenant_id, user=current_user,
        action="SUBMIT_KONAKLAMA_BEYANNAME",
        entity_type="tax_declaration", entity_id=decl_id,
        changes=upd)
    return await _load_decl(current_user.tenant_id, decl_id)


@router.post("/declarations/{decl_id}/pay")
async def pay_declaration(
    decl_id: str, body: PaymentRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v101 DW
) -> dict[str, Any]:
    decl = await _load_decl(current_user.tenant_id, decl_id)
    if decl.get("status") not in ("submitted", "finalized"):
        raise HTTPException(
            409, "Yalnızca onaylanmış/gönderilmiş beyanname için ödeme "
                 "kaydedilebilir")
    upd = {
        "status": "paid",
        "payment_ref": body.payment_ref.strip(),
        "paid_at": body.paid_at or datetime.now(UTC).isoformat(),
        "paid_by": current_user.id,
        "paid_amount": (body.amount if body.amount is not None
                        else decl.get("total_tax")),
    }
    # Atomic: never overwrite a record that's already paid.
    res = await db.tax_declarations.update_one(
        {"id": decl_id, "tenant_id": current_user.tenant_id,
         "status": {"$in": ["finalized", "submitted"]}},
        {"$set": upd})
    if not res.matched_count:
        raise HTTPException(409, "Ödeme zaten kaydedilmiş veya durum uygun değil")
    await create_audit_log(
        tenant_id=current_user.tenant_id, user=current_user,
        action="PAY_KONAKLAMA_BEYANNAME",
        entity_type="tax_declaration", entity_id=decl_id, changes=upd)
    return await _load_decl(current_user.tenant_id, decl_id)


def _decl_html(decl: dict) -> str:
    """Beyanname için yazdırılabilir/PDF dostu HTML.

    weasyprint render'ı için kullanılır; aynı zamanda e-posta gövdesi
    olarak da gönderilebilir. CSS print mediasıyla A4 sayfa düzeni
    verir; harici font/asset gerektirmez (offline-safe).
    """
    t = decl.get("tenant") or {}
    rate = float(decl.get("rate_percent") or 0)
    base = float(decl.get("total_base") or 0)
    tax = float(decl.get("total_tax") or 0)
    nights = float(decl.get("total_nights") or 0)
    folio_count = int(decl.get("folio_count") or 0)

    def _e(v: Any) -> str:
        return xml_escape(str(v if v is not None else "").strip())

    def _money(v: float) -> str:
        return f"{v:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")

    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>Konaklama Vergisi Beyannamesi {_e(decl.get('period'))}</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font-family: 'Helvetica', 'Arial', sans-serif; color:#0f172a; font-size: 11pt; }}
  h1 {{ font-size: 16pt; margin: 0 0 4px; text-align: center; }}
  .sub {{ text-align:center; color:#64748b; font-size: 9pt; margin-bottom: 18px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align:left; }}
  td.r {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .total {{ background:#f8fafc; font-weight: 700; font-size: 12pt; }}
  .meta td {{ border:none; padding: 3px 0; }}
  .meta td.k {{ color:#64748b; width: 40%; }}
  .footer {{ margin-top: 28px; font-size: 8pt; color:#94a3b8; line-height: 1.5; }}
</style></head>
<body>
  <h1>KONAKLAMA VERGİSİ BEYANNAMESİ</h1>
  <div class="sub">{_e(decl.get('law_reference'))}</div>

  <table class="meta">
    <tr><td class="k">İşletme</td><td>{_e(t.get('hotel_name'))}</td></tr>
    <tr><td class="k">Vergi No / Otel ID</td><td>{_e(t.get('tax_no') or t.get('hotel_id'))}</td></tr>
    <tr><td class="k">Dönem</td><td>{_e(decl.get('period'))}</td></tr>
    <tr><td class="k">Son Beyan/Ödeme Tarihi</td><td>{_e(decl.get('due_date'))}</td></tr>
    <tr><td class="k">Vergi Oranı</td><td>%{rate:.2f}</td></tr>
  </table>

  <table>
    <tr><th>Folio Sayısı</th><td class="r">{folio_count}</td></tr>
    <tr><th>Toplam Geceleme</th><td class="r">{nights:.2f}</td></tr>
    <tr><th>Matrah (KDV hariç)</th><td class="r">{_money(base)}</td></tr>
    <tr class="total"><th>Tahakkuk Eden Vergi</th><td class="r">{_money(tax)}</td></tr>
  </table>

  <div class="footer">
    Bu özet, dahili kontrol amaçlıdır. Resmi beyanname için Gelir İdaresi
    Başkanlığı (GİB) e-Beyanname sistemini kullanınız. XML çıktısı GİB form
    alanlarıyla 1-1 eşleşir; muhasebe yazılımına aktarmak için
    kullanabilirsiniz. Otomatik üretildi: {_e(datetime.now(UTC).isoformat()[:19])} UTC.
  </div>
</body></html>"""


def _decl_pdf_bytes(decl: dict) -> bytes:
    """Beyanname HTML'ini weasyprint ile PDF byte'larına dönüştürür.

    weasyprint cairo/pango bağımlılığı isteyen ağır bir kütüphane; lazy
    import ile başlatma gecikmesi önlenir. Hata olursa caller'a açık
    şekilde fırlatır — sessiz fallback yok (kullanıcı PDF butonuna
    bastıysa ya PDF gelir ya net hata görür).
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            500, f"PDF üretimi için weasyprint yüklü değil: {exc}",
        ) from exc
    html = _decl_html(decl)
    return HTML(string=html).write_pdf()


@router.get("/declarations/{decl_id}/export")
async def export_declaration(
    decl_id: str, format: str = "xml",
    current_user: User = Depends(get_current_user),
):
    from fastapi.responses import Response
    decl = await _load_decl(current_user.tenant_id, decl_id)
    fmt = (format or "xml").lower()
    if fmt == "xml":
        body = _gib_xml(decl)
        return Response(
            content=body, media_type="application/xml",
            headers={"Content-Disposition":
                     f'attachment; filename="kvb-{decl["period"]}.xml"'})
    if fmt == "json":
        import json as _json
        body = _json.dumps(decl, ensure_ascii=False, indent=2)
        return Response(
            content=body, media_type="application/json",
            headers={"Content-Disposition":
                     f'attachment; filename="kvb-{decl["period"]}.json"'})
    if fmt == "pdf":
        pdf = _decl_pdf_bytes(decl)
        return Response(
            content=pdf, media_type="application/pdf",
            headers={"Content-Disposition":
                     f'attachment; filename="kvb-{decl["period"]}.pdf"'})
    raise HTTPException(400, "format yalnızca xml|json|pdf olabilir")


class EmailRequest(BaseModel):
    recipients: list[str] | None = None
    note: str | None = None


@router.post("/declarations/{decl_id}/email")
async def email_declaration(
    decl_id: str,
    body: EmailRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v101 DW
) -> dict[str, Any]:
    """Beyannameyi PDF ek olarak e-posta gönder.

    `recipients` boşsa config'teki `email_recipients` kullanılır. Resend
    API üzerinden gönderim yapılır; her alıcıya ayrı bir mesaj gider
    (Resend tek isteğe çok alıcı destekler ama bireysel iz/teslim
    raporları için ayırıyoruz).
    """
    from core.email import _is_valid_email, send_email
    decl = await _load_decl(current_user.tenant_id, decl_id)

    cfg = await _load_config(current_user.tenant_id)
    raw = body.recipients if body.recipients is not None else cfg.get(
        "email_recipients") or []
    seen: set[str] = set()
    targets: list[str] = []
    for r in raw:
        if not isinstance(r, str):
            continue
        rs = r.strip()
        if not rs or not _is_valid_email(rs):
            continue
        k = rs.lower()
        if k in seen:
            continue
        seen.add(k)
        targets.append(rs)
    if not targets:
        raise HTTPException(
            400, "Alıcı bulunamadı — e-posta adresi ekleyin veya "
                 "Yapılandırma → Alıcılar listesine en az bir geçerli "
                 "adres girin.")

    pdf_bytes = _decl_pdf_bytes(decl)
    period = decl.get("period") or ""
    subject = f"Konaklama Vergisi Beyannamesi — {period}"
    note_html = ""
    if body.note:
        from core.mailing_safe import safe_html_value
        note_html = (
            f"<p style='margin:0 0 12px;color:#0f172a;'>"
            f"{safe_html_value(body.note)}</p>"
        )
    html = (
        "<div style='font-family:Helvetica,Arial,sans-serif;max-width:600px;"
        "margin:0 auto;padding:18px;color:#0f172a;'>"
        f"<h2 style='margin:0 0 8px;'>Konaklama Vergisi Beyannamesi — {period}</h2>"
        f"<p style='color:#64748b;margin:0 0 16px;'>"
        f"Son ödeme tarihi: <b>{decl.get('due_date','-')}</b> &middot; "
        f"Tahakkuk eden vergi: <b>{float(decl.get('total_tax') or 0):.2f} TL</b>"
        "</p>"
        f"{note_html}"
        "<p style='margin:0 0 8px;'>Beyanname özeti PDF olarak ekte yer "
        "almaktadır. Resmi beyan için GİB e-Beyanname sistemini kullanınız.</p>"
        "<p style='font-size:11px;color:#94a3b8;margin-top:18px;'>"
        "Syroce PMS · Otomatik üretilmiş bildirim"
        "</p></div>"
    )
    attachments = [{
        "filename": f"kvb-{period}.pdf",
        "content": pdf_bytes,
        "content_type": "application/pdf",
    }]

    sent_ok = 0
    failures: list[dict] = []
    for to in targets:
        res = await send_email(
            to=to, subject=subject, html=html, attachments=attachments,
        )
        if res.get("sent"):
            sent_ok += 1
        else:
            failures.append({"to": to, "error": res.get("error") or res.get("provider")})

    # Audit + decl meta — son gönderim izini decl üzerinde tut.
    await db.tax_declarations.update_one(
        {"id": decl_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "last_email_at": datetime.now(UTC).isoformat(),
            "last_email_by": current_user.id,
            "last_email_recipients": targets,
            "last_email_ok": sent_ok,
            "last_email_failures": failures,
        }})
    await create_audit_log(
        tenant_id=current_user.tenant_id, user=current_user,
        action="EMAIL_KONAKLAMA_BEYANNAME",
        entity_type="tax_declaration", entity_id=decl_id,
        changes={"recipients": targets, "ok": sent_ok,
                 "failures": len(failures)})
    return {
        "sent": sent_ok,
        "total": len(targets),
        "recipients": targets,
        "failures": failures,
    }


@router.post("/post-folio/{folio_id}")
async def post_to_folio(
    folio_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v101 DW
) -> dict[str, Any]:
    """Bir folio için konaklama vergisi satırını idempotent olarak ekle.

    Asıl iş `konaklama_vergisi_core.post_konaklama_vergisi_to_folio` içinde;
    bu endpoint sadece HTTP/RBAC katmanı + audit log üretiyor.
    """
    result = await post_konaklama_vergisi_to_folio(
        tenant_id=current_user.tenant_id,
        folio_id=folio_id,
        posted_by=current_user.id,
        raise_on_error=False,
    )
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "folio_not_found":
            raise HTTPException(status_code=404, detail="Folio not found")
        if reason == "inactive":
            raise HTTPException(status_code=400, detail="Konaklama Vergisi devre dışı")
        if reason == "no_room_charges":
            raise HTTPException(status_code=400, detail="Vergilenecek oda satırı yok")
        raise HTTPException(status_code=400, detail=reason or "Posting failed")

    if result.get("posted"):
        await create_audit_log(
            tenant_id=current_user.tenant_id,
            user=current_user,
            action="POST_KONAKLAMA_VERGISI",
            entity_type="folio_charge",
            entity_id=result.get("charge_id"),
            changes={
                "folio_id": folio_id,
                "base": result.get("base_amount"),
                "tax": result.get("tax_amount"),
                "rate": result.get("rate_percent"),
                "trigger": "manual",
            },
        )
    return {
        "posted": bool(result.get("posted")),
        "already_posted": bool(result.get("already_posted")),
        "posting_id": result.get("posting_id"),
        "charge_id": result.get("charge_id"),
        "base_amount": result.get("base_amount"),
        "tax_amount": result.get("tax_amount"),
        "rate_percent": result.get("rate_percent"),
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
