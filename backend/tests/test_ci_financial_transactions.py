"""Financial acceptance must exercise transactions, never a CI-only fallback."""
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("job", ["backend-full-offline", "battle-e2e"])
def test_financial_acceptance_jobs_use_a_ready_replica_set(job):
    workflow = yaml.safe_load((Path(__file__).resolve().parents[2] / ".github/workflows/ci-cd.yml").read_text())
    config = workflow["jobs"][job]
    assert "replicaSet=rs0" in config["env"]["MONGO_URL"]
    assert "mongodb" not in config.get("services", {})  # no standalone service
    steps = config["steps"]
    start = next(i for i, step in enumerate(steps) if step.get("name") == "Start transaction-capable MongoDB replica set")
    seed = next(i for i, step in enumerate(steps) if step.get("name", "").startswith("Seed"))
    script = steps[start]["run"]
    assert start < seed
    for required in ("mongo:7.0 --replSet rs0", "rs.initiate", "rs.status().myState === 1", "exit 1", "--env HOME=/tmp"):
        assert required in script
    assert not config["env"].get("ALLOW_STANDALONE_BOOKING_FALLBACK")


def test_production_control_matrix_keeps_the_source_reversal_test_and_zero_skip_gate():
    workflow = yaml.safe_load((Path(__file__).resolve().parents[2] / ".github/workflows/ci-cd.yml").read_text())
    steps = workflow["jobs"]["battle-e2e"]["steps"]
    script = next(step["run"] for step in steps if step.get("name") == "Run production control matrix (zero-skip hard gate)")
    assert "tests/test_operational_gl_source_valuation.py" in script
    assert "--max-skips 0" in script
    assert "--min-tests 390" in script
