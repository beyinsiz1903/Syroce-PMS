import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Loader2, Sparkles, User, Coffee, Search, CheckCircle, Bell, Clock } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import MaybeLayout from '@/components/MaybeLayout';

const GuestRelationsDashboard = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [directives, setDirectives] = useState([]);
  const [guestId, setGuestId] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [triggering, setTriggering] = useState(false);

  useEffect(() => {
    fetchDirectives();
  }, []);

  const fetchDirectives = async () => {
    try {
      setLoading(true);
      const res = await axios.get('/guest-relations/preparations/directives');
      setDirectives(res.data.directives || []);
    } catch (err) {
      console.error(err);
      toast.error(t('guestRelations.fetchError', 'Direktifler yüklenemedi.'));
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!guestId.trim()) {
      toast.error('Lütfen bir misafir ID veya rezervasyon numarası girin.');
      return;
    }
    
    setAnalyzing(true);
    setAnalysis(null);
    try {
      const res = await axios.get(`/guest-relations/profiles/${guestId}/analysis`);
      setAnalysis(res.data);
    } catch (err) {
      console.error(err);
      toast.error('Analiz başarısız. Misafir bulunamadı veya yetkiniz yok.');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleTriggerPreparations = async () => {
    try {
      setTriggering(true);
      const res = await axios.post('/guest-relations/preparations/trigger');
      toast.success(`${res.data.triggered_count} adet oda hazırlık direktifi tetiklendi!`);
      fetchDirectives();
    } catch (err) {
      console.error(err);
      toast.error('Direktifler tetiklenemedi.');
    } finally {
      setTriggering(false);
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="guest_relations">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-indigo-600" />
              Misafir İlişkileri (Akıllı Profil)
            </h1>
            <p className="text-sm text-gray-500 mt-1">Misafir tercihlerini öngörün ve oda hazırlık direktiflerini yönetin.</p>
          </div>
          <Button onClick={handleTriggerPreparations} disabled={triggering} className="gap-2 bg-indigo-600 hover:bg-indigo-700 text-white">
            {triggering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Bell className="w-4 h-4" />}
            Yaklaşan Check-in'ler İçin Direktif Tetikle
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Analysis Section */}
          <div className="lg:col-span-1 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Misafir Analizi</CardTitle>
                <CardDescription>Misafirin geçmiş harcama ve konaklama verilerini analiz edin.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <Input 
                    placeholder="Misafir ID girin..." 
                    value={guestId}
                    onChange={(e) => setGuestId(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                  />
                  <Button variant="secondary" onClick={handleAnalyze} disabled={analyzing}>
                    {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  </Button>
                </div>

                {analysis && (
                  <div className="mt-6 p-4 bg-indigo-50 rounded-xl border border-indigo-100 space-y-4">
                    <div className="flex items-center gap-3 border-b border-indigo-200 pb-3">
                      <div className="p-2 bg-indigo-100 rounded-full">
                        <User className="w-5 h-5 text-indigo-700" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-indigo-900">{analysis.guest_name}</p>
                        <p className="text-xs text-indigo-600">ID: {analysis.guest_id}</p>
                      </div>
                    </div>
                    
                    <div className="space-y-3">
                      <div>
                        <span className="text-xs font-semibold text-gray-500 uppercase">Yastık Tercihi</span>
                        <p className="text-sm font-medium text-gray-800">{analysis.pillow_preference}</p>
                      </div>
                      <div>
                        <span className="text-xs font-semibold text-gray-500 uppercase">SPA Tercihleri</span>
                        <p className="text-sm font-medium text-gray-800">{analysis.spa_preference}</p>
                      </div>
                      <div>
                        <span className="text-xs font-semibold text-gray-500 uppercase">Minibar Alışkanlığı</span>
                        <p className="text-sm font-medium text-gray-800 flex items-center gap-1">
                          <Coffee className="w-4 h-4 text-amber-600" />
                          {analysis.minibar_preference}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Directives List */}
          <div className="lg:col-span-2">
            <Card className="h-full">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-lg">Aktif Oda Hazırlık Direktifleri</CardTitle>
                  <CardDescription>Otomatik oluşturulmuş VIP set-up bildirimleri.</CardDescription>
                </div>
                <Button variant="outline" size="sm" onClick={fetchDirectives} disabled={loading}>
                  Yenile
                </Button>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                  </div>
                ) : directives.length === 0 ? (
                  <div className="text-center py-12 bg-gray-50 rounded-lg border border-dashed border-gray-200">
                    <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-3" />
                    <h3 className="text-sm font-medium text-gray-900">Tüm hazırlıklar tamam</h3>
                    <p className="text-xs text-gray-500 mt-1">Şu an için bekleyen direktif bulunmuyor.</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {directives.map((dir) => (
                      <div key={dir.id} className="flex flex-col md:flex-row md:items-center justify-between p-4 bg-white border rounded-xl hover:shadow-sm transition-all gap-4">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold">Oda {dir.room_id}</span>
                            <span className="text-sm font-medium text-gray-900">{dir.guest_name}</span>
                          </div>
                          <p className="text-sm text-gray-600">{dir.directives}</p>
                          <p className="text-xs text-gray-400 mt-2 flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Check-in: {new Date(dir.check_in_date).toLocaleDateString()}
                          </p>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                            dir.status === 'pending' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'
                          }`}>
                            {dir.status === 'pending' ? 'Bekliyor' : 'Hazır'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </MaybeLayout>
  );
};

export default GuestRelationsDashboard;
