"""
Wire Failure Tracking Router
Kanal yoneticisi hata takip sistemi.
ARI push hatalari, sync hatalari, DLQ kayitlarini takip eder.

Tur 23 (May 2026) — kullanici geri bildirimi sonrasi 7-madde duzeltme:
  1) Trend chart'a DLQ + CP gunluk breakdown eklendi.
  2) Mesaj fallback: Exely 'error_message' ALANI okunur, 'sync_type'
     placeholder'i yerine "<sync_type>: bilinmeyen hata" yazilir.
  3) Health threshold dinamik: sadece UNRESOLVED (recon/DLQ/CP) hatalar
     'critical' tetikler; sadece total >0 ise 'warning'. Backround pull
     retry spike'lari artik 30g'de 55 fail iken 'kritik' gostermiyor.
  4) /providers endpoint: dinamik kaynak listesi (kind + provider name).
  5) /recent: aggregate $unionWith ile tek roundtrip — N+4 fetch kaldirildi.
  6) ?nocache=1 query'si tum cached endpoint'lerde "Yenile"yi gercek
     bypass'a cevirir (cache_manager.cached pop('_nocache') destekliyor).
  7) Resolved durumu: ARI/Exely/CP icin gercek 'resolved' / 'resolved_at'
     alanlari okunur, DLQ icin retried_at kontrolu yapilir (hardcoded
     False kaldirildi).
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from cache_manager import cached
from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/wire-failures", tags=["Wire Failure Tracking"])


# ────────────────────────────────────────────────────────────────────────
# Sabit kind katalogu (frontend dinamik liste icin /providers'tan ceker
# ama burada da default sirayi tutariz — bos tenant'ta bile gorunsunler).
# ────────────────────────────────────────────────────────────────────────
_KIND_LABELS = {
    "all": "Tümü",
    "ari": "ARI",
    "exely": "Exely",
    "dlq": "DLQ",
    "control_plane": "Control Plane",
}


# Mongo $or fragment'i — _doc_resolved'in NEGATIF dual'i.
# Bir dokuman "unresolved" sayilir EGER:
#   resolved != True
#   AND resolved_at yok/null
#   AND retried_at / retry_succeeded_at yok/null
#   AND status NOT IN (resolved/completed/succeeded/success)
# Summary count_documents sorgulari bu filtreyi kullanir → /recent'in
# _doc_resolved mantigiyla birebir eslesir (review item 7 fix).
_RESOLVED_STATUSES = ("resolved", "completed", "succeeded", "success")
_UNRESOLVED_MATCH: dict = {
    "$and": [
        {"$or": [{"resolved": {"$ne": True}}, {"resolved": {"$exists": False}}]},
        {"$or": [{"resolved_at": {"$in": [None, ""]}}, {"resolved_at": {"$exists": False}}]},
        {"$or": [{"retried_at": {"$in": [None, ""]}}, {"retried_at": {"$exists": False}}]},
        {
            "$or": [
                {"retry_succeeded_at": {"$in": [None, ""]}},
                {"retry_succeeded_at": {"$exists": False}},
            ]
        },
        # Status case-insensitive: _doc_resolved (str.lower()) ile parite
        {
            "$expr": {
                "$not": {
                    "$in": [
                        {"$toLower": {"$ifNull": ["$status", ""]}},
                        list(_RESOLVED_STATUSES),
                    ]
                }
            }
        },
    ],
}


def _doc_resolved(doc: dict) -> bool:
    """Defensive resolved-state okuyucu: resolved (bool) | resolved_at | retried_at."""
    if doc.get("resolved") is True:
        return True
    if doc.get("resolved_at"):
        return True
    # DLQ retry callback'i bunu yaziyor (controlplane/retry_engine.py)
    if doc.get("retried_at") or doc.get("retry_succeeded_at"):
        return True
    status = (doc.get("status") or "").lower()
    if status in ("resolved", "completed", "succeeded", "success"):
        return True
    return False


def _exely_message(doc: dict) -> str:
    """Anlamli Exely sync hata mesaji (sync_type placeholder kullanmaz)."""
    for k in ("error_message", "error", "reason", "message"):
        v = doc.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            inner = v.get("message") or v.get("error") or v.get("detail")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    sync_type = doc.get("sync_type") or "sync"
    return f"{sync_type}: bilinmeyen Exely sync hatasi"


def _ari_message(doc: dict) -> str:
    for k in ("reason", "error", "error_message", "message"):
        v = doc.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Bilinmeyen ARI hatasi"


def _dlq_message(doc: dict) -> str:
    for k in ("error", "error_message", "last_error", "reason"):
        v = doc.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    payload_type = doc.get("payload_type") or doc.get("event_type") or "outbox"
    return f"{payload_type}: bilinmeyen DLQ hatasi"


def _cp_message(doc: dict) -> str:
    for k in ("message", "error", "error_message", "reason"):
        v = doc.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    component = doc.get("component") or "control_plane"
    return f"{component}: bilinmeyen control-plane hatasi"


def _classify_health(*, unresolved_critical: int, total: int) -> str:
    """
    Dinamik saglik durumu (sert <10/>=10 esigi yerine unresolved-bazli):
      - unresolved_critical >= 5  → critical
      - unresolved_critical >= 1  → warning
      - total > 0                  → warning  (transient/auto-healing)
      - aksi                       → healthy
    """
    if unresolved_critical >= 5:
        return "critical"
    if unresolved_critical >= 1:
        return "warning"
    if total > 0:
        return "warning"
    return "healthy"


@router.get("/summary")
@cached(ttl=60, key_prefix="wire_failures_summary")
async def get_failure_summary(
    days: int = Query(default=7, ge=1, le=90),
    _nocache: bool = Query(False, alias="nocache"),  # noqa: ARG001 — cached() pop ediyor
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get wire failure summary across all providers."""
    tenant_id = current_user.tenant_id
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    # ARI hard fail log — UNRESOLVED ayrimi
    ari_fails = await db.ari_hard_fail_log.count_documents(
        {
            "tenant_id": tenant_id,
            "timestamp": {"$gte": cutoff},
        }
    )
    ari_unresolved = await db.ari_hard_fail_log.count_documents(
        {
            "tenant_id": tenant_id,
            "timestamp": {"$gte": cutoff},
            **_UNRESOLVED_MATCH,
        }
    )

    # Exely sync failures
    exely_fails = await db.exely_sync_logs.count_documents(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["failed", "error"]},
            "timestamp": {"$gte": cutoff},
        }
    )

    # Connector outbox failures (DLQ) — daima unresolved (failed/dead_letter)
    dlq_count = await db.connector_outbox.count_documents(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["failed", "dead_letter"]},
        }
    )

    # CP failures — UNRESOLVED ayrimi (resolved=True olanlar saglikli)
    cp_fails = await db.cp_failures.count_documents(
        {
            "tenant_id": tenant_id,
            "timestamp": {"$gte": cutoff},
        }
    )
    cp_unresolved = await db.cp_failures.count_documents(
        {
            "tenant_id": tenant_id,
            "timestamp": {"$gte": cutoff},
            **_UNRESOLVED_MATCH,
        }
    )

    # Reconciliation issues (her zaman unresolved sayar)
    recon_issues = await db.cm_reconciliation_issues.count_documents(
        {
            "tenant_id": tenant_id,
            "status": {"$ne": "resolved"},
        }
    )

    # Observability errors — TENANT-SCOPED
    obs_errors = await db.observability_errors.count_documents(
        {
            "tenant_id": tenant_id,
            "timestamp": {"$gte": cutoff},
        }
    )

    total = ari_fails + exely_fails + dlq_count + cp_fails + obs_errors

    # UNRESOLVED CRITICAL: kullanici dikkati gerektiren acik sorunlar
    unresolved_critical = recon_issues + dlq_count + cp_unresolved + ari_unresolved

    return {
        "period_days": days,
        "total_failures": total,
        "unresolved_critical": unresolved_critical,
        "breakdown": {
            "ari_hard_fails": ari_fails,
            "exely_sync_fails": exely_fails,
            "dlq_items": dlq_count,
            "control_plane_fails": cp_fails,
            "reconciliation_issues": recon_issues,
            "observability_errors": obs_errors,
        },
        "unresolved_breakdown": {
            "ari_hard_fails": ari_unresolved,
            "dlq_items": dlq_count,
            "control_plane_fails": cp_unresolved,
            "reconciliation_issues": recon_issues,
        },
        "health_status": _classify_health(
            unresolved_critical=unresolved_critical,
            total=total,
        ),
        "health_basis": (f"{unresolved_critical} acik sorun (recon+DLQ+CP+ARI), {total} toplam olay (son {days} gun)"),
    }


@router.get("/providers")
@cached(ttl=300, key_prefix="wire_failures_providers")
async def get_providers(
    _nocache: bool = Query(False, alias="nocache"),  # noqa: ARG001
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Dinamik filter listesi: sabit kind'lar + DB'de gercekten gozlemlenen
    provider isimleri (hotelrunner, booking_com, ...). Yeni connector
    eklendiginde frontend kodu degismeden chip listede belirir.
    """
    tenant_id = current_user.tenant_id

    # Distinct provider names (her koleksiyondan)
    providers: set[str] = set()
    try:
        for col, field in (
            ("ari_hard_fail_log", "provider"),
            ("connector_outbox", "provider"),
            ("cp_failures", "component"),
        ):
            vals = await db[col].distinct(field, {"tenant_id": tenant_id})
            for v in vals:
                if isinstance(v, str) and v.strip():
                    providers.add(v.strip().lower())
    except Exception as e:  # pragma: no cover
        logger.warning("wire_failures.providers distinct error: %s", e)

    items = [{"value": k, "label": v, "kind": True} for k, v in _KIND_LABELS.items()]
    for p in sorted(providers):
        items.append({"value": p, "label": p.replace("_", " ").title(), "kind": False})
    return {"providers": items}


@router.get("/recent")
async def get_recent_failures(
    limit: int = Query(default=50, ge=1, le=200),
    provider: str = Query(default="all"),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """
    Son hatalar — TEK aggregate roundtrip ($unionWith).

    'provider' parametresi:
      - "all"           → tum kindler
      - "ari"|"exely"|"dlq"|"control_plane" → sadece o kind
      - <provider_name> → tum kindlerde 'provider' alani esleyenler
                           (orn. "hotelrunner", "booking_com")
    """
    tenant_id = current_user.tenant_id
    p = (provider or "all").strip().lower()
    is_kind = p in _KIND_LABELS

    # Hangi kind'lar dahil?
    include = {
        "ari": (p in ("all", "ari")) or not is_kind,
        "exely": (p in ("all", "exely")) or not is_kind,
        "dlq": (p in ("all", "dlq")) or not is_kind,
        "cp": (p in ("all", "control_plane")) or not is_kind,
    }
    # Eger kind degil (raw provider name), exely sabit "exely" provider'ina
    # esitse Exely de dahil olsun.
    if not is_kind:
        include["exely"] = p == "exely"

    failures: list[dict] = []

    # ────── Tek aggregate: ari_hard_fail_log + $unionWith (exely/dlq/cp) ──────
    # Pipeline: her kaynagi uniform doc'a $project, sonra dis $sort+$limit
    # MongoDB Atlas 5.0+ destekler; bos tenant'ta de hizli (count yok, find limit).
    base_match = {"tenant_id": tenant_id}

    pipeline_root: list[dict] = []
    sources_used: list[tuple[str, dict]] = []  # (collection, project_stage)

    if include["ari"]:
        sources_used.append(
            (
                "ari_hard_fail_log",
                {
                    "$project": {
                        "_id": 0,
                        "id": {"$ifNull": ["$id", ""]},
                        "type": {"$literal": "ari_hard_fail"},
                        "provider": {"$ifNull": ["$provider", "unknown"]},
                        "raw_reason": {"$ifNull": ["$reason", ""]},
                        "raw_error": {"$ifNull": ["$error", ""]},
                        "raw_error_message": {"$ifNull": ["$error_message", ""]},
                        "raw_message": {"$ifNull": ["$message", ""]},
                        "room_type": {"$ifNull": ["$room_type_code", ""]},
                        "timestamp": {"$ifNull": ["$timestamp", ""]},
                        "severity": {"$literal": "high"},
                        "resolved_flag": {"$ifNull": ["$resolved", False]},
                        "resolved_at": {"$ifNull": ["$resolved_at", None]},
                        "status": {"$ifNull": ["$status", ""]},
                        "retried_at": {"$ifNull": ["$retried_at", None]},
                        "retry_succeeded_at": {"$ifNull": ["$retry_succeeded_at", None]},
                    },
                },
            )
        )
    if include["exely"]:
        exely_match = {**base_match, "status": {"$in": ["failed", "error"]}}
        if not is_kind and p != "exely":
            # raw provider but not exely → skip exely source effectively
            pass
        else:
            sources_used.append(
                (
                    "exely_sync_logs",
                    {
                        "$project": {
                            "_id": 0,
                            "id": {"$ifNull": ["$id", ""]},
                            "type": {"$literal": "exely_sync_fail"},
                            "provider": {"$literal": "exely"},
                            "raw_reason": {"$ifNull": ["$reason", ""]},
                            "raw_error": {"$ifNull": ["$error", ""]},
                            "raw_error_message": {"$ifNull": ["$error_message", ""]},
                            "raw_message": {"$ifNull": ["$message", ""]},
                            "room_type": {"$literal": ""},
                            "timestamp": {"$ifNull": ["$timestamp", ""]},
                            "severity": {"$literal": "medium"},
                            "resolved_flag": {"$ifNull": ["$resolved", False]},
                            "resolved_at": {"$ifNull": ["$resolved_at", None]},
                            "status": {"$ifNull": ["$status", ""]},
                            "retried_at": {"$ifNull": ["$retried_at", None]},
                            "retry_succeeded_at": {"$ifNull": ["$retry_succeeded_at", None]},
                            "sync_type": {"$ifNull": ["$sync_type", ""]},
                        },
                    },
                    exely_match,
                )
            )
    if include["dlq"]:
        sources_used.append(
            (
                "connector_outbox",
                {
                    "$project": {
                        "_id": 0,
                        "id": {"$ifNull": ["$id", ""]},
                        "type": {"$literal": "dlq_item"},
                        "provider": {"$ifNull": ["$provider", "unknown"]},
                        "raw_reason": {"$ifNull": ["$reason", ""]},
                        "raw_error": {"$ifNull": ["$error", ""]},
                        "raw_error_message": {"$ifNull": ["$error_message", ""]},
                        "raw_message": {"$ifNull": ["$last_error", ""]},
                        "payload_type": {"$ifNull": ["$payload_type", ""]},
                        "room_type": {"$ifNull": ["$room_type_code", ""]},
                        "timestamp": {"$ifNull": ["$created_at", ""]},
                        "severity": {"$literal": "high"},
                        "resolved_flag": {"$literal": False},
                        "resolved_at": {"$ifNull": ["$resolved_at", None]},
                        "retried_at": {"$ifNull": ["$retried_at", None]},
                        "retry_succeeded_at": {"$ifNull": ["$retry_succeeded_at", None]},
                        "status": {"$ifNull": ["$status", ""]},
                    },
                },
                {**base_match, "status": {"$in": ["failed", "dead_letter"]}},
            )
        )
    if include["cp"]:
        sources_used.append(
            (
                "cp_failures",
                {
                    "$project": {
                        "_id": 0,
                        "id": {"$ifNull": ["$id", ""]},
                        "type": {"$literal": "cp_failure"},
                        "provider": {"$ifNull": ["$component", "control_plane"]},
                        "raw_reason": {"$ifNull": ["$reason", ""]},
                        "raw_error": {"$ifNull": ["$error", ""]},
                        "raw_error_message": {"$ifNull": ["$error_message", ""]},
                        "raw_message": {"$ifNull": ["$message", ""]},
                        "room_type": {"$literal": ""},
                        "timestamp": {"$ifNull": ["$timestamp", ""]},
                        "severity": {"$ifNull": ["$severity", "medium"]},
                        "resolved_flag": {"$ifNull": ["$resolved", False]},
                        "resolved_at": {"$ifNull": ["$resolved_at", None]},
                        "retried_at": {"$ifNull": ["$retried_at", None]},
                        "retry_succeeded_at": {"$ifNull": ["$retry_succeeded_at", None]},
                        "status": {"$ifNull": ["$status", ""]},
                    },
                },
            )
        )

    if not sources_used:
        return {"failures": [], "total": 0}

    # Ilk kaynak root
    root_col, *root_rest = sources_used[0]
    root_proj = root_rest[0]
    root_match = root_rest[1] if len(root_rest) > 1 else base_match
    pipeline_root = [{"$match": root_match}, root_proj]

    # Diger kaynaklari $unionWith ile ekle
    for src in sources_used[1:]:
        col_name = src[0]
        proj = src[1]
        match = src[2] if len(src) > 2 else base_match
        pipeline_root.append(
            {
                "$unionWith": {
                    "coll": col_name,
                    "pipeline": [{"$match": match}, proj],
                },
            }
        )

    # Raw provider name filtrelemesi (kind disindaki uzerinde)
    if not is_kind:
        # provider field icindeki esitlik (case-insensitive)
        pipeline_root.append(
            {
                "$match": {
                    "$expr": {"$eq": [{"$toLower": "$provider"}, p]},
                },
            }
        )

    pipeline_root.append({"$sort": {"timestamp": -1}})
    pipeline_root.append({"$limit": limit})

    try:
        docs = await db[root_col].aggregate(pipeline_root).to_list(limit)
    except Exception as e:
        logger.warning("wire_failures.recent aggregate fallback: %s", e)
        docs = []

    for d in docs:
        kind = d.get("type", "")
        if kind == "ari_hard_fail":
            msg = _ari_message(
                {
                    "reason": d.get("raw_reason"),
                    "error": d.get("raw_error"),
                    "error_message": d.get("raw_error_message"),
                    "message": d.get("raw_message"),
                }
            )
        elif kind == "exely_sync_fail":
            msg = _exely_message(
                {
                    "error_message": d.get("raw_error_message"),
                    "error": d.get("raw_error"),
                    "reason": d.get("raw_reason"),
                    "message": d.get("raw_message"),
                    "sync_type": d.get("sync_type"),
                }
            )
        elif kind == "dlq_item":
            msg = _dlq_message(
                {
                    "error": d.get("raw_error"),
                    "error_message": d.get("raw_error_message"),
                    "last_error": d.get("raw_message"),
                    "reason": d.get("raw_reason"),
                    "payload_type": d.get("payload_type"),
                }
            )
        else:  # cp_failure
            msg = _cp_message(
                {
                    "message": d.get("raw_message"),
                    "error": d.get("raw_error"),
                    "error_message": d.get("raw_error_message"),
                    "reason": d.get("raw_reason"),
                    "component": d.get("provider"),
                }
            )

        failures.append(
            {
                "id": d.get("id", ""),
                "type": kind,
                "provider": d.get("provider", "unknown"),
                "message": msg,
                "room_type": d.get("room_type", ""),
                "timestamp": d.get("timestamp", ""),
                "severity": d.get("severity", "medium"),
                "resolved": _doc_resolved(
                    {
                        "resolved": d.get("resolved_flag"),
                        "resolved_at": d.get("resolved_at"),
                        "retried_at": d.get("retried_at"),
                        "retry_succeeded_at": d.get("retry_succeeded_at"),
                        "status": d.get("status"),
                    }
                ),
            }
        )

    return {"failures": failures, "total": len(failures)}


@router.get("/trend")
@cached(ttl=120, key_prefix="wire_failures_trend")
async def get_failure_trend(
    days: int = Query(default=30, ge=1, le=90),
    _nocache: bool = Query(False, alias="nocache"),  # noqa: ARG001
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get daily failure trend for charts (ARI + Exely + DLQ + CP)."""
    tenant_id = current_user.tenant_id
    cutoff_dt = datetime.now(UTC) - timedelta(days=days)
    cutoff = cutoff_dt.isoformat()

    # Initialize empty buckets (her gun var, 0'lar dahil)
    daily: dict[str, dict] = {}
    for i in range(days):
        day = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")
        daily[day] = {
            "date": day,
            "ari_fails": 0,
            "sync_fails": 0,
            "dlq": 0,
            "cp": 0,
            "total": 0,
        }

    async def _bump(col: str, ts_field: str, bucket_key: str, extra_match: dict | None = None):
        match = {"tenant_id": tenant_id, ts_field: {"$gte": cutoff}}
        if extra_match:
            match.update(extra_match)
        try:
            cursor = db[col].find(match, {"_id": 0, ts_field: 1}).limit(20000)
            async for doc in cursor:
                ts = doc.get(ts_field, "") or ""
                day = ts[:10] if len(ts) >= 10 else ""
                if day in daily:
                    daily[day][bucket_key] += 1
                    daily[day]["total"] += 1
        except Exception as e:  # pragma: no cover
            logger.warning("trend bump %s.%s error: %s", col, bucket_key, e)

    # ARI
    await _bump("ari_hard_fail_log", "timestamp", "ari_fails")
    # Exely
    await _bump("exely_sync_logs", "timestamp", "sync_fails", {"status": {"$in": ["failed", "error"]}})
    # DLQ (created_at)
    await _bump("connector_outbox", "created_at", "dlq", {"status": {"$in": ["failed", "dead_letter"]}})
    # CP
    await _bump("cp_failures", "timestamp", "cp")

    trend = sorted(daily.values(), key=lambda x: x["date"])
    return {"trend": trend, "period_days": days}
