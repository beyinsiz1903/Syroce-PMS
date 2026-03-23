import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Star, TrendingUp, TrendingDown, AlertTriangle, Home, MessageCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from 'react-i18next';

const ReputationCenter = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [overview, setOverview] = useState(null);
  const [trends, setTrends] = useState(null);
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [overviewRes, trendsRes, alertsRes] = await Promise.all([
        axios.get('/reputation/overview'),
        axios.get('/reputation/trends'),
        axios.get('/reputation/negative-alerts')
      ]);
      
      setOverview(overviewRes.data);
      setTrends(trendsRes.data);
      setAlerts(alertsRes.data.negative_reviews || []);
    } catch (error) {
      console.error('Reputation yüklenemedi');
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-yellow-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">⭐ Online {t('dashboard.reputationCenterModule')}</h1>
            <p className="text-gray-600">Multi-platform review yönetimi ve sentiment analizi</p>
          </div>
        </div>
      </div>

      {overview && (
        <>
          <Card className="mb-6 bg-gradient-to-r from-yellow-50 to-orange-50">
            <CardContent className="pt-8 text-center">
              <div className="flex items-center justify-center gap-2 mb-4">
                <Star className="w-12 h-12 text-yellow-500 fill-yellow-500" />
                <p className="text-6xl font-bold">{overview.overall_rating}</p>
                <span className="text-2xl text-gray-500">/5.0</span>
              </div>
              <p className="text-gray-600">{overview.total_reviews.toLocaleString()} toplam değerlendirme</p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-4 gap-4 mb-6">
            {Object.entries(overview.platforms).map(([platform, data]) => (
              <Card key={platform}>
                <CardContent className="pt-6">
                  <p className="text-sm font-semibold capitalize mb-2">
                    {platform === 'booking_com' ? 'Booking.com' : platform}
                  </p>
                  <p className="text-3xl font-bold">{data.rating}</p>
                  <p className="text-xs text-gray-500">{data.total_reviews} reviews</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}

      {trends && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {trends.trend === 'improving' ? <TrendingUp className="w-6 h-6 text-green-600" /> : 
               trends.trend === 'declining' ? <TrendingDown className="w-6 h-6 text-red-600" /> : null}
              Trend Analizi
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <p className="text-sm text-gray-600">Ortalama Rating</p>
                <p className="text-2xl font-bold">{trends.avg_rating}</p>
              </div>
              <div className="text-center">
                <p className="text-sm text-gray-600">Trend</p>
                <p className={`text-xl font-bold capitalize ${
                  trends.trend === 'improving' ? 'text-green-600' :
                  trends.trend === 'declining' ? 'text-red-600' : 'text-gray-600'
                }`}>
                  {trends.trend === 'improving' ? '↑ Yükseliyor' :
                   trends.trend === 'declining' ? '↓ Düşüyor' : '= Stabil'}
                </p>
              </div>
              <div className="text-center">
                <p className="text-sm text-gray-600">Toplam Review</p>
                <p className="text-2xl font-bold">{trends.total_reviews}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {alerts.length > 0 && (
        <Card className="border-red-200 bg-red-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-800">
              <AlertTriangle className="w-6 h-6" />
              Negatif Review Uyarıları
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-red-700">Son 24 saatte {alerts.length} negatif review</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ReputationCenter;