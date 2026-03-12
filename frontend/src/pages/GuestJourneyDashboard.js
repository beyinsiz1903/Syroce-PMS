import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  User, MessageSquare, Star, Clock, CheckCircle, AlertCircle, Send,
  Mail, Phone, Globe, RefreshCw, FileText, PlusCircle, ArrowRight
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import Layout from '@/components/Layout';

const API = process.env.REACT_APP_BACKEND_URL;

const STATUS_COLORS = {
  open: 'bg-red-100 text-red-800',
  assigned: 'bg-amber-100 text-amber-800',
  in_progress: 'bg-sky-100 text-sky-800',
  resolved: 'bg-emerald-100 text-emerald-800',
  closed: 'bg-slate-100 text-slate-600',
  escalated: 'bg-purple-100 text-purple-800',
};

const TYPE_ICONS = {
  housekeeping: '🏠',
  maintenance: '🔧',
  concierge: '🛎',
  room_service: '🍽',
  amenity: '🧴',
  complaint: '⚠',
};

export default function GuestJourneyDashboard({ user, tenant, onLogout }) {
  const [dashboard, setDashboard] = useState(null);
  const [requests, setRequests] = useState(null);
  const [templates, setTemplates] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [statusFilter, setStatusFilter] = useState(null);
  const [typeFilter, setTypeFilter] = useState(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      let reqParams = '?limit=50';
      if (statusFilter) reqParams += `&status=${statusFilter}`;
      if (typeFilter) reqParams += `&request_type=${typeFilter}`;

      const [dashRes, reqRes, tplRes] = await Promise.all([
        axios.get(`${API}/api/guest-journey/satisfaction-dashboard`, { headers }),
        axios.get(`${API}/api/guest-journey/guest-requests${reqParams}`, { headers }),
        axios.get(`${API}/api/guest-journey/message-templates`, { headers }),
      ]);
      setDashboard(dashRes.data);
      setRequests(reqRes.data);
      setTemplates(tplRes.data);
    } catch (err) {
      console.error('Guest journey error:', err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const updateRequestStatus = async (requestId, newStatus) => {
    try {
      await axios.post(`${API}/api/guest-journey/guest-request/status`, {
        request_id: requestId, new_status: newStatus
      }, { headers });
      fetchAll();
    } catch (err) { console.error(err); }
  };

  const tabs = [
    { id: 'dashboard', label: 'Ozet', icon: Star },
    { id: 'requests', label: 'Talepler', icon: MessageSquare },
    { id: 'messaging', label: 'Mesajlasma', icon: Send },
    { id: 'reviews', label: 'Degerlendirmeler', icon: Star },
  ];

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
        <div className="flex items-center justify-center h-64" data-testid="journey-loading">
          <RefreshCw className="w-8 h-8 animate-spin text-teal-600" />
        </div>
      </Layout>
    );
  }

  const rep = dashboard?.reputation || {};
  const dist = rep?.distribution || {};

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
      <div className="space-y-6 p-4 lg:p-6" data-testid="guest-journey-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Guest Journey</h1>
            <p className="text-sm text-slate-500 mt-1">Misafir deneyimi yonetimi</p>
          </div>
          <Button variant="outline" size="sm" onClick={fetchAll} data-testid="journey-refresh-btn">
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4" data-testid="journey-kpi-cards">
          <Card className="border-l-4 border-l-red-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Acik Talepler</p>
              <p className="text-2xl font-bold" data-testid="kpi-open-requests">{dashboard?.open_requests || 0}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-sky-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Ort. Cozum</p>
              <p className="text-2xl font-bold" data-testid="kpi-avg-resolution">{dashboard?.avg_resolution_minutes || 0} dk</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Bugun Varislar</p>
              <p className="text-2xl font-bold" data-testid="kpi-arrivals">{dashboard?.today_arrivals || 0}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-emerald-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Online Check-in</p>
              <p className="text-2xl font-bold" data-testid="kpi-online-checkins">{dashboard?.online_checkins || 0}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-violet-500">
            <CardContent className="p-4">
              <p className="text-xs text-slate-500 uppercase">Ort. Puan</p>
              <p className="text-2xl font-bold" data-testid="kpi-avg-rating">{rep.average_rating || '-'}</p>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <div className="flex space-x-1 bg-slate-100 rounded-lg p-1" data-testid="journey-tabs">
          {tabs.map(t => {
            const Icon = t.icon;
            return (
              <button key={t.id} onClick={() => setActiveTab(t.id)}
                data-testid={`journey-tab-${t.id}`}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${activeTab === t.id ? 'bg-white text-teal-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}>
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* Resolution by Type */}
            <Card>
              <CardHeader><CardTitle className="text-base">Talep Tipi Bazli Cozum Suresi</CardTitle></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-4" data-testid="resolution-by-type">
                  {Object.entries(dashboard?.avg_resolution_by_type || {}).map(([type, mins]) => (
                    <div key={type} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg">
                      <span className="text-2xl">{TYPE_ICONS[type] || '?'}</span>
                      <div>
                        <p className="text-sm font-medium capitalize">{type.replace(/_/g, ' ')}</p>
                        <p className="text-xs text-slate-500">{mins} dk ortalama</p>
                      </div>
                    </div>
                  ))}
                  {Object.keys(dashboard?.avg_resolution_by_type || {}).length === 0 && (
                    <p className="text-slate-400 text-sm col-span-3 text-center py-4">Henuz veri yok</p>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Request Queue */}
            <Card>
              <CardHeader><CardTitle className="text-base">Aktif Talep Kuyrugu</CardTitle></CardHeader>
              <CardContent>
                {(dashboard?.request_queue || []).length === 0 ? (
                  <div className="text-center py-8 text-slate-400" data-testid="empty-queue">
                    <CheckCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>Tum talepler cozulmus</p>
                  </div>
                ) : (
                  <div className="space-y-2" data-testid="request-queue">
                    {(dashboard?.request_queue || []).map((r, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                        <div className="flex items-center gap-3">
                          <span className="text-lg">{TYPE_ICONS[r.request_type] || '?'}</span>
                          <div>
                            <p className="text-sm font-medium">{r.description?.slice(0, 60)}</p>
                            <p className="text-xs text-slate-500">Oda: {r.room_id} | {r.created_at?.replace('T', ' ').slice(0, 16)}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge className={STATUS_COLORS[r.status] || ''}>{r.status}</Badge>
                          {r.priority === 'urgent' && <Badge variant="destructive">Acil</Badge>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Requests Tab */}
        {activeTab === 'requests' && (
          <div className="space-y-4">
            {/* Filters */}
            <div className="flex flex-wrap gap-2" data-testid="request-filters">
              <div className="flex gap-1">
                {[null, 'open', 'assigned', 'in_progress', 'resolved'].map(s => (
                  <Button key={s || 'all'} variant={statusFilter === s ? 'default' : 'outline'} size="sm"
                    data-testid={`filter-status-${s || 'all'}`}
                    onClick={() => setStatusFilter(s)}>
                    {s ? s.replace(/_/g, ' ') : 'Tumu'}
                  </Button>
                ))}
              </div>
              <div className="flex gap-1">
                {[null, 'housekeeping', 'maintenance', 'concierge', 'room_service', 'complaint'].map(t => (
                  <Button key={t || 'all_type'} variant={typeFilter === t ? 'default' : 'outline'} size="sm"
                    data-testid={`filter-type-${t || 'all'}`}
                    onClick={() => setTypeFilter(t)}>
                    {t ? `${TYPE_ICONS[t] || ''} ${t.replace(/_/g, ' ')}` : 'Tum Tipler'}
                  </Button>
                ))}
              </div>
            </div>

            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm" data-testid="requests-table">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50">
                        <th className="text-left py-3 px-4 text-slate-500 font-medium">Tip</th>
                        <th className="text-left py-3 px-4 text-slate-500 font-medium">Aciklama</th>
                        <th className="text-center py-3 px-4 text-slate-500 font-medium">Oda</th>
                        <th className="text-center py-3 px-4 text-slate-500 font-medium">Oncelik</th>
                        <th className="text-center py-3 px-4 text-slate-500 font-medium">Durum</th>
                        <th className="text-center py-3 px-4 text-slate-500 font-medium">Tarih</th>
                        <th className="text-center py-3 px-4 text-slate-500 font-medium">Islemler</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(requests?.requests || []).map((r, i) => (
                        <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                          <td className="py-2 px-4">
                            <span className="text-lg mr-1">{TYPE_ICONS[r.request_type] || '?'}</span>
                            <span className="capitalize text-xs">{r.request_type?.replace(/_/g, ' ')}</span>
                          </td>
                          <td className="py-2 px-4 max-w-[200px] truncate">{r.description}</td>
                          <td className="py-2 px-4 text-center">{r.room_id || '-'}</td>
                          <td className="py-2 px-4 text-center">
                            <Badge variant={r.priority === 'urgent' ? 'destructive' : 'secondary'}>{r.priority}</Badge>
                          </td>
                          <td className="py-2 px-4 text-center">
                            <Badge className={STATUS_COLORS[r.status] || ''}>{r.status}</Badge>
                          </td>
                          <td className="py-2 px-4 text-center text-xs text-slate-500">
                            {r.created_at?.replace('T', ' ').slice(0, 16)}
                          </td>
                          <td className="py-2 px-4 text-center">
                            {r.status === 'open' && (
                              <Button variant="outline" size="sm" onClick={() => updateRequestStatus(r.id, 'in_progress')}
                                data-testid={`start-${r.id}`}>Basla</Button>
                            )}
                            {r.status === 'in_progress' && (
                              <Button variant="outline" size="sm" onClick={() => updateRequestStatus(r.id, 'resolved')}
                                data-testid={`resolve-${r.id}`}>Coz</Button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {(requests?.requests || []).length === 0 && (
                        <tr><td colSpan={7} className="text-center py-8 text-slate-400">Talep bulunamadi</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Messaging Tab */}
        {activeTab === 'messaging' && (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Otomatik Mesaj Sablonlari</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3" data-testid="message-templates">
                  {(templates?.templates || []).map((t, i) => (
                    <div key={i} className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
                      <div className="shrink-0 mt-0.5">
                        {t.channel === 'email' ? <Mail className="w-5 h-5 text-sky-500" /> :
                         t.channel === 'sms' ? <Phone className="w-5 h-5 text-emerald-500" /> :
                         <Globe className="w-5 h-5 text-teal-500" />}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-sm">{t.name}</p>
                          <Badge variant="outline" className="text-xs">{t.trigger}</Badge>
                          <Badge variant="secondary" className="text-xs">{t.channel}</Badge>
                        </div>
                        {t.subject && <p className="text-sm text-slate-600 mt-1">Konu: {t.subject}</p>}
                        <p className="text-xs text-slate-500 mt-1">{t.body}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Reviews Tab */}
        {activeTab === 'reviews' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Average Rating */}
              <Card>
                <CardContent className="p-6 text-center">
                  <Star className="w-10 h-10 text-amber-400 mx-auto mb-2" />
                  <p className="text-4xl font-bold text-slate-900" data-testid="review-avg-rating">{rep.average_rating || '-'}</p>
                  <p className="text-sm text-slate-500 mt-1">{rep.total_reviews || 0} degerlendirme</p>
                </CardContent>
              </Card>
              {/* Distribution */}
              <Card className="lg:col-span-2">
                <CardHeader><CardTitle className="text-base">Puan Dagilimi</CardTitle></CardHeader>
                <CardContent>
                  <div className="space-y-2" data-testid="rating-distribution">
                    {[5, 4, 3, 2, 1].map(r => {
                      const count = dist[r] || 0;
                      const pct = rep.total_reviews ? (count / rep.total_reviews * 100) : 0;
                      return (
                        <div key={r} className="flex items-center gap-3">
                          <span className="text-sm font-medium w-4">{r}</span>
                          <Star className="w-4 h-4 text-amber-400" />
                          <div className="flex-1 bg-slate-200 rounded-full h-3">
                            <div className="h-3 rounded-full bg-amber-400 transition-all" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-slate-500 w-12 text-right">{count} ({pct.toFixed(0)}%)</span>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Monthly Trend */}
            {(rep.recent_trend || []).length > 0 && (
              <Card>
                <CardHeader><CardTitle className="text-base">Aylik Puan Trendi</CardTitle></CardHeader>
                <CardContent>
                  <div className="flex gap-4 overflow-x-auto pb-2" data-testid="monthly-trend">
                    {(rep.recent_trend || []).map((m, i) => (
                      <div key={i} className="flex-shrink-0 text-center p-3 bg-slate-50 rounded-lg min-w-[100px]">
                        <p className="text-xs text-slate-500">{m.month}</p>
                        <p className="text-xl font-bold text-slate-900 mt-1">{m.avg_rating}</p>
                        <p className="text-xs text-slate-400">{m.count} yorum</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}
