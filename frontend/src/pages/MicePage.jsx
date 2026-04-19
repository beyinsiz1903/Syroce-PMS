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
import {
  CalendarDays, Plus, Building2, UtensilsCrossed, RefreshCw,
  Trash2, FileText, Users, Sparkles,
} from 'lucide-react';

const STATUS = {
  lead: { label: 'Lead', cls: 'bg-slate-100 text-slate-700' },
  tentative: { label: 'Tentative', cls: 'bg-amber-100 text-amber-800' },
  definite: { label: 'Definite', cls: 'bg-sky-100 text-sky-800' },
  confirmed: { label: 'Confirmed', cls: 'bg-emerald-100 text-emerald-800' },
  completed: { label: 'Tamamlandı', cls: 'bg-purple-100 text-purple-800' },
  cancelled: { label: 'İptal', cls: 'bg-red-100 text-red-800' },
};

const SETUPS = ['theatre', 'classroom', 'banquet', 'cocktail', 'u_shape', 'boardroom'];
const EVENT_TYPES = ['meeting', 'conference', 'wedding', 'gala', 'training', 'other'];

const MicePage = () => {
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState({});
  const [spaces, setSpaces] = useState([]);
  const [menus, setMenus] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showEventForm, setShowEventForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [beoData, setBeoData] = useState(null);

  const blankEvent = {
    name: '', client_name: '', client_email: '', client_phone: '',
    organizer_user: '', event_type: 'meeting', status: 'lead',
    expected_pax: 50, start_date: '', end_date: '',
    space_bookings: [{ space_id: '', starts_at: '', ends_at: '',
                       setup_style: 'theatre', expected_pax: 50 }],
    resources: [],
    notes: '', reservation_id: '',
  };
  const [form, setForm] = useState(blankEvent);

  const load = async () => {
    setLoading(true);
    try {
      const [e, s, m] = await Promise.all([
        axios.get('/mice/events'),
        axios.get('/mice/spaces'),
        axios.get('/mice/menus'),
      ]);
      setEvents(e.data.events);
      setSummary(e.data.summary || {});
      setSpaces(s.data.spaces);
      setMenus(m.data.menus);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yüklenemedi');
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const spaceById = useMemo(() => Object.fromEntries(spaces.map((s) => [s.id, s])), [spaces]);

  const openNew = () => { setEditing(null); setForm(blankEvent); setShowEventForm(true); };
  const openEdit = (ev) => {
    setEditing(ev.id);
    setForm({
      name: ev.name, client_name: ev.client_name, client_email: ev.client_email || '',
      client_phone: ev.client_phone || '', organizer_user: ev.organizer_user || '',
      event_type: ev.event_type, status: ev.status, expected_pax: ev.expected_pax,
      start_date: ev.start_date, end_date: ev.end_date,
      space_bookings: ev.space_bookings?.length ? ev.space_bookings : blankEvent.space_bookings,
      resources: ev.resources || [],
      notes: ev.notes || '', reservation_id: ev.reservation_id || '',
    });
    setShowEventForm(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    try {
      const url = editing ? `/mice/events/${editing}` : '/mice/events';
      const method = editing ? 'put' : 'post';
      await axios[method](url, form);
      toast.success(editing ? 'Etkinlik güncellendi' : 'Etkinlik oluşturuldu');
      setShowEventForm(false);
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    }
  };

  const changeStatus = async (id, status) => {
    try {
      await axios.post(`/mice/events/${id}/status`, { status });
      toast.success('Durum güncellendi');
      await load();
    } catch (err) { toast.error(err.response?.data?.detail || 'Hata'); }
  };

  const remove = async (id) => {
    if (!confirm('Etkinlik silinsin mi?')) return;
    try { await axios.delete(`/mice/events/${id}`); await load(); }
    catch { toast.error('Silinemedi'); }
  };

  const showBeo = async (id) => {
    try { const r = await axios.get(`/mice/events/${id}/beo`); setBeoData(r.data); }
    catch (err) { toast.error('BEO alınamadı'); }
  };

  // ── Form helpers ──
  const setSb = (i, patch) => {
    const next = [...form.space_bookings]; next[i] = { ...next[i], ...patch };
    setForm({ ...form, space_bookings: next });
  };
  const addSb = () => setForm({
    ...form, space_bookings: [...form.space_bookings, {
      space_id: '', starts_at: '', ends_at: '',
      setup_style: 'theatre', expected_pax: form.expected_pax,
    }],
  });
  const rmSb = (i) => setForm({
    ...form, space_bookings: form.space_bookings.filter((_, k) => k !== i),
  });

  const setRes = (i, patch) => {
    const next = [...form.resources]; next[i] = { ...next[i], ...patch };
    setForm({ ...form, resources: next });
  };
  const addRes = () => setForm({
    ...form, resources: [...form.resources, {
      menu_id: '', name: '', type: 'fb', quantity: 1, unit: 'pax', unit_price: 0,
    }],
  });
  const rmRes = (i) => setForm({ ...form, resources: form.resources.filter((_, k) => k !== i) });

  if (loading) {
    return <div className="p-8 text-center text-gray-500">
      <RefreshCw className="w-6 h-6 animate-spin inline" /> Yükleniyor…
    </div>;
  }

  const totalPipeline = Object.values(summary).reduce((a, b) => a + (b.total_value || 0), 0);

  return (
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CalendarDays className="w-6 h-6 text-indigo-600" />
            MICE & Banquet
          </h1>
          <p className="text-sm text-gray-500">
            Toplantı, konferans, gala ve düğün etkinliklerinin tam satış döngüsü.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1" /> Yenile
          </Button>
          <Button onClick={openNew}><Plus className="w-4 h-4 mr-1" /> Yeni Etkinlik</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Toplam Etkinlik" value={events.length} />
        {['tentative', 'definite', 'confirmed'].map((k) => (
          <Stat key={k} label={STATUS[k].label}
                value={`${summary[k]?.count || 0} • ₺${(summary[k]?.total_value || 0).toLocaleString('tr-TR')}`}
                cls={STATUS[k].cls.split(' ')[1].replace('text-', 'text-')} />
        ))}
        <Stat label="Toplam Pipeline"
              value={`₺${totalPipeline.toLocaleString('tr-TR')}`} cls="text-emerald-600" />
      </div>

      <Tabs defaultValue="events">
        <TabsList>
          <TabsTrigger value="events">Etkinlikler</TabsTrigger>
          <TabsTrigger value="diary">Function Diary</TabsTrigger>
          <TabsTrigger value="spaces">Mekanlar ({spaces.length})</TabsTrigger>
          <TabsTrigger value="menus">Menüler & Paketler ({menus.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="events">
          <Card><CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b text-left">
                <tr>
                  <th className="p-2">Etkinlik</th><th className="p-2">Müşteri</th>
                  <th className="p-2">Tarih</th><th className="p-2">Pax</th>
                  <th className="p-2">Mekanlar</th><th className="p-2">Tutar</th>
                  <th className="p-2">Durum</th><th className="p-2 text-right">İşlem</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 && <tr><td colSpan={8} className="p-6 text-center text-gray-500">
                  Etkinlik yok.</td></tr>}
                {events.map((ev) => {
                  const st = STATUS[ev.status] || STATUS.lead;
                  return (
                    <tr key={ev.id} className="border-b hover:bg-slate-50">
                      <td className="p-2">
                        <div className="font-semibold">{ev.name}</div>
                        <div className="text-xs text-gray-500">{ev.event_type}</div>
                      </td>
                      <td className="p-2">{ev.client_name}</td>
                      <td className="p-2 font-mono text-xs">{ev.start_date} → {ev.end_date}</td>
                      <td className="p-2 text-center">{ev.expected_pax}</td>
                      <td className="p-2">
                        {(ev.space_bookings || []).map((sb, i) => (
                          <div key={i} className="text-xs">
                            {spaceById[sb.space_id]?.name || '?'} • {sb.setup_style}
                          </div>
                        ))}
                      </td>
                      <td className="p-2 font-semibold">₺{(ev.totals?.grand_total || 0).toLocaleString('tr-TR')}</td>
                      <td className="p-2">
                        <Badge className={`${st.cls} border-0`}>{st.label}</Badge>
                      </td>
                      <td className="p-2 text-right space-x-1">
                        <Button size="sm" variant="ghost" title="BEO"
                                onClick={() => showBeo(ev.id)}>
                          <FileText className="w-4 h-4" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => openEdit(ev)}>Düzenle</Button>
                        {ev.status !== 'completed' && ev.status !== 'cancelled' && (
                          <select className="text-xs border rounded px-1"
                                  value={ev.status}
                                  onChange={(e) => changeStatus(ev.id, e.target.value)}>
                            {Object.entries(STATUS).map(([k, v]) =>
                              <option key={k} value={k}>→ {v.label}</option>)}
                          </select>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => remove(ev.id)}>
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="diary">
          <DiaryView spaceById={spaceById} />
        </TabsContent>

        <TabsContent value="spaces">
          <div className="grid md:grid-cols-2 gap-3">
            {spaces.map((s) => (
              <Card key={s.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Building2 className="w-4 h-4 text-indigo-600" /> {s.name}
                  </CardTitle>
                  <CardDescription>{s.location} • {s.area_m2} m²</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                    {[
                      ['Tiyatro', s.capacity_theatre], ['Sınıf', s.capacity_classroom],
                      ['Banket', s.capacity_banquet], ['Cocktail', s.capacity_cocktail],
                      ['U Şekli', s.capacity_u_shape], ['Boardroom', s.capacity_boardroom],
                    ].filter(([, v]) => v > 0).map(([l, v]) => (
                      <div key={l} className="bg-slate-50 rounded p-1.5 text-center">
                        <div className="text-gray-500">{l}</div>
                        <div className="font-bold">{v}</div>
                      </div>
                    ))}
                  </div>
                  <div className="text-sm">
                    <span className="text-gray-500">Saatlik:</span> ₺{s.hourly_rate.toLocaleString('tr-TR')} •{' '}
                    <span className="text-gray-500">Günlük:</span> ₺{s.daily_rate.toLocaleString('tr-TR')}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="menus">
          <div className="grid md:grid-cols-3 gap-3">
            {menus.map((m) => (
              <Card key={m.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base flex items-center gap-2">
                    {m.type === 'fb' ? <UtensilsCrossed className="w-4 h-4 text-amber-600" /> :
                     m.type === 'av' ? <Sparkles className="w-4 h-4 text-sky-600" /> :
                     <Sparkles className="w-4 h-4 text-pink-600" />}
                    {m.name}
                  </CardTitle>
                  <CardDescription>
                    <Badge variant="outline" className="text-xs">{m.type}</Badge>
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {m.price_per_person > 0 ? (
                    <div className="text-xl font-bold">₺{m.price_per_person.toLocaleString('tr-TR')}
                      <span className="text-xs text-gray-500"> /kişi</span></div>
                  ) : (
                    <div className="text-xl font-bold">₺{m.flat_price.toLocaleString('tr-TR')}
                      <span className="text-xs text-gray-500"> sabit</span></div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>

      {/* Event create/edit */}
      {showEventForm && (
        <Modal title={editing ? 'Etkinlik Düzenle' : 'Yeni Etkinlik'}
               onClose={() => setShowEventForm(false)} wide>
          <form onSubmit={submit} className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Etkinlik Adı"><Input required value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
              <Field label="Müşteri"><Input required value={form.client_name}
                onChange={(e) => setForm({ ...form, client_name: e.target.value })} /></Field>
              <Field label="Müşteri E-posta"><Input value={form.client_email}
                onChange={(e) => setForm({ ...form, client_email: e.target.value })} /></Field>
              <Field label="Müşteri Telefon"><Input value={form.client_phone}
                onChange={(e) => setForm({ ...form, client_phone: e.target.value })} /></Field>
              <Field label="Tip">
                <select className="w-full border rounded px-2 py-1.5" value={form.event_type}
                        onChange={(e) => setForm({ ...form, event_type: e.target.value })}>
                  {EVENT_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="Durum">
                <select className="w-full border rounded px-2 py-1.5" value={form.status}
                        onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  {Object.entries(STATUS).map(([k, v]) =>
                    <option key={k} value={k}>{v.label}</option>)}
                </select>
              </Field>
              <Field label="Beklenen Pax"><Input type="number" required value={form.expected_pax}
                onChange={(e) => setForm({ ...form, expected_pax: +e.target.value })} /></Field>
              <Field label="PMS Rezervasyon ID"><Input value={form.reservation_id}
                onChange={(e) => setForm({ ...form, reservation_id: e.target.value })} /></Field>
              <Field label="Başlangıç Tarihi"><Input type="date" required value={form.start_date}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
              <Field label="Bitiş Tarihi"><Input type="date" required value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <Label className="text-sm font-semibold">Mekan Rezervasyonları</Label>
                <Button type="button" size="sm" variant="outline" onClick={addSb}>
                  <Plus className="w-3 h-3 mr-1" /> Mekan Ekle
                </Button>
              </div>
              {form.space_bookings.map((sb, i) => (
                <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
                  <select className="col-span-3 border rounded px-1 py-1 text-xs"
                          value={sb.space_id}
                          onChange={(e) => setSb(i, { space_id: e.target.value })}>
                    <option value="">Mekan…</option>
                    {spaces.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                  <Input className="col-span-3 text-xs" type="datetime-local" value={sb.starts_at?.slice(0, 16) || ''}
                         onChange={(e) => setSb(i, { starts_at: e.target.value })} />
                  <Input className="col-span-3 text-xs" type="datetime-local" value={sb.ends_at?.slice(0, 16) || ''}
                         onChange={(e) => setSb(i, { ends_at: e.target.value })} />
                  <select className="col-span-2 border rounded px-1 py-1 text-xs"
                          value={sb.setup_style}
                          onChange={(e) => setSb(i, { setup_style: e.target.value })}>
                    {SETUPS.map((s) => <option key={s}>{s}</option>)}
                  </select>
                  <Button type="button" size="sm" variant="ghost" className="col-span-1"
                          onClick={() => rmSb(i)}><Trash2 className="w-3 h-3" /></Button>
                </div>
              ))}
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <Label className="text-sm font-semibold">Kaynak / Menü Hatları</Label>
                <Button type="button" size="sm" variant="outline" onClick={addRes}>
                  <Plus className="w-3 h-3 mr-1" /> Kaynak Ekle
                </Button>
              </div>
              {form.resources.map((r, i) => (
                <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
                  <select className="col-span-4 border rounded px-1 py-1 text-xs"
                          value={r.menu_id || ''}
                          onChange={(e) => {
                            const m = menus.find((x) => x.id === e.target.value);
                            setRes(i, {
                              menu_id: e.target.value,
                              name: m?.name || r.name,
                              type: m?.type || r.type,
                            });
                          }}>
                    <option value="">— Özel —</option>
                    {menus.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                  <Input className="col-span-3 text-xs" placeholder="Açıklama" value={r.name}
                         onChange={(e) => setRes(i, { name: e.target.value })} />
                  <Input className="col-span-2 text-xs" type="number" placeholder="Adet" value={r.quantity}
                         onChange={(e) => setRes(i, { quantity: +e.target.value })} />
                  <Input className="col-span-2 text-xs" type="number" placeholder="Birim ₺" value={r.unit_price}
                         onChange={(e) => setRes(i, { unit_price: +e.target.value })} />
                  <Button type="button" size="sm" variant="ghost" className="col-span-1"
                          onClick={() => rmRes(i)}><Trash2 className="w-3 h-3" /></Button>
                </div>
              ))}
              {form.resources.length > 0 && (
                <p className="text-xs text-gray-500">
                  Menü seçilirse fiyat ve birim otomatik dolar (Per-person menüler beklenen pax sayısıyla çarpılır).
                </p>
              )}
            </div>

            <Field label="Notlar">
              <textarea className="w-full border rounded px-2 py-1.5 text-sm min-h-[60px]"
                        value={form.notes}
                        onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </Field>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setShowEventForm(false)}>İptal</Button>
              <Button type="submit">{editing ? 'Güncelle' : 'Oluştur'}</Button>
            </div>
          </form>
        </Modal>
      )}

      {/* BEO modal */}
      {beoData && (
        <Modal title={`BEO — ${beoData.event.name}`} onClose={() => setBeoData(null)} wide>
          <div className="space-y-3 text-sm">
            <Card><CardContent className="p-3 grid grid-cols-2 gap-2 text-xs">
              <Info l="Müşteri" v={beoData.event.client_name} />
              <Info l="Tip" v={beoData.event.event_type} />
              <Info l="Pax" v={beoData.event.expected_pax} />
              <Info l="Tarih" v={`${beoData.event.start_date} → ${beoData.event.end_date}`} />
              <Info l="E-posta" v={beoData.event.client_email} />
              <Info l="Telefon" v={beoData.event.client_phone} />
            </CardContent></Card>

            <div>
              <h4 className="font-semibold text-sm mb-1">Mekanlar</h4>
              <table className="w-full text-xs border-collapse">
                <thead className="bg-slate-50"><tr>
                  <th className="border p-1 text-left">Mekan</th>
                  <th className="border p-1">Düzen</th>
                  <th className="border p-1">Pax</th>
                  <th className="border p-1">Başla</th>
                  <th className="border p-1">Bitir</th>
                </tr></thead>
                <tbody>
                  {beoData.spaces.map((s, i) => (
                    <tr key={i}>
                      <td className="border p-1">{s.space_name}</td>
                      <td className="border p-1 text-center">{s.setup_style}</td>
                      <td className="border p-1 text-center">{s.expected_pax}</td>
                      <td className="border p-1 font-mono">{s.starts_at?.slice(0, 16)}</td>
                      <td className="border p-1 font-mono">{s.ends_at?.slice(0, 16)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div>
              <h4 className="font-semibold text-sm mb-1">Kaynaklar</h4>
              <table className="w-full text-xs border-collapse">
                <thead className="bg-slate-50"><tr>
                  <th className="border p-1 text-left">Hat</th>
                  <th className="border p-1">Tip</th>
                  <th className="border p-1">Adet</th>
                  <th className="border p-1">Birim ₺</th>
                  <th className="border p-1 text-right">Toplam ₺</th>
                </tr></thead>
                <tbody>
                  {beoData.resources.map((r, i) => (
                    <tr key={i}>
                      <td className="border p-1">{r.name}</td>
                      <td className="border p-1 text-center">{r.type}</td>
                      <td className="border p-1 text-center">{r.quantity}</td>
                      <td className="border p-1 text-right">{r.unit_price?.toLocaleString('tr-TR')}</td>
                      <td className="border p-1 text-right font-semibold">
                        ₺{(r.quantity * r.unit_price).toLocaleString('tr-TR')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Card><CardContent className="p-3 grid grid-cols-3 gap-2 text-xs">
              <Info l="Mekan Toplamı" v={`₺${(beoData.event.totals?.space_total || 0).toLocaleString('tr-TR')}`} />
              <Info l="Kaynak Toplamı" v={`₺${(beoData.event.totals?.resources_total || 0).toLocaleString('tr-TR')}`} />
              <Info l="GRAND TOTAL" v={`₺${(beoData.event.totals?.grand_total || 0).toLocaleString('tr-TR')}`}
                    cls="text-lg text-indigo-600 font-bold" />
            </CardContent></Card>

            <div className="text-right">
              <Button variant="outline" onClick={() => window.print()}>Yazdır</Button>
              <Button variant="ghost" onClick={() => setBeoData(null)}>Kapat</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

const DiaryView = ({ spaceById }) => {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().slice(0, 10);
  const end = new Date(today.getFullYear(), today.getMonth() + 2, 0).toISOString().slice(0, 10);
  const [from, setFrom] = useState(start);
  const [to, setTo] = useState(end);
  const [items, setItems] = useState([]);
  useEffect(() => {
    axios.get('/mice/diary', { params: { date_from: from, date_to: to } })
      .then((r) => setItems(r.data.events))
      .catch(() => toast.error('Diary yüklenemedi'));
  }, [from, to]);
  return (
    <Card><CardContent className="p-3">
      <div className="flex gap-2 mb-3">
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="max-w-[180px]" />
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="max-w-[180px]" />
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-gray-500 p-4 text-center">Bu aralıkta etkinlik yok.</p>
      ) : (
        <div className="space-y-1">
          {items.map((ev) => (
            <div key={ev.id} className="flex items-center gap-2 p-2 border rounded hover:bg-slate-50">
              <CalendarDays className="w-4 h-4 text-indigo-600" />
              <div className="font-mono text-xs w-44">{ev.start_date} → {ev.end_date}</div>
              <div className="flex-1">
                <div className="font-semibold text-sm">{ev.name}</div>
                <div className="text-xs text-gray-500">
                  {ev.client_name} • {ev.expected_pax} pax •{' '}
                  {(ev.space_bookings || []).map((sb) => spaceById[sb.space_id]?.name).filter(Boolean).join(', ')}
                </div>
              </div>
              <Badge className={`${STATUS[ev.status]?.cls || ''} border-0`}>{STATUS[ev.status]?.label}</Badge>
              <div className="font-semibold text-sm w-28 text-right">
                ₺{(ev.totals?.grand_total || 0).toLocaleString('tr-TR')}
              </div>
            </div>
          ))}
        </div>
      )}
    </CardContent></Card>
  );
};

const Stat = ({ label, value, cls = 'text-gray-900' }) => (
  <Card><CardContent className="p-4">
    <div className="text-xs text-gray-500">{label}</div>
    <div className={`text-xl font-bold ${cls}`}>{value}</div>
  </CardContent></Card>
);
const Field = ({ label, children }) => (
  <div><Label className="text-xs">{label}</Label>{children}</div>
);
const Info = ({ l, v, cls = '' }) => (
  <div><div className="text-gray-500">{l}</div><div className={cls || 'font-medium'}>{v || '—'}</div></div>
);
const Modal = ({ title, onClose, children, wide }) => (
  <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
    <Card className={`w-full ${wide ? 'max-w-4xl' : 'max-w-lg'}`} onClick={(e) => e.stopPropagation()}>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  </div>
);

export default MicePage;
