---
name: Playwright e2e ESM __dirname trap
description: Why __dirname can be undefined inside Playwright TS test/fixture files, and how to catch it offline before a browser run.
---

Playwright decides ESM-vs-CJS per file by the NEAREST `package.json` `"type"`.
A test dir with its own `package.json` containing `"type": "module"` (e.g. a
dedicated e2e package) makes Playwright load the config/fixtures/specs as native
ES modules — where `__dirname` and `__filename` are **undefined** and throw
`ReferenceError: __dirname is not defined in ES module scope` at module load.
That kills the WHOLE suite ("No tests found", Total: 0), not just one spec.

**Why:** the outer app `package.json` may be CJS (no `type`), so `__dirname`
"works everywhere else"; the e2e subpackage's own `type: module` is the override
that bites only the e2e files.

**How to apply:**
- For a dir path inside an ESM Playwright file, derive it the same way `.mjs`
  helpers do: `path.dirname(fileURLToPath(import.meta.url))`. Do NOT use bare
  `__dirname`. (`process.cwd()` is cwd-fragile across invocation dirs.)
- If a `tsconfig.json` for that e2e dir still says `module: commonjs`, it
  contradicts the runtime and makes `import.meta` a tsc error — set it to
  `esnext` to match reality.
- Verify offline WITHOUT browsers: `npm install --no-save @playwright/test` then
  `MOBILE_E2E_BASE_URL=… npx playwright test --config=… --list`. `--list`
  evaluates fixtures at import time, so it surfaces the ESM load error in
  seconds. A green `--list` (N tests in M files, exit 0) proves the modules load.
- Standalone `tsc` on the e2e dir will also error `Cannot find module
  '@playwright/test'` if deps aren't installed locally — that's an env artifact
  of the standalone run, NOT a code regression; Playwright's own loader resolves
  it at runtime. Trust `--list`, not standalone tsc, for e2e load health.
