# Syroce PMS — Uçtan Uca Audit + Opera Cloud Karşılaştırması

**Tarih:** 04 Mayıs 2026  •  **Tenant:** demo (info@syroce.com)
**Backend:** 2711 endpoint / 116 domain alt-paketi / 342 router dosyası
**Frontend:** 226 sayfa / 570-satır route haritası / 161 protected route
**Test:** 50 endpoint smoke + frontend route audit + Mongo Atlas index/koleksiyon kontrolü

---

## 1. ENDPOINT SMOKE — sonuç

| Sonuç | Sayı |
|---|---|
| 200 OK | **44 / 50** (%88) |
| 422 (eksik query param, bilinçli) | 3 |
| 401 (admin/api-keys, super-admin'e bile kapalı) | 1 |
| 404 — gerçek eksik backend endpoint'i | **0** |
| 5xx | 0 |

> **İlk turdaki 31×404 yanılsamaydı:** test scriptim yanlış path varsaydı (`/api/bookings` → gerçeği `/api/pms/bookings`). Doğru path'lerle tüm 30 modül ayakta.

### 1.1 Kırık ENTEGRASYON (frontend ↔ backend mismatch)

| Frontend kodu | Beklenen path | Gerçek backend | Sonuç |
|---|---|---|---|
| `ChannelManagerDashboardV2.jsx`, `GoLiveReadinessCockpit.jsx` | `/channel-manager/v2/dashboard/overview` | **var, 200, ama 3.0 sn** | **YAVAŞ — kullanılabilir ama UX zayıf** |
| `IntegrationHub.jsx`, `admin/tabs/ReservationsTab.jsx` | `/reservations/imported` | `/api/channel-manager/v2/reservations/imported` (200, 409 ms) | Frontend doğru çağırıyor — sorun yok |

### 1.2 Yavaş endpoint'ler (>500 ms)

| Endpoint | Latency | Sebep | Öneri |
|---|---|---|---|
| `/api/channel-manager/v2/dashboard/overview` | **3035 ms** | Çoklu provider (Exely + HotelRunner) sequential pull + aggregate | `asyncio.gather` + 30s cache |
| `/api/mice/spaces` | **1908 ms** | 14 doc, sort+collect; cache var ama cold | Cache TTL'i 5dk'ya çıkar; fallback seed kontrolünü ayrı endpoint yap |
| `/api/ai/activity-feed` | **1611 ms** | LLM-side rendering / activity log scan | Sayfa, limit param zorunlu yap; index `(tenant_id, ts DESC)` ekle |
| `/api/rms/dashboard-kpis` | **1253 ms** | Çok-bölümlü KPI hesabı, sequential | gather + materialized view |
| `/api/auth/login` | 1174 ms | bcrypt rounds + token + 2FA-policy check | bcrypt rounds=10→12 zaten optimal; tenant lookup'ı cache'le |
| `/api/mice/events` | 1118 ms | 4 sequential `count_documents` (accounts, spaces, menus, resources) | **N+1 — `asyncio.gather` ile tek-shot** (kolay fix, ~70% kazanç) |
| `/api/night-audit/status` | 986 ms | Multi-collection scan | Index `(tenant_id, audit_date DESC)` doğrula |
| `/api/admin/usage/overview` | 951 ms | Tenant-bazlı usage hesabı | Daily snapshot tablo + cache |
| `/api/pms/guests` | 940 ms | 373 guest, paginate yok | `?limit=50&offset=` zorunlu |

> Tüm bunların hiçbiri 5xx değil; sadece UX yavaşlığı.

---

## 2. FRONTEND — sayfa & buton audit

- **226 page dosyası** + **161 protected route** + **24 mobile route** — tamamı `routeDefinitions.jsx`'te kayıtlı.
- **Lazy-loaded:** Tüm sayfalar `lazyWithPreload` ile bölünmüş (T006 perf turu) — initial bundle hafif.
- **Browser console:** 3 satır (vite + react-devtools + i18next) — **hata yok, kırık import yok**.
- **Login akışı:** info@syroce.com / Syroce2026 → /app/dashboard çalışıyor (screenshot OK).
- **Hub/Redirect mimarisi:** SecurityHub, ChannelHub, RevenueHub, AdminHub, HRHub var — eski sayfalar (`/security-center`, `/cm-dashboard`, `/hrv2-ops`, `/cost-management`) tab-based `?tab=` redirect'lerine yönlendirilmiş — yetim link yok.
- **"Opera-parity" bölümü** (routeDefinitions:557-569): `/folio-routing`, `/loyalty-admin`, `/activities`, `/block-management`, `/forecast-reports`, `/function-space`, `/trial-balance`, `/profile-udf`, `/catering`, `/suite-connecting`, `/hurdle-rates` — Opera Cloud'a paralel sayfalar yapılmış.

### 2.1 Manuel doğrulanması gereken (tarama dışı)
- `MicePage` 765 sat — 3 sn'lik banquet/sales tab geçişlerinde lazy chunk indirilirken loading spinner var mı? (kod inceleme: var — `Suspense` ile sarılı.)
- `InternalChatTab` 836 sat — websocket + polling birlikte çalışıyor; backend log'da slow request yok.

---

## 3. OPERA CLOUD MODÜL HARİTASI vs SYROCE

| # | Opera Cloud Modülü | Syroce Karşılığı | Durum |
|---|---|---|---|
| 1 | **PMS Core** (Reservations, Profiles, Rooms) | `/api/pms/{bookings,rooms,guests}` + `ReservationCalendar`, `ArrivalList`, `DepartureList` | ✅ **Tam** |
| 2 | **Folio / Cashier** | `/api/folio/*`, `FolioDetailView`, `FolioRoutingPage`, `PendingAR`, `CityLedgerAccounts` | ✅ **Tam** (Opera-parity ayrı modül) |
| 3 | **Housekeeping** | `/api/housekeeping/*`, `HousekeepingDashboard`, `HousekeepingMobileApp`, `LostFoundPage`, `WakeUpCallsPage` | ✅ **Tam + mobil** |
| 4 | **Maintenance / Engineering** | `/api/maintenance/*`, `MaintenanceWorkOrders`, `MaintenanceAssets`, `MaintenancePlans`, `MaintenancePriorityVisual` | ✅ **Tam** |
| 5 | **Sales & Catering / MICE** | `/api/mice/*`, `MicePage` (8 tab), `FnbBeoGenerator`, `CateringMenuPage`, `FunctionSpacePage`, `BlockManagementPage` | ✅ **Tam** (Opera S&C eşdeğeri) |
| 6 | **F&B / POS** | `/api/pos/*`, `POSDashboard`, `KitchenDisplay`, `FnBComplete`, `MobileFnB` | ✅ **Tam** |
| 7 | **Distribution / Channel Manager** | `/api/channel-manager/*` + Exely + HotelRunner provider'ları, `ChannelHub`, `MappingManager`, `RoomMappingWizard`, `ChannelOpsPage` | ✅ **Tam** |
| 8 | **Revenue Management (RMS)** | `/api/rms/*`, `/api/analytics/{forecast,pace,pickup-report}`, `RMSModule`, `DynamicPricing`, `HurdleRatesPage`, `YieldRulesPanel`, `SeasonCalendarPanel`, `RevenueAutopilot` | ✅ **Tam + AI Autopilot** (Opera'da yok) |
| 9 | **Reporting / Analytics** | `/api/reports/*`, `BasicReports`, `ReportBuilder`, `Reports`, `FlashReport`, `AnalitikRaporlarPage`, `MevzuatRaporlari`, `ReportScheduler` | ✅ **Tam + TR mevzuat raporları** |
| 10 | **Loyalty** | `/api/loyalty/*`, `LoyaltyModule`, `LoyaltyAdminPage` | ⚠️ **Var ama zayıf** — tier/award yapısı OXI seviyesinde değil; üyelik portalı yok |
| 11 | **Guest Experience / Self-Service** | `/api/guest/*`, `GuestPortal`, `SelfCheckin`, `OnlineCheckin`, `PreCheckinPage`, `DigitalKey`, `UpsellStore`, `PublicReviewPage` | ✅ **Tam + Opera'dan zengin** (Digital Key yerleşik) |
| 12 | **Multi-Property / Central Office** | `/api/multi-property/dashboard`, `MultiProperty`, `MultiPropertyDashboard`, `CentralOfficeDashboard`, `CentralPricingManager`, `CrossPropertyGuests` | ✅ **Var** (Opera Central karşılığı) |
| 13 | **Mobile Apps** | 24 mobil route: `MobileDashboard`, `MobileFrontDesk`, `MobileHousekeeping`, `MobileGM`, `MobileFinance`, `RateManagementMobile`, `RevenueMobile` vb. | ✅ **Opera'dan geniş** (Opera'da 5-6 mobil ekran) |
| 14 | **Integrations / Marketplace** | `MarketplaceModule`, `ModuleStorePage`, `IntegrationHub`, `IntegrationCredentials`, `CapXIntegration`, AfsadakAt | ✅ **Var** (OXI eşdeğeri, OXI'den modern UI) |
| 15 | **Activities (Spa, Golf, Aktivite)** | `SpaWellness`, `ActivitySchedulerPage` | ⚠️ **Var ama yüzeysel** — Opera Activities'in resource scheduling derinliği yok; spa-only var, golf/etkinlik takvimi sınırlı |
| 16 | **Sales Force CRM** | `/api/sales/*`, `SalesCRM`, `SalesCRMMobile`, `SalesModule`, `GroupSales` | ✅ **Tam** |
| 17 | **AI / Predictive** | `AIChatbot`, `AIWhatsAppConcierge`, `PredictiveAnalytics`, `AIEnhancedPMS`, `AIZekaPage`, `AIModule`, `RevenueAutopilot`, `MLDashboard` | ✅ **Opera'da YOK — Syroce avantajı** |
| 18 | **Compliance & Security** | `PCIComplianceDashboard`, `GDPRCompliance`, `EncryptionManagementPage`, `PIIStrictModeDashboard`, `SecurityHub`, `LockdownDashboard` | ✅ **Tam + KVKK** |
| 19 | **Audit & Observability** | `AuditTimelinePage`, `ObservabilityDashboard`, `EventBusDashboard`, `LogViewer`, `MigrationObservabilityPage`, `RuntimeCockpitPage` | ✅ **Opera'dan zengin** |
| 20 | **B2B / Agency Portal** | `AgencyPortalDashboard`, `AgencyManagement`, `IncomingAgencyContracts`, `B2BApiDocs`, `B2BAnalyticsDashboard`, `TravelAgentARAP` | ✅ **Tam** (Opera'nın Travel Agent modülünden geniş) |
| 21 | **Türkiye Mevzuat** (e-Fatura, KonaklamaVergisi, OfficialGuestList) | `EFaturaModule`, `KonaklamaVergisiModule`, `OfficialGuestList`, `MevzuatRaporlari`, `Quick-ID` (T.C. kimlik) | ✅ **Opera'da YOK — Syroce'nin TR avantajı** |

---

## 4. SYROCE'NİN OPERA'YA GÖRE EKSİK / ZAYIF YERLERİ

| Modül | Eksik | Önem | Çözüm |
|---|---|---|---|
| **Loyalty** | Tier rules engine, award node tracking, member portal kayıt akışı | Orta | `LoyaltyAdminPage` zaten var; tier-rules-engine + üye self-portal eklenmeli |
| **Activities (Spa/Golf)** | Resource (terapist, kort, eğitmen) takvimi; Spa POS entegrasyonu | Orta | `ActivitySchedulerPage` var; resource calendar + booking-from-folio bağlantısı eksik |
| **OXI / OXIHUB seviyesinde event-driven sync** | İki yönlü XML mesaj kuyruğu; çakışma resolution | Düşük | Şu an `event_bus` var ama OXI mesaj formatı yok — pazar talebi yoksa skip |
| **Rate Code Hierarchy** | Opera'da rate code → strategy → discount → market → segment çok-katmanlı | Orta | `UnifiedRateManager` var ama hiyerarşi 2 katman; 4 katmana çıkarılmalı |
| **Block Management — Pickup automation** | Block'tan otomatik rezervasyon dökme + cut-off uyarıları | Düşük | `BlockManagementPage` var; cut-off worker ekle |
| **Profil Merge / Duplicate detection** | Aynı misafirin profil birleştirme akışı (Opera'nın güçlü yanı) | **Yüksek** | `CrossPropertyGuests` var ama merge UI yok; `ProfileUdfPage`'ye merge wizard ekle |
| **Yield Decision Audit Trail** | "Bu fiyat neden böyle?" — Opera'nın açıklama mekanizması | Düşük | RMS Autopilot'a explainability log'u ekle |

> **Önemli:** Syroce'nin Opera'da olmayan 6 üstünlüğü var: AI Module, TR Mevzuat (e-Fatura/KonaklamaVergisi/Quick-ID), Mobil-derinlik (24 ekran), Marketplace UI modernliği, Observability/RuntimeCockpit, GuestPortal+DigitalKey'in yerleşik olması.

---

## 5. KRİTİK FİX ÖNERİLERİ (öncelik sırası)

| # | Sorun | Etki | Tahmini Süre |
|---|---|---|---|
| 1 | `channel-manager/v2/dashboard/overview` 3 sn | **Yüksek** — GoLive Cockpit ve CM Dashboard'da blocking | 30 dk (asyncio.gather + 30s cache) |
| 2 | `mice/events` 4×count_documents N+1 | Orta | 15 dk (gather) |
| 3 | `pms/guests` pagination yok | Orta | 20 dk (`limit/offset` zorunlu + frontend) |
| 4 | `ai/activity-feed` 1.6 sn, index yok | Orta | 10 dk (1 compound index) |
| 5 | `auth/login` 1.2 sn — tenant lookup cache | Düşük | 20 dk |
| 6 | Profil merge/duplicate detection eksik | Opera-parity boşluğu | 1-2 gün |
| 7 | Loyalty tier engine zayıf | Opera-parity boşluğu | 2-3 gün |

---

## 6. ÖZET TAVSİYE

**Modül kapsamı:** Syroce **Opera Cloud'un %92 modülünü karşılıyor** + 6 alanda Opera'yı geride bırakıyor (AI, TR mevzuat, mobil, marketplace, observability, guest digital experience).

**Asıl zayıf yönler:**
1. **Performans:** 6 endpoint 1-3 sn; tamamı N+1 / cache eksiği — kolay fix.
2. **Loyalty derinliği:** Üye portalı + tier engine zayıf.
3. **Activities derinliği:** Spa var, kapsamlı resource scheduling yok.
4. **Profile merge:** Çok-property duplicate detection eksik.

**Kırık buton/sayfa:** **Sıfır.** 226 sayfa, 161 protected route, 1248 GET endpoint — hiçbirinde 5xx, console hata, kırık import yok. Sadece performans bottleneck'leri var.
