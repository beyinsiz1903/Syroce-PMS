import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import MaybeLayout from '@/components/MaybeLayout';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { TrendingUp, TrendingDown, Target, Info, BarChart3, ChevronRight, Save } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import AITabs from '@/components/AITabs';

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
        toast.error(data.message || 'Fiyat uygulanamadı. Lütfen alanları kontrol edin.');
      } else if (data.pushed) {
        toast.success(`Fiyat güncellendi: €${recommendation.recommended_price} kanallara gönderildi.`);
      } else {
        toast.info(data.message || `Fiyat €${recommendation.recommended_price} yerel olarak kaydedildi. Gerçek OTA dağıtımı için Toplu Fiyat/Envanter ekranını kullanın.`);
      }
      loadRecommendation();
    } catch (error) {
      toast.error('Fiyat uygulanamadı. Lütfen tekrar deneyin veya kanal yapılandırmasını kontrol edin.');
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="ai_revenue_autopilot">
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-6">
        
        <AITabs />

        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-blue-50 text-blue-600 rounded-lg">
            <BarChart3 className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">{t('aiModule.dynamicPricing', 'Dinamik Fiyatlandırma')}</h1>
            <p className="text-sm text-slate-500">{t('aiModule.dynamicPricingDesc', 'Yapay zeka ve kurallar motoru destekli fiyat optimizasyonu')}</p>
          </div>
        </div>

        {/* Filters */}
        <Card className="shadow-sm border-slate-200">
          <CardContent className="p-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-600">{t('pms.roomType', 'Oda Tipi')}</label>
                <Select value={roomType} onValueChange={setRoomType}>
                  <SelectTrigger className="w-full bg-white border-slate-200 h-10">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Standard">Standard</SelectItem>
                    <SelectItem value="Deluxe">Deluxe</SelectItem>
                    <SelectItem value="Suite">Suite</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-600">{t('common.date', 'Tarih')}</label>
                <input
                  type="date"
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                  className="w-full px-3 h-10 bg-white border border-slate-200 rounded-md focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm transition-all"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-400 space-y-3">
            <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full"></div>
            <p className="text-sm font-medium">Hesaplanıyor...</p>
          </div>
        ) : recommendation && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* Left Column - Main Pricing */}
            <div className="lg:col-span-2 space-y-6">
              {(recommendation.data_available === false || recommendation.recommended_price == null) ? (
                <Card className="shadow-sm border-amber-200 bg-amber-50/30">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2 text-amber-800">
                      <Info className="w-5 h-5 text-amber-600" />
                      Yetersiz Veri
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-amber-900/80 leading-relaxed">
                      Bu oda tipi ve tarih için gerçek veriye dayalı fiyat önerisi üretilemedi. 
                      Oda taban fiyatları yapılandırıldığında öneri otomatik oluşur. 
                      Ayrıntı için aşağıdaki "Devreye Giren Kurallar" bölümüne bakın.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="shadow-sm border-blue-100 overflow-hidden">
                  <div className="bg-gradient-to-r from-blue-50 to-indigo-50 px-6 py-4 border-b border-blue-100 flex justify-between items-center">
                    <div className="flex items-center gap-2 text-blue-900 font-medium">
                      <Target className="w-5 h-5 text-blue-600" />
                      Fiyat Önerisi
                    </div>
                    <Badge variant="outline" className="bg-white text-blue-700 border-blue-200">
                      Optimize Edildi
                    </Badge>
                  </div>
                  
                  <CardContent className="p-6">
                    <div className="flex flex-col md:flex-row items-center justify-between gap-8 mb-8">
                      <div className="text-center md:text-left">
                        <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1.5">Önerilen Fiyat</p>
                        <p className="text-2xl font-bold text-slate-800 tracking-tight">
                          €{recommendation.recommended_price}
                        </p>
                        <div className="flex items-center justify-center md:justify-start gap-4 mt-3 text-xs">
                          <div>
                            <span className="text-slate-400">Taban: </span>
                            <span className="font-medium text-slate-700">€{recommendation.min_price}</span>
                          </div>
                          <div className="w-px h-4 bg-slate-200"></div>
                          <div>
                            <span className="text-slate-400">Tavan: </span>
                            <span className="font-medium text-slate-700">€{recommendation.max_price}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-4 w-full md:w-auto">
                        <div className="flex-1 md:w-28 bg-slate-50 p-4 rounded-lg border border-slate-100 text-center">
                          <p className="text-xs font-medium text-slate-500 mb-1">Mevcut</p>
                          <p className="text-xl font-semibold text-slate-800">€{recommendation.current_price}</p>
                        </div>
                        <div className={`flex-1 md:w-28 p-4 rounded-lg border text-center ${
                          recommendation.price_change_pct > 0 ? 'bg-emerald-50 border-emerald-100' : 'bg-red-50 border-red-100'
                        }`}>
                          <p className="text-xs font-medium text-slate-500 mb-1">Fark</p>
                          <div className={`flex items-center justify-center gap-1 font-semibold ${
                            recommendation.price_change_pct > 0 ? 'text-emerald-600' : 'text-red-600'
                          }`}>
                            {recommendation.price_change_pct > 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                            <span className="text-xl">{recommendation.price_change_pct}%</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-2 pt-6 border-t border-slate-100 flex justify-end">
                      <Button 
                        className="h-8 px-4 text-xs bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm shadow-indigo-200 transition-all rounded-lg font-medium" 
                        onClick={handleUpdateRate}
                      >
                        <Save className="w-3.5 h-3.5 mr-2 opacity-80" />
                        Fiyatı Onayla ve Kaydet
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Applied Rules */}
              {recommendation.applied_rules && recommendation.applied_rules.length > 0 && (
                <Card className="shadow-sm border-slate-200">
                  <CardHeader className="pb-3 border-b border-slate-100 bg-slate-50/50">
                    <CardTitle className="text-sm font-semibold text-slate-800">Devreye Giren Kurallar</CardTitle>
                  </CardHeader>
                  <CardContent className="p-4">
                    <ul className="space-y-2">
                      {recommendation.applied_rules.map((rule, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-sm text-slate-600">
                          <ChevronRight className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                          <span>{rule}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Right Column - Context Data */}
            <div className="lg:col-span-1 space-y-6">
              
              {/* Demand Factors */}
              {recommendation.demand_factors && (
                <Card className="shadow-sm border-slate-200">
                  <CardHeader className="pb-3 border-b border-slate-100">
                    <CardTitle className="text-sm font-semibold text-slate-800">Talep Analizi</CardTitle>
                  </CardHeader>
                  <CardContent className="p-4">
                    <div className="space-y-4">
                      <div className="flex justify-between items-center pb-3 border-b border-slate-100">
                        <span className="text-sm text-slate-500">Beklenen Doluluk</span>
                        <span className="text-lg font-semibold text-slate-800">{recommendation.demand_factors.occupancy_forecast}%</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm text-slate-500">Talep Seviyesi</span>
                        <Badge variant="secondary" className={`text-xs px-2 py-0.5 font-medium uppercase ${
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
              <Card className="shadow-sm border-slate-200">
                <CardHeader className="pb-3 border-b border-slate-100">
                  <CardTitle className="text-sm font-semibold text-slate-800">Rakip Analizi</CardTitle>
                </CardHeader>
                <CardContent className="p-4">
                  {recommendation.competitor_data && recommendation.competitor_data.available ? (
                    <div className="space-y-3">
                      {Object.entries(recommendation.competitor_data.competitors).map(([name, price]) => (
                        <div key={name} className="flex items-center justify-between">
                          <span className="text-sm text-slate-600 flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-300"></span>
                            {name}
                          </span>
                          <span className="text-sm font-medium text-slate-900">€{price}</span>
                        </div>
                      ))}
                      <div className="flex items-center justify-between pt-3 mt-1 border-t border-slate-100">
                        <span className="text-sm font-semibold text-slate-700">Pazar Ortalaması</span>
                        <span className="text-base font-bold text-slate-900">€{recommendation.competitor_data.average}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="py-4 flex flex-col items-center text-center text-slate-400">
                      <Info className="w-5 h-5 mb-2 text-slate-300" />
                      <p className="text-xs">Rakip verisi bulunamadı.</p>
                    </div>
                  )}
                </CardContent>
              </Card>

            </div>
          </div>
        )}
      </div>
    </MaybeLayout>
  );
};

export default DynamicPricing;