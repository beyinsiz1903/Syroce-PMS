import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
import {
  Activity, Bell, Radio, Users, Home, Wrench, AlertTriangle, CheckCircle,
  Clock, Eye, EyeOff, RefreshCw, ChevronDown, Shield
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const API = "";

const PRIORITY_STYLES = {
  critical: 'bg-red-100 text-red-800 border-red-300',
  high: 'bg-amber-100 text-amber-800 border-amber-300',
  medium: 'bg-sky-100 text-sky-800 border-sky-300',
  low: 'bg-slate-100 text-slate-600 border-slate-300',
};

const EVENT_ICONS = {
  check_in_created: Users,
  guest_arrived: Users,
  housekeeping_task_overdue: Home,
  room_ready: CheckCircle,
  audit_exception: AlertTriangle,
  overbooking_risk: Shield,
  reservation_modified: Clock,
  maintenance_block: Wrench,
  checkout_completed: CheckCircle,
  vip_arrival: Activity,
  rate_alert: Bell,
  night_audit_completed: CheckCircle,
};

export default function OperationalEventDashboard({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [liveFeed, setLiveFeed] = useState(null);
  const [stats, setStats] = useState(null);
  const [unread, setUnread] = useState(null);
  const [fdQueue, setFdQueue] = useState(null);
  const [hkBoard, setHkBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('feed');
  const [filterPriority, setFilterPriority] = useState(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const priorityParam = filterPriority ? `&priority=${filterPriority}` : '';
      const [feedRes, statsRes, unreadRes, fdRes, hkRes] = await Promise.all([
        axios.get(`/event-system/live-feed?limit=50${priorityParam}`, { headers }),
        axios.get(`/event-system/stats?hours=24`, { headers }),
        axios.get(`/event-system/unread-count`, { headers }),
        axios.get(`/event-system/front-desk-queue`, { headers }),
        axios.get(`/event-system/housekeeping-board`, { headers }),
      ]);
      setLiveFeed(feedRes.data);
      setStats(statsRes.data);
      setUnread(unreadRes.data);
      setFdQueue(fdRes.data);
      setHkBoard(hkRes.data);
    } catch (err) {
      console.error('Event dashboard error:', err);
    } finally {
      setLoading(false);
    }
  }, [filterPriority]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(fetchAll, 30000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const markRead = async (eventIds) => {
    try {
      await axios.post(`/event-system/mark-read`, { event_ids: eventIds }, { headers });
      fetchAll();
    } catch (err) { console.error(err); }
  };

  const acknowledge = async (eventId, note) => {
    try {
      await axios.post(`/event-system/acknowledge`, { event_id: eventId, note: note || 'Acknowledged' }, { headers });
      fetchAll();
    } catch (err) { console.error(err); }
  };

  const tabs = [
    { id: 'feed', label: 'Canli Akis', icon: Radio },
    { id: 'frontdesk', label: 'Front Desk Kuyrugu', icon: Users },
    { id: 'housekeeping', label: 'Housekeeping Board', icon: Home },
    { id: 'stats', label: 'Istatistikler', icon: Activity },
  ];

  if (loading) {
    return (
      <>
        <div className="flex items-center justify-center h-64" data-testid="event-loading">
          <RefreshCw className="w-8 h-8 animate-spin text-teal-600" />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="space-y-6 p-4 lg:p-6" data-testid="event-system-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{t("techDashboards.operationalEvents")}</h1>
            <p className="text-sm text-slate-500 mt-1">{t("techDashboards.operationalEventsDesc")}</p>
          </div>
          <div className="flex items-center gap-3">
            {unread?.total_unread > 0 && (
              <Badge variant="destructive" className="text-sm" data-testid="unread-badge">
                {unread.total_unread} Okunmamis
              </Badge>
            )}
            <Button variant="outline" size="sm" onClick={fetchAll} data-testid="event-refresh-btn">
              <RefreshCw className="w-4 h-4 mr-2" /> Yenile
            </Button>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="event-stat-cards">
          <Card className="border-l-4 border-l-red-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Kritik</p>
              <p className="text-2xl font-bold" data-testid="stat-critical">{stats?.by_priority?.critical || 0}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Yüksek</p>
              <p className="text-2xl font-bold" data-testid="stat-high">{stats?.by_priority?.high || 0}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-sky-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Toplam (24s)</p>
              <p className="text-2xl font-bold" data-testid="stat-total">{stats?.total_events || 0}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Onaysiz Kritik</p>
              <p className="text-2xl font-bold" data-testid="stat-unack">{stats?.unacknowledged_critical || 0}</p>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <div className="flex space-x-1 bg-slate-100 rounded-lg p-1" data-testid="event-tabs">
          {tabs.map(t => {
            const Icon = t.icon;
            return (
              <button key={t.id} onClick={() => setActiveTab(t.id)}
                data-testid={`event-tab-${t.id}`}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === t.id ? 'bg-white text-teal-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}>
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>

        {/* Live Feed */}
        {activeTab === 'feed' && (
          <div className="space-y-4">
            {/* Priority Filter */}
            <div className="flex gap-2" data-testid="priority-filter">
              {[null, 'critical', 'high', 'medium', 'low'].map(p => (
                <Button key={p || 'all'} variant={filterPriority === p ? 'default' : 'outline'} size="sm"
                  data-testid={`filter-${p || 'all'}`}
                  onClick={() => setFilterPriority(p)}>
                  {p ? p.charAt(0).toUpperCase() + p.slice(1) : 'Tumu'}
                </Button>
              ))}
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Radio className="w-4 h-4 text-red-500 animate-pulse" /> Canli Olay Akisi
                </CardTitle>
              </CardHeader>
              <CardContent>
                {(liveFeed?.events || []).length === 0 ? (
                  <div className="text-center py-12 text-slate-400" data-testid="no-events">
                    <Radio className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>Henüz olay yok</p>
                  </div>
                ) : (
                  <div className="space-y-2" data-testid="event-list">
                    {(liveFeed?.events || []).map(e => {
                      const Icon = EVENT_ICONS[e.event_type] || Activity;
                      return (
                        <div key={e.id} className={`flex items-start gap-3 p-3 rounded-lg border ${PRIORITY_STYLES[e.priority] || PRIORITY_STYLES.low} ${!e.read ? 'ring-1 ring-teal-300' : ''}`}
                          data-testid={`event-${e.id}`}>
                          <Icon className="w-5 h-5 mt-0.5 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-sm">{e.event_type?.replace(/_/g, ' ')}</span>
                              <Badge variant="outline" className="text-xs">{e.priority}</Badge>
                              {!e.read && <span className="w-2 h-2 rounded-full bg-teal-500" />}
                            </div>
                            <p className="text-xs text-slate-500 mt-1 truncate">{JSON.stringify(e.payload).slice(0, 120)}</p>
                            <p className="text-xs text-slate-400 mt-1">{e.created_at?.replace('T', ' ').slice(0, 19)}</p>
                          </div>
                          <div className="flex gap-1 shrink-0">
                            {!e.read && (
                              <Button variant="ghost" size="sm" onClick={() => markRead([e.id])} data-testid={`mark-read-${e.id}`}>
                                <Eye className="w-3 h-3" />
                              </Button>
                            )}
                            {!e.acknowledged && (e.priority === 'critical' || e.priority === 'high') && (
                              <Button variant="ghost" size="sm" onClick={() => acknowledge(e.id)} data-testid={`ack-${e.id}`}>
                                <CheckCircle className="w-3 h-3" />
                              </Button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Front Desk Queue */}
        {activeTab === 'frontdesk' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Bekleyen Varislar ({fdQueue?.pending_arrivals || 0})</CardTitle>
              </CardHeader>
              <CardContent>
                {(fdQueue?.arrivals || []).length === 0 ? (
                  <p className="text-slate-400 text-sm text-center py-8">Bekleyen varis yok</p>
                ) : (
                  <div className="space-y-2" data-testid="arrivals-list">
                    {(fdQueue?.arrivals || []).map((a, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                        <div>
                          <p className="font-medium text-sm">{a.guest_name || 'Misafir'}</p>
                          <p className="text-xs text-slate-500">Oda: {a.room_id}</p>
                        </div>
                        {a.vip && <Badge variant="destructive">VIP</Badge>}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Bekleyen Cikslar ({fdQueue?.pending_departures || 0})</CardTitle>
              </CardHeader>
              <CardContent>
                {(fdQueue?.departures || []).length === 0 ? (
                  <p className="text-slate-400 text-sm text-center py-8">Bekleyen çıkış yok</p>
                ) : (
                  <div className="space-y-2" data-testid="departures-list">
                    {(fdQueue?.departures || []).map((d, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                        <div>
                          <p className="font-medium text-sm">{d.guest_name || 'Misafir'}</p>
                          <p className="text-xs text-slate-500">Oda: {d.room_id}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Housekeeping Board */}
        {activeTab === 'housekeeping' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="hk-summary">
              <Card>
                <CardContent className="p-4 text-center">
                  <p className="text-xs text-slate-500 uppercase">Kirli</p>
                  <p className="text-3xl font-bold text-red-600">{hkBoard?.summary?.dirty || 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4 text-center">
                  <p className="text-xs text-slate-500 uppercase">Temizleniyor</p>
                  <p className="text-3xl font-bold text-amber-600">{hkBoard?.summary?.cleaning || 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4 text-center">
                  <p className="text-xs text-slate-500 uppercase">Denetimde</p>
                  <p className="text-3xl font-bold text-sky-600">{hkBoard?.summary?.inspected || 0}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4 text-center">
                  <p className="text-xs text-slate-500 uppercase">Temiz</p>
                  <p className="text-3xl font-bold text-emerald-600">{hkBoard?.summary?.clean || 0}</p>
                </CardContent>
              </Card>
            </div>

            {(hkBoard?.overdue_alerts || []).length > 0 && (
              <Card>
                <CardHeader><CardTitle className="text-base text-red-600 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" /> Geciken Görevler
                </CardTitle></CardHeader>
                <CardContent>
                  <div className="space-y-2" data-testid="hk-overdue-list">
                    {(hkBoard?.overdue_alerts || []).map((a, i) => (
                      <div key={i} className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm">
                        {a.event_type?.replace(/_/g, ' ')} - {JSON.stringify(a.payload).slice(0, 80)}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Stats Tab */}
        {activeTab === 'stats' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader><CardTitle className="text-base">Olay Tipleri (24 Saat)</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-2" data-testid="event-type-stats">
                  {Object.entries(stats?.by_type || {}).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between p-2 bg-slate-50 rounded">
                      <span className="text-sm">{type.replace(/_/g, ' ')}</span>
                      <Badge variant="secondary">{count}</Badge>
                    </div>
                  ))}
                  {Object.keys(stats?.by_type || {}).length === 0 && (
                    <p className="text-slate-400 text-sm text-center py-4">Veri yok</p>
                  )}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-base">Oncelik Dagilimi</CardTitle></CardHeader>
              <CardContent>
                <div className="space-y-3" data-testid="priority-stats">
                  {['critical', 'high', 'medium', 'low'].map(p => (
                    <div key={p} className="flex items-center gap-3">
                      <Badge className={PRIORITY_STYLES[p]}>{p}</Badge>
                      <div className="flex-1 bg-slate-200 rounded-full h-3">
                        <div className="h-3 rounded-full transition-all"
                          style={{
                            width: `${stats?.total_events ? ((stats.by_priority?.[p] || 0) / stats.total_events * 100) : 0}%`,
                            backgroundColor: p === 'critical' ? '#ef4444' : p === 'high' ? '#f97316' : p === 'medium' ? '#0ea5e9' : '#94a3b8'
                          }} />
                      </div>
                      <span className="text-sm font-medium w-8 text-right">{stats?.by_priority?.[p] || 0}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </>
  );
}
