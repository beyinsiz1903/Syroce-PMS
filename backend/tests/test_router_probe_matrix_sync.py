"""Task #139 — CI guard: keep the 97-spec router-coverage PROBES matrix honest.

Background (Task #136 RCA, see
``docs/drill_reports/20260527_stress_full_stress_suite_cluster_fix.md`` §2.1):

The F9B router-coverage probe spec at
``frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js`` holds a
``PROBES`` array of paths the stress suite hits with safe GETs to measure
"meaningful coverage" of mounted backend routers. The matrix silently drifted
from reality — 38 of 51 originally-listed paths had no router mount (legacy
naming or aspirational endpoints that never shipped). That inflated the
``auth_404_not_deployed`` chorus and collapsed the
``meaningfulCoverage >= 30%`` invariant gate.

Task #136 pruned the list to 20 verified-mounted paths. This test is the
automated guard that keeps it honest as new routers ship:

  * Every PROBES entry must resolve to a real ``GET`` route on the live
    FastAPI app (the one ``server.py`` mounts).
  * If a probe path disappears (router removed/renamed) the build fails
    here, naming the dead probe — long before the stress suite turns it
    into a noisy P2 REVIEW.
  * If somebody adds a new aspirational probe before the endpoint exists,
    the build fails the same way.

Scope: this test only validates that probe paths exist as mounted GETs. It
does NOT enforce that every new public GET endpoint is added to PROBES —
that is an editorial decision (the matrix is intentionally a curated sample,
not an exhaustive route dump).
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute


PROBE_SPEC = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "e2e-stress"
    / "specs"
    / "97-backend-router-coverage-probe.spec.js"
)


def _parse_probe_paths(spec_text: str) -> list[tuple[str, str]]:
    """Extract ``(name, path)`` tuples from the spec's ``PROBES`` array.

    The spec defines entries like::

        { name: 'pms_groups', path: '/api/pms/groups', list_shape: true },

    We pull every ``{ ... path: '...' ... }`` block inside the ``const
    PROBES = [ ... ];`` declaration. The parser is intentionally narrow
    (regex on the curated block) rather than a JS AST because the spec is
    a hand-maintained literal and the format is stable.
    """
    # Isolate the PROBES = [ ... ] literal so we do not match unrelated
    # ``path:`` strings elsewhere in the file (comments, helpers, etc).
    match = re.search(
        r"const\s+PROBES\s*=\s*\[(.*?)\];", spec_text, flags=re.DOTALL
    )
    if not match:
        raise AssertionError(
            f"Could not locate `const PROBES = [...]` in {PROBE_SPEC}. "
            "The probe-matrix sync guard relies on this literal — if the "
            "spec was refactored, update this test to match."
        )
    body = match.group(1)

    entry_re = re.compile(
        r"\{\s*name:\s*'([^']+)'\s*,\s*path:\s*'([^']+)'"
    )
    return entry_re.findall(body)


@pytest.fixture(scope="module")
def app():
    """Load the real FastAPI app (the one uvicorn serves)."""
    return importlib.import_module("server").app


@pytest.fixture(scope="module")
def mounted_get_paths(app) -> set[str]:
    """All static GET paths mounted on the live FastAPI app.

    PROBES are static (no ``{placeholder}`` segments) by design — the
    stress suite hits literal URLs, not parameterised ones — so a plain
    set-membership check is sufficient. Dynamic routes are skipped here:
    if somebody adds a parameterised probe in the future, this test will
    fail with a clear "path not mounted" message and the author can
    either pick a static sibling or extend this guard.
    """
    paths: set[str] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "GET" not in (route.methods or set()):
            continue
        paths.add(route.path)
    return paths


def test_probe_spec_is_parseable():
    """The PROBES literal must remain parseable by this guard."""
    text = PROBE_SPEC.read_text(encoding="utf-8")
    entries = _parse_probe_paths(text)
    assert entries, (
        f"Parsed 0 probe entries from {PROBE_SPEC}. Either the file is "
        "empty or the `{ name: '...', path: '...' }` shape changed — "
        "update _parse_probe_paths to match."
    )


def test_every_probe_path_is_mounted_on_a_real_router(mounted_get_paths):
    """Every PROBES entry must resolve to a mounted GET on the live app.

    When this fails, the message lists every dead probe and the closest
    mounted prefix so the fix is mechanical: either correct the probe
    path to the real mount, or drop the entry if the underlying router
    was removed.
    """
    text = PROBE_SPEC.read_text(encoding="utf-8")
    entries = _parse_probe_paths(text)

    missing: list[tuple[str, str]] = []
    for name, path in entries:
        if path not in mounted_get_paths:
            missing.append((name, path))

    if not missing:
        return

    # Surface a small set of "closest" mounted paths to make the fix
    # obvious (typical case: prefix changed, e.g. /api/guest/journey →
    # /api/guest-journey/list).
    lines = [
        f"{len(missing)} probe(s) in PROBES point at paths that are NOT "
        "mounted on the FastAPI app. The 97-spec router-coverage matrix "
        "has drifted — either fix the path or remove the entry "
        "(see Task #139, and the Task #136 RCA in "
        "docs/drill_reports/20260527_stress_full_stress_suite_cluster_fix.md "
        "§2.1).",
        "",
    ]
    for name, path in missing:
        prefix = path.rsplit("/", 1)[0] or "/"
        siblings = sorted(p for p in mounted_get_paths if p.startswith(prefix))[:5]
        sib_str = ", ".join(siblings) if siblings else "(none — prefix unknown)"
        lines.append(
            f"  • {name}: {path}\n"
            f"      not mounted. Nearby mounted GETs under `{prefix}`: {sib_str}"
        )
    pytest.fail("\n".join(lines))


def test_probe_parser_extracts_known_entry():
    """Self-test: the parser must extract a representative entry.

    Protects the guard itself — if someone weakens ``_parse_probe_paths``
    so the real check passes vacuously (zero entries → zero missing →
    green), this test fails immediately.
    """
    sample = """
    const PROBES = [
        { name: 'demo_one', path: '/api/demo/one', list_shape: true },
        // a comment with path: '/api/should-not-match'
        { name: 'demo_two', path: '/api/demo/two' },
    ];
    """
    entries = dict(_parse_probe_paths(sample))
    assert entries == {
        "demo_one": "/api/demo/one",
        "demo_two": "/api/demo/two",
    }, f"Parser regressed: extracted {entries!r}"
