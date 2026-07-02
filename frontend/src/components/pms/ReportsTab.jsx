import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RefreshCw, TrendingUp, Hotel, DollarSign, BarChart3, LogIn, LogOut, Home } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, ComposedChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, AreaChart, Area } from 'recharts';
import { useTranslation } from 'react-i18next';
const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];
const fmtCurrency = n => {
  if (n == null) return '₺0';
  return `₺${Number(n).toLocaleString('tr-TR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  })}`;
};
const ReportsTab = () => {
  const {
    t
  } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [subTab, setSubTab] = useState('overview');
  const [occupancy, setOccupancy] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [dailyFlash, setDailyFlash] = useState(null);
  const [forecast, setForecast] = useState([]);
  const [forecast30, setForecast30] = useState([]);
  const [marketSegment, setMarketSegment] = useState(null);
  const [hkEfficiency, setHkEfficiency] = useState(null);
  const [dailySummary, setDailySummary] = useState(null);
  const getDateRange = () => {
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
    const monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().split('T')[0];
    return {
      monthStart,
      monthEnd
    };
  };
  const loadAll = useCallback(async (force = false) => {
    setLoading(true);
    const {
      monthStart,
      monthEnd
    } = getDateRange();
    const safe = p => p.catch(() => ({
      data: null
    }));
    // "Yenile" butonu force=true ile çağrılır → backend cache atlanır (her endpoint'te `?nocache=1`).
    const nc = force ? '&nocache=1' : '';
    const ncQ = force ? '?nocache=1' : '';
    try {
      const [occRes, revRes, flashRes, fcRes, fc30Res, mktRes, hkRes, dsRes] = await Promise.all([safe(axios.get(`/reports/occupancy?start_date=${monthStart}&end_date=${monthEnd}${nc}`)), safe(axios.get(`/reports/revenue?start_date=${monthStart}&end_date=${monthEnd}${nc}`)), safe(axios.get(`/reports/daily-flash${ncQ}`)), safe(axios.get(`/reports/forecast?days=7${nc}`)), safe(axios.get(`/reports/forecast?days=30${nc}`)), safe(axios.get(`/reports/market-segment?start_date=${monthStart}&end_date=${monthEnd}${nc}`)), safe(axios.get(`/reports/housekeeping-efficiency?start_date=${monthStart}&end_date=${monthEnd}${nc}`)), safe(axios.get(`/reports/daily-summary${ncQ}`))]);
      setOccupancy(occRes.data);
      setRevenue(revRes.data);
      setDailyFlash(flashRes.data);
      setForecast(Array.isArray(fcRes.data) ? fcRes.data : []);
      setForecast30(Array.isArray(fc30Res.data) ? fc30Res.data : []);
      setMarketSegment(mktRes.data);
      setHkEfficiency(hkRes.data);
      setDailySummary(dsRes.data);
    } catch {
      toast.error('Rapor verileri yuklenirken hata olustu');
    }
    setLoading(false);
  }, []);
  useEffect(() => {
    loadAll(false);
  }, [loadAll]);
  const occRate = occupancy?.occupancy_rate ?? occupancy?.current_occupancy_rate ?? 0;
  const adr = revenue?.adr ?? 0;
  const revpar = revenue?.rev_par ?? revenue?.revpar ?? 0;
  const totalRevenue = revenue?.total_revenue ?? 0;
  const totalRooms = occupancy?.total_rooms ?? 30;
  const occupiedNights = occupancy?.occupied_room_nights ?? 0;
  const forecastChartData = forecast.map(f => ({
    date: f.date?.slice(5),
    doluluk: f.occupancy_rate,
    rez: f.bookings
  }));
  const forecast30ChartData = forecast30.map(f => ({
    date: f.date?.slice(5),
    doluluk: f.occupancy_rate,
    rez: f.bookings
  }));
  const REVENUE_TYPE_LABELS = {
    room: 'Oda',
    room_charge: 'Oda Geliri',
    fb: 'Yiyecek-İçecek',
    food: 'Yemek',
    beverage: 'İçecek',
    spa: 'Spa',
    minibar: 'Minibar',
    laundry: 'Çamaşırhane',
    early_checkin: 'Erken Giriş',
    late_checkout: 'Geç Çıkış',
    airport_transfer: 'Havalimanı Transfer',
    upsell: 'Upsell',
    other: 'Diğer',
    unknown: 'Belirsiz'
  };
  const revenueByType = revenue?.revenue_by_type || {};
  const revenueRaw = Object.entries(revenueByType).map(([key, val]) => ({
    name: REVENUE_TYPE_LABELS[key] || key,
    value: typeof val === 'number' ? val : 0
  })).filter(d => d.value > 0);
  const revenueTotal = revenueRaw.reduce((sum, d) => sum + d.value, 0);
  // Toplamın %1'inden küçük dilimleri "Diğer" altında topla → etiket çakışmasını önler.
  const revenueBreakdownData = (() => {
    if (revenueTotal === 0) return [];
    const significant = [];
    let smallSum = 0;
    revenueRaw.forEach(d => {
      if (d.value / revenueTotal >= 0.01) {
        significant.push(d);
      } else {
        smallSum += d.value;
      }
    });
    if (smallSum > 0) {
      significant.push({
        name: 'Diğer',
        value: smallSum
      });
    }
    return significant.sort((a, b) => b.value - a.value);
  })();
  const marketSegments = marketSegment?.market_segments || {};
  const mktData = Object.entries(marketSegments).map(([key, val]) => ({
    name: key === 'other' ? 'Diger' : key === 'corporate' ? 'Kurumsal' : key === 'ota' ? 'OTA' : key === 'direct' ? 'Direkt' : key,
    rez: val.bookings,
    gece: val.nights,
    gelir: val.revenue,
    adr: val.adr
  }));
  const staffPerf = hkEfficiency?.staff_performance || {};
  const staffData = Object.entries(staffPerf).map(([name, perf]) => ({
    name,
    gorev: perf.tasks_completed,
    gunluk: perf.daily_average
  }));
  const movements = dailyFlash?.movements || {};
  const flashOcc = dailyFlash?.occupancy || {};
  const flashRev = dailyFlash?.revenue || {};
  return <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold">Raporlar & Analiz</h2>
        <Button variant="outline" size="sm" onClick={() => loadAll(true)} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> {t('cm.components_pms_ReportsTab.yenile')}
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <Hotel className="w-4 h-4" /> Doluluk Orani
            </div>
            <p className="text-2xl font-bold">{occupancy ? `%${occRate.toFixed(1)}` : '...'}</p>
            <p className="text-xs text-gray-400">{occupiedNights}/{occupancy?.total_room_nights ?? '-'} oda/gece</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <DollarSign className="w-4 h-4" /> ADR
            </div>
            <p className="text-2xl font-bold">{revenue ? fmtCurrency(adr) : '...'}</p>
            <p className="text-xs text-gray-400">{t('cm.components_pms_ReportsTab.ortalama_gunluk_oda_fiyati')}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-violet-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <TrendingUp className="w-4 h-4" /> RevPAR
            </div>
            <p className="text-2xl font-bold">{revenue ? fmtCurrency(revpar) : '...'}</p>
            <p className="text-xs text-gray-400">{t('cm.components_pms_ReportsTab.oda_basina_gelir')}</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <BarChart3 className="w-4 h-4" /> {t('cm.components_pms_ReportsTab.toplam_gelir')}
            </div>
            <p className="text-2xl font-bold">{revenue ? fmtCurrency(totalRevenue) : '...'}</p>
            <p className="text-xs text-gray-400">Bu ay — {revenue?.bookings_count ?? 0} rezervasyon</p>
          </CardContent>
        </Card>
      </div>

      <Tabs value={subTab} onValueChange={setSubTab}>
        <TabsList>
          <TabsTrigger value="overview">{t('cm.components_pms_ReportsTab.gunluk_ozet')}</TabsTrigger>
          <TabsTrigger value="forecast">Tahmin ({forecast.length + forecast30.length > 0 ? '7/30 Gun' : '-'})</TabsTrigger>
          <TabsTrigger value="market">Pazar Segmenti</TabsTrigger>
          <TabsTrigger value="housekeeping">Kat Hizmetleri</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4 mt-4">
          {dailyFlash ? <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card>
                <CardContent className="pt-4 pb-3 text-center">
                  <LogIn className="w-6 h-6 mx-auto mb-1 text-blue-500" />
                  <p className="text-2xl font-bold text-blue-600">{movements.arrivals ?? 0}</p>
                  <p className="text-xs text-gray-500">{t('cm.components_pms_ReportsTab.giris')}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3 text-center">
                  <LogOut className="w-6 h-6 mx-auto mb-1 text-green-500" />
                  <p className="text-2xl font-bold text-green-600">{movements.departures ?? 0}</p>
                  <p className="text-xs text-gray-500">{t('cm.components_pms_ReportsTab.cikis')}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3 text-center">
                  <Home className="w-6 h-6 mx-auto mb-1 text-indigo-500" />
                  <p className="text-2xl font-bold text-indigo-600">{movements.stayovers ?? 0}</p>
                  <p className="text-xs text-gray-500">Konaklayan</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3 text-center">
                  <Hotel className="w-6 h-6 mx-auto mb-1 text-amber-500" />
                  <p className="text-2xl font-bold text-amber-600">%{flashOcc.occupancy_rate?.toFixed(1) ?? '0'}</p>
                  <p className="text-xs text-gray-500">{flashOcc.occupied_rooms ?? 0}/{flashOcc.total_rooms ?? totalRooms} {t('cm.components_pms_ReportsTab.oda')}</p>
                </CardContent>
              </Card>
            </div> : <Card><CardContent className="py-8 text-center text-gray-400">{t('cm.components_pms_ReportsTab.gunluk_ozet_yuklenemedi')}</CardContent></Card>}

          {dailyFlash?.revenue && <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Gunun Gelir Detayi</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="border rounded-lg p-3 text-center">
                    <p className="text-lg font-bold">{fmtCurrency(flashRev.room_revenue)}</p>
                    <p className="text-xs text-gray-500">{t('cm.components_pms_ReportsTab.oda_geliri')}</p>
                  </div>
                  <div className="border rounded-lg p-3 text-center">
                    <p className="text-lg font-bold">{fmtCurrency(flashRev.fb_revenue)}</p>
                    <p className="text-xs text-gray-500">F&B Geliri</p>
                  </div>
                  <div className="border rounded-lg p-3 text-center">
                    <p className="text-lg font-bold">{fmtCurrency(flashRev.other_revenue)}</p>
                    <p className="text-xs text-gray-500">Diger Gelir</p>
                  </div>
                  <div className="border rounded-lg p-3 text-center bg-gray-50">
                    <p className="text-lg font-bold">{fmtCurrency(flashRev.total_revenue)}</p>
                    <p className="text-xs text-gray-500">{t('cm.components_pms_ReportsTab.toplam')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>}

          {dailySummary && <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{t('cm.components_pms_ReportsTab.gunluk_rapor_ozeti')}</CardTitle>
                <CardDescription>{dailySummary.date}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 md:grid-cols-5 gap-4 text-center">
                  <div>
                    <p className="text-lg font-bold">{dailySummary.arrivals}</p>
                    <p className="text-xs text-gray-500">{t('cm.components_pms_ReportsTab.giris_1ffbd')}</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold">{dailySummary.departures}</p>
                    <p className="text-xs text-gray-500">{t('cm.components_pms_ReportsTab.cikis_b9015')}</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold">{dailySummary.inhouse}</p>
                    <p className="text-xs text-gray-500">Otelde</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold">%{dailySummary.occupancy_rate?.toFixed(1)}</p>
                    <p className="text-xs text-gray-500">Doluluk</p>
                  </div>
                  <div>
                    <p className="text-lg font-bold">{fmtCurrency(dailySummary.daily_revenue)}</p>
                    <p className="text-xs text-gray-500">{t('cm.components_pms_ReportsTab.gunluk_gelir')}</p>
                  </div>
                </div>
              </CardContent>
            </Card>}

          {revenueBreakdownData.length > 0 && <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{t('cm.components_pms_ReportsTab.gelir_dagilimi')}</CardTitle>
                <CardDescription>{t('cm.components_pms_ReportsTab.gelir_kaynagina_gore_dagilim')}</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={340}>
                  <PieChart margin={{
                top: 10,
                right: 20,
                bottom: 10,
                left: 20
              }}>
                    <Pie data={revenueBreakdownData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={45} outerRadius={90} paddingAngle={2} labelLine={false} label={({
                  percent
                }) => {
                  const pct = percent * 100;
                  // Sadece %5+ dilimlerin üzerine yüzde yaz; küçükler Legend'da görünür.
                  return pct >= 5 ? `%${pct.toFixed(0)}` : '';
                }}>
                      {revenueBreakdownData.map((_, i) => <Cell key={_.id || i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v, name) => [fmtCurrency(v), name]} separator=": " />
                    <Legend verticalAlign="bottom" height={48} iconType="circle" formatter={value => <span className="text-xs text-gray-700 dark:text-gray-300">
                          {value}
                        </span>} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>}
        </TabsContent>

        <TabsContent value="forecast" className="space-y-4 mt-4">
          {forecast.length > 0 ? <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{t('cm.components_pms_ReportsTab.7_gunluk_doluluk_tahmini')}</CardTitle>
                <CardDescription>{t('cm.components_pms_ReportsTab.onumuzdeki_7_gun_icin_beklenen_doluluk_v')}</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart data={forecastChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{
                  fontSize: 12
                }} />
                    <YAxis yAxisId="left" domain={[0, 100]} tick={{
                  fontSize: 12
                }} label={{
                  value: '%',
                  position: 'insideTopLeft'
                }} />
                    <YAxis yAxisId="right" orientation="right" tick={{
                  fontSize: 12
                }} label={{
                  value: 'Rez',
                  position: 'insideTopRight'
                }} />
                    <Tooltip formatter={(v, name) => [name === 'doluluk' ? `%${v}` : v, name === 'doluluk' ? 'Doluluk' : 'Rezervasyon']} />
                    <Legend formatter={v => v === 'doluluk' ? 'Doluluk %' : 'Rezervasyon'} />
                    <Bar yAxisId="right" dataKey="rez" fill="#3b82f6" radius={[4, 4, 0, 0]} name="rez" />
                    <Line yAxisId="left" type="monotone" dataKey="doluluk" stroke="#ef4444" strokeWidth={2} dot={{
                  r: 4
                }} name="doluluk" />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card> : <Card><CardContent className="py-8 text-center text-gray-400">{t('cm.components_pms_ReportsTab.tahmin_verisi_bulunamadi')}</CardContent></Card>}

          {forecast30.length > 0 && <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{t('cm.components_pms_ReportsTab.30_gunluk_doluluk_trendi')}</CardTitle>
                <CardDescription>{t('cm.components_pms_ReportsTab.onumuzdeki_30_gun_icin_doluluk_tahmini')}</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <AreaChart data={forecast30ChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{
                  fontSize: 10
                }} interval={2} />
                    <YAxis domain={[0, 100]} tick={{
                  fontSize: 12
                }} />
                    <Tooltip formatter={v => `%${v}`} />
                    <Area type="monotone" dataKey="doluluk" stroke="#8b5cf6" fill="#8b5cf680" strokeWidth={2} name="Doluluk %" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>}
        </TabsContent>

        <TabsContent value="market" className="space-y-4 mt-4">
          {mktData.length > 0 ? <>
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Pazar Segmenti Dagilimi</CardTitle>
                  <CardDescription>{t('cm.components_pms_ReportsTab.rezervasyon_kaynaklarina_gore_dagilim')} {marketSegment?.total_bookings ?? 0} toplam rezervasyon</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 px-3">Segment</th>
                          <th className="text-right py-2 px-3">{t('cm.components_pms_ReportsTab.rezervasyon')}</th>
                          <th className="text-right py-2 px-3">Gece</th>
                          <th className="text-right py-2 px-3">Gelir</th>
                          <th className="text-right py-2 px-3">ADR</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mktData.map((row, i) => <tr key={row.id || i} className="border-b last:border-0">
                            <td className="py-2 px-3 font-medium">{row.name}</td>
                            <td className="py-2 px-3 text-right">{row.rez}</td>
                            <td className="py-2 px-3 text-right">{row.gece}</td>
                            <td className="py-2 px-3 text-right">{fmtCurrency(row.gelir)}</td>
                            <td className="py-2 px-3 text-right">{fmtCurrency(row.adr)}</td>
                          </tr>)}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>

              {mktData.length > 1 && <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Segment Gelir Grafigi</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={280}>
                      <PieChart>
                        <Pie data={mktData.map(m => ({
                    name: m.name,
                    value: m.gelir
                  }))} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label={({
                    name,
                    percent
                  }) => `${name} %${(percent * 100).toFixed(0)}`}>
                          {mktData.map((_, i) => <Cell key={_.id || i} fill={COLORS[i % COLORS.length]} />)}
                        </Pie>
                        <Tooltip formatter={v => fmtCurrency(v)} />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>}

              {marketSegment?.rate_types && <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Fiyat Tipi Dagilimi</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-3">Fiyat Tipi</th>
                            <th className="text-right py-2 px-3">{t('cm.components_pms_ReportsTab.rezervasyon_e95e9')}</th>
                            <th className="text-right py-2 px-3">Gece</th>
                            <th className="text-right py-2 px-3">Gelir</th>
                            <th className="text-right py-2 px-3">ADR</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(marketSegment.rate_types).map(([key, val], i) => <tr key={i} className="border-b last:border-0">
                              <td className="py-2 px-3 font-medium">{key === 'bar' ? 'BAR' : key === 'rack' ? 'Rack' : key}</td>
                              <td className="py-2 px-3 text-right">{val.bookings}</td>
                              <td className="py-2 px-3 text-right">{val.nights}</td>
                              <td className="py-2 px-3 text-right">{fmtCurrency(val.revenue)}</td>
                              <td className="py-2 px-3 text-right">{fmtCurrency(val.adr)}</td>
                            </tr>)}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>}
            </> : <Card><CardContent className="py-8 text-center text-gray-400">{t('cm.components_pms_ReportsTab.pazar_segmenti_verisi_bulunamadi')}</CardContent></Card>}
        </TabsContent>

        <TabsContent value="housekeeping" className="space-y-4 mt-4">
          {hkEfficiency ? <>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <Card className="border-l-4 border-l-blue-500">
                  <CardContent className="pt-4 pb-3">
                    <p className="text-sm text-gray-500">{t('cm.components_pms_ReportsTab.tamamlanan_gorev')}</p>
                    <p className="text-2xl font-bold">{hkEfficiency.total_tasks_completed}</p>
                    <p className="text-xs text-gray-400">{hkEfficiency.date_range_days} {t('cm.components_pms_ReportsTab.gunluk_donem')}</p>
                  </CardContent>
                </Card>
                <Card className="border-l-4 border-l-emerald-500">
                  <CardContent className="pt-4 pb-3">
                    <p className="text-sm text-gray-500">{t('cm.components_pms_ReportsTab.gunluk_ortalama')}</p>
                    <p className="text-2xl font-bold">{hkEfficiency.daily_average_all_staff?.toFixed(1) ?? 0}</p>
                    <p className="text-xs text-gray-400">{t('cm.components_pms_ReportsTab.gorev_gun')}</p>
                  </CardContent>
                </Card>
                <Card className="border-l-4 border-l-violet-500">
                  <CardContent className="pt-4 pb-3">
                    <p className="text-sm text-gray-500">{t('cm.components_pms_ReportsTab.personel_sayisi')}</p>
                    <p className="text-2xl font-bold">{Object.keys(staffPerf).length}</p>
                    <p className="text-xs text-gray-400">aktif personel</p>
                  </CardContent>
                </Card>
              </div>

              {staffData.length > 0 && <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">Personel Performansi</CardTitle>
                    <CardDescription>{t('cm.components_pms_ReportsTab.gorev_tamamlama_sayisina_gore')}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={250}>
                      <BarChart data={staffData} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" tick={{
                    fontSize: 12
                  }} />
                        <YAxis dataKey="name" type="category" tick={{
                    fontSize: 12
                  }} width={80} />
                        <Tooltip formatter={v => [v, 'Görev']} />
                        <Bar dataKey="gorev" fill="#3b82f6" radius={[0, 4, 4, 0]} name="Tamamlanan" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>}

              {staffData.length > 0 && <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base">{t('cm.components_pms_ReportsTab.detayli_personel_raporu')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left py-2 px-3">Personel</th>
                            <th className="text-right py-2 px-3">{t('cm.components_pms_ReportsTab.toplam_29757')}</th>
                            <th className="text-right py-2 px-3">{t('cm.components_pms_ReportsTab.gunluk_ort')}</th>
                            <th className="text-left py-2 px-3">{t('cm.components_pms_ReportsTab.gorev_turleri')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(staffPerf).map(([name, perf], i) => <tr key={i} className="border-b last:border-0">
                              <td className="py-2 px-3 font-medium">{name}</td>
                              <td className="py-2 px-3 text-right">{perf.tasks_completed}</td>
                              <td className="py-2 px-3 text-right">{perf.daily_average?.toFixed(2)}</td>
                              <td className="py-2 px-3">
                                <div className="flex gap-1 flex-wrap">
                                  {Object.entries(perf.by_type || {}).map(([type, cnt]) => <Badge key={type} variant="outline" className="text-xs">
                                      {type === 'cleaning' ? 'Temizlik' : type === 'inspection' ? 'Kontrol' : type === 'turndown' ? 'Turndown' : type === 'deep_cleaning' ? 'Derin Temizlik' : type}: {cnt}
                                    </Badge>)}
                                </div>
                              </td>
                            </tr>)}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>}
            </> : <Card><CardContent className="py-8 text-center text-gray-400">{t('cm.components_pms_ReportsTab.kat_hizmetleri_verisi_bulunamadi')}</CardContent></Card>}
        </TabsContent>
      </Tabs>
    </div>;
};
export default ReportsTab;