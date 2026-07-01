"""Unit tests for backend/scripts/audit_shard_readiness.py (Task #366).

The audit is read-only; these tests exercise the pure shard-key coverage
logic and the static query scanner WITHOUT a live MongoDB cluster.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_shard_readiness.py"
_spec = importlib.util.spec_from_file_location("audit_shard_readiness", _SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["audit_shard_readiness"] = mod  # required for @dataclass lookup
_spec.loader.exec_module(mod)


# ── Index coverage: READY / READY_TENANT_ONLY / MISSING / ABSENT ─────────


def test_bookings_ready_when_shardkey_prefix_index_exists():
    index_maps = {
        "bookings": {
            # (tenant_id, check_in, check_out) → prefix (tenant_id, check_in)
            "idx_bookings_tenant_checkin_checkout": [
                ("tenant_id", 1), ("check_in", 1), ("check_out", 1)
            ],
        }
    }
    r = mod.evaluate_collection("bookings", [("tenant_id", 1), ("check_in", -1)], index_maps)
    assert r.status == "READY"
    assert r.tenant_leading
    assert "idx_bookings_tenant_checkin_checkout" in r.shardkey_by_field
    # Doc recommends check_in: -1, the index is check_in: +1 → field match but
    # direction differs → must surface the "create exact-direction index" note.
    assert not r.shardkey_exact
    assert any("yön" in n for n in r.notes)


def test_exact_direction_match_has_no_warning_note():
    index_maps = {
        "audit_logs": {
            "idx_audit_log_timestamp": [("tenant_id", 1), ("timestamp", -1)],
        }
    }
    r = mod.evaluate_collection("audit_logs", [("tenant_id", 1), ("timestamp", -1)], index_maps)
    assert r.status == "READY"
    assert r.shardkey_exact == ["idx_audit_log_timestamp"]


def test_folios_tenant_only_when_composite_unsupported():
    # Only (tenant_id, status, created_at) exists — leads with tenant_id but
    # the recommended shard key {tenant_id, created_at} has no prefix support.
    index_maps = {
        "folios": {
            "idx_folios_tenant_status_created": [
                ("tenant_id", 1), ("status", 1), ("created_at", -1)
            ],
            "idx_folio_booking_status": [
                ("tenant_id", 1), ("booking_id", 1), ("status", 1)
            ],
        }
    }
    r = mod.evaluate_collection("folios", [("tenant_id", 1), ("created_at", -1)], index_maps)
    assert r.status == "READY_TENANT_ONLY"
    assert r.tenant_leading
    assert r.shardkey_by_field == []


def test_missing_when_no_tenant_leading_index():
    index_maps = {
        "bookings": {
            "idx_booking_guest_global": [("guest_id", 1)],  # cross-tenant only
            "guest_name_text": [("guest_name", "text")],
        }
    }
    r = mod.evaluate_collection("bookings", [("tenant_id", 1), ("check_in", -1)], index_maps)
    assert r.status == "MISSING"
    assert r.tenant_leading == []


def test_absent_collection_reports_absent_not_missing():
    r = mod.evaluate_collection("folios", [("tenant_id", 1), ("created_at", -1)], {"folios": None})
    assert r.status == "ABSENT"
    assert r.present is False


def test_tasks_alias_resolves_to_real_collections():
    index_maps = {
        "housekeeping_tasks": {
            "idx_hk_status_room": [("tenant_id", 1), ("status", 1), ("room_id", 1)],
        },
        "task_queue": {
            "idx_task_queue_poll": [("tenant_id", 1), ("status", 1), ("scheduled_for", 1)],
        },
    }
    r = mod.evaluate_collection("tasks", [("tenant_id", 1)], index_maps)
    assert r.resolved == ["housekeeping_tasks", "task_queue"]
    assert r.status == "READY"
    # Both real collections contribute a tenant_id-leading index (tagged by name).
    assert any("housekeeping_tasks." in t for t in r.tenant_leading)
    assert any("task_queue." in t for t in r.tenant_leading)
    assert any("strateji dokümanı" in n for n in r.notes)


# ── Static query scan ────────────────────────────────────────────────────


def _scan_snippet(tmp_path: Path, code: str):
    (tmp_path / "mod.py").write_text(textwrap.dedent(code), encoding="utf-8")
    return mod.scan_source_tree(tmp_path)


def test_raw_unscoped_read_is_flagged(tmp_path):
    findings = _scan_snippet(tmp_path, """
        async def f():
            return await _raw_db.bookings.find({"status": "confirmed"}).to_list(10)
    """)
    assert len(findings) == 1
    q = findings[0]
    assert q.collection == "bookings" and q.op == "find"
    assert q.scoped is False and q.by_design is False


def test_raw_scoped_read_is_not_flagged_as_risk(tmp_path):
    findings = _scan_snippet(tmp_path, """
        async def f(tid):
            return await _raw_db.folios.find_one({"tenant_id": tid, "id": "x"})
    """)
    assert len(findings) == 1
    assert findings[0].scoped is True


def test_guest_id_global_read_is_by_design(tmp_path):
    findings = _scan_snippet(tmp_path, """
        async def f(ids):
            return await _raw_db.bookings.find({"guest_id": {"$in": ids}}).to_list(50)
    """)
    assert len(findings) == 1
    assert findings[0].by_design is True
    assert findings[0].scoped is False


def test_proxy_db_reads_are_ignored(tmp_path):
    # Reads through the tenant-aware proxy `db` auto-inject tenant_id and must
    # NOT be flagged (only the _raw_db escape hatch is a scatter-gather risk).
    findings = _scan_snippet(tmp_path, """
        async def f():
            return await db.bookings.find({"status": "x"}).to_list(10)
    """)
    assert findings == []


def test_subscript_collection_access_is_detected(tmp_path):
    findings = _scan_snippet(tmp_path, """
        async def f():
            return await _raw_db["guests"].count_documents({})
    """)
    assert len(findings) == 1
    assert findings[0].collection == "guests" and findings[0].op == "count_documents"


def test_non_shardable_collection_is_ignored(tmp_path):
    findings = _scan_snippet(tmp_path, """
        async def f():
            return await _raw_db.tenants.find({}).to_list(10)
    """)
    assert findings == []


def test_skip_dirs_are_not_scanned(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text(
        'async def f():\n    await _raw_db.bookings.find({})\n', encoding="utf-8"
    )
    assert mod.scan_source_tree(tmp_path) == []


# ── build_findings verdict wiring ────────────────────────────────────────


def test_build_findings_missing_index_is_blocker():
    res = [mod.evaluate_collection("bookings", [("tenant_id", 1), ("check_in", -1)],
                                   {"bookings": {"g": [("guest_id", 1)]}})]
    f = mod.build_findings(res, [])
    assert f.verdict == "FAIL"
    assert f.blockers


def test_build_findings_query_only_skips_index_audit():
    f = mod.build_findings(None, [])
    assert f.verdict == "REVIEW"
    assert any("ATLANDI" in w for w in f.warnings)


def test_build_findings_clean_is_pass():
    res = [mod.evaluate_collection("audit_logs", [("tenant_id", 1), ("timestamp", -1)],
                                   {"audit_logs": {"i": [("tenant_id", 1), ("timestamp", -1)]}})]
    f = mod.build_findings(res, [])
    assert f.verdict == "PASS"
    assert not f.blockers and not f.warnings
