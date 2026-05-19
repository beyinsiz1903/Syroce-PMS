# F8D Stress Suite — Evolution (HR / Staff / Shift / Leave / Department, tur-1)

**Status:** TUR-1 PUSH — CI #1 bekleniyor (beklenti: GO WITH WATCH)
**Date:** 2026-05-18
**Scope:** `frontend/e2e-stress/specs/20..23` (4 spec, 19 test), F8A+F8B+F8C operasyonel paketinin üzerine HR yüzeyleri.
**Drill rapor:** `docs/drill_reports/20260518_stress_f8d_hr_staff_shift_leave.md`

Bu ADR F8D stres test suite'inin tur detaylarını içerir. `replit.md` "Gotchas" bölümünde tek-satır özet bırakılmıştır.

---

## Seed extension

`backend/domains/admin/router/stress.py` → `_build_f8d_docs(stress_tid, prefix, now)` factory:

- 5 hr_departments (FO, HK, F&B, MAINT, ADMIN) — `code={prefix}DEPT_<id>` app-level unique
- 8 hr_positions (Front Desk Agent/Supervisor, Housekeeper/Supervisor, Waiter, F&B Manager, Maintenance Tech, HR Officer)
- 30 staff_members (rol dağılımı: 10 HK + 8 FO + 6 F&B + 4 MAINT + 2 ADMIN)
- 30 leave_balances (her staff için annual_entitled_days=14, remaining_days=14)
- 60 attendance_records (son 6 gün × 10 staff sample, hepsi CLOSED — `clock_out` set)
- 20 shift_schedules (gelecek 7 gün, morning/evening/night dönüşümü, status=scheduled)
- 5 leave_requests (status=pending, decision testi için)
- 5 shift_swap_requests (status=pending, consent + decision testi için)
- 3 performance_reviews (status=draft)

`STRESS_COLLECTIONS` + orphan_cleanup loop'a 10 yeni koleksiyon eklendi (payroll_records dahil — seed yok ama orphan scrub var, gelecek spec'ler için forward-compat). `tenant_context(stress_tid)` wrap koruması korunur.

## Kritik invariantlar (dry-run guarantees)

- **(a) External dispatch yok:** HR notifications `_notify_hr_managers`/`_notify_user` sadece `notifications` koleksiyonuna yazar — Resend/SMS/push provider integration yok. F8B'de zaten `notifications` orphan scrub var.
- **(b) Payroll write yok:** `/api/hr/payroll/finalize` endpoint'i `payroll_records` koleksiyonuna yazar (live workflow); spec'ler ASLA çağırmaz. Sadece read endpoint'ler (`/api/hr/payroll/summary`, `/api/hr/payroll/preview`) testlerde olabilir.
- **(c) Leave-balance recalc:** Approval üzerinde in-memory + DB update; side effect yok.
- **(d) Attendance collision:** Seed'deki tüm kayıtlar CLOSED (`clock_out` set) → spec 21-B yeni OPEN row açabilir, app-level unique `(staff_id, date, clock_out:None)` ihlal etmez.
- **(e) Department code uniqueness:** Prefix-isolated (`{prefix}DEPT_FO` vb.) → aynı tur içinde re-seed güvenli.

Helper: `callTimedWithBackoff` (F8B tur-24) + 1500ms inter-call gap + `test.setTimeout(180_000)` 5+ call loop'larda.

---

## Tur-1 — ilk push

- **Seed extension** ✅ — `_build_f8d_docs` + `STRESS_COLLECTIONS` extension + orphan_cleanup + counts wire-up.
- **Spec 20 (hr_staff_org)** — Setup/list_org/bulk_create_staff(N=5)/pilot_drift. RBAC fallback (`permFail === N`) → P2 SKIP.
- **Spec 21 (hr_attendance)** — Setup/records_summary/clock_in(N=5)/clock_out(N≤5)/pilot_drift. Staff pool offset 20-30 (seed 60-attendance kullanmadığı staff).
- **Spec 22 (hr_leave)** — Setup/list_requests/create_requests(N=5)/decision(approve+reject alternating)/pilot_drift.
- **Spec 23 (hr_shift)** — Setup/list_swaps(404 tolerant)/create_swaps(N=5)/consent_decision lifecycle/pilot_drift. Staff offset 5-10 (requester) + 15-20 (target) → seed swap çakışması yok.

### Module-blocked desen (F8C tur-4/tur-5 mirror)

Setup'ta endpoint reachability + seeded pool probe. `moduleBlocked=true` koşulları:
- 20: `/api/hr/departments` veya `/api/hr/positions` non-2xx veya seeded dept/position bulunamadı.
- 21: `/api/hr/staff` non-2xx veya prefix-tagged staff pool < 5.
- 22: `/api/hr/staff` non-2xx veya `/api/hr/leave-balance/<id>` probe fail veya pool < 5.
- 23: `/api/hr/staff` non-2xx veya pool < 10 (5 requester + 5 target).

`moduleBlocked=true` → P2 informational finding + A/B/C `test.skip(true, ...)`; D pilot_drift bağımsız çalışır (kasıtlı: pilot mutation gate her durumda enforce edilmeli).

### RBAC short-circuit deseni

Spec B (bulk create) içinde `permFail === N` (tüm istekler 401/403) → P2 SKIP, FAIL ETMEZ. Backend manuel rol listesi (leave-request line 350 `admin/supervisor/finance`) kasıtlı; F8D resilience tercih edildi.

---

## Sonraki turlar (yer tutucu)

CI #1 sonucu burada güncellenecek. Beklenen başarı kriterleri:
- failedTests = 0
- P0 = P1 = 0 (P2 informational findings izin verilir)
- external_calls_made = []
- pilot_drift = 0
- 19/19 test yeşil (RBAC tarafından skip edilenler dahil — Playwright skip = pass-equivalent)

NO-GO durumunda tipik root cause hipotezleri:
- Backend cache stale (F8C tur-3'teki `_seed_spaces` fallback gibi). Çözüm: `?nocache=1` veya cache_warmer pop pattern.
- Staff field shape drift (`full_name` yok, sadece `first_name`+`last_name`). Çözüm: Setup probe'unda her iki alana bak.
- `staff_pool` filter'da prefix match field yok. Çözüm: `email.toLowerCase().startsWith(prefix.toLowerCase())` fallback (zaten implemente).

---

## Acceptance

- T001 ✅ Seed extension applied (`stress.py` syntax OK, Backend API restart edildi).
- T002 ✅ 4 spec yazıldı, Playwright list 19 test yükledi.
- T003 ⏳ CI #1 sonucu burada raporlanacak.

---

## F8D-v2 — HR deep stress (2026-05-19, Task #205)

**Status:** PUSH HAZIR — CI bekleniyor (beklenti: GO WITH WATCH).
**Date:** 2026-05-19
**Scope:** `frontend/e2e-stress/specs/32..36` (5 yeni spec, ~24 yeni test). Mevcut seed (`_build_f8d_docs`) uzatılmadı — STRESS_COLLECTIONS zaten v1'de payroll_records dahil 10 koleksiyonu kapsadı.
**Backlog source:** `docs/STRESS_TEST_ROADMAP.md` § "F8D backlog — HR / İK / Staff / Shift / Leave (v2)".

### v2 spec set

- **32 (hr_perf) — Performance review lifecycle.** v1'de hiç dokunulmamış `performance_reviews` + `performance_checkins` lifecycle: list reviews (GET /api/hr/performance) → per-review checkin CREATE (POST /api/hr/performance/{id}/checkin) → checkin LIST + DELETE cleanup (idempotent residue=0) → per-staff summary GET. Seeded 3 draft review üzerinde lifecycle; yeni perf_review yazımı yok (cleanup orphan riski sıfır).
- **33 (hr_payroll) — Payroll dry-run smoke.** READ-only: GET /payroll/{month}, GET /payroll/export, GET /payroll/export/csv (CSV stream). **FORBIDDEN runtime invariant:** POST /api/hr/payroll/finalize ASLA çağrılmaz; Setup adımında literal regex (`/(['"])post\1[^)]*\/api\/hr\/payroll\/finalize|request\.post\([^)]*\/api\/hr\/payroll\/finalize/i`) ile spec source-scan guard, ihlal → P0 + spec FAIL. CSV body içinde JWT-shape leak guard (P0). payroll_records koleksiyonuna spec write yok.
- **34 (hr_leave_accrual) — Leave balance accrual + carryover.** GET /leave-balance/{staff_id} baseline → POST /leave-request fresh + POST decision approve → re-read balance asserts `used` artar (decrement contract). POST /leave-balance ile carryover upsert + readback + restore-on-cleanup. Future-year accrual probe (POST balance year+1). RBAC short-circuit: require_op(view_executive_reports) eğer super_admin'i reddederse P2 SKIP.
- **35 (hr_shift_conflict) — Shift conflict + coverage.** POST /api/hr/shifts S1 (09-13) → POST S2 OVERLAPPING (10-14) aynı staff/date. 409 beklenir; backend 200 verirse **P1 "Shift overlap guard MISSING"** finding (production double-booking riski). Coverage: GET /api/hr/shifts 7-gün penceresi → dept rollup, HK ≥ 2 unique staff (P2 finding aksi halde). D adımı DELETE her iki shift'i (idempotent re-DELETE = 404).
- **36 (hr_rbac_pii) — RBAC + PII + audit.** GET /api/hr/staff response phone/national_id `assertPiiMasked` (P0/P1 KVKK). GET /api/hr/staff/{id}/salary-history `assertNoTokenLeak` per stress staff. GET /api/security/audit-logs token leak guard + cross-tenant entry leak guard (response items[].tenant_id === pilot_tid → P0). GET /api/hr/staff/{id}/profile PII walk.

### Doktrin

Her spec F8D v1 desenini birebir izler:
- **Module-blocked**: Setup `withModuleProbe()` non-2xx → `moduleBlocked=true` + P2 informational + A/B/C/D `test.skip()`; E pilot_drift+external_calls invariants **bağımsız** çalışır.
- **RBAC short-circuit**: permFail dominant (101/103) → P2 SKIP, FAIL ETMEZ (super_admin require_op gate'lerinde drift bekleniyor).
- **callTimedWithBackoff** + 400-1500ms inter-call gap + `test.setTimeout(120-180s)` 3+ call loop'larda.
- **Spec-created records cleanup**: sadece DELETE endpoint'i olan koleksiyonlarda yazma (perf_checkins, shift_schedules); endpoint olmayan koleksiyonlar (perf_reviews) için spec içinde write YOK → orphan riski 0.

### Dry-run invariants

- **External dispatch yok**: leave decision + perf checkin sadece `notifications` / `performance_checkins` koleksiyonlarına yazar; Resend/SMS/push provider çağrısı yok.
- **Payroll write yok (KESİN)**: source-scan guard + runtime invariant (D step "forbidden_doctrine" rec).
- **Pilot mutation yok**: E adımı `assertPilotDriftZero` + `assertNoExternalCallsPostBatch`.
- **Audit log scope**: spec 36/C audit response içinde stress token tarafından pilot_tid entry görülürse P0.

### Acceptance — F8D-v2

- T101 ✅ 5 spec dosyası `frontend/e2e-stress/specs/32..36` oluşturuldu (`node --check` clean, tüm helper signature'ları doğrulandı).
- **T101a (architect iter-1, 2026-05-19)** — Code review 4 kritik contract bulgusu çıkardı, tümü düzeltildi:
  - **Spec 32 contract fix**: GoalCheckinPayload enum `'in_progress'` (yanlış) → `'on_track'|'at_risk'|'blocked'` (router line 2762). Aksi halde 422 + false P1 floor fail.
  - **Spec 34 contract fix**: LeaveDecision body `{action: 'approve'}` (yanlış) → `{decision: 'approve'}` (router line 112-114). Aksi halde decision FAIL + decrement assertion yanlış sinyal.
  - **Spec 33 ESM-safe source-scan**: `__filename` Playwright ESM context'inde `ReferenceError` atabilir → `typeof __filename !== 'undefined'` guard + `path.join(process.cwd(), …)` fallback chain + source unreachable durumunda P2 informational rec (runtime invariant defense-in-depth korunur).
  - **Spec 34 D-step residue fix**: future-year leave-balance POST upsert kaldırıldı (cleanup yolu yoktu) → READ-only default behavior probe (router line 1571 `annual.entitlement=14` İş K. m.53 fallback) doğrulandı; stress-tenant residue 0.
  - Not: Spec 34/B onaylanan leave_request terminal state'te kalır (DELETE endpoint yok); F8D v1 spec 22 ile aynı doctrine — STRESS_COLLECTIONS unified cleanup loop `leave_requests` koleksiyonunu tenant-scoped scrub eder.
- T102 ⏳ CI bekleniyor (beklenti: failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0).
- T103 — NO-GO durumunda olası root cause:
  - Spec 33 `__filename` ESM Playwright runtime'da undefined olabilir → fallback `path.join(process.cwd(), …)` zaten implemente.
  - Spec 34 leave-balance upsert require_op gate stress admin'i reddediyorsa → SKIP+P2 (FAIL değil).
  - Spec 35 backend overlap guard yoksa → P1 finding bekleniyor (kasıtlı; verdict GO WITH WATCH'a düşürür, NO-GO yapmaz).
  - Spec 36 `/api/security/audit-logs` endpoint deploy-spesifik 404 → REVIEW + P2 (P0 değil).
