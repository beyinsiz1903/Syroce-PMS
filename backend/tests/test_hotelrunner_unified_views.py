from types import SimpleNamespace

import pytest

from domains.channel_manager.ingest.normalizer import normalize_hotelrunner
from domains.channel_manager.providers.hotelrunner.router_internal import (
    _event_log_view,
    _reservation_view,
    get_local_reservations,
    get_sync_logs,
)


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *_args):
        return self

    async def to_list(self, limit):
        return self.docs[:limit]


class _Collection:
    def __init__(self, docs):
        self.docs = list(docs)
        self.queries = []

    def find(self, query, projection):
        self.queries.append((query, projection))
        return _Cursor(self.docs)


def test_hotelrunner_normalizer_preserves_physical_room_number():
    canonical = normalize_hotelrunner(
        {
            "hr_number": "R300461997",
            "firstname": "Callback",
            "lastname": "Test",
            "checkin_date": "2026-08-31",
            "checkout_date": "2026-09-01",
            "rooms": [{"inv_code": "HR:704309", "rate_code": "HR:704309", "number": "202"}],
        }
    )

    assert canonical["room_type_code"] == "HR:704309"
    assert canonical["provider_room_number"] == "202"


def test_unified_reservation_view_reports_provider_pms_room_mismatch_without_raw_payload():
    event = {
        "id": "event-1",
        "external_reservation_id": "R300461997",
        "event_type": "reservation_create",
        "received_via": "webhook",
        "received_at": "2026-08-25T11:32:58+00:00",
        "processing_status": "processed",
        "normalization_result": {
            "external_reservation_id": "R300461997",
            "guest_name": "Callback Test",
            "check_in": "2026-08-31",
            "check_out": "2026-09-01",
            "room_type_code": "HR:704309",
            "provider_room_number": "202",
            "source_system": "online",
            "status": "confirmed",
            "currency": "TRY",
            "total_amount": 0,
        },
        "raw_payload": {"guest_email": "must-not-leak@example.com"},
    }
    view = _reservation_view(
        event,
        {"id": "booking-1", "status": "confirmed", "room_number": "201"},
        {"import_status": "imported"},
    )

    assert view["provider_room_number"] == "202"
    assert view["pms_room_number"] == "201"
    assert view["room_assignment_matches"] is False
    assert view["pms_status"] == "imported"
    assert "raw_payload" not in view
    assert "guest_email" not in view


def test_unified_event_log_exposes_real_callback_processing_duration():
    view = _event_log_view(
        {
            "id": "event-1",
            "external_reservation_id": "R300461997",
            "event_type": "reservation_create",
            "received_via": "webhook",
            "received_at": "2026-08-25T11:32:58.284000+00:00",
            "processed_at": "2026-08-25T11:32:58.789000+00:00",
            "processing_status": "processed",
            "decision_result": "create",
        }
    )

    assert view["status"] == "success"
    assert view["initiator"] == "webhook"
    assert view["duration_ms"] == 505
    assert view["external_reservation_id"] == "R300461997"


@pytest.mark.asyncio
async def test_internal_endpoints_read_authoritative_unified_collections(monkeypatch):
    event = {
        "id": "event-1",
        "external_reservation_id": "R300461997",
        "event_type": "reservation_create",
        "received_via": "webhook",
        "received_at": "2026-08-25T11:32:58.284000+00:00",
        "processed_at": "2026-08-25T11:32:58.789000+00:00",
        "processing_status": "processed",
        "decision_result": "create",
        "normalization_result": {
            "external_reservation_id": "R300461997",
            "guest_name": "Callback Test",
            "check_in": "2026-08-31",
            "check_out": "2026-09-01",
            "provider_room_number": "202",
        },
    }
    fake_db = SimpleNamespace(
        raw_channel_events=_Collection([event]),
        bookings=_Collection(
            [
                {
                    "id": "booking-1",
                    "external_reservation_id": "R300461997",
                    "status": "confirmed",
                    "room_number": "202",
                }
            ]
        ),
        imported_reservations=_Collection(
            [{"external_reservation_id": "R300461997", "import_status": "imported"}]
        ),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.router_internal.db", fake_db
    )
    user = SimpleNamespace(tenant_id="tenant-1")

    reservations = await get_local_reservations(current_user=user)
    logs = await get_sync_logs(limit=20, current_user=user)

    assert reservations["source"] == "unified_ingest"
    assert reservations["reservations"][0]["room_assignment_matches"] is True
    assert logs["source"] == "unified_ingest"
    assert logs["logs"][0]["external_reservation_id"] == "R300461997"
    assert fake_db.raw_channel_events.queries[0][0] == {
        "tenant_id": "tenant-1",
        "provider": "hotelrunner",
    }
