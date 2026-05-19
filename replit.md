# Syroce PMS

An enterprise-grade, multi-tenant Hotel Property Management System with AI-powered features adaptable to any accommodation type.

## Run & Operate

- **Frontend**:
  - Install dependencies: `cd frontend && yarn install`
  - Start dev server: `cd frontend && yarn run start`
  - Build for deployment: `cd frontend && yarn build`
- **Backend**:
  - Start services (MongoDB, Redis, FastAPI): `bash backend/start.sh`
- **Environment Variables**: `JWT_SECRET`, `RESEND_API_KEY`, `SENTRY_DSN`, `VITE_SENTRY_DSN`, `QUICKID_SERVICE_KEY`, `QUICKID_URL`, `ENABLE_QUICKID_DEMO`, `ROOM_QR_SECRET`, `PUBLIC_APP_URL`, `AFSADAKAT_BASE_URL`, `AFSADAKAT_ADMIN_TOKEN`, `ENABLE_SETUP_ENDPOINTS`, `SETUP_SECRET`, `EXELY_IP_WHITELIST`, `EXELY_TRUST_FORWARDED`, `EXELY_TRUSTED_PROXY_IPS`, `JWT_EXPIRATION_MINUTES`, `REFRESH_TOKEN_EXPIRATION_DAYS`, `DISABLE_EXPO_PUSH`, `MOBILE_PUSH_SCAN_SECONDS`, `MOBILE_PUSH_VIP_WINDOW_MINUTES`, `KVKK_ID_PHOTO_ALERT_INTERVAL_SECONDS`, `ATLAS_TIER`, `SENTRY_ENVIRONMENT`.

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
- **CM-Hardening Series (DONE)** → `docs/adr/2026-05-cm-hardening.md` — Conflict Queue + Bulk Resolve, No-Show OTA Outbox Parity, Stop-Sale Circuit Breaker (per-connection); Exely no-show parity #3c DEFERRED.
- **Production Hardening Series (DONE)** → `docs/adr/2026-05-production-hardening.md` — No-show terminal-state guard, no-show inventory lock release, closed-folio refund/void guard.
- **Production Safety Pack (8/8 DONE)** → `docs/PRODUCTION_SAFETY_PLAN.md`, operatör entry: `docs/REPLIT_OPS_CHEATSHEET.md`, prova: `docs/PRODUCTION_LAUNCH_REHEARSAL.md`. Paketler: rollback · Atlas-managed backup · CM observability single-source · Sentry alert+PII scrub · Admin pilot section · feature-flag std · 24h monitoring runbook · OPS cheat-sheet.
- **E2E pilot residue sweep (Task #178)** — `backend/scripts/cleanup_e2e_pilot_residue.py`: pilot tenant'ta 24+ saatten eski `E2E_` prefix'li `bookings`/`guests`/`folio_charges` kayıtlarını listeler (dry-run default), `--apply` ile bookings→cancelled + charges→voided=true (guests rapor edilir, silinmez). Guard'lar: `E2E_PILOT_TENANT_ID` zorunlu (yoksa rc=2), `--apply` için ayrıca `E2E_ALLOW_PILOT_CLEANUP=true` (rc=2 fail-closed). Sonuç `e2e_residue_scans` koleksiyonuna metric row yazılır (`found_total>0 → rc=1` dry-run'da, cron alerting için). Test: `backend/tests/test_cleanup_e2e_pilot_residue.py` (5 case: env guard, apply guard, tenant/prefix/age filter, no-op cancel guard).
- **F8A Stress (tur-6 → tur-29e, DONE pending CI #47; tur-29e 2026-05-19: CI #46 NO-GO root cause = message-pattern eksikliği; `EventSyncService.handle_event` 0-connector durumda `{handled: True, sync_jobs_created: 0}` döner, dispatcher line 100'e düşüp `delivery_message="Dispatched: 0 sync jobs created"` yazar — mevcut `inert_patterns` bunu yakalamıyordu. Fix: pattern set genişletildi (`"dispatched: 0"`, `"no webhook url configured"`, `"missing creds"`). Env'den bağımsız. Structural-collapse layer defense-in-depth olarak korundu. Önceki turlar: tur-29 2026-05-19: CI #45 NO-GO — per-batch delta ÇALIŞTI, cascade YOK, ama 20 izole P0 göründü. Architect 3-iter review sonucu final fix: endpoint-level **per-source structural collapse** — CM gate `cm_connectors_lookup_ok && count==0 && !CM_PARTNER_WEBHOOK_URL_env` (raw env, module import değil); Afsadakat gate `afsadakat_tenants_lookup_ok && active_tenants_count==0` (env vars sadece diagnostic, per-tenant cred base_url override edebilir). Symmetric TRUE fail-open: her lookup exception → `lookup_ok=False` → gate False. Response additive: `inert_calls_filtered_by_no_connectors` + `structural_breakdown` per-source flags.)** → `docs/adr/2026-05-f8a-stress-evolution.md` — 4 spec × ~30 test + v2 push 2 yeni spec + 3 yeni test, 500-oda stress tenant. Day-turnover / room-move / folio-mass / housekeeping-mass + **reservation lifecycle (create/modify/cancel/no-show/overbooking/group/multi-room)** + **night-audit (business-date/run/idempotency/exceptions)** + **open-folio refund/void**. Son turlar: tur-20 RNL leak fix (checkout transaction'ında `release_booking_nights`), tur-21 perf fix (release call transaction içine), tur-22 OOO TOCTOU fix (`check_in_booking_atomic` + V1 `room_move` atomic CAS, `out_of_service` ROOM_BLOCKED_STATUSES'a eklendi), **tur-27 spec resilience**: (a) `callTimed`/`callTimedWithBackoff` `opts.timeout` desteği (heavy endpoint override), (b) 06-A NA `test.setTimeout(180s)` + per-call 120s + `status=0`→REVIEW+P1, (c) 04-C4 void `pickChargeId` field-name drift fallback (`id|_id|charge_id|chargeId|charge_uuid`) + `allNoCharge`→REVIEW+P2 (data-state ayrımı) + `detail_shape/charge_shape` diagnostic, (d) 05-A reservation create `first_fail_body` snapshot + `all_403`/`all_404`→REVIEW+P2 (module-blocked doctrine F8C/D/E mirror) + fail_modes assert message'a dahil. v2 push notları: spec 05 future dates +60..+90gün (seed çakışması yok), spec 06 RBAC short-circuit (`view_finance_reports` / `run_night_audit` 403 → P2 + REVIEW), spec 04 C3-C5 `void_charge` perm yoksa REVIEW (P2). F8A v2 backlog'ta CM outbox event consistency F8L'e devredildi (geri kalan tüm maddeler kapatıldı).
- **F8C Stress (MICE/Event/Banquet/Group, DONE — GO WITH WATCH after tur-5, 2026-05-18)** → `docs/adr/2026-05-f8c-stress-evolution.md` — 4 spec (14/15/16/17), 19-23 test, MICE & sales yüzeyleri. Seed: `_build_f8c_docs` (8 spaces + 30 events status=lead + 30 opportunities + 20 leads + 10 competitors + 3 packages). Dry-run invariants: events `definite` max (`completed` → folio post + bus.publish), opportunities lead→qualified→proposal→contract (won/lost yok). **module-blocked pattern** (tur-4 15-spec / tur-5 14-spec): endpoint 403 veya cache-stale ise `moduleBlocked=true` + P2 informational + A/B/C/D `test.skip()`, pilot_drift (E) çalışmaya devam — backend RBAC/cache durumları kasıtlı, spec resilience tercih edildi.
- **F8E Stress (Finance / Cashier / Accounting / Invoice / City Ledger, DONE v2 — GO WITH WATCH bekleniyor CI #42+, 2026-05-19)** → `docs/adr/2026-05-f8e-finance-stress-evolution.md` — 5 spec (24/25/26/27/**28**), 24 test (4 D-extension + 4 spec 28), cashier shift lifecycle + city-ledger + accounting CRUD + **finance reports (VAT/P&L/balance-sheet/dashboard/cash-flow) + currency lifecycle (rates+convert)**. v2 push notları: spec 28 RBAC-tolerant (hard floor = no-perm yüzeyler: VAT + currencies + cash-flow), `view_finance_reports` gate'li reports super_admin geçer ama perm_gated_fails ayrı raporlanır. E-fatura paths (`/efatura/*`, `/invoices/{id}/generate-efatura`) **YASAK** (gerçek GİB dispatch); bilinçli dışarıda. STRESS_COLLECTIONS += `currency_rates` (tenant-scoped orphan scrub). Seed: `_build_f8e_docs` (3 closed shift + 30 cashier_txn + 10 supplier + 20 expense + 10 invoice + 5 bank_acc + 15 item + 10 stock_movement + 20 cash_flow + 5 city_ledger). Dry-run guarantees: open-shift seed YOK (spec 24 kendi açar, `uniq_tenant_open_shift` partial index ihlali olmasın), Iyzico router seviyesinde tetiklenmiyor, folio_id + open shift gerektiren split-payment / mobile record-payment spec'lerde çağrılmıyor (F8A § 04 + F8E § 24 kapsamında). **module-blocked + RBAC short-circuit** desen (F8C/D mirror): `permFail === N` veya endpoint non-2xx ise P2 informational + A/B `test.skip()`, C pilot_drift bağımsız. STRESS_COLLECTIONS'a 11 yeni koleksiyon (`city_ledger_transactions` seed yok ama scrub var — forward-compat).
- **F8D Stress (HR / Staff / Shift / Leave / Department, DONE — GO WITH WATCH, CI yeşil, 2026-05-18)** → `docs/adr/2026-05-f8d-hr-staff-shift-evolution.md` — 4 spec (20/21/22/23), 19 test, HR yüzeyleri. Seed: `_build_f8d_docs` (5 dept + 8 pos + 30 staff + 30 leave_balance + 60 attendance + 20 shift + 5 leave_req + 5 swap + 3 perf). Dry-run guarantees: notifications in-app only (F8B cleanup kapsar), payroll `/finalize` ASLA çağrılmaz (live workflow için), attendance seed CLOSED (`clock_out` set) → spec clock-in yeni OPEN row açabilir, dept code prefix-isolated. **module-blocked + RBAC short-circuit** desen (F8C 14/15 mirror): `permFail === N` veya pool eksik ise P2 informational + A/B/C `test.skip()`, D pilot_drift bağımsız. STRESS_COLLECTIONS'a 10 yeni koleksiyon (payroll_records dahil — forward-compat orphan scrub).
- **F8B Stress (Guest Experience, GO WITH WATCH after tur-26)** → `docs/adr/2026-05-f8b-stress-evolution.md` — 4 spec (10/11/12/13), 22 test, QR/complaints/messaging yüzeyleri. Seed: `_build_f8b_docs` (room_qr_requests + service_complaints + messages + notifications). Dry-run guarantees: complaint `guest_id=None` → Resend silent; messaging sadece `/api/messaging/send-*` (legacy provider'a dokunmaz); folio adjustment lokal. Helper: `callTimedWithBackoff` (429 retry, fallbackSleepMs cap 15s). Workflow timeout 15→30dk.
- **Full Stress Suite F8A–F8N** — F8A–F8E yeşil baseline (24 spec, ~120 test); F8F–F8N planlı (Task #192-#201). Yüksek risk yüzeyleri: public/KVKK (F8K), CM webhook (F8L), GraphQL/B2B (F8M), RBAC (F8I). Ortak helper: `assertPilotDriftZero`, `assertPiiMasked`, `withModuleProbe` (`frontend/e2e-stress/fixtures/stress-helpers.js`).
- **Stress Test Roadmap (F8 serisi, tek doğruluk kaynağı)** → `docs/STRESS_TEST_ROADMAP.md` — F8A/B/C/D **DONE v1** · F8E **DONE v2** (tur-6, 24 test) · F8F/G/H/I/J planlı. **F8 Stress roadmap expanded with HR, guest-facing, CM/webhook, GraphQL/B2B, and reservation lifecycle deep phases.** Yeni fazlar: F8K (Guest-facing public flows / online check-in / NPS / digital key / KVKK), F8L (Channel Manager + Webhooks / Exely IP / HotelRunner sig / SXI bus / outbox idempotency), F8M (GraphQL + B2B API / tenant isolation / API key scope), F8N (Reservation lifecycle deep / create-modify-cancel-no-show-group-overbooking-waitlist). F8D v2 backlog: perf-review lifecycle, payroll dry-run (finalize ASLA), org chart traversal, shift conflict/coverage, leave accrual, HR audit log, cross-dept RBAC, PII guard. F8A/B/C de v2 backlog ile genişletildi (roadmap "Coverage Gaps / Added Phases"). Öncelik: F8E → F8N → F8L → F8D-v2 → F8K → F8I → F8J. Her faz aynı mutlak kurallar: pilot mutation yok, external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH.

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
