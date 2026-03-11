import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Network, Plus, RefreshCw, CheckCircle, AlertTriangle, XCircle,
  Clock, ArrowUpDown, Link2, Unlink, Shield, Activity, FileText,
  Download, Eye, ChevronRight, Zap, Settings, Database, Map
} from 'lucide-react';

const API_BASE = '/channel-manager/v2';

const HealthBadge = ({ health }) => {
  const colors = {
    green: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    yellow: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    red: 'bg-red-500/15 text-red-400 border-red-500/30',
  };
  return (
    <Badge data-testid="health-badge" className={`${colors[health] || colors.yellow} border`}>
      {health === 'green' && <CheckCircle className="w-3 h-3 mr-1" />}
      {health === 'yellow' && <AlertTriangle className="w-3 h-3 mr-1" />}
      {health === 'red' && <XCircle className="w-3 h-3 mr-1" />}
      {health?.toUpperCase()}
    </Badge>
  );
};

const StatusBadge = ({ status }) => {
  const map = {
    active: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    draft: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    paused: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    error: 'bg-red-500/15 text-red-400 border-red-500/30',
    disabled: 'bg-red-500/15 text-red-300 border-red-500/30',
    completed: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
    failed: 'bg-red-500/15 text-red-400 border-red-500/30',
    open: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    queued: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
    in_progress: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  };
  return (
    <Badge data-testid={`status-${status}`} className={`${map[status] || map.draft} border text-xs`}>
      {status?.replace('_', ' ')}
    </Badge>
  );
};

const IntegrationHub = ({ user, tenant, onLogout }) => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [connectors, setConnectors] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [syncJobs, setSyncJobs] = useState([]);
  const [importedReservations, setImportedReservations] = useState([]);
  const [issues, setIssues] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNewConnector, setShowNewConnector] = useState(false);
  const [showNewMapping, setShowNewMapping] = useState(false);
  const [selectedConnector, setSelectedConnector] = useState(null);
  const [newConnector, setNewConnector] = useState({
    provider: 'hotelrunner', display_name: '', credentials: { token: '', hr_id: '' },
  });
  const [newMapping, setNewMapping] = useState({
    connector_id: '', entity_type: 'room_type',
    pms_entity_id: '', pms_entity_name: '',
    external_entity_id: '', external_entity_name: '',
  });

  const fetchDashboard = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/dashboard`);
      setDashboard(data);
      setConnectors(data.connectors || []);
    } catch { /* silent */ }
  }, []);

  const fetchConnectors = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/connectors`);
      setConnectors(data.connectors || []);
    } catch { /* silent */ }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    await fetchDashboard();
    try {
      const [jobsRes, importRes, issuesRes, auditRes] = await Promise.all([
        axios.get(`${API_BASE}/sync/jobs`).catch(() => ({ data: { jobs: [] } })),
        axios.get(`${API_BASE}/reservations/imported`).catch(() => ({ data: { reservations: [] } })),
        axios.get(`${API_BASE}/reconciliation/issues`).catch(() => ({ data: { issues: [] } })),
        axios.get(`${API_BASE}/audit`).catch(() => ({ data: { logs: [] } })),
      ]);
      setSyncJobs(jobsRes.data.jobs || []);
      setImportedReservations(importRes.data.reservations || []);
      setIssues(issuesRes.data.issues || []);
      setAuditLogs(auditRes.data.logs || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [fetchDashboard]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleCreateConnector = async () => {
    try {
      await axios.post(`${API_BASE}/connectors`, newConnector);
      toast.success('Connector oluşturuldu');
      setShowNewConnector(false);
      setNewConnector({ provider: 'hotelrunner', display_name: '', credentials: { token: '', hr_id: '' } });
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleActivate = async (id) => {
    try {
      await axios.post(`${API_BASE}/connectors/${id}/activate`);
      toast.success('Connector aktifleştirildi');
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handlePause = async (id) => {
    try {
      await axios.post(`${API_BASE}/connectors/${id}/pause`);
      toast.success('Connector duraklatıldı');
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleTestConnection = async (id) => {
    try {
      const { data } = await axios.post(`${API_BASE}/connectors/${id}/test`);
      if (data.success) toast.success('Bağlantı başarılı');
      else toast.error(data.message || 'Bağlantı başarısız');
    } catch (e) { toast.error('Bağlantı testi başarısız'); }
  };

  const handleCreateMapping = async () => {
    try {
      const payload = { ...newMapping, connector_id: selectedConnector };
      await axios.post(`${API_BASE}/mappings`, payload);
      toast.success('Mapping oluşturuldu');
      setShowNewMapping(false);
      fetchMappings(selectedConnector);
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const fetchMappings = async (connectorId) => {
    if (!connectorId) return;
    try {
      const { data } = await axios.get(`${API_BASE}/mappings/${connectorId}`);
      setMappings(data.mappings || []);
    } catch { setMappings([]); }
  };

  const handleSyncInventory = async (connectorId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/sync/inventory`, { connector_id: connectorId, reason: 'Manual trigger' });
      toast.success(`Sync başlatıldı (Job: ${data.job_id?.slice(0, 8)})`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Sync başarısız'); }
  };

  const handleSyncRates = async (connectorId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/sync/rates`, { connector_id: connectorId, reason: 'Manual rate sync' });
      toast.success(`Rate sync başlatıldı (Job: ${data.job_id?.slice(0, 8)})`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Rate sync başarısız'); }
  };

  const handlePullReservations = async (connectorId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/reservations/pull`, { connector_id: connectorId });
      toast.success(`Rezervasyon çekme tamamlandı: ${data.total || 0} adet`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Rezervasyon çekme başarısız'); }
  };

  const handleRunReconciliation = async (connectorId) => {
    try {
      const { data } = await axios.post(`${API_BASE}/reconciliation/run`, { connector_id: connectorId });
      toast.success(`Reconciliation tamamlandı: ${data.issues_found || 0} sorun bulundu`);
      fetchData();
    } catch (e) { toast.error(e.response?.data?.detail || 'Reconciliation başarısız'); }
  };

  const handleResolveIssue = async (issueId) => {
    try {
      await axios.post(`${API_BASE}/reconciliation/issues/${issueId}/resolve`, { resolution: 'Manual resolution' });
      toast.success('Sorun çözüldü');
      fetchData();
    } catch { toast.error('Çözüm başarısız'); }
  };

  const hs = dashboard?.health_summary || {};

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="integration-hub">
      <div data-testid="integration-hub" className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">Integration Hub</h1>
            <p className="text-sm text-slate-400 mt-1">Channel Manager &middot; Connector Architecture</p>
          </div>
          <div className="flex items-center gap-3">
            <Button data-testid="refresh-btn" variant="outline" size="sm" onClick={fetchData} className="border-slate-700 text-slate-300">
              <RefreshCw className="w-4 h-4 mr-1" /> Yenile
            </Button>
            <Button data-testid="add-connector-btn" size="sm" onClick={() => setShowNewConnector(true)} className="bg-blue-600 hover:bg-blue-700">
              <Plus className="w-4 h-4 mr-1" /> Connector Ekle
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Connectors</p>
                  <p data-testid="total-connectors" className="text-2xl font-bold text-white">{dashboard?.total_connectors || 0}</p>
                </div>
                <Network className="w-8 h-8 text-blue-400 opacity-60" />
              </div>
              <p className="text-xs text-emerald-400 mt-1">{dashboard?.active_connectors || 0} active</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Health</p>
                  <p className="text-2xl font-bold text-white">{(hs.green || 0) + (hs.yellow || 0) + (hs.red || 0)}</p>
                </div>
                <Activity className="w-8 h-8 text-emerald-400 opacity-60" />
              </div>
              <div className="flex gap-2 mt-1 text-xs">
                <span className="text-emerald-400">{hs.green || 0} green</span>
                <span className="text-amber-400">{hs.yellow || 0} yellow</span>
                <span className="text-red-400">{hs.red || 0} red</span>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Sync Jobs</p>
                  <p className="text-2xl font-bold text-white">{syncJobs.length}</p>
                </div>
                <ArrowUpDown className="w-8 h-8 text-violet-400 opacity-60" />
              </div>
              <p className="text-xs text-slate-400 mt-1">Son 50 job</p>
            </CardContent>
          </Card>
          <Card className="bg-slate-900/50 border-slate-800">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-slate-400">Issues</p>
                  <p data-testid="open-issues" className="text-2xl font-bold text-white">{dashboard?.open_issue_count || 0}</p>
                </div>
                <AlertTriangle className="w-8 h-8 text-amber-400 opacity-60" />
              </div>
              <p className="text-xs text-amber-400 mt-1">Açık sorunlar</p>
            </CardContent>
          </Card>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-900/50 border border-slate-800">
            <TabsTrigger value="dashboard" className="data-[state=active]:bg-slate-700">
              <Activity className="w-4 h-4 mr-1" /> Dashboard
            </TabsTrigger>
            <TabsTrigger value="connectors" className="data-[state=active]:bg-slate-700">
              <Network className="w-4 h-4 mr-1" /> Connectors
            </TabsTrigger>
            <TabsTrigger value="mappings" className="data-[state=active]:bg-slate-700">
              <Map className="w-4 h-4 mr-1" /> Mappings
            </TabsTrigger>
            <TabsTrigger value="sync" className="data-[state=active]:bg-slate-700">
              <ArrowUpDown className="w-4 h-4 mr-1" /> Sync Jobs
            </TabsTrigger>
            <TabsTrigger value="reservations" className="data-[state=active]:bg-slate-700">
              <FileText className="w-4 h-4 mr-1" /> Reservations
            </TabsTrigger>
            <TabsTrigger value="reconciliation" className="data-[state=active]:bg-slate-700">
              <Shield className="w-4 h-4 mr-1" /> Reconciliation
            </TabsTrigger>
            <TabsTrigger value="audit" className="data-[state=active]:bg-slate-700">
              <Eye className="w-4 h-4 mr-1" /> Audit
            </TabsTrigger>
          </TabsList>

          {/* Dashboard Tab */}
          <TabsContent value="dashboard">
            <div className="grid md:grid-cols-2 gap-4">
              {connectors.map((c) => (
                <Card key={c.connector_id} className="bg-slate-900/50 border-slate-800">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-base text-white">{c.display_name || c.provider}</CardTitle>
                        <StatusBadge status={c.status} />
                      </div>
                      <HealthBadge health={c.health} />
                    </div>
                    <CardDescription className="text-xs text-slate-500">
                      {c.provider} &middot; Total syncs: {c.total_syncs || 0}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="pt-0 space-y-2">
                    {c.reasons?.length > 0 && (
                      <div className="text-xs text-amber-400/80 space-y-0.5">
                        {c.reasons.map((r, i) => <p key={i}>&#9888; {r}</p>)}
                      </div>
                    )}
                    <div className="flex gap-2 flex-wrap">
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700"
                        onClick={() => handleSyncInventory(c.connector_id)} data-testid={`sync-inv-${c.connector_id}`}>
                        <ArrowUpDown className="w-3 h-3 mr-1" /> Push Inventory
                      </Button>
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700"
                        onClick={() => handleSyncRates(c.connector_id)}>
                        <Zap className="w-3 h-3 mr-1" /> Push Rates
                      </Button>
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700"
                        onClick={() => handlePullReservations(c.connector_id)}>
                        <Download className="w-3 h-3 mr-1" /> Pull Reservations
                      </Button>
                      <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700"
                        onClick={() => handleRunReconciliation(c.connector_id)}>
                        <Shield className="w-3 h-3 mr-1" /> Reconcile
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
              {connectors.length === 0 && !loading && (
                <Card className="bg-slate-900/50 border-slate-800 col-span-2">
                  <CardContent className="p-12 text-center">
                    <Network className="w-12 h-12 mx-auto text-slate-600 mb-3" />
                    <p className="text-slate-400 text-sm">Henüz connector tanımlanmamış</p>
                    <Button size="sm" onClick={() => setShowNewConnector(true)} className="mt-3 bg-blue-600">
                      <Plus className="w-4 h-4 mr-1" /> İlk Connector'ı Ekle
                    </Button>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          {/* Connectors Tab */}
          <TabsContent value="connectors">
            <div className="space-y-3">
              {connectors.map((c) => (
                <Card key={c.connector_id} className="bg-slate-900/50 border-slate-800">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full ${c.status === 'active' ? 'bg-emerald-400' : c.status === 'paused' ? 'bg-amber-400' : 'bg-slate-500'}`} />
                        <div>
                          <p className="font-medium text-white">{c.display_name || c.provider}</p>
                          <p className="text-xs text-slate-500">{c.provider} &middot; {c.connector_id?.slice(0, 8)}</p>
                        </div>
                        <StatusBadge status={c.status} />
                        <HealthBadge health={c.health} />
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="text-xs h-7 border-slate-700"
                          onClick={() => handleTestConnection(c.connector_id)} data-testid={`test-conn-${c.connector_id}`}>
                          Test
                        </Button>
                        {c.status !== 'active' && (
                          <Button size="sm" className="text-xs h-7 bg-emerald-600"
                            onClick={() => handleActivate(c.connector_id)}>
                            Activate
                          </Button>
                        )}
                        {c.status === 'active' && (
                          <Button size="sm" variant="outline" className="text-xs h-7 border-amber-700 text-amber-400"
                            onClick={() => handlePause(c.connector_id)}>
                            Pause
                          </Button>
                        )}
                      </div>
                    </div>
                    {c.last_successful_sync && (
                      <p className="text-xs text-slate-500 mt-2">
                        <Clock className="w-3 h-3 inline mr-1" />
                        Son sync: {new Date(c.last_successful_sync).toLocaleString('tr-TR')}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Mappings Tab */}
          <TabsContent value="mappings">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Label className="text-slate-400">Connector:</Label>
                  <select
                    className="bg-slate-900 border border-slate-700 rounded px-3 py-1.5 text-sm text-white"
                    value={selectedConnector || ''}
                    onChange={(e) => {
                      setSelectedConnector(e.target.value);
                      fetchMappings(e.target.value);
                    }}
                    data-testid="mapping-connector-select"
                  >
                    <option value="">Seçin...</option>
                    {connectors.map((c) => (
                      <option key={c.connector_id} value={c.connector_id}>{c.display_name || c.provider}</option>
                    ))}
                  </select>
                </div>
                <Button data-testid="add-mapping-btn" size="sm" onClick={() => setShowNewMapping(true)} disabled={!selectedConnector}
                  className="bg-blue-600 hover:bg-blue-700">
                  <Plus className="w-4 h-4 mr-1" /> Mapping Ekle
                </Button>
              </div>

              {mappings.length > 0 ? (
                <div className="border border-slate-800 rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-800/50 text-slate-400">
                      <tr>
                        <th className="text-left px-4 py-2">Tip</th>
                        <th className="text-left px-4 py-2">PMS Entity</th>
                        <th className="text-center px-4 py-2"><ArrowUpDown className="w-3 h-3 inline" /></th>
                        <th className="text-left px-4 py-2">External Entity</th>
                        <th className="text-left px-4 py-2">Durum</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {mappings.map((m) => (
                        <tr key={m.id} className="text-slate-300 hover:bg-slate-800/30">
                          <td className="px-4 py-2"><Badge variant="outline" className="text-xs border-slate-700">{m.entity_type}</Badge></td>
                          <td className="px-4 py-2">{m.pms_entity_name || m.pms_entity_id}</td>
                          <td className="px-4 py-2 text-center"><Link2 className="w-4 h-4 inline text-slate-500" /></td>
                          <td className="px-4 py-2">{m.external_entity_name || m.external_entity_id}</td>
                          <td className="px-4 py-2"><StatusBadge status={m.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : selectedConnector ? (
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardContent className="p-8 text-center">
                    <Unlink className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-slate-400 text-sm">Bu connector için mapping yok</p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="bg-slate-900/50 border-slate-800">
                  <CardContent className="p-8 text-center">
                    <Map className="w-10 h-10 mx-auto text-slate-600 mb-2" />
                    <p className="text-slate-400 text-sm">Connector seçin</p>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          {/* Sync Jobs Tab */}
          <TabsContent value="sync">
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-white">Sync History</CardTitle>
              </CardHeader>
              <CardContent>
                {syncJobs.length > 0 ? (
                  <div className="space-y-2">
                    {syncJobs.map((j) => (
                      <div key={j.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                        <div className="flex items-center gap-3">
                          <div className="flex flex-col">
                            <span className="text-sm text-white font-medium">{j.sync_type} ({j.direction})</span>
                            <span className="text-xs text-slate-500">{j.id?.slice(0, 8)} &middot; {new Date(j.created_at).toLocaleString('tr-TR')}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-slate-400">{j.completed_events || 0}/{j.total_events || 0} events</span>
                          <StatusBadge status={j.status} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-slate-500 text-sm">Henüz sync job yok</div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Reservations Tab */}
          <TabsContent value="reservations">
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-white">Imported Reservations</CardTitle>
              </CardHeader>
              <CardContent>
                {importedReservations.length > 0 ? (
                  <div className="border border-slate-800 rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-800/50 text-slate-400">
                        <tr>
                          <th className="text-left px-4 py-2">Ref</th>
                          <th className="text-left px-4 py-2">Misafir</th>
                          <th className="text-left px-4 py-2">Tarih</th>
                          <th className="text-left px-4 py-2">Kanal</th>
                          <th className="text-left px-4 py-2">Durum</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {importedReservations.map((r) => (
                          <tr key={r.id} className="text-slate-300 hover:bg-slate-800/30">
                            <td className="px-4 py-2 text-xs">{r.external_confirmation_number || r.external_reservation_id?.slice(0, 10)}</td>
                            <td className="px-4 py-2">{r.guest_name}</td>
                            <td className="px-4 py-2 text-xs">{r.arrival_date} → {r.departure_date}</td>
                            <td className="px-4 py-2 text-xs">{r.channel_name}</td>
                            <td className="px-4 py-2"><StatusBadge status={r.import_status} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-slate-500 text-sm">Henüz import edilen rezervasyon yok</div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Reconciliation Tab */}
          <TabsContent value="reconciliation">
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-white">Reconciliation Issues</CardTitle>
              </CardHeader>
              <CardContent>
                {issues.length > 0 ? (
                  <div className="space-y-2">
                    {issues.map((issue) => (
                      <div key={issue.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30 border border-slate-800">
                        <div>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-xs border-slate-700">{issue.issue_type}</Badge>
                            <Badge className={`text-xs ${issue.severity === 'critical' ? 'bg-red-500/15 text-red-400' : issue.severity === 'high' ? 'bg-amber-500/15 text-amber-400' : 'bg-slate-500/15 text-slate-400'} border`}>
                              {issue.severity}
                            </Badge>
                          </div>
                          <p className="text-sm text-slate-300 mt-1">{issue.description}</p>
                        </div>
                        <Button size="sm" variant="outline" className="text-xs h-7 border-emerald-700 text-emerald-400"
                          onClick={() => handleResolveIssue(issue.id)}>
                          Resolve
                        </Button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <CheckCircle className="w-10 h-10 mx-auto text-emerald-500/50 mb-2" />
                    <p className="text-slate-500 text-sm">Açık reconciliation sorunu yok</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Audit Tab */}
          <TabsContent value="audit">
            <Card className="bg-slate-900/50 border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-base text-white">Integration Audit Log</CardTitle>
              </CardHeader>
              <CardContent>
                {auditLogs.length > 0 ? (
                  <div className="space-y-1.5">
                    {auditLogs.map((log) => (
                      <div key={log.id} className="flex items-center gap-3 px-3 py-2 rounded bg-slate-800/20 text-xs">
                        <span className="text-slate-500 w-40 shrink-0">{new Date(log.created_at).toLocaleString('tr-TR')}</span>
                        <Badge variant="outline" className="text-xs border-slate-700 shrink-0">{log.action}</Badge>
                        <span className="text-slate-400 truncate">{log.entity_type} {log.entity_id?.slice(0, 8)}</span>
                        <span className="text-slate-600 ml-auto">{log.actor_type}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-slate-500 text-sm">Audit log boş</div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* New Connector Dialog */}
        <Dialog open={showNewConnector} onOpenChange={setShowNewConnector}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white">
            <DialogHeader>
              <DialogTitle>Yeni Connector Ekle</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label className="text-slate-400">Provider</Label>
                <select
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white mt-1"
                  value={newConnector.provider}
                  onChange={(e) => setNewConnector({ ...newConnector, provider: e.target.value })}
                  data-testid="new-connector-provider"
                >
                  <option value="hotelrunner">HotelRunner</option>
                  <option value="siteminder">SiteMinder</option>
                  <option value="channex">Channex</option>
                </select>
              </div>
              <div>
                <Label className="text-slate-400">Display Name</Label>
                <Input
                  value={newConnector.display_name}
                  onChange={(e) => setNewConnector({ ...newConnector, display_name: e.target.value })}
                  placeholder="HotelRunner Production"
                  className="bg-slate-800 border-slate-700 text-white"
                  data-testid="new-connector-name"
                />
              </div>
              <div>
                <Label className="text-slate-400">Token</Label>
                <Input
                  value={newConnector.credentials.token}
                  onChange={(e) => setNewConnector({ ...newConnector, credentials: { ...newConnector.credentials, token: e.target.value } })}
                  placeholder="HotelRunner API Token"
                  className="bg-slate-800 border-slate-700 text-white"
                  data-testid="new-connector-token"
                />
              </div>
              <div>
                <Label className="text-slate-400">HR ID</Label>
                <Input
                  value={newConnector.credentials.hr_id}
                  onChange={(e) => setNewConnector({ ...newConnector, credentials: { ...newConnector.credentials, hr_id: e.target.value } })}
                  placeholder="HotelRunner Hotel ID"
                  className="bg-slate-800 border-slate-700 text-white"
                  data-testid="new-connector-hrid"
                />
              </div>
              <Button data-testid="create-connector-submit" className="w-full bg-blue-600" onClick={handleCreateConnector}>
                Connector Oluştur
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        {/* New Mapping Dialog */}
        <Dialog open={showNewMapping} onOpenChange={setShowNewMapping}>
          <DialogContent className="bg-slate-900 border-slate-800 text-white">
            <DialogHeader>
              <DialogTitle>Yeni Mapping Ekle</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label className="text-slate-400">Entity Type</Label>
                <select
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white mt-1"
                  value={newMapping.entity_type}
                  onChange={(e) => setNewMapping({ ...newMapping, entity_type: e.target.value })}
                  data-testid="new-mapping-type"
                >
                  <option value="room_type">Room Type</option>
                  <option value="rate_plan">Rate Plan</option>
                  <option value="meal_plan">Meal Plan</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-slate-400 text-xs">PMS Entity ID</Label>
                  <Input value={newMapping.pms_entity_id}
                    onChange={(e) => setNewMapping({ ...newMapping, pms_entity_id: e.target.value })}
                    placeholder="Standard" className="bg-slate-800 border-slate-700 text-white" />
                </div>
                <div>
                  <Label className="text-slate-400 text-xs">PMS Entity Name</Label>
                  <Input value={newMapping.pms_entity_name}
                    onChange={(e) => setNewMapping({ ...newMapping, pms_entity_name: e.target.value })}
                    placeholder="Standard Room" className="bg-slate-800 border-slate-700 text-white" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-slate-400 text-xs">External Entity ID</Label>
                  <Input value={newMapping.external_entity_id}
                    onChange={(e) => setNewMapping({ ...newMapping, external_entity_id: e.target.value })}
                    placeholder="STD_HR" className="bg-slate-800 border-slate-700 text-white" />
                </div>
                <div>
                  <Label className="text-slate-400 text-xs">External Entity Name</Label>
                  <Input value={newMapping.external_entity_name}
                    onChange={(e) => setNewMapping({ ...newMapping, external_entity_name: e.target.value })}
                    placeholder="Standard - HotelRunner" className="bg-slate-800 border-slate-700 text-white" />
                </div>
              </div>
              <Button data-testid="create-mapping-submit" className="w-full bg-blue-600"
                onClick={handleCreateMapping}>
                Mapping Oluştur
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default IntegrationHub;
