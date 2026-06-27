# Syroce PMS

An enterprise-grade, multi-tenant Hotel Property Management System with AI-powered features adaptable to any accommodation type.

## Run & Operate

- **Frontend**:
  - Install dependencies: `cd frontend && yarn install`
  - Start dev server: `cd frontend && yarn run start`
  - Build for deployment: `cd frontend && yarn build`
- **Backend**:
  - Start services (MongoDB, Redis, FastAPI): `bash backend/start.sh`
- **Environment Variables**: Gruplu sablon + ornekler → `backend/.env.example`; tam katalog + fail-closed semantikleri → `docs/ENVIRONMENT_VARIABLES.md`. Kritik: `JWT_SECRET`, `SENTRY_DSN`, `QUICKID_SERVICE_KEY`, `ROOM_QR_SECRET`, `PUBLIC_APP_URL`, `EXELY_IP_WHITELIST`, `HOTELRUNNER_WEBHOOK_SECRET`, `EFATURA_SUPPLIER_VKN`.

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

- **Dil**: Operatör (Murat) ile tüm iletişim **Türkçe**. Dosyalarda emoji yok.
- **Proje görevleri (project tasks)**: tüm görev **başlıkları ve açıklamaları Türkçe** yazılır — öneriler/Drafts dâhil. Yeni görev öneren task agent'lar da Türkçe yazmalı.
- **Sırlar/kimlik bilgileri**: parola/secret değerleri sohbete yazılmaz, gösterilmez; değerler doğrudan GitHub Actions secrets veya Replit Secrets'a girilir. CI testleri için gerçek süper-admin yerine adanmış, en düşük yetkili hesap kullanılır.

## Gotchas

Detaylı gotcha kayıtları, dosya/satır referansları ve tarihçe → **`docs/GOTCHAS.md`**. REVIEW/SKIP Zeroing (Wave 6–9) + REVIEW/SKIP Reduction (Package A+B→F) uzun detayları → **`docs/ops/REVIEW_SKIP_ZEROING_GOTCHAS.md`**. Aşağıda her always-on bölümün tek-satırlık özeti:

- **Testing** — `frontend/e2e-business/` (20 spec, business-flow, pilot'a koşar, dış servisler SKIP) + `frontend/e2e-smoke/` (24 route × 2 viewport = 48 navigate test). Komutlar: `yarn test:e2e:business`, `yarn test:e2e:smoke`. Env zorunlu: `E2E_BASE_URL`/`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`.
- **Conventions (always-on)** — axios `/api/` YOK, fetch `/api/` VAR · `purple→indigo`/`orange→amber` · `lib/dialogs.js` (native alert/confirm değil) · walk-in misafir adı placeholder rewrite · image upload strict validation · outbound HTTP DNS-rebind safe + IP allowlist.
- **Auth, security & infra** — JWT 7gün override · Redis pub/sub auth invalidation + WS CB · Mongo Atlas 500-koleksiyon limiti workaround · Night Audit N+1 fix · HotelRunner pull retries (manual=3, scheduled=2) · Exely webhook IP allowlist literal (CIDR DEĞİL) + `verify_exely_whitelist.py`.
- **Design system & layout** — Sprint A: `<PageHeader>`/`<KpiCard intent>`/`<StatusBadge>`, Yenile=outline+RefreshCw, primary CTA siyah, emoji yok (ReservationCalendar amber bilinçli istisna) · M5 Layout wrap: routes own `wrapLayout+layoutModule`, page YOK; `yarn guard:layout` regression guard.
- **Hardening series (DONE)** — CM-Hardening (`docs/adr/2026-05-cm-hardening.md`): Conflict Queue + Bulk Resolve, No-Show OTA Outbox Parity, Stop-Sale CB per-connection (Exely no-show parity #3c DEFERRED). Production Hardening (`docs/adr/2026-05-production-hardening.md`): no-show terminal-state guard + inventory lock release, closed-folio refund/void guard.
- **Production Safety Pack (8/8 DONE)** → `docs/PRODUCTION_SAFETY_PLAN.md`, operatör entry `docs/REPLIT_OPS_CHEATSHEET.md`, prova `docs/PRODUCTION_LAUNCH_REHEARSAL.md`: rollback · Atlas-managed backup · CM observability single-source · Sentry alert+PII scrub · Admin pilot section · feature-flag std · 24h monitoring runbook · OPS cheat-sheet.
- **E2E pilot residue sweep** — `backend/scripts/cleanup_e2e_pilot_residue.py` (dry-run default; `--apply` fail-closed guard'lar, pilot_drift=0). Detay → `docs/GOTCHAS.md`.
- **Stress CRM residue sweep** — `backend/scripts/cleanup_stress_crm_residue.py` (HARD DELETE; `E2E_STRESS_TENANT_ID` zorunlu + pilot eşitse refuse). Detay → `docs/GOTCHAS.md`.
- **Kullanıcı e-posta tekilliği (DB zırhı)** — `users._hash_email` üzerinde partial-unique `uniq_users_hash_email` (blind-index; şifreli `email` ciphertext'i DEĞİL, global). `provision_user` artık `DuplicateKeyError`→400. Mevcut mükerrerler index build'ini sessizce E11000'e düşürür (yalnız WARNING) → `db.users.index_information()` ile kurulduğunu doğrula. Mükerrer temizliği: `backend/scripts/cleanup_duplicate_user_emails.py` (dry-run default; `--apply`+`ALLOW_USER_DEDUPE=true` çift opt-in; her grupta EN ESKİ=otorite; blast-radius cap; PII loglanmaz).
- **F8 Stress Test Series** — Faz tarihçesi, spec listesi, module-blocked doctrine, helper konvansiyonları, F8R–F8AH detayları → `docs/GOTCHAS.md` "F8 Stress Test Series" + "F8 Stress Test Series — Spec History" bölümleri. Roadmap (tek doğruluk kaynağı): `docs/STRESS_TEST_ROADMAP.md`.
- **KBS tarayıcı eklentisi (otel IP'sinden Polis+Jandarma)** — `extension/` (MV3) resepsiyon tarayıcısından KBS bildirimi gönderir (bulut IP reddedilir); PMS sayfası kuyruk worker'ı. İki makam (polis/jandarma), per-makam host kilidi, ZIP indirme endpoint'i. Detay → `docs/GOTCHAS.md`; operatör kurulum → `docs/REPLIT_OPS_CHEATSHEET.md`.

## Stress / REVIEW-SKIP Reduction

- **Mevcut baseline:** Run #206 GREEN (708 test; FAIL/P0/P1/P3=0, P2=16, REVIEW=9, SKIP=8; external_calls=[], pilot_drift=0; verdict GO WITH WATCH). Tam tarihçe, provenance (#205→#206 promote, #207 verification-only) + RED triage logları (2026-06-13 / 06-17 / 06-18) → `docs/ops/STRESS_REVIEW_SKIP_STATE.md`.
- **Doktrin (mutlak):** no fake-green · no RBAC/auth weakening · no PII exposure · pilot_drift=0 · external_calls=[] · failedTests=0 · P0=P1=0 · assertion gevşetme YOK · skip-as-pass YOK · gerçek UI failure'ı REVIEW'a düşürme YOK · verdict ≥ GO WITH WATCH · düz "GO"/"/100" iddiası YOK · mobile/F10 ayrı. Agent full stress dispatch EDEMEZ; doğrulama targeted pytest / `node --check` / canlı read-only probe ile CI-deferred.
- **Tamamlanan paketler (A+B→F):** detay → `docs/ops/STRESS_REVIEW_SKIP_STATE.md` + `docs/drill_reports/20260530_review_skip_packages_ab_to_f_summary.md` + `docs/ops/REVIEW_SKIP_ZEROING_GOTCHAS.md`.

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
