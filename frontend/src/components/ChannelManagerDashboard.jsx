import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Globe, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

const ChannelManagerDashboard = () => {
  const [overview, setOverview] = useState(null);
  const [rateComparison, setRateComparison] = useState(null);
  const [revenueByChannel, setRevenueByChannel] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [overviewRes, ratesRes, revenueRes] = await Promise.all([
        axios.get('/channel-manager/overview'),
        axios.get('/channel-manager/rate-comparison'),
        axios.get('/channel-manager/revenue-by-channel')
      ]);
      
      setOverview(overviewRes.data);
      setRateComparison(ratesRes.data);
      setRevenueByChannel(revenueRes.data);
    } catch (error) {
      console.error('Failed to load channel manager data:', error);
      toast.error('✗ Veri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  if (loading || !overview) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  const getChannelLogo = (channel) => {
    const logos = {
      booking_com: '🏛️',
      expedia: '✈️',
      airbnb: '🏠',
      direct: '🌐'
    };
    return logos[channel] || '🏛️';
  };

  return (
    <div className="space-y-4">
      {/* Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-lg">
            <span className="flex items-center">
              <Globe className="w-5 h-5 mr-2" />
              Channel Manager
            </span>
            <Button size="sm" variant="ghost" onClick={loadData}>
              <RefreshCw className="w-4 h-4" />
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="text-center p-3 bg-blue-50 rounded-lg">
              <div className="text-2xl font-bold text-blue-600">
                {overview.summary.total_bookings_today}
              </div>
              <div className="text-xs text-gray-600">Bugünkü Rezervasyon</div>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg">
              <div className="text-2xl font-bold text-green-600">
                ₺{overview.summary.total_revenue_today.toLocaleString()}
              </div>
              <div className="text-xs text-gray-600">Bugünkü Gelir</div>
            </div>
          </div>

          {/* Channels */}
          <div className="space-y-2">
            {Object.entries(overview.channels).map(([key, channel]) => (
              <div key={key} className="p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <span className="text-2xl">{getChannelLogo(key)}</span>
                    <div>
                      <div className="font-medium text-sm">{channel.name}</div>
                      <div className="text-xs text-gray-500">
                        {channel.bookings_today} rezervasyon • ₺{channel.revenue_today}
                      </div>
                    </div>
                  </div>
                  <Badge className={channel.status === 'connected' ? 'bg-green-500' : 'bg-gray-500'}>
                    {channel.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Rate Comparison */}
      {rateComparison && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Fiyat Karşılaştırma</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(rateComparison.channels).map(([key, data]) => (
                <div key={key} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                  <span className="text-sm">{key}</span>
                  <div className="flex items-center space-x-2">
                    <span className="font-bold">₺{data.rate}</span>
                    <Badge variant="outline" className="text-xs">
                      #{data.rank}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
            
            <div className="mt-4 p-3 bg-blue-50 rounded-lg">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Sizin Fiyatınız:</span>
                <span className="text-lg font-bold text-blue-600">
                  ₺{rateComparison.your_rate}
                </span>
              </div>
              <div className="flex items-center justify-between mt-2">
                <span className="text-xs text-gray-600">Öneri:</span>
                <div className="flex items-center space-x-1">
                  {rateComparison.recommendation === 'increase' ? (
                    <TrendingUp className="w-4 h-4 text-green-500" />
                  ) : (
                    <TrendingDown className="w-4 h-4 text-red-500" />
                  )}
                  <span className="text-sm font-medium">
                    ₺{rateComparison.suggested_rate}
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ChannelManagerDashboard;
