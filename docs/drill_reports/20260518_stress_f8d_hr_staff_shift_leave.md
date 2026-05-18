# F8D Stress Drill — HR / Staff / Shift / Leave / Department (tur-1)

**Date:** 2026-05-18
**Scope:** `frontend/e2e-stress/specs/20..23` (4 spec, 19 test) + seed extension
**Backend seed:** `_build_f8d_docs` (5 dept + 8 pos + 30 staff + 30 leave_balance + 60 attendance + 20 shift + 5 leave_req + 5 swap + 3 perf)
**Environment:** `E2E_ALLOW_DESTRUCTIVE_STRESS=true`, `E2E_EXTERNAL_DRY_RUN=true`, `E2E_STRESS_TENANT_ID=<stress>`, `PILOT_TENANT_ID` set (read-only baseline).

## Suite composition

| Spec | Module | Tests |
|------|--------|-------|
| 20-hr-staff-org | departments + positions + staff list + bulk-create | Setup, A list_org, B bulk_create_staff, C pilot_drift (4) |
| 21-hr-attendance | records + summary read + clock-in/out lifecycle | Setup, A records_summary, B clock_in, C clock_out, D pilot_drift (5) |
| 22-hr-leave | leave-balance + create + approve/reject decision | Setup, A list_requests, B create_requests, C decision, D pilot_drift (5) |
| 23-hr-shift | shift-swap list + create + consent + final decision | Setup, A list_swaps, B create_swaps, C consent_decision, D pilot_drift (5) |

Toplam: 19 test (4 spec × Setup + 3-4 işlem + pilot_drift).

## Invariants (compile-time)

- **(a) External dispatch yok:** HR notifications in-app only (`notifications` koleksiyonu, F8B cleanup zaten kapsıyor). Payroll `/api/hr/payroll/finalize` ASLA çağrılmaz — write to `payroll_records` live workflow için. Specs sadece read + transitional CRUD.
- **(b) Pilot read-only:** Setup'ta `pilotBookingsCount` baseline → her spec sonunda D pilot_drift = 0 doğrulaması; non-zero = P0 FAIL.
- **(c) Tenant isolation:** Tüm seed dokümanları `tenant_id=<stress_tid>` + `stress_seed=True` + `stress_prefix=<round_prefix>`; orphan cleanup loop pre-insert farklı prefix'leri scrub eder.
- **(d) Unique constraints:** `hr_departments.code` app-level unique → her tur `{prefix}DEPT_<code>` ile prefix-isolated. `attendance_records (staff_id, date, clock_out:None)` collision riskine karşı seed'de TÜM kayıtlar `clock_out` set edildi (CLOSED) → spec 21-B clock-in yeni OPEN row açabilir.
- **(e) RBAC tolerance:** Stress admin `super_admin` → `require_op` geçer. Manuel rol listesi (leave-request line 350 `admin/supervisor/finance`) 403 dönerse spec içi `permFail === N` short-circuit → module-blocked SKIP + P2 informational, FAIL ETMEZ. Spec 14/15 (F8C) ile aynı resilience deseni.

## Beklenen GitHub Actions metrikleri

Aşağıdakiler CI #1'den (henüz çalışmadı) beklenen invariant kapısıdır. Gerçek değerler ilk run sonrası buraya yazılacaktır.

- failedTests = 0 (P2 informational findings izin verilir; module-blocked SKIP'ler FAIL değildir)
- P0 finding = 0 (pilot drift, gerçek external dispatch yok)
- P1 finding = 0 (floor ihlal yok — RBAC durumunda short-circuit aktif)
- external_calls_made = [] (post-batch invariant her destructive sonrası doğrulanır)
- pilot_drift = 0 (her spec sonunda D testi)
- seeded_counts: `hr_departments=5`, `hr_positions=8`, `staff_members=30`, `leave_balances=30`, `attendance_records=60`, `shift_schedules=20`, `leave_requests=5`, `shift_swap_requests=5`, `performance_reviews=3`

## Notlar

- **Bulk endpoint yok:** Tüm spec'ler single-POST loops + `callTimedWithBackoff` (429-aware) + 1500ms inter-call gap. `test.setTimeout(180_000)`.
- **Module-blocked pattern:** Setup'ta endpoint reachability + seeded staff pool probe; eksikse `moduleBlocked=true` ve A/B/C `test.skip(true, ...)` — D pilot_drift bağımsız.
- **23-A 404 toleransı:** `/api/hr/shift-swap-requests` list endpoint'i her backend'de mevcut olmayabilir; 404 → REVIEW only, FAIL değil.

| Final verdict | TBD — CI #1 sonrası güncellenecek (beklenti: GO WITH WATCH) |
|--|--|
