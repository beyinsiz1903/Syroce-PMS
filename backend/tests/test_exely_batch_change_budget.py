"""PMSConnect pp.9-10: category change limits are not envelope size limits."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from lxml import etree

from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.provider_quota import ExelyProviderQuota

pytestmark = pytest.mark.exely_failure_stress

SUCCESS = b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05"><Success/></OTA_HotelAvailNotifRS></s:Body></s:Envelope>'
NS = {"ota": "http://www.opentravel.org/OTA/2003/05"}


class BudgetRedis:
    """Stateful model of the unchanged atomic Lua reservation contract."""

    def __init__(self):
        self.values = {}
        self.calls = []

    async def eval(self, script, count, *parts):
        keys, args = parts[:count], parts[count:]
        self.calls.append((keys, args))
        if self.values.get(keys[0]):
            return [0, 1, 60]
        for index, key in enumerate(keys[1:], 2):
            cost, limit, ttl = args[(index - 2) * 3:(index - 1) * 3]
            if self.values.get(key, 0) + cost > limit:
                return [0, index, ttl]
        for index, key in enumerate(keys[1:]):
            self.values[key] = self.values.get(key, 0) + args[index * 3]
        return [1, 0, 0]


@pytest.fixture
def budget(monkeypatch):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 2, 9, 0, 0, tzinfo=UTC)

    monkeypatch.setattr("domains.channel_manager.providers.exely.provider_quota.datetime", FixedClock)
    monkeypatch.setattr("domains.channel_manager.providers.exely.provider.ari_write_block_reason", lambda: "")
    return BudgetRedis()


def provider(redis, connection="budget-test"):
    instance = ExelyProvider(
        username="synthetic", password="synthetic", hotel_code="synthetic-property",
        connection_id=connection,
        quota_guard=ExelyProviderQuota("synthetic-tenant", "synthetic-property", redis_client=redis),
    )
    instance._transport.send_soap = AsyncMock(return_value=SUCCESS)
    return instance


def message(room, start="2026-11-02", end="2028-11-01", availability=8, plan="BASE"):
    return {"room_type_code": room, "rate_plan_code": plan, "start_date": start, "end_date": end, "availability": availability}


async def push(instance, rows, operation="availability_batch"):
    return await instance.push_ari_operation(
        operation=operation, room_type_code="", rate_plan_code="", start_date="", end_date="", value=rows,
    )


async def test_731_days_for_two_rooms_and_changed_stock_periods_use_one_complete_xml(budget):
    instance = provider(budget)
    rows = [
        message("STD", end="2026-11-09"),
        message("STD", start="2026-11-10", end="2026-11-10", availability=0),
        message("STD", start="2026-11-11", end="2026-12-19"),
        message("STD", start="2026-12-20", end="2026-12-21", availability=7),
        message("STD", start="2026-12-22"),
        message("DLX"),
    ]
    result = await push(instance, rows)
    assert result.success and result.metadata["provider_write_count"] == 1
    instance._transport.send_soap.assert_awaited_once()
    xml = etree.fromstring(instance._transport.send_soap.await_args.args[0].encode())
    assert len(xml.findall(".//ota:AvailStatusMessages", NS)) == 1
    elements = xml.findall(".//ota:AvailStatusMessage", NS)
    assert len(elements) == 6
    coverage = {"STD": {}, "DLX": {}}
    for element in elements:
        control = element.find("ota:StatusApplicationControl", NS)
        assert control.get("RatePlanCode") == "BASE"
        room = coverage[control.get("InvTypeCode")]
        current, end = date.fromisoformat(control.get("Start")), date.fromisoformat(control.get("End"))
        while current <= end:
            assert current not in room
            room[current] = int(element.get("BookingLimit"))
            current += timedelta(days=1)
    expected_days = {date(2026, 11, 2) + timedelta(days=i) for i in range(731)}
    assert set(coverage["STD"]) == set(coverage["DLX"]) == expected_days
    assert len(coverage["STD"]) + len(coverage["DLX"]) == 1462
    assert coverage["STD"][date(2026, 11, 10)] == 0
    assert coverage["STD"][date(2026, 12, 20)] == coverage["STD"][date(2026, 12, 21)] == 7
    assert set(coverage["DLX"].values()) == {8}
    keys, args = budget.calls[0]
    assert len(keys) == 6  # shared cooldown plus all five original windows
    assert args[0:3] == (731, 1460, 2)
    assert args[3:6] == (1, 650, 3700)


async def test_parallel_workers_cannot_each_spend_731_in_the_same_second(budget):
    first, second = provider(budget, "worker-one"), provider(budget, "worker-two")
    rows = [message("STD"), message("DLX")]
    results = await asyncio.gather(push(first, rows), push(second, rows))
    assert sorted(result.success for result in results) == [False, True]
    assert sum(result.metadata["provider_write_count"] for result in results) == 1
    assert first._transport.send_soap.await_count + second._transport.send_soap.await_count == 1
    assert len(budget.calls) == 2
    assert budget.calls[0][0] == budget.calls[1][0]
    rejected = next(result for result in results if not result.success)
    assert rejected.error_type == "RATE_LIMITED"


@pytest.mark.parametrize("operation", ["availability_batch", "rate_batch", "restriction_batch"])
async def test_same_category_periods_and_plans_are_summed_not_discounted(budget, operation):
    rows = [message("STD", plan=plan) for plan in ("BASE", "OTHER")]
    if operation == "rate_batch":
        rows = [{**row, "rate_amount": 100, "currency": "USD"} for row in rows]
    elif operation == "restriction_batch":
        rows = [{**row, "operation": "min_los", "value": 2} for row in rows]
    instance = provider(budget)
    result = await push(instance, rows, operation)
    assert not result.success and result.error_type == "RATE_LIMITED"
    assert result.metadata["provider_write_count"] == 0
    instance._transport.send_soap.assert_not_awaited()
    assert budget.calls[0][1][0] == 1462
    assert budget.values == {}  # no partial reservation of the other windows


@pytest.mark.parametrize("window", ["second", "3m", "hour", "day"])
async def test_old_worker_usage_and_every_change_window_still_block_atomically(budget, window):
    quota = ExelyProviderQuota("synthetic-tenant", "synthetic-property", redis_client=budget)
    assert (await quota.reserve(operation="ari_mutation", change_count=1)).allowed
    keys, args = budget.calls[0]
    for index, key in enumerate(keys[1:]):
        if f":changes:{window}:" in key:
            budget.values[key] = args[index * 3 + 1] - 730
    before = dict(budget.values)
    instance = provider(budget)
    result = await push(instance, [message("STD"), message("DLX")])
    assert not result.success and result.metadata["provider_write_count"] == 0
    instance._transport.send_soap.assert_not_awaited()
    assert budget.values == before


async def test_original_property_request_limit_still_blocks_multiroom_batch(budget):
    quota = ExelyProviderQuota("synthetic-tenant", "synthetic-property", redis_client=budget)
    assert (await quota.reserve(operation="discovery")).allowed
    for key in budget.values:
        if ":total:" in key:
            budget.values[key] = 650
    instance = provider(budget)
    result = await push(instance, [message("STD"), message("DLX")])
    assert not result.success and result.metadata["provider_write_count"] == 0
    instance._transport.send_soap.assert_not_awaited()
