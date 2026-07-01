import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart3, RefreshCcw, CheckCircle2, XCircle, Clock, Zap } from 'lucide-react';

const API = "";

const RatePushMetricsTab = () => {
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState('');
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(false);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch(`/api/channel-manager/v2/connectors`, { credentials: "include", headers });
      if (res.ok) {
        const data = await res.json();
        const list = data.connectors || data || [];
        setConnectors(list);
        if (list.length > 0 && !selectedConnector) setSelectedConnector(list[0].id);
      }
    } catch (e) { console.error(e); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const fetchMetrics = useCallback(async () => {
    if (!selectedConnector) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/channel-manager/v2/rate-push-metrics/${selectedConnector}?days=30`, { credentials: "include", headers });
      if (res.ok) setMetrics(await res.json());
    } catch (e) { console.error(e); }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedConnector]);

  useEffect(() => { fetchConnectors(); }, [fetchConnectors]);
  useEffect(() => { if (selectedConnector) fetchMetrics(); }, [selectedConnector, fetchMetrics]);

  const fb = metrics?.failure_breakdown || {};

  return (
    <div data-testid="rate-push-metrics-tab" className="space-y-6">
      <div className="flex items-center gap-3">
        <select
          data-testid="rate-push-connector-select"
          value={selectedConnector}
          onChange={e => setSelectedConnector(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm"
        >
          {connectors.map(c => (
            <option key={c.id} value={c.id}>{c.display_name || c.id}</option>
          ))}
        </select>
        <button
          data-testid="refresh-rate-push-btn"
          onClick={fetchMetrics}
          className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition"
        >
          <RefreshCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {metrics && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="py-4">
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs text-slate-400">Success Rate</span>
                </div>
                <div className="text-2xl font-bold text-emerald-400">{metrics.rate_push_success_rate}%</div>
              </CardContent>
            </Card>
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="py-4">
                <div className="flex items-center gap-2 mb-1">
                  <XCircle className="w-4 h-4 text-red-400" />
                  <span className="text-xs text-slate-400">Failure Rate</span>
                </div>
                <div className="text-2xl font-bold text-red-400">{metrics.rate_push_failure_rate}%</div>
              </CardContent>
            </Card>
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="py-4">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className="w-4 h-4 text-amber-400" />
                  <span className="text-xs text-slate-400">Total Retries</span>
                </div>
                <div className="text-2xl font-bold text-amber-400">{metrics.rate_push_retry_count}</div>
              </CardContent>
            </Card>
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="py-4">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-4 h-4 text-blue-400" />
                  <span className="text-xs text-slate-400">Avg Latency</span>
                </div>
                <div className="text-2xl font-bold text-blue-400">{metrics.avg_latency_ms}ms</div>
              </CardContent>
            </Card>
          </div>

          {/* Summary */}
          <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
                <BarChart3 className="w-4 h-4" /> Rate Push Summary
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Total Pushes</span>
                    <span className="text-white font-medium">{metrics.total_pushes}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Success</span>
                    <span className="text-emerald-400 font-medium">{metrics.success_count}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Failed</span>
                    <span className="text-red-400 font-medium">{metrics.failure_count}</span>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Last Success</span>
                    <span className="text-white text-xs">{metrics.last_success_at ? new Date(metrics.last_success_at).toLocaleString('tr-TR') : '-'}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-400">Last Failure</span>
                    <span className="text-white text-xs">{metrics.last_failure_at ? new Date(metrics.last_failure_at).toLocaleString('tr-TR') : '-'}</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Failure Breakdown */}
          {Object.keys(fb).length > 0 && (
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-slate-300">Failure Classification</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(fb).map(([cls, count]) => (
                    <div key={cls} className="flex items-center gap-3">
                      <div className="flex-1">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-slate-300 capitalize">{cls.replace('_', ' ')}</span>
                          <span className="text-slate-400">{count}</span>
                        </div>
                        <div className="w-full bg-slate-700 rounded-full h-1.5">
                          <div
                            className="bg-red-500 h-1.5 rounded-full"
                            style={{ width: `${(count / Math.max(metrics.failure_count, 1)) * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
};

export default RatePushMetricsTab;
