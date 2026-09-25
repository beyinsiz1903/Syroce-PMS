import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Search, CalendarDays, Users, Bed, Plus, Loader2, Building2, LogOut, ClipboardList, Eye, Phone, Mail, MapPin, RefreshCw, ShieldCheck, Printer, XCircle, WalletCards, SlidersHorizontal, ChevronDown } from 'lucide-react';
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
const toggleFilter = (values, value) => values.includes(value) ? values.filter(item => item !== value) : [...values, value];
const resizeChildAges = (ages, count) => Array.from({ length: count }, (_, index) => ages?.[index] ?? 0);
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
  const [portalMode, setPortalMode] = useState(localStorage.getItem('agency_portal_mode') || 'hotel');
  const [hotels, setHotels] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState(localStorage.getItem('agency_selected_hotel') || '');
  const [profileLoading, setProfileLoading] = useState(Boolean(localStorage.getItem('agency_token')));
  const [profileError, setProfileError] = useState('');
  const [profileRevision, setProfileRevision] = useState(0);

  // Login
  const [loginForm, setLoginForm] = useState({
    email: '',
    password: ''
  });
  const [loginLoading, setLoginLoading] = useState(false);

  // Content
  const [content, setContent] = useState(null);
  const [contentLoading, setContentLoading] = useState(false);

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
  const [reservationsLoading, setReservationsLoading] = useState(false);
  const [reconciliation, setReconciliation] = useState(null);
  const [negotiations, setNegotiations] = useState([]);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelLoading, setCancelLoading] = useState(false);
  const [voucherEmailTarget, setVoucherEmailTarget] = useState(null);
  const [voucherEmail, setVoucherEmail] = useState('');
  const [voucherEmailLoading, setVoucherEmailLoading] = useState(false);

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
      toast.success('Giriş başarılı');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Giriş hatası');
    } finally {
      setLoginLoading(false);
    }
  };
  const handleLogout = () => {
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
    setProfileLoading(false);
    setProfileError('');
  };

  // Load profile on mount if token exists
  useEffect(() => {
    if (!token) return;
    const loadProfile = async () => {
      try {
        if (portalMode === 'marketplace') {
          const { data } = await agencyApi.get('/marketplace/v1/extranet/profile');
          const availableHotels = data.hotels || [];
          // Discovery starts from the whole contracted portfolio. A hotel is
          // selected only when the agent explicitly narrows the search or books.
          const allowedSelected = '';
          setAgencyInfo(data.agency || null);
          setHotels(availableHotels);
          setSelectedTenantId(allowedSelected);
          localStorage.removeItem('agency_selected_hotel');
          const selected = availableHotels.find(h => h.tenant_id === allowedSelected);
          setHotelInfo(selected ? { name: selected.name, currency: selected.currency || 'TRY', ...selected } : null);
        } else {
          const { data } = await agencyApi.get('/agency-portal/profile');
          setAgencyUser(data.user || null);
          setAgencyInfo(data.agency);
          setHotelInfo(data.hotel || null);
        }
        setProfileError('');
      } catch (err) {
        if (err.response?.status === 401 || err.response?.status === 403) handleLogout();
        else setProfileError('Acente hesabı doğrulanamadı. Bağlantınızı kontrol edip tekrar deneyin.');
      } finally {
        setProfileLoading(false);
      }
    };
    loadProfile();
  }, [token, profileRevision, portalMode]);

  // Load content
  const loadContent = async () => {
    setContentLoading(true);
    try {
      if (portalMode === 'marketplace') {
        if (!selectedTenantId) return setContent({ published: false, hotel_content: null });
        const { data } = await agencyApi.get(`/marketplace/v1/hotels/${encodeURIComponent(selectedTenantId)}`);
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
      toast.error('Otel bilgileri yüklenemedi');
    } finally {
      setContentLoading(false);
    }
  };

  // Search availability
  const handleSearch = async () => {
    if (!searchForm.check_in || !searchForm.check_out) return toast.error('Tarih seçin');
    if (searchForm.check_out <= searchForm.check_in) return toast.error('Çıkış tarihi girişten sonra olmalıdır');
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
      toast.error(err.response?.data?.detail || 'Arama hatası');
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
    if (bookingForm.guest_name.trim().length < 2) return toast.error('Misafir adı en az 2 karakter olmalıdır');
    if (bookingForm.adults + bookingForm.children > Number(selectedRoomType?.capacity || 0)) {
      return toast.error('Misafir sayısı seçilen odanın kapasitesini aşıyor');
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
      };
      let response;
      if (portalMode === 'marketplace') {
        response = await agencyApi.post('/marketplace/v1/reservations', {
          ...payload,
          tenant_id: selectedRoomType.tenant_id,
          room_type: selectedRoomType.room_type,
          total_amount: bookingForm.total_amount,
          idempotency_key: bookingForm.idempotency_key,
        });
      } else {
        response = await agencyApi.post('/agency-portal/reservations', {
          ...payload,
          room_type_id: selectedRoomType.room_type,
        });
      }
      toast.success(response.data.message || `Rezervasyon oluşturuldu: ${response.data.reservation?.confirmation_code || ''}`);
      setShowBookingForm(false);
      setAvailability(null);
      loadReservations();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Rezervasyon hatası');
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
      toast.error('Rezervasyonlar yüklenemedi');
    } finally {
      setReservationsLoading(false);
    }
  };
  const decideNegotiation = async (proposal, accept) => {
    const responseNote = window.prompt(accept ? 'Kabul notu (isteğe bağlı)' : 'Reddetme gerekçesi') || '';
    if (!accept && responseNote.trim().length < 5) return toast.error('Reddetme gerekçesi en az 5 karakter olmalıdır');
    try {
      await agencyApi.post(`/marketplace/v1/negotiations/${encodeURIComponent(proposal.id)}/decision`, { accept, response_note: responseNote });
      toast.success(accept ? 'Karşılıklı iptal kabul edildi' : 'Otel önerisi reddedildi; rezervasyon korundu');
      loadReservations();
    } catch (err) { toast.error(err.response?.data?.detail || 'Yanıt kaydedilemedi'); }
  };
  const openCancellationDialog = reservation => {
    setCancelTarget(reservation);
    setCancelReason('');
  };
  const cancelReservation = async () => {
    const reason = cancelReason.trim();
    if (reason.length < 5) return toast.error('İptal gerekçesi en az 5 karakter olmalıdır');
    setCancelLoading(true);
    try {
      await agencyApi.delete(`/marketplace/v1/reservations/${encodeURIComponent(cancelTarget.id)}`, { params: { reason } });
      toast.success('İptal talebi otele iletildi; otel kabul edene kadar rezervasyon korunur');
      setCancelTarget(null);
      setCancelReason('');
      loadReservations();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'İptal işlemi tamamlanamadı');
    } finally {
      setCancelLoading(false);
    }
  };
  const proposeModification = async reservation => {
    const checkIn = window.prompt('Yeni giriş tarihi (YYYY-AA-GG)', String(reservation.check_in || '').slice(0, 10));
    if (!checkIn) return;
    const checkOut = window.prompt('Yeni çıkış tarihi (YYYY-AA-GG)', String(reservation.check_out || '').slice(0, 10));
    if (!checkOut) return;
    const roomType = window.prompt('İstenen oda tipi', reservation.room_type || '');
    if (!roomType) return;
    const reason = window.prompt('Değişiklik gerekçesi (en az 5 karakter)', 'Misafir talebi');
    if (!reason || reason.trim().length < 5) return toast.error('Değişiklik gerekçesi en az 5 karakter olmalıdır');
    try {
      await agencyApi.post(`/marketplace/v1/reservations/${encodeURIComponent(reservation.id)}/modification-proposals`, {
        check_in: checkIn, check_out: checkOut, room_type: roomType.trim(), reason: reason.trim(),
      });
      toast.success('Değişiklik talebi otele iletildi; onay verilene kadar rezervasyon korunur');
      loadReservations();
    } catch (err) { toast.error(err.response?.data?.detail || 'Değişiklik talebi iletilemedi'); }
  };
  const printVoucher = async reservation => {
    try {
      const { data } = await agencyApi.get(`/marketplace/v1/reservations/${encodeURIComponent(reservation.id)}/voucher.pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }));
      const popup = window.open(url, '_blank', 'noopener,noreferrer');
      if (!popup) {
        const link = document.createElement('a');
        link.href = url;
        link.download = `${reservation.confirmation_code || reservation.id}.pdf`;
        link.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) { toast.error(err.response?.data?.detail || 'Voucher PDF oluşturulamadı'); }
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
      await agencyApi.post(`/marketplace/v1/reservations/${encodeURIComponent(voucherEmailTarget.id)}/voucher-email`, { email });
      toast.success('Voucher e-posta ile gönderildi');
      setVoucherEmailTarget(null);
      setVoucherEmail('');
    } catch (err) { toast.error(err.response?.data?.detail || 'Voucher gönderilemedi'); }
    finally { setVoucherEmailLoading(false); }
  };
  const loadReconciliation = async () => {
    if (portalMode !== 'marketplace') return;
    const end = toDateInput(new Date()); const startDate = new Date(); startDate.setDate(startDate.getDate() - 30);
    try { const { data } = await agencyApi.get('/marketplace/v1/reconciliation/agency', { params: { period_start: toDateInput(startDate), period_end: end } }); setReconciliation(data); }
    catch (err) { toast.error(err.response?.data?.detail || 'Mutabakat yüklenemedi'); }
  };
  const downloadReconciliation = async () => {
    const end = toDateInput(new Date()); const startDate = new Date(); startDate.setDate(startDate.getDate() - 30);
    try {
      const { data } = await agencyApi.get('/marketplace/v1/reconciliation/agency.csv', {
        params: { period_start: toDateInput(startDate), period_end: end }, responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([data], { type: 'text/csv;charset=utf-8' }));
      const link = document.createElement('a'); link.href = url; link.download = `acente-mutabakat-${end}.csv`; link.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(err.response?.data?.detail || 'Mutabakat dosyası indirilemedi'); }
  };
  const statusLabels = {
    confirmed: 'Onaylandı',
    pending: 'Beklemede',
    checked_in: 'Giriş Yaptı',
    checked_out: 'Çıkış Yaptı',
    cancelled: 'İptal'
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
        <Card className="w-full max-w-md shadow-2xl border-0">
          <CardHeader className="text-center pb-2">
            <div className="w-14 h-14 bg-emerald-100 rounded-xl flex items-center justify-center mx-auto mb-3">
              <Building2 size={28} className="text-emerald-700" />
            </div>
            <CardTitle className="text-xl">Acente Portalı</CardTitle>
            <p className="text-sm text-slate-500 mt-1">{t('cm.pages_AgencyPortalDashboard.acente_hesabinizla_giris_yapin')}</p>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Hesap türünüz otomatik belirlenir. Global marketplace hesabı tüm sözleşmeli tesisleri,
              otel bağlantılı hesap ise yalnız ilgili tesisi gösterir.
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
              <Button type="submit" className="w-full" disabled={loginLoading} data-testid="agency-login-submit">
                {loginLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
                {t('cm.pages_AgencyPortalDashboard.giris_yap')}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>;
  }

  if (profileLoading) return <div className="min-h-screen bg-slate-50 flex items-center justify-center" role="status">
    <div className="text-center text-slate-500"><Loader2 className="animate-spin mx-auto mb-3" size={28} />Acente hesabı doğrulanıyor…</div>
  </div>;

  if (profileError) return <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
    <Card className="max-w-md w-full"><CardContent className="py-8 text-center space-y-4">
      <p role="alert" className="text-sm text-red-700">{profileError}</p>
      <div className="flex justify-center gap-2">
        <Button variant="outline" onClick={handleLogout}>Oturumu kapat</Button>
        <Button onClick={() => { setProfileLoading(true); setProfileRevision(value => value + 1); }}>Tekrar dene</Button>
      </div>
    </CardContent></Card>
  </div>;

  // ─── MAIN PORTAL ───
  const workspaceLabel = portalMode === 'marketplace' ? 'Global marketplace' : 'Otel bağlantılı portal';
  const signedInIdentity = agencyUser?.email || agencyUser?.name || '';
  return <div className="min-h-screen bg-slate-50" data-testid="agency-portal-dashboard">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-100 rounded-lg flex items-center justify-center">
              <Building2 size={18} className="text-emerald-700" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="font-semibold text-slate-800 text-sm">{portalMode === 'marketplace' ? 'Acente Otel Satış Portalı' : (hotelInfo?.name || 'Otel Satış Portalı')}</div>
                <Badge variant="outline" className={portalMode === 'marketplace' ? 'border-emerald-300 bg-emerald-50 text-emerald-800' : 'border-blue-300 bg-blue-50 text-blue-800'} data-testid="agency-workspace-type">
                  {workspaceLabel}
                </Badge>
              </div>
              <div className="text-xs text-slate-500" data-testid="agency-session-identity">
                {agencyInfo?.name || 'Acente'}{signedInIdentity ? ` · ${signedInIdentity}` : ''}
              </div>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={handleLogout} data-testid="agency-logout-btn">
            <LogOut size={14} className="mr-1" /> {t('cm.pages_AgencyPortalDashboard.cikis')}
          </Button>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-6xl mx-auto p-4 space-y-6">
        <Tabs defaultValue="search" className="w-full">
          <TabsList className={`grid w-full ${portalMode === 'marketplace' ? 'grid-cols-4 max-w-3xl' : 'grid-cols-3 max-w-xl'} h-auto`}>
            <TabsTrigger value="search" data-testid="tab-search">{t('cm.pages_AgencyPortalDashboard.musaitlik_ara')}</TabsTrigger>
            <TabsTrigger value="reservations" onClick={loadReservations} data-testid="tab-reservations">Rezervasyonlarım</TabsTrigger>
            <TabsTrigger value="content" onClick={loadContent} data-testid="tab-content">Otel Bilgileri</TabsTrigger>
            {portalMode === 'marketplace' && <TabsTrigger value="finance" onClick={loadReconciliation}>Mutabakat</TabsTrigger>}
          </TabsList>

          {/* Search Tab */}
          <TabsContent value="search" className="mt-4 space-y-4">
            <Card>
              <CardContent className="pt-5">
                {portalMode === 'marketplace' && <div className="mb-5 space-y-4 rounded-xl border border-emerald-200 bg-emerald-50/40 p-4">
                  <div>
                    <div className="font-semibold text-slate-800">Uygun tesisleri keşfedin</div>
                    <p className="text-xs text-emerald-800 flex items-start gap-1.5 mt-1"><ShieldCheck size={14} className="shrink-0" />Tarih ve tercihlerinize uyan, aktif sözleşmeli ve satışa açık tesisler birlikte listelenir.</p>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div><Label className="text-xs">Tesis, bölge veya açıklama</Label><Input value={searchForm.q} onChange={e => setSearchForm(p => ({ ...p, q: e.target.value }))} placeholder="Kapadokya, sahil, butik…" /></div>
                    <div><Label className="text-xs">Şehir</Label><Input value={searchForm.city} onChange={e => setSearchForm(p => ({ ...p, city: e.target.value }))} placeholder="Tüm şehirler" /></div>
                  </div>
                  <button type="button" onClick={() => setShowAdvancedFilters(value => !value)} className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 hover:border-emerald-300" aria-expanded={showAdvancedFilters}>
                    <span className="flex items-center gap-2"><SlidersHorizontal size={15} />İsteğe bağlı filtreler</span><span className="flex items-center gap-2 text-xs font-normal text-slate-500">{searchForm.amenities.length + searchForm.meal_plans.length + (searchForm.min_star_rating ? 1 : 0) + (searchForm.max_price ? 1 : 0) + (selectedTenantId ? 1 : 0) > 0 ? `${searchForm.amenities.length + searchForm.meal_plans.length + (searchForm.min_star_rating ? 1 : 0) + (searchForm.max_price ? 1 : 0) + (selectedTenantId ? 1 : 0)} seçili` : 'Filtre yok'}<ChevronDown size={15} className={`transition-transform ${showAdvancedFilters ? 'rotate-180' : ''}`} /></span>
                  </button>
                  {showAdvancedFilters && <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
                    <div><Label className="text-xs">Belirli tesis</Label><select value={selectedTenantId} onChange={e => { setSelectedTenantId(e.target.value); setAvailability(null); }} className="mt-1 flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"><option value="">Tüm sözleşmeli tesisler</option>{hotels.map(hotel => <option key={hotel.tenant_id} value={hotel.tenant_id}>{hotel.name}{hotel.city ? ` · ${hotel.city}` : ''}</option>)}</select></div>
                    <div><Label className="text-xs">Tesis ve oda özellikleri</Label><div className="mt-2 flex flex-wrap gap-2">{AMENITY_FILTERS.map(([value, label]) => <button type="button" key={value} onClick={() => setSearchForm(p => ({ ...p, amenities: toggleFilter(p.amenities, value) }))} className={`rounded-full border px-3 py-1.5 text-xs transition ${searchForm.amenities.includes(value) ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-emerald-400'}`}>{label}</button>)}</div></div>
                    <div><Label className="text-xs">Pansiyon tipi</Label><div className="mt-2 flex flex-wrap gap-2">{MEAL_FILTERS.map(([value, label]) => <button type="button" key={value} onClick={() => setSearchForm(p => ({ ...p, meal_plans: toggleFilter(p.meal_plans, value) }))} className={`rounded-full border px-3 py-1.5 text-xs transition ${searchForm.meal_plans.includes(value) ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-blue-400'}`}>{label}</button>)}</div></div>
                    <div className="grid grid-cols-2 gap-3"><div><Label className="text-xs">En az yıldız</Label><select value={searchForm.min_star_rating || ''} onChange={e => setSearchForm(p => ({ ...p, min_star_rating: e.target.value ? Number(e.target.value) : null }))} className="mt-1 flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"><option value="">Farketmez</option>{[3,4,5].map(star => <option key={star} value={star}>{star} yıldız ve üzeri</option>)}</select></div><div><Label className="text-xs">Azami toplam fiyat</Label><Input type="number" min="0" value={searchForm.max_price || ''} onChange={e => setSearchForm(p => ({ ...p, max_price: e.target.value ? Number(e.target.value) : null }))} placeholder="Sınırsız" /></div></div>
                  </div>}
                </div>}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
                  <div className="space-y-1">
                    <Label className="text-xs">{t('cm.pages_AgencyPortalDashboard.giris_tarihi')}</Label>
                    <Input type="date" min={toDateInput(new Date())} value={searchForm.check_in} onChange={e => {
                      const checkIn = e.target.value;
                      const next = new Date(`${checkIn}T12:00:00`);
                      next.setDate(next.getDate() + 1);
                      setSearchForm(p => ({ ...p, check_in: checkIn, check_out: p.check_out <= checkIn ? toDateInput(next) : p.check_out }));
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
                  <Button onClick={handleSearch} disabled={searchLoading} data-testid="search-availability-btn" className="gap-2 w-full">
                    {searchLoading ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />}
                    {t('cm.pages_AgencyPortalDashboard.ara')}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Results */}
            {availability && <div className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-medium text-slate-700">{formatDate(availability.check_in)} – {formatDate(availability.check_out)}</h3>
                  <span className="text-xs text-slate-500">{availability.night_count} gece · {availability.adults + availability.children} misafir</span>
                </div>
                {availability.room_types.length === 0 ? <Card><CardContent className="py-8 text-center text-slate-400">Tercihlerinize ve tarihlere uygun satışa açık tesis bulunamadı. Filtreleri azaltarak tekrar deneyin.</CardContent></Card> : availability.room_types.map(rt => <Card key={`${rt.tenant_id || 'hotel'}-${rt.room_type}`} className="hover:shadow-sm transition" data-testid={`result-${rt.room_type}`}>
                      <CardContent className="py-4">
                        {portalMode === 'marketplace' && <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-slate-100 pb-3"><Building2 size={15} className="text-emerald-600" /><span className="font-semibold text-slate-800">{rt.hotel_name}</span>{rt.hotel_city && <span className="text-xs text-slate-500 flex items-center gap-1"><MapPin size={11} />{rt.hotel_city}</span>}</div>}
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                          <div className="flex items-center gap-4">
                            <div className="w-12 h-12 bg-blue-50 rounded-lg flex items-center justify-center">
                              <Bed size={20} className="text-blue-600" />
                            </div>
                            <div>
                              <div className="font-semibold text-slate-800">{rt.room_type}</div>
                              <div className="text-xs text-slate-500 flex items-center gap-3 mt-0.5">
                                <span><Users size={10} className="inline mr-1" />En fazla {rt.capacity} kişi</span>
                                <span>{rt.available_rooms} müsait / {rt.total_rooms} oda</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center justify-between sm:justify-end gap-4">
                            <div className="text-right">
                              <div className="text-lg font-bold text-slate-800">{formatMoney(rt.stay_total, rt.currency || availability.currency)}</div>
                              <div className="text-[11px] text-slate-500">{availability.night_count} gece toplam · {formatMoney(rt.base_price, rt.currency || availability.currency)}/gece</div>
                              {rt.occupancy_pricing?.children_ages?.length > 0 && <div className="mt-1 text-[11px] text-violet-700" data-testid={`child-price-${rt.room_type}`}>
                                Çocuk yaşları ({rt.occupancy_pricing.children_ages.join(', ')}) fiyata dahil
                                {rt.occupancy_pricing.child_supplement_nightly > 0 ? ` · ${formatMoney(rt.occupancy_pricing.child_supplement_nightly, rt.currency || availability.currency)}/gece çocuk farkı` : ' · ücretsiz'}
                              </div>}
                              {rt.has_contract && <Badge variant="outline" className="mt-1 text-[10px] border-emerald-300 text-emerald-700">Acente sözleşme fiyatı</Badge>}
                            </div>
                            <Button size="sm" onClick={() => openBookingForm(rt)} data-testid={`book-${rt.room_type}`} className="gap-1">
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
            <div className="flex items-center justify-between gap-3">
              <div><h2 className="font-semibold text-slate-800">Acente rezervasyonları</h2><p className="text-xs text-slate-500">Bu acente hesabından oluşturulan kayıtlar</p></div>
              <Button variant="outline" size="sm" onClick={loadReservations} disabled={reservationsLoading}><RefreshCw size={14} className={reservationsLoading ? 'animate-spin mr-1' : 'mr-1'} />Yenile</Button>
            </div>
            {negotiations.filter(item => item.status === 'awaiting_agency').map(item => <Card key={item.id} className="border-amber-300 bg-amber-50"><CardContent className="py-4"><div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3"><div><div className="font-semibold text-amber-900">Otel iptal önerisi · {item.confirmation_code}</div><div className="text-sm text-amber-800 mt-1">{item.reason}</div><div className="text-xs text-amber-700 mt-1">Tek taraflı uygulanmaz; kararınız bekleniyor.</div></div><div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => decideNegotiation(item, false)}>Reddet</Button><Button size="sm" onClick={() => decideNegotiation(item, true)}>Kabul Et</Button></div></div></CardContent></Card>)}
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
                        <div className="flex gap-1 mt-2">
                          <Button size="sm" variant="outline" onClick={() => printVoucher(r)}><Printer size={13} className="mr-1" />Voucher</Button>
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
            <div className="flex items-center justify-between gap-3"><div><h2 className="font-semibold text-slate-800">Son 30 gün mutabakatı</h2><p className="text-xs text-slate-500">Brüt satıştan acente komisyonu ve platform bedeli düşüldükten sonra otele aktarılacak net tutar</p></div><Button variant="outline" size="sm" onClick={downloadReconciliation}>CSV indir</Button></div>
            {!reconciliation ? <Card><CardContent className="py-10 text-center text-slate-400"><Loader2 className="animate-spin mx-auto" /></CardContent></Card> : <>
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                {[['Brüt satış', reconciliation.totals?.gross_revenue, true], ['Acente komisyonu', reconciliation.totals?.commission, true], ['Platform bedeli', reconciliation.totals?.platform_fee, true], ['Otele net', reconciliation.totals?.net_to_hotels, true], ['Rezervasyon', reconciliation.totals?.bookings, false]].map(([label, value, monetary]) => <Card key={label}><CardContent className="pt-4"><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-bold">{monetary ? formatMoney(value, hotelInfo?.currency) : value}</div></CardContent></Card>)}
              </div>
              {(reconciliation.by_hotel || []).map(row => <Card key={row.tenant_id}><CardContent className="py-4 flex items-center justify-between"><div><div className="font-medium">{row.hotel_name}</div><div className="text-xs text-slate-500">{row.bookings} rezervasyon · Komisyon {formatMoney(row.commission, hotelInfo?.currency)} · Platform {formatMoney(row.platform_fee, hotelInfo?.currency)}</div></div><div className="text-right"><div className="font-bold">{formatMoney(row.gross_revenue, hotelInfo?.currency)}</div><div className="text-xs text-emerald-700">Net {formatMoney(row.net_to_hotel, hotelInfo?.currency)}</div></div></CardContent></Card>)}
            </>}
          </TabsContent>}

          {/* Content Tab */}
          <TabsContent value="content" className="mt-4">
            {contentLoading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-400" size={24} /></div> : !content?.published ? <Card><CardContent className="py-12 text-center text-slate-400">
                <Eye size={40} className="mx-auto mb-3 opacity-40" />
                <p>{t('cm.pages_AgencyPortalDashboard.otel_henuz_size_icerik_yayinlamamis')}</p>
              </CardContent></Card> : <div className="space-y-4">
                <Card>
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
                      {content.hotel_content.room_types.map(rt => <Card key={rt.room_type}>
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
              <p className="mt-1 text-xs text-emerald-700">{availability?.night_count || 1} gece · Tutar otelin geçerli acente fiyatından sunucu tarafından hesaplanır.</p>
            </div>
            <div>
              <Label>{t('cm.pages_AgencyPortalDashboard.ozel_istek')}</Label>
              <textarea className="flex min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={bookingForm.special_requests} onChange={e => setBookingForm(p => ({
              ...p,
              special_requests: e.target.value
            }))} maxLength={1000} placeholder={t('cm.pages_AgencyPortalDashboard.erken_giris_deniz_manzarasi')} />
            </div>
            <div className="flex items-start gap-2 text-xs text-slate-500"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-emerald-600" />Rezervasyon kaydedilirken müsaitlik ve fiyat yeniden doğrulanır; çifte rezervasyon engellenir.</div>
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

      <Dialog open={Boolean(voucherEmailTarget)} onOpenChange={open => !open && !voucherEmailLoading && setVoucherEmailTarget(null)}>
        <DialogContent className="max-w-md" data-testid="voucher-email-dialog">
          <DialogHeader>
            <DialogTitle>Voucher'ı e-posta ile gönder</DialogTitle>
            <p className="text-sm text-slate-500">
              {voucherEmailTarget?.confirmation_code || voucherEmailTarget?.id} rezervasyonunun voucher PDF'i belirtilen adrese gönderilir.
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
