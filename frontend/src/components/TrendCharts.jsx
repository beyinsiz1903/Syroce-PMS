import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Activity, Zap, Shield, Layers, RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react';

const API = "";

const MiniBarChart = ({ data, maxVal, color = '#22d3ee', height = 48 }) => {
  if (!data || data.length === 0) return <div className="text-xs text-gray-500 dark:text-slate-400">No data</div>;
  const max = maxVal || Math.max(...data, 1);
  const barW = Math.max(2, Math.min(8, Math.floor(200 / data.length)));
  const gap = 1;

  return (
    <div className="flex items-end gap-px" style={{ height }}>
      {data.map((v, i) => (
        <div key={i} style={{
          width: barW,
          height: Math.max(1, (v / max) * height),
          backgroundColor: color,
          opacity: 0.7 + (i / data.length) * 0.3,
          borderRadius: '1px 1px 0 0',
        }} />
      ))}
    </div>
  );
};

const TrendIndicator = ({ data }) => {
  if (!data || data.length < 2) return <Minus className="w-3 h-3 text-gray-500 dark:text-slate-400" />;
  const recent = data.slice(-5).reduce((a, b) => a + b, 0) / Math.min(5, data.length);
  const older = data.slice(0, 5).reduce((a, b) => a + b, 0) / Math.min(5, data.length);
  if (recent > older * 1.1) return <TrendingUp className="w-3 h-3 text-emerald-600" />;
  if (recent < older * 0.9) return <TrendingDown className="w-3 h-3 text-red-600" />;
  return <Minus className="w-3 h-3 text-gray-500 dark:text-slate-400" />;
};

export const TrendCharts = ({ headers }) => {
  const [trends, setTrends] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hours, setHours] = useState(24);

  const fetchTrends = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`/channel-manager/monitoring/trends?hours=${hours}`, { headers: headers() });
      setTrends(data);
    } catch (e) { console.error('Trends fetch failed:', e); }
    setLoading(false);
  }, [headers, hours]);

  useEffect(() => { fetchTrends(); }, [fetchTrends]);

  if (!trends) {
    return (
      <Card className="bg-white/60 border-gray-200 dark:bg-card/60 dark:border-slate-700">
        <CardContent className="p-6 text-center text-gray-500 text-sm dark:text-slate-400">
          {loading ? 'Loading trend data...' : 'No trend data available yet. Metrics are collected every 60 seconds.'}
        </CardContent>
      </Card>
    );
  }

  const ingestEvents = trends.ingest?.map(d => d.events_1h) || [];
  const ingestFailed = trends.ingest?.map(d => d.failed) || [];
  const ingestDupes = trends.ingest?.map(d => d.duplicates) || [];
  const ariSuccess = trends.ari?.map(d => d.success_rate) || [];
  const ariLatency = trends.ari?.map(d => d.p95_latency) || [];
  const ariRetry = trends.ari?.map(d => d.retry_count) || [];
  const reconOpen = trends.reconciliation?.map(d => d.open_cases) || [];
  const reconCrit = trends.reconciliation?.map(d => d.critical) || [];
  const queueDepth = trends.queue?.map(d => d.depth) || [];
  const queueRetry = trends.queue?.map(d => d.retry_backlog) || [];

  const latest = (arr) => arr.length > 0 ? arr[arr.length - 1] : 0;

  return (
    <Card data-testid="trend-charts-panel" className="bg-white/60 border-gray-200 dark:bg-card/60 dark:border-slate-700">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-gray-700 dark:text-slate-200 flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" /> Trend Charts — Last {hours}h
            <Badge className="bg-gray-100 text-gray-600 border-gray-300 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700 text-xs border ml-2">
              {trends.data_points} data points
            </Badge>
          </CardTitle>
          <div className="flex items-center gap-2">
            {[6, 12, 24, 48].map(h => (
              <button key={h} data-testid={`trend-hours-${h}`}
                onClick={() => setHours(h)}
                className={`px-2 py-0.5 text-xs rounded ${hours === h ? 'bg-cyan-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'}`}>
                {h}h
              </button>
            ))}
            <Button variant="ghost" size="sm" onClick={fetchTrends} disabled={loading} className="text-gray-600 hover:text-gray-900 dark:text-slate-300 dark:hover:text-white h-7 px-2">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {/* Ingest Pipeline */}
          <div data-testid="trend-ingest" className="p-4 bg-gray-50/50 rounded-lg border border-gray-200/50 dark:bg-slate-800/50 dark:border-slate-700/50">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-3.5 h-3.5 text-blue-600" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300">Ingest Pipeline</span>
            </div>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Events / Hour</span>
                  <div className="flex items-center gap-1">
                    <TrendIndicator data={ingestEvents} />
                    <span className="text-xs font-mono text-gray-700 dark:text-slate-200">{latest(ingestEvents)}</span>
                  </div>
                </div>
                <MiniBarChart data={ingestEvents} color="#3b82f6" />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Failed Ingest</span>
                  <span className="text-xs font-mono text-red-600">{latest(ingestFailed)}</span>
                </div>
                <MiniBarChart data={ingestFailed} color="#ef4444" height={32} />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Duplicate Rate</span>
                  <span className="text-xs font-mono text-amber-600">{latest(ingestDupes)}</span>
                </div>
                <MiniBarChart data={ingestDupes} color="#f59e0b" height={32} />
              </div>
            </div>
          </div>

          {/* ARI Push */}
          <div data-testid="trend-ari" className="p-4 bg-gray-50/50 rounded-lg border border-gray-200/50 dark:bg-slate-800/50 dark:border-slate-700/50">
            <div className="flex items-center gap-2 mb-3">
              <Zap className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300">ARI Push</span>
            </div>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Success Rate %</span>
                  <div className="flex items-center gap-1">
                    <TrendIndicator data={ariSuccess} />
                    <span className="text-xs font-mono text-emerald-600">{latest(ariSuccess).toFixed(1)}%</span>
                  </div>
                </div>
                <MiniBarChart data={ariSuccess} maxVal={100} color="#10b981" />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">P95 Latency (ms)</span>
                  <span className="text-xs font-mono text-cyan-400">{latest(ariLatency)}</span>
                </div>
                <MiniBarChart data={ariLatency} color="#22d3ee" height={32} />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Retry Count</span>
                  <span className="text-xs font-mono text-amber-600">{latest(ariRetry)}</span>
                </div>
                <MiniBarChart data={ariRetry} color="#f59e0b" height={32} />
              </div>
            </div>
          </div>

          {/* Reconciliation */}
          <div data-testid="trend-recon" className="p-4 bg-gray-50/50 rounded-lg border border-gray-200/50 dark:bg-slate-800/50 dark:border-slate-700/50">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-3.5 h-3.5 text-violet-400" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300">Reconciliation</span>
            </div>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Open Cases</span>
                  <div className="flex items-center gap-1">
                    <TrendIndicator data={reconOpen} />
                    <span className="text-xs font-mono text-gray-700 dark:text-slate-200">{latest(reconOpen)}</span>
                  </div>
                </div>
                <MiniBarChart data={reconOpen} color="#8b5cf6" />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Critical Cases</span>
                  <span className="text-xs font-mono text-red-600">{latest(reconCrit)}</span>
                </div>
                <MiniBarChart data={reconCrit} color="#ef4444" height={32} />
              </div>
            </div>
          </div>

          {/* Queue Health */}
          <div data-testid="trend-queue" className="p-4 bg-gray-50/50 rounded-lg border border-gray-200/50 dark:bg-slate-800/50 dark:border-slate-700/50">
            <div className="flex items-center gap-2 mb-3">
              <Layers className="w-3.5 h-3.5 text-amber-600" />
              <span className="text-xs font-medium text-gray-600 dark:text-slate-300">Queue & Workers</span>
            </div>
            <div className="space-y-3">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Queue Depth</span>
                  <div className="flex items-center gap-1">
                    <TrendIndicator data={queueDepth} />
                    <span className="text-xs font-mono text-gray-700 dark:text-slate-200">{latest(queueDepth)}</span>
                  </div>
                </div>
                <MiniBarChart data={queueDepth} color="#f97316" />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-500 dark:text-slate-400">Retry Backlog</span>
                  <span className="text-xs font-mono text-amber-600">{latest(queueRetry)}</span>
                </div>
                <MiniBarChart data={queueRetry} color="#f59e0b" height={32} />
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
