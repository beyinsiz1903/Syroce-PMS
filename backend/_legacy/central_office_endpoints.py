"""Central Office Dashboard V2 - Enhanced Chain-wide Analytics
================================================================
Gelişmiş merkez ofis dashboard:
- ADR, RevPAR, GOP, GOPPAR metrikleri
- 7/30/90 günlük trend analizi
- Bütçe vs gerçekleşen karşılaştırma
- Property sağlık skoru
- Departman bazlı karşılaştırma
- Chain-wide alert sistemi
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import asyncio
import statistics

router = APIRouter(prefix="/api/central-office", tags=["Central Office Dashboard"])

# ============= MODELS =============
class PropertyHealthScore(BaseModel):
    """Otel sağlık skoru"""
    property_id: str
    property_name: str
    overall_score: float = 0.0
    occupancy_score: float = 0.0
    revenue_score: float = 0.0
    guest_satisfaction_score: float = 0.0
    operational_score: float = 0.0
    compliance_score: float = 0.0

class ChainBudget(BaseModel):
    """Zincir bütçe hedefi"""
    property_id: str
    period: str  # monthly, quarterly, yearly
    revenue_target: float
    occupancy_target: float
    adr_target: float
    expense_budget: float

class TrendDataPoint(BaseModel):
    """Trend veri noktası"""
    date: str
    value: float
    label: Optional[str] = None

# ============= ENDPOINTS =============
def create_central_office_routes(db, get_current_user):
    """Create enhanced central office dashboard routes"""
    
    async def _require_multi_property_access(current_user):
        """Check if user has multi-property access"""
        if getattr(current_user, 'role', '') == 'super_admin':
            return True
        chain = await db.hotel_chains.find_one({"admin_user_ids": current_user.id})
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
                {"id": {"$in": tenant_ids}}, {"_id": 0}
            ).to_list(100)
            return properties
        
        prop = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
        return [prop] if prop else []
    
    # ============= CONSOLIDATED DASHBOARD =============
    @router.get("/dashboard")
    async def get_central_dashboard(current_user=Depends(get_current_user)):
        """Get chain-wide consolidated dashboard with enhanced KPIs"""
        properties = await _get_user_properties(current_user)
        tenant_ids = [p["id"] for p in properties]
        
        if not tenant_ids:
            return {"error": "Erişilebilir otel bulunamadı"}
        
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        async def get_property_stats(tid):
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            out_of_order = await db.rooms.count_documents({"tenant_id": tid, "status": {"$in": ["out_of_order", "maintenance"]}})
            available = total_rooms - occupied - out_of_order
            
            today_checkins = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_in": {"$gte": today.isoformat(), "$lt": (today + timedelta(days=1)).isoformat()}
            })
            today_checkouts = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_out": {"$gte": today.isoformat(), "$lt": (today + timedelta(days=1)).isoformat()}
            })
            total_guests = await db.guests.count_documents({"tenant_id": tid})
            
            # Revenue hesaplama
            rev_pipeline = [
                {"$match": {"tenant_id": tid, "status": {"$in": ["paid", "closed"]}}},
                {"$group": {"_id": None, "total": {"$sum": "$total_amount"}, "count": {"$sum": 1}}}
            ]
            rev_result = await db.folios.aggregate(rev_pipeline).to_list(1)
            total_revenue = rev_result[0]["total"] if rev_result else 0
            transaction_count = rev_result[0]["count"] if rev_result else 0
            
            # ADR (Average Daily Rate)
            sellable_rooms = total_rooms - out_of_order
            occ_rate = round((occupied / sellable_rooms * 100), 1) if sellable_rooms > 0 else 0
            adr = round(total_revenue / occupied, 2) if occupied > 0 else 0
            revpar = round(total_revenue / sellable_rooms, 2) if sellable_rooms > 0 else 0
            
            # Açık görevler
            open_tasks = await db.tasks.count_documents({
                "tenant_id": tid, "status": {"$in": ["pending", "in_progress"]}
            })
            
            # Bugünkü gelir
            today_rev_pipeline = [
                {"$match": {
                    "tenant_id": tid,
                    "created_at": {"$gte": today.isoformat(), "$lt": (today + timedelta(days=1)).isoformat()}
                }},
                {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
            ]
            today_rev = await db.folios.aggregate(today_rev_pipeline).to_list(1)
            today_revenue = today_rev[0]["total"] if today_rev else 0
            
            return {
                "tenant_id": tid,
                "total_rooms": total_rooms,
                "occupied_rooms": occupied,
                "available_rooms": available,
                "out_of_order_rooms": out_of_order,
                "sellable_rooms": sellable_rooms,
                "occupancy_rate": occ_rate,
                "today_checkins": today_checkins,
                "today_checkouts": today_checkouts,
                "total_guests": total_guests,
                "total_revenue": total_revenue,
                "today_revenue": today_revenue,
                "adr": adr,
                "revpar": revpar,
                "transaction_count": transaction_count,
                "open_tasks": open_tasks
            }
        
        stats = await asyncio.gather(*[get_property_stats(tid) for tid in tenant_ids])
        
        # Consolidated KPIs
        total_rooms = sum(s["total_rooms"] for s in stats)
        total_occupied = sum(s["occupied_rooms"] for s in stats)
        total_available = sum(s["available_rooms"] for s in stats)
        total_ooo = sum(s["out_of_order_rooms"] for s in stats)
        total_sellable = sum(s["sellable_rooms"] for s in stats)
        total_revenue = sum(s["total_revenue"] for s in stats)
        today_revenue = sum(s["today_revenue"] for s in stats)
        total_checkins = sum(s["today_checkins"] for s in stats)
        total_checkouts = sum(s["today_checkouts"] for s in stats)
        total_guests = sum(s["total_guests"] for s in stats)
        total_tasks = sum(s["open_tasks"] for s in stats)
        
        chain_occ = round((total_occupied / total_sellable * 100), 1) if total_sellable > 0 else 0
        chain_adr = round(total_revenue / total_occupied, 2) if total_occupied > 0 else 0
        chain_revpar = round(total_revenue / total_sellable, 2) if total_sellable > 0 else 0
        
        return {
            "chain_kpi": {
                "total_properties": len(properties),
                "total_rooms": total_rooms,
                "total_occupied": total_occupied,
                "total_available": total_available,
                "out_of_order_rooms": total_ooo,
                "sellable_rooms": total_sellable,
                "chain_occupancy_rate": chain_occ,
                "total_revenue": total_revenue,
                "today_revenue": today_revenue,
                "chain_adr": chain_adr,
                "chain_revpar": chain_revpar,
                "today_checkins": total_checkins,
                "today_checkouts": total_checkouts,
                "total_guests": total_guests,
                "open_tasks": total_tasks
            },
            "property_breakdown": [
                {
                    **s,
                    "property_name": next(
                        (p.get("property_name", "Unknown") for p in properties if p["id"] == s["tenant_id"]),
                        "Unknown"
                    )
                }
                for s in stats
            ],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    # ============= PROPERTIES =============
    @router.get("/properties")
    async def list_chain_properties(current_user=Depends(get_current_user)):
        """List all properties in the chain with details"""
        properties = await _get_user_properties(current_user)
        
        enriched = []
        for prop in properties:
            tid = prop["id"]
            room_count = await db.rooms.count_documents({"tenant_id": tid})
            guest_count = await db.guests.count_documents({"tenant_id": tid})
            user_count = await db.users.count_documents({"tenant_id": tid})
            
            enriched.append({
                **prop,
                "room_count": room_count,
                "guest_count": guest_count,
                "user_count": user_count
            })
        
        return {"properties": enriched, "total": len(enriched)}
    
    # ============= OCCUPANCY COMPARISON =============
    @router.get("/occupancy-comparison")
    async def get_occupancy_comparison(
        days: int = 30,
        current_user=Depends(get_current_user)
    ):
        """Compare occupancy across properties with ranking"""
        properties = await _get_user_properties(current_user)
        
        comparison = []
        for prop in properties:
            tid = prop["id"]
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            occ_rate = round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0
            
            # Son N günlük booking sayısı
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            recent_bookings = await db.bookings.count_documents({
                "tenant_id": tid,
                "created_at": {"$gte": cutoff}
            })
            
            comparison.append({
                "property_id": tid,
                "property_name": prop.get("property_name", "Unknown"),
                "total_rooms": total_rooms,
                "occupied_rooms": occupied,
                "occupancy_rate": occ_rate,
                "location": prop.get("location", ""),
                "recent_bookings": recent_bookings
            })
        
        comparison.sort(key=lambda x: x["occupancy_rate"], reverse=True)
        
        # Ranking ekle
        for i, c in enumerate(comparison):
            c["rank"] = i + 1
        
        occ_rates = [c["occupancy_rate"] for c in comparison if c["occupancy_rate"] > 0]
        
        return {
            "comparison": comparison,
            "best_performing": comparison[0] if comparison else None,
            "worst_performing": comparison[-1] if comparison else None,
            "chain_average": round(statistics.mean(occ_rates), 1) if occ_rates else 0,
            "chain_median": round(statistics.median(occ_rates), 1) if occ_rates else 0,
            "chain_std_dev": round(statistics.stdev(occ_rates), 1) if len(occ_rates) > 1 else 0,
            "period_days": days
        }
    
    # ============= REVENUE REPORT =============
    @router.get("/revenue-report")
    async def get_revenue_report(
        period: str = "monthly",
        current_user=Depends(get_current_user)
    ):
        """Cross-property revenue report with ADR/RevPAR"""
        properties = await _get_user_properties(current_user)
        
        report = []
        total_chain_revenue = 0
        total_chain_rooms = 0
        total_chain_occupied = 0
        
        for prop in properties:
            tid = prop["id"]
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            
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
            rev = result[0] if result else {
                "total_revenue": 0, "paid_revenue": 0, "pending_revenue": 0, "total_transactions": 0
            }
            
            prop_revenue = rev.get("total_revenue", 0)
            total_chain_revenue += prop_revenue
            total_chain_rooms += total_rooms
            total_chain_occupied += occupied
            
            adr = round(prop_revenue / occupied, 2) if occupied > 0 else 0
            revpar = round(prop_revenue / total_rooms, 2) if total_rooms > 0 else 0
            
            report.append({
                "property_id": tid,
                "property_name": prop.get("property_name", "Unknown"),
                "total_rooms": total_rooms,
                "occupied_rooms": occupied,
                "total_revenue": prop_revenue,
                "paid_revenue": rev.get("paid_revenue", 0),
                "pending_revenue": rev.get("pending_revenue", 0),
                "total_transactions": rev.get("total_transactions", 0),
                "adr": adr,
                "revpar": revpar,
                "revenue_share_pct": 0  # Will be calculated below
            })
        
        # Revenue share hesapla
        for r in report:
            r["revenue_share_pct"] = round(
                (r["total_revenue"] / total_chain_revenue * 100), 1
            ) if total_chain_revenue > 0 else 0
        
        chain_adr = round(total_chain_revenue / total_chain_occupied, 2) if total_chain_occupied > 0 else 0
        chain_revpar = round(total_chain_revenue / total_chain_rooms, 2) if total_chain_rooms > 0 else 0
        
        return {
            "period": period,
            "total_chain_revenue": total_chain_revenue,
            "chain_adr": chain_adr,
            "chain_revpar": chain_revpar,
            "total_chain_rooms": total_chain_rooms,
            "total_chain_occupied": total_chain_occupied,
            "properties": sorted(report, key=lambda x: x["total_revenue"], reverse=True),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    # ============= TREND ANALYSIS =============
    @router.get("/trends")
    async def get_chain_trends(
        metric: str = "occupancy",
        days: int = 30,
        current_user=Depends(get_current_user)
    ):
        """Zincir genelinde trend analizi (7/30/90 gün)"""
        properties = await _get_user_properties(current_user)
        tenant_ids = [p["id"] for p in properties]
        
        if not tenant_ids:
            return {"error": "Erişilebilir otel bulunamadı"}
        
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        trend_data = []
        
        for day_offset in range(days, 0, -1):
            target_date = today - timedelta(days=day_offset)
            date_str = target_date.strftime("%Y-%m-%d")
            next_date = target_date + timedelta(days=1)
            
            if metric == "occupancy":
                # Booking bazlı doluluk
                bookings = await db.bookings.count_documents({
                    "tenant_id": {"$in": tenant_ids},
                    "check_in": {"$lte": next_date.isoformat()},
                    "check_out": {"$gte": target_date.isoformat()},
                    "status": {"$in": ["confirmed", "checked_in", "completed"]}
                })
                total_rooms = 0
                for tid in tenant_ids:
                    total_rooms += await db.rooms.count_documents({"tenant_id": tid})
                
                value = round((bookings / total_rooms * 100), 1) if total_rooms > 0 else 0
                trend_data.append({"date": date_str, "value": value, "label": f"%{value}"})
                
            elif metric == "revenue":
                pipeline = [
                    {"$match": {
                        "tenant_id": {"$in": tenant_ids},
                        "created_at": {"$gte": target_date.isoformat(), "$lt": next_date.isoformat()}
                    }},
                    {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
                ]
                result = await db.folios.aggregate(pipeline).to_list(1)
                value = result[0]["total"] if result else 0
                trend_data.append({"date": date_str, "value": round(value, 2), "label": f"₺{value:,.0f}"})
                
            elif metric == "bookings":
                bookings = await db.bookings.count_documents({
                    "tenant_id": {"$in": tenant_ids},
                    "created_at": {"$gte": target_date.isoformat(), "$lt": next_date.isoformat()}
                })
                trend_data.append({"date": date_str, "value": bookings, "label": str(bookings)})
                
            elif metric == "guests":
                guests = await db.guests.count_documents({
                    "tenant_id": {"$in": tenant_ids},
                    "created_at": {"$gte": target_date.isoformat(), "$lt": next_date.isoformat()}
                })
                trend_data.append({"date": date_str, "value": guests, "label": str(guests)})
        
        # Trend hesapla
        values = [d["value"] for d in trend_data if d["value"] > 0]
        avg_value = round(statistics.mean(values), 2) if values else 0
        max_value = max(values) if values else 0
        min_value = min(values) if values else 0
        
        # Trend yönü
        if len(values) >= 2:
            first_half = statistics.mean(values[:len(values)//2])
            second_half = statistics.mean(values[len(values)//2:])
            if second_half > first_half * 1.05:
                trend_direction = "up"
            elif second_half < first_half * 0.95:
                trend_direction = "down"
            else:
                trend_direction = "stable"
        else:
            trend_direction = "insufficient_data"
        
        return {
            "metric": metric,
            "period_days": days,
            "data_points": trend_data,
            "summary": {
                "average": avg_value,
                "max": max_value,
                "min": min_value,
                "trend_direction": trend_direction,
                "data_points_count": len(trend_data)
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    # ============= PROPERTY HEALTH SCORE =============
    @router.get("/property-health")
    async def get_property_health_scores(current_user=Depends(get_current_user)):
        """Her otel için sağlık skoru hesapla"""
        properties = await _get_user_properties(current_user)
        
        health_scores = []
        for prop in properties:
            tid = prop["id"]
            
            # Doluluk skoru (0-25)
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            occ_rate = (occupied / total_rooms * 100) if total_rooms > 0 else 0
            occ_score = min(25, occ_rate / 4)  # %100 doluluk = 25 puan
            
            # Gelir skoru (0-25)
            rev_pipeline = [
                {"$match": {"tenant_id": tid, "status": {"$in": ["paid", "closed"]}}},
                {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
            ]
            rev_result = await db.folios.aggregate(rev_pipeline).to_list(1)
            total_revenue = rev_result[0]["total"] if rev_result else 0
            rev_score = min(25, (total_revenue / max(total_rooms * 100, 1)) * 25 / 100) if total_rooms > 0 else 0
            
            # Operasyonel skor (0-25)
            open_tasks = await db.tasks.count_documents({
                "tenant_id": tid, "status": {"$in": ["pending", "in_progress"]}
            })
            completed_tasks = await db.tasks.count_documents({
                "tenant_id": tid, "status": "completed"
            })
            total_tasks = open_tasks + completed_tasks
            task_completion = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 100
            ops_score = task_completion / 4  # %100 tamamlama = 25 puan
            
            # Uyumluluk skoru (0-25)
            guests = await db.guests.count_documents({"tenant_id": tid})
            consents = len(await db.gdpr_consents.distinct("guest_id", {"tenant_id": tid}))
            consent_rate = (consents / guests * 100) if guests > 0 else 0
            
            has_2fa = await db.tenant_security_policies.find_one(
                {"tenant_id": tid, "require_2fa": True}
            ) is not None
            has_ip_rules = await db.ip_rules.count_documents({"tenant_id": tid}) > 0
            
            compliance_items = [
                consent_rate >= 80,
                has_2fa,
                has_ip_rules,
                True,  # Audit trail always active
                True   # GDPR module active
            ]
            compliance_score = (sum(1 for c in compliance_items if c) / len(compliance_items)) * 25
            
            overall = round(occ_score + rev_score + ops_score + compliance_score, 1)
            
            health_scores.append({
                "property_id": tid,
                "property_name": prop.get("property_name", "Unknown"),
                "overall_score": overall,
                "max_score": 100,
                "grade": "A" if overall >= 80 else "B" if overall >= 60 else "C" if overall >= 40 else "D",
                "breakdown": {
                    "occupancy": {"score": round(occ_score, 1), "max": 25, "details": f"%{round(occ_rate, 1)} doluluk"},
                    "revenue": {"score": round(rev_score, 1), "max": 25, "details": f"₺{total_revenue:,.0f} toplam gelir"},
                    "operations": {"score": round(ops_score, 1), "max": 25, "details": f"%{round(task_completion, 1)} görev tamamlama"},
                    "compliance": {"score": round(compliance_score, 1), "max": 25, "details": f"%{round(consent_rate, 1)} KVKK uyum"}
                }
            })
        
        health_scores.sort(key=lambda x: x["overall_score"], reverse=True)
        
        avg_score = round(
            statistics.mean([h["overall_score"] for h in health_scores]), 1
        ) if health_scores else 0
        
        return {
            "chain_average_score": avg_score,
            "properties": health_scores,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    # ============= BUDGET VS ACTUAL =============
    @router.get("/budget-tracking")
    async def get_budget_tracking(current_user=Depends(get_current_user)):
        """Bütçe vs gerçekleşen karşılaştırma"""
        properties = await _get_user_properties(current_user)
        
        tracking = []
        for prop in properties:
            tid = prop["id"]
            
            # Bütçe hedefi getir
            budget = await db.property_budgets.find_one(
                {"tenant_id": tid, "period": "monthly"}, {"_id": 0}
            )
            
            # Gerçekleşen veriler
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            occ_rate = round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0
            
            rev_pipeline = [
                {"$match": {"tenant_id": tid}},
                {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}}
            ]
            rev_result = await db.folios.aggregate(rev_pipeline).to_list(1)
            actual_revenue = rev_result[0]["total"] if rev_result else 0
            actual_adr = round(actual_revenue / occupied, 2) if occupied > 0 else 0
            
            # Varsayılan bütçe (yoksa)
            revenue_target = budget.get("revenue_target", total_rooms * 200 * 30) if budget else total_rooms * 200 * 30
            occ_target = budget.get("occupancy_target", 75) if budget else 75
            adr_target = budget.get("adr_target", 200) if budget else 200
            
            tracking.append({
                "property_id": tid,
                "property_name": prop.get("property_name", "Unknown"),
                "revenue": {
                    "target": revenue_target,
                    "actual": actual_revenue,
                    "variance": round(actual_revenue - revenue_target, 2),
                    "variance_pct": round(((actual_revenue - revenue_target) / revenue_target * 100), 1) if revenue_target > 0 else 0,
                    "on_track": actual_revenue >= revenue_target * 0.9
                },
                "occupancy": {
                    "target": occ_target,
                    "actual": occ_rate,
                    "variance": round(occ_rate - occ_target, 1),
                    "on_track": occ_rate >= occ_target * 0.9
                },
                "adr": {
                    "target": adr_target,
                    "actual": actual_adr,
                    "variance": round(actual_adr - adr_target, 2),
                    "on_track": actual_adr >= adr_target * 0.9
                }
            })
        
        return {
            "tracking": tracking,
            "chain_summary": {
                "revenue_on_track": sum(1 for t in tracking if t["revenue"]["on_track"]),
                "occupancy_on_track": sum(1 for t in tracking if t["occupancy"]["on_track"]),
                "adr_on_track": sum(1 for t in tracking if t["adr"]["on_track"]),
                "total_properties": len(tracking)
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    # ============= SET BUDGET =============
    @router.post("/budget")
    async def set_property_budget(
        property_id: str,
        revenue_target: float,
        occupancy_target: float = 75.0,
        adr_target: float = 200.0,
        expense_budget: float = 0,
        period: str = "monthly",
        current_user=Depends(get_current_user)
    ):
        """Otel bütçe hedefi belirle"""
        if current_user.role not in ["admin", "super_admin"]:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
        
        budget_doc = {
            "tenant_id": property_id,
            "period": period,
            "revenue_target": revenue_target,
            "occupancy_target": occupancy_target,
            "adr_target": adr_target,
            "expense_budget": expense_budget,
            "set_by": current_user.id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.property_budgets.update_one(
            {"tenant_id": property_id, "period": period},
            {"$set": budget_doc},
            upsert=True
        )
        
        return {"success": True, "message": "Bütçe hedefi kaydedildi", "budget": budget_doc}
    
    # ============= CHAIN CREATE =============
    @router.post("/chain")
    async def create_hotel_chain(
        chain_name: str,
        tenant_ids: List[str] = [],
        current_user=Depends(get_current_user)
    ):
        """Create a hotel chain (super_admin only)"""
        if getattr(current_user, 'role', '') != 'super_admin':
            raise HTTPException(status_code=403, detail="Sadece super admin zincir oluşturabilir")
        
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
    
    # ============= ALERTS =============
    @router.get("/alerts")
    async def get_chain_alerts(current_user=Depends(get_current_user)):
        """Get chain-wide alerts with severity levels"""
        properties = await _get_user_properties(current_user)
        
        alerts = []
        for prop in properties:
            tid = prop["id"]
            prop_name = prop.get("property_name", "Unknown")
            
            # Düşük doluluk kontrolü
            total_rooms = await db.rooms.count_documents({"tenant_id": tid})
            occupied = await db.rooms.count_documents({"tenant_id": tid, "status": "occupied"})
            occ_rate = (occupied / total_rooms * 100) if total_rooms > 0 else 0
            
            if occ_rate < 20:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "critical_low_occupancy",
                    "severity": "critical",
                    "property": prop_name,
                    "property_id": tid,
                    "message": f"Kritik düşük doluluk: %{round(occ_rate, 1)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            elif occ_rate < 40:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "low_occupancy",
                    "severity": "warning",
                    "property": prop_name,
                    "property_id": tid,
                    "message": f"Düşük doluluk: %{round(occ_rate, 1)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            # Bakım birikimi
            open_maintenance = await db.tasks.count_documents({
                "tenant_id": tid,
                "status": {"$in": ["pending", "in_progress"]},
                "task_type": "maintenance"
            })
            if open_maintenance > 10:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "maintenance_backlog_critical",
                    "severity": "critical",
                    "property": prop_name,
                    "property_id": tid,
                    "message": f"{open_maintenance} açık bakım görevi (kritik birikim)",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            elif open_maintenance > 5:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "maintenance_backlog",
                    "severity": "warning",
                    "property": prop_name,
                    "property_id": tid,
                    "message": f"{open_maintenance} açık bakım görevi",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            # Out of order oda kontrolü
            ooo_rooms = await db.rooms.count_documents({"tenant_id": tid, "status": {"$in": ["out_of_order", "maintenance"]}})
            if ooo_rooms > total_rooms * 0.1 and total_rooms > 0:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "high_ooo_rooms",
                    "severity": "warning",
                    "property": prop_name,
                    "property_id": tid,
                    "message": f"{ooo_rooms} oda servis dışı (%{round(ooo_rooms/total_rooms*100, 1)})",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            # KVKK uyum kontrolü
            total_guests = await db.guests.count_documents({"tenant_id": tid})
            consented = len(await db.gdpr_consents.distinct("guest_id", {"tenant_id": tid}))
            if total_guests > 0 and consented < total_guests * 0.5:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "type": "low_gdpr_compliance",
                    "severity": "warning",
                    "property": prop_name,
                    "property_id": tid,
                    "message": f"KVKK onay oranı düşük: %{round(consented/total_guests*100, 1)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
        
        # Severity'ye göre sırala
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda x: severity_order.get(x["severity"], 3))
        
        return {
            "alerts": alerts,
            "total": len(alerts),
            "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
            "warning_count": sum(1 for a in alerts if a["severity"] == "warning"),
            "info_count": sum(1 for a in alerts if a["severity"] == "info")
        }
    
    # ============= DEPARTMENT COMPARISON =============
    @router.get("/department-comparison")
    async def get_department_comparison(current_user=Depends(get_current_user)):
        """Oteller arası departman performans karşılaştırması"""
        properties = await _get_user_properties(current_user)
        
        departments = []
        for prop in properties:
            tid = prop["id"]
            prop_name = prop.get("property_name", "Unknown")
            
            # Housekeeping
            hk_total = await db.tasks.count_documents({"tenant_id": tid, "task_type": "housekeeping"})
            hk_completed = await db.tasks.count_documents({"tenant_id": tid, "task_type": "housekeeping", "status": "completed"})
            hk_rate = round((hk_completed / hk_total * 100), 1) if hk_total > 0 else 0
            
            # Maintenance
            mt_total = await db.tasks.count_documents({"tenant_id": tid, "task_type": "maintenance"})
            mt_completed = await db.tasks.count_documents({"tenant_id": tid, "task_type": "maintenance", "status": "completed"})
            mt_rate = round((mt_completed / mt_total * 100), 1) if mt_total > 0 else 0
            
            # Front desk (check-in/out efficiency)
            total_bookings = await db.bookings.count_documents({"tenant_id": tid})
            completed_bookings = await db.bookings.count_documents({"tenant_id": tid, "status": "completed"})
            fd_rate = round((completed_bookings / total_bookings * 100), 1) if total_bookings > 0 else 0
            
            departments.append({
                "property_id": tid,
                "property_name": prop_name,
                "housekeeping": {"completion_rate": hk_rate, "total_tasks": hk_total, "completed": hk_completed},
                "maintenance": {"completion_rate": mt_rate, "total_tasks": mt_total, "completed": mt_completed},
                "front_desk": {"completion_rate": fd_rate, "total_bookings": total_bookings, "completed": completed_bookings}
            })
        
        return {
            "departments": departments,
            "chain_averages": {
                "housekeeping": round(statistics.mean([d["housekeeping"]["completion_rate"] for d in departments]), 1) if departments else 0,
                "maintenance": round(statistics.mean([d["maintenance"]["completion_rate"] for d in departments]), 1) if departments else 0,
                "front_desk": round(statistics.mean([d["front_desk"]["completion_rate"] for d in departments]), 1) if departments else 0
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    return router
