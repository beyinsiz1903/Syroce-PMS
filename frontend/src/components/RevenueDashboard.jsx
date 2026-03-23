import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Bar, Doughnut } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DollarSign, TrendingUp, TrendingDown, Calendar } from 'lucide-react';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
);

const RevenueDashboard = () => {
  const [revenueData, setRevenueData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState('month');

  useEffect(() => {
    loadRevenueData();
  }, [dateRange]);

  const loadRevenueData = async () => {
    try {
      const today = new Date();
      let startDate, endDate;

      if (dateRange === 'week') {
        startDate = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 7);
        endDate = today;
      } else if (dateRange === 'month') {
        startDate = new Date(today.getFullYear(), today.getMonth(), 1);
        endDate = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      } else if (dateRange === 'year') {
        startDate = new Date(today.getFullYear(), 0, 1);
        endDate = new Date(today.getFullYear(), 11, 31);
      }

      const response = await axios.get('/reports/revenue', {
        params: {
          start_date: startDate.toISOString().split('T')[0],
          end_date: endDate.toISOString().split('T')[0]
        }
      });

      setRevenueData(response.data);
    } catch (error) {
      console.error('Failed to load revenue data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !revenueData) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-4 text-gray-600">Loading revenue data...</p>
      </div>
    );
  }

  const barChartData = {
    labels: ['Room Revenue', 'F&B Revenue', 'Other Revenue'],
    datasets: [
      {
        label: 'Revenue ($)',
        data: [
          revenueData.room_revenue || 0,
          revenueData.fnb_revenue || 0,
          revenueData.other_revenue || 0
        ],
        backgroundColor: [
          'rgba(59, 130, 246, 0.8)',
          'rgba(16, 185, 129, 0.8)',
          'rgba(245, 158, 11, 0.8)'
        ],
        borderColor: [
          'rgb(59, 130, 246)',
          'rgb(16, 185, 129)',
          'rgb(245, 158, 11)'
        ],
        borderWidth: 2
      }
    ]
  };

  const doughnutData = {
    labels: ['Room', 'F&B', 'Other'],
    datasets: [
      {
        data: [
          revenueData.room_revenue || 0,
          revenueData.fnb_revenue || 0,
          revenueData.other_revenue || 0
        ],
        backgroundColor: [
          'rgba(59, 130, 246, 0.8)',
          'rgba(16, 185, 129, 0.8)',
          'rgba(245, 158, 11, 0.8)'
        ],
        borderColor: '#fff',
        borderWidth: 2
      }
    ]
  };

  const totalRevenue = (revenueData.room_revenue || 0) + (revenueData.fnb_revenue || 0) + (revenueData.other_revenue || 0);
  const avgDailyRate = revenueData.adr || 0;
  const revPar = revenueData.revpar || 0;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Total Revenue</p>
                <p className="text-2xl font-bold">${totalRevenue.toLocaleString()}</p>
              </div>
              <DollarSign className="w-8 h-8 text-green-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">ADR</p>
                <p className="text-2xl font-bold">${avgDailyRate.toFixed(2)}</p>
              </div>
              <TrendingUp className="w-8 h-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">RevPAR</p>
                <p className="text-2xl font-bold">${revPar.toFixed(2)}</p>
              </div>
              <Calendar className="w-8 h-8 text-purple-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Occupancy</p>
                <p className="text-2xl font-bold">{(revenueData.occupancy_rate || 0).toFixed(1)}%</p>
              </div>
              <TrendingUp className="w-8 h-8 text-orange-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Revenue by Department</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <Bar
                data={barChartData}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: {
                      display: false
                    }
                  },
                  scales: {
                    y: {
                      beginAtZero: true,
                      ticks: {
                        callback: function(value) {
                          return '$' + value.toLocaleString();
                        }
                      }
                    }
                  }
                }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Revenue Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-80 flex items-center justify-center">
              <Doughnut
                data={doughnutData}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: {
                      position: 'bottom'
                    },
                    tooltip: {
                      callbacks: {
                        label: function(context) {
                          const label = context.label || '';
                          const value = context.parsed || 0;
                          const percentage = ((value / totalRevenue) * 100).toFixed(1);
                          return `${label}: $${value.toLocaleString()} (${percentage}%)`;
                        }
                      }
                    }
                  }
                }}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Revenue Details */}
      <Card>
        <CardHeader>
          <CardTitle>Revenue Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-blue-50 rounded-lg">
              <div className="text-sm text-blue-600 font-semibold">Room Revenue</div>
              <div className="text-2xl font-bold text-blue-700">${(revenueData.room_revenue || 0).toLocaleString()}</div>
              <div className="text-xs text-blue-600 mt-1">
                {((revenueData.room_revenue / totalRevenue) * 100).toFixed(1)}% of total
              </div>
            </div>
            <div className="p-4 bg-green-50 rounded-lg">
              <div className="text-sm text-green-600 font-semibold">F&B Revenue</div>
              <div className="text-2xl font-bold text-green-700">${(revenueData.fnb_revenue || 0).toLocaleString()}</div>
              <div className="text-xs text-green-600 mt-1">
                {((revenueData.fnb_revenue / totalRevenue) * 100).toFixed(1)}% of total
              </div>
            </div>
            <div className="p-4 bg-orange-50 rounded-lg">
              <div className="text-sm text-orange-600 font-semibold">Other Revenue</div>
              <div className="text-2xl font-bold text-orange-700">${(revenueData.other_revenue || 0).toLocaleString()}</div>
              <div className="text-xs text-orange-600 mt-1">
                {((revenueData.other_revenue / totalRevenue) * 100).toFixed(1)}% of total
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default RevenueDashboard;