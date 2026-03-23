import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Smile, Meh, Frown, TrendingUp, Home } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const GuestJourney = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [npsData, setNpsData] = useState(null);

  useEffect(() => {
    loadNPS();
  }, []);

  const loadNPS = async () => {
    try {
      const response = await axios.get('/nps/score?days=30');
      setNpsData(response.data);
    } catch (error) {
      console.error('NPS yüklenemedi');
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
            className="hover:bg-purple-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{t('guestJourney.title')}</h1>
            <p className="text-gray-600">{t('guestJourney.subtitle')}</p>
          </div>
        </div>
      </div>

      {npsData && (
        <>
          <Card className="mb-6 bg-gradient-to-r from-green-50 to-blue-50">
            <CardContent className="pt-8 text-center">
              <p className="text-sm text-gray-600 mb-2">{t('guestJourney.npsScore')}</p>
              <p className="text-6xl font-bold text-green-600">{npsData.nps_score}</p>
              <p className="text-sm text-gray-600 mt-2">
                {t('guestJourney.responses', { count: npsData.total_responses })}
              </p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-3 gap-4">
            <Card>
              <CardContent className="pt-6 text-center">
                <Smile className="w-12 h-12 text-green-600 mx-auto mb-2" />
                <p className="text-3xl font-bold">{npsData.promoters}</p>
                <p className="text-sm text-gray-500">{t('guestJourney.promoters')}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <Meh className="w-12 h-12 text-yellow-600 mx-auto mb-2" />
                <p className="text-3xl font-bold">{npsData.passives}</p>
                <p className="text-sm text-gray-500">{t('guestJourney.passives')}</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <Frown className="w-12 h-12 text-red-600 mx-auto mb-2" />
                <p className="text-3xl font-bold">{npsData.detractors}</p>
                <p className="text-sm text-gray-500">{t('guestJourney.detractors')}</p>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
};

export default GuestJourney;