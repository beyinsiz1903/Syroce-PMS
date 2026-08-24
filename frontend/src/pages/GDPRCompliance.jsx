import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
const BACKEND = "";
const headers = {};
export default function GDPRCompliance({
  user,
  tenant,
  onLogout
}) {
  const {
    t
  } = useTranslation();
  const [activeTab, setActiveTab] = useState('dashboard');
  const [complianceStatus, setComplianceStatus] = useState(null);
  const [retentionPolicy, setRetentionPolicy] = useState(null);
  const [dpas, setDPAs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [retentionForm, setRetentionForm] = useState(null);
  const [retentionPreview, setRetentionPreview] = useState(null);
  const [dpaForm, setDPAForm] = useState({
    processor_name: '',
    purpose: '',
    retention_period_days: 365,
    status: 'draft'
  });
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, policyRes, dpaRes] = await Promise.all([axios.get(`/gdpr/compliance-status`, {
        headers
      }), axios.get(`/gdpr/retention-policy`, {
        headers
      }), axios.get(`/gdpr/dpa`, {
        headers
      })]);
      setComplianceStatus(statusRes.data);
      setRetentionPolicy(policyRes.data);
      setRetentionForm({
        guest_data_retention_days: statusRes.data ? policyRes.data.guest_data_retention_days : 730,
        booking_data_retention_days: policyRes.data.booking_data_retention_days,
        audit_log_retention_days: policyRes.data.audit_log_retention_days,
        marketing_consent_retention_days: policyRes.data.marketing_consent_retention_days || 365,
        auto_anonymize: Boolean(policyRes.data.auto_anonymize)
      });
      setDPAs(dpaRes.data.agreements || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }, []);
  const saveRetentionPolicy = async () => {
    if (!retentionForm) return;
    setLoading(true);
    setMessage('');
    try {
      const response = await axios.put('/gdpr/retention-policy', retentionForm, { headers });
      setRetentionPolicy(response.data);
      setRetentionForm(response.data);
      setMessage('Veri saklama politikası kaydedildi ve denetim kaydı oluşturuldu.');
      await fetchData();
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Veri saklama politikası kaydedilemedi.');
    } finally {
      setLoading(false);
    }
  };
  const createDPA = async () => {
    if (!dpaForm.processor_name.trim() || !dpaForm.purpose.trim()) {
      setMessage('Veri işleyen adı ve işleme amacı zorunludur.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      await axios.post('/gdpr/dpa', {
        ...dpaForm,
        retention_period_days: Number(dpaForm.retention_period_days)
      }, { headers });
      setDPAForm({ processor_name: '', purpose: '', retention_period_days: 365, status: 'draft' });
      setMessage('Veri işleme sözleşmesi kaydedildi.');
      await fetchData();
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Veri işleme sözleşmesi kaydedilemedi.');
    } finally {
      setLoading(false);
    }
  };
  const previewRetention = async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await axios.post('/gdpr/retention/run', { dry_run: true, limit: 500 }, { headers });
      setRetentionPreview(response.data);
      setMessage('Saklama politikası etkisi güvenli biçimde önizlendi; veri değiştirilmedi.');
    } catch (error) {
      setMessage(error.response?.data?.detail || 'Saklama politikası önizlenemedi.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [fetchData]);
  const cs = complianceStatus;
  return <>
      <div className="p-6 space-y-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">KVKK/GDPR Uyumluluk</h1>
            <p className="text-gray-500">Veri koruma, onay yönetimi, veri silme/export/anonimize</p>
          </div>
          <Button variant="outline" onClick={fetchData} disabled={loading}>
            {loading ? 'Yükleniyor...' : 'Yenile'}
          </Button>
        </div>

        {message && <div className="p-3 bg-blue-50 rounded-lg text-blue-700">{message}</div>}

        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="dashboard">Uyumluluk Paneli</TabsTrigger>
            <TabsTrigger value="retention">Veri Saklama</TabsTrigger>
            <TabsTrigger value="dpa">Veri İşleme Sözleşmeleri</TabsTrigger>
          </TabsList>

          <TabsContent value="dashboard" className="space-y-4">
            {cs && <>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <Card>
                    <CardContent className="pt-6">
                      <div className="text-center">
                        <div className="text-4xl font-bold text-blue-600">%{cs.compliance_score}</div>
                        <p className="text-sm text-gray-500 mt-1">Uyumluluk Skoru</p>
                        <Progress value={cs.compliance_score} className="mt-2" />
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6 text-center">
                      <div className="text-3xl font-bold">{cs.total_guests}</div>
                      <p className="text-sm text-gray-500">Toplam Misafir</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6 text-center">
                      <div className="text-3xl font-bold text-green-600">{cs.guests_with_consent}</div>
                      <p className="text-sm text-gray-500">Onaylı Misafir</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6 text-center">
                      <div className="text-3xl font-bold text-amber-600">{cs.anonymized_guests}</div>
                      <p className="text-sm text-gray-500">Anonimleştirilmiş</p>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle>Uyumluluk Kontrolleri</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {cs.compliance_checks && Object.entries(cs.compliance_checks).map(([key, val]) => <div key={key} className="flex items-center gap-2 p-2 rounded border">
                          <span className={`w-3 h-3 rounded-full ${val ? 'bg-green-500' : 'bg-red-500'}`} />
                          <span className="text-sm">{key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                        </div>)}
                    </div>
                  </CardContent>
                </Card>

                {cs.recommendations?.length > 0 && <Card>
                    <CardHeader><CardTitle>Öneriler</CardTitle></CardHeader>
                    <CardContent>
                      <ul className="space-y-2">
                        {cs.recommendations.map((r, i) => <li key={r.id || i} className="flex items-center gap-2 text-sm">
                            <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" /> {r}
                          </li>)}
                      </ul>
                    </CardContent>
                  </Card>}

                {cs.recent_actions?.length > 0 && <Card>
                    <CardHeader><CardTitle>Son KVKK İşlemleri</CardTitle></CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {cs.recent_actions.map((a, i) => <div key={a.id || i} className="flex justify-between p-2 bg-gray-50 rounded text-sm">
                            <span>{a.action}</span>
                            <span className="text-gray-400">{a.timestamp ? new Date(a.timestamp).toLocaleString('tr-TR') : ''}</span>
                          </div>)}
                      </div>
                    </CardContent>
                  </Card>}
              </>}
          </TabsContent>

          <TabsContent value="retention" className="space-y-4">
            {retentionPolicy && retentionForm && <Card>
                <CardHeader>
                  <CardTitle>Veri Saklama Politikası</CardTitle>
                  <CardDescription>Her veri kategorisi için saklama süresini gün cinsinden yönetin.</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="p-4 border rounded">
                        <p className="font-medium">Misafir Verileri</p>
                        <Input type="number" min="30" max="3650" value={retentionForm.guest_data_retention_days} onChange={event => setRetentionForm({ ...retentionForm, guest_data_retention_days: Number(event.target.value) })} className="mt-2" />
                        <p className="text-sm text-gray-500 mt-1">{Math.round(retentionForm.guest_data_retention_days / 365)} yıl</p>
                      </div>
                      <div className="p-4 border rounded">
                        <p className="font-medium">Rezervasyon/Finansal</p>
                        <Input type="number" min="365" max="3650" value={retentionForm.booking_data_retention_days} onChange={event => setRetentionForm({ ...retentionForm, booking_data_retention_days: Number(event.target.value) })} className="mt-2" />
                        <p className="text-sm text-gray-500 mt-1">{Math.round(retentionForm.booking_data_retention_days / 365)} yıl</p>
                      </div>
                      <div className="p-4 border rounded">
                        <p className="font-medium">Denetim Logları</p>
                        <Input type="number" min="365" max="3650" value={retentionForm.audit_log_retention_days} onChange={event => setRetentionForm({ ...retentionForm, audit_log_retention_days: Number(event.target.value) })} className="mt-2" />
                        <p className="text-sm text-gray-500 mt-1">{Math.round(retentionForm.audit_log_retention_days / 365)} yıl</p>
                      </div>
                      <div className="p-4 border rounded">
                        <p className="font-medium">Pazarlama Onayları</p>
                        <Input type="number" min="30" max="3650" value={retentionForm.marketing_consent_retention_days} onChange={event => setRetentionForm({ ...retentionForm, marketing_consent_retention_days: Number(event.target.value) })} className="mt-2" />
                        <label className="flex items-center gap-2 mt-3 text-sm">
                          <input type="checkbox" checked={retentionForm.auto_anonymize} onChange={event => setRetentionForm({ ...retentionForm, auto_anonymize: event.target.checked })} />
                          Süresi dolan misafir PII verilerini otomatik anonimleştirmeye hazırla
                        </label>
                      </div>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button variant="outline" onClick={previewRetention} disabled={loading}>Etkiyi Önizle</Button>
                      <Button onClick={saveRetentionPolicy} disabled={loading}>Politikayı Kaydet</Button>
                    </div>
                    {retentionPreview && <div className="grid grid-cols-2 md:grid-cols-4 gap-3 rounded-lg border bg-gray-50 p-4 text-sm">
                        <div><span className="block text-gray-500">Eski kayıt adayı</span><strong>{retentionPreview.candidate_count}</strong></div>
                        <div><span className="block text-gray-500">Uygun misafir</span><strong>{retentionPreview.eligible_count}</strong></div>
                        <div><span className="block text-gray-500">Yeni konaklama nedeniyle korunan</span><strong>{retentionPreview.skipped_recent}</strong></div>
                        <div><span className="block text-gray-500">Kesim tarihi</span><strong>{new Date(retentionPreview.cutoff).toLocaleDateString('tr-TR')}</strong></div>
                      </div>}
                    <p className="text-xs text-gray-500">Önizleme veri değiştirmez. Otomatik anonimleştirme etkinse günlük güvenli süpürme yalnız süresi dolmuş ve daha yeni konaklaması bulunmayan misafir PII alanlarını anonimleştirir; finansal rezervasyon kayıtlarını korur.</p>
                  </div>
                </CardContent>
              </Card>}
          </TabsContent>

          <TabsContent value="dpa" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Veri İşleme Sözleşmeleri (DPA)</CardTitle>
                <CardDescription>Üçüncü parti veri işleyicileri ile yapılan sözleşmeler</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6 p-4 border rounded-lg bg-gray-50">
                  <div>
                    <label className="text-sm font-medium">Veri İşleyen</label>
                    <Input value={dpaForm.processor_name} onChange={event => setDPAForm({ ...dpaForm, processor_name: event.target.value })} placeholder="Örn. mesajlaşma sağlayıcısı" />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Saklama Süresi (gün)</label>
                    <Input type="number" min="1" max="3650" value={dpaForm.retention_period_days} onChange={event => setDPAForm({ ...dpaForm, retention_period_days: event.target.value })} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-sm font-medium">İşleme Amacı</label>
                    <Input value={dpaForm.purpose} onChange={event => setDPAForm({ ...dpaForm, purpose: event.target.value })} placeholder="İşlenen veri ve hizmet amacı" />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Durum</label>
                    <select className="w-full border rounded px-3 py-2" value={dpaForm.status} onChange={event => setDPAForm({ ...dpaForm, status: event.target.value })}>
                      <option value="draft">Taslak</option>
                      <option value="active">Aktif</option>
                    </select>
                  </div>
                  <div className="flex items-end justify-end"><Button onClick={createDPA} disabled={loading}>Sözleşme Kaydı Ekle</Button></div>
                </div>
                {dpas.length === 0 ? <p className="text-center py-8 text-gray-400">Henüz sözleşme eklenmemiş</p> : <div className="space-y-3">
                    {dpas.map((dpa, i) => <div key={dpa.id || i} className="p-4 border rounded">
                        <div className="flex justify-between">
                          <p className="font-medium">{dpa.processor_name}</p>
                          <Badge>{dpa.status}</Badge>
                        </div>
                        <p className="text-sm text-gray-600 mt-1">{dpa.purpose}</p>
                        <p className="text-sm text-gray-400">Saklama: {dpa.retention_period_days} gün</p>
                      </div>)}
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </>;
}
