import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Search, CalendarDays, Users, Bed, Plus, Loader2, Building2, LogOut, ClipboardList, Eye, Phone, Mail, MapPin, RefreshCw, ShieldCheck, Printer, XCircle, WalletCards } from 'lucide-react';
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
  return { check_in: toDateInput(today), check_out: toDateInput(tomorrow), adults: 2, children: 0 };
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

  // Reservation
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [selectedRoomType, setSelectedRoomType] = useState(null);
  const [bookingForm, setBookingForm] = useState({
    guest_name: '',
    guest_email: '',
    guest_phone: '',
    adults: 2,
    children: 0,
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
          const storedHotel = localStorage.getItem('agency_selected_hotel') || '';
          const allowedSelected = availableHotels.some(h => h.tenant_id === storedHotel)
            ? storedHotel : (availableHotels[0]?.tenant_id || '');
          setAgencyInfo(data.agency || null);
          setHotels(availableHotels);
          setSelectedTenantId(allowedSelected);
          if (allowedSelected) localStorage.setItem('agency_selected_hotel', allowedSelected);
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
        if (!selectedTenantId) return toast.error('Aktif sözleşmeli bir otel seçin');
        const { data } = await agencyApi.post('/marketplace/v1/search', searchForm);
        const hotelResult = (data.results || []).find(result => result.tenant_id === selectedTenantId);
        const selectedHotel = hotels.find(h => h.tenant_id === selectedTenantId);
        setAvailability({
          check_in: data.check_in,
          check_out: data.check_out,
          night_count: Math.max(1, Math.round((new Date(data.check_out) - new Date(data.check_in)) / 86400000)),
          adults: searchForm.adults,
          children: searchForm.children,
          currency: selectedHotel?.currency || 'TRY',
          room_types: (hotelResult?.available_room_types || []).map(room => ({
            ...room,
            base_price: room.base_price,
            stay_total: room.total_price,
          })),
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
    const nights = Math.max(1, Math.ceil((new Date(searchForm.check_out) - new Date(searchForm.check_in)) / (1000 * 60 * 60 * 24)));
    setBookingForm({
      guest_name: '',
      guest_email: '',
      guest_phone: '',
      adults: searchForm.adults,
      children: searchForm.children,
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
        special_requests: bookingForm.special_requests.trim(),
      };
      let response;
      if (portalMode === 'marketplace') {
        response = await agencyApi.post('/marketplace/v1/reservations', {
          ...payload,
          tenant_id: selectedTenantId,
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
  const cancelReservation = async reservation => {
    if (!window.confirm(`${reservation.confirmation_code || reservation.id} numaralı rezervasyon iptal edilsin mi?`)) return;
    try {
      const { data } = await agencyApi.delete(`/marketplace/v1/reservations/${encodeURIComponent(reservation.id)}`, { params: { reason: 'agency_portal' } });
      toast.success(data.penalty_amount ? `İptal edildi. Ceza: ${formatMoney(data.penalty_amount, reservation.currency)}` : 'Ücretsiz iptal edildi');
      loadReservations();
    } catch (err) { toast.error(err.response?.data?.detail || 'İptal işlemi tamamlanamadı'); }
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
  const emailVoucher = async reservation => {
    const email = window.prompt('Voucher gönderilecek e-posta adresi', reservation.guest_email || '');
    if (!email) return;
    try {
      await agencyApi.post(`/marketplace/v1/reservations/${encodeURIComponent(reservation.id)}/voucher-email`, { email: email.trim() });
      toast.success('Voucher e-posta ile gönderildi');
    } catch (err) { toast.error(err.response?.data?.detail || 'Voucher gönderilemedi'); }
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
  return <div className="min-h-screen bg-slate-50" data-testid="agency-portal-dashboard">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-100 rounded-lg flex items-center justify-center">
              <Building2 size={18} className="text-emerald-700" />
            </div>
            <div>
              <div className="font-semibold text-slate-800 text-sm">{portalMode === 'marketplace' ? 'Acente Otel Satış Portalı' : (hotelInfo?.name || 'Otel Satış Portalı')}</div>
              <div className="text-xs text-slate-500">{agencyInfo?.name || 'Acente'} · {agencyUser?.name || ''}</div>
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
            {portalMode === 'marketplace' && <Card className="border-emerald-200 bg-emerald-50/40">
              <CardContent className="pt-5">
                <Label htmlFor="agency-hotel-select" className="text-xs">Rezervasyon yapılacak otel</Label>
                <select
                  id="agency-hotel-select"
                  data-testid="agency-hotel-select"
                  value={selectedTenantId}
                  onChange={event => {
                    const tenantId = event.target.value;
                    const selected = hotels.find(hotel => hotel.tenant_id === tenantId);
                    setSelectedTenantId(tenantId);
                    localStorage.setItem('agency_selected_hotel', tenantId);
                    setHotelInfo(selected ? { name: selected.name, currency: selected.currency || 'TRY', ...selected } : null);
                    setAvailability(null);
                    setReservations([]);
                    setContent(null);
                  }}
                  className="mt-1 flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                >
                  {hotels.length === 0 && <option value="">Aktif sözleşmeli otel bulunmuyor</option>}
                  {hotels.map(hotel => <option key={hotel.tenant_id} value={hotel.tenant_id}>
                    {hotel.name}{hotel.city ? ` · ${hotel.city}` : ''}
                  </option>)}
                </select>
                <p className="mt-2 text-xs text-emerald-800 flex items-start gap-1.5"><ShieldCheck size={14} className="shrink-0" />Yalnız aktif ve tüm konaklama tarihini kapsayan sözleşmeli oteller listelenir. Tesis yetkisi rezervasyon kaydında sunucuda tekrar doğrulanır.</p>
              </CardContent>
            </Card>}
            <Card>
              <CardContent className="pt-5">
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
                      ...p, children: Math.max(0, parseInt(e.target.value) || 0)
                    }))} className="w-full" />
                  </div>
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
                {availability.room_types.length === 0 ? <Card><CardContent className="py-8 text-center text-slate-400">{t('cm.pages_AgencyPortalDashboard.bu_tarihler_icin_musait_oda_bulunamadi')}</CardContent></Card> : availability.room_types.map(rt => <Card key={rt.room_type} className="hover:shadow-sm transition" data-testid={`result-${rt.room_type}`}>
                      <CardContent className="py-4">
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
                              <div className="text-lg font-bold text-slate-800">{formatMoney(rt.stay_total, availability.currency)}</div>
                              <div className="text-[11px] text-slate-500">{availability.night_count} gece toplam · {formatMoney(rt.base_price, availability.currency)}/gece</div>
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
                          {portalMode === 'marketplace' && <Button size="sm" variant="outline" onClick={() => emailVoucher(r)}><Mail size={13} className="mr-1" />E-posta</Button>}
                          {!['cancelled', 'checked_in', 'checked_out'].includes(r.status) && portalMode === 'marketplace' && <Button size="sm" variant="outline" onClick={() => proposeModification(r)}>Değişiklik</Button>}
                          {!['cancelled', 'checked_in', 'checked_out'].includes(r.status) && portalMode === 'marketplace' && <Button size="sm" variant="outline" className="text-red-700" onClick={() => cancelReservation(r)}><XCircle size={13} className="mr-1" />İptal</Button>}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>)}
          </TabsContent>

          {portalMode === 'marketplace' && <TabsContent value="finance" className="mt-4 space-y-4">
            <div className="flex items-center justify-between gap-3"><div><h2 className="font-semibold text-slate-800">Son 30 gün mutabakatı</h2><p className="text-xs text-slate-500">Brüt satış, acente komisyonu ve otele aktarılacak net tutar</p></div><Button variant="outline" size="sm" onClick={downloadReconciliation}>CSV indir</Button></div>
            {!reconciliation ? <Card><CardContent className="py-10 text-center text-slate-400"><Loader2 className="animate-spin mx-auto" /></CardContent></Card> : <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[['Brüt satış', reconciliation.totals?.gross_revenue], ['Komisyon', reconciliation.totals?.commission], ['Otele net', reconciliation.totals?.net_to_hotels], ['Rezervasyon', reconciliation.totals?.bookings]].map(([label, value], index) => <Card key={label}><CardContent className="pt-4"><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-bold">{index === 3 ? value : formatMoney(value, hotelInfo?.currency)}</div></CardContent></Card>)}
              </div>
              {(reconciliation.by_hotel || []).map(row => <Card key={row.tenant_id}><CardContent className="py-4 flex items-center justify-between"><div><div className="font-medium">{row.hotel_name}</div><div className="text-xs text-slate-500">{row.bookings} rezervasyon</div></div><div className="text-right"><div className="font-bold">{formatMoney(row.gross_revenue, hotelInfo?.currency)}</div><div className="text-xs text-emerald-700">Net {formatMoney(row.net_to_hotel, hotelInfo?.currency)}</div></div></CardContent></Card>)}
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
                <Input type="number" min={1} max={selectedRoomType?.capacity || 20} value={bookingForm.adults} onChange={e => setBookingForm(p => ({
                ...p,
                adults: parseInt(e.target.value) || 1
              }))} />
              </div>
              <div>
                <Label>Çocuk</Label>
                <Input type="number" min={0} max={selectedRoomType?.capacity || 20} value={bookingForm.children} onChange={e => setBookingForm(p => ({
                ...p,
                children: parseInt(e.target.value) || 0
              }))} />
              </div>
            </div>
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
    </div>;
};
export default AgencyPortalDashboard;
