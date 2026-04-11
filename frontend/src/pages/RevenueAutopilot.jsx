import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Home, Zap, Settings, PlayCircle, CheckCircle, Clock } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const RevenueAutopilot = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [lastCycle, setLastCycle] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      const response = await axios.get('/autopilot/status');
      setStatus(response.data);
    } catch (error) {
      console.error('Autopilot status yüklenemedi');
    }
  };

  const runCycle = async () => {
    setLoading(true);
    try {
      const response = await axios.post('/autopilot/run-cycle');
      setLastCycle(response.data);
      toast.success(t('messages.success.updated'));
    } catch (error) {
      toast.error(t('messages.error.generic'));
    } finally {
      setLoading(false);
    }
  };

  const setMode = async (mode) => {
    try {
      await axios.post('/autopilot/set-mode', { mode });
      toast.success(`Autopilot mode: ${mode}`);
      loadStatus();
    } catch (error) {
      toast.error(t('messages.error.generic'));
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon" onClick={() => navigate('/')} className="hover:bg-purple-50">
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">⚡ Revenue Autopilot</h1>
            <p className="text-gray-600">Tam otomatik revenue management - Sıfır müdahale</p>
          </div>
        </div>
      </div>

      {/* Status Card */}
      {status && (
        <Card className="mb-6 bg-gradient-to-r from-purple-50 to-blue-50 border-2 border-purple-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-6 h-6 text-purple-600" />
              Autopilot Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-gray-600">Mode</p>
                <p className="text-2xl font-bold capitalize">{status.mode}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Status</p>
                <p className="text-2xl font-bold text-green-600">Active</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Last Cycle</p>
                <p className="text-sm font-semibold">{new Date(status.last_cycle).toLocaleString('tr-TR')}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Mode Selection */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <Card className="cursor-pointer hover:shadow-lg" onClick={() => setMode('full_auto')}>
          <CardContent className="pt-6 text-center">
            <Zap className="w-12 h-12 text-purple-600 mx-auto mb-2" />
            <p className="font-bold">Full Auto</p>
            <p className="text-xs text-gray-600 mt-2">AI her şeyi yapar</p>
            {status?.mode === 'full_auto' && <Badge className="mt-2 bg-purple-600">Active</Badge>}
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg" onClick={() => setMode('supervised')}>
          <CardContent className="pt-6 text-center">
            <Settings className="w-12 h-12 text-blue-600 mx-auto mb-2" />
            <p className="font-bold">Supervised</p>
            <p className="text-xs text-gray-600 mt-2">AI önerir, siz onayla</p>
            {status?.mode === 'supervised' && <Badge className="mt-2 bg-blue-600">Active</Badge>}
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg" onClick={() => setMode('advisory')}>
          <CardContent className="pt-6 text-center">
            <CheckCircle className="w-12 h-12 text-green-600 mx-auto mb-2" />
            <p className="font-bold">Advisory</p>
            <p className="text-xs text-gray-600 mt-2">Sadece öneri</p>
            {status?.mode === 'advisory' && <Badge className="mt-2 bg-green-600">Active</Badge>}
          </CardContent>
        </Card>
      </div>

      {/* Manual Run */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Manuel Optimization Cycle</CardTitle>
        </CardHeader>
        <CardContent>
          <Button className="w-full bg-purple-600 hover:bg-purple-700" onClick={runCycle} disabled={loading}>
            <PlayCircle className="w-5 h-5 mr-2" />
            {loading ? 'Çalıştırılıyor...' : 'Optimization Cycle Başlat'}
          </Button>
        </CardContent>
      </Card>

      {/* Last Cycle Results */}
      {lastCycle && (
        <Card>
          <CardHeader>
            <CardTitle>Son Cycle Sonuçları</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {lastCycle.actions?.map((action, idx) => (
                <div key={idx} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <Clock className="w-5 h-5 text-blue-600" />
                  <div className="flex-1">
                    <p className="font-semibold">{action.time} - {action.action}</p>
                    {action.status && (
                      <p className="text-xs text-gray-600">{action.status}</p>
                    )}
                  </div>
                  <CheckCircle className="w-5 h-5 text-green-600" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default RevenueAutopilot;