import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import MaybeLayout from '@/components/MaybeLayout';
import axios from 'axios';
import { useTranslation } from 'react-i18next';

const BACKEND = "";

export default function CentralPricingManager({ user, tenant, onLogout, embedded = false }) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('rates');
  const [rates, setRates] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [history, setHistory] = useState([]);
  const [bulkForm, setBulkForm] = useState({ room_type: 'Standard', new_rate: '', adjustment_type: 'fixed', effective_from: new Date().toISOString().split('T')[0] });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [ratesRes, templatesRes, historyRes] = await Promise.all([
        axios.get(`/central-pricing/rates`, { headers }),
        axios.get(`/central-pricing/rate-templates`, { headers }),
        axios.get(`/central-pricing/rate-history`, { headers })
      ]);
      setRates(ratesRes.data);
      setTemplates(templatesRes.data.templates || []);
      setHistory(historyRes.data.history || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => { fetchData(); }, []);

  const handleBulkUpdate = async () => {
    if (!bulkForm.new_rate) return;
    try {
      const res = await axios.post(`/central-pricing/bulk-update`, {
        ...bulkForm,
        new_rate: parseFloat(bulkForm.new_rate)
      }, { headers });
      setMessage(`${res.data.total_updated} otelde fiyat güncellendi`);
      fetchData();
    } catch (e) { setMessage(e.response?.data?.detail || 'Hata'); }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Merkezi Fiyat Yönetimi</h1>
            <p className="text-gray-500">Zincir genelinde fiyat push ve bulk güncelleme</p>
          </div>
          <Button variant="outline" onClick={fetchData} disabled={loading}>
            {loading ? 'Yükleniyor...' : 'Yenile'}
          </Button>
        </div>

        {message && <div className="p-3 bg-blue-50 rounded-lg text-blue-700">{message}</div>}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="rates">Güncel Fiyatlar</TabsTrigger>
            <TabsTrigger value="bulk">Toplu Güncelleme</TabsTrigger>
            <TabsTrigger value="templates">Sablonlar</TabsTrigger>
            <TabsTrigger value="history">Fiyat Geçmişi</TabsTrigger>
          </TabsList>

          <TabsContent value="rates" className="space-y-4">
            {rates?.properties?.map((prop, i) => (
              <Card key={i}>
                <CardHeader>
                  <CardTitle className="text-lg">{prop.property_name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {prop.room_rates?.map((rt, j) => (
                      <div key={j} className="p-3 border rounded">
                        <p className="font-medium">{rt.room_type}</p>
                        <p className="text-2xl font-bold">{rt.base_rate?.toLocaleString('tr-TR')} TRY</p>
                        <p className="text-sm text-gray-500">{rt.count} oda</p>
                      </div>
                    ))}
                    {(!prop.room_rates || prop.room_rates.length === 0) && (
                      <p className="text-gray-400 col-span-4">Fiyat bilgisi bulunamadı</p>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </TabsContent>

          <TabsContent value="bulk" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Toplu Fiyat Güncelleme</CardTitle>
                <CardDescription>Tüm otellerde seçilen oda tipi için fiyat degisikligi yapin</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium">Oda Tipi</label>
                    <Input value={bulkForm.room_type} onChange={(e) => setBulkForm({...bulkForm, room_type: e.target.value})} />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Yeni Fiyat (TRY)</label>
                    <Input type="number" value={bulkForm.new_rate} onChange={(e) => setBulkForm({...bulkForm, new_rate: e.target.value})} />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Güncelleme Tipi</label>
                    <select className="w-full border rounded px-3 py-2" value={bulkForm.adjustment_type} onChange={(e) => setBulkForm({...bulkForm, adjustment_type: e.target.value})}>
                      <option value="fixed">Sabit Fiyat</option>
                      <option value="percentage">Yuzde Degisim</option>
                      <option value="increment">Artis/Azalis</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-sm font-medium">Gecerlilik Tarihi</label>
                    <Input type="date" value={bulkForm.effective_from} onChange={(e) => setBulkForm({...bulkForm, effective_from: e.target.value})} />
                  </div>
                </div>
                <Button onClick={handleBulkUpdate} className="w-full">Tüm Otellere Uygula</Button>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="templates" className="space-y-4">
            <Card>
              <CardHeader><CardTitle>Fiyat Sablonlari</CardTitle></CardHeader>
              <CardContent>
                {templates.length === 0 ? (
                  <p className="text-center py-8 text-gray-400">Henüz sablon olusturulmamis</p>
                ) : (
                  <div className="space-y-3">
                    {templates.map((t, i) => (
                      <div key={i} className="p-4 border rounded">
                        <p className="font-medium">{t.name}</p>
                        <p className="text-sm text-gray-500">{t.description}</p>
                        <div className="flex gap-2 mt-2">
                          {t.rates && Object.entries(t.rates).map(([k, v]) => (
                            <Badge key={k}>{k}: {v} TRY</Badge>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="history" className="space-y-4">
            <Card>
              <CardHeader><CardTitle>Fiyat Degisiklik Geçmişi</CardTitle></CardHeader>
              <CardContent>
                {history.length === 0 ? (
                  <p className="text-center py-8 text-gray-400">Fiyat geçmişi bulunamadı</p>
                ) : (
                  <div className="space-y-2">
                    {history.map((h, i) => (
                      <div key={i} className="flex justify-between p-3 bg-gray-50 rounded">
                        <div>
                          <span className="font-medium">{h.room_type}</span>
                          <span className="text-gray-500 ml-2">{h.new_rate?.toLocaleString('tr-TR')} {h.currency}</span>
                        </div>
                        <span className="text-sm text-gray-400">{h.updated_at ? new Date(h.updated_at).toLocaleString('tr-TR') : ''}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </MaybeLayout>
  );
}
