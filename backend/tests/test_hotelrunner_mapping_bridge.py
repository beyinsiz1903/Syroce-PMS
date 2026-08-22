from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager.providers.hotelrunner import mapping_bridge


@pytest.mark.asyncio
async def test_legacy_mapping_is_mirrored_with_canonical_room_and_rate_identity(monkeypatch):
    room_mappings = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        update_one=AsyncMock(),
    )
    rate_mappings = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        update_one=AsyncMock(),
    )
    fake_db = SimpleNamespace(
        rooms=SimpleNamespace(distinct=AsyncMock(return_value=["Jakuzisiz Ağaç Ev"])),
        room_mappings=room_mappings,
        rate_plan_mappings=rate_mappings,
    )
    monkeypatch.setattr(mapping_bridge, "db", fake_db)

    await mapping_bridge.mirror_hotelrunner_mapping(
        "tenant-1",
        {
            "pms_room_type": "jakuzisiz ağaç ev",
            "hr_inv_code": "HR:704308",
            "hr_rate_code": "704320:HR:704308",
            "hr_room_name": "Standard Bungalow - Oda ve Kahvaltı",
        },
    )

    room_set = room_mappings.update_one.await_args.args[1]["$set"]
    assert room_set["property_id"] == "prop-001"
    assert room_set["pms_room_type_id"] == "Jakuzisiz Ağaç Ev"
    assert room_set["pms_room_type_name"] == "Jakuzisiz Ağaç Ev"
    assert room_set["provider_room_code"] == "HR:704308"
    assert room_set["validation_status"] == "valid"

    rate_set = rate_mappings.update_one.await_args.args[1]["$set"]
    assert rate_set["provider_rate_code"] == "704320:HR:704308"
    assert rate_set["pms_rate_plan_id"] == "704320:HR:704308"
    assert rate_set["validation_status"] == "valid"
