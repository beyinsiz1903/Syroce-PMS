import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { CalendarRange, Download, RefreshCw, TrendingDown, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';

const COLORS = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899'];

const isoDate = (date) => {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
};

const money = (value) => `₺${Number(value || 0).toLocaleString('tr-TR', { maximumFractionDigits: 0 })}`;

const ReservationReportsTab = () => {
  const today = useMemo(() => new Date(), []);
  const [startDate, setStartDate] = useState(() => isoDate(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [endDate, setEndDate] = useState(() => isoDate(today));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (force = false) => {
    if (!startDate || !endDate) return;
    if (startDate > endDate) {
      toast.error('Başlangıç tarihi bitiş tarihinden sonra olamaz.');
      return;
    }
    setLoading(true);
    try {
      const response = await axios.get('/reports/reservation-performance', {
        params: { start_date: startDate, end_date: endDate, ...(force ? { nocache: 1 } : {}) },
      });
      setData(response.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Rezervasyon raporu yüklenemedi.');
    } finally {
      setLoading(false);
    }
  }, [endDate, startDate]);

  useEffect(() => {
    load();
  }, [load]);

  const downloadExcel = async () => {
    try {
      const response = await axios.get('/reports/reservation-performance/excel', {
        params: { start_date: startDate, end_date: endDate },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `rezervasyon_performansi_${startDate}_${endDate}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Excel raporu indirilemedi.');
    }
  };

  const summary = data?.summary || {};
  const dailyData = data?.daily_arrivals || [];
  const channels = data?.channel_breakdown || [];
  const statuses = data?.status_breakdown || [];
  const leadTime = data?.lead_time_breakdown || [];
  const rows = data?.rows || [];

  return (
    <div className="space-y-4 mt-4">
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
                <Input aria-label="Rezervasyon raporu başlangıç tarihi" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
              </label>
              <label className="grid gap-1 text-xs text-muted-foreground">
                Bitiş
                <Input aria-label="Rezervasyon raporu bitiş tarihi" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
              </label>
              <Button variant="outline" onClick={() => load(true)} disabled={loading}>
                <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Yenile
              </Button>
              <Button onClick={downloadExcel} disabled={!data || loading}>
                <Download className="mr-2 h-4 w-4" /> Excel paketi
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {loading && !data ? (
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-28" />)}
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <Metric title="Toplam rezervasyon" value={summary.total_bookings ?? 0} />
            <Metric title="Rezerve gelir" value={money(summary.booked_revenue)} tone="text-emerald-700" />
            <Metric title="Oda/gece" value={summary.total_room_nights ?? 0} />
            <Metric title="Ort. konaklama" value={`${summary.average_stay ?? 0} gece`} />
            <Metric title="Ort. rezervasyon süresi" value={`${summary.average_lead_time ?? 0} gün`} />
            <Metric title="İptal / No-show" value={`${summary.cancelled_count ?? 0} / ${summary.no_show_count ?? 0}`} tone="text-rose-700" caption={`İptal oranı %${summary.cancellation_rate ?? 0}`} />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Giriş tarihine göre rezervasyon</CardTitle>
                <CardDescription>İptal edilenler toplamda görünür; yeşil sütun aktif rezervasyonları gösterir.</CardDescription>
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
                    <Bar dataKey="commercial_reservations" name="Aktif" fill="#10b981" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer> : <Empty />}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Rezervasyon durumu</CardTitle>
                <CardDescription>İptal ve no-show rezervasyonlar ayrı görünür; rezerve gelirden çıkarılır.</CardDescription>
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
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Kanal ve kaynak performansı</CardTitle>
                <CardDescription>Kaynak, OTA kanalı veya manuel giriş bilgisine göre toplanır.</CardDescription>
              </CardHeader>
              <CardContent>
                {channels.length ? <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b text-left text-muted-foreground">
                      <tr><th className="pb-2">Kanal</th><th className="pb-2 text-right">Rez.</th><th className="pb-2 text-right">Gece</th><th className="pb-2 text-right">Gelir</th><th className="pb-2 text-right">İptal</th></tr>
                    </thead>
                    <tbody>
                      {channels.map((item) => <tr key={item.channel} className="border-b last:border-0">
                        <td className="py-2 font-medium">{item.channel}</td><td className="py-2 text-right">{item.bookings}</td><td className="py-2 text-right">{item.nights}</td><td className="py-2 text-right">{money(item.revenue)}</td><td className="py-2 text-right text-rose-700">{item.cancelled}</td>
                      </tr>)}
                    </tbody>
                  </table>
                </div> : <Empty />}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Rezervasyon ne kadar önce geliyor?</CardTitle>
                <CardDescription>Giriş tarihi ile oluşturma tarihi arasındaki süre.</CardDescription>
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
              <CardDescription>{rows.length} kayıt; Excel paketi tüm tabloyu, kanal ve durum özetlerini içerir.</CardDescription>
            </CardHeader>
            <CardContent>
              {rows.length ? <div className="max-h-96 overflow-auto rounded-md border">
                <table className="w-full min-w-[800px] text-sm">
                  <thead className="sticky top-0 bg-background text-left text-muted-foreground shadow-sm">
                    <tr><th className="p-3">Misafir</th><th className="p-3">Oda</th><th className="p-3">Giriş / Çıkış</th><th className="p-3">Durum</th><th className="p-3">Kanal</th><th className="p-3 text-right">Gece</th><th className="p-3 text-right">Tutar</th><th className="p-3 text-right">Önceden</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => <tr key={row.booking_id || `${row.guest_name}-${row.check_in}`} className="border-t">
                      <td className="p-3 font-medium">{row.guest_name}</td><td className="p-3">{row.room_number}</td><td className="p-3 whitespace-nowrap">{row.check_in} — {row.check_out}</td><td className="p-3">{row.status_label}</td><td className="p-3">{row.channel}</td><td className="p-3 text-right">{row.nights}</td><td className="p-3 text-right">{money(row.total_amount)}</td><td className="p-3 text-right">{row.lead_time_days == null ? '—' : `${row.lead_time_days} gün`}</td>
                    </tr>)}
                  </tbody>
                </table>
              </div> : <Empty />}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
};

const Metric = ({ title, value, caption, tone = 'text-foreground' }) => (
  <Card>
    <CardContent className="pt-4">
      <p className="text-xs text-muted-foreground">{title}</p>
      <p className={`mt-1 text-xl font-bold ${tone}`}>{value}</p>
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
