"""
Materialized Views System
Pre-computed dashboard metrics for ultra-fast loading
"""
from datetime import datetime, timedelta
from pymongo import ASCENDING, DESCENDING
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MaterializedViewsManager:
    def __init__(self, db):
        self.db = db
        self.views = db.materialized_views
        self.bookings = db.bookings
        self.rooms = db.rooms
        self.guests = db.guests
        self.folios = db.folios
        
    async def setup_indexes(self):
        """Setup indexes for materialized views"""
        try:
            await self.views.create_index([("view_name", ASCENDING)], unique=True)
            await self.views.create_index([("updated_at", DESCENDING)])
            await self.views.create_index([("view_type", ASCENDING)])
            logger.info("Materialized view indexes created")
        except Exception as e:
            logger.error(f"Failed to create materialized view indexes: {e}")
    
    async def refresh_dashboard_metrics(self) -> Dict[str, Any]:
        """Refresh all dashboard metrics"""
        try:
            start_time = datetime.utcnow()
            
            # Calculate all metrics in parallel
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today - timedelta(days=1)
            today - timedelta(days=7)
            month_ago = today - timedelta(days=30)
            
            # Occupancy metrics
            total_rooms = await self.rooms.count_documents({"status": {"$ne": "out_of_order"}})
            occupied_rooms = await self.bookings.count_documents({
                "status": "checked_in",
                "check_in": {"$lte": datetime.utcnow()},
                "check_out": {"$gte": datetime.utcnow()}
            })
            occupancy_rate = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
            
            # Today's stats
            today_arrivals = await self.bookings.count_documents({
                "check_in": {
                    "$gte": today,
                    "$lt": today + timedelta(days=1)
                }
            })
            
            today_departures = await self.bookings.count_documents({
                "check_out": {
                    "$gte": today,
                    "$lt": today + timedelta(days=1)
                }
            })
            
            # Revenue metrics
            revenue_pipeline = [
                {
                    "$match": {
                        "created_at": {"$gte": today}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_revenue": {"$sum": "$balance"},
                        "room_revenue": {
                            "$sum": {
                                "$cond": [
                                    {"$eq": ["$folio_type", "guest"]},
                                    "$balance",
                                    0
                                ]
                            }
                        }
                    }
                }
            ]
            revenue_result = await self.folios.aggregate(revenue_pipeline).to_list(1)
            today_revenue = revenue_result[0]["total_revenue"] if revenue_result else 0
            
            # ADR calculation
            adr_pipeline = [
                {
                    "$match": {
                        "status": "checked_in",
                        "check_in": {"$gte": month_ago}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "avg_rate": {"$avg": "$total_amount"}
                    }
                }
            ]
            adr_result = await self.bookings.aggregate(adr_pipeline).to_list(1)
            adr = round(adr_result[0]["avg_rate"], 2) if adr_result else 0
            
            # RevPAR
            revpar = round(adr * (occupancy_rate / 100), 2)
            
            # Guest metrics
            total_guests = await self.guests.count_documents({})
            vip_guests = await self.guests.count_documents({"tags": "vip"})
            
            # Booking metrics
            total_bookings = await self.bookings.count_documents({})
            active_bookings = await self.bookings.count_documents({
                "status": {"$in": ["confirmed", "checked_in"]}
            })
            
            # Weekly trend
            weekly_occupancy = []
            for i in range(7):
                day = today - timedelta(days=i)
                day_occupied = await self.bookings.count_documents({
                    "status": "checked_in",
                    "check_in": {"$lte": day},
                    "check_out": {"$gte": day}
                })
                weekly_occupancy.append({
                    "date": day.isoformat(),
                    "occupancy": round((day_occupied / total_rooms * 100), 2) if total_rooms > 0 else 0,
                    "occupied_rooms": day_occupied
                })
            
            # Monthly revenue trend
            monthly_revenue = []
            for i in range(30):
                day = today - timedelta(days=i)
                day_end = day + timedelta(days=1)
                day_revenue_result = await self.folios.aggregate([
                    {
                        "$match": {
                            "created_at": {"$gte": day, "$lt": day_end}
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "revenue": {"$sum": "$balance"}
                        }
                    }
                ]).to_list(1)
                day_revenue = day_revenue_result[0]["revenue"] if day_revenue_result else 0
                monthly_revenue.append({
                    "date": day.isoformat(),
                    "revenue": round(day_revenue, 2)
                })
            
            # Compile metrics
            metrics = {
                "view_name": "dashboard_metrics",
                "view_type": "dashboard",
                "updated_at": datetime.utcnow(),
                "refresh_duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000,
                "data": {
                    "occupancy": {
                        "rate": round(occupancy_rate, 2),
                        "occupied_rooms": occupied_rooms,
                        "total_rooms": total_rooms,
                        "available_rooms": total_rooms - occupied_rooms
                    },
                    "today": {
                        "arrivals": today_arrivals,
                        "departures": today_departures,
                        "revenue": round(today_revenue, 2)
                    },
                    "financial": {
                        "adr": adr,
                        "revpar": revpar,
                        "today_revenue": round(today_revenue, 2)
                    },
                    "guests": {
                        "total": total_guests,
                        "vip": vip_guests
                    },
                    "bookings": {
                        "total": total_bookings,
                        "active": active_bookings
                    },
                    "trends": {
                        "weekly_occupancy": weekly_occupancy,
                        "monthly_revenue": monthly_revenue[:7]  # Last 7 days for dashboard
                    }
                }
            }
            
            # Upsert to database
            await self.views.update_one(
                {"view_name": "dashboard_metrics"},
                {"$set": metrics},
                upsert=True
            )
            
            logger.info(f"Dashboard metrics refreshed in {metrics['refresh_duration_ms']}ms")
            return {
                "success": True,
                "refresh_duration_ms": metrics['refresh_duration_ms'],
                "metrics": metrics["data"]
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh dashboard metrics: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_view(self, view_name: str, max_age_seconds: int = 300) -> Optional[Dict[str, Any]]:
        """
        Get materialized view with freshness check
        
        Args:
            view_name: Name of the view
            max_age_seconds: Maximum age in seconds (default 5 minutes)
            
        Returns:
            View data or None if too old
        """
        try:
            view = await self.views.find_one({"view_name": view_name})
            
            if not view:
                return None
            
            # Check freshness
            updated_at = view.get("updated_at")
            if updated_at:
                age = (datetime.utcnow() - updated_at).total_seconds()
                if age > max_age_seconds:
                    logger.warning(f"View {view_name} is stale ({age}s old)")
                    return None
            
            return view.get("data")
            
        except Exception as e:
            logger.error(f"Failed to get view {view_name}: {e}")
            return None
    
    async def refresh_all_views(self) -> Dict[str, Any]:
        """Refresh all materialized views"""
        results = {
            "dashboard_metrics": await self.refresh_dashboard_metrics()
        }
        
        return {
            "success": all(r.get("success", False) for r in results.values()),
            "results": results,
            "total_duration_ms": sum(r.get("refresh_duration_ms", 0) for r in results.values())
        }
    
    async def get_view_stats(self) -> Dict[str, Any]:
        """Get statistics about all views"""
        try:
            views = await self.views.find({}).to_list(None)
            
            stats = []
            for view in views:
                updated_at = view.get("updated_at")
                age_seconds = (datetime.utcnow() - updated_at).total_seconds() if updated_at else None
                
                stats.append({
                    "view_name": view.get("view_name"),
                    "view_type": view.get("view_type"),
                    "updated_at": updated_at.isoformat() if updated_at else None,
                    "age_seconds": round(age_seconds, 2) if age_seconds else None,
                    "refresh_duration_ms": view.get("refresh_duration_ms")
                })
            
            return {
                "total_views": len(stats),
                "views": stats
            }
            
        except Exception as e:
            logger.error(f"Failed to get view stats: {e}")
            return {"error": str(e)}
