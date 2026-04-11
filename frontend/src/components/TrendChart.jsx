import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, TrendingDown } from 'lucide-react';

const TrendChart = ({ trendData }) => {
  if (!trendData || !trendData.trend || trendData.trend.length === 0) {
    return null;
  }

  const { trend, changes } = trendData;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Son 7 Gün Trend Analizi</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trend}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="day_name" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="arrivals" stroke="#10b981" name="Girişler" strokeWidth={2} />
            <Line type="monotone" dataKey="departures" stroke="#ef4444" name="Çıkışlar" strokeWidth={2} />
            <Line type="monotone" dataKey="occupancy" stroke="#3b82f6" name="Doluluk" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>

        {changes && (
          <div className="mt-4 grid grid-cols-4 gap-3">
            <div className="p-3 bg-green-50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                {changes.arrivals_change >= 0 ? 
                  <TrendingUp className="w-4 h-4 text-green-600" /> : 
                  <TrendingDown className="w-4 h-4 text-red-600" />
                }
                <span className="text-xs text-gray-600">Girişler</span>
              </div>
              <p className="text-lg font-bold text-gray-900">{changes.arrivals_change > 0 ? '+' : ''}{changes.arrivals_change}</p>
            </div>

            <div className="p-3 bg-red-50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                {changes.departures_change >= 0 ? 
                  <TrendingUp className="w-4 h-4 text-red-600" /> : 
                  <TrendingDown className="w-4 h-4 text-green-600" />
                }
                <span className="text-xs text-gray-600">Çıkışlar</span>
              </div>
              <p className="text-lg font-bold text-gray-900">{changes.departures_change > 0 ? '+' : ''}{changes.departures_change}</p>
            </div>

            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                {changes.occupancy_change >= 0 ? 
                  <TrendingUp className="w-4 h-4 text-blue-600" /> : 
                  <TrendingDown className="w-4 h-4 text-red-600" />
                }
                <span className="text-xs text-gray-600">Doluluk</span>
              </div>
              <p className="text-lg font-bold text-gray-900">{changes.occupancy_change > 0 ? '+' : ''}{changes.occupancy_change}</p>
            </div>

            <div className="p-3 bg-amber-50 rounded-lg">
              <div className="flex items-center gap-2 mb-1">
                {changes.revenue_change >= 0 ? 
                  <TrendingUp className="w-4 h-4 text-green-600" /> : 
                  <TrendingDown className="w-4 h-4 text-red-600" />
                }
                <span className="text-xs text-gray-600">Gelir</span>
              </div>
              <p className="text-sm font-bold text-gray-900">₺{Math.abs(changes.revenue_change)?.toLocaleString('tr-TR')}</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default TrendChart;