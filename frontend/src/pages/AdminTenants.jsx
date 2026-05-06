import React, { useEffect, useState, useMemo } from 'react';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import {
  Calendar, Building2, ChevronDown, ChevronUp, Shield,
  Search, RefreshCw, AlertTriangle, CheckCircle2,
  Plus, Pencil, Users, UsersRound, ArrowUpDown,
} from 'lucide-react';

import { PLANS, MODULE_GROUPS, isModuleIncludedInPlan } from './admin/tenantConstants';
import CreateTenantModal from './admin/CreateTenantModal';
import EditTenantModal from './admin/EditTenantModal';
import TeamManagementModal from './admin/TeamManagementModal';
import AllUsersView from './admin/AllUsersView';
import TenantStatsPanel from './admin/TenantStatsPanel';

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

const AdminTenants = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [tenants, setTenants] = useState([]);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
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
    setError(null);
    try {
      const res = await axios.get('/admin/tenants');
      setTenants(res.data?.tenants || []);
    } catch {
      setError('Otelleri yüklerken bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadTenants(); }, []);
  useEffect(() => {
    if (success) { const t = setTimeout(() => setSuccess(null), 3000); return () => clearTimeout(t); }
  }, [success]);

  const handleToggle = async (tenantId, moduleKey, value) => {
    setSaving(true);
    setError(null);
    try {
      const current = tenants.find((t) => (t.id || t._id) === tenantId);
      const updated = { ...(current?.modules || {}), [moduleKey]: value };
      const res = await axios.patch(`/admin/tenants/${tenantId}/modules`, { modules: updated });
      setTenants((prev) => prev.map((t) => (t.id || t._id) === tenantId ? { ...t, modules: res.data.modules } : t));
    } catch {
      setError('Modül güncellenemedi');
    } finally {
      setSaving(false);
    }
  };

  const handlePlanChange = async () => {
    if (!planChangeTenant) return;
    setSaving(true);
    setError(null);
    try {
      const res = await axios.patch(`/admin/tenants/${planChangeTenant.id}/tier`, {
        tier: selectedNewPlan, reset_modules: resetModulesOnPlanChange,
      });
      if (res.data?.success) {
        setSuccess(`${planChangeTenant.property_name} planı "${PLANS[selectedNewPlan]?.label}" olarak güncellendi`);
        setShowPlanModal(false);
        await loadTenants();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Plan güncellenemedi');
    } finally {
      setSaving(false);
    }
  };

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
      setSuccess('Üyelik süresi güncellendi');
      await loadTenants();
    } catch (err) {
      setError(err.response?.data?.detail || 'Üyelik güncellenemedi');
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
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="admin-tenants">
        <div className="p-4 md:p-6 max-w-[1600px] mx-auto">
          <AllUsersView onBack={() => setActiveView('tenants')} tenants={tenants} />
        </div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="admin-tenants">
      <div className="p-4 md:p-6 space-y-4 max-w-[1600px] mx-auto">
        {/* Header */}
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2" data-testid="admin-tenants-title">
              <Shield className="w-6 h-6 text-indigo-600" />
              Otel & Modül Yönetimi
            </h1>
            <p className="text-sm text-gray-500 mt-1">Her otelin planını seçin, modüllerini yönetin, ekip oluşturun.</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setActiveView('users')} data-testid="view-all-users-btn">
              <UsersRound className="w-4 h-4 mr-1" /> Tüm Kullanıcılar
            </Button>
            <Button size="sm" onClick={() => setShowCreateModal(true)} data-testid="create-tenant-btn">
              <Plus className="w-4 h-4 mr-1" /> Yeni Otel Ekle
            </Button>
            <Button variant="outline" size="sm" onClick={loadTenants} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Yenile
            </Button>
          </div>
        </div>

        {/* Stats */}
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
              <div key={key} className="bg-white border rounded-lg px-4 py-3 flex items-center gap-3 cursor-pointer hover:shadow-sm transition"
                onClick={() => setTierFilter(tierFilter === key ? 'all' : key)}
                data-testid={`stat-${key}`}
              >
                <div className={`${plan.iconBg} rounded-lg p-2`}><Icon className="w-5 h-5" /></div>
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
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              data-testid="tenant-search"
              type="text"
              placeholder="Otel ID, otel adı veya e-posta ile ara..."
              className="w-full border rounded-lg pl-10 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <div className="flex gap-1.5 flex-wrap">
            <button className={`px-3 py-1.5 text-xs rounded-full border transition ${tierFilter === 'all' ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 hover:bg-gray-50'}`} onClick={() => setTierFilter('all')}>Tümü ({tenants.length})</button>
            {Object.entries(PLANS).map(([key, plan]) => (
              <button key={key} className={`px-3 py-1.5 text-xs rounded-full border transition ${tierFilter === key ? 'bg-gray-900 text-white border-gray-900' : 'bg-white hover:bg-gray-50 text-gray-600'}`} onClick={() => setTierFilter(tierFilter === key ? 'all' : key)}>{plan.label} ({tierCounts[key] || 0})</button>
            ))}
          </div>
          <button className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 ml-auto" onClick={() => toggleSort('property_name')} data-testid="sort-btn">
            <ArrowUpDown className="w-3.5 h-3.5" /> Ada göre {sortDir === 'asc' ? 'A-Z' : 'Z-A'}
          </button>
        </div>

        {/* Messages */}
        {error && (
          <div className="p-3 rounded-lg bg-red-50 text-red-700 text-sm flex items-center gap-2 border border-red-200" data-testid="error-msg">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          </div>
        )}
        {success && (
          <div className="p-3 rounded-lg bg-green-50 text-green-700 text-sm flex items-center gap-2 border border-green-200" data-testid="success-msg">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> {success}
          </div>
        )}

        {/* Tenant list */}
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
              const isExp = expandedTenants[id];
              const enabled = countEnabled(t);

              return (
                <Card key={id} className="overflow-hidden" data-testid={`tenant-card-${id}`}>
                  <div className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50/50 transition"
                    onClick={() => setExpandedTenants((p) => ({ ...p, [id]: !p[id] }))}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className={`${plan.iconBg} rounded-lg p-2 flex-shrink-0`}>
                        {React.createElement(plan.icon, { className: 'w-5 h-5' })}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-semibold text-gray-900 truncate">{t.property_name || t.name || 'Otel'}</h3>
                          <PlanBadge tier={tier} />
                          {t.hotel_id && (
                            <span className="inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200">
                              ID: {t.hotel_id}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
                          {t.location && <span>{t.location}</span>}
                          <span>{enabled}/{totalModules} modül</span>
                          {t.subscription_end_date && (
                            <span className={new Date(t.subscription_end_date) > new Date() ? 'text-green-600' : 'text-red-600'}>
                              {new Date(t.subscription_end_date) > new Date() ? 'Aktif' : 'Süresi dolmuş'}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Button variant="ghost" size="sm" className="text-xs h-8 px-2" onClick={(e) => { e.stopPropagation(); setTeamTenant(t); setShowTeamModal(true); }} data-testid={`team-btn-${id}`}>
                        <Users className="w-3.5 h-3.5 mr-1" /> Ekip
                      </Button>
                      <Button variant="ghost" size="sm" className="text-xs h-8 px-2" onClick={(e) => { e.stopPropagation(); setEditTenant(t); setShowEditModal(true); }} data-testid={`edit-btn-${id}`}>
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button variant="outline" size="sm" className="text-xs h-8" onClick={(e) => { e.stopPropagation(); openPlanModal(t); }}>Plan</Button>
                      <Button variant="outline" size="sm" className="text-xs h-8" onClick={(e) => { e.stopPropagation(); openSubscriptionModal(t); }}>
                        <Calendar className="w-3 h-3 mr-1" /> Süre
                      </Button>
                      {isExp ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                    </div>
                  </div>

                  {isExp && (
                    <CardContent className="pt-0 pb-4 px-4 border-t bg-gray-50/30">
                      {/* Stats */}
                      <TenantStatsPanel tenantId={id} />

                      {/* Modules */}
                      <div className="grid gap-3 md:grid-cols-2 mt-3">
                        {MODULE_GROUPS.map((group) => {
                          const GroupIcon = group.icon;
                          return (
                            <div key={group.id} className="border rounded-lg bg-white p-3">
                              <div className="flex items-center gap-2 mb-2">
                                <GroupIcon className="w-4 h-4 text-gray-600" />
                                <p className="text-sm font-semibold text-gray-800">{group.title}</p>
                              </div>
                              <div className="space-y-1">
                                {group.items.map(({ key, label, hint, tier: modTier }) => {
                                  const on = !!t.modules?.[key];
                                  const included = isModuleIncludedInPlan({ tier: modTier }, tier);
                                  return (
                                    <div key={key} className={`flex items-center justify-between py-1 px-2 rounded ${!included ? 'bg-gray-50/80' : ''}`}>
                                      <TooltipProvider>
                                        <Tooltip>
                                          <TooltipTrigger asChild>
                                            <div className="flex items-center gap-1.5">
                                              <span className={`text-xs ${on ? 'text-gray-700' : 'text-gray-400'}`}>{label}</span>
                                              {!included && (
                                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-600 border border-amber-200 font-medium">
                                                  {modTier === 'mini' ? 'MINI' : modTier === 'basic' ? 'BASIC' : modTier === 'professional' ? 'PRO' : 'ENT'}
                                                </span>
                                              )}
                                            </div>
                                          </TooltipTrigger>
                                          <TooltipContent><p className="max-w-xs text-xs">{hint}</p></TooltipContent>
                                        </Tooltip>
                                      </TooltipProvider>
                                      <Switch checked={on} disabled={saving} onCheckedChange={(val) => handleToggle(id, key, val)} />
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      <div className="mt-3 flex items-center justify-between text-[11px] text-gray-400">
                        <span>ID: {id?.substring(0, 8)}... {t.email && <> &bull; {t.email}</>}</span>
                      </div>
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Modals */}
      <CreateTenantModal open={showCreateModal} onOpenChange={setShowCreateModal} onSuccess={() => { setSuccess('Yeni otel oluşturuldu'); loadTenants(); }} />
      <EditTenantModal open={showEditModal} onOpenChange={setShowEditModal} tenant={editTenant} onSuccess={() => { setSuccess('Otel bilgileri güncellendi'); loadTenants(); }} />
      <TeamManagementModal open={showTeamModal} onOpenChange={setShowTeamModal} tenant={teamTenant} />

      {/* Plan Change Modal */}
      <Dialog open={showPlanModal} onOpenChange={setShowPlanModal}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Shield className="w-5 h-5 text-indigo-600" /> Plan Değiştir</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-600">Otel: <strong>{planChangeTenant?.property_name}</strong></p>
              <p className="text-xs text-gray-400 mt-0.5">Mevcut plan: <PlanBadge tier={planChangeTenant?.subscription_tier || 'basic'} /></p>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(PLANS).map(([key, plan]) => {
                const Icon = plan.icon;
                const sel = selectedNewPlan === key;
                return (
                  <button key={key} className={`border-2 rounded-xl p-3 text-center transition-all ${sel ? 'ring-2' : 'border-gray-200 hover:border-gray-300 bg-white'}`}
                    style={sel ? { borderColor: key === 'basic' ? '#10b981' : key === 'professional' ? '#3b82f6' : '#8b5cf6', backgroundColor: key === 'basic' ? '#ecfdf5' : key === 'professional' ? '#eff6ff' : '#f5f3ff' } : {}}
                    onClick={() => setSelectedNewPlan(key)} data-testid={`plan-opt-${key}`}
                  >
                    <Icon className={`w-6 h-6 mx-auto mb-1 ${sel ? '' : 'text-gray-400'}`} />
                    <p className="text-sm font-bold">{plan.label}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5">{plan.description}</p>
                    <p className="text-xs font-semibold mt-1">{plan.price}</p>
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <input type="checkbox" id="reset_modules" checked={resetModulesOnPlanChange} onChange={(e) => setResetModulesOnPlanChange(e.target.checked)} className="w-4 h-4 rounded" />
              <label htmlFor="reset_modules" className="text-sm text-amber-800"><strong>Modülleri sıfırla</strong><span className="block text-xs text-amber-600">Yeni planın varsayılan modüllerini uygular.</span></label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowPlanModal(false)} disabled={saving}>İptal</Button>
              <Button onClick={handlePlanChange} disabled={saving} data-testid="plan-submit">{saving ? 'Güncelleniyor...' : 'Planı Güncelle'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Subscription Modal */}
      <Dialog open={showSubscriptionModal} onOpenChange={setShowSubscriptionModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Üyelik Süresini Güncelle</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-600 mb-1">Otel: <strong>{selectedTenant?.property_name}</strong></p>
              <p className="text-xs text-gray-500">Mevcut Bitiş: {selectedTenant?.subscription_end_date ? new Date(selectedTenant.subscription_end_date).toLocaleDateString('tr-TR') : 'Sınırsız'}</p>
            </div>
            <div className="space-y-2">
              <Label>Üyelik Süresi</Label>
              <select value={subscriptionDays || ''} onChange={(e) => {
                const days = e.target.value ? parseInt(e.target.value) : null;
                setSubscriptionDays(days);
                setSubscriptionStartDate(fmtDate(new Date()));
                setSubscriptionEndDate(days ? fmtDate(new Date(Date.now() + days * 86400000)) : '');
              }} className="w-full px-3 py-2 border rounded-md text-sm" data-testid="subscription-days">
                <option value="30">30 Gün</option><option value="60">60 Gün</option>
                <option value="90">90 Gün</option><option value="180">180 Gün</option>
                <option value="365">1 Yıl</option><option value="">Sınırsız</option>
              </select>
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div><Label className="text-xs">Başlangıç</Label><input type="date" value={subscriptionStartDate} onChange={(e) => setSubscriptionStartDate(e.target.value)} className="w-full px-3 py-2 border rounded-md text-sm" disabled={saving} /></div>
                <div><Label className="text-xs">Bitiş</Label><input type="date" value={subscriptionEndDate} onChange={(e) => setSubscriptionEndDate(e.target.value)} className="w-full px-3 py-2 border rounded-md text-sm" disabled={saving} /><p className="text-[11px] text-gray-400">Boş = Sınırsız</p></div>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowSubscriptionModal(false)} disabled={saving}>İptal</Button>
              <Button onClick={handleUpdateSubscription} disabled={saving} data-testid="subscription-submit">{saving ? 'Güncelleniyor...' : 'Güncelle'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Layout>
  );
};

export default AdminTenants;
