from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager import incident_router


class _AsyncRows:
    def __init__(self, rows):
        self._rows = iter(rows)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._rows)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _SummaryCollection:
    def __init__(self):
        self.pipelines = []
        self.count_filters = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        if len(self.pipelines) == 1:
            return _AsyncRows([{"_id": {"status": "open", "severity": "high"}, "count": 2}])
        return _AsyncRows([{"_id": "payload_mismatch", "count": 2}])

    async def count_documents(self, query):
        self.count_filters.append(query)
        return 1


class _DetailCursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def to_list(self, *_args):
        return self._rows


@pytest.mark.asyncio
async def test_incident_summary_uses_global_scope_for_super_admin(monkeypatch):
    incidents = _SummaryCollection()
    ari = _SummaryCollection()
    fake_db = {
        incident_router.COLL_RECONCILIATION_CASES: incidents,
        incident_router.COLL_ARI_CHANGE_SETS: ari,
    }
    monkeypatch.setattr(incident_router, "db", fake_db)

    result = await incident_router.incident_summary(
        current_user=SimpleNamespace(role="super_admin", tenant_id="admin-tenant", is_impersonating=False)
    )

    assert incidents.pipelines[0][0] == {"$match": {}}
    assert incidents.pipelines[1][0] == {"$match": {"status": {"$in": ["open", "investigating"]}}}
    assert ari.count_filters == [{"status": "manual_review"}]
    assert result["total_incidents"] == 2
    assert result["ari_dead_letters"] == 1


@pytest.mark.asyncio
async def test_incident_summary_scopes_impersonated_admin_to_active_tenant(monkeypatch):
    incidents = _SummaryCollection()
    ari = _SummaryCollection()
    monkeypatch.setattr(
        incident_router,
        "db",
        {
            incident_router.COLL_RECONCILIATION_CASES: incidents,
            incident_router.COLL_ARI_CHANGE_SETS: ari,
        },
    )

    await incident_router.incident_summary(
        current_user=SimpleNamespace(role="super_admin", tenant_id="tenant-a", is_impersonating=True)
    )

    assert incidents.pipelines[0][0] == {"$match": {"tenant_id": "tenant-a"}}
    assert incidents.pipelines[1][0]["$match"]["tenant_id"] == "tenant-a"
    assert ari.count_filters == [{"tenant_id": "tenant-a", "status": "manual_review"}]


@pytest.mark.asyncio
async def test_incident_detail_uses_found_incident_tenant_for_related_queries(monkeypatch):
    incidents = SimpleNamespace(
        find_one=AsyncMock(
            return_value={
                "id": "incident-1",
                "tenant_id": "tenant-found",
                "drift_type": "unknown_internal_type",
                "external_reservation_id": "reservation-1",
            }
        )
    )
    audit = SimpleNamespace(find=lambda query, *_args: _DetailCursor([{"query": query}]))
    lineage = SimpleNamespace(find_one=AsyncMock(return_value={"id": "lineage-1"}))
    ari = SimpleNamespace(find=lambda *_args: _DetailCursor([]))
    monkeypatch.setattr(
        incident_router,
        "db",
        {
            incident_router.COLL_RECONCILIATION_CASES: incidents,
            incident_router.COLL_INCIDENT_AUDIT: audit,
            incident_router.COLL_RESERVATION_LINEAGE: lineage,
            incident_router.COLL_ARI_CHANGE_SETS: ari,
        },
    )

    result = await incident_router.get_incident_detail(
        "incident-1",
        current_user=SimpleNamespace(role="super_admin", tenant_id="admin-tenant", is_impersonating=False),
    )

    lineage.find_one.assert_awaited_once_with(
        {"tenant_id": "tenant-found", "external_reservation_id": "reservation-1"},
        incident_router._NO_ID,
    )
    assert result["audit_trail"][0]["query"]["tenant_id"] == "tenant-found"
    assert result["incident"]["recommended_action"] == "manual_review"

