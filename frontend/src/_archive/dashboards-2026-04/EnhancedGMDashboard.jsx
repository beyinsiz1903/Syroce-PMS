import { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import MetricDetailModal from '@/components/MetricDetailModal';
import useRealTimeData from '@/hooks/useRealTimeData';
import { 
  TrendingUp, 
  TrendingDown,
  DollarSign, 
  Users, 
  Bed, 
  Calendar,
  Target,
  Activity,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  Clock,
  Star,
  TrendingUpIcon
} from 'lucide-react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { useTranslation } from 'react-i18next';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const EnhancedGMDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [selectedMetric, setSelectedMetric] = useState(null);
  const [forecastData, setForecastData] = useState(null);

  // Real-time dashboard data (updates every 30 seconds)
  const { 
    data: dashboardData, 
    loading, 
    lastUpdate, 
    refresh 
  } = useRealTimeData(
    async () => {
      const response = await axios.get('/dashboard/role-based', { timeout: 15000 });
      return response.data;
    },
    30000, // 30 seconds
    true
  );

  // Load forecast data
  useEffect(() => {
    loadForecast();
  }, []);

  const loadForecast = async () => {
    try {
      const response = await axios.get('/dashboard/gm-forecast', { timeout: 15000 });
      setForecastData(response.data);
    } catch (error) {
      console.error('Failed to load forecast:', error);
    }
  };

  const getTrendIcon = (value) => {
    if (value > 0) return <TrendingUp className="w-4 h-4 text-green-600" />;
    if (value < 0) return <TrendingDown className="w-4 h-4 text-red-600" />;
    return null;
  };

  const openMetricDetail = (metric) => {
    setSelectedMetric(metric);
  };

  if (loading && !dashboardData) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout}>
        <div className="flex items-center justify-center h-screen">
          <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  // Prepare forecast chart data
  const forecastChartData = forecastData ? {
    labels: forecastData.daily_forecast?.slice(0, 30).map(f => {
      const date = new Date(f.date);
      return `${date.getMonth() + 1}/${date.getDate()}`;
    }) || [],
    datasets: [
      {
        label: 'Forecasted Occupancy %',
        data: forecastData.daily_forecast?.slice(0, 30).map(f => f.predicted_occupancy) || [],
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.4
      }
    ]
  } : null;

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-6 space-y-6">
        {/* Header with Real-time Indicator */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold" style={{ fontFamily: 'Space Grotesk' }}>
              GM Dashboard
            </h1>
            <p className="text-gray-600">
              Real-time hotel performance overview
            </p>
          </div>
          <div className="flex items-center gap-4">
            {lastUpdate && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <Clock className="w-4 h-4" />
                <span>Last updated: {lastUpdate.toLocaleTimeString()}</span>
              </div>
            )}
            <Button onClick={refresh} variant="outline" size="sm">
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
          </div>
        </div>

        {/* Key Metrics Cards - VERTICAL LAYOUT */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {/* Occupancy */}
          <Card 
            className="cursor-pointer hover:shadow-md transition-all p-4 text-center"
            onClick={() => openMetricDetail({
              title: 'Occupancy Rate',
              description: 'Current hotel occupancy percentage',
              value: `${dashboardData?.occupancy?.current || 0}%`,
              icon: Bed,
              breakdown: {
                'Occupied Rooms': dashboardData?.occupancy?.occupied_rooms || 0,
                'Total Rooms': dashboardData?.occupancy?.total_rooms || 0,
                'Available Rooms': (dashboardData?.occupancy?.total_rooms || 0) - (dashboardData?.occupancy?.occupied_rooms || 0)
              }
            })}
          >
            <CardContent className="p-0 space-y-2">
              <div className="flex justify-center mb-2">
                <div className="bg-blue-100 p-2 rounded-lg">
                  <Bed className="w-6 h-6 text-blue-500" />
                </div>
              </div>
              <div className="text-2xl font-bold text-gray-900">
                {dashboardData?.occupancy?.current || 0}%
              </div>
              <div className="text-xs font-medium text-gray-600">
                Occupancy Rate
              </div>
            </CardContent>
          </Card>

          {/* Total Rooms */}
          <Card 
            className="cursor-pointer hover:shadow-md transition-all p-4 text-center"
            onClick={() => openMetricDetail({
              title: 'Total Rooms',
              description: 'Total available rooms in property',
              value: dashboardData?.occupancy?.total_rooms || 0,
              icon: Bed
            })}
          >
            <CardContent className="p-0 space-y-2">
              <div className="flex justify-center mb-2">
                <div className="bg-green-100 p-2 rounded-lg">
                  <Bed className="w-6 h-6 text-green-500" />
                </div>
              </div>
              <div className="text-2xl font-bold text-gray-900">
                {dashboardData?.occupancy?.total_rooms || 0}
              </div>
              <div className="text-xs font-medium text-gray-600">
                Total Rooms
              </div>
            </CardContent>
          </Card>

          {/* Arrivals Today */}
          <Card 
            className="cursor-pointer hover:shadow-md transition-all p-4 text-center"
            onClick={() => openMetricDetail({
              title: 'Arrivals Today',
              description: 'Expected check-ins for today',
              value: dashboardData?.today_movements?.arrivals || 0,
              icon: CheckCircle
            })}
          >
            <CardContent className="p-0 space-y-2">
              <div className="flex justify-center mb-2">
                <div className="bg-purple-100 p-2 rounded-lg">
                  <CheckCircle className="w-6 h-6 text-purple-500" />
                </div>
              </div>
              <div className="text-2xl font-bold text-gray-900">
                {dashboardData?.today_movements?.arrivals || 0}
              </div>
              <div className="text-xs font-medium text-gray-600">
                Today's Check-ins
              </div>
            </CardContent>
          </Card>

          {/* Total Guests */}
          <Card 
            className="cursor-pointer hover:shadow-md transition-all p-4 text-center"
            onClick={() => openMetricDetail({
              title: 'Total Guests',
              description: 'Total guests currently in house',
              value: (dashboardData?.occupancy?.occupied_rooms || 0) * 1.5,
              icon: Users
            })}
          >
            <CardContent className="p-0 space-y-2">
              <div className="flex justify-center mb-2">
                <div className="bg-orange-100 p-2 rounded-lg">
                  <Users className="w-6 h-6 text-orange-500" />
                </div>
              </div>
              <div className="text-2xl font-bold text-gray-900">
                {Math.round((dashboardData?.occupancy?.occupied_rooms || 0) * 1.5)}
              </div>
              <div className="text-xs font-medium text-gray-600">
                Total Guests
              </div>
            </CardContent>
          </Card>
        </div>

        {/* VIP Arrivals & Priorities */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* VIP Arrivals */}
          {dashboardData?.vip_arrivals && dashboardData.vip_arrivals.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Star className="w-5 h-5 text-yellow-500" />
                  VIP Arrivals Today
                </CardTitle>
                <CardDescription>Special attention required</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {dashboardData.vip_arrivals.map((vip, idx) => (
                    <div key={idx} className="flex items-center justify-between p-3 bg-yellow-50 rounded-lg">
                      <div>
                        <div className="font-semibold">{vip.guest_name}</div>
                        <div className="text-sm text-gray-600">Room {vip.room_number}</div>
                        <div className="text-xs text-gray-500">{vip.preferences}</div>
                      </div>
                      <Badge variant="outline" className="bg-yellow-100">VIP</Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Today's Priorities */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-red-500" />
                Today's Priorities
              </CardTitle>
              <CardDescription>Action items requiring attention</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
                  <div>
                    <div className="font-semibold">Pending Check-ins</div>
                    <div className="text-sm text-gray-600">Guests arriving today</div>
                  </div>
                  <div className="text-2xl font-bold text-blue-600">
                    {dashboardData?.priorities?.pending_checkins || 0}
                  </div>
                </div>
                
                <div className="flex items-center justify-between p-3 bg-orange-50 rounded-lg">
                  <div>
                    <div className="font-semibold">Pending Check-outs</div>
                    <div className="text-sm text-gray-600">Guests departing today</div>
                  </div>
                  <div className="text-2xl font-bold text-orange-600">
                    {dashboardData?.priorities?.pending_checkouts || 0}
                  </div>
                </div>
                
                <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                  <div>
                    <div className="font-semibold">Housekeeping Completed</div>
                    <div className="text-sm text-gray-600">Rooms cleaned today</div>
                  </div>
                  <div className="text-2xl font-bold text-green-600">
                    {dashboardData?.priorities?.housekeeping_completed || 0}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 30-Day Forecast */}
        {forecastChartData && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUpIcon className="w-5 h-5 text-blue-500" />
                30-Day Occupancy Forecast
              </CardTitle>
              <CardDescription>
                AI-powered demand prediction • Avg: {forecastData?.summary?.avg_occupancy}% • 
                Peak Days: {forecastData?.summary?.peak_days_count}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64">
                <Line 
                  data={forecastChartData} 
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                      legend: {
                        display: false
                      },
                      tooltip: {
                        callbacks: {
                          label: function(context) {
                            return `Occupancy: ${context.parsed.y}%`;
                          }
                        }
                      }
                    },
                    scales: {
                      y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                          callback: function(value) {
                            return value + '%';
                          }
                        }
                      }
                    }
                  }}
                />
              </div>

              {/* Forecast Alerts */}
              {forecastData?.alerts && forecastData.alerts.length > 0 && (
                <div className="mt-4 pt-4 border-t">
                  <div className="text-sm font-semibold mb-2">⚠️ High Demand Alerts:</div>
                  <div className="flex flex-wrap gap-2">
                    {forecastData.alerts.map((alert, idx) => (
                      <Badge key={idx} variant="outline" className="bg-red-50">
                        {new Date(alert.date).toLocaleDateString()} - {alert.occupancy}%
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Quick Actions */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Button onClick={() => navigate('/pms')} className="h-20">
            <div className="text-center">
              <Bed className="w-6 h-6 mx-auto mb-1" />
              <div className="text-sm">PMS</div>
            </div>
          </Button>
          <Button onClick={() => navigate('/rms')} variant="outline" className="h-20">
            <div className="text-center">
              <Target className="w-6 h-6 mx-auto mb-1" />
              <div className="text-sm">Revenue</div>
            </div>
          </Button>
          <Button onClick={() => navigate('/reports')} variant="outline" className="h-20">
            <div className="text-center">
              <Activity className="w-6 h-6 mx-auto mb-1" />
              <div className="text-sm">Reports</div>
            </div>
          </Button>
          <Button onClick={() => navigate('/housekeeping')} variant="outline" className="h-20">
            <div className="text-center">
              <CheckCircle className="w-6 h-6 mx-auto mb-1" />
              <div className="text-sm">Housekeeping</div>
            </div>
          </Button>
        </div>
      </div>

      {/* Metric Detail Modal */}
      <MetricDetailModal 
        isOpen={!!selectedMetric}
        onClose={() => setSelectedMetric(null)}
        metric={selectedMetric}
      />
    </Layout>
  );
};

export default EnhancedGMDashboard;
