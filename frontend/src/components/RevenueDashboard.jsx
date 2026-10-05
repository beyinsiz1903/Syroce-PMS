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
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';

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
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
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

  const displayCurrency = cachedTenantCurrency();
  const typeTotals = revenueData.revenue_by_type_currency || {};
  const sumTypes = accepted => Object.entries(typeTotals).reduce((totals, [type, byCurrency]) => {
    if (!accepted(type)) return totals;
    Object.entries(byCurrency || {}).forEach(([currency, amount]) => {
      totals[currency] = (totals[currency] || 0) + Number(amount || 0);
    });
    return totals;
  }, {});
  const roomTotals = revenueData.room_revenue_by_currency || sumTypes(type => ['room', 'room_charge', 'accommodation'].includes(type));
  const fnbTotals = sumTypes(type => ['fb', 'fnb', 'food', 'beverage', 'restaurant', 'bar', 'room_service'].includes(type));
  const otherTotals = sumTypes(type => !['room', 'room_charge', 'accommodation', 'fb', 'fnb', 'food', 'beverage', 'restaurant', 'bar', 'room_service'].includes(type));
  const chartCurrency = Object.keys(revenueData.total_revenue_by_currency || {})[0] || displayCurrency;
  const chartValues = [roomTotals[chartCurrency] || 0, fnbTotals[chartCurrency] || 0, otherTotals[chartCurrency] || 0];
  const chartTotal = chartValues.reduce((sum, value) => sum + value, 0);
  const barChartData = {
    labels: ['Oda Geliri', 'Yiyecek-İçecek Geliri', 'Diğer Gelir'],
    datasets: [
      {
        label: `Gelir (${chartCurrency})`,
        data: chartValues,
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
    labels: ['Oda', 'Yiyecek-İçecek', 'Diğer'],
    datasets: [
      {
        data: chartValues,
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

  const avgDailyRate = revenueData.adr || 0;
  const revPar = revenueData.rev_par ?? revenueData.revpar ?? 0;

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-600">Folyoya İşlenen Toplam Gelir</p>
                <p className="text-2xl font-bold">{formatCurrencyBreakdown(revenueData.total_revenue_by_currency, revenueData.total_revenue)}</p>
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
                <p className="text-2xl font-bold">{formatCurrencyBreakdown(revenueData.adr_by_currency, avgDailyRate)}</p>
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
                <p className="text-2xl font-bold">{formatCurrencyBreakdown(revenueData.rev_par_by_currency, revPar)}</p>
              </div>
              <Calendar className="w-8 h-8 text-indigo-500" />
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
              <TrendingUp className="w-8 h-8 text-amber-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Departman Bazlı Gelir ({chartCurrency})</CardTitle>
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
                          return formatCurrency(value, chartCurrency);
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
            <CardTitle>Gelir Dağılımı ({chartCurrency})</CardTitle>
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
                          const percentage = chartTotal ? ((value / chartTotal) * 100).toFixed(1) : '0.0';
                          return `${label}: ${formatCurrency(value, chartCurrency)} (${percentage}%)`;
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
          <CardTitle>Gelir Kırılımı</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-blue-50 rounded-lg">
              <div className="text-sm text-blue-600 font-semibold">Oda Geliri</div>
              <div className="text-2xl font-bold text-blue-700">{formatCurrencyBreakdown(roomTotals, revenueData.room_revenue)}</div>
            </div>
            <div className="p-4 bg-green-50 rounded-lg">
              <div className="text-sm text-green-600 font-semibold">Yiyecek-İçecek Geliri</div>
              <div className="text-2xl font-bold text-green-700">{formatCurrencyBreakdown(fnbTotals, 0)}</div>
            </div>
            <div className="p-4 bg-amber-50 rounded-lg">
              <div className="text-sm text-amber-600 font-semibold">Diğer Gelir</div>
              <div className="text-2xl font-bold text-amber-700">{formatCurrencyBreakdown(otherTotals, 0)}</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default RevenueDashboard;
