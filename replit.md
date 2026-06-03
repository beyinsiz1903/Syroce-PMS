# Syroce PMS

An enterprise-grade, multi-tenant Hotel Property Management System with AI-powered features adaptable to any accommodation type.

## Run & Operate

- **Frontend**:
  - Install dependencies: `cd frontend && yarn install`
  - Start dev server: `cd frontend && yarn run start`
  - Build for deployment: `cd frontend && yarn build`
- **Backend**:
  - Start services (MongoDB, Redis, FastAPI): `bash backend/start.sh`
- **Environment Variables**: `JWT_SECRET`, `RESEND_API_KEY`, `SENTRY_DSN`, `VITE_SENTRY_DSN`, `QUICKID_SERVICE_KEY`, `QUICKID_URL`, `ENABLE_QUICKID_DEMO`, `ROOM_QR_SECRET`, `PUBLIC_APP_URL`, `AFSADAKAT_BASE_URL`, `AFSADAKAT_ADMIN_TOKEN`, `ENABLE_SETUP_ENDPOINTS`, `SETUP_SECRET`, `EXELY_IP_WHITELIST`, `EXELY_TRUST_FORWARDED`, `EXELY_TRUSTED_PROXY_IPS`, `JWT_EXPIRATION_MINUTES`, `REFRESH_TOKEN_EXPIRATION_DAYS`, `DISABLE_EXPO_PUSH`, `MOBILE_PUSH_SCAN_SECONDS`, `MOBILE_PUSH_VIP_WINDOW_MINUTES`, `KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`, `ATLAS_TIER`, `SENTRY_ENVIRONMENT`, `GRAPHQL_INTROSPECTION` (default off in prod/stress; explicit `true` opt-in for local), `ENABLE_GUEST_ANONYMIZATION` (fail-closed; `1` enables KVKK guest anonymize endpoint), `HOTELRUNNER_WEBHOOK_SECRET` + `ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK` (webhook HMAC signing; dev escape), `EXELY_TEST_WEBHOOK_AUTH_MODE` (`open_for_testing` = fail-closed multi-condition stress/E2E-only Exely IP-allowlist bypass; requires non-prod + `E2E_EXTERNAL_DRY_RUN=true` + `E2E_ALLOW_DESTRUCTIVE_STRESS=true` + `E2E_STRESS_TENANT_ID`; prod stays 503).

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

Detaylı gotcha kayıtları, dosya/satır referansları ve tarihçe → **`docs/GOTCHAS.md`**. REVIEW/SKIP Zeroing (Wave 6–9) + REVIEW/SKIP Reduction (Package A+B→F) uzun detayları → **`docs/ops/REVIEW_SKIP_ZEROING_GOTCHAS.md`**. Aşağıda her always-on bölümün tek-satırlık özeti:

- **Testing** — `frontend/e2e-business/` (20 spec, business-flow, pilot'a koşar, dış servisler SKIP) + `frontend/e2e-smoke/` (24 route × 2 viewport = 48 navigate test). Komutlar: `yarn test:e2e:business`, `yarn test:e2e:smoke`. Env zorunlu: `E2E_BASE_URL`/`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`.
- **Conventions (always-on)** — axios `/api/` YOK, fetch `/api/` VAR · `purple→indigo`/`orange→amber` · `lib/dialogs.js` (native alert/confirm değil) · walk-in misafir adı placeholder rewrite · image upload strict validation · outbound HTTP DNS-rebind safe + IP allowlist.
- **Auth, security & infra** — JWT 7gün override · Redis pub/sub auth invalidation + WS CB · Mongo Atlas 500-koleksiyon limiti workaround · Night Audit N+1 fix · HotelRunner pull retries (manual=3, scheduled=2) · Exely webhook IP allowlist literal (CIDR DEĞİL) + `verify_exely_whitelist.py`.
- **Design system & layout** — Sprint A: `<PageHeader>`/`<KpiCard intent>`/`<StatusBadge>`, Yenile=outline+RefreshCw, primary CTA siyah, emoji yok (ReservationCalendar amber bilinçli istisna) · M5 Layout wrap: routes own `wrapLayout+layoutModule`, page YOK; `yarn guard:layout` regression guard.
- **Hardening series (DONE)** — CM-Hardening (`docs/adr/2026-05-cm-hardening.md`): Conflict Queue + Bulk Resolve, No-Show OTA Outbox Parity, Stop-Sale CB per-connection (Exely no-show parity #3c DEFERRED). Production Hardening (`docs/adr/2026-05-production-hardening.md`): no-show terminal-state guard + inventory lock release, closed-folio refund/void guard.
- **Production Safety Pack (8/8 DONE)** → `docs/PRODUCTION_SAFETY_PLAN.md`, operatör entry `docs/REPLIT_OPS_CHEATSHEET.md`, prova `docs/PRODUCTION_LAUNCH_REHEARSAL.md`: rollback · Atlas-managed backup · CM observability single-source · Sentry alert+PII scrub · Admin pilot section · feature-flag std · 24h monitoring runbook · OPS cheat-sheet.
- **E2E pilot residue sweep** — `backend/scripts/cleanup_e2e_pilot_residue.py` 24+ saatlik `E2E_` prefix'li bookings/guests/folio_charges listeler (dry-run default), `--apply` ile bookings→cancelled + charges→voided=true. Guard'lar: `E2E_PILOT_TENANT_ID` zorunlu + `--apply` için `E2E_ALLOW_PILOT_CLEANUP=true` (fail-closed). `e2e_residue_scans` metric row, `found_total>0 → rc=1` cron alerting için. Test: `backend/tests/test_cleanup_e2e_pilot_residue.py`.
- **Stress CRM residue sweep** — `backend/scripts/cleanup_stress_crm_residue.py` 24+ saatlik `E2E_`/`E2E_STRESS_*` prefix'li `corporate_contracts` + `mice_accounts` (stress tenant) listeler (dry-run default), `--apply` ile **HARD DELETE** (soft-deactivate global unique index'i serbest bırakmaz — colliding `rate_code`/`contact_email`/`tax_no`/`email` değerleri kalır, backstop kapalı kalır). Guard'lar: `E2E_STRESS_TENANT_ID` zorunlu + pilot UUID/`PILOT_TENANT_ID` eşitse refuse (pilot_drift=0) + `--apply` için `E2E_ALLOW_STRESS_CLEANUP=true` (fail-closed). `stress_crm_residue_scans` metric row, `found_total>0 → rc=1` cron alerting için. Test: `backend/tests/test_cleanup_stress_crm_residue.py`.
- **F8 Stress Test Series** — Faz tarihçesi, spec listesi, module-blocked doctrine, helper konvansiyonları, F8R–F8AH detayları → `docs/GOTCHAS.md` "F8 Stress Test Series" + "F8 Stress Test Series — Spec History" bölümleri. Roadmap (tek doğruluk kaynağı): `docs/STRESS_TEST_ROADMAP.md`.

## Stress / REVIEW-SKIP Reduction — Current State

- **Mevcut baseline (tek kaynak):** **Run #194 GREEN BASELINE** (2026-06-03, commit `9f4b3a74d894f52464e2f0f6a0037387df58f636`, run ID 26869789889, job ID 79241995727, event=schedule) — 708 test, status=Success (conclusion=success), failedTests=0, PASS/FAIL/REVIEW/SKIP=1565/0/17/11, P0=P1=0, P2=24 / P3=0, external_calls=[], pilot_drift=0, cleanup#2 idempotent=true, verdict **GO WITH WATCH**. #190→#194 delta: PASS +94, REVIEW −4, SKIP −33, P2 −6, P3 −2 (folio detail + audit timeline + folio activities/operations 500 fix; folio-mass void + HR modülleri + settings_audit artık temiz koşuyor); FAIL/P0/P1 sabit 0, regresyon yok. Seed total=26097.7ms eski 30s eşiğini de geçer → #194 yeşili budget 30s→45s değişikliğine BAĞLI DEĞİL. Provenance GitHub API `digest`'inden doğrulandı, fabrike EDİLMEDİ (artifact ZIP gövdesi auth-gated 401 → gövde REVIEW-toplamı satır-satır re-türetilmedi; tutarlılık granülarite-modeli + #190 §5 + operatör-transkript'e dayanır). Drill: `docs/drill_reports/20260603_stress_full_stress_suite_GREEN_708test_run194.md`. Tam baseline zinciri + provenance (#194 current; #190/#184/#171/#170/#168/#167/#162/#161/#159/#143 historical) → **`docs/baselines/BASELINE_CHAIN.md`**. **Kapsam notu:** bu web/backend full stress suite baseline'ıdır, /100 uygulama kapsamı DEĞİLDİR — mobile/F10 ayrı ve açık (doğrulanmadı); merkezi referans `docs/TEST_COVERAGE_SCORECARD_100.md`.
- **Doktrin (her fazda mutlak):** no fake-green · no RBAC weakening · no auth weakening · no PII exposure · no pilot mutation (pilot_drift=0) · external_calls=[] · failedTests=0 · P0=P1=0 · assertion gevşetme YOK · skip-as-pass YOK · kör-seed YASAK · gerçek UI failure'ı REVIEW'a düşürme YOK · gerçek başarısız UI path'i sayım azaltmak için skip etme YOK · verdict ≥ GO WITH WATCH · düz "GO" veya "/100" iddiası YOK · mobile/F10 ayrı. Agent full stress dispatch EDEMEZ; doğrulama targeted pytest / `node --check` / canlı read-only probe ile CI-deferred.
- **Açık sayımlar (Run #194 current baseline):** P2=24, REVIEW=17, SKIP=11, P3=0.
- **Tamamlanan paketler (REVIEW/SKIP Reduction; detay → `docs/drill_reports/20260530_review_skip_packages_ab_to_f_summary.md` + `docs/ops/REVIEW_SKIP_ZEROING_GOTCHAS.md`):**
  - **A+B** — ENV/posture + güvenli seed/data-state. Tek kod: Exely çok-koşullu fail-closed test-auth gate + spec idempotency stress vardiya self-open.
  - **C** — Ürün-sözleşme/uyum. Tek kod: e-Fatura `_normalize_customer_tax_number` parite (VKN/TCKN).
  - **D** — Endpoint/surface/module-blocked. Tek güvenli düzeltme: cross-tenant pentest messaging path-drift (`/messaging/messages`→`/conversations`).
  - **E** — Seed/data-state/harvest. Tek güvenli düzeltme: folio-mass void harvest window (`slice(10,15)`).
  - **F** — Frontend/UI selector & render. Tek güvenli düzeltme: housekeeping render spec route+selector drift (`/housekeeping`→`/housekeeping-status`, `room-card-*`/`status-btn-*`).
- **Sıradaki adım:** Run #194 full stress (schedule) KOŞTURULDU + provenance CI/GitHub API'dan doğrulandı (run/job/artifact digest'leri, conclusion=success) → **GREEN GO WITH WATCH** promote edildi (current baseline); #190 historical'a indi. Rapor tutarlılığı: Murat'ın 3 maddesi (settings_audit "audit marker not found", reservation_deep waitlist/city-ledger, finance_folio 409) granülarite-artefaktı / legitimate harness annotation (modül-tablosu adım ekseni ≠ severity-triage ekseni), stale carryover DEĞİL — drill §5. Yöntem dürüstlüğü: artifact gövdesi auth-gated, gövde re-sum CI-deferred. Sıradaki açık WATCH adayları: night audit unresolved (200), backup posture, housekeeping soft cold-boot TTI, HR audit 500 (kalan), activity-feed PII, digital-key 404, rate-limit burst 429, full_24h data scarcity. Sıradaki seçenek: mobile/F10 baseline (ayrı ve açık, doğrulanmadı). Full stress agent tarafından dispatch EDİLMEZ.

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
