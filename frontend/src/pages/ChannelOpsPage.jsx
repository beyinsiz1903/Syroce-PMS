import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  XCircle,
  Wifi,
  WifiOff,
  Zap,
  Send,
  RotateCcw,
  Eye,
  ArrowRight,
  Timer,
  Shield,
  TrendingUp,
  AlertCircle,
  Inbox,
} from 'lucide-react';

const API = import.meta.env.VITE_BACKEND_URL;

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ── Helper components ──────────────────────────────────────────────

const StatCard = ({ title, value, subtitle, icon: Icon, color = 'blue', badge }) => {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    orange: 'bg-orange-50 text-orange-700 border-orange-200',
    purple: 'bg-purple-50 text-purple-700 border-purple-200',
    gray: 'bg-gray-50 text-gray-700 border-gray-200',
  };
  return (
    <div className={`rounded-lg border p-4 ${colorMap[color] || colorMap.blue}`} data-testid={`stat-${title?.replace(/\s+/g, '-')?.toLowerCase()}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium uppercase tracking-wider opacity-75">{title}</span>
        {Icon && <Icon className="w-4 h-4 opacity-60" />}
      </div>
      <div className="flex items-end justify-between">
        <div>
          <p className="text-2xl font-bold">{value}</p>
          {subtitle && <p className="text-xs mt-1 opacity-75">{subtitle}</p>}
        </div>
        {badge && (
          <Badge variant="outline" className="text-xs">
            {badge}
          </Badge>
        )}
      </div>
    </div>
  );
};

const SeverityBadge = ({ severity }) => {
  const map = {
    critical: 'bg-red-100 text-red-800',
    warning: 'bg-orange-100 text-orange-800',
    info: 'bg-blue-100 text-blue-800',
    success: 'bg-green-100 text-green-800',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${map[severity] || map.info}`}>
      {severity}
    </span>
  );
};

const StatusBadge = ({ status }) => {
  const map = {
    succeeded: { color: 'bg-green-100 text-green-800', icon: CheckCircle2 },
    failed: { color: 'bg-red-100 text-red-800', icon: XCircle },
    dlq: { color: 'bg-red-100 text-red-800', icon: Inbox },
    retrying: { color: 'bg-orange-100 text-orange-800', icon: RotateCcw },
    pending: { color: 'bg-gray-100 text-gray-800', icon: Clock },
    delivering: { color: 'bg-blue-100 text-blue-800', icon: Send },
    healthy: { color: 'bg-green-100 text-green-800', icon: CheckCircle2 },
    degraded: { color: 'bg-orange-100 text-orange-800', icon: AlertTriangle },
    critical: { color: 'bg-red-100 text-red-800', icon: XCircle },
  };
  const s = map[status] || map.pending;
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${s.color}`}>
      <Icon className="w-3 h-3" />
      {status}
    </span>
  );
};

const HealthIndicator = ({ health }) => {
  const map = {
    healthy: { color: 'bg-green-500', label: 'Sağlıklı' },
    degraded: { color: 'bg-orange-500', label: 'Düşük' },
    critical: { color: 'bg-red-500', label: 'Kritik' },
  };
  const h = map[health] || map.healthy;
  return (
    <div className="flex items-center gap-2">
      <div className={`w-2.5 h-2.5 rounded-full ${h.color} animate-pulse`} />
      <span className="text-sm font-medium">{h.label}</span>
    </div>
  );
};

const TimeAgo = ({ timestamp }) => {
  if (!timestamp) return <span className="text-xs text-gray-400">—</span>;
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHour = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  let text;
  if (diffMin < 1) text = 'az önce';
  else if (diffMin < 60) text = `${diffMin} dk önce`;
  else if (diffHour < 24) text = `${diffHour} sa önce`;
  else text = `${diffDay} gün önce`;

  return <span className="text-xs text-gray-500" title={then.toLocaleString('tr-TR')}>{text}</span>;
};

// ── Main Component ─────────────────────────────────────────────────

const ChannelOpsPage = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [refreshing, setRefreshing] = useState(false);
  const [dlqItems, setDlqItems] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [opsEvents, setOpsEvents] = useState([]);
  const [retryingDlq, setRetryingDlq] = useState(null);

  const fetchDashboard = useCallback(async () => {
    try {
      const resp = await axios.get(`${API}/api/ops-events/dashboard-summary`, {
        headers: getAuthHeaders(),
      });
      setData(resp.data);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || 'Veri alınamadı');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const fetchDlq = useCallback(async () => {
    try {
      const resp = await axios.get(`${API}/api/ops-events/webhook-dlq`, {
        headers: getAuthHeaders(),
      });
      setDlqItems(resp.data?.items || []);
    } catch {}
  }, []);

  const fetchDeliveries = useCallback(async () => {
    try {
      const resp = await axios.get(`${API}/api/ops-events/webhook-deliveries?limit=50`, {
        headers: getAuthHeaders(),
      });
      setDeliveries(resp.data?.deliveries || []);
    } catch {}
  }, []);

  const fetchOpsEvents = useCallback(async () => {
    try {
      const resp = await axios.get(`${API}/api/ops-events/list?limit=50`, {
        headers: getAuthHeaders(),
      });
      setOpsEvents(resp.data?.events || []);
    } catch {}
  }, []);

  useEffect(() => {
    fetchDashboard();
    const interval = setInterval(fetchDashboard, 15000); // 15s auto-refresh
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  useEffect(() => {
    if (activeTab === 'webhooks') {
      fetchDeliveries();
      fetchDlq();
    } else if (activeTab === 'events') {
      fetchOpsEvents();
    }
  }, [activeTab, fetchDeliveries, fetchDlq, fetchOpsEvents]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchDashboard();
    if (activeTab === 'webhooks') {
      fetchDeliveries();
      fetchDlq();
    }
    if (activeTab === 'events') fetchOpsEvents();
  };

  const handleDlqRetry = async (dlqId) => {
    setRetryingDlq(dlqId);
    try {
      await axios.post(`${API}/api/ops-events/webhook-dlq/${dlqId}/retry`, {}, {
        headers: getAuthHeaders(),
      });
      fetchDlq();
      fetchDeliveries();
      fetchDashboard();
    } catch (err) {
      alert(err.response?.data?.detail || 'Retry başarısız');
    } finally {
      setRetryingDlq(null);
    }
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-96" data-testid="ops-loading">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
          <span className="ml-3 text-gray-600">Operasyon verileri yükleniyor...</span>
        </div>
      </Layout>
    );
  }

  const wh = data?.webhook_delivery || {};
  const rl = data?.rate_limit || {};
  const channels = data?.channels || [];
  const recentEvents = data?.recent_events || [];
  const recentImports = data?.recent_imports || [];
  const lastPushes = data?.last_successful_pushes || [];

  return (
    <Layout>
      <div className="p-4 md:p-6 space-y-6 max-w-[1400px] mx-auto" data-testid="channel-ops-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Activity className="w-6 h-6 text-blue-600" />
              Kanal Operasyon Merkezi
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Webhook teslimat, rate limit, kanal sağlığı ve operasyonel olaylar
            </p>
          </div>
          <div className="flex items-center gap-3">
            {data?.generated_at && (
              <span className="text-xs text-gray-400">
                Son güncelleme: <TimeAgo timestamp={data.generated_at} />
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              data-testid="refresh-button"
            >
              <RefreshCw className={`w-4 h-4 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
              Yenile
            </Button>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          <TabsList className="bg-gray-100">
            <TabsTrigger value="overview" data-testid="tab-overview">Genel Bakış</TabsTrigger>
            <TabsTrigger value="webhooks" data-testid="tab-webhooks">Webhook Teslimat</TabsTrigger>
            <TabsTrigger value="channels" data-testid="tab-channels">Kanal Sağlığı</TabsTrigger>
            <TabsTrigger value="events" data-testid="tab-events">Olay Akışı</TabsTrigger>
          </TabsList>

          {/* ═══════ OVERVIEW TAB ═══════ */}
          <TabsContent value="overview" className="space-y-6" data-testid="tab-content-overview">
            {/* KPI Row */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              <StatCard
                title="Webhook Toplam"
                value={wh.total || 0}
                icon={Send}
                color="blue"
                subtitle={`%${wh.success_rate || 0} başarı`}
              />
              <StatCard
                title="Başarılı"
                value={wh.succeeded || 0}
                icon={CheckCircle2}
                color="green"
              />
              <StatCard
                title="Başarısız"
                value={wh.failed || 0}
                icon={XCircle}
                color="red"
              />
              <StatCard
                title="Retry Bekliyor"
                value={wh.retrying || 0}
                icon={RotateCcw}
                color="orange"
              />
              <StatCard
                title="DLQ Bekliyor"
                value={wh.dlq_pending || 0}
                icon={Inbox}
                color={wh.dlq_pending > 0 ? 'red' : 'gray'}
              />
              <StatCard
                title="Throttle (24s)"
                value={rl.throttle_events_24h || 0}
                icon={Timer}
                color={rl.is_throttled ? 'orange' : 'gray'}
                subtitle={rl.is_throttled ? 'Rate limit aktif' : 'Normal'}
              />
            </div>

            {/* Rate Limit Banner */}
            {rl.is_throttled && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-center gap-3" data-testid="rate-limit-banner">
                <AlertTriangle className="w-5 h-5 text-orange-600 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-orange-800">HotelRunner Rate Limit Aktif</p>
                  <p className="text-xs text-orange-600">
                    Son 24 saatte {rl.throttle_events_24h} throttle olayı, {rl.rate_limited_pushes_24h} push rate limit'e takıldı.
                    {rl.last_429_at && <> Son 429: <TimeAgo timestamp={rl.last_429_at} /></>}
                  </p>
                </div>
              </div>
            )}

            {/* Channels Grid */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Wifi className="w-4 h-4" />
                  Kanal Durumu
                </CardTitle>
              </CardHeader>
              <CardContent>
                {channels.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-4">Bağlı kanal bulunamadı</p>
                ) : (
                  <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {channels.map((ch, i) => (
                      <div
                        key={ch.connector_id || i}
                        className="border rounded-lg p-4 space-y-3"
                        data-testid={`channel-card-${ch.provider}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {ch.health === 'healthy' ? (
                              <Wifi className="w-4 h-4 text-green-600" />
                            ) : (
                              <WifiOff className="w-4 h-4 text-red-600" />
                            )}
                            <span className="font-medium text-sm capitalize">{ch.provider}</span>
                          </div>
                          <HealthIndicator health={ch.health} />
                        </div>
                        {ch.property_name && (
                          <p className="text-xs text-gray-500">{ch.property_name}</p>
                        )}
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <span className="text-gray-500">Push (24s):</span>
                            <span className="ml-1 font-medium">{ch.total_pushes_24h}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Başarısız:</span>
                            <span className="ml-1 font-medium text-red-600">{ch.failed_pushes_24h}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Başarı:</span>
                            <span className="ml-1 font-medium">%{ch.push_success_rate_24h}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Son sync:</span>
                            <TimeAgo timestamp={ch.last_sync_at} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Recent Events + Last Pushes */}
            <div className="grid md:grid-cols-2 gap-4">
              {/* Recent Failures */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <XCircle className="w-4 h-4 text-red-500" />
                    Son Başarısız Teslimatlar
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {(wh.recent_failures || []).length === 0 ? (
                    <p className="text-sm text-gray-500 text-center py-4">Başarısız teslimat yok</p>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                      {(wh.recent_failures || []).map((f, i) => (
                        <div key={f.id || i} className="border rounded p-3 text-xs space-y-1 bg-red-50/50">
                          <div className="flex items-center justify-between">
                            <StatusBadge status={f.status} />
                            <TimeAgo timestamp={f.created_at} />
                          </div>
                          <p className="text-gray-700 font-medium">{f.event}</p>
                          <p className="text-gray-500 truncate">{f.url}</p>
                          <p className="text-red-600">{f.last_error}</p>
                          <p className="text-gray-400">Deneme: {f.attempt_count}/{5}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Last Successful Pushes */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-green-500" />
                    Son Başarılı Push'lar
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {lastPushes.length === 0 ? (
                    <p className="text-sm text-gray-500 text-center py-4">Henüz push kaydı yok</p>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                      {lastPushes.map((p, i) => (
                        <div key={i} className="border rounded p-3 text-xs space-y-1 bg-green-50/50">
                          <div className="flex items-center justify-between">
                            <span className="font-medium capitalize">{p.provider}</span>
                            <TimeAgo timestamp={p.last_success_at} />
                          </div>
                          <p className="text-gray-500">Latency: {p.latency_ms}ms</p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Recent Imports */}
            {recentImports.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <ArrowRight className="w-4 h-4" />
                    Son Import İşlemleri
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-[200px] overflow-y-auto">
                    {recentImports.map((ev, i) => (
                      <div key={ev.id || i} className="border rounded p-3 text-xs flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <SeverityBadge severity={ev.severity} />
                          <span className="font-medium">{ev.title}</span>
                        </div>
                        <TimeAgo timestamp={ev.created_at} />
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* ═══════ WEBHOOKS TAB ═══════ */}
          <TabsContent value="webhooks" className="space-y-6" data-testid="tab-content-webhooks">
            {/* DLQ Section */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Inbox className="w-4 h-4 text-red-500" />
                  Dead Letter Queue (DLQ)
                  {dlqItems.filter(d => d.status === 'pending').length > 0 && (
                    <Badge className="bg-red-500 text-white ml-2">
                      {dlqItems.filter(d => d.status === 'pending').length} bekliyor
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {dlqItems.length === 0 ? (
                  <div className="text-center py-6 text-gray-500">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-green-500 opacity-50" />
                    <p className="text-sm">DLQ boş — tüm teslimatlar başarılı</p>
                  </div>
                ) : (
                  <div className="space-y-3 max-h-[400px] overflow-y-auto">
                    {dlqItems.map((item) => (
                      <div key={item.id} className="border border-red-200 bg-red-50/50 rounded-lg p-4 space-y-2" data-testid={`dlq-item-${item.id}`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <StatusBadge status={item.status} />
                            <span className="text-sm font-medium">{item.event}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <TimeAgo timestamp={item.created_at} />
                            {item.status === 'pending' && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="text-xs h-7"
                                onClick={() => handleDlqRetry(item.id)}
                                disabled={retryingDlq === item.id}
                                data-testid={`dlq-retry-${item.id}`}
                              >
                                {retryingDlq === item.id ? (
                                  <RefreshCw className="w-3 h-3 animate-spin mr-1" />
                                ) : (
                                  <RotateCcw className="w-3 h-3 mr-1" />
                                )}
                                Retry
                              </Button>
                            )}
                          </div>
                        </div>
                        <div className="text-xs space-y-1">
                          <p><span className="text-gray-500">URL:</span> <span className="text-gray-700">{item.url}</span></p>
                          <p><span className="text-gray-500">Deneme:</span> <span className="text-gray-700">{item.attempt_count}/{5}</span></p>
                          <p><span className="text-gray-500">Son Hata:</span> <span className="text-red-600">{item.last_error}</span></p>
                          <p><span className="text-gray-500">Agency:</span> <span className="text-gray-700">{item.agency_id}</span></p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Delivery History */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Send className="w-4 h-4" />
                  Teslimat Geçmişi
                </CardTitle>
              </CardHeader>
              <CardContent>
                {deliveries.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-4">Henüz teslimat kaydı yok</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs" data-testid="deliveries-table">
                      <thead>
                        <tr className="border-b text-left text-gray-500">
                          <th className="pb-2 pr-3">Durum</th>
                          <th className="pb-2 pr-3">Olay</th>
                          <th className="pb-2 pr-3">URL</th>
                          <th className="pb-2 pr-3">Deneme</th>
                          <th className="pb-2 pr-3">Son Hata</th>
                          <th className="pb-2">Zaman</th>
                        </tr>
                      </thead>
                      <tbody>
                        {deliveries.map((d) => (
                          <tr key={d.id} className="border-b last:border-0 hover:bg-gray-50">
                            <td className="py-2 pr-3"><StatusBadge status={d.status} /></td>
                            <td className="py-2 pr-3 font-medium">{d.event}</td>
                            <td className="py-2 pr-3 text-gray-500 max-w-[200px] truncate">{d.url}</td>
                            <td className="py-2 pr-3">{d.attempt_count}/{d.max_attempts || 5}</td>
                            <td className="py-2 pr-3 text-red-600 max-w-[200px] truncate">{d.last_error || '—'}</td>
                            <td className="py-2"><TimeAgo timestamp={d.created_at} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════ CHANNELS TAB ═══════ */}
          <TabsContent value="channels" className="space-y-6" data-testid="tab-content-channels">
            {/* Rate Limit Status */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Shield className="w-4 h-4 text-orange-500" />
                  HotelRunner Rate Limit Durumu
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="text-center p-3 rounded-lg bg-gray-50">
                    <p className="text-xs text-gray-500">Durum</p>
                    <p className={`text-sm font-bold mt-1 ${rl.is_throttled ? 'text-orange-600' : 'text-green-600'}`}>
                      {rl.is_throttled ? 'THROTTLED' : 'NORMAL'}
                    </p>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-gray-50">
                    <p className="text-xs text-gray-500">Throttle (24s)</p>
                    <p className="text-sm font-bold mt-1">{rl.throttle_events_24h || 0}</p>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-gray-50">
                    <p className="text-xs text-gray-500">Rate Limited Push</p>
                    <p className="text-sm font-bold mt-1">{rl.rate_limited_pushes_24h || 0}</p>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-gray-50">
                    <p className="text-xs text-gray-500">Son 429</p>
                    <div className="mt-1">{rl.last_429_at ? <TimeAgo timestamp={rl.last_429_at} /> : <span className="text-sm text-gray-400">Yok</span>}</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Detailed Channel Cards */}
            {channels.length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-gray-500">
                  <WifiOff className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">Bağlı kanal bulunamadı</p>
                </CardContent>
              </Card>
            ) : (
              channels.map((ch, i) => (
                <Card key={ch.connector_id || i} data-testid={`channel-detail-${ch.provider}`}>
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base flex items-center gap-2 capitalize">
                        {ch.health === 'healthy' ? (
                          <Wifi className="w-4 h-4 text-green-600" />
                        ) : (
                          <WifiOff className="w-4 h-4 text-red-600" />
                        )}
                        {ch.provider}
                        {ch.property_name && <span className="text-gray-400 font-normal">— {ch.property_name}</span>}
                      </CardTitle>
                      <HealthIndicator health={ch.health} />
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                      <StatCard title="Push (24s)" value={ch.total_pushes_24h} icon={Send} color="blue" />
                      <StatCard title="Başarısız" value={ch.failed_pushes_24h} icon={XCircle} color={ch.failed_pushes_24h > 0 ? 'red' : 'gray'} />
                      <StatCard title="Başarı Oranı" value={`%${ch.push_success_rate_24h}`} icon={TrendingUp} color="green" />
                      <StatCard title="Durum" value={ch.status || 'N/A'} icon={Zap} color="purple" />
                      <div className="rounded-lg border p-4 bg-gray-50 text-gray-700">
                        <p className="text-xs font-medium uppercase tracking-wider opacity-75 mb-2">Son Sync</p>
                        <TimeAgo timestamp={ch.last_sync_at} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          {/* ═══════ EVENTS TAB ═══════ */}
          <TabsContent value="events" className="space-y-4" data-testid="tab-content-events">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Activity className="w-4 h-4 text-blue-500" />
                  Operasyonel Olay Akışı
                  <Badge variant="outline" className="ml-2">{opsEvents.length} kayıt</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {opsEvents.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <Activity className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Henüz operasyonel olay kaydı yok</p>
                    <p className="text-xs text-gray-400 mt-1">Webhook teslimatları, push işlemleri ve rate limit olayları burada görünecek</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[600px] overflow-y-auto">
                    {opsEvents.map((ev) => (
                      <div
                        key={ev.id}
                        className={`border rounded-lg p-3 text-xs space-y-1 ${
                          ev.severity === 'critical' ? 'border-red-200 bg-red-50/50' :
                          ev.severity === 'warning' ? 'border-orange-200 bg-orange-50/50' :
                          ev.severity === 'success' ? 'border-green-200 bg-green-50/50' :
                          'border-gray-200 bg-gray-50/50'
                        }`}
                        data-testid={`event-${ev.id}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <SeverityBadge severity={ev.severity} />
                            <span className="font-medium text-gray-900">{ev.title}</span>
                          </div>
                          <TimeAgo timestamp={ev.created_at} />
                        </div>
                        <div className="flex items-center gap-3 text-gray-500">
                          <span className="bg-gray-100 px-2 py-0.5 rounded">{ev.event_type}</span>
                          {ev.channel && <span>Kanal: {ev.channel}</span>}
                          {ev.correlation_id && <span className="truncate max-w-[120px]">Corr: {ev.correlation_id}</span>}
                        </div>
                        {ev.details && Object.keys(ev.details).length > 0 && (
                          <details className="mt-1">
                            <summary className="text-gray-400 cursor-pointer hover:text-gray-600">Detaylar</summary>
                            <pre className="mt-1 p-2 bg-white rounded text-[10px] overflow-x-auto">
                              {JSON.stringify(ev.details, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
};

export default ChannelOpsPage;
