import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  ArrowLeft, 
  Shield, 
  Activity, 
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  Server,
  Database,
  RefreshCw,
  Wifi,
  WifiOff,
  Home
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MobileSecurity = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [systemStatus, setSystemStatus] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [securityAlerts, setSecurityAlerts] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadData();
    // Auto refresh every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      
      const [statusRes, connectionRes, alertsRes, notifRes] = await Promise.all([
        axios.get('/security/mobile/system-status'),
        axios.get('/security/mobile/connection-status'),
        axios.get('/security/mobile/security-alerts'),
        axios.get('/notifications/mobile/security')
      ]);

      setSystemStatus(statusRes.data);
      setConnectionStatus(connectionRes.data);
      setSecurityAlerts(alertsRes.data.alerts || []);
      setNotifications(notifRes.data.notifications || []);
    } catch (error) {
      console.error('Failed to load security data:', error);
      toast.error('Veri yüklenemedi');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const getStatusIcon = (status) => {
    switch(status) {
      case 'operational':
      case 'healthy':
      case 'connected':
        return <CheckCircle className="w-5 h-5 text-green-600" />;
      case 'degraded':
      case 'idle':
        return <AlertTriangle className="w-5 h-5 text-yellow-600" />;
      case 'critical':
      case 'disconnected':
        return <XCircle className="w-5 h-5 text-red-600" />;
      default:
        return <Clock className="w-5 h-5 text-gray-600" />;
    }
  };

  const getStatusColor = (status) => {
    switch(status) {
      case 'operational':
      case 'healthy':
      case 'connected':
        return 'bg-green-100 text-green-700 border-green-300';
      case 'degraded':
      case 'idle':
        return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'critical':
      case 'disconnected':
        return 'bg-red-100 text-red-700 border-red-300';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  const getSeverityColor = (severity) => {
    switch(severity) {
      case 'high':
        return 'bg-red-500';
      case 'medium':
        return 'bg-yellow-500';
      case 'low':
        return 'bg-blue-500';
      default:
        return 'bg-gray-500';
    }
  };

  if (loading && !systemStatus) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-gray-600 mx-auto mb-2" />
          <p className="text-gray-600">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-gray-900 to-gray-700 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/mobile')}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Güvenlik & IT</h1>
              <p className="text-xs text-gray-300">Security & IT Dashboard</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            {notifications.length > 0 && (
              <Badge className="bg-red-500 text-white">{notifications.length}</Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/')}
              className="text-white hover:bg-white/20 p-2"
              title="Ana Sayfa"
            >
              <Home className="w-5 h-5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="text-white hover:bg-white/20 p-2"
            >
              <RefreshCw className={`w-5 h-5 ${refreshing ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Quick Access Tools */}
        <div className="grid grid-cols-2 gap-3">
          <Button 
            className="h-20 flex flex-col items-center justify-center bg-gradient-to-br from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white"
            onClick={() => navigate('/system/performance')}
          >
            <Activity className="w-6 h-6 mb-1" />
            <span className="text-xs font-semibold">Performans</span>
          </Button>
          
          <Button 
            className="h-20 flex flex-col items-center justify-center bg-gradient-to-br from-gray-700 to-gray-900 hover:from-gray-800 hover:to-black text-white"
            onClick={() => navigate('/mobile/logs')}
          >
            <Server className="w-6 h-6 mb-1" />
            <span className="text-xs font-semibold">Loglar</span>
          </Button>
          
          <Button 
            className="h-20 flex flex-col items-center justify-center bg-gradient-to-br from-teal-600 to-cyan-600 hover:from-teal-700 hover:to-cyan-700 text-white"
            onClick={() => navigate('/system/network')}
          >
            <Wifi className="w-6 h-6 mb-1" />
            <span className="text-xs font-semibold">Ağ Testi</span>
          </Button>
          
          <Button 
            className="h-20 flex flex-col items-center justify-center bg-gradient-to-br from-yellow-600 to-amber-600 hover:from-yellow-700 hover:to-amber-700 text-white"
            onClick={() => window.location.reload()}
          >
            <RefreshCw className="w-6 h-6 mb-1" />
            <span className="text-xs font-semibold">{t("common.refresh")}</span>
          </Button>
        </div>

        {/* Overall Health Score */}
        {systemStatus && (
          <Card className={`border-2 ${
            systemStatus.overall_status === 'healthy' ? 'bg-gradient-to-r from-green-50 to-emerald-50 border-green-300' :
            systemStatus.overall_status === 'degraded' ? 'bg-gradient-to-r from-yellow-50 to-amber-50 border-yellow-300' :
            'bg-gradient-to-r from-red-50 to-rose-50 border-red-300'
          }`}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  {getStatusIcon(systemStatus.overall_status)}
                  <div>
                    <p className="text-sm font-medium text-gray-600">Sistem Durumu</p>
                    <p className="text-2xl font-bold text-gray-900 capitalize">
                      {systemStatus.overall_status}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-bold text-gray-900">
                    {systemStatus.health_score?.toFixed(0)}%
                  </p>
                  <p className="text-xs text-gray-600">Sağlık Skoru</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Notifications */}
        {notifications.length > 0 && (
          <Card className="bg-gradient-to-r from-red-50 to-amber-50 border-red-200">
            <CardContent className="p-3">
              <div className="flex items-start space-x-2">
                <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-gray-900">Bildirimler ({notifications.length})</p>
                  {notifications.slice(0, 3).map((notif, idx) => (
                    <p key={idx} className="text-xs text-gray-700 mt-1">
                      • {notif.title}: {notif.message}
                    </p>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* System Components Status */}
        {systemStatus?.components && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <Server className="w-5 h-5 mr-2 text-blue-600" />
                Sistem Bileşenleri
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(systemStatus.components).map(([component, status]) => (
                <div key={component} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                  <div className="flex items-center space-x-3">
                    {getStatusIcon(status)}
                    <div>
                      <p className="font-medium text-gray-900 capitalize">
                        {component.replace('_', ' ')}
                      </p>
                    </div>
                  </div>
                  <Badge className={getStatusColor(status)}>
                    {status}
                  </Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Connection Status */}
        {connectionStatus?.connections && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <Activity className="w-5 h-5 mr-2 text-indigo-600" />
                Bağlantı Durumu
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(connectionStatus.connections).map(([service, conn]) => (
                <div key={service} className={`p-3 rounded-lg border ${
                  conn.status === 'connected' ? 'bg-green-50 border-green-200' :
                  conn.status === 'idle' ? 'bg-yellow-50 border-yellow-200' :
                  'bg-red-50 border-red-200'
                }`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      {conn.status === 'connected' ? 
                        <Wifi className="w-4 h-4 text-green-600" /> : 
                        <WifiOff className="w-4 h-4 text-red-600" />
                      }
                      <p className="font-bold text-gray-900 capitalize">
                        {service.replace('_', ' ')}
                      </p>
                    </div>
                    <Badge className={getStatusColor(conn.status)}>
                      {conn.status}
                    </Badge>
                  </div>
                  {conn.last_activity && (
                    <p className="text-xs text-gray-600">
                      Son aktivite: {conn.minutes_since_activity} dk önce
                    </p>
                  )}
                  {conn.last_sync && (
                    <p className="text-xs text-gray-600">
                      Son senkronizasyon: {conn.minutes_since_sync} dk önce
                    </p>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Security Alerts */}
        {securityAlerts.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <Shield className="w-5 h-5 mr-2 text-red-600" />
                Güvenlik Uyarıları ({securityAlerts.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {securityAlerts.map((alert) => (
                <div key={alert.id} className="p-3 bg-red-50 rounded-lg border border-red-200">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <p className="font-bold text-gray-900">{alert.title}</p>
                      <p className="text-sm text-gray-700 mt-1">{alert.message}</p>
                    </div>
                    <Badge className={getSeverityColor(alert.severity)}>
                      {alert.severity}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500">
                    {new Date(alert.timestamp).toLocaleString('tr-TR')}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Recent System Errors */}
        {systemStatus?.recent_errors && systemStatus.recent_errors.length > 0 && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg flex items-center">
                <AlertTriangle className="w-5 h-5 mr-2 text-amber-600" />
                Son Sistem Hataları
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {systemStatus.recent_errors.slice(0, 5).map((error, idx) => (
                <div key={idx} className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                  <p className="font-medium text-gray-900">{error.component}</p>
                  <p className="text-sm text-gray-700 mt-1">{error.message}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {new Date(error.timestamp).toLocaleString('tr-TR')}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Info Banner */}
        <Card className="bg-gradient-to-r from-gray-50 to-slate-50">
          <CardContent className="p-4">
            <div className="flex items-start space-x-3">
              <div className="bg-gray-200 p-2 rounded-full">
                <Database className="w-5 h-5 text-gray-700" />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-gray-900 mb-1">Sistem İzleme</h4>
                <p className="text-sm text-gray-600">
                  Tüm sistemlerin sağlığı ve bağlantı durumu gerçek zamanlı olarak izleniyor.
                  Otomatik 30 saniyede bir güncellenir.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default MobileSecurity;