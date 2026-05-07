import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TrendingUp, TrendingDown, Minus, Activity, AlertTriangle, RefreshCcw, BarChart3 } from 'lucide-react';

const API = "";

const MetricCard = ({ label, current, previous, delta, trend, suffix = '%' }) => {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-slate-400';
  return (
    <div data-testid={`metric-${label.toLowerCase().replace(/\s/g, '-')}`} className="bg-slate-800/60 rounded-lg p-4 border border-slate-700/50">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold text-white">{current}{suffix}</span>
        {delta !== undefined && (
          <span className={`flex items-center gap-0.5 text-xs ${trendColor}`}>
            <TrendIcon className="w-3 h-3" />
            {delta > 0 ? '+' : ''}{delta}{suffix}
          </span>
        )}
      </div>
      {previous !== undefined && (
        <div className="text-xs text-slate-500 mt-1">Previous: {previous}{suffix}</div>
      )}
    </div>
  );
};

const TrendChart = ({ data, metricKey, label, color = '#3b82f6' }) => {
  if (!data || data.length === 0) return <div className="text-slate-500 text-sm py-8 text-center">No trend data available</div>;

  const values = data.map(d => d[metricKey] || 0);
  const maxVal = Math.max(...values, 1);
  const minVal = Math.min(...values, 0);
  const range = maxVal - minVal || 1;

  return (
    <div data-testid={`trend-chart-${metricKey}`} className="relative">
      <div className="text-xs text-slate-400 mb-2">{label}</div>
      <div className="flex items-end gap-[2px] h-24">
        {data.map((d, i) => {
          const val = d[metricKey] || 0;
          const height = Math.max(((val - minVal) / range) * 100, 4);
          return (
            <div key={i} className="flex-1 group relative">
              <div
                className="rounded-t transition-all duration-200 group-hover:opacity-80"
                style={{ height: `${height}%`, backgroundColor: color, minHeight: '2px' }}
              />
              <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 bg-slate-900 text-xs text-white px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap z-10 pointer-events-none">
                {d.date}: {val.toFixed(1)}
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between text-[10px] text-slate-600 mt-1">
        <span>{data[0]?.date}</span>
        <span>{data[data.length - 1]?.date}</span>
      </div>
    </div>
  );
};

const HealthTrendTab = () => {
  const [connectors, setConnectors] = useState([]);
  const [selectedConnector, setSelectedConnector] = useState('');
  const [dailyTrend, setDailyTrend] = useState([]);
  const [weeklyTrend, setWeeklyTrend] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchConnectors = useCallback(async () => {
    try {
      const res = await fetch(`/api/channel-manager/v2/connectors`, { headers });
      if (res.ok) {
        const data = await res.json();
        const list = data.connectors || data || [];
        setConnectors(list);
        if (list.length > 0 && !selectedConnector) setSelectedConnector(list[0].id);
      }
    } catch (e) { console.error(e); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const fetchTrends = useCallback(async () => {
    if (!selectedConnector) return;
    setLoading(true);
    try {
      const [dailyRes, weeklyRes, summaryRes] = await Promise.all([
        fetch(`/api/channel-manager/v2/health-trend/${selectedConnector}/daily?days=30`, { headers }),
        fetch(`/api/channel-manager/v2/health-trend/${selectedConnector}/weekly?weeks=12`, { headers }),
        fetch(`/api/channel-manager/v2/health-trend/${selectedConnector}/summary`, { headers }),
      ]);
      if (dailyRes.ok) setDailyTrend(await dailyRes.json());
      if (weeklyRes.ok) setWeeklyTrend(await weeklyRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
    } catch (e) { console.error(e); }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedConnector]);

  useEffect(() => { fetchConnectors(); }, [fetchConnectors]);
  useEffect(() => { if (selectedConnector) fetchTrends(); }, [selectedConnector, fetchTrends]);

  return (
    <div data-testid="health-trend-tab" className="space-y-6">
      {/* Connector Selector */}
      <div className="flex items-center gap-3">
        <select
          data-testid="trend-connector-select"
          value={selectedConnector}
          onChange={e => setSelectedConnector(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2 text-sm"
        >
          {connectors.map(c => (
            <option key={c.id} value={c.id}>{c.display_name || c.id}</option>
          ))}
        </select>
        <button
          data-testid="refresh-trends-btn"
          onClick={fetchTrends}
          className="flex items-center gap-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-sm transition"
        >
          <RefreshCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Trend Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MetricCard
            label="Health Score"
            current={summary.health_score?.current || 0}
            previous={summary.health_score?.previous || 0}
            delta={summary.health_score?.delta || 0}
            trend={summary.health_score?.trend || 'stable'}
          />
          <MetricCard
            label="Sync Success"
            current={summary.sync_success_rate?.current || 0}
            previous={summary.sync_success_rate?.previous || 0}
            delta={summary.sync_success_rate?.delta || 0}
            trend={summary.sync_success_rate?.delta > 0 ? 'up' : summary.sync_success_rate?.delta < 0 ? 'down' : 'stable'}
          />
          <MetricCard
            label="Import Success"
            current={summary.import_success_rate?.current || 0}
            previous={summary.import_success_rate?.previous || 0}
            delta={summary.import_success_rate?.delta || 0}
            trend={summary.import_success_rate?.delta > 0 ? 'up' : summary.import_success_rate?.delta < 0 ? 'down' : 'stable'}
          />
          <MetricCard
            label="Alerts"
            current={summary.alert_frequency?.current || 0}
            previous={summary.alert_frequency?.previous || 0}
            suffix=""
            trend={summary.alert_frequency?.current < summary.alert_frequency?.previous ? 'up' : 'down'}
          />
          <MetricCard
            label="Retries"
            current={summary.retry_frequency?.current || 0}
            previous={summary.retry_frequency?.previous || 0}
            suffix=""
            trend={summary.retry_frequency?.current < summary.retry_frequency?.previous ? 'up' : 'down'}
          />
        </div>
      )}

      {/* Daily Trend Charts */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
            <BarChart3 className="w-4 h-4" /> Daily Trends (Last 30 Days)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <TrendChart data={dailyTrend} metricKey="health_score" label="Health Score" color="#3b82f6" />
            <TrendChart data={dailyTrend} metricKey="sync_success_rate" label="Sync Success Rate" color="#10b981" />
            <TrendChart data={dailyTrend} metricKey="import_success_rate" label="Import Success Rate" color="#8b5cf6" />
            <TrendChart data={dailyTrend} metricKey="alert_count" label="Alert Count" color="#f59e0b" />
          </div>
        </CardContent>
      </Card>

      {/* Weekly Trend */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-slate-300 flex items-center gap-2">
            <Activity className="w-4 h-4" /> Weekly Trends (Last 12 Weeks)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <TrendChart data={weeklyTrend} metricKey="health_score" label="Health Score" color="#3b82f6" />
            <TrendChart data={weeklyTrend} metricKey="sync_success_rate" label="Sync Success Rate" color="#10b981" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default HealthTrendTab;
