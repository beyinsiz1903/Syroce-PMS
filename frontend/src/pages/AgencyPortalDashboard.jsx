import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Search, CalendarDays, Users, Bed, ChevronRight, Plus,
  Loader2, Building2, LogOut, ClipboardList, Eye, Phone, Mail, MapPin
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useTranslation } from 'react-i18next';

const API_BASE = '';

const AgencyPortalDashboard = () => {
  const { t } = useTranslation();
  const [agencyUser, setAgencyUser] = useState(null);
  const [agencyInfo, setAgencyInfo] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('agency_token'));

  // Login
  const [loginForm, setLoginForm] = useState({ email: '', password: '' });
  const [loginLoading, setLoginLoading] = useState(false);

  // Content
  const [content, setContent] = useState(null);
  const [contentLoading, setContentLoading] = useState(false);

  // Availability
  const [searchForm, setSearchForm] = useState({
    check_in: '', check_out: '', adults: 2,
  });
  const [availability, setAvailability] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);

  // Reservation
  const [showBookingForm, setShowBookingForm] = useState(false);
  const [selectedRoomType, setSelectedRoomType] = useState(null);
  const [bookingForm, setBookingForm] = useState({
    guest_name: '', guest_email: '', guest_phone: '', adults: 2, children: 0, special_requests: '', total_amount: 0,
  });
  const [bookingLoading, setBookingLoading] = useState(false);

  // Reservations list
  const [reservations, setReservations] = useState([]);
  const [reservationsLoading, setReservationsLoading] = useState(false);

  const authHeaders = () => ({ headers: { Authorization: `Bearer ${token}` } });

  // Login handler
  const handleLogin = async (e) => {
    e.preventDefault();
    setLoginLoading(true);
    try {
      const { data } = await axios.post(`${API_BASE}/agency-portal/auth/login`, loginForm);
      localStorage.setItem('agency_token', data.token);
      setToken(data.token);
      setAgencyUser(data.user);
      setAgencyInfo(data.agency);
      toast.success('Giriş basarili');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Giriş hatası');
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('agency_token');
    setToken(null);
    setAgencyUser(null);
    setAgencyInfo(null);
    setContent(null);
    setAvailability(null);
    setReservations([]);
  };

  // Load profile on mount if token exists
  useEffect(() => {
    if (!token) return;
    const loadProfile = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/agency-portal/profile`, authHeaders());
        setAgencyUser(prev => prev || { name: data.agency?.name || '' });
        setAgencyInfo(data.agency);
      } catch {
        handleLogout();
      }
    };
    loadProfile();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [token]);

  // Load content
  const loadContent = async () => {
    setContentLoading(true);
    try {
      const { data } = await axios.get(`${API_BASE}/agency-portal/content`, authHeaders());
      setContent(data);
    } catch {
      toast.error('Icerik yüklenemedi');
    } finally {
      setContentLoading(false);
    }
  };

  // Search availability
  const handleSearch = async () => {
    if (!searchForm.check_in || !searchForm.check_out) return toast.error('Tarih seçin');
    setSearchLoading(true);
    try {
      const { data } = await axios.get(`${API_BASE}/agency-portal/availability`, {
        ...authHeaders(),
        params: searchForm,
      });
      setAvailability(data);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Arama hatası');
    } finally {
      setSearchLoading(false);
    }
  };

  // Book
  const openBookingForm = (roomType) => {
    setSelectedRoomType(roomType);
    const nights = Math.max(1, Math.ceil(
      (new Date(searchForm.check_out) - new Date(searchForm.check_in)) / (1000 * 60 * 60 * 24)
    ));
    setBookingForm({
      guest_name: '', guest_email: '', guest_phone: '',
      adults: searchForm.adults, children: 0, special_requests: '',
      total_amount: roomType.base_price * nights,
    });
    setShowBookingForm(true);
  };

  const handleBooking = async () => {
    if (!bookingForm.guest_name.trim()) return toast.error('Misafir adi gerekli');
    setBookingLoading(true);
    try {
      const { data } = await axios.post(`${API_BASE}/agency-portal/reservations`, {
        room_type_id: selectedRoomType.room_type,
        check_in: searchForm.check_in,
        check_out: searchForm.check_out,
        ...bookingForm,
      }, authHeaders());
      toast.success(data.message || 'Rezervasyon oluşturuldu');
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
      const { data } = await axios.get(`${API_BASE}/agency-portal/reservations`, authHeaders());
      setReservations(data);
    } catch {
      toast.error('Rezervasyonlar yüklenemedi');
    } finally {
      setReservationsLoading(false);
    }
  };

  const statusLabels = {
    confirmed: 'Onaylandi', pending: 'Beklemede', checked_in: 'Giriş Yapti',
    checked_out: 'Çıkış Yapti', cancelled: 'İptal',
  };
  const statusColors = {
    confirmed: 'bg-emerald-100 text-emerald-800', pending: 'bg-amber-100 text-amber-800',
    checked_in: 'bg-blue-100 text-blue-800', checked_out: 'bg-slate-100 text-slate-600',
    cancelled: 'bg-red-100 text-red-700',
  };

  // ─── LOGIN PAGE ───
  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-900 flex items-center justify-center p-4" data-testid="agency-portal-login">
        <Card className="w-full max-w-md shadow-2xl border-0">
          <CardHeader className="text-center pb-2">
            <div className="w-14 h-14 bg-emerald-100 rounded-xl flex items-center justify-center mx-auto mb-3">
              <Building2 size={28} className="text-emerald-700" />
            </div>
            <CardTitle className="text-xl">Acente Portali</CardTitle>
            <p className="text-sm text-slate-500 mt-1">{t('cm.pages_AgencyPortalDashboard.acente_hesabinizla_giris_yapin')}</p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <Label>E-posta</Label>
                <Input
                  type="email" required value={loginForm.email}
                  onChange={e => setLoginForm(p => ({ ...p, email: e.target.value }))}
                  data-testid="agency-login-email" placeholder="ornek@acente.com"
                />
              </div>
              <div>
                <Label>Sifre</Label>
                <Input
                  type="password" required value={loginForm.password}
                  onChange={e => setLoginForm(p => ({ ...p, password: e.target.value }))}
                  data-testid="agency-login-password"
                />
              </div>
              <Button type="submit" className="w-full" disabled={loginLoading} data-testid="agency-login-submit">
                {loginLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
                {t('cm.pages_AgencyPortalDashboard.giris_yap')}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ─── MAIN PORTAL ───
  return (
    <div className="min-h-screen bg-slate-50" data-testid="agency-portal-dashboard">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-emerald-100 rounded-lg flex items-center justify-center">
              <Building2 size={18} className="text-emerald-700" />
            </div>
            <div>
              <span className="font-semibold text-slate-800 text-sm">{agencyInfo?.name || 'Acente Portali'}</span>
              <span className="text-xs text-slate-400 ml-2">{agencyUser?.name || ''}</span>
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
          <TabsList className="grid w-full grid-cols-3 max-w-md">
            <TabsTrigger value="search" data-testid="tab-search">{t('cm.pages_AgencyPortalDashboard.musaitlik_ara')}</TabsTrigger>
            <TabsTrigger value="reservations" onClick={loadReservations} data-testid="tab-reservations">Rezervasyonlarim</TabsTrigger>
            <TabsTrigger value="content" onClick={loadContent} data-testid="tab-content">Otel Bilgileri</TabsTrigger>
          </TabsList>

          {/* Search Tab */}
          <TabsContent value="search" className="mt-4 space-y-4">
            <Card>
              <CardContent className="pt-5">
                <div className="flex flex-wrap gap-3 items-end">
                  <div>
                    <Label className="text-xs">{t('cm.pages_AgencyPortalDashboard.giris_tarihi')}</Label>
                    <Input type="date" value={searchForm.check_in} onChange={e => setSearchForm(p => ({ ...p, check_in: e.target.value }))} data-testid="search-checkin" className="w-44" />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_AgencyPortalDashboard.cikis_tarihi')}</Label>
                    <Input type="date" value={searchForm.check_out} onChange={e => setSearchForm(p => ({ ...p, check_out: e.target.value }))} data-testid="search-checkout" className="w-44" />
                  </div>
                  <div>
                    <Label className="text-xs">{t('cm.pages_AgencyPortalDashboard.kisi')}</Label>
                    <Input type="number" min={1} max={10} value={searchForm.adults} onChange={e => setSearchForm(p => ({ ...p, adults: parseInt(e.target.value) || 1 }))} className="w-20" />
                  </div>
                  <Button onClick={handleSearch} disabled={searchLoading} data-testid="search-availability-btn" className="gap-2">
                    {searchLoading ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />}
                    {t('cm.pages_AgencyPortalDashboard.ara')}
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Results */}
            {availability && (
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-slate-600">
                  {availability.check_in} - {availability.check_out} {t('cm.pages_AgencyPortalDashboard.icin_musait_odalar')}
                </h3>
                {availability.room_types.length === 0 ? (
                  <Card><CardContent className="py-8 text-center text-slate-400">{t('cm.pages_AgencyPortalDashboard.bu_tarihler_icin_musait_oda_bulunamadi')}</CardContent></Card>
                ) : (
                  availability.room_types.map(rt => (
                    <Card key={rt.room_type} className="hover:shadow-sm transition" data-testid={`result-${rt.room_type}`}>
                      <CardContent className="py-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4">
                            <div className="w-12 h-12 bg-blue-50 rounded-lg flex items-center justify-center">
                              <Bed size={20} className="text-blue-600" />
                            </div>
                            <div>
                              <div className="font-semibold text-slate-800">{rt.room_type}</div>
                              <div className="text-xs text-slate-500 flex items-center gap-3 mt-0.5">
                                <span><Users size={10} className="inline mr-1" />{rt.capacity} kisi</span>
                                <span>{rt.available_rooms} {t('cm.pages_AgencyPortalDashboard.musait')} {rt.total_rooms} toplam</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-4">
                            <div className="text-right">
                              <div className="text-lg font-bold text-slate-800">{rt.base_price.toLocaleString('tr-TR')} TL</div>
                              <div className="text-[10px] text-slate-400">gece / oda</div>
                            </div>
                            <Button size="sm" onClick={() => openBookingForm(rt)} data-testid={`book-${rt.room_type}`} className="gap-1">
                              <Plus size={14} /> Rezerve Et
                            </Button>
                          </div>
                        </div>
                        {rt.amenities?.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-3">
                            {rt.amenities.map(a => <Badge key={a} variant="outline" className="text-[10px]">{a}</Badge>)}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            )}
          </TabsContent>

          {/* Reservations Tab */}
          <TabsContent value="reservations" className="mt-4 space-y-3">
            {reservationsLoading ? (
              <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-400" size={24} /></div>
            ) : reservations.length === 0 ? (
              <Card><CardContent className="py-12 text-center text-slate-400">
                <ClipboardList size={40} className="mx-auto mb-3 opacity-40" />
                <p>{t('cm.pages_AgencyPortalDashboard.henuz_rezervasyonunuz_yok')}</p>
              </CardContent></Card>
            ) : (
              reservations.map(r => (
                <Card key={r.id} data-testid={`reservation-${r.id}`}>
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-semibold text-slate-800">{r.guest_name || 'Misafir'}</div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          {r.confirmation_code} | {r.room_type} {t('cm.pages_AgencyPortalDashboard.oda')} {r.room_number}
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5">
                          {r.check_in?.split('T')[0]} - {r.check_out?.split('T')[0]}
                        </div>
                      </div>
                      <div className="text-right">
                        <Badge className={`text-xs ${statusColors[r.status] || 'bg-slate-100'}`}>
                          {statusLabels[r.status] || r.status}
                        </Badge>
                        <div className="text-sm font-bold text-slate-700 mt-1">{(r.total_amount || 0).toLocaleString('tr-TR')} TL</div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          {/* Content Tab */}
          <TabsContent value="content" className="mt-4">
            {contentLoading ? (
              <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-400" size={24} /></div>
            ) : !content?.published ? (
              <Card><CardContent className="py-12 text-center text-slate-400">
                <Eye size={40} className="mx-auto mb-3 opacity-40" />
                <p>{t('cm.pages_AgencyPortalDashboard.otel_henuz_size_icerik_yayinlamamis')}</p>
              </CardContent></Card>
            ) : (
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{content.hotel_content?.hotel_name || 'Otel'}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {content.hotel_content?.description && (
                      <p className="text-sm text-slate-600">{content.hotel_content.description}</p>
                    )}
                    <div className="flex flex-wrap gap-4 text-sm text-slate-500">
                      {content.hotel_content?.address && <span className="flex items-center gap-1"><MapPin size={12} />{content.hotel_content.address}</span>}
                      {content.hotel_content?.phone && <span className="flex items-center gap-1"><Phone size={12} />{content.hotel_content.phone}</span>}
                      {content.hotel_content?.email && <span className="flex items-center gap-1"><Mail size={12} />{content.hotel_content.email}</span>}
                    </div>
                    {content.hotel_content?.amenities?.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {content.hotel_content.amenities.map(a => <Badge key={a} variant="outline" className="text-xs">{a}</Badge>)}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {content.hotel_content?.room_types?.length > 0 && (
                  <div>
                    <h3 className="font-medium text-slate-700 mb-2">{t('cm.pages_AgencyPortalDashboard.oda_tipleri')}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {content.hotel_content.room_types.map(rt => (
                        <Card key={rt.room_type}>
                          <CardContent className="pt-4">
                            <div className="flex items-center gap-3 mb-2">
                              <Bed size={16} className="text-blue-500" />
                              <span className="font-medium text-sm">{rt.name || rt.room_type}</span>
                            </div>
                            {rt.description && <p className="text-xs text-slate-500 mb-2">{rt.description}</p>}
                            <div className="flex gap-4 text-xs text-slate-600">
                              <span>{rt.capacity} kisi</span>
                              <span>{rt.base_price} TL / gece</span>
                              {rt.bed_type && <span>{rt.bed_type}</span>}
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                )}

                {content.hotel_content?.services?.length > 0 && (
                  <div>
                    <h3 className="font-medium text-slate-700 mb-2">Hizmetler</h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                      {content.hotel_content.services.map((s, i) => (
                        <Card key={i}>
                          <CardContent className="pt-3 pb-3">
                            <div className="font-medium text-sm text-slate-800">{s.name}</div>
                            {s.description && <div className="text-xs text-slate-500">{s.description}</div>}
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Booking Dialog */}
      <Dialog open={showBookingForm} onOpenChange={setShowBookingForm}>
        <DialogContent className="max-w-md" data-testid="booking-form-dialog">
          <DialogHeader>
            <DialogTitle>{t('cm.pages_AgencyPortalDashboard.rezervasyon_olustur')}</DialogTitle>
            <p className="text-sm text-slate-500">{selectedRoomType?.room_type} | {searchForm.check_in} - {searchForm.check_out}</p>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>{t('cm.pages_AgencyPortalDashboard.misafir_adi')}</Label>
              <Input value={bookingForm.guest_name} onChange={e => setBookingForm(p => ({ ...p, guest_name: e.target.value }))} data-testid="booking-guest-name" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>E-posta</Label>
                <Input value={bookingForm.guest_email} onChange={e => setBookingForm(p => ({ ...p, guest_email: e.target.value }))} />
              </div>
              <div>
                <Label>Telefon</Label>
                <Input value={bookingForm.guest_phone} onChange={e => setBookingForm(p => ({ ...p, guest_phone: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Yetiskin</Label>
                <Input type="number" min={1} value={bookingForm.adults} onChange={e => setBookingForm(p => ({ ...p, adults: parseInt(e.target.value) || 1 }))} />
              </div>
              <div>
                <Label>Cocuk</Label>
                <Input type="number" min={0} value={bookingForm.children} onChange={e => setBookingForm(p => ({ ...p, children: parseInt(e.target.value) || 0 }))} />
              </div>
            </div>
            <div>
              <Label>{t('cm.pages_AgencyPortalDashboard.toplam_tutar_tl')}</Label>
              <Input type="number" value={bookingForm.total_amount} onChange={e => setBookingForm(p => ({ ...p, total_amount: parseFloat(e.target.value) || 0 }))} data-testid="booking-amount" />
            </div>
            <div>
              <Label>{t('cm.pages_AgencyPortalDashboard.ozel_istek')}</Label>
              <Input value={bookingForm.special_requests} onChange={e => setBookingForm(p => ({ ...p, special_requests: e.target.value }))} placeholder={t('cm.pages_AgencyPortalDashboard.erken_giris_deniz_manzarasi')} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBookingForm(false)}>{t('cm.pages_AgencyPortalDashboard.iptal')}</Button>
            <Button onClick={handleBooking} disabled={bookingLoading} data-testid="confirm-booking-btn">
              {bookingLoading ? <Loader2 className="animate-spin mr-2" size={14} /> : null}
              Rezervasyonu Olustur
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AgencyPortalDashboard;
