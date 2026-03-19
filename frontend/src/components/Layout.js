import React, { useState, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Home, Hotel, FileText, TrendingUp, ShoppingCart,
  User, LogOut, Menu, Calendar, DollarSign, Settings as SettingsIcon,
  Layers, BarChart3, Bot, Building2, Zap, Crown, Shield, Users, ClipboardCheck,
  ChevronDown, Server, CalendarCheck, X
} from 'lucide-react';
import LanguageSelector from '@/components/LanguageSelector';
import NotificationBell from '@/components/NotificationBell';
import PushSubscriptionManager from '@/components/PushSubscriptionManager';
import { NAV_ITEMS, NAV_GROUPS } from '@/config/navItems';
import { UpgradeBanner } from '@/components/UpgradeBanner';

// ─── Icon mapping by nav key ─────────────────────────
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
  rate_manager: DollarSign,
  rms: TrendingUp,
  ai: Bot,
  marketplace: ShoppingCart,
  admin_tenants: Shield,
  admin_module_report: FileText,
  admin_leads: Users,
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
};

// ─── Icon mapping for nav groups ─────────────────────
const GROUP_ICONS = {
  operations: Hotel,
  reservations: CalendarCheck,
  finance: DollarSign,
  channels: Layers,
  reports: BarChart3,
  advanced: Zap,
  infrastructure: Server,
};

// ─── Tier badge in header ─────────────────────────────
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

  const currentTier = useMemo(() => {
    const tier = tenant?.subscription_tier || 'basic';
    if (tier === 'pro') return 'professional';
    if (tier === 'ultra') return 'enterprise';
    return tier;
  }, [tenant]);

  const tierConfig = TIER_CONFIG[currentTier] || TIER_CONFIG.basic;
  const TierIcon = tierConfig.icon;

  const getUpgradeTier = (itemTier) => {
    if (itemTier === 'professional') return 'professional';
    return 'enterprise';
  };

  const isModuleEnabled = (moduleKey) => {
    if (!moduleKey) return true;
    if (!modules || Object.keys(modules).length === 0) return true;
    return modules[moduleKey] !== false && modules[moduleKey] !== undefined ? !!modules[moduleKey] : false;
  };

  // ─── Normalize module key for comparison ──────────────
  const normalizeKey = (key) => key ? key.replace(/-/g, '_') : '';
  const normalizedCurrentModule = normalizeKey(currentModule);

  // ─── Build visible/locked items ───────────────────────
  const { visibleNav, lockedNav, upgradeTier } = useMemo(() => {
    const visible = [];
    const locked = [];
    let nextUpgradeTier = null;

    NAV_ITEMS.forEach((item) => {
      if (item.hidden) return;

      if (item.requireSuperAdmin) {
        if (isSuperAdmin) visible.push(item);
        return;
      }

      if (item.moduleKey && isModuleEnabled(item.moduleKey)) {
        visible.push(item);
      } else if (item.moduleKey && !isModuleEnabled(item.moduleKey)) {
        locked.push(item);
        if (!nextUpgradeTier) {
          nextUpgradeTier = getUpgradeTier(item.tier);
        }
      } else {
        visible.push(item);
      }
    });

    return { visibleNav: visible, lockedNav: locked, upgradeTier: nextUpgradeTier };
  }, [modules, isSuperAdmin]);

  // ─── Group items by navGroup ──────────────────────────
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

  // ─── Check if any item in a group is active ───────────
  const isGroupActive = (groupId) => {
    const items = groupedItems[groupId] || [];
    return items.some((item) => {
      const normalized = normalizeKey(item.key);
      if (normalizedCurrentModule === normalized) return true;
      // Also check path match
      if (location.pathname === item.path) return true;
      return false;
    });
  };

  // ─── Navigate without scroll reset ────────────────────
  const handleNavigate = (path, closeMobile = false) => {
    navigate(path);
    if (closeMobile) setMobileMenuOpen(false);
  };

  // ─── Render standalone button ─────────────────────────
  const renderStandaloneButton = (item) => {
    const Icon = ICON_BY_KEY[item.key] || Home;
    const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;

    return (
      <Button
        key={item.key}
        variant="ghost"
        size="sm"
        onClick={() => handleNavigate(item.path)}
        className={`flex items-center gap-1.5 px-3 py-2 text-xs whitespace-nowrap rounded-lg transition-all duration-200 ${
          isActive
            ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
        }`}
        data-nav-key={item.key}
        data-testid={`nav-${item.key}-button`}
      >
        <Icon className="w-3.5 h-3.5" />
        <span className="font-medium">{t(`navKeys.${item.key}`, item.label)}</span>
      </Button>
    );
  };

  // ─── Render group dropdown ────────────────────────────
  const renderGroupDropdown = (groupDef) => {
    const items = groupedItems[groupDef.id];
    if (!items || items.length === 0) return null;

    const GroupIcon = GROUP_ICONS[groupDef.id] || Home;
    const active = isGroupActive(groupDef.id);

    return (
      <DropdownMenu key={groupDef.id}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={`flex items-center gap-1.5 px-3 py-2 text-xs whitespace-nowrap rounded-lg transition-all duration-200 ${
              active
                ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
            }`}
            data-testid={`nav-group-${groupDef.id}-button`}
          >
            <GroupIcon className="w-3.5 h-3.5" />
            <span className="font-medium">{t(`navGroups.${groupDef.id}`, groupDef.label)}</span>
            <ChevronDown className={`w-3 h-3 transition-transform ${active ? 'text-white/80' : 'text-gray-400'}`} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[200px]">
          {items.map((item) => {
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
                <Icon className={`w-4 h-4 ${isItemActive ? 'text-blue-600' : 'text-gray-400'}`} />
                <span>{t(`navKeys.${item.key}`, item.label)}</span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="px-4 py-2.5">
          <div className="flex items-center justify-between">
            {/* Logo & Hotel Name + Tier Badge */}
            <div className="flex items-center space-x-3 shrink-0">
              <img
                src="/syroce-logo.svg"
                alt="Syroce Logo"
                className="h-9 w-auto cursor-pointer"
                onClick={() => navigate('/')}
              />
              <div className="flex flex-col leading-tight min-w-0">
                <span className="text-[10px] uppercase tracking-[0.2em] text-gray-400 hidden lg:block">
                  Syroce PMS
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className="text-sm font-semibold text-gray-700 truncate max-w-[120px] lg:max-w-[160px]"
                    title={tenant?.property_name || 'Hotel Management'}
                  >
                    {tenant?.property_name || 'Hotel Management'}
                  </span>
                  {!isSuperAdmin && (
                    <span className={`hidden lg:inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-semibold ${tierConfig.cls}`}>
                      <TierIcon className="w-2.5 h-2.5" />
                      {tierConfig.label}
                    </span>
                  )}
                  {isSuperAdmin && (
                    <span className="hidden lg:inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full border font-semibold bg-red-100 text-red-700 border-red-200">
                      <Shield className="w-2.5 h-2.5" />
                      Admin
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Desktop Navigation - Grouped */}
            <nav className="hidden md:flex items-center gap-1 flex-1 justify-center max-w-4xl mx-4">
              {/* Dashboard standalone */}
              {standaloneItems
                .filter((item) => item.key === 'dashboard')
                .map((item) => renderStandaloneButton(item))}

              {/* Group dropdowns */}
              {NAV_GROUPS.map((groupDef) => renderGroupDropdown(groupDef))}

              {/* Settings standalone */}
              {standaloneItems
                .filter((item) => item.key === 'settings')
                .map((item) => renderStandaloneButton(item))}

              {/* Super admin items */}
              {standaloneItems
                .filter((item) => item.requireSuperAdmin)
                .map((item) => renderStandaloneButton(item))}

              {/* Upgrade teaser */}
              {!isSuperAdmin && lockedNav.length > 0 && upgradeTier && (
                <UpgradeBanner requiredTier={upgradeTier} variant="inline" />
              )}
            </nav>

            {/* User Menu and Utilities */}
            <div className="flex items-center space-x-2 shrink-0">
              <div className="hidden md:block">
                <LanguageSelector />
              </div>
              <PushSubscriptionManager />
              <NotificationBell />
              <Button
                variant="ghost"
                size="sm"
                className="md:hidden"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                data-testid="mobile-menu-toggle"
              >
                {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="hidden sm:flex">
                    <User className="w-4 h-4 mr-1.5" />
                    <span className="max-w-[80px] truncate">{user?.name || 'User'}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem className="text-sm font-medium">
                    {user?.email}
                  </DropdownMenuItem>
                  <DropdownMenuItem className="text-sm text-gray-500">
                    Rol: {user?.role}
                  </DropdownMenuItem>
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
            <nav className="md:hidden mt-3 pb-2 border-t pt-3 max-h-[70vh] overflow-y-auto" data-testid="mobile-nav">
              {/* Mobile tier badge + language */}
              <div className="px-2 pb-3 flex items-center gap-2">
                <span className={`inline-flex items-center gap-1 ${tierConfig.cls} px-2.5 py-1 rounded-full text-xs font-semibold border`}>
                  <TierIcon className="w-3.5 h-3.5" />
                  {tierConfig.label} Plan
                </span>
                <LanguageSelector />
              </div>

              {/* Dashboard */}
              {standaloneItems
                .filter((item) => item.key === 'dashboard')
                .map((item) => {
                  const Icon = ICON_BY_KEY[item.key] || Home;
                  const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                  return (
                    <Button
                      key={item.key}
                      variant="ghost"
                      size="sm"
                      onClick={() => handleNavigate(item.path, true)}
                      className={`w-full justify-start py-2.5 mb-0.5 ${
                        isActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-100'
                      }`}
                      data-testid={`nav-${item.key}-button`}
                    >
                      <Icon className="w-4 h-4 mr-2" />
                      {t(`navKeys.${item.key}`, item.label)}
                    </Button>
                  );
                })}

              {/* Mobile groups (accordion style) */}
              {NAV_GROUPS.map((groupDef) => {
                const items = groupedItems[groupDef.id];
                if (!items || items.length === 0) return null;

                const GroupIcon = GROUP_ICONS[groupDef.id] || Home;
                const active = isGroupActive(groupDef.id);
                const isExpanded = expandedMobileGroup === groupDef.id;

                return (
                  <div key={groupDef.id} className="mb-0.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setExpandedMobileGroup(isExpanded ? null : groupDef.id)}
                      className={`w-full justify-between py-2.5 ${
                        active && !isExpanded ? 'bg-blue-50 text-blue-700 font-semibold' : 'hover:bg-gray-100'
                      }`}
                    >
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
                            <Button
                              key={item.key}
                              variant="ghost"
                              size="sm"
                              onClick={() => handleNavigate(item.path, true)}
                              className={`w-full justify-start py-2 text-sm ${
                                isItemActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-50'
                              }`}
                              data-testid={`nav-${item.key}-button`}
                            >
                              <Icon className="w-3.5 h-3.5 mr-2" />
                              {t(`navKeys.${item.key}`, item.label)}
                            </Button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Settings */}
              {standaloneItems
                .filter((item) => item.key === 'settings')
                .map((item) => {
                  const Icon = ICON_BY_KEY[item.key] || Home;
                  const isActive = normalizedCurrentModule === normalizeKey(item.key) || location.pathname === item.path;
                  return (
                    <Button
                      key={item.key}
                      variant="ghost"
                      size="sm"
                      onClick={() => handleNavigate(item.path, true)}
                      className={`w-full justify-start py-2.5 mb-0.5 ${
                        isActive ? 'bg-blue-600 text-white hover:bg-blue-700' : 'hover:bg-gray-100'
                      }`}
                      data-testid={`nav-${item.key}-button`}
                    >
                      <Icon className="w-4 h-4 mr-2" />
                      {t(`navKeys.${item.key}`, item.label)}
                    </Button>
                  );
                })}

              {/* Super admin items */}
              {standaloneItems
                .filter((item) => item.requireSuperAdmin)
                .map((item) => {
                  const Icon = ICON_BY_KEY[item.key] || Home;
                  return (
                    <Button
                      key={item.key}
                      variant="ghost"
                      size="sm"
                      onClick={() => handleNavigate(item.path, true)}
                      className="w-full justify-start py-2.5 mb-0.5 hover:bg-gray-100"
                      data-testid={`nav-${item.key}-button`}
                    >
                      <Icon className="w-4 h-4 mr-2" />
                      {t(`navKeys.${item.key}`, item.label)}
                    </Button>
                  );
                })}

              {/* Mobile upgrade banner */}
              {!isSuperAdmin && lockedNav.length > 0 && upgradeTier && (
                <UpgradeBanner requiredTier={upgradeTier} variant="nav-footer" />
              )}
            </nav>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto">
        {children}
      </main>
    </div>
  );
};

export default Layout;
