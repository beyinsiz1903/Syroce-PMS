/**
 * Route Definitions — Thin composer.
 *
 * Route configs live in `./sections/*.js`, organized by domain. Lazy page
 * components live in `./sections/lazyPages.js`. This file:
 *   1. Re-exports the public API used by App.jsx (named pages + getRouteConfigs).
 *   2. Builds the per-render helpers (`p`, `pa`, `pm`) and concatenates each
 *      section's route array in the original visual order.
 *
 * Types:
 *   "public"     — No auth required
 *   "protected"  — Auth required
 *   "module"     — Auth + module check required
 *   "feature"    — Auth + feature flag required
 *   "memory"     — Auth required, saves redirect path on failure
 *   "redirect"   — Static redirect to another path
 *
 * Adding a route:
 *   - Lazy import the page in `sections/lazyPages.js`.
 *   - Append the route entry to the relevant `sections/*.js` file.
 *   - No edit needed here unless adding a new section.
 *
 * Split history: Was a single 595-line file (May 2026) — split into 15
 * section files + central lazy registry to make domain ownership clear and
 * keep the composer thin.
 */
import {
  AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal,
} from "./sections/lazyPages";

import { publicRoutes } from "./sections/public";
import { coreOperationsRoutes } from "./sections/coreOperations";
import { reservationRoutes } from "./sections/reservations";
import { financeReportsRoutes } from "./sections/financeReports";
import { channelManagerRoutes } from "./sections/channelManager";
import { revenueRmsRoutes } from "./sections/revenueRms";
import { marketplaceLoyaltyRoutes } from "./sections/marketplaceLoyalty";
import { guestStaffRoutes } from "./sections/guestStaff";
import { frontdeskMaintenanceRoutes } from "./sections/frontdeskMaintenance";
import { mobileRoutes } from "./sections/mobile";
import { executiveOpsRoutes } from "./sections/executiveOps";
import { infrastructureRoutes } from "./sections/infrastructure";
import { hotelFeaturesAiRoutes } from "./sections/hotelFeaturesAi";
import { securityAdminRoutes } from "./sections/securityAdmin";
import { operaParityRoutes } from "./sections/operaParity";

// Public re-exports for App.jsx (kept stable across the split).
export { AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal };

/**
 * Build all route configs. Receives runtime state for conditional rendering.
 */
export function getRouteConfigs({ user, tenant, modules, isAuthenticated, onLogout, hasFeature }) {
  void isAuthenticated; void hasFeature; // reserved for future per-route gating

  const p = (Component, extra) => ({
    type: "protected",
    component: Component,
    props: { user, tenant, onLogout, ...extra },
  });

  // Protected + super-admin-only route. Non-super-admin users get redirected
  // to /app/dashboard in App.jsx regardless of URL (typed, bookmarked, etc.).
  const pa = (Component, extra) => ({
    type: "protected",
    component: Component,
    props: { user, tenant, onLogout, ...extra },
    requireSuperAdmin: true,
  });

  const pm = (Component, moduleKey, extra, opts = {}) => ({
    type: "module",
    moduleKey,
    strict: !!opts.strict,
    component: Component,
    props: { user, tenant, onLogout, modules, ...extra },
  });

  const helpers = { p, pa, pm, modules };

  return [
    ...publicRoutes(helpers),
    ...coreOperationsRoutes(helpers),
    ...reservationRoutes(helpers),
    ...financeReportsRoutes(helpers),
    ...channelManagerRoutes(helpers),
    ...revenueRmsRoutes(helpers),
    ...marketplaceLoyaltyRoutes(helpers),
    ...guestStaffRoutes(helpers),
    ...frontdeskMaintenanceRoutes(helpers),
    ...mobileRoutes(helpers),
    ...executiveOpsRoutes(helpers),
    ...infrastructureRoutes(helpers),
    ...hotelFeaturesAiRoutes(helpers),
    ...securityAdminRoutes(helpers),
    ...operaParityRoutes(helpers),
  ];
}
