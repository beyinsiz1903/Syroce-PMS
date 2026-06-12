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
  GET  /api/kbs/queue/stream       — SSE: yeni iş bildirimlerini push olarak al
  POST /api/kbs/queue/{id}/claim   — atomik lease (worker iş alır)
  POST /api/kbs/queue/{id}/complete — başarı + KBS referans no
  POST /api/kbs/queue/{id}/fail    — hata + exp. backoff retry / dead
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.database import db
from core.kbs_payload_validation import validate_kbs_payload
from core.security import get_current_user
from core.tenant_db import tenant_context
from infra.kbs_queue_pubsub import kbs_queue_pubsub
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v98 DW
from shared_kernel.idempotency import (
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
)

logger = logging.getLogger("routers.kbs")

router = APIRouter(prefix="/api/kbs", tags=["KBS"])


def _kbs_test_mode() -> bool:
    """KBS_TEST_MODE=1 → reference 'TEST-' ile başlamayan complete'ler reddedilir,
    booking üzerine kbs_test=true bayrağı yazılır."""
    return os.environ.get("KBS_TEST_MODE", "0") == "1"


async def _raise_kbs_alert(
    tenant_id: str,
    *,
    kind: str,
    job: dict,
    error: str = "",
) -> None:
    """Dead-letter / kritik durum alarmı üret. db.kbs_alerts'e kayıt ekler.

    GM dashboard ileride bu collection'ı izleyecek; şimdilik kayıt + log.
    Hata fırlatmaz (alarm sistemi ana akışı etkilememeli).
    """
    try:
        await db.kbs_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "kind": kind,  # "dead_letter" | "missing_data" | "max_attempts"
            "job_id": job.get("id"),
            "booking_id": job.get("booking_id"),
            "guest_name": (job.get("payload") or {}).get("guest_name", ""),
            "room_number": (job.get("payload") or {}).get("room_number", ""),
            "action": job.get("action"),
            "attempts": job.get("attempts"),
            "last_error": error or job.get("last_error"),
            "worker_id": job.get("worker_id"),
            "created_at": _now_iso(),
            "acknowledged": False,
        })
        logger.warning(
            "KBS alert raised: tenant=%s kind=%s booking=%s err=%s",
            tenant_id, kind, job.get("booking_id"), error,
        )
    except Exception as e:
        logger.warning("KBS alert insert failed: %s", e)


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
            from security.encrypted_lookup import decrypt_guest_doc
            async for g in db.guests.find(
                {"tenant_id": tenant_id, "id": {"$in": guest_ids}},
                {"_id": 0, "id": 1, "nationality": 1, "id_number": 1,
                 "passport_number": 1, "birth_date": 1, "gender": 1,
                 "address": 1, "father_name": 1, "mother_name": 1,
                 "birth_place": 1},
            ):
                guest_map[g["id"]] = decrypt_guest_doc(g)

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
        from security.encrypted_lookup import decrypt_guest_doc
        guest = decrypt_guest_doc(await db.guests.find_one(
            {"tenant_id": tenant_id, "id": booking["guest_id"]},
            {
                "_id": 0, "id": 1, "nationality": 1, "id_number": 1,
                "passport_number": 1, "birth_date": 1, "gender": 1,
                "address": 1, "father_name": 1, "mother_name": 1,
                "birth_place": 1,
            },
        )) or {}

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
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),  # KBS perm with legacy reports
):
    """Bildirimi kuyruğa ekle. Aynı (booking_id, action) için pending/in_progress
    iş varsa mevcut işi döner (idempotent), force=true ise yeni iş açar.

    Header `Idempotency-Key` (opsiyonel) verilirse aynı anahtarla gelen
    çağrılar aynı yanıtı döner (ağ retry koruması).

    Payload validation: TC misafir → id_number 11 hane; yabancı → passport.
    `force=true` ise validation bypass edilir (geç düzeltme senaryoları için).
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    idem_key = get_idempotency_key(request)
    idem_lock_id: str | None = None
    if idem_key:
        claim = await claim_idempotency(
            db, tenant_id=tenant_id,
            scope=f"kbs:queue:{data.booking_id}:{data.action}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(409, "Aynı Idempotency-Key işleniyor, bekleyin")
        idem_lock_id = claim["lock_id"]

    try:
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
                    response = {"job": existing, "created": False}
                    if idem_lock_id:
                        await complete_idempotency(
                            db, lock_id=idem_lock_id, response_body=response,
                        )
                    return response

            booking, guest, snapshot = await _build_payload_snapshot(
                tenant_id, data.booking_id
            )

            # Madde 7: enqueue zamanında payload tamlığı kontrolü.
            # force=true → bypass (eksik bilgiyle bilinçli kuyruğa atma).
            if not data.force:
                ok, missing = validate_kbs_payload(snapshot)
                if not ok:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "error": "kbs_payload_incomplete",
                            "missing_fields": missing,
                            "message": (
                                "KBS bildirimi için zorunlu alanlar eksik: "
                                + ", ".join(missing)
                            ),
                        },
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
                # Atomik tekillik kilidi (partial unique index ile birlikte):
                # open jobs (pending/in_progress) için set; closed (done/dead)
                # geçişlerinde unset edilir → aynı booking+action için aynı anda
                # en fazla 1 açık iş garanti.
                "_open_lock": f"{tenant_id}:{data.booking_id}:{data.action}",
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
                "source": "manual",
                "created_at": _iso(now),
                "updated_at": _iso(now),
                "claimed_at": None,
                "completed_at": None,
                "failed_at": None,
            }
            try:
                await db.kbs_reports.insert_one(job)
            except Exception as ins_err:
                # Race: eşzamanlı başka enqueue açık iş yarattı → idempotent dön
                if (
                    "duplicate key" in str(ins_err).lower()
                    or "E11000" in str(ins_err)
                ):
                    existing2 = await db.kbs_reports.find_one(
                        {
                            "_kind": QUEUE_KIND,
                            "tenant_id": tenant_id,
                            "_open_lock": f"{tenant_id}:{data.booking_id}:{data.action}",
                        },
                        {"_id": 0},
                    )
                    # Edge case: rakip transaction _open_lock'u unset etmiş olabilir
                    # (çok hızlı complete/dead). Ek olarak (booking, action, open) ile ara.
                    if not existing2:
                        existing2 = await db.kbs_reports.find_one(
                            {
                                "_kind": QUEUE_KIND,
                                "tenant_id": tenant_id,
                                "booking_id": data.booking_id,
                                "action": data.action,
                                "status": {"$in": ["pending", "in_progress"]},
                            },
                            {"_id": 0},
                        )
                    if existing2:
                        response = {"job": existing2, "created": False}
                        if idem_lock_id:
                            await complete_idempotency(
                                db, lock_id=idem_lock_id, response_body=response,
                            )
                        return response
                raise
            job.pop("_id", None)
        response = {"job": job, "created": True}
        if idem_lock_id:
            await complete_idempotency(
                db, lock_id=idem_lock_id, response_body=response,
            )
        # SSE fan-out: tell every connected agent (this worker AND
        # other workers via Redis) that a new job is ready to claim.
        # Best-effort — a publish failure must never poison the
        # successful enqueue response.
        try:
            await kbs_queue_pubsub.publish(
                "job.available",
                tenant_id,
                job_id=job["id"],
                booking_id=job["booking_id"],
                action=job["action"],
            )
        except Exception as _pub_err:  # pragma: no cover — defensive
            logger.warning(f"KBS SSE publish (enqueue) error: {_pub_err}")
        return response
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as e:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(e))
        raise


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
    wanted_statuses: list[str] = []
    if status:
        wanted_statuses = [s.strip() for s in status.split(",") if s.strip()]
        bad = [s for s in wanted_statuses if s not in QUEUE_STATUSES]
        if bad:
            raise HTTPException(400, f"Geçersiz status: {bad}")
    if booking_id:
        q["booking_id"] = booking_id
    if date_from or date_to:
        q["created_at"] = {}
        if date_from:
            q["created_at"]["$gte"] = date_from
        if date_to:
            q["created_at"]["$lte"] = date_to + "T23:59:59"

    # Madde 3: stuck-worker recovery — pending isteyen ajan, lease süresi
    # dolmuş in_progress işleri de görsün (claim endpoint zaten kabul ediyor).
    #
    # Madde 5 (Faz 5 / SSE coherence): "pending" listing must hide
    # retry-deferred jobs whose ``next_retry_at`` is still in the
    # future — otherwise an agent reconnecting and reconciling via
    # ``GET /queue?status=pending`` would call ``POST /claim`` on
    # them, get HTTP 409 (claim CAS already filters
    # ``next_retry_at <= now``), and tight-loop. We mirror the claim
    # endpoint's filter here so list <-> claim stay coherent and the
    # SSE contract's promise ("retry not visible until back-off
    # elapses") is actually true.
    now_iso_view = _iso(_now())
    if wanted_statuses == ["pending"]:
        pending_claimable = {
            "status": "pending",
            "$or": [
                {"next_retry_at": None},
                {"next_retry_at": {"$exists": False}},
                {"next_retry_at": {"$lte": now_iso_view}},
            ],
        }
        in_progress_stuck = {
            "status": "in_progress",
            "leased_until": {"$lt": now_iso_view},
        }
        q["$or"] = [pending_claimable, in_progress_stuck]
    elif wanted_statuses:
        q["status"] = {"$in": wanted_statuses}

    with tenant_context(tenant_id):
        jobs = await db.kbs_reports.find(q, {"_id": 0}).sort(
            "created_at", -1
        ).to_list(limit)

        # Tüm statüler için sayım (status bar)
        pipeline = [
            {"$match": {"_kind": QUEUE_KIND, "tenant_id": tenant_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        stats = dict.fromkeys(QUEUE_STATUSES, 0)
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
                {
                    "$set": {
                        "status": "dead",
                        "failed_at": _iso(now),
                        "updated_at": _iso(now),
                        "last_error": "max_attempts exceeded on claim",
                    },
                    # Closed state: _open_lock'u kaldır → yeni iş açılabilsin
                    "$unset": {"_open_lock": ""},
                },
            )
            # Madde 6: dead-letter alarm
            await _raise_kbs_alert(
                tenant_id, kind="dead_letter", job=job,
                error="max_attempts exceeded on claim",
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
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Worker başarıyla bildirdi: in_progress → done.

    Sadece claim'i alan worker tamamlayabilir (worker_id eşleşmeli).
    Side-effect: bookings.kbs_reported = true; legacy uyumluluk için
    kbs_reports'a tek-misafir özet kaydı yazılır.

    Header `Idempotency-Key` ile aynı çağrı retry edilebilir (replay).
    `KBS_TEST_MODE=1` env iken kbs_reference "TEST-" prefix'i şart;
    booking üzerinde `kbs_test=true` işareti tutulur.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    # Madde 8: test mode — TEST- prefix zorunlu, prod referans kaçışını engeller.
    test_mode = _kbs_test_mode()
    is_test_ref = data.kbs_reference.startswith("TEST-")
    if test_mode and not is_test_ref:
        raise HTTPException(
            422,
            "KBS_TEST_MODE açık iken kbs_reference 'TEST-' ile başlamalı",
        )

    idem_key = get_idempotency_key(request)
    idem_lock_id: str | None = None
    if idem_key:
        claim = await claim_idempotency(
            db, tenant_id=tenant_id,
            scope=f"kbs:complete:{job_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(409, "Aynı Idempotency-Key işleniyor, bekleyin")
        idem_lock_id = claim["lock_id"]

    try:
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
                {
                    "$set": {
                        "status": "done",
                        "kbs_reference": data.kbs_reference,
                        "completed_at": _iso(now),
                        "updated_at": _iso(now),
                        "kbs_test": is_test_ref,
                        "notes": (job.get("notes") or "") + (
                            ("\n" + data.notes) if data.notes else ""
                        ),
                    },
                    # Closed state: _open_lock'u kaldır → aynı booking+action için
                    # tekrar enqueue açılabilsin (örn. checkout sonrası farklı action).
                    "$unset": {"_open_lock": ""},
                },
            )
            if cas_result.modified_count == 0:
                # İş aralıkta değişti (lease expired + başka worker claim etti vs.)
                raise HTTPException(
                    409,
                    "İş aralıkta değişti, complete uygulanamadı (lease expired olabilir)",
                )
            # Booking üzerine bayrak
            booking_update = {
                "kbs_reported": True,
                "kbs_reported_at": _iso(now),
                "kbs_reference": data.kbs_reference,
            }
            if is_test_ref:
                booking_update["kbs_test"] = True
            await db.bookings.update_one(
                {"tenant_id": tenant_id, "id": job["booking_id"]},
                {"$set": booking_update},
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
                "kbs_test": is_test_ref,
                "created_at": _iso(now),
            })

            job = await db.kbs_reports.find_one(
                {"_kind": QUEUE_KIND, "tenant_id": tenant_id, "id": job_id},
                {"_id": 0},
            )
        response = {"job": job, "report_id": report_id, "test_mode": test_mode}
        if idem_lock_id:
            await complete_idempotency(
                db, lock_id=idem_lock_id, response_body=response,
            )
        # SSE fan-out: notify other connected agents that this job is
        # closed so a stale UI can stop showing it. Best-effort.
        try:
            await kbs_queue_pubsub.publish(
                "job.completed",
                tenant_id,
                job_id=job_id,
                booking_id=job.get("booking_id", ""),
                action=job.get("action", ""),
            )
        except Exception as _pub_err:  # pragma: no cover — defensive
            logger.warning(f"KBS SSE publish (complete) error: {_pub_err}")
        return response
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as e:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(e))
        raise


# --- 5) Fail (with retry / dead) ----------------------------

class KBSQueueFail(BaseModel):
    worker_id: str = Field(..., min_length=1)
    error: str = Field(..., min_length=1, max_length=2000)
    retry: bool = True


@router.post("/queue/{job_id}/fail")
async def kbs_queue_fail(
    job_id: str,
    data: KBSQueueFail,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Worker hata bildirdi.

    retry=True ve attempts < max_attempts → status=pending,
      next_retry_at = now + exp.backoff(attempts), worker/lease temizlenir.
    Aksi halde → status=dead, failed_at set edilir + dead-letter alarmı.

    Header `Idempotency-Key` ile aynı çağrı retry edilebilir (replay).
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    idem_key = get_idempotency_key(request)
    idem_lock_id: str | None = None
    if idem_key:
        claim = await claim_idempotency(
            db, tenant_id=tenant_id,
            scope=f"kbs:fail:{job_id}",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(409, "Aynı Idempotency-Key işleniyor, bekleyin")
        idem_lock_id = claim["lock_id"]

    try:
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
            update_op: dict = {"$set": update}
            # Closed state (dead): _open_lock'u kaldır → yeni iş açılabilsin
            if not will_retry:
                update_op["$unset"] = {"_open_lock": ""}
            cas_result = await db.kbs_reports.update_one(
                {
                    "_kind": QUEUE_KIND,
                    "tenant_id": tenant_id,
                    "id": job_id,
                    "status": "in_progress",
                    "worker_id": data.worker_id,
                },
                update_op,
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

        # Madde 6: dead-letter alarmı (transaction sonrası)
        if not will_retry and job and job.get("status") == "dead":
            await _raise_kbs_alert(
                tenant_id, kind="dead_letter", job=job, error=data.error,
            )

        response = {
            "job": job,
            "will_retry": will_retry,
            "next_retry_at": next_retry_at,
        }
        if idem_lock_id:
            await complete_idempotency(
                db, lock_id=idem_lock_id, response_body=response,
            )
        # SSE fan-out:
        #   will_retry=True  → ``job.retry_scheduled`` *now*. The job
        #     IS NOT immediately claimable: ``GET /queue?status=pending``
        #     and ``POST /claim`` filter on ``next_retry_at <= now``,
        #     so emitting ``job.available`` here would just spam 409s.
        #     The agent uses ``next_retry_at`` to schedule a delayed
        #     reconcile/claim instead of reacting instantly.
        #   will_retry=False → ``job.failed`` (terminal) so UIs can
        #     remove it from the active list and surface the error.
        try:
            if will_retry:
                await kbs_queue_pubsub.publish(
                    "job.retry_scheduled",
                    tenant_id,
                    job_id=job_id,
                    booking_id=(job or {}).get("booking_id", ""),
                    action=(job or {}).get("action", ""),
                    extra={
                        "next_retry_at": next_retry_at,
                        "attempts": (job or {}).get("attempts", 0),
                        "max_attempts": (job or {}).get(
                            "max_attempts", DEFAULT_MAX_ATTEMPTS
                        ),
                    },
                )
            else:
                await kbs_queue_pubsub.publish(
                    "job.failed",
                    tenant_id,
                    job_id=job_id,
                    booking_id=(job or {}).get("booking_id", ""),
                    action=(job or {}).get("action", ""),
                )
        except Exception as _pub_err:  # pragma: no cover — defensive
            logger.warning(f"KBS SSE publish (fail) error: {_pub_err}")
        return response
    except HTTPException:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id)
        raise
    except Exception as e:
        if idem_lock_id:
            await release_idempotency(db, lock_id=idem_lock_id, error=str(e))
        raise


# ============================================================
# Faz 3.5 — Server-Sent Events (push notification stream)
# ============================================================

# Heartbeat cadence — must be shorter than common idle-timeout values
# of intermediary proxies / load balancers (typically 60 s on cloud
# providers). 25 s gives a comfortable margin and also acts as the
# probe that detects half-closed sockets so the server-side asyncio
# task can clean up its subscriber slot.
_SSE_HEARTBEAT_SECONDS = 25.0

# Maximum stream lifetime. Forces a clean reconnect every ~6 hours
# even on perfectly healthy connections so long-running agents
# refresh JWTs and re-establish a known-good state.
_SSE_MAX_STREAM_SECONDS = 6 * 60 * 60


@router.get("/queue/stream")
async def kbs_queue_stream(
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Server-Sent Events stream of KBS queue lifecycle events for the
    caller's tenant. Designed for the desktop KBS agent app to replace
    polling ``GET /queue`` with push-based notifications.

    Auth: Bearer JWT (same as every other ``/api/kbs/*`` endpoint).
    The agent reuses the operator's session token; no separate API key
    is required. ``tenant_id`` is derived from the token, not from a
    query parameter — so the stream is automatically scoped to one
    hotel and cannot be tricked into receiving another tenant's
    events.

    Events:
      - ``ready``               sent once on connect with ``{"instance":...}``.
      - ``job.available``       a fresh enqueue — claim immediately.
      - ``job.retry_scheduled`` a previously-failed job will be
                                claimable at ``next_retry_at`` (in
                                payload). Schedule a delayed claim;
                                do NOT race to claim now (server
                                blocks until the back-off elapses).
      - ``job.completed``       another worker reported success.
      - ``job.failed``          job moved to terminal ``dead`` state.
      - ``heartbeat``           every 25 s, ``data: {"ts":"..."}``. The
                                client may use this as a liveness probe;
                                absence of a heartbeat for >60 s is a
                                strong signal the connection is broken
                                and the client should reconnect.

    Reconnect: SSE is a one-way HTTP stream over a long-lived response.
    On disconnect (network blip, reverse proxy timeout, the 6 h
    server-side rotation) the client reconnects via standard
    EventSource semantics; missed events should be reconciled with a
    single ``GET /queue?status=pending`` call after each reconnect
    (this endpoint is intentionally fire-and-forget — no on-disk
    backlog or Last-Event-ID replay).

    Multi-worker correctness: events published on any worker reach
    every connected agent through the Redis pub/sub bridge in
    ``infra.kbs_queue_pubsub``.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    # Register *before* the generator starts so we can't miss an event
    # that arrives between the HTTP handshake and the first ``await``.
    queue = await kbs_queue_pubsub.add_subscriber(tenant_id)
    started_at = datetime.now(UTC)

    async def event_generator():
        try:
            # Initial ``ready`` frame so the client knows the stream
            # is live (without waiting up to 25 s for the first
            # heartbeat). Includes the worker instance id for
            # operational debugging — it has no security value and
            # the same id is in the Redis pubsub envelope.
            metrics = kbs_queue_pubsub.get_metrics()
            ready_payload = {
                "instance": metrics.get("instance_id", ""),
                "ts": _iso(_now()),
                "heartbeat_seconds": _SSE_HEARTBEAT_SECONDS,
            }
            yield f"event: ready\ndata: {json.dumps(ready_payload)}\n\n"

            while True:
                # Disconnect / lifetime check.
                if await request.is_disconnected():
                    break
                if (datetime.now(UTC) - started_at).total_seconds() > _SSE_MAX_STREAM_SECONDS:
                    yield (
                        "event: server_rotate\n"
                        f"data: {{\"reason\": \"max_stream_age\"}}\n\n"
                    )
                    break

                # Wait for next event or heartbeat tick — whichever
                # comes first. ``wait_for`` cancels the queue.get
                # cleanly on timeout so we never leak tasks.
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=_SSE_HEARTBEAT_SECONDS,
                    )
                except TimeoutError:
                    yield (
                        f"event: heartbeat\n"
                        f"data: {json.dumps({'ts': _iso(_now())})}\n\n"
                    )
                    continue

                event_type = str(event.get("type") or "message")
                # Defense in depth: although the pubsub bridge is
                # already filtering by tenant_id, double-check here
                # so a future routing bug can't leak cross-tenant.
                if event.get("tenant_id") and event["tenant_id"] != tenant_id:
                    continue
                yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            # Client closed; FastAPI cancels the generator task. No
            # logging — happens on every legitimate disconnect.
            raise
        except Exception as e:
            logger.warning(f"KBS SSE generator error: {e}")
        finally:
            await kbs_queue_pubsub.remove_subscriber(tenant_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            # Disable any reverse-proxy buffering (nginx etc.) so
            # events flush immediately.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ============================================================
# Faz 4 — Alarm + setup-info (madde 6 + 9)
# ============================================================


@router.get("/alerts")
async def kbs_alerts_list(
    acknowledged: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """KBS alarmları (dead_letter, missing_data, max_attempts).

    GM dashboard'da kırmızı rozet için kullanılır. acknowledged=False
    sadece aksiyon alınmamışları döner.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    q: dict = {"tenant_id": tenant_id}
    if acknowledged is not None:
        q["acknowledged"] = acknowledged

    with tenant_context(tenant_id):
        alerts = await db.kbs_alerts.find(q, {"_id": 0}).sort(
            "created_at", -1
        ).to_list(limit)
        unack_count = await db.kbs_alerts.count_documents(
            {"tenant_id": tenant_id, "acknowledged": False},
        )

    # KBS otomatik gönderici kimlik bilgisi sistem geneli olduğu için
    # `send_unconfigured` config alarmı tenant_id="_system" ile yazılır.
    # Bunu yalnızca platform yöneticisi (super_admin) görür; tenant proxy
    # _system'i context'e çekemediğinden ayrı sistem-db sorgusuyla eklenir.
    from core.security import _is_super_admin
    if _is_super_admin(current_user):
        from core.tenant_db import get_system_db
        sys_db = get_system_db()
        sys_q: dict = {"tenant_id": "_system"}
        if acknowledged is not None:
            sys_q["acknowledged"] = acknowledged
        sys_alerts = await sys_db.kbs_alerts.find(sys_q, {"_id": 0}).sort(
            "created_at", -1
        ).to_list(limit)
        if sys_alerts:
            alerts = sorted(
                alerts + sys_alerts,
                key=lambda a: a.get("created_at") or "",
                reverse=True,
            )[:limit]
            unack_count += await sys_db.kbs_alerts.count_documents(
                {"tenant_id": "_system", "acknowledged": False},
            )

    return {"alerts": alerts, "total": len(alerts), "unack_count": unack_count}


@router.post("/alerts/{alert_id}/ack")
async def kbs_alert_ack(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Alarmı görüldü işaretle."""
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")
    with tenant_context(tenant_id):
        result = await db.kbs_alerts.update_one(
            {"tenant_id": tenant_id, "id": alert_id},
            {"$set": {
                "acknowledged": True,
                "acknowledged_by": current_user.email,
                "acknowledged_at": _now_iso(),
            }},
        )
    if result.matched_count == 0:
        raise HTTPException(404, "Alarm bulunamadı")
    return {"ok": True}


@router.get("/setup-info")
async def kbs_setup_info(current_user: User = Depends(get_current_user)):
    """KBS Agent kurulum bilgileri (Madde 9).

    Otele gönderilen ajan teknisyenine veya bot kullanıcı kurulum
    rehberi olarak gösterilen sabit bilgi paketi (tenant'a özel).
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(403, "Kullanıcının bir oteli (tenant_id) yok")

    return {
        "tenant_id": tenant_id,
        "api_base": "/api",
        "kbs_base": "/api/kbs",
        "auth_endpoint": "/api/auth/login",
        "auth_payload_format": {
            "hotel_id": "<otelin numerik ID'si, ör: 100001>",
            "username": "kbs-bot",
            "password": "<güçlü parola>",
            "_note": "username = user.username (e-posta DEĞİL). Legacy mod: sadece email+password.",
        },
        "recommended_bot_user": {
            "username_format": "kbs-bot",
            "email_format": "kbs-bot@<oteldomain>.com",
            "role": "frontdesk",
            "required_permissions": ["view_reports"],
            "rotation_policy": "90 gün",
            "creation_steps": [
                "1) Yönetim → Kullanıcılar → Yeni kullanıcı",
                "2) Kullanıcı adı: kbs-bot, E-posta: kbs-bot@<oteldomain>",
                "3) Rol: frontdesk (KBS bildirim izni içerir)",
                "4) Güçlü parola üret, ajan kurulum dosyasında sakla",
                "5) İlk login sonrası /api/kbs/me 200 dönmeli",
            ],
        },
        "endpoints": {
            "me": "GET /api/kbs/me",
            "queue_list": "GET /api/kbs/queue?status=pending",
            "queue_claim": "POST /api/kbs/queue/{id}/claim",
            "queue_complete": "POST /api/kbs/queue/{id}/complete",
            "queue_fail": "POST /api/kbs/queue/{id}/fail",
            "alerts": "GET /api/kbs/alerts?acknowledged=false",
        },
        "headers": {
            "Authorization": "Bearer <jwt_from_login>",
            "Idempotency-Key": "Önerilen (queue/complete/fail için)",
        },
        "test_mode": {
            "env_flag": "KBS_TEST_MODE=1 (PMS server tarafında set edilir)",
            "behavior": "complete'de kbs_reference 'TEST-' ile başlamalı",
            "note": "Sertifika gelmeden test için kullanılır",
        },
        "auto_enqueue": {
            "enabled": os.environ.get("KBS_AUTO_ENQUEUE", "1") != "0",
            "trigger": "atomik check-in/checkout sonrası otomatik kuyruğa alma",
            "disable_env": "KBS_AUTO_ENQUEUE=0",
        },
    }
