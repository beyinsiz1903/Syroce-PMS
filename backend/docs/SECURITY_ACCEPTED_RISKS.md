# Frontend Dependency — Accepted Security Risks

## Decision Date: 2026-03-28
## Decision: Accept remaining low/moderate vulnerabilities; plan remediation
## CI Gate: `yarn audit --level high` (passes with 0 high, 0 critical)

---

## Current State: 29 Vulnerabilities (7 Low + 22 Moderate)

All remaining vulnerabilities are in **build-time toolchain** dependencies (`react-scripts`, `@craco/craco`, `eslint`). None affect production runtime.

---

## Vulnerability Classification

### Bucket 1: Patch ile Cozulur (Resolution/Patch Available)

| Package | Severity | CVE | Root Dependency | Patched Version | Remediation |
|---------|----------|-----|-----------------|-----------------|-------------|
| `lodash` 4.17.21 | MODERATE | CVE-2025-13465 | `@craco/craco`, `react-scripts` (8 paths) | >=4.17.23 | `yarn resolutions`: `"lodash": ">=4.17.23"` |
| `ajv` 6.12.6 | MODERATE | CVE-2025-69873 | `eslint`, `react-scripts` (3 paths) | >=6.14.0 | `yarn resolutions`: `"ajv": ">=6.14.0"` |
| `qs` 6.14.0 | MODERATE+LOW | CVE-2026-2391, CVE-2025-15284 | `react-scripts>webpack-dev-server>express` (4 paths) | >=6.14.2 | `yarn resolutions`: `"qs": ">=6.14.2"` |
| `postcss` <8.4.31 | MODERATE | N/A | `react-scripts>resolve-url-loader` (1 path) | >=8.4.31 | `yarn resolutions`: `"postcss": ">=8.4.31"` |
| `@eslint/plugin-kit` 0.2.8 | LOW | GHSA-xffm-g5w8-qvg7 | `eslint` (1 path) | >=0.3.4 | `yarn resolutions` or eslint upgrade |
| `diff` 4.0.2 | LOW | CVE-2026-24001 | `@craco/craco>cosmiconfig-typescript-loader>ts-node` (1 path) | >=4.0.4 | `yarn resolutions`: `"diff": ">=4.0.4"` |

### Bucket 2: Major Upgrade Ister

| Package | Severity | CVE | Root Dependency | Patched Version | Notes |
|---------|----------|-----|-----------------|-----------------|-------|
| `ajv` 8.x | MODERATE | CVE-2025-69873 | `react-scripts>@pmmmwh/*`, `react-scripts>webpack>terser-webpack-plugin`, `react-scripts>workbox-webpack-plugin` (4 paths) | >=8.18.0 | Requires webpack plugin chain upgrades |
| `webpack-dev-server` 4.x | MODERATE x2 | GHSA-* | `react-scripts` (2 advisories) | >=5.2.1 | CRA pins webpack-dev-server 4.x; major version requires CRA 6+ or eject |

### Bucket 3: Toolchain Migration Ister (CRA/react-scripts Cikmak Gerekir)

| Package | Severity | Root Cause | Long-term Fix |
|---------|----------|-----------|---------------|
| `@tootallnate/once` | LOW (3 paths) | `react-scripts>jest>jsdom` chain | Migrate to Vite or Next.js (eliminates CRA dependency tree) |
| `webpack-dev-server` | MODERATE (2 advisories) | CRA pins old WDS | Same — Vite eliminates webpack dependency |

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

### Short-term (Next Sprint)
- [ ] Add `yarn resolutions` for Bucket 1 packages (lodash, ajv v6, qs, postcss, diff, @eslint/plugin-kit)
- [ ] Estimate: ~30 min, reduces count from 29 to ~10

### Medium-term (Backlog)
- [ ] Evaluate `@craco/craco` removal (replaces with `react-app-rewired` or eject)
- [ ] Evaluate `react-scripts` 6.x upgrade path

### Long-term (Planned)
- [ ] CRA → Vite migration (eliminates all remaining build-time vulnerabilities)
- [ ] Removes dependency on `webpack-dev-server`, old `jest`/`jsdom` chain, `@craco/craco`

---

## References
- Previous fix: 87 → 29 vulnerabilities (2026-03-27, see CHANGELOG.md)
- CI gate: `.github/workflows/ci-cd.yml` → `yarn audit --level high`
- ADR-003 Note: Phase C delivery not blocked by these vulnerabilities
