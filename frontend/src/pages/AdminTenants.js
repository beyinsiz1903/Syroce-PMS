import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { Link } from 'react-router-dom';
import {
  Calendar, Clock, Building2, ChevronDown, ChevronUp, Shield,
  Zap, Crown, Search, RefreshCw, AlertTriangle, CheckCircle2,
  Settings2, Users, BarChart3, Bot
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

// ─── Plan definitions ────────────────────────────────────────
const PLANS = {
  basic: {
    key: 'basic',
    label: 'Basic',
    labelTr: 'Basic',
    color: 'emerald',
    bgClass: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    iconBg: 'bg-emerald-100',
    icon: Building2,
    description: '1-15 oda • Küçük otel / pansiyon',
    maxRooms: 15,
    maxUsers: 3,
    price: '79€/ay',
  },
  professional: {
    key: 'professional',
    label: 'Professional',
    labelTr: 'Profesyonel',
    color: 'blue',
    bgClass: 'bg-blue-50 border-blue-200 text-blue-700',
    badgeClass: 'bg-blue-100 text-blue-800 border-blue-200',
    iconBg: 'bg-blue-100',
    icon: Zap,
    description: '15-80 oda • Orta ölçek otel',
    maxRooms: 80,
    maxUsers: 15,
    price: '299€/ay',
  },
  enterprise: {
    key: 'enterprise',
    label: 'Enterprise',
    labelTr: 'Kurumsal',
    color: 'purple',
    bgClass: 'bg-purple-50 border-purple-200 text-purple-700',
    badgeClass: 'bg-purple-100 text-purple-800 border-purple-200',
    iconBg: 'bg-purple-100',
    icon: Crown,
    description: '80+ oda • 5★ / zincir otel',
    maxRooms: null,
    maxUsers: null,
    price: '799€/ay',
  },
};

// ─── Module group definitions ────────────────────────────────
const MODULE_GROUPS = [
  {
    id: 'core',
    title: 'Core Modüller',
    icon: Settings2,
    description: 'Tüm planlarda dahil olan temel PMS özellikleri',
    color: 'gray',
    items: [
      { key: 'pms', label: 'PMS Core', hint: 'Rezervasyon, check-in/out, oda yönetimi', tier: 'basic' },
      { key: 'reservation_calendar', label: 'Rezervasyon Takvimi', hint: 'Drag & drop takvim görünümü', tier: 'basic' },
      { key: 'dashboard', label: 'Dashboard', hint: 'Ana kontrol paneli', tier: 'basic' },
      { key: 'guests', label: 'Misafir Yönetimi', hint: 'Temel misafir profilleri', tier: 'basic' },
      { key: 'housekeeping', label: 'Housekeeping', hint: 'Temel oda durumu takibi', tier: 'basic' },
      { key: 'basic_reporting', label: 'Temel Raporlar', hint: 'Günlük doluluk ve gelir', tier: 'basic' },
      { key: 'settings', label: 'Ayarlar', hint: 'Otel ayarları', tier: 'basic' },
      { key: 'pms_mobile', label: 'Mobil PMS', hint: 'Mobil erişim', tier: 'basic' },
      { key: 'invoices_basic', label: 'Basit Fatura', hint: 'PDF fatura oluşturma', tier: 'basic' },
    ],
  },
  {
    id: 'professional',
    title: 'Professional Modüller',
    icon: BarChart3,
    description: 'Orta ölçek oteller için gelişmiş özellikler',
    color: 'blue',
    items: [
      { key: 'channel_manager', label: 'Channel Manager', hint: 'OTA senkronizasyonu', tier: 'professional' },
      { key: 'folio_management', label: 'Folio Yönetimi', hint: 'Split, routing, posting', tier: 'professional' },
      { key: 'night_audit', label: 'Gece Denetimi', hint: 'End-of-day otomasyonu', tier: 'professional' },
      { key: 'invoices', label: 'Gelişmiş Fatura & Finans', hint: 'E-fatura, AR/AP', tier: 'professional' },
      { key: 'cost_management', label: 'Maliyet Yönetimi', hint: 'Maliyet takibi', tier: 'professional' },
      { key: 'reports', label: 'Gelişmiş Raporlar', hint: 'Detaylı analitik raporlar', tier: 'professional' },
      { key: 'mobile_housekeeping', label: 'Mobil Housekeeping', hint: 'Mobil görev yönetimi', tier: 'professional' },
      { key: 'rate_management', label: 'Rate Management', hint: 'Fiyat planı yönetimi', tier: 'professional' },
      { key: 'booking_engine', label: 'Booking Engine', hint: 'Direkt rezervasyon motoru', tier: 'professional' },
      { key: 'guest_advanced', label: 'Gelişmiş Misafir Profili', hint: 'VIP, tercihler, LTV', tier: 'professional' },
    ],
  },
  {
    id: 'enterprise',
    title: 'Enterprise Modüller',
    icon: Crown,
    description: 'Büyük oteller ve zincirler için kurumsal özellikler',
    color: 'purple',
    items: [
      { key: 'revenue_management', label: 'Revenue Management', hint: 'Dinamik fiyatlandırma, RMS', tier: 'enterprise' },
      { key: 'multi_property', label: 'Multi-Property', hint: 'Çoklu otel yönetimi', tier: 'enterprise' },
      { key: 'group_sales', label: 'Grup Satış & MICE', hint: 'Grup rezervasyon, etkinlik', tier: 'enterprise' },
      { key: 'sales_crm', label: 'Satış CRM', hint: 'Pipeline, lead yönetimi', tier: 'enterprise' },
      { key: 'loyalty_program', label: 'Sadakat Programı', hint: 'Puan, tier, ödüller', tier: 'enterprise' },
      { key: 'gm_dashboards', label: 'GM Dashboard', hint: 'Executive özet dashboard', tier: 'enterprise' },
      { key: 'mobile_revenue', label: 'Mobil Revenue', hint: 'Mobil gelir yönetimi', tier: 'enterprise' },
      { key: 'advanced_analytics', label: 'Gelişmiş Analitik', hint: 'BI dashboard', tier: 'enterprise' },
      { key: 'api_access', label: 'API Erişimi', hint: 'Open API, webhook', tier: 'enterprise' },
      { key: 'white_label', label: 'White Label', hint: 'Özel branding', tier: 'enterprise' },
      { key: 'audit_trail', label: 'Audit Trail', hint: 'Compliance logging', tier: 'enterprise' },
    ],
  },
  {
    id: 'ai',
    title: 'Yapay Zeka Modülleri',
    icon: Bot,
    description: 'AI destekli akıllı özellikler (Enterprise dahil, diğerleri add-on)',
    color: 'amber',
    items: [
      { key: 'ai', label: 'AI Genel Anahtar', hint: 'Tüm AI modüllerinin üst anahtarı', tier: 'enterprise' },
      { key: 'ai_chatbot', label: 'AI Chatbot', hint: 'Akıllı misafir asistanı', tier: 'enterprise' },
      { key: 'ai_pricing', label: 'AI Dynamic Pricing', hint: 'ML fiyat önerileri', tier: 'enterprise' },
      { key: 'ai_whatsapp', label: 'AI WhatsApp Concierge', hint: 'WhatsApp otonom asistan', tier: 'enterprise' },
      { key: 'ai_predictive', label: 'AI Tahminler', hint: 'No-show, demand prediction', tier: 'enterprise' },
      { key: 'ai_reputation', label: 'AI Reputation', hint: 'Yorum analizi', tier: 'enterprise' },
      { key: 'ai_revenue_autopilot', label: 'AI Revenue Autopilot', hint: 'Otomatik gelir yönetimi', tier: 'enterprise' },
      { key: 'ai_social_radar', label: 'AI Social Radar', hint: 'Sosyal medya takibi', tier: 'enterprise' },
    ],
  },
];

// ─── Helpers ─────────────────────────────────────────────────
const tierRank = { basic: 0, professional: 1, enterprise: 2 };

const isModuleIncludedInPlan = (moduleItem, tenantTier) => {
  const moduleTier = moduleItem.tier || 'enterprise';
  return tierRank[tenantTier] >= tierRank[moduleTier];
};

const PlanBadge = ({ tier }) => {
  const plan = PLANS[tier] || PLANS.basic;
  const Icon = plan.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border font-semibold ${plan.badgeClass}`}>
      <Icon className="w-3.5 h-3.5" />
      {plan.label}
    </span>
  );
};

// ─── Main Component ──────────────────────────────────────────
const AdminTenants = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tenants, setTenants] = useState([]);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [filter, setFilter] = useState('');
  const [tierFilter, setTierFilter] = useState('all');
  const [expandedTenants, setExpandedTenants] = useState({});

  // Subscription modal
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [subscriptionDays, setSubscriptionDays] = useState(30);
  const [subscriptionStartDate, setSubscriptionStartDate] = useState('');
  const [subscriptionEndDate, setSubscriptionEndDate] = useState('');

  // Plan change modal
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [planChangeTenant, setPlanChangeTenant] = useState(null);
  const [selectedNewPlan, setSelectedNewPlan] = useState('basic');
  const [resetModulesOnPlanChange, setResetModulesOnPlanChange] = useState(true);

  const loadTenants = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/admin/tenants');
      setTenants(res.data?.tenants || []);
    } catch (err) {
      console.error('Failed to load tenants', err);
      setError('Otelleri yüklerken bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTenants();
  }, []);

  // Auto-dismiss success messages
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [success]);

  // ─── Module toggle ──────────────────────────────
  const handleToggle = async (tenantId, moduleKey, value) => {
    setSaving(true);
    setError(null);
    try {
      const currentTenant = tenants.find((t) => t.id === tenantId || t._id === tenantId);
      const currentModules = currentTenant?.modules || {};
      const updatedModules = { ...currentModules, [moduleKey]: value };

      const res = await axios.patch(`/admin/tenants/${tenantId}/modules`, {
        modules: updatedModules,
      });

      const updated = res.data;
      setTenants((prev) =>
        prev.map((t) =>
          t.id === tenantId || t._id === tenantId
            ? { ...t, modules: updated.modules }
            : t
        )
      );
    } catch (err) {
      console.error('Failed to update modules', err);
      setError('Modülleri güncellerken bir hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  // ─── Plan change ────────────────────────────────
  const handlePlanChange = async () => {
    if (!planChangeTenant) return;
    setSaving(true);
    setError(null);
    try {
      const res = await axios.patch(`/admin/tenants/${planChangeTenant.id}/tier`, {
        tier: selectedNewPlan,
        reset_modules: resetModulesOnPlanChange,
      });

      if (res.data?.success) {
        setSuccess(`${planChangeTenant.property_name} planı "${PLANS[selectedNewPlan]?.label}" olarak güncellendi`);
        setShowPlanModal(false);
        await loadTenants();
      }
    } catch (err) {
      console.error('Failed to change plan', err);
      setError(err.response?.data?.detail || 'Plan güncellenirken bir hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  // ─── Subscription update ────────────────────────
  const handleUpdateSubscription = async () => {
    if (!selectedTenant) return;
    setSaving(true);
    setError(null);
    try {
      await axios.patch(`/admin/tenants/${selectedTenant.id}/subscription`, {
        subscription_days: subscriptionDays || null,
        subscription_start_date: subscriptionStartDate || null,
        subscription_end_date: subscriptionEndDate || null,
      });
      setShowSubscriptionModal(false);
      setSuccess('Üyelik süresi başarıyla güncellendi');
      await loadTenants();
    } catch (err) {
      console.error('Failed to update subscription', err);
      setError(err.response?.data?.detail || 'Üyelik güncellenirken bir hata oluştu');
    } finally {
      setSaving(false);
    }
  };

  const formatDateInput = (d) => {
    try {
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      return `${yyyy}-${mm}-${dd}`;
    } catch {
      return '';
    }
  };

  const openSubscriptionModal = (t) => {
    setSelectedTenant(t);
    setSubscriptionDays(30);
    const start = new Date();
    const end = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000);
    setSubscriptionStartDate(formatDateInput(start));
    setSubscriptionEndDate(formatDateInput(end));
    setShowSubscriptionModal(true);
  };

  const openPlanModal = (t) => {
    setPlanChangeTenant(t);
    setSelectedNewPlan(t.subscription_tier || 'basic');
    setResetModulesOnPlanChange(true);
    setShowPlanModal(true);
  };

  const toggleExpand = (tenantId) => {
    setExpandedTenants((prev) => ({ ...prev, [tenantId]: !prev[tenantId] }));
  };

  // Filter tenants
  const filteredTenants = useMemo(() => {
    return tenants.filter((t) => {
      const name = (t.property_name || t.name || '').toLowerCase();
      const matchesName = !filter || name.includes(filter.toLowerCase());
      const matchesTier = tierFilter === 'all' || (t.subscription_tier || 'basic') === tierFilter;
      return matchesName && matchesTier;
    });
  }, [tenants, filter, tierFilter]);

  // Tier counts
  const tierCounts = useMemo(() => {
    const counts = { basic: 0, professional: 0, enterprise: 0 };
    tenants.forEach((t) => {
      const tier = t.subscription_tier || 'basic';
      if (counts[tier] !== undefined) counts[tier]++;
      else counts.basic++;
    });
    return counts;
  }, [tenants]);

  // ─── Count enabled modules ─────────────────────
  const countEnabledModules = (t) => {
    const mods = t.modules || {};
    return Object.values(mods).filter(Boolean).length;
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="admin-tenants">
      <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
        {/* Header */}
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Shield className="w-6 h-6 text-indigo-600" />
              Otel & Modül Yönetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1 max-w-2xl">
              Her otelin planını seçin, modüllerini aç/kapat yapın. Plan değişikliği modülleri otomatik ayarlar.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={loadTenants} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white border rounded-lg px-4 py-3 flex items-center gap-3">
            <div className="bg-gray-100 rounded-lg p-2"><Building2 className="w-5 h-5 text-gray-600" /></div>
            <div>
              <p className="text-2xl font-bold text-gray-900">{tenants.length}</p>
              <p className="text-xs text-gray-500">Toplam Otel</p>
            </div>
          </div>
          {Object.entries(PLANS).map(([key, plan]) => {
            const Icon = plan.icon;
            return (
              <div key={key} className="bg-white border rounded-lg px-4 py-3 flex items-center gap-3 cursor-pointer hover:shadow-sm transition" onClick={() => setTierFilter(tierFilter === key ? 'all' : key)}>
                <div className={`${plan.iconBg} rounded-lg p-2`}>
                  <Icon className={`w-5 h-5 text-${plan.color}-600`} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{tierCounts[key] || 0}</p>
                  <p className="text-xs text-gray-500">{plan.label}</p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Filters */}
        <div className="flex flex-col md:flex-row gap-2 items-start md:items-center">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Otel adına göre filtrele..."
              className="w-full border rounded-lg pl-10 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="flex gap-1.5">
            <button
              className={`px-3 py-1.5 text-xs rounded-full border transition ${tierFilter === 'all' ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
              onClick={() => setTierFilter('all')}
            >Tümü ({tenants.length})</button>
            {Object.entries(PLANS).map(([key, plan]) => (
              <button
                key={key}
                className={`px-3 py-1.5 text-xs rounded-full border transition ${tierFilter === key ? 'bg-gray-900 text-white border-gray-900' : `bg-white hover:bg-gray-50 text-gray-600`}`}
                onClick={() => setTierFilter(tierFilter === key ? 'all' : key)}
              >{plan.label} ({tierCounts[key] || 0})</button>
            ))}
          </div>
        </div>

        {/* Messages */}
        {error && (
          <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm flex items-center gap-2 border border-red-200">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          </div>
        )}
        {success && (
          <div className="p-3 rounded-lg bg-green-50 text-green-700 text-sm flex items-center gap-2 border border-green-200">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> {success}
          </div>
        )}

        {/* Tenant cards */}
        {loading ? (
          <div className="text-sm text-gray-500 text-center py-12">Oteller yükleniyor...</div>
        ) : filteredTenants.length === 0 ? (
          <div className="text-sm text-gray-400 text-center py-12">Hiç otel bulunamadı</div>
        ) : (
          <div className="space-y-3">
            {filteredTenants.map((t) => {
              const id = t.id || t._id;
              const tier = t.subscription_tier || 'basic';
              const plan = PLANS[tier] || PLANS.basic;
              const isExpanded = expandedTenants[id];
              const enabledCount = countEnabledModules(t);
              const totalModules = MODULE_GROUPS.reduce((acc, g) => acc + g.items.length, 0);

              return (
                <Card key={id} className="overflow-hidden">
                  {/* Collapsed header */}
                  <div
                    className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50/50 transition"
                    onClick={() => toggleExpand(id)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`${plan.iconBg} rounded-lg p-2 flex-shrink-0`}>
                        {React.createElement(plan.icon, { className: `w-5 h-5 text-${plan.color}-600` })}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-semibold text-gray-900 truncate">{t.property_name || t.name || 'Otel'}</h3>
                          <PlanBadge tier={tier} />
                        </div>
                        <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
                          {t.location && <span>{t.location}</span>}
                          <span>{enabledCount}/{totalModules} modül aktif</span>
                          {t.subscription_end_date && (
                            <span className={new Date(t.subscription_end_date) > new Date() ? 'text-green-600' : 'text-red-600'}>
                              {new Date(t.subscription_end_date) > new Date() ? '✓ Aktif' : '⚠ Süresi dolmuş'}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-xs"
                        onClick={(e) => { e.stopPropagation(); openPlanModal(t); }}
                      >
                        Plan Değiştir
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-xs"
                        onClick={(e) => { e.stopPropagation(); openSubscriptionModal(t); }}
                      >
                        <Calendar className="w-3 h-3 mr-1" /> Süre
                      </Button>
                      {isExpanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                    </div>
                  </div>

                  {/* Expanded module management */}
                  {isExpanded && (
                    <CardContent className="pt-0 pb-4 px-4 border-t bg-gray-50/30">
                      <div className="grid gap-3 md:grid-cols-2 mt-3">
                        {MODULE_GROUPS.map((group) => {
                          const GroupIcon = group.icon;
                          return (
                            <div key={group.id} className="border rounded-lg bg-white p-3">
                              <div className="flex items-center gap-2 mb-2">
                                <GroupIcon className="w-4 h-4 text-gray-600" />
                                <div>
                                  <p className="text-sm font-semibold text-gray-800">{group.title}</p>
                                  <p className="text-[11px] text-gray-400">{group.description}</p>
                                </div>
                              </div>
                              <div className="space-y-1">
                                {group.items.map(({ key, label, hint, tier: moduleTier }) => {
                                  const enabled = t.modules?.[key] !== false && t.modules?.[key] !== undefined ? t.modules[key] : false;
                                  const includedInPlan = isModuleIncludedInPlan({ tier: moduleTier }, tier);
                                  return (
                                    <div
                                      key={key}
                                      className={`flex items-center justify-between py-1 px-2 rounded ${!includedInPlan ? 'bg-gray-50/80' : ''}`}
                                    >
                                      <TooltipProvider>
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <div className="flex items-center gap-1.5">
                                              <span className={`text-xs ${enabled ? 'text-gray-700' : 'text-gray-400'}`}>
                                                {label}
                                              </span>
                                              {!includedInPlan && (
                                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-600 border border-orange-200 font-medium">
                                                  {moduleTier === 'professional' ? 'PRO' : 'ENT'}
                                                </span>
                                              )}
                                            </div>
                                          </TooltipTrigger>
                                          <TooltipContent>
                                            <p className="max-w-xs text-xs">{hint}</p>
                                            {!includedInPlan && (
                                              <p className="text-xs text-orange-600 mt-1">
                                                Bu modül {moduleTier === 'professional' ? 'Professional' : 'Enterprise'} planında dahildir.
                                                Admin olarak manuel açabilirsiniz.
                                              </p>
                                            )}
                                          </TooltipContent>
                                        </Tooltip>
                                      </TooltipProvider>
                                      <Switch
                                        checked={!!enabled}
                                        disabled={saving}
                                        onCheckedChange={(val) => handleToggle(id, key, val)}
                                      />
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* Footer info */}
                      <div className="mt-3 flex items-center justify-between text-[11px] text-gray-400">
                        <span>
                          Tenant ID: {id?.substring(0, 8)}...
                          {t.email && <> • {t.email}</>}
                        </span>
                        <Link to="/pms" className="text-blue-500 hover:underline">
                          Bu otel gibi gör →
                        </Link>
                      </div>
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* ─── Plan Change Modal ─────────────────────────── */}
      <Dialog open={showPlanModal} onOpenChange={setShowPlanModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-indigo-600" />
              Plan Değiştir
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-600">
                Otel: <strong>{planChangeTenant?.property_name}</strong>
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                Mevcut plan: <PlanBadge tier={planChangeTenant?.subscription_tier || 'basic'} />
              </p>
            </div>

            {/* Plan selection cards */}
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(PLANS).map(([key, plan]) => {
                const Icon = plan.icon;
                const isSelected = selectedNewPlan === key;
                return (
                  <button
                    key={key}
                    className={`border-2 rounded-xl p-3 text-center transition-all ${isSelected ? `border-${plan.color}-500 bg-${plan.color}-50 ring-2 ring-${plan.color}-200` : 'border-gray-200 hover:border-gray-300 bg-white'}`}
                    onClick={() => setSelectedNewPlan(key)}
                    style={isSelected ? { borderColor: key === 'basic' ? '#10b981' : key === 'professional' ? '#3b82f6' : '#8b5cf6', backgroundColor: key === 'basic' ? '#ecfdf5' : key === 'professional' ? '#eff6ff' : '#f5f3ff' } : {}}
                  >
                    <Icon className={`w-6 h-6 mx-auto mb-1 ${isSelected ? (key === 'basic' ? 'text-emerald-600' : key === 'professional' ? 'text-blue-600' : 'text-purple-600') : 'text-gray-400'}`} />
                    <p className={`text-sm font-bold ${isSelected ? 'text-gray-900' : 'text-gray-600'}`}>{plan.label}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">{plan.description}</p>
                    <p className={`text-xs font-semibold mt-1 ${isSelected ? (key === 'basic' ? 'text-emerald-600' : key === 'professional' ? 'text-blue-600' : 'text-purple-600') : 'text-gray-400'}`}>{plan.price}</p>
                  </button>
                );
              })}
            </div>

            {/* Reset modules option */}
            <div className="flex items-center gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <input
                type="checkbox"
                id="reset_modules"
                checked={resetModulesOnPlanChange}
                onChange={(e) => setResetModulesOnPlanChange(e.target.checked)}
                className="w-4 h-4 rounded border-amber-300 text-amber-600 focus:ring-amber-500"
              />
              <label htmlFor="reset_modules" className="text-sm text-amber-800">
                <strong>Modülleri sıfırla</strong>
                <span className="block text-xs text-amber-600">
                  Yeni planın varsayılan modüllerini uygular. Kapatırsanız mevcut modüller korunur.
                </span>
              </label>
            </div>

            {error && (
              <div className="p-3 rounded-md bg-red-50 text-red-700 text-sm">{error}</div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowPlanModal(false)} disabled={saving}>
                İptal
              </Button>
              <Button onClick={handlePlanChange} disabled={saving}>
                {saving ? 'Güncelleniyor...' : 'Planı Güncelle'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* ─── Subscription Date Modal ──────────────────────── */}
      <Dialog open={showSubscriptionModal} onOpenChange={setShowSubscriptionModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Üyelik Süresini Güncelle</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-600 mb-2">
                Otel: <strong>{selectedTenant?.property_name}</strong>
              </p>
              <p className="text-xs text-gray-500">
                Mevcut Bitiş: {selectedTenant?.subscription_end_date
                  ? new Date(selectedTenant.subscription_end_date).toLocaleDateString('tr-TR')
                  : 'Sınırsız'}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="subscription_duration">Üyelik Süresi</Label>
              <select
                id="subscription_duration"
                value={subscriptionDays || ''}
                onChange={(e) => {
                  const days = e.target.value ? parseInt(e.target.value) : null;
                  setSubscriptionDays(days);
                  const start = new Date();
                  setSubscriptionStartDate(formatDateInput(start));
                  if (days) {
                    const end = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
                    setSubscriptionEndDate(formatDateInput(end));
                  } else {
                    setSubscriptionEndDate('');
                  }
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="30">30 Gün (1 Ay) - Trial</option>
                <option value="60">60 Gün (2 Ay)</option>
                <option value="90">90 Gün (3 Ay)</option>
                <option value="180">180 Gün (6 Ay)</option>
                <option value="365">365 Gün (1 Yıl)</option>
                <option value="">Sınırsız (Lifetime)</option>
              </select>

              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="space-y-1">
                  <Label>Başlangıç Tarihi</Label>
                  <input
                    type="date"
                    value={subscriptionStartDate}
                    onChange={(e) => setSubscriptionStartDate(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    disabled={saving}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Bitiş Tarihi</Label>
                  <input
                    type="date"
                    value={subscriptionEndDate}
                    onChange={(e) => setSubscriptionEndDate(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    disabled={saving}
                  />
                  <p className="text-[11px] text-gray-400">Boş = Sınırsız</p>
                </div>
              </div>
            </div>

            {error && (
              <div className="p-3 rounded-md bg-red-50 text-red-700 text-sm">{error}</div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowSubscriptionModal(false)} disabled={saving}>
                İptal
              </Button>
              <Button onClick={handleUpdateSubscription} disabled={saving}>
                {saving ? 'Güncelleniyor...' : 'Üyeliği Güncelle'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default AdminTenants;
