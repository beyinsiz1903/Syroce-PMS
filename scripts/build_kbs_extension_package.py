#!/usr/bin/env python3
"""Build/check the production KBS browser-extension ZIP deterministically."""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "extension"
OUTPUT = ROOT / "backend" / "assets" / "syroce-kbs-eklentisi.zip"
PREFIX = "syroce-kbs-eklentisi"
ALLOWED_SUFFIXES = {".js", ".json", ".html", ".css", ".md", ".png", ".svg"}
FIXED_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


def build_archive() -> bytes:
    if not SOURCE.is_dir():
        raise RuntimeError(f"KBS extension source directory not found: {SOURCE}")

    buffer = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(SOURCE.rglob("*")):
            relative = path.relative_to(SOURCE)
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            if "tests" in relative.parts:
                continue
            info = zipfile.ZipInfo(f"{PREFIX}/{relative.as_posix()}", FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
            file_count += 1

    if file_count == 0:
        raise RuntimeError("No KBS extension files were selected for packaging")
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Fail if the committed archive is stale"
    )
    args = parser.parse_args()
    expected = build_archive()

    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != expected:
            print(
                f"ERROR: stale or missing KBS extension package: {OUTPUT}",
                file=sys.stderr,
            )
            return 1
        print(f"KBS extension package is current: {OUTPUT}")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(expected)
    print(f"Wrote {OUTPUT} ({len(expected)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
