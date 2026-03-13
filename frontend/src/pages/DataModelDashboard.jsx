import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
  Database, Link2, Grid3X3, FileText, GitBranch,
  AlertTriangle, RefreshCw, Trash2, CheckCircle,
  Loader2, Server, Layers, ArrowRightLeft, Clock,
  Play, Repeat, Download, Activity, Shield, Eye,
  XCircle, Search, BarChart3
} from 'lucide-react';

const API = process.env.REACT_APP_BACKEND_URL;

const ProviderBadge = ({ provider }) => {
  const map = {
    hotelrunner: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    exely: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  };
  return (
    <Badge data-testid={`provider-badge-${provider}`} className={`${map[provider] || 'bg-zinc-500/15 text-zinc-400'} border text-xs font-medium`}>
      {provider}
    </Badge>
  );
};

const StatusDot = ({ status }) => {
  const colors = {
    active: 'bg-emerald-400', draft: 'bg-amber-400', paused: 'bg-zinc-400',
    error: 'bg-red-400', disabled: 'bg-zinc-600',
    open: 'bg-red-400', investigating: 'bg-amber-400', resolved: 'bg-emerald-400', dismissed: 'bg-zinc-400',
    confirmed: 'bg-emerald-400', modified: 'bg-amber-400', cancelled: 'bg-red-400', pending: 'bg-blue-400',
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] || 'bg-zinc-500'}`} />;
};

const CollectionCard = ({ name, count, icon: Icon, color }) => (
  <Card className="bg-zinc-900/60 border-zinc-800 backdrop-blur">
    <CardContent className="p-4 flex items-center gap-3">
      <div className={`p-2 rounded-lg ${color}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-zinc-500 font-mono truncate">{name}</p>
        <p className="text-xl font-bold text-zinc-100">{count}</p>
      </div>
    </CardContent>
  </Card>
);

const ProcessingBadge = ({ status }) => {
  const map = {
    pending: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    processed: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    failed: 'bg-red-500/15 text-red-400 border-red-500/30',
    duplicate: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30',
    stale: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  };
  return <Badge className={`${map[status] || 'bg-zinc-500/15 text-zinc-400'} border text-xs`}>{status}</Badge>;
};

const DataModelDashboard = ({ user, tenant, onLogout }) => {
  const [loading, setLoading] = useState(false);
  const [schema, setSchema] = useState(null);
  const [connections, setConnections] = useState([]);
  const [roomMappings, setRoomMappings] = useState([]);
  const [ratePlanMappings, setRatePlanMappings] = useState([]);
  const [rawEvents, setRawEvents] = useState([]);
  const [lineages, setLineages] = useState([]);
  const [reconCases, setReconCases] = useState([]);
  const [reconSummary, setReconSummary] = useState(null);
  const [reconDashboard, setReconDashboard] = useState(null);
  const [reconMetrics, setReconMetrics] = useState(null);
  const [reconFilter, setReconFilter] = useState({ status: '', severity: '', case_type: '', provider: '' });
  const [reconRunning, setReconRunning] = useState(false);
  const [ingestStatus, setIngestStatus] = useState(null);
  const [workerAction, setWorkerAction] = useState(null);

  const propertyId = tenant?.property_id || 'prop-001';

  const headers = useCallback(() => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const h = headers();
      const [schemaRes, connRes, roomRes, rateRes, eventsRes, lineageRes, casesRes, summaryRes, ingestRes, reconDashRes, reconMetricsRes] = await Promise.all([
        axios.get(`${API}/api/channel-manager/model/schema`, { headers: h }).catch(() => ({ data: null })),
        axios.get(`${API}/api/channel-manager/model/connections`, { headers: h }).catch(() => ({ data: { connections: [] } })),
        axios.get(`${API}/api/channel-manager/model/room-mappings?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { mappings: [] } })),
        axios.get(`${API}/api/channel-manager/model/rate-plan-mappings?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { mappings: [] } })),
        axios.get(`${API}/api/channel-manager/ingest/events?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { events: [] } })),
        axios.get(`${API}/api/channel-manager/model/lineage?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { lineages: [] } })),
        axios.get(`${API}/api/channel-manager/reconciliation/cases`, { headers: h }).catch(() => ({ data: { cases: [] } })),
        axios.get(`${API}/api/channel-manager/model/reconciliation/summary`, { headers: h }).catch(() => ({ data: null })),
        axios.get(`${API}/api/channel-manager/ingest/status?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: null })),
        axios.get(`${API}/api/channel-manager/reconciliation/dashboard`, { headers: h }).catch(() => ({ data: null })),
        axios.get(`${API}/api/channel-manager/reconciliation/metrics`, { headers: h }).catch(() => ({ data: null })),
      ]);
      setSchema(schemaRes.data);
      setConnections(connRes.data.connections || []);
      setRoomMappings(roomRes.data.mappings || []);
      setRatePlanMappings(rateRes.data.mappings || []);
      setRawEvents(eventsRes.data.events || []);
      setLineages(lineageRes.data.lineages || []);
      setReconCases(casesRes.data.cases || []);
      setReconSummary(summaryRes.data);
      setIngestStatus(ingestRes.data);
      setReconDashboard(reconDashRes.data);
      setReconMetrics(reconMetricsRes.data);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [propertyId, headers]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const activateConnection = async (id) => {
    try {
      await axios.post(`${API}/api/channel-manager/model/connections/${id}/activate`, {}, { headers: headers() });
      toast.success('Connection activated');
      fetchAll();
    } catch { toast.error('Activation failed'); }
  };

  const deleteConnection = async (id) => {
    try {
      await axios.delete(`${API}/api/channel-manager/model/connections/${id}`, { headers: headers() });
      toast.success('Connection deleted');
      fetchAll();
    } catch { toast.error('Delete failed'); }
  };

  const resolveCase = async (caseId) => {
    try {
      await axios.post(`${API}/api/channel-manager/reconciliation/cases/${caseId}/resolve`, { resolution: 'Manually resolved' }, { headers: headers() });
      toast.success('Case resolved');
      fetchAll();
    } catch { toast.error('Resolve failed'); }
  };

  const ignoreCase = async (caseId) => {
    try {
      await axios.post(`${API}/api/channel-manager/reconciliation/cases/${caseId}/ignore`, { reason: 'Manually ignored' }, { headers: headers() });
      toast.success('Case ignored');
      fetchAll();
    } catch { toast.error('Ignore failed'); }
  };

  const acknowledgeCase = async (caseId) => {
    try {
      await axios.post(`${API}/api/channel-manager/reconciliation/cases/${caseId}/acknowledge`, { note: 'Under review' }, { headers: headers() });
      toast.success('Case acknowledged');
      fetchAll();
    } catch { toast.error('Acknowledge failed'); }
  };

  const triggerReconciliation = async () => {
    setReconRunning(true);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/reconciliation/run`, {}, { headers: headers() });
      const r = data.result || {};
      toast.success(`Reconciliation done: ${r.mismatches_found || 0} mismatches, ${r.cases_created || 0} cases created`);
      fetchAll();
    } catch { toast.error('Reconciliation failed'); }
    setReconRunning(false);
  };

  const fetchFilteredCases = async () => {
    const h = headers();
    const params = new URLSearchParams();
    if (reconFilter.status) params.set('status', reconFilter.status);
    if (reconFilter.severity) params.set('severity', reconFilter.severity);
    if (reconFilter.case_type) params.set('case_type', reconFilter.case_type);
    if (reconFilter.provider) params.set('provider', reconFilter.provider);
    try {
      const { data } = await axios.get(`${API}/api/channel-manager/reconciliation/cases?${params.toString()}`, { headers: h });
      setReconCases(data.cases || []);
    } catch { toast.error('Filter failed'); }
  };

  const triggerWorker = async (action) => {
    setWorkerAction(action);
    try {
      const { data } = await axios.post(`${API}/api/channel-manager/ingest/workers/${action}`, {}, { headers: headers() });
      const r = data.result || {};
      if (action === 'process') {
        toast.success(`Processed: ${r.processed || 0} events (${r.created || 0} created, ${r.updated || 0} updated, ${r.skipped || 0} skipped)`);
      } else if (action === 'replay') {
        toast.success(`Replayed: ${r.replayed || 0} events`);
      } else {
        toast.success(`${action} completed`);
      }
      fetchAll();
    } catch { toast.error(`Worker ${action} failed`); }
    setWorkerAction(null);
  };

  const eventStats = ingestStatus?.pipeline?.raw_events || {};
  const lineageStats = ingestStatus?.pipeline?.lineage || {};

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div data-testid="data-model-dashboard" className="space-y-6 p-4 md:p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100 flex items-center gap-2">
              <Database className="w-6 h-6 text-cyan-400" />
              Channel Manager
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              {schema ? `v${schema.model_version} — ${schema.total_collections} collections` : 'Loading...'} | hotelrunner + exely
            </p>
          </div>
          <Button data-testid="refresh-btn" variant="outline" size="sm" onClick={fetchAll} disabled={loading}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="ml-1.5">Refresh</span>
          </Button>
        </div>

        {/* Pipeline Overview Cards */}
        <div data-testid="collection-overview" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <CollectionCard name="raw_events" count={eventStats.total || 0} icon={FileText} color="bg-amber-500/15 text-amber-400" />
          <CollectionCard name="processed" count={eventStats.processed || 0} icon={CheckCircle} color="bg-emerald-500/15 text-emerald-400" />
          <CollectionCard name="pending" count={eventStats.pending || 0} icon={Clock} color="bg-blue-500/15 text-blue-400" />
          <CollectionCard name="lineage" count={lineageStats.total || 0} icon={GitBranch} color="bg-cyan-500/15 text-cyan-400" />
          <CollectionCard name="connections" count={connections.length} icon={Link2} color="bg-violet-500/15 text-violet-400" />
          <CollectionCard name="recon_cases" count={reconSummary?.total_open || 0} icon={AlertTriangle} color="bg-red-500/15 text-red-400" />
        </div>

        {/* Tabs */}
        <Tabs defaultValue="ingest" className="space-y-4">
          <TabsList data-testid="model-tabs" className="bg-zinc-900 border border-zinc-800 p-1 flex-wrap h-auto">
            <TabsTrigger value="ingest" className="data-[state=active]:bg-zinc-800 text-xs">
              <Activity className="w-3.5 h-3.5 mr-1" /> Ingest Pipeline
            </TabsTrigger>
            <TabsTrigger value="lineage" className="data-[state=active]:bg-zinc-800 text-xs">
              <GitBranch className="w-3.5 h-3.5 mr-1" /> Lineage
            </TabsTrigger>
            <TabsTrigger value="connections" className="data-[state=active]:bg-zinc-800 text-xs">
              <Link2 className="w-3.5 h-3.5 mr-1" /> Connections
            </TabsTrigger>
            <TabsTrigger value="mappings" className="data-[state=active]:bg-zinc-800 text-xs">
              <ArrowRightLeft className="w-3.5 h-3.5 mr-1" /> Mappings
            </TabsTrigger>
            <TabsTrigger value="reconciliation" className="data-[state=active]:bg-zinc-800 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 mr-1" /> Reconciliation
            </TabsTrigger>
          </TabsList>

          {/* Ingest Pipeline Tab */}
          <TabsContent value="ingest">
            <div className="space-y-4">
              {/* Worker Controls */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                      <Server className="w-4 h-4 text-cyan-400" />
                      Workers
                    </CardTitle>
                    <div className="flex gap-2">
                      <Button data-testid="trigger-process" size="sm" variant="outline"
                        className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10"
                        onClick={() => triggerWorker('process')} disabled={!!workerAction}>
                        {workerAction === 'process' ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Play className="w-3 h-3 mr-1" />}
                        Process Pending
                      </Button>
                      <Button data-testid="trigger-replay" size="sm" variant="outline"
                        className="h-7 text-xs border-amber-600 text-amber-400 hover:bg-amber-500/10"
                        onClick={() => triggerWorker('replay')} disabled={!!workerAction}>
                        {workerAction === 'replay' ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Repeat className="w-3 h-3 mr-1" />}
                        Replay Failed
                      </Button>
                      <Button data-testid="trigger-hr-pull" size="sm" variant="outline"
                        className="h-7 text-xs border-blue-600 text-blue-400 hover:bg-blue-500/10"
                        onClick={() => triggerWorker('pull/hotelrunner')} disabled={!!workerAction}>
                        <Download className="w-3 h-3 mr-1" /> HR Pull
                      </Button>
                      <Button data-testid="trigger-exely-pull" size="sm" variant="outline"
                        className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10"
                        onClick={() => triggerWorker('pull/exely')} disabled={!!workerAction}>
                        <Download className="w-3 h-3 mr-1" /> Exely Pull
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                {ingestStatus?.workers && (
                  <CardContent>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                      {Object.entries(ingestStatus.workers).map(([name, w]) => (
                        <div key={name} className="p-2 rounded bg-zinc-800/50 border border-zinc-700/50">
                          <p className="text-xs font-mono text-zinc-400">{name.replace('_', ' ')}</p>
                          <p className="text-xs text-zinc-500 mt-1">
                            Last: {w.last_run ? new Date(w.last_run).toLocaleTimeString() : 'never'}
                          </p>
                          <p className="text-xs text-zinc-500">Interval: {w.interval_seconds}s</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}
              </Card>

              {/* Raw Events */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <FileText className="w-4 h-4 text-amber-400" />
                    Raw Channel Events ({rawEvents.length})
                    <div className="flex gap-1 ml-auto">
                      <Badge className="bg-emerald-500/15 text-emerald-400 text-xs">{eventStats.processed || 0} processed</Badge>
                      <Badge className="bg-red-500/15 text-red-400 text-xs">{eventStats.failed || 0} failed</Badge>
                      <Badge className="bg-zinc-500/15 text-zinc-400 text-xs">{eventStats.duplicate || 0} dup</Badge>
                      <Badge className="bg-amber-500/15 text-amber-400 text-xs">{eventStats.stale || 0} stale</Badge>
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {rawEvents.length === 0 ? (
                    <p data-testid="no-raw-events" className="text-zinc-500 text-sm text-center py-6">No raw events</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                            <th className="text-left py-2 px-3">Provider</th>
                            <th className="text-left py-2 px-3">Ext Res ID</th>
                            <th className="text-left py-2 px-3">Event Type</th>
                            <th className="text-left py-2 px-3">Via</th>
                            <th className="text-left py-2 px-3">Status</th>
                            <th className="text-left py-2 px-3">Received</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rawEvents.slice(0, 20).map(e => (
                            <tr key={e.id} data-testid={`raw-event-${e.id}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                              <td className="py-2 px-3"><ProviderBadge provider={e.provider} /></td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{e.external_reservation_id || '-'}</td>
                              <td className="py-2 px-3 text-zinc-300 text-xs">{e.event_type}</td>
                              <td className="py-2 px-3"><Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{e.received_via}</Badge></td>
                              <td className="py-2 px-3"><ProcessingBadge status={e.processing_status} /></td>
                              <td className="py-2 px-3 text-zinc-500 text-xs">{new Date(e.received_at).toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Lineage Tab */}
          <TabsContent value="lineage">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <GitBranch className="w-4 h-4 text-emerald-400" />
                  Reservation Lineage ({lineages.length})
                  {lineageStats.by_status && Object.entries(lineageStats.by_status).map(([s, c]) => (
                    <Badge key={s} className="bg-zinc-700/50 text-zinc-300 text-xs ml-1">{s}: {c}</Badge>
                  ))}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {lineages.length === 0 ? (
                  <p data-testid="no-lineages" className="text-zinc-500 text-sm text-center py-6">No reservation lineage records</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                          <th className="text-left py-2 px-3">Provider</th>
                          <th className="text-left py-2 px-3">External ID</th>
                          <th className="text-left py-2 px-3">Guest</th>
                          <th className="text-left py-2 px-3">Stay</th>
                          <th className="text-left py-2 px-3">Amount</th>
                          <th className="text-left py-2 px-3">Source</th>
                          <th className="text-left py-2 px-3">Ver</th>
                          <th className="text-left py-2 px-3">Status</th>
                          <th className="text-left py-2 px-3">Decision</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lineages.map(l => (
                          <tr key={l.id} data-testid={`lineage-${l.id}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                            <td className="py-2 px-3"><ProviderBadge provider={l.provider} /></td>
                            <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{l.external_reservation_id}</td>
                            <td className="py-2 px-3 text-zinc-300 text-xs">{l.guest_name || '-'}</td>
                            <td className="py-2 px-3 text-zinc-400 text-xs">{l.arrival_date} → {l.departure_date}</td>
                            <td className="py-2 px-3 text-zinc-200 text-xs font-mono">{l.total_amount} {l.currency}</td>
                            <td className="py-2 px-3 text-zinc-500 text-xs">{l.source_system}</td>
                            <td className="py-2 px-3 text-zinc-400 text-xs">v{l.version}</td>
                            <td className="py-2 px-3">
                              <div className="flex items-center gap-1.5">
                                <StatusDot status={l.status} />
                                <span className="text-xs text-zinc-300">{l.status}</span>
                              </div>
                            </td>
                            <td className="py-2 px-3">
                              <Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{l.last_decision}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Connections Tab */}
          <TabsContent value="connections">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <Server className="w-4 h-4 text-blue-400" />
                  Provider Connections ({connections.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {connections.length === 0 ? (
                  <p data-testid="no-connections" className="text-zinc-500 text-sm text-center py-6">No connections configured</p>
                ) : (
                  <div className="space-y-3">
                    {connections.map(c => (
                      <div key={c.id} data-testid={`connection-${c.provider}`} className="flex items-center justify-between p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                        <div className="flex items-center gap-3 min-w-0">
                          <StatusDot status={c.status} />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-zinc-200 truncate">{c.display_name}</p>
                            <p className="text-xs text-zinc-500">{c.property_id} | Syncs: {c.total_syncs} | Errors: {c.total_errors}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 ml-2 shrink-0">
                          <ProviderBadge provider={c.provider} />
                          <Badge className="bg-zinc-700/50 text-zinc-300 border-zinc-600 text-xs">{c.status}</Badge>
                          {c.status === 'draft' && (
                            <Button data-testid={`activate-${c.provider}`} size="sm" variant="outline"
                              className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10"
                              onClick={() => activateConnection(c.id)}>
                              <CheckCircle className="w-3 h-3 mr-1" /> Activate
                            </Button>
                          )}
                          <Button data-testid={`delete-${c.provider}`} size="sm" variant="ghost"
                            className="h-7 text-xs text-red-400 hover:bg-red-500/10"
                            onClick={() => deleteConnection(c.id)}>
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Mappings Tab */}
          <TabsContent value="mappings">
            <div className="space-y-4">
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <Grid3X3 className="w-4 h-4 text-cyan-400" /> Room Mappings ({roomMappings.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {roomMappings.length === 0 ? (
                    <p className="text-zinc-500 text-sm text-center py-4">No room mappings</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                            <th className="text-left py-2 px-3">Provider</th>
                            <th className="text-left py-2 px-3">PMS Room Type</th>
                            <th className="py-2 px-1">→</th>
                            <th className="text-left py-2 px-3">Provider Code</th>
                            <th className="text-left py-2 px-3">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {roomMappings.map(m => (
                            <tr key={m.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                              <td className="py-2 px-3"><ProviderBadge provider={m.provider} /></td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.pms_room_type_id}</td>
                              <td className="py-2 px-1 text-zinc-600">→</td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.provider_room_code}</td>
                              <td className="py-2 px-3">
                                <Badge className={m.is_active ? 'bg-emerald-500/15 text-emerald-400 text-xs' : 'bg-zinc-500/15 text-zinc-400 text-xs'}>
                                  {m.is_active ? 'Active' : 'Inactive'}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <Layers className="w-4 h-4 text-violet-400" /> Rate Plan Mappings ({ratePlanMappings.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {ratePlanMappings.length === 0 ? (
                    <p className="text-zinc-500 text-sm text-center py-4">No rate plan mappings</p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                            <th className="text-left py-2 px-3">Provider</th>
                            <th className="text-left py-2 px-3">PMS Rate Plan</th>
                            <th className="py-2 px-1">→</th>
                            <th className="text-left py-2 px-3">Provider Code</th>
                            <th className="text-left py-2 px-3">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {ratePlanMappings.map(m => (
                            <tr key={m.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                              <td className="py-2 px-3"><ProviderBadge provider={m.provider} /></td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.pms_rate_plan_id}</td>
                              <td className="py-2 px-1 text-zinc-600">→</td>
                              <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.provider_rate_code}</td>
                              <td className="py-2 px-3">
                                <Badge className={m.is_active ? 'bg-emerald-500/15 text-emerald-400 text-xs' : 'bg-zinc-500/15 text-zinc-400 text-xs'}>
                                  {m.is_active ? 'Active' : 'Inactive'}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Reconciliation Tab */}
          <TabsContent value="reconciliation">
            <div className="space-y-4">
              {/* Reconciliation Worker & Controls */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                      <Shield className="w-4 h-4 text-cyan-400" />
                      Reconciliation Engine
                    </CardTitle>
                    <div className="flex gap-2">
                      <Button data-testid="trigger-reconciliation" size="sm" variant="outline"
                        className="h-7 text-xs border-cyan-600 text-cyan-400 hover:bg-cyan-500/10"
                        onClick={triggerReconciliation} disabled={reconRunning}>
                        {reconRunning ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Play className="w-3 h-3 mr-1" />}
                        Run Reconciliation
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                    {reconDashboard && (
                      <>
                        <div className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                          <p className="text-2xl font-bold text-red-400">{reconDashboard.open_cases}</p>
                          <p className="text-xs text-zinc-500">Open Cases</p>
                        </div>
                        {Object.entries(reconDashboard.severity_counts || {}).map(([sev, count]) => (
                          <div key={sev} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                            <p className={`text-2xl font-bold ${sev === 'critical' ? 'text-red-400' : sev === 'high' ? 'text-orange-400' : sev === 'medium' ? 'text-amber-400' : 'text-zinc-400'}`}>{count}</p>
                            <p className="text-xs text-zinc-500 capitalize">{sev}</p>
                          </div>
                        ))}
                      </>
                    )}
                    {reconDashboard?.worker && (
                      <div className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                        <p className="text-2xl font-bold text-cyan-400">{reconDashboard.worker.runs_total}</p>
                        <p className="text-xs text-zinc-500">Total Runs</p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Metrics */}
              {reconMetrics && (
                <Card data-testid="recon-metrics" className="bg-zinc-900/60 border-zinc-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-violet-400" /> Mismatch Metrics
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                      {[
                        { label: 'Missing Res.', value: reconMetrics.missing_reservations, color: 'text-orange-400' },
                        { label: 'Ghost Res.', value: reconMetrics.ghost_reservations, color: 'text-amber-400' },
                        { label: 'Status Conflict', value: reconMetrics.status_conflicts, color: 'text-red-400' },
                        { label: 'Amount Mismatch', value: reconMetrics.amount_mismatches, color: 'text-yellow-400' },
                        { label: 'Date Conflict', value: reconMetrics.date_conflicts, color: 'text-orange-400' },
                        { label: 'Duplicates', value: reconMetrics.duplicate_reservations, color: 'text-zinc-400' },
                      ].map(m => (
                        <div key={m.label} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50 text-center">
                          <p className={`text-xl font-bold ${m.color}`}>{m.value || 0}</p>
                          <p className="text-xs text-zinc-500">{m.label}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Provider Breakdown */}
              {reconDashboard?.provider_breakdown && Object.keys(reconDashboard.provider_breakdown).length > 0 && (
                <Card className="bg-zinc-900/60 border-zinc-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm text-zinc-200">Provider Breakdown</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex gap-4 flex-wrap">
                      {Object.entries(reconDashboard.provider_breakdown).map(([prov, count]) => (
                        <div key={prov} className="flex items-center gap-2">
                          <ProviderBadge provider={prov} />
                          <span className="text-zinc-200 font-bold">{count}</span>
                          <span className="text-zinc-500 text-xs">open cases</span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Filters */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardContent className="p-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Search className="w-4 h-4 text-zinc-500" />
                    <select data-testid="filter-status" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300"
                      value={reconFilter.status} onChange={e => setReconFilter(f => ({ ...f, status: e.target.value }))}>
                      <option value="">All Status</option>
                      <option value="open">Open</option>
                      <option value="acknowledged">Acknowledged</option>
                      <option value="resolved">Resolved</option>
                      <option value="ignored">Ignored</option>
                    </select>
                    <select data-testid="filter-severity" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300"
                      value={reconFilter.severity} onChange={e => setReconFilter(f => ({ ...f, severity: e.target.value }))}>
                      <option value="">All Severity</option>
                      <option value="critical">Critical</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                    <select data-testid="filter-type" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300"
                      value={reconFilter.case_type} onChange={e => setReconFilter(f => ({ ...f, case_type: e.target.value }))}>
                      <option value="">All Types</option>
                      <option value="missing_reservation">Missing Reservation</option>
                      <option value="ghost_reservation">Ghost Reservation</option>
                      <option value="amount_mismatch">Amount Mismatch</option>
                      <option value="date_conflict">Date Conflict</option>
                      <option value="status_conflict">Status Conflict</option>
                      <option value="duplicate_reservation">Duplicate Reservation</option>
                      <option value="missing_mapping">Missing Mapping</option>
                    </select>
                    <select data-testid="filter-provider" className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300"
                      value={reconFilter.provider} onChange={e => setReconFilter(f => ({ ...f, provider: e.target.value }))}>
                      <option value="">All Providers</option>
                      <option value="hotelrunner">HotelRunner</option>
                      <option value="exely">Exely</option>
                    </select>
                    <Button data-testid="apply-filters" size="sm" variant="outline" className="h-7 text-xs border-zinc-700 text-zinc-300"
                      onClick={fetchFilteredCases}>
                      Apply
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Cases List */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    Cases ({reconCases.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {reconCases.length === 0 ? (
                    <p data-testid="no-recon-cases" className="text-zinc-500 text-sm text-center py-6">No cases found</p>
                  ) : (
                    <div className="space-y-2">
                      {reconCases.map(c => (
                        <div key={c.id} data-testid={`recon-case-${c.id}`} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <StatusDot status={c.status} />
                                <ProviderBadge provider={c.provider} />
                                <Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{c.case_type?.replace(/_/g, ' ')}</Badge>
                                <Badge className={`text-xs border ${
                                  c.severity === 'critical' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                  c.severity === 'high' ? 'bg-orange-500/15 text-orange-400 border-orange-500/30' :
                                  c.severity === 'medium' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                                  'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'
                                }`}>{c.severity}</Badge>
                                <Badge className={`text-xs border ${
                                  c.status === 'open' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                  c.status === 'acknowledged' ? 'bg-blue-500/15 text-blue-400 border-blue-500/30' :
                                  c.status === 'resolved' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' :
                                  'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'
                                }`}>{c.status}</Badge>
                              </div>
                              <p className="text-xs text-zinc-400 truncate">{c.description}</p>
                              {c.external_reservation_id && (
                                <p className="text-xs text-zinc-600 font-mono mt-0.5">ext: {c.external_reservation_id}</p>
                              )}
                              {c.suggested_action && (
                                <p className="text-xs text-cyan-400/70 mt-0.5">{c.suggested_action}</p>
                              )}
                              {c.resolution && (
                                <p className="text-xs text-emerald-400/70 mt-0.5">Resolution: {c.resolution}</p>
                              )}
                            </div>
                            {(c.status === 'open' || c.status === 'acknowledged') && (
                              <div className="flex gap-1 shrink-0">
                                {c.status === 'open' && (
                                  <Button data-testid={`ack-case-${c.id}`} size="sm" variant="outline"
                                    className="h-7 text-xs border-blue-600 text-blue-400 hover:bg-blue-500/10"
                                    onClick={() => acknowledgeCase(c.id)}>
                                    <Eye className="w-3 h-3 mr-1" /> Ack
                                  </Button>
                                )}
                                <Button data-testid={`resolve-case-${c.id}`} size="sm" variant="outline"
                                  className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10"
                                  onClick={() => resolveCase(c.id)}>
                                  <CheckCircle className="w-3 h-3 mr-1" /> Resolve
                                </Button>
                                <Button data-testid={`ignore-case-${c.id}`} size="sm" variant="outline"
                                  className="h-7 text-xs border-zinc-600 text-zinc-400 hover:bg-zinc-500/10"
                                  onClick={() => ignoreCase(c.id)}>
                                  <XCircle className="w-3 h-3 mr-1" /> Ignore
                                </Button>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default DataModelDashboard;
