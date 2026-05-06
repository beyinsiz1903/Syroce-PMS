import { useTranslation } from 'react-i18next';
import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Activity, AlertTriangle, ChevronLeft, ChevronRight, Clock3, RefreshCw, ShieldAlert, Waves } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, Tooltip, XAxis, YAxis } from 'recharts';


import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { StalePendingTriageCard } from '@/components/migration/StalePendingTriageCard';


const QUEUE_COLORS = ['#0f766e', '#0891b2', '#dc2626', '#b45309', '#6b7280'];
const PAGE_SIZE = 10;

const HEALTH_SCORE_STYLES = {
  green: {
    badge: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    glow: 'shadow-emerald-200/60',
    panel: 'from-emerald-50 to-white',
  },
  yellow: {
    badge: 'bg-amber-100 text-amber-700 border-amber-200',
    glow: 'shadow-amber-200/60',
    panel: 'from-amber-50 to-white',
  },
  red: {
    badge: 'bg-rose-100 text-rose-700 border-rose-200',
    glow: 'shadow-rose-200/60',
    panel: 'from-rose-50 to-white',
  },
};

function Pagination({ currentPage, totalPages, onPageChange, t }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-end gap-2 pt-3">
      <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)}>
        <ChevronLeft className="h-4 w-4 mr-1" />{t('migrationObs.pagesPrev')}
      </Button>
      <span className="text-sm text-slate-600">{currentPage} {t('migrationObs.pagesOf')} {totalPages}</span>
      <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => onPageChange(currentPage + 1)}>
        {t('migrationObs.pagesNext')}<ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  );
}

const StatCard = ({ icon: Icon, label, value, helper, tone, testId }) => (
  <Card className="border-white/70 bg-white/85 shadow-sm backdrop-blur" data-testid={testId}>
    <CardContent className="p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{label}</p>
          <p className="mt-3 text-3xl font-semibold text-slate-900">{value}</p>
          <p className="mt-2 text-sm text-slate-600">{helper}</p>
        </div>
        <div className={`rounded-2xl p-3 ${tone}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </CardContent>
  </Card>
);


export default function MigrationObservabilityPage({ user, tenant, onLogout }) {
  const { t, i18n } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [chartsReady, setChartsReady] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(() => (typeof window === 'undefined' ? 1280 : window.innerWidth));
  const [outboxPage, setOutboxPage] = useState(1);
  const [auditPage, setAuditPage] = useState(1);
  const [shadowPage, setShadowPage] = useState(1);

  const currentLocale = i18n.language || 'en';
  const formatTime = useCallback((value) => value ? new Date(value).toLocaleString(currentLocale) : '—', [currentLocale]);
  const formatMs = (value) => (typeof value === 'number' ? `${value.toFixed(0)} ms` : 'N/A');
  const formatAgeMinutes = useCallback((value) => (typeof value === 'number' ? `${Math.round(value)} ${t('migrationObs.minutes')}` : '—'), [t]);

  const tm = useCallback((key) => t(`migrationObs.${key}`), [t]);

  const translateReason = useCallback((reason, params) => {
    const reasonKey = `migrationObs.reason_${reason}`;
    const translated = t(reasonKey, params || {});
    return translated !== reasonKey ? translated : reason;
  }, [t]);

  const translateAssessment = useCallback((key, fallback, params = {}) => {
    if (!key) return fallback || '—';
    const translationKey = `migrationObs.assess_${key}`;
    const translated = t(translationKey, params);
    return translated !== translationKey ? translated : fallback || key;
  }, [t]);

  const loadData = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setRefreshing(true);
    try {
      const response = await axios.get('/reports/migration-observability');
      setData(response.data);
      setError(false);
    } catch (err) {
      console.error('Migration observability load failed:', err);
      setData((prev) => {
        if (!prev) setError(true);
        return prev;
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const interval = setInterval(() => loadData({ silent: true }), 20000);
    return () => clearInterval(interval);
  }, [loadData]);

  useEffect(() => {
    const handleResize = () => setViewportWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (activeTab !== 'overview' || loading || !data) {
      setChartsReady(false);
      return undefined;
    }

    const timer = window.setTimeout(() => setChartsReady(true), 180);
    return () => window.clearTimeout(timer);
  }, [activeTab, loading, data]);

  const queueData = useMemo(() => {
    const lifecycle = data?.outbox?.lifecycle;
    if (!lifecycle) return [];
    return [
      [tm('pending'), lifecycle.pending_count ?? 0],
      [tm('processing'), lifecycle.processing_count ?? 0],
      [tm('processed'), lifecycle.processed_count ?? 0],
      [tm('failed'), lifecycle.failed_count ?? 0],
      [tm('parked'), lifecycle.parked_count ?? 0],
    ].map(([name, value], index) => ({
      name,
      value,
      fill: QUEUE_COLORS[index % QUEUE_COLORS.length],
    }));
  }, [data, tm]);

  const overview = data?.outbox;
  const lifecycle = overview?.lifecycle;
  const healthScore = data?.health_score;
  const healthStyle = HEALTH_SCORE_STYLES[healthScore?.status || 'green'];
  const throughputChartWidth = viewportWidth >= 1440 ? 760 : viewportWidth >= 1024 ? 620 : Math.max(viewportWidth - 120, 260);
  const queueChartWidth = viewportWidth >= 1440 ? 420 : viewportWidth >= 1024 ? 360 : Math.max(viewportWidth - 120, 260);

  const guidanceText = useMemo(() => {
    const key = healthScore?.operational_guidance_key;
    if (key) return tm(`${key}Guidance`);
    return tm('greenGuidance');
  }, [healthScore, tm]);

  const outboxBreakdown = overview?.event_breakdown || [];
  const outboxTotalPages = Math.ceil(outboxBreakdown.length / PAGE_SIZE);
  const outboxPageData = outboxBreakdown.slice((outboxPage - 1) * PAGE_SIZE, outboxPage * PAGE_SIZE);

  const auditStream = data?.audit?.recent_stream || [];
  const auditTotalPages = Math.ceil(auditStream.length / PAGE_SIZE);
  const auditPageData = auditStream.slice((auditPage - 1) * PAGE_SIZE, auditPage * PAGE_SIZE);

  const shadowEvents = data?.shadow?.recent_events || [];
  const shadowTotalPages = Math.ceil(shadowEvents.length / PAGE_SIZE);
  const shadowPageData = shadowEvents.slice((shadowPage - 1) * PAGE_SIZE, shadowPage * PAGE_SIZE);

  return (
    <>
      <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(20,184,166,0.16),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(245,158,11,0.16),_transparent_24%),linear-gradient(180deg,#f8fafc_0%,#fffdf7_100%)] p-4 md:p-6" data-testid="migration-observability-page">
        <div className="mx-auto max-w-7xl space-y-6">
          <section className="overflow-hidden rounded-[28px] border border-slate-200/70 bg-slate-950 text-white shadow-2xl shadow-slate-200/60" data-testid="migration-observability-hero">
            <div className="grid gap-6 px-6 py-8 md:grid-cols-[1.2fr_0.8fr] md:px-8">
              <div className="space-y-4">
                <Badge className="bg-white/10 text-teal-100 hover:bg-white/10" data-testid="migration-observability-badge">{t("techDashboards.migration")}</Badge>
                <div className="space-y-3">
                  <h1 className="text-4xl font-semibold tracking-tight md:text-5xl" style={{ fontFamily: 'Space Grotesk' }} data-testid="migration-observability-title">
                    {tm('heroTitle')}
                  </h1>
                  <p className="max-w-2xl text-sm leading-7 text-slate-300 md:text-base" data-testid="migration-observability-subtitle">
                    {tm('heroSubtitle')}
                  </p>
                </div>
              </div>
              <div className="flex flex-col justify-between gap-4 rounded-[24px] border border-white/10 bg-white/5 p-5" data-testid="migration-observability-status-panel">
                <div>
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-400">{tm('lastRefresh')}</p>
                  <p className="mt-2 text-lg font-medium" data-testid="migration-observability-generated-at">{formatTime(data?.generated_at)}</p>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-2xl bg-white/5 p-3" data-testid="migration-observability-panel-outbox-total">
                    <div className="text-slate-400">{tm('outboxEvents')}</div>
                    <div className="mt-1 text-2xl font-semibold">{overview?.total_events ?? '—'}</div>
                  </div>
                  <div className="rounded-2xl bg-white/5 p-3" data-testid="migration-observability-panel-audit-total">
                    <div className="text-slate-400">{tm('auditRows')}</div>
                    <div className="mt-1 text-2xl font-semibold">{data?.audit?.recent_count ?? '—'}</div>
                  </div>
                </div>
                <Button
                  variant="secondary"
                  className="w-full justify-center rounded-full bg-teal-300 text-slate-950 hover:bg-teal-200"
                  onClick={() => loadData()}
                  disabled={refreshing}
                  data-testid="migration-observability-refresh-button"
                >
                  <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                  {tm('refreshData')}
                </Button>
              </div>
            </div>
          </section>

          {loading && !data ? (
            <div className="grid gap-4 md:grid-cols-3" data-testid="migration-observability-loading-state">
              <Skeleton className="h-36" />
              <Skeleton className="h-36" />
              <Skeleton className="h-36" />
            </div>
          ) : error ? (
            <Card className="border-rose-200 bg-rose-50" data-testid="migration-observability-error-state">
              <CardContent className="flex flex-col items-center justify-center gap-4 p-10">
                <AlertTriangle className="h-10 w-10 text-rose-500" />
                <p className="text-center text-lg font-medium text-rose-700">{tm('loadError')}</p>
                <Button variant="outline" onClick={() => loadData()}>{tm('refreshData')}</Button>
              </CardContent>
            </Card>
          ) : !data?.outbox?.total_events && !data?.audit?.recent_count ? (
            <Card className="border-slate-200 bg-white" data-testid="migration-observability-empty-state">
              <CardContent className="flex flex-col items-center justify-center gap-4 p-10">
                <Activity className="h-10 w-10 text-slate-400" />
                <p className="text-center text-sm text-slate-600 max-w-md">{tm('noData')}</p>
              </CardContent>
            </Card>
          ) : (
            <>
              <Card
                className={`overflow-hidden border-white/80 bg-gradient-to-r ${healthStyle.panel} shadow-xl ${healthStyle.glow}`}
                data-testid="migration-health-score-card"
              >
                <CardContent className="grid gap-6 p-6 md:grid-cols-[0.85fr_1.15fr] md:p-7">
                  <div className="space-y-4">
                    <div className="flex items-center gap-3">
                      <Badge className={`border ${healthStyle.badge}`} data-testid="migration-health-score-status-badge">
                        {healthScore?.display_status || 'Green'}
                      </Badge>
                      <span className="text-xs uppercase tracking-[0.25em] text-slate-500" data-testid="migration-health-score-time-window">
                        {healthScore?.time_window_label || 'Last 24h'}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm uppercase tracking-[0.25em] text-slate-500">{tm('healthScore')}</p>
                      <h2 className="mt-2 text-3xl font-semibold text-slate-950" style={{ fontFamily: 'Space Grotesk' }} data-testid="migration-health-score-title">
                        {guidanceText}
                      </h2>
                    </div>
                    <p className="text-sm text-slate-600" data-testid="migration-health-score-calculated-at">
                      {tm('lastCalculated').replace('{{time}}', formatTime(healthScore?.calculated_at))}
                    </p>
                  </div>

                  <div className="grid gap-4 md:grid-cols-[1fr_0.9fr]">
                    <div className="rounded-[24px] border border-white bg-white/80 p-5" data-testid="migration-health-score-reasons-panel">
                      <p className="text-xs uppercase tracking-[0.25em] text-slate-500">{tm('shortReasons')}</p>
                      <ul className="mt-4 space-y-3 text-sm text-slate-700">
                        {(healthScore?.reasons || []).map((reason, index) => (
                          <li key={`${reason}-${index}`} className="flex items-start gap-3" data-testid={`migration-health-score-reason-${index}`}>
                            <span className="mt-1 h-2 w-2 rounded-full bg-slate-900" />
                            <span>{translateReason(reason, healthScore?.reason_params)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="rounded-[24px] border border-white bg-slate-950 p-5 text-white" data-testid="migration-health-score-signals-panel">
                      <p className="text-xs uppercase tracking-[0.25em] text-slate-400">{tm('signals')}</p>
                      <div className="mt-4 space-y-3 text-sm">
                        <div className="flex items-center justify-between"><span>{tm('failedOutbox')}</span><span data-testid="migration-health-score-failed-outbox">{healthScore?.signals?.failed_outbox_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>{tm('stalePending')}</span><span data-testid="migration-health-score-stale-pending">{healthScore?.signals?.stale_pending_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>{tm('auditGap')}</span><span data-testid="migration-health-score-audit-gap">{healthScore?.signals?.audit_gap_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>{tm('compareError')}</span><span data-testid="migration-health-score-compare-error">{healthScore?.signals?.compare_error_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>{tm('maxMismatch')}</span><span data-testid="migration-health-score-mismatch-rate">%{healthScore?.signals?.max_mismatch_rate_percent ?? 0}</span></div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <StatCard icon={Activity} label={tm('throughput24h')} value={overview?.throughput?.events_last_24h ?? 0} helper={tm('eventsPerSec').replace('{{count}}', overview?.throughput?.events_per_second_24h ?? 0)} tone="bg-teal-100 text-teal-700" testId="migration-stat-throughput" />
                <StatCard icon={AlertTriangle} label={tm('pendingQueue')} value={overview?.queue_depth?.pending ?? 0} helper={tm('staleProcessing').replace('{{stale}}', overview?.queue_depth?.stale_pending ?? 0).replace('{{processing}}', lifecycle?.processing_count ?? 0)} tone="bg-amber-100 text-amber-700" testId="migration-stat-pending" />
                <StatCard icon={ShieldAlert} label={tm('shadowMismatch')} value={`${(data?.shadow?.summary || []).reduce((sum, item) => sum + (item.mismatches || 0), 0)}`} helper={tm('mismatchHelper')} tone="bg-rose-100 text-rose-700" testId="migration-stat-shadow" />
                <StatCard icon={Clock3} label={tm('eventLag')} value={formatMs(overview?.lag?.avg_ms)} helper={tm('oldestPendingAge').replace('{{age}}', formatAgeMinutes(lifecycle?.oldest_pending_age_minutes))} tone="bg-sky-100 text-sky-700" testId="migration-stat-lag" />
              </div>

              <StalePendingTriageCard triage={overview?.stale_triage} />

              <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4" data-testid="migration-observability-tabs">
                <TabsList className="h-auto flex-wrap justify-start gap-2 rounded-2xl bg-white/80 p-2" data-testid="migration-observability-tabs-list">
                  <TabsTrigger value="overview" data-testid="migration-tab-overview">{tm('tabOverview')}</TabsTrigger>
                  <TabsTrigger value="outbox" data-testid="migration-tab-outbox">{tm('tabOutbox')}</TabsTrigger>
                  <TabsTrigger value="audit" data-testid="migration-tab-audit">{tm('tabAudit')}</TabsTrigger>
                  <TabsTrigger value="shadow" data-testid="migration-tab-shadow">{tm('tabShadow')}</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-4" data-testid="migration-overview-tab-content">
                  <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
                    <Card className="border-white/70 bg-white/90" data-testid="migration-overview-throughput-chart-card">
                      <CardHeader>
                        <CardTitle>{tm('outboxThroughput')}</CardTitle>
                        <CardDescription>{tm('hourlyFlow')}</CardDescription>
                      </CardHeader>
                      <CardContent className="flex h-[280px] items-center justify-center overflow-hidden">
                        {activeTab === 'overview' && chartsReady ? (
                          <BarChart width={throughputChartWidth} height={260} data={overview?.throughput?.hourly_series || []}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip />
                            <Bar dataKey="count" fill="#0f766e" radius={[8, 8, 0, 0]} />
                          </BarChart>
                        ) : null}
                      </CardContent>
                    </Card>
                    <Card className="border-white/70 bg-white/90" data-testid="migration-overview-queue-chart-card">
                      <CardHeader>
                        <CardTitle>{tm('queueDepth')}</CardTitle>
                        <CardDescription>{tm('queueDistribution')}</CardDescription>
                      </CardHeader>
                      <CardContent className="flex h-[280px] items-center justify-center overflow-hidden">
                        {activeTab === 'overview' && chartsReady ? (
                          <PieChart width={queueChartWidth} height={260}>
                            <Pie data={queueData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={4}>
                              {queueData.map((entry) => <Cell key={entry.name} fill={entry.fill} />)}
                            </Pie>
                            <Tooltip />
                          </PieChart>
                        ) : null}
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>

                <TabsContent value="outbox" className="space-y-4" data-testid="migration-outbox-tab-content">
                  <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                    <Card className="border-white/70 bg-white/90" data-testid="migration-outbox-breakdown-card">
                      <CardHeader>
                        <CardTitle>{tm('eventBreakdown')}</CardTitle>
                        <CardDescription>{tm('eventBreakdownDesc')}</CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Table data-testid="migration-outbox-breakdown-table">
                          <TableHeader>
                            <TableRow>
                              <TableHead>{tm('event')}</TableHead>
                              <TableHead>{tm('total')}</TableHead>
                              <TableHead>{tm('pending')}</TableHead>
                              <TableHead>{tm('processing')}</TableHead>
                              <TableHead>{tm('processed')}</TableHead>
                              <TableHead>{tm('failed')}</TableHead>
                              <TableHead>{tm('parked')}</TableHead>
                              <TableHead>{tm('lastSeen')}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {outboxPageData.map((item) => (
                              <TableRow key={item.event_type} data-testid={`migration-outbox-event-row-${item.event_type.replace(/[^a-z0-9]/gi, '-')}`}>
                                <TableCell className="font-medium">{item.event_type}</TableCell>
                                <TableCell>{item.total_count}</TableCell>
                                <TableCell>{item.pending_count}</TableCell>
                                <TableCell>{item.processing_count}</TableCell>
                                <TableCell>{item.processed_count}</TableCell>
                                <TableCell>{item.failed_count}</TableCell>
                                <TableCell>{item.parked_count}</TableCell>
                                <TableCell>{formatTime(item.last_seen_at)}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                        <Pagination currentPage={outboxPage} totalPages={outboxTotalPages} onPageChange={setOutboxPage} t={t} />
                      </CardContent>
                    </Card>
                    <Card className="border-white/70 bg-white/90" data-testid="migration-outbox-future-ready-card">
                      <CardHeader>
                        <CardTitle>{tm('lifecycleControls')}</CardTitle>
                        <CardDescription>{tm('lifecycleDesc')}</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-outbox-lifecycle-panel">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-700">{tm('lifecycleStateMachine')}</span>
                            <Badge variant="outline">{tm('temporaryWorker')}</Badge>
                          </div>
                          <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-700">
                            <div className="flex items-center justify-between gap-3"><span>{tm('pending')}</span><span data-testid="migration-outbox-pending-count">{lifecycle?.pending_count ?? 0}</span></div>
                            <div className="flex items-center justify-between gap-3"><span>{tm('processing')}</span><span data-testid="migration-outbox-processing-count">{lifecycle?.processing_count ?? 0}</span></div>
                            <div className="flex items-center justify-between gap-3"><span>{tm('processed')}</span><span data-testid="migration-outbox-processed-count">{lifecycle?.processed_count ?? 0}</span></div>
                            <div className="flex items-center justify-between gap-3"><span>{tm('failed')}</span><span data-testid="migration-outbox-failed-count">{lifecycle?.failed_count ?? 0}</span></div>
                            <div className="flex items-center justify-between gap-3"><span>{tm('parked')}</span><span data-testid="migration-outbox-parked-count">{lifecycle?.parked_count ?? 0}</span></div>
                            <div className="flex items-center justify-between gap-3"><span>{tm('retries')}</span><span data-testid="migration-outbox-retry-total">{lifecycle?.retry_attempts_total ?? 0}</span></div>
                          </div>
                          <div className="mt-4 space-y-2 text-xs text-slate-500">
                            <div className="flex items-center justify-between gap-3"><span>{tm('oldestPendingAgeLabel')}</span><span data-testid="migration-outbox-oldest-pending-age">{formatAgeMinutes(lifecycle?.oldest_pending_age_minutes)}</span></div>
                            <div className="flex items-center justify-between gap-3"><span>{tm('oldestFailedAge')}</span><span data-testid="migration-outbox-oldest-failed-age">{formatAgeMinutes(lifecycle?.oldest_failed_age_minutes)}</span></div>
                          </div>
                        </div>
                        <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-outbox-retries-panel">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-700">{tm('retryAttempts')}</span>
                            <Badge variant="outline">{overview?.retries?.future_ready ? tm('futureReady') : tm('active')}</Badge>
                          </div>
                          <div className="mt-3 text-2xl font-semibold text-slate-900">{overview?.retries?.total_attempts ?? 0}</div>
                          <div className="mt-1 text-sm text-slate-500">{tm('failed')}: {overview?.retries?.active_failed_count ?? 0} · {tm('parked')}: {overview?.retries?.parked_count ?? 0}</div>
                        </div>
                        <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-outbox-lag-panel">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-700">{tm('processingLag')}</span>
                            <Badge variant="outline">{overview?.lag?.future_ready ? tm('futureReady') : tm('measured')}</Badge>
                          </div>
                          <div className="mt-3 text-2xl font-semibold text-slate-900">{formatMs(overview?.lag?.avg_ms)}</div>
                          <div className="mt-1 text-sm text-slate-500">P95: {formatMs(overview?.lag?.p95_ms)}</div>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>

                <TabsContent value="audit" className="space-y-4" data-testid="migration-audit-tab-content">
                  <Card className="border-white/70 bg-white/90" data-testid="migration-audit-stream-card">
                    <CardHeader>
                      <CardTitle>{tm('auditStream')}</CardTitle>
                      <CardDescription>{tm('auditStreamDesc')}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Table data-testid="migration-audit-stream-table">
                        <TableHeader>
                          <TableRow>
                            <TableHead>{tm('action')}</TableHead>
                            <TableHead>{tm('entity')}</TableHead>
                            <TableHead>{tm('actor')}</TableHead>
                            <TableHead>{tm('property')}</TableHead>
                            <TableHead>{tm('timestamp')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {auditPageData.map((row) => (
                            <TableRow key={row.id || `${row.action}-${row.entity_id}`} data-testid={`migration-audit-row-${row.entity_id}`}>
                              <TableCell className="font-medium">{row.action}</TableCell>
                              <TableCell>{row.entity_type}:{row.entity_id}</TableCell>
                              <TableCell>{row.actor_id || 'system'}</TableCell>
                              <TableCell>{row.property_id || '—'}</TableCell>
                              <TableCell>{formatTime(row.timestamp)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      <Pagination currentPage={auditPage} totalPages={auditTotalPages} onPageChange={setAuditPage} t={t} />
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="shadow" className="space-y-4" data-testid="migration-shadow-tab-content">
                  <div className="grid gap-4 md:grid-cols-2">
                    {(data?.shadow?.summary || []).map((item) => (
                      <Card key={item.endpoint} className="border-white/70 bg-white/90" data-testid={`migration-shadow-summary-${item.endpoint}`}>
                        <CardHeader>
                          <CardTitle className="capitalize">{item.endpoint}</CardTitle>
                          <CardDescription>{tm('mismatchRate')} %{item.mismatch_rate_percent}</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          <div className="flex items-center justify-between text-sm"><span>{tm('totalCompares')}</span><span className="font-semibold">{item.total_compares}</span></div>
                          <div className="flex items-center justify-between text-sm"><span>{tm('mismatches')}</span><span className="font-semibold">{item.mismatches}</span></div>
                          <div className="flex items-center justify-between text-sm"><span>{tm('errors')}</span><span className="font-semibold">{item.errors}</span></div>
                          <div className="flex items-center justify-between text-sm"><span>{tm('lastCompare')}</span><span className="font-semibold">{formatTime(item.last_compare_at)}</span></div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                  <Card className="border-white/70 bg-white/90" data-testid="migration-shadow-recent-card">
                    <CardHeader>
                      <CardTitle>{tm('recentShadow')}</CardTitle>
                      <CardDescription>{tm('recentShadowDesc')}</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Table data-testid="migration-shadow-recent-table">
                        <TableHeader>
                          <TableRow>
                            <TableHead>{tm('endpoint')}</TableHead>
                            <TableHead>{tm('result')}</TableHead>
                            <TableHead>{tm('mismatchFields')}</TableHead>
                            <TableHead>{tm('duration')}</TableHead>
                            <TableHead>{tm('timestamp')}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {shadowPageData.map((row, index) => (
                            <TableRow key={`${row.endpoint}-${row.timestamp}-${index}`} data-testid={`migration-shadow-event-row-${index}`}>
                              <TableCell>{row.endpoint}</TableCell>
                              <TableCell>
                                <div className="inline-flex items-center gap-2">
                                  <Waves className="h-4 w-4 text-teal-600" />
                                  {row.compare_result}
                                </div>
                              </TableCell>
                              <TableCell>{(row.mismatch_fields || []).join(', ') || '—'}</TableCell>
                              <TableCell>{row.duration_ms} ms</TableCell>
                              <TableCell>{formatTime(row.timestamp)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      <Pagination currentPage={shadowPage} totalPages={shadowTotalPages} onPageChange={setShadowPage} t={t} />
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      </div>
    </>
  );
}
