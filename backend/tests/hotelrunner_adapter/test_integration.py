"""
HotelRunner Adapter — Integration Tests
=========================================

Tests wiring between the new adapter and the system:
- Provider config flow (test_connection + full validation)
- Reservation pull flow (via legacy dict interface)
- ARI push flow (via legacy update_room interface)
- Snapshot collector flow

Uses mocked HTTP responses to test the full stack without real API calls.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider
from domains.channel_manager.providers.hotelrunner.schemas import ProviderResult
from domains.channel_manager.providers.hotelrunner.client import HttpResult
from domains.channel_manager.providers.hotelrunner.errors import (
    HotelRunnerAuthError,
    HotelRunnerTemporaryError,
)


def _mock_http_result(data=None, success=True, status_code=200, error=""):
    return HttpResult(
        success=success,
        status_code=status_code,
        data=data or {},
        error=error,
        duration_ms=50,
        correlation_id="test-123",
    )


# ══════════════════════════════════════════════════════════════════════
# 1. Provider Config Flow Integration
# ══════════════════════════════════════════════════════════════════════

class TestProviderConfigIntegration:
    """Test that provider config router functions work with new adapter."""

    @pytest.mark.asyncio
    async def test_connection_success(self):
        """test_connection returns ProviderResult on success."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_http_result(
                data={"channels": [{"code": "booking", "name": "Booking.com"}]}
            )
            result = await provider.test_connection()

        assert isinstance(result, ProviderResult)
        assert result.success is True
        assert result.data["connected"] is True
        assert result.data["channel_count"] == 1

    @pytest.mark.asyncio
    async def test_connection_auth_failure(self):
        """test_connection returns error on 401."""
        provider = HotelRunnerProvider(token="bad_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = HotelRunnerAuthError("Invalid token")
            result = await provider.test_connection()

        assert result.success is False
        assert "HotelRunnerAuthError" in result.error_type

    @pytest.mark.asyncio
    async def test_fetch_rooms(self):
        """fetch_rooms returns parsed room data."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_http_result(data={
                "rooms": [
                    {"inv_code": "STD", "name": "Standard", "rate_plans": [{"code": "BAR"}]},
                    {"inv_code": "DLX", "name": "Deluxe"},
                ]
            })
            result = await provider.fetch_rooms()

        assert result.success is True
        assert result.data["room_count"] == 2
        assert result.data["rooms"][0]["inv_code"] == "STD"


# ══════════════════════════════════════════════════════════════════════
# 2. Reservation Pull Flow Integration
# ══════════════════════════════════════════════════════════════════════

class TestReservationPullIntegration:
    """Test that ingest workers can use the new adapter via legacy dict interface."""

    @pytest.mark.asyncio
    async def test_get_reservations_legacy(self):
        """Legacy get_reservations returns dict format."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_http_result(data={
                "reservations": [
                    {
                        "reservation_id": "123",
                        "hr_number": "HR-001",
                        "state": "reserved",
                        "firstname": "Ali",
                        "lastname": "Yilmaz",
                        "checkin_date": "2026-04-10",
                        "checkout_date": "2026-04-15",
                        "total": 5000,
                        "currency": "TRY",
                        "rooms": [{"inv_code": "STD", "total_adult": 2}],
                    }
                ],
                "pages": 1,
                "page": 1,
            })
            result = await provider.get_reservations(
                undelivered=True, per_page=10, page=1,
            )

        assert isinstance(result, dict)
        assert result["success"] is True
        assert len(result["data"]["reservations"]) == 1

    @pytest.mark.asyncio
    async def test_sync_reservations(self):
        """Legacy sync_reservations pulls all undelivered."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = _mock_http_result(data={
                "reservations": [{"hr_number": "HR-001"}, {"hr_number": "HR-002"}],
                "pages": 1,
            })
            result = await provider.sync_reservations()

        assert result["success"] is True
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_multi_page_pull(self):
        """Legacy get_reservations with pagination."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        call_count = 0

        async def mock_get(path, **kwargs):
            nonlocal call_count
            call_count += 1
            params = kwargs.get("params", {})
            page = int(params.get("page", 1))
            if page <= 2:
                return _mock_http_result(data={
                    "reservations": [{"hr_number": f"HR-{page}"}],
                    "pages": 2,
                    "page": page,
                })
            return _mock_http_result(data={"reservations": [], "pages": 2})

        with patch.object(provider._client, "get", side_effect=mock_get):
            result = await provider.sync_reservations()

        assert result["success"] is True
        assert result["count"] == 2


# ══════════════════════════════════════════════════════════════════════
# 3. ARI Push Flow Integration
# ══════════════════════════════════════════════════════════════════════

class TestARIPushIntegration:
    """Test that ARI adapter can use the new provider via legacy interface."""

    @pytest.mark.asyncio
    async def test_update_room_legacy(self):
        """Legacy update_room used by ARI adapter."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "put", new_callable=AsyncMock) as mock_put:
            mock_put.return_value = _mock_http_result(data={"status": "ok"})
            result = await provider.update_room(
                inv_code="STD",
                start_date="2026-04-15",
                end_date="2026-04-20",
                availability=5,
                price=1200,
            )

        assert result["success"] is True
        assert mock_put.called

    @pytest.mark.asyncio
    async def test_push_daily_inventory(self):
        """New push_daily_inventory with mapping."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "put", new_callable=AsyncMock) as mock_put:
            mock_put.return_value = _mock_http_result(data={"status": "ok"})
            result = await provider.push_daily_inventory(
                payload={"date": "2026-04-15", "availability": 5},
                room_mapping={"external_code": "HR-STD"},
            )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_push_date_range_inventory(self):
        """New push_date_range_inventory with mapping."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        with patch.object(provider._client, "put", new_callable=AsyncMock) as mock_put:
            mock_put.return_value = _mock_http_result(data={"status": "ok"})
            result = await provider.push_date_range_inventory(
                payload={
                    "start_date": "2026-04-15",
                    "end_date": "2026-04-20",
                    "availability": 3,
                    "price": 1500,
                },
                room_mapping={"external_code": "HR-DLX"},
            )

        assert result.success is True


# ══════════════════════════════════════════════════════════════════════
# 4. Snapshot Collector Flow Integration
# ══════════════════════════════════════════════════════════════════════

class TestSnapshotCollectorIntegration:
    """Test snapshot collector compatibility with new adapter."""

    @pytest.mark.asyncio
    async def test_canonical_mapping(self):
        """Provider map_reservation_to_canonical works with raw data."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")

        raw = {
            "reservation_id": "123",
            "hr_number": "HR-001",
            "state": "reserved",
            "firstname": "Ali",
            "lastname": "Yilmaz",
            "checkin_date": "2026-04-10",
            "checkout_date": "2026-04-15",
            "total": 5000,
            "currency": "TRY",
            "rooms": [{"inv_code": "STD", "total_adult": 2}],
        }
        canonical = provider.map_reservation_to_canonical(raw)

        assert canonical["external_reservation_id"] == "HR-001"
        assert canonical["provider"] == "hotelrunner"
        assert canonical["guest_name"] == "Ali Yilmaz"
        assert canonical["status"] == "confirmed"
        assert canonical["room_type_code"] == "STD"
        assert canonical["adults"] == 2


# ══════════════════════════════════════════════════════════════════════
# 5. Error Recovery Integration
# ══════════════════════════════════════════════════════════════════════

class TestErrorRecoveryIntegration:
    """Test retry and error handling across the full stack."""

    @pytest.mark.asyncio
    async def test_temporary_error_retries(self):
        """Temporary errors trigger retries."""
        provider = HotelRunnerProvider(
            token="valid_token_12345", hr_id="hr12345",
            max_retries=2,
        )

        call_count = 0
        async def mock_get(path, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise HotelRunnerTemporaryError("Server error")
            return _mock_http_result(data={"channels": []})

        with patch.object(provider._client, "get", side_effect=mock_get):
            result = await provider.test_connection()

        assert result.success is True
        assert call_count == 3  # 2 retries + 1 success

    @pytest.mark.asyncio
    async def test_auth_error_no_retry(self):
        """Auth errors do not trigger retries."""
        provider = HotelRunnerProvider(
            token="bad_token_12345", hr_id="hr12345",
            max_retries=3,
        )

        call_count = 0
        async def mock_get(path, **kwargs):
            nonlocal call_count
            call_count += 1
            raise HotelRunnerAuthError("Invalid token")

        with patch.object(provider._client, "get", side_effect=mock_get):
            result = await provider.test_connection()

        assert result.success is False
        assert call_count == 1  # No retries for auth errors

    @pytest.mark.asyncio
    async def test_get_usage_stats(self):
        """Legacy usage stats works with observability module."""
        provider = HotelRunnerProvider(token="valid_token_12345", hr_id="hr12345")
        stats = provider.get_usage_stats()
        assert "requests_today" in stats
        assert "daily_remaining" in stats
