import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { confirmDialog } from '@/lib/dialogs';
import {
  Sparkles, Plus, Calendar, Users, DoorOpen, RefreshCw, Trash2,
  CheckCircle2, XCircle, PlayCircle, Receipt, History,
} from 'lucide-react';

const STATUS = {
  scheduled: { label: 'Planlandı', cls: 'bg-sky-100 text-sky-800' },
  in_progress: { label: 'Devam Ediyor', cls: 'bg-amber-100 text-amber-800' },
  completed: { label: 'Tamamlandı', cls: 'bg-emerald-100 text-emerald-800' },
  no_show: { label: 'Gelmedi', cls: 'bg-gray-100 text-gray-700' },
  cancelled: { label: 'İptal', cls: 'bg-red-100 text-red-800' },
};

const fmtTime = (iso) => iso ? new Date(iso).toLocaleString('tr-TR', {
  hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit',
}) : '—';

const SpaWellness = ({ user, tenant, onLogout }) => {
  const [services, setServices] = useState([]);
  const [therapists, setTherapists] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showBook, setShowBook] = useState(false);
  const [showServiceForm, setShowServiceForm] = useState(false);
  const [showTherapistForm, setShowTherapistForm] = useState(false);
  const [showRoomForm, setShowRoomForm] = useState(false);
  const [filter, setFilter] = useState({ date_from: '', therapist_id: '' });

  const [bookForm, setBookForm] = useState({
    service_id: '', therapist_id: '', room_id: '',
    starts_at: new Date().toISOString().slice(0, 16),
    guest_name: '', guest_phone: '', reservation_id: '', charge_to_room: false,
  });
  const [serviceForm, setServiceForm] = useState({
    name: '', category: 'massage', duration_minutes: 60, price: 0, currency: 'TRY',
  });
  const [therapistForm, setTherapistForm] = useState({
    name: '', specialties: [], work_start: '09:00', work_end: '21:00',
  });
  const [roomForm, setRoomForm] = useState({
    name: '', room_type: 'standard', capacity: 1,
  });

  const load = async () => {
    setLoading(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      // Promise.allSettled: tek bir uç hata verirse diğer kartlar boş kalmasın.
      const [s, t, r, a, sum] = await Promise.allSettled([
        axios.get('/spa/services'),
        axios.get('/spa/therapists'),
        axios.get('/spa/rooms'),
        axios.get('/spa/appointments', { params: filter }),
        axios.get('/spa/daily-summary', { params: { date: today } }),
      ]);
      const failed = [];
      if (s.status === 'fulfilled') setServices(s.value.data.services || []);
      else { setServices([]); failed.push('Hizmetler'); }
      if (t.status === 'fulfilled') setTherapists(t.value.data.therapists || []);
      else { setTherapists([]); failed.push('Terapistler'); }
      if (r.status === 'fulfilled') setRooms(r.value.data.rooms || []);
      else { setRooms([]); failed.push('Odalar'); }
      if (a.status === 'fulfilled') setAppointments(a.value.data.appointments || []);
      else { setAppointments([]); failed.push('Randevular'); }
      if (sum.status === 'fulfilled') setSummary(sum.value.data);
      else { setSummary(null); failed.push('Günlük özet'); }
      if (failed.length) toast.error(`Yüklenemedi: ${failed.join(', ')}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [filter]);

  const therapistById = useMemo(() => Object.fromEntries(therapists.map((t) => [t.id, t])), [therapists]);
  const roomById = useMemo(() => Object.fromEntries(rooms.map((r) => [r.id, r])), [rooms]);

  const book = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/spa/appointments', bookForm);
      toast.success('Randevu oluşturuldu');
      setShowBook(false);
      setBookForm({ ...bookForm, guest_name: '', guest_phone: '' });
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Oluşturulamadı');
    }
  };

  const updateStatus = async (id, status) => {
    try {
      await axios.post(`/spa/appointments/${id}/status`, { status });
      toast.success('Durum güncellendi');
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || 'Hata'); }
  };

  const remove = async (id) => {
    if (!await confirmDialog({ message: 'Randevu silinsin mi?', variant: 'danger' })) return;
    try { await axios.delete(`/spa/appointments/${id}`); await load(); }
    catch (e) { toast.error('Silinemedi'); }
  };

  const addService = async (e) => {
    e.preventDefault();
    try { await axios.post('/spa/services', serviceForm); setShowServiceForm(false); await load(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Eklenemedi'); }
  };
  const addTherapist = async (e) => {
    e.preventDefault();
    try { await axios.post('/spa/therapists', therapistForm); setShowTherapistForm(false); await load(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Eklenemedi'); }
  };
  const addRoom = async (e) => {
    e.preventDefault();
    try { await axios.post('/spa/rooms', roomForm); setShowRoomForm(false); await load(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Eklenemedi'); }
  };

  if (loading) {
    return (
      <>
        <div className="p-8 text-center text-gray-500">
          <RefreshCw className="w-6 h-6 animate-spin inline" /> Yükleniyor…
        </div>
      </>
    );
  }

  return (
    <>
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-indigo-600" /> Spa & Wellness
          </h1>
          <p className="text-sm text-gray-500">
            Hizmet kataloğu, terapist & oda yönetimi, çakışma kontrollü randevu planlama.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
          <Button onClick={() => setShowBook(true)}>
            <Plus className="w-4 h-4 mr-1" /> Randevu
          </Button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Bugün Toplam" value={summary.total} />
          <Stat label="Tamamlanan" value={summary.by_status?.completed || 0} cls="text-emerald-600" />
          <Stat label="Planlanan" value={summary.by_status?.scheduled || 0} cls="text-sky-600" />
          <Stat label="Bugünkü Ciro" value={`₺${(summary.revenue || 0).toLocaleString('tr-TR')}`} cls="text-indigo-600" />
        </div>
      )}

      <Tabs defaultValue="appointments">
        <TabsList>
          <TabsTrigger value="appointments">Randevular</TabsTrigger>
          <TabsTrigger value="services">Hizmetler ({services.length})</TabsTrigger>
          <TabsTrigger value="therapists">Terapistler ({therapists.length})</TabsTrigger>
          <TabsTrigger value="rooms">Odalar ({rooms.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="appointments" className="space-y-3">
          <div className="flex gap-2 flex-wrap">
            <Input type="date" value={filter.date_from}
                   onChange={(e) => setFilter({ ...filter, date_from: e.target.value })}
                   className="max-w-[180px]" />
            <select className="border rounded px-2 text-sm"
                    value={filter.therapist_id}
                    onChange={(e) => setFilter({ ...filter, therapist_id: e.target.value })}>
              <option value="">Tüm terapistler</option>
              {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <Card>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 border-b text-left">
                  <tr>
                    <th className="p-2">Saat</th><th className="p-2">Misafir</th>
                    <th className="p-2">Hizmet</th><th className="p-2">Terapist</th>
                    <th className="p-2">Oda</th><th className="p-2">Tutar</th>
                    <th className="p-2">Durum</th><th className="p-2 text-right">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {appointments.length === 0 && (
                    <tr><td colSpan={8} className="p-6 text-center text-gray-500">
                      Randevu yok.</td></tr>
                  )}
                  {appointments.map((a) => {
                    const st = STATUS[a.status] || STATUS.scheduled;
                    return (
                      <tr key={a.id} className="border-b hover:bg-slate-50">
                        <td className="p-2 font-mono text-xs">{fmtTime(a.starts_at)}</td>
                        <td className="p-2">
                          <div>{a.guest_name}</div>
                          {a.guest_phone && <div className="text-xs text-gray-500">{a.guest_phone}</div>}
                        </td>
                        <td className="p-2">{a.service_name}</td>
                        <td className="p-2">{therapistById[a.therapist_id]?.name || '—'}</td>
                        <td className="p-2">{roomById[a.room_id]?.name || '—'}</td>
                        <td className="p-2">
                          ₺{(a.price || 0).toLocaleString('tr-TR')}
                          {a.charge_to_room && <Badge className="ml-1 text-[10px]" variant="outline">→ Folio</Badge>}
                        </td>
                        <td className="p-2"><Badge className={`${st.cls} border-0`}>{st.label}</Badge></td>
                        <td className="p-2 text-right space-x-1">
                          {a.status === 'scheduled' && (
                            <Button size="sm" variant="ghost" title="Başlat"
                                    onClick={() => updateStatus(a.id, 'in_progress')}>
                              <PlayCircle className="w-4 h-4" />
                            </Button>
                          )}
                          {(a.status === 'scheduled' || a.status === 'in_progress') && (
                            <Button size="sm" variant="ghost" title="Tamamla"
                                    onClick={() => updateStatus(a.id, 'completed')}>
                              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            </Button>
                          )}
                          {a.status === 'scheduled' && (
                            <Button size="sm" variant="ghost" title="İptal"
                                    onClick={() => updateStatus(a.id, 'cancelled')}>
                              <XCircle className="w-4 h-4 text-red-500" />
                            </Button>
                          )}
                          <Button size="sm" variant="ghost" onClick={() => remove(a.id)}>
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="services" className="space-y-3">
          <Button size="sm" onClick={() => setShowServiceForm(true)}>
            <Plus className="w-4 h-4 mr-1" /> Hizmet Ekle
          </Button>
          <div className="grid md:grid-cols-3 gap-3">
            {services.map((s) => (
              <Card key={s.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{s.name}</CardTitle>
                  <CardDescription>
                    <Badge variant="outline" className="text-xs">{s.category}</Badge>
                    <span className="ml-2">{s.duration_minutes} dk</span>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-indigo-600">
                    ₺{(s.price || 0).toLocaleString('tr-TR')}
                  </div>
                  {s.commission_rate > 0 && (
                    <div className="text-xs text-gray-500">
                      Komisyon: %{(s.commission_rate * 100).toFixed(0)}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="therapists" className="space-y-3">
          <Button size="sm" onClick={() => setShowTherapistForm(true)}>
            <Plus className="w-4 h-4 mr-1" /> Terapist Ekle
          </Button>
          <div className="grid md:grid-cols-2 gap-3">
            {therapists.length === 0 && (
              <p className="text-sm text-gray-500 col-span-full">Henüz terapist yok.</p>
            )}
            {therapists.map((t) => (
              <Card key={t.id}>
                <CardContent className="p-4 flex items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold flex items-center gap-2">
                      <span className="w-3 h-3 rounded-full" style={{ backgroundColor: t.color }} />
                      {t.name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {t.work_start}–{t.work_end} • Uzmanlık: {(t.specialties || []).join(', ') || '—'}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="rooms" className="space-y-3">
          <Button size="sm" onClick={() => setShowRoomForm(true)}>
            <Plus className="w-4 h-4 mr-1" /> Oda Ekle
          </Button>
          <div className="grid md:grid-cols-3 gap-3">
            {rooms.length === 0 && (
              <p className="text-sm text-gray-500 col-span-full">Henüz tedavi odası yok.</p>
            )}
            {rooms.map((r) => (
              <Card key={r.id}>
                <CardContent className="p-4">
                  <div className="font-semibold flex items-center gap-2">
                    <DoorOpen className="w-4 h-4 text-indigo-600" /> {r.name}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Tip: {r.room_type} • Kapasite: {r.capacity}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>

      {/* ── Booking modal ── */}
      {showBook && (
        <Modal title="Yeni Randevu" onClose={() => setShowBook(false)}>
          <form onSubmit={book} className="space-y-3">
            <Field label="Hizmet">
              <select required className="w-full border rounded px-2 py-1.5"
                      value={bookForm.service_id}
                      onChange={(e) => setBookForm({ ...bookForm, service_id: e.target.value })}>
                <option value="">Seçin…</option>
                {services.map((s) => <option key={s.id} value={s.id}>
                  {s.name} ({s.duration_minutes}dk • ₺{s.price})
                </option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Terapist (otomatik için boş)">
                <select className="w-full border rounded px-2 py-1.5"
                        value={bookForm.therapist_id}
                        onChange={(e) => setBookForm({ ...bookForm, therapist_id: e.target.value })}>
                  <option value="">Otomatik</option>
                  {therapists.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </Field>
              <Field label="Oda">
                <select className="w-full border rounded px-2 py-1.5"
                        value={bookForm.room_id}
                        onChange={(e) => setBookForm({ ...bookForm, room_id: e.target.value })}>
                  <option value="">Otomatik</option>
                  {rooms.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Başlangıç">
              <Input type="datetime-local" required value={bookForm.starts_at}
                     onChange={(e) => setBookForm({ ...bookForm, starts_at: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Misafir Adı">
                <Input required value={bookForm.guest_name}
                       onChange={(e) => setBookForm({ ...bookForm, guest_name: e.target.value })} />
              </Field>
              <Field label="Telefon">
                <Input value={bookForm.guest_phone}
                       onChange={(e) => setBookForm({ ...bookForm, guest_phone: e.target.value })} />
              </Field>
            </div>
            <Field label="PMS Rezervasyon ID (opsiyonel)">
              <Input value={bookForm.reservation_id}
                     onChange={(e) => setBookForm({ ...bookForm, reservation_id: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={bookForm.charge_to_room}
                     onChange={(e) => setBookForm({ ...bookForm, charge_to_room: e.target.checked })} />
              Oda hesabına yansıtılsın
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setShowBook(false)}>İptal</Button>
              <Button type="submit">Randevu Oluştur</Button>
            </div>
          </form>
        </Modal>
      )}

      {showServiceForm && (
        <Modal title="Yeni Hizmet" onClose={() => setShowServiceForm(false)}>
          <form onSubmit={addService} className="space-y-3">
            <Field label="Ad"><Input required value={serviceForm.name}
              onChange={(e) => setServiceForm({ ...serviceForm, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Kategori">
                <select className="w-full border rounded px-2 py-1.5"
                        value={serviceForm.category}
                        onChange={(e) => setServiceForm({ ...serviceForm, category: e.target.value })}>
                  {['massage', 'facial', 'body', 'hydro', 'nail', 'hair'].map((c) =>
                    <option key={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Süre (dk)"><Input type="number" required value={serviceForm.duration_minutes}
                onChange={(e) => setServiceForm({ ...serviceForm, duration_minutes: +e.target.value })} /></Field>
            </div>
            <Field label="Fiyat (₺)"><Input type="number" required value={serviceForm.price}
              onChange={(e) => setServiceForm({ ...serviceForm, price: +e.target.value })} /></Field>
            <div className="flex justify-end gap-2"><Button type="submit">Ekle</Button></div>
          </form>
        </Modal>
      )}

      {showTherapistForm && (
        <Modal title="Yeni Terapist" onClose={() => setShowTherapistForm(false)}>
          <form onSubmit={addTherapist} className="space-y-3">
            <Field label="Ad"><Input required value={therapistForm.name}
              onChange={(e) => setTherapistForm({ ...therapistForm, name: e.target.value })} /></Field>
            <Field label="Uzmanlık (virgülle)">
              <Input placeholder="massage, facial"
                     onChange={(e) => setTherapistForm({
                       ...therapistForm,
                       specialties: e.target.value.split(',').map((x) => x.trim()).filter(Boolean),
                     })} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Mesai Başı"><Input type="time" value={therapistForm.work_start}
                onChange={(e) => setTherapistForm({ ...therapistForm, work_start: e.target.value })} /></Field>
              <Field label="Mesai Sonu"><Input type="time" value={therapistForm.work_end}
                onChange={(e) => setTherapistForm({ ...therapistForm, work_end: e.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2"><Button type="submit">Ekle</Button></div>
          </form>
        </Modal>
      )}

      {showRoomForm && (
        <Modal title="Yeni Oda" onClose={() => setShowRoomForm(false)}>
          <form onSubmit={addRoom} className="space-y-3">
            <Field label="Ad"><Input required value={roomForm.name}
              onChange={(e) => setRoomForm({ ...roomForm, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Tip">
                <select className="w-full border rounded px-2 py-1.5" value={roomForm.room_type}
                        onChange={(e) => setRoomForm({ ...roomForm, room_type: e.target.value })}>
                  {['standard', 'couples', 'wet_room', 'hammam', 'sauna'].map((c) =>
                    <option key={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Kapasite"><Input type="number" min={1} value={roomForm.capacity}
                onChange={(e) => setRoomForm({ ...roomForm, capacity: +e.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2"><Button type="submit">Ekle</Button></div>
          </form>
        </Modal>
      )}
    </div>
    </>
  );
};

const Stat = ({ label, value, cls = 'text-gray-900' }) => (
  <Card><CardContent className="p-4">
    <div className="text-xs text-gray-500">{label}</div>
    <div className={`text-2xl font-bold ${cls}`}>{value}</div>
  </CardContent></Card>
);
const Field = ({ label, children }) => (
  <div><Label className="text-xs">{label}</Label>{children}</div>
);
const Modal = ({ title, onClose, children }) => (
  <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
    <Card className="w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  </div>
);

export default SpaWellness;
