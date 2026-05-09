import React, { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog } from '@/lib/dialogs';
import {
  Shield, Activity, Flag, BarChart3, RefreshCw, Search,
  Plus, Trash2, Settings2, ChevronRight, AlertTriangle,
  CheckCircle2, XCircle, Gauge, Building2, Zap,
  Rocket, Play, Server, ShieldAlert, Loader2,
  CircleDot, Timer, Database, TestTube2, Ban, ShieldCheck,
} from 'lucide-react';

const TIER_INTENT = {
  enterprise: 'default',
  professional: 'info',
  basic: 'success',
  mini: 'success',
};

const handleApiError = (e, fallback) => {
  const msg = e?.response?.data?.detail || e?.message || fallback;
  toast.error(msg);
};

/* ================================================================
   TAB 1 — Entitlements Overview
   ================================================================ */
const EntitlementsTab = ({ refreshKey }) => {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenantDetail, setTenantDetail] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [search, setSearch] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, tRes] = await Promise.all([
        axios.get('/admin/entitlements/overview'),
        axios.get('/admin/tenants'),
      ]);
      setOverview(ovRes.data);
      setTenants(tRes.data?.tenants || []);
    } catch (e) {
      handleApiError(e, 'Entitlement verileri yüklenemedi');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview, refreshKey]);

  const loadTenantDetail = async (tenantId) => {
    setSelectedTenant(tenantId);
    setTenantDetail(null);
    try {
      const res = await axios.get(`/admin/tenants/${tenantId}/entitlements`);
      setTenantDetail(res.data);
    } catch (e) {
      handleApiError(e, 'Tenant detayı yüklenemedi');
    }
  };

  const filteredTenants = useMemo(() => {
    if (!search) return tenants;
    const q = search.toLowerCase();
    return tenants.filter((t) =>
      (t.property_name || '').toLowerCase().includes(q) ||
      (t.id || '').toLowerCase().includes(q)
    );
  }, [tenants, search]);

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;
  }

  const tierEntries = Object.entries(overview?.by_tier || {});

  return (
    <div className="space-y-4" data-testid="entitlements-tab">
      {overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={Building2} label="Toplam Tenant" value={overview.total_tenants ?? 0} intent="default" />
          {tierEntries.map(([tier, count]) => (
            <KpiCard
              key={tier}
              icon={Shield}
              label={tier.charAt(0).toUpperCase() + tier.slice(1)}
              value={count}
              intent={TIER_INTENT[tier] || 'neutral'}
            />
          ))}
          {overview.expired_count > 0 && (
            <KpiCard icon={AlertTriangle} label="Süresi Dolan" value={overview.expired_count} intent="danger" />
          )}
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center justify-between gap-2">
            <span className="flex items-center gap-2"><Shield className="w-4 h-4" /> Tenant Entitlement Detay</span>
            <span className="text-xs font-normal text-slate-500">
              {filteredTenants.length} / {tenants.length} tenant
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative mb-3 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Otel adı veya ID ile ara..."
              className="pl-9 h-9 text-sm"
              aria-label="Tenant arama"
            />
          </div>
          {filteredTenants.length === 0 ? (
            <div className="text-center py-6 text-sm text-slate-400">Eşleşen tenant yok.</div>
          ) : (
            <div className="divide-y">
              {filteredTenants.map((t) => {
                const moduleCount = Object.values(t.modules || {}).filter(Boolean).length;
                const tier = (t.subscription_tier || 'basic').toLowerCase();
                return (
                  <div
                    key={t.id}
                    className="flex items-center justify-between py-2.5 px-2 hover:bg-slate-50 rounded cursor-pointer"
                    onClick={() => loadTenantDetail(t.id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') loadTenantDetail(t.id); }}
                    role="button"
                    tabIndex={0}
                    data-testid={`tenant-row-${t.id}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800 truncate">{t.property_name}</p>
                        <p className="text-xs text-slate-400 capitalize">{tier}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <StatusBadge intent="neutral">{moduleCount} modül</StatusBadge>
                      <ChevronRight className="w-4 h-4 text-slate-300" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

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
                <StatusBadge intent={tenantDetail.is_expired ? 'danger' : 'success'}>
                  {tenantDetail.subscription_status}
                </StatusBadge>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {Object.entries(tenantDetail.quotas || {}).map(([key, q]) => (
                  <div key={key} className="border rounded-lg p-3">
                    <p className="text-xs text-slate-500 capitalize">{key}</p>
                    <p className="text-lg font-bold">{q.current} <span className="text-sm font-normal text-slate-400">/ {q.limit || '∞'}</span></p>
                    {!q.allowed && <p className="text-xs text-rose-600 mt-1 font-medium">Limit aşıldı!</p>}
                  </div>
                ))}
              </div>

              <div>
                <p className="text-sm font-medium mb-2">Aktif Modüller</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(tenantDetail.modules || {}).filter(([, v]) => v).map(([k]) => (
                    <Badge key={k} variant="outline" className="text-xs bg-emerald-50 text-emerald-700 border-emerald-200">{k}</Badge>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-sm font-medium mb-2">Kapalı Modüller</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(tenantDetail.modules || {}).filter(([, v]) => !v).map(([k]) => (
                    <Badge key={k} variant="outline" className="text-xs bg-slate-50 text-slate-400">{k}</Badge>
                  ))}
                </div>
              </div>
            </div>
          ) : <p className="text-sm text-slate-400">Yükleniyor...</p>}
        </DialogContent>
      </Dialog>
    </div>
  );
};

/* ================================================================
   TAB 2 — Usage Metering
   ================================================================ */
const EVENT_LABELS = {
  api_call: 'API Çağrısı',
  reservation_created: 'Rezervasyon',
  login: 'Giriş',
  guest_created: 'Misafir',
  channel_sync: 'Kanal Sync',
  report_generated: 'Rapor',
  invoice_created: 'Fatura',
  ai_request: 'AI İstek',
  webhook_received: 'Webhook',
};

const MeteringTab = ({ refreshKey }) => {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenantUsage, setTenantUsage] = useState(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/usage/overview');
      setOverview(res.data);
    } catch (e) {
      handleApiError(e, 'Kullanım verileri yüklenemedi');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview, refreshKey]);

  const loadTenantUsage = async (tenantId) => {
    setSelectedTenant(tenantId);
    setTenantUsage(null);
    try {
      const res = await axios.get(`/admin/tenants/${tenantId}/usage?days=30`);
      setTenantUsage(res.data);
    } catch (e) {
      handleApiError(e, 'Tenant kullanımı yüklenemedi');
    }
  };

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;
  }

  const todayTotal = Object.values(overview?.today || {}).reduce((s, v) => s + v, 0);
  const monthTotal = Object.values(overview?.this_month || {}).reduce((s, v) => s + v, 0);

  return (
    <div className="space-y-4" data-testid="metering-tab">
      {overview && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard icon={Activity} label="Aktif Tenant (7g)" value={overview.active_tenants_7d ?? 0} intent="success" />
            <KpiCard icon={Gauge} label="Bugün Toplam Olay" value={todayTotal.toLocaleString()} intent="info" />
            <KpiCard icon={BarChart3} label="Bu Ay Toplam Olay" value={monthTotal.toLocaleString()} intent="default" />
            <KpiCard icon={Building2} label="En Aktif Tenant" value={overview.top_tenants?.[0]?.total_events?.toLocaleString() || '—'} sub={overview.top_tenants?.[0]?.property_name || ''} intent="neutral" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-600">Bugün</CardTitle></CardHeader>
              <CardContent>
                {Object.keys(overview.today || {}).length === 0 ? (
                  <p className="text-sm text-slate-400">Henüz veri yok</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(overview.today).map(([event, count]) => (
                      <div key={event} className="flex justify-between items-center">
                        <span className="text-sm text-slate-700">{EVENT_LABELS[event] || event}</span>
                        <span className="text-sm font-mono font-semibold text-slate-800">{count.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-600">Bu Ay</CardTitle></CardHeader>
              <CardContent>
                {Object.keys(overview.this_month || {}).length === 0 ? (
                  <p className="text-sm text-slate-400">Henüz veri yok</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(overview.this_month).map(([event, count]) => (
                      <div key={event} className="flex justify-between items-center">
                        <span className="text-sm text-slate-700">{EVENT_LABELS[event] || event}</span>
                        <span className="text-sm font-mono font-semibold text-slate-800">{count.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {overview.top_tenants?.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2"><BarChart3 className="w-4 h-4" /> En Aktif Tenantlar (Bu Ay)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="divide-y">
                  {overview.top_tenants.map((t, i) => (
                    <div
                      key={t.tenant_id}
                      className="flex items-center justify-between py-2 px-1 hover:bg-slate-50 rounded cursor-pointer"
                      onClick={() => loadTenantUsage(t.tenant_id)}
                      onKeyDown={(e) => { if (e.key === 'Enter') loadTenantUsage(t.tenant_id); }}
                      role="button"
                      tabIndex={0}
                      data-testid={`top-tenant-${i}`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono text-slate-400 w-5">#{i + 1}</span>
                        <div>
                          <p className="text-sm font-medium text-slate-800">{t.property_name}</p>
                          <p className="text-xs text-slate-400 capitalize">{t.tier}</p>
                        </div>
                      </div>
                      <span className="text-sm font-mono font-semibold text-slate-800">{t.total_events.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      <Dialog open={!!selectedTenant} onOpenChange={() => setSelectedTenant(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Tenant Kullanımı (30 gün)</DialogTitle></DialogHeader>
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
                <p className="text-sm font-medium mb-2">Olaylar (Son 30 Gün)</p>
                {Object.keys(tenantUsage.events || {}).length === 0 ? (
                  <p className="text-sm text-slate-400">Veri yok</p>
                ) : (
                  <div className="space-y-2">
                    {Object.entries(tenantUsage.events).map(([event, count]) => (
                      <div key={event} className="flex justify-between items-center border-b pb-1">
                        <span className="text-sm">{EVENT_LABELS[event] || event}</span>
                        <span className="text-sm font-mono font-semibold">{count.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : <p className="text-sm text-slate-400">Yükleniyor...</p>}
        </DialogContent>
      </Dialog>
    </div>
  );
};

/* ================================================================
   TAB 3 — Feature Flags
   ================================================================ */
const FeatureFlagsTab = ({ refreshKey }) => {
  const [flags, setFlags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ flag_key: '', enabled: false, description: '', rollout_percentage: '', kill_switch: false, expires_at: '' });
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');

  const loadFlags = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/feature-flags');
      setFlags(res.data?.flags || []);
    } catch (e) {
      handleApiError(e, 'Feature flag listesi yüklenemedi');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadFlags(); }, [loadFlags, refreshKey]);

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
        const v = parseInt(form.rollout_percentage, 10);
        if (Number.isNaN(v) || v < 0 || v > 100) {
          toast.error('Rollout yüzdesi 0-100 arasında olmalı');
          setSaving(false);
          return;
        }
        payload.rollout_percentage = v;
      }
      if (form.expires_at) payload.expires_at = form.expires_at;
      await axios.post('/admin/feature-flags', payload);
      toast.success('Feature flag kaydedildi');
      setShowCreate(false);
      setForm({ flag_key: '', enabled: false, description: '', rollout_percentage: '', kill_switch: false, expires_at: '' });
      await loadFlags();
    } catch (e) {
      handleApiError(e, 'Flag kaydedilemedi');
    } finally { setSaving(false); }
  };

  const handleDelete = async (flagKey) => {
    if (!await confirmDialog({ message: `"${flagKey}" flag'ını silmek istediğinize emin misiniz?`, variant: 'danger' })) return;
    try {
      await axios.delete(`/admin/feature-flags/${flagKey}`);
      toast.success(`"${flagKey}" silindi`);
      await loadFlags();
    } catch (e) {
      handleApiError(e, 'Flag silinemedi');
    }
  };

  const toggleFlag = async (flag) => {
    try {
      await axios.post('/admin/feature-flags', { ...flag, enabled: !flag.enabled });
      toast.success(`"${flag.flag_key}" ${!flag.enabled ? 'açıldı' : 'kapatıldı'}`);
      await loadFlags();
    } catch (e) {
      handleApiError(e, 'Flag güncellenemedi');
    }
  };

  const toggleKillSwitch = async (flag) => {
    const willActivate = !flag.kill_switch;
    if (willActivate && !await confirmDialog({
      message: `"${flag.flag_key}" için Kill Switch'i aktif etmek istediğinize emin misiniz? Bu özellik tüm tenantlar için anında kapanır.`,
      variant: 'danger',
    })) return;
    try {
      await axios.post('/admin/feature-flags', { ...flag, kill_switch: willActivate });
      toast.success(`Kill switch ${willActivate ? 'aktif edildi' : 'kaldırıldı'}`);
      await loadFlags();
    } catch (e) {
      handleApiError(e, 'Kill switch güncellenemedi');
    }
  };

  const filteredFlags = useMemo(() => {
    if (!search) return flags;
    const q = search.toLowerCase();
    return flags.filter((f) =>
      (f.flag_key || '').toLowerCase().includes(q) ||
      (f.description || '').toLowerCase().includes(q)
    );
  }, [flags, search]);

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;
  }

  return (
    <div className="space-y-4" data-testid="feature-flags-tab">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
        <div className="relative max-w-sm w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Flag ara..."
            className="pl-9 h-9"
            aria-label="Flag arama"
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">{filteredFlags.length} / {flags.length} flag</span>
          <Button size="sm" onClick={() => setShowCreate(true)} data-testid="create-flag-btn">
            <Plus className="w-4 h-4 mr-1" /> Yeni Flag
          </Button>
        </div>
      </div>

      {filteredFlags.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Flag className="w-10 h-10 text-slate-300 mx-auto mb-2" aria-hidden="true" />
            <p className="text-sm font-medium text-slate-600">
              {search ? 'Eşleşen flag yok' : 'Henüz feature flag tanımlanmamış'}
            </p>
            {!search && (
              <Button size="sm" variant="outline" className="mt-3" onClick={() => setShowCreate(true)}>
                <Plus className="w-4 h-4 mr-1" /> İlk Flag'ini Oluştur
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2.5">
          {filteredFlags.map((flag) => {
            const overrideCount = Object.keys(flag.tenant_overrides || {}).length;
            return (
              <Card
                key={flag.flag_key}
                className={flag.kill_switch ? 'border-rose-300 bg-rose-50/30' : ''}
                data-testid={`flag-card-${flag.flag_key}`}
              >
                <CardContent className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-mono text-sm font-semibold text-slate-800">{flag.flag_key}</p>
                        {flag.kill_switch && <StatusBadge intent="danger" icon={Ban}>KILL SWITCH</StatusBadge>}
                        {flag.enabled && !flag.kill_switch && <StatusBadge intent="success">Aktif</StatusBadge>}
                        {!flag.enabled && !flag.kill_switch && <StatusBadge intent="neutral">Kapalı</StatusBadge>}
                        {overrideCount > 0 && <StatusBadge intent="info">{overrideCount} override</StatusBadge>}
                      </div>
                      {flag.description && <p className="text-xs text-slate-500 mt-1">{flag.description}</p>}
                      <div className="flex items-center gap-4 mt-2 text-xs text-slate-400 flex-wrap">
                        {flag.rollout_percentage != null && <span>Rollout: %{flag.rollout_percentage}</span>}
                        {flag.expires_at && <span>Bitiş: {new Date(flag.expires_at).toLocaleDateString('tr-TR')}</span>}
                        {flag.updated_by && <span>Son: {flag.updated_by}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Switch
                        checked={flag.enabled}
                        onCheckedChange={() => toggleFlag(flag)}
                        disabled={flag.kill_switch}
                        data-testid={`flag-toggle-${flag.flag_key}`}
                        aria-label={`${flag.flag_key} aktif/pasif`}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className={`h-8 w-8 ${flag.kill_switch ? 'text-rose-600 hover:text-rose-700' : 'text-slate-400 hover:text-rose-600'}`}
                        onClick={() => toggleKillSwitch(flag)}
                        title={flag.kill_switch ? 'Kill switch kaldır' : 'Kill switch aktif et'}
                        aria-label="Kill switch"
                      >
                        {flag.kill_switch ? <Ban className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-slate-400 hover:text-rose-600"
                        onClick={() => handleDelete(flag.flag_key)}
                        title="Sil"
                        aria-label="Flag sil"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Yeni Feature Flag</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div>
              <Label>Flag Key *</Label>
              <Input
                placeholder="new_booking_flow"
                value={form.flag_key}
                onChange={(e) => setForm((f) => ({ ...f, flag_key: e.target.value }))}
                data-testid="flag-key-input"
              />
            </div>
            <div>
              <Label>Açıklama</Label>
              <Input
                placeholder="Bu flag ne yapar?"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </div>
            <div className="flex items-center justify-between">
              <Label>Aktif</Label>
              <Switch checked={form.enabled} onCheckedChange={(v) => setForm((f) => ({ ...f, enabled: v }))} />
            </div>
            <div>
              <Label>Rollout Yüzdesi (0-100, boş = tüm tenantlar)</Label>
              <Input
                type="number" min="0" max="100" placeholder="100"
                value={form.rollout_percentage}
                onChange={(e) => setForm((f) => ({ ...f, rollout_percentage: e.target.value }))}
              />
            </div>
            <div>
              <Label>Bitiş Tarihi (opsiyonel)</Label>
              <Input
                type="datetime-local"
                value={form.expires_at}
                onChange={(e) => setForm((f) => ({ ...f, expires_at: e.target.value }))}
              />
            </div>
            <div className="flex items-center justify-between">
              <Label className="text-rose-600">Kill Switch</Label>
              <Switch checked={form.kill_switch} onCheckedChange={(v) => setForm((f) => ({ ...f, kill_switch: v }))} />
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
const CATEGORY_LABELS = { setup: 'Kurulum', operations: 'Operasyon', team: 'Ekip', channels: 'Kanallar', finance: 'Finans', reports: 'Raporlar' };
const CATEGORY_INTENT = { setup: 'info', operations: 'success', team: 'default', channels: 'warning', finance: 'danger', reports: 'neutral' };

const OnboardingTab = ({ refreshKey }) => {
  const [overview, setOverview] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [tenantProgress, setTenantProgress] = useState(null);
  const [search, setSearch] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/admin/onboarding/overview');
      setOverview(res.data?.tenants || []);
    } catch (e) {
      handleApiError(e, 'Onboarding listesi yüklenemedi');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadOverview(); }, [loadOverview, refreshKey]);

  const loadTenantProgress = async (tenantId) => {
    setSelectedTenant(tenantId);
    setTenantProgress(null);
    try {
      const res = await axios.get(`/admin/tenants/${tenantId}/onboarding`);
      setTenantProgress(res.data);
    } catch (e) {
      handleApiError(e, 'Tenant onboarding yüklenemedi');
    }
  };

  const markComplete = async (stepId) => {
    if (!selectedTenant) return;
    try {
      await axios.post(`/admin/tenants/${selectedTenant}/onboarding/${stepId}/complete`);
      toast.success('Adım tamamlandı');
      await loadTenantProgress(selectedTenant);
      loadOverview();
    } catch (e) {
      handleApiError(e, 'Adım kaydedilemedi');
    }
  };

  const filteredOverview = useMemo(() => {
    if (!search) return overview;
    const q = search.toLowerCase();
    return overview.filter((t) => (t.property_name || '').toLowerCase().includes(q));
  }, [overview, search]);

  const avgProgress = overview.length
    ? Math.round(overview.reduce((s, t) => s + (t.progress_pct || 0), 0) / overview.length)
    : 0;
  const completedTenants = overview.filter((t) => (t.progress_pct || 0) >= 100).length;
  const stuckTenants = overview.filter((t) => (t.progress_pct || 0) < 40).length;

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;
  }

  return (
    <div className="space-y-4" data-testid="onboarding-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={Building2} label="Toplam Tenant" value={overview.length} intent="default" />
        <KpiCard icon={Gauge} label="Ortalama İlerleme" value={`%${avgProgress}`} intent={avgProgress >= 80 ? 'success' : avgProgress >= 40 ? 'warning' : 'danger'} />
        <KpiCard icon={CheckCircle2} label="Tamamlanan" value={completedTenants} intent="success" />
        <KpiCard icon={AlertTriangle} label="Takılan (<40%)" value={stuckTenants} intent="danger" />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center justify-between gap-2">
            <span className="flex items-center gap-2"><Zap className="w-4 h-4" /> Onboarding Durumu</span>
            <span className="text-xs font-normal text-slate-500">{filteredOverview.length} / {overview.length} tenant</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative mb-3 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" aria-hidden="true" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Otel adı ile ara..."
              className="pl-9 h-9 text-sm"
              aria-label="Onboarding tenant arama"
            />
          </div>
          {filteredOverview.length === 0 ? (
            <div className="text-center py-6 text-sm text-slate-400">Eşleşen tenant yok.</div>
          ) : (
            <div className="divide-y">
              {filteredOverview.map((t) => {
                const pct = t.progress_pct || 0;
                const barClass = pct >= 80 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-rose-400';
                return (
                  <div
                    key={t.tenant_id}
                    className="flex items-center justify-between py-2.5 px-2 hover:bg-slate-50 rounded cursor-pointer"
                    onClick={() => loadTenantProgress(t.tenant_id)}
                    onKeyDown={(e) => { if (e.key === 'Enter') loadTenantProgress(t.tenant_id); }}
                    role="button"
                    tabIndex={0}
                    data-testid={`onboard-row-${t.tenant_id}`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800 truncate">{t.property_name}</p>
                        <p className="text-xs text-slate-400 capitalize">{t.tier}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <div className="w-32 bg-slate-100 rounded-full h-2">
                        <div className={`h-2 rounded-full ${barClass}`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs font-mono text-slate-600 w-12 text-right">%{pct}</span>
                      <span className="text-xs text-slate-400">{t.completed}/{t.total}</span>
                      <ChevronRight className="w-4 h-4 text-slate-300" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!selectedTenant} onOpenChange={() => setSelectedTenant(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Onboarding Kontrol Listesi</DialogTitle></DialogHeader>
          {tenantProgress ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-500">İlerleme: <span className="font-bold text-slate-900">%{tenantProgress.progress_pct}</span></p>
                  <p className="text-xs text-slate-400">{tenantProgress.completed} / {tenantProgress.total} adım tamamlandı</p>
                </div>
                <div className="w-16 h-16 relative">
                  <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90" aria-hidden="true">
                    <circle cx="18" cy="18" r="16" fill="none" stroke="#e2e8f0" strokeWidth="2.5" />
                    <circle cx="18" cy="18" r="16" fill="none"
                      stroke={tenantProgress.progress_pct >= 80 ? '#10b981' : tenantProgress.progress_pct >= 40 ? '#f59e0b' : '#f43f5e'}
                      strokeWidth="2.5" strokeDasharray={`${tenantProgress.progress_pct} ${100 - tenantProgress.progress_pct}`} strokeLinecap="round" />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-bold">%{tenantProgress.progress_pct}</span>
                </div>
              </div>

              <div className="space-y-2">
                {tenantProgress.steps?.map((step) => (
                  <div
                    key={step.step_id}
                    className={`flex items-start gap-3 p-2.5 rounded-lg border ${step.completed ? 'bg-emerald-50/50 border-emerald-200' : 'bg-white border-slate-200'}`}
                  >
                    <div className="mt-0.5">
                      {step.completed ? (
                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                      ) : (
                        <button
                          onClick={() => markComplete(step.step_id)}
                          className="w-5 h-5 rounded-full border-2 border-slate-300 hover:border-emerald-500 transition-colors"
                          aria-label={`${step.label} adımını tamamla`}
                          title="Adımı tamamlandı işaretle"
                        />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className={`text-sm font-medium ${step.completed ? 'text-emerald-700 line-through' : 'text-slate-800'}`}>{step.label}</p>
                        <StatusBadge intent={CATEGORY_INTENT[step.category] || 'neutral'}>
                          {CATEGORY_LABELS[step.category] || step.category}
                        </StatusBadge>
                      </div>
                      {step.description && <p className="text-xs text-slate-500 mt-0.5">{step.description}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : <p className="text-sm text-slate-400">Yükleniyor...</p>}
        </DialogContent>
      </Dialog>
    </div>
  );
};

/* ================================================================
   TAB 5 — Deploy Pipeline
   ================================================================ */
const GATE_ICONS = { lint: ShieldAlert, unit_test: TestTube2, security_audit: Shield, migration_check: Database, build: Server, smoke_test: Rocket };
const STATUS_INTENT = { passed: 'success', failed: 'danger', running: 'warning', pending: 'neutral' };

const DeployTab = ({ refreshKey }) => {
  const [pipelines, setPipelines] = useState([]);
  const [triggers, setTriggers] = useState(null);
  const [canaryStatus, setCanaryStatus] = useState(null);
  const [smokeResult, setSmokeResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runningSmoke, setRunningSmoke] = useState(false);
  const [activePipeline, setActivePipeline] = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [pRes, tRes, cRes] = await Promise.all([
        axios.get('/deploy/pipelines?limit=5'),
        axios.get('/deploy/rollback/evaluate'),
        axios.get('/deploy/canary/status'),
      ]);
      setPipelines(pRes.data?.data?.pipelines || []);
      setTriggers(tRes.data?.data || null);
      setCanaryStatus(cRes.data?.data || null);
    } catch (e) {
      handleApiError(e, 'Deploy verileri yüklenemedi');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData, refreshKey]);

  const runPipeline = async () => {
    if (!await confirmDialog({
      message: 'Yeni deploy pipeline\'ı çalıştırılacak. Devam etmek istiyor musunuz?',
      variant: 'default',
    })) return;
    setRunning(true);
    try {
      const res = await axios.post('/deploy/pipeline/run-all', { version_tag: 'latest' });
      setActivePipeline(res.data?.data || null);
      toast.success('Pipeline başlatıldı');
      await loadData();
    } catch (e) {
      handleApiError(e, 'Pipeline başlatılamadı');
    } finally { setRunning(false); }
  };

  const runSmoke = async () => {
    setRunningSmoke(true);
    try {
      const res = await axios.post('/deploy/smoke-tests/run');
      setSmokeResult(res.data?.data || null);
      toast.success('Smoke test tamamlandı');
    } catch (e) {
      handleApiError(e, 'Smoke test başarısız');
    } finally { setRunningSmoke(false); }
  };

  if (loading) {
    return <div className="flex justify-center py-12"><RefreshCw className="w-5 h-5 animate-spin text-slate-400" /></div>;
  }

  const latestPipeline = activePipeline || (pipelines.length > 0 ? pipelines[0] : null);
  const recIntent = triggers?.recommendation === 'continue' ? 'success'
    : triggers?.recommendation === 'rollback' ? 'danger' : 'warning';
  const recLabel = triggers?.recommendation === 'continue' ? 'SAĞLAM'
    : triggers?.recommendation === 'rollback' ? 'ROLLBACK' : 'DİKKAT';

  return (
    <div className="space-y-4" data-testid="deploy-tab">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-slate-500">{pipelines.length} pipeline kaydı</p>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={runSmoke} disabled={runningSmoke} data-testid="run-smoke-btn">
            {runningSmoke ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <TestTube2 className="w-4 h-4 mr-1" />}
            Smoke Test
          </Button>
          <Button size="sm" onClick={runPipeline} disabled={running} data-testid="run-pipeline-btn">
            {running ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Play className="w-4 h-4 mr-1" />}
            Pipeline Çalıştır
          </Button>
        </div>
      </div>

      {latestPipeline && (
        <Card data-testid="pipeline-status-card">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <CardTitle className="text-sm flex items-center gap-2">
                <Rocket className="w-4 h-4" /> Pipeline: <span className="font-mono text-xs">{latestPipeline.pipeline_id?.slice(0, 16)}</span>
              </CardTitle>
              <div className="flex items-center gap-2">
                <StatusBadge intent={STATUS_INTENT[latestPipeline.status] || 'neutral'}>
                  {(latestPipeline.status || '').toUpperCase()}
                </StatusBadge>
                <span className="text-xs text-slate-400">{latestPipeline.passed_gates}/{latestPipeline.total_gates} gate</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(latestPipeline.gates || {}).map(([gateId, gate]) => {
                const Icon = GATE_ICONS[gateId] || CircleDot;
                return (
                  <div key={gateId} className="flex items-center gap-3 p-2.5 rounded-lg border bg-white" data-testid={`gate-${gateId}`}>
                    <Icon className="w-4 h-4 text-slate-500" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium capitalize text-slate-800">{gateId.replace(/_/g, ' ')}</p>
                      {gate.errors?.length > 0 && (
                        <p className="text-xs text-rose-600 truncate mt-0.5">{gate.errors[0]}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-slate-500">
                      {gate.duration_ms != null && <span className="font-mono">{gate.duration_ms}ms</span>}
                      <StatusBadge intent={STATUS_INTENT[gate.status] || 'neutral'}>{gate.status}</StatusBadge>
                    </div>
                  </div>
                );
              })}
            </div>
            {latestPipeline.verdict && (
              <div className={`mt-3 p-2 rounded text-xs font-mono text-center ${latestPipeline.verdict === 'ALL_GATES_PASSED' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                {latestPipeline.verdict}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {triggers && (
        <Card data-testid="triggers-card">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <CardTitle className="text-sm flex items-center gap-2">
                <ShieldAlert className="w-4 h-4" /> Auto-Rollback Trigger'ları
              </CardTitle>
              <StatusBadge intent={recIntent}>{recLabel}</StatusBadge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {triggers.triggers?.map((t) => (
                <div
                  key={t.trigger_id}
                  className={`flex items-center justify-between p-2.5 rounded-lg border ${t.triggered ? 'bg-rose-50 border-rose-200' : 'bg-white'}`}
                  data-testid={`trigger-${t.trigger_id}`}
                >
                  <div className="flex-1">
                    <p className="text-sm font-medium text-slate-800">{t.name}</p>
                    <p className="text-xs text-slate-400">{t.description}</p>
                  </div>
                  <div className="flex items-center gap-3 text-right">
                    <div>
                      <p className={`text-sm font-mono font-bold ${t.triggered ? 'text-rose-600' : 'text-emerald-600'}`}>{t.current_value}</p>
                      <p className="text-[10px] text-slate-400">eşik: {t.threshold} {t.unit}</p>
                    </div>
                    {t.triggered ? <XCircle className="w-4 h-4 text-rose-500" /> : <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {canaryStatus && canaryStatus.current_stage_id && (
        <Card data-testid="canary-status-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center gap-2"><CircleDot className="w-4 h-4" /> Canary Deploy Durumu</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-800">{canaryStatus.current_stage_name || canaryStatus.current_stage_id}</p>
                <p className="text-xs text-slate-400">Trafik: %{canaryStatus.traffic_percent || 0}</p>
              </div>
              <StatusBadge
                intent={canaryStatus.status === 'active' ? 'info' : canaryStatus.status === 'rolled_back' ? 'danger' : 'neutral'}
              >
                {(canaryStatus.status || '').toUpperCase()}
              </StatusBadge>
            </div>
          </CardContent>
        </Card>
      )}

      {smokeResult && (
        <Card data-testid="smoke-results-card">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <CardTitle className="text-sm flex items-center gap-2">
                <TestTube2 className="w-4 h-4" /> Smoke Test Sonuçları
              </CardTitle>
              <StatusBadge intent={smokeResult.verdict === 'PASS' ? 'success' : 'danger'}>
                {smokeResult.passed}/{smokeResult.total} GEÇTİ
              </StatusBadge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {smokeResult.results?.map((t) => (
                <div key={t.id} className={`flex items-center justify-between py-1.5 px-2 rounded ${t.passed ? '' : 'bg-rose-50'}`} data-testid={`smoke-${t.id}`}>
                  <div className="flex items-center gap-2">
                    {t.passed ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> : <XCircle className="w-3.5 h-3.5 text-rose-500" />}
                    <span className="text-sm text-slate-700">{t.name}</span>
                  </div>
                  <span className="text-xs font-mono text-slate-400">{t.duration_ms}ms</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {pipelines.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Timer className="w-4 h-4" /> Son Pipeline'lar</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y">
              {pipelines.map((p) => (
                <div key={p.pipeline_id} className="flex items-center justify-between py-2 px-1">
                  <div>
                    <p className="text-sm font-mono text-slate-700">{p.pipeline_id?.slice(0, 16)}</p>
                    <p className="text-xs text-slate-400">{p.triggered_by} — {new Date(p.started_at).toLocaleString('tr-TR')}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-slate-500">{p.passed_gates}/{p.total_gates}</span>
                    <StatusBadge intent={STATUS_INTENT[p.status] || 'neutral'}>{p.status}</StatusBadge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

/* ================================================================
   MAIN PAGE — Governance Panel
   ================================================================ */
const GovernancePanel = () => {
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = () => {
    setRefreshing(true);
    setRefreshKey((k) => k + 1);
    setTimeout(() => setRefreshing(false), 600);
  };

  return (
    <div className="p-4 md:p-6 max-w-[1400px] mx-auto space-y-4">
      <PageHeader
        icon={Settings2}
        title="Governance & Metering"
        subtitle="Entitlement, kullanım ölçümü, feature flag ve deploy pipeline yönetimi tek panelde."
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
            Yenile
          </Button>
        }
      />

      <Tabs defaultValue="entitlements">
        <TabsList className="bg-slate-100" data-testid="governance-tabs">
          <TabsTrigger value="entitlements" className="gap-1.5"><Shield className="w-3.5 h-3.5" /> Entitlement</TabsTrigger>
          <TabsTrigger value="metering" className="gap-1.5"><Gauge className="w-3.5 h-3.5" /> Metering</TabsTrigger>
          <TabsTrigger value="flags" className="gap-1.5"><Flag className="w-3.5 h-3.5" /> Feature Flags</TabsTrigger>
          <TabsTrigger value="onboarding" className="gap-1.5"><Zap className="w-3.5 h-3.5" /> Onboarding</TabsTrigger>
          <TabsTrigger value="deploy" className="gap-1.5"><Rocket className="w-3.5 h-3.5" /> Deploy</TabsTrigger>
        </TabsList>

        <TabsContent value="entitlements" className="mt-4"><EntitlementsTab refreshKey={refreshKey} /></TabsContent>
        <TabsContent value="metering" className="mt-4"><MeteringTab refreshKey={refreshKey} /></TabsContent>
        <TabsContent value="flags" className="mt-4"><FeatureFlagsTab refreshKey={refreshKey} /></TabsContent>
        <TabsContent value="onboarding" className="mt-4"><OnboardingTab refreshKey={refreshKey} /></TabsContent>
        <TabsContent value="deploy" className="mt-4"><DeployTab refreshKey={refreshKey} /></TabsContent>
      </Tabs>
    </div>
  );
};

export default GovernancePanel;
