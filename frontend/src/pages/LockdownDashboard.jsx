import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  Shield, ShieldCheck, ShieldAlert,
  Activity, AlertTriangle, CheckCircle, XCircle,
  RefreshCw, Loader2, ArrowRightLeft,
  FileWarning, Clock, TrendingUp, Eye,
  Server, Database, Zap,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const POLL_MS = 30000;

const StatusDot = ({ status }) => {
  const { t } = useTranslation();
  const colors = {
    healthy: 'bg-emerald-500',
    degraded: 'bg-amber-500',
    critical: 'bg-rose-500 animate-pulse',
  };
  return (
    <span
      data-testid={`status-dot-${status}`}
      className={`inline-block w-2.5 h-2.5 rounded-full ${colors[status] || colors.degraded}`}
    />
  );
};

const RatePill = ({ label, value, good }) => (
  <div className="flex items-center justify-between py-1.5">
    <span className="text-xs text-slate-600">{label}</span>
    <span className={`text-sm font-mono font-semibold ${
      good ? 'text-emerald-700' : value > 0 ? 'text-rose-700' : 'text-slate-500'
    }`}>
      {typeof value === 'number' ? `${value}%` : value}
    </span>
  </div>
);

const ProviderBadge = ({ name }) => (
  <StatusBadge intent="neutral">{name}</StatusBadge>
);

export default function LockdownDashboard({ user, tenant }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const [status, setStatus] = useState(null);
  const [ingestMetrics, setIngestMetrics] = useState(null);
  const [lineageMetrics, setLineageMetrics] = useState(null);
  const [reconMetrics, setReconMetrics] = useState(null);
  const [mappingHealth, setMappingHealth] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [truthTable, setTruthTable] = useState(null);
  const [errorBanner, setErrorBanner] = useState(null);

  const propertyId =
    tenant?.hotel_id || tenant?.property_id || user?.property_id || user?.hotel_id || null;

  const intervalRef = useRef(null);

  const fetchAll = useCallback(async (nocache = false) => {
    const buildUrl = (path, extra = {}) => {
      const sp = new URLSearchParams();
      if (nocache) sp.set('nocache', 'true');
      Object.entries(extra).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
      });
      const qs = sp.toString();
      return qs ? `${path}?${qs}` : path;
    };

    const calls = [
      ['Sistem durumu', axios.get(buildUrl('/lockdown/status'))],
      ['Ingest metrikleri', axios.get(buildUrl('/lockdown/metrics/ingest', { hours: 24 }))],
      ['Lineage metrikleri', axios.get(buildUrl('/lockdown/metrics/lineage'))],
      ['Reconciliation metrikleri', axios.get(buildUrl('/lockdown/metrics/reconciliation'))],
      ['Mapping sağlığı', axios.get(buildUrl('/lockdown/health/mapping', { property_id: propertyId }))],
      ['Sağlayıcı yetenekleri', axios.get(buildUrl('/lockdown/providers/capabilities'))],
      ['Truth table', axios.get(buildUrl('/lockdown/reconciliation/truth-table'))],
    ];
    const setters = [setStatus, setIngestMetrics, setLineageMetrics, setReconMetrics,
                     setMappingHealth, setCapabilities, setTruthTable];

    const results = await Promise.allSettled(calls.map(([, p]) => p));

    const failed = [];
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') {
        setters[i](r.value.data);
      } else {
        const code = r.reason?.response?.status;
        const detail = r.reason?.response?.data?.detail || r.reason?.message || 'bilinmeyen hata';
        failed.push(`${calls[i][0]}: ${code ? code + ' — ' : ''}${detail}`);
      }
    });

    if (failed.length > 0) {
      setErrorBanner(failed.join(' • '));
      // Per-failure toast (max 3 to avoid spam)
      failed.slice(0, 3).forEach((m) => toast.error(m));
    } else {
      setErrorBanner(null);
    }

    setLastUpdated(new Date());
    setLoading(false);
    setRefreshing(false);
  }, [propertyId]);

  useEffect(() => { fetchAll(false); }, [fetchAll]);

  // Auto-refresh polling, paused when tab hidden
  useEffect(() => {
    if (!autoRefresh) return;
    const tick = () => {
      if (document.visibilityState === 'visible') {
        fetchAll(true);
      }
    };
    intervalRef.current = setInterval(tick, POLL_MS);
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh, fetchAll]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchAll(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-slate-500" />
      </div>
    );
  }

  const overallStatus = status?.status || 'degraded';
  const isReady = mappingHealth?.overall_production_ready || false;
  const checks = status?.checks || {};
  const rates = ingestMetrics?.rates || {};
  const totals = ingestMetrics?.totals || {};
  const lin = lineageMetrics || {};
  const recon = reconMetrics || {};

  const HeaderIcon = overallStatus === 'healthy' ? ShieldCheck : ShieldAlert;

  return (
    <div className="space-y-5 p-4 lg:p-6 max-w-[1400px] mx-auto">

      <PageHeader
        icon={HeaderIcon}
        title={t('cm.pages_LockdownDashboard.cekirdek_kilitlenme')}
        subtitle={t('cm.pages_LockdownDashboard.uretime_hazirlik_panosu')}
        actions={
          <>
            <StatusBadge intent={isReady ? 'success' : 'danger'} icon={Shield}>
              {isReady ? 'ÜRETİME HAZIR' : 'HAZIR DEĞİL'}
            </StatusBadge>
            <Button
              data-testid="lockdown-autorefresh-toggle"
              variant="outline"
              size="sm"
              onClick={() => setAutoRefresh((v) => !v)}
              className={autoRefresh ? '' : 'opacity-60'}
              title={autoRefresh ? 'Otomatik yenileme açık (30s)' : 'Otomatik yenileme kapalı'}
            >
              <Activity className={`w-4 h-4 mr-1.5 ${autoRefresh ? 'text-emerald-600' : 'text-slate-400'}`} />
              {autoRefresh ? 'Oto-yenile: Açık' : 'Oto-yenile: Kapalı'}
            </Button>
            <Button
              data-testid="lockdown-refresh-btn"
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
            >
              <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
              {t('cm.pages_LockdownDashboard.yenile')}
            </Button>
          </>
        }
      />

      {errorBanner && (
        <Card className="border-l-4 border-l-rose-500">
          <CardContent className="p-3 flex items-start gap-2 text-sm">
            <AlertTriangle className="w-4 h-4 text-rose-600 mt-0.5 flex-shrink-0" />
            <div className="flex-1 text-slate-700">{errorBanner}</div>
            <Button variant="outline" size="sm" onClick={() => setErrorBanner(null)}>{t('cm.pages_LockdownDashboard.kapat')}</Button>
          </CardContent>
        </Card>
      )}

      {/* System Health Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {['ingest', 'mapping', 'reconciliation'].map((key) => {
          const check = checks[key] || {};
          const st = check.status || 'degraded';
          const icons = { ingest: Zap, mapping: Database, reconciliation: ArrowRightLeft };
          const Icon = icons[key];
          const labels = {
            ingest: 'Ingest Hattı',
            mapping: 'Eşleme Sağlığı',
            reconciliation: 'Mutabakat',
          };
          return (
            <Card
              key={key}
              data-testid={`health-card-${key}`}
              className={`bg-white border-l-4 ${st === 'healthy' ? 'border-l-emerald-500' : 'border-l-rose-500'}`}
            >
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Icon className={`w-4 h-4 ${st === 'healthy' ? 'text-emerald-600' : 'text-rose-600'}`} />
                    <span className="text-sm font-semibold text-slate-800">{labels[key]}</span>
                  </div>
                  <StatusDot status={st} />
                </div>
                <div className="space-y-1 text-xs text-slate-600">
                  {key === 'ingest' && (
                    <>
                      <div className="flex justify-between"><span>24s Olay</span><span className="text-slate-800 font-medium">{check.events_24h ?? 0}</span></div>
                      <div className="flex justify-between"><span>{t('cm.pages_LockdownDashboard.basarisiz')}</span><span className={check.failed_24h > 0 ? 'text-rose-700 font-medium' : 'text-emerald-700 font-medium'}>{check.failed_24h ?? 0}</span></div>
                      <div className="flex justify-between"><span>{t('cm.pages_LockdownDashboard.hata_orani')}</span><span className={check.failure_rate_pct > 0 ? 'text-rose-700 font-medium' : 'text-emerald-700 font-medium'}>{check.failure_rate_pct ?? 0}%</span></div>
                    </>
                  )}
                  {key === 'mapping' && (
                    <>
                      <div className="flex justify-between"><span>{t('cm.pages_LockdownDashboard.aktif_esleme')}</span><span className="text-slate-800 font-medium">{check.active_room_mappings ?? 0}</span></div>
                      <div className="flex justify-between"><span>{t('cm.pages_LockdownDashboard.kirik_esleme')}</span><span className={check.broken_room_mappings > 0 ? 'text-rose-700 font-medium' : 'text-emerald-700 font-medium'}>{check.broken_room_mappings ?? 0}</span></div>
                    </>
                  )}
                  {key === 'reconciliation' && (
                    <>
                      <div className="flex justify-between"><span>{t('cm.pages_LockdownDashboard.acik_vakalar')}</span><span className={check.open_cases > 0 ? 'text-amber-700 font-medium' : 'text-emerald-700 font-medium'}>{check.open_cases ?? 0}</span></div>
                      <div className="flex justify-between"><span>Kritik Vakalar</span><span className={check.critical_cases > 0 ? 'text-rose-700 font-medium' : 'text-emerald-700 font-medium'}>{check.critical_cases ?? 0}</span></div>
                      <div className="flex justify-between"><span>{t('cm.pages_LockdownDashboard.eslesmemis')}</span><span className="text-slate-800 font-medium">{check.unreconciled_lineages ?? 0}</span></div>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard data-testid="metric-total-events" intent="info" icon={Activity}
          label={t('cm.pages_LockdownDashboard.toplam_olay_24s')} value={totals.total_events ?? 0} />
        <KpiCard data-testid="metric-duplicate-rate" intent={(rates.duplicate_rate_pct ?? 0) > 10 ? 'danger' : 'warning'} icon={FileWarning}
          label={t('cm.pages_LockdownDashboard.duplikat_orani')} value={`${rates.duplicate_rate_pct ?? 0}%`} />
        <KpiCard data-testid="metric-stale-rate" intent={(rates.stale_rate_pct ?? 0) > 5 ? 'danger' : 'warning'} icon={Clock}
          label={t('cm.pages_LockdownDashboard.stale_orani')} value={`${rates.stale_rate_pct ?? 0}%`} />
        <KpiCard data-testid="metric-success-rate" intent="success" icon={CheckCircle}
          label={t('cm.pages_LockdownDashboard.basari_orani')} value={`${rates.success_rate_pct ?? 0}%`} />
        <KpiCard data-testid="metric-total-lineages" intent="info" icon={TrendingUp}
          label={t('cm.pages_LockdownDashboard.toplam_lineage')} value={lin.total_lineages ?? 0} />
        <KpiCard data-testid="metric-unreconciled" intent={(lin.unreconciled ?? 0) > 0 ? 'danger' : 'neutral'} icon={AlertTriangle}
          label={t('cm.pages_LockdownDashboard.eslesmemis_5b18f')} value={lin.unreconciled ?? 0} />
      </div>

      {/* Ingest Pipeline Detail + Lineage by Status */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card data-testid="ingest-detail-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Zap className="w-4 h-4 text-sky-600" />
              {t('cm.pages_LockdownDashboard.ingest_hatti_son_24_saat')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-0.5">
            <RatePill label={t('cm.pages_LockdownDashboard.islenen')} value={rates.success_rate_pct ?? 0} good={true} />
            <RatePill label="Duplikat" value={rates.duplicate_rate_pct ?? 0} good={false} />
            <RatePill label={t('cm.pages_LockdownDashboard.stale_eski')} value={rates.stale_rate_pct ?? 0} good={false} />
            <RatePill label={t('cm.pages_LockdownDashboard.basarisiz_3260d')} value={rates.failure_rate_pct ?? 0} good={false} />
            <div className="border-t border-slate-200 mt-2 pt-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-600 font-medium">{t('cm.pages_LockdownDashboard.karar_dagilimi')}</span>
              </div>
              {ingestMetrics?.decisions && Object.entries(ingestMetrics.decisions).length > 0 ? (
                Object.entries(ingestMetrics.decisions).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between py-0.5">
                    <span className="text-xs text-slate-600 capitalize">{key}</span>
                    <span className="text-xs font-mono text-slate-800">{val}</span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-slate-400 py-1">Karar verisi yok</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card data-testid="lineage-detail-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Database className="w-4 h-4 text-indigo-600" />
              {t('cm.pages_LockdownDashboard.rezervasyon_lineage')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-slate-600">{t('cm.pages_LockdownDashboard.toplam')}</span>
                <span className="text-slate-800 font-semibold">{lin.total_lineages ?? 0}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-600">{t('cm.pages_LockdownDashboard.eslesmis')}</span>
                <span className="text-emerald-700 font-semibold">{lin.reconciled ?? 0}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-600">{t('cm.pages_LockdownDashboard.eslesmemis_5b18f')}</span>
                <span className={`font-semibold ${(lin.unreconciled ?? 0) > 0 ? 'text-rose-700' : 'text-emerald-700'}`}>
                  {lin.unreconciled ?? 0}
                </span>
              </div>
            </div>

            {lin.by_status && Object.keys(lin.by_status).length > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-200">
                <span className="text-xs text-slate-600 font-medium mb-1 block">{t('cm.pages_LockdownDashboard.duruma_gore')}</span>
                {Object.entries(lin.by_status).map(([st, cnt]) => (
                  <div key={st} className="flex justify-between py-0.5">
                    <span className="text-xs text-slate-600 capitalize">{st}</span>
                    <span className="text-xs font-mono text-slate-800">{cnt}</span>
                  </div>
                ))}
              </div>
            )}

            {lin.by_provider && Object.keys(lin.by_provider).length > 0 && (
              <div className="mt-3 pt-3 border-t border-slate-200">
                <span className="text-xs text-slate-600 font-medium mb-1 block">{t('cm.pages_LockdownDashboard.saglayiciya_gore')}</span>
                {Object.entries(lin.by_provider).map(([prov, cnt]) => (
                  <div key={prov} className="flex items-center justify-between py-0.5">
                    <ProviderBadge name={prov} />
                    <span className="text-xs font-mono text-slate-800">{cnt}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Mapping Health per Provider */}
      {mappingHealth?.mapping_health && mappingHealth.mapping_health.length > 0 && (
        <Card data-testid="mapping-health-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Database className="w-4 h-4 text-sky-600" />
              {t('cm.pages_LockdownDashboard.esleme_sagligi')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {mappingHealth.mapping_health.map((mh, i) => (
                <div key={i} className="border border-slate-200 rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <ProviderBadge name={mh.provider} />
                    <StatusBadge intent={mh.is_production_ready ? 'success' : 'danger'}>
                      {mh.is_production_ready ? 'Hazır' : 'Hazır Değil'}
                    </StatusBadge>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          mh.overall_completeness_pct === 100 ? 'bg-emerald-500' :
                          mh.overall_completeness_pct > 80 ? 'bg-amber-500' : 'bg-rose-500'
                        }`}
                        style={{ width: `${mh.overall_completeness_pct || 0}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-slate-800 w-10 text-right">
                      {mh.overall_completeness_pct ?? 0}%
                    </span>
                  </div>
                  {mh.room_mapping && (
                    <div className="text-xs text-slate-600 grid grid-cols-3 gap-1">
                      <span>{t('cm.pages_LockdownDashboard.oda')} {mh.room_mapping.total ?? 0}</span>
                      <span className={mh.room_mapping.broken > 0 ? 'text-rose-700 font-medium' : ''}>
                        {t('cm.pages_LockdownDashboard.kirik')} {mh.room_mapping.broken ?? 0}
                      </span>
                      <span className={mh.room_mapping.inactive > 0 ? 'text-amber-700 font-medium' : ''}>
                        {t('cm.pages_LockdownDashboard.pasif')} {mh.room_mapping.inactive ?? 0}
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Reconciliation Detail */}
      <Card data-testid="reconciliation-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
            <ArrowRightLeft className="w-4 h-4 text-amber-600" />
            Mutabakat
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="text-center p-2 rounded-lg bg-slate-50">
              <p data-testid="recon-total" className="text-lg font-bold text-slate-800">{recon.total_cases ?? 0}</p>
              <p className="text-[10px] text-slate-600">{t('cm.pages_LockdownDashboard.toplam_vaka')}</p>
            </div>
            <div className="text-center p-2 rounded-lg bg-slate-50">
              <p data-testid="recon-open" className={`text-lg font-bold ${(recon.open_cases ?? 0) > 0 ? 'text-amber-700' : 'text-emerald-700'}`}>
                {recon.open_cases ?? 0}
              </p>
              <p className="text-[10px] text-slate-600">{t('cm.pages_LockdownDashboard.acik')}</p>
            </div>
            <div className="text-center p-2 rounded-lg bg-slate-50">
              <p data-testid="recon-resolved" className="text-lg font-bold text-emerald-700">{recon.resolved_cases ?? 0}</p>
              <p className="text-[10px] text-slate-600">{t('cm.pages_LockdownDashboard.cozulmus')}</p>
            </div>
            <div className="text-center p-2 rounded-lg bg-slate-50">
              <p className={`text-lg font-bold ${recon.oldest_unresolved_age_hours ? 'text-rose-700' : 'text-slate-500'}`}>
                {recon.oldest_unresolved_age_hours ? `${recon.oldest_unresolved_age_hours}s` : '-'}
              </p>
              <p className="text-[10px] text-slate-600">{t('cm.pages_LockdownDashboard.en_eski_acik_saat')}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Provider Capabilities */}
      {capabilities?.providers && (
        <Card data-testid="capabilities-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Server className="w-4 h-4 text-indigo-600" />
              {t('cm.pages_LockdownDashboard.saglayici_yetenek_matrisi')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-2 text-slate-500 font-medium">{t('cm.pages_LockdownDashboard.saglayici')}</th>
                    <th className="text-left py-2 text-slate-500 font-medium">Ingest</th>
                    <th className="text-left py-2 text-slate-500 font-medium">ARI Push</th>
                    <th className="text-center py-2 text-slate-500 font-medium">Delta</th>
                    <th className="text-center py-2 text-slate-500 font-medium">{t('cm.pages_LockdownDashboard.ack_uygulandi')}</th>
                    <th className="text-right py-2 text-slate-500 font-medium">{t('cm.pages_LockdownDashboard.hiz_siniri')}</th>
                    <th className="text-right py-2 text-slate-500 font-medium">Tekrar</th>
                  </tr>
                </thead>
                <tbody>
                  {capabilities.providers.map((p) => (
                    <tr key={p.provider} className="border-b border-slate-100">
                      <td className="py-2"><ProviderBadge name={p.provider} /></td>
                      <td className="py-2 text-slate-700">{p.reservation?.ingest_type}</td>
                      <td className="py-2 text-slate-700">{p.ari?.push_behavior}</td>
                      <td className="py-2 text-center">
                        {p.ari?.supports_delta_push
                          ? <CheckCircle className="w-3.5 h-3.5 text-emerald-600 inline" />
                          : <XCircle className="w-3.5 h-3.5 text-slate-400 inline" />
                        }
                      </td>
                      <td className="py-2 text-center">
                        {p.consistency?.ack_means_applied
                          ? <CheckCircle className="w-3.5 h-3.5 text-emerald-600 inline" />
                          : <XCircle className="w-3.5 h-3.5 text-slate-400 inline" />
                        }
                      </td>
                      <td className="py-2 text-right text-slate-700">{p.rate_limits?.requests_per_minute}/dk</td>
                      <td className="py-2 text-right text-slate-700">{p.retry_policy?.max_attempts}x</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Truth Table */}
      {truthTable?.truth_table && (
        <Card data-testid="truth-table-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <Eye className="w-4 h-4 text-indigo-600" />
              {t('cm.pages_LockdownDashboard.mutabakat_dogruluk_tablosu')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-2 text-slate-500 font-medium">Drift Tipi</th>
                    <th className="text-left py-2 text-slate-500 font-medium">{t('cm.pages_LockdownDashboard.altin_kaynak')}</th>
                    <th className="text-left py-2 text-slate-500 font-medium">{t('cm.pages_LockdownDashboard.cozum')}</th>
                    <th className="text-center py-2 text-slate-500 font-medium">{t('cm.pages_LockdownDashboard.oto_iyilestirme')}</th>
                  </tr>
                </thead>
                <tbody>
                  {truthTable.truth_table.map((row, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-1.5">
                        <Badge variant="outline" className="text-[10px] border-slate-300 text-slate-700">
                          {row.drift_type}
                        </Badge>
                      </td>
                      <td className="py-1.5 text-slate-700">{row.gold_source}</td>
                      <td className="py-1.5">
                        <StatusBadge
                          intent={
                            row.resolution === 'safe_auto_heal' ? 'success' :
                            row.resolution === 'manual_review' ? 'danger' : 'warning'
                          }
                        >
                          {row.resolution}
                        </StatusBadge>
                      </td>
                      <td className="py-1.5 text-center">
                        {row.can_auto_heal
                          ? <CheckCircle className="w-3.5 h-3.5 text-emerald-600 inline" />
                          : <XCircle className="w-3.5 h-3.5 text-slate-400 inline" />
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-[11px] text-slate-500 text-right">
        {t('cm.pages_LockdownDashboard.son_guncelleme')} {lastUpdated ? lastUpdated.toLocaleString('tr-TR') : '-'}
        {autoRefresh && <span className="ml-2 text-slate-400">• 30s'de bir otomatik yenilenir</span>}
      </p>
    </div>
  );
}
