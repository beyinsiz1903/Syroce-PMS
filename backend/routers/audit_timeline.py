"""
Audit Timeline — API Foundations
Provides timeline-friendly audit log queries, entity audit trails,
and summary endpoints for the upcoming Audit Timeline Panel.
"""
import csv
import io
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from common.context import OperationContext
from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["Audit Timeline"])


def _ts_to_iso(ts) -> str:
    """Audit Timeline P1 fix — pilot DB karışık timestamp tipleri içeriyor.

    Eski yazılı kayıtlar `timestamp`'ı ISO string olarak tutuyor; daha
    yeni kayıtlar Mongo'ya `datetime` (BSON Date) olarak yazıyor. Bu
    yardımcı her iki tipi de güvenli ISO string'e çevirir; dict cursor
    ($lt sözlüğü gibi sızıntılar) veya None için boş string döner.
    """
    if ts is None:
        return ""
    if isinstance(ts, str):
        return ts
    if isinstance(ts, datetime):
        try:
            return ts.isoformat()
        except Exception:
            return str(ts)
    # Sayı / dict / başka tipler — defansif fallback (logger kayıt almaz)
    return str(ts)


@router.get("/timeline")
async def get_audit_timeline(
    start_date: str | None = None,
    end_date: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    severity: str | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """
    Timeline-friendly audit log query.
    Supports cursor-based pagination and comprehensive filtering.

    Audit Timeline P1 fix (2026-05-13):
      - Karışık timestamp tipleri (str + datetime) crash etmesin diye
        `_ts_to_iso` ile normalize edilir; `_group_by_time` artık
        `len(datetime)` çağırmaz.
      - Beklenmeyen aggregation/serialization hatası 500 yerine 200 +
        boş `events` listesi + `degraded=true` döner. Audit timeline
        UI'sı boş düşmek yerine "şu an kayıt yok" gösterebilsin.
      - `cursor` ile birlikte tarih filtresi gelirse `cursor` üst
        sınırı baskın; tarih filtreleri `$gte`/`$lte` korunur (eski kod
        sözlüğü tamamen overwrite ediyordu).
    """
    ctx = OperationContext.from_user(current_user)
    query: dict = {"tenant_id": ctx.tenant_id}
    ts_filter: dict = {}

    if start_date:
        ts_filter["$gte"] = start_date
    if end_date:
        ts_filter["$lte"] = end_date
    if cursor:
        ts_filter["$lt"] = cursor
    if ts_filter:
        query["timestamp"] = ts_filter

    if actor_id:
        query["actor_id"] = actor_id
    if action:
        from security.query_safety import safe_search_term
        if (_a := safe_search_term(action)):
            query["operation_name"] = {"$regex": _a, "$options": "i"}
    if severity:
        query["severity"] = severity
    if entity_type:
        query["target_type"] = entity_type

    try:
        # Exclude the heavy before/after entity-diff snapshots from this flat
        # timeline. after_snapshot mirrors a service `result.data` dict that
        # under mutation-heavy load may hold non-JSON-native Mongo types
        # (Decimal128, encrypted-field bytes, naive datetimes) — those serialize
        # OUTSIDE this try/except (at response encoding) and surface as a 500.
        # They are also PII-heavy; the per-entity audit-trail endpoints serve
        # them on demand. Dropping them here keeps the timeline 200-stable.
        projection = {"_id": 0, "before_snapshot": 0, "after_snapshot": 0}
        logs = await db.audit_logs.find(query, projection).sort(
            "timestamp", -1
        ).limit(limit + 1).to_list(limit + 1)

        has_more = len(logs) > limit
        if has_more:
            logs = logs[:limit]

        # Tüm kayıtların timestamp'ini ISO string'e normalize et —
        # JSON response + frontend timeline UI string bekliyor.
        for _log in logs:
            if "timestamp" in _log:
                _log["timestamp"] = _ts_to_iso(_log["timestamp"])

        next_cursor = logs[-1]["timestamp"] if has_more and logs else None
        grouped = _group_by_time(logs)

        return {
            "events": logs,
            "count": len(logs),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "grouped": grouped,
        }
    except Exception:
        # PII koruması: query/exception detayı log'a düşürülmez,
        # sadece traceback Sentry'ye gider. Kullanıcıya boş yanıt.
        logger.exception("audit_timeline query failed (degraded fallback)")
        return {
            "events": [],
            "count": 0,
            "has_more": False,
            "next_cursor": None,
            "grouped": [],
            "degraded": True,
        }


@router.get("/timeline/{entity_type}/{entity_id}")
async def get_entity_audit_trail(
    entity_type: str,
    entity_id: str,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
):
    """
    Get full audit trail for a specific entity (booking, guest, room, folio, etc.)
    with before/after snapshot diffs.
    """
    ctx = OperationContext.from_user(current_user)
    query = {
        "tenant_id": ctx.tenant_id,
        "target_type": entity_type,
        "target_id": entity_id,
    }

    logs = await db.audit_logs.find(query, {"_id": 0}).sort(
        "timestamp", -1
    ).limit(limit).to_list(limit)

    # Compute diffs between snapshots
    trail = []
    for log in logs:
        entry = {
            "id": log.get("id"),
            "operation": log.get("operation_name"),
            "actor_id": log.get("actor_id"),
            "actor_role": log.get("actor_role"),
            "result_status": log.get("result_status"),
            "severity": log.get("severity"),
            "timestamp": log.get("timestamp"),
            "duration_ms": log.get("duration_ms"),
            "before_snapshot": log.get("before_snapshot"),
            "after_snapshot": log.get("after_snapshot"),
            "override_reason": log.get("override_reason"),
        }
        # Compute changed fields if both snapshots exist
        before = log.get("before_snapshot") or {}
        after = log.get("after_snapshot") or {}
        if before and after and isinstance(before, dict) and isinstance(after, dict):
            changed = {}
            all_keys = set(list(before.keys()) + list(after.keys()))
            for k in all_keys:
                if before.get(k) != after.get(k):
                    changed[k] = {"before": before.get(k), "after": after.get(k)}
            entry["changed_fields"] = changed
        trail.append(entry)

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "trail": trail,
        "count": len(trail),
    }


@router.get("/summary")
async def get_audit_summary(
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
):
    """
    Aggregated audit summary for dashboard cards.
    Counts by severity, operation, and actor.
    """
    ctx = OperationContext.from_user(current_user)

    period_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}
    hours = period_map.get(period, 24)
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    pipeline = [
        {"$match": {"tenant_id": ctx.tenant_id, "timestamp": {"$gte": since}}},
        {"$facet": {
            "by_severity": [
                {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
            ],
            "by_operation": [
                {"$group": {"_id": "$operation_name", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_actor": [
                {"$group": {"_id": "$actor_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_result": [
                {"$group": {"_id": "$result_status", "count": {"$sum": 1}}},
            ],
            "total": [{"$count": "count"}],
        }},
    ]

    result = await db.audit_logs.aggregate(pipeline).to_list(1)
    data = result[0] if result else {}

    total = data.get("total", [{}])[0].get("count", 0) if data.get("total") else 0

    return {
        "period": period,
        "since": since,
        "total_events": total,
        "by_severity": {d["_id"]: d["count"] for d in data.get("by_severity", []) if d["_id"]},
        "by_operation": {d["_id"]: d["count"] for d in data.get("by_operation", []) if d["_id"]},
        "by_actor": {d["_id"]: d["count"] for d in data.get("by_actor", []) if d["_id"]},
        "by_result": {d["_id"]: d["count"] for d in data.get("by_result", []) if d["_id"]},
    }


@router.get("/urgent-message-report")
async def get_urgent_message_report(
    start_date: str | None = None,
    end_date: str | None = None,
    sender_id: str | None = None,
    recipient_department: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    # Task #26 — yönetici sınırı. Acil mesaj denetim kayıtları
    # `message_preview` içerebileceği için sıradan personelin erişimine
    # kapalı. SUPERVISOR/ADMIN/SUPER_ADMIN dışındaki roller 403 alır.
    _perm=Depends(require_op("view_audit_log")),
):
    """
    Task #26 — Acil Mesaj Raporu.

    `audit_logs` koleksiyonundaki `send_urgent_internal_message`
    olaylarını yöneticilere özet + liste şeklinde sunar.

    Filtreler (hepsi opsiyonel):
      - start_date / end_date  : ISO timestamp string (`>=` / `<=`).
      - sender_id              : `actor_id` tam eşleşmesi.
      - recipient_department   : `after_snapshot.to_department` tam eşleşmesi.

    Yanıt:
      {
        "events":  [...],            # paginated liste (timestamp DESC)
        "total":   N,
        "summary": {
          "by_sender":               [{sender_id, sender_name, sender_department, count}],
          "by_recipient_department": [{department, count}],
          "by_hour_of_day":          [{hour, count}],   # "00".."23"
        },
        "filters": {start_date, end_date, sender_id, recipient_department},
      }

    Multi-tenant: yalnızca çağıranın tenant'ına ait kayıtlar döner.
    """
    ctx = OperationContext.from_user(current_user)
    match_stage: dict = {
        "tenant_id": ctx.tenant_id,
        "operation_name": "send_urgent_internal_message",
    }
    if start_date:
        match_stage.setdefault("timestamp", {})["$gte"] = start_date
    if end_date:
        match_stage.setdefault("timestamp", {})["$lte"] = end_date
    if sender_id:
        match_stage["actor_id"] = sender_id
    if recipient_department:
        match_stage["after_snapshot.to_department"] = recipient_department

    pipeline = [
        {"$match": match_stage},
        {"$facet": {
            "events": [
                {"$sort": {"timestamp": -1}},
                {"$skip": int(offset)},
                {"$limit": int(limit)},
                {"$project": {
                    "_id": 0,
                    "id": 1,
                    "timestamp": 1,
                    "actor_id": 1,
                    "actor_role": 1,
                    "after_snapshot": 1,
                }},
            ],
            "by_sender": [
                {"$group": {
                    "_id": {
                        "sender_id": "$actor_id",
                        "sender_name": "$after_snapshot.from_user_name",
                        "sender_department": "$after_snapshot.from_department",
                    },
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_recipient_department": [
                {"$group": {
                    "_id": "$after_snapshot.to_department",
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
            ],
            "by_hour_of_day": [
                # ISO timestamp `YYYY-MM-DDTHH:MM:SS...` — 11. karakterden
                # 2 karakter saat dilimini (HH) verir. Tüm saat kayıtları
                # UTC olduğu için bucket'lar tutarlı.
                {"$group": {
                    "_id": {"$substr": ["$timestamp", 11, 2]},
                    "count": {"$sum": 1},
                }},
                {"$sort": {"_id": 1}},
            ],
            "total": [{"$count": "count"}],
        }},
    ]

    try:
        result = await db.audit_logs.aggregate(pipeline).to_list(1)
    except Exception:  # pragma: no cover - defensive
        logger.exception("urgent-message-report aggregation failed")
        result = []

    data = result[0] if result else {}
    total = (data.get("total") or [{}])[0].get("count", 0) if data.get("total") else 0

    by_sender = [
        {
            "sender_id": (d.get("_id") or {}).get("sender_id"),
            "sender_name": (d.get("_id") or {}).get("sender_name"),
            "sender_department": (d.get("_id") or {}).get("sender_department"),
            "count": d.get("count", 0),
        }
        for d in (data.get("by_sender") or [])
        if (d.get("_id") or {}).get("sender_id")
    ]

    by_recipient_department = [
        {"department": d.get("_id"), "count": d.get("count", 0)}
        for d in (data.get("by_recipient_department") or [])
        if d.get("_id")
    ]

    by_hour_of_day = [
        {"hour": d.get("_id"), "count": d.get("count", 0)}
        for d in (data.get("by_hour_of_day") or [])
        if d.get("_id")
    ]

    return {
        "events": data.get("events", []),
        "total": total,
        "summary": {
            "by_sender": by_sender,
            "by_recipient_department": by_recipient_department,
            "by_hour_of_day": by_hour_of_day,
        },
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "sender_id": sender_id,
            "recipient_department": recipient_department,
        },
        "pagination": {"limit": limit, "offset": offset},
    }


_ALLOWED_RECALL_PRIORITIES = ("urgent", "normal")


@router.get("/recalled-messages")
async def get_recalled_messages_report(
    start_date: str | None = None,
    end_date: str | None = None,
    sender_id: str | None = None,
    priority: str | None = None,
    include_denied: bool = False,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    # Task #35 — yönetici sınırı. Geri alma denetim kayıtları
    # `message_preview` içerebileceği için sıradan personelin erişimine
    # kapalı. SUPERVISOR/ADMIN/SUPER_ADMIN dışındaki roller 403 alır.
    _perm=Depends(require_op("view_audit_log")),
):
    """
    Task #35 — Geri Alınan Mesajlar Raporu.

    `audit_logs` koleksiyonundaki `recall_internal_message` olaylarını
    yöneticilere özet + liste şeklinde sunar.

    Filtreler (hepsi opsiyonel):
      - start_date / end_date  : ISO timestamp string (`>=` / `<=`).
      - sender_id              : `actor_id` tam eşleşmesi (mesajı geri
                                 alan kullanıcı = orijinal gönderen).
      - priority               : "urgent" | "normal" — orijinal mesajın
                                 önceliği (`before_snapshot.priority`).

    Yanıt:
      {
        "events":  [...],            # paginated liste (timestamp DESC)
        "total":   N,
        "summary": {
          "by_sender":      [{sender_id, sender_name, sender_department, count}],
          "by_priority":    [{priority, count}],
          "by_hour_of_day": [{hour, count}],   # "00".."23"
        },
        "filters": {start_date, end_date, sender_id, priority},
        "pagination": {limit, offset},
      }

    Multi-tenant: yalnızca çağıranın tenant'ına ait kayıtlar döner.

    Geçersiz `priority` değeri için 422 atılır — aksi halde admin filtre
    uygulandı sanıp filtresiz sonuçları görür ve yanlış değerlendirir.
    """
    # Strict whitelist: invalid → 422 (FastAPI HTTPException). Boş
    # string ya da None ise filtre uygulanmaz.
    if priority not in (None, "") and priority not in _ALLOWED_RECALL_PRIORITIES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=(
                f"Geçersiz priority değeri: {priority!r}. "
                f"İzin verilen değerler: {list(_ALLOWED_RECALL_PRIORITIES)}."
            ),
        )

    ctx = OperationContext.from_user(current_user)
    # Task #36: when `include_denied=true`, the report also returns rows for
    # window-expired recall attempts (action ``recall_internal_message_denied``)
    # so admins can spot users who repeatedly bump into the 5-minute limit.
    # Default stays narrow (successful recalls only) for backward compatibility.
    operation_filter = (
        {"$in": ["recall_internal_message", "recall_internal_message_denied"]}
        if include_denied
        else "recall_internal_message"
    )
    match_stage: dict = {
        "tenant_id": ctx.tenant_id,
        "operation_name": operation_filter,
    }
    if start_date:
        match_stage.setdefault("timestamp", {})["$gte"] = start_date
    if end_date:
        match_stage.setdefault("timestamp", {})["$lte"] = end_date
    if sender_id:
        match_stage["actor_id"] = sender_id
    if priority:
        match_stage["before_snapshot.priority"] = priority

    pipeline = [
        {"$match": match_stage},
        {"$facet": {
            "events": [
                {"$sort": {"timestamp": -1}},
                {"$skip": int(offset)},
                {"$limit": int(limit)},
                {"$project": {
                    "_id": 0,
                    "id": 1,
                    "timestamp": 1,
                    "actor_id": 1,
                    "actor_role": 1,
                    "operation_name": 1,  # Task #36: distinguishes successful recall vs denial
                    "before_snapshot": 1,
                    "after_snapshot": 1,
                }},
            ],
            "by_sender": [
                {"$group": {
                    "_id": {
                        "sender_id": "$actor_id",
                        "sender_name": "$before_snapshot.from_user_name",
                        "sender_department": "$before_snapshot.from_department",
                    },
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_priority": [
                {"$group": {
                    "_id": "$before_snapshot.priority",
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
            ],
            "by_hour_of_day": [
                {"$group": {
                    "_id": {"$substr": ["$timestamp", 11, 2]},
                    "count": {"$sum": 1},
                }},
                {"$sort": {"_id": 1}},
            ],
            "total": [{"$count": "count"}],
        }},
    ]

    try:
        result = await db.audit_logs.aggregate(pipeline).to_list(1)
    except Exception:  # pragma: no cover - defensive
        logger.exception("recalled-messages report aggregation failed")
        result = []

    data = result[0] if result else {}
    total = (data.get("total") or [{}])[0].get("count", 0) if data.get("total") else 0

    by_sender = [
        {
            "sender_id": (d.get("_id") or {}).get("sender_id"),
            "sender_name": (d.get("_id") or {}).get("sender_name"),
            "sender_department": (d.get("_id") or {}).get("sender_department"),
            "count": d.get("count", 0),
        }
        for d in (data.get("by_sender") or [])
        if (d.get("_id") or {}).get("sender_id")
    ]

    by_priority = [
        {"priority": d.get("_id") or "unknown", "count": d.get("count", 0)}
        for d in (data.get("by_priority") or [])
    ]

    by_hour_of_day = [
        {"hour": d.get("_id"), "count": d.get("count", 0)}
        for d in (data.get("by_hour_of_day") or [])
        if d.get("_id")
    ]

    return {
        "events": data.get("events", []),
        "total": total,
        "summary": {
            "by_sender": by_sender,
            "by_priority": by_priority,
            "by_hour_of_day": by_hour_of_day,
        },
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "sender_id": sender_id,
            "priority": priority,
        },
        "pagination": {"limit": limit, "offset": offset},
    }


def _build_id_photo_view_match(
    tenant_id: str,
    start_date: str | None,
    end_date: str | None,
    actor_id: str | None,
    booking_id: str | None,
    checkin_id: str | None,
) -> dict:
    """
    Task #83 — KVKK kimlik fotoğrafı raporu için ortak `$match` üreteci.

    `view_online_checkin_id_photo` audit eylemi resepsiyon her kimlik
    fotoğrafı görüntülediğinde yazılıyor (bkz. `checkin_router.py`).
    Burada match aşaması hem JSON listeleme hem CSV dışa aktarımı için
    aynı şekilde kurulur, böylece iki uç noktanın filtre semantiği
    birbirinden ayrışmaz.

    - `target_type` = "online_checkin"  → audit kaydındaki entity_type.
    - `target_id`                       → checkin_id filtresi.
    - `after_snapshot.booking_id`       → booking filtresi.
    - `actor_id`                        → personel (tam eşleşme).
    """
    match: dict = {
        "tenant_id": tenant_id,
        "operation_name": "view_online_checkin_id_photo",
    }
    if start_date:
        match.setdefault("timestamp", {})["$gte"] = start_date
    if end_date:
        match.setdefault("timestamp", {})["$lte"] = end_date
    if actor_id:
        match["actor_id"] = actor_id
    if booking_id:
        match["after_snapshot.booking_id"] = booking_id
    if checkin_id:
        match["target_id"] = checkin_id
    return match


def _validate_id_photo_view_date_range(
    start_date: str | None, end_date: str | None
) -> None:
    """`start_date > end_date` durumu admin'in farkında olmadan filtre
    uyguladığı bir tuzaktır — sessizce boş sonuç döner ve "kayıt yok"
    izlenimi uyandırır. Bunu 422 ile reddederek erken hata fırlatırız.

    Karşılaştırma string üzerinden yapılır çünkü ISO 8601 timestamp'ler
    leksikografik olarak da sıralı.
    """
    if start_date and end_date and start_date > end_date:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=(
                f"Tarih aralığı geçersiz: start_date ({start_date!r}) "
                f"end_date ({end_date!r}) değerinden sonra olamaz."
            ),
        )


@router.get("/id-photo-views")
async def get_id_photo_view_report(
    start_date: str | None = None,
    end_date: str | None = None,
    actor_id: str | None = None,
    booking_id: str | None = None,
    checkin_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    # Task #83 — yönetici sınırı. Kimlik fotoğrafı görüntüleme kayıtları
    # KVKK kapsamında kişisel veri olduğu için sıradan personelin
    # erişimine kapalı. SUPERVISOR/ADMIN/SUPER_ADMIN dışındaki roller
    # 403 alır.
    _perm=Depends(require_op("view_audit_log")),
):
    """
    Task #83 — KVKK Kimlik Fotoğrafı Görüntüleme Raporu.

    `audit_logs` koleksiyonundaki `view_online_checkin_id_photo`
    eylemlerini yöneticilere özet + sayfalı liste şeklinde sunar.

    Filtreler (hepsi opsiyonel):
      - start_date / end_date  : ISO timestamp string (`>=` / `<=`).
      - actor_id               : `actor_id` tam eşleşmesi (görüntüleyen
                                 personel).
      - booking_id             : `after_snapshot.booking_id` tam eşleşmesi.
      - checkin_id             : `target_id` tam eşleşmesi.

    Yanıt:
      {
        "events":  [...],            # paginated liste (timestamp DESC)
        "total":   N,
        "summary": {
          "by_actor":      [{actor_id, count}],
          "by_booking":    [{booking_id, count}],
          "by_hour_of_day":[{hour, count}],   # "00".."23"
        },
        "filters": {start_date, end_date, actor_id, booking_id, checkin_id},
        "pagination": {limit, offset},
      }

    Multi-tenant: yalnızca çağıranın tenant'ına ait kayıtlar döner.
    """
    _validate_id_photo_view_date_range(start_date, end_date)
    ctx = OperationContext.from_user(current_user)
    match_stage = _build_id_photo_view_match(
        tenant_id=ctx.tenant_id,
        start_date=start_date,
        end_date=end_date,
        actor_id=actor_id,
        booking_id=booking_id,
        checkin_id=checkin_id,
    )

    pipeline = [
        {"$match": match_stage},
        {"$facet": {
            "events": [
                {"$sort": {"timestamp": -1}},
                {"$skip": int(offset)},
                {"$limit": int(limit)},
                {"$project": {
                    "_id": 0,
                    "id": 1,
                    "timestamp": 1,
                    "actor_id": 1,
                    "actor_role": 1,
                    "target_id": 1,
                    "after_snapshot": 1,
                }},
            ],
            "by_actor": [
                {"$group": {"_id": "$actor_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_booking": [
                {"$group": {
                    "_id": "$after_snapshot.booking_id",
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
                {"$limit": 10},
            ],
            "by_hour_of_day": [
                # ISO timestamp `YYYY-MM-DDTHH:MM:SS...` — 11. karakterden
                # 2 karakter saat dilimini (HH) verir. Tüm saat kayıtları
                # UTC olduğu için bucket'lar tutarlı.
                {"$group": {
                    "_id": {"$substr": ["$timestamp", 11, 2]},
                    "count": {"$sum": 1},
                }},
                {"$sort": {"_id": 1}},
            ],
            "total": [{"$count": "count"}],
        }},
    ]

    try:
        result = await db.audit_logs.aggregate(pipeline).to_list(1)
    except Exception:  # pragma: no cover - defensive
        logger.exception("id-photo-view-report aggregation failed")
        result = []

    data = result[0] if result else {}
    total = (data.get("total") or [{}])[0].get("count", 0) if data.get("total") else 0

    by_actor = [
        {"actor_id": d.get("_id"), "count": d.get("count", 0)}
        for d in (data.get("by_actor") or [])
        if d.get("_id")
    ]

    by_booking = [
        {"booking_id": d.get("_id"), "count": d.get("count", 0)}
        for d in (data.get("by_booking") or [])
        if d.get("_id")
    ]

    by_hour_of_day = [
        {"hour": d.get("_id"), "count": d.get("count", 0)}
        for d in (data.get("by_hour_of_day") or [])
        if d.get("_id")
    ]

    return {
        "events": data.get("events", []),
        "total": total,
        "summary": {
            "by_actor": by_actor,
            "by_booking": by_booking,
            "by_hour_of_day": by_hour_of_day,
        },
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "actor_id": actor_id,
            "booking_id": booking_id,
            "checkin_id": checkin_id,
        },
        "pagination": {"limit": limit, "offset": offset},
    }


# CSV dışa aktarımı için üst sınır. KVKK denetimlerinde uzun aralıklı
# raporlar istenebileceği için JSON ucundan (500) daha geniş tutulur,
# fakat bellek koruması için sınırlandırılır.
_ID_PHOTO_VIEW_CSV_MAX_ROWS = 10000


@router.get("/id-photo-views.csv")
async def export_id_photo_view_report_csv(
    start_date: str | None = None,
    end_date: str | None = None,
    actor_id: str | None = None,
    booking_id: str | None = None,
    checkin_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_audit_log")),
):
    """
    Task #83 — KVKK Kimlik Fotoğrafı Görüntüleme Raporu (CSV dışa aktar).

    Aynı filtre semantiği ile JSON ucundan ayrı tutulur; tek bir akış
    içinde CSV üretir. Her satır KVKK denetimi için yeterli bilgiyi
    içerir: zaman, kullanıcı, booking, check-in, photo_id ve fotoğrafın
    SHA-256 imzası (entegrite kanıtı).

    Filtre semantiği `/id-photo-views` ile birebir aynıdır. Sayfalama
    yoktur; bunun yerine güvenlik için sabit bir üst sınır vardır
    (`_ID_PHOTO_VIEW_CSV_MAX_ROWS`).
    """
    _validate_id_photo_view_date_range(start_date, end_date)
    ctx = OperationContext.from_user(current_user)
    match_stage = _build_id_photo_view_match(
        tenant_id=ctx.tenant_id,
        start_date=start_date,
        end_date=end_date,
        actor_id=actor_id,
        booking_id=booking_id,
        checkin_id=checkin_id,
    )

    cursor = db.audit_logs.find(match_stage, {"_id": 0}).sort(
        "timestamp", -1
    ).limit(_ID_PHOTO_VIEW_CSV_MAX_ROWS)
    rows = await cursor.to_list(_ID_PHOTO_VIEW_CSV_MAX_ROWS)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp",
        "actor_id",
        "actor_role",
        "checkin_id",
        "booking_id",
        "photo_id",
        "sha256",
        "content_type",
    ])
    for row in rows:
        snap = row.get("after_snapshot") or {}
        writer.writerow([
            row.get("timestamp") or "",
            row.get("actor_id") or "",
            row.get("actor_role") or "",
            row.get("target_id") or "",
            snap.get("booking_id") or "",
            snap.get("photo_id") or "",
            snap.get("sha256") or "",
            snap.get("content_type") or "",
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # Excel'in TR karakterler için BOM beklemesi
    filename = f"kvkk-id-photo-views-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store, max-age=0",
        },
    )


def _group_by_time(logs: list) -> list:
    """Group audit events by hour for timeline visualization.

    Pilot DB'de `timestamp` hem ISO string hem `datetime` olarak
    karşımıza çıkabiliyor (eski/yeni yazıcılar). `_ts_to_iso` ikisini
    de string'e çevirip `len()` TypeError'unu engeller.
    """
    buckets = {}
    for log in logs:
        ts = _ts_to_iso(log.get("timestamp"))
        hour_key = ts[:13] if len(ts) >= 13 else ts[:10]
        if hour_key not in buckets:
            buckets[hour_key] = {"time_bucket": hour_key, "count": 0, "events": []}
        buckets[hour_key]["count"] += 1
        buckets[hour_key]["events"].append({
            "id": log.get("id"),
            "operation": log.get("operation_name"),
            "severity": log.get("severity"),
            "target_type": log.get("target_type"),
        })
    return list(buckets.values())
