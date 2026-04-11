"""Cross-Property Guest Profiles - Single guest record across all hotels"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/cross-property/guests", tags=["Cross-Property Guest Profiles"])

# ============= MODELS =============
class GuestMergeRequest(BaseModel):
    primary_guest_id: str
    secondary_guest_ids: List[str]
    merge_strategy: str = "keep_primary"  # 'keep_primary', 'keep_latest', 'manual'

class GlobalGuestSearch(BaseModel):
    query: str  # name, email, phone
    search_across_properties: bool = True

# ============= ENDPOINTS =============
def create_cross_property_guest_routes(db, get_current_user):
    """Create cross-property guest profile routes"""
    
    async def _get_accessible_tenant_ids(current_user):
        if getattr(current_user, 'role', '') == 'super_admin':
            tenants = await db.tenants.find({}, {"id": 1, "_id": 0}).to_list(100)
            return [t["id"] for t in tenants]
        chain = await db.hotel_chains.find_one({"admin_user_ids": current_user.id})
        if chain:
            return chain.get("tenant_ids", [])
        return [current_user.tenant_id] if current_user.tenant_id else []
    
    @router.get("/search")
    async def search_guests_globally(
        q: str = "",
        limit: int = 50,
        current_user=Depends(get_current_user)
    ):
        """Search guests across all accessible properties"""
        tenant_ids = await _get_accessible_tenant_ids(current_user)
        
        query = {"tenant_id": {"$in": tenant_ids}}
        if q:
            query["$or"] = [
                {"name": {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}},
                {"phone": {"$regex": q, "$options": "i"}}
            ]
        
        guests = await db.guests.find(query, {"_id": 0}).sort("name", 1).to_list(limit)
        
        # Group by email to find cross-property guests
        email_groups = {}
        for g in guests:
            email = g.get("email", "")
            if email:
                if email not in email_groups:
                    email_groups[email] = []
                email_groups[email].append(g)
        
        cross_property = {e: gs for e, gs in email_groups.items() if len(gs) > 1}
        
        return {
            "guests": guests,
            "total": len(guests),
            "cross_property_matches": len(cross_property),
            "cross_property_details": {
                email: {
                    "count": len(gs),
                    "properties": [g.get("tenant_id") for g in gs]
                }
                for email, gs in cross_property.items()
            }
        }
    
    @router.get("/profile/{guest_id}")
    async def get_unified_guest_profile(
        guest_id: str,
        current_user=Depends(get_current_user)
    ):
        """Get unified guest profile across all properties"""
        tenant_ids = await _get_accessible_tenant_ids(current_user)
        
        # Find the primary guest record
        guest = await db.guests.find_one(
            {"id": guest_id, "tenant_id": {"$in": tenant_ids}},
            {"_id": 0}
        )
        if not guest:
            raise HTTPException(status_code=404, detail="Misafir bulunamadi")
        
        email = guest.get("email", "")
        
        # Find all records for this guest across properties
        related_records = []
        if email:
            related_records = await db.guests.find(
                {"email": email, "tenant_id": {"$in": tenant_ids}},
                {"_id": 0}
            ).to_list(100)
        
        # Aggregate stay history across properties
        all_bookings = []
        for record in related_records:
            bookings = await db.bookings.find(
                {"guest_id": record["id"], "tenant_id": record["tenant_id"]},
                {"_id": 0}
            ).sort("check_in", -1).to_list(100)
            
            tenant = await db.tenants.find_one({"id": record["tenant_id"]}, {"_id": 0, "property_name": 1})
            for b in bookings:
                b["property_name"] = tenant.get("property_name", "Unknown") if tenant else "Unknown"
            all_bookings.extend(bookings)
        
        # Calculate lifetime value
        total_spent = 0
        total_nights = 0
        for booking in all_bookings:
            total_spent += booking.get("total_amount", booking.get("rate", 0))
            if booking.get("check_in") and booking.get("check_out"):
                try:
                    ci = datetime.fromisoformat(str(booking["check_in"]).replace('Z', '+00:00'))
                    co = datetime.fromisoformat(str(booking["check_out"]).replace('Z', '+00:00'))
                    total_nights += (co - ci).days
                except (ValueError, TypeError):
                    pass
        
        return {
            "guest": guest,
            "cross_property_records": len(related_records),
            "properties_visited": list(set(r.get("tenant_id") for r in related_records)),
            "stay_history": all_bookings[:50],
            "lifetime_stats": {
                "total_stays": len(all_bookings),
                "total_nights": total_nights,
                "total_spent": round(total_spent, 2),
                "properties_count": len(set(r.get("tenant_id") for r in related_records)),
                "first_stay": all_bookings[-1].get("check_in") if all_bookings else None,
                "last_stay": all_bookings[0].get("check_in") if all_bookings else None
            }
        }
    
    @router.post("/merge")
    async def merge_guest_profiles(
        request: GuestMergeRequest,
        current_user=Depends(get_current_user)
    ):
        """Merge duplicate guest profiles"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        primary = await db.guests.find_one({"id": request.primary_guest_id}, {"_id": 0})
        if not primary:
            raise HTTPException(status_code=404, detail="Birincil misafir profili bulunamadi")
        
        merged_count = 0
        for sec_id in request.secondary_guest_ids:
            secondary = await db.guests.find_one({"id": sec_id}, {"_id": 0})
            if not secondary:
                continue
            
            # Update bookings to point to primary guest
            await db.bookings.update_many(
                {"guest_id": sec_id},
                {"$set": {
                    "guest_id": request.primary_guest_id,
                    "original_guest_id": sec_id,
                    "merged_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Update folios
            await db.folios.update_many(
                {"guest_id": sec_id},
                {"$set": {"guest_id": request.primary_guest_id}}
            )
            
            # Mark secondary as merged
            await db.guests.update_one(
                {"id": sec_id},
                {"$set": {
                    "merged_into": request.primary_guest_id,
                    "merged_at": datetime.now(timezone.utc).isoformat(),
                    "is_merged": True
                }}
            )
            
            merged_count += 1
        
        # Audit log
        await db.audit_logs.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "action": "guest_profiles_merged",
            "resource_type": "guest",
            "resource_id": request.primary_guest_id,
            "details": {
                "merged_ids": request.secondary_guest_ids,
                "merged_count": merged_count
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return {
            "success": True,
            "primary_guest_id": request.primary_guest_id,
            "merged_count": merged_count,
            "message": f"{merged_count} misafir profili birlestirildi"
        }
    
    @router.get("/loyalty-summary")
    async def get_cross_property_loyalty(
        current_user=Depends(get_current_user)
    ):
        """Get cross-property loyalty summary"""
        tenant_ids = await _get_accessible_tenant_ids(current_user)
        
        # Find guests with most stays across properties
        pipeline = [
            {"$match": {"tenant_id": {"$in": tenant_ids}}},
            {"$group": {
                "_id": "$email",
                "total_records": {"$sum": 1},
                "properties": {"$addToSet": "$tenant_id"},
                "names": {"$addToSet": "$name"},
                "guest_ids": {"$addToSet": "$id"}
            }},
            {"$match": {"total_records": {"$gt": 1}}},
            {"$sort": {"total_records": -1}},
            {"$limit": 50}
        ]
        
        loyal_guests = await db.guests.aggregate(pipeline).to_list(50)
        
        return {
            "loyal_guests": [
                {
                    "email": g["_id"],
                    "name": g["names"][0] if g["names"] else "Unknown",
                    "total_records": g["total_records"],
                    "properties_count": len(g["properties"]),
                    "guest_ids": g["guest_ids"]
                }
                for g in loyal_guests
            ],
            "total_cross_property_guests": len(loyal_guests)
        }
    
    return router
