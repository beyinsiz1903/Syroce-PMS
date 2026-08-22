"""Tenant-scoped Nilvera → Genel Muhasebe automation and review queue.

This module never calls Nilvera.  It only reacts to locally persisted invoice
snapshots/statuses and writes through the durable GL posting kernel.  New
tenants default to ``review`` so an accountant can verify the mapping before a
journal is posted; ``automatic`` is an explicit tenant setting.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from pymongo import ReturnDocument

from core.integrations.invoice_gl_bridge import (
    InvoiceGLBridgeError,
    post_incoming_invoice_to_gl,
    post_outgoing_invoice_to_gl,
    reverse_outgoing_invoice_gl,
)
from core.tenant_db import get_db_for_tenant

logger = logging.getLogger("core.integrations.nilvera_gl_automation")

NILVERA_GL_MODES = {"disabled", "review", "automatic"}

DEFAULT_NILVERA_GL_SETTINGS: dict = {
    "incoming_mode": "review",
    "outgoing_mode": "review",
    "incoming_purchase_account_code": "153",
    "incoming_vat_account_code": "191",
    "incoming_payable_account_code": "320",
    "incoming_other_tax_account_code": None,
    "incoming_deduction_account_code": None,
    "incoming_other_tax_accounts_by_code": {},
    "incoming_deduction_accounts_by_code": {},
    "outgoing_revenue_account_code": "600",
    "outgoing_receivable_account_code": "120",
    "outgoing_discount_account_code": "611",
    "outgoing_vat_account_code": "391",
    "outgoing_accommodation_tax_account_code": "360",
    "outgoing_vat_accounts_by_rate": {},
    "outgoing_accommodation_tax_accounts_by_rate": {},
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _queue_id(tenant_id: str, direction: str, invoice_id: str, operation: str = "post") -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"syroce:nilvera-gl:{tenant_id}:{operation}:{direction}:{invoice_id}",
        )
    )


def _public_settings(doc: dict | None) -> dict:
    settings = dict(DEFAULT_NILVERA_GL_SETTINGS)
    if doc:
        settings.update({key: value for key, value in doc.items() if key not in {"_id", "tenant_id"}})
    return settings


async def get_nilvera_gl_settings(tenant_id: str) -> dict:
    db = get_db_for_tenant(tenant_id)
    doc = await db.gl_nilvera_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return _public_settings(doc)


async def save_nilvera_gl_settings(tenant_id: str, payload: dict, *, actor: str) -> dict:
    incoming_mode = payload.get("incoming_mode")
    outgoing_mode = payload.get("outgoing_mode")
    if incoming_mode not in NILVERA_GL_MODES or outgoing_mode not in NILVERA_GL_MODES:
        raise InvoiceGLBridgeError("Nilvera GL mode must be disabled, review or automatic")

    clean = _public_settings(payload)
    for key, value in clean.items():
        if key.endswith("_account_code") and value is not None:
            normalized = str(value).strip()
            if not normalized or len(normalized) > 40:
                raise InvoiceGLBridgeError(f"Invalid account code: {key}")
            clean[key] = normalized
        elif key.endswith("_accounts_by_rate") or key.endswith("_accounts_by_code"):
            if not isinstance(value, dict):
                raise InvoiceGLBridgeError(f"Invalid rate mapping: {key}")
            clean[key] = {
                str(rate).strip(): str(account).strip()
                for rate, account in value.items()
                if str(rate).strip() and str(account).strip()
            }

    now = _now_iso()
    db = get_db_for_tenant(tenant_id)
    await db.gl_nilvera_settings.update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {**clean, "updated_at": now, "updated_by": actor},
            "$setOnInsert": {"tenant_id": tenant_id, "created_at": now},
        },
        upsert=True,
    )
    return await get_nilvera_gl_settings(tenant_id)


async def enqueue_nilvera_gl_candidate(
    tenant_id: str,
    direction: str,
    invoice_id: str,
    *,
    source_status: str,
    actor: str = "system",
) -> dict | None:
    """Create/reuse a durable review item and auto-post only when opted in."""
    if direction not in {"incoming", "outgoing"}:
        raise InvoiceGLBridgeError("Invalid Nilvera GL direction")
    settings = await get_nilvera_gl_settings(tenant_id)
    mode = settings[f"{direction}_mode"]
    if mode == "disabled":
        return None

    db = get_db_for_tenant(tenant_id)
    now = _now_iso()
    item_id = _queue_id(tenant_id, direction, invoice_id)
    await db.gl_nilvera_queue.update_one(
        {"tenant_id": tenant_id, "id": item_id},
        {
            "$setOnInsert": {
                "id": item_id,
                "tenant_id": tenant_id,
                "operation": "post",
                "direction": direction,
                "invoice_id": invoice_id,
                "status": "pending",
                "attempt_count": 0,
                "created_at": now,
                "created_by": actor,
            },
            "$set": {"mode": mode, "source_status": source_status, "last_seen_at": now},
        },
        upsert=True,
    )
    item = await db.gl_nilvera_queue.find_one(
        {"tenant_id": tenant_id, "id": item_id},
        {"_id": 0},
    )
    if mode == "automatic" and item and item.get("status") != "posted":
        return await process_nilvera_gl_queue_item(tenant_id, item_id, actor=actor)
    return item


async def process_nilvera_gl_queue_item(tenant_id: str, item_id: str, *, actor: str) -> dict:
    db = get_db_for_tenant(tenant_id)
    existing = await db.gl_nilvera_queue.find_one(
        {"tenant_id": tenant_id, "id": item_id},
        {"_id": 0},
    )
    if not existing:
        raise InvoiceGLBridgeError("Nilvera GL queue item not found")
    if existing.get("operation") != "post":
        raise InvoiceGLBridgeError("Queue item is not a posting candidate")
    if existing.get("status") == "posted":
        return existing

    claimed = await db.gl_nilvera_queue.find_one_and_update(
        {
            "tenant_id": tenant_id,
            "id": item_id,
            "status": {"$in": ["pending", "blocked"]},
        },
        {
            "$set": {"status": "processing", "processing_started_at": _now_iso(), "processed_by": actor},
            "$inc": {"attempt_count": 1},
            "$unset": {"error_code": "", "error_detail": ""},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        latest = await db.gl_nilvera_queue.find_one(
            {"tenant_id": tenant_id, "id": item_id},
            {"_id": 0},
        )
        if latest and latest.get("status") == "posted":
            return latest
        raise InvoiceGLBridgeError("Nilvera GL queue item is already processing")

    settings = await get_nilvera_gl_settings(tenant_id)
    try:
        if claimed["direction"] == "incoming":
            entry = await post_incoming_invoice_to_gl(
                tenant_id,
                claimed["invoice_id"],
                purchase_account_code=settings["incoming_purchase_account_code"],
                vat_account_code=settings["incoming_vat_account_code"],
                payable_account_code=settings["incoming_payable_account_code"],
                other_tax_account_code=settings.get("incoming_other_tax_account_code"),
                deduction_account_code=settings.get("incoming_deduction_account_code"),
                other_tax_accounts_by_code=settings.get("incoming_other_tax_accounts_by_code"),
                deduction_accounts_by_code=settings.get("incoming_deduction_accounts_by_code"),
                actor=actor,
            )
        else:
            entry = await post_outgoing_invoice_to_gl(
                tenant_id,
                claimed["invoice_id"],
                revenue_account_code=settings["outgoing_revenue_account_code"],
                receivable_account_code=settings["outgoing_receivable_account_code"],
                discount_account_code=settings.get("outgoing_discount_account_code"),
                vat_account_code=settings.get("outgoing_vat_account_code"),
                accommodation_tax_account_code=settings.get("outgoing_accommodation_tax_account_code"),
                vat_accounts_by_rate=settings.get("outgoing_vat_accounts_by_rate"),
                accommodation_tax_accounts_by_rate=settings.get(
                    "outgoing_accommodation_tax_accounts_by_rate"
                ),
                actor=actor,
            )
    except Exception as exc:
        detail = str(exc)[:500] or type(exc).__name__
        await db.gl_nilvera_queue.update_one(
            {"tenant_id": tenant_id, "id": item_id},
            {
                "$set": {
                    "status": "blocked",
                    "error_code": type(exc).__name__,
                    "error_detail": detail,
                    "updated_at": _now_iso(),
                }
            },
        )
        logger.warning(
            "Nilvera GL posting blocked tenant=%s direction=%s invoice=%s error_type=%s",
            tenant_id,
            claimed.get("direction"),
            claimed.get("invoice_id"),
            type(exc).__name__,
        )
        return await db.gl_nilvera_queue.find_one(
            {"tenant_id": tenant_id, "id": item_id},
            {"_id": 0},
        )

    await db.gl_nilvera_queue.update_one(
        {"tenant_id": tenant_id, "id": item_id},
        {
            "$set": {
                "status": "posted",
                "journal_entry_id": entry.get("id"),
                "journal_entry_no": entry.get("entry_no"),
                "posted_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        },
    )
    return await db.gl_nilvera_queue.find_one(
        {"tenant_id": tenant_id, "id": item_id},
        {"_id": 0},
    )


async def list_nilvera_gl_queue(
    tenant_id: str,
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    db = get_db_for_tenant(tenant_id)
    query: dict = {"tenant_id": tenant_id}
    if status:
        query["status"] = status
    return await (
        db.gl_nilvera_queue.find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(max(1, min(limit, 1000)))
        .to_list(length=max(1, min(limit, 1000)))
    )


async def handle_incoming_invoice_synced(tenant_id: str, invoice_id: str) -> dict | None:
    return await enqueue_nilvera_gl_candidate(
        tenant_id,
        "incoming",
        invoice_id,
        source_status="synced",
    )


async def handle_outgoing_invoice_accepted(tenant_id: str, invoice_id: str) -> dict | None:
    return await enqueue_nilvera_gl_candidate(
        tenant_id,
        "outgoing",
        invoice_id,
        source_status="accepted",
    )


async def handle_outgoing_invoice_cancelled(
    tenant_id: str,
    invoice_id: str,
    *,
    event_ref: str,
    reason: str,
    actor: str = "system",
) -> dict | None:
    """Reverse a posted outgoing journal or expose a durable blocked case."""
    db = get_db_for_tenant(tenant_id)
    item_id = _queue_id(tenant_id, "outgoing", invoice_id, "reverse")
    now = _now_iso()
    try:
        reversal = await reverse_outgoing_invoice_gl(
            tenant_id,
            invoice_id,
            event_ref=event_ref,
            reason=reason,
            actor=actor,
        )
        status = "reversed" if reversal else "not_applicable"
        await db.gl_nilvera_queue.update_one(
            {"tenant_id": tenant_id, "id": item_id},
            {
                "$set": {
                    "status": status,
                    "journal_entry_id": reversal.get("id") if reversal else None,
                    "journal_entry_no": reversal.get("entry_no") if reversal else None,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "id": item_id,
                    "tenant_id": tenant_id,
                    "operation": "reverse",
                    "direction": "outgoing",
                    "invoice_id": invoice_id,
                    "event_ref": event_ref,
                    "reason": reason,
                    "created_at": now,
                    "created_by": actor,
                },
            },
            upsert=True,
        )
        return reversal
    except Exception as exc:
        await db.gl_nilvera_queue.update_one(
            {"tenant_id": tenant_id, "id": item_id},
            {
                "$set": {
                    "status": "blocked",
                    "error_code": type(exc).__name__,
                    "error_detail": (str(exc) or type(exc).__name__)[:500],
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "id": item_id,
                    "tenant_id": tenant_id,
                    "operation": "reverse",
                    "direction": "outgoing",
                    "invoice_id": invoice_id,
                    "event_ref": event_ref,
                    "reason": reason,
                    "created_at": now,
                    "created_by": actor,
                },
            },
            upsert=True,
        )
        logger.error(
            "Nilvera outgoing GL reversal blocked tenant=%s invoice=%s error_type=%s",
            tenant_id,
            invoice_id,
            type(exc).__name__,
        )
        return None
