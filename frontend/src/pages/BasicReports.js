import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  BarChart3, TrendingUp, TrendingDown, Users, BedDouble, DollarSign,
  Calendar, ArrowUpRight, ArrowDownRight, Building2, Utensils,
  Wrench, FileText, RefreshCw, Hotel, CheckCircle2, Clock,
  AlertTriangle, Loader2, PieChart as PieChartIcon, Activity,
  Globe, CreditCard, Shield, UserCheck, ListChecks, ChevronRight,
  Eye, Download, Search, Filter, MapPin, Star, Receipt, BookOpen
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ComposedChart, LineChart, Line
} from 'recharts';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL;
const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#14B8A6'];
const ROOM_STATUS_COLORS = { available: '#10B981', occupied: '#3B82F6', dirty: '#F59E0B', maintenance: '#EF4444', out_of_order: '#6B7280' };

const formatCurrency = (val) => {
  if (val === undefined || val === null) return '₺0';
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(val);
};
const formatPercent = (val) => '%' + (val || 0).toFixed(1);
const calcChange = (current, prev) => {
  if (!prev || prev === 0) return { pct: 0, direction: 'neutral' };
  const pct = ((current - prev) / prev * 100).toFixed(1);
  return { pct: Math.abs(pct), direction: pct >= 0 ? 'up' : 'down' };
};

const KPICard = ({ title, value, prevValue, prevLabel, icon: Icon, color = 'blue' }) => {
  const change = calcChange(typeof value === 'number' ? value : 0, typeof prevValue === 'number' ? prevValue : 0);
  const colorMap = {
    blue: 'from-blue-500 to-blue-600', green: 'from-green-500 to-green-600',
    purple: 'from-purple-500 to-purple-600', amber: 'from-amber-500 to-amber-600',
    cyan: 'from-cyan-500 to-cyan-600', red: 'from-red-500 to-red-600'
  };
  return (
    <Card className="hover:shadow-lg transition-all border-0 shadow-sm">
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-3">
          <div className={'p-2 rounded-lg bg-gradient-to-r text-white ' + (colorMap[color] || colorMap.blue)}>
            <Icon className="w-4 h-4" />
          </div>
          {prevValue !== undefined && change.pct > 0 && (
            <span className={'text-xs font-semibold flex items-center gap-0.5 px-2 py-0.5 rounded-full ' + (change.direction === 'up' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700')}>
              {change.direction === 'up' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
              {change.pct}%
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">{title}</p>
        <p className="text-2xl font-bold text-gray-900 mt-1">{typeof value === 'number' ? (title.toLowerCase().includes('gelir') || title.toLowerCase().includes('adr') || title.toLowerCase().includes('rev') ? formatCurrency(value) : value) : value}</p>
        {prevLabel && <p className="text-[10px] text-gray-400 mt-1">{prevLabel}</p>}
      </CardContent>
    </Card>
  );
};

const CustomTooltip = ({ active, payload, label, formatter }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white p-3 border border-gray-200 rounded-lg shadow-lg text-xs">
        <p className="font-semibold text-gray-800 mb-1">{label}</p>
        {payload.map((entry, idx) => (
          <p key={idx} style={{ color: entry.color }} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: entry.color }}></span>
            {entry.name}: {formatter ? formatter(entry.value) : entry.value}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

const MENU_ITEMS = [
  { id: 'insights', label: 'Insights', icon: Star, desc: 'Özet Yönetici Raporu' },
  { id: 'gelir', label: 'Gelir', icon: DollarSign, desc: 'Gelir analizi ve trend' },
  { id: 'doluluk', label: 'Doluluk Oranı', icon: BedDouble, desc: 'Doluluk raporları' },
  { id: 'ulke', label: 'Ülke Bazlı', icon: Globe, desc: 'Milliyet dağılımı' },
  { id: 'konaklama', label: 'Konaklama Türü', icon: Hotel, desc: 'Oda tipi analizi' },
  { id: 'odemeler', label: 'Ödemeler', icon: CreditCard, desc: 'Ödeme yöntemleri' },
  { id: 'oda_gelirleri', label: 'Oda Gelirleri', icon: Receipt, desc: 'Oda tipi gelir' },
  { id: 'misafir', label: 'Misafir Listesi', icon: Users, desc: 'Tüm misafirler' },
  { id: 'resmi_liste', label: 'Resmi Müşteri Listesi', icon: FileText, desc: 'Resmi kayıtlar' },
  { id: 'polis', label: 'Polis Listesi', icon: Shield, desc: 'Emniyet bildirimi' },
  { id: 'departmanlar', label: 'Departmanlar', icon: Building2, desc: 'Departman raporları' },
  { id: 'kaynaklar', label: 'Kaynaklar', icon: PieChartIcon, desc: 'Rezervasyon kaynakları' },
];

const BasicReports = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSection, setActiveSection] = useState('insights');
  const [searchGuest, setSearchGuest] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(BACKEND_URL + '/api/reports/basic-dashboard', { headers: { 'Authorization': 'Bearer ' + token } });
      if (!res.ok) throw new Error('Veri yüklenemedi');
      setData(await res.json());
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="flex items-center justify-center min-h-[60vh]"><Loader2 className="w-8 h-8 animate-spin text-blue-600" /></div>
    </Layout>
  );

  if (error) return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="p-6"><Card className="border-red-200 bg-red-50"><CardContent className="p-6 text-center"><AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-3" /><p className="text-red-700">{error}</p><Button onClick={fetchData} className="mt-4" variant="outline"><RefreshCw className="w-4 h-4 mr-2" />Tekrar Dene</Button></CardContent></Card></div>
    </Layout>
  );

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

  const roomStatusData = Object.entries(roomStatus).filter(([,v]) => v > 0).map(([key, value]) => ({
    name: key === 'available' ? 'Müsait' : key === 'occupied' ? 'Dolu' : key === 'dirty' ? 'Kirli' : key === 'maintenance' ? 'Bakım' : 'Devre Dışı',
    value, color: ROOM_STATUS_COLORS[key] || '#6B7280'
  }));
  const roomTypeData = Object.entries(roomTypeOcc).map(([key, val]) => ({ name: key, total: val.total, occupied: val.occupied, occupancy: val.occupancy, revenue: val.revenue }));
  const countryData = Object.entries(countryDist).sort((a,b) => b[1] - a[1]).map(([key, value]) => ({ name: key, count: value }));
  const paymentData = Object.entries(payments.by_method || {}).map(([key, value]) => ({
    name: key === 'credit_card' ? 'Kredi Kartı' : key === 'cash' ? 'Nakit' : key === 'bank_transfer' ? 'Havale/EFT' : key === 'debit_card' ? 'Banka Kartı' : key,
    value
  }));
  const sourceData = Object.entries(bookingSources.distribution || {}).map(([key, value]) => ({
    name: key === 'direct' ? 'Direkt' : key === 'ota' ? 'OTA' : key === 'corporate' ? 'Kurumsal' : key === 'walk_in' ? 'Walk-in' : key === 'booking_com' ? 'Booking.com' : key === 'company_direct' ? 'Şirket' : key,
    count: value, revenue: bookingSources.revenue?.[key] || 0
  }));

  const filteredGuests = guestList.filter(g => {
    if (!searchGuest) return true;
    const term = searchGuest.toLowerCase();
    return (g.guest_name || '').toLowerCase().includes(term) || (g.room_number || '').toString().includes(term) || (g.guest_email || '').toLowerCase().includes(term);
  });

  const revChange = calcChange(pc.month_revenue, pc.prev_month_revenue);

  const renderContent = () => {
    switch(activeSection) {
      case 'insights': return renderInsights();
      case 'insights_ozet': return renderInsightsOzet();
      case 'gelir': return renderGelir();
      case 'doluluk': return renderDoluluk();
      case 'ulke': return renderUlke();
      case 'konaklama': return renderKonaklama();
      case 'odemeler': return renderOdemeler();
      case 'oda_gelirleri': return renderOdaGelirleri();
      case 'misafir': return renderMisafirListesi();
      case 'resmi_liste': return renderResmiListe();
      case 'polis': return renderPolisListesi();
      case 'departmanlar': return renderDepartmanlar();
      case 'kaynaklar': return renderKaynaklar();
      default: return renderInsights();
    }
  };

  const renderInsights = () => (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div><h2 className="text-xl font-bold text-gray-900">Insights</h2>
        <p className="text-sm text-gray-500">Verilerinizle daha akıllı iş kararları alın. Ham verileri eyleme dönüştürülebilir bilgilere çevirin.</p></div>
        <Badge className="bg-green-100 text-green-700 border-green-200">Canlı</Badge>
      </div>

      {/* Yönetici Raporları */}
      <div>
        <h3 className="text-base font-semibold text-gray-800 mb-1">Yönetici</h3>
        <p className="text-xs text-gray-500 mb-3">Otel yöneticileri için temel KPI'ları takip edin, trend performansı değerlendirin ve stratejik kararlar alın.</p>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          <button onClick={() => setActiveSection('insights_ozet')} className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-blue-300 transition-all group">
            <div className="flex items-center gap-2 mb-2"><Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-600 border-blue-200">Geçmiş ve Uzman</Badge><Eye className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-500" /></div>
            <h4 className="font-semibold text-gray-900 text-sm">Özet Yönetici Raporu</h4>
            <p className="text-xs text-gray-500 mt-1">Temel KPI'ları takip etmek için oluşturulmuştur. Toplam Gelir, ADR, RevPar, Doluluk Oranı ve daha fazlası.</p>
          </button>
          <button onClick={() => setActiveSection('doluluk')} className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-blue-300 transition-all group">
            <div className="flex items-center gap-2 mb-2"><Badge variant="outline" className="text-[10px] bg-green-50 text-green-600 border-green-200">Geçmiş ve Tahmin</Badge><Eye className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-500" /></div>
            <h4 className="font-semibold text-gray-900 text-sm">Doluluk Oranı Raporu</h4>
            <p className="text-xs text-gray-500 mt-1">Seçilen tarih aralığına göre doluluk oranlarını karşılaştırma yapar. Oda tipine göre detaylı kırılım sunar.</p>
          </button>
          <button onClick={() => setActiveSection('gelir')} className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-blue-300 transition-all group">
            <div className="flex items-center gap-2 mb-2"><Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-600 border-purple-200">Hedef</Badge><Eye className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-500" /></div>
            <h4 className="font-semibold text-gray-900 text-sm">Hedef Raporu</h4>
            <p className="text-xs text-gray-500 mt-1">Gelir hedeflerinizi ve gerçekleşen performansı karşılaştırın. Haftalık, aylık ve yıllık hedef takibi.</p>
          </button>
        </div>
      </div>

      {/* Karşılaştırma Raporları */}
      <div>
        <h3 className="text-base font-semibold text-gray-800 mb-1">Karşılaştırma</h3>
        <p className="text-xs text-gray-500 mb-3">Performans karşılaştırmaları ile iş stratejinizi güçlendirin.</p>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
          <button onClick={() => setActiveSection('kaynaklar')} className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-blue-300 transition-all group">
            <div className="flex items-center gap-2 mb-2"><Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-600 border-amber-200">Pickup</Badge><Eye className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-500" /></div>
            <h4 className="font-semibold text-gray-900 text-sm">Pickup Raporu</h4>
            <p className="text-xs text-gray-500 mt-1">Rezervasyon akış hızını ve kanal performansını analiz edin. Kaynak bazlı gelir karşılaştırması.</p>
          </button>
          <button onClick={() => setActiveSection('oda_gelirleri')} className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-blue-300 transition-all group">
            <div className="flex items-center gap-2 mb-2"><Badge variant="outline" className="text-[10px] bg-cyan-50 text-cyan-600 border-cyan-200">Geçmiş ve Tahmin</Badge><Eye className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-500" /></div>
            <h4 className="font-semibold text-gray-900 text-sm">Geçmiş ve Tutundurma Raporu</h4>
            <p className="text-xs text-gray-500 mt-1">Oda tipi bazlı gelir analizi ve tutundurma raporu. Geçmiş performans karşılaştırması.</p>
          </button>
          <button onClick={() => setActiveSection('ulke')} className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:shadow-md hover:border-blue-300 transition-all group">
            <div className="flex items-center gap-2 mb-2"><Badge variant="outline" className="text-[10px] bg-red-50 text-red-600 border-red-200">Pace</Badge><Eye className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-500" /></div>
            <h4 className="font-semibold text-gray-900 text-sm">Rezervasyon Akış Hızı Raporu</h4>
            <p className="text-xs text-gray-500 mt-1">Ülke bazlı misafir dağılımı ve akış hızı analizi. Milliyet trendlerini takip edin.</p>
          </button>
        </div>
      </div>

      {/* Özet Yönetici Dashboard */}
      <Card className="border-blue-100 bg-blue-50/30">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div><CardTitle className="text-base">Özet Yönetici Raporu</CardTitle><CardDescription>Temel KPI'lar ve performans özeti • Son 30 gün</CardDescription></div>
            <Badge className="bg-green-100 text-green-700 border-green-200 text-xs">Yayınlandı</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            <KPICard title="Toplam Gelir" value={pc.month_revenue} prevValue={pc.prev_month_revenue} prevLabel={'Önceki ay: ' + formatCurrency(pc.prev_month_revenue)} icon={DollarSign} color="green" />
            <KPICard title="Ort. ADR" value={s.adr} prevValue={pc.prev_month_adr} prevLabel={'Önceki ay: ' + formatCurrency(pc.prev_month_adr)} icon={TrendingUp} color="blue" />
            <KPICard title="Toplam Geceleme" value={pc.month_bookings + ' Room Nights'} icon={BedDouble} color="purple" />
            <KPICard title="Toplam Rezervasyon" value={pc.month_bookings} prevValue={pc.prev_month_bookings} prevLabel={'Önceki ay: ' + (pc.prev_month_bookings || 0)} icon={BookOpen} color="cyan" />
            <KPICard title="RevPar" value={s.revpar} icon={BarChart3} color="amber" />
            <KPICard title="Doluluk Oranı" value={formatPercent(s.occupancy_percentage)} icon={Hotel} color="red" />
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <Card className="shadow-sm"><CardHeader className="pb-2"><CardTitle className="text-sm">Toplam Gelir & Rezervasyon Sayısı</CardTitle><div className="flex gap-2 mt-1"><button className="text-[10px] px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">Günlük</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Haftalık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Aylık</button></div></CardHeader>
              <CardContent><ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={data?.revenue_trend || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={3} />
                  <YAxis yAxisId="left" tick={{ fontSize: 10 }} tickFormatter={v => '₺' + (v/1000).toFixed(0) + 'K'} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
                  <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar yAxisId="right" dataKey="revenue" name="Toplam Gelir" fill="#3B82F6" opacity={0.6} radius={[2,2,0,0]} />
                  <Line yAxisId="left" type="monotone" dataKey="revenue" name="Trend" stroke="#F97316" strokeWidth={2} dot={{ r: 3, fill: '#F97316' }} />
                </ComposedChart>
              </ResponsiveContainer></CardContent>
            </Card>
            <Card className="shadow-sm"><CardHeader className="pb-2"><CardTitle className="text-sm">Ort. ADR & Toplam Geceleme</CardTitle><div className="flex gap-2 mt-1"><button className="text-[10px] px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">Günlük</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Haftalık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Aylık</button></div></CardHeader>
              <CardContent><ResponsiveContainer width="100%" height={260}>
                <BarChart data={data?.revenue_trend?.slice(-14) || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={v => '₺' + (v/1000).toFixed(0) + 'K'} />
                  <Tooltip content={<CustomTooltip formatter={formatCurrency} />} /><Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="revenue" name="Günlük Gelir" fill="#3B82F6" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer></CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>

      {/* Günlük Hareket Özeti */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Günlük Hareket Özeti</CardTitle><CardDescription>Bugünkü operasyonel veriler</CardDescription></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="p-3 bg-blue-50 rounded-lg text-center border border-blue-100"><ArrowUpRight className="w-5 h-5 text-blue-600 mx-auto mb-1" /><p className="text-2xl font-bold text-blue-700">{s.arrivals || 0}</p><p className="text-xs text-blue-600">Giriş</p></div>
            <div className="p-3 bg-amber-50 rounded-lg text-center border border-amber-100"><ArrowDownRight className="w-5 h-5 text-amber-600 mx-auto mb-1" /><p className="text-2xl font-bold text-amber-700">{s.departures || 0}</p><p className="text-xs text-amber-600">Çıkış</p></div>
            <div className="p-3 bg-green-50 rounded-lg text-center border border-green-100"><Users className="w-5 h-5 text-green-600 mx-auto mb-1" /><p className="text-2xl font-bold text-green-700">{s.in_house || 0}</p><p className="text-xs text-green-600">{t("pms.inHouse")}</p></div>
            <div className="p-3 bg-red-50 rounded-lg text-center border border-red-100"><AlertTriangle className="w-5 h-5 text-red-500 mx-auto mb-1" /><p className="text-2xl font-bold text-red-600">{s.no_shows || 0}</p><p className="text-xs text-red-500">No-Show</p></div>
            <div className="p-3 bg-gray-50 rounded-lg text-center border border-gray-200"><Calendar className="w-5 h-5 text-gray-500 mx-auto mb-1" /><p className="text-2xl font-bold text-gray-700">{s.cancellations || 0}</p><p className="text-xs text-gray-500">{t("common.cancel")}</p></div>
          </div>
        </CardContent>
      </Card>

      {/* Oda Durumu & Dönem Karşılaştırma */}
      <div className="grid md:grid-cols-3 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Oda Durumu</CardTitle></CardHeader>
          <CardContent><ResponsiveContainer width="100%" height={200}><PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} dataKey="value" paddingAngle={3}>{roomStatusData.map((entry, i) => (<Cell key={i} fill={entry.color} />))}</Pie><Tooltip /><Legend iconSize={8} wrapperStyle={{ fontSize: '11px' }} /></PieChart></ResponsiveContainer></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Doluluk Trendi (30 Gün)</CardTitle></CardHeader>
          <CardContent><ResponsiveContainer width="100%" height={200}>
            <AreaChart data={data?.occupancy_trend || []}>
              <defs><linearGradient id="occG" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} /><stop offset="95%" stopColor="#3B82F6" stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={5} />
              <YAxis tick={{ fontSize: 9 }} domain={[0, 100]} tickFormatter={v => '%' + v} />
              <Tooltip /><Area type="monotone" dataKey="occupancy" name="Doluluk" stroke="#3B82F6" fill="url(#occG)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Dönem Karşılaştırma</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="p-3 bg-blue-50 rounded-lg"><p className="text-xs text-blue-600 font-medium">Son 7 Gün</p><p className="text-lg font-bold text-blue-800">{formatCurrency(pc.week_revenue)}</p><p className="text-[10px] text-blue-500">{pc.week_bookings} rezervasyon</p></div>
            <div className="p-3 bg-green-50 rounded-lg"><p className="text-xs text-green-600 font-medium">Son 30 Gün</p><p className="text-lg font-bold text-green-800">{formatCurrency(pc.month_revenue)}</p><p className="text-[10px] text-green-500">{pc.month_bookings} rezervasyon</p></div>
            <div className="p-3 bg-purple-50 rounded-lg"><p className="text-xs text-purple-600 font-medium">Önceki 30 Gün</p><p className="text-lg font-bold text-purple-800">{formatCurrency(pc.prev_month_revenue)}</p><p className="text-[10px] text-purple-500">{pc.prev_month_bookings} rezervasyon</p></div>
          </CardContent>
        </Card>
      </div>
    </div>
  );

  const renderInsightsOzet = () => (
    <div className="space-y-6">
      <div className="flex items-center gap-2 mb-2">
        <button onClick={() => setActiveSection('insights')} className="text-blue-600 hover:text-blue-800 text-sm font-medium flex items-center gap-1"><ChevronRight className="w-3 h-3 rotate-180" />Insights</button>
        <ChevronRight className="w-3 h-3 text-gray-400" />
        <span className="text-sm text-gray-700 font-medium">Özet Yönetici Raporu</span>
      </div>
      <div className="flex items-center justify-between">
        <div><h2 className="text-xl font-bold text-gray-900">Özet Yönetici Raporu</h2><p className="text-sm text-gray-500">Bu dashboard temel KPI'ları takip etmek için oluşturulmuştur. Tarih filtresi müşterilerin konakladığı tarihe göre filtrelenir.</p></div>
        <Badge className="bg-green-100 text-green-700 border-green-200">Yayınlandı</Badge>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <KPICard title="Toplam Gelir" value={pc.month_revenue} prevValue={pc.prev_month_revenue} prevLabel={'vs. ÖA: ' + formatCurrency(pc.prev_month_revenue)} icon={DollarSign} color="green" />
        <KPICard title="Ort. ADR" value={s.adr} prevValue={pc.prev_month_adr} prevLabel={'vs. ÖA: ' + formatCurrency(pc.prev_month_adr)} icon={TrendingUp} color="blue" />
        <KPICard title="Toplam Geceleme" value={pc.month_bookings + ' Room Nights'} prevValue={pc.prev_month_bookings} prevLabel={'vs. ÖA: ' + (pc.prev_month_bookings || 0) + ' RN'} icon={BedDouble} color="purple" />
        <KPICard title="Toplam Rezervasyon Sayısı" value={pc.month_bookings} prevValue={pc.prev_month_bookings} prevLabel={'vs. ÖA: ' + (pc.prev_month_bookings || 0)} icon={BookOpen} color="cyan" />
        <KPICard title="RevPar" value={s.revpar} icon={BarChart3} color="amber" />
        <KPICard title="Doluluk Oranı" value={formatPercent(s.occupancy_percentage)} icon={Hotel} color="red" />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Toplam Gelir & Toplam Rezervasyon Sayısı</CardTitle><div className="flex gap-2 mt-1"><button className="text-[10px] px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">Günlük</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Haftalık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Aylık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Üç Aylık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Yıllık</button></div></CardHeader>
          <CardContent><ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={data?.revenue_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={3} />
              <YAxis yAxisId="left" tick={{ fontSize: 10 }} tickFormatter={v => '₺' + (v/1000).toFixed(0) + 'K'} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
              <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="right" dataKey="revenue" name="Toplam Rezervasyon Sayısı" fill="#3B82F6" opacity={0.6} radius={[2,2,0,0]} />
              <Line yAxisId="left" type="monotone" dataKey="revenue" name="Toplam Gelir" stroke="#F97316" strokeWidth={2.5} dot={{ r: 3.5, fill: '#F97316' }} />
            </ComposedChart>
          </ResponsiveContainer></CardContent>
        </Card>
        <Card><CardHeader className="pb-2"><CardTitle className="text-sm">Ort. ADR & Toplam Geceleme</CardTitle><div className="flex gap-2 mt-1"><button className="text-[10px] px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">Günlük</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Haftalık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Aylık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Üç Aylık</button><button className="text-[10px] px-2 py-0.5 rounded text-gray-400 hover:bg-gray-100">Yıllık</button></div></CardHeader>
          <CardContent><ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={data?.revenue_trend?.slice(-14) || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 10 }} tickFormatter={v => '₺' + (v/1000).toFixed(0) + 'K'} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
              <Tooltip content={<CustomTooltip formatter={formatCurrency} />} /><Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="right" dataKey="revenue" name="Toplam Geceleme" fill="#3B82F6" radius={[3,3,0,0]} />
              <Line yAxisId="left" type="monotone" dataKey="revenue" name="Ort. ADR" stroke="#F97316" strokeWidth={2} dot={{ r: 3, fill: '#F97316' }} />
            </ComposedChart>
          </ResponsiveContainer></CardContent>
        </Card>
      </div>
    </div>
  );

  const renderGelir = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900">Gelir Raporu</h2>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="Bugünkü Gelir" value={s.today_revenue} icon={DollarSign} color="green" />
        <KPICard title="Haftalık Gelir" value={pc.week_revenue} icon={Calendar} color="blue" />
        <KPICard title="Aylık Gelir" value={pc.month_revenue} prevValue={pc.prev_month_revenue} icon={TrendingUp} color="purple" />
        <KPICard title="F&B Geliri" value={s.fnb_revenue} icon={Utensils} color="amber" />
      </div>
      <Card><CardHeader><CardTitle className="text-sm">30 Günlük Gelir Trendi</CardTitle></CardHeader>
        <CardContent><ResponsiveContainer width="100%" height={350}>
          <AreaChart data={data?.revenue_trend || []}>
            <defs><linearGradient id="rg" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10B981" stopOpacity={0.3} /><stop offset="95%" stopColor="#10B981" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={2} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={v => '₺' + (v/1000).toFixed(0) + 'K'} />
            <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
            <Area type="monotone" dataKey="revenue" name={t("finance.revenue")} stroke="#10B981" fill="url(#rg)" strokeWidth={2.5} />
          </AreaChart>
        </ResponsiveContainer></CardContent>
      </Card>
      <div className="grid md:grid-cols-2 gap-4">
        <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200"><CardContent className="p-6">
          <h3 className="font-semibold text-blue-900 mb-3">Son 7 Gün</h3>
          <p className="text-3xl font-bold text-blue-800">{formatCurrency(pc.week_revenue)}</p>
          <p className="text-sm text-blue-600 mt-1">{pc.week_bookings} rezervasyon</p>
        </CardContent></Card>
        <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200"><CardContent className="p-6">
          <h3 className="font-semibold text-green-900 mb-3">Son 30 Gün</h3>
          <p className="text-3xl font-bold text-green-800">{formatCurrency(pc.month_revenue)}</p>
          <p className="text-sm text-green-600 mt-1">{pc.month_bookings} rezervasyon</p>
        </CardContent></Card>
      </div>
    </div>
  );

  const renderDoluluk = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between"><h2 className="text-xl font-bold text-gray-900">Doluluk Oranı Raporu</h2><Badge className="bg-blue-100 text-blue-700">Canlı</Badge></div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard title="Toplam Oda" value={s.total_rooms} icon={Hotel} color="blue" />
        <KPICard title="Dolu Oda" value={s.occupied_rooms} icon={BedDouble} color="green" />
        <KPICard title="Doluluk" value={formatPercent(s.occupancy_percentage)} icon={TrendingUp} color="purple" />
        <KPICard title="Müsait" value={(s.total_rooms||0) - (s.occupied_rooms||0)} icon={CheckCircle2} color="cyan" />
      </div>
      <Card><CardHeader><CardTitle className="text-sm">Doluluk Oranı (30 Gün)</CardTitle><CardDescription>Önceki ay ile karşılaştırma</CardDescription></CardHeader>
        <CardContent><ResponsiveContainer width="100%" height={350}>
          <ComposedChart data={data?.occupancy_trend || []}>
            <defs><linearGradient id="og" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3B82F6" stopOpacity={0.2} /><stop offset="95%" stopColor="#3B82F6" stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={2} />
            <YAxis yAxisId="left" domain={[0, 100]} tickFormatter={v => '%' + v} tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} /><Legend wrapperStyle={{ fontSize: 11 }} />
            <Area yAxisId="left" type="monotone" dataKey="occupancy" name="Doluluk %" stroke="#3B82F6" fill="url(#og)" strokeWidth={2} />
            <Bar yAxisId="right" dataKey="rooms_occupied" name="Dolu Oda" fill="#F97316" opacity={0.5} radius={[2,2,0,0]} />
          </ComposedChart>
        </ResponsiveContainer></CardContent>
      </Card>
      {roomTypeData.length > 0 && (
        <Card><CardHeader><CardTitle className="text-sm">Oda Tipine Göre Doluluk Oranı</CardTitle></CardHeader>
          <CardContent><div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="border-b bg-gray-50"><th className="text-left py-2 px-3 font-semibold text-gray-600">Oda Tipi</th><th className="text-center py-2 px-3 font-semibold text-gray-600">Doluluk(%)</th><th className="text-center py-2 px-3 font-semibold text-gray-600">{t("housekeeping.occupied")}</th><th className="text-center py-2 px-3 font-semibold text-gray-600">Toplam</th><th className="text-right py-2 px-3 font-semibold text-gray-600">{t("finance.revenue")}</th></tr></thead>
            <tbody>{roomTypeData.map((rt, i) => (
              <tr key={i} className="border-b hover:bg-gray-50"><td className="py-2.5 px-3 font-medium">{rt.name}</td><td className="py-2.5 px-3 text-center"><span className={'px-2 py-0.5 rounded-full text-xs font-semibold ' + (rt.occupancy > 70 ? 'bg-green-100 text-green-700' : rt.occupancy > 30 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700')}>{rt.occupancy}%</span></td><td className="py-2.5 px-3 text-center">{rt.occupied}</td><td className="py-2.5 px-3 text-center">{rt.total}</td><td className="py-2.5 px-3 text-right font-medium">{formatCurrency(rt.revenue)}</td></tr>
            ))}</tbody>
          </table></div></CardContent>
        </Card>
      )}
    </div>
  );

  const renderUlke = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900">Ülke Bazlı Misafir Dağılımı</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <Card><CardHeader><CardTitle className="text-sm">Milliyet Dağılımı</CardTitle></CardHeader>
          <CardContent>{countryData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}><PieChart><Pie data={countryData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="count" paddingAngle={3} label={({name, count}) => name + ': ' + count}>{countryData.map((_,i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart></ResponsiveContainer>
          ) : <div className="text-center py-12 text-gray-400"><Globe className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>Henüz milliyet verisi yok</p></div>}</CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm">Ülke Detayları</CardTitle></CardHeader>
          <CardContent>{countryData.length > 0 ? (
            <div className="space-y-2">{countryData.slice(0, 15).map((c, i) => {
              const total = countryData.reduce((a,b) => a + b.count, 0);
              const pct = total > 0 ? (c.count / total * 100).toFixed(1) : 0;
              return (<div key={i} className="flex items-center gap-3"><span className="w-3 h-3 rounded-full" style={{backgroundColor: COLORS[i % COLORS.length]}}></span><span className="flex-1 text-sm font-medium">{c.name}</span><span className="text-sm text-gray-500">{c.count} kişi</span><span className="text-xs text-gray-400 w-12 text-right">{pct}%</span></div>);
            })}</div>
          ) : <p className="text-gray-400 text-center py-12">Veri yok</p>}</CardContent>
        </Card>
      </div>
    </div>
  );

  const renderKonaklama = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900">Konaklama Türü Analizi</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <Card><CardHeader><CardTitle className="text-sm">Oda Tipi Dağılımı</CardTitle></CardHeader>
          <CardContent><ResponsiveContainer width="100%" height={300}><PieChart><Pie data={roomTypeData} cx="50%" cy="50%" outerRadius={100} dataKey="total" label={({name, total}) => name + ': ' + total}>{roomTypeData.map((_,i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer></CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm">Oda Tipi Doluluk</CardTitle></CardHeader>
          <CardContent><ResponsiveContainer width="100%" height={300}>
            <BarChart data={roomTypeData} layout="vertical"><CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" /><XAxis type="number" domain={[0, 100]} tickFormatter={v => v + '%'} tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} /><Tooltip /><Bar dataKey="occupancy" name="Doluluk %" fill="#8B5CF6" radius={[0,4,4,0]} /></BarChart>
          </ResponsiveContainer></CardContent>
        </Card>
      </div>
    </div>
  );

  const renderOdemeler = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900">Ödeme Raporu</h2>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <KPICard title="Toplam Ödenen" value={payments.total_paid} icon={CheckCircle2} color="green" />
        <KPICard title="Bekleyen Fatura" value={payments.total_pending} icon={Clock} color="amber" />
        <KPICard title="Ödeme Yöntemi" value={Object.keys(payments.by_method || {}).length + ' tür'} icon={CreditCard} color="blue" />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <Card><CardHeader><CardTitle className="text-sm">Ödeme Yöntemi Dağılımı</CardTitle></CardHeader>
          <CardContent>{paymentData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}><PieChart><Pie data={paymentData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" paddingAngle={3} label={({name, value}) => name + ': ' + formatCurrency(value)}>{paymentData.map((_,i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart></ResponsiveContainer>
          ) : <div className="text-center py-12 text-gray-400"><CreditCard className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>Henüz ödeme verisi yok</p></div>}</CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm">Ödeme Detayları</CardTitle></CardHeader>
          <CardContent>{paymentData.length > 0 ? (
            <div className="space-y-3">{paymentData.map((p, i) => (<div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"><div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full" style={{backgroundColor: COLORS[i % COLORS.length]}}></span><span className="font-medium text-sm">{p.name}</span></div><span className="font-bold text-sm">{formatCurrency(p.value)}</span></div>))}</div>
          ) : <p className="text-gray-400 text-center py-12">Veri yok</p>}</CardContent>
        </Card>
      </div>
    </div>
  );

  const renderOdaGelirleri = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900">Oda Gelirleri</h2>
      {roomTypeData.length > 0 ? (<>
        <Card><CardHeader><CardTitle className="text-sm">Oda Tipi Bazlı Gelir</CardTitle></CardHeader>
          <CardContent><ResponsiveContainer width="100%" height={300}>
            <BarChart data={roomTypeData}><CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={v => '₺' + (v/1000).toFixed(0) + 'K'} /><Tooltip content={<CustomTooltip formatter={formatCurrency} />} /><Bar dataKey="revenue" name={t("finance.revenue")} radius={[4,4,0,0]}>{roomTypeData.map((_,i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar></BarChart>
          </ResponsiveContainer></CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm">Oda Gelir Tablosu</CardTitle></CardHeader>
          <CardContent><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b bg-gray-50"><th className="text-left py-2 px-3 font-semibold text-gray-600">Oda Tipi</th><th className="text-center py-2 px-3 font-semibold text-gray-600">Oda Sayısı</th><th className="text-center py-2 px-3 font-semibold text-gray-600">{t("housekeeping.occupied")}</th><th className="text-center py-2 px-3 font-semibold text-gray-600">Doluluk</th><th className="text-right py-2 px-3 font-semibold text-gray-600">{t("finance.revenue")}</th><th className="text-right py-2 px-3 font-semibold text-gray-600">Oda Başı Gelir</th></tr></thead>
            <tbody>{roomTypeData.map((rt, i) => (<tr key={i} className="border-b hover:bg-gray-50"><td className="py-2.5 px-3 font-medium">{rt.name}</td><td className="py-2.5 px-3 text-center">{rt.total}</td><td className="py-2.5 px-3 text-center">{rt.occupied}</td><td className="py-2.5 px-3 text-center">{rt.occupancy}%</td><td className="py-2.5 px-3 text-right font-semibold">{formatCurrency(rt.revenue)}</td><td className="py-2.5 px-3 text-right text-gray-500">{rt.total > 0 ? formatCurrency(rt.revenue / rt.total) : '₺0'}</td></tr>))}</tbody>
          </table></div></CardContent>
        </Card>
      </>) : <Card><CardContent className="py-12 text-center text-gray-400"><Receipt className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>Henüz oda gelir verisi yok</p></CardContent></Card>}
    </div>
  );

  const renderGuestTable = (guests, title, showId = false) => (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h2 className="text-xl font-bold text-gray-900">{title}</h2><Badge variant="outline">{guests.length} kayıt</Badge></div>
      <div className="flex gap-2"><div className="relative flex-1"><Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" /><Input placeholder="Misafir ara..." value={searchGuest} onChange={e => setSearchGuest(e.target.value)} className="pl-9" /></div></div>
      <Card><CardContent className="p-0"><div className="overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="border-b bg-gray-50"><th className="text-left py-2.5 px-3 font-semibold text-gray-600">Misafir</th><th className="text-left py-2.5 px-3 font-semibold text-gray-600">Oda</th>{showId && <th className="text-left py-2.5 px-3 font-semibold text-gray-600">TC/Pasaport</th>}<th className="text-left py-2.5 px-3 font-semibold text-gray-600">Giriş</th><th className="text-left py-2.5 px-3 font-semibold text-gray-600">Çıkış</th><th className="text-left py-2.5 px-3 font-semibold text-gray-600">Durum</th><th className="text-right py-2.5 px-3 font-semibold text-gray-600">Tutar</th></tr></thead>
        <tbody>{(guests.length > 0 ? guests : []).map((g, i) => (
          <tr key={i} className="border-b hover:bg-gray-50"><td className="py-2 px-3"><div className="font-medium">{g.guest_name || '-'}</div><div className="text-xs text-gray-400">{g.guest_email || ''}</div></td><td className="py-2 px-3">{g.room_number || '-'}</td>{showId && <td className="py-2 px-3 text-xs">{g.id_number || g.passport_number || '-'}</td>}<td className="py-2 px-3 text-xs">{g.check_in ? new Date(g.check_in).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3 text-xs">{g.check_out ? new Date(g.check_out).toLocaleDateString('tr-TR') : '-'}</td><td className="py-2 px-3"><span className={'text-xs px-2 py-0.5 rounded-full ' + (g.status === 'checked_in' ? 'bg-green-100 text-green-700' : g.status === 'checked_out' ? 'bg-gray-100 text-gray-600' : 'bg-blue-100 text-blue-700')}>{g.status === 'checked_in' ? 'Otelde' : g.status === 'checked_out' ? 'Çıkış' : 'Onaylı'}</span></td><td className="py-2 px-3 text-right font-medium">{formatCurrency(g.total_amount)}</td></tr>
        ))}{guests.length === 0 && <tr><td colSpan={showId ? 7 : 6} className="py-8 text-center text-gray-400">Kayıt bulunamadı</td></tr>}</tbody>
      </table></div></CardContent></Card>
    </div>
  );

  const renderMisafirListesi = () => renderGuestTable(filteredGuests, 'Misafir Listesi');
  const renderResmiListe = () => renderGuestTable(filteredGuests, 'Resmi Müşteri Listesi', true);
  const renderPolisListesi = () => renderGuestTable(filteredGuests, 'Polis Listesi (Emniyet Bildirimi)', true);

  const renderDepartmanlar = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900">Departman Raporları</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <Card><CardHeader><CardTitle className="text-sm flex items-center gap-2"><Users className="w-4 h-4 text-blue-500" />{t("nav.frontDesk")}</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-3 gap-3">
            <div className="p-3 bg-blue-50 rounded-lg text-center"><p className="text-2xl font-bold text-blue-700">{s.arrivals||0}</p><p className="text-xs text-blue-600">Giriş</p></div>
            <div className="p-3 bg-amber-50 rounded-lg text-center"><p className="text-2xl font-bold text-amber-700">{s.departures||0}</p><p className="text-xs text-amber-600">Çıkış</p></div>
            <div className="p-3 bg-green-50 rounded-lg text-center"><p className="text-2xl font-bold text-green-700">{s.in_house||0}</p><p className="text-xs text-green-600">{t("pms.inHouse")}</p></div>
          </div></CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-green-500" />Housekeeping</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-3 gap-3">
            <div className="p-3 bg-green-50 rounded-lg text-center"><p className="text-2xl font-bold text-green-700">{hk.completed||0}</p><p className="text-xs text-green-600">Tamam</p></div>
            <div className="p-3 bg-amber-50 rounded-lg text-center"><p className="text-2xl font-bold text-amber-700">{hk.pending||0}</p><p className="text-xs text-amber-600">Bekleyen</p></div>
            <div className="p-3 bg-blue-50 rounded-lg text-center"><p className="text-2xl font-bold text-blue-700">{hk.in_progress||0}</p><p className="text-xs text-blue-600">Devam</p></div>
          </div></CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm flex items-center gap-2"><Wrench className="w-4 h-4 text-orange-500" />Teknik Servis</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-orange-50 rounded-lg text-center"><p className="text-2xl font-bold text-orange-700">{maint.open||0}</p><p className="text-xs text-orange-600">Açık</p></div>
            <div className="p-3 bg-green-50 rounded-lg text-center"><p className="text-2xl font-bold text-green-700">{maint.completed_month||0}</p><p className="text-xs text-green-600">Tamamlanan</p></div>
          </div></CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm flex items-center gap-2"><DollarSign className="w-4 h-4 text-green-500" />Finans</CardTitle></CardHeader>
          <CardContent><div className="grid grid-cols-2 gap-3">
            <div className="p-3 bg-red-50 rounded-lg text-center"><p className="text-2xl font-bold text-red-700">{finance.pending_invoices||0}</p><p className="text-xs text-red-600">Bekleyen</p></div>
            <div className="p-3 bg-green-50 rounded-lg text-center"><p className="text-2xl font-bold text-green-700">{finance.paid_invoices_month||0}</p><p className="text-xs text-green-600">Ödenen</p></div>
          </div></CardContent>
        </Card>
      </div>
    </div>
  );

  const renderKaynaklar = () => (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900">Rezervasyon Kaynakları</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <Card><CardHeader><CardTitle className="text-sm">Kaynak Dağılımı</CardTitle></CardHeader>
          <CardContent>{sourceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}><PieChart><Pie data={sourceData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="count" paddingAngle={3} label={({name, count}) => name + ': ' + count}>{sourceData.map((_,i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: 11 }} /></PieChart></ResponsiveContainer>
          ) : <div className="text-center py-12 text-gray-400"><PieChartIcon className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>Veri yok</p></div>}</CardContent>
        </Card>
        <Card><CardHeader><CardTitle className="text-sm">Kaynak Bazlı Gelir</CardTitle></CardHeader>
          <CardContent>{sourceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}><BarChart data={sourceData}><CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={v => '₺' + (v/1000).toFixed(0) + 'K'} /><Tooltip content={<CustomTooltip formatter={formatCurrency} />} /><Bar dataKey="revenue" name={t("finance.revenue")} radius={[4,4,0,0]}>{sourceData.map((_,i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar></BarChart></ResponsiveContainer>
          ) : <div className="text-center py-12 text-gray-400"><BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>Veri yok</p></div>}</CardContent>
        </Card>
      </div>
    </div>
  );

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="flex min-h-[calc(100vh-64px)]">
        {/* Sidebar */}
        <aside className="w-64 bg-white border-r border-gray-200 flex-shrink-0 hidden lg:block">
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-center gap-2"><BarChart3 className="w-5 h-5 text-blue-600" /><h1 className="text-lg font-bold text-gray-900">{t("nav.reports")}</h1></div>
            <p className="text-xs text-gray-400 mt-1">{new Date().toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
          </div>
          <nav className="p-2 space-y-0.5 overflow-y-auto max-h-[calc(100vh-160px)]">
            {MENU_ITEMS.map(item => {
              const MenuIcon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button key={item.id} onClick={() => setActiveSection(item.id)} className={'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all text-sm ' + (isActive ? 'bg-blue-50 text-blue-700 font-semibold border-l-3 border-blue-600' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900')}>
                  <MenuIcon className={'w-4 h-4 ' + (isActive ? 'text-blue-600' : 'text-gray-400')} />
                  <span>{item.label}</span>
                </button>
              );
            })}
            <div className="border-t border-gray-100 pt-2 mt-2">
              <a href="/reports/builder" className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all text-sm text-blue-600 hover:bg-blue-50 font-medium" data-testid="report-builder-link">
                <ListChecks className="w-4 h-4 text-blue-500" />
                <span>Rapor Oluşturucu</span>
              </a>
            </div>
          </nav>
        </aside>

        {/* Mobile menu */}
        <div className="lg:hidden w-full">
          <div className="p-3 bg-white border-b flex items-center gap-2 overflow-x-auto">
            {MENU_ITEMS.map(item => {
              const MenuIcon = item.icon;
              return (
                <button key={item.id} onClick={() => setActiveSection(item.id)} className={'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap border transition-all ' + (activeSection === item.id ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300')}>
                  <MenuIcon className="w-3 h-3" />{item.label}
                </button>
              );
            })}
          </div>
          <div className="p-4">{renderContent()}</div>
        </div>

        {/* Main Content - Desktop */}
        <main className="flex-1 hidden lg:block">
          <div className="p-6 max-w-6xl">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <span>{t("nav.reports")}</span><ChevronRight className="w-3 h-3" />
                <span className="text-gray-700 font-medium">{MENU_ITEMS.find(m => m.id === activeSection)?.label}</span>
              </div>
              <Button onClick={fetchData} variant="outline" size="sm"><RefreshCw className="w-3.5 h-3.5 mr-1.5" />{t("common.refresh")}</Button>
            </div>
            {renderContent()}
          </div>
        </main>
      </div>
    </Layout>
  );
};

export default BasicReports;
