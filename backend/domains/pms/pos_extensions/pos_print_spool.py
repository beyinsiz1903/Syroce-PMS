"""POS Print Spool — termal fiş yazıcı (ESC/POS) kuyruğu + adapter.

Mevcut akış bozulmaz. close_order tetiklendiğinde frontend bu router'a
`POST /jobs` ile bir print job push edebilir; backend ESC/POS metin
şablonu render eder ve adapter'a iletir.

Adapter seçimi `POS_PRINT_DRIVER` env değişkeniyle:
  - "simulator" (default) → job 'sent' işaretlenir, bytes preview döndürülür
  - "escpos_tcp"          → ileride gerçek TCP yazıcıya socket.send (stub)
Gerçek donanım entegrasyonu sertifikasyon gerektirir; adapter pattern
ile pluggable.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

from ._idem import idempotent_insert

router = APIRouter(prefix="/api/pos/ext/print", tags=["pos-ext-print"])

# ESC/POS control bytes
_INIT = b"\x1b\x40"           # initialize
_CUT = b"\x1d\x56\x00"        # full cut
_BOLD_ON = b"\x1b\x45\x01"
_BOLD_OFF = b"\x1b\x45\x00"
_ALIGN_CENTER = b"\x1b\x61\x01"
_ALIGN_LEFT = b"\x1b\x61\x00"
_NL = b"\n"


class PrintJobCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = Field(pattern="^(receipt|kitchen|test)$")
    printer_id: str = Field(default="default")
    copies: int = Field(default=1, ge=1, le=5)
    payload: dict
    idempotency_key: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _render_receipt(payload: dict) -> bytes:
    """Render a minimal receipt to ESC/POS bytes."""
    out = bytearray()
    out += _INIT
    header = (payload.get("header") or "RECEIPT")[:42]
    out += _ALIGN_CENTER + _BOLD_ON + header.encode("utf-8", "ignore") + _BOLD_OFF + _NL
    if payload.get("subheader"):
        out += (str(payload["subheader"])[:42]).encode("utf-8", "ignore") + _NL
    out += b"-" * 32 + _NL
    out += _ALIGN_LEFT
    for item in (payload.get("items") or []):
        name = str(item.get("name", ""))[:24]
        qty = int(item.get("quantity") or 1)
        line_total = float(item.get("line_total") or (item.get("quantity", 1) * item.get("price", 0)))
        line = f"{qty}x {name:<24} {line_total:>7.2f}"
        out += line.encode("utf-8", "ignore") + _NL
    out += b"-" * 32 + _NL
    total = float(payload.get("total") or 0)
    out += _BOLD_ON + f"TOTAL {total:>26.2f}".encode("utf-8", "ignore") + _BOLD_OFF + _NL
    if payload.get("footer"):
        out += _NL + _ALIGN_CENTER + str(payload["footer"])[:42].encode("utf-8", "ignore") + _NL
    out += _NL * 3 + _CUT
    return bytes(out)


def _render_kitchen(payload: dict) -> bytes:
    out = bytearray()
    out += _INIT + _ALIGN_CENTER + _BOLD_ON
    station = str(payload.get("station") or "KITCHEN")[:32]
    out += station.encode("utf-8", "ignore") + _NL + _BOLD_OFF
    if payload.get("table"):
        out += f"Masa: {payload['table']}".encode("utf-8", "ignore") + _NL
    out += b"-" * 32 + _NL + _ALIGN_LEFT
    for item in (payload.get("items") or []):
        out += f"{int(item.get('quantity') or 1)}x {item.get('name', '')[:28]}".encode("utf-8", "ignore") + _NL
        notes = item.get("special_instructions")
        if notes:
            out += f"  >> {notes[:28]}".encode("utf-8", "ignore") + _NL
    out += _NL * 2 + _CUT
    return bytes(out)


def _render(kind: str, payload: dict) -> bytes:
    if kind == "kitchen":
        return _render_kitchen(payload)
    if kind == "test":
        return _INIT + b"PRINTER TEST OK" + _NL * 3 + _CUT
    return _render_receipt(payload)


async def _dispatch(job: dict) -> dict:
    """Send rendered bytes to the configured driver."""
    driver = (os.environ.get("POS_PRINT_DRIVER") or "simulator").lower()
    bytes_blob = job["rendered_bytes"]
    if driver == "simulator":
        return {"driver": "simulator", "ok": True, "bytes_len": len(bytes_blob)}
    if driver == "escpos_tcp":
        # Real network dispatch deliberately not enabled here without a printer
        # registry. Mark as 'failed' so ops sees the gap and provisions a printer.
        return {"driver": "escpos_tcp", "ok": False, "reason": "no printer registry configured"}
    return {"driver": driver, "ok": False, "reason": "unknown driver"}


@router.post("/jobs")
async def enqueue(body: PrintJobCreate, current_user: User = Depends(get_current_user)):
    rendered = _render(body.kind, body.payload)
    job = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "kind": body.kind,
        "printer_id": body.printer_id,
        "copies": int(body.copies),
        "payload": body.payload,
        "rendered_bytes": rendered,
        "status": "pending",
        "idempotency_key": body.idempotency_key,
        "created_at": _now(),
        "created_by": current_user.id,
    }
    saved, replayed = await idempotent_insert(
        db.print_jobs, current_user.tenant_id, body.idempotency_key, job
    )
    public = {**saved}
    public.pop("_id", None)
    public["rendered_bytes_len"] = len(rendered)
    public["rendered_preview"] = rendered[:80].decode("latin-1", "replace")
    public.pop("rendered_bytes", None)
    return {"success": True, "job": public, "idempotent": replayed}


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(default=None, pattern="^(pending|sent|failed|cancelled)$"),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
):
    q: dict = {"tenant_id": current_user.tenant_id}
    if status:
        q["status"] = status
    rows = await db.print_jobs.find(
        q, {"_id": 0, "rendered_bytes": 0}
    ).sort("created_at", -1).to_list(limit)
    return {"jobs": rows, "count": len(rows)}


@router.post("/jobs/{job_id}/dispatch")
async def dispatch_job(job_id: str, current_user: User = Depends(get_current_user)):
    job = await db.print_jobs.find_one(
        {"id": job_id, "tenant_id": current_user.tenant_id}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] in ("sent", "cancelled"):
        return {"success": True, "job_status": job["status"], "idempotent": True}

    result = await _dispatch(job)
    new_status = "sent" if result.get("ok") else "failed"
    await db.print_jobs.update_one(
        {"id": job_id, "tenant_id": current_user.tenant_id},
        {"$set": {
            "status": new_status,
            "dispatched_at": _now(),
            "dispatch_result": result,
        }},
    )
    return {"success": True, "status": new_status, "result": result}


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, current_user: User = Depends(get_current_user)):
    res = await db.print_jobs.update_one(
        {"id": job_id, "tenant_id": current_user.tenant_id, "status": "pending"},
        {"$set": {"status": "cancelled", "cancelled_at": _now(), "cancelled_by": current_user.id}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pending job not found")
    return {"success": True, "cancelled": job_id}
