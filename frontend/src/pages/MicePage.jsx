import { useEffect, useMemo, useState, Suspense, lazy } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { Stat } from '@/components/mice/_shared';
// R4: Modal-bazlı render bloğu modals/ alt-paketine taşındı.
import EventFormModal from '@/components/mice/modals/EventFormModal';
import MenuFormModal from '@/components/mice/modals/MenuFormModal';
import BeoModal from '@/components/mice/modals/BeoModal';
import KitchenModal from '@/components/mice/modals/KitchenModal';
import FnbOrderModal from '@/components/mice/modals/FnbOrderModal';
import OpsModal from '@/components/mice/modals/OpsModal';
import { STATUS } from '@/components/mice/modals/constants';
import {
  CalendarDays, Plus, Building2, UtensilsCrossed, RefreshCw,
  Trash2, FileText, Sparkles, ClipboardList, ChefHat, Briefcase,
  History as HistoryIcon, Pencil, Send,
} from 'lucide-react';
import EntityHistoryDrawer from '@/components/EntityHistoryDrawer';

import { confirmDialog, promptDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';
const MicePage = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
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
  const [fnbOrderEvent, setFnbOrderEvent] = useState(null);
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
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
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
      const reason = await promptDialog({ message: 'İptal/lost-business sebebi (en az 10 karakter):', defaultValue: '' });
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
    if (!await confirmDialog({ message: 'Etkinlik silinsin mi?', variant: 'danger' })) return;
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
    if (!await confirmDialog({ message: `"${name}" silinsin mi?`, variant: 'danger' })) return;
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
    const ref = await promptDialog({ message: 'Ödeme referansı (banka/işlem no):', defaultValue: '' }) || '';
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
      <RefreshCw className="w-6 h-6 animate-spin inline" /> {t('cm.pages_MicePage.yukleniyor')}
    </div>;
  }

  const totalPipeline = Object.values(summary).reduce((a, b) => a + (b.total_value || 0), 0);
  const psTotal = form.payment_schedule.reduce((a, p) => a + (Number(p.amount) || 0), 0);

  return (
    <>
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CalendarDays className="w-6 h-6 text-indigo-600" />
            MICE & Banquet
          </h1>
          <p className="text-sm text-gray-500">
            {t('cm.pages_MicePage.toplanti_konferans_gala_ve_dugun_etkinli')}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Input type="date" value={opsDate} onChange={(e) => setOpsDate(e.target.value)}
                 className="max-w-[160px]" />
          <Button variant="outline" onClick={showOpsSheet}>
            <ClipboardList className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.gunun_ops_sheet_i')}
          </Button>
          <Button variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.yenile')}
          </Button>
          <Button onClick={openNew}><Plus className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.yeni_etkinlik')}</Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label={t('cm.pages_MicePage.toplam_etkinlik')} value={events.length} />
        {['tentative', 'definite', 'confirmed'].map((k) => (
          <Stat key={k} label={STATUS[k].label}
                value={`${summary[k]?.count || 0} • ₺${(summary[k]?.total_value || 0).toLocaleString('tr-TR')}`}
                cls={STATUS[k].cls.split(' ')[1].replace('text-', 'text-')} />
        ))}
        <Stat label={t('cm.pages_MicePage.toplam_pipeline')}
              value={`₺${totalPipeline.toLocaleString('tr-TR')}`} cls="text-emerald-600" />
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          <TabsTrigger value="events">Etkinlikler</TabsTrigger>
          <TabsTrigger value="diary">Function Diary</TabsTrigger>
          <TabsTrigger value="accounts">{t('cm.pages_MicePage.musteriler')}{loadedTabs.has('accounts') ? accounts.length : (counts.accounts ?? '…')})</TabsTrigger>
          <TabsTrigger value="spaces">Mekanlar ({loadedTabs.has('spaces') ? spaces.length : (counts.spaces ?? '…')})</TabsTrigger>
          <TabsTrigger value="menus">{t('cm.pages_MicePage.menuler_paketler')}{loadedTabs.has('menus') ? menus.length : (counts.menus ?? '…')})</TabsTrigger>
          <TabsTrigger value="resources">Envanter ({loadedTabs.has('resources') ? resources.length : (counts.resources ?? '…')})</TabsTrigger>
          <TabsTrigger value="pipeline">{t('cm.pages_MicePage.satis_pipeline')}</TabsTrigger>
          <TabsTrigger value="packages">Paketler</TabsTrigger>
          <TabsTrigger value="competitors">Rakip Analizi</TabsTrigger>
        </TabsList>

        <TabsContent value="events">
          <Card><CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b text-left">
                <tr>
                  <th className="p-2">Etkinlik</th><th className="p-2">{t('cm.pages_MicePage.musteri')}</th>
                  <th className="p-2">{t('cm.pages_MicePage.tarih')}</th><th className="p-2">Pax</th>
                  <th className="p-2">Mekanlar</th><th className="p-2">{t('cm.pages_MicePage.tutar')}</th>
                  <th className="p-2">{t('cm.pages_MicePage.durum')}</th><th className="p-2 text-right">{t('cm.pages_MicePage.islem')}</th>
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
                        <Button size="sm" variant="ghost" title={t('cm.pages_MicePage.mutfak_fisi')}
                                onClick={() => showKitchen(ev.id)}>
                          <ChefHat className="w-4 h-4" />
                        </Button>
                        <Button size="sm" variant="ghost" title="Mutfağa Gönder"
                                onClick={() => setFnbOrderEvent(ev)}>
                          <Send className="w-4 h-4" />
                        </Button>
                        <Button size="sm" variant="ghost" title={t('cm.pages_MicePage.degisiklik_gecmisi')}
                                onClick={() => setHistoryEvent(ev)}>
                          <HistoryIcon className="w-4 h-4" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => openEdit(ev)}>{t('cm.pages_MicePage.duzenle')}</Button>
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
                    <span className="text-gray-500">{t('cm.pages_MicePage.gunluk')}</span> ₺{s.daily_rate.toLocaleString('tr-TR')}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="menus">
          <div className="flex justify-between items-center mb-3">
            <p className="text-sm text-gray-500">
              {t('cm.pages_MicePage.f_b_menuleri_av_ve_dekorasyon_paketleri_')}
            </p>
            <Button size="sm" onClick={openNewMenu}>
              <Plus className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.yeni_menu_paket')}
            </Button>
          </div>
          {menus.length === 0 && (
            <div className="text-center py-12 text-gray-500 text-sm">
              {t('cm.pages_MicePage.henuz_menu_eklenmemis_yeni_menu_paket_bu')}
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
                              onClick={() => openEditMenu(m)} title={t('cm.pages_MicePage.duzenle_cc6f2')}>
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-600"
                              onClick={() => removeMenu(m.id, m.name)} title={t('cm.pages_MicePage.sil')}>
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
                      <span className="text-xs text-gray-500"> {t('cm.pages_MicePage.kisi')}</span></div>
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
                      {m.min_guests > 0 && <>Min. {m.min_guests} {t('cm.pages_MicePage.kisi_94aaa')}</>}
                      {m.min_guests > 0 && m.prep_lead_minutes > 0 && ' • '}
                      {m.prep_lead_minutes > 0 && <>{m.prep_lead_minutes} {t('cm.pages_MicePage.dk_hazirlik')}</>}
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
            <Suspense fallback={<div className="p-6 text-sm text-slate-500">{t('cm.pages_MicePage.yukleniyor_b597b')}</div>}>
              <SalesPipelineTab accounts={accounts} />
            </Suspense>
          )}
        </TabsContent>

        <TabsContent value="packages">
          {visitedMiceTabs.has('packages') && (
            <Suspense fallback={<div className="p-6 text-sm text-slate-500">{t('cm.pages_MicePage.yukleniyor_b597b')}</div>}>
              <PackagesTab />
            </Suspense>
          )}
        </TabsContent>

        <TabsContent value="competitors">
          <Suspense fallback={<div className="p-6 text-sm text-slate-500">{t('cm.pages_MicePage.yukleniyor_b597b')}</div>}>
            <BanquetCompetitorTab />
          </Suspense>
        </TabsContent>
      </Tabs>

      {/* Event create/edit */}
      {showEventForm && (
        <EventFormModal
          editing={editing}
          form={form} setForm={setForm}
          eventTab={eventTab} setEventTab={setEventTab}
          accounts={accounts} accountById={accountById}
          spaces={spaces} menus={menus} resources={resources}
          psTotal={psTotal}
          addSb={addSb} setSb={setSb} rmSb={rmSb}
          addRes={addRes} setRes={setRes} rmRes={rmRes}
          addAg={addAg} setAg={setAg} rmAg={rmAg}
          addPs={addPs} setPs={setPs} rmPs={rmPs}
          submit={submit}
          onClose={() => setShowEventForm(false)}
        />
      )}

      {/* Menu / Package create-edit */}
      {showMenuForm && (
        <MenuFormModal editingMenu={editingMenu} menuForm={menuForm} setMenuForm={setMenuForm} toggleTag={toggleTag} submitMenu={submitMenu} onClose={() => setShowMenuForm(false)} />
      )}

      {/* BEO modal */}
      {beoData && (
        <BeoModal beoData={beoData} markPaid={markPaid} onClose={() => setBeoData(null)} />
      )}

      {/* Kitchen ticket modal */}
      {kitchenData && (
        <KitchenModal kitchenData={kitchenData} onClose={() => setKitchenData(null)} />
      )}

      {/* Send F&B order to kitchen modal */}
      {fnbOrderEvent && (
        <FnbOrderModal event={fnbOrderEvent} onClose={() => setFnbOrderEvent(null)} />
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
        <OpsModal opsData={opsData} onClose={() => setOpsData(null)} />
      )}
    </div>
    </>
  );
};


export default MicePage;
