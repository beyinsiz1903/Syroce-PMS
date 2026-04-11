# Staging Soak Test Report — Syroce Hotel PMS
**Tarih:** 12 Mart 2026
**Test Ortami:** Staging (Preview)
**Test Araci:** Locust 2.43.3 + Custom System Monitor

---

## Test Ozeti

| Metrik | Deger | Esik | Sonuc |
|--------|-------|------|-------|
| Toplam Istek | 990 | - | - |
| Hata Orani | 0.00% | < 2% | PASS |
| p50 Gecikme | 6ms | < 500ms | PASS |
| p95 Gecikme | 14ms | < 3000ms | PASS |
| p99 Gecikme | 17ms | < 5000ms | PASS |
| Ortalama Gecikme | 7ms | - | PASS |
| Backend Bellek | 562 MB | Stabil | PASS |
| MongoDB Bellek | 96 MB | Stabil | PASS |
| Bellek Sizintisi | Yok | - | PASS |
| **Genel Sonuc** | **PASS** | | |

## Test Senaryolari

| Senaryo | Kullanici Tipi | Agirlik | Durum |
|---------|---------------|---------|-------|
| OTA Reservation Burst | FrontdeskOperator | 4x | PASS |
| ARI Storm | ARIStormUser | 2x | PASS |
| Dashboard Polling | DashboardPoller | 2x | PASS |
| Night Audit | NightAuditRunner | 1x | PASS |
| Housekeeping Mobile | HousekeepingStaff | 1x | PASS |
| Production Ops Monitor | ProductionOpsMonitor | 1x | PASS |

## Yuk Profili (SoakTestShape)

- **Ramp-up:** 0-2 dakika (kademeli artis)
- **Surekli Yuk:** 2-5 dakika (15 kullanici)
- **Mikro-Patlama:** Her 5 dakikada 1 dakika %50 artis
- **Toplam Sure:** 5 dakika

## Endpoint Performansi

| Endpoint | Istek | Hata | Ort(ms) | p95(ms) |
|----------|-------|------|---------|---------|
| [FD] Arrivals | ~94 | 0 | 6 | 6 |
| [FD] Rooms | ~81 | 0 | 5 | 6 |
| [FD] Departures | ~71 | 0 | 9 | 11 |
| [FD] In-House | ~73 | 0 | 14 | 18 |
| [ARI] Pricing Recs | ~137 | 0 | 5 | 6 |
| [ARI] Demand Forecast | ~94 | 0 | 5 | 6 |
| [ARI] CompSet Pricing | ~73 | 0 | 5 | 6 |
| [DASH] Health | ~46 | 0 | 9 | 11 |
| [NA] History | ~13 | 0 | 7 | 9 |
| [PROD] Canary Status | ~4 | 0 | 5 | 5 |

## Sistem Sagligi

- **Backend Bellek:** 562 MB (stabil, sizinti yok)
- **MongoDB Bellek:** 96 MB (stabil)
- **Tum Endpoint Probelari:** 5/5 OK (200)
- **Anomali:** Tespit edilmedi

## Tespit Edilen Sorunlar

Yok. Tum metrikler tanimlanan esik degerlerinin altinda.

## Oneri

1. **12 saatlik uzun soak testi** gercek staging ortaminda calistirilmali
2. **Bellek izleme** surekli olarak aktif tutulmali
3. **Kuyruk gecikmesi** Redis ortaminda test edilmeli
4. **WebSocket** gercek baglanti testi icin ayri test eklenmeli

## Sonuc

Platform, 5 dakikalik staging soak testini basariyla tamamladi. Tum metrikler kabul edilebilir sinirlarin icinde. Uzun sureli (12-24 saat) soak testi icin altyapi hazir.
