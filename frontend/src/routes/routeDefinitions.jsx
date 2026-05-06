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

// ── Lazy imports ───────────────────────────────────────────────────
// Eski "kritik" sayfalar da lazy yapıldı (T006 perf): AuthPage, Dashboard,
// LandingPage, PrivacyPolicy — App.jsx'te <Routes> Suspense ile sarılı.
const AuthPage = lazy(() => import("@/pages/AuthPage"));
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const LandingPage = lazy(() => import("@/pages/LandingPage"));
const PrivacyPolicy = lazy(() => import("@/pages/PrivacyPolicy"));
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
const PreCheckinPage = lazy(() => import("@/pages/PreCheckinPage"));
const DigitalKey = lazy(() => import("@/pages/DigitalKey"));
const UpsellStore = lazy(() => import("@/pages/UpsellStore"));
const StaffMobileApp = lazy(() => import("@/pages/StaffMobileApp"));
const StaffRoomServiceOrders = lazy(() => import("@/pages/StaffRoomServiceOrders"));
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
const DepartureList = lazy(() => import("@/pages/DepartureList"));
const NoShowToday = lazy(() => import("@/pages/NoShowToday"));
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
const IdPhotoViewReportPage = lazy(() => import("@/pages/IdPhotoViewReportPage"));
const IdPhotoAdminPage = lazy(() => import("@/pages/IdPhotoAdminPage"));
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
const ShiftHandoverPage = lazy(() => import("@/pages/ShiftHandoverPage"));
const EarlyLatePricingSettings = lazy(() => import("@/pages/EarlyLatePricingSettings"));
const EodReportPage = lazy(() => import("@/pages/EodReportPage"));
const WalkinPage = lazy(() => import("@/pages/WalkinPage"));
const RoomMapPage = lazy(() => import("@/pages/RoomMapPage"));
const WakeUpCallsPage = lazy(() => import("@/pages/WakeUpCallsPage"));
const LostFoundPage = lazy(() => import("@/pages/LostFoundPage"));
const GroupFolioPage = lazy(() => import("@/pages/GroupFolioPage"));
const RoomMappingWizard = lazy(() => import("@/pages/RoomMappingWizard"));
const B2BApiDocs = lazy(() => import("@/pages/B2BApiDocs"));
const ChannelOpsPage = lazy(() => import("@/pages/ChannelOpsPage"));
const SecurityHub = lazy(() => import("@/pages/SecurityHub"));
const ChannelHub = lazy(() => import("@/pages/ChannelHub"));
const RevenueHub = lazy(() => import("@/pages/RevenueHub"));
const AdminHub = lazy(() => import("@/pages/AdminHub"));
const HRHub = lazy(() => import("@/pages/HRHub"));
const GoLiveReadinessCockpit = lazy(() => import("@/pages/GoLiveReadinessCockpit"));
const EncryptionManagementPage = lazy(() => import("@/pages/EncryptionManagementPage"));
const WebhookOutboxAdmin = lazy(() => import("@/pages/WebhookOutboxAdmin"));
const EarlyWarningDashboard = lazy(() => import("@/pages/EarlyWarningDashboard"));
const ModuleDiscovery = lazy(() => import("@/pages/ModuleDiscovery"));
const IntegrationCredentials = lazy(() => import("@/pages/IntegrationCredentials"));
const CapXIntegration = lazy(() => import("@/pages/CapXIntegration"));
// Opera-parity additions
const FolioRoutingPage = lazy(() => import("@/pages/FolioRoutingPage"));
const LoyaltyAdminPage = lazy(() => import("@/pages/LoyaltyAdminPage"));
const ActivitySchedulerPage = lazy(() => import("@/pages/ActivitySchedulerPage"));
const BlockManagementPage = lazy(() => import("@/pages/BlockManagementPage"));
const ForecastReportsPage = lazy(() => import("@/pages/ForecastReportsPage"));
const FunctionSpacePage = lazy(() => import("@/pages/FunctionSpacePage"));
const TrialBalancePage = lazy(() => import("@/pages/TrialBalancePage"));
const ProfileUdfPage = lazy(() => import("@/pages/ProfileUdfPage"));
const CateringMenuPage = lazy(() => import("@/pages/CateringMenuPage"));
const SuiteConnectingPage = lazy(() => import("@/pages/SuiteConnectingPage"));
const HurdleRatesPage = lazy(() => import("@/pages/HurdleRatesPage"));

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
    { path: "/precheckin/:token", type: "public", component: PreCheckinPage },

    // ── Core Operations ────────────────────────────────
    { path: "/app/dashboard", ...p(Dashboard, { modules }) , wrapLayout: true, layoutModule: "dashboard" },
    { path: "/app/profile", ...p(ProfilePage) , wrapLayout: true, layoutModule: "profile" },
    { path: "/profile", ...p(ProfilePage) , wrapLayout: true, layoutModule: "profile" },
    { path: "/app/compliance/pci", ...p(PCIComplianceDashboard) , wrapLayout: true, layoutModule: "pci-compliance" },
    { path: "/app/xchange", ...p(XchangePage) , wrapLayout: true, layoutModule: "xchange" },
    { path: "/app/mice", ...pm(MicePage, "mice", undefined, { strict: true }) , wrapLayout: true, layoutModule: "mice" },
    { path: "/app/procurement", ...p(ProcurementPage) , wrapLayout: true, layoutModule: "procurement" },
    { path: "/app/stock-rehber", ...p(InventoryProcurementGuide) , wrapLayout: true, layoutModule: "procurement" },
    { path: "/app/mailing", ...p(MailingPage) , wrapLayout: true, layoutModule: "mailing" },
    { path: "/app/module-store", ...p(ModuleStorePage) , wrapLayout: true, layoutModule: "module-store" },
    { path: "/module-store", ...p(ModuleStorePage) , wrapLayout: true, layoutModule: "module-store" },
    { path: "/app/afsadakat", ...p(AfsadakatLauncher) , wrapLayout: true, layoutModule: "afsadakat" },
    { path: "/app/onboarding", ...p(OnboardingWizard) , wrapLayout: true, layoutModule: "onboarding" },
    { path: "/dashboard-simple", ...p(Dashboard, { modules }) , wrapLayout: true, layoutModule: "dashboard" },
    { path: "/ai-pms", ...p(AIEnhancedPMS) },
    { path: "/app/ai", ...p(AIModule) , wrapLayout: true, layoutModule: "ai" },
    { path: "/pms", type: "memory", targetPath: "/pms", ...p(PMSModule) },
    { path: "/app/pms", type: "memory", targetPath: "/app/pms", ...p(PMSModule) },
    { path: "/pms-operations", ...p(PMSOperationalDashboard) , wrapLayout: true, layoutModule: "pms_operations" },
    { path: "/folio-detail", ...p(FolioDetailView) , wrapLayout: true, layoutModule: "folio_detail" },
    { path: "/folio-detail/:folioId", ...p(FolioDetailView) , wrapLayout: true, layoutModule: "folio_detail" },
    { path: "/housekeeping-status", ...p(HousekeepingStatusPage) , wrapLayout: true, layoutModule: "housekeeping" },
    // M5 pilot (May 2026): Layout sarımı ProtectedRoute tarafından yapılır.
    // Bu route'lar `wrapLayout: true` flag'i ile işaretli; sayfa dosyaları
    // Layout import/sarımını kendi return'lerinden kaldırmıştır.
    { path: "/shift-handover", ...p(ShiftHandoverPage), wrapLayout: true, layoutModule: "shift_handover" },
    { path: "/settings/early-late-pricing", ...p(EarlyLatePricingSettings) },
    { path: "/eod-report", ...p(EodReportPage), wrapLayout: true, layoutModule: "eod_report" },
    { path: "/walkin", ...p(WalkinPage), wrapLayout: true, layoutModule: "walkin" },
    { path: "/room-map", ...p(RoomMapPage), wrapLayout: true, layoutModule: "room_map" },
    { path: "/wake-up-calls", ...p(WakeUpCallsPage), wrapLayout: true, layoutModule: "wake_up_calls" },
    { path: "/lost-found", ...p(LostFoundPage), wrapLayout: true, layoutModule: "lost_found" },
    { path: "/guest-journey", ...p(GuestJourney) , wrapLayout: true },
    { path: "/operational-events", ...p(OperationalEventDashboard) , wrapLayout: true, layoutModule: "pms_operations" },
    { path: "/app/migration-observability", ...p(MigrationObservabilityPage) , wrapLayout: true, layoutModule: "reports" },
    { path: "/app/integration-hub", ...pa(IntegrationHub) , wrapLayout: true, layoutModule: "integration-hub" },
    { path: "/app/admin-control-panel", ...pa(AdminControlPanel) , wrapLayout: true, layoutModule: "admin_control_panel" },

    // ── Reservations ───────────────────────────────────
    { path: "/reservation-calendar", ...p(ReservationCalendar) },
    { path: "/app/reservation-calendar", ...p(ReservationCalendar) },
    { path: "/reservation-lineage", ...p(ReservationLineage) , wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/group-bookings-manage", ...p(GroupBookingsPage) , wrapLayout: true, layoutModule: "group-bookings" },
    { path: "/deposit-tracking", ...p(DepositTrackingPage) , wrapLayout: true, layoutModule: "deposits" },
    { path: "/group-folio", ...p(GroupFolioPage) , wrapLayout: true, layoutModule: "group_folio" },
    { path: "/no-show-analytics", ...p(NoShowAnalytics) },
    { path: "/group-reservations", ...p(GroupReservations) },
    { path: "/arrival-list", ...p(ArrivalList) , wrapLayout: true, layoutModule: "pms" },
    { path: "/departure-list", ...p(DepartureList) , wrapLayout: true, layoutModule: "departure_list" },
    { path: "/no-show-today", ...p(NoShowToday) , wrapLayout: true, layoutModule: "no_show_today" },

    // ── Finance ────────────────────────────────────────
    { path: "/invoices", ...p(InvoiceModule) , wrapLayout: true, layoutModule: "invoices" },
    { path: "/app/invoices", ...p(InvoiceModule) , wrapLayout: true, layoutModule: "invoices" },
    { path: "/night-audit", ...p(NightAuditDashboard) , wrapLayout: true, layoutModule: "night_audit" },
    { path: "/night-audit/logs", ...p(NightAuditLogs) , wrapLayout: true, layoutModule: "reports" },
    { path: "/pending-ar", ...p(PendingAR) , wrapLayout: true, layoutModule: "pending-ar" },
    { path: "/city-ledger", ...p(CityLedgerAccounts) , wrapLayout: true, layoutModule: "city-ledger" },
    { path: "/efatura", ...p(EFaturaModule) },

    // ── Settings ───────────────────────────────────────
    { path: "/settings", ...p(Settings) , wrapLayout: true, layoutModule: "settings" },
    { path: "/app/settings", ...p(Settings) , wrapLayout: true, layoutModule: "settings" },

    // ── Channel Manager ────────────────────────────────
    { path: "/channel-connections", type: "redirect", to: "/channels?tab=connections" },
    { path: "/cm-dashboard", type: "redirect", to: "/channels?tab=dashboard" },
    { path: "/go-live-readiness", ...p(GoLiveReadinessCockpit) , wrapLayout: true },
    { path: "/channel-manager", ...p(ChannelManagerModule) , wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/app/channel-manager", ...p(ChannelManagerModule) , wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/channel-ops", type: "redirect", to: "/channels?tab=ops" },
    { path: "/channels", ...p(ChannelHub) , wrapLayout: true, layoutModule: "channels" },
    { path: "/app/channels", ...p(ChannelHub) , wrapLayout: true, layoutModule: "channels" },
    { path: "/app/revenue-hub", ...p(RevenueHub) , wrapLayout: true, layoutModule: "revenue" },
    { path: "/app/admin-hub", ...pa(AdminHub) , wrapLayout: true, layoutModule: "admin" },
    { path: "/mapping-manager", ...p(MappingManager) , wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/room-mapping-wizard", ...p(RoomMappingWizard) , wrapLayout: true },
    { path: "/hotelrunner", ...pa(HotelRunnerIntegration) , wrapLayout: true },
    { path: "/hrv2-ops", type: "redirect", to: "/hr?tab=ops" },
    { path: "/exely", ...pa(ExelyIntegration) , wrapLayout: true },
    { path: "/ari-push", ...pa(ARIPushDashboard) , wrapLayout: true },
    { path: "/rate-manager", ...pa(UnifiedRateManager) },
    { path: "/hr-rate-manager", ...pa(UnifiedRateManager) },
    { path: "/unified-rate-manager", ...p(UnifiedRateManager) },
    { path: "/wire-failures", ...pa(WireFailureDashboard) , wrapLayout: true, layoutModule: "channel-manager" },
    { path: "/data-model", ...pa(DataModelDashboard) , wrapLayout: true },
    { path: "/lockdown", ...pa(LockdownDashboard) , wrapLayout: true },
    { path: "/incidents", ...pa(OperatorIncidentPanel) , wrapLayout: true },
    { path: "/runtime-cockpit", ...pa(RuntimeCockpitPage) , wrapLayout: true },
    { path: "/control-plane", ...pa(ControlPlane) , wrapLayout: true },

    // ── Reports ────────────────────────────────────────
    { path: "/app/raporlar", ...p(BasicReports) , wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/app/gelismis-raporlar", ...p(BasicReports) , wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/reports", ...p(BasicReports) , wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/app/reports", ...p(BasicReports) , wrapLayout: true, layoutModule: "reports_basic" },
    { path: "/reports/builder", ...p(ReportBuilder) , wrapLayout: true, layoutModule: "reports" },
    { path: "/app/rapor-olusturucu", ...p(ReportBuilder) , wrapLayout: true, layoutModule: "reports" },
    { path: "/reports/official-guest-list", ...p(OfficialGuestList) , wrapLayout: true, layoutModule: "reports" },
    { path: "/reports/corporate-contracts", ...p(CorporateContractsDashboard) , wrapLayout: true, layoutModule: "reports" },

    // ── Revenue & Analytics (Consolidated) ───────────
    { path: "/displacement-analysis", ...p(DisplacementAnalysis) },
    { path: "/app/displacement-analysis", ...p(DisplacementAnalysis) },
    { path: "/app/gelir-yonetimi", ...p(GelirYonetimiPage) },
    { path: "/app/ai-zeka", ...p(AIZekaPage) , wrapLayout: true, layoutModule: "ai" },
    { path: "/app/analitik", ...p(AnalitikRaporlarPage) , wrapLayout: true, layoutModule: "rms" },

    // ── Revenue & Analytics (Legacy routes — backward compat) ──
    { path: "/revenue-engine", ...p(RevenueEngineDashboard) , wrapLayout: true, layoutModule: "rms" },
    { path: "/data-intelligence", ...p(DataIntelligenceDashboard) },
    { path: "/messaging-dashboard", ...p(MessagingDashboard) , wrapLayout: true, layoutModule: "messaging" },
    { path: "/ml-scheduler", ...p(MLSchedulerDashboard) },
    { path: "/revenue-autopilot-v2", ...p(RevenueAutopilotDashboard) },
    { path: "/analytics-export", ...p(AnalyticsExportDashboard) },

    // ── RMS (feature-gated) ────────────────────────────
    { path: "/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },
    { path: "/app/rms", type: "feature", featureKey: "hidden_rms", ...p(RMSModule) },

    // ── Marketplace ────────────────────────────────────
    { path: "/marketplace", ...p(MarketplaceModule) , wrapLayout: true, layoutModule: "marketplace" },
    { path: "/app/marketplace", ...p(MarketplaceModule) , wrapLayout: true, layoutModule: "marketplace" },
    { path: "/app/supplies-market", ...p(SuppliesMarket) , wrapLayout: true, layoutModule: "supplies_market" },
    { path: "/vendor", type: "public", component: VendorPortal },
    { path: "/vendor/*", type: "public", component: VendorPortal },

    // ── Loyalty & Inventory ────────────────────────────
    { path: "/loyalty", ...p(LoyaltyModule) , wrapLayout: true, layoutModule: "loyalty" },
    { path: "/hotel-inventory", ...p(HotelInventory) , wrapLayout: true },
    { path: "/templates", ...p(TemplateManager) , wrapLayout: true, layoutModule: "pms" },

    // ── Core Operations (Dashboard module cards) ──────
    { path: "/housekeeping", ...p(HousekeepingDashboard) , wrapLayout: true, layoutModule: "housekeeping" },
    { path: "/pos", ...p(POSDashboard) , wrapLayout: true, layoutModule: "pos" },
    { path: "/features", ...p(FeaturesShowcase) , wrapLayout: true },

    // ── Guest Features ─────────────────────────────────
    { path: "/guest/checkin/:bookingId", ...p(SelfCheckin) },
    { path: "/guest/digital-key/:bookingId", ...p(DigitalKey) },
    { path: "/guest/upsell/:bookingId", ...p(UpsellStore) },

    // ── Staff & OTA ────────────────────────────────────
    { path: "/staff/mobile", ...p(StaffMobileApp) },
    { path: "/staff/room-service", ...p(StaffRoomServiceOrders) , wrapLayout: true, layoutModule: "pos" },
    { path: "/ota-messaging-hub", ...p(OTAMessagingHub) },
    { path: "/messaging-center", ...p(MessagingCenter) , wrapLayout: true, layoutModule: "messaging" },
    { path: "/sales", ...p(SalesModule) , wrapLayout: true, layoutModule: "sales" },
    { path: "/travel-agent-arap", ...p(TravelAgentARAP) , wrapLayout: true },
    { path: "/app/travel-agent-arap", ...p(TravelAgentARAP) , wrapLayout: true },
    { path: "/agency-requests", ...p(AgencyRequests) },
    { path: "/app/incoming-agency-contracts", ...p(IncomingAgencyContracts) , wrapLayout: true },
    { path: "/agency-management", ...p(AgencyManagement) , wrapLayout: true },
    { path: "/agency-content", ...p(AgencyContentDistribution) , wrapLayout: true },
    { path: "/b2b-analytics", ...p(B2BAnalyticsDashboard) , wrapLayout: true, layoutModule: "b2b-analytics" },
    { path: "/report-scheduler", ...p(ReportScheduler) , wrapLayout: true, layoutModule: "report-scheduler" },

    // ── Frontdesk & Maintenance ────────────────────────
    { path: "/frontdesk/audit-checklist", ...p(FrontdeskAuditChecklist) , wrapLayout: true, layoutModule: "pms" },
    { path: "/maintenance/work-orders", ...p(MaintenanceWorkOrders) , wrapLayout: true, layoutModule: "maintenance" },
    { path: "/maintenance/assets", ...p(MaintenanceAssets) , wrapLayout: true, layoutModule: "maintenance" },
    { path: "/maintenance/plans", ...p(MaintenancePlans) , wrapLayout: true, layoutModule: "maintenance" },

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
    { path: "/app/konaklama-vergisi", ...pm(KonaklamaVergisiModule, "invoices") , wrapLayout: true, layoutModule: "konaklama-vergisi" },
    { path: "/app/help", ...p(HelpCenter) , wrapLayout: true, layoutModule: "help" },
    { path: "/app/mevzuat-raporlari", ...pm(MevzuatRaporlari, "basic_reporting") , wrapLayout: true, layoutModule: "mevzuat-raporlari" },
    { path: "/executive", ...pm(ExecutiveDashboard, "gm_dashboards") },
    { path: "/gm/enhanced", type: "redirect", to: "/executive" },
    { path: "/gm-classic", type: "redirect", to: "/app/dashboard" },

    // ── Infrastructure ─────────────────────────────────
    { path: "/data-pipeline", ...p(DataPipelineDashboard) },
    { path: "/event-bus", ...p(EventBusDashboard) },
    { path: "/system-health", ...p(SystemHealthDashboard) , wrapLayout: true, layoutModule: "system-health" },
    { path: "/observability", ...p(ObservabilityDashboard) },
    { path: "/security-hardening", type: "redirect", to: "/security?tab=hardening" },
    { path: "/security", ...p(SecurityHub) , wrapLayout: true, layoutModule: "security" },
    { path: "/app/security", ...p(SecurityHub) , wrapLayout: true, layoutModule: "security" },
    { path: "/runtime-infrastructure", ...p(RuntimeInfrastructureDashboard) },
    { path: "/infra-hardening", ...p(InfraHardeningDashboard) , wrapLayout: true },
    { path: "/production-golive", ...p(ProductionGoLiveDashboard) , wrapLayout: true },
    { path: "/platform-scaling", ...p(PlatformScalingDashboard) , wrapLayout: true },
    { path: "/enterprise-live", type: "redirect", to: "/executive" },
    { path: "/pii-strict-mode", ...p(PIIStrictModeDashboard) },

    // ── Ops & Phases ───────────────────────────────────
    { path: "/audit-timeline", ...p(AuditTimelinePage, {}) , wrapLayout: true, layoutModule: "audit-timeline" },
    { path: "/urgent-message-report", ...p(UrgentMessageReportPage, {}) , wrapLayout: true, layoutModule: "urgent-message-report" },
    { path: "/recalled-messages-report", ...p(RecalledMessagesReportPage, {}) , wrapLayout: true, layoutModule: "recalled-messages-report" },
    { path: "/id-photo-view-report", ...p(IdPhotoViewReportPage, {}) , wrapLayout: true, layoutModule: "id-photo-view-report" },
    { path: "/id-photo-admin", ...p(IdPhotoAdminPage, {}) , wrapLayout: true, layoutModule: "id-photo-admin" },
    { path: "/admin/urgent-permissions", ...p(UrgentPermissionAdminPage, {}) , wrapLayout: true, layoutModule: "urgent-permission-admin" },
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
    { path: "/group-sales", ...p(GroupSales) , wrapLayout: true, layoutModule: "group-sales" },
    { path: "/sales-crm", ...p(SalesCRM) , wrapLayout: true, layoutModule: "sales-crm" },
    { path: "/service-recovery", ...p(ServiceRecovery) , wrapLayout: true },
    { path: "/spa-wellness", ...pm(SpaWellness, "spa", undefined, { strict: true }) , wrapLayout: true, layoutModule: "spa" },
    { path: "/multi-property", ...p(MultiProperty) },
    { path: "/staff-management", ...p(StaffManagement) },
    { path: "/hr-complete", type: "redirect", to: "/hr?tab=suite" },
    { path: "/hr", ...p(HRHub) , wrapLayout: true, layoutModule: "hr" },
    { path: "/app/hr", ...p(HRHub) , wrapLayout: true, layoutModule: "hr" },
    { path: "/fnb-complete", ...p(FnBComplete) , wrapLayout: true, layoutModule: "fnb" },
    { path: "/fnb/beo-generator", ...p(FnbBeoGenerator) , wrapLayout: true, layoutModule: "fnb" },
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
    { path: "/gdpr-compliance", ...p(GDPRCompliance) , wrapLayout: true },
    { path: "/encryption-management", ...p(EncryptionManagementPage) , wrapLayout: true, layoutModule: "encryption_management" },
    { path: "/central-office", ...p(CentralOfficeDashboard) , wrapLayout: true },
    { path: "/central-pricing", ...p(CentralPricingManager) },
    { path: "/cross-property-guests", ...p(CrossPropertyGuests) , wrapLayout: true },
    { path: "/ml-dashboard", ...p(MLDashboard) , wrapLayout: true },

    // ── Admin ──────────────────────────────────────────
    { path: "/admin/tenants", ...pa(AdminTenants) , wrapLayout: true, layoutModule: "admin-tenants" },
    { path: "/admin/vendors", ...pa(AdminVendors) , wrapLayout: true, layoutModule: "admin_vendors" },
    { path: "/admin/quick-id", ...pa(QuickIdSettings) , wrapLayout: true, layoutModule: "quick_id_settings" },
    { path: "/admin/room-qr-codes", ...pa(RoomQrCodes) , wrapLayout: true, layoutModule: "room_qr_codes" },
    { path: "/app/room-requests", ...p(RoomRequests) , wrapLayout: true, layoutModule: "room_qr_requests" },
    { path: "/admin/module-report", ...pa(ModuleReport) , wrapLayout: true, layoutModule: "admin-module-report" },
    { path: "/app/admin/leads", ...pa(AdminLeads) , wrapLayout: true, layoutModule: "admin-leads" },
    { path: "/admin/governance", ...pa(GovernancePanel) , wrapLayout: true, layoutModule: "governance" },
    { path: "/admin/user-roles", ...pa(UserRoleManager) , wrapLayout: true, layoutModule: "user-role-manager" },
    { path: "/admin/housekeeping", ...pa(HousekeepingDashboard) , wrapLayout: true, layoutModule: "housekeeping" },
    { path: "/admin/pos", ...pa(POSDashboard) , wrapLayout: true, layoutModule: "pos" },
    { path: "/admin/features", ...pa(FeaturesShowcase) , wrapLayout: true },
    { path: "/admin/webhook-outbox", ...pa(WebhookOutboxAdmin) , wrapLayout: true, layoutModule: "webhook-outbox-admin" },
    { path: "/admin/early-warning", ...pa(EarlyWarningDashboard) , wrapLayout: true, layoutModule: "early-warning" },
    { path: "/admin/module-discovery", ...pa(ModuleDiscovery) , wrapLayout: true, layoutModule: "module-discovery" },
    { path: "/admin/integration-credentials", ...pa(IntegrationCredentials) , wrapLayout: true, layoutModule: "integration-credentials" },
    { path: "/admin/capx-integration", ...pa(CapXIntegration) , wrapLayout: true, layoutModule: "capx-integration" },
    { path: "/admin/cost", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/app/cost-management", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/cost-management", type: "redirect", to: "/app/raporlar?section=expenses" },
    { path: "/admin/gm-enhanced", type: "redirect", to: "/executive" },

    // ── Opera-parity (Folio Routing, Block Mgmt, Activity Scheduler, Loyalty, Forecast) ──
    { path: "/folio-routing", ...p(FolioRoutingPage) },
    { path: "/loyalty-admin", ...p(LoyaltyAdminPage) },
    { path: "/activities", ...p(ActivitySchedulerPage) },
    { path: "/block-management", ...p(BlockManagementPage), wrapLayout: true, layoutModule: "block_management" },
    { path: "/forecast-reports", ...p(ForecastReportsPage) },
    { path: "/function-space", ...p(FunctionSpacePage) },
    { path: "/trial-balance", ...p(TrialBalancePage) },
    { path: "/profile-udf", ...p(ProfileUdfPage) },
    { path: "/catering", ...p(CateringMenuPage) },
    { path: "/suite-connecting", ...p(SuiteConnectingPage) },
    { path: "/hurdle-rates", ...p(HurdleRatesPage) },
  ];
}
