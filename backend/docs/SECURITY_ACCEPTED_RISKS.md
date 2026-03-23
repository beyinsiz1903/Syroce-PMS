# Frontend Dependency — Accepted Security Risks

## Decision Date: 2026-03-28
## Decision: Accept remaining low/moderate vulnerabilities; plan remediation
## CI Gate: `yarn audit --level high` (passes with 0 high, 0 critical)

---

## Current State: 14 Vulnerabilities (3 Low + 11 Moderate)

After Bucket 1 yarn resolutions (2026-03-28), reduced from 29 → 14. All remaining vulnerabilities are in **build-time toolchain** dependencies (`react-scripts`, `@craco/craco`). None affect production runtime. Resolution is only possible via CRA → Vite migration.

---

## Vulnerability Classification

### Bucket 1: RESOLVED via yarn resolutions (2026-03-28)

| Package | Status | Resolution Applied |
|---------|--------|--------------------|
| `lodash` | FIXED | `"lodash": ">=4.17.23"` |
| `qs` | FIXED | `"qs": ">=6.14.2"` |
| `postcss` | FIXED | `"postcss": ">=8.4.31"` |
| `diff` | FIXED | `"diff": ">=4.0.4"` |
| `@eslint/plugin-kit` | FIXED | `"@eslint/plugin-kit": ">=0.3.4"` |

**Note:** `ajv` resolution (`>=6.14.0`) was attempted but removed — breaks `ajv-keywords` v3 compatibility in CRA build chain. v6.14.0 does not exist in npm registry; fix only available in v8+ which is incompatible with CRA's webpack plugin chain.

### Bucket 2: CRA-Locked (Cannot resolve without migration)

| Package | Severity | Paths | Root Cause | Fix |
|---------|----------|-------|-----------|-----|
| `ajv` v6 | MODERATE | x4 | `react-scripts` internals | Requires CRA → Vite |
| `ajv` v8 | MODERATE | x5 | `webpack>terser-webpack-plugin`, `workbox-webpack-plugin` | Requires CRA → Vite |
| `webpack-dev-server` 4.x | MODERATE | x2 | CRA pins WDS 4.x | Requires CRA → Vite |
| `@tootallnate/once` | LOW | x3 | `jest>jsdom>http-proxy-agent` chain | Requires CRA → Vite |

---

## Risk Assessment

| Factor | Assessment |
|--------|-----------|
| **Runtime impact** | NONE — all vulns in build-time/dev-only packages |
| **Attack surface** | Build pipeline only, not accessible to end users |
| **Exploitability** | Low — requires crafted input to build tools, not production APIs |
| **Data risk** | NONE — no access to production data or credentials |

---

## Remediation Plan

### Short-term: DONE (2026-03-28)
- [x] Added `yarn resolutions` for Bucket 1 packages (lodash, qs, postcss, diff, @eslint/plugin-kit)
- [x] Result: 29 → 14 vulnerabilities (52% reduction)
- [x] `ajv` resolution attempted and reverted (CRA incompatible)

### Medium-term (Backlog)
- [ ] Evaluate `@craco/craco` removal (replaces with `react-app-rewired` or eject)
- [ ] Evaluate `react-scripts` 6.x upgrade path

### Long-term (Planned)
- [ ] CRA → Vite migration (eliminates all 14 remaining build-time vulnerabilities)
- [ ] Removes dependency on `webpack-dev-server`, old `jest`/`jsdom` chain, `@craco/craco`

---

## References
- Initial fix: 87 → 29 vulnerabilities (2026-03-27, see CHANGELOG.md)
- Bucket 1 fix: 29 → 14 vulnerabilities (2026-03-28, yarn resolutions)
- CI gate: `.github/workflows/ci-cd.yml` → `yarn audit --level high` (passes with 0 high, 0 critical)
- ADR-003 Note: Phase C delivery not blocked by these vulnerabilities
