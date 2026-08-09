import json
import subprocess
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parents[2] / ".github/workflows/exely-production-cutover.yml"
SPEC_FILTER_PATH = Path(__file__).parents[2] / ".github/scripts/exely-cutover-spec.jq"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(_workflow_text())


def test_cutover_is_manual_and_production_protected() -> None:
    workflow = _workflow()

    assert set(workflow[True]) == {"workflow_dispatch"}
    assert workflow["jobs"]["cutover"]["environment"] == "production"
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_cutover_requires_exact_head_confirmation_and_first_attempt() -> None:
    text = _workflow_text()

    assert "BLOCKED_PRODUCTION_CONFIRMATION_REQUIRED" in text
    assert "BLOCKED_EXACT_HEAD_MISMATCH" in text
    assert "BLOCKED_MUTATION_RERUN" in text
    assert 'test "${{ github.ref_name }}" = "main"' in text


def test_read_only_stage_keeps_reservation_and_ari_stopped() -> None:
    text = _workflow_text()
    spec_filter = SPEC_FILTER_PATH.read_text(encoding="utf-8")

    assert 'enable_read_only)\n              MASTER_GATE="true"' in text
    assert 'set_env("DISABLE_EXELY_RESERVATION_SYNC"; "true")' in spec_filter
    assert 'set_env("DISABLE_EXELY_ARI_WRITE"; "true")' in spec_filter
    assert 'set_env("ENABLE_EXELY_PRODUCTION"; $master)' in spec_filter


def test_prepare_and_close_stages_disable_master_gate() -> None:
    text = _workflow_text()

    assert 'prepare_disabled|close_all)\n              MASTER_GATE="false"' in text


def test_cutover_has_no_exely_provider_call() -> None:
    text = _workflow_text().lower()

    assert "pmsconnect.test.hopenapi.com" not in text
    assert "pmsconnect.prod.hopenapi.com" not in text
    assert "ota_resretrieve" not in text
    assert "ota_notifreport" not in text
    assert "ota_hotelavailnotif" not in text


def test_diagnostic_mode_is_read_only_and_redacted() -> None:
    text = _workflow_text()

    assert "diagnose_last_failed" in text
    assert "if: inputs.operation != 'diagnose_last_failed'" in text
    assert "if: inputs.operation == 'diagnose_last_failed'" in text
    assert "safe_startup_log_diagnosis.py" in text
    assert "BLOCKED_UNCLASSIFIED_STARTUP_FAILURE" in text
    assert "production_mutation_count: 0" in text


def test_cutover_verifies_live_sha_and_all_runtime_gates() -> None:
    text = _workflow_text()

    assert "BLOCKED_LIVE_SHA_MISMATCH" in text
    assert "BLOCKED_COMPONENT_REPOSITORY" in text
    assert "BLOCKED_LIVE_REPOSITORY_MISMATCH" in text
    assert "BLOCKED_MASTER_GATE_MISMATCH" in text
    assert "BLOCKED_RESERVATION_STOP_MISSING" in text
    assert "BLOCKED_ARI_STOP_MISSING" in text
    assert "provider_read_count: 0" in text
    assert "provider_write_count: 0" in text


def test_cutover_smoke_uses_production_environment_url() -> None:
    text = _workflow_text()

    assert "APP_BASE_URL: ${{ secrets.VITE_BACKEND_URL }}" in text
    assert "STRESS_E2E_BASE_URL" not in text
    assert 'BASE_URL="${BASE_URL%/api}"' in text


def test_cutover_never_renders_deployment_spec() -> None:
    text = _workflow_text()

    assert "cat /tmp/exely" not in text
    assert 'apps update "$DO_APP_ID" --spec /tmp/exely-new-spec.json --wait >/dev/null' in text
    assert "Remove temporary deployment files" in text


def test_spec_filter_sets_exact_sha_and_fail_closed_gates() -> None:
    source = {
        "services": [
            {"name": "backend", "image": {"tag": "old", "digest": "sha256:old"}},
            {"name": "frontend", "image": {"tag": "old", "digest": "sha256:old"}},
        ],
        "workers": [
            {"name": "worker", "image": {"tag": "old"}},
            {"name": "beat", "image": {"tag": "old"}},
        ],
    }
    result = subprocess.run(
        [
            "jq",
            "--arg",
            "sha",
            "exact-head",
            "--arg",
            "master",
            "true",
            "-f",
            str(SPEC_FILTER_PATH),
        ],
        input=json.dumps(source),
        capture_output=True,
        check=True,
        text=True,
    )
    transformed = json.loads(result.stdout)

    components = {item["name"]: item for item in transformed["services"] + transformed["workers"]}
    for name in ("backend", "frontend", "worker", "beat"):
        assert components[name]["image"]["tag"] == "exact-head"
        assert "digest" not in components[name]["image"]

    for name in ("backend", "worker", "beat"):
        envs = {item["key"]: item["value"] for item in components[name]["envs"]}
        assert envs == {
            "DISABLE_EXELY_ARI_WRITE": "true",
            "DISABLE_EXELY_RESERVATION_SYNC": "true",
            "ENABLE_EXELY_PRODUCTION": "true",
        }
    assert "envs" not in components["frontend"]
