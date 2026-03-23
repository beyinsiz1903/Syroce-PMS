import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Building2, TrendingUp, DollarSign, Users, Calendar } from 'lucide-react';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { useTranslation } from 'react-i18next';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

const MultiPropertyDashboard = () => {
  const { t } = useTranslation();
  const [properties, setProperties] = useState([]);
  const [selectedProperty, setSelectedProperty] = useState('all');
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProperties();
    loadDashboardData();
  }, [selectedProperty]);

  const loadProperties = async () => {
    try {
      const response = await axios.get('/multi-property/properties');
      setProperties(response.data.properties || []);
    } catch (error) {
      console.error('Failed to load properties:', error);
    }
  };

  const loadDashboardData = async () => {
    try {
      const params = selectedProperty !== 'all' ? { property_id: selectedProperty } : {};
      const response = await axios.get('/multi-property/dashboard', { params });
      setDashboardData(response.data);
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const chartData = {
    labels: properties.map(p => p.name),
    datasets: [
      {
        label: 'Revenue',
        data: dashboardData?.property_revenues || [],
        backgroundColor: 'rgba(59, 130, 246, 0.8)'
      },
      {
        label: 'Occupancy %',
        data: dashboardData?.property_occupancies || [],
        backgroundColor: 'rgba(16, 185, 129, 0.8)'
      }
    ]
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">{t('dashboard.multiProperty')}</h1>
          <p className="text-gray-600">{t('dashboard.multiPropertyDesc')}</p>
        </div>
        <div className="w-64">
          <Select value={selectedProperty} onValueChange={setSelectedProperty}>
            <SelectTrigger>
              <SelectValue placeholder="{t('common.property')}" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('common.all')}</SelectItem>
              {properties.map(prop => (
                <SelectItem key={prop.id} value={prop.id}>{prop.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">{t('common.property')}</p>
                <p className="text-3xl font-bold">{properties.length}</p>
              </div>
              <Building2 className="w-8 h-8 text-purple-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">{t('reports.totalRevenue')}</p>
                <p className="text-3xl font-bold">${(dashboardData?.total_revenue || 0).toLocaleString()}</p>
              </div>
              <DollarSign className="w-8 h-8 text-green-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">{t('reports.occupancyRate')}</p>
                <p className="text-3xl font-bold">{(dashboardData?.avg_occupancy || 0).toFixed(1)}%</p>
              </div>
              <TrendingUp className="w-8 h-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">{t('dashboard.totalGuests')}</p>
                <p className="text-3xl font-bold">{dashboardData?.total_guests || 0}</p>
              </div>
              <Users className="w-8 h-8 text-orange-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">{t('dashboard.totalRooms')}</p>
                <p className="text-3xl font-bold">{dashboardData?.total_rooms || 0}</p>
              </div>
              <Calendar className="w-8 h-8 text-cyan-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Performance Chart */}
      <Card>
        <CardHeader>
          <CardTitle>{t('dashboard.multiProperty')} Comparison</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-96">
            <Bar
              data={chartData}
              options={{
                responsive: true,
                maintainAspectRatio: false
              }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Properties Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {properties.map((property) => (
          <Card key={property.id} className="hover:shadow-lg transition">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Building2 className="w-5 h-5 text-purple-500" />
                <CardTitle className="text-lg">{property.name}</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Location:</span>
                  <span className="font-semibold">{property.city}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Rooms:</span>
                  <span className="font-semibold">{property.total_rooms}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Occupancy:</span>
                  <span className="font-semibold">{property.occupancy_rate}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Revenue (MTD):</span>
                  <span className="font-semibold">${property.revenue_mtd?.toLocaleString()}</span>
                </div>
                <Button size="sm" variant="outline" className="w-full mt-2">
                  View Details
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default MultiPropertyDashboard;