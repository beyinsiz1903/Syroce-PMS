import {
  GDPRCompliance, EncryptionManagementPage, CentralOfficeDashboard,
  CentralPricingManager, CrossPropertyGuests, MLDashboard, AdminTenants,
  AdminVendors, QuickIdSettings, RoomQrCodes, RoomRequests, ModuleReport,
  AdminLeads, GovernancePanel, UserRoleManager, TenantUsers, HousekeepingDashboard,
  POSDashboard, FeaturesShowcase, WebhookOutboxAdmin, EarlyWarningDashboard,
  ModuleDiscovery, IntegrationCredentials, IntegrationsOverview, CapXIntegration,
  RnlAutoResolveRuns, RnlDuplicates, SiteContentEditor, VoiceNumberMapping,
  AutonomousCollectionJobs, PhysicalSecurityDashboard, ContactCenterDashboard,
} from "./lazyPages";

const CALL_CENTER_ROLES = ["call_center_agent", "supervisor", "admin", "super_admin"];

export function securityAdminRoutes({ p, pa, pm }) {
  // Route-section unit tests exercise unrelated entries with only the generic
  // factories. Keep that lightweight contract intact while the application
  // always supplies `pm` for the entitlement-aware Call Center route.
  const moduleRoute = pm || ((Component, _moduleKey, extra, opts = {}) => ({
    ...p(Component, extra),
    allowedRoles: opts.allowedRoles,
  }));

  return [
    // ── Security & Compliance ──────────────────────────
    { path: "/app/physical-security", ...pa(PhysicalSecurityDashboard), wrapLayout: true, layoutModule: "physical_security" },
    { path: "/security-center", type: "redirect", to: "/security?tab=center" },
    { path: "/app/güvenlik", type: "redirect", to: "/security?tab=monitor" },
    { path: "/gdpr-compliance", ...moduleRoute(GDPRCompliance, null, {}, { allowedRoles: ["admin", "super_admin", "general_manager", "gdpr_officer"] }), wrapLayout: true },
    { path: "/encryption-management", ...pa(EncryptionManagementPage), wrapLayout: true, layoutModule: "encryption_management" },
    { path: "/central-office", ...p(CentralOfficeDashboard), wrapLayout: true },
    { path: "/central-pricing", ...p(CentralPricingManager) },
    { path: "/cross-property-guests", ...p(CrossPropertyGuests), wrapLayout: true },
    { path: "/ml-dashboard", ...p(MLDashboard), wrapLayout: true },

    // ── Admin ──────────────────────────────────────────
    { path: "/admin/otel-kullanicilari", ...p(TenantUsers), wrapLayout: true, layoutModule: "tenant_users" },
    { path: "/admin/tenants", ...pa(AdminTenants), wrapLayout: true, layoutModule: "admin-tenants" },
    { path: "/admin/vendors", ...pa(AdminVendors), wrapLayout: true, layoutModule: "admin_vendors" },
    { path: "/admin/quick-id", ...pa(QuickIdSettings), wrapLayout: true, layoutModule: "quick_id_settings" },
    { path: "/admin/voice-numbers", ...p(VoiceNumberMapping), wrapLayout: true, layoutModule: "voice-number-mapping" },
    { path: "/app/call-center", ...moduleRoute(ContactCenterDashboard, "contact_center", {}, { allowedRoles: CALL_CENTER_ROLES }), wrapLayout: true, layoutModule: "contact-center" },
    { path: "/admin/contact-center", type: "redirect", to: "/app/call-center" },
    { path: "/admin/room-qr-codes", ...p(RoomQrCodes), wrapLayout: true, layoutModule: "room_qr_codes" },
    { path: "/app/room-requests", ...p(RoomRequests), wrapLayout: true, layoutModule: "room_qr_requests" },
    { path: "/admin/module-report", ...pa(ModuleReport), wrapLayout: true, layoutModule: "admin-module-report" },
    { path: "/app/admin/leads", ...pa(AdminLeads), wrapLayout: true, layoutModule: "admin-leads" },
    { path: "/admin/governance", ...pa(GovernancePanel), wrapLayout: true, layoutModule: "governance" },
    { path: "/admin/user-roles", ...pa(UserRoleManager), wrapLayout: true, layoutModule: "user-role-manager" },
    { path: "/admin/housekeeping", ...pa(HousekeepingDashboard), wrapLayout: true, layoutModule: "housekeeping" },
    { path: "/admin/pos", ...pa(POSDashboard), wrapLayout: true, layoutModule: "pos" },
    { path: "/admin/features", ...pa(FeaturesShowcase), wrapLayout: true },
    { path: "/admin/webhook-outbox", ...pa(WebhookOutboxAdmin), wrapLayout: true, layoutModule: "webhook-outbox-admin" },
    { path: "/admin/early-warning", ...pa(EarlyWarningDashboard), wrapLayout: true, layoutModule: "early_warning_dashboard" },
    { path: "/admin/module-discovery", ...pa(ModuleDiscovery), wrapLayout: true, layoutModule: "module-discovery" },
    { path: "/admin/integration-credentials", ...pa(IntegrationCredentials), wrapLayout: true, layoutModule: "integration-credentials" },
    { path: "/admin/integrations-overview", ...pa(IntegrationsOverview), wrapLayout: true, layoutModule: "integrations_overview" },
    { path: "/admin/capx-integration", ...pa(CapXIntegration), wrapLayout: true, layoutModule: "capx-integration" },
    { path: "/admin/rnl-auto-resolve-runs", ...pa(RnlAutoResolveRuns), wrapLayout: true, layoutModule: "rnl-auto-resolve-runs" },
    { path: "/admin/rnl-duplicates", ...pa(RnlDuplicates), wrapLayout: true, layoutModule: "rnl-duplicates" },
    { path: "/admin/autonomous-collection", ...pa(AutonomousCollectionJobs), wrapLayout: true, layoutModule: "autonomous-collection" },
    { path: "/admin/site-content", ...pa(SiteContentEditor), wrapLayout: true, layoutModule: "site-content" },
    { path: "/admin/cost", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/app/cost-management", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/cost-management", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/admin/gm-enhanced", type: "redirect", to: "/executive" },
  ];
}
