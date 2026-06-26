# ADR — Odeme Gecidi Soyutlamasi ve Kart Kasasi

**Status:** Accepted (2026-06-26)
**Kapsam:** Cekirdek port/DTO + tenant fail-closed secim + kart kasasi token
soyutlamasi. Somut Iyzico adaptoru (Task #312) ve otonom tahsilat worker'i
(Task #313) bu sozlesmeyi uygular; bu ADR onlarin temel kontratidir.

## Baglam

PMS, OTA sanal kartlarini (Booking/Expedia VCC) ve no-show cezalarini otonom
tahsil edebilmeli. Bugun Iyzico yalnizca checkout-form sarmalayicisi olarak var
(`core/iyzico.py`); charge/refund/void/3DS ve saglayici soyutlamasi yok. Kart
kasasi (`vcc_cards`, AES-256-GCM, 3-view reveal) mevcut ve PCI yuzeyi olarak
test ediliyor (`docs/adr/2026-05-f8ae-vcc-pci-compliance.md`).

Cekirdek finans/folio kodunun hicbir odeme kurulusuna (PSP) dogrudan baglanmamasi
gerekiyor: bugun Iyzico, yarin Stripe/Param secilse bile cekirdek mantik bundan
habersiz olmali (Interface-First, Zero Bloat).

## Karar

### 1. Port/Adapter modeli
`backend/core/payments/` altinda saglayici-bagimsiz bir port:
- `PaymentProvider` (ABC): `authorize / capture / charge / refund / void` +
  `name`, `capabilities`, `is_configured`. Islem metodlari guvenli-varsayilan
  olarak `UnsupportedOperation` atar; adaptor yalnizca destekledigi islemleri
  override eder ve `ProviderCapabilities` bayraklarini buna gore bildirir.

### 2. Kanonik DTO sozlesmesi
- `PaymentRequest`: `operation`, `tenant_id`, `currency` (ISO 4217, zorunlu),
  `idempotency_key` (zorunlu), `amount_minor` (**kurus-tam integer**, float YOK;
  VOID disinda zorunlu/pozitif), `vault_card_ref` (CHARGE/AUTHORIZE icin zorunlu),
  `reference` (CAPTURE/REFUND/VOID icin zorunlu), `booking_id`, `descriptor`,
  `three_ds_return_url`, `metadata`. DTO `__post_init__` ile fail-closed dogrular.
- `PaymentResult`: `status` (succeeded/pending/requires_action/failed), maskeli
  `masked_card`, `provider_ref`, `requires_action_url` (3DS), hata alanlari. Ham
  PAN/CVV yapisal olarak tutulamaz.

### 3. Idempotency + atomiklik doktrini (kritik)
PSP cagrisi **harici I/O**'dur; Mongo transaction'ina **GIREMEZ** (uzun suren
ag cagrisi tx tutamaz, replica-set tx zaman asimi). Bu yuzden:

```
intent(pending) kaydet  ->  PSP cagrisi  ->  sonucu atomik kaydet (idempotent)
```

- Tahsilat oncesi `pending` intent yazilir (idempotency_key tekil).
- PSP cagrisi disarida yapilir.
- Sonuc (succeeded/failed) atomik tek update ile yazilir; ayni idempotency_key
  ikinci kez gelirse onceki sonuc dondurulur (replay guvenli).
- Crash reconcile: `pending` kalmis intent'ler PSP'den sorgulanip kesinlestirilir
  (Task #313 worker'da). Sahte-yesil/optimistik tamamlama YASAK.

### 4. Tenant bazli fail-closed secim
Aktif saglayici `tenant_settings.active_payment_provider`'dan okunur. Bos /
gecersiz / kayitsiz / `is_configured()=False` (env/sir eksik) -> mevcut
`not_configured` kalibiyla tutarli **503**. Sessiz fallback YOK.

### 5. Kart kasasi token soyutlamasi
- Uygulama kodu yalnizca opak `vault_card_ref` tasir; ham PAN dolasmaz.
- `resolve_card_material` AES-256-GCM cozumlemeyi **yalnizca adapter sinirinda**
  yapar; `CardMaterial` repr/str maskelidir ve `clear()` ile omru minimize edilir.
- PAN/CVV **ASLA** log/exception/trace/DTO'ya yazilmaz.

### 6. Webhook guvenligi (adaptor sorumlulugu — Task #312)
Saglayici callback'leri HMAC imza dogrulamasi + SSRF korumasi (DNS-rebind safe,
IP allowlist) ile karsilanir; mevcut outbound HTTP guvenlik kaliplariyla tutarli.
Spoof callback tenant/booking kimligini belirleyemez — kimlik sunucu tarafindan
dogrulanir.

### 7. PCI kapsam daraltma + CVV politikasi
- PAN yalnizca kasada (AES-256-GCM) ve yalnizca adapter sinirinda plaintext.
- **CVV (PCI-DSS Req 3.2):** yetkilendirme sonrasi CVV saklanmaz. Mevcut kasa
  semasi `cvv_enc` tasiyabiliyor; bu, OTA VCC tek-cekim senaryosu disinda kalici
  saklama icin kullanilmamali. Politika: charge sonrasi CVV temizlenir; kalici
  CVV saklama ihtiyaci ayrica QSA onayina baglanir. (Uygulama Task #312/#313.)

## Sonuclar
- Cekirdek kod PSP'den tamamen soyutlanir; saglayici degisimi cekirdege dokunmaz.
- Para hareketleri kurus-tam ve idempotent; PSP cagrisi tx disinda kalir.
- PAN/CVV sizinti yuzeyi adapter sinirina hapsedilir.

## Kapsam disi (bu ADR)
- Gercek Iyzico/Stripe/Param tahsilat cagrilari (Task #312).
- Otonom tahsilat worker'i + crash reconcile uygulamasi (Task #313).
- Misafire donuk odeme sayfasi / taksit akislari.
