import { useState, useEffect, useMemo, useCallback, Suspense, lazy, memo } from 'react';
const ReservationDetailModal = lazy(() => import('@/pages/ReservationDetailModal'));
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
import GlobalSearch from '@/components/GlobalSearch';
import PickupPaceChart from '@/components/PickupPaceChart';
import LeadTimeCurve from '@/components/LeadTimeCurve';
import ForecastGraph from '@/components/ForecastGraph';
import RevenueDashboard from '@/components/RevenueDashboard';
import AIActivityLog from '@/components/AIActivityLog';
import StaffTaskManager from '@/components/StaffTaskManager';
import FeedbackSystem from '@/components/FeedbackSystem';
import AllotmentGrid from '@/components/AllotmentGrid';
import GroupRevenueByCompany from '@/components/GroupRevenueByCompany';
import PickupPaceReport from '@/components/PickupPaceReport';
import FrontdeskTab from '@/components/pms/FrontdeskTab';
import HousekeepingTab from '@/components/pms/HousekeepingTab';
import BookingsTab from '@/components/pms/BookingsTab';
import RoomsTab from '@/components/pms/RoomsTab';
import BookingDialog from '@/components/pms/BookingDialog';
import BookingDetailDialog from '@/components/pms/BookingDetailDialog';
import BulkRoomsDialog from '@/components/pms/BulkRoomsDialog';
import CompanyDialog from '@/components/pms/CompanyDialog';
import FindRoomDialog from '@/components/pms/FindRoomDialog';
import HKTaskDialog from '@/components/pms/HKTaskDialog';
import MaintenanceDialog from '@/components/pms/MaintenanceDialog';
import { RoomBlockCreateDialog, RoomBlockViewDialog } from '@/components/pms/RoomBlockDialogs';
import GuestsTab from '@/components/pms/GuestsTab';
import GuestInfoDialog from '@/components/pms/GuestInfoDialog';
import PaymentDialog from '@/components/pms/PaymentDialog';
import Guest360Dialog from '@/components/pms/Guest360Dialog';
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
  Star, Send, MessageSquare, UserPlus, ArrowRight, RefreshCw, User, Search, CheckSquare, Download, Clock, Crown
} from 'lucide-react';
import FloatingActionButton from '@/components/FloatingActionButton';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
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
    type: 'out_of_order',
    reason: '',
    details: '',
    start_date: '',
    end_date: '',
    allow_sell: false
  });
  

  // Search and filter states
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');
  const [quickFilters, setQuickFilters] = useState({
    roomType: '',
    bookingStatus: '',
    paymentStatus: '',
    roomView: '',
    amenity: ''
  });
  
  // Bulk selection states
  const [selectedRooms, setSelectedRooms] = useState([]);
  const [bulkRoomMode, setBulkRoomMode] = useState(false);

  // Phase H - CRM & Upsell states
  const [selectedGuest360, setSelectedGuest360] = useState(null);
  const [guest360Data, setGuest360Data] = useState(null);
  const [loadingGuest360, setLoadingGuest360] = useState(false);
  const [selectedBookingDetail, setSelectedBookingDetail] = useState(null);
  const [reservationDetailId, setReservationDetailId] = useState(null);
  const [expandedChargeItems, setExpandedChargeItems] = useState({});
  const [guestTag, setGuestTag] = useState('');
  const [guestNote, setGuestNote] = useState('');
  const [upsellOffers, setUpsellOffers] = useState([]);
  const [messageTemplates, setMessageTemplates] = useState([]);
  const [newMessage, setNewMessage] = useState({
    channel: 'email',
    recipient: '',
    subject: '',
    body: '',
    template_id: null
  });
  const [sentMessages, setSentMessages] = useState([]);
  const [posOrders, setPosOrders] = useState([]);
  const [posRevenue, setPosRevenue] = useState({
    restaurant: 0,
    bar: 0,
    room_service: 0,
    total: 0
  });
  const [findRoomCriteria, setFindRoomCriteria] = useState({
    check_in: '',
    check_out: '',
    room_type: '',
    guests: 1
  });

  const [maintenanceDialogOpen, setMaintenanceDialogOpen] = useState(false);
  const [maintenanceForm, setMaintenanceForm] = useState({
    room_id: null,
    room_number: '',
    issue_type: 'housekeeping_damage',
    priority: 'normal',
    description: ''
  });

  const [reports, setReports] = useState({
    occupancy: null,
    revenue: null,
    daily: null,
    forecast: [],
    dailyFlash: null,
    marketSegment: null,
    companyAging: null,
    hkEfficiency: null
  });
  
  // PMS Lite için izinli sekmeler
  const LITE_TABS = new Set([
    'frontdesk',
    'housekeeping',
    'rooms',
    'guests',
    'bookings',
    'reports',
  ]);

  const ALL_TABS = [
    { key: 'frontdesk', labelKey: 'pms.frontDesk', icon: UserCheck, testId: 'tab-frontdesk' },
    { key: 'housekeeping', labelKey: 'pms.housekeeping', icon: ClipboardList, testId: 'tab-housekeeping' },
    { key: 'rooms', labelKey: 'pms.rooms', icon: BedDouble, testId: 'tab-rooms' },
    { key: 'guests', labelKey: 'pms.guests', icon: Users, testId: 'tab-guests' },
    { key: 'bookings', labelKey: 'pms.bookings', icon: Calendar, testId: 'tab-bookings' },
    { key: 'upsell', labelText: '🤖 Upsell', icon: TrendingUp, testId: 'tab-upsell' },
    { key: 'messaging', labelText: '💬 Messages', icon: null, testId: 'tab-messaging' },
    { key: 'reports', labelKey: 'pms.reports', icon: FileText, testId: 'tab-reports' },
    { key: 'tasks', labelText: '🔧 Tasks', icon: null, testId: 'tab-tasks' },
    { key: 'feedback', labelText: '⭐ Feedback', icon: null, testId: 'tab-feedback' },
    { key: 'allotment', labelText: '🏢 Allotment', icon: null, testId: 'tab-allotment' },
    { key: 'pos', labelText: '🍽️ POS', icon: null, testId: 'tab-pos' },
  ];

  const visibleTabs = isLite
    ? ALL_TABS.filter((tab) => LITE_TABS.has(tab.key))
    : ALL_TABS;

  // Active tab state - check URL hash on mount (Lite'ta izinli olmayan hash gelirse frontdesk'e zorla)
  const [activeTab, setActiveTab] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    if (hash && (!isLite || LITE_TABS.has(hash))) {
      return hash;
    }
    return 'frontdesk';
  });

  // Hash change listener so that navigation with #tab updates the UI
  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace('#', '');

      // Lite planda izinli olmayan bir hash gelirse frontdesk'e dön
      if (isLite && hash && !LITE_TABS.has(hash)) {
        setActiveTab('frontdesk');
        window.location.hash = 'frontdesk';
        return;
      }

      setActiveTab(hash || 'frontdesk');
    };

    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [isLite]);

  // Handle one-time dialog open requests from onboarding (Lite only)
  useEffect(() => {
    if (!isLite) return;
    if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') return;

    const tenantId = tenant?.id || tenant?._id || tenant?.tenant_id || 'unknown';
    const key = `pms_open_dialog_once:${tenantId}`;
    const val = window.localStorage.getItem(key);

    if (val && activeTab === 'rooms') {
      setOpenDialog(val);
      window.localStorage.removeItem(key);
    }
  }, [isLite, tenant, activeTab]);

  // Apply first booking prefill for Lite when booking dialog opens
  useEffect(() => {
    if (!isLite) return;
    if (openDialog !== 'booking') return;
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

      setNewBooking((prev) => ({
        ...prev,
        check_in: fmt(today),
        check_out: fmt(tomorrow),
        adults: prev?.adults || 2,
      }));

      window.localStorage.removeItem(key);
    } catch (e) {
      console.warn('Failed to apply booking prefill', e);
    }
  }, [isLite, tenant, openDialog]);

  const [newRoom, setNewRoom] = useState({
    room_number: '',
    room_type: 'standard',
    floor: 1,
    capacity: 2,
    base_price: 100,
    amenities: [],
    view: '',
    bed_type: ''
  });

  // Bulk delete UI
  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState('');

  const [newGuest, setNewGuest] = useState({
    name: '', email: '', phone: '', id_number: '', address: ''
  });

  const [newBooking, setNewBooking] = useState({
    guest_id: '',
    room_id: '',
    check_in: '',
    check_out: '',
    adults: 1,
    children: 0,
    children_ages: [],
    guests_count: 1,
    total_amount: 0,
    base_rate: 0,
    channel: 'direct',
    company_id: '',
    contracted_rate: '',
    rate_type: '',
    market_segment: '',
    cancellation_policy: '',
    billing_address: '',
    billing_tax_number: '',
    billing_contact_person: '',
    override_reason: ''
  });

  // Multi-room booking state: each item is one room in the booking
  const [multiRoomBooking, setMultiRoomBooking] = useState([
    {
      room_id: '',
      adults: 1,
      children: 0,
      children_ages: [],
      total_amount: 0,
      base_rate: 0,
      rate_plan: '',
      package_code: null
    }
  ]);

  const [newCompany, setNewCompany] = useState({
    name: '',
    corporate_code: '',
    tax_number: '',
    billing_address: '',
    contact_person: '',
    contact_email: '',
    contact_phone: '',
    contracted_rate: '',
    default_rate_type: '',
    default_market_segment: '',
    default_cancellation_policy: '',
    payment_terms: '',
    status: 'pending'
  });

  // Lightweight stats for UI (kept outside heavy JSX where possible)
  const bookingStats = useMemo(() => {
    const total = bookings.length;
    const confirmed = bookings.filter(b => b.status === 'confirmed').length;
    const checkedIn = bookings.filter(b => b.status === 'checked_in').length;
    const totalRevenue = bookings.reduce((sum, b) => sum + (b.total_amount || 0), 0);
    const avgAdr = total > 0 ? totalRevenue / total : 0;
    return { total, confirmed, checkedIn, totalRevenue, avgAdr };
  }, [bookings]);

  const [newCharge, setNewCharge] = useState({
    charge_type: 'food', description: '', amount: 0, quantity: 1
  });

  const [newFolioCharge, setNewFolioCharge] = useState({
    charge_category: 'room',
    description: '',
    amount: 0,
    quantity: 1,
    auto_calculate_tax: false
  });

  const [newPayment, setNewPayment] = useState({
    amount: 0, method: 'card', reference: '', notes: ''
  });

  const [newFolioPayment, setNewFolioPayment] = useState({
    amount: 0,
    method: 'card',
    payment_type: 'interim',
    reference: '',
    notes: ''
  });

  const [paymentForm, setPaymentForm] = useState({
    amount: 0,
    method: 'card',
    payment_type: 'interim',
    reference: '',
    notes: ''
  });

  const addRoomToMultiBooking = () => {
    setMultiRoomBooking(prev => [
      ...prev,
      {
        room_id: '',
        adults: 1,
        children: 0,
        children_ages: [],
        total_amount: 0,
        base_rate: 0,
        rate_plan: '',
        package_code: null
      }
    ]);
  };

  const removeRoomFromMultiBooking = (index) => {
    setMultiRoomBooking(prev => {
      if (prev.length === 1) return prev; // En az 1 oda kalsın
      return prev.filter((_, i) => i !== index);
    });
  };

  const updateMultiRoomField = (index, field, value) => {
    setMultiRoomBooking(prev => prev.map((room, i) => {
      if (i !== index) return room;
      if (field === 'adults' || field === 'children' || field === 'base_rate' || field === 'total_amount') {
        const numeric = field === 'base_rate' || field === 'total_amount'
          ? parseFloat(value) || 0
          : parseInt(value) || 0;
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
      if (count > ages.length) {
        ages = [...ages, ...Array(count - ages.length).fill(0)];
      } else {
        ages = ages.slice(0, count);
      }
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

  const [newHKTask, setNewHKTask] = useState({
    room_id: '', task_type: 'cleaning', priority: 'normal', notes: ''
  });

  useEffect(() => {
    // Only load essential data on initial mount
    loadData();
    // Load audit logs and channel manager data lazily (after 1 second)
    setTimeout(() => {
      loadAuditLogs();
      loadChannelManagerData();
    }, 1000);
  }, []);
  
  // Flags to track if tab-specific data has been loaded at least once
  const [hasLoadedFrontdesk, setHasLoadedFrontdesk] = useState(false);
  const [hasLoadedHousekeeping, setHasLoadedHousekeeping] = useState(false);
  const [hasLoadedReports, setHasLoadedReports] = useState(false);

  // Load data when tab changes (lazy-load per tab, but only once)
  useEffect(() => {
    if (activeTab === 'reports' && !hasLoadedReports) {
      console.log('🔄 Reports tab activated, loading reports (first time)...');
      loadReports();
      setHasLoadedReports(true);
    } else if (activeTab === 'frontdesk' && !hasLoadedFrontdesk) {
      console.log('🔄 Frontdesk tab activated, loading data (first time)...');
      loadFrontDeskData();
      setHasLoadedFrontdesk(true);
    } else if (activeTab === 'housekeeping' && !hasLoadedHousekeeping) {
      console.log('🔄 Housekeeping tab activated, loading data (first time)...');
      loadHousekeepingData();
      setHasLoadedHousekeeping(true);
    }
  }, [activeTab, hasLoadedFrontdesk, hasLoadedHousekeeping, hasLoadedReports]);

  const loadData = async () => {
    try {
      // PERFORMANCE OPTIMIZED: Load only essential data with limits for 550+ room properties
      const today = new Date().toISOString().split('T')[0];
      const futureDate = new Date();
      futureDate.setDate(futureDate.getDate() + 90);
      const futureDateStr = futureDate.toISOString().split('T')[0];
      
      const results = await Promise.allSettled([
        axios.get('/pms/rooms?limit=100', { timeout: 15000 }), // Limit rooms for initial load
        axios.get('/pms/guests?limit=100', { timeout: 15000 }), // Limit guests to 100
        axios.get(`/pms/bookings?start_date=${today}&end_date=${futureDateStr}&limit=200`, { timeout: 15000 }), // Next 90 days
        axios.get('/companies?limit=50', { timeout: 15000 }) // Limit companies to 50
      ]);

      const [roomsRes, guestsRes, bookingsRes, companiesRes] = results.map((r) => (r.status === 'fulfilled' ? r.value : null));

      // Log failures but do not hard-fail the entire PMS screen
      results.forEach((r, idx) => {
        if (r.status === 'rejected') {
          console.warn('PMS loadData partial failure:', idx, r.reason?.response?.status, r.reason?.config?.url, r.reason);
        }
      });

      const rawBookings = bookingsRes?.data || [];
      const grouped = [];
      const seenGroupIds = new Set();

      // First, handle grouped bookings (with group_booking_id)
      rawBookings
        .filter(b => b.group_booking_id)
        .forEach(b => {
          if (seenGroupIds.has(b.group_booking_id)) return;
          const sameGroup = rawBookings.filter(x => x.group_booking_id === b.group_booking_id);
          seenGroupIds.add(b.group_booking_id);
          grouped.push({
            type: 'group',
            group_booking_id: b.group_booking_id,
            master_booking: b,
            bookings: sameGroup
          });
        });

      // Then add single bookings (no group id)
      rawBookings
        .filter(b => !b.group_booking_id)
        .forEach(b => {
          grouped.push({
            type: 'single',
            booking: b
          });
        });

      setGroupedBookings(grouped);

      setRooms(roomsRes?.data || []);
      setGuests(guestsRes?.data || []);
      setBookings(bookingsRes?.data || []);
      setCompanies(companiesRes?.data || []);
    } catch (error) {
      toast.error('Failed to load data');
      console.error('PMS data load error:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadFrontDeskData = async () => {
    try {
      const [arrivalsRes, departuresRes, inhouseRes] = await Promise.all([
        axios.get('/frontdesk/arrivals'),
        axios.get('/frontdesk/departures'),
        axios.get('/frontdesk/inhouse')
      ]);
      setArrivals(arrivalsRes.data);
      setDepartures(departuresRes.data);
      setInhouse(inhouseRes.data);
      
      // Load AI insights
      loadAIInsights();
    } catch (error) {
      toast.error('Failed to load front desk data');
    }
  };

  const loadAIInsights = async () => {
    try {
      const [predictionRes, patternsRes] = await Promise.all([
        axios.get('/ai/pms/occupancy-prediction').catch(() => null),
        axios.get('/ai/pms/guest-patterns').catch(() => null)
      ]);
      if (predictionRes) {
        const raw = predictionRes.data || {};
        // Normalize AI prediction response to a safe, flattened shape
        const normalizedPrediction = {
          current_occupancy: typeof raw.current_occupancy === 'number' ? raw.current_occupancy : 0,
          upcoming_bookings: typeof raw.upcoming_bookings === 'number' ? raw.upcoming_bookings : 0,
          // prediction can be string or object; keep as-is for FrontdeskTab which handles both
          prediction: raw.prediction,
        };
        setAiPrediction(normalizedPrediction);
      }
      if (patternsRes) {
        const rawPatterns = patternsRes.data || {};
        // Normalize guest patterns response to always have a flat insights array of strings
        const insights = Array.isArray(rawPatterns.insights)
          ? rawPatterns.insights.map((item) =>
              typeof item === 'string' ? item : JSON.stringify(item)
            )
          : [];
        setAiPatterns({ insights });
      }
    } catch (error) {
      // Fail silently - AI features are optional
      console.error('AI insights not available');
    }
  };

  const loadHousekeepingData = async () => {
    try {
      // Load essential data first
      const [tasksRes, boardRes] = await Promise.all([
        axios.get('/housekeeping/tasks'),
        axios.get('/housekeeping/room-status')
      ]);
      setHousekeepingTasks(tasksRes.data);
      setRoomStatusBoard(boardRes.data);
      
      // Load additional data in background
      setTimeout(async () => {
        try {
          const [dueOutRes, stayoverRes, arrivalsRes, blocksRes] = await Promise.all([
            axios.get('/housekeeping/due-out'),
            axios.get('/housekeeping/stayovers'),
            axios.get('/housekeeping/arrivals'),
            axios.get('/pms/room-blocks?status=active')
          ]);
          setDueOutRooms(dueOutRes.data.due_out_rooms || []);
          setStayoverRooms(stayoverRes.data.stayover_rooms || []);
          setArrivalRooms(arrivalsRes.data.arrival_rooms || []);
          setRoomBlocks(blocksRes.data.blocks || []);
        } catch (error) {
          console.error('Failed to load additional housekeeping data:', error);
        }
      }, 500);
    } catch (error) {
      toast.error('Failed to load housekeeping data');
    }
  };

  // Cached rate plans and packages to avoid refetching on every change
  const [ratePlans, setRatePlans] = useState([]);
  const [packages, setPackages] = useState([]);

  const loadRateData = async (channel, companyId, stayDate) => {
    try {
      const params = {};
      if (channel) params.channel = channel;
      if (companyId) params.company_id = companyId;
      if (stayDate) params.stay_date = stayDate;
      const [rpRes, pkgRes] = await Promise.all([
        axios.get('/rates/rate-plans', { params }),
        axios.get('/rates/packages')
      ]);
      setRatePlans(rpRes.data || []);
      setPackages(pkgRes.data || []);
    } catch (error) {
      console.error('Failed to load rate plans/packages', error);
      toast.error('Failed to load rate plans');
    }
  };

  const loadAuditLogs = async () => {
    try {
      // Reduce limit for faster load
      const response = await axios.get('/audit-logs?limit=20');
      setAuditLogs(response.data.logs || []);
    } catch (error) {
      // Permission denied is okay
      if (error.response?.status !== 403) {
        console.error('Failed to load audit logs:', error);
      }
    }
  };

  const loadChannelManagerData = async () => {
    try {
      const [otaRes, suggestionsRes, exceptionsRes] = await Promise.all([
        axios.get('/channel-manager/ota-reservations?status=pending'),
        axios.get('/rms/suggestions?status=pending'),
        axios.get('/channel-manager/exceptions?status=pending')
      ]);
      setOtaReservations(otaRes.data.reservations || []);
      setRmsSuggestions(suggestionsRes.data.suggestions || []);
      setExceptions(exceptionsRes.data.exceptions || []);
    } catch (error) {
      console.error('Failed to load channel manager data:', error);
    }
  };

  const handleImportOTA = async (otaId) => {
    try {
      const response = await axios.post(`/channel-manager/import-reservation/${otaId}`);
      toast.success(`✅ ${response.data.message} - Room ${response.data.room_number}`);
      loadChannelManagerData();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to import reservation');
    }
  };

  const handleApplyRMSSuggestion = async (suggestionId) => {
    try {
      const response = await axios.post(`/rms/apply-suggestion/${suggestionId}`);
      toast.success(`✅ ${response.data.message}`);
      loadChannelManagerData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to apply suggestion');
    }
  };

  const handleGenerateRMSSuggestions = async () => {
    try {
      const today = new Date().toISOString().split('T')[0];
      const nextWeek = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      const response = await axios.post(`/rms/generate-suggestions?start_date=${today}&end_date=${nextWeek}`);
      toast.success(`✅ ${response.data.message}`);
      loadChannelManagerData();
    } catch (error) {
      toast.error('Failed to generate suggestions');
    }
  };

  const checkPermission = async (permission) => {
    try {
      const response = await axios.post('/permissions/check', null, {
        params: { permission }
      });
      return response.data.has_permission;
    } catch (error) {
      return false;
    }
  };

  const loadReports = async () => {
    try {
      console.log('📊 Loading reports...');
      const today = new Date().toISOString().split('T')[0];
      const monthStart = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0];
      const monthEnd = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).toISOString().split('T')[0];
      
      // Use .catch() on each request so one failure doesn't break all reports
      const [occupancyRes, revenueRes, dailyRes, forecastRes, forecast30Res, dailyFlashRes, marketSegmentRes, companyAgingRes, hkEfficiencyRes] = await Promise.all([
        axios.get(`/reports/occupancy?start_date=${monthStart}&end_date=${monthEnd}`).catch(e => { console.error('Occupancy report failed:', e); return { data: null }; }),
        axios.get(`/reports/revenue?start_date=${monthStart}&end_date=${monthEnd}`).catch(e => { console.error('Revenue report failed:', e); return { data: null }; }),
        axios.get('/reports/daily-summary').catch(e => { console.error('Daily summary failed:', e); return { data: null }; }),
        axios.get('/reports/forecast?days=7').catch(e => { console.error('Forecast failed:', e); return { data: null }; }),
        axios.get('/reports/forecast?days=30').catch(e => { console.error('30-day forecast failed:', e); return { data: null }; }),
        axios.get('/reports/daily-flash').catch(e => { console.error('Daily flash failed:', e); return { data: null }; }),
        axios.get(`/reports/market-segment?start_date=${monthStart}&end_date=${monthEnd}`).catch(e => { console.error('Market segment failed:', e); return { data: null }; }),
        axios.get('/reports/company-aging').catch(e => { console.error('Company aging failed:', e); return { data: null }; }),
        axios.get(`/reports/housekeeping-efficiency?start_date=${monthStart}&end_date=${monthEnd}`).catch(e => { console.error('HK efficiency failed:', e); return { data: null }; })
      ]);
      
      console.log('✅ Reports loaded:', { 
        occupancy: !!occupancyRes.data, 
        revenue: !!revenueRes.data, 
        daily: !!dailyRes.data 
      });
      
      setReports({
        occupancy: occupancyRes.data,
        revenue: revenueRes.data,
        daily: dailyRes.data,
        forecast: forecastRes.data,
        forecast30: forecast30Res.data,
        dailyFlash: dailyFlashRes.data,
        marketSegment: marketSegmentRes.data,
        companyAging: companyAgingRes.data,
        hkEfficiency: hkEfficiencyRes.data
      });
    } catch (error) {
      console.error('❌ Reports loading error:', error);
      toast.error('Failed to load some reports');
    }
  };

  const handleCheckIn = async (bookingId, forceClean = false) => {
    try {
      const params = new URLSearchParams({ create_folio: 'true' });
      if (forceClean) params.append('force_clean', 'true');
      const response = await axios.post(`/frontdesk/checkin/${bookingId}?${params}`);
      toast.success(`${response.data.message} - Oda ${response.data.room_number}`);
      loadData();
      loadFrontDeskData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Check-in failed');
    }
  };

  const handleCheckOut = async (bookingId) => {
    try {
      const response = await axios.post(`/frontdesk/checkout/${bookingId}?auto_close_folios=true`);
      if (response.data.total_balance > 0.01) {
        toast.warning(`⚠️ Check-out with outstanding balance: $${response.data.total_balance.toFixed(2)}`);
      } else {
        toast.success(`✅ ${response.data.message} - ${response.data.folios_closed} folios closed`);
      }
      loadData();
      loadFrontDeskData();
      loadHousekeepingData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Check-out failed');
    }
  };

  const loadFolio = async (bookingId) => {
    try {
      const response = await axios.get(`/frontdesk/folio/${bookingId}`);
      setFolio(response.data);
      setSelectedBooking(bookingId);
      setOpenDialog('folio');
    } catch (error) {
      toast.error('Failed to load folio');
    }
  };

  const handleAddCharge = async (e) => {
    e.preventDefault();
    try {
      await axios.post(
        `/frontdesk/folio/${selectedBooking}/charge`,
        null,
        { params: newCharge }
      );
      toast.success('Charge added');
      loadFolio(selectedBooking);
      setNewCharge({ charge_type: 'food', description: '', amount: 0, quantity: 1 });
    } catch (error) {
      toast.error('Failed to add charge');
    }
  };

  const handleProcessPayment = async (e) => {
    e.preventDefault();
    try {
      await axios.post(
        `/frontdesk/payment/${selectedBooking}`,
        null,
        { params: newPayment }
      );
      toast.success('Payment processed');
      loadFolio(selectedBooking);
      setNewPayment({ amount: 0, method: 'card', reference: '', notes: '' });
    } catch (error) {
      toast.error('Failed to process payment');
    }
  };

  const handleCreateHKTask = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/housekeeping/tasks', null, { params: newHKTask });
      toast.success('Task created');
      setOpenDialog(null);
      loadHousekeepingData();
      setNewHKTask({ room_id: '', task_type: 'cleaning', priority: 'normal', notes: '' });
    } catch (error) {
      toast.error('Failed to create task');
    }
  };

  const handleUpdateHKTask = async (taskId, status) => {
    try {
      await axios.put(`/housekeeping/tasks/${taskId}`, null, { params: { status } });
      toast.success('Task updated');
      loadHousekeepingData();
      loadData();
    } catch (error) {
      toast.error('Failed to update task');
    }
  };

  const handleCreateRoom = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/pms/rooms', {
        ...newRoom,
        view: newRoom.view || null,
        bed_type: newRoom.bed_type || null,
      });
      toast.success('Room created');
      setOpenDialog(null);
      loadData();
      setNewRoom({
        room_number: '',
        room_type: 'standard',
        floor: 1,
        capacity: 2,
        base_price: 100,
        amenities: [],
        view: '',
        bed_type: ''
      });
    } catch (error) {
      toast.error('Failed to create room');
    }
  };

  const handleCreateGuest = async (e) => {
    e.preventDefault();
    try {
      await axios.post('/pms/guests', newGuest);
      toast.success('Guest created');
      setOpenDialog(null);
      loadData();
      setNewGuest({ name: '', email: '', phone: '', id_number: '', address: '' });
    } catch (error) {
      toast.error('Failed to create guest');
    }
  };

  const handleCreateCompany = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post('/companies', newCompany);
      toast.success('Company created successfully');
      setOpenDialog(null);
      loadData();
      // Auto-select the newly created company
      const company = response.data;
      handleCompanySelect(company.id);
      setNewCompany({
        name: '',
        corporate_code: '',
        tax_number: '',
        billing_address: '',
        contact_person: '',
        contact_email: '',
        contact_phone: '',
        contracted_rate: '',
        default_rate_type: '',
        default_market_segment: '',
        default_cancellation_policy: '',
        payment_terms: '',
        status: 'pending'
      });
    } catch (error) {
      toast.error('Failed to create company');
    }
  };

  const handleCompanySelect = (companyId) => {
    if (companyId === "none") {
      setSelectedCompany(null);
      setNewBooking({
        ...newBooking,
        company_id: null,
        contracted_rate: '',
        rate_type: '',
        market_segment: '',
        cancellation_policy: '',
        billing_address: '',
        billing_tax_number: '',
        billing_contact_person: ''
      });
      return;
    }
    
    const company = companies.find(c => c.id === companyId);
    if (company) {
      setSelectedCompany(company);
      setNewBooking({
        ...newBooking,
        company_id: companyId,
        contracted_rate: company.contracted_rate || '',
        rate_type: company.default_rate_type || '',
        market_segment: company.default_market_segment || '',
        cancellation_policy: company.default_cancellation_policy || '',
        billing_address: company.billing_address || '',
        billing_tax_number: company.tax_number || '',
        billing_contact_person: company.contact_person || ''
      });
    }
  };

  const handleContractedRateSelect = (contractedRate) => {
    // Auto-fill rate type and market segment based on contracted rate
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
    if (mapping) {
      setNewBooking({
        ...newBooking,
        contracted_rate: contractedRate,
        rate_type: mapping.rate_type,
        market_segment: mapping.market_segment,
        cancellation_policy: mapping.cancellation_policy
      });
    }
  };

  const handleChildrenChange = (count) => {
    const childrenCount = parseInt(count) || 0;
    const currentAges = newBooking.children_ages;
    
    // Adjust children_ages array based on new count
    let newAges = [...currentAges];
    if (childrenCount > currentAges.length) {
      // Add default ages for new children
      newAges = [...currentAges, ...Array(childrenCount - currentAges.length).fill(0)];
    } else {
      // Remove excess ages
      newAges = currentAges.slice(0, childrenCount);
    }
    
    setNewBooking({
      ...newBooking,
      children: childrenCount,
      children_ages: newAges,
      guests_count: newBooking.adults + childrenCount
    });
  };

  const handleChildAgeChange = (index, age) => {
    const newAges = [...newBooking.children_ages];
    newAges[index] = parseInt(age) || 0;
    setNewBooking({
      ...newBooking,
      children_ages: newAges
    });
  };

  const handleCreateBooking = async (e) => {
    e.preventDefault();

    // Rate override kontrolü (ana form)
    if (newBooking.base_rate > 0 && newBooking.base_rate !== newBooking.total_amount) {
      if (!newBooking.override_reason) {
        toast.error('Please provide a reason for rate override');
        return;
      }
    }

    if (!newBooking.guest_id) {
      toast.error('Please select guest');
      return;
    }

    if (!newBooking.check_in || !newBooking.check_out) {
      toast.error('Please select check-in and check-out dates');
      return;
    }

    // Load rate data for this booking window
    await loadRateData(newBooking.channel, newBooking.company_id, newBooking.check_in);

    // Multi-room validasyonu
    if (!multiRoomBooking || multiRoomBooking.length === 0) {
      toast.error('Please add at least one room');
      return;
    }

    const invalidRoom = multiRoomBooking.find(r => !r.room_id);
    if (invalidRoom) {
      toast.error('Please select room for each line');
      return;
    }

    try {
      const roomsPayload = multiRoomBooking.map(room => ({
        room_id: room.room_id,
        adults: room.adults,
        children: room.children,
        children_ages: room.children_ages || [],
        total_amount: room.total_amount,
        base_rate: room.base_rate,
        rate_plan: room.rate_plan || newBooking.rate_type || 'Standard',
        package_code: room.package_code || null
      }));

      const payload = {
        guest_id: newBooking.guest_id,
        arrival_date: newBooking.check_in,
        departure_date: newBooking.check_out,
        rooms: roomsPayload,
        company_id: newBooking.company_id || null,
        channel: newBooking.channel || 'direct',
        special_requests: undefined
      };

      await axios.post('/pms/bookings/multi-room', payload);
      toast.success('Booking created successfully');
      setOpenDialog(null);
      loadData();
      setSelectedCompany(null);
      setNewBooking({
        guest_id: '',
        room_id: '',
        check_in: '',
        check_out: '',
        adults: 1,
        children: 0,
        children_ages: [],
        guests_count: 1,
        total_amount: 0,
        base_rate: 0,
        channel: 'direct',
        company_id: '',
        contracted_rate: '',
        rate_type: '',
        market_segment: '',
        cancellation_policy: '',
        billing_address: '',
        billing_tax_number: '',
        billing_contact_person: '',
        override_reason: ''
      });
      setMultiRoomBooking([
        {
          room_id: '',
          adults: 1,
          children: 0,
          children_ages: [],
          total_amount: 0,
          base_rate: 0,
          rate_plan: '',
          package_code: null
        }
      ]);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create booking');
    }
  };

  // Folio Management Functions
  const loadBookingFolios = async (bookingId) => {
    try {
      const response = await axios.get(`/folio/booking/${bookingId}`);
      setFolios(response.data);
      setSelectedBooking(bookingId);
      setOpenDialog('folio-view');
      
      // Auto-select guest folio if exists
      const guestFolio = response.data.find(f => f.folio_type === 'guest');
      if (guestFolio) {
        loadFolioDetails(guestFolio.id);
      }
    } catch (error) {
      toast.error('Failed to load folios');
    }
  };

  const loadFolioDetails = async (folioId) => {
    try {
      const response = await axios.get(`/folio/${folioId}`);
      setSelectedFolio(response.data.folio);
      setFolioCharges(response.data.charges || []);
      setFolioPayments(response.data.payments || []);
    } catch (error) {
      toast.error('Failed to load folio details');
    }
  };

  const handlePostCharge = async (e) => {
    e.preventDefault();
    if (!selectedFolio) return;
    
    try {
      await axios.post(`/folio/${selectedFolio.id}/charge`, newFolioCharge);
      toast.success('Charge posted successfully');
      loadFolioDetails(selectedFolio.id);
      setNewFolioCharge({
        charge_category: 'room',
        description: '',
        amount: 0,
        quantity: 1,
        auto_calculate_tax: false
      });
      setOpenDialog('folio-view');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to post charge');
    }
  };

  const handlePostPayment = async (e) => {
    e.preventDefault();
    if (!selectedFolio) return;
    
    try {
      await axios.post(`/folio/${selectedFolio.id}/payment`, newFolioPayment);
      toast.success('Payment posted successfully');
      loadFolioDetails(selectedFolio.id);
      setNewFolioPayment({
        amount: 0,
        method: 'card',
        payment_type: 'interim',
        reference: '',
        notes: ''
      });
      setOpenDialog('folio-view');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to post payment');
    }
  };

  const updateRoomStatus = async (roomId, newStatus) => {
    try {
      await axios.put(`/pms/rooms/${roomId}`, { status: newStatus });
      toast.success('Room status updated');
      loadData();
      loadHousekeepingData();
    } catch (error) {
      toast.error('Failed to update status');
    }
  };

  const quickUpdateRoomStatus = async (roomId, newStatus) => {
    try {
      const response = await axios.put(`/housekeeping/room/${roomId}/status?new_status=${newStatus}`);
      toast.success(response.data.message);
      loadHousekeepingData();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update status');
    }
  };

  const createRoomBlock = async () => {
    if (!selectedRoom) {
      toast.error('Please select a room');
      return;
    }
    if (!newRoomBlock.reason || !newRoomBlock.start_date) {
      toast.error('Please fill in all required fields');
      return;
    }
    
    try {
      const idempotencyKey = window.crypto?.randomUUID?.() || `room-block-create-${Date.now()}-${Math.random()}`;
      const response = await axios.post('/pms/room-blocks', {
        room_id: selectedRoom.id,
        ...newRoomBlock
      }, {
        headers: {
          'Idempotency-Key': idempotencyKey
        }
      });
      
      if (response.data.warnings && response.data.warnings.length > 0) {
        response.data.warnings.forEach(warning => {
          toast.warning(warning.message);
        });
      }
      
      toast.success(response.data.message);
      setOpenDialog(null);
      setSelectedRoom(null);
      setNewRoomBlock({
        type: 'out_of_order',
        reason: '',
        details: '',
        start_date: '',
        end_date: '',
        allow_sell: false
      });
      loadHousekeepingData();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create room block');
    }
  };

  const cancelRoomBlock = async (blockId) => {
    try {
      const idempotencyKey = window.crypto?.randomUUID?.() || `room-block-release-${Date.now()}-${Math.random()}`;
      await axios.post(`/pms/room-blocks/${blockId}/cancel`, null, {
        headers: {
          'Idempotency-Key': idempotencyKey
        }
      });
      toast.success('Room block cancelled');
      loadHousekeepingData();
      loadData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to cancel block');
    }
  };

  // Phase H - Load Guest 360° Profile
  const loadGuest360 = async (guestId) => {
    setLoadingGuest360(true);
    try {
      const response = await axios.get(`/crm/guest/${guestId}`, { timeout: 15000 });
      setGuest360Data(response.data);
      setOpenDialog('guest360');
    } catch (error) {
      console.error('Guest 360 error:', error);
      if (error.code === 'ECONNABORTED') {
        toast.error('Request timeout - Guest profile has too much data. Please try again.');
      } else {
        toast.error(error.response?.data?.detail || 'Failed to load guest profile. Please try again later.');
      }
    } finally {
      setLoadingGuest360(false);
    }
  };

  const addGuestTag = async () => {
    if (!guestTag || !selectedGuest360) return;
    try {
      await axios.post(`/crm/guest/add-tag?guest_id=${selectedGuest360}&tag=${guestTag}`);
      toast.success('Tag added');
      setGuestTag('');
      loadGuest360(selectedGuest360);
    } catch (error) {
      toast.error('Failed to add tag');
    }
  };

  const addGuestNote = async () => {
    if (!guestNote || !selectedGuest360) return;
    try {
      await axios.post(`/crm/guest/note?guest_id=${selectedGuest360}&note=${guestNote}`);
      toast.success('Note added');
      setGuestNote('');
      loadGuest360(selectedGuest360);
    } catch (error) {
      toast.error('Failed to add note');
    }
  };

  const generateUpsellOffers = async (bookingId) => {
    try {
      const response = await axios.post(`/ai/upsell/generate?booking_id=${bookingId}`, {}, { timeout: 10000 });
      toast.success(`Generated ${response.data.total_offers} upsell offers`);
      setUpsellOffers(response.data.offers);
    } catch (error) {
      console.error('Upsell generation error:', error);
      if (error.response?.status === 503) {
        toast.error('AI service is temporarily unavailable. Using default offers.');
      } else if (error.response?.status === 404) {
        toast.error('Booking not found or no available upsell options.');
      } else {
        toast.error(error.response?.data?.detail || 'Failed to generate upsell offers. Please try again.');
      }
    }
  };

  const loadMessageTemplates = async () => {
    try {
      const response = await axios.get('/messages/templates');
      setMessageTemplates(response.data.templates || []);
    } catch (error) {
      console.error('Failed to load templates');
    }
  };

  const sendMessage = async () => {
    if (!newMessage.recipient || !newMessage.body) {
      toast.error('Please fill in all fields');
      return;
    }

    try {
      let response;
      if (newMessage.channel === 'email') {
        response = await axios.post('/messages/send-email', {
          recipient: newMessage.recipient,
          subject: newMessage.subject,
          body: newMessage.body
        });
      } else if (newMessage.channel === 'sms') {
        response = await axios.post('/messages/send-sms', {
          recipient: newMessage.recipient,
          body: newMessage.body
        });
      } else if (newMessage.channel === 'whatsapp') {
        response = await axios.post('/messages/send-whatsapp', {
          recipient: newMessage.recipient,
          body: newMessage.body
        });
      }

      toast.success('Message sent successfully!');
      setSentMessages([response.data, ...sentMessages]);
      setNewMessage({
        channel: 'email',
        recipient: '',
        subject: '',
        body: '',
        template_id: null
      });
    } catch (error) {
      console.error('Message send error:', error);
      if (error.response?.status === 503) {
        toast.error(`${newMessage.channel.toUpperCase()} service is not configured. Please configure API credentials in Settings.`);
      } else if (error.response?.status === 401) {
        toast.error('Authentication failed. Please check your API credentials.');
      } else {
        toast.error(error.response?.data?.detail || `Failed to send ${newMessage.channel} message. Please check your configuration.`);
      }
    }
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
              console.log('Search result selected:', result);
              toast.success(`Selected ${result.type}: ${result.data.name || result.data.room_number || result.data.id}`);
            }} />
          </div>
        </div>


        {/* Quick Actions Toolbar */}
        <Card className="border-blue-200 bg-gradient-to-r from-blue-50 to-purple-50">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="text-sm font-semibold text-gray-700">Quick Actions:</div>
              </div>
              <div className="flex gap-2">
                <Button 
                  size="sm" 
                  variant="outline"
                  onClick={() => {
                    setOpenDialog('booking');
                    toast.info('Opening new booking form...');
                  }}
                >
                  <Plus className="w-4 h-4 mr-2" />
                  New Booking
                </Button>
                <Button 
                  size="sm" 
                  variant="outline"
                  onClick={() => {
                    setOpenDialog('guest');
                  }}
                >
                  <UserPlus className="w-4 h-4 mr-2" />
                  New Guest
                </Button>
                <Button 
                  size="sm" 
                  variant="outline"
                  onClick={async () => {
                    try {
                      const response = await axios.get('/reports/daily-flash');
                      if (response.data) {
                        toast.success('Flash report generated!');
                        console.log('Flash report:', response.data);
                        setActiveTab('reports');
                      } else {
                        toast.info('No flash report data available');
                      }
                    } catch (error) {
                      toast.error('Failed to generate report');
                    }
                  }}
                >
                  <FileText className="w-4 h-4 mr-2" />
                  Flash Report
                </Button>
                <Button 
                  size="sm" 
                  variant="outline"
                  onClick={() => loadData()}
                >
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Refresh
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>


        <Tabs
          value={activeTab}
          className="w-full"
          onValueChange={(v) => {
            // Sekme değeri hemen değişsin (UI anında tepki versin)
            setActiveTab(v);
            window.location.hash = v;
          }}
        >
          <TabsList className="grid w-full grid-cols-12 gap-1">
            {visibleTabs.map((tab) => {
              const Icon = tab.icon;
              const label = tab.labelKey ? t(tab.labelKey) : tab.labelText;
              return (
                <TabsTrigger key={tab.key} value={tab.key} data-testid={tab.testId}>
                  {Icon ? <Icon className="w-4 h-4 mr-2" /> : null}
                  {label}
                </TabsTrigger>
              );
            })}
          </TabsList>

          {/* FRONT DESK TAB */}
          <FrontdeskTab
            t={t}
            arrivals={arrivals}
            departures={departures}
            inhouse={inhouse}
            aiPrediction={aiPrediction}
            aiPatterns={aiPatterns}
            handleCheckIn={handleCheckIn}
            handleCheckOut={handleCheckOut}
            loadFolio={loadFolio}
            loadFrontDeskData={loadFrontDeskData}
          />

          {/* HOUSEKEEPING TAB */}
          <HousekeepingTab
            roomBlocks={roomBlocks}
            roomStatusBoard={roomStatusBoard}
            dueOutRooms={dueOutRooms}
            stayoverRooms={stayoverRooms}
            arrivalRooms={arrivalRooms}
            housekeepingTasks={housekeepingTasks}
            quickUpdateRoomStatus={quickUpdateRoomStatus}
            setOpenDialog={setOpenDialog}
            setSelectedRoom={setSelectedRoom}
            setNewBooking={setNewBooking}
            setMaintenanceForm={setMaintenanceForm}
            setMaintenanceDialogOpen={setMaintenanceDialogOpen}
            handleUpdateHKTask={handleUpdateHKTask}
            toast={toast}
          />

          {/* ROOMS TAB */}
          <TabsContent value="rooms" className="space-y-4">
            <RoomsTab
              rooms={rooms}
              bookings={bookings}
              guests={guests}
              handleCheckIn={handleCheckIn}
              handleCheckOut={handleCheckOut}
              onPayment={(bookingId) => {
                setSelectedBookingDetail(bookings.find(b => b.id === bookingId) || null);
                setOpenDialog('bookingDetail');
              }}
              onGuestClick={(guestId) => {
                const guest = guests.find(g => g.id === guestId);
                if (guest) {
                  setSelectedGuest(guest);
                  setOpenDialog('guestInfo');
                }
              }}
              onBookingDoubleClick={(booking) => {
                setReservationDetailId(booking.id);
              }}
              onDataRefresh={loadData}
            />
          </TabsContent>

          {/* GUESTS TAB */}
          <GuestsTab
            guests={guests}
            setOpenDialog={setOpenDialog}
            setSelectedGuest360={setSelectedGuest360}
            loadGuest360={loadGuest360}
            setNewBooking={setNewBooking}
            t={t}
          />

          {/* BOOKINGS TAB */}
          <BookingsTab
            bookingStats={bookingStats}
            bookings={bookings}
            groupedBookings={groupedBookings}
            guests={guests}
            rooms={rooms}
            companies={companies}
            handleCheckIn={handleCheckIn}
            handleCheckOut={handleCheckOut}
            loadBookingFolios={loadBookingFolios}
            generateUpsellOffers={generateUpsellOffers}
            loadGuest360={loadGuest360}
            setSelectedGuest360={setSelectedGuest360}
            setOpenDialog={setOpenDialog}
            setSelectedBooking={setSelectedBooking}
            setSelectedBookingDetail={setSelectedBookingDetail}
            toast={toast}
            isLite={isLite}
            roomsCount={roomsCount}
            activeTab={activeTab}
          />

          {/* UPSELL TAB */}
          <TabsContent value="upsell" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">🤖 AI Upsell & Revenue Optimization</h2>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TrendingUp className="w-5 h-5" />
                    Upsell Opportunities
                  </CardTitle>
                  <CardDescription>AI-generated upsell suggestions for current bookings</CardDescription>
                </CardHeader>
                <CardContent>
                  {upsellOffers.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <TrendingUp className="w-12 h-12 mx-auto mb-4 opacity-50" />
                      <p>No upsell offers generated yet</p>
                      <p className="text-sm">Select a booking to generate AI-powered upsell suggestions</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {upsellOffers.map((offer, index) => (
                        <div key={index} className="border rounded-lg p-4 space-y-2">
                          <div className="flex justify-between items-start">
                            <div>
                              <h4 className="font-semibold">{offer.title}</h4>
                              <p className="text-sm text-gray-600">{offer.description}</p>
                            </div>
                            <Badge variant="secondary">${offer.additional_revenue}</Badge>
                          </div>
                          <div className="flex justify-between items-center pt-2">
                            <span className="text-xs text-gray-500">Confidence: {offer.confidence}%</span>
                            <Button size="sm" variant="outline">
                              Apply Offer
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="w-5 h-5" />
                    Revenue Insights
                  </CardTitle>
                  <CardDescription>AI-powered revenue optimization suggestions</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                        <span className="font-semibold text-green-800">Revenue Opportunity</span>
                      </div>
                      <p className="text-sm text-green-700">
                        Increase ADR by 12% through strategic room upgrades and package offerings
                      </p>
                    </div>
                    
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                        <span className="font-semibold text-blue-800">Occupancy Optimization</span>
                      </div>
                      <p className="text-sm text-blue-700">
                        Target corporate segment for weekday bookings to improve occupancy by 8%
                      </p>
                    </div>
                    
                    <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-2 h-2 bg-purple-500 rounded-full"></div>
                        <span className="font-semibold text-purple-800">Guest Satisfaction</span>
                      </div>
                      <p className="text-sm text-purple-700">
                        Personalized amenity packages can increase guest satisfaction by 15%
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* MESSAGING TAB */}
          <TabsContent value="messaging" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">💬 Guest Communication</h2>
              <Button onClick={loadMessageTemplates}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Load Templates
              </Button>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Send Message */}
              <Card>
                <CardHeader>
                  <CardTitle>Send Message</CardTitle>
                  <CardDescription>Send email, SMS, or WhatsApp messages to guests</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label>Channel</Label>
                    <Select
                      value={newMessage.channel}
                      onValueChange={(v) => setNewMessage(prev => ({...prev, channel: v}))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="email">📧 Email</SelectItem>
                        <SelectItem value="sms">📱 SMS</SelectItem>
                        <SelectItem value="whatsapp">💬 WhatsApp</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div>
                    <Label>Recipient</Label>
                    <Input
                      placeholder={newMessage.channel === 'email' ? 'guest@example.com' : '+1234567890'}
                      value={newMessage.recipient}
                      onChange={(e) => setNewMessage(prev => ({...prev, recipient: e.target.value}))}
                    />
                  </div>
                  
                  {newMessage.channel === 'email' && (
                    <div>
                      <Label>Subject</Label>
                      <Input
                        placeholder="Message subject"
                        value={newMessage.subject}
                        onChange={(e) => setNewMessage(prev => ({...prev, subject: e.target.value}))}
                      />
                    </div>
                  )}
                  
                  <div>
                    <Label>Message</Label>
                    <Textarea
                      placeholder="Type your message here..."
                      value={newMessage.body}
                      onChange={(e) => setNewMessage(prev => ({...prev, body: e.target.value}))}
                      rows={4}
                    />
                  </div>
                  
                  <Button onClick={sendMessage} className="w-full">
                    <Send className="w-4 h-4 mr-2" />
                    Send {newMessage.channel.toUpperCase()}
                  </Button>
                </CardContent>
              </Card>

              {/* Message Templates */}
              <Card>
                <CardHeader>
                  <CardTitle>Message Templates</CardTitle>
                  <CardDescription>Pre-defined message templates for common scenarios</CardDescription>
                </CardHeader>
                <CardContent>
                  {messageTemplates.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">
                      <MessageSquare className="w-12 h-12 mx-auto mb-4 opacity-50" />
                      <p>No templates available</p>
                      <p className="text-sm">Click &quot;Load Templates&quot; to fetch available templates</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {messageTemplates.map((template) => (
                        <div key={template.id} className="border rounded-lg p-3">
                          <div className="flex justify-between items-start mb-2">
                            <h4 className="font-semibold text-sm">{template.name}</h4>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setNewMessage(prev => ({
                                  ...prev,
                                  subject: template.subject || prev.subject,
                                  body: template.body,
                                  template_id: template.id
                                }));
                              }}
                            >
                              Use
                            </Button>
                          </div>
                          <p className="text-xs text-gray-600">{template.description}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Sent Messages */}
            {sentMessages.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Recent Messages</CardTitle>
                  <CardDescription>Recently sent messages</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {sentMessages.slice(0, 5).map((message, index) => (
                      <div key={index} className="border-l-4 border-blue-500 pl-4 py-2">
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="font-semibold text-sm">{message.channel.toUpperCase()} to {message.recipient}</div>
                            <div className="text-xs text-gray-600">{message.subject}</div>
                          </div>
                          <Badge variant="secondary">{message.status}</Badge>
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {new Date(message.sent_at).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* REPORTS TAB */}
          <TabsContent value="reports" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">Reports & Analytics</h2>
              <Button onClick={loadReports}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh Reports
              </Button>
            </div>

            {/* Key Metrics Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Occupancy Rate</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {reports.occupancy ? `${(reports.occupancy.current_occupancy_rate ?? reports.occupancy.occupancy_rate ?? 0).toFixed(1)}%` : 'Loading...'}
                  </div>
                  <p className="text-xs text-gray-600">
                    {reports.occupancy ? `${reports.occupancy.occupied_rooms ?? reports.occupancy.occupied_room_nights ?? 0}/${reports.occupancy.total_rooms} rooms` : ''}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">ADR</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {reports.revenue ? `$${(reports.revenue.adr ?? 0).toFixed(2)}` : 'Loading...'}
                  </div>
                  <p className="text-xs text-gray-600">Average Daily Rate</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">RevPAR</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {reports.revenue ? `$${(reports.revenue.revpar ?? reports.revenue.rev_par ?? 0).toFixed(2)}` : 'Loading...'}
                  </div>
                  <p className="text-xs text-gray-600">Revenue Per Available Room</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Total Revenue</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {reports.revenue ? `$${(reports.revenue.total_revenue ?? 0).toLocaleString()}` : 'Loading...'}
                  </div>
                  <p className="text-xs text-gray-600">This Month</p>
                </CardContent>
              </Card>
            </div>

            {/* Charts and Detailed Reports */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Occupancy Chart */}
              <Card>
                <CardHeader>
                  <CardTitle>Occupancy Trend</CardTitle>
                  <CardDescription>Daily occupancy for the current month</CardDescription>
                </CardHeader>
                <CardContent>
                  {reports.occupancy && reports.occupancy.daily_data ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <PickupPaceChart data={reports.occupancy.daily_data} />
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[300px] flex items-center justify-center text-gray-500">
                      <RefreshCw className="w-8 h-8 animate-spin mr-2" />
                      Loading chart data...
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Revenue Breakdown */}
              <Card>
                <CardHeader>
                  <CardTitle>Revenue Breakdown</CardTitle>
                  <CardDescription>Revenue by source</CardDescription>
                </CardHeader>
                <CardContent>
                  {reports.revenue && reports.revenue.breakdown ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={reports.revenue.breakdown}
                          dataKey="amount"
                          nameKey="source"
                          cx="50%"
                          cy="50%"
                          outerRadius={100}
                          fill="#8884d8"
                        >
                          {reports.revenue.breakdown.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={['#0088FE', '#00C49F', '#FFBB28', '#FF8042'][index % 4]} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-[300px] flex items-center justify-center text-gray-500">
                      <RefreshCw className="w-8 h-8 animate-spin mr-2" />
                      Loading chart data...
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Forecast */}
            {reports.forecast && (
              <Card>
                <CardHeader>
                  <CardTitle>7-Day Forecast</CardTitle>
                  <CardDescription>Predicted occupancy and revenue</CardDescription>
                </CardHeader>
                <CardContent>
                  <ForecastGraph data={reports.forecast} />
                </CardContent>
              </Card>
            )}

            {/* Daily Flash Report */}
            {reports.dailyFlash && (
              <Card>
                <CardHeader>
                  <CardTitle>Daily Flash Report</CardTitle>
                  <CardDescription>Today&apos;s key metrics and performance</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-600">{reports.dailyFlash.arrivals}</div>
                      <div className="text-sm text-gray-600">Arrivals</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-600">{reports.dailyFlash.departures}</div>
                      <div className="text-sm text-gray-600">Departures</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-purple-600">{reports.dailyFlash.inhouse}</div>
                      <div className="text-sm text-gray-600">In-House</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-orange-600">
                      {reports.dailyFlash?.revenue
                        ? `$${(reports.dailyFlash.revenue.total_revenue ?? 0).toFixed(2)}`
                        : 'Loading...'}
                    </div>
                      <div className="text-sm text-gray-600">Revenue</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* TASKS TAB */}
          <TabsContent value="tasks" className="space-y-4">
            <StaffTaskManager />
          </TabsContent>

          {/* FEEDBACK TAB */}
          <TabsContent value="feedback" className="space-y-4">
            <FeedbackSystem />
          </TabsContent>

          {/* ALLOTMENT TAB */}
          <TabsContent value="allotment" className="space-y-4">
            <AllotmentGrid />
          </TabsContent>

          {/* POS TAB */}
          <TabsContent value="pos" className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-semibold">🍽️ Point of Sale Integration</h2>
              <Button onClick={async () => {
                try {
                  const response = await axios.get('/pos/orders/today');
                  setPosOrders(response.data.orders || []);
                  setPosRevenue(response.data.revenue || { restaurant: 0, bar: 0, room_service: 0, total: 0 });
                  toast.success('POS data refreshed');
                } catch (error) {
                  toast.error('Failed to load POS data');
                }
              }}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh POS Data
              </Button>
            </div>

            {/* POS Revenue Summary */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Restaurant</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">${posRevenue.restaurant}</div>
                  <p className="text-xs text-gray-600">Today&apos;s Revenue</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Bar</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">${posRevenue.bar}</div>
                  <p className="text-xs text-gray-600">Today&apos;s Revenue</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Room Service</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">${posRevenue.room_service}</div>
                  <p className="text-xs text-gray-600">Today&apos;s Revenue</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">Total F&B</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">${posRevenue.total}</div>
                  <p className="text-xs text-gray-600">Today&apos;s Total</p>
                </CardContent>
              </Card>
            </div>

            {/* Recent POS Orders */}
            <Card>
              <CardHeader>
                <CardTitle>Recent Orders</CardTitle>
                <CardDescription>Latest POS transactions</CardDescription>
              </CardHeader>
              <CardContent>
                {posOrders.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <div className="text-4xl mb-4">🍽️</div>
                    <p>No recent orders</p>
                    <p className="text-sm">POS orders will appear here when available</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {posOrders.slice(0, 10).map((order) => (
                      <div key={order.id} className="flex justify-between items-center p-3 border rounded-lg">
                        <div>
                          <div className="font-semibold">Order #{order.id}</div>
                          <div className="text-sm text-gray-600">
                            {order.outlet} • Room {order.room_number || 'N/A'}
                          </div>
                          <div className="text-xs text-gray-500">
                            {new Date(order.created_at).toLocaleString()}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-bold">${order.total}</div>
                          <Badge variant={order.status === 'completed' ? 'default' : 'secondary'}>
                            {order.status}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Dialogs and Modals */}
        <Dialog open={openDialog === 'folio'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Guest Folio</DialogTitle>
            </DialogHeader>
            {folio && (
              <div className="space-y-6">
                {/* Charges */}
                <div>
                  <h3 className="font-semibold mb-2">Charges</h3>
                  <div className="space-y-2">
                    {folio.charges.map((charge, idx) => (
                      <div key={idx} className="flex justify-between text-sm border-b pb-2">
                        <div>
                          <div className="font-medium">{charge.description}</div>
                          <div className="text-xs text-gray-500 capitalize">{charge.charge_type}</div>
                        </div>
                        <div className="text-right">
                          <div>${charge.total.toFixed(2)}</div>
                          <div className="text-xs text-gray-500">{charge.quantity} × ${charge.amount}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  
                  {/* Add Charge Form */}
                  <form onSubmit={handleAddCharge} className="mt-4 p-4 bg-gray-50 rounded">
                    <div className="grid grid-cols-2 gap-4">
                      <Select value={newCharge.charge_type} onValueChange={(v) => setNewCharge({...newCharge, charge_type: v})}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="food">Food & Beverage</SelectItem>
                          <SelectItem value="laundry">Laundry</SelectItem>
                          <SelectItem value="minibar">Minibar</SelectItem>
                          <SelectItem value="spa">Spa</SelectItem>
                          <SelectItem value="phone">Phone</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        placeholder={t("common.description")}
                        value={newCharge.description}
                        onChange={(e) => setNewCharge({...newCharge, description: e.target.value})}
                        required
                      />
                      <Input
                        type="number"
                        step="0.01"
                        placeholder="Amount"
                        value={newCharge.amount}
                        onChange={(e) => setNewCharge({...newCharge, amount: parseFloat(e.target.value)})}
                        required
                      />
                      <Button type="submit">Add Charge</Button>
                    </div>
                  </form>
                </div>

                {/* Payments */}
                <div>
                  <h3 className="font-semibold mb-2">Payments</h3>
                  <div className="space-y-2">
                    {folio.payments.map((payment, idx) => (
                      <div key={idx} className="flex justify-between text-sm border-b pb-2">
                        <div>
                          <div className="font-medium capitalize">{payment.method}</div>
                          {payment.reference && <div className="text-xs text-gray-500">Ref: {payment.reference}</div>}
                        </div>
                        <div className="text-green-600 font-medium">${payment.amount.toFixed(2)}</div>
                      </div>
                    ))}
                  </div>
                  
                  {/* Add Payment Form */}
                  <form onSubmit={handleProcessPayment} className="mt-4 p-4 bg-gray-50 rounded">
                    <div className="grid grid-cols-2 gap-4">
                      <Input
                        type="number"
                        step="0.01"
                        placeholder="Amount"
                        value={newPayment.amount}
                        onChange={(e) => setNewPayment({...newPayment, amount: parseFloat(e.target.value)})}
                        required
                      />
                      <Select value={newPayment.method} onValueChange={(v) => setNewPayment({...newPayment, method: v})}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="cash">Cash</SelectItem>
                          <SelectItem value="card">Card</SelectItem>
                          <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                          <SelectItem value="online">Online</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        placeholder="Reference (optional)"
                        value={newPayment.reference}
                        onChange={(e) => setNewPayment({...newPayment, reference: e.target.value})}
                      />
                      <Button type="submit">Process Payment</Button>
                    </div>
                  </form>
                </div>

                {/* Summary */}
                <div className="border-t pt-4">
                  <div className="flex justify-between text-lg font-bold">
                    <span>Total Charges:</span>
                    <span>${folio.total_charges.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-lg font-bold text-green-600">
                    <span>Total Paid:</span>
                    <span>${folio.total_paid.toFixed(2)}</span>
                  </div>
                  <div className={`flex justify-between text-2xl font-bold ${folio.balance > 0 ? 'text-red-600' : 'text-gray-600'}`}>
                    <span>Balance:</span>
                    <span>${folio.balance.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Room Dialog */}
        <Dialog open={openDialog === 'room'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Room</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateRoom} className="space-y-4">
              <div>
                <Label>Room Number</Label>
                <Input value={newRoom.room_number} onChange={(e) => setNewRoom({...newRoom, room_number: e.target.value})} required />
              </div>
              <div>
                <Label>Room Type</Label>
                <Select value={newRoom.room_type} onValueChange={(v) => setNewRoom({...newRoom, room_type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="standard">Standard</SelectItem>
                    <SelectItem value="deluxe">Deluxe</SelectItem>
                    <SelectItem value="suite">Suite</SelectItem>
                    <SelectItem value="presidential">Presidential</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Floor</Label>
                  <Input type="number" value={newRoom.floor} onChange={(e) => setNewRoom({...newRoom, floor: parseInt(e.target.value)})} required />
                </div>
                <div>
                  <Label>Capacity</Label>
                  <Input type="number" value={newRoom.capacity} onChange={(e) => setNewRoom({...newRoom, capacity: parseInt(e.target.value)})} required />
                </div>
              </div>
              <div>
                <Label>Base Price</Label>
                <Input type="number" step="0.01" value={newRoom.base_price} onChange={(e) => setNewRoom({...newRoom, base_price: parseFloat(e.target.value)})} required />
              </div>
              <Button type="submit" className="w-full">Create Room</Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* Room Images Dialog */}
        <Dialog open={openDialog === 'room-images'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-4xl">
            <DialogHeader>
              <DialogTitle>Oda Fotoğrafları {selectedRoom ? `- ${selectedRoom.room_number}` : ''}</DialogTitle>
              <DialogDescription>
                Bu özellik preview ortamında sunucu diskine yükler. Canlıda dosya kalıcılığı için daha sonra S3/Cloudinary önerilir.
              </DialogDescription>
            </DialogHeader>

            {selectedRoom ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {(selectedRoom.images || []).length === 0 ? (
                    <div className="col-span-full text-sm text-gray-500">Henüz fotoğraf yüklenmemiş.</div>
                  ) : (
                    (selectedRoom.images || []).map((src) => (
                      <a key={src} href={src} target="_blank" rel="noreferrer" className="block">
                        <div className="h-32 rounded-lg overflow-hidden border bg-gray-50">
                          <img src={src} alt="room" className="w-full h-full object-cover" />
                        </div>
                      </a>
                    ))
                  )}
                </div>

                <div className="border-t pt-4">
                  <Label>Yeni Fotoğraf(lar) Yükle</Label>
                  <Input
                    type="file"
                    accept="image/*"
                    multiple
                    onChange={async (e) => {
                      try {
                        const files = Array.from(e.target.files || []);
                        if (files.length === 0) return;

                        const formData = new FormData();
                        files.forEach((f) => formData.append('files', f));

                        const res = await axios.post(`/pms/rooms/${selectedRoom.id}/images`, formData, {
                          headers: { 'Content-Type': 'multipart/form-data' },
                        });

                        toast.success(`${res.data.uploaded} fotoğraf yüklendi`);

                        // Refresh rooms, then refresh selectedRoom reference
                        await loadData();
                        // After loadData, close and re-open dialog to refresh selectedRoom from updated rooms list.
                        // (Rooms state updates async; we keep the dialog open and optimistically append returned images.)
                        setSelectedRoom(prev => prev ? ({ ...prev, images: res.data.images || prev.images }) : prev);
                      } catch (err) {
                        toast.error(err?.response?.data?.detail || 'Fotoğraf yüklenemedi');
                      } finally {
                        // clear input value
                        e.target.value = '';
                      }
                    }}
                  />
                  <p className="text-[11px] text-gray-500 mt-1">JPEG/PNG/WEBP önerilir. Max 10MB/dosya.</p>
                </div>

                <div className="flex justify-end">
                  <Button variant="outline" onClick={() => setOpenDialog(null)}>{t("common.close")}</Button>
                </div>
              </div>
            ) : (
              <div className="text-sm text-gray-500">Oda seçilmedi.</div>
            )}
          </DialogContent>
        </Dialog>


        {/* Bulk Delete Rooms Dialog */}
        <Dialog open={openDialog === 'bulk-delete-rooms'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Toplu Oda Silme</DialogTitle>
              <DialogDescription>
                Bu işlem geri alınamaz gibi düşünün (soft delete yapılır). Silmeyi onaylamak için aşağıya <span className="font-mono">DELETE</span> yazmalısınız.
                Aktif rezervasyonu olan odalar otomatik olarak bloklanır.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3">
              <div className="rounded-md border bg-gray-50 p-3 text-sm">
                <div className="font-semibold">Silinecek oda sayısı: {selectedRooms.length}</div>
                <div className="text-xs text-gray-600 mt-1">
                  Seçili odalardan ilk 5&apos;i: {rooms.filter(r => selectedRooms.includes(r.id)).slice(0,5).map(r => r.room_number).join(', ') || '-'}
                </div>
              </div>

              <div className="space-y-1">
                <Label>Onay</Label>
                <Input
                  value={bulkDeleteConfirm}
                  onChange={(e) => setBulkDeleteConfirm(e.target.value)}
                  placeholder="DELETE"
                />
                <p className="text-[11px] text-gray-500">Yanlışlıkla silmeyi önlemek için zorunludur.</p>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setOpenDialog(null)}>Vazgeç</Button>
                <Button
                  variant="destructive"
                  disabled={selectedRooms.length === 0 || bulkDeleteConfirm.trim().toUpperCase() !== 'DELETE'}
                  onClick={async () => {
                    try {
                      const res = await axios.post('/pms/rooms/bulk/delete', {
                        ids: selectedRooms,
                        confirm_text: bulkDeleteConfirm,
                      });

                      const msgParts = [`Deleted: ${res.data.deleted}`];
                      if (res.data.blocked > 0) msgParts.push(`Blocked: ${res.data.blocked}`);
                      toast.success(msgParts.join(' • '));

                      if (res.data.blocked > 0) {
                        toast.info(`Bloklanan odalar: ${(res.data.blocked_rooms || []).slice(0, 10).join(', ')}`);
                      }

                      setSelectedRooms([]);
                      setBulkRoomMode(false);
                      setOpenDialog(null);
                      await loadData();
                    } catch (err) {
                      toast.error(err?.response?.data?.detail || 'Toplu silme başarısız');
                    }
                  }}
                >
                  Sil
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>


        <BulkRoomsDialog
          open={openDialog === 'bulk-rooms'}
          onClose={() => setOpenDialog(null)}
          onRoomsCreated={loadData}
        />


        {/* Guest Dialog */}
        <Dialog open={openDialog === 'guest'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Register New Guest</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateGuest} className="space-y-4">
              <div>
                <Label>Name</Label>
                <Input value={newGuest.name} onChange={(e) => setNewGuest({...newGuest, name: e.target.value})} required />
              </div>
              <div>
                <Label>Email</Label>
                <Input type="email" value={newGuest.email} onChange={(e) => setNewGuest({...newGuest, email: e.target.value})} required />
              </div>
              <div>
                <Label>Phone</Label>
                <Input value={newGuest.phone} onChange={(e) => setNewGuest({...newGuest, phone: e.target.value})} required />
              </div>
              <div>
                <Label>ID Number</Label>
                <Input value={newGuest.id_number} onChange={(e) => setNewGuest({...newGuest, id_number: e.target.value})} required />
              </div>
              <div>
                <Label>Address</Label>
                <Input value={newGuest.address} onChange={(e) => setNewGuest({...newGuest, address: e.target.value})} />
              </div>
              <Button type="submit" className="w-full">Register Guest</Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* Booking Dialog - Extracted Component */}
        <BookingDialog
          open={openDialog === 'booking'}
          onClose={() => setOpenDialog(null)}
          guests={guests}
          rooms={rooms}
          companies={companies}
          ratePlans={ratePlans}
          packages={packages}
          newBooking={newBooking}
          setNewBooking={setNewBooking}
          multiRoomBooking={multiRoomBooking}
          handleCreateBooking={handleCreateBooking}
          handleCompanySelect={handleCompanySelect}
          handleContractedRateSelect={handleContractedRateSelect}
          handleChildrenChange={handleChildrenChange}
          handleChildAgeChange={handleChildAgeChange}
          addRoomToMultiBooking={addRoomToMultiBooking}
          removeRoomFromMultiBooking={removeRoomFromMultiBooking}
          updateMultiRoomField={updateMultiRoomField}
          updateMultiRoomChildrenAges={updateMultiRoomChildrenAges}
          updateMultiRoomChildAge={updateMultiRoomChildAge}
          isLite={isLite}
          setOpenDialog={setOpenDialog}
        />

        {/* Quick Company Create Dialog */}
        <CompanyDialog
          open={openDialog === 'company'}
          onClose={() => setOpenDialog(null)}
          newCompany={newCompany}
          setNewCompany={setNewCompany}
          onSubmit={handleCreateCompany}
        />

        {/* Folio View Dialog */}
        <Dialog open={openDialog === 'folio-view'} onOpenChange={(open) => !open && setOpenDialog(null)}>
          <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Folio Management</DialogTitle>
              <DialogDescription>
                {selectedFolio && `Folio ${selectedFolio.folio_number} - ${selectedFolio.folio_type.toUpperCase()}`}
              </DialogDescription>
            </DialogHeader>

            {selectedFolio && (
              <div className="space-y-6">
                {/* Header Summary */}
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 p-6 rounded-lg border">
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <div className="text-sm text-gray-600">Guest</div>
                      <div className="font-semibold">
                        {guests.find(g => g.id === selectedFolio.guest_id)?.name || 'N/A'}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Booking</div>
                      <div className="font-semibold">
                        {(() => {
                          const booking = bookings.find(b => b.id === selectedFolio.booking_id);
                          if (!booking) return 'N/A';
                          return `${new Date(booking.check_in).toLocaleDateString()} - ${new Date(booking.check_out).toLocaleDateString()}`;
                        })()}
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600">Current Balance</div>
                      <div className={`text-2xl font-bold ${selectedFolio.balance > 0 ? 'text-red-600' : selectedFolio.balance < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                        ${selectedFolio.balance?.toFixed(2) || '0.00'}
                      </div>
                      <div className="text-xs text-gray-500">
                        {selectedFolio.balance > 0 ? 'Guest owes hotel' : selectedFolio.balance < 0 ? 'Hotel owes guest' : 'Balanced'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex gap-2">
                  <Button onClick={() => setOpenDialog('post-charge')} variant="default">
                    <Plus className="w-4 h-4 mr-2" />
                    Post Charge
                  </Button>
                  <Button onClick={() => setOpenDialog('post-payment')} variant="default">
                    <Plus className="w-4 h-4 mr-2" />
                    Post Payment
                  </Button>
                </div>

                {/* Charges and Payments Lists */}
                <div className="grid grid-cols-2 gap-6">
                  {/* Charges List */}
                  <div>
                    <h3 className="text-lg font-semibold mb-3 flex items-center">
                      <ClipboardList className="w-5 h-5 mr-2" />
                      Charges
                    </h3>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {folioCharges.length === 0 ? (
                        <div className="text-center text-gray-400 py-8">No charges posted</div>
                      ) : 
                        folioCharges.map((charge) => {
                          // Check if this is a POS charge with line items
                          const isPOSCharge = charge.charge_category === 'restaurant' || charge.charge_category === 'bar' || charge.charge_category === 'room_service';
                          const hasLineItems = charge.line_items && charge.line_items.length > 0;
                          const isExpanded = expandedChargeItems[charge.id];
                          
                          return (
                          <Card key={charge.id} className={charge.voided ? 'opacity-50 bg-gray-50' : ''}>
                            <CardContent className="p-4">
                              <div 
                                className={`flex justify-between items-start ${isPOSCharge && hasLineItems ? 'cursor-pointer hover:bg-gray-50' : ''}`}
                                onClick={() => {
                                  if (isPOSCharge && hasLineItems) {
                                    setExpandedChargeItems(prev => ({
                                      ...prev,
                                      [charge.id]: !prev[charge.id]
                                    }));
                                  }
                                }}
                              >
                                <div className="flex-1">
                                  <div className="flex items-center gap-2">
                                    <div className="font-semibold">{charge.description}</div>
                                    {isPOSCharge && hasLineItems && (
                                      <button className="text-blue-600 text-xs">
                                        {isExpanded ? '▼ Hide Items' : '▶ Show Items'}
                                      </button>
                                    )}
                                  </div>
                                  <div className="text-sm text-gray-600">
                                    {charge.charge_category.replace('_', ' ').toUpperCase()}
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    {new Date(charge.date).toLocaleDateString()} • Qty: {charge.quantity}
                                  </div>
                                  {charge.voided && (
                                    <div className="text-xs text-red-600 mt-1">
                                      VOIDED: {charge.void_reason}
                                    </div>
                                  )}
                                </div>
                                <div className="text-right">
                                  <div className="font-bold">${charge.total.toFixed(2)}</div>
                                  {charge.tax_amount > 0 && (
                                    <div className="text-xs text-gray-500">
                                      +${charge.tax_amount.toFixed(2)} tax
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* POS Line Items Breakdown - NEW */}
                              {isPOSCharge && hasLineItems && isExpanded && (
                                <div className="mt-3 pt-3 border-t bg-blue-50/50 rounded p-3">
                                  <div className="text-xs font-semibold text-gray-700 mb-2">POS Fiş Detayı:</div>
                                  <div className="space-y-1.5">
                                    {charge.line_items.map((item, idx) => (
                                      <div key={idx} className="flex justify-between items-center text-sm">
                                        <div className="flex-1">
                                          <span className="font-medium text-gray-700">
                                            {item.quantity} x {item.item_name}
                                          </span>
                                          {item.modifiers && item.modifiers.length > 0 && (
                                            <div className="text-xs text-gray-500 ml-4">
                                              ({item.modifiers.join(', ')})
                                            </div>
                                          )}
                                        </div>
                                        <span className="font-semibold text-gray-800">
                                          ${(item.unit_price * item.quantity).toFixed(2)}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                  <div className="mt-2 pt-2 border-t flex justify-between text-sm">
                                    <span className="font-semibold">Subtotal:</span>
                                    <span className="font-bold">${charge.total.toFixed(2)}</span>
                                  </div>
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        );
                        })
                      }
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <div className="flex justify-between font-semibold">
                        <span>Total Charges:</span>
                        <span>${folioCharges.filter(c => !c.voided).reduce((sum, c) => sum + c.total, 0).toFixed(2)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Payments List */}
                  <div>
                    <h3 className="text-lg font-semibold mb-3 flex items-center">
                      <DollarSign className="w-5 h-5 mr-2" />
                      Payments
                    </h3>
                    <div className="space-y-2 max-h-96 overflow-y-auto">
                      {folioPayments.length === 0 ? (
                        <div className="text-center text-gray-400 py-8">No payments posted</div>
                      ) : (
                        folioPayments.map((payment) => (
                          <Card key={payment.id} className="bg-green-50">
                            <CardContent className="p-4">
                              <div className="flex justify-between items-start">
                                <div className="flex-1">
                                  <div className="font-semibold">{payment.method.toUpperCase()}</div>
                                  <div className="text-sm text-gray-600">
                                    {payment.payment_type.replace('_', ' ').toUpperCase()}
                                  </div>
                                  <div className="text-xs text-gray-500">
                                    {new Date(payment.processed_at).toLocaleDateString()}
                                  </div>
                                  {payment.reference && (
                                    <div className="text-xs text-gray-500">
                                      Ref: {payment.reference}
                                    </div>
                                  )}
                                </div>
                                <div className="text-right">
                                  <div className="font-bold text-green-600">${payment.amount.toFixed(2)}</div>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        ))
                      )}
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <div className="flex justify-between font-semibold">
                        <span>Total Payments:</span>
                        <span className="text-green-600">${folioPayments.reduce((sum, p) => sum + p.amount, 0).toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Net Balance */}
                <div className="bg-gray-50 p-6 rounded-lg border-2 border-gray-300">
                  <div className="flex justify-between items-center">
                    <span className="text-xl font-semibold">Net Balance:</span>
                    <span className={`text-3xl font-bold ${selectedFolio.balance > 0 ? 'text-red-600' : selectedFolio.balance < 0 ? 'text-green-600' : 'text-gray-600'}`}>
                      ${selectedFolio.balance?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Post Charge Dialog */}
        <Dialog open={openDialog === 'post-charge'} onOpenChange={(open) => !open && setOpenDialog('folio-view')}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Post Charge</DialogTitle>
            </DialogHeader>
            <form onSubmit={handlePostCharge} className="space-y-4">
              <div>
                <Label>Charge Category *</Label>
                <Select value={newFolioCharge.charge_category} onValueChange={(v) => setNewFolioCharge({...newFolioCharge, charge_category: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="room">Room</SelectItem>
                    <SelectItem value="food">Food & Beverage</SelectItem>
                    <SelectItem value="minibar">Minibar</SelectItem>
                    <SelectItem value="spa">Spa</SelectItem>
                    <SelectItem value="laundry">Laundry</SelectItem>
                    <SelectItem value="phone">Phone</SelectItem>
                    <SelectItem value="internet">Internet</SelectItem>
                    <SelectItem value="parking">Parking</SelectItem>
                    <SelectItem value="city_tax">City Tax</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Description *</Label>
                <Input 
                  value={newFolioCharge.description} 
                  onChange={(e) => setNewFolioCharge({...newFolioCharge, description: e.target.value})}
                  placeholder="e.g., Room 101 - Night Charge"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Amount *</Label>
                  <Input 
                    type="number" 
                    step="0.01"
                    value={newFolioCharge.amount} 
                    onChange={(e) => setNewFolioCharge({...newFolioCharge, amount: parseFloat(e.target.value) || 0})}
                    required
                  />
                </div>
                <div>
                  <Label>Quantity *</Label>
                  <Input 
                    type="number" 
                    min="1"
                    value={newFolioCharge.quantity} 
                    onChange={(e) => setNewFolioCharge({...newFolioCharge, quantity: parseFloat(e.target.value) || 1})}
                    required
                  />
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <input 
                  type="checkbox" 
                  id="auto-tax"
                  checked={newFolioCharge.auto_calculate_tax}
                  onChange={(e) => setNewFolioCharge({...newFolioCharge, auto_calculate_tax: e.target.checked})}
                  className="rounded"
                />
                <Label htmlFor="auto-tax" className="cursor-pointer">
                  Auto-calculate city tax
                </Label>
              </div>
              <Button type="submit" className="w-full">Post Charge</Button>
            </form>
          </DialogContent>
        </Dialog>

        {/* Post Payment Dialog */}
        <Dialog open={openDialog === 'post-payment'} onOpenChange={(open) => !open && setOpenDialog('folio-view')}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Post Payment</DialogTitle>
            </DialogHeader>
            <form onSubmit={handlePostPayment} className="space-y-4">
              <div>
                <Label>Payment Method *</Label>
                <Select value={newFolioPayment.method} onValueChange={(v) => setNewFolioPayment({...newFolioPayment, method: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Credit/Debit Card</SelectItem>
                    <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                    <SelectItem value="online">Online Payment</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Payment Type *</Label>
                <Select value={newFolioPayment.payment_type} onValueChange={(v) => setNewFolioPayment({...newFolioPayment, payment_type: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="prepayment">Prepayment</SelectItem>
                    <SelectItem value="deposit">Deposit</SelectItem>
                    <SelectItem value="interim">Interim Payment</SelectItem>
                    <SelectItem value="final">Final Payment</SelectItem>
                    <SelectItem value="refund">Refund</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Amount *</Label>
                <Input 
                  type="number" 
                  step="0.01"
                  value={newFolioPayment.amount} 
                  onChange={(e) => setNewFolioPayment({...newFolioPayment, amount: parseFloat(e.target.value) || 0})}
                  required
                />
              </div>
              <div>
                <Label>Reference / Auth Code</Label>
                <Input 
                  value={newFolioPayment.reference} 
                  onChange={(e) => setNewFolioPayment({...newFolioPayment, reference: e.target.value})}
                  placeholder="e.g., AUTH123456"
                />
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea 
                  value={newFolioPayment.notes} 
                  onChange={(e) => setNewFolioPayment({...newFolioPayment, notes: e.target.value})}
                  rows={2}
                />
              </div>
              <Button type="submit" className="w-full">Post Payment</Button>
            </form>
          </DialogContent>
        </Dialog>

        <HKTaskDialog
          open={openDialog === 'hktask'}
          onClose={() => setOpenDialog(null)}
          rooms={rooms}
          newHKTask={newHKTask}
          setNewHKTask={setNewHKTask}
          onSubmit={handleCreateHKTask}
        />

        <RoomBlockCreateDialog
          open={openDialog === 'roomblock'}
          onClose={() => setOpenDialog(null)}
          rooms={rooms}
          selectedRoom={selectedRoom}
          setSelectedRoom={setSelectedRoom}
          newRoomBlock={newRoomBlock}
          setNewRoomBlock={setNewRoomBlock}
          onSubmit={createRoomBlock}
        />

        <RoomBlockViewDialog
          open={openDialog === 'viewblocks'}
          onClose={() => setOpenDialog(null)}
          selectedRoom={selectedRoom}
          roomBlocks={roomBlocks}
          onCancelBlock={(id) => { cancelRoomBlock(id); setOpenDialog(null); }}
        />

        {/* Guest 360° Profile Dialog - Extracted Component */}
        <Guest360Dialog
          open={openDialog === 'guest360'}
          onClose={() => setOpenDialog(null)}
          guest360Data={guest360Data}
          loadingGuest360={loadingGuest360}
          selectedGuest360={selectedGuest360}
          loadGuest360={loadGuest360}
        />

        {/* Booking Detail Dialog - Double-Click to Open */}
        <BookingDetailDialog
          open={openDialog === 'bookingDetail'}
          onClose={() => setOpenDialog(null)}
          booking={selectedBookingDetail}
          guests={guests}
          rooms={rooms}
          companies={companies}
          onViewFolio={loadBookingFolios}
          onBookingUpdated={loadData}
        />

        {/* Reservation Detail Modal (same as Calendar double-click) */}
        {reservationDetailId && (
          <Suspense fallback={<div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"><div className="bg-white rounded-xl p-6 text-gray-500">Yukleniyor...</div></div>}>
            <ReservationDetailModal
              bookingId={reservationDetailId}
              onClose={() => { setReservationDetailId(null); loadData(); }}
              allBookings={bookings}
            />
          </Suspense>
        )}

        {/* Floating Action Button - Quick Actions */}
        {/* Maintenance Work Order Dialog */}
        <MaintenanceDialog
          open={maintenanceDialogOpen}
          onClose={() => setMaintenanceDialogOpen(false)}
          maintenanceForm={maintenanceForm}
          setMaintenanceForm={setMaintenanceForm}
        />

        {/* FloatingActionButton - Quick Actions (mirrors top toolbar) */}
        <FloatingActionButton
          actions={[
            {
              label: 'New Booking',
              icon: <Plus className="w-5 h-5" />,
              onClick: () => {
                setOpenDialog('newbooking');
                toast.info('Opening new booking form...');
              }
            },
            {
              label: 'New Guest',
              icon: <UserPlus className="w-5 h-5" />,
              onClick: () => setOpenDialog('newguest')
            },
            {
              label: 'Flash Report',
              icon: <FileText className="w-5 h-5" />,
              onClick: async () => {
                try {
                  const response = await axios.get('/reports/flash-report');
                  toast.success('Flash report generated!');
                  console.log('Flash report:', response.data);
                } catch (error) {
                  toast.error('Failed to generate report');
                }
              }
            },
            {
              label: 'Refresh Dashboard',
              icon: <RefreshCw className="w-5 h-5" />,
              onClick: () => loadData()
            }
          ]}
        />

      </div>

        <GuestInfoDialog
          open={openDialog === 'guestinfo'}
          onClose={() => setOpenDialog(null)}
          selectedGuest={selectedGuest}
          setSelectedGuest={setSelectedGuest}
          onSaved={loadData}
        />

        {/* Payment Dialog */}
        <PaymentDialog
          open={openDialog === 'payment'}
          onClose={() => setOpenDialog(null)}
          selectedBooking={selectedBooking}
          paymentForm={paymentForm}
          setPaymentForm={setPaymentForm}
          onPaymentDone={loadData}
        />

        <FindRoomDialog
          open={openDialog === 'findroom'}
          onClose={() => setOpenDialog(null)}
          findRoomCriteria={findRoomCriteria}
          setFindRoomCriteria={setFindRoomCriteria}
          onRoomSelected={(room) => {
            setNewBooking({
              ...newBooking,
              room_id: room.id,
              check_in: findRoomCriteria.check_in,
              check_out: findRoomCriteria.check_out,
              adults: findRoomCriteria.guests
            });
            setOpenDialog('booking');
          }}
        />

    </Layout>
  );
};

export default PMSModule;
