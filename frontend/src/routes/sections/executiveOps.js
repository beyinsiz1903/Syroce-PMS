import {
  KonaklamaVergisiModule, HelpCenter, MevzuatRaporlari, ExecutiveDashboard,
  AuditTimelinePage, UrgentMessageReportPage, RecalledMessagesReportPage,
  IdPhotoViewReportPage, IdPhotoAdminPage, UrgentPermissionAdminPage,
  PilotReadinessPage, IncidentDashboardPage, GoLiveDashboardPage,
  ProductionRolloutPage, SoakTestDashboard, SystemPerformanceMonitor,
  LogViewer, NetworkTestTools,
} from "./lazyPages";

export function executiveOpsRoutes({ p, pm }) {
  return [
    // ── Executive & GM ─────────────────────────────────
    { path: "/app/konaklama-vergisi", ...pm(KonaklamaVergisiModule, "invoices"), wrapLayout: true, layoutModule: "konaklama-vergisi" },
    { path: "/app/help", ...p(HelpCenter), wrapLayout: true, layoutModule: "help" },
    { path: "/app/mevzuat-raporlari", ...pm(MevzuatRaporlari, "basic_reporting"), wrapLayout: true, layoutModule: "mevzuat-raporlari" },
    { path: "/executive", ...pm(ExecutiveDashboard, "gm_dashboards") },
    { path: "/gm/enhanced", type: "redirect", to: "/executive" },
    { path: "/gm-classic", type: "redirect", to: "/app/dashboard" },

    // ── Ops & Phases ───────────────────────────────────
    { path: "/audit-timeline", ...p(AuditTimelinePage, {}), wrapLayout: true, layoutModule: "audit-timeline" },
    { path: "/urgent-message-report", ...p(UrgentMessageReportPage, {}), wrapLayout: true, layoutModule: "urgent-message-report" },
    { path: "/recalled-messages-report", ...p(RecalledMessagesReportPage, {}), wrapLayout: true, layoutModule: "recalled_messages_report" },
    { path: "/id-photo-view-report", ...p(IdPhotoViewReportPage, {}), wrapLayout: true, layoutModule: "id-photo-view-report" },
    { path: "/id-photo-admin", ...p(IdPhotoAdminPage, {}), wrapLayout: true, layoutModule: "id-photo-admin" },
    { path: "/admin/urgent-permissions", ...p(UrgentPermissionAdminPage, {}), wrapLayout: true, layoutModule: "urgent_permission_admin" },
    { path: "/pilot-readiness", ...p(PilotReadinessPage, {}) },
    { path: "/incident-dashboard", ...p(IncidentDashboardPage, {}) },
    { path: "/golive-dashboard", ...p(GoLiveDashboardPage, {}) },
    { path: "/production-rollout", ...p(ProductionRolloutPage, {}) },
    { path: "/soak-test", ...p(SoakTestDashboard, {}) },

    // ── System Tools ───────────────────────────────────
    { path: "/system/performance", ...p(SystemPerformanceMonitor) },
    { path: "/system/logs", ...p(LogViewer) },
    { path: "/system/network", ...p(NetworkTestTools) },
  ];
}
