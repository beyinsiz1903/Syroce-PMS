#!/usr/bin/env python3
"""Remove credential-bearing text before publishing Maestro diagnostics."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote, quote_plus

MASK = "[REDACTED]"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SECRET_ENV = ("SMOKE_EMAIL", "SMOKE_PASSWORD", "SMOKE_GUEST_EMAIL", "SMOKE_GUEST_PASSWORD")


def redact_structure(value):
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "inputTextCommand" and isinstance(item, dict):
            result[key] = {**redact_structure(item), "text": MASK}
        elif any(word in key.upper() for word in ("PASSWORD", "TOKEN", "SECRET")) and isinstance(item, str) and item:
            result[key] = MASK
        else:
            result[key] = redact_structure(item)
    return result


def redact_text(content, secrets):
    variants = set()
    for secret in secrets:
        if secret:
            variants.update((secret, json.dumps(secret)[1:-1], json.dumps(secret, ensure_ascii=False)[1:-1], quote(secret, safe=""), quote_plus(secret)))
    for secret in sorted(variants, key=len, reverse=True):
        content = content.replace(secret, MASK)
    return content


def sanitize(root, secrets):
    count = 0
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise ValueError("Symbolic links are not publishable diagnostics")
        if not path.is_file() or path.suffix.lower() in IMAGE_SUFFIXES:
            continue
        # Unknown binary content fails closed; do not put it into an archive.
        content = path.read_text(encoding="utf-8")
        content = redact_text(content, secrets)
        if path.suffix.lower() == ".json":
            content = json.dumps(redact_structure(json.loads(content)), ensure_ascii=False, indent=2) + "\n"
        path.write_text(content, encoding="utf-8")
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print("Sanitized diagnostic text files:", sanitize(args.root, [os.environ.get(name, "") for name in SECRET_ENV]))
