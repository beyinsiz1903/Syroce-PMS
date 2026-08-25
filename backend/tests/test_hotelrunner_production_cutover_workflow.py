import json
import subprocess
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parents[2] / ".github/workflows/hotelrunner-production-cutover.yml"
SPEC_FILTER_PATH = Path(__file__).parents[2] / ".github/scripts/hotelrunner-cutover-spec.jq"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(_workflow_text())


def test_cutover_is_manual_and_production_protected() -> None:
    workflow = _workflow()

    assert set(workflow[True]) == {"workflow_dispatch"}
    assert workflow["jobs"]["cutover"]["environment"] == "production"
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_cutover_requires_confirmation_exact_head_and_first_attempt() -> None:
    text = _workflow_text()

    assert "BLOCKED_PRODUCTION_CONFIRMATION_REQUIRED" in text
    assert "BLOCKED_EXACT_HEAD_MISMATCH" in text
    assert "BLOCKED_MUTATION_RERUN" in text
    assert 'test "${{ github.ref_name }}" = "main"' in text


def test_read_only_stage_keeps_reservation_and_ari_stopped() -> None:
    text = _workflow_text()
    spec_filter = SPEC_FILTER_PATH.read_text(encoding="utf-8")

    assert 'enable_read_only)\n              MASTER_GATE="true"' in text
    assert 'set_env("ENABLE_HOTELRUNNER_PRODUCTION"; $master)' in spec_filter
    assert 'set_env("DISABLE_HOTELRUNNER_RESERVATION_SYNC"; $reservation_stop)' in spec_filter
    assert 'set_env("DISABLE_HOTELRUNNER_ARI_WRITE"; $ari_stop)' in spec_filter
    assert 'set_env("NILVERA_ENABLED"; "false")' in spec_filter


def test_prepare_and_close_disable_master_gate() -> None:
    assert 'prepare_disabled|close_all)\n              MASTER_GATE="false"' in _workflow_text()


def test_live_stages_require_prerequisite_attestation_and_exact_confirmation() -> None:
    text = _workflow_text()

    assert "BLOCKED_PROVIDER_PREREQUISITES_NOT_ATTESTED" in text
    assert "BLOCKED_PROVIDER_ACTIVATION_CONFIRMATION" in text
    assert '"ENABLE_HOTELRUNNER_RESERVATION_SYNC"' in text
    assert '"ENABLE_HOTELRUNNER_ARI_WRITE"' in text
    assert '"ENABLE_HOTELRUNNER_LIVE"' in text


def test_live_stage_matrix_keeps_paths_independent() -> None:
    text = _workflow_text()

    assert 'enable_reservation_sync)\n              MASTER_GATE="true"\n              RESERVATION_STOP="false"\n              ARI_STOP="true"' in text
    assert 'enable_ari_write)\n              MASTER_GATE="true"\n              RESERVATION_STOP="true"\n              ARI_STOP="false"' in text
    assert 'enable_live)\n              MASTER_GATE="true"\n              RESERVATION_STOP="false"\n              ARI_STOP="false"' in text


def test_cutover_uses_official_callback_auth_without_requiring_hmac_secret() -> None:
    text = _workflow_text()

    assert "BLOCKED_HOTELRUNNER_WEBHOOK_SECRET_MISSING_OR_NOT_SECRET" not in text
    assert "official_callback_auth: token_plus_hr_id" in text


def test_reservation_stages_require_exact_head_readonly_reconciliation_evidence() -> None:
    workflow = _workflow()
    text = _workflow_text()

    inputs = workflow[True]["workflow_dispatch"]["inputs"]
    assert "reservation_reconciliation_run_id" in inputs
    assert workflow["permissions"]["actions"] == "read"
    assert "BLOCKED_RESERVATION_RECONCILIATION_RUN_REQUIRED" in text
    assert "BLOCKED_RESERVATION_RECONCILIATION_HEAD_MISMATCH" in text
    assert "BLOCKED_RESERVATION_RECONCILIATION_RUN_NOT_GREEN" in text
    assert "test_hotelrunner_pilot_reservation_reconciliation" in text
    assert '"provider_write_count": "0"' in text
    assert '"undelivered_match_count_class": "ZERO"' in text
    assert '"history_match_count_class": "ONE"' in text


def test_cutover_contains_no_hotelrunner_provider_call() -> None:
    text = _workflow_text().lower()

    assert "app.hotelrunner.com" not in text
    assert "sandbox.hotelrunner.com" not in text
    assert "/reservations" not in text
    assert "/rooms" not in text
    assert "/transactions" not in text


def test_cutover_verifies_exact_sha_repository_and_all_stops() -> None:
    text = _workflow_text()

    assert "BLOCKED_LIVE_SHA_MISMATCH" in text
    assert "BLOCKED_COMPONENT_REPOSITORY" in text
    assert "BLOCKED_LIVE_REPOSITORY_MISMATCH" in text
    assert "BLOCKED_MASTER_GATE_MISMATCH" in text
    assert "BLOCKED_RESERVATION_GATE_MISMATCH" in text
    assert "BLOCKED_ARI_GATE_MISMATCH" in text
    assert "BLOCKED_NILVERA_STOP_MISSING" in text
    assert "provider_read_count: 0" in text
    assert "provider_write_count: 0" in text


def test_cutover_smoke_uses_production_environment_url() -> None:
    text = _workflow_text()

    assert "APP_BASE_URL: ${{ secrets.VITE_BACKEND_URL }}" in text
    assert 'BASE_URL="${BASE_URL%/api}"' in text
    assert '"${BASE_URL}/health/live"' in text


def test_cutover_never_prints_deployment_spec() -> None:
    text = _workflow_text()

    assert "cat /tmp/hotelrunner" not in text
    assert 'apps update "$DO_APP_ID" --spec /tmp/hotelrunner-new-spec.json --wait >/dev/null' in text
    assert "Remove temporary deployment files" in text


def test_spec_filter_sets_exact_sha_preserves_other_gates_and_stops_hotelrunner() -> None:
    protected_envs = [
        {"key": "ENABLE_EXELY_PRODUCTION", "value": "true"},
        {"key": "DISABLE_EXELY_RESERVATION_SYNC", "value": "true"},
        {"key": "DISABLE_EXELY_ARI_WRITE", "value": "true"},
        {"key": "UNRELATED_RUNTIME_SETTING", "value": "preserved"},
    ]
    source = {
        "services": [
            {
                "name": "backend",
                "image": {"tag": "old", "digest": "sha256:old"},
                "envs": protected_envs,
            },
            {"name": "frontend", "image": {"tag": "old", "digest": "sha256:old"}},
        ],
        "workers": [
            {"name": "worker", "image": {"tag": "old"}, "envs": protected_envs},
            {"name": "beat", "image": {"tag": "old"}, "envs": protected_envs},
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
            "--arg",
            "reservation_stop",
            "true",
            "--arg",
            "ari_stop",
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
        assert envs["ENABLE_HOTELRUNNER_PRODUCTION"] == "true"
        assert envs["DISABLE_HOTELRUNNER_RESERVATION_SYNC"] == "true"
        assert envs["DISABLE_HOTELRUNNER_ARI_WRITE"] == "true"
        assert envs["NILVERA_ENABLED"] == "false"
        assert envs["ENABLE_EXELY_PRODUCTION"] == "true"
        assert envs["DISABLE_EXELY_RESERVATION_SYNC"] == "true"
        assert envs["DISABLE_EXELY_ARI_WRITE"] == "true"
        assert envs["UNRELATED_RUNTIME_SETTING"] == "preserved"

    assert "envs" not in components["frontend"]


def test_spec_filter_can_open_only_reservation_sync() -> None:
    source = {
        "services": [{"name": "backend", "image": {"tag": "old"}}],
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
            "--arg",
            "reservation_stop",
            "false",
            "--arg",
            "ari_stop",
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
    for component in transformed["services"] + transformed["workers"]:
        envs = {item["key"]: item["value"] for item in component["envs"]}
        assert envs["ENABLE_HOTELRUNNER_PRODUCTION"] == "true"
        assert envs["DISABLE_HOTELRUNNER_RESERVATION_SYNC"] == "false"
        assert envs["DISABLE_HOTELRUNNER_ARI_WRITE"] == "true"
