import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { UtensilsCrossed } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';

const OutletSalesChart = () => {
  const { t } = useTranslation();
  const [salesData, setSalesData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSalesData();
  }, []);

  const loadSalesData = async () => {
    try {
      const response = await axios.get('/pos/outlet-sales-breakdown');
      setSalesData(response.data);
    } catch (error) {
      console.error('Failed to load outlet sales:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !salesData) {
    return <div className="text-center py-4">{t('cm.components_OutletSalesChart.yukleniyor')}</div>;
  }

  const outlets = salesData.outlets;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <UtensilsCrossed className="w-5 h-5 mr-2" />
          {t('cm.components_OutletSalesChart.outlet_bazinda_satislar')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {Object.entries(outlets).map(([name, data]) => (
            <div key={name}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">{name}</span>
                <div className="text-right">
                  <div className="text-sm font-bold">{formatCurrencyBreakdown(data.sales_by_currency, data.sales, salesData.currency)}</div>
                  <div className="text-xs text-gray-500">{data.orders} {t('cm.components_OutletSalesChart.siparis')}</div>
                </div>
              </div>
              {Object.entries(data.sales_by_currency || {}).map(([currency, amount]) => {
                const max = Math.max(...Object.values(outlets).map(o => Number(o.sales_by_currency?.[currency] || 0)), 0);
                return <div key={currency} className="text-xs text-gray-500">{currency === 'UNKNOWN' ? 'Para birimi bilinmiyor' : currency}<div className="w-full bg-gray-200 rounded-full h-3"><div className="bg-gradient-to-r from-amber-400 to-amber-600 h-3 rounded-full" style={{ width: `${max > 0 ? amount / max * 100 : 0}%` }} /></div></div>;
              })}
              <div className="text-xs text-gray-500 mt-1">
                Ortalama: {formatCurrencyBreakdown(
                  Object.fromEntries(Object.entries(data.sales_by_currency || {}).filter(([currency]) => data.orders_by_currency?.[currency]).map(([currency, amount]) => [currency, amount / data.orders_by_currency[currency]])),
                  data.avg_ticket,
                  salesData.currency,
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t">
          <div className="flex items-center justify-between">
            <span className="font-bold">{t('cm.components_OutletSalesChart.toplam_satis')}</span>
            <span className="text-lg font-bold text-amber-600">
              {formatCurrencyBreakdown(salesData.total_sales_by_currency, salesData.total_sales, salesData.currency)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default OutletSalesChart;
