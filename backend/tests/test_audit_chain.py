"""
Tests: Tamper-evident audit hash chain (Task #568).

Validates:
  - compute_record_hash determinism + tamper-sensitivity (content + chain links)
  - verify_chain detects content tampering, link tampering, and deletion gaps
  - verify_chain treats legacy (unchained) rows as skipped, not broken
  - the first record in a window is treated as the chain start

These tests are pure: compute_record_hash needs no DB, and verify_chain is
exercised against an in-memory fake system db, so they run without Mongo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import audit_chain
from core.audit_chain import compute_record_hash, verify_chain


def _entry(**over):
    base = {
        "tenant_id": "t1",
        "actor_id": "u1",
        "operation_name": "folio_payment_voided",
        "action": "folio_payment_voided",
        "target_type": "payment",
        "entity_type": "payment",
        "target_id": "p1",
        "entity_id": "p1",
        "result_status": "success",
        "severity": "warning",
        "before_snapshot": {"voided": False},
        "after_snapshot": {"voided": True},
        "ip_address": "203.0.113.7",
        "user_agent": "pytest-agent/1.0",
        "timestamp": "2026-06-12T10:00:00+00:00",
    }
    base.update(over)
    return base


# ── compute_record_hash ───────────────────────────────────

def test_hash_is_deterministic():
    e = _entry()
    assert compute_record_hash(e, 1, "") == compute_record_hash(dict(e), 1, "")


def test_hash_changes_when_content_changes():
    e = _entry()
    h1 = compute_record_hash(e, 1, "")
    h2 = compute_record_hash(_entry(after_snapshot={"voided": False}), 1, "")
    assert h1 != h2


def test_hash_changes_with_seq_and_prev():
    e = _entry()
    assert compute_record_hash(e, 1, "") != compute_record_hash(e, 2, "")
    assert compute_record_hash(e, 1, "") != compute_record_hash(e, 1, "abc")


def test_unhashed_fields_do_not_affect_hash():
    # `details`/`id` are not in the hashed set — changing them must not move the hash.
    e = _entry()
    h1 = compute_record_hash(e, 1, "")
    e2 = _entry()
    e2["details"] = "totally different free text"
    e2["id"] = "some-uuid"
    assert compute_record_hash(e2, 1, "") == h1


# ── verify_chain (in-memory fake system db) ────────────────

class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    async def to_list(self, *a, **k):
        return list(self._rows)


def _ts_match(value, cond):
    """Minimal $gte/$lt support over comparable (str/datetime) timestamps."""
    if not isinstance(cond, dict):
        return value == cond
    ok = True
    if "$gte" in cond:
        ok = ok and value is not None and value >= cond["$gte"]
    if "$lt" in cond:
        ok = ok and value is not None and value < cond["$lt"]
    return ok


class _FakeColl:
    def __init__(self, rows):
        self._rows = rows

    def find(self, query, projection=None):
        rows = [
            r for r in self._rows
            if r.get("tenant_id") == query.get("tenant_id") and "record_hash" in r
        ]
        rows.sort(key=lambda r: r.get("seq", 0))
        return _FakeCursor(rows)

    async def count_documents(self, query):
        n = 0
        for r in self._rows:
            if r.get("tenant_id") != query.get("tenant_id"):
                continue
            rh = query.get("record_hash")
            if isinstance(rh, dict) and "$exists" in rh:
                has = "record_hash" in r
                if has != rh["$exists"]:
                    continue
            ts_cond = query.get("timestamp")
            if ts_cond is not None and not _ts_match(r.get("timestamp"), ts_cond):
                continue
            n += 1
        return n


class _FakeDB:
    def __init__(self, rows, archive_rows=None):
        self._colls = {
            "audit_logs": _FakeColl(rows),
            "audit_logs_archive": _FakeColl(archive_rows or []),
        }
        self.audit_logs = self._colls["audit_logs"]
        self.audit_logs_archive = self._colls["audit_logs_archive"]

    def __getitem__(self, name):
        return self._colls[name]


def _chained_rows(n, tenant_id="t1"):
    """Build a valid n-record chain the way append_audit_log would."""
    rows = []
    prev = ""
    for i in range(1, n + 1):
        seq = i
        e = _entry(tenant_id=tenant_id, target_id=f"p{i}", entity_id=f"p{i}",
                   timestamp=f"2026-06-12T10:0{i}:00+00:00")
        rh = compute_record_hash(e, seq, prev)
        e.update({"id": f"id{i}", "seq": seq, "prev_hash": prev, "record_hash": rh})
        rows.append(e)
        prev = rh
    return rows


@pytest.fixture
def patch_sysdb(monkeypatch):
    def _install(rows, archive_rows=None):
        monkeypatch.setattr(audit_chain, "_system_db", lambda: _FakeDB(rows, archive_rows))
    return _install


async def test_verify_clean_chain_ok(patch_sysdb):
    patch_sysdb(_chained_rows(5))
    res = await verify_chain("t1")
    assert res["ok"] is True
    assert res["checked"] == 5
    assert res["breaks"] == []
    assert res["last_seq"] == 5


async def test_verify_detects_content_tamper(patch_sysdb):
    rows = _chained_rows(5)
    # Mutate a stored field WITHOUT recomputing its hash → content mismatch.
    rows[2]["after_snapshot"] = {"voided": False, "amount": 9999}
    patch_sysdb(rows)
    res = await verify_chain("t1")
    assert res["ok"] is False
    assert any(b["reason"] == "content_hash_mismatch" and b["seq"] == 3 for b in res["breaks"])


async def test_verify_detects_deletion_gap(patch_sysdb):
    rows = _chained_rows(5)
    # Delete the 3rd record → record 4's prev_hash no longer matches record 2.
    del rows[2]
    patch_sysdb(rows)
    res = await verify_chain("t1")
    assert res["ok"] is False
    assert any(b["reason"] == "prev_hash_mismatch" for b in res["breaks"])


async def test_verify_skips_legacy_unchained_rows(patch_sysdb):
    rows = _chained_rows(3)
    legacy = _entry(tenant_id="t1", target_id="legacy")
    legacy["id"] = "legacy"  # no record_hash → must be skipped
    patch_sysdb(rows + [legacy])
    res = await verify_chain("t1")
    assert res["ok"] is True
    assert res["checked"] == 3  # legacy row not counted


async def test_verify_first_record_not_compared_to_predecessor(patch_sysdb):
    # A window that starts mid-chain (first row has a non-empty prev_hash) must
    # not be flagged just because its predecessor is outside the window.
    rows = _chained_rows(5)
    window = rows[2:]  # starts at seq 3 with a real prev_hash
    patch_sysdb(window)
    res = await verify_chain("t1")
    assert res["ok"] is True
    assert res["checked"] == 3


# ── Fail-visible: post-genesis unchained gaps ──────────────

async def test_verify_flags_post_genesis_unchained_gap(patch_sysdb):
    # A record written AFTER the chain genesis but lacking a record_hash is a
    # silent linking failure and MUST force ok=False (not silently skipped).
    rows = _chained_rows(3)  # timestamps 10:01..10:03
    gap = _entry(tenant_id="t1", target_id="gap",
                 timestamp="2026-06-12T10:05:00+00:00")
    gap["id"] = "gap"  # no record_hash, AFTER genesis
    patch_sysdb(rows + [gap])
    res = await verify_chain("t1")
    assert res["ok"] is False
    assert res["unverifiable"] == 1
    assert any(b["reason"] == "unverifiable_unchained_records" for b in res["breaks"])
    assert res["checked"] == 3  # only chained rows are walked


async def test_verify_legacy_before_genesis_is_not_a_gap(patch_sysdb):
    # A record written BEFORE the genesis is honest legacy → skipped, ok stays True.
    rows = _chained_rows(3)  # genesis at 10:01
    legacy = _entry(tenant_id="t1", target_id="legacy",
                    timestamp="2026-06-12T09:00:00+00:00")
    legacy["id"] = "legacy"  # no record_hash, BEFORE genesis
    patch_sysdb(rows + [legacy])
    res = await verify_chain("t1")
    assert res["ok"] is True
    assert res["unverifiable"] == 0
    assert res["legacy_skipped"] == 1


# ── Hot + archive union ────────────────────────────────────

async def test_verify_unions_hot_and_archive(patch_sysdb):
    # Records 1-2 archived, 3-5 still hot: the chain must verify continuously.
    full = _chained_rows(5)
    archive_rows = full[:2]
    hot_rows = full[2:]
    patch_sysdb(hot_rows, archive_rows=archive_rows)
    res = await verify_chain("t1")
    assert res["ok"] is True
    assert res["checked"] == 5
    assert res["last_seq"] == 5


async def test_verify_detects_tamper_in_archive(patch_sysdb):
    full = _chained_rows(5)
    archive_rows = [dict(r) for r in full[:2]]
    archive_rows[1]["after_snapshot"] = {"voided": False, "amount": 1}  # tamper archived row
    patch_sysdb(full[2:], archive_rows=archive_rows)
    res = await verify_chain("t1")
    assert res["ok"] is False
    assert any(b["reason"] == "content_hash_mismatch" and b["seq"] == 2 for b in res["breaks"])
