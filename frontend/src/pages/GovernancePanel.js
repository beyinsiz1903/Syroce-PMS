import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Shield, Activity, Flag, BarChart3, RefreshCw,
  Plus, Trash2, Settings2, ChevronRight, AlertTriangle,
  CheckCircle2, XCircle, Gauge, Users, Building2, Zap,
} from 'lucide-react';

/* ================================================================
   TAB 1 — Entitlements Overview
   ================================================================ */
const EntitlementsTab = () => {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenantDetail, setTenantDetail] = useState(null);
  const [tenants, setTenants] = useState([]);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, tRes] = await Promise.all([
        axios.get('/admin/entitlements/overview'),
        axios.get('/admin/tenants'),
      ]);
      setOverview(ovRes.data);
      setTenants(tRes.data?.tenants || []);
    } catch { /* skip */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const loadTenantDetail = async (tenantId) => {
    setSelectedTenant(tenantId);
    try {
      const res = await axios.get(`/admin/tenants/${tenantId}/entitlements`);
      setTenantDetail(res.data);
    } catch { setTenantDetail(null); }
  };

  if (loading) return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-6" data-testid="entitlements-tab">
      {/* Summary Cards */}
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card><CardContent className="pt-4">
            <div className="flex items-center gap-3">
              <div className="bg-indigo-50 rounded-lg p-2"><Building2 className="w-5 h-5 text-indigo-600" /></div>
              <div><p className="text-2xl font-bold">{overview.total_tenants}</p><p className="text-xs text-slate-500">Toplam Tenant</p></div>
            </div>
          </CardContent></Card>
          {Object.entries(overview.by_tier || {}).map(([tier, count]) => (
            <Card key={tier}><CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className={`rounded-lg p-2 ${tier === 'enterprise' ? 'bg-amber-50' : tier === 'professional' ? 'bg-blue-50' : 'bg-slate-50'}`}>
                  <Shield className={`w-5 h-5 ${tier === 'enterprise' ? 'text-amber-600' : tier === 'professional' ? 'text-blue-600' : 'text-slate-600'}`} />
                </div>
                <div><p className="text-2xl font-bold">{count}</p><p className="text-xs text-slate-500 capitalize">{tier}</p></div>
              </div>
            </CardContent></Card>
          ))}
          {overview.expired_count > 0 && (
            <Card className="border-red-200"><CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="bg-red-50 rounded-lg p-2"><AlertTriangle className="w-5 h-5 text-red-600" /></div>
                <div><p className="text-2xl font-bold text-red-600">{overview.expired_count}</p><p className="text-xs text-slate-500">Suresi Dolan</p></div>
              </div>
            </CardContent></Card>
          )}
        </div>
      )}

      {/* Tenant List with Entitlement Drill-down */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Shield className="w-4 h-4" /> Tenant Entitlement Detay</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="divide-y">
            {tenants.slice(0, 20).map((t) => (
              <div key={t.id} className="flex items-center justify-between py-3 hover:bg-slate-50 px-2 rounded cursor-pointer"
                   onClick={() => loadTenantDetail(t.id)} data-testid={`tenant-row-${t.id}`}>
                <div className="flex items-center gap-3">
                  <Building2 className="w-4 h-4 text-slate-400" />
                  <div>
                    <p className="text-sm font-medium">{t.property_name}</p>
                    <p className="text-xs text-slate-400">{t.subscription_tier || 'basic'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-xs">{Object.values(t.modules || {}).filter(Boolean).length} modul</Badge>
                  <ChevronRight className="w-4 h-4 text-slate-300" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Detail Panel */}
      <Dialog open={!!selectedTenant} onOpenChange={() => setSelectedTenant(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Entitlement Detay</DialogTitle></DialogHeader>
          {tenantDetail ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold">{tenantDetail.property_name}</p>
                  <p className="text-sm text-slate-500 capitalize">{tenantDetail.tier} plan</p>
                </div>
                <Badge className={tenantDetail.is_expired ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}>
                  {tenantDetail.subscription_status}
                </Badge>
              </div>

              {/* Quotas */}
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(tenantDetail.quotas || {}).map(([key, q]) => (
                  <div key={key} className="border rounded-lg p-3">
                    <p className="text-xs text-slate-500 capitalize">{key}</p>
                    <p className="text-lg font-bold">{q.current} <span className="text-sm font-normal text-slate-400">/ {q.limit || '∞'}</span></p>
                    {!q.allowed && <p className="text-xs text-red-500 mt-1">Limit asildi!</p>}
                  </div>
                ))}
              </div>

              {/* Modules */}
              <div>
                <p className="text-sm font-medium mb-2">Aktif Moduller</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(tenantDetail.modules || {}).filter(([, v]) => v).map(([k]) => (
                    <Badge key={k} variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">{k}</Badge>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium mb-2">Kapali Moduller</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(tenantDetail.modules || {}).filter(([, v]) => !v).map(([k]) => (
                    <Badge key={k} variant="outline" className="text-xs bg-slate-50 text-slate-400">{k}</Badge>
                  ))}
                </div>
              </div>
            </div>
          ) : <p className="text-sm text-slate-400">Yukleniyor...</p>}
        </DialogContent>
      </Dialog>
    </div>
  );
};

/* ================================================================
   TAB 2 — Usage Metering
   ================================================================ */
const MeteringTab = () => {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenantUsage, setTenantUsage] = useState(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/usage/overview');
      setOverview(res.data);
    } catch { /* skip */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const loadTenantUsage = async (tenantId) => {
    setSelectedTenant(tenantId);
    try {
      const res = await axios.get(`/admin/tenants/${tenantId}/usage?days=30`);
      setTenantUsage(res.data);
    } catch { setTenantUsage(null); }
  };

  if (loading) return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;

  const EVENT_LABELS = {
    api_call: 'API Cagrisi',
    reservation_created: 'Rezervasyon',
    login: 'Giris',
    guest_created: 'Misafir',
    channel_sync: 'Kanal Sync',
    report_generated: 'Rapor',
    invoice_created: 'Fatura',
    ai_request: 'AI Istek',
    webhook_received: 'Webhook',
  };

  return (
    <div className="space-y-6" data-testid="metering-tab">
      {/* Today + This Month Summary */}
      {overview && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-500">Bugun</CardTitle></CardHeader>
              <CardContent>
                {Object.keys(overview.today || {}).length === 0 ? (
                  <p className="text-sm text-slate-400">Henuz veri yok</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(overview.today).map(([event, count]) => (
                      <div key={event} className="flex justify-between items-center">
                        <span className="text-sm">{EVENT_LABELS[event] || event}</span>
                        <span className="text-sm font-mono font-bold">{count.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-500">Bu Ay</CardTitle></CardHeader>
              <CardContent>
                {Object.keys(overview.this_month || {}).length === 0 ? (
                  <p className="text-sm text-slate-400">Henuz veri yok</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(overview.this_month).map(([event, count]) => (
                      <div key={event} className="flex justify-between items-center">
                        <span className="text-sm">{EVENT_LABELS[event] || event}</span>
                        <span className="text-sm font-mono font-bold">{count.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Active Tenants */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Card><CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="bg-green-50 rounded-lg p-2"><Activity className="w-5 h-5 text-green-600" /></div>
                <div><p className="text-2xl font-bold">{overview.active_tenants_7d}</p><p className="text-xs text-slate-500">Aktif Tenant (7 gun)</p></div>
              </div>
            </CardContent></Card>
          </div>

          {/* Top Tenants */}
          {overview.top_tenants?.length > 0 && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><BarChart3 className="w-4 h-4" /> En Aktif Tenantlar (Bu Ay)</CardTitle></CardHeader>
              <CardContent>
                <div className="divide-y">
                  {overview.top_tenants.map((t, i) => (
                    <div key={t.tenant_id} className="flex items-center justify-between py-2 px-1 hover:bg-slate-50 rounded cursor-pointer"
                         onClick={() => loadTenantUsage(t.tenant_id)} data-testid={`top-tenant-${i}`}>
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono text-slate-400 w-5">#{i + 1}</span>
                        <div>
                          <p className="text-sm font-medium">{t.property_name}</p>
                          <p className="text-xs text-slate-400 capitalize">{t.tier}</p>
                        </div>
                      </div>
                      <span className="text-sm font-mono font-bold">{t.total_events.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Tenant Usage Detail */}
      <Dialog open={!!selectedTenant} onOpenChange={() => setSelectedTenant(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Tenant Kullanim (30 gun)</DialogTitle></DialogHeader>
          {tenantUsage ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(tenantUsage.current_resources || {}).map(([k, v]) => (
                  <div key={k} className="border rounded-lg p-3 text-center">
                    <p className="text-xs text-slate-500 capitalize">{k}</p>
                    <p className="text-lg font-bold">{v}</p>
                  </div>
                ))}
              </div>
              <div>
                <p className="text-sm font-medium mb-2">Olaylar (Son 30 Gun)</p>
                {Object.keys(tenantUsage.events || {}).length === 0 ? (
                  <p className="text-sm text-slate-400">Veri yok</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(tenantUsage.events).map(([event, count]) => (
                      <div key={event} className="flex justify-between items-center border-b pb-1">
                        <span className="text-sm">{EVENT_LABELS[event] || event}</span>
                        <span className="text-sm font-mono font-bold">{count.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : <p className="text-sm text-slate-400">Yukleniyor...</p>}
        </DialogContent>
      </Dialog>
    </div>
  );
};

/* ================================================================
   TAB 3 — Feature Flags
   ================================================================ */
const FeatureFlagsTab = () => {
  const [flags, setFlags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ flag_key: '', enabled: false, description: '', rollout_percentage: '', kill_switch: false, expires_at: '' });
  const [saving, setSaving] = useState(false);

  const loadFlags = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/feature-flags');
      setFlags(res.data?.flags || []);
    } catch { /* skip */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadFlags(); }, [loadFlags]);

  const handleSave = async () => {
    if (!form.flag_key) return;
    setSaving(true);
    try {
      const payload = {
        flag_key: form.flag_key,
        enabled: form.enabled,
        description: form.description,
        kill_switch: form.kill_switch,
      };
      if (form.rollout_percentage !== '' && form.rollout_percentage !== null) {
        payload.rollout_percentage = parseInt(form.rollout_percentage, 10);
      }
      if (form.expires_at) payload.expires_at = form.expires_at;
      await axios.post('/admin/feature-flags', payload);
      setShowCreate(false);
      setForm({ flag_key: '', enabled: false, description: '', rollout_percentage: '', kill_switch: false, expires_at: '' });
      await loadFlags();
    } catch { /* skip */ } finally { setSaving(false); }
  };

  const handleDelete = async (flagKey) => {
    if (!window.confirm(`"${flagKey}" flagini silmek istediginize emin misiniz?`)) return;
    try {
      await axios.delete(`/admin/feature-flags/${flagKey}`);
      await loadFlags();
    } catch { /* skip */ }
  };

  const toggleFlag = async (flag) => {
    try {
      await axios.post('/admin/feature-flags', { ...flag, enabled: !flag.enabled });
      await loadFlags();
    } catch { /* skip */ }
  };

  const toggleKillSwitch = async (flag) => {
    try {
      await axios.post('/admin/feature-flags', { ...flag, kill_switch: !flag.kill_switch });
      await loadFlags();
    } catch { /* skip */ }
  };

  if (loading) return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-6" data-testid="feature-flags-tab">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">{flags.length} flag tanimli</p>
        <Button size="sm" onClick={() => setShowCreate(true)} data-testid="create-flag-btn"><Plus className="w-4 h-4 mr-1" /> Yeni Flag</Button>
      </div>

      {flags.length === 0 ? (
        <Card><CardContent className="py-12 text-center">
          <Flag className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <p className="text-sm text-slate-400">Henuz feature flag tanimlanmamis</p>
          <Button size="sm" variant="outline" className="mt-3" onClick={() => setShowCreate(true)}>Ilk Flagini Olustur</Button>
        </CardContent></Card>
      ) : (
        <div className="space-y-3">
          {flags.map((flag) => (
            <Card key={flag.flag_key} className={flag.kill_switch ? 'border-red-200 bg-red-50/30' : ''} data-testid={`flag-card-${flag.flag_key}`}>
              <CardContent className="py-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="font-mono text-sm font-semibold">{flag.flag_key}</p>
                      {flag.kill_switch && <Badge variant="destructive" className="text-xs">KILL SWITCH</Badge>}
                      {flag.enabled && !flag.kill_switch && <Badge className="text-xs bg-green-100 text-green-700">Aktif</Badge>}
                      {!flag.enabled && !flag.kill_switch && <Badge variant="outline" className="text-xs">Kapali</Badge>}
                    </div>
                    {flag.description && <p className="text-xs text-slate-500 mt-1">{flag.description}</p>}
                    <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                      {flag.rollout_percentage != null && <span>Rollout: %{flag.rollout_percentage}</span>}
                      {flag.expires_at && <span>Bitis: {new Date(flag.expires_at).toLocaleDateString('tr-TR')}</span>}
                      {Object.keys(flag.tenant_overrides || {}).length > 0 && (
                        <span>{Object.keys(flag.tenant_overrides).length} tenant override</span>
                      )}
                      {flag.updated_by && <span>Son: {flag.updated_by}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <Switch checked={flag.enabled} onCheckedChange={() => toggleFlag(flag)} data-testid={`flag-toggle-${flag.flag_key}`} />
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-red-400 hover:text-red-600" onClick={() => toggleKillSwitch(flag)}
                            title={flag.kill_switch ? 'Kill switch kaldir' : 'Kill switch aktif et'}>
                      <XCircle className="w-4 h-4" />
                    </Button>
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-600" onClick={() => handleDelete(flag.flag_key)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Yeni Feature Flag</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Flag Key *</Label>
              <Input placeholder="new_booking_flow" value={form.flag_key} onChange={(e) => setForm(f => ({...f, flag_key: e.target.value}))} data-testid="flag-key-input" />
            </div>
            <div>
              <Label>Aciklama</Label>
              <Input placeholder="Bu flag ne yapar?" value={form.description} onChange={(e) => setForm(f => ({...f, description: e.target.value}))} />
            </div>
            <div className="flex items-center justify-between">
              <Label>Aktif</Label>
              <Switch checked={form.enabled} onCheckedChange={(v) => setForm(f => ({...f, enabled: v}))} />
            </div>
            <div>
              <Label>Rollout Yuzdesi (0-100, bos = tum tenantlar)</Label>
              <Input type="number" min="0" max="100" placeholder="100" value={form.rollout_percentage} onChange={(e) => setForm(f => ({...f, rollout_percentage: e.target.value}))} />
            </div>
            <div>
              <Label>Bitis Tarihi (opsiyonel)</Label>
              <Input type="datetime-local" value={form.expires_at} onChange={(e) => setForm(f => ({...f, expires_at: e.target.value}))} />
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-red-500">Kill Switch</Label>
              <Switch checked={form.kill_switch} onCheckedChange={(v) => setForm(f => ({...f, kill_switch: v}))} />
            </div>
            <Button className="w-full" onClick={handleSave} disabled={saving || !form.flag_key} data-testid="save-flag-btn">
              {saving ? 'Kaydediliyor...' : 'Kaydet'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

/* ================================================================
   TAB 4 — Onboarding Progress
   ================================================================ */
const OnboardingTab = () => {
  const [overview, setOverview] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenantProgress, setTenantProgress] = useState(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/onboarding/overview');
      setOverview(res.data?.tenants || []);
    } catch { /* skip */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview]);

  const loadTenantProgress = async (tenantId) => {
    setSelectedTenant(tenantId);
    try {
      const res = await axios.get(`/admin/tenants/${tenantId}/onboarding`);
      setTenantProgress(res.data);
    } catch { setTenantProgress(null); }
  };

  const markComplete = async (stepId) => {
    if (!selectedTenant) return;
    try {
      await axios.post(`/admin/tenants/${selectedTenant}/onboarding/${stepId}/complete`);
      await loadTenantProgress(selectedTenant);
    } catch { /* skip */ }
  };

  if (loading) return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;

  const CATEGORY_LABELS = { setup: 'Kurulum', operations: 'Operasyon', team: 'Ekip', channels: 'Kanallar', finance: 'Finans', reports: 'Raporlar' };
  const CATEGORY_COLORS = { setup: 'bg-blue-50 text-blue-700', operations: 'bg-green-50 text-green-700', team: 'bg-purple-50 text-purple-700', channels: 'bg-amber-50 text-amber-700', finance: 'bg-red-50 text-red-700', reports: 'bg-slate-50 text-slate-700' };

  return (
    <div className="space-y-6" data-testid="onboarding-tab">
      {/* Tenant Progress Overview */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base flex items-center gap-2"><Zap className="w-4 h-4" /> Onboarding Durumu</CardTitle></CardHeader>
        <CardContent>
          <div className="divide-y">
            {overview.map((t) => (
              <div key={t.tenant_id} className="flex items-center justify-between py-3 px-2 hover:bg-slate-50 rounded cursor-pointer"
                   onClick={() => loadTenantProgress(t.tenant_id)} data-testid={`onboard-row-${t.tenant_id}`}>
                <div className="flex items-center gap-3">
                  <Building2 className="w-4 h-4 text-slate-400" />
                  <div>
                    <p className="text-sm font-medium">{t.property_name}</p>
                    <p className="text-xs text-slate-400 capitalize">{t.tier}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-32 bg-slate-100 rounded-full h-2">
                    <div className={`h-2 rounded-full ${t.progress_pct >= 80 ? 'bg-green-500' : t.progress_pct >= 40 ? 'bg-amber-500' : 'bg-red-400'}`}
                         style={{width: `${t.progress_pct}%`}} />
                  </div>
                  <span className="text-xs font-mono text-slate-500 w-12 text-right">%{t.progress_pct}</span>
                  <span className="text-xs text-slate-400">{t.completed}/{t.total}</span>
                  <ChevronRight className="w-4 h-4 text-slate-300" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Tenant Detail */}
      <Dialog open={!!selectedTenant} onOpenChange={() => setSelectedTenant(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Onboarding Kontrol Listesi</DialogTitle></DialogHeader>
          {tenantProgress ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-500">Ilerleme: <span className="font-bold text-slate-900">%{tenantProgress.progress_pct}</span></p>
                  <p className="text-xs text-slate-400">{tenantProgress.completed} / {tenantProgress.total} adim tamamlandi</p>
                </div>
                <div className="w-16 h-16 relative">
                  <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                    <circle cx="18" cy="18" r="16" fill="none" stroke="#e2e8f0" strokeWidth="2.5" />
                    <circle cx="18" cy="18" r="16" fill="none" stroke={tenantProgress.progress_pct >= 80 ? '#22c55e' : tenantProgress.progress_pct >= 40 ? '#f59e0b' : '#ef4444'}
                            strokeWidth="2.5" strokeDasharray={`${tenantProgress.progress_pct} ${100 - tenantProgress.progress_pct}`} strokeLinecap="round" />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-bold">%{tenantProgress.progress_pct}</span>
                </div>
              </div>

              <div className="space-y-2">
                {tenantProgress.steps.map((step) => (
                  <div key={step.step_id} className={`flex items-start gap-3 p-2.5 rounded-lg border ${step.completed ? 'bg-green-50/50 border-green-200' : 'bg-white border-slate-200'}`}>
                    <div className="mt-0.5">
                      {step.completed ? (
                        <CheckCircle2 className="w-5 h-5 text-green-500" />
                      ) : (
                        <button onClick={() => markComplete(step.step_id)} className="w-5 h-5 rounded-full border-2 border-slate-300 hover:border-green-500 transition-colors" />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className={`text-sm font-medium ${step.completed ? 'text-green-700 line-through' : ''}`}>{step.label}</p>
                        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${CATEGORY_COLORS[step.category] || ''}`}>
                          {CATEGORY_LABELS[step.category] || step.category}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">{step.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : <p className="text-sm text-slate-400">Yukleniyor...</p>}
        </DialogContent>
      </Dialog>
    </div>
  );
};

/* ================================================================
   MAIN PAGE — Governance Panel
   ================================================================ */
const GovernancePanel = ({ user, tenant, onLogout }) => {
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="governance">
      <div className="p-4 md:p-6 max-w-[1400px] mx-auto space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2" data-testid="governance-title">
            <Settings2 className="w-6 h-6 text-indigo-600" />
            Governance & Metering
          </h1>
          <p className="text-sm text-gray-500 mt-1">Entitlement, kullanim olcumu ve feature flag yonetimi.</p>
        </div>

        <Tabs defaultValue="entitlements">
          <TabsList className="bg-slate-100" data-testid="governance-tabs">
            <TabsTrigger value="entitlements" className="gap-1.5"><Shield className="w-3.5 h-3.5" /> Entitlement</TabsTrigger>
            <TabsTrigger value="metering" className="gap-1.5"><Gauge className="w-3.5 h-3.5" /> Metering</TabsTrigger>
            <TabsTrigger value="flags" className="gap-1.5"><Flag className="w-3.5 h-3.5" /> Feature Flags</TabsTrigger>
            <TabsTrigger value="onboarding" className="gap-1.5"><Zap className="w-3.5 h-3.5" /> Onboarding</TabsTrigger>
          </TabsList>

          <TabsContent value="entitlements"><EntitlementsTab /></TabsContent>
          <TabsContent value="metering"><MeteringTab /></TabsContent>
          <TabsContent value="flags"><FeatureFlagsTab /></TabsContent>
          <TabsContent value="onboarding"><OnboardingTab /></TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default GovernancePanel;
