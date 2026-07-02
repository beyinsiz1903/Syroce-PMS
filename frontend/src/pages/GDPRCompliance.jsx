import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { AlertTriangle } from 'lucide-react';
import axios from 'axios';
import { useTranslation } from 'react-i18next';
const BACKEND = "";
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
  const token = localStorage.getItem('token');
  const headers = {
    Authorization: `Bearer ${token}`
  };
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
      setDPAs(dpaRes.data.agreements || []);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  useEffect(() => {
    fetchData();
  }, []);
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
            <TabsTrigger value="dpa">Veri Isleme Sozlesmeleri</TabsTrigger>
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
                      <p className="text-sm text-gray-500">Onayli Misafir</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-6 text-center">
                      <div className="text-3xl font-bold text-amber-600">{cs.anonymized_guests}</div>
                      <p className="text-sm text-gray-500">Anonimlestirilmis</p>
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
                    <CardHeader><CardTitle>Oneriler</CardTitle></CardHeader>
                    <CardContent>
                      <ul className="space-y-2">
                        {cs.recommendations.map((r, i) => <li key={r.id || i} className="flex items-center gap-2 text-sm">
                            <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" /> {r}
                          </li>)}
                      </ul>
                    </CardContent>
                  </Card>}

                {cs.recent_actions?.length > 0 && <Card>
                    <CardHeader><CardTitle>Son KVKK Islemleri</CardTitle></CardHeader>
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
            {retentionPolicy && <Card>
                <CardHeader>
                  <CardTitle>Veri Saklama Politikasi</CardTitle>
                  <CardDescription>Her veri kategorisi için saklama suresi</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="p-4 border rounded">
                        <p className="font-medium">Misafir Verileri</p>
                        <p className="text-2xl font-bold">{Math.round(retentionPolicy.guest_data_retention_days / 365)} yil</p>
                        <p className="text-sm text-gray-500">{retentionPolicy.guest_data_retention_days} gun</p>
                      </div>
                      <div className="p-4 border rounded">
                        <p className="font-medium">Rezervasyon/Finansal</p>
                        <p className="text-2xl font-bold">{Math.round(retentionPolicy.booking_data_retention_days / 365)} yil</p>
                        <p className="text-sm text-gray-500">{retentionPolicy.booking_data_retention_days} gun</p>
                      </div>
                      <div className="p-4 border rounded">
                        <p className="font-medium">Denetim Loglari</p>
                        <p className="text-2xl font-bold">{Math.round(retentionPolicy.audit_log_retention_days / 365)} yil</p>
                        <p className="text-sm text-gray-500">{retentionPolicy.audit_log_retention_days} gun</p>
                      </div>
                      <div className="p-4 border rounded">
                        <p className="font-medium">Otomatik Anonimize</p>
                        <Badge variant={retentionPolicy.auto_anonymize ? 'default' : 'outline'}>
                          {retentionPolicy.auto_anonymize ? 'Aktif' : 'Pasif'}
                        </Badge>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>}
          </TabsContent>

          <TabsContent value="dpa" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Veri Isleme Sozlesmeleri (DPA)</CardTitle>
                <CardDescription>Ucuncu parti veri isleyicileri ile yapilan sozlesmeler</CardDescription>
              </CardHeader>
              <CardContent>
                {dpas.length === 0 ? <p className="text-center py-8 text-gray-400">Henüz sozlesme eklenmemis</p> : <div className="space-y-3">
                    {dpas.map((dpa, i) => <div key={dpa.id || i} className="p-4 border rounded">
                        <div className="flex justify-between">
                          <p className="font-medium">{dpa.processor_name}</p>
                          <Badge>{dpa.status}</Badge>
                        </div>
                        <p className="text-sm text-gray-600 mt-1">{dpa.purpose}</p>
                        <p className="text-sm text-gray-400">Saklama: {dpa.retention_period_days} gun</p>
                      </div>)}
                  </div>}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </>;
}