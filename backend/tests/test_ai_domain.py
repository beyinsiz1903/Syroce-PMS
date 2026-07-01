"""
Tests for AI Domain — Dynamic Pricing, Predictive Engine, Reputation Manager
Covers K5 critical gap: AI domain had zero test coverage.
"""
import re
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime, timedelta


class FakeCursor:
    def __init__(self, data):
        self._data = data

    async def to_list(self, limit=None):
        return self._data[:limit] if limit else list(self._data)


def _match_doc(doc, query):
    """Mongo-benzeri sorgu eslestirme (test FakeDB icin).

    Esitlik + $gt/$gte/$lt/$lte/$in/$nin/$ne/$regex destekler. Eksik alan bir
    karsilastirma/regex operatorunu KARSILAMAZ (fail-closed) — boylece
    tenant/room_type/tarih filtreleri gercekten sinanir (fake-green degil).
    """
    for k, v in query.items():
        dv = doc.get(k)
        if isinstance(v, dict):
            for op, ov in v.items():
                if op == '$gt':
                    if dv is None or not (dv > ov):
                        return False
                elif op == '$gte':
                    if dv is None or not (dv >= ov):
                        return False
                elif op == '$lt':
                    if dv is None or not (dv < ov):
                        return False
                elif op == '$lte':
                    if dv is None or not (dv <= ov):
                        return False
                elif op == '$in':
                    if dv not in ov:
                        return False
                elif op == '$nin':
                    if dv in ov:
                        return False
                elif op == '$ne':
                    if dv == ov:
                        return False
                elif op == '$regex':
                    if dv is None or re.search(ov, str(dv)) is None:
                        return False
                # bilinmeyen operator -> yok say (asiri kisitlama yapma)
        else:
            if dv != v:
                return False
    return True


class FakeCollection:
    def __init__(self, data=None):
        self._data = data or []

    async def count_documents(self, query=None):
        return len([d for d in self._data if _match_doc(d, query or {})])

    def find(self, query=None, projection=None):
        return FakeCursor([d for d in self._data if _match_doc(d, query or {})])

    def aggregate(self, pipeline):
        # $match (esitlik + operatorler) ve $group ($avg) emulasyonu.
        docs = list(self._data)
        for stage in pipeline:
            if '$match' in stage:
                docs = [d for d in docs if _match_doc(d, stage['$match'])]
            elif '$group' in stage:
                g = stage['$group']
                out = {'_id': g.get('_id')}
                for key, expr in g.items():
                    if key == '_id':
                        continue
                    if isinstance(expr, dict) and '$avg' in expr:
                        field = str(expr['$avg']).lstrip('$')
                        vals = [d.get(field) for d in docs if isinstance(d.get(field), (int, float))]
                        out[key] = (sum(vals) / len(vals)) if vals else None
                docs = [out] if docs else []
        return FakeCursor(docs)


class FakeDB:
    def __init__(self, rooms=None, bookings=None, reviews=None, service_complaints=None, competitor_rates=None, external_reviews=None):
        self.rooms = FakeCollection(rooms or [])
        self.bookings = FakeCollection(bookings or [])
        self.reviews = FakeCollection(reviews or [])
        self.service_complaints = FakeCollection(service_complaints or [])
        self.competitor_rates = FakeCollection(competitor_rates or [])
        self.external_reviews = FakeCollection(external_reviews or [])


class TestDynamicPricingEngine:
    def setup_method(self):
        from domains.ai.dynamic_pricing_engine import DynamicPricingEngine
        self.db = FakeDB(
            rooms=[{"tenant_id": "t1", "room_type": "Standard", "base_price": 100} for _ in range(100)],
            # check_in/check_out span "2026-04-20" so strict filtering counts them (occupancy 70%).
            bookings=[
                {"tenant_id": "t1", "status": "confirmed",
                 "check_in": "2026-01-01", "check_out": "2026-12-31"}
                for _ in range(70)
            ],
            competitor_rates=[
                {"tenant_id": "t1", "date": "2026-04-20", "room_type": "Standard", "competitor_name": "Comp A", "rate": 100},
                {"tenant_id": "t1", "date": "2026-04-20", "room_type": "Standard", "competitor_name": "Comp B", "rate": 110},
                {"tenant_id": "t1", "date": "2026-04-20", "room_type": "Standard", "competitor_name": "Comp C", "rate": 120},
            ],
        )
        self.engine = DynamicPricingEngine(self.db)

    @pytest.mark.asyncio
    async def test_base_price_derived_from_real_rooms(self):
        # Taban fiyat artik GERCEK oda kayitlarindan turetilir (sabit dict yok).
        assert not hasattr(self.engine, "base_prices")
        base = await self.engine._resolve_base_price("t1", "Standard")
        assert base == 100

    @pytest.mark.asyncio
    async def test_recommend_price_no_real_base_fails_closed(self):
        from domains.ai.dynamic_pricing_engine import DynamicPricingEngine
        # base_price'i olmayan odalar -> uydurma sabit YOK, fail-closed.
        engine = DynamicPricingEngine(FakeDB(
            rooms=[{"tenant_id": "t1", "room_type": "Standard"} for _ in range(10)],
        ))
        result = await engine.recommend_price("t1", "Standard", "2026-04-20")
        assert result["recommended_price"] is None
        assert result["current_price"] is None
        assert result["pricing_method"] == "base_price_unavailable"
        assert result["data_available"] is False

    @pytest.mark.asyncio
    async def test_get_competitor_rates_structure(self):
        result = await self.engine.get_competitor_rates("t1", "2026-04-20", "Standard")
        assert result["available"] is True
        assert "competitors" in result
        assert "average" in result
        assert "min" in result
        assert "max" in result
        assert len(result["competitors"]) == 3
        assert result["min"] <= result["average"] <= result["max"]

    @pytest.mark.asyncio
    async def test_competitor_rates_empty_returns_unavailable(self):
        from domains.ai.dynamic_pricing_engine import DynamicPricingEngine
        empty_engine = DynamicPricingEngine(FakeDB())
        result = await empty_engine.get_competitor_rates("t1", "2026-04-20", "Standard")
        assert result["available"] is False
        assert result["competitors"] == {}
        assert result["average"] is None

    @pytest.mark.asyncio
    async def test_competitor_rates_deterministic(self):
        first = await self.engine.get_competitor_rates("t1", "2026-04-20", "Standard")
        second = await self.engine.get_competitor_rates("t1", "2026-04-20", "Standard")
        assert first == second

    @pytest.mark.asyncio
    async def test_calculate_demand_factors_structure(self):
        result = await self.engine.calculate_demand_factors("t1", "2026-04-20")
        assert "weekend_factor" in result
        assert "demand_factor" in result
        assert "urgency_factor" in result
        assert "event_factor" in result
        assert "occupancy_forecast" in result
        assert result["weekend_factor"] >= 1.0
        assert result["demand_factor"] >= 0.9
        # Etkinlik faktoru gercek veri entegre edilene kadar notr (deterministik)
        assert result["event_factor"] == 1.0

    @pytest.mark.asyncio
    async def test_weekend_factor_higher(self):
        friday = datetime(2026, 4, 17, tzinfo=UTC)
        monday = datetime(2026, 4, 20, tzinfo=UTC)
        result_fri = await self.engine.calculate_demand_factors("t1", friday.isoformat())
        result_mon = await self.engine.calculate_demand_factors("t1", monday.isoformat())
        assert result_fri["weekend_factor"] >= result_mon["weekend_factor"]

    @pytest.mark.asyncio
    async def test_recommend_price_structure(self):
        result = await self.engine.recommend_price("t1", "Standard", "2026-04-20")
        assert "recommended_price" in result
        assert "min_price" in result
        assert "max_price" in result
        assert "pricing_method" in result
        assert "applied_rules" in result
        assert "competitor_data" in result
        assert "demand_factors" in result
        assert "current_price" in result
        assert "price_change_pct" in result
        assert "confidence_score" not in result
        assert result["min_price"] <= result["recommended_price"] <= result["max_price"]

    @pytest.mark.asyncio
    async def test_recommend_price_positive(self):
        result = await self.engine.recommend_price("t1", "Standard", "2026-04-20")
        assert result["recommended_price"] > 0
        assert result["pricing_method"] == "rule_based_deterministic"
        assert isinstance(result["applied_rules"], list)
        assert len(result["applied_rules"]) > 0

    @pytest.mark.asyncio
    async def test_recommend_price_deterministic(self):
        first = await self.engine.recommend_price("t1", "Standard", "2026-04-20")
        second = await self.engine.recommend_price("t1", "Standard", "2026-04-20")
        assert first["recommended_price"] == second["recommended_price"]
        assert first["applied_rules"] == second["applied_rules"]

    @pytest.mark.asyncio
    async def test_recommend_price_not_deviate_too_much(self):
        result = await self.engine.recommend_price("t1", "Standard", "2026-04-20")
        competitor_avg = result["competitor_data"]["average"]
        assert result["recommended_price"] < competitor_avg * 1.5
        assert result["recommended_price"] > competitor_avg * 0.5

    @pytest.mark.asyncio
    async def test_recommend_price_no_competitor_data(self):
        from domains.ai.dynamic_pricing_engine import DynamicPricingEngine
        engine = DynamicPricingEngine(FakeDB(
            rooms=[{"tenant_id": "t1", "room_type": "Standard", "base_price": 100} for _ in range(10)],
            bookings=[{"tenant_id": "t1", "status": "confirmed"} for _ in range(5)],
        ))
        result = await engine.recommend_price("t1", "Standard", "2026-04-20")
        assert result["competitor_data"]["available"] is False
        assert result["recommended_price"] > 0
        assert any("Rakip verisi yok" in r for r in result["applied_rules"])

    @pytest.mark.asyncio
    async def test_resolve_base_price_tenant_room_type_and_fallback(self):
        # Filtrelemenin GERCEKTEN sinanmasi: yanlis tenant/room_type sizmamali.
        from domains.ai.dynamic_pricing_engine import DynamicPricingEngine
        eng = DynamicPricingEngine(FakeDB(rooms=[
            {"tenant_id": "t1", "room_type": "Standard", "base_price": 100},
            {"tenant_id": "t1", "room_type": "Deluxe", "base_price": 200},
            {"tenant_id": "t2", "room_type": "Standard", "base_price": 999},
        ]))
        # room_type'a ozel ortalama
        assert await eng._resolve_base_price("t1", "Standard") == 100
        assert await eng._resolve_base_price("t1", "Deluxe") == 200
        # cross-tenant haric: t2'nin 999'u t1'e sizmaz
        assert await eng._resolve_base_price("t1", "Standard") != 999
        assert await eng._resolve_base_price("t2", "Standard") == 999
        # t1'de olmayan oda tipi -> None (room_type ozel sorgu)
        assert await eng._resolve_base_price("t1", "Suite") is None
        # mulk geneli fallback (room_type yok) -> (100+200)/2 = 150
        assert await eng._resolve_base_price("t1", None) == 150


class TestPredictiveEngine:
    def setup_method(self):
        from domains.ai.predictive_engine import PredictiveEngine
        self.db = FakeDB(
            rooms=[{"tenant_id": "t1", "room_type": "Standard", "base_price": 100} for _ in range(4)],
            bookings=[
                {
                    "id": "b1", "tenant_id": "t1", "guest_id": "g1",
                    "check_in": "2026-04-20T14:00:00", "check_out": "2027-01-01T11:00:00",
                    "status": "confirmed",
                    "channel": "booking_com", "payment_method": None,
                    "total_amount": 50, "last_contact_date": None, "created_at": datetime.now(UTC).isoformat()
                },
                {
                    "id": "b2", "tenant_id": "t1", "guest_id": "g2",
                    "check_in": "2026-04-20T14:00:00", "check_out": "2027-01-01T11:00:00",
                    "status": "confirmed",
                    "channel": "direct", "payment_method": "credit_card",
                    "total_amount": 200, "last_contact_date": "2026-04-19", "created_at": datetime.now(UTC).isoformat()
                },
            ],
            reviews=[],
            service_complaints=[],
        )
        self.engine = PredictiveEngine(self.db)

    @pytest.mark.asyncio
    async def test_predict_no_shows_returns_list(self):
        result = await self.engine.predict_no_shows("t1", "2026-04-20")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_high_risk_booking_detected(self):
        result = await self.engine.predict_no_shows("t1", "2026-04-20")
        high_risk = [p for p in result if p["risk_level"] == "high"]
        assert len(high_risk) >= 1
        assert high_risk[0]["booking_id"] == "b1"

    @pytest.mark.asyncio
    async def test_risk_factors_populated(self):
        result = await self.engine.predict_no_shows("t1", "2026-04-20")
        if result:
            assert "factors" in result[0]
            assert isinstance(result[0]["factors"], list)

    def test_get_risk_factors_no_payment(self):
        factors = self.engine._get_risk_factors({"channel": "direct"})
        assert "No payment method" in factors

    def test_get_risk_factors_ota(self):
        factors = self.engine._get_risk_factors({"payment_method": "cc", "channel": "booking_com"})
        assert "OTA booking" in factors

    @pytest.mark.asyncio
    async def test_predict_demand_returns_30_days(self):
        result = await self.engine.predict_demand("t1", 30)
        assert len(result) == 30
        for day in result:
            assert "date" in day
            assert "occupancy_forecast" in day
            assert "demand_level" in day
            assert "recommended_price" in day
            assert 20 <= day["occupancy_forecast"] <= 95

    @pytest.mark.asyncio
    async def test_predict_demand_levels_valid(self):
        result = await self.engine.predict_demand("t1", 7)
        valid_levels = {"very_high", "high", "medium", "low"}
        for day in result:
            assert day["demand_level"] in valid_levels


class TestReputationManager:
    def setup_method(self):
        from domains.ai.reputation_manager import ReputationManager
        _now = datetime.now(UTC).isoformat()
        self.db = FakeDB(
            reviews=[
                {"tenant_id": "t1", "rating": 5, "created_at": datetime.now(UTC).isoformat()},
                {"tenant_id": "t1", "rating": 4, "created_at": datetime.now(UTC).isoformat()},
                {"tenant_id": "t1", "rating": 2, "created_at": (datetime.now(UTC) - timedelta(days=60)).isoformat()},
            ],
            external_reviews=[
                {"tenant_id": "t1", "platform": "google", "rating": 4.5, "review_date": _now},
                {"tenant_id": "t1", "platform": "booking", "rating": 8.0, "review_date": _now},
                {"tenant_id": "t1", "platform": "google", "rating": 5.0, "review_date": _now},
            ],
        )
        self.manager = ReputationManager(self.db)

    @pytest.mark.asyncio
    async def test_aggregate_reviews_structure(self):
        result = await self.manager.aggregate_reviews("t1")
        assert "platforms" in result
        assert "overall_rating" in result
        assert "total_reviews" in result
        assert result["overall_rating"] > 0
        assert result["total_reviews"] > 0

    @pytest.mark.asyncio
    async def test_sentiment_positive(self):
        result = await self.manager.analyze_sentiment("This hotel is amazing and excellent!")
        assert result["sentiment"] == "positive"
        assert result["score"] > 0

    @pytest.mark.asyncio
    async def test_sentiment_negative(self):
        result = await self.manager.analyze_sentiment("This place is terrible and awful")
        assert result["sentiment"] == "negative"
        assert result["score"] < 0

    @pytest.mark.asyncio
    async def test_sentiment_neutral(self):
        result = await self.manager.analyze_sentiment("The room was okay")
        assert result["sentiment"] == "neutral"
        assert result["score"] == 0

    @pytest.mark.asyncio
    async def test_suggest_response_positive(self):
        response = await self.manager.suggest_response("Amazing hotel, excellent service!", 5)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_suggest_response_negative(self):
        response = await self.manager.suggest_response("Terrible experience, awful room", 1)
        assert len(response) > 0
        assert response != await self.manager.suggest_response("Amazing!", 5)

    @pytest.mark.asyncio
    async def test_reputation_trends_structure(self):
        result = await self.manager.get_reputation_trends("t1", 30)
        assert "trend" in result
        assert result["trend"] in {"improving", "declining", "stable"}
        assert "avg_rating" in result
        assert "total_reviews" in result

    @pytest.mark.asyncio
    async def test_reputation_trends_empty_db(self):
        from domains.ai.reputation_manager import ReputationManager as RM
        empty_mgr = RM(FakeDB())
        result = await empty_mgr.get_reputation_trends("t1", 30)
        assert result["trend"] == "stable"
        assert result["total_reviews"] == 0
