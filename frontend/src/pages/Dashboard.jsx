import { lazy, Suspense, useState, useEffect, useLayoutEffect, useMemo, useCallback, useRef } from 'react';
import axios from 'axios';
import { canAccessPath } from '@/utils/moduleAccess';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Hotel, FileText, TrendingUp, TrendingDown, Minus, Award, ShoppingCart, Users, BedDouble, Calendar, Package, Shield, Sparkles, Bot, Star, Building, Gift, UserCheck, MessageCircle, Target, Instagram, Zap, Monitor, ArrowRight } from 'lucide-react';
import CommandCenter from '@/components/CommandCenter';
import RoleStart from '@/components/experience/RoleStart';
import DashboardWelcome from '@/components/experience/DashboardWelcome';
import ProductState from '@/components/shared/ProductState';
import { runIdle } from '@/lib/idle';
import { useCurrency } from '@/context/CurrencyContext';

const DashboardAnalytics = lazy(() => import('@/components/DashboardAnalytics'));

// Dashboard cards are shortcuts to product modules, not a second catalogue.
// Keep their entitlement key explicit: an unknown/missing key must never turn
// into a visible upsell or a route that the hotel did not select.
const DASHBOARD_MODULE_KEYS = {
  '/pms': ['pms'],
  '/invoices': ['invoices', 'invoices_basic'],
  '/rms': ['revenue_management'],
  '/cost-management': ['cost_management'],
  '/housekeeping': ['housekeeping', 'housekeeping_advanced'],
  '/pos': ['pos_basic', 'pos_fnb'],
  '/features': ['pms'],
  '/loyalty': ['loyalty_program'],
  '/marketplace': ['marketplace'],
  '/hotel-inventory': ['pms'],
  '/flash-report': ['reports', 'basic_reporting'],
  '/group-sales': ['group_sales'],
  '/crm': ['sales_crm'],
  '/service-recovery': ['guest_advanced'],
  '/spa-wellness': ['spa'],
  '/ai-chatbot': ['ai', 'ai_chatbot'],
  '/dynamic-pricing': ['ai', 'ai_pricing'],
  '/app/multi-property': ['multi_property'],
  '/staff-management': ['hr'],
  '/guest-journey': ['guests', 'guest_advanced'],
  '/arrival-list': ['pms'],
  '/ai-whatsapp-concierge': ['ai', 'ai_whatsapp'],
  '/predictive-analytics': ['ai', 'ai_predictive'],
  '/social-media-radar': ['ai', 'ai_social_radar'],
  '/revenue-autopilot': ['ai', 'ai_revenue_autopilot'],
  '/hr-complete': ['hr'],
  '/fnb-complete': ['pos_basic', 'pos_fnb'],
  '/kitchen-display': ['pos_fnb'],
};

// Hafif inline SVG sparkline — recharts overhead yok, 4 KPI kartına uygun.
const Sparkline = ({
  values,
  stroke = '#0ea5e9',
  fill = 'rgba(14,165,233,0.12)',
  height = 32
}) => {
  if (!values || values.length < 2) {
    return <div className="h-8 w-full flex items-center justify-center text-[10px] text-slate-300">veri yok</div>;
  }
  const w = 100;
  const h = height;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = w / (values.length - 1);
  const points = values.map((v, i) => `${(i * step).toFixed(2)},${(h - (v - min) / range * (h - 4) - 2).toFixed(2)}`);
  const path = `M ${points.join(' L ')}`;
  const area = `${path} L ${w},${h} L 0,${h} Z`;
  const first = values[0];
  const last = values[values.length - 1];
  const delta = first === 0 ? 0 : (last - first) / Math.abs(first) * 100;
  const TrendIcon = Math.abs(delta) < 1 ? Minus : delta > 0 ? TrendingUp : TrendingDown;
  const trendCls = Math.abs(delta) < 1 ? 'text-muted-foreground' : delta > 0 ? 'text-emerald-600' : 'text-rose-600';
  return <div className="w-full">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full" style={{
      height
    }}>
        <path d={area} fill={fill} />
        <path d={path} fill="none" stroke={stroke} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className={`flex items-center justify-center gap-1 mt-0.5 text-[10px] font-medium ${trendCls}`}>
        <TrendIcon className="w-3 h-3" />
        <span>{delta > 0 ? '+' : ''}{delta.toFixed(1)}% / 7g</span>
      </div>
    </div>;
};

// Memory cache for dashboard data (faster than IndexedDB)
const dashboardCache = {
  stats: null,
  aiBriefing: null,
  aiBriefingLanguage: null,
  timestamp: null,
  tenantKey: null,
  CACHE_DURATION: 30000 // 30 seconds
};
const Dashboard = ({
  user,
  tenant,
  modules,
  onLogout
}) => {
  const navigate = useNavigate();
  const {
    t,
    i18n
  } = useTranslation();
  const {
    format: fmtMoney,
    symbol: currencySymbol
  } = useCurrency();
  const tenantCacheKey = tenant?.id || tenant?._id || tenant?.tenant_id || user?.tenant_id || 'unknown';
  const interfaceLanguage = (i18n.resolvedLanguage || i18n.language || 'tr').split('-')[0];
  const isCurrentTenantCache = dashboardCache.tenantKey === tenantCacheKey;
  const isCurrentBriefingCache = isCurrentTenantCache && dashboardCache.aiBriefingLanguage === interfaceLanguage;
  const activeTenantKeyRef = useRef(tenantCacheKey);
  activeTenantKeyRef.current = tenantCacheKey;
  const [stats, setStats] = useState(() => isCurrentTenantCache ? dashboardCache.stats : null);
  const [loading, setLoading] = useState(() => !(isCurrentTenantCache && dashboardCache.stats));
  const [aiBriefing, setAiBriefing] = useState(() => isCurrentBriefingCache ? dashboardCache.aiBriefing : null);
  const [loadingAI, setLoadingAI] = useState(false);
  const [occupancyData, setOccupancyData] = useState([]);
  const [revenueData, setRevenueData] = useState([]);
  const [trendData, setTrendData] = useState([]);
  const [analyticsReady, setAnalyticsReady] = useState(false);
  const plan = tenant?.subscription_plan || tenant?.plan || tenant?.subscription_tier || "core_small_hotel";
  const isLite = plan === "pms_lite";

  // NOT: pms_lite erken-return'ü AŞAĞIDA tüm hook'lardan SONRA yapılıyor
  // (react-hooks/rules-of-hooks: hook'lar koşullu çağrılamaz). DashboardLite
  // render kararı `isLite` flag'ine göre tüm hook'lar deklare edildikten
  // sonra alınır.

  // Süperadmin tesis değiştirdiğinde önceki tesisin KPI veya yapay zekâ özeti
  // hiç görünmemeli. Layout effect bu state'i tarayıcı boyamadan sıfırlar;
  // böylece hızlı çalışma alanı geçişinde kısa bir veri sızıntısı oluşmaz.
  useLayoutEffect(() => {
    const cacheMatchesTenant = dashboardCache.tenantKey === tenantCacheKey;
    setStats(cacheMatchesTenant ? dashboardCache.stats : null);
    setAiBriefing(cacheMatchesTenant && dashboardCache.aiBriefingLanguage === interfaceLanguage ? dashboardCache.aiBriefing : null);
    setOccupancyData([]);
    setRevenueData([]);
    setTrendData([]);
    setAnalyticsReady(false);
    setLoading(!(cacheMatchesTenant && dashboardCache.stats));
  }, [tenantCacheKey, interfaceLanguage]);

  const loadAIBriefing = useCallback(async (requestTenantKey, requestLanguage) => {
    setLoadingAI(true);
    try {
      const response = await axios.get(`/ai/dashboard/briefing?lang=${encodeURIComponent(requestLanguage)}`);
      const data = response.data;
      if (activeTenantKeyRef.current !== requestTenantKey || requestLanguage !== interfaceLanguage) return;
      setAiBriefing(data);
      if (dashboardCache.tenantKey === requestTenantKey) {
        dashboardCache.aiBriefing = data;
        dashboardCache.aiBriefingLanguage = requestLanguage;
      }
    } catch (error) {
      console.error('Failed to load AI briefing:', error);
      // Fail silently - AI features are optional
    } finally {
      if (activeTenantKeyRef.current === requestTenantKey && requestLanguage === interfaceLanguage) setLoadingAI(false);
    }
  }, [interfaceLanguage]);
  const loadChartData = useCallback(async (requestTenantKey) => {
    const endpoints = [{
      url: '/analytics/occupancy-trend?days=30',
      key: 'trend',
      set: setOccupancyData
    }, {
      url: '/analytics/revenue-trend?days=30',
      key: 'trend',
      set: setRevenueData
    }, {
      url: '/analytics/booking-trends?days=30',
      key: 'trend',
      set: setTrendData
    }];
    const results = await Promise.allSettled(endpoints.map(e => axios.get(e.url)));
    if (activeTenantKeyRef.current !== requestTenantKey) return;
    results.forEach((res, i) => {
      const {
        key,
        set,
        url
      } = endpoints[i];
      if (res.status === 'fulfilled') {
        set(res.value.data?.[key] || []);
      } else {
        console.error(`Failed to load ${url}:`, res.reason);
        set([]);
      }
    });
  }, []);
  const loadDashboardStats = useCallback(async (requestTenantKey) => {
    try {
      // PMS KPI'ları ana ekran için kritiktir. Fatura özeti aynı anda başlasın
      // fakat yavaş bir finans servisi kontrol panelinin tamamını bekletmesin.
      const invoiceStatsPromise = axios.get('/invoices/stats').catch(() => ({ data: {} }));
      const pmsResponse = await axios.get('/pms/dashboard').catch(() => ({ data: {} }));
      const statsData = {
        pms: pmsResponse.data || {},
        invoices: dashboardCache.tenantKey === requestTenantKey
          ? dashboardCache.stats?.invoices || {}
          : {}
      };
      if (activeTenantKeyRef.current !== requestTenantKey) return;
      setStats(statsData);
      dashboardCache.stats = statsData;
      dashboardCache.timestamp = Date.now();
      dashboardCache.tenantKey = requestTenantKey;

      void invoiceStatsPromise.then((invoiceResponse) => {
        if (activeTenantKeyRef.current !== requestTenantKey) return;
        const nextStats = {
          ...statsData,
          invoices: invoiceResponse.data || {}
        };
        setStats(nextStats);
        if (dashboardCache.tenantKey === requestTenantKey) dashboardCache.stats = nextStats;
      });
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      if (activeTenantKeyRef.current === requestTenantKey) setLoading(false);
    }
  }, []);
  const renderAIBriefingText = briefing => {
    if (!briefing) return null;
    if (typeof briefing === 'string') {
      return briefing;
    }
    if (typeof briefing === 'object') {
      try {
        return JSON.stringify(briefing);
      } catch (e) {
        return String(briefing);
      }
    }
    return String(briefing);
  };
  const renderBriefingItems = items => {
    if (!Array.isArray(items) || items.length === 0) return null;
    const priorityLabel = {
      high: t('dashboard.highPriority'),
      medium: t('dashboard.mediumPriority'),
      low: t('dashboard.lowPriority')
    };
    const priorityBadgeClass = priority => {
      switch (priority) {
        case 'high':
          return 'bg-red-500/90 text-white';
        case 'medium':
          return 'bg-amber-500/90 text-white';
        default:
          return 'bg-emerald-500/90 text-white';
      }
    };
    return <div className="space-y-2 mt-2">
        {items.map((item, idx) => {
        if (!item || typeof item !== 'object') return null;
        const priority = (item.priority || 'low').toLowerCase();
        const category = item.category || '';
        const message = item.message || '';
        const insight = item.insight || '';
        return <div key={idx} className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-xs md:text-sm">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="inline-flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${priorityBadgeClass(priority)}`}>
                    {priorityLabel[priority] || priorityLabel.low}
                  </span>
                  {category && <span className="text-[11px] uppercase tracking-wide text-white/70">
                      {category}
                    </span>}
                </span>
              </div>
              {message && <div className="text-white/90">
                  {typeof message === 'object' ? JSON.stringify(message) : String(message)}
                </div>}
              {insight && <div className="text-white/70 text-[11px] mt-1">
                  {typeof insight === 'object' ? JSON.stringify(insight) : String(insight)}
                </div>}
            </div>;
      })}
      </div>;
  };
  useEffect(() => {
    const now = Date.now();
    const isCacheValid = dashboardCache.tenantKey === tenantCacheKey && dashboardCache.timestamp && now - dashboardCache.timestamp < dashboardCache.CACHE_DURATION;
    let cancelIdle = () => {};
    if (!isCacheValid) {
      // KPI'lar (PMS dashboard + invoice stats) ana ekranın görsel iskeleti
      // — hemen yüklensin. AI briefing ve grafik verileri
      // ikincil; idle'a alınınca KPI'lar saniyeler önce ekrana basılır.
      loadDashboardStats(tenantCacheKey);
    }
    // Grafikler sunucu tarafında önbelleğe alınmış KPI verisinden bağımsızdır.
    // Her mount'ta idle slotunda istenir; böylece sıcak dashboard'da boş grafik
    // bırakılmaz, ama ilk ekran ağ ve CPU kaynaklarıyla yarışmaz.
    cancelIdle = runIdle(() => {
      loadAIBriefing(tenantCacheKey, interfaceLanguage);
      loadChartData(tenantCacheKey);
      setAnalyticsReady(true);
    }, {
      timeout: 4000
    });

    // API base URL'si /api olduğundan, burada document'a eklenen
    // "/pms/dashboard" ve "/invoices/stats" linkleri API önbelleğini
    // ısıtmıyordu. Bunun yerine SPA rotası olarak istenip gereksiz iki ağ
    // isteği ve yanıt işleme maliyeti çıkarıyordu. KPI isteği zaten axios
    // önbelleği üzerinden bu verileri yüklediği için ek bir prefetch yok.
    return () => cancelIdle();
  }, [tenantCacheKey, interfaceLanguage, loadDashboardStats, loadAIBriefing, loadChartData]);
  const visibleModules = useMemo(() => [{
    title: t('nav.pms'),
    description: t('dashboard.propertyManagement'),
    icon: Hotel,
    path: '/pms',
    color: '#667eea',
    stats: stats?.pms,
    category: 'core'
  }, {
    title: t('nav.invoices'),
    description: t('dashboard.billingReporting'),
    icon: FileText,
    path: '/invoices',
    color: '#f093fb',
    stats: stats?.invoices,
    category: 'financial'
  }, {
    title: t('nav.rms'),
    description: t('dashboard.revenueManagement'),
    icon: TrendingUp,
    path: '/rms',
    color: '#4facfe',
    category: 'revenue'
  }, {
    title: t('dashboard.costManagement'),
    description: t('dashboard.costManagementDesc'),
    icon: TrendingUp,
    path: '/cost-management',
    color: '#f093fb',
    badge: 'NEW',
    category: 'financial'
  }, {
    title: t('dashboard.housekeepingTitle'),
    description: t('dashboard.housekeepingDesc'),
    icon: Hotel,
    path: '/housekeeping',
    color: '#3b82f6',
    badge: 'NEW',
    category: 'core'
  }, {
    title: t('dashboard.posRestaurant'),
    description: t('dashboard.posDesc'),
    icon: ShoppingCart,
    path: '/pos',
    color: '#f97316',
    badge: 'NEW',
    category: 'core'
  }, {
    title: t('dashboard.newFeatures'),
    description: t('dashboard.newFeaturesDesc'),
    icon: Award,
    path: '/features',
    color: '#a855f7',
    badge: 'NEW',
    category: 'core'
  }, {
    title: t('nav.loyalty'),
    description: t('dashboard.guestRewards'),
    icon: Award,
    path: '/loyalty',
    color: '#43e97b',
    category: 'guest'
  }, {
    title: t('nav.marketplace'),
    description: t('dashboard.wholesalePurchasing'),
    icon: ShoppingCart,
    path: '/marketplace',
    color: '#fa709a',
    category: 'core'
  }, {
    title: t('dashboard.hotelInventory'),
    description: t('dashboard.hotelInventoryDesc'),
    icon: Package,
    path: '/hotel-inventory',
    color: '#10b981',
    badge: 'NEW',
    category: 'core'
  }, {
    title: t('dashboard.flashReport'),
    description: t('dashboard.flashReportDesc'),
    icon: TrendingUp,
    path: '/flash-report',
    color: '#8b5cf6',
    badge: 'NEW',
    category: 'management'
  }, {
    title: t('dashboard.groupSales'),
    description: t('dashboard.groupSalesDesc'),
    icon: Users,
    path: '/group-sales',
    color: '#ec4899',
    badge: 'NEW',
    category: 'revenue'
  }, {
    title: t('dashboard.salesCRM'),
    description: t('dashboard.salesCRMDesc'),
    icon: TrendingUp,
    path: '/crm',
    color: '#3b82f6',
    badge: 'NEW',
    category: 'revenue'
  }, {
    title: t('dashboard.serviceRecovery'),
    description: t('dashboard.serviceRecoveryDesc'),
    icon: Shield,
    path: '/service-recovery',
    color: '#ef4444',
    badge: 'NEW',
    category: 'guest'
  }, {
    title: t('dashboard.spaWellness'),
    description: t('dashboard.spaWellnessDesc'),
    icon: Sparkles,
    path: '/spa-wellness',
    color: '#8b5cf6',
    badge: 'NEW',
    category: 'guest'
  }, {
    title: t('dashboard.aiChatbot'),
    description: t('dashboard.aiChatbotDesc'),
    icon: Bot,
    path: '/ai-chatbot',
    color: '#06b6d4',
    badge: 'NEW',
    category: 'ai'
  }, {
    title: t('dashboard.dynamicPricingModule'),
    description: t('dashboard.dynamicPricingModuleDesc'),
    icon: TrendingUp,
    path: '/dynamic-pricing',
    color: '#8b5cf6',
    badge: 'AI',
    category: 'ai'
  }, {
    title: t('dashboard.multiProperty'),
    description: t('dashboard.multiPropertyDesc'),
    icon: Building,
    path: '/app/multi-property',
    color: '#06b6d4',
    badge: 'NEW',
    category: 'management'
  }, {
    title: t('dashboard.staffManagement'),
    description: t('dashboard.staffManagementDesc'),
    icon: Users,
    path: '/staff-management',
    color: '#10b981',
    badge: 'NEW',
    category: 'management'
  }, {
    title: t('dashboard.guestJourney'),
    description: t('dashboard.guestJourneyDesc'),
    icon: TrendingUp,
    path: '/guest-journey',
    color: '#8b5cf6',
    badge: 'NEW',
    category: 'guest'
  }, {
    title: t('dashboard.arrivalList'),
    description: t('dashboard.arrivalListDesc'),
    icon: UserCheck,
    path: '/arrival-list',
    color: '#10b981',
    badge: 'NEW',
    category: 'core'
  }, {
    title: t('dashboard.aiWhatsApp'),
    description: t('dashboard.aiWhatsAppDesc'),
    icon: MessageCircle,
    path: '/ai-whatsapp-concierge',
    color: '#10b981',
    badge: 'GAME-CHANGER',
    category: 'ai'
  }, {
    title: t('dashboard.predictiveAnalytics'),
    description: t('dashboard.predictiveAnalyticsDesc'),
    icon: Target,
    path: '/predictive-analytics',
    color: '#8b5cf6',
    badge: 'GAME-CHANGER',
    category: 'ai'
  }, {
    title: t('dashboard.socialMediaRadar'),
    description: t('dashboard.socialMediaRadarDesc'),
    icon: Instagram,
    path: '/social-media-radar',
    color: '#ec4899',
    badge: 'GAME-CHANGER',
    category: 'ai'
  }, {
    title: t('dashboard.revenueAutopilot'),
    description: t('dashboard.revenueAutopilotDesc'),
    icon: Zap,
    path: '/revenue-autopilot',
    color: '#8b5cf6',
    badge: 'GAME-CHANGER',
    category: 'ai'
  }, {
    title: t('dashboard.hrSuite'),
    description: t('dashboard.hrSuiteDesc'),
    icon: Users,
    path: '/hr-complete',
    color: '#10b981',
    badge: 'COMPLETE',
    category: 'management'
  }, {
    title: t('dashboard.fnbSuite'),
    description: t('dashboard.fnbSuiteDesc'),
    icon: ShoppingCart,
    path: '/fnb-complete',
    color: '#f97316',
    badge: 'COMPLETE',
    category: 'core'
  }, {
    title: t('dashboard.kitchenDisplay'),
    description: t('dashboard.kitchenDisplayDesc'),
    icon: Monitor,
    path: '/kitchen-display',
    color: '#ef4444',
    badge: 'NEW',
    category: 'core'
  }], [t, stats]);

  // Dashboard always reflects the selected hotel's effective module set.
  // Platform privilege may still allow an administrator to navigate to a
  // diagnostic route, but it must not make an unpurchased module look active.
  const isSuperAdmin = user?.role === 'super_admin' || Array.isArray(user?.roles) && user.roles.includes('super_admin');
  const filteredModules = useMemo(() => {
    const accessibleModules = visibleModules.filter(m => canAccessPath(user, m.path));
    if (!modules || Object.keys(modules).length === 0) return [];
    return accessibleModules.filter(m => {
      const requiredKeys = DASHBOARD_MODULE_KEYS[m.path];
      return Array.isArray(requiredKeys) && requiredKeys.every((key) => modules[key] === true);
    });
  }, [visibleModules, modules, user]);

  // Kategorilere göre modülleri grupla
  const categorizedModules = useMemo(() => {
    const categories = {
      core: {
        title: t('dashboard.coreOps'),
        color: 'blue',
        modules: []
      },
      revenue: {
        title: t('dashboard.revenueSales'),
        color: 'green',
        modules: []
      },
      guest: {
        title: t('dashboard.guestExperience'),
        color: 'purple',
        modules: []
      },
      ai: {
        title: t('dashboard.aiGameChangers'),
        color: 'pink',
        modules: []
      },
      financial: {
        title: t('dashboard.financial'),
        color: 'emerald',
        modules: []
      },
      management: {
        title: t('dashboard.managementReports'),
        color: 'indigo',
        modules: []
      }
    };
    filteredModules.forEach(module => {
      const category = module.category || 'core';
      if (categories[category]) {
        categories[category].modules.push(module);
      }
    });
    return categories;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [filteredModules]);

  // pms_lite için DashboardLite render et — tüm hook'lar yukarıda
  // koşulsuz olarak çağrıldıktan SONRA güvenle erken-return yapılabilir.
  if (isLite) {
    return <DashboardLite user={user} tenant={tenant} stats={stats} />;
  }
  return <>
      <div className="p-4 md:p-6 space-y-4" role="main" aria-label="Ana gösterge paneli">
        <DashboardWelcome user={user} tenant={tenant} />

        {loading ? <ProductState state="loading" moduleName={t('dashboard.title', { defaultValue: 'Kontrol paneli' })} compact showDashboardLink={false} /> : <>
            <RoleStart user={user} tenant={tenant} />
            <CommandCenter />
            <details className="rounded-xl border bg-card p-4"><summary className="cursor-pointer font-semibold">{t("experience.summary", "Günlük değerlendirme")}</summary><p className="my-2 text-sm text-muted-foreground">{t("experience.summaryScope", "Otomatik özet, oluşturulduğu anı yansıtır. Güncel operasyon durumunu iş listelerinden doğrulayın.")}</p>
            {/* AI Daily Briefing Card */}
            {aiBriefing && <Card className="bg-slate-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100 mb-4 border-0 shadow-lg" role="region" aria-label="Yapay zeka günlük brifing">
                <CardHeader className="p-4">
                  <CardTitle className="flex items-center justify-between text-base md:text-lg">
                    <span className="flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-amber-300" aria-hidden="true" />
                      {aiBriefing.ai_powered ? t('ai.dailyBriefing') : t('ai.dailySummary')}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => loadAIBriefing(tenantCacheKey, interfaceLanguage)}
                      className="text-slate-700 hover:bg-slate-200 text-xs"
                      disabled={loadingAI}
                      aria-label={loadingAI ? t('ai.loading') : t('ai.refreshInsights')}
                      aria-busy={loadingAI}
                    >
                      {loadingAI ? t('ai.loading') : t('ai.refreshInsights')}
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <div className="text-sm md:text-base leading-relaxed mb-3">
                    {typeof aiBriefing.summary === 'string' ? aiBriefing.summary : (() => {
                try {
                  return JSON.stringify(aiBriefing.summary);
                } catch (e) {
                  return String(aiBriefing.summary);
                }
              })()}
                  </div>
                  {renderBriefingItems(aiBriefing.briefing_items)}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs bg-white/10 rounded-lg p-3 mt-3">
                    <div>
                      <div className="opacity-75 text-xs">{t('dashboard.occupancyRate')}</div>
                      <div className="text-lg font-bold">{typeof aiBriefing.metrics?.occupancy_rate === 'number' ? aiBriefing.metrics.occupancy_rate.toFixed(1) : '0'}%</div>
                    </div>
                    <div>
                      <div className="opacity-75 text-xs">{t('dashboard.todayCheckins')}</div>
                      <div className="text-lg font-bold">{typeof aiBriefing.metrics?.today_checkins === 'number' ? aiBriefing.metrics.today_checkins : 0}</div>
                    </div>
                    <div>
                      <div className="opacity-75 text-xs">{t('dashboard.todayCheckOut')}</div>
                      <div className="text-lg font-bold">{typeof aiBriefing.metrics?.today_checkouts === 'number' ? aiBriefing.metrics.today_checkouts : 0}</div>
                    </div>
                    <div>
                      <div className="opacity-75 text-xs">{t('dashboard.monthlyTurnover')}</div>
                      <div className="text-lg font-bold">{fmtMoney(aiBriefing.metrics?.monthly_revenue || 0, {
                    decimals: 0
                  })}</div>
                    </div>
                  </div>
                  <div className="text-xs opacity-75 mt-2 text-right">
                    {aiBriefing.ai_powered ? t('ai.poweredBy') : t('ai.autoSummary')} • {new Date(aiBriefing.generated_at).toLocaleTimeString()}
                  </div>
                </CardContent>
              </Card>}

            {loadingAI && !aiBriefing && <Card className="bg-slate-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100 mb-6 border-0">
                <CardContent className="py-8">
                  <div className="flex items-center justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mr-3"></div>
                    <span className="text-lg">{t('ai.loading')}</span>
                  </div>
                </CardContent>
              </Card>}

            </details>

            {/* Quick Stats — KPI kartları + son 7 gün sparkline */}
            {stats?.pms && (() => {
          const occ7 = (occupancyData || []).slice(-7).map(d => Number(d?.occupancy_rate) || 0);
          const book7 = (trendData || []).slice(-7).map(d => Number(d?.bookings) || 0);
          // Toplam misafir = günlük doluluk × oda sayısı (yaklaşık dolu yatak); semantik olarak misafir trendine yakın.
          const totalRooms = Number(stats?.pms?.total_rooms) || 0;
          const guests7 = occ7.map(o => Math.round(o / 100 * totalRooms));
          // Sabit envanter için düz çizgi (görsel tutarlılık).
          const rooms7 = totalRooms > 0 ? Array(7).fill(totalRooms) : [];
          return <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 gap-3" role="list" aria-label="Otel KPI metrikleri">
                <Card className="hover:shadow-md transition-shadow border-slate-200" role="listitem">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-slate-100 rounded-lg" aria-hidden="true">
                        <BedDouble className="w-6 h-6 text-slate-600" aria-hidden="true" />
                      </div>
                      <div className="text-2xl font-bold text-slate-900" aria-label={`Toplam oda sayısı: ${stats.pms.total_rooms}`}>{stats.pms.total_rooms}</div>
                      <div className="text-xs font-medium text-slate-600">{t('dashboard.totalRooms')}</div>
                      <Sparkline values={rooms7} stroke="#64748b" fill="rgba(100,116,139,0.10)" />
                    </div>
                  </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-shadow border-amber-200 bg-amber-50/30" role="listitem">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-amber-100 rounded-lg" aria-hidden="true">
                        <Hotel className="w-6 h-6 text-amber-700" aria-hidden="true" />
                      </div>
                      <div className="text-2xl font-bold text-amber-800" aria-label={`Doluluk oranı: ${(typeof stats.pms.occupancy_rate === 'number' ? stats.pms.occupancy_rate : 0).toFixed(1)} yüzde`}>{(typeof stats.pms.occupancy_rate === 'number' ? stats.pms.occupancy_rate : 0).toFixed(1)}%</div>
                      <div className="text-xs font-medium text-slate-600">{t('dashboard.occupancyRate')}</div>
                      <Sparkline values={occ7} stroke="#d97706" fill="rgba(217,119,6,0.12)" />
                    </div>
                  </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-shadow border-emerald-200" role="listitem">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-emerald-100 rounded-lg" aria-hidden="true">
                        <Calendar className="w-6 h-6 text-emerald-700" aria-hidden="true" />
                      </div>
                      <div className="text-2xl font-bold text-slate-900" aria-label={`Bugünkü check-in sayısı: ${stats.pms.today_checkins}`}>{stats.pms.today_checkins}</div>
                      <div className="text-xs font-medium text-slate-600">{t('dashboard.todayCheckins')}</div>
                      <Sparkline values={book7} stroke="#059669" fill="rgba(5,150,105,0.12)" />
                    </div>
                  </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-shadow border-sky-200" role="listitem">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-sky-100 rounded-lg" aria-hidden="true">
                        <Users className="w-6 h-6 text-sky-700" aria-hidden="true" />
                      </div>
                      <div className="text-2xl font-bold text-slate-900" aria-label={`Toplam misafir sayısı: ${stats.pms.total_guests}`}>{stats.pms.total_guests}</div>
                      <div className="text-xs font-medium text-slate-600">{t('dashboard.totalGuests')}</div>
                      <Sparkline values={guests7} stroke="#0284c7" fill="rgba(2,132,199,0.12)" />
                    </div>
                  </CardContent>
                </Card>
              </div>;
        })()}

            {isSuperAdmin && <details className="rounded-xl border bg-card p-3"><summary className="cursor-pointer text-sm font-medium">Platform yönetimi</summary><Button variant="link" onClick={() => navigate("/app/migration-observability")}>{t("dashboard.migrationObservability")}</Button></details>}

            {/* Modules Grid - Categorized with Accordion */}


            {analyticsReady && <Suspense fallback={<div className="h-24" aria-hidden="true" />}>
                <DashboardAnalytics occupancyData={occupancyData} revenueData={revenueData} trendData={trendData} formatMoney={fmtMoney} currencySymbol={currencySymbol} />
              </Suspense>}

            <div className="space-y-4">
              <h2 className="text-xl md:text-2xl font-bold mb-4" style={{
            fontFamily: 'Space Grotesk'
          }}>{t('dashboard.yourModules')}</h2>
              
              <Accordion type="multiple" defaultValue={['ai']} className="space-y-3">
                {Object.entries(categorizedModules).map(([categoryKey, category]) => category.modules.length > 0 && <AccordionItem key={categoryKey} value={categoryKey} className="border rounded-lg bg-white dark:bg-card shadow-sm">
                      <AccordionTrigger className="px-4 py-3 hover:no-underline hover:bg-gray-50 dark:hover:bg-slate-800/50">
                        <div className="flex items-center gap-3 flex-1">
                          <h3 className="text-lg font-bold text-gray-800 dark:text-slate-100">{category.title}</h3>
                          <Badge variant="outline" className="text-xs">
                            {category.modules.length} {t('dashboard.modules')}
                          </Badge>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-4 pb-4 pt-2">
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                          {category.modules.map(module => {
                    const Icon = module.icon;
                    return <Card key={module.path} className={`card-hover cursor-pointer ${'border-slate-200'}`} onClick={() => navigate(module.path)} data-testid={`module-${module.title.toLowerCase()}`}>
                            <CardHeader className="p-4">
                              <div className="flex items-center space-x-2">
                                <div style={{
                            background: module.color,
                            padding: '8px',
                            borderRadius: '8px'
                          }}>
                                  <Icon className="w-5 h-5 text-white" />
                                </div>
                                <div className="flex-1">
                                  <div className="flex items-center justify-between">
                                    <CardTitle className="text-base">{module.title}</CardTitle>
                                    {module.badge === 'NEW' && <span className={`px-1.5 py-0.5 text-xs font-bold rounded ${module.badge === 'GAME-CHANGER' ? 'bg-pink-100 text-pink-700' : module.badge === 'AI' ? 'bg-indigo-100 text-indigo-700' : 'bg-blue-100 text-blue-700'}`}>
                                        {module.badge === 'NEW'
                                          ? t('common.new')
                                          : module.badge === 'GAME-CHANGER'
                                            ? t('dashboard.innovative')
                                            : module.badge}
                                      </span>}
                                  </div>
                                  <CardDescription className="text-xs">{module.description}</CardDescription>
                                </div>
                              </div>
                            </CardHeader>
                            {module.stats && <CardContent>
                                <div className="grid grid-cols-2 gap-2 text-sm">
                                  {Object.entries(module.stats).slice(0, 2).map(([key, value]) => <div key={key}>
                                      <p className="text-muted-foreground capitalize">{key.replace('_', ' ')}</p>
                                      <p className="font-semibold">{typeof value === 'number' ? value.toFixed(0) : typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? '')}</p>
                                    </div>)}
                                </div>
                              </CardContent>}
                          </Card>;
                  })}
                        </div>
                      </AccordionContent>
                    </AccordionItem>)}
              </Accordion>
            </div>
          </>}
      </div>
    </>;
};
import PmsLiteOnboarding from "@/components/PmsLiteOnboarding";
const DashboardLite = ({
  user,
  tenant,
  stats
}) => {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  return <>
      <div className="p-4 md:p-6 space-y-4">
        <PmsLiteOnboarding tenant={tenant} />
        <div>
          <h1 className="text-2xl md:text-3xl font-bold mb-1" style={{
          fontFamily: 'Space Grotesk'
        }}>
            {t('nav.dashboard')}
          </h1>
          <p className="text-sm md:text-base text-gray-600 dark:text-slate-300">{t('dashboard.dailySummaryDesc')}</p>
        </div>

        {/* Core stat cards */}
        {stats?.pms && <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 gap-3">
            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-blue-100 rounded-lg">
                    <BedDouble className="w-6 h-6 text-blue-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.pms.total_rooms}</div>
                  <div className="text-xs font-medium text-gray-600 dark:text-slate-300">{t('dashboard.totalRooms')}</div>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-green-100 rounded-lg">
                    <Hotel className="w-6 h-6 text-green-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">{(typeof stats.pms.occupancy_rate === 'number' ? stats.pms.occupancy_rate : 0).toFixed(1)}%</div>
                  <div className="text-xs font-medium text-gray-600 dark:text-slate-300">{t('dashboard.occupancyRate')}</div>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-indigo-100 rounded-lg">
                    <Calendar className="w-6 h-6 text-indigo-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.pms.today_checkins}</div>
                  <div className="text-xs font-medium text-gray-600 dark:text-slate-300">{t('dashboard.todayCheckins')}</div>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-amber-100 rounded-lg">
                    <Users className="w-6 h-6 text-amber-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.pms.total_guests}</div>
                  <div className="text-xs font-medium text-gray-600 dark:text-slate-300">{t('dashboard.totalGuests')}</div>
                </div>
              </CardContent>
            </Card>
          </div>}

        {/* Quick actions */}
        <div className="rounded-2xl border border-slate-200 bg-white dark:bg-card p-4">
          <div className="text-sm font-semibold text-slate-900">{t('dashboard.quickActions')}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" className="bg-amber-600 hover:bg-amber-700 text-white" onClick={() => navigate("/app/pms#frontdesk")}>
              {t('dashboard.newReservation')}
            </Button>
            <Button size="sm" variant="outline" className="border-slate-300" onClick={() => navigate("/app/reservation-calendar")}>
              {t('dashboard.openCalendar')}
            </Button>
            <Button size="sm" variant="outline" className="border-slate-300" onClick={() => navigate("/app/pms#frontdesk")}>
              {t('dashboard.reservations')}
            </Button>
          </div>
        </div>
      </div>
    </>;
};
export default Dashboard;
