import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import MaybeLayout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, TrendingUp, Target, CheckCircle, Lightbulb, Activity, ChevronRight } from 'lucide-react';
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
      high: 'bg-red-50 text-red-600 border-red-200',
      medium: 'bg-amber-50 text-amber-600 border-amber-200',
      low: 'bg-emerald-50 text-emerald-600 border-emerald-200'
    };
    return (
      <Badge className={`${colors[level]} border px-2 py-0.5 rounded-md text-xs font-semibold uppercase`}>
        {level}
      </Badge>
    );
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="ai_revenue_autopilot">
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-lg">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-slate-900">Tahmine Dayalı Analiz</h1>
              <p className="text-sm text-slate-500">Yapay zeka destekli no-show riskleri ve talep öngörüleri</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 h-10 bg-white border border-slate-200 rounded-md focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm transition-all"
            />
          </div>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card className="shadow-sm border-slate-200">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="p-3 bg-red-50 text-red-600 rounded-lg shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-800">{noShowPredictions.filter(p => p.risk_level === 'high').length}</p>
                <p className="text-xs font-medium text-slate-500">Yüksek Risk No-show</p>
              </div>
            </CardContent>
          </Card>
          
          <Card className="shadow-sm border-slate-200">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="p-3 bg-amber-50 text-amber-600 rounded-lg shrink-0">
                <Target className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-800">{noShowPredictions.length}</p>
                <p className="text-xs font-medium text-slate-500">Toplam Riskli Kayıt</p>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-sm border-slate-200">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-lg shrink-0">
                <TrendingUp className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-800">
                  {demandForecast.filter(f => ['high', 'very_high'].includes(f.demand_level)).length}
                </p>
                <p className="text-xs font-medium text-slate-500">Yüksek Talep Günleri</p>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-sm border-slate-200">
            <CardContent className="p-4 flex items-center gap-4">
              <div className="p-3 bg-emerald-50 text-emerald-600 rounded-lg shrink-0">
                <Activity className="w-5 h-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-800">30</p>
                <p className="text-xs font-medium text-slate-500">Günlük Projeksiyon</p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* No-Show List */}
          <Card className="lg:col-span-1 shadow-sm border-slate-200 flex flex-col max-h-[600px]">
            <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
              <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-slate-500" />
                No-Show Riskleri
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-y-auto flex-1">
              {loading && noShowPredictions.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-sm">Tahminler yükleniyor...</div>
              ) : noShowPredictions.length === 0 ? (
                <div className="py-12 flex flex-col items-center justify-center text-center px-4">
                  <div className="p-3 bg-emerald-50 rounded-full mb-3">
                    <CheckCircle className="w-6 h-6 text-emerald-500" />
                  </div>
                  <p className="text-sm font-medium text-slate-700">Harika haber!</p>
                  <p className="text-xs text-slate-500 mt-1">Seçili gün için yüksek riskli no-show kaydı bulunamadı.</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {noShowPredictions.map((pred, idx) => (
                    <div key={idx} className="p-4 hover:bg-slate-50 transition-colors">
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <p className="font-bold text-slate-800 font-mono text-sm">#{pred.booking_id.substring(0, 8).toUpperCase()}</p>
                          <p className="text-xs text-slate-500 mt-0.5">
                            Risk Skoru: <span className="font-medium text-slate-700">%{(pred.risk_score * 100).toFixed(0)}</span>
                          </p>
                        </div>
                        <RiskBadge level={pred.risk_level} />
                      </div>
                      
                      {pred.factors && pred.factors.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {pred.factors.map((factor, i) => (
                            <Badge key={i} variant="secondary" className="bg-white border-slate-200 text-slate-600 text-[10px] font-normal px-1.5 py-0">
                              {factor}
                            </Badge>
                          ))}
                        </div>
                      )}
                      
                      <div className="mt-3 flex items-start gap-2 bg-slate-50 p-2 rounded border border-slate-100">
                        <Lightbulb className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                        <p className="text-xs text-slate-600 leading-relaxed">
                          {pred.recommended_action || "Rezervasyonu kontrol edin veya misafirle iletişime geçin."}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Demand Forecast */}
          <Card className="lg:col-span-2 shadow-sm border-slate-200 flex flex-col">
            <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
              <CardTitle className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-slate-500" />
                30 Günlük Talep Tahmini
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              {loading && demandForecast.length === 0 ? (
                <div className="py-20 text-center text-slate-400 text-sm">Talep grafiği yükleniyor...</div>
              ) : (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-3">
                    {demandForecast.slice(0, 14).map((forecast, idx) => (
                      <div 
                        key={idx} 
                        className={`p-3 rounded-lg flex flex-col items-center justify-center border shadow-sm ${
                          forecast.demand_level === 'very_high' ? 'bg-red-50/50 border-red-100' :
                          forecast.demand_level === 'high' ? 'bg-amber-50/50 border-amber-100' :
                          forecast.demand_level === 'medium' ? 'bg-blue-50/50 border-blue-100' :
                          'bg-slate-50/50 border-slate-200'
                        }`}
                      >
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                          {forecast.day_of_week.substring(0, 3)}
                        </p>
                        <p className={`text-lg font-bold leading-none ${
                          forecast.demand_level === 'very_high' ? 'text-red-700' :
                          forecast.demand_level === 'high' ? 'text-amber-700' :
                          forecast.demand_level === 'medium' ? 'text-blue-700' :
                          'text-slate-700'
                        }`}>
                          {forecast.occupancy_forecast}%
                        </p>
                        <div className="mt-2.5 w-full bg-white rounded border border-slate-100 py-1 text-center">
                          <p className="text-xs font-semibold text-slate-700">€{forecast.recommended_price}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  <div className="mt-6 p-4 bg-blue-50 border border-blue-100 rounded-lg flex items-start gap-3">
                    <div className="mt-0.5 shrink-0 text-blue-500">
                      <Lightbulb className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-blue-900 mb-1">Yapay Zeka Fiyatlandırma Önerisi</h4>
                      <p className="text-xs text-blue-800/80 leading-relaxed">
                        Önümüzdeki 14 gün içinde tespit edilen yüksek talep günleri için fiyatlarınızı <strong>%15-20</strong> oranında artırmanız önerilmektedir. 
                        Renklendirilmiş günler talep potansiyelini ifade eder.
                      </p>
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
