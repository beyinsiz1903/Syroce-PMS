"""
Revenue ML - Machine learning models for demand forecasting, rate elasticity,
booking probability, and cancellation prediction.
Uses statistical models (no external ML dependencies needed).
"""
import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from core.database import db


class DemandForecastingModel:
    """Demand forecasting using historical booking patterns and seasonality."""

    async def forecast_demand(self, tenant_id: str, forecast_days: int = 30) -> dict[str, Any]:
        """Generate demand forecast using weighted historical analysis."""
        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        if total_rooms == 0:
            total_rooms = 1

        today = date.today()
        # Perf: 90 historical + N forecast count_documents seri çağrı
        # cold-start'ta /api/data-intelligence/revenue/forecast-dashboard'u dakikalara
        # çıkartıyordu. Hepsi bağımsız → tek asyncio.gather ile paralel çalıştır.
        hist_dates = [(today - timedelta(days=i)) for i in range(1, 91)]
        target_dates = [(today + timedelta(days=i)) for i in range(forecast_days)]

        hist_status_set = ["confirmed", "guaranteed", "checked_in", "checked_out"]
        otb_status_set = ["confirmed", "guaranteed"]

        hist_tasks = [
            db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_in": {"$lte": d.isoformat()}, "check_out": {"$gt": d.isoformat()},
                "status": {"$in": hist_status_set},
            }) for d in hist_dates
        ]
        otb_tasks = [
            db.bookings.count_documents({
                "tenant_id": tenant_id,
                "check_in": {"$lte": d.isoformat()}, "check_out": {"$gt": d.isoformat()},
                "status": {"$in": otb_status_set},
            }) for d in target_dates
        ]
        all_counts = await asyncio.gather(*hist_tasks, *otb_tasks, return_exceptions=True)
        hist_counts = all_counts[:len(hist_tasks)]
        otb_counts = all_counts[len(hist_tasks):]

        dow_history: dict[int, list[float]] = {i: [] for i in range(7)}
        for d, booked in zip(hist_dates, hist_counts):
            if isinstance(booked, Exception):
                continue
            dow_history[d.weekday()].append(booked / total_rooms)

        # Weighted average (recent weeks weighted more)
        def weighted_avg(values):
            if not values:
                return 0.5
            weights = [1 + i * 0.5 for i in range(len(values))]
            weights.reverse()
            return sum(v * w for v, w in zip(values, weights)) / sum(weights)

        forecast = []
        for i in range(forecast_days):
            target = target_dates[i]
            target_s = target.isoformat()
            dow = target.weekday()

            # Base prediction from day-of-week history
            base_occ = weighted_avg(dow_history.get(dow, []))

            # Current bookings on-the-books (gather'dan çekildi)
            otb_raw = otb_counts[i]
            otb = 0 if isinstance(otb_raw, Exception) else otb_raw
            otb_occ = otb / total_rooms

            # Blend: nearer dates trust OTB more, farther dates trust historical more
            if i <= 3:
                blend = 0.8 * otb_occ + 0.2 * base_occ
            elif i <= 14:
                blend = 0.5 * otb_occ + 0.5 * base_occ
            else:
                blend = 0.2 * otb_occ + 0.8 * base_occ

            predicted_occ = min(max(round(blend * 100, 1), 0), 100)
            predicted_rooms = round(blend * total_rooms)

            # Confidence based on data availability and distance
            confidence = max(0.3, min(0.95, 1.0 - (i / forecast_days) * 0.5))
            if len(dow_history.get(dow, [])) < 4:
                confidence *= 0.7

            forecast.append({
                "date": target_s,
                "day_of_week": target.strftime("%A"),
                "predicted_occupancy_pct": predicted_occ,
                "predicted_rooms_sold": predicted_rooms,
                "on_the_books": otb,
                "remaining_to_sell": max(total_rooms - otb, 0),
                "confidence": round(confidence, 2),
                "demand_level": "high" if predicted_occ > 80 else ("medium" if predicted_occ > 50 else "low"),
            })

        return {
            "tenant_id": tenant_id,
            "total_rooms": total_rooms,
            "forecast_days": forecast_days,
            "model": "weighted_historical_dow",
            "forecast": forecast,
        }


class RateElasticityModel:
    """Rate elasticity model measuring price sensitivity of demand."""

    async def analyze_elasticity(self, tenant_id: str, room_type: str | None = None) -> dict[str, Any]:
        """Analyze rate elasticity using historical booking and rate data."""
        # Get recent bookings with rates
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        query = {"tenant_id": tenant_id, "created_at": {"$gte": cutoff},
                 "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}}
        if room_type:
            query["room_type"] = room_type

        bookings = await db.bookings.find(
            query, {"_id": 0, "total_amount": 1, "check_in": 1, "check_out": 1, "room_type": 1}
        ).to_list(5000)

        if len(bookings) < 10:
            return {
                "tenant_id": tenant_id,
                "room_type": room_type,
                "elasticity_coefficient": -1.0,
                "interpretation": "insufficient_data",
                "recommendation": "Yeterli veri yok, varsayilan esnek talep kullaniliyor",
                "data_points": len(bookings),
            }

        # Group by price ranges and calculate demand at each level
        prices = [b.get("total_amount", 0) for b in bookings if b.get("total_amount", 0) > 0]
        if not prices:
            return {"elasticity_coefficient": -1.0, "interpretation": "no_price_data"}

        avg_price = sum(prices) / len(prices)
        price_buckets = {
            "low": {"range": (0, avg_price * 0.8), "count": 0},
            "mid_low": {"range": (avg_price * 0.8, avg_price * 0.95), "count": 0},
            "mid": {"range": (avg_price * 0.95, avg_price * 1.05), "count": 0},
            "mid_high": {"range": (avg_price * 1.05, avg_price * 1.2), "count": 0},
            "high": {"range": (avg_price * 1.2, float('inf')), "count": 0},
        }

        for p in prices:
            for bucket_name, bucket in price_buckets.items():
                if bucket["range"][0] <= p < bucket["range"][1]:
                    bucket["count"] += 1
                    break

        # Calculate elasticity coefficient
        low_demand = price_buckets["low"]["count"] + price_buckets["mid_low"]["count"]
        high_demand = price_buckets["mid_high"]["count"] + price_buckets["high"]["count"]

        if high_demand > 0 and low_demand > 0:
            demand_change = (high_demand - low_demand) / low_demand
            price_change = 0.3  # Approximate 30% price difference
            elasticity = round(demand_change / price_change, 2)
        else:
            elasticity = -1.0

        # Interpretation
        if elasticity > -0.5:
            interp = "inelastic"
            recommendation = "Fiyat artisi gelir artisina yol acar, fiyatlari artirabilirsiniz"
        elif elasticity > -1.0:
            interp = "unit_elastic"
            recommendation = "Dengeli talep, kucuk fiyat ayarlamalari yapilabilir"
        else:
            interp = "elastic"
            recommendation = "Talep fiyata duyarli, agresif fiyatlamadan kacinin"

        return {
            "tenant_id": tenant_id,
            "room_type": room_type,
            "elasticity_coefficient": elasticity,
            "interpretation": interp,
            "recommendation": recommendation,
            "average_price": round(avg_price, 2),
            "data_points": len(bookings),
            "price_distribution": {k: v["count"] for k, v in price_buckets.items()},
        }

    async def get_optimal_price_points(self, tenant_id: str) -> dict[str, Any]:
        """Calculate optimal price points per room type."""
        room_types = await db.rooms.distinct("room_type", {"tenant_id": tenant_id})
        if not room_types:
            room_types = ["Standard"]

        import asyncio
        async def _one(rt: str) -> dict[str, Any]:
            elasticity, rooms = await asyncio.gather(
                self.analyze_elasticity(tenant_id, rt),
                db.rooms.find(
                    {"tenant_id": tenant_id, "room_type": rt},
                    {"_id": 0, "base_price": 1},
                ).to_list(100),
            )
            current_avg = sum(r.get("base_price", 0) for r in rooms) / max(len(rooms), 1)
            coeff = elasticity.get("elasticity_coefficient", -1.0)
            if coeff > -0.5:
                suggested = round(current_avg * 1.10, 2)
                action = "increase"
            elif coeff > -1.0:
                suggested = round(current_avg * 1.03, 2)
                action = "slight_increase"
            else:
                suggested = round(current_avg * 0.95, 2)
                action = "decrease"
            return {
                "room_type": rt,
                "current_avg_price": round(current_avg, 2),
                "suggested_price": suggested,
                "action": action,
                "elasticity": coeff,
            }

        # Tüm room_type'lar bağımsız → paralel. Tipik mülklerde 3-10 oda tipi olur,
        # semaphore gerekmiyor. Exception olursa o satır skip edilir, kalanlar döner.
        results = await asyncio.gather(*[_one(rt) for rt in room_types], return_exceptions=True)
        price_points = [r for r in results if not isinstance(r, Exception)]
        return {"tenant_id": tenant_id, "price_points": price_points}


class BookingProbabilityModel:
    """Predict booking conversion probability based on lead time and patterns."""

    async def predict_conversion(self, tenant_id: str, check_in: str, check_out: str,
                                  source: str = "direct", room_type: str = "Standard",
                                  rate: float = 0) -> dict[str, Any]:
        """Predict probability of a booking converting (not cancelling)."""
        today = date.today()
        try:
            ci = date.fromisoformat(check_in)
        except Exception:
            ci = today + timedelta(days=7)

        lead_time = (ci - today).days

        # Historical conversion rate by source
        cutoff = (today - timedelta(days=90)).isoformat()
        total = await db.bookings.count_documents({
            "tenant_id": tenant_id, "created_at": {"$gte": cutoff},
            "source": source,
        })
        cancelled = await db.bookings.count_documents({
            "tenant_id": tenant_id, "created_at": {"$gte": cutoff},
            "source": source, "status": "cancelled",
        })
        base_rate = 1.0 - (cancelled / max(total, 1))
        if total < 5:
            base_rate = 0.75

        # Lead time adjustment
        if lead_time <= 1:
            lt_factor = 0.95
        elif lead_time <= 7:
            lt_factor = 0.90
        elif lead_time <= 30:
            lt_factor = 0.80
        elif lead_time <= 60:
            lt_factor = 0.70
        else:
            lt_factor = 0.60

        probability = round(base_rate * lt_factor, 3)
        probability = min(max(probability, 0.1), 0.99)

        risk = "low" if probability > 0.8 else ("medium" if probability > 0.6 else "high")

        return {
            "check_in": check_in,
            "check_out": check_out,
            "source": source,
            "room_type": room_type,
            "lead_time_days": lead_time,
            "conversion_probability": probability,
            "cancellation_risk": risk,
            "base_conversion_rate": round(base_rate, 3),
            "lead_time_factor": lt_factor,
            "recommendation": self._get_recommendation(risk, source),
        }

    def _get_recommendation(self, risk: str, source: str) -> str:
        if risk == "high":
            return "Yuksek iptal riski - Odeme garantisi alin veya kati iptal politikasi uygulayin"
        elif risk == "medium":
            return "Orta risk - Onay e-postasi gonderip teyit alin"
        return "Dusuk risk - Standart prosedur"

    async def get_portfolio_conversion_rates(self, tenant_id: str) -> dict[str, Any]:
        """Get conversion rates by source and lead time."""
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "source": 1, "status": 1, "created_at": 1, "check_in": 1},
        ).to_list(10000)

        by_source = {}
        for b in bookings:
            src = b.get("source", "direct")
            if src not in by_source:
                by_source[src] = {"total": 0, "cancelled": 0, "completed": 0}
            by_source[src]["total"] += 1
            if b.get("status") == "cancelled":
                by_source[src]["cancelled"] += 1
            elif b.get("status") in ("checked_out", "checked_in"):
                by_source[src]["completed"] += 1

        rates = []
        for src, data in by_source.items():
            conv_rate = round(1.0 - (data["cancelled"] / max(data["total"], 1)), 3)
            rates.append({
                "source": src,
                "total_bookings": data["total"],
                "cancelled": data["cancelled"],
                "completed": data["completed"],
                "conversion_rate": conv_rate,
            })

        rates.sort(key=lambda x: x["conversion_rate"], reverse=True)
        return {"tenant_id": tenant_id, "period_days": 90, "by_source": rates}


class CancellationPredictionModel:
    """Predict cancellation likelihood for existing bookings."""

    async def predict_cancellation_risk(self, tenant_id: str, booking_id: str) -> dict[str, Any]:
        """Predict cancellation risk for a specific booking."""
        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        today = date.today()
        check_in = booking.get("check_in", "")
        try:
            ci = date.fromisoformat(check_in[:10])
            lead_time = (ci - today).days
        except Exception:
            lead_time = 7

        # Risk factors
        risk_score = 0.0
        factors = []

        # Lead time risk
        if lead_time > 60:
            risk_score += 0.25
            factors.append({"factor": "long_lead_time", "impact": 0.25, "detail": f"{lead_time} gun onceden"})
        elif lead_time > 30:
            risk_score += 0.15
            factors.append({"factor": "medium_lead_time", "impact": 0.15, "detail": f"{lead_time} gun onceden"})

        # Source risk
        source = booking.get("source", "direct")
        if source in ("ota", "booking.com", "expedia"):
            risk_score += 0.15
            factors.append({"factor": "ota_source", "impact": 0.15, "detail": f"OTA kaynakli: {source}"})

        # No payment/deposit
        if not booking.get("payment_received") and not booking.get("deposit_paid"):
            risk_score += 0.20
            factors.append({"factor": "no_payment", "impact": 0.20, "detail": "Odeme/depozito yok"})

        # Guest history - repeat guest lower risk
        guest_id = booking.get("guest_id")
        if guest_id:
            past_stays = await db.bookings.count_documents({
                "tenant_id": tenant_id, "guest_id": guest_id,
                "status": {"$in": ["checked_out"]},
            })
            past_cancels = await db.bookings.count_documents({
                "tenant_id": tenant_id, "guest_id": guest_id,
                "status": "cancelled",
            })
            if past_cancels > past_stays:
                risk_score += 0.20
                factors.append({"factor": "cancel_history", "impact": 0.20, "detail": f"{past_cancels} onceki iptal"})
            elif past_stays > 2:
                risk_score -= 0.10
                factors.append({"factor": "loyal_guest", "impact": -0.10, "detail": f"{past_stays} onceki konaklama"})

        # Group booking lower risk
        if booking.get("group_id"):
            risk_score -= 0.10
            factors.append({"factor": "group_booking", "impact": -0.10, "detail": "Grup rezervasyonu"})

        risk_score = min(max(round(risk_score, 3), 0.0), 1.0)
        risk_level = "high" if risk_score > 0.5 else ("medium" if risk_score > 0.25 else "low")

        return {
            "booking_id": booking_id,
            "check_in": check_in,
            "lead_time_days": lead_time,
            "source": source,
            "cancellation_probability": risk_score,
            "risk_level": risk_level,
            "risk_factors": factors,
            "recommendation": self._recommendation(risk_level),
        }

    def _recommendation(self, risk_level: str) -> str:
        if risk_level == "high":
            return "Yuksek iptal riski - Misafir ile iletisime gecin, depozito veya odeme talep edin"
        elif risk_level == "medium":
            return "Orta risk - Onay e-postasi gonderip konaklami teyit edin"
        return "Dusuk risk - Standart prosedurle devam edin"

    async def get_at_risk_bookings(self, tenant_id: str, min_risk: float = 0.3) -> dict[str, Any]:
        """Get all bookings with high cancellation risk."""
        today_d = date.today()
        today = today_d.isoformat()
        # Önceden N+1 vardı: 500 booking × (1 find_one + 2 count_documents) = 1500
        # seri Mongo çağrısı. predict_cancellation_risk içindeki tüm field'ları
        # ilk projection'a dahil edip, guest_id history'sini tek bir aggregation
        # ile bulk topluyoruz; risk skoru tamamen in-memory hesaplanıyor.
        upcoming = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": {"$gte": today},
             "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "check_in": 1, "check_out": 1,
             "room_id": 1, "source": 1, "total_amount": 1, "guest_id": 1,
             "payment_received": 1, "deposit_paid": 1, "group_id": 1},
        ).to_list(500)

        guest_ids = list({b["guest_id"] for b in upcoming if b.get("guest_id")})
        history: dict[str, dict[str, int]] = {}
        if guest_ids:
            cursor = db.bookings.aggregate([
                {"$match": {"tenant_id": tenant_id, "guest_id": {"$in": guest_ids},
                            "status": {"$in": ["checked_out", "cancelled"]}}},
                {"$group": {"_id": {"gid": "$guest_id", "st": "$status"},
                             "n": {"$sum": 1}}},
            ])
            async for row in cursor:
                gid = row["_id"]["gid"]
                st = row["_id"]["st"]
                history.setdefault(gid, {"checked_out": 0, "cancelled": 0})
                history[gid][st] = row["n"]

        at_risk = []
        for b in upcoming:
            try:
                ci = date.fromisoformat((b.get("check_in") or "")[:10])
                lead_time = (ci - today_d).days
            except Exception:
                lead_time = 7

            score = 0.0
            factors: list[dict[str, Any]] = []

            if lead_time > 60:
                score += 0.25
                factors.append({"factor": "long_lead_time", "impact": 0.25, "detail": f"{lead_time} gun onceden"})
            elif lead_time > 30:
                score += 0.15
                factors.append({"factor": "medium_lead_time", "impact": 0.15, "detail": f"{lead_time} gun onceden"})

            source = b.get("source", "direct")
            if source in ("ota", "booking.com", "expedia"):
                score += 0.15
                factors.append({"factor": "ota_source", "impact": 0.15, "detail": f"OTA kaynakli: {source}"})

            if not b.get("payment_received") and not b.get("deposit_paid"):
                score += 0.20
                factors.append({"factor": "no_payment", "impact": 0.20, "detail": "Odeme/depozito yok"})

            gid = b.get("guest_id")
            if gid:
                h = history.get(gid, {"checked_out": 0, "cancelled": 0})
                past_stays = h.get("checked_out", 0)
                past_cancels = h.get("cancelled", 0)
                if past_cancels > past_stays:
                    score += 0.20
                    factors.append({"factor": "cancel_history", "impact": 0.20, "detail": f"{past_cancels} onceki iptal"})
                elif past_stays > 2:
                    score -= 0.10
                    factors.append({"factor": "loyal_guest", "impact": -0.10, "detail": f"{past_stays} onceki konaklama"})

            if b.get("group_id"):
                score -= 0.10
                factors.append({"factor": "group_booking", "impact": -0.10, "detail": "Grup rezervasyonu"})

            score = min(max(round(score, 3), 0.0), 1.0)
            if score >= min_risk:
                risk_level = "high" if score > 0.5 else ("medium" if score > 0.25 else "low")
                at_risk.append({
                    **{k: v for k, v in b.items()
                       if k not in ("payment_received", "deposit_paid", "group_id", "guest_id")},
                    "cancellation_probability": score,
                    "risk_level": risk_level,
                    "risk_factors": factors,
                })

        at_risk.sort(key=lambda x: x["cancellation_probability"], reverse=True)
        total_at_risk_revenue = sum(b.get("total_amount", 0) for b in at_risk)

        return {
            "tenant_id": tenant_id,
            "min_risk_threshold": min_risk,
            "at_risk_count": len(at_risk),
            "total_at_risk_revenue": round(total_at_risk_revenue, 2),
            "bookings": at_risk[:30],
        }


class RevenueMLDashboard:
    """Unified dashboard for all Revenue ML models."""

    def __init__(self):
        self.demand = DemandForecastingModel()
        self.elasticity = RateElasticityModel()
        self.booking_prob = BookingProbabilityModel()
        self.cancellation = CancellationPredictionModel()

    async def get_ml_dashboard(self, tenant_id: str) -> dict[str, Any]:
        """Get comprehensive ML insights dashboard.

        Subpipeline'lar paralel ve fault-tolerant: biri patlarsa kalanlar yine
        döner, hata sectionErrors içinde bildirilir (kısmi sonuç stratejisi).
        """
        import asyncio
        import logging as _logging
        _log = _logging.getLogger(__name__)

        results = await asyncio.gather(
            self.demand.forecast_demand(tenant_id, 14),
            self.elasticity.get_optimal_price_points(tenant_id),
            self.booking_prob.get_portfolio_conversion_rates(tenant_id),
            self.cancellation.get_at_risk_bookings(tenant_id, 0.3),
            return_exceptions=True,
        )
        section_names = ("demand_forecast", "price_optimization", "conversion_rates", "cancellation_risk")
        section_errors: dict[str, str] = {}
        normalized: list[dict[str, Any]] = []
        for name, res in zip(section_names, results, strict=True):
            if isinstance(res, Exception):
                _log.exception("ml_dashboard subpipeline %s failed for tenant %s", name, tenant_id, exc_info=res)
                section_errors[name] = f"{type(res).__name__}: {res}"
                normalized.append({})
            else:
                normalized.append(res)
        demand_forecast, price_points, conversion_rates, at_risk = normalized

        # Summarize
        high_demand_days = sum(1 for f in demand_forecast.get("forecast", []) if f.get("demand_level") == "high")
        low_demand_days = sum(1 for f in demand_forecast.get("forecast", []) if f.get("demand_level") == "low")

        return {
            "tenant_id": tenant_id,
            "summary": {
                "high_demand_days_next_14": high_demand_days,
                "low_demand_days_next_14": low_demand_days,
                "at_risk_bookings": at_risk.get("at_risk_count", 0),
                "at_risk_revenue": at_risk.get("total_at_risk_revenue", 0),
                "price_optimization_opportunities": len(price_points.get("price_points", [])),
            },
            "demand_forecast": demand_forecast,
            "price_optimization": price_points,
            "conversion_rates": conversion_rates,
            "cancellation_risk": at_risk,
            "section_errors": section_errors,
            "generated_at": datetime.now(UTC).isoformat(),
        }
