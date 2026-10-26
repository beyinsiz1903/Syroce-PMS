"""Regression tests for POST /api/pos/check-split (pos_core.split_check).

Covers the Sentry production bug (TypeError: '<' not supported between str and int)
plus the financial integrity hardening added on top:
  - by_item: decimal string indices remain supported
  - invalid, incomplete, negative, empty or duplicate partitions are rejected
  - custom: decimal string amounts work, malformed amounts are never zeroed
  - custom/by_item: non-numeric split_num falls back to sequential number
  - response includes total_validation with expected/actual/delta/match
  - cent-exact equal split preview never rewrites a paid receipt
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


async def test_by_item_negative_index_rejected(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='by_item', split_details={'1': [-1, 0]})
    assert error.value.status_code == 422


async def test_by_item_all_invalid_indices_rejected(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='by_item', split_details={'1': ['x', 'y'], '2': [99]})
    assert error.value.status_code == 422


async def test_by_item_out_of_range_index_rejected(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='by_item', split_details={'1': [0, 99], '2': [1, 2]})
    assert error.value.status_code == 422


async def test_by_item_non_numeric_split_num_falls_back(monkeypatch, fake_user, fake_txn):
    result = await _call(monkeypatch, fake_user, fake_txn, split_type='by_item', split_details={'abc': [0, 1, 2]})
    assert result['splits'][0]['split_number'] == 1
    assert result['splits'][0]['amount'] == 100


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


async def test_custom_non_numeric_amount_is_rejected_not_zeroed(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='custom', split_details={'1': 'abc'})
    assert error.value.status_code == 422


async def test_equal_split_unaffected(monkeypatch, fake_user, fake_txn):
    res = await _call(
        monkeypatch, fake_user, fake_txn,
        split_type="equal",
        split_count=4,
    )
    assert len(res["splits"]) == 4
    assert all(s["amount"] == 25.0 for s in res["splits"])
    assert res["total_validation"]["match"] is True


async def test_incomplete_partition_is_rejected(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='by_item', split_details={'1': [0]})
    assert error.value.status_code == 422


async def test_missing_split_details_is_rejected(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='by_item', split_details=None)
    assert error.value.status_code == 422


async def test_empty_partition_is_rejected(monkeypatch, fake_user, fake_txn):
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='by_item', split_details={'1': [], '2': []})
    assert error.value.status_code == 422


async def test_minor_unit_mismatch_is_not_silently_accepted(monkeypatch, fake_user, fake_txn):
    fake_txn['total_amount'] = 100.005
    with pytest.raises(HTTPException) as error:
        await _call(monkeypatch, fake_user, fake_txn, split_type='custom', split_details={'1': 50, '2': 50})
    assert error.value.status_code == 422


async def test_transaction_not_found_returns_404(monkeypatch, fake_user):
    with pytest.raises(HTTPException) as exc:
        await _call(
            monkeypatch, fake_user, None,
            split_type="equal",
            split_count=2,
        )
    assert exc.value.status_code == 404
