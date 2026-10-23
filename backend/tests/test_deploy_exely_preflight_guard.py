"""Regression guard for the production webhook security preflight."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/deploy.yml"


def test_droplet_deploy_checks_candidate_exely_trust_boundary_before_service_replacement():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    preflight = "python scripts/verify_exely_whitelist.py --env production"
    pull = "bash deploy/pull-ci-images.sh"
    compose = "docker compose -f docker-compose.prod.yml -f deploy/docker-compose.registry.yml"
    rollout = "up -d --no-build --pull never"
    assert preflight in workflow
    assert workflow.index(pull) < workflow.index(preflight) < workflow.index(rollout)
    assert "docker compose -f docker-compose.prod.yml build" not in workflow
    assert "docker compose -f docker-compose.prod.yml down" not in workflow
    # Run under compose so backend/.env is available, but prevent startup or
    # dependency attachment while this is only a pure configuration check.
    # Use the registry overlay: the preflight must validate the candidate
    # image, not the old local image left behind by an earlier deployment.
    assert f"{compose} \\\n              run --rm --no-deps --pull never backend \\\n              {preflight}" in workflow
    assert "set -euo pipefail" in workflow  # Preflight failure must abort rollout.


@pytest.mark.parametrize("preflight_exit", [1, 37])
def test_rejected_candidate_preflight_never_reaches_rollout(tmp_path, preflight_exit):
    workflow = yaml.safe_load(WORKFLOW.read_text())
    deploy = next(
        step for step in workflow["jobs"]["deploy"]["steps"]
        if step.get("name") == "Deploy to Server"
    )
    script = deploy["with"]["script"]
    candidate_start = script.index(
        "docker compose -f docker-compose.prod.yml -f deploy/docker-compose.registry.yml"
    )
    # Execute the real candidate-preflight/rollout tail with a fake Docker CLI.
    # Exclude SSH/checkout/install setup so this never touches a host or stack.
    script = script.splitlines()[0] + "\n" + script[candidate_start:]
    docker = tmp_path / "docker"
    docker.write_text("""#!/bin/sh
printf '%s\\n' "$*" >> "$CALL_LOG"
case "$*" in
  *"python scripts/verify_exely_whitelist.py --env production") exit "$PREFLIGHT_EXIT" ;;
esac
exit 0
""")
    docker.chmod(0o755)
    calls_path = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-c", script],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CALL_LOG": str(calls_path),
            "PREFLIGHT_EXIT": str(preflight_exit),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == preflight_exit
    assert calls_path.read_text().splitlines() == [
        "compose -f docker-compose.prod.yml -f deploy/docker-compose.registry.yml "
        "run --rm --no-deps --pull never backend "
        "python scripts/verify_exely_whitelist.py --env production"
    ]
