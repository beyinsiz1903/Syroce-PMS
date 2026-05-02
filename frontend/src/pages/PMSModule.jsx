import { useState, useEffect, useMemo, useCallback, Suspense, lazy, memo } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import GlobalSearch from '@/components/GlobalSearch';
// Tur 5: Bundle code-split — tab içerikleri ve büyük dialog'lar lazy.
// İlk yüklemede sadece varsayılan 'frontdesk' tab'ı indirilir; kullanıcı
// diğer sekmelere geçince ilgili chunk talep üzerine yüklenir.
// Sticky-mount mantığı (visitedTabs) korunur — bir kez ziyaret edilen
// chunk RAM'de kalır, geri dönünce yeniden indirilmez.
const FrontdeskTab = lazy(() => import('@/components/pms/FrontdeskTab'));
const HousekeepingTab = lazy(() => import('@/components/pms/HousekeepingTab'));
const BookingsTab = lazy(() => import('@/components/pms/BookingsTab'));
const RoomsTab = lazy(() => import('@/components/pms/RoomsTab'));
const GuestsTab = lazy(() => import('@/components/pms/GuestsTab'));
const CashierTab = lazy(() => import('@/components/pms/CashierTab'));
const UpsellTab = lazy(() => import('@/components/pms/UpsellTab'));
const InternalChatTab = lazy(() => import('@/components/pms/InternalChatTab'));
const ReportsTab = lazy(() => import('@/components/pms/ReportsTab'));
const FlashReportContent = lazy(() => import('@/components/pms/FlashReportContent'));
const LaundryTab = lazy(() => import('@/components/pms/LaundryTab'));
const POSTab = lazy(() => import('@/components/pms/POSTab'));
// Büyük dialog'lar (>500 satır) — açılmadığı sürece chunk indirilmez.
const BookingDialog = lazy(() => import('@/components/pms/BookingDialog'));
const FolioViewDialog = lazy(() => import('@/components/pms/FolioViewDialog'));
const Guest360Dialog = lazy(() => import('@/components/pms/Guest360Dialog'));
// Modal flow — her zaman opt-in, ekstra split.
const ReservationDetailModal = lazy(() => import('@/pages/ReservationDetailModal'));
// Küçük/sık dialog'lar statik kalsın (split overhead'i değmez).
import LeadTimeCurve from '@/components/LeadTimeCurve';
import RevenueDashboard from '@/components/RevenueDashboard';
import AIActivityLog from '@/components/AIActivityLog';
import StaffTaskManager from '@/components/StaffTaskManager';
import FeedbackSystem from '@/components/FeedbackSystem';
import AllotmentGrid from '@/components/AllotmentGrid';
import GroupRevenueByCompany from '@/components/GroupRevenueByCompany';
import PickupPaceReport from '@/components/PickupPaceReport';
import BookingDetailDialog from '@/components/pms/BookingDetailDialog';
import BulkRoomsDialog from '@/components/pms/BulkRoomsDialog';
import CompanyDialog from '@/components/pms/CompanyDialog';
import FindRoomDialog from '@/components/pms/FindRoomDialog';
import HKTaskDialog from '@/components/pms/HKTaskDialog';
import MaintenanceDialog from '@/components/pms/MaintenanceDialog';
import { RoomBlockCreateDialog, RoomBlockViewDialog } from '@/components/pms/RoomBlockDialogs';
import GuestInfoDialog from '@/components/pms/GuestInfoDialog';
import PaymentDialog from '@/components/pms/PaymentDialog';
import { printRegistrationCard } from '@/components/pms/PrintTemplates';
import RoomFeaturesPanel from '@/components/pms/RoomFeaturesPanel';
import ConciergeDesk from '@/components/pms/ConciergeDesk';
import GuestPreferences from '@/components/pms/GuestPreferences';
import RoutingInstructions from '@/components/pms/RoutingInstructions';
import ManagerDailyReport from '@/components/pms/ManagerDailyReport';
import KBSNotification from '@/components/pms/KBSNotification';
import KVKKManager from '@/components/pms/KVKKManager';
import RevenueControls from '@/components/pms/RevenueControls';
import FolioDialog from '@/components/pms/FolioDialog';
import RoomCreateDialog from '@/components/pms/RoomCreateDialog';
import RoomImageUploadDialog from '@/components/pms/RoomImageUploadDialog';
import GuestCreateDialog from '@/components/pms/GuestCreateDialog';
import BulkDeleteRoomsDialog from '@/components/pms/BulkDeleteRoomsDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { 
  BedDouble, Users, Calendar, Plus, CheckCircle, DollarSign, 
  ClipboardList, BarChart3, TrendingUp, UserCheck, LogIn, LogOut, Home, FileText, 
  Star, Send, MessageSquare, UserPlus, ArrowRight, RefreshCw, User, Search, CheckSquare, Download, Clock, Crown,
  Wallet, Wrench, ThumbsUp, Building2, UtensilsCrossed, Shirt,
  MapPin, Shield, Lock, Heart
} from 'lucide-react';
import FloatingActionButton from '@/components/FloatingActionButton';
import { useSetupStatus } from '@/hooks/useSetupStatus';
import LiteSetupBanner from '@/components/LiteSetupBanner';

const PMSModule = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const plan =
    tenant?.subscription_plan ||
    tenant?.plan ||
    tenant?.subscription_tier ||
    'core_small_hotel';
  const isLite = plan === 'pms_lite';

  const { data: setup } = useSetupStatus({ enabled: isLite });
  const roomsCount = setup?.rooms_count ?? 0;
  const [rooms, setRooms] = useState([]);
  const [guests, setGuests] = useState([]);
  const [groupedBookings, setGroupedBookings] = useState([]);

  const [bookings, setBookings] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [arrivals, setArrivals] = useState([]);
  const [departures, setDepartures] = useState([]);
  const [inhouse, setInhouse] = useState([]);
  const [housekeepingTasks, setHousekeepingTasks] = useState([]);
  const [roomStatusBoard, setRoomStatusBoard] = useState(null);
  const [dueOutRooms, setDueOutRooms] = useState([]);
  const [stayoverRooms, setStayoverRooms] = useState([]);
  const [arrivalRooms, setArrivalRooms] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [userPermissions, setUserPermissions] = useState({});
  const [otaReservations, setOtaReservations] = useState([]);
  const [rmsSuggestions, setRmsSuggestions] = useState([]);
  const [exceptions, setExceptions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fdLoading, setFdLoading] = useState(false);
  const [fdError, setFdError] = useState(null);
  const [hkLoading, setHkLoading] = useState(false);
  const [aiPrediction, setAiPrediction] = useState(null);
  const [aiPatterns, setAiPatterns] = useState(null);
  const [openDialog, setOpenDialog] = useState(null);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [selectedGuest, setSelectedGuest] = useState(null);

  const [folio, setFolio] = useState(null);
  const [folios, setFolios] = useState([]);
  const [selectedFolio, setSelectedFolio] = useState(null);
  const [folioCharges, setFolioCharges] = useState([]);
  const [folioPayments, setFolioPayments] = useState([]);
  const [roomBlocks, setRoomBlocks] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [newRoomBlock, setNewRoomBlock] = useState({
    type: 'out_of_order', reason: '', details: '', start_date: '', end_date: '', allow_sell: false
  });

  const navigate = useNavigate();
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');
  const [quickFilters, setQuickFilters] = useState({
    roomType: '', bookingStatus: '', paymentStatus: '', roomView: '', amenity: ''
  });
  
  const [selectedRooms, setSelectedRooms] = useState([]);
  const [bulkRoomMode, setBulkRoomMode] = useState(false);

  const [selectedGuest360, setSelectedGuest360] = useState(null);
  const [guest360Data, setGuest360Data] = useState(null);
  const [loadingGuest360, setLoadingGuest360] = useState(false);
  const [selectedBookingDetail, setSelectedBookingDetail] = useState(null);
  const [reservationDetailId, setReservationDetailId] = useState(null);
  const [guestTag, setGuestTag] = useState('');
  const [guestNote, setGuestNote] = useState('');
  
  const [findRoomCriteria, setFindRoomCriteria] = useState({
    check_in: '', check_out: '', room_type: '', guests: 1
  });

  const [maintenanceDialogOpen, setMaintenanceDialogOpen] = useState(false);
  const [maintenanceForm, setMaintenanceForm] = useState({
    room_id: null, room_number: '', issue_type: 'housekeeping_damage', priority: 'normal', description: ''
  });

  // Tur 5: lazy dialog'lar için sticky-visited pattern.
  // Bir kez açıldığında DOM'da kalır → kapanış animasyonu kaybolmaz,
  // ikinci açılışta chunk yeniden indirilmez. open prop tek source-of-truth.
  const [visitedDialogs, setVisitedDialogs] = useState(() => new Set());
  useEffect(() => {
    if (!openDialog) return;
    setVisitedDialogs((prev) => (prev.has(openDialog) ? prev : new Set([...prev, openDialog])));
  }, [openDialog]);

  const LITE_TABS = new Set(['frontdesk', 'housekeeping', 'rooms', 'guests', 'bookings', 'reports']);

  const ALL_TABS = [
    { key: 'frontdesk', labelText: 'Ön Büro', icon: UserCheck, testId: 'tab-frontdesk' },
    { key: 'housekeeping', labelText: 'Kat Hizmetleri', icon: ClipboardList, testId: 'tab-housekeeping' },
    { key: 'rooms', labelText: 'Odalar', icon: BedDouble, testId: 'tab-rooms' },
    { key: 'guests', labelText: 'Misafirler', icon: Users, testId: 'tab-guests' },
    { key: 'bookings', labelText: 'Rezervasyonlar', icon: Calendar, testId: 'tab-bookings' },
    { key: 'cashier', labelText: 'Kasa', icon: Wallet, testId: 'tab-cashier' },
    { key: 'upsell', labelText: 'Upsell', icon: TrendingUp, testId: 'tab-upsell' },
    { key: 'internal_chat', labelText: 'İletişim', icon: MessageSquare, testId: 'tab-internal-chat' },
    { key: 'reports', labelText: 'Raporlar', icon: FileText, testId: 'tab-reports' },
    { key: 'flash', labelText: 'Flash Rapor', icon: BarChart3, testId: 'tab-flash' },
    { key: 'tasks', labelText: 'Görevler', icon: Wrench, testId: 'tab-tasks' },
    { key: 'feedback', labelText: 'Geri Bildirim', icon: ThumbsUp, testId: 'tab-feedback' },
    { key: 'allotment', labelText: 'Kontenjan', icon: Building2, testId: 'tab-allotment' },
    { key: 'pos', labelText: 'POS', icon: UtensilsCrossed, testId: 'tab-pos' },
    { key: 'laundry', labelText: 'Çamaşırhane', icon: Shirt, testId: 'tab-laundry' },
    { key: 'concierge', labelText: 'Concierge', icon: MapPin, testId: 'tab-concierge' },
    { key: 'revenue', labelText: 'Gelir Kontrol', icon: TrendingUp, testId: 'tab-revenue' },
    { key: 'manager_report', labelText: 'Müdür Raporu', icon: FileText, testId: 'tab-manager-report' },
    { key: 'kbs', labelText: 'KBS / GİKS', icon: Shield, testId: 'tab-kbs' },
    { key: 'kvkk', labelText: 'KVKK', icon: Lock, testId: 'tab-kvkk' },
  ];

  const visibleTabs = isLite
    ? ALL_TABS.filter((tab) => LITE_TABS.has(tab.key))
    : ALL_TABS;

  const validTabKeys = useMemo(() => new Set(visibleTabs.map((t) => t.key)), [visibleTabs]);

  const [activeTab, setActiveTab] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    const validKeys = isLite
      ? new Set(ALL_TABS.filter((t) => LITE_TABS.has(t.key)).map((t) => t.key))
      : new Set(ALL_TABS.map((t) => t.key));
    if (hash && validKeys.has(hash)) return hash;
    return 'frontdesk';
  });

  // Sticky-lazy mount: yalnızca ziyaret edilmiş PMS sekmelerinin içeriği
  // mount edilir. Globaldeki TabsContent forceMount yapıyor; bu yüzden
  // 20 sekmenin hepsi başlangıçta mount oluyor ve onlarca gereksiz
  // endpoint + polling timer + Socket.IO bağlantısı tetikleniyordu.
  // Bir sekme bir kez ziyaret edilince mount kalır → state ve abone-
  // likler korunur, geri dönünce yeniden fetch yok.
  const [visitedTabs, setVisitedTabs] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    const initial = (hash && validTabKeys.has(hash)) ? hash : 'frontdesk';
    return new Set([initial]);
  });
  useEffect(() => {
    setVisitedTabs((prev) => (prev.has(activeTab) ? prev : new Set([...prev, activeTab])));
  }, [activeTab]);

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace('#', '');
      if (hash && !validTabKeys.has(hash)) {
        setActiveTab('frontdesk');
        window.location.hash = 'frontdesk';
        return;
      }
      setActiveTab(hash || 'frontdesk');
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [validTabKeys]);

  useEffect(() => {
    const hash = window.location.hash.replace('#', '');
    if (hash && !validTabKeys.has(hash)) {
      setActiveTab('frontdesk');
      window.location.hash = 'frontdesk';
    }
  }, [validTabKeys]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') return;
    const tenantId = tenant?.id || tenant?._id || tenant?.tenant_id || 'unknown';
    const key = `pms_open_dialog_once:${tenantId}`;
    const val = window.localStorage.getItem(key);
    if (val && activeTab === 'rooms') {
      setOpenDialog(val);
      window.localStorage.removeItem(key);
    }
  }, [tenant, activeTab]);

  // Auto-open booking detail when navigated with ?edit=<id>
  // (used by ReservationCalendar "Düzenle" → /app/pms?edit=ID#bookings).
  // The full booking object is passed via sessionStorage so this works
  // even when the booking is outside the PMS module's loaded date range.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const editId = params.get('edit');
    if (!editId) return;
    let target = null;
    try {
      const stored = window.sessionStorage?.getItem('pms_edit_booking');
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed?.id === editId) target = parsed;
      }
    } catch { /* ignore sessionStorage parse errors */ }
    if (!target && bookings && bookings.length > 0) {
      target = bookings.find((b) => b.id === editId) || null;
    }
    if (!target) return;
    setSelectedBookingDetail(target);
    setOpenDialog('bookingDetail');
    try { window.sessionStorage?.removeItem('pms_edit_booking'); } catch { /* ignore */ }
    // Clean URL so back-nav / refresh does not re-open.
    params.delete('edit');
    const newSearch = params.toString();
    const newUrl = window.location.pathname + (newSearch ? `?${newSearch}` : '') + window.location.hash;
    window.history.replaceState(null, '', newUrl);
  }, [bookings]);

  useEffect(() => {
    if (!isLite || openDialog !== 'booking') return;
    if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') return;
    const tenantId = tenant?.id || tenant?._id || tenant?.tenant_id || 'unknown';
    const key = `pms_booking_prefill:${tenantId}`;
    const raw = window.localStorage.getItem(key);
    if (!raw) return;
    try {
      const p = JSON.parse(raw);
      if (p.mode && p.mode !== 'lite_first_booking') return;
      const today = new Date();
      const tomorrow = new Date();
      tomorrow.setDate(today.getDate() + 1);
      const fmt = (d) => d.toISOString().split('T')[0];
      setNewBooking((prev) => ({ ...prev, check_in: fmt(today), check_out: fmt(tomorrow), adults: prev?.adults || 2 }));
      window.localStorage.removeItem(key);
    } catch (e) {
      console.warn('Failed to apply booking prefill', e);
    }
  }, [isLite, tenant, openDialog]);

  const [newBooking, setNewBooking] = useState({
    guest_id: '', room_id: '', check_in: '', check_out: '',
    adults: 1, children: 0, children_ages: [], guests_count: 1,
    total_amount: 0, base_rate: 0, channel: 'direct', company_id: '',
    contracted_rate: '', rate_type: '', market_segment: '',
    cancellation_policy: '', billing_address: '', billing_tax_number: '',
    billing_contact_person: '', override_reason: ''
  });

  const [multiRoomBooking, setMultiRoomBooking] = useState([
    { room_id: '', adults: 1, children: 0, children_ages: [], total_amount: 0, base_rate: 0, rate_plan: '', package_code: null }
  ]);

  const [newCompany, setNewCompany] = useState({
    name: '', corporate_code: '', tax_number: '', billing_address: '',
    contact_person: '', contact_email: '', contact_phone: '',
    contracted_rate: '', default_rate_type: '', default_market_segment: '',
    default_cancellation_policy: '', payment_terms: '', status: 'pending'
  });

  const bookingStats = useMemo(() => {
    const total = bookings.length;
    const confirmed = bookings.filter(b => b.status === 'confirmed').length;
    const checkedIn = bookings.filter(b => b.status === 'checked_in').length;
    const totalRevenue = bookings.reduce((sum, b) => sum + (b.total_amount || 0), 0);
    const avgAdr = total > 0 ? totalRevenue / total : 0;
    return { total, confirmed, checkedIn, totalRevenue, avgAdr };
  }, [bookings]);

  const [newCharge, setNewCharge] = useState({ charge_type: 'food', description: '', amount: 0, quantity: 1 });
  const [newPayment, setNewPayment] = useState({ amount: 0, method: 'card', reference: '', notes: '' });
  const [newHKTask, setNewHKTask] = useState({ room_id: '', task_type: 'cleaning', priority: 'normal', notes: '' });
  const [paymentForm, setPaymentForm] = useState({ amount: 0, method: 'card', payment_type: 'interim', reference: '', notes: '' });

  const addRoomToMultiBooking = () => {
    setMultiRoomBooking(prev => [...prev, { room_id: '', adults: 1, children: 0, children_ages: [], total_amount: 0, base_rate: 0, rate_plan: '', package_code: null }]);
  };

  const removeRoomFromMultiBooking = (index) => {
    setMultiRoomBooking(prev => prev.length === 1 ? prev : prev.filter((_, i) => i !== index));
  };

  const updateMultiRoomField = (index, field, value) => {
    setMultiRoomBooking(prev => prev.map((room, i) => {
      if (i !== index) return room;
      if (field === 'adults' || field === 'children' || field === 'base_rate' || field === 'total_amount') {
        const numeric = field === 'base_rate' || field === 'total_amount' ? parseFloat(value) || 0 : parseInt(value) || 0;
        return { ...room, [field]: numeric };
      }
      return { ...room, [field]: value };
    }));
  };

  const updateMultiRoomChildrenAges = (index, childrenCount) => {
    setMultiRoomBooking(prev => prev.map((room, i) => {
      if (i !== index) return room;
      const count = parseInt(childrenCount) || 0;
      let ages = room.children_ages || [];
      if (count > ages.length) ages = [...ages, ...Array(count - ages.length).fill(0)];
      else ages = ages.slice(0, count);
      return { ...room, children: count, children_ages: ages };
    }));
  };

  const updateMultiRoomChildAge = (roomIndex, ageIndex, age) => {
    setMultiRoomBooking(prev => prev.map((room, i) => {
      if (i !== roomIndex) return room;
      const ages = [...(room.children_ages || [])];
      ages[ageIndex] = parseInt(age) || 0;
      return { ...room, children_ages: ages };
    }));
  };

  const [hasLoadedFrontdesk, setHasLoadedFrontdesk] = useState(false);
  const [hasLoadedHousekeeping, setHasLoadedHousekeeping] = useState(false);
  const [ratePlans, setRatePlans] = useState([]);
  const [packages, setPackages] = useState([]);

  useEffect(() => { loadData(); setTimeout(() => { loadAuditLogs(); loadChannelManagerData(); }, 1000); }, []);

  useEffect(() => {
    if (activeTab === 'frontdesk' && !hasLoadedFrontdesk) { loadFrontDeskData(); setHasLoadedFrontdesk(true); }
    else if (activeTab === 'housekeeping' && !hasLoadedHousekeeping) { loadHousekeepingData(); setHasLoadedHousekeeping(true); }
  }, [activeTab, hasLoadedFrontdesk, hasLoadedHousekeeping]);

  const loadData = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const futureDate = new Date(); futureDate.setDate(futureDate.getDate() + 90);
      const futureDateStr = futureDate.toISOString().split('T')[0];
      const results = await Promise.allSettled([
        axios.get('/pms/rooms?limit=100', { timeout: 15000 }),
        axios.get('/pms/guests?limit=100', { timeout: 15000 }),
        axios.get(`/pms/bookings?start_date=${today}&end_date=${futureDateStr}&limit=200`, { timeout: 15000 }),
        axios.get('/companies?limit=50', { timeout: 15000 })
      ]);
      const [roomsRes, guestsRes, bookingsRes, companiesRes] = results.map((r) => (r.status === 'fulfilled' ? r.value : null));
      results.forEach((r, idx) => { if (r.status === 'rejected') console.warn('PMS loadData partial failure:', idx, r.reason); });
      const rawBookings = bookingsRes?.data || [];
      const grouped = [];
      const seenGroupIds = new Set();
      rawBookings.filter(b => b.group_booking_id).forEach(b => {
        if (seenGroupIds.has(b.group_booking_id)) return;
        const sameGroup = rawBookings.filter(x => x.group_booking_id === b.group_booking_id);
        seenGroupIds.add(b.group_booking_id);
        grouped.push({ type: 'group', group_booking_id: b.group_booking_id, master_booking: b, bookings: sameGroup });
      });
      rawBookings.filter(b => !b.group_booking_id).forEach(b => { grouped.push({ type: 'single', booking: b }); });
      setGroupedBookings(grouped);
      setRooms(roomsRes?.data || []); setGuests(guestsRes?.data || []);
      setBookings(bookingsRes?.data || []); setCompanies(companiesRes?.data || []);
    } catch (error) { toast.error('Failed to load data'); console.error('PMS data load error:', error);
    } finally { setLoading(false); }
  };

  const loadFrontDeskData = async () => {
    setFdLoading(true); setFdError(null);
    try {
      const [arrivalsRes, departuresRes, inhouseRes] = await Promise.all([
        axios.get('/frontdesk/arrivals'), axios.get('/frontdesk/departures'), axios.get('/frontdesk/inhouse')
      ]);
      setArrivals(arrivalsRes.data); setDepartures(departuresRes.data); setInhouse(inhouseRes.data);
      loadAIInsights();
    } catch (error) {
      const msg = error?.response?.data?.detail || error.message || 'Failed to load front desk data';
      setFdError(msg); toast.error('Failed to load front desk data');
    } finally { setFdLoading(false); }
  };

  const loadAIInsights = async () => {
    try {
      const [predictionRes, patternsRes] = await Promise.all([
        axios.get('/ai/pms/occupancy-prediction').catch(() => null),
        axios.get('/ai/pms/guest-patterns').catch(() => null)
      ]);
      if (predictionRes) {
        const raw = predictionRes.data || {};
        setAiPrediction({ current_occupancy: typeof raw.current_occupancy === 'number' ? raw.current_occupancy : 0, upcoming_bookings: typeof raw.upcoming_bookings === 'number' ? raw.upcoming_bookings : 0, prediction: raw.prediction });
      }
      if (patternsRes) {
        const rawPatterns = patternsRes.data || {};
        const insights = Array.isArray(rawPatterns.insights) ? rawPatterns.insights.map((item) => typeof item === 'string' ? item : JSON.stringify(item)) : [];
        setAiPatterns({ insights });
      }
    } catch (error) { console.error('AI insights not available'); }
  };

  const loadHousekeepingData = async () => {
    setHkLoading(true);
    try {
      const [tasksRes, boardRes] = await Promise.all([axios.get('/housekeeping/tasks'), axios.get('/housekeeping/room-status')]);
      setHousekeepingTasks(tasksRes.data); setRoomStatusBoard(boardRes.data);
      setTimeout(async () => {
        try {
          const [dueOutRes, stayoverRes, arrivalsRes, blocksRes] = await Promise.all([
            axios.get('/housekeeping/due-out'), axios.get('/housekeeping/stayovers'),
            axios.get('/housekeeping/arrivals'), axios.get('/pms/room-blocks?status=active')
          ]);
          setDueOutRooms(dueOutRes.data.due_out_rooms || []); setStayoverRooms(stayoverRes.data.stayover_rooms || []);
          setArrivalRooms(arrivalsRes.data.arrival_rooms || []); setRoomBlocks(blocksRes.data.blocks || []);
        } catch (error) { console.error('Failed to load additional housekeeping data:', error); }
      }, 500);
    } catch (error) { toast.error('Failed to load housekeeping data');
    } finally { setHkLoading(false); }
  };

  const loadRateData = async (channel, companyId, stayDate) => {
    try {
      const params = {};
      if (channel) params.channel = channel; if (companyId) params.company_id = companyId; if (stayDate) params.stay_date = stayDate;
      const [rpRes, pkgRes] = await Promise.all([axios.get('/rates/rate-plans', { params }), axios.get('/rates/packages')]);
      setRatePlans(rpRes.data || []); setPackages(pkgRes.data || []);
    } catch (error) { console.error('Failed to load rate plans/packages', error); toast.error('Failed to load rate plans'); }
  };

  const loadAuditLogs = async () => {
    try { const response = await axios.get('/audit-logs?limit=20'); setAuditLogs(response.data.logs || []);
    } catch (error) { if (error.response?.status !== 403) console.error('Failed to load audit logs:', error); }
  };

  const loadChannelManagerData = async () => {
    try {
      const [otaRes, suggestionsRes, exceptionsRes] = await Promise.all([
        axios.get('/channel-manager/ota-reservations?status=pending'),
        axios.get('/rms/suggestions?status=pending'),
        axios.get('/channel-manager/exceptions?status=pending')
      ]);
      setOtaReservations(otaRes.data.reservations || []); setRmsSuggestions(suggestionsRes.data.suggestions || []);
      setExceptions(exceptionsRes.data.exceptions || []);
    } catch (error) { console.error('Failed to load channel manager data:', error); }
  };

  const handleImportOTA = async (otaId) => {
    try {
      const response = await axios.post(`/channel-manager/import-reservation/${otaId}`);
      toast.success(`${response.data.message} - Room ${response.data.room_number}`);
      loadChannelManagerData(); loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Failed to import reservation'); }
  };

  const handleApplyRMSSuggestion = async (suggestionId) => {
    try { const response = await axios.post(`/rms/apply-suggestion/${suggestionId}`); toast.success(response.data.message); loadChannelManagerData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Failed to apply suggestion'); }
  };

  const handleGenerateRMSSuggestions = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const nextWeek = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      const response = await axios.post(`/rms/generate-suggestions?start_date=${today}&end_date=${nextWeek}`);
      toast.success(response.data.message); loadChannelManagerData();
    } catch (error) { toast.error('Failed to generate suggestions'); }
  };

  const handleCheckIn = async (bookingId, forceClean = false) => {
    try {
      const params = new URLSearchParams({ create_folio: 'true' });
      if (forceClean) params.append('force_clean', 'true');
      const response = await axios.post(`/frontdesk/checkin/${bookingId}?${params}`);
      toast.success(`${response.data.message} - Room ${response.data.room_number}`);
      loadData(); loadFrontDeskData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Check-in failed'); }
  };

  const handleCheckOut = async (bookingId) => {
    try {
      const response = await axios.post(`/frontdesk/checkout/${bookingId}?auto_close_folios=true`);
      if (response.data.total_balance > 0.01) toast.warning(`Open balance on check-out: ${response.data.total_balance.toFixed(2)} ₺`);
      else toast.success(`${response.data.message} - ${response.data.folios_closed} folios closed`);
      loadData(); loadFrontDeskData(); loadHousekeepingData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Check-out failed'); }
  };

  const loadFolio = async (bookingId) => {
    try { const response = await axios.get(`/frontdesk/folio/${bookingId}`); setFolio(response.data); setSelectedBooking(bookingId); setOpenDialog('folio');
    } catch (error) { toast.error('Failed to load folio'); }
  };

  const handleCreateHKTask = async (e) => {
    e.preventDefault();
    try { await axios.post('/housekeeping/tasks', newHKTask); toast.success('Task created'); setOpenDialog(null); loadHousekeepingData(); setNewHKTask({ room_id: '', task_type: 'cleaning', priority: 'normal', notes: '' });
    } catch (error) { toast.error('Failed to create task'); }
  };

  const handleAssignHKTask = async (taskId, assignedTo) => {
    try {
      await axios.put(`/housekeeping/tasks/${taskId}`, null, { params: { assigned_to: assignedTo } });
      toast.success(`Görev ${assignedTo} kişisine atandı`);
      loadHousekeepingData();
    } catch (error) { toast.error('Atama başarısız'); }
  };

  const handleUpdateHKTask = async (taskId, status) => {
    try { await axios.put(`/housekeeping/tasks/${taskId}`, null, { params: { status } }); toast.success('Task updated'); loadHousekeepingData(); loadData();
    } catch (error) { toast.error('Failed to update task'); }
  };

  const handleCreateCompany = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post('/companies', newCompany);
      toast.success('Company created successfully'); setOpenDialog(null); loadData();
      const company = response.data; handleCompanySelect(company.id);
      setNewCompany({ name: '', corporate_code: '', tax_number: '', billing_address: '', contact_person: '', contact_email: '', contact_phone: '', contracted_rate: '', default_rate_type: '', default_market_segment: '', default_cancellation_policy: '', payment_terms: '', status: 'pending' });
    } catch (error) { toast.error('Failed to create company'); }
  };

  const handleCompanySelect = (companyId) => {
    if (companyId === "none") {
      setSelectedCompany(null);
      setNewBooking({ ...newBooking, company_id: null, contracted_rate: '', rate_type: '', market_segment: '', cancellation_policy: '', billing_address: '', billing_tax_number: '', billing_contact_person: '' });
      return;
    }
    const company = companies.find(c => c.id === companyId);
    if (company) {
      setSelectedCompany(company);
      setNewBooking({ ...newBooking, company_id: companyId, contracted_rate: company.contracted_rate || '', rate_type: company.default_rate_type || '', market_segment: company.default_market_segment || '', cancellation_policy: company.default_cancellation_policy || '', billing_address: company.billing_address || '', billing_tax_number: company.tax_number || '', billing_contact_person: company.contact_person || '' });
    }
  };

  const handleContractedRateSelect = (contractedRate) => {
    const rateMapping = {
      'corp_std': { rate_type: 'corporate', market_segment: 'corporate', cancellation_policy: 'h48' },
      'corp_pref': { rate_type: 'corporate', market_segment: 'corporate', cancellation_policy: 'flexible' },
      'gov': { rate_type: 'government', market_segment: 'government', cancellation_policy: 'h24' },
      'ta': { rate_type: 'wholesale', market_segment: 'wholesale', cancellation_policy: 'd7' },
      'crew': { rate_type: 'corporate', market_segment: 'crew', cancellation_policy: 'same_day' },
      'mice': { rate_type: 'package', market_segment: 'mice', cancellation_policy: 'd14' },
      'lts': { rate_type: 'long_stay', market_segment: 'long_stay', cancellation_policy: 'flexible' },
      'tou': { rate_type: 'wholesale', market_segment: 'wholesale', cancellation_policy: 'd14' }
    };
    const mapping = rateMapping[contractedRate];
    if (mapping) setNewBooking({ ...newBooking, contracted_rate: contractedRate, rate_type: mapping.rate_type, market_segment: mapping.market_segment, cancellation_policy: mapping.cancellation_policy });
  };

  const handleChildrenChange = (count) => {
    const childrenCount = parseInt(count) || 0;
    let newAges = [...newBooking.children_ages];
    if (childrenCount > newAges.length) newAges = [...newAges, ...Array(childrenCount - newAges.length).fill(0)];
    else newAges = newAges.slice(0, childrenCount);
    setNewBooking({ ...newBooking, children: childrenCount, children_ages: newAges, guests_count: newBooking.adults + childrenCount });
  };

  const handleChildAgeChange = (index, age) => {
    const newAges = [...newBooking.children_ages]; newAges[index] = parseInt(age) || 0;
    setNewBooking({ ...newBooking, children_ages: newAges });
  };

  const handleCreateBooking = async (e) => {
    e.preventDefault();
    if (newBooking.base_rate > 0 && newBooking.base_rate !== newBooking.total_amount && !newBooking.override_reason) { toast.error('Please provide a reason for rate override'); return; }
    if (!newBooking.guest_id) { toast.error('Please select guest'); return; }
    if (!newBooking.check_in || !newBooking.check_out) { toast.error('Please select check-in and check-out dates'); return; }
    await loadRateData(newBooking.channel, newBooking.company_id, newBooking.check_in);
    if (!multiRoomBooking || multiRoomBooking.length === 0) { toast.error('Please add at least one room'); return; }
    if (multiRoomBooking.find(r => !r.room_id)) { toast.error('Please select room for each line'); return; }
    try {
      const roomsPayload = multiRoomBooking.map(room => ({
        room_id: room.room_id, adults: room.adults, children: room.children, children_ages: room.children_ages || [],
        total_amount: room.total_amount, base_rate: room.base_rate, rate_plan: room.rate_plan || newBooking.rate_type || 'Standard', package_code: room.package_code || null
      }));
      await axios.post('/pms/bookings/multi-room', {
        guest_id: newBooking.guest_id, arrival_date: newBooking.check_in, departure_date: newBooking.check_out,
        rooms: roomsPayload, company_id: newBooking.company_id || null, channel: newBooking.channel || 'direct'
      });
      toast.success('Booking created successfully'); setOpenDialog(null); loadData(); setSelectedCompany(null);
      setNewBooking({ guest_id: '', room_id: '', check_in: '', check_out: '', adults: 1, children: 0, children_ages: [], guests_count: 1, total_amount: 0, base_rate: 0, channel: 'direct', company_id: '', contracted_rate: '', rate_type: '', market_segment: '', cancellation_policy: '', billing_address: '', billing_tax_number: '', billing_contact_person: '', override_reason: '' });
      setMultiRoomBooking([{ room_id: '', adults: 1, children: 0, children_ages: [], total_amount: 0, base_rate: 0, rate_plan: '', package_code: null }]);
    } catch (error) { toast.error(error.response?.data?.detail || 'Failed to create booking'); }
  };

  const loadBookingFolios = async (bookingId) => {
    try {
      const response = await axios.get(`/folio/booking/${bookingId}`);
      setFolios(response.data); setSelectedBooking(bookingId); setOpenDialog('folio-view');
      const guestFolio = response.data.find(f => f.folio_type === 'guest');
      if (guestFolio) loadFolioDetails(guestFolio.id);
    } catch (error) { toast.error('Failed to load folios'); }
  };

  const loadFolioDetails = async (folioId) => {
    try {
      const response = await axios.get(`/folio/${folioId}`);
      setSelectedFolio(response.data.folio); setFolioCharges(response.data.charges || []); setFolioPayments(response.data.payments || []);
    } catch (error) { toast.error('Failed to load folio details'); }
  };

  const updateRoomStatus = async (roomId, newStatus) => {
    try { await axios.put(`/pms/rooms/${roomId}`, { status: newStatus }); toast.success('Room status updated'); loadData(); loadHousekeepingData();
    } catch (error) { toast.error('Failed to update status'); }
  };

  const quickUpdateRoomStatus = async (roomId, newStatus) => {
    try { const response = await axios.put(`/housekeeping/room/${roomId}/status?new_status=${newStatus}`); toast.success(response.data.message); loadHousekeepingData(); loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Failed to update status'); }
  };

  const createRoomBlock = async () => {
    if (!selectedRoom) { toast.error('Please select a room'); return; }
    if (!newRoomBlock.reason || !newRoomBlock.start_date) { toast.error('Please fill in all required fields'); return; }
    try {
      const idempotencyKey = window.crypto?.randomUUID?.() || `room-block-create-${Date.now()}-${Math.random()}`;
      const response = await axios.post('/pms/room-blocks', { room_id: selectedRoom.id, ...newRoomBlock }, { headers: { 'Idempotency-Key': idempotencyKey } });
      if (response.data.warnings?.length > 0) response.data.warnings.forEach(w => toast.warning(w.message));
      toast.success(response.data.message); setOpenDialog(null); setSelectedRoom(null);
      setNewRoomBlock({ type: 'out_of_order', reason: '', details: '', start_date: '', end_date: '', allow_sell: false });
      loadHousekeepingData(); loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Failed to create room block'); }
  };

  const cancelRoomBlock = async (blockId) => {
    try {
      const idempotencyKey = window.crypto?.randomUUID?.() || `room-block-release-${Date.now()}-${Math.random()}`;
      await axios.post(`/pms/room-blocks/${blockId}/cancel`, null, { headers: { 'Idempotency-Key': idempotencyKey } });
      toast.success('Room block cancelled'); loadHousekeepingData(); loadData();
    } catch (error) { toast.error(error.response?.data?.detail || 'Failed to cancel block'); }
  };

  const loadGuest360 = async (guestId) => {
    setLoadingGuest360(true);
    try { const response = await axios.get(`/crm/guest/${guestId}`, { timeout: 15000 }); setGuest360Data(response.data); setOpenDialog('guest360');
    } catch (error) {
      if (error.code === 'ECONNABORTED') toast.error('Request timeout - Guest profile has too much data.');
      else toast.error(error.response?.data?.detail || 'Failed to load guest profile');
    } finally { setLoadingGuest360(false); }
  };

  const addGuestTag = async () => {
    if (!guestTag || !selectedGuest360) return;
    try { await axios.post(`/crm/guest/add-tag?guest_id=${selectedGuest360}&tag=${guestTag}`); toast.success('Tag added'); setGuestTag(''); loadGuest360(selectedGuest360);
    } catch (error) { toast.error('Failed to add tag'); }
  };

  const addGuestNote = async () => {
    if (!guestNote || !selectedGuest360) return;
    try { await axios.post(`/crm/guest/note?guest_id=${selectedGuest360}&note=${guestNote}`); toast.success('Note added'); setGuestNote(''); loadGuest360(selectedGuest360);
    } catch (error) { toast.error('Failed to add note'); }
  };

  if (loading) {
    return (
      <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
        <div className="flex items-center justify-center h-screen">
          <div className="text-center">
            <RefreshCw className="w-12 h-12 animate-spin text-blue-600 mx-auto mb-4" />
            <p className="text-lg font-medium text-gray-700">Loading PMS Data...</p>
            <p className="text-sm text-gray-500 mt-2">Please wait while we load your data</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="pms">
      <div className="p-6 space-y-6">
        <div className="mb-6 flex justify-between items-start gap-4">
          <div>
            <h1 className="text-4xl font-bold mb-2" style={{ fontFamily: 'Space Grotesk' }}>{t('pms.title')}</h1>
            <p className="text-gray-600">{t('pms.subtitle')}</p>
          </div>
          <div className="w-96">
            <GlobalSearch onSelectResult={(result) => {
              if (result.type === 'page' && result.data?.path) {
                navigate(result.data.path);
                toast.info(result.data.label || result.data.path);
                return;
              }
              const typeTabMap = { guest: 'frontdesk', booking: 'frontdesk', room: 'rooms', company: 'frontdesk', housekeeping: 'housekeeping' };
              const tab = typeTabMap[result.type] || 'frontdesk';
              setActiveTab(tab); window.location.hash = tab;
              toast.info(`${result.data.name || result.data.room_number || result.data.id} - redirected to ${tab}`);
            }} />
          </div>
        </div>

        <Card className="border-blue-200 bg-gradient-to-r from-blue-50 to-purple-50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="text-sm font-semibold text-gray-700">{t('pms.quickActions', 'Quick Actions')}:</div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setOpenDialog('booking')}>
                  <Plus className="w-4 h-4 mr-2" />{t('pms.newBooking', 'New Booking')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setOpenDialog('guest')}>
                  <UserPlus className="w-4 h-4 mr-2" />{t('pms.newGuest', 'New Guest')}
                </Button>
                <Button size="sm" variant="outline" onClick={async () => {
                  try { const response = await axios.get('/reports/daily-flash'); if (response.data) { toast.success('Flash report generated!'); setActiveTab('reports'); } else { toast.info('No flash report data available'); }
                  } catch (error) { toast.error('Failed to generate report'); }
                }}>
                  <FileText className="w-4 h-4 mr-2" />{t('pms.flashReport', 'Flash Report')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => loadData()}>
                  <RefreshCw className="w-4 h-4 mr-2" />Refresh
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Tabs value={activeTab} className="w-full" onValueChange={(v) => { setActiveTab(v); window.location.hash = v; }}>
          <TabsList className="flex flex-wrap h-auto w-full gap-1 p-1">
            {visibleTabs.map((tab) => {
              const Icon = tab.icon;
              const label = tab.labelKey ? t(tab.labelKey) : tab.labelText;
              return (<TabsTrigger key={tab.key} value={tab.key} data-testid={tab.testId}>{Icon ? <Icon className="w-4 h-4 mr-2" /> : null}{label}</TabsTrigger>);
            })}
          </TabsList>

          {/* Tur 5: Tüm tab içerikleri lazy chunk — tek Suspense yeterli.
              Sticky-mount + lazy birlikte: ziyaret edilmemiş tab indirilmez,
              ziyaret edilmiş tab tekrar gelse RAM'den anında render. */}
          <Suspense fallback={<div className="p-6 text-sm text-slate-500">Yükleniyor…</div>}>
          {visitedTabs.has('frontdesk') && (
            <FrontdeskTab t={t} arrivals={arrivals} departures={departures} inhouse={inhouse} bookings={bookings} rooms={rooms} guests={guests} aiPrediction={aiPrediction} aiPatterns={aiPatterns} handleCheckIn={handleCheckIn} handleCheckOut={handleCheckOut} loadFolio={loadFolio} loadFrontDeskData={loadFrontDeskData} loadData={loadData} loading={fdLoading} error={fdError} tenant={tenant} setReservationDetailId={setReservationDetailId} />
          )}
          {visitedTabs.has('housekeeping') && (
            <HousekeepingTab roomBlocks={roomBlocks} roomStatusBoard={roomStatusBoard} dueOutRooms={dueOutRooms} stayoverRooms={stayoverRooms} arrivalRooms={arrivalRooms} housekeepingTasks={housekeepingTasks} quickUpdateRoomStatus={quickUpdateRoomStatus} setOpenDialog={setOpenDialog} setSelectedRoom={setSelectedRoom} setNewBooking={setNewBooking} setMaintenanceForm={setMaintenanceForm} setMaintenanceDialogOpen={setMaintenanceDialogOpen} handleUpdateHKTask={handleUpdateHKTask} handleAssignHKTask={handleAssignHKTask} currentUserName={user?.name} loadHousekeepingData={loadHousekeepingData} onBookingCardClick={async (bookingId) => {
              let booking = bookings.find(b => b.id === bookingId);
              if (!booking) {
                try {
                  const res = await axios.get(`/pms/bookings/${bookingId}`);
                  booking = res.data;
                } catch { toast.error('Rezervasyon yüklenemedi'); return; }
              }
              setSelectedBookingDetail(booking);
              setOpenDialog('bookingDetail');
            }} toast={toast} loading={hkLoading} />
          )}
          {visitedTabs.has('rooms') && (
            <TabsContent value="rooms" className="space-y-4">
              <RoomsTab rooms={rooms} bookings={bookings} guests={guests} handleCheckIn={handleCheckIn} handleCheckOut={handleCheckOut} onPayment={(bookingId) => { setSelectedBookingDetail(bookings.find(b => b.id === bookingId) || null); setOpenDialog('bookingDetail'); }} onGuestClick={(guestId) => { const guest = guests.find(g => g.id === guestId); if (guest) { setSelectedGuest(guest); setOpenDialog('guestInfo'); } }} onBookingDoubleClick={(booking) => setReservationDetailId(booking.id)} onDataRefresh={loadData} />
              {selectedRoom && <RoomFeaturesPanel room={selectedRoom} onUpdate={loadData} />}
            </TabsContent>
          )}
          {visitedTabs.has('guests') && (
            <GuestsTab guests={guests} setOpenDialog={setOpenDialog} setSelectedGuest360={setSelectedGuest360} loadGuest360={loadGuest360} setNewBooking={setNewBooking} t={t} />
          )}
          {visitedTabs.has('bookings') && (
            <BookingsTab bookingStats={bookingStats} bookings={bookings} groupedBookings={groupedBookings} guests={guests} rooms={rooms} companies={companies} handleCheckIn={handleCheckIn} handleCheckOut={handleCheckOut} loadBookingFolios={loadBookingFolios} loadGuest360={loadGuest360} setSelectedGuest360={setSelectedGuest360} setOpenDialog={setOpenDialog} setSelectedBooking={setSelectedBooking} setSelectedBookingDetail={setSelectedBookingDetail} toast={toast} isLite={isLite} roomsCount={roomsCount} activeTab={activeTab} />
          )}
          {visitedTabs.has('cashier') && <TabsContent value="cashier" className="space-y-4"><CashierTab user={user} /></TabsContent>}
          {visitedTabs.has('upsell') && <TabsContent value="upsell" className="space-y-4"><UpsellTab bookings={bookings} /></TabsContent>}
          {visitedTabs.has('internal_chat') && <TabsContent value="internal_chat" className="space-y-4"><InternalChatTab currentUser={user} /></TabsContent>}
          {visitedTabs.has('reports') && <TabsContent value="reports" className="space-y-4"><ReportsTab /></TabsContent>}
          {visitedTabs.has('flash') && <TabsContent value="flash" className="space-y-4"><FlashReportContent rooms={rooms} bookings={bookings} arrivals={arrivals} departures={departures} inhouse={inhouse} /></TabsContent>}
          {visitedTabs.has('tasks') && <TabsContent value="tasks" className="space-y-4"><StaffTaskManager /></TabsContent>}
          {visitedTabs.has('feedback') && <TabsContent value="feedback" className="space-y-4"><FeedbackSystem /></TabsContent>}
          {visitedTabs.has('allotment') && <TabsContent value="allotment" className="space-y-4"><AllotmentGrid /></TabsContent>}
          {visitedTabs.has('pos') && <TabsContent value="pos" className="space-y-4"><POSTab /></TabsContent>}
          {visitedTabs.has('laundry') && <TabsContent value="laundry" className="space-y-4"><LaundryTab /></TabsContent>}
          {visitedTabs.has('concierge') && <TabsContent value="concierge" className="space-y-4"><ConciergeDesk /></TabsContent>}
          {visitedTabs.has('revenue') && <TabsContent value="revenue" className="space-y-4"><RevenueControls rooms={rooms} /></TabsContent>}
          {visitedTabs.has('manager_report') && <TabsContent value="manager_report" className="space-y-4"><ManagerDailyReport rooms={rooms} bookings={bookings} arrivals={arrivals} departures={departures} inhouse={inhouse} /></TabsContent>}
          {visitedTabs.has('kbs') && <TabsContent value="kbs" className="space-y-4"><KBSNotification bookings={bookings} guests={guests} /></TabsContent>}
          {visitedTabs.has('kvkk') && <TabsContent value="kvkk" className="space-y-4"><KVKKManager /></TabsContent>}
          </Suspense>
        </Tabs>

        <FolioDialog open={openDialog === 'folio'} onClose={() => setOpenDialog(null)} folio={folio} bookingId={selectedBooking} onFolioUpdated={() => loadFolio(selectedBooking)} />
        <RoomCreateDialog open={openDialog === 'room'} onClose={() => setOpenDialog(null)} onRoomCreated={loadData} />
        <RoomImageUploadDialog open={openDialog === 'room-images'} onClose={() => setOpenDialog(null)} selectedRoom={selectedRoom} setSelectedRoom={setSelectedRoom} onDataRefresh={loadData} />
        <BulkDeleteRoomsDialog open={openDialog === 'bulk-delete-rooms'} onClose={() => setOpenDialog(null)} selectedRooms={selectedRooms} rooms={rooms} onDeleted={() => { setSelectedRooms([]); setBulkRoomMode(false); loadData(); }} />
        <BulkRoomsDialog open={openDialog === 'bulk-rooms'} onClose={() => setOpenDialog(null)} onRoomsCreated={loadData} user={user} />
        <GuestCreateDialog open={openDialog === 'guest'} onClose={() => setOpenDialog(null)} onGuestCreated={loadData} />
        {/* Tur 5: Büyük dialog'lar lazy + sticky-visited.
            Bir kez açıldıktan sonra DOM'da kalır (visitedDialogs Set),
            chunk yeniden indirilmez, kapanış animasyonu çalışır.
            open prop her zaman gerçek koşulu yansıtır → modal davranışı korunur. */}
        {visitedDialogs.has('booking') && (
          <Suspense fallback={null}>
            <BookingDialog open={openDialog === 'booking'} onClose={() => setOpenDialog(null)} guests={guests} rooms={rooms} companies={companies} ratePlans={ratePlans} packages={packages} newBooking={newBooking} setNewBooking={setNewBooking} multiRoomBooking={multiRoomBooking} handleCreateBooking={handleCreateBooking} handleCompanySelect={handleCompanySelect} handleContractedRateSelect={handleContractedRateSelect} handleChildrenChange={handleChildrenChange} handleChildAgeChange={handleChildAgeChange} addRoomToMultiBooking={addRoomToMultiBooking} removeRoomFromMultiBooking={removeRoomFromMultiBooking} updateMultiRoomField={updateMultiRoomField} updateMultiRoomChildrenAges={updateMultiRoomChildrenAges} updateMultiRoomChildAge={updateMultiRoomChildAge} isLite={isLite} setOpenDialog={setOpenDialog} />
          </Suspense>
        )}
        <CompanyDialog open={openDialog === 'company'} onClose={() => setOpenDialog(null)} newCompany={newCompany} setNewCompany={setNewCompany} onSubmit={handleCreateCompany} />
        {visitedDialogs.has('folio-view') && (
          <Suspense fallback={null}>
            <FolioViewDialog open={openDialog === 'folio-view'} onClose={() => setOpenDialog(null)} selectedFolio={selectedFolio} folioCharges={folioCharges} folioPayments={folioPayments} guests={guests} bookings={bookings} onChargePosted={(folioId) => { loadFolioDetails(folioId); }} onPaymentPosted={(folioId) => { loadFolioDetails(folioId); }} />
          </Suspense>
        )}
        <HKTaskDialog open={openDialog === 'hktask'} onClose={() => setOpenDialog(null)} rooms={rooms} newHKTask={newHKTask} setNewHKTask={setNewHKTask} onSubmit={handleCreateHKTask} />
        <RoomBlockCreateDialog open={openDialog === 'roomblock'} onClose={() => { setOpenDialog(null); setSelectedRoom(null); }} selectedRoom={selectedRoom} newRoomBlock={newRoomBlock} setNewRoomBlock={setNewRoomBlock} onSubmit={createRoomBlock} />
        <RoomBlockViewDialog open={openDialog === 'roomblock-view'} onClose={() => setOpenDialog(null)} roomBlocks={roomBlocks} onCancel={cancelRoomBlock} />
        <FindRoomDialog open={openDialog === 'findroom'} onClose={() => setOpenDialog(null)} criteria={findRoomCriteria} setCriteria={setFindRoomCriteria} />
        <PaymentDialog open={openDialog === 'payment'} onClose={() => setOpenDialog(null)} paymentForm={paymentForm} setPaymentForm={setPaymentForm} bookingId={selectedBooking} onPaymentSuccess={() => { loadData(); loadFrontDeskData(); }} />

        {selectedBookingDetail && (
          <BookingDetailDialog
            open={openDialog === 'bookingDetail'}
            onClose={() => { setOpenDialog(null); setSelectedBookingDetail(null); }}
            booking={selectedBookingDetail}
            guests={guests}
            rooms={rooms}
            companies={companies}
            onCheckIn={handleCheckIn}
            onCheckOut={handleCheckOut}
            onViewFolio={loadBookingFolios}
            onBookingUpdated={loadData}
          />
        )}

        {selectedGuest && (
          <GuestInfoDialog
            open={openDialog === 'guestInfo'}
            onClose={() => { setOpenDialog(null); setSelectedGuest(null); }}
            guest={selectedGuest}
          />
        )}

        {guest360Data && visitedDialogs.has('guest360') && (
          <Suspense fallback={null}>
            <Guest360Dialog
              open={openDialog === 'guest360'}
              onClose={() => { setOpenDialog(null); setGuest360Data(null); }}
              guest360Data={guest360Data}
              guestTag={guestTag}
              setGuestTag={setGuestTag}
              guestNote={guestNote}
              setGuestNote={setGuestNote}
              addGuestTag={addGuestTag}
              addGuestNote={addGuestNote}
            />
          </Suspense>
        )}

        <MaintenanceDialog
          open={maintenanceDialogOpen}
          onClose={() => setMaintenanceDialogOpen(false)}
          maintenanceForm={maintenanceForm}
          setMaintenanceForm={setMaintenanceForm}
          onSuccess={() => { loadHousekeepingData(); loadData(); }}
        />

        {reservationDetailId && (
          <Suspense fallback={null}>
            <ReservationDetailModal
              bookingId={reservationDetailId}
              onClose={() => setReservationDetailId(null)}
            />
          </Suspense>
        )}

        <FloatingActionButton
          actions={[
            { label: t('pms.newBooking', 'New Booking'), icon: Calendar, onClick: () => setOpenDialog('booking') },
            { label: t('pms.newGuest', 'New Guest'), icon: UserPlus, onClick: () => setOpenDialog('guest') },
            { label: t('pms.newRoom', 'New Room'), icon: BedDouble, onClick: () => setOpenDialog('room') },
          ]}
        />
      </div>
    </Layout>
  );
};

export default PMSModule;