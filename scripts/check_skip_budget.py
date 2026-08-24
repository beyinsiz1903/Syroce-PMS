#!/usr/bin/env python3
"""Prevent test suites from becoming green by silently skipping more tests.

This is intentionally a source-level growth guard. Runtime skips in the full
backend suite are validated separately from its JUnit report.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = ROOT / ".ci" / "test-skip-budget.json"


def _python_skip_counts() -> tuple[int, int]:
    total = 0
    ci_module = 0
    for path in (ROOT / "backend" / "tests").rglob("*.py"):
        if "_quarantine" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            raise SystemExit(f"Cannot audit skips; invalid Python in {path}: {exc}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                dotted = _dotted_name(node.func)
                if dotted == "pytest.skip" or dotted in {
                    "pytest.mark.skip",
                    "pytest.mark.skipif",
                }:
                    total += 1
                if dotted == "pytest.skip" and any(
                    keyword.arg == "allow_module_level"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                ):
                    ci_module += 1
    return total, ci_module


def _dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


JS_SKIP = re.compile(r"\b(?:test|it|describe)\s*\.\s*skip\s*\(")


def _javascript_skip_count(root: Path) -> int:
    total = 0
    for suffix in ("*.js", "*.jsx", "*.ts", "*.tsx"):
        for path in root.rglob(suffix):
            total += len(JS_SKIP.findall(path.read_text(encoding="utf-8")))
    return total


def main() -> int:
    budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    python_total, python_module = _python_skip_counts()
    frontend_unit = _javascript_skip_count(ROOT / "frontend" / "src")
    frontend_e2e = sum(
        _javascript_skip_count(ROOT / "frontend" / directory)
        for directory in ("e2e", "e2e-business", "e2e-stress")
        if (ROOT / "frontend" / directory).exists()
    )
    test_files = sum(
        1
        for path in (ROOT / "backend" / "tests").rglob("test_*.py")
        if "_quarantine" not in path.parts
    )
    actual = {
        "backend_skip_constructs": python_total,
        "backend_module_level_skips": python_module,
        "frontend_unit_skip_constructs": frontend_unit,
        "frontend_e2e_skip_constructs": frontend_e2e,
    }

    failures: list[str] = []
    for key, value in actual.items():
        maximum = int(budget[key])
        if value > maximum:
            failures.append(f"{key} grew: actual={value}, budget={maximum}")
    minimum_files = int(budget["minimum_backend_test_files"])
    if test_files < minimum_files:
        failures.append(
            f"backend test inventory shrank: actual={test_files}, minimum={minimum_files}"
        )

    print(json.dumps({**actual, "backend_test_files": test_files}, indent=2))
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
