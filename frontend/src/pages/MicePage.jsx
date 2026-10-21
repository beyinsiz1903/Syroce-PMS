import { useEffect, useMemo, useRef, useState, Suspense, lazy } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
// Tur 5: pipeline ve packages tab'ları sadece tıklanınca yüklenir.
// R4: BanquetCompetitorTab da lazy — sadece "competitors" tab'ı açılınca yüklenir.
const SalesPipelineTab = lazy(() => import('@/components/mice/SalesPipelineTab'));
const PackagesTab = lazy(() => import('@/components/mice/PackagesTab'));
const BanquetCompetitorTab = lazy(() => import('@/components/mice/BanquetCompetitorTab'));
const KitchenBoardTab = lazy(() => import('@/components/mice/KitchenBoardTab'));
import AccountsView from '@/components/mice/AccountsView';
import DiaryView from '@/components/mice/DiaryView';
import ResourcesView from '@/components/mice/ResourcesView';
import SpacesView from '@/components/mice/SpacesView';
import ReadinessPanel from '@/components/mice/ReadinessPanel';
import { Stat } from '@/components/mice/_shared';
// R4: Modal-bazlı render bloğu modals/ alt-paketine taşındı.
import EventFormModal from '@/components/mice/modals/EventFormModal';

export const omitEmptySpaceBookings = (spaceBookings = []) =>
  spaceBookings.filter((booking) =>
    Boolean(booking?.space_id || booking?.starts_at || booking?.ends_at),
  );
import MenuFormModal from '@/components/mice/modals/MenuFormModal';
import BeoModal from '@/components/mice/modals/BeoModal';
import KitchenModal from '@/components/mice/modals/KitchenModal';
import FnbOrderModal from '@/components/mice/modals/FnbOrderModal';
import OpsModal from '@/components/mice/modals/OpsModal';
import { STATUS } from '@/components/mice/modals/constants';
import { CalendarDays, Plus, Building2, UtensilsCrossed, RefreshCw, Trash2, FileText, Sparkles, ClipboardList, ChefHat, Briefcase, History as HistoryIcon, Pencil, Send } from 'lucide-react';
import EntityHistoryDrawer from '@/components/EntityHistoryDrawer';
import EmptyState from '@/components/EmptyState';
import { confirmDialog, promptDialog } from '@/lib/dialogs';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useEntitlements } from '@/context/EntitlementContext';
import { ModuleLoadError } from '@/components/shared/ModuleAvailabilityState';
import apiErrorText from '@/utils/apiErrorText';
import { isSuperAdmin } from '@/utils/authRoles';
const MicePage = ({
  user,
  tenant,
  onLogout
}) => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { entitlements } = useEntitlements();
  const spacesLimit = entitlements?.mice?.limits?.spaces_limit ?? null;
  const spacesUsed = entitlements?.mice?.usage?.spaces_limit ?? 0;
  const spacesLimitReached = spacesLimit !== null && spacesUsed >= spacesLimit;

  const concurrentEventsLimit = entitlements?.mice?.limits?.concurrent_events ?? null;
  const concurrentEventsUsed = entitlements?.mice?.usage?.concurrent_events ?? 0;
  const eventsLimitReached = concurrentEventsLimit !== null && concurrentEventsUsed >= concurrentEventsLimit;

  const miceFeatures = Array.isArray(entitlements?.mice?.features) ? entitlements.mice.features : [];
  const hasBanquet = miceFeatures.includes('banquet_operations');
  const hasProposals = miceFeatures.includes('proposals_contracts');
  const hasAdvancedReporting = miceFeatures.includes('advanced_reporting');
  const canCatalog = isSuperAdmin(user) || ['admin', 'supervisor'].includes(user?.role);
  const canFinance = isSuperAdmin(user) || ['admin', 'supervisor', 'front_desk', 'finance'].includes(user?.role);
  const canMice = isSuperAdmin(user) || ['admin', 'supervisor', 'sales'].includes(user?.role);

  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState({});
  const [totalCount, setTotalCount] = useState(0);
  const [eventOffset, setEventOffset] = useState(0);
  const [eventFilters, setEventFilters] = useState({});
  const [draftFilters, setDraftFilters] = useState({});
  const [search, setSearch] = useState('');
  const [eventsBusy, setEventsBusy] = useState(false);
  const requestSerial = useRef(0);
  const [savingEvent, setSavingEvent] = useState(false);
  const [quotePreview, setQuotePreview] = useState(null);
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
  const [loadError, setLoadError] = useState(null);
  const [activeTab, setActiveTab] = useState('events');
  // Tur 5: TabsContent global forceMount yaptığı için lazy chunk'lar
  // panel mount olur olmaz indiriliyordu. visitedMiceTabs koşulu ile
  // pipeline/packages componentleri ancak kullanıcı sekmeye geçince
  // instantiate edilir. Bir kez ziyaret edildiğinde DOM'da kalır,
  // tekrar dönünce yeniden chunk fetch yok.
  const [visitedMiceTabs, setVisitedMiceTabs] = useState(() => new Set(['events']));
  useEffect(() => {
    setVisitedMiceTabs(prev => prev.has(activeTab) ? prev : new Set([...prev, activeTab]));
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
    projector: false,
    screen: false,
    microphone_wired: 0,
    microphone_wireless: 0,
    sound_system: false,
    stage: false,
    lighting: false,
    livestream: false,
    internet_mbps: 0,
    translation_booths: 0,
    notes: ''
  };
  const blankEntertainment = {
    type: 'none',
    name: '',
    contact: '',
    start_at: '',
    end_at: '',
    requirements: '',
    fee: 0
  };
  const blankEvent = {
    name: '',
    client_name: '',
    client_email: '',
    client_phone: '',
    client_account_id: '',
    client_contact_id: '',
    organizer_user: '',
    event_type: 'meeting',
    status: 'lead',
    currency: cachedTenantCurrency(),
    expected_pax: 50,
    pricing: null,
    start_date: '',
    end_date: '',
    space_bookings: [{
      space_id: '',
      starts_at: '',
      ends_at: '',
      setup_style: 'theatre',
      expected_pax: 50
    }],
    resources: [],
    agenda: [],
    payment_schedule: [],
    notes: '',
    reservation_id: '',
    technical_requirements: {
      ...blankTechReq
    },
    staff_assignments: [],
    entertainment: {
      ...blankEntertainment
    }
  };
  const [form, setForm] = useState(blankEvent);
  useEffect(() => { setQuotePreview(null); }, [form]);
  const blankMenu = {
    name: '',
    type: 'fb',
    price_per_person: 0,
    flat_price: 0,
    currency: cachedTenantCurrency(),
    description: '',
    active: true,
    dietary_tags: [],
    allergens: [],
    min_guests: 0,
    prep_lead_minutes: 30,
    // courses are preserved on edit (no UI yet); kept here so PUT does not wipe them.
    courses: []
  };
  const [showMenuForm, setShowMenuForm] = useState(false);
  const [editingMenu, setEditingMenu] = useState(null);
  const [menuForm, setMenuForm] = useState(blankMenu);

  // Targeted refreshers used by CRUD handlers below so a single mutation
  // doesn't refetch all five collections.
  const markLoaded = key => setLoadedTabs(prev => {
    if (prev.has(key)) return prev;
    const next = new Set(prev);
    next.add(key);
    return next;
  });
  const loadEvents = async (filters = eventFilters, offset = eventOffset) => {
    const serial = ++requestSerial.current;
    setEventsBusy(true);
    try {
    const params = Object.fromEntries(Object.entries({ ...filters, offset: offset || '' }).filter(([, value]) => value));
    const e = await axios.get('/mice/events', ...(Object.keys(params).length ? [{ params }] : []));
    if (serial !== requestSerial.current) return;
    setEvents(e.data.events);
    setSummary(e.data.summary || {});
    setTotalCount(e.data.total_count ?? e.data.events.length);
    setCounts(e.data.counts || {});
    markLoaded('events');
    } finally { if (serial === requestSerial.current) setEventsBusy(false); }
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
    setLoadError(null);
    try {
      await Promise.all([loadEvents(), loadSpaces(), loadAccountsList()]);
    } catch (err) {
      setLoadError(err);
      toast.error(err.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- yalnız ilk açılışta başlangıç verisini yükler
  }, []);

  // Tab open → fetch on first reveal only. Mutation handlers call the
  // direct loadX helpers so they always refetch, even before that tab
  // was opened (keeps cached badge counts in sync).
  const ensureTabLoaded = tab => {
    if (loadedTabs.has(tab)) return;
    if (tab === 'menus') loadMenus().catch(e => toast.error(e.response?.data?.detail || 'Menüler yüklenemedi'));else if (tab === 'resources') loadResourcesList().catch(e => toast.error(e.response?.data?.detail || 'Envanter yüklenemedi'));
  };
  const handleTabChange = tab => {
    setActiveTab(tab);
    ensureTabLoaded(tab);
  };

  // Event form needs menus + resources for the selection dropdowns; load
  // them on demand the first time the form opens.
  const ensureFormCollections = () => {
    if (!loadedTabs.has('menus')) loadMenus().catch(e => {
      console.warn('[MicePage] loadMenus (on-demand) failed:', e?.response?.status ?? e?.message);
    });
    if (!loadedTabs.has('resources')) loadResourcesList().catch(e => {
      console.warn('[MicePage] loadResourcesList (on-demand) failed:', e?.response?.status ?? e?.message);
    });
  };
  const spaceById = useMemo(() => Object.fromEntries(spaces.map(s => [s.id, s])), [spaces]);
  const accountById = useMemo(() => Object.fromEntries(accounts.map(a => [a.id, a])), [accounts]);
  const openNew = () => {
    setQuotePreview(null);
    ensureFormCollections();
    setEditing(null);
    setForm({ ...blankEvent, client_request_id: crypto.randomUUID() });
    setEventTab('basics');
    setShowEventForm(true);
  };
  const openEdit = ev => {
    setQuotePreview(null);
    ensureFormCollections();
    setEditing(ev.id);
    setForm({
      expected_revision: ev.updated_at || ev.created_at,
      name: ev.name,
      client_name: ev.client_name,
      client_email: ev.client_email || '',
      client_phone: ev.client_phone || '',
      client_account_id: ev.client_account_id || '',
      client_contact_id: ev.client_contact_id || '',
      organizer_user: ev.organizer_user || '',
      event_type: ev.event_type,
      status: ev.status,
      currency: ev.currency || cachedTenantCurrency(),
      expected_pax: ev.expected_pax,
      pricing: ev.pricing || null,
      start_date: ev.start_date,
      end_date: ev.end_date,
      space_bookings: ev.space_bookings?.length ? ev.space_bookings : blankEvent.space_bookings,
      resources: ev.resources || [],
      agenda: ev.agenda || [],
      payment_schedule: ev.payment_schedule || [],
      notes: ev.notes || '',
      reservation_id: ev.reservation_id || '',
      technical_requirements: {
        ...blankTechReq,
        ...(ev.technical_requirements || {})
      },
      staff_assignments: ev.staff_assignments || [],
      entertainment: {
        ...blankEntertainment,
        ...(ev.entertainment || {})
      }
    });
    setEventTab('basics');
    setShowEventForm(true);
  };
  const submit = async e => {
    e.preventDefault();
    if (savingEvent) return;
    if (!form.name.trim() || !form.client_name.trim() || !form.start_date || !form.end_date) {
      setEventTab('basics');
      toast.error('Etkinlik adı, müşteri adı ve tarihleri zorunludur');
      return;
    }
    setSavingEvent(true);
    try {
      // Normalize: empty datetime strings → null; entertainment.type==='none'
      // means user did not configure entertainment, so omit object entirely.
      const payload = {
        ...form
      };
      // The form starts with one convenience row. Do not send that untouched
      // row as a real booking because its required datetimes are intentionally
      // empty until the user selects a space.
      payload.space_bookings = omitEmptySpaceBookings(payload.space_bookings);
      const ent = payload.entertainment || {};
      if (!ent.type || ent.type === 'none') {
        payload.entertainment = null;
      } else {
        payload.entertainment = {
          ...ent,
          start_at: ent.start_at || null,
          end_at: ent.end_at || null
        };
      }
      // Drop empty technical_requirements object (all-falsy/zero) so backend
      // stores null rather than an empty config blob.
      const tr = payload.technical_requirements || {};
      const trHasValue = Object.values(tr).some(v => v && (typeof v !== 'string' || v.trim()));
      if (!trHasValue) payload.technical_requirements = null;

      // Normalize datetime fields inside staff_assignments too.
      payload.staff_assignments = (payload.staff_assignments || []).map(s => ({
        ...s,
        start_at: s.start_at || null,
        end_at: s.end_at || null
      }));
      const url = editing ? `/mice/events/${editing}` : '/mice/events';
      const method = editing ? 'put' : 'post';
      await axios[method](url, payload);
      toast.success(editing ? 'Etkinlik güncellendi' : 'Etkinlik oluşturuldu');
      setShowEventForm(false);
      await loadEvents();
    } catch (err) {
      toast.error(apiErrorText(err, 'Kaydedilemedi; tarih, saat ve zorunlu alanları kontrol edin'));
    } finally { setSavingEvent(false); }
  };
  const changeStatus = async (id, status) => {
    let body = {
      status
    };
    if (status === 'cancelled') {
      const reason = await promptDialog({
        message: 'İptal/lost-business sebebi (en az 10 karakter):',
        defaultValue: ''
      });
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
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Hata');
    }
  };
  const remove = async id => {
    if (!(await confirmDialog({
      message: 'Etkinlik silinsin mi?',
      variant: 'danger'
    }))) return;
    try {
      await axios.delete(`/mice/events/${id}`);
      await loadEvents();
    } catch {
      toast.error('Silinemedi');
    }
  };

  // ── Menu CRUD ──
  const openNewMenu = () => {
    setEditingMenu(null);
    setMenuForm(blankMenu);
    setShowMenuForm(true);
  };
  const openEditMenu = m => {
    setEditingMenu(m.id);
    setMenuForm({
      name: m.name || '',
      type: m.type || 'fb',
      price_per_person: m.price_per_person || 0,
      flat_price: m.flat_price || 0,
      currency: m.currency || cachedTenantCurrency(),
      description: m.description || '',
      active: m.active !== false,
      dietary_tags: m.dietary_tags || [],
      allergens: m.allergens || [],
      min_guests: m.min_guests || 0,
      prep_lead_minutes: m.prep_lead_minutes ?? 30,
      // Preserve courses across edit — backend uses $set: model_dump() so
      // omitting this field would silently wipe existing kitchen course data.
      courses: m.courses || []
    });
    setShowMenuForm(true);
  };
  const submitMenu = async e => {
    e.preventDefault();
    if (!menuForm.name.trim()) {
      toast.error('Ad zorunludur');
      return;
    }
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
        description: menuForm.description?.trim() || null
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
    if (!(await confirmDialog({
      message: `"${name}" silinsin mi?`,
      variant: 'danger'
    }))) return;
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
      [field]: list.includes(val) ? list.filter(x => x !== val) : [...list, val]
    });
  };
  const showBeo = async id => {
    try {
      const r = await axios.get(`/mice/events/${id}/beo`);
      setBeoData(r.data);
    } catch {
      toast.error('BEO alınamadı');
    }
  };
  const showKitchen = async id => {
    try {
      const r = await axios.get(`/mice/events/${id}/kitchen-ticket`);
      setKitchenData(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Mutfak fişi alınamadı');
    }
  };
  const showOpsSheet = async () => {
    try {
      const r = await axios.get('/mice/ops-sheet', {
        params: {
          date: opsDate
        }
      });
      setOpsData(r.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Ops sheet alınamadı');
    }
  };
  const markPaid = async (eventId, idx) => {
    const ref = await promptDialog({
      message: 'Ödeme referansı (banka/işlem no):',
      defaultValue: ''
    });
    if (ref == null) return;
    try {
      await axios.post(`/mice/events/${eventId}/payment-schedule/${idx}/mark-paid`, null, {
        params: ref ? {
          reference: ref
        } : {}
      });
      toast.success('Ödeme işaretlendi');
      await loadEvents();
      // refresh BEO if open
      if (beoData?.event?.id === eventId) showBeo(eventId);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İşaretlenemedi');
    }
  };

  const previewQuote = async () => {
    try {
      // The same normalization as save: optional operation times must be null.
      const ent = form.entertainment;
      const { data } = await axios.post('/mice/events/quote-preview', {
        ...form, space_bookings: omitEmptySpaceBookings(form.space_bookings),
        entertainment: ent?.type && ent.type !== 'none' ? { ...ent, start_at: ent.start_at || null, end_at: ent.end_at || null } : null,
        staff_assignments: form.staff_assignments.map(s => ({ ...s, start_at: s.start_at || null, end_at: s.end_at || null })),
      }, ...(editing ? [{ params: { event_id: editing } }] : []));
      setQuotePreview({ ...data, source: JSON.stringify(form) });
    } catch (error) {
      setQuotePreview(null);
      toast.error(apiErrorText(error, 'Önce etkinlik tarihlerini ve salon / kaynak alanlarını tamamlayın'));
    }
  };

  // ── Form helpers ──
  const setSb = (i, patch) => {
    const next = [...form.space_bookings];
    next[i] = {
      ...next[i],
      ...patch
    };
    setForm({
      ...form,
      space_bookings: next
    });
  };
  const addSb = () => setForm({
    ...form,
    space_bookings: [...form.space_bookings, {
      space_id: '',
      starts_at: '',
      ends_at: '',
      setup_style: 'theatre',
      expected_pax: form.expected_pax
    }]
  });
  const rmSb = i => setForm({
    ...form,
    space_bookings: form.space_bookings.filter((_, k) => k !== i)
  });
  const setRes = (i, patch) => {
    const next = [...form.resources];
    next[i] = {
      ...next[i],
      ...patch
    };
    setForm({
      ...form,
      resources: next
    });
  };
  const addRes = () => setForm({
    ...form,
    resources: [...form.resources, {
      menu_id: '',
      inventory_id: '',
      name: '',
      type: 'fb',
      quantity: 1,
      unit: 'pax',
      unit_price: 0
    }]
  });
  const rmRes = i => setForm({
    ...form,
    resources: form.resources.filter((_, k) => k !== i)
  });
  const setAg = (i, patch) => {
    const next = [...form.agenda];
    next[i] = {
      ...next[i],
      ...patch
    };
    setForm({
      ...form,
      agenda: next
    });
  };
  const addAg = () => setForm({
    ...form,
    agenda: [...form.agenda, {
      starts_at: '',
      ends_at: '',
      title: '',
      kind: 'session',
      location: '',
      owner: '',
      notes: ''
    }]
  });
  const rmAg = i => setForm({
    ...form,
    agenda: form.agenda.filter((_, k) => k !== i)
  });
  const setPs = (i, patch) => {
    const next = [...form.payment_schedule];
    next[i] = {
      ...next[i],
      ...patch
    };
    setForm({
      ...form,
      payment_schedule: next
    });
  };
  const addPs = () => setForm({
    ...form,
    payment_schedule: [...form.payment_schedule, {
      due_date: '',
      label: 'Depozito',
      amount: 0,
      paid: false
    }]
  });
  const rmPs = i => setForm({
    ...form,
    payment_schedule: form.payment_schedule.filter((_, k) => k !== i)
  });
  if (loading) {
    return <div className="p-8 text-center text-gray-500">
      <RefreshCw className="w-6 h-6 animate-spin inline" /> {t('cm.pages_MicePage.yukleniyor')}
    </div>;
  }
  if (loadError) {
    return <ModuleLoadError moduleName="MICE & Banquet" error={loadError} onRetry={load} />;
  }
  const totalPipelineByCurrency = Object.entries(summary).filter(([status]) => !['completed', 'cancelled'].includes(status)).reduce((totals, [, bucket]) => {
    Object.entries(bucket.total_value_by_currency || {}).forEach(([currency, amount]) => {
      totals[currency] = (totals[currency] || 0) + Number(amount || 0);
    });
    return totals;
  }, {});
  const totalPipeline = Object.values(totalPipelineByCurrency).reduce((sum, amount) => sum + amount, 0);
  const psTotal = form.payment_schedule.reduce((a, p) => a + (Number(p.amount) || 0), 0);
  const visibleEvents = events.filter(event => `${event.name} ${event.client_name}`.toLocaleLowerCase('tr').includes(search.toLocaleLowerCase('tr')));
  return <>
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div className="min-w-0 max-w-full">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <CalendarDays className="w-6 h-6 text-indigo-600" />
            MICE & Banquet
          </h1>
          <p className="text-sm text-gray-500 break-words">
            {t('cm.pages_MicePage.toplanti_konferans_gala_ve_dugun_etkinli')}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Input type="date" value={opsDate} onChange={e => setOpsDate(e.target.value)} className="max-w-[160px]" />
          {hasBanquet && <Button variant="outline" onClick={showOpsSheet}>
            <ClipboardList className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.gunun_ops_sheet_i')}
          </Button>}
          <Button variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.yenile')}
          </Button>
          <Button onClick={openNew} disabled={eventsLimitReached || !canMice} title={eventsLimitReached ? 'Eşzamanlı etkinlik limitine ulaşıldı' : ''}><Plus className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.yeni_etkinlik')}</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        {/* Toplam Etkinlik */}
        <div className="rounded-xl bg-gradient-to-br from-indigo-50 to-indigo-100/50 p-5 shadow-sm border border-indigo-100/60 relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-indigo-500/10 rounded-full blur-xl group-hover:scale-110 transition-transform duration-500"></div>
          <div className="flex flex-col gap-1 relative z-10">
            <span className="text-sm font-medium text-indigo-600/80 uppercase tracking-wider">{t('cm.pages_MicePage.toplam_etkinlik')}</span>
            <div className="flex items-end gap-2 mt-1">
              <span className="text-3xl font-bold text-indigo-950">{totalCount}</span>
              <span className="text-sm font-medium text-indigo-600/70 mb-1">etkinlik</span>
            </div>
          </div>
        </div>

        {/* Status Cards (Tentative, Definite, Confirmed) */}
        {['tentative', 'definite', 'confirmed'].map(k => {
          const count = summary[k]?.count || 0;
          const totalValue = summary[k]?.total_value || 0;

          let theme = '';
          if (k === 'tentative') theme = 'from-amber-50 to-amber-100/50 border-amber-200/60 text-amber-900 label-amber-600/80 icon-amber-500/10 val-amber-700';
          else if (k === 'definite') theme = 'from-blue-50 to-sky-100/50 border-blue-200/60 text-blue-900 label-blue-600/80 icon-blue-500/10 val-blue-700';
          else if (k === 'confirmed') theme = 'from-emerald-50 to-teal-100/50 border-emerald-200/60 text-emerald-900 label-emerald-600/80 icon-emerald-500/10 val-emerald-700';

          const parts = theme.split(' ');
          const bg = parts[0] + ' ' + parts[1];
          const border = parts[2];
          const text = parts[3];
          const label = parts[4].replace('label-', 'text-');
          const icon = parts[5].replace('icon-', 'bg-');
          const valText = parts[6].replace('val-', 'text-');

          return (
            <div key={k} className={`rounded-xl bg-gradient-to-br ${bg} p-5 shadow-sm border ${border} relative overflow-hidden group`}>
              <div className={`absolute -right-4 -top-4 w-24 h-24 ${icon} rounded-full blur-xl group-hover:scale-110 transition-transform duration-500`}></div>
              <div className="flex flex-col gap-1 relative z-10">
                <span className={`text-sm font-medium uppercase tracking-wider ${label}`}>{STATUS[k].label}</span>
                <div className="flex flex-col mt-1">
                  <div className="flex items-end gap-2">
                    <span className={`text-2xl font-bold ${text}`}>{count}</span>
                    <span className={`text-xs font-medium mb-1 ${label}`}>adet</span>
                  </div>
                  <span className={`text-lg font-semibold mt-1 ${valText} opacity-90`}>{formatCurrencyBreakdown(summary[k]?.total_value_by_currency, totalValue, cachedTenantCurrency(), i18n.language)}</span>
                </div>
              </div>
            </div>
          );
        })}

        {/* Toplam Pipeline */}
        <div className="rounded-xl bg-gradient-to-br from-violet-50 to-fuchsia-50 p-5 shadow-sm border border-violet-100/60 relative overflow-hidden group">
          <div className="absolute -right-4 -top-4 w-24 h-24 bg-violet-500/10 rounded-full blur-xl group-hover:scale-110 transition-transform duration-500"></div>
          <div className="flex flex-col gap-1 relative z-10">
            <span className="text-sm font-medium text-violet-600/80 uppercase tracking-wider flex items-center gap-1">
              <Sparkles className="w-3.5 h-3.5" /> {t('cm.pages_MicePage.toplam_pipeline')}
            </span>
            <div className="flex items-end gap-2 mt-1">
              <span className="text-2xl md:text-3xl font-bold text-violet-950 tracking-tight">{formatCurrencyBreakdown(totalPipelineByCurrency, totalPipeline, cachedTenantCurrency(), i18n.language)}</span>
            </div>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="h-auto flex-wrap justify-start gap-1">
          <TabsTrigger value="events">Etkinlikler</TabsTrigger>
          <TabsTrigger value="kitchen-board">Mutfak Panosu</TabsTrigger>
          <TabsTrigger value="diary">Function Diary</TabsTrigger>
          <TabsTrigger value="accounts">{t('cm.pages_MicePage.musteriler')}{loadedTabs.has('accounts') ? accounts.length : counts.accounts ?? '…'})</TabsTrigger>
          <TabsTrigger value="spaces">Mekanlar ({loadedTabs.has('spaces') ? spaces.length : counts.spaces ?? '…'})</TabsTrigger>
          <TabsTrigger value="menus">{t('cm.pages_MicePage.menuler_paketler')}{loadedTabs.has('menus') ? menus.length : counts.menus ?? '…'})</TabsTrigger>
          <TabsTrigger value="resources">Envanter ({loadedTabs.has('resources') ? resources.length : counts.resources ?? '…'})</TabsTrigger>
          {hasProposals && <TabsTrigger value="pipeline">{t('cm.pages_MicePage.satis_pipeline')}</TabsTrigger>}
          <TabsTrigger value="packages">Paketler</TabsTrigger>
          <TabsTrigger value="competitors">Rakip Analizi</TabsTrigger>
          {hasAdvancedReporting && <TabsTrigger value="readiness">Operasyon Kontrolü</TabsTrigger>}
        </TabsList>

        <TabsContent value="events">
          <form className="mb-3 flex flex-wrap items-end gap-2" onSubmit={async e => {
            e.preventDefault(); setEventFilters(draftFilters); setEventOffset(0);
            try { await loadEvents(draftFilters, 0); } catch { toast.error('Filtre yüklenemedi'); }
          }}>
            <label className="text-xs">Etkinlik / müşteri<Input aria-label="Etkinlik veya müşteri ara" value={search} onChange={e => setSearch(e.target.value)} /></label>
            <label className="text-xs">Durum<select aria-label="Etkinlik durumu filtresi" className="block h-10 rounded border bg-background px-2" value={draftFilters.status || ''} onChange={e => setDraftFilters({ ...draftFilters, status: e.target.value })}>
              <option value="">Tüm durumlar</option>{Object.entries(STATUS).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
            </select></label>
            <label className="text-xs">Başlangıç<Input type="date" aria-label="Filtre başlangıç" value={draftFilters.date_from || ''} onChange={e => setDraftFilters({ ...draftFilters, date_from: e.target.value })} /></label>
            <label className="text-xs">Bitiş<Input type="date" aria-label="Filtre bitiş" min={draftFilters.date_from} value={draftFilters.date_to || ''} onChange={e => setDraftFilters({ ...draftFilters, date_to: e.target.value })} /></label>
            <Button type="submit" variant="outline" disabled={eventsBusy}>Filtrele</Button>
          </form>
          <p className="mb-3 text-xs text-muted-foreground">Kartlar uygulanan tarih / durum filtresini kapsar. Pipeline, iptal ve tamamlanan işleri içermez. Metin araması yalnız bu sayfada uygulanır.</p>
          {visibleEvents.length === 0 ? <EmptyState icon={CalendarDays} title={t('emptyStates.mice.eventsTitle')} description={t('emptyStates.mice.eventsDesc')} actionText={t('emptyStates.mice.eventsAction')} onAction={canMice && !eventsLimitReached ? openNew : undefined} /> : <Card><CardContent className="p-0 overflow-x-auto">
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
                {visibleEvents.map(ev => {
                    const st = STATUS[ev.status] || STATUS.lead;
                    const acct = ev.client_account_id && accountById[ev.client_account_id];
                    return <tr key={ev.id} className="border-b hover:bg-slate-50">
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
                        {(ev.space_bookings || []).map((sb, i) => <div key={sb.id || i} className="text-xs">
                            {spaceById[sb.space_id]?.name || '?'} • {sb.setup_style}
                          </div>)}
                      </td>
                      <td className="p-2 font-semibold">{formatCurrency(ev.totals?.grand_total, ev.currency || cachedTenantCurrency())}</td>
                      <td className="p-2">
                        <Badge className={`${st.cls} border-0`}>{st.label}</Badge>
                        {ev.lost_reason && <div className="text-xs text-red-600 mt-1 max-w-[160px]" title={ev.lost_reason}>↳ {ev.lost_reason.slice(0, 30)}…</div>}
                      </td>
                      <td className="p-2 text-right space-x-1 whitespace-nowrap">
                        {hasBanquet && <Button size="sm" variant="ghost" title="BEO" onClick={() => showBeo(ev.id)}>
                          <FileText className="w-4 h-4" />
                        </Button>}
                        {hasBanquet && <Button size="sm" variant="ghost" title={t('cm.pages_MicePage.mutfak_fisi')} onClick={() => showKitchen(ev.id)}>
                          <ChefHat className="w-4 h-4" />
                        </Button>}
                        {hasBanquet && <Button size="sm" variant="ghost" title="Mutfak Siparişleri" onClick={() => setFnbOrderEvent(ev)}>
                          <Send className="w-4 h-4" />
                        </Button>}
                        <Button size="sm" variant="ghost" title={t('cm.pages_MicePage.degisiklik_gecmisi')} onClick={() => setHistoryEvent(ev)}>
                          <HistoryIcon className="w-4 h-4" />
                        </Button>
                        <Button size="sm" variant="ghost" disabled={!canMice || ['completed', 'cancelled'].includes(ev.status) || Boolean(ev.signature || ev.gl_journal_entry_id)} onClick={() => openEdit(ev)}>{t('cm.pages_MicePage.duzenle')}</Button>
                        {ev.status !== 'completed' && <select disabled={!canMice} aria-label={`${ev.name} durum değiştir`} className="text-xs border rounded px-1" value={ev.status} onChange={e => changeStatus(ev.id, e.target.value)}>
                            {[ev.status, ...({ lead: ['tentative', 'cancelled'], tentative: ['definite', 'cancelled', 'lead'], definite: ['confirmed', 'tentative', 'cancelled'], confirmed: [...(canFinance ? ['completed'] : []), 'cancelled'], cancelled: ['lead'] }[ev.status] || [])].map(k => <option key={k} value={k}>→ {STATUS[k]?.label || k}</option>)}
                          </select>}
                        <Button disabled={!canMice || Boolean(ev.signature || ev.gl_journal_entry_id) || ev.payment_schedule?.some(p => p.paid)} size="sm" variant="ghost" onClick={() => remove(ev.id)}>
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>;
                  })}
              </tbody>
            </table>
          </CardContent></Card>}
          {totalCount > 500 && <div className="mt-3 flex items-center justify-between gap-2 text-sm"><Button variant="outline" disabled={!eventOffset || eventsBusy} onClick={async () => { const next = Math.max(0, eventOffset - 500); setEventOffset(next); try { await loadEvents(eventFilters, next); } catch { toast.error('Sayfa yüklenemedi'); } }}>Önceki</Button>
            <span>{eventOffset + 1}–{eventOffset + events.length} / {totalCount}</span><Button variant="outline" disabled={eventOffset + events.length >= totalCount || eventsBusy} onClick={async () => { const next = eventOffset + 500; setEventOffset(next); try { await loadEvents(eventFilters, next); } catch { toast.error('Sayfa yüklenemedi'); } }}>Sonraki</Button></div>}
        </TabsContent>

        <TabsContent value="kitchen-board">
          {visitedMiceTabs.has('kitchen-board') && <Suspense fallback={<div className="p-6 text-sm text-slate-500">{t('cm.pages_MicePage.yukleniyor_b597b')}</div>}>
              <KitchenBoardTab />
            </Suspense>}
        </TabsContent>

        <TabsContent value="diary">
          {visitedMiceTabs.has('diary') && <DiaryView spaceById={spaceById} spaces={spaces} />}
        </TabsContent>

        <TabsContent value="accounts">
          <AccountsView accounts={accounts} reload={loadAccountsList} canManage={canMice} />
        </TabsContent>

        <TabsContent value="spaces">
          <SpacesView spaces={spaces} reload={loadSpaces} canManage={canCatalog} limitReached={spacesLimitReached} />
        </TabsContent>

        <TabsContent value="menus">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-3">
            <p className="text-sm text-gray-500">
              {t('cm.pages_MicePage.f_b_menuleri_av_ve_dekorasyon_paketleri_')}
            </p>
            <div className="flex flex-wrap gap-2 w-full sm:w-auto">
              <Button size="sm" variant="outline" onClick={() => navigate('/catering')} data-testid="btn-go-catering" className="w-full sm:w-auto">
                <UtensilsCrossed className="w-4 h-4 mr-1.5" /> {t('cm.pages_MicePage.catering_yonetimi', 'Catering Yönetimi')}
              </Button>
              <Button disabled={!canCatalog} size="sm" onClick={openNewMenu} className="w-full sm:w-auto">
                <Plus className="w-4 h-4 mr-1" /> {t('cm.pages_MicePage.yeni_menu_paket')}
              </Button>
            </div>
          </div>
          {menus.length === 0 && <EmptyState icon={UtensilsCrossed} title={t('emptyStates.mice.menusTitle')} description={t('emptyStates.mice.menusDesc')} actionText={t('emptyStates.mice.menusAction')} onAction={canCatalog ? openNewMenu : undefined} />}
          <div className="grid md:grid-cols-3 gap-3">
            {menus.map(m => <Card key={m.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      {m.type === 'fb' ? <UtensilsCrossed className="w-4 h-4 text-amber-600" /> : m.type === 'av' ? <Sparkles className="w-4 h-4 text-sky-600" /> : <Sparkles className="w-4 h-4 text-pink-600" />}
                      {m.name}
                    </CardTitle>
                    <div className="flex gap-1 shrink-0">
                      <Button disabled={!canCatalog} size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => openEditMenu(m)} title={t('cm.pages_MicePage.duzenle_cc6f2')}>
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button disabled={!canCatalog} size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-600" onClick={() => removeMenu(m.id, m.name)} title={t('cm.pages_MicePage.sil')}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                  <CardDescription>
                    <Badge variant="outline" className="text-xs">{m.type}</Badge>
                    {m.active === false && <Badge variant="outline" className="text-xs ml-1 text-gray-500">pasif</Badge>}
                    {m.dietary_tags?.length > 0 && m.dietary_tags.map(d => <Badge key={d} variant="outline" className="text-xs ml-1">{d}</Badge>)}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {m.price_per_person > 0 ? <div className="text-xl font-bold">{formatCurrency(m.price_per_person, m.currency || cachedTenantCurrency())}
                      <span className="text-xs text-gray-500"> {t('cm.pages_MicePage.kisi')}</span></div> : <div className="text-xl font-bold">{formatCurrency(m.flat_price, m.currency || cachedTenantCurrency())}
                      <span className="text-xs text-gray-500"> sabit</span></div>}
                  {m.description && <div className="text-xs text-gray-600 mt-1">{m.description}</div>}
                  {m.courses?.length > 0 && <div className="text-xs text-gray-600 mt-2">
                      {m.courses.length} kurs: {m.courses.map(c => c.name).join(', ')}
                    </div>}
                  {m.allergens?.length > 0 && <div className="text-xs text-red-600 mt-1">
                      Alerjenler: {m.allergens.join(', ')}
                    </div>}
                  {(m.min_guests > 0 || m.prep_lead_minutes > 0) && <div className="text-xs text-gray-500 mt-1">
                      {m.min_guests > 0 && <>Min. {m.min_guests} {t('cm.pages_MicePage.kisi_94aaa')}</>}
                      {m.min_guests > 0 && m.prep_lead_minutes > 0 && ' • '}
                      {m.prep_lead_minutes > 0 && <>{m.prep_lead_minutes} {t('cm.pages_MicePage.dk_hazirlik')}</>}
                    </div>}
                </CardContent>
              </Card>)}
          </div>
        </TabsContent>

        <TabsContent value="resources">
          <ResourcesView resources={resources} reload={loadResourcesList} canManage={canCatalog} />
        </TabsContent>

        <TabsContent value="pipeline">
          {visitedMiceTabs.has('pipeline') && <Suspense fallback={<div className="p-6 text-sm text-slate-500">{t('cm.pages_MicePage.yukleniyor_b597b')}</div>}>
              <SalesPipelineTab accounts={accounts} />
            </Suspense>}
        </TabsContent>

        <TabsContent value="packages">
          {visitedMiceTabs.has('packages') && <Suspense fallback={<div className="p-6 text-sm text-slate-500">{t('cm.pages_MicePage.yukleniyor_b597b')}</div>}>
              <PackagesTab />
            </Suspense>}
        </TabsContent>

        <TabsContent value="competitors">
          <Suspense fallback={<div className="p-6 text-sm text-slate-500">{t('cm.pages_MicePage.yukleniyor_b597b')}</div>}>
            <BanquetCompetitorTab />
          </Suspense>
        </TabsContent>
        {hasAdvancedReporting && <TabsContent value="readiness"><ReadinessPanel events={events} totalCount={totalCount} onOpen={openEdit} /></TabsContent>}
      </Tabs>

      {/* Event create/edit */}
      {showEventForm && <EventFormModal editing={editing} form={form} setForm={value => { setQuotePreview(null); setForm(value); }} eventTab={eventTab} setEventTab={setEventTab} accounts={accounts} accountById={accountById} spaces={spaces} menus={menus} resources={resources} psTotal={psTotal} addSb={addSb} setSb={setSb} rmSb={rmSb} addRes={addRes} setRes={setRes} rmRes={rmRes} addAg={addAg} setAg={setAg} rmAg={rmAg} addPs={addPs} setPs={setPs} rmPs={rmPs} submit={submit} saving={savingEvent} quotePreview={quotePreview?.source === JSON.stringify(form) ? quotePreview : null} previewQuote={previewQuote} onClose={() => { if (!savingEvent) setShowEventForm(false); }} />}

      {/* Menu / Package create-edit */}
      {showMenuForm && <MenuFormModal editingMenu={editingMenu} menuForm={menuForm} setMenuForm={setMenuForm} toggleTag={toggleTag} submitMenu={submitMenu} onClose={() => setShowMenuForm(false)} />}

      {/* BEO modal */}
      {beoData && <BeoModal beoData={beoData} canFinance={canFinance} canActuals={canFinance && hasAdvancedReporting} canRequestApproval={canMice} markPaid={markPaid} onChanged={async () => { await loadEvents(); await showBeo(beoData.event.id); }} onClose={() => setBeoData(null)} />}

      {/* Kitchen ticket modal */}
      {kitchenData && <KitchenModal kitchenData={kitchenData} onClose={() => setKitchenData(null)} />}

      {/* Send F&B order to kitchen modal */}
      {fnbOrderEvent && <FnbOrderModal event={fnbOrderEvent} onClose={() => setFnbOrderEvent(null)} />}

      {/* Entity history drawer */}
      {historyEvent && <EntityHistoryDrawer entityType="mice_event" entityId={historyEvent.id} title={`${historyEvent.name} (${historyEvent.start_date})`} onClose={() => setHistoryEvent(null)} />}

      {/* Ops sheet modal */}
      {opsData && <OpsModal opsData={opsData} onClose={() => setOpsData(null)} />}
    </div>
    </>;
};
export default MicePage;
