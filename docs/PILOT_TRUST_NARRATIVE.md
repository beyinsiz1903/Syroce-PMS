# Neden Syroce PMS pilot için hazır

> **Hedef kitle:** pilot otel karar vericileri, stratejik ortaklar,
> yatırımcılar.
> **Ton:** profesyonel, sakin, doğrulanabilir. Hype yok, abartı yok.
> **Kapsam tarihi:** 2026-05-24 — Full Operational Stress Suite GREEN
> baseline (commit `ee7573b3`).

---

## 1) Yönetici özeti

Syroce PMS, sade bir cümleyle: bir otelin günlük operasyonunu (PMS),
finansını, insan kaynaklarını, misafir deneyimini, kanal yönetimini,
B2B/API yüzeyini ve operasyonel hazırlığını **tek bir test paketinde**
uçtan uca doğrulayan bir Hospitality OS adayıdır.

2026-05-24 tarihli **Full Operational Stress Suite** çalışmasında,
sistemin 68 spec'lik geniş test paketi tek seferde **yeşil** döndü.
Önemli güvenlik ve operasyonel eşiklerin tamamı **sıfır kritik bulgu**
ile geçti:

| Eşik | Sonuç |
|---|---|
| Başarısız test | **0** |
| FAIL adım | **0** |
| Kritik bulgu (P0) | **0** |
| Yüksek öncelikli bulgu (P1) | **0** |
| Gerçek dış servis çağrısı (SMS / e-posta / OTA / ödeme) | **Yok** (`external_calls=[]`) |
| Pilot tenant verisinde değişim (`pilot_drift`) | **0** |
| Test sonrası temizlik | **İdempotent** (ikinci çalıştırma "0 silindi") |
| Bağımsız mimari değerlendirme | **PASS** |
| Final verdict | ✅ **GO** |

Bu, "yazılım çalışıyor" demekten daha fazlasını ifade ediyor: sistem,
gerçek bir otel verisine zarar vermeden, gerçek bir misafire mesaj
göndermeden, tenant'lar arasında veri sızdırmadan, kapsamlı bir
stres senaryosunu geçebiliyor.

> *GitHub Actions run numarası ve toplam süre bu belgeye sonradan
> backfill edilebilir; baseline'ın doğrulanabilirliği için commit SHA
> (`ee7573b3`) ve drill report referansı (bkz. § 9) yeterlidir.*

---

## 2) Test edilen yüzeyler

Stres paketinin kapsadığı ana ürün yüzeyleri:

- **PMS çekirdeği** — front desk, oda durumu, oda transferi.
- **Rezervasyon yaşam döngüsü** — check-in / check-out, gün devri,
  night audit, no-show.
- **Folio / kasiyer / muhasebe** — folio kalemleri, vardiya kasiyer,
  city ledger, gider kayıtları, banka & envanter, raporlar, döviz.
- **Housekeeping & operasyon** — toplu görev üretimi, fotoğraf upload,
  oda durumu güncelleme.
- **İK & bordro** — personel/organizasyon, mesai, izin, vardiya,
  bordro yaşam döngüsü, performans, self-service, offboarding,
  bordro PII export, RBAC PII denetimi.
- **Misafir-yönlü genel akışlar** — oda QR servis talebi, online
  check-in submit, KVKK rıza, misafir mesajlaşma.
- **Channel manager** — Exely & HotelRunner webhook'ları, outbox kuyruğu,
  conflict queue, ARI push, stop-sale, no-show OTA parity.
- **Raporlar & export** — PDF/CSV/XLSX export, indirme imzaları,
  tenant-bağımlı artifact.
- **GraphQL & B2B API** — tenant izolasyonu, API anahtarı kapsamı.
- **AI dry-run** — upsell, dinamik fiyatlama, no-show risk tahmini
  (gerçek model çağrısı yapılmadan kontrat doğrulaması).
- **Bildirim batch dry-run** — push/email batch zarf doğrulaması.
- **Cross-tenant güvenlik** — guests / folios / charges / messages /
  hr_staff için ayrı izolasyon probları.
- **Auth token yaşam döngüsü** *(F8U yeni)* — login, refresh rotation,
  logout, tampered/garbage token reddi.
- **WebSocket tenant izolasyonu** *(F8V yeni)* — `/api/enterprise/ws/live`
  kanalında pilot verisi sızıntısı yok.
- **Export artifact IDOR** *(F8R yeni)* — 9 export endpoint'i için
  cross-tenant indirme reddi.
- **Dosya / doküman upload güvenliği** *(F8S yeni)* — HR doküman
  ve housekeeping fotoğraf için boyut, MIME, polyglot, path-traversal,
  cross-tenant indirme.
- **Operasyonel hazırlık smoke** *(F8W yeni)* — health endpoint'leri,
  yedek yaşı, CM kuyruk derinliği, cache warmup, rollback metadata.

---

## 3) Gate'ler ne anlama geliyor?

Test sonuçlarındaki sayılar teknik terimler içeriyor; her birinin pilot
müşteri için somut karşılığı şu:

- **`failedTests = 0`** — paketin bütün senaryoları çalıştı; "kırmızı"
  test kalmadı.
- **`P0 = 0`** — sistemin bütünlüğünü veya tenant izolasyonunu bozan
  kritik bir bulgu tespit edilmedi.
- **`P1 = 0`** — yüksek öncelikli sözleşme ihlali (örneğin sanitize
  edilmeden saklanan veri, eşik aşımı) yok.
- **`external_calls = []`** — testler boyunca tek bir gerçek SMS,
  e-posta, ödeme veya OTA API çağrısı yapılmadı. Dış dünya etkilenmedi.
- **`pilot_drift = 0`** — testler pilot otelin verilerine dokunmadı.
  Testten önceki ve sonraki rezervasyon sayısı aynı.
- **Cleanup idempotent** — testlerin oluşturduğu veri silindi;
  ikinci silme denemesi "0 kayıt" gördü, yani sistemde yetim veri
  bırakmadı.
- **Verdict GO** — bağımsız mimari değerlendirme (architect) + invariant
  kapıların tamamı geçti; paket yeşil onaya hazır.

---

## 4) Pilot otel için ne anlama geliyor?

Pilot operasyonun risklerini azaltan somut başlıklar:

1. **Tenant verisi karışmıyor.** GraphQL, B2B API, WebSocket, export,
   upload yüzeylerinde tenant izolasyonu ayrı ayrı probe edildi —
   bir otelin verisi başka bir otele sızmıyor.
2. **Pilot otel test sırasında etkilenmiyor.** Bütün stres senaryoları
   "stress" tenant'ında çalışıyor; pilot otel için tek yapılan
   *read-only* sayım kontrolü. `pilot_drift = 0` bunun kanıtı.
3. **Gerçek misafire mesaj gitmiyor.** SMS, e-posta, push, ödeme,
   OTA push çağrılarının tamamı dry-run modunda; testten sonra `external_calls = []`
   yeniden doğrulanıyor.
4. **Misafir ve personel PII'si korunuyor.** KVKK consent akışı, ID
   foto saklama, bordro PII export, RBAC ile PII erişimi ayrı stress
   spec'leri ile doğrulandı.
5. **Geri alınamaz aksiyonlar tetiklenmiyor.** Bordro finalize, personel
   offboarding, no-show inventory release, folio kapama gibi terminal
   state aksiyonlar stres testlerinde tetiklenmiyor; bu işlemler ayrı
   guard'larla korunuyor.
6. **Public yüzeyler aktif olarak test ediliyor.** Online check-in,
   doküman upload, QR/token akışları gibi internet'e açık yüzeyler için
   boyut, MIME, polyglot, path-traversal, cross-tenant indirme gibi
   saldırı vektörleri tek tek probe edildi.
7. **Operasyonel hazırlık sinyali kayıt altında.** Health endpoint'leri,
   yedek yaşı, channel manager kuyruk derinliği, cache durumu nightly
   stress run'ın bir parçası — sapma anında görünür hale geliyor.

---

## 5) Klasik PMS / bulut-PMS karşısında pozisyon

Pazarın bilinen PMS çözümleri (klasik desktop PMS, bulut-PMS) genelde
ön büro operasyonunu çok iyi yapar. Syroce'nin farklılaşması "klasik
PMS'i daha iyi yapmak" değil; aynı çatı altında **Hospitality OS**
katmanını sunmak:

| Katman | Klasik PMS odağı | Syroce kapsamı |
|---|---|---|
| Ön büro / rezervasyon / housekeeping | ✅ | ✅ |
| Folio / kasiyer / muhasebe | Çoğunlukla ✅ | ✅ |
| İK / bordro / vardiya / izin | Genelde dışarıda | ✅ entegre |
| Misafir deneyimi (QR, online check-in, mesajlaşma, KVKK) | Add-on | ✅ entegre |
| Channel manager (OTA outbox, ARI push, conflict queue) | Ayrı entegratör | ✅ entegre |
| B2B / GraphQL API yüzeyi | Sınırlı | ✅ entegre |
| AI öneri (upsell / fiyat / no-show / NPS) | Add-on / yok | ✅ dry-run kontratı doğrulanmış |
| Tenant-ölçeğinde güvenlik baseline'ı | Müşteriye bırakılır | ✅ stress suite + ADR doctrine |
| Operasyonel hazırlık ölçümleri (health/backup/outbox/rollback) | Genellikle DevOps tarafı | ✅ ürün içi smoke |

Yani Syroce, "klasik PMS + integrasyon paketi" yerine **tek paket
olarak şekillenen bir işletim sistemi**. Burada rekabetin sloganlarına
girmiyoruz; sayısal olarak görünen şey: yukarıdaki katmanların hepsinin
**aynı stres test koşusunda** birlikte geçmiş olması.

---

## 6) Şeffaf sınırlar ve yol haritası

Pilot operasyonun beklenti yönetimi için, henüz derinleştirilmemiş
alanları dürüstçe paylaşıyoruz:

- **MICE execution katmanı** — BEO/event yürütme akışları kapsama
  alındı; derin operasyonel senaryolar (servis kaynak çakışması,
  banket revizyon hattı) genişletilecek.
- **Warehouse transfer** — F&B envanter hareketleri stres altında;
  depo-ler-arası transfer ve kısmi teslim senaryoları F8F v2 backlog'unda.
- **QR secret rotation derinliği** — temel tamper / cross-tenant
  korunmuş; eski token grace, revoked TTL, audit emit derinliği
  endpoint expose'una bağlı olarak F8K v2 backlog'unda.
- **Derin organizasyon şeması traversal'ı** — temel İK kapsamı geçti;
  çok katmanlı org chart, vekâlet, manager-of-manager izolasyonu
  ileride genişletilecek.
- **CI run numarası / süre kaydı** — baseline'ın doğrulanabilirliği
  commit SHA ve drill report ile sağlanıyor; GitHub Actions run URL'i
  paylaşıldığında bu belgeye backfill edilecek.

Bu liste "yapılmadı" değil "daha da derinleştirilecek" anlamına gelir;
bütün başlıklar mevcut kod tabanında en az bir yüzeyle stres testinden
geçmiş durumda.

---

## 7) Müşteri-yönlü özet cümleler

**Kısa satış cümlesi:**
> Syroce, otelin ön bürosundan İK'sına, kanal yönetiminden misafir
> deneyimine kadar tek paket yürüyen, güvenlik baseline'ı bağımsız
> doğrulanmış bir Hospitality OS'tir.

**Pilot otel cümlesi:**
> Pilot otelimizin verisine dokunmadan, gerçek misafirine mesaj
> göndermeden ve sistemleri kapatmadan, Syroce'nin 68 testlik geniş
> operasyonel stres paketi sıfır kritik bulgu ile yeşil geçti.
> Pilot süresince sistemden beklediğiniz güvenlik ve süreklilik kaydı
> teknik olarak doğrulanmış durumda.

**Yatırımcı / stratejik ortak cümlesi:**
> Syroce PMS; PMS çekirdek, finans, İK, channel manager, guest/public,
> GraphQL/B2B, AI dry-run, cross-tenant güvenlik, auth token yaşam
> döngüsü, WebSocket tenant izolasyonu, file upload security, export
> artifact IDOR ve ops readiness dahil geniş üretim yüzeylerinde
> Full Operational Stress Suite'i tek seferde yeşil geçmiştir
> (2026-05-24, commit `ee7573b3`, 68 spec, failedTests=0, P0=P1=0,
> external_calls=[], pilot_drift=0, cleanup idempotent, architect verdict
> PASS).

---

## 8) Doğrulanabilirlik

Bu belge teknik kayıtla birebir hizalı. Doğrulamak için aşağıdaki
dahili referanslara bakınız:

- **Roadmap baseline tablosu:** [`docs/STRESS_TEST_ROADMAP.md`](./STRESS_TEST_ROADMAP.md) §
  *Latest verified baseline (2026-05-24) ✅ GREEN — F8R–F8W included*
- **Drill report (run künyesi + gate'ler + iterasyon hikâyesi):**
  [`docs/drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md`](./drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md)
- **ADR (kapsam + doctrine + verified status):**
  [`docs/adr/2026-05-f8r-f8w-hardening.md`](./adr/2026-05-f8r-f8w-hardening.md)
- **Önceki baseline (referans, 2026-05-23 / 413 test / commit `a035568c`):**
  [`docs/drill_reports/20260523_stress_full_stress_suite_GREEN.md`](./drill_reports/20260523_stress_full_stress_suite_GREEN.md)
- **Operatör entry (canlı / pilot süresinde olay yönetimi):**
  [`docs/REPLIT_OPS_CHEATSHEET.md`](./REPLIT_OPS_CHEATSHEET.md)

---

*Son güncelleme: 2026-05-24. Bu belge, baseline güncellendikçe
revize edilir.*
