import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertTriangle, CheckCircle, RefreshCw, Loader2,
  Activity, Zap, XCircle, TrendingDown, Clock, Shield
} from 'lucide-react';

const API = "";

const WireFailureDashboard = ({ user, tenant, onLogout }) => {
  const [summary, setSummary] = useState(null);
  const [failures, setFailures] = useState([]);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [filterProvider, setFilterProvider] = useState('all');

  const headers = { Authorization: `Bearer ${user?.token || user?.access_token}` };

  const fetchSummary = useCallback(async () => {
    try {
      const { data } = await axios.get(`/channel-manager/wire-failures/summary?days=30`, { headers });
      setSummary(data);
    } catch { /* ignore */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const fetchFailures = useCallback(async () => {
    try {
      const { data } = await axios.get(`/channel-manager/wire-failures/recent?limit=100&provider=${filterProvider}`, { headers });
      setFailures(data.failures || []);
    } catch { /* ignore */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [filterProvider]);

  const fetchTrend = useCallback(async () => {
    try {
      const { data } = await axios.get(`/channel-manager/wire-failures/trend?days=30`, { headers });
      setTrend(data.trend || []);
    } catch { /* ignore */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const refreshAll = async () => {
    setLoading(true);
    await Promise.all([fetchSummary(), fetchFailures(), fetchTrend()]);
    setLoading(false);
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => { refreshAll(); }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => { fetchFailures(); }, [filterProvider]);

  const statusColor = summary?.health_status === 'healthy' ? 'text-emerald-600' : summary?.health_status === 'warning' ? 'text-amber-600' : 'text-red-600';
  const statusBg = summary?.health_status === 'healthy' ? 'bg-emerald-50 border-emerald-200' : summary?.health_status === 'warning' ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200';
  const statusIcon = summary?.health_status === 'healthy' ? <CheckCircle className="w-5 h-5" /> : summary?.health_status === 'warning' ? <AlertTriangle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />;
  const statusLabel = summary?.health_status === 'healthy' ? 'Saglikli' : summary?.health_status === 'warning' ? 'Uyarı' : 'Kritik';

  const maxTrend = Math.max(...trend.map(t => t.total), 1);

  const severityColor = (s) => s === 'high' ? 'text-red-700 bg-red-50' : s === 'medium' ? 'text-amber-700 bg-amber-50' : 'text-slate-700 bg-slate-50';

  return (
    <>
      <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto" data-testid="wire-failure-dashboard">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold" data-testid="wire-failure-title">Wire Failure Takibi</h1>
            <p className="text-sm text-slate-500 mt-1">Kanal yöneticisi hata ve başarısız işlem takibi</p>
          </div>
          <Button variant="outline" size="sm" onClick={refreshAll} disabled={loading} data-testid="wire-refresh-btn">
            {loading ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />}
            Yenile
          </Button>
        </div>

        {summary && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Health Status */}
            <Card className={`border ${statusBg}`} data-testid="wire-health-card">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <div className={statusColor}>{statusIcon}</div>
                  <div>
                    <p className="text-xs text-slate-500 uppercase">Genel Durum</p>
                    <p className={`text-lg font-bold ${statusColor}`}>{statusLabel}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Total Failures */}
            <Card data-testid="wire-total-card">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <Zap className="w-5 h-5 text-red-500" />
                  <div>
                    <p className="text-xs text-slate-500 uppercase">Toplam Hata</p>
                    <p className="text-lg font-bold">{summary.total_failures}</p>
                    <p className="text-xs text-slate-400">Son {summary.period_days} gun</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ARI Fails */}
            <Card data-testid="wire-ari-card">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <Activity className="w-5 h-5 text-amber-500" />
                  <div>
                    <p className="text-xs text-slate-500 uppercase">ARI Hard Fail</p>
                    <p className="text-lg font-bold">{summary.breakdown.ari_hard_fails}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Reconciliation */}
            <Card data-testid="wire-recon-card">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <Shield className="w-5 h-5 text-indigo-500" />
                  <div>
                    <p className="text-xs text-slate-500 uppercase">Açık Recon Sorunu</p>
                    <p className="text-lg font-bold">{summary.breakdown.reconciliation_issues}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Breakdown Cards */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(summary.breakdown).map(([key, value]) => (
              <div key={key} className="p-3 bg-slate-50 rounded-lg border text-center" data-testid={`wire-stat-${key}`}>
                <p className="text-xs text-slate-500 uppercase">{key.replace(/_/g, ' ')}</p>
                <p className={`text-xl font-bold mt-1 ${value > 0 ? 'text-red-600' : 'text-emerald-600'}`}>{value}</p>
              </div>
            ))}
          </div>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="overview" data-testid="wire-tab-overview">Trend</TabsTrigger>
            <TabsTrigger value="recent" data-testid="wire-tab-recent">Son Hatalar</TabsTrigger>
          </TabsList>

          {/* Trend Tab */}
          <TabsContent value="overview" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Günlük Hata Trendi (Son 30 Gun)</CardTitle>
              </CardHeader>
              <CardContent>
                {trend.length > 0 ? (
                  <div className="space-y-1" data-testid="wire-trend-chart">
                    {trend.slice(-14).map((day) => (
                      <div key={day.date} className="flex items-center gap-2 text-xs">
                        <span className="w-20 text-slate-500 font-mono">{day.date.slice(5)}</span>
                        <div className="flex-1 flex items-center gap-1">
                          <div className="h-5 bg-red-400 rounded-sm transition-all" style={{ width: `${Math.max((day.ari_fails / maxTrend) * 100, day.ari_fails > 0 ? 2 : 0)}%` }} title={`ARI: ${day.ari_fails}`} />
                          <div className="h-5 bg-amber-400 rounded-sm transition-all" style={{ width: `${Math.max((day.sync_fails / maxTrend) * 100, day.sync_fails > 0 ? 2 : 0)}%` }} title={`Sync: ${day.sync_fails}`} />
                        </div>
                        <span className="w-10 text-right font-mono text-slate-600">{day.total}</span>
                      </div>
                    ))}
                    <div className="flex items-center gap-4 mt-3 pt-2 border-t">
                      <div className="flex items-center gap-1 text-xs"><div className="w-3 h-3 bg-red-400 rounded-sm" /> ARI Hatalari</div>
                      <div className="flex items-center gap-1 text-xs"><div className="w-3 h-3 bg-amber-400 rounded-sm" /> Sync Hatalari</div>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500 text-center py-8">Trend verisi yükleniyor...</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Recent Failures Tab */}
          <TabsContent value="recent" className="mt-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-base">Son Hatalar</CardTitle>
                <div className="flex gap-1">
                  {['all', 'ari', 'exely', 'dlq', 'control_plane'].map(p => (
                    <Button
                      key={p}
                      size="sm"
                      variant={filterProvider === p ? 'default' : 'outline'}
                      onClick={() => setFilterProvider(p)}
                      data-testid={`wire-filter-${p}`}
                      className="text-xs h-7"
                    >
                      {p === 'all' ? 'Tumu' : p.replace('_', ' ').toUpperCase()}
                    </Button>
                  ))}
                </div>
              </CardHeader>
              <CardContent>
                {failures.length === 0 ? (
                  <div className="text-center py-8">
                    <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                    <p className="text-sm text-slate-500">Bu filtrede hata bulunamadı</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[500px] overflow-y-auto" data-testid="wire-failures-list">
                    {failures.map((f, i) => (
                      <div key={f.id || i} className={`flex items-start justify-between p-3 rounded-lg border ${severityColor(f.severity)}`} data-testid={`wire-failure-row-${i}`}>
                        <div className="flex items-start gap-3">
                          {f.severity === 'high' ? <XCircle className="w-4 h-4 mt-0.5 text-red-500 flex-shrink-0" /> : <AlertTriangle className="w-4 h-4 mt-0.5 text-amber-500 flex-shrink-0" />}
                          <div>
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0">{f.type.replace(/_/g, ' ')}</Badge>
                              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{f.provider}</Badge>
                            </div>
                            <p className="text-sm mt-1 font-medium">{f.message || 'Bilinmeyen hata'}</p>
                            {f.room_type && <p className="text-xs text-slate-500 mt-0.5">Oda tipi: {f.room_type}</p>}
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0 ml-4">
                          <p className="text-xs text-slate-500">{f.timestamp ? new Date(f.timestamp).toLocaleString('tr-TR') : '-'}</p>
                          {f.resolved && <Badge className="bg-emerald-100 text-emerald-700 text-[10px] mt-1">Çözüldü</Badge>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </>
  );
};

export default WireFailureDashboard;
