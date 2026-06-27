import {
  Dashboard, ProfilePage, PCIComplianceDashboard, XchangePage, MicePage,
  ProcurementPage, InventoryProcurementGuide, MailingPage, ModuleStorePage,
  AfsadakatLauncher, OnboardingWizard, AIEnhancedPMS, AIModule, PMSModule,
  PMSOperationalDashboard, FolioDetailView, HousekeepingStatusPage,
  ShiftHandoverPage, EarlyLatePricingSettings, EodReportPage, WalkinPage,
  RoomMapPage, WakeUpCallsPage, LostFoundPage, MinibarPage, GuestJourney,
  OperationalEventDashboard, MigrationObservabilityPage, IntegrationHub,
  AdminControlPanel, HousekeepingDashboard, POSDashboard, POSWaiterTerminal, POSExtensions, FeaturesShowcase,
} from "./lazyPages";

export function coreOperationsRoutes({ p, pa, pm, modules }) {
  return [
    { path: "/app/dashboard", ...p(Dashboard, { modules }), wrapLayout: true, layoutModule: "dashboard" },
    { path: "/app/profile", ...p(ProfilePage), wrapLayout: true, layoutModule: "profile" },
    { path: "/profile", ...p(ProfilePage), wrapLayout: true, layoutModule: "profile" },
    { path: "/app/compliance/pci", ...p(PCIComplianceDashboard), wrapLayout: true, layoutModule: "pci-compliance" },
    { path: "/app/xchange", ...p(XchangePage), wrapLayout: true, layoutModule: "xchange" },
    { path: "/app/mice", ...pm(MicePage, "mice", undefined, { strict: true }), wrapLayout: true, layoutModule: "mice" },
    { path: "/app/procurement", ...p(ProcurementPage), wrapLayout: true, layoutModule: "procurement" },
    { path: "/app/stock-rehber", ...p(InventoryProcurementGuide), wrapLayout: true, layoutModule: "procurement" },
    { path: "/app/mailing", ...p(MailingPage), wrapLayout: true, layoutModule: "mailing" },
    { path: "/app/module-store", ...p(ModuleStorePage), wrapLayout: true, layoutModule: "module_store" },
    { path: "/module-store", ...p(ModuleStorePage), wrapLayout: true, layoutModule: "module_store" },
    { path: "/app/afsadakat", ...p(AfsadakatLauncher), wrapLayout: true, layoutModule: "afsadakat" },
    { path: "/app/onboarding", ...p(OnboardingWizard), wrapLayout: true, layoutModule: "onboarding" },
    { path: "/dashboard-simple", ...p(Dashboard, { modules }), wrapLayout: true, layoutModule: "dashboard" },
    { path: "/ai-pms", ...p(AIEnhancedPMS) },
    { path: "/app/ai", ...p(AIModule), wrapLayout: true, layoutModule: "ai" },
    { path: "/pms", type: "memory", targetPath: "/pms", ...p(PMSModule) },
    { path: "/app/pms", type: "memory", targetPath: "/app/pms", ...p(PMSModule) },
    { path: "/pms-operations", ...p(PMSOperationalDashboard), wrapLayout: true, layoutModule: "pms_operations" },
    { path: "/folio-detail", ...p(FolioDetailView), wrapLayout: true, layoutModule: "folio_detail" },
    { path: "/folio-detail/:folioId", ...p(FolioDetailView), wrapLayout: true, layoutModule: "folio_detail" },
    { path: "/housekeeping-status", ...p(HousekeepingStatusPage), wrapLayout: true, layoutModule: "housekeeping" },
    // M5 pilot (May 2026): Layout sarımı ProtectedRoute tarafından yapılır.
    // Bu route'lar `wrapLayout: true` flag'i ile işaretli; sayfa dosyaları
    // Layout import/sarımını kendi return'lerinden kaldırmıştır.
    { path: "/shift-handover", ...p(ShiftHandoverPage), wrapLayout: true, layoutModule: "shift_handover" },
    { path: "/settings/early-late-pricing", ...p(EarlyLatePricingSettings), wrapLayout: true, layoutModule: "early_late_pricing" },
    { path: "/eod-report", ...p(EodReportPage), wrapLayout: true, layoutModule: "eod_report" },
    { path: "/walkin", ...p(WalkinPage), wrapLayout: true, layoutModule: "walkin" },
    { path: "/room-map", ...p(RoomMapPage), wrapLayout: true, layoutModule: "room_map" },
    { path: "/wake-up-calls", ...p(WakeUpCallsPage), wrapLayout: true, layoutModule: "wake_up_calls" },
    { path: "/lost-found", ...p(LostFoundPage), wrapLayout: true, layoutModule: "lost_found" },
    { path: "/minibar", ...p(MinibarPage), wrapLayout: true, layoutModule: "minibar" },
    { path: "/guest-journey", ...p(GuestJourney), wrapLayout: true },
    { path: "/operational-events", ...p(OperationalEventDashboard), wrapLayout: true, layoutModule: "pms_operations" },
    { path: "/app/migration-observability", ...p(MigrationObservabilityPage), wrapLayout: true, layoutModule: "reports" },
    { path: "/app/integration-hub", ...pa(IntegrationHub), wrapLayout: true, layoutModule: "integration-hub" },
    { path: "/app/admin-control-panel", ...pa(AdminControlPanel), wrapLayout: true, layoutModule: "admin_control_panel" },

    // ── Core Operations (Dashboard module cards) ──────
    { path: "/housekeeping", ...p(HousekeepingDashboard), wrapLayout: true, layoutModule: "housekeeping" },
    { path: "/pos", ...p(POSDashboard), wrapLayout: true, layoutModule: "pos" },
    { path: "/pos/terminal", ...p(POSWaiterTerminal), wrapLayout: true, layoutModule: "pos" },
    { path: "/pos-extensions", ...p(POSExtensions), wrapLayout: true, layoutModule: "pos" },
    { path: "/features", ...p(FeaturesShowcase), wrapLayout: true },
  ];
}
