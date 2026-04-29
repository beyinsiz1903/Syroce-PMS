#!/usr/bin/env python3
"""v72 Bug DH-CI / v78 DN / v81 DQ: AST static check for `@cached` endpoints.

Catches three regression classes:
  1. DD2/DE: @cached endpoint without tenant param → cross-tenant cache key collision
     (cache_manager._extract_tenant_id resolves args by name: current_user/user/tenant/tenant_id).
  2. DG/DH: @cached GET endpoint without RBAC dependency → cross-role data leak.
  3. v81 DQ: @cached endpoint with manual `_require_*(user)` guard in body BUT no
     `_perm=Depends(require_op(...))` in signature → cache HIT bypasses guard
     (FastAPI dependency-injection runs before cache lookup; function body does NOT).
     This is the architectural leak documented in v80-EXT (Bug DP-2).

Alias-aware: detects `cached`, `_cached`, or any local alias of the decorator.
Allow-list: explicit global/admin endpoints (super_admin guarded).

v78 DN: per-endpoint inline allowlist via `# rbac-allow: cache-rbac` marker on
the line directly above the first decorator. Use when cross-role read access is
intentionally operational (e.g. spa/services, mice/spaces, housekeeping ops).
NOTE: marker SADECE intentional cross-role içindir, "manuel guard var" gerekçesiyle DEĞİL.

Legacy `# noqa: cache-rbac` form is also accepted for backward compatibility,
but new code should use `# rbac-allow: cache-rbac` (avoids ruff "invalid noqa"
warnings since `cache-rbac` is not a real lint code).

Exit 0 on clean, 1 on tenant findings, manual-guard anti-pattern, or (--strict) any RBAC.
"""
import ast
import pathlib
import sys

# Both forms accepted — new code uses `rbac-allow:` to avoid ruff noqa-parser warnings.
NOQA_MARKERS = ("rbac-allow: cache-rbac", "noqa: cache-rbac")

REPO = pathlib.Path(__file__).resolve().parents[1] / "backend"
TENANT_PARAMS = {"current_user", "user", "tenant", "tenant_id"}
ALLOWLIST_TENANT = {
    # Intentionally global metric endpoints (super_admin router-level guard).
    "routers/import_admin.py",
    "routers/outbox_admin.py",
}


def _is_cached_decorator(d, cached_aliases: set[str]) -> bool:
    """Match @cached, @cached(...), @<alias>, @<module>.cached(...)."""
    if isinstance(d, ast.Name) and d.id in cached_aliases:
        return True
    if isinstance(d, ast.Call):
        if isinstance(d.func, ast.Name) and d.func.id in cached_aliases:
            return True
        if isinstance(d.func, ast.Attribute) and d.func.attr == "cached":
            return True
    if isinstance(d, ast.Attribute) and d.attr == "cached":
        return True
    return False


def _collect_cached_aliases(tree: ast.AST) -> set[str]:
    """Find local names bound to `cached` import (e.g. `from cache_manager import cached as _cached`)."""
    aliases = {"cached"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "cached":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _has_rbac(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detect RBAC dependency: route-level dependencies=[] or signature param Depends(require_*)."""
    for d in node.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
            for kw in d.keywords:
                if kw.arg == "dependencies":
                    return True
    for default in node.args.defaults + node.args.kw_defaults:
        if default is None:
            continue
        try:
            src = ast.unparse(default)
        except Exception:
            continue
        if "require_op" in src or "require_role" in src or "require_super_admin" in src:
            return True
    return False


def _is_get_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in node.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
            if d.func.attr == "get":
                return True
    return False


_SAFE_GUARD_NAMES = {
    "require_op", "require_role", "require_super_admin",
    "require_finance", "require_roles",
}


def _extract_guard_call_name(call: ast.Call) -> str | None:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _has_manual_role_guard(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Detect TOP-LEVEL `_require_*` / `require_*` calls in function body.

    Only top-level Expr/Assign statements count — these are unconditional guards
    that get bypassed on @cached hit (v80-EXT Bug DP-2). Calls inside `if`,
    `try`, etc. are conditional (e.g. write-gating) and do not constitute a
    cache-bypass leak. Calls inside `Depends(...)` are in the function signature
    (args), not body, and are safe.
    """
    for stmt in node.body:
        call: ast.Call | None = None
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Call):
            call = stmt.value
        if call is None:
            continue
        name = _extract_guard_call_name(call)
        if name and (
            name.startswith(("_require_", "require_"))
            or name in {"_enforce", "enforce_permission", "_enforce_permission"}
        ) and name not in _SAFE_GUARD_NAMES:
            return name
    return None


def _has_noqa_marker(source_lines: list[str], node) -> bool:
    """Check line directly above first decorator for an RBAC-allow marker."""
    if not node.decorator_list:
        return False
    first_dec_line = min(d.lineno for d in node.decorator_list)
    idx = first_dec_line - 2  # 0-indexed line above first decorator
    if idx < 0 or idx >= len(source_lines):
        return False
    line = source_lines[idx]
    return any(m in line for m in NOQA_MARKERS)


def main() -> int:
    strict = "--strict" in sys.argv
    tenant_findings: list[tuple[str, int, str]] = []
    rbac_findings: list[tuple[str, int, str]] = []
    anti_pattern_findings: list[tuple[str, int, str, str]] = []  # v81 DQ
    suppressed = 0
    marker_count = 0
    legacy_marker_count = 0

    for py in REPO.rglob("*.py"):
        rel = str(py.relative_to(REPO))
        try:
            source = py.read_text()
            tree = ast.parse(source)
        except SyntaxError:
            continue
        source_lines = source.splitlines()
        marker_count += source.count("rbac-allow: cache-rbac")
        legacy_marker_count += source.count("noqa: cache-rbac")

        cached_aliases = _collect_cached_aliases(tree)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(_is_cached_decorator(d, cached_aliases) for d in node.decorator_list):
                continue

            params = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}

            # Check 1: tenant param (noqa does NOT suppress — tenant leak always hard-fail)
            if not (params & TENANT_PARAMS) and rel not in ALLOWLIST_TENANT:
                tenant_findings.append((rel, node.lineno, node.name))

            # Check 2: RBAC for GET endpoints (noqa suppresses intentional cross-role)
            has_rbac = _has_rbac(node)
            if _is_get_route(node) and not has_rbac and rel not in ALLOWLIST_TENANT:
                if _has_noqa_marker(source_lines, node):
                    suppressed += 1
                else:
                    rbac_findings.append((rel, node.lineno, node.name))

            # Check 3 (v81 DQ): @cached + manual `_require_*(user)` body guard but no Depends RBAC
            # → cache HIT bypasses guard. Allows `# noqa: cache-rbac` marker for known-safe
            # cases (e.g. tenant-only guard + tenant-scoped cache key).
            if not has_rbac:
                guard_name = _has_manual_role_guard(node)
                if guard_name and rel not in ALLOWLIST_TENANT:
                    if _has_noqa_marker(source_lines, node):
                        suppressed += 1
                    else:
                        anti_pattern_findings.append((rel, node.lineno, node.name, guard_name))

    if tenant_findings:
        print("FAIL: @cached endpoints missing tenant param (cross-tenant cache leak risk):")
        for f in tenant_findings:
            print(f"  {f[0]}:{f[1]} {f[2]}")
    if rbac_findings:
        print(f"\nWARN: {len(rbac_findings)} @cached GET endpoints missing RBAC dependency (cross-role leak audit needed):")
        for f in rbac_findings[:20]:
            print(f"  {f[0]}:{f[1]} {f[2]}")
        if len(rbac_findings) > 20:
            print(f"  ... +{len(rbac_findings) - 20} more")

    if anti_pattern_findings:
        print(f"\nFAIL: {len(anti_pattern_findings)} @cached endpoints with manual body guard (cache HIT bypasses guard, v80-EXT DP-2):")
        for f in anti_pattern_findings:
            print(f"  {f[0]}:{f[1]} {f[2]} — manual `{f[3]}()` in body, missing Depends(require_op/role)")

    if suppressed:
        print(f"\nINFO: {suppressed} RBAC finding(s) suppressed via `# rbac-allow: cache-rbac` (intentional cross-role).")
        print(f"INFO: {marker_count} marker(s) present in source ({suppressed} suppressed; rest are on endpoints with RBAC dep or in ALLOWLIST_TENANT — safe).")
    if legacy_marker_count:
        print(f"\nWARN: {legacy_marker_count} legacy `# noqa: cache-rbac` marker(s) found — please migrate to `# rbac-allow: cache-rbac` to avoid ruff noqa-parser warnings.")

    if not tenant_findings and not rbac_findings and not anti_pattern_findings:
        print("OK: 0 @cached endpoints with cache leak, RBAC gap, or manual-guard anti-pattern.")
        return 0
    if tenant_findings or anti_pattern_findings:
        return 1  # tenant leak / cache-bypass anti-pattern = hard fail
    if strict and rbac_findings:
        return 1  # --strict: RBAC also fails
    return 0  # RBAC = warn-only by default (audit ongoing)


if __name__ == "__main__":
    sys.exit(main())
