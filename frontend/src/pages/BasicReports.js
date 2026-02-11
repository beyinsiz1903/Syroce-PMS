import React, { useState, useEffect, useCallback } from 'react';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  BarChart3, TrendingUp, Users, BedDouble, DollarSign,
  Calendar, ArrowUpRight, ArrowDownRight, Building2, Utensils,
  Wrench, FileText, RefreshCw, Hotel, CheckCircle2, Clock,
  AlertTriangle, Loader2, PieChart as PieChartIcon, Activity
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  ComposedChart
} from 'recharts';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#84CC16'];
const ROOM_STATUS_COLORS = { available: '#10B981', occupied: '#3B82F6', dirty: '#F59E0B', maintenance: '#EF4444', out_of_order: '#6B7280' };

const formatCurrency = (val) => {
  if (val === undefined || val === null) return '₺0';
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(val);
};
const formatPercent = (val) => '%' + (val || 0).toFixed(1);

const StatCard = ({ title, value, subtitle, icon: Icon, color = 'blue' }) => {
  const cls = { blue: 'bg-blue-50 text-blue-600 border-blue-100', green: 'bg-green-50 text-green-600 border-green-100', amber: 'bg-amber-50 text-amber-600 border-amber-100', red: 'bg-red-50 text-red-600 border-red-100', purple: 'bg-purple-50 text-purple-600 border-purple-100', cyan: 'bg-cyan-50 text-cyan-600 border-cyan-100' };
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
            {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
          </div>
          <div className={'p-2.5 rounded-lg border ' + (cls[color] || cls.blue)}><Icon className="w-5 h-5" /></div>
        </div>
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

const BasicReports = ({ user, tenant, onLogout }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

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
      <div className="flex items-center justify-center min-h-[60vh]"><div className="text-center"><Loader2 className="w-8 h-8 animate-spin text-blue-600 mx-auto mb-3" /><p className="text-gray-500">Raporlar yükleniyor...</p></div></div>
    </Layout>
  );

  if (error) return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="p-6 max-w-4xl mx-auto"><Card className="border-red-200 bg-red-50"><CardContent className="p-6 text-center"><AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-3" /><p className="text-red-700 font-medium">{error}</p><Button onClick={fetchData} className="mt-4" variant="outline"><RefreshCw className="w-4 h-4 mr-2" /> Tekrar Dene</Button></CardContent></Card></div>
    </Layout>
  );

  const s = data?.summary || {};
  const pc = data?.period_comparison || {};
  const roomStatus = data?.room_status || {};
  const roomTypes = data?.room_types || {};
  const bookingSources = data?.booking_sources || {};
  const hk = data?.housekeeping || {};
  const maint = data?.maintenance || {};
  const finance = data?.finance || {};

  const roomStatusData = Object.entries(roomStatus).filter(([,v]) => v > 0).map(([key, value]) => ({
    name: key === 'available' ? 'Müsait' : key === 'occupied' ? 'Dolu' : key === 'dirty' ? 'Kirli' : key === 'maintenance' ? 'Bakım' : 'Devre Dışı',
    value, color: ROOM_STATUS_COLORS[key] || '#6B7280'
  }));
  const roomTypeData = Object.entries(roomTypes).map(([key, value]) => ({ name: key, value }));
  const sourceData = Object.entries(bookingSources.distribution || {}).map(([key, value]) => ({
    name: key === 'direct' ? 'Direkt' : key === 'ota' ? 'OTA' : key === 'corporate' ? 'Kurumsal' : key === 'walk_in' ? 'Walk-in' : key === 'booking_com' ? 'Booking.com' : key === 'company_direct' ? 'Şirket' : key,
    count: value, revenue: bookingSources.revenue?.[key] || 0
  }));

  const tabs = [
    { id: 'overview', label: 'Genel Bakış', icon: BarChart3 },
    { id: 'occupancy', label: 'Doluluk', icon: BedDouble },
    { id: 'revenue', label: 'Gelir', icon: DollarSign },
    { id: 'departments', label: 'Departmanlar', icon: Building2 },
    { id: 'sources', label: 'Kaynaklar', icon: PieChartIcon },
  ];

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="reports_basic">
      <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-gray-900 flex items-center gap-3"><BarChart3 className="w-7 h-7 text-blue-600" />Otel Raporları</h1>
            <p className="text-sm text-gray-500 mt-1">{new Date().toLocaleDateString('tr-TR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</p>
          </div>
          <Button onClick={fetchData} variant="outline" size="sm" className="self-start"><RefreshCw className="w-4 h-4 mr-2" /> Yenile</Button>
        </div>

        <div className="flex gap-1 bg-gray-100 p-1 rounded-lg overflow-x-auto">
          {tabs.map(tab => {
            const TabIcon = tab.icon;
            return (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={'flex items-center gap-1.5 px-3 py-2 rounded-md text-xs md:text-sm font-medium whitespace-nowrap transition-all ' + (activeTab === tab.id ? 'bg-white text-blue-700 shadow-sm' : 'text-gray-600 hover:text-gray-900 hover:bg-white/50')}>
                <TabIcon className="w-3.5 h-3.5" />{tab.label}
              </button>
            );
          })}
        </div>

        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
              <StatCard title="Doluluk" value={formatPercent(s.occupancy_percentage)} subtitle={(s.occupied_rooms || 0) + '/' + (s.total_rooms || 0) + ' oda'} icon={BedDouble} color="blue" />
              <StatCard title="Bugünkü Gelir" value={formatCurrency(s.today_revenue)} subtitle={'ADR: ' + formatCurrency(s.adr)} icon={DollarSign} color="green" />
              <StatCard title="RevPAR" value={formatCurrency(s.revpar)} subtitle="Müsait oda başına gelir" icon={TrendingUp} color="purple" />
              <StatCard title="F&B Geliri" value={formatCurrency(s.fnb_revenue)} subtitle="Bugünkü restoran geliri" icon={Utensils} color="amber" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Card className="bg-blue-50 border-blue-100"><CardContent className="p-3 text-center"><ArrowUpRight className="w-5 h-5 text-blue-600 mx-auto mb-1" /><p className="text-2xl font-bold text-blue-700">{s.arrivals || 0}</p><p className="text-xs text-blue-600">Giriş</p></CardContent></Card>
              <Card className="bg-amber-50 border-amber-100"><CardContent className="p-3 text-center"><ArrowDownRight className="w-5 h-5 text-amber-600 mx-auto mb-1" /><p className="text-2xl font-bold text-amber-700">{s.departures || 0}</p><p className="text-xs text-amber-600">Çıkış</p></CardContent></Card>
              <Card className="bg-green-50 border-green-100"><CardContent className="p-3 text-center"><Users className="w-5 h-5 text-green-600 mx-auto mb-1" /><p className="text-2xl font-bold text-green-700">{s.in_house || 0}</p><p className="text-xs text-green-600">Otelde</p></CardContent></Card>
              <Card className="bg-red-50 border-red-100"><CardContent className="p-3 text-center"><AlertTriangle className="w-5 h-5 text-red-500 mx-auto mb-1" /><p className="text-2xl font-bold text-red-600">{s.no_shows || 0}</p><p className="text-xs text-red-500">No-Show</p></CardContent></Card>
              <Card className="bg-gray-50 border-gray-100"><CardContent className="p-3 text-center"><Calendar className="w-5 h-5 text-gray-500 mx-auto mb-1" /><p className="text-2xl font-bold text-gray-700">{s.cancellations || 0}</p><p className="text-xs text-gray-500">İptal</p></CardContent></Card>
            </div>
            <div className="grid md:grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold flex items-center gap-2"><BedDouble className="w-4 h-4 text-blue-500" />Doluluk Trendi (30 Gün)</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={data?.occupancy_trend || []}>
                      <defs><linearGradient id="occGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} /><stop offset="95%" stopColor="#3B82F6" stopOpacity={0} /></linearGradient></defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={4} />
                      <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} tickFormatter={(v) => '%' + v} />
                      <Tooltip content={<CustomTooltip formatter={(v) => '%' + v} />} />
                      <Area type="monotone" dataKey="occupancy" name="Doluluk" stroke="#3B82F6" fill="url(#occGradient)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold flex items-center gap-2"><DollarSign className="w-4 h-4 text-green-500" />Gelir Trendi (30 Gün)</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data?.revenue_trend || []}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="label" tick={{ fontSize: 10 }} interval={4} />
                      <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => '₺' + (v/1000).toFixed(0) + 'K'} />
                      <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                      <Bar dataKey="revenue" name="Gelir" fill="#10B981" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>
            <div className="grid md:grid-cols-3 gap-4">
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold flex items-center gap-2"><Hotel className="w-4 h-4 text-blue-500" />Oda Durumu</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} dataKey="value" paddingAngle={3}>{roomStatusData.map((entry, i) => (<Cell key={i} fill={entry.color} />))}</Pie><Tooltip /><Legend iconSize={8} wrapperStyle={{ fontSize: '11px' }} /></PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold flex items-center gap-2"><BedDouble className="w-4 h-4 text-purple-500" />Oda Tipleri</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart><Pie data={roomTypeData} cx="50%" cy="50%" outerRadius={75} dataKey="value" label={({ name, value }) => name + ': ' + value}>{roomTypeData.map((_, i) => (<Cell key={i} fill={COLORS[i % COLORS.length]} />))}</Pie><Tooltip /></PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-sm font-semibold flex items-center gap-2"><Activity className="w-4 h-4 text-amber-500" />Dönem Karşılaştırma</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div className="p-3 bg-blue-50 rounded-lg"><p className="text-xs text-blue-600 font-medium">Son 7 Gün</p><p className="text-xl font-bold text-blue-800">{formatCurrency(pc.week_revenue)}</p><p className="text-xs text-blue-500">{pc.week_bookings} rezervasyon</p></div>
                  <div className="p-3 bg-green-50 rounded-lg"><p className="text-xs text-green-600 font-medium">Son 30 Gün</p><p className="text-xl font-bold text-green-800">{formatCurrency(pc.month_revenue)}</p><p className="text-xs text-green-500">{pc.month_bookings} rezervasyon</p></div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {activeTab === 'occupancy' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard title="Toplam Oda" value={s.total_rooms} icon={Hotel} color="blue" />
              <StatCard title="Dolu Oda" value={s.occupied_rooms} icon={BedDouble} color="green" />
              <StatCard title="Doluluk Oranı" value={formatPercent(s.occupancy_percentage)} icon={TrendingUp} color="purple" />
              <StatCard title="Müsait Oda" value={(s.total_rooms || 0) - (s.occupied_rooms || 0)} icon={CheckCircle2} color="cyan" />
            </div>
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><BarChart3 className="w-5 h-5 text-blue-500" />30 Günlük Doluluk Trendi</CardTitle><CardDescription>Günlük doluluk oranları ve dolu oda sayısı</CardDescription></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <ComposedChart data={data?.occupancy_trend || []}>
                    <defs><linearGradient id="occGrad2" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3B82F6" stopOpacity={0.2} /><stop offset="95%" stopColor="#3B82F6" stopOpacity={0} /></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={2} />
                    <YAxis yAxisId="left" tick={{ fontSize: 11 }} domain={[0, 100]} tickFormatter={(v) => '%' + v} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                    <Tooltip content={<CustomTooltip />} /><Legend />
                    <Area yAxisId="left" type="monotone" dataKey="occupancy" name="Doluluk %" stroke="#3B82F6" fill="url(#occGrad2)" strokeWidth={2} />
                    <Bar yAxisId="right" dataKey="rooms_occupied" name="Dolu Oda" fill="#10B981" opacity={0.6} radius={[2, 2, 0, 0]} />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <div className="grid md:grid-cols-2 gap-4">
              <Card>
                <CardHeader><CardTitle className="text-base flex items-center gap-2"><Hotel className="w-5 h-5 text-blue-500" />Oda Durumu Dağılımı</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart><Pie data={roomStatusData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="value" paddingAngle={3} label={({ name, value }) => name + ': ' + value}>{roomStatusData.map((entry, i) => (<Cell key={i} fill={entry.color} />))}</Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: '12px' }} /></PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-base flex items-center gap-2"><BedDouble className="w-5 h-5 text-purple-500" />Oda Tipi Dağılımı</CardTitle></CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={roomTypeData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis type="number" tick={{ fontSize: 11 }} />
                      <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
                      <Tooltip /><Bar dataKey="value" name="Oda Sayısı" fill="#8B5CF6" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {activeTab === 'revenue' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard title="Bugünkü Gelir" value={formatCurrency(s.today_revenue)} icon={DollarSign} color="green" />
              <StatCard title="ADR" value={formatCurrency(s.adr)} subtitle="Ortalama Günlük Ücret" icon={TrendingUp} color="blue" />
              <StatCard title="RevPAR" value={formatCurrency(s.revpar)} subtitle="Oda Başı Gelir" icon={BarChart3} color="purple" />
              <StatCard title="F&B Geliri" value={formatCurrency(s.fnb_revenue)} subtitle="Bugün" icon={Utensils} color="amber" />
            </div>
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><DollarSign className="w-5 h-5 text-green-500" />30 Günlük Gelir Trendi</CardTitle><CardDescription>Günlük toplam oda geliri</CardDescription></CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={350}>
                  <AreaChart data={data?.revenue_trend || []}>
                    <defs><linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#10B981" stopOpacity={0.3} /><stop offset="95%" stopColor="#10B981" stopOpacity={0} /></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={2} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => '₺' + (v/1000).toFixed(0) + 'K'} />
                    <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                    <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#10B981" fill="url(#revGrad)" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <div className="grid md:grid-cols-2 gap-4">
              <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
                <CardContent className="p-6">
                  <div className="flex items-center gap-3 mb-4"><div className="p-2 bg-blue-200 rounded-lg"><Calendar className="w-5 h-5 text-blue-700" /></div><div><h3 className="font-semibold text-blue-900">Son 7 Gün</h3><p className="text-xs text-blue-600">Haftalık performans</p></div></div>
                  <div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-blue-600">Toplam Gelir</p><p className="text-2xl font-bold text-blue-900">{formatCurrency(pc.week_revenue)}</p></div><div><p className="text-xs text-blue-600">Rezervasyon</p><p className="text-2xl font-bold text-blue-900">{pc.week_bookings}</p></div></div>
                </CardContent>
              </Card>
              <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
                <CardContent className="p-6">
                  <div className="flex items-center gap-3 mb-4"><div className="p-2 bg-green-200 rounded-lg"><Calendar className="w-5 h-5 text-green-700" /></div><div><h3 className="font-semibold text-green-900">Son 30 Gün</h3><p className="text-xs text-green-600">Aylık performans</p></div></div>
                  <div className="grid grid-cols-2 gap-4"><div><p className="text-xs text-green-600">Toplam Gelir</p><p className="text-2xl font-bold text-green-900">{formatCurrency(pc.month_revenue)}</p></div><div><p className="text-xs text-green-600">Rezervasyon</p><p className="text-2xl font-bold text-green-900">{pc.month_bookings}</p></div></div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {activeTab === 'departments' && (
          <div className="space-y-6">
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><Users className="w-5 h-5 text-blue-500" />Ön Büro (Front Office)</CardTitle><CardDescription>Bugünkü giriş-çıkış ve misafir hareketleri</CardDescription></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <div className="p-3 bg-blue-50 rounded-lg text-center"><p className="text-xs text-blue-600 font-medium">Giriş</p><p className="text-2xl font-bold text-blue-800">{s.arrivals || 0}</p></div>
                  <div className="p-3 bg-amber-50 rounded-lg text-center"><p className="text-xs text-amber-600 font-medium">Çıkış</p><p className="text-2xl font-bold text-amber-800">{s.departures || 0}</p></div>
                  <div className="p-3 bg-green-50 rounded-lg text-center"><p className="text-xs text-green-600 font-medium">Otelde</p><p className="text-2xl font-bold text-green-800">{s.in_house || 0}</p></div>
                  <div className="p-3 bg-red-50 rounded-lg text-center"><p className="text-xs text-red-600 font-medium">No-Show</p><p className="text-2xl font-bold text-red-800">{s.no_shows || 0}</p></div>
                  <div className="p-3 bg-gray-50 rounded-lg text-center"><p className="text-xs text-gray-600 font-medium">İptal</p><p className="text-2xl font-bold text-gray-800">{s.cancellations || 0}</p></div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><CheckCircle2 className="w-5 h-5 text-green-500" />Housekeeping (Kat Hizmetleri)</CardTitle><CardDescription>Son 7 gündeki görev durumu</CardDescription></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <div className="p-3 bg-green-50 rounded-lg text-center"><CheckCircle2 className="w-5 h-5 text-green-500 mx-auto mb-1" /><p className="text-2xl font-bold text-green-700">{hk.completed || 0}</p><p className="text-xs text-green-600">Tamamlanan</p></div>
                  <div className="p-3 bg-amber-50 rounded-lg text-center"><Clock className="w-5 h-5 text-amber-500 mx-auto mb-1" /><p className="text-2xl font-bold text-amber-700">{hk.pending || 0}</p><p className="text-xs text-amber-600">Bekleyen</p></div>
                  <div className="p-3 bg-blue-50 rounded-lg text-center"><Activity className="w-5 h-5 text-blue-500 mx-auto mb-1" /><p className="text-2xl font-bold text-blue-700">{hk.in_progress || 0}</p><p className="text-xs text-blue-600">Devam Eden</p></div>
                  <div className="p-3 bg-purple-50 rounded-lg text-center"><BarChart3 className="w-5 h-5 text-purple-500 mx-auto mb-1" /><p className="text-2xl font-bold text-purple-700">{hk.total_week || 0}</p><p className="text-xs text-purple-600">Toplam (7 Gün)</p></div>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={[{ name: 'Tamamlanan', value: hk.completed || 0 }, { name: 'Bekleyen', value: hk.pending || 0 }, { name: 'Devam Eden', value: hk.in_progress || 0 }]}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip />
                    <Bar dataKey="value" name="Görev" radius={[4, 4, 0, 0]}><Cell fill="#10B981" /><Cell fill="#F59E0B" /><Cell fill="#3B82F6" /></Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><Wrench className="w-5 h-5 text-orange-500" />Teknik Servis (Maintenance)</CardTitle><CardDescription>Bakım ve onarım durumu</CardDescription></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 bg-orange-50 rounded-lg text-center"><AlertTriangle className="w-6 h-6 text-orange-500 mx-auto mb-2" /><p className="text-3xl font-bold text-orange-700">{maint.open || 0}</p><p className="text-sm text-orange-600">Açık İş Emri</p></div>
                  <div className="p-4 bg-green-50 rounded-lg text-center"><CheckCircle2 className="w-6 h-6 text-green-500 mx-auto mb-2" /><p className="text-3xl font-bold text-green-700">{maint.completed_month || 0}</p><p className="text-sm text-green-600">Tamamlanan (30 Gün)</p></div>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><DollarSign className="w-5 h-5 text-green-500" />Finans</CardTitle><CardDescription>Fatura ve ödeme durumu</CardDescription></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 bg-red-50 rounded-lg text-center"><Clock className="w-6 h-6 text-red-500 mx-auto mb-2" /><p className="text-3xl font-bold text-red-700">{finance.pending_invoices || 0}</p><p className="text-sm text-red-600">Bekleyen Fatura</p></div>
                  <div className="p-4 bg-green-50 rounded-lg text-center"><CheckCircle2 className="w-6 h-6 text-green-500 mx-auto mb-2" /><p className="text-3xl font-bold text-green-700">{finance.paid_invoices_month || 0}</p><p className="text-sm text-green-600">Ödenen (30 Gün)</p></div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {activeTab === 'sources' && (
          <div className="space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <Card>
                <CardHeader><CardTitle className="text-base flex items-center gap-2"><PieChartIcon className="w-5 h-5 text-blue-500" />Rezervasyon Kaynağı Dağılımı</CardTitle><CardDescription>Son 30 gün</CardDescription></CardHeader>
                <CardContent>
                  {sourceData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart><Pie data={sourceData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="count" paddingAngle={3} label={({ name, count }) => name + ': ' + count}>{sourceData.map((_, i) => (<Cell key={i} fill={COLORS[i % COLORS.length]} />))}</Pie><Tooltip /><Legend iconSize={10} wrapperStyle={{ fontSize: '12px' }} /></PieChart>
                    </ResponsiveContainer>
                  ) : (<div className="text-center py-10 text-gray-400"><PieChartIcon className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>Henüz veri yok</p></div>)}
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle className="text-base flex items-center gap-2"><DollarSign className="w-5 h-5 text-green-500" />Kaynak Bazlı Gelir</CardTitle><CardDescription>Her kaynaktan elde edilen gelir</CardDescription></CardHeader>
                <CardContent>
                  {sourceData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={sourceData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => '₺' + (v/1000).toFixed(0) + 'K'} />
                        <Tooltip content={<CustomTooltip formatter={formatCurrency} />} />
                        <Bar dataKey="revenue" name="Gelir" radius={[4, 4, 0, 0]}>{sourceData.map((_, i) => (<Cell key={i} fill={COLORS[i % COLORS.length]} />))}</Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (<div className="text-center py-10 text-gray-400"><BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" /><p>Henüz veri yok</p></div>)}
                </CardContent>
              </Card>
            </div>
            {sourceData.length > 0 && (
              <Card>
                <CardHeader><CardTitle className="text-base flex items-center gap-2"><FileText className="w-5 h-5 text-gray-500" />Kaynak Detayları</CardTitle></CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="border-b border-gray-200"><th className="text-left py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Kaynak</th><th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Rezervasyon</th><th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Gelir</th><th className="text-right py-2 px-3 text-xs font-semibold text-gray-500 uppercase">Ort. Gelir</th></tr></thead>
                      <tbody>
                        {sourceData.map((src, i) => (
                          <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                            <td className="py-2.5 px-3 flex items-center gap-2"><span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: COLORS[i % COLORS.length] }}></span><span className="font-medium">{src.name}</span></td>
                            <td className="py-2.5 px-3 text-right">{src.count}</td>
                            <td className="py-2.5 px-3 text-right font-medium">{formatCurrency(src.revenue)}</td>
                            <td className="py-2.5 px-3 text-right text-gray-500">{src.count > 0 ? formatCurrency(src.revenue / src.count) : '₺0'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
};

export default BasicReports;
