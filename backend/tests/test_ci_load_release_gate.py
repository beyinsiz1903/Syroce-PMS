"""CI load failures must never be hidden by tee or a missing demo login."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _steps():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci-cd.yml").read_text())
    return workflow["jobs"]["load-test"]["steps"]


def test_load_seed_provides_the_login_used_by_the_load_fixtures():
    seed = next(step["run"] for step in _steps() if step.get("name") == "Seed load-test database (hard gate)")
    assert "DEMO_PASSWORD=demo123 python create_demo_users.py" in seed
    assert "||" not in seed


def test_load_test_pipeline_propagates_pytest_failure():
    step = next(step for step in _steps() if step.get("name") == "Run CI load tests (hard gate)")
    assert step["shell"] == "bash"
    assert "set -euo pipefail" in step["run"]
    # Exercise the shell mechanism without starting a server or test process.
    failure = subprocess.run(["bash", "-c", "set -euo pipefail; false | tee /dev/null"], check=False)
    assert failure.returncode != 0
    policy = next(step["run"] for step in _steps() if step.get("name") == "Enforce load-test result policy")
    assert "check_junit_policy.py backend/load-test-results.xml --min-tests 11 --max-skips 0" in policy


def test_load_backend_readiness_fails_closed():
    start = next(step["run"] for step in _steps() if step.get("name") == "Start backend server")
    assert "curl --fail --silent --show-error http://localhost:8001/health/ready" in start
    assert 'if [ "$ready" -ne 1 ]' in start and "exit 1" in start


@pytest.mark.parametrize("backend, success", [("memory", True), ("redis", False)])
def test_raw_load_fixture_rejects_nonshared_or_failed_cache_invalidation(monkeypatch, backend, success):
    import cache_manager
    from load_tests.conftest import _invalidate_seeded_inventory

    monkeypatch.setattr(cache_manager, "cache", SimpleNamespace(backend=backend, safe_invalidate=lambda *_: success))
    with pytest.raises(RuntimeError, match="shared Redis"):
        _invalidate_seeded_inventory("synthetic-tenant")


def test_raw_load_fixture_invalidates_only_the_seeded_tenant_inventory(monkeypatch):
    import cache_manager
    from load_tests.conftest import _invalidate_seeded_inventory

    calls = []
    monkeypatch.setattr(cache_manager, "cache", SimpleNamespace(
        backend="redis", safe_invalidate=lambda *args: calls.append(args) or True,
    ))
    _invalidate_seeded_inventory("synthetic-tenant")
    assert calls == [("synthetic-tenant", "rooms_availability")]
