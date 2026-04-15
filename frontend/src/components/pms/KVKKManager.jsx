import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Shield, CheckCircle, Database, UserX
} from 'lucide-react';

const RETENTION_POLICIES = [
  { category: 'Misafir Kimlik Bilgileri', retention: '10 yıl', legal_basis: 'Yasal Zorunluluk (KBS)', status: 'active' },
  { category: 'Folyo / Fatura Bilgileri', retention: '10 yıl', legal_basis: 'Vergi Mevzuatı', status: 'active' },
  { category: 'İletişim Bilgileri', retention: '3 yıl', legal_basis: 'Açık Rıza / Meşru Menfaat', status: 'active' },
  { category: 'Tercihler & Notlar', retention: '5 yıl', legal_basis: 'Meşru Menfaat', status: 'active' },
  { category: 'Kamera Kayıtları', retention: '30 gün', legal_basis: 'Güvenlik', status: 'active' },
  { category: 'Pazarlama İzinleri', retention: 'İptal Edilene Kadar', legal_basis: 'Açık Rıza', status: 'active' },
  { category: 'Şikâyet Kayıtları', retention: '5 yıl', legal_basis: 'Yasal Zorunluluk', status: 'active' },
  { category: 'Çalışma Kayıtları', retention: '15 yıl', legal_basis: 'İş Mevzuatı', status: 'active' },
];

const KVKKManager = () => {
  const [activeTab, setActiveTab] = useState('policies');
  const [requests, setRequests] = useState([]);
  const [showNewRequest, setShowNewRequest] = useState(false);
  const [newRequest, setNewRequest] = useState({ guest_name: '', type: '', details: '' });
  const [consents, setConsents] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [reqRes, consentRes, auditRes] = await Promise.allSettled([
        axios.get('/kvkk/requests'),
        axios.get('/kvkk/consents'),
        axios.get('/kvkk/audit-log'),
      ]);
      if (reqRes.status === 'fulfilled') setRequests(reqRes.value.data.requests || []);
      if (consentRes.status === 'fulfilled') setConsents(consentRes.value.data.consents || []);
      if (auditRes.status === 'fulfilled') setAuditLogs(auditRes.value.data.logs || []);
    } catch {
      toast.error('KVKK verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const createRequest = async () => {
    if (!newRequest.guest_name || !newRequest.type) return;
    try {
      const res = await axios.post('/kvkk/requests', newRequest);
      setRequests(prev => [res.data, ...prev]);
      setNewRequest({ guest_name: '', type: '', details: '' });
      setShowNewRequest(false);
      toast.success('KVKK talebi oluşturuldu');
    } catch {
      toast.error('Talep oluşturulamadı');
    }
  };

  const completeRequest = async (id) => {
    try {
      await axios.patch(`/kvkk/requests/${id}`, { status: 'completed' });
      setRequests(prev => prev.map(r => r.id === id ? { ...r, status: 'completed', response_date: new Date().toISOString().split('T')[0] } : r));
      toast.success('Talep tamamlandı');
    } catch {
      toast.error('Talep tamamlanamadı');
    }
  };

  const typeLabel = (t) => t === 'access' ? 'Erişim' : t === 'erasure' ? 'Silme' : t === 'rectification' ? 'Düzeltme' : t === 'portability' ? 'Taşınabilirlik' : t === 'objection' ? 'İtiraz' : t;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Shield className="h-5 w-5" /> KVKK / GDPR Veri Yönetimi
        </h2>
        <Button onClick={() => setShowNewRequest(true)}>Yeni Talep</Button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{requests.length}</div><div className="text-xs text-muted-foreground">Toplam Talep</div></CardContent></Card>
        <Card className="border-yellow-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-yellow-600">{requests.filter(r => r.status === 'pending').length}</div><div className="text-xs text-muted-foreground">Bekleyen</div></CardContent></Card>
        <Card className="border-green-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-green-600">{requests.filter(r => r.status === 'completed').length}</div><div className="text-xs text-muted-foreground">Tamamlanan</div></CardContent></Card>
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{RETENTION_POLICIES.length}</div><div className="text-xs text-muted-foreground">Saklama Politikası</div></CardContent></Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="policies">Saklama Politikaları</TabsTrigger>
          <TabsTrigger value="requests">Veri Talepleri ({requests.length})</TabsTrigger>
          <TabsTrigger value="consents">Rıza Yönetimi ({consents.length})</TabsTrigger>
          <TabsTrigger value="audit">Denetim İzi ({auditLogs.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="policies">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted"><tr><th className="p-3 text-left">Veri Kategorisi</th><th className="p-3 text-left">Saklama Süresi</th><th className="p-3 text-left">Hukuki Dayanak</th><th className="p-3 text-left">Durum</th></tr></thead>
                  <tbody>
                    {RETENTION_POLICIES.map((p, i) => (
                      <tr key={i} className="border-t">
                        <td className="p-3 font-medium">{p.category}</td>
                        <td className="p-3"><Badge variant="outline">{p.retention}</Badge></td>
                        <td className="p-3 text-muted-foreground">{p.legal_basis}</td>
                        <td className="p-3"><Badge className="bg-green-100 text-green-800">Aktif</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="requests" className="space-y-2">
          {loading && <p className="text-center text-muted-foreground py-4">Yükleniyor...</p>}
          {!loading && requests.length === 0 && <p className="text-center text-muted-foreground py-8">Henüz veri talebi yok</p>}
          {requests.map(req => (
            <Card key={req.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{req.guest_name}</span>
                    <Badge variant="outline">{typeLabel(req.type)}</Badge>
                    <Badge variant={req.status === 'completed' ? 'default' : req.status === 'pending' ? 'secondary' : 'outline'}>
                      {req.status === 'completed' ? 'Tamamlandı' : req.status === 'pending' ? 'Bekliyor' : 'İşlemde'}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{req.details}</p>
                  <div className="text-xs text-muted-foreground">Talep: {req.date} {req.response_date ? `| Yanıt: ${req.response_date}` : '| 30 gün içinde yanıtlanmalı'}</div>
                </div>
                {req.status !== 'completed' && (
                  <Button size="sm" onClick={() => completeRequest(req.id)}><CheckCircle className="h-3 w-3 mr-1" />Tamamla</Button>
                )}
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="consents">
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-muted"><tr><th className="p-3 text-left">Misafir</th><th className="p-3 text-center">E-posta</th><th className="p-3 text-center">SMS</th><th className="p-3 text-center">Veri Paylaşımı</th><th className="p-3 text-left">Tarih</th></tr></thead>
                <tbody>
                  {consents.length === 0 && <tr><td colSpan="5" className="p-4 text-center text-muted-foreground">Henüz rıza kaydı yok</td></tr>}
                  {consents.map(c => (
                    <tr key={c.id} className="border-t">
                      <td className="p-3 font-medium">{c.guest_name}</td>
                      <td className="p-3 text-center">{c.email_marketing ? <CheckCircle className="h-4 w-4 text-green-500 mx-auto" /> : <UserX className="h-4 w-4 text-red-400 mx-auto" />}</td>
                      <td className="p-3 text-center">{c.sms_marketing ? <CheckCircle className="h-4 w-4 text-green-500 mx-auto" /> : <UserX className="h-4 w-4 text-red-400 mx-auto" />}</td>
                      <td className="p-3 text-center">{c.data_sharing ? <CheckCircle className="h-4 w-4 text-green-500 mx-auto" /> : <UserX className="h-4 w-4 text-red-400 mx-auto" />}</td>
                      <td className="p-3 text-muted-foreground">{c.date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit">
          <Card>
            <CardContent className="p-4">
              <div className="space-y-3">
                {auditLogs.length === 0 && <p className="text-center text-muted-foreground py-4">Henüz denetim izi yok</p>}
                {auditLogs.map((log) => (
                  <div key={log.id} className="flex items-center justify-between border-b pb-2 last:border-0">
                    <div>
                      <div className="flex items-center gap-2">
                        <Database className="h-3 w-3 text-muted-foreground" />
                        <span className="text-sm font-medium">{log.action}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">Kullanıcı: {log.user} | Hedef: {log.target}</div>
                    </div>
                    <div className="text-xs text-muted-foreground">{log.timestamp ? new Date(log.timestamp).toLocaleString('tr-TR') : ''}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={showNewRequest} onOpenChange={setShowNewRequest}>
        <DialogContent>
          <DialogHeader><DialogTitle>Yeni KVKK Talebi</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Misafir Adı</Label><Input value={newRequest.guest_name} onChange={e => setNewRequest(p => ({ ...p, guest_name: e.target.value }))} /></div>
            <div><Label>Talep Tipi</Label>
              <Select value={newRequest.type} onValueChange={v => setNewRequest(p => ({ ...p, type: v }))}>
                <SelectTrigger><SelectValue placeholder="Talep tipi..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="access">Erişim Hakkı (Verilerimi Göster)</SelectItem>
                  <SelectItem value="erasure">Silme Hakkı (Unutulma)</SelectItem>
                  <SelectItem value="rectification">Düzeltme Hakkı</SelectItem>
                  <SelectItem value="portability">Taşınabilirlik</SelectItem>
                  <SelectItem value="objection">İtiraz Hakkı</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div><Label>Detaylar</Label><Textarea value={newRequest.details} onChange={e => setNewRequest(p => ({ ...p, details: e.target.value }))} placeholder="Talep detayları..." /></div>
            <Button className="w-full" onClick={createRequest}>Talep Oluştur</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KVKKManager;
