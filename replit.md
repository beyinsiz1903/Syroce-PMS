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
- **F8R–F8W Hardening Pack (DONE 2026-05-23)** → `docs/adr/2026-05-f8r-f8w-hardening.md` — 5 yeni spec: F8U auth_token_lifecycle (`98-auth-token-lifecycle`), F8V ws_tenant_isolation (`98B-websocket-tenant-isolation`), F8R export_artifact_idor (`91-export-artifact-idor`), F8S file_upload_security (`64-file-upload-security`), F8W ops_readiness (`09-ops-readiness-smoke`). Doctrine: paylaşılan stress bearer'a dokunma (F8U fresh login), module-block tekil scope, P0=tenant/auth bypass, P1=contract/threshold, P2=info; final invariant her spec'te zorunlu.
- **F8AC Golf Operational Stress (spec written 2026-05-24)** → `docs/adr/2026-05-f8ac-golf-operational.md`, roadmap F8AC section. Yeni spec: `frontend/e2e-stress/specs/98-golf-operational.spec.js` (module `golf_operations`). F8AB spa pattern'inin kardeşi: catalog smoke (courses auto-seed default, super_admin POST fallback) + booking lifecycle (confirmed→checked_in→completed + no_show + cancelled) + **iki katmanlı atomic conflict guard**: (a) slot capacity overflow (party_size+booked > capacity → 409) (b) same player_ids/guest_id at same tee_time → 409 (both under `with_resource_locks` keyed on (course, tee_time)) + folio-post endpoint contract (`/bookings/{id}/folio-post`: reservation_id=null → 400, bogus id → 404, replay → 409 idempotent) + invalid status guard + Idempotency-Key replay with same player_id (distinct ids = P1) + **P0 cross-tenant IDOR** (pilot bearer stress-created booking status / delete / folio-post → 4xx zorunlu, 2xx = P0) + cleanup idempotent. Folio safety: `charge_to_room=True + reservation_id=null` short-circuit (`_post_to_folio` ve `bus.publish(POSTING_CHARGE)` ASLA tetiklenmez, router.py L558-559). Module-blocked: courses/players probe 403/404 → A/B/C/D/E skip + P2. `STRESS_COLLECTIONS` += `golf_courses|golf_players|golf_tee_bookings|golf_locks` (orphan-scrub safety net; spec-side DELETE bookings primary path). Baseline 72 → **73 spec** (full-suite verification bir sonraki tur).
- **F8AB Spa & Wellness Operational Stress (spec written 2026-05-24)** → `docs/drill_reports/20260524_stress_f8ab_spa_operations.md`, ADR-eq: roadmap F8AB section + `docs/STRESS_TEST_ROADMAP.md` "Latest verified baseline" note. Yeni spec: `frontend/e2e-stress/specs/98-spa-wellness-operational.spec.js` (module `spa_operations`). Doctrine: catalog smoke + appointment lifecycle (scheduled→in_progress→completed + no_show + cancelled) + atomic conflict guard (aynı therapist+room+slot → 409, 2xx = P1) + auto-pick (assigned tuple zorunlu) + waitlist CRUD/patch/delete + manual promote + invalid status guard + Idempotency-Key replay (aynı tuple+key → same id veya 409, distinct ids = P1) + **P0 cross-tenant IDOR** (pilot bearer stress-created appt/waitlist mutate edemez, 2xx = P0) + cleanup idempotent + post-batch external_calls=[] + pilot_drift=0 her test'te try/finally. Folio safety: `charge_to_room=True + reservation_id=null` short-circuit (Xchange POSTING_CHARGE ASLA tetiklenmez). Module-blocked: catalog probe 403/404 → A/B/C/D/E skip + P2. `STRESS_COLLECTIONS` += `spa_appointments|waitlist|services|therapists|rooms|locks` (orphan-scrub safety net). Baseline 68 → **69 spec** (full-suite verification bir sonraki tur).
- **F8X–F8AA Local Compliance & Money Safety Pack (specs written 2026-05-24)** → `docs/adr/2026-05-f8x-f8aa-compliance-money-safety.md` — 4 yeni spec: F8X efatura_earsiv_dryrun (`98-efatura-earsiv-dryrun`), F8Y identity_reporting_dryrun (`65-identity-reporting-kbs-jandarma-dryrun`), F8Z payment_pos_reconciliation (`98-payment-pos-reconciliation-dryrun`), F8AA kvkk_retention (`66-kvkk-retention-deletion-anonymization`). Doctrine: read-only + validation + cross-tenant IDOR (P0 hard-fail `expect().toBeGreaterThanOrEqual(400)`) + post-batch external-calls delta=0; dry_run flag olmayan write yüzeylerinde mutation YAPMA (negative amount + bogus id + Idempotency-Key replay yeterli); eksik endpoint (anonymize gibi) → P2 REVIEW (fake PASS yok). **F8X gerçek P0 backend bug yakaladı (2026-05-24)**: `PUT /api/invoices/{id}` (`backend/routers/finance/invoices.py` `update_invoice`) hem `update_one` hem post-update `find_one`'da tenant_id filtresi eksikti → stress_token + pilot invoice_id → 200 + pilot mutated. Architect 4. tur'da paralel IDOR-class bulgusu: `PUT /api/accounting/invoices/{id}` (`backend/routers/finance/accounting.py:705` aktif + `backend/domains/accounting/endpoints.py:672` shadow) — tenant filtresi vardı ama `matched_count==0` guard'ı yoktu (cross-tenant→200+null sessiz no-op, regression risk). Her iki handler'a aynı pattern fix uygulandı (`tenant_filter` + `matched_count==0 → HTTPException(404)`). Manuel localhost doğrulama: invoices stress→pilot=404 ✅ / pilot→pilot=200 ✅; accounting bogus+stress=404 ✅. Önkoşul: stress admin credentials reset (önceki test pilot super_admin ile koşuyordu — false pozitif). **Republish** sonrası targeted re-run (F8X|F8Y|F8Z|F8AA) → full-suite verification (72 spec baseline) sırada.
- **F8 Stress Test Series** — F8A/B/C/D/E/I/L/M faz detayları, tur tarihçesi, module-blocked doctrine, helper konvansiyonları → `docs/GOTCHAS.md` "F8 Stress Test Series" bölümü. Roadmap (tek doğruluk kaynağı): `docs/STRESS_TEST_ROADMAP.md`. **✅ GREEN BASELINE (2026-05-24, commit `ee7573b3`) — F8R–F8W dahil**: Full Operational Stress Suite tek run → 68 spec (5 F8R–F8W: 09/64/91/98/98B), 0 fail, FAIL adım=0, P0=P1=0, external_calls=[], pilot_drift=0, cleanup idempotent. F8S `hr_docs_traversal_sanitize` ilk run'da P1 verdi (gerçek backend bug: raw `file.filename` DB'ye literal yazılıyordu) → `backend/domains/hr/router.py` `_sanitize_doc_filename()` upload+download fix (commit `ee7573b3`) → republish → CI yeşil. Architect verdict: PASS. Detay: `docs/drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md`, ADR: `docs/adr/2026-05-f8r-f8w-hardening.md`. Önceki baseline (referans): `docs/drill_reports/20260523_stress_full_stress_suite_GREEN.md` (413 test, commit `a035568c`). Mutlak kurallar her fazda: pilot mutation=0, external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH, assertion gevşetme YOK, skip-as-pass YOK.

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
