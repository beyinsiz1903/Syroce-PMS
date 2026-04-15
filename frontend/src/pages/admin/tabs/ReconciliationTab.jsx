import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, RotateCcw, CheckCircle, Eye, XCircle, Trash2 } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { API, SeverityBadge } from '../shared';

const ReconciliationTab = () => {
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
    } catch { toast.error('Toplu kapatma hatasi'); }
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
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Sorun bulunamadı</CardContent></Card>
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
                      <Button size="sm" variant="ghost" className="text-blue-400 h-7 px-2" onClick={() => handleAction(issue.id, 'retry-ack')}><RefreshCw className="w-3 h-3" /></Button>
                    )}
                    {(issue.suggested_actions || []).includes('revalidate_mapping') && (
                      <Button size="sm" variant="ghost" className="text-amber-400 h-7 px-2" onClick={() => handleAction(issue.id, 'revalidate-mapping')}><CheckCircle className="w-3 h-3" /></Button>
                    )}
                    <Button size="sm" variant="ghost" className="text-slate-400 h-7 px-2" onClick={() => handleAction(issue.id, 'send-to-review')}><Eye className="w-3 h-3" /></Button>
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

export default ReconciliationTab;
