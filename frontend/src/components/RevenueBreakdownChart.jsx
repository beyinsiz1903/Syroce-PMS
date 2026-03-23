import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { DollarSign, TrendingUp } from 'lucide-react';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

const RevenueBreakdownChart = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const res = await axios.get('/revenue/breakdown');
      setData(res.data);
    } catch (error) {
      console.error('Failed to load revenue breakdown:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading...</div>;
  if (!data) return null;

  const chartData = data.breakdown.map(item => ({
    name: item.category,
    value: item.amount
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center">
          <DollarSign className="w-5 h-5 mr-2 text-green-600" />
          Revenue Breakdown - {data.month}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm text-gray-600">Total Revenue</p>
            <p className="text-3xl font-bold text-green-600">
              ${data.total_revenue.toLocaleString()}
            </p>
          </div>
          <TrendingUp className="w-12 h-12 text-green-600" />
        </div>

        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
              outerRadius={100}
              fill="#8884d8"
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => `$${value.toLocaleString()}`} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>

        <div className="mt-4 space-y-2">
          {data.breakdown.map((item, idx) => (
            <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 rounded">
              <div className="flex items-center">
                <div
                  className="w-4 h-4 rounded mr-2"
                  style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                />
                <span className="text-sm font-medium">{item.category}</span>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold">${item.amount.toLocaleString()}</p>
                <p className="text-xs text-gray-500">{item.percentage}%</p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default RevenueBreakdownChart;