"""Previously uncovered room-feature and profile-UDF write boundaries."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.guest import profile_udf_router as udf
from domains.pms import operations_router as ops

USER = SimpleNamespace(id="operator", tenant_id="demo-local", email="qa@example.invalid")


def room_store(monkeypatch, *, row=None, matched=1):
    row = row or {"_id": "storage-room", "id": "public-room", "tenant_id": USER.tenant_id, "dnd": False}
    rooms = SimpleNamespace(find_one=AsyncMock(return_value=row), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=matched)))
    monkeypatch.setattr(ops, "db", SimpleNamespace(rooms=rooms))
    return rooms


@pytest.mark.asyncio
async def test_room_dnd_resolves_public_id_and_atomically_retains_actor(monkeypatch):
    rooms = room_store(monkeypatch)
    result = await ops.update_room_features("public-room", {"dnd": True, "expected_dnd": False}, current_user=USER)
    assert rooms.find_one.await_args_list[0].args[0] == {"tenant_id": USER.tenant_id, "id": "public-room"}
    query, update = rooms.update_one.await_args.args
    assert query["_id"] == "storage-room" and query["tenant_id"] == USER.tenant_id and query["dnd"] is False
    assert update["$set"]["dnd"] is True
    assert set(update["$set"]) == {"dnd", "features_updated_at", "features_updated_by_id"}
    event = update["$push"]["features_audit"]
    assert (event["actor_id"], event["before"], event["after"]) == (USER.id, {"dnd": False}, {"dnd": True})
    assert result["dnd"] is True and result["id"] == "public-room"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"dnd": "false"}, {"dnd": 1}, {"dnd": None}, {"dnd": True, "status": "available"}, {"dnd": True, "room_number": "other"}, {"dnd": True, "tenant_id": "other"}, {"dnd": True, "features_audit": []}, {"dnd": True, "expected_dnd": "false"}])
async def test_room_features_rejects_non_boolean_or_unrelated_fields(monkeypatch, body):
    rooms = room_store(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await ops.update_room_features("public-room", body, current_user=USER)
    assert exc.value.status_code == 400
    rooms.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_room_dnd_stale_request_cannot_overwrite_or_duplicate_audit(monkeypatch):
    rooms = room_store(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await ops.update_room_features("public-room", {"dnd": True, "expected_dnd": True}, current_user=USER)
    assert exc.value.status_code == 409
    rooms.update_one.assert_not_awaited()
    result = await ops.update_room_features("public-room", {"dnd": False}, current_user=USER)
    assert result["already_applied"] is True
    rooms.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_room_dnd_compare_and_set_failure_is_conflict(monkeypatch):
    room_store(monkeypatch, matched=0)
    with pytest.raises(HTTPException) as exc:
        await ops.update_room_features("public-room", {"dnd": True}, current_user=USER)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("value", ["NaN", "nan", "Infinity", "-Infinity", "1e999", float("nan"), float("inf"), True, False, 10**500, [], {}])
def test_udf_number_rejects_nonfinite_bool_and_unrepresentable_values(value):
    with pytest.raises(HTTPException) as exc:
        udf._coerce_value(value, {"key": "score", "type": "number"})
    assert exc.value.status_code == 400


@pytest.mark.parametrize("value,expected", [("0", 0.0), (0, 0.0), ("12.75", 12.75), (-2, -2.0)])
def test_udf_number_keeps_valid_zero_decimal_and_negative_business_values(value, expected):
    assert udf._coerce_value(value, {"key": "score", "type": "number"}) == expected


@pytest.mark.parametrize("value", ["maybe", "tru", {}, [], 2, 0.5])
def test_udf_boolean_does_not_silently_turn_typo_into_false(value):
    with pytest.raises(HTTPException) as exc:
        udf._coerce_value(value, {"key": "opt_in", "type": "boolean"})
    assert exc.value.status_code == 400


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), ("evet", True), ("hayır", False), ("false", False), ("0", False), (1, True), (0, False)])
def test_udf_boolean_accepts_only_explicit_known_values(value, expected):
    assert udf._coerce_value(value, {"key": "opt_in", "type": "boolean"}) is expected


class Rows:
    def __init__(self, rows): self.rows = rows
    def __aiter__(self):
        async def iterator():
            for row in self.rows: yield dict(row)
        return iterator()


def udf_store(monkeypatch, *, matched=1):
    guest = {"_id": "storage-guest", "id": "public-guest", "tenant_id": USER.tenant_id, "custom_fields": {"score": 0, "legacy": "preserve"}}
    guests = SimpleNamespace(find_one=AsyncMock(return_value=guest), update_one=AsyncMock(return_value=SimpleNamespace(matched_count=matched)))
    definitions = SimpleNamespace(find=lambda query: Rows([{"key": "score", "type": "number", "required": True}]))
    monkeypatch.setattr(udf, "get_system_db", lambda: SimpleNamespace(guests=guests, profile_udf_defs=definitions))
    return guests


@pytest.mark.asyncio
async def test_udf_partial_merge_has_tenant_cas_actor_and_preserves_other_fields(monkeypatch):
    guests = udf_store(monkeypatch)
    result = await udf.set_guest_udf_values("public-guest", udf.UdfValuesPayload(values={"score": "12.5"}), user=USER)
    query, update = guests.update_one.await_args.args
    assert query == {"_id": "storage-guest", "tenant_id": USER.tenant_id, "custom_fields": {"score": 0, "legacy": "preserve"}}
    assert update["$set"]["custom_fields"] == result["values"] == {"score": 12.5, "legacy": "preserve"}
    assert update["$set"]["custom_fields_updated_by_id"] == USER.id


@pytest.mark.asyncio
async def test_udf_unknown_key_is_explicit_error_not_false_success(monkeypatch):
    guests = udf_store(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await udf.set_guest_udf_values("public-guest", udf.UdfValuesPayload(values={"scroe": 12}), user=USER)
    assert exc.value.status_code == 400
    guests.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_udf_concurrent_write_cannot_silently_drop_another_update(monkeypatch):
    udf_store(monkeypatch, matched=0)
    with pytest.raises(HTTPException) as exc:
        await udf.set_guest_udf_values("public-guest", udf.UdfValuesPayload(values={"score": 1}), user=USER)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_udf_old_browser_revision_cannot_overwrite_a_later_saved_map(monkeypatch):
    guests = udf_store(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await udf.set_guest_udf_values("public-guest", udf.UdfValuesPayload(values={"score": 10}, expected_revision=udf.values_revision({"score": 0})), user=USER)
    assert exc.value.status_code == 409
    guests.update_one.assert_not_awaited()


@pytest.mark.parametrize("value", [{"score": float("nan")}, {"score": float("inf")}, [1, 2]])
def test_udf_legacy_invalid_map_cannot_break_json_or_be_silently_rewritten(value):
    with pytest.raises(HTTPException) as exc:
        udf.values_revision(value)
    assert exc.value.status_code == 409
