import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart3, TrendingUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MarketSegmentChart = () => {
  const { t } = useTranslation();
  const [segmentData, setSegmentData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSegmentData();
  }, []);

  const loadSegmentData = async () => {
    try {
      const response = await axios.get('/revenue/market-segment-breakdown');
      setSegmentData(response.data);
    } catch (error) {
      console.error('Failed to load segment data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !segmentData) {
    return <div className="text-center py-4">{t('cm.components_MarketSegmentChart.yukleniyor')}</div>;
  }

  const segments = segmentData.segments;
  const colors = {
    OTA: 'bg-blue-500',
    Direct: 'bg-green-500',
    Corporate: 'bg-indigo-500',
    Group: 'bg-amber-500'
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <BarChart3 className="w-5 h-5 mr-2" />
          {t('cm.components_MarketSegmentChart.market_segment_kirilimi')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {Object.entries(segments).map(([name, data]) => (
            <div key={name}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">{name}</span>
                <span className="text-sm font-bold">
                  ₺{data.revenue.toLocaleString()} ({data.revenue_pct}%)
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`${colors[name]} h-2 rounded-full transition-all duration-500`}
                  style={{ width: `${data.revenue_pct}%` }}
                />
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {data.bookings} rezervasyon • {data.rooms} oda
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t">
          <div className="flex items-center justify-between">
            <span className="font-bold">{t('cm.components_MarketSegmentChart.toplam_gelir')}</span>
            <span className="text-lg font-bold text-green-600">
              ₺{segmentData.total_revenue.toLocaleString()}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default MarketSegmentChart;
