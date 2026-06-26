# ADR — Acente <-> PMS Entegrasyon Sozlesmesi (Haziran 2026)

**Durum**: ACCEPTED (sozlesme dondu). Bu dokuman yalnizca mimari karari ve tel-uzeri (wire) kontrati sabitler. Kod, veritabani semasi ve endpoint implementasyonu KAPSAM DISI — ayri uygulama turlarinde yapilir.

**Baglam**: B2B Acente uygulamasi PMS'in icine gomulmeden, kendi reposu/Docker konteyneri icinde yasayan ayri bir servistir. Iki servis ancak acik, versiyonlu, kimlik-dogrulamali bir kontrat uzerinden konusur. Bu ADR, iki servisin birbirine soyledigi her seyi (rezervasyon olusturma, musaitlik sorgusu, musaitlik push) yaziya dokup dondurur. Loyalty modulu bilincli olarak ertelendi (ayri is kolu).

**Doktrin bagi**: no fake-green, auth/RBAC zayiflatma yok, PII/secret/imzali-URL loglanmaz, fail-closed (not_configured), tenant izolasyonu mutlak, additive. Overbooking dogrulugu yalnizca DB-atomiktir; Redis kilidi correctness sinirini olusturamaz.

---

## Karar 0 — Iletisim topolojisi: REST request/response + imzali webhook. Redis Pub-Sub HAYIR.

- **Senkron sorgu/komut** (musaitlik+fiyat sorgusu, rezervasyon olustur/degistir/iptal): Acente -> PMS yonunde versiyonlu **REST** request/response.
- **Anlik push** (PMS -> Acente: envanter/fiyat/restriksiyon degisikligi): **imzali webhook** + outbox/retry + idempotency.
- **Redis Pub-Sub entegrasyon omurgasi DEGILDIR**: teslim garantisi/replay/idempotency/audit yoktur; paylasilan Redis iki bagimsiz servisi siki bagla baglar ve "kursun gecirmez sinir" hedefini bozar. Redis yalnizca cache / rate-limit / gecici koordinasyon icin kalir.

---

## Karar 1 — Tel formati: Hafif ozel JSON, kanonik modele 1:1 hizali, versiyonlu, strict.

- Wire formati **OTA/HTNG XML DEGIL**, hafif modern JSON'dur. Gerekce: iki ucu da biz sahipleniyoruz; OTA/HTNG'nin tek varlik sebebi olan uciuncu-taraf interoperabilitesi burada yok. OTA/HTNG yalnizca gercek OTA'lar icin provider kenarinda bir esleme endisesi olarak kalir (Exely gibi).
- JSON, mevcut `backend/channel_manager/domain/models/canonical.py` icindeki `CanonicalReservation`/`CanonicalGuest` alanlarina **1:1 map** edilir. Yeni kanonik sozluk ICAT EDILMEZ — acente, mevcut SXI kanal saglayicilariyla (HotelRunner/Exely) ayni ic sozlesmeye bosalan yeni bir "Kanal Saglayicisi" adaptorudur.
- **Versiyonlama**: birinci gunden zorunlu. URL'de major version (`/api/agency/v1/...`) + govdede `schema_version` (string, or. `"2026-06"`). Donmus kontrat; kirici degisiklik = yeni major.
- **Bilinmeyen alan politikasi**: strict **reject** (HTTP 422), sessiz yutma YOK. Fail-closed.
- **Para birimi/tutar**: tutarlar ondalik string DEGIL, kanonikteki gibi sayisal; `currency` ISO-4217 (varsayilan kabul yok, alan zorunlu). Tarihler `YYYY-MM-DD` (kanonik konvansiyon).

### Alan eslemesi (Acente JSON -> CanonicalReservation)

| Acente JSON alani | Kanonik alan | Not |
|---|---|---|
| `agency_reservation_id` | `external_id` | Acente tarafi essiz id; dedup anahtari |
| `confirmation_number` | `confirmation_number` | Opsiyonel |
| `status` | `status` (ReservationStatus) | confirmed/provisional/cancelled/modified |
| `arrival_date` / `departure_date` | `arrival_date` / `departure_date` | YYYY-MM-DD, departure > arrival |
| `room_type_id` | `room_type_id` | PMS oda tipi (eslenmemisse 422 mapping hatasi) |
| `rate_plan_id` | `rate_plan_id` | PMS rate plan |
| `occupancy.adults` / `occupancy.children` / `occupancy.child_ages` | `adult_count` / `child_count` / `child_ages` | |
| `room_count` | `room_count` | |
| `meal_plan` | `meal_plan` (MealPlan) | RO/BB/HB/FB/AI |
| `pricing.total` / `pricing.sub_total` / `pricing.tax_total` | `total_amount` / `sub_total` / `tax_total` | |
| `pricing.currency` | `currency` | ISO-4217 |
| `pricing.breakdown[]` | `price_breakdown[]` (PriceBreakdown) | gece-bazli |
| `commission.amount` / `commission.rate` | `commission_amount` / `commission_rate` | |
| `payment_type` | `payment_type` | prepaid / pay_at_hotel / credit_card_guarantee |
| `guest.{first_name,last_name,email,phone,nationality,national_id,country_code,...}` | `CanonicalGuest.*` | PII; log'lanmaz |
| `special_requests` | `special_requests` | |

Acente JSON, kanonikteki saglayici-ozel alanlari (`hr_number`, `message_uid`, `requires_ack`) ICERMEZ — bunlar HotelRunner'a ozeldir.

---

## Karar 2 — Servisler-arasi kimlik (S2S API key + imza)

- Otel ve acente anlastiginda PMS tarafinda her ikili-iliski icin ayri bir **API key** uretilir (mevcut `backend/routers/b2b_api/api_keys.py` deseni). Key tek bir `(tenant_id, agency_id)` ciftine baglidir; cross-tenant kullanim fail-closed reddedilir.
- Her acente->PMS istegi su header'lari tasir:
  - `Authorization: Bearer <api_key_id>` (key tanimlayici; sir degeri govdede/log'da gecmez)
  - `X-Agency-Timestamp` (Unix saniye), `X-Agency-Nonce` (essiz jti), `X-Agency-Signature`
- **Imza string-to-sign (kanonik, donmus)** — sadece body imzalamak YETERSIZ (endpoint-substitution + replay riski). Imza su kanonik dizinin HMAC-SHA256'sidir:
  ```
  string_to_sign = key_id + "\n" + method + "\n" + path + "\n" +
                   canonical_query + "\n" + timestamp + "\n" + nonce + "\n" +
                   sha256_hex(body)
  X-Agency-Signature = hex(hmac_sha256(shared_secret, string_to_sign))
  ```
  `canonical_query`: query parametreleri ad'a gore siralanmis ve URL-encode edilmis hali (bos ise "").
- **Tazelik + saat-kaymasi (clock-drift) penceresi (donmus)**: kabul penceresi = tazelik **+/- 300s** + saat-kaymasi toleransi **+/- 60s** = **etkin +/- 360s**. Gerekce: NTP sapmasi/cluster dugum farki meşru istegi rastgele 401'e dusurmemeli (or. acente saati 65s geri kalirsa). Pencere disi timestamp -> 401. Tum PMS dugumleri NTP zorunlu calistirir; bu pencere bir mazeret degil, guvenlik agi.
- **Replay korumasi (TToU)**: `nonce` (jti) **replay-cache**'te tutulur; ayni nonce tekrari -> 401. **Degismez kural**: replay-cache TTL **>= etkin kabul penceresi (360s)** — aksi halde nonce suresi dolup timestamp hala gecerliyken replay penceresi acilir. Tek basina timestamp replay'i kapatmaz.
- Imza/secret **dogrulama PMS sunucu tarafinda**; gecersiz/eksik imza, pencere disi timestamp, tekrar eden nonce -> fail-closed 401. Secret degerleri asla log/yanit/hata govdesinde gecmez.
- PMS->acente webhook'lari ayni simetrik string-to-sign + nonce semasini tasir (`X-Syroce-Signature` / `X-Syroce-Nonce` / `X-Syroce-Timestamp`), acente tarafinda ayni sekilde dogrulanir.

---

## Karar 3 — Istek/Cevap sozlesmesi

### 3.1 Musaitlik + fiyat sorgusu (Acente -> PMS)

`GET /api/agency/v1/availability?room_type_id=&arrival_date=&departure_date=&adults=&children=`

200 yaniti (ozet):
```
{
  "schema_version": "2026-06",
  "currency": "TRY",
  "nights": [
    { "date": "2026-07-01", "room_type_id": "...", "rate_plan_id": "...",
      "available": 3, "sell_rate": 4200.0, "restrictions": { "closed": false,
      "closed_to_arrival": false, "min_stay": 1 } }
  ]
}
```
Bu yanit baglayici teklif DEGILDIR (musaitlik anliktir; kesin sonuc rezervasyon olusturmada belirlenir).

### 3.2 Rezervasyon olusturma (Acente -> PMS)

`POST /api/agency/v1/reservations`
- Header: `Idempotency-Key` (zorunlu), kimlik+imza header'lari (Karar 2).
- Govde: Karar 1 alan eslemesindeki acente JSON'u.
- Basari **201**:
```
{ "pms_reservation_id": "...", "confirmation_number": "...",
  "status": "confirmed", "schema_version": "2026-06" }
```
- Cakisma (son oda kapildi) **409** (Karar 5).
- Dogrulama/eslesme hatasi **422** (bilinmeyen alan, eslenmemis room_type/rate_plan, gecersiz tarih).
- Yetki/imza **401/403**, gecici altyapi **503**, rate-limit **429**.

### 3.3 Degisiklik / iptal (Acente -> PMS)

`PATCH /api/agency/v1/reservations/{agency_reservation_id}` (modify),
`DELETE /api/agency/v1/reservations/{agency_reservation_id}` (cancel).
- `agency_reservation_id` = kanonik `external_id`; PMS bu anahtarla bulur.
- Iptal sonrasi envanter serbest birakma DB-atomiktir; basari 200, bulunamaz 404, terminal-state catismasi 409.

---

## Karar 4 — Idempotency kurallari

- **`Idempotency-Key` zorunlu** olan uclar: rezervasyon olustur (POST), degistir (PATCH), iptal (DELETE).
- **TTL**: anahtar kaydi **48 saat** saklanir. Bu sure, acentenin maksimum retry penceresinden buyuk olmalidir (Karar 6 webhook backoff ~24h ile uyumlu, marjli).
- **Iki-katmanli saklama (donmus) — RAM maliyeti kontrolu**: rezervasyon yanit govdeleri agir JSON'dur (misafir PII, folio, fiyat tablolari); tamamini 48h Redis RAM'inde tutmak belleği sisirir. Bu yuzden:
  - **Sicak katman (Redis/Valkey)**: yalnizca in-flight kilitleri + sicak tekrarlar icin **15-30 dk** TTL. RAM temiz kalir.
  - **Soguk katman (MongoDB `idempotency_cache`)**: cozulen yanit asenkron olarak Mongo'ya offload edilir, **TTL index** ile 48h sonunda otomatik silinir. Sicak katmanda yoksa Mongo'dan replay edilir.
  - Scope ve davranis matrisi her iki katmanda ozdes; PII govdesi soguk katmanda sifrelenir veya referans tutulur (log'lanmaz).
- **Davranis matrisi**:
  - Ayni key + ayni govde parmak-izi (`payload_fingerprint`, mevcut `reservation_import` deseni) -> orijinal yanit **tekrar uretilir** (cached), is yeniden CALISTIRILMAZ. Idempotent.
  - Ayni key + FARKLI govde -> **422 idempotency_conflict** (anahtar yeniden kullanilmis).
  - Ayni key, ilk islem hala devam ediyor (in-flight) -> **409 idempotency_in_progress** (acente kisa backoff ile yeniden dener — bu 409, Karar 5'teki `inventory_conflict` 409'undan FARKLI; retry edilir).
  - TTL dolduktan sonra ayni key -> yeni islem olarak ele alinir (acente o pencere sonrasi yeni key uretmeli).
- **Idempotency scope (donmus)**: `(tenant_id, agency_id, method, path, idempotency_key)`. Yalniz key ile scope yetersizdir — ayni anahtar farkli uclarda (or. POST create vs PATCH modify) yanlis 422/409 uretebilir. Method+path baglama bunu engeller. Cross-tenant gorunmez.

---

## Karar 5 — Atomik rezervasyon kilidi ve yaris-durumu (409)

- Tek gerceklik kaynagi: **DB-atomik kosullu guncelleme** (`find_one_and_update`, kosul `available > 0`) — mevcut room-night lock / negative-stock guard / `channel_event_dedup` claim desenleriyle simetrik. Redis kilidi yalnizca opsiyonel cekisme-azaltma; correctness sinirini OLUSTURAMAZ.
- Iki acente son odayi ayni anda satarsa: yalnizca DB-atomik kazanan 201 alir; kaybeden:
```
HTTP 409 Conflict
{ "error_code": "inventory_conflict",
  "conflict_date": "2026-07-01",
  "room_type_id": "...",
  "available": 0,
  "schema_version": "2026-06" }
```
- **Retry semantigi (kritik)**: `inventory_conflict` 409'u **kesin** bir satis-basarisizligidir; acente bunu **yeniden DENEMEZ** (retry envanteri geri getirmez). Bu, Karar 4'teki `idempotency_in_progress` 409'undan FARKLIDIR (o, kisa backoff ile retry edilir). Ayrim error_code ile yapilir, HTTP koduyla DEGIL. 503/429 ise **gecicidir** ve exponential backoff ile yeniden denenir. Bu ayrimlar sozlesmede dondu.
- Cok-geceli rezervasyonda ilk catisan gece `conflict_date` olarak doner; kismi-claim edilen geceler compensation ile serbest birakilir (mevcut conflict-resolve compensation deseni).

---

## Karar 6 — PMS -> Acente webhook / outbox + exponential backoff

- PMS, envanter/fiyat/restriksiyon degisikliginde acenteye **imzali webhook** firlatir (mevcut SXI outbox + dispatcher uzerinden; yeni event tipleri additive).
- **Hedef konfigurasyonu (donmus)**: ayri bir ayar tablosu YOK. Hedef, `agency_contracts` (Partner Sozlesmesi) kaydina eklenen tek bir **`webhook_url`** alanindan okunur. Sozlesme zaten `(tenant_id, agency_id)` muhurlu oldugu icin olay firlatilirken dogrudan bu kayda bakilir — per-acente global esneksizligi de per-tenant konfig coplugu de onlenir.
- **Idempotency**: her outbound olay `event_id` + `idempotency_key=tenant:event:entity:payload_hash` tasir; acente tarafinda tekrarlar dedup edilir.
- **Backoff stratejisi** (donmus): exponential + jitter.
  - Maks deneme: **8**.
  - Programlama (yaklasik): 0s, 30s, 2m, 8m, 30m, 2h, 6h, 24h (her adimda +/- %20 jitter).
  - 2xx -> basari. Acente'den 4xx (408/429 haric) -> kalici hata, **dead-letter** (DLQ) + alarm, retry durur. 5xx/timeout/429 -> retry.
  - 8. denemeden sonra basarisiz -> DLQ + operator gorunur alarm; sessiz drop YOK.
- **DLQ isletim sozlesmesi (donmus)** — "sessiz drop yok" garantisi ancak bunlarla tamamlanir:
  - **Retention**: DLQ kaydi en az **14 gun** saklanir (event_id + payload_hash + son hata + deneme sayisi; PII/secret govdesi sifrelenir veya referans tutulur).
  - **Replay**: super_admin'e ozel manuel replay ucu/komutu (idempotency_key korunur, cift-teslim acente tarafinda dedup edilir); replay basarisi DLQ kaydini cozer.
  - **Alarm esigi/SLO**: DLQ'ya dusen ilk olayda warning, esik (or. 5 dk'da >N veya tek acenteye art arda basarisizlik) asilirsa escalation; hedef: DLQ olaylari 24h icinde cozulur.
  - **Runbook**: operator proseduru `docs/REPLIT_OPS_CHEATSHEET.md`'ye implementasyon turunda eklenir.
- Webhook hedef URL'i SSRF/DNS-rebind korumali outbound (mevcut `integrations.xchange.safety.safe_request_async`) ile cagrilir; imzali URL/secret loglanmaz.

---

## Karar 7 — Sinir cozumleri: edge esleme + rate-limit

- **`agency_id` <-> `tenant_id` / `room_type_id` esleme (donmus)**: PMS **cekirdegine gomulmez**. Esleme `b2b_api` router'inin hemen arkasindaki **Provider/Adaptor (SXI kenari)** katmaninda cozulur. PMS iceriye yalnizca kendi `tenant_id` + `room_type_id` dunyasiyla bakar; disaridan gelen acente kimliklerini kanonik formata cevirme yuku butunuyle entegrasyon sinirinda biter (Zero Bloat — cekirdek her yeni acente icin haritalama tablosu tasimaz).
- **Rate-limit (donmus)**: IP-bazli rate-limit B2B'de YANLIS (NAT arkasindaki alt-acenteler ortak cikis IP'si paylasir; biri digerini bloklar). IP yalnizca mTLS/guvenlik kapisinda sinir kontrolu olarak kullanilir. Kova mantigi (Token Bucket, Redis) **strictly `key_id (acente) + tenant_id`** bileskesine baglanir — A acentesinin X oteline yuku, Y otelini veya B acentesini etkilemez. Sorgu (availability) ve yazma (create) **ayri kova/esik** tasir (yazma daha pahali).

---

## Hata modeli (ortak)

| HTTP | error_code (ornek) | Acente davranisi |
|---|---|---|
| 401 | unauthorized / invalid_signature / stale_timestamp | Duzelt, retry etme |
| 403 | forbidden / module_disabled | Retry etme |
| 409 | inventory_conflict / idempotency_in_progress / terminal_state | inventory_conflict + terminal_state: retry ETME; in_progress: kisa backoff |
| 422 | validation_error / unknown_field / mapping_error / idempotency_conflict | Govdeyi duzelt, retry etme |
| 429 | rate_limited | Retry-After ile backoff |
| 503 | not_configured / upstream_unavailable | Exponential backoff ile retry |

`not_configured` (eksik secret/connector) durumunda uc fail-closed 503 doner — sahte basari YOK.

---

## Kapsam disi / ertelenen

- Loyalty modulu (ayri is kolu, ertelendi).
- Acente uygulamasinin kendi ic mimarisi (kendi repo/container).
- OTA/HTNG XML adaptoru (yalnizca gercek OTA gerektiginde, provider kenarinda).
- GraphQL (yalnizca acente cok-degiskenli alan secimi gerektirirse degerlendirilir; varsayilan REST).
- Implementasyon (router/sema/test) — bu ADR sonrasi ayri is.

## Cozulen acik sorular

Ilk taslaktaki 3 acik soru karara baglandi:
1. `agency_id` <-> `tenant_id` esleme -> **Karar 7** (cekirdege gomulmez, SXI kenarinda cozulur).
2. Webhook hedef konfigurasyonu -> **Karar 6** (`agency_contracts.webhook_url`, ayri ayar tablosu yok).
3. Rate-limit kovalari -> **Karar 7** (`key_id + tenant_id` bileskesi, IP DEGIL; sorgu/yazma ayri kova).

Implementasyon turuna devreden somut esikler (deger ayari, kontrat alani): rate-limit sayisal esikleri, `idempotency_cache` TTL index alan adlari, `agency_contracts.webhook_url` sema migration'i.
