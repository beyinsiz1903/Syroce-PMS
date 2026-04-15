import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Shield, Send, CheckCircle, AlertTriangle, Clock,
  Download, Search, UserCog
} from 'lucide-react';

const escapeXml = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');

const KBSNotification = ({ bookings = [], guests = [] }) => {
  const [pendingGuests, setPendingGuests] = useState([]);
  const [sentHistory, setSentHistory] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState('pending');
  const [sending, setSending] = useState(false);
  const [editDialog, setEditDialog] = useState(null);
  const [editForm, setEditForm] = useState({ id_number: '', birth_date: '' });

  useEffect(() => {
    const checkedIn = bookings.filter(b => b.status === 'checked_in');
    const pending = checkedIn.map(b => ({
      id: b.id,
      guest_id: b.guest_id || b.guestId || b.id,
      guest_name: b.guest_name || b.guestName || 'Bilinmiyor',
      room_number: b.room_number || b.roomNumber || '-',
      check_in: b.check_in || b.checkIn,
      check_out: b.check_out || b.checkOut,
      nationality: b.guest_nationality || b.nationality || 'TC',
      id_type: b.id_type || 'tc_kimlik',
      id_number: b.id_number || '',
      birth_date: b.birth_date || '',
      kbs_status: b.kbs_status || 'pending',
      kbs_sent_at: b.kbs_sent_at || null,
    }));
    setPendingGuests(pending.filter(p => p.kbs_status === 'pending'));
    setSentHistory(pending.filter(p => p.kbs_status !== 'pending'));
  }, [bookings]);

  const sendToKBS = async (guest) => {
    setSending(true);
    try {
      const res = await axios.post('/kbs/send', {
        booking_id: guest.id,
        guest_data: {
          guest_name: guest.guest_name,
          nationality: guest.nationality,
          id_number: guest.id_number,
        }
      });
      toast.success(`${guest.guest_name} - KBS bildirimi gönderildi (Ref: ${res.data.kbs_reference})`);
      setPendingGuests(prev => prev.filter(p => p.id !== guest.id));
      setSentHistory(prev => [{
        ...guest,
        kbs_status: 'sent',
        kbs_sent_at: res.data.sent_at,
        kbs_reference: res.data.kbs_reference,
      }, ...prev]);
    } catch {
      toast.error('KBS bildirimi gönderilemedi');
    } finally {
      setSending(false);
    }
  };

  const sendAllToKBS = async () => {
    const toSend = pendingGuests.filter(p => p.id_number);
    if (toSend.length === 0) {
      toast.error('Gönderilecek geçerli kayıt yok (kimlik no eksik)');
      return;
    }
    setSending(true);
    try {
      const res = await axios.post('/kbs/send-batch', { booking_ids: toSend.map(p => p.id) });
      toast.success(`${res.data.count} misafir bildirimi gönderildi`);
      const sentIds = new Set(toSend.map(p => p.id));
      const sentResults = res.data.results || [];
      setPendingGuests(prev => prev.filter(p => !sentIds.has(p.id)));
      setSentHistory(prev => [
        ...toSend.map(g => {
          const r = sentResults.find(sr => sr.booking_id === g.id);
          return { ...g, kbs_status: 'sent', kbs_sent_at: res.data.sent_at, kbs_reference: r?.kbs_reference || '' };
        }),
        ...prev
      ]);
    } catch {
      toast.error('Toplu gönderim başarısız');
    } finally {
      setSending(false);
    }
  };

  const downloadXML = () => {
    const xmlLines = ['<?xml version="1.0" encoding="UTF-8"?>', '<KBSBildirimler>'];
    pendingGuests.filter(g => g.id_number).forEach(g => {
      xmlLines.push('  <Misafir>');
      xmlLines.push(`    <AdSoyad>${escapeXml(g.guest_name)}</AdSoyad>`);
      xmlLines.push(`    <KimlikNo>${escapeXml(g.id_number)}</KimlikNo>`);
      xmlLines.push(`    <Uyruk>${escapeXml(g.nationality)}</Uyruk>`);
      xmlLines.push(`    <OdaNo>${escapeXml(g.room_number)}</OdaNo>`);
      xmlLines.push(`    <GirisTarihi>${escapeXml(g.check_in)}</GirisTarihi>`);
      xmlLines.push(`    <CikisTarihi>${escapeXml(g.check_out)}</CikisTarihi>`);
      xmlLines.push('  </Misafir>');
    });
    xmlLines.push('</KBSBildirimler>');
    const blob = new Blob([xmlLines.join('\n')], { type: 'application/xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `kbs_bildirim_${new Date().toISOString().split('T')[0]}.xml`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('XML dosyası indirildi');
  };

  const openEditDialog = (guest) => {
    setEditForm({ id_number: guest.id_number || '', birth_date: guest.birth_date || '' });
    setEditDialog(guest);
  };

  const saveGuestInfo = async () => {
    if (!editDialog) return;
    try {
      await axios.patch(`/pms/guests/${editDialog.guest_id}/preferences`, {
        id_number: editForm.id_number,
        birth_date: editForm.birth_date,
      });
      setPendingGuests(prev => prev.map(p =>
        p.id === editDialog.id ? { ...p, id_number: editForm.id_number, birth_date: editForm.birth_date } : p
      ));
      toast.success('Bilgiler güncellendi');
      setEditDialog(null);
    } catch {
      toast.error('Bilgi güncellenemedi');
    }
  };

  const filteredPending = pendingGuests.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || String(g.room_number).includes(searchTerm)
  );
  const filteredSent = sentHistory.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || String(g.room_number).includes(searchTerm)
  );
  const missingData = pendingGuests.filter(g => !g.id_number || !g.birth_date);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Shield className="h-5 w-5" /> KBS / GİKS Bildirim Sistemi
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={downloadXML} disabled={pendingGuests.filter(p => p.id_number).length === 0}>
            <Download className="h-4 w-4 mr-1" /> XML İndir
          </Button>
          <Button onClick={sendAllToKBS} disabled={pendingGuests.length === 0 || sending}>
            <Send className="h-4 w-4 mr-1" /> Toplu Gönder ({pendingGuests.filter(p => p.id_number).length})
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="bg-yellow-50 border-yellow-200">
          <CardContent className="p-3 text-center">
            <Clock className="w-5 h-5 mx-auto mb-1 text-yellow-600" />
            <p className="text-2xl font-bold text-yellow-700">{pendingGuests.length}</p>
            <p className="text-xs text-yellow-600">Bekleyen Bildirim</p>
          </CardContent>
        </Card>
        <Card className="bg-green-50 border-green-200">
          <CardContent className="p-3 text-center">
            <CheckCircle className="w-5 h-5 mx-auto mb-1 text-green-600" />
            <p className="text-2xl font-bold text-green-700">{sentHistory.length}</p>
            <p className="text-xs text-green-600">Gönderilen</p>
          </CardContent>
        </Card>
        <Card className="bg-red-50 border-red-200">
          <CardContent className="p-3 text-center">
            <AlertTriangle className="w-5 h-5 mx-auto mb-1 text-red-600" />
            <p className="text-2xl font-bold text-red-700">{missingData.length}</p>
            <p className="text-xs text-red-600">Eksik Bilgi</p>
          </CardContent>
        </Card>
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-3 text-center">
            <Shield className="w-5 h-5 mx-auto mb-1 text-blue-600" />
            <p className="text-2xl font-bold text-blue-700">{pendingGuests.filter(g => g.nationality !== 'TC').length}</p>
            <p className="text-xs text-blue-600">Yabancı Uyruk</p>
          </CardContent>
        </Card>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <Input className="pl-9" placeholder="Misafir adı veya oda no..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="pending">Bekleyen ({pendingGuests.length})</TabsTrigger>
          <TabsTrigger value="sent">Gönderilen ({sentHistory.length})</TabsTrigger>
          <TabsTrigger value="missing">Eksik Bilgi ({missingData.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="space-y-2">
          {filteredPending.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <Shield className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p>Bekleyen bildirim yok</p>
            </div>
          ) : filteredPending.map(guest => (
            <Card key={guest.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">Oda {guest.room_number}</Badge>
                    <Badge variant="secondary">{guest.nationality}</Badge>
                    {!guest.id_number && <Badge variant="destructive">Kimlik Eksik</Badge>}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Giriş: {guest.check_in ? new Date(guest.check_in).toLocaleDateString('tr-TR') : '-'} |
                    Çıkış: {guest.check_out ? new Date(guest.check_out).toLocaleDateString('tr-TR') : '-'}
                  </div>
                </div>
                <Button size="sm" onClick={() => sendToKBS(guest)} disabled={!guest.id_number || sending}>
                  <Send className="h-3 w-3 mr-1" /> Gönder
                </Button>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="sent" className="space-y-2">
          {filteredSent.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <CheckCircle className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p>Henüz gönderilmiş bildirim yok</p>
            </div>
          ) : filteredSent.map(guest => (
            <Card key={guest.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">Oda {guest.room_number}</Badge>
                    {guest.kbs_reference && <Badge variant="secondary">Ref: {guest.kbs_reference}</Badge>}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Gönderilme: {guest.kbs_sent_at ? new Date(guest.kbs_sent_at).toLocaleString('tr-TR') : '-'}
                  </div>
                </div>
                <Badge className="bg-green-100 text-green-800">Gönderildi</Badge>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="missing" className="space-y-2">
          {missingData.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <CheckCircle className="w-10 h-10 mx-auto mb-2 text-gray-300" />
              <p>Tüm misafir bilgileri tamam</p>
            </div>
          ) : missingData.map(guest => (
            <Card key={guest.id} className="border-red-200">
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">Oda {guest.room_number}</Badge>
                  </div>
                  <div className="text-xs text-red-600 mt-1">
                    Eksik: {!guest.id_number ? 'Kimlik No ' : ''}{!guest.birth_date ? 'Doğum Tarihi' : ''}
                  </div>
                </div>
                <Button size="sm" variant="outline" onClick={() => openEditDialog(guest)}>
                  <UserCog className="w-3.5 h-3.5 mr-1" /> Bilgi Güncelle
                </Button>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>

      <Dialog open={!!editDialog} onOpenChange={o => { if (!o) setEditDialog(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Misafir Bilgisi Güncelle</DialogTitle>
          </DialogHeader>
          {editDialog && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">{editDialog.guest_name} - Oda {editDialog.room_number}</p>
              <div>
                <Label>Kimlik Numarası</Label>
                <Input
                  value={editForm.id_number}
                  onChange={e => setEditForm({ ...editForm, id_number: e.target.value })}
                  placeholder="T.C. Kimlik veya Pasaport No"
                />
              </div>
              <div>
                <Label>Doğum Tarihi</Label>
                <Input
                  type="date"
                  value={editForm.birth_date}
                  onChange={e => setEditForm({ ...editForm, birth_date: e.target.value })}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setEditDialog(null)}>İptal</Button>
                <Button onClick={saveGuestInfo}>Kaydet</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default KBSNotification;
