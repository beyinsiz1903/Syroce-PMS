from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

from domains.channel_manager.providers.exely import lifecycle

pytestmark = pytest.mark.exely_failure_stress


def _canonical(version: str = "2030-01-01T10:00:00Z") -> dict:
    return {
        "external_id": "provider-reservation",
        "provider_reservation_id": "provider-reservation",
        "provider_reservation_id_context": "context",
        "property_id": "property",
        "provider_last_modified_at": version,
        "provider_created_at": "2030-01-01T09:00:00Z",
        "channel": "direct",
        "channel_display": "Direct",
        "status": "confirmed",
        "guest": {
            "name": "Synthetic Guest",
            "first_name": "Synthetic",
            "last_name": "Guest",
            "email": "",
            "phone": "",
            "country": "",
        },
        "stay": {"check_in": "2030-01-01", "check_out": "2030-01-02", "nights": 1},
        "financial": {"total_amount": 100, "currency": "USD", "payment_method": ""},
        "rooms": [
            {
                "index_number": "1",
                "room_type_code": "STD",
                "rate_plan_code": "BAR",
                "amount": 100,
            }
        ],
        "total_rooms": 1,
        "total_guests": 1,
        "notes": "",
        "ingested_via": "pull",
        "message_uid": "provider-reservation",
    }


def _winner(version: str, payload_hash: str) -> dict:
    return {
        "id": "winner",
        "provider_version_key": version,
        "provider_version_identity": lifecycle.version_identity(
            "tenant",
            "property",
            "provider-reservation",
            version,
        ),
        "provider_payload_hash": payload_hash,
        "pms_booking_ids": [],
        "pms_booking_id": None,
    }


def _database(*, winner: dict, update_results: list) -> SimpleNamespace:
    return SimpleNamespace(
        exely_reservation_versions=SimpleNamespace(update_one=AsyncMock()),
        exely_reservations=SimpleNamespace(
            find_one=AsyncMock(side_effect=[None, winner]),
            update_one=AsyncMock(side_effect=update_results),
        ),
        exely_room_mappings=SimpleNamespace(find_one=AsyncMock(return_value={"pms_room_type": "Standard"})),
    )


@pytest.mark.asyncio
async def test_concurrent_current_upsert_is_idempotent_and_redacted(monkeypatch, caplog):
    sensitive_error = "tenant=synthetic-tenant external=synthetic-reservation"
    database = _database(
        winner=_winner("2030-01-01T10:00:00Z", "same-hash"),
        update_results=[DuplicateKeyError(sensitive_error)],
    )
    monkeypatch.setattr(lifecycle, "db", database)

    result = await lifecycle.persist_exely_event(
        "tenant",
        _canonical(),
        "reservation",
        "event",
        "same-hash",
    )

    assert result == {
        "action": "skip",
        "reason": "duplicate_payload",
        "external_id": "provider-reservation",
    }
    assert sensitive_error not in caplog.text
    assert database.exely_reservations.update_one.await_count == 1


@pytest.mark.asyncio
async def test_newer_version_retries_once_after_concurrent_insert(monkeypatch):
    older_identity = lifecycle.version_identity(
        "tenant",
        "property",
        "provider-reservation",
        "2030-01-01T09:30:00Z",
    )
    database = _database(
        winner=_winner("2030-01-01T09:30:00Z", "older-hash"),
        update_results=[
            DuplicateKeyError("synthetic duplicate"),
            SimpleNamespace(modified_count=1),
        ],
    )
    monkeypatch.setattr(lifecycle, "db", database)

    result = await lifecycle.persist_exely_event(
        "tenant",
        _canonical(),
        "reservation",
        "event",
        "newer-hash",
    )

    assert result["action"] == "updated"
    assert database.exely_reservations.update_one.await_count == 2
    retry_query = database.exely_reservations.update_one.await_args_list[1].args[0]
    retry_update = database.exely_reservations.update_one.await_args_list[1].args[1]
    assert retry_query == {
        "tenant_id": "tenant",
        "external_id": "provider-reservation",
        "provider_version_identity": older_identity,
    }
    assert retry_update["$set"]["provider_version_key"] == "2030-01-01T10:00:00Z"
    assert retry_update["$set"]["provider_payload_hash"] == "newer-hash"
    assert database.exely_reservations.update_one.await_args_list[1].kwargs == {"upsert": False}
