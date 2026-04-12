import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import Layout from '@/components/Layout';
import axios from 'axios';
import { useTranslation } from 'react-i18next';

const BACKEND = "";

export default function MLDashboard({ user, tenant, onLogout }) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('status');
  const [modelsStatus, setModelsStatus] = useState(null);
  const [sentimentText, setSentimentText] = useState('');
  const [sentimentResult, setSentimentResult] = useState(null);
  const [trainingResult, setTrainingResult] = useState(null);
  const [predictionResult, setPredictionResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`/ml/models/status`, { headers });
      setModelsStatus(res.data.models);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchStatus(); }, []);

  const trainModel = async (type) => {
    setLoading(true); setTrainingResult(null);
    try {
      const res = await axios.post(`/ml/${type}/train`, {}, { headers });
      setTrainingResult({ type, ...res.data });
      setMessage(`${type} modeli basariyla egitildi!`);
      fetchStatus();
    } catch (e) {
      setTrainingResult({ type, error: e.response?.data?.detail || 'Hata' });
    }
    setLoading(false);
  };

  const analyzeSentiment = async () => {
    if (!sentimentText) return;
    try {
      const res = await axios.post(`/ml/sentiment/analyze?text=${encodeURIComponent(sentimentText)}`, {}, { headers });
      setSentimentResult(res.data);
    } catch (e) { console.error(e); }
  };

  const predictPrice = async () => {
    try {
      const res = await axios.post(`/ml/pricing/predict?room_type=Standard&channel=direct`, {}, { headers });
      setPredictionResult({ type: 'pricing', ...res.data });
    } catch (e) { setPredictionResult({ type: 'pricing', error: e.response?.data?.detail || 'Hata' }); }
  };

  const predictNoShow = async () => {
    try {
      const res = await axios.post(`/ml/noshow/predict?lead_days=7&channel=booking&nights=2`, {}, { headers });
      setPredictionResult({ type: 'noshow', ...res.data });
    } catch (e) { setPredictionResult({ type: 'noshow', error: e.response?.data?.detail || 'Hata' }); }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold">AI/ML Modelleri</h1>
          <p className="text-gray-500">Gercek ML model egitimi ve tahminleme</p>
        </div>

        {message && <div className="p-3 bg-green-50 rounded-lg text-green-700">{message}</div>}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="status">Model Durumu</TabsTrigger>
            <TabsTrigger value="training">Egitim</TabsTrigger>
            <TabsTrigger value="predict">Tahminleme</TabsTrigger>
            <TabsTrigger value="sentiment">Duygu Analizi</TabsTrigger>
          </TabsList>

          <TabsContent value="status" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {modelsStatus && Object.entries(modelsStatus).map(([key, val]) => (
                <Card key={key}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      {{pricing:'Fiyatlandirma',noshow:'No-Show Tahmini',upsell:'Upsell Skorlama',sentiment:'Duygu Analizi'}[key] || key}
                      <Badge className={val.in_memory_trained || val.ready ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}>
                        {val.in_memory_trained || val.ready ? 'Hazir' : 'Egitilmedi'}
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {val.db_record?.metrics && (
                      <div className="space-y-1 text-sm">
                        {Object.entries(val.db_record.metrics).map(([mk, mv]) => (
                          <div key={mk} className="flex justify-between">
                            <span className="text-gray-500">{mk}</span>
                            <span className="font-medium">{typeof mv === 'number' ? mv.toFixed(4) : String(mv)}</span>
                          </div>
                        ))}
                        <p className="text-xs text-gray-400 mt-2">Son egitim: {val.db_record?.trained_at ? new Date(val.db_record.trained_at).toLocaleString('tr-TR') : '-'}</p>
                      </div>
                    )}
                    {val.type && <p className="text-sm text-gray-500">Tip: {val.type}</p>}
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="training" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Model Egitimi</CardTitle>
                <CardDescription>Otel verilerinizle ML modelleri egitin</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Button onClick={() => trainModel('pricing')} disabled={loading} className="h-20">
                    <div className="text-center">
                      <p className="font-bold">Fiyatlandirma Modeli</p>
                      <p className="text-xs opacity-80">GradientBoosting</p>
                    </div>
                  </Button>
                  <Button onClick={() => trainModel('noshow')} disabled={loading} className="h-20" variant="outline">
                    <div className="text-center">
                      <p className="font-bold">No-Show Modeli</p>
                      <p className="text-xs opacity-80">RandomForest</p>
                    </div>
                  </Button>
                  <Button onClick={() => trainModel('upsell')} disabled={loading} className="h-20" variant="outline">
                    <div className="text-center">
                      <p className="font-bold">Upsell Modeli</p>
                      <p className="text-xs opacity-80">GradientBoosting</p>
                    </div>
                  </Button>
                </div>

                {trainingResult && (
                  <div className={`p-4 rounded-lg ${trainingResult.trained ? 'bg-green-50 border border-green-200' : 'bg-yellow-50 border border-yellow-200'}`}>
                    <p className="font-medium">{trainingResult.type} model egitim sonucu:</p>
                    {trainingResult.metrics ? (
                      <div className="mt-2 space-y-1 text-sm">
                        {Object.entries(trainingResult.metrics).map(([k, v]) => (
                          <div key={k} className="flex justify-between">
                            <span>{k}</span>
                            <span className="font-mono">{typeof v === 'object' ? JSON.stringify(v) : typeof v === 'number' ? v.toFixed(4) : String(v)}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-yellow-700 mt-1">{trainingResult.error || 'Yeterli veri yok'}</p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="predict" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardHeader><CardTitle>Fiyat Tahmini</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  <Button onClick={predictPrice} variant="outline">Fiyat Tahmin Et</Button>
                  {predictionResult?.type === 'pricing' && (
                    <div className="p-3 bg-blue-50 rounded">
                      {predictionResult.error ? (
                        <p className="text-red-500">{predictionResult.error}</p>
                      ) : (
                        <p className="text-2xl font-bold">{predictionResult.predicted_price?.toLocaleString('tr-TR')} TRY</p>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>No-Show Tahmini</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  <Button onClick={predictNoShow} variant="outline">No-Show Risk Analizi</Button>
                  {predictionResult?.type === 'noshow' && (
                    <div className="p-3 bg-blue-50 rounded space-y-2">
                      {predictionResult.error ? (
                        <p className="text-red-500">{predictionResult.error}</p>
                      ) : (
                        <>
                          <p className="text-2xl font-bold">%{(predictionResult.no_show_probability * 100).toFixed(1)}</p>
                          <Badge className={{
                            low: 'bg-green-100 text-green-700',
                            medium: 'bg-yellow-100 text-yellow-700',
                            high: 'bg-red-100 text-red-700'
                          }[predictionResult.risk_level]}>
                            {predictionResult.risk_level?.toUpperCase()} RISK
                          </Badge>
                          <p className="text-sm">{predictionResult.recommendation}</p>
                        </>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="sentiment" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>NLP Duygu Analizi</CardTitle>
                <CardDescription>Misafir yorumlarini analiz edin</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <Input value={sentimentText} onChange={(e) => setSentimentText(e.target.value)} placeholder="Analiz edilecek metin girin..." />
                  <Button onClick={analyzeSentiment}>Analiz Et</Button>
                </div>

                {sentimentResult && (
                  <div className="p-4 border rounded-lg">
                    <div className="flex items-center gap-3">
                      <span className="text-3xl">
                        {sentimentResult.sentiment === 'positive' ? '😊' : sentimentResult.sentiment === 'negative' ? '😞' : '😐'}
                      </span>
                      <div>
                        <Badge className={{
                          positive: 'bg-green-100 text-green-700',
                          negative: 'bg-red-100 text-red-700',
                          neutral: 'bg-gray-100 text-gray-700'
                        }[sentimentResult.sentiment]}>
                          {{positive:'Pozitif',negative:'Negatif',neutral:'Notr'}[sentimentResult.sentiment]}
                        </Badge>
                        <p className="text-sm text-gray-500 mt-1">Polarite: {sentimentResult.polarity} | Subjektivite: {sentimentResult.subjectivity}</p>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
