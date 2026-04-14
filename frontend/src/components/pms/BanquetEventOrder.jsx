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
  Calendar, Plus, Users, Clock, Printer, CheckCircle, AlertCircle
} from 'lucide-react';

const SETUP_TYPES = [
  { value: 'theater', label: 'Tiyatro', capacity_factor: 1.0 },
  { value: 'classroom', label: 'Sinif', capacity_factor: 0.6 },
  { value: 'u_shape', label: 'U Duzeni', capacity_factor: 0.35 },
  { value: 'boardroom', label: 'Toplanti', capacity_factor: 0.25 },
  { value: 'banquet', label: 'Ziyafet', capacity_factor: 0.7 },
  { value: 'cocktail', label: 'Kokteyl', capacity_factor: 0.9 },
  { value: 'hollow_square', label: 'Icki Kare', capacity_factor: 0.3 },
];

const MENU_TYPES = [
  { value: 'breakfast', label: 'Kahvalti' },
  { value: 'lunch', label: 'Ogle Yemegi' },
  { value: 'dinner', label: 'Aksam Yemegi' },
  { value: 'coffee_break', label: 'Kahve Molasi' },
  { value: 'cocktail', label: 'Kokteyl' },
  { value: 'gala', label: 'Gala Yemegi' },
  { value: 'buffet', label: 'Acik Bufe' },
];

const AV_EQUIPMENT = [
  'Projektor', 'LED Ekran', 'Ses Sistemi', 'Mikrofon (Kablosuz)', 'Mikrofon (Yakalı)',
  'Video Konferans', 'Sahne', 'Isik Sistemi', 'Flipchart', 'Beyaz Tahta',
  'Simultane Ceviri', 'Kayit Sistemi', 'DJ Masasi', 'Canli Muzik Sahnesi'
];

const EMPTY_EVENT = {
  event_name: '', company: '', contact_name: '', contact_phone: '', contact_email: '',
  room_name: '', date: '', start_time: '', end_time: '',
  setup_type: '', attendees: '', guaranteed_pax: '', menu_type: '',
  menu_details: '', av_equipment: [], special_requests: '', decorations: '',
  price_per_person: '', total_price: '', deposit_amount: '', status: 'tentative',
  billing_instructions: '', notes: ''
};

const BanquetEventOrder = () => {
  const [events, setEvents] = useState([]);
  const [showNew, setShowNew] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [viewMode, setViewMode] = useState('list');
  const [loading, setLoading] = useState(false);
  const [newEvent, setNewEvent] = useState({ ...EMPTY_EVENT });

  useEffect(() => { loadEvents(); }, []);

  const loadEvents = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/banquet/events');
      setEvents(res.data.events || []);
    } catch {
      toast.error('Etkinlikler yuklenemedi');
    } finally {
      setLoading(false);
    }
  };

  const createEvent = async () => {
    if (!newEvent.event_name || !newEvent.date) return;
    try {
      const payload = {
        ...newEvent,
        attendees: parseInt(newEvent.attendees) || 0,
        guaranteed_pax: parseInt(newEvent.guaranteed_pax) || 0,
        price_per_person: parseFloat(newEvent.price_per_person) || 0,
        total_price: parseFloat(newEvent.total_price) || 0,
        deposit_amount: parseFloat(newEvent.deposit_amount) || 0,
      };
      const res = await axios.post('/banquet/events', payload);
      setEvents(prev => [res.data, ...prev]);
      setNewEvent({ ...EMPTY_EVENT });
      setShowNew(false);
      toast.success('Etkinlik olusturuldu');
    } catch {
      toast.error('Etkinlik olusturulamadi');
    }
  };

  const printBEO = (event) => {
    const esc = (str) => {
      const div = document.createElement('div');
      div.textContent = String(str ?? '');
      return div.innerHTML;
    };
    const w = window.open('', '_blank');
    w.document.write(`<html><head><title>BEO - ${esc(event.event_name)}</title><style>body{font-family:Arial;padding:40px;font-size:13px}h1{text-align:center;border-bottom:2px solid #333;padding-bottom:10px}table{width:100%;border-collapse:collapse;margin:15px 0}td,th{border:1px solid #ccc;padding:8px;text-align:left}th{background:#f5f5f5}.header{display:flex;justify-content:space-between;margin-bottom:20px}.section{margin:20px 0}.label{font-weight:bold;color:#555;min-width:150px;display:inline-block}@media print{body{padding:20px}}</style></head><body>`);
    w.document.write(`<h1>BANQUET EVENT ORDER (BEO)</h1>`);
    w.document.write(`<div class="header"><div><span class="label">Etkinlik:</span> ${esc(event.event_name)}<br><span class="label">Firma:</span> ${esc(event.company || '-')}<br><span class="label">Iletisim:</span> ${esc(event.contact_name)} - ${esc(event.contact_phone)}</div><div><span class="label">Tarih:</span> ${esc(event.date)}<br><span class="label">Saat:</span> ${esc(event.start_time)} - ${esc(event.end_time)}<br><span class="label">Salon:</span> ${esc(event.room_name)}</div></div>`);
    w.document.write(`<div class="section"><table><tr><th>Duzen</th><th>Katilimci</th><th>Garanti</th><th>Menu</th><th>Kisi Basi</th><th>Toplam</th></tr><tr><td>${esc(SETUP_TYPES.find(s=>s.value===event.setup_type)?.label || event.setup_type)}</td><td>${esc(event.attendees)}</td><td>${esc(event.guaranteed_pax)}</td><td>${esc(MENU_TYPES.find(m=>m.value===event.menu_type)?.label || event.menu_type)}</td><td>${esc(event.price_per_person)} TL</td><td>${esc(event.total_price)} TL</td></tr></table></div>`);
    if (event.menu_details) w.document.write(`<div class="section"><span class="label">Menu Detaylari:</span><p>${esc(event.menu_details)}</p></div>`);
    if (event.av_equipment?.length) w.document.write(`<div class="section"><span class="label">AV Ekipman:</span><p>${esc(event.av_equipment.join(', '))}</p></div>`);
    if (event.decorations) w.document.write(`<div class="section"><span class="label">Dekorasyon:</span><p>${esc(event.decorations)}</p></div>`);
    if (event.special_requests) w.document.write(`<div class="section"><span class="label">Ozel Istekler:</span><p>${esc(event.special_requests)}</p></div>`);
    if (event.billing_instructions) w.document.write(`<div class="section"><span class="label">Faturalama:</span><p>${esc(event.billing_instructions)}</p></div>`);
    w.document.write(`<div style="margin-top:40px;display:flex;justify-content:space-between"><div>Satis Md: _______________</div><div>Mutfak Sefi: _______________</div><div>Banket Md: _______________</div></div>`);
    w.document.write('</body></html>');
    w.document.close();
    w.print();
  };

  const toggleEquipment = (eq) => {
    setNewEvent(prev => ({
      ...prev,
      av_equipment: prev.av_equipment.includes(eq)
        ? prev.av_equipment.filter(e => e !== eq)
        : [...prev.av_equipment, eq]
    }));
  };

  const statusLabel = (s) => s === 'confirmed' ? 'Kesin' : s === 'tentative' ? 'Opsiyonel' : s === 'cancelled' ? 'Iptal' : s;
  const statusVariant = (s) => s === 'confirmed' ? 'default' : s === 'tentative' ? 'secondary' : 'destructive';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold flex items-center gap-2">
          <Calendar className="h-5 w-5" /> Banket & Etkinlik Yonetimi
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setViewMode(viewMode === 'list' ? 'calendar' : 'list')}>
            {viewMode === 'list' ? 'Takvim' : 'Liste'}
          </Button>
          <Button onClick={() => setShowNew(true)}><Plus className="h-4 w-4 mr-1" /> Yeni Etkinlik</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card className="border-blue-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-blue-600">{events.filter(e => e.status === 'confirmed').length}</div>
            <div className="text-xs text-muted-foreground">Kesin Etkinlik</div>
          </CardContent>
        </Card>
        <Card className="border-yellow-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-yellow-600">{events.filter(e => e.status === 'tentative').length}</div>
            <div className="text-xs text-muted-foreground">Opsiyonel</div>
          </CardContent>
        </Card>
        <Card className="border-green-200">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-green-600">{events.reduce((s, e) => s + (e.total_price || 0), 0).toLocaleString()} TL</div>
            <div className="text-xs text-muted-foreground">Toplam Gelir</div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-2">
        {loading && <p className="text-center text-muted-foreground py-4">Yukleniyor...</p>}
        {!loading && events.length === 0 && <p className="text-center text-muted-foreground py-8">Henuz etkinlik yok</p>}
        {events.map(event => (
          <Card key={event.id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => setSelectedEvent(event)}>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold">{event.event_name}</span>
                    <Badge variant={statusVariant(event.status)}>{statusLabel(event.status)}</Badge>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1"><Calendar className="h-3 w-3" />{event.date}</span>
                    <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{event.start_time}-{event.end_time}</span>
                    <span className="flex items-center gap-1"><Users className="h-3 w-3" />{event.attendees} kisi</span>
                    <span>{event.room_name}</span>
                    {event.company && <span className="flex items-center gap-1">• {event.company}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-green-600">{event.total_price?.toLocaleString()} TL</span>
                  <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); printBEO(event); }}>
                    <Printer className="h-3 w-3 mr-1" /> BEO
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={selectedEvent !== null} onOpenChange={() => setSelectedEvent(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          {selectedEvent && (
            <>
              <DialogHeader>
                <DialogTitle>{selectedEvent.event_name}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div><Label className="text-xs text-muted-foreground">Firma</Label><p className="font-medium">{selectedEvent.company || '-'}</p></div>
                  <div><Label className="text-xs text-muted-foreground">Iletisim</Label><p className="font-medium">{selectedEvent.contact_name} - {selectedEvent.contact_phone}</p></div>
                  <div><Label className="text-xs text-muted-foreground">Salon</Label><p className="font-medium">{selectedEvent.room_name}</p></div>
                  <div><Label className="text-xs text-muted-foreground">Duzen</Label><p className="font-medium">{SETUP_TYPES.find(s=>s.value===selectedEvent.setup_type)?.label || selectedEvent.setup_type}</p></div>
                  <div><Label className="text-xs text-muted-foreground">Tarih/Saat</Label><p className="font-medium">{selectedEvent.date} / {selectedEvent.start_time} - {selectedEvent.end_time}</p></div>
                  <div><Label className="text-xs text-muted-foreground">Katilimci/Garanti</Label><p className="font-medium">{selectedEvent.attendees} / {selectedEvent.guaranteed_pax}</p></div>
                </div>
                {selectedEvent.menu_details && <div><Label className="text-xs text-muted-foreground">Menu</Label><p className="text-sm">{selectedEvent.menu_details}</p></div>}
                {selectedEvent.av_equipment?.length > 0 && <div><Label className="text-xs text-muted-foreground">AV Ekipman</Label><div className="flex flex-wrap gap-1 mt-1">{selectedEvent.av_equipment.map(eq => <Badge key={eq} variant="outline">{eq}</Badge>)}</div></div>}
                {selectedEvent.decorations && <div><Label className="text-xs text-muted-foreground">Dekorasyon</Label><p className="text-sm">{selectedEvent.decorations}</p></div>}
                {selectedEvent.special_requests && <div><Label className="text-xs text-muted-foreground">Ozel Istekler</Label><p className="text-sm">{selectedEvent.special_requests}</p></div>}
                <div className="grid grid-cols-3 gap-4 bg-muted p-3 rounded-lg">
                  <div className="text-center"><div className="text-xs text-muted-foreground">Kisi Basi</div><div className="font-bold">{selectedEvent.price_per_person} TL</div></div>
                  <div className="text-center"><div className="text-xs text-muted-foreground">Toplam</div><div className="font-bold text-green-600">{selectedEvent.total_price?.toLocaleString()} TL</div></div>
                  <div className="text-center"><div className="text-xs text-muted-foreground">Kapora</div><div className="font-bold text-blue-600">{selectedEvent.deposit_amount?.toLocaleString()} TL</div></div>
                </div>
                <Button className="w-full" onClick={() => { printBEO(selectedEvent); }}><Printer className="h-4 w-4 mr-1" /> BEO Yazdir</Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={showNew} onOpenChange={setShowNew}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Yeni Etkinlik / BEO</DialogTitle></DialogHeader>
          <Tabs defaultValue="general">
            <TabsList className="grid grid-cols-4 w-full">
              <TabsTrigger value="general">Genel</TabsTrigger>
              <TabsTrigger value="menu">Menu & Servis</TabsTrigger>
              <TabsTrigger value="technical">Teknik</TabsTrigger>
              <TabsTrigger value="financial">Finansal</TabsTrigger>
            </TabsList>
            <TabsContent value="general" className="space-y-3">
              <div><Label>Etkinlik Adi</Label><Input value={newEvent.event_name} onChange={e => setNewEvent(p => ({ ...p, event_name: e.target.value }))} placeholder="Yillik Toplanti, Dugun..." /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Firma/Kurum</Label><Input value={newEvent.company} onChange={e => setNewEvent(p => ({ ...p, company: e.target.value }))} /></div>
                <div><Label>Salon</Label><Select value={newEvent.room_name} onValueChange={v => setNewEvent(p => ({ ...p, room_name: v }))}><SelectTrigger><SelectValue placeholder="Salon secin..." /></SelectTrigger><SelectContent><SelectItem value="Balo Salonu">Balo Salonu</SelectItem><SelectItem value="Toplanti Salonu A">Toplanti Salonu A</SelectItem><SelectItem value="Toplanti Salonu B">Toplanti Salonu B</SelectItem><SelectItem value="VIP Toplanti Odasi">VIP Toplanti Odasi</SelectItem></SelectContent></Select></div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Tarih</Label><Input type="date" value={newEvent.date} onChange={e => setNewEvent(p => ({ ...p, date: e.target.value }))} /></div>
                <div><Label>Baslangic</Label><Input type="time" value={newEvent.start_time} onChange={e => setNewEvent(p => ({ ...p, start_time: e.target.value }))} /></div>
                <div><Label>Bitis</Label><Input type="time" value={newEvent.end_time} onChange={e => setNewEvent(p => ({ ...p, end_time: e.target.value }))} /></div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Iletisim Adi</Label><Input value={newEvent.contact_name} onChange={e => setNewEvent(p => ({ ...p, contact_name: e.target.value }))} /></div>
                <div><Label>Telefon</Label><Input value={newEvent.contact_phone} onChange={e => setNewEvent(p => ({ ...p, contact_phone: e.target.value }))} /></div>
                <div><Label>E-posta</Label><Input value={newEvent.contact_email} onChange={e => setNewEvent(p => ({ ...p, contact_email: e.target.value }))} /></div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Duzen</Label><Select value={newEvent.setup_type} onValueChange={v => setNewEvent(p => ({ ...p, setup_type: v }))}><SelectTrigger><SelectValue placeholder="Duzen..." /></SelectTrigger><SelectContent>{SETUP_TYPES.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent></Select></div>
                <div><Label>Katilimci</Label><Input type="number" value={newEvent.attendees} onChange={e => setNewEvent(p => ({ ...p, attendees: e.target.value }))} /></div>
                <div><Label>Garanti Kisi</Label><Input type="number" value={newEvent.guaranteed_pax} onChange={e => setNewEvent(p => ({ ...p, guaranteed_pax: e.target.value }))} /></div>
              </div>
            </TabsContent>
            <TabsContent value="menu" className="space-y-3">
              <div><Label>Menu Tipi</Label><Select value={newEvent.menu_type} onValueChange={v => setNewEvent(p => ({ ...p, menu_type: v }))}><SelectTrigger><SelectValue placeholder="Menu tipi..." /></SelectTrigger><SelectContent>{MENU_TYPES.map(m => <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>)}</SelectContent></Select></div>
              <div><Label>Menu Detaylari</Label><Textarea value={newEvent.menu_details} onChange={e => setNewEvent(p => ({ ...p, menu_details: e.target.value }))} placeholder="Meze cesitleri, ana yemek, tatli..." rows={3} /></div>
              <div><Label>Dekorasyon</Label><Textarea value={newEvent.decorations} onChange={e => setNewEvent(p => ({ ...p, decorations: e.target.value }))} placeholder="Tema, cicek, masa duzeni..." rows={2} /></div>
              <div><Label>Ozel Istekler</Label><Textarea value={newEvent.special_requests} onChange={e => setNewEvent(p => ({ ...p, special_requests: e.target.value }))} placeholder="Ek istekler..." rows={2} /></div>
            </TabsContent>
            <TabsContent value="technical" className="space-y-3">
              <Label>AV Ekipman (secili: {newEvent.av_equipment.length})</Label>
              <div className="grid grid-cols-2 gap-2">
                {AV_EQUIPMENT.map(eq => (
                  <Button key={eq} size="sm" variant={newEvent.av_equipment.includes(eq) ? 'default' : 'outline'} className="justify-start" onClick={() => toggleEquipment(eq)}>
                    {newEvent.av_equipment.includes(eq) ? <CheckCircle className="h-3 w-3 mr-1" /> : null}{eq}
                  </Button>
                ))}
              </div>
            </TabsContent>
            <TabsContent value="financial" className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <div><Label>Kisi Basi (TL)</Label><Input type="number" value={newEvent.price_per_person} onChange={e => setNewEvent(p => ({ ...p, price_per_person: e.target.value }))} /></div>
                <div><Label>Toplam (TL)</Label><Input type="number" value={newEvent.total_price} onChange={e => setNewEvent(p => ({ ...p, total_price: e.target.value }))} /></div>
                <div><Label>Kapora (TL)</Label><Input type="number" value={newEvent.deposit_amount} onChange={e => setNewEvent(p => ({ ...p, deposit_amount: e.target.value }))} /></div>
              </div>
              <div><Label>Durum</Label><Select value={newEvent.status} onValueChange={v => setNewEvent(p => ({ ...p, status: v }))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="tentative">Opsiyonel</SelectItem><SelectItem value="confirmed">Kesin</SelectItem></SelectContent></Select></div>
              <div><Label>Faturalama Talimatlari</Label><Textarea value={newEvent.billing_instructions} onChange={e => setNewEvent(p => ({ ...p, billing_instructions: e.target.value }))} placeholder="Fatura kime kesilecek, ozel notlar..." /></div>
              <div><Label>Notlar</Label><Input value={newEvent.notes} onChange={e => setNewEvent(p => ({ ...p, notes: e.target.value }))} /></div>
            </TabsContent>
          </Tabs>
          <Button className="w-full mt-4" onClick={createEvent}>Etkinlik Olustur</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default BanquetEventOrder;
