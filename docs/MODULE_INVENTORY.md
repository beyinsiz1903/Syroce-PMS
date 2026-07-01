# Syroce PMS — Modül Envanteri

**Tutulan tarih:** Mayıs 2026
**Amaç:** Her modül + her dış API yüzeyi için ortak statü etiketi (kalite kapısı). Yeni modül eklendiğinde / mevcut bir modül olgunlaştığında **bu dosya güncellenir**. Statü değişiklikleri PR açıklamasında zorunludur.

> Bu doküman ChatGPT'nin Mayıs 2026 mimari incelemesinde önerilen "modül envanteri" aksiyonunun karşılığıdır. "Her şey var ama hiçbir şey tam bitmemiş" hissinden kaçınmak için **gerçek** statü görünürlüğü sağlar.

---

## Statü konvansiyonu

| Etiket | Anlamı |
|---|---|
| `production_ready` | Tam CRUD + tenant scope + permission + audit + test. Müşteriye satılabilir. |
| `partial` | Gerçek DB okuma var ama write/workflow eksik **veya** UI hazır ama bazı edge-case'ler işlenmiyor. |
| `stub` | Sadece güvenli default döner; iş mantığı yok. UI çakılmasın diye var. |
| `demo` | Yalnız demo verisi / mock servis ile çalışır; gerçek müşteri ortamında kapatılmalı. |
| `deprecated` | Eski clientlar için bekletiliyor; bir sonraki major sürümde kaldırılacak. |

Etiketler **nominal**; ölçütler:
- `production_ready` → en az 1 backend test + 1 frontend test, permission decorator, audit field
  - **Public endpoint istisnası:** Permission decorator doğal olarak yoktur. Yerine: explicit public-access rationale (yorumda) + rate limit + abuse guard (örn. token, captcha veya IP throttle) aranır. Örnek: `/g/room/...`, `/review/:token`, `/precheckin`.
- `partial` → tenant scope OK, ama eksik workflow listelenmeli
- `stub` → yorumda hangi alan eksik açıklanmalı
- `demo` → environment var ile kapatılabilir olmalı
- `deprecated` → kaldırılma tarihi yorumda

---

## Backend modülleri (domain bazlı)

### PMS Core (ana çekirdek)
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Bookings (CRUD/lifecycle) | `routers/pms_bookings.py` | `production_ready` | Atomic check-in/out; overbooking guard testleri var |
| Reservations | `routers/pms_reservations.py` | `production_ready` | Lifecycle state machine; multi-room |
| Rooms | `routers/pms_rooms.py` | `production_ready` | Status, image upload |
| Room Map | `routers/room_map.py` | `production_ready` | |
| Guests | `routers/pms_guests.py` | `production_ready` | Walk-in placeholder isim handling |
| Walk-in | `routers/walkin.py` | `production_ready` | |
| Availability | `routers/pms_availability.py` | `production_ready` | Channel ile beslenir |
| Booking Holds | `routers/booking_holds.py` | `production_ready` | TTL'li |
| Block Management | `domains/pms/block_management_router.py` | `production_ready` | |
| Reservation Detail | `routers/reservation_detail.py` | `production_ready` | |
| Calendar | `domains/pms/calendar_router.py` | `production_ready` | TR locale fix tamamlandı |
| Approvals | `domains/pms/approvals_router.py` | `production_ready` | |
| Activity Scheduler | `domains/pms/activity_scheduler_router.py` | `partial` | |
| Catering | `domains/pms/catering_router.py` | `partial` | |
| Cashier | `domains/pms/cashier_router.py` | `production_ready` | PCI-DSS yönetimi var |

### Operations
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Housekeeping | `routers/housekeeping.py` | `production_ready` | Mobil push notification var |
| Maintenance Work Orders | `domains/pms/maintenance_router.py` + frontend `MaintenanceWorkOrders.jsx` | `production_ready` | Sprint A pilot; backend: work-orders CRUD + mobile/technician-task + repeat-issues + sla-metrics |
| Shift Handover | `routers/shift_handover.py` | `production_ready` | |
| Departments | `routers/departments/` (bookings/dashboards/housekeeping/pos/reports/rms_rates) | `production_ready` | Klasör; 7 alt-router |
| Lost & Found | `routers/b2b_api/lost_found.py` + frontend `LostFoundPage.jsx` | `production_ready` | Sprint A pilot; backend: GET/POST `/lost-found` (b2b_api altında ama internal UI de tüketir) |
| Wake-up Calls | `routers/b2b_api/wake_up.py` + frontend `WakeUpCallsPage.jsx` | `production_ready` | Sprint A pilot; backend: GET/POST `/wake-up-calls` (b2b_api altında ama internal UI de tüketir) |
| Night Audit | `domains/pms/night_audit/router.py` | `production_ready` | N+1 fix done |
| EOD Report | `routers/eod_report.py` | `production_ready` | |
| Frontdesk Audit Checklist | (frontend pilot) | `production_ready` | Sprint A pilot |

### Finance / Accounting
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Folio Ledger | `routers/folio_ledger.py` | `production_ready` | Append-only ledger; void/transfer var |
| Folio dialog (UI) | `components/pms/FolioViewDialog.jsx` | `production_ready` | Loading/picker/empty state May 2026 |
| Finance | `routers/finance/` (klasör; folio/invoices/...) | `production_ready` | |
| Accounting Domain | `domains/accounting/` | `partial` | E-Fatura mevcut, e-Arşiv pending |
| Invoices (E-Fatura) | (frontend `EFaturaModule.jsx`) | `production_ready` | |
| Pending AR | (frontend `PendingAR.jsx`) | `production_ready` | |
| City Ledger | (frontend `CityLedgerAccounts.jsx`) | `production_ready` | |
| Travel Agent A/R-A/P | `routers/travel_agent_arap.py` | `production_ready` | |
| Deposit Tracking | (frontend `DepositTrackingPage.jsx`) | `production_ready` | Sprint A pilot |
| VCC | `routers/vcc_router.py` | `partial` | |
| Procurement | (frontend `ProcurementPage.jsx`) | `production_ready` | Action ghost→outline+icon migration done |

### Channel Manager
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Channel Connections | `domains/channel_manager/channel_connections_router.py` | `production_ready` | |
| HotelRunner Integration | `routers/hotelrunner_compat.py` | `production_ready` | Pull retries fix May 2026 |
| Exely Integration | (`backend/...`) | `production_ready` | IP allowlist required |
| ARI Push Engine | `domains/channel_manager/ari/` + `workers/ari_push_worker.py` | `production_ready` | DLQ + replay; ack_service/buffer/coalescer |
| Auto-Map | `domains/channel_manager/auto_map_router.py` | `production_ready` | |
| Auto-Heal Service | `domains/channel_manager/auto_heal_service.py` | `partial` | |
| Availability Reconciliation | `domains/channel_manager/availability_reconciliation_worker.py` | `production_ready` | |
| Cockpit Snapshot Worker | `domains/channel_manager/cockpit_snapshot_worker.py` | `production_ready` | |
| CapX Integration | `routers/capx_integration.py` | `production_ready` | Encrypted credentials |
| Wire Failure Dashboard | (frontend) | `production_ready` | |

### Revenue / RMS
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Revenue Management | `routers/revenue_management.py` | `production_ready` | |
| Forecasting | `domains/revenue/forecasting/` + `forecast_router.py` | `partial` | Demo veri olmadan zayıf öneri |
| Hurdle Rates | `domains/revenue/hurdle_router.py` | `partial` | |
| Pricing | `domains/revenue/pricing_router/` | `partial` | |
| Auto-Pricing | `domains/revenue/autopricing/` | `partial` | İlk versiyon "recommend + explain", autopilot kapatık |
| Displacement Analysis | `routers/displacement_analysis.py` | `production_ready` | |
| Revenue Autopilot v2 | `routers/revenue_autopilot_v2.py` | `partial` | |
| Banquet Competitor | `routers/banquet_competitor.py` | `partial` | |
| Unified Rate Manager (UI) | `pages/UnifiedRateManager` | `production_ready` | |
| RMS Module (UI) | `pages/RMSModule` | `production_ready` | Sprint A pilot |

### Guest Experience
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Guest Journey | `routers/guest_journey.py` | `partial` | |
| Guest Messaging | `routers/guest_messaging.py` | `production_ready` | |
| Loyalty | `domains/guest/loyalty_router.py` | `partial` | |
| Self Check-in / Pre-checkin | `domains/guest/checkin_router.py` | `production_ready` | KVKK ID-photo cleanup var |
| Digital Key | (frontend) | `partial` | |
| Online Check-in | (frontend `OnlineCheckin.jsx`) | `production_ready` | |
| Room QR Requests | (`/g/room/...` public route) | `production_ready` | |
| Public Reviews | (`/review/:token` public route) | `production_ready` | |
| Mailing | (`pages/MailingPage`) | `production_ready` | Sprint A pilot |
| Reputation Manager | `domains/ai/router/pricing_reputation.py` | `partial` | |

### AI / ML
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| AI Module Hub | `pages/AIModule` | `partial` | |
| Dynamic Pricing Engine | `domains/ai/dynamic_pricing_engine.py` | `partial` | "Recommend + explain" yaklaşımı |
| Predictive Engine | `domains/ai/predictive_engine.py` | `partial` | |
| Revenue Autopilot (AI) | `domains/ai/revenue_autopilot.py` | `partial` | |
| Reputation Manager (AI) | `domains/ai/router/pricing_reputation.py` | `partial` | |
| ML Scheduler | `routers/ml_scheduler.py` | `production_ready` | |
| AI RMS Dashboard (UI) | (frontend) | `production_ready` | EN→TR + gradient kaldırma May 2026 |
| Predictive Analytics (UI) | (frontend) | `production_ready` | |

### Marketplace / B2B / Agency
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Module Store (UI) | `pages/ModuleStorePage` | `production_ready` | |
| Marketplace | (`/app/module-store`) | `partial` | |
| B2B API | `routers/b2b_api/` | `partial` | |
| B2B Analytics | `routers/b2b_analytics.py` | `partial` | |
| Agency Portal | `routers/agency_portal.py` | `production_ready` | |
| Agency Contracts | `routers/agency_contracts.py` | `production_ready` | |
| Agency Content | `routers/agency_content.py` | `partial` | |
| Hotel Booking Requests | `routers/missing_endpoints_compat.py` | `production_ready` | Compat dosyasında ama tam workflow var; taşınmalı |

### Compliance / Security / Admin
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Auth (JWT + 2FA/TOTP) | `routers/auth.py` + `core/security.py` | `production_ready` | Refresh + jti revocation |
| Tenant Isolation | `core/tenant_db.py` | `production_ready` | 3 katmanlı, 4 ayrı test suite |
| RBAC | `modules/pms_core/role_permission_service.py` | `production_ready` | |
| Admin Control Panel (UI hub) | `pages/AdminControlPanel.jsx` → `domains/admin/router/` alt-router'lar | `production_ready` | UI hub; backend tek dosya değil |
| KVKK Manager | (frontend `KVKKManager.jsx`) | `production_ready` | |
| KBS Notification | (frontend `KBSNotification.jsx`) | `production_ready` | |
| GDPR Compliance | `routers/missing_endpoints_compat.py` (compliance-status, dpa) | `partial` | Compat dosyasında; gerçek workflow eksik |
| GDPR Retention Policy | `routers/missing_endpoints_compat.py` | `stub` | Hard-coded liste |
| Security IP Rules | `routers/missing_endpoints_compat.py` | `production_ready` | Tam CRUD; taşınmalı |
| Security IP Check | `routers/missing_endpoints_compat.py` | `stub` | Her zaman allowed=true |
| PCI Compliance Dashboard | (frontend) | `production_ready` | |
| Audit Timeline | `routers/audit_timeline.py` | `production_ready` | |
| Auto-Remediation Engine | `routers/auto_remediation_engine.py` | `partial` | |
| Lockdown Dashboard | (frontend) | `production_ready` | |

### Observability / Control Plane
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Observability | `routers/observability.py` | `production_ready` | |
| Control Plane | (frontend `ControlPlane.jsx`) | `production_ready` | |
| Runtime Cockpit | (frontend `RuntimeCockpitPage.jsx`) | `production_ready` | |
| Operator Incident Panel | (frontend `OperatorIncidentPanel.jsx`) | `production_ready` | |
| Migration Observability | (frontend `MigrationObservabilityPage.jsx`) | `production_ready` | |
| Operational Event Dashboard | (frontend `OperationalEventDashboard.jsx`) | `production_ready` | |
| Production Go-Live | `routers/production_golive.py` + `GoLiveReadinessCockpit.jsx` | `production_ready` | |
| Event Bus | `routers/event_bus.py` | `production_ready` | SXI bus |
| WebSocket Health | `routers/websocket_health.py` | `production_ready` | Circuit breaker |

### Multi-property / Central Office
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Cross-Property | `routers/cross_property.py` | `partial` | |
| Central Office Dashboard | `routers/missing_endpoints_compat.py` | `partial` | Properties read OK, KPI'lar 0 |
| Central Office Alerts/Occupancy/Revenue | `routers/missing_endpoints_compat.py` | `stub` | Hepsi boş |
| Central Pricing (3 endpoint) | `routers/missing_endpoints_compat.py` | `stub` | Tümü boş |

### Add-on Domains
| Modül | Dosya | Statü | Not |
|---|---|---|---|
| Spa | `domains/spa/router.py` | `partial` | |
| Golf | `domains/golf/router.py` | `partial` | |
| HR | `domains/hr/router.py` | `partial` | |
| Sales / CRM | `domains/sales/crm_router.py` | `partial` | |
| MICE / Banquet | (frontend `MicePage`) | `partial` | |

---

## Frontend modülleri (sayfa bazlı, özet)

> Tam liste için `frontend/src/routes/routeDefinitions.jsx`'e bakın. Aşağıda **kritik akışlar** statüye göre.

| Sayfa | Statü | Not |
|---|---|---|
| `/auth` (Login) | `production_ready` | E2E #01 var |
| `/app/dashboard` | `production_ready` | E2E #02 |
| `/pms` (PMSModule hub) | `production_ready` | Quick actions sade Card May 2026 |
| `/reservation-calendar` | `production_ready` | Locale fix + amber CTA bilinçli istisna |
| `/arrival-list` | `production_ready` | Sprint A pilot |
| `/departure-list` | `production_ready` | Sprint A pilot |
| `/no-show-today` | `production_ready` | Sprint A pilot |
| Folio Yönetimi dialog | `production_ready` | Loading/picker/empty May 2026 |
| `/night-audit` | `production_ready` | |
| `/channel-manager`, `/channels` | `production_ready` | |
| `/unified-rate-manager` | `production_ready` | |
| `/control-plane` | `production_ready` | |
| `/online-checkin` | `production_ready` | |
| `/marketplace`, `/module-store` | `partial` | |
| `/spa`, `/golf`, `/hr`, `/mice` | `partial` | |
| `/ai-pms` | `partial` | |

### Sprint A pilot uygulanan 12 sayfa (May 2026)
DepartureList, NoShowToday, WakeUpCallsPage, LostFoundPage, DepositTracking, ArrivalList, HousekeepingDashboard, MaintenanceWorkOrders, NightAuditDashboard, FrontdeskAuditChecklist, RMSModule, MailingPage. Hepsi `PageHeader/KpiCard/StatusBadge` standardına geçti.

---

## Test kapsamı (May 2026)

| Katman | Test | Statü |
|---|---|---|
| Backend pytest | 296 dosya (battle/integration/resilience/runtime klasörleri) | `production_ready` |
| Tenant isolation | `harnesses/tenant_isolation.py` + `resilience/test_tenant_isolation.py` + `runtime/test_tenant_isolation_concurrent.py` + `test_strict_tenant_wire_status.py` (4 katman) | `production_ready` |
| Channel Manager (DLQ/retry/idempotency) | `tests/integration/test_exely_provider_flows.py` + ops events tests | `production_ready` |
| Folio ledger | `tests/battle/test_folio_ledger.py` | `production_ready` |
| Frontend Vitest | 13 dosya, 117 test (currency, KpiCard, PageHeader, StatusBadge, FolioViewDialog, dialogs, helpers, ...) | `partial` (kapsam gelişiyor) |
| Frontend Playwright E2E | 5 smoke (login → dashboard → rooms → reservation dialog → arrivals + logout) | `partial` (full lifecycle eksik: payment + checkout) |

---

## Compatibility / Stub haritası

`backend/routers/missing_endpoints_compat.py` — **20 endpoint**, geçici barınma noktası. Her endpoint dosya içinde `# STATUS: ...` ile etiketlendi (May 2026):

| Statü | Sayı | Hedef |
|---|---|---|
| `production_ready` | 6 | Domain router'a taşınmaya hazır (security/ip CRUD, agency booking workflow, booking guest patch) |
| `partial` | 6 | Eksik workflow'lar tamamlanmalı (upsell, gdpr-status, gdpr-dpa, central-office-dashboard, media-list) |
| `stub` | 8 | Gerçek implementasyon eksik (gdpr-retention, central-office-{alerts,occupancy,revenue}, central-pricing × 3, security-ip-check) |

**Migration kuralı:** Bu dosyaya **yeni endpoint eklenmemeli**. Her **cleanup/refactor sprint**'inde en az 2 `production_ready` etiketli endpoint domain router'a taşınmalı (ürün/bugfix sprintlerinde zorunlu borç baskısı oluşturmamak için bu kural cleanup sprintlerine yönlendirildi).

---

## Altyapı (yatay servis katmanı)

Bu katman tek başına bir "modül" değil; ama birçok `production_ready` modülün doğruluk garantisi buradan gelir. Burada bir regression olursa yukarıdaki etiketler güvenilirliğini kaybeder.

| Servis | Dosya | Statü | Not |
|---|---|---|---|
| Outbox Dispatcher | `core/outbox_dispatcher.py` | `production_ready` | At-least-once event delivery |
| Event System | `routers/event_system.py` + `modules/event_system/` | `production_ready` | SXI bus altyapısı |
| Tenant DB | `core/tenant_db.py` | `production_ready` | 4 katman test |
| Cache Manager | `backend/cache_manager.py` (ana) + `backend/core/cache.py` (helper) + `backend/advanced_cache.py` (advanced layer) | `production_ready` | `?refresh=1` ile `_nocache` kwarg tetikler |
| Auth cache invalidation | (Redis pub/sub) | `production_ready` | Multi-worker |
| Mobile push | `services/expo_push.py` + `workers/mobile_push_scheduler.py` + `domains/pms/notification_router.py` | `partial` | DISABLE_EXPO_PUSH flag; tek bir `routers/mobile_push.py` yok — push akışı service+worker+notification router'a dağıtılmış |
| Xchange Integration | `backend/integrations/xchange` | `partial` | |
| CapX Webhook | `routers/capx_webhook.py` | `production_ready` | |

---

## Bilinen "demo / sentetik veri" alanları

Aşağıdakiler gerçek müşteri verisi olmadan zayıf çalışır; pilot/demo'da görünür ama go-live'da feature flag ile kapatılmalı:

- AI Reputation Manager (review verisi yoksa)
- Forecasting / Hurdle / Auto-Pricing (en az 90 gün rezervasyon geçmişi olmadan zayıf)
- Predictive Analytics (no-show risk için en az 6 ay veri lazım)
- Central Office KPI'ları (multi-property abonelik yoksa)

---

## Güncelleme prosedürü

1. Yeni modül eklendi / mevcut modülün statüsü değişti → bu dosya güncellenir.
2. PR açıklamasına "MODULE_INVENTORY.md güncellendi: X → Y statü değişikliği" yazılır.
3. `production_ready` etiketi koymak için minimum: backend test + frontend test + permission decorator + audit field.
4. `compat` dosyasından bir endpoint çıkarıldığında bu envanterdeki kaydı **silinmez**, dosya yolu yeni router'a güncellenir.

---

## Pointers

- ChatGPT mimari incelemesi: `attached_assets/Pasted-Murat-ilk-izlenimim-net-bu-repo-basit-otel-otomasyonu-d_1778424796518.txt`
- Sprint A standartları: `digitalocean.md` Gotchas → "Sprint A Design System (May 2026)"
- Pages Layout Wrap kuralı: `digitalocean.md` Gotchas → "Pages Layout Wrap"
