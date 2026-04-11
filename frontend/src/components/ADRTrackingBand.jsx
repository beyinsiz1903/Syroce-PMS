import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown } from 'lucide-react';

const ADRTrackingBand = () => {
  const [adrData, setAdrData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadADRData();
  }, []);

  const loadADRData = async () => {
    try {
      const response = await axios.get('/revenue/adr-tracking');
      setAdrData(response.data);
    } catch (error) {
      console.error('Failed to load ADR data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !adrData) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <Card className="bg-gradient-to-br from-indigo-50 to-indigo-100">
      <CardHeader>
        <CardTitle className="text-lg">ADR Takip Bandı</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="text-center">
            <div className="text-xs text-gray-600 mb-1">Geçen Yıl</div>
            <div className="text-2xl font-bold text-gray-700">
              ₺{adrData.last_year_adr}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-600 mb-1">Forecast</div>
            <div className="text-2xl font-bold text-blue-600">
              ₺{adrData.forecast_adr}
            </div>
          </div>
          <div className="text-center">
            <div className="text-xs text-gray-600 mb-1">Gerçekleşen</div>
            <div className="text-2xl font-bold text-green-600">
              ₺{adrData.actual_adr}
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between p-2 bg-white rounded-lg">
            <span className="text-sm">vs Geçen Yıl:</span>
            <Badge className={adrData.vs_last_year_pct >= 0 ? 'bg-green-500' : 'bg-red-500'}>
              {adrData.vs_last_year_pct >= 0 ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
              {Math.abs(adrData.vs_last_year_pct)}%
            </Badge>
          </div>
          <div className="flex items-center justify-between p-2 bg-white rounded-lg">
            <span className="text-sm">vs Forecast:</span>
            <Badge className={adrData.vs_forecast_pct >= 0 ? 'bg-green-500' : 'bg-red-500'}>
              {adrData.vs_forecast_pct >= 0 ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
              {Math.abs(adrData.vs_forecast_pct)}%
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ADRTrackingBand;
