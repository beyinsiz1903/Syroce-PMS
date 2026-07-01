# F8O — AI / Automation Dry-run Stress (Task #206)

**Tarih:** 2026-05-19
**Status:** IN_PROGRESS (specs eklendi, CI bekleniyor)
**Scope:** AI router yüzeyleri (upsell-insights, dynamic-pricing, no-show
risk) — vendor LLM HTTP çağrısı tetiklenmeden read-only stress.

## Hedef

Üretim AI / otomasyon endpoint'lerinin (revenue autopilot, no-show
prediction, guest-persona insights, dynamic rate recommendation) stres
testlerini eklemek; bunu yaparken:

1. Hiçbir vendor LLM (OpenAI / Anthropic / Gemini) HTTP çağrısı tetiklenmeden,
2. Pilot tenant'a mutation üretmeden,
3. Autopilot run-cycle / set-mode / ML train kapalı kapı (source-scan),
4. Cross-tenant insight / pricing / no-show leak guard'larıyla,
5. PII (phone/email/identity_number/passport_no) maskeleme doğrulamasıyla.

## Spec'ler

| Spec | Konu                              | Test sayısı | Module                |
| ---- | --------------------------------- | ----------- | --------------------- |
| 42   | AI upsell insights dry-run        | 6 (setup+A+B+C+D+E) | `ai_upsell`     |
| 43   | AI dynamic pricing dry-run        | 7 (setup+A+B+C+D+E+F) | `ai_pricing`  |
| 44   | AI no-show risk dry-run           | 7 (setup+A+B+C+D+E+F) | `ai_noshow_risk` |

Toplam: **20 test** (3 spec).

## Mutlak kurallar (F8O)

- **Vendor LLM HTTP çağrısı YOK** — backend `briefing.ai_powered=false`
  invariant'ı her batch sonunda doğrulanır (`assertNoVendorHttpCall`).
  Fail-closed: hem `/api/ai/diagnostics/llm-state` hem
  `/api/ai/dashboard/briefing` unreachable → P0 finding.
- **Pilot mutation YOK** — `assertPilotDriftZero(baseline, after)` her
  spec'in son testi.
- **Autopilot run-cycle / set-mode YASAK** — `assertEndpointNeverCalled`
  spec source-scan; literal substring spec dosyasında geçemez (helper
  sabitleri kasıtlı string concat ile inşa edilmiştir).
- **ML training YASAK** — `/ml/train-all` + `/ml/<x>/train` fragmenti
  source-scan ile yakalanır.
- **`external_calls=[]`** — her batch sonu re-assert.
- **`failedTests=0`, `P0=0`, `P1=0`** — verdict ≥ GO WITH WATCH.

## Module-blocked doctrine

Setup probe non-2xx (403/404/network) → `moduleBlocked=true` + P2
informational. Setup'a ek olarak:

- Spec 42/43/44 **A/B/C** step'leri `test.skip()`,
- **D (forbidden source-scan) + E (vendor-call guard) + F (pilot_drift +
  external_calls)** **BAĞIMSIZ** çalışmaya devam eder.

Bu sayede AI router'ı stres ortamında deploy edilmemiş bile olsa,
forbidden-endpoint kapalı kapısı + vendor-call guard + pilot isolation
invariant'ları her zaman çalışır.

## Backend ekleme

`backend/domains/ai/router/ops.py` — yeni endpoint:

```
GET /api/ai/diagnostics/llm-state
RBAC: view_system_diagnostics (super_admin)
Returns: { llm_enabled, providers: { openai|anthropic|gemini_configured },
          e2e_ai_dry_run, model_name_default, note }
```

**Critical**: Bu endpoint hiçbir vendor HTTP çağrısı yapmaz. Pure
config read (env var presence + service flag). API key value asla
döndürülmez.

## Helper eklemeleri

`frontend/e2e-stress/fixtures/stress-helpers.js`:

- `FORBIDDEN_AI_AUTOPILOT_RUN`, `FORBIDDEN_AI_AUTOPILOT_SETMODE`,
  `FORBIDDEN_AI_ML_TRAIN_ALL`, `FORBIDDEN_AI_ML_TRAIN_FRAGMENT` — string
  concat sabitleri (spec source-scan false-positive önlemi).
- `assertNoVendorHttpCall(testInfo, module, request, token, label?)` —
  briefing.ai_powered=false guard, fail-closed her iki probe unreachable
  ise.
- `assertAiKeyShapeIsSentinel(testInfo, module, llmStateBody)` —
  informational; E2E_AI_DRY_RUN flag eksikse P2 emit.

## Cross-tenant leak guard'ları

| Spec | Leak surface                      | Probe                                          | Severity |
| ---- | --------------------------------- | ---------------------------------------------- | -------- |
| 42   | guest_id (insights)               | pilot token → stress guest_id substring        | P0       |
| 43   | room_type (recommendations)       | pilot token → stress prefix'li room_type leak  | P0       |
| 44   | booking_id (no-show predictions)  | pilot token → stress booking_id substring      | P0       |

## STRESS_COLLECTIONS güncellemesi

Bu fazda yeni koleksiyon seed YOK (read-only). Forward-compat amaçlı:

- `guest_personas` — `/api/ai/guest-persona/analyze/{guest_id}` POST yaparsa
  oluşur (bu fazda çağrılmıyor, ama future cleanup için STRESS_COLLECTIONS'a
  eklenebilir; bu PR'da değiştirilmedi).

## GO/NO-GO kriteri

- `failedTests=0`
- `P0=0`, `P1=0`
- `pilot_drift=0` (her spec'in son test'i)
- `external_calls=[]` (her batch sonu)
- `briefing.ai_powered=false` (vendor isolation invariant)
- Verdict ≥ **GO WITH WATCH**

## Backlog (F8O v2)

- Vendor key sentinel format detection (backend masked api_key suffix
  döndürürse spec içinde shape check eklenir).
- Concierge social `/api/ai/concierge/*` surface — F8O scope'undan
  şimdilik dışarıda (Task #206 minimal scope).
- ML model status (`GET /api/ml/models/status`) — read-only, future F8O
  v2 batch'inde eklenir.
- Predictive maintenance `/api/ai/predictive-maintenance/analyze` —
  potentially LLM-backed; vendor-call guard yeterli kapsamayı sağlar
  ama explicit spec yok.
