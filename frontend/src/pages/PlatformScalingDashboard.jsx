import { useTranslation } from 'react-i18next';
import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts';
import {
  Activity, Bell, Building2, TrendingUp, Brain,
  AlertTriangle, Globe, Zap, Shield, RefreshCw, ChevronRight,
  ArrowUp, ArrowDown, Minus, Users, DollarSign, BarChart3,
  Radio, Layers, Eye, Crosshair
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const API = "";
const COLORS = ['#0f766e', '#0ea5e9', '#8b5cf6', '#f59e0b', '#ef4444', '#10b981', '#6366f1', '#ec4899'];

export default function PlatformScalingDashboard({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [activeModule, setActiveModule] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [eventData, setEventData] = useState(null);
  const [multiPropData, setMultiPropData] = useState(null);
  const [mlData, setMlData] = useState(null);
  const [compData, setCompData] = useState(null);
  const [notifications, setNotifications] = useState(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [evtRes, mpRes, mlRes, compRes, notifRes] = await Promise.all([
        axios.get(`/platform/events/analytics?hours=24`, { headers }).catch(() => ({ data: null })),
        axios.get(`/platform/multi-property/dashboard`, { headers }).catch(() => ({ data: null })),
        axios.get(`/platform/ml/dashboard`, { headers }).catch(() => ({ data: null })),
        axios.get(`/platform/competitive/dashboard`, { headers }).catch(() => ({ data: null })),
        axios.get(`/platform/events/notifications?unread_only=true&limit=10`, { headers }).catch(() => ({ data: null })),
      ]);
      setEventData(evtRes.data);
      setMultiPropData(mpRes.data);
      setMlData(mlRes.data);
      setCompData(compRes.data);
      setNotifications(notifRes.data);
    } catch (err) {
      console.error('Platform dashboard error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const modules = [
    { id: 'overview', label: 'Genel Bakis', icon: Layers },
    { id: 'events', label: 'Event Mimari', icon: Radio },
    { id: 'multi_property', label: 'Multi-Property', icon: Building2 },
    { id: 'competitive', label: 'CompSet Analiz', icon: Crosshair },
  ];

  if (loading) {
    return (
      <>
        <div className="flex items-center justify-center h-96" data-testid="loading-spinner">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-teal-500" />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="space-y-6 p-6" data-testid="platform-scaling-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900" data-testid="dashboard-title">
              {t("techDashboards.platformScaling")}
            </h1>
            <p className="text-sm text-slate-500 mt-1">{t("techDashboards.platformScalingDesc")}</p>
          </div>
          <div className="flex items-center gap-3">
            <NotificationBadge notifications={notifications} />
            <Button onClick={fetchAll} variant="outline" size="sm" data-testid="refresh-btn">
              <RefreshCw className="w-4 h-4 mr-1" /> Yenile
            </Button>
          </div>
        </div>

        {/* Module Tabs */}
        <div className="flex gap-2 border-b pb-3 overflow-x-auto" data-testid="module-tabs">
          {modules.map(m => (
            <button
              key={m.id}
              data-testid={`tab-${m.id}`}
              onClick={() => setActiveModule(m.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${
                activeModule === m.id
                  ? 'bg-teal-600 text-white shadow-md'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              <m.icon className="w-4 h-4" />
              {m.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {activeModule === 'overview' && <OverviewPanel eventData={eventData} multiPropData={multiPropData} mlData={mlData} compData={compData} />}
        {activeModule === 'events' && <EventArchitecturePanel data={eventData} headers={headers} fetchAll={fetchAll} />}
        {activeModule === 'multi_property' && <MultiPropertyPanel data={multiPropData} />}
        {activeModule === 'competitive' && <CompetitivePanel data={compData} headers={headers} fetchAll={fetchAll} />}
      </div>
    </>
  );
}

function NotificationBadge({ notifications }) {
  const count = notifications?.unread_count || 0;
  return (
    <div className="relative" data-testid="notification-badge">
      <Bell className="w-5 h-5 text-slate-600" />
      {count > 0 && (
        <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
          {count > 9 ? '9+' : count}
        </span>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════ */
/* OVERVIEW PANEL                                  */
/* ════════════════════════════════════════════════ */
function OverviewPanel({ eventData, multiPropData, mlData, compData }) {
  const portfolio = multiPropData?.portfolio || {};
  const mlSummary = mlData?.summary || {};
  const alerts = multiPropData?.alerts || {};

  const kpis = [
    { label: 'Toplam Oda', value: portfolio.total_rooms || 0, icon: Building2, color: 'text-teal-600' },
    { label: 'Portfolio Doluluk', value: `${portfolio.portfolio_occupancy_pct || 0}%`, icon: TrendingUp, color: 'text-blue-600' },
    { label: 'Riskli Rezervasyon', value: mlSummary.at_risk_bookings || 0, icon: AlertTriangle, color: 'text-amber-600' },
    { label: 'Yüksek Talep Gunu', value: `${mlSummary.high_demand_days_next_14 || 0}/14`, icon: Zap, color: 'text-indigo-600' },
    { label: 'Global Uyarı', value: alerts.count || 0, icon: Bell, color: 'text-red-600' },
    { label: 'Olay Sayısı (24s)', value: eventData?.total_events || 0, icon: Activity, color: 'text-indigo-600' },
  ];

  return (
    <div className="space-y-6" data-testid="overview-panel">
      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {kpis.map((kpi, i) => (
          <Card key={i} data-testid={`kpi-card-${i}`}>
            <CardContent className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <kpi.icon className={`w-4 h-4 ${kpi.color}`} />
                <span className="text-xs text-slate-500">{kpi.label}</span>
              </div>
              <div className="text-2xl font-bold text-slate-900">{kpi.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Properties + Alerts side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card data-testid="properties-overview">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Building2 className="w-4 h-4 text-teal-600" /> Property Durumu
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {(portfolio.properties || []).map((p, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div>
                    <div className="font-medium text-sm text-slate-800">{p.property_name}</div>
                    <div className="text-xs text-slate-500">{p.total_rooms} oda</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <OccupancyBadge pct={p.occupancy_pct} />
                    <div className="text-right text-xs">
                      <div className="text-green-600">{p.arrivals_today} giriş</div>
                      <div className="text-amber-600">{p.departures_today} çıkış</div>
                    </div>
                  </div>
                </div>
              ))}
              {(!portfolio.properties || portfolio.properties.length === 0) && (
                <p className="text-sm text-slate-400 text-center py-4">Property verisi yok</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card data-testid="global-alerts-overview">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" /> Global Uyarilar
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {(alerts.alerts || []).map((a, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-slate-50 rounded-lg">
                  <PriorityDot priority={a.priority} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-800 truncate">{a.message}</div>
                    <div className="text-xs text-slate-500">{a.property_name}</div>
                  </div>
                  <Badge variant={a.priority === 'critical' ? 'destructive' : 'secondary'} className="text-xs shrink-0">
                    {a.priority}
                  </Badge>
                </div>
              ))}
              {(!alerts.alerts || alerts.alerts.length === 0) && (
                <p className="text-sm text-slate-400 text-center py-4">Aktif uyarı yok</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ML Summary + Event Priority */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card data-testid="ml-summary-overview">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Brain className="w-4 h-4 text-indigo-600" /> ML Özet
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <StatBox label="Riskli Rez. Geliri" value={`${(mlData?.cancellation_risk?.total_at_risk_revenue || 0).toLocaleString()} TL`} color="text-red-600" />
              <StatBox label="Fiyat Opt. Firsati" value={mlData?.price_optimization?.price_points?.length || 0} color="text-teal-600" />
              <StatBox label="Düşük Talep Gunu" value={`${mlData?.summary?.low_demand_days_next_14 || 0}/14`} color="text-amber-600" />
              <StatBox label="Riskli Rez. Sayısı" value={mlData?.cancellation_risk?.at_risk_count || 0} color="text-amber-600" />
            </div>
          </CardContent>
        </Card>

        <Card data-testid="event-priority-overview">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Radio className="w-4 h-4 text-indigo-600" /> Olay Oncelik Dagilimi
            </CardTitle>
          </CardHeader>
          <CardContent>
            {eventData?.total_events > 0 ? (
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={Object.entries(eventData?.by_priority || {}).map(([k, v]) => ({ name: k, value: v }))}
                      cx="50%" cy="50%" outerRadius={70} dataKey="value" label={({ name, value }) => `${name}: ${value}`}
                    >
                      {Object.keys(eventData?.by_priority || {}).map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-slate-400 text-center py-8">Henüz olay yok</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════ */
/* EVENT ARCHITECTURE PANEL                       */
/* ════════════════════════════════════════════════ */
function EventArchitecturePanel({ data, headers, fetchAll }) {
  const [publishForm, setPublishForm] = useState({ event_type: 'rate_alert', payload: '{}' });
  const [publishing, setPublishing] = useState(false);
  const [events, setEvents] = useState([]);
  const [escalations, setEscalations] = useState([]);

  useEffect(() => {
    const fetchEvents = async () => {
      try {
        const [evtRes, escRes] = await Promise.all([
          axios.get(`/platform/events/stream?limit=20`, { headers }),
          axios.get(`/platform/events/escalation-queue`, { headers }),
        ]);
        setEvents(evtRes.data?.events || []);
        setEscalations(escRes.data?.events || []);
      } catch (e) { console.error(e); }
    };
    fetchEvents();
  }, []);

  const handlePublish = async () => {
    setPublishing(true);
    try {
      let payload = {};
      try { payload = JSON.parse(publishForm.payload); } catch { payload = { message: publishForm.payload }; }
      await axios.post(`/platform/events/publish`, {
        event_type: publishForm.event_type, payload
      }, { headers });
      fetchAll();
      const evtRes = await axios.get(`/platform/events/stream?limit=20`, { headers });
      setEvents(evtRes.data?.events || []);
    } catch (e) { console.error(e); }
    setPublishing(false);
  };

  const eventTypes = [
    'rate_alert', 'demand_spike', 'competitor_price_change', 'cancellation_wave',
    'vip_arrival', 'overbooking_risk', 'revenue_alert', 'ml_prediction_alert',
    'guest_complaint_escalation', 'system_health_alert', 'check_in_created', 'room_ready',
  ];

  return (
    <div className="space-y-6" data-testid="event-architecture-panel">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Publish Event */}
        <Card data-testid="publish-event-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Olay Yayinla</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <select
              data-testid="event-type-select"
              value={publishForm.event_type}
              onChange={e => setPublishForm(p => ({ ...p, event_type: e.target.value }))}
              className="w-full border rounded-lg px-3 py-2 text-sm"
            >
              {eventTypes.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <textarea
              data-testid="event-payload-input"
              value={publishForm.payload}
              onChange={e => setPublishForm(p => ({ ...p, payload: e.target.value }))}
              className="w-full border rounded-lg px-3 py-2 text-sm h-20"
              placeholder='{"message": "Test olayi"}'
            />
            <Button onClick={handlePublish} disabled={publishing} className="w-full" size="sm" data-testid="publish-event-btn">
              <Zap className="w-4 h-4 mr-1" /> {publishing ? 'Yayinlaniyor...' : 'Yayinla'}
            </Button>
          </CardContent>
        </Card>

        {/* Analytics */}
        <Card className="lg:col-span-2" data-testid="event-analytics-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Olay Analitigi (24 saat)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-4 mb-4">
              <StatBox label="Toplam" value={data?.total_events || 0} color="text-slate-800" />
              <StatBox label="Kritik" value={data?.by_priority?.critical || 0} color="text-red-600" />
              <StatBox label="Yüksek" value={data?.by_priority?.high || 0} color="text-amber-600" />
              <StatBox label="Onaysiz Kritik" value={data?.unacknowledged_critical || 0} color="text-red-500" />
            </div>
            {data?.by_type && Object.keys(data.by_type).length > 0 ? (
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={Object.entries(data.by_type).map(([k, v]) => ({ name: k.replace(/_/g, ' '), count: v }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" fill="#0f766e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-slate-400 text-center py-6">Olay verisi yok</p>}
          </CardContent>
        </Card>
      </div>

      {/* Event Stream + Escalation */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card data-testid="event-stream-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="w-4 h-4" /> Canli Olay Akisi
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {events.map((e, i) => (
                <div key={i} className="flex items-start gap-3 p-2 border-b last:border-0">
                  <PriorityDot priority={e.priority} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-700">{e.event_type?.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-slate-500">{new Date(e.created_at).toLocaleString('tr-TR')}</div>
                  </div>
                  <Badge variant="outline" className="text-xs shrink-0">{e.priority}</Badge>
                </div>
              ))}
              {events.length === 0 && <p className="text-sm text-slate-400 text-center py-4">Henüz olay yok</p>}
            </div>
          </CardContent>
        </Card>

        <Card data-testid="escalation-queue-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Shield className="w-4 h-4 text-red-500" /> Eskalasyon Kuyrugu
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {escalations.map((e, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-red-50 rounded-lg">
                  <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-red-800">{e.event_type?.replace(/_/g, ' ')}</div>
                    <div className="text-xs text-red-600">{e.overdue_minutes} dk gecikme</div>
                  </div>
                </div>
              ))}
              {escalations.length === 0 && (
                <div className="text-center py-8">
                  <Shield className="w-8 h-8 text-green-400 mx-auto mb-2" />
                  <p className="text-sm text-green-600">Tüm olaylar zamaninda islenidi</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Gateway Stats */}
      <Card data-testid="gateway-stats-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Globe className="w-4 h-4 text-blue-600" /> WebSocket Gateway Istatistikleri
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            <StatBox label="Aktif Bağlantı" value={data?.gateway_stats?.total_connections || 0} color="text-blue-600" />
            <StatBox label="Bagli Tenant" value={data?.gateway_stats?.tenants_connected || 0} color="text-teal-600" />
            <StatBox label="Son Yayinlar" value={data?.gateway_stats?.recent_broadcasts || 0} color="text-indigo-600" />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ════════════════════════════════════════════════ */
/* MULTI-PROPERTY PANEL                           */
/* ════════════════════════════════════════════════ */
function MultiPropertyPanel({ data }) {
  const portfolio = data?.portfolio || {};
  const revenue = data?.revenue || {};
  const alerts = data?.alerts || {};

  return (
    <div className="space-y-6" data-testid="multi-property-panel">
      {/* Portfolio KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard label="Portfolio Doluluk" value={`${portfolio.portfolio_occupancy_pct || 0}%`} icon={Building2} color="bg-teal-50 text-teal-700" />
        <KPICard label="Toplam Oda" value={portfolio.total_rooms || 0} icon={Layers} color="bg-blue-50 text-blue-700" />
        <KPICard label="Müsait Oda" value={portfolio.total_available || 0} icon={Eye} color="bg-green-50 text-green-700" />
        <KPICard label="Portfolio Gelir" value={`${(revenue.total_portfolio_revenue || 0).toLocaleString()} TL`} icon={DollarSign} color="bg-indigo-50 text-indigo-700" />
      </div>

      {/* Property Comparison */}
      <Card data-testid="property-comparison-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Property Karşılaştırma</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-2 text-slate-500 font-medium">Property</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Oda</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Doluluk</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Giriş</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Çıkış</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Gelir</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">ADR</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">RevPAR</th>
                </tr>
              </thead>
              <tbody>
                {(portfolio.properties || []).map((p, i) => {
                  const rev = (revenue.properties || []).find(r => r.property_id === p.property_id) || {};
                  return (
                    <tr key={i} className="border-b last:border-0 hover:bg-slate-50">
                      <td className="py-3 font-medium">{p.property_name}</td>
                      <td className="py-3 text-right">{p.total_rooms}</td>
                      <td className="py-3 text-right"><OccupancyBadge pct={p.occupancy_pct} /></td>
                      <td className="py-3 text-right text-green-600">{p.arrivals_today}</td>
                      <td className="py-3 text-right text-amber-600">{p.departures_today}</td>
                      <td className="py-3 text-right">{(rev.total_revenue || 0).toLocaleString()} TL</td>
                      <td className="py-3 text-right">{rev.adr || 0} TL</td>
                      <td className="py-3 text-right">{rev.revpar || 0} TL</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Revenue Chart + Global Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card data-testid="revenue-chart-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Property Gelir Dagilimi</CardTitle>
          </CardHeader>
          <CardContent>
            {(revenue.properties || []).length > 0 ? (
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={(revenue.properties || []).map(p => ({
                    name: (p.property_name || '').slice(0, 15),
                    room: p.room_revenue || 0,
                    fnb: p.fnb_revenue || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="room" name="Oda Geliri" fill="#0f766e" stackId="a" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="fnb" name="F&B Geliri" fill="#0ea5e9" stackId="a" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-slate-400 text-center py-8">Gelir verisi yok</p>}
          </CardContent>
        </Card>

        <Card data-testid="mp-alerts-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Uyarilar ({alerts.count || 0})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-56 overflow-y-auto">
              {(alerts.alerts || []).map((a, i) => (
                <div key={i} className="flex items-start gap-2 p-2 bg-slate-50 rounded">
                  <PriorityDot priority={a.priority} />
                  <div className="flex-1 min-w-0 text-sm">
                    <div className="truncate">{a.message}</div>
                  </div>
                </div>
              ))}
              {(!alerts.alerts || alerts.alerts.length === 0) && (
                <p className="text-sm text-slate-400 text-center py-4">Aktif uyarı yok</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════ */
/* COMPETITIVE PANEL                              */
/* ════════════════════════════════════════════════ */
function CompetitivePanel({ data, headers, fetchAll }) {
  const [addForm, setAddForm] = useState({ name: '', star_rating: 4 });
  const [adding, setAdding] = useState(false);

  const competitors = data?.comp_set?.competitors || [];
  const parity = data?.rate_parity?.room_types || [];
  const suggestions = data?.adr_suggestions?.suggestions || [];
  const totalImpact = data?.adr_suggestions?.total_estimated_monthly_impact || 0;

  const handleAddCompetitor = async () => {
    if (!addForm.name) return;
    setAdding(true);
    try {
      await axios.post(`/platform/competitive/add-competitor`, {
        name: addForm.name, star_rating: addForm.star_rating,
      }, { headers });
      setAddForm({ name: '', star_rating: 4 });
      fetchAll();
    } catch (e) { console.error(e); }
    setAdding(false);
  };

  return (
    <div className="space-y-6" data-testid="competitive-panel">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Add Competitor */}
        <Card data-testid="add-competitor-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Rakip Ekle</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <input
              data-testid="competitor-name-input"
              value={addForm.name}
              onChange={e => setAddForm(p => ({ ...p, name: e.target.value }))}
              className="w-full border rounded-lg px-3 py-2 text-sm"
              placeholder="Otel adi..."
            />
            <select
              data-testid="competitor-star-select"
              value={addForm.star_rating}
              onChange={e => setAddForm(p => ({ ...p, star_rating: parseInt(e.target.value) }))}
              className="w-full border rounded-lg px-3 py-2 text-sm"
            >
              {[3, 4, 5].map(s => <option key={s} value={s}>{s} Yildiz</option>)}
            </select>
            <Button onClick={handleAddCompetitor} disabled={adding || !addForm.name} className="w-full" size="sm" data-testid="add-competitor-btn">
              {adding ? 'Ekleniyor...' : 'Rakip Ekle'}
            </Button>
          </CardContent>
        </Card>

        {/* Comp Set */}
        <Card className="lg:col-span-2" data-testid="comp-set-card">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Crosshair className="w-4 h-4 text-indigo-600" /> Rakip Seti ({competitors.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {competitors.map((c, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <div>
                    <div className="font-medium text-sm">{c.name}</div>
                    <div className="text-xs text-slate-500">{c.location || 'Konum belirtilmedi'}</div>
                  </div>
                  <Badge variant="outline">{c.star_rating} Yildiz</Badge>
                </div>
              ))}
              {competitors.length === 0 && <p className="text-sm text-slate-400 text-center py-4">Rakip eklenmemis</p>}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Rate Parity */}
      <Card data-testid="rate-parity-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Fiyat Parite Analizi</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-2 text-slate-500 font-medium">Oda Tipi</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Bizim Fiyat</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Pazar Ort.</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Pozisyon Indeksi</th>
                  <th className="pb-2 text-slate-500 font-medium text-right">Konum</th>
                </tr>
              </thead>
              <tbody>
                {parity.map((p, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-2 font-medium">{p.room_type}</td>
                    <td className="py-2 text-right">{p.our_rate} TL</td>
                    <td className="py-2 text-right">{p.market_average} TL</td>
                    <td className="py-2 text-right">{p.position_index}</td>
                    <td className="py-2 text-right">
                      <PositionBadge position={p.market_position} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {parity.length === 0 && <p className="text-sm text-slate-400 text-center py-4">Parite verisi yok</p>}
          </div>
        </CardContent>
      </Card>

      {/* ADR Suggestions */}
      <Card data-testid="adr-suggestions-card">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-green-600" /> ADR Ayarlama Onerileri
            {totalImpact !== 0 && (
              <Badge variant={totalImpact > 0 ? 'default' : 'destructive'} className="ml-2">
                {totalImpact > 0 ? '+' : ''}{totalImpact.toLocaleString()} TL/ay
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {suggestions.map((s, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                <div>
                  <div className="font-medium text-sm">{s.room_type}</div>
                  <div className="text-xs text-slate-500">{s.reason}</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-xs text-slate-500">Mevcut</div>
                    <div className="text-sm">{s.current_rate} TL</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-400" />
                  <div className="text-right">
                    <div className="text-xs text-slate-500">Önerilen</div>
                    <div className="text-sm font-bold text-teal-700">{s.suggested_rate} TL</div>
                  </div>
                  <ActionBadge action={s.action} />
                </div>
              </div>
            ))}
            {suggestions.length === 0 && <p className="text-sm text-slate-400 text-center py-4">ADR onerisi yok</p>}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ════════════════════════════════════════════════ */
/* SHARED COMPONENTS                              */
/* ════════════════════════════════════════════════ */
function StatBox({ label, value, color = 'text-slate-800' }) {
  return (
    <div>
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${color}`}>{value}</div>
    </div>
  );
}

function KPICard({ label, value, icon: Icon, color }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className={`inline-flex items-center gap-2 px-2 py-1 rounded-md text-xs ${color} mb-2`}>
          <Icon className="w-3 h-3" /> {label}
        </div>
        <div className="text-2xl font-bold text-slate-900">{value}</div>
      </CardContent>
    </Card>
  );
}

function OccupancyBadge({ pct }) {
  const color = pct >= 80 ? 'bg-green-100 text-green-700' : pct >= 50 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700';
  return <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${color}`}>{pct}%</span>;
}

function PriorityDot({ priority }) {
  const colors = { critical: 'bg-red-500', high: 'bg-amber-500', medium: 'bg-yellow-500', low: 'bg-slate-400' };
  return <span className={`w-2 h-2 rounded-full ${colors[priority] || colors.low} shrink-0 mt-1.5`} />;
}

function ActionBadge({ action }) {
  const map = {
    increase: { label: 'Artir', icon: ArrowUp, cls: 'text-green-600' },
    slight_increase: { label: 'Hafif Artir', icon: ArrowUp, cls: 'text-teal-600' },
    maintain: { label: 'Koru', icon: Minus, cls: 'text-blue-600' },
    decrease: { label: 'Dusur', icon: ArrowDown, cls: 'text-red-600' },
    slight_decrease: { label: 'Hafif Dusur', icon: ArrowDown, cls: 'text-amber-600' },
    no_data: { label: 'Veri Yok', icon: Minus, cls: 'text-slate-400' },
  };
  const item = map[action] || map.no_data;
  return (
    <span className={`flex items-center gap-1 text-xs font-medium ${item.cls}`}>
      <item.icon className="w-3 h-3" /> {item.label}
    </span>
  );
}

function PositionBadge({ position }) {
  const map = {
    premium: { label: 'Premium', cls: 'bg-indigo-100 text-indigo-700' },
    above_market: { label: 'Pazar Ustu', cls: 'bg-blue-100 text-blue-700' },
    at_market: { label: 'Pazar Seviye', cls: 'bg-green-100 text-green-700' },
    below_market: { label: 'Pazar Alti', cls: 'bg-yellow-100 text-yellow-700' },
    budget: { label: 'Butce', cls: 'bg-red-100 text-red-700' },
    unknown: { label: 'Bilinmiyor', cls: 'bg-slate-100 text-slate-500' },
  };
  const item = map[position] || map.unknown;
  return <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${item.cls}`}>{item.label}</span>;
}
