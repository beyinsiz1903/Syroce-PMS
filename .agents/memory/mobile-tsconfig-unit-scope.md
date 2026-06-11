---
name: Mobile tsconfig.unit.json scope
description: Why type-checking with tsconfig.unit.json silently skips app code
---
`mobile/tsconfig.unit.json` has an explicit `include` of only a handful of pure-util files (datePickerUtils, availabilityFilters, availabilityGrid + their tests) with `rootDir: src`. Running `npx tsc -p tsconfig.unit.json --noEmit` exits 0 even when `app/` screens or `src/api/*` have type errors — it never compiles them.

**Why:** it exists to typecheck the Vitest-style unit subset fast, not the whole Expo app.

**How to apply:** to validate new screens/components/api modules, run `npx tsc -p tsconfig.json --noEmit` (the Expo project config, `include: **/*.ts(x)`). Use tsconfig.unit.json only for the unit-test util subset.
