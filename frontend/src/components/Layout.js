import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Home, Hotel, FileText, TrendingUp, Award, ShoppingCart,
  User, LogOut, Menu, Calendar, DollarSign, Settings as SettingsIcon,
  Layers, BarChart3, Bot, Building2, Zap, Crown, Lock, Shield, Users, ClipboardCheck
} from 'lucide-react';
import LanguageSelector from '@/components/LanguageSelector';
import NotificationBell from '@/components/NotificationBell';
import PushSubscriptionManager from '@/components/PushSubscriptionManager';
import { NAV_ITEMS } from '@/config/navItems';
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
  guest_journey: Award,
};

// ─── Tier badge in header ─────────────────────────────
const TIER_CONFIG = {
  basic: { label: 'Basic', icon: Building2, cls: 'bg-emerald-100 text-emerald-700 border-emerald-200' },
  professional: { label: 'Pro', icon: Zap, cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  enterprise: { label: 'Enterprise', icon: Crown, cls: 'bg-purple-100 text-purple-700 border-purple-200' },
};

const Layout = ({ children, user, tenant, onLogout, currentModule }) => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navScrollRef = useRef(null);

  const isSuperAdmin = user?.role === 'super_admin';

  // ─── Get modules from tenant (set by App.js from /subscription/current) ──
  const modules = useMemo(() => tenant?.modules || {}, [tenant]);

  // ─── Determine current tier ──────────────────────────
  const currentTier = useMemo(() => {
    const tier = tenant?.subscription_tier || 'basic';
    // Handle legacy tier names
    if (tier === 'pro') return 'professional';
    if (tier === 'ultra') return 'enterprise';
    return tier;
  }, [tenant]);

  const tierConfig = TIER_CONFIG[currentTier] || TIER_CONFIG.basic;
  const TierIcon = tierConfig.icon;

  // ─── Determine which tier is needed for upgrade ──────
  const getUpgradeTier = (itemTier) => {
    if (itemTier === 'professional') return 'professional';
    return 'enterprise';
  };

  // ─── Check if module is enabled ──────────────────────
  const isModuleEnabled = (moduleKey) => {
    if (!moduleKey) return true;
    // If modules aren't loaded yet, default to showing (backward compat)
    if (!modules || Object.keys(modules).length === 0) return true;
    // Explicit check
    return modules[moduleKey] !== false && modules[moduleKey] !== undefined ? !!modules[moduleKey] : false;
  };

  // ─── Build navigation items ──────────────────────────
  const { visibleNav, lockedNav, upgradeTier } = useMemo(() => {
    const visible = [];
    const locked = [];
    let nextUpgradeTier = null;

    NAV_ITEMS.forEach((item) => {
      // Hidden items
      if (item.hidden) return;

      // Super admin items (admin panel links)
      if (item.requireSuperAdmin) {
        if (isSuperAdmin) visible.push(item);
        return;
      }

      // Check if module is enabled for this tenant (applies to ALL users including super_admin)
      if (item.moduleKey && isModuleEnabled(item.moduleKey)) {
        visible.push(item);
      } else if (item.moduleKey && !isModuleEnabled(item.moduleKey)) {
        locked.push(item);
        // Determine which tier they should upgrade to
        if (!nextUpgradeTier) {
          nextUpgradeTier = getUpgradeTier(item.tier);
        }
      } else {
        // No moduleKey, show by default
        visible.push(item);
      }
    });

    return { visibleNav: visible, lockedNav: locked, upgradeTier: nextUpgradeTier };
  }, [modules, isSuperAdmin]);

  // ─── Normalize module key for comparison (handle hyphen vs underscore) ──
  const normalizeKey = (key) => key ? key.replace(/-/g, '_') : '';
  const normalizedCurrentModule = normalizeKey(currentModule);

  // ─── Scroll active item into view ────────────────────
  useEffect(() => {
    if (navScrollRef.current && currentModule) {
      // Find active button by matching normalized keys
      const allButtons = navScrollRef.current.querySelectorAll('[data-nav-key]');
      let activeButton = null;
      allButtons.forEach(btn => {
        if (normalizeKey(btn.getAttribute('data-nav-key')) === normalizedCurrentModule) {
          activeButton = btn;
        }
      });
      if (activeButton) {
        // Use requestAnimationFrame for more reliable scroll timing
        requestAnimationFrame(() => {
          activeButton.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        });
      }
    }
  }, [currentModule, normalizedCurrentModule]);

  // ─── Render nav button ───────────────────────────────
  const renderNavButton = (item, isMobile = false) => {
    const Icon = ICON_BY_KEY[item.key] || Home;
    const isActive = normalizedCurrentModule === normalizeKey(item.key);

    return (
      <Button
        key={item.path + item.key}
        variant={isActive ? 'default' : 'ghost'}
        size="sm"
        onClick={() => {
          navigate(item.path);
          if (isMobile) setMobileMenuOpen(false);
        }}
        className={`flex items-center space-x-1.5 ${isMobile ? 'w-full justify-start py-2.5' : 'px-3 py-2 text-xs whitespace-nowrap'} ${
          isActive
            ? 'bg-blue-600 text-white hover:bg-blue-700'
            : 'hover:bg-gray-100'
        }`}
        data-nav-key={item.key}
        data-testid={`nav-${item.key}-button`}
      >
        <Icon className={isMobile ? "w-4 h-4" : "w-3.5 h-3.5"} />
        <span className="font-medium">{t(`navKeys.${item.key}`, item.label)}</span>
      </Button>
    );
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50 shadow-sm">
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            {/* Logo & Hotel Name + Tier Badge */}
            <div className="flex items-center space-x-3">
              <img
                src="/syroce-logo.svg"
                alt="Syroce Logo"
                className="h-10 w-auto cursor-pointer"
                onClick={() => navigate('/')}
              />
              <div className="flex flex-col leading-tight min-w-0">
                <span className="text-xs uppercase tracking-[0.2em] text-gray-400 hidden md:block">
                  Syroce PMS
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className="text-sm font-semibold text-gray-700 truncate max-w-[140px] sm:max-w-[200px]"
                    title={tenant?.property_name || 'Hotel Management'}
                  >
                    {tenant?.property_name || 'Hotel Management'}
                  </span>
                  {/* Tier Badge */}
                  {!isSuperAdmin && (
                    <span className={`hidden sm:inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-semibold ${tierConfig.cls}`}>
                      <TierIcon className="w-3 h-3" />
                      {tierConfig.label}
                    </span>
                  )}
                  {isSuperAdmin && (
                    <span className="hidden sm:inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-semibold bg-red-100 text-red-700 border-red-200">
                      <Shield className="w-3 h-3" />
                      Super Admin
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Desktop Navigation */}
            <nav
              ref={navScrollRef}
              className="hidden md:flex items-center space-x-1 max-w-3xl overflow-x-auto scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-gray-100"
              style={{ scrollBehavior: 'smooth' }}
            >
              {visibleNav.map((item) => renderNavButton(item))}

              {/* Upgrade teaser for locked items - show a subtle indicator */}
              {!isSuperAdmin && lockedNav.length > 0 && upgradeTier && (
                <UpgradeBanner requiredTier={upgradeTier} variant="inline" />
              )}
            </nav>

            {/* User Menu and Utilities */}
            <div className="flex items-center space-x-3">
              <div className="hidden md:block">
                <LanguageSelector />
              </div>
              <PushSubscriptionManager />
              <NotificationBell />
              <Button
                variant="ghost"
                className="md:hidden"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                <Menu className="w-5 h-5" />
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm">
                    <User className="w-4 h-4 mr-2" />
                    {user?.name || 'User'}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>Hesabım</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem className="text-sm">
                    {user?.email}
                  </DropdownMenuItem>
                  <DropdownMenuItem className="text-sm text-gray-500">
                    Rol: {user?.role}
                  </DropdownMenuItem>
                  {!isSuperAdmin && (
                    <DropdownMenuItem className="text-sm text-gray-500">
                      <span className={`inline-flex items-center gap-1 ${tierConfig.cls} px-2 py-0.5 rounded-full text-[10px] font-semibold`}>
                        <TierIcon className="w-3 h-3" />
                        {tierConfig.label} Plan
                      </span>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={onLogout}>
                    <LogOut className="w-4 h-4 mr-2" />
                    {t('common.logout')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {/* Mobile Navigation */}
          {mobileMenuOpen && (
            <nav className="md:hidden mt-4 pb-2 space-y-1 border-t pt-3">
              {/* Mobile tier badge */}
              <div className="px-2 pb-2 flex items-center gap-2">
                <span className={`inline-flex items-center gap-1 ${tierConfig.cls} px-2.5 py-1 rounded-full text-xs font-semibold border`}>
                  <TierIcon className="w-3.5 h-3.5" />
                  {tierConfig.label} Plan
                </span>
                <LanguageSelector />
              </div>

              {visibleNav.map((item) => renderNavButton(item, true))}

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
