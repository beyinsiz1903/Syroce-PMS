import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Wifi, Activity, Zap, CheckCircle, XCircle, Clock, TrendingUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const NetworkTestTools = ({ user }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [testing, setTesting] = useState(false);
  const [pingResult, setPingResult] = useState(null);
  const [healthResult, setHealthResult] = useState(null);
  const [pingTarget, setPingTarget] = useState('8.8.8.8');

  const runPingTest = async () => {
    try {
      setTesting(true);
      const res = await axios.post('/network/ping', {
        target: pingTarget,
        count: 4
      });
      setPingResult(res.data);
      toast.success('Ping testi tamamlandı');
    } catch (error) {
      console.error('Ping test failed:', error);
      toast.error('Ping testi başarısız');
    } finally {
      setTesting(false);
    }
  };

  const runHealthCheck = async () => {
    try {
      setTesting(true);
      const res = await axios.get('/system/health');
      setHealthResult(res.data);
      toast.success('Sağlık kontrolü tamamlandı');
    } catch (error) {
      console.error('Health check failed:', error);
      toast.error('Sağlık kontrolü başarısız');
    } finally {
      setTesting(false);
    }
  };

  const getQualityColor = (quality) => {
    switch(quality) {
      case 'excellent': return 'bg-green-500';
      case 'good': return 'bg-blue-500';
      case 'fair': return 'bg-orange-500';
      case 'poor': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const getStatusColor = (status) => {
    switch(status) {
      case 'healthy': return 'text-green-600 bg-green-50 border-green-200';
      case 'degraded': return 'text-orange-600 bg-orange-50 border-orange-200';
      case 'critical': return 'text-red-600 bg-red-50 border-red-200';
      default: return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 pb-20">
      {/* Header */}
      <div className="bg-gradient-to-r from-teal-600 to-cyan-600 text-white p-4 sticky top-0 z-50 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(-1)}
              className="text-white hover:bg-white/20 p-2"
            >
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-xl font-bold">Ağ Test Araçları</h1>
              <p className="text-xs text-teal-100">Network Diagnostics</p>
            </div>
          </div>
          <Wifi className="w-6 h-6" />
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Ping Test */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-teal-600" />
              Ping Testi
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input
                placeholder="Hedef IP veya Domain"
                value={pingTarget}
                onChange={(e) => setPingTarget(e.target.value)}
              />
              <Button onClick={runPingTest} disabled={testing} className="bg-teal-600 hover:bg-teal-700">
                {testing ? 'Test Ediliyor...' : 'Ping Testi Yap'}
              </Button>
            </div>

            {pingResult && (
              <div className="space-y-3 mt-4">
                <div className="flex items-center justify-between p-3 bg-gray-50 rounded">
                  <span className="text-sm font-medium">Bağlantı Kalitesi</span>
                  <Badge className={`${getQualityColor(pingResult.quality)} text-white`}>
                    {pingResult.quality === 'excellent' ? 'Mükemmel' :
                     pingResult.quality === 'good' ? 'İyi' :
                     pingResult.quality === 'fair' ? 'Orta' :
                     pingResult.quality === 'poor' ? 'Zayıf' : 'Bağlantı Yok'}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 bg-blue-50 rounded">
                    <div className="text-xs text-gray-600">Ortalama Gecikme</div>
                    <div className="text-2xl font-bold text-blue-600">{pingResult.latency?.avg_ms}ms</div>
                  </div>
                  <div className="p-3 bg-green-50 rounded">
                    <div className="text-xs text-gray-600">Paket Kaybı</div>
                    <div className="text-2xl font-bold text-green-600">{pingResult.packet_loss_percent}%</div>
                  </div>
                  <div className="p-3 bg-purple-50 rounded">
                    <div className="text-xs text-gray-600">En Düşük</div>
                    <div className="text-lg font-bold text-purple-600">{pingResult.latency?.min_ms}ms</div>
                  </div>
                  <div className="p-3 bg-orange-50 rounded">
                    <div className="text-xs text-gray-600">En Yüksek</div>
                    <div className="text-lg font-bold text-orange-600">{pingResult.latency?.max_ms}ms</div>
                  </div>
                </div>

                <div className="p-3 bg-gray-50 rounded">
                  <div className="text-xs text-gray-600 mb-2">Ping Süreleri</div>
                  <div className="flex flex-wrap gap-2">
                    {pingResult.ping_times?.map((time, idx) => (
                      <Badge key={idx} variant="outline">{time}ms</Badge>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Health Check */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-yellow-600" />
              Servis Sağlık Kontrolü
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Button onClick={runHealthCheck} disabled={testing} className="w-full bg-yellow-600 hover:bg-yellow-700">
              {testing ? 'Kontrol Ediliyor...' : 'Sağlık Kontrolü Yap'}
            </Button>

            {healthResult && (
              <div className="space-y-3 mt-4">
                <div className={`p-3 rounded border ${getStatusColor(healthResult.overall_status)}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">Genel Durum</span>
                    <Badge className={getStatusColor(healthResult.overall_status)}>
                      {healthResult.overall_status === 'healthy' ? 'Sağlıklı' :
                       healthResult.overall_status === 'degraded' ? 'Dikkat' : 'Kritik'}
                    </Badge>
                  </div>
                  <div className="text-sm mt-2">
                    {healthResult.healthy_count}/{healthResult.total_checks} servis sağlıklı
                  </div>
                </div>

                <div className="space-y-2">
                  {healthResult.checks?.map((check, idx) => (
                    <div key={idx} className="p-3 bg-gray-50 rounded flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {check.status === 'healthy' ? 
                          <CheckCircle className="w-4 h-4 text-green-600" /> :
                          <XCircle className="w-4 h-4 text-red-600" />
                        }
                        <div>
                          <div className="font-medium text-sm">{check.service}</div>
                          <div className="text-xs text-gray-500">{check.message}</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-bold text-gray-700">{check.latency_ms}ms</div>
                        {check.record_count !== undefined && (
                          <div className="text-xs text-gray-500">{check.record_count} kayıt</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Tips */}
        <Card className="bg-cyan-50 border-cyan-200">
          <CardContent className="p-4">
            <div className="flex items-start gap-2">
              <TrendingUp className="w-5 h-5 text-cyan-600 mt-1" />
              <div>
                <div className="font-semibold text-sm text-cyan-900">Performans İpuçları</div>
                <ul className="text-xs text-cyan-800 mt-2 space-y-1">
                  <li>• Ping süresi &lt;50ms = Mükemmel bağlantı</li>
                  <li>• Paket kaybı %0 = Stabil ağ</li>
                  <li>• Tüm servisler sağlıklı = Sistem hazır</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default NetworkTestTools;