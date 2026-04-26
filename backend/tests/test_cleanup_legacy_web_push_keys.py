"""
Safety regression tests for ``backend/scripts/cleanup_legacy_web_push_keys.py``.

The script purges legacy auto-generated VAPID keys from ``db.web_push_keys``.
A bug in the filter (or an over-eager refactor) could silently delete the
production VAPID private key — invalidating every browser PushSubscription
pinned to that public key. These tests pin the script's safety contract:

  * Default mode deletes ONLY rows stamped ``auto_generated: true`` and
    leaves an unmarked (operator-inserted) row strictly untouched.
  * ``--dry-run`` performs zero writes regardless of mode.
  * ``--mark-only`` never deletes anything; it only stamps the
    ``auto_generated`` marker on legacy unmarked rows.

We replace ``AsyncIOMotorClient`` inside the script module with an
in-memory fake so the test runs without a real Mongo / motor dependency.
"""
from __future__ import annotations

import copy
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts import cleanup_legacy_web_push_keys as cleanup


# ── In-memory Mongo fake ─────────────────────────────────────────────────
#
# The script touches a very narrow surface of the Motor API:
#   client.admin.command("ping")
#   client[db_name]                            → db
#   db.web_push_keys                           → collection
#   coll.find({})                              → async-iterable cursor
#   coll.count_documents(filter)               → awaitable int
#   coll.update_one(filter, {"$set": {...}})   → awaitable
#   coll.delete_many(filter)                   → awaitable result with .deleted_count
#
# Reproducing only that surface keeps the fake small and obvious. Any new
# Mongo call introduced by the script will surface here as an
# AttributeError, not silently no-op.


def _matches(doc: dict[str, Any], filter_: dict[str, Any]) -> bool:
    """Bare-bones equality match: every key in `filter_` must equal `doc[k]`."""
    for k, v in filter_.items():
        if doc.get(k) != v:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]):
        self._docs = docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    """Tiny in-memory stand-in for `db.web_push_keys`."""

    def __init__(self) -> None:
        # Keyed by `_id` so update_one can target a specific row.
        self.docs: dict[Any, dict[str, Any]] = {}

    # --- helpers used by the test (not by the script) -----------------
    def insert(self, doc: dict[str, Any]) -> None:
        self.docs[doc["_id"]] = copy.deepcopy(doc)

    def all(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(d) for d in self.docs.values()]

    # --- Motor surface used by the script -----------------------------
    def find(self, filter_: dict[str, Any]) -> _FakeCursor:
        # Hand out copies so the script can't mutate our store by accident.
        matched = [copy.deepcopy(d) for d in self.docs.values() if _matches(d, filter_)]
        return _FakeCursor(matched)

    async def count_documents(self, filter_: dict[str, Any]) -> int:
        return sum(1 for d in self.docs.values() if _matches(d, filter_))

    async def update_one(self, filter_: dict[str, Any], update: dict[str, Any]) -> None:
        for d in self.docs.values():
            if _matches(d, filter_):
                if "$set" in update:
                    d.update(update["$set"])
                return

    async def delete_many(self, filter_: dict[str, Any]):
        to_del = [k for k, d in self.docs.items() if _matches(d, filter_)]
        for k in to_del:
            del self.docs[k]
        result = MagicMock()
        result.deleted_count = len(to_del)
        return result


class _FakeAdmin:
    async def command(self, *_args, **_kwargs):
        return {"ok": 1}


class _FakeDB:
    def __init__(self, coll: _FakeCollection) -> None:
        self.web_push_keys = coll


class _FakeClient:
    """Stands in for `AsyncIOMotorClient(mongo_url, ...)`.

    The constructor signature mirrors Motor's so the script's call site
    (`AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)`) works
    unchanged.
    """

    def __init__(self, *_args, _coll: _FakeCollection, **_kwargs) -> None:
        self.admin = _FakeAdmin()
        self._db = _FakeDB(_coll)

    def __getitem__(self, _name: str) -> _FakeDB:
        return self._db


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def fake_collection(monkeypatch) -> _FakeCollection:
    """Patch the script to talk to an in-memory collection.

    Returns the collection so the test can pre-seed rows and inspect the
    final state after the script runs.
    """
    coll = _FakeCollection()

    def _factory(*args, **kwargs):
        return _FakeClient(*args, _coll=coll, **kwargs)

    monkeypatch.setattr(cleanup, "AsyncIOMotorClient", _factory)
    return coll


def _auto_generated_doc() -> dict[str, Any]:
    """A doc the script's default mode IS allowed to delete."""
    return {
        "_id": "singleton",
        "public_key": "auto-pub-key-base64url",
        "private_key": "auto-priv-key-base64url",
        "private_key_pem": "-----BEGIN PRIVATE KEY-----\nAUTO\n-----END PRIVATE KEY-----\n",
        "created_at": "2024-01-01T00:00:00+00:00",
        "auto_generated": True,
    }


def _operator_inserted_doc() -> dict[str, Any]:
    """A doc the operator placed manually — MUST survive every mode but --force."""
    return {
        "_id": "operator-pinned",
        "public_key": "operator-pub-key-base64url",
        "private_key": "operator-priv-key-base64url",
        "created_at": "2023-06-01T00:00:00+00:00",
        # Crucially: NO `auto_generated` marker. This is the regression
        # surface — the script must never touch this row by default.
    }


# ── Tests ─────────────────────────────────────────────────────────────────

async def test_default_mode_deletes_only_auto_generated_records(fake_collection):
    """Default run wipes the marked record but leaves the unmarked one alone."""
    fake_collection.insert(_auto_generated_doc())
    fake_collection.insert(_operator_inserted_doc())

    rc = await cleanup._run(cleanup._parse_args([]))

    assert rc == 0
    remaining = fake_collection.all()
    assert len(remaining) == 1, (
        "Default mode must NOT touch records missing `auto_generated: true` — "
        "an operator-inserted row was deleted, which would silently destroy "
        "the production VAPID private key."
    )
    assert remaining[0]["_id"] == "operator-pinned"
    # The surviving row must be byte-for-byte intact (no metadata stamping
    # in the destructive flow).
    assert remaining[0] == _operator_inserted_doc()


async def test_default_mode_leaves_unmarked_record_when_no_auto_generated_present(
    fake_collection,
):
    """Without any `auto_generated: true` row, default mode is a strict no-op."""
    fake_collection.insert(_operator_inserted_doc())

    rc = await cleanup._run(cleanup._parse_args([]))

    assert rc == 0
    assert fake_collection.all() == [_operator_inserted_doc()]


async def test_dry_run_makes_no_writes(fake_collection):
    """`--dry-run` must not delete, update, or stamp anything."""
    auto = _auto_generated_doc()
    operator = _operator_inserted_doc()
    fake_collection.insert(auto)
    fake_collection.insert(operator)

    rc = await cleanup._run(cleanup._parse_args(["--dry-run"]))

    assert rc == 0
    remaining = sorted(fake_collection.all(), key=lambda d: d["_id"])
    assert remaining == sorted([auto, operator], key=lambda d: d["_id"]), (
        "`--dry-run` is a preview mode and MUST be a true read-only no-op."
    )


async def test_mark_only_stamps_unmarked_record_without_deleting(fake_collection):
    """`--mark-only` adds the `auto_generated: true` marker but never deletes."""
    fake_collection.insert(_auto_generated_doc())
    fake_collection.insert(_operator_inserted_doc())

    rc = await cleanup._run(cleanup._parse_args(["--mark-only"]))

    assert rc == 0
    remaining = {d["_id"]: d for d in fake_collection.all()}
    # Both rows survive — `--mark-only` is purely additive metadata.
    assert set(remaining.keys()) == {"singleton", "operator-pinned"}

    # The previously-unmarked operator row was stamped...
    op = remaining["operator-pinned"]
    assert op.get("auto_generated") is True, (
        "`--mark-only` should stamp `auto_generated: true` on legacy "
        "unmarked rows so the operator can decide whether to delete them."
    )
    assert "auto_generated_marked_at" in op, (
        "Stamped rows should carry an `auto_generated_marked_at` timestamp "
        "so an operator can distinguish a freshly-stamped row from an "
        "originally auto-generated one."
    )

    # ...and the originally-marked row was left exactly as it was (no
    # re-stamping that would lose forensic timestamps on legitimate
    # auto-generated rows).
    assert remaining["singleton"] == _auto_generated_doc()


async def test_mark_only_dry_run_neither_stamps_nor_deletes(fake_collection):
    """`--mark-only --dry-run` is a pure preview: zero writes."""
    fake_collection.insert(_operator_inserted_doc())

    rc = await cleanup._run(cleanup._parse_args(["--mark-only", "--dry-run"]))

    assert rc == 0
    assert fake_collection.all() == [_operator_inserted_doc()]
