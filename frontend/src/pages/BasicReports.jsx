import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  BarChart3, DollarSign, BedDouble, Users, Globe, Hotel, CreditCard,
  Shield, FileText, Building2, Utensils, TrendingUp, AlertTriangle,
  ArrowLeftRight, Loader2, RefreshCw, ChevronRight, Search, Star,
  LayoutDashboard, Calendar, ArrowUpRight, ArrowDownRight, CheckCircle2,
  Clock, Activity, Wrench, Download, ListChecks, Eye, BookOpen, Receipt
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ComposedChart, Line
} from 'recharts';
import {
  COLORS, formatCurrency, formatNumber, formatPercent, calcChange,
  KPICard, CustomTooltip, SectionHeader, EmptyState, StatBox,
  ROOM_STATUS_COLORS, ROOM_STATUS_LABELS
} from './reports/ReportHelpers';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;

const REPORT_MENU = [
  { type: 'header', label: 'GENEL' },
  { id: 'overview', label: 'Genel Bakış', icon: LayoutDashboard, desc: 'Yönetici özet raporu' },
  { type: 'header', label: 'GELİR & FİNANS' },
  { id: 'revenue', label: 'Gelir Raporu', icon: DollarSign, desc: 'Gelir analizi ve trend' },
  { id: 'adr_revpar', label: 'ADR & RevPAR', icon: TrendingUp, desc: 'Performans metrikleri' },
  { id: 'period', label: 'Dönem Karşılaştırma', icon: Calendar, desc: 'Periyodik karşılaştırma' },
  { type: 'header', label: 'DOLULUK & KAPASİTE' },
  { id: 'occupancy', label: 'Doluluk Raporu', icon: BedDouble, desc: 'Doluluk oranları' },
  { id: 'room_types', label: 'Oda Tipi Analizi', icon: Hotel, desc: 'Oda tipi kırılımı' },
  { type: 'header', label: 'MİSAFİR' },
  { id: 'guests', label: 'Misafir Listesi', icon: Users, desc: 'Tüm misafirler' },
  { id: 'nationality', label: 'Milliyet Dağılımı', icon: Globe, desc: 'Ülke bazlı analiz' },
  { type: 'header', label: 'ÖN BÜRO' },
  { id: 'front_office', label: 'Giriş / Çıkış', icon: ArrowLeftRight, desc: 'Günlük hareketler' },
  { id: 'noshow', label: 'No-Show & İptaller', icon: AlertTriangle, desc: 'İptal ve no-show' },
  { type: 'header', label: 'OPERASYON' },
  { id: 'room_status', label: 'Oda Durumu', icon: Hotel, desc: 'Canlı oda durumu' },
  { id: 'housekeeping', label: 'Housekeeping', icon: CheckCircle2, desc: 'Temizlik raporları' },
  { type: 'header', label: 'KANAL & PAZAR' },
  { id: 'channels', label: 'Kanal Dağılımı', icon: Activity, desc: 'Kanal performansı' },
  { id: 'sources', label: 'Kaynak Analizi', icon: BarChart3, desc: 'Rezervasyon kaynakları' },
  { type: 'header', label: 'FİNANS & MUHASEBE' },
  { id: 'payments', label: 'Ödemeler', icon: CreditCard, desc: 'Ödeme yöntemleri' },
  { type: 'header', label: 'RESMİ RAPORLAR' },
  { id: 'official', label: 'Maliye Listesi', icon: FileText, desc: 'Resmi müşteri listesi' },
  { id: 'police', label: 'Polis Bildirimi', icon: Shield, desc: 'Emniyet bildirimi' },
  { type: 'header', label: 'DEPARTMANLAR' },
  { id: 'departments', label: 'Departman Özeti', icon: Building2, desc: 'Departman raporları' },
  { type: 'header', label: 'F&B' },
  { id: 'fnb', label: 'F&B Raporu', icon: Utensils, desc: 'Yiyecek & içecek' },
];

const BasicReports = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSection, setActiveSection] = useState('overview');
  const [searchGuest, setSearchGuest] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(BACKEND_URL + '/api/reports/basic-dashboard', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (!res.ok) throw new Error('Veri yuklenemedi');
      setData(await res.json());
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Loading state
  if (loading) return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-3" />
          <p className="text-sm text-gray-500">Raporlar yükleniyor...</p>
        </div>
      </div>
    </Layout>
  );

  // Error state
  if (error) return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="p-6">
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-6 text-center">
            <AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-3" />
            <p className="text-red-700">{error}</p>
            <Button onClick={fetchData} className="mt-4" variant="outline">
              <RefreshCw className="w-4 h-4 mr-2" />Tekrar Dene
            </Button>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );

  // Data extraction
  const s = data?.summary || {};
  const pc = data?.period_comparison || {};
  const roomTypes = data?.room_types || {};
  const roomTypeOcc = data?.room_type_occupancy || {};
  const roomStatus = data?.room_status || {};
  const bookingSources = data?.booking_sources || {};
  const countryDist = data?.country_distribution || {};
  const payments = data?.payments || {};
  const guestList = data?.guest_list || [];
  const hk = data?.housekeeping || {};
  const maint = data?.maintenance || {};
  const finance = data?.finance || {};

  // Derived data
  const roomStatusData = Object.entries(roomStatus).filter(([, v]) => v > 0).map(([key, value]) => ({
    name: ROOM_STATUS_LABELS[key] || key, value, color: ROOM_STATUS_COLORS[key] || '#6B7280'
  }));
  const roomTypeData = Object.entries(roomTypeOcc).map(([key, val]) => ({
    name: key, total: val.total, occupied: val.occupied, occupancy: val.occupancy, revenue: val.revenue
  }));
  const countryData = Object.entries(countryDist).sort((a, b) => b[1] - a[1]).map(([key, value]) => ({ name: key, count: value }));
  const paymentData = Object.entries(payments.by_method || {}).map(([key, value]) => ({
    name: key === 'credit_card' ? 'Kredi Karti' : key === 'cash' ? 'Nakit' : key === 'bank_transfer' ? 'Havale/EFT' : key === 'debit_card' ? 'Banka Karti' : key,
    value
  }));
  const sourceData = Object.entries(bookingSources.distribution || {}).map(([key, value]) => ({
    name: key === 'direct' ? 'Direkt' : key === 'ota' ? 'OTA' : key === 'corporate' ? 'Kurumsal' : key === 'walk_in' ? 'Walk-in' : key === 'booking_com' ? 'Booking.com' : key === 'company_direct' ? 'Sirket' : key,
    count: value, revenue: bookingSources.revenue?.[key] || 0
  }));

  const todayStr = new Date().toISOString().split('T')[0];
  const todayArrivals = guestList.filter(g => g.check_in?.startsWith(todayStr) && ['confirmed', 'guaranteed'].includes(g.status));
  const todayDepartures = guestList.filter(g => g.check_out?.startsWith(todayStr));
  const inHouseGuests = guestList.filter(g => g.status === 'checked_in');
  const noShowGuests = guestList.filter(g => g.status === 'no_show');
  const cancelledGuests = guestList.filter(g => g.status === 'cancelled');

  const filteredGuests = guestList.filter(g => {
    if (!searchGuest) return true;
    const term = searchGuest.toLowerCase();
    return (g.guest_name || '').toLowerCase().includes(term) || (g.room_number || '').toString().includes(term) || (g.guest_email || '').toLowerCase().includes(term);
  });

  // ─── RENDER SECTIONS ──────────────────────────────────

  const renderOverview = () => (
    <div className="space-y-6" data-testid="section-overview">
      <SectionHeader title="Genel Bakış - Yönetici Özeti" description="Temel KPI'lar ve günlük operasyonel özet" actions={<Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">Canlı</Badge>} />
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <KPICard title="Toplam Gelir (30 Gün)" value={pc.month_revenue} prevValue={pc.prev_month_revenue} prevLabel={'Önceki ay: ' + formatCurrency(pc.prev_month_revenue)} icon={DollarSign} color="green" />
        <KPICard title="Ortalama ADR" value={s.adr} prevValue={pc.prev_month_adr} prevLabel={'Önceki ay: ' + formatCurrency(pc.prev_month_adr)} icon={TrendingUp} color="blue" />
        <KPICard title="RevPAR" value={s.revpar} icon={BarChart3} color="amber" />
        <KPICard title="Doluluk Oranı" value={formatPercent(s.occupancy_percentage)} icon={Hotel} color="purple" />
        <KPICard title="Toplam Rezervasyon" value={pc.month_bookings} prevValue={pc.prev_month_bookings} prevLabel={'Önceki ay: ' + (pc.prev_month_bookings || 0)} icon={BookOpen} color="cyan" />
        <KPICard title="F&B Geliri (Bugün)" value={s.fnb_revenue} icon={Utensils} color="teal" />
      </div>

      {/* Gunluk Hareket */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Günlük Hareket Özeti</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <StatBox label="Giriş" value={s.arrivals || 0} color="blue" icon={ArrowUpRight} />
            <StatBox label="Çıkış" value={s.departures || 0} color="amber" icon={ArrowDownRight} />
            <StatBox label="Otelde" value={s.in_house || 0} color="green" icon={Users} />
            <StatBox label="No-Show" value={s.no_shows || 0} color="red" icon={AlertTriangle} />
            <StatBox label="İptal" value={s.cancellations || 0} color="gray" icon={Calendar} />
          </div>
        </CardContent>
      </Card>

      {/* Mini Charts */}
      <div className="grid md:grid-cols-3 gap-4">
        <Card className="shadow-sm">
          <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">Gelir Trendi (30 Gün)</CardTitle></CardHeader>
          <CardContent className="pb-3">
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={data?.revenue_trend || []}>
                <defs><linearGradient id="rvG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#059669" stopOpacity={0.3} /><stop offset="95%" stopColor="#059669" stopOpacity={0} /></linearGradient></defs>
                <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={5} />
                <YAxis tick={{ fontSize: 9 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
                <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                <Area type="monotone" dataKey="revenue" stroke="#059669" fill="url(#rvG)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">Doluluk Trendi (30 Gün)</CardTitle></CardHeader>
          <CardContent className="pb-3">
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={data?.occupancy_trend || []}>
                <defs><linearGradient id="ocG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563EB" stopOpacity={0.3} /><stop offset="95%" stopColor="#2563EB" stopOpacity={0} /></linearGradient></defs>
                <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={5} />
                <YAxis tick={{ fontSize: 9 }} domain={[0, 100]} tickFormatter={v => v + '%'} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="occupancy" stroke="#2563EB" fill="url(#ocG)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card className="shadow-sm">
          <CardHeader className="pb-1"><CardTitle className="text-xs text-gray-500">Oda Durumu</CardTitle></CardHeader>
          <CardContent className="pb-3">
            {roomStatusData.length > 0 ? (
              <ResponsiveContainer width="100%" height={160}>
                <PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={40} outerRadius={65} dataKey="value" paddingAngle={3}>
                  {roomStatusData.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Pie><Tooltip /><Legend iconSize={8} wrapperStyle={{ fontSize: '10px' }} /></PieChart>
              </ResponsiveContainer>
            ) : <EmptyState icon={Hotel} message="Oda verisi yok" />}
          </CardContent>
        </Card>
      </div>

      {/* Dönem Karşılaştırma */}
      <div className="grid md:grid-cols-3 gap-3">
        <div className="p-4 bg-blue-50 rounded-xl border border-blue-100">
          <p className="text-xs text-blue-600 font-medium mb-1">Son 7 Gün</p>
          <p className="text-2xl font-bold text-blue-800">{formatCurrency(pc.week_revenue)}</p>
          <p className="text-[11px] text-blue-500 mt-0.5">{pc.week_bookings} rezervasyon</p>
        </div>
        <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-100">
          <p className="text-xs text-emerald-600 font-medium mb-1">Son 30 Gün</p>
          <p className="text-2xl font-bold text-emerald-800">{formatCurrency(pc.month_revenue)}</p>
          <p className="text-[11px] text-emerald-500 mt-0.5">{pc.month_bookings} rezervasyon</p>
        </div>
        <div className="p-4 bg-violet-50 rounded-xl border border-violet-100">
          <p className="text-xs text-violet-600 font-medium mb-1">Önceki 30 Gün</p>
          <p className="text-2xl font-bold text-violet-800">{formatCurrency(pc.prev_month_revenue)}</p>
          <p className="text-[11px] text-violet-500 mt-0.5">{pc.prev_month_bookings} rezervasyon</p>
        </div>
      </div>
    </div>
  );

  const renderRevenue = () => (
    <div className="space-y-6" data-testid="section-revenue">
      <SectionHeader title="Gelir Raporu" description="Detaylı gelir analizi ve trendler" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="Bugünkü Gelir" value={s.today_revenue} icon={DollarSign} color="green" />
        <KPICard title="Haftalık Gelir" value={pc.week_revenue} icon={Calendar} color="blue" />
        <KPICard title="Aylık Gelir" value={pc.month_revenue} prevValue={pc.prev_month_revenue} icon={TrendingUp} color="purple" />
        <KPICard title="F&B Geliri" value={s.fnb_revenue} icon={Utensils} color="amber" />
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">30 Günlük Gelir Trendi</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={data?.revenue_trend || []}>
              <defs><linearGradient id="rvFull" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#059669" stopOpacity={0.2} /><stop offset="95%" stopColor="#059669" stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={2} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
              <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#059669" fill="url(#rvFull)" strokeWidth={2} />
              <Line type="monotone" dataKey="revenue" name="Trend" stroke="#EA580C" strokeWidth={2} dot={false} strokeDasharray="5 5" />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
      {roomTypeData.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Bazlı Gelir</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={roomTypeData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
                <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                <Bar dataKey="revenue" name="Gelir" radius={[4, 4, 0, 0]}>{roomTypeData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  );

  const renderAdrRevpar = () => (
    <div className="space-y-6" data-testid="section-adr-revpar">
      <SectionHeader title="ADR & RevPAR Analizi" description="Ortalama günlük oda fiyatı ve oda başına gelir metrikleri" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="ADR (Bugün)" value={s.adr} prevValue={pc.prev_month_adr} icon={TrendingUp} color="blue" />
        <KPICard title="RevPAR (Bugün)" value={s.revpar} icon={BarChart3} color="green" />
        <KPICard title="Dolu Oda" value={s.occupied_rooms} icon={BedDouble} color="purple" />
        <KPICard title="Toplam Oda" value={s.total_rooms} icon={Hotel} color="cyan" />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <Card className="bg-gradient-to-br from-blue-50 to-blue-100/50 border-blue-200">
          <CardContent className="p-6">
            <h3 className="text-sm font-semibold text-blue-900 mb-3">ADR Detay</h3>
            <div className="space-y-3">
              <div className="flex justify-between"><span className="text-sm text-blue-700">Bugünkü ADR</span><span className="font-bold text-blue-900">{formatCurrency(s.adr)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-blue-700">Önceki Ay ADR</span><span className="font-bold text-blue-900">{formatCurrency(pc.prev_month_adr)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-blue-700">Dolu Oda Sayısı</span><span className="font-bold text-blue-900">{s.occupied_rooms}</span></div>
              <div className="flex justify-between"><span className="text-sm text-blue-700">Bugünkü Oda Geliri</span><span className="font-bold text-blue-900">{formatCurrency(s.today_revenue)}</span></div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-gradient-to-br from-emerald-50 to-emerald-100/50 border-emerald-200">
          <CardContent className="p-6">
            <h3 className="text-sm font-semibold text-emerald-900 mb-3">RevPAR Detay</h3>
            <div className="space-y-3">
              <div className="flex justify-between"><span className="text-sm text-emerald-700">Bugünkü RevPAR</span><span className="font-bold text-emerald-900">{formatCurrency(s.revpar)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-emerald-700">Toplam Oda</span><span className="font-bold text-emerald-900">{s.total_rooms}</span></div>
              <div className="flex justify-between"><span className="text-sm text-emerald-700">Müsait Oda</span><span className="font-bold text-emerald-900">{(s.total_rooms || 0) - (s.occupied_rooms || 0)}</span></div>
              <div className="flex justify-between"><span className="text-sm text-emerald-700">Doluluk</span><span className="font-bold text-emerald-900">{formatPercent(s.occupancy_percentage)}</span></div>
            </div>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Son 14 Gün - Günlük Gelir Performansı</CardTitle></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data?.revenue_trend?.slice(-14) || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
              <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
              <Bar dataKey="revenue" name="Günlük Gelir" fill="#2563EB" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );

  const renderPeriod = () => {
    const revChange = calcChange(pc.month_revenue, pc.prev_month_revenue);
    const bookChange = calcChange(pc.month_bookings, pc.prev_month_bookings);
    return (
      <div className="space-y-6" data-testid="section-period">
        <SectionHeader title="Dönem Karşılaştırma" description="Haftalık, aylık ve önceki dönem karşılaştırmaları" />
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
          <Card className="border-l-4 border-l-blue-500"><CardContent className="p-4">
            <p className="text-[11px] text-gray-500 uppercase tracking-wide">Son 7 Gün Gelir</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.week_revenue)}</p>
            <p className="text-xs text-gray-400 mt-1">{pc.week_bookings} rezervasyon</p>
          </CardContent></Card>
          <Card className="border-l-4 border-l-emerald-500"><CardContent className="p-4">
            <p className="text-[11px] text-gray-500 uppercase tracking-wide">Son 30 Gün Gelir</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.month_revenue)}</p>
            <p className="text-xs text-gray-400 mt-1">{pc.month_bookings} rezervasyon</p>
          </CardContent></Card>
          <Card className="border-l-4 border-l-violet-500"><CardContent className="p-4">
            <p className="text-[11px] text-gray-500 uppercase tracking-wide">Önceki 30 Gün Gelir</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.prev_month_revenue)}</p>
            <p className="text-xs text-gray-400 mt-1">{pc.prev_month_bookings} rezervasyon</p>
          </CardContent></Card>
          <Card className="border-l-4 border-l-amber-500"><CardContent className="p-4">
            <p className="text-[11px] text-gray-500 uppercase tracking-wide">Geçen Yıl (Aynı Dönem)</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(pc.last_year_revenue)}</p>
            <p className="text-xs text-gray-400 mt-1">{pc.last_year_bookings} rezervasyon</p>
          </CardContent></Card>
        </div>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Gelir & Rezervasyon Trendi</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={data?.revenue_trend || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={3} />
                <YAxis yAxisId="left" tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
                <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="left" dataKey="revenue" name="Gelir" fill="#2563EB" opacity={0.6} radius={[2, 2, 0, 0]} />
                <Line yAxisId="left" type="monotone" dataKey="revenue" name="Trend" stroke="#EA580C" strokeWidth={2} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <div className="grid md:grid-cols-2 gap-4">
          <Card className={`border-2 ${Number(revChange.pct) > 0 && revChange.direction === 'up' ? 'border-emerald-200 bg-emerald-50/30' : 'border-rose-200 bg-rose-50/30'}`}>
            <CardContent className="p-5 text-center">
              <p className="text-sm font-medium text-gray-600">Gelir Değişimi (Önceki Aya Göre)</p>
              <p className={`text-3xl font-bold mt-2 ${revChange.direction === 'up' ? 'text-emerald-700' : 'text-rose-700'}`}>
                {revChange.direction === 'up' ? '+' : '-'}{revChange.pct}%
              </p>
              <p className="text-xs text-gray-500 mt-1">{formatCurrency(pc.month_revenue)} vs {formatCurrency(pc.prev_month_revenue)}</p>
            </CardContent>
          </Card>
          <Card className={`border-2 ${Number(bookChange.pct) > 0 && bookChange.direction === 'up' ? 'border-emerald-200 bg-emerald-50/30' : 'border-rose-200 bg-rose-50/30'}`}>
            <CardContent className="p-5 text-center">
              <p className="text-sm font-medium text-gray-600">Rezervasyon Değişimi (Önceki Aya Göre)</p>
              <p className={`text-3xl font-bold mt-2 ${bookChange.direction === 'up' ? 'text-emerald-700' : 'text-rose-700'}`}>
                {bookChange.direction === 'up' ? '+' : '-'}{bookChange.pct}%
              </p>
              <p className="text-xs text-gray-500 mt-1">{pc.month_bookings} vs {pc.prev_month_bookings}</p>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  };

  const renderOccupancy = () => (
    <div className="space-y-6" data-testid="section-occupancy">
      <SectionHeader title="Doluluk Raporu" description="Doluluk oranları ve trendler" actions={<Badge className="bg-blue-100 text-blue-700 border-blue-200">Canli</Badge>} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="Toplam Oda" value={s.total_rooms} icon={Hotel} color="blue" />
        <KPICard title="Dolu Oda" value={s.occupied_rooms} icon={BedDouble} color="green" />
        <KPICard title="Doluluk" value={formatPercent(s.occupancy_percentage)} icon={TrendingUp} color="purple" />
        <KPICard title="Müsait" value={(s.total_rooms || 0) - (s.occupied_rooms || 0)} icon={CheckCircle2} color="cyan" />
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Doluluk Oranı (30 Gün)</CardTitle><CardDescription>Dolu oda sayısı ve doluluk yüzdesi</CardDescription></CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={data?.occupancy_trend || []}>
              <defs><linearGradient id="occFull" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#2563EB" stopOpacity={0.2} /><stop offset="95%" stopColor="#2563EB" stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={2} />
              <YAxis yAxisId="left" domain={[0, 100]} tickFormatter={v => v + '%'} tick={{ fontSize: 10 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
              <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
              <Area yAxisId="left" type="monotone" dataKey="occupancy" name="Doluluk %" stroke="#2563EB" fill="url(#occFull)" strokeWidth={2} />
              <Bar yAxisId="right" dataKey="rooms_occupied" name="Dolu Oda" fill="#EA580C" opacity={0.5} radius={[2, 2, 0, 0]} />
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );

  const renderRoomTypes = () => (
    <div className="space-y-6" data-testid="section-room-types">
      <SectionHeader title="Oda Tipi Analizi" description="Oda tipine göre doluluk ve gelir kırılımı" />
      {roomTypeData.length > 0 ? (<>
        <div className="grid md:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Dağılımı</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart><Pie data={roomTypeData} cx="50%" cy="50%" outerRadius={90} dataKey="total" label={({ name, total }) => name + ': ' + total}>
                  {roomTypeData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie><Tooltip /></PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Doluluk</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={roomTypeData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis type="number" domain={[0, 100]} tickFormatter={v => v + '%'} tick={{ fontSize: 10 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={100} />
                  <Tooltip /><Bar dataKey="occupancy" name="Doluluk %" fill="#7C3AED" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Tipi Detay Tablosu</CardTitle></CardHeader>
          <CardContent>
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="room-type-table">
              <thead><tr className="border-b bg-gray-50">
                <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Oda Tipi</th>
                <th className="text-center py-2.5 px-3 font-semibold text-gray-600">Toplam</th>
                <th className="text-center py-2.5 px-3 font-semibold text-gray-600">Dolu</th>
                <th className="text-center py-2.5 px-3 font-semibold text-gray-600">Doluluk</th>
                <th className="text-right py-2.5 px-3 font-semibold text-gray-600">Gelir</th>
                <th className="text-right py-2.5 px-3 font-semibold text-gray-600">Oda Basi Gelir</th>
              </tr></thead>
              <tbody>{roomTypeData.map((rt, i) => (
                <tr key={i} className="border-b hover:bg-gray-50">
                  <td className="py-2.5 px-3 font-medium">{rt.name}</td>
                  <td className="py-2.5 px-3 text-center">{rt.total}</td>
                  <td className="py-2.5 px-3 text-center">{rt.occupied}</td>
                  <td className="py-2.5 px-3 text-center"><span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${rt.occupancy > 70 ? 'bg-emerald-100 text-emerald-700' : rt.occupancy > 30 ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'}`}>{rt.occupancy}%</span></td>
                  <td className="py-2.5 px-3 text-right font-medium">{formatCurrency(rt.revenue)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-500">{rt.total > 0 ? formatCurrency(rt.revenue / rt.total) : '-'}</td>
                </tr>
              ))}</tbody>
            </table></div>
          </CardContent>
        </Card>
      </>) : <Card><CardContent className="py-12"><EmptyState icon={Hotel} message="Oda tipi verisi yok" /></CardContent></Card>}
    </div>
  );

  const renderGuestTable = (guests, title, showId = false) => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <SectionHeader title={title} />
        <Badge variant="outline" className="h-6">{guests.length} kayit</Badge>
      </div>
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400 z-10" />
        <Input
          placeholder="Misafir, oda veya e-posta ara..."
          value={searchGuest}
          onChange={e => setSearchGuest(e.target.value)}
          className="pl-9 bg-white border-gray-300 text-gray-900 placeholder:text-gray-400 focus:border-blue-400 focus:ring-blue-200"
          data-testid="guest-search-input"
        />
      </div>
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="guest-table">
            <thead><tr className="border-b bg-gray-50">
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Misafir</th>
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Oda</th>
              {showId && <th className="text-left py-2.5 px-3 font-semibold text-gray-600">TC/Pasaport</th>}
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Giriş</th>
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Çıkış</th>
              <th className="text-left py-2.5 px-3 font-semibold text-gray-600">Durum</th>
              <th className="text-right py-2.5 px-3 font-semibold text-gray-600">Tutar</th>
            </tr></thead>
            <tbody>
              {guests.length > 0 ? guests.map((g, i) => (
                <tr key={i} className="border-b hover:bg-blue-50/30 transition-colors">
                  <td className="py-2 px-3"><div className="font-medium text-gray-900">{g.guest_name || '-'}</div><div className="text-[11px] text-gray-400">{g.guest_email || ''}</div></td>
                  <td className="py-2 px-3 font-medium">{g.room_number || '-'}</td>
                  {showId && <td className="py-2 px-3 text-xs font-mono">{g.id_number || g.passport_number || '-'}</td>}
                  <td className="py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td>
                  <td className="py-2 px-3 text-xs">{g.check_out ? new Date(g.check_out).toLocaleDateString('tr-TR') : '-'}</td>
                  <td className="py-2 px-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${g.status === 'checked_in' ? 'bg-emerald-100 text-emerald-700' : g.status === 'checked_out' ? 'bg-gray-100 text-gray-600' : g.status === 'no_show' ? 'bg-rose-100 text-rose-700' : g.status === 'cancelled' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>{g.status === 'checked_in' ? 'Otelde' : g.status === 'checked_out' ? 'Çıkış Yaptı' : g.status === 'no_show' ? 'No-Show' : g.status === 'cancelled' ? 'İptal' : 'Onayli'}</span></td>
                  <td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td>
                </tr>
              )) : <tr><td colSpan={showId ? 7 : 6} className="py-8 text-center text-gray-400">Kayıt bulunamadı</td></tr>}
            </tbody>
          </table></div>
        </CardContent>
      </Card>
    </div>
  );

  const renderGuests = () => (
    <div data-testid="section-guests">{renderGuestTable(filteredGuests, 'Misafir Listesi')}</div>
  );

  const renderNationality = () => {
    const totalGuests = countryData.reduce((a, b) => a + b.count, 0);
    return (
      <div className="space-y-6" data-testid="section-nationality">
        <SectionHeader title="Milliyet Dağılımı" description="Misafirlerin ülke bazlı dağılımı" />
        <div className="grid md:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Milliyet Dağılımı</CardTitle></CardHeader>
            <CardContent>
              {countryData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart><Pie data={countryData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="count" paddingAngle={3} label={({ name, count }) => name + ': ' + count}>
                    {countryData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart>
                </ResponsiveContainer>
              ) : <EmptyState icon={Globe} message="Milliyet verisi yok" />}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Ülke Detayları</CardTitle></CardHeader>
            <CardContent>
              {countryData.length > 0 ? (
                <div className="space-y-2 max-h-[300px] overflow-y-auto">{countryData.slice(0, 20).map((c, i) => {
                  const pct = totalGuests > 0 ? (c.count / totalGuests * 100).toFixed(1) : 0;
                  return (
                    <div key={i} className="flex items-center gap-3">
                      <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                      <span className="flex-1 text-sm font-medium truncate">{c.name}</span>
                      <span className="text-sm text-gray-500">{c.count} kisi</span>
                      <span className="text-xs text-gray-400 w-12 text-right">{pct}%</span>
                    </div>
                  );
                })}</div>
              ) : <p className="text-gray-400 text-center py-12">Veri yok</p>}
            </CardContent>
          </Card>
        </div>
      </div>
    );
  };

  const renderFrontOffice = () => (
    <div className="space-y-6" data-testid="section-front-office">
      <SectionHeader title="Giriş / Çıkış Raporu" description="Bugünkü giriş, çıkış ve oteldeki misafirler" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="Beklenen Giriş" value={s.arrivals || 0} icon={ArrowUpRight} color="blue" />
        <KPICard title="Beklenen Çıkış" value={s.departures || 0} icon={ArrowDownRight} color="amber" />
        <KPICard title="Otelde" value={s.in_house || 0} icon={Users} color="green" />
        <KPICard title="Müsait Oda" value={(s.total_rooms || 0) - (s.occupied_rooms || 0)} icon={CheckCircle2} color="cyan" />
      </div>
      {todayArrivals.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Bugunku Beklenen Girişler ({todayArrivals.length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="border-b bg-blue-50"><th className="text-left py-2 px-3 text-xs font-semibold text-blue-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-blue-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-blue-700">Çıkış</th><th className="text-right py-2 px-3 text-xs font-semibold text-blue-700">Tutar</th></tr></thead>
              <tbody>{todayArrivals.map((g, i) => (
                <tr key={i} className="border-b hover:bg-blue-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3 text-xs">{g.check_out ? new Date(g.check_out).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
              ))}</tbody>
            </table></div>
          </CardContent>
        </Card>
      )}
      {todayDepartures.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Bugünkü Çıkışlar ({todayDepartures.length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="border-b bg-amber-50"><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Durum</th><th className="text-right py-2 px-3 text-xs font-semibold text-amber-700">Tutar</th></tr></thead>
              <tbody>{todayDepartures.map((g, i) => (
                <tr key={i} className="border-b hover:bg-amber-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3"><span className={`text-xs px-2 py-0.5 rounded-full ${g.status === 'checked_out' ? 'bg-gray-100 text-gray-600' : 'bg-amber-100 text-amber-700'}`}>{g.status === 'checked_out' ? 'Çıkış Yaptı' : 'Bekliyor'}</span></td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
              ))}</tbody>
            </table></div>
          </CardContent>
        </Card>
      )}
      {todayArrivals.length === 0 && todayDepartures.length === 0 && (
        <Card><CardContent className="py-12"><EmptyState icon={ArrowLeftRight} message="Bugün için giriş/çıkış hareketi yok" /></CardContent></Card>
      )}
    </div>
  );

  const renderNoShow = () => (
    <div className="space-y-6" data-testid="section-noshow">
      <SectionHeader title="No-Show & İptaller" description="No-show ve iptal edilen rezervasyonlar" />
      <div className="grid grid-cols-2 gap-3">
        <KPICard title="No-Show" value={s.no_shows || 0} icon={AlertTriangle} color="red" />
        <KPICard title="İptal" value={s.cancellations || 0} icon={Calendar} color="amber" />
      </div>
      {noShowGuests.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-rose-700">No-Show Listesi ({noShowGuests.length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="border-b bg-rose-50"><th className="text-left py-2 px-3 text-xs font-semibold text-rose-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-rose-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-rose-700">Giriş Tarihi</th><th className="text-right py-2 px-3 text-xs font-semibold text-rose-700">Tutar</th></tr></thead>
              <tbody>{noShowGuests.map((g, i) => (
                <tr key={i} className="border-b hover:bg-rose-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
              ))}</tbody>
            </table></div>
          </CardContent>
        </Card>
      )}
      {cancelledGuests.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-amber-700">İptal Listesi ({cancelledGuests.length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="border-b bg-amber-50"><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Misafir</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Oda</th><th className="text-left py-2 px-3 text-xs font-semibold text-amber-700">Tarih</th><th className="text-right py-2 px-3 text-xs font-semibold text-amber-700">Tutar</th></tr></thead>
              <tbody>{cancelledGuests.map((g, i) => (
                <tr key={i} className="border-b hover:bg-amber-50/30"><td className="py-2 px-3 font-medium">{g.guest_name || '-'}</td><td className="py-2 px-3">{g.room_number || '-'}</td><td className="py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
              ))}</tbody>
            </table></div>
          </CardContent>
        </Card>
      )}
      {noShowGuests.length === 0 && cancelledGuests.length === 0 && (
        <Card><CardContent className="py-12"><EmptyState icon={AlertTriangle} message="No-show veya iptal kaydı yok" submessage="Bu dönem için herhangi bir no-show veya iptal bulunmuyor" /></CardContent></Card>
      )}
    </div>
  );

  const renderRoomStatus = () => (
    <div className="space-y-6" data-testid="section-room-status">
      <SectionHeader title="Oda Durumu" description="Canlı oda durumu özeti" actions={<Badge className="bg-emerald-100 text-emerald-700 border-emerald-200">Canli</Badge>} />
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Object.entries(roomStatus).map(([key, val]) => (
          <StatBox key={key} label={ROOM_STATUS_LABELS[key] || key} value={val} color={key === 'available' ? 'green' : key === 'occupied' ? 'blue' : key === 'dirty' ? 'amber' : key === 'maintenance' ? 'red' : 'gray'} />
        ))}
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Oda Durumu Dağılımı</CardTitle></CardHeader>
        <CardContent>
          {roomStatusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={60} outerRadius={110} dataKey="value" paddingAngle={3} label={({ name, value }) => name + ': ' + value}>
                {roomStatusData.map((e, i) => <Cell key={i} fill={e.color} />)}
              </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart>
            </ResponsiveContainer>
          ) : <EmptyState icon={Hotel} message="Oda durumu verisi yok" />}
        </CardContent>
      </Card>
    </div>
  );

  const renderHousekeeping = () => (
    <div className="space-y-6" data-testid="section-housekeeping">
      <SectionHeader title="Housekeeping Raporu" description="Temizlik operasyonları ve verimlilik" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard title="Tamamlanan" value={hk.completed || 0} icon={CheckCircle2} color="green" />
        <KPICard title="Bekleyen" value={hk.pending || 0} icon={Clock} color="amber" />
        <KPICard title="Devam Eden" value={hk.in_progress || 0} icon={Activity} color="blue" />
        <KPICard title="Haftalık Toplam" value={hk.total_week || 0} icon={ListChecks} color="purple" />
      </div>
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-sm">Housekeeping Performans Özeti</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-4">
            {['completed', 'pending', 'in_progress'].map(status => {
              const val = hk[status] || 0;
              const total = (hk.completed || 0) + (hk.pending || 0) + (hk.in_progress || 0);
              const pct = total > 0 ? (val / total * 100).toFixed(0) : 0;
              const colors = { completed: 'bg-emerald-500', pending: 'bg-amber-500', in_progress: 'bg-blue-500' };
              const labels = { completed: 'Tamamlanan', pending: 'Bekleyen', in_progress: 'Devam Eden' };
              return (
                <div key={status}>
                  <div className="flex justify-between text-sm mb-1"><span className="text-gray-600">{labels[status]}</span><span className="font-medium">{val} ({pct}%)</span></div>
                  <div className="w-full bg-gray-100 rounded-full h-2.5"><div className={`h-2.5 rounded-full ${colors[status]}`} style={{ width: pct + '%' }} /></div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );

  const renderChannels = () => (
    <div className="space-y-6" data-testid="section-channels">
      <SectionHeader title="Kanal Dagilimi" description="Rezervasyon kanalları ve performans analizi" />
      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Kaynak Dağılımı</CardTitle></CardHeader>
          <CardContent>
            {sourceData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart><Pie data={sourceData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="count" paddingAngle={3} label={({ name, count }) => name + ': ' + count}>
                  {sourceData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart>
              </ResponsiveContainer>
            ) : <EmptyState icon={Activity} message="Kanal verisi yok" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Kaynak Bazlı Gelir</CardTitle></CardHeader>
          <CardContent>
            {sourceData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={sourceData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={v => (v / 1000).toFixed(0) + 'K'} />
                  <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                  <Bar dataKey="revenue" name="Gelir" radius={[4, 4, 0, 0]}>{sourceData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <EmptyState icon={BarChart3} message="Kaynak gelir verisi yok" />}
          </CardContent>
        </Card>
      </div>
      {sourceData.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Kanal Detay Tablosu</CardTitle></CardHeader>
          <CardContent>
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="channel-table">
              <thead><tr className="border-b bg-gray-50">
                <th className="text-left py-2 px-3 font-semibold text-gray-600">Kanal</th>
                <th className="text-center py-2 px-3 font-semibold text-gray-600">Rezervasyon</th>
                <th className="text-right py-2 px-3 font-semibold text-gray-600">Gelir</th>
                <th className="text-right py-2 px-3 font-semibold text-gray-600">Ort. Tutar</th>
              </tr></thead>
              <tbody>{sourceData.map((src, i) => (
                <tr key={i} className="border-b hover:bg-gray-50">
                  <td className="py-2.5 px-3 flex items-center gap-2"><span className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} /><span className="font-medium">{src.name}</span></td>
                  <td className="py-2.5 px-3 text-center">{src.count}</td>
                  <td className="py-2.5 px-3 text-right font-medium">{formatCurrency(src.revenue)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-500">{src.count > 0 ? formatCurrency(src.revenue / src.count) : '-'}</td>
                </tr>
              ))}</tbody>
            </table></div>
          </CardContent>
        </Card>
      )}
    </div>
  );

  const renderSources = () => (
    <div className="space-y-6" data-testid="section-sources">
      <SectionHeader title="Kaynak Analizi" description="Rezervasyon kaynaklarının detaylı performans karşılaştırması" />
      {sourceData.length > 0 ? (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {sourceData.slice(0, 4).map((src, i) => (
              <Card key={i} className="border-l-4" style={{ borderLeftColor: COLORS[i % COLORS.length] }}>
                <CardContent className="p-4">
                  <p className="text-xs text-gray-500 font-medium">{src.name}</p>
                  <p className="text-xl font-bold text-gray-900 mt-1">{src.count} rez.</p>
                  <p className="text-sm text-gray-600 mt-0.5">{formatCurrency(src.revenue)}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Kaynak Karşılaştırması</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={sourceData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="count" name="Rezervasyon" fill="#2563EB" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      ) : <Card><CardContent className="py-12"><EmptyState icon={BarChart3} message="Kaynak verisi yok" /></CardContent></Card>}
    </div>
  );

  const renderPayments = () => (
    <div className="space-y-6" data-testid="section-payments">
      <SectionHeader title="Ödeme Raporu" description="Ödeme yöntemleri ve tutar dağılımı" />
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <KPICard title="Toplam Ödenen" value={payments.total_paid} icon={CheckCircle2} color="green" />
        <KPICard title="Bekleyen Fatura" value={payments.total_pending} icon={Clock} color="amber" />
        <KPICard title="Ödeme Yöntemi" value={(Object.keys(payments.by_method || {}).length) + ' tur'} icon={CreditCard} color="blue" />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Ödeme Yöntemi Dagilimi</CardTitle></CardHeader>
          <CardContent>
            {paymentData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart><Pie data={paymentData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" paddingAngle={3} label={({ name, value }) => name + ': ' + formatCurrency(value)}>
                  {paymentData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart>
              </ResponsiveContainer>
            ) : <EmptyState icon={CreditCard} message="Ödeme verisi yok" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Ödeme Detayları</CardTitle></CardHeader>
          <CardContent>
            {paymentData.length > 0 ? (
              <div className="space-y-3">{paymentData.map((p, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                  <div className="flex items-center gap-3">
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                    <span className="font-medium text-sm">{p.name}</span>
                  </div>
                  <span className="font-bold text-sm">{formatCurrency(p.value)}</span>
                </div>
              ))}</div>
            ) : <p className="text-gray-400 text-center py-12">Veri yok</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );

  const renderOfficial = () => (
    <div data-testid="section-official">
      <Card className="mb-5 border-amber-200 bg-amber-50/30">
        <CardContent className="p-4 flex items-start gap-3">
          <FileText className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-gray-900 text-sm">Resmi Müşteri Listesi (Maliye Raporu)</h4>
            <p className="text-xs text-gray-600 mt-0.5">Maliye veya resmi denetim geldiğinde, seçtiğiniz gün için otelde konaklayan tüm misafirlerin resmi listesini bu ekrandan alabilirsiniz. Liste TCKN/pasaport, oda, giriş-çıkış ve toplam tutarı içerir.</p>
          </div>
        </CardContent>
      </Card>
      {renderGuestTable(filteredGuests, 'Resmi Müşteri Listesi', true)}
    </div>
  );

  const renderPolice = () => (
    <div data-testid="section-police">
      <Card className="mb-5 border-blue-200 bg-blue-50/30">
        <CardContent className="p-4 flex items-start gap-3">
          <Shield className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-gray-900 text-sm">Polis Bildirimi (Emniyet Listesi)</h4>
            <p className="text-xs text-gray-600 mt-0.5">Emniyet Müdürlüğü'ne bildirilmesi gereken konaklayan misafir listesi. TC Kimlik No ve pasaport bilgileri dahildir.</p>
          </div>
        </CardContent>
      </Card>
      {renderGuestTable(filteredGuests, 'Polis Bildirimi Listesi', true)}
    </div>
  );

  const renderDepartments = () => (
    <div className="space-y-6" data-testid="section-departments">
      <SectionHeader title="Departman Özeti" description="Tüm departmanların günlük performans özeti" />
      <div className="grid md:grid-cols-2 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Users className="w-4 h-4 text-blue-500" />Ön Büro</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-3 gap-3">
            <StatBox label="Giriş" value={s.arrivals || 0} color="blue" />
            <StatBox label="Çıkış" value={s.departures || 0} color="amber" />
            <StatBox label="Otelde" value={s.in_house || 0} color="green" />
          </div></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-500" />Housekeeping</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-3 gap-3">
            <StatBox label="Tamam" value={hk.completed || 0} color="green" />
            <StatBox label="Bekleyen" value={hk.pending || 0} color="amber" />
            <StatBox label="Devam" value={hk.in_progress || 0} color="blue" />
          </div></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Wrench className="w-4 h-4 text-orange-500" />Teknik Servis</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-2 gap-3">
            <StatBox label="Acik" value={maint.open || 0} color="amber" />
            <StatBox label="Tamamlanan" value={maint.completed_month || 0} color="green" />
          </div></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><DollarSign className="w-4 h-4 text-emerald-500" />Finans</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-2 gap-3">
            <StatBox label="Bekleyen" value={finance.pending_invoices || 0} color="red" />
            <StatBox label="Odenen" value={finance.paid_invoices_month || 0} color="green" />
          </div></CardContent>
        </Card>
      </div>
    </div>
  );

  const renderFnB = () => (
    <div className="space-y-6" data-testid="section-fnb">
      <SectionHeader title="F&B Raporu" description="Yiyecek & İçecek gelir ve performans özeti" />
      <div className="grid grid-cols-2 gap-3">
        <KPICard title="Bugünkü F&B Geliri" value={s.fnb_revenue} icon={Utensils} color="amber" />
        <KPICard title="Toplam Gelir İçi Payı" value={s.today_revenue > 0 ? formatPercent((s.fnb_revenue || 0) / s.today_revenue * 100) : '%0'} icon={Activity} color="purple" />
      </div>
      <Card className="bg-gradient-to-br from-amber-50 to-amber-100/30 border-amber-200">
        <CardContent className="p-6 text-center">
          <Utensils className="w-12 h-12 text-amber-500 mx-auto mb-3" />
          <h3 className="text-lg font-bold text-gray-900">F&B Geliri</h3>
          <p className="text-3xl font-bold text-amber-700 mt-2">{formatCurrency(s.fnb_revenue)}</p>
          <p className="text-sm text-gray-500 mt-2">Bugünkü toplam yiyecek & içecek geliri</p>
          <div className="mt-4 grid grid-cols-2 gap-3 max-w-xs mx-auto">
            <div className="p-3 bg-white/70 rounded-lg"><p className="text-xs text-gray-500">Oda Geliri</p><p className="font-bold text-gray-900">{formatCurrency(s.today_revenue)}</p></div>
            <div className="p-3 bg-white/70 rounded-lg"><p className="text-xs text-gray-500">F&B Payi</p><p className="font-bold text-amber-700">{s.today_revenue > 0 ? ((s.fnb_revenue || 0) / s.today_revenue * 100).toFixed(1) : '0'}%</p></div>
          </div>
        </CardContent>
      </Card>
    </div>
  );

  // ─── CONTENT SWITCHER ─────────────────────────────────
  const renderContent = () => {
    switch (activeSection) {
      case 'overview': return renderOverview();
      case 'revenue': return renderRevenue();
      case 'adr_revpar': return renderAdrRevpar();
      case 'period': return renderPeriod();
      case 'occupancy': return renderOccupancy();
      case 'room_types': return renderRoomTypes();
      case 'guests': return renderGuests();
      case 'nationality': return renderNationality();
      case 'front_office': return renderFrontOffice();
      case 'noshow': return renderNoShow();
      case 'room_status': return renderRoomStatus();
      case 'housekeeping': return renderHousekeeping();
      case 'channels': return renderChannels();
      case 'sources': return renderSources();
      case 'payments': return renderPayments();
      case 'official': return renderOfficial();
      case 'police': return renderPolice();
      case 'departments': return renderDepartments();
      case 'fnb': return renderFnB();
      default: return renderOverview();
    }
  };

  const currentMenuItem = REPORT_MENU.find(m => m.id === activeSection);

  // ─── MAIN RENDER ──────────────────────────────────────
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="flex min-h-[calc(100vh-64px)]">
        {/* ── SIDEBAR (Desktop) ──────────────────────── */}
        <aside className="w-[260px] bg-white border-r border-gray-200 flex-shrink-0 hidden lg:flex lg:flex-col" data-testid="reports-sidebar">
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-blue-600" />
              <h1 className="text-base font-bold text-gray-900">Rapor Merkezi</h1>
            </div>
            <p className="text-[11px] text-gray-400 mt-1">{new Date().toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
          </div>
          <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
            {REPORT_MENU.map((item, idx) => {
              if (item.type === 'header') {
                return <p key={idx} className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-3 pt-4 pb-1">{item.label}</p>;
              }
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveSection(item.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-all text-[13px] ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-semibold border-l-[3px] border-blue-600 pl-[9px]'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                  data-testid={`report-nav-${item.id}`}
                >
                  <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-blue-600' : 'text-gray-400'}`} />
                  <span className="truncate">{item.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="p-3 border-t border-gray-100">
            <a
              href="/app/rapor-olusturucu"
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-blue-600 hover:bg-blue-50 font-medium transition-colors"
              data-testid="report-builder-link"
            >
              <ListChecks className="w-4 h-4" />
              <span>Rapor Oluşturucu</span>
            </a>
          </div>
        </aside>

        {/* ── MOBILE SELECTOR ────────────────────────── */}
        <div className="lg:hidden w-full">
          <div className="p-3 bg-white border-b sticky top-0 z-10">
            <div className="flex items-center gap-2 mb-2">
              <BarChart3 className="w-4 h-4 text-blue-600" />
              <span className="text-sm font-bold text-gray-900">Rapor Merkezi</span>
            </div>
            <select
              value={activeSection}
              onChange={e => setActiveSection(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white"
              data-testid="mobile-report-selector"
            >
              {REPORT_MENU.filter(m => m.id).map(m => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="p-4" data-testid="reports-mobile-content">{renderContent()}</div>
        </div>

        {/* ── MAIN CONTENT (Desktop) ─────────────────── */}
        <main className="flex-1 hidden lg:block overflow-y-auto" data-testid="reports-desktop-content">
          <div className="p-6 max-w-6xl">
            {/* Breadcrumb + Actions */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <span>Raporlar</span>
                <ChevronRight className="w-3 h-3" />
                <span className="text-gray-700 font-medium">{currentMenuItem?.label || 'Genel Bakış'}</span>
              </div>
              <Button onClick={fetchData} variant="outline" size="sm" data-testid="refresh-reports-btn">
                <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Yenile
              </Button>
            </div>
            {renderContent()}
          </div>
        </main>
      </div>
    </Layout>
  );
};

export default BasicReports;
