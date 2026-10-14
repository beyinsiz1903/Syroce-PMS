"""Fan-out must not queue webhook events for portal-only agencies (Sentry noise)."""

from types import SimpleNamespace

import pytest

from routers import agency_contracts


class _Cursor:
    def __init__(self, rows):
        self._rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._rows)
        except StopIteration:
            raise StopAsyncIteration from None


@pytest.mark.asyncio
async def test_only_contracts_with_https_webhook_are_targets(monkeypatch):
    seen = {}

    def find(query, projection):
        seen["query"] = query
        return _Cursor([{"agency_id": "a1"}, {"agency_id": "a1"}, {"agency_id": "a2"}])

    monkeypatch.setattr(agency_contracts, "get_system_db", lambda: SimpleNamespace(agency_contracts=SimpleNamespace(find=find)))

    assert await agency_contracts.list_webhook_agencies_for_tenant("t1", on_date="2026-10-14") == ["a1", "a2"]
    assert seen["query"]["webhook_url"] == {"$regex": "^https://"}
    assert seen["query"]["status"] == "approved"
    assert seen["query"]["valid_from"] == {"$lte": "2026-10-14"}


@pytest.mark.asyncio
async def test_fan_out_skips_tenant_without_webhook_partners(monkeypatch):
    from core import agency_fanout
    from core.outbox_service import BOOKING_CREATED

    async def no_webhook_partners(tenant_id, on_date=None):
        return []

    async def derived(db, event):
        return ("agency.inventory.availability.updated.v1", {"room_type_id": "Superior"})

    monkeypatch.setattr(agency_contracts, "list_webhook_agencies_for_tenant", no_webhook_partners)
    monkeypatch.setattr(agency_fanout, "_derive_agency_event", derived)

    count = await agency_fanout.fan_out_agency_events({"id": "e1", "tenant_id": "t1", "event_type": BOOKING_CREATED})

    assert count == 0
