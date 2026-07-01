"""Phase 1 guardrail tests for tools/tenant_restore_drill.py.

No real mongodump/mongorestore — only argparse + classification + risk logic.
Pilot Readiness Checklist hard-blocker #3 regression guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_DRILL_PATH = _REPO / "tools" / "tenant_restore_drill.py"
_CLASSIFY_PATH = _REPO / "backend" / "scripts" / "classify_tenant_scope.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-load classify so drill's `import classify_tenant_scope` finds it
# (drill also inserts its sys.path; either way works).
classify_mod = _load("classify_tenant_scope", _CLASSIFY_PATH)
sys.path.insert(0, str(_CLASSIFY_PATH.parent))
drill = _load("tenant_restore_drill", _DRILL_PATH)


# Fake classification — avoids running the real ripgrep-style scan in unit tests.
FAKE_CLASS = {
    "TENANT_SCOPED": [
        {"name": "bookings", "ref_files": ["a.py"], "ref_count": 1},
        {"name": "folios", "ref_files": ["b.py"], "ref_count": 2},
        {"name": "guests", "ref_files": ["c.py"], "ref_count": 1},
    ],
    "GLOBAL_EXCLUDE": [
        {"name": "credential_vault", "ref_files": ["s.py"], "ref_count": 1},
        {"name": "provider_secrets", "ref_files": ["s.py"], "ref_count": 1},
        {"name": "_dev_secrets", "ref_files": ["s.py"], "ref_count": 1},
    ],
    "UNKNOWN_REVIEW_REQUIRED": [
        {"name": "connector_dlq", "ref_files": ["c.py"], "ref_count": 1},
    ],
    "SYSTEM_INTERNAL": [],
    "_summary": {
        "TENANT_SCOPED": 3,
        "GLOBAL_EXCLUDE": 3,
        "UNKNOWN_REVIEW_REQUIRED": 1,
        "SYSTEM_INTERNAL": 0,
    },
}


# ── build_plan ────────────────────────────────────────────────────────────


def test_build_plan_includes_all_required_fields():
    plan = drill.build_plan(
        backup_archive="/tmp/bk_x",
        tenant_id="T1",
        target_db="staging",
        classification=FAKE_CLASS,
    )
    assert plan["source_backup_archive"] == "/tmp/bk_x"
    assert plan["target_tenant_id"] == "T1"
    assert plan["target_database"] == "staging"
    assert plan["tenant_scoped_collections"] == ["bookings", "folios", "guests"]
    assert "credential_vault" in plan["excluded_global_collections"]
    assert "connector_dlq" in plan["unknown_collections_requiring_review"]
    assert plan["validation_queries"]
    assert "mongorestore" in plan["planned_restore_strategy"]


def test_build_plan_global_secrets_never_in_tenant_scoped():
    """Global secret stores must be excluded — cross-tenant restore = poisoning."""
    plan = drill.build_plan(
        backup_archive="/tmp/bk_x",
        tenant_id="T1",
        target_db="staging",
        classification=FAKE_CLASS,
    )
    forbidden = {
        "credential_vault",
        "provider_secrets",
        "_dev_secrets",
        "secret_access_audit",
    }
    assert not (forbidden & set(plan["tenant_scoped_collections"]))


def test_build_plan_unknown_collections_never_in_tenant_scoped():
    plan = drill.build_plan(
        backup_archive="/tmp/bk_x",
        tenant_id="T1",
        target_db="staging",
        classification=FAKE_CLASS,
    )
    assert "connector_dlq" not in plan["tenant_scoped_collections"]


# ── assess_risk ───────────────────────────────────────────────────────────


def test_assess_risk_blocks_prod_target_without_flag():
    plan = drill.build_plan(
        backup_archive="/tmp/bk_x",
        tenant_id="T1",
        target_db="hotel_pms",
        classification=FAKE_CLASS,
    )
    verdict, findings = drill.assess_risk(
        plan, prod_db_name="hotel_pms", allow_prod_target=False
    )
    assert verdict == "BLOCK"
    assert any("matches production" in f for f in findings)


def test_assess_risk_allows_prod_target_with_flag():
    plan = drill.build_plan(
        backup_archive="/tmp/bk_x",
        tenant_id="T1",
        target_db="hotel_pms",
        classification=FAKE_CLASS,
    )
    verdict, findings = drill.assess_risk(
        plan, prod_db_name="hotel_pms", allow_prod_target=True
    )
    assert verdict == "REVIEW"
    assert any("--allow-prod-target ENABLED" in f for f in findings)


def test_assess_risk_review_when_unknown_collections_present():
    plan = drill.build_plan(
        backup_archive="/tmp/bk_x",
        tenant_id="T1",
        target_db="staging",
        classification=FAKE_CLASS,
    )
    verdict, findings = drill.assess_risk(
        plan, prod_db_name="hotel_pms", allow_prod_target=False
    )
    assert verdict == "REVIEW"
    assert any("UNKNOWN_REVIEW_REQUIRED" in f for f in findings)


def test_assess_risk_block_when_no_tenant_scoped():
    empty_class = {**FAKE_CLASS, "TENANT_SCOPED": []}
    plan = drill.build_plan(
        backup_archive="/tmp/bk_x",
        tenant_id="T1",
        target_db="staging",
        classification=empty_class,
    )
    verdict, findings = drill.assess_risk(
        plan, prod_db_name="hotel_pms", allow_prod_target=False
    )
    assert verdict == "BLOCK"
    assert any("classification likely failed" in f for f in findings)


def test_assess_risk_warns_on_missing_archive():
    plan = drill.build_plan(
        backup_archive="/definitely/does/not/exist/bk_x",
        tenant_id="T1",
        target_db="staging",
        classification={**FAKE_CLASS, "UNKNOWN_REVIEW_REQUIRED": []},
    )
    verdict, findings = drill.assess_risk(
        plan, prod_db_name="hotel_pms", allow_prod_target=False
    )
    assert verdict == "REVIEW"
    assert any("does not exist" in f for f in findings)


def test_assess_risk_ok_when_clean_inputs():
    plan = drill.build_plan(
        backup_archive=str(_REPO),  # an existing path
        tenant_id="T1",
        target_db="staging",
        classification={**FAKE_CLASS, "UNKNOWN_REVIEW_REQUIRED": []},
    )
    verdict, findings = drill.assess_risk(
        plan, prod_db_name="hotel_pms", allow_prod_target=False
    )
    assert verdict == "OK"
    assert findings == []


# ── CLI / argparse guards ─────────────────────────────────────────────────


def test_cli_missing_required_args_exits():
    with pytest.raises(SystemExit):
        drill.main([])


@pytest.fixture
def patched_classify(monkeypatch):
    monkeypatch.setattr(
        drill.classify_tenant_scope, "build_report", lambda root: FAKE_CLASS
    )


def test_cli_dry_run_default(patched_classify, capsys):
    rc = drill.main(
        [
            "--backup-archive",
            "/nonexistent/bk_x",
            "--tenant-id",
            "T1",
            "--target-db",
            "staging",
            "--prod-db-name",
            "hotel_pms",
        ]
    )
    out = capsys.readouterr().out
    assert "mode: dry-run" in out
    assert "REVIEW" in out  # archive missing + unknown collections → REVIEW
    assert rc == 0


def test_cli_blocks_prod_target_via_exit_code(patched_classify, capsys):
    rc = drill.main(
        [
            "--backup-archive",
            "/nonexistent/bk_x",
            "--tenant-id",
            "T1",
            "--target-db",
            "hotel_pms",
            "--prod-db-name",
            "hotel_pms",
        ]
    )
    out = capsys.readouterr().out
    assert "BLOCK" in out
    assert rc == 1


def test_cli_allow_prod_target_passes(patched_classify):
    rc = drill.main(
        [
            "--backup-archive",
            "/nonexistent/bk_x",
            "--tenant-id",
            "T1",
            "--target-db",
            "hotel_pms",
            "--prod-db-name",
            "hotel_pms",
            "--allow-prod-target",
        ]
    )
    assert rc == 0


def test_execute_does_not_run_without_flag(patched_classify, monkeypatch):
    """No --execute → run_execute must not be called."""
    called = {"hit": False}
    monkeypatch.setattr(
        drill,
        "run_execute",
        lambda *a, **kw: called.__setitem__("hit", True) or 0,
    )
    rc = drill.main(
        [
            "--backup-archive",
            "/nonexistent/bk_x",
            "--tenant-id",
            "T1",
            "--target-db",
            "staging",
            "--prod-db-name",
            "hotel_pms",
        ]
    )
    assert rc == 0
    assert called["hit"] is False


def test_execute_blocked_by_block_verdict(patched_classify, monkeypatch):
    """Even with --execute, BLOCK verdict prevents run_execute invocation."""
    called = {"hit": False}
    monkeypatch.setattr(
        drill,
        "run_execute",
        lambda *a, **kw: called.__setitem__("hit", True) or 0,
    )
    rc = drill.main(
        [
            "--backup-archive",
            "/nonexistent/bk_x",
            "--tenant-id",
            "T1",
            "--target-db",
            "hotel_pms",
            "--prod-db-name",
            "hotel_pms",
            "--execute",
        ]
    )
    assert rc == 1
    assert called["hit"] is False


def test_json_format_output(patched_classify, capsys):
    rc = drill.main(
        [
            "--backup-archive",
            "/nonexistent/bk_x",
            "--tenant-id",
            "T1",
            "--target-db",
            "staging",
            "--prod-db-name",
            "hotel_pms",
            "--format",
            "json",
        ]
    )
    out = capsys.readouterr().out
    import json as _json

    parsed = _json.loads(out)
    assert parsed["mode"] == "dry-run"
    assert parsed["target_tenant_id"] == "T1"
    assert "bookings" in parsed["tenant_scoped_collections"]
    assert rc == 0


# ── classify_tenant_scope hard-coded list integrity ───────────────────────


def test_classify_global_excludes_have_secret_stores():
    assert {"_dev_secrets", "credential_vault", "provider_secrets",
            "secret_access_audit"} <= classify_mod.GLOBAL_EXCLUDE


def test_classify_unknown_review_has_channel_state():
    assert {"connector_dlq", "connector_outbox", "cm_webhook_events",
            "raw_channel_events"} <= classify_mod.UNKNOWN_REVIEW_FORCED


def test_classify_system_prefix_classified_as_internal():
    assert classify_mod.classify("system.indexes", []) == "SYSTEM_INTERNAL"
    assert classify_mod.classify("fs.files", []) == "SYSTEM_INTERNAL"


def test_classify_global_exclude_overrides_tenant_id_heuristic():
    # Even if a secret store accidentally co-occurred with tenant_id in code,
    # GLOBAL_EXCLUDE wins.
    assert classify_mod.classify("credential_vault", []) == "GLOBAL_EXCLUDE"
