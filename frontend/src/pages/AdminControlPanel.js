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
  Activity, AlertTriangle, CheckCircle, XCircle, RefreshCw,
  Shield, Clock, Loader2, Search, Filter, RotateCcw,
  Eye, Trash2, ArrowUpRight, ChevronDown, Zap,
  Key, Database, Settings, AlertOctagon, FileText
} from 'lucide-react';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

const API = '/channel-manager/v2';

/* ─── Tiny utility components ───────────────────────────────── */

const SeverityBadge = ({ severity }) => {
  const map = {
    critical: 'bg-red-500/15 text-red-400 border-red-500/30',
    high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
    medium: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
    low: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
  };
  return <Badge data-testid={`severity-${severity}`} className={`${map[severity] || map.low} border text-xs`}>{severity}</Badge>;
};

const StatusDot = ({ status }) => {
  const colors = { healthy: 'bg-emerald-400', degraded: 'bg-amber-400', critical: 'bg-red-400' };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status] || 'bg-slate-400'}`} />;
};

const ScoreRing = ({ score, size = 80 }) => {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const fill = c - (score / 100) * c;
  const color = score >= 80 ? '#34d399' : score >= 50 ? '#fbbf24' : '#f87171';
  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="currentColor" strokeWidth="4" className="text-slate-700" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="4"
        strokeDasharray={c} strokeDashoffset={fill} strokeLinecap="round" />
      <text x={size/2} y={size/2} textAnchor="middle" dominantBaseline="central"
        className="fill-white text-lg font-bold" transform={`rotate(90 ${size/2} ${size/2})`}>{score}</text>
    </svg>
  );
};

const MetricCard = ({ title, value, sub, icon: Icon, color = 'text-slate-300' }) => (
  <Card data-testid={`metric-${title.toLowerCase().replace(/\s+/g,'-')}`} className="bg-slate-800/50 border-slate-700">
    <CardContent className="p-4 flex items-center gap-3">
      {Icon && <Icon className={`w-5 h-5 ${color}`} />}
      <div>
        <p className="text-xs text-slate-400">{title}</p>
        <p className="text-xl font-semibold text-white">{value}</p>
        {sub && <p className="text-[10px] text-slate-500">{sub}</p>}
      </div>
    </CardContent>
  </Card>
);

/* ─── Reconciliation Issues Tab ─────────────────────────────── */

const ReconciliationTab = ({ user }) => {
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ severity: 'all', issue_type: 'all', status: 'open', connector: 'all' });
  const [actionLoading, setActionLoading] = useState(null);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.status !== 'all') params.append('status', filters.status);
      if (filters.severity !== 'all') params.append('severity', filters.severity);
      if (filters.issue_type !== 'all') params.append('issue_type', filters.issue_type);
      if (filters.connector !== 'all') params.append('connector_id', filters.connector);
      const { data } = await axios.get(`${API}/admin/reconciliation/issues?${params}`);
      setIssues(data.issues || []);
    } catch { /* silent */ }
    setLoading(false);
  }, [filters]);

  useEffect(() => { fetchIssues(); }, [fetchIssues]);

  const handleAction = async (issueId, action) => {
    setActionLoading(`${issueId}-${action}`);
    try {
      await axios.post(`${API}/admin/reconciliation/issues/${issueId}/${action}`);
      toast.success(`Islem basarili: ${action}`);
      fetchIssues();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
    setActionLoading(null);
  };

  const handleBulkDismiss = async () => {
    const ids = issues.map(i => i.id);
    if (!ids.length) return;
    try {
      await axios.post(`${API}/admin/reconciliation/issues/bulk-dismiss`, { issue_ids: ids, reason: 'Bulk admin dismiss' });
      toast.success(`${ids.length} sorun kapatildi`);
      fetchIssues();
    } catch (e) { toast.error('Toplu kapatma hatasi'); }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        <Select value={filters.status} onValueChange={v => setFilters(f => ({...f, status: v}))}>
          <SelectTrigger data-testid="filter-status" className="w-36 bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Durum</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="investigating">Investigating</SelectItem>
            <SelectItem value="retrying">Retrying</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="dismissed">Dismissed</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filters.severity} onValueChange={v => setFilters(f => ({...f, severity: v}))}>
          <SelectTrigger data-testid="filter-severity" className="w-32 bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Seviye</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>
        <Select value={filters.issue_type} onValueChange={v => setFilters(f => ({...f, issue_type: v}))}>
          <SelectTrigger data-testid="filter-type" className="w-44 bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Tipler</SelectItem>
            <SelectItem value="inventory_mismatch">Envanter Uyumsuzlugu</SelectItem>
            <SelectItem value="rate_mismatch">Fiyat Uyumsuzlugu</SelectItem>
            <SelectItem value="stale_sync">Eski Senkronizasyon</SelectItem>
            <SelectItem value="invalid_mapping">Gecersiz Eslestirme</SelectItem>
            <SelectItem value="ack_failed">ACK Hatasi</SelectItem>
            <SelectItem value="unprocessed_import">Islenmeyen Import</SelectItem>
          </SelectContent>
        </Select>
        <Button data-testid="refresh-issues" variant="outline" size="sm" onClick={fetchIssues} className="border-slate-700 text-slate-300">
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
        </Button>
        {issues.length > 0 && (
          <Button data-testid="bulk-dismiss-btn" variant="outline" size="sm" onClick={handleBulkDismiss} className="border-red-700 text-red-400 ml-auto">
            <Trash2 className="w-3.5 h-3.5 mr-1" /> Toplu Kapat ({issues.length})
          </Button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : issues.length === 0 ? (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Sorun bulunamadi</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {issues.map(issue => (
            <Card key={issue.id} data-testid={`issue-${issue.id}`} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <SeverityBadge severity={issue.severity} />
                      <Badge className="bg-slate-700/50 text-slate-300 border-slate-600 text-xs border">{issue.issue_type?.replace(/_/g,' ')}</Badge>
                      <Badge className="bg-blue-500/10 text-blue-400 border-blue-500/30 text-xs border">{issue.status}</Badge>
                    </div>
                    <p className="text-sm text-white truncate">{issue.description}</p>
                    <div className="flex gap-3 text-[10px] text-slate-500 mt-1">
                      <span>Connector: {issue.connector_id?.slice(0,8)}...</span>
                      <span>{new Date(issue.created_at).toLocaleString('tr-TR')}</span>
                    </div>
                  </div>
                  <div className="flex gap-1 flex-shrink-0">
                    {(issue.suggested_actions || []).includes('retry_sync') && (
                      <Button data-testid={`retry-sync-${issue.id}`} size="sm" variant="ghost" className="text-emerald-400 h-7 px-2"
                        disabled={actionLoading === `${issue.id}-retry-sync`}
                        onClick={() => handleAction(issue.id, 'retry-sync')}>
                        {actionLoading === `${issue.id}-retry-sync` ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                      </Button>
                    )}
                    {(issue.suggested_actions || []).includes('retry_ack') && (
                      <Button size="sm" variant="ghost" className="text-blue-400 h-7 px-2"
                        onClick={() => handleAction(issue.id, 'retry-ack')}>
                        <RefreshCw className="w-3 h-3" />
                      </Button>
                    )}
                    {(issue.suggested_actions || []).includes('revalidate_mapping') && (
                      <Button size="sm" variant="ghost" className="text-amber-400 h-7 px-2"
                        onClick={() => handleAction(issue.id, 'revalidate-mapping')}>
                        <CheckCircle className="w-3 h-3" />
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" className="text-slate-400 h-7 px-2"
                      onClick={() => handleAction(issue.id, 'send-to-review')}>
                      <Eye className="w-3 h-3" />
                    </Button>
                    <Button size="sm" variant="ghost" className="text-red-400 h-7 px-2"
                      onClick={() => axios.post(`${API}/reconciliation/issues/${issue.id}/dismiss`, { reason: 'Admin dismissed' }).then(() => { toast.success('Kapatildi'); fetchIssues(); })}>
                      <XCircle className="w-3 h-3" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

/* ─── Scheduler Status Tab ──────────────────────────────────── */

const SchedulerTab = ({ user }) => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggerLoading, setTriggerLoading] = useState(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/admin/scheduler/status`);
      setStatus(data);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleTrigger = async (connectorId) => {
    setTriggerLoading(connectorId);
    try {
      const { data } = await axios.post(`${API}/admin/scheduler/trigger/${connectorId}`);
      toast.success(`Scheduler calisti: ${data.total_actions || 0} aksiyon`);
      fetchStatus();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
    setTriggerLoading(null);
  };

  const handleTriggerAll = async () => {
    setTriggerLoading('all');
    try {
      const { data } = await axios.post(`${API}/admin/scheduler/trigger-all`);
      toast.success(`Tum scheduler calisti: ${data.connectors_checked || 0} connector`);
      fetchStatus();
    } catch (e) { toast.error('Hata'); }
    setTriggerLoading(null);
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Zamanlayici Durumu</h3>
        <div className="flex gap-2">
          <Button data-testid="trigger-all-btn" size="sm" variant="outline" className="border-slate-700 text-slate-300"
            disabled={triggerLoading === 'all'} onClick={handleTriggerAll}>
            {triggerLoading === 'all' ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Zap className="w-3.5 h-3.5 mr-1" />}
            Tumu Calistir
          </Button>
          <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchStatus}>
            <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
          </Button>
        </div>
      </div>

      {(status?.connectors || []).map(c => (
        <Card key={c.connector_id} data-testid={`scheduler-${c.connector_id}`} className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-medium text-white">{c.display_name}</p>
                <p className="text-xs text-slate-500">{c.provider} - {c.connector_id.slice(0,8)}...</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge className={`border text-xs ${c.status === 'active' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-slate-500/15 text-slate-400 border-slate-500/30'}`}>
                  {c.status}
                </Badge>
                <Button data-testid={`trigger-${c.connector_id}`} size="sm" variant="ghost" className="text-blue-400 h-7"
                  disabled={triggerLoading === c.connector_id} onClick={() => handleTrigger(c.connector_id)}>
                  {triggerLoading === c.connector_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-900/50 rounded p-2">
                <p className="text-[10px] text-slate-500">Stale Jobs</p>
                <p className={`text-lg font-semibold ${c.stale_jobs > 0 ? 'text-amber-400' : 'text-white'}`}>{c.stale_jobs}</p>
              </div>
              <div className="bg-slate-900/50 rounded p-2">
                <p className="text-[10px] text-slate-500">Failed Jobs</p>
                <p className={`text-lg font-semibold ${c.failed_jobs > 0 ? 'text-red-400' : 'text-white'}`}>{c.failed_jobs}</p>
              </div>
              <div className="bg-slate-900/50 rounded p-2">
                <p className="text-[10px] text-slate-500">Consecutive Fails</p>
                <p className={`text-lg font-semibold ${c.consecutive_failures > 2 ? 'text-red-400' : 'text-white'}`}>{c.consecutive_failures}</p>
              </div>
              <div className="bg-slate-900/50 rounded p-2">
                <p className="text-[10px] text-slate-500">Last Sync</p>
                <p className="text-xs text-white truncate">{c.last_successful_sync ? new Date(c.last_successful_sync).toLocaleString('tr-TR') : 'Yok'}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
      {(!status?.connectors || status.connectors.length === 0) && (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Aktif connector bulunamadi</CardContent></Card>
      )}
    </div>
  );
};

/* ─── Credentials Tab ───────────────────────────────────────── */

const CredentialsTab = ({ user }) => {
  const [creds, setCreds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);

  const fetchCreds = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/admin/credentials`);
      setCreds(data.credentials || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchCreds(); }, [fetchCreds]);

  const handleTest = async (cid) => {
    setActionLoading(`test-${cid}`);
    try {
      const { data } = await axios.post(`${API}/admin/credentials/${cid}/test`);
      toast.success(`Baglanti testi: ${data.success ? 'Basarili' : 'Basarisiz'}`);
    } catch (e) { toast.error(e.response?.data?.detail || 'Test hatasi'); }
    setActionLoading(null);
  };

  const handleRotate = async (cid) => {
    setActionLoading(`rotate-${cid}`);
    toast.info('Credential rotation icin yeni degerler gerekli');
    setActionLoading(null);
  };

  const handleDisable = async (cid) => {
    setActionLoading(`disable-${cid}`);
    try {
      await axios.post(`${API}/admin/credentials/${cid}/disable`);
      toast.success('Connector devre disi birakildi');
      fetchCreds();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
    setActionLoading(null);
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Credential Yonetimi (RBAC Korumali)</h3>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchCreds}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
        </Button>
      </div>
      {creds.map(c => (
        <Card key={c.connector_id} data-testid={`cred-${c.connector_id}`} className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <Key className="w-4 h-4 text-amber-400" />
                  <span className="text-sm font-medium text-white">{c.display_name}</span>
                  <Badge className={`border text-xs ${c.encrypted ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'}`}>
                    {c.encrypted ? c.encryption_algorithm || 'Encrypted' : 'Not Encrypted'}
                  </Badge>
                  <Badge className={`border text-xs ${c.status === 'active' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-slate-500/15 text-slate-400 border-slate-500/30'}`}>
                    {c.status}
                  </Badge>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                  <div><span className="text-slate-500">Provider:</span> <span className="text-white">{c.provider}</span></div>
                  <div><span className="text-slate-500">Environment:</span> <span className="text-white">{c.environment}</span></div>
                  <div><span className="text-slate-500">Last Tested:</span> <span className="text-white">{c.last_tested ? new Date(c.last_tested).toLocaleDateString('tr-TR') : '-'}</span></div>
                  <div><span className="text-slate-500">Last Rotated:</span> <span className="text-white">{c.last_rotated ? new Date(c.last_rotated).toLocaleDateString('tr-TR') : '-'}</span></div>
                </div>
                {c.masked_credentials && Object.keys(c.masked_credentials).length > 0 && (
                  <div className="mt-2 flex gap-2 flex-wrap">
                    {Object.entries(c.masked_credentials).map(([k, v]) => (
                      <span key={k} className="text-[10px] bg-slate-900 text-slate-400 px-2 py-0.5 rounded font-mono">{k}: {v}</span>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex gap-1 flex-shrink-0">
                <Button data-testid={`test-cred-${c.connector_id}`} size="sm" variant="ghost" className="text-emerald-400 h-7 px-2"
                  disabled={actionLoading === `test-${c.connector_id}`} onClick={() => handleTest(c.connector_id)}>
                  {actionLoading === `test-${c.connector_id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                </Button>
                <Button size="sm" variant="ghost" className="text-blue-400 h-7 px-2" onClick={() => handleRotate(c.connector_id)}>
                  <RotateCcw className="w-3 h-3" />
                </Button>
                <Button data-testid={`disable-${c.connector_id}`} size="sm" variant="ghost" className="text-red-400 h-7 px-2"
                  disabled={actionLoading === `disable-${c.connector_id}`} onClick={() => handleDisable(c.connector_id)}>
                  {actionLoading === `disable-${c.connector_id}` ? <Loader2 className="w-3 h-3 animate-spin" /> : <XCircle className="w-3 h-3" />}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
      {creds.length === 0 && (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Credential bulunamadi</CardContent></Card>
      )}
    </div>
  );
};

/* ─── Error Queue Tab ───────────────────────────────────────── */

const ErrorQueueTab = ({ user }) => {
  const [queue, setQueue] = useState({ items: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('all');
  const [actionLoading, setActionLoading] = useState(null);
  const [selected, setSelected] = useState(new Set());

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterType !== 'all' ? `?error_type=${filterType}` : '';
      const { data } = await axios.get(`${API}/admin/error-queue${params}`);
      setQueue(data);
    } catch { /* silent */ }
    setLoading(false);
  }, [filterType]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const toggleSelect = (id) => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelected(new Set(queue.items.map(i => i.id)));

  const handleAction = async (itemId, errorType, action) => {
    setActionLoading(`${itemId}-${action}`);
    try {
      await axios.post(`${API}/admin/error-queue/${action}`, { item_id: itemId, error_type: errorType });
      toast.success(`${action} basarili`);
      fetchQueue();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
    setActionLoading(null);
  };

  const handleBulk = async (action) => {
    if (selected.size === 0) return;
    const items = queue.items.filter(i => selected.has(i.id));
    const groups = {};
    items.forEach(i => { const t = i.error_type; if (!groups[t]) groups[t] = []; groups[t].push(i.id); });
    try {
      for (const [errorType, ids] of Object.entries(groups)) {
        await axios.post(`${API}/admin/error-queue/bulk-${action}`, { item_ids: ids, error_type: errorType, reason: 'Bulk admin action' });
      }
      toast.success(`Toplu ${action}: ${selected.size} oge`);
      setSelected(new Set());
      fetchQueue();
    } catch { toast.error('Toplu islem hatasi'); }
  };

  const summary = queue.summary || {};

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard title="Toplam Hata" value={summary.total || 0} icon={AlertOctagon} color="text-red-400" />
        <MetricCard title="Sync Hatasi" value={summary.sync_failed || 0} icon={RefreshCw} color="text-orange-400" />
        <MetricCard title="Import Hatasi" value={summary.import_failed || 0} icon={Database} color="text-amber-400" />
        <MetricCard title="ACK Hatasi" value={summary.ack_failed || 0} icon={AlertTriangle} color="text-red-400" />
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger data-testid="error-type-filter" className="w-40 bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Tum Tipler</SelectItem>
            <SelectItem value="sync_failed">Sync Hatasi</SelectItem>
            <SelectItem value="import_failed">Import Hatasi</SelectItem>
            <SelectItem value="ack_failed">ACK Hatasi</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchQueue}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
        </Button>
        {selected.size > 0 && (
          <>
            <Button data-testid="bulk-retry-btn" size="sm" variant="outline" className="border-emerald-700 text-emerald-400 ml-auto" onClick={() => handleBulk('retry')}>
              <RotateCcw className="w-3.5 h-3.5 mr-1" /> Toplu Yeniden Dene ({selected.size})
            </Button>
            <Button data-testid="bulk-dismiss-btn" size="sm" variant="outline" className="border-red-700 text-red-400" onClick={() => handleBulk('dismiss')}>
              <Trash2 className="w-3.5 h-3.5 mr-1" /> Toplu Kapat ({selected.size})
            </Button>
          </>
        )}
        {queue.items.length > 0 && selected.size === 0 && (
          <Button size="sm" variant="ghost" className="text-slate-400 ml-auto" onClick={selectAll}>Tumu Sec</Button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : queue.items.length === 0 ? (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Hata kuyrugunda oge yok</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {queue.items.map(item => (
            <Card key={item.id} data-testid={`error-${item.id}`}
              className={`bg-slate-800/50 border-slate-700 cursor-pointer ${selected.has(item.id) ? 'ring-1 ring-blue-500' : ''}`}
              onClick={() => toggleSelect(item.id)}>
              <CardContent className="p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge className="bg-red-500/15 text-red-400 border-red-500/30 border text-xs">{item.error_type?.replace(/_/g,' ')}</Badge>
                      <span className="text-xs text-slate-500">{item.connector_id?.slice(0,8)}...</span>
                      <span className="text-[10px] text-slate-600">{new Date(item.created_at).toLocaleString('tr-TR')}</span>
                    </div>
                    <p className="text-xs text-slate-300 truncate">{item.last_error || item.import_error || item.status || '-'}</p>
                    {item.retry_count > 0 && <span className="text-[10px] text-orange-400">Retry: {item.retry_count}</span>}
                  </div>
                  <div className="flex gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
                    <Button size="sm" variant="ghost" className="text-emerald-400 h-6 px-1.5"
                      onClick={() => handleAction(item.id, item.error_type, 'retry')}>
                      <RotateCcw className="w-3 h-3" />
                    </Button>
                    <Button size="sm" variant="ghost" className="text-amber-400 h-6 px-1.5"
                      onClick={() => handleAction(item.id, item.error_type, 'escalate')}>
                      <ArrowUpRight className="w-3 h-3" />
                    </Button>
                    <Button size="sm" variant="ghost" className="text-red-400 h-6 px-1.5"
                      onClick={() => handleAction(item.id, item.error_type, 'dismiss')}>
                      <XCircle className="w-3 h-3" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

/* ─── Sync Health Dashboard Tab ─────────────────────────────── */

const SyncHealthTab = ({ user }) => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/admin/sync-health`);
      setHealth(data);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchHealth(); }, [fetchHealth]);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  if (!health) return null;

  const trend = health.sync_trend_24h || [];
  const maxTotal = Math.max(1, ...trend.map(t => t.total));

  return (
    <div className="space-y-6">
      {/* Overall Score */}
      <div className="flex items-center gap-6">
        <ScoreRing score={health.overall_health_score} size={100} />
        <div>
          <p className="text-lg font-semibold text-white flex items-center gap-2">
            <StatusDot status={health.overall_status} /> Genel Saglik: {health.overall_status?.toUpperCase()}
          </p>
          <p className="text-sm text-slate-400">{health.connector_count} connector izleniyor</p>
          <div className="flex gap-4 mt-2 text-xs">
            <span className="text-red-400">{health.error_summary?.total || 0} hata</span>
            <span className="text-amber-400">{health.error_summary?.sync_failed || 0} sync hatasi</span>
          </div>
        </div>
        <Button size="sm" variant="outline" className="ml-auto border-slate-700 text-slate-300" onClick={fetchHealth}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
        </Button>
      </div>

      {/* 24h Trend Chart */}
      {trend.length > 0 && (
        <Card className="bg-slate-800/50 border-slate-700">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-300">24 Saatlik Sync Trendi</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-end gap-1 h-32">
              {trend.map((t, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                  <div className="w-full flex flex-col-reverse" style={{height: 100}}>
                    <div className="bg-emerald-500/60 rounded-t" style={{height: `${(t.succeeded||0)/maxTotal*100}%`}} />
                    <div className="bg-red-500/60" style={{height: `${(t.failed||0)/maxTotal*100}%`}} />
                  </div>
                  <span className="text-[8px] text-slate-600 truncate w-full text-center">{t.hour?.slice(11) || ''}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-4 mt-2 text-[10px]">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-emerald-500" />Basarili</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-red-500" />Basarisiz</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Per-connector health */}
      <div className="grid gap-3">
        {(health.connectors || []).map(c => (
          <Card key={c.connector_id} data-testid={`health-${c.connector_id}`} className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <ScoreRing score={c.health_score} size={50} />
                  <div>
                    <p className="text-sm font-medium text-white">{c.display_name}</p>
                    <p className="text-xs text-slate-500 flex items-center gap-1"><StatusDot status={c.status} /> {c.status} - {c.provider}</p>
                  </div>
                </div>
                <div className="text-right text-xs">
                  <p className="text-slate-400">Open Issues: <span className="text-white">{c.open_issues}</span></p>
                  <p className="text-slate-400">Failures: <span className="text-red-400">{c.details?.consecutive_failures || 0}</span></p>
                </div>
              </div>
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                {Object.entries(c.by_severity || {}).map(([sev, count]) => (
                  <div key={sev} className="bg-slate-900/50 rounded p-1.5 text-center">
                    <p className="text-[9px] text-slate-500">{sev}</p>
                    <p className="text-sm font-semibold text-white">{count}</p>
                  </div>
                ))}
                {Object.entries(c.sync_metrics?.sync_jobs || {}).map(([st, count]) => (
                  <div key={st} className="bg-slate-900/50 rounded p-1.5 text-center">
                    <p className="text-[9px] text-slate-500">{st}</p>
                    <p className="text-sm font-semibold text-white">{count}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

/* ─── Production Readiness Tab ──────────────────────────────── */

const ReadinessTab = ({ user }) => {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(null);

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/admin/production-readiness/overview`);
      setReports(data.reports || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchOverview(); }, [fetchOverview]);

  const handleRunCheck = async (connectorId) => {
    setRunLoading(connectorId);
    try {
      const { data } = await axios.post(`${API}/admin/production-readiness/${connectorId}`);
      setReports(prev => prev.map(r => r.connector_id === connectorId ? data : r));
      toast.success('Kontrol tamamlandi');
    } catch (e) { toast.error('Hata'); }
    setRunLoading(null);
  };

  const checkIcon = (status) => {
    if (status === 'passed') return <CheckCircle className="w-4 h-4 text-emerald-400" />;
    if (status === 'warning') return <AlertTriangle className="w-4 h-4 text-amber-400" />;
    return <XCircle className="w-4 h-4 text-red-400" />;
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Production Readiness Report</h3>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchOverview}>
          <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
        </Button>
      </div>

      {reports.map(r => (
        <Card key={r.connector_id} data-testid={`readiness-${r.connector_id}`} className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-sm font-medium text-white">{r.display_name}</p>
                <p className="text-xs text-slate-500">{r.provider} - {r.connector_id?.slice(0,8)}...</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge data-testid={`readiness-badge-${r.connector_id}`} className={`border text-xs ${
                  r.production_recommendation === 'READY_FOR_PRODUCTION' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' :
                  r.production_recommendation === 'READY_WITH_WARNINGS' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                  'bg-red-500/15 text-red-400 border-red-500/30'
                }`}>{r.production_recommendation?.replace(/_/g,' ')}</Badge>
                <Button size="sm" variant="ghost" className="text-blue-400 h-7"
                  disabled={runLoading === r.connector_id} onClick={() => handleRunCheck(r.connector_id)}>
                  {runLoading === r.connector_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                </Button>
              </div>
            </div>
            <div className="flex gap-4 mb-3 text-xs">
              <span className="text-emerald-400">{r.passed_checks} passed</span>
              <span className="text-red-400">{r.failed_checks} failed</span>
              <span className="text-amber-400">{r.warning_checks} warnings</span>
            </div>
            <div className="space-y-1.5">
              {(r.checks || []).map((check, i) => (
                <div key={i} className="flex items-center gap-2 bg-slate-900/40 rounded p-2">
                  {checkIcon(check.status)}
                  <span className="text-xs text-white flex-1">{check.check?.replace(/_/g,' ')}</span>
                  <span className="text-[10px] text-slate-500 max-w-[50%] truncate text-right">{check.detail}</span>
                </div>
              ))}
            </div>
            {r.blocker_issues?.length > 0 && (
              <div className="mt-2 p-2 bg-red-500/10 rounded border border-red-500/20">
                <p className="text-xs text-red-400 font-medium">Blocker Issues:</p>
                {r.blocker_issues.map((b, i) => <p key={i} className="text-xs text-red-300">{b.replace(/_/g,' ')}</p>)}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
      {reports.length === 0 && (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Connector bulunamadi</CardContent></Card>
      )}
    </div>
  );
};

/* ─── Observability Tab ─────────────────────────────────────── */

const ObservabilityTab = ({ user }) => {
  const [metrics, setMetrics] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAudit, setShowAudit] = useState(false);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const [metricsRes, auditRes] = await Promise.all([
        axios.get(`${API}/admin/observability/metrics`),
        axios.get(`${API}/admin/observability/audit-trail?limit=50`),
      ]);
      setMetrics(metricsRes.data.metrics || []);
      setAudit(auditRes.data.logs || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchMetrics(); }, [fetchMetrics]);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Operasyonel Gozlemlenebilirlik</h3>
        <div className="flex gap-2">
          <Button size="sm" variant={showAudit ? 'default' : 'outline'}
            className={showAudit ? 'bg-blue-600' : 'border-slate-700 text-slate-300'} onClick={() => setShowAudit(!showAudit)}>
            <FileText className="w-3.5 h-3.5 mr-1" /> Audit Trail
          </Button>
          <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchMetrics}>
            <RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile
          </Button>
        </div>
      </div>

      {!showAudit ? (
        <div className="space-y-3">
          {metrics.map(m => (
            <Card key={m.connector_id} data-testid={`obs-${m.connector_id}`} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-4">
                <p className="text-sm font-medium text-white mb-3">{m.display_name} <span className="text-slate-500 text-xs">({m.provider})</span></p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="bg-slate-900/50 rounded p-2 text-center">
                    <p className="text-[10px] text-slate-500">Sync Basari Orani</p>
                    <p className={`text-xl font-semibold ${m.sync_success_rate >= 90 ? 'text-emerald-400' : m.sync_success_rate >= 50 ? 'text-amber-400' : 'text-red-400'}`}>{m.sync_success_rate}%</p>
                    <p className="text-[9px] text-slate-600">{m.sync_succeeded}/{m.sync_total}</p>
                  </div>
                  <div className="bg-slate-900/50 rounded p-2 text-center">
                    <p className="text-[10px] text-slate-500">ACK Basari Orani</p>
                    <p className={`text-xl font-semibold ${m.ack_success_rate >= 90 ? 'text-emerald-400' : 'text-amber-400'}`}>{m.ack_success_rate}%</p>
                    <p className="text-[9px] text-slate-600">{m.ack_sent}/{m.total_imports}</p>
                  </div>
                  <div className="bg-slate-900/50 rounded p-2 text-center">
                    <p className="text-[10px] text-slate-500">Retry Orani</p>
                    <p className="text-xl font-semibold text-orange-400">{m.retry_rate}%</p>
                    <p className="text-[9px] text-slate-600">{m.retry_jobs} retry</p>
                  </div>
                  <div className="bg-slate-900/50 rounded p-2 text-center">
                    <p className="text-[10px] text-slate-500">Mapping Dogruluk</p>
                    <p className={`text-xl font-semibold ${m.mapping_validation_rate >= 90 ? 'text-emerald-400' : 'text-amber-400'}`}>{m.mapping_validation_rate}%</p>
                    <p className="text-[9px] text-slate-600">{m.valid_mappings}/{m.total_mappings}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
          {metrics.length === 0 && (
            <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Metrik bulunamadi</CardContent></Card>
          )}
        </div>
      ) : (
        <div className="space-y-1">
          {audit.map((log, i) => (
            <div key={i} className="flex items-center gap-3 bg-slate-800/50 rounded p-2 border border-slate-700/50">
              <span className="text-[10px] text-slate-600 w-28 flex-shrink-0">{new Date(log.created_at).toLocaleString('tr-TR')}</span>
              <Badge className="bg-slate-700/50 text-slate-300 border-slate-600 text-[10px] border">{log.action?.replace(/_/g,' ')}</Badge>
              <span className="text-xs text-slate-400 truncate flex-1">{log.connector_id?.slice(0,8) || '-'}</span>
              <span className="text-[10px] text-slate-500">{log.actor_id?.slice(0,8) || 'system'}</span>
            </div>
          ))}
          {audit.length === 0 && <p className="text-center text-slate-500 py-8 text-sm">Audit kaydi yok</p>}
        </div>
      )}
    </div>
  );
};

/* ─── Main Admin Control Panel ──────────────────────────────── */

const AdminControlPanel = ({ user, tenant, onLogout }) => {
  const [activeTab, setActiveTab] = useState('health');

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentPage="admin-control-panel">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div>
          <h1 data-testid="admin-panel-title" className="text-2xl font-bold text-white">Admin Control Panel</h1>
          <p className="text-sm text-slate-400 mt-1">Channel Manager operasyonel yonetim ve izleme merkezi</p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-800 border border-slate-700 flex-wrap h-auto gap-1 p-1">
            <TabsTrigger data-testid="tab-health" value="health" className="data-[state=active]:bg-slate-700 text-xs gap-1">
              <Activity className="w-3.5 h-3.5" /> Sync Health
            </TabsTrigger>
            <TabsTrigger data-testid="tab-issues" value="issues" className="data-[state=active]:bg-slate-700 text-xs gap-1">
              <AlertTriangle className="w-3.5 h-3.5" /> Reconciliation
            </TabsTrigger>
            <TabsTrigger data-testid="tab-scheduler" value="scheduler" className="data-[state=active]:bg-slate-700 text-xs gap-1">
              <Clock className="w-3.5 h-3.5" /> Scheduler
            </TabsTrigger>
            <TabsTrigger data-testid="tab-credentials" value="credentials" className="data-[state=active]:bg-slate-700 text-xs gap-1">
              <Key className="w-3.5 h-3.5" /> Credentials
            </TabsTrigger>
            <TabsTrigger data-testid="tab-errors" value="errors" className="data-[state=active]:bg-slate-700 text-xs gap-1">
              <AlertOctagon className="w-3.5 h-3.5" /> Error Queue
            </TabsTrigger>
            <TabsTrigger data-testid="tab-observability" value="observability" className="data-[state=active]:bg-slate-700 text-xs gap-1">
              <Eye className="w-3.5 h-3.5" /> Observability
            </TabsTrigger>
            <TabsTrigger data-testid="tab-readiness" value="readiness" className="data-[state=active]:bg-slate-700 text-xs gap-1">
              <Shield className="w-3.5 h-3.5" /> Readiness
            </TabsTrigger>
          </TabsList>

          <TabsContent value="health"><SyncHealthTab user={user} /></TabsContent>
          <TabsContent value="issues"><ReconciliationTab user={user} /></TabsContent>
          <TabsContent value="scheduler"><SchedulerTab user={user} /></TabsContent>
          <TabsContent value="credentials"><CredentialsTab user={user} /></TabsContent>
          <TabsContent value="errors"><ErrorQueueTab user={user} /></TabsContent>
          <TabsContent value="observability"><ObservabilityTab user={user} /></TabsContent>
          <TabsContent value="readiness"><ReadinessTab user={user} /></TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default AdminControlPanel;
