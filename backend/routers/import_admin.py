"""
DATA-001: Import Admin Router — Review Queue, Retry, Status
=============================================================
Admin/internal endpoints for managing OTA → PMS import pipeline.

Endpoints:
  - GET  /api/imports/status              → Import bridge health + metrics
  - GET  /api/imports/review-queue        → List review_required imports
  - GET  /api/imports/events              → List imports by status/provider
  - POST /api/imports/{id}/retry          → Retry a single import
  - POST /api/imports/{id}/approve-and-import → Approve and auto-import
  - POST /api/imports/{id}/dismiss        → Dismiss a review item
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from cache_manager import cached
from core.database import db
from core.helpers import require_super_admin_guard
from core.import_bridge_service import (
    COLL_IMPORTED,
    auto_import_reservation_to_pms,
)

logger = logging.getLogger("routers.import_admin")

# v69 Bug DF: import_admin auth gate'siz + cross-tenant. outbox_admin patern'i —
# router-level super_admin guard. HK kullanıcı/diğer roller tüm tenant'ların
# import status/review-queue/event'lerini görüyordu + retry/approve/dismiss yapabiliyordu.
_require_super_admin = require_super_admin_guard()

import_admin_router = APIRouter(
    prefix="/imports",
    tags=["import-admin"],
    dependencies=[Depends(_require_super_admin)],
)


class ImportStatusResponse(BaseModel):
    pending_auto_import: int
    processing: int
    imported: int
    review_required: int
    retry: int
    failed: int
    duplicate: int
    oldest_pending_seconds: float | None
    last_imported_at: str | None
    provider_failures: dict
    worker: dict


class ImportActionResponse(BaseModel):
    success: bool
    message: str
    import_id: str


# NOTE: Global admin/ops metric — counts across ALL tenants (no tenant_id filter
# in the queries below). Cache key intentionally resolves to 'global' namespace.
# noqa: cache-rbac — global ops admin endpoint (router-level admin guard)
@import_admin_router.get("/status", response_model=ImportStatusResponse)
@cached(ttl=60, key_prefix="imports_status_global")
async def import_status():
    """Get import bridge health and metrics."""
    now = datetime.now(UTC)
    coll = db[COLL_IMPORTED]

    pending = await coll.count_documents({"import_status": "pending_auto_import"})
    processing = await coll.count_documents({"import_status": "processing"})
    imported = await coll.count_documents({"import_status": "imported"})
    review = await coll.count_documents({"import_status": "review_required"})
    retry = await coll.count_documents({"import_status": "retry"})
    failed = await coll.count_documents({"import_status": "failed"})
    duplicate = await coll.count_documents({"import_status": "duplicate"})

    # Oldest pending
    oldest = await coll.find_one(
        {"import_status": {"$in": ["pending_auto_import", "retry"]}},
        {"_id": 0, "created_at": 1},
        sort=[("created_at", 1)],
    )
    oldest_seconds = None
    if oldest and oldest.get("created_at"):
        try:
            created = datetime.fromisoformat(oldest["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            oldest_seconds = round((now - created).total_seconds(), 1)
        except Exception:
            pass

    # Last imported timestamp
    last = await coll.find_one(
        {"import_status": "imported"},
        {"_id": 0, "imported_at": 1},
        sort=[("imported_at", -1)],
    )
    last_imported_at = last.get("imported_at") if last else None

    # Provider failure breakdown
    pipeline = [
        {"$match": {"import_status": {"$in": ["failed", "review_required"]}}},
        {"$group": {"_id": "$provider", "count": {"$sum": 1}}},
    ]
    provider_failures = {}
    async for doc in coll.aggregate(pipeline):
        provider_failures[doc["_id"] or "unknown"] = doc["count"]

    # Worker metrics
    try:
        from core.import_retry_worker import import_retry_worker
        worker_metrics = import_retry_worker.metrics
    except Exception:
        worker_metrics = {"running": False}

    return ImportStatusResponse(
        pending_auto_import=pending,
        processing=processing,
        imported=imported,
        review_required=review,
        retry=retry,
        failed=failed,
        duplicate=duplicate,
        oldest_pending_seconds=oldest_seconds,
        last_imported_at=last_imported_at,
        provider_failures=provider_failures,
        worker=worker_metrics,
    )


@import_admin_router.get("/review-queue")
async def list_review_queue(
    provider: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List imports requiring manual review."""
    query = {"import_status": "review_required"}
    if provider:
        query["provider"] = provider
    if tenant_id:
        query["tenant_id"] = tenant_id

    items = await db[COLL_IMPORTED].find(
        query, {"_id": 0},
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)

    total = await db[COLL_IMPORTED].count_documents(query)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@import_admin_router.get("/events")
async def list_import_events(
    status: str | None = Query(None, description="Filter by import_status"),
    provider: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List import events with optional filters."""
    query = {}
    if status:
        query["import_status"] = status
    if provider:
        query["provider"] = provider
    if tenant_id:
        query["tenant_id"] = tenant_id

    items = await db[COLL_IMPORTED].find(
        query, {"_id": 0},
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)

    total = await db[COLL_IMPORTED].count_documents(query)

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@import_admin_router.post("/{import_id}/retry", response_model=ImportActionResponse)
async def retry_import(import_id: str):
    """Retry a failed or review_required import."""
    now = datetime.now(UTC).isoformat()

    result = await db[COLL_IMPORTED].find_one_and_update(
        {
            "id": import_id,
            "import_status": {"$in": ["failed", "review_required", "retry"]},
        },
        {
            "$set": {
                "import_status": "pending_auto_import",
                "next_retry_at": None,
                "retry_count": 0,
                "review_reason": None,
                "last_error": None,
                "updated_at": now,
            },
        },
        projection={"_id": 0, "id": 1},
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Import {import_id} not found or not in retryable status",
        )

    logger.info("Import record requeued for retry: %s", import_id)
    return ImportActionResponse(
        success=True,
        message="Import requeued for automatic retry",
        import_id=import_id,
    )


@import_admin_router.post("/{import_id}/approve-and-import", response_model=ImportActionResponse)
async def approve_and_import(import_id: str):
    """Approve a review_required import and attempt auto-import."""
    now = datetime.now(UTC).isoformat()

    # Reset to pending so the import bridge can process it
    result = await db[COLL_IMPORTED].find_one_and_update(
        {
            "id": import_id,
            "import_status": {"$in": ["review_required", "failed"]},
        },
        {
            "$set": {
                "import_status": "pending_auto_import",
                "next_retry_at": None,
                "retry_count": 0,
                "review_reason": None,
                "last_error": None,
                "updated_at": now,
            },
        },
        projection={"_id": 0, "id": 1},
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Import {import_id} not found or not in review/failed status",
        )

    # Attempt immediate import
    success, message = await auto_import_reservation_to_pms(import_id)

    return ImportActionResponse(
        success=success,
        message=message,
        import_id=import_id,
    )


@import_admin_router.post("/{import_id}/dismiss", response_model=ImportActionResponse)
async def dismiss_import(import_id: str):
    """Dismiss a review item (won't be imported)."""
    now = datetime.now(UTC).isoformat()

    result = await db[COLL_IMPORTED].find_one_and_update(
        {
            "id": import_id,
            "import_status": {"$in": ["review_required", "failed", "pending_auto_import"]},
        },
        {
            "$set": {
                "import_status": "dismissed",
                "updated_at": now,
                "last_error": "Dismissed by admin",
            },
        },
        projection={"_id": 0, "id": 1},
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Import {import_id} not found or not in dismissable status",
        )

    logger.info("Import record dismissed: %s", import_id)
    return ImportActionResponse(
        success=True,
        message="Import dismissed",
        import_id=import_id,
    )
