/**
 * Route Definitions — Centralized lazy imports and route configuration.
 * Each route is defined as a config object for the App router to consume.
 *
 * Types:
 *   "public"     — No auth required
 *   "protected"  — Auth required
 *   "module"     — Auth + module check required
 *   "feature"    — Auth + feature flag required
 *   "memory"     — Auth required, saves redirect path on failure
 */
import { lazy } from "react";

// ── Critical imports (loaded immediately) ──────────────────────────
import AuthPage from "@/pages/AuthPage";
import Dashboard from "@/pages/Dashboard";
import LandingPage from "@/pages/LandingPage";
import PrivacyPolicy from "@/pages/PrivacyPolicy";

// ── Lazy imports ───────────────────────────────────────────────────
const GMDashboard = lazy(() => import("@/pages/GMDashboard"));
const PMSModule = lazy(() => import("@/pages/PMSModule"));
const InvoiceModule = lazy(() => import("@/pages/InvoiceModule"));
const RMSModule = lazy(() => import("@/pages/RMSModule"));
const ChannelManagerModule = lazy(() => import("@/pages/ChannelManagerModule"));
const MappingManager = lazy(() => import("@/pages/MappingManager"));
const ReservationLineage = lazy(() => import("@/pages/ReservationLineage"));
const ReservationCalendar = lazy(() => import("@/pages/ReservationCalendar"));
const Settings = lazy(() => import("@/pages/Settings"));
const PendingAR = lazy(() => import("@/pages/PendingAR"));
const CityLedgerAccounts = lazy(() => import("@/pages/CityLedgerAccounts"));
const LoyaltyModule = lazy(() => import("@/pages/LoyaltyModule"));
const MarketplaceModule = lazy(() => import("@/pages/MarketplaceModule"));
const HotelInventory = lazy(() => import("@/pages/HotelInventory"));
const GuestPortal = lazy(() => import("@/pages/GuestPortal"));
const TemplateManager = lazy(() => import("@/pages/TemplateManager"));
const SelfCheckin = lazy(() => import("@/pages/SelfCheckin"));
const DigitalKey = lazy(() => import("@/pages/DigitalKey"));
const UpsellStore = lazy(() => import("@/pages/UpsellStore"));
const StaffMobileApp = lazy(() => import("@/pages/StaffMobileApp"));
const OTAMessagingHub = lazy(() => import("@/pages/OTAMessagingHub"));
const EFaturaModule = lazy(() => import("@/pages/EFaturaModule"));
const MessagingCenter = lazy(() => import("@/pages/MessagingCenter"));
const SalesModule = lazy(() => import("@/pages/SalesModule"));
const GroupReservations = lazy(() => import("@/pages/GroupReservations"));
const MultiPropertyDashboard = lazy(() => import("@/pages/MultiPropertyDashboard"));
const HousekeepingMobileApp = lazy(() => import("@/pages/HousekeepingMobileApp"));
const AIEnhancedPMS = lazy(() => import("@/pages/AIEnhancedPMS"));
const Reports = lazy(() => import("@/pages/Reports"));
const BasicReports = lazy(() => import("@/pages/BasicReports"));
const ReportBuilder = lazy(() => import("@/pages/ReportBuilder"));
const PmsLiteLanding = lazy(() => import("@/pages/PmsLiteLanding"));
const AdminLeads = lazy(() => import("@/pages/AdminLeads"));
const GovernancePanel = lazy(() => import("@/pages/GovernancePanel"));
const NoShowAnalytics = lazy(() => import("@/pages/NoShowAnalytics"));
const OfficialGuestList = lazy(() => import("@/pages/OfficialGuestList"));
const MobileDashboard = lazy(() => import("@/pages/MobileDashboard"));
const MobileHousekeeping = lazy(() => import("@/pages/MobileHousekeeping"));
const MobileFrontDesk = lazy(() => import("@/pages/MobileFrontDesk"));
const MobileFnB = lazy(() => import("@/pages/MobileFnB"));
const MobileMaintenance = lazy(() => import("@/pages/MobileMaintenance"));
const MobileFinance = lazy(() => import("@/pages/MobileFinance"));
const MobileSecurity = lazy(() => import("@/pages/MobileSecurity"));
const MobileGM = lazy(() => import("@/pages/MobileGM"));
const MobileOrderTracking = lazy(() => import("@/pages/MobileOrderTracking"));
const MobileInventory = lazy(() => import("@/pages/MobileInventory"));
const MobileApprovals = lazy(() => import("@/pages/MobileApprovals"));
const ExecutiveDashboard = lazy(() => import("@/pages/ExecutiveDashboard"));
const GMEnhancedDashboard = lazy(() => import("@/pages/GMEnhancedDashboard"));
const SalesCRMMobile = lazy(() => import("@/pages/SalesCRMMobile"));
const SimpleAdminPanel = lazy(() => import("@/pages/SimpleAdminPanel"));
const RateManagementMobile = lazy(() => import("@/pages/RateManagementMobile"));
const RevenueMobile = lazy(() => import("@/pages/RevenueMobile"));
const ChannelManagerMobile = lazy(() => import("@/pages/ChannelManagerMobile"));
const CorporateContractsMobile = lazy(() => import("@/pages/CorporateContractsMobile"));
const MigrationObservabilityPage = lazy(() => import("@/pages/MigrationObservabilityPage"));
const SystemPerformanceMonitor = lazy(() => import("@/pages/SystemPerformanceMonitor"));
const LogViewer = lazy(() => import("@/pages/LogViewer"));
const MobileLogViewer = lazy(() => import("@/pages/MobileLogViewer"));
const NetworkTestTools = lazy(() => import("@/pages/NetworkTestTools"));
const MaintenancePriorityVisual = lazy(() => import("@/pages/MaintenancePriorityVisual"));
const CostManagement = lazy(() => import("@/pages/CostManagement"));
const FeaturesShowcase = lazy(() => import("@/pages/FeaturesShowcase"));
const HousekeepingDashboard = lazy(() => import("@/pages/HousekeepingDashboard"));
const POSDashboard = lazy(() => import("@/pages/POSDashboard"));
const AdminTenants = lazy(() => import("@/pages/AdminTenants"));
const ModuleReport = lazy(() => import("@/pages/ModuleReport"));
const UserRoleManager = lazy(() => import("@/pages/UserRoleManager"));
const AIModule = lazy(() => import("@/pages/AIModule"));
const OnlineCheckin = lazy(() => import("@/pages/OnlineCheckin"));
const FlashReport = lazy(() => import("@/pages/FlashReport"));
const GroupSales = lazy(() => import("@/pages/GroupSales"));
const VIPManagement = lazy(() => import("@/pages/VIPManagement"));
const SalesCRM = lazy(() => import("@/pages/SalesCRM"));
const ServiceRecovery = lazy(() => import("@/pages/ServiceRecovery"));
const SpaWellness = lazy(() => import("@/pages/SpaWellness"));
const MeetingEvents = lazy(() => import("@/pages/MeetingEvents"));
const AIChatbot = lazy(() => import("@/pages/AIChatbot"));
const DynamicPricing = lazy(() => import("@/pages/DynamicPricing"));
const ReputationCenter = lazy(() => import("@/pages/ReputationCenter"));
const MultiProperty = lazy(() => import("@/pages/MultiProperty"));
const PaymentGateway = lazy(() => import("@/pages/PaymentGateway"));
const AdvancedLoyalty = lazy(() => import("@/pages/AdvancedLoyalty"));
const GDSIntegration = lazy(() => import("@/pages/GDSIntegration"));
const StaffManagement = lazy(() => import("@/pages/StaffManagement"));
const GuestJourney = lazy(() => import("@/pages/GuestJourney"));
const ArrivalList = lazy(() => import("@/pages/ArrivalList"));
const AIWhatsAppConcierge = lazy(() => import("@/pages/AIWhatsAppConcierge"));
const PredictiveAnalytics = lazy(() => import("@/pages/PredictiveAnalytics"));
const AgencyRequests = lazy(() => import("@/pages/AgencyRequests"));
const AgencyManagement = lazy(() => import("@/pages/AgencyManagement"));
const AgencyContentDistribution = lazy(() => import("@/pages/AgencyContentDistribution"));
const AgencyPortalDashboard = lazy(() => import("@/pages/AgencyPortalDashboard"));
const SocialMediaRadar = lazy(() => import("@/pages/SocialMediaRadar"));
const RevenueAutopilot = lazy(() => import("@/pages/RevenueAutopilot"));
const HRComplete = lazy(() => import("@/pages/HRComplete"));
const FnBComplete = lazy(() => import("@/pages/FnBComplete"));
const FnbBeoGenerator = lazy(() => import("@/pages/FnbBeoGenerator"));
const KitchenDisplay = lazy(() => import("@/pages/KitchenDisplay"));
const NightAuditLogs = lazy(() => import("@/pages/NightAuditLogs"));
const NightAuditDashboard = lazy(() => import("@/pages/NightAuditDashboard"));
const PMSOperationalDashboard = lazy(() => import("@/pages/PMSOperationalDashboard"));
const FolioDetailView = lazy(() => import("@/pages/FolioDetailView"));
const RevenueEngineDashboard = lazy(() => import("@/pages/RevenueEngineDashboard"));
const OperationalEventDashboard = lazy(() => import("@/pages/OperationalEventDashboard"));
const GuestJourneyDashboard = lazy(() => import("@/pages/GuestJourneyDashboard"));
const PlatformScalingDashboard = lazy(() => import("@/pages/PlatformScalingDashboard"));
const EnterpriseLiveDashboard = lazy(() => import("@/pages/EnterpriseLiveDashboard"));
const DataIntelligenceDashboard = lazy(() => import("@/pages/DataIntelligenceDashboard"));
const MessagingDashboard = lazy(() => import("@/pages/MessagingDashboard"));
const MLSchedulerDashboard = lazy(() => import("@/pages/MLSchedulerDashboard"));
const RevenueAutopilotDashboard = lazy(() => import("@/pages/RevenueAutopilotDashboard"));
const AnalyticsExportDashboard = lazy(() => import("@/pages/AnalyticsExportDashboard"));
const FrontdeskAuditChecklist = lazy(() => import("@/pages/FrontdeskAuditChecklist"));
const CorporateContractsDashboard = lazy(() => import("@/pages/CorporateContractsDashboard"));
const MaintenanceWorkOrders = lazy(() => import("@/pages/MaintenanceWorkOrders"));
const MaintenanceAssets = lazy(() => import("@/pages/MaintenanceAssets"));
const MaintenancePlans = lazy(() => import("@/pages/MaintenancePlans"));
const SecurityCenter = lazy(() => import("@/pages/SecurityCenter"));
const SecurityDashboard = lazy(() => import("@/pages/SecurityDashboard"));
const GDPRCompliance = lazy(() => import("@/pages/GDPRCompliance"));
const CentralOfficeDashboard = lazy(() => import("@/pages/CentralOfficeDashboard"));
const CentralPricingManager = lazy(() => import("@/pages/CentralPricingManager"));
const CrossPropertyGuests = lazy(() => import("@/pages/CrossPropertyGuests"));
const MLDashboard = lazy(() => import("@/pages/MLDashboard"));
const IntegrationHub = lazy(() => import("@/pages/IntegrationHub"));
const AdminControlPanel = lazy(() => import("@/pages/AdminControlPanel"));
const DataPipelineDashboard = lazy(() => import("@/pages/DataPipelineDashboard"));
const EventBusDashboard = lazy(() => import("@/pages/EventBusDashboard"));
const ObservabilityDashboard = lazy(() => import("@/pages/ObservabilityDashboard"));
const SecurityHardeningDashboard = lazy(() => import("@/pages/SecurityHardeningDashboard"));
const SystemHealthDashboard = lazy(() => import("@/pages/SystemHealthDashboard"));
const RuntimeInfrastructureDashboard = lazy(() => import("@/pages/RuntimeInfrastructureDashboard"));
const InfraHardeningDashboard = lazy(() => import("@/pages/InfraHardeningDashboard"));
const ProductionGoLiveDashboard = lazy(() => import("@/pages/ProductionGoLiveDashboard"));
const AuditTimelinePage = lazy(() => import("@/pages/AuditTimelinePage"));
const PilotReadinessPage = lazy(() => import("@/pages/PilotReadinessPage"));
const IncidentDashboardPage = lazy(() => import("@/pages/IncidentDashboardPage"));
const GoLiveDashboardPage = lazy(() => import("@/pages/GoLiveDashboardPage"));
const ProductionRolloutPage = lazy(() => import("@/pages/ProductionRolloutPage"));
const SoakTestDashboard = lazy(() => import("@/pages/SoakTestDashboard"));
const HotelRunnerIntegration = lazy(() => import("@/pages/HotelRunnerIntegration"));
const HRv2OpsDashboard = lazy(() => import("@/pages/HRv2OpsDashboard"));
const ExelyIntegration = lazy(() => import("@/pages/ExelyIntegration"));
const ChannelConnections = lazy(() => import("@/pages/ChannelConnections"));
const ARIPushDashboard = lazy(() => import("@/pages/ARIPushDashboard"));
const RateManager = lazy(() => import("@/pages/RateManager"));
const HRRateManager = lazy(() => import("@/pages/HRRateManager"));
const UnifiedRateManager = lazy(() => import("@/pages/UnifiedRateManager"));
const WireFailureDashboard = lazy(() => import("@/pages/WireFailureDashboard"));
const PIIStrictModeDashboard = lazy(() => import("@/pages/PIIStrictModeDashboard"));
const DataModelDashboard = lazy(() => import("@/pages/DataModelDashboard"));
const LockdownDashboard = lazy(() => import("@/pages/LockdownDashboard"));
const OperatorIncidentPanel = lazy(() => import("@/pages/OperatorIncidentPanel"));
const RuntimeCockpitPage = lazy(() => import("@/pages/RuntimeCockpitPage"));
const ControlPlane = lazy(() => import("@/pages/ControlPlane"));
const GroupBookingsPage = lazy(() => import("@/pages/GroupBookings"));
const DepositTrackingPage = lazy(() => import("@/pages/DepositTracking"));
const HousekeepingStatusPage = lazy(() => import("@/pages/HousekeepingStatusPage"));
const WakeUpCallsPage = lazy(() => import("@/pages/WakeUpCallsPage"));
const LostFoundPage = lazy(() => import("@/pages/LostFoundPage"));
const GroupFolioPage = lazy(() => import("@/pages/GroupFolioPage"));
const EnhancedGMDashboard = lazy(() => import("@/pages/EnhancedGMDashboard"));
const RoomMappingWizard = lazy(() => import("@/pages/RoomMappingWizard"));

// ── Exported components for direct access ──────────────────────────
export {
  AuthPage, Dashboard, LandingPage, PrivacyPolicy, GuestPortal,
};

/**
 * Build all route configs. Receives runtime state for conditional rendering.
 */
export function getRouteConfigs({ user, tenant, modules, isAuthenticated, onLogout, hasFeature }) {
  const p = (Component, extra) => ({
    type: "protected",
    component: Component,
    props: { user, tenant, onLogout, ...extra },
  });

  const pm = (Component, moduleKey, extra) => ({
    type: "module",
    moduleKey,
    component: Component,
    props: { user, tenant, onLogout, modules, ...extra },
  });

  return [
    // ── Public ──────────────────────────────────────────
    { path: "/landing", type: "public", component: LandingPage },
    { path: "/privacy-policy", type: "public", component: PrivacyPolicy },
    { path: "/gizlilik", type: "public", component: PrivacyPolicy },
    { path: "/pms-lite", type: "public", component: PmsLiteLanding },
    { path: "/agency-portal", type: "public", component: AgencyPortalDashboard },
    { path: "/system-status", type: "public", component: SimpleAdminPanel },

    // ── Core Operations ────────────────────────────────
    { path: "/app/dashboard", ...p(Dashboard, { modules }) },
    { path: "/dashboard-simple", ...p(Dashboard, { modules }) },
    { path: "/ai-pms", ...p(AIEnhancedPMS) },
    { path: "/app/ai", ...p(AIModule) },
    { path: "/pms", type: "memory", targetPath: "/pms", ...p(PMSModule) },
    { path: "/app/pms", type: "memory", targetPath: "/app/pms", ...p(PMSModule) },
    { path: "/pms-operations", ...p(PMSOperationalDashboard) },
    { path: "/folio-detail", ...p(FolioDetailView) },
    { path: "/folio-detail/:folioId", ...p(FolioDetailView) },
    { path: "/housekeeping-status", ...p(HousekeepingStatusPage) },
    { path: "/wake-up-calls", ...p(WakeUpCallsPage) },
    { path: "/lost-found", ...p(LostFoundPage) },
    { path: "/guest-journey", ...p(GuestJourney) },
    { path: "/operational-events", ...p(OperationalEventDashboard) },
    { path: "/app/migration-observability", ...p(MigrationObservabilityPage) },
    { path: "/app/integration-hub", ...p(IntegrationHub) },
    { path: "/app/admin-control-panel", ...p(AdminControlPanel) },

    // ── Reservations ───────────────────────────────────
    { path: "/reservation-calendar", ...p(ReservationCalendar) },
    { path: "/app/reservation-calendar", ...p(ReservationCalendar) },
    { path: "/reservation-lineage", ...p(ReservationLineage) },
    { path: "/group-bookings-manage", ...p(GroupBookingsPage) },
    { path: "/deposit-tracking", ...p(DepositTrackingPage) },
    { path: "/group-folio", ...p(GroupFolioPage) },
    { path: "/no-show-analytics", ...p(NoShowAnalytics) },
    { path: "/group-reservations", ...p(GroupReservations) },
    { path: "/arrival-list", ...p(ArrivalList) },

    // ── Finance ────────────────────────────────────────
    { path: "/invoices", ...p(InvoiceModule) },
    { path: "/app/invoices", ...p(InvoiceModule) },
    { path: "/night-audit", ...p(NightAuditDashboard) },
    { path: "/night-audit/logs", ...p(NightAuditLogs) },
    { path: "/pending-ar", ...p(PendingAR) },
    { path: "/city-ledger", ...p(CityLedgerAccounts) },
    { path: "/efatura", ...p(EFaturaModule) },
    { path: "/e-fatura", ...p(EFaturaModule) },

    // ── Settings ───────────────────────────────────────
    { path: "/settings", ...p(Settings) },
    { path: "/app/settings", ...p(Settings) },

    // ── Channel Manager ────────────────────────────────
    { path: "/channel-connections", ...p(ChannelConnections) },
    { path: "/channel-manager", ...p(ChannelManagerModule) },
    { path: "/app/channel-manager", ...p(ChannelManagerModule) },
    { path: "/mapping-manager", ...p(MappingManager) },
    { path: "/room-mapping-wizard", ...p(RoomMappingWizard) },
    { path: "/hotelrunner", ...p(HotelRunnerIntegration) },
    { path: "/hrv2-ops", ...p(HRv2OpsDashboard) },
    { path: "/exely", ...p(ExelyIntegration) },
    { path: "/ari-push", ...p(ARIPushDashboard) },
    { path: "/rate-manager", ...p(RateManager) },
    { path: "/hr-rate-manager", ...p(HRRateManager) },
    { path: "/unified-rate-manager", ...p(UnifiedRateManager) },
    { path: "/wire-failures", ...p(WireFailureDashboard) },
    { path: "/data-model", ...p(DataModelDashboard) },
    { path: "/lockdown", ...p(LockdownDashboard) },
    { path: "/incidents", ...p(OperatorIncidentPanel) },
    { path: "/runtime-cockpit", ...p(RuntimeCockpitPage) },
    { path: "/control-plane", ...p(ControlPlane) },

    // ── Reports ────────────────────────────────────────
    { path: "/reports", ...p(Reports) },
    { path: "/app/reports", ...p(Reports) },
    { path: "/app/raporlar", ...p(BasicReports) },
    { path: "/app/gelismis-raporlar", ...p(Reports) },
    { path: "/reports/builder", ...p(ReportBuilder) },
    { path: "/app/rapor-olusturucu", ...p(ReportBuilder) },
    { path: "/reports/official-guest-list", ...p(OfficialGuestList) },
    { path: "/reports/corporate-contracts", ...p(CorporateContractsDashboard) },

    // ── Revenue & Analytics ────────────────────────────
    { path: "/revenue-engine", ...p(RevenueEngineDashboard) },
    { path: "/data-intelligence", ...p(DataIntelligenceDashboard) },
    { path: "/messaging-dashboard", ...p(MessagingDashboard) },
    { path: "/ml-scheduler", ...p(MLSchedulerDashboard) },
    { path: "/revenue-autopilot-v2", ...p(RevenueAutopilotDashboard) },
    { path: "/analytics-export", ...p(AnalyticsExportDashboard) },

    // ── RMS (feature-gated) ────────────────────────────
    { path: "/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },
    { path: "/app/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },

    // ── Marketplace (feature-gated) ────────────────────
    { path: "/marketplace", type: "feature", featureKey: "hidden_marketplace", ...p(MarketplaceModule) },
    { path: "/app/marketplace", ...p(MarketplaceModule) },

    // ── Loyalty & Inventory ────────────────────────────
    { path: "/loyalty", ...p(LoyaltyModule) },
    { path: "/hotel-inventory", ...p(HotelInventory) },
    { path: "/templates", ...p(TemplateManager) },

    // ── Guest Features ─────────────────────────────────
    { path: "/guest/checkin/:bookingId", ...p(SelfCheckin) },
    { path: "/guest/digital-key/:bookingId", ...p(DigitalKey) },
    { path: "/guest/upsell/:bookingId", ...p(UpsellStore) },

    // ── Staff & OTA ────────────────────────────────────
    { path: "/staff/mobile", ...p(StaffMobileApp) },
    { path: "/ota-messaging-hub", ...p(OTAMessagingHub) },
    { path: "/messaging-center", ...p(MessagingCenter) },
    { path: "/sales", ...p(SalesModule) },
    { path: "/agency-requests", ...p(AgencyRequests) },
    { path: "/agency-management", ...p(AgencyManagement) },
    { path: "/agency-content", ...p(AgencyContentDistribution) },

    // ── Frontdesk & Maintenance ────────────────────────
    { path: "/frontdesk/audit-checklist", ...p(FrontdeskAuditChecklist) },
    { path: "/maintenance/work-orders", ...p(MaintenanceWorkOrders) },
    { path: "/maintenance/assets", ...p(MaintenanceAssets) },
    { path: "/maintenance/plans", ...p(MaintenancePlans) },

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

    // ── Executive & GM ─────────────────────────────────
    { path: "/executive", ...pm(ExecutiveDashboard, "gm_dashboards") },
    { path: "/gm/enhanced", ...pm(GMEnhancedDashboard, "gm_dashboards") },
    { path: "/gm-classic", ...pm(GMDashboard, "gm_dashboards") },

    // ── Infrastructure ─────────────────────────────────
    { path: "/data-pipeline", ...p(DataPipelineDashboard) },
    { path: "/event-bus", ...p(EventBusDashboard) },
    { path: "/system-health", ...p(SystemHealthDashboard) },
    { path: "/observability", ...p(ObservabilityDashboard) },
    { path: "/security-hardening", ...p(SecurityHardeningDashboard) },
    { path: "/runtime-infrastructure", ...p(RuntimeInfrastructureDashboard) },
    { path: "/infra-hardening", ...p(InfraHardeningDashboard) },
    { path: "/production-golive", ...p(ProductionGoLiveDashboard) },
    { path: "/platform-scaling", ...p(PlatformScalingDashboard) },
    { path: "/enterprise-live", ...p(EnterpriseLiveDashboard) },
    { path: "/pii-strict-mode", ...p(PIIStrictModeDashboard) },

    // ── Ops & Phases ───────────────────────────────────
    { path: "/audit-timeline", ...p(AuditTimelinePage, {}) },
    { path: "/pilot-readiness", ...p(PilotReadinessPage, {}) },
    { path: "/incident-dashboard", ...p(IncidentDashboardPage, {}) },
    { path: "/golive-dashboard", ...p(GoLiveDashboardPage, {}) },
    { path: "/production-rollout", ...p(ProductionRolloutPage, {}) },
    { path: "/soak-test", ...p(SoakTestDashboard, {}) },

    // ── System Tools ───────────────────────────────────
    { path: "/system/performance", ...p(SystemPerformanceMonitor) },
    { path: "/system/logs", ...p(LogViewer) },
    { path: "/system/network", ...p(NetworkTestTools) },

    // ── 5-Star Hotel Features ──────────────────────────
    { path: "/online-checkin", ...p(OnlineCheckin) },
    { path: "/flash-report", ...p(FlashReport) },
    { path: "/group-sales", ...p(GroupSales) },
    { path: "/vip-management", ...p(VIPManagement) },
    { path: "/sales-crm", ...p(SalesCRM) },
    { path: "/service-recovery", ...p(ServiceRecovery) },
    { path: "/spa-wellness", ...p(SpaWellness) },
    { path: "/meeting-events", ...p(MeetingEvents) },
    { path: "/multi-property", ...p(MultiProperty) },
    { path: "/payment-gateway", ...p(PaymentGateway) },
    { path: "/advanced-loyalty", ...p(AdvancedLoyalty) },
    { path: "/gds-integration", ...p(GDSIntegration) },
    { path: "/staff-management", ...p(StaffManagement) },
    { path: "/hr-complete", ...p(HRComplete) },
    { path: "/fnb-complete", ...p(FnBComplete) },
    { path: "/fnb/beo-generator", ...p(FnbBeoGenerator) },
    { path: "/kitchen-display", ...p(KitchenDisplay) },

    // ── AI Module-gated ────────────────────────────────
    { path: "/ai-chatbot", ...pm(AIChatbot, "ai_chatbot") },
    { path: "/dynamic-pricing", ...pm(DynamicPricing, "ai_pricing") },
    { path: "/reputation-center", ...pm(ReputationCenter, "ai_reputation") },
    { path: "/ai-whatsapp-concierge", ...pm(AIWhatsAppConcierge, "ai_whatsapp") },
    { path: "/predictive-analytics", ...pm(PredictiveAnalytics, "ai_predictive") },
    { path: "/social-media-radar", ...pm(SocialMediaRadar, "ai_social_radar") },
    { path: "/revenue-autopilot", ...pm(RevenueAutopilot, "ai_revenue_autopilot") },

    // ── Security & Compliance ──────────────────────────
    { path: "/security-center", ...p(SecurityCenter) },
    { path: "/app/guvenlik", ...p(SecurityDashboard) },
    { path: "/gdpr-compliance", ...p(GDPRCompliance) },
    { path: "/central-office", ...p(CentralOfficeDashboard) },
    { path: "/central-pricing", ...p(CentralPricingManager) },
    { path: "/cross-property-guests", ...p(CrossPropertyGuests) },
    { path: "/ml-dashboard", ...p(MLDashboard) },

    // ── Admin ──────────────────────────────────────────
    { path: "/admin/tenants", ...p(AdminTenants) },
    { path: "/admin/module-report", ...p(ModuleReport) },
    { path: "/app/admin/leads", ...p(AdminLeads) },
    { path: "/admin/governance", ...p(GovernancePanel) },
    { path: "/admin/user-roles", ...p(UserRoleManager) },
    { path: "/admin/housekeeping", ...p(HousekeepingDashboard) },
    { path: "/admin/pos", ...p(POSDashboard) },
    { path: "/admin/features", ...p(FeaturesShowcase) },
    { path: "/admin/cost", ...p(CostManagement) },
    { path: "/admin/gm-enhanced", ...p(EnhancedGMDashboard) },
  ];
}
