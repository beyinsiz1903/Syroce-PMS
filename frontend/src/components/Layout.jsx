import React, { useState, useMemo, useRef, useEffect } from 'react';
import axios from 'axios';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { preloadRoute } from '@/routes/preload';
import { shouldPrefetchOnGroupOpen } from '@/lib/navigationPrefetchPolicy';
import { useEntitlements } from '@/context/EntitlementContext';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Home, Hotel, FileText, TrendingUp, ShoppingCart, Headset,
  User, LogOut, Menu, Calendar, DollarSign, Settings as SettingsIcon,
  Layers, BarChart3, Bot, Building2, Zap, Crown, Shield, Users, ClipboardCheck,
  ChevronDown, Server, CalendarCheck, X, Undo2,
  BrainCircuit, MessageSquare, Clock, Rocket, Download, Grid3X3, ParkingSquare, Activity,
  Utensils, Briefcase, ConciergeBell, BedDouble } from 'lucide-react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import LanguageSelector from '@/components/LanguageSelector';
import AppLauncher from '@/components/AppLauncher';

import NotificationBell from '@/components/NotificationBell';
import NightScreen from '@/components/NightScreen';
import ThemeToggle from '@/components/ThemeToggle';
import PushSubscriptionManager from '@/components/PushSubscriptionManager';
import PMSDateBadge from '@/components/PMSDateBadge';
import WakeUpAlarmMonitor from '@/components/WakeUpAlarmMonitor';
import { NAV_GROUPS, NAV_GROUP_SECTIONS } from '@/config/navItems';
import { UpgradeBanner } from '@/components/UpgradeBanner';
import SimulationOverlay from '@/components/academy/SimulationOverlay';
import {
  canAccessPmsTab,
} from '@/utils/moduleAccess';
import { persistExitedTenantContext } from '@/lib/adminTenantContext';
import { accessibleNavigationItems, navigationItemsByGroup } from '@/lib/navigationCatalog';
import { userAccessScopeLabel, userIdentityLabel, userRoleLabel } from '@/lib/userRolePresentation';

const ICON_BY_KEY = {
  dashboard: Home,
  pms: Hotel,
  pms_operations: ClipboardCheck,
  reservation_calendar: Calendar,
  reports_basic: FileText,
  reports: BarChart3,
  settings: SettingsIcon,
  invoices: DollarSign,
  cost_management: Layers,
  channel_manager: Layers,
  unified_rate_manager: DollarSign,
  rate_manager: DollarSign,
  rms: TrendingUp,
  ai: Bot,
  marketplace: ShoppingCart,
  supplies_market: ShoppingCart,
  module_store: ShoppingCart,
  admin_tenants: Shield,
  admin_module_report: FileText,
  admin_leads: Users,
  governance: SettingsIcon,
  revenue_engine: TrendingUp,
  operational_events: Zap,
  guest_journey: Users,
  group_bookings: Users,
  deposit_tracking: Shield,
  night_audit: FileText,
  housekeeping_status: ClipboardCheck,
  wake_up_calls: Calendar,
  transfer_parking: ParkingSquare,
  lost_found: ShoppingCart,
  group_folio: FileText,
  travel_agent_arap: DollarSign,
  agency_management: Building2,
  agency_content: FileText,
  data_intelligence: BrainCircuit,
  messaging_dashboard: MessageSquare,
  ml_scheduler: Clock,
  revenue_autopilot_v2: Rocket,
  analytics_export: Download,
  gelir_yonetimi: DollarSign,
  ai_zeka: BrainCircuit,
  analitik_raporlar: Download,
  no_show_analytics: BarChart3,
  report_builder: FileText,
  displacement_analysis: TrendingUp,
  api_docs: FileText,
  pos_dashboard: ShoppingCart,
  contact_center_dashboard: Headset,
  cashier_workspace: DollarSign,
  tasks_workspace: ClipboardCheck,
  observability: Activity,
  control_plane: Server,
  runtime_cockpit: Activity,
  incident_panel: Zap,
  encryption_management: Shield,
  production_golive: Rocket,
  integration_observability: Activity,
  data_model: Layers,
  hrv2_ops: Server,
  infra_hardening: Shield,
  multi_property: Building2,
};

const GROUP_ICONS = {
  frontdesk: ConciergeBell,
  sales: TrendingUp,
  guest: Users,
  operations: Building2,
  fb: Utensils,
  backoffice: Briefcase,
  reports: BarChart3,
  system: SettingsIcon,
  admin: Shield,
};

const normalizedUserRoles = (user) => new Set([
  user?.role,
  ...(Array.isArray(user?.roles) ? user.roles : []),
].filter(Boolean).map((role) => String(role).trim().toLowerCase()));

/**
 * Üst çubukta aynı anda yalnızca dört iş alanı gösterilir. Kontrol paneli ve
 * Uygulamalar başlatıcısıyla birlikte ana navigasyon altı girişte kalır.
 * Yetki/entitlement filtresi bundan önce çalıştığı için bu fonksiyon yalnızca
 * yerleşimi belirler; kullanıcıya yeni bir erişim hakkı kazandırmaz.
 */
export const primaryNavigationGroupIds = (user, isSuperAdmin = false) => {
  const roles = normalizedUserRoles(user);
  if (isSuperAdmin || roles.has('super_admin')) return ['frontdesk', 'admin', 'system', 'reports'];
  if ([...roles].some((role) => ['accounting', 'finance', 'finance_manager', 'cashier'].includes(role))) {
    return ['frontdesk', 'backoffice', 'reports', 'sales'];
  }
  if ([...roles].some((role) => ['gm', 'general_manager', 'manager', 'owner'].includes(role))) {
    return ['frontdesk', 'sales', 'operations', 'reports'];
  }
  if ([...roles].some((role) => ['fnb', 'fnb_manager', 'waiter', 'restaurant'].includes(role))) {
    return ['fb', 'operations', 'reports'];
  }
  if ([...roles].some((role) => ['housekeeping', 'maintenance', 'technical'].includes(role))) {
    return ['frontdesk', 'operations', 'reports'];
  }
  return ['frontdesk', 'guest', 'operations'];
};

export const orderedNavigationGroups = (groups, user, isSuperAdmin = false) => {
  const preferred = primaryNavigationGroupIds(user, isSuperAdmin);
  const priority = new Map(preferred.map((id, index) => [id, index]));
  return [...groups].sort((left, right) => {
    const leftRank = priority.has(left.id) ? priority.get(left.id) : preferred.length + NAV_GROUPS.findIndex(({ id }) => id === left.id);
    const rightRank = priority.has(right.id) ? priority.get(right.id) : preferred.length + NAV_GROUPS.findIndex(({ id }) => id === right.id);
    return leftRank - rightRank;
  });
};

const TIER_CONFIG = {
  basic: { label: 'Basic', icon: Building2, cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  professional: { label: 'Pro', icon: Zap, cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  enterprise: { label: 'Enterprise', icon: Crown, cls: 'bg-indigo-100 text-indigo-700 border-indigo-200' },
};

export const sectionNavItems = (groupId, items) => {
  const definitions = NAV_GROUP_SECTIONS[groupId] || [];
  if (definitions.length === 0) return [{ id: 'all', label: null, items }];

  const knownSectionIds = new Set(definitions.map(({ id }) => id));
  const sections = definitions
    .map((definition) => ({
      ...definition,
      items: items.filter((item) => item.navSection === definition.id),
    }))
    .filter((section) => section.items.length > 0);
  const unsectioned = items.filter((item) => !knownSectionIds.has(item.navSection));

  if (unsectioned.length > 0) {
    sections.push({ id: 'other', label: 'Diğer', items: unsectioned });
  }
  return sections;
};

const Layout = ({ children, user, tenant, onLogout, currentModule, fullWidth = false }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedMobileGroup, setExpandedMobileGroup] = useState(null);
  const [exitingTenantContext, setExitingTenantContext] = useState(false);

  const { isSuperAdmin, hasModule, hasTenantModule = hasModule } = useEntitlements();
  const identityLabel = userIdentityLabel(user);
  const roleLabel = userRoleLabel(user?.role, t);
  const accessScopeLabel = userAccessScopeLabel(user?.role);
  const navRef = useRef(null);
  const mainRef = useRef(null);

  useEffect(() => {
    if (location.hash) return;
    if (mainRef.current) {
      mainRef.current.scrollTop = 0;
    }
    if (typeof window !== 'undefined') {
      window.scrollTo(0, 0);
    }
  }, [location.pathname, location.hash]);
  const hiddenNavGroups = useMemo(() => new Set(tenant?.hidden_nav_groups || []), [tenant]);

  const currentTier = useMemo(() => {
    const tier = tenant?.subscription_tier || 'basic';
    if (tier === 'pro') return 'professional';
    if (tier === 'ultra') return 'enterprise';
    return tier;
  }, [tenant]);

  const tierConfig = TIER_CONFIG[currentTier] || TIER_CONFIG.basic;
  const TierIcon = tierConfig.icon;

  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const active = nav.querySelector('button.bg-blue-600');
    if (active && typeof active.scrollIntoView === 'function') {
      active.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
  }, [location.pathname, currentModule]);

  const getUpgradeTier = (itemTier) => itemTier === 'professional' ? 'professional' : 'enterprise';

  const normalizeKey = (key) => key ? key.replace(/-/g, '_') : '';
  const normalizedCurrentModule = normalizeKey(currentModule);

  const visibleNav = useMemo(() => accessibleNavigationItems({
    user,
    tenant,
    isSuperAdmin,
    // Navigation inside a selected hotel reflects that hotel's effective
    // module configuration. Super-admin-only platform tools are preserved by
    // the catalogue itself rather than by granting every hotel add-on.
    hasModule: hasTenantModule,
  }), [hasTenantModule, isSuperAdmin, tenant, user]);

  const { standaloneItems, groupedItems } = useMemo(() => {
    const standalone = [];
    const grouped = navigationItemsByGroup(visibleNav);

    visibleNav.forEach((item) => {
      if (!item.navGroup) {
        standalone.push(item);
      }
    });

    return { standaloneItems: standalone, groupedItems: grouped };
  }, [visibleNav]);

  const navigationGroups = useMemo(() => {
    const availableGroups = NAV_GROUPS.filter((group) => (
      (!hiddenNavGroups.has(group.id) || isSuperAdmin)
      && (groupedItems[group.id]?.length || 0) > 0
    )).map((group) => ({
      ...group,
      label: tenant?.nav_group_labels?.[group.id] || group.label,
    }));
    return orderedNavigationGroups(availableGroups, user, isSuperAdmin);
  }, [groupedItems, hiddenNavGroups, isSuperAdmin, tenant?.nav_group_labels, user]);

  const navGroupLabel = (group) => tenant?.nav_group_labels?.[group.id]
    || t(`navGroups.${group.id}`, group.label);
  const navItemLabel = (item) => tenant?.nav_item_labels?.[item.key]
    || t(`navKeys.${item.key}`, item.label);

  const roleWorkspace = useMemo(() => {
    const roles = normalizedUserRoles(user);
    if ([...roles].some((role) => ['accounting', 'finance', 'finance_manager'].includes(role)) && hasModule('invoices')) {
      return { path: '/app/invoices', label: 'Muhasebe' };
    }
    if ([...roles].some((role) => ['gm', 'general_manager', 'manager', 'owner'].includes(role)) && hasModule('gm_dashboards')) {
      return { path: '/executive', label: 'GM Paneli' };
    }
    return { path: '/app/dashboard', label: null };
  }, [hasModule, user]);

  const currentTabParam = new URLSearchParams(location.search).get('tab');
  const isItemPathActive = (item) => {
    if (item.tabBase) {
      const bases = Array.isArray(item.tabBase) ? item.tabBase : [item.tabBase];
      if (bases.includes(location.pathname)) {
        if (item.tabKey == null) return !currentTabParam;
        return currentTabParam === item.tabKey;
      }
    }
    return location.pathname === item.path;
  };

  const isGroupActive = (groupId) => {
    const items = groupedItems[groupId] || [];
    // A page may keep its parent module as currentModule (for example
    // hotel-network keeps PMS context). A concrete URL match must win over
    // that fallback, otherwise two unrelated top-level groups look selected.
    const hasExactPathMatch = visibleNav.some((item) => isItemPathActive(item));
    return items.some((item) => {
      if (isItemPathActive(item)) return true;
      if (!hasExactPathMatch && normalizedCurrentModule === normalizeKey(item.key)) return true;
      return false;
    });
  };

  const handleNavigate = (path, closeMobile = false) => {
    navigate(path);
    if (closeMobile) setMobileMenuOpen(false);
  };

  const exitHotelWorkspace = async () => {
    setExitingTenantContext(true);
    try {
      const response = await axios.post('/admin/tenant-context/exit');
      persistExitedTenantContext(response.data);
      toast.success('Süperadmin görünümüne dönülüyor');
      navigate('/admin/tenants', { replace: true });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Otel çalışma alanından çıkılamadı');
      setExitingTenantContext(false);
    }
  };

  const renderGroupDropdown = (groupDef) => {
    const items = groupedItems[groupDef.id];
    if (!items || items.length === 0) return null;

    const GroupIcon = GROUP_ICONS[groupDef.id] || Home;
    const active = isGroupActive(groupDef.id);
    const label = navGroupLabel(groupDef);
    const sections = sectionNavItems(groupDef.id, items);

    return (
      <DropdownMenu
        key={groupDef.id}
        onOpenChange={(open) => {
          // A category can contain dozens of routes. Do not turn one menu
          // click into a network burst; item hover/focus remains targeted.
          if (open && shouldPrefetchOnGroupOpen()) preloadRoute(items[0]?.path);
        }}
      >
        <TooltipProvider delayDuration={300}>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className={`flex items-center gap-1 px-2 py-1.5 text-[11px] whitespace-nowrap rounded-md transition-all duration-150 h-8 ${
                    active
                      ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                  data-testid={`nav-group-${groupDef.id}-button`}
                  aria-label={`${label} menüsünü aç`}
                  title={label}
                >
                  <GroupIcon className="w-3.5 h-3.5 shrink-0" />
                  <span className="hidden lg:inline font-medium">{label}</span>
                  <ChevronDown className={`w-2.5 h-2.5 shrink-0 ${active ? 'text-white/70' : 'text-gray-400'}`} />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="lg:hidden">
              <p>{label}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <DropdownMenuContent align="start" className="min-w-[230px] max-h-[70vh] overflow-y-auto p-1.5">
          {(() => {
            const groupHasPathMatch = items.some(i => isItemPathActive(i));
            return sections.map((section, sectionIndex) => (
              <React.Fragment key={section.id}>
                {sectionIndex > 0 && <DropdownMenuSeparator />}
                {section.label && (
                  <DropdownMenuLabel className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    {t(`navSections.${groupDef.id}.${section.id}`, section.label)}
                  </DropdownMenuLabel>
                )}
                {section.items.map((item) => {
                  const Icon = ICON_BY_KEY[item.key] || Home;
                  const isItemActive = isItemPathActive(item) || (!groupHasPathMatch && normalizedCurrentModule === normalizeKey(item.key));
                  return (
                    <DropdownMenuItem
                      key={item.key}
                      onClick={() => handleNavigate(item.path)}
                      onPointerDown={() => preloadRoute(item.path)}
                      onMouseEnter={() => preloadRoute(item.path)}
                      onFocus={() => preloadRoute(item.path)}
                      className={`flex items-center gap-2 cursor-pointer ${
                        isItemActive ? 'bg-blue-50 text-blue-700 font-semibold' : ''
                      }`}
                      data-testid={`nav-${item.key}-button`}
                    >
                      <Icon className={`w-3.5 h-3.5 ${isItemActive ? 'text-blue-600' : 'text-gray-400'}`} />
                      <span className="text-sm leading-5">{navItemLabel(item)}</span>
                    </DropdownMenuItem>
                  );
                })}
              </React.Fragment>
            ));
          })()}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  const renderApplicationsButton = () => {
    const active = location.pathname === '/app/applications';
    return (
      <TooltipProvider key="applications" delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleNavigate('/app/applications')}
              onPointerDown={() => preloadRoute('/app/applications')}
              onMouseEnter={() => preloadRoute('/app/applications')}
              onFocus={() => preloadRoute('/app/applications')}
              className={`flex items-center gap-1 px-2 py-1.5 text-[11px] whitespace-nowrap rounded-md transition-all duration-150 h-8 ${
                active
                  ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`}
              data-testid="nav-applications-button"
              aria-label={t("navGroups.apps", "Tüm Uygulamalar")}
              title={t("navGroups.apps", "Tüm Uygulamalar")}
            >
              <Grid3X3 className="w-3.5 h-3.5 shrink-0" />
              <span className="hidden lg:inline font-medium">{t("navGroups.apps", "Tüm Uygulamalar")}</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="lg:hidden"><p>{t("navGroups.apps", "Tüm Uygulamalar")}</p></TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:bg-none dark:bg-background flex flex-col" data-testid="app-shell">
      <header className="print:hidden bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm shrink-0">
        <div className="px-3 py-1.5">
          <div className="flex items-center min-h-[44px]">
            <div
              className="flex items-center gap-2 shrink-0 cursor-pointer mr-3"
              onClick={() => navigate(roleWorkspace.path)}
            >
              <img src="/syroce-logo.svg" alt="Syroce" className="h-7 w-auto" />
              <div className="hidden lg:flex flex-col leading-none">
                <span className="text-[9px] uppercase tracking-widest text-gray-400">Syroce PMS</span>
                <span className="text-xs font-semibold text-gray-700 truncate max-w-[120px]" title={tenant?.property_name || ''}>
                  {tenant?.property_name || 'Hotel'}
                </span>
              </div>
            </div>

            <nav ref={navRef} className="hidden md:flex items-center gap-0.5 flex-1 min-w-0 overflow-x-auto pb-1.5 [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-gray-400" style={{ scrollbarWidth: 'auto', scrollbarColor: '#94a3b8 transparent' }}>
              {[...standaloneItems.filter((item) => item.key === 'dashboard'), ...visibleNav.filter((item) => item.key === 'reservation_calendar')].map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isDashboard = item.key === 'dashboard';
                const targetPath = isDashboard ? roleWorkspace.path : item.path;
                const label = isDashboard ? (roleWorkspace.label || navItemLabel(item)) : navItemLabel(item);
                const isActive = isDashboard ? (location.pathname === roleWorkspace.path || normalizedCurrentModule === normalizeKey(item.key) || isItemPathActive(item)) : (normalizedCurrentModule === normalizeKey(item.key) || isItemPathActive(item));
                
                return (
                  <TooltipProvider key={item.key} delayDuration={300}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleNavigate(targetPath)}
                          onPointerDown={() => preloadRoute(targetPath)}
                          onMouseEnter={() => preloadRoute(targetPath)}
                          onFocus={() => preloadRoute(targetPath)}
                          className={`flex items-center gap-1 px-2 py-1.5 text-[11px] whitespace-nowrap rounded-md h-8 transition-all duration-150 ${
                            isActive
                              ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                              : 'text-gray-600 hover:bg-gray-100'
                          }`}
                          data-nav-key={item.key}
                          data-testid={`nav-${item.key}-button`}
                          aria-label={label}
                          title={label}
                        >
                          <Icon className="w-3.5 h-3.5 shrink-0" />
                          <span className="hidden lg:inline font-medium">{label}</span>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="lg:hidden">
                        <p>{label}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })}

              <div className="w-px h-5 bg-gray-200 mx-1 shrink-0" />
              {/* Odalar kısayolu — PMS'in rooms sekmesine direkt bağlantı */}
              {visibleNav.some((item) => item.key === 'pms') && canAccessPmsTab(user, 'rooms') && (() => {
                const roomsPath = '/app/pms#rooms';
                const isRoomsActive = location.pathname === '/app/pms' && location.hash === '#rooms';
                return (
                  <TooltipProvider key="rooms-shortcut" delayDuration={300}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleNavigate(roomsPath)}
                          onPointerDown={() => preloadRoute('/app/pms')}
                          onMouseEnter={() => preloadRoute('/app/pms')}
                          onFocus={() => preloadRoute('/app/pms')}
                          className={`flex items-center gap-1 px-2 py-1.5 text-[11px] whitespace-nowrap rounded-md h-8 transition-all duration-150 ${
                            isRoomsActive
                              ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                              : 'text-gray-600 hover:bg-gray-100'
                          }`}
                          data-nav-key="rooms-shortcut"
                          data-testid="nav-rooms-shortcut-button"
                          aria-label="Odalar"
                          title="Odalar"
                        >
                          <BedDouble className="w-3.5 h-3.5 shrink-0" />
                          <span className="hidden lg:inline font-medium">Odalar</span>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="lg:hidden">
                        <p>Odalar</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })()}
              {navigationGroups.map((groupDef) => renderGroupDropdown(groupDef))}
            </nav>

            <div className="flex items-center gap-1.5 shrink-0 ml-2">
              {renderApplicationsButton()}
              {standaloneItems.filter((item) => item.key === 'settings').map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isActive = normalizedCurrentModule === normalizeKey(item.key) || isItemPathActive(item);
                return (
                  <TooltipProvider key={item.key} delayDuration={300}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleNavigate(item.path)}
                          onPointerDown={() => preloadRoute(item.path)}
                          onMouseEnter={() => preloadRoute(item.path)}
                          onFocus={() => preloadRoute(item.path)}
                          className={`hidden md:flex items-center gap-1 px-2 py-1.5 text-[11px] whitespace-nowrap rounded-md h-8 transition-all duration-150 ${
                            isActive
                              ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                              : 'text-gray-600 hover:bg-gray-100'
                          }`}
                          data-nav-key={item.key}
                          data-testid={`nav-${item.key}-button`}
                          aria-label={navItemLabel(item)}
                          title={navItemLabel(item)}
                        >
                          <Icon className="w-3.5 h-3.5 shrink-0" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">
                        <p>{navItemLabel(item)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })}
              <div className="hidden md:block">
                <LanguageSelector />
              </div>
              <PushSubscriptionManager />
              <AppLauncher user={user} />
              <NotificationBell />
              <ThemeToggle />
              <NightScreen />

              <Button
                variant="ghost"
                size="sm"
                className="md:hidden h-8 w-8 p-0 dark:text-gray-100"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                data-testid="mobile-menu-toggle"
                aria-label={mobileMenuOpen ? 'Gezinme menüsünü kapat' : 'Gezinme menüsünü aç'}
                aria-expanded={mobileMenuOpen}
                aria-controls="mobile-navigation"
                title={mobileMenuOpen ? 'Menüyü kapat' : 'Menüyü aç'}
              >
                {mobileMenuOpen ? <X className="w-4 h-4" aria-hidden="true" /> : <Menu className="w-4 h-4" aria-hidden="true" />}
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-8 px-2 text-xs dark:border-gray-600 dark:text-gray-100" aria-label={`${identityLabel}; ${roleLabel}; ${accessScopeLabel}`}>
                    <User className="w-3.5 h-3.5 mr-1" />
                    <span className="hidden sm:inline max-w-[110px] truncate">{identityLabel}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel className="max-w-[280px] space-y-0.5">
                    <span className="block text-[10px] font-semibold uppercase tracking-wider text-gray-500">Kullanıcı</span>
                    <span className="block truncate text-sm font-semibold">{identityLabel}</span>
                    {user?.email && <span className="block truncate text-xs font-normal text-gray-500">{user.email}</span>}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem className="text-sm text-gray-600" aria-label={`Yetki rolü: ${roleLabel}`}>
                    <span className="text-gray-500 mr-1">Yetki rolü:</span>
                    <span className="font-semibold">{roleLabel}</span>
                    {isSuperAdmin && <span className="ml-2 text-[10px] bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">{accessScopeLabel}</span>}
                  </DropdownMenuItem>
                  {!isSuperAdmin && (
                    <DropdownMenuItem className="text-sm text-gray-600">
                      <span className="text-gray-500 mr-1">Plan:</span>
                      <span className={`inline-flex items-center gap-1 ${tierConfig.cls} px-2 py-0.5 rounded-full text-[10px] font-semibold`}>
                        <TierIcon className="w-3 h-3" />
                        {tierConfig.label}
                      </span>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onClick={() => navigate('/app/profile')} className="text-sm cursor-pointer">
                    <User className="w-4 h-4 mr-2" />
                    Profilim
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={onLogout} className="text-red-600 focus:text-red-700">
                    <LogOut className="w-4 h-4 mr-2" />
                    {t('common.logout')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {mobileMenuOpen && (
            <nav id="mobile-navigation" className="md:hidden mt-2 pb-2 border-t pt-2 max-h-[70vh] overflow-y-auto" data-testid="mobile-nav">
              <div className="px-2 pb-2 flex items-center gap-2">
                <span className={`inline-flex items-center gap-1 ${tierConfig.cls} px-2 py-0.5 rounded-full text-xs font-semibold border`}>
                  <TierIcon className="w-3 h-3" />
                  {tierConfig.label}
                </span>
                <LanguageSelector />
              </div>

              {[...standaloneItems.filter((item) => item.key === 'dashboard'), ...visibleNav.filter((item) => item.key === 'reservation_calendar')].map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isDashboard = item.key === 'dashboard';
                const targetPath = isDashboard ? roleWorkspace.path : item.path;
                const label = isDashboard ? (roleWorkspace.label || navItemLabel(item)) : navItemLabel(item);
                const isActive = isDashboard ? (location.pathname === roleWorkspace.path || normalizedCurrentModule === normalizeKey(item.key) || isItemPathActive(item)) : (normalizedCurrentModule === normalizeKey(item.key) || isItemPathActive(item));
                
                return (
                  <Button key={item.key} variant="ghost" size="sm" onClick={() => handleNavigate(targetPath, true)} onMouseEnter={() => preloadRoute(targetPath)} onFocus={() => preloadRoute(targetPath)}
                    className={`w-full justify-start py-2 mb-0.5 ${isActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-100 dark:text-gray-100'}`}
                    data-testid={`nav-${item.key}-button`}>
                    <Icon className="w-4 h-4 mr-2" />{label}
                  </Button>
                );
              })}

              {navigationGroups.map((groupDef) => {
                const items = groupedItems[groupDef.id];
                if (!items || items.length === 0) return null;
                const GroupIcon = GROUP_ICONS[groupDef.id] || Home;
                const active = isGroupActive(groupDef.id);
                const isExpanded = expandedMobileGroup === groupDef.id;
                const sections = sectionNavItems(groupDef.id, items);
                return (
                  <div key={groupDef.id} className="mb-0.5">
                    <Button variant="ghost" size="sm"
                      onClick={() => {
                        setExpandedMobileGroup(!isExpanded ? groupDef.id : null);
                      }}
                      className={`w-full justify-between py-2 ${active && !isExpanded ? 'bg-blue-50 text-blue-700 font-semibold' : 'hover:bg-gray-100 dark:text-gray-100'}`}>
                      <div className="flex items-center">
                        <GroupIcon className="w-4 h-4 mr-2" />
                        {navGroupLabel(groupDef)}
                      </div>
                      <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                    </Button>
                    {isExpanded && (
                      <div className="pl-4 py-1">
                        {sections.map((section, sectionIndex) => (
                          <div key={section.id} className={sectionIndex > 0 ? 'mt-2' : ''}>
                            {section.label && (
                              <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                {t(`navSections.${groupDef.id}.${section.id}`, section.label)}
                              </p>
                            )}
                            <div className="space-y-0.5">
                              {section.items.map((item) => {
                                const Icon = ICON_BY_KEY[item.key] || Home;
                                const isItemActive = normalizedCurrentModule === normalizeKey(item.key) || isItemPathActive(item);
                                return (
                                  <Button key={item.key} variant="ghost" size="sm"
                                    onClick={() => handleNavigate(item.path, true)} onMouseEnter={() => preloadRoute(item.path)} onFocus={() => preloadRoute(item.path)}
                                    className={`w-full justify-start py-1.5 text-sm ${isItemActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-50 dark:text-gray-100'}`}
                                    data-testid={`nav-${item.key}-button`}>
                                    <Icon className="w-3.5 h-3.5 mr-2" />{navItemLabel(item)}
                                  </Button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}

              {standaloneItems.filter((item) => item.key === 'settings').map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                return (
                  <Button key={item.key} variant="ghost" size="sm" onClick={() => handleNavigate(item.path, true)} onMouseEnter={() => preloadRoute(item.path)} onFocus={() => preloadRoute(item.path)}
                    className={`w-full justify-start py-2 mb-0.5 ${isActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-100 dark:text-gray-100'}`}
                    data-testid={`nav-${item.key}-button`}>
                    <Icon className="w-4 h-4 mr-2" />{navItemLabel(item)}
                  </Button>
                );
              })}

              {standaloneItems.filter((item) => item.requireSuperAdmin).map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                return (
                  <Button key={item.key} variant="ghost" size="sm" onClick={() => handleNavigate(item.path, true)} onMouseEnter={() => preloadRoute(item.path)} onFocus={() => preloadRoute(item.path)}
                    className="w-full justify-start py-2 mb-0.5 hover:bg-gray-100 dark:text-gray-100" data-testid={`nav-${item.key}-button`}>
                    <Icon className="w-4 h-4 mr-2" />{t(`navKeys.${item.key}`, item.label)}
                  </Button>
                );
              })}
            </nav>
          )}
        </div>
        {user?.is_impersonating && (
          <div
            className="flex flex-col gap-2 border-t border-amber-200 bg-amber-50 px-3 py-2 text-amber-950 sm:flex-row sm:items-center sm:justify-between"
            data-testid="admin-tenant-context-banner"
          >
            <div className="flex items-center gap-2 text-xs sm:text-sm">
              <Shield className="h-4 w-4 shrink-0 text-amber-700" aria-hidden="true" />
              <span>
                <strong>{tenant?.property_name || user?.impersonated_tenant_name || 'Seçili otel'}</strong> adına işlem yapıyorsunuz.
                {' '}Gerçek kullanıcı: {user?.name || user?.email}
              </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="h-8 border-amber-300 bg-white text-xs text-amber-900 hover:bg-amber-100"
              onClick={exitHotelWorkspace}
              disabled={exitingTenantContext}
              data-testid="exit-admin-tenant-context"
            >
              <Undo2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
              {exitingTenantContext ? 'Dönülüyor...' : 'Süperadmin görünümüne dön'}
            </Button>
          </div>
        )}
      </header>

      <PMSDateBadge inLayout />
      <WakeUpAlarmMonitor tenant={tenant} />

      <main
        ref={mainRef}
        className={`app-safe-bottom-padding flex-1 w-full mx-auto overflow-auto ${fullWidth ? 'max-w-none' : 'max-w-7xl'}`}
      >
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
      </main>

      <SimulationOverlay />
    </div>
  );
};

export default Layout;
