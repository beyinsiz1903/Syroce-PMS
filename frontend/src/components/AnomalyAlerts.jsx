import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { 
  Bell,
  AlertTriangle,
  TrendingDown,
  DollarSign,
  X,
  Activity
} from 'lucide-react';

const AnomalyAlerts = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [anomalies, setAnomalies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    loadAnomalies();
    
    // Auto-refresh every 2 minutes
    const interval = setInterval(() => {
      loadAnomalies();
    }, 120000);
    
    return () => clearInterval(interval);
  }, []);

  const loadAnomalies = async () => {
    try {
      const response = await axios.get('/anomaly/detect');
      setAnomalies(response.data.anomalies || []);
      setUnreadCount(response.data.high_severity_count || 0);
    } catch (error) {
      console.error('Failed to load anomalies:', error);
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'high':
        return 'bg-red-500';
      case 'medium':
        return 'bg-orange-500';
      default:
        return 'bg-yellow-500';
    }
  };

  const getAnomalyIcon = (type) => {
    switch (type) {
      case 'occupancy_drop':
        return <TrendingDown className="h-5 w-5" />;
      case 'revpar_deviation':
        return <DollarSign className="h-5 w-5" />;
      case 'cancellation_spike':
        return <X className="h-5 w-5" />;
      default:
        return <Activity className="h-5 w-5" />;
    }
  };

  return (
    <>
      {/* Floating Bell Button */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed top-4 right-4 z-50 bg-gradient-to-r from-red-600 to-orange-600 text-white rounded-full p-3 shadow-lg hover:shadow-xl transition-all hover:scale-110"
      >
        <Bell className="h-6 w-6" />
        {unreadCount > 0 && (
          <Badge className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full h-6 w-6 flex items-center justify-center p-0 text-xs animate-pulse">
            {unreadCount}
          </Badge>
        )}
      </button>

      {/* Anomaly Alerts Modal */}
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-red-500" />
              Anomali Uyarıları
            </DialogTitle>
          </DialogHeader>

          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-600 mx-auto"></div>
              <p className="text-gray-500 mt-2">Uyarılar yükleniyor...</p>
            </div>
          ) : (
            <div className="space-y-3">
              {anomalies.length === 0 ? (
                <div className="text-center py-8">
                  <AlertTriangle className="h-12 w-12 text-gray-300 mx-auto mb-2" />
                  <p className="text-gray-500">Aktif anomali bulunmuyor</p>
                  <p className="text-xs text-gray-400 mt-1">Sistem normal çalışıyor</p>
                </div>
              ) : (
                anomalies.map((anomaly) => (
                  <div
                    key={anomaly.id}
                    className={`p-4 rounded-lg border-l-4 ${
                      anomaly.severity === 'high'
                        ? 'border-red-500 bg-red-50'
                        : anomaly.severity === 'medium'
                        ? 'border-orange-500 bg-orange-50'
                        : 'border-yellow-500 bg-yellow-50'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-2">
                        {getAnomalyIcon(anomaly.type)}
                        <h4 className="font-bold text-gray-900">{anomaly.title}</h4>
                      </div>
                      <Badge className={`${getSeverityColor(anomaly.severity)} text-white`}>
                        {anomaly.severity === 'high' ? 'Yüksek' : 
                         anomaly.severity === 'medium' ? 'Orta' : 'Düşük'}
                      </Badge>
                    </div>

                    <p className="text-sm text-gray-700 mb-3">{anomaly.message}</p>

                    {anomaly.current_value !== undefined && (
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div className="bg-white p-2 rounded">
                          <div className="text-gray-500">Mevcut</div>
                          <div className="font-bold">{anomaly.current_value}</div>
                        </div>
                        <div className="bg-white p-2 rounded">
                          <div className="text-gray-500">Önceki</div>
                          <div className="font-bold">{anomaly.previous_value}</div>
                        </div>
                      </div>
                    )}

                    <div className="text-xs text-gray-500 mt-2">
                      {new Date(anomaly.detected_at).toLocaleString('tr-TR')}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {anomalies.length > 0 && (
            <div className="text-xs text-gray-500 text-center mt-4">
              Otomatik olarak her 2 dakikada bir güncellenir
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default AnomalyAlerts;