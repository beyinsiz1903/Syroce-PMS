import React from "react";
import { useLocation } from "react-router-dom";
import NotAvailable from "@/pages/NotAvailable";
import { normalizeFeatures } from "@/utils/featureFlags";

// PMS Lite için izinli path prefix'leri
const PMS_LITE_ALLOWED_PREFIXES = [
  "/app/dashboard",
  "/app/pms",
  "/app/reservation-calendar",
  "/app/bookings",
  "/app/rooms",
  "/app/guests",
  "/app/reports",
  "/app/raporlar",
  "/app/settings",
];

// Path -> moduleKey mapping for module-based access control
const PATH_MODULE_MAP = {
  "/app/invoices": "invoices",
  "/app/cost-management": "cost_management",
  "/app/channel-manager": "channel_manager",
  "/app/gelismis-raporlar": "reports",
  "/app/rms": "revenue_management",
  "/app/ai": "ai",
  "/app/marketplace": "marketplace",
  "/marketplace": "marketplace",
  "/app/loyalty": "loyalty_program",
  "/app/multi-property": "multi_property",
  "/app/group-sales": "group_sales",
  "/app/sales-crm": "sales_crm",
};

// Paths that are always allowed (no module check needed)
const ALWAYS_ALLOWED = [
  "/app/dashboard",
  "/app/pms",
  "/app/reservation-calendar",
  "/app/raporlar",
  "/app/settings",
  "/app/bookings",
  "/app/rooms",
  "/app/guests",
  "/admin/",
  "/auth",
  "/reports/official-guest-list",
];

function isAllowedForLite(pathname) {
  return PMS_LITE_ALLOWED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
}

function isAlwaysAllowed(pathname) {
  return ALWAYS_ALLOWED.some(
    (p) => pathname === p || pathname.startsWith(p)
  );
}

function getRequiredModule(pathname) {
  for (const [path, moduleKey] of Object.entries(PATH_MODULE_MAP)) {
    if (pathname === path || pathname.startsWith(path + "/")) {
      return moduleKey;
    }
  }
  return null;
}

export default function PlanRouteGuard({ tenant, user, children }) {
  const location = useLocation();

  if (!tenant) return children;

  // Super admin, admin, and demo users bypass all plan/module restrictions
  const userRole = user?.role;
  const userRoles = Array.isArray(user?.roles) ? user.roles : [];
  if (
    userRole === "super_admin" || userRole === "admin" || userRole === "owner" || userRole === "demo_manager_readonly" ||
    userRoles.includes("super_admin") || userRoles.includes("admin") || userRoles.includes("owner") || userRoles.includes("demo_manager_readonly")
  ) {
    return children;
  }

  const plan =
    tenant.subscription_plan ||
    tenant.plan ||
    tenant.subscription_tier ||
    "core_small_hotel";

  const _features = normalizeFeatures(tenant.features || {});
  const modules = tenant.modules || {};

  // Enterprise plan has access to all modules
  if (plan === "enterprise" || plan === "professional") {
    return children;
  }

  // PMS Lite plan restriction
  if (plan === "pms_lite") {
    if (!isAllowedForLite(location.pathname)) {
      return <NotAvailable />;
    }
  }

  // Always allowed paths
  if (isAlwaysAllowed(location.pathname)) {
    return children;
  }

  // Module-based access control
  const requiredModule = getRequiredModule(location.pathname);
  if (requiredModule) {
    const isEnabled = modules[requiredModule] === true;
    if (!isEnabled) {
      return <NotAvailable />;
    }
  }

  return children;
}
