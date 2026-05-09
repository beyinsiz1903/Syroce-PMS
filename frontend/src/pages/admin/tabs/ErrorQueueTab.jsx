import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, RotateCcw, ArrowUpRight, XCircle, Trash2, AlertOctagon, AlertTriangle, Database } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { API, MetricCard } from '../shared';
import { useTranslation } from 'react-i18next';

const ErrorQueueTab = () => {
  const { t } = useTranslation();
  const [queue, setQueue] = useState({ items: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('all');
  const [selected, setSelected] = useState(new Set());

  const fetchQueue = useCallback(async () => {
    setLoading(true);
    try { const params = filterType !== 'all' ? `?error_type=${filterType}` : ''; const { data } = await axios.get(`${API}/admin/error-queue${params}`); setQueue(data); } catch { /* silent */ }
    setLoading(false);
  }, [filterType]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const toggleSelect = (id) => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll = () => setSelected(new Set(queue.items.map(i => i.id)));

  const handleAction = async (itemId, errorType, action) => {
    try { await axios.post(`${API}/admin/error-queue/${action}`, { item_id: itemId, error_type: errorType }); toast.success(`${action} basarili`); fetchQueue(); } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const handleBulk = async (action) => {
    if (selected.size === 0) return;
    const items = queue.items.filter(i => selected.has(i.id));
    const groups = {};
    items.forEach(i => { const t = i.error_type; if (!groups[t]) groups[t] = []; groups[t].push(i.id); });
    try {
      for (const [errorType, ids] of Object.entries(groups)) { await axios.post(`${API}/admin/error-queue/bulk-${action}`, { item_ids: ids, error_type: errorType, reason: 'Bulk admin action' }); }
      toast.success(`Toplu ${action}: ${selected.size} oge`); setSelected(new Set()); fetchQueue();
    } catch { toast.error('Toplu işlem hatası'); }
  };

  const summary = queue.summary || {};

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard title={t('cm.pages_admin_tabs_ErrorQueueTab.toplam_hata')} value={summary.total || 0} icon={AlertOctagon} color="text-red-400" />
        <MetricCard title={t('cm.pages_admin_tabs_ErrorQueueTab.sync_hatasi')} value={summary.sync_failed || 0} icon={RefreshCw} color="text-amber-400" />
        <MetricCard title={t('cm.pages_admin_tabs_ErrorQueueTab.import_hatasi')} value={summary.import_failed || 0} icon={Database} color="text-amber-400" />
        <MetricCard title={t('cm.pages_admin_tabs_ErrorQueueTab.ack_hatasi')} value={summary.ack_failed || 0} icon={AlertTriangle} color="text-red-400" />
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger data-testid="error-type-filter" className="w-40 bg-slate-800 border-slate-700 text-white"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('cm.pages_admin_tabs_ErrorQueueTab.tum_tipler')}</SelectItem>
            <SelectItem value="sync_failed">{t('cm.pages_admin_tabs_ErrorQueueTab.sync_hatasi_b6679')}</SelectItem>
            <SelectItem value="import_failed">{t('cm.pages_admin_tabs_ErrorQueueTab.import_hatasi_f1031')}</SelectItem>
            <SelectItem value="ack_failed">{t('cm.pages_admin_tabs_ErrorQueueTab.ack_hatasi_3b9e2')}</SelectItem>
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchQueue}><RefreshCw className="w-3.5 h-3.5 mr-1" /> {t('cm.pages_admin_tabs_ErrorQueueTab.yenile')}</Button>
        {selected.size > 0 && (
          <>
            <Button data-testid="bulk-retry-btn" size="sm" variant="outline" className="border-emerald-700 text-emerald-400 ml-auto" onClick={() => handleBulk('retry')}><RotateCcw className="w-3.5 h-3.5 mr-1" /> Toplu Yeniden Dene ({selected.size})</Button>
            <Button data-testid="bulk-dismiss-btn" size="sm" variant="outline" className="border-red-700 text-red-400" onClick={() => handleBulk('dismiss')}><Trash2 className="w-3.5 h-3.5 mr-1" /> {t('cm.pages_admin_tabs_ErrorQueueTab.toplu_kapat')}{selected.size})</Button>
          </>
        )}
        {queue.items.length > 0 && selected.size === 0 && <Button size="sm" variant="ghost" className="text-slate-400 ml-auto" onClick={selectAll}>Tumu Sec</Button>}
      </div>
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>
      ) : queue.items.length === 0 ? (
        <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">{t('cm.pages_admin_tabs_ErrorQueueTab.hata_kuyrugunda_oge_yok')}</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {queue.items.map(item => (
            <Card key={item.id} data-testid={`error-${item.id}`} className={`bg-slate-800/50 border-slate-700 cursor-pointer ${selected.has(item.id) ? 'ring-1 ring-blue-500' : ''}`} onClick={() => toggleSelect(item.id)}>
              <CardContent className="p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge className="bg-red-500/15 text-red-400 border-red-500/30 border text-xs">{item.error_type?.replace(/_/g,' ')}</Badge>
                      <span className="text-xs text-slate-500">{item.connector_id?.slice(0,8)}...</span>
                      <span className="text-[10px] text-slate-600">{new Date(item.created_at).toLocaleString('tr-TR')}</span>
                    </div>
                    <p className="text-xs text-slate-300 truncate">{item.last_error || item.import_error || item.status || '-'}</p>
                    {item.retry_count > 0 && <span className="text-[10px] text-amber-400">Retry: {item.retry_count}</span>}
                  </div>
                  <div className="flex gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
                    <Button size="sm" variant="ghost" className="text-emerald-400 h-6 px-1.5" onClick={() => handleAction(item.id, item.error_type, 'retry')}><RotateCcw className="w-3 h-3" /></Button>
                    <Button size="sm" variant="ghost" className="text-amber-400 h-6 px-1.5" onClick={() => handleAction(item.id, item.error_type, 'escalate')}><ArrowUpRight className="w-3 h-3" /></Button>
                    <Button size="sm" variant="ghost" className="text-red-400 h-6 px-1.5" onClick={() => handleAction(item.id, item.error_type, 'dismiss')}><XCircle className="w-3 h-3" /></Button>
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

export default ErrorQueueTab;
