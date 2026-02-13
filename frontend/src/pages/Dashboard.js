import { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import Layout from '@/components/Layout';
import { Hotel, FileText, TrendingUp, Award, ShoppingCart, Users, BedDouble, Calendar, Package, Crown, Shield, Sparkles, Bot, Star, Building, CreditCard, Gift, Globe, UserCheck, MessageCircle, Target, Instagram, Zap, Monitor } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import cacheDB from '@/utils/cacheDB';

// Memory cache for dashboard data (faster than IndexedDB)
const dashboardCache = {
  stats: null,
  aiBriefing: null,
  timestamp: null,
  CACHE_DURATION: 30000 // 30 seconds
};

const Dashboard = ({ user, tenant, modules, onLogout }) => {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [stats, setStats] = useState(dashboardCache.stats);
  const [loading, setLoading] = useState(!dashboardCache.stats);
  const [aiBriefing, setAiBriefing] = useState(dashboardCache.aiBriefing);
  const [loadingAI, setLoadingAI] = useState(false);
  const [occupancyData, setOccupancyData] = useState([]);
  const [revenueData, setRevenueData] = useState([]);
  const [trendData, setTrendData] = useState([]);
  const [heatmapData, setHeatmapData] = useState([]);

  const plan =
    tenant?.subscription_plan ||
    tenant?.plan ||
    tenant?.subscription_tier ||
    "core_small_hotel";

  const isLite = plan === "pms_lite";

  if (isLite) {
    return <DashboardLite user={user} tenant={tenant} stats={stats} />;
  }

  const loadAIBriefing = useCallback(async () => {
    setLoadingAI(true);
    try {
      const response = await axios.get('/ai/dashboard/briefing');
      const data = response.data;
      setAiBriefing(data);
      dashboardCache.aiBriefing = data;
    } catch (error) {
      console.error('Failed to load AI briefing:', error);
      // Fail silently - AI features are optional
    } finally {
      setLoadingAI(false);
    }
  }, []);


  const loadChartData = useCallback(async () => {
    try {
      // Load occupancy trend (last 30 days)
      const occupancyRes = await axios.get('/analytics/occupancy-trend?days=30');
      setOccupancyData(occupancyRes.data.trend || []);
      
      // Load revenue trend
      const revenueRes = await axios.get('/analytics/revenue-trend?days=30');
      setRevenueData(revenueRes.data.trend || []);
      
      // Load booking trends
      const trendRes = await axios.get('/analytics/booking-trends?days=30');
      setTrendData(trendRes.data.trend || []);
      
      // Load heatmap data
      const heatmapRes = await axios.get('/rms/demand-heatmap?days=30');
      setHeatmapData(heatmapRes.data.heatmap || []);
    } catch (error) {
      console.error('Failed to load chart data:', error);
      // Generate mock data for demo
      generateMockChartData();
    }
  }, []);

  const generateMockChartData = () => {
    // Mock occupancy data for last 30 days
    const occupancy = [];
    const revenue = [];
    const trends = [];
    
    for (let i = 29; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      const dateStr = date.toISOString().split('T')[0];
      
      occupancy.push({
        date: dateStr,
        occupancy_rate: 60 + Math.random() * 30,
        available_rooms: Math.floor(50 + Math.random() * 50),
        occupied_rooms: Math.floor(100 + Math.random() * 100)
      });
      
      revenue.push({
        date: dateStr,
        room_revenue: 5000 + Math.random() * 5000,
        fnb_revenue: 1000 + Math.random() * 2000,
        other_revenue: 500 + Math.random() * 1000,
        total_revenue: 6500 + Math.random() * 8000
      });
      
      trends.push({
        date: dateStr,
        bookings: Math.floor(5 + Math.random() * 15),
        adr: 100 + Math.random() * 100,
        revpar: 80 + Math.random() * 120
      });
    }
    
    setOccupancyData(occupancy);
    setRevenueData(revenue);
    setTrendData(trends);
  };


  const loadDashboardStats = useCallback(async () => {
    try {
      // Check IndexedDB first (persistent cache)
      const cachedData = await cacheDB.get('dashboard_stats');
      if (cachedData) {
        console.log('📦 Loading from IndexedDB cache');
        setStats(cachedData);
        dashboardCache.stats = cachedData;
        setLoading(false);
        // Load fresh data in background
      }

      // Use Promise.all for parallel requests - faster!
      const [pmsResponse, invoiceResponse] = await Promise.all([
        axios.get('/pms/dashboard'),
        axios.get('/invoices/stats')
      ]);
      
      const statsData = {
        pms: pmsResponse.data,
        invoices: invoiceResponse.data
      };
      
      setStats(statsData);
      dashboardCache.stats = statsData;
      dashboardCache.timestamp = Date.now();
      
      // Save to IndexedDB for next time
      await cacheDB.set('dashboard_stats', statsData, 60000); // 1 minute
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const renderAIBriefingText = (briefing) => {
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

  const renderBriefingItems = (items) => {
    if (!Array.isArray(items) || items.length === 0) return null;

    const priorityLabel = {
      high: 'Yüksek Öncelik',
      medium: 'Orta Öncelik',
      low: 'Düşük Öncelik'
    };

    const priorityBadgeClass = (priority) => {
      switch (priority) {
        case 'high':
          return 'bg-red-500/90 text-white';
        case 'medium':
          return 'bg-amber-500/90 text-white';
        default:
          return 'bg-emerald-500/90 text-white';
      }
    };

    return (
      <div className="space-y-2 mt-2">
        {items.map((item, idx) => {
          if (!item || typeof item !== 'object') return null;
          const priority = (item.priority || 'low').toLowerCase();
          const category = item.category || '';
          const message = item.message || '';
          const insight = item.insight || '';

          return (
            <div
              key={idx}
              className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-xs md:text-sm"
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="inline-flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${priorityBadgeClass(priority)}`}>
                    {priorityLabel[priority] || priorityLabel.low}
                  </span>
                  {category && (
                    <span className="text-[11px] uppercase tracking-wide text-white/70">
                      {category}
                    </span>
                  )}
                </span>
              </div>
              {message && (
                <div className="text-white/90">
                  {typeof message === 'object' ? JSON.stringify(message) : String(message)}
                </div>
              )}
              {insight && (
                <div className="text-white/70 text-[11px] mt-1">
                  {typeof insight === 'object' ? JSON.stringify(insight) : String(insight)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  useEffect(() => {
    const now = Date.now();
    const isCacheValid = dashboardCache.timestamp && (now - dashboardCache.timestamp < dashboardCache.CACHE_DURATION);
    
    if (!isCacheValid) {
      loadDashboardStats();
      loadAIBriefing();
      loadChartData();
    }

    // Prefetch commonly used routes in background
    const prefetchRoutes = () => {
      const routes = ['/pms/dashboard', '/invoices/stats'];
      routes.forEach(route => {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = route;
        document.head.appendChild(link);
      });
    };

    // Prefetch after 2 seconds
    const timer = setTimeout(prefetchRoutes, 2000);
    return () => clearTimeout(timer);
  }, [loadDashboardStats, loadAIBriefing, loadChartData]);

  const visibleModules = useMemo(() => [
    {
      title: t('nav.pms'),
      description: t('dashboard.propertyManagement'),
      icon: Hotel,
      path: '/pms',
      color: '#667eea',
      stats: stats?.pms,
      category: 'core'
    },
    {
      title: t('nav.invoices'),
      description: t('dashboard.billingReporting'),
      icon: FileText,
      path: '/invoices',
      color: '#f093fb',
      stats: stats?.invoices,
      category: 'financial'
    },
    {
      title: t('nav.rms'),
      description: t('dashboard.revenueManagement'),
      icon: TrendingUp,
      path: '/rms',
      color: '#4facfe',
      category: 'revenue'
    },
    {
      title: 'Cost Management',
      description: 'Track operational costs & expenses',
      icon: TrendingUp,
      path: '/cost-management',
      color: '#f093fb',
      badge: 'NEW',
      category: 'financial'
    },
    {
      title: 'Housekeeping',
      description: 'Staff, rooms & task management',
      icon: Hotel,
      path: '/housekeeping',
      color: '#3b82f6',
      badge: 'NEW',
      category: 'core'
    },
    {
      title: 'POS Restaurant',
      description: 'Tables, menu & orders',
      icon: ShoppingCart,
      path: '/pos',
      color: '#f97316',
      badge: 'NEW',
      category: 'core'
    },
    {
      title: '✨ New Features',
      description: 'All new features showcase',
      icon: Award,
      path: '/features',
      color: '#a855f7',
      badge: 'NEW',
      category: 'core'
    },
    {
      title: t('nav.loyalty'),
      description: t('dashboard.guestRewards'),
      icon: Award,
      path: '/loyalty',
      color: '#43e97b',
      category: 'guest'
    },
    {
      title: t('nav.marketplace'),
      description: t('dashboard.wholesalePurchasing'),
      icon: ShoppingCart,
      path: '/marketplace',
      color: '#fa709a',
      category: 'core'
    },
    {
      title: '🏨 Otel Ekipman Stoğu',
      description: 'Otomatik stok takibi ve sipariş yönetimi',
      icon: Package,
      path: '/hotel-inventory',
      color: '#10b981',
      badge: 'NEW',
      category: 'core'
    },
    {
      title: '⚡ Flash Report',
      description: 'Günlük performans özeti - Yönetici raporu',
      icon: TrendingUp,
      path: '/flash-report',
      color: '#8b5cf6',
      badge: 'NEW',
      category: 'management'
    },
    {
      title: '👥 Grup Satış',
      description: 'Grup rezervasyonları ve blok yönetimi',
      icon: Users,
      path: '/group-sales',
      color: '#ec4899',
      badge: 'NEW',
      category: 'revenue'
    },
    {
      title: '👑 VIP Yönetimi',
      description: 'VIP profiller, özel protokoller ve kutlamalar',
      icon: Crown,
      path: '/vip-management',
      color: '#a855f7',
      badge: 'NEW',
      category: 'guest'
    },
    {
      title: '📊 Sales CRM',
      description: 'Lead yönetimi ve satış hunisi',
      icon: TrendingUp,
      path: '/sales-crm',
      color: '#3b82f6',
      badge: 'NEW',
      category: 'revenue'
    },
    {
      title: '🛡️ Service Recovery',
      description: 'Şikayet yönetimi ve çözüm takibi',
      icon: Shield,
      path: '/service-recovery',
      color: '#ef4444',
      badge: 'NEW',
      category: 'guest'
    },
    {
      title: '🧖 Spa & Wellness',
      description: 'Spa randevuları ve treatment yönetimi',
      icon: Sparkles,
      path: '/spa-wellness',
      color: '#8b5cf6',
      badge: 'NEW',
      category: 'guest'
    },
    {
      title: '🏛️ Meeting & Events',
      description: 'Toplantı odaları ve etkinlik yönetimi',
      icon: Calendar,
      path: '/meeting-events',
      color: '#f59e0b',
      badge: 'NEW',
      category: 'revenue'
    },
    {
      title: '🤖 AI Chatbot',
      description: 'AI destekli misafir asistanı',
      icon: Bot,
      path: '/ai-chatbot',
      color: '#06b6d4',
      badge: 'NEW',
      category: 'ai'
    },
    {
      title: '🤖 AI Dynamic Pricing',
      description: 'Rakip analizi ve otomatik fiyatlandırma',
      icon: TrendingUp,
      path: '/dynamic-pricing',
      color: '#8b5cf6',
      badge: 'AI',
      category: 'ai'
    },
    {
      title: '⭐ Reputation Center',
      description: 'Online itibar yönetimi ve review tracking',
      icon: Star,
      path: '/reputation-center',
      color: '#f59e0b',
      badge: 'NEW',
      category: 'guest'
    },
    {
      title: '🏢 Multi-Property',
      description: 'Çoklu otel yönetimi dashboard',
      icon: Building,
      path: '/multi-property',
      color: '#06b6d4',
      badge: 'NEW',
      category: 'management'
    },
    {
      title: '💳 Payment Gateway',
      description: 'Stripe, PayPal, Crypto ödeme entegrasyonu',
      icon: CreditCard,
      path: '/payment-gateway',
      color: '#10b981',
      badge: 'NEW',
      category: 'financial'
    },
    {
      title: '🎯 Advanced Loyalty',
      description: 'Gamification, referral, tier management',
      icon: Gift,
      path: '/advanced-loyalty',
      color: '#f59e0b',
      badge: 'NEW',
      category: 'guest'
    },
    {
      title: '🌍 GDS Integration',
      description: 'Amadeus, Sabre, Galileo entegrasyonu',
      icon: Globe,
      path: '/gds-integration',
      color: '#3b82f6',
      badge: 'NEW',
      category: 'revenue'
    },
    {
      title: '👥 Staff Management',
      description: 'Personel, vardiya ve performans yönetimi',
      icon: Users,
      path: '/staff-management',
      color: '#10b981',
      badge: 'NEW',
      category: 'management'
    },
    {
      title: '🛤️ Guest Journey',
      description: 'Misafir yolculuğu ve NPS tracking',
      icon: TrendingUp,
      path: '/guest-journey',
      color: '#8b5cf6',
      badge: 'NEW',
      category: 'guest'
    },
    {
      title: '📋 Arrival List',
      description: 'Bugünün varışları - VIP, grup ve özel istekler',
      icon: UserCheck,
      path: '/arrival-list',
      color: '#10b981',
      badge: 'NEW',
      category: 'core'
    },
    {
      title: '🤖 AI WhatsApp Concierge',
      description: '24/7 Otomatik misafir hizmeti - Sıfır insan',
      icon: MessageCircle,
      path: '/ai-whatsapp-concierge',
      color: '#10b981',
      badge: 'GAME-CHANGER',
      category: 'ai'
    },
    {
      title: '🔮 Predictive Analytics',
      description: 'No-show, talep, şikayet tahminleri - AI Oracle',
      icon: Target,
      path: '/predictive-analytics',
      color: '#8b5cf6',
      badge: 'GAME-CHANGER',
      category: 'ai'
    },
    {
      title: '📡 Social Media Radar',
      description: 'Instagram, Twitter, Facebook monitoring - Real-time',
      icon: Instagram,
      path: '/social-media-radar',
      color: '#ec4899',
      badge: 'GAME-CHANGER',
      category: 'ai'
    },
    {
      title: '⚡ Revenue Autopilot',
      description: 'Tam otomatik revenue optimization - Sıfır müdahale',
      icon: Zap,
      path: '/revenue-autopilot',
      color: '#8b5cf6',
      badge: 'GAME-CHANGER',
      category: 'ai'
    },
    {
      title: '👥 HR Complete Suite',
      description: 'Time & Attendance, Payroll, Leave, Recruitment',
      icon: Users,
      path: '/hr-complete',
      color: '#10b981',
      badge: 'COMPLETE',
      category: 'management'
    },
    {
      title: '🍳 F&B Complete Suite',
      description: 'Recipe Costing, BEO, Kitchen Display, Inventory',
      icon: ShoppingCart,
      path: '/fnb-complete',
      color: '#f97316',
      badge: 'COMPLETE',
      category: 'core'
    },
    {
      title: '📺 Kitchen Display',
      description: 'Real-time mutfak ekranı - Sipariş takibi',
      icon: Monitor,
      path: '/kitchen-display',
      color: '#ef4444',
      badge: 'NEW',
      category: 'core'
    }
  ], [t, stats]);

  // Backend modül yetkilerine göre kartları filtrele
  const filteredModules = useMemo(() => {
    if (!modules) return visibleModules;

    return visibleModules.filter((m) => {
      // PMS & mobil
      if (m.path === '/pms') return modules.pms !== false;
      if (m.path === '/mobile' || m.path?.startsWith('/mobile/')) return modules.pms_mobile !== false;

      // Raporlar
      if (m.path === '/reports' || m.path === '/flash-report') return modules.reports !== false;

      // Faturalar & finans
      if (m.path === '/invoices' || m.path === '/efatura' || m.path === '/e-fatura' || m.path === '/pending-ar' || m.path === '/cost-management') {
        return modules.invoices !== false;
      }

      // AI alt modülleri
      if (m.path === '/ai-chatbot') return modules.ai_chatbot !== false;
      if (m.path === '/dynamic-pricing') return modules.ai_pricing !== false;
      if (m.path === '/ai-whatsapp-concierge') return modules.ai_whatsapp !== false;
      if (m.path === '/predictive-analytics') return modules.ai_predictive !== false;
      if (m.path === '/reputation-center') return modules.ai_reputation !== false;
      if (m.path === '/revenue-autopilot') return modules.ai_revenue_autopilot !== false;
      if (m.path === '/social-media-radar') return modules.ai_social_radar !== false;

      // AI kategorisi genel fallback: ana ai kapalıysa gizle
      if (m.category === 'ai' || m.path === '/ai-pms') return modules.ai !== false;

      // Diğer modüller şimdilik her zaman görünür
      return true;
    });
  }, [visibleModules, modules]);

  // Kategorilere göre modülleri grupla
  const categorizedModules = useMemo(() => {
    const categories = {
      core: { title: '🏨 Core Operations', color: 'blue', modules: [] },
      revenue: { title: '💰 Revenue & Sales', color: 'green', modules: [] },
      guest: { title: '👤 Guest Experience', color: 'purple', modules: [] },
      ai: { title: '🤖 AI & Game-Changers', color: 'pink', modules: [] },
      financial: { title: '💵 Financial', color: 'emerald', modules: [] },
      management: { title: '📊 Management & Reports', color: 'indigo', modules: [] }
    };

    filteredModules.forEach(module => {
      const category = module.category || 'core';
      if (categories[category]) {
        categories[category].modules.push(module);
      }
    });

    return categories;
  }, [filteredModules]);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="dashboard">
      <div className="p-4 md:p-6 space-y-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold mb-1" style={{ fontFamily: 'Space Grotesk' }}>
            {t('dashboard.welcome')}, {user.name}
          </h1>
          <p className="text-sm md:text-base text-gray-600">{tenant?.property_name || 'Hotel Management System'}</p>
        </div>

        {loading ? (
          <div className="text-center py-12">{t('common.loading')}</div>
        ) : (
          <>
            {/* AI Daily Briefing Card */}
            {aiBriefing && (
              <Card className="bg-gradient-to-r from-blue-500 to-purple-600 text-white mb-4">
                <CardHeader className="p-4">
                  <CardTitle className="flex items-center justify-between text-base md:text-lg">
                    <span className="flex items-center">
                      <span className="text-xl mr-2">🤖</span>
                      {t('ai.dailyBriefing')}
                    </span>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={loadAIBriefing}
                      className="text-white hover:bg-white/20 text-xs"
                      disabled={loadingAI}
                    >
                      {loadingAI ? t('ai.loading') : t('ai.refreshInsights')}
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <div className="text-sm md:text-base leading-relaxed mb-3">
                    {typeof aiBriefing.summary === 'string'
                      ? aiBriefing.summary
                      : (() => {
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
                      <div className="opacity-75 text-xs">Doluluk Oranı</div>
                      <div className="text-lg font-bold">{typeof aiBriefing.metrics?.occupancy_rate === 'number' ? aiBriefing.metrics.occupancy_rate.toFixed(1) : '0'}%</div>
                    </div>
                    <div>
                      <div className="opacity-75 text-xs">Bugünkü Check-in</div>
                      <div className="text-lg font-bold">{typeof aiBriefing.metrics?.today_checkins === 'number' ? aiBriefing.metrics.today_checkins : 0}</div>
                    </div>
                    <div>
                      <div className="opacity-75 text-xs">Bugünkü Check-out</div>
                      <div className="text-lg font-bold">{typeof aiBriefing.metrics?.today_checkouts === 'number' ? aiBriefing.metrics.today_checkouts : 0}</div>
                    </div>
                    <div>
                      <div className="opacity-75 text-xs">Aylık Ciro</div>
                      <div className="text-lg font-bold">${typeof aiBriefing.metrics?.monthly_revenue === 'number' ? aiBriefing.metrics.monthly_revenue.toFixed(0) : '0'}</div>
                    </div>
                  </div>
                  <div className="text-xs opacity-75 mt-2 text-right">
                    {t('ai.poweredBy')} • Generated: {new Date(aiBriefing.generated_at).toLocaleTimeString()}
                  </div>
                </CardContent>
              </Card>
            )}

            {loadingAI && !aiBriefing && (
              <Card className="bg-gradient-to-r from-blue-500 to-purple-600 text-white mb-6">
                <CardContent className="py-8">
                  <div className="flex items-center justify-center">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mr-3"></div>
                    <span className="text-lg">{t('ai.loading')}</span>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Quick Stats */}
            {stats?.pms && (
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 gap-3">
                <Card className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-blue-100 rounded-lg">
                        <BedDouble className="w-6 h-6 text-blue-500" />
                      </div>
                      <div className="text-2xl font-bold text-gray-900">{stats.pms.total_rooms}</div>
                      <div className="text-xs font-medium text-gray-600">{t('dashboard.totalRooms')}</div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-green-100 rounded-lg">
                        <Hotel className="w-6 h-6 text-green-500" />
                      </div>
                      <div className="text-2xl font-bold text-gray-900">{(typeof stats.pms.occupancy_rate === 'number' ? stats.pms.occupancy_rate : 0).toFixed(1)}%</div>
                      <div className="text-xs font-medium text-gray-600">{t('dashboard.occupancyRate')}</div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-purple-100 rounded-lg">
                        <Calendar className="w-6 h-6 text-purple-500" />
                      </div>
                      <div className="text-2xl font-bold text-gray-900">{stats.pms.today_checkins}</div>
                      <div className="text-xs font-medium text-gray-600">{t('dashboard.todayCheckins')}</div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4 text-center">
                    <div className="flex flex-col items-center space-y-2">
                      <div className="p-2 bg-orange-100 rounded-lg">
                        <Users className="w-6 h-6 text-orange-500" />
                      </div>
                      <div className="text-2xl font-bold text-gray-900">{stats.pms.total_guests}</div>
                      <div className="text-xs font-medium text-gray-600">{t('dashboard.totalGuests')}</div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Modules Grid - Categorized with Accordion */}


            {/* Analytics & Charts Section */}
            <div className="space-y-4">
              <h2 className="text-xl md:text-2xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
                Analytics & Insights
              </h2>
              
              {/* Occupancy & Revenue Charts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Occupancy Trend */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Occupancy Trend (30 Days)</CardTitle>
                    <CardDescription>Daily occupancy percentage</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart data={occupancyData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="date" 
                          tick={{ fontSize: 10 }}
                          tickFormatter={(value) => new Date(value).getDate()}
                        />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip 
                          labelFormatter={(value) => new Date(value).toLocaleDateString()}
                          formatter={(value) => `${(typeof value === 'number' ? value : 0).toFixed(1)}%`}
                        />
                        <Area 
                          type="monotone" 
                          dataKey="occupancy_rate" 
                          stroke="#3b82f6" 
                          fill="#3b82f6" 
                          fillOpacity={0.3}
                          name="Occupancy"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* Revenue Trend */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Revenue Trend (30 Days)</CardTitle>
                    <CardDescription>Daily revenue breakdown</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={250}>
                      <BarChart data={revenueData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="date" 
                          tick={{ fontSize: 10 }}
                          tickFormatter={(value) => new Date(value).getDate()}
                        />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip 
                          labelFormatter={(value) => new Date(value).toLocaleDateString()}
                          formatter={(value) => `$${(typeof value === 'number' ? value : 0).toFixed(0)}`}
                        />
                        <Legend wrapperStyle={{ fontSize: '12px' }} />
                        <Bar dataKey="room_revenue" fill="#10b981" name="Room" />
                        <Bar dataKey="fnb_revenue" fill="#f59e0b" name="F&B" />
                        <Bar dataKey="other_revenue" fill="#6366f1" name="Other" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </div>

              {/* Booking Trends & ADR */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Booking Trends */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Booking Trends</CardTitle>
                    <CardDescription>Daily bookings & ADR performance</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart data={trendData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="date" 
                          tick={{ fontSize: 10 }}
                          tickFormatter={(value) => new Date(value).getDate()}
                        />
                        <YAxis yAxisId="left" tick={{ fontSize: 10 }} />
                        <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
                        <Tooltip 
                          labelFormatter={(value) => new Date(value).toLocaleDateString()}
                        />
                        <Legend wrapperStyle={{ fontSize: '12px' }} />
                        <Line 
                          yAxisId="left"
                          type="monotone" 
                          dataKey="bookings" 
                          stroke="#8b5cf6" 
                          strokeWidth={2}
                          name="Bookings"
                        />
                        <Line 
                          yAxisId="right"
                          type="monotone" 
                          dataKey="adr" 
                          stroke="#10b981" 
                          strokeWidth={2}
                          name="ADR ($)"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                {/* RevPAR & Performance */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">RevPAR Performance</CardTitle>
                    <CardDescription>Revenue per available room</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={250}>
                      <AreaChart data={trendData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="date" 
                          tick={{ fontSize: 10 }}
                          tickFormatter={(value) => new Date(value).getDate()}
                        />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip 
                          labelFormatter={(value) => new Date(value).toLocaleDateString()}
                          formatter={(value) => `$${(typeof value === 'number' ? value : 0).toFixed(2)}`}
                        />
                        <Area 
                          type="monotone" 
                          dataKey="revpar" 
                          stroke="#f59e0b" 
                          fill="#f59e0b" 
                          fillOpacity={0.4}
                          name="RevPAR"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </div>

              {/* Occupancy Heatmap */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">30-Day Occupancy Heatmap</CardTitle>
                  <CardDescription>Visual representation of daily occupancy levels</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-10 gap-1">
                    {occupancyData.slice(0, 30).map((day, index) => {
                      const rate = typeof day.occupancy_rate === 'number' ? day.occupancy_rate : 0;
                      const color = 
                        rate >= 90 ? 'bg-red-600' :
                        rate >= 80 ? 'bg-orange-500' :
                        rate >= 70 ? 'bg-yellow-500' :
                        rate >= 60 ? 'bg-green-500' :
                        rate >= 50 ? 'bg-blue-500' :
                        'bg-gray-300';
                      
                      return (
                        <div
                          key={index}
                          className={`${color} rounded p-2 text-center text-white text-xs font-semibold cursor-pointer hover:scale-110 transition-transform`}
                          title={`${new Date(day.date).toLocaleDateString()}: ${rate.toFixed(1)}% occupied`}
                        >
                          {new Date(day.date).getDate()}
                          <div className="text-[10px]">{rate.toFixed(0)}%</div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex justify-center gap-4 mt-4 text-xs">
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-gray-300 rounded"></div>
                      <span>&lt;50%</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-blue-500 rounded"></div>
                      <span>50-60%</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-green-500 rounded"></div>
                      <span>60-70%</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-yellow-500 rounded"></div>
                      <span>70-80%</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-orange-500 rounded"></div>
                      <span>80-90%</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-3 h-3 bg-red-600 rounded"></div>
                      <span>&gt;90%</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="space-y-4">
              <h2 className="text-xl md:text-2xl font-bold mb-4" style={{ fontFamily: 'Space Grotesk' }}>{t('dashboard.yourModules')}</h2>
              
              <Accordion type="multiple" defaultValue={['ai']} className="space-y-3">
                {Object.entries(categorizedModules).map(([categoryKey, category]) => (
                  category.modules.length > 0 && (
                    <AccordionItem key={categoryKey} value={categoryKey} className="border rounded-lg bg-white shadow-sm">
                      <AccordionTrigger className="px-4 py-3 hover:no-underline hover:bg-gray-50">
                        <div className="flex items-center gap-3 flex-1">
                          <h3 className="text-lg font-bold text-gray-800">{category.title}</h3>
                          <Badge variant="outline" className="text-xs">
                            {category.modules.length} modül
                          </Badge>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-4 pb-4 pt-2">
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                          {category.modules.map((module) => {
                        const Icon = module.icon;
                        return (
                          <Card 
                            key={module.path} 
                            className={`card-hover cursor-pointer ${module.badge === 'GAME-CHANGER' ? 'border-2 border-pink-500 shadow-lg' : module.badge === 'AI' ? 'border-2 border-purple-400 shadow-lg' : module.badge === 'NEW' ? 'border-2 border-blue-300 shadow-md' : ''}`}
                            onClick={() => navigate(module.path)}
                            data-testid={`module-${module.title.toLowerCase()}`}
                          >
                            <CardHeader className="p-4">
                              <div className="flex items-center space-x-2">
                                <div 
                                  style={{ 
                                    background: module.color,
                                    padding: '8px',
                                    borderRadius: '8px'
                                  }}
                                >
                                  <Icon className="w-5 h-5 text-white" />
                                </div>
                                <div className="flex-1">
                                  <div className="flex items-center justify-between">
                                    <CardTitle className="text-base">{module.title}</CardTitle>
                                    {module.badge && (
                                      <span className={`px-1.5 py-0.5 text-xs font-bold rounded ${
                                        module.badge === 'GAME-CHANGER' ? 'bg-pink-100 text-pink-700' :
                                        module.badge === 'AI' ? 'bg-purple-100 text-purple-700' :
                                        'bg-blue-100 text-blue-700'
                                      }`}>
                                        {module.badge}
                                      </span>
                                    )}
                                  </div>
                                  <CardDescription className="text-xs">{module.description}</CardDescription>
                                </div>
                              </div>
                            </CardHeader>
                            {module.stats && (
                              <CardContent>
                                <div className="grid grid-cols-2 gap-2 text-sm">
                                  {Object.entries(module.stats).slice(0, 2).map(([key, value]) => (
                                    <div key={key}>
                                      <p className="text-gray-500 capitalize">{key.replace('_', ' ')}</p>
                                      <p className="font-semibold">{typeof value === 'number' ? value.toFixed(0) : (typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value ?? ''))}</p>
                                    </div>
                                  ))}
                                </div>
                              </CardContent>
                            )}
                          </Card>
                        );
                      })}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  )
                ))}
              </Accordion>
            </div>
          </>
        )}
      </div>
    </Layout>
  );
};

import PmsLiteOnboarding from "@/components/PmsLiteOnboarding";

const DashboardLite = ({ user, tenant, stats }) => {
  const navigate = useNavigate();

  return (
    <Layout user={user} tenant={tenant} onLogout={() => {}} currentModule="dashboard">
      <div className="p-4 md:p-6 space-y-4">
        <PmsLiteOnboarding tenant={tenant} />
        <div>
          <h1 className="text-2xl md:text-3xl font-bold mb-1" style={{ fontFamily: 'Space Grotesk' }}>
            Dashboard
          </h1>
          <p className="text-sm md:text-base text-gray-600">Günlük özet ve hızlı işlemler.</p>
        </div>

        {/* Core stat cards */}
        {stats?.pms && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 gap-3">
            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-blue-100 rounded-lg">
                    <BedDouble className="w-6 h-6 text-blue-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900">{stats.pms.total_rooms}</div>
                  <div className="text-xs font-medium text-gray-600">Toplam Oda</div>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-green-100 rounded-lg">
                    <Hotel className="w-6 h-6 text-green-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900">{(typeof stats.pms.occupancy_rate === 'number' ? stats.pms.occupancy_rate : 0).toFixed(1)}%</div>
                  <div className="text-xs font-medium text-gray-600">Doluluk Oranı</div>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-purple-100 rounded-lg">
                    <Calendar className="w-6 h-6 text-purple-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900">{stats.pms.today_checkins}</div>
                  <div className="text-xs font-medium text-gray-600">Bugün Giriş</div>
                </div>
              </CardContent>
            </Card>

            <Card className="hover:shadow-md transition-shadow">
              <CardContent className="p-4 text-center">
                <div className="flex flex-col items-center space-y-2">
                  <div className="p-2 bg-orange-100 rounded-lg">
                    <Users className="w-6 h-6 text-orange-500" />
                  </div>
                  <div className="text-2xl font-bold text-gray-900">{stats.pms.total_guests}</div>
                  <div className="text-xs font-medium text-gray-600">Toplam Misafir</div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Quick actions */}
        <div className="rounded-2xl border bg-white p-4">
          <div className="text-sm font-medium text-gray-900">Hızlı İşlemler</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => window.location.assign("/app/pms#frontdesk")}>
              Yeni Rezervasyon
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => window.location.assign("/app/reservation-calendar")}
            >
              Takvimi Aç
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => window.location.assign("/app/pms#frontdesk")}
            >
              Rezervasyonlar
            </Button>
          </div>
        </div>
      </div>
    </Layout>
  );
};

export default Dashboard;
