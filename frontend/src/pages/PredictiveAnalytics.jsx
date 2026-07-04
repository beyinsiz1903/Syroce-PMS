import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import MaybeLayout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Home, AlertTriangle, TrendingUp, Calendar, Target, CheckCircle, Lightbulb, Activity } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const PredictiveAnalytics = ({ user, tenant, onLogout, embedded }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [noShowPredictions, setNoShowPredictions] = useState([]);
  const [demandForecast, setDemandForecast] = useState([]);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [loading, setLoading] = useState(false);

  const loadPredictions = useCallback(async () => {
    try {
      const response = await axios.get(`/predictions/no-shows?target_date=${selectedDate}`);
      setNoShowPredictions(response.data.predictions || []);
    } catch (error) {
      console.error('Predictions yüklenemedi');
    }
  }, [selectedDate]);

  const loadDemandForecast = useCallback(async () => {
    try {
      const response = await axios.get('/predictions/demand-forecast?days=30');
      setDemandForecast(response.data.daily_forecast || []);
    } catch (error) {
      console.error('Demand forecast yüklenemedi');
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadPredictions(), loadDemandForecast()]).finally(() => setLoading(false));
  }, [loadPredictions, loadDemandForecast]);

  const RiskBadge = ({ level }) => {
    const colors = {
      high: 'bg-red-500/10 text-red-600 border-red-500/20 shadow-sm',
      medium: 'bg-amber-500/10 text-amber-600 border-amber-500/20 shadow-sm',
      low: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20 shadow-sm'
    };
    return (
      <Badge className={`${colors[level]} border px-2.5 py-0.5 rounded-full font-semibold`}>
        {level.toUpperCase()}
      </Badge>
    );
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="ai_revenue_autopilot">
      <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-200">
              <Activity className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">Tahmine Dayalı Analiz</h1>
              <p className="text-slate-500 mt-1">Yapay zeka destekli no-show riskleri ve talep öngörüleri</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-4 py-2 bg-white border border-slate-200 rounded-xl shadow-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
            />
          </div>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card className="border-none shadow-md overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-red-500/5 to-transparent z-0"></div>
            <CardContent className="p-6 relative z-10 flex flex-col items-center justify-center text-center">
              <div className="p-3 bg-red-100 text-red-600 rounded-full mb-4 group-hover:scale-110 transition-transform">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <p className="text-4xl font-black text-slate-800">{noShowPredictions.filter(p => p.risk_level === 'high').length}</p>
              <p className="text-sm font-medium text-slate-500 mt-1">Yüksek Risk No-show</p>
            </CardContent>
          </Card>
          
          <Card className="border-none shadow-md overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-amber-500/5 to-transparent z-0"></div>
            <CardContent className="p-6 relative z-10 flex flex-col items-center justify-center text-center">
              <div className="p-3 bg-amber-100 text-amber-600 rounded-full mb-4 group-hover:scale-110 transition-transform">
                <Target className="w-6 h-6" />
              </div>
              <p className="text-4xl font-black text-slate-800">{noShowPredictions.length}</p>
              <p className="text-sm font-medium text-slate-500 mt-1">Toplam Riskli Rezervasyon</p>
            </CardContent>
          </Card>

          <Card className="border-none shadow-md overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent z-0"></div>
            <CardContent className="p-6 relative z-10 flex flex-col items-center justify-center text-center">
              <div className="p-3 bg-blue-100 text-blue-600 rounded-full mb-4 group-hover:scale-110 transition-transform">
                <TrendingUp className="w-6 h-6" />
              </div>
              <p className="text-4xl font-black text-slate-800">
                {demandForecast.filter(d => d.demand_level === 'very_high').length}
              </p>
              <p className="text-sm font-medium text-slate-500 mt-1">Yüksek Talep Beklenen Gün</p>
            </CardContent>
          </Card>

          <Card className="border-none shadow-md overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent z-0"></div>
            <CardContent className="p-6 relative z-10 flex flex-col items-center justify-center text-center">
              <div className="p-3 bg-emerald-100 text-emerald-600 rounded-full mb-4 group-hover:scale-110 transition-transform">
                <Calendar className="w-6 h-6" />
              </div>
              <p className="text-4xl font-black text-slate-800">30</p>
              <p className="text-sm font-medium text-slate-500 mt-1">Günlük Projeksiyon</p>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* No-Show Predictions */}
          <Card className="lg:col-span-1 border-none shadow-lg shadow-slate-200/50">
            <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4">
              <CardTitle className="text-lg font-bold text-slate-800 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-500" />
                No-Show Riskleri
              </CardTitle>
              <CardDescription>Seçili tarih ({selectedDate}) için riskli rezervasyonlar</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="p-8 text-center text-slate-400">Analiz ediliyor...</div>
              ) : noShowPredictions.length === 0 ? (
                <div className="p-10 text-center flex flex-col items-center">
                  <div className="w-16 h-16 bg-emerald-50 rounded-full flex items-center justify-center mb-4">
                    <CheckCircle className="w-8 h-8 text-emerald-500" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-800">Risk Bulunmadı</h3>
                  <p className="text-slate-500 mt-1">Bugün için yüksek risk taşıyan no-show tahminlemesi yapılmadı.</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100 max-h-[500px] overflow-y-auto">
                  {noShowPredictions.map((pred, idx) => (
                    <div key={idx} className="p-5 hover:bg-slate-50 transition-colors relative overflow-hidden">
                      <div className={`absolute left-0 top-0 bottom-0 w-1 ${pred.risk_level === 'high' ? 'bg-red-500' : pred.risk_level === 'medium' ? 'bg-amber-500' : 'bg-emerald-500'}`}></div>
                      <div className="flex items-start justify-between mb-3 pl-2">
                        <div>
                          <p className="font-bold text-slate-800 font-mono">#{pred.booking_id.substring(0, 8).toUpperCase()}</p>
                          <p className="text-xs font-medium text-slate-500 mt-1 flex items-center gap-1">
                            Risk Skoru: <span className="text-slate-700">%{(pred.risk_score * 100).toFixed(0)}</span>
                          </p>
                        </div>
                        <RiskBadge level={pred.risk_level} />
                      </div>
                      <div className="mt-3 pl-2">
                        <div className="bg-slate-100 p-3 rounded-lg">
                          <p className="text-sm font-medium text-slate-700 flex items-start gap-2">
                            <Lightbulb className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                            {pred.recommended_action || "Rezervasyonu kontrol edin veya misafirle iletişime geçin."}
                          </p>
                        </div>
                        {pred.factors && pred.factors.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-3">
                            {pred.factors.map((factor, i) => (
                              <Badge key={i} variant="secondary" className="bg-white border-slate-200 text-slate-600 text-[10px]">
                                {factor}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Demand Forecast */}
          <Card className="lg:col-span-2 border-none shadow-lg shadow-slate-200/50">
            <CardHeader className="bg-slate-50/50 border-b border-slate-100 pb-4 flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-lg font-bold text-slate-800 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-indigo-500" />
                  30 Günlük Talep Tahmini
                </CardTitle>
                <CardDescription>Gelecek 30 gün için öngörülen doluluk ve fiyatlandırma önerileri</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-6">
              {loading && demandForecast.length === 0 ? (
                <div className="py-20 text-center text-slate-400">Talep grafiği yükleniyor...</div>
              ) : (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-3">
                    {demandForecast.slice(0, 14).map((forecast, idx) => (
                      <div 
                        key={idx} 
                        className={`p-4 rounded-xl flex flex-col items-center justify-center border shadow-sm transition-transform hover:scale-105 ${
                          forecast.demand_level === 'very_high' ? 'bg-red-50/80 border-red-100' :
                          forecast.demand_level === 'high' ? 'bg-amber-50/80 border-amber-100' :
                          forecast.demand_level === 'medium' ? 'bg-indigo-50/80 border-indigo-100' :
                          'bg-emerald-50/80 border-emerald-100'
                        }`}
                      >
                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
                          {forecast.day_of_week.substring(0, 3)}
                        </p>
                        <div className="w-full flex items-center justify-center gap-1">
                          <p className={`text-xl font-black ${
                            forecast.demand_level === 'very_high' ? 'text-red-700' :
                            forecast.demand_level === 'high' ? 'text-amber-700' :
                            forecast.demand_level === 'medium' ? 'text-indigo-700' :
                            'text-emerald-700'
                          }`}>
                            {forecast.occupancy_forecast}%
                          </p>
                        </div>
                        <div className="mt-3 px-3 py-1 bg-white/60 rounded-full w-full text-center backdrop-blur-sm">
                          <p className="text-xs font-bold text-slate-700">€{forecast.recommended_price}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="mt-8 p-5 bg-gradient-to-r from-indigo-50 to-blue-50 border border-indigo-100 rounded-xl shadow-inner">
                    <div className="flex gap-4">
                      <div className="bg-white p-2 rounded-full shadow-sm h-fit">
                        <Lightbulb className="w-6 h-6 text-indigo-500" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-indigo-900 mb-1">Yapay Zeka Fiyatlandırma Önerisi</h4>
                        <p className="text-sm text-indigo-800/80 leading-relaxed">
                          Önümüzdeki 14 gün içinde tespit edilen yüksek talep günleri için fiyatlarınızı <strong>%15-20</strong> oranında artırmanız önerilmektedir. 
                          Kırmızı ile işaretlenmiş günler "çok yüksek" talep potansiyeline sahiptir; bu günlerde taban fiyat uygulamanızı kısıtlayabilirsiniz.
                        </p>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </MaybeLayout>
  );
};

export default PredictiveAnalytics;
