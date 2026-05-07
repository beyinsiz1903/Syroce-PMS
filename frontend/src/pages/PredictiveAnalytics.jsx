import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Home, AlertTriangle, TrendingUp, Calendar, Target, CheckCircle, Lightbulb } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const PredictiveAnalytics = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [noShowPredictions, setNoShowPredictions] = useState([]);
  const [demandForecast, setDemandForecast] = useState([]);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);

  useEffect(() => {
    loadPredictions();
    loadDemandForecast();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedDate]);

  const loadPredictions = async () => {
    try {
      const response = await axios.get(`/predictions/no-shows?target_date=${selectedDate}`);
      setNoShowPredictions(response.data.predictions || []);
    } catch (error) {
      console.error('Predictions yüklenemedi');
    }
  };

  const loadDemandForecast = async () => {
    try {
      const response = await axios.get('/predictions/demand-forecast?days=30');
      setDemandForecast(response.data.daily_forecast || []);
    } catch (error) {
      console.error('Demand forecast yüklenemedi');
    }
  };

  const RiskBadge = ({ level }) => {
    const colors = {
      high: 'bg-red-100 text-red-800 border-red-300',
      medium: 'bg-yellow-100 text-yellow-800 border-yellow-300',
      low: 'bg-green-100 text-green-800 border-green-300'
    };
    return (
      <Badge className={`${colors[level]} border`}>
        {level.toUpperCase()}
      </Badge>
    );
  };

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
            <h1 className="text-3xl font-bold">Predictive Analytics - AI Oracle</h1>
            <p className="text-gray-600">Geleceği görün: No-show, talep, şikayet tahminleri</p>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <Card className="bg-red-50 border-red-200">
          <CardContent className="pt-6 text-center">
            <AlertTriangle className="w-10 h-10 text-red-600 mx-auto mb-2" />
            <p className="text-3xl font-bold">{noShowPredictions.filter(p => p.risk_level === 'high').length}</p>
            <p className="text-sm text-gray-600">Yüksek Risk No-show</p>
          </CardContent>
        </Card>
        <Card className="bg-yellow-50 border-yellow-200">
          <CardContent className="pt-6 text-center">
            <Target className="w-10 h-10 text-yellow-600 mx-auto mb-2" />
            <p className="text-3xl font-bold">{noShowPredictions.length}</p>
            <p className="text-sm text-gray-600">Toplam Risk</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="pt-6 text-center">
            <TrendingUp className="w-10 h-10 text-blue-600 mx-auto mb-2" />
            <p className="text-3xl font-bold">
              {demandForecast.filter(d => d.demand_level === 'very_high').length}
            </p>
            <p className="text-sm text-gray-600">Yüksek Talep Gün</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200">
          <CardContent className="pt-6 text-center">
            <Calendar className="w-10 h-10 text-green-600 mx-auto mb-2" />
            <p className="text-3xl font-bold">30</p>
            <p className="text-sm text-gray-600">Günlük Tahmin</p>
          </CardContent>
        </Card>
      </div>

      {/* No-Show Predictions */}
      <Card className="mb-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>No-Show Risk Tahminleri</CardTitle>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-2 border rounded-lg"
            />
          </div>
        </CardHeader>
        <CardContent>
          {noShowPredictions.length === 0 ? (
            <div className="text-center py-8">
              <CheckCircle className="w-16 h-16 text-green-400 mx-auto mb-4" />
              <p className="text-gray-600">Bugün için yüksek risk no-show yok.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {noShowPredictions.map((pred, idx) => (
                <div key={idx} className="p-4 bg-gray-50 rounded-lg border-l-4 border-amber-500">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <p className="font-bold">Booking #{pred.booking_id.substring(0, 8).toUpperCase()}</p>
                      <p className="text-sm text-gray-600">Risk: %{Math.round(pred.risk_score * 100)}</p>
                    </div>
                    <RiskBadge level={pred.risk_level} />
                  </div>
                  <div className="mt-3">
                    <p className="text-sm font-semibold text-amber-600">
                      {pred.recommended_action}
                    </p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {pred.factors?.map((factor, i) => (
                        <Badge key={i} variant="outline" className="text-xs">
                          {factor}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Demand Forecast */}
      <Card>
        <CardHeader>
          <CardTitle>30 Günlük Talep Tahmini</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-2">
            {demandForecast.slice(0, 14).map((forecast, idx) => (
              <div 
                key={idx} 
                className={`p-3 rounded-lg text-center ${
                  forecast.demand_level === 'very_high' ? 'bg-red-100' :
                  forecast.demand_level === 'high' ? 'bg-amber-100' :
                  forecast.demand_level === 'medium' ? 'bg-yellow-100' :
                  'bg-green-100'
                }`}
              >
                <p className="text-xs text-gray-600">{forecast.day_of_week.substring(0, 3)}</p>
                <p className="text-lg font-bold">{forecast.occupancy_forecast}%</p>
                <p className="text-xs font-semibold">€{forecast.recommended_price}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 p-4 bg-sky-50 rounded-lg">
            <p className="text-sm text-sky-800 flex items-start gap-1.5">
              <Lightbulb className="w-4 h-4 mt-0.5 shrink-0 text-amber-500" />
              <span><strong>AI Recommendation:</strong> Peak demand days detected. Consider increasing rates by 15-20%.</span>
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default PredictiveAnalytics;