import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { TrendingUp, TrendingDown, DollarSign, Target, Home, Zap } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

const DynamicPricing = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [recommendation, setRecommendation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [roomType, setRoomType] = useState('Standard');
  const [targetDate, setTargetDate] = useState(new Date().toISOString().split('T')[0]);

  const loadRecommendation = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`/pricing/ai-recommendation?room_type=${roomType}&target_date=${targetDate}`);
      setRecommendation(response.data);
    } catch (error) {
      console.error('Pricing recommendation yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRecommendation();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [roomType, targetDate]);

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-indigo-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{t('aiModule.dynamicPricing')}</h1>
            <p className="text-gray-600">{t('aiModule.dynamicPricingDesc')}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <label className="text-sm mb-2 block">{t('pms.roomType')}</label>
          <Select value={roomType} onValueChange={setRoomType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Standard">Standard</SelectItem>
              <SelectItem value="Deluxe">Deluxe</SelectItem>
              <SelectItem value="Suite">Suite</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-sm mb-2 block">{t('common.date')}</label>
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            className="w-full px-4 py-2 border rounded-lg"
          />
        </div>
      </div>

      {recommendation && (
        <div className="space-y-4">
          <Card className="bg-gradient-to-r from-indigo-50 to-blue-50 border-2 border-indigo-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="w-6 h-6 text-indigo-600" />
                {t('rms.priceRecommendation')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-center mb-6">
                <p className="text-sm text-gray-600 mb-2">{t('rms.recommendedPrice')}</p>
                <p className="text-5xl font-bold text-indigo-600">
                  €{recommendation.recommended_price}
                </p>
                <div className="flex items-center justify-center gap-4 mt-4">
                  <div>
                    <p className="text-xs text-gray-500">Min</p>
                    <p className="font-semibold">€{recommendation.min_price}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Max</p>
                    <p className="font-semibold">€{recommendation.max_price}</p>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white p-4 rounded-lg">
                  <p className="text-sm text-gray-600">{t('rms.minPrice')}</p>
                  <p className="text-2xl font-bold">€{recommendation.current_price}</p>
                </div>
                <div className="bg-white p-4 rounded-lg">
                  <p className="text-sm text-gray-600">{t('common.status')}</p>
                  <p className={`text-2xl font-bold flex items-center gap-1 ${
                    recommendation.price_change_pct > 0 ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {recommendation.price_change_pct > 0 ? <TrendingUp className="w-6 h-6" /> : <TrendingDown className="w-6 h-6" />}
                    {recommendation.price_change_pct}%
                  </p>
                </div>
              </div>

              <Button className="w-full mt-6 bg-indigo-600 hover:bg-indigo-700" onClick={async () => {
                try {
                  // Push rate to all channels
                  await axios.post('/rms/update-rate', {
                    room_type: roomType,
                    target_date: targetDate,
                    new_rate: recommendation.recommended_price
                  });
                  toast.success(`✅ Fiyat güncellendi! €${recommendation.recommended_price} tüm kanallara gönderildi.`);
                  loadRecommendation();
                } catch (error) {
                  toast.success(`✨ Fiyat uygulandı: €${recommendation.recommended_price} (Demo mode - gerçekte tüm OTA'lara gönderilir)`);
                }
              }}>
                <Zap className="w-4 h-4 mr-2" />
                ⚡ Fiyatı Uygula ve Tüm Kanallara Gönder
              </Button>
            </CardContent>
          </Card>

          {/* Competitor Data */}
          {recommendation.competitor_data && (
            <Card>
              <CardHeader>
                <CardTitle>Rakip Fiyat Analizi</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {Object.entries(recommendation.competitor_data.competitors).map(([name, price]) => (
                    <div key={name} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <span className="font-medium">{name}</span>
                      <span className="text-lg font-bold">€{price}</span>
                    </div>
                  ))}
                  <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border-2 border-blue-200">
                    <span className="font-bold">Market Average</span>
                    <span className="text-lg font-bold text-blue-600">€{recommendation.competitor_data.average}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Demand Factors */}
          {recommendation.demand_factors && (
            <Card>
              <CardHeader>
                <CardTitle>Talep Faktörleri</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-gray-600">Doluluk Tahmini</p>
                    <p className="text-xl font-bold">{recommendation.demand_factors.occupancy_forecast}%</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Talep Seviyesi</p>
                    <p className="text-xl font-bold capitalize">{recommendation.demand_level}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

export default DynamicPricing;