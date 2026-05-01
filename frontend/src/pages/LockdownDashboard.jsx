import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Shield, ShieldCheck, ShieldAlert, ShieldX,
  Activity, AlertTriangle, CheckCircle, XCircle,
  RefreshCw, Loader2, ArrowRightLeft, Gauge,
  FileWarning, Clock, TrendingUp, Eye,
  Server, Database, Zap, Lock
} from 'lucide-react';

const API = "";

// ─── Status Indicator ────────────────────────────────────────
const StatusDot = ({ status }) => {
  const colors = {
    healthy: 'bg-emerald-500 shadow-emerald-500/50',
    degraded: 'bg-amber-500 shadow-amber-500/50',
    critical: 'bg-red-500 shadow-red-500/50 animate-pulse',
  };
  return (
    <span
      data-testid={`status-dot-${status}`}
      className={`inline-block w-2.5 h-2.5 rounded-full shadow-lg ${colors[status] || colors.degraded}`}
    />
  );
};

// ─── Metric Card ─────────────────────────────────────────────
const MetricCard = ({ title, value, icon: Icon, color, alert, testId }) => (
  <Card data-testid={testId} className={`bg-white border-gray-200 ${alert ? 'border-red-500/40 ring-1 ring-red-500/20' : ''}`}>
    <CardContent className="p-4 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-gray-500 font-medium truncate">{title}</p>
        <p className={`text-lg font-bold ${alert ? 'text-red-400' : 'text-gray-900'}`}>{value}</p>
      </div>
    </CardContent>
  </Card>
);

// ─── Rate Display ────────────────────────────────────────────
const RatePill = ({ label, value, good }) => (
  <div className="flex items-center justify-between py-1.5">
    <span className="text-xs text-gray-500">{label}</span>
    <span className={`text-sm font-mono font-semibold ${
      good ? 'text-emerald-400' : value > 0 ? 'text-red-400' : 'text-gray-600'
    }`}>
      {typeof value === 'number' ? `${value}%` : value}
    </span>
  </div>
);

// ─── Provider Badge ──────────────────────────────────────────
const ProviderBadge = ({ name }) => {
  const colors = {
    exely: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    hotelrunner: 'bg-violet-500/15 text-violet-400 border-violet-500/30',
  };
  return (
    <Badge className={`${colors[name] || 'bg-gray-100 text-gray-600'} border text-xs font-medium`}>
      {name}
    </Badge>
  );
};

export default function LockdownDashboard({ user, tenant, onLogout }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [status, setStatus] = useState(null);
  const [ingestMetrics, setIngestMetrics] = useState(null);
  const [lineageMetrics, setLineageMetrics] = useState(null);
  const [reconMetrics, setReconMetrics] = useState(null);
  const [mappingHealth, setMappingHealth] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [truthTable, setTruthTable] = useState(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    try {
      const [sRes, iRes, lRes, rRes, mRes, cRes, tRes] = await Promise.allSettled([
        axios.get(`/lockdown/status`, { headers }),
        axios.get(`/lockdown/metrics/ingest?hours=24`, { headers }),
        axios.get(`/lockdown/metrics/lineage`, { headers }),
        axios.get(`/lockdown/metrics/reconciliation`, { headers }),
        axios.get(`/lockdown/health/mapping`, { headers }),
        axios.get(`/lockdown/providers/capabilities`, { headers }),
        axios.get(`/lockdown/reconciliation/truth-table`, { headers }),
      ]);

      if (sRes.status === 'fulfilled') setStatus(sRes.value.data);
      if (iRes.status === 'fulfilled') setIngestMetrics(iRes.value.data);
      if (lRes.status === 'fulfilled') setLineageMetrics(lRes.value.data);
      if (rRes.status === 'fulfilled') setReconMetrics(rRes.value.data);
      if (mRes.status === 'fulfilled') setMappingHealth(mRes.value.data);
      if (cRes.status === 'fulfilled') setCapabilities(cRes.value.data);
      if (tRes.status === 'fulfilled') setTruthTable(tRes.value.data);
    } catch {
      toast.error('Lockdown verileri yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchAll();
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="lockdown">
        <div className="flex items-center justify-center h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-gray-500" />
        </div>
      </Layout>
    );
  }

  const overallStatus = status?.status || 'degraded';
  const isReady = mappingHealth?.overall_production_ready || false;
  const checks = status?.checks || {};

  // Ingest rates
  const rates = ingestMetrics?.rates || {};
  const totals = ingestMetrics?.totals || {};

  // Lineage
  const lin = lineageMetrics || {};

  // Reconciliation
  const recon = reconMetrics || {};

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} activeModule="lockdown">
      <div className="space-y-6 p-4 lg:p-6 max-w-[1400px] mx-auto">

        {/* ─── Header ──────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${overallStatus === 'healthy' ? 'bg-emerald-500/15' : 'bg-red-500/15'}`}>
              {overallStatus === 'healthy'
                ? <ShieldCheck data-testid="lockdown-shield-healthy" className="w-6 h-6 text-emerald-400" />
                : <ShieldAlert data-testid="lockdown-shield-degraded" className="w-6 h-6 text-red-400" />
              }
            </div>
            <div>
              <h1 data-testid="lockdown-title" className="text-xl font-bold text-gray-900">
                Core Lockdown
              </h1>
              <p className="text-xs text-gray-500">Production Readiness Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge
              data-testid="production-ready-badge"
              className={`text-xs font-bold px-3 py-1 ${
                isReady
                  ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40'
                  : 'bg-red-500/15 text-red-400 border-red-500/40'
              } border`}
            >
              {isReady ? 'PRODUCTION READY' : 'NOT READY'}
            </Badge>
            <Button
              data-testid="lockdown-refresh-btn"
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="border-gray-300 text-gray-600 hover:text-gray-900"
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </div>

        {/* ─── System Health Overview ─────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {['ingest', 'mapping', 'reconciliation'].map((key) => {
            const check = checks[key] || {};
            const st = check.status || 'degraded';
            const icons = { ingest: Zap, mapping: Database, reconciliation: ArrowRightLeft };
            const Icon = icons[key];
            const labels = { ingest: 'Ingest Pipeline', mapping: 'Mapping Health', reconciliation: 'Reconciliation' };
            return (
              <Card
                key={key}
                data-testid={`health-card-${key}`}
                className={`bg-white border-gray-200 ${st !== 'healthy' ? 'border-red-500/30' : 'border-emerald-500/20'}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Icon className={`w-4 h-4 ${st === 'healthy' ? 'text-emerald-400' : 'text-red-400'}`} />
                      <span className="text-sm font-semibold text-gray-800">{labels[key]}</span>
                    </div>
                    <StatusDot status={st} />
                  </div>
                  <div className="space-y-1 text-xs text-gray-500">
                    {key === 'ingest' && (
                      <>
                        <div className="flex justify-between"><span>24s Events</span><span className="text-gray-700">{check.events_24h ?? 0}</span></div>
                        <div className="flex justify-between"><span>Basarisiz</span><span className={check.failed_24h > 0 ? 'text-red-400' : 'text-emerald-400'}>{check.failed_24h ?? 0}</span></div>
                        <div className="flex justify-between"><span>Hata Orani</span><span className={check.failure_rate_pct > 0 ? 'text-red-400' : 'text-emerald-400'}>{check.failure_rate_pct ?? 0}%</span></div>
                      </>
                    )}
                    {key === 'mapping' && (
                      <>
                        <div className="flex justify-between"><span>Aktif Mapping</span><span className="text-gray-700">{check.active_room_mappings ?? 0}</span></div>
                        <div className="flex justify-between"><span>Kirik Mapping</span><span className={check.broken_room_mappings > 0 ? 'text-red-400' : 'text-emerald-400'}>{check.broken_room_mappings ?? 0}</span></div>
                      </>
                    )}
                    {key === 'reconciliation' && (
                      <>
                        <div className="flex justify-between"><span>Açık Vakalar</span><span className={check.open_cases > 0 ? 'text-amber-400' : 'text-emerald-400'}>{check.open_cases ?? 0}</span></div>
                        <div className="flex justify-between"><span>Kritik Vakalar</span><span className={check.critical_cases > 0 ? 'text-red-400' : 'text-emerald-400'}>{check.critical_cases ?? 0}</span></div>
                        <div className="flex justify-between"><span>Eslesmemis</span><span className="text-gray-700">{check.unreconciled_lineages ?? 0}</span></div>
                      </>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* ─── Key Metrics Grid ──────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <MetricCard
            testId="metric-total-events"
            title="Toplam Event (24s)"
            value={totals.total_events ?? 0}
            icon={Activity}
            color="bg-blue-500/15 text-blue-400"
          />
          <MetricCard
            testId="metric-duplicate-rate"
            title="Duplikat Orani"
            value={`${rates.duplicate_rate_pct ?? 0}%`}
            icon={FileWarning}
            color="bg-amber-500/15 text-amber-400"
            alert={(rates.duplicate_rate_pct ?? 0) > 10}
          />
          <MetricCard
            testId="metric-stale-rate"
            title="Stale Red Orani"
            value={`${rates.stale_rate_pct ?? 0}%`}
            icon={Clock}
            color="bg-orange-500/15 text-orange-400"
            alert={(rates.stale_rate_pct ?? 0) > 5}
          />
          <MetricCard
            testId="metric-success-rate"
            title="Basari Orani"
            value={`${rates.success_rate_pct ?? 0}%`}
            icon={CheckCircle}
            color="bg-emerald-500/15 text-emerald-400"
          />
          <MetricCard
            testId="metric-total-lineages"
            title="Toplam Lineage"
            value={lin.total_lineages ?? 0}
            icon={TrendingUp}
            color="bg-violet-500/15 text-violet-400"
          />
          <MetricCard
            testId="metric-unreconciled"
            title="Eslesmemis"
            value={lin.unreconciled ?? 0}
            icon={AlertTriangle}
            color="bg-red-500/15 text-red-400"
            alert={(lin.unreconciled ?? 0) > 0}
          />
        </div>

        {/* ─── Ingest Pipeline Detail ─────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card data-testid="ingest-detail-card" className="bg-white border-gray-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <Zap className="w-4 h-4 text-blue-400" />
                Ingest Pipeline (Son 24 Saat)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-0.5">
              <RatePill label="Islenen" value={rates.success_rate_pct ?? 0} good={true} />
              <RatePill label="Duplikat" value={rates.duplicate_rate_pct ?? 0} good={false} />
              <RatePill label="Stale (Eski)" value={rates.stale_rate_pct ?? 0} good={false} />
              <RatePill label="Basarisiz" value={rates.failure_rate_pct ?? 0} good={false} />
              <div className="border-t border-gray-200 mt-2 pt-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-500">Karar Dagilimi</span>
                </div>
                {ingestMetrics?.decisions && Object.entries(ingestMetrics.decisions).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between py-0.5">
                    <span className="text-xs text-gray-500 capitalize">{key}</span>
                    <span className="text-xs font-mono text-gray-700">{val}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* ─── Lineage by Status ─────────────────────────── */}
          <Card data-testid="lineage-detail-card" className="bg-white border-gray-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <Database className="w-4 h-4 text-violet-400" />
                Rezervasyon Lineage
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Toplam</span>
                  <span className="text-gray-800 font-semibold">{lin.total_lineages ?? 0}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Eslesmis</span>
                  <span className="text-emerald-400 font-semibold">{lin.reconciled ?? 0}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Eslesmemis</span>
                  <span className={`font-semibold ${(lin.unreconciled ?? 0) > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                    {lin.unreconciled ?? 0}
                  </span>
                </div>
              </div>

              {lin.by_status && Object.keys(lin.by_status).length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <span className="text-xs text-gray-500 mb-1 block">Duruma Gore</span>
                  {Object.entries(lin.by_status).map(([st, cnt]) => (
                    <div key={st} className="flex justify-between py-0.5">
                      <span className="text-xs text-gray-500 capitalize">{st}</span>
                      <span className="text-xs font-mono text-gray-700">{cnt}</span>
                    </div>
                  ))}
                </div>
              )}

              {lin.by_provider && Object.keys(lin.by_provider).length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-200">
                  <span className="text-xs text-gray-500 mb-1 block">Provider Gore</span>
                  {Object.entries(lin.by_provider).map(([prov, cnt]) => (
                    <div key={prov} className="flex items-center justify-between py-0.5">
                      <ProviderBadge name={prov} />
                      <span className="text-xs font-mono text-gray-700">{cnt}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ─── Mapping Health per Provider ─────────────────── */}
        {mappingHealth?.mapping_health && mappingHealth.mapping_health.length > 0 && (
          <Card data-testid="mapping-health-card" className="bg-white border-gray-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <Database className="w-4 h-4 text-cyan-400" />
                Mapping Sagligi
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {mappingHealth.mapping_health.map((mh, i) => (
                  <div key={i} className="border border-gray-200 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <ProviderBadge name={mh.provider} />
                      <Badge
                        className={`text-[10px] ${
                          mh.is_production_ready
                            ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                            : 'bg-red-500/15 text-red-400 border-red-500/30'
                        } border`}
                      >
                        {mh.is_production_ready ? 'READY' : 'NOT READY'}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            mh.overall_completeness_pct === 100 ? 'bg-emerald-500' :
                            mh.overall_completeness_pct > 80 ? 'bg-amber-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${mh.overall_completeness_pct || 0}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-gray-700 w-10 text-right">
                        {mh.overall_completeness_pct ?? 0}%
                      </span>
                    </div>
                    {mh.room_mapping && (
                      <div className="text-xs text-gray-500 grid grid-cols-3 gap-1">
                        <span>Oda: {mh.room_mapping.total ?? 0}</span>
                        <span className={mh.room_mapping.broken > 0 ? 'text-red-400' : ''}>
                          Kirik: {mh.room_mapping.broken ?? 0}
                        </span>
                        <span className={mh.room_mapping.inactive > 0 ? 'text-amber-400' : ''}>
                          Pasif: {mh.room_mapping.inactive ?? 0}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* ─── Reconciliation Detail ──────────────────────── */}
        <Card data-testid="reconciliation-card" className="bg-white border-gray-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-gray-800 flex items-center gap-2">
              <ArrowRightLeft className="w-4 h-4 text-amber-400" />
              Reconciliation
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="text-center p-2 rounded-lg bg-gray-50">
                <p className="text-lg font-bold text-gray-800">{recon.total_cases ?? 0}</p>
                <p className="text-[10px] text-gray-500">Toplam Vaka</p>
              </div>
              <div className="text-center p-2 rounded-lg bg-gray-50">
                <p className={`text-lg font-bold ${(recon.open_cases ?? 0) > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {recon.open_cases ?? 0}
                </p>
                <p className="text-[10px] text-gray-500">Açık</p>
              </div>
              <div className="text-center p-2 rounded-lg bg-gray-50">
                <p className="text-lg font-bold text-emerald-400">{recon.resolved_cases ?? 0}</p>
                <p className="text-[10px] text-gray-500">Cozulmus</p>
              </div>
              <div className="text-center p-2 rounded-lg bg-gray-50">
                <p className={`text-lg font-bold ${recon.oldest_unresolved_age_hours ? 'text-red-400' : 'text-gray-600'}`}>
                  {recon.oldest_unresolved_age_hours ? `${recon.oldest_unresolved_age_hours}s` : '-'}
                </p>
                <p className="text-[10px] text-gray-500">En Eski Açık (saat)</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ─── Provider Capabilities ──────────────────────── */}
        {capabilities?.providers && (
          <Card data-testid="capabilities-card" className="bg-white border-gray-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <Server className="w-4 h-4 text-indigo-400" />
                Provider Yetenek Matrisi
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 text-gray-500 font-medium">Provider</th>
                      <th className="text-left py-2 text-gray-500 font-medium">Ingest</th>
                      <th className="text-left py-2 text-gray-500 font-medium">ARI Push</th>
                      <th className="text-center py-2 text-gray-500 font-medium">Delta</th>
                      <th className="text-center py-2 text-gray-500 font-medium">ACK=Applied</th>
                      <th className="text-right py-2 text-gray-500 font-medium">Rate Limit</th>
                      <th className="text-right py-2 text-gray-500 font-medium">Retry</th>
                    </tr>
                  </thead>
                  <tbody>
                    {capabilities.providers.map((p) => (
                      <tr key={p.provider} className="border-b border-gray-100">
                        <td className="py-2"><ProviderBadge name={p.provider} /></td>
                        <td className="py-2 text-gray-700">{p.reservation?.ingest_type}</td>
                        <td className="py-2 text-gray-700">{p.ari?.push_behavior}</td>
                        <td className="py-2 text-center">
                          {p.ari?.supports_delta_push
                            ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 inline" />
                            : <XCircle className="w-3.5 h-3.5 text-gray-600 inline" />
                          }
                        </td>
                        <td className="py-2 text-center">
                          {p.consistency?.ack_means_applied
                            ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 inline" />
                            : <XCircle className="w-3.5 h-3.5 text-gray-600 inline" />
                          }
                        </td>
                        <td className="py-2 text-right text-gray-600">{p.rate_limits?.requests_per_minute}/dk</td>
                        <td className="py-2 text-right text-gray-600">{p.retry_policy?.max_attempts}x</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

        {/* ─── Truth Table ────────────────────────────────── */}
        {truthTable?.truth_table && (
          <Card data-testid="truth-table-card" className="bg-white border-gray-200">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <Eye className="w-4 h-4 text-cyan-400" />
                Reconciliation Truth Table
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 text-gray-500 font-medium">Drift Tipi</th>
                      <th className="text-left py-2 text-gray-500 font-medium">Gold Kaynak</th>
                      <th className="text-left py-2 text-gray-500 font-medium">Cozum</th>
                      <th className="text-center py-2 text-gray-500 font-medium">Oto-Heal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {truthTable.truth_table.map((row, i) => (
                      <tr key={i} className="border-b border-gray-100">
                        <td className="py-1.5">
                          <Badge className="bg-gray-100 text-gray-700 border-gray-300 border text-[10px]">
                            {row.drift_type}
                          </Badge>
                        </td>
                        <td className="py-1.5 text-gray-600">{row.gold_source}</td>
                        <td className="py-1.5">
                          <Badge className={`border text-[10px] ${
                            row.resolution === 'safe_auto_heal'
                              ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                              : row.resolution === 'manual_review'
                              ? 'bg-red-500/15 text-red-400 border-red-500/30'
                              : 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                          }`}>
                            {row.resolution}
                          </Badge>
                        </td>
                        <td className="py-1.5 text-center">
                          {row.can_auto_heal
                            ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 inline" />
                            : <XCircle className="w-3.5 h-3.5 text-gray-600 inline" />
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

        {/* ─── Timestamp ──────────────────────────────────── */}
        <p className="text-[10px] text-gray-600 text-right">
          Son güncelleme: {status?.timestamp ? new Date(status.timestamp).toLocaleString('tr-TR') : '-'}
        </p>
      </div>
    </Layout>
  );
}
