import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  AlertTriangle, ArrowRight, BadgeDollarSign, BarChart3, Building2, CalendarDays,
  CheckCircle2, ChevronRight, CircleAlert, DoorOpen, Eye, FileBarChart, Hotel,
  Loader2, LogIn, RefreshCw, Search, ShieldCheck, Sparkles, Tags, UserPlus,
  WalletCards,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';
import { persistEnteredTenantContext } from '@/lib/adminTenantContext';

const number = new Intl.NumberFormat('tr-TR');
const percent = value => `%${Number(value || 0).toLocaleString('tr-TR', { maximumFractionDigits: 1 })}`;
const displayDate = value => {
  if (!value) return '—';
  const parsed = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
};
const displayTime = value => {
  if (!value) return 'Bilinmiyor';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'Bilinmiyor' : parsed.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
};

function addBreakdown(target, source) {
  Object.entries(source || {}).forEach(([currency, amount]) => {
    target[currency] = Number(((target[currency] || 0) + Number(amount || 0)).toFixed(2));
  });
  return target;
}

function dividedBreakdown(source, divisor) {
  return Object.fromEntries(Object.entries(source || {}).map(([currency, amount]) => [currency, divisor ? Number(amount || 0) / divisor : 0]));
}

function propertyAlerts(property) {
  const alerts = [];
  if (property.integrations?.channel_manager?.has_error) alerts.push({ priority: 'critical', label: 'Kanal bağlantısı hata veriyor' });
  if (property.open_folios > 0) alerts.push({ priority: 'high', label: `${property.open_folios} tahsilat bekleyen folyo` });
  if (property.housekeeping_pending > 0) alerts.push({ priority: 'medium', label: `${property.housekeeping_pending} temizlik görevi bekliyor` });
  if (property.out_of_order_rooms > 0) alerts.push({ priority: 'medium', label: `${property.out_of_order_rooms} oda hizmet dışı` });
  return alerts;
}

const priorityStyle = {
  critical: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200',
  high: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200',
  medium: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-200',
};

function KpiCard({ icon: Icon, label, value, detail, tone = 'blue' }) {
  const tones = {
    blue: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200',
    emerald: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200',
    violet: 'bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-200',
    amber: 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200',
    cyan: 'bg-cyan-50 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-200',
    rose: 'bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-200',
  };
  return <Card className="min-w-0 shadow-sm"><CardContent className="p-4"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p><p className="mt-2 truncate text-2xl font-bold tracking-tight text-slate-950 dark:text-slate-50">{value}</p><p className="mt-1 truncate text-xs text-slate-500">{detail}</p></div><span className={`rounded-xl p-2.5 ${tones[tone]}`}><Icon className="h-5 w-5" /></span></div></CardContent></Card>;
}

export default function MultiProperty({ embedded = false }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [platformData, setPlatformData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [propertyFilter, setPropertyFilter] = useState('all');
  const [selectedProperty, setSelectedProperty] = useState(null);
  const [switchingPropertyId, setSwitchingPropertyId] = useState('');
  const [team, setTeam] = useState(null);
  const [teamError, setTeamError] = useState('');
  const [savingUser, setSavingUser] = useState(false);
  const [userForm, setUserForm] = useState({ property_id: '', name: '', email: '', password: '', role: 'supervisor' });

  const loadTeam = useCallback(() => {
    axios.get('/platform/multi-property/team').then(({ data: result }) => {
      setTeam(result);
      setUserForm(current => ({ ...current, property_id: current.property_id || result.properties?.[0]?.property_id || '' }));
      setTeamError('');
    }).catch(requestError => {
      if (requestError?.response?.status !== 403) setTeamError('Zincir kullanıcıları yüklenemedi.');
    });
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [dashboardResult, platformResult] = await Promise.allSettled([
        axios.get('/multi-property/dashboard'),
        axios.get('/platform/multi-property/dashboard'),
      ]);
      if (dashboardResult.status !== 'fulfilled') throw dashboardResult.reason;
      setData(dashboardResult.value.data);
      setPlatformData(platformResult.status === 'fulfilled' ? platformResult.value.data : null);
    } catch (requestError) {
      setError(requestError?.response?.data?.detail || 'Zincir operasyon verileri yüklenemedi.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); loadTeam(); }, [loadData, loadTeam]);

  const properties = useMemo(() => {
    const revenueById = new Map((platformData?.revenue?.properties || []).map(item => [item.property_id, item]));
    return (data?.properties || []).map(item => ({ ...item, period: revenueById.get(item.property_id) || {} }));
  }, [data, platformData]);

  const filteredProperties = useMemo(() => properties.filter(property => {
    const matchesFilter = propertyFilter === 'all' || property.property_id === propertyFilter;
    const text = `${property.property_name} ${property.location || ''}`.toLocaleLowerCase('tr-TR');
    return matchesFilter && text.includes(query.trim().toLocaleLowerCase('tr-TR'));
  }), [properties, propertyFilter, query]);

  const metrics = useMemo(() => {
    const revenue = {};
    const roomRevenue = {};
    let occupied = 0;
    let rooms = 0;
    properties.forEach(property => {
      addBreakdown(revenue, property.today_revenue_by_currency);
      addBreakdown(roomRevenue, property.room_revenue_by_currency);
      occupied += Number(property.occupied_rooms || 0);
      rooms += Number(property.total_rooms || 0);
    });
    return { revenue, adr: dividedBreakdown(roomRevenue, occupied), revpar: dividedBreakdown(roomRevenue, rooms), occupied, rooms };
  }, [properties]);
  const businessDatesAligned = data?.business_dates_aligned !== false;
  const businessDateLabel = businessDatesAligned
    ? `İş günü: ${displayDate(data?.business_date)}`
    : `${data?.business_dates?.length || 0} farklı PMS iş günü`;

  const alerts = useMemo(() => {
    const central = (platformData?.alerts?.alerts || []).map(alert => ({ ...alert, label: alert.message }));
    const local = properties.flatMap(property => propertyAlerts(property).map((alert, index) => ({ ...alert, id: `${property.property_id}-${alert.priority}-${index}`, property_id: property.property_id, property_name: property.property_name })));
    const unique = new Map();
    [...central, ...local].forEach(alert => unique.set(`${alert.property_id}-${alert.type || alert.label}`, alert));
    const rank = { critical: 0, high: 1, medium: 2 };
    return [...unique.values()].sort((a, b) => (rank[a.priority] ?? 3) - (rank[b.priority] ?? 3));
  }, [platformData, properties]);

  const createChainUser = async event => {
    event.preventDefault();
    setSavingUser(true);
    setTeamError('');
    try {
      await axios.post('/platform/multi-property/team', userForm);
      toast.success('Zincir kullanıcısı oluşturuldu');
      setUserForm(current => ({ ...current, name: '', email: '', password: '' }));
      loadTeam();
    } catch (requestError) {
      setTeamError(requestError?.response?.data?.detail || 'Kullanıcı oluşturulamadı.');
    } finally {
      setSavingUser(false);
    }
  };

  const enterPropertyWorkspace = async property => {
    if (!property?.property_id) return;
    if (property.property_id === data?.current_property_id) {
      navigate('/app/dashboard');
      return;
    }
    setSwitchingPropertyId(property.property_id);
    try {
      const response = await axios.post(`/admin/tenants/${property.property_id}/context`);
      persistEnteredTenantContext(response.data);
      toast.success(`${property.property_name} çalışma alanına geçiliyor`);
      navigate('/app/dashboard', { replace: true });
    } catch (requestError) {
      toast.error(requestError?.response?.data?.detail || 'Otel çalışma alanına geçilemedi.');
      setSwitchingPropertyId('');
    }
  };

  const inspectProperty = property => { if (property) setSelectedProperty(property); };
  const actionItems = [
    { label: 'Tesisler Arası Rezervasyon', icon: CalendarDays, path: '/app/hotel-network' },
    { label: 'Merkezi Fiyat Güncelle', icon: Tags, path: '/central-pricing' },
    { label: 'Mutabakat', icon: WalletCards, path: '/app/bank-reconciliation' },
    { label: 'Onay Merkezi', icon: ShieldCheck, path: '/mobile/approvals' },
    { label: 'Zincir Raporu', icon: FileBarChart, path: '/app/raporlar' },
  ];

  if (loading) return <div className="flex min-h-[420px] items-center justify-center"><div className="text-center"><Loader2 className="mx-auto h-9 w-9 animate-spin text-blue-600" /><p className="mt-3 text-sm text-slate-500">Zincir verileri hazırlanıyor…</p></div></div>;
  if (error) return <div className="p-6"><Card className="border-rose-200 bg-rose-50 dark:border-rose-900 dark:bg-rose-950"><CardContent className="py-10 text-center"><AlertTriangle className="mx-auto h-10 w-10 text-rose-600" /><p className="mt-3 font-semibold text-rose-800 dark:text-rose-200">{error}</p><Button className="mt-4" variant="outline" onClick={loadData}><RefreshCw className="mr-2 h-4 w-4" />Tekrar dene</Button></CardContent></Card></div>;

  return <div className="mx-auto max-w-[1800px] space-y-4 p-4 md:p-6" data-testid="chain-command-center">
    <header className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
      <div className="flex items-start gap-3"><span className="rounded-2xl bg-blue-50 p-3 text-blue-700 dark:bg-blue-950 dark:text-blue-200"><Building2 className="h-6 w-6" /></span><div><h1 className="text-2xl font-bold tracking-tight md:text-3xl">Zincir Operasyon Merkezi</h1><p className="mt-1 text-sm text-slate-500">Tüm tesislerin performansı, operasyonu ve kritik aksiyonları</p></div></div>
      <div className="flex flex-wrap items-center gap-2"><select aria-label="Tesis filtresi" className="h-10 rounded-md border bg-background px-3 text-sm" value={propertyFilter} onChange={event => setPropertyFilter(event.target.value)}><option value="all">Tüm Tesisler</option>{properties.map(property => <option key={property.property_id} value={property.property_id}>{property.property_name}</option>)}</select><div className={`flex h-10 items-center gap-2 rounded-md border px-3 text-sm ${businessDatesAligned ? 'bg-background' : 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200'}`} title={businessDatesAligned ? 'Tüm tesisler aynı PMS iş gününde' : (data?.business_dates || []).map(displayDate).join(', ')}><CalendarDays className="h-4 w-4 text-slate-500" />{businessDateLabel}</div><div className="flex h-10 items-center gap-2 rounded-md border bg-background px-3 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-emerald-500" />Güncellendi: {displayTime(data?.generated_at)}</div><label className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" /><input aria-label="Otel ara" value={query} onChange={event => setQuery(event.target.value)} className="h-10 w-52 rounded-md border bg-background pl-9 pr-3 text-sm" placeholder="Otel ara…" /></label><Button variant="outline" size="icon" onClick={loadData} aria-label="Verileri yenile"><RefreshCw className="h-4 w-4" /></Button></div>
    </header>

    {!businessDatesAligned && <div role="alert" className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" /><div><p className="font-semibold">Tesislerin açık PMS iş günleri farklı</p><p className="mt-1">Zincir ADR ve RevPAR değerleri farklı günler birleştirilerek gösterilmez. Tesis satırlarında her otelin kendi iş günü verisi yer alır.</p></div></div>}
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6" aria-label="Zincir göstergeleri"><KpiCard icon={Hotel} label="Doluluk" value={percent(data?.summary?.avg_occupancy)} detail={`${number.format(metrics.occupied)} / ${number.format(metrics.rooms)} oda`} tone="emerald" /><KpiCard icon={BadgeDollarSign} label="ADR · Açık İş Günü" value={businessDatesAligned ? formatCurrencyBreakdown(metrics.adr, 0) : '—'} detail={businessDatesAligned ? 'Oda geliri / satılan oda' : 'İş günleri eşitlenmeli'} tone="violet" /><KpiCard icon={BarChart3} label="RevPAR · Açık İş Günü" value={businessDatesAligned ? formatCurrencyBreakdown(metrics.revpar, 0) : '—'} detail={businessDatesAligned ? 'Oda geliri / satılabilir oda' : 'İş günleri eşitlenmeli'} /><KpiCard icon={WalletCards} label="Açık İş Günü Tahsilatı" value={formatCurrencyBreakdown(metrics.revenue, 0)} detail="Para birimleri ayrı gösterilir" tone="amber" /><KpiCard icon={Sparkles} label="7 Gün Pickup" value={`${number.format(data?.summary?.pickup_7d || 0)} rezervasyon`} detail="Gelecek konaklamalar" tone="cyan" /><KpiCard icon={DoorOpen} label="İş Günü Hareketi" value={`${number.format(data?.summary?.arrivals_today || 0)} / ${number.format(data?.summary?.departures_today || 0)}`} detail="Giriş / Çıkış" tone="rose" /></section>

    <section className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(360px,0.75fr)]"><Card className="min-w-0 shadow-sm"><CardContent className="p-4"><div className="mb-4 flex items-center justify-between"><div><h2 className="font-semibold">Tesis Performansı</h2><p className="text-xs text-slate-500">Açık iş günündeki gerçek doluluk karşılaştırması</p></div><Badge variant="outline">Canlı veri</Badge></div><div className="h-64 min-h-1 min-w-0"><ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={1}><BarChart data={properties} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="property_name" tick={{ fontSize: 12 }} /><YAxis domain={[0, 100]} tickFormatter={value => `%${value}`} tick={{ fontSize: 11 }} /><Tooltip formatter={value => [percent(value), 'Doluluk']} /><Bar dataKey="occupancy_pct" fill="#2563eb" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer></div></CardContent></Card><Card className="shadow-sm"><CardContent className="p-0"><div className="flex items-center justify-between border-b p-4"><div><h2 className="flex items-center gap-2 font-semibold"><CircleAlert className="h-5 w-5 text-rose-500" />Dikkat Gerektirenler</h2><p className="mt-1 text-xs text-slate-500">{alerts.length} açık konu</p></div></div><div className="max-h-64 divide-y overflow-auto">{alerts.length === 0 ? <div className="p-8 text-center"><CheckCircle2 className="mx-auto h-8 w-8 text-emerald-500" /><p className="mt-2 text-sm font-medium">Kritik konu bulunmuyor</p></div> : alerts.slice(0, 8).map(alert => <button type="button" key={alert.id || `${alert.property_id}-${alert.label}`} onClick={() => inspectProperty(properties.find(item => item.property_id === alert.property_id))} className="flex w-full items-center gap-3 p-3 text-left hover:bg-slate-50 dark:hover:bg-slate-900"><span className={`h-9 w-1 rounded-full ${alert.priority === 'critical' ? 'bg-rose-500' : alert.priority === 'high' ? 'bg-amber-500' : 'bg-blue-500'}`} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{alert.property_name}</p><p className="truncate text-xs text-slate-500">{String(alert.label || '').replace(`${alert.property_name}: `, '')}</p></div><Badge variant="outline" className={priorityStyle[alert.priority] || priorityStyle.medium}>{alert.priority === 'critical' ? 'Kritik' : alert.priority === 'high' ? 'Uyarı' : 'Operasyon'}</Badge><ChevronRight className="h-4 w-4 text-slate-400" /></button>)}</div></CardContent></Card></section>

    <section className="overflow-hidden rounded-xl border bg-background shadow-sm"><div className="flex flex-col gap-3 border-b p-4 xl:flex-row xl:items-center xl:justify-between"><div><h2 className="font-semibold">Tesis Karşılaştırması</h2><p className="text-xs text-slate-500">Aynı iş günündeki operasyon ve finans görünümü</p></div><div className="flex flex-wrap gap-2">{actionItems.map(item => <Button key={item.path} size="sm" variant={item.path === '/app/hotel-network' ? 'default' : 'outline'} onClick={() => navigate(item.path)}><item.icon className="mr-2 h-4 w-4" />{item.label}</Button>)}</div></div><Table><TableHeader><TableRow className="bg-slate-50 dark:bg-slate-900"><TableHead>Tesis</TableHead><TableHead>Durum</TableHead><TableHead>Doluluk</TableHead><TableHead>ADR</TableHead><TableHead>RevPAR</TableHead><TableHead>Bugün Tahsilat</TableHead><TableHead>Pickup</TableHead><TableHead>Giriş / Çıkış</TableHead><TableHead>Uyarı</TableHead><TableHead className="text-right">İşlem</TableHead></TableRow></TableHeader><TableBody>{filteredProperties.map(property => {
      const alertCount = propertyAlerts(property).length;
      return <TableRow key={property.property_id} className="cursor-pointer" onClick={() => inspectProperty(property)} data-testid={`property-row-${property.property_id}`}><TableCell><div className="font-semibold">{property.property_name}</div><div className="flex items-center gap-1 text-xs text-slate-500">{property.location || 'Konum belirtilmedi'}{property.property_id === data.current_property_id && <Badge variant="outline" className="ml-1">Aktif tesis</Badge>}</div></TableCell><TableCell><span className="inline-flex items-center gap-2 text-sm font-medium text-emerald-700"><span className="h-2 w-2 rounded-full bg-emerald-500" />Aktif</span></TableCell><TableCell><div className="font-semibold">{percent(property.occupancy_pct)}</div><div className="text-xs text-slate-500">{property.occupied_rooms}/{property.total_rooms} oda</div></TableCell><TableCell>{formatCurrencyBreakdown(property.adr_by_currency, property.adr, property.currency)}</TableCell><TableCell>{formatCurrencyBreakdown(dividedBreakdown(property.room_revenue_by_currency, property.total_rooms), 0, property.currency)}</TableCell><TableCell>{formatCurrencyBreakdown(property.today_revenue_by_currency, property.today_revenue, property.currency)}</TableCell><TableCell><span className="font-semibold">{number.format(property.pickup_7d || 0)}</span><span className="block text-xs text-slate-500">son 7 gün</span></TableCell><TableCell>{property.arrivals_today || 0} / {property.departures_today || 0}</TableCell><TableCell>{alertCount ? <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">{alertCount} konu</Badge> : <span className="text-emerald-600">Sorun yok</span>}</TableCell><TableCell onClick={event => event.stopPropagation()}><div className="flex justify-end gap-2"><Button size="sm" variant="outline" onClick={() => inspectProperty(property)}><Eye className="mr-1.5 h-4 w-4" />Hızlı görünüm</Button><Button size="sm" onClick={() => enterPropertyWorkspace(property)} disabled={Boolean(switchingPropertyId)} aria-label={`${property.property_name} çalışma alanına geç`}>{switchingPropertyId === property.property_id ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <LogIn className="mr-1.5 h-4 w-4" />}Otele gir</Button></div></TableCell></TableRow>;
    })}</TableBody></Table>{filteredProperties.length === 0 && <div className="p-10 text-center text-sm text-slate-500">Aramanızla eşleşen tesis bulunamadı.</div>}</section>

    <section className="grid gap-3 md:grid-cols-3"><Card><CardContent className="p-4"><div className="flex items-center justify-between"><h3 className="font-semibold">Dağıtım Sağlığı</h3><Button variant="ghost" size="sm" onClick={() => navigate('/app/channel-manager')}>Detaya git <ArrowRight className="ml-1 h-4 w-4" /></Button></div><div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><p className="text-slate-500">Bağlantı hatası</p><p className="mt-1 font-semibold">{properties.filter(item => item.integrations?.channel_manager?.has_error).length} tesis</p></div><div><p className="text-slate-500">Kurulum gerekli</p><p className="mt-1 font-semibold">{properties.filter(item => !item.integrations?.channel_manager?.provider).length} tesis</p></div></div></CardContent></Card><Card><CardContent className="p-4"><div className="flex items-center justify-between"><h3 className="font-semibold">Finansal Mutabakat</h3><Button variant="ghost" size="sm" onClick={() => navigate('/app/bank-reconciliation')}>Detaya git <ArrowRight className="ml-1 h-4 w-4" /></Button></div><div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><p className="text-slate-500">Açık folyo</p><p className="mt-1 font-semibold text-amber-700">{number.format(data?.summary?.open_folios || 0)}</p></div><div><p className="text-slate-500">Bugün tahsilat</p><p className="mt-1 truncate font-semibold">{formatCurrencyBreakdown(metrics.revenue, 0)}</p></div></div></CardContent></Card><Card><CardContent className="p-4"><div className="flex items-center justify-between"><h3 className="font-semibold">Operasyon</h3><Button variant="ghost" size="sm" onClick={() => navigate('/housekeeping')}>Detaya git <ArrowRight className="ml-1 h-4 w-4" /></Button></div><div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><p className="text-slate-500">Temizlik bekleyen</p><p className="mt-1 font-semibold text-amber-700">{number.format(data?.summary?.housekeeping_pending || 0)} görev</p></div><div><p className="text-slate-500">Hizmet dışı oda</p><p className="mt-1 font-semibold">{number.format(data?.summary?.out_of_order_rooms || 0)} oda</p></div></div></CardContent></Card></section>

    {team && <details className="rounded-xl border bg-background p-4"><summary className="cursor-pointer font-semibold">Zincir kullanıcıları · {team.users?.length || 0}</summary><div className="mt-4"><form onSubmit={createChainUser} className="grid gap-3 rounded-lg bg-slate-50 p-4 dark:bg-slate-900 md:grid-cols-2 xl:grid-cols-6"><select aria-label="Tesis" required value={userForm.property_id} onChange={event => setUserForm({ ...userForm, property_id: event.target.value })} className="h-10 rounded-md border bg-background px-3 text-sm xl:col-span-2">{(team.properties || []).map(property => <option key={property.property_id} value={property.property_id}>{property.property_name}</option>)}</select><input aria-label="Ad soyad" required minLength={2} placeholder="Ad soyad" value={userForm.name} onChange={event => setUserForm({ ...userForm, name: event.target.value })} className="h-10 rounded-md border bg-background px-3 text-sm" /><input aria-label="E-posta" required type="email" placeholder="E-posta" value={userForm.email} onChange={event => setUserForm({ ...userForm, email: event.target.value })} className="h-10 rounded-md border bg-background px-3 text-sm" /><input aria-label="Geçici şifre" required minLength={8} type="password" placeholder="Geçici şifre" value={userForm.password} onChange={event => setUserForm({ ...userForm, password: event.target.value })} className="h-10 rounded-md border bg-background px-3 text-sm" /><div className="flex gap-2"><select aria-label="Rol" value={userForm.role} onChange={event => setUserForm({ ...userForm, role: event.target.value })} className="h-10 min-w-0 flex-1 rounded-md border bg-background px-2 text-sm"><option value="admin">Yönetici</option><option value="supervisor">Müdür</option><option value="front_desk">Ön Büro</option><option value="finance">Muhasebe</option><option value="housekeeping">Kat Hizmetleri</option></select><Button type="submit" disabled={savingUser} aria-label="Kullanıcı ekle"><UserPlus className="h-4 w-4" /></Button></div></form>{teamError && <p className="mt-3 text-sm text-rose-600">{teamError}</p>}<div className="mt-3 divide-y rounded-lg border">{(team.users || []).map(user => <div key={user.id} className="grid gap-1 px-4 py-3 text-sm md:grid-cols-3"><span className="font-semibold">{user.name}</span><span className="text-slate-500">{user.email}</span><span className="text-slate-500 md:text-right">{user.property_name} · {user.role}</span></div>)}</div></div></details>}
    {teamError && !team && <p className="text-sm text-rose-600">{teamError}</p>}

    <Sheet open={Boolean(selectedProperty)} onOpenChange={open => { if (!open) setSelectedProperty(null); }}><SheetContent className="w-full overflow-y-auto sm:max-w-xl"><SheetHeader><SheetTitle>{selectedProperty?.property_name}</SheetTitle><SheetDescription>{selectedProperty?.location || 'Konum belirtilmedi'} · İş günü {displayDate(selectedProperty?.business_date || data?.business_date)}</SheetDescription></SheetHeader>{selectedProperty && <div className="mt-6 space-y-5"><div className="grid grid-cols-3 gap-2"><div className="rounded-lg border p-3"><p className="text-xs text-slate-500">Doluluk</p><p className="mt-1 text-xl font-bold">{percent(selectedProperty.occupancy_pct)}</p></div><div className="rounded-lg border p-3"><p className="text-xs text-slate-500">Oda</p><p className="mt-1 text-xl font-bold">{selectedProperty.occupied_rooms}/{selectedProperty.total_rooms}</p></div><div className="rounded-lg border p-3"><p className="text-xs text-slate-500">Pickup</p><p className="mt-1 text-xl font-bold">{selectedProperty.pickup_7d || 0}</p></div></div><div className="rounded-xl border p-4"><h3 className="font-semibold">Bugünkü operasyon</h3><dl className="mt-3 grid grid-cols-2 gap-3 text-sm"><div><dt className="text-slate-500">Giriş</dt><dd className="font-semibold">{selectedProperty.arrivals_today || 0}</dd></div><div><dt className="text-slate-500">Çıkış</dt><dd className="font-semibold">{selectedProperty.departures_today || 0}</dd></div><div><dt className="text-slate-500">Temizlik görevi</dt><dd className="font-semibold">{selectedProperty.housekeeping_pending || 0}</dd></div><div><dt className="text-slate-500">Hizmet dışı oda</dt><dd className="font-semibold">{selectedProperty.out_of_order_rooms || 0}</dd></div></dl></div><div className="rounded-xl border p-4"><h3 className="font-semibold">Finans</h3><dl className="mt-3 space-y-2 text-sm"><div className="flex justify-between gap-3"><dt className="text-slate-500">Bugün tahsilat</dt><dd className="font-semibold">{formatCurrencyBreakdown(selectedProperty.today_revenue_by_currency, selectedProperty.today_revenue, selectedProperty.currency)}</dd></div><div className="flex justify-between gap-3"><dt className="text-slate-500">ADR</dt><dd className="font-semibold">{formatCurrencyBreakdown(selectedProperty.adr_by_currency, selectedProperty.adr, selectedProperty.currency)}</dd></div><div className="flex justify-between gap-3"><dt className="text-slate-500">Açık folyo</dt><dd className="font-semibold">{selectedProperty.open_folios || 0}</dd></div><div className="flex justify-between gap-3"><dt className="text-slate-500">Bekleyen bakiye</dt><dd className="font-semibold">{formatCurrencyBreakdown(selectedProperty.outstanding_by_currency, 0, selectedProperty.currency)}</dd></div></dl></div><div className="rounded-xl border p-4"><h3 className="font-semibold">Bağlantılar</h3><div className="mt-3 space-y-3 text-sm"><div className="flex items-center justify-between"><span>Kanal yöneticisi</span><Badge variant="outline">{selectedProperty.integrations?.channel_manager?.provider ? (selectedProperty.integrations.channel_manager.has_error ? 'Bağlantı hatası' : 'Bağlı') : 'Kurulum gerekli'}</Badge></div><div className="flex items-center justify-between"><span>Nilvera</span><Badge variant="outline">{selectedProperty.integrations?.nilvera?.enabled ? 'Etkin' : 'Kapalı'}</Badge></div></div></div>{propertyAlerts(selectedProperty).length > 0 && <div><h3 className="mb-2 font-semibold">Açık konular</h3><div className="space-y-2">{propertyAlerts(selectedProperty).map(alert => <div key={alert.label} className={`rounded-lg border p-3 text-sm ${priorityStyle[alert.priority]}`}>{alert.label}</div>)}</div></div>}</div>}<SheetFooter className="mt-6"><Button variant="outline" onClick={() => navigate('/app/raporlar')}>Raporları aç</Button><Button onClick={() => enterPropertyWorkspace(selectedProperty)} disabled={!selectedProperty || Boolean(switchingPropertyId)}><LogIn className="mr-2 h-4 w-4" />Otel çalışma alanına gir</Button></SheetFooter></SheetContent></Sheet>
    {!embedded && <span className="sr-only">Zincir operasyon merkezi</span>}
  </div>;
}
