import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Activity, Cpu, HardDrive, Database, Zap, AlertTriangle } from 'lucide-react';

const AdvancedMonitoring = () => {
  const [metrics, setMetrics] = useState(null);
  const [health, setHealth] = useState(null);
  const [thresholds, setThresholds] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    // Refresh every 10 seconds
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [metricsRes, healthRes, thresholdsRes] = await Promise.all([
        axios.get('/monitoring/api-metrics?hours=1'),
        axios.get('/monitoring/system-health'),
        axios.get('/monitoring/alert-thresholds')
      ]);
      
      setMetrics(metricsRes.data);
      setHealth(healthRes.data);
      setThresholds(thresholdsRes.data);
    } catch (error) {
      console.error('Failed to load monitoring data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy':
      case 'operational':
        return 'bg-green-500';
      case 'warning':
        return 'bg-orange-500';
      case 'error':
      case 'critical':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getMetricStatus = (current, warning, critical) => {
    if (current >= critical) return 'critical';
    if (current >= warning) return 'warning';
    return 'healthy';
  };

  if (loading || !health) {
    return <div className="text-center py-4">Yükleniyor...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Health Score */}
      <Card className="bg-gradient-to-br from-blue-50 to-indigo-100">
        <CardContent className="p-6">
          <div className="text-center">
            <div className="text-5xl font-bold text-blue-600 mb-2">
              {health.health_score}%
            </div>
            <div className="text-sm text-gray-600">Sistem Sağlık Skoru</div>
            <div className="mt-3">
              <Badge className={getStatusColor('healthy')}>
                Tüm Sistemler Operasyonel
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* System Resources */}
      {health.system && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center text-base">
              <Cpu className="w-5 h-5 mr-2" />
              Sistem Kaynakları
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* CPU */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">CPU Kullanımı</span>
                <span className="text-sm font-bold">
                  {health.system.cpu?.usage_percent?.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    health.system.cpu?.usage_percent > 80 ? 'bg-red-500' :
                    health.system.cpu?.usage_percent > 60 ? 'bg-orange-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${health.system.cpu?.usage_percent || 0}%` }}
                />
              </div>
            </div>

            {/* Memory */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">Bellek</span>
                <span className="text-sm font-bold">
                  {health.system.memory?.used_gb?.toFixed(1)}GB / {health.system.memory?.total_gb?.toFixed(1)}GB
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    health.system.memory?.percent > 80 ? 'bg-red-500' :
                    health.system.memory?.percent > 60 ? 'bg-orange-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${health.system.memory?.percent || 0}%` }}
                />
              </div>
            </div>

            {/* Disk */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">Disk</span>
                <span className="text-sm font-bold">
                  {health.system.disk?.used_gb?.toFixed(1)}GB / {health.system.disk?.total_gb?.toFixed(1)}GB
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${
                    health.system.disk?.percent > 85 ? 'bg-red-500' :
                    health.system.disk?.percent > 70 ? 'bg-orange-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${health.system.disk?.percent || 0}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Services Status */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center text-base">
            <Activity className="w-5 h-5 mr-2" />
            Servis Durumları
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {Object.entries(health.services).map(([key, service]) => (
              <div key={key} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                <div className="flex items-center space-x-2">
                  <div className={`w-2 h-2 rounded-full ${getStatusColor(service.status)}`} />
                  <span className="text-sm font-medium">
                    {key.toUpperCase().replace('_', ' ')}
                  </span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-gray-500">
                    {service.response_time}ms
                  </span>
                  <Badge variant="outline" className="text-xs">
                    {service.uptime}%
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* API Metrics */}
      {metrics && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center text-base">
              <Zap className="w-5 h-5 mr-2" />
              API Metrikleri (Son 1 Saat)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              <div className="text-center p-3 bg-blue-50 rounded-lg">
                <div className="text-xl font-bold text-blue-600">
                  {metrics.summary.avg_response_time}ms
                </div>
                <div className="text-xs text-gray-600">Ort. Yanıt Süresi</div>
              </div>
              <div className="text-center p-3 bg-green-50 rounded-lg">
                <div className="text-xl font-bold text-green-600">
                  {metrics.summary.uptime_percentage}%
                </div>
                <div className="text-xs text-gray-600">Uptime</div>
              </div>
              <div className="text-center p-3 bg-purple-50 rounded-lg">
                <div className="text-xl font-bold text-purple-600">
                  {(metrics.summary.total_requests / 1000).toFixed(1)}K
                </div>
                <div className="text-xs text-gray-600">Toplam İstek</div>
              </div>
              <div className="text-center p-3 bg-orange-50 rounded-lg">
                <div className="text-xl font-bold text-orange-600">
                  {metrics.summary.avg_error_rate}%
                </div>
                <div className="text-xs text-gray-600">Hata Oranı</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Alert Thresholds */}
      {thresholds && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center text-base">
              <AlertTriangle className="w-5 h-5 mr-2" />
              Uyarı Eşikleri
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 text-xs">
              {Object.entries(thresholds.thresholds).slice(0, 4).map(([key, threshold]) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="font-medium">{key.replace('_', ' ').toUpperCase()}</span>
                  <div className="flex items-center space-x-2">
                    <Badge className={getStatusColor(
                      getMetricStatus(threshold.current, threshold.warning, threshold.critical)
                    )}>
                      {threshold.current}
                    </Badge>
                    <span className="text-gray-500">
                      / {threshold.warning} / {threshold.critical}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default AdvancedMonitoring;
