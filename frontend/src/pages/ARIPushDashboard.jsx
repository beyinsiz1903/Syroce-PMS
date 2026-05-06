import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Activity, ArrowUpDown, CheckCircle, XCircle, Clock,
  RefreshCw, AlertTriangle, Loader2, Zap, BarChart3,
  ArrowRightLeft, Shield, Gauge, Timer, Inbox,
  TestTube, Play, ChevronRight
} from 'lucide-react';

const API = "";

const StatusBadge = ({ status }) => {
  const map = {
    pending: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', label: 'Pending' },
    queued: { color: 'bg-blue-500/15 text-blue-400 border-blue-500/30', label: 'Queued' },
    pushed: { color: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30', label: 'Pushed' },
    acked: { color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', label: 'Acked' },
    failed_retryable: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', label: 'Retry' },
    manual_review: { color: 'bg-red-500/15 text-red-400 border-red-500/30', label: 'Failed' },
    skipped: { color: 'bg-gray-100 text-gray-600 border-gray-300', label: 'Skipped' },
  };
  const s = map[status] || { color: 'bg-gray-100 text-gray-600', label: status };
  return <Badge data-testid={`status-badge-${status}`} className={`${s.color} border text-xs font-medium`}>{s.label}</Badge>;
};

const ScopeBadge = ({ scope }) => {
  const map = {
    availability: { color: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30', icon: '◈' },
    rate: { color: 'bg-violet-500/15 text-violet-400 border-violet-500/30', icon: '₺' },
    restriction: { color: 'bg-rose-500/15 text-rose-400 border-rose-500/30', icon: '⊘' },
  };
  const s = map[scope] || { color: 'bg-gray-100 text-gray-600', icon: '?' };
  return <Badge className={`${s.color} border text-xs`}>{s.icon} {scope}</Badge>;
};

const MetricCard = ({ title, value, icon: Icon, color, testId }) => (
  <Card data-testid={testId} className="bg-white border-gray-200">
    <CardContent className="p-4 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-gray-500 font-medium">{title}</p>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
      </div>
    </CardContent>
  </Card>
);

const ARIPushDashboard = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const [engineStats, setEngineStats] = useState(null);
  const [changeSets, setChangeSets] = useState([]);
  const [outboundLogs, setOutboundLogs] = useState([]);
  const [driftStates, setDriftStates] = useState([]);
  const [events, setEvents] = useState([]);
  const [statusFilter, setStatusFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [opMetrics, setOpMetrics] = useState(null);
  const [driftMode, setDriftMode] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [testRunning, setTestRunning] = useState(null);

  const tenantId = tenant?.id || '044f122b-87b5-480a-88b4-b9534b0c8c90';
  const propertyId = tenant?.property_id || 'prop-001';

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = `tenant_id=${tenantId}&property_id=${propertyId}`;
      const [statsRes, engineRes, csRes, logsRes, driftRes, evRes, metricsRes, modeRes] = await Promise.all([
        axios.get(`/channel-manager/ari/stats?${params}`).catch(() => ({ data: {} })),
        axios.get(`/channel-manager/ari/engine-stats`).catch(() => ({ data: {} })),
        axios.get(`/channel-manager/ari/change-sets?${params}&limit=100`).catch(() => ({ data: { change_sets: [] } })),
        axios.get(`/channel-manager/ari/outbound-logs?${params}&limit=50`).catch(() => ({ data: { logs: [] } })),
        axios.get(`/channel-manager/ari/drift?${params}&limit=50`).catch(() => ({ data: { drift_states: [] } })),
        axios.get(`/channel-manager/ari/events?${params}&limit=50`).catch(() => ({ data: { events: [] } })),
        axios.get(`/channel-manager/ari/test-harness/metrics?${params}`).catch(() => ({ data: {} })),
        axios.get(`/channel-manager/ari/drift/mode`).catch(() => ({ data: null })),
      ]);
      setStats(statsRes.data);
      setEngineStats(engineRes.data);
      setChangeSets(csRes.data.change_sets || []);
      setOutboundLogs(logsRes.data.logs || []);
      setDriftStates(driftRes.data.drift_states || []);
      setEvents(evRes.data.events || []);
      setOpMetrics(metricsRes.data);
      setDriftMode(modeRes.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [tenantId, propertyId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const pushPending = async () => {
    try {
      const { data } = await axios.post(`/channel-manager/ari/push`, {
        tenant_id: tenantId, provider: providerFilter === 'all' ? null : providerFilter,
      });
      toast.success(`Pushed: ${data.pushed}, Skipped: ${data.skipped}, Failed: ${data.failed}`);
      fetchAll();
    } catch { toast.error('Push failed'); }
  };

  const toggleDriftMode = async () => {
    const newMode = driftMode?.mode === 'normal' ? 'recovery' : 'normal';
    try {
      const { data } = await axios.post(`/channel-manager/ari/drift/mode/${newMode}`);
      // Map current_mode to mode for consistent state shape
      setDriftMode({ mode: data.current_mode, interval: data.interval, scope: data.scope });
      toast.success(`Drift mode: ${data.current_mode} (${data.interval}s interval)`);
    } catch { toast.error('Mode switch failed'); }
  };

  const runProviderTest = async (provider) => {
    setTestRunning(provider);
    try {
      const { data } = await axios.post(`/channel-manager/ari/test-harness/run/${provider}`);
      setTestResults(prev => ({ ...prev, [provider]: data }));
      const s = data.summary;
      if (s.failed === 0) {
        toast.success(`${provider}: All ${s.total} tests passed`);
      } else {
        toast.warning(`${provider}: ${s.passed}/${s.total} passed, ${s.failed} failed`);
      }
    } catch { toast.error(`${provider} test failed`); }
    setTestRunning(null);
  };

  const filteredCS = changeSets.filter(cs => {
    if (statusFilter !== 'all' && cs.status !== statusFilter) return false;
    if (providerFilter !== 'all' && cs.provider !== providerFilter) return false;
    return true;
  });

  return (
    <>
      <div data-testid="ari-push-dashboard" className="space-y-6 p-4 sm:p-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 tracking-tight">ARI Push Engine</h1>
            <p className="text-sm text-gray-500 mt-1">Event-driven availability, rate & restriction push pipeline</p>
          </div>
          <div className="flex gap-2">
            <Button data-testid="push-pending-btn" onClick={pushPending} size="sm" className="bg-emerald-600 hover:bg-emerald-700">
              <Zap className="w-4 h-4 mr-1" /> Push Pending
            </Button>
            <Button data-testid="refresh-btn" onClick={fetchAll} variant="outline" size="sm" disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
          </div>
        </div>

        {/* Metric Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <MetricCard testId="metric-total-events" title="Total Events" value={stats?.total_events ?? 0} icon={Activity} color="bg-cyan-500/15 text-cyan-400" />
          <MetricCard testId="metric-pending" title="Pending" value={stats?.pending_changes ?? 0} icon={Clock} color="bg-amber-500/15 text-amber-400" />
          <MetricCard testId="metric-acked" title="Acked" value={stats?.acked_changes ?? 0} icon={CheckCircle} color="bg-emerald-500/15 text-emerald-400" />
          <MetricCard testId="metric-failed" title="Failed" value={stats?.failed_changes ?? 0} icon={XCircle} color="bg-red-500/15 text-red-400" />
          <MetricCard testId="metric-drift" title="Drift" value={stats?.drift_count ?? 0} icon={AlertTriangle} color="bg-amber-500/15 text-amber-400" />
          <MetricCard testId="metric-outbound" title="Outbound" value={stats?.total_outbound_pushes ?? 0} icon={ArrowUpDown} color="bg-violet-500/15 text-violet-400" />
        </div>

        {/* Engine Status + Drift Mode */}
        {engineStats && (
          <Card className="bg-white border-gray-200">
            <CardContent className="p-4">
              <div className="flex items-center gap-6 flex-wrap text-sm">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${engineStats.buffer?.running ? 'bg-emerald-400 animate-pulse' : 'bg-gray-400'}`} />
                  <span className="text-gray-600">Buffer: {engineStats.buffer?.running ? 'Active' : 'Idle'}</span>
                  <span className="text-gray-600">({engineStats.buffer?.total_buffered_events ?? 0} buffered)</span>
                </div>
                <div className="flex items-center gap-2">
                  <Shield className="w-3.5 h-3.5 text-gray-500" />
                  <span className="text-gray-600">Adapters:</span>
                  {(engineStats.registered_adapters || []).map(a => (
                    <Badge key={a} className="bg-gray-100 text-gray-700 border-gray-300 text-xs">{a}</Badge>
                  ))}
                </div>
                {driftMode && (
                  <div className="flex items-center gap-2">
                    <Timer className="w-3.5 h-3.5 text-gray-500" />
                    <span className="text-gray-600">Drift:</span>
                    <Badge
                      data-testid="drift-mode-badge"
                      className={`text-xs cursor-pointer transition-colors ${
                        driftMode.mode === 'recovery'
                          ? 'bg-amber-500/15 text-amber-400 border-amber-500/30 hover:bg-amber-500/25'
                          : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/25'
                      }`}
                      onClick={toggleDriftMode}
                    >
                      {driftMode.mode} ({driftMode.interval}s)
                    </Badge>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Operational Metrics Cards */}
        {opMetrics && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Provider Health */}
            {Object.entries(opMetrics.provider_health || {}).map(([prov, h]) => (
              <Card key={prov} data-testid={`health-card-${prov}`} className="bg-white border-gray-200">
                <CardHeader className="pb-2 pt-3 px-4">
                  <CardTitle className="text-xs text-gray-500 flex items-center gap-1.5">
                    <Gauge className="w-3.5 h-3.5" /> {prov} Health
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <p className="text-lg font-bold text-emerald-400">{h.ack_rate}%</p>
                      <p className="text-[10px] text-gray-600">ACK Rate</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-red-400">{h.error_rate}%</p>
                      <p className="text-[10px] text-gray-600">Error Rate</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-amber-400">{h.retry_rate}%</p>
                      <p className="text-[10px] text-gray-600">Retry Rate</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}

            {/* Latency Percentiles */}
            {Object.entries(opMetrics.performance || {}).map(([prov, p]) => (
              <Card key={`perf-${prov}`} data-testid={`perf-card-${prov}`} className="bg-white border-gray-200">
                <CardHeader className="pb-2 pt-3 px-4">
                  <CardTitle className="text-xs text-gray-500 flex items-center gap-1.5">
                    <BarChart3 className="w-3.5 h-3.5" /> {prov} Latency
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <p className="text-lg font-bold text-cyan-400">{p.p50}ms</p>
                      <p className="text-[10px] text-gray-600">P50</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-amber-400">{p.p95}ms</p>
                      <p className="text-[10px] text-gray-600">P95</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-rose-400">{p.p99}ms</p>
                      <p className="text-[10px] text-gray-600">P99</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}

            {/* Queue Stats */}
            {opMetrics.queue && (
              <Card data-testid="queue-stats-card" className="bg-white border-gray-200">
                <CardHeader className="pb-2 pt-3 px-4">
                  <CardTitle className="text-xs text-gray-500 flex items-center gap-1.5">
                    <Inbox className="w-3.5 h-3.5" /> Queue
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-3">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div>
                      <p className="text-lg font-bold text-blue-400">{opMetrics.queue.queue_depth}</p>
                      <p className="text-[10px] text-gray-600">Queue Depth</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-amber-400">{opMetrics.queue.retry_backlog}</p>
                      <p className="text-[10px] text-gray-600">Retry Backlog</p>
                    </div>
                    <div>
                      <p className="text-lg font-bold text-red-400">{opMetrics.queue.dead_letter_count}</p>
                      <p className="text-[10px] text-gray-600">Dead Letters</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Tabs */}
        <Tabs defaultValue="queue" className="space-y-4">
          <TabsList className="bg-gray-100 border border-gray-200 p-1">
            <TabsTrigger data-testid="tab-queue" value="queue" className="data-[state=active]:bg-white data-[state=active]:shadow-sm text-xs sm:text-sm">Queue Monitor</TabsTrigger>
            <TabsTrigger data-testid="tab-outbound" value="outbound" className="data-[state=active]:bg-white data-[state=active]:shadow-sm text-xs sm:text-sm">Outbound Logs</TabsTrigger>
            <TabsTrigger data-testid="tab-drift" value="drift" className="data-[state=active]:bg-white data-[state=active]:shadow-sm text-xs sm:text-sm">Drift</TabsTrigger>
            <TabsTrigger data-testid="tab-events" value="events" className="data-[state=active]:bg-white data-[state=active]:shadow-sm text-xs sm:text-sm">Events</TabsTrigger>
            <TabsTrigger data-testid="tab-harness" value="harness" className="data-[state=active]:bg-white data-[state=active]:shadow-sm text-xs sm:text-sm">Test Harness</TabsTrigger>
          </TabsList>

          {/* Queue Monitor Tab */}
          <TabsContent value="queue" className="space-y-4">
            <div className="flex gap-3 flex-wrap">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger data-testid="status-filter" className="w-[140px] bg-white border-gray-200 text-sm">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent className="bg-white border-gray-200">
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="acked">Acked</SelectItem>
                  <SelectItem value="failed_retryable">Retryable</SelectItem>
                  <SelectItem value="manual_review">Failed</SelectItem>
                </SelectContent>
              </Select>
              <Select value={providerFilter} onValueChange={setProviderFilter}>
                <SelectTrigger data-testid="provider-filter" className="w-[160px] bg-white border-gray-200 text-sm">
                  <SelectValue placeholder="Provider" />
                </SelectTrigger>
                <SelectContent className="bg-white border-gray-200">
                  <SelectItem value="all">All Providers</SelectItem>
                  <SelectItem value="hotelrunner">HotelRunner</SelectItem>
                  <SelectItem value="exely">Exely</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Card className="bg-white border-gray-200">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm text-gray-600">Change Sets ({filteredCS.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="change-sets-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 text-gray-500 text-xs">
                        <th className="text-left py-2.5 px-4 font-medium">Provider</th>
                        <th className="text-left py-2.5 px-4 font-medium">Scope</th>
                        <th className="text-left py-2.5 px-4 font-medium">Room</th>
                        <th className="text-left py-2.5 px-4 font-medium">Dates</th>
                        <th className="text-left py-2.5 px-4 font-medium">Status</th>
                        <th className="text-left py-2.5 px-4 font-medium">Attempts</th>
                        <th className="text-left py-2.5 px-4 font-medium">Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredCS.length === 0 ? (
                        <tr><td colSpan={7} className="text-center py-8 text-gray-600">No change sets found</td></tr>
                      ) : filteredCS.map((cs, i) => (
                        <tr key={cs.id || i} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-gray-100 text-gray-700 border-gray-300 text-xs">{cs.provider}</Badge>
                          </td>
                          <td className="py-2.5 px-4"><ScopeBadge scope={cs.change_scope} /></td>
                          <td className="py-2.5 px-4 text-gray-700 font-mono text-xs">{cs.room_type_code}{cs.rate_plan_code ? `/${cs.rate_plan_code}` : ''}</td>
                          <td className="py-2.5 px-4 text-gray-600 text-xs">{cs.date_from} → {cs.date_to}</td>
                          <td className="py-2.5 px-4"><StatusBadge status={cs.status} /></td>
                          <td className="py-2.5 px-4 text-gray-600 text-xs">{cs.outbound_attempt_count}</td>
                          <td className="py-2.5 px-4 text-gray-500 text-xs">{cs.updated_at ? new Date(cs.updated_at).toLocaleString('tr-TR') : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Outbound Logs Tab */}
          <TabsContent value="outbound" className="space-y-4">
            <Card className="bg-white border-gray-200">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm text-gray-600">Outbound Push Logs ({outboundLogs.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="outbound-logs-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 text-gray-500 text-xs">
                        <th className="text-left py-2.5 px-4 font-medium">Provider</th>
                        <th className="text-left py-2.5 px-4 font-medium">Action</th>
                        <th className="text-left py-2.5 px-4 font-medium">Success</th>
                        <th className="text-left py-2.5 px-4 font-medium">Status</th>
                        <th className="text-left py-2.5 px-4 font-medium">Duration</th>
                        <th className="text-left py-2.5 px-4 font-medium">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outboundLogs.length === 0 ? (
                        <tr><td colSpan={6} className="text-center py-8 text-gray-600">No outbound logs</td></tr>
                      ) : outboundLogs.map((log, i) => (
                        <tr key={log.id || i} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-gray-100 text-gray-700 border-gray-300 text-xs">{log.provider}</Badge>
                          </td>
                          <td className="py-2.5 px-4 text-gray-600 text-xs font-mono">{log.endpoint_or_action}</td>
                          <td className="py-2.5 px-4">
                            {log.success
                              ? <CheckCircle className="w-4 h-4 text-emerald-400" />
                              : <XCircle className="w-4 h-4 text-red-400" />}
                          </td>
                          <td className="py-2.5 px-4 text-gray-600 text-xs">{log.status_code || '-'}</td>
                          <td className="py-2.5 px-4 text-gray-600 text-xs">{log.duration_ms}ms</td>
                          <td className="py-2.5 px-4 text-gray-500 text-xs">{log.pushed_at ? new Date(log.pushed_at).toLocaleString('tr-TR') : '-'}</td>
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
            <Card className="bg-white border-gray-200">
              <CardHeader className="pb-2 pt-4 px-4 flex flex-row items-center justify-between">
                <CardTitle className="text-sm text-gray-600">Drift States ({driftStates.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="drift-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 text-gray-500 text-xs">
                        <th className="text-left py-2.5 px-4 font-medium">Provider</th>
                        <th className="text-left py-2.5 px-4 font-medium">Room</th>
                        <th className="text-left py-2.5 px-4 font-medium">Dates</th>
                        <th className="text-left py-2.5 px-4 font-medium">Drift</th>
                        <th className="text-left py-2.5 px-4 font-medium">PMS Hash</th>
                        <th className="text-left py-2.5 px-4 font-medium">Provider Hash</th>
                        <th className="text-left py-2.5 px-4 font-medium">Last Check</th>
                      </tr>
                    </thead>
                    <tbody>
                      {driftStates.length === 0 ? (
                        <tr><td colSpan={7} className="text-center py-8 text-gray-600">No drift data. Run a drift check to compare PMS vs provider state.</td></tr>
                      ) : driftStates.map((ds, i) => (
                        <tr key={i} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-gray-100 text-gray-700 border-gray-300 text-xs">{ds.provider}</Badge>
                          </td>
                          <td className="py-2.5 px-4 text-gray-700 font-mono text-xs">{ds.room_type_code}{ds.rate_plan_code ? `/${ds.rate_plan_code}` : ''}</td>
                          <td className="py-2.5 px-4 text-gray-600 text-xs">{ds.date_from} → {ds.date_to}</td>
                          <td className="py-2.5 px-4">
                            {ds.drift_detected
                              ? <Badge className="bg-red-500/15 text-red-400 border-red-500/30 text-xs">Drift</Badge>
                              : <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs">OK</Badge>}
                          </td>
                          <td className="py-2.5 px-4 text-gray-500 font-mono text-xs">{ds.pms_hash?.slice(0, 8) || '-'}</td>
                          <td className="py-2.5 px-4 text-gray-500 font-mono text-xs">{ds.provider_hash?.slice(0, 8) || '-'}</td>
                          <td className="py-2.5 px-4 text-gray-500 text-xs">{ds.last_checked_at ? new Date(ds.last_checked_at).toLocaleString('tr-TR') : '-'}</td>
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
            <Card className="bg-white border-gray-200">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm text-gray-600">Recent ARI Events ({events.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="events-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 text-gray-500 text-xs">
                        <th className="text-left py-2.5 px-4 font-medium">Source</th>
                        <th className="text-left py-2.5 px-4 font-medium">Type</th>
                        <th className="text-left py-2.5 px-4 font-medium">Room</th>
                        <th className="text-left py-2.5 px-4 font-medium">Dates</th>
                        <th className="text-left py-2.5 px-4 font-medium">Payload</th>
                        <th className="text-left py-2.5 px-4 font-medium">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {events.length === 0 ? (
                        <tr><td colSpan={6} className="text-center py-8 text-gray-600">No events yet</td></tr>
                      ) : events.map((ev, i) => (
                        <tr key={ev.id || i} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-gray-100 text-gray-700 border-gray-300 text-xs">{ev.source_service}</Badge>
                          </td>
                          <td className="py-2.5 px-4"><ScopeBadge scope={ev.event_type} /></td>
                          <td className="py-2.5 px-4 text-gray-700 font-mono text-xs">{ev.room_type_code}{ev.rate_plan_code ? `/${ev.rate_plan_code}` : ''}</td>
                          <td className="py-2.5 px-4 text-gray-600 text-xs">{ev.date_from} → {ev.date_to}</td>
                          <td className="py-2.5 px-4 text-gray-500 text-xs font-mono max-w-[200px] truncate">{JSON.stringify(ev.payload)}</td>
                          <td className="py-2.5 px-4 text-gray-500 text-xs">{ev.created_at ? new Date(ev.created_at).toLocaleString('tr-TR') : '-'}</td>
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
              {['hotelrunner', 'exely'].map(provider => (
                <Card key={provider} data-testid={`test-harness-${provider}`} className="bg-white border-gray-200">
                  <CardHeader className="pb-2 pt-4 px-4 flex flex-row items-center justify-between">
                    <div>
                      <CardTitle className="text-sm text-gray-700 capitalize">{provider} Validation</CardTitle>
                      <CardDescription className="text-xs text-gray-600">Sandbox / Live test checklist</CardDescription>
                    </div>
                    <Button
                      data-testid={`run-test-${provider}`}
                      size="sm"
                      onClick={() => runProviderTest(provider)}
                      disabled={testRunning === provider}
                      className="bg-violet-600 hover:bg-violet-700 text-xs"
                    >
                      {testRunning === provider
                        ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Running...</>
                        : <><Play className="w-3 h-3 mr-1" /> Run All</>}
                    </Button>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    {testResults[provider]?.results ? (
                      <div className="space-y-1.5">
                        {testResults[provider].results.map((r, i) => (
                          <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded bg-gray-100/40 text-xs">
                            <div className="flex items-center gap-2">
                              {r.success
                                ? <CheckCircle className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                                : <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />}
                              <span className="text-gray-700">{r.step}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-gray-600 max-w-[200px] truncate">{r.detail}</span>
                              <span className="text-gray-700">{r.duration_ms}ms</span>
                            </div>
                          </div>
                        ))}
                        {testResults[provider].summary && (
                          <div className="mt-2 pt-2 border-t border-gray-200 flex gap-3 text-xs">
                            <span className="text-emerald-400">{testResults[provider].summary.passed} passed</span>
                            <span className="text-red-400">{testResults[provider].summary.failed} failed</span>
                            <span className="text-gray-600">/ {testResults[provider].summary.total} total</span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-gray-600 py-4 text-center">Click "Run All" to execute the validation checklist</p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
};

export default ARIPushDashboard;
