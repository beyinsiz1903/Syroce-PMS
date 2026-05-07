import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Ban, CheckCircle, AlertTriangle, Clock } from 'lucide-react';

/**
 * Stop-Sale Manager
 * Quick toggle to stop sales for specific operators/channels
 * Use case: TUI stop-sale verdiğinde tek tıkla kapatmak
 */
const StopSaleManager = ({ operators = [] }) => {
  const [stopSaleStatus, setStopSaleStatus] = useState({});
  const [loading, setLoading] = useState({});

  React.useEffect(() => {
    loadStopSaleStatus();
  }, []);

  const loadStopSaleStatus = async () => {
    try {
      const response = await axios.get('/api/rates/stop-sale/status');
      setStopSaleStatus(response.data.operators || {});
    } catch (error) {
      console.error('Failed to load stop-sale status:', error);
    }
  };

  const toggleStopSale = async (operatorId, operatorName) => {
    setLoading({ ...loading, [operatorId]: true });
    try {
      const currentStatus = stopSaleStatus[operatorId];
      const newStatus = !currentStatus;

      await axios.post('/api/rates/stop-sale/toggle', {
        operator_id: operatorId,
        stop_sale: newStatus
      });

      setStopSaleStatus({
        ...stopSaleStatus,
        [operatorId]: newStatus
      });

      if (newStatus) {
        toast.success(`${operatorName} için stop-sale aktif edildi!`);
      } else {
        toast.success(`${operatorName} için stop-sale kaldırıldı!`);
      }
    } catch (error) {
      toast.error('Stop-sale durumu değiştirilemedi');
    } finally {
      setLoading({ ...loading, [operatorId]: false });
    }
  };

  const defaultOperators = operators.length > 0 ? operators : [
    { id: 'tui', name: 'TUI', color: 'blue' },
    { id: 'holidaycheck', name: 'HolidayCheck', color: 'green' },
    { id: 'expedia', name: 'Expedia', color: 'yellow' },
    { id: 'booking', name: 'Booking.com', color: 'blue' }
  ];

  return (
    <Card className="border-2 border-amber-300">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Ban className="w-5 h-5 text-amber-600" />
          Stop-Sale Yönetimi
        </CardTitle>
        <CardDescription>
          Operatör bazlı satışları tek tıkla durdur/başlat
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {/* Warning Info */}
          <div className="p-3 bg-amber-50 border-l-4 border-amber-500 rounded mb-4">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5" />
              <div className="text-xs text-amber-800">
                <strong>Dikkat:</strong> Stop-sale aktif olduğunda, seçili operatörden yeni rezervasyon alınamaz.
                Mevcut rezervasyonlar etkilenmez.
              </div>
            </div>
          </div>

          {/* Operators List */}
          {defaultOperators.map((operator) => {
            const isStopSale = stopSaleStatus[operator.id] || false;
            const isLoading = loading[operator.id] || false;

            return (
              <div
                key={operator.id}
                className={`p-4 rounded-lg border-2 transition-all ${
                  isStopSale
                    ? 'border-red-300 bg-red-50'
                    : 'border-green-300 bg-green-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  {/* Operator Info */}
                  <div className="flex items-center gap-3">
                    {isStopSale ? (
                      <Ban className="w-6 h-6 text-red-600" />
                    ) : (
                      <CheckCircle className="w-6 h-6 text-green-600" />
                    )}
                    <div>
                      <div className="font-semibold text-gray-900">
                        {operator.name}
                      </div>
                      <div className="text-xs text-gray-600">
                        {isStopSale ? (
                          <span className="text-red-700 font-semibold">
                            Stop-Sale Aktif - Satışlar Durdu
                          </span>
                        ) : (
                          <span className="text-green-700 font-semibold">
                            Aktif - Satışlar Devam Ediyor
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Toggle Button */}
                  <Button
                    onClick={() => toggleStopSale(operator.id, operator.name)}
                    disabled={isLoading}
                    className={`min-w-[140px] ${
                      isStopSale
                        ? 'bg-green-600 hover:bg-green-700'
                        : 'bg-red-600 hover:bg-red-700'
                    }`}
                  >
                    {isLoading ? (
                      <Clock className="w-4 h-4 mr-2 animate-spin" />
                    ) : isStopSale ? (
                      <CheckCircle className="w-4 h-4 mr-2" />
                    ) : (
                      <Ban className="w-4 h-4 mr-2" />
                    )}
                    {isLoading
                      ? 'İşleniyor...'
                      : isStopSale
                      ? 'Satışları Başlat'
                      : 'Stop-Sale Aktif Et'}
                  </Button>
                </div>

                {/* Timestamp */}
                {stopSaleStatus[`${operator.id}_timestamp`] && (
                  <div className="text-xs text-gray-500 mt-2 pt-2 border-t">
                    Son değişiklik:{' '}
                    {new Date(stopSaleStatus[`${operator.id}_timestamp`]).toLocaleString('tr-TR')}
                  </div>
                )}
              </div>
            );
          })}

          {/* Summary */}
          <div className="mt-4 p-3 bg-gray-100 rounded text-sm">
            <strong>Özet:</strong>
            <div className="mt-2 flex gap-4">
              <span className="text-green-700">
                Aktif: {Object.values(stopSaleStatus).filter(s => !s).length}
              </span>
              <span className="text-red-700">
                Stop-Sale: {Object.values(stopSaleStatus).filter(s => s).length}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default StopSaleManager;
