import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  ArrowLeft, 
  RefreshCw, 
  TrendingUp, 
  TrendingDown, 
  Minus,
  DollarSign,
  PieChart,
  BarChart3,
  Calendar,
  Users,
  XCircle,
  AlertCircle
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const RevenueMobile = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState('overview');
  const [dateRange, setDateRange] = useState('30'); // days
  
  // Data states
  const [adrData, setAdrData] = useState(null);
  const [revparData, setRevparData] = useState(null);
  const [totalRevenue, setTotalRevenue] = useState(null);
  const [segmentData, setSegmentData] = useState(null);
  const [pickupData, setPickupData] = useState(null);
  const [forecastData, setForecastData] = useState(null);
  const [channelData, setChannelData] = useState(null);
  const [cancellationData, setCancellationData] = useState(null);

  useEffect(() => {
    loadData();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [dateRange]);

  const loadData = async () => {
    try {
      setLoading(true);
      
      // Calculate date range
      const end = new Date();
      const start = new Date();
      start.setDate(start.getDate() - parseInt(dateRange));
      
      const startDate = start.toISOString().split('T')[0];
      const endDate = end.toISOString().split('T')[0];
      
      const params = { start_date: startDate, end_date: endDate };

      // Load all data in parallel
      const [adr, revpar, revenue, segment, channel, cancellation] = await Promise.all([
        axios.get('/revenue-mobile/adr', { params }),
        axios.get('/revenue-mobile/revpar', { params }),
        axios.get('/revenue-mobile/total-revenue', { params }),
        axios.get('/revenue-mobile/segment-distribution', { params }),
        axios.get('/revenue-mobile/channel-distribution', { params }),
        axios.get('/revenue-mobile/cancellation-report', { params })
      ]);

      setAdrData(adr.data);
      setRevparData(revpar.data);
      setTotalRevenue(revenue.data);
      setSegmentData(segment.data);
      setChannelData(channel.data);
      setCancellationData(cancellation.data);

      // Load pickup and forecast separately (different parameters)
      const pickup = await axios.get('/revenue-mobile/pickup-graph');
      setPickupData(pickup.data);

      const forecast = await axios.get('/revenue-mobile/forecast', { params: { days_ahead: 30 } });
      setForecastData(forecast.data);

      toast.success('Veriler güncellendi');
    } catch (error) {
      console.error('Failed to load revenue data:', error);
      toast.error('Veri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const getTrendIcon = (trend) => {
    if (trend === 'up') return <TrendingUp className="h-4 w-4 text-green-600" />;
    if (trend === 'down') return <TrendingDown className="h-4 w-4 text-red-600" />;
    return <Minus className="h-4 w-4 text-gray-400" />;
  };

  const getTrendColor = (trend) => {
    if (trend === 'up') return 'text-green-600';
    if (trend === 'down') return 'text-red-600';
    return 'text-gray-600';
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(amount);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center">
        <RefreshCw className="h-12 w-12 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold">Gelir Yönetimi</h1>
              <p className="text-blue-100 text-sm">Revenue Management</p>
            </div>
          </div>
          <button onClick={loadData} className="p-2 hover:bg-white/20 rounded-lg">
            <RefreshCw className="h-5 w-5" />
          </button>
        </div>

        {/* Date Range Selector */}
        <div className="flex gap-2 overflow-x-auto mb-3">
          {['7', '30', '60', '90'].map(days => (
            <button
              key={days}
              onClick={() => setDateRange(days)}
              className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${
                dateRange === days ? 'bg-white text-blue-600' : 'bg-white/20'
              }`}
            >
              Son {days} Gün
            </button>
          ))}
        </div>

        {/* View Tabs */}
        <div className="flex gap-2 overflow-x-auto">
          {[
            { key: 'overview', label: 'Genel' },
            { key: 'segment', label: 'Segment' },
            { key: 'channel', label: 'Kanal' },
            { key: 'pickup', label: 'Pickup' },
            { key: 'forecast', label: 'Tahmin' },
            { key: 'cancellation', label: t('common.cancel') }
          ].map(view => (
            <button
              key={view.key}
              onClick={() => setActiveView(view.key)}
              className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${
                activeView === view.key ? 'bg-white text-blue-600' : 'bg-white/20'
              }`}
            >
              {view.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {/* Overview View */}
        {activeView === 'overview' && (
          <>
            {/* Key Metrics Grid */}
            <div className="grid grid-cols-2 gap-3">
              {/* ADR Card */}
              <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <DollarSign className="h-5 w-5" />
                    <span className="text-sm font-medium">ADR</span>
                  </div>
                  <div className="text-2xl font-bold">{formatCurrency(adrData?.adr || 0)}</div>
                  <div className="flex items-center gap-1 mt-1 text-sm">
                    {getTrendIcon(adrData?.comparison?.trend)}
                    <span>{adrData?.comparison?.change_pct}%</span>
                  </div>
                </CardContent>
              </Card>

              {/* RevPAR Card */}
              <Card className="bg-gradient-to-br from-indigo-500 to-indigo-600 text-white">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="h-5 w-5" />
                    <span className="text-sm font-medium">RevPAR</span>
                  </div>
                  <div className="text-2xl font-bold">{formatCurrency(revparData?.revpar || 0)}</div>
                  <div className="flex items-center gap-1 mt-1 text-sm">
                    {getTrendIcon(revparData?.comparison?.trend)}
                    <span>{revparData?.comparison?.change_pct}%</span>
                  </div>
                </CardContent>
              </Card>

              {/* Occupancy Card */}
              <Card className="bg-gradient-to-br from-indigo-500 to-indigo-600 text-white">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="h-5 w-5" />
                    <span className="text-sm font-medium">Doluluk</span>
                  </div>
                  <div className="text-2xl font-bold">{revparData?.occupancy_pct}%</div>
                  <div className="text-sm mt-1">
                    {revparData?.occupied_room_nights} / {revparData?.available_room_nights} oda gecesi
                  </div>
                </CardContent>
              </Card>

              {/* Total Revenue Card */}
              <Card className="bg-gradient-to-br from-green-500 to-green-600 text-white">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="h-5 w-5" />
                    <span className="text-sm font-medium">Toplam Gelir</span>
                  </div>
                  <div className="text-2xl font-bold">{formatCurrency(totalRevenue?.total_revenue || 0)}</div>
                  <div className="flex items-center gap-1 mt-1 text-sm">
                    {getTrendIcon(totalRevenue?.comparison?.trend)}
                    <span>{totalRevenue?.comparison?.change_pct}%</span>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Revenue Breakdown */}
            <Card>
              <CardContent className="p-4">
                <h3 className="font-bold text-lg mb-3 flex items-center gap-2">
                  <PieChart className="h-5 w-5 text-blue-600" />
                  Gelir Dağılımı
                </h3>
                <div className="space-y-2">
                  {totalRevenue?.revenue_by_category && Object.entries(totalRevenue.revenue_by_category).map(([category, amount]) => (
                    <div key={category} className="flex justify-between items-center">
                      <span className="text-sm capitalize">{category}</span>
                      <span className="font-bold">{formatCurrency(amount)}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}

        {/* Segment Distribution View */}
        {activeView === 'segment' && (
          <>
            <Card>
              <CardContent className="p-4">
                <h3 className="font-bold text-lg mb-3">Segment Analizi</h3>
                <div className="text-sm text-gray-600 mb-4">
                  Toplam: {formatCurrency(segmentData?.total_revenue || 0)}
                </div>
                <div className="space-y-3">
                  {segmentData?.segments?.map(segment => (
                    <div key={segment.segment} className="border-l-4 border-blue-500 pl-3 py-2 bg-blue-50 rounded">
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <div className="font-bold capitalize">{segment.segment}</div>
                          <div className="text-sm text-gray-600">
                            {segment.bookings_count} rezervasyon • {segment.room_nights} gece
                          </div>
                        </div>
                        <Badge className="bg-blue-600">{segment.percentage}%</Badge>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-gray-600">{t("finance.revenue")}</span>
                        <span className="font-bold text-green-600">{formatCurrency(segment.revenue)}</span>
                      </div>
                      <div className="flex justify-between items-center mt-1">
                        <span className="text-sm text-gray-600">Ort. Rezervasyon</span>
                        <span className="font-semibold">{formatCurrency(segment.avg_booking_value)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}

        {/* Channel Distribution View */}
        {activeView === 'channel' && (
          <>
            <Card className="bg-gradient-to-br from-green-50 to-emerald-50">
              <CardContent className="p-4">
                <h3 className="font-bold text-lg mb-2">Kanal Özeti</h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-gray-600">Brüt Gelir</div>
                    <div className="font-bold text-lg">{formatCurrency(channelData?.summary?.total_gross_revenue || 0)}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Net Gelir</div>
                    <div className="font-bold text-lg text-green-600">{formatCurrency(channelData?.summary?.total_net_revenue || 0)}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Komisyon</div>
                    <div className="font-bold text-red-600">{formatCurrency(channelData?.summary?.total_commission || 0)}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Efektif Komisyon</div>
                    <div className="font-bold">{channelData?.summary?.effective_commission_pct}%</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-3">
              {channelData?.channels?.map(channel => (
                <Card key={channel.channel}>
                  <CardContent className="p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <div className="font-bold text-lg capitalize">{channel.channel}</div>
                        <div className="text-sm text-gray-600">
                          {channel.bookings_count} rezervasyon • {channel.room_nights} gece
                        </div>
                      </div>
                      <Badge className="bg-indigo-600">{channel.percentage}%</Badge>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="bg-gray-50 p-2 rounded">
                        <div className="text-gray-600 text-xs">Brüt Gelir</div>
                        <div className="font-bold">{formatCurrency(channel.gross_revenue)}</div>
                      </div>
                      <div className="bg-green-50 p-2 rounded">
                        <div className="text-gray-600 text-xs">Net Gelir</div>
                        <div className="font-bold text-green-600">{formatCurrency(channel.net_revenue)}</div>
                      </div>
                    </div>

                    <div className="mt-2 flex justify-between items-center text-sm">
                      <span className="text-gray-600">Komisyon ({channel.commission_pct}%)</span>
                      <span className="font-bold text-red-600">{formatCurrency(channel.commission)}</span>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Pickup Graph View */}
        {activeView === 'pickup' && (
          <>
            <Card>
              <CardContent className="p-4">
                <h3 className="font-bold text-lg mb-3">Pickup Analizi</h3>
                <div className="text-sm text-gray-600 mb-4">
                  Hedef Tarih: {pickupData?.target_date}
                </div>
                
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-blue-50 p-3 rounded">
                    <div className="text-gray-600 text-xs">Mevcut Doluluk</div>
                    <div className="font-bold text-lg">{pickupData?.current_occupancy}%</div>
                    <div className="text-sm text-gray-600">{pickupData?.current_bookings} / {pickupData?.total_rooms}</div>
                  </div>
                  <div className="bg-green-50 p-3 rounded">
                    <div className="text-gray-600 text-xs">Pickup Hızı (7 gün)</div>
                    <div className="font-bold text-lg">{pickupData?.pickup_velocity?.last_7_days}</div>
                    <div className="text-sm text-gray-600">Günlük ort: {pickupData?.pickup_velocity?.daily_average}</div>
                  </div>
                </div>

                <div className="space-y-2">
                  {pickupData?.pickup_data?.map(data => (
                    <div key={data.days_out} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                      <div>
                        <div className="font-semibold">{data.days_out} gün önce</div>
                        <div className="text-xs text-gray-600">{data.date}</div>
                      </div>
                      <div className="text-right">
                        <div className="font-bold">{data.occupancy_pct}%</div>
                        <div className="text-xs text-gray-600">{data.rooms_booked} oda</div>
                      </div>
                    </div>
                  ))}
                </div>

                {pickupData?.year_over_year && (
                  <div className="mt-4 p-3 bg-indigo-50 rounded">
                    <div className="text-sm font-semibold mb-1">Geçen Yıl Karşılaştırması</div>
                    <div className="flex justify-between items-center">
                      <span className="text-sm">Değişim</span>
                      <div className={`flex items-center gap-1 font-bold ${getTrendColor(pickupData.year_over_year.trend)}`}>
                        {getTrendIcon(pickupData.year_over_year.trend)}
                        <span>{pickupData.year_over_year.change_pct}%</span>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}

        {/* Forecast View */}
        {activeView === 'forecast' && (
          <>
            <Card className="bg-gradient-to-br from-indigo-50 to-indigo-50">
              <CardContent className="p-4">
                <h3 className="font-bold text-lg mb-2">Tahmin Özeti (30 Gün)</h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-gray-600">Tahmini Toplam Gelir</div>
                    <div className="font-bold text-lg text-green-600">
                      {formatCurrency(forecastData?.summary?.total_forecast_revenue || 0)}
                    </div>
                  </div>
                  <div>
                    <div className="text-gray-600">Ort. Doluluk</div>
                    <div className="font-bold text-lg">{forecastData?.summary?.avg_occupancy_pct}%</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Oda Geliri</div>
                    <div className="font-bold">{formatCurrency(forecastData?.summary?.total_room_revenue || 0)}</div>
                  </div>
                  <div>
                    <div className="text-gray-600">Rezervasyon</div>
                    <div className="font-bold">{forecastData?.summary?.total_bookings}</div>
                  </div>
                </div>

                {forecastData?.comparison && (
                  <div className="mt-3 p-2 bg-white rounded">
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-600">Geçen Yıl Varyansı</span>
                      <div className={`flex items-center gap-1 font-bold ${getTrendColor(forecastData.comparison.trend)}`}>
                        {getTrendIcon(forecastData.comparison.trend)}
                        <span>{forecastData.comparison.variance_pct}%</span>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="space-y-2 max-h-[500px] overflow-y-auto">
              {forecastData?.daily_forecast?.slice(0, 14).map(day => (
                <Card key={day.date} className="hover:shadow-md transition">
                  <CardContent className="p-3">
                    <div className="flex justify-between items-center">
                      <div>
                        <div className="font-semibold">{day.date}</div>
                        <div className="text-xs text-gray-600">{day.day_of_week}</div>
                      </div>
                      <div className="text-right">
                        <div className="font-bold text-green-600">{formatCurrency(day.estimated_total_revenue)}</div>
                        <div className="text-xs text-gray-600">{day.occupancy_pct}% doluluk</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Cancellation Report View */}
        {activeView === 'cancellation' && (
          <>
            <Card className="bg-gradient-to-br from-red-50 to-amber-50">
              <CardContent className="p-4">
                <h3 className="font-bold text-lg mb-3 flex items-center gap-2">
                  <XCircle className="h-5 w-5 text-red-600" />
                  İptal & No-Show Özeti
                </h3>
                
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-white p-3 rounded">
                    <div className="text-gray-600 text-xs">İptal Oranı</div>
                    <div className="font-bold text-xl text-red-600">{cancellationData?.summary?.cancellation_rate}%</div>
                    <div className="text-sm text-gray-600">{cancellationData?.summary?.cancellations} iptal</div>
                  </div>
                  <div className="bg-white p-3 rounded">
                    <div className="text-gray-600 text-xs">No-Show Oranı</div>
                    <div className="font-bold text-xl text-amber-600">{cancellationData?.summary?.no_show_rate}%</div>
                    <div className="text-sm text-gray-600">{cancellationData?.summary?.no_shows} no-show</div>
                  </div>
                </div>

                <div className="space-y-2 mb-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Kayıp Gelir</span>
                    <span className="font-bold text-red-600">{formatCurrency(cancellationData?.summary?.total_lost_revenue || 0)}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">Toplanan İptal Ücreti</span>
                    <span className="font-bold text-green-600">{formatCurrency(cancellationData?.summary?.cancellation_fees_collected || 0)}</span>
                  </div>
                  <div className="flex justify-between items-center pt-2 border-t">
                    <span className="text-sm font-semibold">Net Kayıp</span>
                    <span className="font-bold text-red-600">{formatCurrency(cancellationData?.summary?.net_lost_revenue || 0)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* By Channel */}
            <Card>
              <CardContent className="p-4">
                <h3 className="font-bold mb-3">Kanallara Göre</h3>
                <div className="space-y-2">
                  {cancellationData?.by_channel?.map(channel => (
                    <div key={channel.channel} className="p-3 bg-gray-50 rounded">
                      <div className="flex justify-between items-start mb-2">
                        <div className="font-semibold capitalize">{channel.channel}</div>
                        <Badge variant="outline">{channel.rate}%</Badge>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-sm">
                        <div>
                          <div className="text-gray-600 text-xs">{t("common.cancel")}</div>
                          <div className="font-bold">{channel.cancellations}</div>
                        </div>
                        <div>
                          <div className="text-gray-600 text-xs">No-Show</div>
                          <div className="font-bold">{channel.no_shows}</div>
                        </div>
                        <div>
                          <div className="text-gray-600 text-xs">Kayıp</div>
                          <div className="font-bold text-red-600">{formatCurrency(channel.lost_revenue)}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Lead Time Analysis */}
            <Card>
              <CardContent className="p-4">
                <h3 className="font-bold mb-3">İptal Zamanlaması</h3>
                <div className="space-y-2">
                  {cancellationData?.cancellation_lead_time && Object.entries(cancellationData.cancellation_lead_time).map(([key, count]) => (
                    <div key={key} className="flex justify-between items-center p-2 bg-gray-50 rounded">
                      <span className="text-sm capitalize">{key.replace('_', ' ')}</span>
                      <span className="font-bold">{count}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
};

export default RevenueMobile;
