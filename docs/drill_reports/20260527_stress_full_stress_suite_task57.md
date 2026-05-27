# Stress E2E (full_stress_suite_task57) — 20260527

> Suite: `frontend/e2e-stress/` (Playwright config: `playwright.stress.config.js`). Üretildi: 2026-05-27T12:51:56.008Z · Tag: `full_stress_suite_task57`

## 1) Yönetici özeti

| Metrik | Değer |
|---|---|
| Toplam test | 723 |
| Başarısız test | 11 |
| Adım PASS / FAIL / REVIEW / SKIP | 1039 / 1 / 78 / 130 |
| P0 / P1 / P2 / P3 finding | 0 / 3 / 110 / 0 |
| Süre | 2476.9s |
| Final verdict | **NO-GO** — failedTests=11, FAIL adım=1 |

## 2) Seed snapshot (globalSetup)

- prefix: `E2E_STRESS_F7_1779886322643_`
- room_count: `500`
- counts: rooms=500 guests=500 bookings=500 folios=500 charges=1750 rnl=1250 hk=500
- timing_ms: factory=83.8 insert=21110.9 total=21194.7
- external_calls_made: `[]`
- tenant_context_used: `true`
- gates: `{"env_stress_tid_present":true,"target_matches_stress_tid":true,"pilot_tid_not_targeted":true,"destructive_stress_allowed":true,"external_dry_run":true}`

## 3) Cleanup snapshot (globalTeardown)

- **cleanup#1**: status=200 deleted_total=0 ms=11198.3
- **cleanup#2_idempotent**: status=200 deleted_total=0 ms=11556.9 idempotent=true
- **pilot_diff**: baseline_bookings=30 after_bookings=30 drift=0

## 4) Modül bazlı tablo

| Modül | PASS | FAIL | REVIEW | SKIP | Toplam |
|---|---:|---:|---:|---:|---:|
| accommodation_tax | 37 | 0 | 0 | 3 | 41 |
| accounting_bank_inventory | 8 | 0 | 0 | 0 | 8 |
| accounting_expenses | 8 | 0 | 0 | 0 | 8 |
| admin_rbac | 5 | 0 | 0 | 4 | 9 |
| ai_noshow_risk | 23 | 0 | 0 | 1 | 24 |
| ai_pricing | 20 | 0 | 0 | 1 | 21 |
| ai_upsell | 22 | 0 | 0 | 0 | 22 |
| auth_token_lifecycle | 20 | 0 | 0 | 0 | 20 |
| b2b_api | 8 | 0 | 0 | 10 | 18 |
| backend_router_coverage_probe | 10 | 0 | 43 | 0 | 53 |
| banquet_competitor | 10 | 0 | 0 | 0 | 10 |
| booking_holds | 4 | 0 | 0 | 0 | 4 |
| bulk-seed-500 | 11 | 0 | 1 | 0 | 12 |
| cashier_shift | 8 | 0 | 0 | 0 | 8 |
| cm_exely_webhook | 14 | 0 | 3 | 0 | 17 |
| cm_hotelrunner_webhook | 15 | 0 | 1 | 0 | 16 |
| cm_outbox | 16 | 0 | 1 | 0 | 17 |
| cm_stop_sale_bulk_resolve | 11 | 1 | 0 | 0 | 12 |
| complaints | 0 | 0 | 1 | 0 | 1 |
| crm_offers | 16 | 0 | 0 | 0 | 16 |
| cross_property_rollup | 3 | 0 | 0 | 0 | 3 |
| cross_tenant_pentest | 8 | 0 | 0 | 1 | 9 |
| day-turnover | 12 | 0 | 0 | 0 | 12 |
| efatura_earsiv_dryrun | 10 | 0 | 0 | 0 | 11 |
| eod_report | 3 | 0 | 0 | 0 | 3 |
| export_artifact_idor | 8 | 0 | 0 | 1 | 9 |
| f8ah_cleanup | 4 | 0 | 0 | 0 | 4 |
| f8ah_setup | 2 | 0 | 0 | 0 | 3 |
| file_upload_security | 12 | 0 | 0 | 1 | 13 |
| finance_cityledger | 8 | 0 | 0 | 0 | 8 |
| finance_folio | 4 | 0 | 1 | 0 | 5 |
| finance_reports_currency | 5 | 0 | 2 | 0 | 7 |
| fnb_beo | 18 | 0 | 2 | 0 | 20 |
| folio-mass | 1 | 0 | 1 | 9 | 11 |
| full_24h | 3 | 0 | 0 | 1 | 4 |
| gates | 9 | 0 | 2 | 0 | 11 |
| golf_operations | 24 | 0 | 0 | 0 | 25 |
| graphql_isolation | 16 | 0 | 1 | 0 | 17 |
| housekeeping | 5 | 0 | 0 | 3 | 8 |
| hr_attendance | 2 | 0 | 0 | 3 | 5 |
| hr_dept_position_masterdata | 14 | 0 | 0 | 0 | 14 |
| hr_employee_profile_detail | 4 | 0 | 0 | 3 | 7 |
| hr_leave | 2 | 0 | 0 | 3 | 5 |
| hr_leave_accrual | 4 | 0 | 0 | 5 | 9 |
| hr_lifecycle_v2 | 5 | 0 | 0 | 3 | 8 |
| hr_offboarding | 4 | 0 | 0 | 3 | 7 |
| hr_payroll | 15 | 0 | 0 | 0 | 15 |
| hr_payroll_export_pii | 13 | 0 | 0 | 0 | 13 |
| hr_payroll_lifecycle | 6 | 0 | 2 | 0 | 8 |
| hr_perf | 4 | 0 | 0 | 5 | 9 |
| hr_rbac_pii | 4 | 0 | 0 | 7 | 11 |
| hr_shift | 2 | 0 | 0 | 5 | 7 |
| hr_shift_conflict | 4 | 0 | 0 | 6 | 10 |
| hr_shift_coverage_planning | 9 | 0 | 2 | 0 | 11 |
| hr_staff_org | 2 | 0 | 0 | 2 | 4 |
| hr_staff_self_service | 8 | 0 | 0 | 0 | 8 |
| identity_reporting_dryrun | 11 | 0 | 1 | 0 | 13 |
| inventory_stock | 13 | 0 | 0 | 0 | 13 |
| inventory_transfer_procurement | 5 | 0 | 0 | 0 | 6 |
| kvkk_retention | 11 | 0 | 0 | 2 | 14 |
| maintenance_workorder | 2 | 0 | 1 | 0 | 3 |
| marketplace | 14 | 0 | 3 | 1 | 18 |
| messaging | 7 | 0 | 1 | 0 | 8 |
| messaging_template | 25 | 0 | 0 | 0 | 25 |
| mice_events | 3 | 0 | 0 | 0 | 3 |
| mice_execution | 4 | 0 | 0 | 3 | 7 |
| mice_opportunities | 13 | 0 | 0 | 0 | 13 |
| mobile_cashier | 25 | 0 | 1 | 0 | 26 |
| mobile_staff | 9 | 0 | 1 | 9 | 19 |
| night-audit | 6 | 0 | 0 | 0 | 6 |
| notification_batch | 4 | 0 | 0 | 3 | 7 |
| ops_readiness | 11 | 0 | 1 | 0 | 12 |
| payment_pos_reconciliation | 12 | 0 | 0 | 3 | 16 |
| pos_deep_lifecycle | 33 | 0 | 1 | 0 | 35 |
| pos_extensions | 30 | 0 | 0 | 0 | 31 |
| pos_kds_inventory | 40 | 0 | 0 | 0 | 41 |
| public_checkin | 11 | 0 | 0 | 0 | 11 |
| public_kvkk | 11 | 0 | 1 | 1 | 13 |
| public_nps | 15 | 0 | 1 | 0 | 16 |
| public_token_rotation | 4 | 0 | 0 | 3 | 7 |
| purchasing_supplier | 13 | 0 | 0 | 0 | 13 |
| qr_requests | 1 | 0 | 0 | 0 | 1 |
| rate_limit_boundary | 10 | 0 | 0 | 0 | 10 |
| reports_export | 21 | 0 | 1 | 0 | 22 |
| reservation_deep | 4 | 0 | 0 | 12 | 16 |
| reservation-lifecycle | 1 | 0 | 0 | 0 | 1 |
| revenue_management | 53 | 0 | 1 | 2 | 57 |
| room-move | 1 | 0 | 0 | 0 | 1 |
| sales_leads | 13 | 0 | 0 | 0 | 13 |
| sales_lifecycle | 19 | 0 | 0 | 0 | 19 |
| service_requests | 6 | 0 | 0 | 1 | 7 |
| settings_audit | 4 | 0 | 0 | 5 | 9 |
| shift_handover | 3 | 0 | 0 | 0 | 3 |
| spa_operations | 5 | 0 | 0 | 1 | 7 |
| twofa_lifecycle | 27 | 0 | 1 | 0 | 28 |
| vcc_pci_compliance | 10 | 0 | 0 | 1 | 12 |
| webhook_admin_dlq | 2 | 0 | 0 | 0 | 2 |
| ws_tenant_isolation | 4 | 0 | 0 | 3 | 7 |

## 5) P0/P1/P2/P3 Severity Triage

### P1 (3)
- **[cm_stop_sale_bulk_resolve]** Bulk-resolve real-succeeded seed missing
  - Test: `stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › G) Bulk-resolve — real partial-success (deterministic; seeded pending)`
  - Detay: GET /api/channel-manager/conflict-queue returned no pending_assignment booking despite global-setup.js passing seed_pending_bookings>0. Check backend stress seed factory (pending_bookings_docs branch) or PENDING_QUERY shape drift.
- **[mobile_cashier]** Cashier handover PIN/password gate has NO brute-force throttle
  - Test: `stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › L) PIN brute-force throttle probe`
  - Detay: 7 wrong-credential attempts produced statuses=[401,401,401,401,401,401,401]; expected 429 by attempt 7. Financial gate must rate-limit.
- **[mobile_staff]** Mobile staff stress requires DISABLE_EXPO_PUSH=1
  - Test: `stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › Setup: stress token + module probe + pilot baseline`
  - Detay: Runner env not set; lifecycle batch SKIPped to prevent real Expo delivery.

### P2 (110)
- **[room-move]** Rooms fetch stress_prefix mismatch — stress_seed:true fallback'e düşüldü
  - Test: `stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › Setup: stress bookings + rooms snapshot + guarantee vacant pool`
  - Detay: prefix_match=0 fakat stress_seed:true ile 200 room recovered. Backend serializer stress_prefix'i drop ediyor olabilir; root cause: pms_rooms.py response model.
- **[night-audit]** Açık night-audit exception sayısı yüksek (200)
  - Test: `stress › 06-night-audit.spec.js › F8A § 06 — Night audit (business-date / run / re-run idempotency / exceptions) › C) Exceptions list GET`
  - Detay: Stress tenant icin unresolved transaction birikmis — operasyon dashboard takip etmeli.
- **[ops_readiness]** Backup status response'unda last_backup_at türetilemedi
  - Test: `stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › B) Backup status not stale — last backup age within threshold`
  - Detay: endpoint=/api/infra/backup/status body_keys=enabled,retention_days,backup_path,last_successful,history_count,metrics,critical_collections,rpo_target,rto_target. Shape değişti veya boş history.
- **[ops_readiness]** CM outbox depth endpoint reachable değil
  - Test: `stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › C) CM outbox depth + conflict queue — within bounds`
  - Detay: tried=["/api/cm/outbox/stats","/api/cm/outbox/depth","/api/channel-manager/outbox/stats","/api/cm/health"] — observability sinyali eksik.
- **[ops_readiness]** CM conflict queue endpoint reachable değil
  - Test: `stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › C) CM outbox depth + conflict queue — within bounds`
  - Detay: tried=["/api/cm/conflict-queue/stats","/api/cm/conflict-queue?status=open&limit=1"] — operasyon sinyali eksik.
- **[mice_execution]** no MICE event harvested
  - Test: `stress › 18-mice-execution-beo.spec.js › F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet) › Setup: prefix + pilot baseline + stress event harvest + MICE probe`
  - Detay: events list status=200 count=0
- **[mice_execution]** F&B order send endpoint absent
  - Test: `stress › 18-mice-execution-beo.spec.js › F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet) › D) Missing endpoint REVIEW (F&B send) + final invariants`
  - Detay: Backend `backend/routers/mice.py` content: BEO + kitchen-ticket + ops-sheet + payment-schedule var; F&B order send (restoran/mutfak entegrasyon outbound) YOK. F8C-v2 backlog (docs/STRESS_TEST_ROADMAP.md "Coverage Gaps / F8C backlog"). Eklendiğinde bu spec extend edilir.
- **[hr_staff_org]** HR org module read blocked
  - Test: `stress › 20-hr-staff-org.spec.js › F8D § 20 — HR Staff Org › Setup: prefix + pilot baseline + module probe`
  - Detay: dept_status=200 pos_status=200 dept_id=fdc24800-e044-4dbb-9ab3-0545a00a1680 pos_id=none — A/B skipped, pilot_drift gate still enforced.
- **[hr_attendance]** HR attendance module read blocked
  - Test: `stress › 21-hr-attendance.spec.js › F8D § 21 — HR Attendance › Setup: prefix + pilot baseline + staff pool`
  - Detay: staff_status=200 pool_size=0 need>=5 — A/B/C skipped, pilot_drift gate still enforced.
- **[hr_leave]** HR leave module read blocked
  - Test: `stress › 22-hr-leave.spec.js › F8D § 22 — HR Leave › Setup: prefix + pilot baseline + staff pool + balance probe`
  - Detay: staff_status=200 balance_status=n/a pool=0 — A/B/C skipped, pilot_drift gate still enforced.
- **[hr_shift]** HR shift module read blocked
  - Test: `stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › Setup: prefix + pilot baseline + staff pool + shift pool`
  - Detay: staff_status=200 shifts_status=200 swap_list_status=200 staff_pool=0 shift_pool=0 need_staff>=10 need_shift>=5 — A/B/C skipped, pilot_drift gate still enforced.
- **[finance_reports_currency]** Currency secondary step fail (hard-floor PASS)
  - Test: `stress › 28-finance-reports-currency.spec.js › F8E § 28 — Finance Reports + Currency › B) Currency rates lifecycle (create + list + convert)`
  - Detay: rate=3/3 list=200 conv=0/2 (rate hard floor OK).
- **[admin_rbac]** Admin tenants probe non-2xx
  - Test: `stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › Setup: prefix + pilot baseline + super_admin team POST probe + per-role user create`
  - Detay: status=404 reason=endpoint_not_deployed — A/B/C skipped, D pilot_drift still enforced.
- **[settings_audit]** Admin tenants probe non-2xx
  - Test: `stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › Setup: prefix + pilot baseline + tenants probe + snapshots`
  - Detay: status=404 reason=endpoint_not_deployed — A/B/C/D skipped, F pilot_drift still enforced.
- **[hr_perf]** No seeded performance reviews available
  - Test: `stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › Setup: prefix + pilot baseline + perf list probe + pool build`
  - Detay: items_total=0 pool=0 — A/B/C skipped, E pilot_drift still enforced.
- **[hr_leave_accrual]** No stress-tagged staff in pool
  - Test: `stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › Setup: prefix + pilot baseline + staff pool + leave-balance probe`
  - Detay: total=355 prefix=E2E_STRESS_F7_1779886322643_ pool=0 — A/B/C/D skipped, E enforced.
- **[hr_shift_conflict]** Stress staff pool insufficient for conflict probe
  - Test: `stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › Setup: prefix + pilot baseline + staff pool + shifts probe`
  - Detay: pool=0 need>=2 — A/B/C/D skipped.
- **[hr_rbac_pii]** Per-role test user creation failed for all roles
  - Test: `stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › Setup: prefix + pilot baseline + staff pool + per-role test user create + login`
  - Detay: front_desk → status=404 body={"detail":"Not Found"} — B matrix skipped; C/D/E still attempted under super_admin; F pilot_drift enforced.
- **[hr_lifecycle_v2]** HR lifecycle v2 staff pool insufficient
  - Test: `stress › 37-hr-lifecycle-v2.spec.js › F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim) › Setup: prefix + pilot baseline + staff pool + outstanding probe`
  - Detay: staff_status=200 pool=0 need>=4 — A/B/C skipped, D pilot_drift still enforced.
- **[hr_employee_profile_detail]** Employee profile staff pool insufficient
  - Test: `stress › 38-hr-employee-profile-detail.spec.js › F8D-v3 § 38 — Employee Profile Detail › Setup: prefix + pilot baseline + staff pool + profile probe`
  - Detay: staff_status=200 pool=0 — A/B/C skipped, D pilot_drift still enforced.
- **[hr_offboarding]** Offboarding stress staff pool empty
  - Test: `stress › 39B-hr-offboarding.spec.js › F8D-v3 § 39B — Offboarding (Termination Read-Only + 409 Guard) › Setup: prefix + pilot baseline + termination GET probe`
  - Detay: staff_status=200 prefix=E2E_STRESS_F7_1779886322643_ — A/B/C skipped, D pilot_drift still enforced.
- **[graphql_isolation]** GraphQL introspection production stress'te açık
  - Test: `stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › A) Introspection policy + Mutation surface contract`
  - Detay: Schema introspection 2xx döndü (types=25). Production'da disable edilmesi önerilir; attack surface keşfi ücretsiz oluyor. Acceptance: REVIEW/P2 informational.
- **[graphql_isolation]** Pilot GraphQL vs REST count discrepancy (informational)
  - Test: `stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › D) Auth boundary — unauthenticated + invalid token + wrong-tenant`
  - Detay: Pilot REST(limit=500)=50 bookings; GraphQL(limit=100)=100. GraphQL limit'e dayandı; REST status/date filtreleri farklı semantik. Tenant isolation kanıtı resolver tenant_id filtresi (schema.py:328) — leak değil, kıyas semantik farkı.
- **[b2b_api]** Stress tenant'a ait agency bulunamadı
  - Test: `stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › Setup: prefix + pilot baseline + agencies probe + create stress API key`
  - Detay: agencies_list_len=0 — seed agency yok; API key create akışı yapılamıyor. A/B/C/D skipped.
- **[b2b_api]** Stress tenant agency yok (v2 matrix)
  - Test: `stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › Setup: pilot baseline + stress agency + create key + pilot id sampling`
  - Detay: agencies_list_len=0 — matrix tests skipped.
- **[notification_batch]** DISABLE_EXPO_PUSH not set
  - Test: `stress › 45-notification-batch-dryrun.spec.js › F8Q § 45 — Push notification batch dry-run › Setup: prefix + DISABLE_EXPO_PUSH guard + messaging probe + pilot baseline`
  - Detay: Env var ENV=stress runner için set değil — Expo HTTP fail-closed assert hala external_calls=[] gate ile yakalanır, ama config drift.
- **[notification_batch]** messaging module probe blocked
  - Test: `stress › 45-notification-batch-dryrun.spec.js › F8Q § 45 — Push notification batch dry-run › Setup: prefix + DISABLE_EXPO_PUSH guard + messaging probe + pilot baseline`
  - Detay: endpoint=/api/messaging/settings status=404 reason=endpoint_not_deployed — A/B/C skip, D bağımsız.
- **[cm_exely_webhook]** Exely readiness gate prod_like_unset (informational)
  - Test: `stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › F) EXELY readiness gate — env contract semantics (configured PASS / HR-only N/A / prod-like unset P2 informational / bypass P1)`
  - Detay: EXELY_IP_WHITELIST set değil + bypass yok — fail-closed 503 contract honored. Production deploy öncesi CI/CD env'inde whitelist seed'i zorunlu.
- **[cm_exely_webhook]** Exely valid-payload + idempotency coverage gap
  - Test: `stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › G) Conditional valid payload + duplicate ingest idempotency (auth-mode=open_for_testing veya EXELY_IP_WHITELIST set)`
  - Detay: auth_mode=fail_closed_503. Bu koşuda valid parse path test edilemedi; production-like ortamda (whitelist + caller IP) test sürdürülmeli.
- **[cm_exely_webhook]** Exely cancellation idempotency coverage gap
  - Test: `stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › H) Conditional cancellation idempotency — aynı reservation_id cancel 2x → tek state geçişi (auth-mode=open)`
  - Detay: auth_mode=fail_closed_503. Whitelisted prod env'de cancel duplicate 2x test sürdürülmeli.
- **[cm_hotelrunner_webhook]** HotelRunner signed-path coverage gap — stres env'de HOTELRUNNER_WEBHOOK_SECRET set değil
  - Test: `stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › F) Signed valid-path — HOTELRUNNER_WEBHOOK_SECRET set ise gerçek HMAC payload kabul edilmeli (stress_tid scope, dispatcher dry-run)`
  - Detay: Imzasız reddetme contract'ı PASS; valid HMAC kabul path'i bu koşuda assert edilemedi. Production readiness için CI env'inde secret seed'i öneriliyor (follow-up: gerçek imzalı yük testi).
- **[cm_outbox]** Outbox active idempotency coverage gap — secret unset
  - Test: `stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › E) Active idempotency — duplicate signed webhook ingest → outbox event delta ≤ 1 (HOTELRUNNER_WEBHOOK_SECRET conditional)`
  - Detay: Passive delta (Test A) PASS; aktif duplicate-dispatch dedupe path'i bu koşuda assert edilemedi. Production readiness için CI env'inde HOTELRUNNER_WEBHOOK_SECRET seed'i öneriliyor (follow-up: aktif idempotency).
- **[public_kvkk]** Digital key route probe non-2xx (endpoint_not_deployed)
  - Test: `stress › 62-public-kvkk-consent.spec.js › F8K § 62 — KVKK Consent + Digital Key + PII Guard Stress › Setup: prefix + pilot baseline + stress booking/guest probe + digital-key route probe`
  - Detay: GET /api/guest/digital-key/<stress_bk> status=404 — B step skipped, A+C bağımsız.
- **[public_token_rotation]** no stress room harvested
  - Test: `stress › 63-public-token-rotation.spec.js › F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep › Setup: prefix + pilot baseline + stress room harvest + module probe`
  - Detay: GET /api/rooms status=404 — A/B/C skip, D bağımsız.
- **[public_token_rotation]** QR secret rotation endpoint absent
  - Test: `stress › 63-public-token-rotation.spec.js › F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep › D) Rotation surface contract REVIEW + final invariants`
  - Detay: ROOM_QR_SECRET rotation deployment-only (env var). Public/staff API surface yok. Rotation-after token reject kontratı _verify_token HMAC sig mismatch ile dolaylı doğrulanır (tamper_contract A adımı).
- **[file_upload_security]** Housekeeping photo surface blocked
  - Test: `stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › Setup: pilot baseline + staff/room probes`
  - Detay: reason=no_stress_rooms — HK photo testleri SKIP; HR + final bağımsız.
- **[file_upload_security]** HR docs polyglot kabul edildi (HTML body, MIME=application/pdf)
  - Test: `stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › A) HR docs — oversized / bad MIME / polyglot / path traversal reject`
  - Detay: doc_id=b339cbf2-0baa-4d68-8ef4-cf1ffe9b7fac — backend MIME header-trust; download response Content-Type sanitize edilmezse browser XSS render edebilir. Magic-bytes verification eklenmesi önerilir.
- **[identity_reporting_dryrun]** KBS_TEST_MODE prefix guard not enforced (env likely off)
  - Test: `stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS_TEST_MODE prefix guard + queue schema enforcement`
  - Detay: POST /api/kbs/queue/.../complete with no TEST- prefix → http=404. If KBS_TEST_MODE=1 expected 422 with "TEST-" mention; route reached job-not-found instead. Env state review needed.
- **[kvkk_retention]** Anonymize / hard-delete guest endpoint not surfaced
  - Test: `stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › GDPR + retention surface read-only probe`
  - Detay: Backend explicit `/api/gdpr/anonymize` veya `/api/gdpr/guest-delete` endpoint'i bulunmadı. KVKK silinme talebi şu an file-level (ID-photo) cleanup'a dayanıyor; guest profile anonymize/erase iş kuralı için endpoint kontratı gerekir. Roadmap backlog: F8AA v2.
- **[crm_offers]** Duplicate tax_no contract gap on mice_accounts
  - Test: `stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › A) Account CRUD + duplicate-tax-no guard probe`
  - Detay: Expected 409 on duplicate tax_no POST; got 200. Informational contract gap (no native unique index on mice_accounts.tax_no).
- **[crm_offers]** Duplicate-email guard surface absent on mice_accounts
  - Test: `stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › A) Account CRUD + duplicate-tax-no guard probe`
  - Detay: mice_accounts payload (AccountIn) has no email field, so duplicate-email guard not applicable at account level. Contact-level email also has no unique constraint. Informational gap recorded.
- **[crm_offers]** No native contract approval state machine
  - Test: `stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › D) Corporate contract dry-run lifecycle (create + update)`
  - Detay: Backend POST /api/sales/corporate-contract hard-codes status="active"; PUT update does not expose approval lifecycle (draft→review→approved→signed) as a first-class field. Spec simulates the transition via notes payload. Informational gap — not blocking.
- **[reservation_deep]** Setup: stress oda havuzu yetersiz — module blocked
  - Test: `stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › Setup: stress bookings/rooms/guests snapshot + pilot baseline`
  - Detay: rooms=0 (en az 5 gerekli A–L için) — A/B/C/D/E/F/G/H/I/J/K/L skipped, M/N still enforced.
- **[cross_tenant_pentest]** surface_blocked:folios
  - Test: `stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › Setup: prefix + pilot baseline + surface probes + pilot sample ID harvest`
  - Detay: endpoint=/api/folios?limit=50 status=404 reason=endpoint_not_deployed — list/PII tests skip, IDOR + pilot_drift bağımsız.
- **[cross_tenant_pentest]** surface_blocked:folio_charges
  - Test: `stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › Setup: prefix + pilot baseline + surface probes + pilot sample ID harvest`
  - Detay: endpoint=/api/folio-charges?limit=50 status=404 reason=endpoint_not_deployed — list/PII tests skip, IDOR + pilot_drift bağımsız.
- **[cross_tenant_pentest]** surface_blocked:messages
  - Test: `stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › Setup: prefix + pilot baseline + surface probes + pilot sample ID harvest`
  - Detay: endpoint=/api/messaging/messages?limit=50 status=404 reason=endpoint_not_deployed — list/PII tests skip, IDOR + pilot_drift bağımsız.
- **[backend_router_coverage_probe]** Router pos_fnb_menu: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pos_fnb_menu (/api/pos/fnb/menu)`
  - Detay: path=/api/pos/fnb/menu anon=404 auth=404
- **[backend_router_coverage_probe]** Router pos_fnb_modifiers: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pos_fnb_modifiers (/api/pos/fnb/modifiers)`
  - Detay: path=/api/pos/fnb/modifiers anon=404 auth=404
- **[backend_router_coverage_probe]** Router mobile_router_tasks: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: mobile_router_tasks (/api/mobile/tasks)`
  - Detay: path=/api/mobile/tasks anon=404 auth=404
- **[backend_router_coverage_probe]** Router mobile_router_shift: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: mobile_router_shift (/api/mobile/shift/current)`
  - Detay: path=/api/mobile/shift/current anon=404 auth=404
- **[backend_router_coverage_probe]** Router dashboard_widgets: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: dashboard_widgets (/api/pms/dashboard/widgets)`
  - Detay: path=/api/pms/dashboard/widgets anon=404 auth=404
- **[backend_router_coverage_probe]** Router pms_groups: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_groups (/api/pms/groups)`
  - Detay: path=/api/pms/groups anon=404 auth=404
- **[backend_router_coverage_probe]** Router pms_catering: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_catering (/api/pms/catering)`
  - Detay: path=/api/pms/catering anon=404 auth=404
- **[backend_router_coverage_probe]** Router pms_approvals: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_approvals (/api/pms/approvals)`
  - Detay: path=/api/pms/approvals anon=404 auth=404
- **[backend_router_coverage_probe]** Router pms_wakeup: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_wakeup (/api/pms/wakeup-calls)`
  - Detay: path=/api/pms/wakeup-calls anon=404 auth=404
- **[backend_router_coverage_probe]** Router hotelrunner_status: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hotelrunner_status (/api/channel-manager/hotelrunner/status)`
  - Detay: path=/api/channel-manager/hotelrunner/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router exely_status: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: exely_status (/api/channel-manager/exely/status)`
  - Detay: path=/api/channel-manager/exely/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router cm_validation: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_validation (/api/channel-manager/validation/health)`
  - Detay: path=/api/channel-manager/validation/health anon=404 auth=404
- **[backend_router_coverage_probe]** Router cm_lockdown: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_lockdown (/api/channel-manager/lockdown/status)`
  - Detay: path=/api/channel-manager/lockdown/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router cm_incident_list: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_incident_list (/api/channel-manager/incidents)`
  - Detay: path=/api/channel-manager/incidents anon=404 auth=404
- **[backend_router_coverage_probe]** Router cm_reconciliation: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_reconciliation (/api/channel-manager/reconciliation/summary)`
  - Detay: path=/api/channel-manager/reconciliation/summary anon=404 auth=404
- **[backend_router_coverage_probe]** Router ai_upsell: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_upsell (/api/ai/upsell/recommendations)`
  - Detay: path=/api/ai/upsell/recommendations anon=404 auth=404
- **[backend_router_coverage_probe]** Router ai_forecasting: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_forecasting (/api/ai/forecasting/horizon)`
  - Detay: path=/api/ai/forecasting/horizon anon=404 auth=404
- **[backend_router_coverage_probe]** Router ai_guest_pattern: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_guest_pattern (/api/ai/guest-patterns/summary)`
  - Detay: path=/api/ai/guest-patterns/summary anon=404 auth=404
- **[backend_router_coverage_probe]** Router ai_dynamic_offers: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_dynamic_offers (/api/ai/offers/active)`
  - Detay: path=/api/ai/offers/active anon=404 auth=404
- **[backend_router_coverage_probe]** Router finance_mobile_cashier: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: finance_mobile_cashier (/api/finance/mobile/cashier/status)`
  - Detay: path=/api/finance/mobile/cashier/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router finance_mobile_payments: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: finance_mobile_payments (/api/finance/mobile/payments/recent)`
  - Detay: path=/api/finance/mobile/payments/recent anon=404 auth=404
- **[backend_router_coverage_probe]** Router guest_journey_list: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: guest_journey_list (/api/guest/journey/list)`
  - Detay: path=/api/guest/journey/list anon=404 auth=404
- **[backend_router_coverage_probe]** Router guest_loyalty_status: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: guest_loyalty_status (/api/guest/loyalty/status)`
  - Detay: path=/api/guest/loyalty/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router guest_preferences: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: guest_preferences (/api/guest/preferences)`
  - Detay: path=/api/guest/preferences anon=404 auth=404
- **[backend_router_coverage_probe]** Router messaging_templates: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: messaging_templates (/api/messaging/templates)`
  - Detay: path=/api/messaging/templates anon=404 auth=404
- **[backend_router_coverage_probe]** Router messaging_settings: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: messaging_settings (/api/messaging/settings)`
  - Detay: path=/api/messaging/settings anon=404 auth=404
- **[backend_router_coverage_probe]** Router hr_leave_balance: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_leave_balance (/api/hr/leave/balance)`
  - Detay: path=/api/hr/leave/balance anon=404 auth=404
- **[backend_router_coverage_probe]** Router hr_performance_reviews: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_performance_reviews (/api/hr/performance/reviews)`
  - Detay: path=/api/hr/performance/reviews anon=401 auth=404
- **[backend_router_coverage_probe]** Router hr_recruitment_postings: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_recruitment_postings (/api/hr/recruitment/postings)`
  - Detay: path=/api/hr/recruitment/postings anon=404 auth=404
- **[backend_router_coverage_probe]** Router hr_training_catalog: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_training_catalog (/api/hr/training/catalog)`
  - Detay: path=/api/hr/training/catalog anon=404 auth=404
- **[backend_router_coverage_probe]** Router hr_benefits_summary: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_benefits_summary (/api/hr/benefits/summary)`
  - Detay: path=/api/hr/benefits/summary anon=404 auth=404
- **[backend_router_coverage_probe]** Router admin_governance: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: admin_governance (/api/admin/governance/audit)`
  - Detay: path=/api/admin/governance/audit anon=404 auth=404
- **[backend_router_coverage_probe]** Router admin_feature_flags: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: admin_feature_flags (/api/admin/feature-flags)`
  - Detay: path=/api/admin/feature-flags anon=401 auth=404
- **[backend_router_coverage_probe]** Router observability_traces: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: observability_traces (/api/observability/traces/recent)`
  - Detay: path=/api/observability/traces/recent anon=404 auth=404
- **[backend_router_coverage_probe]** Router system_health_components: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: system_health_components (/api/system-health/components)`
  - Detay: path=/api/system-health/components anon=404 auth=404
- **[backend_router_coverage_probe]** Router svc_laundry_status: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_laundry_status (/api/services/laundry/status)`
  - Detay: path=/api/services/laundry/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router svc_transport_status: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_transport_status (/api/services/transport/status)`
  - Detay: path=/api/services/transport/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router svc_concierge_requests: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_concierge_requests (/api/services/concierge/requests)`
  - Detay: path=/api/services/concierge/requests anon=404 auth=404
- **[backend_router_coverage_probe]** Router svc_activities: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_activities (/api/services/activities)`
  - Detay: path=/api/services/activities anon=404 auth=404
- **[backend_router_coverage_probe]** Router svc_kids_club: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_kids_club (/api/services/kids-club)`
  - Detay: path=/api/services/kids-club anon=404 auth=404
- **[backend_router_coverage_probe]** Router integrations_whatsapp: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: integrations_whatsapp (/api/integrations/whatsapp/status)`
  - Detay: path=/api/integrations/whatsapp/status anon=404 auth=404
- **[backend_router_coverage_probe]** Router reports_list: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: reports_list (/api/reports/list)`
  - Detay: path=/api/reports/list anon=404 auth=404
- **[backend_router_coverage_probe]** Router reports_scheduled: auth_404_not_deployed
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: reports_scheduled (/api/reports/scheduled)`
  - Detay: path=/api/reports/scheduled anon=404 auth=404
- **[efatura_earsiv_dryrun]** InvoiceCreate schema lacks VKN/TCKN customer identity fields
  - Test: `stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement`
  - Detay: Backend `InvoiceCreate` (`backend/models/schemas/invoicing.py`) yalnız customer_name + customer_email saklıyor; Türkiye e-fatura/e-arşiv UBL pratiğinde VKN (kurumsal) ve TCKN (bireysel) zorunlu. Schema genişletilmesi roadmap backlog: F8X v2.
- **[fnb_beo]** E2_beo_pdf non-200 status=404
  - Test: `stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › E2) GET /api/mice/events/{id}/beo.pdf — PDF render`
  - Detay: 
- **[accommodation_tax]** Pilot konaklama vergisi declaration pool empty — IDOR vacuously holds
  - Test: `stress › 98-konaklama-vergisi-dryrun.spec.js › F8AD konaklama vergisi dryrun › P0 cross-tenant IDOR — stress_token vs pilot resources (hard-fail)`
  - Detay: GET /api/finance/konaklama-vergisi/declarations?limit=5 list_len=0; cross-tenant decl probe surface eksik.
- **[marketplace]** inventory non-200 status=404
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › F) Inventory check — GET marketplace/inventory`
  - Detay: 
- **[marketplace]** purchase-orders POST non-2xx status=404
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › H) Order place — POST purchase-orders`
  - Detay: body={"detail":"Not Found"}
- **[marketplace]** J1 unexpected status=422
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › J) IDOR: cross-tenant probes → no mutation / no leak`
  - Detay: probe=bogus_tid_fallback
- **[webhook_admin_dlq]** webhook-admin endpoint not deployed
  - Test: `stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › C) webhook_admin_dlq — global status smoke + non-super-admin 403 + cross-tenant filter`
  - Detay: GET /api/webhooks/status http=404 — module not mounted; suite SKIP.
- **[payment_pos_reconciliation]** Payment pos_tables_list surface module-blocked
  - Test: `stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › cashier + POS read-only surface`
  - Detay: GET /api/pos/tables?limit=5 http=404 reason=endpoint_not_deployed.
- **[payment_pos_reconciliation]** Manual transaction idempotency probe skipped
  - Test: `stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › manual-transaction X-Idempotency-Key replay`
  - Detay: Cashier current-shift http=200 body.shift=null; cannot exercise X-Idempotency-Key replay without active shift.
- **[pos_deep_lifecycle]** transfer-table happy-path structurally unreachable
  - Test: `stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › E) Table-transfer: happy-path attempt + bogus 404 + cross-tenant guard`
  - Detay: No production write surface creates pos_transactions.status='open'. Seed via /pos/transaction (status='completed') produced http=200; subsequent transfer-table call http=422 (expected 404 because filter requires status='open'). Backend gap — transfer-table is dead-code for v2 lifecycle until an "open-tab" surface is added. Compensating: negative-contract + cross-tenant guard tested below.
- **[pos_kds_inventory]** F&B recipe catalog empty/blocked
  - Test: `stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › Setup: probe KDS + inventory surfaces + pilot inventory baseline`
  - Detay: recipes_http=200 count=0 — E (inventory deplete happy) + G (concurrent close race) skip. Out of scope per Task #11.
- **[pos_kds_inventory]** Inventory deplete happy path skipped — no recipe seed
  - Test: `stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › E) Inventory deplete happy path (recipe → close → inventory_items decrement)`
  - Detay: Stress tenant has no recipes/BOM; Task #11 leaves seeding out of scope. Step recorded as P2 REVIEW (not fake PASS).
- **[revenue_management]** ai-pricing auto-publish lacks server-side dry_run gate
  - Test: `stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › F) AI pricing auto-publish — dry_run gate + post-batch external_calls=0`
  - Detay: POST .../auto-publish-rates accepted dry_run=true query param without distinct behaviour (rates_published=3). Backend has no dry_run kill-switch — operator must rely on external_calls invariant (no real channel HTTP this run) + caller-side gating. Feature request: add explicit dry_run server flag suppressing rate-calendar writes + outbox events.
- **[revenue_management]** displacement saved-scenario fetch/mutate IDOR not exercisable
  - Test: `stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › G) Cross-tenant IDOR — stress_token must NOT mutate pilot resources`
  - Detay: Backend /api/displacement exposes no GET/{id} or DELETE/{id} surface — saved-scenario cross-tenant fetch/mutate has no path-id IDOR vector. Tenant scoping covered by per-tenant /history filter + pilot_drift invariant.
- **[revenue_management]** pilot hurdle harvest empty — IDOR vector not exercised
  - Test: `stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › G) Cross-tenant IDOR — stress_token must NOT mutate pilot resources`
  - Detay: GET /api/hurdle-rates/ pilot returned empty list; cross-tenant guard cannot be exercised this run.
- **[revenue_management]** pilot autopilot queue empty — IDOR vector not exercised
  - Test: `stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › G) Cross-tenant IDOR — stress_token must NOT mutate pilot resources`
  - Detay: GET /api/revenue-autopilot/queue?status=pending returned empty; cross-tenant approve guard not exercised this run.
- **[spa_operations]** Spa catalog surface module-blocked
  - Test: `stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › Setup: probe catalog surfaces + prefix`
  - Detay: services_http=403 therapists_http=403 rooms_http=403 — A/B/C/D/E skip, final invariants still enforced.
- **[vcc_pci_compliance]** No stress-seeded booking available for VCC attach
  - Test: `stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › Setup: harvest stress booking + probe VCC/PCI surfaces`
  - Detay: fetchAllByPrefix returned 0 bookings for prefix=E2E_STRESS_F7_1779886322643_. A/B/C/D/E skip; cleanup + final invariants still run.
- **[ws_tenant_isolation]** WS endpoint 404 — enterprise_live router mount yok
  - Test: `stress › 98B-websocket-tenant-isolation.spec.js › F8V § 98B — WebSocket Tenant Isolation › Setup: pilot baseline + ws lib probe + endpoint reachability`
  - Detay: A/B/C SKIP, D bağımsız.
- **[twofa_lifecycle]** Backup code /auth/2fa/verify path'inde kabul edilmedi — single-use davranışı sadece /disable+/regenerate üzerinden test edilebilir
  - Test: `stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › E) Backup code single-use — consume one → second use rejected`
  - Detay: status=429. Bu informational; single-use guard backup_hashes pop pattern üzerinden hash listesinden düşer (consume_backup_code).
- **[full_24h]** 24h sim data scarcity — F8 seed minimumun altinda
  - Test: `stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Setup: reachability probe + pilot baseline + stress inventory`
  - Detay: Bookings=0, rooms=0. F8 stres seed >=500 bekler. Phase-ler skip; invariant-lar kosar.

## 6) Performance Hotspots (top 10 slowest ops, p95)

| Modül | Op | n | p50 (ms) | p95 (ms) | max (ms) | avg (ms) |
|---|---|---:|---:|---:|---:|---:|
| reports_export | dashboard_kpi | 3 | 417 | 6652 | 6652 | 2495 |
| reports_export | pagination_cache | 5 | 612 | 3260 | 3260 | 1234 |
| accounting_expenses | list_accounting | 2 | 3246 | 3246 | 3246 | 2144 |
| reports_export | ops_reports_read | 7 | 1220 | 3182 | 3182 | 1490 |
| day-turnover | walkin_create | 50 | 2526 | 2630 | 3017 | 2146 |
| hr_payroll_lifecycle | draft_lifecycle | 5 | 921 | 2523 | 2523 | 1351 |
| accounting_expenses | bulk_create_accounting | 18 | 1499 | 2004 | 2004 | 1367 |
| finance_reports_currency | reports_read | 6 | 1203 | 1851 | 1851 | 1067 |
| day-turnover | checkout_force_true | 100 | 1755 | 1842 | 1946 | 1764 |
| hr_payroll_lifecycle | dryrun_idempotency | 2 | 1656 | 1656 | 1656 | 1616 |

## 7) Bulgular (REVIEW + SKIP detail)

### ❌ FAIL [cm_stop_sale_bulk_resolve] br_real_partial
- Test: `stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › G) Bulk-resolve — real partial-success (deterministic; seeded pending)`
- Endpoint: `-` HTTP=`-`
- Not: no_existing_pending — seed_pending_bookings did not populate a pending booking (expected ≥1)

### ❌ Test failure — stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › Setup: stress bookings + rooms snapshot + guarantee vacant pool
- File: `frontend/e2e-stress/specs/03-room-move.spec.js`  Süre: 44.8s
- Hata: Error: seed reported 60 extra room_move_target rooms but only 0 fetched — likely /api/pms/rooms projection drop or fetchAllByPrefix pagination/prefix-mismatch. Check room-move-setup-debug.json field_name_drift_check + seed_contract.    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeGreaterThanOrEqual[2m([22m[32mexpected[39m[2m)[22m  

### ❌ Test failure — stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › Setup: stress bookings + rooms snapshot + pilot baseline
- File: `frontend/e2e-stress/specs/05-reservation-lifecycle.spec.js`  Süre: 41.5s
- Hata: Error: Setup: stress room havuzu boş — seed eksik    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeGreaterThan[2m([22m[32mexpected[39m[2m)[22m  

### ❌ Test failure — stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › E) Mobile viewport smoke (390x844): tek HK transition + summary
- File: `frontend/e2e-stress/specs/08-housekeeping-mass.spec.js`  Süre: 0.0s
- Hata: Error: browserType.launch: Executable doesn't exist at /home/runner/workspace/.cache/ms-playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell  ╔════════════════════════════════════════════════════════════╗  ║ Looks like Playwright was just installed or updated.       ║  ║ Please run the following command to download new browsers: ║

### ❌ Test failure — stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › Setup: fetch rooms + seeded QR requests + pilot baseline
- File: `frontend/e2e-stress/specs/10-qr-requests.spec.js`  Süre: 2.5s
- Hata: Error: [2mexpect([22m[31mreceived[39m[2m).[22mtoBeGreaterThanOrEqual[2m([22m[32mexpected[39m[2m)[22m    Expected: >= [32m50[39m  Received:    [31m0[39m

### ❌ Test failure — stress › 12-complaints.spec.js › F8B § 12 — Service complaints › Setup: fetch seeded complaints + pilot baseline
- File: `frontend/e2e-stress/specs/12-complaints.spec.js`  Süre: 1.0s
- Hata: Error: [2mexpect([22m[31mreceived[39m[2m).[22mtoBeGreaterThanOrEqual[2m([22m[32mexpected[39m[2m)[22m    Expected: >= [32m20[39m  Received:    [31m0[39m

### ❌ Test failure — stress › 14-mice-events.spec.js › F8C § 14 — MICE Events › A) Catalog read: spaces, menus, accounts, events, diary
- File: `frontend/e2e-stress/specs/14-mice-events.spec.js`  Süre: 3.8s
- Hata: Error: [2mexpect([22m[31mreceived[39m[2m).[22mtoBeGreaterThan[2m([22m[32mexpected[39m[2m)[22m    Expected: > [32m0[39m  Received:   [31m0[39m

### ❌ Test failure — stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › G) Bulk-resolve — real partial-success (deterministic; seeded pending)
- File: `frontend/e2e-stress/specs/52B-cm-stop-sale-bulk-resolve.spec.js`  Süre: 0.0s
- Hata: Error: seed_pending_bookings must produce a pending_assignment booking    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeTruthy[2m()[22m  

### ❌ Test failure — stress › 72-warehouse-transfer-procurement.spec.js › F8F v2 § 72 — Warehouse Transfer + Procurement Hardening › A) Warehouse transfer endpoint — happy path + insufficient-source-stock 409
- File: `frontend/e2e-stress/specs/72-warehouse-transfer-procurement.spec.js`  Süre: 4.5s
- Hata: Error: transfer happy http=405 body={"detail":"Method Not Allowed"}    [2mexpect([22m[31mreceived[39m[2m).[22mtoBe[2m([22m[32mexpected[39m[2m) // Object.is equality[22m  

### ❌ Test failure — stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › invariants: probe coverage summary
- File: `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js`  Süre: 0.0s
- Hata: Error: Meaningful coverage too low: 8/51 (need ≥15). Çok fazla endpoint yok/erişilemez — bu spec gap'ı azaltmadı.    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeGreaterThanOrEqual[2m([22m[32mexpected[39m[2m)[22m  

### ❌ Test failure — stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › A) Create work order — stress-tenant scoped
- File: `frontend/e2e-stress/specs/98-maintenance-workorder-lifecycle.spec.js`  Süre: 0.7s
- Hata: Error: A_create unexpected status=500    [2mexpect([22m[31mreceived[39m[2m).[22mtoBeLessThan[2m([22m[32mexpected[39m[2m)[22m  

### ❌ Test failure — stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › A0) POST /api/folio/create (open lifecycle)
- File: `frontend/e2e-stress/specs/99-finance-folio-surface.spec.js`  Süre: 0.5s
- Hata: Error: A0_open unexpected status=400    [2mexpect([22m[31mreceived[39m[2m).[22mtoContain[2m([22m[32mexpected[39m[2m) // indexOf[22m  

### REVIEW (78)
- **[gates]** cm_outbox_backlog — Outbox stats endpoint bulunamadı; pilot sırasında manuel takip.
- **[gates]** circuit_breaker_snapshot — CB endpoint bulunamadı.
- **[bulk-seed-500]** outbox_no_unexpected — Outbox endpoint yok — manuel doğrula. (seed kodu domain event yayınlamıyor → REVIEW kabul edilebilir)
- **[folio-mass]** setup — bookings=0 folios=0 pilot_before=30 fallback=false bookings_with_folio_id=0
- **[ops_readiness]** backup_status — endpoint=/api/infra/backup/status last=null age_hours=n/a
- **[complaints]** setup — list_status=200 total_open=0 owned=0 pilot_before=30
- **[messaging]** conversations — conversations_len=0 max_ms=828
- **[finance_reports_currency]** perf:currency_lifecycle — n=6 p50=513ms p95=599ms max=599ms avg=496ms
- **[finance_reports_currency]** currency_lifecycle — rate ok=3/3 fail=0 | list=200 | conv ok=0/2 fail=2 | perm_fail=0 throttled_429=0 errs=[{"ep":"conv","status":422,"body":"{\"detail\":[{\"type\":\"missing\",\"loc\":[\"body\",\"from_currency\"],\"msg\":\"Field require"},{"ep":"conv","status":422,"body":"{\"detail\":[{\"type\":\"missing\",\"loc\":[\"body\",\"from_currency\"],\"msg\":\"Field require"}]
- **[hr_payroll_lifecycle]** perf:dryrun_idempotency — n=2 p50=1656ms p95=1656ms max=1656ms avg=1616ms
- **[hr_payroll_lifecycle]** dryrun_idempotency — r1_staff=325 r2_staff=315 r1_gross=0 r2_gross=0
- **[hr_shift_coverage_planning]** perf:idem_window — n=2 p50=655ms p95=655ms max=655ms avg=586ms
- **[hr_shift_coverage_planning]** idem_window — r1_status=200 r2_status=500 r1_id=0a1aa1e3 r2_id=undefined
- **[graphql_isolation]** introspection — introspection_open=true types=25 mutation_type=null
- **[cm_exely_webhook]** exely_readiness_gate — gate=prod_like_unset wl_set=false bypass=false hr_only=false auth_mode=fail_closed_503
- **[cm_exely_webhook]** valid_payload_idemp — auth_mode=fail_closed_503 — valid-payload path açık değil (fail_closed/ip_gated)
- **[cm_exely_webhook]** cancel_idemp — auth_mode=fail_closed_503 — cancel path açık değil
- **[cm_hotelrunner_webhook]** signed_valid_path — HOTELRUNNER_WEBHOOK_SECRET unset → signed-path coverage gap (stres ortamı prod-like değil)
- **[cm_outbox]** active_idempotency — HOTELRUNNER_WEBHOOK_SECRET unset → active dedupe assert edilemedi
- **[public_nps]** nps_duplicate_guard — Duplicate (aynı booking/guest/score) 2xx döndü — backend tasarımı kasıtlı (her manuel entry ayrı kayıt). F8K-v2: tek-survey-per-booking-day enforcement değerlendirilsin.
- **[public_kvkk]** kvkk_revoke_export_probe — revoke=404 export=404 (backend'de bu endpoint'ler yok; DELETE /requests/{id} tek revoke proxy. F8K-v2 backlog: dedicated revoke + export endpoint).
- **[identity_reporting_dryrun]** kbs_test_mode_prefix_guard — http=404 (KBS_TEST_MODE likely OFF; prefix check skipped, route reached job lookup)
- **[reports_export]** pii_masked_flag_observed — pii_masked=false (super_admin has_pii=true path, hard assertion gated). informational_pattern_scan=synthetic_pii_observed_count=60; no P0 emitted by design.
- **[backend_router_coverage_probe]** pos_fnb_menu — -
- **[backend_router_coverage_probe]** pos_fnb_modifiers — -
- **[backend_router_coverage_probe]** mobile_router_tasks — -
- **[backend_router_coverage_probe]** mobile_router_shift — -
- **[backend_router_coverage_probe]** dashboard_widgets — -
- **[backend_router_coverage_probe]** pms_groups — -
- **[backend_router_coverage_probe]** pms_catering — -
- **[backend_router_coverage_probe]** pms_approvals — -
- **[backend_router_coverage_probe]** pms_wakeup — -
- **[backend_router_coverage_probe]** hotelrunner_status — -
- **[backend_router_coverage_probe]** exely_status — -
- **[backend_router_coverage_probe]** cm_validation — -
- **[backend_router_coverage_probe]** cm_lockdown — -
- **[backend_router_coverage_probe]** cm_incident_list — -
- **[backend_router_coverage_probe]** cm_reconciliation — -
- **[backend_router_coverage_probe]** ai_upsell — -
- **[backend_router_coverage_probe]** ai_forecasting — -
- **[backend_router_coverage_probe]** ai_guest_pattern — -
- **[backend_router_coverage_probe]** ai_dynamic_offers — -
- **[backend_router_coverage_probe]** finance_mobile_cashier — -
- **[backend_router_coverage_probe]** finance_mobile_payments — -
- **[backend_router_coverage_probe]** guest_journey_list — -
- **[backend_router_coverage_probe]** guest_loyalty_status — -
- **[backend_router_coverage_probe]** guest_preferences — -
- **[backend_router_coverage_probe]** messaging_templates — -
- **[backend_router_coverage_probe]** messaging_settings — -
- **[backend_router_coverage_probe]** hr_leave_balance — -
- **[backend_router_coverage_probe]** hr_performance_reviews — -
- **[backend_router_coverage_probe]** hr_recruitment_postings — -
- **[backend_router_coverage_probe]** hr_training_catalog — -
- **[backend_router_coverage_probe]** hr_benefits_summary — -
- **[backend_router_coverage_probe]** admin_governance — -
- **[backend_router_coverage_probe]** admin_feature_flags — -
- **[backend_router_coverage_probe]** observability_traces — -
- **[backend_router_coverage_probe]** system_health_components — -
- **[backend_router_coverage_probe]** svc_laundry_status — -
- **[backend_router_coverage_probe]** svc_transport_status — -
- **[backend_router_coverage_probe]** svc_concierge_requests — -
- **[backend_router_coverage_probe]** svc_activities — -
- **[backend_router_coverage_probe]** svc_kids_club — -
- **[backend_router_coverage_probe]** integrations_whatsapp — -
- **[backend_router_coverage_probe]** reports_list — -
- **[backend_router_coverage_probe]** reports_scheduled — -
- **[fnb_beo]** perf:E2_beo_pdf — n=1 p50=431ms p95=431ms max=431ms avg=431ms
- **[fnb_beo]** E2_beo_pdf — -
- **[maintenance_workorder]** perf:A_create — n=1 p50=629ms p95=629ms max=629ms avg=629ms
- **[marketplace]** F_inventory — -
- **[marketplace]** perf:H_order — n=1 p50=714ms p95=714ms max=714ms avg=714ms
- **[marketplace]** H_order — -
- **[mobile_cashier]** L_pin_throttle — no throttle observed; statuses=[401,401,401,401,401,401,401]
- **[mobile_staff]** env_check — DISABLE_EXPO_PUSH != "1" — A-I SKIP (real-delivery guard), J/K independent.
- **[pos_deep_lifecycle]** transfer_happy_path — seed_http=200 happy_transfer_http=422 (gap documented, see P2)
- **[revenue_management]** ai_pricing_dry_run_probe — http=200 rates_published=3 (no dry_run gate)
- **[twofa_lifecycle]** backup_single_use — backup code not accepted on verify path status=429 — backend may restrict backup codes to /disable+/regenerate paths only.
- **[finance_folio]** perf:A0_open — n=1 p50=422ms p95=422ms max=422ms avg=422ms

### SKIP (130)
- **[folio-mass]** charge_sample — No folios reachable
- **[folio-mass]** payment_sample — -
- **[folio-mass]** split_sample — -
- **[folio-mass]** reconcile_sample — -
- **[folio-mass]** refund_sample — -
- **[folio-mass]** void_charge_sample — -
- **[folio-mass]** void_payment_sample — -
- **[folio-mass]** audit_sample — -
- **[folio-mass]** closed_guard — -
- **[housekeeping]** transitions_sample — rooms=0
- **[housekeeping]** ooo_sample — -
- **[housekeeping]** ooo_booking_guard — -
- **[service_requests]** bulk_patch — owned_open=0
- **[mice_execution]** beo_kitchen — no_event_harvested
- **[mice_execution]** ops_sheet — no_event_harvested
- **[mice_execution]** payment_schedule — no_event_harvested
- **[hr_staff_org]** list_org — module blocked (see Setup)
- **[hr_staff_org]** bulk_create_staff — module blocked (see Setup)
- **[hr_attendance]** records_summary — module blocked (see Setup)
- **[hr_attendance]** clock_in — module blocked (see Setup)
- **[hr_attendance]** clock_out — module blocked
- **[hr_leave]** list_requests — module blocked (see Setup)
- **[hr_leave]** create_requests — module blocked (see Setup)
- **[hr_leave]** decision — module blocked
- **[hr_shift]** list_swaps — module blocked (see Setup)
- **[hr_shift]** create_swaps — module blocked (see Setup)
- **[hr_shift]** consent_decision — module blocked
- **[hr_shift]** bulk_shifts — module blocked (see Setup)
- **[hr_shift]** overtime_payroll — module blocked (see Setup)
- **[admin_rbac]** super_admin_baseline — module blocked: admin_tenants_probe_endpoint_not_deployed_status_404
- **[admin_rbac]** rbac_catalog — module blocked: admin_tenants_probe_endpoint_not_deployed_status_404
- **[admin_rbac]** negative_matrix — module blocked: admin_tenants_probe_endpoint_not_deployed_status_404
- **[admin_rbac]** existence_disclosure — module blocked: admin_tenants_probe_endpoint_not_deployed_status_404
- **[settings_audit]** mutation — module blocked: admin_tenants_probe_endpoint_not_deployed_status_404
- **[settings_audit]** audit_trail — module blocked or mutation skipped
- **[settings_audit]** pilot_settings_drift — module_blocked=true pilot_snap_present=false
- **[settings_audit]** rate_limit_boundary — module blocked: admin_tenants_probe_endpoint_not_deployed_status_404
- **[settings_audit]** restore — no mutation to restore
- **[hr_perf]** list_reviews — module blocked: no_perf_reviews_in_pool
- **[hr_perf]** create_checkin — module blocked or empty pool
- **[hr_perf]** list_delete_checkins — module blocked or no created check-ins
- **[hr_perf]** staff_summary — module blocked or empty pool
- **[hr_perf]** create_review_lifecycle — module blocked: no_perf_reviews_in_pool
- **[hr_leave_accrual]** baseline_read — module blocked: no_stress_staff
- **[hr_leave_accrual]** approve_decrement — module blocked or empty baseline
- **[hr_leave_accrual]** carryover_upsert — module blocked
- **[hr_leave_accrual]** negative_balance_reject — module blocked
- **[hr_leave_accrual]** future_accrual_readonly — module blocked
- **[hr_shift_conflict]** create_s1 — module blocked: staff_pool_insufficient (0)
- **[hr_shift_conflict]** overlap_s2 — module blocked or no S1
- **[hr_shift_conflict]** overnight_overlap — module blocked: staff_pool_insufficient (0)
- **[hr_shift_conflict]** coverage — module blocked: staff_pool_insufficient (0)
- **[hr_shift_conflict]** cleanup_shifts — module blocked or nothing to clean (created=0)
- **[hr_shift_conflict]** coverage_rules — module blocked: staff_pool_insufficient (0)
- **[hr_rbac_pii]** rbac_matrix — module blocked: team_create_all_fail (front_desk → status=404 body={"detail":"Not Found"})
- **[hr_rbac_pii]** rbac_write_matrix — module blocked: team_create_all_fail (front_desk → status=404 body={"detail":"Not Found"})
- **[hr_rbac_pii]** staff_list_pii — module blocked: team_create_all_fail (front_desk → status=404 body={"detail":"Not Found"})
- **[hr_rbac_pii]** salary_history_guard — module blocked or empty pool
- **[hr_rbac_pii]** audit_scope — module blocked: team_create_all_fail (front_desk → status=404 body={"detail":"Not Found"})
- **[hr_rbac_pii]** cleanup_users — no users created
- **[hr_rbac_pii]** v2_foundation — module blocked: team_create_all_fail (front_desk → status=404 body={"detail":"Not Found"})
- **[hr_lifecycle_v2]** equipment_lifecycle — module blocked: pool_short_status_200_size_0_need_4
- **[hr_lifecycle_v2]** warning_lifecycle — module blocked: pool_short_status_200_size_0_need_4
- **[hr_lifecycle_v2]** training_lifecycle — module blocked: pool_short_status_200_size_0_need_4
- **[hr_employee_profile_detail]** profile_aggregate — module blocked: pool_short_status_200_size_0
- **[hr_employee_profile_detail]** specialty_surfaces — module blocked: pool_short_status_200_size_0
- **[hr_employee_profile_detail]** cross_tenant — module blocked: pool_short_status_200_size_0
- **[hr_offboarding]** cross_tenant_terminate — module blocked: no_stress_staff_status_200
- **[hr_offboarding]** termination_get — module blocked: no_stress_staff_status_200
- **[hr_offboarding]** outstanding_409_guard — module blocked: no_stress_staff_status_200
- **[b2b_api]** key_lifecycle — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** scope_assertions — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** extended_b2b_smoke — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** revoked_key — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** expired_wrong_tenant — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** existence_disclosure — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** collection_no_tid_leak — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** idor_matrix — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** auth_matrix — module blocked: no_stress_agency_in_list (len=0)
- **[b2b_api]** scope_per_subrouter — module blocked: no_stress_agency_in_list (len=0)
- **[ai_pricing]** cross_tenant_pricing — module blocked or no room types
- **[ai_noshow_risk]** cross_tenant_noshow — module blocked or no stress bookings
- **[notification_batch]** batch_enqueue — endpoint_not_deployed
- **[notification_batch]** logs_and_pii — endpoint_not_deployed
- **[notification_batch]** activity_feed — endpoint_not_deployed
- **[public_kvkk]** digital_key_dryrun — blocked: dk_probe_endpoint_not_deployed_status_404
- **[public_token_rotation]** tamper_contract — no_stress_room_harvest
- **[public_token_rotation]** cross_tenant_forge — no_stress_room_harvest
- **[public_token_rotation]** bulk_qr_pii — no_stress_room_harvest
- **[file_upload_security]** hk_photo_reject — hk blocked: no_stress_rooms
- **[kvkk_retention]** idphoto_xtenant_single_delete — pilot photo harvest empty
- **[kvkk_retention]** idphoto_xtenant_bulk_delete — pilot booking harvest empty
- **[export_artifact_idor]** cross_tenant_idor — all path-ID surfaces module-blocked: {"hr_payroll_run":"pilot_list_empty (len=0)"}
- **[reservation_deep]** waitlist_promote — module_blocked=true (insufficient_rooms_0)
- **[reservation_deep]** hold_create — -
- **[reservation_deep]** overbook_oversell — -
- **[reservation_deep]** overbook_yield — -
- **[reservation_deep]** multi_room_partial_cancel — -
- **[reservation_deep]** group_rooming_list — -
- **[reservation_deep]** rate_change — -
- **[reservation_deep]** split_reservation — -
- **[reservation_deep]** merge_guest — -
- **[reservation_deep]** noshow_fee — -
- **[reservation_deep]** cancel_fee_tier — -
- **[reservation_deep]** city_ledger_transfer — -
- **[cross_tenant_pentest]** pii_guard — caller_role=admin privileged — mask bypass per doctrine (KVKK least-privilege RBAC, not defense-in-depth). Coverage requires lower-trust token; tracked as roadmap backlog.
- **[accommodation_tax]** pilot_self_detail_export — pilot declaration pool empty — success-path detail/export not exercised
- **[accommodation_tax]** cross_tenant_idor_decl — pilot declaration harvest empty — decl IDOR target yok
- **[accommodation_tax]** idor_post_folio — pilot folio harvest empty
- **[marketplace]** I_cancel — no_po_created
- **[mobile_staff]** A_push_register — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** B_prefs_get — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** C_prefs_put — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** D_hv_create — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** E_hv_list — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** F_hv_open_count — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** G_hv_ack — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** H_inbox_list — DISABLE_EXPO_PUSH_not_1
- **[mobile_staff]** I_push_unregister — DISABLE_EXPO_PUSH_not_1
- **[payment_pos_reconciliation]** pos_tables_list_probe — module_blocked:endpoint_not_deployed http=404
- **[payment_pos_reconciliation]** folio_cross_tenant_payment — pilot folio harvest empty
- **[payment_pos_reconciliation]** manual_txn_idempotency — no open cashier shift (http=200, shift=null); idempotency probe requires active shift.
- **[revenue_management]** idor_hurdle — pilot hurdle harvest empty
- **[revenue_management]** idor_queue_approve — pilot queue empty
- **[spa_operations]** catalog_probe — module_blocked services=403 therapists=403 rooms=403
- **[vcc_pci_compliance]** booking_harvest — no stress bookings
- **[ws_tenant_isolation]** unauth_reject — module blocked: ws_endpoint_404
- **[ws_tenant_isolation]** valid_token_scope — module blocked: ws_endpoint_404
- **[ws_tenant_isolation]** cross_tenant_subscribe_spoof — module_blocked=true pilot_tid_present=true
- **[full_24h]** final_cleanup_snapshot — module-blocked: data scarcity bookings=0 rooms=0

## 7a) Broken Buttons / Wrong Business Rule (file:line + repro)

### ⚖️ Wrong Business Rule (26)
- **[P2] [ops_readiness] CM outbox depth endpoint reachable değil** — `frontend/e2e-stress/specs/09-ops-readiness-smoke.spec.js:156`
  - Test: `stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › C) CM outbox depth + conflict queue — within bounds`
  - Repro: tried=["/api/cm/outbox/stats","/api/cm/outbox/depth","/api/channel-manager/outbox/stats","/api/cm/health"] — observability sinyali eksik.
- **[P2] [admin_rbac] Admin tenants probe non-2xx** — `frontend/e2e-stress/specs/30-admin-rbac.spec.js:69`
  - Test: `stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › Setup: prefix + pilot baseline + super_admin team POST probe + per-role user create`
  - Repro: status=404 reason=endpoint_not_deployed — A/B/C skipped, D pilot_drift still enforced.
- **[P2] [settings_audit] Admin tenants probe non-2xx** — `frontend/e2e-stress/specs/31-settings-audit.spec.js:44`
  - Test: `stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › Setup: prefix + pilot baseline + tenants probe + snapshots`
  - Repro: status=404 reason=endpoint_not_deployed — A/B/C/D skipped, F pilot_drift still enforced.
- **[P2] [graphql_isolation] GraphQL introspection production stress'te açık** — `frontend/e2e-stress/specs/40-graphql-tenant-isolation.spec.js:119`
  - Test: `stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › A) Introspection policy + Mutation surface contract`
  - Repro: Schema introspection 2xx döndü (types=25). Production'da disable edilmesi önerilir; attack surface keşfi ücretsiz oluyor. Acceptance: REVIEW/P2 informational.
- **[P2] [graphql_isolation] Pilot GraphQL vs REST count discrepancy (informational)** — `frontend/e2e-stress/specs/40-graphql-tenant-isolation.spec.js:378`
  - Test: `stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › D) Auth boundary — unauthenticated + invalid token + wrong-tenant`
  - Repro: Pilot REST(limit=500)=50 bookings; GraphQL(limit=100)=100. GraphQL limit'e dayandı; REST status/date filtreleri farklı semantik. Tenant isolation kanıtı resolver tenant_id filtresi (schema.py:328) — leak değil, kıyas semantik farkı.
- **[P2] [b2b_api] Stress tenant'a ait agency bulunamadı** — `frontend/e2e-stress/specs/41-b2b-api-key-scope.spec.js:56`
  - Test: `stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › Setup: prefix + pilot baseline + agencies probe + create stress API key`
  - Repro: agencies_list_len=0 — seed agency yok; API key create akışı yapılamıyor. A/B/C/D skipped.
- **[P2] [b2b_api] Stress tenant agency yok (v2 matrix)** — `frontend/e2e-stress/specs/41B-b2b-subrouter-matrix.spec.js:108`
  - Test: `stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › Setup: pilot baseline + stress agency + create key + pilot id sampling`
  - Repro: agencies_list_len=0 — matrix tests skipped.
- **[P2] [cm_exely_webhook] Exely valid-payload + idempotency coverage gap** — `frontend/e2e-stress/specs/50-cm-webhooks-exely.spec.js:391`
  - Test: `stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › G) Conditional valid payload + duplicate ingest idempotency (auth-mode=open_for_testing veya EXELY_IP_WHITELIST set)`
  - Repro: auth_mode=fail_closed_503. Bu koşuda valid parse path test edilemedi; production-like ortamda (whitelist + caller IP) test sürdürülmeli.
- **[P2] [cm_exely_webhook] Exely cancellation idempotency coverage gap** — `frontend/e2e-stress/specs/50-cm-webhooks-exely.spec.js:455`
  - Test: `stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › H) Conditional cancellation idempotency — aynı reservation_id cancel 2x → tek state geçişi (auth-mode=open)`
  - Repro: auth_mode=fail_closed_503. Whitelisted prod env'de cancel duplicate 2x test sürdürülmeli.
- **[P2] [cm_hotelrunner_webhook] HotelRunner signed-path coverage gap — stres env'de HOTELRUNNER_WEBHOOK_SECRET set değil** — `frontend/e2e-stress/specs/51-cm-hotelrunner-outbox.spec.js:366`
  - Test: `stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › F) Signed valid-path — HOTELRUNNER_WEBHOOK_SECRET set ise gerçek HMAC payload kabul edilmeli (stress_tid scope, dispatcher dry-run)`
  - Repro: Imzasız reddetme contract'ı PASS; valid HMAC kabul path'i bu koşuda assert edilemedi. Production readiness için CI env'inde secret seed'i öneriliyor (follow-up: gerçek imzalı yük testi).
- **[P2] [cm_outbox] Outbox active idempotency coverage gap — secret unset** — `frontend/e2e-stress/specs/52-cm-outbox-idempotency.spec.js:262`
  - Test: `stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › E) Active idempotency — duplicate signed webhook ingest → outbox event delta ≤ 1 (HOTELRUNNER_WEBHOOK_SECRET conditional)`
  - Repro: Passive delta (Test A) PASS; aktif duplicate-dispatch dedupe path'i bu koşuda assert edilemedi. Production readiness için CI env'inde HOTELRUNNER_WEBHOOK_SECRET seed'i öneriliyor (follow-up: aktif idempotency).
- **[P2] [identity_reporting_dryrun] KBS_TEST_MODE prefix guard not enforced (env likely off)** — `frontend/e2e-stress/specs/65-identity-reporting-kbs-jandarma-dryrun.spec.js:71`
  - Test: `stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS_TEST_MODE prefix guard + queue schema enforcement`
  - Repro: POST /api/kbs/queue/.../complete with no TEST- prefix → http=404. If KBS_TEST_MODE=1 expected 422 with "TEST-" mention; route reached job-not-found instead. Env state review needed.
- **[P2] [crm_offers] Duplicate-email guard surface absent on mice_accounts** — `frontend/e2e-stress/specs/80-crm-offers-contracts.spec.js:119`
  - Test: `stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › A) Account CRUD + duplicate-tax-no guard probe`
  - Repro: mice_accounts payload (AccountIn) has no email field, so duplicate-email guard not applicable at account level. Contact-level email also has no unique constraint. Informational gap recorded.
- **[P2] [crm_offers] No native contract approval state machine** — `frontend/e2e-stress/specs/80-crm-offers-contracts.spec.js:442`
  - Test: `stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › D) Corporate contract dry-run lifecycle (create + update)`
  - Repro: Backend POST /api/sales/corporate-contract hard-codes status="active"; PUT update does not expose approval lifecycle (draft→review→approved→signed) as a first-class field. Spec simulates the transition via notes payload. Informational gap — not blocking.
- **[P2] [cross_tenant_pentest] surface_blocked:folios** — `frontend/e2e-stress/specs/96-cross-tenant-pentest.spec.js:115`
  - Test: `stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › Setup: prefix + pilot baseline + surface probes + pilot sample ID harvest`
  - Repro: endpoint=/api/folios?limit=50 status=404 reason=endpoint_not_deployed — list/PII tests skip, IDOR + pilot_drift bağımsız.
- **[P2] [cross_tenant_pentest] surface_blocked:folio_charges** — `frontend/e2e-stress/specs/96-cross-tenant-pentest.spec.js:115`
  - Test: `stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › Setup: prefix + pilot baseline + surface probes + pilot sample ID harvest`
  - Repro: endpoint=/api/folio-charges?limit=50 status=404 reason=endpoint_not_deployed — list/PII tests skip, IDOR + pilot_drift bağımsız.
- **[P2] [backend_router_coverage_probe] Router dashboard_widgets: auth_404_not_deployed** — `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js:192`
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: dashboard_widgets (/api/pms/dashboard/widgets)`
  - Repro: path=/api/pms/dashboard/widgets anon=404 auth=404
- **[P2] [backend_router_coverage_probe] Router reports_list: auth_404_not_deployed** — `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js:192`
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: reports_list (/api/reports/list)`
  - Repro: path=/api/reports/list anon=404 auth=404
- **[P2] [backend_router_coverage_probe] Router reports_scheduled: auth_404_not_deployed** — `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js:192`
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: reports_scheduled (/api/reports/scheduled)`
  - Repro: path=/api/reports/scheduled anon=404 auth=404
- **[P2] [marketplace] inventory non-200 status=404** — `frontend/e2e-stress/specs/98-marketplace-deep-lifecycle.spec.js:314`
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › F) Inventory check — GET marketplace/inventory`
  - Repro: -
- **[P2] [marketplace] purchase-orders POST non-2xx status=404** — `frontend/e2e-stress/specs/98-marketplace-deep-lifecycle.spec.js:364`
  - Test: `stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › H) Order place — POST purchase-orders`
  - Repro: body={"detail":"Not Found"}
- **[P2] [webhook_admin_dlq] webhook-admin endpoint not deployed** — `frontend/e2e-stress/specs/98-ops-surface-smoke.spec.js:247`
  - Test: `stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › C) webhook_admin_dlq — global status smoke + non-super-admin 403 + cross-tenant filter`
  - Repro: GET /api/webhooks/status http=404 — module not mounted; suite SKIP.
- **[P2] [payment_pos_reconciliation] Manual transaction idempotency probe skipped** — `frontend/e2e-stress/specs/98-payment-pos-reconciliation-dryrun.spec.js:165`
  - Test: `stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › manual-transaction X-Idempotency-Key replay`
  - Repro: Cashier current-shift http=200 body.shift=null; cannot exercise X-Idempotency-Key replay without active shift.
- **[P2] [pos_deep_lifecycle] transfer-table happy-path structurally unreachable** — `frontend/e2e-stress/specs/98-pos-deep-lifecycle.spec.js:308`
  - Test: `stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › E) Table-transfer: happy-path attempt + bogus 404 + cross-tenant guard`
  - Repro: No production write surface creates pos_transactions.status='open'. Seed via /pos/transaction (status='completed') produced http=200; subsequent transfer-table call http=422 (expected 404 because filter requires status='open'). Backend gap — transfer-table is dead-code for v2 lifecycle until an "open-tab" surface is added. Compensating: negative-contract + cross-tenant guard tested below.
- **[P2] [pos_kds_inventory] Inventory deplete happy path skipped — no recipe seed** — `frontend/e2e-stress/specs/98-pos-kds-inventory.spec.js:411`
  - Test: `stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › E) Inventory deplete happy path (recipe → close → inventory_items decrement)`
  - Repro: Stress tenant has no recipes/BOM; Task #11 leaves seeding out of scope. Step recorded as P2 REVIEW (not fake PASS).
- **[P2] [vcc_pci_compliance] No stress-seeded booking available for VCC attach** — `frontend/e2e-stress/specs/98-vcc-pci-compliance.spec.js:118`
  - Test: `stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › Setup: harvest stress booking + probe VCC/PCI surfaces`
  - Repro: fetchAllByPrefix returned 0 bookings for prefix=E2E_STRESS_F7_1779886322643_. A/B/C/D/E skip; cleanup + final invariants still run.

### 🖱️ Broken Buttons / UI (6)
- **[P2] [cm_exely_webhook] Exely readiness gate prod_like_unset (informational)** — `frontend/e2e-stress/specs/50-cm-webhooks-exely.spec.js:336`
  - Test: `stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › F) EXELY readiness gate — env contract semantics (configured PASS / HR-only N/A / prod-like unset P2 informational / bypass P1)`
  - Repro: EXELY_IP_WHITELIST set değil + bypass yok — fail-closed 503 contract honored. Production deploy öncesi CI/CD env'inde whitelist seed'i zorunlu.
- **[P2] [backend_router_coverage_probe] Router messaging_settings: auth_404_not_deployed** — `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js:192`
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: messaging_settings (/api/messaging/settings)`
  - Repro: path=/api/messaging/settings anon=404 auth=404
- **[P2] [backend_router_coverage_probe] Router hr_recruitment_postings: auth_404_not_deployed** — `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js:192`
  - Test: `stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_recruitment_postings (/api/hr/recruitment/postings)`
  - Repro: path=/api/hr/recruitment/postings anon=404 auth=404
- **[P1] [mobile_cashier] Cashier handover PIN/password gate has NO brute-force throttle** — `frontend/e2e-stress/specs/98-mobile-cashier-surface.spec.js:371`
  - Test: `stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › L) PIN brute-force throttle probe`
  - Repro: 7 wrong-credential attempts produced statuses=[401,401,401,401,401,401,401]; expected 429 by attempt 7. Financial gate must rate-limit.
- **[P1] [mobile_staff] Mobile staff stress requires DISABLE_EXPO_PUSH=1** — `frontend/e2e-stress/specs/98-mobile-staff-surface.spec.js:88`
  - Test: `stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › Setup: stress token + module probe + pilot baseline`
  - Repro: Runner env not set; lifecycle batch SKIPped to prevent real Expo delivery.
- **[P2] [revenue_management] ai-pricing auto-publish lacks server-side dry_run gate** — `frontend/e2e-stress/specs/98-rms-revenue-deep.spec.js:471`
  - Test: `stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › F) AI pricing auto-publish — dry_run gate + post-batch external_calls=0`
  - Repro: POST .../auto-publish-rates accepted dry_run=true query param without distinct behaviour (rates_published=3). Backend has no dry_run kill-switch — operator must rely on external_calls invariant (no real channel HTTP this run) + caller-side gating. Feature request: add explicit dry_run server flag suppressing rate-calendar writes + outbox events.

## 7b) Cleanup Integrity

| Adım | Durum | Detay |
|---|---|---|
| cleanup#1 (deletion) | ✅ OK | deleted_total=n/a |
| cleanup#2 (idempotency) | ✅ idempotent | re-run deleted=n/a |
| pilot drift | ✅ drift=0 | baseline=[object Object] after=[object Object] |

_Audit logs are NEVER deleted (KVKK retention) — bu liste sadece stress-seeded business data'yı kapsar._

## 8) Test inventory

| # | Test | Outcome | Süre |
|---:|---|---|---:|
| 1 | stress › 00-gates.spec.js › F7 § Stress Gates › Login: stress admin token cache hazır | ✅ passed | 0.0s |
| 2 | stress › 00-gates.spec.js › F7 § Stress Gates › Tenant: stress tenant id env eşleşiyor | ✅ passed | 0.0s |
| 3 | stress › 00-gates.spec.js › F7 § Stress Gates › Flag: E2E_ALLOW_DESTRUCTIVE_STRESS=true | ✅ passed | 0.0s |
| 4 | stress › 00-gates.spec.js › F7 § Stress Gates › Flag: E2E_EXTERNAL_DRY_RUN=true | ✅ passed | 0.0s |
| 5 | stress › 00-gates.spec.js › F7 § Stress Gates › Pilot: pilot tenant hedeflenmiyor (config & runtime) | ✅ passed | 0.0s |
| 6 | stress › 00-gates.spec.js › F7 § Stress Gates › Seed response: external_calls_made boş | ✅ passed | 0.0s |
| 7 | stress › 00-gates.spec.js › F7 § Stress Gates › Seed response: tenant_context kullanıldı | ✅ passed | 0.0s |
| 8 | stress › 00-gates.spec.js › F7 § Stress Gates › Seed response: gates dict tüm kapı PASS | ✅ passed | 0.0s |
| 9 | stress › 00-gates.spec.js › F7 § Stress Gates › System health: en az REVIEW seviyesinde (best-effort) | ✅ passed | 0.7s |
| 10 | stress › 00-gates.spec.js › F7 § Stress Gates › CM outbox backlog: snapshot (best-effort) | ✅ passed | 2.1s |
| 11 | stress › 00-gates.spec.js › F7 § Stress Gates › Circuit breaker: başlangıç snapshot (best-effort) | ✅ passed | 0.7s |
| 12 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Seed response counts: rooms=guests=bookings=folios=500 + extra room-move pool | ✅ passed | 0.0s |
| 13 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Seed response counts: housekeeping_tasks=500 | ✅ passed | 0.0s |
| 14 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Seed response counts: room_night_locks beklenen aralıkta | ✅ passed | 0.0s |
| 15 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Seed response counts: folio_charges ≥ 2*N (per-night room + acc-tax) | ✅ passed | 0.0s |
| 16 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Seed performance: 500-oda toplam < 30s | ✅ passed | 0.0s |
| 17 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Variety: 20 room_types × 5 blocks × 10 floors meta | ✅ passed | 0.0s |
| 18 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Stress tenant rooms endpoint sızıntısız cevap (stress bearer) | ✅ passed | 1.1s |
| 19 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Stress tenant bookings endpoint sızıntısız cevap (stress bearer) | ✅ passed | 1.3s |
| 20 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Stress tenant guests endpoint sızıntısız cevap (stress bearer) | ✅ passed | 0.5s |
| 21 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Pilot tenant counts değişmedi (mutation=0) | ✅ passed | 0.5s |
| 22 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › External calls = [] korundu | ✅ passed | 0.0s |
| 23 | stress › 01-bulk-seed-500.spec.js › F7 § Bulk Seed 500 — entity counts › Outbox unexpected event yok (best-effort) | ✅ passed | 0.8s |
| 24 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › Setup: stress bookings + rooms listele, pilot drift baseline | ✅ passed | 44.5s |
| 25 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › A) Open-folio guard: 20 checkout (force=false) → 400 bekle | ✅ passed | 17.7s |
| 26 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › B) Force checkout batch: 100 booking (force=true) | ✅ passed | 176.4s |
| 27 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › B-post) external_calls invariant after force_checkout_batch (runtime endpoint) | ✅ passed | 1.0s |
| 28 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › C) Same-day turnover: 50 walk-in (boşalan oda → yeni booking) | ✅ passed | 144.1s |
| 29 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › D) Pilot drift: spec sonu pilot bookings sayımı = baseline | ✅ passed | 0.4s |
| 30 | stress › 02-day-turnover.spec.js › F8A § 02 — Day turnover (checkout + walk-in + guard) › E) External calls: stress seed snapshot hala [] | ✅ passed | 0.0s |
| 31 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › Setup: stress bookings + rooms snapshot + guarantee vacant pool | ❌ failed | 44.8s |
| 32 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › A) Positive room-move: 50 (booking → vacant + same-category target) + post-move state transfer | ⏭️ skipped | 0.0s |
| 33 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › B) Negative — occupied target reject | ⏭️ skipped | 0.0s |
| 34 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › C) Negative — OOO target reject | ⏭️ skipped | 0.0s |
| 35 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › D) Race — aynı hedefe paralel iki move | ⏭️ skipped | 0.0s |
| 36 | stress › 03-room-move.spec.js › F8A § 03 — Room move (positive + negative + race) › E) Pilot drift = 0 | ⏭️ skipped | 0.0s |
| 37 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › Setup: stress folios + bookings list | ✅ passed | 37.5s |
| 38 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › A) 100 folio charge POST (mini-bar, restaurant, other) | ✅ passed | 0.0s |
| 39 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › B) 50 dry-run payment POST (cash, reference="F8A_DRY_RUN") | ✅ passed | 0.0s |
| 40 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › C) Folio split-by-amount (10 folio) | ✅ passed | 0.0s |
| 41 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › C2) Total mismatch detector: sum(charges) == folio.total (10 folio) | ✅ passed | 0.0s |
| 42 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › C3) Open-folio refund dry-run (10 folio) | ✅ passed | 0.0s |
| 43 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › C4) Void charge (5 folio — fetch charge_id via detail) | ✅ passed | 0.0s |
| 44 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › C5) Void payment (5 folio — fetch payment_id via detail) | ✅ passed | 0.0s |
| 45 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › D) Folio audit GET (5 folio) | ✅ passed | 0.0s |
| 46 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › E) Closed folio guard: checkout sonrası charge reddi | ✅ passed | 0.0s |
| 47 | stress › 04-folio-mass.spec.js › F8A § 04 — Folio mass (charge / payment / split / audit / closed-guard) › F) Pilot drift = 0 | ✅ passed | 0.4s |
| 48 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › Setup: stress bookings + rooms snapshot + pilot baseline | ❌ failed | 41.5s |
| 49 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › A) 10 reservation create (future dates, quick-booking) | ⏭️ skipped | 0.0s |
| 50 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › B) 5 modify dates (PUT booking) | ⏭️ skipped | 0.0s |
| 51 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › C) 5 cancel | ⏭️ skipped | 0.0s |
| 52 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › D) 3 no-show conversion | ⏭️ skipped | 0.0s |
| 53 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › E) Overbooking guard: aynı oda + dolu tarih → conflict tespit | ⏭️ skipped | 0.0s |
| 54 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › F) Group reservation create | ⏭️ skipped | 0.0s |
| 55 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › G) Multi-room booking (1 guest, 3 rooms) | ⏭️ skipped | 0.0s |
| 56 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › H) External calls invariant after lifecycle batch | ⏭️ skipped | 0.0s |
| 57 | stress › 05-reservation-lifecycle.spec.js › F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room) › I) Pilot drift = 0 | ⏭️ skipped | 0.0s |
| 58 | stress › 06-night-audit.spec.js › F8A § 06 — Night audit (business-date / run / re-run idempotency / exceptions) › Setup: business-date GET + pilot baseline | ✅ passed | 1.0s |
| 59 | stress › 06-night-audit.spec.js › F8A § 06 — Night audit (business-date / run / re-run idempotency / exceptions) › A) Night audit run (business_date current) | ✅ passed | 61.4s |
| 60 | stress › 06-night-audit.spec.js › F8A § 06 — Night audit (business-date / run / re-run idempotency / exceptions) › B) Re-run idempotency (same business_date → duplicate posting yok) | ✅ passed | 57.2s |
| 61 | stress › 06-night-audit.spec.js › F8A § 06 — Night audit (business-date / run / re-run idempotency / exceptions) › C) Exceptions list GET | ✅ passed | 2.5s |
| 62 | stress › 06-night-audit.spec.js › F8A § 06 — Night audit (business-date / run / re-run idempotency / exceptions) › D) External calls invariant after NA batch | ✅ passed | 1.0s |
| 63 | stress › 06-night-audit.spec.js › F8A § 06 — Night audit (business-date / run / re-run idempotency / exceptions) › E) Pilot drift = 0 | ✅ passed | 0.6s |
| 64 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › Setup: stress rooms + summary baseline | ✅ passed | 1.6s |
| 65 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › A) HK summary endpoint: <2s p95 | ✅ passed | 2.6s |
| 66 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › B) 500-oda HK list endpoint render performansı | ✅ passed | 1.4s |
| 67 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › C) 100 oda HK transitions (dirty→cleaning→inspected→clean) | ✅ passed | 0.0s |
| 68 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › D) 20 oda OOO işaretle + summary diff | ✅ passed | 0.0s |
| 69 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › D2) OOO booking-guard: OOO odaya walk-in / new-booking attempt → reject | ✅ passed | 0.0s |
| 70 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › E) Mobile viewport smoke (390x844): tek HK transition + summary | ❌ failed | 0.0s |
| 71 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › G) FE render TTI: /housekeeping desktop + mobile (real DOM, 50/200/500 row scaling) | ⏭️ skipped | 0.0s |
| 72 | stress › 08-housekeeping-mass.spec.js › F8A § 08 — Housekeeping mass (render + transitions + OOO + summary) › F) Pilot drift = 0 | ⏭️ skipped | 0.0s |
| 73 | stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › Setup: pilot baseline | ✅ passed | 0.5s |
| 74 | stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › A) Health endpoints — /health, /health/ready, /api/health all 200 | ✅ passed | 2.2s |
| 75 | stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › B) Backup status not stale — last backup age within threshold | ✅ passed | 1.3s |
| 76 | stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › C) CM outbox depth + conflict queue — within bounds | ✅ passed | 4.1s |
| 77 | stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › D) Cache warmer + WS hub + observability — alive signals | ✅ passed | 2.8s |
| 78 | stress › 09-ops-readiness-smoke.spec.js › F8W § 09 — Ops Readiness Smoke › E) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.3s |
| 79 | stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › Setup: fetch rooms + seeded QR requests + pilot baseline | ❌ failed | 2.5s |
| 80 | stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › A) 50 public QR submit (different rooms — under per-room RL) | ⏭️ skipped | 0.0s |
| 81 | stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › B) 30 staff status transitions (new→assigned→in_progress→completed) | ⏭️ skipped | 0.0s |
| 82 | stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › C) SLA / overdue surface: stats summary returns non-trivial distribution | ⏭️ skipped | 0.0s |
| 83 | stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › D) Token guard: invalid token → 403; cross-tenant token → 403 | ⏭️ skipped | 0.0s |
| 84 | stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › E) external_calls invariant post-suite | ⏭️ skipped | 0.0s |
| 85 | stress › 10-qr-requests.spec.js › F8B § 10 — Room QR requests › F) Pilot drift = 0 | ⏭️ skipped | 0.0s |
| 86 | stress › 11-service-requests.spec.js › F8B § 11 — Service requests staff view › Setup: prefix + pilot baseline | ✅ passed | 0.5s |
| 87 | stress › 11-service-requests.spec.js › F8B § 11 — Service requests staff view › A) Staff list pagination — limit & status filter coverage | ✅ passed | 2.0s |
| 88 | stress › 11-service-requests.spec.js › F8B § 11 — Service requests staff view › B) Bulk PATCH — 20 priority bump (assigned) | ✅ passed | 1.2s |
| 89 | stress › 11-service-requests.spec.js › F8B § 11 — Service requests staff view › C) Filter combinations: department / room_id scoping | ✅ passed | 1.4s |
| 90 | stress › 11-service-requests.spec.js › F8B § 11 — Service requests staff view › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 91 | stress › 12-complaints.spec.js › F8B § 12 — Service complaints › Setup: fetch seeded complaints + pilot baseline | ❌ failed | 1.0s |
| 92 | stress › 12-complaints.spec.js › F8B § 12 — Service complaints › A) 30 resolve with compensation (folio adjustment local) | ⏭️ skipped | 0.0s |
| 93 | stress › 12-complaints.spec.js › F8B § 12 — Service complaints › B) Summary stats endpoint reachable + non-trivial | ⏭️ skipped | 0.0s |
| 94 | stress › 12-complaints.spec.js › F8B § 12 — Service complaints › C) Compensation report endpoint (post-resolve breakdown) | ⏭️ skipped | 0.0s |
| 95 | stress › 12-complaints.spec.js › F8B § 12 — Service complaints › D) Pilot drift = 0 | ⏭️ skipped | 0.0s |
| 96 | stress › 13-messaging.spec.js › F8B § 13 — Messaging dry-run › Setup: pilot baseline + prefix | ✅ passed | 0.6s |
| 97 | stress › 13-messaging.spec.js › F8B § 13 — Messaging dry-run › A) 50 send: 20 email + 15 sms + 15 whatsapp (lokal-only) | ✅ passed | 62.4s |
| 98 | stress › 13-messaging.spec.js › F8B § 13 — Messaging dry-run › B) Conversations read endpoint reachable + paginated | ✅ passed | 2.2s |
| 99 | stress › 13-messaging.spec.js › F8B § 13 — Messaging dry-run › C) External-calls=[] suite-final invariant | ✅ passed | 0.8s |
| 100 | stress › 13-messaging.spec.js › F8B § 13 — Messaging dry-run › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 101 | stress › 14-mice-events.spec.js › F8C § 14 — MICE Events › Setup: prefix + pilot baseline + space catalog | ✅ passed | 2.7s |
| 102 | stress › 14-mice-events.spec.js › F8C § 14 — MICE Events › A) Catalog read: spaces, menus, accounts, events, diary | ❌ failed | 3.8s |
| 103 | stress › 14-mice-events.spec.js › F8C § 14 — MICE Events › B) Bulk create — N events status=lead, unique (space, date) | ⏭️ skipped | 0.0s |
| 104 | stress › 14-mice-events.spec.js › F8C § 14 — MICE Events › C) Status transitions: lead → tentative → definite | ⏭️ skipped | 0.0s |
| 105 | stress › 14-mice-events.spec.js › F8C § 14 — MICE Events › D) Payment schedule replace + mark-paid (DB-only) | ⏭️ skipped | 0.0s |
| 106 | stress › 14-mice-events.spec.js › F8C § 14 — MICE Events › E) Pilot drift = 0 | ⏭️ skipped | 0.0s |
| 107 | stress › 15-sales-opportunities.spec.js › F8C § 15 — Sales-catering Opportunities › Setup: prefix + pilot baseline + module access probe | ✅ passed | 1.5s |
| 108 | stress › 15-sales-opportunities.spec.js › F8C § 15 — Sales-catering Opportunities › A) List + pipeline aggregation read | ✅ passed | 1.8s |
| 109 | stress › 15-sales-opportunities.spec.js › F8C § 15 — Sales-catering Opportunities › B) Bulk create — N opportunities (stage=lead) | ✅ passed | 22.4s |
| 110 | stress › 15-sales-opportunities.spec.js › F8C § 15 — Sales-catering Opportunities › C) Stage transitions: lead → qualified → proposal → contract | ✅ passed | 67.6s |
| 111 | stress › 15-sales-opportunities.spec.js › F8C § 15 — Sales-catering Opportunities › D) Activity log — 1 activity per created opp | ✅ passed | 23.2s |
| 112 | stress › 15-sales-opportunities.spec.js › F8C § 15 — Sales-catering Opportunities › E) Pilot drift = 0 | ✅ passed | 0.4s |
| 113 | stress › 16-sales-leads.spec.js › F8C § 16 — Sales Leads › Setup: prefix + pilot baseline | ✅ passed | 0.4s |
| 114 | stress › 16-sales-leads.spec.js › F8C § 16 — Sales Leads › A) List + funnel aggregation read | ✅ passed | 1.8s |
| 115 | stress › 16-sales-leads.spec.js › F8C § 16 — Sales Leads › B) Bulk create — N leads | ✅ passed | 22.0s |
| 116 | stress › 16-sales-leads.spec.js › F8C § 16 — Sales Leads › C) Stage transitions: new → contacted → qualified → proposal_sent | ✅ passed | 68.0s |
| 117 | stress › 16-sales-leads.spec.js › F8C § 16 — Sales Leads › D) Activity log — 1 per created lead | ✅ passed | 24.0s |
| 118 | stress › 16-sales-leads.spec.js › F8C § 16 — Sales Leads › E) Pilot drift = 0 | ✅ passed | 0.4s |
| 119 | stress › 17-banquet-competitor.spec.js › F8C § 17 — Banquet Competitor › Setup: prefix + pilot baseline | ✅ passed | 0.4s |
| 120 | stress › 17-banquet-competitor.spec.js › F8C § 17 — Banquet Competitor › A) List competitors + positioning aggregation read | ✅ passed | 1.8s |
| 121 | stress › 17-banquet-competitor.spec.js › F8C § 17 — Banquet Competitor › B) Bulk create competitors | ✅ passed | 11.0s |
| 122 | stress › 17-banquet-competitor.spec.js › F8C § 17 — Banquet Competitor › C) Bulk rate snapshots — RATES_PER per competitor | ✅ passed | 31.5s |
| 123 | stress › 17-banquet-competitor.spec.js › F8C § 17 — Banquet Competitor › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 124 | stress › 18-mice-execution-beo.spec.js › F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet) › Setup: prefix + pilot baseline + stress event harvest + MICE probe | ✅ passed | 1.0s |
| 125 | stress › 18-mice-execution-beo.spec.js › F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet) › A) BEO + kitchen-ticket read — response shape + PII mask + cross-tenant guard | ⏭️ skipped | 0.0s |
| 126 | stress › 18-mice-execution-beo.spec.js › F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet) › B) Ops-sheet (event-day checklist) read + cross-tenant scope | ⏭️ skipped | 0.0s |
| 127 | stress › 18-mice-execution-beo.spec.js › F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet) › C) Payment schedule consistency probe (read-only — no mark-paid) | ⏭️ skipped | 0.0s |
| 128 | stress › 18-mice-execution-beo.spec.js › F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet) › D) Missing endpoint REVIEW (F&B send) + final invariants | ✅ passed | 1.3s |
| 129 | stress › 20-hr-staff-org.spec.js › F8D § 20 — HR Staff Org › Setup: prefix + pilot baseline + module probe | ✅ passed | 1.5s |
| 130 | stress › 20-hr-staff-org.spec.js › F8D § 20 — HR Staff Org › A) List staff + departments + positions | ⏭️ skipped | 0.0s |
| 131 | stress › 20-hr-staff-org.spec.js › F8D § 20 — HR Staff Org › B) Bulk create staff | ⏭️ skipped | 0.0s |
| 132 | stress › 20-hr-staff-org.spec.js › F8D § 20 — HR Staff Org › C) Pilot drift = 0 | ✅ passed | 0.4s |
| 133 | stress › 21-hr-attendance.spec.js › F8D § 21 — HR Attendance › Setup: prefix + pilot baseline + staff pool | ✅ passed | 1.4s |
| 134 | stress › 21-hr-attendance.spec.js › F8D § 21 — HR Attendance › A) Attendance records list + summary read | ⏭️ skipped | 0.0s |
| 135 | stress › 21-hr-attendance.spec.js › F8D § 21 — HR Attendance › B) Clock-in N=5 staff | ⏭️ skipped | 0.0s |
| 136 | stress › 21-hr-attendance.spec.js › F8D § 21 — HR Attendance › C) Clock-out same staff | ✅ passed | 0.0s |
| 137 | stress › 21-hr-attendance.spec.js › F8D § 21 — HR Attendance › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 138 | stress › 22-hr-leave.spec.js › F8D § 22 — HR Leave › Setup: prefix + pilot baseline + staff pool + balance probe | ✅ passed | 1.4s |
| 139 | stress › 22-hr-leave.spec.js › F8D § 22 — HR Leave › A) Leave requests list | ⏭️ skipped | 0.0s |
| 140 | stress › 22-hr-leave.spec.js › F8D § 22 — HR Leave › B) Create N=5 leave requests | ⏭️ skipped | 0.0s |
| 141 | stress › 22-hr-leave.spec.js › F8D § 22 — HR Leave › C) Decision (approve/reject) | ✅ passed | 0.0s |
| 142 | stress › 22-hr-leave.spec.js › F8D § 22 — HR Leave › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 143 | stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › Setup: prefix + pilot baseline + staff pool + shift pool | ✅ passed | 3.6s |
| 144 | stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › A) Shift swap list read | ⏭️ skipped | 0.0s |
| 145 | stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › B) Create N=5 shift swap requests | ⏭️ skipped | 0.0s |
| 146 | stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › C) Consent + decision lifecycle | ✅ passed | 0.0s |
| 147 | stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › F) Bulk shift create probe (Task #263 v2) | ⏭️ skipped | 0.0s |
| 148 | stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › G) Overtime ready-for-payroll contract (Task #263 v2) | ⏭️ skipped | 0.0s |
| 149 | stress › 23-hr-shift.spec.js › F8D § 23 — HR Shift › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 150 | stress › 24-cashier-shift.spec.js › F8E § 24 — Cashier Shift Lifecycle › Setup: prefix + pilot baseline + module probe + residual close | ✅ passed | 0.9s |
| 151 | stress › 24-cashier-shift.spec.js › F8E § 24 — Cashier Shift Lifecycle › A) Read current-shift + period-report | ✅ passed | 1.6s |
| 152 | stress › 24-cashier-shift.spec.js › F8E § 24 — Cashier Shift Lifecycle › B) open-shift + N manual-transactions + close-shift | ✅ passed | 24.5s |
| 153 | stress › 24-cashier-shift.spec.js › F8E § 24 — Cashier Shift Lifecycle › C) Read shift-history (seeded + spec-created shifts) | ✅ passed | 0.7s |
| 154 | stress › 24-cashier-shift.spec.js › F8E § 24 — Cashier Shift Lifecycle › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 155 | stress › 25-finance-cityledger.spec.js › F8E § 25 — Finance City Ledger › Setup: prefix + pilot baseline + module probe | ✅ passed | 1.3s |
| 156 | stress › 25-finance-cityledger.spec.js › F8E § 25 — Finance City Ledger › A) List city-ledger accounts | ✅ passed | 0.8s |
| 157 | stress › 25-finance-cityledger.spec.js › F8E § 25 — Finance City Ledger › B) Bulk create city-ledger accounts | ✅ passed | 11.6s |
| 158 | stress › 25-finance-cityledger.spec.js › F8E § 25 — Finance City Ledger › C) Read city-ledger account transactions (seeded account) | ✅ passed | 3.0s |
| 159 | stress › 25-finance-cityledger.spec.js › F8E § 25 — Finance City Ledger › D) Pilot drift = 0 | ✅ passed | 0.5s |
| 160 | stress › 26-accounting-expenses.spec.js › F8E § 26 — Accounting Expenses › Setup: prefix + pilot baseline + module probe | ✅ passed | 3.0s |
| 161 | stress › 26-accounting-expenses.spec.js › F8E § 26 — Accounting Expenses › A) List suppliers + expenses | ✅ passed | 4.3s |
| 162 | stress › 26-accounting-expenses.spec.js › F8E § 26 — Accounting Expenses › B) Bulk create suppliers + expenses + invoices | ✅ passed | 55.1s |
| 163 | stress › 26-accounting-expenses.spec.js › F8E § 26 — Accounting Expenses › C) Read expenses filtered by category (aggregation) | ✅ passed | 4.3s |
| 164 | stress › 26-accounting-expenses.spec.js › F8E § 26 — Accounting Expenses › D) Pilot drift = 0 | ✅ passed | 0.5s |
| 165 | stress › 27-accounting-bank-inventory.spec.js › F8E § 27 — Accounting Bank + Inventory › Setup: prefix + pilot baseline + module probe | ✅ passed | 3.4s |
| 166 | stress › 27-accounting-bank-inventory.spec.js › F8E § 27 — Accounting Bank + Inventory › A) List bank-accounts + inventory-items | ✅ passed | 1.9s |
| 167 | stress › 27-accounting-bank-inventory.spec.js › F8E § 27 — Accounting Bank + Inventory › B) Bulk create bank-accounts + inventory movements | ✅ passed | 32.1s |
| 168 | stress › 27-accounting-bank-inventory.spec.js › F8E § 27 — Accounting Bank + Inventory › C) Inventory low-stock + total_value aggregation | ✅ passed | 0.9s |
| 169 | stress › 27-accounting-bank-inventory.spec.js › F8E § 27 — Accounting Bank + Inventory › D) Pilot drift = 0 | ✅ passed | 0.4s |
| 170 | stress › 28-finance-reports-currency.spec.js › F8E § 28 — Finance Reports + Currency › Setup: prefix + pilot baseline + currencies probe | ✅ passed | 0.8s |
| 171 | stress › 28-finance-reports-currency.spec.js › F8E § 28 — Finance Reports + Currency › A) Reports read (VAT / P&L / balance-sheet / dashboard / cash-flow / currencies) | ✅ passed | 6.4s |
| 172 | stress › 28-finance-reports-currency.spec.js › F8E § 28 — Finance Reports + Currency › B) Currency rates lifecycle (create + list + convert) | ✅ passed | 11.4s |
| 173 | stress › 28-finance-reports-currency.spec.js › F8E § 28 — Finance Reports + Currency › C) Pilot drift = 0 | ✅ passed | 0.4s |
| 174 | stress › 29-hr-payroll-lifecycle.spec.js › F8D-v2 § 29 — HR Payroll Lifecycle › Setup: prefix + pilot baseline + dry-run probe | ✅ passed | 2.0s |
| 175 | stress › 29-hr-payroll-lifecycle.spec.js › F8D-v2 § 29 — HR Payroll Lifecycle › A) Draft save (idempotent) + runs list + run detail | ✅ passed | 6.8s |
| 176 | stress › 29-hr-payroll-lifecycle.spec.js › F8D-v2 § 29 — HR Payroll Lifecycle › B) RBAC + finalize-without-perm (no-op safety net) | ✅ passed | 0.3s |
| 177 | stress › 29-hr-payroll-lifecycle.spec.js › F8D-v2 § 29 — HR Payroll Lifecycle › C) Dry-run idempotency — preview tekrar çağrısı drift üretmez | ✅ passed | 3.2s |
| 178 | stress › 29-hr-payroll-lifecycle.spec.js › F8D-v2 § 29 — HR Payroll Lifecycle › D) Pilot drift + external_calls invariant | ✅ passed | 1.3s |
| 179 | stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › Setup: prefix + pilot baseline + super_admin team POST probe + per-role user create | ✅ passed | 0.8s |
| 180 | stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › A) Super-admin baseline — 10 sensitive endpoints 2xx (control) | ⏭️ skipped | 0.0s |
| 181 | stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › B) RBAC catalog — /api/rbac/roles + my-permissions per-role tutarlılık | ⏭️ skipped | 0.0s |
| 182 | stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › C) Negative matrix — düşük-priv tokens hassas endpoint'lere 403/404 almalı | ⏭️ skipped | 0.0s |
| 183 | stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › D) Existence-disclosure contract — bogus + real cross-tenant ID lookups 403/404 dönmeli (strict) | ⏭️ skipped | 0.0s |
| 184 | stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 185 | stress › 30-admin-rbac.spec.js › F8I § 30 — Admin / RBAC Matrix › Z) Cleanup — created RBAC users idempotent DELETE (audit_logs preserved) | ✅ passed | 0.0s |
| 186 | stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › Setup: prefix + pilot baseline + tenants probe + snapshots | ✅ passed | 0.8s |
| 187 | stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › A) Settings mutation — PATCH /admin/tenants/{stress_tid}/info with prefix-tagged description | ⏭️ skipped | 0.0s |
| 188 | stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › B) Audit trail — mutation entry exists with stress tenant_id binding (architect review #3) | ⏭️ skipped | 0.0s |
| 189 | stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › C) Cross-tenant settings drift — pilot tenant info baseline'a göre ZERO drift | ⏭️ skipped | 0.0s |
| 190 | stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › D) Rate-limit boundary — admin tenants GET 20x ardışık, 5xx olmamalı | ⏭️ skipped | 0.0s |
| 191 | stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › E) Restore: stress tenant description orijinaline geri al | ✅ passed | 0.0s |
| 192 | stress › 31-settings-audit.spec.js › F8I § 31 — Settings + Audit › F) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 193 | stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › Setup: prefix + pilot baseline + perf list probe + pool build | ✅ passed | 0.9s |
| 194 | stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › A) List perf reviews — baseline read | ⏭️ skipped | 0.0s |
| 195 | stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › B) Per-review goal check-in CREATE | ⏭️ skipped | 0.0s |
| 196 | stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › C) Check-in LIST + DELETE cleanup (idempotent residue=0) | ✅ passed | 0.0s |
| 197 | stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › D) Per-staff perf summary read — staff scope sanity | ✅ passed | 0.0s |
| 198 | stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › F) Full lifecycle: manager-feedback create + employee-ack analog + terminal-state second-feedback rejection probe | ⏭️ skipped | 0.0s |
| 199 | stress › 32-hr-performance-lifecycle.spec.js › F8D-v2 § 32 — HR Performance Review Lifecycle › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 200 | stress › 33-hr-payroll-dryrun.spec.js › F8D-v2 § 33 — HR Payroll Dry-run › Setup: prefix + pilot baseline + payroll export probe + FORBIDDEN source-scan guard | ✅ passed | 1.7s |
| 201 | stress › 33-hr-payroll-dryrun.spec.js › F8D-v2 § 33 — HR Payroll Dry-run › A) GET /hr/payroll/{month} — finalized records lookup (read-only) | ✅ passed | 1.6s |
| 202 | stress › 33-hr-payroll-dryrun.spec.js › F8D-v2 § 33 — HR Payroll Dry-run › B) GET /hr/payroll/export — JSON dry-run preview | ✅ passed | 1.3s |
| 203 | stress › 33-hr-payroll-dryrun.spec.js › F8D-v2 § 33 — HR Payroll Dry-run › C) GET /hr/payroll/export/csv — CSV stream preview | ✅ passed | 1.1s |
| 204 | stress › 33-hr-payroll-dryrun.spec.js › F8D-v2 § 33 — HR Payroll Dry-run › D) FORBIDDEN doctrine — runtime invariant (helper-constant referenced, literal NEVER in source) | ✅ passed | 0.0s |
| 205 | stress › 33-hr-payroll-dryrun.spec.js › F8D-v2 § 33 — HR Payroll Dry-run › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 206 | stress › 33B-hr-payroll-export-pii.spec.js › F8D-v3 § 33B — Payroll Export PII / Role Visibility › Setup: prefix + pilot baseline + export probe | ✅ passed | 1.7s |
| 207 | stress › 33B-hr-payroll-export-pii.spec.js › F8D-v3 § 33B — Payroll Export PII / Role Visibility › A) JSON export — content-type + numeric contract + PII guard | ✅ passed | 2.1s |
| 208 | stress › 33B-hr-payroll-export-pii.spec.js › F8D-v3 § 33B — Payroll Export PII / Role Visibility › B) CSV stream export — content-type + PII guard in raw text | ✅ passed | 2.0s |
| 209 | stress › 33B-hr-payroll-export-pii.spec.js › F8D-v3 § 33B — Payroll Export PII / Role Visibility › C) XLSX run export — content-type + cross-tenant IDOR guard | ✅ passed | 3.9s |
| 210 | stress › 33B-hr-payroll-export-pii.spec.js › F8D-v3 § 33B — Payroll Export PII / Role Visibility › D) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 211 | stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › Setup: prefix + pilot baseline + staff pool + leave-balance probe | ✅ passed | 1.3s |
| 212 | stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › A) GET leave-balance baseline — read shape sanity | ⏭️ skipped | 0.0s |
| 213 | stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › B) Approve fresh leave_request → balance decrement check | ⏭️ skipped | 0.0s |
| 214 | stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › C) Year-end carryover upsert — POST /hr/leave-balance set carry_over | ⏭️ skipped | 0.0s |
| 215 | stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › C2) Negative annual_entitlement reject — 422 validation guard | ⏭️ skipped | 0.0s |
| 216 | stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › D) Future-year accrual probe — READ-only default behavior (no upsert) | ✅ passed | 0.0s |
| 217 | stress › 34-hr-leave-accrual.spec.js › F8D-v2 § 34 — HR Leave Balance Accrual + Carryover › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 218 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › Setup: prefix + pilot baseline + staff pool + shifts probe | ✅ passed | 2.4s |
| 219 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › A) Create initial shift S1 — staffA tomorrow morning 09-13 | ⏭️ skipped | 0.0s |
| 220 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › B) Create overlapping shift S2 — expect 409 conflict OR document P1 gap | ⏭️ skipped | 0.0s |
| 221 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › B2) Overnight branch — crosses_midnight contract + next-day overlap (Task #255/#258) | ⏭️ skipped | 0.0s |
| 222 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › C) Coverage check — HK dept ≥ MIN_COVERAGE_HK scheduled staff | ⏭️ skipped | 0.0s |
| 223 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › D) Cleanup — DELETE all created shifts (idempotent residue=0) | ✅ passed | 0.0s |
| 224 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › F) Coverage rules CRUD + coverage-check probe (Task #263 v2) | ⏭️ skipped | 0.0s |
| 225 | stress › 35-hr-shift-conflict.spec.js › F8D-v2 § 35 — HR Shift Conflict + Coverage › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.4s |
| 226 | stress › 35B-hr-shift-coverage-planning.spec.js › F8D-v3 § 35B — Shift Coverage Planning › Setup: prefix + pilot baseline + coverage-rules probe | ✅ passed | 0.9s |
| 227 | stress › 35B-hr-shift-coverage-planning.spec.js › F8D-v3 § 35B — Shift Coverage Planning › A) Coverage rule CRUD — create N + list + dept filter + shape contract | ✅ passed | 7.1s |
| 228 | stress › 35B-hr-shift-coverage-planning.spec.js › F8D-v3 § 35B — Shift Coverage Planning › B) Idempotency window — same payload create twice (allowed, no unique constraint) | ✅ passed | 2.0s |
| 229 | stress › 35B-hr-shift-coverage-planning.spec.js › F8D-v3 § 35B — Shift Coverage Planning › Cleanup) Inline DELETE coverage-rules (residue=0 target) | ✅ passed | 2.7s |
| 230 | stress › 35B-hr-shift-coverage-planning.spec.js › F8D-v3 § 35B — Shift Coverage Planning › D) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 231 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › Setup: prefix + pilot baseline + staff pool + per-role test user create + login | ✅ passed | 3.5s |
| 232 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › A) HR-RBAC matrix — 4 roles × 6 sensitive endpoints (cross-dept deny) | ⏭️ skipped | 0.0s |
| 233 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › A2) HR WRITE deny matrix — 4 roles × 7 mutation endpoints (cross-dept escalation guard) | ⏭️ skipped | 0.0s |
| 234 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › B) Staff list PII guard — phone/national_id/TC/IBAN masked | ⏭️ skipped | 0.0s |
| 235 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › C) Salary-history token+PII guard — per stress staff sample | ⏭️ skipped | 0.0s |
| 236 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › D) Audit log scope sanity — read + token guard + cross-tenant leak | ⏭️ skipped | 0.0s |
| 237 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › E) Cleanup created users (idempotent DELETE; audit logs untouched) | ✅ passed | 0.0s |
| 238 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › G) v2 Foundation — source filter + /hr/system-users + dept soft-delete guard | ⏭️ skipped | 0.0s |
| 239 | stress › 36-hr-rbac-pii-audit.spec.js › F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit › F) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 240 | stress › 37-hr-lifecycle-v2.spec.js › F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim) › Setup: prefix + pilot baseline + staff pool + outstanding probe | ✅ passed | 1.9s |
| 241 | stress › 37-hr-lifecycle-v2.spec.js › F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim) › A) Zimmet lifecycle — assign N + return half + outstanding compliance read | ⏭️ skipped | 0.0s |
| 242 | stress › 37-hr-lifecycle-v2.spec.js › F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim) › B) Uyarı lifecycle — issue N + acknowledge + per-staff list by_type | ⏭️ skipped | 0.0s |
| 243 | stress › 37-hr-lifecycle-v2.spec.js › F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim) › C) Eğitim lifecycle — add N + per-staff list + expiring compliance read | ⏭️ skipped | 0.0s |
| 244 | stress › 37-hr-lifecycle-v2.spec.js › F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim) › Cleanup) Inline DELETE — equipment / warnings / trainings (residue=0 target) | ✅ passed | 0.0s |
| 245 | stress › 37-hr-lifecycle-v2.spec.js › F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim) › D) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 246 | stress › 38-hr-employee-profile-detail.spec.js › F8D-v3 § 38 — Employee Profile Detail › Setup: prefix + pilot baseline + staff pool + profile probe | ✅ passed | 1.4s |
| 247 | stress › 38-hr-employee-profile-detail.spec.js › F8D-v3 § 38 — Employee Profile Detail › A) Profile aggregate read — kişi + attendance + leaves + reviews + payroll + shifts | ⏭️ skipped | 0.0s |
| 248 | stress › 38-hr-employee-profile-detail.spec.js › F8D-v3 § 38 — Employee Profile Detail › B) Salary-history + certifications + documents — özlük yüzeyleri | ⏭️ skipped | 0.0s |
| 249 | stress › 38-hr-employee-profile-detail.spec.js › F8D-v3 § 38 — Employee Profile Detail › C) Cross-tenant profile probe — pilot staff_id ile stress token → 403/404 expected | ⏭️ skipped | 0.0s |
| 250 | stress › 38-hr-employee-profile-detail.spec.js › F8D-v3 § 38 — Employee Profile Detail › D) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 251 | stress › 38B-hr-staff-self-service.spec.js › F8D-v3 § 38B — Staff Self-Service Scope › Setup: prefix + pilot baseline + self-service probe | ✅ passed | 0.9s |
| 252 | stress › 38B-hr-staff-self-service.spec.js › F8D-v3 § 38B — Staff Self-Service Scope › A) /payroll/me — self-only contract (locked-only doctrine + no cross-staff) | ✅ passed | 3.9s |
| 253 | stress › 38B-hr-staff-self-service.spec.js › F8D-v3 § 38B — Staff Self-Service Scope › B) Cross-staff IDOR probe — pilot staff_id ile self-service surface | ✅ passed | 0.5s |
| 254 | stress › 38B-hr-staff-self-service.spec.js › F8D-v3 § 38B — Staff Self-Service Scope › C) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 255 | stress › 39-hr-department-position-masterdata.spec.js › F8D-v3 § 39 — Department / Position Master Data › Setup: prefix + pilot baseline + departments probe | ✅ passed | 1.1s |
| 256 | stress › 39-hr-department-position-masterdata.spec.js › F8D-v3 § 39 — Department / Position Master Data › A) Department CRUD — create N + list + active-staff guard + position FK | ✅ passed | 6.7s |
| 257 | stress › 39-hr-department-position-masterdata.spec.js › F8D-v3 § 39 — Department / Position Master Data › B) Position CRUD — create N pozisyon (dept FK valid) + list + dept filter | ✅ passed | 6.0s |
| 258 | stress › 39-hr-department-position-masterdata.spec.js › F8D-v3 § 39 — Department / Position Master Data › C) Sync-from-staff — idempotent master data backfill | ✅ passed | 3.5s |
| 259 | stress › 39-hr-department-position-masterdata.spec.js › F8D-v3 § 39 — Department / Position Master Data › Cleanup) Inline DELETE positions + departments (residue=0 target) | ✅ passed | 4.8s |
| 260 | stress › 39-hr-department-position-masterdata.spec.js › F8D-v3 § 39 — Department / Position Master Data › D) external_calls invariant + pilot_drift=0 | ✅ passed | 1.4s |
| 261 | stress › 39B-hr-offboarding.spec.js › F8D-v3 § 39B — Offboarding (Termination Read-Only + 409 Guard) › Setup: prefix + pilot baseline + termination GET probe | ✅ passed | 1.4s |
| 262 | stress › 39B-hr-offboarding.spec.js › F8D-v3 § 39B — Offboarding (Termination Read-Only + 409 Guard) › A) Cross-tenant termination probe — pilot staff_id ile stress token (must 403/404) | ⏭️ skipped | 0.0s |
| 263 | stress › 39B-hr-offboarding.spec.js › F8D-v3 § 39B — Offboarding (Termination Read-Only + 409 Guard) › B) Termination GET read-only — record shape + masked PII | ⏭️ skipped | 0.0s |
| 264 | stress › 39B-hr-offboarding.spec.js › F8D-v3 § 39B — Offboarding (Termination Read-Only + 409 Guard) › C) Outstanding equipment 409 guard — PRECONDITIONED (assign→probe→return) | ⏭️ skipped | 0.0s |
| 265 | stress › 39B-hr-offboarding.spec.js › F8D-v3 § 39B — Offboarding (Termination Read-Only + 409 Guard) › D) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 266 | stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › Setup: prefix + pilot baseline + GraphQL reachability probe + pilot sample IDs | ✅ passed | 2.1s |
| 267 | stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › A) Introspection policy + Mutation surface contract | ✅ passed | 0.4s |
| 268 | stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › B) Resolver isolation — stress_token ile bookings/rooms/dashboard kendi tenant'ı dönmeli, pilot ID'leri sızmamalı | ✅ passed | 3.2s |
| 269 | stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › C) Cross-tenant injection probes — variable spoof, pilot ID lookup, pagination cursor | ✅ passed | 2.6s |
| 270 | stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › C2) Folios + Reports surface contract — schema'da YOK; query attempt schema error dönmeli, data DÖNMEMELİ | ✅ passed | 2.1s |
| 271 | stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › D) Auth boundary — unauthenticated + invalid token + wrong-tenant | ✅ passed | 1.9s |
| 272 | stress › 40-graphql-tenant-isolation.spec.js › F8M § 40 — GraphQL Tenant Isolation › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 273 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › Setup: prefix + pilot baseline + agencies probe + create stress API key | ✅ passed | 1.1s |
| 274 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › A) Key lifecycle smoke — get info, regenerate, get info again (no leak in read responses) | ⏭️ skipped | 0.0s |
| 275 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › B) Scope assertions — valid key 200, missing key 401/403, garbage key 401/403, cross-tenant access denied | ⏭️ skipped | 0.0s |
| 276 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › B2) Extended B2B smoke — availability/rates/reservations/hotel-info/guests-search/folio under valid API key | ⏭️ skipped | 0.0s |
| 277 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › C) Revoked-key contract — DELETE key, then re-attempt smoke → 401/403 | ⏭️ skipped | 0.0s |
| 278 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › C2) Expired-key + wrong-tenant endpoint-level scope | ⏭️ skipped | 0.0s |
| 279 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › D) Existence-disclosure on api-keys GET — bogus agency_id + cross-tenant pilot agency_id | ⏭️ skipped | 0.0s |
| 280 | stress › 41-b2b-api-key-scope.spec.js › F8M § 41 — B2B API Key Scope › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 281 | stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › Setup: pilot baseline + stress agency + create key + pilot id sampling | ✅ passed | 1.0s |
| 282 | stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › A) Collection GET matrix — no pilot_tid leak in stress-key responses | ⏭️ skipped | 0.0s |
| 283 | stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › B) ID-bearing GET matrix — P0 cross-tenant IDOR (stress key + pilot resource id → 4xx) | ⏭️ skipped | 0.0s |
| 284 | stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › C) Auth matrix — missing/bogus X-API-Key → 401/403 (P0 if 2xx) | ⏭️ skipped | 0.0s |
| 285 | stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › D) Per-subrouter scope enforcement — P2 REVIEW (scope provisioning yok) | ⏭️ skipped | 0.0s |
| 286 | stress › 41B-b2b-subrouter-matrix.spec.js › F8M v2 § 41B — B2B Sub-Router Matrix › E) Invariants — pilot_drift=0 + external_calls delta=0 | ✅ passed | 1.3s |
| 287 | stress › 42-ai-upsell-dryrun.spec.js › F8O § 42 — AI Upsell Dry-run › Setup: prefix + pilot baseline + LLM diagnostics + env guards + insights probe | ✅ passed | 1.9s |
| 288 | stress › 42-ai-upsell-dryrun.spec.js › F8O § 42 — AI Upsell Dry-run › A) Insights read — response shape + PII guard (phone/email/identity_number) | ✅ passed | 1.4s |
| 289 | stress › 42-ai-upsell-dryrun.spec.js › F8O § 42 — AI Upsell Dry-run › B) Cross-tenant insights — pilot token kendi tenant scope dışına çıkmamalı | ✅ passed | 0.6s |
| 290 | stress › 42-ai-upsell-dryrun.spec.js › F8O § 42 — AI Upsell Dry-run › C) Forbidden endpoint source-scan — autopilot/ML/pricing kapalı kapı | ✅ passed | 0.0s |
| 291 | stress › 42-ai-upsell-dryrun.spec.js › F8O § 42 — AI Upsell Dry-run › D) Vendor-call guard — authoritative ledger delta + briefing.ai_powered=false | ✅ passed | 0.5s |
| 292 | stress › 42-ai-upsell-dryrun.spec.js › F8O § 42 — AI Upsell Dry-run › E) Pilot drift=0 + external_calls invariant | ✅ passed | 1.3s |
| 293 | stress › 43-ai-pricing-dryrun.spec.js › F8O § 43 — AI Dynamic Pricing Dry-run › Setup: prefix + pilot baseline + LLM diagnostics + env guards + recommend probe | ✅ passed | 1.5s |
| 294 | stress › 43-ai-pricing-dryrun.spec.js › F8O § 43 — AI Dynamic Pricing Dry-run › A) recommend-rates — 14-day window shape + invariants (no apply) | ✅ passed | 1.5s |
| 295 | stress › 43-ai-pricing-dryrun.spec.js › F8O § 43 — AI Dynamic Pricing Dry-run › B) autopilot/status — read-only mode bilgisi (mutation YOK) | ✅ passed | 0.4s |
| 296 | stress › 43-ai-pricing-dryrun.spec.js › F8O § 43 — AI Dynamic Pricing Dry-run › C) Cross-tenant pricing — pilot token kendi tenant scope dışına taşmamalı | ⏭️ skipped | 0.0s |
| 297 | stress › 43-ai-pricing-dryrun.spec.js › F8O § 43 — AI Dynamic Pricing Dry-run › D) Forbidden endpoint source-scan — autopilot/ML/pricing/rate kapalı kapı | ✅ passed | 0.0s |
| 298 | stress › 43-ai-pricing-dryrun.spec.js › F8O § 43 — AI Dynamic Pricing Dry-run › E) Vendor-call guard — authoritative ledger delta + briefing.ai_powered=false | ✅ passed | 0.5s |
| 299 | stress › 43-ai-pricing-dryrun.spec.js › F8O § 43 — AI Dynamic Pricing Dry-run › F) Pilot drift=0 + external_calls invariant | ✅ passed | 1.3s |
| 300 | stress › 44-ai-noshow-risk-dryrun.spec.js › F8O § 44 — AI No-Show Risk Dry-run › Setup: prefix + pilot baseline + LLM diagnostics + env guards + booking field snapshot + no-show probe | ✅ passed | 1.9s |
| 301 | stress › 44-ai-noshow-risk-dryrun.spec.js › F8O § 44 — AI No-Show Risk Dry-run › A) GET /api/predictions/no-shows — read + shape | ✅ passed | 1.4s |
| 302 | stress › 44-ai-noshow-risk-dryrun.spec.js › F8O § 44 — AI No-Show Risk Dry-run › B) POST /api/ai/predict-no-shows — risk scoring + PII guard | ✅ passed | 0.6s |
| 303 | stress › 44-ai-noshow-risk-dryrun.spec.js › F8O § 44 — AI No-Show Risk Dry-run › C) Cross-tenant — pilot token stress booking_id leak guard | ⏭️ skipped | 0.0s |
| 304 | stress › 44-ai-noshow-risk-dryrun.spec.js › F8O § 44 — AI No-Show Risk Dry-run › D) Forbidden endpoint source-scan — autopilot/ML/pricing kapalı kapı | ✅ passed | 0.0s |
| 305 | stress › 44-ai-noshow-risk-dryrun.spec.js › F8O § 44 — AI No-Show Risk Dry-run › E) Vendor-call guard — authoritative ledger delta + briefing.ai_powered=false | ✅ passed | 0.5s |
| 306 | stress › 44-ai-noshow-risk-dryrun.spec.js › F8O § 44 — AI No-Show Risk Dry-run › F) Pilot drift=0 + per-booking immutability + external_calls invariant | ✅ passed | 1.7s |
| 307 | stress › 45-notification-batch-dryrun.spec.js › F8Q § 45 — Push notification batch dry-run › Setup: prefix + DISABLE_EXPO_PUSH guard + messaging probe + pilot baseline | ✅ passed | 0.8s |
| 308 | stress › 45-notification-batch-dryrun.spec.js › F8Q § 45 — Push notification batch dry-run › A) Batch enqueue 100 + duplicate idempotency + invalid token graceful | ⏭️ skipped | 0.0s |
| 309 | stress › 45-notification-batch-dryrun.spec.js › F8Q § 45 — Push notification batch dry-run › B) Tenant-scoped delivery-logs + activity feed + PII/token mask | ⏭️ skipped | 0.0s |
| 310 | stress › 45-notification-batch-dryrun.spec.js › F8Q § 45 — Push notification batch dry-run › C) Activity feed read + token mask (notifications endpoint) | ⏭️ skipped | 0.0s |
| 311 | stress › 45-notification-batch-dryrun.spec.js › F8Q § 45 — Push notification batch dry-run › D) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.3s |
| 312 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › Setup: prefix + pilot baseline + GET /health + GET /info reachability + auth-mode classification | ✅ passed | 1.4s |
| 313 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › A) Auth contract — empty body, garbage payload, missing content-type → fail-closed (503/403/400) | ✅ passed | 1.3s |
| 314 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › B) Payload-size limit — oversized body (>256 KiB) → 400/413 | ✅ passed | 1.2s |
| 315 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › C) Tenant injection probe — forge pilot_tid içerikli payload pilot tenant'a sızdırmamalı | ✅ passed | 0.3s |
| 316 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › D) Replay & burst — aynı payload 5x ardışık POST, 5xx storm yok + status istikrarlı | ✅ passed | 1.6s |
| 317 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › F) EXELY readiness gate — env contract semantics (configured PASS / HR-only N/A / prod-like unset P2 informational / bypass P1) | ✅ passed | 0.0s |
| 318 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › G) Conditional valid payload + duplicate ingest idempotency (auth-mode=open_for_testing veya EXELY_IP_WHITELIST set) | ✅ passed | 0.0s |
| 319 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › H) Conditional cancellation idempotency — aynı reservation_id cancel 2x → tek state geçişi (auth-mode=open) | ✅ passed | 0.0s |
| 320 | stress › 50-cm-webhooks-exely.spec.js › F8L § 50 — Exely Webhook Stress › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 321 | stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › Setup: prefix + pilot baseline + logs reachability probe + sig-mode classification | ✅ passed | 1.4s |
| 322 | stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › A) Sig contract — missing headers / bad sig / stale ts → 401 (or 503 fail-closed) | ✅ passed | 1.9s |
| 323 | stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › B) Webhook surface coverage — reservations/modifications/cancellations endpoints same contract | ✅ passed | 1.0s |
| 324 | stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › C) Tenant injection probe — pilot_tid forge payload imzasız reject edilmeli | ✅ passed | 0.3s |
| 325 | stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › D) Logs read scope — /logs/events ve /logs/errors stress tenant'a scope'lu olmalı + PII mask | ✅ passed | 1.2s |
| 326 | stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › F) Signed valid-path — HOTELRUNNER_WEBHOOK_SECRET set ise gerçek HMAC payload kabul edilmeli (stress_tid scope, dispatcher dry-run) | ✅ passed | 0.0s |
| 327 | stress › 51-cm-hotelrunner-outbox.spec.js › F8L § 51 — HotelRunner Webhook + Outbox › E) external_calls invariant + pilot_drift=0 | ✅ passed | 1.3s |
| 328 | stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › Setup: prefix + pilot baseline + outbox status reachability + t1 snapshot | ✅ passed | 0.9s |
| 329 | stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › A) Outbox status delta — no-op window: pending/processing/retry/failed delta == 0 | ✅ passed | 1.9s |
| 330 | stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › B) Outbox events list — stress_tid scope'lu, pilot_tid leak yok + PII mask | ✅ passed | 1.1s |
| 331 | stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › C) Conflict Queue — stress tenant scope, count + list reachability, cross-tenant pilot booking leak yok | ✅ passed | 2.1s |
| 332 | stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › E) Active idempotency — duplicate signed webhook ingest → outbox event delta ≤ 1 (HOTELRUNNER_WEBHOOK_SECRET conditional) | ✅ passed | 0.0s |
| 333 | stress › 52-cm-outbox-idempotency.spec.js › F8L § 52 — Outbox Idempotency + Conflict Queue › D) external_calls invariant + pilot_drift=0 | ✅ passed | 1.4s |
| 334 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › Setup: prefix + pilot baseline + CB/CQ probe + room sample + pending probe | ✅ passed | 2.9s |
| 335 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › A) Circuit-breakers — shape + tenant-scope + token/PII guard | ✅ passed | 0.5s |
| 336 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › A2) Circuit-breakers — anonymous deny (401/403) | ✅ passed | 0.3s |
| 337 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › B) Bulk-resolve — partial isolation (room_not_found + not_pending parity) | ✅ passed | 0.6s |
| 338 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › C) Bulk-resolve — duplicate booking_id dedup (last room_id wins) | ✅ passed | 0.6s |
| 339 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › D) Bulk-resolve — max 50 limit (51 items → 422) | ✅ passed | 0.5s |
| 340 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › E) Bulk-resolve — anonymous deny + RBAC contract | ✅ passed | 0.3s |
| 341 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › F) Bulk-resolve — P0 cross-tenant IDOR (stress token + pilot booking_id) | ✅ passed | 1.3s |
| 342 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › G) Bulk-resolve — real partial-success (deterministic; seeded pending) | ❌ failed | 0.0s |
| 343 | stress › 52B-cm-stop-sale-bulk-resolve.spec.js › F8L v2 § 52B — Stop-sale CB + Bulk Resolve › Z) external_calls invariant + pilot_drift=0 | ⏭️ skipped | 0.0s |
| 344 | stress › 60-public-online-checkin.spec.js › F8K § 60 — Public Online Check-in Stress › Setup: prefix + pilot baseline + stress booking probe + auth contract baseline | ✅ passed | 2.0s |
| 345 | stress › 60-public-online-checkin.spec.js › F8K § 60 — Public Online Check-in Stress › A) Auth contract — anonymous + garbage + tampered JWT → 401/403 on state GET | ✅ passed | 1.6s |
| 346 | stress › 60-public-online-checkin.spec.js › F8K § 60 — Public Online Check-in Stress › B) Form submit contract — invalid payload + no-auth + cross-tenant booking_id | ✅ passed | 1.8s |
| 347 | stress › 60-public-online-checkin.spec.js › F8K § 60 — Public Online Check-in Stress › C) ID-photo upload guard — anon/oversized/invalid mime → reject + metadata-only positive dry-run | ✅ passed | 3.5s |
| 348 | stress › 60-public-online-checkin.spec.js › F8K § 60 — Public Online Check-in Stress › D) Public token guard — Quick-ID precheckin public surface | ✅ passed | 1.0s |
| 349 | stress › 60-public-online-checkin.spec.js › F8K § 60 — Public Online Check-in Stress › E) Pilot drift + external_calls invariant | ✅ passed | 1.3s |
| 350 | stress › 61-public-nps-reviews.spec.js › F8K § 61 — Public NPS + Review Invite Stress › Setup: prefix + pilot baseline + NPS score reachability probe | ✅ passed | 0.9s |
| 351 | stress › 61-public-nps-reviews.spec.js › F8K § 61 — Public NPS + Review Invite Stress › A) NPS submit + duplicate guard + score aggregation read | ✅ passed | 2.8s |
| 352 | stress › 61-public-nps-reviews.spec.js › F8K § 61 — Public NPS + Review Invite Stress › B) NPS recent + by-room PII guard + cross-tenant scope | ✅ passed | 1.1s |
| 353 | stress › 61-public-nps-reviews.spec.js › F8K § 61 — Public NPS + Review Invite Stress › C) Public review invite token guard — anonymous GET + invalid format + non-existent + rate-limit boundary | ✅ passed | 10.7s |
| 354 | stress › 61-public-nps-reviews.spec.js › F8K § 61 — Public NPS + Review Invite Stress › D) Pilot drift + external_calls invariant | ✅ passed | 1.4s |
| 355 | stress › 62-public-kvkk-consent.spec.js › F8K § 62 — KVKK Consent + Digital Key + PII Guard Stress › Setup: prefix + pilot baseline + stress booking/guest probe + digital-key route probe | ✅ passed | 2.5s |
| 356 | stress › 62-public-kvkk-consent.spec.js › F8K § 62 — KVKK Consent + Digital Key + PII Guard Stress › A) KVKK consent contract — empty/garbage/cross-tenant booking_id rejection (probe-only) | ✅ passed | 1.5s |
| 357 | stress › 62-public-kvkk-consent.spec.js › F8K § 62 — KVKK Consent + Digital Key + PII Guard Stress › B) Digital key dry-run — anonymous + cross-tenant + non-checked-in booking guard | ⏭️ skipped | 0.0s |
| 358 | stress › 62-public-kvkk-consent.spec.js › F8K § 62 — KVKK Consent + Digital Key + PII Guard Stress › C) Guest profile PII guard + cross-tenant scope (profile-enhanced / profile-complete) | ✅ passed | 2.1s |
| 359 | stress › 62-public-kvkk-consent.spec.js › F8K § 62 — KVKK Consent + Digital Key + PII Guard Stress › D) KVKK lifecycle — consents/audit read + request create/update/delete + PII guard | ✅ passed | 4.0s |
| 360 | stress › 62-public-kvkk-consent.spec.js › F8K § 62 — KVKK Consent + Digital Key + PII Guard Stress › E) Pilot drift + external_calls invariant | ✅ passed | 1.3s |
| 361 | stress › 63-public-token-rotation.spec.js › F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep › Setup: prefix + pilot baseline + stress room harvest + module probe | ✅ passed | 0.7s |
| 362 | stress › 63-public-token-rotation.spec.js › F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep › A) Tampered/malformed/missing token → 403 contract | ⏭️ skipped | 0.0s |
| 363 | stress › 63-public-token-rotation.spec.js › F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep › B) Cross-tenant token forge — wrong tenant + valid token shape | ⏭️ skipped | 0.0s |
| 364 | stress › 63-public-token-rotation.spec.js › F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep › C) Bulk QR fetch (staff) PII mask + secret in response guard | ⏭️ skipped | 0.0s |
| 365 | stress › 63-public-token-rotation.spec.js › F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep › D) Rotation surface contract REVIEW + final invariants | ✅ passed | 1.2s |
| 366 | stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › Setup: pilot baseline + staff/room probes | ✅ passed | 2.4s |
| 367 | stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › A) HR docs — oversized / bad MIME / polyglot / path traversal reject | ✅ passed | 7.0s |
| 368 | stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › B) HR docs — valid upload + self download smoke + cross-tenant download reject | ✅ passed | 3.5s |
| 369 | stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › C) Housekeeping photo — polyglot/oversized/MIME/path-traversal reject (magic-bytes enforced) | ⏭️ skipped | 0.0s |
| 370 | stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › D) Unauthenticated upload — both surfaces must reject without bearer | ✅ passed | 1.2s |
| 371 | stress › 64-file-upload-security.spec.js › F8S § 64 — File Upload Security › E) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.4s |
| 372 | stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS read-only surface + setup-info probe | ✅ passed | 4.2s |
| 373 | stress › 65-identity-reporting-kbs-jandarma-dryrun.spec.js › F8Y identity reporting dryrun › KBS_TEST_MODE prefix guard + queue schema enforcement | ✅ passed | 4.5s |
| 374 | stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › GDPR + retention surface read-only probe | ✅ passed | 3.6s |
| 375 | stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › ID-photo single + bulk delete cross-tenant guard | ✅ passed | 3.2s |
| 376 | stress › 66-kvkk-retention-deletion-anonymization.spec.js › F8AA KVKK retention/deletion/anonymization › GDPR data-requests cross-tenant filter probe | ✅ passed | 2.2s |
| 377 | stress › 70-inventory-stock.spec.js › F8F § 70 — Inventory / Stock Stress › Setup: prefix + pilot baseline + module probe | ✅ passed | 1.4s |
| 378 | stress › 70-inventory-stock.spec.js › F8F § 70 — Inventory / Stock Stress › A) Stock item bulk create — stress prefix marker | ✅ passed | 11.0s |
| 379 | stress › 70-inventory-stock.spec.js › F8F § 70 — Inventory / Stock Stress › B) Stock movements — in/out cycles + low-stock contract | ✅ passed | 18.6s |
| 380 | stress › 70-inventory-stock.spec.js › F8F § 70 — Inventory / Stock Stress › C) Negative stock guard — out movement exceeding current stock must reject | ✅ passed | 2.9s |
| 381 | stress › 70-inventory-stock.spec.js › F8F § 70 — Inventory / Stock Stress › D) Low-stock aggregation contract + cross-tenant isolation | ✅ passed | 0.9s |
| 382 | stress › 70-inventory-stock.spec.js › F8F § 70 — Inventory / Stock Stress › E) Pilot drift = 0 + external_calls = [] | ✅ passed | 1.5s |
| 383 | stress › 71-purchasing-supplier.spec.js › F8F § 71 — Purchasing / Supplier Stress › Setup: prefix + pilot baseline + supplier list probe | ✅ passed | 1.9s |
| 384 | stress › 71-purchasing-supplier.spec.js › F8F § 71 — Purchasing / Supplier Stress › A) Supplier CRUD + cross-tenant isolation | ✅ passed | 8.6s |
| 385 | stress › 71-purchasing-supplier.spec.js › F8F § 71 — Purchasing / Supplier Stress › B) PR → PO lifecycle dry-run (draft → approved → PO sent) | ✅ passed | 5.6s |
| 386 | stress › 71-purchasing-supplier.spec.js › F8F § 71 — Purchasing / Supplier Stress › C) GRN + invoice matching dry-run + supplier-delete-when-used guard | ✅ passed | 3.0s |
| 387 | stress › 71-purchasing-supplier.spec.js › F8F § 71 — Purchasing / Supplier Stress › D) Pilot drift = 0 + external_calls = [] | ✅ passed | 1.3s |
| 388 | stress › 72-warehouse-transfer-procurement.spec.js › F8F v2 § 72 — Warehouse Transfer + Procurement Hardening › Setup: probe procurement + prefix + pilot baseline | ✅ passed | 2.2s |
| 389 | stress › 72-warehouse-transfer-procurement.spec.js › F8F v2 § 72 — Warehouse Transfer + Procurement Hardening › A) Warehouse transfer endpoint — happy path + insufficient-source-stock 409 | ❌ failed | 4.5s |
| 390 | stress › 72-warehouse-transfer-procurement.spec.js › F8F v2 § 72 — Warehouse Transfer + Procurement Hardening › B) Partial GRN lifecycle: sent → partially_received → received + rejected-no-stock + duplicate grn_no | ⏭️ skipped | 0.0s |
| 391 | stress › 72-warehouse-transfer-procurement.spec.js › F8F v2 § 72 — Warehouse Transfer + Procurement Hardening › C) PO cancellation guard: cancel+GRN blocked, empty reason 422, closed→cancelled 409 | ⏭️ skipped | 0.0s |
| 392 | stress › 72-warehouse-transfer-procurement.spec.js › F8F v2 § 72 — Warehouse Transfer + Procurement Hardening › D) Supplier credit_limit probe + delete-when-used guard + cross-tenant IDOR | ⏭️ skipped | 0.0s |
| 393 | stress › 72-warehouse-transfer-procurement.spec.js › F8F v2 § 72 — Warehouse Transfer + Procurement Hardening › E) Final invariants + cleanup idempotency | ⏭️ skipped | 0.0s |
| 394 | stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › Setup: prefix + pilot baseline + module access probe | ✅ passed | 1.1s |
| 395 | stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › A) Account CRUD + duplicate-tax-no guard probe | ✅ passed | 13.4s |
| 396 | stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › B) Contact CRUD per account | ✅ passed | 23.0s |
| 397 | stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › C) Lead→Opportunity→won/lost terminal + activity log (F8C backlog kapanır) | ✅ passed | 37.6s |
| 398 | stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › D) Corporate contract dry-run lifecycle (create + update) | ✅ passed | 29.2s |
| 399 | stress › 80-crm-offers-contracts.spec.js › F8G § 80 — CRM Accounts + Contacts + Offers + Contracts › E) Tenant isolation + pilot_drift + external_calls invariant | ✅ passed | 2.0s |
| 400 | stress › 90-reports-analytics-export.spec.js › F8H § 90 — Reports / Analytics / Export Stress › Setup: prefix + pilot baseline + dashboard probe | ✅ passed | 1.7s |
| 401 | stress › 90-reports-analytics-export.spec.js › F8H § 90 — Reports / Analytics / Export Stress › A) Dashboard KPI reads (pms / accounting / revenue-engine) | ✅ passed | 8.4s |
| 402 | stress › 90-reports-analytics-export.spec.js › F8H § 90 — Reports / Analytics / Export Stress › B) Operational reports read (occupancy / revenue / aging / HR / finance / inventory) | ✅ passed | 20.4s |
| 403 | stress › 90-reports-analytics-export.spec.js › F8H § 90 — Reports / Analytics / Export Stress › C) CSV / XLSX export dry-run (analytics-export + report-builder + departments) | ✅ passed | 12.9s |
| 404 | stress › 90-reports-analytics-export.spec.js › F8H § 90 — Reports / Analytics / Export Stress › D) PDF export dry-run + PII/token mask guard on export payloads | ✅ passed | 13.2s |
| 405 | stress › 90-reports-analytics-export.spec.js › F8H § 90 — Reports / Analytics / Export Stress › E) Large pagination smoke + cache invalidation via stress mutation→read | ✅ passed | 11.8s |
| 406 | stress › 90-reports-analytics-export.spec.js › F8H § 90 — Reports / Analytics / Export Stress › F) Pilot drift = 0 (final gate, runs independently of moduleBlocked) | ✅ passed | 0.4s |
| 407 | stress › 91-export-artifact-idor.spec.js › F8R § 91 — Export Artifact IDOR › Setup: pilot baseline + pilot ID harvest per surface | ✅ passed | 0.9s |
| 408 | stress › 91-export-artifact-idor.spec.js › F8R § 91 — Export Artifact IDOR › A) Cross-tenant IDOR — stress_token MUST NOT download pilot-owned export artifacts | ⏭️ skipped | 0.0s |
| 409 | stress › 91-export-artifact-idor.spec.js › F8R § 91 — Export Artifact IDOR › B) Self-tenant download smoke — stress_token gets stress artifact OK + content-type sane | ✅ passed | 6.7s |
| 410 | stress › 91-export-artifact-idor.spec.js › F8R § 91 — Export Artifact IDOR › C) Unauthenticated download — no token → all export endpoints must reject | ✅ passed | 3.8s |
| 411 | stress › 91-export-artifact-idor.spec.js › F8R § 91 — Export Artifact IDOR › D) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.3s |
| 412 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › Setup: stress bookings/rooms/guests snapshot + pilot baseline | ✅ passed | 41.9s |
| 413 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › A) Waitlist promote (endpoint probe + REVIEW if absent) | ⏭️ skipped | 0.0s |
| 414 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › B) Booking hold create + status read (TTL contract) | ⏭️ skipped | 0.0s |
| 415 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › C) Overbooking oversell guard (duplicate booking reject) | ⏭️ skipped | 0.0s |
| 416 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › D) Overbooking yield guard (room-type sample probe) | ⏭️ skipped | 0.0s |
| 417 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › E) Multi-room partial cancel (3 rooms → cancel 1, keep 2) | ⏭️ skipped | 0.0s |
| 418 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › F) Group rooming list batch upload | ⏭️ skipped | 0.0s |
| 419 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › G) Rate change after modification | ⏭️ skipped | 0.0s |
| 420 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › H) Split reservation (5-night → 2 + 3) | ⏭️ skipped | 0.0s |
| 421 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › I) Merge duplicate guest profiles | ⏭️ skipped | 0.0s |
| 422 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › J) No-show fee dry-run (folio charge gözlem) | ⏭️ skipped | 0.0s |
| 423 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › K) Cancellation policy fee tier observation | ⏭️ skipped | 0.0s |
| 424 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › L) City ledger transfer dry-run | ⏭️ skipped | 0.0s |
| 425 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › M) External calls invariant after deep lifecycle batch | ✅ passed | 0.9s |
| 426 | stress › 95-reservation-lifecycle-deep.spec.js › F8N § 95 — Reservation Lifecycle Deep Stress › N) Pilot drift = 0 (tenant isolation final gate) | ✅ passed | 0.8s |
| 427 | stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › Setup: prefix + pilot baseline + surface probes + pilot sample ID harvest | ✅ passed | 4.6s |
| 428 | stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › A) LIST scan — stress_token must not return pilot-tagged items | ✅ passed | 2.2s |
| 429 | stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › B) IDOR probe — pilot-owned IDs must NOT be readable via stress_token | ✅ passed | 1.4s |
| 430 | stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › C) PII mask guard — list responses must mask sensitive fields | ⏭️ skipped | 0.4s |
| 431 | stress › 96-cross-tenant-pentest.spec.js › F8P § 96 — Cross-tenant pen-test (guests/folios/charges/messages/staff) › D) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.3s |
| 432 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › setup: stress token + tenant id present | ✅ passed | 0.0s |
| 433 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: marketplace_router (/api/marketplace/incoming-requests) | ✅ passed | 1.6s |
| 434 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pos_fnb_menu (/api/pos/fnb/menu) | ✅ passed | 0.8s |
| 435 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pos_fnb_modifiers (/api/pos/fnb/modifiers) | ✅ passed | 0.8s |
| 436 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: mobile_router_tasks (/api/mobile/tasks) | ✅ passed | 0.7s |
| 437 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: mobile_router_shift (/api/mobile/shift/current) | ✅ passed | 0.7s |
| 438 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: dashboard_widgets (/api/pms/dashboard/widgets) | ✅ passed | 0.7s |
| 439 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_groups (/api/pms/groups) | ✅ passed | 0.7s |
| 440 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_catering (/api/pms/catering) | ✅ passed | 0.7s |
| 441 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_approvals (/api/pms/approvals) | ✅ passed | 0.7s |
| 442 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_wakeup (/api/pms/wakeup-calls) | ✅ passed | 0.7s |
| 443 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_lost_found (/api/pms/lost-found) | ✅ passed | 0.8s |
| 444 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_maintenance_workorders (/api/maintenance/work-orders) | ✅ passed | 0.8s |
| 445 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_maintenance_assets (/api/maintenance/assets) | ✅ passed | 0.8s |
| 446 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: pms_maintenance_plans (/api/maintenance/plans) | ✅ passed | 0.8s |
| 447 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hotelrunner_status (/api/channel-manager/hotelrunner/status) | ✅ passed | 0.8s |
| 448 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: exely_status (/api/channel-manager/exely/status) | ✅ passed | 0.8s |
| 449 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_validation (/api/channel-manager/validation/health) | ✅ passed | 0.8s |
| 450 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_lockdown (/api/channel-manager/lockdown/status) | ✅ passed | 0.8s |
| 451 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_ingest_status (/api/channel-manager/ingest/status) | ✅ passed | 1.2s |
| 452 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_incident_list (/api/channel-manager/incidents) | ✅ passed | 1.0s |
| 453 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: cm_reconciliation (/api/channel-manager/reconciliation/summary) | ✅ passed | 0.8s |
| 454 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_upsell (/api/ai/upsell/recommendations) | ✅ passed | 0.8s |
| 455 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_forecasting (/api/ai/forecasting/horizon) | ✅ passed | 0.8s |
| 456 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_guest_pattern (/api/ai/guest-patterns/summary) | ✅ passed | 0.8s |
| 457 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: ai_dynamic_offers (/api/ai/offers/active) | ✅ passed | 0.8s |
| 458 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: finance_mobile_cashier (/api/finance/mobile/cashier/status) | ✅ passed | 0.7s |
| 459 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: finance_mobile_payments (/api/finance/mobile/payments/recent) | ✅ passed | 0.7s |
| 460 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: guest_journey_list (/api/guest/journey/list) | ✅ passed | 0.7s |
| 461 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: guest_loyalty_status (/api/guest/loyalty/status) | ✅ passed | 0.7s |
| 462 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: guest_preferences (/api/guest/preferences) | ✅ passed | 0.7s |
| 463 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: messaging_templates (/api/messaging/templates) | ✅ passed | 0.7s |
| 464 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: messaging_settings (/api/messaging/settings) | ✅ passed | 0.7s |
| 465 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_leave_balance (/api/hr/leave/balance) | ✅ passed | 0.7s |
| 466 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_performance_reviews (/api/hr/performance/reviews) | ✅ passed | 0.9s |
| 467 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_recruitment_postings (/api/hr/recruitment/postings) | ✅ passed | 0.7s |
| 468 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_training_catalog (/api/hr/training/catalog) | ✅ passed | 0.7s |
| 469 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: hr_benefits_summary (/api/hr/benefits/summary) | ✅ passed | 0.7s |
| 470 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: admin_governance (/api/admin/governance/audit) | ✅ passed | 0.7s |
| 471 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: admin_feature_flags (/api/admin/feature-flags) | ✅ passed | 0.7s |
| 472 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: observability_metrics (/api/observability/metrics) | ✅ passed | 0.7s |
| 473 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: observability_traces (/api/observability/traces/recent) | ✅ passed | 0.7s |
| 474 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: system_health_components (/api/system-health/components) | ✅ passed | 0.7s |
| 475 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_laundry_status (/api/services/laundry/status) | ✅ passed | 0.7s |
| 476 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_transport_status (/api/services/transport/status) | ✅ passed | 0.7s |
| 477 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_concierge_requests (/api/services/concierge/requests) | ✅ passed | 0.7s |
| 478 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_activities (/api/services/activities) | ✅ passed | 0.7s |
| 479 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: svc_kids_club (/api/services/kids-club) | ✅ passed | 0.7s |
| 480 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: integrations_whatsapp (/api/integrations/whatsapp/status) | ✅ passed | 0.7s |
| 481 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: reports_list (/api/reports/list) | ✅ passed | 0.7s |
| 482 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: report_builder_templates (/api/reports/builder/templates) | ✅ passed | 0.9s |
| 483 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › probe: reports_scheduled (/api/reports/scheduled) | ✅ passed | 0.7s |
| 484 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › invariants: probe coverage summary | ❌ failed | 0.0s |
| 485 | stress › 97-backend-router-coverage-probe.spec.js › F9B § Backend Router Coverage Probe › invariants: external_calls + pilot_drift safe (read-only probe) | ⏭️ skipped | 0.0s |
| 486 | stress › 97-rate-limit-boundary.spec.js › F8Q § 97 — Per-endpoint rate-limit boundary › Setup: prefix + pilot baseline + stress sample harvest | ✅ passed | 0.9s |
| 487 | stress › 97-rate-limit-boundary.spec.js › F8Q § 97 — Per-endpoint rate-limit boundary › A) Public surface burst — QR submit + login (anonymous) | ✅ passed | 1.7s |
| 488 | stress › 97-rate-limit-boundary.spec.js › F8Q § 97 — Per-endpoint rate-limit boundary › B) Authenticated surface burst — GraphQL + B2B + reports export | ✅ passed | 4.0s |
| 489 | stress › 97-rate-limit-boundary.spec.js › F8Q § 97 — Per-endpoint rate-limit boundary › C) Tenant/IP isolation — pilot probe MUST remain healthy after stress burst | ✅ passed | 2.9s |
| 490 | stress › 97-rate-limit-boundary.spec.js › F8Q § 97 — Per-endpoint rate-limit boundary › D) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.3s |
| 491 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › Setup: pilot baseline + fresh login (isolated session) + token shape | ✅ passed | 1.5s |
| 492 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › A) Valid access token — /auth/me 2xx + role/tenant present + no token leak in body | ✅ passed | 1.4s |
| 493 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › B) Refresh rotation — old refresh issues NEW access+refresh; rotation contract enforced | ✅ passed | 1.5s |
| 494 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › C) Old refresh after rotation must be REJECTED (single-use enforcement) | ✅ passed | 1.3s |
| 495 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › D) Logout invalidates access token AND refresh token (revocation) | ✅ passed | 2.4s |
| 496 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › E) Garbage / malformed / tampered access tokens — all rejected | ✅ passed | 2.4s |
| 497 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › F) Cross-scope guard — refresh token MUST NOT work as access bearer | ✅ passed | 3.1s |
| 498 | stress › 98-auth-token-lifecycle.spec.js › F8U § 98 — Auth Token Lifecycle › G) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.3s |
| 499 | stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › read-only invoice surface + schema enforcement | ✅ passed | 4.5s |
| 500 | stress › 98-efatura-earsiv-dryrun.spec.js › F8X efatura/earsiv dryrun › ERP integration sync — forbidden real provider HTTP | ✅ passed | 3.0s |
| 501 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.6s |
| 502 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › G) Catalog: GET /api/mice/spaces + /api/mice/menus | ✅ passed | 1.2s |
| 503 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › A) Create BEO event — stress-tenant scoped | ✅ passed | 2.8s |
| 504 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › B) List + filter by status=lead — tenant scoping invariant | ✅ passed | 2.1s |
| 505 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › C) GET event detail | ✅ passed | 0.6s |
| 506 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › D) Update: menu attach + space link + pricing calc | ✅ passed | 2.7s |
| 507 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › E) GET /api/mice/events/{id}/beo — generator output | ✅ passed | 0.7s |
| 508 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › E2) GET /api/mice/events/{id}/beo.pdf — PDF render | ✅ passed | 0.4s |
| 509 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › F) Status transition: lead → tentative | ✅ passed | 0.9s |
| 510 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › H) GET /api/mice/events/{id}/kitchen-ticket | ✅ passed | 0.7s |
| 511 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › J) IDOR: cross-tenant status POST → no mutation | ✅ passed | 0.6s |
| 512 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › K) Anonymous (headerless) GET /api/mice/events → 401/403 | ✅ passed | 0.3s |
| 513 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.8s |
| 514 | stress › 98-fnb-beo-generator.spec.js › F9C § 98 — F&B BEO Generator Lifecycle › N) Invariant: pilot drift — booking-count baseline + BEO prefix scan | ✅ passed | 0.9s |
| 515 | stress › 98-golf-operational.spec.js › F8AC golf operational stress › Setup: probe catalog surfaces + prefix | ✅ passed | 3.3s |
| 516 | stress › 98-golf-operational.spec.js › F8AC golf operational stress › A) Catalog smoke + tee-sheet + daily-summary | ✅ passed | 4.5s |
| 517 | stress › 98-golf-operational.spec.js › F8AC golf operational stress › B) Booking lifecycle: confirmed → checked_in → completed + no_show + cancelled + folio-guard | ✅ passed | 9.0s |
| 518 | stress › 98-golf-operational.spec.js › F8AC golf operational stress › C) Conflict guard: slot capacity + player double-book | ✅ passed | 5.2s |
| 519 | stress › 98-golf-operational.spec.js › F8AC golf operational stress › D) Folio-post endpoint contract (no reservation → 400, replay → 409) | ✅ passed | 3.6s |
| 520 | stress › 98-golf-operational.spec.js › F8AC golf operational stress › E) Cross-tenant IDOR + negative validation + idempotency replay | ✅ passed | 6.5s |
| 521 | stress › 98-golf-operational.spec.js › F8AC golf operational stress › Z) Cleanup (idempotent) + final invariants | ✅ passed | 10.0s |
| 522 | stress › 98-konaklama-vergisi-dryrun.spec.js › F8AD konaklama vergisi dryrun › read-only surface smoke + module probe + success-path detail/export | ✅ passed | 11.7s |
| 523 | stress › 98-konaklama-vergisi-dryrun.spec.js › F8AD konaklama vergisi dryrun › calculate + report validation + idempotency (no mutation) | ✅ passed | 8.2s |
| 524 | stress › 98-konaklama-vergisi-dryrun.spec.js › F8AD konaklama vergisi dryrun › write surface negative + bogus-id probes (4xx-strict) | ✅ passed | 9.4s |
| 525 | stress › 98-konaklama-vergisi-dryrun.spec.js › F8AD konaklama vergisi dryrun › P0 cross-tenant IDOR — stress_token vs pilot resources (hard-fail) | ✅ passed | 6.4s |
| 526 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.5s |
| 527 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › A) Create work order — stress-tenant scoped | ❌ failed | 0.7s |
| 528 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › B) List + filter by status=open | ⏭️ skipped | 0.0s |
| 529 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › C+D) Lifecycle: open → in_progress → completed | ⏭️ skipped | 0.0s |
| 530 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › E) GET /api/maintenance/tasks read-only | ⏭️ skipped | 0.0s |
| 531 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › F) POST+GET /api/maintenance/assets | ⏭️ skipped | 0.0s |
| 532 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › G) POST+GET /api/maintenance/plans | ⏭️ skipped | 0.0s |
| 533 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › H) GET /api/maintenance/repeat-issues read-only | ⏭️ skipped | 0.0s |
| 534 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › I) GET /api/maintenance/sla-metrics read-only | ⏭️ skipped | 0.0s |
| 535 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › J) IDOR: cross-tenant PATCH → no mutation | ⏭️ skipped | 0.0s |
| 536 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › K) Anonymous (headerless) GET → 401/403 | ⏭️ skipped | 0.0s |
| 537 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › M) Invariant: external_calls=[] for this module batch | ⏭️ skipped | 0.0s |
| 538 | stress › 98-maintenance-workorder-lifecycle.spec.js › F9C § 98 — Maintenance Work Order Lifecycle › N) Invariant: pilot drift — booking-count baseline + prefix scan | ⏭️ skipped | 0.0s |
| 539 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 2.4s |
| 540 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › A) Publish listing — stress-tenant opt-in | ✅ passed | 3.2s |
| 541 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › B) Read listing — verify tenant scope | ✅ passed | 1.1s |
| 542 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › C) Update listing — PUT changes apply | ✅ passed | 1.2s |
| 543 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › D) Unpublish listing — DELETE sets is_listed=false | ✅ passed | 1.7s |
| 544 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › E) Re-publish after unpublish — lifecycle idempotency | ✅ passed | 2.3s |
| 545 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › F) Inventory check — GET marketplace/inventory | ✅ passed | 0.9s |
| 546 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › G) Vendor profile — GET marketplace/suppliers | ✅ passed | 0.8s |
| 547 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › H) Order place — POST purchase-orders | ✅ passed | 2.2s |
| 548 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › I) Order cancel — POST purchase-orders/{id}/reject | ⏭️ skipped | 0.0s |
| 549 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › J) IDOR: cross-tenant probes → no mutation / no leak | ✅ passed | 1.0s |
| 550 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › K) Anonymous (headerless) GET listings/me → 401/403 | ✅ passed | 0.3s |
| 551 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.9s |
| 552 | stress › 98-marketplace-deep-lifecycle.spec.js › F9C § 98 — Marketplace Deep Lifecycle › N) Invariant: pilot drift — booking baseline + pilot marketplace prefix scan | ✅ passed | 1.6s |
| 553 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.0s |
| 554 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › B) Create template — stress-tenant scoped | ✅ passed | 2.0s |
| 555 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › C) List templates — tenant scope + created presence | ✅ passed | 2.0s |
| 556 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › D) Update template body | ✅ passed | 2.0s |
| 557 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › E) Template-injection payload stored-as-data (no exec/leak) | ✅ passed | 2.2s |
| 558 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › F) GET /providers — no credentials leak | ✅ passed | 0.7s |
| 559 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › G) POST /settings/test-connection — sandbox safe | ✅ passed | 0.5s |
| 560 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › H) GET /metrics read-only | ✅ passed | 0.5s |
| 561 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › I) GET /delivery-logs — RBAC + PII guard | ✅ passed | 0.5s |
| 562 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › J) IDOR cross-tenant PUT (pilot→stress template) → 4xx | ✅ passed | 0.6s |
| 563 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › J2) IDOR cross-tenant DELETE (pilot→stress template) → 4xx | ✅ passed | 0.5s |
| 564 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › K) Anonymous headerless GET /templates → 401/403 | ✅ passed | 0.3s |
| 565 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.9s |
| 566 | stress › 98-messaging-template-lifecycle.spec.js › F9C § 98 — Messaging Template Lifecycle › N) Invariant: pilot drift — booking baseline + pilot template prefix scan | ✅ passed | 0.9s |
| 567 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.5s |
| 568 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › A) GET /api/cashier/current-shift | ✅ passed | 1.0s |
| 569 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › B) POST /api/cashier/open-shift | ✅ passed | 2.1s |
| 570 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › C) POST /api/cashier/manual-transaction (charge) | ✅ passed | 2.2s |
| 571 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › D) POST /api/cashier/manual-transaction (refund) | ✅ passed | 2.2s |
| 572 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › E) GET /api/cashier/x-report | ✅ passed | 0.5s |
| 573 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › F) GET /api/cashier/shift/{id}/transactions | ✅ passed | 0.5s |
| 574 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › L) PIN brute-force throttle probe | ✅ passed | 6.1s |
| 575 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › G) POST /api/cashier/close-shift | ✅ passed | 2.1s |
| 576 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › H) GET /api/cashier/z-report/{shift_id} | ✅ passed | 0.5s |
| 577 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › I) GET /api/finance/mobile/daily-collections | ✅ passed | 0.6s |
| 578 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › J) IDOR: cross-tenant shift txn read → no leak | ✅ passed | 0.5s |
| 579 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › K) Anonymous (headerless) GET → 401/403 | ✅ passed | 0.3s |
| 580 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.8s |
| 581 | stress › 98-mobile-cashier-surface.spec.js › F9C § 98 — Mobile Cashier Surface › N) Invariant: pilot drift — booking baseline + cashier shift scan | ✅ passed | 1.5s |
| 582 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › Setup: stress token + module probe + pilot baseline | ✅ passed | 1.4s |
| 583 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › A) Register push device token — stress-tenant scoped | ⏭️ skipped | 0.0s |
| 584 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › B) GET /api/notifications/preferences read | ⏭️ skipped | 0.0s |
| 585 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › C) PUT /api/notifications/preferences update | ⏭️ skipped | 0.0s |
| 586 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › D) POST /api/pms/shift-handover create note | ⏭️ skipped | 0.0s |
| 587 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › E) GET /api/pms/shift-handover list + tenant scope | ⏭️ skipped | 0.0s |
| 588 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › F) GET /api/pms/shift-handover/open-count | ⏭️ skipped | 0.0s |
| 589 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › G) PATCH /api/pms/shift-handover/{id}/acknowledge | ⏭️ skipped | 0.0s |
| 590 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › H) GET /api/notifications/list read-only | ⏭️ skipped | 0.0s |
| 591 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › I) POST /api/notifications/push/unregister | ⏭️ skipped | 0.0s |
| 592 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › J) IDOR: cross-tenant PATCH ack → no mutation | ✅ passed | 0.5s |
| 593 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › K) Anonymous (headerless) GET handover list → 401/403 | ✅ passed | 0.3s |
| 594 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.8s |
| 595 | stress › 98-mobile-staff-surface.spec.js › F9C § 98 — Mobile Staff Surface › N) Invariant: pilot drift — booking baseline + push token prefix scan | ✅ passed | 2.1s |
| 596 | stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › Setup: prefix + tenant id snapshot + pilot baseline | ✅ passed | 1.7s |
| 597 | stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › A) cross_property_rollup — guest-search smoke + cross-tenant leak guard | ✅ passed | 4.1s |
| 598 | stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › B) shift_handover — create/list/open-count/ack/delete + cross-tenant IDOR | ✅ passed | 6.0s |
| 599 | stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › C) webhook_admin_dlq — global status smoke + non-super-admin 403 + cross-tenant filter | ⏭️ skipped | 2.1s |
| 600 | stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › D) eod_report — preview + pdf smoke (NO /send — external_calls invariant) | ✅ passed | 8.5s |
| 601 | stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › E) booking_holds — create/status/delete + cross-tenant IDOR + sweep role-guard | ✅ passed | 6.7s |
| 602 | stress › 98-ops-surface-smoke.spec.js › F8AH ops surface smoke stress › Z) Cleanup (idempotent) + final invariants | ✅ passed | 3.9s |
| 603 | stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › cashier + POS read-only surface | ✅ passed | 4.3s |
| 604 | stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › folio payment — schema enforcement + cross-tenant IDOR | ✅ passed | 3.4s |
| 605 | stress › 98-payment-pos-reconciliation-dryrun.spec.js › F8Z payment/pos reconciliation dryrun › manual-transaction X-Idempotency-Key replay | ✅ passed | 2.2s |
| 606 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › Setup: probe POS surface + outlet handle | ✅ passed | 2.9s |
| 607 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › A) Catalog smoke (orders + transactions list) | ✅ passed | 3.9s |
| 608 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › B) Lifecycle: create → close (post_to_folio=false, no folio, no Xchange) | ✅ passed | 4.1s |
| 609 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › C) Atomic conflict guard via idempotency-key replay (same key → same order id) | ✅ passed | 3.6s |
| 610 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › D) Split-check: equal + by_item + custom (sum ≤ original_amount invariant) | ✅ passed | 6.3s |
| 611 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › E) Table-transfer: happy-path attempt + bogus 404 + cross-tenant guard | ✅ passed | 3.3s |
| 612 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › F) Idempotency replay on close_order (same key → idempotent flag) | ✅ passed | 5.5s |
| 613 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › G) Terminal-state guard: void order, re-void already-voided, close-after-void | ✅ passed | 5.6s |
| 614 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › H) P0 Cross-tenant IDOR: pilot bearer must NOT touch stress order/txn | ✅ passed | 7.1s |
| 615 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › I) validate-room-charge: bogus booking + cross-tenant probe | ✅ passed | 2.9s |
| 616 | stress › 98-pos-deep-lifecycle.spec.js › F8Z v2 pos deep lifecycle › Z) Cleanup (idempotent void) + final invariants | ✅ passed | 11.7s |
| 617 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › Setup: probe KDS + inventory surfaces + pilot inventory baseline | ✅ passed | 5.0s |
| 618 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › A) KDS catalog smoke: kitchen-display tenant-scoped read | ✅ passed | 3.7s |
| 619 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › B) Kitchen-order lifecycle: create → preparing → ready → served + terminal-state guard | ✅ passed | 6.9s |
| 620 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › C) P0 cross-tenant KDS IDOR: pilot bearer must NOT mutate stress kitchen_order | ✅ passed | 6.5s |
| 621 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › D) Idempotency replay: kitchen-order create twice (no key support → distinct = P1) | ✅ passed | 4.1s |
| 622 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › E) Inventory deplete happy path (recipe → close → inventory_items decrement) | ⏭️ skipped | 0.0s |
| 623 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › F) Negative-stock guard: out movement > available → 409 (atomic guard) | ✅ passed | 5.1s |
| 624 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › G) Concurrent close race: 5 parallel out movements → atomic decrement | ✅ passed | 4.5s |
| 625 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › H) P0 cross-tenant inventory mutate: pilot bearer must NOT touch stress item | ✅ passed | 4.8s |
| 626 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › I) stock_consumption cross-tenant read: pilot bearer must NOT receive stress identifiers | ✅ passed | 3.4s |
| 627 | stress › 98-pos-kds-inventory.spec.js › F8Z.2 pos kds + fnb inventory › Z) Cleanup (idempotent cancel) + final invariants | ✅ passed | 6.6s |
| 628 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › Setup — pilot baseline + module probe + force advisory mode | ✅ passed | 4.8s |
| 629 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › A) Read-only probes (dashboard / queue / summary / market-overview / history / hurdle list / demand-forecast GET) | ✅ passed | 8.6s |
| 630 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › B) Policy update (advisory + thresholds) + demand-forecast POST (short range) | ✅ passed | 4.2s |
| 631 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › C) Autopilot pipeline — process / approve / reject | ✅ passed | 5.1s |
| 632 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › D) Displacement — analyze / compare / save | ✅ passed | 12.7s |
| 633 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › E) Hurdle rates — POST / PATCH / GET check (allowed + blocked) / DELETE | ✅ passed | 4.0s |
| 634 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › F) AI pricing auto-publish — dry_run gate + post-batch external_calls=0 | ✅ passed | 4.5s |
| 635 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › G) Cross-tenant IDOR — stress_token must NOT mutate pilot resources | ✅ passed | 5.8s |
| 636 | stress › 98-rms-revenue-deep.spec.js › F8AF revenue_management deep stress › Z) Cleanup (idempotent) + restore policy mode | ✅ passed | 4.9s |
| 637 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › Setup: stress token + module probe + pilot baseline | ✅ passed | 2.4s |
| 638 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › A) Create lead — stress-tenant scoped | ✅ passed | 2.1s |
| 639 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › B) List + filter by status=new | ✅ passed | 2.3s |
| 640 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › C+D) Lifecycle: new → qualified → won | ✅ passed | 2.4s |
| 641 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › E) Lead detail — GET /api/sales/leads/{id} (attachments=activities) | ✅ passed | 0.7s |
| 642 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › F) GET /api/sales/funnel | ✅ passed | 0.6s |
| 643 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › G) POST /api/sales/activity — activity (attachment-like) log | ✅ passed | 0.8s |
| 644 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › H) POST /api/mice/sales/opportunities — contract surrogate | ✅ passed | 1.8s |
| 645 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › I) Quote generate — POST /api/mice/sales/packages/{pkg_id}/quote | ✅ passed | 1.8s |
| 646 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › J) IDOR: cross-tenant PUT stage → no mutation | ✅ passed | 0.6s |
| 647 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › K) Anonymous (headerless) GET /api/sales/leads → 401/403 | ✅ passed | 0.3s |
| 648 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › M) Invariant: external_calls=[] for this module batch | ✅ passed | 0.8s |
| 649 | stress › 98-sales-basic-lifecycle.spec.js › F9C § 98 — Sales Basic Lifecycle › N) Invariant: pilot drift — booking-count baseline + sales prefix scan | ✅ passed | 1.0s |
| 650 | stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › Setup: probe catalog surfaces + prefix | ✅ passed | 3.6s |
| 651 | stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › A) Catalog smoke + availability + daily-summary | ⏭️ skipped | 0.0s |
| 652 | stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › B) Appointment lifecycle: scheduled → in_progress → completed + no_show + cancelled | ⏭️ skipped | 0.0s |
| 653 | stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › C) Conflict guard + auto-pick | ⏭️ skipped | 0.0s |
| 654 | stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › D) Waitlist CRUD + promote | ⏭️ skipped | 0.0s |
| 655 | stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › E) Cross-tenant IDOR + negative validation | ⏭️ skipped | 0.0s |
| 656 | stress › 98-spa-wellness-operational.spec.js › F8AB spa wellness operational stress › Z) Cleanup (idempotent) + final invariants | ✅ passed | 1.7s |
| 657 | stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › Setup: harvest stress booking + probe VCC/PCI surfaces | ✅ passed | 6.4s |
| 658 | stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › A) PCI compliance read smoke (status / controls / report.csv / attestation) | ✅ passed | 4.3s |
| 659 | stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › B) VCC lifecycle: store → status → reveal → audit invariant | ⏭️ skipped | 0.0s |
| 660 | stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › C) Reveal 3-view limit + 4th attempt = 403 | ⏭️ skipped | 0.0s |
| 661 | stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › D) Cross-tenant IDOR + negative validation | ⏭️ skipped | 0.0s |
| 662 | stress › 98-vcc-pci-compliance.spec.js › F8AE VCC + PCI compliance stress › Z) Cleanup (idempotent) + final invariants | ✅ passed | 1.7s |
| 663 | stress › 98B-websocket-tenant-isolation.spec.js › F8V § 98B — WebSocket Tenant Isolation › Setup: pilot baseline + ws lib probe + endpoint reachability | ⏭️ skipped | 1.1s |
| 664 | stress › 98B-websocket-tenant-isolation.spec.js › F8V § 98B — WebSocket Tenant Isolation › A) Unauthenticated / garbage / tampered tokens — WS auth fail (close code 4001 or short-lived) + no leaked frames | ⏭️ skipped | 0.0s |
| 665 | stress › 98B-websocket-tenant-isolation.spec.js › F8V § 98B — WebSocket Tenant Isolation › B) Valid stress token — connect OK + initial frame scoped to stress tenant + no pilot_tid leak | ⏭️ skipped | 0.0s |
| 666 | stress › 98B-websocket-tenant-isolation.spec.js › F8V § 98B — WebSocket Tenant Isolation › C) Cross-tenant subscribe spoof — stress socket "subscribe pilot tenant" must not yield pilot data | ⏭️ skipped | 0.0s |
| 667 | stress › 98B-websocket-tenant-isolation.spec.js › F8V § 98B — WebSocket Tenant Isolation › D) Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 1.3s |
| 668 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › Setup: pilot baseline + module probe + status snapshot | ✅ passed | 0.9s |
| 669 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › A) Setup → returns secret + otpauth URI + QR data URL (pending state) | ✅ passed | 2.4s |
| 670 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › B) Confirm with wrong code → 400; correct code → enabled + backup codes | ✅ passed | 5.2s |
| 671 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › C) Verify happy-path → exchange challenge_token for access_token + same-window replay guard | ✅ passed | 14.5s |
| 672 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › D) Brute-force boundary — invalid codes hit TWOFA_VERIFY_IP throttle (15/60s) → ≥1× 429 | ✅ passed | 16.7s |
| 673 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › E) Backup code single-use — consume one → second use rejected | ✅ passed | 2.9s |
| 674 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › F) Regenerate backup codes — requires valid TOTP; invalidates previous list | ✅ passed | 12.5s |
| 675 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › G) Policy GET + P0 cross-tenant IDOR — pilot bearer cannot read stress user's 2FA state | ✅ passed | 4.7s |
| 676 | stress › 98C-twofa-totp-lifecycle.spec.js › F8AG § 98C — 2FA TOTP Lifecycle › H) Disable (cleanup primary path) + Pilot drift = 0 + external_calls = [] (final invariants) | ✅ passed | 22.2s |
| 677 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › Setup: stress token + module probe + pilot baseline + harvest | ✅ passed | 2.0s |
| 678 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › A0) POST /api/folio/create (open lifecycle) | ❌ failed | 0.5s |
| 679 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › A) GET /api/folio/list | ⏭️ skipped | 0.0s |
| 680 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › B) GET /api/folio/{folio_id} | ⏭️ skipped | 0.0s |
| 681 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › C) POST /api/folio/{folio_id}/charge + Idempotency-Key replay | ⏭️ skipped | 0.0s |
| 682 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › D) POST /api/folio/{folio_id}/payment + Idempotency-Key replay | ⏭️ skipped | 0.0s |
| 683 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › E) POST /api/folio/{id}/void-charge/{cid} | ⏭️ skipped | 0.0s |
| 684 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › F) POST /api/folio/{id}/payment/{pid}/void | ⏭️ skipped | 0.0s |
| 685 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › G) POST /api/guest/purchase-upsell/{booking_id} (staff token rejected) | ⏭️ skipped | 0.0s |
| 686 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › H) GET /api/guest/purchased-upsells/{booking_id} (tenant scope) | ⏭️ skipped | 0.0s |
| 687 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › I) IDOR: cross-tenant folio detail + mutate → all rejected | ⏭️ skipped | 0.0s |
| 688 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › J) Anonymous GET /api/folio/list → 401/403 | ⏭️ skipped | 0.0s |
| 689 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › K) Bogus folio id mutations → 4xx | ⏭️ skipped | 0.0s |
| 690 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › L) Teardown: void leftover stress charges/payments | ⏭️ skipped | 0.0s |
| 691 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › M) Invariant: external_calls=[] for this module batch | ⏭️ skipped | 0.0s |
| 692 | stress › 99-finance-folio-surface.spec.js › F9D § 99 — Finance Folio & Guest-Purchase Surface › N) Invariant: pilot drift — booking baseline | ⏭️ skipped | 0.0s |
| 693 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Setup: reachability probe + pilot baseline + stress inventory | ✅ passed | 16.4s |
| 694 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Sabah-A) Arrivals listele + 20 walk-in (atomic check-in) | ⏭️ skipped | 0.0s |
| 695 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Sabah-B) external_calls invariant (sabah_walk_in_batch) | ⏭️ skipped | 0.0s |
| 696 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Sabah-C) QR request listing + complaints listing | ⏭️ skipped | 0.0s |
| 697 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Öğlen-A) Housekeeping transition (10 oda) | ⏭️ skipped | 0.0s |
| 698 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Öğlen-B) Inventory movement (read + 3 hareket) | ⏭️ skipped | 0.0s |
| 699 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Öğlen-C) Procurement: purchase request create | ⏭️ skipped | 0.0s |
| 700 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Öğlen-D) MICE events listing (event update opsiyonel) | ⏭️ skipped | 0.0s |
| 701 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Öğlen-E) external_calls invariant (oglen_ops_batch) | ⏭️ skipped | 0.0s |
| 702 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Akşam-A) Folio charge (walk-in booking'lerine ek charge) | ⏭️ skipped | 0.0s |
| 703 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Akşam-B) Folio payment (charge edilen booking'leri kapat) | ⏭️ skipped | 0.0s |
| 704 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Akşam-C) Room move (5 oda, vacant havuzdan) | ⏭️ skipped | 0.0s |
| 705 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Akşam-D) HR clock-in (5 personel smoke) | ⏭️ skipped | 0.0s |
| 706 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Akşam-E) external_calls invariant (aksam_ops_batch) | ⏭️ skipped | 0.0s |
| 707 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Gece-A) Checkout (force=true, walk-in batch) | ⏭️ skipped | 0.0s |
| 708 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Gece-B) Night audit run + re-run idempotency | ⏭️ skipped | 0.0s |
| 709 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Gece-C) Finance summary + reports read | ⏭️ skipped | 0.0s |
| 710 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Gece-D) external_calls invariant (gece_ops_batch) | ⏭️ skipped | 0.0s |
| 711 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Final-A) Pilot drift = 0 (24h sim sonu) | ✅ passed | 0.5s |
| 712 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Final-B) external_calls invariant (final_24h_batch) | ✅ passed | 0.9s |
| 713 | stress › 99-full-24h-hotel-simulation.spec.js › F8J § 99 — Full 24h hotel simulation › Final-C) Cleanup tracker + dashboard snapshot | ✅ passed | 0.0s |
| 714 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › Setup: probe POS extensions surface | ✅ passed | 2.4s |
| 715 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › A) Currency: upsert rate + foreign payment idempotency + cross-tenant guard | ✅ passed | 4.8s |
| 716 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › B) HappyHour: create rule + apply discounts + delete idempotent | ✅ passed | 3.0s |
| 717 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › C) Coupons: create + validate + atomic redeem (race guard) + duplicate code 409 | ✅ passed | 8.2s |
| 718 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › D) Loyalty: settings + earn idempotency + atomic redeem + insufficient guard | ✅ passed | 6.7s |
| 719 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › E) Shifts: open + duplicate 409 + close variance + idempotent re-close | ✅ passed | 5.3s |
| 720 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › F) Barcode: map + lookup + cross-tenant 404 + unmapped 404 | ✅ passed | 4.5s |
| 721 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › G) Print: enqueue + dispatch simulator + cancel idempotent | ✅ passed | 5.0s |
| 722 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › H) Fiscal: enqueue 404 for fake order + idempotency + EOD simulator | ✅ passed | 3.6s |
| 723 | stress › 99-pos-extensions.spec.js › F8AI POS Extensions › Z) Cleanup: delete all stress-created docs + idempotent second pass | ✅ passed | 9.2s |

## 9) Artifact path'leri

- HTML report: `frontend/playwright-stress-report/`
- Trace/video/screenshot: `frontend/test-results-stress/`
- State: `frontend/e2e-stress/.auth/stress-state.json` (gitignored)
- Teardown log: `frontend/e2e-stress/.auth/teardown.json` (gitignored)

## 10) Sonraki tur

❌ **NO-GO** — F8 (operasyonel stress senaryoları) öncesi P0/P1 düzeltilmeli.

## 11) Task #57 — Pacing fix end-to-end verification (addendum)

> Run trigger: Task #57 (Replit `Stress Suite Task57` workflow, not the GH Actions
> nightly — GITHUB_TOKEN was not authorized for this repo from the task sandbox,
> so the canonical `Full Stress Suite (one-shot)` workflow was reproduced 1:1 via
> `cd frontend && STRESS_REPORT_TAG=full_stress_suite_task57 yarn test:e2e:stress`
> with the same pre-flight env (E2E_BASE_URL=stress pilot, destructive_stress=true,
> external_dry_run=true). Suite ran one-shot, workers=1, 723 tests, 41.3 min.

### 11.1) Pacing fix scope (Task #34) — VERIFIED

Task #34 added a client-side pacer (write=100/min, default=250/min, anonymous=
50/min per bearer) plus automatic 429 retry in `frontend/e2e-stress/fixtures/
stress-helpers.js`. The acceptance signal from Task #34 was that the five
lifecycle specs that previously 429'd on their first POST in the 2026-05-24 run
(`20260524_stress_full_stress_suite_f8ah_NOT_GREEN.md`) all pass cleanly:

| Spec (target of pacer) | Result this run | Notes |
|---|---|---|
| `98C-twofa-totp-lifecycle.spec.js` — D (TWOFA throttle boundary, expects 429) | ✅ passed (16.7s) | Single intentional 429 from `noBackoff:true` burst — pacer correctly opted out. |
| `98-pos-deep-lifecycle.spec.js` — B/C/D/E/F/G/H/I/Z (F8Z v2 lifecycle) | ✅ all passed | No 429 leak; pacer kept writes under 100/min. |
| `98-golf-operational.spec.js` (F8AC) — A..E | ✅ all passed | |
| `39-hr-department-position-masterdata.spec.js` (F8D v3) — A) Bulk department CRUD | ✅ passed | Previously hit 429 on first POST burst; now clean. |
| `71-purchasing-supplier.spec.js` (F8F) — A) Bulk supplier create | ✅ passed | Previously hit 429 on first POST burst; now clean. |

`grep '429' /tmp/stress/run.log` returned only the expected intentional 429s
(TWOFA throttle boundary in 98C-D, the rate-limit-boundary burst spec that
deliberately uses `noPacer:true`). **Zero unexpected 429 failures on first POST
across all 723 tests.** Pacing wall-clock overhead vs. previous GREEN baseline
(Run #143 reporter 47m 1s, 84 spec / 556 test): this run's reporter 41m 17s on
89 spec / 723 test — pacing did not regress runtime; the longer spec count fits
inside the same hour-class envelope.

### 11.2) Overall verdict — NO-GO (unrelated regressions)

Suite verdict is **NO-GO** because 11 tests failed, but none of them are
attributable to rate limiting or the pacing helper. The failures cluster into
pre-existing environmental / module-availability issues:

| # | Spec | Symptom | Pacing-related? |
|---|---|---|---|
| 1 | `03-room-move` Setup | vacant pool snapshot timeout | ❌ no — read-side env state |
| 2 | `05-reservation-lifecycle` Setup | pilot-baseline timeout | ❌ no — read-side env state |
| 3 | `08-housekeeping-mass` E (mobile viewport) | render assertion | ❌ no — UI |
| 4 | `10-qr-requests` Setup | seeded fixture missing | ❌ no — env state |
| 5 | `12-complaints` Setup | seeded fixture missing | ❌ no — env state |
| 6 | `14-mice-events` A (catalog read) | module disabled on tenant | ❌ no — matches open task "Turn on the events & banquets module for the stress test tenant" |
| 7 | `52B-cm-stop-sale-bulk-resolve` G | seeded pending count drift | ❌ no — CM seed state |
| 8 | `72-warehouse-transfer-procurement` A | happy-path transfer 4xx | ❌ no — matches open task "Stop staff from transferring stock into the wrong unit" / multi-leg work in flight |
| 9 | `97-backend-router-coverage-probe` | meaningful_coverage 8 < 15 | ❌ no — coverage threshold drift |
| 10 | `98-maintenance-workorder-lifecycle` A | POST returns 500 | ❌ no — server bug |
| 11 | `99-finance-folio-surface` A0 | POST returns 400 (not in allow-list) | ❌ no — contract drift |

### 11.3) Outcome of Task #57

- Pacing fix verified end-to-end on the deployed stress pilot: **0 × unexpected
  429**, all five previously-429ing lifecycle specs PASS.
- The GREEN baseline pointer in `replit.md` Gotchas is **NOT** moved off Run #143
  (commit `3b3891d`, 84 spec / 556 test, 2026-05-26) because this run is overall
  NO-GO on 11 unrelated regressions. Promoting a new baseline requires the 11
  failures above to be closed first (those map to existing open tasks plus three
  net-new regressions worth filing separately).
- Drill report path (this file): `docs/drill_reports/20260527_stress_full_stress_suite_task57.md`.
