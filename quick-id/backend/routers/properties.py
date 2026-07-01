"""Multi-property endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import require_admin, require_auth
from db import db
from helpers import serialize_doc
from multi_property import create_property, get_property, list_properties, update_property
from schemas import PropertyCreate, PropertyUpdate

router = APIRouter()


@router.get("/api/properties", tags=["Multi-Property"], summary="Tesisleri listele")
async def get_properties(is_active: Optional[bool] = None, user=Depends(require_auth)):
    properties = await list_properties(db, is_active=is_active)
    return {"properties": properties, "total": len(properties)}


@router.post("/api/properties", tags=["Multi-Property"], summary="Yeni tesis oluştur")
async def create_new_property(req: PropertyCreate, user=Depends(require_admin)):
    prop = await create_property(
        db, name=req.name, address=req.address, phone=req.phone,
        tax_no=req.tax_no, city=req.city, created_by=user.get("email"),
    )
    return {"success": True, "property": serialize_doc(prop)}


@router.get("/api/properties/{property_id}", tags=["Multi-Property"], summary="Tesis detayı")
async def get_property_detail(property_id: str, user=Depends(require_auth)):
    prop = await get_property(db, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Tesis bulunamadı")
    return {"property": prop}


@router.patch("/api/properties/{property_id}", tags=["Multi-Property"], summary="Tesis güncelle")
async def update_property_endpoint(property_id: str, req: PropertyUpdate, user=Depends(require_admin)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    prop = await update_property(db, property_id, updates)
    if not prop:
        raise HTTPException(status_code=404, detail="Tesis bulunamadı")
    return {"success": True, "property": prop}
