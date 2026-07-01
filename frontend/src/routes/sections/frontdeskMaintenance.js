import {
  FrontdeskAuditChecklist, MaintenanceWorkOrders, MaintenanceAssets,
  MaintenancePlans,
} from "./lazyPages";

export function frontdeskMaintenanceRoutes({ p }) {
  return [
    { path: "/frontdesk/audit-checklist", ...p(FrontdeskAuditChecklist), wrapLayout: true, layoutModule: "pms" },
    { path: "/maintenance/work-orders", ...p(MaintenanceWorkOrders), wrapLayout: true, layoutModule: "maintenance" },
    { path: "/maintenance/assets", ...p(MaintenanceAssets), wrapLayout: true, layoutModule: "maintenance" },
    { path: "/maintenance/plans", ...p(MaintenancePlans), wrapLayout: true, layoutModule: "maintenance" },
  ];
}
