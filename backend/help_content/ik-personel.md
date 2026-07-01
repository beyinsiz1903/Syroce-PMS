# İK & Personel Yönetimi

Çalışan kayıtları, vardiya, mesai, izin, performans ve bordro takibi için modül.

## Modülün Mevcut Durumu

> **Not**: HR modülü aşamalı geliştirilmektedir. Bu sayfada **bugün hangi özelliklerin çalıştığı**, **hangilerinin gelişim aşamasında** olduğu açıkça belirtilmiştir.

### Çalışan Özellikler ✓

- **Mesai Takibi (Attendance)**: clock-in / clock-out, günlük & aylık özet
- **Personel Listesi**: `Yönetim > Personel Yönetimi` ekranı; ayrı sayfa olarak açılır
- **Bordro CSV Export**: aylık dönem için saat × ücret CSV indirme
- **Audit log**: tüm işlemler kayıtlı

### Gelişim Aşamasında ⏳

- **İzin yönetimi** (talep formu var, liste/onay akışı yok)
- **Performans değerlendirme** (görüntüleme var, değerlendirme formu yok)
- **İşe alım (Recruitment)** (ilan oluşturma var, başvuru takibi yok)
- **Tam bordro motoru** (SGK kesintileri, brüt→net, payslip PDF)

## Personel Ekleme

> **Önemli**: Personel ekleme **HR Suite ekranından değil**, ayrı `Yönetim > Personel Yönetimi` ekranından yapılır.

Yeni personel için zorunlu alanlar:

- Ad Soyad
- E-posta + telefon
- Departman (housekeeping, ön büro, finans, satış, yönetim)
- Pozisyon
- İşe başlama tarihi
- Çalışma türü (tam zamanlı, yarı zamanlı, dönemsel)
- Saatlik / aylık ücret

## Mesai Takibi

- Personel mobil uygulamadan veya kiosk tabletten **Giriş** / **Çıkış** kaydı atar
- Vardiya planı ile karşılaştırma yapılır; geç giriş veya erken çıkış uyarılır
- Aylık özet: toplam çalışılan saat, fazla mesai, devamsızlık

## Bordro Export

`HR > Payroll` ekranından dönem seçilip CSV indirilir:

- Personel × günlük saat × hesaplanan brüt
- Logo / Netsis / başka muhasebe yazılımına manuel aktarım için uygun

> **Önemli**: Üretilen CSV **gerçek bordro** değildir; SGK kesintisi, gelir vergisi, AGİ, damga vergisi **dahil değildir**. Resmi bordro üretimi için muhasebe yazılımınızı kullanın.

## Yetki ve Güvenlik

- Personel listesi yalnızca **HR / GM / Süper Admin** rollerine açık
- Bordro export'u ek **PII yetkisi** gerektirir
- Çalışanın özlük bilgileri KVKK kapsamında — erişim audit log'a yazılır

## Yol Haritası

Önümüzdeki sürümlerde planlanan:

- İzin akışı (talep → onay → bakiye düşme → SGK türleri)
- Performans değerlendirme formu (KPI tabanlı, 360°)
- Tam bordro motoru (SGK + GİB entegrasyonu)
- E-bordro / e-imza, payslip PDF, banka transfer dosyası
- Eğitim takibi, organizasyon şeması
