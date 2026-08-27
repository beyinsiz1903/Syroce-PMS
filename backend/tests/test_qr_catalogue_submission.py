import pytest
from datetime import datetime, UTC
import uuid

from domains.guest.qr_catalogue_service import validate_input_value
from domains.guest.qr_request_description import compute_payload_fingerprint
from domains.guest.qr_submission_service import _build_ledger_upsert_update, generate_deterministic_description
from models.schemas.qr_catalogue_submission import StructuredRequestSubmit, LegacyRequestSubmit
from pydantic import ValidationError

def test_fingerprint_normalization():
    payload1 = {
        "language": "EN ",
        "idempotency_key": "123",
        "items": [
            {"service_code": "b", "value": {"quantity": 2}},
            {"service_code": "a", "note": " test "}
        ]
    }
    payload2 = {
        "language": "en",
        "idempotency_key": "123",
        "items": [
            {"service_code": "a", "note": "test"},
            {"service_code": "b", "value": {"quantity": 2}}
        ]
    }
    m1 = StructuredRequestSubmit.model_validate(payload1)
    m2 = StructuredRequestSubmit.model_validate(payload2)
    f1 = compute_payload_fingerprint(m1.language, m1.items)
    f2 = compute_payload_fingerprint(m2.language, m2.items)
    assert f1 == f2

def test_fingerprint_mismatch():
    payload1 = {
        "language": "tr",
        "idempotency_key": "123",
        "items": [{"service_code": "a"}]
    }
    payload2 = {
        "language": "tr",
        "idempotency_key": "123",
        "items": [{"service_code": "a", "note": "note"}]
    }
    m1 = StructuredRequestSubmit.model_validate(payload1)
    m2 = StructuredRequestSubmit.model_validate(payload2)
    assert compute_payload_fingerprint(m1.language, m1.items) != compute_payload_fingerprint(m2.language, m2.items)


def test_ledger_upsert_update_has_no_conflicting_mongo_paths():
    created_at = datetime(2026, 8, 27, 7, 0, tzinfo=UTC)
    refreshed_at = datetime(2026, 8, 27, 7, 1, tzinfo=UTC)

    update = _build_ledger_upsert_update(
        {
            "idempotency_key": "idem-1",
            "status": "pending",
            "created_at": created_at,
            "updated_at": created_at,
        },
        refreshed_at,
    )

    insert_paths = set(update["$setOnInsert"])
    set_paths = set(update["$set"])
    assert insert_paths.isdisjoint(set_paths)
    assert "updated_at" not in update["$setOnInsert"]
    assert update["$set"]["updated_at"] == refreshed_at
    assert update["$setOnInsert"]["created_at"] == created_at

def test_value_shapes():
    val = validate_input_value("quantity", {"min": 1, "max": 5}, {"quantity": 3}, "UTC")
    assert val == {"quantity": 3}
    with pytest.raises(ValueError):
        validate_input_value("quantity", {"min": 1, "max": 5}, {"quantity": 6}, "UTC")

    val = validate_input_value("time", {"interval_minutes": 15}, {"time_value": "14:30"}, "Europe/Istanbul")
    assert val["time_value"] == "14:30"
    assert "resolved_local_datetime" in val

    with pytest.raises(ValueError):
        validate_input_value("time", {"interval_minutes": 15}, {"time_value": "14:20"}, "Europe/Istanbul")

def test_legacy_validation_tolerance():
    payload = {
        "category": "cleaning",
        "description": "Clean my room",
        "priority": "high",
        "language": "en",
        "extra_unknown_field": "should be dropped implicitly without forbid error in legacy"
    }
    LegacyRequestSubmit.model_validate(payload)

def test_structured_validation_intolerance():
    payload = {
        "idempotency_key": "123",
        "language": "en",
        "items": [{"service_code": "towel"}],
        "extra_unknown_field": "this must fail"
    }
    with pytest.raises(ValidationError):
        StructuredRequestSubmit.model_validate(payload)

class FakeAsyncCollection:
    def __init__(self):
        self.indexes = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    async def index_information(self):
        pass

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

def test_exact_index_definitions():
    import routers.room_qr_requests as router_module

    mock_db = MagicMock()
    submissions_coll = MagicMock()
    requests_coll = MagicMock()

    submissions_coll.create_index = AsyncMock()
    requests_coll.create_index = AsyncMock()

    def get_collection(name):
        if name == "guest_service_submissions":
            return submissions_coll
        elif name == "qr_requests":
            return requests_coll
        mock_coll = MagicMock()
        mock_coll.create_index = AsyncMock()
        return mock_coll

    mock_db.__getitem__.side_effect = get_collection

    async def run():
        with patch.object(router_module, 'raw_db', mock_db):
            router_module._INDEXES_READY = False
            await router_module._ensure_indexes()

    asyncio.run(run())

    calls = submissions_coll.create_index.call_args_list
    assert len(calls) == 2, f"Expected 2 index calls, got {len(calls)}"

    assert calls[0][0][0] == [("tenant_id", 1), ("property_id", 1), ("booking_id", 1), ("idempotency_key", 1)]
    assert calls[0][1] == {"unique": True, "name": "gsc_ledger_unique"}

    assert calls[1][0][0] == [("tenant_id", 1), ("submission_reference", 1)]
    assert calls[1][1] == {"unique": True, "name": "gsc_ledger_reference_unique"}

    calls = requests_coll.create_index.call_args_list
    assert len(calls) == 2, f"Expected 2 index calls, got {len(calls)}"

    assert calls[0][0][0] == [("tenant_id", 1), ("submission_group_id", 1), ("service_code", 1)]
    assert calls[0][1] == {"unique": True, "partialFilterExpression": {"submission_group_id": {"$exists": True}, "service_code": {"$exists": True}}, "name": "gsc_request_group_service_unique"}

    assert calls[1][0][0] == [("tenant_id", 1), ("request_reference", 1)]
    assert calls[1][1] == {"unique": True, "partialFilterExpression": {"request_reference": {"$exists": True}}, "name": "gsc_request_reference_unique"}


def test_structured_response_no_pydantic_exposure():
    from routers.room_qr_requests import public_submit_request
    from fastapi import HTTPException
    import asyncio

    payload = {
        "items": [
            {
                "service_code": "some-invalid",
                "value": "this is a test",
                "note": "no"
            }
        ]
    }
    mock_request = MagicMock()
    mock_request.client = MagicMock()
    mock_request.client.host = "127.0.0.1"
    mock_request.headers = {}

    with patch("routers.room_qr_requests._rl_check", return_value=True), \
         patch("routers.room_qr_requests._verify_guest_session", new_callable=AsyncMock) as mock_sess, \
         patch("routers.room_qr_requests.raw_db") as mock_db:

        mock_sess.return_value = ({"property_id": "P", "id": "B", "guest_name": "T", "guest_phone": "1"}, {"property_id": "P", "id": "S"})
        mock_coll = MagicMock()
        mock_coll.find_one = AsyncMock(return_value={"property_id": "P", "is_active": True, "room_number": "1", "name": "Hotel"})
        mock_db.__getitem__.return_value = mock_coll

        async def run():
            with pytest.raises(HTTPException) as excinfo:
                await public_submit_request("T1", "R1", payload, mock_request, "valid")

            assert excinfo.value.status_code == 422
            assert excinfo.value.detail == "Geçersiz girdi"

        asyncio.run(run())



import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from domains.guest.qr_submission_service import handle_structured_submission


class MockDuplicateKeyError(DuplicateKeyError):
    def __init__(self, keyPattern):
        super().__init__("dup")
        self._details = {"keyPattern": keyPattern}

    @property
    def details(self):
        return self._details

class MockDB:
    def __init__(self):
        self.collections = {}

    def get_collection(self, name):
        if name not in self.collections:
            coll = MagicMock()
            coll.find_one = AsyncMock(return_value=None)
            coll.find = MagicMock()
            coll.find.return_value.to_list = AsyncMock(return_value=[])
            coll.insert_one = AsyncMock()
            coll.update_one = AsyncMock()
            coll.find_one_and_update = AsyncMock()
            self.collections[name] = coll
        return self.collections[name]

    def __getitem__(self, name):
        return self.get_collection(name)

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_unknown_duplicate_key_error_sanitized(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    mock_coll.find_one = AsyncMock(return_value=None)
    mock_coll.find_one_and_update = AsyncMock(return_value={
        "_id": "test",
        "payload_fingerprint": "fprint",
        "prepared_items": [{"service_code": "a"}],
        "submission_group_id": "G1",
        "submission_reference": "R1"
    })
    mock_upd = MagicMock()
    mock_upd.matched_count = 1
    mock_coll.update_one = AsyncMock(return_value=mock_upd)

    mock_qr = db["qr_requests"]
    mock_qr.insert_one = AsyncMock(side_effect=DuplicateKeyError({"keyPattern": {"unknown": 1}}))
    mock_qr.find = MagicMock()
    mock_qr.find.return_value.to_list = AsyncMock(return_value=[{"service_code": "a"}])

    payload = MagicMock()
    payload.idempotency_key = "idem"
    payload.items = []
    payload.language = "en"

    async def run():
        try:
            await handle_structured_submission(
                tenant_id="T", property_id="P", room_id="R", booking_id="B",
                session_id="S", room_number="1", payload=payload,
                guest_name="Test", guest_phone="123"
            )
        except Exception as e:
            assert e.status_code == 503
            assert e.detail == "Sistem hatası"

    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_completion_matched_count_0(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    mock_coll.find_one = AsyncMock(return_value=None)
    mock_coll.find_one_and_update = AsyncMock(return_value={
        "_id": "test",
        "payload_fingerprint": "fprint",
        "prepared_items": [],
        "submission_group_id": "G1",
        "submission_reference": "R1"
    })

    # matched_count = 0 for completion
    mock_upd = MagicMock()
    mock_upd.matched_count = 0
    # For attempt_count increment, we need matched_count=1
    mock_inc = MagicMock()
    mock_inc.matched_count = 1
    mock_coll.update_one = AsyncMock(side_effect=[mock_inc, mock_upd])

    mock_qr = db["qr_requests"]
    mock_qr.insert_one = AsyncMock()
    mock_qr.find = MagicMock()
    mock_qr.find.return_value.to_list = AsyncMock(return_value=[])

    payload = MagicMock()
    payload.idempotency_key = "idem"
    payload.items = []
    payload.language = "en"

    async def run():
        try:
            await handle_structured_submission(
                tenant_id="T", property_id="P", room_id="R", booking_id="B",
                session_id="S", room_number="1", payload=payload,
                guest_name="Test", guest_phone="123"
            )
        except Exception as e:
            assert e.status_code == 503
            assert "Talep işleme alınamadı" in e.detail

    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_existing_ledger_partial_retry(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    # Initial lookup returns pending ledger with a and b
    mock_coll.find_one = AsyncMock(side_effect=[
        {
            "_id": "test",
            "payload_fingerprint": "fprint",
            "prepared_items": [{"service_code": "a"}, {"service_code": "b"}],
            "submission_group_id": "G1",
            "submission_reference": "R1",
            "status": "pending"
        },
        # second find_one is for completion check
        {
            "_id": "test",
            "status": "completed",
            "completed_at": "now",
            "prepared_items": [{"service_code": "a", "request_reference": "RR1"}, {"service_code": "b", "request_reference": "RR2"}]
        }
    ])

    # Update mock returns matched_count=1
    mock_upd = MagicMock()
    mock_upd.matched_count = 1
    mock_coll.update_one = AsyncMock(return_value=mock_upd)

    mock_qr = db["qr_requests"]
    # We simulate 'a' already exists -> DuplicateKeyError
    async def mock_insert(doc):
        if doc["service_code"] == "a":
            raise MockDuplicateKeyError({"submission_group_id": 1, "service_code": 1})
        return True
    mock_qr.insert_one = AsyncMock(side_effect=mock_insert)

    mock_qr.find = MagicMock()
    mock_qr.find.return_value.to_list = AsyncMock(return_value=[{"service_code": "a"}, {"service_code": "b"}])

    with patch("domains.guest.qr_submission_service.fetch_catalogue_data", side_effect=Exception("Should not resolve catalogue!")):
        payload = MagicMock()
        payload.idempotency_key = "idem"
        payload.items = []
        payload.language = "en"

        async def run():
            res = await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
            assert res["success"] is True
            assert res["stats"]["created"] == 1
            assert res["stats"]["replayed"] == 1
            # docs_to_emit (notifications) should only contain 'b'
            assert len(res["docs_to_emit"]) == 1
            assert res["docs_to_emit"][0]["service_code"] == "b"

            # verify attempt count was incremented
            calls = mock_coll.update_one.call_args_list
            assert any("$inc" in call[0][1] and call[0][1]["$inc"].get("attempt_count") == 1 for call in calls)

        asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_full_replay(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    # Initial lookup returns completed ledger with a and b
    mock_coll.find_one = AsyncMock(side_effect=[
        {
            "_id": "test",
            "payload_fingerprint": "fprint",
            "prepared_items": [{"service_code": "a"}, {"service_code": "b"}],
            "submission_group_id": "G1",
            "submission_reference": "R1",
            "status": "completed"
        },
        # second find_one is for completion check
        {
            "_id": "test",
            "status": "completed",
            "completed_at": "now",
            "prepared_items": [{"service_code": "a", "request_reference": "RR1"}, {"service_code": "b", "request_reference": "RR2"}]
        }
    ])

    mock_upd = MagicMock()
    mock_upd.matched_count = 1
    mock_coll.update_one = AsyncMock(return_value=mock_upd)

    mock_qr = db["qr_requests"]
    # Both a and b already exist
    async def mock_insert(doc):
        raise MockDuplicateKeyError({"submission_group_id": 1, "service_code": 1})
    mock_qr.insert_one = AsyncMock(side_effect=mock_insert)

    mock_qr.find = MagicMock()
    mock_qr.find.return_value.to_list = AsyncMock(return_value=[{"service_code": "a"}, {"service_code": "b"}])

    with patch("domains.guest.qr_submission_service.fetch_catalogue_data", side_effect=Exception("Should not resolve catalogue!")):
        payload = MagicMock()
        payload.idempotency_key = "idem"
        payload.items = []
        payload.language = "en"

        async def run():
            res = await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
            assert res["success"] is True
            assert res["stats"]["created"] == 0
            assert res["stats"]["replayed"] == 2
            assert len(res["docs_to_emit"]) == 0

            # verify attempt count was incremented
            calls = mock_coll.update_one.call_args_list
            assert any("$inc" in call[0][1] and call[0][1]["$inc"].get("attempt_count") == 1 for call in calls)

        asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_duplicate_key_error_winner_reread(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    # first find_one (lookup) -> None
    # find_one_and_update -> DupKeyError
    # second find_one (reread) -> Returns winner
    mock_coll.find_one = AsyncMock(side_effect=[
        None,
        {
            "_id": "test",
            "payload_fingerprint": "fprint",
            "prepared_items": [{"service_code": "a"}],
            "submission_group_id": "G1",
            "submission_reference": "R1"
        },
        # Reread for completion
        {
            "_id": "test",
            "status": "completed",
            "completed_at": "now",
            "prepared_items": [{"service_code": "a", "request_reference": "RR"}]
        }
    ])
    mock_coll.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError({"keyPattern": {"submission_group_id": 1, "service_code": 1}}))

    mock_upd = MagicMock()
    mock_upd.matched_count = 1
    mock_coll.update_one = AsyncMock(return_value=mock_upd)

    mock_qr = db["qr_requests"]
    mock_qr.insert_one = AsyncMock()
    mock_qr.find = MagicMock()
    mock_qr.find.return_value.to_list = AsyncMock(return_value=[{"service_code": "a"}])

    payload = MagicMock()
    payload.idempotency_key = "idem"
    payload.items = []
    payload.language = "en"

    async def run():
        res = await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
        assert res["success"] is True

    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_duplicate_key_error_winner_reread_unavailable(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    # lookup -> None, find_one_and_update -> DupKeyError, reread -> None (5 times)
    mock_coll.find_one = AsyncMock(return_value=None)
    mock_coll.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError({"keyPattern": {"submission_group_id": 1, "service_code": 1}}))

    payload = MagicMock()
    payload.idempotency_key = "idem"

    async def run():
        try:
            await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
            assert False
        except HTTPException as e:
            assert e.status_code == 503

    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_conflicting_fingerprint_race(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    mock_coll.find_one = AsyncMock(side_effect=[
        None,
        {
            "_id": "test",
            "payload_fingerprint": "DIFFERENT",
            "prepared_items": [{"service_code": "a"}],
            "submission_group_id": "G1",
            "submission_reference": "R1"
        }
    ])
    mock_coll.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError({"keyPattern": {"submission_group_id": 1, "service_code": 1}}))

    payload = MagicMock()
    payload.idempotency_key = "idem"

    async def run():
        try:
            await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
            assert False
        except HTTPException as e:
            assert e.status_code == 409

    asyncio.run(run())


def test_duplicate_service_error():
    payload = StructuredRequestSubmit.model_validate({
        "idempotency_key": "test",
        "language": "en",
        "items": [
            {"service_code": "TOWEL", "value": None, "note": None},
            {"service_code": "TOWEL", "value": None, "note": None}
        ]
    })

    async def run():
        try:
            await handle_structured_submission(
                tenant_id="T", property_id="P", room_id="R", booking_id="B",
                session_id="S", room_number="1", payload=payload,
                guest_name="Test", guest_phone="123"
            )
            assert False, "Should have raised exception"
        except HTTPException as e:
            assert e.status_code == 422
            assert e.detail == "Geçersiz girdi"

    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_missing_submission_reference_503(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    mock_coll.find_one = AsyncMock(return_value={
        "_id": "test",
        "payload_fingerprint": "fprint",
        "prepared_items": [{"service_code": "a"}],
        "submission_group_id": "G1"
    })

    payload = MagicMock()
    payload.idempotency_key = "idem"
    payload.items = []
    payload.language = "en"

    async def run():
        try:
            await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
            assert False, "Should have raised exception"
        except HTTPException as e:
            assert e.status_code == 503
            assert e.detail == "Sistem hatası"

    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_convergence_actual_contains_duplicates(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    mock_coll.find_one = AsyncMock(side_effect=[
        {
            "_id": "test",
            "payload_fingerprint": "fprint",
            "prepared_items": [{"service_code": "a"}, {"service_code": "b"}],
            "submission_group_id": "G1",
            "submission_reference": "R1",
            "status": "pending"
        },
        None
    ])

    mock_upd = MagicMock()
    mock_upd.matched_count = 1
    mock_coll.update_one = AsyncMock(return_value=mock_upd)

    mock_qr = db["qr_requests"]
    mock_qr.insert_one = AsyncMock()
    mock_qr.find = MagicMock()
    mock_qr.find.return_value.to_list = AsyncMock(return_value=[
        {"service_code": "a"}, {"service_code": "a"}, {"service_code": "b"}
    ])

    with patch("domains.guest.qr_submission_service.fetch_catalogue_data", side_effect=Exception("Should not resolve catalogue!")):
        payload = MagicMock()
        payload.idempotency_key = "idem"
        payload.items = []
        payload.language = "en"

        async def run():
            try:
                await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
                assert False, "Should raise 503 due to convergence failure"
            except HTTPException as e:
                assert e.status_code == 503
                calls = mock_coll.update_one.call_args_list
                assert any("$set" in call[0][1] and call[0][1]["$set"].get("last_error_code") == "CONVERGENCE_MISS" for call in calls)

        asyncio.run(run())


@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_convergence_actual_contains_different(mock_raw_db, mock_fingerprint):
    db = MockDB()
    mock_raw_db.__getitem__.side_effect = db.__getitem__

    mock_coll = db["guest_service_submissions"]
    mock_coll.find_one = AsyncMock(side_effect=[
        {
            "_id": "test",
            "payload_fingerprint": "fprint",
            "prepared_items": [{"service_code": "a"}, {"service_code": "b"}],
            "submission_group_id": "G1",
            "submission_reference": "R1",
            "status": "pending"
        },
        None
    ])

    mock_upd = MagicMock()
    mock_upd.matched_count = 1
    mock_coll.update_one = AsyncMock(return_value=mock_upd)

    mock_qr = db["qr_requests"]
    mock_qr.insert_one = AsyncMock()
    mock_qr.find = MagicMock()
    mock_qr.find.return_value.to_list = AsyncMock(return_value=[
        {"service_code": "a"}, {"service_code": "c"}
    ])

    with patch("domains.guest.qr_submission_service.fetch_catalogue_data", side_effect=Exception("Should not resolve catalogue!")):
        payload = MagicMock()
        payload.idempotency_key = "idem"
        payload.items = []
        payload.language = "en"

        async def run():
            try:
                await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
                assert False, "Should raise 503 due to convergence failure"
            except HTTPException as e:
                assert e.status_code == 503
                calls = mock_coll.update_one.call_args_list
                assert any("$set" in call[0][1] and call[0][1]["$set"].get("last_error_code") == "CONVERGENCE_MISS" for call in calls)

        asyncio.run(run())
