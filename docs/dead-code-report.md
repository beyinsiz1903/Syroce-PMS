# Dead Code Raporu (knip 6.x)

**Üretildi:** 7 Mayıs 2026 — `cd frontend && yarn knip --reporter compact`  
**Yorum:** Aşağıdaki bulgular **OTOMATİK SİLİNMEMELİ**. knip lazy-loaded
route'larda ve dynamic import'larda false-positive verebilir. Her dosya
manuel doğrulama sonrası temizlenmeli.

## Özet

| Kategori | Adet | Tahmini bundle etkisi |
|---|---|---|
| Kullanılmayan dosya | **92** | ~150-300 KB gzip (büyük çoğunluğu component) |
| Kullanılmayan npm dep | 11 | ~80-120 KB gzip (jspdf, html5-qrcode, react-hook-form vs.) |
| Kullanılmayan dev dep | 4 | 0 (build dışı) |
| Kullanılmayan export | 19 | ~5-10 KB |
| Çözülemeyen import | 1 | `src/utils/lazyLoad.jsx → ./pages/Dashboard` (broken!) |

## ÖNCELİK 1 — Hemen düzelt (broken import)

```
src/utils/lazyLoad.jsx → ./pages/Dashboard
```

`Dashboard.jsx` taşınmış/silinmiş ama `lazyLoad.jsx` hâlâ import etmeye
çalışıyor. Eğer `lazyLoad.jsx` da unused (knip listesinde) ise ikisi
birlikte kaldırılabilir.

## ÖNCELİK 2 — npm deps (build size kazanımı)

`package.json` dependencies:

- `@hookform/resolvers` (knip yanıltıcı olabilir — `react-hook-form` ile
  birlikte; manuel grep et)
- `@tanstack/react-query-devtools` (devtools — DEV-only kullanılmıyorsa kaldır)
- `cmdk` (CommandCenter unused → birlikte gidebilir)
- `date-fns` ⚠️ — büyük olasılıkla DOLAYLI kullanım var (recharts/sonner
  peer-dep). **Manuel doğrulama şart**, kaldırma riskli.
- `html5-qrcode` (QR Reader components unused → birlikte temizle)
- `i18next-http-backend` (locale fetch — gerçekten kullanılmıyorsa kaldır,
  i18n.js refactor sırasında bırakılmış olabilir)
- `jspdf`, `jspdf-autotable` (PDF export — Reports sayfaları kullanıyor mu?
  manuel kontrol)
- `react-hook-form` (form pattern — büyük olasılıkla `@hookform/resolvers`
  ile birlikte aktif, false-positive)
- `react-resizable-panels` (dashboard panel layout?)
- `zod` ⚠️ — schema validation, kesinlikle kullanılıyor olabilir

**Tavsiye**: Önce `rg "import .* from ['\"](X)['\"]"` ile her birini
doğrula. Sadece sıfır eşleşenleri kaldır.

## ÖNCELİK 3 — 92 unused dosya

Büyük temizlik fırsatı. Ama dikkat:

- `src/components/calendar/CalendarDialogs.jsx`,
  `CalendarWidgets.jsx` — calendar/* lazy import edilmiş olabilir
- `src/modules/*/index.jsx` (8 modül index'i) — module loader pattern
  varsa dynamic import false-positive
- `src/components/ui/*` (knip'de zaten `ignore` listesinde) — dokunma

**Güvenli temizleme önerisi (PR akışı):**

1. `git checkout -b chore/dead-code-batch-1`
2. Her PR'da en fazla 10 dosya sil; vitest + e2e suite çalıştır
3. Tarayıcıda Login → Dashboard → Reservations → Folio → Cashier
   smoke (Playwright #01-#05) yeşil
4. Bundle analyze: `yarn analyze` öncesi/sonrası karşılaştır

## Tam liste — 92 unused dosya

(knip output birebir; commit'te yer alır)

```
src/api/bookings.jsx
src/components/ADRTrackingBand.jsx
src/components/AdvancedMonitoring.jsx
src/components/AllotmentConsumptionChart.jsx
src/components/AnomalyAlerts.jsx
src/components/ApprovalWidget.jsx
src/components/BookingSearch.jsx
src/components/CRMNotes.jsx
src/components/CancellationPolicyDisplay.jsx
src/components/ChannelManagerDashboard.jsx
src/components/ColorLegend.jsx
src/components/ComplaintManager.jsx
src/components/ComprehensiveReportsModule.jsx
src/components/CorporateRatesModule.jsx
src/components/EmployeePerformanceDashboard.jsx
src/components/EmptyState.jsx
src/components/EnhancedFolioManager.jsx
src/components/ExpenseSummaryCard.jsx
src/components/ForecastGraph.jsx
src/components/GuestAlerts.jsx
src/components/GuestPreferences.jsx
src/components/GuestProfileComplete.jsx
src/components/GuestSatisfactionTrends.jsx
src/components/HousekeepingMobileEnhancements.jsx
src/components/HousekeepingTaskTiming.jsx
src/components/InventoryMovements.jsx
src/components/LazyImage.jsx
src/components/LostFoundWorkflow.jsx
src/components/LoyaltyTierBenefitsManager.jsx
src/components/MaintenanceCalendar.jsx
src/components/MaintenanceReports.jsx
src/components/MarketSegmentChart.jsx
src/components/MessagingModuleAdvanced.jsx
src/components/MetricDetailModal.jsx
src/components/ModuleCard.jsx
src/components/MultiPeriodRateManager.jsx
src/components/NotificationCenter.jsx
src/components/OTACancellationRate.jsx
src/components/OTAReservationDetails.jsx
src/components/OutletSalesChart.jsx
src/components/POSAutoPostSettings.jsx
src/components/POSEnhancements.jsx
src/components/POSManualQRPost.jsx
src/components/PassportScanOCR.jsx
src/components/PickupPaceChart.jsx
src/components/QRMaintenanceScanner.jsx
src/components/QRRoomAccess.jsx
src/components/RateTooltip.jsx
src/components/RejectBookingModal.jsx
src/components/RevenueBreakdownChart.jsx
src/components/RevenueManagementAdvanced.jsx
src/components/ReviewSentimentAnalysis.jsx
src/components/RoomAssignment.jsx
src/components/RoomNotesManager.jsx
src/components/SLAConfigCard.jsx
src/components/SecurityGDPRModule.jsx
src/components/SecurityLogs.jsx
src/components/ShiftMetrics.jsx
src/components/SplitFolioDialog.jsx
src/components/StopSaleManager.jsx
src/components/TaskKanbanBoard.jsx
src/components/TeamPerformance.jsx
src/components/TrendChart.jsx
src/components/WalkInBookingQuick.jsx
src/components/calendar/CalendarDialogs.jsx
src/components/calendar/CalendarWidgets.jsx
src/components/invoice/InvoiceFormDialog.jsx
src/components/pms/BanquetEventOrder.jsx
src/components/pms/RoomTimelineView.jsx
src/components/shared/AuditTimelineSummaryCard.jsx
src/components/shared/ModuleErrorBoundary.jsx
src/components/shared/OperationalWidgets.jsx
src/config/roles.jsx
src/constants/colors.jsx
src/hooks/useMobileOptimization.jsx
src/hooks/useOperationalSocket.jsx
src/hooks/usePMSData.jsx
src/hooks/useRealTimeData.jsx
src/modules/admin/index.jsx
src/modules/finance/index.jsx
src/modules/frontdesk/index.jsx
src/modules/housekeeping/index.jsx
src/modules/messaging/index.jsx
src/modules/mobile/index.jsx
src/modules/pos_fnb/index.jsx
src/modules/rms/index.jsx
src/modules/runtime-health/index.jsx
src/pages/rate-manager/ProviderToggle.jsx
src/setupTests.jsx
src/utils/apiUtils.jsx
src/utils/performanceMonitor.jsx
src/utils/performanceUtils.jsx
```

## Kullanılmayan export'lar (19) — kolay temizlik

Tek dosyada export kaldırmak güvenli:

```
src/api/axios.js: BACKEND_URL
src/config/axiosConfig.js: BACKEND_URL  ← duplicate konstant!
src/components/IdPhotoViewerButton.jsx: ID_PHOTO_REASON_OPTIONS, canUserViewIdPhoto
src/components/UpgradeBanner.jsx: LockedBadge, default
src/components/cost/CostAnalyticsView.jsx: CATEGORY_KEYS
src/config/navItems.jsx: PMS_LITE_NAV_KEYS
src/context/CurrencyContext.jsx: default
src/hooks/use-toast.jsx: reducer, toast
src/i18n.jsx: default
src/lib/currency.js: localeForCurrency
src/lib/queryClient.jsx: queryKeys, invalidateQueries, prefetchQueries
src/pages/admin/tenantConstants.jsx: tierRank
src/pages/calendar/calendarHelpers.jsx: isRoomOccupiedOnDay, getOTAInfo,
                                          getSourceColor, turkishDayNames,
                                          getHeatmapColor
src/pages/reports/GuestSection.jsx: default
src/utils/authRoles.js: isSuperAdmin, hasRole, hasGrantedPermission
src/utils/cacheUtils.jsx: clearCache, clearAllCache, clearExpiredCache,
                           getCacheStats
src/utils/lazyLoad.jsx: lazyLoadComponent, lazyWithRetry, preloadComponent,
                         LoadingSkeleton, DashboardLoadingSkeleton
```

`BACKEND_URL` iki dosyada duplicate — biri kaldırılmalı (P0).

## Sonraki adım

```bash
cd frontend
yarn knip                  # rapor
yarn knip --fix --allow-remove-files   # OTOMATİK SİL — yapma! manuel önerilir
yarn analyze               # bundle baseline
# 5-10 dosya temizle
yarn build && yarn e2e     # smoke yeşil mi
yarn analyze               # delta ölç
```
