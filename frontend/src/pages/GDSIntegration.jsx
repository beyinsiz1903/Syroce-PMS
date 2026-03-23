import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Globe, Send, Home, TrendingUp, DollarSign, Calendar, CheckCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const GDSIntegration = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [reservations, setReservations] = useState([]);
  const [stats, setStats] = useState({ total: 0, today: 0, revenue: 0 });

  useEffect(() => {
    loadReservations();
  }, []);

  const loadReservations = async () => {
    try {
      const response = await axios.get('/gds/reservations');
      setReservations(response.data.reservations || []);
      setStats({
        total: response.data.total || 0,
        today: response.data.reservations?.filter(r => 
          new Date(r.created_at).toDateString() === new Date().toDateString()
        ).length || 0,
        revenue: response.data.reservations?.reduce((sum, r) => sum + (r.total_amount || 0), 0) || 0
      });
    } catch (error) {
      console.error('GDS rezervasyonları yüklenemedi');
    }
  };

  const pushRateToGDS = async (provider) => {
    try {
      await axios.post('/gds/push-rate', {
        provider: provider,
        room_type: 'Standard',
        rate: 120,
        availability: 10
      });
      toast.success(t('gds.rateSent', { provider }));
    } catch (error) {
      toast.error(t('gds.rateFailed'));
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button 
              variant="outline" 
              size="icon"
              onClick={() => navigate('/')}
              className="hover:bg-blue-50"
            >
              <Home className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold">{t('gds.title')}</h1>
              <p className="text-gray-600">{t('gds.subtitle')}</p>
            </div>
          </div>
        </div>
      </div>

      {/* GDS Providers */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <Card className="hover:shadow-lg transition-shadow">
          <CardContent className="pt-6">
            <Globe className="w-12 h-12 text-blue-600 mx-auto mb-3" />
            <p className="text-xl font-bold text-center mb-2">Amadeus</p>
            <p className="text-sm text-gray-600 text-center mb-4">Global #1 GDS</p>
            <Button 
              className="w-full bg-blue-600 hover:bg-blue-700"
              onClick={() => pushRateToGDS('Amadeus')}
            >
              <Send className="w-4 h-4 mr-2" />
              {t('gds.sendRate')}
            </Button>
          </CardContent>
        </Card>
        <Card className="hover:shadow-lg transition-shadow">
          <CardContent className="pt-6">
            <Globe className="w-12 h-12 text-green-600 mx-auto mb-3" />
            <p className="text-xl font-bold text-center mb-2">Sabre</p>
            <p className="text-sm text-gray-600 text-center mb-4">Americas Leader</p>
            <Button 
              className="w-full bg-green-600 hover:bg-green-700"
              onClick={() => pushRateToGDS('Sabre')}
            >
              <Send className="w-4 h-4 mr-2" />
              {t('gds.sendRate')}
            </Button>
          </CardContent>
        </Card>
        <Card className="hover:shadow-lg transition-shadow">
          <CardContent className="pt-6">
            <Globe className="w-12 h-12 text-purple-600 mx-auto mb-3" />
            <p className="text-xl font-bold text-center mb-2">Galileo</p>
            <p className="text-sm text-gray-600 text-center mb-4">Europe Strong</p>
            <Button 
              className="w-full bg-purple-600 hover:bg-purple-700"
              onClick={() => pushRateToGDS('Galileo')}
            >
              <Send className="w-4 h-4 mr-2" />
              {t('gds.sendRate')}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent className="pt-6 text-center">
            <Calendar className="w-8 h-8 text-blue-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{stats.total}</p>
            <p className="text-sm text-gray-500">{t('gds.totalGdsReservations')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <CheckCircle className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{stats.today}</p>
            <p className="text-sm text-gray-500">{t('gds.todayArrived')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <DollarSign className="w-8 h-8 text-purple-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">€{stats.revenue}</p>
            <p className="text-sm text-gray-500">{t('gds.gdsRevenue')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <TrendingUp className="w-8 h-8 text-orange-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">+12%</p>
            <p className="text-sm text-gray-500">{t('gds.growth')}</p>
          </CardContent>
        </Card>
      </div>

      {/* Reservations */}
      <Card>
        <CardHeader>
          <CardTitle>{t('gds.recentReservations')}</CardTitle>
        </CardHeader>
        <CardContent>
          {reservations.length === 0 ? (
            <div className="text-center py-8">
              <Globe className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">{t('gds.noReservations')}</p>
              <p className="text-sm text-gray-500 mt-2">{t('gds.autoSyncActive')}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {reservations.map((res) => (
                <div key={res.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-semibold">{res.guest_name}</p>
                    <p className="text-sm text-gray-600">PNR: {res.pnr_number}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold capitalize">{res.gds_provider}</p>
                    <p className="text-sm text-gray-500">{res.check_in}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default GDSIntegration;