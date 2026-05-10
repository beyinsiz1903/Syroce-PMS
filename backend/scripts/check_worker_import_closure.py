#!/usr/bin/env python3
"""AST-based import closure scan for the Celery worker process.

Phase 5 prerequisite (per docs/backend_refactors/requirements-split-plan.md
§4.4): before slimming the worker Docker image to a subset of requirements,
deterministically prove which third-party packages the worker actually
imports — recursively, starting from the worker entry points.

This is a STATIC scan. It WILL miss:
    - dynamic imports (importlib.import_module(name_from_var))
    - provider/plugin discovery via entry_points
    - Celery autodiscover_tasks() targets that are not also statically imported
    - string-based plugin loading
    - imports gated behind runtime feature flags evaluated at boot
A `worker boot smoke` is therefore STILL required before promoting any
Phase 5 worker.txt-only Dockerfile.

Targets (which subset closure to compare against):

    --target worker               : closure of requirements/worker.txt
                                     (= base.txt). Strict minimum.
    --target worker-runtime       : closure of requirements/worker-runtime.txt
                                     (= worker.txt + fastapi + starlette).
                                     Phase-5 production worker image (Pragmatic
                                     case from plan §4.4).
    --target worker-conservative  : closure of base + worker + ml + reports
                                     + integrations. Fall-back if Pragmatic
                                     boot smoke fails — covers all subsets
                                     the worker queues might transitively
                                     touch (default/ml/analytics/messaging/
                                     pipeline/backup).

Exit codes:
    0 : every imported third-party module is covered by the chosen subset
    1 : missing packages found (subset is not sufficient)
    2 : usage / file not found

Usage:
    python backend/scripts/check_worker_import_closure.py --target worker
    python backend/scripts/check_worker_import_closure.py --target worker-runtime
    python backend/scripts/check_worker_import_closure.py --target worker-runtime --verbose
"""
from __future__ import annotations

import argparse
import ast
import importlib.metadata
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
SPLIT_DIR = BACKEND_DIR / "requirements"

# Worker entry points: ONLY celery_app.py + celery_tasks.py.
# Rationale: celery_app.py defines no autodiscover_tasks() / no `include=` arg
# (verified 2026-05-10), so the worker process boots strictly via these two
# modules. backend/workers/*.py files are reached transitively only when
# celery_tasks (or one of its transitive imports) imports them. Files like
# backend/workers/hardening_router.py are FastAPI routers mounted by server.py
# and are NOT loaded into the worker process — including them as entry points
# was producing false-positive FastAPI/uvicorn dependencies in v1 of this scan.
ENTRY_POINTS: list[Path] = [
    BACKEND_DIR / "celery_app.py",
    BACKEND_DIR / "celery_tasks.py",
]

# Module-name -> distribution-name overrides for cases packages_distributions()
# does not cover or maps ambiguously.
MANUAL_DIST_OVERRIDES: dict[str, str] = {
    "PIL": "pillow",
    "jwt": "pyjwt",
    "yaml": "pyyaml",
    "jose": "python-jose",
    "magic": "python-magic",
    "dotenv": "python-dotenv",
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python-headless",
    "email_validator": "email-validator",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "dateutil": "python-dateutil",
    "OpenSSL": "pyopenssl",
    "Crypto": "pycryptodome",
    "google": "google-api-core",
    "win32api": "pywin32",
}

# Third-party top-level modules to ignore in coverage check (built-in to runtime
# image but not declared as direct deps; not relevant to subset selection).
IGNORE_MODULES: set[str] = {
    "pkg_resources",
    "setuptools",
    "_distutils_hack",
}

NAME_RE = re.compile(r"[<>=!~\[;\s]")


def _norm(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def parse_requirement_set(path: Path, _seen: set[Path] | None = None) -> set[str]:
    """Return transitive distribution-name set for a requirements file."""
    if _seen is None:
        _seen = set()
    rp = path.resolve()
    if rp in _seen or not rp.exists():
        return set()
    _seen.add(rp)
    out: set[str] = set()
    for raw in rp.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            ref = line.split(None, 1)[1].strip()
            out |= parse_requirement_set(rp.parent / ref, _seen)
            continue
        if line.startswith("-"):
            continue
        name = NAME_RE.split(line, 1)[0].strip()
        if name:
            out.add(_norm(name))
    return out


# Cache project-internal top-level names (siblings of celery_app.py inside backend/).
def _project_internal_top_names() -> set[str]:
    names: set[str] = set()
    for entry in BACKEND_DIR.iterdir():
        if entry.is_dir() and (entry / "__init__.py").exists():
            names.add(entry.name)
        elif entry.is_dir() and not entry.name.startswith((".", "__")):
            # backend/workers, backend/scripts etc. — also project-internal.
            names.add(entry.name)
        elif entry.suffix == ".py":
            names.add(entry.stem)
    return names


PROJECT_INTERNAL: set[str] = _project_internal_top_names()
STDLIB: set[str] = set(sys.stdlib_module_names)


def is_project_internal(top: str) -> bool:
    return top in PROJECT_INTERNAL


def is_stdlib(top: str) -> bool:
    return top in STDLIB


def resolve_internal_path(modname: str) -> Path | None:
    """Map dotted module name to a backend/ file path, if it exists."""
    parts = modname.split(".")
    cur = BACKEND_DIR
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        cand_dir = cur / part
        cand_pkg_init = cand_dir / "__init__.py"
        cand_mod = cur / f"{part}.py"
        if is_last:
            if cand_mod.exists():
                return cand_mod
            if cand_pkg_init.exists():
                return cand_pkg_init
            if cand_dir.is_dir():
                return cand_dir  # namespace package or module dir
            return None
        if cand_dir.is_dir():
            cur = cand_dir
        else:
            return None
    return None


def collect_imports_from_file(path: Path) -> set[str]:
    """Return set of dotted module names imported by this file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        print(f"WARN: syntax error in {path}: {e}", file=sys.stderr)
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports (level > 0) — they are project-internal.
            if node.level and node.level > 0:
                # Best-effort: resolve relative to file's package.
                pkg_parts = path.relative_to(BACKEND_DIR).with_suffix("").parts
                # Drop file basename if it's not __init__
                if pkg_parts and pkg_parts[-1] != "__init__":
                    pkg_parts = pkg_parts[:-1]
                base = list(pkg_parts[: max(0, len(pkg_parts) - (node.level - 1))])
                if node.module:
                    base.append(node.module)
                if base:
                    out.add(".".join(base))
                # Also collect from-import names that may be submodules
                for alias in node.names:
                    if alias.name != "*":
                        out.add(".".join(base + [alias.name]))
                continue
            if node.module:
                out.add(node.module)
                # `from X import Y` — Y might be submodule; record both.
                for alias in node.names:
                    if alias.name != "*":
                        out.add(f"{node.module}.{alias.name}")
    return out


def walk_project_closure(entry_points: list[Path]) -> tuple[set[str], set[Path]]:
    """Recursively collect (third_party_top_modules, visited_internal_files)."""
    visited: set[Path] = set()
    third_party: set[str] = set()
    queue: list[Path] = [p for p in entry_points if p.exists()]
    for p in entry_points:
        if not p.exists():
            print(f"WARN: entry point not found: {p}", file=sys.stderr)
    while queue:
        f = queue.pop()
        rf = f.resolve()
        if rf in visited:
            continue
        visited.add(rf)
        if f.is_dir():
            # Walk all .py inside the dir (e.g. namespace package).
            for sub in f.rglob("*.py"):
                if sub.resolve() not in visited:
                    queue.append(sub)
            continue
        for modname in collect_imports_from_file(f):
            top = modname.split(".")[0]
            if not top:
                continue
            if is_stdlib(top):
                continue
            if is_project_internal(top):
                # Try to resolve and recurse.
                resolved = resolve_internal_path(modname)
                if resolved is None:
                    # Try the top-level alone (e.g. `from integrations import X`).
                    resolved = resolve_internal_path(top)
                if resolved and resolved.resolve() not in visited:
                    queue.append(resolved)
                continue
            third_party.add(top)
    return third_party, visited


def build_module_to_dist_map() -> dict[str, str]:
    """Best-effort: use importlib.metadata.packages_distributions + manual overrides."""
    raw = importlib.metadata.packages_distributions()
    out: dict[str, str] = {}
    for mod, dists in raw.items():
        if dists:
            out[mod] = _norm(dists[0])
    out.update({k: _norm(v) for k, v in MANUAL_DIST_OVERRIDES.items()})
    return out


TARGETS: dict[str, list[str]] = {
    "worker": ["worker.txt"],
    "worker-runtime": ["worker-runtime.txt"],
    "worker-conservative": ["worker.txt", "ml.txt", "reports.txt", "integrations.txt"],
}


def resolve_target_set(target: str) -> set[str]:
    if target not in TARGETS:
        print(f"ERROR: unknown target {target!r}", file=sys.stderr)
        sys.exit(2)
    out: set[str] = set()
    for fname in TARGETS[target]:
        out |= parse_requirement_set(SPLIT_DIR / fname)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=list(TARGETS.keys()))
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    third_party_modules, visited = walk_project_closure(ENTRY_POINTS)

    mod2dist = build_module_to_dist_map()
    target_dists = resolve_target_set(args.target)

    covered: dict[str, str] = {}        # mod -> dist
    missing_dists: dict[str, str] = {}  # mod -> dist (dist NOT in subset)
    unmapped: set[str] = set()          # mod -> no dist resolution

    for mod in sorted(third_party_modules):
        if mod in IGNORE_MODULES:
            continue
        dist = mod2dist.get(mod)
        if dist is None:
            unmapped.add(mod)
            continue
        if dist in target_dists:
            covered[mod] = dist
        else:
            missing_dists[mod] = dist

    print("=" * 64)
    print(f"worker import closure scan — target={args.target}")
    print("=" * 64)
    print(f"  entry points scanned    : {len(ENTRY_POINTS)}")
    print(f"  internal files visited  : {len(visited)}")
    print(f"  third-party modules     : {len(third_party_modules)}")
    print(f"  subset distribution set : {len(target_dists)}")
    print(f"  subset files            : {', '.join(TARGETS[args.target])}")
    print()
    print(f"[ok]    covered modules   : {len(covered):3d}")
    print(f"[?]     unmapped modules  : {len(unmapped):3d} (no dist mapping found)")
    print(f"[FAIL?] missing in subset : {len(missing_dists):3d}")
    print()

    if unmapped:
        print("Unmapped third-party modules (manual review required):")
        for m in sorted(unmapped):
            print(f"    ? {m}")
        print()

    if missing_dists:
        print(f"Missing distributions ({len(missing_dists)}):")
        # Group by dist for readability.
        by_dist: dict[str, list[str]] = {}
        for mod, dist in missing_dists.items():
            by_dist.setdefault(dist, []).append(mod)
        for dist in sorted(by_dist):
            mods = sorted(by_dist[dist])
            print(f"    - {dist:30s}  used as: {', '.join(mods)}")
        print()

    if args.verbose:
        print("--- covered modules (mod -> dist) ---")
        for mod, dist in sorted(covered.items()):
            print(f"    {mod:30s} -> {dist}")
        print()

    print("CAVEAT: AST scan misses dynamic imports, plugin entry_points,")
    print("Celery autodiscover targets, and string-based feature loaders.")
    print("Worker boot smoke required before promoting Phase 5 Dockerfile.")
    print()

    if missing_dists:
        print(f"VERDICT: INSUFFICIENT — subset '{args.target}' is missing "
              f"{len(missing_dists)} third-party module(s).")
        return 1

    if unmapped:
        print(f"VERDICT: REVIEW NEEDED — {len(unmapped)} unmapped module(s); "
              f"manually confirm each is stdlib/internal/declared.")
        # Treat as warning (exit 0). Caller should still inspect.
        return 0

    print(f"VERDICT: OK — subset '{args.target}' covers all "
          f"statically-detected worker imports.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
