"""Execute the pull-only helper with a fake Docker CLI, never a live server."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/pull-ci-images.sh"
TEST_TOKEN = "synthetic-registry-token-not-a-credential"


@pytest.fixture
def registry_cli(tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("""#!/bin/sh
set -eu
test "$1" = --config
config="$2"
shift 2
printf '%s\\n' "$*" >> "$CALL_LOG"
if [ "$1" = login ]; then
    printf '%s' "$config" > "$CONFIG_PATH_LOG"
    IFS= read -r token || true
    test "$token" = "$REGISTRY_TOKEN"
    printf '{"auths":{"ghcr.io":{"auth":"synthetic"}}}' > "$config/config.json"
    if [ "${FAIL_AT:-}" = login ]; then exit 17; fi
    echo 'Login Succeeded'
else
    test "$DEPLOY_SHA" = 1111111111111111111111111111111111111111
    test "$DEPLOY_IMAGE_PREFIX" = ghcr.io/test-owner/syroce
    case "$*" in
        *"pull ${FAIL_AT:-no-failure}") exit 17 ;;
    esac
fi
""")
    docker.chmod(0o755)
    return {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "DEPLOY_SHA": "1" * 40,
        "DEPLOY_IMAGE_PREFIX": "ghcr.io/test-owner/syroce",
        "REGISTRY_USER": "test-user",
        "REGISTRY_TOKEN": TEST_TOKEN,
        "CALL_LOG": str(tmp_path / "calls"),
        "CONFIG_PATH_LOG": str(tmp_path / "config-path"),
        "FAIL_AT": "",
    }


def run_helper(env):
    result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert TEST_TOKEN not in result.stdout + result.stderr
    config_path_log = Path(env["CONFIG_PATH_LOG"])
    if config_path_log.exists():
        assert not Path(config_path_log.read_text()).exists(), "temporary auth must be removed"
    return result


def test_pulls_only_three_exact_revision_images_and_removes_temporary_auth(registry_cli):
    assert run_helper(registry_cli).returncode == 0
    calls = Path(registry_cli["CALL_LOG"]).read_text().splitlines()
    assert calls[0] == "login ghcr.io --username test-user --password-stdin"
    prefix = "compose -f docker-compose.prod.yml -f deploy/docker-compose.registry.yml pull "
    assert calls[1:] == [prefix + name for name in ("backend", "frontend", "worker")]


@pytest.mark.parametrize("failure", ["login", "backend", "frontend", "worker"])
def test_auth_or_pull_failure_stops_before_further_images_and_cleans_auth(registry_cli, failure):
    registry_cli["FAIL_AT"] = failure
    assert run_helper(registry_cli).returncode == 17
    calls = Path(registry_cli["CALL_LOG"]).read_text().splitlines()
    assert calls[-1].endswith("--password-stdin" if failure == "login" else "pull " + failure)
    assert not any("build" in call or " up " in call for call in calls)


@pytest.mark.parametrize("field,value", [
    ("DEPLOY_SHA", "main"),
    ("DEPLOY_SHA", "latest"),
    ("DEPLOY_SHA", "1" * 39),
    ("DEPLOY_IMAGE_PREFIX", "external.example/test/syroce"),
    ("DEPLOY_IMAGE_PREFIX", "ghcr.io/test/some-other-app"),
    ("REGISTRY_TOKEN", ""),
])
def test_invalid_revision_registry_or_missing_auth_never_calls_docker(registry_cli, field, value):
    registry_cli[field] = value
    assert run_helper(registry_cli).returncode != 0
    assert not Path(registry_cli["CALL_LOG"]).exists()
