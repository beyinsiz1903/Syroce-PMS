"""POS Barcode — barkod → menü ürünü eşleme + scan event log.

Bu router pos_menu/pos_orders'a YAZMAZ. Sadece eşleme tablosu tutar
(`pos_barcode_map`) ve `/lookup/{barcode}` endpoint'i ile menü item
döner; frontend orderItem oluştururken bu sonucu kullanabilir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/pos/ext/barcode", tags=["pos-ext-barcode"])


class BarcodeMap(BaseModel):
    model_config = ConfigDict(extra="ignore")
    barcode: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9\-]+$")
    menu_item_id: str | None = None
    sku: str | None = None
    name: str | None = None
    unit_price: float | None = Field(default=None, ge=0)
    category: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("/map")
async def upsert_mapping(body: BarcodeMap, current_user: User = Depends(get_current_user)):
    if not body.menu_item_id:
        raise HTTPException(422, 'Barkodu mevcut bir menü ürününe bağlayın.')
    menu_item = await db.pos_menu_items.find_one({'tenant_id': current_user.tenant_id, 'id': body.menu_item_id}, {'_id': 0})
    if not menu_item:
        raise HTTPException(404, 'Menü ürünü bu tesiste bulunamadı.')
    doc = body.model_dump()
    doc.update(name=menu_item.get('item_name') or menu_item.get('name'),
               unit_price=menu_item.get('unit_price', menu_item.get('price')), outlet_id=menu_item.get('outlet_id'))
    doc.update(
        {
            "tenant_id": current_user.tenant_id,
            "updated_at": _now(),
            "updated_by": current_user.id,
        }
    )
    res = await db.pos_barcode_map.update_one(
        {"tenant_id": current_user.tenant_id, "barcode": body.barcode},
        {
            "$set": doc,
            "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now()},
        },
        upsert=True,
    )
    saved = await db.pos_barcode_map.find_one({"tenant_id": current_user.tenant_id, "barcode": body.barcode}, {"_id": 0})
    return {"success": True, "mapping": saved, "created": res.upserted_id is not None}


@router.get("/map")
async def list_mappings(
    q: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    flt: dict = {"tenant_id": current_user.tenant_id}
    if q:
        flt["barcode"] = {"$regex": f"^{q}"}
    rows = await db.pos_barcode_map.find(flt, {"_id": 0}).sort("updated_at", -1).to_list(limit)
    return {"mappings": rows, "count": len(rows)}


@router.delete("/map/{barcode}")
async def delete_mapping(barcode: str, current_user: User = Depends(get_current_user)):
    res = await db.pos_barcode_map.delete_one({"tenant_id": current_user.tenant_id, "barcode": barcode})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"success": True, "deleted": barcode}


@router.get("/lookup/{barcode}")
async def lookup(barcode: str, current_user: User = Depends(get_current_user), outlet_id: str | None = None):
    doc = await db.pos_barcode_map.find_one({"tenant_id": current_user.tenant_id, "barcode": barcode}, {"_id": 0})
    # Log every lookup for audit/fraud reasons.
    await db.pos_barcode_scans.insert_one(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "barcode": barcode,
            "found": bool(doc),
            "user_id": current_user.id,
            "scanned_at": _now(),
        }
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Barcode not mapped")
    query = {'tenant_id': current_user.tenant_id, 'id': doc.get('menu_item_id'),
             'available': {'$ne': False}, 'is_active': {'$ne': False}, 'status': {'$nin': ['inactive', 'deleted', 'archived']}}
    if outlet_id:
        query['outlet_id'] = outlet_id
    item = await db.pos_menu_items.find_one(query, {'_id': 0})
    if not item:
        raise HTTPException(422, 'Barkod bu satış noktasında etkin bir ürüne bağlı değil. Menü eşlemesini kontrol edin.')
    return {"barcode": barcode, "mapping": doc, 'item': item}


@router.get("/scans")
async def list_scans(
    limit: int = Query(default=100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    rows = await db.pos_barcode_scans.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("scanned_at", -1).to_list(limit)
    return {"scans": rows, "count": len(rows)}
