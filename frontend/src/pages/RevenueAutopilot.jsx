import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import MaybeLayout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Zap, Settings, PlayCircle, CheckCircle, Clock, Activity, Cpu, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const RevenueAutopilot = ({ user, tenant, onLogout, embedded }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [lastCycle, setLastCycle] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const response = await axios.get('/autopilot/status');
      setStatus(response.data);
    } catch (error) {
      console.error('Autopilot status yüklenemedi');
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

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
      toast.success(`Autopilot modu güncellendi: ${mode}`);
      loadStatus();
    } catch (error) {
      toast.error(t('messages.error.generic'));
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="ai_revenue_autopilot">
      <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-xl shadow-lg shadow-indigo-200">
              <Cpu className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">Revenue Autopilot</h1>
              <p className="text-slate-500 mt-1">Tam otomatik revenue management ve fiyatlandırma motoru</p>
            </div>
          </div>
          <Button 
            variant="outline" 
            className="border-indigo-200 text-indigo-700 hover:bg-indigo-50 hover:border-indigo-300"
            onClick={() => navigate('/revenue-autopilot/monitor')}
          >
            <Activity className="w-4 h-4 mr-2" /> İzleme Paneli
          </Button>
        </div>

        {/* Status Highlight */}
        {status && (
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 to-indigo-950 p-8 shadow-2xl">
            <div className="absolute right-0 top-0 opacity-10 pointer-events-none transform translate-x-1/4 -translate-y-1/4">
              <Cpu className="w-96 h-96" />
            </div>
            <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-6">
              <div className="flex items-center gap-4">
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-indigo-500/20 ring-1 ring-indigo-400/30">
                  <div className="absolute h-full w-full animate-ping rounded-full bg-indigo-400/20 opacity-75"></div>
                  <Zap className="h-8 w-8 text-indigo-300" />
                </div>
                <div>
                  <p className="text-indigo-200 font-medium tracking-wide text-sm uppercase">Sistem Durumu</p>
                  <div className="flex items-center gap-3 mt-1">
                    <h2 className="text-3xl font-bold text-white capitalize">{status.mode.replace('_', ' ')}</h2>
                    <Badge className="bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-3 py-1">
                      <CheckCircle className="w-3.5 h-3.5 mr-1.5" />
                      Aktif
                    </Badge>
                  </div>
                </div>
              </div>
              
              <div className="bg-white/10 backdrop-blur-md rounded-xl p-5 border border-white/10 min-w-[250px]">
                <div className="flex items-center gap-2 text-indigo-200 mb-2">
                  <Clock className="w-4 h-4" />
                  <span className="text-sm font-medium">Son Optimizasyon Döngüsü</span>
                </div>
                <p className="text-lg font-bold text-white">
                  {new Date(status.last_cycle).toLocaleString('tr-TR', {
                    day: '2-digit', month: 'short', year: 'numeric',
                    hour: '2-digit', minute: '2-digit', second: '2-digit'
                  })}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Mode Selection */}
        <div>
          <h3 className="text-xl font-bold text-slate-800 mb-4">Çalışma Modunu Seçin</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card 
              className={`cursor-pointer transition-all duration-300 border-2 overflow-hidden relative group ${
                status?.mode === 'full_auto' 
                  ? 'border-indigo-500 shadow-lg shadow-indigo-200/50' 
                  : 'border-transparent shadow-md hover:border-indigo-200'
              }`}
              onClick={() => setMode('full_auto')}
            >
              {status?.mode === 'full_auto' && (
                <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-indigo-500 to-purple-500"></div>
              )}
              <CardContent className="p-8 text-center flex flex-col items-center">
                <div className={`p-4 rounded-full mb-5 transition-colors ${
                  status?.mode === 'full_auto' ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-500 group-hover:bg-indigo-50 group-hover:text-indigo-400'
                }`}>
                  <Zap className="w-8 h-8" />
                </div>
                <h4 className={`text-xl font-bold mb-2 ${status?.mode === 'full_auto' ? 'text-indigo-900' : 'text-slate-700'}`}>Full Auto</h4>
                <p className="text-sm text-slate-500 leading-relaxed">
                  Kural motoru piyasayı analiz eder ve fiyatları hiçbir onay beklemeden tüm kanallara otomatik yollar.
                </p>
                {status?.mode === 'full_auto' && (
                  <Badge className="mt-6 bg-indigo-500 hover:bg-indigo-600 px-4 py-1.5 shadow-sm">Aktif Mod</Badge>
                )}
              </CardContent>
            </Card>

            <Card 
              className={`cursor-pointer transition-all duration-300 border-2 overflow-hidden relative group ${
                status?.mode === 'supervised' 
                  ? 'border-blue-500 shadow-lg shadow-blue-200/50' 
                  : 'border-transparent shadow-md hover:border-blue-200'
              }`}
              onClick={() => setMode('supervised')}
            >
              {status?.mode === 'supervised' && (
                <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-blue-500 to-cyan-500"></div>
              )}
              <CardContent className="p-8 text-center flex flex-col items-center">
                <div className={`p-4 rounded-full mb-5 transition-colors ${
                  status?.mode === 'supervised' ? 'bg-blue-100 text-blue-600' : 'bg-slate-100 text-slate-500 group-hover:bg-blue-50 group-hover:text-blue-400'
                }`}>
                  <Settings className="w-8 h-8" />
                </div>
                <h4 className={`text-xl font-bold mb-2 ${status?.mode === 'supervised' ? 'text-blue-900' : 'text-slate-700'}`}>Supervised</h4>
                <p className="text-sm text-slate-500 leading-relaxed">
                  Kural motoru fiyatları optimize eder, ancak değişiklikler yayınlanmadan önce sizin onayınızı bekler.
                </p>
                {status?.mode === 'supervised' && (
                  <Badge className="mt-6 bg-blue-500 hover:bg-blue-600 px-4 py-1.5 shadow-sm">Aktif Mod</Badge>
                )}
              </CardContent>
            </Card>

            <Card 
              className={`cursor-pointer transition-all duration-300 border-2 overflow-hidden relative group ${
                status?.mode === 'advisory' 
                  ? 'border-emerald-500 shadow-lg shadow-emerald-200/50' 
                  : 'border-transparent shadow-md hover:border-emerald-200'
              }`}
              onClick={() => setMode('advisory')}
            >
              {status?.mode === 'advisory' && (
                <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-emerald-500 to-teal-500"></div>
              )}
              <CardContent className="p-8 text-center flex flex-col items-center">
                <div className={`p-4 rounded-full mb-5 transition-colors ${
                  status?.mode === 'advisory' ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-500 group-hover:bg-emerald-50 group-hover:text-emerald-400'
                }`}>
                  <ShieldCheck className="w-8 h-8" />
                </div>
                <h4 className={`text-xl font-bold mb-2 ${status?.mode === 'advisory' ? 'text-emerald-900' : 'text-slate-700'}`}>Advisory</h4>
                <p className="text-sm text-slate-500 leading-relaxed">
                  Sistem sadece öneriler sunar, otomatik fiyat taslağı dahi oluşturmaz. Pasif dinleme modudur.
                </p>
                {status?.mode === 'advisory' && (
                  <Badge className="mt-6 bg-emerald-500 hover:bg-emerald-600 px-4 py-1.5 shadow-sm">Aktif Mod</Badge>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Manual Run */}
          <Card className="lg:col-span-1 border-none shadow-lg shadow-slate-200/50 h-fit">
            <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-5">
              <CardTitle className="text-lg font-bold text-slate-800">Manuel Tetikleme</CardTitle>
              <CardDescription>Zamanlanmış görevi beklemeden hemen analiz başlat</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              <Button 
                className="w-full h-14 text-base font-bold bg-indigo-600 hover:bg-indigo-700 shadow-md shadow-indigo-200 transition-all group" 
                onClick={runCycle} 
                disabled={loading}
              >
                {loading ? (
                  <>
                    <div className="animate-spin w-5 h-5 border-2 border-white border-t-transparent rounded-full mr-3"></div>
                    Optimizasyon Çalışıyor...
                  </>
                ) : (
                  <>
                    <PlayCircle className="w-5 h-5 mr-2 group-hover:scale-110 transition-transform" />
                    Optimizasyon Döngüsünü Başlat
                  </>
                )}
              </Button>
              <p className="text-xs text-slate-400 mt-4 text-center">
                Not: Bu işlem veritabanı boyutuna göre 1-2 dakika sürebilir.
              </p>
            </CardContent>
          </Card>

          {/* Last Cycle Results */}
          <Card className="lg:col-span-2 border-none shadow-lg shadow-slate-200/50">
            <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-5">
              <CardTitle className="text-lg font-bold text-slate-800">Son Döngü Aktivitesi</CardTitle>
              <CardDescription>Son yapılan analizde alınan aksiyonların logları</CardDescription>
            </CardHeader>
            <CardContent className="p-6">
              {lastCycle && lastCycle.actions && lastCycle.actions.length > 0 ? (
                <div className="relative border-l-2 border-slate-100 ml-3 space-y-8 pb-4">
                  {lastCycle.actions.map((action, idx) => (
                    <div key={idx} className="relative pl-6">
                      <div className="absolute -left-[9px] top-1 w-4 h-4 rounded-full bg-white border-2 border-indigo-500 shadow-sm shadow-indigo-200"></div>
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-sm font-bold text-slate-800">{action.action}</p>
                          <span className="text-xs font-medium text-slate-400 bg-slate-50 px-2 py-0.5 rounded-full border border-slate-100">
                            {action.time}
                          </span>
                        </div>
                        {action.status && (
                          <div className="mt-2 bg-slate-50 p-3 rounded-lg border border-slate-100">
                            <p className="text-sm text-slate-600">{action.status}</p>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="py-12 flex flex-col items-center justify-center text-slate-400">
                  <div className="w-16 h-16 rounded-full bg-slate-50 flex items-center justify-center mb-4">
                    <CheckCircle className="w-8 h-8 text-slate-300" />
                  </div>
                  <h3 className="text-base font-semibold text-slate-700">Aktivite Yok</h3>
                  <p className="text-sm mt-1 text-center max-w-md">Henüz manuel olarak tetiklenmiş bir optimizasyon logu bulunmuyor. Sol taraftaki butonu kullanarak bir döngü başlatabilirsiniz.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        
      </div>
    </MaybeLayout>
  );
};

export default RevenueAutopilot;