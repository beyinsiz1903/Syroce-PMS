"""
Revenue Management Engine - Demand Analysis, Rate Optimization, Yield Rules, Channel Strategy.
Enterprise-grade dynamic pricing and revenue optimization for hospitality.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from core.database import db


class RevenueManagementEngine:
    """Core revenue management engine with demand analysis, rate optimization, yield rules."""

    # ── DEMAND ANALYSIS ──

    async def get_booking_pace(self, tenant_id: str, target_date: str, lookback_days: int = 30) -> Dict[str, Any]:
        """Analyze booking pace for a target date comparing to historical average."""
        target = date.fromisoformat(target_date)
        today = date.today()
        days_out = (target - today).days

        # Current bookings for target date
        current_bookings = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "check_in": {"$lte": target_date},
            "check_out": {"$gt": target_date},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
        })

        # Historical average for same day-of-week
        historical_counts = []
        for w in range(1, 5):
            hist_date = (target - timedelta(weeks=w)).isoformat()
            count = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_in": {"$lte": hist_date},
                "check_out": {"$gt": hist_date},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
            })
            historical_counts.append(count)

        hist_avg = sum(historical_counts) / len(historical_counts) if historical_counts else 0
        pace_index = round((current_bookings / hist_avg * 100), 1) if hist_avg > 0 else 100.0

        return {
            "target_date": target_date,
            "days_out": days_out,
            "current_bookings": current_bookings,
            "historical_average": round(hist_avg, 1),
            "pace_index": pace_index,
            "pace_status": "ahead" if pace_index > 110 else ("behind" if pace_index < 90 else "on_track"),
        }

    async def get_pickup_trends(self, tenant_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """Analyze reservation pickup trends over a date range."""
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
        trends = []
        cur = sd
        while cur <= ed:
            day_s = cur.isoformat()
            # Bookings made for this stay date
            bookings_for_day = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_in": {"$lte": day_s},
                "check_out": {"$gt": day_s},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
            })
            # Net new bookings created on this date
            new_bookings = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "created_at": {"$gte": day_s, "$lt": (cur + timedelta(days=1)).isoformat()},
            })
            # Cancellations on this date
            cancellations = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "status": "cancelled",
                "updated_at": {"$gte": day_s, "$lt": (cur + timedelta(days=1)).isoformat()},
            })
            trends.append({
                "date": day_s,
                "on_the_books": bookings_for_day,
                "new_bookings": new_bookings,
                "cancellations": cancellations,
                "net_pickup": new_bookings - cancellations,
            })
            cur += timedelta(days=1)

        return {"tenant_id": tenant_id, "start_date": start_date, "end_date": end_date, "trends": trends}

    async def get_occupancy_forecast(self, tenant_id: str, forecast_days: int = 14) -> Dict[str, Any]:
        """Generate occupancy forecast for upcoming days."""
        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        if total_rooms == 0:
            total_rooms = 1

        today = date.today()
        forecast = []
        for i in range(forecast_days):
            target = today + timedelta(days=i)
            day_s = target.isoformat()

            booked = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_in": {"$lte": day_s},
                "check_out": {"$gt": day_s},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            })
            blocked = await db.room_blocks.count_documents({
                "tenant_id": tenant_id,
                "status": "active",
                "start_date": {"$lte": day_s},
                "$or": [{"end_date": None}, {"end_date": {"$gt": day_s}}],
            })
            available = max(total_rooms - booked - blocked, 0)
            occ_pct = round((booked / total_rooms) * 100, 1)

            forecast.append({
                "date": day_s,
                "total_rooms": total_rooms,
                "booked": booked,
                "blocked": blocked,
                "available": available,
                "occupancy_pct": occ_pct,
                "demand_level": "high" if occ_pct > 85 else ("medium" if occ_pct > 60 else "low"),
            })

        return {"tenant_id": tenant_id, "total_rooms": total_rooms, "forecast": forecast}

    async def get_lead_time_analysis(self, tenant_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Analyze booking lead time distribution."""
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "created_at": 1, "check_in": 1, "source": 1},
        ).to_list(5000)

        lead_times = []
        by_source = {}
        for b in bookings:
            created = b.get("created_at", "")[:10]
            checkin = b.get("check_in", "")[:10]
            if created and checkin:
                try:
                    lt = (date.fromisoformat(checkin) - date.fromisoformat(created)).days
                    lead_times.append(lt)
                    src = b.get("source", "direct")
                    by_source.setdefault(src, []).append(lt)
                except Exception:
                    pass

        avg_lt = round(sum(lead_times) / len(lead_times), 1) if lead_times else 0
        buckets = {"same_day": 0, "1_3_days": 0, "4_7_days": 0, "8_14_days": 0, "15_30_days": 0, "30_plus": 0}
        for lt in lead_times:
            if lt == 0:
                buckets["same_day"] += 1
            elif lt <= 3:
                buckets["1_3_days"] += 1
            elif lt <= 7:
                buckets["4_7_days"] += 1
            elif lt <= 14:
                buckets["8_14_days"] += 1
            elif lt <= 30:
                buckets["15_30_days"] += 1
            else:
                buckets["30_plus"] += 1

        source_avg = {src: round(sum(lts) / len(lts), 1) for src, lts in by_source.items() if lts}

        return {
            "period_days": days_back,
            "total_bookings": len(lead_times),
            "average_lead_time": avg_lt,
            "distribution": buckets,
            "by_source": source_avg,
        }

    # ── RATE OPTIMIZATION ──

    async def calculate_ideal_adr(self, tenant_id: str, target_date: str) -> Dict[str, Any]:
        """Calculate ideal ADR based on demand and historical data."""
        forecast = await self.get_occupancy_forecast(tenant_id, 1)
        day_data = forecast["forecast"][0] if forecast["forecast"] else {}
        occ_pct = day_data.get("occupancy_pct", 50)

        # Get current rate plans
        rate_plans = await db.rate_plans.find(
            {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
        ).to_list(20)
        base_rate = rate_plans[0].get("base_price", 100) if rate_plans else 100

        # Get historical ADR
        hist_revenue = await db.folio_charges.find(
            {"tenant_id": tenant_id, "category": "room", "voided": {"$ne": True}},
            {"_id": 0, "amount": 1},
        ).to_list(1000)
        hist_adr = round(sum(c.get("amount", 0) for c in hist_revenue) / len(hist_revenue), 2) if hist_revenue else base_rate

        # Dynamic pricing multiplier based on occupancy
        if occ_pct >= 90:
            multiplier = 1.35
        elif occ_pct >= 80:
            multiplier = 1.20
        elif occ_pct >= 70:
            multiplier = 1.10
        elif occ_pct >= 50:
            multiplier = 1.0
        elif occ_pct >= 30:
            multiplier = 0.90
        else:
            multiplier = 0.80

        ideal_adr = round(base_rate * multiplier, 2)
        revpar_estimate = round(ideal_adr * (occ_pct / 100), 2)

        return {
            "target_date": target_date,
            "current_occupancy_pct": occ_pct,
            "base_rate": base_rate,
            "historical_adr": hist_adr,
            "demand_multiplier": multiplier,
            "ideal_adr": ideal_adr,
            "revpar_estimate": revpar_estimate,
            "recommendation": "increase" if multiplier > 1 else ("decrease" if multiplier < 1 else "maintain"),
        }

    async def get_rate_suggestions(self, tenant_id: str, days: int = 7) -> Dict[str, Any]:
        """Generate rate suggestions for upcoming days."""
        suggestions = []
        today = date.today()
        for i in range(days):
            target = (today + timedelta(days=i)).isoformat()
            adr_data = await self.calculate_ideal_adr(tenant_id, target)
            suggestions.append({
                "date": target,
                "current_occupancy_pct": adr_data["current_occupancy_pct"],
                "ideal_adr": adr_data["ideal_adr"],
                "recommendation": adr_data["recommendation"],
                "revpar_estimate": adr_data["revpar_estimate"],
                "demand_multiplier": adr_data["demand_multiplier"],
            })

        return {"tenant_id": tenant_id, "suggestions": suggestions}

    # ── YIELD RULES ──

    async def get_yield_recommendations(self, tenant_id: str) -> Dict[str, Any]:
        """Generate yield management recommendations: min stay, stop sell, CTA/CTD."""
        forecast = await self.get_occupancy_forecast(tenant_id, 14)
        recommendations = []

        for day in forecast.get("forecast", []):
            occ = day["occupancy_pct"]
            rec = {
                "date": day["date"],
                "occupancy_pct": occ,
                "demand_level": day["demand_level"],
                "min_stay": 1,
                "stop_sell": False,
                "cta": False,
                "ctd": False,
                "notes": [],
            }

            if occ >= 95:
                rec["stop_sell"] = True
                rec["notes"].append("Doluluk %95+: Stop-sell onerisi")
            elif occ >= 85:
                rec["min_stay"] = 2
                rec["cta"] = True
                rec["notes"].append("Yuksek talep: Minimum 2 gece + CTA")
            elif occ >= 75:
                rec["min_stay"] = 2
                rec["notes"].append("Iyi talep: Minimum 2 gece onerisi")
            elif occ < 30:
                rec["ctd"] = True
                rec["notes"].append("Dusuk talep: CTD kaldirma onerisi, promosyon onerilir")

            recommendations.append(rec)

        return {"tenant_id": tenant_id, "recommendations": recommendations}

    # ── CHANNEL STRATEGY ──

    async def get_channel_performance(self, tenant_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Analyze channel mix and rate parity."""
        cutoff = (date.today() - timedelta(days=days_back)).isoformat()
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}, "status": {"$nin": ["cancelled"]}},
            {"_id": 0, "source": 1, "total_amount": 1, "channel": 1},
        ).to_list(5000)

        channel_stats = {}
        for b in bookings:
            ch = b.get("channel") or b.get("source") or "direct"
            if ch not in channel_stats:
                channel_stats[ch] = {"count": 0, "revenue": 0}
            channel_stats[ch]["count"] += 1
            channel_stats[ch]["revenue"] += b.get("total_amount", 0)

        total_bookings = sum(s["count"] for s in channel_stats.values())
        total_revenue = sum(s["revenue"] for s in channel_stats.values())

        channels = []
        for ch, stats in channel_stats.items():
            channels.append({
                "channel": ch,
                "bookings": stats["count"],
                "revenue": round(stats["revenue"], 2),
                "booking_share_pct": round((stats["count"] / total_bookings * 100), 1) if total_bookings > 0 else 0,
                "revenue_share_pct": round((stats["revenue"] / total_revenue * 100), 1) if total_revenue > 0 else 0,
                "avg_booking_value": round(stats["revenue"] / stats["count"], 2) if stats["count"] > 0 else 0,
            })

        channels.sort(key=lambda x: x["revenue"], reverse=True)

        direct_share = next((c["booking_share_pct"] for c in channels if c["channel"] == "direct"), 0)

        return {
            "period_days": days_back,
            "total_bookings": total_bookings,
            "total_revenue": round(total_revenue, 2),
            "channels": channels,
            "direct_booking_share": direct_share,
            "direct_booking_incentive": direct_share < 30,
        }

    # ── REVENUE DASHBOARD DATA ──

    async def get_revenue_dashboard(self, tenant_id: str) -> Dict[str, Any]:
        """Comprehensive revenue dashboard with ADR, RevPAR, trends."""
        today = date.today()
        start_30 = (today - timedelta(days=30)).isoformat()
        today_s = today.isoformat()

        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        if total_rooms == 0:
            total_rooms = 1

        # Today's metrics
        today_booked = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "check_in": {"$lte": today_s},
            "check_out": {"$gt": today_s},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
        })
        today_occ = round((today_booked / total_rooms) * 100, 1)

        # 30-day revenue
        charges = await db.folio_charges.find(
            {"tenant_id": tenant_id, "posted_at": {"$gte": start_30}, "voided": {"$ne": True}},
            {"_id": 0, "amount": 1, "category": 1, "posted_at": 1},
        ).to_list(10000)

        total_revenue = sum(c.get("amount", 0) for c in charges)
        room_revenue = sum(c.get("amount", 0) for c in charges if c.get("category") == "room")

        # Room nights sold in last 30 days
        room_nights = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "check_in": {"$gte": start_30},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
        })

        adr = round(room_revenue / room_nights, 2) if room_nights > 0 else 0
        revpar = round(room_revenue / (total_rooms * 30), 2)

        # Daily revenue trend
        daily_trend = []
        for i in range(30):
            d = (today - timedelta(days=29 - i))
            d_s = d.isoformat()
            d_next = (d + timedelta(days=1)).isoformat()
            day_rev = sum(c.get("amount", 0) for c in charges if d_s <= (c.get("posted_at") or "")[:10] < d_next)
            day_booked = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_in": {"$lte": d_s},
                "check_out": {"$gt": d_s},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
            })
            day_occ = round((day_booked / total_rooms) * 100, 1)
            daily_trend.append({
                "date": d_s,
                "revenue": round(day_rev, 2),
                "occupancy_pct": day_occ,
                "adr": round(day_rev / day_booked, 2) if day_booked > 0 else 0,
                "revpar": round(day_rev / total_rooms, 2),
            })

        # Revenue opportunities
        forecast = await self.get_occupancy_forecast(tenant_id, 7)
        opportunities = []
        for day in forecast.get("forecast", []):
            if day["demand_level"] == "high" and day["available"] > 0:
                opportunities.append({
                    "date": day["date"],
                    "type": "price_increase",
                    "message": f"Yuksek talep, {day['available']} oda musait - fiyat artisi onerilir",
                    "potential_revenue": round(day["available"] * adr * 0.2, 2),
                })
            elif day["demand_level"] == "low" and day["available"] > 5:
                opportunities.append({
                    "date": day["date"],
                    "type": "promotion",
                    "message": f"Dusuk talep, {day['available']} oda bos - promosyon onerilir",
                    "potential_revenue": round(day["available"] * adr * 0.6, 2),
                })

        return {
            "tenant_id": tenant_id,
            "total_rooms": total_rooms,
            "today_occupancy_pct": today_occ,
            "today_booked": today_booked,
            "period_30d": {
                "total_revenue": round(total_revenue, 2),
                "room_revenue": round(room_revenue, 2),
                "room_nights_sold": room_nights,
                "adr": adr,
                "revpar": revpar,
            },
            "daily_trend": daily_trend,
            "opportunities": opportunities,
        }

    # ── AUTO-APPLY RATES ──

    async def apply_rate_suggestion(self, tenant_id: str, target_date: str, new_rate: float, user_id: str) -> Dict[str, Any]:
        """Apply a suggested rate to the rate plan for a specific date."""
        # Store rate override
        override = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "date": target_date,
            "rate": new_rate,
            "applied_by": user_id,
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "source": "revenue_engine",
        }
        await db.revenue_rate_overrides.insert_one(override)

        # Audit
        await db.pms_audit_trail.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "entity_type": "revenue_rate",
            "entity_id": override["id"],
            "action": "rate_override_applied",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {"date": target_date, "new_rate": new_rate},
        })

        return {"success": True, "override_id": override["id"], "date": target_date, "new_rate": new_rate}
