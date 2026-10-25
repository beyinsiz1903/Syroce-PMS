"""Execute the actual new capacity block without Docker or host mutations.

The unchanged healthwatch topology section uses Bash4 mapfile. Isolating only
the new block lets these arithmetic/parser contracts also run on macOS Bash3.
CI and production still run the full script with their native Bash.
"""
import os
import subprocess
from pathlib import Path

import pytest

SOURCE = (Path(__file__).resolve().parents[2] / "deploy/syroce-healthwatch.sh").read_text()
BLOCK = SOURCE.split('min_free_gib="', 1)[1].split('\nif ((${#failures[@]})); then', 1)[0]
BLOCK = 'min_free_gib="' + BLOCK
HARNESS = r'''
set -euo pipefail
failures=()
docker() { printf '%s\n' "$PMS_TEST_DOCKER_ROOT"; }
df() {
  printf 'Filesystem 1B-blocks Used Available Use%% Mounted\n'
  printf '/dev/example 999999999999 1000 %s 10%% /\n' "$PMS_TEST_FREE_BYTES"
}
'''


def run_capacity(free, threshold="10", root="/"):
    env = {**os.environ, "PMS_TEST_FREE_BYTES": str(free), "PMS_TEST_DOCKER_ROOT": root,
           "HEALTHWATCH_MIN_FREE_GIB": threshold}
    # Bash3 treats an explicitly declared empty array as unbound under-u.
    # Only the harness's result printing disables it; the actual block above
    # still executes with the production errexit/nounset/pipefail settings.
    return subprocess.run(["bash", "-c", HARNESS + BLOCK + '\nset +u\nprintf "%s\\n" "${failures[@]}"\n((${#failures[@]} == 0))'],
                          env=env, text=True, capture_output=True, timeout=5)


@pytest.mark.parametrize("free,threshold,expected", [
    (9 * 1024**3, "10", 1), (10 * 1024**3, "10", 0),
    (11 * 1024**3, "10", 0), (15 * 1024**3, "20", 1),
    (20 * 1024**3, "20", 0), (0, "1", 1),
])
def test_capacity_gate_uses_bytes_and_exact_threshold(free, threshold, expected):
    result = run_capacity(free, threshold)
    assert result.returncode == expected, result.stderr
    if expected:
        assert "disk-free:" in result.stdout
    else:
        assert not result.stdout.strip()


@pytest.mark.parametrize("threshold", ["", "0", "08", "-1", "1.5", "1025", "100000000000000000000", "$(touch /must-not-run)"])
def test_invalid_thresholds_fail_without_shell_evaluation(threshold):
    # Empty environment value intentionally uses the documented default10.
    result = run_capacity(11 * 1024**3, threshold)
    if threshold == "":
        assert result.returncode == 0
    else:
        assert result.returncode == 1
        assert "disk-threshold:invalid" in result.stdout
    assert not result.stderr


@pytest.mark.parametrize("free", ["unknown", "-100", "1.2GB", ""])
def test_unreadable_capacity_fails_visible(free):
    result = run_capacity(free)
    assert result.returncode == 1 and "disk-free:unreadable" in result.stdout


@pytest.mark.parametrize("root", ["", "relative/path", "/nonexistent-healthwatch-test-path"])
def test_unknown_docker_storage_is_not_reported_healthy(root):
    result = run_capacity(20 * 1024**3, root=root)
    assert result.returncode == 1 and "docker-storage:unknown" in result.stdout
