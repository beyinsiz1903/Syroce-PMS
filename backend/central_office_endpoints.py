"""Central Office Dashboard - Chain-wide Consolidated Reporting & KPI
Multi-property data isolation with cross-property reporting"""
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone, timedelta, date
import uuid
import asyncio

router = APIRouter(prefix="/api/central-office", tags=["Central Office Dashboard"])

# ============= ENDPOINTS =============
def create_central_office_routes(db, get_current_user):
    """Create central office dashboard routes"""
    
    async def _require_multi_property_access(current_user):
        """Check if user has multi-property access"""
        if getattr(current_user, 'role', '') == 'super_admin':
            return True
        # Check if user is a chain admin
        chain = await db.hotel_chains.find_one({
            "admin_user_ids": current_user.id
        })
        return chain is not None
    
    async def _get_user_properties(current_user):
        """Get all properties accessible by user"""
        if getattr(current_user, 'role', '') == 'super_admin':
            properties = await db.tenants.find({}, {"_id": 0}).to_list(100)
            return properties
        
        chain = await db.hotel_chains.find_one({"admin_user_ids": current_user.id})
        if chain:
            tenant_ids = chain.get("tenant_ids", [])
            properties = await db.tenants.find(
                {"id": {"$in": tenant_ids}},
                {"_id": 0}
            ).to_list(100)
            return properties
        
        # Single property user
        prop = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
        return [prop] if prop else []
    
    @router.get("/dashboard")
    async def get_central_dashboard(current_user=Depends(get_current_user)):
        """Get chain-wide consolidated dashboard KPIs"""
        properties = await _get_user_properties(current_user)
        tenant_ids = [p["id"] for p in properties]
        
        if not tenant_ids:
            return {"error": "Erisilebilir otel bulunamadi"}
        
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Parallel data fetching
        async def get_property_stats(tid):
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            today_checkins = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_in": {"$gte": today.isoformat(), "$lt": (today + timedelta(days=1)).isoformat()}
            })
            today_checkouts = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_out": {"$gte": today.isoformat(), "$lt": (today + timedelta(days=1)).isoformat()}
            })
            total_guests = await db.guests.count_documents({"tenant_id": tid})
            
            # Revenue from folios
            revenue_pipeline = [
                {"$match": {"tenant_id": tid, "status": {"$in": ["paid", "closed"]}}},
                {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
            ]
            rev_result = await db.folios.aggregate(revenue_pipeline).to_list(1)
            total_revenue = rev_result[0]["total"] if rev_result else 0
            
            occ_rate = round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0
            
            return {
                "tenant_id": tid,
                "total_rooms": total_rooms,
                "occupied_rooms": occupied,
                "available_rooms": total_rooms - occupied,
                "occupancy_rate": occ_rate,
                "today_checkins": today_checkins,
                "today_checkouts": today_checkouts,
                "total_guests": total_guests,
                "total_revenue": total_revenue
            }
        
        # Fetch all property stats in parallel
        stats = await asyncio.gather(*[get_property_stats(tid) for tid in tenant_ids])
        
        # Consolidated KPIs
        total_rooms = sum(s["total_rooms"] for s in stats)
        total_occupied = sum(s["occupied_rooms"] for s in stats)
        total_available = sum(s["available_rooms"] for s in stats)
        total_revenue = sum(s["total_revenue"] for s in stats)
        total_checkins = sum(s["today_checkins"] for s in stats)
        total_checkouts = sum(s["today_checkouts"] for s in stats)
        total_guests = sum(s["total_guests"] for s in stats)
        avg_occ = round((total_occupied / total_rooms * 100), 1) if total_rooms > 0 else 0
        
        return {
            "chain_kpi": {
                "total_properties": len(properties),
                "total_rooms": total_rooms,
                "total_occupied": total_occupied,
                "total_available": total_available,
                "chain_occupancy_rate": avg_occ,
                "total_revenue": total_revenue,
                "today_checkins": total_checkins,
                "today_checkouts": total_checkouts,
                "total_guests": total_guests
            },
            "property_breakdown": [
                {
                    **s,
                    "property_name": next((p["property_name"] for p in properties if p["id"] == s["tenant_id"]), "Unknown")
                }
                for s in stats
            ],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    @router.get("/properties")
    async def list_chain_properties(current_user=Depends(get_current_user)):
        """List all properties in the chain"""
        properties = await _get_user_properties(current_user)
        return {
            "properties": properties,
            "total": len(properties)
        }
    
    @router.get("/occupancy-comparison")
    async def get_occupancy_comparison(
        days: int = 30,
        current_user=Depends(get_current_user)
    ):
        """Compare occupancy across properties"""
        properties = await _get_user_properties(current_user)
        tenant_ids = [p["id"] for p in properties]
        
        comparison = []
        for prop in properties:
            tid = prop["id"]
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            occ_rate = round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0
            
            comparison.append({
                "property_id": tid,
                "property_name": prop.get("property_name", "Unknown"),
                "total_rooms": total_rooms,
                "occupied_rooms": occupied,
                "occupancy_rate": occ_rate,
                "location": prop.get("location", "")
            })
        
        comparison.sort(key=lambda x: x["occupancy_rate"], reverse=True)
        
        return {
            "comparison": comparison,
            "best_performing": comparison[0] if comparison else None,
            "worst_performing": comparison[-1] if comparison else None,
            "chain_average": round(sum(c["occupancy_rate"] for c in comparison) / len(comparison), 1) if comparison else 0
        }
    
    @router.get("/revenue-report")
    async def get_revenue_report(
        period: str = "monthly",  # daily, weekly, monthly
        current_user=Depends(get_current_user)
    ):
        """Cross-property revenue report"""
        properties = await _get_user_properties(current_user)
        
        report = []
        total_chain_revenue = 0
        
        for prop in properties:
            tid = prop["id"]
            # Calculate revenue from folios
            pipeline = [
                {"$match": {"tenant_id": tid}},
                {"$group": {
                    "_id": None,
                    "total_revenue": {"$sum": "$total_amount"},
                    "paid_revenue": {"$sum": {"$cond": [{"$eq": ["$status", "paid"]}, "$total_amount", 0]}},
                    "pending_revenue": {"$sum": {"$cond": [{"$eq": ["$status", "open"]}, "$total_amount", 0]}},
                    "total_transactions": {"$sum": 1}
                }}
            ]
            result = await db.folios.aggregate(pipeline).to_list(1)
            rev = result[0] if result else {"total_revenue": 0, "paid_revenue": 0, "pending_revenue": 0, "total_transactions": 0}
            
            prop_revenue = rev.get("total_revenue", 0)
            total_chain_revenue += prop_revenue
            
            report.append({
                "property_id": tid,
                "property_name": prop.get("property_name", "Unknown"),
                "total_revenue": prop_revenue,
                "paid_revenue": rev.get("paid_revenue", 0),
                "pending_revenue": rev.get("pending_revenue", 0),
                "total_transactions": rev.get("total_transactions", 0)
            })
        
        return {
            "period": period,
            "total_chain_revenue": total_chain_revenue,
            "properties": report,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    @router.post("/chain")
    async def create_hotel_chain(
        chain_name: str,
        tenant_ids: List[str] = [],
        current_user=Depends(get_current_user)
    ):
        """Create a hotel chain (super_admin only)"""
        if getattr(current_user, 'role', '') != 'super_admin':
            raise HTTPException(status_code=403, detail="Sadece super admin zincir olusturabilir")
        
        chain_doc = {
            "id": str(uuid.uuid4()),
            "chain_name": chain_name,
            "tenant_ids": tenant_ids,
            "admin_user_ids": [current_user.id],
            "created_by": current_user.id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.hotel_chains.insert_one(chain_doc)
        
        return {"success": True, "chain": {k: v for k, v in chain_doc.items() if k != '_id'}}
    
    @router.get("/alerts")
    async def get_chain_alerts(current_user=Depends(get_current_user)):
        """Get chain-wide alerts and notifications"""
        properties = await _get_user_properties(current_user)
        
        alerts = []
        for prop in properties:
            tid = prop["id"]
            # Check for low occupancy
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            occ_rate = (occupied / total_rooms * 100) if total_rooms > 0 else 0
            
            if occ_rate < 30:
                alerts.append({
                    "type": "low_occupancy",
                    "severity": "warning",
                    "property": prop.get("property_name"),
                    "message": f"Dusuk doluluk: %{round(occ_rate, 1)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            # Check maintenance issues
            open_tasks = await db.tasks.count_documents({
                "tenant_id": tid,
                "status": {"$in": ["pending", "in_progress"]},
                "task_type": "maintenance"
            })
            if open_tasks > 5:
                alerts.append({
                    "type": "maintenance_backlog",
                    "severity": "info",
                    "property": prop.get("property_name"),
                    "message": f"{open_tasks} acik bakim gorevi",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
        
        return {"alerts": alerts, "total": len(alerts)}
    
    return router
