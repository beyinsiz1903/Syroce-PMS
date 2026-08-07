"""Offline contract and delivery tests for the canonical Exely ARI path."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from domains.channel_manager.ari.ack_service import process_ack
from domains.channel_manager.ari.adapters.exely_ari_adapter import ExelyARIAdapter
from domains.channel_manager.ari.delta_compiler import compile_delta_exely
from domains.channel_manager.ari.events import ARIChangeEvent, ARIDelta
from domains.channel_manager.ari.events import ProviderResult as ARIProviderResult
from domains.channel_manager.ari.outbound_service import publish_ari_event
from domains.channel_manager.providers.exely.ari_delivery import (
    ExelyARIDeliveryResult,
    deliver_exely_ari,
    preview_exely_ari,
)
from domains.channel_manager.providers.exely.ari_publish import enqueue_exely_ari_update
from domains.channel_manager.providers.exely.errors import ExelyTemporaryError, ExelyValidationError
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.response_parser import parse_ari_update_rs
from domains.channel_manager.providers.exely.soap_builder import (
    build_ari_update_rq,
    build_rate_amount_notif_rq,
)
from domains.channel_manager.providers.hotelrunner.schemas import ProviderResult

pytestmark = pytest.mark.exely_failure_stress

SOAP_SUCCESS = b"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05" Version="1.17">
<Success/></OTA_HotelAvailNotifRS></s:Body></s:Envelope>"""

SOAP_WARNING = b"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05" Version="1.17">
<Success/><Warnings><Warning Code="438">limited</Warning></Warnings>
</OTA_HotelAvailNotifRS></s:Body></s:Envelope>"""

SOAP_REJECTED = b"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05" Version="1.17">
<Errors><Error Code="15">invalid</Error></Errors>
</OTA_HotelAvailNotifRS></s:Body></s:Envelope>"""

SOAP_NO_RESULT = b"""<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05" Version="1.17"/>
</s:Body></s:Envelope>"""


def _update(value=5):
    return {
        "property_id": "PROPERTY",
        "room_type_code": "ROOM",
        "rate_plan_code": "RATE",
        "start_date": "2030-01-01",
        "end_date": "2030-01-02",
        "value": value,
        "currency": "TRY",
    }


class TestExelyGoldenXML:
    def test_availability_uses_protocol_117(self):
        xml = build_ari_update_rq("u", "p", "H", "R", "RP", "2030-01-01", "2030-01-02", availability=4)
        assert 'Version="1.17"' in xml
        assert 'BookingLimit="4"' in xml

    def test_rate_uses_protocol_117(self):
        xml = build_rate_amount_notif_rq("u", "p", "H", "R", "RP", "2030-01-01", "2030-01-02", 123.45, "TRY")
        assert 'Version="1.17"' in xml
        assert 'AmountAfterTax="123.45"' in xml

    def test_stop_sell_is_not_cta(self):
        xml = build_ari_update_rq("u", "p", "H", "R", "RP", "2030-01-01", "2030-01-02", stop_sell=True)
        assert "RestrictionStatus" in xml
        assert 'Status="Close"' in xml
        assert 'Restriction="Arrival"' not in xml

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"min_stay": 2}, 'MinMaxMessageType="SetMinLOS"'),
            ({"max_stay": 7}, 'MinMaxMessageType="SetMaxLOS"'),
            ({"cta": True}, 'Restriction="Arrival"'),
            ({"ctd": True}, 'Restriction="Departure"'),
        ],
    )
    def test_restriction_contracts(self, kwargs, expected):
        xml = build_ari_update_rq("u", "p", "H", "R", "RP", "2030-01-01", "2030-01-02", **kwargs)
        assert expected in xml

    def test_min_los_arrival_is_explicit(self):
        xml = build_ari_update_rq("u", "p", "H", "R", "RP", "2030-01-01", "2030-01-02", min_los_arrival=3)
        assert 'ArrivalDateBased="true"' in xml
        assert 'MinMaxMessageType="SetMinLOS"' in xml


class TestExelyARIResponseContract:
    def test_explicit_success(self):
        assert parse_ari_update_rs(SOAP_SUCCESS)["result_class"] == "SUCCESS"

    def test_warning_success_preserves_safe_code(self):
        result = parse_ari_update_rs(SOAP_WARNING)
        assert result["success"] is True
        assert result["result_class"] == "WARNING_SUCCESS"
        assert result["warning_codes"] == ["438"]

    def test_errors_are_rejected(self):
        result = parse_ari_update_rs(SOAP_REJECTED)
        assert result["success"] is False
        assert result["result_class"] == "REJECTED"
        assert result["provider_codes"] == ["15"]

    def test_missing_explicit_success_is_malformed(self):
        result = parse_ari_update_rs(SOAP_NO_RESULT)
        assert result["success"] is False
        assert result["result_class"] == "MALFORMED"


class TestExelySingleWriteProvider:
    @pytest.mark.asyncio
    async def test_one_operation_makes_one_transport_call(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H", max_retries=5)
        provider._transport.send_soap = AsyncMock(return_value=SOAP_SUCCESS)
        result = await provider.push_ari(
            room_type_code="R",
            rate_plan_code="RP",
            start_date="2030-01-01",
            end_date="2030-01-02",
            availability=4,
        )
        assert result.success is True
        assert provider._transport.send_soap.await_count == 1
        assert result.metadata["provider_write_count"] == 1

    @pytest.mark.asyncio
    async def test_multiple_operations_fail_before_transport(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H")
        provider._transport.send_soap = AsyncMock()
        with pytest.raises(ExelyValidationError, match="Exactly one"):
            await provider.push_ari(
                room_type_code="R",
                rate_plan_code="RP",
                start_date="2030-01-01",
                end_date="2030-01-02",
                availability=4,
                stop_sell=True,
            )
        provider._transport.send_soap.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_temporary_error_is_not_retried(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H", max_retries=9)
        provider._transport.send_soap = AsyncMock(side_effect=ExelyTemporaryError("temporary"))
        result = await provider.push_ari(
            room_type_code="R",
            rate_plan_code="RP",
            start_date="2030-01-01",
            end_date="2030-01-02",
            availability=4,
        )
        assert result.success is False
        assert result.error_type == "ExelyTemporaryError"
        assert result.metadata["classification"] == "AMBIGUOUS"
        assert result.metadata["provider_status_class"] == "WRITE_OUTCOME_UNKNOWN"
        assert result.metadata["provider_write_count"] == 1
        assert provider._transport.send_soap.await_count == 1


class TestExelyDurableDelivery:
    @pytest.mark.asyncio
    async def test_dry_run_is_not_success_and_writes_zero(self):
        result = preview_exely_ari("availability", {"tenant_id": "T", **_update()})
        assert result.success is False
        assert result.state == "dry_run"
        assert result.provider_write_count == 0

    def test_operation_identity_is_distinct_from_payload_fingerprint(self):
        first = preview_exely_ari(
            "availability",
            {"tenant_id": "T", **_update(), "operation_identity": "change-1"},
        )
        second = preview_exely_ari(
            "availability",
            {"tenant_id": "T", **_update(), "operation_identity": "change-2"},
        )
        assert first.operation_identity != second.operation_identity

    @pytest.mark.asyncio
    async def test_confirmed_delivery_persists_and_writes_once(self):
        provider = AsyncMock()
        provider.push_ari_operation.return_value = ProviderResult(
            success=True,
            metadata={"provider_status_class": "SUCCESS", "provider_write_count": 1},
        )
        with (
            patch("domains.channel_manager.providers.exely.ari_delivery._prepare_delivery", new=AsyncMock(return_value=(True, None))),
            patch("domains.channel_manager.providers.exely.ari_delivery._mark_sending", new=AsyncMock(return_value=True)),
            patch("domains.channel_manager.providers.exely.ari_delivery._finish", new=AsyncMock(return_value=True)),
        ):
            result = await deliver_exely_ari("T", "availability", _update(), provider=provider, write_enabled=True)
        assert result.success is True
        assert result.state == "confirmed"
        assert result.provider_write_count == 1
        provider.push_ari_operation.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_timeout_is_ambiguous_and_never_retried(self):
        provider = AsyncMock()
        provider.push_ari_operation.side_effect = TimeoutError("unknown")
        with (
            patch("domains.channel_manager.providers.exely.ari_delivery._prepare_delivery", new=AsyncMock(return_value=(True, None))),
            patch("domains.channel_manager.providers.exely.ari_delivery._mark_sending", new=AsyncMock(return_value=True)),
            patch("domains.channel_manager.providers.exely.ari_delivery._finish", new=AsyncMock(return_value=True)),
        ):
            result = await deliver_exely_ari("T", "availability", _update(), provider=provider, write_enabled=True)
        assert result.success is False
        assert result.state == "ambiguous"
        assert result.provider_write_count == 1
        provider.push_ari_operation.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_definitive_rejection_is_not_success(self):
        provider = AsyncMock()
        provider.push_ari_operation.return_value = ProviderResult(
            success=False,
            error_type="REJECTED",
            metadata={"provider_status_class": "REJECTED", "provider_write_count": 1},
        )
        with (
            patch("domains.channel_manager.providers.exely.ari_delivery._prepare_delivery", new=AsyncMock(return_value=(True, None))),
            patch("domains.channel_manager.providers.exely.ari_delivery._mark_sending", new=AsyncMock(return_value=True)),
            patch("domains.channel_manager.providers.exely.ari_delivery._finish", new=AsyncMock(return_value=True)),
        ):
            result = await deliver_exely_ari("T", "availability", _update(), provider=provider, write_enabled=True)
        assert result.success is False
        assert result.state == "rejected"
        assert result.provider_status_class == "DEFINITIVE_REJECTION"

    @pytest.mark.asyncio
    async def test_duplicate_confirmed_operation_does_not_write(self):
        provider = AsyncMock()
        with patch(
            "domains.channel_manager.providers.exely.ari_delivery._prepare_delivery",
            new=AsyncMock(return_value=(False, {"state": "confirmed"})),
        ):
            result = await deliver_exely_ari("T", "availability", _update(), provider=provider, write_enabled=True)
        assert result.success is True
        assert result.provider_write_count == 0
        provider.push_ari_operation.assert_not_awaited()


class TestExelyCanonicalOutbox:
    @pytest.mark.asyncio
    async def test_publish_is_durable_before_returning(self):
        event = ARIChangeEvent(
            tenant_id="T",
            property_id="P",
            source_service="test",
            event_type="availability",
            room_type_code="R",
            rate_plan_code="RP",
            date_from=date(2030, 1, 1),
            date_to=date(2030, 1, 2),
            payload={"operation": "availability", "availability": 4},
            target_provider="exely",
        )
        order = []

        async def insert(_event):
            order.append("event")

        async def upsert(_change_set):
            order.append("change_set")
            return "CS"

        with (
            patch("domains.channel_manager.ari.outbound_service.repo.insert_ari_event", side_effect=insert),
            patch("domains.channel_manager.ari.outbound_service.repo.upsert_change_set", side_effect=upsert),
            patch("services.b2b_streams.publish_ari_to_agency_streams", new=AsyncMock()),
        ):
            result = await publish_ari_event(event)
        assert order == ["change_set", "event"]
        assert result["durable"] is True
        assert result["change_set_ids"] == ["CS"]

    @pytest.mark.asyncio
    async def test_publisher_splits_operations_into_durable_events(self):
        captured = []

        async def fake_publish(event):
            captured.append(event)
            return {"durable": True}

        with patch("domains.channel_manager.providers.exely.ari_publish.publish_ari_event", side_effect=fake_publish):
            result = await enqueue_exely_ari_update(
                "T",
                "P",
                "R",
                "RP",
                "2030-01-01",
                "2030-01-02",
                source_service="test",
                availability=4,
                stop_sell=True,
                cta=False,
            )
        assert result["queued_operation_count"] == 3
        assert result["provider_write_count"] == 0
        assert [event.payload["operation"] for event in captured] == ["availability", "stop_sell", "cta"]
        assert all(event.target_provider == "exely" for event in captured)

    def test_compiler_preserves_explicit_restriction_operation(self):
        delta = compile_delta_exely(
            {
                "tenant_id": "T",
                "property_id": "P",
                "provider": "exely",
                "change_scope": "restriction",
                "room_type_code": "R",
                "rate_plan_code": "RP",
                "date_from": "2030-01-01",
                "date_to": "2030-01-02",
                "compacted_payload": {"operation": "ctd", "ctd": True},
            }
        )
        assert delta.payload == {"operation": "ctd", "value": True}

    @pytest.mark.asyncio
    async def test_adapter_never_returns_fake_dry_run_success(self):
        delta = ARIDelta(
            provider="exely",
            tenant_id="T",
            property_id="P",
            change_scope="availability",
            room_type_code="R",
            rate_plan_code="RP",
            date_from=date(2030, 1, 1),
            date_to=date(2030, 1, 2),
            payload={"operation": "availability", "value": 4},
        )
        blocked = ExelyARIDeliveryResult(False, "blocked", "WRITE_DISABLED", "NOT_SENT", 0, "a" * 64)
        with patch(
            "domains.channel_manager.ari.adapters.exely_ari_adapter.deliver_exely_ari",
            new=AsyncMock(return_value=blocked),
        ):
            result = await ExelyARIAdapter().push_availability(delta)
        assert result.success is False
        assert result.delivery_state == "blocked"
        assert result.provider_write_count == 0

    @pytest.mark.asyncio
    async def test_exely_429_does_not_enter_retry_queue(self):
        change_set = {
            "id": "CS",
            "tenant_id": "T",
            "property_id": "P",
            "provider": "exely",
            "change_scope": "rate",
            "outbound_attempt_count": 1,
            "compacted_payload": {"base_rate": 1},
        }
        result = ARIProviderResult(
            success=False,
            provider="exely",
            status_code=429,
            error="RATE_LIMITED",
            delivery_state="rejected",
            provider_write_count=1,
        )
        with (
            patch("domains.channel_manager.ari.ack_service.repo.insert_outbound_log", new=AsyncMock()),
            patch("domains.channel_manager.ari.ack_service.repo.update_change_set_status", new=AsyncMock()) as update,
        ):
            status = await process_ack(change_set, result, "OUT")
        assert status == "manual_review"
        assert update.await_args.args[1] == "manual_review"

    def test_active_exely_mutation_paths_use_canonical_delivery(self):
        from pathlib import Path

        root = Path(__file__).parents[1] / "domains" / "channel_manager"
        active_paths = (
            root / "rate_manager_router.py",
            root / "unified_rate_manager_router.py",
            root / "availability_auto_sync.py",
            root / "availability_reconciliation_worker.py",
            root / "providers" / "exely" / "exely_router.py",
        )
        for path in active_paths:
            assert ".push_ari(" not in path.read_text(encoding="utf-8"), path
