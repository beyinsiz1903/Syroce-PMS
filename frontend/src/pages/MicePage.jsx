import { useEffect, useMemo, useState, Suspense, lazy } from 'react';
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
// Tur 5: pipeline ve packages tab'ları sadece tıklanınca yüklenir.
// R4: BanquetCompetitorTab da lazy — sadece "competitors" tab'ı açılınca yüklenir.
const SalesPipelineTab = lazy(() => import('@/components/mice/SalesPipelineTab'));
const PackagesTab = lazy(() => import('@/components/mice/PackagesTab'));
const BanquetCompetitorTab = lazy(() => import('@/components/mice/BanquetCompetitorTab'));
import AccountsView from '@/components/mice/AccountsView';
import DiaryView from '@/components/mice/DiaryView';
import ResourcesView from '@/components/mice/ResourcesView';
import OperationsPanel from '@/components/mice/OperationsPanel';
import { Stat, Field, Info, Modal } from '@/components/mice/_shared';
import {
  CalendarDays, Plus, Building2, UtensilsCrossed, RefreshCw,
  Trash2, FileText, Users, Sparkles, ClipboardList, ChefHat, Briefcase,
  History as HistoryIcon, Pencil,
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
  // tab badge counts come from /mice/events response; survives lazy-loaded
  // collections so tab labels stay accurate before the user opens that tab.
  const [counts, setCounts] = useState({});
  const [spaces, setSpaces] = useState([]);
  const [menus, setMenus] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [resources, setResources] = useState([]);
  // Tracks which tab payloads have been fetched so we don't refetch on
  // every tab change. Mount populates events/spaces/accounts (needed by
  // the default Etkinlikler tab listing); menus/resources are lazy.
  const [loadedTabs, setLoadedTabs] = useState(() => new Set());
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('events');
  // Tur 5: TabsContent global forceMount yaptığı için lazy chunk'lar
  // panel mount olur olmaz indiriliyordu. visitedMiceTabs koşulu ile
  // pipeline/packages componentleri ancak kullanıcı sekmeye geçince
  // instantiate edilir. Bir kez ziyaret edildiğinde DOM'da kalır,
  // tekrar dönünce yeniden chunk fetch yok.
  const [visitedMiceTabs, setVisitedMiceTabs] = useState(() => new Set(['events']));
  useEffect(() => {
    setVisitedMiceTabs((prev) => (prev.has(activeTab) ? prev : new Set([...prev, activeTab])));
  }, [activeTab]);
  const [showEventForm, setShowEventForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [beoData, setBeoData] = useState(null);
  const [historyEvent, setHistoryEvent] = useState(null);
  const [kitchenData, setKitchenData] = useState(null);
  const [opsData, setOpsData] = useState(null);
  const [opsDate, setOpsDate] = useState(new Date().toISOString().slice(0, 10));
  const [eventTab, setEventTab] = useState('basics');

  const blankTechReq = {
    projector: false, screen: false, microphone_wired: 0, microphone_wireless: 0,
    sound_system: false, stage: false, lighting: false, livestream: false,
    internet_mbps: 0, translation_booths: 0, notes: '',
  };
  const blankEntertainment = {
    type: 'none', name: '', contact: '', start_at: '', end_at: '',
    requirements: '', fee: 0,
  };
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
    technical_requirements: { ...blankTechReq },
    staff_assignments: [],
    entertainment: { ...blankEntertainment },
  };
  const [form, setForm] = useState(blankEvent);

  const blankMenu = {
    name: '', type: 'fb', price_per_person: 0, flat_price: 0,
    currency: 'TRY', description: '', active: true,
    dietary_tags: [], allergens: [], min_guests: 0, prep_lead_minutes: 30,
    // courses are preserved on edit (no UI yet); kept here so PUT does not wipe them.
    courses: [],
  };
  const [showMenuForm, setShowMenuForm] = useState(false);
  const [editingMenu, setEditingMenu] = useState(null);
  const [menuForm, setMenuForm] = useState(blankMenu);

  // Targeted refreshers used by CRUD handlers below so a single mutation
  // doesn't refetch all five collections.
  const markLoaded = (key) => setLoadedTabs((prev) => {
    if (prev.has(key)) return prev;
    const next = new Set(prev);
    next.add(key);
    return next;
  });
  const loadEvents = async () => {
    const e = await axios.get('/mice/events');
    setEvents(e.data.events);
    setSummary(e.data.summary || {});
    setCounts(e.data.counts || {});
    markLoaded('events');
  };
  const loadSpaces = async () => {
    const s = await axios.get('/mice/spaces');
    setSpaces(s.data.spaces);
    markLoaded('spaces');
  };
  const loadMenus = async () => {
    const m = await axios.get('/mice/menus');
    setMenus(m.data.menus);
    markLoaded('menus');
  };
  const loadAccountsList = async () => {
    const a = await axios.get('/mice/accounts');
    setAccounts(a.data.accounts || []);
    markLoaded('accounts');
  };
  const loadResourcesList = async () => {
    const r = await axios.get('/mice/resources');
    setResources(r.data.resources || []);
    markLoaded('resources');
  };

  // Initial mount: events + spaces + accounts only.
  // The default "Etkinlikler" tab renders space and customer names per
  // event row, so those two sibling collections are required up-front.
  // menus and resources are deferred until the user opens those tabs
  // or starts the event form (which needs them for selection).
  const load = async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadEvents(), loadSpaces(), loadAccountsList(),
      ]);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yüklenemedi');
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  // Tab open → fetch on first reveal only. Mutation handlers call the
  // direct loadX helpers so they always refetch, even before that tab
  // was opened (keeps cached badge counts in sync).
  const ensureTabLoaded = (tab) => {
    if (loadedTabs.has(tab)) return;
    if (tab === 'menus') loadMenus().catch((e) =>
      toast.error(e.response?.data?.detail || 'Menüler yüklenemedi'));
    else if (tab === 'resources') loadResourcesList().catch((e) =>
      toast.error(e.response?.data?.detail || 'Envanter yüklenemedi'));
  };
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    ensureTabLoaded(tab);
  };

  // Event form needs menus + resources for the selection dropdowns; load
  // them on demand the first time the form opens.
  const ensureFormCollections = () => {
    if (!loadedTabs.has('menus')) loadMenus().catch(() => {});
    if (!loadedTabs.has('resources')) loadResourcesList().catch(() => {});
  };

  const spaceById = useMemo(() => Object.fromEntries(spaces.map((s) => [s.id, s])), [spaces]);
  const accountById = useMemo(() => Object.fromEntries(accounts.map((a) => [a.id, a])), [accounts]);

  const openNew = () => {
    ensureFormCollections();
    setEditing(null); setForm(blankEvent); setEventTab('basics'); setShowEventForm(true);
  };
  const openEdit = (ev) => {
    ensureFormCollections();
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
      technical_requirements: { ...blankTechReq, ...(ev.technical_requirements || {}) },
      staff_assignments: ev.staff_assignments || [],
      entertainment: { ...blankEntertainment, ...(ev.entertainment || {}) },
    });
    setEventTab('basics');
    setShowEventForm(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    try {
      // Normalize: empty datetime strings → null; entertainment.type==='none'
      // means user did not configure entertainment, so omit object entirely.
      const payload = { ...form };
      const ent = payload.entertainment || {};
      if (!ent.type || ent.type === 'none') {
        payload.entertainment = null;
      } else {
        payload.entertainment = {
          ...ent,
          start_at: ent.start_at || null,
          end_at: ent.end_at || null,
        };
      }
      // Drop empty technical_requirements object (all-falsy/zero) so backend
      // stores null rather than an empty config blob.
      const tr = payload.technical_requirements || {};
      const trHasValue = Object.values(tr).some(
        (v) => v && (typeof v !== 'string' || v.trim()));
      if (!trHasValue) payload.technical_requirements = null;

      // Normalize datetime fields inside staff_assignments too.
      payload.staff_assignments = (payload.staff_assignments || []).map((s) => ({
        ...s,
        start_at: s.start_at || null,
        end_at: s.end_at || null,
      }));

      const url = editing ? `/mice/events/${editing}` : '/mice/events';
      const method = editing ? 'put' : 'post';
      await axios[method](url, payload);
      toast.success(editing ? 'Etkinlik güncellendi' : 'Etkinlik oluşturuldu');
      setShowEventForm(false);
      await loadEvents();
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
      await loadEvents();
    } catch (err) { toast.error(err.response?.data?.detail || 'Hata'); }
  };

  const remove = async (id) => {
    if (!confirm('Etkinlik silinsin mi?')) return;
    try { await axios.delete(`/mice/events/${id}`); await loadEvents(); }
    catch { toast.error('Silinemedi'); }
  };

  // ── Menu CRUD ──
  const openNewMenu = () => {
    setEditingMenu(null);
    setMenuForm(blankMenu);
    setShowMenuForm(true);
  };
  const openEditMenu = (m) => {
    setEditingMenu(m.id);
    setMenuForm({
      name: m.name || '',
      type: m.type || 'fb',
      price_per_person: m.price_per_person || 0,
      flat_price: m.flat_price || 0,
      currency: m.currency || 'TRY',
      description: m.description || '',
      active: m.active !== false,
      dietary_tags: m.dietary_tags || [],
      allergens: m.allergens || [],
      min_guests: m.min_guests || 0,
      prep_lead_minutes: m.prep_lead_minutes ?? 30,
      // Preserve courses across edit — backend uses $set: model_dump() so
      // omitting this field would silently wipe existing kitchen course data.
      courses: m.courses || [],
    });
    setShowMenuForm(true);
  };
  const submitMenu = async (e) => {
    e.preventDefault();
    if (!menuForm.name.trim()) { toast.error('Ad zorunludur'); return; }
    if (menuForm.price_per_person <= 0 && menuForm.flat_price <= 0) {
      toast.error('Kişi başı veya sabit fiyatlardan biri girilmelidir');
      return;
    }
    try {
      const payload = {
        ...menuForm,
        price_per_person: Number(menuForm.price_per_person) || 0,
        flat_price: Number(menuForm.flat_price) || 0,
        min_guests: Number(menuForm.min_guests) || 0,
        prep_lead_minutes: Number(menuForm.prep_lead_minutes) || 0,
        description: menuForm.description?.trim() || null,
      };
      if (editingMenu) {
        await axios.put(`/mice/menus/${editingMenu}`, payload);
        toast.success('Menü güncellendi');
      } else {
        await axios.post('/mice/menus', payload);
        toast.success('Menü oluşturuldu');
      }
      setShowMenuForm(false);
      await loadMenus();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Kaydedilemedi');
    }
  };
  const removeMenu = async (id, name) => {
    if (!confirm(`"${name}" silinsin mi?`)) return;
    try {
      await axios.delete(`/mice/menus/${id}`);
      toast.success('Silindi');
      await loadMenus();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Silinemedi');
    }
  };
  const toggleTag = (field, val) => {
    const list = menuForm[field] || [];
    setMenuForm({
      ...menuForm,
      [field]: list.includes(val) ? list.filter((x) => x !== val) : [...list, val],
    });
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
      await loadEvents();
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

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="events">Etkinlikler</TabsTrigger>
          <TabsTrigger value="diary">Function Diary</TabsTrigger>
          <TabsTrigger value="accounts">Müşteriler ({loadedTabs.has('accounts') ? accounts.length : (counts.accounts ?? '…')})</TabsTrigger>
          <TabsTrigger value="spaces">Mekanlar ({loadedTabs.has('spaces') ? spaces.length : (counts.spaces ?? '…')})</TabsTrigger>
          <TabsTrigger value="menus">Menüler & Paketler ({loadedTabs.has('menus') ? menus.length : (counts.menus ?? '…')})</TabsTrigger>
          <TabsTrigger value="resources">Envanter ({loadedTabs.has('resources') ? resources.length : (counts.resources ?? '…')})</TabsTrigger>
          <TabsTrigger value="pipeline">Satış Pipeline</TabsTrigger>
          <TabsTrigger value="packages">Paketler</TabsTrigger>
          <TabsTrigger value="competitors">Rakip Analizi</TabsTrigger>
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
          <AccountsView accounts={accounts} reload={loadAccountsList} />
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
          <div className="flex justify-between items-center mb-3">
            <p className="text-sm text-gray-500">
              F&B menüleri, AV ve dekorasyon paketleri. Etkinlik kaynaklarına eklenir.
            </p>
            <Button size="sm" onClick={openNewMenu}>
              <Plus className="w-4 h-4 mr-1" /> Yeni Menü / Paket
            </Button>
          </div>
          {menus.length === 0 && (
            <div className="text-center py-12 text-gray-500 text-sm">
              Henüz menü eklenmemiş. "Yeni Menü / Paket" butonuyla ekleyin.
            </div>
          )}
          <div className="grid md:grid-cols-3 gap-3">
            {menus.map((m) => (
              <Card key={m.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      {m.type === 'fb' ? <UtensilsCrossed className="w-4 h-4 text-amber-600" /> :
                       m.type === 'av' ? <Sparkles className="w-4 h-4 text-sky-600" /> :
                       <Sparkles className="w-4 h-4 text-pink-600" />}
                      {m.name}
                    </CardTitle>
                    <div className="flex gap-1 shrink-0">
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
                              onClick={() => openEditMenu(m)} title="Düzenle">
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-600"
                              onClick={() => removeMenu(m.id, m.name)} title="Sil">
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                  <CardDescription>
                    <Badge variant="outline" className="text-xs">{m.type}</Badge>
                    {m.active === false && (
                      <Badge variant="outline" className="text-xs ml-1 text-gray-500">pasif</Badge>
                    )}
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
                  {m.description && (
                    <div className="text-xs text-gray-600 mt-1">{m.description}</div>
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
                  {(m.min_guests > 0 || m.prep_lead_minutes > 0) && (
                    <div className="text-xs text-gray-500 mt-1">
                      {m.min_guests > 0 && <>Min. {m.min_guests} kişi</>}
                      {m.min_guests > 0 && m.prep_lead_minutes > 0 && ' • '}
                      {m.prep_lead_minutes > 0 && <>{m.prep_lead_minutes} dk hazırlık</>}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="resources">
          <ResourcesView resources={resources} reload={loadResourcesList} />
        </TabsContent>

        <TabsContent value="pipeline">
          {visitedMiceTabs.has('pipeline') && (
            <Suspense fallback={<div className="p-6 text-sm text-slate-500">Yükleniyor…</div>}>
              <SalesPipelineTab accounts={accounts} />
            </Suspense>
          )}
        </TabsContent>

        <TabsContent value="packages">
          {visitedMiceTabs.has('packages') && (
            <Suspense fallback={<div className="p-6 text-sm text-slate-500">Yükleniyor…</div>}>
              <PackagesTab />
            </Suspense>
          )}
        </TabsContent>

        <TabsContent value="competitors">
          <Suspense fallback={<div className="p-6 text-sm text-slate-500">Yükleniyor…</div>}>
            <BanquetCompetitorTab />
          </Suspense>
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
                <TabsTrigger value="operations">Operasyon</TabsTrigger>
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

              <TabsContent value="operations" className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
                <OperationsPanel form={form} setForm={setForm} />
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

      {/* Menu / Package create-edit */}
      {showMenuForm && (
        <Modal title={editingMenu ? 'Menü / Paket Düzenle' : 'Yeni Menü / Paket'}
               onClose={() => setShowMenuForm(false)}>
          <form onSubmit={submitMenu} className="space-y-3">
            <Field label="Ad">
              <Input required value={menuForm.name}
                onChange={(e) => setMenuForm({ ...menuForm, name: e.target.value })} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Tip">
                <select className="w-full border rounded px-2 py-1.5"
                        value={menuForm.type}
                        onChange={(e) => setMenuForm({ ...menuForm, type: e.target.value })}>
                  <option value="fb">F&B (yiyecek-içecek)</option>
                  <option value="av">AV (görsel-işitsel)</option>
                  <option value="decor">Dekorasyon</option>
                  <option value="ddr">DDR (Daily Delegate Rate)</option>
                </select>
              </Field>
              <Field label="Para Birimi">
                <Input value={menuForm.currency}
                  onChange={(e) => setMenuForm({ ...menuForm, currency: e.target.value.toUpperCase() })} />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Kişi Başı Fiyat (₺)">
                <Input type="number" min="0" step="0.01"
                  value={menuForm.price_per_person}
                  onChange={(e) => setMenuForm({ ...menuForm, price_per_person: e.target.value })} />
              </Field>
              <Field label="Sabit Fiyat (₺)">
                <Input type="number" min="0" step="0.01"
                  value={menuForm.flat_price}
                  onChange={(e) => setMenuForm({ ...menuForm, flat_price: e.target.value })} />
              </Field>
            </div>
            <p className="text-xs text-gray-500 -mt-1">
              Sadece birini doldurun. Kişi başı dolu ise pax ile çarpılır; sabit ise toplam tek seferdir.
            </p>
            <Field label="Açıklama (opsiyonel)">
              <textarea className="w-full border rounded px-2 py-1.5 text-sm min-h-[60px]"
                value={menuForm.description}
                onChange={(e) => setMenuForm({ ...menuForm, description: e.target.value })} />
            </Field>
            <Field label="Diyet Etiketleri">
              <div className="flex flex-wrap gap-1.5">
                {['vegan', 'vegetarian', 'halal', 'kosher', 'gluten_free'].map((t) => (
                  <button type="button" key={t}
                    onClick={() => toggleTag('dietary_tags', t)}
                    className={`px-2 py-1 text-xs rounded border ${
                      menuForm.dietary_tags.includes(t)
                        ? 'bg-emerald-100 border-emerald-400 text-emerald-800'
                        : 'bg-white border-gray-300 text-gray-600'
                    }`}>{t}</button>
                ))}
              </div>
            </Field>
            <Field label="Alerjenler">
              <div className="flex flex-wrap gap-1.5">
                {['nuts', 'gluten', 'dairy', 'egg', 'soy', 'fish', 'shellfish', 'sesame'].map((t) => (
                  <button type="button" key={t}
                    onClick={() => toggleTag('allergens', t)}
                    className={`px-2 py-1 text-xs rounded border ${
                      menuForm.allergens.includes(t)
                        ? 'bg-red-100 border-red-400 text-red-800'
                        : 'bg-white border-gray-300 text-gray-600'
                    }`}>{t}</button>
                ))}
              </div>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Min. Kişi Sayısı">
                <Input type="number" min="0" value={menuForm.min_guests}
                  onChange={(e) => setMenuForm({ ...menuForm, min_guests: e.target.value })} />
              </Field>
              <Field label="Mutfak Hazırlık (dk)">
                <Input type="number" min="0" value={menuForm.prep_lead_minutes}
                  onChange={(e) => setMenuForm({ ...menuForm, prep_lead_minutes: e.target.value })} />
              </Field>
            </div>
            <Field label="Durum">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={menuForm.active}
                  onChange={(e) => setMenuForm({ ...menuForm, active: e.target.checked })} />
                Aktif (etkinliklerde seçilebilir)
              </label>
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => setShowMenuForm(false)}>İptal</Button>
              <Button type="submit">{editingMenu ? 'Güncelle' : 'Oluştur'}</Button>
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


export default MicePage;
