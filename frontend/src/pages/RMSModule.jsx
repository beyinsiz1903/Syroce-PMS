import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
  RefreshCw, Loader2
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

const RMSModule = ({ user, tenant, onLogout, embedded = false }) => {
  const [kpis, setKpis] = useState(null);
  const [channels, setChannels] = useState([]);
  const [dailyTrend, setDailyTrend] = useState([]);
  const [roomTypePerf, setRoomTypePerf] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [genLoading, setGenLoading] = useState(false);
  const [period, setPeriod] = useState('30');

  const wrap = (content) => embedded ? content : (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="rms">{content}</Layout>
  );

  const loadData = useCallback(async () => {
    try {
      const [dashRes, recRes] = await Promise.all([
        axios.get(`/rms/dashboard-kpis?period=${period}`),
        axios.get('/rms/pricing-recommendations?status=pending'),
      ]);
      const d = dashRes.data;
      setKpis(d.kpis);
      setChannels(d.channels || []);
      setDailyTrend(d.daily_trend || []);
      setRoomTypePerf(d.room_type_performance || []);
      setRecommendations(recRes.data.recommendations || []);
    } catch (e) {
      console.error('RMS data load error:', e);
      toast.error('RMS verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleGeneratePricing = async () => {
    setGenLoading(true);
    try {
      const today = new Date();
      const start = today.toISOString().split('T')[0];
      const end = new Date(today.getTime() + 30 * 86400000).toISOString().split('T')[0];
      const res = await axios.post('/rms/generate-pricing', { start_date: start, end_date: end });
      toast.success(`${res.data.summary?.total || 0} fiyat onerisi uretildi`);
      loadData();
    } catch (e) {
      toast.error('Fiyat onerisi uretilemedi');
    } finally {
      setGenLoading(false);
    }
  };

  const handleApplyAll = async () => {
    try {
      const res = await axios.post('/rms/apply-recommendations');
      toast.success(res.data.message || 'Oneriler uygulandi');
      loadData();
    } catch (e) {
      toast.error('Oneriler uygulanamadi');
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

  // Chart: Daily Occupancy Trend
  const trendData = {
    labels: dailyTrend.map(d => {
      const dt = new Date(d.date);
      return `${dt.getDate()}/${dt.getMonth() + 1}`;
    }),
    datasets: [{
      label: 'Doluluk %',
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
      label: 'Rez. Sayisi',
      data: roomTypePerf.map(r => r.count),
      backgroundColor: 'rgba(245,158,11,0.7)',
      borderRadius: 4,
      yAxisID: 'y1',
    }],
  };

  return wrap(
    <div data-testid="rms-dashboard" className="space-y-6 p-1">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-slate-800">RMS Dashboard</h2>
          <p className="text-sm text-slate-500">Ic veriye dayali dinamik fiyatlama ve analiz</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            data-testid="period-select"
            value={period}
            onChange={e => { setPeriod(e.target.value); setLoading(true); }}
            className="text-sm border rounded-md px-2 py-1.5 bg-white"
          >
            <option value="7">Son 7 gun</option>
            <option value="30">Son 30 gun</option>
            <option value="90">Son 90 gun</option>
          </select>
          <Button size="sm" variant="outline" onClick={() => { setLoading(true); loadData(); }} data-testid="refresh-btn">
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card className="bg-gradient-to-br from-sky-50 to-white border-sky-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-sky-600 uppercase tracking-wide">Doluluk</span>
              <Hotel className="w-4 h-4 text-sky-400" />
            </div>
            <p data-testid="kpi-occupancy" className="text-2xl font-bold text-slate-800">%{k.occupancy || 0}</p>
            <DeltaBadge current={k.occupancy} previous={k.occupancy_prev} />
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-emerald-50 to-white border-emerald-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-emerald-600 uppercase tracking-wide">ADR</span>
              <TrendingUp className="w-4 h-4 text-emerald-400" />
            </div>
            <p data-testid="kpi-adr" className="text-2xl font-bold text-slate-800">{fmt(k.adr)} <span className="text-sm font-normal">TRY</span></p>
            <DeltaBadge current={k.adr} previous={k.adr_prev} />
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-violet-50 to-white border-violet-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-violet-600 uppercase tracking-wide">RevPAR</span>
              <Zap className="w-4 h-4 text-violet-400" />
            </div>
            <p data-testid="kpi-revpar" className="text-2xl font-bold text-slate-800">{fmt(k.revpar)} <span className="text-sm font-normal">TRY</span></p>
            <DeltaBadge current={k.revpar} previous={k.revpar_prev} />
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-amber-50 to-white border-amber-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-amber-600 uppercase tracking-wide">Rez. Hizi</span>
              <CalendarDays className="w-4 h-4 text-amber-400" />
            </div>
            <p data-testid="kpi-pickup" className="text-2xl font-bold text-slate-800">{k.pickup_rate || 0}<span className="text-sm font-normal">/gun</span></p>
            <span className="text-xs text-slate-500">Son 7 gun: {k.pickup_count_7d || 0} yeni rez.</span>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-red-50 to-white border-red-100">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-red-600 uppercase tracking-wide">İptal Orani</span>
              <Ban className="w-4 h-4 text-red-400" />
            </div>
            <p data-testid="kpi-cancel" className="text-2xl font-bold text-slate-800">%{k.cancel_rate || 0}</p>
            <span className="text-xs text-slate-500">Toplam gelir: {fmt(k.total_revenue)} TRY</span>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Occupancy Trend */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-600">Doluluk Trendi</CardTitle>
          </CardHeader>
          <CardContent>
            <div data-testid="occupancy-chart" className="h-56">
              <Line data={trendData} options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                  y: { beginAtZero: true, max: 100, ticks: { callback: v => `${v}%` } },
                  x: { grid: { display: false } },
                },
              }} />
            </div>
          </CardContent>
        </Card>

        {/* Channel Distribution */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-slate-600">Kanal Dagilimi</CardTitle>
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
                <p className="text-sm text-slate-400">Veri yok</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Room Type Performance */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-slate-600">Oda Tipi Performansi</CardTitle>
        </CardHeader>
        <CardContent>
          <div data-testid="roomtype-chart" className="h-52">
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
          </div>
        </CardContent>
      </Card>

      {/* Pricing Recommendations */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-slate-600">
            Fiyat Onerileri
            {recommendations.length > 0 && (
              <Badge variant="secondary" className="ml-2">{recommendations.length} bekleyen</Badge>
            )}
          </CardTitle>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={handleGeneratePricing} disabled={genLoading} data-testid="generate-pricing-btn">
              {genLoading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Zap className="w-4 h-4 mr-1" />}
              Oneri Uret
            </Button>
            {recommendations.length > 0 && (
              <Button size="sm" onClick={handleApplyAll} data-testid="apply-all-btn">
                Tumunu Uygula ({recommendations.length})
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {recommendations.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-6">
              Bekleyen oneri yok. "Oneri Uret" ile yeni oneriler olusturabilirsiniz.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="recommendations-table">
                <thead>
                  <tr className="border-b text-left text-slate-500">
                    <th className="pb-2 font-medium">Tarih</th>
                    <th className="pb-2 font-medium">Oda Tipi</th>
                    <th className="pb-2 font-medium">Mevcut</th>
                    <th className="pb-2 font-medium">Onerilen</th>
                    <th className="pb-2 font-medium">Degisim</th>
                    <th className="pb-2 font-medium">Doluluk</th>
                    <th className="pb-2 font-medium">Guven</th>
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
                          <Badge variant={r.confidence_level === 'Yuksek' ? 'default' : r.confidence_level === 'Orta' ? 'secondary' : 'outline'}
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
                <p className="text-xs text-slate-400 text-center mt-2">+{recommendations.length - 15} daha fazla oneri</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Channel Detail Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-slate-600">Kanal Detay Tablosu</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="channel-table">
              <thead>
                <tr className="border-b text-left text-slate-500">
                  <th className="pb-2 font-medium">Kanal</th>
                  <th className="pb-2 font-medium">Rez. Sayisi</th>
                  <th className="pb-2 font-medium">Toplam Gelir</th>
                  <th className="pb-2 font-medium">Gece Sayisi</th>
                  <th className="pb-2 font-medium">Pay (%)</th>
                </tr>
              </thead>
              <tbody>
                {channels.map((ch, i) => (
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
