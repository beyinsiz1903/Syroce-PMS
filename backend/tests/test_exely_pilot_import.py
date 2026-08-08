"""Offline contract tests for the persistent Exely reservation import pilot."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import OperationFailure

from domains.channel_manager.providers.exely import pilot_import

pytestmark = pytest.mark.exely_failure_stress


class _Collection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    async def find_one(self, query, projection=None):
        document = next(
            (row for row in self.documents if all(row.get(key) == value for key, value in query.items())),
            None,
        )
        if document is None:
            return None
        if not projection:
            return deepcopy(document)
        included_keys = [key for key, included in projection.items() if included and key != "_id"]
        if not included_keys:
            result = deepcopy(document)
            for key, included in projection.items():
                if not included:
                    result.pop(key, None)
            return result
        return {key: deepcopy(document[key]) for key, included in projection.items() if included and key != "_id" and key in document}

    async def insert_one(self, document):
        self.documents.append(deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("id"))


class _DB:
    def __init__(self):
        self.exely_room_mappings = _Collection()
        self.exely_reservations = _Collection()
        self.exely_reservation_versions = _Collection()
        self.bookings = _Collection()


@pytest.mark.asyncio
async def test_persistence_preflight_redacts_database_auth_failure(monkeypatch):
    sensitive = "synthetic-sensitive-database-detail"
    mapping = AsyncMock()
    monkeypatch.setattr(
        pilot_import,
        "ensure_pilot_schema",
        AsyncMock(side_effect=OperationFailure(sensitive)),
    )
    monkeypatch.setattr(pilot_import, "ensure_pilot_mapping", mapping)

    with pytest.raises(
        pilot_import.PilotImportError,
        match="BLOCKED_PERSISTENT_TEST_DB_PREFLIGHT_FAILED",
    ) as exc_info:
        await pilot_import.prepare_pilot_persistence(
            "tenant",
            room_type_code="synthetic-room",
            rate_plan_code="synthetic-rate",
            pms_room_type="Synthetic Standard",
        )

    assert sensitive not in str(exc_info.value)
    mapping.assert_not_awaited()


def _raw_reservation(*, room="synthetic-room", rate="synthetic-rate"):
    return {
        "reservation_id": "synthetic-reservation",
        "last_modify": "2030-01-01T10:00:00Z",
        "create_date": "2030-01-01T09:00:00Z",
        "status": "commit",
        "rooms": [
            {
                "index_number": "1",
                "room_type_code": room,
                "rate_plan_code": rate,
            }
        ],
    }


def _verification(**overrides):
    values = {
        "durable_pms_state": True,
        "lineage_match": True,
        "version_match": True,
        "ack_state_pending": True,
        "ack_reservation_id_present": True,
        "ack_confirmation_id_present": True,
        "ack_create_datetime_present": True,
        "ack_last_modify_datetime_present": True,
        "booking_count": 1,
    }
    values.update(overrides)
    return pilot_import.DurableImportVerification(**values)


@pytest.mark.parametrize(
    ("raw", "room", "rate"),
    [
        ({"rooms": []}, "synthetic-room", "synthetic-rate"),
        (_raw_reservation(room="other-room"), "synthetic-room", "synthetic-rate"),
        (_raw_reservation(rate="other-rate"), "synthetic-room", "synthetic-rate"),
    ],
)
def test_exact_mapping_mismatch_fails_closed(raw, room, rate):
    with pytest.raises(
        pilot_import.PilotImportError,
        match="BLOCKED_PILOT_MAPPING_NOT_DISCOVERED",
    ):
        pilot_import.validate_exact_mapping(
            raw,
            room_type_code=room,
            rate_plan_code=rate,
        )


@pytest.mark.asyncio
async def test_mapping_conflict_fails_closed(monkeypatch):
    database = _DB()
    database.exely_room_mappings.documents.append(
        {
            "tenant_id": "tenant",
            "exely_room_code": "synthetic-room",
            "exely_rate_plan_code": "synthetic-rate",
            "pms_room_type": "Unexpected Type",
        }
    )
    monkeypatch.setattr(pilot_import, "db", database)

    with pytest.raises(pilot_import.PilotImportError, match="BLOCKED_PILOT_MAPPING_CONFLICT"):
        await pilot_import.ensure_pilot_mapping(
            "tenant",
            room_type_code="synthetic-room",
            rate_plan_code="synthetic-rate",
            pms_room_type="Synthetic Standard",
        )


@pytest.mark.asyncio
async def test_canonical_persistence_failure_is_blocked(monkeypatch):
    monkeypatch.setattr(pilot_import, "ensure_pilot_schema", AsyncMock())
    monkeypatch.setattr(pilot_import, "ensure_pilot_mapping", AsyncMock(return_value=1))
    monkeypatch.setattr(
        pilot_import,
        "ingest_reservation",
        AsyncMock(return_value={"success": False, "action": "error"}),
    )

    with pytest.raises(
        pilot_import.PilotImportError,
        match="BLOCKED_CANONICAL_PERSISTENCE_FAILED",
    ):
        await pilot_import.import_reservation_durably(
            "tenant",
            "property",
            _raw_reservation(),
            room_type_code="synthetic-room",
            rate_plan_code="synthetic-rate",
            pms_room_type="Synthetic Standard",
        )


@pytest.mark.asyncio
async def test_lifecycle_failure_is_blocked(monkeypatch):
    database = _DB()
    database.exely_reservations.documents.append(
        {
            "tenant_id": "tenant",
            "property_id": "property",
            "external_id": "synthetic-reservation",
        }
    )
    monkeypatch.setattr(pilot_import, "db", database)
    monkeypatch.setattr(pilot_import, "ensure_pilot_schema", AsyncMock())
    monkeypatch.setattr(pilot_import, "ensure_pilot_mapping", AsyncMock(return_value=0))
    monkeypatch.setattr(
        pilot_import,
        "ingest_reservation",
        AsyncMock(return_value={"success": True, "action": "created"}),
    )
    monkeypatch.setattr(
        pilot_import,
        "process_reservation_version",
        AsyncMock(return_value={"success": False, "reason": "PMS_FAILED"}),
    )

    with pytest.raises(
        pilot_import.PilotImportError,
        match="BLOCKED_CANONICAL_LIFECYCLE_FAILED",
    ):
        await pilot_import.import_reservation_durably(
            "tenant",
            "property",
            _raw_reservation(),
            room_type_code="synthetic-room",
            rate_plan_code="synthetic-rate",
            pms_room_type="Synthetic Standard",
        )


@pytest.mark.asyncio
async def test_durable_readback_failure_is_blocked(monkeypatch):
    database = _DB()
    database.exely_reservations.documents.append(
        {
            "tenant_id": "tenant",
            "property_id": "property",
            "external_id": "synthetic-reservation",
        }
    )
    monkeypatch.setattr(pilot_import, "db", database)
    monkeypatch.setattr(pilot_import, "ensure_pilot_schema", AsyncMock())
    monkeypatch.setattr(pilot_import, "ensure_pilot_mapping", AsyncMock(return_value=0))
    monkeypatch.setattr(
        pilot_import,
        "ingest_reservation",
        AsyncMock(return_value={"success": True, "action": "created"}),
    )
    monkeypatch.setattr(
        pilot_import,
        "process_reservation_version",
        AsyncMock(return_value={"success": True, "created": 1}),
    )
    monkeypatch.setattr(
        pilot_import,
        "verify_durable_import",
        AsyncMock(return_value=_verification(lineage_match=False)),
    )

    with pytest.raises(
        pilot_import.PilotImportError,
        match="BLOCKED_DURABLE_PMS_READBACK_FAILED",
    ):
        await pilot_import.import_reservation_durably(
            "tenant",
            "property",
            _raw_reservation(),
            room_type_code="synthetic-room",
            rate_plan_code="synthetic-rate",
            pms_room_type="Synthetic Standard",
        )


@pytest.mark.asyncio
async def test_duplicate_durable_import_is_idempotent(monkeypatch):
    database = _DB()
    database.exely_reservations.documents.append(
        {
            "tenant_id": "tenant",
            "property_id": "property",
            "external_id": "synthetic-reservation",
        }
    )
    monkeypatch.setattr(pilot_import, "db", database)
    monkeypatch.setattr(pilot_import, "ensure_pilot_schema", AsyncMock())
    monkeypatch.setattr(pilot_import, "ensure_pilot_mapping", AsyncMock(return_value=0))
    monkeypatch.setattr(
        pilot_import,
        "ingest_reservation",
        AsyncMock(return_value={"success": True, "action": "duplicate"}),
    )
    monkeypatch.setattr(
        pilot_import,
        "process_reservation_version",
        AsyncMock(return_value={"success": True, "reason": "ALREADY_DURABLE"}),
    )
    monkeypatch.setattr(
        pilot_import,
        "verify_durable_import",
        AsyncMock(return_value=_verification()),
    )

    result = await pilot_import.import_reservation_durably(
        "tenant",
        "property",
        _raw_reservation(),
        room_type_code="synthetic-room",
        rate_plan_code="synthetic-rate",
        pms_room_type="Synthetic Standard",
    )

    assert result.already_durable is True
    assert result.local_pms_write_count == 0
    pilot_import.process_reservation_version.assert_awaited_once()


@pytest.mark.asyncio
async def test_readback_requires_exact_lineage_version_and_pending_ack(monkeypatch):
    database = _DB()
    database.exely_reservations.documents.append(
        {
            "tenant_id": "tenant",
            "property_id": "property",
            "external_id": "synthetic-reservation",
            "provider_version_identity": "identity",
            "provider_version_key": "2030-01-01T10:00:00Z",
            "delivery_state": "PENDING",
            "room_stay_lineage": [
                {"pms_booking_id": "booking", "active": True},
            ],
        }
    )
    database.exely_reservation_versions.documents.append(
        {
            "tenant_id": "tenant",
            "version_identity": "identity",
            "provider_reservation_id": "synthetic-reservation",
            "provider_version_key": "2030-01-01T10:00:00Z",
            "processing_state": "PMS_DURABLE",
            "ack_state": "PENDING",
            "room_stays": [
                {
                    "room_type_code": "synthetic-room",
                    "rate_plan_code": "synthetic-rate",
                }
            ],
            "ack_confirmations": [
                {"pms_booking_id": "booking", "pms_created_at": "2030-01-01T10:01:00Z"},
            ],
            "durable_expectations": [
                {"pms_booking_id": "booking", "status": "confirmed"},
            ],
        }
    )
    database.bookings.documents.append(
        {
            "tenant_id": "tenant",
            "id": "booking",
            "status": "confirmed",
            "provider_version_key": "2030-01-01T10:00:00Z",
        }
    )
    monkeypatch.setattr(pilot_import, "db", database)

    result = await pilot_import.verify_durable_import(
        "tenant",
        "property",
        _raw_reservation(),
        room_type_code="synthetic-room",
        rate_plan_code="synthetic-rate",
    )

    assert result.success is True
    assert result.booking_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_version_key", "2030-01-01T10:01:00Z"),
        ("processing_state", "PMS_FAILED"),
        ("ack_state", "NOT_READY"),
    ],
)
async def test_readback_mismatch_blocks_ack_readiness(monkeypatch, field, value):
    database = _DB()
    database.exely_reservations.documents.append(
        {
            "tenant_id": "tenant",
            "property_id": "property",
            "external_id": "synthetic-reservation",
            "provider_version_identity": "identity",
            "provider_version_key": "2030-01-01T10:00:00Z",
            "delivery_state": "PENDING",
            "room_stay_lineage": [{"pms_booking_id": "booking", "active": True}],
        }
    )
    version = {
        "tenant_id": "tenant",
        "version_identity": "identity",
        "provider_reservation_id": "synthetic-reservation",
        "provider_version_key": "2030-01-01T10:00:00Z",
        "processing_state": "PMS_DURABLE",
        "ack_state": "PENDING",
        "room_stays": [
            {
                "room_type_code": "synthetic-room",
                "rate_plan_code": "synthetic-rate",
            }
        ],
        "ack_confirmations": [
            {"pms_booking_id": "booking", "pms_created_at": "2030-01-01T10:01:00Z"},
        ],
        "durable_expectations": [{"pms_booking_id": "booking", "status": "confirmed"}],
    }
    version[field] = value
    database.exely_reservation_versions.documents.append(version)
    database.bookings.documents.append(
        {
            "tenant_id": "tenant",
            "id": "booking",
            "status": "confirmed",
            "provider_version_key": "2030-01-01T10:00:00Z",
        }
    )
    monkeypatch.setattr(pilot_import, "db", database)

    verification = await pilot_import.verify_durable_import(
        "tenant",
        "property",
        _raw_reservation(),
        room_type_code="synthetic-room",
        rate_plan_code="synthetic-rate",
    )

    assert verification.success is False


@pytest.mark.asyncio
async def test_ack_loader_blocks_when_durable_state_is_not_verified(monkeypatch):
    monkeypatch.setattr(
        pilot_import,
        "verify_durable_import",
        AsyncMock(return_value=_verification(ack_state_pending=False)),
    )

    with pytest.raises(
        pilot_import.PilotImportError,
        match="BLOCKED_ACK_DURABLE_STATE_NOT_VERIFIED",
    ):
        await pilot_import.load_ack_ready_reservation(
            "tenant",
            "property",
            _raw_reservation(),
            room_type_code="synthetic-room",
            rate_plan_code="synthetic-rate",
        )
