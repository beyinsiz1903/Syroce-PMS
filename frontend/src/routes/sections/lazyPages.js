/**
 * Central lazy page registry — all route components defined once,
 * imported by section files. Keeps the route-tree split clean and
 * allows the public API (AuthPage/Dashboard/LandingPage/PrivacyPolicy/
 * GuestPortal) to remain re-exported from `routeDefinitions.jsx`.
 */
import { lazyWithPreload as lazy } from "../lazyWithPreload";

// Named — also re-exported from routeDefinitions.jsx for App.jsx
export const AuthPage = lazy(() => import("@/pages/AuthPage"));
export const Dashboard = lazy(() => import("@/pages/Dashboard"));
export const LandingPage = lazy(() => import("@/pages/LandingPage"));
export const PrivacyPolicy = lazy(() => import("@/pages/PrivacyPolicy"));
export const GuestPortal = lazy(() => import("@/pages/GuestPortal"));

// Core modules
export const PMSModule = lazy(() => import("@/pages/PMSModule"));
export const InvoiceModule = lazy(() => import("@/pages/InvoiceModule"));
export const RMSModule = lazy(() => import("@/pages/RMSModule"));
export const ChannelManagerModule = lazy(() => import("@/pages/ChannelManagerModule"));
export const ChannelManagerDashboardV2 = lazy(() => import("@/pages/ChannelManagerDashboardV2"));
export const MappingManager = lazy(() => import("@/pages/MappingManager"));
export const ReservationLineage = lazy(() => import("@/pages/ReservationLineage"));
export const ReservationCalendar = lazy(() => import("@/pages/ReservationCalendar"));
export const Settings = lazy(() => import("@/pages/Settings"));
export const ProfilePage = lazy(() => import("@/pages/ProfilePage"));
export const PCIComplianceDashboard = lazy(() => import("@/pages/PCIComplianceDashboard"));
export const XchangePage = lazy(() => import("@/pages/XchangePage"));
export const MicePage = lazy(() => import("@/pages/MicePage"));
export const ProcurementPage = lazy(() => import("@/pages/ProcurementPage"));
export const InventoryProcurementGuide = lazy(() => import("@/pages/InventoryProcurementGuide"));
export const MailingPage = lazy(() => import("@/pages/MailingPage"));
export const ModuleStorePage = lazy(() => import("@/pages/ModuleStorePage"));
export const AfsadakatLauncher = lazy(() => import("@/pages/AfsadakatLauncher"));
export const OnboardingWizard = lazy(() => import("@/pages/OnboardingWizard"));
export const ResetPasswordPage = lazy(() => import("@/pages/ResetPasswordPage"));
export const PendingAR = lazy(() => import("@/pages/PendingAR"));
export const CityLedgerAccounts = lazy(() => import("@/pages/CityLedgerAccounts"));
export const LoyaltyModule = lazy(() => import("@/pages/LoyaltyModule"));
export const MarketplaceModule = lazy(() => import("@/pages/MarketplaceModule"));
export const SuppliesMarket = lazy(() => import("@/pages/SuppliesMarket"));
export const VendorPortal = lazy(() => import("@/pages/VendorPortal"));
export const HotelInventory = lazy(() => import("@/pages/HotelInventory"));
export const InventoryTransferHistory = lazy(() => import("@/pages/InventoryTransferHistory"));
export const TemplateManager = lazy(() => import("@/pages/TemplateManager"));
export const SelfCheckin = lazy(() => import("@/pages/SelfCheckin"));
export const PreCheckinPage = lazy(() => import("@/pages/PreCheckinPage"));
export const DigitalKey = lazy(() => import("@/pages/DigitalKey"));
export const UpsellStore = lazy(() => import("@/pages/UpsellStore"));
export const StaffMobileApp = lazy(() => import("@/pages/StaffMobileApp"));
export const StaffRoomServiceOrders = lazy(() => import("@/pages/StaffRoomServiceOrders"));
export const OTAMessagingHub = lazy(() => import("@/pages/OTAMessagingHub"));
export const EFaturaModule = lazy(() => import("@/pages/EFaturaModule"));
export const MessagingCenter = lazy(() => import("@/pages/MessagingCenter"));
export const SalesModule = lazy(() => import("@/pages/SalesModule"));
export const GroupReservations = lazy(() => import("@/pages/GroupReservations"));
export const MultiPropertyDashboard = lazy(() => import("@/pages/MultiPropertyDashboard"));
export const HousekeepingMobileApp = lazy(() => import("@/pages/HousekeepingMobileApp"));
export const AIEnhancedPMS = lazy(() => import("@/pages/AIEnhancedPMS"));
export const Reports = lazy(() => import("@/pages/Reports"));
export const BasicReports = lazy(() => import("@/pages/BasicReports"));
export const ReportBuilder = lazy(() => import("@/pages/ReportBuilder"));
export const PmsLiteLanding = lazy(() => import("@/pages/PmsLiteLanding"));
export const AdminLeads = lazy(() => import("@/pages/AdminLeads"));
export const GovernancePanel = lazy(() => import("@/pages/GovernancePanel"));
export const NoShowAnalytics = lazy(() => import("@/pages/NoShowAnalytics"));
export const OfficialGuestList = lazy(() => import("@/pages/OfficialGuestList"));

// Mobile
export const MobileDashboard = lazy(() => import("@/pages/MobileDashboard"));
export const MobileHousekeeping = lazy(() => import("@/pages/MobileHousekeeping"));
export const MobileFrontDesk = lazy(() => import("@/pages/MobileFrontDesk"));
export const MobileFnB = lazy(() => import("@/pages/MobileFnB"));
export const MobileMaintenance = lazy(() => import("@/pages/MobileMaintenance"));
export const MobileFinance = lazy(() => import("@/pages/MobileFinance"));
export const MobileSecurity = lazy(() => import("@/pages/MobileSecurity"));
export const MobileGM = lazy(() => import("@/pages/MobileGM"));
export const MobileOrderTracking = lazy(() => import("@/pages/MobileOrderTracking"));
export const MobileInventory = lazy(() => import("@/pages/MobileInventory"));
export const MobileApprovals = lazy(() => import("@/pages/MobileApprovals"));
export const MobileLogViewer = lazy(() => import("@/pages/MobileLogViewer"));
export const SalesCRMMobile = lazy(() => import("@/pages/SalesCRMMobile"));
export const RateManagementMobile = lazy(() => import("@/pages/RateManagementMobile"));
export const RevenueMobile = lazy(() => import("@/pages/RevenueMobile"));
export const ChannelManagerMobile = lazy(() => import("@/pages/ChannelManagerMobile"));
export const CorporateContractsMobile = lazy(() => import("@/pages/CorporateContractsMobile"));

// Executive / GM / Misc
export const ExecutiveDashboard = lazy(() => import("@/pages/ExecutiveDashboard"));
export const KonaklamaVergisiModule = lazy(() => import("@/pages/KonaklamaVergisiModule"));
export const HelpCenter = lazy(() => import("@/pages/HelpCenter"));
export const MevzuatRaporlari = lazy(() => import("@/pages/MevzuatRaporlari"));
export const SimpleAdminPanel = lazy(() => import("@/pages/SimpleAdminPanel"));
export const MigrationObservabilityPage = lazy(() => import("@/pages/MigrationObservabilityPage"));
export const SystemPerformanceMonitor = lazy(() => import("@/pages/SystemPerformanceMonitor"));
export const LogViewer = lazy(() => import("@/pages/LogViewer"));
export const NetworkTestTools = lazy(() => import("@/pages/NetworkTestTools"));
export const MaintenancePriorityVisual = lazy(() => import("@/pages/MaintenancePriorityVisual"));
export const FeaturesShowcase = lazy(() => import("@/pages/FeaturesShowcase"));
export const HousekeepingDashboard = lazy(() => import("@/pages/HousekeepingDashboard"));
export const POSDashboard = lazy(() => import("@/pages/POSDashboard"));
export const POSExtensions = lazy(() => import("@/pages/POSExtensions"));

// Admin
export const AdminTenants = lazy(() => import("@/pages/AdminTenants"));
export const AdminVendors = lazy(() => import("@/pages/AdminVendors"));
export const QuickIdSettings = lazy(() => import("@/pages/admin/QuickIdSettings"));
export const RoomQrCodes = lazy(() => import("@/pages/admin/RoomQrCodes"));
export const RoomRequests = lazy(() => import("@/pages/RoomRequests"));
export const RoomRequestPage = lazy(() => import("@/pages/guest/RoomRequestPage"));
export const PublicReviewPage = lazy(() => import("@/pages/PublicReviewPage"));
export const ModuleReport = lazy(() => import("@/pages/ModuleReport"));
export const UserRoleManager = lazy(() => import("@/pages/UserRoleManager"));
export const RnlAutoResolveRuns = lazy(() => import("@/pages/admin/RnlAutoResolveRuns"));
export const RnlDuplicates = lazy(() => import("@/pages/admin/RnlDuplicates"));

// AI / Guest
export const AIModule = lazy(() => import("@/pages/AIModule"));
export const OnlineCheckin = lazy(() => import("@/pages/OnlineCheckin"));
export const FlashReport = lazy(() => import("@/pages/FlashReport"));
export const GroupSales = lazy(() => import("@/pages/GroupSales"));
export const SalesCRM = lazy(() => import("@/pages/SalesCRM"));
export const ServiceRecovery = lazy(() => import("@/pages/ServiceRecovery"));
export const SpaWellness = lazy(() => import("@/pages/SpaWellness"));
export const AIChatbot = lazy(() => import("@/pages/AIChatbot"));
export const DynamicPricing = lazy(() => import("@/pages/DynamicPricing"));
export const MultiProperty = lazy(() => import("@/pages/MultiProperty"));
export const StaffManagement = lazy(() => import("@/pages/StaffManagement"));
export const StaffProfile = lazy(() => import("@/pages/StaffProfile"));
export const ShiftPlannerPage = lazy(() => import("@/pages/ShiftPlannerPage"));
export const GuestJourney = lazy(() => import("@/pages/GuestJourney"));
export const ArrivalList = lazy(() => import("@/pages/ArrivalList"));
export const DepartureList = lazy(() => import("@/pages/DepartureList"));
export const NoShowToday = lazy(() => import("@/pages/NoShowToday"));
export const AIWhatsAppConcierge = lazy(() => import("@/pages/AIWhatsAppConcierge"));
export const PredictiveAnalytics = lazy(() => import("@/pages/PredictiveAnalytics"));
export const TravelAgentARAP = lazy(() => import("@/pages/TravelAgentARAP"));
export const AgencyRequests = lazy(() => import("@/pages/AgencyRequests"));
export const IncomingAgencyContracts = lazy(() => import("@/pages/IncomingAgencyContracts"));
export const AgencyManagement = lazy(() => import("@/pages/AgencyManagement"));
export const AgencyContentDistribution = lazy(() => import("@/pages/AgencyContentDistribution"));
export const AgencyPortalDashboard = lazy(() => import("@/pages/AgencyPortalDashboard"));
export const B2BAnalyticsDashboard = lazy(() => import("@/pages/B2BAnalyticsDashboard"));
export const ReportScheduler = lazy(() => import("@/pages/ReportScheduler"));
export const SocialMediaRadar = lazy(() => import("@/pages/SocialMediaRadar"));
export const RevenueAutopilot = lazy(() => import("@/pages/RevenueAutopilot"));
export const HRComplete = lazy(() => import("@/pages/HRComplete"));
export const FnBComplete = lazy(() => import("@/pages/FnBComplete"));
export const FnbBeoGenerator = lazy(() => import("@/pages/FnbBeoGenerator"));
export const KitchenDisplay = lazy(() => import("@/pages/KitchenDisplay"));

// Night audit / dashboards
export const NightAuditLogs = lazy(() => import("@/pages/NightAuditLogs"));
export const NightAuditDashboard = lazy(() => import("@/pages/NightAuditDashboard"));
export const PMSOperationalDashboard = lazy(() => import("@/pages/PMSOperationalDashboard"));
export const FolioDetailView = lazy(() => import("@/pages/FolioDetailView"));
export const RevenueEngineDashboard = lazy(() => import("@/pages/RevenueEngineDashboard"));
export const OperationalEventDashboard = lazy(() => import("@/pages/OperationalEventDashboard"));
export const GuestJourneyDashboard = lazy(() => import("@/pages/GuestJourneyDashboard"));
export const PlatformScalingDashboard = lazy(() => import("@/pages/PlatformScalingDashboard"));
export const DataIntelligenceDashboard = lazy(() => import("@/pages/DataIntelligenceDashboard"));
export const MessagingDashboard = lazy(() => import("@/pages/MessagingDashboard"));
export const MLSchedulerDashboard = lazy(() => import("@/pages/MLSchedulerDashboard"));
export const RevenueAutopilotDashboard = lazy(() => import("@/pages/RevenueAutopilotDashboard"));
export const AnalyticsExportDashboard = lazy(() => import("@/pages/AnalyticsExportDashboard"));
export const DisplacementAnalysis = lazy(() => import("@/pages/DisplacementAnalysis"));
export const GelirYonetimiPage = lazy(() => import("@/pages/GelirYonetimiPage"));
export const AIZekaPage = lazy(() => import("@/pages/AIZekaPage"));
export const AnalitikRaporlarPage = lazy(() => import("@/pages/AnalitikRaporlarPage"));
export const FrontdeskAuditChecklist = lazy(() => import("@/pages/FrontdeskAuditChecklist"));
export const CorporateContractsDashboard = lazy(() => import("@/pages/CorporateContractsDashboard"));
export const CorporateContractApprovals = lazy(() => import("@/pages/CorporateContractApprovals"));

// Maintenance
export const MaintenanceWorkOrders = lazy(() => import("@/pages/MaintenanceWorkOrders"));
export const MaintenanceAssets = lazy(() => import("@/pages/MaintenanceAssets"));
export const MaintenancePlans = lazy(() => import("@/pages/MaintenancePlans"));

// Security / Compliance
export const SecurityCenter = lazy(() => import("@/pages/SecurityCenter"));
export const SecurityDashboard = lazy(() => import("@/pages/SecurityDashboard"));
export const GDPRCompliance = lazy(() => import("@/pages/GDPRCompliance"));
export const CentralOfficeDashboard = lazy(() => import("@/pages/CentralOfficeDashboard"));
export const CentralPricingManager = lazy(() => import("@/pages/CentralPricingManager"));
export const CrossPropertyGuests = lazy(() => import("@/pages/CrossPropertyGuests"));
export const MLDashboard = lazy(() => import("@/pages/MLDashboard"));
export const IntegrationHub = lazy(() => import("@/pages/IntegrationHub"));
export const AdminControlPanel = lazy(() => import("@/pages/AdminControlPanel"));
export const DataPipelineDashboard = lazy(() => import("@/pages/DataPipelineDashboard"));
export const EventBusDashboard = lazy(() => import("@/pages/EventBusDashboard"));
export const ObservabilityDashboard = lazy(() => import("@/pages/ObservabilityDashboard"));
export const SecurityHardeningDashboard = lazy(() => import("@/pages/SecurityHardeningDashboard"));
export const SystemHealthDashboard = lazy(() => import("@/pages/SystemHealthDashboard"));
export const RuntimeInfrastructureDashboard = lazy(() => import("@/pages/RuntimeInfrastructureDashboard"));
export const InfraHardeningDashboard = lazy(() => import("@/pages/InfraHardeningDashboard"));
export const ProductionGoLiveDashboard = lazy(() => import("@/pages/ProductionGoLiveDashboard"));
export const AuditTimelinePage = lazy(() => import("@/pages/AuditTimelinePage"));
export const UrgentMessageReportPage = lazy(() => import("@/pages/UrgentMessageReportPage"));
export const RecalledMessagesReportPage = lazy(() => import("@/pages/RecalledMessagesReportPage"));
export const IdPhotoViewReportPage = lazy(() => import("@/pages/IdPhotoViewReportPage"));
export const IdPhotoAdminPage = lazy(() => import("@/pages/IdPhotoAdminPage"));
export const UrgentPermissionAdminPage = lazy(() => import("@/pages/UrgentPermissionAdminPage"));
export const PilotReadinessPage = lazy(() => import("@/pages/PilotReadinessPage"));
export const IncidentDashboardPage = lazy(() => import("@/pages/IncidentDashboardPage"));
export const GoLiveDashboardPage = lazy(() => import("@/pages/GoLiveDashboardPage"));
export const ProductionRolloutPage = lazy(() => import("@/pages/ProductionRolloutPage"));
export const SoakTestDashboard = lazy(() => import("@/pages/SoakTestDashboard"));

// Channel manager
export const HotelRunnerIntegration = lazy(() => import("@/pages/HotelRunnerIntegration"));
export const HRv2OpsDashboard = lazy(() => import("@/pages/HRv2OpsDashboard"));
export const ExelyIntegration = lazy(() => import("@/pages/ExelyIntegration"));
export const ChannelConnections = lazy(() => import("@/pages/ChannelConnections"));
export const ARIPushDashboard = lazy(() => import("@/pages/ARIPushDashboard"));
export const UnifiedRateManager = lazy(() => import("@/pages/UnifiedRateManager"));
export const WireFailureDashboard = lazy(() => import("@/pages/WireFailureDashboard"));
export const PIIStrictModeDashboard = lazy(() => import("@/pages/PIIStrictModeDashboard"));
export const DataModelDashboard = lazy(() => import("@/pages/DataModelDashboard"));
export const LockdownDashboard = lazy(() => import("@/pages/LockdownDashboard"));
export const OperatorIncidentPanel = lazy(() => import("@/pages/OperatorIncidentPanel"));
export const RuntimeCockpitPage = lazy(() => import("@/pages/RuntimeCockpitPage"));
export const ControlPlane = lazy(() => import("@/pages/ControlPlane"));

// PMS extras
export const GroupBookingsPage = lazy(() => import("@/pages/GroupBookings"));
export const DepositTrackingPage = lazy(() => import("@/pages/DepositTracking"));
export const HousekeepingStatusPage = lazy(() => import("@/pages/HousekeepingStatusPage"));
export const ShiftHandoverPage = lazy(() => import("@/pages/ShiftHandoverPage"));
export const EarlyLatePricingSettings = lazy(() => import("@/pages/EarlyLatePricingSettings"));
export const EodReportPage = lazy(() => import("@/pages/EodReportPage"));
export const WalkinPage = lazy(() => import("@/pages/WalkinPage"));
export const RoomMapPage = lazy(() => import("@/pages/RoomMapPage"));
export const WakeUpCallsPage = lazy(() => import("@/pages/WakeUpCallsPage"));
export const LostFoundPage = lazy(() => import("@/pages/LostFoundPage"));
export const GroupFolioPage = lazy(() => import("@/pages/GroupFolioPage"));
export const RoomMappingWizard = lazy(() => import("@/pages/RoomMappingWizard"));
export const B2BApiDocs = lazy(() => import("@/pages/B2BApiDocs"));
export const ChannelOpsPage = lazy(() => import("@/pages/ChannelOpsPage"));

// Hubs
export const SecurityHub = lazy(() => import("@/pages/SecurityHub"));
export const ChannelHub = lazy(() => import("@/pages/ChannelHub"));
export const ConflictQueuePage = lazy(() => import("@/pages/ConflictQueuePage"));
export const RevenueHub = lazy(() => import("@/pages/RevenueHub"));
export const AdminHub = lazy(() => import("@/pages/AdminHub"));
export const HRHub = lazy(() => import("@/pages/HRHub"));
export const GoLiveReadinessCockpit = lazy(() => import("@/pages/GoLiveReadinessCockpit"));
export const EncryptionManagementPage = lazy(() => import("@/pages/EncryptionManagementPage"));
export const WebhookOutboxAdmin = lazy(() => import("@/pages/WebhookOutboxAdmin"));
export const EarlyWarningDashboard = lazy(() => import("@/pages/EarlyWarningDashboard"));
export const ModuleDiscovery = lazy(() => import("@/pages/ModuleDiscovery"));
export const IntegrationCredentials = lazy(() => import("@/pages/IntegrationCredentials"));
export const IntegrationsOverview = lazy(() => import("@/pages/admin/IntegrationsOverview"));
export const CapXIntegration = lazy(() => import("@/pages/CapXIntegration"));

// Opera-parity additions
export const FolioRoutingPage = lazy(() => import("@/pages/FolioRoutingPage"));
export const LoyaltyAdminPage = lazy(() => import("@/pages/LoyaltyAdminPage"));
export const ActivitySchedulerPage = lazy(() => import("@/pages/ActivitySchedulerPage"));
export const BlockManagementPage = lazy(() => import("@/pages/BlockManagementPage"));
export const ForecastReportsPage = lazy(() => import("@/pages/ForecastReportsPage"));
export const FunctionSpacePage = lazy(() => import("@/pages/FunctionSpacePage"));
export const TrialBalancePage = lazy(() => import("@/pages/TrialBalancePage"));
export const ProfileUdfPage = lazy(() => import("@/pages/ProfileUdfPage"));
export const CateringMenuPage = lazy(() => import("@/pages/CateringMenuPage"));
export const SuiteConnectingPage = lazy(() => import("@/pages/SuiteConnectingPage"));
export const HurdleRatesPage = lazy(() => import("@/pages/HurdleRatesPage"));
