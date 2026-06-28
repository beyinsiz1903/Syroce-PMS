"""
AI Intelligence Service for Hotel Management System
Provides AI-powered insights, predictions, and recommendations
"""

import os
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI

    _OPENAI_AVAILABLE = True
except Exception:
    AsyncOpenAI = None
    _OPENAI_AVAILABLE = False

load_dotenv()


# F8O (Task #206) — authoritative LLM-attempt ledger.
# Module-level, process-scoped. Every `_create_chat` invocation increments
# the counter and appends a (ts, provider, session_excerpt) entry capped
# at 20 entries. Diagnostics endpoint exposes this snapshot so stress
# specs can compare deltas around test batches and fail-closed on any
# attempted vendor call. NO request/response payloads are stored.
_AI_LLM_CALL_LEDGER: dict[str, Any] = {
    "attempted_count": 0,
    "last_attempts": [],
}


def _record_llm_attempt(provider: str, session_id: str) -> None:
    try:
        _AI_LLM_CALL_LEDGER["attempted_count"] = int(_AI_LLM_CALL_LEDGER.get("attempted_count", 0)) + 1
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "provider": provider,
            "session": (session_id or "")[:40],
        }
        attempts = _AI_LLM_CALL_LEDGER.get("last_attempts") or []
        attempts.append(entry)
        if len(attempts) > 20:
            attempts = attempts[-20:]
        _AI_LLM_CALL_LEDGER["last_attempts"] = attempts
    except Exception:
        # Never break LLM flow on ledger bookkeeping error.
        pass


def get_ai_llm_call_ledger() -> dict[str, Any]:
    """Return a shallow snapshot of the LLM attempt ledger (read-only)."""
    return {
        "attempted_count": int(_AI_LLM_CALL_LEDGER.get("attempted_count", 0)),
        "last_attempts": list(_AI_LLM_CALL_LEDGER.get("last_attempts") or []),
    }


class _SimpleLlmChat:
    def __init__(self, api_key: str, system_message: str, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=api_key)
        self.system_message = system_message
        self.model = model

    async def send_message(self, content: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_message},
                {"role": "user", "content": content},
            ],
            max_tokens=1024,
            temperature=0.7,
        )
        return response.choices[0].message.content


class AIService:
    def __init__(self):
        self.llm_enabled = False
        self.api_key = None

        if _OPENAI_AVAILABLE and AsyncOpenAI is not None:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.api_key = api_key
                self.llm_enabled = True

    def _create_chat(self, system_message: str, session_id: str = "default") -> _SimpleLlmChat:
        if not self.llm_enabled:
            raise RuntimeError("LLM backend not available")
        # F8O ledger — record EVERY chat construction. This catches even
        # attempted-but-failed vendor calls; stress specs read this counter
        # via /api/ai/diagnostics/llm-state and fail-closed on any delta.
        _record_llm_attempt(provider="openai", session_id=session_id)
        return _SimpleLlmChat(api_key=self.api_key, system_message=system_message)

    async def generate_daily_briefing(
        self, hotel_name: str, total_rooms: int, occupied_rooms: int, today_checkins: int, today_checkouts: int, pending_invoices: int, monthly_revenue: float, weather: str = "clear", lang: str = "tr"
    ) -> str:
        """
        Generate a natural language daily briefing for the dashboard
        """
        if lang == "tr":
            system_message = """Sen bir otel yönetimi AI asistanısın.
            Otel müdürlerine kısa, samimi ve uygulanabilir günlük brifingleri TÜRKÇE olarak sunarsan.
            Ana metriklere, trendlere ve uygulanabilir içgörülere odaklan.
            Yanıtlarını 100 kelimeyi geçmeyecek şekilde tut. Her zaman Türkçe yanıt ver."""
        else:
            system_message = f"""You are a hotel management AI assistant.
            You provide short, friendly, and actionable daily briefings in {lang.upper()} language.
            Focus on key metrics, trends, and actionable insights.
            Keep your response under 100 words. Always respond in {lang.upper()} language."""

        chat = self._create_chat(system_message, session_id=f"briefing_{datetime.now().strftime('%Y%m%d')}")

        occupancy_rate = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0

        if lang == "tr":
            prompt = f"""{hotel_name} için sabah brifingini oluştur:

Mevcut Durum:
- Toplam Oda: {total_rooms}
- Dolu: {occupied_rooms} (%{occupancy_rate:.1f} doluluk)
- Bugünkü Girişler: {today_checkins}
- Bugünkü Çıkışlar: {today_checkouts}
- Bekleyen Faturalar: {pending_invoices}
- Aylık Gelir: {monthly_revenue:,.2f} TL
- Hava: {weather}

Samimi bir karşılama yap, önemli metrikleri vurgula ve bugün için 1-2 uygulanabilir içgörü ver. Türkçe yanıt ver."""
        else:
            prompt = f"""Generate a morning briefing for {hotel_name}:

Current Status:
- Total Rooms: {total_rooms}
- Occupied: {occupied_rooms} ({occupancy_rate:.1f}% occupancy)
- Today's Check-ins: {today_checkins}
- Today's Check-outs: {today_checkouts}
- Pending Invoices: {pending_invoices}
- Monthly Revenue: {monthly_revenue:,.2f} ₺
- Weather: {weather}

Give a friendly greeting, highlight key metrics, and provide 1-2 actionable insights for today."""

        response = await chat.send_message(prompt)
        return response

    async def predict_occupancy(
        self, historical_data: list[dict[str, Any]], current_occupancy: float, upcoming_bookings: int, season: str = "normal", room_capacity: int | None = None
    ) -> dict[str, Any]:
        """
        Predict occupancy trends and patterns for PMS.
        Falls back to a deterministic heuristic when the LLM backend is unavailable.
        """
        system_message = """You are a hotel revenue management AI.
        Analyze occupancy data and provide predictions with confidence levels.
        Be data-driven and provide specific numbers."""

        try:
            chat = self._create_chat(system_message, session_id="occupancy_prediction")
            prompt = f"""Analyze this hotel occupancy data:

Current occupancy: {current_occupancy}%
Upcoming bookings (next 7 days): {upcoming_bookings}
Season: {season}
Historical data points: {len(historical_data)}

Based on this data:
1. Predict tomorrow's occupancy percentage
2. Predict next week's average occupancy
3. Identify any concerning patterns
4. Provide 1-2 actionable recommendations

Format your response as JSON with keys: tomorrow_prediction, next_week_prediction, patterns, recommendations"""

            response = await chat.send_message(prompt)
        except Exception as exc:
            return self._fallback_occupancy_prediction(current_occupancy=current_occupancy, upcoming_bookings=upcoming_bookings, season=season, room_capacity=room_capacity, error_message=str(exc))

        # Try to parse as JSON, fallback to text response
        try:
            import json

            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start != -1 and json_end != -1:
                parsed = json.loads(response[json_start:json_end])
                if isinstance(parsed, dict):
                    parsed.setdefault("source", "llm")
                    return parsed
        except Exception:
            pass

        return {"prediction": response, "confidence": "medium", "source": "llm_raw"}

    def _fallback_occupancy_prediction(self, current_occupancy: float, upcoming_bookings: int, season: str, room_capacity: int | None = None, error_message: str | None = None) -> dict[str, Any]:
        """
        Generate a deterministic occupancy prediction when the AI backend
        is unavailable. Keeps the UI responsive instead of surfacing 500 errors.
        """
        capacity = max(room_capacity or 100, 1)
        booking_ratio = min(1.5, upcoming_bookings / capacity)
        seasonal_adjustment = 5 if season == "peak" else -3 if season == "low" else 0

        demand_modifier = booking_ratio * 20
        tomorrow_prediction = max(0.0, min(100.0, current_occupancy + demand_modifier * 0.6 + seasonal_adjustment))
        next_week_prediction = max(tomorrow_prediction, max(0.0, min(100.0, current_occupancy + demand_modifier + seasonal_adjustment)))

        confidence = "high" if booking_ratio >= 1 else "medium" if booking_ratio >= 0.5 else "low"

        patterns = [f"Current occupancy is {current_occupancy:.1f}%.", f"{upcoming_bookings} upcoming bookings cover roughly {booking_ratio:.0%} of available rooms."]
        # We do not surface technical error messages to end users in the UI;
        # the frontend only shows human-friendly patterns.

        recommendations = []
        if booking_ratio >= 0.8:
            recommendations.append("Prioritize rate management to capitalize on strong demand.")
        else:
            recommendations.append("Launch a targeted promotion to build short-term demand.")

        if next_week_prediction > current_occupancy + 5:
            recommendations.append("Schedule sufficient staff to handle the projected increase in occupancy.")
        else:
            recommendations.append("Use the softer demand window for maintenance or deep cleaning.")

        return {
            "tomorrow_prediction": round(tomorrow_prediction, 1),
            "next_week_prediction": round(next_week_prediction, 1),
            "patterns": patterns,
            "recommendations": recommendations,
            "confidence": confidence,
            "source": "heuristic",
        }

    async def analyze_guest_patterns(self, checkin_times: list[str], checkout_times: list[str], guest_count: int) -> str:
        """
        Analyze check-in/check-out patterns for staffing optimization
        """
        system_message = """You are a hotel operations AI.
        Analyze guest patterns to optimize staffing and operations."""

        chat = self._create_chat(system_message, session_id="pattern_analysis")

        prompt = f"""Analyze these guest patterns:

Check-in times: {", ".join(checkin_times[:10])}
Check-out times: {", ".join(checkout_times[:10])}
Total guests: {guest_count}

Identify:
1. Peak check-in/check-out hours
2. Staffing recommendations
3. Any unusual patterns

Keep response concise (under 80 words)."""

        response = await chat.send_message(prompt)
        return response

    async def categorize_expense(self, description: str, amount: float, vendor: str = "") -> dict[str, str]:
        """
        Automatically categorize expenses for invoicing
        """
        system_message = """You are a hotel accounting AI.
        Categorize expenses accurately based on description and amount.
        Categories: Utilities, Supplies, Maintenance, Food & Beverage, Marketing, Staff, Other"""

        chat = self._create_chat(system_message, session_id="expense_categorization")

        prompt = f"""Categorize this expense:

Description: {description}
Amount: ${amount}
Vendor: {vendor}

Respond with just the category name and a confidence level (high/medium/low).
Format: Category: [category], Confidence: [level]"""

        response = await chat.send_message(prompt)

        # Parse response
        category = "Other"
        confidence = "medium"

        if "Category:" in response:
            try:
                parts = response.split(",")
                category = parts[0].split(":")[1].strip()
                if len(parts) > 1:
                    confidence = parts[1].split(":")[1].strip().lower()
            except Exception:
                pass

        return {"category": category, "confidence": confidence, "raw_response": response}

    async def detect_invoice_anomalies(self, invoices: list[dict[str, Any]], average_amount: float) -> list[dict[str, Any]]:
        """
        Detect unusual patterns in invoices
        """
        system_message = """You are a financial analysis AI for hotels.
        Detect anomalies, unusual patterns, or potential issues in invoice data."""

        chat = self._create_chat(system_message, session_id="invoice_analysis")

        # Summarize invoice data
        invoice_summary = []
        for inv in invoices[:10]:  # Analyze last 10
            invoice_summary.append(f"${inv.get('total', 0):.2f} - {inv.get('customer_name', 'Unknown')}")

        prompt = f"""Analyze these recent invoices:

{chr(10).join(invoice_summary)}

Average invoice amount: ${average_amount:.2f}

Identify:
1. Any unusually high/low amounts
2. Potential duplicate invoices
3. Any concerning patterns

List only genuine anomalies. Be concise."""

        response = await chat.send_message(prompt)

        return [{"type": "analysis", "message": response}]

    async def segment_guests(self, guests: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Segment guests for loyalty program targeting
        """
        system_message = """You are a hotel marketing AI.
        Segment guests into categories for targeted marketing and loyalty programs."""

        chat = self._create_chat(system_message, session_id="guest_segmentation")

        # Create guest summary
        guest_summary = f"Total guests: {len(guests)}\n"
        if len(guests) > 0:
            # Sample some guest data
            sample_guests = guests[:5]
            for g in sample_guests:
                guest_summary += f"- {g.get('name', 'Guest')}: {g.get('total_stays', 0)} stays, ${g.get('total_spent', 0):.2f} spent\n"

        prompt = f"""Analyze this guest data and create segments:

{guest_summary}

Create 3-4 guest segments (e.g., VIP, Regular, New, At-Risk) with:
1. Segment criteria
2. Marketing strategy for each
3. Predicted lifetime value

Format as JSON with segments array."""

        response = await chat.send_message(prompt)

        return {"segments_analysis": response, "total_guests": len(guests)}

    async def predict_churn_risk(self, guest_id: str, last_visit_days: int, total_visits: int, average_spend: float) -> dict[str, Any]:
        """
        Predict if a guest is at risk of churning
        """
        system_message = """You are a customer retention AI for hotels.
        Predict churn risk and recommend retention strategies."""

        chat = self._create_chat(system_message, session_id=f"churn_{guest_id}")

        prompt = f"""Assess churn risk for this guest:

Last visit: {last_visit_days} days ago
Total visits: {total_visits}
Average spend per visit: ${average_spend:.2f}

Provide:
1. Churn risk level (low/medium/high)
2. Key risk factors
3. 1-2 retention recommendations

Be concise (under 60 words)."""

        response = await chat.send_message(prompt)

        # Determine risk level from response
        risk_level = "medium"
        if "high" in response.lower():
            risk_level = "high"
        elif "low" in response.lower():
            risk_level = "low"

        return {"risk_level": risk_level, "analysis": response}

    async def recommend_products(self, inventory: list[dict[str, Any]], recent_orders: list[dict[str, Any]], season: str = "normal") -> list[dict[str, Any]]:
        """
        Recommend products to order based on usage patterns
        """
        system_message = """You are a hotel procurement AI.
        Recommend products to order based on inventory levels and usage patterns."""

        chat = self._create_chat(system_message, session_id="product_recommendations")

        # Summarize inventory
        low_stock_items = [item for item in inventory if item.get("quantity", 0) < item.get("reorder_level", 10)]

        prompt = f"""Analyze inventory and recommend orders:

Low stock items: {len(low_stock_items)}
Recent orders (last month): {len(recent_orders)}
Season: {season}

Based on typical hotel needs and the season, recommend:
1. Top 3 items to reorder immediately
2. Quantities for each
3. Any seasonal items to stock up on

Keep it concise and practical."""

        response = await chat.send_message(prompt)

        return [{"type": "recommendation", "message": response, "low_stock_count": len(low_stock_items)}]

    async def analyze_revenue_trends(self, revenue_data: list[dict[str, Any]], current_month_revenue: float, last_month_revenue: float) -> str:
        """
        Analyze revenue trends for RMS insights
        """
        system_message = """You are a hotel revenue management AI.
        Analyze revenue trends and provide strategic insights."""

        chat = self._create_chat(system_message, session_id="revenue_analysis")

        change_percent = ((current_month_revenue - last_month_revenue) / last_month_revenue * 100) if last_month_revenue > 0 else 0

        prompt = f"""Analyze revenue trends:

Current month: ${current_month_revenue:,.2f}
Last month: ${last_month_revenue:,.2f}
Change: {change_percent:+.1f}%

Data points: {len(revenue_data)}

Provide:
1. Trend analysis
2. Contributing factors
3. 1-2 pricing recommendations

Keep under 80 words."""

        response = await chat.send_message(prompt)
        return response


# Lazy-loaded singleton instance
_ai_service_instance = None


def get_ai_service():
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
    return _ai_service_instance


# For backwards compatibility
ai_service = None  # Will be initialized on first use
