import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Database, Link2, Grid3X3, FileText, GitBranch,
  AlertTriangle, RefreshCw, Plus, Trash2, CheckCircle,
  XCircle, Loader2, Server, Layers, ArrowRightLeft, Clock
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

  const propertyId = tenant?.property_id || 'prop-001';

  const headers = useCallback(() => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const h = headers();
      const [schemaRes, connRes, roomRes, rateRes, eventsRes, lineageRes, casesRes, summaryRes] = await Promise.all([
        axios.get(`${API}/api/channel-manager/model/schema`, { headers: h }).catch(() => ({ data: null })),
        axios.get(`${API}/api/channel-manager/model/connections`, { headers: h }).catch(() => ({ data: { connections: [] } })),
        axios.get(`${API}/api/channel-manager/model/room-mappings?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { mappings: [] } })),
        axios.get(`${API}/api/channel-manager/model/rate-plan-mappings?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { mappings: [] } })),
        axios.get(`${API}/api/channel-manager/model/raw-events?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { events: [] } })),
        axios.get(`${API}/api/channel-manager/model/lineage?property_id=${propertyId}`, { headers: h }).catch(() => ({ data: { lineages: [] } })),
        axios.get(`${API}/api/channel-manager/model/reconciliation/cases`, { headers: h }).catch(() => ({ data: { cases: [] } })),
        axios.get(`${API}/api/channel-manager/model/reconciliation/summary`, { headers: h }).catch(() => ({ data: null })),
      ]);
      setSchema(schemaRes.data);
      setConnections(connRes.data.connections || []);
      setRoomMappings(roomRes.data.mappings || []);
      setRatePlanMappings(rateRes.data.mappings || []);
      setRawEvents(eventsRes.data.events || []);
      setLineages(lineageRes.data.lineages || []);
      setReconCases(casesRes.data.cases || []);
      setReconSummary(summaryRes.data);
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
      await axios.post(`${API}/api/channel-manager/model/reconciliation/cases/${caseId}/resolve`, { resolution: 'Manually resolved' }, { headers: headers() });
      toast.success('Case resolved');
      fetchAll();
    } catch { toast.error('Resolve failed'); }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div data-testid="data-model-dashboard" className="space-y-6 p-4 md:p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100 flex items-center gap-2">
              <Database className="w-6 h-6 text-cyan-400" />
              Channel Manager Data Model
            </h1>
            <p className="text-sm text-zinc-500 mt-1">
              {schema ? `v${schema.model_version} — ${schema.total_collections} collections` : 'Loading...'} | Providers: hotelrunner, exely
            </p>
          </div>
          <Button data-testid="refresh-btn" variant="outline" size="sm" onClick={fetchAll} disabled={loading}
            className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="ml-1.5">Refresh</span>
          </Button>
        </div>

        {/* Collection Overview Cards */}
        <div data-testid="collection-overview" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <CollectionCard name="provider_connections" count={connections.length} icon={Link2} color="bg-blue-500/15 text-blue-400" />
          <CollectionCard name="room_mappings" count={roomMappings.length} icon={Grid3X3} color="bg-cyan-500/15 text-cyan-400" />
          <CollectionCard name="rate_plan_mappings" count={ratePlanMappings.length} icon={Layers} color="bg-violet-500/15 text-violet-400" />
          <CollectionCard name="reservation_lineage" count={lineages.length} icon={GitBranch} color="bg-emerald-500/15 text-emerald-400" />
          <CollectionCard name="reconciliation_cases" count={reconCases.length} icon={AlertTriangle} color="bg-amber-500/15 text-amber-400" />
        </div>

        {/* Tabs */}
        <Tabs defaultValue="connections" className="space-y-4">
          <TabsList data-testid="model-tabs" className="bg-zinc-900 border border-zinc-800 p-1">
            <TabsTrigger value="connections" className="data-[state=active]:bg-zinc-800 text-xs">
              <Link2 className="w-3.5 h-3.5 mr-1" /> Connections
            </TabsTrigger>
            <TabsTrigger value="room-mappings" className="data-[state=active]:bg-zinc-800 text-xs">
              <Grid3X3 className="w-3.5 h-3.5 mr-1" /> Room Mappings
            </TabsTrigger>
            <TabsTrigger value="rate-mappings" className="data-[state=active]:bg-zinc-800 text-xs">
              <Layers className="w-3.5 h-3.5 mr-1" /> Rate Mappings
            </TabsTrigger>
            <TabsTrigger value="lineage" className="data-[state=active]:bg-zinc-800 text-xs">
              <GitBranch className="w-3.5 h-3.5 mr-1" /> Lineage
            </TabsTrigger>
            <TabsTrigger value="raw-events" className="data-[state=active]:bg-zinc-800 text-xs">
              <FileText className="w-3.5 h-3.5 mr-1" /> Raw Events
            </TabsTrigger>
            <TabsTrigger value="reconciliation" className="data-[state=active]:bg-zinc-800 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 mr-1" /> Reconciliation
            </TabsTrigger>
          </TabsList>

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

          {/* Room Mappings Tab */}
          <TabsContent value="room-mappings">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <Grid3X3 className="w-4 h-4 text-cyan-400" />
                  Room Mappings ({roomMappings.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {roomMappings.length === 0 ? (
                  <p data-testid="no-room-mappings" className="text-zinc-500 text-sm text-center py-6">No room mappings</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                          <th className="text-left py-2 px-3">Provider</th>
                          <th className="text-left py-2 px-3">PMS Room Type</th>
                          <th className="text-left py-2 px-3"><ArrowRightLeft className="w-3 h-3 inline" /></th>
                          <th className="text-left py-2 px-3">Provider Room Code</th>
                          <th className="text-left py-2 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {roomMappings.map(m => (
                          <tr key={m.id} data-testid={`room-mapping-${m.id}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                            <td className="py-2 px-3"><ProviderBadge provider={m.provider} /></td>
                            <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.pms_room_type_id} <span className="text-zinc-500">({m.pms_room_type_name})</span></td>
                            <td className="py-2 px-3 text-zinc-600">→</td>
                            <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.provider_room_code}</td>
                            <td className="py-2 px-3">
                              <Badge className={m.is_active ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs' : 'bg-zinc-500/15 text-zinc-400 text-xs'}>
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
          </TabsContent>

          {/* Rate Plan Mappings Tab */}
          <TabsContent value="rate-mappings">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-violet-400" />
                  Rate Plan Mappings ({ratePlanMappings.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {ratePlanMappings.length === 0 ? (
                  <p data-testid="no-rate-mappings" className="text-zinc-500 text-sm text-center py-6">No rate plan mappings</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-zinc-500 text-xs border-b border-zinc-800">
                          <th className="text-left py-2 px-3">Provider</th>
                          <th className="text-left py-2 px-3">PMS Rate Plan</th>
                          <th className="text-left py-2 px-3"><ArrowRightLeft className="w-3 h-3 inline" /></th>
                          <th className="text-left py-2 px-3">Provider Rate Code</th>
                          <th className="text-left py-2 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ratePlanMappings.map(m => (
                          <tr key={m.id} data-testid={`rate-mapping-${m.id}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                            <td className="py-2 px-3"><ProviderBadge provider={m.provider} /></td>
                            <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.pms_rate_plan_id} <span className="text-zinc-500">({m.pms_rate_plan_name})</span></td>
                            <td className="py-2 px-3 text-zinc-600">→</td>
                            <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{m.provider_rate_code}</td>
                            <td className="py-2 px-3">
                              <Badge className={m.is_active ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 text-xs' : 'bg-zinc-500/15 text-zinc-400 text-xs'}>
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
          </TabsContent>

          {/* Reservation Lineage Tab */}
          <TabsContent value="lineage">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <GitBranch className="w-4 h-4 text-emerald-400" />
                  Reservation Lineage ({lineages.length})
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
                          <th className="text-left py-2 px-3">Version</th>
                          <th className="text-left py-2 px-3">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lineages.map(l => (
                          <tr key={l.id} data-testid={`lineage-${l.id}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                            <td className="py-2 px-3"><ProviderBadge provider={l.provider} /></td>
                            <td className="py-2 px-3 text-zinc-200 font-mono text-xs">{l.external_reservation_id}</td>
                            <td className="py-2 px-3 text-zinc-300 text-xs">{l.guest_name || '-'}</td>
                            <td className="py-2 px-3 text-zinc-400 text-xs">{l.arrival_date} → {l.departure_date}</td>
                            <td className="py-2 px-3 text-zinc-200 text-xs">{l.total_amount} {l.currency}</td>
                            <td className="py-2 px-3 text-zinc-400 text-xs">v{l.version}</td>
                            <td className="py-2 px-3">
                              <Badge className="bg-zinc-700/50 text-zinc-300 border-zinc-600 text-xs">{l.status}</Badge>
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

          {/* Raw Events Tab */}
          <TabsContent value="raw-events">
            <Card className="bg-zinc-900/60 border-zinc-800">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-amber-400" />
                  Raw Channel Events ({rawEvents.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                {rawEvents.length === 0 ? (
                  <p data-testid="no-raw-events" className="text-zinc-500 text-sm text-center py-6">No raw events yet</p>
                ) : (
                  <div className="space-y-2">
                    {rawEvents.map(e => (
                      <div key={e.id} data-testid={`raw-event-${e.id}`} className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                        <div className="flex items-center gap-2 mb-1">
                          <ProviderBadge provider={e.provider} />
                          <Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{e.source}</Badge>
                          <Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{e.event_type}</Badge>
                          {e.processed ? (
                            <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Clock className="w-3.5 h-3.5 text-amber-400" />
                          )}
                        </div>
                        <p className="text-xs text-zinc-500 font-mono">{e.received_at}</p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Reconciliation Tab */}
          <TabsContent value="reconciliation">
            <div className="space-y-4">
              {/* Summary */}
              {reconSummary && (
                <div data-testid="recon-summary" className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <Card className="bg-zinc-900/60 border-zinc-800">
                    <CardContent className="p-3 text-center">
                      <p className="text-2xl font-bold text-red-400">{reconSummary.total_open}</p>
                      <p className="text-xs text-zinc-500">Open Cases</p>
                    </CardContent>
                  </Card>
                  {Object.entries(reconSummary.by_severity || {}).map(([sev, count]) => (
                    <Card key={sev} className="bg-zinc-900/60 border-zinc-800">
                      <CardContent className="p-3 text-center">
                        <p className="text-2xl font-bold text-zinc-200">{count}</p>
                        <p className="text-xs text-zinc-500 capitalize">{sev}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}

              {/* Cases List */}
              <Card className="bg-zinc-900/60 border-zinc-800">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-zinc-200 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    Reconciliation Cases ({reconCases.length})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {reconCases.length === 0 ? (
                    <p data-testid="no-recon-cases" className="text-zinc-500 text-sm text-center py-6">No open reconciliation cases</p>
                  ) : (
                    <div className="space-y-2">
                      {reconCases.map(c => (
                        <div key={c.id} data-testid={`recon-case-${c.id}`} className="flex items-center justify-between p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
                          <div className="flex items-center gap-3 min-w-0">
                            <StatusDot status={c.status} />
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 mb-0.5">
                                <ProviderBadge provider={c.provider} />
                                <Badge className="bg-zinc-700/50 text-zinc-300 text-xs">{c.case_type}</Badge>
                                <Badge className={`text-xs ${
                                  c.severity === 'critical' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                  c.severity === 'high' ? 'bg-orange-500/15 text-orange-400 border-orange-500/30' :
                                  c.severity === 'medium' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                                  'bg-zinc-500/15 text-zinc-400 border-zinc-500/30'
                                } border`}>{c.severity}</Badge>
                              </div>
                              <p className="text-xs text-zinc-400 truncate">{c.description}</p>
                            </div>
                          </div>
                          {c.status === 'open' && (
                            <Button data-testid={`resolve-case-${c.id}`} size="sm" variant="outline"
                              className="h-7 text-xs border-emerald-600 text-emerald-400 hover:bg-emerald-500/10 ml-2 shrink-0"
                              onClick={() => resolveCase(c.id)}>
                              <CheckCircle className="w-3 h-3 mr-1" /> Resolve
                            </Button>
                          )}
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
