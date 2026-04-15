import { useState, useEffect, useCallback, useMemo } from 'react';
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
import { Building2, Plus, RefreshCw, Users, Calendar, MapPin, ChevronLeft, ChevronRight, CreditCard, Banknote, X } from 'lucide-react';

const SETUP_TYPES = [
  { code: 'theater', name: 'Tiyatro', icon: '🎭' },
  { code: 'classroom', name: 'Sinif', icon: '📚' },
  { code: 'u_shape', name: 'U Sekli', icon: '🔲' },
  { code: 'boardroom', name: 'Toplanti Masasi', icon: '🪑' },
  { code: 'banquet', name: 'Banket', icon: '🍽️' },
  { code: 'cocktail', name: 'Kokteyl', icon: '🥂' },
  { code: 'hollow_square', name: 'Acik Kare', icon: '⬜' },
];

const DEFAULT_EVENT_TYPES = [
  { code: 'meeting', name: 'Toplanti', icon: '📋' },
  { code: 'conference', name: 'Konferans', icon: '🎤' },
  { code: 'seminar', name: 'Seminer', icon: '🎓' },
  { code: 'cocktail_party', name: 'Kokteyl', icon: '🥂' },
  { code: 'ball', name: 'Balo', icon: '💃' },
  { code: 'wedding', name: 'Dugun', icon: '💒' },
  { code: 'circumcision', name: 'Sunnet', icon: '🎉' },
  { code: 'engagement', name: 'Nisan', icon: '💍' },
  { code: 'birthday', name: 'Dogum Gunu', icon: '🎂' },
  { code: 'yoga', name: 'Yoga', icon: '🧘' },
  { code: 'workshop', name: 'Workshop', icon: '🛠️' },
  { code: 'training', name: 'Egitim', icon: '📖' },
  { code: 'product_launch', name: 'Urun Lansmani', icon: '🚀' },
  { code: 'gala_dinner', name: 'Gala Yemegi', icon: '🍷' },
  { code: 'other', name: 'Diger', icon: '📌' },
];

const PAYMENT_METHODS = [
  { code: 'cash', name: 'Nakit', icon: '💵' },
  { code: 'credit_card', name: 'Kredi Karti', icon: '💳' },
  { code: 'bank_transfer', name: 'Havale/EFT', icon: '🏦' },
  { code: 'check', name: 'Cek', icon: '📝' },
];

const DAYS_TR = ['Pzt', 'Sal', 'Car', 'Per', 'Cum', 'Cmt', 'Paz'];
const MONTHS_TR = ['Ocak', 'Subat', 'Mart', 'Nisan', 'Mayis', 'Haziran', 'Temmuz', 'Agustos', 'Eylul', 'Ekim', 'Kasim', 'Aralik'];

const MeetingRoomTab = () => {
  const [rooms, setRooms] = useState([]);
  const [reservations, setReservations] = useState([]);
  const [showNewReservation, setShowNewReservation] = useState(false);
  const [loading, setLoading] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const d = new Date();
    return { year: d.getFullYear(), month: d.getMonth() };
  });
  const [selectedCalendarDate, setSelectedCalendarDate] = useState(null);
  const [eventTypes, setEventTypes] = useState(DEFAULT_EVENT_TYPES);
  const [showAddEventType, setShowAddEventType] = useState(false);
  const [newEventTypeName, setNewEventTypeName] = useState('');
  const [selectedReservation, setSelectedReservation] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [saving, setSaving] = useState(false);

  const emptyForm = {
    room_id: '', company_name: '', contact_name: '', contact_phone: '',
    event_name: '', event_type: 'meeting', date: '', start_time: '', end_time: '',
    setup_type: 'theater', attendees: 20, equipment: [],
    catering: 'none', notes: '',
    total_price: '', deposit_amount: '', deposit_paid: false,
    payment_method: '', payment_notes: ''
  };
  const [form, setForm] = useState(emptyForm);

  const loadData = useCallback(async () => {
    try {
      const [roomsRes, resRes] = await Promise.allSettled([
        axios.get('/meeting-rooms'),
        axios.get('/meeting-rooms/reservations')
      ]);
      setRooms(roomsRes.status === 'fulfilled' ? roomsRes.value.data.rooms || [] : []);
      setReservations(resRes.status === 'fulfilled' ? resRes.value.data.reservations || [] : []);
      if (roomsRes.status === 'rejected' || resRes.status === 'rejected') {
        toast.error('Toplanti salonu verileri yuklenemedi');
      }
    } catch {
      toast.error('Toplanti salonu verileri yuklenemedi');
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const submitReservation = async () => {
    if (!form.room_id || !form.date || !form.start_time || !form.end_time) {
      toast.error('Salon, tarih ve saat bilgileri zorunludur');
      return;
    }
    setLoading(true);
    try {
      const room = rooms.find(r => r.id === form.room_id);
      const payload = {
        ...form,
        room_name: room?.name || '',
        total_price: form.total_price ? parseFloat(form.total_price) : 0,
        deposit_amount: form.deposit_amount ? parseFloat(form.deposit_amount) : 0,
        attendees: parseInt(form.attendees) || 0,
      };
      await axios.post('/meeting-rooms/reservations', payload);
      toast.success('Salon rezervasyonu olusturuldu');
    } catch {
      toast.error('Salon rezervasyonu olusturulamadi');
    }
    setShowNewReservation(false);
    setForm(emptyForm);
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

  const reservationsByDate = useMemo(() => {
    const map = {};
    reservations.forEach(res => {
      if (!res.date) return;
      if (!map[res.date]) map[res.date] = [];
      map[res.date].push(res);
    });
    return map;
  }, [reservations]);

  const calendarDays = useMemo(() => {
    const { year, month } = calendarMonth;
    const firstDay = new Date(year, month, 1);
    let startWeekday = firstDay.getDay() - 1;
    if (startWeekday < 0) startWeekday = 6;
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    const days = [];
    for (let i = 0; i < startWeekday; i++) days.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const dayReservations = reservationsByDate[dateStr] || [];
      const roomsBooked = new Set(dayReservations.map(r => r.room_id));
      const roomsFree = rooms.filter(r => !roomsBooked.has(r.id));
      days.push({ day: d, dateStr, reservations: dayReservations, roomsFree, roomsBooked: roomsBooked.size });
    }
    return days;
  }, [calendarMonth, reservationsByDate, rooms]);

  const prevMonth = () => setCalendarMonth(p => p.month === 0 ? { year: p.year - 1, month: 11 } : { ...p, month: p.month - 1 });
  const nextMonth = () => setCalendarMonth(p => p.month === 11 ? { year: p.year + 1, month: 0 } : { ...p, month: p.month + 1 });

  const todayStr = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }, []);

  const selectedDateReservations = selectedCalendarDate ? (reservationsByDate[selectedCalendarDate] || []) : [];
  const selectedDateFreeRooms = useMemo(() => {
    if (!selectedCalendarDate) return rooms;
    const booked = new Set(selectedDateReservations.map(r => r.room_id));
    return rooms.filter(r => !booked.has(r.id));
  }, [selectedCalendarDate, selectedDateReservations, rooms]);

  const handleAddEventType = () => {
    const trimmed = newEventTypeName.trim();
    if (!trimmed) return;
    const code = trimmed.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
    if (eventTypes.find(e => e.code === code)) {
      toast.error('Bu etkinlik tipi zaten mevcut');
      return;
    }
    setEventTypes(prev => [...prev, { code, name: trimmed, icon: '📌' }]);
    setNewEventTypeName('');
    setShowAddEventType(false);
    toast.success(`"${trimmed}" etkinlik tipi eklendi`);
  };

  const handleOpenNewReservation = (dateStr) => {
    setForm({ ...emptyForm, date: dateStr || '' });
    setShowNewReservation(true);
  };

  const openReservationDetail = (res) => {
    setSelectedReservation(res);
    setEditForm({
      room_id: res.room_id || '',
      room_name: res.room_name || '',
      event_name: res.event_name || '',
      event_type: res.event_type || 'meeting',
      company_name: res.company_name || '',
      contact_name: res.contact_name || '',
      contact_phone: res.contact_phone || '',
      date: res.date || '',
      start_time: res.start_time || '',
      end_time: res.end_time || '',
      setup_type: res.setup_type || 'theater',
      attendees: res.attendees || 0,
      catering: res.catering || 'none',
      notes: res.notes || '',
      status: res.status || 'confirmed',
      total_price: res.total_price || '',
      deposit_amount: res.deposit_amount || '',
      deposit_paid: res.deposit_paid || false,
      payment_method: res.payment_method || '',
      payment_notes: res.payment_notes || '',
    });
  };

  const updateReservation = async () => {
    if (!selectedReservation || !editForm) return;
    setSaving(true);
    try {
      const room = rooms.find(r => r.id === editForm.room_id);
      const payload = {
        ...editForm,
        room_name: room?.name || editForm.room_name,
        total_price: editForm.total_price ? parseFloat(editForm.total_price) : 0,
        deposit_amount: editForm.deposit_amount ? parseFloat(editForm.deposit_amount) : 0,
        attendees: parseInt(editForm.attendees) || 0,
      };
      await axios.put(`/meeting-rooms/reservations/${selectedReservation.id}`, payload);
      toast.success('Rezervasyon guncellendi');
      setSelectedReservation(null);
      setEditForm(null);
      loadData();
    } catch {
      toast.error('Rezervasyon guncellenemedi');
    }
    setSaving(false);
  };

  const cancelReservation = async () => {
    if (!selectedReservation) return;
    setSaving(true);
    try {
      await axios.put(`/meeting-rooms/reservations/${selectedReservation.id}`, { status: 'cancelled' });
      toast.success('Rezervasyon iptal edildi');
      setSelectedReservation(null);
      setEditForm(null);
      loadData();
    } catch {
      toast.error('Iptal islemi basarisiz');
    }
    setSaving(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <Building2 className="w-6 h-6" /> Toplanti & Kongre Salonlari
        </h2>
        <div className="flex gap-2">
          <Button onClick={() => handleOpenNewReservation(null)} className="bg-blue-600 hover:bg-blue-700">
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
            <Card key={room.id} className="hover:shadow-md transition">
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
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <Calendar className="w-4 h-4" /> Salon Musaitlik Takvimi
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={prevMonth}><ChevronLeft className="w-4 h-4" /></Button>
              <span className="text-sm font-medium min-w-[120px] text-center">
                {MONTHS_TR[calendarMonth.month]} {calendarMonth.year}
              </span>
              <Button variant="ghost" size="sm" onClick={nextMonth}><ChevronRight className="w-4 h-4" /></Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-px bg-gray-200 rounded-lg overflow-hidden">
            {DAYS_TR.map(d => (
              <div key={d} className="bg-gray-50 text-center text-[10px] font-semibold text-gray-500 py-1.5">{d}</div>
            ))}
            {calendarDays.map((cell, i) => {
              if (!cell) return <div key={`empty-${i}`} className="bg-white min-h-[64px]" />;
              const isToday = cell.dateStr === todayStr;
              const isSelected = cell.dateStr === selectedCalendarDate;
              const hasEvents = cell.reservations.length > 0;
              const allBooked = rooms.length > 0 && cell.roomsFree.length === 0;
              return (
                <div
                  key={cell.dateStr}
                  onClick={() => setSelectedCalendarDate(cell.dateStr === selectedCalendarDate ? null : cell.dateStr)}
                  className={`bg-white min-h-[64px] p-1 cursor-pointer transition hover:bg-blue-50 ${isSelected ? 'ring-2 ring-blue-500 bg-blue-50' : ''} ${isToday ? 'bg-blue-50/50' : ''}`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-xs font-medium ${isToday ? 'bg-blue-600 text-white rounded-full w-5 h-5 flex items-center justify-center' : 'text-gray-700'}`}>
                      {cell.day}
                    </span>
                    {rooms.length > 0 && (
                      <span className={`text-[9px] px-1 rounded ${allBooked ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-600'}`}>
                        {cell.roomsFree.length}/{rooms.length}
                      </span>
                    )}
                  </div>
                  {hasEvents && (
                    <div className="mt-0.5 space-y-0.5">
                      {cell.reservations.slice(0, 2).map((res, ri) => (
                        <div key={ri} className="text-[8px] bg-purple-100 text-purple-700 rounded px-1 py-0.5 truncate">
                          {res.event_name || res.room_name}
                        </div>
                      ))}
                      {cell.reservations.length > 2 && (
                        <div className="text-[8px] text-gray-400 px-1">+{cell.reservations.length - 2} daha</div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="flex items-center gap-4 mt-3 text-[10px] text-gray-500">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-emerald-100 inline-block" /> Musait salon var</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-100 inline-block" /> Tum salonlar dolu</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-purple-100 inline-block" /> Etkinlik var</span>
          </div>

          {selectedCalendarDate && (
            <div className="mt-4 p-3 bg-gray-50 rounded-lg border">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold">{selectedCalendarDate} - Salon Durumu</h4>
                <Button size="sm" variant="outline" onClick={() => handleOpenNewReservation(selectedCalendarDate)}>
                  <Plus className="w-3 h-3 mr-1" /> Bu Gun Rezervasyon
                </Button>
              </div>
              {selectedDateFreeRooms.length > 0 && (
                <div className="mb-2">
                  <p className="text-xs text-gray-500 mb-1">Musait Salonlar:</p>
                  <div className="flex flex-wrap gap-1">
                    {selectedDateFreeRooms.map(r => (
                      <Badge key={r.id} className="bg-emerald-100 text-emerald-700 text-[10px]">{r.name} ({r.capacity} kisi)</Badge>
                    ))}
                  </div>
                </div>
              )}
              {selectedDateReservations.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">Rezervasyonlar:</p>
                  <div className="space-y-1">
                    {selectedDateReservations.map(res => {
                      const evType = eventTypes.find(e => e.code === res.event_type);
                      return (
                        <div key={res.id} onClick={() => openReservationDetail(res)} className="flex items-center justify-between p-2 bg-white rounded border text-xs cursor-pointer hover:bg-blue-50 transition">
                          <div className="flex items-center gap-2">
                            <span>{evType?.icon || '📋'}</span>
                            <span className="font-medium">{res.event_name}</span>
                            <span className="text-gray-400">|</span>
                            <span className="text-gray-500">{res.room_name}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="text-gray-500">{res.start_time} - {res.end_time}</span>
                            {res.total_price > 0 && (
                              <span className="text-emerald-600 font-medium">{Number(res.total_price).toLocaleString('tr-TR')} TL</span>
                            )}
                            {res.deposit_paid && <Badge className="bg-green-100 text-green-700 text-[9px]">Kapora Alindi</Badge>}
                            {!res.deposit_paid && res.deposit_amount > 0 && <Badge className="bg-amber-100 text-amber-700 text-[9px]">Kapora Bekliyor</Badge>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {selectedDateReservations.length === 0 && selectedDateFreeRooms.length === rooms.length && (
                <p className="text-xs text-gray-400">Bu tarihte henuz rezervasyon yok. Tum salonlar musait.</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

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
                const evType = eventTypes.find(e => e.code === res.event_type);
                return (
                  <div key={res.id} onClick={() => openReservationDetail(res)} className="flex items-center justify-between p-3 border rounded-lg hover:bg-blue-50 cursor-pointer transition">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center text-lg">
                        {evType?.icon || '📋'}
                      </div>
                      <div>
                        <p className="text-sm font-medium">{res.event_name || 'Etkinlik'}</p>
                        <p className="text-xs text-gray-500">{res.room_name} | {res.company_name} {evType ? `| ${evType.name}` : ''}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-xs">
                      {res.total_price > 0 && (
                        <div className="text-right">
                          <p className="text-sm font-semibold text-gray-800">{Number(res.total_price).toLocaleString('tr-TR')} TL</p>
                          {res.deposit_amount > 0 && (
                            <p className="text-[10px] text-gray-400">Kapora: {Number(res.deposit_amount).toLocaleString('tr-TR')} TL</p>
                          )}
                        </div>
                      )}
                      {res.deposit_paid && <Badge className="bg-green-100 text-green-700 text-[10px]">Kapora Alindi</Badge>}
                      {!res.deposit_paid && res.deposit_amount > 0 && <Badge className="bg-amber-100 text-amber-700 text-[10px]">Kapora Bekliyor</Badge>}
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
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Building2 className="w-5 h-5" /> Yeni Salon Rezervasyonu</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2 max-h-[75vh] overflow-y-auto pr-1">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Salon</Label>
                <Select value={form.room_id} onValueChange={v => setForm(p => ({ ...p, room_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Salon seciniz" /></SelectTrigger>
                  <SelectContent>
                    {rooms.map(r => <SelectItem key={r.id} value={r.id}>{r.name} ({r.capacity} kisi)</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <Label>Etkinlik Tipi</Label>
                  <Button variant="ghost" size="sm" className="h-5 text-[10px] text-blue-600 px-1" onClick={() => setShowAddEventType(true)}>
                    + Yeni Tip Ekle
                  </Button>
                </div>
                <Select value={form.event_type} onValueChange={v => setForm(p => ({ ...p, event_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {eventTypes.map(e => <SelectItem key={e.code} value={e.code}>{e.icon} {e.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div><Label>Etkinlik Adi</Label><Input value={form.event_name} onChange={e => setForm(p => ({ ...p, event_name: e.target.value }))} placeholder="Ornek: Yilmaz Dugun Organizasyonu" /></div>
              <div><Label>Katilimci Sayisi</Label><Input type="number" value={form.attendees} onChange={e => setForm(p => ({ ...p, attendees: parseInt(e.target.value) || 0 }))} /></div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div><Label>Tarih</Label><Input type="date" value={form.date} onChange={e => setForm(p => ({ ...p, date: e.target.value }))} /></div>
              <div><Label>Baslangic</Label><Input type="time" value={form.start_time} onChange={e => setForm(p => ({ ...p, start_time: e.target.value }))} /></div>
              <div><Label>Bitis</Label><Input type="time" value={form.end_time} onChange={e => setForm(p => ({ ...p, end_time: e.target.value }))} /></div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div><Label>Firma / Kisi Adi</Label><Input value={form.company_name} onChange={e => setForm(p => ({ ...p, company_name: e.target.value }))} /></div>
              <div><Label>Yetkili Kisi</Label><Input value={form.contact_name} onChange={e => setForm(p => ({ ...p, contact_name: e.target.value }))} /></div>
            </div>
            <div>
              <Label>Telefon</Label>
              <Input value={form.contact_phone} onChange={e => setForm(p => ({ ...p, contact_phone: e.target.value }))} placeholder="05XX XXX XX XX" />
            </div>

            <div className="grid grid-cols-2 gap-3">
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
            </div>

            <div className="border-t pt-4">
              <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                <CreditCard className="w-4 h-4" /> Ucret & Odeme Bilgileri
              </h4>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Toplam Ucret (TL)</Label>
                  <Input type="number" value={form.total_price} onChange={e => setForm(p => ({ ...p, total_price: e.target.value }))} placeholder="0" min="0" />
                </div>
                <div>
                  <Label>Kapora Tutari (TL)</Label>
                  <Input type="number" value={form.deposit_amount} onChange={e => setForm(p => ({ ...p, deposit_amount: e.target.value }))} placeholder="0" min="0" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-3">
                <div>
                  <Label>Kapora Durumu</Label>
                  <Select value={form.deposit_paid ? 'paid' : 'pending'} onValueChange={v => setForm(p => ({ ...p, deposit_paid: v === 'paid' }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pending">Henuz Alinmadi</SelectItem>
                      <SelectItem value="paid">Kapora Alindi</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Odeme Yontemi</Label>
                  <Select value={form.payment_method} onValueChange={v => setForm(p => ({ ...p, payment_method: v }))}>
                    <SelectTrigger><SelectValue placeholder="Seciniz" /></SelectTrigger>
                    <SelectContent>
                      {PAYMENT_METHODS.map(m => <SelectItem key={m.code} value={m.code}>{m.icon} {m.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="mt-3">
                <Label>Odeme Notu</Label>
                <Input value={form.payment_notes} onChange={e => setForm(p => ({ ...p, payment_notes: e.target.value }))} placeholder="Ornek: 2 taksit ile odenecek" />
              </div>
            </div>

            <div><Label>Not</Label><Textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} placeholder="Ozel istekler..." rows={2} /></div>

            <Button onClick={submitReservation} disabled={loading} className="w-full">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              Rezervasyon Olustur
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showAddEventType} onOpenChange={setShowAddEventType}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Yeni Etkinlik Tipi Ekle</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>Etkinlik Tipi Adi</Label>
              <Input
                value={newEventTypeName}
                onChange={e => setNewEventTypeName(e.target.value)}
                placeholder="Ornek: Baby Shower"
                onKeyDown={e => e.key === 'Enter' && handleAddEventType()}
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={handleAddEventType} className="flex-1">Ekle</Button>
              <Button variant="outline" onClick={() => { setShowAddEventType(false); setNewEventTypeName(''); }}>Iptal</Button>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-2">Mevcut Tipler:</p>
              <div className="flex flex-wrap gap-1">
                {eventTypes.map(e => (
                  <Badge key={e.code} variant="outline" className="text-[10px]">{e.icon} {e.name}</Badge>
                ))}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!selectedReservation} onOpenChange={v => { if (!v) { setSelectedReservation(null); setEditForm(null); } }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5" /> Rezervasyon Detayi
              {selectedReservation && (
                <Badge className={statusMap[selectedReservation.status]?.color || 'bg-gray-100'}>
                  {statusMap[selectedReservation.status]?.label || selectedReservation.status}
                </Badge>
              )}
            </DialogTitle>
          </DialogHeader>
          {editForm && (
            <div className="space-y-4 py-2 max-h-[75vh] overflow-y-auto pr-1">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Salon</Label>
                  <Select value={editForm.room_id} onValueChange={v => setEditForm(p => ({ ...p, room_id: v }))}>
                    <SelectTrigger><SelectValue placeholder="Salon seciniz" /></SelectTrigger>
                    <SelectContent>
                      {rooms.map(r => <SelectItem key={r.id} value={r.id}>{r.name} ({r.capacity} kisi)</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Etkinlik Tipi</Label>
                  <Select value={editForm.event_type} onValueChange={v => setEditForm(p => ({ ...p, event_type: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {eventTypes.map(e => <SelectItem key={e.code} value={e.code}>{e.icon} {e.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div><Label>Etkinlik Adi</Label><Input value={editForm.event_name} onChange={e => setEditForm(p => ({ ...p, event_name: e.target.value }))} /></div>
                <div><Label>Katilimci Sayisi</Label><Input type="number" value={editForm.attendees} onChange={e => setEditForm(p => ({ ...p, attendees: parseInt(e.target.value) || 0 }))} /></div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div><Label>Tarih</Label><Input type="date" value={editForm.date} onChange={e => setEditForm(p => ({ ...p, date: e.target.value }))} /></div>
                <div><Label>Baslangic</Label><Input type="time" value={editForm.start_time} onChange={e => setEditForm(p => ({ ...p, start_time: e.target.value }))} /></div>
                <div><Label>Bitis</Label><Input type="time" value={editForm.end_time} onChange={e => setEditForm(p => ({ ...p, end_time: e.target.value }))} /></div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div><Label>Firma / Kisi Adi</Label><Input value={editForm.company_name} onChange={e => setEditForm(p => ({ ...p, company_name: e.target.value }))} /></div>
                <div><Label>Yetkili Kisi</Label><Input value={editForm.contact_name} onChange={e => setEditForm(p => ({ ...p, contact_name: e.target.value }))} /></div>
              </div>
              <div>
                <Label>Telefon</Label>
                <Input value={editForm.contact_phone} onChange={e => setEditForm(p => ({ ...p, contact_phone: e.target.value }))} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Kurulum Tipi</Label>
                  <Select value={editForm.setup_type} onValueChange={v => setEditForm(p => ({ ...p, setup_type: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SETUP_TYPES.map(s => <SelectItem key={s.code} value={s.code}>{s.icon} {s.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Ikram</Label>
                  <Select value={editForm.catering} onValueChange={v => setEditForm(p => ({ ...p, catering: v }))}>
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
              </div>

              <div className="border-t pt-4">
                <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                  <Banknote className="w-4 h-4" /> Ucret & Odeme Bilgileri
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Toplam Ucret (TL)</Label>
                    <Input type="number" value={editForm.total_price} onChange={e => setEditForm(p => ({ ...p, total_price: e.target.value }))} placeholder="0" min="0" />
                  </div>
                  <div>
                    <Label>Kapora Tutari (TL)</Label>
                    <Input type="number" value={editForm.deposit_amount} onChange={e => setEditForm(p => ({ ...p, deposit_amount: e.target.value }))} placeholder="0" min="0" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div>
                    <Label>Kapora Durumu</Label>
                    <Select value={editForm.deposit_paid ? 'paid' : 'pending'} onValueChange={v => setEditForm(p => ({ ...p, deposit_paid: v === 'paid' }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="pending">Henuz Alinmadi</SelectItem>
                        <SelectItem value="paid">Kapora Alindi</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Odeme Yontemi</Label>
                    <Select value={editForm.payment_method} onValueChange={v => setEditForm(p => ({ ...p, payment_method: v }))}>
                      <SelectTrigger><SelectValue placeholder="Seciniz" /></SelectTrigger>
                      <SelectContent>
                        {PAYMENT_METHODS.map(m => <SelectItem key={m.code} value={m.code}>{m.icon} {m.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="mt-3">
                  <Label>Odeme Notu</Label>
                  <Input value={editForm.payment_notes} onChange={e => setEditForm(p => ({ ...p, payment_notes: e.target.value }))} placeholder="Ornek: 2 taksit ile odenecek" />
                </div>
              </div>

              <div>
                <Label>Durum</Label>
                <Select value={editForm.status} onValueChange={v => setEditForm(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="confirmed">Onaylandi</SelectItem>
                    <SelectItem value="tentative">Taslak</SelectItem>
                    <SelectItem value="cancelled">Iptal</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div><Label>Not</Label><Textarea value={editForm.notes} onChange={e => setEditForm(p => ({ ...p, notes: e.target.value }))} placeholder="Ozel istekler..." rows={2} /></div>

              {selectedReservation?.created_by && (
                <div className="text-[10px] text-gray-400 border-t pt-2">
                  Olusturan: {selectedReservation.created_by} | {selectedReservation.created_at}
                  {selectedReservation.updated_by && (<> | Son guncelleme: {selectedReservation.updated_by} - {selectedReservation.updated_at}</>)}
                </div>
              )}

              <div className="flex gap-2">
                <Button onClick={updateReservation} disabled={saving} className="flex-1">
                  {saving ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}
                  Kaydet
                </Button>
                {editForm.status !== 'cancelled' && (
                  <Button variant="destructive" onClick={cancelReservation} disabled={saving}>
                    Iptal Et
                  </Button>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MeetingRoomTab;
