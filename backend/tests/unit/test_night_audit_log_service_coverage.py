from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import Binary, ObjectId
from bson.decimal128 import Decimal128

from common.context import OperationContext
from domains.pms.night_audit_service import NightAuditService, _sanitize_bson


class AsyncCursor:
    def __init__(self, documents=None, *, error=None):
        self.documents = list(documents or [])
        self.error = error

    def sort(self, *_args, **_kwargs):
        return self

    def skip(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    async def to_list(self, _length=None):
        if self.error:
            raise self.error
        return list(self.documents)

    def __aiter__(self):
        async def generate():
            if self.error:
                raise self.error
            for document in self.documents:
                yield dict(document)

        return generate()


def _collection(*, documents=None, aggregate_documents=None, total=0, modified=1):
    return SimpleNamespace(
        find=MagicMock(return_value=AsyncCursor(documents)),
        aggregate=MagicMock(return_value=AsyncCursor(aggregate_documents)),
        count_documents=AsyncMock(return_value=total),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=modified)),
    )


def _service(**collections):
    service = NightAuditService()
    defaults = {
        "audit_logs": _collection(),
        "error_logs": _collection(),
        "night_audit_logs": _collection(),
        "ota_sync_logs": _collection(),
        "rms_publish_logs": _collection(),
        "maintenance_prediction_logs": _collection(),
    }
    defaults.update(collections)
    service._db = SimpleNamespace(**defaults)
    return service


def _ctx(role="admin", *, super_admin=False):
    return OperationContext(
        tenant_id="tenant-1",
        actor_id="user-1",
        actor_role=role,
        actor_is_super_admin=super_admin,
    )


def test_sanitize_bson_recursively_converts_supported_values():
    object_id = ObjectId()
    moment = datetime(2026, 8, 25, 10, 30, tzinfo=UTC)
    value = {
        "id": object_id,
        "amount": Decimal128("12.50"),
        "payload": Binary(b"\x01\x02"),
        "nested": [moment, {"unchanged": "value"}],
    }

    assert _sanitize_bson(value) == {
        "id": str(object_id),
        "amount": 12.5,
        "payload": "0102",
        "nested": [moment.isoformat(), {"unchanged": "value"}],
    }


@pytest.mark.asyncio
async def test_audit_logs_require_admin_permission():
    service = _service()

    result = await service.get_audit_logs(_ctx("receptionist"))

    assert result.ok is False
    assert result.code == "FORBIDDEN"
    service._db.audit_logs.find.assert_not_called()


@pytest.mark.asyncio
async def test_audit_logs_apply_filters_and_sanitize_results():
    object_id = ObjectId()
    collection = _collection(documents=[{"details": {"legacy_id": object_id}}])
    service = _service(audit_logs=collection)

    result = await service.get_audit_logs(
        _ctx(),
        entity_type="booking",
        entity_id="booking-1",
        user_id="user-2",
        action="update",
        start_date="2026-08-24T00:00:00+00:00",
        end_date="2026-08-25T23:59:59+00:00",
        limit=25,
    )

    assert result.ok is True
    assert result.data["count"] == 1
    assert result.data["logs"][0]["details"]["legacy_id"] == str(object_id)
    query = collection.find.call_args.args[0]
    assert query["tenant_id"] == "tenant-1"
    assert query["entity_type"] == "booking"
    assert query["entity_id"] == "booking-1"
    assert query["user_id"] == "user-2"
    assert query["action"] == "update"
    assert query["timestamp"] == {
        "$gte": "2026-08-24T00:00:00+00:00",
        "$lte": "2026-08-25T23:59:59+00:00",
    }
    assert "tenant_id" not in result.data["filters_applied"]


@pytest.mark.asyncio
async def test_error_logs_filter_paginate_and_build_severity_statistics():
    collection = _collection(
        documents=[{"_id": ObjectId(), "id": "error-1", "severity": "error"}],
        aggregate_documents=[
            {"_id": "error", "count": 3},
            {"_id": "warning", "count": 2},
        ],
        total=5,
    )
    service = _service(error_logs=collection)

    result = await service.get_error_logs(
        _ctx(),
        start_date="2026-08-24",
        end_date="2026-08-25",
        severity="error",
        endpoint="/api/bookings",
        resolved=False,
        limit=20,
        skip=10,
    )

    assert result.ok is True
    assert result.data["logs"] == [{"id": "error-1", "severity": "error"}]
    assert result.data["total_count"] == 5
    assert result.data["severity_stats"] == {"error": 3, "warning": 2}
    query = collection.find.call_args.args[0]
    assert query["timestamp"] == {"$gte": "2026-08-24", "$lte": "2026-08-25"}
    assert query["severity"] == "error"
    assert query["endpoint"]["$options"] == "i"
    assert query["resolved"] is False


@pytest.mark.parametrize(("modified", "expected_ok", "expected_code"), [(1, True, None), (0, False, "NOT_FOUND")])
@pytest.mark.asyncio
async def test_resolve_error_log_handles_found_and_missing_records(modified, expected_ok, expected_code):
    collection = _collection(modified=modified)
    service = _service(error_logs=collection)

    result = await service.resolve_error_log(_ctx(), "error-1", "fixed")

    assert result.ok is expected_ok
    assert result.code == expected_code
    update = collection.update_one.await_args.args[1]["$set"]
    assert update["resolved"] is True
    assert update["resolved_by"] == "user-1"
    assert update["resolution_notes"] == "fixed"


@pytest.mark.asyncio
async def test_night_audit_logs_calculate_totals_and_success_rate():
    collection = _collection(
        documents=[
            {"_id": "mongo-1", "status": "completed", "total_amount": 100, "rooms_processed": 4},
            {"status": "failed", "total_amount": 20, "rooms_processed": 1},
        ],
        total=2,
    )
    service = _service(night_audit_logs=collection)

    result = await service.get_night_audit_logs(
        _ctx(),
        start_date="2026-08-01",
        end_date="2026-08-25",
        status="completed",
        limit=10,
        skip=5,
    )

    assert result.ok is True
    assert result.data["stats"] == {
        "total_audits": 2,
        "successful": 1,
        "failed": 1,
        "total_charges": 120.0,
        "total_rooms": 5,
        "success_rate": 50.0,
    }
    query = collection.find.call_args_list[0].args[0]
    assert query["audit_date"] == {"$gte": "2026-08-01", "$lte": "2026-08-25"}
    assert query["status"] == "completed"


@pytest.mark.asyncio
async def test_empty_night_audit_logs_report_zero_success_rate():
    service = _service(night_audit_logs=_collection(total=0))

    result = await service.get_night_audit_logs(_ctx())

    assert result.data["stats"]["success_rate"] == 0


@pytest.mark.asyncio
async def test_ota_sync_logs_build_per_channel_statistics():
    collection = _collection(
        documents=[{"_id": "mongo-1", "channel": "hotelrunner"}],
        aggregate_documents=[
            {"_id": "hotelrunner", "total": 4, "successful": 3, "failed": 1, "records_synced": 12},
            {"_id": "empty", "total": 0, "successful": 0, "failed": 0, "records_synced": 0},
        ],
        total=1,
    )
    service = _service(ota_sync_logs=collection)

    result = await service.get_ota_sync_logs(
        _ctx(),
        start_date="2026-08-24",
        end_date="2026-08-25",
        channel="hotelrunner",
        sync_type="reservations",
        status="completed",
        limit=10,
        skip=2,
    )

    assert result.ok is True
    assert result.data["channel_stats"]["hotelrunner"] == {
        "total_syncs": 4,
        "successful": 3,
        "failed": 1,
        "success_rate": 75.0,
        "records_synced": 12,
    }
    assert result.data["channel_stats"]["empty"]["success_rate"] == 0
    query = collection.find.call_args.args[0]
    assert query["timestamp"] == {"$gte": "2026-08-24", "$lte": "2026-08-25"}
    assert query["channel"] == "hotelrunner"
    assert query["sync_type"] == "reservations"
    assert query["status"] == "completed"


@pytest.mark.asyncio
async def test_rms_publish_logs_apply_all_filters():
    collection = _collection(documents=[{"_id": "mongo-1", "status": "completed"}], total=1)
    service = _service(rms_publish_logs=collection)

    result = await service.get_rms_publish_logs(
        _ctx(),
        start_date="2026-08-24",
        end_date="2026-08-25",
        publish_type="rates",
        auto_published=False,
        status="completed",
        limit=15,
        skip=3,
    )

    assert result.ok is True
    assert result.data["returned_count"] == 1
    query = collection.find.call_args.args[0]
    assert query["timestamp"] == {"$gte": "2026-08-24", "$lte": "2026-08-25"}
    assert query["publish_type"] == "rates"
    assert query["auto_published"] is False
    assert query["status"] == "completed"


@pytest.mark.asyncio
async def test_maintenance_logs_build_risk_statistics():
    collection = _collection(
        documents=[{"_id": "mongo-1", "prediction_result": "high_risk"}],
        aggregate_documents=[
            {"_id": "high_risk", "count": 2, "avg_confidence": 0.87654, "tasks_created": 1}
        ],
        total=2,
    )
    service = _service(maintenance_prediction_logs=collection)

    result = await service.get_maintenance_prediction_logs(
        _ctx(),
        start_date="2026-08-24",
        end_date="2026-08-25",
        equipment_type="hvac",
        prediction_result="high_risk",
        room_number="204",
        limit=10,
        skip=1,
    )

    assert result.ok is True
    assert result.data["risk_stats"] == {
        "high_risk": {"count": 2, "avg_confidence": 0.877, "tasks_created": 1}
    }
    query = collection.find.call_args.args[0]
    assert query["timestamp"] == {"$gte": "2026-08-24", "$lte": "2026-08-25"}
    assert query["equipment_type"] == "hvac"
    assert query["prediction_result"] == "high_risk"
    assert query["room_number"] == "204"
