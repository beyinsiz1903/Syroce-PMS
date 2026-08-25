from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check_critical_coverage.py"
SPEC = util.spec_from_file_location("check_critical_coverage", SCRIPT)
assert SPEC and SPEC.loader
POLICY_MODULE = util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY_MODULE)


def _coverage(percent=85.0):
    return {
        "files": {
            "critical.py": {"summary": {"percent_covered": percent}},
        }
    }


def _policy(minimum=80.0):
    return {
        "critical_files": [
            {"path": "critical.py", "minimum_percent": minimum},
        ]
    }


def test_policy_accepts_file_at_or_above_floor():
    messages, problems = POLICY_MODULE.evaluate_coverage(_coverage(), _policy())

    assert problems == []
    assert messages == ["PASS critical.py: 85.00% (minimum 80.00%)"]


def test_policy_rejects_coverage_regression():
    messages, problems = POLICY_MODULE.evaluate_coverage(_coverage(79.9), _policy())

    assert messages == ["FAIL critical.py: 79.90% (minimum 80.00%)"]
    assert problems == ["critical.py: 79.90% is below 80.00%"]


def test_policy_fails_closed_when_critical_file_is_missing():
    messages, problems = POLICY_MODULE.evaluate_coverage({"files": {}}, _policy())

    assert messages == []
    assert problems == ["critical.py: missing from coverage report"]


def test_policy_rejects_invalid_report_and_empty_policy():
    assert POLICY_MODULE.evaluate_coverage({}, _policy())[1] == [
        "coverage report has no 'files' object"
    ]
    assert POLICY_MODULE.evaluate_coverage(_coverage(), {})[1] == [
        "policy has no non-empty 'critical_files' list"
    ]
