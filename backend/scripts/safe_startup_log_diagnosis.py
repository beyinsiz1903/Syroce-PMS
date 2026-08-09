#!/usr/bin/env python3
"""Reduce application startup logs to allowlisted, non-sensitive metadata."""

from __future__ import annotations

import json
import re
import sys

MISSING_MODULE_RE = re.compile(r"No module named ['\"]([A-Za-z0-9_.-]{1,100})['\"]")
EXCEPTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{1,100}(?:Error|Exception))\b")
APP_FRAME_RE = re.compile(r'(?:File )?["\']?/app/([A-Za-z0-9_./-]{1,200}\.py)["\']?, line (\d{1,7})')
CONFIG_KEYS = (
    "DB_NAME",
    "ENCRYPTION_MASTER_KEY",
    "JWT_SECRET",
    "MONGO_URL",
    "REDIS_URL",
)


def _count_class(count: int) -> str:
    if count == 0:
        return "ZERO"
    if count <= 20:
        return "LOW"
    if count <= 200:
        return "MEDIUM"
    return "HIGH"


def diagnose(text: str) -> dict[str, object]:
    """Return safe startup failure metadata without preserving log text."""
    missing_modules = sorted(set(MISSING_MODULE_RE.findall(text)))[:10]
    exception_types = sorted(set(EXCEPTION_RE.findall(text)))[:10]
    application_frames = []
    seen_frames: set[tuple[str, int]] = set()
    for path, line_text in APP_FRAME_RE.findall(text):
        frame = (path, int(line_text))
        if frame not in seen_frames:
            seen_frames.add(frame)
            application_frames.append({"file": path, "line": frame[1]})
        if len(application_frames) == 10:
            break

    config_key_mentions = [key for key in CONFIG_KEYS if key in text]
    lowered = text.lower()
    if missing_modules:
        classification = "MISSING_RUNTIME_DEPENDENCY"
    elif "validationerror" in lowered or config_key_mentions:
        classification = "CONFIGURATION_ERROR"
    elif "serverselectiontimeouterror" in lowered or "connectionfailure" in lowered:
        classification = "DATABASE_CONNECTIVITY"
    elif "importerror" in lowered:
        classification = "APPLICATION_IMPORT_ERROR"
    elif "application startup failed" in lowered or exception_types:
        classification = "APPLICATION_STARTUP_ERROR"
    else:
        classification = "UNCLASSIFIED_STARTUP_FAILURE"

    return {
        "classification": classification,
        "missing_modules": missing_modules,
        "exception_types": exception_types,
        "application_frames": application_frames,
        "config_key_mentions": config_key_mentions,
        "log_line_count_class": _count_class(len(text.splitlines())),
    }


def main() -> None:
    print(json.dumps(diagnose(sys.stdin.read()), separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
