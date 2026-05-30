---
name: Stress spec module-block probes can hide path drift
description: Why a "module-blocked / SKIP" stress surface may be a vacuous security scan, and how to verify it is honest.
---

# Stress spec "module-blocked via HTTP probe" can silently disable a security scan

In the web/backend Full Stress Suite, many specs gate their real assertions behind a
reachability probe: they GET a `list`/setup URL, and if it returns non-2xx they mark
the surface `moduleBlocked` (recorded as an informational P2) and SKIP the actual
checks (e.g. cross-tenant leak scan, PII mask, IDOR).

**Trap:** if the probed URL is *wrong* (path drift), it 404s and the surface is marked
"blocked" — looking like a legitimate module-block, but the security scan never ran.
A drifted path turns a security test into a vacuous no-op that still reports green-ish.

**Why:** the block is keyed on HTTP status, not on whether the route actually exists.
A typo / stale prefix is indistinguishable from a genuinely-gated module.

**How to apply:** before accepting any stress surface's `blocked`/`SKIP`/`REVIEW` as
honest, confirm the probed path actually resolves to a mounted backend route (grep the
routers for the real prefix). If the path is drifted and the real endpoint exists and
is reachable by the test token, fixing the path restores real coverage — this is a
strengthening, not fake-green, and is safe because the probe degrades non-2xx to a P2
informational (never a hard FAIL). Distinct doctrine for the by-design cases that must
NOT be "fixed" to 2xx: super_admin fail-closed 404 (`require_super_admin_guard(
not_found=True)`), EntitlementMiddleware 403 (module-not-purchased), HMAC-gated public
surfaces — making those reachable would be auth weakening.
