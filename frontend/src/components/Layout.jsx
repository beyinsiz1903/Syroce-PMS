import React, { useState, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
  Home, Hotel, FileText, TrendingUp, ShoppingCart,
  User, LogOut, Menu, Calendar, DollarSign, Settings as SettingsIcon,
  Layers, BarChart3, Bot, Building2, Zap, Crown, Shield, Users, ClipboardCheck,
  ChevronDown, Server, CalendarCheck, X,
  BrainCircuit, MessageSquare, Clock, Rocket, Download
} from 'lucide-react';
import LanguageSelector from '@/components/LanguageSelector';
import NotificationBell from '@/components/NotificationBell';
import PushSubscriptionManager from '@/components/PushSubscriptionManager';
import { NAV_ITEMS, NAV_GROUPS } from '@/config/navItems';
import { UpgradeBanner } from '@/components/UpgradeBanner';

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
};

const GROUP_ICONS = {
  operations: Hotel,
  reservations: CalendarCheck,
  finance: DollarSign,
  channels: Layers,
  reports: BarChart3,
  advanced: Zap,
  infrastructure: Server,
  admin: Shield,
};

const TIER_CONFIG = {
  basic: { label: 'Basic', icon: Building2, cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  professional: { label: 'Pro', icon: Zap, cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  enterprise: { label: 'Enterprise', icon: Crown, cls: 'bg-purple-100 text-purple-700 border-purple-200' },
};

const Layout = ({ children, user, tenant, onLogout, currentModule }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedMobileGroup, setExpandedMobileGroup] = useState(null);

  const isSuperAdmin = user?.role === 'super_admin';
  const modules = useMemo(() => tenant?.modules || {}, [tenant]);
  const hiddenNavGroups = useMemo(() => new Set(tenant?.hidden_nav_groups || []), [tenant]);
  const hiddenNavItems = useMemo(() => new Set(tenant?.hidden_nav_items || []), [tenant]);

  const currentTier = useMemo(() => {
    const tier = tenant?.subscription_tier || 'basic';
    if (tier === 'pro') return 'professional';
    if (tier === 'ultra') return 'enterprise';
    return tier;
  }, [tenant]);

  const tierConfig = TIER_CONFIG[currentTier] || TIER_CONFIG.basic;
  const TierIcon = tierConfig.icon;

  const getUpgradeTier = (itemTier) => itemTier === 'professional' ? 'professional' : 'enterprise';

  const isModuleEnabled = (moduleKey) => {
    if (!moduleKey) return true;
    if (!modules || Object.keys(modules).length === 0) return true;
    // Only hide if explicitly set to false; treat missing/undefined as enabled
    return modules[moduleKey] !== false;
  };

  const normalizeKey = (key) => key ? key.replace(/-/g, '_') : '';
  const normalizedCurrentModule = normalizeKey(currentModule);

  const { visibleNav, lockedNav, upgradeTier } = useMemo(() => {
    const visible = [];
    const locked = [];
    let nextUpgradeTier = null;

    NAV_ITEMS.forEach((item) => {
      if (item.hidden) return;
      if (!isSuperAdmin && hiddenNavItems.has(item.key)) return;
      if (!isSuperAdmin && item.navGroup && hiddenNavGroups.has(item.navGroup)) return;
      if (item.requireSuperAdmin) {
        if (isSuperAdmin) visible.push(item);
        return;
      }
      if (item.moduleKey && isModuleEnabled(item.moduleKey)) {
        visible.push(item);
      } else if (item.moduleKey && !isModuleEnabled(item.moduleKey)) {
        locked.push(item);
        if (!nextUpgradeTier) nextUpgradeTier = getUpgradeTier(item.tier);
      } else {
        visible.push(item);
      }
    });

    return { visibleNav: visible, lockedNav: locked, upgradeTier: nextUpgradeTier };
  }, [modules, isSuperAdmin, hiddenNavGroups, hiddenNavItems]);

  const { standaloneItems, groupedItems } = useMemo(() => {
    const standalone = [];
    const grouped = {};

    visibleNav.forEach((item) => {
      if (!item.navGroup) {
        standalone.push(item);
      } else {
        if (!grouped[item.navGroup]) grouped[item.navGroup] = [];
        grouped[item.navGroup].push(item);
      }
    });

    return { standaloneItems: standalone, groupedItems: grouped };
  }, [visibleNav]);

  const isGroupActive = (groupId) => {
    const items = groupedItems[groupId] || [];
    return items.some((item) => {
      if (normalizedCurrentModule === normalizeKey(item.key)) return true;
      if (location.pathname === item.path) return true;
      return false;
    });
  };

  const handleNavigate = (path, closeMobile = false) => {
    navigate(path);
    if (closeMobile) setMobileMenuOpen(false);
  };

  const renderGroupDropdown = (groupDef) => {
    const items = groupedItems[groupDef.id];
    if (!items || items.length === 0) return null;

    const GroupIcon = GROUP_ICONS[groupDef.id] || Home;
    const active = isGroupActive(groupDef.id);
    const label = t(`navGroups.${groupDef.id}`, groupDef.label);

    return (
      <DropdownMenu key={groupDef.id}>
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
                >
                  <GroupIcon className="w-3.5 h-3.5 shrink-0" />
                  <span className="hidden 2xl:inline font-medium">{label}</span>
                  <ChevronDown className={`w-2.5 h-2.5 shrink-0 ${active ? 'text-white/70' : 'text-gray-400'}`} />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="2xl:hidden">
              <p>{label}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <DropdownMenuContent align="start" className="min-w-[190px]">
          {(() => {
            const normalItems = items.filter(i => !i.requireSuperAdmin);
            const adminItems = items.filter(i => i.requireSuperAdmin);
            return (
              <>
                {normalItems.map((item) => {
                  const Icon = ICON_BY_KEY[item.key] || Home;
                  const isItemActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                  return (
                    <DropdownMenuItem
                      key={item.key}
                      onClick={() => handleNavigate(item.path)}
                      className={`flex items-center gap-2 cursor-pointer ${
                        isItemActive ? 'bg-blue-50 text-blue-700 font-semibold' : ''
                      }`}
                      data-testid={`nav-${item.key}-button`}
                    >
                      <Icon className={`w-3.5 h-3.5 ${isItemActive ? 'text-blue-600' : 'text-gray-400'}`} />
                      <span className="text-sm">{t(`navKeys.${item.key}`, item.label)}</span>
                    </DropdownMenuItem>
                  );
                })}
                {adminItems.length > 0 && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel className="text-[10px] text-gray-400 font-normal uppercase tracking-wider px-2">
                      Teknik Yönetim
                    </DropdownMenuLabel>
                    {adminItems.map((item) => {
                      const Icon = ICON_BY_KEY[item.key] || Home;
                      const isItemActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                      return (
                        <DropdownMenuItem
                          key={item.key}
                          onClick={() => handleNavigate(item.path)}
                          className={`flex items-center gap-2 cursor-pointer text-gray-500 ${
                            isItemActive ? 'bg-blue-50 text-blue-700 font-semibold' : ''
                          }`}
                          data-testid={`nav-${item.key}-button`}
                        >
                          <Icon className={`w-3.5 h-3.5 ${isItemActive ? 'text-blue-600' : 'text-gray-400'}`} />
                          <span className="text-sm">{t(`navKeys.${item.key}`, item.label)}</span>
                        </DropdownMenuItem>
                      );
                    })}
                  </>
                )}
              </>
            );
          })()}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm shrink-0">
        <div className="px-3 py-1.5">
          <div className="flex items-center h-10">
            {/* Logo area - fixed width */}
            <div
              className="flex items-center gap-2 shrink-0 cursor-pointer mr-3"
              onClick={() => navigate('/')}
            >
              <img src="/syroce-logo.svg" alt="Syroce" className="h-7 w-auto" />
              <div className="hidden lg:flex flex-col leading-none">
                <span className="text-[9px] uppercase tracking-widest text-gray-400">Syroce PMS</span>
                <span className="text-xs font-semibold text-gray-700 truncate max-w-[120px]" title={tenant?.property_name || ''}>
                  {tenant?.property_name || 'Hotel'}
                </span>
              </div>
            </div>

            {/* Desktop Navigation - scrollable */}
            <nav className="hidden md:flex items-center gap-0.5 flex-1 min-w-0 overflow-x-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: '#cbd5e1 transparent' }}>
              {/* Dashboard */}
              {standaloneItems.filter((item) => item.key === 'dashboard').map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                return (
                  <TooltipProvider key={item.key} delayDuration={300}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleNavigate(item.path)}
                          className={`flex items-center gap-1 px-2 py-1.5 text-[11px] whitespace-nowrap rounded-md h-8 transition-all duration-150 ${
                            isActive
                              ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                              : 'text-gray-600 hover:bg-gray-100'
                          }`}
                          data-nav-key={item.key}
                          data-testid={`nav-${item.key}-button`}
                        >
                          <Icon className="w-3.5 h-3.5 shrink-0" />
                          <span className="hidden 2xl:inline font-medium">{t(`navKeys.${item.key}`, item.label)}</span>
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom" className="2xl:hidden">
                        <p>{t(`navKeys.${item.key}`, item.label)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })}

              {/* Separator */}
              <div className="w-px h-5 bg-gray-200 mx-1 shrink-0" />

              {/* Group dropdowns */}
              {NAV_GROUPS.filter(g => !hiddenNavGroups.has(g.id) || isSuperAdmin).map((groupDef) => renderGroupDropdown(groupDef))}

            </nav>

            {/* Right utilities - fixed */}
            <div className="flex items-center gap-1.5 shrink-0 ml-2">
              {/* Settings button - always visible */}
              {standaloneItems.filter((item) => item.key === 'settings').map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                return (
                  <TooltipProvider key={item.key} delayDuration={300}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleNavigate(item.path)}
                          className={`hidden md:flex items-center gap-1 px-2 py-1.5 text-[11px] whitespace-nowrap rounded-md h-8 transition-all duration-150 ${
                            isActive
                              ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                              : 'text-gray-600 hover:bg-gray-100'
                          }`}
                          data-nav-key={item.key}
                          data-testid={`nav-${item.key}-button`}
                        >
                          <Icon className="w-3.5 h-3.5 shrink-0" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="bottom">
                        <p>{t(`navKeys.${item.key}`, item.label)}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })}
              <div className="hidden md:block">
                <LanguageSelector />
              </div>
              <PushSubscriptionManager />
              <NotificationBell />

              {/* Mobile hamburger */}
              <Button
                variant="ghost"
                size="sm"
                className="md:hidden h-8 w-8 p-0"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                data-testid="mobile-menu-toggle"
              >
                {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
              </Button>

              {/* User menu */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-8 px-2 text-xs">
                    <User className="w-3.5 h-3.5 mr-1" />
                    <span className="hidden sm:inline max-w-[70px] truncate">{user?.name || 'User'}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem className="text-sm font-medium">{user?.email}</DropdownMenuItem>
                  <DropdownMenuItem className="text-sm text-gray-500">Rol: {user?.role}</DropdownMenuItem>
                  {!isSuperAdmin && (
                    <DropdownMenuItem>
                      <span className={`inline-flex items-center gap-1 ${tierConfig.cls} px-2 py-0.5 rounded-full text-[10px] font-semibold`}>
                        <TierIcon className="w-3 h-3" />
                        {tierConfig.label} Plan
                      </span>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onClick={onLogout} className="text-red-600 focus:text-red-700">
                    <LogOut className="w-4 h-4 mr-2" />
                    {t('common.logout')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {/* Mobile Navigation */}
          {mobileMenuOpen && (
            <nav className="md:hidden mt-2 pb-2 border-t pt-2 max-h-[70vh] overflow-y-auto" data-testid="mobile-nav">
              <div className="px-2 pb-2 flex items-center gap-2">
                <span className={`inline-flex items-center gap-1 ${tierConfig.cls} px-2 py-0.5 rounded-full text-xs font-semibold border`}>
                  <TierIcon className="w-3 h-3" />
                  {tierConfig.label}
                </span>
                <LanguageSelector />
              </div>

              {standaloneItems.filter((item) => item.key === 'dashboard').map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                return (
                  <Button key={item.key} variant="ghost" size="sm" onClick={() => handleNavigate(item.path, true)}
                    className={`w-full justify-start py-2 mb-0.5 ${isActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-100'}`}
                    data-testid={`nav-${item.key}-button`}>
                    <Icon className="w-4 h-4 mr-2" />{t(`navKeys.${item.key}`, item.label)}
                  </Button>
                );
              })}

              {NAV_GROUPS.filter(g => !hiddenNavGroups.has(g.id) || isSuperAdmin).map((groupDef) => {
                const items = groupedItems[groupDef.id];
                if (!items || items.length === 0) return null;
                const GroupIcon = GROUP_ICONS[groupDef.id] || Home;
                const active = isGroupActive(groupDef.id);
                const isExpanded = expandedMobileGroup === groupDef.id;
                return (
                  <div key={groupDef.id} className="mb-0.5">
                    <Button variant="ghost" size="sm"
                      onClick={() => setExpandedMobileGroup(isExpanded ? null : groupDef.id)}
                      className={`w-full justify-between py-2 ${active && !isExpanded ? 'bg-blue-50 text-blue-700 font-semibold' : 'hover:bg-gray-100'}`}>
                      <div className="flex items-center">
                        <GroupIcon className="w-4 h-4 mr-2" />
                        {t(`navGroups.${groupDef.id}`, groupDef.label)}
                      </div>
                      <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                    </Button>
                    {isExpanded && (
                      <div className="pl-4 py-1 space-y-0.5">
                        {items.map((item) => {
                          const Icon = ICON_BY_KEY[item.key] || Home;
                          const isItemActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                          return (
                            <Button key={item.key} variant="ghost" size="sm"
                              onClick={() => handleNavigate(item.path, true)}
                              className={`w-full justify-start py-1.5 text-sm ${isItemActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-50'}`}
                              data-testid={`nav-${item.key}-button`}>
                              <Icon className="w-3.5 h-3.5 mr-2" />{t(`navKeys.${item.key}`, item.label)}
                            </Button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}

              {standaloneItems.filter((item) => item.key === 'settings').map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                return (
                  <Button key={item.key} variant="ghost" size="sm" onClick={() => handleNavigate(item.path, true)}
                    className={`w-full justify-start py-2 mb-0.5 ${isActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-100'}`}
                    data-testid={`nav-${item.key}-button`}>
                    <Icon className="w-4 h-4 mr-2" />{t(`navKeys.${item.key}`, item.label)}
                  </Button>
                );
              })}

              {standaloneItems.filter((item) => item.requireSuperAdmin).map((item) => {
                const Icon = ICON_BY_KEY[item.key] || Home;
                return (
                  <Button key={item.key} variant="ghost" size="sm" onClick={() => handleNavigate(item.path, true)}
                    className="w-full justify-start py-2 mb-0.5 hover:bg-gray-100" data-testid={`nav-${item.key}-button`}>
                    <Icon className="w-4 h-4 mr-2" />{t(`navKeys.${item.key}`, item.label)}
                  </Button>
                );
              })}

              {!isSuperAdmin && lockedNav.length > 0 && upgradeTier && (
                <UpgradeBanner requiredTier={upgradeTier} variant="nav-footer" />
              )}
            </nav>
          )}
        </div>
      </header>

      {/* Main Content - fills remaining viewport */}
      <main className="flex-1 max-w-7xl w-full mx-auto overflow-auto">
        {children}
      </main>
    </div>
  );
};

export default Layout;
