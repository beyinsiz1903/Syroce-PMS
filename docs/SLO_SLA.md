# Syroce PMS — SLO / SLA Tanimlari
## Servis Seviyesi Hedefleri ve Garantileri

**Versiyon**: 1.0
**Son Güncelleme**: Subat 2026
**Sahip**: Platform Muhendisligi
**Gozden Gecirme Periyodu**: Aylik

---

## 1. Terimler

| Terim | Tanim |
|-------|-------|
| **SLI** (Service Level Indicator) | Olculen metrik (orn. basarili istek orani) |
| **SLO** (Service Level Objective) | Ic hedef (orn. %99.5 uptime) |
| **SLA** (Service Level Agreement) | Musteriye garanti edilen seviye (orn. %99.0 uptime) |
| **Error Budget** | SLO ile %100 arasindaki fark. Hata butcesi tukenince yeni ozellik deploy'u durdurulur. |
| **Burn Rate** | Error budget'in tukenme hizi. 1x = normal, >3x = alarm |

---

## 2. Servis Seviyesi Gostergeleri (SLI)

### 2.1 Kullanilabilirlik (Availability)

| SLI | Tanim | Olcum Yontemi |
|-----|-------|---------------|
| API Availability | `(basarili_istek / toplam_istek) * 100` | Prometheus: `rate(http_requests_total{status!~"5.."}[5m]) / rate(http_requests_total[5m])` |
| Frontend Availability | HTML 200 donme orani | Synthetic monitoring (1dk aralik) |
| Database Availability | MongoDB ping basarisi | Health check endpoint (15s aralik) |

### 2.2 Gecikme (Latency)

| SLI | Tanim | Olcum Yontemi |
|-----|-------|---------------|
| API p50 latency | Medyan istek suresi | Prometheus histogram |
| API p95 latency | 95. yuzdelik istek suresi | Prometheus histogram |
| API p99 latency | 99. yuzdelik istek suresi | Prometheus histogram |
| Frontend TTFB | Time to First Byte | Synthetic monitoring |

### 2.3 Dogruluk (Correctness)

| SLI | Tanim | Olcum Yontemi |
|-----|-------|---------------|
| Booking Integrity | Cift rezervasyon olmayi orani | Load test + uretim loglari |
| Night Audit Accuracy | Hatali gece denetimi orani | Gunluk reconciliation raporu |
| OTA Sync Lag | PMS degisikliginin OTA'ya ulasmasi | Outbox queue depth metrigi |

---

## 3. Servis Seviyesi Hedefleri (SLO)

### 3.1 Tier 1 — Kritik Yol (Booking & Check-in/out)

| Metrik | SLO Hedefi | Olcum Penceresi | Error Budget (30 gun) |
|--------|-----------|-----------------|----------------------|
| Availability | >= 99.9% | 30 gunluk hareketli | 43 dakika downtime |
| p95 Latency | <= 500ms | 30 gunluk hareketli | - |
| p99 Latency | <= 2000ms | 30 gunluk hareketli | - |
| Booking Integrity | 0 cift rezervasyon | Surekli | Sifir tolerans |

**Kapsam**: `/api/pms/bookings/*`, `/api/pms/reservations/*`, `/api/pms/availability/*`, `/api/auth/login`

### 3.2 Tier 2 — Operasyonel (Dashboard, Housekeeping, Reports)

| Metrik | SLO Hedefi | Olcum Penceresi | Error Budget (30 gun) |
|--------|-----------|-----------------|----------------------|
| Availability | >= 99.5% | 30 gunluk hareketli | 3.6 saat downtime |
| p95 Latency | <= 1000ms | 30 gunluk hareketli | - |
| p99 Latency | <= 3000ms | 30 gunluk hareketli | - |

**Kapsam**: `/api/pms/dashboard/*`, `/api/housekeeping/*`, `/api/reports/*`, `/api/ops/*`

### 3.3 Tier 3 — Yardimci (Admin, Ayarlar, Raporlama)

| Metrik | SLO Hedefi | Olcum Penceresi | Error Budget (30 gun) |
|--------|-----------|-----------------|----------------------|
| Availability | >= 99.0% | 30 gunluk hareketli | 7.2 saat downtime |
| p95 Latency | <= 2000ms | 30 gunluk hareketli | - |

**Kapsam**: `/api/admin/*`, `/api/settings/*`, `/api/analytics/*`

---

## 4. Musteri SLA

### 4.1 Uptime Garantisi

| Plan | SLA | Aylik Izin Verilen Downtime | Kredi Politikasi |
|------|-----|----------------------------|------------------|
| Standard | 99.0% | 7 saat 18 dakika | %10 kredi (SLA ihlali basina) |
| Professional | 99.5% | 3 saat 36 dakika | %15 kredi |
| Enterprise | 99.9% | 43 dakika | %25 kredi + RCA raporu 48 saat icerisinde |

### 4.2 Harici Bagimliliklarin Etkisi

| Baglanti | SLA'ya Dahil mi? | Aciklama |
|----------|-------------------|----------|
| MongoDB Atlas | Hayir | Atlas kendi SLA'sini saglar (%99.995) |
| OTA API'leri (HotelRunner, Exely) | Hayir | Ucuncu taraf kullanilabilirlik garantimiz disindadir |
| CDN | Hayir | Statik asset'ler CDN uzerinden sunulur |
| Syroce API | Evet | Tamamen bizim sorumlulugumuzda |
| Syroce Frontend | Evet | Tamamen bizim sorumlulugumuzda |

### 4.3 Planlanan Bakim Pencereleri

| Parametre | Deger |
|-----------|-------|
| Bakim gunleri | Sali ve Persembe, 02:00-04:00 UTC |
| Bildirim suresi | En az 48 saat onceden |
| Maksimum sure | 2 saat |
| Aylik limit | 4 saat |
| SLA'dan haric mi? | Evet (onceden bildirilmis bakim SLA hesabina dahil edilmez) |

---

## 5. Yanit Suresi Hedefleri

| Oncelik | Tespetten Ilk Yanita | Cozume | Ornekler |
|---------|----------------------|--------|----------|
| P0 — Kritik | 15 dakika | 4 saat | Sistem tamamen erislemez, veri kaybi |
| P1 — Yuksek | 30 dakika | 8 saat | Rezervasyon olusturulamaz, check-in basarisiz |
| P2 — Orta | 2 saat | 24 saat | Dashboard yavas, rapor hatali |
| P3 — Dusuk | 8 saat | 72 saat | Kozmetik hata, minor UI sorunu |

---

## 6. Error Budget Politikasi

### 6.1 Normal Isleyis (Budget > %50)

- Normal gelistirme ve deploy ritmi
- Haftalik SLO inceleme toplantisi

### 6.2 Uyari Durumu (Budget %25-%50)

- Yeni ozellik deploy'lari yavaslat
- Her deploy icin ek smoke test zorunlu
- Gunluk SLO inceleme

### 6.3 Kritik Durum (Budget < %25)

- **YENI OZELLIK DEPLOY'U DURDURULUR**
- Sadece guvenilirlik iyilestirmeleri ve bug fix'ler deploy edilir
- Gunluk RCA toplantisi
- Geri donuse kadar Tier 1 endpointler icin canary deploy zorunlu

### 6.4 Budget Tukendi (%0)

- Tum deploy'lar CTO onayi gerektirir
- Kok neden analizi (RCA) zorunlu
- Musteri iletisimi tetiklenir
- Post-mortem sonrasi iyilestirme plani olusturulur

---

## 7. Izleme & Raporlama

### 7.1 Dashboard'lar

| Dashboard | Icerik | Erisim |
|-----------|--------|--------|
| SLO Overview | Tum tier'larin guncel durumu, error budget | Grafana: `/d/slo-overview` |
| API Latency | p50/p95/p99 dagilimi, endpoint bazli | Grafana: `/d/api-latency` |
| Availability | Uptime timeline, downtime olaylari | Grafana: `/d/availability` |
| Error Budget Burn | Yakin zamandaki tukenme hizi | Grafana: `/d/error-budget` |

### 7.2 Alarm Kurallari

| Alarm | Kosul | Kanal | Aksiyon |
|-------|-------|-------|---------|
| SLO Burn Rate > 3x | 1 saatlik pencerede | PagerDuty + Slack | Nobet muhendisi inceler |
| SLO Burn Rate > 10x | 5 dakikalik pencerede | PagerDuty (acil) | Aninda mudahale |
| Error Budget < %25 | Hesaplanan | Slack #slo-alerts | Deploy freeze baslar |
| p99 > 5s | 10 dakika sureli | Slack #ops-alerts | Performans inceleme |

### 7.3 Aylik SLO Raporu

Her ayin ilk is gunu:
1. Her tier icin gerceklesen SLI degerleri
2. Error budget kullanim durumu
3. SLA ihlali oldu mu? (Kredi gerekli mi?)
4. Onceki ayin olay ozeti
5. Gelecek ay iyilestirme onerileri
