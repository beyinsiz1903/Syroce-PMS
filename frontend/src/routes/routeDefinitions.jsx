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
import { lazyWithPreload as lazy } from "./lazyWithPreload";

// ── Critical imports (loaded immediately) ──────────────────────────
import AuthPage from "@/pages/AuthPage";
import Dashboard from "@/pages/Dashboard";
import LandingPage from "@/pages/LandingPage";
import PrivacyPolicy from "@/pages/PrivacyPolicy";

// ── Lazy imports ───────────────────────────────────────────────────
const PMSModule = lazy(() => import("@/pages/PMSModule"));
const InvoiceModule = lazy(() => import("@/pages/InvoiceModule"));
const RMSModule = lazy(() => import("@/pages/RMSModule"));
const ChannelManagerModule = lazy(() => import("@/pages/ChannelManagerModule"));
const ChannelManagerDashboardV2 = lazy(() => import("@/pages/ChannelManagerDashboardV2"));
const MappingManager = lazy(() => import("@/pages/MappingManager"));
const ReservationLineage = lazy(() => import("@/pages/ReservationLineage"));
const ReservationCalendar = lazy(() => import("@/pages/ReservationCalendar"));
const Settings = lazy(() => import("@/pages/Settings"));
const ProfilePage = lazy(() => import("@/pages/ProfilePage"));
const PCIComplianceDashboard = lazy(() => import("@/pages/PCIComplianceDashboard"));
const XchangePage = lazy(() => import("@/pages/XchangePage"));
const MicePage = lazy(() => import("@/pages/MicePage"));
const ProcurementPage = lazy(() => import("@/pages/ProcurementPage"));
const InventoryProcurementGuide = lazy(() => import("@/pages/InventoryProcurementGuide"));
const MailingPage = lazy(() => import("@/pages/MailingPage"));
const ModuleStorePage = lazy(() => import("@/pages/ModuleStorePage"));
const AfsadakatLauncher = lazy(() => import("@/pages/AfsadakatLauncher"));
const OnboardingWizard = lazy(() => import("@/pages/OnboardingWizard"));
const ResetPasswordPage = lazy(() => import("@/pages/ResetPasswordPage"));
const PendingAR = lazy(() => import("@/pages/PendingAR"));
const CityLedgerAccounts = lazy(() => import("@/pages/CityLedgerAccounts"));
const LoyaltyModule = lazy(() => import("@/pages/LoyaltyModule"));
const MarketplaceModule = lazy(() => import("@/pages/MarketplaceModule"));
const SuppliesMarket = lazy(() => import("@/pages/SuppliesMarket"));
const VendorPortal = lazy(() => import("@/pages/VendorPortal"));
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
const KonaklamaVergisiModule = lazy(() => import("@/pages/KonaklamaVergisiModule"));
const HelpCenter = lazy(() => import("@/pages/HelpCenter"));
const MevzuatRaporlari = lazy(() => import("@/pages/MevzuatRaporlari"));
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
const FeaturesShowcase = lazy(() => import("@/pages/FeaturesShowcase"));
const HousekeepingDashboard = lazy(() => import("@/pages/HousekeepingDashboard"));
const POSDashboard = lazy(() => import("@/pages/POSDashboard"));
const AdminTenants = lazy(() => import("@/pages/AdminTenants"));
const AdminVendors = lazy(() => import("@/pages/AdminVendors"));
const QuickIdSettings = lazy(() => import("@/pages/admin/QuickIdSettings"));
const RoomQrCodes = lazy(() => import("@/pages/admin/RoomQrCodes"));
const RoomRequests = lazy(() => import("@/pages/RoomRequests"));
const RoomRequestPage = lazy(() => import("@/pages/guest/RoomRequestPage"));
const PublicReviewPage = lazy(() => import("@/pages/PublicReviewPage"));
const ModuleReport = lazy(() => import("@/pages/ModuleReport"));
const UserRoleManager = lazy(() => import("@/pages/UserRoleManager"));
const AIModule = lazy(() => import("@/pages/AIModule"));
const OnlineCheckin = lazy(() => import("@/pages/OnlineCheckin"));
const FlashReport = lazy(() => import("@/pages/FlashReport"));
const GroupSales = lazy(() => import("@/pages/GroupSales"));
const SalesCRM = lazy(() => import("@/pages/SalesCRM"));
const ServiceRecovery = lazy(() => import("@/pages/ServiceRecovery"));
const SpaWellness = lazy(() => import("@/pages/SpaWellness"));
const AIChatbot = lazy(() => import("@/pages/AIChatbot"));
const DynamicPricing = lazy(() => import("@/pages/DynamicPricing"));
const MultiProperty = lazy(() => import("@/pages/MultiProperty"));
const StaffManagement = lazy(() => import("@/pages/StaffManagement"));
const GuestJourney = lazy(() => import("@/pages/GuestJourney"));
const ArrivalList = lazy(() => import("@/pages/ArrivalList"));
const AIWhatsAppConcierge = lazy(() => import("@/pages/AIWhatsAppConcierge"));
const PredictiveAnalytics = lazy(() => import("@/pages/PredictiveAnalytics"));
const TravelAgentARAP = lazy(() => import("@/pages/TravelAgentARAP"));
const AgencyRequests = lazy(() => import("@/pages/AgencyRequests"));
const IncomingAgencyContracts = lazy(() => import("@/pages/IncomingAgencyContracts"));
const AgencyManagement = lazy(() => import("@/pages/AgencyManagement"));
const AgencyContentDistribution = lazy(() => import("@/pages/AgencyContentDistribution"));
const AgencyPortalDashboard = lazy(() => import("@/pages/AgencyPortalDashboard"));
const B2BAnalyticsDashboard = lazy(() => import("@/pages/B2BAnalyticsDashboard"));
const ReportScheduler = lazy(() => import("@/pages/ReportScheduler"));
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
const DataIntelligenceDashboard = lazy(() => import("@/pages/DataIntelligenceDashboard"));
const MessagingDashboard = lazy(() => import("@/pages/MessagingDashboard"));
const MLSchedulerDashboard = lazy(() => import("@/pages/MLSchedulerDashboard"));
const RevenueAutopilotDashboard = lazy(() => import("@/pages/RevenueAutopilotDashboard"));
const AnalyticsExportDashboard = lazy(() => import("@/pages/AnalyticsExportDashboard"));
const DisplacementAnalysis = lazy(() => import("@/pages/DisplacementAnalysis"));
const GelirYonetimiPage = lazy(() => import("@/pages/GelirYonetimiPage"));
const AIZekaPage = lazy(() => import("@/pages/AIZekaPage"));
const AnalitikRaporlarPage = lazy(() => import("@/pages/AnalitikRaporlarPage"));
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
const UrgentMessageReportPage = lazy(() => import("@/pages/UrgentMessageReportPage"));
const RecalledMessagesReportPage = lazy(() => import("@/pages/RecalledMessagesReportPage"));
const UrgentPermissionAdminPage = lazy(() => import("@/pages/UrgentPermissionAdminPage"));
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
const RoomMappingWizard = lazy(() => import("@/pages/RoomMappingWizard"));
const B2BApiDocs = lazy(() => import("@/pages/B2BApiDocs"));
const ChannelOpsPage = lazy(() => import("@/pages/ChannelOpsPage"));
const SecurityHub = lazy(() => import("@/pages/SecurityHub"));
const ChannelHub = lazy(() => import("@/pages/ChannelHub"));
const HRHub = lazy(() => import("@/pages/HRHub"));
const GoLiveReadinessCockpit = lazy(() => import("@/pages/GoLiveReadinessCockpit"));
const EncryptionManagementPage = lazy(() => import("@/pages/EncryptionManagementPage"));
const WebhookOutboxAdmin = lazy(() => import("@/pages/WebhookOutboxAdmin"));
const EarlyWarningDashboard = lazy(() => import("@/pages/EarlyWarningDashboard"));
const ModuleDiscovery = lazy(() => import("@/pages/ModuleDiscovery"));
const IntegrationCredentials = lazy(() => import("@/pages/IntegrationCredentials"));

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

  return [
    // ── Public ──────────────────────────────────────────
    { path: "/landing", type: "public", component: LandingPage },
    { path: "/g/room/:tenantId/:roomId", type: "public", component: RoomRequestPage },
    { path: "/review/:token", type: "public", component: PublicReviewPage },
    { path: "/privacy-policy", type: "public", component: PrivacyPolicy },
    { path: "/gizlilik", type: "public", component: PrivacyPolicy },
    { path: "/pms-lite", type: "public", component: PmsLiteLanding },
    { path: "/agency-portal", type: "public", component: AgencyPortalDashboard },
    { path: "/b2b/docs", ...pa(B2BApiDocs) },
    { path: "/system-status", type: "public", component: SimpleAdminPanel },
    { path: "/auth/reset-password", type: "public", component: ResetPasswordPage },

    // ── Core Operations ────────────────────────────────
    { path: "/app/dashboard", ...p(Dashboard, { modules }) },
    { path: "/app/profile", ...p(ProfilePage) },
    { path: "/profile", ...p(ProfilePage) },
    { path: "/app/compliance/pci", ...p(PCIComplianceDashboard) },
    { path: "/app/xchange", ...p(XchangePage) },
    { path: "/app/mice", ...pm(MicePage, "mice", undefined, { strict: true }) },
    { path: "/app/procurement", ...p(ProcurementPage) },
    { path: "/app/stock-rehber", ...p(InventoryProcurementGuide) },
    { path: "/app/mailing", ...p(MailingPage) },
    { path: "/app/module-store", ...p(ModuleStorePage) },
    { path: "/module-store", ...p(ModuleStorePage) },
    { path: "/app/afsadakat", ...p(AfsadakatLauncher) },
    { path: "/app/onboarding", ...p(OnboardingWizard) },
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
    { path: "/app/integration-hub", ...pa(IntegrationHub) },
    { path: "/app/admin-control-panel", ...pa(AdminControlPanel) },

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

    // ── Settings ───────────────────────────────────────
    { path: "/settings", ...p(Settings) },
    { path: "/app/settings", ...p(Settings) },

    // ── Channel Manager ────────────────────────────────
    { path: "/channel-connections", type: "redirect", to: "/channels?tab=connections" },
    { path: "/cm-dashboard", type: "redirect", to: "/channels?tab=dashboard" },
    { path: "/go-live-readiness", ...p(GoLiveReadinessCockpit) },
    { path: "/channel-manager", ...p(ChannelManagerModule) },
    { path: "/app/channel-manager", ...p(ChannelManagerModule) },
    { path: "/channel-ops", type: "redirect", to: "/channels?tab=ops" },
    { path: "/channels", ...p(ChannelHub) },
    { path: "/app/channels", ...p(ChannelHub) },
    { path: "/mapping-manager", ...p(MappingManager) },
    { path: "/room-mapping-wizard", ...p(RoomMappingWizard) },
    { path: "/hotelrunner", ...pa(HotelRunnerIntegration) },
    { path: "/hrv2-ops", type: "redirect", to: "/hr?tab=ops" },
    { path: "/exely", ...pa(ExelyIntegration) },
    { path: "/ari-push", ...pa(ARIPushDashboard) },
    { path: "/rate-manager", ...pa(UnifiedRateManager) },
    { path: "/hr-rate-manager", ...pa(UnifiedRateManager) },
    { path: "/unified-rate-manager", ...p(UnifiedRateManager) },
    { path: "/wire-failures", ...pa(WireFailureDashboard) },
    { path: "/data-model", ...pa(DataModelDashboard) },
    { path: "/lockdown", ...pa(LockdownDashboard) },
    { path: "/incidents", ...pa(OperatorIncidentPanel) },
    { path: "/runtime-cockpit", ...pa(RuntimeCockpitPage) },
    { path: "/control-plane", ...pa(ControlPlane) },

    // ── Reports ────────────────────────────────────────
    { path: "/app/raporlar", ...p(BasicReports) },
    { path: "/app/gelismis-raporlar", ...p(BasicReports) },
    { path: "/reports", ...p(BasicReports) },
    { path: "/app/reports", ...p(BasicReports) },
    { path: "/reports/builder", ...p(ReportBuilder) },
    { path: "/app/rapor-olusturucu", ...p(ReportBuilder) },
    { path: "/reports/official-guest-list", ...p(OfficialGuestList) },
    { path: "/reports/corporate-contracts", ...p(CorporateContractsDashboard) },

    // ── Revenue & Analytics (Consolidated) ───────────
    { path: "/displacement-analysis", ...p(DisplacementAnalysis) },
    { path: "/app/displacement-analysis", ...p(DisplacementAnalysis) },
    { path: "/app/gelir-yonetimi", ...p(GelirYonetimiPage) },
    { path: "/app/ai-zeka", ...p(AIZekaPage) },
    { path: "/app/analitik", ...p(AnalitikRaporlarPage) },

    // ── Revenue & Analytics (Legacy routes — backward compat) ──
    { path: "/revenue-engine", ...p(RevenueEngineDashboard) },
    { path: "/data-intelligence", ...p(DataIntelligenceDashboard) },
    { path: "/messaging-dashboard", ...p(MessagingDashboard) },
    { path: "/ml-scheduler", ...p(MLSchedulerDashboard) },
    { path: "/revenue-autopilot-v2", ...p(RevenueAutopilotDashboard) },
    { path: "/analytics-export", ...p(AnalyticsExportDashboard) },

    // ── RMS (feature-gated) ────────────────────────────
    { path: "/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },
    { path: "/app/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },

    // ── Marketplace ────────────────────────────────────
    { path: "/marketplace", ...p(MarketplaceModule) },
    { path: "/app/marketplace", ...p(MarketplaceModule) },
    { path: "/app/supplies-market", ...p(SuppliesMarket) },
    { path: "/vendor", type: "public", component: VendorPortal },
    { path: "/vendor/*", type: "public", component: VendorPortal },

    // ── Loyalty & Inventory ────────────────────────────
    { path: "/loyalty", ...p(LoyaltyModule) },
    { path: "/hotel-inventory", ...p(HotelInventory) },
    { path: "/templates", ...p(TemplateManager) },

    // ── Core Operations (Dashboard module cards) ──────
    { path: "/housekeeping", ...p(HousekeepingDashboard) },
    { path: "/pos", ...p(POSDashboard) },
    { path: "/features", ...p(FeaturesShowcase) },

    // ── Guest Features ─────────────────────────────────
    { path: "/guest/checkin/:bookingId", ...p(SelfCheckin) },
    { path: "/guest/digital-key/:bookingId", ...p(DigitalKey) },
    { path: "/guest/upsell/:bookingId", ...p(UpsellStore) },

    // ── Staff & OTA ────────────────────────────────────
    { path: "/staff/mobile", ...p(StaffMobileApp) },
    { path: "/ota-messaging-hub", ...p(OTAMessagingHub) },
    { path: "/messaging-center", ...p(MessagingCenter) },
    { path: "/sales", ...p(SalesModule) },
    { path: "/travel-agent-arap", ...p(TravelAgentARAP) },
    { path: "/app/travel-agent-arap", ...p(TravelAgentARAP) },
    { path: "/agency-requests", ...p(AgencyRequests) },
    { path: "/app/incoming-agency-contracts", ...p(IncomingAgencyContracts) },
    { path: "/agency-management", ...p(AgencyManagement) },
    { path: "/agency-content", ...p(AgencyContentDistribution) },
    { path: "/b2b-analytics", ...p(B2BAnalyticsDashboard) },
    { path: "/report-scheduler", ...p(ReportScheduler) },

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
    { path: "/app/konaklama-vergisi", ...pm(KonaklamaVergisiModule, "invoices") },
    { path: "/app/help", ...p(HelpCenter) },
    { path: "/app/mevzuat-raporlari", ...pm(MevzuatRaporlari, "basic_reporting") },
    { path: "/executive", ...pm(ExecutiveDashboard, "gm_dashboards") },
    { path: "/gm/enhanced", type: "redirect", to: "/executive" },
    { path: "/gm-classic", type: "redirect", to: "/app/dashboard" },

    // ── Infrastructure ─────────────────────────────────
    { path: "/data-pipeline", ...p(DataPipelineDashboard) },
    { path: "/event-bus", ...p(EventBusDashboard) },
    { path: "/system-health", ...p(SystemHealthDashboard) },
    { path: "/observability", ...p(ObservabilityDashboard) },
    { path: "/security-hardening", type: "redirect", to: "/security?tab=hardening" },
    { path: "/security", ...p(SecurityHub) },
    { path: "/app/security", ...p(SecurityHub) },
    { path: "/runtime-infrastructure", ...p(RuntimeInfrastructureDashboard) },
    { path: "/infra-hardening", ...p(InfraHardeningDashboard) },
    { path: "/production-golive", ...p(ProductionGoLiveDashboard) },
    { path: "/platform-scaling", ...p(PlatformScalingDashboard) },
    { path: "/enterprise-live", type: "redirect", to: "/executive" },
    { path: "/pii-strict-mode", ...p(PIIStrictModeDashboard) },

    // ── Ops & Phases ───────────────────────────────────
    { path: "/audit-timeline", ...p(AuditTimelinePage, {}) },
    { path: "/urgent-message-report", ...p(UrgentMessageReportPage, {}) },
    { path: "/recalled-messages-report", ...p(RecalledMessagesReportPage, {}) },
    { path: "/admin/urgent-permissions", ...p(UrgentPermissionAdminPage, {}) },
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
    { path: "/sales-crm", ...p(SalesCRM) },
    { path: "/service-recovery", ...p(ServiceRecovery) },
    { path: "/spa-wellness", ...pm(SpaWellness, "spa", undefined, { strict: true }) },
    { path: "/multi-property", ...p(MultiProperty) },
    { path: "/staff-management", ...p(StaffManagement) },
    { path: "/hr-complete", type: "redirect", to: "/hr?tab=suite" },
    { path: "/hr", ...p(HRHub) },
    { path: "/app/hr", ...p(HRHub) },
    { path: "/fnb-complete", ...p(FnBComplete) },
    { path: "/fnb/beo-generator", ...p(FnbBeoGenerator) },
    { path: "/kitchen-display", ...p(KitchenDisplay) },

    // ── AI Module-gated ────────────────────────────────
    { path: "/ai-chatbot", ...pm(AIChatbot, "ai_chatbot") },
    { path: "/dynamic-pricing", ...pm(DynamicPricing, "ai_pricing") },
    { path: "/ai-whatsapp-concierge", ...pm(AIWhatsAppConcierge, "ai_whatsapp") },
    { path: "/predictive-analytics", ...pm(PredictiveAnalytics, "ai_predictive") },
    { path: "/social-media-radar", ...pm(SocialMediaRadar, "ai_social_radar") },
    { path: "/revenue-autopilot", ...pm(RevenueAutopilot, "ai_revenue_autopilot") },

    // ── Security & Compliance ──────────────────────────
    { path: "/security-center", type: "redirect", to: "/security?tab=center" },
    { path: "/app/güvenlik", type: "redirect", to: "/security?tab=monitor" },
    { path: "/gdpr-compliance", ...p(GDPRCompliance) },
    { path: "/encryption-management", ...p(EncryptionManagementPage) },
    { path: "/central-office", ...p(CentralOfficeDashboard) },
    { path: "/central-pricing", ...p(CentralPricingManager) },
    { path: "/cross-property-guests", ...p(CrossPropertyGuests) },
    { path: "/ml-dashboard", ...p(MLDashboard) },

    // ── Admin ──────────────────────────────────────────
    { path: "/admin/tenants", ...pa(AdminTenants) },
    { path: "/admin/vendors", ...pa(AdminVendors) },
    { path: "/admin/quick-id", ...pa(QuickIdSettings) },
    { path: "/admin/room-qr-codes", ...pa(RoomQrCodes) },
    { path: "/app/room-requests", ...p(RoomRequests) },
    { path: "/admin/module-report", ...pa(ModuleReport) },
    { path: "/app/admin/leads", ...pa(AdminLeads) },
    { path: "/admin/governance", ...pa(GovernancePanel) },
    { path: "/admin/user-roles", ...pa(UserRoleManager) },
    { path: "/admin/housekeeping", ...pa(HousekeepingDashboard) },
    { path: "/admin/pos", ...pa(POSDashboard) },
    { path: "/admin/features", ...pa(FeaturesShowcase) },
    { path: "/admin/webhook-outbox", ...pa(WebhookOutboxAdmin) },
    { path: "/admin/early-warning", ...pa(EarlyWarningDashboard) },
    { path: "/admin/module-discovery", ...pa(ModuleDiscovery) },
    { path: "/admin/integration-credentials", ...pa(IntegrationCredentials) },
    { path: "/admin/cost", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/app/cost-management", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/cost-management", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/admin/gm-enhanced", type: "redirect", to: "/executive" },
  ];
}
