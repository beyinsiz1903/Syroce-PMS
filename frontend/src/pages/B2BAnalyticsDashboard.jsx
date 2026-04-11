import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  BarChart3, TrendingUp, DollarSign, Activity, Download,
  Building2, Zap, RefreshCw, FileText,
} from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell,
} from 'recharts';
import { KPICard, CustomTooltip, COLORS, formatCurrency, formatNumber } from './reports/ReportHelpers';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const apiFetch = async (path, params = {}) => {
  const token = localStorage.getItem('token');
  const qs = new URLSearchParams(params).toString();
  const url = `${BACKEND_URL}${path}${qs ? '?' + qs : ''}`;
  const res = await fetch(url, { headers: { 'Authorization': 'Bearer ' + token } });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
};

const apiFetchBlob = async (path, params = {}) => {
  const token = localStorage.getItem('token');
  const qs = new URLSearchParams(params).toString();
  const url = `${BACKEND_URL}${path}${qs ? '?' + qs : ''}`;
  const res = await fetch(url, { headers: { 'Authorization': 'Bearer ' + token } });
  if (!res.ok) throw new Error(`Export ${res.status}`);
  return res.blob();
};

const PERIOD_OPTIONS = [
  { value: '7d', label: 'Son 7 Gun' },
  { value: '30d', label: 'Son 30 Gun' },
  { value: '90d', label: 'Son 90 Gun' },
  { value: '180d', label: 'Son 6 Ay' },
  { value: '365d', label: 'Son 1 Yil' },
];

const EVENT_TYPE_LABELS = {
  api_call: 'API Cagrisi',
  reservation_created: 'Rezervasyon',
  reservation_cancelled: 'Iptal',
  channel_sync: 'Kanal Senk.',
  webhook_received: 'Webhook',
  guest_created: 'Misafir',
  report_generated: 'Rapor',
  invoice_created: 'Fatura',
  ai_request: 'AI Istek',
  login: 'Giris',
  night_audit_run: 'Gece Audit',
};

const getEventLabel = (type) => EVENT_TYPE_LABELS[type] || type;

export default function B2BAnalyticsDashboard() {
  const [period, setPeriod] = useState('30d');
  const [agencyFilter, setAgencyFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null);
  const [agencies, setAgencies] = useState([]);
  const [trends, setTrends] = useState([]);
  const [apiUsage, setApiUsage] = useState({ timeline: [], totals: [] });
  const [topEndpoints, setTopEndpoints] = useState([]);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { period };
      const trendParams = { ...params, ...(agencyFilter !== 'all' ? { agency_id: agencyFilter } : {}) };
      const [sumRes, agRes, trendRes, usageRes, topRes] = await Promise.all([
        apiFetch('/api/b2b-analytics/summary', params).catch(() => null),
        apiFetch('/api/b2b-analytics/agency-breakdown', params).catch(() => null),
        apiFetch('/api/b2b-analytics/booking-trends', trendParams).catch(() => null),
        apiFetch('/api/b2b-analytics/api-usage', params).catch(() => null),
        apiFetch('/api/b2b-analytics/top-endpoints', params).catch(() => null),
      ]);

      const failedCount = [sumRes, agRes, trendRes, usageRes, topRes].filter(r => !r).length;
      if (failedCount === 5) {
        setError('Analitik verileri yuklenemedi. Lutfen tekrar deneyin.');
      } else if (failedCount > 0) {
        setError('Bazi veriler yuklenemedi. Eksik bolumler olabilir.');
      }

      if (sumRes) setSummary(sumRes);
      if (agRes) setAgencies(agRes.agencies || []);
      if (trendRes) setTrends(trendRes.trends || []);
      if (usageRes) setApiUsage({ timeline: usageRes.timeline || [], totals: usageRes.totals || [] });
      if (topRes) setTopEndpoints(topRes.endpoints || []);
    } catch {
      setError('Analitik verileri yuklenemedi. Lutfen tekrar deneyin.');
    } finally {
      setLoading(false);
    }
  }, [period, agencyFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleExport = async (type) => {
    setExporting(true);
    try {
      const blob = await apiFetchBlob('/api/b2b-analytics/export', { period, export_type: type });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `b2b_${type}_${period}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Dosya indirilemedi. Lutfen tekrar deneyin.');
    } finally {
      setExporting(false);
    }
  };

  const kpis = summary?.kpis || {};

  return (
    <div className="min-h-screen bg-gray-50/50 p-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BarChart3 className="w-7 h-7 text-indigo-600" />
            B2B Analytics
          </h1>
          <p className="text-sm text-gray-500 mt-1">Acente performansi ve API kullanim analitikleri</p>
        </div>

        <div className="flex items-center gap-3">
          <Select value={period} onValueChange={setPeriod}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={agencyFilter} onValueChange={setAgencyFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Tum Acenteler" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tum Acenteler</SelectItem>
              {agencies.map((a) => (
                <SelectItem key={a.agency_id} value={a.agency_id}>{a.agency_name}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button variant="outline" size="icon" onClick={fetchData} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center justify-between">
          <p className="text-sm text-amber-800">{error}</p>
          <Button variant="ghost" size="sm" onClick={() => setError(null)} className="text-amber-600 hover:text-amber-800">
            Kapat
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <KPICard title="Toplam Rez." value={kpis.total_bookings || 0} icon={FileText} color="blue" />
        <KPICard title="Onaylanan" value={kpis.approved_bookings || 0} icon={TrendingUp} color="green" />
        <KPICard title="Donusum %" value={`%${kpis.conversion_rate || 0}`} icon={Zap} color="purple" />
        <KPICard title="Toplam Gelir" value={kpis.total_revenue || 0} icon={DollarSign} color="amber" />
        <KPICard title="Aktif Acente" value={kpis.active_agencies || 0} icon={Building2} color="cyan" />
        <KPICard title="API Cagrisi" value={kpis.api_calls || 0} icon={Activity} color="indigo" />
      </div>

      <Tabs defaultValue="bookings" className="space-y-4">
        <TabsList className="bg-white border">
          <TabsTrigger value="bookings">Rez. Trendleri</TabsTrigger>
          <TabsTrigger value="agencies">Acente Performansi</TabsTrigger>
          <TabsTrigger value="api">API Kullanimi</TabsTrigger>
          <TabsTrigger value="endpoints">Top Endpointler</TabsTrigger>
        </TabsList>

        <TabsContent value="bookings" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-gray-700">Gunluk Rezervasyonlar</CardTitle>
              </CardHeader>
              <CardContent>
                {trends.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={trends}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend />
                      <Bar dataKey="approved" name="Onaylanan" fill="#059669" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="pending" name="Bekleyen" fill="#D97706" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="rejected" name="Reddedilen" fill="#DC2626" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[300px] flex items-center justify-center text-gray-400 text-sm">
                    Veri bulunamadi
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-gray-700">Gunluk Gelir Trendi</CardTitle>
              </CardHeader>
              <CardContent>
                {trends.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={trends}>
                      <defs>
                        <linearGradient id="revenueGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#2563EB" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#2563EB" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
                      <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                      <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#2563EB" fill="url(#revenueGrad)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[300px] flex items-center justify-center text-gray-400 text-sm">
                    Veri bulunamadi
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="agencies" className="space-y-4">
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-gray-700">Acente Bazli Performans</CardTitle>
              <Button variant="outline" size="sm" onClick={() => handleExport('agencies')} disabled={exporting}>
                <Download className="w-4 h-4 mr-1" />
                CSV
              </Button>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="py-2 px-3 font-medium">Acente</th>
                      <th className="py-2 px-3 font-medium text-center">Durum</th>
                      <th className="py-2 px-3 font-medium text-right">Komisyon %</th>
                      <th className="py-2 px-3 font-medium text-right">Rez.</th>
                      <th className="py-2 px-3 font-medium text-right">Onay</th>
                      <th className="py-2 px-3 font-medium text-right">Donusum</th>
                      <th className="py-2 px-3 font-medium text-right">Gelir</th>
                      <th className="py-2 px-3 font-medium text-right">Net</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agencies.length > 0 ? agencies.map((a) => (
                      <tr key={a.agency_id} className="border-b hover:bg-gray-50 transition-colors">
                        <td className="py-2.5 px-3 font-medium text-gray-900">{a.agency_name}</td>
                        <td className="py-2.5 px-3 text-center">
                          <Badge variant={a.status === 'active' ? 'default' : 'secondary'} className="text-[10px]">
                            {a.status === 'active' ? 'Aktif' : 'Pasif'}
                          </Badge>
                        </td>
                        <td className="py-2.5 px-3 text-right">%{a.commission_rate}</td>
                        <td className="py-2.5 px-3 text-right">{formatNumber(a.total_bookings)}</td>
                        <td className="py-2.5 px-3 text-right text-emerald-600 font-medium">{formatNumber(a.approved_bookings)}</td>
                        <td className="py-2.5 px-3 text-right">
                          <span className={a.conversion_rate >= 50 ? 'text-emerald-600' : 'text-amber-600'}>
                            %{a.conversion_rate}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-right font-medium">{formatCurrency(a.revenue)}</td>
                        <td className="py-2.5 px-3 text-right font-medium text-indigo-600">{formatCurrency(a.net_revenue)}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="8" className="py-8 text-center text-gray-400">
                          Acente verisi bulunamadi
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {agencies.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold text-gray-700">Acente Gelir Dagilimi</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie
                        data={agencies.filter(a => a.revenue > 0).slice(0, 8)}
                        dataKey="revenue"
                        nameKey="agency_name"
                        cx="50%" cy="50%"
                        outerRadius={100}
                        label={({ agency_name, percent }) => `${agency_name} (${(percent * 100).toFixed(0)}%)`}
                        labelLine={{ strokeWidth: 1 }}
                      >
                        {agencies.filter(a => a.revenue > 0).slice(0, 8).map((_, idx) => (
                          <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(val) => formatCurrency(val)} />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold text-gray-700">Acente Rez. Karsilastirmasi</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={agencies.slice(0, 8)} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis type="number" tick={{ fontSize: 11 }} />
                      <YAxis dataKey="agency_name" type="category" tick={{ fontSize: 11 }} width={120} />
                      <Tooltip content={<CustomTooltip />} />
                      <Bar dataKey="approved_bookings" name="Onaylanan" fill="#059669" radius={[0, 4, 4, 0]} />
                      <Bar dataKey="total_bookings" name="Toplam" fill="#93C5FD" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="api" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2 flex flex-row items-center justify-between">
                <CardTitle className="text-sm font-semibold text-gray-700">API Kullanim Trendi</CardTitle>
                <Button variant="outline" size="sm" onClick={() => handleExport('usage')} disabled={exporting}>
                  <Download className="w-4 h-4 mr-1" />
                  CSV
                </Button>
              </CardHeader>
              <CardContent>
                {apiUsage.timeline.length > 0 ? (
                  <ResponsiveContainer width="100%" height={320}>
                    <AreaChart data={apiUsage.timeline}>
                      <defs>
                        {['api_call', 'reservation_created', 'channel_sync', 'webhook_received'].map((key, i) => (
                          <linearGradient key={key} id={`grad_${key}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={COLORS[i]} stopOpacity={0.2} />
                            <stop offset="95%" stopColor={COLORS[i]} stopOpacity={0} />
                          </linearGradient>
                        ))}
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(v) => v.slice(5)} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip content={<CustomTooltip formatter={formatNumber} />} />
                      <Legend />
                      {['api_call', 'reservation_created', 'channel_sync', 'webhook_received'].map((key, i) => (
                        <Area
                          key={key}
                          type="monotone"
                          dataKey={key}
                          name={getEventLabel(key)}
                          stroke={COLORS[i]}
                          fill={`url(#grad_${key})`}
                          strokeWidth={2}
                        />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[320px] flex items-center justify-center text-gray-400 text-sm">
                    Veri bulunamadi
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-gray-700">Olay Tipi Dagilimi</CardTitle>
              </CardHeader>
              <CardContent>
                {apiUsage.totals.length > 0 ? (
                  <ResponsiveContainer width="100%" height={320}>
                    <PieChart>
                      <Pie
                        data={apiUsage.totals.slice(0, 8).map(t => ({ ...t, name: getEventLabel(t.event_type) }))}
                        dataKey="total"
                        nameKey="name"
                        cx="50%" cy="50%"
                        innerRadius={50}
                        outerRadius={90}
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        labelLine={{ strokeWidth: 1 }}
                      >
                        {apiUsage.totals.slice(0, 8).map((_, idx) => (
                          <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(val) => formatNumber(val)} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[320px] flex items-center justify-center text-gray-400 text-sm">
                    Veri bulunamadi
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="endpoints" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-700">En Cok Kullanilan Endpointler</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {topEndpoints.length > 0 ? topEndpoints.map((ep, idx) => (
                  <div key={ep.event_type} className="flex items-center gap-3">
                    <span className="text-xs font-bold text-gray-400 w-6 text-right">#{idx + 1}</span>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-gray-800">{getEventLabel(ep.event_type)}</span>
                        <span className="text-sm text-gray-600">{formatNumber(ep.total_calls)} <span className="text-gray-400 text-xs">(%{ep.percentage})</span></span>
                      </div>
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{ width: `${ep.percentage}%`, backgroundColor: COLORS[idx % COLORS.length] }}
                        />
                      </div>
                    </div>
                  </div>
                )) : (
                  <div className="py-8 text-center text-gray-400 text-sm">
                    Veri bulunamadi
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => handleExport('bookings')} disabled={exporting}>
          <Download className="w-4 h-4 mr-1" />
          Rez. CSV
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleExport('agencies')} disabled={exporting}>
          <Download className="w-4 h-4 mr-1" />
          Acente CSV
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleExport('usage')} disabled={exporting}>
          <Download className="w-4 h-4 mr-1" />
          Kullanim CSV
        </Button>
      </div>
    </div>
  );
}
