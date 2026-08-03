import pytest
from datetime import datetime, UTC
import uuid

from domains.guest.qr_catalogue_service import validate_input_value
from domains.guest.qr_request_description import compute_payload_fingerprint
from domains.guest.qr_submission_service import generate_deterministic_description
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

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fingerprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_unknown_duplicate_key_error_sanitized(mock_raw_db, mock_fingerprint):
    from domains.guest.qr_submission_service import handle_structured_submission
    from pymongo.errors import DuplicateKeyError
    import asyncio

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=None)
    mock_coll.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("E11000 duplicate key error"))
    mock_coll.update_one = AsyncMock()
    mock_coll.insert_one = AsyncMock()
    mock_raw_db.__getitem__.return_value = mock_coll

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

            assert e.status_code == 503
            assert e.detail == "Sistem hatası"


    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fingerprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_completion_matched_count_0(mock_raw_db, mock_fingerprint):
    from domains.guest.qr_submission_service import handle_structured_submission
    import asyncio

    mock_upd = MagicMock()
    mock_upd.matched_count = 0

    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value=None)
    mock_coll.find_one_and_update = AsyncMock(return_value={
        "_id": "test",
        "payload_fingerprint": "fingerprint",
        "prepared_items": [],
        "submission_group_id": "G1",
        "submission_reference": "R1"
    })
    mock_coll.update_one = AsyncMock(return_value=mock_upd)
    mock_coll.insert_one = AsyncMock()
    mock_coll.count_documents = AsyncMock(return_value=1)
    mock_raw_db.__getitem__.return_value = mock_coll

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
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from domains.guest.qr_submission_service import handle_structured_submission

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_existing_matching_ledger_skips_catalogue(mock_raw_db, mock_fingerprint):
    # existing matching ledger skips catalogue resolution
    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value={
        "_id": "test",
        "payload_fingerprint": "fprint",
        "prepared_items": [{"service_code": "a"}],
        "submission_group_id": "G1",
        "submission_reference": "R1"
    })
    mock_coll.update_one = AsyncMock()
    mock_coll.insert_one = AsyncMock()
    mock_coll.count_documents = AsyncMock(return_value=1)

    # We mock fetch_catalogue_data to raise exception if called, to prove it's skipped
    with patch("domains.guest.qr_submission_service.fetch_catalogue_data", side_effect=Exception("Should not resolve catalogue!")):
        mock_raw_db.__getitem__.return_value = mock_coll
        payload = MagicMock()
        payload.idempotency_key = "idem"
        payload.items = []
        payload.language = "en"

        async def run():
            res = await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
            assert res["success"] is True
            assert res["stats"]["created"] == 1

        asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_partial_replay_counts(mock_raw_db, mock_fingerprint):
    # existing pending ledger completes missing items
    # Ledger has 2 items. DB has 1.
    mock_coll = MagicMock()
    mock_coll.find_one = AsyncMock(return_value={
        "_id": "test",
        "payload_fingerprint": "fprint",
        "prepared_items": [{"service_code": "a"}, {"service_code": "b"}],
        "submission_group_id": "G1",
        "submission_reference": "R1"
    })

    mock_coll.update_one = AsyncMock()

    async def mock_insert_one(doc):
        if doc["service_code"] == "a":
            e = DuplicateKeyError("dup")
            e.details = {"keyPattern": {"submission_group_id": 1, "service_code": 1}}
            raise e
        return True

    mock_coll.insert_one = AsyncMock(side_effect=mock_insert_one)
    mock_coll.count_documents = AsyncMock(return_value=2)
    mock_raw_db.__getitem__.return_value = mock_coll

    payload = MagicMock()
    payload.idempotency_key = "idem"
    payload.items = []
    payload.language = "en"

    async def run():
        res = await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
        assert res["stats"]["created"] == 1
        assert res["stats"]["replayed"] == 1

    asyncio.run(run())

@patch("domains.guest.qr_submission_service.compute_payload_fingerprint", return_value="fprint")
@patch("domains.guest.qr_submission_service.raw_db")
def test_duplicate_key_error_winner_reread(mock_raw_db, mock_fingerprint):
    mock_coll = MagicMock()
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
    mock_coll.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("dup"))

    mock_coll.update_one = AsyncMock()
    mock_coll.insert_one = AsyncMock()
    mock_coll.count_documents = AsyncMock(return_value=1)
    mock_raw_db.__getitem__.return_value = mock_coll

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
    mock_coll = MagicMock()
    # lookup -> None, find_one_and_update -> DupKeyError, reread -> None (5 times)
    mock_coll.find_one = AsyncMock(return_value=None)
    mock_coll.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("dup"))

    mock_raw_db.__getitem__.return_value = mock_coll

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
    mock_coll = MagicMock()
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
    mock_coll.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("dup"))

    mock_raw_db.__getitem__.return_value = mock_coll
    payload = MagicMock()
    payload.idempotency_key = "idem"

    async def run():
        try:
            await handle_structured_submission("T", "P", "R", "B", "S", "1", payload, "Test", "123")
            assert False
        except HTTPException as e:
            assert e.status_code == 409

    asyncio.run(run())
