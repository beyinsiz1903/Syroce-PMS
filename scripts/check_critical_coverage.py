#!/usr/bin/env python3
"""Enforce per-file coverage floors for business-critical backend paths."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def evaluate_coverage(
    coverage: dict[str, Any], policy: dict[str, Any]
) -> tuple[list[str], list[str]]:
    files = coverage.get("files")
    targets = policy.get("critical_files")
    if not isinstance(files, dict):
        return [], ["coverage report has no 'files' object"]
    if not isinstance(targets, list) or not targets:
        return [], ["policy has no non-empty 'critical_files' list"]

    messages: list[str] = []
    problems: list[str] = []
    for target in targets:
        if not isinstance(target, dict):
            problems.append("critical_files entries must be objects")
            continue
        path = target.get("path")
        minimum = target.get("minimum_percent")
        if not isinstance(path, str) or not path:
            problems.append("critical file entry has an invalid path")
            continue
        if not isinstance(minimum, (int, float)) or isinstance(minimum, bool):
            problems.append(f"{path}: minimum_percent must be numeric")
            continue
        if minimum < 0 or minimum > 100:
            problems.append(f"{path}: minimum_percent must be between 0 and 100")
            continue

        report = files.get(path)
        if not isinstance(report, dict):
            problems.append(f"{path}: missing from coverage report")
            continue
        summary = report.get("summary")
        actual = summary.get("percent_covered") if isinstance(summary, dict) else None
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            problems.append(f"{path}: report has no numeric percent_covered")
            continue

        status = "PASS" if actual + 1e-9 >= minimum else "FAIL"
        messages.append(f"{status} {path}: {actual:.2f}% (minimum {minimum:.2f}%)")
        if status == "FAIL":
            problems.append(f"{path}: {actual:.2f}% is below {minimum:.2f}%")

    return messages, problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage", type=Path, help="coverage.py JSON report")
    parser.add_argument("policy", type=Path, help="critical coverage policy JSON")
    args = parser.parse_args()

    try:
        coverage = load_json(args.coverage)
        policy = load_json(args.policy)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    messages, problems = evaluate_coverage(coverage, policy)
    print("Critical backend coverage policy:")
    for message in messages:
        print(f"- {message}")
    if problems:
        print("ERROR:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
