import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import PropertySwitcher from '@/components/PropertySwitcher';
import { 
  ArrowLeft, 
  TrendingUp,
  TrendingDown,
  DollarSign,
  Calendar,
  RefreshCw,
  Target,
  BarChart3,
  Activity
} from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useTranslation } from 'react-i18next';

const RevenueManagementMobile = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pickupData, setPickupData] = useState(null);
  const [paceReport, setPaceReport] = useState(null);
  const [rateRecommendations, setRateRecommendations] = useState(null);
  const [historicalComparison, setHistoricalComparison] = useState(null);
  const [activeView, setActiveView] = useState('pickup'); // pickup, pace, rates, comparison

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      
      const [pickupRes, paceRes, ratesRes, comparisonRes] = await Promise.all([
        axios.get('/revenue/pickup-analysis'),
        axios.get('/revenue/pace-report'),
        axios.get('/revenue/rate-recommendations'),
        axios.get('/revenue/historical-comparison')
      ]);
      
      setPickupData(pickupRes.data);
      setPaceReport(paceRes.data);
      setRateRecommendations(ratesRes.data);
      setHistoricalComparison(comparisonRes.data);
    } catch (error) {
      console.error('Failed to load revenue data:', error);
      toast.error('Gelir verileri yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  if (loading && !refreshing) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-blue-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="h-12 w-12 animate-spin text-green-600 mx-auto mb-4" />
          <p className="text-gray-600">Revenue verileri yükleniyor...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-green-50 to-blue-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-green-600 to-blue-600 text-white p-4 sticky top-0 z-10 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-2 hover:bg-white/20 rounded-lg transition">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold">{t('rms.title')}</h1>
              <p className="text-green-100 text-sm">Gelir Yönetimi</p>
            </div>
          </div>
          
          <button
            onClick={handleRefresh}
            className="p-2 hover:bg-white/20 rounded-lg transition"
            disabled={refreshing}
          >
            <RefreshCw className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {/* View Tabs */}
        <div className="flex gap-2 overflow-x-auto">
          <button
            onClick={() => setActiveView('pickup')}
            className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${
              activeView === 'pickup' ? 'bg-white text-green-600' : 'bg-white/20'
            }`}
          >
            Pickup
          </button>
          <button
            onClick={() => setActiveView('pace')}
            className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${
              activeView === 'pace' ? 'bg-white text-green-600' : 'bg-white/20'
            }`}
          >
            Pace
          </button>
          <button
            onClick={() => setActiveView('rates')}
            className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${
              activeView === 'rates' ? 'bg-white text-green-600' : 'bg-white/20'
            }`}
          >
            Fiyatlar
          </button>
          <button
            onClick={() => setActiveView('comparison')}
            className={`px-3 py-1 rounded-lg text-sm whitespace-nowrap ${
              activeView === 'comparison' ? 'bg-white text-green-600' : 'bg-white/20'
            }`}
          >
            Karşılaştırma
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Pickup Analysis View */}
        {activeView === 'pickup' && pickupData && (
          <>
            {/* Summary Cards */}
            <div className="grid grid-cols-3 gap-2">
              <Card className="bg-white">
                <CardContent className="p-3">
                  <div className="text-xs text-gray-500">Ort. Doluluk</div>
                  <div className="text-xl font-bold text-green-600">
                    %{pickupData.summary.avg_occupancy_30d}
                  </div>
                </CardContent>
              </Card>
              <Card className="bg-white">
                <CardContent className="p-3">
                  <div className="text-xs text-gray-500">Ort. Gelir</div>
                  <div className="text-xl font-bold text-blue-600">
                    ₺{(pickupData.summary.avg_revenue_30d / 1000).toFixed(0)}K
                  </div>
                </CardContent>
              </Card>
              <Card className="bg-white">
                <CardContent className="p-3">
                  <div className="text-xs text-gray-500">Trend</div>
                  <div className="flex items-center justify-center pt-1">
                    {pickupData.summary.trend === 'up' ? (
                      <TrendingUp className="h-6 w-6 text-green-500" />
                    ) : (
                      <TrendingDown className="h-6 w-6 text-red-500" />
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Pickup Chart */}
            <Card>
              <CardContent className="p-4">
                <h3 className="font-semibold mb-3">Doluluk Trendi (30 Gün)</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={[...pickupData.historical, ...pickupData.forecast]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={(date) => new Date(date).getDate()}
                      fontSize={10}
                    />
                    <YAxis fontSize={10} />
                    <Tooltip />
                    <Line 
                      type="monotone" 
                      dataKey="occupancy" 
                      stroke="#10b981" 
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
                <div className="flex gap-2 mt-2 text-xs">
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 bg-green-500 rounded"></div>
                    <span>Gerçekleşen</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 bg-blue-500 rounded"></div>
                    <span>Forecast</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        )}

        {/* Pace Report View */}
        {activeView === 'pace' && paceReport && (
          <>
            <Card className="bg-gradient-to-r from-blue-500 to-purple-500 text-white">
              <CardContent className="p-4">
                <div className="flex justify-between items-center">
                  <div>
                    <div className="text-sm opacity-90">Bu Yıl vs Geçen Yıl</div>
                    <div className="text-3xl font-bold mt-1">
                      {paceReport.summary.total_this_year}
                    </div>
                  </div>
                  <Badge className={`${
                    paceReport.summary.pace_status === 'ahead' 
                      ? 'bg-green-500' 
                      : 'bg-red-500'
                  } text-white`}>
                    {paceReport.summary.pace_status === 'ahead' ? 'Önde' : 'Geride'}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            {/* Pace Chart */}
            <Card>
              <CardContent className="p-4">
                <h3 className="font-semibold mb-3">Rezervasyon Hızı (30 Gün)</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={paceReport.pace_data.slice(0, 14)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="date" 
                      tickFormatter={(date) => new Date(date).getDate()}
                      fontSize={10}
                    />
                    <YAxis fontSize={10} />
                    <Tooltip />
                    <Bar dataKey="this_year" fill="#3b82f6" name="Bu Yıl" />
                    <Bar dataKey="last_year" fill="#9ca3af" name="Geçen Yıl" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </>
        )}

        {/* Rate Recommendations View */}
        {activeView === 'rates' && rateRecommendations && (
          <>
            <Card className="bg-gradient-to-r from-amber-500 to-orange-500 text-white">
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  <Target className="h-6 w-6" />
                  <div>
                    <div className="text-sm opacity-90">Ortalama Öneri</div>
                    <div className="text-2xl font-bold">
                      %{rateRecommendations.summary.avg_recommended_increase > 0 ? '+' : ''}
                      {rateRecommendations.summary.avg_recommended_increase}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-2">
              {rateRecommendations.recommendations.map((rec) => (
                <Card key={rec.date} className="hover:shadow-lg transition">
                  <CardContent className="p-4">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <div className="font-semibold">
                          {new Date(rec.date).toLocaleDateString('tr-TR', { 
                            weekday: 'short', 
                            month: 'short', 
                            day: 'numeric' 
                          })}
                        </div>
                        <div className="text-sm text-gray-600">
                          Doluluk: %{rec.current_occupancy}
                        </div>
                      </div>
                      <Badge className={`${
                        rec.strategy === 'maximize' ? 'bg-green-500' :
                        rec.strategy === 'optimize' ? 'bg-blue-500' :
                        rec.strategy === 'stimulate' ? 'bg-orange-500' :
                        'bg-gray-500'
                      } text-white`}>
                        {rec.strategy === 'maximize' ? 'Maksimize' :
                         rec.strategy === 'optimize' ? 'Optimize' :
                         rec.strategy === 'stimulate' ? 'Talep Artır' : 'Koru'}
                      </Badge>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-600">Mevcut: ₺{rec.current_rate}</span>
                      <span className="font-bold text-green-600">
                        Öneri: ₺{rec.recommended_rate} ({rec.variance_pct > 0 ? '+' : ''}%{rec.variance_pct})
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-2">
                      {rec.reason}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Historical Comparison View */}
        {activeView === 'comparison' && historicalComparison && (
          <>
            <Card className="bg-gradient-to-r from-purple-500 to-pink-500 text-white">
              <CardContent className="p-4">
                <h3 className="font-semibold mb-3">Bu Ay vs Geçen Yıl</h3>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <div className="text-2xl font-bold">{historicalComparison.this_year.bookings}</div>
                    <div className="text-xs opacity-90">Rezervasyon</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold">₺{(historicalComparison.this_year.revenue / 1000).toFixed(0)}K</div>
                    <div className="text-xs opacity-90">{t("finance.revenue")}</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold">₺{historicalComparison.this_year.adr}</div>
                    <div className="text-xs opacity-90">ADR</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-2 gap-3">
              <Card>
                <CardContent className="p-3">
                  <div className="text-xs text-gray-500 mb-1">Rezervasyon Değişimi</div>
                  <div className={`text-2xl font-bold ${
                    historicalComparison.variance.bookings_pct > 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {historicalComparison.variance.bookings_pct > 0 ? '+' : ''}
                    %{historicalComparison.variance.bookings_pct}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3">
                  <div className="text-xs text-gray-500 mb-1">Gelir Değişimi</div>
                  <div className={`text-2xl font-bold ${
                    historicalComparison.variance.revenue_pct > 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {historicalComparison.variance.revenue_pct > 0 ? '+' : ''}
                    %{historicalComparison.variance.revenue_pct}
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardContent className="p-4">
                <h3 className="font-semibold mb-3">Detaylı Karşılaştırma</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center pb-2 border-b">
                    <span className="text-sm text-gray-600">Rezervasyon</span>
                    <div className="text-right">
                      <div className="font-semibold">{historicalComparison.this_year.bookings}</div>
                      <div className="text-xs text-gray-500">Geçen yıl: {historicalComparison.last_year.bookings}</div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center pb-2 border-b">
                    <span className="text-sm text-gray-600">{t("finance.revenue")}</span>
                    <div className="text-right">
                      <div className="font-semibold">₺{historicalComparison.this_year.revenue.toLocaleString()}</div>
                      <div className="text-xs text-gray-500">Geçen yıl: ₺{historicalComparison.last_year.revenue.toLocaleString()}</div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">ADR</span>
                    <div className="text-right">
                      <div className="font-semibold">₺{historicalComparison.this_year.adr}</div>
                      <div className="text-xs text-gray-500">Geçen yıl: ₺{historicalComparison.last_year.adr}</div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* Property Switcher */}
      <PropertySwitcher onPropertyChange={() => loadData()} />
    </div>
  );
};

export default RevenueManagementMobile;
