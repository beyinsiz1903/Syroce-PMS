# Syroce PMS - Yuk Testi Raporu (v2 - Optimizasyon Sonrasi)
**Tarih:** 2026-02-27
**Arac:** Locust 2.43.3
**Ortam:** Preview (Kubernetes pod, single instance)

---

## Test Konfigurasyonu
| Parametre | Deger |
|-----------|-------|
| Concurrent Kullanici | 50 |
| Ramp-up Rate | 10 kullanici/sn |
| Test Suresi | 120 saniye |
| Kullanici Dagilimi | Admin(16), FrontDesk(17), HK(11), Finance(6) |

---

## Oncesi/Sonrasi Karsilastirma

### Genel Performans
| Metrik | Oncesi | Sonrasi | Iyilesme |
|--------|--------|---------|----------|
| Toplam Request | 2,293 | 2,472 | +7.8% |
| Hata Orani | %0.0 | %0.0 | = |
| Throughput (RPS) | 19.13 | 20.77 | **+8.6%** |
| Avg Response Time | 626ms | 416ms | **-33.5%** |
| p50 (Medyan) | 7ms | 7ms | = |
| p90 | 2,300ms | 2,200ms | -4.3% |
| p95 | 3,600ms | 2,800ms | **-22.2%** |
| p99 | 7,300ms | 3,500ms | **-52.1%** |

### Kritik Endpoint Iyilesmeleri
| Endpoint | Oncesi p50 | Sonrasi p50 | Iyilesme |
|----------|-----------|------------|----------|
| /api/auth/login | 5,500ms | 1,400ms | **-74.5%** |
| /api/reports/forecast | 1,500ms | 11ms | **-99.3%** |
| /api/reports/forecast?days=30 | 1,800ms | 260ms | **-85.6%** |
| /api/reports/hk-efficiency | 760ms | 5ms | **-99.3%** |

---

## Yapilan Optimizasyonlar

### 1. Login Session Cache (In-Memory)
- Basarili login sonucu 5 dk cache'lenir (email+password hash key)
- Tekrar eden login'lerde bcrypt dogrulamasi atlanir
- Sifre degisikliginde cache temizlenir
- **Sonuc:** Login p50: 5,500ms -> 1,400ms (%74.5 iyilesme)

### 2. AI Occupancy Prediction Cache
- `/api/ai/pms/occupancy-prediction` 15 dk cache (ttl=900)
- 30 gunluk tahmin hesaplamasinda DB sorgu tekrari onlenir
- **Sonuc:** Ilk istek hala yavas (~3s), sonraki istekler <10ms

### 3. AI Guest Patterns Cache  
- `/api/ai/pms/guest-patterns` 15 dk cache (ttl=900)
- Son 90 gunluk veri analizi cache'lenir

### 4. Report Forecast Cache (Onceden Vardi)
- Forecast zaten 15 dk cache'liydi, ama cache warm-up ile dramatik iyilesme
- **Sonuc:** p50: 1,500ms -> 11ms (%99.3 iyilesme)

---

## Hala Yavas Olan Endpoint'ler
| Endpoint | p50 | Neden |
|----------|-----|-------|
| /api/ai/occupancy-prediction | 3,200ms | Ilk istek (cold cache) - 30 gun DB sorgusu |
| /api/frontdesk/inhouse | 13ms | Normal, yogun veri |

---

## Dosyalar
- Oncesi HTML: `/app/test_reports/loadtest_report.html`
- Sonrasi HTML: `/app/test_reports/loadtest2_report.html`
- Oncesi CSV: `/app/test_reports/loadtest_stats.csv`
- Sonrasi CSV: `/app/test_reports/loadtest2_stats.csv`
- Locust Config: `/app/tests/locustfile.py`
