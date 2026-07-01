"""Offline sync endpoints."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import require_admin, require_auth
from db import db, guests_col, scans_col
from helpers import serialize_doc
from multi_property import get_pending_syncs, process_sync, store_offline_data
from schemas import OfflineSyncRequest

router = APIRouter()


@router.post("/api/sync/upload", tags=["Offline Sync"], summary="Çevrimdışı veri yükle",
             description="Internet kesintisinde biriktirilen verileri sunucuya yükler")
async def upload_offline_data(req: OfflineSyncRequest, user=Depends(require_auth)):
    if req.data_type not in ("scans", "guests"):
        raise HTTPException(status_code=400, detail="Geçersiz veri tipi. scans veya guests olmalı.")
    sync = await store_offline_data(
        db, property_id=req.property_id, data_type=req.data_type,
        data=req.data, device_id=req.device_id,
    )
    return {"success": True, "sync": serialize_doc(sync)}


@router.get("/api/sync/pending", tags=["Offline Sync"], summary="Bekleyen senkronizasyonlar")
async def get_pending_sync(property_id: Optional[str] = None, user=Depends(require_auth)):
    syncs = await get_pending_syncs(db, property_id=property_id)
    return {"syncs": syncs, "total": len(syncs)}


@router.post("/api/sync/{sync_id}/process", tags=["Offline Sync"], summary="Senkronizasyonu işle")
async def process_sync_data(sync_id: str, user=Depends(require_admin)):
    """Offline verilerini gerçek DB'ye işle"""
    col = db["offline_sync"]
    sync_doc = await col.find_one({"sync_id": sync_id})
    if not sync_doc:
        raise HTTPException(status_code=404, detail="Senkronizasyon bulunamadı")
    errors = []
    processed = 0
    for item in sync_doc.get("data", []):
        try:
            if sync_doc["data_type"] == "guests":
                guest_doc = {
                    **item,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "status": "pending",
                    "source": "offline_sync",
                    "sync_id": sync_id,
                }
                await guests_col.insert_one(guest_doc)
                processed += 1
            elif sync_doc["data_type"] == "scans":
                scan_doc = {
                    **item,
                    "created_at": datetime.now(timezone.utc),
                    "source": "offline_sync",
                    "sync_id": sync_id,
                }
                await scans_col.insert_one(scan_doc)
                processed += 1
        except Exception as e:
            errors.append(f"Kayıt işleme hatası: {str(e)}")
    status = "processed" if not errors else "partial"
    result = await process_sync(db, sync_id, status=status, errors=errors)
    return {
        "success": True,
        "processed_count": processed,
        "error_count": len(errors),
        "errors": errors,
        "sync": result,
    }
