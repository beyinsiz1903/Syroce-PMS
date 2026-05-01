import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, Zap } from 'lucide-react';
import { API } from '../shared';

const SchedulerTab = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggerLoading, setTriggerLoading] = useState(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try { const { data } = await axios.get(`${API}/admin/scheduler/status`); setStatus(data); } catch { /* silent */ }
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
      toast.success(`Tüm scheduler calisti: ${data.connectors_checked || 0} connector`);
      fetchStatus();
    } catch { toast.error('Hata'); }
    setTriggerLoading(null);
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Zamanlayici Durumu</h3>
        <div className="flex gap-2">
          <Button data-testid="trigger-all-btn" size="sm" variant="outline" className="border-slate-700 text-slate-300" disabled={triggerLoading === 'all'} onClick={handleTriggerAll}>
            {triggerLoading === 'all' ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Zap className="w-3.5 h-3.5 mr-1" />} Tumu Calistir
          </Button>
          <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchStatus}><RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile</Button>
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
                <Badge className={`border text-xs ${c.status === 'active' ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-slate-500/15 text-slate-400 border-slate-500/30'}`}>{c.status}</Badge>
                <Button data-testid={`trigger-${c.connector_id}`} size="sm" variant="ghost" className="text-blue-400 h-7" disabled={triggerLoading === c.connector_id} onClick={() => handleTrigger(c.connector_id)}>
                  {triggerLoading === c.connector_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-slate-900/50 rounded p-2"><p className="text-[10px] text-slate-500">Stale Jobs</p><p className={`text-lg font-semibold ${c.stale_jobs > 0 ? 'text-amber-400' : 'text-white'}`}>{c.stale_jobs}</p></div>
              <div className="bg-slate-900/50 rounded p-2"><p className="text-[10px] text-slate-500">Failed Jobs</p><p className={`text-lg font-semibold ${c.failed_jobs > 0 ? 'text-red-400' : 'text-white'}`}>{c.failed_jobs}</p></div>
              <div className="bg-slate-900/50 rounded p-2"><p className="text-[10px] text-slate-500">Consecutive Fails</p><p className={`text-lg font-semibold ${c.consecutive_failures > 2 ? 'text-red-400' : 'text-white'}`}>{c.consecutive_failures}</p></div>
              <div className="bg-slate-900/50 rounded p-2"><p className="text-[10px] text-slate-500">Last Sync</p><p className="text-xs text-white truncate">{c.last_successful_sync ? new Date(c.last_successful_sync).toLocaleString('tr-TR') : 'Yok'}</p></div>
            </div>
          </CardContent>
        </Card>
      ))}
      {(!status?.connectors || status.connectors.length === 0) && (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Aktif connector bulunamadı</CardContent></Card>
      )}
    </div>
  );
};

export default SchedulerTab;
