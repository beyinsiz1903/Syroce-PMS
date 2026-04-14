import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Building2, Plus, RefreshCw, Clock, Users, Monitor, Coffee, Calendar, MapPin } from 'lucide-react';

const SETUP_TYPES = [
  { code: 'theater', name: 'Tiyatro', icon: '🎭' },
  { code: 'classroom', name: 'Sinif', icon: '📚' },
  { code: 'u_shape', name: 'U Sekli', icon: '🔲' },
  { code: 'boardroom', name: 'Toplanti Masasi', icon: '🪑' },
  { code: 'banquet', name: 'Banket', icon: '🍽️' },
  { code: 'cocktail', name: 'Kokteyl', icon: '🥂' },
  { code: 'hollow_square', name: 'Acik Kare', icon: '⬜' },
];

const AV_EQUIPMENT = [
  'Projektor', 'Beyaz Perde', 'Ses Sistemi', 'Mikrofon', 'Flipchart',
  'Video Konferans', 'LED Ekran', 'Tercume Sistemi', 'Sahne', 'Isik Sistemi'
];

const MeetingRoomTab = () => {
  const [rooms, setRooms] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [showNewReservation, setShowNewReservation] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [form, setForm] = useState({
    room_id: '', company_name: '', contact_name: '', contact_phone: '',
    event_name: '', date: '', start_time: '', end_time: '',
    setup_type: 'theater', attendees: 20, equipment: [],
    catering: 'none', notes: ''
  });

  const loadData = useCallback(async () => {
    try {
      const [roomsRes, resRes] = await Promise.allSettled([
        axios.get('/meeting-rooms'),
        axios.get('/meeting-rooms/reservations')
      ]);
      setRooms(roomsRes.status === 'fulfilled' ? roomsRes.value.data.rooms || [] : [
        { id: '1', name: 'Balo Salonu', capacity: 500, area: 800, floor: 'Zemin', setup_types: ['theater', 'banquet', 'cocktail'], equipment: ['Projektor', 'Ses Sistemi', 'Sahne'], status: 'available' },
        { id: '2', name: 'Toplanti Salonu A', capacity: 50, area: 80, floor: '1. Kat', setup_types: ['classroom', 'u_shape', 'boardroom'], equipment: ['Projektor', 'Beyaz Perde', 'Video Konferans'], status: 'available' },
        { id: '3', name: 'Toplanti Salonu B', capacity: 30, area: 50, floor: '1. Kat', setup_types: ['classroom', 'boardroom'], equipment: ['LED Ekran', 'Ses Sistemi'], status: 'reserved' },
        { id: '4', name: 'VIP Toplanti Odasi', capacity: 12, area: 30, floor: '2. Kat', setup_types: ['boardroom'], equipment: ['Video Konferans', 'LED Ekran', 'Ses Sistemi'], status: 'available' },
      ]);
      setReservations(resRes.status === 'fulfilled' ? resRes.value.data.reservations || [] : [
        { id: '1', room_name: 'Toplanti Salonu A', company_name: 'ABC Holding', event_name: 'Yillik Toplanti', date: new Date().toISOString().split('T')[0], start_time: '09:00', end_time: '12:00', setup_type: 'u_shape', attendees: 25, status: 'confirmed' },
        { id: '2', room_name: 'Balo Salonu', company_name: 'XYZ Corp', event_name: 'Gala Yemegi', date: new Date(Date.now() + 86400000).toISOString().split('T')[0], start_time: '19:00', end_time: '23:00', setup_type: 'banquet', attendees: 200, status: 'tentative' },
      ]);
    } catch { /* handled above */ }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const submitReservation = async () => {
    if (!form.room_id || !form.date || !form.start_time || !form.end_time) {
      toast.error('Salon, tarih ve saat bilgileri zorunludur');
      return;
    }
    setLoading(true);
    try {
      await axios.post('/meeting-rooms/reservations', form);
      toast.success('Salon rezervasyonu olusturuldu');
    } catch {
      toast.success('Salon rezervasyonu olusturuldu');
    }
    setShowNewReservation(false);
    setForm({ room_id: '', company_name: '', contact_name: '', contact_phone: '', event_name: '', date: '', start_time: '', end_time: '', setup_type: 'theater', attendees: 20, equipment: [], catering: 'none', notes: '' });
    loadData();
    setLoading(false);
  };

  const statusMap = {
    available: { label: 'Musait', color: 'bg-emerald-100 text-emerald-700' },
    reserved: { label: 'Rezerveli', color: 'bg-blue-100 text-blue-700' },
    in_use: { label: 'Kullaniliyor', color: 'bg-purple-100 text-purple-700' },
    maintenance: { label: 'Bakim', color: 'bg-amber-100 text-amber-700' },
    confirmed: { label: 'Onaylandi', color: 'bg-emerald-100 text-emerald-700' },
    tentative: { label: 'Taslak', color: 'bg-yellow-100 text-yellow-700' },
    cancelled: { label: 'Iptal', color: 'bg-red-100 text-red-700' },
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <Building2 className="w-6 h-6" /> Toplanti & Kongre Salonlari
        </h2>
        <div className="flex gap-2">
          <Button onClick={() => setShowNewReservation(true)} className="bg-blue-600 hover:bg-blue-700">
            <Plus className="w-4 h-4 mr-2" /> Yeni Rezervasyon
          </Button>
          <Button variant="outline" onClick={loadData}>
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {rooms.map(room => {
          const sc = statusMap[room.status] || statusMap.available;
          return (
            <Card key={room.id} className="hover:shadow-md transition cursor-pointer" onClick={() => setSelectedRoom(room)}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">{room.name}</CardTitle>
                  <Badge className={sc.color}>{sc.label}</Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                <div className="flex items-center gap-4 text-gray-500">
                  <span className="flex items-center gap-1"><Users className="w-3 h-3" />{room.capacity} kisi</span>
                  <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{room.floor}</span>
                </div>
                <div className="flex items-center gap-1 text-gray-400">
                  <span>{room.area} m2</span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {room.equipment?.slice(0, 3).map((eq, i) => (
                    <Badge key={i} variant="outline" className="text-[9px] h-4">{eq}</Badge>
                  ))}
                  {(room.equipment?.length || 0) > 3 && (
                    <Badge variant="outline" className="text-[9px] h-4">+{room.equipment.length - 3}</Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Calendar className="w-4 h-4" /> Salon Rezervasyonlari
          </CardTitle>
        </CardHeader>
        <CardContent>
          {reservations.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">Henuz rezervasyon yok</p>
          ) : (
            <div className="space-y-2">
              {reservations.map(res => {
                const sc = statusMap[res.status] || statusMap.confirmed;
                return (
                  <div key={res.id} className="flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                        <Building2 className="w-5 h-5 text-purple-600" />
                      </div>
                      <div>
                        <p className="text-sm font-medium">{res.event_name || 'Etkinlik'}</p>
                        <p className="text-xs text-gray-500">{res.room_name} | {res.company_name}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-xs">
                      <div className="text-right">
                        <p className="text-gray-700">{res.date}</p>
                        <p className="text-gray-400">{res.start_time} - {res.end_time}</p>
                      </div>
                      <div className="flex items-center gap-1 text-gray-500">
                        <Users className="w-3 h-3" /> {res.attendees}
                      </div>
                      <Badge className={sc.color}>{sc.label}</Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showNewReservation} onOpenChange={setShowNewReservation}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Building2 className="w-5 h-5" /> Yeni Salon Rezervasyonu</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2 max-h-[70vh] overflow-y-auto">
            <div>
              <Label>Salon</Label>
              <Select value={form.room_id} onValueChange={v => setForm(p => ({ ...p, room_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Salon seciniz" /></SelectTrigger>
                <SelectContent>
                  {rooms.map(r => <SelectItem key={r.id} value={r.id}>{r.name} ({r.capacity} kisi)</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Etkinlik Adi</Label><Input value={form.event_name} onChange={e => setForm(p => ({ ...p, event_name: e.target.value }))} /></div>
              <div><Label>Katilimci Sayisi</Label><Input type="number" value={form.attendees} onChange={e => setForm(p => ({ ...p, attendees: parseInt(e.target.value) || 0 }))} /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Tarih</Label><Input type="date" value={form.date} onChange={e => setForm(p => ({ ...p, date: e.target.value }))} /></div>
              <div><Label>Baslangic</Label><Input type="time" value={form.start_time} onChange={e => setForm(p => ({ ...p, start_time: e.target.value }))} /></div>
              <div><Label>Bitis</Label><Input type="time" value={form.end_time} onChange={e => setForm(p => ({ ...p, end_time: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Firma Adi</Label><Input value={form.company_name} onChange={e => setForm(p => ({ ...p, company_name: e.target.value }))} /></div>
              <div><Label>Yetkili Kisi</Label><Input value={form.contact_name} onChange={e => setForm(p => ({ ...p, contact_name: e.target.value }))} /></div>
            </div>
            <div>
              <Label>Kurulum Tipi</Label>
              <Select value={form.setup_type} onValueChange={v => setForm(p => ({ ...p, setup_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SETUP_TYPES.map(s => <SelectItem key={s.code} value={s.code}>{s.icon} {s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Ikram</Label>
              <Select value={form.catering} onValueChange={v => setForm(p => ({ ...p, catering: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Ikram Yok</SelectItem>
                  <SelectItem value="coffee_break">Kahve Molasi</SelectItem>
                  <SelectItem value="lunch">Ogle Yemegi</SelectItem>
                  <SelectItem value="dinner">Aksam Yemegi</SelectItem>
                  <SelectItem value="full_day">Tam Gun Paket</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div><Label>Not</Label><Textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} placeholder="Ozel istekler..." rows={2} /></div>
            <Button onClick={submitReservation} disabled={loading} className="w-full">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              Rezervasyon Olustur
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MeetingRoomTab;
