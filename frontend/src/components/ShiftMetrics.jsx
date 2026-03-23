import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Clock } from 'lucide-react';

const ShiftMetrics = () => {
  const [shiftData, setShiftData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadShiftData();
  }, []);

  const loadShiftData = async () => {
    try {
      const response = await axios.get('/pos/shift-metrics');
      setShiftData(response.data);
    } catch (error) {
      console.error('Failed to load shift metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading || !shiftData) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  const shifts = shiftData.shifts;
  const shiftColors = {
    morning: 'bg-yellow-500',
    afternoon: 'bg-orange-500',
    evening: 'bg-purple-500'
  };

  const shiftNames = {
    morning: 'Sabah',
    afternoon: 'Öğle',
    evening: 'Akşam'
  };

  const shiftIcons = {
    morning: '☀️',
    afternoon: '🌞',
    evening: '🌙'
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <Clock className="w-5 h-5 mr-2" />
          Vardiya Metrikleri
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(shifts).map(([key, data]) => (
            <div key={key} className="text-center">
              <div className={`${shiftColors[key]} text-white rounded-lg p-3`}>
                <div className="text-2xl mb-1">{shiftIcons[key]}</div>
                <div className="text-xs font-medium">{shiftNames[key]}</div>
                <div className="text-xs opacity-80">{data.hours}</div>
                <div className="text-lg font-bold mt-2">₺{data.sales}</div>
                <div className="text-xs opacity-90">{data.orders} sipariş</div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default ShiftMetrics;
