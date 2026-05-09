import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog } from '@/lib/dialogs';
import {
  Activity, ArrowUpDown, CheckCircle, XCircle, Clock,
  RefreshCw, AlertTriangle, Loader2, Zap, BarChart3,
  Shield, Gauge, Timer, Inbox, Play, AlertOctagon,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const STATUS_LABEL = {
  pending: { tr: 'Bekliyor', intent: 'warning' },
  queued: { tr: 'Kuyrukta', intent: 'info' },
  pushed: { tr: 'Gönderildi', intent: 'info' },
  acked: { tr: 'Onaylandı', intent: 'success' },
  failed_retryable: { tr: 'Tekrar Denenecek', intent: 'warning' },
  manual_review: { tr: 'Başarısız', intent: 'danger' },
  skipped: { tr: 'Atlandı', intent: 'neutral' },
};

const SCOPE_LABEL = {
  availability: 'Stok',
  rate: 'Fiyat',
  restriction: 'Kısıtlama',
};

const FIELD_LABEL = {
  availability: 'Stok',
  rate: 'Fiyat',
  min_stay: 'Min. Konaklama',
  max_stay: 'Maks. Konaklama',
  closed: 'Kapalı',
  stop_sell: 'Satış Durdur',
  restrictions: 'Kısıtlamalar',
  __missing__: 'Eksik Kayıt',
  __unknown__: 'Bilinmeyen',
};

const StatusPill = ({ status }) => {
  const { t } = useTranslation();
  const m = STATUS_LABEL[status];
  if (!m) return <StatusBadge intent="neutral">{status || '-'}</StatusBadge>;
  return <StatusBadge intent={m.intent}>{m.tr}</StatusBadge>;
};

const ScopeChip = ({ scope }) => (
  <StatusBadge intent="neutral">{SCOPE_LABEL[scope] || scope || '-'}</StatusBadge>
);

const ARIPushDashboard = ({ user, tenant }) => {
  const [activeTab, setActiveTab] = useState('queue');
  const [loading, setLoading] = useState(false);
  const [refreshingTab, setRefreshingTab] = useState(false);
  const [errorBanner, setErrorBanner] = useState(null);

  const [stats, setStats] = useState(null);
  const [engineStats, setEngineStats] = useState(null);
  const [changeSets, setChangeSets] = useState([]);
  const [outboundLogs, setOutboundLogs] = useState([]);
  const [driftStates, setDriftStates] = useState([]);
  const [events, setEvents] = useState([]);
  const [opMetrics, setOpMetrics] = useState(null);
  const [driftMode, setDriftMode] = useState(null);

  const [statusFilter, setStatusFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [testResults, setTestResults] = useState({});
  const [testRunning, setTestRunning] = useState(null);

  const tenantId = tenant?.id || user?.tenant_id || null;
  const propertyId = tenant?.hotel_id || tenant?.property_id || user?.hotel_id || null;
  const scopeReady = !!(tenantId && propertyId);

  const params = useMemo(
    () => (scopeReady ? `tenant_id=${tenantId}&property_id=${propertyId}` : ''),
    [scopeReady, tenantId, propertyId],
  );

  const collectErrors = (results, labels) => {
    const errs = [];
    results.forEach((r, i) => {
      if (r.status === 'rejected') {
        const code = r.reason?.response?.status;
        const detail = r.reason?.response?.data?.detail || r.reason?.message || 'bilinmeyen hata';
        errs.push(`${labels[i]}: ${code ? code + ' — ' : ''}${detail}`);
      }
    });
    return errs;
  };

  const fetchHeader = useCallback(async (nocache = false) => {
    if (!scopeReady) return;
    const nc = nocache ? '&nocache=true' : '';
    const calls = [
      axios.get(`/channel-manager/ari/stats?${params}${nc}`),
      axios.get(`/channel-manager/ari/engine-stats`),
      axios.get(`/channel-manager/ari/test-harness/metrics?${params}${nc}`),
      axios.get(`/channel-manager/ari/drift/mode`),
    ];
    const labels = ['İstatistikler', 'Motor durumu', 'Operasyonel metrikler', 'Drift modu'];
    const r = await Promise.allSettled(calls);
    if (r[0].status === 'fulfilled') setStats(r[0].value.data);
    if (r[1].status === 'fulfilled') setEngineStats(r[1].value.data);
    if (r[2].status === 'fulfilled') setOpMetrics(r[2].value.data);
    if (r[3].status === 'fulfilled') setDriftMode(r[3].value.data);
    const errs = collectErrors(r, labels);
    setErrorBanner(errs.length ? errs.join(' • ') : null);
  }, [scopeReady, params]);

  const fetchTab = useCallback(async (tab, nocache = false) => {
    if (!scopeReady) return;
    const nc = nocache ? '&nocache=true' : '';
    let promise;
    let label;
    let setter;
    let extract;
    if (tab === 'queue') {
      promise = axios.get(`/channel-manager/ari/change-sets?${params}&limit=100${nc}`);
      label = 'Kuyruk';
      setter = setChangeSets;
      extract = (d) => d.change_sets || [];
    } else if (tab === 'outbound') {
      promise = axios.get(`/channel-manager/ari/outbound-logs?${params}&limit=50${nc}`);
      label = 'Giden istekler';
      setter = setOutboundLogs;
      extract = (d) => d.logs || [];
    } else if (tab === 'drift') {
      promise = axios.get(`/channel-manager/ari/drift?${params}&limit=50${nc}`);
      label = 'Drift';
      setter = setDriftStates;
      extract = (d) => d.drift_states || [];
    } else if (tab === 'events') {
      promise = axios.get(`/channel-manager/ari/events?${params}&limit=50${nc}`);
      label = 'Olaylar';
      setter = setEvents;
      extract = (d) => d.events || [];
    } else {
      return;
    }
    try {
      const { data } = await promise;
      setter(extract(data));
    } catch (e) {
      const code = e?.response?.status;
      const detail = e?.response?.data?.detail || e?.message || 'bilinmeyen hata';
      const msg = `${label}: ${code ? code + ' — ' : ''}${detail}`;
      setErrorBanner((prev) => (prev ? `${prev} • ${msg}` : msg));
      toast.error(`${label} yüklenemedi`);
    }
  }, [scopeReady, params]);

  const refreshActiveTab = async () => {
    if (!scopeReady) return;
    setRefreshingTab(true);
    try {
      await Promise.all([fetchHeader(true), fetchTab(activeTab, true)]);
    } finally {
      setRefreshingTab(false);
    }
  };

  const initialLoad = useCallback(async () => {
    if (!scopeReady) return;
    setLoading(true);
    try {
      await Promise.all([fetchHeader(false), fetchTab(activeTab, false)]);
    } finally {
      setLoading(false);
    }
  }, [scopeReady, fetchHeader, fetchTab, activeTab]);

  useEffect(() => { initialLoad(); }, [initialLoad]);

  // Lazy-load when tab changes
  useEffect(() => {
    if (!scopeReady) return;
    fetchTab(activeTab, false);
  }, [activeTab, scopeReady, fetchTab]);

  const pushPending = async () => {
    const ok = await confirmDialog({
      title: 'Bekleyenleri gönder',
      message:
        providerFilter === 'all'
          ? 'Tüm sağlayıcılara bekleyen değişiklik setleri gönderilecek. Onaylıyor musunuz?'
          : `${providerFilter} sağlayıcısına bekleyen değişiklik setleri gönderilecek. Onaylıyor musunuz?`,
      confirmText: 'Gönder',
      cancelText: 'Vazgeç',
    });
    if (!ok) return;
    try {
      const { data } = await axios.post(`/channel-manager/ari/push`, {
        tenant_id: tenantId,
        provider: providerFilter === 'all' ? null : providerFilter,
      });
      toast.success(`Gönderildi: ${data.pushed} • Atlandı: ${data.skipped} • Başarısız: ${data.failed}`);
      refreshActiveTab();
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || '';
      toast.error(`Gönderim başarısız ${detail ? '— ' + detail : ''}`);
    }
  };

  const toggleDriftMode = async () => {
    const newMode = driftMode?.mode === 'normal' ? 'recovery' : 'normal';
    const human =
      newMode === 'recovery'
        ? 'Kurtarma moduna alınacak — drift kontrolü 30 saniyede bir tüm property üzerinde çalışır. Sadece olay anında kullanın.'
        : 'Normal moda alınacak — drift kontrolü 2 dakikada bir, yalnızca değişen oda tipleri için çalışır.';
    const ok = await confirmDialog({
      title: 'Drift modunu değiştir',
      message: human,
      confirmText: 'Değiştir',
      cancelText: 'Vazgeç',
    });
    if (!ok) return;
    try {
      const { data } = await axios.post(`/channel-manager/ari/drift/mode/${newMode}`);
      setDriftMode({ mode: data.current_mode || data.mode, interval: data.interval, scope: data.scope });
      toast.success(`Drift modu: ${data.current_mode || data.mode} (${data.interval}s)`);
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || '';
      toast.error(`Mod değiştirilemedi ${detail ? '— ' + detail : ''}`);
    }
  };

  const runProviderTest = async (provider) => {
    const ok = await confirmDialog({
      title: 'Test paketi',
      message:
        `${provider} sağlayıcısının doğrulama testleri çalıştırılacak. ` +
        `Bu testler GERÇEK sağlayıcıya istek atar (sandbox veya canlı, ortam yapılandırmasına bağlı). ` +
        `Devam edilsin mi?`,
      confirmText: 'Çalıştır',
      cancelText: 'Vazgeç',
    });
    if (!ok) return;
    setTestRunning(provider);
    try {
      const { data } = await axios.post(`/channel-manager/ari/test-harness/run/${provider}`);
      setTestResults((prev) => ({ ...prev, [provider]: data }));
      const s = data.summary;
      if (s.failed === 0) toast.success(`${provider}: ${s.total} testin tümü geçti`);
      else toast.warning(`${provider}: ${s.passed}/${s.total} geçti, ${s.failed} başarısız`);
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || '';
      toast.error(`${provider} testi başarısız ${detail ? '— ' + detail : ''}`);
    }
    setTestRunning(null);
  };

  const filteredCS = changeSets.filter((cs) => {
    if (statusFilter !== 'all' && cs.status !== statusFilter) return false;
    if (providerFilter !== 'all' && cs.provider !== providerFilter) return false;
    return true;
  });

  if (!scopeReady) {
    return (
      <div className="p-6">
        <PageHeader icon={Zap} title="ARI Push Motoru" subtitle={t('cm.pages_ARIPushDashboard.stok_fiyat_ve_kisitlama_itme_ardisik_duz')} />
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="p-4 flex items-start gap-3">
            <AlertOctagon className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-slate-700">
              <p className="font-semibold mb-1">{t('cm.pages_ARIPushDashboard.property_bilgisi_bulunamadi')}</p>
              <p>
                {t('cm.pages_ARIPushDashboard.bu_sayfanin_calisabilmesi_icin_aktif_bir')}
              </p>
              <p className="mt-2 text-xs text-slate-500">
                tenant_id: {tenantId || '—'} • hotel_id: {propertyId || '—'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div data-testid="ari-push-dashboard" className="space-y-5 p-4 sm:p-6">
      <PageHeader
        icon={Zap}
        title="ARI Push Motoru"
        subtitle={t('cm.pages_ARIPushDashboard.stok_fiyat_ve_kisitlama_itme_ardisik_duz_e1aae')}
        actions={
          <>
            <Button data-testid="push-pending-btn" onClick={pushPending} size="sm">
              <Zap className="w-4 h-4 mr-1.5" /> {t('cm.pages_ARIPushDashboard.bekleyenleri_gonder')}
            </Button>
            <Button
              data-testid="refresh-btn"
              onClick={refreshActiveTab}
              variant="outline"
              size="sm"
              disabled={loading || refreshingTab}
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${(loading || refreshingTab) ? 'animate-spin' : ''}`} /> {t('cm.pages_ARIPushDashboard.yenile')}
            </Button>
          </>
        }
      />

      {errorBanner && (
        <Card className="border-l-4 border-l-rose-500">
          <CardContent className="p-3 flex items-start gap-2 text-sm">
            <AlertOctagon className="w-4 h-4 text-rose-600 mt-0.5 flex-shrink-0" />
            <div className="flex-1 text-slate-700">{errorBanner}</div>
            <Button variant="outline" size="sm" onClick={() => setErrorBanner(null)}>{t('cm.pages_ARIPushDashboard.kapat')}</Button>
          </CardContent>
        </Card>
      )}

      {/* KPI Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <KpiCard data-testid="metric-total-events" icon={Activity} intent="info" label={t('cm.pages_ARIPushDashboard.toplam_olay')} value={stats?.total_events ?? 0} />
        <KpiCard data-testid="metric-pending" icon={Clock} intent="warning" label="Bekliyor" value={stats?.pending_changes ?? 0} />
        <KpiCard data-testid="metric-acked" icon={CheckCircle} intent="success" label={t('cm.pages_ARIPushDashboard.onaylandi')} value={stats?.acked_changes ?? 0} />
        <KpiCard data-testid="metric-failed" icon={XCircle} intent="danger" label={t('cm.pages_ARIPushDashboard.basarisiz')} value={stats?.failed_changes ?? 0} />
        <KpiCard data-testid="metric-drift" icon={AlertTriangle} intent="warning" label="Drift" value={stats?.drift_count ?? 0} />
        <KpiCard data-testid="metric-outbound" icon={ArrowUpDown} intent="neutral" label="Giden" value={stats?.total_outbound_pushes ?? 0} />
      </div>

      {/* Engine + Drift Mode */}
      {engineStats && (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-6 flex-wrap text-sm">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${engineStats.buffer?.running ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
                <span className="text-slate-600">Buffer: {engineStats.buffer?.running ? 'Aktif' : 'Boşta'}</span>
                <span className="text-slate-500">({engineStats.buffer?.total_buffered_events ?? 0} tampondaki olay)</span>
              </div>
              <div className="flex items-center gap-2">
                <Shield className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-slate-600">{t('cm.pages_ARIPushDashboard.adaptorler')}</span>
                {(engineStats.registered_adapters || []).map((a) => (
                  <StatusBadge key={a} intent="neutral">{a}</StatusBadge>
                ))}
              </div>
              {driftMode && (
                <div className="flex items-center gap-2">
                  <Timer className="w-3.5 h-3.5 text-slate-500" />
                  <span className="text-slate-600">{t('cm.pages_ARIPushDashboard.drift_modu_sadece_bu_kiraci')}</span>
                  <button
                    type="button"
                    data-testid="drift-mode-badge"
                    onClick={toggleDriftMode}
                    className="cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 rounded-md"
                    title={t('cm.pages_ARIPushDashboard.drift_modunu_degistir_kiraciya_ozel')}
                  >
                    <StatusBadge intent={driftMode.mode === 'recovery' ? 'warning' : 'success'}>
                      {driftMode.mode === 'recovery' ? 'Kurtarma' : 'Normal'} ({driftMode.interval}s)
                    </StatusBadge>
                  </button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Operational Metrics */}
      {opMetrics && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {Object.entries(opMetrics.provider_health || {}).map(([prov, h]) => (
            <Card key={prov} data-testid={`health-card-${prov}`}>
              <CardHeader className="pb-2 pt-3 px-4">
                <CardTitle className="text-xs text-slate-500 flex items-center gap-1.5">
                  <Gauge className="w-3.5 h-3.5" /> {prov} {t('cm.pages_ARIPushDashboard.sagligi')}
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <p className="text-lg font-bold text-emerald-600">%{h.ack_rate}</p>
                    <p className="text-[10px] text-slate-500">{t('cm.pages_ARIPushDashboard.onay_orani')}</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-rose-600">%{h.error_rate}</p>
                    <p className="text-[10px] text-slate-500">{t('cm.pages_ARIPushDashboard.hata_orani')}</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-amber-600">%{h.retry_rate}</p>
                    <p className="text-[10px] text-slate-500">{t('cm.pages_ARIPushDashboard.tekrar_orani')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {Object.entries(opMetrics.performance || {}).map(([prov, p]) => (
            <Card key={`perf-${prov}`} data-testid={`perf-card-${prov}`}>
              <CardHeader className="pb-2 pt-3 px-4">
                <CardTitle className="text-xs text-slate-500 flex items-center gap-1.5">
                  <BarChart3 className="w-3.5 h-3.5" /> {prov} gecikme
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <p className="text-lg font-bold text-sky-600">{p.p50}ms</p>
                    <p className="text-[10px] text-slate-500">P50</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-amber-600">{p.p95}ms</p>
                    <p className="text-[10px] text-slate-500">P95</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-rose-600">{p.p99}ms</p>
                    <p className="text-[10px] text-slate-500">P99</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {opMetrics.queue && (
            <Card data-testid="queue-stats-card">
              <CardHeader className="pb-2 pt-3 px-4">
                <CardTitle className="text-xs text-slate-500 flex items-center gap-1.5">
                  <Inbox className="w-3.5 h-3.5" /> Kuyruk
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-3">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <p className="text-lg font-bold text-sky-600">{opMetrics.queue.queue_depth}</p>
                    <p className="text-[10px] text-slate-500">{t('cm.pages_ARIPushDashboard.kuyruk_derinligi')}</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-amber-600">{opMetrics.queue.retry_backlog}</p>
                    <p className="text-[10px] text-slate-500">{t('cm.pages_ARIPushDashboard.tekrar_yigini')}</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold text-rose-600">{opMetrics.queue.dead_letter_count}</p>
                    <p className="text-[10px] text-slate-500">{t('cm.pages_ARIPushDashboard.olu_mektuplar')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger data-testid="tab-queue" value="queue">{t('cm.pages_ARIPushDashboard.kuyruk_monitoru')}</TabsTrigger>
          <TabsTrigger data-testid="tab-outbound" value="outbound">{t('cm.pages_ARIPushDashboard.giden_istekler')}</TabsTrigger>
          <TabsTrigger data-testid="tab-drift" value="drift">Drift</TabsTrigger>
          <TabsTrigger data-testid="tab-events" value="events">Olaylar</TabsTrigger>
          <TabsTrigger data-testid="tab-harness" value="harness">Test Paneli</TabsTrigger>
        </TabsList>

        {/* Queue Tab */}
        <TabsContent value="queue" className="space-y-4">
          <div className="flex gap-3 flex-wrap">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger data-testid="status-filter" className="w-[160px] text-sm">
                <SelectValue placeholder={t('cm.pages_ARIPushDashboard.durum')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('cm.pages_ARIPushDashboard.tum_durumlar')}</SelectItem>
                <SelectItem value="pending">Bekliyor</SelectItem>
                <SelectItem value="acked">{t('cm.pages_ARIPushDashboard.onaylandi_64902')}</SelectItem>
                <SelectItem value="failed_retryable">Tekrar Denenecek</SelectItem>
                <SelectItem value="manual_review">{t('cm.pages_ARIPushDashboard.basarisiz_3260d')}</SelectItem>
              </SelectContent>
            </Select>
            <Select value={providerFilter} onValueChange={setProviderFilter}>
              <SelectTrigger data-testid="provider-filter" className="w-[180px] text-sm">
                <SelectValue placeholder={t('cm.pages_ARIPushDashboard.saglayici')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('cm.pages_ARIPushDashboard.tum_saglayicilar')}</SelectItem>
                <SelectItem value="hotelrunner">HotelRunner</SelectItem>
                <SelectItem value="exely">Exely</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm text-slate-700">{t('cm.pages_ARIPushDashboard.degisiklik_setleri')}{filteredCS.length})</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table data-testid="change-sets-table" className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 text-xs">
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.saglayici_1a787')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Kapsam</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.oda')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Tarihler</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.durum_074f4')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Deneme</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.guncellendi')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCS.length === 0 ? (
                      <tr><td colSpan={7} className="text-center py-8 text-slate-500">{t('cm.pages_ARIPushDashboard.degisiklik_seti_bulunamadi')}</td></tr>
                    ) : filteredCS.map((cs, i) => (
                      <tr key={cs.id || i} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-2.5 px-4"><StatusBadge intent="neutral">{cs.provider}</StatusBadge></td>
                        <td className="py-2.5 px-4"><ScopeChip scope={cs.change_scope} /></td>
                        <td className="py-2.5 px-4 text-slate-700 font-mono text-xs">{cs.room_type_code}{cs.rate_plan_code ? `/${cs.rate_plan_code}` : ''}</td>
                        <td className="py-2.5 px-4 text-slate-600 text-xs">{cs.date_from} → {cs.date_to}</td>
                        <td className="py-2.5 px-4"><StatusPill status={cs.status} /></td>
                        <td className="py-2.5 px-4 text-slate-600 text-xs">{cs.outbound_attempt_count}</td>
                        <td className="py-2.5 px-4 text-slate-500 text-xs">{cs.updated_at ? new Date(cs.updated_at).toLocaleString('tr-TR') : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Outbound Tab */}
        <TabsContent value="outbound" className="space-y-4">
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm text-slate-700">{t('cm.pages_ARIPushDashboard.giden_istek_kayitlari')}{outboundLogs.length})</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table data-testid="outbound-logs-table" className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 text-xs">
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.saglayici_1a787')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.islem')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.sonuc')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">HTTP</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.sure')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Zaman</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outboundLogs.length === 0 ? (
                      <tr><td colSpan={6} className="text-center py-8 text-slate-500">{t('cm.pages_ARIPushDashboard.giden_istek_kaydi_yok')}</td></tr>
                    ) : outboundLogs.map((log, i) => (
                      <tr key={log.id || i} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-2.5 px-4"><StatusBadge intent="neutral">{log.provider}</StatusBadge></td>
                        <td className="py-2.5 px-4 text-slate-600 text-xs font-mono">{log.endpoint_or_action}</td>
                        <td className="py-2.5 px-4">
                          {log.success
                            ? <CheckCircle className="w-4 h-4 text-emerald-600" />
                            : <XCircle className="w-4 h-4 text-rose-600" />}
                        </td>
                        <td className="py-2.5 px-4 text-slate-600 text-xs">{log.status_code || '-'}</td>
                        <td className="py-2.5 px-4 text-slate-600 text-xs">{log.duration_ms}ms</td>
                        <td className="py-2.5 px-4 text-slate-500 text-xs">{log.pushed_at ? new Date(log.pushed_at).toLocaleString('tr-TR') : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Drift Tab */}
        <TabsContent value="drift" className="space-y-4">
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm text-slate-700">{t('cm.pages_ARIPushDashboard.drift_durumlari')}{driftStates.length})</CardTitle>
              <CardDescription className="text-xs text-slate-500">
                {t('cm.pages_ARIPushDashboard.pms_gercegi_ile_saglayici_durumu_arasind')}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table data-testid="drift-table" className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 text-xs">
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.saglayici_1a787')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.oda_e4b47')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Tarihler</th>
                      <th className="text-left py-2.5 px-4 font-medium">Drift</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.farkli_alanlar')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">PMS Hash</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.saglayici_hash')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Son Kontrol</th>
                    </tr>
                  </thead>
                  <tbody>
                    {driftStates.length === 0 ? (
                      <tr><td colSpan={8} className="text-center py-8 text-slate-500">{t('cm.pages_ARIPushDashboard.drift_kaydi_yok_olay_tetikli_karsilastir')}</td></tr>
                    ) : driftStates.map((ds, i) => (
                      <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-2.5 px-4"><StatusBadge intent="neutral">{ds.provider}</StatusBadge></td>
                        <td className="py-2.5 px-4 text-slate-700 font-mono text-xs">{ds.room_type_code}{ds.rate_plan_code ? `/${ds.rate_plan_code}` : ''}</td>
                        <td className="py-2.5 px-4 text-slate-600 text-xs">{ds.date_from} → {ds.date_to}</td>
                        <td className="py-2.5 px-4">
                          {ds.drift_detected
                            ? <StatusBadge intent="danger">Drift</StatusBadge>
                            : <StatusBadge intent="success">OK</StatusBadge>}
                        </td>
                        <td className="py-2.5 px-4">
                          <div className="flex flex-wrap gap-1">
                            {(ds.drift_fields || []).length === 0
                              ? <span className="text-xs text-slate-400">—</span>
                              : (ds.drift_fields || []).map((f) => (
                                  <Badge key={f} variant="outline" className="text-[10px] border-rose-300 text-rose-700">
                                    {FIELD_LABEL[f] || f}
                                  </Badge>
                                ))}
                          </div>
                        </td>
                        <td className="py-2.5 px-4 text-slate-500 font-mono text-xs">{ds.pms_hash?.slice(0, 8) || '-'}</td>
                        <td className="py-2.5 px-4 text-slate-500 font-mono text-xs">{ds.provider_hash?.slice(0, 8) || '-'}</td>
                        <td className="py-2.5 px-4 text-slate-500 text-xs">{ds.last_checked_at ? new Date(ds.last_checked_at).toLocaleString('tr-TR') : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Events Tab */}
        <TabsContent value="events" className="space-y-4">
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm text-slate-700">{t('cm.pages_ARIPushDashboard.son_ari_olaylari')}{events.length})</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table data-testid="events-table" className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 text-xs">
                      <th className="text-left py-2.5 px-4 font-medium">Kaynak</th>
                      <th className="text-left py-2.5 px-4 font-medium">Tip</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.oda_e4b47')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Tarihler</th>
                      <th className="text-left py-2.5 px-4 font-medium">{t('cm.pages_ARIPushDashboard.yuk')}</th>
                      <th className="text-left py-2.5 px-4 font-medium">Zaman</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.length === 0 ? (
                      <tr><td colSpan={6} className="text-center py-8 text-slate-500">{t('cm.pages_ARIPushDashboard.henuz_olay_yok')}</td></tr>
                    ) : events.map((ev, i) => (
                      <tr key={ev.id || i} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-2.5 px-4"><StatusBadge intent="neutral">{ev.source_service}</StatusBadge></td>
                        <td className="py-2.5 px-4"><ScopeChip scope={ev.event_type} /></td>
                        <td className="py-2.5 px-4 text-slate-700 font-mono text-xs">{ev.room_type_code}{ev.rate_plan_code ? `/${ev.rate_plan_code}` : ''}</td>
                        <td className="py-2.5 px-4 text-slate-600 text-xs">{ev.date_from} → {ev.date_to}</td>
                        <td className="py-2.5 px-4 text-slate-500 text-xs font-mono max-w-[240px] truncate">{JSON.stringify(ev.payload)}</td>
                        <td className="py-2.5 px-4 text-slate-500 text-xs">{ev.created_at ? new Date(ev.created_at).toLocaleString('tr-TR') : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Test Harness Tab */}
        <TabsContent value="harness" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {['hotelrunner', 'exely'].map((provider) => (
              <Card key={provider} data-testid={`test-harness-${provider}`}>
                <CardHeader className="pb-2 pt-4 px-4 flex flex-row items-center justify-between">
                  <div>
                    <CardTitle className="text-sm text-slate-700 capitalize">{provider} {t('cm.pages_ARIPushDashboard.dogrulama')}</CardTitle>
                    <CardDescription className="text-xs text-slate-500">{t('cm.pages_ARIPushDashboard.sandbox_canli_test_kontrol_listesi')}</CardDescription>
                  </div>
                  <Button
                    data-testid={`run-test-${provider}`}
                    size="sm"
                    variant="outline"
                    onClick={() => runProviderTest(provider)}
                    disabled={testRunning === provider}
                  >
                    {testRunning === provider
                      ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> {t('cm.pages_ARIPushDashboard.calisiyor')}</>
                      : <><Play className="w-3.5 h-3.5 mr-1.5" /> {t('cm.pages_ARIPushDashboard.tumunu_calistir')}</>}
                  </Button>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  {testResults[provider]?.results ? (
                    <div className="space-y-1.5">
                      {testResults[provider].results.map((r, i) => (
                        <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded bg-slate-50 text-xs">
                          <div className="flex items-center gap-2">
                            {r.success
                              ? <CheckCircle className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                              : <XCircle className="w-3.5 h-3.5 text-rose-600 flex-shrink-0" />}
                            <span className="text-slate-700">{r.step}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-slate-500 max-w-[200px] truncate">{r.detail}</span>
                            <span className="text-slate-700">{r.duration_ms}ms</span>
                          </div>
                        </div>
                      ))}
                      {testResults[provider].summary && (
                        <div className="mt-2 pt-2 border-t border-slate-200 flex gap-3 text-xs">
                          <span className="text-emerald-700">{testResults[provider].summary.passed} {t('cm.pages_ARIPushDashboard.gecti')}</span>
                          <span className="text-rose-700">{testResults[provider].summary.failed} {t('cm.pages_ARIPushDashboard.basarisiz_f592b')}</span>
                          <span className="text-slate-500">/ toplam {testResults[provider].summary.total}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 py-4 text-center">
                      {t('cm.pages_ARIPushDashboard.dogrulama_listesini_calistirmak_icin_tum')}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default ARIPushDashboard;
