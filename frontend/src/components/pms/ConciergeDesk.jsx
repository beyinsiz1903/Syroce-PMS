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
import {
  MapPin, Car, Utensils, Ticket, Clock, Plus, CheckCircle,
  AlertCircle, Package, Key, Coffee, Bell, Search
} from 'lucide-react';

const REQUEST_TYPES = [
  { value: 'restaurant', label: 'Restoran Rezervasyonu', icon: Utensils },
  { value: 'transfer', label: 'Transfer / Ulasim', icon: Car },
  { value: 'tour', label: 'Tur / Gezi', icon: MapPin },
  { value: 'ticket', label: 'Bilet (Konser/Etkinlik)', icon: Ticket },
  { value: 'spa', label: 'Spa Randevusu', icon: Coffee },
  { value: 'valet', label: 'Vale Parking', icon: Car },
  { value: 'parcel', label: 'Paket / Kargo', icon: Package },
  { value: 'deposit_box', label: 'Kasa Kiralama', icon: Key },
  { value: 'wakeup', label: 'Uyandirma Servisi', icon: Bell },
  { value: 'other', label: 'Diger Talep', icon: AlertCircle },
];

const STATUS_COLORS = {
  pending: 'bg-yellow-100 text-yellow-800',
  in_progress: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  confirmed: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-red-100 text-red-800',
};

const ConciergeDesk = () => {
  const [requests, setRequests] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const [activeType, setActiveType] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [newReq, setNewReq] = useState({
    type: '', room_number: '', guest_name: '', details: '',
    date: '', time: '', pax: '', notes: '', priority: 'normal'
  });

  useEffect(() => { loadRequests(); }, []);

  const loadRequests = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/concierge/requests');
      setRequests(res.data.requests || []);
    } catch (err) {
      toast.error('Concierge talepleri yuklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const createRequest = async () => {
    if (!newReq.type || !newReq.room_number) return;
    try {
      const res = await axios.post('/concierge/requests', newReq);
      setRequests(prev => [res.data, ...prev]);
      toast.success('Talep olusturuldu');
      setNewReq({ type: '', room_number: '', guest_name: '', details: '', date: '', time: '', pax: '', notes: '', priority: 'normal' });
      setShowNew(false);
    } catch {
      toast.error('Talep olusturulamadi');
    }
  };

  const updateStatus = async (id, status) => {
    try {
      await axios.patch(`/concierge/requests/${id}`, { status });
      setRequests(prev => prev.map(r => r.id === id ? { ...r, status } : r));
      toast.success(`Talep durumu: ${status === 'completed' ? 'Tamamlandi' : status === 'in_progress' ? 'Islemde' : status === 'cancelled' ? 'Iptal' : status}`);
    } catch {
      toast.error('Durum guncellenemedi');
    }
  };

  const filtered = requests.filter(r => {
    if (activeType !== 'all' && r.type !== activeType) return false;
    if (searchTerm && !r.guest_name?.toLowerCase().includes(searchTerm.toLowerCase()) && !r.room_number?.includes(searchTerm)) return false;
    return true;
  });

  const stats = {
    total: requests.length,
    pending: requests.filter(r => r.status === 'pending').length,
    in_progress: requests.filter(r => r.status === 'in_progress').length,
    completed: requests.filter(r => r.status === 'completed').length,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <MapPin className="h-5 w-5" /> Concierge Masasi
        </h2>
        <Button onClick={() => setShowNew(true)}><Plus className="h-4 w-4 mr-1" /> Yeni Talep</Button>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <Card className="cursor-pointer" onClick={() => setActiveType('all')}>
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold">{stats.total}</div>
            <div className="text-xs text-muted-foreground">Toplam</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer border-yellow-200" onClick={() => setActiveType('all')}>
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-yellow-600">{stats.pending}</div>
            <div className="text-xs text-muted-foreground">Bekleyen</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer border-blue-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.in_progress}</div>
            <div className="text-xs text-muted-foreground">Islemde</div>
          </CardContent>
        </Card>
        <Card className="cursor-pointer border-green-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-green-600">{stats.completed}</div>
            <div className="text-xs text-muted-foreground">Tamamlanan</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-2 flex-wrap">
        <Button size="sm" variant={activeType === 'all' ? 'default' : 'outline'} onClick={() => setActiveType('all')}>Tumu</Button>
        {REQUEST_TYPES.map(t => (
          <Button key={t.value} size="sm" variant={activeType === t.value ? 'default' : 'outline'} onClick={() => setActiveType(t.value)}>
            <t.icon className="h-3 w-3 mr-1" />{t.label}
          </Button>
        ))}
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Misafir adi veya oda no ile ara..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
      </div>

      <div className="space-y-2">
        {loading && <p className="text-center text-muted-foreground py-4">Yukleniyor...</p>}
        {!loading && filtered.length === 0 && <p className="text-center text-muted-foreground py-8">Talep bulunamadi</p>}
        {filtered.map(req => {
          const typeInfo = REQUEST_TYPES.find(t => t.value === req.type);
          const Icon = typeInfo?.icon || AlertCircle;
          return (
            <Card key={req.id}>
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-muted"><Icon className="h-4 w-4" /></div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{req.guest_name}</span>
                        <Badge variant="outline">Oda {req.room_number}</Badge>
                        {req.priority === 'vip' && <Badge className="bg-purple-100 text-purple-800">VIP</Badge>}
                        {req.priority === 'high' && <Badge className="bg-red-100 text-red-800">Oncelikli</Badge>}
                      </div>
                      <p className="text-sm text-muted-foreground">{typeInfo?.label}: {req.details}</p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
                        <Clock className="h-3 w-3" />{req.date} {req.time}
                        {req.pax > 1 && <span>• {req.pax} kisi</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={STATUS_COLORS[req.status] || ''}>
                      {req.status === 'pending' ? 'Bekliyor' : req.status === 'in_progress' ? 'Islemde' : req.status === 'completed' ? 'Tamamlandi' : req.status === 'confirmed' ? 'Onaylandi' : 'Iptal'}
                    </Badge>
                    {req.status === 'pending' && (
                      <Button size="sm" variant="outline" onClick={() => updateStatus(req.id, 'in_progress')}>Basla</Button>
                    )}
                    {(req.status === 'pending' || req.status === 'in_progress') && (
                      <Button size="sm" onClick={() => updateStatus(req.id, 'completed')}>
                        <CheckCircle className="h-3 w-3 mr-1" />Tamam
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Dialog open={showNew} onOpenChange={setShowNew}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Yeni Concierge Talebi</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Talep Tipi</Label>
                <Select value={newReq.type} onValueChange={v => setNewReq(p => ({ ...p, type: v }))}>
                  <SelectTrigger><SelectValue placeholder="Tip secin..." /></SelectTrigger>
                  <SelectContent>{REQUEST_TYPES.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div>
                <Label>Oncelik</Label>
                <Select value={newReq.priority} onValueChange={v => setNewReq(p => ({ ...p, priority: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="high">Yuksek</SelectItem>
                    <SelectItem value="vip">VIP</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Oda No</Label><Input value={newReq.room_number} onChange={e => setNewReq(p => ({ ...p, room_number: e.target.value }))} /></div>
              <div><Label>Misafir Adi</Label><Input value={newReq.guest_name} onChange={e => setNewReq(p => ({ ...p, guest_name: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Tarih</Label><Input type="date" value={newReq.date} onChange={e => setNewReq(p => ({ ...p, date: e.target.value }))} /></div>
              <div><Label>Saat</Label><Input type="time" value={newReq.time} onChange={e => setNewReq(p => ({ ...p, time: e.target.value }))} /></div>
              <div><Label>Kisi</Label><Input type="number" min="1" value={newReq.pax} onChange={e => setNewReq(p => ({ ...p, pax: e.target.value }))} /></div>
            </div>
            <div><Label>Detaylar</Label><Textarea value={newReq.details} onChange={e => setNewReq(p => ({ ...p, details: e.target.value }))} placeholder="Restoran adi, adres, arac tipi..." /></div>
            <div><Label>Notlar</Label><Input value={newReq.notes} onChange={e => setNewReq(p => ({ ...p, notes: e.target.value }))} placeholder="Ek bilgiler..." /></div>
            <Button className="w-full" onClick={createRequest}>Talep Olustur</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ConciergeDesk;
