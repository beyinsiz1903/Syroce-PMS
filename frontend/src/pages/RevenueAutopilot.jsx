import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import MaybeLayout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Zap, Play, CheckCircle2, AlertCircle, Settings, Shield, Clock, RotateCw, Cpu, Check, FileText } from 'lucide-react';
import { toast } from 'sonner';
import AITabs from '@/components/AITabs';

const RevenueAutopilot = ({ user, tenant, onLogout, embedded }) => {
  const [autopilotMode, setAutopilotMode] = useState('supervised');
  const [lastLogs, setLastLogs] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      const response = await axios.get('/rms/autopilot/status');
      if (response.data) {
        setAutopilotMode(response.data.current_mode || 'supervised');
        setLastLogs(response.data.recent_actions || []);
      }
    } catch (error) {
      console.error('Autopilot durumu alınamadı');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const changeMode = async (newMode) => {
    try {
      await axios.post('/rms/autopilot/configure', { mode: newMode });
      setAutopilotMode(newMode);
      toast.success(`Autopilot modu "${newMode}" olarak güncellendi.`);
    } catch (error) {
      toast.error('Mod güncellenemedi.');
    }
  };

  const triggerRun = async () => {
    setIsRunning(true);
    toast.info('Optimizasyon döngüsü başlatılıyor...');
    try {
      const response = await axios.post('/rms/autopilot/trigger');
      toast.success('Döngü tamamlandı. ' + response.data.summary);
      fetchStatus();
    } catch (error) {
      toast.error('Döngü çalıştırılamadı.');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="ai_revenue_autopilot">
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
        
        <AITabs />

        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-50 text-blue-600 rounded-lg">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-slate-900">Revenue Autopilot</h1>
              <p className="text-sm text-slate-500">Tam otomatik revenue management ve fiyatlandırma motoru</p>
            </div>
          </div>
          
          <Button 
            onClick={triggerRun} 
            disabled={isRunning || loading}
            className="bg-slate-900 hover:bg-slate-800 text-white shadow-sm h-9 px-4 text-xs"
          >
            {isRunning ? (
              <RotateCw className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Play className="w-4 h-4 mr-2" />
            )}
            {isRunning ? 'Çalışıyor...' : 'Manuel Tetikle'}
          </Button>
        </div>

        {/* Current Status Banner */}
        <div className="bg-slate-900 rounded-xl overflow-hidden text-white shadow-md">
          <div className="px-6 py-5 flex items-center justify-between bg-slate-800/50">
            <div className="flex items-center gap-4">
              <div className="p-2.5 bg-slate-700/50 rounded-lg border border-slate-600">
                <Zap className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-0.5">Aktif Sistem Modu</p>
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-bold capitalize tracking-tight">{autopilotMode}</h2>
                  <span className="px-2 py-0.5 bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 text-[10px] rounded uppercase font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    Aktif
                  </span>
                </div>
              </div>
            </div>
            <div className="hidden md:block text-right">
              <p className="text-xs text-slate-400 mb-1 flex items-center justify-end gap-1">
                <Clock className="w-3 h-3" />
                Son Optimizasyon
              </p>
              <p className="text-sm font-medium text-slate-200">
                {lastLogs.length > 0 ? new Date(lastLogs[0].timestamp).toLocaleString('tr-TR') : 'Henüz çalışmadı'}
              </p>
            </div>
          </div>
        </div>

        {/* Mode Selector */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div 
            onClick={() => changeMode('full_auto')}
            className={`cursor-pointer border rounded-xl p-5 transition-all ${
              autopilotMode === 'full_auto' 
                ? 'bg-blue-50 border-blue-200 ring-1 ring-blue-500' 
                : 'bg-white border-slate-200 hover:border-slate-300'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className={`p-2 rounded-lg ${autopilotMode === 'full_auto' ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-600'}`}>
                <Zap className="w-4 h-4" />
              </div>
              {autopilotMode === 'full_auto' && <Check className="w-4 h-4 text-blue-600" />}
            </div>
            <h3 className="font-semibold text-slate-900 text-sm mb-1">Full Auto</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              Kurallar doğrudan OTA ve kanallara otomatik gönderilir.
            </p>
            <div className={`text-xs font-semibold ${autopilotMode === 'full_auto' ? 'text-blue-600' : 'text-slate-400'}`}>
              {autopilotMode === 'full_auto' ? 'Aktif Mod' : 'Seçmek İçin Tıklayın'}
            </div>
          </div>

          <div 
            onClick={() => changeMode('supervised')}
            className={`cursor-pointer border rounded-xl p-5 transition-all ${
              autopilotMode === 'supervised' 
                ? 'bg-blue-50 border-blue-200 ring-1 ring-blue-500' 
                : 'bg-white border-slate-200 hover:border-slate-300'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className={`p-2 rounded-lg ${autopilotMode === 'supervised' ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-600'}`}>
                <Settings className="w-4 h-4" />
              </div>
              {autopilotMode === 'supervised' && <Check className="w-4 h-4 text-blue-600" />}
            </div>
            <h3 className="font-semibold text-slate-900 text-sm mb-1">Supervised</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              Değişiklikler yayınlanmadan önce sizin onayınızı bekler.
            </p>
            <div className={`text-xs font-semibold ${autopilotMode === 'supervised' ? 'text-blue-600' : 'text-slate-400'}`}>
              {autopilotMode === 'supervised' ? 'Aktif Mod' : 'Seçmek İçin Tıklayın'}
            </div>
          </div>

          <div 
            onClick={() => changeMode('advisory')}
            className={`cursor-pointer border rounded-xl p-5 transition-all ${
              autopilotMode === 'advisory' 
                ? 'bg-blue-50 border-blue-200 ring-1 ring-blue-500' 
                : 'bg-white border-slate-200 hover:border-slate-300'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className={`p-2 rounded-lg ${autopilotMode === 'advisory' ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-600'}`}>
                <Shield className="w-4 h-4" />
              </div>
              {autopilotMode === 'advisory' && <Check className="w-4 h-4 text-blue-600" />}
            </div>
            <h3 className="font-semibold text-slate-900 text-sm mb-1">Advisory</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              Sadece rapor ve öneri sunar. İşlem yapmaz (Pasif Mod).
            </p>
            <div className={`text-xs font-semibold ${autopilotMode === 'advisory' ? 'text-blue-600' : 'text-slate-400'}`}>
              {autopilotMode === 'advisory' ? 'Aktif Mod' : 'Seçmek İçin Tıklayın'}
            </div>
          </div>
        </div>

        {/* Activity Logs */}
        <Card className="shadow-sm border-slate-200">
          <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
            <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
              <FileText className="w-4 h-4 text-slate-500" />
              Sistem Logları
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loading && lastLogs.length === 0 ? (
              <div className="py-12 text-center text-slate-400 text-sm">Loglar yükleniyor...</div>
            ) : lastLogs.length === 0 ? (
              <div className="py-12 flex flex-col items-center justify-center text-slate-400 text-sm">
                <AlertCircle className="w-6 h-6 mb-2 text-slate-300" />
                <p>Henüz sistem logu bulunmuyor.</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100 max-h-[400px] overflow-y-auto">
                {lastLogs.map((log, idx) => (
                  <div key={idx} className="p-4 hover:bg-slate-50 transition-colors flex items-start gap-4">
                    <div className={`mt-0.5 p-1.5 rounded-full shrink-0 ${
                      log.status === 'success' ? 'bg-emerald-100 text-emerald-600' :
                      log.status === 'warning' ? 'bg-amber-100 text-amber-600' :
                      'bg-slate-100 text-slate-600'
                    }`}>
                      {log.status === 'success' ? <CheckCircle2 className="w-3.5 h-3.5" /> :
                       log.status === 'warning' ? <AlertCircle className="w-3.5 h-3.5" /> :
                       <Info className="w-3.5 h-3.5" />}
                    </div>
                    <div>
                      <p className="text-sm text-slate-700">{log.message}</p>
                      <p className="text-[10px] text-slate-400 mt-1 font-mono">
                        {new Date(log.timestamp).toLocaleString('tr-TR')}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

      </div>
    </MaybeLayout>
  );
};

export default RevenueAutopilot;