"""Regression tests for POST /api/pos/check-split (pos_core.split_check).

Covers the Sentry production bug (TypeError: '<' not supported between str and int)
plus the defensive hardening added on top:
  - by_item: string indices, non-numeric, negative, out-of-range
  - by_item: all-invalid payload returns 400 (no silent empty splits)
  - custom: string amounts, non-numeric amounts default to 0
  - custom/by_item: non-numeric split_num falls back to sequential number
  - response includes total_validation with expected/actual/delta/match
  - equal split path remains unaffected
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import pos_core


class _FakeColl:
    def __init__(self, doc):
        self._doc = doc

    async def find_one(self, *_a, **_kw):
        return self._doc

    async def update_one(self, *_a, **_kw):
        return SimpleNamespace(modified_count=1)


class _FakeDB:
    def __init__(self, doc):
        self.pos_transactions = _FakeColl(doc)


@pytest.fixture
def fake_user():
    return SimpleNamespace(id="u1", tenant_id="t1")


@pytest.fixture
def fake_txn():
    return {
        "id": "tx1",
        "tenant_id": "t1",
        "total_amount": 100.0,
        "order_items": [
            {"name": "Burger", "price": 40.0},
            {"name": "Fries", "price": 25.0},
            {"name": "Soda", "price": 35.0},
        ],
    }


async def _call(monkeypatch, fake_user, fake_txn, **kw):
    monkeypatch.setattr(pos_core, "db", _FakeDB(fake_txn))
    return await pos_core.split_check(
        transaction_id="tx1",
        split_type=kw.pop("split_type"),
        split_count=kw.pop("split_count", 2),
        split_details=kw.pop("split_details", None),
        current_user=fake_user,
        _perm=None,
    )


async def test_by_item_string_indices_does_not_crash(monkeypatch, fake_user, fake_txn):
    """Sentry root cause: split_details inner-list values arriving as strings."""
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="by_item",
        split_details={"1": ["0", "1"], "2": ["2"]},
    )
    assert res["success"] is True
    splits = {s["split_number"]: s for s in res["splits"]}
    assert splits[1]["amount"] == 65.0
    assert splits[2]["amount"] == 35.0
    assert res["total_validation"]["match"] is True


async def test_by_item_negative_index_dropped(monkeypatch, fake_user, fake_txn):
    """Python's negative-index access (-1 -> last item) must NOT be exploitable."""
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="by_item",
        split_details={"1": [-1, 0]},
    )
    splits = {s["split_number"]: s for s in res["splits"]}
    assert splits[1]["amount"] == 40.0
    assert splits[1]["items"] == ["Burger"]


async def test_by_item_all_invalid_indices_returns_400(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as exc:
        await _call(
            monkeypatch, fake_user, fake_txn,
            split_type="by_item",
            split_details={"1": ["x", "y"], "2": [99]},
        )
    assert exc.value.status_code == 400


async def test_by_item_out_of_range_index_dropped(monkeypatch, fake_user, fake_txn):
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="by_item",
        split_details={"1": [0, 99], "2": [2]},
    )
    splits = {s["split_number"]: s for s in res["splits"]}
    assert splits[1]["amount"] == 40.0
    assert splits[2]["amount"] == 35.0


async def test_by_item_non_numeric_split_num_falls_back(monkeypatch, fake_user, fake_txn):
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="by_item",
        split_details={"abc": [0]},
    )
    assert res["splits"][0]["split_number"] == 1


async def test_custom_string_amounts(monkeypatch, fake_user, fake_txn):
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="custom",
        split_details={"1": "40", "2": "60"},
    )
    splits = {s["split_number"]: s for s in res["splits"]}
    assert splits[1]["amount"] == 40.0
    assert splits[2]["amount"] == 60.0
    assert res["total_validation"]["match"] is True


async def test_custom_non_numeric_amount_defaults_to_zero(monkeypatch, fake_user, fake_txn):
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="custom",
        split_details={"1": "abc"},
    )
    assert res["splits"][0]["amount"] == 0.0


async def test_equal_split_unaffected(monkeypatch, fake_user, fake_txn):
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="equal",
        split_count=4,
    )
    assert len(res["splits"]) == 4
    assert all(s["amount"] == 25.0 for s in res["splits"])
    assert res["total_validation"]["match"] is True


async def test_total_validation_detects_mismatch(monkeypatch, fake_user, fake_txn):
    """When client only assigns a subset of items, total_validation flags the delta."""
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="by_item",
        split_details={"1": [0]},
    )
    assert res["total_validation"]["expected"] == 100.0
    assert res["total_validation"]["actual"] == 40.0
    assert res["total_validation"]["delta"] == -60.0
    assert res["total_validation"]["match"] is False


async def test_missing_split_details_returns_400_by_item(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as exc:
        await _call(
            monkeypatch, fake_user, fake_txn,
            split_type="by_item",
            split_details=None,
        )
    assert exc.value.status_code == 400


async def test_by_item_all_empty_arrays_not_blocked(monkeypatch, fake_user, fake_txn):
    """All-empty split arrays (no raw indices) must NOT trigger the all-invalid 400."""
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="by_item",
        split_details={"1": [], "2": []},
    )
    assert res["success"] is True
    assert all(s["amount"] == 0.0 for s in res["splits"])


async def test_total_validation_tolerance_boundary(monkeypatch, fake_user, fake_txn):
    """Floating point delta within 0.01 must report match=True (boundary)."""
    fake_txn["total_amount"] = 100.005
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="custom",
        split_details={"1": 50.0, "2": 50.0},
    )
    assert res["total_validation"]["match"] is True


async def test_transaction_not_found_returns_404(monkeypatch, fake_user):
    with pytest.raises(HTTPException) as exc:
        await _call(
            monkeypatch, fake_user, None,
            split_type="equal",
            split_count=2,
        )
    assert exc.value.status_code == 404
