import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
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
import { KPICard, CustomTooltip, COLORS, formatNumber } from './reports/ReportHelpers';
import { formatCurrency as formatTenantCurrency } from '@/lib/currency';
import { useTranslation } from 'react-i18next';

// Tur 21 #3: raw fetch yerine axios — silent token refresh, retry, axios-cache
// ve correlation-id interceptor'larina otomatik dahil olur. Token Authorization
// header'i App.jsx'te axios.defaults uzerinden ekleniyor; manuel set gereksiz.
// `/api/...` mutlak path bilincli (skill: native fetch icin /api/, axios icin
// relative; ama burada interceptor zinciri istedigimiz icin axios + tam path).

const PERIOD_OPTIONS = [
  // Tur 21 #7: Türkçe karakter normalizasyonu (Gun → Gün, Yil → Yıl).
  { value: '7d', label: 'Son 7 Gün' },
  { value: '30d', label: 'Son 30 Gün' },
  { value: '90d', label: 'Son 90 Gün' },
  { value: '180d', label: 'Son 6 Ay' },
  { value: '365d', label: 'Son 1 Yıl' },
];

const EVENT_TYPE_LABELS = {
  api_call: 'API Çağrısı',
  reservation_created: 'Rezervasyon',
  reservation_cancelled: 'İptal',
  channel_sync: 'Kanal Senk.',
  webhook_received: 'Webhook',
  guest_created: 'Misafir',
  report_generated: 'Rapor',
  invoice_created: 'Fatura',
  ai_request: 'AI İstek',
  login: 'Giriş',
  night_audit_run: 'Gece Audit',
};
const getEventLabel = (type) => EVENT_TYPE_LABELS[type] || type;

// Tur 21 #2: reservation_cancelled grafikte yoktu — eklendi.
const TIMELINE_KEYS = [
  'api_call', 'reservation_created', 'reservation_cancelled',
  'channel_sync', 'webhook_received',
];

// Tur 21 #3: 5xx tek-retry yardimcisi (4xx'te retry yok, abort sessiz).
const fetchJsonWithRetry = async (path, params, signal) => {
  const tryOnce = () => axios.get(path, { params, signal }).then(r => r.data);
  try {
    return await tryOnce();
  } catch (e) {
    if (axios.isCancel?.(e) || e?.name === 'CanceledError') throw e;
    const st = e?.response?.status;
    if (st && st >= 400 && st < 500) throw e;
    await new Promise(r => setTimeout(r, 1500));
    return tryOnce();
  }
};

export default function B2BAnalyticsDashboard({ user, tenant }) {
  const { t } = useTranslation();
  // Tur 21 #5: tenant currency override (multi-currency tenant'lar icin).
  const tenantCurrency = (tenant?.currency || tenant?.default_currency || 'TRY').toUpperCase();
  const fmtMoney = useCallback((v) => formatTenantCurrency(v ?? 0, tenantCurrency, { decimals: 0 }), [tenantCurrency]);

  const [period, setPeriod] = useState('30d');
  const [agencyFilter, setAgencyFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [summary, setSummary] = useState(null);
  const [agencies, setAgencies] = useState([]);
  const [trends, setTrends] = useState([]);
  const [apiUsage, setApiUsage] = useState({ timeline: [], totals: [] });
  const [topEndpoints, setTopEndpoints] = useState([]);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);

  const ctrlRef = useRef(null);
  const trendCtrlRef = useRef(null);

  // Tur 21 #4: agency filter sadece booking-trends'i tetikler.
  // Period degisince HEPSI; agency degisince SADECE trends.
  const fetchAllByPeriod = useCallback(async () => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const params = { period };
      const trendParams = { ...params, ...(agencyFilter !== 'all' ? { agency_id: agencyFilter } : {}) };
      const results = await Promise.allSettled([
        fetchJsonWithRetry('/b2b-analytics/summary', params, ctrl.signal),
        fetchJsonWithRetry('/b2b-analytics/agency-breakdown', params, ctrl.signal),
        fetchJsonWithRetry('/b2b-analytics/booking-trends', trendParams, ctrl.signal),
        fetchJsonWithRetry('/b2b-analytics/api-usage', params, ctrl.signal),
        fetchJsonWithRetry('/b2b-analytics/top-endpoints', params, ctrl.signal),
      ]);
      if (ctrl.signal.aborted) return;

      const [sumR, agR, trR, usR, topR] = results;
      const failed = results.filter(r => r.status === 'rejected').length;
      // 403'leri daha aciklayici yap (yeni permission gate).
      const has403 = results.some(r => r.status === 'rejected' && r.reason?.response?.status === 403);
      if (has403) {
        setError('Finans raporu görüntüleme yetkiniz yok (view_finance_reports izni gerekli).');
      } else if (failed === 5) {
        setError('Analitik verileri yüklenemedi. Lütfen tekrar deneyin.');
      } else if (failed > 0) {
        setError('Bazı veriler yüklenemedi. Eksik bölümler olabilir.');
      }

      if (sumR.status === 'fulfilled') setSummary(sumR.value);
      if (agR.status === 'fulfilled') setAgencies(agR.value.agencies || []);
      if (trR.status === 'fulfilled') setTrends(trR.value.trends || []);
      if (usR.status === 'fulfilled') setApiUsage({ timeline: usR.value.timeline || [], totals: usR.value.totals || [] });
      if (topR.status === 'fulfilled') setTopEndpoints(topR.value.endpoints || []);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  // agencyFilter degisikliginde tekrar tetiklemiyoruz — ayri effect'te.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period]);

  // Period'u ref'te tut — agency-only effect'in callback identity'sine
  // bagli olmamasi icin (period degisikliginde TEKRAR trends cagirilmasini
  // engeller; period zaten fetchAllByPeriod ile hepsini ceker).
  const periodRef = useRef(period);
  useEffect(() => { periodRef.current = period; }, [period]);

  const fetchTrendsOnly = useCallback(async (agencyId) => {
    trendCtrlRef.current?.abort();
    const ctrl = new AbortController();
    trendCtrlRef.current = ctrl;
    setTrendsLoading(true);
    try {
      const trendParams = {
        period: periodRef.current,
        ...(agencyId && agencyId !== 'all' ? { agency_id: agencyId } : {}),
      };
      const data = await fetchJsonWithRetry('/b2b-analytics/booking-trends', trendParams, ctrl.signal);
      if (!ctrl.signal.aborted) setTrends(data.trends || []);
    } catch (e) {
      if (axios.isCancel?.(e) || e?.name === 'CanceledError') return;
      // Sessiz hata — tum-yukleme effect'i ana hatalari yonetir.
    } finally {
      if (!ctrl.signal.aborted) setTrendsLoading(false);
    }
  }, []);

  // Period degistiginde HEPSI yuklenir.
  useEffect(() => {
    fetchAllByPeriod();
    return () => ctrlRef.current?.abort();
  }, [fetchAllByPeriod]);

  // YALNIZCA agencyFilter degisiminde trends'i ceker. period degisikliginde
  // (callback identity degisse bile) tetiklenmez — fetchTrendsOnly stabil
  // (deps=[]) ve period periodRef'ten okunur.
  const isFirstAgencyRender = useRef(true);
  useEffect(() => {
    if (isFirstAgencyRender.current) {
      isFirstAgencyRender.current = false;
      return;
    }
    fetchTrendsOnly(agencyFilter);
    return () => trendCtrlRef.current?.abort();
  }, [agencyFilter, fetchTrendsOnly]);

  const handleRefresh = () => fetchAllByPeriod();

  const handleExport = async (type) => {
    setExporting(true);
    try {
      const res = await axios.get('/b2b-analytics/export', {
        params: { period, export_type: type },
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(res.data);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `b2b_${type}_${period}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      const st = e?.response?.status;
      setError(st === 403
        ? 'CSV dışa aktarma yetkiniz yok (view_finance_reports izni gerekli).'
        : 'Dosya indirilemedi. Lütfen tekrar deneyin.');
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
          {/* #7: performansi → performansı, kullanım zaten unicode; hizala */}
          <p className="text-sm text-gray-500 mt-1">{t('cm.pages_B2BAnalyticsDashboard.acente_performansi_ve_api_kullanim_anali')}</p>
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
              <SelectValue placeholder={t('cm.pages_B2BAnalyticsDashboard.tum_acenteler')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('cm.pages_B2BAnalyticsDashboard.tum_acenteler_ce665')}</SelectItem>
              {agencies.map((a) => (
                <SelectItem key={a.agency_id} value={a.agency_id}>{a.agency_name}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Sprint A: standart Yenile butonu */}
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading || trendsLoading ? 'animate-spin' : ''}`} />
            {t('cm.pages_B2BAnalyticsDashboard.yenile')}
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center justify-between">
          <p className="text-sm text-amber-800">{error}</p>
          <Button variant="ghost" size="sm" onClick={() => setError(null)} className="text-amber-600 hover:text-amber-800">
            {t('cm.pages_B2BAnalyticsDashboard.kapat')}
          </Button>
        </div>
      )}

      {/* Tur 21 #6: purple → indigo (replit.md Color Palette Convention) */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <KPICard title={t('cm.pages_B2BAnalyticsDashboard.toplam_rez')} value={kpis.total_bookings || 0} icon={FileText} color="blue" />
        <KPICard title="Onaylanan" value={kpis.approved_bookings || 0} icon={TrendingUp} color="green" />
        <KPICard title={t('cm.pages_B2BAnalyticsDashboard.donusum')} value={`%${kpis.conversion_rate || 0}`} icon={Zap} color="indigo" />
        <KPICard
          title={t('cm.pages_B2BAnalyticsDashboard.toplam_gelir')}
          // KPICard kendi formatCurrency'sini cagiriyor (TRY-only); sayisal istemiyoruz,
          // tenant para birimiyle once formatlayip string verelim.
          value={fmtMoney(kpis.total_revenue || 0)}
          icon={DollarSign} color="amber"
        />
        <KPICard title={t('cm.pages_B2BAnalyticsDashboard.aktif_acente')} value={kpis.active_agencies || 0} icon={Building2} color="cyan" />
        <KPICard title={t('cm.pages_B2BAnalyticsDashboard.api_cagrisi')} value={kpis.api_calls || 0} icon={Activity} color="indigo" />
      </div>

      <Tabs defaultValue="bookings" className="space-y-4">
        <TabsList className="bg-white border">
          <TabsTrigger value="bookings">Rez. Trendleri</TabsTrigger>
          <TabsTrigger value="agencies">{t('cm.pages_B2BAnalyticsDashboard.acente_performansi')}</TabsTrigger>
          <TabsTrigger value="api">{t('cm.pages_B2BAnalyticsDashboard.api_kullanimi')}</TabsTrigger>
          <TabsTrigger value="endpoints">Top Endpointler</TabsTrigger>
        </TabsList>

        <TabsContent value="bookings" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-gray-700">
                  {t('cm.pages_B2BAnalyticsDashboard.gunluk_rezervasyonlar')} {trendsLoading && <span className="text-[10px] text-gray-400 ml-2">{t('cm.pages_B2BAnalyticsDashboard.guncelleniyor')}</span>}
                </CardTitle>
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
                    {t('cm.pages_B2BAnalyticsDashboard.veri_bulunamadi')}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_B2BAnalyticsDashboard.gunluk_gelir_trendi')}</CardTitle>
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
                      <Tooltip content={<CustomTooltip formatter={fmtMoney} />} />
                      <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#2563EB" fill="url(#revenueGrad)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[300px] flex items-center justify-center text-gray-400 text-sm">
                    {t('cm.pages_B2BAnalyticsDashboard.veri_bulunamadi_c60c4')}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="agencies" className="space-y-4">
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_B2BAnalyticsDashboard.acente_bazli_performans')}</CardTitle>
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
                      <th className="py-2 px-3 font-medium text-center">{t('cm.pages_B2BAnalyticsDashboard.durum')}</th>
                      <th className="py-2 px-3 font-medium text-right">Komisyon %</th>
                      <th className="py-2 px-3 font-medium text-right">Rez.</th>
                      <th className="py-2 px-3 font-medium text-right">Onay</th>
                      <th className="py-2 px-3 font-medium text-right">{t('cm.pages_B2BAnalyticsDashboard.donusum_d70ec')}</th>
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
                        <td className="py-2.5 px-3 text-right font-medium">{fmtMoney(a.revenue)}</td>
                        <td className="py-2.5 px-3 text-right font-medium text-indigo-600">{fmtMoney(a.net_revenue)}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="8" className="py-8 text-center text-gray-400">
                          {t('cm.pages_B2BAnalyticsDashboard.acente_verisi_bulunamadi')}
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
                  <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_B2BAnalyticsDashboard.acente_gelir_dagilimi')}</CardTitle>
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
                      <Tooltip formatter={(val) => fmtMoney(val)} />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_B2BAnalyticsDashboard.acente_rez_karsilastirmasi')}</CardTitle>
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
                <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_B2BAnalyticsDashboard.api_kullanim_trendi')}</CardTitle>
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
                        {/* Tur 21 #2: 5. seri (reservation_cancelled) eklendi */}
                        {TIMELINE_KEYS.map((key, i) => (
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
                      {TIMELINE_KEYS.map((key, i) => (
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
                    {t('cm.pages_B2BAnalyticsDashboard.veri_bulunamadi_c60c4')}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_B2BAnalyticsDashboard.olay_tipi_dagilimi')}</CardTitle>
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
                    {t('cm.pages_B2BAnalyticsDashboard.veri_bulunamadi_c60c4')}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="endpoints" className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-gray-700">{t('cm.pages_B2BAnalyticsDashboard.en_cok_kullanilan_endpointler')}</CardTitle>
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
                    {t('cm.pages_B2BAnalyticsDashboard.veri_bulunamadi_c60c4')}
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
          {t('cm.pages_B2BAnalyticsDashboard.kullanim_csv')}
        </Button>
      </div>
    </div>
  );
}
