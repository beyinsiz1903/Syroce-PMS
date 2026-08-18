from __future__ import annotations

from pathlib import Path


def _source() -> str:
    return (
        Path(__file__).resolve().parents[2] / "scripts" / "pre_pilot_reset.py"
    ).read_text(encoding="utf-8")


def test_pre_pilot_reset_uses_no_drop_or_provider_primitives():
    source = _source()
    forbidden = (
        "drop_database(",
        ".drop_collection(",
        "delete_many({})",
        "NilveraHttpClient",
        "requests.post(",
        "httpx.post(",
    )
    for token in forbidden:
        assert token not in source


def test_reset_contract_contains_fail_closed_guards():
    source = _source()
    assert "RESET_COLLECTIONS: tuple[CollectionSpec, ...]" in source
    assert "BLOCKED_COLLECTION_NOT_ALLOWLISTED" in source
    assert "BLOCKED_PLAN_DIGEST_MISMATCH" in source
    assert "CRITICAL_SUPER_ADMIN_POSTCONDITION_FAILED" in source
    assert '"role": {"$ne": SUPER_ADMIN_ROLE}' in source
