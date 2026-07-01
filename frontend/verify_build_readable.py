#!/usr/bin/env python3
"""Full-read integrity verifier for a built SPA directory.

Why this exists (no-fake-green):
  Size-only checks (``test -s`` / ``find -size 0``) inspect ``st_size`` only.
  A deploy-VM materialization hiccup (write phase running out of disk, or a
  copy that sets the file size but never lands the data blocks) can leave a
  file whose inode reports the CORRECT ``st_size`` but whose data is
  unreadable / short. Such a file passes every size-only gate, so the build
  "looks healthy" — yet at serve time uvicorn opens it, stamps the right
  ``Content-Length`` from ``st_size`` (HEAD 200), then the body read hits EOF
  early: ``RuntimeError("Response content shorter than Content-Length")`` ->
  the edge reverse-proxy reports "reading: unexpected EOF" -> the client gets a
  500 for every JS chunk -> permanent WHITE SCREEN.

  This verifier actually READS every served file to EOF and asserts
  ``bytes_read == st_size`` (catching truncation / unreadable data blocks), and
  additionally asserts that every ``index.html``-referenced ``/js`` chunk and
  every ``build/js/*.js`` is non-empty (catching 0-byte entry/lazy chunks).

  ``.map`` source maps are skipped: the browser does not fetch them to render,
  so reading them at boot only wastes time and a corrupt map never white-screens.

Exit 0 = intact, exit 1 = broken (offending files printed to stderr),
exit 2 = bad usage.
"""
from __future__ import annotations

import os
import re
import sys

_CHUNK = 1 << 16
_MAX_REPORT = 50

# Text assets a browser parses as source. A correctly-built minified bundle of
# any of these contains ZERO NUL bytes, so even a SINGLE embedded NUL means a
# partially-sparse / hole-punched materialization (data length matches st_size
# but some blocks came back as zeros). Binary assets (fonts, images) legitimately
# contain NUL bytes, so they get only the weaker all-NUL check.
_TEXT_EXTS = (
    ".js", ".mjs", ".cjs", ".css", ".html", ".htm", ".json",
    ".svg", ".txt", ".webmanifest", ".xml",
)


def _full_read(path: str) -> tuple[int, bool, bool]:
    """Read the whole file to EOF.

    Returns ``(bytes_read, has_nonzero, has_nul)``.

    - ``bytes_read`` short vs ``st_size`` (or an ``OSError``) means the data
      blocks are not fully readable — an EOF-early materialization fault.
    - ``has_nonzero`` False on a non-empty file means every byte is NUL: a
      sparse/holes materialization where reads return zeros up to ``st_size``
      (so ``bytes_read == st_size`` but the asset is still garbage). No
      legitimate built asset is entirely NUL, so this is also corruption.
    - ``has_nul`` True means at least one NUL byte is present; for a TEXT asset
      that alone is corruption (a clean source bundle has none), catching a
      partially-sparse file whose non-NUL bytes still sum to ``st_size``.
    """
    total = 0
    has_nonzero = False
    has_nul = False
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if not has_nonzero and chunk.translate(None, b"\x00"):
                has_nonzero = True
            if not has_nul and b"\x00" in chunk:
                has_nul = True
    return total, has_nonzero, has_nul


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_build_readable.py <build_dir>", file=sys.stderr)
        return 2

    build = os.path.abspath(sys.argv[1])
    if not os.path.isdir(build):
        print(f"BROKEN: build dir missing: {build}", file=sys.stderr)
        return 1

    broken: list[str] = []
    checked = 0

    # 1) Full-read EVERY served regular file: bytes-read MUST equal st_size.
    #    Skip symlinks and *.map (dev-only, never fetched to render).
    for root, _dirs, files in os.walk(build):
        for name in files:
            if name.endswith(".map"):
                continue
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            try:
                size = os.stat(path).st_size
            except OSError as exc:
                broken.append(f"{path} (stat: {exc})")
                continue
            try:
                got, has_nonzero, has_nul = _full_read(path)
            except OSError as exc:
                broken.append(f"{path} (read: {exc})")
                continue
            checked += 1
            if got != size:
                broken.append(f"{path} (short read: {got}/{size} bytes)")
            elif size > 0 and not has_nonzero:
                broken.append(f"{path} (all-NUL data: {size} bytes, sparse/holes)")
            elif has_nul and name.lower().endswith(_TEXT_EXTS):
                broken.append(f"{path} (NUL byte in text asset: {size} bytes, partially sparse)")

    # 2) Every index.html-referenced /js chunk must exist and be non-empty.
    index_html = os.path.join(build, "index.html")
    refs: list[str] = []
    if os.path.isfile(index_html):
        try:
            with open(index_html, "rb") as fh:
                html = fh.read().decode("utf-8", "replace")
            refs = sorted(set(re.findall(r"/js/[A-Za-z0-9._-]+\.js", html)))
        except OSError as exc:
            broken.append(f"{index_html} (read: {exc})")
    else:
        broken.append(f"{index_html} (missing)")
    if not refs:
        broken.append("index.html references no /js chunks")
    for ref in refs:
        ref_path = build + ref
        try:
            if os.path.getsize(ref_path) <= 0:
                broken.append(f"{ref_path} (referenced /js chunk empty)")
        except OSError as exc:
            broken.append(f"{ref_path} (referenced /js chunk missing: {exc})")

    # 3) Every build/js/*.js must be non-empty (a 0-byte lazy chunk still
    #    white-screens on navigation even when the entry chunk is fine).
    js_dir = os.path.join(build, "js")
    if os.path.isdir(js_dir):
        for name in os.listdir(js_dir):
            if not name.endswith(".js"):
                continue
            js_path = os.path.join(js_dir, name)
            try:
                if os.path.getsize(js_path) <= 0:
                    broken.append(f"{js_path} (0-byte js chunk)")
            except OSError as exc:
                broken.append(f"{js_path} (js chunk stat: {exc})")

    if broken:
        print(
            f"BROKEN: full-read verify failed ({len(broken)} issue(s); "
            f"{checked} files fully read):",
            file=sys.stderr,
        )
        for item in broken[:_MAX_REPORT]:
            print(f"  - {item}", file=sys.stderr)
        if len(broken) > _MAX_REPORT:
            print(f"  ... and {len(broken) - _MAX_REPORT} more", file=sys.stderr)
        return 1

    print(
        f"OK: full-read verify passed ({checked} files fully read, "
        f"{len(refs)} index.html /js refs present+nonempty)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
