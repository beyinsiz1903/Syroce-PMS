from shared_kernel.shadow_metrics import (
    compare_availability_payloads,
    compare_folio_payloads,
    hash_payload,
    shadow_metrics_store,
)


def test_compare_availability_payloads_detects_field_drift():
    semantic = [{"id": "room-1", "room_type": "STD", "available": True, "capacity": 2, "blocks": []}]
    legacy = [{"id": "room-1", "room_type": "STD", "available": False, "capacity": 2, "blocks": []}]

    result = compare_availability_payloads(semantic, legacy)
    assert result["compare_result"] == "mismatch"
    assert "available" in result["mismatch_fields"]


def test_compare_folio_payloads_detects_balance_drift():
    semantic = {
        "folio": {"id": "folio-1", "status": "open", "currency": "TRY", "guest_id": "guest-1", "booking_id": "stay-1"},
        "charges": [],
        "payments": [],
        "balance": 10,
    }
    legacy = {
        "folio": {"id": "folio-1", "status": "open", "currency": "TRY", "guest_id": "guest-1", "booking_id": "stay-1"},
        "charges": [],
        "payments": [],
        "balance": 12,
    }

    result = compare_folio_payloads(semantic, legacy)
    assert result["compare_result"] == "mismatch"
    assert "balance" in result["mismatch_fields"]


def test_shadow_metrics_store_records_compare_events():
    event = {
        "endpoint": "availability",
        "compare_result": "mismatch",
        "mismatch_fields": ["available", "capacity"],
    }
    before_total = shadow_metrics_store.get_metric("shadow.availability.compare.total")
    before_mismatch = shadow_metrics_store.get_metric("shadow.availability.compare.mismatch")
    shadow_metrics_store.record(event)
    assert shadow_metrics_store.get_metric("shadow.availability.compare.total") == before_total + 1
    assert shadow_metrics_store.get_metric("shadow.availability.compare.mismatch") == before_mismatch + 1


def test_hash_payload_is_stable_for_equivalent_shapes():
    left = {"b": 1, "a": [2, 1]}
    right = {"a": [1, 2], "b": 1}
    assert hash_payload(left) == hash_payload(right)