---
name: audit-fix resolution floor can cross majors and break a CJS consumer
description: Why a `">=X"` resolution to clear a yarn audit finding can jump a transitive dep to a new (incompatible) major; pin the EXACT advisory-patched version instead.
---

# A `">=X"` audit-fix resolution resolves to the HIGHEST match — often a new major

When clearing a `yarn audit` finding, copying the advisory's "Patched in
`>=A.B.C`" string straight into `resolutions`/`overrides` is a trap. yarn
satisfies a `>=` floor with the **highest** available version, so a floor
like `brace-expansion: ">=2.0.3"` does NOT land on 2.0.3 — it jumps to the
latest major (e.g. 5.x). If that major changed its module/export shape, a
transitive consumer that does `const x = require('pkg')` gets a non-function
and crashes at runtime/build/lint.

Real incident: `brace-expansion: ">=2.0.3"` -> 5.0.6, whose export is no
longer a bare function, so minimatch's `braceExpand` threw
`TypeError: expand is not a function` and CI eslint died.

**Fix:** pin the EXACT advisory-patched version within the major the tree
already uses (here `"brace-expansion": "2.0.3"`), in BOTH `resolutions` and
`overrides`. Confirm that version is still the expected module type
(`npm view <pkg>@<ver> type main exports` — empty `type` + `main: index.js`
= CJS function export) before trusting it.

**Why:** the advisory floor only tells you the *minimum* safe version, not
which major your consumers' API expects. The public API can be stable across
two majors (brace-expansion `expand(str)` is identical in 1.x and 2.x) but
break in a later one.

**How to apply:** after a `>=`-style resolution, `rg "^\"?<pkg>@" yarn.lock`
— if the resolved `version` is a higher major than the consumers request,
re-pin to the exact patched version in the consumers' major. Note 2.0.2 was
NOT enough here: the advisory's patched floor for the 2.x line was 2.0.3, so
2.0.2 still flagged. Match the advisory floor exactly, no lower.
