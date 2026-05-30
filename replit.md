# Syroce PMS

An enterprise-grade, multi-tenant Hotel Property Management System with AI-powered features adaptable to any accommodation type.

## Run & Operate

- **Frontend**:
  - Install dependencies: `cd frontend && yarn install`
  - Start dev server: `cd frontend && yarn run start`
  - Build for deployment: `cd frontend && yarn build`
- **Backend**:
  - Start services (MongoDB, Redis, FastAPI): `bash backend/start.sh`
- **Environment Variables**: `JWT_SECRET`, `RESEND_API_KEY`, `SENTRY_DSN`, `VITE_SENTRY_DSN`, `QUICKID_SERVICE_KEY`, `QUICKID_URL`, `ENABLE_QUICKID_DEMO`, `ROOM_QR_SECRET`, `PUBLIC_APP_URL`, `AFSADAKAT_BASE_URL`, `AFSADAKAT_ADMIN_TOKEN`, `ENABLE_SETUP_ENDPOINTS`, `SETUP_SECRET`, `EXELY_IP_WHITELIST`, `EXELY_TRUST_FORWARDED`, `EXELY_TRUSTED_PROXY_IPS`, `JWT_EXPIRATION_MINUTES`, `REFRESH_TOKEN_EXPIRATION_DAYS`, `DISABLE_EXPO_PUSH`, `MOBILE_PUSH_SCAN_SECONDS`, `MOBILE_PUSH_VIP_WINDOW_MINUTES`, `KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`, `ATLAS_TIER`, `SENTRY_ENVIRONMENT`, `GRAPHQL_INTROSPECTION` (default off in prod/stress; explicit `true` opt-in for local), `ENABLE_GUEST_ANONYMIZATION` (fail-closed; `1` enables KVKK guest anonymize endpoint), `HOTELRUNNER_WEBHOOK_SECRET` + `ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK` (webhook HMAC signing; dev escape).

## Stack

- **Frontend**: React 19, Vite 8, Tailwind CSS, shadcn/ui, TanStack Query v5, React Router v7, i18next, Yarn 1.22.22, Vitest.
- **Backend**: FastAPI (Python 3.11+), MongoDB 7.0+ (motor), Redis, Celery, pytest.
- **Auth**: JWT, AES-256-GCM, RBAC.

## Where things live

- `frontend/`: React + Vite application.
- `backend/`: FastAPI Python application (contains `bootstrap/`, `channel_manager/`, `controlplane/`, `core/`, `domains/`, `modules/`, `workers/`).
- `infra/`: Prometheus/Grafana/K8s config.
- `deploy/`: Deployment scripts (`rollback.sh`, `smoke.sh`, `deploy.sh`).
- `docs/`: ADRs and playbooks (pilot operator entry point: `docs/REPLIT_OPS_CHEATSHEET.md`).
- **Key Files**:
  - DB Schema: `backend/models/schemas/` (Pydantic models).
  - API Contracts: `backend/routers/`, `backend/domains/*/router.py`.
  - Theme Files: `frontend/tailwind.config.js`.

## Architecture decisions

- **Multi-tenant Architecture**: Isolated data sets per hotel enforced by `tenant_id` scoping.
- **Property Type Profiling System**: Dynamic configuration of modules and features based on property type.
- **Atomic Operations**: Critical workflows use MongoDB transactions or unique compound indexes for atomicity.
- **Security-First Development**: Robust defenses against common web vulnerabilities.
- **Event-Driven Integrations**: Syroce Xchange (SXI) bus for reliable, idempotent event distribution with SSRF protection.
- **Fail-Closed Principle**: Security-critical configurations default to fail-closed, preventing insecure operation if not properly configured.

## Product

- **Core PMS**: Front desk, reservations, housekeeping, financial folios, guest management.
- **AI Integration**: Upsell offers, dynamic pricing, forecasting, no-show risk, guest pattern analysis.
- **Channel Management**: Unified Rate Manager, OTA sync (Exely, HotelRunner), SXI bus.
- **Financial Operations**: Cashier module, PCI-DSS, automated Turkish Accommodation Tax, Procurement.
- **Guest Experience**: Room QR requests, guest reviews & NPS, digital key, mobile apps.
- **Operational Efficiency**: Spa & MICE, shift handover, in-app help, regulatory reports.
- **Security & Compliance**: 2FA/TOTP, KVKK/GDPR, audit logging, Quick-ID.

## User preferences

_Populate as you build_

## Gotchas

Detaylı gotcha kayıtları, dosya/satır referansları ve tarihçe → **`docs/GOTCHAS.md`**. Aşağıda her bölümün tek-satırlık özeti:

- **Testing** — `frontend/e2e-business/` (20 spec, business-flow, pilot'a koşar, dış servisler SKIP) + `frontend/e2e-smoke/` (24 route × 2 viewport = 48 navigate test). Komutlar: `yarn test:e2e:business`, `yarn test:e2e:smoke`. Env zorunlu: `E2E_BASE_URL`/`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`.
- **Conventions (always-on)** — axios `/api/` YOK, fetch `/api/` VAR · `purple→indigo`/`orange→amber` · `lib/dialogs.js` (native alert/confirm değil) · walk-in misafir adı placeholder rewrite · image upload strict validation · outbound HTTP DNS-rebind safe + IP allowlist.
- **Auth, security & infra** — JWT 7gün override · Redis pub/sub auth invalidation + WS CB · Mongo Atlas 500-koleksiyon limiti workaround · Night Audit N+1 fix · HotelRunner pull retries (manual=3, scheduled=2) · Exely webhook IP allowlist literal (CIDR DEĞİL) + `verify_exely_whitelist.py`.
- **Design system & layout** — Sprint A: `<PageHeader>`/`<KpiCard intent>`/`<StatusBadge>`, Yenile=outline+RefreshCw, primary CTA siyah, emoji yok (ReservationCalendar amber bilinçli istisna) · M5 Layout wrap: routes own `wrapLayout+layoutModule`, page YOK; `yarn guard:layout` regression guard.
- **Hardening series (DONE)** — CM-Hardening (`docs/adr/2026-05-cm-hardening.md`): Conflict Queue + Bulk Resolve, No-Show OTA Outbox Parity, Stop-Sale CB per-connection (Exely no-show parity #3c DEFERRED). Production Hardening (`docs/adr/2026-05-production-hardening.md`): no-show terminal-state guard + inventory lock release, closed-folio refund/void guard.
- **Production Safety Pack (8/8 DONE)** → `docs/PRODUCTION_SAFETY_PLAN.md`, operatör entry `docs/REPLIT_OPS_CHEATSHEET.md`, prova `docs/PRODUCTION_LAUNCH_REHEARSAL.md`: rollback · Atlas-managed backup · CM observability single-source · Sentry alert+PII scrub · Admin pilot section · feature-flag std · 24h monitoring runbook · OPS cheat-sheet.
- **E2E pilot residue sweep (Task #178)** — `backend/scripts/cleanup_e2e_pilot_residue.py` 24+ saatlik `E2E_` prefix'li bookings/guests/folio_charges listeler (dry-run default), `--apply` ile bookings→cancelled + charges→voided=true. Guard'lar: `E2E_PILOT_TENANT_ID` zorunlu + `--apply` için `E2E_ALLOW_PILOT_CLEANUP=true` (fail-closed). `e2e_residue_scans` metric row, `found_total>0 → rc=1` cron alerting için. Test: `backend/tests/test_cleanup_e2e_pilot_residue.py`.
- **REVIEW/SKIP Zeroing — Wave 6 (env/secret/test posture)** — Hedef 5 alanda backend kodu zaten fail-closed/doğru; REVIEW'lar stres env posture eksiği (bug değil). Repo: `stress.yml` runner-side `HOTELRUNNER_WEBHOOK_SECRET = secrets.STRESS_HOTELRUNNER_WEBHOOK_SECRET` (unset → spec honest REVIEW). Operatör (repl dışı, devops): stres backend AYNI secret + `EXELY_IP_WHITELIST`/`ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1` (yalnız stres) + `KBS_TEST_MODE=1` + `GRAPHQL_INTROSPECTION=false`. PROD gerçek secret/whitelist; fail-closed korunur. Runbook+validation: `docs/drill_reports/20260529_review_skip_wave6_candidate.md`; envanter: `docs/drill_reports/20260529_review_skip_zeroing_inventory.md`. Baseline #162 pointer TAŞINMAZ; targeted spec PASS CI-deferred.
- **F8 Stress Test Series** — Faz tarihçesi, spec listesi, module-blocked doctrine, helper konvansiyonları, F8R–F8AH detayları → `docs/GOTCHAS.md` "F8 Stress Test Series" + "F8 Stress Test Series — Spec History" bölümleri. Roadmap (tek doğruluk kaynağı): `docs/STRESS_TEST_ROADMAP.md`. **✅ GREEN BASELINE (2026-05-29, Run #162, commit `bde7662744c9b94a5c9294fa778202d813319dfc`)**: 702 test, duration 3576.2s (~59m 36s), status=Success, failedTests=0, PASS/FAIL/REVIEW/SKIP=1316/0/46/61, P0=P1=0, P2=60 / P3=1 informational, external_calls=[], pilot_drift=0, cleanup idempotent (7756→0), verdict **GO WITH WATCH**. Wave 1–5 P2/REVIEW cleanup candidate'i doğrular (test-only + docs + C420 lint fix; prod davranış değişikliği yok; cleanup etkisi REVIEW 48→46, P2 65→60). Run URL: https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26653464472 (run #162, run ID 26653464472, job ID 78557501168, branch main). Artifacts: stress-drill-report (ID 7298692917, sha256:ca8a84b03c07972ad70024284082f5f93d69f779ea441d21103dd24e6d266d28) + playwright-stress-report (ID 7298692578, sha256:89f2e67d44099ba6ce603c1c5c4fd92bdee33966e7bd3b8c84b1e59c7939be07). Drill: `docs/drill_reports/20260529_stress_full_stress_suite_GREEN_702test.md`. **Kapsam notu: bu web/backend full stress suite baseline'ıdır, /100 uygulama kapsamı DEĞİLDİR — mobile/F10 ayrı ve açık (doğrulanmadı); merkezi referans `docs/TEST_COVERAGE_SCORECARD_100.md`.** Önceki baseline (historical reference): 2026-05-29, Run #161, 702 test, commit `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`, P2=65/REVIEW=48/P3=1, GO WITH WATCH, run URL https://github.com/beyinsiz1903/emergent-yeni-uygulama/actions/runs/26641150604 (run ID 26641150604, job ID 78514272098), artifacts stress-drill-report ID 7293609890 + playwright-stress-report ID 7293609632, provenance+metrics drill comparison block'ta korunmuştur (`docs/drill_reports/20260529_stress_full_stress_suite_GREEN_702test.md`). Daha eski (older historical reference): 2026-05-28, Run #159, 702 test, commit `e23a4ec603cc32984b741d77d67d57a0abba698b`, P2=65/P3=1, GO WITH WATCH, drill `docs/drill_reports/20260528_stress_full_stress_suite_GREEN_702test.md`. En eski (oldest historical reference): 2026-05-26, Run #143, 84 spec / 556 test, commit `3b3891d`, P2=60/P3=1, GO WITH WATCH — F8AH iki-tur kapatma: Tur 1 (commit `94514e6`) 4 P1 (konaklama amount/nights Pydantic `le=1e9/3650`, KDS terminal-state 409, KDS idempotency Mongo unique + 503); Tur 2 (commits `147266d4` + `67374954` + `8f7f77b6`) P0 TWOFA throttle — Mongo-backed cross-instance throttle (`backend/security/auth_throttle.py`) + per-user_id layered throttle (`backend/routers/auth.py:720-732`, JWT-trusted, IP rotation immune, `consumed_jtis` insert ÖNCESI). Drill: `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md`. Coverage gap: `docs/STRESS_COVERAGE_GAP_REPORT_20260526.md`. Mutlak kurallar her fazda: pilot mutation=0, external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH, assertion gevşetme YOK, skip-as-pass YOK.

## Closing note — 2026-05-26 baseline stabilization

Run #143 official 84-spec GO WITH WATCH baseline stabilized. Stale T001–T006 plan retired. P2/REVIEW triage moved to §11 pre-pilot decision matrix (`docs/STRESS_P2_REVIEW_TRIAGE_20260526.md`). Sentry worker noise reduction completed with `TransientFailureTracker` across 11 workers (architect Round-2 PASS, commit `6f48e71`). Bu noktadan sonra yeni faz ayrı başlık altında açılacak: **Pilot Onboarding Pack · MUST CLOSE PC1–PC4 Sprint · Sales/Investor Readiness Pack**.

## Pointers

- **FastAPI Documentation**: [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)
- **React Documentation**: [React Docs](https://react.dev/learn)
- **MongoDB Documentation**: [MongoDB Manual](https://www.mongodb.com/docs/manual/)
- **Redis Documentation**: [Redis Docs](https://redis.io/docs/)
- **Celery Documentation**: [Celery User Guide](https://docs.celeryq.dev/en/stable/userguide/index.html)
- **Tailwind CSS**: [Tailwind CSS Docs](https://tailwindcss.com/docs)
- **shadcn/ui**: [shadcn/ui Docs](https://ui.shadcn.com/)
- **TanStack Query**: [TanStack Query Docs](https://tanstack.com/query/latest)
- **React Router**: [React Router Docs](https://reactrouter.com/en/main)
- **i18next**: [i18next Docs](https://www.i18next.com/overview/getting-started)
- **Vitest**: [Vitest Docs](https://vitest.dev/guide/)
- **pytest**: [pytest Docs](https://docs.pytest.org/en/stable/)
- **PCI DSS v4.0**: [PCI DSS Resources](https://www.pcisecuritystandards.org/document_library/)
- **RFC 6238 (TOTP)**: [RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238)
- **HTNG 2024B XML**: For Sabre SynXis integration.
- **OData V4 JSON**: For SAP S/4HANA integration.
