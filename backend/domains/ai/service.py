"""
AI Intelligence Service for Hotel Management System
Provides AI-powered insights, predictions, and recommendations
"""

import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    _AI_BACKEND_AVAILABLE = True
except Exception:
    LlmChat = None
    UserMessage = None
    _AI_BACKEND_AVAILABLE = False

# Load environment variables
load_dotenv()

class AIService:
    def __init__(self):
        # Track whether we can safely call the external LLM backend
        self.llm_enabled = False
        self.api_key = None

        if _AI_BACKEND_AVAILABLE and LlmChat is not None:
            api_key = os.getenv('EMERGENT_LLM_KEY')
            if api_key:
                self.api_key = api_key
                self.llm_enabled = True
        # If the backend or key is missing we stay in fallback mode

    def _create_chat(self, system_message: str, session_id: str = "default") -> LlmChat:
        """Create a new chat instance with the specified system message.
        If LLM backend is not available, raise a clear error so callers can
        fallback to heuristic logic instead of crashing the app.
        """
        if not self.llm_enabled:
            raise RuntimeError("LLM backend not available")

        chat = LlmChat(
            api_key=self.api_key,
            session_id=session_id,
            system_message=system_message
        )
        # Use GPT-4o-mini for fast, cost-effective responses
        chat.with_model("openai", "gpt-4o-mini")
        return chat

    async def generate_daily_briefing(
        self,
        hotel_name: str,
        total_rooms: int,
        occupied_rooms: int,
        today_checkins: int,
        today_checkouts: int,
        pending_invoices: int,
        monthly_revenue: float,
        weather: str = "clear"
    ) -> str:
        """
        Generate a natural language daily briefing for the dashboard
        """
        system_message = """Sen bir otel yönetimi AI asistanısın.
        Otel müdürlerine kısa, samimi ve uygulanabilir günlük brifingleri TÜRKÇE olarak sunarsan.
        Ana metriklere, trendlere ve uygulanabilir içgörülere odaklan.
        Yanıtlarını 100 kelimeyi geçmeyecek şekilde tut. Her zaman Türkçe yanıt ver."""

        chat = self._create_chat(system_message, session_id=f"briefing_{datetime.now().strftime('%Y%m%d')}")

        occupancy_rate = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0

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

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        return response

    async def predict_occupancy(
        self,
        historical_data: list[dict[str, Any]],
        current_occupancy: float,
        upcoming_bookings: int,
        season: str = "normal",
        room_capacity: int | None = None
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

            user_message = UserMessage(text=prompt)
            response = await chat.send_message(user_message)
        except Exception as exc:
            return self._fallback_occupancy_prediction(
                current_occupancy=current_occupancy,
                upcoming_bookings=upcoming_bookings,
                season=season,
                room_capacity=room_capacity,
                error_message=str(exc)
            )

        # Try to parse as JSON, fallback to text response
        try:
            import json
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                parsed = json.loads(response[json_start:json_end])
                if isinstance(parsed, dict):
                    parsed.setdefault("source", "llm")
                    return parsed
        except Exception:
            pass

        return {
            "prediction": response,
            "confidence": "medium",
            "source": "llm_raw"
        }

    def _fallback_occupancy_prediction(
        self,
        current_occupancy: float,
        upcoming_bookings: int,
        season: str,
        room_capacity: int | None = None,
        error_message: str | None = None
    ) -> dict[str, Any]:
        """
        Generate a deterministic occupancy prediction when the AI backend
        is unavailable. Keeps the UI responsive instead of surfacing 500 errors.
        """
        capacity = max(room_capacity or 100, 1)
        booking_ratio = min(1.5, upcoming_bookings / capacity)
        seasonal_adjustment = 5 if season == "peak" else -3 if season == "low" else 0

        demand_modifier = booking_ratio * 20
        tomorrow_prediction = max(0.0, min(100.0, current_occupancy + demand_modifier * 0.6 + seasonal_adjustment))
        next_week_prediction = max(
            tomorrow_prediction,
            max(0.0, min(100.0, current_occupancy + demand_modifier + seasonal_adjustment))
        )

        confidence = "high" if booking_ratio >= 1 else "medium" if booking_ratio >= 0.5 else "low"

        patterns = [
            f"Current occupancy is {current_occupancy:.1f}%.",
            f"{upcoming_bookings} upcoming bookings cover roughly {booking_ratio:.0%} of available rooms."
        ]
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
            "source": "heuristic"
        }

    async def analyze_guest_patterns(
        self,
        checkin_times: list[str],
        checkout_times: list[str],
        guest_count: int
    ) -> str:
        """
        Analyze check-in/check-out patterns for staffing optimization
        """
        system_message = """You are a hotel operations AI.
        Analyze guest patterns to optimize staffing and operations."""

        chat = self._create_chat(system_message, session_id="pattern_analysis")

        prompt = f"""Analyze these guest patterns:

Check-in times: {', '.join(checkin_times[:10])}
Check-out times: {', '.join(checkout_times[:10])}
Total guests: {guest_count}

Identify:
1. Peak check-in/check-out hours
2. Staffing recommendations
3. Any unusual patterns

Keep response concise (under 80 words)."""

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
        return response

    async def categorize_expense(
        self,
        description: str,
        amount: float,
        vendor: str = ""
    ) -> dict[str, str]:
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

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)

        # Parse response
        category = "Other"
        confidence = "medium"

        if "Category:" in response:
            try:
                parts = response.split(',')
                category = parts[0].split(':')[1].strip()
                if len(parts) > 1:
                    confidence = parts[1].split(':')[1].strip().lower()
            except Exception:
                pass

        return {
            "category": category,
            "confidence": confidence,
            "raw_response": response
        }

    async def detect_invoice_anomalies(
        self,
        invoices: list[dict[str, Any]],
        average_amount: float
    ) -> list[dict[str, Any]]:
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

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)

        return [{
            "type": "analysis",
            "message": response
        }]

    async def segment_guests(
        self,
        guests: list[dict[str, Any]]
    ) -> dict[str, Any]:
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

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)

        return {
            "segments_analysis": response,
            "total_guests": len(guests)
        }

    async def predict_churn_risk(
        self,
        guest_id: str,
        last_visit_days: int,
        total_visits: int,
        average_spend: float
    ) -> dict[str, Any]:
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

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)

        # Determine risk level from response
        risk_level = "medium"
        if "high" in response.lower():
            risk_level = "high"
        elif "low" in response.lower():
            risk_level = "low"

        return {
            "risk_level": risk_level,
            "analysis": response
        }

    async def recommend_products(
        self,
        inventory: list[dict[str, Any]],
        recent_orders: list[dict[str, Any]],
        season: str = "normal"
    ) -> list[dict[str, Any]]:
        """
        Recommend products to order based on usage patterns
        """
        system_message = """You are a hotel procurement AI.
        Recommend products to order based on inventory levels and usage patterns."""

        chat = self._create_chat(system_message, session_id="product_recommendations")

        # Summarize inventory
        low_stock_items = [item for item in inventory if item.get('quantity', 0) < item.get('reorder_level', 10)]

        prompt = f"""Analyze inventory and recommend orders:

Low stock items: {len(low_stock_items)}
Recent orders (last month): {len(recent_orders)}
Season: {season}

Based on typical hotel needs and the season, recommend:
1. Top 3 items to reorder immediately
2. Quantities for each
3. Any seasonal items to stock up on

Keep it concise and practical."""

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)

        return [{
            "type": "recommendation",
            "message": response,
            "low_stock_count": len(low_stock_items)
        }]

    async def analyze_revenue_trends(
        self,
        revenue_data: list[dict[str, Any]],
        current_month_revenue: float,
        last_month_revenue: float
    ) -> str:
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

        user_message = UserMessage(text=prompt)
        response = await chat.send_message(user_message)
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
