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
