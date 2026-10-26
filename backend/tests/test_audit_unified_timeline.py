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


@pytest.mark.asyncio
async def test_entity_trail_keeps_protected_room_and_payment_metadata(monkeypatch):
    from routers import audit_timeline as timeline

    original = {'id': 'e', 'tenant_id': 'hotel-a', 'actor_id': 'operator', 'action': 'room_swap',
        'entity_type': 'reservation', 'entity_id': 'b', 'timestamp': '2026-10-25T12:00:00Z',
        'metadata': {'from_room': '102', 'to_room': '103', 'reason': 'Misafir oda tercihi',
            'amount': 100, 'currency': 'EUR', 'password': 'never-return-this'}}
    class Cursor:
        def sort(self, *args):
            return self
        def limit(self, *args):
            return self
        async def to_list(self, *args):
            return [original]
    class Logs:
        def find(self, query, *args):
            assert query['tenant_id'] == 'hotel-a'
            return Cursor()
    from types import SimpleNamespace
    monkeypatch.setattr(timeline, 'db', SimpleNamespace(audit_logs=Logs()))
    result = await timeline.get_entity_audit_trail('reservation', 'b', limit=50,
        current_user=SimpleNamespace(tenant_id='hotel-a', id='operator', role='admin'), _perm=None)
    row = result['trail'][0]
    assert row['operation'] == 'room_swap' and row['actor_id'] == 'operator'
    assert row['metadata']['from_room'] == '102' and row['metadata']['to_room'] == '103'
    assert row['metadata']['reason'] == 'Misafir oda tercihi' and row['metadata']['currency'] == 'EUR'
    assert 'never-return-this' not in str(result) and original['metadata']['password'] == 'never-return-this'


@pytest.mark.asyncio
async def test_reservation_local_payment_is_visible_without_claiming_a_hash_chain(monkeypatch):
    from types import SimpleNamespace
    from routers import audit_timeline as timeline
    class Cursor:
        def __init__(self, rows):
            self.rows = rows
        def sort(self, *args):
            return self
        def limit(self, *args):
            return self
        async def to_list(self, *args):
            return self.rows
    class Collection:
        def __init__(self, rows):
            self.rows = rows
        def find(self, query, *args):
            assert query['tenant_id'] == 'hotel'
            return Cursor(self.rows)
    payment = {'id': 'payment-log', 'booking_id': 'b', 'actor': 'Ayşe Kaya', 'action': 'payment_recorded',
        'created_at': '2026-10-25T15:00:00+03:00', 'details': {'amount': 2200, 'currency': 'TRY',
            'received_currency': 'EUR', 'received_amount': 40, 'method': 'cash'}}
    monkeypatch.setattr(timeline, 'db', SimpleNamespace(audit_logs=Collection([]), reservation_activity_log=Collection([payment])))
    result = await timeline.get_entity_audit_trail('reservation', 'b', limit=50,
        current_user=SimpleNamespace(tenant_id='hotel', id='manager', role='admin'), _perm=None)
    entry = result['trail'][0]
    assert entry['actor_name'] == 'Ayşe Kaya' and entry['operation'] == 'payment_recorded'
    assert entry['metadata']['received_amount'] == 40 and entry['metadata']['received_currency'] == 'EUR'
    assert entry['evidence_source'] == 'reservation_activity_log' and 'record_hash' not in entry
