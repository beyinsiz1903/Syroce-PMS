import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import PropertySwitcher from '@/components/PropertySwitcher';
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Users,
  Home,
  Star,
  Wallet,
  AlertTriangle,
  RefreshCw,
  Calendar,
  ChevronRight,
  Activity,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const ExecutiveDashboard = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [kpiSnapshot, setKpiSnapshot] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [dailySummary, setDailySummary] = useState(null);
  const [compSetSummary, setCompSetSummary] = useState(null);
  const [budgetOverview, setBudgetOverview] = useState(null);
  const [activeTab, setActiveTab] = useState('snapshot');
  const [budgetYear, setBudgetYear] = useState(new Date().getFullYear());

  useEffect(() => {
    loadData();

    // Auto refresh every 60 seconds
    const interval = setInterval(() => {
      loadData(true);
    }, 60000);

    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [budgetYear]);

  const loadData = async (isAutoRefresh = false) => {
    try {
      if (!isAutoRefresh) setLoading(true);

      const [kpiRes, alertsRes, summaryRes, compSetRes, budgetRes] = await Promise.all([
        axios.get('/executive/kpi-snapshot'),
        axios.get('/executive/performance-alerts'),
        axios.get('/executive/daily-summary'),
        axios.get('/executive/comp-set-summary'),
        axios.get('/executive/budget-overview', { params: { year: budgetYear } }),
      ]);

      setKpiSnapshot(kpiRes.data);
      setAlerts(alertsRes.data.alerts || []);
      setDailySummary(summaryRes.data);
      setCompSetSummary(compSetRes.data || null);
      setBudgetOverview(budgetRes.data || null);
    } catch (error) {
      console.error('Failed to load executive data:', error);
      toast.error('Veriler yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleYearChange = (direction) => {
    setBudgetYear((prev) => prev + (direction === 'next' ? 1 : -1));
  };

  const getTrendIcon = (trend) => {
    if (trend > 0) return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (trend < 0) return <TrendingDown className="h-4 w-4 text-red-500" />;
    return null;
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'urgent':
        return 'bg-red-500';
      case 'high':
        return 'bg-amber-500';
      case 'medium':
        return 'bg-yellow-500';
      default:
        return 'bg-blue-500';
    }
  };

  const getSeverityIcon = (severity) => {
    if (severity === 'urgent' || severity === 'high') {
      return <AlertTriangle className="h-5 w-5" />;
    }
    return <Activity className="h-5 w-5" />;
  };

  if (loading && !refreshing) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-900 to-slate-900 flex items-center justify-center">
        <div className="text-center text-white">
          <RefreshCw className="h-12 w-12 animate-spin mx-auto mb-4" />
          <p>Dashboard yükleniyor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-900 to-slate-900 pb-20">
      {/* Header */}
      <div className="bg-black/30 backdrop-blur-sm text-white p-4 sticky top-0 z-10 shadow-lg border-b border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/10 rounded-lg transition">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold">{t('reports.executiveReport')}</h1>
              <p className="text-gray-300 text-sm">
                {new Date().toLocaleDateString('tr-TR', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </p>
            </div>
          </div>

          <button
            onClick={handleRefresh}
            className="p-2 hover:bg-white/10 rounded-lg transition"
            disabled={refreshing}
          >
            <RefreshCw className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* Executive Tabs */}
        <div className="mt-3">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="bg-white/10">
              <TabsTrigger
                value="snapshot"
                className="data-[state=active]:bg-white/20 data-[state=active]:text-white"
              >
                Snapshot
              </TabsTrigger>
              <TabsTrigger
                value="budget"
                className="data-[state=active]:bg-white/20 data-[state=active]:text-white"
              >
                Budget
              </TabsTrigger>
              <TabsTrigger
                value="comp"
                className="data-[state=active]:bg-white/20 data-[state=active]:text-white"
              >
                Comp-Set
              </TabsTrigger>
            </TabsList>

            {/* SNAPSHOT TAB */}
            <TabsContent value="snapshot" className="mt-4">
              {/* Critical Alerts */}
              {alerts.length > 0 && (
                <div className="p-4 space-y-2">
                  {alerts.slice(0, 3).map((alert) => (
                    <div
                      key={alert.id}
                      className={`${getSeverityColor(alert.severity)} text-white p-4 rounded-lg flex items-center gap-3 shadow-lg ${
                        alert.severity === 'urgent' ? 'animate-pulse' : ''
                      }`}
                    >
                      {getSeverityIcon(alert.severity)}
                      <div className="flex-1">
                        <div className="font-bold">{alert.title}</div>
                        <div className="text-sm opacity-90">{alert.message}</div>
                      </div>
                      <ChevronRight className="h-5 w-5" />
                    </div>
                  ))}
                </div>
              )}

              {/* KPI Cards */}
              <div className="p-4 space-y-3">
                {kpiSnapshot && (
                  <>
                    {/* RevPAR */}
                    <Card className="bg-gradient-to-br from-emerald-500 to-teal-600 text-white border-0 shadow-xl">
                      <CardContent className="p-6">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <DollarSign className="h-6 w-6" />
                            <span className="text-sm font-medium opacity-90">
                              {kpiSnapshot.kpis.revpar.label}
                            </span>
                          </div>
                          <div className="flex items-center gap-1">
                            {getTrendIcon(kpiSnapshot.kpis.revpar.trend)}
                            <span className="text-sm font-semibold">
                              {kpiSnapshot.kpis.revpar.trend > 0 ? '+' : ''}
                              {kpiSnapshot.kpis.revpar.trend.toFixed(1)}%
                            </span>
                          </div>
                        </div>
                        <div className="text-4xl font-bold">
                          {kpiSnapshot.kpis.revpar.currency}
                          {kpiSnapshot.kpis.revpar.value.toFixed(0)}
                        </div>
                        <div className="text-sm opacity-75 mt-1">Revenue Per Available Room</div>
                      </CardContent>
                    </Card>

                    {/* ADR & Occupancy */}
                    <div className="grid grid-cols-2 gap-3">
                      <Card className="bg-gradient-to-br from-blue-500 to-indigo-600 text-white border-0 shadow-xl">
                        <CardContent className="p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <Home className="h-5 w-5" />
                            <span className="text-xs font-medium opacity-90">
                              {kpiSnapshot.kpis.adr.label}
                            </span>
                          </div>
                          <div className="text-3xl font-bold mb-1">
                            {kpiSnapshot.kpis.adr.currency}
                            {kpiSnapshot.kpis.adr.value.toFixed(0)}
                          </div>
                          <div className="flex items-center gap-1 text-sm">
                            {getTrendIcon(kpiSnapshot.kpis.adr.trend)}
                            <span>
                              {kpiSnapshot.kpis.adr.trend > 0 ? '+' : ''}
                              {kpiSnapshot.kpis.adr.trend.toFixed(1)}%
                            </span>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="bg-gradient-to-br from-indigo-500 to-pink-600 text-white border-0 shadow-xl">
                        <CardContent className="p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <Users className="h-5 w-5" />
                            <span className="text-xs font-medium opacity-90">
                              {kpiSnapshot.kpis.occupancy.label}
                            </span>
                          </div>
                          <div className="text-3xl font-bold mb-1">
                            {kpiSnapshot.kpis.occupancy.value.toFixed(0)}
                            {kpiSnapshot.kpis.occupancy.unit}
                          </div>
                          <div className="flex items-center gap-1 text-sm">
                            {getTrendIcon(kpiSnapshot.kpis.occupancy.trend)}
                            <span>
                              {kpiSnapshot.kpis.occupancy.trend > 0 ? '+' : ''}
                              {kpiSnapshot.kpis.occupancy.trend.toFixed(1)}%
                            </span>
                          </div>
                        </CardContent>
                      </Card>
                    </div>

                    {/* Revenue */}
                    <Card className="bg-gradient-to-br from-amber-500 to-amber-600 text-white border-0 shadow-xl">
                      <CardContent className="p-6">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <TrendingUp className="h-6 w-6" />
                            <span className="text-sm font-medium opacity-90">
                              {kpiSnapshot.kpis.revenue.label}
                            </span>
                          </div>
                          <div className="flex items-center gap-1">
                            {getTrendIcon(kpiSnapshot.kpis.revenue.trend)}
                            <span className="text-sm font-semibold">
                              {kpiSnapshot.kpis.revenue.trend > 0 ? '+' : ''}
                              {kpiSnapshot.kpis.revenue.trend.toFixed(1)}%
                            </span>
                          </div>
                        </div>
                        <div className="text-4xl font-bold">
                          {kpiSnapshot.kpis.revenue.currency}
                          {kpiSnapshot.kpis.revenue.value.toLocaleString()}
                        </div>
                        <div className="text-sm opacity-75 mt-1">Son 24 Saat</div>
                      </CardContent>
                    </Card>

                    {/* NPS & Cash */}
                    <div className="grid grid-cols-2 gap-3">
                      <Card className="bg-gradient-to-br from-green-500 to-emerald-600 text-white border-0 shadow-xl">
                        <CardContent className="p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <Star className="h-5 w-5" />
                            <span className="text-xs font-medium opacity-90">
                              {kpiSnapshot.kpis.nps.label}
                            </span>
                          </div>
                          <div className="text-3xl font-bold mb-1">
                            {kpiSnapshot.kpis.nps.data_available === false
                              ? '—'
                              : `${kpiSnapshot.kpis.nps.value}${kpiSnapshot.kpis.nps.unit}`}
                          </div>
                          <div className="flex items-center gap-1 text-sm">
                            {kpiSnapshot.kpis.nps.data_available === false ? (
                              <span className="opacity-80">Veri yok</span>
                            ) : (
                              <>
                                {getTrendIcon(kpiSnapshot.kpis.nps.trend)}
                                <span>
                                  {kpiSnapshot.kpis.nps.trend > 0 ? '+' : ''}
                                  {kpiSnapshot.kpis.nps.trend.toFixed(1)}%
                                </span>
                              </>
                            )}
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="bg-gradient-to-br from-slate-600 to-gray-700 text-white border-0 shadow-xl">
                        <CardContent className="p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <Wallet className="h-5 w-5" />
                            <span className="text-xs font-medium opacity-90">
                              {kpiSnapshot.kpis.cash.label}
                            </span>
                          </div>
                          <div className="text-2xl font-bold mb-1">
                            {kpiSnapshot.kpis.cash.data_available === false
                              ? '—'
                              : `${kpiSnapshot.kpis.cash.currency}${(kpiSnapshot.kpis.cash.value / 1000).toFixed(0)}K`}
                          </div>
                          <div className="flex items-center gap-1 text-sm">
                            {kpiSnapshot.kpis.cash.data_available === false ? (
                              <span className="opacity-80">Veri yok</span>
                            ) : (
                              <>
                                {getTrendIcon(kpiSnapshot.kpis.cash.trend)}
                                <span>
                                  {kpiSnapshot.kpis.cash.trend > 0 ? '+' : ''}
                                  {kpiSnapshot.kpis.cash.trend.toFixed(1)}%
                                </span>
                              </>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  </>
                )}

                {/* Daily Summary */}
                {dailySummary && (
                  <Card className="bg-white/10 backdrop-blur-sm text-white border border-white/20 shadow-xl">
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 mb-4">
                        <Calendar className="h-5 w-5" />
                        <h3 className="font-bold">Günlük Özet</h3>
                      </div>

                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <div className="text-gray-300 mb-1">Yeni Rezervasyon</div>
                          <div className="text-2xl font-bold">{dailySummary.summary.new_bookings}</div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">Check-in</div>
                          <div className="text-2xl font-bold text-green-400">
                            {dailySummary.summary.check_ins}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">Check-out</div>
                          <div className="text-2xl font-bold text-blue-400">
                            {dailySummary.summary.check_outs}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">{t("common.cancel")}</div>
                          <div className="text-2xl font-bold text-red-400">
                            {dailySummary.summary.cancellations}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">Şikayet</div>
                          <div className="text-2xl font-bold text-amber-400">
                            {dailySummary.summary.complaints}
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">{t("finance.revenue")}</div>
                          <div className="text-2xl font-bold text-emerald-400">
                            ₺{(dailySummary.summary.revenue / 1000).toFixed(0)}K
                          </div>
                        </div>
                      </div>

                      {dailySummary.highlights && (
                        <div className="mt-4 pt-4 border-t border-white/20 space-y-2 text-xs">
                          <div className="flex justify-between">
                            <span className="text-gray-300">İptal Oranı:</span>
                            <span
                              className={
                                dailySummary.highlights.cancellation_rate > 10
                                  ? 'text-red-400'
                                  : 'text-green-400'
                              }
                            >
                              %{dailySummary.highlights.cancellation_rate}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-300">Ort. Rezervasyon Geliri:</span>
                            <span className="text-blue-400">
                              ₺{dailySummary.highlights.avg_revenue_per_booking.toFixed(0)}
                            </span>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Comp-Set Summary inline (for snapshot tab) */}
                {compSetSummary && (
                  <Card className="bg-white/10 backdrop-blur-sm text-white border border-white/20 shadow-xl mt-4">
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Home className="h-5 w-5" />
                          <span className="font-semibold text-sm">Comp-Set Karşılaştırma</span>
                        </div>
                        <Badge
                          variant="outline"
                          className="text-xs border-white/40 text-white/80"
                        >
                          {compSetSummary.period}
                        </Badge>
                      </div>

                      <div className="grid grid-cols-3 gap-3 text-xs">
                        <div>
                          <div className="text-gray-300 mb-1">Doluluk</div>
                          <div className="space-y-1">
                            <div className="flex justify-between">
                              <span className="text-[11px]">Otel</span>
                              <span className="font-semibold">
                                {compSetSummary.hotel.occupancy}%
                              </span>
                            </div>
                            <div className="flex justify-between text-gray-300">
                              <span className="text-[11px]">Comp-set</span>
                              <span>
                                {compSetSummary.data_available === false
                                  ? '—'
                                  : `${compSetSummary.comp_set.occupancy}%`}
                              </span>
                            </div>
                            <div className="flex justify-between text-[11px] mt-1">
                              <span>Index</span>
                              <span
                                className={
                                  compSetSummary.data_available === false
                                    ? 'text-gray-400'
                                    : compSetSummary.indexes.occ_index >= 100
                                      ? 'text-emerald-400'
                                      : 'text-red-300'
                                }
                              >
                                {compSetSummary.data_available === false
                                  ? '—'
                                  : compSetSummary.indexes.occ_index}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div>
                          <div className="text-gray-300 mb-1">ADR</div>
                          <div className="space-y-1">
                            <div className="flex justify-between">
                              <span className="text-[11px]">Otel</span>
                              <span className="font-semibold">
                                ₺{compSetSummary.hotel.adr.toFixed(0)}
                              </span>
                            </div>
                            <div className="flex justify-between text-gray-300">
                              <span className="text-[11px]">Comp-set</span>
                              <span>
                                {compSetSummary.data_available === false
                                  ? '—'
                                  : `₺${compSetSummary.comp_set.adr.toFixed(0)}`}
                              </span>
                            </div>
                            <div className="flex justify-between text-[11px] mt-1">
                              <span>Index</span>
                              <span
                                className={
                                  compSetSummary.data_available === false
                                    ? 'text-gray-400'
                                    : compSetSummary.indexes.adr_index >= 100
                                      ? 'text-emerald-400'
                                      : 'text-red-300'
                                }
                              >
                                {compSetSummary.data_available === false
                                  ? '—'
                                  : compSetSummary.indexes.adr_index}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div>
                          <div className="text-gray-300 mb-1">RevPAR</div>
                          <div className="space-y-1">
                            <div className="flex justify-between">
                              <span className="text-[11px]">Otel</span>
                              <span className="font-semibold">
                                ₺{compSetSummary.hotel.revpar.toFixed(0)}
                              </span>
                            </div>
                            <div className="flex justify-between text-gray-300">
                              <span className="text-[11px]">Comp-set</span>
                              <span>
                                {compSetSummary.data_available === false
                                  ? '—'
                                  : `₺${compSetSummary.comp_set.revpar.toFixed(0)}`}
                              </span>
                            </div>
                            <div className="flex justify-between text-[11px] mt-1">
                              <span>Index</span>
                              <span
                                className={
                                  compSetSummary.data_available === false
                                    ? 'text-gray-400'
                                    : compSetSummary.indexes.revpar_index >= 100
                                      ? 'text-emerald-400'
                                      : 'text-red-300'
                                }
                              >
                                {compSetSummary.data_available === false
                                  ? '—'
                                  : compSetSummary.indexes.revpar_index}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {compSetSummary.data_available === false && (
                        <p className="text-[11px] text-amber-300 mt-2">
                          {compSetSummary.message ||
                            'Rakip seti (comp-set) verisi mevcut değil.'}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Room Summary */}
                {kpiSnapshot && kpiSnapshot.summary && (
                  <Card className="bg-white/10 backdrop-blur-sm text-white border border-white/20 shadow-xl mt-4">
                    <CardContent className="p-4">
                      <div className="flex items-center gap-2 mb-4">
                        <Home className="h-5 w-5" />
                        <h3 className="font-bold">Oda Durumu</h3>
                      </div>

                      <div className="grid grid-cols-3 gap-4 text-center">
                        <div>
                          <div className="text-3xl font-bold text-blue-400">
                            {kpiSnapshot.summary.total_rooms}
                          </div>
                          <div className="text-xs text-gray-300 mt-1">Toplam</div>
                        </div>
                        <div>
                          <div className="text-3xl font-bold text-green-400">
                            {kpiSnapshot.summary.occupied_rooms}
                          </div>
                          <div className="text-xs text-gray-300 mt-1">{t("housekeeping.occupied")}</div>
                        </div>
                        <div>
                          <div className="text-3xl font-bold text-amber-400">
                            {kpiSnapshot.summary.available_rooms}
                          </div>
                          <div className="text-xs text-gray-300 mt-1">Boş</div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* All Alerts Link */}
                {alerts.length > 3 && (
                  <Button
                    variant="outline"
                    className="w-full border-white/20 text-white hover:bg-white/10 mt-4"
                    onClick={() => navigate('/executive')}
                  >
                    Tüm Uyarıları Gör ({alerts.length})
                    <ChevronRight className="h-4 w-4 ml-2" />
                  </Button>
                )}
              </div>
            </TabsContent>

            {/* BUDGET TAB */}
            <TabsContent value="budget" className="mt-4">
              <div className="p-4 space-y-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h2 className="text-lg font-bold text-white">Budget Management</h2>
                    <p className="text-xs text-gray-300">
                      Yıllık bütçe hedefleri ve gerçekleşen performans
                    </p>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-white/30 text-white"
                      onClick={() => handleYearChange('prev')}
                    >
                      <ChevronRight className="h-4 w-4 rotate-180 mr-1" />
                      {budgetYear - 1}
                    </Button>
                    <span className="font-semibold text-white">{budgetYear}</span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-white/30 text-white"
                      onClick={() => handleYearChange('next')}
                    >
                      {budgetYear + 1}
                      <ChevronRight className="h-4 w-4 ml-1" />
                    </Button>
                  </div>
                </div>

                {budgetOverview && (
                  <>
                    <Card className="bg-white/5 border border-white/20 text-white">
                      <CardContent className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                        <div>
                          <div className="text-gray-300 mb-1">Toplam Gelir (Bütçe)</div>
                          <div className="text-lg font-bold">
                            ₺{(budgetOverview.totals.rev_target / 1000).toFixed(0)}K
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">Toplam Gelir (Gerçekleşen)</div>
                          <div className="text-lg font-bold text-emerald-400">
                            ₺{(budgetOverview.totals.rev_actual / 1000).toFixed(0)}K
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">Rev. Variance %</div>
                          <div
                            className={
                              budgetOverview.totals.rev_variance_pct >= 0
                                ? 'text-emerald-400 font-bold'
                                : 'text-red-300 font-bold'
                            }
                          >
                            {budgetOverview.totals.rev_variance_pct > 0 ? '+' : ''}
                            {budgetOverview.totals.rev_variance_pct}%
                          </div>
                        </div>
                        <div>
                          <div className="text-gray-300 mb-1">Avg. Occ / ADR</div>
                          <div className="text-sm">
                            <span className="text-emerald-300">
                              {budgetOverview.totals.occ_actual.toFixed(1)}%
                            </span>
                            <span className="text-gray-400"> / </span>
                            <span className="text-blue-300">
                              ₺{budgetOverview.totals.adr_actual.toFixed(0)}
                            </span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>

                    <Card className="bg-white/5 border border-white/10 text-white overflow-x-auto">
                      <CardContent className="p-0">
                        <table className="min-w-full text-xs">
                          <thead className="bg-white/10">
                            <tr>
                              <th className="px-3 py-2 text-left">Ay</th>
                              <th className="px-3 py-2 text-right">Occ Target</th>
                              <th className="px-3 py-2 text-right">Occ Actual</th>
                              <th className="px-3 py-2 text-right">ADR Target</th>
                              <th className="px-3 py-2 text-right">ADR Actual</th>
                              <th className="px-3 py-2 text-right">Rev Target</th>
                              <th className="px-3 py-2 text-right">Rev Actual</th>
                            </tr>
                          </thead>
                          <tbody>
                            {budgetOverview.months.map((m) => (
                              <tr key={m.month} className="border-t border-white/5">
                                <td className="px-3 py-1.5">{m.month}. Ay</td>
                                <td className="px-3 py-1.5 text-right text-gray-300">
                                  {m.occ_target.toFixed(1)}%
                                </td>
                                <td
                                  className={`px-3 py-1.5 text-right ${
                                    m.occ_actual >= m.occ_target ? 'text-emerald-300' : 'text-red-300'
                                  }`}
                                >
                                  {m.occ_actual.toFixed(1)}%
                                </td>
                                <td className="px-3 py-1.5 text-right text-gray-300">
                                  ₺{m.adr_target.toFixed(0)}
                                </td>
                                <td
                                  className={`px-3 py-1.5 text-right ${
                                    m.adr_actual >= m.adr_target ? 'text-emerald-300' : 'text-red-300'
                                  }`}
                                >
                                  ₺{m.adr_actual.toFixed(0)}
                                </td>
                                <td className="px-3 py-1.5 text-right text-gray-300">
                                  ₺{(m.rev_target / 1000).toFixed(0)}K
                                </td>
                                <td
                                  className={`px-3 py-1.5 text-right ${
                                    m.rev_actual >= m.rev_target ? 'text-emerald-300' : 'text-red-300'
                                  }`}
                                >
                                  ₺{(m.rev_actual / 1000).toFixed(0)}K
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </CardContent>
                    </Card>
                  </>
                )}
              </div>
            </TabsContent>

            {/* COMP-SET TAB */}
            <TabsContent value="comp" className="mt-4">
              <div className="p-4">
                {compSetSummary ? (
                  <p className="text-xs text-gray-200">
                    Comp-set detayları Snapshot sekmesindeki karttan görüntülenmektedir.
                  </p>
                ) : (
                  <div className="text-xs text-gray-300">Comp-set verisi bulunamadı.</div>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Auto Refresh Indicator */}
      <div className="fixed bottom-4 left-4 right-4 text-center">
        <div className="bg-black/50 backdrop-blur-sm text-white text-xs py-2 px-4 rounded-full inline-block">
          <RefreshCw className="h-3 w-3 inline mr-2" />
          Otomatik yenileme aktif (60 sn)
        </div>
      </div>

      {/* Property Switcher */}
      <PropertySwitcher onPropertyChange={() => loadData()} />
    </div>
  );
};

export default ExecutiveDashboard;
