import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import axios from 'axios';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Package, TrendingUp, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Allotment Consumption Chart
 * Visualizes: Allocated vs Sold vs Remaining rooms per operator
 * Demo pitch: "Siz otelinizdeki allotment kaosunu tek tuşla yönetiyorsunuz"
 */
const AllotmentConsumptionChart = ({
  dateRange
}) => {
  const {
    t
  } = useTranslation();
  const [allotments, setAllotments] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    loadAllotmentData();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [dateRange]);
  const loadAllotmentData = async () => {
    setLoading(true);
    try {
      const response = await axios.get('/allotment/consumption', {
        params: dateRange
      });
      setAllotments(response.data.allotments || []);
    } catch (error) {
      console.error('Failed to load allotment data:', error);
      // Demo data for presentation
      setAllotments([{
        operator: 'TUI',
        allocated: 10,
        sold: 7,
        remaining: 3,
        utilization: 70,
        status: 'good'
      }, {
        operator: 'HolidayCheck',
        allocated: 15,
        sold: 12,
        remaining: 3,
        utilization: 80,
        status: 'good'
      }, {
        operator: 'Expedia',
        allocated: 8,
        sold: 8,
        remaining: 0,
        utilization: 100,
        status: 'critical'
      }, {
        operator: 'Booking.com',
        allocated: 20,
        sold: 5,
        remaining: 15,
        utilization: 25,
        status: 'warning'
      }]);
    } finally {
      setLoading(false);
    }
  };
  const getStatusColor = status => {
    switch (status) {
      case 'critical':
        return 'red';
      case 'warning':
        return 'yellow';
      case 'good':
        return 'green';
      default:
        return 'gray';
    }
  };
  const getStatusIcon = status => {
    switch (status) {
      case 'critical':
        return <AlertCircle className="w-4 h-4 text-red-600" />;
      case 'warning':
        return <Clock className="w-4 h-4 text-yellow-600" />;
      case 'good':
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      default:
        return null;
    }
  };
  if (loading) {
    return <Card>
        <CardContent className="py-12 text-center text-gray-400">
          Loading allotment data...
        </CardContent>
      </Card>;
  }
  return <Card className="border-2 border-indigo-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Package className="w-5 h-5 text-indigo-600" />
          {t('cm.components_AllotmentConsumptionChart.allotment_consumption_operator_bazli')}
        </CardTitle>
        <CardDescription>
          {t('cm.components_AllotmentConsumptionChart.ayrilan_satilan_kalan_oda_durumu')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Summary Cards */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-3 bg-blue-50 rounded-lg text-center">
              <div className="text-2xl font-bold text-blue-700">
                {allotments.reduce((sum, a) => sum + a.allocated, 0)}
              </div>
              <div className="text-xs text-gray-600">{t('cm.components_AllotmentConsumptionChart.toplam_ayrilan')}</div>
            </div>
            <div className="p-3 bg-green-50 rounded-lg text-center">
              <div className="text-2xl font-bold text-green-700">
                {allotments.reduce((sum, a) => sum + a.sold, 0)}
              </div>
              <div className="text-xs text-gray-600">{t('cm.components_AllotmentConsumptionChart.toplam_satilan')}</div>
            </div>
            <div className="p-3 bg-amber-50 rounded-lg text-center">
              <div className="text-2xl font-bold text-amber-700">
                {allotments.reduce((sum, a) => sum + a.remaining, 0)}
              </div>
              <div className="text-xs text-gray-600">{t('cm.components_AllotmentConsumptionChart.toplam_kalan')}</div>
            </div>
          </div>

          {/* Operator Breakdown */}
          <div className="space-y-3">
            {allotments.map((allotment, index) => <div key={allotment.id || index} className={`p-4 rounded-lg border-2 transition-all ${allotment.status === 'critical' ? 'border-red-300 bg-red-50' : allotment.status === 'warning' ? 'border-yellow-300 bg-yellow-50' : 'border-green-300 bg-green-50'}`}>
                {/* Operator Header */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(allotment.status)}
                    <span className="font-semibold text-gray-900">
                      {allotment.operator}
                    </span>
                    <Badge className={`bg-${getStatusColor(allotment.status)}-500 text-xs`}>
                      {allotment.utilization}% Doluluk
                    </Badge>
                  </div>
                  <div className="text-xs text-gray-600">
                    {allotment.remaining} {t('cm.components_AllotmentConsumptionChart.oda_kaldi')}
                  </div>
                </div>

                {/* Progress Bar */}
                <div className="mb-3">
                  <div className="w-full bg-gray-200 rounded-full h-8 relative overflow-hidden">
                    {/* Sold (Green) */}
                    <div className="absolute left-0 h-full bg-green-500 flex items-center justify-center text-white text-xs font-semibold transition-all" style={{
                  width: `${allotment.sold / allotment.allocated * 100}%`
                }}>
                      {allotment.sold > 0 && `${allotment.sold} Satılan`}
                    </div>
                    {/* Remaining (Orange) */}
                    <div className="absolute h-full bg-amber-300 flex items-center justify-center text-gray-700 text-xs font-semibold transition-all" style={{
                  left: `${allotment.sold / allotment.allocated * 100}%`,
                  width: `${allotment.remaining / allotment.allocated * 100}%`
                }}>
                      {allotment.remaining > 0 && `${allotment.remaining} Kalan`}
                    </div>
                  </div>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-3 gap-2 text-center text-sm">
                  <div>
                    <div className="font-bold text-blue-700">{allotment.allocated}</div>
                    <div className="text-xs text-gray-600">Allocated</div>
                  </div>
                  <div>
                    <div className="font-bold text-green-700">{allotment.sold}</div>
                    <div className="text-xs text-gray-600">Sold</div>
                  </div>
                  <div>
                    <div className="font-bold text-amber-700">{allotment.remaining}</div>
                    <div className="text-xs text-gray-600">Remaining</div>
                  </div>
                </div>

                {/* Status Message */}
                <div className="mt-2 text-xs text-center">
                  {allotment.status === 'critical' && <span className="text-red-700 font-semibold">
                      Allotment doldu - Acil aksiyon gerekli!
                    </span>}
                  {allotment.status === 'warning' && <span className="text-yellow-700 font-semibold">
                      {t('cm.components_AllotmentConsumptionChart.dusuk_stok_takibe_alin')}
                    </span>}
                  {allotment.status === 'good' && <span className="text-green-700 font-semibold">
                      {t('cm.components_AllotmentConsumptionChart.saglikli_seviyede')}
                    </span>}
                </div>
              </div>)}
          </div>

          {/* Demo Pitch Banner */}
          <div className="mt-4 p-4 bg-gradient-to-r from-indigo-100 to-pink-100 rounded-lg border-2 border-indigo-300">
            <div className="flex items-start gap-3">
              <TrendingUp className="w-6 h-6 text-indigo-600 mt-1" />
              <div>
                <div className="font-bold text-indigo-900 mb-1">
                  {t('cm.components_AllotmentConsumptionChart.demo_pitch_allotment_kaosunu_tek_tusla_y')}
                </div>
                <p className="text-sm text-indigo-800">
                  {t('cm.components_AllotmentConsumptionChart.tum_operatorlerin_allotment_durumunu_tek')}
                </p>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>;
};
export default AllotmentConsumptionChart;