import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Calendar, Building2, ChevronDown, ChevronUp, Shield,
  Search, RefreshCw,
  Plus, Pencil, Users, UsersRound, ArrowUpDown,
} from 'lucide-react';

import { PLANS, MODULE_GROUPS, isModuleIncludedInPlan } from './admin/tenantConstants';
import CreateTenantModal from './admin/CreateTenantModal';
import EditTenantModal from './admin/EditTenantModal';
import TeamManagementModal from './admin/TeamManagementModal';
import AllUsersView from './admin/AllUsersView';
import TenantStatsPanel from './admin/TenantStatsPanel';
import { useTranslation } from 'react-i18next';

// Map plan tier → shared StatusBadge intent (palette-compliant)
const TIER_INTENT = {
  mini: 'success',          // teal-ish via emerald
  basic: 'success',
  professional: 'info',     // sky
  enterprise: 'default',    // indigo via default neutral-strong
};

const PlanBadge = ({ tier }) => {
  const { t } = useTranslation();
  const plan = PLANS[tier] || PLANS.basic;
  const Icon = plan.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border font-semibold ${plan.badgeClass}`}>
      <Icon className="w-3.5 h-3.5" />
      {plan.label}
    </span>
  );
};

const AdminTenants = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tenants, setTenants] = useState([]);
  const [filter, setFilter] = useState('');
  const [tierFilter, setTierFilter] = useState('all');
  const [expandedTenants, setExpandedTenants] = useState({});
  const [sortField, setSortField] = useState('property_name');
  const [sortDir, setSortDir] = useState('asc');
  const [activeView, setActiveView] = useState('tenants'); // 'tenants' | 'users'

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editTenant, setEditTenant] = useState(null);
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [teamTenant, setTeamTenant] = useState(null);
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [subscriptionDays, setSubscriptionDays] = useState(30);
  const [subscriptionStartDate, setSubscriptionStartDate] = useState('');
  const [subscriptionEndDate, setSubscriptionEndDate] = useState('');
  const [showPlanModal, setShowPlanModal] = useState(false);
  const [planChangeTenant, setPlanChangeTenant] = useState(null);
  const [selectedNewPlan, setSelectedNewPlan] = useState('basic');
  const [resetModulesOnPlanChange, setResetModulesOnPlanChange] = useState(true);

  const loadTenants = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/tenants');
      setTenants(res.data?.tenants || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Otelleri yüklerken bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadTenants(); }, []);

  const handleToggle = async (tenantId, moduleKey, value) => {
    setSaving(true);
    try {
      const current = tenants.find((t) => (t.id || t._id) === tenantId);
      const updated = { ...(current?.modules || {}), [moduleKey]: value };
      const res = await axios.patch(`/admin/tenants/${tenantId}/modules`, { modules: updated });
      setTenants((prev) => prev.map((t) => (t.id || t._id) === tenantId ? { ...t, modules: res.data.modules } : t));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Modül güncellenemedi');
    } finally {
      setSaving(false);
    }
  };

  const handlePlanChange = async () => {
    if (!planChangeTenant) return;
    setSaving(true);
    try {
      const res = await axios.patch(`/admin/tenants/${planChangeTenant.id}/tier`, {
        tier: selectedNewPlan, reset_modules: resetModulesOnPlanChange,
      });
      if (res.data?.success) {
        toast.success(`${planChangeTenant.property_name} planı "${PLANS[selectedNewPlan]?.label}" olarak güncellendi`);
        setShowPlanModal(false);
        await loadTenants();
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Plan güncellenemedi');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateSubscription = async () => {
    if (!selectedTenant) return;
    setSaving(true);
    try {
      await axios.patch(`/admin/tenants/${selectedTenant.id}/subscription`, {
        subscription_days: subscriptionDays || null,
        subscription_start_date: subscriptionStartDate || null,
        subscription_end_date: subscriptionEndDate || null,
      });
      setShowSubscriptionModal(false);
      toast.success('Üyelik süresi güncellendi');
      await loadTenants();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Üyelik güncellenemedi');
    } finally {
      setSaving(false);
    }
  };

  const fmtDate = (d) => {
    try {
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    } catch { return ''; }
  };

  const openSubscriptionModal = (t) => {
    setSelectedTenant(t);
    setSubscriptionDays(30);
    setSubscriptionStartDate(fmtDate(new Date()));
    setSubscriptionEndDate(fmtDate(new Date(Date.now() + 30 * 86400000)));
    setShowSubscriptionModal(true);
  };

  const openPlanModal = (t) => {
    setPlanChangeTenant(t);
    setSelectedNewPlan(t.subscription_tier || 'basic');
    setResetModulesOnPlanChange(true);
    setShowPlanModal(true);
  };

  const toggleSort = (field) => {
    if (sortField === field) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortField(field); setSortDir('asc'); }
  };

  const filteredTenants = useMemo(() => {
    const q = filter.trim().toLowerCase();
    let list = tenants.filter((t) => {
      const name = (t.property_name || t.name || '').toLowerCase();
      const hotelId = String(t.hotel_id || '').toLowerCase();
      const email = String(t.email || t.contact_email || '').toLowerCase();
      const matchQuery = !q || name.includes(q) || hotelId.includes(q) || email.includes(q);
      const matchTier = tierFilter === 'all' || (t.subscription_tier || 'basic') === tierFilter;
      return matchQuery && matchTier;
    });
    list.sort((a, b) => {
      let va = a[sortField] || '';
      let vb = b[sortField] || '';
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [tenants, filter, tierFilter, sortField, sortDir]);

  const tierCounts = useMemo(() => {
    const c = { basic: 0, professional: 0, enterprise: 0 };
    tenants.forEach((t) => { const tier = t.subscription_tier || 'basic'; c[tier] = (c[tier] || 0) + 1; });
    return c;
  }, [tenants]);

  const countEnabled = (t) => Object.values(t.modules || {}).filter(Boolean).length;
  const totalModules = MODULE_GROUPS.reduce((a, g) => a + g.items.length, 0);

  if (activeView === 'users') {
    return (
      <div className="p-4 md:p-6 max-w-[1600px] mx-auto">
        <AllUsersView onBack={() => setActiveView('tenants')} tenants={tenants} />
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
      <PageHeader
        icon={Shield}
        title={t('cm.pages_AdminTenants.otel_modul_yonetimi')}
        subtitle={t('cm.pages_AdminTenants.her_otelin_planini_secin_modullerini_yon')}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setActiveView('users')} data-testid="view-all-users-btn">
              <UsersRound className="w-4 h-4 mr-1.5" aria-hidden="true" /> {t('cm.pages_AdminTenants.tum_kullanicilar')}
            </Button>
            <Button variant="outline" size="sm" onClick={loadTenants} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" /> {t('cm.pages_AdminTenants.yenile')}
            </Button>
            <Button size="sm" onClick={() => setShowCreateModal(true)} data-testid="create-tenant-btn">
              <Plus className="w-4 h-4 mr-1.5" aria-hidden="true" /> {t('cm.pages_AdminTenants.yeni_otel_ekle')}
            </Button>
          </div>
        }
      />

      {/* Stats — KPI tiles, click to filter */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiCard
          icon={Building2}
          label={t('cm.pages_AdminTenants.toplam_otel')}
          value={tenants.length}
          intent="default"
          active={tierFilter === 'all'}
          onClick={() => setTierFilter('all')}
        />
        {Object.entries(PLANS).map(([key, plan]) => (
          <KpiCard
            key={key}
            icon={plan.icon}
            label={plan.label}
            value={tierCounts[key] || 0}
            intent={TIER_INTENT[key] || 'default'}
            active={tierFilter === key}
            onClick={() => setTierFilter(tierFilter === key ? 'all' : key)}
            data-testid={`stat-${key}`}
          />
        ))}
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-3 flex flex-col md:flex-row gap-2 items-start md:items-center">
          <div className="relative flex-1 max-w-sm w-full">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
            <Input
              data-testid="tenant-search"
              type="text"
              placeholder={t('cm.pages_AdminTenants.otel_id_otel_adi_veya_e_posta_ile_ara')}
              className="pl-9"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Otel arama"
            />
          </div>
          <div className="text-xs text-slate-500">
            {filteredTenants.length} {t('cm.pages_AdminTenants.sonuc')}
            {tierFilter !== 'all' && (
              <> · <button className="underline hover:text-slate-700" onClick={() => setTierFilter('all')}>filtreyi temizle</button></>
            )}
          </div>
          <Button variant="ghost" size="sm" className="ml-auto text-xs" onClick={() => toggleSort('property_name')} data-testid="sort-btn">
            <ArrowUpDown className="w-3.5 h-3.5 mr-1" aria-hidden="true" /> {t('cm.pages_AdminTenants.ada_gore')} {sortDir === 'asc' ? 'A-Z' : 'Z-A'}
          </Button>
        </CardContent>
      </Card>

      {/* Tenant list */}
      {loading ? (
        <div className="text-sm text-slate-500 text-center py-12">{t('cm.pages_AdminTenants.oteller_yukleniyor')}</div>
      ) : filteredTenants.length === 0 ? (
        <div className="text-sm text-slate-400 text-center py-12">{t('cm.pages_AdminTenants.hic_otel_bulunamadi')}</div>
      ) : (
        <div className="space-y-3">
          {filteredTenants.map((t) => {
            const id = t.id || t._id;
            const tier = t.subscription_tier || 'basic';
            const plan = PLANS[tier] || PLANS.basic;
            const isExp = expandedTenants[id];
            const enabled = countEnabled(t);
            const subActive = t.subscription_end_date ? new Date(t.subscription_end_date) > new Date() : null;

            return (
              <Card key={id} className="overflow-hidden" data-testid={`tenant-card-${id}`}>
                <div
                  role="button"
                  tabIndex={0}
                  aria-expanded={!!isExp}
                  aria-label={`${t.property_name || t.name || 'Otel'} ${isExp ? 'gizle' : 'göster'}`}
                  className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-slate-50/50 transition focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-1"
                  onClick={() => setExpandedTenants((p) => ({ ...p, [id]: !p[id] }))}
                  onKeyDown={(e) => {
                    if (e.target !== e.currentTarget) return;
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setExpandedTenants((p) => ({ ...p, [id]: !p[id] }));
                    }
                  }}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`${plan.iconBg} rounded-lg p-2 flex-shrink-0`}>
                      {React.createElement(plan.icon, { className: 'w-5 h-5', 'aria-hidden': true })}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-slate-900 truncate">{t.property_name || t.name || 'Otel'}</h3>
                        <PlanBadge tier={tier} />
                        {t.hotel_id && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200">
                            ID: {t.hotel_id}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-slate-500 mt-0.5">
                        {t.location && <span>{t.location}</span>}
                        <span>{enabled}/{totalModules} {t('cm.pages_AdminTenants.modul')}</span>
                        {subActive !== null && (
                          <StatusBadge intent={subActive ? 'success' : 'danger'}>
                            {subActive ? 'Aktif' : 'Süresi dolmuş'}
                          </StatusBadge>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button variant="ghost" size="sm" className="text-xs h-8 px-2" onClick={(e) => { e.stopPropagation(); setTeamTenant(t); setShowTeamModal(true); }} data-testid={`team-btn-${id}`}>
                      <Users className="w-3.5 h-3.5 mr-1" aria-hidden="true" /> Ekip
                    </Button>
                    <Button variant="ghost" size="sm" className="text-xs h-8 px-2" onClick={(e) => { e.stopPropagation(); setEditTenant(t); setShowEditModal(true); }} data-testid={`edit-btn-${id}`} aria-label={t('cm.pages_AdminTenants.duzenle')}>
                      <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
                    </Button>
                    <Button variant="outline" size="sm" className="text-xs h-8" onClick={(e) => { e.stopPropagation(); openPlanModal(t); }}>Plan</Button>
                    <Button variant="outline" size="sm" className="text-xs h-8" onClick={(e) => { e.stopPropagation(); openSubscriptionModal(t); }}>
                      <Calendar className="w-3 h-3 mr-1" aria-hidden="true" /> {t('cm.pages_AdminTenants.sure')}
                    </Button>
                    {isExp ? <ChevronUp className="w-5 h-5 text-slate-400" aria-hidden="true" /> : <ChevronDown className="w-5 h-5 text-slate-400" aria-hidden="true" />}
                  </div>
                </div>

                {isExp && (
                  <CardContent className="pt-0 pb-4 px-4 border-t bg-slate-50/30">
                    <TenantStatsPanel tenantId={id} />

                    <div className="grid gap-3 md:grid-cols-2 mt-3">
                      {MODULE_GROUPS.map((group) => {
                        const GroupIcon = group.icon;
                        return (
                          <div key={group.id} className="border rounded-lg bg-white p-3">
                            <div className="flex items-center gap-2 mb-2">
                              <GroupIcon className="w-4 h-4 text-slate-600" aria-hidden="true" />
                              <p className="text-sm font-semibold text-slate-800">{group.title}</p>
                            </div>
                            <div className="space-y-1">
                              {group.items.map(({ key, label, hint, tier: modTier }) => {
                                const on = !!t.modules?.[key];
                                const included = isModuleIncludedInPlan({ tier: modTier }, tier);
                                return (
                                  <div key={key} className={`flex items-center justify-between py-1 px-2 rounded ${!included ? 'bg-slate-50/80' : ''}`}>
                                    <TooltipProvider>
                                      <Tooltip>
                                        <TooltipTrigger asChild>
                                          <div className="flex items-center gap-1.5">
                                            <span className={`text-xs ${on ? 'text-slate-700' : 'text-slate-400'}`}>{label}</span>
                                            {!included && (
                                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200 font-medium">
                                                {modTier === 'mini' ? 'MINI' : modTier === 'basic' ? 'BASIC' : modTier === 'professional' ? 'PRO' : 'ENT'}
                                              </span>
                                            )}
                                          </div>
                                        </TooltipTrigger>
                                        <TooltipContent><p className="max-w-xs text-xs">{hint}</p></TooltipContent>
                                      </Tooltip>
                                    </TooltipProvider>
                                    <Switch checked={on} disabled={saving} onCheckedChange={(val) => handleToggle(id, key, val)} aria-label={label} />
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div className="mt-3 flex items-center justify-between text-[11px] text-slate-400">
                      <span>ID: {id?.substring(0, 8)}... {t.email && <> &bull; {t.email}</>}</span>
                    </div>
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Modals */}
      <CreateTenantModal open={showCreateModal} onOpenChange={setShowCreateModal} onSuccess={() => { toast.success('Yeni otel oluşturuldu'); loadTenants(); }} />
      <EditTenantModal open={showEditModal} onOpenChange={setShowEditModal} tenant={editTenant} onSuccess={() => { toast.success('Otel bilgileri güncellendi'); loadTenants(); }} />
      <TeamManagementModal open={showTeamModal} onOpenChange={setShowTeamModal} tenant={teamTenant} />

      {/* Plan Change Modal */}
      <Dialog open={showPlanModal} onOpenChange={setShowPlanModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Shield className="w-5 h-5 text-indigo-600" aria-hidden="true" /> {t('cm.pages_AdminTenants.plan_degistir')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-slate-600">Otel: <strong>{planChangeTenant?.property_name}</strong></p>
              <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">Mevcut plan: <PlanBadge tier={planChangeTenant?.subscription_tier || 'basic'} /></div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {Object.entries(PLANS).map(([key, plan]) => {
                const Icon = plan.icon;
                const sel = selectedNewPlan === key;
                const selRing = {
                  mini:         'border-teal-500 bg-teal-50 ring-2 ring-teal-200',
                  basic:        'border-emerald-500 bg-emerald-50 ring-2 ring-emerald-200',
                  professional: 'border-sky-500 bg-sky-50 ring-2 ring-sky-200',
                  enterprise:   'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-200',
                }[key] || 'border-slate-400 bg-slate-50 ring-2 ring-slate-200';
                return (
                  <button
                    key={key}
                    type="button"
                    className={`border-2 rounded-xl p-3 text-center transition-all ${sel ? selRing : 'border-slate-200 hover:border-slate-300 bg-white'}`}
                    onClick={() => setSelectedNewPlan(key)}
                    data-testid={`plan-opt-${key}`}
                    aria-pressed={sel}
                  >
                    <Icon className={`w-6 h-6 mx-auto mb-1 ${sel ? '' : 'text-slate-400'}`} aria-hidden="true" />
                    <p className="text-sm font-bold">{plan.label}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">{plan.description}</p>
                    <p className="text-xs font-semibold mt-1">{plan.price}</p>
                  </button>
                );
              })}
            </div>
            <label htmlFor="reset_modules" className="flex items-center gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg cursor-pointer">
              <input type="checkbox" id="reset_modules" checked={resetModulesOnPlanChange} onChange={(e) => setResetModulesOnPlanChange(e.target.checked)} className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500" />
              <span className="text-sm text-amber-800"><strong>{t('cm.pages_AdminTenants.modulleri_sifirla')}</strong><span className="block text-xs text-amber-700">{t('cm.pages_AdminTenants.yeni_planin_varsayilan_modullerini_uygul')}</span></span>
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowPlanModal(false)} disabled={saving}>{t('cm.pages_AdminTenants.iptal')}</Button>
              <Button onClick={handlePlanChange} disabled={saving} data-testid="plan-submit">{saving ? 'Güncelleniyor...' : 'Planı Güncelle'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Subscription Modal */}
      <Dialog open={showSubscriptionModal} onOpenChange={setShowSubscriptionModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('cm.pages_AdminTenants.uyelik_suresini_guncelle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-slate-600 mb-1">Otel: <strong>{selectedTenant?.property_name}</strong></p>
              <p className="text-xs text-slate-500">{t('cm.pages_AdminTenants.mevcut_bitis')} {selectedTenant?.subscription_end_date ? new Date(selectedTenant.subscription_end_date).toLocaleDateString('tr-TR') : 'Sınırsız'}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="subscription-days-trigger">{t('cm.pages_AdminTenants.uyelik_suresi')}</Label>
              <Select
                value={subscriptionDays ? String(subscriptionDays) : 'unlimited'}
                onValueChange={(val) => {
                  const days = val === 'unlimited' ? null : parseInt(val);
                  setSubscriptionDays(days);
                  setSubscriptionStartDate(fmtDate(new Date()));
                  setSubscriptionEndDate(days ? fmtDate(new Date(Date.now() + days * 86400000)) : '');
                }}
              >
                <SelectTrigger id="subscription-days-trigger" data-testid="subscription-days" aria-label={t('cm.pages_AdminTenants.uyelik_suresi_secimi')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">{t('cm.pages_AdminTenants.30_gun')}</SelectItem>
                  <SelectItem value="60">{t('cm.pages_AdminTenants.60_gun')}</SelectItem>
                  <SelectItem value="90">{t('cm.pages_AdminTenants.90_gun')}</SelectItem>
                  <SelectItem value="180">{t('cm.pages_AdminTenants.180_gun')}</SelectItem>
                  <SelectItem value="365">{t('cm.pages_AdminTenants.1_yil')}</SelectItem>
                  <SelectItem value="unlimited">{t('cm.pages_AdminTenants.sinirsiz')}</SelectItem>
                </SelectContent>
              </Select>
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div><Label className="text-xs">{t('cm.pages_AdminTenants.baslangic')}</Label><Input type="date" value={subscriptionStartDate} onChange={(e) => setSubscriptionStartDate(e.target.value)} disabled={saving} /></div>
                <div><Label className="text-xs">{t('cm.pages_AdminTenants.bitis')}</Label><Input type="date" value={subscriptionEndDate} onChange={(e) => setSubscriptionEndDate(e.target.value)} disabled={saving} /><p className="text-[11px] text-slate-400">{t('cm.pages_AdminTenants.bos_sinirsiz')}</p></div>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowSubscriptionModal(false)} disabled={saving}>{t('cm.pages_AdminTenants.iptal_25174')}</Button>
              <Button onClick={handleUpdateSubscription} disabled={saving} data-testid="subscription-submit">{saving ? 'Güncelleniyor...' : 'Güncelle'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminTenants;
