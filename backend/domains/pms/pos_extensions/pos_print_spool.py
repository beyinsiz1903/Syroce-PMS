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

# Real-time status request commands (DLE EOT n).
_DLE_EOT_OFFLINE = b"\x10\x04\x02"  # offline cause status (cover/paper/error)
_DLE_EOT_PAPER = b"\x10\x04\x04"    # paper sensor status (near-end / end)

# ── Character code pages (Turkish certification) ──────────────────────────
# Real ESC/POS thermal printers do NOT consume UTF-8: each glyph is one byte
# resolved through the printer's *currently selected* code page. Turkish letters
# (ç ş ğ ü ö ı İ Ş Ğ Ü Ö Ç) must therefore be encoded with a Turkish single-byte
# code page (CP857 or CP1254) AND the matching "ESC t n" code-table command must
# be emitted first, or the printer renders multi-byte UTF-8 as garbage. The exact
# "ESC t n" table id varies per model, so it is operator-overridable per printer
# (codepage_table_id) during certification.
_DEFAULT_CODEPAGE = (os.environ.get("POS_PRINT_CODEPAGE") or "cp857").lower()

_CODEPAGE_TABLE_ID: dict[str, int] = {
    "cp437": 0,    # PC437 USA / Standard Europe
    "cp850": 2,    # PC850 Multilingual
    "cp857": 13,   # PC857 Turkish (common Epson TM code table 13)
    "cp1254": 47,  # WPC1254 Windows Turkish
}

# Last-resort transliteration for glyphs absent from the chosen code page, so an
# unmappable character degrades to a readable ASCII approximation instead of a
# replacement box.
_TRANSLIT = str.maketrans({
    "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
    "ç": "c", "Ç": "C", "ö": "o", "Ö": "O", "ü": "u", "Ü": "U",
    "₺": "TL", "“": '"', "”": '"', "’": "'", "‘": "'", "–": "-", "—": "-",
})


def _norm_codepage(codepage: str | None) -> str:
    cp = (codepage or _DEFAULT_CODEPAGE or "cp857").lower()
    return cp if cp in _CODEPAGE_TABLE_ID else "cp857"


def _select_codepage_cmd(codepage: str, table_id: int | None = None) -> bytes:
    """ESC t n — select the printer character code table for `codepage`."""
    n = table_id if table_id is not None else _CODEPAGE_TABLE_ID[_norm_codepage(codepage)]
    return b"\x1b\x74" + bytes([n & 0xFF])


def _enc(text: str, codepage: str) -> bytes:
    """Encode `text` for a single-byte ESC/POS code page (NOT UTF-8).

    Unmappable glyphs are transliterated to ASCII before a final replace pass so
    nothing is silently dropped.
    """
    try:
        return text.encode(codepage)
    except (UnicodeEncodeError, LookupError):
        return text.translate(_TRANSLIT).encode(codepage, "replace")


def _interpret_status(offline: int | None, paper: int | None) -> dict:
    """Decode DLE EOT real-time status bytes into operator-readable conditions."""
    conditions: list[str] = []
    if offline is not None:
        if offline & 0x04:
            conditions.append("cover_open")
        if offline & 0x20:
            conditions.append("paper_end")
        if offline & 0x40:
            conditions.append("error")
    if paper is not None:
        if paper & 0x60 == 0x60:
            conditions.append("paper_end")
        elif paper & 0x0C == 0x0C:
            conditions.append("paper_near_end")
    seen: list[str] = []
    for c in conditions:
        if c not in seen:
            seen.append(c)
    return {
        "conditions": seen,
        "offline_byte": offline,
        "paper_byte": paper,
        "blocking": any(c in ("cover_open", "paper_end", "error") for c in seen),
    }


class PrintJobCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = Field(pattern="^(receipt|kitchen|test)$")
    printer_id: str = Field(default="default")
    copies: int = Field(default=1, ge=1, le=5)
    payload: dict
    idempotency_key: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _render_receipt(payload: dict, codepage: str = _DEFAULT_CODEPAGE, table_id: int | None = None) -> bytes:
    """Render a minimal receipt to ESC/POS bytes (single-byte code page)."""
    cp = _norm_codepage(codepage)
    out = bytearray()
    out += _INIT + _select_codepage_cmd(cp, table_id)
    header = (payload.get("header") or "RECEIPT")[:42]
    out += _ALIGN_CENTER + _BOLD_ON + _enc(header, cp) + _BOLD_OFF + _NL
    if payload.get("subheader"):
        out += _enc(str(payload["subheader"])[:42], cp) + _NL
    out += b"-" * 32 + _NL
    out += _ALIGN_LEFT
    for item in (payload.get("items") or []):
        name = str(item.get("name", ""))[:24]
        qty = int(item.get("quantity") or 1)
        line_total = float(item.get("line_total") or (item.get("quantity", 1) * item.get("price", 0)))
        line = f"{qty}x {name:<24} {line_total:>7.2f}"
        out += _enc(line, cp) + _NL
    out += b"-" * 32 + _NL
    total = float(payload.get("total") or 0)
    out += _BOLD_ON + _enc(f"TOTAL {total:>26.2f}", cp) + _BOLD_OFF + _NL
    if payload.get("footer"):
        out += _NL + _ALIGN_CENTER + _enc(str(payload["footer"])[:42], cp) + _NL
    out += _NL * 3 + _CUT
    return bytes(out)


def _render_kitchen(payload: dict, codepage: str = _DEFAULT_CODEPAGE, table_id: int | None = None) -> bytes:
    cp = _norm_codepage(codepage)
    out = bytearray()
    out += _INIT + _select_codepage_cmd(cp, table_id) + _ALIGN_CENTER + _BOLD_ON
    station = str(payload.get("station") or "KITCHEN")[:32]
    out += _enc(station, cp) + _NL + _BOLD_OFF
    if payload.get("adisyon_number"):
        out += _BOLD_ON + _enc(f"Adisyon No: {payload['adisyon_number']}", cp) + _BOLD_OFF + _NL
    if payload.get("business_date"):
        out += _enc(f"Is Gunu: {payload['business_date']}", cp) + _NL
    if payload.get("table"):
        out += _enc(f"Masa: {payload['table']}", cp) + _NL
    out += b"-" * 32 + _NL + _ALIGN_LEFT
    for item in (payload.get("items") or []):
        out += _enc(f"{int(item.get('quantity') or 1)}x {str(item.get('name', ''))[:28]}", cp) + _NL
        notes = item.get("special_instructions")
        if notes:
            out += _enc(f"  >> {str(notes)[:28]}", cp) + _NL
    out += _NL * 2 + _CUT
    return bytes(out)


def _render(kind: str, payload: dict, codepage: str = _DEFAULT_CODEPAGE, table_id: int | None = None) -> bytes:
    cp = _norm_codepage(codepage)
    if kind == "kitchen":
        return _render_kitchen(payload, cp, table_id)
    if kind == "test":
        # The test ticket doubles as a code-page certification aid: it prints the
        # full Turkish glyph set so an operator can confirm correct output live.
        return (
            _INIT
            + _select_codepage_cmd(cp, table_id)
            + _enc(f"PRINTER TEST OK\nKod sayfasi: {cp}\nTurkce: ", cp)
            + _enc("ç ş ğ ü ö ı  İ Ş Ğ Ü Ö Ç", cp)
            + _NL * 3
            + _CUT
        )
    return _render_receipt(payload, cp, table_id)


async def _resolve_codepage(tenant_id: str | None, printer_id: str) -> tuple[str, int | None]:
    """Resolve the code page (and optional ESC t n override) for the target
    printer. Falls back to the env/default code page when the printer is not
    registered or the lookup fails."""
    cp = _DEFAULT_CODEPAGE
    table_id: int | None = None
    if tenant_id:
        try:
            printer = await db.pos_printers.find_one(
                {"tenant_id": tenant_id, "printer_id": printer_id},
                {"_id": 0, "codepage": 1, "codepage_table_id": 1},
            )
            if printer:
                cp = printer.get("codepage") or cp
                table_id = printer.get("codepage_table_id")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("codepage resolve failed: %s", exc)
    return _norm_codepage(cp), table_id


async def _send_tcp(
    host: str,
    port: int,
    data: bytes,
    timeout: float = 5.0,
    query_status: bool = True,
    status_timeout: float = 1.5,
) -> dict | None:
    """Open a short-lived TCP socket to an ESC/POS network printer and stream the
    rendered bytes. Time-bounded so an unreachable printer can't hang the caller.
    Returns the decoded real-time status (paper/cover/error) when the printer
    answers, else None.
    """
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=timeout
    )
    status: dict | None = None
    try:
        writer.write(data)
        await asyncio.wait_for(writer.drain(), timeout=timeout)
        if query_status:
            status = await _read_status(reader, writer, status_timeout)
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=timeout)
        except Exception:
            pass
    return status


async def _read_status(reader, writer, timeout: float = 1.5) -> dict | None:
    """Best-effort real-time status read (DLE EOT). A printer that doesn't answer
    over the raw port simply yields None — we never let it fail the print."""
    offline = paper = None
    for cmd, slot in ((_DLE_EOT_OFFLINE, "offline"), (_DLE_EOT_PAPER, "paper")):
        try:
            writer.write(cmd)
            await asyncio.wait_for(writer.drain(), timeout=timeout)
            chunk = await asyncio.wait_for(reader.read(1), timeout=timeout)
            if chunk:
                if slot == "offline":
                    offline = chunk[0]
                else:
                    paper = chunk[0]
        except Exception:
            pass
    if offline is None and paper is None:
        return None
    return _interpret_status(offline, paper)


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
            status = await _send_tcp(
                str(printer["host"]), int(printer.get("port") or 9100), bytes_blob
            )
            result = {
                "driver": "escpos_tcp",
                "ok": True,
                "bytes_len": len(bytes_blob),
                "host": printer["host"],
            }
            if status:
                result["printer_status"] = status
                if status.get("blocking"):
                    # Bytes left the host, but the printer is offline/out of paper
                    # so nothing actually printed — surface it as a failure.
                    result["ok"] = False
                    result["reason"] = "yazici donanim hatasi: " + ", ".join(
                        status.get("conditions") or ["unknown"]
                    )
            return result
        except Exception as exc:
            return {"driver": "escpos_tcp", "ok": False, "reason": f"tcp send failed: {exc}"}
    return {"driver": driver, "ok": False, "reason": "unknown driver"}


async def resolve_kot_printer(
    tenant_id: str, outlet_id: str | None, station: str
) -> dict:
    """Resolve the physical printer for a (outlet_id, station) pair from the
    `pos_printers` registry so the same kitchen station can target a different
    physical printer in each outlet/restaurant.

    Resolution priority (first enabled match wins):
      1. Exact (outlet_id + station) mapping — the per-outlet printer.
      2. Outlet-agnostic station printer (outlet_id unset) — a shared station
         printer used across outlets that don't override it.
      3. Legacy mapping: a printer whose `printer_id` literally equals the
         station name (the pre-registry convention).

    When nothing maps, falls back to `printer_id == station` (legacy behaviour)
    but flags `matched=False` so the caller can surface a visible warning.

    Returns {"printer_id": str, "matched": bool, "reason": str}.
    """
    base = {"tenant_id": tenant_id, "station": station}
    try:
        # 1. Exact per-outlet mapping.
        if outlet_id:
            p = await db.pos_printers.find_one(
                {**base, "outlet_id": outlet_id},
                {"_id": 0, "printer_id": 1, "enabled": 1},
            )
            if p and p.get("enabled", True):
                return {"printer_id": p["printer_id"], "matched": True, "reason": "outlet_station"}

        # 2. Outlet-agnostic (shared) station printer.
        p = await db.pos_printers.find_one(
            {**base, "outlet_id": {"$in": [None, ""]}},
            {"_id": 0, "printer_id": 1, "enabled": 1},
        )
        if p and p.get("enabled", True):
            return {"printer_id": p["printer_id"], "matched": True, "reason": "station_shared"}

        # 3. Legacy: a printer registered with printer_id == station.
        legacy = await db.pos_printers.find_one(
            {"tenant_id": tenant_id, "printer_id": station},
            {"_id": 0, "printer_id": 1, "enabled": 1},
        )
        if legacy and legacy.get("enabled", True):
            return {"printer_id": station, "matched": True, "reason": "legacy_id"}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("KOT printer resolution failed: %s", exc)

    # 4. Unmapped — fall back to the station name as printer_id, flag a warning.
    return {"printer_id": station, "matched": False, "reason": "unmapped"}


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
    routing_warning: str | None = None,
) -> tuple[dict, bool]:
    """Reusable spooler entry point (callable from other modules, e.g. the POS
    create-order auto-KOT path). Renders, idempotently inserts, and — when
    auto_dispatch — immediately attempts delivery, recording the result so a
    failed/missing printer stays visible in print_jobs status.

    `routing_warning` (set by the KOT path when no registered printer maps to the
    (outlet, station) pair) is persisted on the job so the unmapped-printer case
    stays visible in print_jobs status even when a fallback dispatch succeeds.

    Returns (saved_job, was_idempotent_replay).
    """
    codepage, table_id = await _resolve_codepage(tenant_id, printer_id)
    rendered = _render(kind, payload, codepage, table_id)
    job = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "kind": kind,
        "printer_id": printer_id,
        "copies": int(copies),
        "payload": payload,
        "rendered_bytes": rendered,
        "codepage": codepage,
        "status": "pending",
        "routing_warning": routing_warning,
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
    saved, replayed = await enqueue_print_job(
        tenant_id=current_user.tenant_id,
        kind=body.kind,
        payload=body.payload,
        idempotency_key=body.idempotency_key,
        printer_id=body.printer_id,
        copies=body.copies,
        created_by=current_user.id,
    )
    rendered = saved.get("rendered_bytes") or b""
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
    # Turkish certification: which single-byte code page the printer is set to.
    codepage: str = Field(default="cp857", pattern="^(cp437|cp850|cp857|cp1254)$")
    # Optional ESC t n override when a model's code-table id differs from the
    # built-in preset (set during certification of a specific model).
    codepage_table_id: int | None = Field(default=None, ge=0, le=255)


@router.get("/printers")
async def list_printers(current_user: User = Depends(get_current_user)):
    rows = await db.pos_printers.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("printer_id", 1).to_list(200)
    return {"printers": rows, "count": len(rows)}


@router.get("/printers/status")
async def printers_status(current_user: User = Depends(get_current_user)):
    """Return the latest print-job outcome per printer_id so the settings list
    can show each printer's live hardware status (offline / paper-end / near-end)
    at a glance, without the operator having to press "Test" on each one.

    The status is read from the most recent print_jobs row for each printer_id,
    using the dispatch_result.printer_status the dispatcher already records.
    """
    pipeline = [
        {"$match": {"tenant_id": current_user.tenant_id}},
        {"$sort": {"created_at": -1}},
        {
            "$group": {
                "_id": "$printer_id",
                "status": {"$first": "$status"},
                "dispatch_result": {"$first": "$dispatch_result"},
                "dispatched_at": {"$first": "$dispatched_at"},
                "created_at": {"$first": "$created_at"},
                "kind": {"$first": "$kind"},
                "routing_warning": {"$first": "$routing_warning"},
            }
        },
    ]
    statuses: dict[str, dict] = {}
    try:
        rows = await db.print_jobs.aggregate(pipeline).to_list(500)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("printers_status aggregation failed: %s", exc)
        rows = []
    for r in rows:
        pid = r.get("_id")
        if not pid:
            continue
        printer_status = (r.get("dispatch_result") or {}).get("printer_status") or {}
        conditions = printer_status.get("conditions") or []
        reason = (r.get("dispatch_result") or {}).get("reason")
        statuses[pid] = {
            "job_status": r.get("status"),
            "conditions": conditions,
            "blocking": bool(printer_status.get("blocking")),
            "reason": reason,
            "kind": r.get("kind"),
            "routing_warning": r.get("routing_warning"),
            "last_at": r.get("dispatched_at") or r.get("created_at"),
        }
    return {"statuses": statuses, "count": len(statuses)}


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
