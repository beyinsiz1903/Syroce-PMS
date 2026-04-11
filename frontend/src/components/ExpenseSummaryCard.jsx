import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DollarSign, TrendingDown, Package, Users, Zap, ShoppingCart } from 'lucide-react';

const ExpenseSummaryCard = ({ expenseData }) => {
  if (!expenseData || !expenseData.categories) {
    return null;
  }

  const getCategoryIcon = (category) => {
    switch(category) {
      case 'fnb_costs': return <Package className="w-4 h-4" />;
      case 'housekeeping_expenses': return <TrendingDown className="w-4 h-4" />;
      case 'staff_costs': return <Users className="w-4 h-4" />;
      case 'utilities': return <Zap className="w-4 h-4" />;
      case 'procurement': return <ShoppingCart className="w-4 h-4" />;
      default: return <DollarSign className="w-4 h-4" />;
    }
  };

  const categories = Object.entries(expenseData.categories || {});

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Gider Kategorileri</span>
          <span className="text-sm font-normal text-gray-500">
            Toplam: ₺{expenseData.total_expenses?.toLocaleString('tr-TR')}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {categories.map(([key, data]) => (
            <div key={key} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg text-blue-600">
                  {getCategoryIcon(key)}
                </div>
                <div>
                  <p className="font-medium text-sm">{data.category}</p>
                  {key === 'staff_costs' && data.hourly_rate_avg && (
                    <p className="text-xs text-gray-500">Ortalama: ₺{data.hourly_rate_avg}/saat</p>
                  )}
                </div>
              </div>
              <div className="text-right">
                <p className="font-bold text-gray-900">₺{data.amount?.toLocaleString('tr-TR')}</p>
                <p className="text-xs text-gray-500">
                  {((data.amount / expenseData.total_expenses) * 100).toFixed(1)}%
                </p>
              </div>
            </div>
          ))}
        </div>
        
        <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-amber-800">Günlük Ortalama</span>
            <span className="text-sm font-bold text-amber-900">₺{expenseData.daily_average?.toLocaleString('tr-TR')}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ExpenseSummaryCard;