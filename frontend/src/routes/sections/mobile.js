import {
  MultiPropertyDashboard, HousekeepingMobileApp, MobileDashboard,
  MobileHousekeeping, MobileFrontDesk, MobileFnB, MobileMaintenance,
  MobileFinance, MobileSecurity, MobileGM, MaintenancePriorityVisual,
  MobileOrderTracking, MobileInventory, MobileApprovals, SalesCRMMobile,
  RateManagementMobile, RevenueMobile, ChannelManagerMobile,
  CorporateContractsMobile, MobileLogViewer,
} from "./lazyPages";

export function mobileRoutes({ p, pm }) {
  return [
    // ── Multi Property ─────────────────────────────────
    { path: "/multi-property-dashboard", ...p(MultiPropertyDashboard) },
    { path: "/housekeeping-mobile-app", ...p(HousekeepingMobileApp) },

    // ── Mobile Routes ──────────────────────────────────
    { path: "/mobile", ...pm(MobileDashboard, "pms_mobile") },
    { path: "/mobile/housekeeping", ...pm(MobileHousekeeping, "mobile_housekeeping") },
    { path: "/mobile/frontdesk", ...p(MobileFrontDesk) },
    { path: "/mobile/fnb", ...p(MobileFnB) },
    { path: "/mobile/maintenance", ...p(MobileMaintenance) },
    { path: "/mobile/finance", ...p(MobileFinance) },
    { path: "/mobile/security", ...p(MobileSecurity) },
    { path: "/mobile/gm", ...p(MobileGM) },
    { path: "/mobile/maintenance/priority-visual", ...p(MaintenancePriorityVisual) },
    { path: "/mobile/order-tracking", ...p(MobileOrderTracking) },
    { path: "/mobile/inventory", ...p(MobileInventory) },
    { path: "/mobile/approvals", ...p(MobileApprovals) },
    { path: "/mobile/sales", ...p(SalesCRMMobile) },
    { path: "/mobile/rates", ...p(RateManagementMobile) },
    { path: "/mobile/revenue", ...pm(RevenueMobile, "mobile_revenue") },
    { path: "/mobile/channels", ...p(ChannelManagerMobile) },
    { path: "/mobile/corporate", ...p(CorporateContractsMobile) },
    { path: "/mobile/logs", ...p(MobileLogViewer) },
  ];
}
