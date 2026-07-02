import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Activity, AlertTriangle, ArrowRight, Check, CheckCircle, ChevronRight, Cloud, ExternalLink, Key, Layers, Loader2, MapPin, Plug, RefreshCw, Rocket, Shield, Signal, TestTube, Wifi, WifiOff, X, Zap } from 'lucide-react';
import { useTranslation } from 'react-i18next';
const ChecklistItem = ({
  label,
  status,
  detail,
  action,
  actionLabel,
  icon: Icon
}) => {
  const {
    t
  } = useTranslation();
  const statusConfig = {
    pass: {
      color: 'bg-emerald-100 text-emerald-700 border-emerald-200',
      icon: CheckCircle,
      iconColor: 'text-emerald-500'
    },
    fail: {
      color: 'bg-red-100 text-red-700 border-red-200',
      icon: X,
      iconColor: 'text-red-500'
    },
    warn: {
      color: 'bg-amber-100 text-amber-700 border-amber-200',
      icon: AlertTriangle,
      iconColor: 'text-amber-500'
    },
    loading: {
      color: 'bg-slate-100 text-slate-500 border-slate-200',
      icon: Loader2,
      iconColor: 'text-slate-400'
    },
    pending: {
      color: 'bg-slate-50 text-slate-500 border-slate-200',
      icon: Activity,
      iconColor: 'text-slate-400'
    }
  };
  const cfg = statusConfig[status] || statusConfig.pending;
  const StatusIcon = cfg.icon;
  return <div className={`flex items-center gap-3 px-4 py-3 rounded-lg border ${cfg.color}`} data-testid={`checklist-${label?.replace(/\s+/g, '-')?.toLowerCase()}`}>
      <StatusIcon className={`w-5 h-5 flex-shrink-0 ${cfg.iconColor} ${status === 'loading' ? 'animate-spin' : ''}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-3.5 h-3.5 opacity-60" />}
          <span className="text-sm font-medium">{label}</span>
        </div>
        {detail && <p className="text-xs opacity-75 mt-0.5">{detail}</p>}
      </div>
      {action && <Button variant="ghost" size="sm" className="h-7 text-xs flex-shrink-0" onClick={action}>
          {actionLabel || 'Duzelt'}
          <ChevronRight className="w-3.5 h-3.5 ml-1" />
        </Button>}
    </div>;
};
const ScoreBar = ({
  label,
  score,
  weight
}) => {
  const {
    t
  } = useTranslation();
  const getColor = s => {
    if (s >= 80) return 'bg-emerald-500';
    if (s >= 50) return 'bg-amber-500';
    return 'bg-red-500';
  };
  return <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-600 font-medium">{label}</span>
        <div className="flex items-center gap-2">
          <span className="text-slate-400">%{weight} agirlik</span>
          <span className={`font-bold ${score >= 80 ? 'text-emerald-600' : score >= 50 ? 'text-amber-600' : 'text-red-600'}`}>{score}</span>
        </div>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${getColor(score)}`} style={{
        width: `${Math.min(score, 100)}%`
      }} />
      </div>
    </div>;
};
const BlockerCard = ({
  blocker
}) => <div className="p-3 rounded-lg border border-red-200 bg-red-50" data-testid={`blocker-${blocker.category}`}>
    <div className="flex items-center gap-2 mb-1">
      <Shield className="w-4 h-4 text-red-500" />
      <span className="text-sm font-semibold text-red-700 capitalize">{blocker.category?.replace(/_/g, ' ')}</span>
      <Badge className="bg-red-200 text-red-800 text-[10px] ml-auto">{blocker.score}/100</Badge>
    </div>
    {(blocker.issues || []).map((issue, i) => <p key={issue.id || i} className="text-xs text-red-600 ml-6">• {issue}</p>)}
  </div>;
const CATEGORY_LABELS = {
  runtime_validation: 'Runtime Dogrulama',
  provider_validation: 'Provider Dogrulama',
  incident_response: 'Incident Yanit',
  observability: 'Gozlemlenebilirlik',
  pilot_checklist: 'Pilot Kontrol Listesi',
  tenant_isolation: 'Tenant Izolasyonu',
  audit_timeline: 'Denetim Zaman Cizgisi'
};
const GoLiveReadinessCockpit = ({
  user,
  tenant,
  onLogout
}) => {
  const {
    t
  } = useTranslation();
  const navigate = useNavigate();
  const isSuperAdmin = user?.role === 'super_admin' || Array.isArray(user?.roles) && user.roles.includes('super_admin');
  const [loading, setLoading] = useState(true);
  const [connections, setConnections] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [goliveScore, setGoliveScore] = useState(null);
  const [fetchErrors, setFetchErrors] = useState([]);
  const [testingConnector, setTestingConnector] = useState(null);
  const [dryRunning, setDryRunning] = useState(false);
  const [dryRunResult, setDryRunResult] = useState(null);
  const headers = {};
  const fetchAll = useCallback(async ({
    silent = false
  } = {}) => {
    setLoading(true);
    const errors = [];
    // Geçici ağ hatasında (backend restart, ECONNREFUSED, 5xx) tek retry.
    // 4xx (auth/yetki) → retry yok. Network/5xx → 1.5sn sonra tek deneme.
    const fetchWithRetry = async url => {
      const tryOnce = () => axios.get(url, {
        headers
      }).then(r => r.data);
      try {
        return await tryOnce();
      } catch (firstErr) {
        const status = firstErr?.response?.status;
        if (status && status >= 400 && status < 500) throw firstErr;
        await new Promise(r => setTimeout(r, 1500));
        return await tryOnce();
      }
    };
    try {
      const [connRes, dashRes, scoreRes] = await Promise.allSettled([fetchWithRetry('/channel-manager/connections/overview'), fetchWithRetry('/channel-manager/v2/dashboard/overview'), fetchWithRetry('/validation/golive-score')]);
      if (connRes.status === 'fulfilled') {
        setConnections(connRes.value);
      } else {
        errors.push('Bağlantı verileri');
        setConnections(null);
      }
      if (dashRes.status === 'fulfilled') {
        setDashboard(dashRes.value);
      } else {
        errors.push('Dashboard verileri');
        setDashboard(null);
      }
      if (scoreRes.status === 'fulfilled') {
        setGoliveScore(scoreRes.value?.data || scoreRes.value);
      } else {
        errors.push('Hazırlık skoru');
        setGoliveScore(null);
      }
      setFetchErrors(errors);
      if (errors.length > 0) {
        console.error('[GoLive Cockpit] partial fetch failures:', {
          connections: connRes.reason?.response?.status || connRes.reason?.message,
          dashboard: dashRes.reason?.response?.status || dashRes.reason?.message,
          score: scoreRes.reason?.response?.status || scoreRes.reason?.message
        });
        if (!silent) toast.error(`Yüklenemedi: ${errors.join(', ')}`);
      }
    } catch (err) {
      console.error('[GoLive Cockpit] fetchAll fatal:', err);
      if (!silent) toast.error('Veriler yüklenirken hata oluştu');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- headers stable per mount
  }, []);
  useEffect(() => {
    fetchAll({
      silent: true
    });
  }, [fetchAll]);
  const handleTestConnection = async connectorId => {
    setTestingConnector(connectorId);
    try {
      const {
        data
      } = await axios.post(`/channel-manager/v2/connectors/${connectorId}/test`, {}, {
        headers
      });
      if (data?.success) {
        toast.success('Bağlantı testi basarili');
      } else {
        toast.error(data?.detail || 'Bağlantı testi başarısız');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Bağlantı testi sirasinda hata');
    } finally {
      setTestingConnector(null);
      fetchAll();
    }
  };
  const handleDryRun = async () => {
    setDryRunning(true);
    setDryRunResult(null);
    try {
      const {
        data
      } = await axios.post('/channel/hotelrunner-v2/dry-run/ari-push', {
        simulate_failure: false
      }, {
        headers
      });
      setDryRunResult(data);
      if (data?.success) {
        toast.success('Dry run başarılı');
      } else {
        toast.error('Dry run başarısız');
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Dry run sirasinda hata');
    } finally {
      setDryRunning(false);
    }
  };
  const kpis = dashboard?.kpis || {};
  const mapping = dashboard?.mapping_visibility || {};
  const connectors = dashboard?.connectors || [];
  const score = goliveScore?.overall_score ?? null;
  const categories = goliveScore?.categories || {};
  const blockers = goliveScore?.blockers || [];
  const goLiveReady = goliveScore?.go_live_ready === true;
  const providers = connections?.providers || [];
  const connectedProviders = providers.filter(p => p.connected);
  const hasCredentials = connectedProviders.length > 0;
  const hasActiveConnectors = connectors.some(c => c.status === 'active' || c.status === 'healthy') || connectedProviders.length > 0;
  const noMappingConflicts = (mapping.total_conflicts || 0) === 0;
  const reviewQueueClear = (kpis.review_queue || 0) === 0;
  const noRecentFailures = (kpis.failed_imports || 0) === 0 && (kpis.wire_failures_24h || 0) === 0;
  if (loading && !dashboard) {
    return <>
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-[#C09D63]" />
        </div>
      </>;
  }
  return <>
      <div className="max-w-6xl mx-auto space-y-6" data-testid="golive-cockpit">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#C09D63]/10 flex items-center justify-center">
              <Rocket className="w-5 h-5 text-[#C09D63]" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900" style={{
              fontFamily: 'Manrope, sans-serif'
            }}>
                Go-Live Hazirlik Merkezi
              </h1>
              <p className="text-sm text-slate-500">Canli yayina gecis oncesi kontrol ve hazirlik durumu</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => navigate('/cm-dashboard')}>
              <Cloud className="w-4 h-4 mr-1.5 text-blue-500" />
              CM Dashboard
            </Button>
            <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
              {t('cm.pages_GoLiveReadinessCockpit.yenile')}
            </Button>
          </div>
        </div>

        {fetchErrors.length > 0 && <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-lg text-sm" data-testid="fetch-errors">
            <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
            <span className="text-amber-700">{t('cm.pages_GoLiveReadinessCockpit.bazi_veriler_yuklenemedi')} {fetchErrors.join(', ')}. Sayfa kismi veriyle gosteriliyor.</span>
          </div>}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Card data-testid="onboarding-checklist">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-[#C09D63]" />
                  <CardTitle className="text-base" style={{
                  fontFamily: 'Manrope, sans-serif'
                }}>
                    Onboarding Kontrol Listesi
                  </CardTitle>
                  <Badge className="ml-auto bg-slate-100 text-slate-600 text-xs">
                    {[hasCredentials, hasActiveConnectors, noMappingConflicts, reviewQueueClear, noRecentFailures].filter(Boolean).length}/5 tamamlandi
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                <ChecklistItem label={t('cm.pages_GoLiveReadinessCockpit.credential_baglanti')} icon={Key} status={hasCredentials && hasActiveConnectors ? 'pass' : hasCredentials ? 'warn' : 'fail'} detail={hasActiveConnectors ? `${connectedProviders.length} aktif bağlantı (${connectedProviders.map(p => p.display_name || p.provider).join(', ')})` : hasCredentials ? 'Connector aktif değil' : 'Bağlantı bulunamadı'} action={isSuperAdmin ? () => navigate('/channel-connections') : undefined} actionLabel="Baglantilari Yonet" />
                <ChecklistItem label="Provider Dogrulama" icon={Signal} status={hasActiveConnectors ? 'pass' : 'fail'} detail={hasActiveConnectors ? 'Provider baglantisi dogrulandi' : 'Henüz dogrulanmadi'} action={connectors[0] ? () => handleTestConnection(connectors[0].id) : undefined} actionLabel={testingConnector ? 'Test ediliyor...' : 'Test Et'} />
                <ChecklistItem label="Mapping Cakismasi" icon={Layers} status={noMappingConflicts ? 'pass' : 'fail'} detail={noMappingConflicts ? `${mapping.connectors_with_mappings || 0} connector eslesmis` : `${mapping.total_conflicts} cakisma mevcut`} action={!noMappingConflicts ? () => navigate('/room-mapping-wizard') : undefined} actionLabel="Mapping Sihirbazi" />
                <ChecklistItem label="Inceleme Kuyrugu" icon={Activity} status={reviewQueueClear ? 'pass' : 'warn'} detail={reviewQueueClear ? 'Kuyruk temiz' : `${kpis.review_queue} ogeleri inceleme bekliyor`} action={!reviewQueueClear && isSuperAdmin ? () => navigate('/channel-ops') : undefined} actionLabel="Incele" />
                <ChecklistItem label="Son Hatalar" icon={AlertTriangle} status={noRecentFailures ? 'pass' : 'fail'} detail={noRecentFailures ? 'Son 24 saatte başarısız işlem yok' : `${kpis.failed_imports || 0} başarısız import, ${kpis.wire_failures_24h || 0} wire hatası`} action={!noRecentFailures && isSuperAdmin ? () => navigate('/channel-ops') : undefined} actionLabel="Detay" />
              </CardContent>
            </Card>

            <Card data-testid="action-panel">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <TestTube className="w-4 h-4 text-blue-500" />
                  <CardTitle className="text-base" style={{
                  fontFamily: 'Manrope, sans-serif'
                }}>
                    Test & Dogrulama
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <Button variant="outline" className="h-auto py-3 flex flex-col items-center gap-1.5" onClick={connectors[0] ? () => handleTestConnection(connectors[0].id) : undefined} disabled={!connectors[0] || testingConnector} data-testid="btn-test-connection">
                    {testingConnector ? <Loader2 className="w-5 h-5 animate-spin text-blue-500" /> : <Wifi className="w-5 h-5 text-blue-500" />}
                    <span className="text-xs font-medium">Test Connection</span>
                    <span className="text-[10px] text-slate-400">{t('cm.pages_GoLiveReadinessCockpit.baglanti_dogrulamasi')}</span>
                  </Button>

                  <Button variant="outline" className="h-auto py-3 flex flex-col items-center gap-1.5" onClick={handleDryRun} disabled={dryRunning || !hasActiveConnectors} data-testid="btn-dry-run">
                    {dryRunning ? <Loader2 className="w-5 h-5 animate-spin text-indigo-500" /> : <TestTube className="w-5 h-5 text-indigo-500" />}
                    <span className="text-xs font-medium">Dry Run</span>
                    <span className="text-[10px] text-slate-400">ARI push simulasyonu</span>
                  </Button>

                  <Button variant="outline" className="h-auto py-3 flex flex-col items-center gap-1.5" onClick={() => navigate('/room-mapping-wizard')} data-testid="btn-mapping-wizard">
                    <Layers className="w-5 h-5 text-amber-500" />
                    <span className="text-xs font-medium">Mapping Sihirbazi</span>
                    <span className="text-[10px] text-slate-400">{t('cm.pages_GoLiveReadinessCockpit.oda_eslestirmesi')}</span>
                  </Button>
                </div>

                {dryRunResult && <div className={`mt-3 p-3 rounded-lg border text-sm ${dryRunResult.success ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-red-50 border-red-200 text-red-700'}`} data-testid="dry-run-result">
                    <div className="flex items-center gap-2">
                      {dryRunResult.success ? <CheckCircle className="w-4 h-4" /> : <X className="w-4 h-4" />}
                      <span className="font-medium">{dryRunResult.success ? 'Dry run başarılı' : 'Dry run başarısız'}</span>
                    </div>
                    {dryRunResult.message && <p className="text-xs mt-1 opacity-75">{dryRunResult.message}</p>}
                  </div>}
              </CardContent>
            </Card>

            {blockers.length > 0 && <Card data-testid="blockers-panel">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-red-500" />
                    <CardTitle className="text-base text-red-700" style={{
                  fontFamily: 'Manrope, sans-serif'
                }}>
                      Blocker&apos;lar ({blockers.length})
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  {blockers.map((b, i) => <BlockerCard key={b.id || i} blocker={b} />)}
                </CardContent>
              </Card>}
          </div>

          <div className="space-y-4">
            <Card data-testid="readiness-score">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Rocket className="w-4 h-4 text-[#C09D63]" />
                  <CardTitle className="text-base" style={{
                  fontFamily: 'Manrope, sans-serif'
                }}>
                    Hazirlik Skoru
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-col items-center py-3">
                  <div className={`w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold text-white ${score === null ? 'bg-slate-300' : score >= 75 ? 'bg-emerald-500' : score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}>
                    {score !== null ? score : '—'}
                  </div>
                  <p className="text-sm font-medium text-slate-700 mt-2">
                    {score === null ? 'Hesaplanamadi' : goliveScore?.maturity_name || 'Bilinmiyor'}
                  </p>
                  <Badge className={`mt-1 text-xs ${goLiveReady ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                    {goLiveReady ? 'Canli Yayina Hazir' : 'Henüz Hazir Degil'}
                  </Badge>
                </div>

                <div className="space-y-3 pt-3 border-t">
                  {Object.entries(categories).map(([key, cat]) => <ScoreBar key={key} label={CATEGORY_LABELS[key] || key} score={cat.score || 0} weight={cat.weight || 0} />)}
                  {Object.keys(categories).length === 0 && <p className="text-xs text-slate-400 text-center py-2">{t('cm.pages_GoLiveReadinessCockpit.skor_verileri_mevcut_degil')}</p>}
                </div>
              </CardContent>
            </Card>

            <Card data-testid="connector-summary">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Plug className="w-4 h-4 text-blue-500" />
                  <CardTitle className="text-base" style={{
                  fontFamily: 'Manrope, sans-serif'
                }}>
                    Connector Durumu
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {connectors.length === 0 ? <div className="text-center py-4">
                    <WifiOff className="w-6 h-6 text-slate-300 mx-auto mb-2" />
                    <p className="text-xs text-slate-400">{t('cm.pages_GoLiveReadinessCockpit.aktif_connector_bulunamadi')}</p>
                    <Button variant="ghost" size="sm" className="mt-2 text-xs" onClick={() => navigate('/channel-connections')}>
                      {t('cm.pages_GoLiveReadinessCockpit.baglanti_ekle')} <ArrowRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </div> : connectors.map((c, i) => <div key={c.id || i} className="flex items-center gap-2 p-2 rounded-lg border bg-white text-sm">
                    <div className={`w-2 h-2 rounded-full ${c.status === 'active' ? 'bg-emerald-500' : c.status === 'error' ? 'bg-red-500' : 'bg-amber-500'}`} />
                    <div className="flex-1 min-w-0">
                      <span className="font-medium text-slate-700 truncate block">{c.display_name || c.id}</span>
                      <span className="text-[10px] text-slate-400">{c.provider}</span>
                    </div>
                    <Button variant="ghost" size="sm" className="h-6 text-[10px] px-2" onClick={() => handleTestConnection(c.id)} disabled={testingConnector === c.id}>
                      {testingConnector === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Test'}
                    </Button>
                  </div>)}
              </CardContent>
            </Card>

            <div className="sticky bottom-4">
              <Button className={`w-full h-12 text-sm font-semibold ${goLiveReady ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-slate-200 text-slate-500 cursor-not-allowed'}`} disabled={!goLiveReady} onClick={() => goLiveReady && toast.success('Go-Live aktivasyonu başlatıldı!')} data-testid="go-live-button">
                <Rocket className="w-4.5 h-4.5 mr-2" />
                {goLiveReady ? 'Canli Yayina Gec' : `Hazir Degil — ${blockers.length} blocker`}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </>;
};
export default GoLiveReadinessCockpit;