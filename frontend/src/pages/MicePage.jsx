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
import SalesPipelineTab from '@/components/mice/SalesPipelineTab';
import PackagesTab from '@/components/mice/PackagesTab';
import {
  CalendarDays, Plus, Building2, UtensilsCrossed, RefreshCw,
  Trash2, FileText, Users, Sparkles, ClipboardList, ChefHat, Briefcase,
  History as HistoryIcon,
} from 'lucide-react';
import EntityHistoryDrawer from '@/components/EntityHistoryDrawer';
import Layout from '@/components/Layout';

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
const AGENDA_KINDS = ['session', 'meal', 'break', 'av', 'logistics', 'other'];

const MicePage = ({ user, tenant, onLogout }) => {
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState({});
  const [spaces, setSpaces] = useState([]);
  const [menus, setMenus] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showEventForm, setShowEventForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [beoData, setBeoData] = useState(null);
  const [historyEvent, setHistoryEvent] = useState(null);
  const [kitchenData, setKitchenData] = useState(null);
  const [opsData, setOpsData] = useState(null);
  const [opsDate, setOpsDate] = useState(new Date().toISOString().slice(0, 10));
  const [eventTab, setEventTab] = useState('basics');

  const blankEvent = {
    name: '', client_name: '', client_email: '', client_phone: '',
    client_account_id: '', client_contact_id: '',
    organizer_user: '', event_type: 'meeting', status: 'lead',
    expected_pax: 50, start_date: '', end_date: '',
    space_bookings: [{ space_id: '', starts_at: '', ends_at: '',
                       setup_style: 'theatre', expected_pax: 50 }],
    resources: [],
    agenda: [],
    payment_schedule: [],
    notes: '', reservation_id: '',
  };
  const [form, setForm] = useState(blankEvent);

  const load = async () => {
    setLoading(true);
    try {
      const [e, s, m, a, r] = await Promise.all([
        axios.get('/mice/events'),
        axios.get('/mice/spaces'),
        axios.get('/mice/menus'),
        axios.get('/mice/accounts'),
        axios.get('/mice/resources'),
      ]);
      setEvents(e.data.events);
      setSummary(e.data.summary || {});
      setSpaces(s.data.spaces);
      setMenus(m.data.menus);
      setAccounts(a.data.accounts || []);
      setResources(r.data.resources || []);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yüklenemedi');
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const spaceById = useMemo(() => Object.fromEntries(spaces.map((s) => [s.id, s])), [spaces]);
  const accountById = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a])), [accounts]);

  const openNew = () => { setEditing(null); setForm(blankEvent); setEventTab('basics'); setShowEventForm(true); };
  const openEdit = (ev) => {
    setEditing(ev.id);
    setForm({
      name: ev.name, client_name: ev.client_name, client_email: ev.client_email || '',
      client_phone: ev.client_phone || '',
      client_account_id: ev.client_account_id || '',
      client_contact_id: ev.client_contact_id || '',
      organizer_user: ev.organizer_user || '',
      event_type: ev.event_type, status: ev.status, expected_pax: ev.expected_pax,
      start_date: ev.start_date, end_date: ev.end_date,
      space_bookings: ev.space_bookings?.length ? ev.space_bookings : blankEvent.space_bookings,
      resources: ev.resources || [],
      agenda: ev.agenda || [],
      payment_schedule: ev.payment_schedule || [],
      notes: ev.notes || '', reservation_id: ev.reservation_id || '',
    });
    setEventTab('basics');
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
    let body = { status };
    if (status === 'cancelled') {
      const reason = prompt('İptal/lost-business sebebi (en az 10 karakter):', '');
      if (reason === null) return;
      if (reason.trim().length < 10) {
        toast.error('En az 10 karakter sebep gereklidir');
        return;
      }
      body.reason = reason.trim();
    }
    try {
      await axios.post(`/mice/events/${id}/status`, body);
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
    catch { toast.error('BEO alınamadı'); }
  };
  const showKitchen = async (id) => {
    try { const r = await axios.get(`/mice/events/${id}/kitchen-ticket`); setKitchenData(r.data); }
    catch (err) { toast.error(err.response?.data?.detail || 'Mutfak fişi alınamadı'); }
  };
  const showOpsSheet = async () => {
    try { const r = await axios.get('/mice/ops-sheet', { params: { date: opsDate } }); setOpsData(r.data); }
    catch (err) { toast.error(err.response?.data?.detail || 'Ops sheet alınamadı'); }
  };

  const markPaid = async (eventId, idx) => {
    const ref = prompt('Ödeme referansı (banka/işlem no):', '') || '';
    try {
      await axios.post(`/mice/events/${eventId}/payment-schedule/${idx}/mark-paid`,
        null, { params: ref ? { reference: ref } : {} });
      toast.success('Ödeme işaretlendi');
      await load();
      // refresh BEO if open
      if (beoData?.event?.id === eventId) showBeo(eventId);
    } catch (err) { toast.error(err.response?.data?.detail || 'İşaretlenemedi'); }
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
      menu_id: '', inventory_id: '', name: '', type: 'fb',
      quantity: 1, unit: 'pax', unit_price: 0,
    }],
  });
  const rmRes = (i) => setForm({ ...form, resources: form.resources.filter((_, k) => k !== i) });

  const setAg = (i, patch) => {
    const next = [...form.agenda]; next[i] = { ...next[i], ...patch };
    setForm({ ...form, agenda: next });
  };
  const addAg = () => setForm({
    ...form, agenda: [...form.agenda, {
      starts_at: '', ends_at: '', title: '', kind: 'session',
      location: '', owner: '', notes: '',
    }],
  });
  const rmAg = (i) => setForm({ ...form, agenda: form.agenda.filter((_, k) => k !== i) });

  const setPs = (i, patch) => {
    const next = [...form.payment_schedule]; next[i] = { ...next[i], ...patch };
    setForm({ ...form, payment_schedule: next });
  };
  const addPs = () => setForm({
    ...form, payment_schedule: [...form.payment_schedule, {
      due_date: '', label: 'Depozito', amount: 0, paid: false,
    }],
  });
  const rmPs = (i) => setForm({
    ...form, payment_schedule: form.payment_schedule.filter((_, k) => k !== i),
  });

  if (loading) {
    return <div className="p-8 text-center text-gray-500">
      <RefreshCw className="w-6 h-6 animate-spin inline" /> Yükleniyor…
    </div>;
  }

  const totalPipeline = Object.values(summary).reduce((a, b) => a + (b.total_value || 0), 0);
  const psTotal = form.payment_schedule.reduce((a, p) => a + (Number(p.amount) || 0), 0);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="mice">
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
        <div className="flex gap-2 flex-wrap">
          <Input type="date" value={opsDate} onChange={(e) => setOpsDate(e.target.value)}
                 className="max-w-[160px]" />
          <Button variant="outline" onClick={showOpsSheet}>
            <ClipboardList className="w-4 h-4 mr-1" /> Günün Ops Sheet'i
          </Button>
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
          <TabsTrigger value="accounts">Müşteriler ({accounts.length})</TabsTrigger>
          <TabsTrigger value="spaces">Mekanlar ({spaces.length})</TabsTrigger>
          <TabsTrigger value="menus">Menüler & Paketler ({menus.length})</TabsTrigger>
          <TabsTrigger value="resources">Envanter ({resources.length})</TabsTrigger>
          <TabsTrigger value="pipeline">Satış Pipeline</TabsTrigger>
          <TabsTrigger value="packages">Paketler</TabsTrigger>
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
                  const acct = ev.client_account_id && accountById[ev.client_account_id];
                  return (
                    <tr key={ev.id} className="border-b hover:bg-slate-50">
                      <td className="p-2">
                        <div className="font-semibold">{ev.name}</div>
                        <div className="text-xs text-gray-500">{ev.event_type}</div>
                      </td>
                      <td className="p-2">
                        <div>{ev.client_name}</div>
                        {acct && <div className="text-xs text-indigo-600 flex items-center gap-1">
                          <Briefcase className="w-3 h-3" /> {acct.name}
                        </div>}
                      </td>
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
                        {ev.lost_reason && <div className="text-xs text-red-600 mt-1 max-w-[160px]"
                          title={ev.lost_reason}>↳ {ev.lost_reason.slice(0, 30)}…</div>}
                      </td>
                      <td className="p-2 text-right space-x-1 whitespace-nowrap">
                        <Button size="sm" variant="ghost" title="BEO"
                                onClick={() => showBeo(ev.id)}>
                          <FileText className="w-4 h-4" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Mutfak Fişi"
                                onClick={() => showKitchen(ev.id)}>
                          <ChefHat className="w-4 h-4" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Değişiklik Geçmişi"
                                onClick={() => setHistoryEvent(ev)}>
                          <HistoryIcon className="w-4 h-4" />
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
          <DiaryView spaceById={spaceById} spaces={spaces} />
        </TabsContent>

        <TabsContent value="accounts">
          <AccountsView accounts={accounts} reload={load} />
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
                    {m.dietary_tags?.length > 0 && m.dietary_tags.map((d) =>
                      <Badge key={d} variant="outline" className="text-xs ml-1">{d}</Badge>
                    )}
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
                  {m.courses?.length > 0 && (
                    <div className="text-xs text-gray-600 mt-2">
                      {m.courses.length} kurs: {m.courses.map((c) => c.name).join(', ')}
                    </div>
                  )}
                  {m.allergens?.length > 0 && (
                    <div className="text-xs text-red-600 mt-1">
                      Alerjenler: {m.allergens.join(', ')}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="resources">
          <ResourcesView resources={resources} reload={load} />
        </TabsContent>

        <TabsContent value="pipeline">
          <SalesPipelineTab accounts={accounts} />
        </TabsContent>

        <TabsContent value="packages">
          <PackagesTab />
        </TabsContent>
      </Tabs>

      {/* Event create/edit */}
      {showEventForm && (
        <Modal title={editing ? 'Etkinlik Düzenle' : 'Yeni Etkinlik'}
               onClose={() => setShowEventForm(false)} wide>
          <form onSubmit={submit} className="space-y-3">
            <Tabs value={eventTab} onValueChange={setEventTab}>
              <TabsList>
                <TabsTrigger value="basics">Temel</TabsTrigger>
                <TabsTrigger value="spaces">Mekan & Kaynak</TabsTrigger>
                <TabsTrigger value="agenda">Fonksiyon Sheet</TabsTrigger>
                <TabsTrigger value="payment">Ödeme Takvimi</TabsTrigger>
              </TabsList>

              <TabsContent value="basics" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Etkinlik Adı"><Input required value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
                  <Field label="Müşteri Adı"><Input required value={form.client_name}
                    onChange={(e) => setForm({ ...form, client_name: e.target.value })} /></Field>
                  <Field label="Kurumsal Hesap (opsiyonel)">
                    <select className="w-full border rounded px-2 py-1.5"
                            value={form.client_account_id}
                            onChange={(e) => {
                              const id = e.target.value;
                              const acct = accountById[id];
                              setForm({ ...form, client_account_id: id,
                                client_name: acct?.name || form.client_name });
                            }}>
                      <option value="">— Seçilmedi —</option>
                      {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                  </Field>
                  <Field label="Organizatör Kullanıcı"><Input value={form.organizer_user}
                    onChange={(e) => setForm({ ...form, organizer_user: e.target.value })} /></Field>
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
                <Field label="Notlar">
                  <textarea className="w-full border rounded px-2 py-1.5 text-sm min-h-[60px]"
                            value={form.notes}
                            onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                </Field>
              </TabsContent>

              <TabsContent value="spaces" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
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
                      <select className="col-span-3 border rounded px-1 py-1 text-xs"
                              value={r.menu_id || ''}
                              onChange={(e) => {
                                const m = menus.find((x) => x.id === e.target.value);
                                setRes(i, {
                                  menu_id: e.target.value,
                                  inventory_id: '',
                                  name: m?.name || r.name,
                                  type: m?.type || r.type,
                                });
                              }}>
                        <option value="">— Menü —</option>
                        {menus.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                      </select>
                      <select className="col-span-3 border rounded px-1 py-1 text-xs"
                              value={r.inventory_id || ''}
                              onChange={(e) => {
                                const inv = resources.find((x) => x.id === e.target.value);
                                setRes(i, {
                                  inventory_id: e.target.value,
                                  menu_id: '',
                                  name: inv?.name || r.name,
                                  type: inv?.type || r.type,
                                  unit_price: inv?.unit_price || r.unit_price,
                                });
                              }}>
                        <option value="">— Envanter —</option>
                        {resources.map((x) => <option key={x.id} value={x.id}>{x.name} (stok {x.total_stock})</option>)}
                      </select>
                      <Input className="col-span-2 text-xs" placeholder="Ad" value={r.name}
                             onChange={(e) => setRes(i, { name: e.target.value })} />
                      <Input className="col-span-1 text-xs" type="number" placeholder="Adet" value={r.quantity}
                             onChange={(e) => setRes(i, { quantity: +e.target.value })} />
                      <Input className="col-span-2 text-xs" type="number" placeholder="Birim ₺" value={r.unit_price}
                             onChange={(e) => setRes(i, { unit_price: +e.target.value })} />
                      <Button type="button" size="sm" variant="ghost" className="col-span-1"
                              onClick={() => rmRes(i)}><Trash2 className="w-3 h-3" /></Button>
                    </div>
                  ))}
                  {form.resources.length > 0 && (
                    <p className="text-xs text-gray-500">
                      Envanter seçilirse sistem tüm aktif etkinliklerdeki kullanım toplanır; stok aşılırsa 409.
                    </p>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="agenda" className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-sm font-semibold">
                    Dakika Bazlı Fonksiyon Sheet ({form.agenda.length} kalem)
                  </Label>
                  <Button type="button" size="sm" variant="outline" onClick={addAg}>
                    <Plus className="w-3 h-3 mr-1" /> Satır Ekle
                  </Button>
                </div>
                {form.agenda.length === 0 && (
                  <p className="text-xs text-gray-500 text-center p-4 border rounded">
                    Karşılama, açılış, ana yemek, AV testi gibi kalemleri ekleyerek tam fonksiyon sheet oluşturun.
                  </p>
                )}
                {form.agenda.map((a, i) => (
                  <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
                    <Input className="col-span-2 text-xs" type="datetime-local"
                           value={a.starts_at?.slice(0, 16) || ''}
                           onChange={(e) => setAg(i, { starts_at: e.target.value })} required />
                    <Input className="col-span-2 text-xs" type="datetime-local"
                           value={a.ends_at?.slice(0, 16) || ''}
                           onChange={(e) => setAg(i, { ends_at: e.target.value })} required />
                    <Input className="col-span-3 text-xs" placeholder="Başlık" value={a.title}
                           onChange={(e) => setAg(i, { title: e.target.value })} required />
                    <select className="col-span-2 border rounded px-1 py-1 text-xs"
                            value={a.kind}
                            onChange={(e) => setAg(i, { kind: e.target.value })}>
                      {AGENDA_KINDS.map((k) => <option key={k}>{k}</option>)}
                    </select>
                    <Input className="col-span-2 text-xs" placeholder="Sorumlu" value={a.owner || ''}
                           onChange={(e) => setAg(i, { owner: e.target.value })} />
                    <Button type="button" size="sm" variant="ghost" className="col-span-1"
                            onClick={() => rmAg(i)}><Trash2 className="w-3 h-3" /></Button>
                  </div>
                ))}
              </TabsContent>

              <TabsContent value="payment" className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-sm font-semibold">
                    Ödeme Takvimi ({form.payment_schedule.length} satır, toplam ₺{psTotal.toLocaleString('tr-TR')})
                  </Label>
                  <Button type="button" size="sm" variant="outline" onClick={addPs}>
                    <Plus className="w-3 h-3 mr-1" /> Taksit Ekle
                  </Button>
                </div>
                {form.payment_schedule.length === 0 && (
                  <p className="text-xs text-gray-500 text-center p-4 border rounded">
                    Depozito + bakiye taksit planı ekleyebilirsiniz.
                  </p>
                )}
                {form.payment_schedule.map((p, i) => (
                  <div key={i} className="grid grid-cols-12 gap-1 mb-1.5 items-center">
                    <Input className="col-span-3 text-xs" type="date" value={p.due_date || ''}
                           onChange={(e) => setPs(i, { due_date: e.target.value })} required />
                    <Input className="col-span-4 text-xs" placeholder="Etiket (Depozito %30)"
                           value={p.label}
                           onChange={(e) => setPs(i, { label: e.target.value })} required />
                    <Input className="col-span-3 text-xs" type="number" placeholder="Tutar ₺"
                           value={p.amount}
                           onChange={(e) => setPs(i, { amount: +e.target.value })} required />
                    <label className="col-span-1 text-xs text-center flex items-center gap-1">
                      <input type="checkbox" checked={p.paid || false}
                             onChange={(e) => setPs(i, { paid: e.target.checked })} />
                      Öd.
                    </label>
                    <Button type="button" size="sm" variant="ghost" className="col-span-1"
                            onClick={() => rmPs(i)}><Trash2 className="w-3 h-3" /></Button>
                  </div>
                ))}
              </TabsContent>
            </Tabs>

            <div className="flex justify-end gap-2 pt-2 border-t">
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
              {beoData.event.lost_reason && (
                <Info l="Lost/Cancel Sebebi" v={beoData.event.lost_reason} cls="text-red-600" />
              )}
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

            {beoData.agenda?.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Fonksiyon Sheet</h4>
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-slate-50"><tr>
                    <th className="border p-1">Saat</th>
                    <th className="border p-1 text-left">Başlık</th>
                    <th className="border p-1">Tip</th>
                    <th className="border p-1">Sorumlu</th>
                  </tr></thead>
                  <tbody>
                    {beoData.agenda.map((a, i) => (
                      <tr key={i}>
                        <td className="border p-1 font-mono">
                          {a.starts_at?.slice(11, 16)}–{a.ends_at?.slice(11, 16)}
                        </td>
                        <td className="border p-1">{a.title}</td>
                        <td className="border p-1 text-center">{a.kind}</td>
                        <td className="border p-1">{a.owner || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

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
                      <td className="border p-1 text-right">
                        ₺{(r.quantity * r.unit_price).toLocaleString('tr-TR')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {beoData.payment_schedule?.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm mb-1">Ödeme Takvimi</h4>
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-slate-50"><tr>
                    <th className="border p-1">Vade</th>
                    <th className="border p-1 text-left">Etiket</th>
                    <th className="border p-1 text-right">Tutar</th>
                    <th className="border p-1">Durum</th>
                    <th className="border p-1">Aksiyon</th>
                  </tr></thead>
                  <tbody>
                    {beoData.payment_schedule.map((p, i) => (
                      <tr key={i}>
                        <td className="border p-1 font-mono">{p.due_date}</td>
                        <td className="border p-1">{p.label}</td>
                        <td className="border p-1 text-right">₺{p.amount?.toLocaleString('tr-TR')}</td>
                        <td className="border p-1 text-center">
                          {p.paid ? <Badge className="bg-emerald-100 text-emerald-800 border-0">Ödendi</Badge>
                                  : <Badge className="bg-amber-100 text-amber-800 border-0">Bekliyor</Badge>}
                          {p.reference && <div className="text-[10px] text-gray-500 mt-0.5">Ref: {p.reference}</div>}
                        </td>
                        <td className="border p-1 text-center">
                          {!p.paid && (
                            <Button size="sm" variant="ghost"
                                    onClick={() => markPaid(beoData.event.id, i)}>
                              Öde
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

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

      {/* Kitchen ticket modal */}
      {kitchenData && (
        <Modal title={`Mutfak Fişi — ${kitchenData.event_name}`}
               onClose={() => setKitchenData(null)} wide>
          <div className="space-y-3 text-sm">
            <Card><CardContent className="p-3 grid grid-cols-3 gap-2 text-xs">
              <Info l="Beklenen Pax" v={kitchenData.expected_pax} />
              <Info l="İlk Servis" v={kitchenData.first_service_at?.slice(0, 16) || '—'} />
              <Info l="Toplam Hat" v={kitchenData.tickets.length} />
            </CardContent></Card>

            {kitchenData.all_allergens?.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded p-2 text-xs">
                <strong className="text-red-700">⚠ Alerjenler:</strong> {kitchenData.all_allergens.join(', ')}
              </div>
            )}
            {kitchenData.all_dietary_tags?.length > 0 && (
              <div className="bg-emerald-50 border border-emerald-200 rounded p-2 text-xs">
                <strong className="text-emerald-700">Diyet Etiketleri:</strong> {kitchenData.all_dietary_tags.join(', ')}
              </div>
            )}

            {kitchenData.tickets.length === 0 ? (
              <p className="text-center text-gray-500 p-4">F&B menü hattı yok.</p>
            ) : (
              kitchenData.tickets.map((t, i) => (
                <Card key={i}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <ChefHat className="w-4 h-4 text-amber-600" />
                      {t.menu_name} × {t.qty_pax} pax
                    </CardTitle>
                    <CardDescription>
                      Hazırlık tamamlanmalı: <span className="font-mono font-bold text-red-600">
                        {t.prep_by?.slice(0, 16) || '—'}
                      </span> ({t.prep_lead_minutes}dk lead)
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {t.courses?.length > 0 && (
                      <table className="w-full text-xs border-collapse">
                        <thead className="bg-slate-50"><tr>
                          <th className="border p-1">Kurs</th>
                          <th className="border p-1 text-left">Yemek</th>
                          <th className="border p-1 text-left">Açıklama</th>
                        </tr></thead>
                        <tbody>
                          {t.courses.map((c, j) => (
                            <tr key={j}>
                              <td className="border p-1 text-center">{c.course_type}</td>
                              <td className="border p-1 font-semibold">{c.name}</td>
                              <td className="border p-1 text-gray-600">{c.description || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {t.allergens?.length > 0 && (
                      <div className="text-xs text-red-600 mt-2">
                        Alerjenler: {t.allergens.join(', ')}
                      </div>
                    )}
                    {t.dietary_tags?.length > 0 && (
                      <div className="text-xs text-emerald-600 mt-1">
                        Diyet: {t.dietary_tags.join(', ')}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))
            )}

            <div className="text-right">
              <Button variant="outline" onClick={() => window.print()}>Yazdır</Button>
              <Button variant="ghost" onClick={() => setKitchenData(null)}>Kapat</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Entity history drawer */}
      {historyEvent && (
        <EntityHistoryDrawer
          entityType="mice_event"
          entityId={historyEvent.id}
          title={`${historyEvent.name} (${historyEvent.start_date})`}
          onClose={() => setHistoryEvent(null)} />
      )}

      {/* Ops sheet modal */}
      {opsData && (
        <Modal title={`Günün Ops Sheet'i — ${opsData.date}`}
               onClose={() => setOpsData(null)} wide>
          <div className="space-y-3 text-sm">
            {opsData.rows.length === 0 ? (
              <p className="text-center text-gray-500 p-4">Bu tarih için aktif etkinlik yok.</p>
            ) : (
              <table className="w-full text-xs border-collapse">
                <thead className="bg-slate-50"><tr>
                  <th className="border p-1">Saat</th>
                  <th className="border p-1 text-left">Etkinlik</th>
                  <th className="border p-1 text-left">Müşteri</th>
                  <th className="border p-1">Mekan</th>
                  <th className="border p-1">Düzen / Pax</th>
                  <th className="border p-1">Sorumlu</th>
                  <th className="border p-1 text-left">Ajanda Özeti</th>
                </tr></thead>
                <tbody>
                  {opsData.rows.map((r, i) => (
                    <tr key={i}>
                      <td className="border p-1 font-mono">
                        {r.starts_at?.slice(11, 16)}–{r.ends_at?.slice(11, 16)}
                      </td>
                      <td className="border p-1 font-semibold">{r.event_name}</td>
                      <td className="border p-1">{r.client_name}</td>
                      <td className="border p-1">{r.space_name}</td>
                      <td className="border p-1 text-center">{r.setup_style} / {r.expected_pax}</td>
                      <td className="border p-1">{r.organizer_user || '—'}</td>
                      <td className="border p-1">
                        {r.agenda_summary?.length === 0 ? <span className="text-gray-400">—</span> : (
                          <ul className="text-[11px] space-y-0.5">
                            {r.agenda_summary.map((a, j) => (
                              <li key={j}>
                                <span className="font-mono">{a.starts_at?.slice(11, 16)}</span>
                                {' '}{a.title} <span className="text-gray-400">[{a.kind}]</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="text-right">
              <Button variant="outline" onClick={() => window.print()}>Yazdır</Button>
              <Button variant="ghost" onClick={() => setOpsData(null)}>Kapat</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
    </Layout>
  );
};

const DAYS_TR = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
const MONTHS_TR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
                   'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

const DiaryView = ({ spaceById, spaces }) => {
  const today = new Date();
  const [view, setView] = useState('calendar');
  const [calMonth, setCalMonth] = useState({ year: today.getFullYear(), month: today.getMonth() });
  const [selectedDate, setSelectedDate] = useState(null);
  const [items, setItems] = useState([]);

  const monthRange = useMemo(() => {
    const { year, month } = calMonth;
    const from = `${year}-${String(month + 1).padStart(2, '0')}-01`;
    const lastDay = new Date(year, month + 1, 0).getDate();
    const to = `${year}-${String(month + 1).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
    return { from, to, lastDay };
  }, [calMonth]);

  useEffect(() => {
    axios.get('/mice/diary', { params: { date_from: monthRange.from, date_to: monthRange.to } })
      .then((r) => setItems(r.data.events || []))
      .catch(() => toast.error('Takvim yüklenemedi'));
  }, [monthRange.from, monthRange.to]);

  const eventsByDate = useMemo(() => {
    const map = {};
    items.forEach((ev) => {
      const start = new Date(ev.start_date);
      const end = new Date(ev.end_date || ev.start_date);
      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        if (!map[key]) map[key] = [];
        if (!map[key].find((e) => e.id === ev.id)) map[key].push(ev);
      }
    });
    return map;
  }, [items]);

  const calendarDays = useMemo(() => {
    const { year, month } = calMonth;
    let startWeekday = new Date(year, month, 1).getDay() - 1;
    if (startWeekday < 0) startWeekday = 6;
    const days = [];
    for (let i = 0; i < startWeekday; i++) days.push(null);
    for (let d = 1; d <= monthRange.lastDay; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const dayEvents = eventsByDate[dateStr] || [];
      const bookedSpaceIds = new Set();
      dayEvents.forEach((ev) => (ev.space_bookings || []).forEach((sb) => bookedSpaceIds.add(sb.space_id)));
      days.push({
        day: d, dateStr, events: dayEvents,
        bookedCount: bookedSpaceIds.size,
        freeCount: Math.max(0, (spaces?.length || 0) - bookedSpaceIds.size),
      });
    }
    return days;
  }, [calMonth, eventsByDate, spaces, monthRange.lastDay]);

  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const prevMonth = () => setCalMonth((p) => p.month === 0 ? { year: p.year - 1, month: 11 } : { ...p, month: p.month - 1 });
  const nextMonth = () => setCalMonth((p) => p.month === 11 ? { year: p.year + 1, month: 0 } : { ...p, month: p.month + 1 });
  const goToday = () => { setCalMonth({ year: today.getFullYear(), month: today.getMonth() }); setSelectedDate(todayStr); };

  const selectedDayEvents = selectedDate ? (eventsByDate[selectedDate] || []) : [];
  const selectedDayBookedIds = new Set();
  selectedDayEvents.forEach((ev) => (ev.space_bookings || []).forEach((sb) => selectedDayBookedIds.add(sb.space_id)));
  const selectedDayFreeSpaces = (spaces || []).filter((s) => !selectedDayBookedIds.has(s.id));
  const selectedDayBookedSpaces = (spaces || []).filter((s) => selectedDayBookedIds.has(s.id));

  return (
    <Card><CardContent className="p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={prevMonth}>‹</Button>
          <div className="font-semibold min-w-[140px] text-center">
            {MONTHS_TR[calMonth.month]} {calMonth.year}
          </div>
          <Button variant="outline" size="sm" onClick={nextMonth}>›</Button>
          <Button variant="outline" size="sm" onClick={goToday}>Bugün</Button>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 text-xs">
            <span className="inline-block w-3 h-3 rounded bg-indigo-100 border border-indigo-300" /> Etkinlik
            <span className="inline-block w-3 h-3 rounded bg-emerald-100 border border-emerald-300 ml-2" /> Müsait
          </div>
          <Button variant={view === 'calendar' ? 'default' : 'outline'} size="sm" onClick={() => setView('calendar')}>Takvim</Button>
          <Button variant={view === 'list' ? 'default' : 'outline'} size="sm" onClick={() => setView('list')}>Liste</Button>
        </div>
      </div>

      {view === 'calendar' ? (
        <div className="grid md:grid-cols-[1fr_320px] gap-3">
          <div>
            <div className="grid grid-cols-7 gap-1 mb-1">
              {DAYS_TR.map((d) => (
                <div key={d} className="text-center text-xs font-semibold text-gray-500 py-1">{d}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {calendarDays.map((cell, idx) => {
                if (!cell) return <div key={`empty-${idx}`} className="h-20 bg-slate-50/40 rounded" />;
                const isToday = cell.dateStr === todayStr;
                const isSelected = cell.dateStr === selectedDate;
                const hasEvents = cell.events.length > 0;
                return (
                  <button
                    key={cell.dateStr}
                    onClick={() => setSelectedDate(cell.dateStr)}
                    className={`h-20 rounded border p-1 text-left transition hover:border-indigo-400 hover:shadow-sm ${
                      isSelected ? 'border-indigo-500 ring-2 ring-indigo-200 bg-indigo-50/60'
                        : isToday ? 'border-indigo-300 bg-indigo-50/30'
                        : hasEvents ? 'border-slate-200 bg-white'
                        : 'border-slate-100 bg-white'
                    }`}
                  >
                    <div className={`text-xs font-semibold ${isToday ? 'text-indigo-700' : 'text-gray-700'}`}>{cell.day}</div>
                    {hasEvents && (
                      <div className="mt-0.5">
                        <div className="text-[10px] inline-flex items-center gap-1 px-1 py-0.5 rounded bg-indigo-100 text-indigo-700">
                          <CalendarDays className="w-2.5 h-2.5" /> {cell.events.length}
                        </div>
                      </div>
                    )}
                    {(spaces?.length || 0) > 0 && (
                      <div className="mt-0.5 text-[10px] text-emerald-700">
                        {cell.freeCount}/{spaces.length} müsait
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="border rounded-lg p-3 bg-slate-50/50">
            {selectedDate ? (
              <>
                <div className="font-semibold text-sm mb-2 flex items-center gap-2">
                  <CalendarDays className="w-4 h-4 text-indigo-600" />
                  {selectedDate}
                </div>
                <div className="text-xs text-gray-600 mb-2">
                  {selectedDayEvents.length} etkinlik • {selectedDayFreeSpaces.length} müsait mekan
                </div>
                {selectedDayEvents.length > 0 && (
                  <div className="space-y-1.5 mb-3">
                    <div className="text-[11px] font-semibold text-gray-500 uppercase">Etkinlikler</div>
                    {selectedDayEvents.map((ev) => (
                      <div key={ev.id} className="bg-white rounded border p-2">
                        <div className="flex items-start justify-between gap-1">
                          <div className="font-semibold text-xs">{ev.name}</div>
                          <Badge className={`${STATUS[ev.status]?.cls || ''} border-0 text-[10px]`}>{STATUS[ev.status]?.label}</Badge>
                        </div>
                        <div className="text-[11px] text-gray-500 mt-0.5">
                          {ev.client_name} • {ev.expected_pax} pax
                        </div>
                        <div className="text-[11px] text-gray-600 mt-0.5">
                          {(ev.space_bookings || []).map((sb) => spaceById[sb.space_id]?.name).filter(Boolean).join(', ')}
                        </div>
                        <div className="text-[11px] font-semibold mt-0.5">
                          ₺{(ev.totals?.grand_total || 0).toLocaleString('tr-TR')}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {selectedDayBookedSpaces.length > 0 && (
                  <div className="space-y-1 mb-3">
                    <div className="text-[11px] font-semibold text-gray-500 uppercase">Dolu Mekanlar</div>
                    <div className="flex flex-wrap gap-1">
                      {selectedDayBookedSpaces.map((s) => (
                        <Badge key={s.id} variant="outline" className="text-[10px] bg-rose-50 border-rose-200 text-rose-700">{s.name}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {selectedDayFreeSpaces.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[11px] font-semibold text-gray-500 uppercase">Müsait Mekanlar</div>
                    <div className="flex flex-wrap gap-1">
                      {selectedDayFreeSpaces.map((s) => (
                        <Badge key={s.id} variant="outline" className="text-[10px] bg-emerald-50 border-emerald-200 text-emerald-700">{s.name}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-xs text-gray-500 text-center py-8">
                Detay için bir gün seçin
              </div>
            )}
          </div>
        </div>
      ) : (
        items.length === 0 ? (
          <p className="text-sm text-gray-500 p-4 text-center">Bu ayda etkinlik yok.</p>
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
        )
      )}
    </CardContent></Card>
  );
};

const AccountsView = ({ accounts, reload }) => {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', tax_no: '', city: '', industry: 'corporate',
                                     credit_limit: 0, payment_terms_days: 30 });
  const [expandedId, setExpandedId] = useState(null);
  const [contactsCache, setContactsCache] = useState({});
  const [contactForm, setContactForm] = useState(null); // {account_id, name, title, email, phone}

  const create = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/mice/accounts', form);
      toast.success('Hesap oluşturuldu');
      setShowForm(false);
      setForm({ name: '', tax_no: '', city: '', industry: 'corporate',
                credit_limit: 0, payment_terms_days: 30 });
      await reload();
    } catch (err) { toast.error(err.response?.data?.detail || 'Hata'); }
  };
  const remove = async (id) => {
    if (!confirm('Hesap silinsin mi?')) return;
    try { await axios.delete(`/mice/accounts/${id}`); await reload(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };
  const expand = async (id) => {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    if (!contactsCache[id]) {
      try {
        const r = await axios.get(`/mice/accounts/${id}/contacts`);
        setContactsCache((c) => ({ ...c, [id]: r.data.contacts }));
      } catch { toast.error('Kişiler yüklenemedi'); }
    }
  };
  const addContact = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`/mice/accounts/${contactForm.account_id}/contacts`, contactForm);
      const r = await axios.get(`/mice/accounts/${contactForm.account_id}/contacts`);
      setContactsCache((c) => ({ ...c, [contactForm.account_id]: r.data.contacts }));
      setContactForm(null);
      toast.success('Kişi eklendi');
    } catch (err) { toast.error(err.response?.data?.detail || 'Eklenemedi'); }
  };

  return (
    <Card><CardContent className="p-3">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-semibold">Kurumsal Müşteriler ({accounts.length})</h3>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus className="w-3 h-3 mr-1" /> Yeni Hesap
        </Button>
      </div>
      {accounts.length === 0 && <p className="text-center text-gray-500 p-4">Henüz hesap yok.</p>}
      <div className="space-y-1">
        {accounts.map((a) => (
          <div key={a.id} className="border rounded">
            <div className="flex items-center gap-2 p-2 hover:bg-slate-50 cursor-pointer"
                 onClick={() => expand(a.id)}>
              <Briefcase className="w-4 h-4 text-indigo-600" />
              <div className="flex-1">
                <div className="font-semibold text-sm">{a.name}</div>
                <div className="text-xs text-gray-500">
                  {a.tax_no && `VKN ${a.tax_no} • `}{a.city || ''} • {a.industry}
                  {a.credit_limit > 0 && ` • Kredi limiti ₺${a.credit_limit.toLocaleString('tr-TR')}`}
                </div>
              </div>
              <Badge variant="outline" className="text-xs">
                {a.payment_terms_days}gün vade
              </Badge>
              <Button size="sm" variant="ghost" onClick={(e) => {
                e.stopPropagation();
                setContactForm({ account_id: a.id, name: '', title: '', email: '', phone: '', is_primary: false });
              }}>
                <Plus className="w-3 h-3" /> Kişi
              </Button>
              <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); remove(a.id); }}>
                <Trash2 className="w-3 h-3" />
              </Button>
            </div>
            {expandedId === a.id && (
              <div className="bg-slate-50 p-2 border-t">
                {(contactsCache[a.id] || []).length === 0 ? (
                  <p className="text-xs text-gray-500">Henüz kişi yok.</p>
                ) : (
                  <table className="w-full text-xs">
                    <thead><tr className="text-gray-500">
                      <th className="text-left p-1">Ad</th>
                      <th className="text-left p-1">Unvan</th>
                      <th className="text-left p-1">E-posta</th>
                      <th className="text-left p-1">Telefon</th>
                      <th>Birincil</th>
                    </tr></thead>
                    <tbody>
                      {(contactsCache[a.id] || []).map((c) => (
                        <tr key={c.id} className="border-t">
                          <td className="p-1 font-medium">{c.name}</td>
                          <td className="p-1">{c.title}</td>
                          <td className="p-1">{c.email}</td>
                          <td className="p-1">{c.phone}</td>
                          <td className="p-1 text-center">{c.is_primary ? '✓' : ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {showForm && (
        <Modal title="Yeni Kurumsal Hesap" onClose={() => setShowForm(false)}>
          <form onSubmit={create} className="space-y-2">
            <Field label="Şirket Adı"><Input required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Vergi No"><Input value={form.tax_no}
                onChange={(e) => setForm({ ...form, tax_no: e.target.value })} /></Field>
              <Field label="Şehir"><Input value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })} /></Field>
              <Field label="Sektör">
                <select className="w-full border rounded px-2 py-1.5" value={form.industry}
                        onChange={(e) => setForm({ ...form, industry: e.target.value })}>
                  {['corporate', 'travel_agency', 'government', 'ngo', 'other'].map((x) => <option key={x}>{x}</option>)}
                </select>
              </Field>
              <Field label="Vade (gün)"><Input type="number" value={form.payment_terms_days}
                onChange={(e) => setForm({ ...form, payment_terms_days: +e.target.value })} /></Field>
              <Field label="Kredi Limiti ₺"><Input type="number" value={form.credit_limit}
                onChange={(e) => setForm({ ...form, credit_limit: +e.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>İptal</Button>
              <Button type="submit">Oluştur</Button>
            </div>
          </form>
        </Modal>
      )}
      {contactForm && (
        <Modal title="Yeni Kişi" onClose={() => setContactForm(null)}>
          <form onSubmit={addContact} className="space-y-2">
            <Field label="Ad Soyad"><Input required value={contactForm.name}
              onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })} /></Field>
            <Field label="Unvan"><Input value={contactForm.title}
              onChange={(e) => setContactForm({ ...contactForm, title: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="E-posta"><Input type="email" value={contactForm.email}
                onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })} /></Field>
              <Field label="Telefon"><Input value={contactForm.phone}
                onChange={(e) => setContactForm({ ...contactForm, phone: e.target.value })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={contactForm.is_primary}
                     onChange={(e) => setContactForm({ ...contactForm, is_primary: e.target.checked })} />
              Birincil kişi
            </label>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setContactForm(null)}>İptal</Button>
              <Button type="submit">Ekle</Button>
            </div>
          </form>
        </Modal>
      )}
    </CardContent></Card>
  );
};

const ResourcesView = ({ resources, reload }) => {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'av', total_stock: 1, unit: 'unit',
                                     unit_price: 0, currency: 'TRY' });
  const create = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/mice/resources', form);
      toast.success('Envanter eklendi');
      setShowForm(false);
      setForm({ name: '', type: 'av', total_stock: 1, unit: 'unit', unit_price: 0, currency: 'TRY' });
      await reload();
    } catch (err) { toast.error(err.response?.data?.detail || 'Hata'); }
  };
  const remove = async (id) => {
    if (!confirm('Silinsin mi?')) return;
    try { await axios.delete(`/mice/resources/${id}`); await reload(); }
    catch (err) { toast.error(err.response?.data?.detail || 'Silinemedi'); }
  };

  return (
    <Card><CardContent className="p-3">
      <div className="flex justify-between items-center mb-3">
        <h3 className="font-semibold">Kaynak Envanteri (AV / Dekor)</h3>
        <Button size="sm" onClick={() => setShowForm(true)}>
          <Plus className="w-3 h-3 mr-1" /> Yeni Kaynak
        </Button>
      </div>
      {resources.length === 0 && <p className="text-center text-gray-500 p-4">Envanter yok.</p>}
      <div className="grid md:grid-cols-3 gap-2">
        {resources.map((r) => (
          <Card key={r.id}>
            <CardContent className="p-3">
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-semibold">{r.name}</div>
                  <div className="text-xs text-gray-500">{r.type}</div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => remove(r.id)}>
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
              <div className="mt-2 text-sm">
                Stok: <span className="font-bold">{r.total_stock}</span> {r.unit}
              </div>
              <div className="text-sm">
                Birim: <span className="font-bold">₺{r.unit_price?.toLocaleString('tr-TR')}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {showForm && (
        <Modal title="Yeni Kaynak" onClose={() => setShowForm(false)}>
          <form onSubmit={create} className="space-y-2">
            <Field label="Ad"><Input required value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Tip">
                <select className="w-full border rounded px-2 py-1.5" value={form.type}
                        onChange={(e) => setForm({ ...form, type: e.target.value })}>
                  {['av', 'decor', 'fb', 'other'].map((x) => <option key={x}>{x}</option>)}
                </select>
              </Field>
              <Field label="Birim"><Input value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })} /></Field>
              <Field label="Toplam Stok"><Input type="number" required value={form.total_stock}
                onChange={(e) => setForm({ ...form, total_stock: +e.target.value })} /></Field>
              <Field label="Birim ₺"><Input type="number" value={form.unit_price}
                onChange={(e) => setForm({ ...form, unit_price: +e.target.value })} /></Field>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>İptal</Button>
              <Button type="submit">Oluştur</Button>
            </div>
          </form>
        </Modal>
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
    <Card className={`w-full ${wide ? 'max-w-5xl' : 'max-w-lg'} max-h-[90vh] overflow-hidden flex flex-col`}
          onClick={(e) => e.stopPropagation()}>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="overflow-y-auto">{children}</CardContent>
    </Card>
  </div>
);

export default MicePage;
