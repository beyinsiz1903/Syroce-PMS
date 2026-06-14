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

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

from ._idem import idempotent_insert

logger = logging.getLogger(__name__)

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
    if payload.get("adisyon_number"):
        out += _BOLD_ON + f"Adisyon No: {payload['adisyon_number']}".encode("utf-8", "ignore") + _BOLD_OFF + _NL
    if payload.get("business_date"):
        out += f"Is Gunu: {payload['business_date']}".encode("utf-8", "ignore") + _NL
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


async def _send_tcp(host: str, port: int, data: bytes, timeout: float = 5.0) -> None:
    """Open a short-lived TCP socket to an ESC/POS network printer and stream the
    rendered bytes. Time-bounded so an unreachable printer can't hang the caller.
    """
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=timeout
    )
    try:
        writer.write(data)
        await asyncio.wait_for(writer.drain(), timeout=timeout)
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=timeout)
        except Exception:
            pass


async def _dispatch(job: dict) -> dict:
    """Send rendered bytes to the printer the job targets.

    Driver resolution: the registered printer's own `driver` wins; otherwise the
    `POS_PRINT_DRIVER` env default (simulator). The escpos_tcp driver streams to
    the operator-configured printer host:port from the `pos_printers` registry.
    """
    bytes_blob = job["rendered_bytes"]
    tenant_id = job.get("tenant_id")
    printer_id = job.get("printer_id") or "default"

    printer = None
    if tenant_id:
        try:
            printer = await db.pos_printers.find_one(
                {"tenant_id": tenant_id, "printer_id": printer_id}, {"_id": 0}
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("printer registry lookup failed: %s", exc)

    if printer and not printer.get("enabled", True):
        return {"driver": "disabled", "ok": False, "reason": "printer disabled"}

    driver = (
        (printer.get("driver") if printer else None)
        or os.environ.get("POS_PRINT_DRIVER")
        or "simulator"
    ).lower()

    if driver == "simulator":
        return {"driver": "simulator", "ok": True, "bytes_len": len(bytes_blob)}
    if driver == "escpos_tcp":
        if not printer or not printer.get("host"):
            return {
                "driver": "escpos_tcp",
                "ok": False,
                "reason": "printer not registered or host missing",
            }
        try:
            await _send_tcp(
                str(printer["host"]), int(printer.get("port") or 9100), bytes_blob
            )
            return {
                "driver": "escpos_tcp",
                "ok": True,
                "bytes_len": len(bytes_blob),
                "host": printer["host"],
            }
        except Exception as exc:
            return {"driver": "escpos_tcp", "ok": False, "reason": f"tcp send failed: {exc}"}
    return {"driver": driver, "ok": False, "reason": "unknown driver"}


async def enqueue_print_job(
    *,
    tenant_id: str,
    kind: str,
    payload: dict,
    idempotency_key: str | None = None,
    printer_id: str = "default",
    copies: int = 1,
    created_by: str | None = None,
    auto_dispatch: bool = False,
) -> tuple[dict, bool]:
    """Reusable spooler entry point (callable from other modules, e.g. the POS
    create-order auto-KOT path). Renders, idempotently inserts, and — when
    auto_dispatch — immediately attempts delivery, recording the result so a
    failed/missing printer stays visible in print_jobs status.

    Returns (saved_job, was_idempotent_replay).
    """
    rendered = _render(kind, payload)
    job = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "kind": kind,
        "printer_id": printer_id,
        "copies": int(copies),
        "payload": payload,
        "rendered_bytes": rendered,
        "status": "pending",
        "idempotency_key": idempotency_key,
        "created_at": _now(),
        "created_by": created_by,
    }
    saved, replayed = await idempotent_insert(db.print_jobs, tenant_id, idempotency_key, job)
    if auto_dispatch and not replayed:
        disp_job = saved if saved.get("rendered_bytes") else {**saved, "rendered_bytes": rendered}
        result = await _dispatch(disp_job)
        new_status = "sent" if result.get("ok") else "failed"
        try:
            await db.print_jobs.update_one(
                {"id": saved["id"], "tenant_id": tenant_id},
                {"$set": {
                    "status": new_status,
                    "dispatched_at": _now(),
                    "dispatch_result": result,
                }},
            )
            saved["status"] = new_status
            saved["dispatch_result"] = result
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("print job status update failed: %s", exc)
    return saved, replayed


@router.post("/jobs")
async def enqueue(body: PrintJobCreate, current_user: User = Depends(get_current_user)):
    rendered = _render(body.kind, body.payload)
    saved, replayed = await enqueue_print_job(
        tenant_id=current_user.tenant_id,
        kind=body.kind,
        payload=body.payload,
        idempotency_key=body.idempotency_key,
        printer_id=body.printer_id,
        copies=body.copies,
        created_by=current_user.id,
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


# ── Printer registry ──────────────────────────────────────────────────────
# Operators register their network (ESC/POS over TCP) or simulator printers and
# map each kitchen station / outlet to one. The KOT auto-print path targets a
# printer_id == station, so a "hot_kitchen" printer here receives the hot KOT.

class PrinterUpsert(BaseModel):
    model_config = ConfigDict(extra="ignore")
    printer_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    driver: str = Field(default="simulator", pattern="^(simulator|escpos_tcp)$")
    host: str | None = None
    port: int = Field(default=9100, ge=1, le=65535)
    station: str | None = None
    outlet_id: str | None = None
    enabled: bool = True


@router.get("/printers")
async def list_printers(current_user: User = Depends(get_current_user)):
    rows = await db.pos_printers.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("printer_id", 1).to_list(200)
    return {"printers": rows, "count": len(rows)}


@router.post("/printers")
async def upsert_printer(body: PrinterUpsert, current_user: User = Depends(get_current_user)):
    if body.driver == "escpos_tcp" and not (body.host and body.host.strip()):
        raise HTTPException(
            status_code=400, detail="escpos_tcp yazıcı için host (IP) zorunludur"
        )
    doc = body.model_dump()
    doc["tenant_id"] = current_user.tenant_id
    doc["updated_at"] = _now()
    doc["updated_by"] = current_user.id
    await db.pos_printers.update_one(
        {"tenant_id": current_user.tenant_id, "printer_id": body.printer_id},
        {"$set": doc, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )
    saved = await db.pos_printers.find_one(
        {"tenant_id": current_user.tenant_id, "printer_id": body.printer_id}, {"_id": 0}
    )
    return {"success": True, "printer": saved}


@router.delete("/printers/{printer_id}")
async def delete_printer(printer_id: str, current_user: User = Depends(get_current_user)):
    res = await db.pos_printers.delete_one(
        {"tenant_id": current_user.tenant_id, "printer_id": printer_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Printer not found")
    return {"success": True, "deleted": printer_id}


@router.post("/printers/{printer_id}/test")
async def test_printer(printer_id: str, current_user: User = Depends(get_current_user)):
    """Render + dispatch a test ticket to the given printer so operators can
    verify connectivity before going live."""
    saved, _ = await enqueue_print_job(
        tenant_id=current_user.tenant_id,
        kind="test",
        payload={},
        printer_id=printer_id,
        created_by=current_user.id,
        auto_dispatch=True,
    )
    return {
        "success": True,
        "status": saved.get("status"),
        "result": saved.get("dispatch_result"),
    }
