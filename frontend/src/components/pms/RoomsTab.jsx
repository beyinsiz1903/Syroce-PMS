import React, { useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { BedDouble, User, LogIn, LogOut, CreditCard, AlertTriangle, SprayCan, ExternalLink, Banknote, Building2, Wallet, Plus, CalendarPlus, Search, UserCheck, UserPlus, Calendar } from 'lucide-react';

const RoomsTab = ({
  rooms,
  bookings = [],
  guests = [],
  handleCheckIn,
  handleCheckOut,
  onPayment,
  onGuestClick,
  onBookingDoubleClick,
  onDataRefresh,
}) => {
  const { t } = useTranslation();
  const [typeFilter, setTypeFilter] = useState('all');
  const [viewFilter, setViewFilter] = useState('all');
  const [amenityFilter, setAmenityFilter] = useState('all');

  // Checkout confirmation dialog state
  const [checkoutDialog, setCheckoutDialog] = useState(false);
  const [checkoutBooking, setCheckoutBooking] = useState(null);

  // Dirty room check-in dialog state
  const [dirtyRoomDialog, setDirtyRoomDialog] = useState(false);
  const [dirtyRoomInfo, setDirtyRoomInfo] = useState(null);

  // Quick payment dialog state
  const [paymentDialog, setPaymentDialog] = useState(false);
  const [paymentTarget, setPaymentTarget] = useState(null);
  const [paymentAmount, setPaymentAmount] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [paymentLoading, setPaymentLoading] = useState(false);

  // Quick reservation dialog state
  const [quickResDialog, setQuickResDialog] = useState(false);
  const [quickResRoom, setQuickResRoom] = useState(null);
  const [quickResForm, setQuickResForm] = useState({ guest_name: '', check_in: '', check_out: '', total_amount: '' });
  const [quickResLoading, setQuickResLoading] = useState(false);

  // Guest search state
  const [guestSearchQuery, setGuestSearchQuery] = useState('');
  const [guestSearchResults, setGuestSearchResults] = useState([]);
  const [guestSearchLoading, setGuestSearchLoading] = useState(false);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [showGuestDropdown, setShowGuestDropdown] = useState(false);
  const guestSearchTimerRef = React.useRef(null);

  const today = useMemo(() => new Date().toISOString().split('T')[0], []);
  const tomorrow = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
  }, []);

  // Build a map of room_number -> current guest info from active bookings
  const roomGuestMap = useMemo(() => {
    const map = {};
    const activeStatuses = ['confirmed', 'checked_in', 'guaranteed'];
    for (const b of bookings) {
      if (!activeStatuses.includes(b.status)) continue;
      if (!b.room_number) continue;
      const ci = (b.check_in || '').slice(0, 10);
      const co = (b.check_out || '').slice(0, 10);
      if (ci <= today && co > today) {
        const balance = Math.max(0, (b.total_amount || 0) - (b.paid_amount || 0));
        // Determine guest category
        let category = 'pending_checkin'; // confirmed/guaranteed but not checked in
        if (b.status === 'checked_in') {
          category = co === tomorrow ? 'departing_tomorrow' : 'in_house';
        }
        map[String(b.room_number)] = {
          booking_id: b.id,
          guest_id: b.guest_id,
          guest_name: b.guest_name || 'Misafir',
          check_in: ci,
          check_out: co,
          status: b.status,
          total_amount: b.total_amount || 0,
          paid_amount: b.paid_amount || 0,
          balance: Math.round(balance * 100) / 100,
          isCheckInToday: ci === today,
          isCheckOutToday: co === today,
          category,
        };
      }
      // Also handle check-out today for checked_in guests whose co == today
      if (b.status === 'checked_in' && co === today && !map[String(b.room_number)]) {
        const balance = Math.max(0, (b.total_amount || 0) - (b.paid_amount || 0));
        map[String(b.room_number)] = {
          booking_id: b.id,
          guest_id: b.guest_id,
          guest_name: b.guest_name || 'Misafir',
          check_in: ci,
          check_out: co,
          status: b.status,
          total_amount: b.total_amount || 0,
          paid_amount: b.paid_amount || 0,
          balance: Math.round(balance * 100) / 100,
          isCheckInToday: ci === today,
          isCheckOutToday: true,
          category: 'departing_today',
        };
      }
    }
    return map;
  }, [bookings, today, tomorrow]);

  const filteredRooms = useMemo(() => {
    return rooms.filter(r => {
      if (typeFilter !== 'all' && r.room_type !== typeFilter) return false;
      if (viewFilter !== 'all' && r.view !== viewFilter) return false;
      if (amenityFilter !== 'all' && !(r.amenities || []).includes(amenityFilter)) return false;
      return true;
    });
  }, [rooms, typeFilter, viewFilter, amenityFilter]);

  const allTypes = [...new Set(rooms.map(r => r.room_type).filter(Boolean))];
  const allViews = [...new Set(rooms.map(r => r.view).filter(Boolean))];
  const allAmenities = [...new Set(rooms.flatMap(r => r.amenities || []))];

  // Card border/bg colors based on guest category
  const categoryStyles = {
    in_house: 'border-l-4 border-l-green-500 bg-green-50/40',
    departing_today: 'border-l-4 border-l-red-500 bg-red-50/40',
    departing_tomorrow: 'border-l-4 border-l-orange-500 bg-orange-50/40',
    pending_checkin: 'border-l-4 border-l-purple-500 bg-purple-50/40',
  };

  const categoryLabels = {
    in_house: { text: 'Iceride', cls: 'bg-green-100 text-green-700' },
    departing_today: { text: 'Bugün Çıkış', cls: 'bg-red-100 text-red-700' },
    departing_tomorrow: { text: 'Yarin Çıkış', cls: 'bg-orange-100 text-orange-700' },
    pending_checkin: { text: 'Giriş Bekleniyor', cls: 'bg-purple-100 text-purple-700' },
  };

  const guestSectionStyles = {
    in_house: 'bg-green-50 border-green-200',
    departing_today: 'bg-red-50 border-red-200',
    departing_tomorrow: 'bg-orange-50 border-orange-200',
    pending_checkin: 'bg-purple-50 border-purple-200',
  };

  const guestTextStyles = {
    in_house: { icon: 'text-green-600', name: 'text-green-800', date: 'text-green-500', link: 'text-green-400', hoverBg: 'hover:bg-green-100' },
    departing_today: { icon: 'text-red-600', name: 'text-red-800', date: 'text-red-500', link: 'text-red-400', hoverBg: 'hover:bg-red-100' },
    departing_tomorrow: { icon: 'text-orange-600', name: 'text-orange-800', date: 'text-orange-500', link: 'text-orange-400', hoverBg: 'hover:bg-orange-100' },
    pending_checkin: { icon: 'text-purple-600', name: 'text-purple-800', date: 'text-purple-500', link: 'text-purple-400', hoverBg: 'hover:bg-purple-100' },
  };

  // Handle guest name click -> open reservation detail modal (same as calendar double-click)
  const handleGuestNameClick = useCallback((e, guestInfo) => {
    e.stopPropagation();
    if (!guestInfo.booking_id) return;
    const booking = bookings.find(b => b.id === guestInfo.booking_id);
    if (booking && onBookingDoubleClick) {
      onBookingDoubleClick(booking);
    }
  }, [bookings, onBookingDoubleClick]);

  // Handle check-in click with dirty room check
  const handleCheckInClick = useCallback((e, room, guestInfo) => {
    e.stopPropagation();
    if (room.status === 'dirty' || room.status === 'cleaning') {
      setDirtyRoomInfo({ room, guestInfo });
      setDirtyRoomDialog(true);
    } else {
      handleCheckIn?.(guestInfo.booking_id);
    }
  }, [handleCheckIn]);

  // Handle checkout with balance check
  const handleCheckOutClick = useCallback(async (e, guestInfo) => {
    e.stopPropagation();
    if (guestInfo.balance > 0.01) {
      setCheckoutBooking(guestInfo);
      setCheckoutDialog(true);
    } else {
      handleCheckOut?.(guestInfo.booking_id);
    }
  }, [handleCheckOut]);

  // Open quick payment dialog
  const handlePaymentClick = useCallback((e, guestInfo) => {
    e.stopPropagation();
    setPaymentTarget(guestInfo);
    setPaymentAmount(guestInfo.balance > 0 ? String(guestInfo.balance) : '');
    setPaymentMethod('cash');
    setPaymentDialog(true);
  }, []);

  // Submit quick payment
  const handleQuickPayment = useCallback(async () => {
    if (!paymentTarget) return;
    const amount = parseFloat(paymentAmount);
    if (!amount || amount <= 0) {
      toast.error('Lutfen geçerli bir tutar giriniz');
      return;
    }
    setPaymentLoading(true);
    try {
      await axios.post(`/pms/reservations/${paymentTarget.booking_id}/record-payment`, {
        amount,
        method: paymentMethod,
        payment_type: 'interim',
      });
      toast.success(`${amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} ödeme başarıyla alindi`);
      setPaymentDialog(false);
      setPaymentTarget(null);
      onDataRefresh?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Ödeme işlemi başarısız');
    } finally {
      setPaymentLoading(false);
    }
  }, [paymentTarget, paymentAmount, paymentMethod, onDataRefresh]);

  // Open quick reservation dialog for an empty room
  const handleQuickResOpen = useCallback((e, room) => {
    e.stopPropagation();
    setQuickResRoom(room);
    setQuickResForm({ guest_name: '', check_in: today, check_out: tomorrow, total_amount: '' });
    setSelectedGuest(null);
    setGuestSearchQuery('');
    setGuestSearchResults([]);
    setShowGuestDropdown(false);
    setQuickResDialog(true);
  }, [today, tomorrow]);

  // Guest search with debounce
  const handleGuestSearch = useCallback((query) => {
    setGuestSearchQuery(query);
    setQuickResForm(f => ({ ...f, guest_name: query }));
    setSelectedGuest(null);

    if (guestSearchTimerRef.current) clearTimeout(guestSearchTimerRef.current);

    if (query.trim().length < 2) {
      setGuestSearchResults([]);
      setShowGuestDropdown(false);
      return;
    }

    setGuestSearchLoading(true);
    guestSearchTimerRef.current = setTimeout(async () => {
      try {
        const res = await axios.get(`/pms/guests/search?q=${encodeURIComponent(query.trim())}&limit=8`);
        setGuestSearchResults(res.data || []);
        setShowGuestDropdown(true);
      } catch {
        setGuestSearchResults([]);
      } finally {
        setGuestSearchLoading(false);
      }
    }, 300);
  }, []);

  // Select an existing guest from search results
  const handleSelectGuest = useCallback((guest) => {
    setSelectedGuest(guest);
    setGuestSearchQuery(guest.name);
    setQuickResForm(f => ({ ...f, guest_name: guest.name }));
    setShowGuestDropdown(false);
    setGuestSearchResults([]);
  }, []);

  // Clear selected guest
  const handleClearGuest = useCallback(() => {
    setSelectedGuest(null);
    setGuestSearchQuery('');
    setQuickResForm(f => ({ ...f, guest_name: '' }));
    setGuestSearchResults([]);
    setShowGuestDropdown(false);
  }, []);

  // Submit quick reservation
  const handleQuickResSubmit = useCallback(async () => {
    if (!quickResRoom) return;
    const { guest_name, check_in, check_out, total_amount } = quickResForm;
    if (!guest_name.trim()) { toast.error('Misafir adi giriniz'); return; }
    if (!check_in || !check_out) { toast.error('Tarih seciniz'); return; }
    if (check_in >= check_out) { toast.error('Çıkış tarihi giristen sonra olmalidir'); return; }
    const amount = parseFloat(total_amount);
    if (!amount || amount <= 0) { toast.error('Geçerli bir fiyat giriniz'); return; }

    setQuickResLoading(true);
    try {
      const idempotencyKey = globalThis.crypto?.randomUUID?.() || `quick-booking-${Date.now()}-${Math.random()}`;
      const payload = {
        guest_name: guest_name.trim(),
        room_id: quickResRoom.id,
        check_in: check_in + 'T14:00:00+00:00',
        check_out: check_out + 'T11:00:00+00:00',
        total_amount: amount,
      };
      if (selectedGuest?.id) {
        payload.guest_id = selectedGuest.id;
      }
      await axios.post('/pms/quick-booking', payload, { headers: { 'Idempotency-Key': idempotencyKey } });
      toast.success(`Oda ${quickResRoom.room_number} için rezervasyon oluşturuldu`);
      setQuickResDialog(false);
      setQuickResRoom(null);
      onDataRefresh?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Rezervasyon oluşturulamadı');
    } finally {
      setQuickResLoading(false);
    }
  }, [quickResRoom, quickResForm, selectedGuest, onDataRefresh]);



  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold">{t('pms.rooms')} ({rooms.length})</h2>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder={t('pms.roomType')} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'Tüm Tipler'}</SelectItem>
            {allTypes.map(t2 => <SelectItem key={t2} value={t2}>{t2}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={viewFilter} onValueChange={setViewFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder={t('common.view')} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'Tüm Manzaralar'}</SelectItem>
            {allViews.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={amenityFilter} onValueChange={setAmenityFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Ozellik" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'Tüm Ozellikler'}</SelectItem>
            {allAmenities.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Legend */}
      <div className="flex gap-4 flex-wrap text-xs">
        <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-green-500" /> Iceride</div>
        <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-orange-500" /> Yarin Çıkış</div>
        <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-red-500" /> Bugün Çıkış</div>
        <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-purple-500" /> Giriş Bekleniyor</div>
        <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-yellow-400" /> Kirli</div>
        <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-gray-300" /> Bos</div>
      </div>

      {/* Room Grid */}
      {filteredRooms.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <span className="text-4xl block mb-2">🏨</span>
          <p className="text-sm">Secili filtreye uygun oda bulunamadı</p>
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {filteredRooms.map(room => {
          const guestInfo = roomGuestMap[String(room.room_number)];
          const showCheckIn = guestInfo && guestInfo.isCheckInToday && (guestInfo.status === 'confirmed' || guestInfo.status === 'guaranteed');
          const showCheckOut = guestInfo && guestInfo.isCheckOutToday && guestInfo.status === 'checked_in';
          const hasBalance = guestInfo && guestInfo.balance > 0.01;
          const isOccupied = guestInfo && guestInfo.status === 'checked_in';
          const cat = guestInfo?.category;
          const cardExtra = cat ? categoryStyles[cat] : (room.status === 'dirty' || room.status === 'cleaning') ? 'border-l-4 border-l-yellow-400' : '';
          const catLabel = cat ? categoryLabels[cat] : null;
          const guestBg = cat ? guestSectionStyles[cat] : 'bg-blue-50 border-blue-100';
          const gText = cat ? guestTextStyles[cat] : { icon: 'text-blue-600', name: 'text-blue-800', date: 'text-blue-500', link: 'text-blue-400', hoverBg: 'hover:bg-blue-100' };

          const statusColors = {
            available: 'bg-green-100 text-green-800',
            occupied: 'bg-blue-100 text-blue-800',
            dirty: 'bg-yellow-100 text-yellow-800',
            cleaning: 'bg-orange-100 text-orange-800',
            maintenance: 'bg-red-100 text-red-800',
            out_of_order: 'bg-gray-100 text-gray-800',
            inspected: 'bg-purple-100 text-purple-800',
          };

          return (
            <Card
              key={room.id}
              className={`hover:shadow-md transition-all ${cardExtra}`}
              data-testid={`room-card-${room.room_number}`}
            >
              <CardContent className="p-3">
                <div className="flex justify-between items-start mb-2">
                  <span className="text-lg font-bold" style={{ fontFamily: 'Manrope' }}>{room.room_number}</span>
                  <div className="flex gap-1 items-center">
                    {catLabel && <Badge className={`text-[10px] ${catLabel.cls}`}>{catLabel.text}</Badge>}
                    <Badge className={statusColors[room.status] || 'bg-gray-100'}>{room.status}</Badge>
                  </div>
                </div>
                <p className="text-sm text-gray-600">{room.room_type}</p>
                <p className="text-xs text-gray-400">Kat {room.floor} &bull; {room.capacity} kisi</p>

                {/* Live cleaning indicator for dirty/cleaning rooms */}
                {(room.status === 'dirty' || room.status === 'cleaning') && (
                  <div className="mt-2 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5" data-testid={`room-cleaning-${room.room_number}`}>
                    <div className="flex items-center justify-between text-[10px] text-amber-700 mb-1">
                      <span className="flex items-center gap-1">
                        <span className={`w-1.5 h-1.5 rounded-full ${room.status === 'cleaning' ? 'bg-amber-500 animate-pulse' : 'bg-amber-300'}`} />
                        {room.status === 'cleaning' ? 'Temizleniyor' : 'Temizlik bekliyor'}
                      </span>
                      <span className="font-medium">~{room.cleaning_time || (room.status === 'cleaning' ? '8' : '15')} dk</span>
                    </div>
                    {room.status === 'cleaning' && (
                      <div className="w-full h-1 bg-amber-200 rounded-full overflow-hidden">
                        <div className="h-full bg-amber-500 rounded-full animate-pulse" style={{ width: '60%' }} />
                      </div>
                    )}
                  </div>
                )}

                {/* Next check-in indicator for available rooms with arrivals */}
                {room.status === 'available' && guestInfo && guestInfo.isCheckInToday && (
                  <div className="mt-2 bg-emerald-50 border border-emerald-200 rounded-md px-2 py-1" data-testid={`room-checkin-eta-${room.room_number}`}>
                    <span className="text-[10px] text-emerald-700 flex items-center gap-1">
                      <Calendar className="w-3 h-3" /> Giriş bekleniyor
                    </span>
                  </div>
                )}

                {/* Guest info section */}
                {guestInfo && (
                  <div
                    className={`mt-2 p-2 rounded-md border ${guestBg}`}
                    data-testid={`room-guest-${room.room_number}`}
                    onDoubleClick={(e) => handleGuestNameClick(e, guestInfo)}
                    title="Tikla: Rezervasyon detayı"
                  >
                    <div
                      className={`flex items-center gap-1.5 cursor-pointer ${gText.hoverBg} rounded px-1 -mx-1 transition-colors`}
                      onClick={(e) => handleGuestNameClick(e, guestInfo)}
                      data-testid={`guest-name-click-${room.room_number}`}
                      title="Tikla: Rezervasyon detayı"
                    >
                      <User className={`w-3.5 h-3.5 ${gText.icon} flex-shrink-0`} />
                      <span className={`text-sm font-medium ${gText.name} truncate underline decoration-dotted underline-offset-2`}>
                        {guestInfo.guest_name}
                      </span>
                      <ExternalLink className={`w-3 h-3 ${gText.link} flex-shrink-0`} />
                    </div>
                    <p className={`text-[10px] ${gText.date} mt-0.5`}>
                      {guestInfo.check_in} &rarr; {guestInfo.check_out}
                    </p>

                    {/* Balance display */}
                    {hasBalance && (
                      <div className="flex items-center gap-1 mt-1" data-testid={`room-balance-${room.room_number}`}>
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                        <span className="text-[11px] font-semibold text-amber-700">
                          Bakiye: {guestInfo.balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    )}

                    {/* Quick action buttons */}
                    <div className="flex gap-1.5 mt-2 flex-wrap">
                      {showCheckIn && (
                        <Button
                          size="sm"
                          className="h-7 text-xs bg-green-600 hover:bg-green-700 text-white px-2"
                          onClick={(e) => handleCheckInClick(e, room, guestInfo)}
                          data-testid={`room-checkin-btn-${room.room_number}`}
                        >
                          <LogIn className="w-3 h-3 mr-1" />
                          C/In
                        </Button>
                      )}
                      {showCheckOut && (
                        <Button
                          size="sm"
                          className={`h-7 text-xs px-2 ${hasBalance ? 'bg-amber-600 hover:bg-amber-700' : 'bg-red-600 hover:bg-red-700'} text-white`}
                          onClick={(e) => handleCheckOutClick(e, guestInfo)}
                          data-testid={`room-checkout-btn-${room.room_number}`}
                        >
                          <LogOut className="w-3 h-3 mr-1" />
                          C/Out
                        </Button>
                      )}
                      {isOccupied && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs px-2"
                          onClick={(e) => handlePaymentClick(e, guestInfo)}
                          data-testid={`room-payment-btn-${room.room_number}`}
                        >
                          <CreditCard className="w-3 h-3 mr-1" />
                          Ödeme
                        </Button>
                      )}
                    </div>
                  </div>
                )}

                {room.base_price && <p className="text-sm font-semibold mt-1">{room.base_price}</p>}
                <div className="flex gap-1 mt-2 flex-wrap">
                  {room.view && <Badge variant="outline" className="text-[10px]">{room.view}</Badge>}
                  {room.bed_type && <Badge variant="outline" className="text-[10px]"><BedDouble className="w-3 h-3 mr-0.5" />{room.bed_type}</Badge>}
                </div>

                {/* Quick reservation button for empty rooms */}
                {!guestInfo && room.status === 'available' && (
                  <Button
                    size="sm"
                    className="w-full mt-2 h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white"
                    onClick={(e) => handleQuickResOpen(e, room)}
                    data-testid={`quick-res-btn-${room.room_number}`}
                  >
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    Rezervasyon Yap
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Checkout Balance Warning Dialog */}
      <Dialog open={checkoutDialog} onOpenChange={(o) => !o && setCheckoutDialog(false)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-700">
              <AlertTriangle className="w-5 h-5" />
              Açık Bakiye Uyarisi
            </DialogTitle>
            <DialogDescription>
              Misafirin açık bakiyesi bulunmaktadir
            </DialogDescription>
          </DialogHeader>
          {checkoutBooking && (
            <div className="space-y-4">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-sm font-medium text-amber-900">{checkoutBooking.guest_name}</p>
                <div className="mt-2 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Toplam Tutar:</span>
                    <span className="font-medium">{checkoutBooking.total_amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Odenen:</span>
                    <span className="font-medium text-green-700">{checkoutBooking.paid_amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between border-t pt-1">
                    <span className="text-amber-800 font-semibold">Kalan Bakiye:</span>
                    <span className="font-bold text-amber-800">{checkoutBooking.balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              </div>
              <p className="text-sm text-gray-600">
                Bakiyeyi sifirlamadan check-out yapilamaz. Lutfen once ödeme aliniz.
              </p>
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  onClick={() => {
                    setCheckoutDialog(false);
                    handlePaymentClick({ stopPropagation: () => {} }, checkoutBooking);
                  }}
                  data-testid="checkout-pay-btn"
                >
                  <CreditCard className="w-4 h-4 mr-1" />
                  Ödeme Al
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setCheckoutDialog(false)}
                >
                  Kapat
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Dirty Room — Smart Decision Dialog */}
      <Dialog open={dirtyRoomDialog} onOpenChange={(o) => !o && setDirtyRoomDialog(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-700" style={{ fontFamily: 'Manrope' }}>
              <SprayCan className="w-5 h-5" />
              Kirli Oda — Karar Paneli
            </DialogTitle>
            <DialogDescription>
              Misafir check-in bekliyor, oda henüz hazir değil
            </DialogDescription>
          </DialogHeader>
          {dirtyRoomInfo && (
            <DirtyRoomDecision
              room={dirtyRoomInfo.room}
              guestInfo={dirtyRoomInfo.guestInfo}
              allRooms={rooms}
              onForceCheckIn={() => {
                setDirtyRoomDialog(false);
                handleCheckIn?.(dirtyRoomInfo.guestInfo.booking_id, true);
              }}
              onAssignAlternative={(altRoom) => {
                setDirtyRoomDialog(false);
                // For now, force check-in to dirty room with clean flag
                // In future: reassign room via API
                handleCheckIn?.(dirtyRoomInfo.guestInfo.booking_id, true);
                toast.info(`Alternatif oda ${altRoom.room_number} onerisi not edildi`);
              }}
              onCancel={() => setDirtyRoomDialog(false)}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Quick Payment Dialog */}
      <Dialog open={paymentDialog} onOpenChange={(o) => !o && setPaymentDialog(false)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wallet className="w-5 h-5 text-blue-600" />
              Hızlı Ödeme
            </DialogTitle>
            <DialogDescription>
              Ödeme bilgilerini girin
            </DialogDescription>
          </DialogHeader>
          {paymentTarget && (
            <div className="space-y-4">
              {/* Guest & balance info */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <p className="text-sm font-medium text-blue-900">{paymentTarget.guest_name}</p>
                <div className="mt-2 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Toplam Tutar:</span>
                    <span className="font-medium">{paymentTarget.total_amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Odenen:</span>
                    <span className="font-medium text-green-700">{paymentTarget.paid_amount.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between border-t pt-1">
                    <span className="text-blue-800 font-semibold">Kalan Bakiye:</span>
                    <span className="font-bold text-blue-800">{paymentTarget.balance.toLocaleString('tr-TR', { minimumFractionDigits: 2 })}</span>
                  </div>
                </div>
              </div>

              {/* Payment amount */}
              <div>
                <Label className="text-sm font-medium">Ödeme Tutari</Label>
                <div className="flex gap-2 mt-1">
                  <Input
                    type="number"
                    step="0.01"
                    min="0"
                    value={paymentAmount}
                    onChange={(e) => setPaymentAmount(e.target.value)}
                    placeholder="0.00"
                    className="flex-1"
                    data-testid="quick-payment-amount"
                  />
                  {paymentTarget.balance > 0 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs whitespace-nowrap"
                      onClick={() => setPaymentAmount(String(paymentTarget.balance))}
                      data-testid="quick-payment-fill-balance"
                    >
                      Tamamini Al
                    </Button>
                  )}
                </div>
              </div>

              {/* Payment method */}
              <div>
                <Label className="text-sm font-medium">Ödeme Yontemi</Label>
                <div className="grid grid-cols-3 gap-2 mt-1">
                  <Button
                    variant={paymentMethod === 'cash' ? 'default' : 'outline'}
                    className={`h-14 flex-col gap-1 ${paymentMethod === 'cash' ? 'bg-green-600 hover:bg-green-700' : ''}`}
                    onClick={() => setPaymentMethod('cash')}
                    data-testid="quick-payment-method-cash"
                  >
                    <Banknote className="w-5 h-5" />
                    <span className="text-xs">Nakit</span>
                  </Button>
                  <Button
                    variant={paymentMethod === 'card' ? 'default' : 'outline'}
                    className={`h-14 flex-col gap-1 ${paymentMethod === 'card' ? 'bg-blue-600 hover:bg-blue-700' : ''}`}
                    onClick={() => setPaymentMethod('card')}
                    data-testid="quick-payment-method-card"
                  >
                    <CreditCard className="w-5 h-5" />
                    <span className="text-xs">Kart</span>
                  </Button>
                  <Button
                    variant={paymentMethod === 'bank_transfer' ? 'default' : 'outline'}
                    className={`h-14 flex-col gap-1 ${paymentMethod === 'bank_transfer' ? 'bg-purple-600 hover:bg-purple-700' : ''}`}
                    onClick={() => setPaymentMethod('bank_transfer')}
                    data-testid="quick-payment-method-transfer"
                  >
                    <Building2 className="w-5 h-5" />
                    <span className="text-xs">Havale</span>
                  </Button>
                </div>
              </div>

              {/* Submit */}
              <Button
                className="w-full bg-green-600 hover:bg-green-700"
                onClick={handleQuickPayment}
                disabled={paymentLoading || !paymentAmount || parseFloat(paymentAmount) <= 0}
                data-testid="quick-payment-submit"
              >
                {paymentLoading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Isleniyor...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <Wallet className="w-4 h-4" />
                    Ödeme Al
                  </span>
                )}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Quick Reservation Dialog */}
      <Dialog open={quickResDialog} onOpenChange={(o) => { if (!o) { setQuickResDialog(false); setShowGuestDropdown(false); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CalendarPlus className="w-5 h-5 text-blue-600" />
              Hızlı Rezervasyon
            </DialogTitle>
            <DialogDescription>
              {quickResRoom ? `Oda ${quickResRoom.room_number} - ${quickResRoom.room_type}` : 'Oda bilgisi'}
            </DialogDescription>
          </DialogHeader>
          {quickResRoom && (
            <div className="space-y-4">
              {/* Guest search field */}
              <div>
                <Label className="text-sm font-medium">Misafir *</Label>
                {selectedGuest ? (
                  <div className="mt-1 flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-md p-2.5" data-testid="quick-res-selected-guest">
                    <UserCheck className="w-4 h-4 text-blue-600 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-blue-900 truncate">{selectedGuest.name}</p>
                      <p className="text-xs text-blue-600 truncate">
                        {selectedGuest.email && !selectedGuest.email.includes('placeholder') ? selectedGuest.email : ''}
                        {selectedGuest.phone ? (selectedGuest.email && !selectedGuest.email.includes('placeholder') ? ' | ' : '') + selectedGuest.phone : ''}
                        {selectedGuest.total_stays > 0 && ` | ${selectedGuest.total_stays} konaklama`}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 text-blue-400 hover:text-blue-600 hover:bg-blue-100"
                      onClick={handleClearGuest}
                      data-testid="quick-res-clear-guest"
                    >
                      &times;
                    </Button>
                  </div>
                ) : (
                  <div className="relative mt-1">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <Input
                        value={guestSearchQuery}
                        onChange={(e) => handleGuestSearch(e.target.value)}
                        onFocus={() => { if (guestSearchResults.length > 0) setShowGuestDropdown(true); }}
                        placeholder="Misafir ara veya yeni isim gir..."
                        className="pl-9"
                        autoFocus
                        data-testid="quick-res-guest-search"
                      />
                      {guestSearchLoading && (
                        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                      )}
                    </div>

                    {/* Search results dropdown */}
                    {showGuestDropdown && guestSearchResults.length > 0 && (
                      <div
                        className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto"
                        data-testid="quick-res-guest-dropdown"
                      >
                        {guestSearchResults.map((g) => (
                          <button
                            key={g.id}
                            type="button"
                            className="w-full text-left px-3 py-2 hover:bg-blue-50 border-b border-gray-50 last:border-b-0 transition-colors"
                            onClick={() => handleSelectGuest(g)}
                            data-testid={`quick-res-guest-option-${g.id}`}
                          >
                            <div className="flex items-center gap-2">
                              <UserCheck className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
                              <div className="min-w-0">
                                <p className="text-sm font-medium text-gray-900 truncate">
                                  {g.name}
                                  {g.vip_status && <span className="ml-1 text-amber-500 text-xs">VIP</span>}
                                </p>
                                <p className="text-xs text-gray-500 truncate">
                                  {g.email && !g.email.includes('placeholder') ? g.email : ''}
                                  {g.phone ? (g.email && !g.email.includes('placeholder') ? ' | ' : '') + g.phone : ''}
                                </p>
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}

                    {/* "New guest" hint when typing but no match selected */}
                    {guestSearchQuery.trim().length >= 2 && !guestSearchLoading && showGuestDropdown && guestSearchResults.length === 0 && (
                      <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg px-3 py-2">
                        <div className="flex items-center gap-2 text-gray-500">
                          <UserPlus className="w-3.5 h-3.5" />
                          <span className="text-sm">"{guestSearchQuery.trim()}" yeni misafir olarak eklenecek</span>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-sm font-medium">Giriş Tarihi *</Label>
                  <Input
                    type="date"
                    value={quickResForm.check_in}
                    onChange={(e) => setQuickResForm(f => ({ ...f, check_in: e.target.value }))}
                    className="mt-1"
                    data-testid="quick-res-check-in"
                  />
                </div>
                <div>
                  <Label className="text-sm font-medium">Çıkış Tarihi *</Label>
                  <Input
                    type="date"
                    value={quickResForm.check_out}
                    onChange={(e) => setQuickResForm(f => ({ ...f, check_out: e.target.value }))}
                    className="mt-1"
                    data-testid="quick-res-check-out"
                  />
                </div>
              </div>
              <div>
                <Label className="text-sm font-medium">Toplam Fiyat *</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={quickResForm.total_amount}
                  onChange={(e) => setQuickResForm(f => ({ ...f, total_amount: e.target.value }))}
                  placeholder="0.00"
                  className="mt-1"
                  data-testid="quick-res-total-amount"
                />
              </div>
              <Button
                className="w-full bg-blue-600 hover:bg-blue-700"
                onClick={handleQuickResSubmit}
                disabled={quickResLoading}
                data-testid="quick-res-submit"
              >
                {quickResLoading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Olusturuluyor...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <CalendarPlus className="w-4 h-4" />
                    Rezervasyon Olustur
                  </span>
                )}
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RoomsTab;

/** Smart Dirty Room Decision sub-component */
function DirtyRoomDecision({ room, guestInfo, allRooms, onForceCheckIn, onAssignAlternative, onCancel }) {
  const sameTypeClean = (allRooms || []).filter(
    r => r.status === 'available' && r.room_type === room.room_type && String(r.room_number) !== String(room.room_number)
  );
  const estimatedCleanMin = room.status === 'cleaning' ? 8 : 15;

  return (
    <div className="space-y-4" data-testid="dirty-room-decision">
      {/* Current situation */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-sm font-bold text-amber-900">Oda {room.room_number}</span>
          <Badge className="bg-yellow-100 text-yellow-800 text-[10px]">{room.status === 'cleaning' ? 'Temizleniyor' : 'Kirli'}</Badge>
        </div>
        <p className="text-sm text-amber-700">{guestInfo.guest_name}</p>
        <div className="mt-2 flex items-center gap-2 text-xs text-amber-600">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            Tahmini temizlik: ~{estimatedCleanMin} dk
          </span>
        </div>
      </div>

      {/* Alternative rooms */}
      {sameTypeClean.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Alternatif Odalar ({room.room_type})</p>
          <div className="space-y-1.5">
            {sameTypeClean.slice(0, 3).map(alt => (
              <div
                key={alt.id}
                className="flex items-center justify-between bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 hover:bg-emerald-100 transition-colors"
                data-testid={`alt-room-${alt.room_number}`}
              >
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-md bg-emerald-100 flex items-center justify-center">
                    <BedDouble className="w-4 h-4 text-emerald-700" />
                  </div>
                  <div>
                    <span className="text-sm font-semibold text-emerald-800">Oda {alt.room_number}</span>
                    <span className="text-[10px] text-emerald-600 ml-2">Kat {alt.floor}</span>
                  </div>
                </div>
                <Button
                  size="sm"
                  className="h-7 text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                  onClick={() => onAssignAlternative(alt)}
                  data-testid={`assign-alt-${alt.room_number}`}
                >
                  Bu Odaya Ata
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {sameTypeClean.length === 0 && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-center">
          <p className="text-xs text-slate-500">Ayni tipte bos oda yok. Bekle ve temizle secenegini kullanin.</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 pt-1">
        <Button
          className="flex-1 bg-[#C09D63] hover:bg-[#B08D55] text-white"
          onClick={onForceCheckIn}
          data-testid="dirty-room-checkin-btn"
        >
          <SprayCan className="w-4 h-4 mr-1" />
          Temizle ve Giriş Yap
        </Button>
        <Button variant="outline" onClick={onCancel} data-testid="dirty-room-cancel-btn">
          Bekle
        </Button>
      </div>
    </div>
  );
}
