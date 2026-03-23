import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, Building2, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react';
import { API, ScoreRing, StatusDot, MetricCard } from '../shared';

const MultiPropertyTab = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('dashboard');

  const fetchDashboard = useCallback(async () => {
    setLoading(true);
    try { const { data: d } = await axios.get(`${API}/multi-property/dashboard`); setData(d); } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-slate-400" /></div>;
  if (!data) return null;

  const statusColors = { healthy: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', degraded: 'bg-amber-500/15 text-amber-400 border-amber-500/30', critical: 'bg-red-500/15 text-red-400 border-red-500/30' };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Multi-Property Integration Dashboard</h3>
        <div className="flex gap-2">
          <Button size="sm" variant={view === 'dashboard' ? 'default' : 'outline'} className={view === 'dashboard' ? 'bg-blue-600' : 'border-slate-700 text-slate-300'} onClick={() => setView('dashboard')}>Genel Bakis</Button>
          <Button size="sm" variant={view === 'comparison' ? 'default' : 'outline'} className={view === 'comparison' ? 'bg-blue-600' : 'border-slate-700 text-slate-300'} onClick={() => setView('comparison')}>Karsilastirma</Button>
          <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={fetchDashboard}><RefreshCw className="w-3.5 h-3.5 mr-1" /> Yenile</Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <MetricCard title="Toplam Property" value={data.total_properties} icon={Building2} color="text-blue-400" />
        <MetricCard title="Saglikli" value={data.healthy_properties} icon={TrendingUp} color="text-emerald-400" />
        <MetricCard title="Bozulmus" value={data.degraded_properties} icon={TrendingDown} color="text-amber-400" />
        <MetricCard title="Kritik" value={data.critical_properties} icon={AlertTriangle} color="text-red-400" />
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-4 flex items-center gap-3">
            <ScoreRing score={data.average_health_score} size={48} />
            <div>
              <p className="text-xs text-slate-400">Ort. Saglik</p>
              <p className="text-lg font-semibold text-white flex items-center gap-1"><StatusDot status={data.tenant_health_status} /> {data.average_health_score}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {view === 'dashboard' ? (
        <div className="space-y-3">
          {/* Provider Distribution */}
          {Object.keys(data.provider_distribution || {}).length > 0 && (
            <Card className="bg-slate-800/50 border-slate-700">
              <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-300">Provider Dagilimi</CardTitle></CardHeader>
              <CardContent>
                <div className="flex gap-4 flex-wrap">
                  {Object.entries(data.provider_distribution).map(([provider, count]) => (
                    <div key={provider} className="bg-slate-900/50 rounded px-3 py-2">
                      <p className="text-xs text-slate-400">{provider}</p>
                      <p className="text-lg font-semibold text-white">{count}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Top Failing */}
          {data.top_failing?.length > 0 && data.top_failing.some(f => f.failed_syncs > 0) && (
            <Card className="bg-slate-800/50 border-slate-700">
              <CardHeader className="pb-2"><CardTitle className="text-sm text-red-400">En Cok Hata Veren Property'ler</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {data.top_failing.filter(f => f.failed_syncs > 0).map((f, i) => (
                    <div key={i} className="flex items-center justify-between bg-slate-900/30 rounded p-2">
                      <span className="text-xs text-slate-300">{f.property_id?.slice(0,12)}...</span>
                      <span className="text-xs text-red-400">{f.failed_syncs} hata</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Property Cards */}
          {(data.properties || []).map(p => (
            <Card key={p.property_id} data-testid={`property-${p.property_id}`} className="bg-slate-800/50 border-slate-700">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <ScoreRing score={p.health_score} size={45} />
                    <div>
                      <p className="text-sm font-medium text-white">Property {p.property_id?.slice(0,8)}...</p>
                      <p className="text-xs text-slate-500">{p.connector_count} connector, {p.active_connectors} aktif</p>
                    </div>
                  </div>
                  <Badge className={`border text-xs ${statusColors[p.health_status] || statusColors.degraded}`}>{p.health_status}</Badge>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  <div className="bg-slate-900/50 rounded p-1.5 text-center"><p className="text-[9px] text-slate-500">Sync</p><p className="text-sm font-semibold text-white">{p.sync_success_rate}%</p></div>
                  <div className="bg-slate-900/50 rounded p-1.5 text-center"><p className="text-[9px] text-slate-500">ACK</p><p className="text-sm font-semibold text-white">{p.ack_success_rate}%</p></div>
                  <div className="bg-slate-900/50 rounded p-1.5 text-center"><p className="text-[9px] text-slate-500">Retry</p><p className="text-sm font-semibold text-orange-400">{p.retry_rate}%</p></div>
                  <div className="bg-slate-900/50 rounded p-1.5 text-center"><p className="text-[9px] text-slate-500">Issues</p><p className="text-sm font-semibold text-red-400">{p.open_issues}</p></div>
                  <div className="bg-slate-900/50 rounded p-1.5 text-center"><p className="text-[9px] text-slate-500">Failed</p><p className="text-sm font-semibold text-red-400">{p.failed_syncs}</p></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          <Card className="bg-slate-800/50 border-slate-700">
            <CardHeader className="pb-2"><CardTitle className="text-sm text-slate-300">Cross-Property Karsilastirmasi</CardTitle></CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-700">
                      <th className="text-left p-2">Property</th>
                      <th className="text-center p-2">Saglik</th>
                      <th className="text-center p-2">Connector</th>
                      <th className="text-center p-2">Sync %</th>
                      <th className="text-center p-2">ACK %</th>
                      <th className="text-center p-2">Retry %</th>
                      <th className="text-center p-2">Issues</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.properties || []).map(p => (
                      <tr key={p.property_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                        <td className="p-2 text-white">{p.property_id?.slice(0,10)}...</td>
                        <td className="p-2 text-center"><Badge className={`border text-[10px] ${statusColors[p.health_status] || ''}`}>{p.health_score}</Badge></td>
                        <td className="p-2 text-center text-slate-300">{p.connector_count}</td>
                        <td className={`p-2 text-center ${p.sync_success_rate >= 90 ? 'text-emerald-400' : 'text-amber-400'}`}>{p.sync_success_rate}%</td>
                        <td className={`p-2 text-center ${p.ack_success_rate >= 90 ? 'text-emerald-400' : 'text-amber-400'}`}>{p.ack_success_rate}%</td>
                        <td className={`p-2 text-center ${p.retry_rate <= 10 ? 'text-emerald-400' : 'text-orange-400'}`}>{p.retry_rate}%</td>
                        <td className={`p-2 text-center ${p.open_issues > 0 ? 'text-red-400' : 'text-slate-400'}`}>{p.open_issues}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

export default MultiPropertyTab;
