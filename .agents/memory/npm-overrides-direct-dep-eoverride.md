---
name: npm overrides for a direct dep must use $name ($EOVERRIDE breaks npx)
description: Why a yarn-managed repo that keeps resolutions+overrides in lockstep can still break npx/npm with EOVERRIDE, and the fix.
---

# An npm `overrides` entry for a package you ALSO depend on directly throws EOVERRIDE

This repo keeps yarn `resolutions` and npm `overrides` in lockstep (every
resolution mirrored as an override) so npm-based consumers get the same
security pins. Yarn 1.x ignores `overrides`, so this is invisible during
normal `yarn install`. But anything that shells out to **npm/npx** parses
`overrides` and enforces a rule yarn does not:

> a package that appears in BOTH `dependencies`/`devDependencies` AND
> `overrides` must reference the direct dep via `$<name>`; a plain range
> there is rejected as `EOVERRIDE: Override for X conflicts with direct
> dependency`.

Real incident: CI e2e served the build with `npx --yes serve -s build -l
3000`. postcss was a direct devDep (`^8.5.10`) and also an override
(`>=8.5.10`) -> npx died with EOVERRIDE, nothing bound :3000, and every
Playwright UI spec failed `net::ERR_CONNECTION_REFUSED`. The CI serve
wait-loop (`for i in 1..20; curl; done`) does NOT fail the step, so the
real cause only surfaced one step later at e2e time.

**Fix:** for the colliding package only, set the npm override value to
`"$<name>"` (e.g. `"postcss": "$postcss"`). npm then pins all nested copies
to the resolved direct-dependency version; yarn keeps using its own
`resolutions` range. Leave non-direct (transitive-only) overrides as
ranges.

**How to apply:** find collisions with
`node -e 'const p=require("./package.json");const d={...p.dependencies,...p.devDependencies};console.log(Object.keys(p.overrides||{}).filter(k=>d[k]))'`
then switch each listed key's override to `$<key>`. Verify with a real
`npx --yes serve ...` (or any npx that triggers an install) — yarn-only
checks will NOT catch EOVERRIDE.
