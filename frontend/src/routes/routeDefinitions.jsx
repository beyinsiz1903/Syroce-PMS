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
 */
import React from "react";

import {
  AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal,
} from "./sections/lazyPages";
import ModuleScopeBoundary from "./ModuleScopeBoundary";
import { moduleScopesForRoute } from "@/utils/moduleAccess";

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
import { moduleWorkspaceRoutes } from "./sections/moduleWorkspaces";

// Public re-exports for App.jsx (kept stable across the split).
export { AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal };

function applyUserModuleScope(routeConfig) {
  const scopes = moduleScopesForRoute(routeConfig);
  if (!scopes.length || routeConfig.type === "public" || routeConfig.type === "redirect") {
    return routeConfig;
  }

  const OriginalComponent = routeConfig.component;
  const ScopedComponent = (props) => (
    <ModuleScopeBoundary user={props.user} scopes={scopes}>
      <OriginalComponent {...props} />
    </ModuleScopeBoundary>
  );
  ScopedComponent.displayName = `ModuleScoped(${OriginalComponent?.displayName || OriginalComponent?.name || "Route"})`;

  return {
    ...routeConfig,
    component: ScopedComponent,
    moduleScopes: scopes,
  };
}

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

  const routes = [
    ...publicRoutes(helpers),
    ...coreOperationsRoutes(helpers),
    ...moduleWorkspaceRoutes(helpers),
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

  return routes.map(applyUserModuleScope);
}
