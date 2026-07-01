# NO-GO analizi — 2 transient 500 FAIL (b2b P1 kapandı) — 20260530

Run: commit `26ff329` (b2b auth fix dahil), tag `full_stress_suite`, 702 test.
Sonuç: **NO-GO** — failedTests=0, FAIL adım=2, P0=0, **P1=1**, P2=58, P3=1.

## b2b P1 → KAPANDI (doğrulandı)

Önceki run (a148a455) tek FAIL'i `b2b_api` idi. Bu run: `b2b_api` = PASS 56 / FAIL 0 /
REVIEW 1 (REVIEW = per-subrouter scope provisioning, **by-design** karar — D testi açıkça
"Tasarım kararı" diyor, P1 değil). Missing X-API-Key → 401 fix işe yaradı.

## Kalan 2 FAIL — transient altyapı 500 imzası (kod regresyonu DEĞİL)

| # | Modül / step | Endpoint | Sinyal |
|---|---|---|---|
| 1 | `twofa_lifecycle` H) disable_cleanup (P1) | POST `/api/2fa/disable` | status=500 body=null |
| 2 | `ai_pricing` C) cross_tenant_pricing (FAIL) | POST `/api/ai/recommend-rates` (pilot token) | pilot_status=500, leak_hits=0 |

### Neden transient/altyapı, regresyon değil

1. **İki ilgisiz yüzey, aynı anda**: 2fa disable (stress user) + ai recommend-rates
   (pilot user) — farklı tenant, farklı kod yolu, ortak tek faktör aynı run.
2. **`body=null`**: FastAPI HTTPException her zaman `{"detail":...}` JSON döndürür.
   Null body = handled app hatası değil; instance overload / connection-pool exhaustion /
   Mongo-Redis anlık blip / proxy 500 imzası.
3. **Baseline-yeşil**: ikisi de #162 baseline'ında ve önceki run'da (a148a455 — tek FAIL
   yalnız b2b) PASS idi; yalnız bu run'da ve ilk kez çıktılar.
4. **Kod incelemesi temiz**:
   - `disable_2fa` (backend/routers/security_2fa.py:162) tüm bilinen hataları handled
     HTTPException (400/401/429) ile döner; 500 yolu yok. Stress user'ın `2fadis:`
     throttle anahtarı bu testte yalnız 1 kez çağrılır (throttle 5/900s — tetiklenmez).
   - `recommend-rates` C testi güvenlik açısından temiz: `leak_hits=0` → tenant
     isolation tuttu; 500 yalnız availability/durum sorunu, sızıntı değil.
5. **Tek kod değişikliği (b2b auth) ikisiyle de ilgisiz.**
6. **Tüm güvenlik invariant'ları tuttu**: leak_hits=0, pilot_drift=0, external_calls=[],
   cleanup#2 idempotent (7761→0). twofa H'de afterAll backup-code fallback (spec yazarının
   bilinçli "belt-and-braces" tasarımı) cleanup'ı garantiledi → pilot_drift=0.

## Karar / öneri

- Spekülatif kod yaması YOK (deterministik kök sebep yok; yama = fake-green riski).
- **Baseline #162 pointer (`bde7662`) TAŞINMADI.**
- Önerilen yol: suite'i **aynen yeniden dispatch** et. Transient ise iki FAIL tekrarlamaz;
  b2b fix kalıcı PASS verir. FAIL'ler aynı 500/null imzasıyla ya da deterministik tekrar
  ederse, o zaman derin inceleme (instance kaynak limitleri / Mongo-Redis CI env / ilgili
  endpoint hardening) ayrı tur olarak açılır.
- Alternatif (operatör onayıyla, ayrı tur): cleanup/probe adımlarına 5xx'te **tek sınırlı
  retry** — güvenlik assertion'larını (leak/drift/external_calls) hard-assert bırakarak;
  deterministik 500'ü maskelemez (retry de 500 verirse yine FAIL), yalnız transient
  flake'i azaltır. Bu spec değişikliği operatörün küratör alanı → onay gerekir.

## Doktrin

failedTests=0, external_calls=[], pilot_drift=0 korundu. "GO"/"/100" iddiası yok.
Baseline pointer taşınmadı; promosyon ancak tüm gate'leri geçen yeni GREEN artifact ile.
