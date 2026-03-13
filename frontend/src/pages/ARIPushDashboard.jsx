import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Activity, ArrowUpDown, CheckCircle, XCircle, Clock,
  RefreshCw, AlertTriangle, Loader2, Zap, BarChart3,
  ArrowRightLeft, Shield
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const StatusBadge = ({ status }) => {
  const map = {
    pending: { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30', label: 'Pending' },
    queued: { color: 'bg-blue-500/15 text-blue-400 border-blue-500/30', label: 'Queued' },
    pushed: { color: 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30', label: 'Pushed' },
    acked: { color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', label: 'Acked' },
    failed_retryable: { color: 'bg-orange-500/15 text-orange-400 border-orange-500/30', label: 'Retry' },
    manual_review: { color: 'bg-red-500/15 text-red-400 border-red-500/30', label: 'Failed' },
    skipped: { color: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30', label: 'Skipped' },
  };
  const s = map[status] || { color: 'bg-zinc-500/15 text-zinc-400', label: status };
  return <Badge data-testid={`status-badge-${status}`} className={`${s.color} border text-xs font-medium`}>{s.label}</Badge>;
};

const ScopeBadge = ({ scope }) => {
  const map = {
    availability: { color: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30', icon: '◈' },
    rate: { color: 'bg-violet-500/15 text-violet-400 border-violet-500/30', icon: '₺' },
    restriction: { color: 'bg-rose-500/15 text-rose-400 border-rose-500/30', icon: '⊘' },
  };
  const s = map[scope] || { color: 'bg-zinc-500/15 text-zinc-400', icon: '?' };
  return <Badge className={`${s.color} border text-xs`}>{s.icon} {scope}</Badge>;
};

const MetricCard = ({ title, value, icon: Icon, color, testId }) => (
  <Card data-testid={testId} className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
    <CardContent className="p-4 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs text-zinc-500 font-medium">{title}</p>
        <p className="text-2xl font-bold text-zinc-100">{value}</p>
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

  const tenantId = tenant?.id || '044f122b-87b5-480a-88b4-b9534b0c8c90';
  const propertyId = tenant?.property_id || 'prop-001';

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = `tenant_id=${tenantId}&property_id=${propertyId}`;
      const [statsRes, engineRes, csRes, logsRes, driftRes, evRes] = await Promise.all([
        axios.get(`${API}/api/channel-manager/ari/stats?${params}`).catch(() => ({ data: {} })),
        axios.get(`${API}/api/channel-manager/ari/engine-stats`).catch(() => ({ data: {} })),
        axios.get(`${API}/api/channel-manager/ari/change-sets?${params}&limit=100`).catch(() => ({ data: { change_sets: [] } })),
        axios.get(`${API}/api/channel-manager/ari/outbound-logs?${params}&limit=50`).catch(() => ({ data: { logs: [] } })),
        axios.get(`${API}/api/channel-manager/ari/drift?${params}&limit=50`).catch(() => ({ data: { drift_states: [] } })),
        axios.get(`${API}/api/channel-manager/ari/events?${params}&limit=50`).catch(() => ({ data: { events: [] } })),
      ]);
      setStats(statsRes.data);
      setEngineStats(engineRes.data);
      setChangeSets(csRes.data.change_sets || []);
      setOutboundLogs(logsRes.data.logs || []);
      setDriftStates(driftRes.data.drift_states || []);
      setEvents(evRes.data.events || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [tenantId, propertyId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const pushPending = async () => {
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/ari/push`, {
        tenant_id: tenantId, provider: providerFilter === 'all' ? null : providerFilter,
      });
      toast.success(`Pushed: ${data.pushed}, Skipped: ${data.skipped}, Failed: ${data.failed}`);
      fetchAll();
    } catch { toast.error('Push failed'); }
  };

  const filteredCS = changeSets.filter(cs => {
    if (statusFilter !== 'all' && cs.status !== statusFilter) return false;
    if (providerFilter !== 'all' && cs.provider !== providerFilter) return false;
    return true;
  });

  return (
    <Layout user={user} onLogout={onLogout} title="ARI Push Engine">
      <div data-testid="ari-push-dashboard" className="space-y-6 p-4 sm:p-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-zinc-100 tracking-tight">ARI Push Engine</h1>
            <p className="text-sm text-zinc-500 mt-1">Event-driven availability, rate & restriction push pipeline</p>
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
          <MetricCard testId="metric-drift" title="Drift" value={stats?.drift_count ?? 0} icon={AlertTriangle} color="bg-orange-500/15 text-orange-400" />
          <MetricCard testId="metric-outbound" title="Outbound" value={stats?.total_outbound_pushes ?? 0} icon={ArrowUpDown} color="bg-violet-500/15 text-violet-400" />
        </div>

        {/* Engine Status */}
        {engineStats && (
          <Card className="bg-zinc-900/60 border-zinc-800">
            <CardContent className="p-4">
              <div className="flex items-center gap-6 flex-wrap text-sm">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${engineStats.buffer?.running ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-600'}`} />
                  <span className="text-zinc-400">Buffer: {engineStats.buffer?.running ? 'Active' : 'Idle'}</span>
                  <span className="text-zinc-600">({engineStats.buffer?.total_buffered_events ?? 0} buffered)</span>
                </div>
                <div className="flex items-center gap-2">
                  <Shield className="w-3.5 h-3.5 text-zinc-500" />
                  <span className="text-zinc-400">Adapters:</span>
                  {(engineStats.registered_adapters || []).map(a => (
                    <Badge key={a} className="bg-zinc-800 text-zinc-300 border-zinc-700 text-xs">{a}</Badge>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Tabs */}
        <Tabs defaultValue="queue" className="space-y-4">
          <TabsList className="bg-zinc-900/80 border border-zinc-800 p-1">
            <TabsTrigger data-testid="tab-queue" value="queue" className="data-[state=active]:bg-zinc-800 text-xs sm:text-sm">Queue Monitor</TabsTrigger>
            <TabsTrigger data-testid="tab-outbound" value="outbound" className="data-[state=active]:bg-zinc-800 text-xs sm:text-sm">Outbound Logs</TabsTrigger>
            <TabsTrigger data-testid="tab-drift" value="drift" className="data-[state=active]:bg-zinc-800 text-xs sm:text-sm">Drift</TabsTrigger>
            <TabsTrigger data-testid="tab-events" value="events" className="data-[state=active]:bg-zinc-800 text-xs sm:text-sm">Events</TabsTrigger>
          </TabsList>

          {/* Queue Monitor Tab */}
          <TabsContent value="queue" className="space-y-4">
            <div className="flex gap-3 flex-wrap">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger data-testid="status-filter" className="w-[140px] bg-zinc-900 border-zinc-800 text-sm">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800">
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="acked">Acked</SelectItem>
                  <SelectItem value="failed_retryable">Retryable</SelectItem>
                  <SelectItem value="manual_review">Failed</SelectItem>
                </SelectContent>
              </Select>
              <Select value={providerFilter} onValueChange={setProviderFilter}>
                <SelectTrigger data-testid="provider-filter" className="w-[160px] bg-zinc-900 border-zinc-800 text-sm">
                  <SelectValue placeholder="Provider" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800">
                  <SelectItem value="all">All Providers</SelectItem>
                  <SelectItem value="hotelrunner">HotelRunner</SelectItem>
                  <SelectItem value="exely">Exely</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm text-zinc-400">Change Sets ({filteredCS.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="change-sets-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-500 text-xs">
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
                        <tr><td colSpan={7} className="text-center py-8 text-zinc-600">No change sets found</td></tr>
                      ) : filteredCS.map((cs, i) => (
                        <tr key={cs.id || i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-zinc-800 text-zinc-300 border-zinc-700 text-xs">{cs.provider}</Badge>
                          </td>
                          <td className="py-2.5 px-4"><ScopeBadge scope={cs.change_scope} /></td>
                          <td className="py-2.5 px-4 text-zinc-300 font-mono text-xs">{cs.room_type_code}{cs.rate_plan_code ? `/${cs.rate_plan_code}` : ''}</td>
                          <td className="py-2.5 px-4 text-zinc-400 text-xs">{cs.date_from} → {cs.date_to}</td>
                          <td className="py-2.5 px-4"><StatusBadge status={cs.status} /></td>
                          <td className="py-2.5 px-4 text-zinc-400 text-xs">{cs.outbound_attempt_count}</td>
                          <td className="py-2.5 px-4 text-zinc-500 text-xs">{cs.updated_at ? new Date(cs.updated_at).toLocaleString('tr-TR') : '-'}</td>
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
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm text-zinc-400">Outbound Push Logs ({outboundLogs.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="outbound-logs-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-500 text-xs">
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
                        <tr><td colSpan={6} className="text-center py-8 text-zinc-600">No outbound logs</td></tr>
                      ) : outboundLogs.map((log, i) => (
                        <tr key={log.id || i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-zinc-800 text-zinc-300 border-zinc-700 text-xs">{log.provider}</Badge>
                          </td>
                          <td className="py-2.5 px-4 text-zinc-400 text-xs font-mono">{log.endpoint_or_action}</td>
                          <td className="py-2.5 px-4">
                            {log.success
                              ? <CheckCircle className="w-4 h-4 text-emerald-400" />
                              : <XCircle className="w-4 h-4 text-red-400" />}
                          </td>
                          <td className="py-2.5 px-4 text-zinc-400 text-xs">{log.status_code || '-'}</td>
                          <td className="py-2.5 px-4 text-zinc-400 text-xs">{log.duration_ms}ms</td>
                          <td className="py-2.5 px-4 text-zinc-500 text-xs">{log.pushed_at ? new Date(log.pushed_at).toLocaleString('tr-TR') : '-'}</td>
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
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-4 flex flex-row items-center justify-between">
                <CardTitle className="text-sm text-zinc-400">Drift States ({driftStates.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="drift-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-500 text-xs">
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
                        <tr><td colSpan={7} className="text-center py-8 text-zinc-600">No drift data. Run a drift check to compare PMS vs provider state.</td></tr>
                      ) : driftStates.map((ds, i) => (
                        <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-zinc-800 text-zinc-300 border-zinc-700 text-xs">{ds.provider}</Badge>
                          </td>
                          <td className="py-2.5 px-4 text-zinc-300 font-mono text-xs">{ds.room_type_code}{ds.rate_plan_code ? `/${ds.rate_plan_code}` : ''}</td>
                          <td className="py-2.5 px-4 text-zinc-400 text-xs">{ds.date_from} → {ds.date_to}</td>
                          <td className="py-2.5 px-4">
                            {ds.drift_detected
                              ? <Badge className="bg-red-500/15 text-red-400 border-red-500/30 text-xs">Drift</Badge>
                              : <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs">OK</Badge>}
                          </td>
                          <td className="py-2.5 px-4 text-zinc-500 font-mono text-xs">{ds.pms_hash?.slice(0, 8) || '-'}</td>
                          <td className="py-2.5 px-4 text-zinc-500 font-mono text-xs">{ds.provider_hash?.slice(0, 8) || '-'}</td>
                          <td className="py-2.5 px-4 text-zinc-500 text-xs">{ds.last_checked_at ? new Date(ds.last_checked_at).toLocaleString('tr-TR') : '-'}</td>
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
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm text-zinc-400">Recent ARI Events ({events.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table data-testid="events-table" className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-500 text-xs">
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
                        <tr><td colSpan={6} className="text-center py-8 text-zinc-600">No events yet</td></tr>
                      ) : events.map((ev, i) => (
                        <tr key={ev.id || i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                          <td className="py-2.5 px-4">
                            <Badge className="bg-zinc-800 text-zinc-300 border-zinc-700 text-xs">{ev.source_service}</Badge>
                          </td>
                          <td className="py-2.5 px-4"><ScopeBadge scope={ev.event_type} /></td>
                          <td className="py-2.5 px-4 text-zinc-300 font-mono text-xs">{ev.room_type_code}{ev.rate_plan_code ? `/${ev.rate_plan_code}` : ''}</td>
                          <td className="py-2.5 px-4 text-zinc-400 text-xs">{ev.date_from} → {ev.date_to}</td>
                          <td className="py-2.5 px-4 text-zinc-500 text-xs font-mono max-w-[200px] truncate">{JSON.stringify(ev.payload)}</td>
                          <td className="py-2.5 px-4 text-zinc-500 text-xs">{ev.created_at ? new Date(ev.created_at).toLocaleString('tr-TR') : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default ARIPushDashboard;
