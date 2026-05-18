# Stress Test Roadmap (F8 Serisi)

**Hedef:** Tüm PMS modül yüzeylerini sırayla GitHub Actions stress CI'ya
sokmak — pilot tenant'a mutation yok, gerçek dış servis çağrısı yok,
external_calls=[], failedTests=0, P0=P1=0, verdict ≥ GO WITH WATCH.

## Mutlak kurallar (her faz için aynen geçerli)

- Pilot tenant'a **mutation yok** (yalnızca read; pilot_drift gate
  tüm spec'lerin son testidir).
- Gerçek **SMS / e-posta / OTA / payment / KVKK** çağrısı yok.
- `E2E_EXTERNAL_DRY_RUN=true` her zaman set.
- Cleanup idempotent (önce dry-run #1, sonra apply #2 no-op olmalı).
- `external_calls=[]` her batch sonunda re-assert.
- `failedTests=0`, `P0=0`, `P1=0`, final verdict ≥ **GO WITH WATCH**.
- Defans baseline: 5 gate (cleanup × 1, idempotent × 2, external_calls
  re-assert, pilot_drift), `module-blocked pattern` (endpoint 403/cache
  stale → `moduleBlocked=true` flag + P2 informational + A/B/C/D
  `test.skip()`, pilot_drift bağımsız çalışır).
- Seed: `STRESS_COLLECTIONS` listesi + `_build_<phase>_docs` factory +
  `stress_seed=True` + `stress_prefix=<prefix>` etiketleri, chunked
  insert + orphan cleanup loop.

## Faz listesi ve durumlar

| Faz  | Kapsam                                                                  | Spec aralığı              | Status                                                       | ADR                                                       |
| ---- | ----------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------ | --------------------------------------------------------- |
| F8A  | Front Office / Folio / Housekeeping (day-turnover, room-move, mass)     | 02 / 03 / 04 / 05         | **DONE** — GO WITH WATCH (CI #38 / #55 PASS, tur-6..22)      | `docs/adr/2026-05-f8a-stress-evolution.md`                |
| F8B  | Guest Experience (QR / complaints / messaging / notifications)          | 10 / 11 / 12 / 13         | **DONE** — GO WITH WATCH (CI #55 PASS, tur-23..26)           | `docs/adr/2026-05-f8b-stress-evolution.md`                |
| F8C  | MICE / Event / Banquet / Group Operations                               | 14 / 15 / 16 / 17         | **DONE** — GO WITH WATCH (tur-5 CI YEŞİL, 2026-05-18)        | `docs/adr/2026-05-f8c-stress-evolution.md`                |
| F8D  | HR / İK / Staff / Shift / Leave / Department                            | 20 / 21 / 22 / 23         | **DONE** — GO WITH WATCH (CI yeşil, 2026-05-18)              | `docs/adr/2026-05-f8d-hr-staff-shift-evolution.md`        |
| F8E  | Finance / Cashier / Accounting / Invoice / City Ledger                  | 24 / 25 / 26 / 27         | **IN PROGRESS** — tur-1 push (seed + 4 spec, 16 test), CI #1 bekleniyor | `docs/adr/2026-05-f8e-finance-stress-evolution.md`        |
| F8F  | Inventory / Stock / Purchasing / Supplier                               | 30 / 31 / 32 / 33 (TBD)   | Planlandı                                                    | TBD                                                       |
| F8G  | Sales / CRM / Offers / Contracts (F8C MICE-sales üstünde devam)         | 34 / 35 / 36 / 37 (TBD)   | Planlandı                                                    | TBD                                                       |
| F8H  | Reports / Analytics / Export                                            | 40 / 41 / 42 / 43 (TBD)   | Planlandı                                                    | TBD                                                       |
| F8I  | Admin / RBAC / Settings / Audit                                         | 44 / 45 / 46 / 47 (TBD)   | Planlandı                                                    | TBD                                                       |
| F8J  | **Full 24h Hotel Simulation** — tüm modüller birlikte                   | 50+ (chained scenario)    | Final — F8D-I yeşilden sonra                                 | TBD                                                       |

## F8D — sonraki başlatma için pre-flight notları

Aday yüzeyler (backend route taraması gerekecek, F8D session'ında):

- **Staff / Personel**: `/api/hr/staff*`, `/api/hr/employees*`, bulk
  create + role assignment + activation flow.
- **Shift**: `/api/hr/shifts*`, shift schedule generation, swap, conflict.
- **Task**: `/api/operations/tasks*` (eğer hr modülü altında değilse
  operasyon modülünden), assignment + completion + escalation.
- **Leave / İzin**: `/api/hr/leaves*`, request → approve/reject → balance
  decrement.
- **Department**: `/api/hr/departments*`, hierarchy, role mapping.

Dış servis riski: KVKK ID-photo entegrasyonu yoksa düşük; payroll
e-mail ve provider bildirim varsa `E2E_EXTERNAL_DRY_RUN` gate'i
zorunlu. `module-blocked pattern` her zaman fallback.

## Yapılış sırası

1. **Backend route taraması** (rg ile staff/shift/leave/department).
2. **Seed extension** (`backend/domains/admin/router/stress.py`):
   `STRESS_COLLECTIONS` += yeni koleksiyonlar, `_build_f8d_docs`
   factory.
3. **4 spec** (frontend/e2e-stress/specs/): Setup → A/B/C/D → external
   re-assert → pilot drift; serial mode, 1500ms gap,
   `callTimedWithBackoff` (429 retry).
4. **Drill report** (`docs/drill_reports/<date>_stress_f8d_*.md`).
5. **ADR** (`docs/adr/<yyyy-mm>-f8d-*.md`).
6. **replit.md** "Gotchas" → tek-satırlık pointer.

## Acceptance contract (her faz)

- failedTests=0, P0=0, P1=0
- external_calls_made=[]
- pilot_drift=0
- cleanup idempotent (#2 no-op)
- final verdict ≥ GO WITH WATCH

Bu dosya stress test serisi için tek doğruluk kaynağıdır. Faz
tamamlandıkça status sütunu güncellenir.
