import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  ArrowLeft, Cpu, HardDrive, Activity, Zap, Clock, RefreshCw,
  TrendingUp, Server, Shield, Database, AlertTriangle, CheckCircle2,
  XCircle, Timer, BarChart3, Globe, Lock, Gauge
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const BACKEND_URL = "";
const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

const SystemPerformanceMonitor = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [performance, setPerformance] = useState(null);
  const [dbStats, setDbStats] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const token = localStorage.getItem('token') || localStorage.getItem('access_token');
      const headers = { Authorization: `Bearer ${token}` };

      const [perfRes, dbRes] = await Promise.all([
        axios.get(`/system/performance`, { headers }).catch(() => ({ data: null })),
        axios.get(`/system/db-stats`, { headers }).catch(() => ({ data: null })),
      ]);

      if (perfRes.data) setPerformance(perfRes.data);
      if (dbRes.data) setDbStats(dbRes.data);

      setLoading(false);
      setRefreshing(false);
    } catch (error) {
      console.error('Failed to load monitoring data:', error);
      if (!loading) toast.error('Monitoring verileri yüklenemedi');
      setLoading(false);
      setRefreshing(false);
    }
  }, [loading]);

  useEffect(() => {
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(loadData, 8000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadData]);

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-slate-800/50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-10 h-10 animate-spin text-blue-600 mx-auto mb-3" />
          <p className="text-gray-500 dark:text-slate-400">Monitoring verileri yükleniyor...</p>
        </div>
      </div>
    );
  }

  const { system, api_metrics, rate_limiting, database, timeline, health_status, uptime_seconds, recent_errors } = performance || {};

  const formatUptime = (seconds) => {
    if (!seconds) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}s ${m}dk`;
    if (m > 0) return `${m}dk ${s}sn`;
    return `${s}sn`;
  };

  const getHealthColor = (status) => {
    if (status === 'healthy') return 'bg-green-500';
    if (status === 'degraded') return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getHealthLabel = (status) => {
    if (status === 'healthy') return 'Sağlıklı';
    if (status === 'degraded') return 'Yüksek Yük';
    return 'Kritik';
  };

  // Status code pie data
  const statusData = api_metrics?.status_breakdown
    ? Object.entries(api_metrics.status_breakdown).map(([k, v]) => ({ name: k, value: v }))
    : [];

  // Tabs
  const tabs = [
    { id: 'overview', label: t('loyalty.overview'), icon: Gauge },
    { id: 'apm', label: 'APM Metrikleri', icon: Activity },
    { id: 'ratelimit', label: 'Rate Limiting', icon: Shield },
    { id: 'database', label: 'Veritabanı', icon: Database },
  ];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-slate-800/50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-slate-800 via-blue-900 to-indigo-900 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold flex items-center gap-2">
                <Gauge className="w-5 h-5" />
                Sistem Monitoring & APM
              </h1>
              <p className="text-xs text-blue-200">
                Uptime: {formatUptime(uptime_seconds)} • Son güncelleme: {new Date().toLocaleTimeString('tr-TR')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={`${getHealthColor(health_status)} text-white border-0`}>
              {health_status === 'healthy' ? <CheckCircle2 className="w-3 h-3 mr-1" /> : <AlertTriangle className="w-3 h-3 mr-1" />}
              {getHealthLabel(health_status)}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`text-white hover:bg-white/20 p-2 text-xs ${autoRefresh ? 'bg-white/10' : ''}`}
            >
              {autoRefresh ? 'Otomatik' : 'Manuel'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="text-white hover:bg-white/20 p-2"
            >
              <RefreshCw className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-white dark:bg-card border-b shadow-sm sticky top-[72px] z-40">
        <div className="max-w-7xl mx-auto flex overflow-x-auto">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-4 space-y-4">

        {/* ─── OVERVIEW TAB ─── */}
        {activeTab === 'overview' && (
          <>
            {/* System Resources Row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <ResourceCard
                icon={<Cpu className="w-5 h-5 text-blue-600" />}
                label="CPU"
                value={`${system?.cpu_percent || 0}%`}
                percent={system?.cpu_percent || 0}
                color="blue"
              />
              <ResourceCard
                icon={<Activity className="w-5 h-5 text-indigo-600" />}
                label="RAM"
                value={`${system?.memory_percent || 0}%`}
                sub={`${system?.memory_used_gb || 0}GB / ${system?.memory_total_gb || 0}GB`}
                percent={system?.memory_percent || 0}
                color="purple"
              />
              <ResourceCard
                icon={<HardDrive className="w-5 h-5 text-green-600" />}
                label="Disk"
                value={`${system?.disk_percent || 0}%`}
                sub={`${system?.disk_used_gb || 0}GB / ${system?.disk_total_gb || 0}GB`}
                percent={system?.disk_percent || 0}
                color="green"
              />
              <ResourceCard
                icon={<Server className="w-5 h-5 text-indigo-600" />}
                label="DB Bağlantı"
                value={`${database?.connections?.current || 0}`}
                sub={`/ ${database?.connections?.available || 0} boş`}
                percent={database?.connections?.current ? (database.connections.current / (database.connections.current + (database.connections.available || 1))) * 100 : 0}
                color="indigo"
              />
            </div>

            {/* Key Metrics Row */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <MetricCard
                icon={<Zap className="w-4 h-4" />}
                label="Ort. Yanıt"
                value={`${api_metrics?.avg_response_time_ms || 0}ms`}
                color="text-yellow-600"
              />
              <MetricCard
                icon={<Timer className="w-4 h-4" />}
                label="P95"
                value={`${api_metrics?.p95_ms || 0}ms`}
                color="text-amber-600"
              />
              <MetricCard
                icon={<TrendingUp className="w-4 h-4" />}
                label="İstek/dk"
                value={api_metrics?.requests_per_minute || 0}
                color="text-cyan-600"
              />
              <MetricCard
                icon={<XCircle className="w-4 h-4" />}
                label="Hata Oranı"
                value={`${api_metrics?.error_rate_percent || 0}%`}
                color={api_metrics?.error_rate_percent > 5 ? 'text-red-600' : 'text-green-600'}
              />
              <MetricCard
                icon={<Shield className="w-4 h-4" />}
                label="Rate Limit"
                value={rate_limiting?.total_rate_limit_hits || 0}
                sub="hit"
                color="text-violet-600"
              />
            </div>

            {/* Timeline Chart */}
            {timeline && timeline.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-blue-600" />
                    İstek & Yanıt Süresi (Son 10 Dakika)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={timeline}>
                      <defs>
                        <linearGradient id="reqGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--dash-chart-grid, #f0f0f0)" />
                      <XAxis
                        dataKey="timestamp"
                        tick={{ fontSize: 10, fill: 'var(--dash-chart-axis, #666)' }}
                        tickFormatter={(v) => v ? v.split('T')[1] || v.slice(-5) : ''}
                      />
                      <YAxis yAxisId="left" tick={{ fontSize: 10, fill: 'var(--dash-chart-axis, #666)' }} />
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: 'var(--dash-chart-axis, #666)' }} />
                      <Tooltip
                        contentStyle={{ fontSize: 12 }}
                        labelFormatter={(v) => v ? v.replace('T', ' ') : ''}
                      />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Area
                        yAxisId="left"
                        type="monotone"
                        dataKey="requests"
                        stroke="#3b82f6"
                        fill="url(#reqGrad)"
                        name="İstek Sayısı"
                      />
                      <Line
                        yAxisId="right"
                        type="monotone"
                        dataKey="avg_duration_ms"
                        stroke="#f59e0b"
                        name="Ort. Süre (ms)"
                        strokeWidth={2}
                        dot={false}
                      />
                      <Bar
                        yAxisId="left"
                        dataKey="errors"
                        fill="#ef4444"
                        name="Hatalar"
                        opacity={0.7}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            )}

            {/* Status Code Distribution + Top Endpoints side by side */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Status Codes */}
              {statusData.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">HTTP Durum Kodları</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-4">
                      <ResponsiveContainer width={120} height={120}>
                        <PieChart>
                          <Pie
                            data={statusData}
                            cx="50%"
                            cy="50%"
                            outerRadius={50}
                            dataKey="value"
                            stroke="none"
                          >
                            {statusData.map((_, i) => (
                              <Cell key={i} fill={
                                statusData[i]?.name === '2xx' ? '#10b981' :
                                statusData[i]?.name === '3xx' ? '#3b82f6' :
                                statusData[i]?.name === '4xx' ? '#f59e0b' :
                                '#ef4444'
                              } />
                            ))}
                          </Pie>
                          <Tooltip />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="space-y-1 flex-1">
                        {statusData.map((item, i) => (
                          <div key={i} className="flex justify-between items-center text-sm">
                            <span className="flex items-center gap-2">
                              <span className={`w-3 h-3 rounded-full ${
                                item.name === '2xx' ? 'bg-green-500' :
                                item.name === '3xx' ? 'bg-blue-500' :
                                item.name === '4xx' ? 'bg-yellow-500' :
                                'bg-red-500'
                              }`} />
                              {item.name}
                            </span>
                            <span className="font-semibold">{item.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Top Endpoints */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">En Çok İstek Alan Endpoint'ler</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 max-h-[200px] overflow-y-auto">
                    {(api_metrics?.endpoints || []).slice(0, 8).map((ep, i) => (
                      <div key={i} className="flex justify-between items-center p-2 bg-gray-50 dark:bg-slate-800/50 rounded text-xs">
                        <div className="flex-1 min-w-0">
                          <div className="font-mono truncate text-gray-700 dark:text-slate-200">{ep.endpoint}</div>
                          <div className="text-gray-400 dark:text-slate-500">{ep.count} istek</div>
                        </div>
                        <div className="text-right ml-2">
                          <div className="font-bold">{ep.avg_ms}ms</div>
                          <Badge className={`text-[10px] px-1 ${
                            ep.error_rate > 10 ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'
                          }`}>
                            {ep.error_rate}% hata
                          </Badge>
                        </div>
                      </div>
                    ))}
                    {(!api_metrics?.endpoints || api_metrics.endpoints.length === 0) && (
                      <div className="text-center text-gray-400 dark:text-slate-500 py-4 text-sm">
                        Henüz yeterli veri yok
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}

        {/* ─── APM TAB ─── */}
        {activeTab === 'apm' && (
          <>
            {/* Percentile Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard icon={<Timer className="w-4 h-4" />} label="P50 (Median)" value={`${api_metrics?.p50_ms || 0}ms`} color="text-blue-600" />
              <MetricCard icon={<Timer className="w-4 h-4" />} label="P95" value={`${api_metrics?.p95_ms || 0}ms`} color="text-amber-600" />
              <MetricCard icon={<Timer className="w-4 h-4" />} label="P99" value={`${api_metrics?.p99_ms || 0}ms`} color="text-red-600" />
              <MetricCard icon={<AlertTriangle className="w-4 h-4" />} label="Yavaş İstek" value={api_metrics?.slow_requests || 0} sub=">500ms" color="text-amber-600" />
            </div>

            {/* Slowest Endpoints */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Clock className="w-4 h-4 text-red-500" />
                  En Yavaş Endpoint'ler
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(api_metrics?.slowest_endpoints || []).map((ep, i) => (
                    <div key={i} className="flex items-center gap-3 p-2 bg-gray-50 dark:bg-slate-800/50 rounded">
                      <div className={`text-xs font-bold w-6 h-6 rounded-full flex items-center justify-center ${
                        i < 3 ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-500 dark:bg-slate-800 dark:text-slate-400'
                      }`}>
                        {i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-xs truncate">{ep.endpoint}</div>
                        <div className="text-xs text-gray-400 dark:text-slate-500">{ep.count} istek</div>
                      </div>
                      <div className="text-right">
                        <div className={`font-bold text-sm ${ep.avg_ms > 500 ? 'text-red-600' : ep.avg_ms > 200 ? 'text-amber-600' : 'text-green-600'}`}>
                          {ep.avg_ms}ms
                        </div>
                      </div>
                    </div>
                  ))}
                  {(!api_metrics?.slowest_endpoints || api_metrics.slowest_endpoints.length === 0) && (
                    <div className="text-center text-gray-400 dark:text-slate-500 py-6 text-sm">Henüz yeterli veri yok</div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Error Endpoints */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <XCircle className="w-4 h-4 text-red-500" />
                  Hatalı Endpoint'ler
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {(api_metrics?.error_endpoints || []).map((ep, i) => (
                    <div key={i} className="flex items-center gap-3 p-2 bg-red-50 rounded border border-red-100">
                      <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-xs truncate">{ep.endpoint}</div>
                        <div className="text-xs text-gray-500 dark:text-slate-400">{ep.total_requests} toplam istek</div>
                      </div>
                      <div className="text-right">
                        <div className="font-bold text-red-600 text-sm">{ep.error_count} hata</div>
                        <div className="text-xs text-red-400">{ep.error_rate}%</div>
                      </div>
                    </div>
                  ))}
                  {(!api_metrics?.error_endpoints || api_metrics.error_endpoints.length === 0) && (
                    <div className="text-center text-green-500 py-6 text-sm flex items-center justify-center gap-2">
                      <CheckCircle2 className="w-5 h-5" />
                      Hatalı endpoint bulunamadı
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Recent Errors */}
            {recent_errors && recent_errors.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                    Son Hatalar
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1 max-h-[200px] overflow-y-auto">
                    {recent_errors.slice(0, 10).map((err, i) => (
                      <div key={i} className="flex items-center gap-2 p-2 bg-red-50 rounded text-xs">
                        <Badge className="bg-red-100 text-red-700 text-[10px]">{err.status_code}</Badge>
                        <span className="font-mono truncate flex-1">{err.method} {err.path}</span>
                        <span className="text-gray-400 dark:text-slate-500">{err.duration_ms?.toFixed(0)}ms</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {/* ─── RATE LIMITING TAB ─── */}
        {activeTab === 'ratelimit' && (
          <>
            {/* Rate Limit Status */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard
                icon={<Shield className="w-4 h-4" />}
                label={t("common.status")}
                value={<Badge className="bg-green-500 text-white">Aktif</Badge>}
                color="text-green-600"
              />
              <MetricCard
                icon={<Globe className="w-4 h-4" />}
                label="Aktif İstemci"
                value={rate_limiting?.active_clients || 0}
                color="text-blue-600"
              />
              <MetricCard
                icon={<Lock className="w-4 h-4" />}
                label="Toplam Engelleme"
                value={rate_limiting?.total_rate_limit_hits || 0}
                color={rate_limiting?.total_rate_limit_hits > 0 ? 'text-red-600' : 'text-green-600'}
              />
              <MetricCard
                icon={<Server className="w-4 h-4" />}
                label="Mod"
                value="In-Memory"
                sub="Sliding Window"
                color="text-indigo-600"
              />
            </div>

            {/* Rate Limit Configuration */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Shield className="w-4 h-4 text-blue-500" />
                  Rate Limit Yapılandırması
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(rate_limiting?.limits_config || {}).map(([key, config]) => (
                    <div key={key} className="p-3 bg-gray-50 dark:bg-slate-800/50 rounded-lg border">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-sm capitalize">{key}</span>
                        <Badge className={`text-[10px] ${
                          key === 'auth' ? 'bg-red-100 text-red-700' :
                          key === 'anonymous' ? 'bg-yellow-100 text-yellow-700' :
                          key === 'admin' ? 'bg-indigo-100 text-indigo-700' :
                          'bg-blue-100 text-blue-700'
                        }`}>
                          {getCategoryLabel(key)}
                        </Badge>
                      </div>
                      <div className="flex items-end justify-between">
                        <div>
                          <div className="text-2xl font-bold text-gray-800 dark:text-slate-100">{config.max_requests}</div>
                          <div className="text-xs text-gray-400 dark:text-slate-500">istek / {config.window_seconds}sn</div>
                        </div>
                        <div className="text-xs text-gray-400 dark:text-slate-500">
                          {(config.max_requests / (config.window_seconds / 60)).toFixed(0)}/dk
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Rate Limit Hits by Endpoint */}
            {rate_limiting?.hits_by_endpoint && Object.keys(rate_limiting.hits_by_endpoint).length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-500" />
                    Engellenen Endpoint'ler
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {Object.entries(rate_limiting.hits_by_endpoint).map(([ep, count], i) => (
                      <div key={i} className="flex items-center justify-between p-2 bg-red-50 rounded border border-red-100">
                        <span className="font-mono text-xs truncate flex-1">{ep}</span>
                        <Badge className="bg-red-100 text-red-700">{count} hit</Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* How it works */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Nasıl Çalışır?</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-gray-500 dark:text-slate-400 space-y-2">
                  <p>• Her API isteği, kullanıcı kimliği veya IP adresine göre takip edilir.</p>
                  <p>• Kayan pencere (sliding window) algoritması ile dakika başına istek sayısı kontrol edilir.</p>
                  <p>• Limit aşıldığında <code className="bg-gray-100 dark:bg-slate-800 px-1 py-0.5 rounded">429 Too Many Requests</code> yanıtı döner.</p>
                  <p>• <code className="bg-gray-100 dark:bg-slate-800 px-1 py-0.5 rounded">X-RateLimit-Limit</code>, <code className="bg-gray-100 dark:bg-slate-800 px-1 py-0.5 rounded">X-RateLimit-Remaining</code>, <code className="bg-gray-100 dark:bg-slate-800 px-1 py-0.5 rounded">X-RateLimit-Reset</code> header'ları her yanıtta yer alır.</p>
                  <p>• Whitelist: <code className="bg-gray-100 dark:bg-slate-800 px-1 py-0.5 rounded">/health</code>, <code className="bg-gray-100 dark:bg-slate-800 px-1 py-0.5 rounded">/api/health</code>, <code className="bg-gray-100 dark:bg-slate-800 px-1 py-0.5 rounded">/api/status</code></p>
                </div>
              </CardContent>
            </Card>
          </>
        )}

        {/* ─── DATABASE TAB ─── */}
        {activeTab === 'database' && (
          <>
            {/* DB Connection Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricCard
                icon={<Database className="w-4 h-4" />}
                label="Aktif Bağlantı"
                value={dbStats?.connections?.current || database?.connections?.current || 0}
                color="text-blue-600"
              />
              <MetricCard
                icon={<Server className="w-4 h-4" />}
                label="Boş Bağlantı"
                value={dbStats?.connections?.available || database?.connections?.available || 0}
                color="text-green-600"
              />
              <MetricCard
                icon={<Globe className="w-4 h-4" />}
                label="Toplam Oluşturulan"
                value={dbStats?.connections?.total_created || database?.connections?.total_created || 0}
                color="text-indigo-600"
              />
              <MetricCard
                icon={<Clock className="w-4 h-4" />}
                label="DB Uptime"
                value={formatUptime(dbStats?.uptime_seconds || 0)}
                color="text-indigo-600"
              />
            </div>

            {/* Connection Pool Config */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Gauge className="w-4 h-4 text-blue-500" />
                  Bağlantı Havuzu Yapılandırması
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center p-3 bg-blue-50 rounded-lg">
                    <div className="text-2xl font-bold text-blue-600">{dbStats?.pool_config?.max_pool_size || 500}</div>
                    <div className="text-xs text-gray-500 dark:text-slate-400">Max Pool Size</div>
                  </div>
                  <div className="text-center p-3 bg-green-50 rounded-lg">
                    <div className="text-2xl font-bold text-green-600">{dbStats?.pool_config?.min_pool_size || 50}</div>
                    <div className="text-xs text-gray-500 dark:text-slate-400">Min Pool Size</div>
                  </div>
                  <div className="text-center p-3 bg-indigo-50 rounded-lg">
                    <div className="text-2xl font-bold text-indigo-600">{((dbStats?.pool_config?.max_idle_time_ms || 45000) / 1000).toFixed(0)}s</div>
                    <div className="text-xs text-gray-500 dark:text-slate-400">Max Idle Time</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* DB Operations */}
            {(dbStats?.operations || database?.opcounters) && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Activity className="w-4 h-4 text-green-500" />
                    Veritabanı İşlemleri
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(dbStats?.operations || database?.opcounters || {}).map(([op, count]) => (
                      <div key={op} className="text-center p-3 bg-gray-50 dark:bg-slate-800/50 rounded-lg">
                        <div className="text-xl font-bold text-gray-700 dark:text-slate-200">{(count || 0).toLocaleString()}</div>
                        <div className="text-xs text-gray-400 dark:text-slate-500 uppercase">{op}</div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Collection Stats */}
            {dbStats?.collections && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Database className="w-4 h-4 text-indigo-500" />
                    Koleksiyon İstatistikleri
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b text-gray-500 dark:text-slate-400">
                          <th className="text-left py-2 px-2">Koleksiyon</th>
                          <th className="text-right py-2 px-2">Doküman</th>
                          <th className="text-right py-2 px-2">Boyut</th>
                          <th className="text-right py-2 px-2">İndeks</th>
                          <th className="text-right py-2 px-2">İndeks Boyutu</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(dbStats.collections)
                          .filter(([, v]) => typeof v === 'object' && v.count !== undefined)
                          .sort((a, b) => (b[1].count || 0) - (a[1].count || 0))
                          .map(([name, stats]) => (
                            <tr key={name} className="border-b hover:bg-gray-50 dark:hover:bg-slate-800/50">
                              <td className="py-2 px-2 font-mono">{name}</td>
                              <td className="text-right py-2 px-2 font-semibold">{(stats.count || 0).toLocaleString()}</td>
                              <td className="text-right py-2 px-2">{stats.size_mb || 0} MB</td>
                              <td className="text-right py-2 px-2">{stats.indexes || 0}</td>
                              <td className="text-right py-2 px-2">{stats.index_size_mb || 0} MB</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Index Details */}
            {dbStats?.indexes && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Zap className="w-4 h-4 text-yellow-500" />
                    İndeks Detayları
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {Object.entries(dbStats.indexes)
                      .filter(([, v]) => typeof v === 'object' && v.count !== undefined)
                      .map(([col, info]) => (
                        <div key={col} className="p-3 bg-gray-50 dark:bg-slate-800/50 rounded-lg">
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-mono text-sm font-semibold">{col}</span>
                            <Badge className="bg-blue-100 text-blue-700">{info.count} indeks</Badge>
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {(info.indexes || []).map((idx, i) => (
                              <span key={i} className="text-[10px] bg-white dark:bg-card px-2 py-0.5 rounded border text-gray-500 dark:text-slate-400">
                                {idx}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
};

// ─── Helper Components ───

const ResourceCard = ({ icon, label, value, sub, percent, color }) => (
  <Card>
    <CardContent className="p-3">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs text-gray-500 dark:text-slate-400">{label}</span>
      </div>
      <div className={`text-2xl font-bold text-${color}-600`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 dark:text-slate-500 mt-0.5">{sub}</div>}
      <div className="w-full bg-gray-200 dark:bg-slate-700 rounded-full h-1.5 mt-2">
        <div
          className={`h-1.5 rounded-full transition-all duration-500 ${
            percent > 80 ? 'bg-red-500' :
            percent > 60 ? 'bg-amber-400' : `bg-${color}-500`
          }`}
          style={{ width: `${Math.min(100, percent || 0)}%` }}
        />
      </div>
    </CardContent>
  </Card>
);

const MetricCard = ({ icon, label, value, sub, color }) => (
  <Card>
    <CardContent className="p-3">
      <div className="flex items-center gap-1.5 mb-1">
        <span className={color}>{icon}</span>
        <span className="text-xs text-gray-500 dark:text-slate-400">{label}</span>
      </div>
      <div className={`text-xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 dark:text-slate-500">{sub}</div>}
    </CardContent>
  </Card>
);

const getCategoryLabel = (key) => {
  const labels = {
    auth: 'Kimlik Doğrulama',
    export: 'Dışa Aktarma',
    report: 'Raporlar',
    write: 'Yazma İşlemi',
    default: 'Varsayılan',
    anonymous: 'Anonim',
    admin: 'Yönetici',
  };
  return labels[key] || key;
};

export default SystemPerformanceMonitor;
