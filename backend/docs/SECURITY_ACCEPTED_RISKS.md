# Frontend Dependency — Accepted Security Risks

## Decision Date: 2026-03-28 (Updated: 2026-03-23)
## Decision: All frontend vulnerabilities resolved via CRA→Vite migration + yarn resolutions
## CI Gate: `yarn audit --level high` (passes with 0 high, 0 critical, 0 moderate, 0 low)

---

## Current State: 0 Vulnerabilities

After CRA→Vite migration and yarn resolutions, all frontend vulnerabilities are resolved.
- **Original:** 87 vulnerabilities (2026-03-27 baseline)
- **After direct upgrades:** 29 vulnerabilities (2026-03-27)
- **After Bucket 1 resolutions:** 14 vulnerabilities (2026-03-28)
- **After CRA→Vite migration:** 2 vulnerabilities (2026-03-23, eslint ajv only)
- **After ajv resolution (post-CRA removal):** 0 vulnerabilities (2026-03-23)

---

## Resolution History

### Phase 1: Direct Dependency Upgrades (2026-03-27)
- jspdf, axios, react-router-dom, socket.io-client upgraded
- 87 → 29 vulnerabilities

### Phase 2: Bucket 1 yarn resolutions (2026-03-28)
- lodash, qs, postcss, diff, @eslint/plugin-kit resolved
- 29 → 14 vulnerabilities
- ajv resolution attempted & reverted (CRA incompatible)

### Phase 3: CRA → Vite Migration (2026-03-23)
- Removed `react-scripts` and `@craco/craco` (source of 12/14 remaining vulns)
- Migrated to Vite 8.0.1 with @vitejs/plugin-react 6.0.1
- 14 → 2 vulnerabilities

### Phase 4: ajv Resolution (2026-03-23)
- Added `ajv >= 6.14.0` resolution (now works without CRA blocking)
- 2 → 0 vulnerabilities

---

## References
- CHANGELOG.md: Full timeline of security work
- CI gate: `.github/workflows/ci-cd.yml` → `yarn audit --level high`
