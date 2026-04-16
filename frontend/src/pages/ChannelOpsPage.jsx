import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import IncidentDrilldownDrawer from '@/components/ops/IncidentDrilldownDrawer';
import EarlyWarningPanel from '@/components/ops/EarlyWarningPanel';
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
  ChevronRight,
  Filter,
  Gauge,
  Target,
  BarChart3,
  Sparkles,
} from 'lucide-react';

const API = "";

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ── Helper components ──────────────────────────────────────────────

const StatCard = ({ title, value, subtitle, icon: Icon, color = 'blue', badge, onClick }) => {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    orange: 'bg-orange-50 text-orange-700 border-orange-200',
    purple: 'bg-purple-50 text-purple-700 border-purple-200',
    gray: 'bg-gray-50 text-gray-700 border-gray-200',
  };
  return (
    <div 
      className={`rounded-lg border p-4 ${colorMap[color] || colorMap.blue} ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''}`} 
      onClick={onClick}
      data-testid={`stat-${title?.replace(/\s+/g, '-')?.toLowerCase()}`}
    >
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

const HealthScoreBadge = ({ score, size = 'md' }) => {
  const getColor = (s) => {
    if (s >= 80) return 'bg-green-500';
    if (s >= 50) return 'bg-orange-500';
    return 'bg-red-500';
  };
  const getLabel = (s) => {
    if (s >= 80) return 'Sağlıklı';
    if (s >= 50) return 'Düşük';
    return 'Kritik';
  };
  const sizeClass = size === 'lg' ? 'w-14 h-14 text-lg' : 'w-10 h-10 text-sm';
  
  return (
    <div className="flex items-center gap-2">
      <div className={`${sizeClass} ${getColor(score)} rounded-full flex items-center justify-center text-white font-bold`}>
        {score}
      </div>
      <span className="text-sm font-medium text-gray-700">{getLabel(score)}</span>
    </div>
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

const PriorityBadge = ({ priority, label }) => {
  const map = {
    1: 'bg-red-600 text-white',
    2: 'bg-red-500 text-white',
    3: 'bg-orange-500 text-white',
    4: 'bg-yellow-500 text-gray-900',
    5: 'bg-green-500 text-white',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${map[priority] || map[4]}`}>
      {label || `P${priority}`}
    </span>
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

// ── Prioritized Incident Card ──────────────────────────────────────

const IncidentCard = ({ incident, onOpenTimeline, onRetry }) => {
  const getIcon = () => {
    if (incident.type === 'dlq') return <Inbox className="w-4 h-4" />;
    if (incident.priority <= 2) return <AlertCircle className="w-4 h-4" />;
    if (incident.priority <= 4) return <AlertTriangle className="w-4 h-4" />;
    return <CheckCircle2 className="w-4 h-4" />;
  };

  const getBorderColor = () => {
    if (incident.priority === 1) return 'border-red-400 bg-red-50/70';
    if (incident.priority === 2) return 'border-red-300 bg-red-50/50';
    if (incident.priority === 3) return 'border-orange-300 bg-orange-50/50';
    if (incident.priority === 4) return 'border-yellow-300 bg-yellow-50/50';
    return 'border-green-300 bg-green-50/50';
  };

  return (
    <div 
      className={`border rounded-lg p-3 ${getBorderColor()} hover:shadow-md transition-shadow cursor-pointer`}
      onClick={() => incident.correlation_id && onOpenTimeline(incident.correlation_id)}
      data-testid={`incident-card-${incident.id}`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          {getIcon()}
          <PriorityBadge priority={incident.priority} label={incident.priority_label} />
        </div>
        <TimeAgo timestamp={incident.created_at} />
      </div>
      
      <h4 className="font-medium text-sm text-gray-900 mb-1 line-clamp-1">{incident.title}</h4>
      
      {incident.description && (
        <p className="text-xs text-gray-600 line-clamp-2 mb-2">{incident.description}</p>
      )}
      
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2">
          {incident.event_type && (
            <span className="text-[10px] bg-gray-200 px-1.5 py-0.5 rounded">{incident.event_type}</span>
          )}
          {incident.status && <StatusBadge status={incident.status} />}
        </div>
        
        <div className="flex items-center gap-1">
          {incident.actionable && incident.action_type === 'retry' && (
            <Button
              size="sm"
              variant="outline"
              className="h-6 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                onRetry(incident.id);
              }}
              data-testid={`incident-retry-${incident.id}`}
            >
              <RotateCcw className="w-3 h-3 mr-1" />
              Retry
            </Button>
          )}
          {incident.correlation_id && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                onOpenTimeline(incident.correlation_id);
              }}
              data-testid={`incident-timeline-${incident.id}`}
            >
              <Eye className="w-3 h-3 mr-1" />
              Timeline
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Connector Health Card (Unified Contract) ───────────────────────

const ConnectorHealthCard = ({ connector, onOpenTimeline }) => {
  const getStatusBg = () => {
    if (connector.status === 'critical') return 'border-red-300 bg-red-50';
    if (connector.status === 'degraded') return 'border-orange-300 bg-orange-50';
    return 'border-green-300 bg-green-50';
  };

  return (
    <Card className={`${getStatusBg()} hover:shadow-md transition-shadow`} data-testid={`connector-health-${connector.provider}`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {connector.status === 'healthy' ? (
              <Wifi className="w-5 h-5 text-green-600" />
            ) : connector.status === 'degraded' ? (
              <Wifi className="w-5 h-5 text-orange-600" />
            ) : (
              <WifiOff className="w-5 h-5 text-red-600" />
            )}
            <div>
              <h3 className="font-semibold text-sm capitalize">{connector.provider}</h3>
              {connector.property_name && (
                <p className="text-xs text-gray-500">{connector.property_name}</p>
              )}
            </div>
          </div>
          <HealthScoreBadge score={connector.health_score} />
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs mb-3">
          <div className="flex justify-between">
            <span className="text-gray-500">Failure Rate (1s):</span>
            <span className={`font-medium ${connector.failure_rate_1h > 10 ? 'text-red-600' : 'text-gray-700'}`}>
              %{connector.failure_rate_1h}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">DLQ:</span>
            <span className={`font-medium ${connector.dlq_count > 0 ? 'text-red-600' : 'text-gray-700'}`}>
              {connector.dlq_count}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Retry Backlog:</span>
            <span className={`font-medium ${connector.retry_backlog > 5 ? 'text-orange-600' : 'text-gray-700'}`}>
              {connector.retry_backlog}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Throttle:</span>
            <span className={`font-medium ${connector.throttle_active ? 'text-orange-600' : 'text-gray-700'}`}>
              {connector.throttle_active ? 'Aktif' : 'Normal'}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between text-xs border-t pt-2">
          <div>
            <span className="text-gray-500">Son Başarılı:</span>
            <TimeAgo timestamp={connector.last_success_at} />
          </div>
          <div className="flex items-center gap-1">
            <span className="text-gray-500">1s Ops:</span>
            <span className="font-medium">{connector.metrics_1h?.total_operations || 0}</span>
            <span className={`text-green-600`}>(%{connector.metrics_1h?.success_rate || 0})</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// ── Main Component ─────────────────────────────────────────────────

const ChannelOpsPage = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [refreshing, setRefreshing] = useState(false);
  const [dlqItems, setDlqItems] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [opsEvents, setOpsEvents] = useState([]);
  const [retryingDlq, setRetryingDlq] = useState(null);
  
  // Sprint 2: New state
  const [prioritizedIncidents, setPrioritizedIncidents] = useState({ incidents: [], counts: {} });
  const [connectorsHealth, setConnectorsHealth] = useState({ connectors: [], summary: {} });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedCorrelationId, setSelectedCorrelationId] = useState(null);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [incidentFilter, setIncidentFilter] = useState('all');
  const [earlyWarningSummary, setEarlyWarningSummary] = useState(null);
  const [highlightProvider, setHighlightProvider] = useState(null);

  const fetchEarlyWarningSummary = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/early-warnings/summary`, {
        headers: getAuthHeaders(),
      });
      setEarlyWarningSummary(resp.data);
    } catch (e) { /* silently ignore */ }
  }, []);

  const fetchDashboard = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/dashboard-summary`, {
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
      const resp = await axios.get(`/ops-events/webhook-dlq`, {
        headers: getAuthHeaders(),
      });
      setDlqItems(resp.data?.items || []);
    } catch (e) { /* silently ignore */ }
  }, []);

  const fetchDeliveries = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/webhook-deliveries?limit=50`, {
        headers: getAuthHeaders(),
      });
      setDeliveries(resp.data?.deliveries || []);
    } catch (e) { /* silently ignore */ }
  }, []);

  const fetchOpsEvents = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/list?limit=50`, {
        headers: getAuthHeaders(),
      });
      setOpsEvents(resp.data?.events || []);
    } catch (e) { /* silently ignore */ }
  }, []);

  // Sprint 2: Fetch prioritized incidents
  const fetchPrioritizedIncidents = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/incidents/prioritized?include_resolved=true`, {
        headers: getAuthHeaders(),
      });
      setPrioritizedIncidents(resp.data);
    } catch (e) { /* silently ignore */ }
  }, []);

  // Sprint 2: Fetch connectors health
  const fetchConnectorsHealth = useCallback(async () => {
    try {
      const resp = await axios.get(`/ops-events/connectors/health`, {
        headers: getAuthHeaders(),
      });
      setConnectorsHealth(resp.data);
    } catch (e) { /* silently ignore */ }
  }, []);

  useEffect(() => {
    fetchDashboard();
    fetchPrioritizedIncidents();
    fetchConnectorsHealth();
    fetchEarlyWarningSummary();
    const interval = setInterval(() => {
      fetchDashboard();
      fetchPrioritizedIncidents();
      fetchEarlyWarningSummary();
    }, 15000); // 15s auto-refresh
    return () => clearInterval(interval);
  }, [fetchDashboard, fetchPrioritizedIncidents, fetchConnectorsHealth, fetchEarlyWarningSummary]);

  useEffect(() => {
    if (activeTab === 'webhooks') {
      fetchDeliveries();
      fetchDlq();
    } else if (activeTab === 'events') {
      fetchOpsEvents();
    } else if (activeTab === 'channels') {
      fetchConnectorsHealth();
    }
  }, [activeTab, fetchDeliveries, fetchDlq, fetchOpsEvents, fetchConnectorsHealth]);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchDashboard();
    fetchPrioritizedIncidents();
    fetchConnectorsHealth();
    fetchEarlyWarningSummary();
    if (activeTab === 'webhooks') {
      fetchDeliveries();
      fetchDlq();
    }
    if (activeTab === 'events') fetchOpsEvents();
  };

  const handleDlqRetry = async (dlqId) => {
    setRetryingDlq(dlqId);
    try {
      await axios.post(`/ops-events/webhook-dlq/${dlqId}/retry`, {}, {
        headers: getAuthHeaders(),
      });
      fetchDlq();
      fetchDeliveries();
      fetchDashboard();
      fetchPrioritizedIncidents();
    } catch (err) {
      alert(err.response?.data?.detail || 'Retry başarısız');
    } finally {
      setRetryingDlq(null);
    }
  };

  const openTimelineDrawer = (correlationId) => {
    setSelectedCorrelationId(correlationId);
    setSelectedEventId(null);
    setDrawerOpen(true);
  };

  const openEventDrawer = (eventId) => {
    setSelectedEventId(eventId);
    setSelectedCorrelationId(null);
    setDrawerOpen(true);
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    setSelectedCorrelationId(null);
    setSelectedEventId(null);
  };

  // Filter incidents
  const filteredIncidents = prioritizedIncidents.incidents.filter(inc => {
    if (incidentFilter === 'all') return true;
    if (incidentFilter === 'critical') return inc.priority <= 2;
    if (incidentFilter === 'warning') return inc.priority === 3 || inc.priority === 4;
    if (incidentFilter === 'resolved') return inc.priority === 5;
    return true;
  });

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="channel_ops">
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
  const healthSummary = connectorsHealth.summary || {};

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="channel_ops">
      <div className="p-4 md:p-6 space-y-6 max-w-[1400px] mx-auto" data-testid="channel-ops-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Activity className="w-6 h-6 text-blue-600" />
              Kanal Operasyon Merkezi
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Operasyonel kontrol, kök neden analizi ve aksiyon yönetimi
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Overall Health Badge */}
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100">
              <Gauge className="w-4 h-4" />
              <span className="text-sm font-medium">Genel Sağlık:</span>
              <StatusBadge status={healthSummary.overall_health || 'healthy'} />
            </div>
            {data?.generated_at && (
              <span className="text-xs text-gray-400 hidden md:block">
                Son: <TimeAgo timestamp={data.generated_at} />
              </span>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/cm-dashboard')}
              data-testid="cta-cm-dashboard"
            >
              <BarChart3 className="w-4 h-4 mr-1 text-blue-500" />
              CM Dashboard
            </Button>
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
            <TabsTrigger value="early-warning" data-testid="tab-early-warning">
              <Sparkles className="w-3 h-3 mr-1" />
              Erken Uyarı
            </TabsTrigger>
            <TabsTrigger value="incidents" data-testid="tab-incidents">
              Öncelikli Olaylar
              {prioritizedIncidents.counts?.dlq_pending > 0 && (
                <Badge className="ml-1.5 bg-red-500 text-white text-[10px] px-1.5">
                  {prioritizedIncidents.counts.dlq_pending}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="webhooks" data-testid="tab-webhooks">Webhook</TabsTrigger>
            <TabsTrigger value="channels" data-testid="tab-channels">Connector Sağlığı</TabsTrigger>
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
                onClick={() => setActiveTab('incidents')}
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
                onClick={() => setActiveTab('incidents')}
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

            {/* Early Warning Summary Card */}
            {earlyWarningSummary && (earlyWarningSummary.warning_count > 0 || earlyWarningSummary.system_health_indicator === 'critical') && (
              <Card className={`border-l-4 ${
                earlyWarningSummary.system_health_indicator === 'critical' ? 'border-l-red-500 bg-red-50/50' :
                earlyWarningSummary.system_health_indicator === 'degraded' ? 'border-l-orange-500 bg-orange-50/50' :
                'border-l-yellow-500 bg-yellow-50/50'
              }`} data-testid="early-warning-overview-card">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-purple-600" />
                      Erken Uyarı Durumu
                      {earlyWarningSummary.system_health_indicator === 'critical' && (
                        <Badge className="bg-red-500 text-white text-[10px]">Kritik</Badge>
                      )}
                      {earlyWarningSummary.system_health_indicator === 'degraded' && (
                        <Badge className="bg-orange-500 text-white text-[10px]">Bozulma Riski</Badge>
                      )}
                    </span>
                    <Button variant="ghost" size="sm" onClick={() => setActiveTab('early-warning')}>
                      Detaylı Görünüm <ChevronRight className="w-4 h-4 ml-1" />
                    </Button>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-6 mb-3">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-red-500" />
                      <span className="text-sm"><strong>{earlyWarningSummary.critical_count}</strong> kritik</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-orange-500" />
                      <span className="text-sm"><strong>{earlyWarningSummary.warning_count_warning}</strong> uyarı</span>
                    </div>
                    {earlyWarningSummary.connectors_at_risk_count > 0 && (
                      <div className="flex items-center gap-2">
                        <Shield className="w-4 h-4 text-blue-500" />
                        <span className="text-sm"><strong>{earlyWarningSummary.connectors_at_risk_count}</strong> connector risk altında</span>
                      </div>
                    )}
                  </div>
                  {earlyWarningSummary.top_warnings?.length > 0 && (
                    <div className="space-y-2">
                      {earlyWarningSummary.top_warnings.slice(0, 2).map((w, i) => (
                        <div key={i} className="flex items-center justify-between bg-white rounded-md p-2 border text-sm">
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${w.severity === 'critical' ? 'bg-red-500' : 'bg-orange-500'}`} />
                            <span className="truncate text-gray-700">{w.reason}</span>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                            <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${w.confidence >= 80 ? 'bg-red-100 text-red-700' : 'bg-orange-100 text-orange-700'}`}>
                              {w.confidence}%
                            </span>
                            <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={() => setActiveTab('early-warning')}>
                              <Eye className="w-3 h-3" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {earlyWarningSummary.connectors_at_risk?.length > 0 && (
                    <div className="flex items-center gap-2 mt-3">
                      <span className="text-xs text-gray-500">Risk altında:</span>
                      {earlyWarningSummary.connectors_at_risk.map((prov) => (
                        <Badge key={prov} variant="outline" className="bg-orange-50 border-orange-300 text-orange-800 capitalize text-[10px]">
                          {prov}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Connector Health Overview */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Gauge className="w-4 h-4" />
                    Connector Sağlık Özeti
                  </span>
                  <div className="flex items-center gap-2 text-sm font-normal">
                    <span className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
                      {healthSummary.healthy || 0}
                    </span>
                    <span className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full bg-orange-500" />
                      {healthSummary.degraded || 0}
                    </span>
                    <span className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                      {healthSummary.critical || 0}
                    </span>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {(connectorsHealth.connectors || []).length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-4">Bağlı connector bulunamadı</p>
                ) : (
                  <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {(connectorsHealth.connectors || []).map((conn) => (
                      <ConnectorHealthCard
                        key={conn.connector_id}
                        connector={conn}
                        onOpenTimeline={openTimelineDrawer}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Recent Incidents Quick View */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Target className="w-4 h-4 text-red-500" />
                    Öncelikli Olaylar (Son)
                  </span>
                  <Button variant="ghost" size="sm" onClick={() => setActiveTab('incidents')}>
                    Tümünü Gör <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {filteredIncidents.length === 0 ? (
                  <div className="text-center py-6 text-gray-500">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-green-500 opacity-50" />
                    <p className="text-sm">Bekleyen kritik olay yok</p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[300px] overflow-y-auto">
                    {filteredIncidents.slice(0, 5).map((inc) => (
                      <IncidentCard
                        key={inc.id}
                        incident={inc}
                        onOpenTimeline={openTimelineDrawer}
                        onRetry={handleDlqRetry}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════ EARLY WARNING TAB (Sprint 4) ═══════ */}
          <TabsContent value="early-warning" className="space-y-6" data-testid="tab-content-early-warning">
            <EarlyWarningPanel
              onViewConnector={(provider) => {
                setHighlightProvider(provider);
                setActiveTab('channels');
              }}
              onOpenTimeline={(connectorId) => {
                openTimelineDrawer(connectorId);
              }}
              onOpenBacklog={() => {
                setActiveTab('incidents');
              }}
            />
          </TabsContent>

          {/* ═══════ INCIDENTS TAB (Sprint 2 P1) ═══════ */}
          <TabsContent value="incidents" className="space-y-6" data-testid="tab-content-incidents">
            {/* Incident Counts */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <StatCard
                title="DLQ Bekliyor"
                value={prioritizedIncidents.counts?.dlq_pending || 0}
                icon={Inbox}
                color="red"
              />
              <StatCard
                title="Throttle Aktif"
                value={prioritizedIncidents.counts?.throttle_active || 0}
                icon={Timer}
                color="orange"
              />
              <StatCard
                title="Terminal Failure"
                value={prioritizedIncidents.counts?.terminal_failures || 0}
                icon={XCircle}
                color="red"
              />
              <StatCard
                title="Uyarılar"
                value={prioritizedIncidents.counts?.warnings || 0}
                icon={AlertTriangle}
                color="orange"
              />
              <StatCard
                title="Çözülen"
                value={prioritizedIncidents.counts?.resolved || 0}
                icon={CheckCircle2}
                color="green"
              />
            </div>

            {/* Filter */}
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-gray-500" />
              <span className="text-sm text-gray-500">Filtre:</span>
              {['all', 'critical', 'warning', 'resolved'].map((filter) => (
                <Button
                  key={filter}
                  variant={incidentFilter === filter ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setIncidentFilter(filter)}
                  data-testid={`filter-${filter}`}
                >
                  {filter === 'all' && 'Tümü'}
                  {filter === 'critical' && 'Kritik'}
                  {filter === 'warning' && 'Uyarı'}
                  {filter === 'resolved' && 'Çözülen'}
                </Button>
              ))}
            </div>

            {/* Prioritized Incident List */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Target className="w-4 h-4" />
                  Öncelikli Olay Listesi
                  <Badge variant="outline" className="ml-2">{filteredIncidents.length} olay</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {filteredIncidents.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-green-500 opacity-50" />
                    <p className="text-sm">Seçili filtreye göre olay bulunamadı</p>
                  </div>
                ) : (
                  <div className="space-y-3 max-h-[600px] overflow-y-auto">
                    {filteredIncidents.map((inc) => (
                      <IncidentCard
                        key={inc.id}
                        incident={inc}
                        onOpenTimeline={openTimelineDrawer}
                        onRetry={handleDlqRetry}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
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
                      <div 
                        key={item.id} 
                        className="border border-red-200 bg-red-50/50 rounded-lg p-4 space-y-2 cursor-pointer hover:shadow-md transition-shadow" 
                        onClick={() => item.correlation_id && openTimelineDrawer(item.correlation_id)}
                        data-testid={`dlq-item-${item.id}`}
                      >
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
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDlqRetry(item.id);
                                }}
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
                            {item.correlation_id && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-xs h-7"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openTimelineDrawer(item.correlation_id);
                                }}
                              >
                                <Eye className="w-3 h-3 mr-1" />
                                Timeline
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
                          <th className="pb-2 pr-3">Zaman</th>
                          <th className="pb-2">Aksiyon</th>
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
                            <td className="py-2 pr-3"><TimeAgo timestamp={d.created_at} /></td>
                            <td className="py-2">
                              {d.correlation_id && (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-6 text-xs"
                                  onClick={() => openTimelineDrawer(d.correlation_id)}
                                >
                                  <Eye className="w-3 h-3" />
                                </Button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ═══════ CHANNELS TAB (Sprint 2 P1 - Unified Health Contract) ═══════ */}
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

            {/* Provider Filter */}
            {highlightProvider && (
              <div className="flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                <Filter className="w-4 h-4 text-blue-500" />
                <span className="text-sm text-blue-700">
                  Filtre: <strong className="capitalize">{highlightProvider}</strong>
                </span>
                <Button variant="ghost" size="sm" className="h-6 text-xs ml-auto" onClick={() => setHighlightProvider(null)}>
                  Filtreyi Kaldır
                </Button>
              </div>
            )}

            {/* Unified Connector Health Cards */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Gauge className="w-4 h-4" />
                    Connector Sağlık Durumu (Standart Şema)
                  </span>
                  <div className="flex items-center gap-2 text-sm font-normal">
                    <span className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
                      {healthSummary.healthy || 0} Sağlıklı
                    </span>
                    <span className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full bg-orange-500" />
                      {healthSummary.degraded || 0} Düşük
                    </span>
                    <span className="flex items-center gap-1">
                      <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                      {healthSummary.critical || 0} Kritik
                    </span>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {(connectorsHealth.connectors || []).length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <WifiOff className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Bağlı connector bulunamadı</p>
                  </div>
                ) : (
                  <div className="grid md:grid-cols-2 gap-4">
                    {(connectorsHealth.connectors || [])
                      .filter(conn => !highlightProvider || (conn.provider || '').toLowerCase() === highlightProvider.toLowerCase())
                      .map((conn) => (
                      <ConnectorHealthCard
                        key={conn.connector_id}
                        connector={conn}
                        onOpenTimeline={openTimelineDrawer}
                      />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
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
                        className={`border rounded-lg p-3 text-xs space-y-1 cursor-pointer hover:shadow-md transition-shadow ${
                          ev.severity === 'critical' ? 'border-red-200 bg-red-50/50' :
                          ev.severity === 'warning' ? 'border-orange-200 bg-orange-50/50' :
                          ev.severity === 'success' ? 'border-green-200 bg-green-50/50' :
                          'border-gray-200 bg-gray-50/50'
                        }`}
                        onClick={() => ev.correlation_id ? openTimelineDrawer(ev.correlation_id) : openEventDrawer(ev.id)}
                        data-testid={`event-${ev.id}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <SeverityBadge severity={ev.severity} />
                            <span className="font-medium text-gray-900">{ev.title}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <TimeAgo timestamp={ev.created_at} />
                            {ev.correlation_id && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-5 text-[10px] px-1"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openTimelineDrawer(ev.correlation_id);
                                }}
                              >
                                <Eye className="w-3 h-3" />
                              </Button>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-3 text-gray-500">
                          <span className="bg-gray-100 px-2 py-0.5 rounded">{ev.event_type}</span>
                          {ev.channel && <span>Kanal: {ev.channel}</span>}
                          {ev.correlation_id && <span className="truncate max-w-[120px]">Corr: {ev.correlation_id.slice(0, 8)}...</span>}
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

      {/* Drilldown Drawer */}
      <IncidentDrilldownDrawer
        open={drawerOpen}
        onClose={closeDrawer}
        correlationId={selectedCorrelationId}
        eventId={selectedEventId}
        onRetryDlq={() => {
          fetchDlq();
          fetchDashboard();
          fetchPrioritizedIncidents();
        }}
      />
    </Layout>
  );
};

export default ChannelOpsPage;
