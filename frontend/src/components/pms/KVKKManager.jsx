import { useState } from 'react';
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
  Shield, Trash2, Eye, FileText, Clock, CheckCircle, AlertTriangle,
  Search, Download, Lock, UserX, Database
} from 'lucide-react';

const RETENTION_POLICIES = [
  { category: 'Misafir Kimlik Bilgileri', retention: '10 yil', legal_basis: 'Yasal Zorunluluk (KBS)', status: 'active' },
  { category: 'Folyo / Fatura Bilgileri', retention: '10 yil', legal_basis: 'Vergi Mevzuati', status: 'active' },
  { category: 'Iletisim Bilgileri', retention: '3 yil', legal_basis: 'Acik Riza / Meşru Menfaat', status: 'active' },
  { category: 'Tercihler & Notlar', retention: '5 yil', legal_basis: 'Meşru Menfaat', status: 'active' },
  { category: 'Kamera Kayitlari', retention: '30 gun', legal_basis: 'Guvenlik', status: 'active' },
  { category: 'Pazarlama Izinleri', retention: 'Iptal Edilene Kadar', legal_basis: 'Acik Riza', status: 'active' },
  { category: 'Sikayet Kayitlari', retention: '5 yil', legal_basis: 'Yasal Zorunluluk', status: 'active' },
  { category: 'Calisma Kayitlari', retention: '15 yil', legal_basis: 'Is Mevzuati', status: 'active' },
];

const KVKKManager = () => {
  const [activeTab, setActiveTab] = useState('policies');
  const [requests, setRequests] = useState([
    { id: '1', guest_name: 'Ahmet Yilmaz', type: 'access', status: 'completed', date: '2026-04-10', response_date: '2026-04-12', details: 'Tum kisisel verilerin kopyasi talep edildi' },
    { id: '2', guest_name: 'Maria Garcia', type: 'erasure', status: 'pending', date: '2026-04-13', response_date: null, details: 'Pazarlama verilerinin silinmesi' },
    { id: '3', guest_name: 'John Smith', type: 'rectification', status: 'in_progress', date: '2026-04-12', response_date: null, details: 'Telefon numarasi duzeltmesi' },
  ]);
  const [showNewRequest, setShowNewRequest] = useState(false);
  const [newRequest, setNewRequest] = useState({ guest_name: '', type: '', details: '' });
  const [consents, setConsents] = useState([
    { id: '1', guest_name: 'Fatma Demir', email_marketing: true, sms_marketing: false, data_sharing: false, date: '2026-03-15' },
    { id: '2', guest_name: 'Mehmet Kaya', email_marketing: true, sms_marketing: true, data_sharing: true, date: '2026-02-20' },
    { id: '3', guest_name: 'Elena Petrova', email_marketing: false, sms_marketing: false, data_sharing: false, date: '2026-04-01' },
  ]);

  const createRequest = () => {
    if (!newRequest.guest_name || !newRequest.type) return;
    setRequests(prev => [{ id: Date.now().toString(), ...newRequest, status: 'pending', date: new Date().toISOString().split('T')[0], response_date: null }, ...prev]);
    setNewRequest({ guest_name: '', type: '', details: '' });
    setShowNewRequest(false);
    toast.success('KVKK talebi olusturuldu');
  };

  const completeRequest = (id) => {
    setRequests(prev => prev.map(r => r.id === id ? { ...r, status: 'completed', response_date: new Date().toISOString().split('T')[0] } : r));
    toast.success('Talep tamamlandi');
  };

  const typeLabel = (t) => t === 'access' ? 'Erisim' : t === 'erasure' ? 'Silme' : t === 'rectification' ? 'Duzeltme' : t === 'portability' ? 'Tasinabilirlik' : t === 'objection' ? 'Itiraz' : t;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Shield className="h-5 w-5" /> KVKK / GDPR Veri Yonetimi
        </h2>
        <Button onClick={() => setShowNewRequest(true)}>Yeni Talep</Button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{requests.length}</div><div className="text-xs text-muted-foreground">Toplam Talep</div></CardContent></Card>
        <Card className="border-yellow-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-yellow-600">{requests.filter(r => r.status === 'pending').length}</div><div className="text-xs text-muted-foreground">Bekleyen</div></CardContent></Card>
        <Card className="border-green-200"><CardContent className="p-3 text-center"><div className="text-2xl font-bold text-green-600">{requests.filter(r => r.status === 'completed').length}</div><div className="text-xs text-muted-foreground">Tamamlanan</div></CardContent></Card>
        <Card><CardContent className="p-3 text-center"><div className="text-2xl font-bold">{RETENTION_POLICIES.length}</div><div className="text-xs text-muted-foreground">Saklama Politikasi</div></CardContent></Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="policies">Saklama Politikalari</TabsTrigger>
          <TabsTrigger value="requests">Veri Talepleri ({requests.length})</TabsTrigger>
          <TabsTrigger value="consents">Riza Yonetimi</TabsTrigger>
          <TabsTrigger value="audit">Denetim Izi</TabsTrigger>
        </TabsList>

        <TabsContent value="policies">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted"><tr><th className="p-3 text-left">Veri Kategorisi</th><th className="p-3 text-left">Saklama Suresi</th><th className="p-3 text-left">Hukuki Dayanak</th><th className="p-3 text-left">Durum</th></tr></thead>
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
          {requests.map(req => (
            <Card key={req.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{req.guest_name}</span>
                    <Badge variant="outline">{typeLabel(req.type)}</Badge>
                    <Badge variant={req.status === 'completed' ? 'default' : req.status === 'pending' ? 'secondary' : 'outline'}>
                      {req.status === 'completed' ? 'Tamamlandi' : req.status === 'pending' ? 'Bekliyor' : 'Islemde'}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{req.details}</p>
                  <div className="text-xs text-muted-foreground">Talep: {req.date} {req.response_date ? `| Yanit: ${req.response_date}` : '| 30 gun icinde yanitlanmali'}</div>
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
                <thead className="bg-muted"><tr><th className="p-3 text-left">Misafir</th><th className="p-3 text-center">E-posta</th><th className="p-3 text-center">SMS</th><th className="p-3 text-center">Veri Paylasimi</th><th className="p-3 text-left">Tarih</th></tr></thead>
                <tbody>
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
                {[
                  { action: 'Misafir verisi goruntulendi', user: 'Ayse Kaya', target: 'Ahmet Yilmaz', time: '14:30', date: 'Bugun' },
                  { action: 'Folyo disa aktarildi (PDF)', user: 'Ali Demir', target: 'Maria Garcia', time: '13:15', date: 'Bugun' },
                  { action: 'Kimlik fotokopisi silindi', user: 'Sistem', target: 'John Brown', time: '02:00', date: 'Dun' },
                  { action: 'Riza formu guncellendi', user: 'Fatma Han', target: 'Elena Petrova', time: '11:45', date: 'Dun' },
                  { action: 'Toplu veri disa aktarimi', user: 'Admin', target: '150 misafir', time: '09:00', date: '2 gun once' },
                ].map((log, i) => (
                  <div key={i} className="flex items-center justify-between border-b pb-2 last:border-0">
                    <div>
                      <div className="flex items-center gap-2">
                        <Database className="h-3 w-3 text-muted-foreground" />
                        <span className="text-sm font-medium">{log.action}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">Kullanici: {log.user} | Hedef: {log.target}</div>
                    </div>
                    <div className="text-xs text-muted-foreground">{log.date} {log.time}</div>
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
            <div><Label>Misafir Adi</Label><Input value={newRequest.guest_name} onChange={e => setNewRequest(p => ({ ...p, guest_name: e.target.value }))} /></div>
            <div><Label>Talep Tipi</Label>
              <Select value={newRequest.type} onValueChange={v => setNewRequest(p => ({ ...p, type: v }))}>
                <SelectTrigger><SelectValue placeholder="Talep tipi..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="access">Erisim Hakki (Verilerimi Goster)</SelectItem>
                  <SelectItem value="erasure">Silme Hakki (Unutulma)</SelectItem>
                  <SelectItem value="rectification">Duzeltme Hakki</SelectItem>
                  <SelectItem value="portability">Tasinabilirlik</SelectItem>
                  <SelectItem value="objection">Itiraz Hakki</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div><Label>Detaylar</Label><Textarea value={newRequest.details} onChange={e => setNewRequest(p => ({ ...p, details: e.target.value }))} placeholder="Talep detaylari..." /></div>
            <Button className="w-full" onClick={createRequest}>Talep Olustur</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KVKKManager;
