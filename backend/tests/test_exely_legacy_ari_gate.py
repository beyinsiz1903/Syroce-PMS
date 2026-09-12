from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domains.channel_manager.ari.hard_fail_gate import check_mapping_gate


@pytest.mark.asyncio
async def test_legacy_exely_pair_satisfies_canonical_ari_mapping_gate():
    generic_room = MagicMock()
    generic_room.find_one = AsyncMock(return_value=None)
    generic_rate = MagicMock()
    generic_rate.find_one = AsyncMock(return_value=None)
    legacy = MagicMock()
    legacy.find_one = AsyncMock(
        return_value={
            "pms_room_type": "standard",
            "exely_room_code": "5003299",
            "exely_rate_plan_code": "10009740",
            "is_active": True,
        }
    )

    def collection(name):
        return {
            "room_mappings": generic_room,
            "rate_plan_mappings": generic_rate,
            "exely_room_mappings": legacy,
        }[name]

    with patch("domains.channel_manager.ari.hard_fail_gate.db") as database:
        database.__getitem__ = MagicMock(side_effect=collection)
        verdict = await check_mapping_gate(
            "tenant-1",
            "501694",
            "exely",
            "5003299",
            "10009740",
        )

    assert verdict.passed is True
    legacy.find_one.assert_awaited_once_with(
        {
            "tenant_id": "tenant-1",
            "$or": [
                {"exely_room_code": "5003299", "exely_rate_plan_code": "10009740"},
                {"pms_api_room_code": "5003299", "pms_api_rate_plan_code": "10009740"},
            ],
        },
        {"_id": 0},
    )


@pytest.mark.asyncio
async def test_pms_api_pair_satisfies_exely_mapping_gate():
    generic_room = MagicMock()
    generic_room.find_one = AsyncMock(return_value=None)
    generic_rate = MagicMock()
    generic_rate.find_one = AsyncMock(return_value=None)
    legacy = MagicMock()
    legacy.find_one = AsyncMock(return_value={
        "pms_room_type": "standard",
        "exely_room_code": "5003299",
        "exely_rate_plan_code": "10009740",
        "pms_api_room_code": "5001574",
        "pms_api_rate_plan_code": "10003870",
        "is_active": True,
    })

    with patch("domains.channel_manager.ari.hard_fail_gate.db") as database:
        database.__getitem__ = MagicMock(side_effect=lambda name: {
            "room_mappings": generic_room,
            "rate_plan_mappings": generic_rate,
            "exely_room_mappings": legacy,
        }[name])
        verdict = await check_mapping_gate(
            "tenant-1", "501694", "exely", "5001574", "10003870",
        )

    assert verdict.passed is True
    legacy.find_one.assert_awaited_once_with({
        "tenant_id": "tenant-1",
        "$or": [
            {"exely_room_code": "5001574", "exely_rate_plan_code": "10003870"},
            {"pms_api_room_code": "5001574", "pms_api_rate_plan_code": "10003870"},
        ],
    }, {"_id": 0})


@pytest.mark.asyncio
async def test_legacy_exely_mapping_does_not_accept_a_different_rate_plan():
    empty = MagicMock()
    empty.find_one = AsyncMock(return_value=None)

    with patch("domains.channel_manager.ari.hard_fail_gate.db") as database:
        database.__getitem__ = MagicMock(return_value=empty)
        verdict = await check_mapping_gate(
            "tenant-1",
            "501694",
            "exely",
            "5003299",
            "wrong-rate",
        )

    assert verdict.passed is False
    assert {failure["entity_type"] for failure in verdict.failures} == {"room", "rate_plan"}
