"""
HotelRunner Scheduled Pull Job & Reservation Sync

Re-export module — preserves backward compatibility.
Actual implementation split into:
  - sync_engine.py    — Core sync phases (A, A.5, A.6, B) + reservation update
  - sync_scheduler.py — ReservationPullScheduler class + singleton

API endpoints remain in this file for router registration compatibility.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
    _resolve_property_id,
    explode_multi_room_reservation,
)
from domains.channel_manager.providers.sync_engine import (  # noqa: F401
    log_pull,
    run_phase_a,
    run_phase_a5,
    run_phase_a6,
    run_phase_b,
    sync_reservation_update,
)
from domains.channel_manager.providers.sync_scheduler import (  # noqa: F401
    ReservationPullScheduler,
    pull_scheduler,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v93 DW

logger = logging.getLogger(__name__)

sync_router = APIRouter(
    prefix="/api/channel-manager/hotelrunner",
    tags=["HotelRunner Sync"],
)


@sync_router.post("/sync/reservations/pull")
async def manual_pull(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi")

    hr_id = conn.get("hr_id", conn.get("property_id", "default"))
    from core.secrets import get_secrets_manager

    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(current_user.tenant_id, "hotelrunner", hr_id)

    if not creds or not creds.get("token"):
        fallback = await db.hotelrunner_connections.find_one(
            {"tenant_id": current_user.tenant_id, "is_active": True},
            {"_id": 0, "token": 1, "hr_id": 1},
        )
        if fallback and fallback.get("token"):
            creds = {"token": fallback["token"], "hr_id": fallback.get("hr_id", hr_id)}
        else:
            raise HTTPException(status_code=502, detail="HotelRunner kimlik bilgileri bulunamadi")

    result = await pull_scheduler.pull_for_tenant(
        tenant_id=current_user.tenant_id,
        token=creds["token"],
        hr_id=creds.get("hr_id", hr_id),
        safety_window_minutes=5,
        is_manual=True,
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Pull hatasi: {result.get('error')}")

    return {
        "message": f"{result['processed']} rezervasyon islendi ({result['fetched']} cekildi, {result.get('fired', 0)} onaylandi)",
        **result,
    }


@sync_router.get("/sync/status")
async def get_sync_status(current_user: User = Depends(get_current_user)):
    cursor = await db.hotelrunner_pull_cursors.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    )

    pending_events = await db.hotelrunner_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "pending"},
    )
    error_events = await db.hotelrunner_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "error"},
    )
    total_reservations = await db.hotelrunner_reservations.count_documents(
        {"tenant_id": current_user.tenant_id},
    )

    return {
        "scheduler_running": pull_scheduler.is_running,
        "auto_polling_disabled": not pull_scheduler.is_running,
        "polling_interval_seconds": pull_scheduler._base_interval,
        "cycle_count": pull_scheduler._cycle_count,
        "last_pull": cursor,
        "pending_events": pending_events,
        "error_events": error_events,
        "total_reservations": total_reservations,
        "optimization_notes": {
            "phase_a": "Yeni rezervasyonlar (undelivered) - her döngüde",
            "phase_a5": "Modifikasyon tespiti (from_last_update_date) - her döngüde",
            "phase_a6": "Bireysel rezervasyon kontrolü - her döngüde",
            "phase_b": "Tam catch-up (tüm rezervasyonlar) - her 10. döngüde",
        },
    }


@sync_router.post("/sync/scheduler/start")
async def start_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi")

    interval = conn.get("sync_interval_minutes", 15)
    await pull_scheduler.start(interval_minutes=interval)
    return {"message": f"Scheduler baslatildi ({interval} dk aralikla)", "interval": interval}


@sync_router.post("/sync/scheduler/stop")
async def stop_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    await pull_scheduler.stop()
    return {"message": "Scheduler durduruldu"}


@sync_router.post("/sync/reservations/full-resync")
async def full_resync(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi")

    hr_id = conn.get("hr_id", conn.get("property_id", "default"))
    from core.secrets import get_secrets_manager

    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(current_user.tenant_id, "hotelrunner", hr_id)

    if not creds or not creds.get("token"):
        fallback = await db.hotelrunner_connections.find_one(
            {"tenant_id": current_user.tenant_id, "is_active": True},
            {"_id": 0, "token": 1, "hr_id": 1},
        )
        if fallback and fallback.get("token"):
            creds = {"token": fallback["token"], "hr_id": fallback.get("hr_id", hr_id)}
        else:
            raise HTTPException(status_code=502, detail="HotelRunner kimlik bilgileri bulunamadi")

    from core.tenant_db import set_tenant_context

    set_tenant_context(current_user.tenant_id)
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

    provider = HotelRunnerProvider(token=creds["token"], hr_id=creds.get("hr_id", hr_id))

    all_reservations = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        result = await provider.get_reservations(
            undelivered=False,
            per_page=50,
            page=page,
        )
        if not result["success"]:
            raise HTTPException(status_code=502, detail=f"Rezervasyon cekme hatasi: {result.get('error')}")
        page_reservations = result["data"].get("reservations", [])
        all_reservations.extend(page_reservations)
        total_pages = result["data"].get("pages", 1)
        page += 1

    processed = 0
    skipped = 0
    errors = 0
    for res in all_reservations:
        sub_reservations = explode_multi_room_reservation(res)
        for sub_res in sub_reservations:
            try:
                await _persist_and_process(
                    current_user.tenant_id,
                    _resolve_property_id(sub_res),
                    sub_res,
                    "reservation_pull",
                )
                processed += 1
            except Exception as e:
                err_msg = str(e)
                if "duplicate" in err_msg.lower() or "already" in err_msg.lower():
                    skipped += 1
                else:
                    errors += 1
                    logger.error(f"[RESYNC] Error: {e}")

    return {
        "message": f"Full resync tamamlandi: {processed} islendi, {skipped} atlandi (zaten var), {errors} hata",
        "success": True,
        "fetched": len(all_reservations),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
    }
