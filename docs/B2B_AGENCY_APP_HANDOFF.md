# Syroce PMS — B2B Acente Otomasyon Uygulamasi Devir Promptu (T005)

Bu dosya, AYRI bir Replit projesinde calisacak "acente otomasyon uygulamasi"
agent'ina verilecek devir (handoff) promptudur. Syroce PMS, bu uygulama icin
yetkili (authoritative) iki-yonlu B2B backend'idir: REST uzerinden rezervasyon/
musaitlik/fiyat (Kanal A) ve Redis Streams uzerinden gercek zamanli ARI fanout
(Kanal B — fiyat/kontenjan/stop-sale).

Bu kontrat KILITLIDIR. Acente uygulamasi bu sozlesmeye gore yazilmalidir; PMS
tarafi additive ve geriye-uyumlu kalir.

---

## 1. Mimari ozet

- **Kanal A (REST, istek/yanit):** acente -> PMS. Musaitlik sorgula, fiyat al,
  rezervasyon olustur/iptal et, folio oku. Base path: `/api/b2b`.
- **Kanal B (Redis Streams, push):** PMS -> acente. PMS tarafindaki ARI degisimleri
  (availability / rate / restriction-stop-sale) acente-basina ayri bir stream'e
  yazilir. Acente kendi stream'ini consumer-group ile okur, koptugunda son ID'den
  devam eder.

Iki kanal birbirinden bagimsizdir. REST 4xx/5xx kurallari ile Streams teslim
semantigi ayri ayri ele alinmalidir.

---

## 2. Guvenlik modeli (zorunlu)

1. **API key (uygulama seviyesi, ENFORCED):** her REST cagrisi `X-API-Key`
   basligi ile gelir. Anahtar `sysdb.agency_api_keys` icinde SHA-256 hash olarak
   tutulur; gecersiz/pasif anahtar 401, pasif acente 403 doner. Anahtar degeri
   ASLA log'a/sohbete yazilmaz.
2. **Scope (fail-closed, ENFORCED):** anahtara `scopes: list[str]` atanmissa SADECE
   o alt-router'lara erisir; kapsam disi alt-router 403 doner. `scopes` None/eksik
   ise eski tek-anahtar modeli (kisitsiz). Gecerli scope'lar:
   `booking_engine, folio, groups, guest_journey, guests, housekeeping, identity,
   kbs, lost_found, services, wake_up, webhooks`.
3. **IP allowlist + mTLS (ingress/deployment seviyesi):** DigitalOcean App Platform
   ingress'inde uygulanir; kaynak IP allowlist'te olmali ve istemci mTLS sertifikasi
   sunmalidir. BUNLAR UYGULAMA KODUNDA DEGIL, ingress'te zorlanir — acente uygulamasi
   sabit cikis IP'si + istemci sertifikasi ile cagri yapmalidir.
4. **Idempotency-Key (istemci tarafinda ZORUNLU):** her POST `/reservations` cagrisinda
   istemci uretimli bir UUID `Idempotency-Key` basligi gonderilmelidir (asagiya bkz).
5. **Redis ASLA public degildir:** acente, Kanal B stream'lerini yalnizca ozel ag
   (private networking / VPC) uzerinden okur; Redis internete acilmaz.

---

## 3. Kanal A — REST kontrati (base: `/api/b2b`)

Tum cagrilarda baslik: `X-API-Key: <agency_key>`. Tarihler `YYYY-MM-DD`.

### 3.1 GET `/availability`
Query: `check_in` (zorunlu), `check_out` (zorunlu), `room_type` (ops).
```json
{
  "check_in": "2026-07-01",
  "check_out": "2026-07-03",
  "room_types": [
    {"room_type": "Deluxe", "capacity": 2, "base_price": 1200,
     "amenities": [], "bed_type": "", "total_rooms": 10, "available_rooms": 4}
  ]
}
```

### 3.2 GET `/rates`
Query: `start_date` (zorunlu), `end_date` (zorunlu), `room_type` (ops).
Acenteye ozel fiyat takvimini (`agency_rate_calendar`) doner.

### 3.3 POST `/reservations`  (Idempotency-Key ZORUNLU)
Baslik: `Idempotency-Key: <uuid>`. Govde:
```json
{
  "room_type": "Deluxe",
  "check_in": "2026-07-01",
  "check_out": "2026-07-03",
  "guest_name": "Ad Soyad",
  "guest_email": "",
  "guest_phone": "",
  "adults": 2,
  "children": 0,
  "special_requests": "",
  "total_amount": 0
}
```
Basari (200):
```json
{
  "ok": true,
  "reservation": {
    "id": "<uuid>", "confirmation_code": "B2B-XXXXXXXX", "status": "confirmed",
    "room_type": "Deluxe", "room_number": "101",
    "check_in": "2026-07-01", "check_out": "2026-07-03",
    "guest_name": "Ad Soyad", "total_amount": 2400,
    "commission_rate": 12.5, "commission_amount": 300.0,
    "created_at": "..."
  },
  "message": "Rezervasyon olusturuldu: B2B-XXXXXXXX"
}
```

**Idempotency davranisi (kritik):**
- Ayni `Idempotency-Key` + ayni govde tekrar gonderilirse: ikinci rezervasyon
  OLUSTURULMAZ; orijinal yanit (basari ya da is-kurali hatasi) AYNEN doner (replay).
- Ayni anahtar + FARKLI govde: `409` (anahtar baska istekle kullanildi).
- Ayni anahtar su an islenirken (in-flight): `429` + `Retry-After: 2`. Istemci
  Retry-After kadar bekleyip ayni anahtarla tekrar denemeli.
- Is-kurali 4xx kalicidir (ayni anahtarla yeniden deneme ayni hatayi alir);
  beklenmeyen 5xx tekrar denenebilir.
- **Baslik gonderilmezse** eski (idempotent olmayan) davranis korunur — ama acente
  uygulamasi her zaman baslik gondermelidir.

### 3.4 GET `/reservations`
Query: `status`, `check_in_from`, `check_in_to`, `limit` (<=500). Sadece cagiran
acentenin rezervasyonlari.

### 3.5 GET `/reservations/{reservation_id}` · PUT `/reservations/{reservation_id}/cancel`
Tekil detay / iptal. Iptal kontenjan + kredi sayaclarini geri birakmaz —
sayaclar rezervasyon yasam dongusune gore PMS tarafinda yonetilir (bkz. is kurallari).

### 3.6 Diger alt-router'lar (scope'a tabi)
`/folio/{booking_id}` (+`/charge`, `/invoice`), `/guests/*`, `/groups/*`,
`/housekeeping/*`, `/kbs/*`, `/identity/*`, `/lost-found`, `/wake-up-calls`,
`/guest-journey/*`, `/concierge/*`, `/spa/*`, `/webhooks*`. Tam liste PMS
OpenAPI'sinde (`/api/openapi.json`). Her biri ilgili scope ister.

### 3.7 Webhook'lar (PMS -> acente, push alternatifi)
POST `/webhooks` ile `{url, events[], secret?}` kaydedilir; ornegin
`reservation.created` olayinda PMS kayitli URL'e imzali cagri yapar (retry + DLQ).
Streams (Kanal B) ARI icin, webhook ise olay-bazli is bildirimleri icindir.

---

## 4. Kanal B — Redis Streams consumer kontrati

### 4.1 Stream anahtari (acente-basina, KILITLI)
```
b2b:tenant:{tenant_id}:agency:{agency_id}:ari:v1
```
- Acente YALNIZCA kendi `{tenant_id, agency_id}` stream'ini okur. Tenant-genelinde
  TEK stream YOKTUR (acenteler-arasi sizinti engeli).
- MAXLEN ~100.000 (yaklasik trim). Eski mesajlar otomatik budanir.

### 4.2 Mesaj alanlari (`schema = "ari.v1"`)
XADD alanlari (hepsi string; `payload` JSON string'tir):
```
schema           = "ari.v1"
event_id         = <uuid>
tenant_id        = <tenant>
agency_id        = <agency>           # bu stream'in sahibi
property_id      = <property>
event_type       = availability | rate | restriction
room_type_code   = <oda tipi kodu>
rate_plan_code   = <plan> | ""
date_from        = YYYY-MM-DD
date_to          = YYYY-MM-DD
payload          = <JSON string>      # ornegin {"price":1200,"currency":"TRY","stop_sale":false}
source_service   = pricing | frontdesk | night_audit | manual | ...
correlation_id   = <uuid> | ""
created_at       = ISO-8601
```

### 4.3 Tuketim deseni (consumer group)
```
# Grup yoksa olustur (stream yoksa MKSTREAM ile):
XGROUP CREATE b2b:tenant:{t}:agency:{a}:ari:v1 agency-consumers $ MKSTREAM

# Oku (yeni mesajlar):
XREADGROUP GROUP agency-consumers <consumer_name> COUNT 100 BLOCK 5000 \
  STREAMS b2b:tenant:{t}:agency:{a}:ari:v1 >

# Isledikten sonra ACK:
XACK b2b:tenant:{t}:agency:{a}:ari:v1 agency-consumers <message_id>

# Yeniden baglanmada bekleyenleri (pending) topla:
XREADGROUP GROUP agency-consumers <consumer_name> COUNT 100 \
  STREAMS b2b:tenant:{t}:agency:{a}:ari:v1 0
```
- Consumer group sayesinde acente koptuktan sonra **son ACK'ledigi ID'den devam eder**;
  kayip yoktur (pub/sub aksine).
- **At-least-once + idempotent:** PMS, Redis kisa sureli dususte mesaji Mongo outbox'a
  park edip sonraki saglikli flush'ta yeniden yayar. Bu nedenle ayni `event_id`
  birden fazla kez gelebilir. ARI dogasi geregi last-write-wins'tir; tuketici
  (room_type_code + date_from..date_to) anahtariyla idempotent uygulamali, `created_at`
  ile sirayi cozmelidir.
- ACK edilmeyen mesajlar pending'de kalir; periyodik `XAUTOCLAIM`/`XPENDING` ile
  yeniden islenmelidir.

---

## 5. Hata semantigi (REST)

| Kod | Anlam | Istemci davranisi |
|----|-------|-------------------|
| 401 | API key eksik/gecersiz/pasif | Anahtari kontrol et; tekrar deneme |
| 403 | Acente pasif veya scope yetersiz | Yetki/scope sorunu; tekrar deneme |
| 402 | Kredi limiti asildi (credit guard) | Odeme/limit; rezervasyon reddedildi |
| 409 | Idempotency-Key farkli govde ile / kontenjan (allotment) dolu / oda cakismasi | Govdeyi/anahtari duzelt; allotment icin baska tarih/oda |
| 422 | Sozlesme allowed_room_types disi oda tipi / gecersiz govde | Istek alanlarini duzelt |
| 429 | Ayni Idempotency-Key isleniyor | `Retry-After` kadar bekle, ayni anahtarla tekrar dene |
| 5xx | Gecici sunucu hatasi | Ayni Idempotency-Key ile guvenle tekrar dene |

---

## 6. Is kurallari (PMS tarafinda zorlanan — acente bilmek zorunda)

- **Komisyon:** onayli + tarih-gecerli sozlesme (`agency_contracts`) varsa komisyon
  oradan; yoksa eski `agencies.commission_rate` (varsayilan 0). Yanitfaki
  `commission_rate`/`commission_amount` bilgilendirme amaclidir.
- **Allotment (kontenjan) — opt-in, HARD:** sozlesmede (room_type, donem) icin
  `rooms_allocated` tanimliysa kontenjan ASILAMAZ; dolu ise `409`. Tanimsizsa kontenjan
  sinirsizdir. Kontenjan klasik OTA mantigiyla ODA-GECE bazinda tuketilir
  (`rooms_allocated`/`rooms_used` bir oda-gece kotasidir): bir rezervasyon `oda * gece`
  birim duser, ornegin 3 gecelik tek-oda rezervasyon kontenjandan 3 birim tuketir.
- **Kredi — opt-in, HARD:** acentede `credit_limit` tanimliysa `current_debt + tutar
  <= credit_limit` saglanmazsa `402`. Tanimsizsa kredi sinirsizdir. Sayaclar yaris
  guvenli (Mongo atomik) artirilir; rezervasyon olusturulamazsa saga ile geri alinir.
- **Sozlesme oda tipi kisiti:** `allowed_room_types` tanimliysa disindaki oda tipi
  `422` ile reddedilir (misafir olusturulmadan once).

---

## 7. Acente uygulamasi agent'ina verilecek GOREV PROMPTU

> Asagidaki blok, yeni Replit projesinde acente otomasyon uygulamasini kuracak
> agent'a yapistirilacak talimattir.

```
Syroce PMS'in yetkili B2B backend oldugu, AYRI bir acente otomasyon uygulamasi kur.
Bu uygulama PMS'e bir kanal yoneticisi (channel manager) gibi baglanir.

KIMLIK & GUVENLIK
- Tum REST cagrilari `X-API-Key: <PMS_AGENCY_KEY>` basligi ile yapilir (gizli; ortam
  degiskeni/secret olarak tut, asla log'lama).
- Cikis IP'sini sabitle (PMS ingress'inde IP allowlist var) ve istemci mTLS sertifikasi
  sun. Bunlar PMS ingress'inde zorunlu.
- POST rezervasyonda her zaman istemci uretimli `Idempotency-Key: <uuid>` gonder.

KANAL A (REST, base `/api/b2b`)
- Musaitlik: GET /availability?check_in&check_out[&room_type]
- Fiyat: GET /rates?start_date&end_date[&room_type]
- Rezervasyon olustur: POST /reservations (Idempotency-Key zorunlu) — govde:
  {room_type, check_in, check_out, guest_name, guest_email?, guest_phone?, adults,
   children, special_requests?, total_amount?}
- Liste/detay/iptal: GET /reservations, GET /reservations/{id},
  PUT /reservations/{id}/cancel
- Hata kodlarini isle: 401/403 (yetki, tekrar deneme yok), 402 (kredi),
  409 (idempotency-farkli-govde / allotment dolu / oda cakismasi), 422 (gecersiz/oda
  tipi kisiti), 429 (in-flight: Retry-After bekle + ayni anahtarla tekrar), 5xx
  (ayni Idempotency-Key ile tekrar dene).

KANAL B (Redis Streams, gercek zamanli ARI — PMS'ten push)
- SADECE kendi stream'ini oku: b2b:tenant:{TENANT_ID}:agency:{AGENCY_ID}:ari:v1
  (Redis'e yalnizca ozel ag uzerinden eris; public degil).
- Consumer group ile tuket: XGROUP CREATE ... MKSTREAM; XREADGROUP ... BLOCK; isle;
  XACK. Yeniden baglanmada pending'i (ID 0 ile) ve XAUTOCLAIM ile topla. Boylece
  koptugunda son ACK'ten devam edersin.
- Mesaj alanlari schema="ari.v1": event_type (availability|rate|restriction),
  room_type_code, rate_plan_code, date_from, date_to, payload (JSON), created_at, ...
- AT-LEAST-ONCE: ayni event_id birden cok gelebilir. (room_type_code, date_from..
  date_to) anahtariyla idempotent uygula, created_at ile sirala (last-write-wins).
  Yerel musaitlik/fiyat/stop-sale tablonu bu olaylarla guncelle.

GENEL
- PMS tarafini yetkili kabul et; cakismada PMS kazanir. Tum yazma yollarinda
  idempotent ol. Hicbir gizli anahtari log'lama. Tum hatalari fail-closed isle.
```

---

## 8. Notlar (PMS tarafi gercekleri)

- Idempotency, partner sozlesme katmani, hard allotment+kredi guard ve per-agency
  Streams fanout PMS'te uygulanmistir (additive, pilot_drift=0, fail-closed).
- Streams fanout best-effort'tur: Redis dususte olaylar `sysdb.b2b_stream_outbox`'a
  park edilir ve sonraki saglikli ARI flush'inda yeniden yayinlanir (en-az-bir-kez).
- Bu kontrat kilitlidir; degisiklik gerekirse stream schema surumu (`ari.v1` ->
  `ari.v2`) ve yeni REST alanlari additive olarak eklenir.
```
