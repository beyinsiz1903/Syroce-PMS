import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  ArrowLeft, 
  BarChart3, 
  TrendingUp, 
  Users,
  DollarSign,
  Bed,
  AlertCircle,
  RefreshCw,
  CheckCircle,
  Clock,
  Target,
  Calendar,
  Building2,
  ChevronDown,
  Home
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MobileGM = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [dailyFlash, setDailyFlash] = useState(null);
  const [financeSnapshot, setFinanceSnapshot] = useState(null);
  const [roomStatus, setRoomStatus] = useState(null);
  const [staffTasks, setStaffTasks] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [dashboardModalOpen, setDashboardModalOpen] = useState(false);
  const [reportsModalOpen, setReportsModalOpen] = useState(false);
  const [pickupModalOpen, setPickupModalOpen] = useState(false);
  const [anomalyModalOpen, setAnomalyModalOpen] = useState(false);
  const [forecastModalOpen, setForecastModalOpen] = useState(false);
  const [pickupData, setPickupData] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [weeklyForecast, setWeeklyForecast] = useState([]);
  const [monthlyForecast, setMonthlyForecast] = useState([]);
  const [propertyModalOpen, setPropertyModalOpen] = useState(false);
  const [selectedProperty, setSelectedProperty] = useState(null);
  const [properties, setProperties] = useState([
    { id: 1, name: 'Hilton Istanbul Bosphorus', location: 'Istanbul, TR', rooms: 498, status: 'active' },
    { id: 2, name: 'Hilton Ankara', location: 'Ankara, TR', rooms: 312, status: 'active' },
    { id: 3, name: 'Hilton Izmir', location: 'Izmir, TR', rooms: 276, status: 'active' },
    { id: 4, name: 'Hilton Antalya', location: 'Antalya, TR', rooms: 425, status: 'active' }
  ]);

  useEffect(() => {
    // Set default property
    if (!selectedProperty && properties.length > 0) {
      setSelectedProperty(properties[0]);
    }
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      
      const [flashRes, financeRes, roomsRes, tasksRes] = await Promise.all([
        axios.get('/reports/daily-flash'),
        axios.get('/reports/finance-snapshot'),
        axios.get('/housekeeping/room-status'),
        axios.get('/pms/staff-tasks?limit=5')
      ]);

      setDailyFlash(flashRes.data);
      setFinanceSnapshot(financeRes.data);
      setRoomStatus(roomsRes.data);
      setStaffTasks(tasksRes.data?.tasks || tasksRes.data || []);
    } catch (error) {
      console.error('Failed to load GM data:', error);
      toast.error('Veri yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const loadPickupAnalysis = async () => {
    try {
      const res = await axios.get('/dashboard/gm/pickup-analysis');
      setPickupData(res.data);
      setPickupModalOpen(true);
    } catch (error) {
      toast.error('Pickup analizi yüklenemedi');
    }
  };

  const loadAnomalyDetection = async () => {
    try {
      const res = await axios.get('/dashboard/gm/anomaly-detection');
      setAnomalies(res.data.anomalies || []);
      setAnomalyModalOpen(true);
    } catch (error) {
      toast.error('Anomali tespiti yüklenemedi');
    }
  };

  const loadForecast = async () => {
    try {
      const [weeklyRes, monthlyRes] = await Promise.all([
        axios.get('/dashboard/gm/forecast-weekly'),
        axios.get('/dashboard/gm/forecast-monthly')
      ]);
      setWeeklyForecast(weeklyRes.data.weeks || []);
      setMonthlyForecast(monthlyRes.data.months || []);
      setForecastModalOpen(true);
    } catch (error) {
      toast.error('Tahmin verileri yüklenemedi');
    }
  };

  const formatCurrency = (amount) => {
    return `₺${parseFloat(amount || 0).toFixed(2)}`;
  };

  const formatPercent = (value) => {
    return `${parseFloat(value || 0).toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-red-600 mx-auto mb-2" />
          <p className="text-gray-600">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-red-600 to-red-500 text-white sticky top-0 z-50 shadow-lg">
        <div className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/mobile')}
                className="text-white hover:bg-white/20 p-2"
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
              <div>
                <h1 className="text-xl font-bold">Genel Müdür Dashboard</h1>
                <p className="text-xs text-red-100">GM Executive Dashboard</p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/')}
                className="text-white hover:bg-white/20 p-2"
                title="Ana Sayfa"
              >
                <Home className="w-5 h-5" />
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
        
        {/* Property Selector */}
        <div className="px-4 pb-3">
          <Button
            variant="ghost"
            className="w-full bg-white/10 hover:bg-white/20 text-white border border-white/30 justify-between"
            onClick={() => setPropertyModalOpen(true)}
          >
            <div className="flex items-center space-x-2">
              <Building2 className="w-4 h-4" />
              <div className="text-left">
                <p className="text-xs font-normal opacity-80">Seçili Tesis</p>
                <p className="text-sm font-bold">{selectedProperty?.name || 'Tesis Seçin'}</p>
              </div>
            </div>
            <ChevronDown className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Property Switcher & Breadcrumb */}
        <Card className="bg-white border-2 border-blue-200">
          <CardContent className="p-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2 flex-1">
                <Building2 className="w-5 h-5 text-blue-600" />
                <div className="flex-1">
                  <div className="text-xs text-gray-500">Aktif Tesis</div>
                  <button
                    onClick={() => setPropertyModalOpen(true)}
                    className="text-sm font-bold text-blue-600 hover:text-blue-800"
                  >
                    {selectedProperty ? selectedProperty.name : 'Hilton Istanbul Bosphorus'} ▼
                  </button>
                </div>
              </div>
            </div>
            <div className="mt-2 pt-2 border-t border-gray-200">
              <div className="flex items-center space-x-2 text-xs text-gray-600">
                <span>Dashboard</span>
                <span>›</span>
                <span className="font-medium text-blue-600">GM Panel</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Date Badge */}
        <Card className="bg-gradient-to-r from-red-50 to-pink-50">
          <CardContent className="p-3">
            <div className="text-center">
              <p className="text-xs text-gray-600">Bugün</p>
              <p className="text-lg font-bold text-gray-900">
                {new Date().toLocaleDateString('tr-TR', { 
                  weekday: 'long', 
                  year: 'numeric', 
                  month: 'long', 
                  day: 'numeric' 
                })}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Key Performance Indicators */}
        <div className="grid grid-cols-2 gap-3">
          <Card className="bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-blue-600 font-medium">DOLULUK</p>
                  <p className="text-3xl font-bold text-blue-700">
                    {formatPercent(dailyFlash?.occupancy?.occupancy_pct || 0)}
                  </p>
                  <p className="text-xs text-blue-600 mt-1">
                    {dailyFlash?.occupancy?.occupied_rooms || 0}/{dailyFlash?.occupancy?.total_rooms || 0} oda
                  </p>
                </div>
                <Bed className="w-10 h-10 text-blue-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-green-600 font-medium">GÜN GELİRİ</p>
                  <p className="text-2xl font-bold text-green-700">
                    {formatCurrency(dailyFlash?.revenue?.total_revenue || 0)}
                  </p>
                  <p className="text-xs text-green-600 mt-1">
                    ADR: {formatCurrency(dailyFlash?.revenue?.adr || 0)}
                  </p>
                </div>
                <DollarSign className="w-10 h-10 text-green-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-indigo-50 to-indigo-100 border-indigo-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-indigo-600 font-medium">RevPAR</p>
                  <p className="text-2xl font-bold text-indigo-700">
                    {formatCurrency(dailyFlash?.revenue?.revpar || 0)}
                  </p>
                </div>
                <Target className="w-10 h-10 text-indigo-300" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-amber-50 to-amber-100 border-amber-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-amber-600 font-medium">BEKLEYEN AR</p>
                  <p className="text-2xl font-bold text-amber-700">
                    {formatCurrency(financeSnapshot?.pending_ar?.total_pending || 0)}
                  </p>
                </div>
                <AlertCircle className="w-10 h-10 text-amber-300" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Today's Movements */}
        {dailyFlash?.movements && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <Users className="w-5 h-5 mr-2 text-blue-600" />
                Bugünkü Hareketler
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center p-3 bg-green-50 rounded-lg">
                  <p className="text-xs text-green-600 mb-1">Geliş</p>
                  <p className="text-3xl font-bold text-green-700">
                    {dailyFlash.movements.arrivals || 0}
                  </p>
                </div>
                <div className="text-center p-3 bg-red-50 rounded-lg">
                  <p className="text-xs text-red-600 mb-1">Gidiş</p>
                  <p className="text-3xl font-bold text-red-700">
                    {dailyFlash.movements.departures || 0}
                  </p>
                </div>
                <div className="text-center p-3 bg-blue-50 rounded-lg">
                  <p className="text-xs text-blue-600 mb-1">Konaklayan</p>
                  <p className="text-3xl font-bold text-blue-700">
                    {dailyFlash.movements.in_house || 0}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Room Status Overview */}
        {roomStatus?.status_counts && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <Bed className="w-5 h-5 mr-2 text-indigo-600" />
                Oda Durumu Özeti
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center p-2 bg-green-50 rounded border border-green-200">
                  <p className="text-2xl font-bold text-green-700">{roomStatus.status_counts.available || 0}</p>
                  <p className="text-xs text-green-600">Hazır</p>
                </div>
                <div className="text-center p-2 bg-red-50 rounded border border-red-200">
                  <p className="text-2xl font-bold text-red-700">{roomStatus.status_counts.dirty || 0}</p>
                  <p className="text-xs text-red-600">{t("housekeeping.dirty")}</p>
                </div>
                <div className="text-center p-2 bg-indigo-50 rounded border border-indigo-200">
                  <p className="text-2xl font-bold text-indigo-700">{roomStatus.status_counts.occupied || 0}</p>
                  <p className="text-xs text-indigo-600">{t("housekeeping.occupied")}</p>
                </div>
                <div className="text-center p-2 bg-blue-50 rounded border border-blue-200">
                  <p className="text-2xl font-bold text-blue-700">{roomStatus.status_counts.inspected || 0}</p>
                  <p className="text-xs text-blue-600">Kontrol</p>
                </div>
                <div className="text-center p-2 bg-yellow-50 rounded border border-yellow-200">
                  <p className="text-2xl font-bold text-yellow-700">{roomStatus.status_counts.cleaning || 0}</p>
                  <p className="text-xs text-yellow-600">Temizlik</p>
                </div>
                <div className="text-center p-2 bg-amber-50 rounded border border-amber-200">
                  <p className="text-2xl font-bold text-amber-700">{roomStatus.status_counts.maintenance || 0}</p>
                  <p className="text-xs text-amber-600">Bakım</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Financial Summary */}
        {financeSnapshot && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <DollarSign className="w-5 h-5 mr-2 text-green-600" />
                Finansal Özet
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                <div>
                  <p className="text-sm font-medium text-gray-700">Bugünkü Tahsilat</p>
                  <p className="text-xs text-gray-500">
                    {financeSnapshot.todays_collections?.payment_count || 0} işlem
                  </p>
                </div>
                <p className="text-xl font-bold text-green-700">
                  {formatCurrency(financeSnapshot.todays_collections?.total_collected || 0)}
                </p>
              </div>
              <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
                <div>
                  <p className="text-sm font-medium text-gray-700">Aylık Tahsilat</p>
                  <p className="text-xs text-gray-500">
                    Oran: {formatPercent(financeSnapshot.mtd_collections?.collection_rate || 0)}
                  </p>
                </div>
                <p className="text-xl font-bold text-blue-700">
                  {formatCurrency(financeSnapshot.mtd_collections?.total_collected || 0)}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Recent Tasks */}
        {staffTasks?.tasks && staffTasks.tasks.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <CheckCircle className="w-5 h-5 mr-2 text-indigo-600" />
                Son Görevler
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {staffTasks.tasks.slice(0, 5).map((task, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                  <div className="flex-1">
                    <p className="font-medium text-gray-900 text-sm">{task.title || 'Görev'}</p>
                    <p className="text-xs text-gray-500">{task.department || 'Genel'}</p>
                  </div>
                  <Badge variant={task.status === 'completed' ? 'success' : 'default'}>
                    {task.status || 'pending'}
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Quick Actions */}
        <Card className="bg-gradient-to-r from-red-50 to-amber-50">
          <CardContent className="p-4">
            <div className="grid grid-cols-2 gap-3">
              <Button
                className="h-20 flex flex-col items-center justify-center bg-red-600 hover:bg-red-700"
                onClick={() => setDashboardModalOpen(true)}
              >
                <BarChart3 className="w-6 h-6 mb-1" />
                <span className="text-xs">Tam Dashboard</span>
              </Button>
              <Button
                className="h-20 flex flex-col items-center justify-center"
                variant="outline"
                onClick={() => setReportsModalOpen(true)}
              >
                <TrendingUp className="w-6 h-6 mb-1" />
                <span className="text-xs">{t("nav.reports")}</span>
              </Button>
              <Button
                className="h-20 flex flex-col items-center justify-center bg-blue-600 hover:bg-blue-700"
                onClick={loadPickupAnalysis}
              >
                <Target className="w-6 h-6 mb-1" />
                <span className="text-xs">Pickup Analizi</span>
              </Button>
              <Button
                className="h-20 flex flex-col items-center justify-center bg-amber-600 hover:bg-amber-700"
                onClick={loadAnomalyDetection}
              >
                <AlertCircle className="w-6 h-6 mb-1" />
                <span className="text-xs">Anomali Tespiti</span>
              </Button>
              <Button
                className="h-20 flex flex-col items-center justify-center bg-indigo-600 hover:bg-indigo-700"
                onClick={loadForecast}
              >
                <Calendar className="w-6 h-6 mb-1" />
                <span className="text-xs">Tahminler</span>
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Info Banner */}
        <Card className="bg-gradient-to-r from-indigo-50 to-indigo-50">
          <CardContent className="p-4">
            <div className="flex items-start space-x-3">
              <div className="bg-indigo-100 p-2 rounded-full">
                <Target className="w-5 h-5 text-indigo-600" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-gray-900 mb-1">📊 Executive Snapshot</h4>
                <p className="text-sm text-gray-600">
                  Tüm operasyonlarınızın özeti mobil cihazınızda. 
                  Detaylı analizler için tam dashboard'u ziyaret edin.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Dashboard Modal */}
      <Dialog open={dashboardModalOpen} onOpenChange={setDashboardModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Executive Dashboard - Detaylı Görünüm</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Günlük Performans</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 bg-blue-50 rounded-lg">
                    <p className="text-xs text-blue-600 mb-1">Doluluk Oranı</p>
                    <p className="text-2xl font-bold text-blue-700">
                      {dailyFlash?.occupancy_rate?.toFixed(1) || 0}%
                    </p>
                  </div>
                  <div className="p-3 bg-green-50 rounded-lg">
                    <p className="text-xs text-green-600 mb-1">RevPAR</p>
                    <p className="text-2xl font-bold text-green-700">
                      ₺{dailyFlash?.revpar?.toFixed(0) || 0}
                    </p>
                  </div>
                  <div className="p-3 bg-indigo-50 rounded-lg">
                    <p className="text-xs text-indigo-600 mb-1">ADR</p>
                    <p className="text-2xl font-bold text-indigo-700">
                      ₺{dailyFlash?.adr?.toFixed(0) || 0}
                    </p>
                  </div>
                  <div className="p-3 bg-amber-50 rounded-lg">
                    <p className="text-xs text-amber-600 mb-1">Günlük Gelir</p>
                    <p className="text-2xl font-bold text-amber-700">
                      ₺{dailyFlash?.total_revenue?.toFixed(0) || 0}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Operasyonel Durum</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">Toplam Oda:</span>
                  <span className="font-bold">{roomStatus?.total_rooms || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Dolu Odalar:</span>
                  <span className="font-bold text-blue-700">{roomStatus?.status_counts?.occupied || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Müsait Odalar:</span>
                  <span className="font-bold text-green-700">{roomStatus?.status_counts?.available || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Temizlik Bekleyen:</span>
                  <span className="font-bold text-red-700">{roomStatus?.status_counts?.dirty || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Bakımda:</span>
                  <span className="font-bold text-amber-700">{roomStatus?.status_counts?.maintenance || 0}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Finansal Özet</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-600">Bugünkü Tahsilat:</span>
                  <span className="font-bold text-green-700">₺{financeSnapshot?.today_collections?.toFixed(0) || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Bekleyen Alacaklar:</span>
                  <span className="font-bold text-amber-700">₺{financeSnapshot?.pending_receivables?.toFixed(0) || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Aylık Toplam Gelir:</span>
                  <span className="font-bold text-blue-700">₺{financeSnapshot?.monthly_revenue?.toFixed(0) || 0}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>

      {/* Pickup Analysis Modal */}
      <Dialog open={pickupModalOpen} onOpenChange={setPickupModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>📊 Pickup Analizi</DialogTitle>
          </DialogHeader>
          {pickupData && (
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">{t("common.summary")}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Toplam Rezervasyon:</span>
                    <span className="font-bold">{pickupData.summary?.total_rooms || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Toplam Gelir:</span>
                    <span className="font-bold">₺{pickupData.summary?.total_revenue?.toFixed(0) || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Ort. Rezervasyon Zamanı:</span>
                    <span className="font-bold">{pickupData.summary?.avg_days_before?.toFixed(0) || 0} gün önce</span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Booking Window Analizi</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {pickupData.pickup_trends && Object.entries(pickupData.pickup_trends).map(([days, data]) => (
                    <div key={days} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <span className="text-sm">{days} gün önce:</span>
                      <div className="text-right">
                        <p className="text-sm font-bold">{data.rooms} oda</p>
                        <p className="text-xs text-gray-500">₺{data.revenue?.toFixed(0)}</p>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Anomaly Detection Modal */}
      <Dialog open={anomalyModalOpen} onOpenChange={setAnomalyModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>⚠️ Anomali Tespiti</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            {anomalies.length === 0 ? (
              <div className="text-center py-8">
                <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-2" />
                <p className="text-gray-600">Hiç anomali tespit edilmedi! ✨</p>
              </div>
            ) : (
              anomalies.map((anomaly, idx) => (
                <Card key={idx} className={`border-2 ${
                  anomaly.severity === 'high' ? 'border-red-300 bg-red-50' :
                  anomaly.severity === 'medium' ? 'border-yellow-300 bg-yellow-50' :
                  'border-blue-300 bg-blue-50'
                }`}>
                  <CardContent className="p-3">
                    <div className="flex items-start space-x-2">
                      <AlertCircle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                        anomaly.severity === 'high' ? 'text-red-600' :
                        anomaly.severity === 'medium' ? 'text-yellow-600' :
                        'text-blue-600'
                      }`} />
                      <div className="flex-1">
                        <p className="font-bold text-sm mb-1">{anomaly.message}</p>
                        <div className="flex items-center space-x-2 text-xs text-gray-600">
                          <Badge className={
                            anomaly.severity === 'high' ? 'bg-red-500' :
                            anomaly.severity === 'medium' ? 'bg-yellow-500' :
                            'bg-blue-500'
                          }>
                            {anomaly.type}
                          </Badge>
                          {anomaly.room_number && (
                            <span>Oda: {anomaly.room_number}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Forecast Modal */}
      <Dialog open={forecastModalOpen} onOpenChange={setForecastModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>📅 Tahminler</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Haftalık Tahmin (4 Hafta)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {weeklyForecast.map((week) => (
                  <div key={week.week_number} className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                    <div className="flex items-center justify-between mb-2">
                      <p className="font-bold text-gray-900">Hafta {week.week_number}</p>
                      <Badge className="bg-blue-500">{week.expected_occupancy?.toFixed(0) || 0}% Doluluk</Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <p className="text-gray-600">Rezervasyon:</p>
                        <p className="font-bold">{week.bookings}</p>
                      </div>
                      <div>
                        <p className="text-gray-600">Gelir:</p>
                        <p className="font-bold">₺{week.expected_revenue?.toFixed(0) || 0}</p>
                      </div>
                      <div>
                        <p className="text-gray-600">ADR:</p>
                        <p className="font-bold">₺{week.avg_rate?.toFixed(0) || 0}</p>
                      </div>
                      <div>
                        <p className="text-gray-600">Tarih:</p>
                        <p className="text-xs">{week.start_date}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Aylık Tahmin (3 Ay)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {monthlyForecast.map((month) => (
                  <div key={month.month_number} className="p-3 bg-green-50 rounded-lg border border-green-200">
                    <div className="flex items-center justify-between mb-2">
                      <p className="font-bold text-gray-900">{month.month}</p>
                      <Badge className="bg-green-500">{month.expected_occupancy?.toFixed(0) || 0}% Doluluk</Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <p className="text-gray-600">Rezervasyon:</p>
                        <p className="font-bold">{month.bookings}</p>
                      </div>
                      <div>
                        <p className="text-gray-600">Gelir:</p>
                        <p className="font-bold">₺{month.expected_revenue?.toFixed(0) || 0}</p>
                      </div>
                      <div>
                        <p className="text-gray-600">ADR:</p>
                        <p className="font-bold">₺{month.avg_rate?.toFixed(0) || 0}</p>
                      </div>
                      <div>
                        <p className="text-gray-600">RevPAR:</p>
                        <p className="font-bold">₺{month.revpar?.toFixed(0) || 0}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>

      {/* Reports Modal */}
      <Dialog open={reportsModalOpen} onOpenChange={setReportsModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Executive Raporlar</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Bugünkü Flash Rapor</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <p className="text-gray-500">Doluluk:</p>
                    <p className="font-bold">{dailyFlash?.occupancy_rate?.toFixed(1) || 0}%</p>
                  </div>
                  <div>
                    <p className="text-gray-500">RevPAR:</p>
                    <p className="font-bold">₺{dailyFlash?.revpar?.toFixed(0) || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">ADR:</p>
                    <p className="font-bold">₺{dailyFlash?.adr?.toFixed(0) || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Günlük Gelir:</p>
                    <p className="font-bold">₺{dailyFlash?.total_revenue?.toFixed(0) || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Gelen Misafir:</p>
                    <p className="font-bold">{dailyFlash?.arrivals || 0}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">Çıkan Misafir:</p>
                    <p className="font-bold">{dailyFlash?.departures || 0}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Departman Durumu</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between p-2 bg-green-50 rounded">
                  <span className="text-sm">{t("nav.frontDesk")}</span>
                  <Badge className="bg-green-500">Operasyonel</Badge>
                </div>
                <div className="flex items-center justify-between p-2 bg-green-50 rounded">
                  <span className="text-sm">Housekeeping</span>
                  <Badge className="bg-green-500">
                    {roomStatus?.status_counts?.dirty || 0} kirli oda
                  </Badge>
                </div>
                <div className="flex items-center justify-between p-2 bg-green-50 rounded">
                  <span className="text-sm">Teknik Servis</span>
                  <Badge className="bg-green-500">
                    {roomStatus?.status_counts?.maintenance || 0} bakımda
                  </Badge>
                </div>
                <div className="flex items-center justify-between p-2 bg-green-50 rounded">
                  <span className="text-sm">F&B</span>
                  <Badge className="bg-green-500">Operasyonel</Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Performans Göstergeleri</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Ortalama Konaklama Süresi:</span>
                  <span className="font-bold">{dailyFlash?.avg_stay_duration || 0} gece</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Rezervasyon Kaynağı (OTA):</span>
                  <span className="font-bold">{dailyFlash?.ota_percentage || 0}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Direkt Rezervasyon:</span>
                  <span className="font-bold">{dailyFlash?.direct_percentage || 0}%</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>

      {/* Property Selector Modal */}
      <Dialog open={propertyModalOpen} onOpenChange={setPropertyModalOpen}>
        <DialogContent className="max-w-full w-[95vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center space-x-2">
              <Building2 className="w-5 h-5 text-red-600" />
              <span>Tesis Seçimi</span>
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-3">
            {/* Selected Property Info */}
            {selectedProperty && (
              <Card className="bg-gradient-to-r from-red-50 to-pink-50 border-red-200">
                <CardContent className="p-4">
                  <div className="flex items-center space-x-3">
                    <CheckCircle className="w-8 h-8 text-red-600" />
                    <div className="flex-1">
                      <p className="text-sm text-gray-600">Şu anda görüntülenen:</p>
                      <p className="font-bold text-gray-900">{selectedProperty.name}</p>
                      <p className="text-xs text-gray-500">{selectedProperty.location} • {selectedProperty.rooms} oda</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Property List */}
            <div className="space-y-2">
              <p className="text-sm font-medium text-gray-700 mb-2">Tüm Tesisler:</p>
              {properties.map((property) => (
                <Button
                  key={property.id}
                  variant={selectedProperty?.id === property.id ? "default" : "outline"}
                  className={`w-full justify-start h-auto p-4 ${
                    selectedProperty?.id === property.id 
                      ? 'bg-red-600 hover:bg-red-700 text-white border-red-600' 
                      : 'bg-white hover:bg-gray-50'
                  }`}
                  onClick={() => {
                    setSelectedProperty(property);
                    setPropertyModalOpen(false);
                    toast.success(`${property.name} tesisine geçildi!`);
                    loadData(); // Reload data for new property
                  }}
                >
                  <div className="flex items-center space-x-3 w-full">
                    <Building2 className={`w-8 h-8 ${
                      selectedProperty?.id === property.id ? 'text-white' : 'text-red-600'
                    }`} />
                    <div className="flex-1 text-left">
                      <p className={`font-bold ${
                        selectedProperty?.id === property.id ? 'text-white' : 'text-gray-900'
                      }`}>
                        {property.name}
                      </p>
                      <p className={`text-sm ${
                        selectedProperty?.id === property.id ? 'text-red-100' : 'text-gray-600'
                      }`}>
                        📍 {property.location}
                      </p>
                      <div className="flex items-center space-x-3 mt-1">
                        <span className={`text-xs ${
                          selectedProperty?.id === property.id ? 'text-red-100' : 'text-gray-500'
                        }`}>
                          🛏️ {property.rooms} oda
                        </span>
                        <Badge className={
                          property.status === 'active' 
                            ? 'bg-green-500' 
                            : 'bg-gray-500'
                        }>
                          {property.status === 'active' ? 'Aktif' : 'Pasif'}
                        </Badge>
                      </div>
                    </div>
                    {selectedProperty?.id === property.id && (
                      <CheckCircle className="w-6 h-6 text-white" />
                    )}
                  </div>
                </Button>
              ))}
            </div>

            {/* Portfolio Summary */}
            <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200 mt-4">
              <CardContent className="p-4">
                <p className="text-sm font-bold text-gray-900 mb-2">📊 Portföy Özeti</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="text-center p-2 bg-white rounded">
                    <p className="text-xs text-gray-600">Toplam Tesis</p>
                    <p className="text-2xl font-bold text-blue-700">{properties.length}</p>
                  </div>
                  <div className="text-center p-2 bg-white rounded">
                    <p className="text-xs text-gray-600">Toplam Oda</p>
                    <p className="text-2xl font-bold text-green-700">
                      {properties.reduce((sum, p) => sum + p.rooms, 0)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MobileGM;
