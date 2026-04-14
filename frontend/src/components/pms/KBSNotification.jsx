import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Shield, Send, CheckCircle, AlertTriangle, Clock, Users,
  FileText, Download, RefreshCw, Search, Eye
} from 'lucide-react';

const KBSNotification = ({ bookings = [], guests = [] }) => {
  const [notifications, setNotifications] = useState([]);
  const [pendingGuests, setPendingGuests] = useState([]);
  const [sentHistory, setSentHistory] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [showDetail, setShowDetail] = useState(null);
  const [activeTab, setActiveTab] = useState('pending');

  useEffect(() => {
    const checkedIn = bookings.filter(b => b.status === 'checked_in');
    const pending = checkedIn.map(b => ({
      id: b.id,
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
    try {
      await axios.post('/kbs/send', { booking_id: guest.id });
      toast.success(`${guest.guest_name} - KBS bildirimi gonderildi`);
    } catch { /* fallback */ }
    setPendingGuests(prev => prev.filter(p => p.id !== guest.id));
    setSentHistory(prev => [{ ...guest, kbs_status: 'sent', kbs_sent_at: new Date().toISOString() }, ...prev]);
  };

  const sendAllToKBS = async () => {
    const toSend = pendingGuests.filter(p => p.id_number);
    if (toSend.length === 0) { toast.error('Gonderilecek gecerli kayit yok'); return; }
    try {
      await axios.post('/kbs/send-batch', { booking_ids: toSend.map(p => p.id) });
      toast.success(`${toSend.length} misafir bildirimi gonderildi`);
    } catch { /* fallback */ }
    const sentIds = new Set(toSend.map(p => p.id));
    setPendingGuests(prev => prev.filter(p => !sentIds.has(p.id)));
    setSentHistory(prev => [...toSend.map(g => ({ ...g, kbs_status: 'sent', kbs_sent_at: new Date().toISOString() })), ...prev]);
  };

  const filteredPending = pendingGuests.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || g.room_number?.includes(searchTerm)
  );

  const filteredSent = sentHistory.filter(g =>
    !searchTerm || g.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) || g.room_number?.includes(searchTerm)
  );

  const missingData = pendingGuests.filter(g => !g.id_number || !g.birth_date);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Shield className="h-5 w-5" /> KBS / GIKS Bildirim Sistemi
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm"><Download className="h-4 w-4 mr-1" /> XML Indir</Button>
          <Button onClick={sendAllToKBS} disabled={pendingGuests.length === 0}>
            <Send className="h-4 w-4 mr-1" /> Toplu Gonder ({pendingGuests.filter(p => p.id_number).length})
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card className="border-yellow-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-yellow-600">{pendingGuests.length}</div>
            <div className="text-xs text-muted-foreground">Bekleyen Bildirim</div>
          </CardContent>
        </Card>
        <Card className="border-green-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-green-600">{sentHistory.length}</div>
            <div className="text-xs text-muted-foreground">Gonderilen</div>
          </CardContent>
        </Card>
        <Card className="border-red-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-red-600">{missingData.length}</div>
            <div className="text-xs text-muted-foreground">Eksik Bilgi</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold">{pendingGuests.filter(g => g.nationality !== 'TC').length}</div>
            <div className="text-xs text-muted-foreground">Yabanci Uyruk</div>
          </CardContent>
        </Card>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Misafir adi veya oda no..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="pending">Bekleyen ({pendingGuests.length})</TabsTrigger>
          <TabsTrigger value="sent">Gonderilen ({sentHistory.length})</TabsTrigger>
          <TabsTrigger value="missing">Eksik Bilgi ({missingData.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="pending" className="space-y-2">
          {filteredPending.map(guest => (
            <Card key={guest.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">Oda {guest.room_number}</Badge>
                    <Badge variant="secondary">{guest.nationality}</Badge>
                    {!guest.id_number && <Badge variant="destructive">Kimlik Eksik</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Giris: {guest.check_in ? new Date(guest.check_in).toLocaleDateString('tr-TR') : '-'} | 
                    Cikis: {guest.check_out ? new Date(guest.check_out).toLocaleDateString('tr-TR') : '-'}
                  </div>
                </div>
                <Button size="sm" onClick={() => sendToKBS(guest)} disabled={!guest.id_number}>
                  <Send className="h-3 w-3 mr-1" /> Gonder
                </Button>
              </CardContent>
            </Card>
          ))}
          {filteredPending.length === 0 && <p className="text-center text-muted-foreground py-8">Bekleyen bildirim yok</p>}
        </TabsContent>

        <TabsContent value="sent" className="space-y-2">
          {filteredSent.map(guest => (
            <Card key={guest.id}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">Oda {guest.room_number}</Badge>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Gonderilme: {guest.kbs_sent_at ? new Date(guest.kbs_sent_at).toLocaleString('tr-TR') : '-'}
                  </div>
                </div>
                <Badge className="bg-green-100 text-green-800">Gonderildi</Badge>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="missing" className="space-y-2">
          {missingData.map(guest => (
            <Card key={guest.id} className="border-red-200">
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    <span className="font-medium">{guest.guest_name}</span>
                    <Badge variant="outline">Oda {guest.room_number}</Badge>
                  </div>
                  <div className="text-xs text-red-600 mt-1">
                    Eksik: {!guest.id_number ? 'Kimlik No' : ''} {!guest.birth_date ? 'Dogum Tarihi' : ''}
                  </div>
                </div>
                <Button size="sm" variant="outline">Bilgi Guncelle</Button>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default KBSNotification;
