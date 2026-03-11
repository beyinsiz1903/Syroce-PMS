import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, FileText } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { API } from '../shared';

const ObservabilityTab = () => {
  const [metrics, setMetrics] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAudit, setShowAudit] = useState(false);
  const [trends, setTrends] = useState(null);
  const [period, setPeriod] = useState('7d');

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const [metricsRes, auditRes, trendsRes] = await Promise.all([
        axios.get(`${API}/admin/observability/metrics`),
        axios.get(`${API}/admin/observability/audit-trail?limit=50`),
        axios.get(`${API}/metrics/trends?period=${period}`),
      ]);
      setMetrics(metricsRes.data.metrics || []);
      setAudit(auditRes.data.logs || []);
      setTrends(trendsRes.data);
    } catch { /* silent */ }
    setLoading(false);
  }, [period]);

  useEffect(() => { fetchMetrics(); }, [fetchMetrics]);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;

  const trendData = trends?.trends || [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Operasyonel Gozlemlenebilirlik</h3>
        <div className="flex gap-2">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-24 bg-slate-800 border-slate-700 text-white text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="24h">24 Saat</SelectItem>
              <SelectItem value="7d">7 Gun</SelectItem>
              <SelectItem value="30d">30 Gun</SelectItem>
              <SelectItem value="90d">90 Gun</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" variant={showAudit ? 'default' : 'outline'}
            className={showAudit ? 'bg-blue-600' : 'border-slate-700 text-slate-300'} onClick={() => setShowAudit(!showAudit)}>
            <FileText className="w-3.5 h-3.5 mr-1" /> Audit Trail
          </Button>
          <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchMetrics}><RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile</Button>
        </div>
      </div>

      {/* Historical Trend Chart */}
      {trendData.length > 1 && !showAudit && (
        <Card className="bg-slate-800/50 border-slate-700">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-300">Tarihsel Trend ({period})</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-end gap-1 h-28">
              {trendData.map((t, i) => {
                const score = t.health_score || 0;
                const color = score >= 80 ? 'bg-emerald-500/70' : score >= 50 ? 'bg-amber-500/70' : 'bg-red-500/70';
                return (
                  <div key={i} className="flex-1 flex flex-col items-center gap-0.5" title={`${t.date}: ${score}`}>
                    <div className={`w-full ${color} rounded-t`} style={{height: `${score}%`}} />
                    <span className="text-[7px] text-slate-600 truncate w-full text-center">{t.date?.slice(5) || ''}</span>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-4 mt-2 text-[10px]">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-emerald-500" />Saglikli</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-amber-500" />Bozulmus</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-red-500" />Kritik</span>
            </div>
          </CardContent>
        </Card>
      )}

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
          {metrics.length === 0 && <Card className="bg-slate-800/50 border-slate-700"><CardContent className="py-12 text-center text-slate-400">Metrik bulunamadi</CardContent></Card>}
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

export default ObservabilityTab;
