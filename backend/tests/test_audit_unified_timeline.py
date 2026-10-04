"""Contract tests for the unified, verifiable audit timeline."""

from __future__ import annotations

import pytest


def test_signed_export_is_verifiable_and_tamper_evident():
    from core.audit_export import build_signed_export, verify_signed_export

    package = build_signed_export(
        tenant_id="hotel-a",
        actor_id="manager-1",
        events=[{"id": "evt-1", "action": "reservation.updated"}],
        filters={"entity_type": "reservation"},
        chain_status={"ok": True, "checked": 1},
        key=b"audit-export-test-key",
    )

    assert package["signature"]["algorithm"] == "HMAC-SHA256"
    assert verify_signed_export(package, b"audit-export-test-key") is True
    package["payload"]["events"][0]["action"] = "reservation.deleted"
    assert verify_signed_export(package, b"audit-export-test-key") is False


def test_signed_export_requires_a_dedicated_key(monkeypatch):
    from core.audit_export import SIGNING_KEY_ENV, build_signed_export

    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    with pytest.raises(RuntimeError, match=SIGNING_KEY_ENV):
        build_signed_export(
            tenant_id="hotel-a",
            actor_id="manager-1",
            events=[],
            filters={},
        )


def test_entity_query_links_reservation_aliases_without_cross_tenant_scope():
    from routers.audit_timeline import _entity_timeline_query

    entity_type, query = _entity_timeline_query("hotel-a", "booking", "booking-42")

    assert entity_type == "reservation"
    assert query["tenant_id"] == "hotel-a"
    relation_values = [next(iter(item.values())) for item in query["$and"][1]["$or"]]
    assert "booking-42" in relation_values
    assert any(item.get("target_type", {}).get("$in") == ("reservation", "booking", "bookings") for item in query["$and"][0]["$or"])


def test_entity_query_rejects_unsupported_or_unbounded_entity_types():
    from fastapi import HTTPException
    from routers.audit_timeline import _entity_timeline_query

    with pytest.raises(HTTPException) as unsupported:
        _entity_timeline_query("hotel-a", "guest", "guest-1")
    assert unsupported.value.status_code == 422

    with pytest.raises(HTTPException) as invalid_id:
        _entity_timeline_query("hotel-a", "room", "x" * 161)
    assert invalid_id.value.status_code == 422


@pytest.mark.asyncio
async def test_retention_status_reports_the_configured_audit_contract(monkeypatch):
    from routers import audit_timeline as timeline

    class _Policies:
        async def find_one(self, *_args, **_kwargs):
            return {"configured": True, "audit_log_retention_days": 1825}

    monkeypatch.setattr(timeline, "db", type("Database", (), {"gdpr_retention_policies": _Policies()})())
    status = await timeline._retention_status("hotel-a")

    assert status == {
        "configured": True,
        "audit_log_retention_days": 1825,
        "hot_store_days": 365,
        "archive_enabled": True,
        "archive_immutable": True,
        "policy_source": "gdpr_retention_policy",
    }
