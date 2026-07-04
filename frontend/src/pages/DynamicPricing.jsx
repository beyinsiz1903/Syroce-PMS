import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import MaybeLayout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { TrendingUp, TrendingDown, Target, Home, Zap, Info, BarChart3, ChevronRight, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';

const DynamicPricing = ({ user, tenant, onLogout, embedded }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [recommendation, setRecommendation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [roomType, setRoomType] = useState('Standard');
  const [targetDate, setTargetDate] = useState(new Date().toISOString().split('T')[0]);

  const loadRecommendation = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(`/pricing/ai-recommendation?room_type=${roomType}&target_date=${targetDate}`);
      setRecommendation(response.data);
    } catch (error) {
      console.error('Pricing recommendation yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [roomType, targetDate]);

  useEffect(() => {
    loadRecommendation();
  }, [loadRecommendation]);

  const handleUpdateRate = async () => {
    try {
      const resp = await axios.post('/rms/update-rate', {
        room_type: roomType,
        target_date: targetDate,
        new_rate: recommendation.recommended_price
      });
      const data = resp?.data || {};
      if (data.success === false) {
        toast.error(data.message || 'Fiyat uygulanamadi. Lutfen alanlari kontrol edin.');
      } else if (data.pushed) {
        toast.success(`Fiyat güncellendi: €${recommendation.recommended_price} kanallara gönderildi.`);
      } else {
        toast.info(data.message || `Fiyat €${recommendation.recommended_price} yerel olarak kaydedildi. Gerçek OTA dağıtımı için Toplu Fiyat/Envanter ekranını kullanın.`);
      }
      loadRecommendation();
    } catch (error) {
      toast.error('Fiyat uygulanamadi. Lutfen tekrar deneyin veya kanal yapilandirmasini kontrol edin.');
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="ai_revenue_autopilot">
      <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-8 animate-in fade-in duration-500">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl shadow-lg shadow-blue-200">
              <BarChart3 className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">{t('aiModule.dynamicPricing')}</h1>
              <p className="text-slate-500 mt-1">{t('aiModule.dynamicPricingDesc')}</p>
            </div>
          </div>
        </div>

        {/* Filters */}
        <Card className="border-none shadow-md overflow-visible relative z-20">
          <CardContent className="p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700 block">{t('pms.roomType')}</label>
                <Select value={roomType} onValueChange={setRoomType}>
                  <SelectTrigger className="w-full bg-slate-50 border-slate-200 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-all rounded-xl h-12">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Standard">Standard</SelectItem>
                    <SelectItem value="Deluxe">Deluxe</SelectItem>
                    <SelectItem value="Suite">Suite</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-slate-700 block">{t('common.date')}</label>
                <input
                  type="date"
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                  className="w-full px-4 h-12 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {loading ? (
          <div className="h-64 flex flex-col items-center justify-center text-slate-400 space-y-4">
            <div className="animate-spin w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full"></div>
            <p className="font-medium animate-pulse">Optimum fiyat hesaplanıyor...</p>
          </div>
        ) : recommendation && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            
            {/* Left Column - Main Pricing */}
            <div className="lg:col-span-7 space-y-8">
              {(recommendation.data_available === false || recommendation.recommended_price == null) ? (
                <Card className="border-none shadow-md overflow-hidden relative">
                  <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-amber-400 z-10"></div>
                  <div className="absolute inset-0 bg-gradient-to-br from-amber-50 to-transparent z-0"></div>
                  <CardHeader className="relative z-10">
                    <CardTitle className="flex items-center gap-2 text-amber-800">
                      <Info className="w-6 h-6 text-amber-500" />
                      Yetersiz Veri
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="relative z-10">
                    <p className="text-amber-800/80 leading-relaxed">
                      Bu oda tipi ve tarih için gerçek veriye dayalı fiyat önerisi üretilemedi. 
                      Oda taban fiyatları yapılandırıldığında öneri otomatik oluşur. 
                      Ayrıntı için aşağıdaki "Uygulanan Kurallar" bölümüne bakın.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="border-none shadow-xl shadow-indigo-200/50 overflow-hidden relative">
                  <div className="absolute inset-0 bg-gradient-to-br from-indigo-500 via-indigo-600 to-blue-700 opacity-5 pointer-events-none z-0"></div>
                  <CardContent className="p-8 relative z-10 flex flex-col h-full justify-between">
                    <div className="flex justify-between items-start mb-8">
                      <div>
                        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                          <Target className="w-6 h-6 text-indigo-600" />
                          Yapay Zeka Fiyat Önerisi
                        </h2>
                        <p className="text-sm text-slate-500 mt-1">Gelişmiş kural motoru tarafından optimize edildi</p>
                      </div>
                      <Badge variant="outline" className="bg-indigo-50 text-indigo-700 border-indigo-200 px-3 py-1 text-xs uppercase tracking-wider font-bold">
                        Optimum
                      </Badge>
                    </div>

                    <div className="text-center mb-10">
                      <p className="text-7xl font-black text-transparent bg-clip-text bg-gradient-to-br from-indigo-600 to-blue-600 py-2">
                        €{recommendation.recommended_price}
                      </p>
                      
                      <div className="flex items-center justify-center gap-10 mt-6 pt-6 border-t border-slate-100">
                        <div className="text-center">
                          <p className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-1">Taban Limit</p>
                          <p className="text-2xl font-bold text-slate-700">€{recommendation.min_price}</p>
                        </div>
                        <div className="w-px h-12 bg-slate-200"></div>
                        <div className="text-center">
                          <p className="text-sm font-semibold text-slate-400 uppercase tracking-wide mb-1">Tavan Limit</p>
                          <p className="text-2xl font-bold text-slate-700">€{recommendation.max_price}</p>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mb-8">
                      <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100 flex flex-col items-center justify-center transition-transform hover:-translate-y-1">
                        <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">{t('rms.minPrice')}</p>
                        <p className="text-3xl font-black text-slate-800">€{recommendation.current_price}</p>
                      </div>
                      <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100 flex flex-col items-center justify-center transition-transform hover:-translate-y-1">
                        <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">{t('common.status')}</p>
                        <div className={`flex items-center justify-center gap-2 ${
                          recommendation.price_change_pct > 0 ? 'text-emerald-500 bg-emerald-50' : 'text-red-500 bg-red-50'
                        } px-4 py-2 rounded-xl`}>
                          {recommendation.price_change_pct > 0 ? <TrendingUp className="w-6 h-6" /> : <TrendingDown className="w-6 h-6" />}
                          <span className="text-3xl font-black">{recommendation.price_change_pct}%</span>
                        </div>
                      </div>
                    </div>

                    <Button 
                      className="w-full h-14 text-lg font-bold shadow-lg shadow-indigo-300 hover:shadow-xl hover:shadow-indigo-400 transition-all bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 rounded-xl group" 
                      onClick={handleUpdateRate}
                    >
                      <Save className="w-5 h-5 mr-2 group-hover:scale-110 transition-transform" />
                      Fiyatı Onayla ve Kaydet
                    </Button>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Right Column - Context Data */}
            <div className="lg:col-span-5 space-y-6">
              
              {/* Demand Factors */}
              {recommendation.demand_factors && (
                <Card className="border-none shadow-md overflow-hidden relative">
                  <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-500 z-10"></div>
                  <CardHeader className="bg-slate-50/50 pb-4 border-b border-slate-100 pl-8">
                    <CardTitle className="text-lg font-bold text-slate-800">Talep Analizi</CardTitle>
                  </CardHeader>
                  <CardContent className="p-6 pl-8">
                    <div className="grid grid-cols-2 gap-6">
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Beklenen Doluluk</p>
                        <p className="text-3xl font-black text-slate-800">{recommendation.demand_factors.occupancy_forecast}%</p>
                      </div>
                      <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Talep Seviyesi</p>
                        <Badge variant="secondary" className={`text-sm px-3 py-1 font-bold uppercase ${
                          recommendation.demand_level === 'very_high' ? 'bg-red-100 text-red-700' :
                          recommendation.demand_level === 'high' ? 'bg-amber-100 text-amber-700' :
                          recommendation.demand_level === 'medium' ? 'bg-blue-100 text-blue-700' :
                          'bg-emerald-100 text-emerald-700'
                        }`}>
                          {recommendation.demand_level}
                        </Badge>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Competitor Data */}
              <Card className="border-none shadow-md overflow-hidden relative">
                <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-purple-500 z-10"></div>
                <CardHeader className="bg-slate-50/50 pb-4 border-b border-slate-100 pl-8">
                  <CardTitle className="text-lg font-bold text-slate-800">Rakip Analizi</CardTitle>
                </CardHeader>
                <CardContent className="p-6 pl-8">
                  {recommendation.competitor_data && recommendation.competitor_data.available ? (
                    <div className="space-y-4">
                      {Object.entries(recommendation.competitor_data.competitors).map(([name, price]) => (
                        <div key={name} className="flex items-center justify-between p-4 bg-white border border-slate-100 rounded-xl shadow-sm hover:border-slate-300 transition-colors">
                          <span className="font-semibold text-slate-700 flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-slate-300"></div>
                            {name}
                          </span>
                          <span className="text-xl font-bold text-slate-900">€{price}</span>
                        </div>
                      ))}
                      <div className="flex items-center justify-between p-4 mt-2 bg-gradient-to-r from-purple-50 to-indigo-50 border border-purple-100 rounded-xl shadow-inner">
                        <span className="font-black text-purple-900">Pazar Ortalaması</span>
                        <span className="text-2xl font-black text-purple-700">€{recommendation.competitor_data.average}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="py-6 flex flex-col items-center justify-center text-slate-400">
                      <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mb-3">
                        <Info className="w-6 h-6 text-slate-300" />
                      </div>
                      <p className="text-sm font-medium">Bu bölge/oda için rakip verisi bulunamadı.</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Applied Rules */}
              {recommendation.applied_rules && recommendation.applied_rules.length > 0 && (
                <Card className="border-none shadow-md overflow-hidden relative">
                  <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-emerald-500 z-10"></div>
                  <CardHeader className="bg-slate-50/50 pb-4 border-b border-slate-100 pl-8">
                    <CardTitle className="text-lg font-bold text-slate-800">Devreye Giren Kurallar</CardTitle>
                  </CardHeader>
                  <CardContent className="p-6 pl-8">
                    <ul className="space-y-3">
                      {recommendation.applied_rules.map((rule, idx) => (
                        <li key={idx} className="flex items-start gap-3">
                          <ChevronRight className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
                          <span className="text-sm font-medium text-slate-700 leading-relaxed">{rule}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
            </div>
            
          </div>
        )}
      </div>
    </MaybeLayout>
  );
};

export default DynamicPricing;