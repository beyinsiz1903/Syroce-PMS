from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.guest_property import guest_property_context, room_property_id


@pytest.mark.parametrize("room,booking,expected", [
    ({"id": "r", "tenant_id": "t"}, {"room_id": "r", "tenant_id": "t"}, "t"),
    ({"id": "r", "property_id": "p"}, {"room_id": "r"}, "p"),
    ({"id": "r"}, {"room_id": "r", "property_id": "p"}, "p"),
    ({"id": "r", "property_id": "p"}, {"room_id": "r", "property_id": "other"}, None),
    ({"id": "r", "tenant_id": "other"}, {}, None),
    ({"id": "r"}, {"tenant_id": "other"}, None),
    ({"id": "r"}, {"room_id": "other"}, None),
])
def test_exact_room_property_boundary(room, booking, expected):
    assert room_property_id("t", room, booking) == expected


def database(prop=None, tenant=None, settings=None):
    return {name: SimpleNamespace(find_one=AsyncMock(return_value=value)) for name, value in (("properties", prop), ("tenants", tenant), ("hotel_settings", settings))}


async def test_legacy_context_reads_exact_existing_tenant_and_local_settings_without_write():
    db = database(tenant={"id": "t", "property_name": "QA hotel", "secret": "not surfaced"}, settings={"timezone": "Europe/Istanbul", "currency": "TRY", "checkout_time": "12:00"})
    result = await guest_property_context(db, "t", "t")
    assert result == {"id": "t", "tenant_id": "t", "scope": "legacy_single_property", "property_name": "QA hotel", "timezone": "Europe/Istanbul", "currency": "TRY", "checkout_time": "12:00"}
    db["tenants"].find_one.assert_awaited_once_with({"id": "t"})


@pytest.mark.parametrize("tenant,pid", [(None, "t"), ({"id": "t", "tenant_id": "other"}, "t"), ({"id": "t", "property_id": "configured"}, "t"), ({"id": "t"}, "other")])
async def test_no_missing_foreign_or_configured_property_fallback(tenant, pid):
    db = database(tenant=tenant)
    assert await guest_property_context(db, "t", pid) is None
    db["properties"].find_one.assert_awaited_once_with({"id": pid, "tenant_id": "t"})
    if pid != "t":
        db["tenants"].find_one.assert_not_awaited()


async def test_explicit_property_is_not_relabelled_as_tenant():
    prop = {"id": "p", "tenant_id": "t", "timezone": "Europe/Paris"}
    db = database(prop=prop)
    assert await guest_property_context(db, "t", "p") == prop
    db["tenants"].find_one.assert_not_awaited()
