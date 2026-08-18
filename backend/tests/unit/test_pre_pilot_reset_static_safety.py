from __future__ import annotations

from pathlib import Path


def test_pre_pilot_reset_uses_no_drop_or_provider_primitives():
    source = (
        Path(__file__).resolve().parents[2] / "scripts" / "pre_pilot_reset.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "drop_database(",
        ".drop_collection(",
        "delete_many({})",
        "NilveraHttpClient",
        "HotelRunner",
        "Exely",
        "requests.post(",
        "httpx.post(",
    )
    for token in forbidden:
        assert token not in source


def test_reset_collection_names_are_literal_allowlist_entries():
    source = (
        Path(__file__).resolve().parents[2] / "scripts" / "pre_pilot_reset.py"
    ).read_text(encoding="utf-8")

    assert "RESET_COLLECTIONS: tuple[CollectionSpec, ...]" in source
    assert "BLOCKED_COLLECTION_NOT_ALLOWLISTED" in source
    assert "CRITICAL_SUPER_ADMIN_POSTCONDITION_FAILED" in source
