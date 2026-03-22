# Syroce PMS — Onboarding Playbook

## Genel Bakis

Bu belge, yeni bir otelin Syroce PMS platformuna basariyla entegre edilmesi icin gerekli adimlari, sorumlulari ve zaman cizelgesini tanimlar.

---

## Onboarding Sureci (Tipik: 5-10 is gunu)

### Gun 1-2: Hesap Kurulumu

| Adim | Sorumlu | Detay |
|------|---------|-------|
| Tenant olustur | Super Admin | AdminTenants > Yeni Otel Ekle |
| Plan sec | Super Admin | basic / professional / enterprise |
| Admin kullanici olustur | Super Admin | Otel yoneticisi icin email + sifre |
| Otel bilgilerini gir | Otel Admin | Adres, telefon, toplam oda sayisi |
| Logo ve marka ayarlari | Otel Admin | Settings > Otel Bilgileri |

### Gun 2-3: Oda ve Fiyat Konfigurasyonu

| Adim | Sorumlu | Detay |
|------|---------|-------|
| Oda tipleri tanimla | Otel Admin | Standard, Deluxe, Suite, vb. |
| Odalari olustur | Otel Admin | Her kat icin oda numaralari |
| Baz fiyatlari gir | Otel Admin | Oda tipi basina gunluk fiyat |
| Sezon fiyatlari | Otel Admin | Yuksek/dusuk sezon ayarlari |

### Gun 3-4: Ekip ve Roller

| Adim | Sorumlu | Detay |
|------|---------|-------|
| Resepsiyon kullanicilari | Otel Admin | front_desk rolu |
| Kat hizmetleri | Otel Admin | housekeeping rolu |
| Muhasebe | Otel Admin | manager rolu |
| Rol yetkileri kontrolu | Super Admin | RBAC dogrulamasi |

### Gun 4-5: Operasyonel Hazirlilk

| Adim | Sorumlu | Detay |
|------|---------|-------|
| Test rezervasyonu | Resepsiyon | Manuel rezervasyon olustur |
| Test check-in/out | Resepsiyon | Walk-in misafir akisi |
| Fatura testi | Muhasebe | Fatura olustur ve yazdir |
| Kat hizmetleri testi | Kat Hizmetleri | Oda temizlik akisi |

### Gun 5-7: Kanal Entegrasyonu (Professional+)

| Adim | Sorumlu | Detay |
|------|---------|-------|
| OTA credentials | Otel Admin | Booking.com, Expedia API anahtarlari |
| Kanal baglantisi | Super Admin | Provider config kurulumu |
| Oda-kanal eslesme | Otel Admin | Room mapping dogrulamasi |
| Sync testi | Super Admin | ARI push + reservation pull |

### Gun 7-10: Go-Live

| Adim | Sorumlu | Detay |
|------|---------|-------|
| Gece kapanisi testi | Otel Admin | Night audit dry-run |
| Personel egitimi | Egitim Ekibi | 2 saatlik hands-on egitim |
| Go-live onay | Super Admin | Kontrol listesi tamam |
| Canli izleme (3 gun) | Destek Ekibi | Hata/uyari takibi |

---

## Basari Kriterleri (Go-Live Onay)

- [ ] Tum odalar tanimlandi
- [ ] Fiyatlar girildi
- [ ] En az 2 kullanici (admin + resepsiyon) olusturuldu
- [ ] Test rezervasyonu basarili
- [ ] Test check-in/out basarili
- [ ] Fatura olusturulabiliyor
- [ ] Kanal sync calisiyor (Professional+ plan)
- [ ] Gece kapanisi tamamlanabiliyor
- [ ] Personel egitimi verildi

---

## Destek Eskalasyon Matrisi

| Seviye | Kanal | SLA |
|--------|-------|-----|
| L1 | Email | 4 saat (is saatleri) |
| L2 | Telefon | 2 saat |
| L3 | Dedicated | 1 saat (Enterprise) |

---

## Pilot KPI Metrikleri

Onboarding tamamlandiktan sonra ilk 30 gun icinde izlenmesi gereken metrikler:

| KPI | Hedef | Olcum |
|-----|-------|-------|
| Gunluk aktif kullanici | >= 3 | Login sayisi |
| Rezervasyon/gun | >= 2 | Yeni rezervasyonlar |
| Check-in suresi | < 3 dk | Ort. check-in suresi |
| Hata orani | < 1% | API error rate |
| Kanal sync basari | > 99% | Basarili sync orani |
| NPS | > 7 | Kullanici memnuniyeti |

---

## Referans Musteri Sablonu

### [Otel Adi] — Pilot Sonuc Raporu

**Otel Profili:**
- Oda sayisi: __
- Personel: __
- Plan: __
- Entegre kanallar: __

**Onboarding Suresi:** __ gun

**30-Gun Metrikleri:**
- Toplam rezervasyon: __
- Gunluk aktif kullanici: __
- Kanal sync basari: __%
- Ortalama API response: __ ms
- Toplam hata sayisi: __

**Musteri Gorusu:**
> "[Quote]" — [Isim], [Pozisyon]

**Oneriler:**
1. ...
2. ...
3. ...
