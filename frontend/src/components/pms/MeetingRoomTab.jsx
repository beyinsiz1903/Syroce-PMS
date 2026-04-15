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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Building2, Plus, RefreshCw, Users, Calendar, MapPin, ChevronLeft, ChevronRight, Printer, CheckCircle } from 'lucide-react';

const SETUP_TYPES = [
  { code: 'theater', name: 'Tiyatro', icon: '🎭', factor: 1.0 },
  { code: 'classroom', name: 'Sinif', icon: '📚', factor: 0.6 },
  { code: 'u_shape', name: 'U Sekli', icon: '🔲', factor: 0.35 },
  { code: 'boardroom', name: 'Toplanti Masasi', icon: '🪑', factor: 0.25 },
  { code: 'banquet', name: 'Ziyafet', icon: '🍽️', factor: 0.7 },
  { code: 'cocktail', name: 'Kokteyl', icon: '🥂', factor: 0.9 },
  { code: 'hollow_square', name: 'Acik Kare', icon: '⬜', factor: 0.3 },
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

const MENU_TYPES = [
  { code: 'none', name: 'Yok' },
  { code: 'coffee_break', name: 'Kahve Molasi' },
  { code: 'breakfast', name: 'Kahvalti' },
  { code: 'lunch', name: 'Ogle Yemegi' },
  { code: 'dinner', name: 'Aksam Yemegi' },
  { code: 'cocktail', name: 'Kokteyl' },
  { code: 'gala', name: 'Gala Yemegi' },
  { code: 'buffet', name: 'Acik Bufe' },
  { code: 'full_day', name: 'Tam Gun Paket' },
];

const AV_EQUIPMENT = [
  'Projektor', 'LED Ekran', 'Ses Sistemi', 'Mikrofon (Kablosuz)', 'Mikrofon (Yakali)',
  'Video Konferans', 'Sahne', 'Isik Sistemi', 'Flipchart', 'Beyaz Tahta',
  'Simultane Ceviri', 'Kayit Sistemi', 'DJ Masasi', 'Canli Muzik Sahnesi'
];

const PAYMENT_METHODS = [
  { code: 'cash', name: 'Nakit', icon: '💵' },
  { code: 'credit_card', name: 'Kredi Karti', icon: '💳' },
  { code: 'bank_transfer', name: 'Havale/EFT', icon: '🏦' },
  { code: 'check', name: 'Cek', icon: '📝' },
];

const DAYS_TR = ['Pzt', 'Sal', 'Car', 'Per', 'Cum', 'Cmt', 'Paz'];
const MONTHS_TR = ['Ocak', 'Subat', 'Mart', 'Nisan', 'Mayis', 'Haziran', 'Temmuz', 'Agustos', 'Eylul', 'Ekim', 'Kasim', 'Aralik'];

const STATUS_MAP = {
  available: { label: 'Musait', color: 'bg-emerald-100 text-emerald-700' },
  reserved: { label: 'Rezerveli', color: 'bg-blue-100 text-blue-700' },
  in_use: { label: 'Kullaniliyor', color: 'bg-purple-100 text-purple-700' },
  maintenance: { label: 'Bakim', color: 'bg-amber-100 text-amber-700' },
  confirmed: { label: 'Onaylandi', color: 'bg-emerald-100 text-emerald-700' },
  tentative: { label: 'Opsiyonel', color: 'bg-yellow-100 text-yellow-700' },
  cancelled: { label: 'Iptal', color: 'bg-red-100 text-red-700' },
};

const EMPTY_FORM = {
  room_id: '', company_name: '', contact_name: '', contact_phone: '', contact_email: '',
  event_name: '', event_type: 'meeting', date: '', start_time: '', end_time: '',
  setup_type: 'theater', attendees: 20, guaranteed_pax: 0,
  menu_type: 'none', menu_details: '', av_equipment: [],
  decorations: '', special_requests: '',
  notes: '',
  total_price: '', price_per_person: '', deposit_amount: '', deposit_paid: false,
  payment_method: '', payment_notes: '', billing_instructions: '',
  status: 'confirmed',
};

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
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });

  const loadData = useCallback(async () => {
    try {
      const [roomsRes, resRes] = await Promise.allSettled([
        axios.get('/meeting-rooms'),
        axios.get('/meeting-rooms/reservations')
      ]);
      setRooms(roomsRes.status === 'fulfilled' ? roomsRes.value.data.rooms || [] : []);
      setReservations(resRes.status === 'fulfilled' ? resRes.value.data.reservations || [] : []);
    } catch {
      toast.error('Veriler yuklenemedi');
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
        price_per_person: form.price_per_person ? parseFloat(form.price_per_person) : 0,
        deposit_amount: form.deposit_amount ? parseFloat(form.deposit_amount) : 0,
        attendees: parseInt(form.attendees) || 0,
        guaranteed_pax: parseInt(form.guaranteed_pax) || 0,
      };
      await axios.post('/meeting-rooms/reservations', payload);
      toast.success('Organizasyon olusturuldu');
      setShowNewReservation(false);
      setForm({ ...EMPTY_FORM });
      loadData();
    } catch {
      toast.error('Organizasyon olusturulamadi');
    }
    setLoading(false);
  };

  const openReservationDetail = (res) => {
    setSelectedReservation(res);
    setShowCancelConfirm(false);
    setEditForm({
      room_id: res.room_id || '',
      room_name: res.room_name || '',
      event_name: res.event_name || '',
      event_type: res.event_type || 'meeting',
      company_name: res.company_name || '',
      contact_name: res.contact_name || '',
      contact_phone: res.contact_phone || '',
      contact_email: res.contact_email || '',
      date: res.date || '',
      start_time: res.start_time || '',
      end_time: res.end_time || '',
      setup_type: res.setup_type || 'theater',
      attendees: res.attendees || 0,
      guaranteed_pax: res.guaranteed_pax || 0,
      menu_type: res.menu_type || 'none',
      menu_details: res.menu_details || '',
      av_equipment: res.av_equipment || [],
      decorations: res.decorations || '',
      special_requests: res.special_requests || '',
      notes: res.notes || '',
      status: res.status || 'confirmed',
      total_price: res.total_price || '',
      price_per_person: res.price_per_person || '',
      deposit_amount: res.deposit_amount || '',
      deposit_paid: res.deposit_paid || false,
      payment_method: res.payment_method || '',
      payment_notes: res.payment_notes || '',
      billing_instructions: res.billing_instructions || '',
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
        price_per_person: editForm.price_per_person ? parseFloat(editForm.price_per_person) : 0,
        deposit_amount: editForm.deposit_amount ? parseFloat(editForm.deposit_amount) : 0,
        attendees: parseInt(editForm.attendees) || 0,
        guaranteed_pax: parseInt(editForm.guaranteed_pax) || 0,
      };
      await axios.put(`/meeting-rooms/reservations/${selectedReservation.id}`, payload);
      toast.success('Organizasyon guncellendi');
      closeDetailDialog();
      loadData();
    } catch {
      toast.error('Guncelleme basarisiz');
    }
    setSaving(false);
  };

  const cancelReservation = async () => {
    if (!selectedReservation) return;
    setSaving(true);
    try {
      await axios.put(`/meeting-rooms/reservations/${selectedReservation.id}`, { status: 'cancelled' });
      toast.success('Organizasyon iptal edildi');
      closeDetailDialog();
      loadData();
    } catch {
      toast.error('Iptal islemi basarisiz');
    }
    setSaving(false);
  };

  const closeDetailDialog = () => {
    setSelectedReservation(null);
    setEditForm(null);
    setShowCancelConfirm(false);
  };

  const handleAddEventType = () => {
    const trimmed = newEventTypeName.trim();
    if (!trimmed) return;
    const code = trimmed.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
    if (eventTypes.find(e => e.code === code)) { toast.error('Bu tip zaten mevcut'); return; }
    setEventTypes(prev => [...prev, { code, name: trimmed, icon: '📌' }]);
    setNewEventTypeName('');
    setShowAddEventType(false);
    toast.success(`"${trimmed}" eklendi`);
  };

  const handleOpenNewReservation = (dateStr) => {
    setForm({ ...EMPTY_FORM, date: dateStr || '' });
    setShowNewReservation(true);
  };

  const toggleEquipment = (eq, setter) => {
    setter(prev => ({
      ...prev,
      av_equipment: prev.av_equipment.includes(eq)
        ? prev.av_equipment.filter(e => e !== eq)
        : [...prev.av_equipment, eq]
    }));
  };

  const printBEO = (event) => {
    const esc = (str) => { const div = document.createElement('div'); div.textContent = String(str ?? ''); return div.innerHTML; };
    const evType = eventTypes.find(e => e.code === event.event_type);
    const setup = SETUP_TYPES.find(s => s.code === event.setup_type);
    const menu = MENU_TYPES.find(m => m.code === event.menu_type);
    const w = window.open('', '_blank');
    w.document.write(`<html><head><title>BEO - ${esc(event.event_name)}</title><style>body{font-family:Arial;padding:40px;font-size:13px}h1{text-align:center;border-bottom:2px solid #333;padding-bottom:10px}table{width:100%;border-collapse:collapse;margin:15px 0}td,th{border:1px solid #ccc;padding:8px;text-align:left}th{background:#f5f5f5}.header{display:flex;justify-content:space-between;margin-bottom:20px}.section{margin:20px 0}.label{font-weight:bold;color:#555;min-width:150px;display:inline-block}@media print{body{padding:20px}}</style></head><body>`);
    w.document.write(`<h1>BANQUET EVENT ORDER (BEO)</h1>`);
    w.document.write(`<div class="header"><div><span class="label">Etkinlik:</span> ${esc(event.event_name)} ${evType ? `(${esc(evType.name)})` : ''}<br><span class="label">Firma:</span> ${esc(event.company_name || '-')}<br><span class="label">Iletisim:</span> ${esc(event.contact_name)} - ${esc(event.contact_phone)}</div><div><span class="label">Tarih:</span> ${esc(event.date)}<br><span class="label">Saat:</span> ${esc(event.start_time)} - ${esc(event.end_time)}<br><span class="label">Salon:</span> ${esc(event.room_name)}</div></div>`);
    w.document.write(`<div class="section"><table><tr><th>Duzen</th><th>Katilimci</th><th>Garanti</th><th>Menu</th><th>Kisi Basi</th><th>Toplam</th><th>Kapora</th></tr><tr><td>${esc(setup?.name || event.setup_type)}</td><td>${esc(event.attendees)}</td><td>${esc(event.guaranteed_pax || '-')}</td><td>${esc(menu?.name || event.menu_type || '-')}</td><td>${esc(event.price_per_person || '-')} TL</td><td>${esc(event.total_price || 0)} TL</td><td>${esc(event.deposit_amount || 0)} TL ${event.deposit_paid ? '(Alindi)' : '(Bekliyor)'}</td></tr></table></div>`);
    if (event.menu_details) w.document.write(`<div class="section"><span class="label">Menu Detaylari:</span><p>${esc(event.menu_details)}</p></div>`);
    if (event.av_equipment?.length) w.document.write(`<div class="section"><span class="label">AV Ekipman:</span><p>${esc(event.av_equipment.join(', '))}</p></div>`);
    if (event.decorations) w.document.write(`<div class="section"><span class="label">Dekorasyon:</span><p>${esc(event.decorations)}</p></div>`);
    if (event.special_requests) w.document.write(`<div class="section"><span class="label">Ozel Istekler:</span><p>${esc(event.special_requests)}</p></div>`);
    if (event.billing_instructions) w.document.write(`<div class="section"><span class="label">Faturalama:</span><p>${esc(event.billing_instructions)}</p></div>`);
    if (event.notes) w.document.write(`<div class="section"><span class="label">Notlar:</span><p>${esc(event.notes)}</p></div>`);
    w.document.write(`<div style="margin-top:40px;display:flex;justify-content:space-between"><div>Satis Md: _______________</div><div>Mutfak Sefi: _______________</div><div>Organizasyon Md: _______________</div></div>`);
    w.document.write('</body></html>');
    w.document.close();
    w.print();
  };

  const reservationsByDate = useMemo(() => {
    const map = {};
    reservations.forEach(res => { if (res.date) { if (!map[res.date]) map[res.date] = []; map[res.date].push(res); } });
    return map;
  }, [reservations]);

  const calendarDays = useMemo(() => {
    const { year, month } = calendarMonth;
    let startWeekday = new Date(year, month, 1).getDay() - 1;
    if (startWeekday < 0) startWeekday = 6;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const days = [];
    for (let i = 0; i < startWeekday; i++) days.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const dayRes = reservationsByDate[dateStr] || [];
      const roomsBooked = new Set(dayRes.map(r => r.room_id));
      days.push({ day: d, dateStr, reservations: dayRes, roomsFree: rooms.filter(r => !roomsBooked.has(r.id)), roomsBooked: roomsBooked.size });
    }
    return days;
  }, [calendarMonth, reservationsByDate, rooms]);

  const prevMonth = () => setCalendarMonth(p => p.month === 0 ? { year: p.year - 1, month: 11 } : { ...p, month: p.month - 1 });
  const nextMonth = () => setCalendarMonth(p => p.month === 11 ? { year: p.year + 1, month: 0 } : { ...p, month: p.month + 1 });
  const todayStr = useMemo(() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }, []);
  const selectedDateReservations = selectedCalendarDate ? (reservationsByDate[selectedCalendarDate] || []) : [];
  const selectedDateFreeRooms = useMemo(() => {
    if (!selectedCalendarDate) return rooms;
    const booked = new Set(selectedDateReservations.map(r => r.room_id));
    return rooms.filter(r => !booked.has(r.id));
  }, [selectedCalendarDate, selectedDateReservations, rooms]);

  const confirmedCount = reservations.filter(e => e.status === 'confirmed').length;
  const tentativeCount = reservations.filter(e => e.status === 'tentative').length;
  const totalRevenue = reservations.reduce((s, e) => s + (e.total_price || 0), 0);

  const renderEventForm = (f, setter, isEdit = false) => (
    <Tabs defaultValue="general">
      <TabsList className="grid grid-cols-4 w-full">
        <TabsTrigger value="general">Genel</TabsTrigger>
        <TabsTrigger value="menu">Menu & Servis</TabsTrigger>
        <TabsTrigger value="technical">Teknik</TabsTrigger>
        <TabsTrigger value="financial">Finansal</TabsTrigger>
      </TabsList>
      <TabsContent value="general" className="space-y-3 pt-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Salon</Label>
            <Select value={f.room_id} onValueChange={v => setter(p => ({ ...p, room_id: v }))}>
              <SelectTrigger><SelectValue placeholder="Salon seciniz" /></SelectTrigger>
              <SelectContent>{rooms.map(r => <SelectItem key={r.id} value={r.id}>{r.name} ({r.capacity} kisi)</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <div className="flex items-center justify-between">
              <Label>Etkinlik Tipi</Label>
              {!isEdit && <Button variant="ghost" size="sm" className="h-5 text-[10px] text-blue-600 px-1" onClick={() => setShowAddEventType(true)}>+ Yeni Tip</Button>}
            </div>
            <Select value={f.event_type} onValueChange={v => setter(p => ({ ...p, event_type: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{eventTypes.map(e => <SelectItem key={e.code} value={e.code}>{e.icon} {e.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label>Etkinlik Adi</Label><Input value={f.event_name} onChange={e => setter(p => ({ ...p, event_name: e.target.value }))} placeholder="Ornek: Yilmaz Dugun Organizasyonu" /></div>
          <div>
            <Label>Kurulum Tipi</Label>
            <Select value={f.setup_type} onValueChange={v => setter(p => ({ ...p, setup_type: v }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{SETUP_TYPES.map(s => <SelectItem key={s.code} value={s.code}>{s.icon} {s.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div><Label>Tarih</Label><Input type="date" value={f.date} onChange={e => setter(p => ({ ...p, date: e.target.value }))} /></div>
          <div><Label>Baslangic</Label><Input type="time" value={f.start_time} onChange={e => setter(p => ({ ...p, start_time: e.target.value }))} /></div>
          <div><Label>Bitis</Label><Input type="time" value={f.end_time} onChange={e => setter(p => ({ ...p, end_time: e.target.value }))} /></div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div><Label>Katilimci</Label><Input type="number" value={f.attendees} onChange={e => setter(p => ({ ...p, attendees: parseInt(e.target.value) || 0 }))} /></div>
          <div><Label>Garanti Kisi</Label><Input type="number" value={f.guaranteed_pax} onChange={e => setter(p => ({ ...p, guaranteed_pax: parseInt(e.target.value) || 0 }))} /></div>
          <div>
            <Label>Durum</Label>
            {isEdit && f.status === 'cancelled' ? (
              <div className="mt-1"><Badge className="bg-red-100 text-red-700">Iptal Edildi</Badge></div>
            ) : (
              <Select value={f.status} onValueChange={v => setter(p => ({ ...p, status: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="confirmed">Kesin</SelectItem>
                  <SelectItem value="tentative">Opsiyonel</SelectItem>
                </SelectContent>
              </Select>
            )}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div><Label>Firma / Kisi Adi</Label><Input value={f.company_name} onChange={e => setter(p => ({ ...p, company_name: e.target.value }))} /></div>
          <div><Label>Yetkili Kisi</Label><Input value={f.contact_name} onChange={e => setter(p => ({ ...p, contact_name: e.target.value }))} /></div>
          <div><Label>Telefon</Label><Input value={f.contact_phone} onChange={e => setter(p => ({ ...p, contact_phone: e.target.value }))} /></div>
        </div>
        <div><Label>E-posta</Label><Input type="email" value={f.contact_email || ''} onChange={e => setter(p => ({ ...p, contact_email: e.target.value }))} /></div>
      </TabsContent>

      <TabsContent value="menu" className="space-y-3 pt-3">
        <div>
          <Label>Menu Tipi</Label>
          <Select value={f.menu_type || 'none'} onValueChange={v => setter(p => ({ ...p, menu_type: v }))}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{MENU_TYPES.map(m => <SelectItem key={m.code} value={m.code}>{m.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div><Label>Menu Detaylari</Label><Textarea value={f.menu_details || ''} onChange={e => setter(p => ({ ...p, menu_details: e.target.value }))} placeholder="Meze cesitleri, ana yemek, tatli..." rows={3} /></div>
        <div><Label>Dekorasyon</Label><Textarea value={f.decorations || ''} onChange={e => setter(p => ({ ...p, decorations: e.target.value }))} placeholder="Tema, cicek, masa duzeni..." rows={2} /></div>
        <div><Label>Ozel Istekler</Label><Textarea value={f.special_requests || ''} onChange={e => setter(p => ({ ...p, special_requests: e.target.value }))} placeholder="Ek istekler..." rows={2} /></div>
      </TabsContent>

      <TabsContent value="technical" className="space-y-3 pt-3">
        <Label>AV Ekipman (secili: {(f.av_equipment || []).length})</Label>
        <div className="grid grid-cols-2 gap-2">
          {AV_EQUIPMENT.map(eq => (
            <Button key={eq} type="button" size="sm" variant={(f.av_equipment || []).includes(eq) ? 'default' : 'outline'} className="justify-start text-xs" onClick={() => toggleEquipment(eq, setter)}>
              {(f.av_equipment || []).includes(eq) ? <CheckCircle className="h-3 w-3 mr-1" /> : null}{eq}
            </Button>
          ))}
        </div>
        <div><Label>Notlar</Label><Textarea value={f.notes || ''} onChange={e => setter(p => ({ ...p, notes: e.target.value }))} placeholder="Teknik notlar, ozel duzenlemeler..." rows={2} /></div>
      </TabsContent>

      <TabsContent value="financial" className="space-y-3 pt-3">
        <div className="grid grid-cols-3 gap-3">
          <div><Label>Kisi Basi (TL)</Label><Input type="number" value={f.price_per_person || ''} onChange={e => setter(p => ({ ...p, price_per_person: e.target.value }))} placeholder="0" min="0" /></div>
          <div><Label>Toplam Ucret (TL)</Label><Input type="number" value={f.total_price || ''} onChange={e => setter(p => ({ ...p, total_price: e.target.value }))} placeholder="0" min="0" /></div>
          <div><Label>Kapora (TL)</Label><Input type="number" value={f.deposit_amount || ''} onChange={e => setter(p => ({ ...p, deposit_amount: e.target.value }))} placeholder="0" min="0" /></div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Kapora Durumu</Label>
            <Select value={f.deposit_paid ? 'paid' : 'pending'} onValueChange={v => setter(p => ({ ...p, deposit_paid: v === 'paid' }))}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="pending">Henuz Alinmadi</SelectItem>
                <SelectItem value="paid">Kapora Alindi</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Odeme Yontemi</Label>
            <Select value={f.payment_method || ''} onValueChange={v => setter(p => ({ ...p, payment_method: v }))}>
              <SelectTrigger><SelectValue placeholder="Seciniz" /></SelectTrigger>
              <SelectContent>{PAYMENT_METHODS.map(m => <SelectItem key={m.code} value={m.code}>{m.icon} {m.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <div><Label>Odeme Notu</Label><Input value={f.payment_notes || ''} onChange={e => setter(p => ({ ...p, payment_notes: e.target.value }))} placeholder="Ornek: 2 taksit ile odenecek" /></div>
        <div><Label>Faturalama Talimatlari</Label><Textarea value={f.billing_instructions || ''} onChange={e => setter(p => ({ ...p, billing_instructions: e.target.value }))} placeholder="Fatura kime kesilecek, ozel notlar..." rows={2} /></div>
      </TabsContent>
    </Tabs>
  );

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold flex items-center gap-2">
          <Building2 className="w-6 h-6" /> Organizasyon & Salon Yonetimi
        </h2>
        <div className="flex gap-2">
          <Button onClick={() => handleOpenNewReservation(null)} className="bg-blue-600 hover:bg-blue-700">
            <Plus className="w-4 h-4 mr-2" /> Yeni Organizasyon
          </Button>
          <Button variant="outline" onClick={loadData}>
            <RefreshCw className="w-4 h-4 mr-2" /> Yenile
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card className="border-blue-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-blue-600">{confirmedCount}</div>
            <div className="text-xs text-gray-500">Kesin Organizasyon</div>
          </CardContent>
        </Card>
        <Card className="border-yellow-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-yellow-600">{tentativeCount}</div>
            <div className="text-xs text-gray-500">Opsiyonel</div>
          </CardContent>
        </Card>
        <Card className="border-green-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-green-600">{totalRevenue.toLocaleString('tr-TR')} TL</div>
            <div className="text-xs text-gray-500">Toplam Gelir</div>
          </CardContent>
        </Card>
        <Card className="border-purple-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-purple-600">{rooms.length}</div>
            <div className="text-xs text-gray-500">Salon</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        {rooms.map(room => {
          const sc = STATUS_MAP[room.status] || STATUS_MAP.available;
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
                <div className="text-gray-400">{room.area} m2</div>
                <div className="flex flex-wrap gap-1">
                  {room.equipment?.slice(0, 3).map((eq, i) => (<Badge key={i} variant="outline" className="text-[9px] h-4">{eq}</Badge>))}
                  {(room.equipment?.length || 0) > 3 && <Badge variant="outline" className="text-[9px] h-4">+{room.equipment.length - 3}</Badge>}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2"><Calendar className="w-4 h-4" /> Salon Musaitlik Takvimi</CardTitle>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={prevMonth}><ChevronLeft className="w-4 h-4" /></Button>
              <span className="text-sm font-medium min-w-[120px] text-center">{MONTHS_TR[calendarMonth.month]} {calendarMonth.year}</span>
              <Button variant="ghost" size="sm" onClick={nextMonth}><ChevronRight className="w-4 h-4" /></Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-px bg-gray-200 rounded-lg overflow-hidden">
            {DAYS_TR.map(d => (<div key={d} className="bg-gray-50 text-center text-[10px] font-semibold text-gray-500 py-1.5">{d}</div>))}
            {calendarDays.map((cell, i) => {
              if (!cell) return <div key={`e-${i}`} className="bg-white min-h-[64px]" />;
              const isToday = cell.dateStr === todayStr;
              const isSelected = cell.dateStr === selectedCalendarDate;
              const hasEvents = cell.reservations.length > 0;
              const allBooked = rooms.length > 0 && cell.roomsFree.length === 0;
              return (
                <div key={cell.dateStr} onClick={() => setSelectedCalendarDate(cell.dateStr === selectedCalendarDate ? null : cell.dateStr)}
                  className={`bg-white min-h-[64px] p-1 cursor-pointer transition hover:bg-blue-50 ${isSelected ? 'ring-2 ring-blue-500 bg-blue-50' : ''} ${isToday ? 'bg-blue-50/50' : ''}`}>
                  <div className="flex items-center justify-between">
                    <span className={`text-xs font-medium ${isToday ? 'bg-blue-600 text-white rounded-full w-5 h-5 flex items-center justify-center' : 'text-gray-700'}`}>{cell.day}</span>
                    {rooms.length > 0 && <span className={`text-[9px] px-1 rounded ${allBooked ? 'bg-red-100 text-red-600' : 'bg-emerald-100 text-emerald-600'}`}>{cell.roomsFree.length}/{rooms.length}</span>}
                  </div>
                  {hasEvents && (
                    <div className="mt-0.5 space-y-0.5">
                      {cell.reservations.slice(0, 2).map((res, ri) => (<div key={ri} className="text-[8px] bg-purple-100 text-purple-700 rounded px-1 py-0.5 truncate">{res.event_name || res.room_name}</div>))}
                      {cell.reservations.length > 2 && <div className="text-[8px] text-gray-400 px-1">+{cell.reservations.length - 2} daha</div>}
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
                  <Plus className="w-3 h-3 mr-1" /> Bu Gun Organizasyon
                </Button>
              </div>
              {selectedDateFreeRooms.length > 0 && (
                <div className="mb-2">
                  <p className="text-xs text-gray-500 mb-1">Musait Salonlar:</p>
                  <div className="flex flex-wrap gap-1">{selectedDateFreeRooms.map(r => (<Badge key={r.id} className="bg-emerald-100 text-emerald-700 text-[10px]">{r.name} ({r.capacity} kisi)</Badge>))}</div>
                </div>
              )}
              {selectedDateReservations.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1">Organizasyonlar:</p>
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
                            {res.total_price > 0 && <span className="text-emerald-600 font-medium">{Number(res.total_price).toLocaleString('tr-TR')} TL</span>}
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
                <p className="text-xs text-gray-400">Bu tarihte henuz organizasyon yok. Tum salonlar musait.</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2"><Calendar className="w-4 h-4" /> Organizasyonlar</CardTitle>
        </CardHeader>
        <CardContent>
          {reservations.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">Henuz organizasyon yok</p>
          ) : (
            <div className="space-y-2">
              {reservations.map(res => {
                const sc = STATUS_MAP[res.status] || STATUS_MAP.confirmed;
                const evType = eventTypes.find(e => e.code === res.event_type);
                return (
                  <div key={res.id} onClick={() => openReservationDetail(res)} className="flex items-center justify-between p-3 border rounded-lg hover:bg-blue-50 cursor-pointer transition">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center text-lg">{evType?.icon || '📋'}</div>
                      <div>
                        <p className="text-sm font-medium">{res.event_name || 'Etkinlik'}</p>
                        <p className="text-xs text-gray-500">{res.room_name} | {res.company_name} {evType ? `| ${evType.name}` : ''}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 text-xs">
                      {res.total_price > 0 && (
                        <div className="text-right">
                          <p className="text-sm font-semibold text-gray-800">{Number(res.total_price).toLocaleString('tr-TR')} TL</p>
                          {res.deposit_amount > 0 && <p className="text-[10px] text-gray-400">Kapora: {Number(res.deposit_amount).toLocaleString('tr-TR')} TL</p>}
                        </div>
                      )}
                      {res.deposit_paid && <Badge className="bg-green-100 text-green-700 text-[10px]">Kapora Alindi</Badge>}
                      {!res.deposit_paid && res.deposit_amount > 0 && <Badge className="bg-amber-100 text-amber-700 text-[10px]">Kapora Bekliyor</Badge>}
                      <div className="text-right">
                        <p className="text-gray-700">{res.date}</p>
                        <p className="text-gray-400">{res.start_time} - {res.end_time}</p>
                      </div>
                      <div className="flex items-center gap-1 text-gray-500"><Users className="w-3 h-3" /> {res.attendees}</div>
                      <Badge className={sc.color}>{sc.label}</Badge>
                      <Button size="sm" variant="outline" className="h-7 text-[10px]" onClick={(e) => { e.stopPropagation(); printBEO(res); }}>
                        <Printer className="w-3 h-3 mr-1" /> BEO
                      </Button>
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
            <DialogTitle className="flex items-center gap-2"><Building2 className="w-5 h-5" /> Yeni Organizasyon</DialogTitle>
          </DialogHeader>
          <div className="max-h-[70vh] overflow-y-auto pr-1">
            {renderEventForm(form, setForm, false)}
            <Button onClick={submitReservation} disabled={loading} className="w-full mt-4">
              {loading ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              Organizasyon Olustur
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showAddEventType} onOpenChange={setShowAddEventType}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Yeni Etkinlik Tipi Ekle</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div><Label>Etkinlik Tipi Adi</Label><Input value={newEventTypeName} onChange={e => setNewEventTypeName(e.target.value)} placeholder="Ornek: Baby Shower" onKeyDown={e => e.key === 'Enter' && handleAddEventType()} /></div>
            <div className="flex gap-2">
              <Button onClick={handleAddEventType} className="flex-1">Ekle</Button>
              <Button variant="outline" onClick={() => { setShowAddEventType(false); setNewEventTypeName(''); }}>Vazgec</Button>
            </div>
            <div>
              <p className="text-xs text-gray-500 mb-2">Mevcut Tipler:</p>
              <div className="flex flex-wrap gap-1">{eventTypes.map(e => (<Badge key={e.code} variant="outline" className="text-[10px]">{e.icon} {e.name}</Badge>))}</div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!selectedReservation} onOpenChange={v => { if (!v) closeDetailDialog(); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5" /> Organizasyon Detayi
              {selectedReservation && <Badge className={STATUS_MAP[selectedReservation.status]?.color || 'bg-gray-100'}>{STATUS_MAP[selectedReservation.status]?.label || selectedReservation.status}</Badge>}
            </DialogTitle>
          </DialogHeader>
          {editForm && (
            <div className="max-h-[70vh] overflow-y-auto pr-1 space-y-3">
              {renderEventForm(editForm, setEditForm, true)}

              {selectedReservation?.created_by && (
                <div className="text-[10px] text-gray-400 border-t pt-2">
                  Olusturan: {selectedReservation.created_by} | {selectedReservation.created_at}
                  {selectedReservation.updated_by && (<> | Son guncelleme: {selectedReservation.updated_by} - {selectedReservation.updated_at}</>)}
                </div>
              )}

              {editForm.status !== 'cancelled' && !showCancelConfirm && (
                <div className="border-t pt-3">
                  <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-700 hover:bg-red-50 text-xs" onClick={() => setShowCancelConfirm(true)}>
                    Organizasyonu Iptal Et
                  </Button>
                </div>
              )}

              {showCancelConfirm && (
                <div className="border border-red-200 bg-red-50 rounded-lg p-3 space-y-2">
                  <p className="text-sm font-medium text-red-800">Organizasyonu iptal etmek istediginizden emin misiniz?</p>
                  <p className="text-xs text-red-600">Bu islem geri alinamaz. Durum "Iptal" olarak guncellenecektir.</p>
                  <div className="flex gap-2">
                    <Button variant="destructive" size="sm" onClick={cancelReservation} disabled={saving}>
                      {saving ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}Evet, Iptal Et
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setShowCancelConfirm(false)}>Vazgec</Button>
                  </div>
                </div>
              )}

              <div className="flex gap-2 border-t pt-3">
                <Button onClick={updateReservation} disabled={saving} className="flex-1">
                  {saving ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}Kaydet
                </Button>
                <Button variant="outline" size="sm" onClick={(e) => { e.stopPropagation(); printBEO({ ...editForm, ...selectedReservation }); }}>
                  <Printer className="w-4 h-4 mr-1" /> BEO Yazdir
                </Button>
                <Button variant="outline" onClick={closeDetailDialog}>Kapat</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MeetingRoomTab;
