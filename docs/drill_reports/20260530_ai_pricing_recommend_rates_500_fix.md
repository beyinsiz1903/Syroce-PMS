# Drill — ai_pricing recommend-rates deterministik 500 fix (2026-05-30)

## Özet

Full Stress Suite (CI, commit `26ff329`) iki ardışık run'da aynı tek FAIL'i verdi:
`43-ai-pricing-dryrun.spec.js` C) cross_tenant_pricing →
`POST /api/ai/recommend-rates` **pilot token** ile `status=500`, `leak_hits=0`
(çapraz-tenant sızıntı YOK). A) (stress token, seedli veri, `base_price>0`)
PASS. Tekrarlama + pilot'a özgü + stress'te yok → **transient değil,
deterministik**.

Operatör kuralı uyarınca (aynı endpoint/imza tekrarladı) transient kabul
edilmedi; derin inceleme açıldı.

## Kök sebep (kanıtlı)

Pilot tenant `rooms` read-only sorgusu (tenant id yazdırılmadan, agregat):
- 31 oda, 7 room_type.
- lowercase **`'standard'`** tipi: tek oda, `base_price = None` (missing/null=1).
- Diğer tipler (`Standard`, `Deluxe`, ...) geçerli `base_price>0`.

Eski handler (`backend/domains/ai/router/autopilot_reco.py`):
- Satır 679: `base_rate = rt_rooms[0]['base_price'] if rt_rooms else 0` → `'standard'`
  için `None` alıyor.
- Satır 691/709: `recommended_rate = base_rate * 1.25` → `None * 1.25` =
  **TypeError**; ya da `base_rate=0` durumunda satır 727
  `(recommended_rate - base_rate) / base_rate` = **ZeroDivisionError**.
- İkisi de unhandled → HTTP 500.

Stress seed verisi her zaman geçerli `base_price` taşıdığından A) PASS; pilot
kirli/legacy veri tek FAIL kaynağı. Güvenlik invariantı sağlam (sadece server
error, sızıntı yok).

## Düzeltme (minimal, savunmacı)

`backend/domains/ai/router/autopilot_reco.py`:
1. `base_rate` artık oda tipindeki **ilk geçerli (sayısal, non-bool, >0)**
   `base_price`'a düşüyor; yoksa fail-safe `0`. (string/None/eksik/0 hepsi güvenli.)
2. `difference_pct` bölmesi sıfıra karşı korundu: `... if base_rate else 0.0`.

Kirli fiyatlı oda tipi artık 500 yerine benign `current_rate=0` önerisi üretir;
geçerli tipler etkilenmez.

## Doğrulama

- Unit: `backend/tests/test_ai_recommend_rates_occupancy.py` — mevcut occupancy
  testi değişmeden PASS + yeni `test_recommend_rates_dirty_base_price_no_500`
  (None / eksik anahtar / 0 / karışık geçerli+geçersiz) PASS. 2 passed.
- Canlı (read-only, gerçek pilot Atlas verisi): `recommend_rates` doğrudan
  çağrıldı → exception YOK, 49 öneri döndü, `'standard'` benign işlendi.
- Architect (evaluate_task, includeGitDiff): **PASS**. Doctrine: no fake-green /
  no RBAC broadening / no PII / no pilot mutation / external_calls=[] — hepsi OK.
  Regression testi anlamlı (vacuous değil).

## Bilinçli kapsam dışı

- Architect residual bir `KeyError` yolu işaret etti: `r['room_type']` doğrudan
  indeksleme; `room_type` eksik bir oda dokümanı hâlâ 500'leyebilir. **Pilot
  veride böyle bir oda YOK** (tüm odalarda room_type mevcut), failing spec bu
  yola değmiyor → spekülatif-patch yapılmadı. Robustluk genişletmesi gerekirse
  ayrı tur + kendi regression'ı ile eklenir.

## Baseline / süreç

- Run #162 baseline pointer (`bde7662`, `digitalocean.md`) **TAŞINMADI** — yeni GREEN
  CI artifact doğrulanana kadar official kalır.
- Agent CI dispatch edemez; operatör `stress.yml` re-dispatch eder.
- Beklenti: bu fix sonrası ai_pricing 21/0/0/0, FAIL adım=0; diğer invariantlar
  (failedTests=0, P0=P1=0, external_calls=[], pilot_drift=0, cleanup#2 idempotent)
  korunursa baseline promosyonu değerlendirilir.
