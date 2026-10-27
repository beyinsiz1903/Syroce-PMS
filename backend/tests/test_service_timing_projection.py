from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.pms_core.service_timing import project_service_times


class SourceDB:
    def __init__(self, records, timezone="Europe/Istanbul"):
        self.records = records
        self.reads = []
        self.tenant_settings = SimpleNamespace(find_one=AsyncMock(return_value={"timezone": timezone}))

    def __getitem__(self, collection):
        def find(query, projection):
            self.reads.append((collection, query, projection))
            rows = [deepcopy(row) for row in self.records.get(collection, [])
                    if row.get("tenant_id") == query["tenant_id"] and row["id"] in query["id"]["$in"]]
            return SimpleNamespace(to_list=AsyncMock(return_value=rows))
        return SimpleNamespace(find=find)


@pytest.mark.asyncio
async def test_projects_source_time_in_hotel_zone_without_changing_source_or_financial_fields():
    records = {"spa_appointments": [{"id": "s", "tenant_id": "t", "starts_at": "2026-10-24T21:30:00Z"}],
               "pos_orders": [{"id": "p", "tenant_id": "t", "created_at": "2026-10-24T16:15:00Z"}]}
    original = deepcopy(records)
    database = SourceDB(records)
    charges = [{"source_spa_appointment_id": "s", "amount": 30, "currency": "USD", "business_date": "2026-10-26"},
               {"source_pos_order_id": "p", "amount": 12, "created_at": "2026-10-27T10:00:00Z"}]
    await project_service_times(database, "t", charges)
    assert (charges[0]["service_date"], charges[0]["service_time"]) == ("2026-10-25", "00:30")
    assert charges[0]["service_timing_source"] == "spa_appointment"
    assert charges[0]["amount"] == 30 and charges[0]["currency"] == "USD"
    assert charges[0]["business_date"] == "2026-10-26"
    assert charges[1]["service_time"] == "19:15"
    assert charges[1]["service_timing_source"] == "pos_order"
    assert records == original
    assert all(query["tenant_id"] == "t" for _, query, _ in database.reads)


@pytest.mark.asyncio
async def test_missing_foreign_invalid_sources_do_not_become_posting_times():
    database = SourceDB({"spa_appointments": [{"id": "foreign", "tenant_id": "other", "starts_at": "2026-10-24T15:30:00Z"},
                                             {"id": "bad", "tenant_id": "t", "starts_at": "not-a-date"}]})
    charges = [{"source_spa_appointment_id": source, "posted_at": "2026-10-27T08:00:00Z"} for source in ("foreign", "missing", "bad")]
    before = deepcopy(charges)
    await project_service_times(database, "t", charges)
    assert charges == before


@pytest.mark.asyncio
async def test_manual_date_is_never_overwritten_and_old_rows_do_not_trigger_queries():
    database = SourceDB({})
    charges = [{"service_date": "2026-10-20", "service_time": "12:30", "source_spa_appointment_id": "s"},
               {"category": "food", "created_at": "2026-10-27T10:00:00Z"}]
    before = deepcopy(charges)
    await project_service_times(database, "t", charges)
    assert charges == before
    assert database.reads == []
    database.tenant_settings.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_naive_source_contract_is_utc_and_invalid_timezone_is_explicit_utc():
    database = SourceDB({"spa_appointments": [{"id": "s", "tenant_id": "t", "starts_at": "2026-10-24T12:00:00"}]}, timezone="invalid/zone")
    charges = [{"source_spa_appointment_id": "s"}]
    await project_service_times(database, "t", charges)
    assert charges[0]["service_timezone"] == "UTC"
    assert charges[0]["service_time"] == "12:00"
