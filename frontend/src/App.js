import { useState, useEffect, Suspense, lazy } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import PlanRouteGuard from "@/components/PlanRouteGuard";
import axios from "axios";
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { queryClient } from '@/lib/queryClient';
import usePushNotifications from '@/hooks/usePushNotifications';
import { NotificationProvider } from '@/context/NotificationContext';
import NotificationCenter from '@/components/NotificationCenter';

// Critical imports - loaded immediately
import AuthPage from "@/pages/AuthPage";
import Dashboard from "@/pages/Dashboard";

// Lazy load all other pages for faster initial load
const GMDashboard = lazy(() => import("@/pages/GMDashboard"));
const EnhancedGMDashboard = lazy(() => import("@/pages/EnhancedGMDashboard"));
const PMSModule = lazy(() => import("@/pages/PMSModule"));
const InvoiceModule = lazy(() => import("@/pages/InvoiceModule"));
const RMSModule = lazy(() => import("@/pages/RMSModule"));
const ChannelManagerModule = lazy(() => import("@/pages/ChannelManagerModule"));
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
const RevenueManagementMobile = lazy(() => import("@/pages/RevenueManagementMobile"));
const GMEnhancedDashboard = lazy(() => import("@/pages/GMEnhancedDashboard"));
const SalesCRMMobile = lazy(() => import("@/pages/SalesCRMMobile"));
import LandingPage from "@/pages/LandingPage";
import PrivacyPolicy from "@/pages/PrivacyPolicy";
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

// New 5-star hotel features
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
const SocialMediaRadar = lazy(() => import("@/pages/SocialMediaRadar"));
const RevenueAutopilot = lazy(() => import("@/pages/RevenueAutopilot"));
const HRComplete = lazy(() => import("@/pages/HRComplete"));
const FnBComplete = lazy(() => import("@/pages/FnBComplete"));
const FnbBeoGenerator = lazy(() => import("@/pages/FnbBeoGenerator"));
const KitchenDisplay = lazy(() => import("@/pages/KitchenDisplay"));
const NightAuditLogs = lazy(() => import("@/pages/NightAuditLogs"));
const FrontdeskAuditChecklist = lazy(() => import("@/pages/FrontdeskAuditChecklist"));
const CorporateContractsDashboard = lazy(() => import("@/pages/CorporateContractsDashboard"));
const MaintenanceWorkOrders = lazy(() => import("@/pages/MaintenanceWorkOrders"));
const MaintenanceAssets = lazy(() => import("@/pages/MaintenanceAssets"));
const MaintenancePlans = lazy(() => import("@/pages/MaintenancePlans"));

// New modules - Security, Compliance, Multi-Property, ML
const SecurityCenter = lazy(() => import("@/pages/SecurityCenter"));
const SecurityDashboard = lazy(() => import("@/pages/SecurityDashboard"));
const GDPRCompliance = lazy(() => import("@/pages/GDPRCompliance"));
const CentralOfficeDashboard = lazy(() => import("@/pages/CentralOfficeDashboard"));
const CentralPricingManager = lazy(() => import("@/pages/CentralPricingManager"));
const CrossPropertyGuests = lazy(() => import("@/pages/CrossPropertyGuests"));
const MLDashboard = lazy(() => import("@/pages/MLDashboard"));

import { Toaster } from "@/components/ui/sonner";

// Loading component
const LoadingFallback = () => (
  <div className="flex items-center justify-center h-screen">
    <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
  </div>
);

const RAW_BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '/api';
// Ensure /api suffix for Kubernetes ingress routing
const BACKEND_URL = RAW_BACKEND_URL.endsWith('/api')
  ? RAW_BACKEND_URL
  : RAW_BACKEND_URL.replace(/\/+$/, '') + '/api';

console.log('🔍 Backend Configuration:', {
  RAW_BACKEND_URL,
  BACKEND_URL,
});

// Use environment variable for backend URL with /api suffix
console.log('🔍 Setting axios.defaults.baseURL to:', BACKEND_URL);
axios.defaults.baseURL = BACKEND_URL;
axios.defaults.timeout = 30000;

// Setup axios interceptor for token and caching
axios.interceptors.request.use(
  (config) => {
    const url = config.url || '';

    const isPublicAuthEndpoint =
      url.includes('/auth/login') ||
      url.includes('/auth/register') ||
      url.includes('/auth/forgot-password') ||
      url.includes('/auth/reset-password');

    if (!config.headers) {
      config.headers = {};
    }

    // Get token from localStorage for every request
    // Only attach token for non-public endpoints
    if (!isPublicAuthEndpoint) {
      const token = localStorage.getItem('token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    } else {
      // Ensure no Authorization header is sent for public auth endpoints
      if (config.headers.Authorization) {
        delete config.headers.Authorization;
      }
    }

    // Add cache headers for GET requests
    if (config.method === 'get') {
      config.headers['Cache-Control'] = 'max-age=60'; // Cache for 60 seconds
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Setup response interceptor for 401 errors
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn('⚠️ 401 Unauthorized - Token may be invalid');
      // Don't auto-logout on first 401, let app handle it
    }
    return Promise.reject(error);
  }
);

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [tenant, setTenant] = useState(null);
  const [modules, setModules] = useState(null);
  const [loading, setLoading] = useState(true);

  usePushNotifications(isAuthenticated ? user : null);

  // Setup axios interceptor for handling auth errors - DISABLED for now
  // The aggressive logout was causing issues with optional endpoints
  // useEffect(() => {
  //   const interceptor = axios.interceptors.response.use(
  //     (response) => response,
  //     (error) => {
  //       // If we get 401 Unauthorized, logout the user
  //       if (error.response && error.response.status === 401) {
  //         console.warn('Authentication error detected, logging out...');
  //         handleLogout();
  //       }
  //       return Promise.reject(error);
  //     }
  //   );

  //   // Cleanup interceptor on unmount
  //   return () => {
  //     axios.interceptors.response.eject(interceptor);
  //   };
  // }, []);

  useEffect(() => {
    console.log('🔄 App mounting - checking auth state...');
    const token = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    const storedTenant = localStorage.getItem('tenant');
    const storedModules = localStorage.getItem('modules');
    
    console.log('📦 LocalStorage check:', {
      hasToken: !!token,
      hasUser: !!storedUser,
      hasTenant: !!storedTenant,
      hasModules: !!storedModules,
    });
    
    if (token && storedUser) {
      // Set authorization header for all future requests
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      
      // Call /auth/me to get fresh user data with current role
      console.log('🔍 Fetching fresh user data from /auth/me...');
      axios.get('/auth/me')
        .then(meResponse => {
          const freshUser = meResponse.data;
          
          console.log('✅ Fresh user data received:', freshUser);
          console.log('🎭 Fresh role:', freshUser.role);
          
          // Update localStorage with fresh data
          localStorage.setItem('user', JSON.stringify(freshUser));
          setUser(freshUser);
          
          // Parse tenant and modules
          let parsedTenant = null;
          if (storedTenant && storedTenant !== 'null') {
            try {
              parsedTenant = JSON.parse(storedTenant);
            } catch (e) {
              console.warn('Failed to parse tenant data:', e);
            }
          }

          let parsedModules = null;
          if (storedModules) {
            try {
              parsedModules = JSON.parse(storedModules);
              setModules(parsedModules);
            } catch (e) {
              console.warn('Failed to parse modules data:', e);
            }
          }

          // Tenant nesnesine modules alanını merge et
          if (parsedTenant) {
            setTenant(parsedModules ? { ...parsedTenant, modules: parsedModules } : parsedTenant);
          } else {
            setTenant(null);
          }
          setIsAuthenticated(true);
          console.log('✅ Auth state restored with fresh data');
        })
        .catch(e => {
          console.error('❌ Failed to verify token or fetch user:', e);
          // Clear invalid data
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          localStorage.removeItem('tenant');
          localStorage.removeItem('modules');
          setIsAuthenticated(false);
        })
        .finally(() => {
          setLoading(false);
        });
    } else {
      console.log('ℹ️ No auth data found in localStorage');
      setLoading(false);
    }
  }, []);

  const handleLogin = (token, userData, tenantData) => {
    console.log('🔐 handleLogin called with:', { 
      token: token?.substring(0, 20) + '...', 
      userData: userData,
      userRole: userData?.role,
      tenantData: tenantData 
    });
    
    // IMPORTANT: Clear old data first to prevent stale data
    localStorage.clear();
    
    // Then set new data
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(userData));
    localStorage.setItem('tenant', tenantData ? JSON.stringify(tenantData) : 'null');

    // Tenant modüllerini subscription endpoint'inden çek
    const fetchModules = async () => {
      try {
        const res = await axios.get('/subscription/current');
        const tenantModules = res.data?.modules || null;
        if (tenantModules) {
          localStorage.setItem('modules', JSON.stringify(tenantModules));
          setModules(tenantModules);
        }
      } catch (error) {
        console.warn('Failed to load tenant modules, using default behavior (all enabled).', error);
      }
    };

    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    setUser(userData);
    setTenant(tenantData);
    setIsAuthenticated(true);
    fetchModules();
    console.log('✅ Auth state updated:', { isAuthenticated: true, user: userData?.email, role: userData?.role });
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('tenant');
    localStorage.removeItem('modules');
    delete axios.defaults.headers.common['Authorization'];
    setUser(null);
    setTenant(null);
    setModules(null);
    setIsAuthenticated(false);
  };

  if (loading) {
    return (
      <div className="loading-screen" style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
      }}>
        <div style={{ textAlign: 'center', color: 'white' }}>
          <div className="spinner" style={{
            border: '4px solid rgba(255,255,255,0.3)',
            borderTop: '4px solid white',
            borderRadius: '50%',
            width: '40px',
            height: '40px',
            animation: 'spin 1s linear infinite',
            margin: '0 auto 1rem'
          }}></div>
          <p>Yükleniyor...</p>
        </div>
      </div>
    );
  }

  // Guest user routes
  if (isAuthenticated && user?.role === 'guest') {
    return (
      <NotificationProvider>
        <QueryClientProvider client={queryClient}>
          <div className="App">
            <Toaster position="top-right" />
            <BrowserRouter>
              <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/privacy-policy" element={<PrivacyPolicy />} />
                <Route path="/gizlilik" element={<PrivacyPolicy />} />
                <Route path="/guest-portal/*" element={<GuestPortal user={user} onLogout={handleLogout} />} />
              </Routes>
            </BrowserRouter>
            <NotificationCenter />
          </div>
        </QueryClientProvider>
      </NotificationProvider>
    );
  }
  const hasFeature = (key) => {
    if (!key) return true;
    if ((user?.roles || []).includes('super_admin') || user?.role === 'super_admin') return true;
    return !!tenant?.features?.[key];
  };



  // Hotel admin routes
  return (
    <NotificationProvider>
      <QueryClientProvider client={queryClient}>
        <div className="App">
          <Toaster position="top-right" />
          <BrowserRouter>
          <PlanRouteGuard tenant={tenant} user={user}>
          <Routes>
          {/* Public Landing Page */}
          <Route path="/landing" element={<LandingPage />} />
          <Route path="/privacy-policy" element={<PrivacyPolicy />} />
          <Route path="/gizlilik" element={<PrivacyPolicy />} />
          <Route path="/login" element={<Navigate to="/auth" replace />} />
          
          {/* Simple Admin Panel - No auth required for easy access */}
          <Route path="/system-status" element={<SimpleAdminPanel />} />
          
          <Route
            path="/app/dashboard"
            element={
              isAuthenticated ? (
                <Dashboard user={user} tenant={tenant} modules={modules} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/migration-observability"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <MigrationObservabilityPage user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/"
            element={
              isAuthenticated ? (
                <Navigate to="/app/dashboard" replace />
              ) : (
                <LandingPage />
              )
            }
          />
          <Route path="/pms-lite" element={<PmsLiteLanding />} />
          <Route
            path="/gm-classic"
            element={
              isAuthenticated && modules?.gm_dashboards !== false ? (
                <GMDashboard user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/dashboard-simple"
            element={
              isAuthenticated ? (
                <Dashboard user={user} tenant={tenant} modules={modules} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/auth"
            element={
              !isAuthenticated ? (
                <AuthPage onLogin={handleLogin} />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/ai-pms"
            element={
              isAuthenticated ? (
                <AIEnhancedPMS user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/ai"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <AIModule user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/pms"
            element={
              isAuthenticated ? (
                <PMSModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/pms"
            element={
              isAuthenticated ? (
                <PMSModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/invoices"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <InvoiceModule user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/invoices"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <InvoiceModule user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/rms"
            element={
              isAuthenticated && hasFeature('hidden_rms') ? (
                <RMSModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : isAuthenticated ? (
                <Navigate to="/" replace />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/rms"
            element={
              isAuthenticated && hasFeature('hidden_rms') ? (
                <RMSModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : isAuthenticated ? (
                <Navigate to="/" replace />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/channel-manager"
            element={
              isAuthenticated ? (
                <ChannelManagerModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/channel-manager"
            element={
              isAuthenticated ? (
                <ChannelManagerModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/reservation-calendar"
            element={
              isAuthenticated ? (
                <ReservationCalendar user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/reservation-calendar"
            element={
              isAuthenticated ? (
                <ReservationCalendar user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/settings"
            element={
              isAuthenticated ? (
                <Settings user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/settings"
            element={
              isAuthenticated ? (
                <Settings user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />

          <Route
            path="/pending-ar"
            element={
              isAuthenticated ? (
                <PendingAR user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/city-ledger"
            element={
              isAuthenticated ? (
                <CityLedgerAccounts user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/loyalty"
            element={
              isAuthenticated ? (
                <LoyaltyModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/marketplace"
            element={
              isAuthenticated && hasFeature('hidden_marketplace') ? (
                <MarketplaceModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : isAuthenticated ? (
                <Navigate to="/" replace />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/marketplace"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <MarketplaceModule user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/hotel-inventory"
            element={
              isAuthenticated ? (
                <HotelInventory user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/templates"
            element={
              isAuthenticated ? (
                <TemplateManager user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/guest/checkin/:bookingId"
            element={
              isAuthenticated ? (
                <SelfCheckin bookingId={window.location.pathname.split('/').pop()} onComplete={() => window.location.href = '/guest/portal'} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/guest/digital-key/:bookingId"
            element={
              isAuthenticated ? (
                <DigitalKey bookingId={window.location.pathname.split('/').pop()} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/guest/upsell/:bookingId"
            element={
              isAuthenticated ? (
                <UpsellStore bookingId={window.location.pathname.split('/').pop()} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/staff/mobile"
            element={
              isAuthenticated ? (
                <StaffMobileApp user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/ota-messaging-hub"
            element={
              isAuthenticated ? (
                <OTAMessagingHub user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/messaging-center"
            element={
              isAuthenticated ? (
                <MessagingCenter user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/sales"
            element={
              isAuthenticated ? (
                <SalesModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/frontdesk/audit-checklist"
            element={
              isAuthenticated ? (
                <FrontdeskAuditChecklist user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/reports/corporate-contracts"
            element={
              isAuthenticated ? (
                <CorporateContractsDashboard user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/maintenance/work-orders"
            element={
              isAuthenticated ? (
                <MaintenanceWorkOrders user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/agency-requests"
            element={
              isAuthenticated ? (
                <AgencyRequests user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />

          <Route
            path="/maintenance/assets"
            element={
              isAuthenticated ? (
                <MaintenanceAssets user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/maintenance/plans"
            element={
              isAuthenticated ? (
                <MaintenancePlans user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />

          <Route
            path="/efatura"
            element={
              isAuthenticated ? (
                <EFaturaModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/e-fatura"
            element={
              isAuthenticated ? (
                <EFaturaModule user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/group-reservations"
            element={
              isAuthenticated ? (
                <GroupReservations user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/multi-property-dashboard"
            element={
              isAuthenticated ? (
                <MultiPropertyDashboard user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/housekeeping-mobile-app"
            element={
              isAuthenticated ? (
                <HousekeepingMobileApp user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/reports"
            element={
              isAuthenticated ? (
                <Reports user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/reports"
            element={
              isAuthenticated ? (
                <Reports user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/raporlar"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <BasicReports user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/gelismis-raporlar"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <Reports user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/reports/builder"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <ReportBuilder user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/rapor-olusturucu"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <ReportBuilder user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/reports/official-guest-list"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <OfficialGuestList user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          {/* Mobile Department Routes */}
          <Route
            path="/mobile"
            element={
              isAuthenticated && modules?.pms_mobile !== false ? (
                <MobileDashboard user={user} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/housekeeping"
            element={
              isAuthenticated && modules?.mobile_housekeeping !== false ? (
                <MobileHousekeeping user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/frontdesk"
            element={
              isAuthenticated ? (
                <MobileFrontDesk user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/fnb"
            element={
              isAuthenticated ? (
                <MobileFnB user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/maintenance"
            element={
              isAuthenticated ? (
                <MobileMaintenance user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/finance"
            element={
              isAuthenticated ? (
                <MobileFinance user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/night-audit/logs"
            element={
              isAuthenticated ? (
                <NightAuditLogs user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/gm"
            element={
              isAuthenticated ? (
                <MobileGM user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/maintenance/priority-visual"
            element={
              isAuthenticated ? (
                <MaintenancePriorityVisual user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/security"
            element={
              isAuthenticated ? (
                <MobileSecurity user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/order-tracking"
            element={
              isAuthenticated ? (
                <MobileOrderTracking user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/inventory"
            element={
              isAuthenticated ? (
                <MobileInventory user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/approvals"
            element={
              isAuthenticated ? (
                <MobileApprovals user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/executive"
            element={
              isAuthenticated && modules?.gm_dashboards !== false ? (
                <ExecutiveDashboard user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/revenue"
            element={
              isAuthenticated && modules?.mobile_revenue !== false ? (
                <RevenueMobile user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/gm/enhanced"
            element={
              isAuthenticated && modules?.gm_dashboards !== false ? (
                <GMEnhancedDashboard user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/sales"
            element={
              isAuthenticated ? (
                <SalesCRMMobile user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/rates"
            element={
              isAuthenticated ? (
                <RateManagementMobile user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/revenue"
            element={
              isAuthenticated && modules?.mobile_revenue !== false ? (
                <RevenueMobile user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/channels"
            element={
              isAuthenticated ? (
                <ChannelManagerMobile user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/corporate"
            element={
              isAuthenticated ? (
                <CorporateContractsMobile user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/system/performance"
            element={
              isAuthenticated ? (
                <SystemPerformanceMonitor user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/system/logs"
            element={
              isAuthenticated ? (
                <LogViewer user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/mobile/logs"
            element={
              isAuthenticated ? (
                <MobileLogViewer user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/network/test"
            element={
              isAuthenticated ? (
                <NetworkTestTools user={user} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/cost-management"
            element={
              isAuthenticated ? (
                <CostManagement user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/cost-management"
            element={
              isAuthenticated ? (
                <CostManagement user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/features"
            element={
              isAuthenticated ? (
                <FeaturesShowcase user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/housekeeping"
            element={
              isAuthenticated ? (
                <HousekeepingDashboard user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/pos"
            element={
              isAuthenticated ? (
                <POSDashboard user={user} tenant={tenant} onLogout={handleLogout} />
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/admin/tenants"
            element={
              isAuthenticated && user?.role === 'super_admin' ? (
                <Suspense fallback={<LoadingFallback />}>
                  <AdminTenants user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/admin/leads"
            element={
              isAuthenticated && user?.role === 'super_admin' ? (
                <Suspense fallback={<LoadingFallback />}>
                  <AdminLeads user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/app/admin/leads"
            element={
              isAuthenticated && user?.role === 'super_admin' ? (
                <Suspense fallback={<LoadingFallback />}>
                  <AdminLeads user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/admin/module-report"
            element={
              isAuthenticated && user?.role === 'super_admin' ? (
                <Suspense fallback={<LoadingFallback />}>
                  <ModuleReport user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/admin/user-roles"
            element={
              isAuthenticated && user?.role === 'super_admin' ? (
                <Suspense fallback={<LoadingFallback />}>
                  <UserRoleManager user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          
          {/* New 5-Star Hotel Features */}
          <Route
            path="/online-checkin/:bookingId"
            element={
              <Suspense fallback={<LoadingFallback />}>
                <OnlineCheckin />
              </Suspense>
            }
          />
          <Route
            path="/flash-report"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <FlashReport user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/group-sales"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <GroupSales user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/vip-management"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <VIPManagement user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/sales-crm"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <SalesCRM user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/service-recovery"
            element={
              isAuthenticated ? (
                <Suspense fallback={<LoadingFallback />}>
                  <ServiceRecovery user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route path="/spa-wellness" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><SpaWellness user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/meeting-events" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><MeetingEvents user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route
            path="/ai-chatbot"
            element={
              isAuthenticated && modules?.ai_chatbot !== false ? (
                <Suspense fallback={<LoadingFallback />}>
                  <AIChatbot user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/dynamic-pricing"
            element={
              isAuthenticated && modules?.ai_pricing !== false ? (
                <Suspense fallback={<LoadingFallback />}>
                  <DynamicPricing user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/reputation-center"
            element={
              isAuthenticated && modules?.ai_reputation !== false ? (
                <Suspense fallback={<LoadingFallback />}>
                  <ReputationCenter user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route path="/multi-property" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><MultiProperty user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/payment-gateway" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><PaymentGateway user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/advanced-loyalty" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><AdvancedLoyalty user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/gds-integration" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><GDSIntegration user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/staff-management" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><StaffManagement user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/guest-journey" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><GuestJourney user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/arrival-list" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><ArrivalList user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route
            path="/ai-whatsapp-concierge"
            element={
              isAuthenticated && modules?.ai_whatsapp !== false ? (
                <Suspense fallback={<LoadingFallback />}>
                  <AIWhatsAppConcierge user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/predictive-analytics"
            element={
              isAuthenticated && modules?.ai_predictive !== false ? (
                <Suspense fallback={<LoadingFallback />}>
                  <PredictiveAnalytics user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/social-media-radar"
            element={
              isAuthenticated && modules?.ai_social_radar !== false ? (
                <Suspense fallback={<LoadingFallback />}>
                  <SocialMediaRadar user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route
            path="/revenue-autopilot"
            element={
              isAuthenticated && modules?.ai_revenue_autopilot !== false ? (
                <Suspense fallback={<LoadingFallback />}>
                  <RevenueAutopilot user={user} tenant={tenant} onLogout={handleLogout} />
                </Suspense>
              ) : (
                <Navigate to="/auth" replace />
              )
            }
          />
          <Route path="/hr-complete" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><HRComplete user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/fnb-complete" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><FnBComplete user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/fnb/beo-generator" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><FnbBeoGenerator user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/kitchen-display" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><KitchenDisplay user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />

          {/* New Modules - Security, Compliance, Multi-Property, ML */}
          <Route path="/security-center" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><SecurityCenter user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/app/guvenlik" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><SecurityDashboard user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/gdpr-compliance" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><GDPRCompliance user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/central-office" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><CentralOfficeDashboard user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/central-pricing" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><CentralPricingManager user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/cross-property-guests" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><CrossPropertyGuests user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
          <Route path="/ml-dashboard" element={isAuthenticated ? <Suspense fallback={<LoadingFallback />}><MLDashboard user={user} tenant={tenant} onLogout={handleLogout} /></Suspense> : <Navigate to="/auth" replace />} />
        </Routes>
        </PlanRouteGuard>
        </BrowserRouter>
        <NotificationCenter />
      </div>
    </QueryClientProvider>
    </NotificationProvider>
  );
}

export default App;
