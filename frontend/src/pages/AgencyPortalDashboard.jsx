import { currencyTotalsText, formatAgencyMoney } from '@/utils/agencyMoney';
import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { AGENCY_ADMIN_RETURN_PATH, agencyVoucherPath } from '@/utils/agencyPortalNavigation';
import axios from 'axios';
import { toast } from 'sonner';
import { Search, CalendarDays, Users, Bed, Plus, Loader2, Building2, LogOut, ClipboardList, Eye, Phone, Mail, MapPin, RefreshCw, ShieldCheck, Printer, XCircle, WalletCards, SlidersHorizontal, ChevronDown, Sparkles, Hotel, ArrowRight, BadgeCheck, Settings, Bell, Globe2, KeyRound, Save } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useTranslation } from 'react-i18next';
const RAW_BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '/api';
const API_BASE = RAW_BACKEND_URL.endsWith('/api') ? RAW_BACKEND_URL : `${RAW_BACKEND_URL.replace(/\/+$/, '')}/api`;
// Isolated client: never inherit a hotel employee's Authorization header.
const agencyApi = axios.create({ baseURL: API_BASE, timeout: 30000, withCredentials: false });
agencyApi.interceptors.request.use(config => {
  const agencyToken = localStorage.getItem('agency_token');
  config.headers = config.headers || {};
  if (agencyToken && !String(config.url || '').includes('/auth/login')) {
    config.headers.Authorization = `Bearer ${agencyToken}`;
  } else {
    delete config.headers.Authorization;
  }
  return config;
});
// A signed-in session that the server no longer accepts (expired, password
// changed, account disabled) must end visibly instead of leaving spinners.
// Only the session that made the request may be ended: a late 401 from a
// previous (signed-out) session must not sign out the new one.
export const endsCurrentSession = (error, currentToken) => {
  const url = String(error?.config?.url || '');
  const sentWith = String(error?.config?.headers?.Authorization || '');
  return error?.response?.status === 401 && Boolean(currentToken)
    && sentWith === `Bearer ${currentToken}` && !url.includes('/auth/login');
};
// What the portal does with a failed identity load. A response that belongs
// to an older session (the user signed out and in meanwhile) is ignored.
export const profileFailureAction = (error, requestToken, currentToken) => {
  if (!requestToken || requestToken !== currentToken) return 'ignore';
  return [401, 403].includes(error?.response?.status) ? 'logout' : 'error';
};
agencyApi.interceptors.response.use(undefined, error => {
  if (endsCurrentSession(error, localStorage.getItem('agency_token'))) {
    window.dispatchEvent(new CustomEvent('agency-session-expired'));
  }
  return Promise.reject(error);
});

const AgencyImage = ({ src, alt, className }) => {
  const [objectUrl, setObjectUrl] = useState('');
  useEffect(() => {
    if (!src) return undefined;
    if (!src.startsWith('/api/uploads/')) {
      setObjectUrl(src);
      return undefined;
    }
    let active = true;
    let createdUrl = '';
    agencyApi.get(src.replace(/^\/api/, ''), { responseType: 'blob' }).then(({ data }) => {
      if (!active) return;
      createdUrl = URL.createObjectURL(data);
      setObjectUrl(createdUrl);
    }).catch(() => setObjectUrl(''));
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src]);
  return objectUrl ? <img src={objectUrl} alt={alt} className={className} /> : <div className={`${className} bg-slate-100`} aria-label={alt} />;
};

const toDateInput = date => {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
};
const initialDates = () => {
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  return { check_in: toDateInput(today), check_out: toDateInput(tomorrow), adults: 2, children: 0, child_ages: [], q: '', city: '', amenities: [], meal_plans: [], min_star_rating: null, max_price: null };
};
const AMENITY_FILTERS = [
  ['pool', 'Havuz'], ['jacuzzi', 'Jakuzi'], ['beach', 'Plaj'], ['sea_view', 'Deniz manzarası'],
  ['spa', 'Spa'], ['parking', 'Otopark'], ['wifi', 'Wi-Fi'], ['family_room', 'Aile odası'],
];
const MEAL_FILTERS = [['RO', 'Sadece oda'], ['BB', 'Oda kahvaltı'], ['HB', 'Yarım pansiyon'], ['FB', 'Tam pansiyon'], ['AI', 'Her şey dahil']];
const PAYMENT_TERMS_LABELS = { prepaid: 'Ön ödemeli', on_arrival: 'Girişte', net_7: '7 gün', net_15: '15 gün', net_30: '30 gün' };
const CONTRACT_STATUS_LABELS = { approved: 'Onaylandı', pending: 'Otel onayı bekleniyor', rejected: 'Reddedildi', expired: 'Süresi doldu', terminated: 'Sonlandırıldı', withdrawn: 'Geri çekildi' };
const toggleFilter = (values, value) => values.includes(value) ? values.filter(item => item !== value) : [...values, value];
const resizeChildAges = (ages, count) => Array.from({ length: count }, (_, index) => ages?.[index] ?? 0);
export const PAYMENT_STATUS_LABELS = {
  paid: 'Ödendi', partial: 'Kısmen ödendi', pending: 'Ödeme bekleniyor', unpaid: 'Ödeme bekleniyor',
  transferred: 'Cari hesaba aktarıldı', refunded: 'İade edildi',
};
const formatMoney = (amount, currency = 'TRY') => new Intl.NumberFormat('tr-TR', {
  style: 'currency', currency, minimumFractionDigits: 2, maximumFractionDigits: 2,
}).format(Number(amount) || 0);
const formatDate = value => value ? new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(new Date(`${String(value).slice(0, 10)}T12:00:00`)) : '—';
const AgencyPortalDashboard = () => {
  const {
    t
  } = useTranslation();
  const [agencyUser, setAgencyUser] = useState(null);
  const [agencyInfo, setAgencyInfo] = useState(null);
  const [hotelInfo, setHotelInfo] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('agency_token'));
  const sessionEndingRef = useRef(false);
  const [portalMode, setPortalMode] = useState(localStorage.getItem('agency_portal_mode') || 'hotel');
  const [hotels, setHotels] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState(localStorage.getItem('agency_selected_hotel') || '');
  const [profileLoading, setProfileLoading] = useState(Boolean(localStorage.getItem('agency_token')));
  const [profileError, setProfileError] = useState('');
  const [profileRevision, setProfileRevision] = useState(0);
  const [impersonation, setImpersonation] = useState(null);

  // Login
  const [loginForm, setLoginForm] = useState({
    email: '',
    password: ''
  });
  const [loginLoading, setLoginLoading] = useState(false);

  // Content
  const [content, setContent] = useState(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentTenantId, setContentTenantId] = useState('');

  // Availability
  const [searchForm, setSearchForm] = useState(initialDates);
  const [availability, setAvailability] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);

  // Reservation
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [selectedRoomType, setSelectedRoomType] = useState(null);
  const [bookingForm, setBookingForm] = useState({
    guest_name: '',
    guest_email: '',
    guest_phone: '',
    adults: 2,
    children: 0,
    child_ages: [],
    special_requests: '',
    total_amount: 0,
    idempotency_key: ''
  });
  const [bookingLoading, setBookingLoading] = useState(false);

  // Reservations list
  const [reservations, setReservations] = useState([]);
  const [paymentHistory, setPaymentHistory] = useState(null);
  const [creditOverview, setCreditOverview] = useState(null);
  const [reservationsLoading, setReservationsLoading] = useState(false);
  const [reconciliation, setReconciliation] = useState(null);
  const [notices, setNotices] = useState([]);
  const [statements, setStatements] = useState([]);
  const [paymentNotice, setPaymentNotice] = useState(null);
  const [paymentNoticeBusy, setPaymentNoticeBusy] = useState(false);
  const [disputeTarget, setDisputeTarget] = useState(null);
  const [disputeReason, setDisputeReason] = useState('');
  const [disputeIds, setDisputeIds] = useState([]);
  const [statementBusy, setStatementBusy] = useState(false);
  const [reconPeriod, setReconPeriod] = useState(() => {
    const startDate = new Date(); startDate.setDate(startDate.getDate() - 30);
    return { start: toDateInput(startDate), end: toDateInput(new Date()) };
  });
  const [negotiations, setNegotiations] = useState([]);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [modificationTarget, setModificationTarget] = useState(null);
  const [modificationForm, setModificationForm] = useState({ check_in: '', check_out: '', room_type: '', rate_plan_code: '', reason: '' });
  const [modificationLoading, setModificationLoading] = useState(false);
  const [negotiationDecision, setNegotiationDecision] = useState(null);
  const [negotiationNote, setNegotiationNote] = useState('');
  const [negotiationLoading, setNegotiationLoading] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelLoading, setCancelLoading] = useState(false);
  const [voucherEmailTarget, setVoucherEmailTarget] = useState(null);
  const [voucherEmail, setVoucherEmail] = useState('');
  const [voucherEmailLoading, setVoucherEmailLoading] = useState(false);
  const [portalSettings, setPortalSettings] = useState(null);
  const [profile, setProfile] = useState(null);
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', repeat: '' });
  const [profileBusy, setProfileBusy] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [widgetOriginsText, setWidgetOriginsText] = useState('');
  const [contracts, setContracts] = useState([]);
  const [contractHotels, setContractHotels] = useState([]);
  const [selectedHotelIds, setSelectedHotelIds] = useState([]);
  const [proposing, setProposing] = useState(false);
  const [contractsLoading, setContractsLoading] = useState(false);
  const [withdrawingId, setWithdrawingId] = useState(null);
  const [withdrawBusy, setWithdrawBusy] = useState(false);
  const [contractForm, setContractForm] = useState({ tenant_id: '', commission_pct: '', valid_from: toDateInput(new Date()), valid_to: `${new Date().getFullYear() + 1}-12-31`, payment_terms: 'on_arrival', currency: 'TRY', allow_base_rate_fallback: false });

  // Login handler
  const handleLogin = async e => {
    e.preventDefault();
    setLoginLoading(true);
    try {
      const credentials = { email: loginForm.email.trim().toLowerCase(), password: loginForm.password };
      let response;
      let mode = 'hotel';
      try {
        response = await agencyApi.post('/agency-portal/auth/login', credentials);
      } catch (localError) {
        if (![401, 403, 404].includes(localError.response?.status)) throw localError;
        response = await agencyApi.post('/marketplace/v1/extranet/auth/login', credentials);
        mode = 'marketplace';
      }
      const { data } = response;
      localStorage.setItem('agency_token', data.token);
      localStorage.setItem('agency_portal_mode', mode);
      setPortalMode(mode);
      setProfileLoading(true);
      setToken(data.token);
      setAgencyUser(data.user);
      setAgencyInfo(data.agency);
      setProfileError('');
      toast.success('Acente hesabınıza güvenli giriş yapıldı.');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Giriş bilgileri doğrulanamadı. E-posta ve şifrenizi kontrol edin.');
    } finally {
      setLoginLoading(false);
    }
  };
  useEffect(() => {
    const expired = () => {
      if (sessionEndingRef.current) return;  // the logout's own requests may 401 too
      sessionEndingRef.current = true;
      toast.error('Oturum süreniz doldu. Lütfen yeniden giriş yapın.', { id: 'agency-session-expired' });
      Promise.resolve(handleLogout()).finally(() => { sessionEndingRef.current = false; });
    };
    window.addEventListener('agency-session-expired', expired);
    return () => window.removeEventListener('agency-session-expired', expired);
  });
  const handleLogout = async () => {
    const adminReturnPath = impersonation?.active ? AGENCY_ADMIN_RETURN_PATH : null;
    if (impersonation?.active) {
      try {
        await agencyApi.post('/marketplace/v1/extranet/admin-context/exit');
      } catch {
        // Local cleanup and return must still work if the short session already expired.
      }
    }
    localStorage.removeItem('agency_token');
    localStorage.removeItem('agency_portal_mode');
    localStorage.removeItem('agency_selected_hotel');
    setToken(null);
    setAgencyUser(null);
    setAgencyInfo(null);
    setHotelInfo(null);
    setContent(null);
    setAvailability(null);
    setReservations([]);
    setHotels([]);
    setSelectedTenantId('');
    setContentTenantId('');
    setProfileLoading(false);
    setProfileError('');
    setImpersonation(null);
    if (adminReturnPath) {
      sessionStorage.removeItem('agency_admin_return_path');
      window.location.assign(adminReturnPath);
    }
  };

  // Load profile on mount if token exists
  useEffect(() => {
    if (!token) return undefined;
    let active = true;
    const requestToken = token;
    const current = () => active && localStorage.getItem('agency_token') === requestToken;
    const loadProfile = async () => {
      try {
        if (portalMode === 'marketplace') {
          const { data } = await agencyApi.get('/marketplace/v1/extranet/profile');
          if (!current()) return;  // answer of an older session
          const availableHotels = data.hotels || [];
          setAgencyUser(data.user || null);
          // Discovery starts from the whole contracted portfolio. A hotel is
          // selected only when the agent explicitly narrows the search or books.
          const allowedSelected = '';
          setAgencyInfo(data.agency || null);
          setImpersonation(data.impersonation || null);
          setHotels(availableHotels);
          setContentTenantId(current => availableHotels.some(hotel => hotel.tenant_id === current) ? current : (availableHotels[0]?.tenant_id || ''));
          setSelectedTenantId(allowedSelected);
          localStorage.removeItem('agency_selected_hotel');
          const selected = availableHotels.find(h => h.tenant_id === allowedSelected);
          setHotelInfo(selected ? { name: selected.name, currency: selected.currency || 'TRY', ...selected } : null);
        } else {
          const { data } = await agencyApi.get('/agency-portal/profile');
          if (!current()) return;
          setAgencyUser(data.user || null);
          setAgencyInfo(data.agency);
          setHotelInfo(data.hotel || null);
        }
        setProfileError('');
      } catch (err) {
        const action = profileFailureAction(err, requestToken, active ? localStorage.getItem('agency_token') : null);
        if (action === 'logout') handleLogout();
        else if (action === 'error') setProfileError('Acente hesabı doğrulanamadı. Bağlantınızı kontrol edip tekrar deneyin.');
      } finally {
        if (current()) setProfileLoading(false);
      }
    };
    loadProfile();
    return () => { active = false; };
  }, [token, profileRevision, portalMode]);

  const loadNotices = async () => {
    if (portalMode !== 'marketplace') return;
    try {
      const { data } = await agencyApi.get('/marketplace/v1/notices', { params: { limit: 20 } });
      setNotices(data.items || []);
    } catch {
      // Notices are informational; the portal stays usable without them.
    }
  };
  useEffect(() => {
    if (token && portalMode === 'marketplace') loadNotices();
  }, [token, portalMode]); // eslint-disable-line react-hooks/exhaustive-deps
  const markNoticeRead = async notice => {
    try {
      await agencyApi.post(`/marketplace/v1/notices/${encodeURIComponent(notice.id)}/read`);
      setNotices(current => current.map(item => (item.id === notice.id ? { ...item, read: true } : item)));
    } catch (err) { toast.error(err.response?.data?.detail || 'Bildirim güncellenemedi.'); }
  };

  // Load content
  const loadContent = async tenantIdOverride => {
    setContentLoading(true);
    try {
      if (portalMode === 'marketplace') {
        const tenantId = typeof tenantIdOverride === 'string' && tenantIdOverride
          ? tenantIdOverride
          : (contentTenantId || selectedTenantId || hotels[0]?.tenant_id || '');
        if (!tenantId) return setContent({ published: false, hotel_content: null });
        setContentTenantId(tenantId);
        const { data } = await agencyApi.get(`/marketplace/v1/hotels/${encodeURIComponent(tenantId)}`);
        setContent({
          published: true,
          hotel_content: {
            ...data.listing,
            hotel_name: data.listing?.hotel_name,
            room_types: data.room_types || [],
          },
        });
      } else {
        const { data } = await agencyApi.get('/agency-portal/content');
        setContent(data);
      }
    } catch {
      toast.error('Tesis bilgileri şu anda görüntülenemiyor. Lütfen yeniden deneyin.');
    } finally {
      setContentLoading(false);
    }
  };

  // Search availability
  const handleSearch = async () => {
    if (!searchForm.check_in || !searchForm.check_out) return toast.error('Arama için giriş ve çıkış tarihlerini seçin.');
    if (searchForm.check_out <= searchForm.check_in) return toast.error('Çıkış tarihi, giriş tarihinden sonra olmalıdır.');
    setSearchLoading(true);
    try {
      if (portalMode === 'marketplace') {
        const { data } = await agencyApi.post('/marketplace/v1/search', searchForm);
        const hotelResults = selectedTenantId
          ? (data.results || []).filter(result => result.tenant_id === selectedTenantId)
          : (data.results || []);
        const roomTypes = hotelResults.flatMap(hotel => (hotel.available_room_types || []).map(room => ({
          ...room,
          tenant_id: hotel.tenant_id,
          hotel_name: hotel.hotel_name,
          hotel_city: hotel.city,
          hotel_amenities: hotel.amenities || [],
          hotel_photos: hotel.photos || [],
          hotel_description: hotel.description || '',
          currency: hotel.currency || 'TRY',
          base_price: room.nightly_rates?.[0]?.rate ?? room.base_price,
          stay_total: room.total_price,
        })));
        setAvailability({
          check_in: data.check_in,
          check_out: data.check_out,
          night_count: Math.max(1, Math.round((new Date(data.check_out) - new Date(data.check_in)) / 86400000)),
          adults: searchForm.adults,
          children: searchForm.children,
          child_ages: searchForm.child_ages,
          currency: 'TRY',
          hotels: hotelResults,
          room_types: roomTypes,
          total_hotels: hotelResults.length,
        });
      } else {
        const { data } = await agencyApi.get('/agency-portal/availability', { params: searchForm });
        setAvailability(data);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Müsaitlik sonuçları alınamadı. Lütfen aramanızı yeniden deneyin.');
    } finally {
      setSearchLoading(false);
    }
  };

  // Book
  const openBookingForm = roomType => {
    setSelectedRoomType(roomType);
    if (roomType.tenant_id) {
      setSelectedTenantId(roomType.tenant_id);
      localStorage.setItem('agency_selected_hotel', roomType.tenant_id);
      const selected = hotels.find(hotel => hotel.tenant_id === roomType.tenant_id);
      setHotelInfo(selected ? { name: selected.name, currency: roomType.currency || selected.currency || 'TRY', ...selected } : null);
    }
    const nights = Math.max(1, Math.ceil((new Date(searchForm.check_out) - new Date(searchForm.check_in)) / (1000 * 60 * 60 * 24)));
    setBookingForm({
      guest_name: '',
      guest_email: '',
      guest_phone: '',
      adults: searchForm.adults,
      children: searchForm.children,
      child_ages: [...searchForm.child_ages],
      special_requests: '',
      total_amount: roomType.stay_total ?? roomType.base_price * nights,
      idempotency_key: crypto.randomUUID()
    });
    setShowBookingForm(true);
  };
  const handleBooking = async () => {
    if (bookingForm.guest_name.trim().length < 2) return toast.error('Misafir adı en az 2 karakter olmalıdır.');
    if (bookingForm.adults + bookingForm.children > Number(selectedRoomType?.capacity || 0)) {
      return toast.error('Misafir sayısı seçilen oda tipinin kapasitesini aşıyor.');
    }
    setBookingLoading(true);
    try {
      const payload = {
        check_in: searchForm.check_in,
        check_out: searchForm.check_out,
        guest_name: bookingForm.guest_name.trim(),
        guest_email: bookingForm.guest_email.trim() || null,
        guest_phone: bookingForm.guest_phone.trim(),
        adults: bookingForm.adults,
        children: bookingForm.children,
        child_ages: bookingForm.child_ages,
        special_requests: bookingForm.special_requests.trim(),
        rate_plan_code: selectedRoomType.rate_plan_code,
        idempotency_key: bookingForm.idempotency_key,
      };
      let response;
      if (portalMode === 'marketplace') {
        response = await agencyApi.post('/marketplace/v1/reservations', {
          ...payload,
          tenant_id: selectedRoomType.tenant_id,
          room_type: selectedRoomType.room_type,
          rate_plan_code: selectedRoomType.rate_plan_code,
          total_amount: bookingForm.total_amount,
          idempotency_key: bookingForm.idempotency_key,
        });
      } else {
        response = await agencyApi.post('/agency-portal/reservations', {
          ...payload,
          room_type_id: selectedRoomType.room_type,
        });
      }
      toast.success(response.data.message || `Rezervasyon başarıyla oluşturuldu. Onay kodu: ${response.data.reservation?.confirmation_code || '-'}`);
      const integration = (response.data.reservation || response.data.booking)?.integration_status;
      if (integration && integration !== 'complete') toast.info('Rezervasyon kaydedildi. Entegrasyon işlemleri takip ediliyor; yeniden rezervasyon oluşturmayın.');
      setShowBookingForm(false);
      setAvailability(null);
      loadReservations();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Rezervasyon oluşturulamadı. Müsaitlik değişmiş olabilir; lütfen yeniden arayın.');
    } finally {
      setBookingLoading(false);
    }
  };

  // Load reservations
  const loadReservations = async () => {
    setReservationsLoading(true);
    try {
      if (portalMode === 'marketplace') {
        const [{ data }, { data: negotiationData }] = await Promise.all([
          agencyApi.get('/marketplace/v1/reservations', { params: selectedTenantId ? { tenant_id: selectedTenantId } : {} }),
          agencyApi.get('/marketplace/v1/negotiations'),
        ]);
        setReservations(data.reservations || []);
        setNegotiations((negotiationData.items || []).filter(item => !selectedTenantId || item.tenant_id === selectedTenantId));
      } else {
        const { data } = await agencyApi.get('/agency-portal/reservations');
        setReservations(Array.isArray(data) ? data : data.items || []);
      }
    } catch {
      toast.error('Rezervasyonlarınız şu anda görüntülenemiyor. Lütfen yeniden deneyin.');
    } finally {
      setReservationsLoading(false);
    }
  };
  const decideNegotiation = (proposal, accept) => {
    setNegotiationDecision({ proposal, accept });
    setNegotiationNote('');
  };
  const submitNegotiationDecision = async () => {
    if (!negotiationDecision) return;
    const { proposal, accept } = negotiationDecision;
    const responseNote = negotiationNote.trim();
    if (!accept && responseNote.length < 5) return toast.error('Rezervasyonu koruma gerekçesi en az 5 karakter olmalıdır.');
    setNegotiationLoading(true);
    try {
      await agencyApi.post(`/marketplace/v1/negotiations/${encodeURIComponent(proposal.id)}/decision`, { accept, response_note: responseNote });
      toast.success(accept ? 'Karşılıklı iptal onaylandı.' : 'İptal talebi reddedildi; rezervasyon korunuyor.');
      setNegotiationDecision(null);
      loadReservations();
    } catch (err) { toast.error(err.response?.data?.detail || 'Yanıtınız kaydedilemedi. Lütfen yeniden deneyin.'); }
    finally { setNegotiationLoading(false); }
  };
  const openCancellationDialog = reservation => {
    setCancelTarget(reservation);
    setCancelReason('');
  };
  const cancelReservation = async () => {
    const reason = cancelReason.trim();
    if (reason.length < 5) return toast.error('İptal gerekçesi en az 5 karakter olmalıdır.');
    setCancelLoading(true);
    try {
      await agencyApi.delete(`/marketplace/v1/reservations/${encodeURIComponent(cancelTarget.id)}`, { params: { reason } });
      toast.success('İptal talebi otele iletildi. Otel onay verene kadar rezervasyon korunur.');
      setCancelTarget(null);
      setCancelReason('');
      loadReservations();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İptal talebi iletilemedi. Lütfen yeniden deneyin.');
    } finally {
      setCancelLoading(false);
    }
  };
  const proposeModification = reservation => {
    setModificationTarget(reservation);
    setModificationForm({
      check_in: String(reservation.check_in || '').slice(0, 10),
      check_out: String(reservation.check_out || '').slice(0, 10),
      room_type: reservation.room_type || '',
      rate_plan_code: reservation.rate_plan_code || '',
      reason: '',
    });
  };
  const submitModification = async () => {
    const form = {
      ...modificationForm,
      room_type: modificationForm.room_type.trim(),
      rate_plan_code: modificationForm.rate_plan_code.trim(),
      reason: modificationForm.reason.trim(),
    };
    if (!form.check_in || !form.check_out || form.check_out <= form.check_in) return toast.error('Çıkış tarihi, giriş tarihinden sonra olmalıdır.');
    if (!form.room_type) return toast.error('Oda tipi boş olamaz.');
    if (!form.rate_plan_code) return toast.error('Fiyat planı seçilmelidir.');
    if (form.reason.length < 5) return toast.error('Değişiklik açıklaması en az 5 karakter olmalıdır.');
    setModificationLoading(true);
    try {
      await agencyApi.post(`/marketplace/v1/reservations/${encodeURIComponent(modificationTarget.id)}/modification-proposals`, form);
      toast.success('Değişiklik talebi otele iletildi. Onay verilene kadar mevcut rezervasyon korunur.');
      setModificationTarget(null);
      loadReservations();
    } catch (err) { toast.error(err.response?.data?.detail || 'Değişiklik talebi iletilemedi. Lütfen yeniden deneyin.'); }
    finally { setModificationLoading(false); }
  };
  const printVoucher = async reservation => {
    try {
      const { data } = await agencyApi.get(agencyVoucherPath(portalMode, reservation.id), { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }));
      const popup = window.open(url, '_blank', 'noopener,noreferrer');
      if (!popup) {
        const link = document.createElement('a');
        link.href = url;
        link.download = `${reservation.confirmation_code || reservation.id}.pdf`;
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) { toast.error(err.response?.data?.detail || 'Rezervasyon belgesi oluşturulamadı. Lütfen yeniden deneyin.'); }
  };
  const openVoucherEmailDialog = reservation => {
    setVoucherEmailTarget(reservation);
    setVoucherEmail(reservation.guest_email || '');
  };
  const emailVoucher = async () => {
    const email = voucherEmail.trim();
    if (!email || !voucherEmailTarget) return;
    setVoucherEmailLoading(true);
    try {
      await agencyApi.post(agencyVoucherPath(portalMode, voucherEmailTarget.id, true), { email });
      toast.success('Rezervasyon belgesi e-posta ile gönderildi.');
      setVoucherEmailTarget(null);
      setVoucherEmail('');
    } catch (err) { toast.error(err.response?.data?.detail || 'Rezervasyon belgesi gönderilemedi. Lütfen e-posta adresini kontrol edin.'); }
    finally { setVoucherEmailLoading(false); }
  };
  const reconPeriodParams = () => {
    if (!reconPeriod.start || !reconPeriod.end || reconPeriod.end < reconPeriod.start) {
      toast.error('Mutabakat dönemi için geçerli bir başlangıç ve bitiş tarihi seçin.');
      return null;
    }
    return { period_start: reconPeriod.start, period_end: reconPeriod.end };
  };
  const NOTICE_STATUS = { pending: 'Otel doğrulaması bekleniyor', verified: 'Doğrulandı', rejected: 'Reddedildi' };
  const openPaymentNotice = statement => {
    const pending = (statement.payment_notices || []).filter(n => n.status === 'pending').reduce((sum, n) => sum + Number(n.amount || 0), 0);
    setPaymentNotice({ statement, amount: Math.max(0, Number(statement.outstanding || 0) - pending).toFixed(2),
      paid_at: toDateInput(new Date()), reference: '', method: 'bank_transfer', file: null });
  };
  const submitPaymentNotice = async event => {
    event.preventDefault();
    const form = new FormData();
    form.append('amount', paymentNotice.amount);
    form.append('paid_at', paymentNotice.paid_at);
    form.append('reference', paymentNotice.reference.trim());
    form.append('method', paymentNotice.method);
    if (paymentNotice.file) form.append('proof', paymentNotice.file);
    setPaymentNoticeBusy(true);
    try {
      await agencyApi.post(`/marketplace/v1/statements/${paymentNotice.statement.id}/payment-notices`, form);
      toast.success('Ödeme bildiriminiz otele iletildi. Otel doğruladığında bakiye ve krediniz güncellenir.');
      setPaymentNotice(null);
      setStatements((await agencyApi.get('/marketplace/v1/statements')).data.items || []);
    } catch (err) { toast.error(err.response?.data?.detail || 'Ödeme bildirimi gönderilemedi.'); }
    finally { setPaymentNoticeBusy(false); }
  };
  const openPaymentProof = async (statement, notice) => {
    try {
      const { data } = await agencyApi.get(`/marketplace/v1/statements/${statement.id}/payment-notices/${notice.id}/proof`, { responseType: 'blob' });
      window.open(URL.createObjectURL(data), '_blank', 'noopener');
    } catch { toast.error('Dekont açılamadı.'); }
  };
  const agreeStatement = async statement => {
    setStatementBusy(true);
    try {
      await agencyApi.post(`/marketplace/v1/statements/${encodeURIComponent(statement.id)}/agree`);
      toast.success(`${statement.number} onaylandı; otele iletildi.`);
      setStatements((await agencyApi.get('/marketplace/v1/statements')).data.items || []);
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre onaylanamadı.'); }
    finally { setStatementBusy(false); }
  };
  const openDispute = async statement => {
    try {
      const { data } = await agencyApi.get(`/marketplace/v1/statements/${encodeURIComponent(statement.id)}`);
      setDisputeTarget(data); setDisputeReason(''); setDisputeIds([]);
    } catch (err) { toast.error(err.response?.data?.detail || 'Ekstre açılamadı.'); }
  };
  const submitDispute = async () => {
    setStatementBusy(true);
    try {
      await agencyApi.post(`/marketplace/v1/statements/${encodeURIComponent(disputeTarget.id)}/dispute`, { reason: disputeReason.trim(), booking_ids: disputeIds });
      toast.success('İtirazınız otele iletildi.');
      setDisputeTarget(null);
      setStatements((await agencyApi.get('/marketplace/v1/statements')).data.items || []);
    } catch (err) { toast.error(err.response?.data?.detail || 'İtiraz gönderilemedi.'); }
    finally { setStatementBusy(false); }
  };
  const openPaymentHistory = async reservation => {
    setPaymentHistory({ reservation, loading: true });
    try {
      const { data } = await agencyApi.get(`/marketplace/v1/reservations/${encodeURIComponent(reservation.id)}/payments`);
      setPaymentHistory({ reservation, ...data });
    } catch (err) {
      setPaymentHistory({ reservation, error: err.response?.data?.detail || 'Ödeme bilgisi alınamadı.' });
    }
  };
  const loadReconciliation = async () => {
    if (portalMode !== 'marketplace') return;
    const params = reconPeriodParams();
    if (!params) return;
    setReconciliation(null);
    agencyApi.get('/marketplace/v1/statements').then(({ data }) => setStatements(data.items || [])).catch(() => setStatements([]));
    agencyApi.get('/marketplace/v1/extranet/credit').then(({ data }) => setCreditOverview(data.hotels || [])).catch(() => setCreditOverview([]));
    try { const { data } = await agencyApi.get('/marketplace/v1/reconciliation/agency', { params }); setReconciliation(data); }
    catch (err) {
      setReconciliation({ error: err.response?.data?.detail || 'Mutabakat özeti yüklenemedi.' });
      if (err.response?.status !== 401) toast.error(err.response?.data?.detail || 'Mutabakat özeti yüklenemedi. Lütfen yeniden deneyin.');
    }
  };
  const loadContracts = async () => {
    if (portalMode !== 'marketplace') return;
    setContractsLoading(true);
    try {
      const [{ data: contractData }, { data: hotelData }] = await Promise.all([
        agencyApi.get('/marketplace/v1/contracts/mine'),
        agencyApi.get('/marketplace/v1/contracts/hotel-candidates'),
      ]);
      setContracts(contractData.contracts || []);
      setContractHotels(hotelData.hotels || []);
      setContractForm(current => ({ ...current, commission_pct: current.commission_pct || String(Math.round(Number(agencyInfo?.default_commission_pct ?? 12)) || 12) }));
    } catch (err) { toast.error(err.response?.data?.detail || 'Sözleşmeler yüklenemedi.'); }
    finally { setContractsLoading(false); }
  };
  // A pending proposal (e.g. sent to the wrong hotel) can be withdrawn
  // before the hotel decides; it then never becomes a contract.
  const withdrawContract = async contract => {
    setWithdrawBusy(true);
    try {
      await agencyApi.delete(`/marketplace/v1/contracts/${contract.id}`);
      toast.success(`${contract.contract_code} teklifi geri çekildi.`);
      setWithdrawingId(null);
      await loadContracts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Teklif geri çekilemedi.'); }
    finally { setWithdrawBusy(false); }
  };
  const proposeContract = async event => {
    event.preventDefault();
    if (!selectedHotelIds.length) return toast.error('Teklif göndermek için en az bir otel seçin.');
    setProposing(true);
    try {
      const { data } = await agencyApi.post('/marketplace/v1/contracts/propose-bulk', {
        tenant_ids: selectedHotelIds,
        commission_pct: Math.round(Number(contractForm.commission_pct)),
        payment_terms: contractForm.payment_terms,
        valid_from: contractForm.valid_from,
        valid_to: contractForm.valid_to,
        cancellation_policy: { free_until_days_before: 7, penalty_pct: 50, no_show_penalty_pct: 100 },
      });
      if (data.sent) toast.success(`${data.sent} otele teklif gönderildi. Her otel ayrı onaylar; onaydan önce satış açılmaz.`);
      (data.results || []).filter(result => !result.ok).forEach(result => {
        const hotel = contractHotels.find(item => item.tenant_id === result.tenant_id);
        toast.error(`${hotel?.hotel_name || 'Otel'}: ${typeof result.error === 'string' ? result.error : 'teklif gönderilemedi'}`);
      });
      setSelectedHotelIds([]);
      await loadContracts();
    } catch (err) { toast.error(err.response?.data?.detail || 'Sözleşme teklifi gönderilemedi.'); }
    finally { setProposing(false); }
  };

  const downloadReconciliation = async () => {
    const params = reconPeriodParams();
    if (!params) return;
    try {
      const { data } = await agencyApi.get('/marketplace/v1/reconciliation/agency.csv', {
        params, responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([data], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a'); link.href = url; link.download = `acente-mutabakat-${params.period_start}-${params.period_end}.csv`; link.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(err.response?.data?.detail || 'Mutabakat dosyası indirilemedi. Lütfen yeniden deneyin.'); }
  };
  const loadPortalSettings = async () => {
    if (portalMode !== 'marketplace') return;
    setSettingsLoading(true);
    try {
      const [{ data }, { data: me }] = await Promise.all([
        agencyApi.get('/marketplace/v1/extranet/settings'),
        agencyApi.get('/marketplace/v1/extranet/profile'),
      ]);
      setPortalSettings(data);
      // Same identity endpoint the portal reload uses ({user, impersonation}).
      setProfile({ name: me.user?.name || '', email: me.user?.email || '', can_edit: !me.impersonation });
      setWidgetOriginsText((data.widget?.allowed_origins || []).join('\n'));
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Hesap ayarları yüklenemedi. Lütfen yeniden deneyin.');
    } finally {
      setSettingsLoading(false);
    }
  };
  const saveProfileName = async () => {
    if ((profile?.name || '').trim().length < 2) return toast.error('Ad soyad en az iki karakter olmalıdır.');
    setProfileBusy(true);
    try {
      const { data } = await agencyApi.patch('/marketplace/v1/extranet/profile', { name: profile.name.trim() });
      setProfile(current => ({ ...current, name: data.name }));
      toast.success('Profiliniz güncellendi.');
    } catch (err) { toast.error(err.response?.data?.detail || 'Profil güncellenemedi.'); }
    finally { setProfileBusy(false); }
  };
  const changePassword = async event => {
    event.preventDefault();
    if (passwordForm.next !== passwordForm.repeat) return toast.error('Yeni şifreler aynı değil.');
    setProfileBusy(true);
    try {
      const { data } = await agencyApi.post('/marketplace/v1/extranet/profile/password', {
        current_password: passwordForm.current, new_password: passwordForm.next,
      });
      // Other sessions are signed out; this one continues with the new token.
      localStorage.setItem('agency_token', data.token);
      setToken(data.token);
      setPasswordForm({ current: '', next: '', repeat: '' });
      toast.success('Şifreniz değişti. Diğer cihazlardaki oturumlar kapatıldı.');
    } catch (err) { toast.error(err.response?.data?.detail || 'Şifre değiştirilemedi.'); }
    finally { setProfileBusy(false); }
  };
  const updateAgencyField = (field, value) => setPortalSettings(current => ({
    ...current,
    agency: { ...current.agency, [field]: value },
  }));
  const updateNotification = (field, value) => setPortalSettings(current => ({
    ...current,
    notification_preferences: { ...current.notification_preferences, [field]: value },
  }));
  const savePortalSettings = async () => {
    if (!portalSettings?.agency?.name?.trim() || !portalSettings?.agency?.contact_email?.trim()) {
      return toast.error('Acente adı ve iletişim e-postası zorunludur.');
    }
    setSettingsSaving(true);
    try {
      await agencyApi.patch('/marketplace/v1/extranet/settings', {
        name: portalSettings.agency.name,
        contact_email: portalSettings.agency.contact_email,
        contact_phone: portalSettings.agency.contact_phone || '',
        address: portalSettings.agency.address || '',
        website: portalSettings.agency.website || '',
        notification_preferences: portalSettings.notification_preferences,
        allowed_widget_origins: widgetOriginsText.split(/\r?\n|,/).map(value => value.trim()).filter(Boolean),
        widget_brand_color: portalSettings.widget?.brand_color || '#047857',
      });
      setAgencyInfo(current => ({ ...current, name: portalSettings.agency.name, contact_email: portalSettings.agency.contact_email }));
      toast.success('Hesap ve portal ayarları kaydedildi.');
      await loadPortalSettings();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Ayarlar kaydedilemedi. Bilgileri kontrol edip yeniden deneyin.');
    } finally {
      setSettingsSaving(false);
    }
  };
  const statusLabels = {
    confirmed: 'Onaylandı',
    pending: 'Beklemede',
    checked_in: 'Giriş Yaptı',
    checked_out: 'Çıkış Yaptı',
    cancelled: 'İptal edildi'
  };
  const statusColors = {
    confirmed: 'bg-emerald-100 text-emerald-800',
    pending: 'bg-amber-100 text-amber-800',
    checked_in: 'bg-blue-100 text-blue-800',
    checked_out: 'bg-slate-100 text-slate-600',
    cancelled: 'bg-red-100 text-red-700'
  };

  // ─── LOGIN PAGE ───
  if (!token) {
    return <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 flex items-center justify-center p-4" data-testid="agency-portal-login">
        <Card className="w-full max-w-md overflow-hidden border-white/10 bg-white shadow-2xl">
          <div className="h-1.5 bg-gradient-to-r from-emerald-400 via-teal-500 to-sky-500" />
          <CardHeader className="text-center pb-2 pt-7">
            <div className="w-14 h-14 bg-gradient-to-br from-emerald-500 to-teal-700 rounded-2xl shadow-lg shadow-emerald-900/20 flex items-center justify-center mx-auto mb-3">
              <Building2 size={28} className="text-white" />
            </div>
            <CardTitle className="text-xl">Acente Portalı</CardTitle>
            <p className="text-sm text-slate-500 mt-1">{t('cm.pages_AgencyPortalDashboard.acente_hesabinizla_giris_yapin')}</p>
            <p className="text-xs text-slate-500 mt-2 leading-relaxed">
              Yetkinize bağlı sözleşmeli tesislere, canlı müsaitliğe ve rezervasyonlarınıza güvenli biçimde erişin.
            </p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <Label>E-posta</Label>
                <Input type="email" autoComplete="username" required value={loginForm.email} onChange={e => setLoginForm(p => ({
                ...p,
                email: e.target.value
              }))} data-testid="agency-login-email" placeholder="ornek@acente.com" />
              </div>
              <div>
                <Label>Şifre</Label>
                <Input type="password" autoComplete="current-password" required value={loginForm.password} onChange={e => setLoginForm(p => ({
                ...p,
                password: e.target.value
              }))} data-testid="agency-login-password" />
              </div>
              <Button type="submit" className="w-full bg-emerald-700 hover:bg-emerald-800" disabled={loginLoading} data-testid="agency-login-submit">
                {loginLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
                {t('cm.pages_AgencyPortalDashboard.giris_yap')}
              </Button>
            </form>
            <div className="mt-4 flex flex-col gap-2 text-sm">
              <Link to="/agency-recover" className="text-emerald-800 underline">Şifremi unuttum</Link>
              <Link to="/agency-activate" className="text-emerald-800 underline">Davetimi nasıl etkinleştiririm?</Link>
            </div>
          </CardContent>
        </Card>
      </div>;
  }

  if (profileLoading) return <div className="min-h-screen bg-slate-50 flex items-center justify-center" role="status">
    <div className="text-center text-slate-500"><Loader2 className="animate-spin mx-auto mb-3" size={28} />Acente hesabı doğrulanıyor…</div>
  </div>;

  if (profileError) return <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
    <Card className="max-w-md w-full"><CardContent className="py-8 text-center space-y-4">
      <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-red-50 text-red-700"><XCircle size={22} /></div>
      <div><h2 className="font-semibold text-slate-900">Hesap bilgileri doğrulanamadı</h2><p role="alert" className="mt-1 text-sm leading-6 text-red-700">{profileError}</p></div>
      <div className="flex justify-center gap-2">
        <Button variant="outline" onClick={handleLogout}>Oturumu kapat</Button>
        <Button onClick={() => { setProfileLoading(true); setProfileRevision(value => value + 1); }}>Tekrar dene</Button>
      </div>
    </CardContent></Card>
  </div>;

  // ─── MAIN PORTAL ───
  const workspaceLabel = portalMode === 'marketplace' ? 'Acente Extranet' : 'Otel bağlantılı portal';
  // Show only human-readable identity; never surface session/impersonation tokens (e.g. "SYR1:eyJ...").
  const isReadableIdentity = value => typeof value === 'string' && value.trim() !== '' && value.length <= 80 && !/^[A-Z0-9]+:/.test(value) && !/^eyJ/.test(value) && !/[A-Za-z0-9_-]{40,}/.test(value);
  const signedInIdentity = [agencyUser?.email, agencyUser?.name].find(isReadableIdentity) || '';
  return <div className="min-h-screen bg-[linear-gradient(180deg,#f8fafc_0%,#f1f5f9_48%,#f8fafc_100%)] text-slate-900" data-testid="agency-portal-dashboard">
      {impersonation?.active && <div className="sticky top-0 z-50 border-b border-amber-300 bg-amber-100 px-4 py-2 text-amber-950" role="status" data-testid="agency-impersonation-banner">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 text-sm sm:flex-row sm:items-center sm:justify-between">
          <span><strong>Süperadmin görünümü:</strong> {agencyInfo?.name || 'Acente'} hesabını parola kullanmadan görüntülüyorsunuz. Oturum 15 dakika içinde sona erer.</span>
          <Button variant="outline" size="sm" className="border-amber-400 bg-white hover:bg-amber-50" onClick={handleLogout}>Süperadmin paneline dön</Button>
        </div>
      </div>}
      {/* Header */}
      <header className="bg-white/90 border-b border-slate-200/80 sticky top-0 z-30 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 shrink-0 bg-gradient-to-br from-emerald-500 to-teal-700 rounded-xl shadow-sm flex items-center justify-center">
              <Building2 size={20} className="text-white" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <div className="font-semibold text-slate-900 text-sm sm:text-base truncate">{portalMode === 'marketplace' ? 'Acente Otel Satış Portalı' : (hotelInfo?.name || 'Otel Satış Portalı')}</div>
                <Badge variant="outline" className={portalMode === 'marketplace' ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-blue-300 bg-blue-50 text-blue-800'} data-testid="agency-workspace-type">
                  {workspaceLabel}
                </Badge>
              </div>
              <div className="text-xs text-slate-500" data-testid="agency-session-identity">
                {agencyInfo?.name || 'Acente'}{signedInIdentity ? ` · ${signedInIdentity}` : ''}
              </div>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={handleLogout} data-testid="agency-logout-btn" className="shrink-0 border-slate-200 bg-white hover:bg-slate-50">
            <LogOut size={14} className="mr-1" /> {t('cm.pages_AgencyPortalDashboard.cikis')}
          </Button>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-5 sm:py-8 space-y-6">
        <section className="relative overflow-hidden rounded-2xl border border-emerald-900/10 bg-gradient-to-br from-slate-950 via-slate-900 to-emerald-950 p-5 sm:p-7 text-white shadow-xl shadow-slate-900/10">
          <div className="absolute -right-14 -top-20 h-52 w-52 rounded-full bg-emerald-400/15 blur-3xl" />
          <div className="relative flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
            <div className="max-w-2xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium text-emerald-100"><Sparkles size={13} /> Acente satış merkezi</div>
              <h1 className="text-xl sm:text-2xl font-semibold tracking-tight">Konaklama satışlarınızı tek ekrandan yönetin</h1>
              <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">Canlı müsaitlik ve sözleşmeli fiyatlarla arama yapın, rezervasyonları izleyin ve finansal mutabakatı kolayca yönetin.</p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/10 px-3 py-2"><BadgeCheck size={14} className="text-emerald-300" /> Doğrulanmış erişim</span>
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/10 px-3 py-2"><Hotel size={14} className="text-sky-300" /> {hotels.length || (hotelInfo ? 1 : 0)} aktif tesis</span>
            </div>
          </div>
        </section>
        {notices.some(notice => !notice.read) && (
          <Card className="border-amber-200 bg-amber-50/60" data-testid="agency-notices">
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-base"><Bell size={17} className="text-amber-600" />Otellerden bildirimler</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {notices.filter(notice => !notice.read).slice(0, 5).map(notice => (
                <div key={notice.id} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-amber-200 bg-white p-3">
                  <div className="min-w-0"><div className="text-sm font-medium text-slate-900">{notice.title}</div><div className="text-xs leading-5 text-slate-600">{notice.message}</div><div className="text-[11px] text-slate-400">{String(notice.created_at || '').slice(0, 16).replace('T', ' ')}</div></div>
                  <Button variant="outline" size="sm" onClick={() => markNoticeRead(notice)}>Okundu</Button>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
        {/* Load on activation, not on click: Radix switches tabs on mousedown,
            the page height then changes and the mouseup may miss the trigger,
            so a click handler would not run (tab open, content empty). */}
        <Tabs defaultValue="search" className="w-full" onValueChange={value => ({
          reservations: loadReservations, content: () => loadContent(), finance: loadReconciliation,
          contracts: loadContracts, settings: loadPortalSettings,
        })[value]?.()}>
          <TabsList className={`grid w-full ${portalMode === 'marketplace' ? 'grid-cols-2 lg:grid-cols-6' : 'grid-cols-1 sm:grid-cols-3'} h-auto gap-1 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm`}>
            <TabsTrigger value="search" data-testid="tab-search" className="min-h-10 rounded-lg data-[state=active]:bg-slate-900 data-[state=active]:text-white">{t('cm.pages_AgencyPortalDashboard.musaitlik_ara')}</TabsTrigger>
            <TabsTrigger value="reservations" data-testid="tab-reservations" className="min-h-10 rounded-lg data-[state=active]:bg-slate-900 data-[state=active]:text-white">Rezervasyonlarım</TabsTrigger>
            <TabsTrigger value="content" data-testid="tab-content" className="min-h-10 rounded-lg data-[state=active]:bg-slate-900 data-[state=active]:text-white">Tesis Bilgileri</TabsTrigger>
            {portalMode === 'marketplace' && <TabsTrigger value="finance" className="min-h-10 rounded-lg data-[state=active]:bg-slate-900 data-[state=active]:text-white">Mutabakat</TabsTrigger>}
            {portalMode === 'marketplace' && <TabsTrigger value="contracts" className="min-h-10 rounded-lg data-[state=active]:bg-slate-900 data-[state=active]:text-white">Sözleşmeler</TabsTrigger>}
            {portalMode === 'marketplace' && <TabsTrigger value="settings" data-testid="tab-settings" className="min-h-10 rounded-lg data-[state=active]:bg-slate-900 data-[state=active]:text-white"><Settings size={14} className="mr-1.5" />Ayarlar</TabsTrigger>}
          </TabsList>

          {/* Search Tab */}
          <TabsContent value="search" className="mt-4 space-y-4">
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-4 sm:p-5">
                {/* Dates first: the native date picker needs room below the field. */}
                <div className="mb-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
                  <div className="space-y-1">
                    <Label className="text-xs">{t('cm.pages_AgencyPortalDashboard.giris_tarihi')}</Label>
                    <Input type="date" min={toDateInput(new Date())} value={searchForm.check_in} onChange={e => {
                      const checkIn = e.target.value;
                      const next = new Date(`${checkIn}T12:00:00`);
                      // While a date is typed segment by segment the value can be
                      // empty or invalid; only then-valid dates move check-out.
                      if (!checkIn || Number.isNaN(next.getTime())) {
                        setSearchForm(p => ({ ...p, check_in: checkIn }));
                        setAvailability(null);
                        return;
                      }
                      next.setDate(next.getDate() + 1);
                      setSearchForm(p => ({ ...p, check_in: checkIn, check_out: !p.check_out || p.check_out <= checkIn ? toDateInput(next) : p.check_out }));
                      setAvailability(null);
                    }} data-testid="search-checkin" className="w-full" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">{t('cm.pages_AgencyPortalDashboard.cikis_tarihi')}</Label>
                    <Input type="date" min={searchForm.check_in} value={searchForm.check_out} onChange={e => {
                      setSearchForm(p => ({ ...p, check_out: e.target.value })); setAvailability(null);
                    }} data-testid="search-checkout" className="w-full" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Yetişkin</Label>
                    <Input type="number" min={1} max={10} value={searchForm.adults} onChange={e => setSearchForm(p => ({
                    ...p,
                    adults: parseInt(e.target.value) || 1
                  }))} className="w-full" />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Çocuk</Label>
                    <Input type="number" min={0} max={10} value={searchForm.children} onChange={e => setSearchForm(p => ({
                      ...p,
                      children: Math.max(0, parseInt(e.target.value) || 0),
                      child_ages: resizeChildAges(p.child_ages, Math.max(0, parseInt(e.target.value) || 0)),
                    }))} className="w-full" />
                  </div>
                  {searchForm.child_ages.map((age, index) => <div className="space-y-1" key={`search-child-${index}`}>
                    <Label className="text-xs">{index + 1}. çocuk yaşı</Label>
                    <Input type="number" min={0} max={17} value={age} onChange={e => setSearchForm(p => ({
                      ...p,
                      child_ages: p.child_ages.map((value, childIndex) => childIndex === index ? Math.max(0, Math.min(17, parseInt(e.target.value) || 0)) : value),
                    }))} data-testid={`search-child-age-${index}`} className="w-full" />
                  </div>)}
                  <Button onClick={handleSearch} disabled={searchLoading} data-testid="search-availability-btn" className="gap-2 w-full min-h-10 bg-emerald-700 hover:bg-emerald-800 shadow-sm">
                    {searchLoading ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />}
                    {t('cm.pages_AgencyPortalDashboard.ara')} <ArrowRight size={14} />
                  </Button>
                </div>
                {portalMode === 'marketplace' && <div className="mb-5 space-y-4 rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-white p-4 sm:p-5">
                  <div>
                    <div className="font-semibold text-slate-900">Size uygun tesisleri bulun</div>
                    <p className="text-xs leading-5 text-emerald-800 flex items-start gap-1.5 mt-1"><ShieldCheck size={14} className="mt-0.5 shrink-0" />Arama sonuçlarında yalnızca sözleşmesi aktif ve seçtiğiniz tarihlerde satışa açık tesisler gösterilir.</p>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div><Label className="text-xs font-medium text-slate-600">Tesis veya bölge</Label><Input value={searchForm.q} onChange={e => setSearchForm(p => ({ ...p, q: e.target.value }))} placeholder="Tesis adı, bölge veya özellik" className="mt-1 bg-white" /></div>
                    <div><Label className="text-xs font-medium text-slate-600">Şehir</Label><Input value={searchForm.city} onChange={e => setSearchForm(p => ({ ...p, city: e.target.value }))} placeholder="Tüm şehirlerde ara" className="mt-1 bg-white" /></div>
                  </div>
                  <button type="button" onClick={() => setShowAdvancedFilters(value => !value)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 hover:border-emerald-300" aria-expanded={showAdvancedFilters}>
                    <span className="flex items-center gap-2"><SlidersHorizontal size={15} />İsteğe bağlı filtreler</span><span className="flex items-center gap-2 text-xs font-normal text-slate-500">{searchForm.amenities.length + searchForm.meal_plans.length + (searchForm.min_star_rating ? 1 : 0) + (searchForm.max_price ? 1 : 0) + (selectedTenantId ? 1 : 0) > 0 ? `${searchForm.amenities.length + searchForm.meal_plans.length + (searchForm.min_star_rating ? 1 : 0) + (searchForm.max_price ? 1 : 0) + (selectedTenantId ? 1 : 0)} seçili` : 'Filtre yok'}<ChevronDown size={15} className={`transition-transform ${showAdvancedFilters ? 'rotate-180' : ''}`} /></span>
                  </button>
                  {showAdvancedFilters && <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
                    <div><Label className="text-xs">Belirli tesis</Label><select value={selectedTenantId} onChange={e => { setSelectedTenantId(e.target.value); setAvailability(null); }} className="mt-1 flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"><option value="">Tüm sözleşmeli tesisler</option>{hotels.map(hotel => <option key={hotel.tenant_id} value={hotel.tenant_id}>{hotel.name}{hotel.city ? ` · ${hotel.city}` : ''}</option>)}</select></div>
                    <div><Label className="text-xs">Tesis ve oda özellikleri</Label><div className="mt-2 flex flex-wrap gap-2">{AMENITY_FILTERS.map(([value, label]) => <button type="button" key={value} onClick={() => setSearchForm(p => ({ ...p, amenities: toggleFilter(p.amenities, value) }))} className={`rounded-full border px-3 py-1.5 text-xs transition ${searchForm.amenities.includes(value) ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-emerald-400'}`}>{label}</button>)}</div></div>
                    <div><Label className="text-xs">Pansiyon tipi</Label><div className="mt-2 flex flex-wrap gap-2">{MEAL_FILTERS.map(([value, label]) => <button type="button" key={value} onClick={() => setSearchForm(p => ({ ...p, meal_plans: toggleFilter(p.meal_plans, value) }))} className={`rounded-full border px-3 py-1.5 text-xs transition ${searchForm.meal_plans.includes(value) ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-blue-400'}`}>{label}</button>)}</div></div>
                    <div className="grid grid-cols-2 gap-3"><div><Label className="text-xs">En az yıldız</Label><select value={searchForm.min_star_rating || ''} onChange={e => setSearchForm(p => ({ ...p, min_star_rating: e.target.value ? Number(e.target.value) : null }))} className="mt-1 flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"><option value="">Fark etmez</option>{[3,4,5].map(star => <option key={star} value={star}>{star} yıldız ve üzeri</option>)}</select></div><div><Label className="text-xs">Azami toplam fiyat</Label><Input type="number" min="0" value={searchForm.max_price || ''} onChange={e => setSearchForm(p => ({ ...p, max_price: e.target.value ? Number(e.target.value) : null }))} placeholder="Sınırsız" /></div></div>
                  </div>}
                </div>}
              </CardContent>
            </Card>

            {/* Results */}
            {availability && <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
                  <h3 className="text-sm font-semibold text-slate-800">{formatDate(availability.check_in)} – {formatDate(availability.check_out)}</h3>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">{availability.night_count} gece · {availability.adults + availability.children} misafir</span>
                </div>
                {availability.room_types.length === 0 ? <Card className="border-dashed"><CardContent className="py-10 text-center"><Search size={28} className="mx-auto mb-3 text-slate-300" /><div className="font-medium text-slate-700">Uygun tesis bulunamadı</div><p className="mt-1 text-sm text-slate-500">Tarihleri veya isteğe bağlı filtreleri değiştirerek yeniden arayabilirsiniz.</p></CardContent></Card> : availability.room_types.map(rt => <Card key={`${rt.tenant_id || 'hotel'}-${rt.room_type}-${rt.rate_plan_code || "legacy"}`} className="overflow-hidden border-slate-200 bg-white shadow-sm transition-all hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md" data-testid={`result-${rt.room_type}-${rt.rate_plan_code || "legacy"}`}>
                      <CardContent className="py-4">
                        {portalMode === 'marketplace' && <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-slate-100 pb-3"><Building2 size={15} className="text-emerald-600" /><span className="font-semibold text-slate-800">{rt.hotel_name}</span>{rt.hotel_city && <span className="text-xs text-slate-500 flex items-center gap-1"><MapPin size={11} />{rt.hotel_city}</span>}</div>}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                          <div className="flex items-center gap-4">
                            {rt.images?.[0] || rt.hotel_photos?.[0]
                              ? <AgencyImage src={rt.images?.[0] || rt.hotel_photos?.[0]} alt={rt.name || rt.room_type} className="h-20 w-28 shrink-0 rounded-xl object-cover ring-1 ring-slate-200" />
                              : <div className="w-12 h-12 shrink-0 bg-emerald-50 rounded-xl flex items-center justify-center ring-1 ring-emerald-100"><Bed size={20} className="text-emerald-700" /></div>}
                            <div>
                              <div className="font-semibold text-slate-800">{rt.name || rt.room_type}</div>
                              {rt.description && <div className="mt-0.5 line-clamp-2 max-w-xl text-xs text-slate-500">{rt.description}</div>}
                              <div className="text-xs text-slate-500 flex items-center gap-3 mt-0.5">
                                <span><Users size={10} className="inline mr-1" />En fazla {rt.capacity} kişi</span>
                                <span>{rt.available_rooms} oda müsait</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-wrap items-center justify-between sm:justify-end gap-3 sm:gap-4">
                            <div className="text-right">
                              <div className="text-lg font-bold text-slate-800">{formatMoney(rt.stay_total, rt.currency || availability.currency)}</div>
                              <div className="text-xs">Plan: {rt.rate_plan_code || 'Eski sözleşme'} · Pansiyon: {rt.meal_plan && rt.meal_plan !== 'unspecified' ? rt.meal_plan : 'Belirtilmemiş'}</div>
                              <div className="text-[11px] text-slate-500">{availability.night_count} gece · Gecelik {formatMoney(rt.base_price, rt.currency || availability.currency)}</div>
                              {rt.occupancy_pricing?.children_ages?.length > 0 && <div className="mt-1 text-[11px] text-violet-700" data-testid={`child-price-${rt.room_type}-${rt.rate_plan_code || "legacy"}`}>
                                Çocuk yaşları ({rt.occupancy_pricing.children_ages.join(', ')}) fiyata dahil
                                {rt.occupancy_pricing.child_supplement_nightly > 0 ? ` · ${formatMoney(rt.occupancy_pricing.child_supplement_nightly, rt.currency || availability.currency)}/gece çocuk farkı` : ' · ücretsiz'}
                              </div>}
                              {rt.has_contract && <Badge variant="outline" className="mt-1 text-[10px] border-emerald-300 text-emerald-700">Acente sözleşme fiyatı</Badge>}
                            </div>
                            <Button size="sm" onClick={() => openBookingForm(rt)} data-testid={`book-${rt.room_type}-${rt.rate_plan_code || "legacy"}`} className="gap-1 shrink-0 bg-slate-900 hover:bg-slate-800">
                              <Plus size={14} /> Rezerve Et
                            </Button>
                          </div>
                        </div>
                        {rt.amenities?.length > 0 && <div className="flex flex-wrap gap-1.5 mt-3">
                            {rt.amenities.map(a => <Badge key={a} variant="outline" className="text-[10px]">{a}</Badge>)}
                          </div>}
                      </CardContent>
                    </Card>)}
              </div>}
          </TabsContent>

          {/* Reservations Tab */}
          <TabsContent value="reservations" className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
              <div><h2 className="font-semibold text-slate-900">Rezervasyonlarınız</h2><p className="text-xs text-slate-500">Oluşturduğunuz rezervasyonları ve güncel durumlarını takip edin.</p></div>
              <Button variant="outline" size="sm" onClick={loadReservations} disabled={reservationsLoading}><RefreshCw size={14} className={reservationsLoading ? 'animate-spin mr-1' : 'mr-1'} />Yenile</Button>
            </div>
            {negotiations.filter(item => item.type === 'hotel_cancellation' && item.status === 'applying').map(item => <Card key={item.id} className="border-red-300 bg-red-50 shadow-sm" data-testid={`negotiation-resume-${item.id}`}><CardContent className="py-4"><div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div><div className="font-semibold text-red-900">İptal onayınız yarıda kaldı · {item.confirmation_code}</div><div className="text-xs leading-5 text-red-800 mt-1">Onayınız kaydedildi ancak işlem tamamlanamadı. Aynı iptali tamamlamak için tekrar deneyin; rezervasyon iki kez işlenmez.</div></div><Button size="sm" onClick={() => decideNegotiation(item, true)} className="bg-red-700 hover:bg-red-800 shrink-0">İptali Tamamla</Button></div></CardContent></Card>)}
            {negotiations.filter(item => item.status === 'awaiting_agency').map(item => <Card key={item.id} className="border-amber-300 bg-amber-50 shadow-sm"><CardContent className="py-4"><div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div><div className="font-semibold text-amber-950">İptal talebi değerlendirmenizi bekliyor · {item.confirmation_code}</div><div className="text-sm text-amber-900 mt-1">Otel açıklaması: {item.reason}</div><div className="text-xs leading-5 text-amber-700 mt-1">Rezervasyon siz onay vermeden iptal edilmez. Talebi kabul edebilir veya reddederek rezervasyonu koruyabilirsiniz.</div></div><div className="flex flex-wrap gap-2 shrink-0"><Button size="sm" variant="outline" onClick={() => decideNegotiation(item, false)}>Rezervasyonu Koru</Button><Button size="sm" onClick={() => decideNegotiation(item, true)} className="bg-amber-700 hover:bg-amber-800">İptali Onayla</Button></div></div></CardContent></Card>)}
            {reservationsLoading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-400" size={24} /></div> : reservations.length === 0 ? <Card><CardContent className="py-12 text-center text-slate-400">
                <ClipboardList size={40} className="mx-auto mb-3 opacity-40" />
                <p>{t('cm.pages_AgencyPortalDashboard.henuz_rezervasyonunuz_yok')}</p>
              </CardContent></Card> : reservations.map(r => <Card key={r.id} data-testid={`reservation-${r.id}`}>
                  <CardContent className="py-4">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-semibold text-slate-800">{r.guest_name || 'Misafir'}</div>
                        <div className="text-xs text-slate-600 mt-1 flex flex-wrap gap-x-3 gap-y-1">
                          <span className="font-mono">{r.confirmation_code || r.id}</span>
                          {r.integration_status && r.integration_status !== 'complete' && <span role="status">Entegrasyon tamamlanıyor ({r.integration_status}); rezervasyon kayıtlı.</span>}
                          {r.hotel_name && <span className="font-medium text-emerald-700">{r.hotel_name}</span>}
                          <span>{r.room_type || 'Oda tipi belirtilmemiş'}</span>
                          <span>{r.room_number ? `Oda ${r.room_number}` : 'Oda ataması bekliyor'}</span>
                        </div>
                        <div className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                          <CalendarDays size={12} />{formatDate(r.check_in)} – {formatDate(r.check_out)}
                        </div>
                      </div>
                      <div className="sm:text-right flex sm:block items-center justify-between gap-3">
                        <Badge className={`text-xs ${statusColors[r.status] || 'bg-slate-100'}`}>
                          {statusLabels[r.status] || r.status}
                        </Badge>
                        <div className="text-sm font-bold text-slate-700 sm:mt-1">{formatMoney(r.total_amount, r.currency || hotelInfo?.currency)}</div>
                        {portalMode === 'marketplace' && r.status !== 'cancelled' && <div className="text-xs text-slate-500" data-testid={`payment-summary-${r.id}`}>
                          Tahsil edilen {formatMoney(r.collected_amount || 0, r.currency || hotelInfo?.currency)} · Kalan {formatMoney(r.balance ?? r.total_amount, r.currency || hotelInfo?.currency)}
                          {r.payment_status && <span className="ml-1 font-medium text-slate-700">· {PAYMENT_STATUS_LABELS[r.payment_status] || r.payment_status}</span>}
                        </div>}
                        <div className="flex flex-wrap gap-1.5 mt-2 sm:justify-end">
                          <Button size="sm" variant="outline" onClick={() => printVoucher(r)}><Printer size={13} className="mr-1" />Voucher</Button>
                          {portalMode === 'marketplace' && <Button size="sm" variant="outline" onClick={() => openPaymentHistory(r)}><WalletCards size={13} className="mr-1" />Ödemeler</Button>}
                          {portalMode === 'marketplace' && <Button size="sm" variant="outline" onClick={() => openVoucherEmailDialog(r)}><Mail size={13} className="mr-1" />E-posta</Button>}
                          {!['cancelled', 'checked_in', 'checked_out'].includes(r.status) && portalMode === 'marketplace' && <Button size="sm" variant="outline" onClick={() => proposeModification(r)}>Değişiklik</Button>}
                          {!['cancelled', 'checked_in', 'checked_out'].includes(r.status) && portalMode === 'marketplace' && <Button size="sm" variant="outline" className="text-red-700" onClick={() => openCancellationDialog(r)}><XCircle size={13} className="mr-1" />İptal</Button>}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>)}
          </TabsContent>

          {portalMode === 'marketplace' && <TabsContent value="finance" className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm"><div><h2 className="font-semibold text-slate-900">Dönem mutabakat özeti</h2><p className="text-xs leading-5 text-slate-500">Giriş tarihine göre brüt satış, acente komisyonu, platform hizmet bedeli ve otellere aktarılacak net tutar. Otelin PMS'te yaptığı iptal, no-show ve tutar değişiklikleri yansıtılır.</p></div>
              <div className="flex flex-wrap items-end gap-2">
                <div><Label htmlFor="recon-start" className="text-xs">Başlangıç</Label><Input id="recon-start" type="date" value={reconPeriod.start} onChange={e => setReconPeriod(current => ({ ...current, start: e.target.value }))} className="h-9" /></div>
                <div><Label htmlFor="recon-end" className="text-xs">Bitiş</Label><Input id="recon-end" type="date" value={reconPeriod.end} onChange={e => setReconPeriod(current => ({ ...current, end: e.target.value }))} className="h-9" /></div>
                <Button size="sm" onClick={loadReconciliation}>Uygula</Button>
                <Button variant="outline" size="sm" onClick={downloadReconciliation}>CSV olarak indir</Button>
              </div></div>
            {reconciliation?.error ? <Card><CardContent className="py-8 text-center text-sm text-slate-600">{reconciliation.error} <Button size="sm" variant="outline" className="ml-2" onClick={loadReconciliation}>Yeniden dene</Button></CardContent></Card> : !reconciliation ? <Card><CardContent className="py-10 text-center text-slate-400"><Loader2 className="animate-spin mx-auto" /></CardContent></Card> : <>
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                {[['Brüt satış', 'gross_revenue', true], ['Acente komisyonu', 'commission', true], ['Platform hizmet bedeli', 'platform_fee', true], ['Satışların otele net tutarı', 'net_to_hotels', true], ['Rezervasyon', reconciliation.totals?.bookings, false]].map(([label, value, monetary], index) => <Card key={label} className={`overflow-hidden border-slate-200 shadow-sm ${index === 3 ? 'ring-1 ring-emerald-200' : ''} ${index === 4 ? 'col-span-2 lg:col-span-1' : ''}`}><div className={`h-1 ${index === 3 ? 'bg-emerald-500' : 'bg-slate-200'}`} /><CardContent className="pt-4"><div className="text-xs font-medium text-slate-500">{label}</div><div className={`mt-1 text-lg font-bold ${index === 3 ? 'text-emerald-700' : 'text-slate-900'}`}>{monetary ? currencyTotalsText(reconciliation.totals_by_currency, value) : value}</div></CardContent></Card>)}
              </div>
              {(reconciliation.totals?.cancelled > 0 || reconciliation.totals?.no_show > 0) && <p className="text-xs text-slate-500">Hesaba katılmayan: {reconciliation.totals?.cancelled || 0} iptal · {reconciliation.totals?.no_show || 0} no-show</p>}
              {(reconciliation.by_hotel || []).map(row => <Card key={`${row.tenant_id}-${row.currency}`}><CardContent className="py-4 flex items-center justify-between"><div><div className="font-medium">{row.hotel_name}</div><div className="text-xs text-slate-500">{row.bookings} rezervasyon · Komisyon {formatAgencyMoney(row.commission, row.currency)} · Platform {formatAgencyMoney(row.platform_fee, row.currency)}</div></div><div className="text-right"><div className="font-bold">{formatAgencyMoney(row.gross_revenue, row.currency)}</div><div className="text-xs text-emerald-700">Net {formatAgencyMoney(row.net_to_hotel, row.currency)}</div></div></CardContent></Card>)}
            </>}
            {creditOverview && creditOverview.length > 0 && <Card data-testid="agency-credit">
              <CardHeader className="pb-2"><CardTitle className="text-base">Kredi kullanımı</CardTitle><p className="text-xs text-slate-500">Otel başına açık net borcunuz (ekstre ödemeleri ve otelde tahsil edilen tutarlar düşülmüş) ve kalan kredi. Misafirin otele ödediği bakiye ayrıca rezervasyonda gösterilir.</p></CardHeader>
              <CardContent className="space-y-2">
                {creditOverview.map(hotel => <div key={hotel.tenant_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm">
                  <div><div className="font-medium">{hotel.hotel_name}</div><div className="text-xs text-slate-500">{hotel.contract_code}</div></div>
                  {!hotel.credit ? <span className="text-xs text-slate-500">Kredi limiti tanımsız</span>
                    : hotel.credit.error ? <span className="text-xs text-red-700">{hotel.credit.error}</span>
                    : <div className="text-right text-xs"><div>Kullanılan <strong>{formatMoney(hotel.credit.used, hotel.credit.currency)}</strong> / Limit {formatMoney(hotel.credit.limit, hotel.credit.currency)}</div><div className="text-emerald-700">Kalan {formatMoney(hotel.credit.available, hotel.credit.currency)}</div></div>}
                </div>)}
              </CardContent>
            </Card>}
            <Card data-testid="agency-statements">
              <CardHeader className="pb-2"><CardTitle className="text-base">Otellerin dönem ekstreleri</CardTitle><p className="text-xs text-slate-500">Otelin düzenlediği ekstreyi kontrol edip onaylayın veya satır belirterek itiraz edin.</p></CardHeader>
              <CardContent className="space-y-2">
                {statements.length === 0 ? <p className="text-sm text-slate-400">Henüz ekstre yok.</p> : statements.map(statement => (
                  <div key={statement.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
                    <div>
                      <div className="text-sm font-medium">{statement.number} · {statement.hotel_name}</div>
                      <div className="text-xs text-slate-500">{statement.period_start} – {statement.period_end} · {statement.status} · {Number(statement.outstanding) > 0 ? `Ödemeniz: ${formatAgencyMoney(statement.outstanding, statement.currency)}` : Number(statement.outstanding) < 0 ? `Otel ödeyecek: ${formatAgencyMoney(-statement.outstanding, statement.currency)}` : 'Bakiye yok'}</div>
                    </div>
                    {['issued', 'resolved'].includes(statement.status) && <div className="flex gap-2">
                      <Button size="sm" onClick={() => agreeStatement(statement)} disabled={statementBusy}>Mutabıkız</Button>
                      <Button size="sm" variant="outline" onClick={() => openDispute(statement)} disabled={statementBusy}>İtiraz et</Button>
                    </div>}
                    {['agreed', 'resolved'].includes(statement.status) && Number(statement.outstanding) > 0 && <Button size="sm" variant="outline" onClick={() => openPaymentNotice(statement)} data-testid={`report-payment-${statement.id}`}><WalletCards size={13} className="mr-1" />Ödeme bildir</Button>}
                    {(statement.payment_notices || []).length > 0 && <div className="w-full space-y-1 border-t pt-2">
                      {statement.payment_notices.map(notice => <div key={notice.id} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                        <span>{notice.paid_at} · {formatAgencyMoney(notice.amount, statement.currency)} · ref {notice.reference}</span>
                        <span className="flex items-center gap-2">{notice.has_proof && <button type="button" className="underline" onClick={() => openPaymentProof(statement, notice)}>Dekont</button>}<span className={notice.status === 'verified' ? 'text-emerald-700' : notice.status === 'rejected' ? 'text-red-700' : 'text-amber-700'}>{NOTICE_STATUS[notice.status] || notice.status}{notice.status === 'rejected' && notice.note ? `: ${notice.note}` : ''}</span></span>
                      </div>)}
                    </div>}
                  </div>
                ))}
              </CardContent>
            </Card>
          </TabsContent>}

          {portalMode === 'marketplace' && <TabsContent value="contracts" className="mt-4 space-y-4">
            <Card><CardHeader><CardTitle>Otel bazlı sözleşme teklifi</CardTitle></CardHeader><CardContent><p className="mb-4 text-sm text-slate-600">Komisyon her otelle ayrı kararlaştırılır. Teklif oranı satışta ancak otel onayladıktan sonra kullanılır.</p><form onSubmit={proposeContract} className="grid gap-3 md:grid-cols-3"><div><Label htmlFor="contract-rate">Teklif edilen komisyon (%)</Label><Input id="contract-rate" required type="number" min="0" max="100" step="1" inputMode="numeric" value={contractForm.commission_pct} onChange={event => { const raw = event.target.value; setContractForm(current => ({ ...current, commission_pct: raw === '' ? '' : String(Math.min(100, Math.max(0, Math.round(Number(raw))))) })); }} /></div><div><Label htmlFor="contract-payment">Ödeme vadesi</Label><select id="contract-payment" value={contractForm.payment_terms} onChange={event => setContractForm(current => ({ ...current, payment_terms: event.target.value }))} className="mt-1 flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"><option value="prepaid">Ön ödemeli</option><option value="on_arrival">Girişte</option><option value="net_7">7 gün</option><option value="net_15">15 gün</option><option value="net_30">30 gün</option></select></div><div><Label htmlFor="contract-from">Başlangıç</Label><Input id="contract-from" required type="date" value={contractForm.valid_from} onChange={event => setContractForm(current => ({ ...current, valid_from: event.target.value }))} /></div><div><Label htmlFor="contract-to">Bitiş</Label><Input id="contract-to" required type="date" value={contractForm.valid_to} onChange={event => setContractForm(current => ({ ...current, valid_to: event.target.value }))} /></div><div className="flex items-end"><Button type="submit" disabled={proposing || !selectedHotelIds.length} className="w-full bg-emerald-700 hover:bg-emerald-800" data-testid="propose-selected-hotels">{proposing && <Loader2 size={14} className="mr-2 animate-spin" />}Seçili otellere teklif gönder ({selectedHotelIds.length})</Button></div></form></CardContent></Card>
            <Card data-testid="hotel-candidates"><CardHeader className="pb-2"><CardTitle className="text-base">Oteller</CardTitle><p className="text-xs text-slate-500">Tüm Syroce otelleri listelenir. Fiyat, kontenjan ve fotoğraf galerisi otel sözleşmeyi onayladıktan sonra açılır.</p></CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {contractHotels.length === 0 && !contractsLoading && <p className="text-sm text-slate-400">Listelenecek otel yok.</p>}
                {contractHotels.map(hotel => {
                  const locked = ['pending', 'approved'].includes(hotel.contract_status);
                  const checked = selectedHotelIds.includes(hotel.tenant_id);
                  return (
                    <label key={hotel.tenant_id} className={`flex cursor-pointer flex-col overflow-hidden rounded-lg border ${checked ? 'border-emerald-500 ring-1 ring-emerald-300' : 'border-slate-200'} ${locked ? 'cursor-default opacity-70' : ''}`}>
                      {hotel.cover_photo ? <AgencyImage src={hotel.cover_photo} alt={hotel.hotel_name} className="h-28 w-full object-cover" /> : <div className="flex h-28 items-center justify-center bg-slate-100 text-slate-300"><Hotel size={28} /></div>}
                      <div className="space-y-1 p-3">
                        <div className="flex items-start justify-between gap-2">
                          <span className="font-semibold text-slate-900">{hotel.hotel_name}</span>
                          {locked ? <Badge className={hotel.contract_status === 'approved' ? 'bg-emerald-600' : 'bg-amber-500'}>{CONTRACT_STATUS_LABELS[hotel.contract_status]}</Badge>
                            : <input type="checkbox" checked={checked} onChange={() => setSelectedHotelIds(ids => (checked ? ids.filter(id => id !== hotel.tenant_id) : [...ids, hotel.tenant_id]))} aria-label={`${hotel.hotel_name} seç`} />}
                        </div>
                        <div className="text-xs text-slate-500">{[hotel.city, hotel.country].filter(Boolean).join(', ')}{hotel.star_rating ? ` · ${'★'.repeat(hotel.star_rating)}` : ''}</div>
                        {(hotel.meal_plans || []).length > 0 && <div className="text-xs text-slate-600">Pansiyon: {hotel.meal_plans.join(', ')}</div>}
                        {(hotel.room_type_names || []).length > 0 && <div className="text-xs text-slate-600">Odalar: {hotel.room_type_names.slice(0, 4).join(', ')}</div>}
                        {hotel.summary && <p className="line-clamp-3 text-xs text-slate-500">{hotel.summary}</p>}
                      </div>
                    </label>
                  );
                })}
              </CardContent>
            </Card>
            {contractsLoading ? <Card><CardContent className="py-10 text-center"><Loader2 className="mx-auto animate-spin" /></CardContent></Card> : contracts.map(contract => <Card key={contract.id}><CardContent className="flex flex-wrap items-center justify-between gap-3 py-4"><div><div className="font-semibold">{contract.hotel_name}</div><div className="text-xs text-slate-500">{contract.contract_code} · {formatDate(contract.valid_from)} – {formatDate(contract.valid_to)} · {PAYMENT_TERMS_LABELS[contract.payment_terms] || contract.payment_terms}</div></div><div className="text-right"><Badge className={contract.status === 'approved' ? 'bg-emerald-600' : contract.status === 'pending' ? 'bg-amber-500' : 'bg-slate-500'}>{contract.status === 'approved' ? 'Onaylandı' : contract.status === 'pending' ? 'Otel onayı bekleniyor' : (CONTRACT_STATUS_LABELS[contract.status] || contract.status)}</Badge><div className="mt-1 text-sm font-semibold">%{Math.round(Number(contract.commission_pct))} komisyon</div>{contract.status === 'pending' && (withdrawingId === contract.id
              ? <div className="mt-2 flex justify-end gap-2"><Button size="sm" variant="outline" disabled={withdrawBusy} onClick={() => setWithdrawingId(null)}>Vazgeç</Button><Button size="sm" variant="destructive" disabled={withdrawBusy} onClick={() => withdrawContract(contract)} data-testid={`confirm-withdraw-${contract.id}`}>Evet, geri çek</Button></div>
              : <Button size="sm" variant="outline" className="mt-2" onClick={() => setWithdrawingId(contract.id)} data-testid={`withdraw-${contract.id}`}>Teklifi geri çek</Button>)}</div></CardContent></Card>)}
          </TabsContent>}

          {/* Content Tab */}
          <TabsContent value="content" className="mt-4 space-y-4">
            {portalMode === 'marketplace' && <Card className="border-slate-200 shadow-sm"><CardContent className="py-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold text-slate-900">Tesis bilgileri</h2><p className="mt-1 text-xs text-slate-500">Sözleşmeli tesislerin oda tiplerini, özelliklerini ve iletişim bilgilerini inceleyin.</p></div><div className="w-full sm:w-80"><Label htmlFor="content-hotel-select" className="sr-only">Görüntülenecek tesis</Label><select id="content-hotel-select" value={contentTenantId} onChange={event => loadContent(event.target.value)} className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" data-testid="content-hotel-select"><option value="" disabled>Tesis seçin</option>{hotels.map(hotel => <option key={hotel.tenant_id} value={hotel.tenant_id}>{hotel.name}{hotel.city ? ` · ${hotel.city}` : ''}</option>)}</select></div></div></CardContent></Card>}
            {contentLoading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-400" size={24} /></div> : !content?.published ? <Card><CardContent className="py-12 text-center text-slate-400">
                <Eye size={40} className="mx-auto mb-3 opacity-40" />
                <p className="font-medium text-slate-700">Görüntülenecek tesis bilgisi bulunamadı</p>
                <p className="mt-1 text-sm">Sözleşmeli bir tesis seçin veya içerik paylaşımı için tesisle iletişime geçin.</p>
              </CardContent></Card> : <div className="space-y-4">
                <Card>
                  {content.hotel_content?.photos?.[0] || content.hotel_content?.images?.[0] ? <div className="grid h-56 grid-cols-3 gap-1 overflow-hidden rounded-t-xl bg-slate-100">
                    <AgencyImage src={(content.hotel_content.photos || content.hotel_content.images)[0]} alt={content.hotel_content?.hotel_name || 'Tesis'} className="col-span-2 h-full w-full object-cover" />
                    <div className="grid grid-rows-2 gap-1">{(content.hotel_content.photos || content.hotel_content.images).slice(1, 3).map((url, index) => <AgencyImage key={url} src={url} alt={`${content.hotel_content?.hotel_name || 'Tesis'} ${index + 2}`} className="h-full min-h-0 w-full object-cover" />)}</div>
                  </div> : null}
                  <CardHeader>
                    <CardTitle className="text-lg">{content.hotel_content?.hotel_name || 'Otel'}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {content.hotel_content?.description && <p className="text-sm text-slate-600">{content.hotel_content.description}</p>}
                    <div className="flex flex-wrap gap-4 text-sm text-slate-500">
                      {content.hotel_content?.address && <span className="flex items-center gap-1"><MapPin size={12} />{content.hotel_content.address}</span>}
                      {content.hotel_content?.phone && <span className="flex items-center gap-1"><Phone size={12} />{content.hotel_content.phone}</span>}
                      {content.hotel_content?.email && <span className="flex items-center gap-1"><Mail size={12} />{content.hotel_content.email}</span>}
                    </div>
                    {content.hotel_content?.amenities?.length > 0 && <div className="flex flex-wrap gap-1.5">
                        {content.hotel_content.amenities.map(a => <Badge key={a} variant="outline" className="text-xs">{a}</Badge>)}
                      </div>}
                  </CardContent>
                </Card>

                {content.hotel_content?.room_types?.length > 0 && <div>
                    <h3 className="font-medium text-slate-700 mb-2">{t('cm.pages_AgencyPortalDashboard.oda_tipleri')}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {content.hotel_content.room_types.map(rt => <Card key={rt.room_type} className="overflow-hidden">
                          {rt.images?.[0] && <AgencyImage src={rt.images[0]} alt={rt.name || rt.room_type} className="h-36 w-full object-cover" />}
                          <CardContent className="pt-4">
                            <div className="flex items-center gap-3 mb-2">
                              <Bed size={16} className="text-blue-500" />
                              <span className="font-medium text-sm">{rt.name || rt.room_type}</span>
                            </div>
                            {rt.description && <p className="text-xs text-slate-500 mb-2">{rt.description}</p>}
                            <div className="flex gap-4 text-xs text-slate-600">
                              <span>{rt.capacity} kişi</span>
                              <span>{formatMoney(rt.base_price, hotelInfo?.currency)} / gece</span>
                              {rt.bed_type && <span>{rt.bed_type}</span>}
                            </div>
                          </CardContent>
                        </Card>)}
                    </div>
                  </div>}

                {content.hotel_content?.services?.length > 0 && <div>
                    <h3 className="font-medium text-slate-700 mb-2">Hizmetler</h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                      {content.hotel_content.services.map((s, i) => <Card key={s.id || i}>
                          <CardContent className="pt-3 pb-3">
                            <div className="font-medium text-sm text-slate-800">{s.name}</div>
                            {s.description && <div className="text-xs text-slate-500">{s.description}</div>}
                          </CardContent>
                        </Card>)}
                    </div>
                  </div>}
              </div>}
          </TabsContent>

          {portalMode === 'marketplace' && <TabsContent value="settings" className="mt-4 space-y-4" data-testid="agency-settings-panel">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
              <div><h2 className="font-semibold text-slate-900">Hesap ve portal ayarları</h2><p className="text-xs leading-5 text-slate-500">Acente bilgilerinizi, bildirimleri, kullanıcıları ve web sitesi bağlantısını yönetin.</p></div>
              <Button onClick={savePortalSettings} disabled={settingsSaving || settingsLoading || !portalSettings} className="bg-emerald-700 hover:bg-emerald-800"><Save size={14} className="mr-1.5" />{settingsSaving ? 'Kaydediliyor…' : 'Değişiklikleri Kaydet'}</Button>
            </div>
            {settingsLoading ? <Card><CardContent className="py-12 text-center text-slate-500"><Loader2 className="mx-auto mb-2 animate-spin" />Ayarlar yükleniyor…</CardContent></Card> : portalSettings && <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {profile && <Card className="border-slate-200 shadow-sm xl:col-span-2" data-testid="agency-profile-card">
                <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Settings size={17} className="text-emerald-700" />Profilim</CardTitle></CardHeader>
                <CardContent className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="agency-profile-name">Ad soyad</Label>
                    <div className="flex gap-2"><Input id="agency-profile-name" value={profile.name || ''} disabled={!profile.can_edit} onChange={event => setProfile(current => ({ ...current, name: event.target.value }))} />
                      <Button type="button" variant="outline" disabled={!profile.can_edit || profileBusy} onClick={saveProfileName}>Kaydet</Button></div>
                    <p className="text-xs text-slate-500">Giriş e-postası: {profile.email || '—'}</p>
                    {!profile.can_edit && <p className="text-xs text-amber-700">Süperadmin önizlemesinde profil değiştirilemez.</p>}
                  </div>
                  <form onSubmit={changePassword} className="space-y-2">
                    <Label>Şifre değiştir</Label>
                    <Input type="password" autoComplete="current-password" placeholder="Mevcut şifre" required disabled={!profile.can_edit} value={passwordForm.current} onChange={event => setPasswordForm(f => ({ ...f, current: event.target.value }))} />
                    <Input type="password" autoComplete="new-password" placeholder="Yeni şifre (en az 12 karakter, büyük/küçük harf ve rakam)" required minLength={12} maxLength={72} disabled={!profile.can_edit} value={passwordForm.next} onChange={event => setPasswordForm(f => ({ ...f, next: event.target.value }))} />
                    <Input type="password" autoComplete="new-password" placeholder="Yeni şifre (tekrar)" required minLength={12} maxLength={72} disabled={!profile.can_edit} value={passwordForm.repeat} onChange={event => setPasswordForm(f => ({ ...f, repeat: event.target.value }))} />
                    <Button type="submit" variant="outline" disabled={!profile.can_edit || profileBusy}>Şifreyi değiştir</Button>
                  </form>
                </CardContent>
              </Card>}
              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Building2 size={17} className="text-emerald-700" />Acente bilgileri</CardTitle></CardHeader>
                <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2"><Label htmlFor="agency-settings-name">Acente unvanı</Label><Input id="agency-settings-name" value={portalSettings.agency.name} onChange={event => updateAgencyField('name', event.target.value)} /></div>
                  <div><Label htmlFor="agency-settings-email">İletişim e-postası</Label><Input id="agency-settings-email" type="email" value={portalSettings.agency.contact_email} onChange={event => updateAgencyField('contact_email', event.target.value)} /></div>
                  <div><Label htmlFor="agency-settings-phone">Telefon</Label><Input id="agency-settings-phone" type="tel" value={portalSettings.agency.contact_phone || ''} onChange={event => updateAgencyField('contact_phone', event.target.value)} /></div>
                  <div className="sm:col-span-2"><Label htmlFor="agency-settings-address">Adres</Label><Input id="agency-settings-address" value={portalSettings.agency.address || ''} onChange={event => updateAgencyField('address', event.target.value)} /></div>
                  <div className="sm:col-span-2"><Label htmlFor="agency-settings-website">Web sitesi</Label><Input id="agency-settings-website" type="url" placeholder="https://www.acenteniz.com" value={portalSettings.agency.website || ''} onChange={event => updateAgencyField('website', event.target.value)} /></div>
                </CardContent>
              </Card>

              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Bell size={17} className="text-amber-600" />Bildirim tercihleri</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {[
                    ['new_reservation', 'Yeni rezervasyonlar', 'Oluşturulan rezervasyon ve onay bildirimleri'],
                    ['reservation_change', 'Rezervasyon değişiklikleri', 'Tarih, oda ve durum değişiklikleri'],
                    ['cancellation_request', 'İptal görüşmeleri', 'Otel ile karşılıklı iptal talebi ve yanıtları'],
                    ['payment_reconciliation', 'Finans ve mutabakat', 'Tahsilat ve dönem mutabakat bildirimleri'],
                    ['contract_updates', 'Sözleşme kararları', 'Otelin sözleşme onayı, reddi ve feshi'],
                  ].map(([key, label, description]) => <label key={key} className="flex cursor-pointer items-start justify-between gap-4 rounded-lg border border-slate-200 p-3 hover:border-emerald-300"><span><span className="block text-sm font-medium text-slate-800">{label}</span><span className="block text-xs leading-5 text-slate-500">{description}</span></span><input type="checkbox" className="mt-1 h-4 w-4 accent-emerald-700" checked={portalSettings.notification_preferences?.[key] !== false} onChange={event => updateNotification(key, event.target.checked)} /></label>)}
                </CardContent>
              </Card>

              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Users size={17} className="text-sky-700" />Kullanıcılar</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {(portalSettings.users || []).map(user => <div key={user.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3"><div className="min-w-0"><div className="truncate text-sm font-medium text-slate-900">{user.name || 'İsimsiz kullanıcı'}</div><div className="truncate text-xs text-slate-500">{user.email}</div></div><Badge variant="outline" className="shrink-0">{user.role === 'marketplace_agent' ? 'Acente kullanıcısı' : user.role}</Badge></div>)}
                  {(portalSettings.users || []).length === 0 && <p className="py-6 text-center text-sm text-slate-500">Aktif kullanıcı bulunamadı.</p>}
                  <p className="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600"><ShieldCheck size={14} className="mr-1 inline text-emerald-700" />Kullanıcı ekleme, rol değiştirme ve erişim kapatma işlemleri denetim kaydıyla süperadmin üzerinden yürütülür.</p>
                </CardContent>
              </Card>

              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Globe2 size={17} className="text-indigo-700" />Web sitesi ve API</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div><Label htmlFor="agency-widget-origins">İzinli web sitesi adresleri</Label><textarea id="agency-widget-origins" className="mt-1 flex min-h-24 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" placeholder={'https://www.acenteniz.com\nhttps://rezervasyon.acenteniz.com'} value={widgetOriginsText} onChange={event => setWidgetOriginsText(event.target.value)} /><p className="mt-1 text-xs leading-5 text-slate-500">Her satıra bir HTTPS adresi yazın. Widget yalnız bu alan adlarında çalışır.</p></div>
                  <div><Label htmlFor="agency-widget-color">Widget ana rengi</Label><div className="mt-1 flex items-center gap-2"><input id="agency-widget-color" type="color" className="h-10 w-14 rounded border border-slate-300 bg-white p-1" value={portalSettings.widget?.brand_color || '#047857'} onChange={event => setPortalSettings(current => ({ ...current, widget: { ...current.widget, brand_color: event.target.value } }))} /><code className="rounded bg-slate-100 px-2 py-1 text-xs">{portalSettings.widget?.brand_color || '#047857'}</code></div></div>
                  {portalSettings.widget?.token && <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3"><div className="text-sm font-semibold text-indigo-950">Web sitenize ekleme kodu</div><p className="mt-1 text-xs leading-5 text-indigo-800">Önce izinli adresleri kaydedin, ardından bu kodu rezervasyon sayfanızda görünmesini istediğiniz yere yapıştırın.</p><code className="mt-3 block max-h-28 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">{`<iframe src="${window.location.origin}/agency-widget?key=${portalSettings.widget.token}" title="Otel rezervasyonu" width="100%" height="760" style="border:0;border-radius:16px" loading="lazy" referrerpolicy="strict-origin"></iframe>`}</code><Button type="button" size="sm" variant="outline" className="mt-3 bg-white" onClick={async () => { await navigator.clipboard.writeText(`<iframe src="${window.location.origin}/agency-widget?key=${portalSettings.widget.token}" title="Otel rezervasyonu" width="100%" height="760" style="border:0;border-radius:16px" loading="lazy" referrerpolicy="strict-origin"></iframe>`); toast.success('Widget kodu kopyalandı'); }}><ClipboardList size={14} className="mr-1.5" />Kodu kopyala</Button></div>}
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3"><div className="flex items-center gap-2 text-sm font-medium text-slate-800"><KeyRound size={15} />API erişimi</div>{(portalSettings.api_keys || []).map(key => <div key={key.id} className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs"><code className="text-slate-700">{key.key_prefix}</code><span className="text-slate-500">{key.usage_count || 0} kullanım</span></div>)}<p className="mt-2 text-xs leading-5 text-slate-500">Güvenlik nedeniyle anahtarların tamamı gösterilmez. Yenileme işlemi süperadmin tarafından yapılır.</p></div>
                </CardContent>
              </Card>
            </div>}
          </TabsContent>}
        </Tabs>
      </div>

      {/* Booking Dialog */}
      <Dialog open={showBookingForm} onOpenChange={setShowBookingForm}>
        <DialogContent className="max-w-md" data-testid="booking-form-dialog">
          <DialogHeader>
            <DialogTitle>{t('cm.pages_AgencyPortalDashboard.rezervasyon_olustur')}</DialogTitle>
            <p className="text-sm text-slate-500">{selectedRoomType?.room_type} · {formatDate(searchForm.check_in)} – {formatDate(searchForm.check_out)}</p>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>{t('cm.pages_AgencyPortalDashboard.misafir_adi')}</Label>
              <Input required autoFocus value={bookingForm.guest_name} onChange={e => setBookingForm(p => ({
              ...p,
              guest_name: e.target.value
            }))} data-testid="booking-guest-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>E-posta</Label>
                <Input type="email" value={bookingForm.guest_email} onChange={e => setBookingForm(p => ({
                ...p,
                guest_email: e.target.value
              }))} />
              </div>
              <div>
                <Label>Telefon</Label>
                <Input type="tel" value={bookingForm.guest_phone} onChange={e => setBookingForm(p => ({
                ...p,
                guest_phone: e.target.value
              }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Yetişkin</Label>
                <Input type="number" value={bookingForm.adults} readOnly aria-describedby="quoted-occupancy-note" />
              </div>
              <div>
                <Label>Çocuk</Label>
                <Input type="number" value={bookingForm.children} readOnly aria-describedby="quoted-occupancy-note" />
              </div>
            </div>
            {bookingForm.child_ages.length > 0 && <div className="grid grid-cols-2 gap-3">
              {bookingForm.child_ages.map((age, index) => <div key={`booking-child-${index}`}>
                <Label>{index + 1}. çocuk yaşı</Label>
                <Input type="number" value={age} readOnly data-testid={`booking-child-age-${index}`} aria-describedby="quoted-occupancy-note" />
              </div>)}
            </div>}
            <p id="quoted-occupancy-note" className="text-xs text-slate-500">Kişi ve çocuk yaşları arama fiyatına dahildir. Değiştirmek için aramaya dönün.</p>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3" data-testid="booking-amount">
              <div className="flex items-center justify-between gap-3"><span className="text-sm text-emerald-900">Konaklama toplamı</span><strong className="text-emerald-900">{formatMoney(bookingForm.total_amount, availability?.currency || hotelInfo?.currency)}</strong></div>
              <p className="mt-1 text-xs text-emerald-700">Seçilen {availability?.night_count || 1} gece için güncel acente fiyatı.</p>
            </div>
            <div>
              <Label>{t('cm.pages_AgencyPortalDashboard.ozel_istek')}</Label>
              <textarea className="flex min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={bookingForm.special_requests} onChange={e => setBookingForm(p => ({
              ...p,
              special_requests: e.target.value
            }))} maxLength={1000} placeholder={t('cm.pages_AgencyPortalDashboard.erken_giris_deniz_manzarasi')} />
            </div>
            <div className="flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-emerald-600" />Onay sırasında güncel müsaitlik ve fiyat yeniden kontrol edilir. Böylece rezervasyonunuz doğru tesis ve oda tipi için güvenle oluşturulur.</div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBookingForm(false)}>{t('cm.pages_AgencyPortalDashboard.iptal')}</Button>
            <Button onClick={handleBooking} disabled={bookingLoading} data-testid="confirm-booking-btn">
              {bookingLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
              Rezervasyonu Oluştur
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(modificationTarget)} onOpenChange={open => !open && !modificationLoading && setModificationTarget(null)}>
        <DialogContent className="max-w-md" data-testid="agency-modification-dialog">
          <DialogHeader>
            <DialogTitle>Değişiklik talebi gönder</DialogTitle>
            <p className="text-sm text-slate-500">
              {modificationTarget?.confirmation_code || modificationTarget?.id} için talep otele iletilir. Otel onaylayana kadar mevcut rezervasyon geçerlidir.
            </p>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3 py-2">
            <div><Label htmlFor="agency-mod-check-in">Yeni giriş</Label><Input id="agency-mod-check-in" type="date" value={modificationForm.check_in} onChange={e => setModificationForm(f => ({ ...f, check_in: e.target.value }))} /></div>
            <div><Label htmlFor="agency-mod-check-out">Yeni çıkış</Label><Input id="agency-mod-check-out" type="date" min={modificationForm.check_in} value={modificationForm.check_out} onChange={e => setModificationForm(f => ({ ...f, check_out: e.target.value }))} /></div>
            <div><Label htmlFor="agency-mod-room-type">Oda tipi</Label><Input id="agency-mod-room-type" value={modificationForm.room_type} onChange={e => setModificationForm(f => ({ ...f, room_type: e.target.value }))} /></div>
            <div><Label htmlFor="agency-mod-rate-plan">Fiyat planı</Label><Input id="agency-mod-rate-plan" placeholder="RO, BB…" value={modificationForm.rate_plan_code} onChange={e => setModificationForm(f => ({ ...f, rate_plan_code: e.target.value }))} /></div>
            <div className="col-span-2"><Label htmlFor="agency-mod-reason">Gerekçe</Label>
              <textarea id="agency-mod-reason" className="flex min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={modificationForm.reason} maxLength={500} placeholder="En az 5 karakterle değişiklik gerekçesini yazın" onChange={e => setModificationForm(f => ({ ...f, reason: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModificationTarget(null)} disabled={modificationLoading}>Vazgeç</Button>
            <Button onClick={submitModification} disabled={modificationLoading || modificationForm.reason.trim().length < 5} data-testid="submit-agency-modification">
              {modificationLoading && <Loader2 className="animate-spin mr-2" size={14} />}Talebi Gönder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(negotiationDecision)} onOpenChange={open => !open && !negotiationLoading && setNegotiationDecision(null)}>
        <DialogContent className="max-w-md" data-testid="agency-negotiation-dialog">
          <DialogHeader>
            <DialogTitle>{negotiationDecision?.accept ? 'Otelin iptal talebini kabul et' : 'Otelin iptal talebini reddet'}</DialogTitle>
            <p className="text-sm text-slate-500">
              {negotiationDecision?.accept ? 'Kabul ederseniz rezervasyon karşılıklı olarak iptal edilir.' : 'Reddederseniz rezervasyon korunur; gerekçeniz otele iletilir.'}
            </p>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="agency-negotiation-note">{negotiationDecision?.accept ? 'Kabul notu (isteğe bağlı)' : 'Reddetme gerekçesi'}</Label>
            <textarea id="agency-negotiation-note" className="flex min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={negotiationNote} maxLength={500} onChange={e => setNegotiationNote(e.target.value)} autoFocus />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNegotiationDecision(null)} disabled={negotiationLoading}>Vazgeç</Button>
            <Button variant={negotiationDecision?.accept ? 'default' : 'destructive'} onClick={submitNegotiationDecision} disabled={negotiationLoading || (!negotiationDecision?.accept && negotiationNote.trim().length < 5)} data-testid="submit-agency-negotiation">
              {negotiationLoading && <Loader2 className="animate-spin mr-2" size={14} />}{negotiationDecision?.accept ? 'Kabul Et' : 'Reddet'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(disputeTarget)} onOpenChange={open => !open && !statementBusy && setDisputeTarget(null)}>
        <DialogContent className="max-w-lg" data-testid="agency-dispute-dialog">
          <DialogHeader>
            <DialogTitle>{disputeTarget?.number} ekstresine itiraz</DialogTitle>
            <p className="text-sm text-slate-500">İtiraz ettiğiniz rezervasyonları işaretleyin ve gerekçenizi yazın.</p>
          </DialogHeader>
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {(disputeTarget?.lines || []).map(line => (
              <label key={line.booking_id} className="flex items-center gap-2 rounded border p-2 text-xs">
                <input type="checkbox" checked={disputeIds.includes(line.booking_id)} onChange={() => setDisputeIds(ids => ids.includes(line.booking_id) ? ids.filter(id => id !== line.booking_id) : [...ids, line.booking_id])} />
                <span className="flex-1">{line.confirmation_code} · {line.check_in} · {line.guest_name} · {line.status}</span>
                <span>{formatAgencyMoney(line.gross, disputeTarget.currency)}</span>
              </label>
            ))}
          </div>
          <textarea className="min-h-20 w-full rounded-md border p-2 text-sm" placeholder="İtiraz gerekçesi (en az 5 karakter)" value={disputeReason} maxLength={1000} onChange={e => setDisputeReason(e.target.value)} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisputeTarget(null)} disabled={statementBusy}>Vazgeç</Button>
            <Button variant="destructive" onClick={submitDispute} disabled={statementBusy || disputeReason.trim().length < 5}>İtirazı gönder</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(cancelTarget)} onOpenChange={open => !open && !cancelLoading && setCancelTarget(null)}>
        <DialogContent className="max-w-md" data-testid="agency-cancellation-dialog">
          <DialogHeader>
            <DialogTitle>İptal talebi gönder</DialogTitle>
            <p className="text-sm text-slate-500">
              {cancelTarget?.confirmation_code || cancelTarget?.id} için talep otele iletilir. Otel kabul edene kadar rezervasyon ve kontenjan korunur.
            </p>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="agency-cancellation-reason">İptal gerekçesi</Label>
            <textarea
              id="agency-cancellation-reason"
              className="flex min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={cancelReason}
              onChange={event => setCancelReason(event.target.value)}
              maxLength={500}
              placeholder="En az 5 karakterle iptal gerekçesini yazın"
              autoFocus
              data-testid="agency-cancellation-reason"
            />
            <p className="text-xs text-slate-500">Bu açıklama otel tarafındaki onay ekranında görüntülenir.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelTarget(null)} disabled={cancelLoading}>Vazgeç</Button>
            <Button
              variant="destructive"
              onClick={cancelReservation}
              disabled={cancelLoading || cancelReason.trim().length < 5}
              data-testid="submit-agency-cancellation"
            >
              {cancelLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : <XCircle className="mr-2" size={14} />}
              İptal Talebini Gönder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(paymentHistory)} onOpenChange={open => !open && setPaymentHistory(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Ödemeler · {paymentHistory?.reservation?.confirmation_code}</DialogTitle></DialogHeader>
          {paymentHistory?.loading ? <Loader2 className="mx-auto animate-spin" /> : paymentHistory?.error ? <p className="text-sm text-red-700">{paymentHistory.error}</p> : paymentHistory && <div className="space-y-3" data-testid="payment-history">
            <div className="grid grid-cols-3 gap-2 text-center text-sm">
              <div className="rounded-lg border p-2"><div className="text-xs text-slate-500">Rezervasyon</div><div className="font-semibold">{formatMoney(paymentHistory.total_amount, paymentHistory.currency)}</div></div>
              <div className="rounded-lg border p-2"><div className="text-xs text-slate-500">Tahsil edilen</div><div className="font-semibold">{formatMoney(paymentHistory.collected_amount, paymentHistory.currency)}</div></div>
              <div className="rounded-lg border p-2"><div className="text-xs text-slate-500">Kalan</div><div className="font-semibold">{formatMoney(paymentHistory.balance ?? paymentHistory.total_amount, paymentHistory.currency)}</div></div>
            </div>
            {paymentHistory.payment_status && <p className="text-xs text-slate-600">Durum: <strong>{PAYMENT_STATUS_LABELS[paymentHistory.payment_status] || paymentHistory.payment_status}</strong>{paymentHistory.transferred_amount > 0 && ` · Cari hesaba aktarılan ${formatMoney(paymentHistory.transferred_amount, paymentHistory.currency)} (tahsil edilmedi)`}</p>}
            {(paymentHistory.payments || []).length === 0 ? <p className="text-sm text-slate-500">Bu rezervasyon için henüz ödeme kaydı yok.</p> : <div className="divide-y rounded-lg border">
              {paymentHistory.payments.map((payment, index) => <div key={index} className={`flex items-center justify-between px-3 py-2 text-sm ${payment.voided ? 'text-slate-400 line-through' : ''}`}>
                <span>{payment.date ? formatDate(String(payment.date).slice(0, 10)) : '—'} · {payment.label}{payment.voided ? ' (iptal edildi)' : ''}</span>
                <span className={payment.kind === 'refund' ? 'text-red-700' : ''}>{payment.kind === 'refund' ? '−' : ''}{formatMoney(payment.amount, payment.currency)}</span>
              </div>)}
            </div>}
          </div>}
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(paymentNotice)} onOpenChange={open => !open && !paymentNoticeBusy && setPaymentNotice(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Ödeme bildir · {paymentNotice?.statement?.number}</DialogTitle></DialogHeader>
          {paymentNotice && <form onSubmit={submitPaymentNotice} className="space-y-3" data-testid="payment-notice-form">
            <p className="text-xs text-slate-500">Bildirim otel doğrulayana kadar bakiyenizi ve kredinizi değiştirmez.</p>
            <div className="grid grid-cols-2 gap-3">
              <div><Label htmlFor="notice-amount">Tutar ({paymentNotice.statement.currency})</Label><Input id="notice-amount" type="number" min="0.01" step="0.01" required value={paymentNotice.amount} onChange={e => setPaymentNotice(n => ({ ...n, amount: e.target.value }))} /></div>
              <div><Label htmlFor="notice-date">Ödeme tarihi</Label><Input id="notice-date" type="date" required max={toDateInput(new Date())} value={paymentNotice.paid_at} onChange={e => setPaymentNotice(n => ({ ...n, paid_at: e.target.value }))} /></div>
            </div>
            <div><Label htmlFor="notice-ref">Banka referansı / açıklama</Label><Input id="notice-ref" required minLength={3} maxLength={120} value={paymentNotice.reference} onChange={e => setPaymentNotice(n => ({ ...n, reference: e.target.value }))} /></div>
            <div><Label htmlFor="notice-method">Yöntem</Label><select id="notice-method" className="mt-1 flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" value={paymentNotice.method} onChange={e => setPaymentNotice(n => ({ ...n, method: e.target.value }))}><option value="bank_transfer">Havale / EFT</option><option value="card">Kart</option><option value="cash">Nakit</option><option value="other">Diğer</option></select></div>
            <div><Label htmlFor="notice-proof">Dekont (PDF, JPG, PNG — en fazla 5 MB)</Label><Input id="notice-proof" type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={e => setPaymentNotice(n => ({ ...n, file: e.target.files?.[0] || null }))} /></div>
            <DialogFooter><Button type="button" variant="outline" disabled={paymentNoticeBusy} onClick={() => setPaymentNotice(null)}>Vazgeç</Button><Button type="submit" disabled={paymentNoticeBusy}>{paymentNoticeBusy ? 'Gönderiliyor…' : 'Bildir'}</Button></DialogFooter>
          </form>}
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(voucherEmailTarget)} onOpenChange={open => !open && !voucherEmailLoading && setVoucherEmailTarget(null)}>
        <DialogContent className="max-w-md" data-testid="voucher-email-dialog">
          <DialogHeader>
            <DialogTitle>Voucher'ı e-posta ile gönder</DialogTitle>
            <p className="text-sm text-slate-500">
              {voucherEmailTarget?.confirmation_code || voucherEmailTarget?.id} rezervasyonunun belgesi e-posta içeriğinde belirtilen adrese gönderilir. PDF için yazdır/indir düğmesini kullanın.
            </p>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="voucher-email-address">Alıcı e-posta adresi</Label>
            <Input
              id="voucher-email-address"
              type="email"
              value={voucherEmail}
              onChange={event => setVoucherEmail(event.target.value)}
              placeholder="ornek@eposta.com"
              autoComplete="email"
              autoFocus
              data-testid="voucher-email-address"
            />
            <p className="text-xs text-slate-500">Gönderim sonucu ekranda açıkça bildirilecektir.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setVoucherEmailTarget(null)} disabled={voucherEmailLoading}>Vazgeç</Button>
            <Button
              onClick={emailVoucher}
              disabled={voucherEmailLoading || !/^\S+@\S+\.\S+$/.test(voucherEmail.trim())}
              data-testid="send-voucher-email"
            >
              {voucherEmailLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : <Mail className="mr-2" size={14} />}
              E-posta Gönder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>;
};
export default AgencyPortalDashboard;
