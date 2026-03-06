import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Activity, AlertTriangle, Clock3, RefreshCw, ShieldAlert, Waves } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import Layout from '@/components/Layout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';


const QUEUE_COLORS = ['#0f766e', '#0891b2', '#dc2626', '#b45309', '#6b7280'];

const formatTime = (value) => value ? new Date(value).toLocaleString('tr-TR') : '—';
const formatMs = (value) => (typeof value === 'number' ? `${value.toFixed(0)} ms` : 'N/A');
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
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setRefreshing(true);
    try {
      const response = await axios.get('/reports/migration-observability');
      setData(response.data);
    } catch (error) {
      console.error('Migration observability load failed:', error);
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

  const queueData = useMemo(() => {
    if (!data?.outbox?.queue_depth) return [];
    return Object.entries(data.outbox.queue_depth).map(([name, value], index) => ({
      name,
      value,
      fill: QUEUE_COLORS[index % QUEUE_COLORS.length],
    }));
  }, [data]);

  const overview = data?.outbox;
  const healthScore = data?.health_score;
  const healthStyle = HEALTH_SCORE_STYLES[healthScore?.status || 'green'];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports">
      <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(20,184,166,0.16),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(245,158,11,0.16),_transparent_24%),linear-gradient(180deg,#f8fafc_0%,#fffdf7_100%)] p-4 md:p-6" data-testid="migration-observability-page">
        <div className="mx-auto max-w-7xl space-y-6">
          <section className="overflow-hidden rounded-[28px] border border-slate-200/70 bg-slate-950 text-white shadow-2xl shadow-slate-200/60" data-testid="migration-observability-hero">
            <div className="grid gap-6 px-6 py-8 md:grid-cols-[1.2fr_0.8fr] md:px-8">
              <div className="space-y-4">
                <Badge className="bg-white/10 text-teal-100 hover:bg-white/10" data-testid="migration-observability-badge">Migration Control Surface</Badge>
                <div className="space-y-3">
                  <h1 className="text-4xl font-semibold tracking-tight md:text-5xl" style={{ fontFamily: 'Space Grotesk' }} data-testid="migration-observability-title">
                    Semantic cutover akışlarını canlı izleyin.
                  </h1>
                  <p className="max-w-2xl text-sm leading-7 text-slate-300 md:text-base" data-testid="migration-observability-subtitle">
                    Outbox throughput, audit trail ve shadow mismatch sinyallerini tek ekranda toplayan operasyon paneli.
                  </p>
                </div>
              </div>
              <div className="flex flex-col justify-between gap-4 rounded-[24px] border border-white/10 bg-white/5 p-5" data-testid="migration-observability-status-panel">
                <div>
                  <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Last refresh</p>
                  <p className="mt-2 text-lg font-medium" data-testid="migration-observability-generated-at">{formatTime(data?.generated_at)}</p>
                </div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-2xl bg-white/5 p-3" data-testid="migration-observability-panel-outbox-total">
                    <div className="text-slate-400">Outbox events</div>
                    <div className="mt-1 text-2xl font-semibold">{overview?.total_events ?? '—'}</div>
                  </div>
                  <div className="rounded-2xl bg-white/5 p-3" data-testid="migration-observability-panel-audit-total">
                    <div className="text-slate-400">Audit rows</div>
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
                  Veriyi yenile
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
                      <p className="text-sm uppercase tracking-[0.25em] text-slate-500">Migration health score</p>
                      <h2 className="mt-2 text-3xl font-semibold text-slate-950" style={{ fontFamily: 'Space Grotesk' }} data-testid="migration-health-score-title">
                        {healthScore?.operational_guidance || 'Green → sıradaki dar write-path’e geçilebilir'}
                      </h2>
                    </div>
                    <p className="text-sm text-slate-600" data-testid="migration-health-score-calculated-at">
                      Son hesaplanma: {formatTime(healthScore?.calculated_at)}
                    </p>
                  </div>

                  <div className="grid gap-4 md:grid-cols-[1fr_0.9fr]">
                    <div className="rounded-[24px] border border-white bg-white/80 p-5" data-testid="migration-health-score-reasons-panel">
                      <p className="text-xs uppercase tracking-[0.25em] text-slate-500">Kısa nedenler</p>
                      <ul className="mt-4 space-y-3 text-sm text-slate-700">
                        {(healthScore?.reasons || []).map((reason, index) => (
                          <li key={`${reason}-${index}`} className="flex items-start gap-3" data-testid={`migration-health-score-reason-${index}`}>
                            <span className="mt-1 h-2 w-2 rounded-full bg-slate-900" />
                            <span>{reason}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="rounded-[24px] border border-white bg-slate-950 p-5 text-white" data-testid="migration-health-score-signals-panel">
                      <p className="text-xs uppercase tracking-[0.25em] text-slate-400">Signals</p>
                      <div className="mt-4 space-y-3 text-sm">
                        <div className="flex items-center justify-between"><span>Failed outbox</span><span data-testid="migration-health-score-failed-outbox">{healthScore?.signals?.failed_outbox_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>Stale pending</span><span data-testid="migration-health-score-stale-pending">{healthScore?.signals?.stale_pending_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>Audit gap</span><span data-testid="migration-health-score-audit-gap">{healthScore?.signals?.audit_gap_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>Compare error</span><span data-testid="migration-health-score-compare-error">{healthScore?.signals?.compare_error_count ?? 0}</span></div>
                        <div className="flex items-center justify-between"><span>Max mismatch</span><span data-testid="migration-health-score-mismatch-rate">%{healthScore?.signals?.max_mismatch_rate_percent ?? 0}</span></div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <StatCard icon={Activity} label="24h throughput" value={overview?.throughput?.events_last_24h ?? 0} helper={`${overview?.throughput?.events_per_second_24h ?? 0} events/sec`} tone="bg-teal-100 text-teal-700" testId="migration-stat-throughput" />
                <StatCard icon={AlertTriangle} label="Pending queue" value={overview?.queue_depth?.pending ?? 0} helper={`${overview?.queue_depth?.stale_pending ?? 0} stale pending`} tone="bg-amber-100 text-amber-700" testId="migration-stat-pending" />
                <StatCard icon={ShieldAlert} label="Shadow mismatch" value={`${(data?.shadow?.summary || []).reduce((sum, item) => sum + (item.mismatches || 0), 0)}`} helper="Availability + folio toplam mismatch" tone="bg-rose-100 text-rose-700" testId="migration-stat-shadow" />
                <StatCard icon={Clock3} label="Event lag" value={formatMs(overview?.lag?.avg_ms)} helper={overview?.lag?.future_ready ? 'Future-ready / N-A' : `P95 ${formatMs(overview?.lag?.p95_ms)}`} tone="bg-sky-100 text-sky-700" testId="migration-stat-lag" />
              </div>

              <Tabs defaultValue="overview" className="space-y-4" data-testid="migration-observability-tabs">
                <TabsList className="h-auto flex-wrap justify-start gap-2 rounded-2xl bg-white/80 p-2" data-testid="migration-observability-tabs-list">
                  <TabsTrigger value="overview" data-testid="migration-tab-overview">Overview</TabsTrigger>
                  <TabsTrigger value="outbox" data-testid="migration-tab-outbox">Outbox</TabsTrigger>
                  <TabsTrigger value="audit" data-testid="migration-tab-audit">Audit</TabsTrigger>
                  <TabsTrigger value="shadow" data-testid="migration-tab-shadow">Shadow</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-4" data-testid="migration-overview-tab-content">
                  <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
                    <Card className="border-white/70 bg-white/90" data-testid="migration-overview-throughput-chart-card">
                      <CardHeader>
                        <CardTitle>Outbox event throughput</CardTitle>
                        <CardDescription>Son 24 saatte saatlik event akışı</CardDescription>
                      </CardHeader>
                      <CardContent className="h-[280px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={overview?.throughput?.hourly_series || []}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip />
                            <Bar dataKey="count" fill="#0f766e" radius={[8, 8, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                    <Card className="border-white/70 bg-white/90" data-testid="migration-overview-queue-chart-card">
                      <CardHeader>
                        <CardTitle>Queue depth snapshot</CardTitle>
                        <CardDescription>Pending, processed, failed ve dead-letter dağılımı</CardDescription>
                      </CardHeader>
                      <CardContent className="h-[280px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie data={queueData} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={4}>
                              {queueData.map((entry) => <Cell key={entry.name} fill={entry.fill} />)}
                            </Pie>
                            <Tooltip />
                          </PieChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </div>
                </TabsContent>

                <TabsContent value="outbox" className="space-y-4" data-testid="migration-outbox-tab-content">
                  <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                    <Card className="border-white/70 bg-white/90" data-testid="migration-outbox-breakdown-card">
                      <CardHeader>
                        <CardTitle>Event breakdown</CardTitle>
                        <CardDescription>Semantic çekirdeğe taşınan event tiplerinin dağılımı</CardDescription>
                      </CardHeader>
                      <CardContent>
                        <Table data-testid="migration-outbox-breakdown-table">
                          <TableHeader>
                            <TableRow>
                              <TableHead>Event</TableHead>
                              <TableHead>Total</TableHead>
                              <TableHead>Pending</TableHead>
                              <TableHead>Last seen</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {(overview?.event_breakdown || []).map((item) => (
                              <TableRow key={item.event_type} data-testid={`migration-outbox-event-row-${item.event_type.replace(/[^a-z0-9]/gi, '-')}`}>
                                <TableCell className="font-medium">{item.event_type}</TableCell>
                                <TableCell>{item.total_count}</TableCell>
                                <TableCell>{item.pending_count}</TableCell>
                                <TableCell>{formatTime(item.last_seen_at)}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                    <Card className="border-white/70 bg-white/90" data-testid="migration-outbox-future-ready-card">
                      <CardHeader>
                        <CardTitle>Retry & lag readiness</CardTitle>
                        <CardDescription>Retry/dead-letter ve processed lag için future-ready durumu</CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-outbox-retries-panel">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-700">Retry attempts</span>
                            <Badge variant="outline">{overview?.retries?.future_ready ? 'Future-ready / N-A' : 'Active'}</Badge>
                          </div>
                          <div className="mt-3 text-2xl font-semibold text-slate-900">{overview?.retries?.total_attempts ?? 0}</div>
                          <div className="mt-1 text-sm text-slate-500">Dead letter: {overview?.retries?.dead_letter_count ?? 0}</div>
                        </div>
                        <div className="rounded-2xl bg-slate-50 p-4" data-testid="migration-outbox-lag-panel">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium text-slate-700">Processing lag</span>
                            <Badge variant="outline">{overview?.lag?.future_ready ? 'Future-ready / N-A' : 'Measured'}</Badge>
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
                      <CardTitle>Audit stream</CardTitle>
                      <CardDescription>Actor, entity, action ve correlation context ile son migration kayıtları</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Table data-testid="migration-audit-stream-table">
                        <TableHeader>
                          <TableRow>
                            <TableHead>Action</TableHead>
                            <TableHead>Entity</TableHead>
                            <TableHead>Actor</TableHead>
                            <TableHead>Property</TableHead>
                            <TableHead>Timestamp</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(data?.audit?.recent_stream || []).map((row) => (
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
                    </CardContent>
                  </Card>
                </TabsContent>

                <TabsContent value="shadow" className="space-y-4" data-testid="migration-shadow-tab-content">
                  <div className="grid gap-4 md:grid-cols-2">
                    {(data?.shadow?.summary || []).map((item) => (
                      <Card key={item.endpoint} className="border-white/70 bg-white/90" data-testid={`migration-shadow-summary-${item.endpoint}`}>
                        <CardHeader>
                          <CardTitle className="capitalize">{item.endpoint}</CardTitle>
                          <CardDescription>Mismatch rate %{item.mismatch_rate_percent}</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          <div className="flex items-center justify-between text-sm"><span>Total compares</span><span className="font-semibold">{item.total_compares}</span></div>
                          <div className="flex items-center justify-between text-sm"><span>Mismatches</span><span className="font-semibold">{item.mismatches}</span></div>
                          <div className="flex items-center justify-between text-sm"><span>Errors</span><span className="font-semibold">{item.errors}</span></div>
                          <div className="flex items-center justify-between text-sm"><span>Last compare</span><span className="font-semibold">{formatTime(item.last_compare_at)}</span></div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                  <Card className="border-white/70 bg-white/90" data-testid="migration-shadow-recent-card">
                    <CardHeader>
                      <CardTitle>Recent shadow events</CardTitle>
                      <CardDescription>Mismatch veya compare detayları</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Table data-testid="migration-shadow-recent-table">
                        <TableHeader>
                          <TableRow>
                            <TableHead>Endpoint</TableHead>
                            <TableHead>Result</TableHead>
                            <TableHead>Mismatch fields</TableHead>
                            <TableHead>Duration</TableHead>
                            <TableHead>Timestamp</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(data?.shadow?.recent_events || []).map((row, index) => (
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
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      </div>
    </Layout>
  );
}