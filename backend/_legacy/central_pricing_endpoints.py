"""Central Pricing Management - Chain-wide Rate Push & Bulk Price Updates"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/central-pricing", tags=["Central Pricing Management"])

# ============= MODELS =============
class BulkRateUpdate(BaseModel):
    room_type: str
    new_rate: float
    currency: str = "TRY"
    effective_from: str  # ISO date
    effective_to: Optional[str] = None
    target_properties: List[str] = []  # empty = all properties
    adjustment_type: str = "fixed"  # 'fixed', 'percentage', 'increment'
    adjustment_value: Optional[float] = None
    reason: Optional[str] = None

class RateTemplate(BaseModel):
    name: str
    description: Optional[str] = None
    rates: Dict[str, float]  # room_type -> rate
    currency: str = "TRY"
    season: Optional[str] = None  # 'high', 'low', 'mid'

# ============= ENDPOINTS =============
def create_central_pricing_routes(db, get_current_user):
    """Create central pricing management routes"""
    
    async def _get_user_tenant_ids(current_user):
        if getattr(current_user, 'role', '') == 'super_admin':
            tenants = await db.tenants.find({}, {"id": 1, "_id": 0}).to_list(100)
            return [t["id"] for t in tenants]
        chain = await db.hotel_chains.find_one({"admin_user_ids": current_user.id})
        if chain:
            return chain.get("tenant_ids", [])
        return [current_user.tenant_id] if current_user.tenant_id else []
    
    @router.get("/rates")
    async def get_chain_rates(
        room_type: Optional[str] = None,
        current_user=Depends(get_current_user)
    ):
        """Get current rates across all properties"""
        tenant_ids = await _get_user_tenant_ids(current_user)
        
        rates_by_property = []
        for tid in tenant_ids:
            tenant = await db.tenants.find_one({"id": tid}, {"_id": 0, "property_name": 1, "id": 1})
            query = {"tenant_id": tid}
            if room_type:
                query["room_type"] = room_type
            
            rates = await db.room_rates.find(query, {"_id": 0}).to_list(100)
            rooms = await db.rooms.find(query, {"_id": 0, "room_type": 1, "base_rate": 1, "rate": 1}).to_list(100)
            
            # Aggregate by room type
            room_types = {}
            for room in rooms:
                rt = room.get("room_type", "Standard")
                if rt not in room_types:
                    room_types[rt] = {
                        "room_type": rt,
                        "base_rate": room.get("base_rate", room.get("rate", 0)),
                        "count": 0
                    }
                room_types[rt]["count"] += 1
            
            rates_by_property.append({
                "property_id": tid,
                "property_name": tenant.get("property_name", "Unknown") if tenant else "Unknown",
                "room_rates": list(room_types.values()),
                "special_rates": rates
            })
        
        return {
            "properties": rates_by_property,
            "total_properties": len(rates_by_property)
        }
    
    @router.post("/bulk-update")
    async def bulk_rate_update(
        update: BulkRateUpdate,
        current_user=Depends(get_current_user)
    ):
        """Push rate changes across multiple properties"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        all_tenant_ids = await _get_user_tenant_ids(current_user)
        target_ids = update.target_properties if update.target_properties else all_tenant_ids
        
        # Validate target properties
        target_ids = [t for t in target_ids if t in all_tenant_ids]
        if not target_ids:
            raise HTTPException(status_code=400, detail="Gecerli hedef otel bulunamadi")
        
        results = []
        for tid in target_ids:
            try:
                if update.adjustment_type == "fixed":
                    new_rate = update.new_rate
                elif update.adjustment_type == "percentage" and update.adjustment_value:
                    # Get current rate first
                    room = await db.rooms.find_one({"tenant_id": tid, "room_type": update.room_type})
                    current_rate = room.get("base_rate", room.get("rate", 100)) if room else 100
                    new_rate = current_rate * (1 + update.adjustment_value / 100)
                elif update.adjustment_type == "increment" and update.adjustment_value:
                    room = await db.rooms.find_one({"tenant_id": tid, "room_type": update.room_type})
                    current_rate = room.get("base_rate", room.get("rate", 100)) if room else 100
                    new_rate = current_rate + update.adjustment_value
                else:
                    new_rate = update.new_rate
                
                # Update rooms
                result = await db.rooms.update_many(
                    {"tenant_id": tid, "room_type": update.room_type},
                    {"$set": {
                        "base_rate": new_rate,
                        "rate": new_rate,
                        "rate_updated_at": datetime.now(timezone.utc).isoformat(),
                        "rate_updated_by": current_user.id
                    }}
                )
                
                # Create rate history record
                await db.rate_history.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": tid,
                    "room_type": update.room_type,
                    "new_rate": new_rate,
                    "currency": update.currency,
                    "effective_from": update.effective_from,
                    "effective_to": update.effective_to,
                    "reason": update.reason,
                    "updated_by": current_user.id,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                
                results.append({
                    "property_id": tid,
                    "success": True,
                    "rooms_updated": result.modified_count,
                    "new_rate": round(new_rate, 2)
                })
            except Exception as e:
                results.append({
                    "property_id": tid,
                    "success": False,
                    "error": str(e)
                })
        
        # Audit log
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id or "chain",
            "user_id": current_user.id,
            "action": "bulk_rate_update",
            "resource_type": "pricing",
            "details": {
                "room_type": update.room_type,
                "properties_count": len(target_ids),
                "adjustment_type": update.adjustment_type
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "success": True,
            "results": results,
            "total_updated": sum(1 for r in results if r["success"]),
            "total_failed": sum(1 for r in results if not r["success"])
        }
    
    @router.get("/rate-templates")
    async def list_rate_templates(current_user=Depends(get_current_user)):
        """List rate templates"""
        templates = await db.rate_templates.find(
            {"$or": [{"tenant_id": current_user.tenant_id}, {"is_global": True}]},
            {"_id": 0}
        ).to_list(100)
        return {"templates": templates}
    
    @router.post("/rate-templates")
    async def create_rate_template(
        template: RateTemplate,
        current_user=Depends(get_current_user)
    ):
        """Create a rate template"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "is_global": current_user.role == "super_admin",
            "name": template.name,
            "description": template.description,
            "rates": template.rates,
            "currency": template.currency,
            "season": template.season,
            "created_by": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.rate_templates.insert_one(doc)
        return {"success": True, "template": {k: v for k, v in doc.items() if k != '_id'}}
    
    @router.post("/apply-template/{template_id}")
    async def apply_rate_template(
        template_id: str,
        target_properties: List[str] = [],
        current_user=Depends(get_current_user)
    ):
        """Apply a rate template to properties"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        template = await db.rate_templates.find_one({"id": template_id}, {"_id": 0})
        if not template:
            raise HTTPException(status_code=404, detail="Sablon bulunamadi")
        
        all_tenant_ids = await _get_user_tenant_ids(current_user)
        target_ids = target_properties if target_properties else all_tenant_ids
        target_ids = [t for t in target_ids if t in all_tenant_ids]
        
        results = []
        for tid in target_ids:
            for room_type, rate in template["rates"].items():
                result = await db.rooms.update_many(
                    {"tenant_id": tid, "room_type": room_type},
                    {"$set": {
                        "base_rate": rate,
                        "rate": rate,
                        "rate_updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                results.append({
                    "property_id": tid,
                    "room_type": room_type,
                    "new_rate": rate,
                    "rooms_updated": result.modified_count
                })
        
        return {
            "success": True,
            "template_applied": template["name"],
            "results": results
        }
    
    @router.get("/rate-history")
    async def get_rate_history(
        property_id: Optional[str] = None,
        room_type: Optional[str] = None,
        limit: int = 50,
        current_user=Depends(get_current_user)
    ):
        """Get rate change history"""
        query = {}
        tenant_ids = await _get_user_tenant_ids(current_user)
        
        if property_id:
            query["tenant_id"] = property_id
        else:
            query["tenant_id"] = {"$in": tenant_ids}
        
        if room_type:
            query["room_type"] = room_type
        
        history = await db.rate_history.find(
            query, {"_id": 0}
        ).sort("updated_at", -1).to_list(limit)
        
        return {"history": history, "total": len(history)}
    
    return router
