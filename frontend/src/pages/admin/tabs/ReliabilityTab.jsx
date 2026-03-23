import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';
import { API, StatusDot, ScoreRing, MetricCard } from '../shared';

const ReliabilityTab = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try { const { data: d } = await axios.get(`${API}/reliability`); setData(d); } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  if (!data) return null;

  const classColors = { stable: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', healthy: 'bg-blue-500/15 text-blue-400 border-blue-500/30', degraded: 'bg-amber-500/15 text-amber-400 border-amber-500/30', unstable: 'bg-red-500/15 text-red-400 border-red-500/30' };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Connector Reliability Monitoring</h3>
        <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchData}><RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile</Button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard title="Ortalama Uptime" value={`${data.average_uptime}%`} icon={TrendingUp} color="text-emerald-400" />
        <MetricCard title="Stable" value={data.classifications?.stable || 0} icon={TrendingUp} color="text-emerald-400" />
        <MetricCard title="Degraded" value={data.classifications?.degraded || 0} icon={TrendingDown} color="text-amber-400" />
        <MetricCard title="Unstable" value={data.classifications?.unstable || 0} icon={AlertTriangle} color="text-red-400" />
      </div>

      <div className="space-y-3">
        {(data.connectors || []).map(c => (
          <Card key={c.connector_id} data-testid={`reliability-${c.connector_id}`} className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <ScoreRing score={Math.round(c.uptime_percentage)} size={50} />
                  <div>
                    <p className="text-sm font-medium text-white">{c.display_name}</p>
                    <p className="text-xs text-slate-500 flex items-center gap-1"><StatusDot status={c.classification} /> {c.provider}</p>
                  </div>
                </div>
                <Badge className={`border text-xs ${classColors[c.classification] || classColors.degraded}`}>{c.classification}</Badge>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                <div className="bg-slate-900/50 rounded p-2 text-center">
                  <p className="text-[10px] text-slate-500">Uptime</p>
                  <p className={`text-lg font-semibold ${c.uptime_percentage >= 90 ? 'text-emerald-400' : c.uptime_percentage >= 70 ? 'text-amber-400' : 'text-red-400'}`}>{c.uptime_percentage}%</p>
                </div>
                <div className="bg-slate-900/50 rounded p-2 text-center">
                  <p className="text-[10px] text-slate-500">MTBF</p>
                  <p className="text-lg font-semibold text-white">{c.mtbf_hours}h</p>
                </div>
                <div className="bg-slate-900/50 rounded p-2 text-center">
                  <p className="text-[10px] text-slate-500">MTTR</p>
                  <p className={`text-lg font-semibold ${c.mttr_hours > 4 ? 'text-red-400' : c.mttr_hours > 1 ? 'text-amber-400' : 'text-emerald-400'}`}>{c.mttr_hours}h</p>
                </div>
                <div className="bg-slate-900/50 rounded p-2 text-center">
                  <p className="text-[10px] text-slate-500">Sync Basari</p>
                  <p className={`text-lg font-semibold ${c.sync_success_rate >= 90 ? 'text-emerald-400' : 'text-amber-400'}`}>{c.sync_success_rate}%</p>
                </div>
                <div className="bg-slate-900/50 rounded p-2 text-center">
                  <p className="text-[10px] text-slate-500">ACK Basari</p>
                  <p className={`text-lg font-semibold ${c.ack_success_rate >= 90 ? 'text-emerald-400' : 'text-amber-400'}`}>{c.ack_success_rate}%</p>
                </div>
              </div>

              {c.failure_patterns?.length > 0 && (
                <div className="mt-3 space-y-1">
                  <p className="text-[10px] text-slate-500 font-medium">Hata Patternleri:</p>
                  {c.failure_patterns.map((p, i) => (
                    <div key={i} className="flex items-center gap-2 bg-slate-900/30 rounded p-1.5">
                      <Badge className={`border text-[9px] ${p.severity === 'critical' ? 'bg-red-500/15 text-red-400 border-red-500/30' : 'bg-amber-500/15 text-amber-400 border-amber-500/30'}`}>{p.pattern?.replace(/_/g,' ')}</Badge>
                      <span className="text-[10px] text-slate-400 truncate">{p.detail}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default ReliabilityTab;
