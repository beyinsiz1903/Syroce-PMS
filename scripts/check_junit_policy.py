#!/usr/bin/env python3
"""Fail closed on empty, failing, or unexpectedly skipped JUnit suites."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--min-tests", type=int, required=True)
    parser.add_argument("--max-skips", type=int, required=True)
    parser.add_argument("--allow-skip", action="append", default=[])
    args = parser.parse_args()

    root = ET.parse(args.report).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    tests = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", 0)) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", 0)) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in suites)

    unexpected: list[str] = []
    allowed = [re.compile(pattern) for pattern in args.allow_skip]
    for case in root.iter("testcase"):
        skipped_node = case.find("skipped")
        if skipped_node is None:
            continue
        identity = "::".join(
            filter(
                None,
                (
                    case.attrib.get("classname", ""),
                    case.attrib.get("name", ""),
                    skipped_node.attrib.get("message", ""),
                ),
            )
        )
        if not any(pattern.search(identity) for pattern in allowed):
            unexpected.append(identity)

    print(
        "JUnit policy: "
        f"tests={tests} failures={failures} errors={errors} skipped={skipped} "
        f"unexpected_skips={len(unexpected)}"
    )
    problems: list[str] = []
    if tests < args.min_tests:
        problems.append(f"test count {tests} is below minimum {args.min_tests}")
    if failures or errors:
        problems.append(f"failures={failures}, errors={errors}")
    if skipped > args.max_skips:
        problems.append(f"skip count {skipped} exceeds budget {args.max_skips}")
    if unexpected:
        problems.append("unexpected skips:\n- " + "\n- ".join(unexpected))
    if problems:
        print("ERROR: " + "\n".join(problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
