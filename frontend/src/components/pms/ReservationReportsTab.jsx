import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { CalendarRange, Download, RefreshCw, TrendingDown, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { bookingSourceLabel } from '@/utils/bookingSource';
import { useBusinessDate } from '@/hooks/useBusinessDate';
import { validateReportDate, reportDownloadError } from '@/utils/reportExports';

const COLORS = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899'];

const money = (value, currency) => value == null ? '—' : formatCurrency(value, currency || cachedTenantCurrency(), { locale: 'tr-TR', decimals: 2, compactDecimals: false });
const moneyBreakdown = (totals, fallback, currency) => {
  const entries = Object.entries(totals || {});
  if (!entries.length) return money(fallback ?? 0, currency);
  return entries.sort(([left], [right]) => left.localeCompare(right)).map(([code, amount]) => `${code}: ${money(amount, code)}`).join(' · ');
};

const ReservationReportsTab = () => {
  const businessDate = useBusinessDate();
  const [startDate, setStartDate] = useState(() => `${businessDate.slice(0, 7)}-01`);
  const [endDate, setEndDate] = useState(businessDate);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const requestId = useRef(0);
  const customPeriod = useRef(false);

  useEffect(() => {
    if (!customPeriod.current) {
      setStartDate(`${businessDate.slice(0, 7)}-01`);
      setEndDate(businessDate);
    }
  }, [businessDate]);

  const periodError = useCallback(() => {
    try {
      const start = validateReportDate(startDate);
      const end = validateReportDate(endDate);
      if (start > end) return 'Başlangıç tarihi bitiş tarihinden sonra olamaz.';
      if ((end - start) / 86_400_000 >= 366) return 'Rezervasyon raporu en fazla 366 günlük aralıkta alınabilir.';
      if (endDate === '9999-12-31') return 'Geçerli bir rapor tarihi seçin.';
      return '';
    } catch (invalid) { return invalid.message; }
  }, [startDate, endDate]);

  const load = useCallback(async (force = false) => {
    const request = ++requestId.current;
    setData(null);
    const invalid = periodError();
    setError(invalid);
    if (invalid) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const response = await axios.get('/reports/reservation-performance', {
        params: { start_date: startDate, end_date: endDate, ...(force ? { nocache: 1 } : {}) },
      });
      if (request !== requestId.current) return;
      const payload = response.data;
      if (!payload?.summary || typeof payload.summary !== 'object' || !Number.isFinite(payload.summary.total_bookings)
        || payload.start_date !== startDate || payload.end_date !== endDate
        || !Array.isArray(payload.rows) || !Array.isArray(payload.daily_arrivals)
        || !Array.isArray(payload.channel_breakdown) || !Array.isArray(payload.status_breakdown) || !Array.isArray(payload.lead_time_breakdown)) {
        throw new Error('Rapor yanıtı eksik. Sıfır sonuç olarak değerlendirmeyin.');
      }
      setData(payload);
    } catch (error) {
      if (request !== requestId.current) return;
      const detail = error?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : (error.message?.startsWith('Rapor yanıtı') ? error.message : 'Rezervasyon raporu yüklenemedi. Lütfen tekrar deneyin.'));
    } finally {
      if (request === requestId.current) setLoading(false);
    }
  }, [endDate, startDate, periodError]);

  useEffect(() => {
    load();
    return () => { requestId.current += 1; };
  }, [load]);

  const selectPeriod = (setter, value) => {
    customPeriod.current = true;
    requestId.current += 1;
    setData(null);
    setter(value);
  };

  const downloadExcel = async () => {
    if (!data || loading || downloading || periodError()) return;
    setDownloading(true);
    let url;
    try {
      const response = await axios.get('/reports/reservation-performance/excel', {
        params: { start_date: data.start_date, end_date: data.end_date },
        responseType: 'blob',
      });
      url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `rezervasyon_performansi_${data.start_date}_${data.end_date}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      toast.error(await reportDownloadError(error));
    } finally {
      if (url) URL.revokeObjectURL(url);
      setDownloading(false);
    }
  };

  const summary = data?.summary || {};
  const dailyData = data?.daily_arrivals || [];
  const channels = data?.channel_breakdown || [];
  const statuses = data?.status_breakdown || [];
  const leadTime = data?.lead_time_breakdown || [];
  const rows = data?.rows || [];
  const quality = data?.data_quality || {};

  return (
    <div className="space-y-4 mt-4 min-w-0">
      <Card>
        <CardContent className="pt-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex items-center gap-2">
              <CalendarRange className="h-5 w-5 text-blue-600" />
              <div>
                <h3 className="font-semibold">Rezervasyon Analizi</h3>
                <p className="text-sm text-muted-foreground">Konaklama başlangıç tarihine göre rezervasyon, kanal, iptal ve talep analizi.</p>
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label className="grid gap-1 text-xs text-muted-foreground">
                Başlangıç
                <Input aria-label="Rezervasyon raporu başlangıç tarihi" type="date" value={startDate} onChange={(event) => selectPeriod(setStartDate, event.target.value)} />
              </label>
              <label className="grid gap-1 text-xs text-muted-foreground">
                Bitiş
                <Input aria-label="Rezervasyon raporu bitiş tarihi" type="date" value={endDate} onChange={(event) => selectPeriod(setEndDate, event.target.value)} />
              </label>
              <Button variant="outline" onClick={() => load(true)} disabled={loading}>
                <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Yenile
              </Button>
              <Button onClick={downloadExcel} disabled={!data || loading || downloading}>
                <Download className="mr-2 h-4 w-4" /> Excel paketi
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {error && <p role="alert" className="rounded-md border border-destructive/30 p-3 text-sm text-destructive">{error}</p>}
      {loading ? (
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-28" />)}
        </div>
      ) : data ? (
        <>
          <p className="text-sm text-muted-foreground">Dönem: {data.start_date} – {data.end_date}. Geçerli rezervasyon bedeli, tahsilat veya muhasebeleşmiş gelir değildir. Taslak/bekleyen ve geçersiz konaklamalar satışa katılmaz; ücretsiz odaların referans bedeli sıfırdır. Dövizler ayrı gösterilir, kur dönüşümü yapılmaz.</p>
          {(quality.invalid_amounts > 0 || quality.invalid_stays > 0 || quality.invalid_lead_times > 0) && <p role="alert" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">Veri kontrolü: {quality.invalid_amounts || 0} tutar, {quality.invalid_stays || 0} konaklama, {quality.invalid_lead_times || 0} rezervasyon süresi hesaplanamadı. Eksik veriler ilgili hesaplara katılmadı; sonuç tam toplam değildir.</p>}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <Metric title="Toplam rezervasyon" value={summary.total_bookings ?? 0} />
            <Metric title="Geçerli rezervasyon bedeli" value={moneyBreakdown(summary.booked_revenue_by_currency, summary.booked_revenue, data.currency)} tone="text-emerald-700" caption={`${summary.commercial_bookings ?? 0} geçerli rezervasyon`} />
            <Metric title="Oda/gece" value={summary.total_room_nights ?? 0} />
            <Metric title="Ort. konaklama" value={`${summary.average_stay ?? 0} gece`} />
            <Metric title="Ort. rezervasyon süresi" value={`${summary.average_lead_time ?? 0} gün`} />
            <Metric title="İptal / No-show" value={`${summary.cancelled_count ?? 0} / ${summary.no_show_count ?? 0}`} tone="text-rose-700" caption={`Tüm kayıtlar içinde iptal %${summary.cancellation_rate ?? 0} (no-show hariç)`} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Giriş tarihine göre rezervasyon</CardTitle>
                <CardDescription>Tüm durumlar toplamda görünür; yeşil sütun geçerli durum ve konaklamaları gösterir.</CardDescription>
              </CardHeader>
              <CardContent>
                {dailyData.length ? <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={dailyData} margin={{ left: -16, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tickFormatter={(value) => value.slice(5)} fontSize={12} />
                    <YAxis allowDecimals={false} fontSize={12} />
                    <Tooltip labelFormatter={(value) => `Giriş: ${value}`} />
                    <Legend />
                    <Bar dataKey="reservations" name="Toplam" fill="#2563eb" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="commercial_reservations" name="Geçerli" fill="#10b981" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer> : <Empty />}
              </CardContent>
            </Card>

            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Rezervasyon durumu</CardTitle>
                <CardDescription>İptal, no-show ve onaylanmamış kayıtlar ayrı görünür; satışa katılmaz.</CardDescription>
              </CardHeader>
              <CardContent>
                {statuses.length ? <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={statuses} dataKey="count" nameKey="label" innerRadius={55} outerRadius={90} paddingAngle={2}>
                      {statuses.map((item, index) => <Cell key={item.status} fill={COLORS[index % COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(value) => [value, 'Rezervasyon']} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer> : <Empty />}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Kanal ve kaynak performansı</CardTitle>
                <CardDescription>Gece ve bedel yalnız geçerli rezervasyonlardan; son sütun iptal ve no-show toplamıdır.</CardDescription>
              </CardHeader>
              <CardContent>
                {channels.length ? <><p className="mb-2 text-xs text-muted-foreground">Dar ekranda tüm sütunlar için tabloyu yana kaydırın.</p><div role="region" aria-label="Kanal ve kaynak tablosu" tabIndex={0} className="overflow-x-auto">
                  <table className="w-full min-w-[650px] text-sm">
                    <thead className="border-b text-left text-muted-foreground">
                      <tr><th className="p-2">Kanal</th><th className="p-2 text-right">Rez.</th><th className="p-2 text-right">Gece</th><th className="p-2 text-right">Rezervasyon bedeli</th><th className="p-2 text-right">İptal/No-show</th></tr>
                    </thead>
                    <tbody>
                      {channels.map((item) => <tr key={item.channel} className="border-b last:border-0">
                        <td className="p-2 font-medium">{bookingSourceLabel({ channel: item.channel })}</td><td className="p-2 text-right">{item.bookings}</td><td className="p-2 text-right">{item.nights}</td><td className="p-2 text-right">{moneyBreakdown(item.revenue_by_currency, item.revenue, data.currency)}</td><td className="p-2 text-right text-rose-700">{item.cancelled}</td>
                      </tr>)}
                    </tbody>
                  </table>
                </div></> : <Empty />}
              </CardContent>
            </Card>

            <Card className="min-w-0">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Rezervasyon ne kadar önce geliyor?</CardTitle>
                <CardDescription>Tüm durumlarda giriş günü ile oluşturma günü arasındaki süre; girişten sonra oluşturulmuş kayıtlar hariç.</CardDescription>
              </CardHeader>
              <CardContent>
                {leadTime.some((item) => item.count) ? <ResponsiveContainer width="100%" height={230}>
                  <BarChart data={leadTime} margin={{ left: -16, right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" fontSize={12} />
                    <YAxis allowDecimals={false} fontSize={12} />
                    <Tooltip formatter={(value) => [value, 'Rezervasyon']} />
                    <Bar dataKey="count" name="Rezervasyon" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer> : <Empty text="Rezervasyon oluşturma tarihi bulunmadığı için talep süresi hesaplanamadı." />}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base"><Users className="h-4 w-4" /> Rezervasyon listesi</CardTitle>
              <CardDescription>{rows.length} kayıt; Excel paketi tüm tabloyu, kanal ve durum özetlerini içerir. Dar ekranda tüm sütunlar için tabloyu yana kaydırın.</CardDescription>
            </CardHeader>
            <CardContent>
              {rows.length ? <div role="region" aria-label="Rezervasyon detay tablosu" tabIndex={0} className="max-h-96 overflow-auto rounded-md border">
                <table className="w-full min-w-[800px] text-sm">
                  <thead className="sticky top-0 bg-background text-left text-muted-foreground shadow-sm">
                    <tr><th className="p-3">Misafir</th><th className="p-3">Oda</th><th className="p-3">Giriş / Çıkış</th><th className="p-3">Durum</th><th className="p-3">Kanal</th><th className="p-3 text-right">Gece</th><th className="p-3 text-right">Tutar</th><th className="p-3 text-right">Önceden</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => <tr key={row.booking_id || `${row.guest_name}-${row.check_in}`} className="border-t">
                      <td className="p-3 font-medium">{row.guest_name}</td><td className="p-3">{row.room_number}</td><td className="p-3 whitespace-nowrap">{row.check_in} — {row.check_out}</td><td className="p-3">{row.status_label}</td><td className="p-3">{bookingSourceLabel({ channel: row.channel })}</td><td className="p-3 text-right">{row.nights}</td><td className="p-3 text-right">{money(row.total_amount, row.currency)}</td><td className="p-3 text-right">{row.lead_time_days == null ? '—' : `${row.lead_time_days} gün`}</td>
                    </tr>)}
                  </tbody>
                </table>
              </div> : <Empty />}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
};

const Metric = ({ title, value, caption, tone = 'text-foreground' }) => (
  <Card className="min-w-0">
    <CardContent className="pt-4 min-w-0">
      <p className="text-xs text-muted-foreground">{title}</p>
      <p className={`mt-1 text-xl font-bold break-words ${tone}`} style={{ overflowWrap: 'anywhere' }}>{value}</p>
      {caption && <p className="mt-1 text-xs text-muted-foreground">{caption}</p>}
    </CardContent>
  </Card>
);

const Empty = ({ text = 'Seçilen tarih aralığında rezervasyon verisi yok.' }) => (
  <div className="flex min-h-40 items-center justify-center text-center text-sm text-muted-foreground">
    <TrendingDown className="mr-2 h-4 w-4" /> {text}
  </div>
);

export default ReservationReportsTab;
