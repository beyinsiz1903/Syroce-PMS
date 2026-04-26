"""KBS (Konaklama Bildirim Sistemi) — Kullanıcı oturumu tabanlı uçlar.

Bu router, masaüstü/yardımcı KBS uygulamasının PMS otel kullanıcısının
kendi e-posta + şifre bilgileriyle (POST /api/auth/login) giriş yapıp
dönen JWT token'ı ile çalışmasını sağlar. Her otel için ayrı API key
dağıtmaya gerek yoktur — tenant_id, oturumdaki kullanıcıdan otomatik
çözülür ve kullanıcı sadece kendi otelinin verisini görür.

Endpoint'ler (legacy / pull-mark akışı):
  GET  /api/kbs/guests             — bir günün KBS'ye girecek misafirleri
  POST /api/kbs/report             — gönderim işareti (rapor kaydı)
  GET  /api/kbs/reports            — geçmiş raporlar
  GET  /api/kbs/reports/{id}       — rapor detayı

Endpoint'ler (Faz 1 — kuyruk altyapısı, agent uygulaması için):
  POST /api/kbs/queue              — bildirim kuyruğa ekle (idempotent)
  GET  /api/kbs/queue              — kuyruk listele + stat'lar
  POST /api/kbs/queue/{id}/claim   — atomik lease (worker iş alır)
  POST /api/kbs/queue/{id}/complete — başarı + KBS referans no
  POST /api/kbs/queue/{id}/fail    — hata + exp. backoff retry / dead
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from core.tenant_db import tenant_context
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v98 DW

router = APIRouter(prefix="/api/kbs", tags=["KBS"])


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


@router.get("/guests")
async def kbs_guest_list(
    date: str | None = Query(None, description="YYYY-MM-DD (varsayılan: bugün)"),
    status: str | None = Query(None, description="Booking status filtresi"),
    limit: int = Query(200, le=500),
    current_user: User = Depends(get_current_user),
):
    """KBS bildirimine girecek misafir listesi (oturumdaki kullanıcının oteli için)."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")
    status_filter = (
        [status] if status
        else ["checked_in", "confirmed", "guaranteed"]
    )

    with tenant_context(tenant_id):
        bookings = await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": status_filter},
                "check_in": {
                    "$gte": target_date + "T00:00:00",
                    "$lte": target_date + "T23:59:59",
                },
            },
            {
                "_id": 0, "id": 1, "guest_id": 1, "guest_name": 1,
                "guest_email": 1, "guest_phone": 1, "room_number": 1,
                "check_in": 1, "check_out": 1, "adults": 1, "children": 1,
                "status": 1, "confirmation_code": 1,
            },
        ).sort("check_in", 1).to_list(limit)

        guest_ids = [b.get("guest_id") for b in bookings if b.get("guest_id")]
        guest_map: dict[str, dict] = {}
        if guest_ids:
            async for g in db.guests.find(
                {"tenant_id": tenant_id, "id": {"$in": guest_ids}},
                {"_id": 0, "id": 1, "nationality": 1, "id_number": 1,
                 "passport_number": 1, "birth_date": 1, "gender": 1,
                 "address": 1, "father_name": 1, "mother_name": 1,
                 "birth_place": 1},
            ):
                guest_map[g["id"]] = g

        for b in bookings:
            g = guest_map.get(b.get("guest_id"), {})
            b["nationality"] = g.get("nationality", "")
            b["id_number"] = g.get("id_number", "")
            b["passport_number"] = g.get("passport_number", "")
            b["birth_date"] = g.get("birth_date", "")
            b["gender"] = g.get("gender", "")
            b["address"] = g.get("address", "")
            b["father_name"] = g.get("father_name", "")
            b["mother_name"] = g.get("mother_name", "")
            b["birth_place"] = g.get("birth_place", "")
            b["kbs_ready"] = bool(
                (g.get("id_number") or g.get("passport_number"))
                and g.get("birth_date")
                and g.get("nationality")
            )

        reports = await db.kbs_reports.find(
            {
                "tenant_id": tenant_id, "date": target_date,
                "_kind": {"$ne": "queue_job"},
            },
            {"_id": 0},
        ).sort("created_at", -1).to_list(50)

    return {
        "date": target_date,
        "tenant_id": tenant_id,
        "guests": bookings,
        "guest_count": len(bookings),
        "ready_count": sum(1 for b in bookings if b.get("kbs_ready")),
        "missing_info_count": sum(1 for b in bookings if not b.get("kbs_ready")),
        "reports": reports,
        "report_count": len(reports),
    }


class KBSReportCreate(BaseModel):
    date: str
    booking_ids: list[str] = []
    notes: str = ""
    submission_reference: str = ""


@router.post("/report")
async def kbs_create_report(
    data: KBSReportCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # v98 DW
):
    """KBS resmi servisine gönderim sonrası PMS'e işaret bırak."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    report_id = _uuid()
    report = {
        "_kind": REPORT_KIND,
        "id": report_id,
        "tenant_id": tenant_id,
        "date": data.date,
        "status": "submitted",
        "guest_count": len(data.booking_ids),
        "guest_ids": data.booking_ids,
        "notes": data.notes,
        "submission_reference": data.submission_reference,
        "submitted_by": f"user:{current_user.id}",
        "submitted_by_email": current_user.email,
        "created_at": _now_iso(),
    }
    with tenant_context(tenant_id):
        await db.kbs_reports.insert_one(report)
        if data.booking_ids:
            await db.bookings.update_many(
                {"tenant_id": tenant_id, "id": {"$in": data.booking_ids}},
                {"$set": {
                    "kbs_reported": True,
                    "kbs_report_id": report_id,
                    "kbs_reported_at": _now_iso(),
                }},
            )
    report.pop("_id", None)
    return {"ok": True, "report": report}


@router.get("/reports")
async def kbs_list_reports(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """Geçmiş KBS raporları (oturumdaki kullanıcının oteli için)."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    q: dict = {"tenant_id": tenant_id, "_kind": {"$ne": "queue_job"}}
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to

    with tenant_context(tenant_id):
        docs = await db.kbs_reports.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"reports": docs, "total": len(docs)}


@router.get("/reports/{report_id}")
async def kbs_get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    with tenant_context(tenant_id):
        doc = await db.kbs_reports.find_one(
            {
                "tenant_id": tenant_id, "id": report_id,
                "_kind": {"$ne": "queue_job"},
            },
            {"_id": 0},
        )
    if not doc:
        raise HTTPException(404, "KBS raporu bulunamadı")
    return {"report": doc}


@router.get("/me")
async def kbs_who_am_i(current_user: User = Depends(get_current_user)):
    """KBS uygulaması için 'login başarılı mı, hangi otele bağlıyım' kontrolü."""
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "full_name": getattr(current_user, "full_name", ""),
        "tenant_id": current_user.tenant_id,
        "role": getattr(current_user, "role", ""),
    }


# ============================================================
# Faz 1 — Kuyruk altyapısı (kbs_queue)
# ============================================================
# Atomik claim + lease + exponential-backoff retry pattern.
# Worker (agent app) login → POST /queue/{id}/claim → KBS'ye gönderir →
# başarıysa /complete, hata ise /fail çağırır. Lease süresi geçen
# in_progress kayıtlar yeniden claim edilebilir (stuck worker recovery).
# ============================================================

QUEUE_STATUSES = ("pending", "in_progress", "done", "failed", "dead")
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LEASE_SECONDS = 300  # 5 dk

# Atlas tier 500-collection limit nedeniyle kuyruk işleri kbs_reports
# collection'ında `_kind: "queue_job"` discriminator'ı ile saklanır.
# Legacy raporlar `_kind: "report"` (yoksa null) ile işaretlenir.
QUEUE_KIND = "queue_job"
REPORT_KIND = "report"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _backoff_seconds(attempts: int) -> int:
    """Exp. backoff: 60s, 120s, 240s, 480s, 960s, cap 3600s."""
    base = 60 * (2 ** max(attempts - 1, 0))
    return min(base, 3600)


def _scrub(doc: dict | None) -> dict | None:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


async def _build_payload_snapshot(
    tenant_id: str, booking_id: str
) -> tuple[dict, dict, dict]:
    """booking + guest verisini birleştirip snapshot çıkarır.

    Returns: (booking, guest, snapshot)
    Raises: HTTPException(404) if booking bulunamazsa.
    """
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {
            "_id": 0, "id": 1, "guest_id": 1, "guest_name": 1,
            "guest_email": 1, "guest_phone": 1, "room_number": 1,
            "check_in": 1, "check_out": 1, "adults": 1, "children": 1,
            "status": 1, "confirmation_code": 1, "guest_nationality": 1,
        },
    )
    if not booking:
        raise HTTPException(404, f"Rezervasyon bulunamadı: {booking_id}")

    guest = {}
    if booking.get("guest_id"):
        guest = await db.guests.find_one(
            {"tenant_id": tenant_id, "id": booking["guest_id"]},
            {
                "_id": 0, "id": 1, "nationality": 1, "id_number": 1,
                "passport_number": 1, "birth_date": 1, "gender": 1,
                "address": 1, "father_name": 1, "mother_name": 1,
                "birth_place": 1,
            },
        ) or {}

    snapshot = {
        "guest_name": booking.get("guest_name", ""),
        "room_number": booking.get("room_number", ""),
        "check_in": booking.get("check_in", ""),
        "check_out": booking.get("check_out", ""),
        "nationality": guest.get("nationality")
            or booking.get("guest_nationality") or "TC",
        "id_number": guest.get("id_number", ""),
        "passport_number": guest.get("passport_number", ""),
        "birth_date": guest.get("birth_date", ""),
        "gender": guest.get("gender", ""),
        "father_name": guest.get("father_name", ""),
        "mother_name": guest.get("mother_name", ""),
        "birth_place": guest.get("birth_place", ""),
        "address": guest.get("address", ""),
    }
    return booking, guest, snapshot


# --- 1) Enqueue ---------------------------------------------

class KBSQueueEnqueue(BaseModel):
    booking_id: str = Field(..., min_length=1)
    action: str = Field("checkin", pattern="^(checkin|checkout)$")
    force: bool = False
    max_attempts: int = Field(DEFAULT_MAX_ATTEMPTS, ge=1, le=20)
    notes: str = ""


@router.post("/queue", status_code=201)
async def kbs_queue_enqueue(
    data: KBSQueueEnqueue,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # KBS perm with legacy reports
):
    """Bildirimi kuyruğa ekle. Aynı (booking_id, action) için pending/in_progress
    iş varsa mevcut işi döner (idempotent), force=true ise yeni iş açar."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    with tenant_context(tenant_id):
        if not data.force:
            existing = await db.kbs_reports.find_one(
                {
                    "_kind": QUEUE_KIND,
                    "tenant_id": tenant_id,
                    "booking_id": data.booking_id,
                    "action": data.action,
                    "status": {"$in": ["pending", "in_progress"]},
                },
                {"_id": 0},
            )
            if existing:
                return {"job": existing, "created": False}

        booking, guest, snapshot = await _build_payload_snapshot(
            tenant_id, data.booking_id
        )

        now = _now()
        job = {
            "_kind": QUEUE_KIND,
            "id": _uuid(),
            "tenant_id": tenant_id,
            "booking_id": data.booking_id,
            "guest_id": booking.get("guest_id"),
            "action": data.action,
            "status": "pending",
            "attempts": 0,
            "max_attempts": data.max_attempts,
            "worker_id": None,
            "leased_until": None,
            "next_retry_at": None,
            "last_error": None,
            "kbs_reference": None,
            "payload": snapshot,
            "notes": data.notes,
            "enqueued_by": current_user.email,
            "created_at": _iso(now),
            "updated_at": _iso(now),
            "claimed_at": None,
            "completed_at": None,
            "failed_at": None,
        }
        await db.kbs_reports.insert_one(job)
        job.pop("_id", None)
    return {"job": job, "created": True}


# --- 2) List + stats ----------------------------------------

@router.get("/queue")
async def kbs_queue_list(
    status: str | None = Query(
        None, description="Virgülle ayrılmış: pending,in_progress,done,failed,dead"
    ),
    booking_id: str | None = Query(None),
    date_from: str | None = Query(None, description="created_at >= ISO date"),
    date_to: str | None = Query(None, description="created_at <= ISO date"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Kuyruk listesi + tüm statüler için sayım (status bar için)."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    q: dict = {"_kind": QUEUE_KIND, "tenant_id": tenant_id}
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        bad = [s for s in wanted if s not in QUEUE_STATUSES]
        if bad:
            raise HTTPException(400, f"Geçersiz status: {bad}")
        q["status"] = {"$in": wanted}
    if booking_id:
        q["booking_id"] = booking_id
    if date_from or date_to:
        q["created_at"] = {}
        if date_from:
            q["created_at"]["$gte"] = date_from
        if date_to:
            q["created_at"]["$lte"] = date_to + "T23:59:59"

    with tenant_context(tenant_id):
        jobs = await db.kbs_reports.find(q, {"_id": 0}).sort(
            "created_at", -1
        ).to_list(limit)

        # Tüm statüler için sayım (status bar)
        pipeline = [
            {"$match": {"_kind": QUEUE_KIND, "tenant_id": tenant_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        stats = {s: 0 for s in QUEUE_STATUSES}
        async for row in db.kbs_reports.aggregate(pipeline):
            if row["_id"] in stats:
                stats[row["_id"]] = row["count"]

    return {
        "jobs": jobs,
        "total": len(jobs),
        "stats": stats,
    }


# --- 3) Atomic claim with lease -----------------------------

class KBSQueueClaim(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    lease_seconds: int = Field(DEFAULT_LEASE_SECONDS, ge=30, le=3600)


@router.post("/queue/{job_id}/claim")
async def kbs_queue_claim(
    job_id: str,
    data: KBSQueueClaim,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Atomik claim: pending → in_progress (worker_id + lease).

    Stuck-worker kurtarma: in_progress AND leased_until < now ise yeniden
    claim edilebilir. Aksi halde 409 döner (başkası işliyor).
    Her başarılı claim'de attempts +1.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    now = _now()
    leased_until = now + timedelta(seconds=data.lease_seconds)

    # Atomik: ya pending (backoff penceresi geçmiş) ya da lease'i süren in_progress
    now_iso = _iso(now)
    query = {
        "_kind": QUEUE_KIND,
        "tenant_id": tenant_id,
        "id": job_id,
        "$or": [
            # Server-side backoff zorlaması: pending iş ancak retry penceresi
            # geçtiyse claim edilebilir (next_retry_at boş ya da geçmişte)
            {"$and": [
                {"status": "pending"},
                {"$or": [
                    {"next_retry_at": None},
                    {"next_retry_at": {"$exists": False}},
                    {"next_retry_at": {"$lte": now_iso}},
                ]},
            ]},
            # Stuck-worker kurtarma: lease süresi dolmuş in_progress
            {"status": "in_progress", "leased_until": {"$lt": now_iso}},
        ],
    }
    update = {
        "$set": {
            "status": "in_progress",
            "worker_id": data.worker_id,
            "leased_until": _iso(leased_until),
            "claimed_at": _iso(now),
            "updated_at": _iso(now),
        },
        "$inc": {"attempts": 1},
    }

    with tenant_context(tenant_id):
        # find_one_and_update'da return_document=AFTER yok ise sonuç eski hâl olabilir;
        # motor 3.x sürümünde ReturnDocument.AFTER lazım. Burada güvenli yol: update,
        # sonra fresh fetch.
        result = await db.kbs_reports.update_one(query, update)
        if result.modified_count == 0:
            existing = await db.kbs_reports.find_one(
                {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
                {"_id": 0},
            )
            if not existing:
                raise HTTPException(404, "İş bulunamadı")
            if existing["status"] in ("done", "dead"):
                raise HTTPException(
                    409,
                    f"İş zaten kapanmış ({existing['status']})",
                )
            # Backoff penceresinde mi?
            next_retry = existing.get("next_retry_at")
            if existing["status"] == "pending" and next_retry and next_retry > now_iso:
                raise HTTPException(
                    409,
                    f"Retry penceresi dolmadı, şu zamana kadar bekle: {next_retry}",
                )
            raise HTTPException(
                409,
                f"İş başka bir worker tarafından işleniyor: "
                f"{existing.get('worker_id')}",
            )
        job = await db.kbs_reports.find_one(
            {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
            {"_id": 0},
        )
        # max_attempts aşıldıysa hemen dead'e çek
        if job and job.get("attempts", 0) > job.get(
            "max_attempts", DEFAULT_MAX_ATTEMPTS
        ):
            await db.kbs_reports.update_one(
                {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
                {"$set": {
                    "status": "dead",
                    "failed_at": _iso(now),
                    "updated_at": _iso(now),
                    "last_error": "max_attempts exceeded on claim",
                }},
            )
            raise HTTPException(
                409, "Maks. deneme sayısı aşıldı (dead)"
            )

    return {"job": job}


# --- 4) Complete --------------------------------------------

class KBSQueueComplete(BaseModel):
    worker_id: str = Field(..., min_length=1)
    kbs_reference: str = Field(..., min_length=1, max_length=200)
    notes: str = ""


@router.post("/queue/{job_id}/complete")
async def kbs_queue_complete(
    job_id: str,
    data: KBSQueueComplete,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Worker başarıyla bildirdi: in_progress → done.

    Sadece claim'i alan worker tamamlayabilir (worker_id eşleşmeli).
    Side-effect: bookings.kbs_reported = true; legacy uyumluluk için
    kbs_reports'a tek-misafir özet kaydı yazılır.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    now = _now()
    with tenant_context(tenant_id):
        job = await db.kbs_reports.find_one(
            {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
            {"_id": 0},
        )
        if not job:
            raise HTTPException(404, "İş bulunamadı")
        if job["status"] != "in_progress":
            raise HTTPException(
                409,
                f"Sadece in_progress işler tamamlanabilir (mevcut: {job['status']})",
            )
        if job.get("worker_id") != data.worker_id:
            raise HTTPException(
                403,
                f"Bu işi farklı worker claim etmiş: {job.get('worker_id')}",
            )

        # CAS: yalnızca hâlâ aynı worker'ın in_progress'i ise geçir.
        # Çift complete çağrısında ya da worker arada değiştiyse side-effect tetiklenmez.
        cas_result = await db.kbs_reports.update_one(
            {
                "_kind": QUEUE_KIND,
                "tenant_id": tenant_id,
                "id": job_id,
                "status": "in_progress",
                "worker_id": data.worker_id,
            },
            {"$set": {
                "status": "done",
                "kbs_reference": data.kbs_reference,
                "completed_at": _iso(now),
                "updated_at": _iso(now),
                "notes": (job.get("notes") or "") + (
                    ("\n" + data.notes) if data.notes else ""
                ),
            }},
        )
        if cas_result.modified_count == 0:
            # İş aralıkta değişti (lease expired + başka worker claim etti vs.)
            raise HTTPException(
                409,
                "İş aralıkta değişti, complete uygulanamadı (lease expired olabilir)",
            )
        # Booking üzerine bayrak
        await db.bookings.update_one(
            {"tenant_id": tenant_id, "id": job["booking_id"]},
            {"$set": {
                "kbs_reported": True,
                "kbs_reported_at": _iso(now),
                "kbs_reference": data.kbs_reference,
            }},
        )
        # Legacy uyumluluk: kbs_reports'a özet ekle (_kind=report)
        report_id = _uuid()
        await db.kbs_reports.insert_one({
            "_kind": REPORT_KIND,
            "id": report_id,
            "tenant_id": tenant_id,
            "date": (job["payload"].get("check_in") or _iso(now))[:10],
            "status": "submitted",
            "guest_count": 1,
            "guest_ids": [job["booking_id"]],
            "submission_reference": data.kbs_reference,
            "notes": data.notes or "via queue",
            "submitted_by": f"worker:{data.worker_id}",
            "submitted_by_email": current_user.email,
            "queue_job_id": job_id,
            "created_at": _iso(now),
        })

        job = await db.kbs_reports.find_one(
            {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
            {"_id": 0},
        )
    return {"job": job, "report_id": report_id}


# --- 5) Fail (with retry / dead) ----------------------------

class KBSQueueFail(BaseModel):
    worker_id: str = Field(..., min_length=1)
    error: str = Field(..., min_length=1, max_length=2000)
    retry: bool = True


@router.post("/queue/{job_id}/fail")
async def kbs_queue_fail(
    job_id: str,
    data: KBSQueueFail,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Worker hata bildirdi.

    retry=True ve attempts < max_attempts → status=pending,
      next_retry_at = now + exp.backoff(attempts), worker/lease temizlenir.
    Aksi halde → status=dead, failed_at set edilir.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    now = _now()
    with tenant_context(tenant_id):
        job = await db.kbs_reports.find_one(
            {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
            {"_id": 0},
        )
        if not job:
            raise HTTPException(404, "İş bulunamadı")
        if job["status"] != "in_progress":
            raise HTTPException(
                409,
                f"Sadece in_progress iş fail edilebilir (mevcut: {job['status']})",
            )
        if job.get("worker_id") != data.worker_id:
            raise HTTPException(
                403,
                f"Bu işi farklı worker claim etmiş: {job.get('worker_id')}",
            )

        attempts = job.get("attempts", 0)
        max_attempts = job.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
        will_retry = data.retry and attempts < max_attempts
        next_retry_at = None

        if will_retry:
            next_retry_at = _iso(
                now + timedelta(seconds=_backoff_seconds(attempts))
            )
            update = {
                "status": "pending",
                "worker_id": None,
                "leased_until": None,
                "next_retry_at": next_retry_at,
                "last_error": data.error,
                "updated_at": _iso(now),
            }
        else:
            update = {
                "status": "dead",
                "failed_at": _iso(now),
                "last_error": data.error,
                "updated_at": _iso(now),
            }

        # CAS: idempotent. İş aralıkta başka bir transition geçirdiyse no-op
        cas_result = await db.kbs_reports.update_one(
            {
                "_kind": QUEUE_KIND,
                "tenant_id": tenant_id,
                "id": job_id,
                "status": "in_progress",
                "worker_id": data.worker_id,
            },
            {"$set": update},
        )
        if cas_result.modified_count == 0:
            raise HTTPException(
                409,
                "İş aralıkta değişti, fail uygulanamadı (lease expired olabilir)",
            )
        job = await db.kbs_reports.find_one(
            {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
            {"_id": 0},
        )

    return {
        "job": job,
        "will_retry": will_retry,
        "next_retry_at": next_retry_at,
    }
