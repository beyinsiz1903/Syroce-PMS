---
name: yarn 1.x range resolutions don't override direct deps
description: Why a `resolutions`/`overrides` range entry leaves a direct dependency on its own (vulnerable) version, and how to actually force it.
---

# yarn 1.x: a range `resolutions` entry does NOT force a direct dependency

When clearing a `yarn audit` finding on a package that is BOTH a direct
dependency and a transitive one, adding a range entry to `resolutions`
(e.g. `"postcss": ">=8.5.10"`) forces the transitive copies but leaves the
**direct** dependency resolving against its own declared range
(e.g. devDep `"postcss": "^8.4.49"` stays on 8.5.8). The lockfile then shows
two entries: the resolution group at the patched version and the direct-dep
descriptor still on the vulnerable one — so the audit still fails.

**Fix:** bump the direct dependency's own range in
`dependencies`/`devDependencies` (e.g. `^8.4.49` -> `^8.5.10`), not just the
`resolutions` entry. After that the descriptors merge onto one patched
version.

**Why:** in yarn 1.x the `resolutions` field reliably overrides nested
(transitive) deps; range-valued resolutions are flaky for the top-level
descriptor. An exact-version resolution is more forceful than a range, but
bumping the declared direct range is the unambiguous fix.

**How to apply:** after editing resolutions, `rg "^<pkg>@" yarn.lock` — if
you still see a second entry pinned below the patched version, find which
direct dep declares that range and bump it too. Transitive-only packages
(ws, dompurify-via-jspdf, brace-expansion-via-eslint) are fine with a
resolution alone.
