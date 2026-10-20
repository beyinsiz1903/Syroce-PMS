"""Contract tests for the unified, verifiable audit timeline."""

from __future__ import annotations

import pytest


def test_legacy_audit_details_and_snapshots_are_normalized_and_protected():
    from routers.audit_timeline import _normalize_audit_record

    original = {
        "user_id": "operator-42", "action": "room.updated", "entity_id": "room-203",
        "before_value": {"room_status": "dirty", "password": "old-secret"},
        "after_value": {"room_status": "clean", "password": "new-secret"},
        "details": "Oda temizlendi token=private-value",
        "metadata": {"room_number": "203", "refresh_token": "private-token"},
    }
    result = _normalize_audit_record(original, {"role": "admin"})
    assert result["actor_id"] == "operator-42"
    assert result["target_id"] == "room-203"
    assert result["before_snapshot"]["room_status"] == "dirty"
    assert result["after_snapshot"]["room_status"] == "clean"
    assert "private-value" not in result["details"]
    for field in ("before_snapshot", "before_value", "after_snapshot", "after_value", "metadata"):
        assert "secret" not in str(result[field])
        assert "private-token" not in str(result[field])
    # Reading historical logs must not mutate the stored chain payload.
    assert original["before_value"]["password"] == "old-secret"


def test_canonical_audit_snapshots_take_precedence_over_legacy_aliases():
    from routers.audit_timeline import _normalize_audit_record

    result = _normalize_audit_record({"before_snapshot": {}, "before_value": {"status": "dirty"}}, {"role": "admin"})
    assert result["before_snapshot"] == {}


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
