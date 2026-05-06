import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import {
  TrendingUp, TrendingDown, Hotel, CalendarDays,
  Ban, Zap, ArrowUpRight, ArrowDownRight, Minus,
  RefreshCw, Loader2, AlertTriangle, Info, FlaskConical
} from 'lucide-react';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Title, Tooltip, Legend, Filler,
);

function fmt(val) {
  if (val == null) return '0';
  return Number(val).toLocaleString('tr-TR');
}

function DeltaBadge({ current, previous }) {
  if (!previous || previous === 0) return null;
  const pct = ((current - previous) / previous * 100).toFixed(1);
  const up = pct > 0;
  return (
    <span data-testid="delta-badge" className={`inline-flex items-center text-xs font-medium ${up ? 'text-emerald-600' : 'text-red-500'}`}>
      {up ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
      {up ? '+' : ''}{pct}%
    </span>
  );
}

// Map backend data_quality.warnings to translated CTA lines.
function buildDQLines(t, dq) {
  if (!dq) return [];
  const w = dq.warnings || [];
  const out = [];
  if (w.includes('no_rooms')) out.push({ key: 'no_rooms', text: t('rmsModule.dq_no_rooms') });
  if (w.includes('no_room_types')) out.push({ key: 'no_room_types', text: t('rmsModule.dq_no_room_types') });
  if (w.includes('no_bookings_in_period')) out.push({ key: 'no_bookings', text: t('rmsModule.dq_no_bookings') });
  if (w.includes('insufficient_history_for_pricing')) {
    out.push({
      key: 'history',
      text: t('rmsModule.dq_insufficient_history', {
        days: dq.thresholds?.min_history_days_for_pricing ?? 14,
      }),
    });
  }
  if (w.includes('insufficient_bookings_for_pricing') && !w.includes('no_bookings_in_period')) {
    out.push({
      key: 'bookings',
      text: t('rmsModule.dq_insufficient_pricing', {
        count: dq.thresholds?.min_bookings_for_pricing ?? 10,
      }),
    });
  }
  if (w.includes('no_yield_rules')) out.push({ key: 'yield', text: t('rmsModule.dq_no_yield_rules') });
  if (w.includes('no_seasons')) out.push({ key: 'seasons', text: t('rmsModule.dq_no_seasons') });
  return out;
}

function ChartEmpty({ label }) {
  return (
    <div className="h-full w-full flex flex-col items-center justify-center gap-2 text-slate-400">
      <Info className="w-6 h-6 opacity-60" />
      <p className="text-xs">{label}</p>
    </div>
  );
}

const RMSModule = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const [kpis, setKpis] = useState(null);
  const [channels, setChannels] = useState([]);
  const [dailyTrend, setDailyTrend] = useState([]);
  const [roomTypePerf, setRoomTypePerf] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [dataQuality, setDataQuality] = useState(null);
  const [demoMode, setDemoMode] = useState(false);
  const [demoToggling, setDemoToggling] = useState(false);
  const [loading, setLoading] = useState(true);
  const [genLoading, setGenLoading] = useState(false);
  const [period, setPeriod] = useState('30');

  // Demo mode toggle is super_admin-only per product spec.
  const canToggleDemoMode = user?.role === 'super_admin';

  const wrap = (content) => embedded ? content : (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rms">{content}</Layout>
  );

  const loadData = useCallback(async () => {
    try {
      const [dashRes, recRes, settingsRes] = await Promise.all([
        axios.get(`/rms/dashboard-kpis?period=${period}`),
        axios.get('/rms/pricing-recommendations?status=pending'),
        axios.get('/rms/settings').catch(() => null),
      ]);
      const d = dashRes.data;
      setKpis(d.kpis);
      setChannels(d.channels || []);
      setDailyTrend(d.daily_trend || []);
      setRoomTypePerf(d.room_type_performance || []);
      setDataQuality(d.data_quality || null);
      setRecommendations(recRes.data.recommendations || []);
      // Trust settings endpoint when reachable; otherwise fall back to the
      // demo_mode bit baked into the dashboard payload so the toggle and
      // banner stay consistent if /rms/settings transiently fails.
      const dmFromSettings = settingsRes?.data?.rms_demo_mode;
      const dmFromDash = d.data_quality?.demo_mode;
      setDemoMode(typeof dmFromSettings === 'boolean' ? dmFromSettings : !!dmFromDash);
    } catch (e) {
      console.error('RMS data load error:', e);
      toast.error(t('rmsModule.load_failed'));
    } finally {
      setLoading(false);
    }
  }, [period, t]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleToggleDemoMode = async (next) => {
    setDemoToggling(true);
    try {
      await axios.patch('/rms/settings', { rms_demo_mode: next });
      setDemoMode(next);
      setLoading(true);
      loadData();
    } catch (e) {
      toast.error(t('common.error') || 'Error');
    } finally {
      setDemoToggling(false);
    }
  };

  const handleGeneratePricing = async () => {
    setGenLoading(true);
    try {
      const today = new Date();
      const start = today.toISOString().split('T')[0];
      const end = new Date(today.getTime() + 30 * 86400000).toISOString().split('T')[0];
      const res = await axios.post('/rms/generate-pricing', { start_date: start, end_date: end });
      toast.success(t('rmsModule.generate_success', { count: res.data.summary?.total || 0 }));
      loadData();
    } catch (e) {
      // Backend returns structured 422 with detail.error / detail.message when
      // data is insufficient. Surface that to the user instead of a generic toast.
      const detail = e?.response?.data?.detail;
      if (detail && detail.error === 'insufficient_data_for_pricing') {
        toast.error(t('rmsModule.generate_error_insufficient'));
      } else if (detail && detail.message) {
        toast.error(detail.message);
      } else {
        toast.error(t('rmsModule.generate_failed'));
      }
    } finally {
      setGenLoading(false);
    }
  };

  const handleApplyAll = async () => {
    try {
      const res = await axios.post('/rms/apply-recommendations');
      toast.success(res.data.message || t('rmsModule.apply_success'));
      loadData();
    } catch (e) {
      toast.error(t('rmsModule.apply_failed'));
    }
  };

  if (loading) {
    return wrap(
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  const k = kpis || {};
  const dq = dataQuality;
  const dqLines = buildDQLines(t, dq);
  // Banner shown only when *meaningful* gaps exist (not just missing yield
  // rules / seasons which both have working defaults).
  const blockingWarnings = (dq?.warnings || []).filter(
    (w) => w !== 'no_yield_rules' && w !== 'no_seasons'
  );
  const showQualityBanner = !!dq && blockingWarnings.length > 0 && !demoMode;

  const canGenerate = !!dq && (dq.sufficient_for_pricing || demoMode);
  const hasBookings = !!dq?.has_bookings;

  // Chart: Daily Occupancy Trend
  const trendData = {
    labels: dailyTrend.map(d => {
      const dt = new Date(d.date);
      return `${dt.getDate()}/${dt.getMonth() + 1}`;
    }),
    datasets: [{
      label: t('rmsModule.kpi_occupancy'),
      data: dailyTrend.map(d => d.occupancy),
      borderColor: '#0ea5e9',
      backgroundColor: 'rgba(14,165,233,0.08)',
      tension: 0.35,
      fill: true,
      pointRadius: 2,
      pointHoverRadius: 5,
    }],
  };

  // Chart: Channel Revenue Distribution
  const channelColors = ['#0ea5e9', '#f59e0b', '#10b981', '#8b5cf6', '#ef4444', '#64748b'];
  const channelData = {
    labels: channels.map(c => c.label),
    datasets: [{
      data: channels.map(c => c.revenue),
      backgroundColor: channelColors.slice(0, channels.length),
      borderWidth: 0,
    }],
  };

  // Chart: Room Type Revenue
  const rtData = {
    labels: roomTypePerf.map(r => r.room_type),
    datasets: [{
      label: 'Gelir (TRY)',
      data: roomTypePerf.map(r => r.revenue),
      backgroundColor: 'rgba(14,165,233,0.7)',
      borderRadius: 4,
    }, {
      label: 'Rez. Sayısı',
      data: roomTypePerf.map(r => r.count),
      backgroundColor: 'rgba(245,158,11,0.7)',
      borderRadius: 4,
      yAxisID: 'y1',
    }],
  };

  // Show "—" instead of misleading 0 when there's literally no data.
  const dash = '—';
  const occVal = hasBookings ? `%${k.occupancy || 0}` : dash;
  const adrVal = hasBookings ? `${fmt(k.adr)}` : dash;
  const revparVal = hasBookings ? `${fmt(k.revpar)}` : dash;
  const cancelVal = hasBookings ? `%${k.cancel_rate || 0}` : dash;

  return wrap(
    <div data-testid="rms-dashboard" className="space-y-6 p-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-slate-800">{t('rmsModule.title')}</h2>
          <p className="text-sm text-slate-500">{t('rmsModule.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {canToggleDemoMode && (
            <div
              className="flex items-center gap-2 text-xs bg-slate-50 border border-slate-200 rounded-md px-2 py-1"
              title={t('rmsModule.demo_mode_tooltip')}
              data-testid="demo-mode-toggle-wrap"
            >
              <FlaskConical className={`w-3.5 h-3.5 ${demoMode ? 'text-amber-500' : 'text-slate-400'}`} />
              <span className="text-slate-600">{t('rmsModule.demo_mode_label')}</span>
              <Switch
                checked={demoMode}
                disabled={demoToggling}
                onCheckedChange={handleToggleDemoMode}
                data-testid="demo-mode-toggle"
              />
            </div>
          )}
          <select
            data-testid="period-select"
            value={period}
            onChange={e => { setPeriod(e.target.value); setLoading(true); }}
            className="text-sm border rounded-md px-2 py-1.5 bg-white"
          >
            <option value="7">{t('rmsModule.period_7d')}</option>
            <option value="30">{t('rmsModule.period_30d')}</option>
            <option value="90">{t('rmsModule.period_90d')}</option>
          </select>
          <Button size="sm" variant="outline" onClick={() => { setLoading(true); loadData(); }} data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Demo mode active banner */}
      {demoMode && (
        <div
          className="flex items-start gap-2 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-3 py-2 text-sm"
          data-testid="demo-mode-banner"
        >
          <FlaskConical className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <span>{t('rmsModule.demo_mode_on')}</span>
        </div>
      )}

      {/* Data quality banner */}
      {showQualityBanner && (
        <div
          className="flex items-start gap-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-md px-4 py-3"
          data-testid="data-quality-banner"
        >
          <AlertTriangle className="w-5 h-5 mt-0.5 flex-shrink-0 text-amber-500" />
          <div className="flex-1 text-sm">
            <p className="font-semibold mb-1">{t('rmsModule.data_quality_banner_title')}</p>
            <p className="text-amber-800/80 mb-2">{t('rmsModule.data_quality_banner_desc')}</p>
            <ul className="list-disc pl-5 space-y-0.5">
              {dqLines.map(line => (
                <li key={line.key}>{line.text}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card className="bg-gradient-to-br from-sky-50 to-white border-sky-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-sky-600 uppercase tracking-wide">{t('rmsModule.kpi_occupancy')}</span>
              <Hotel className="w-4 h-4 text-sky-400" />
            </div>
            <p data-testid="kpi-occupancy" className="text-2xl font-bold text-slate-800" title={!hasBookings ? t('rmsModule.kpi_no_data') : undefined}>{occVal}</p>
            {hasBookings && <DeltaBadge current={k.occupancy} previous={k.occupancy_prev} />}
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-emerald-50 to-white border-emerald-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-emerald-600 uppercase tracking-wide">{t('rmsModule.kpi_adr')}</span>
              <TrendingUp className="w-4 h-4 text-emerald-400" />
            </div>
            <p data-testid="kpi-adr" className="text-2xl font-bold text-slate-800" title={!hasBookings ? t('rmsModule.kpi_no_data') : undefined}>
              {adrVal}{hasBookings && <span className="text-sm font-normal"> TRY</span>}
            </p>
            {hasBookings && <DeltaBadge current={k.adr} previous={k.adr_prev} />}
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-violet-50 to-white border-violet-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-violet-600 uppercase tracking-wide">{t('rmsModule.kpi_revpar')}</span>
              <Zap className="w-4 h-4 text-violet-400" />
            </div>
            <p data-testid="kpi-revpar" className="text-2xl font-bold text-slate-800" title={!hasBookings ? t('rmsModule.kpi_no_data') : undefined}>
              {revparVal}{hasBookings && <span className="text-sm font-normal"> TRY</span>}
            </p>
            {hasBookings && <DeltaBadge current={k.revpar} previous={k.revpar_prev} />}
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-amber-50 to-white border-amber-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-amber-600 uppercase tracking-wide">{t('rmsModule.kpi_pickup')}</span>
              <CalendarDays className="w-4 h-4 text-amber-400" />
            </div>
            <p data-testid="kpi-pickup" className="text-2xl font-bold text-slate-800">
              {k.pickup_rate || 0}<span className="text-sm font-normal">{t('rmsModule.kpi_pickup_unit')}</span>
            </p>
            <span className="text-xs text-slate-500">{t('rmsModule.kpi_pickup_sub', { count: k.pickup_count_7d || 0 })}</span>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-red-50 to-white border-red-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-red-600 uppercase tracking-wide">{t('rmsModule.kpi_cancel')}</span>
              <Ban className="w-4 h-4 text-red-400" />
            </div>
            <p data-testid="kpi-cancel" className="text-2xl font-bold text-slate-800" title={!hasBookings ? t('rmsModule.kpi_no_data') : undefined}>{cancelVal}</p>
            <span className="text-xs text-slate-500">{t('rmsModule.kpi_total_revenue', { amount: fmt(k.total_revenue) })}</span>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Occupancy Trend */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-600">{t('rmsModule.chart_occupancy_trend')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div data-testid="occupancy-chart" className="h-56">
              {hasBookings ? (
                <Line data={trendData} options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { display: false } },
                  scales: {
                    y: { beginAtZero: true, max: 100, ticks: { callback: v => `${v}%` } },
                    x: { grid: { display: false } },
                  },
                }} />
              ) : (
                <ChartEmpty label={t('rmsModule.no_data')} />
              )}
            </div>
          </CardContent>
        </Card>

        {/* Channel Distribution */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-600">{t('rmsModule.chart_channel_dist')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div data-testid="channel-chart" className="h-44 flex items-center justify-center">
              {channels.length > 0 ? (
                <Doughnut data={channelData} options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
                  cutout: '60%',
                }} />
              ) : (
                <ChartEmpty label={t('rmsModule.no_data')} />
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Room Type Performance */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-slate-600">{t('rmsModule.chart_room_type_perf')}</CardTitle>
        </CardHeader>
        <CardContent>
          <div data-testid="roomtype-chart" className="h-52">
            {roomTypePerf.length > 0 ? (
              <Bar data={rtData} options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top', labels: { boxWidth: 10, font: { size: 11 } } } },
                scales: {
                  y: { beginAtZero: true, position: 'left', ticks: { callback: v => `${(v / 1000).toFixed(0)}K` } },
                  y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false } },
                  x: { grid: { display: false } },
                },
              }} />
            ) : (
              <ChartEmpty label={t('rmsModule.no_data')} />
            )}
          </div>
        </CardContent>
      </Card>

      {/* Pricing Recommendations */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-slate-600">
            {t('rmsModule.rec_title')}
            {recommendations.length > 0 && (
              <Badge variant="secondary" className="ml-2">{t('rmsModule.rec_pending', { count: recommendations.length })}</Badge>
            )}
          </CardTitle>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={handleGeneratePricing}
              disabled={genLoading || !canGenerate}
              data-testid="generate-pricing-btn"
              title={!canGenerate ? t('rmsModule.generate_disabled_tooltip') : undefined}
            >
              {genLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Zap className="w-4 h-4 mr-1" />}
              {t('rmsModule.rec_generate')}
            </Button>
            {recommendations.length > 0 && (
              <Button size="sm" onClick={handleApplyAll} data-testid="apply-all-btn">
                {t('rmsModule.rec_apply_all', { count: recommendations.length })}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {recommendations.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-6">{t('rmsModule.rec_empty')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="recommendations-table">
                <thead>
                  <tr className="border-b text-left text-slate-500">
                    <th className="pb-2 font-medium">{t('rmsModule.rec_col_date')}</th>
                    <th className="pb-2 font-medium">{t('rmsModule.rec_col_room_type')}</th>
                    <th className="pb-2 font-medium">{t('rmsModule.rec_col_current')}</th>
                    <th className="pb-2 font-medium">{t('rmsModule.rec_col_suggested')}</th>
                    <th className="pb-2 font-medium">{t('rmsModule.rec_col_change')}</th>
                    <th className="pb-2 font-medium">{t('rmsModule.rec_col_occupancy')}</th>
                    <th className="pb-2 font-medium">{t('rmsModule.rec_col_confidence')}</th>
                  </tr>
                </thead>
                <tbody>
                  {recommendations.slice(0, 15).map(r => {
                    const up = r.change_pct > 0;
                    const down = r.change_pct < 0;
                    return (
                      <tr key={r.id} className="border-b last:border-0 hover:bg-slate-50/50">
                        <td className="py-2">{r.date}</td>
                        <td className="py-2">{r.room_type}</td>
                        <td className="py-2">{fmt(r.current_rate)} TRY</td>
                        <td className="py-2 font-semibold">{fmt(r.suggested_rate)} TRY</td>
                        <td className="py-2">
                          <span className={`inline-flex items-center gap-0.5 font-medium ${up ? 'text-emerald-600' : down ? 'text-red-500' : 'text-slate-400'}`}>
                            {up ? <ArrowUpRight className="w-3 h-3" /> : down ? <ArrowDownRight className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                            {up ? '+' : ''}{r.change_pct}%
                          </span>
                        </td>
                        <td className="py-2">%{r.occupancy}</td>
                        <td className="py-2">
                          <Badge variant={r.confidence_level === 'Yüksek' ? 'default' : r.confidence_level === 'Orta' ? 'secondary' : 'outline'}
                            className="text-xs">
                            {r.confidence_level}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {recommendations.length > 15 && (
                <p className="text-xs text-slate-400 text-center mt-2">{t('rmsModule.rec_more', { count: recommendations.length - 15 })}</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Channel Detail Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-slate-600">{t('rmsModule.channel_table_title')}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="channel-table">
              <thead>
                <tr className="border-b text-left text-slate-500">
                  <th className="pb-2 font-medium">{t('rmsModule.channel_col_name')}</th>
                  <th className="pb-2 font-medium">{t('rmsModule.channel_col_bookings')}</th>
                  <th className="pb-2 font-medium">{t('rmsModule.channel_col_revenue')}</th>
                  <th className="pb-2 font-medium">{t('rmsModule.channel_col_nights')}</th>
                  <th className="pb-2 font-medium">{t('rmsModule.channel_col_share')}</th>
                </tr>
              </thead>
              <tbody>
                {channels.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center text-slate-400 py-4 text-sm">{t('rmsModule.no_data')}</td>
                  </tr>
                ) : channels.map((ch, i) => (
                  <tr key={ch.channel} className="border-b last:border-0 hover:bg-slate-50/50">
                    <td className="py-2 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: channelColors[i] }} />
                      {ch.label}
                    </td>
                    <td className="py-2">{ch.bookings}</td>
                    <td className="py-2 font-medium">{fmt(ch.revenue)} TRY</td>
                    <td className="py-2">{ch.nights}</td>
                    <td className="py-2">
                      <div className="flex items-center gap-2">
                        <div className="w-16 bg-slate-100 rounded-full h-1.5">
                          <div className="h-1.5 rounded-full" style={{ width: `${ch.share_pct}%`, backgroundColor: channelColors[i] }} />
                        </div>
                        <span className="text-xs text-slate-500">{ch.share_pct}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default RMSModule;
