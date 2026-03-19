import React, { useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { BedDouble, User, LogIn, LogOut, CreditCard, AlertTriangle, IdCard, SprayCan } from 'lucide-react';

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

  // Quick identity dialog state
  const [identityDialog, setIdentityDialog] = useState(false);
  const [identityGuest, setIdentityGuest] = useState(null);
  const [savingIdentity, setSavingIdentity] = useState(false);

  // Checkout confirmation dialog state
  const [checkoutDialog, setCheckoutDialog] = useState(false);
  const [checkoutBooking, setCheckoutBooking] = useState(null);

  // Dirty room check-in dialog state
  const [dirtyRoomDialog, setDirtyRoomDialog] = useState(false);
  const [dirtyRoomInfo, setDirtyRoomInfo] = useState(null);

  const today = useMemo(() => new Date().toISOString().split('T')[0], []);

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
        };
      }
    }
    return map;
  }, [bookings, today]);

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

  const statusColors = {
    available: 'bg-green-100 text-green-800',
    occupied: 'bg-blue-100 text-blue-800',
    dirty: 'bg-yellow-100 text-yellow-800',
    cleaning: 'bg-orange-100 text-orange-800',
    maintenance: 'bg-red-100 text-red-800',
    out_of_order: 'bg-gray-100 text-gray-800',
    inspected: 'bg-purple-100 text-purple-800',
  };

  // Handle guest name click -> open identity dialog
  const handleGuestNameClick = useCallback((e, guestInfo) => {
    e.stopPropagation();
    if (!guestInfo.guest_id) return;

    // Find full guest data
    const guest = guests.find(g => g.id === guestInfo.guest_id);
    if (guest) {
      setIdentityGuest({ ...guest });
      setIdentityDialog(true);
    } else {
      // Fetch guest from API if not in local list
      axios.get(`/pms/guests/${guestInfo.guest_id}`).then(res => {
        setIdentityGuest({ ...res.data });
        setIdentityDialog(true);
      }).catch(() => {
        toast.error('Misafir bilgisi yüklenemedi');
      });
    }
  }, [guests]);

  // Handle double-click on guest area -> open booking detail
  const handleGuestDoubleClick = useCallback((e, guestInfo) => {
    e.stopPropagation();
    if (!guestInfo.booking_id) return;
    const booking = bookings.find(b => b.id === guestInfo.booking_id);
    if (booking && onBookingDoubleClick) {
      onBookingDoubleClick(booking);
    }
  }, [bookings, onBookingDoubleClick]);

  // Save identity info
  const handleSaveIdentity = async () => {
    if (!identityGuest) return;
    setSavingIdentity(true);
    try {
      await axios.put(`/pms/guests/${identityGuest.id}`, identityGuest);
      toast.success('Kimlik bilgileri kaydedildi');
      setIdentityDialog(false);
      onDataRefresh?.();
    } catch (error) {
      toast.error('Kimlik bilgileri kaydedilemedi');
    } finally {
      setSavingIdentity(false);
    }
  };

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
            <SelectItem value="all">{t('common.filter') || 'Tum Tipler'}</SelectItem>
            {allTypes.map(t2 => <SelectItem key={t2} value={t2}>{t2}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={viewFilter} onValueChange={setViewFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder={t('common.view')} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'Tum Manzaralar'}</SelectItem>
            {allViews.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={amenityFilter} onValueChange={setAmenityFilter}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Ozellik" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('common.filter') || 'Tum Ozellikler'}</SelectItem>
            {allAmenities.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Room Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {filteredRooms.map(room => {
          const guestInfo = roomGuestMap[String(room.room_number)];
          const showCheckIn = guestInfo && guestInfo.isCheckInToday && (guestInfo.status === 'confirmed' || guestInfo.status === 'guaranteed');
          const showCheckOut = guestInfo && guestInfo.isCheckOutToday && guestInfo.status === 'checked_in';
          const hasBalance = guestInfo && guestInfo.balance > 0.01;
          const isOccupied = guestInfo && guestInfo.status === 'checked_in';

          return (
            <Card
              key={room.id}
              className="hover:shadow-md transition-all"
              data-testid={`room-card-${room.room_number}`}
            >
              <CardContent className="p-3">
                <div className="flex justify-between items-start mb-2">
                  <span className="text-lg font-bold">{room.room_number}</span>
                  <Badge className={statusColors[room.status] || 'bg-gray-100'}>{room.status}</Badge>
                </div>
                <p className="text-sm text-gray-600">{room.room_type}</p>
                <p className="text-xs text-gray-400">Kat {room.floor} &bull; {room.capacity} kisi</p>

                {/* Guest info section */}
                {guestInfo && (
                  <div
                    className="mt-2 p-2 bg-blue-50 rounded-md border border-blue-100"
                    data-testid={`room-guest-${room.room_number}`}
                    onDoubleClick={(e) => handleGuestDoubleClick(e, guestInfo)}
                    title="Cift tikla: Rezervasyon detayi"
                  >
                    <div
                      className="flex items-center gap-1.5 cursor-pointer hover:bg-blue-100 rounded px-1 -mx-1 transition-colors"
                      onClick={(e) => handleGuestNameClick(e, guestInfo)}
                      data-testid={`guest-name-click-${room.room_number}`}
                      title="Tikla: Kimlik bilgileri"
                    >
                      <User className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" />
                      <span className="text-sm font-medium text-blue-800 truncate underline decoration-dotted underline-offset-2">
                        {guestInfo.guest_name}
                      </span>
                      <IdCard className="w-3 h-3 text-blue-400 flex-shrink-0" />
                    </div>
                    <p className="text-[10px] text-blue-500 mt-0.5">
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
                          onClick={(e) => { e.stopPropagation(); onPayment?.(guestInfo.booking_id); }}
                          data-testid={`room-payment-btn-${room.room_number}`}
                        >
                          <CreditCard className="w-3 h-3 mr-1" />
                          Odeme
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
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Quick Identity Dialog */}
      <Dialog open={identityDialog} onOpenChange={(o) => !o && setIdentityDialog(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <IdCard className="w-5 h-5" />
              Kimlik Bilgileri
            </DialogTitle>
            <DialogDescription>Misafir kimlik bilgilerini giriniz</DialogDescription>
          </DialogHeader>
          {identityGuest && (
            <div className="space-y-4">
              <div>
                <Label>Ad Soyad</Label>
                <Input
                  value={identityGuest.name || ''}
                  onChange={(e) => setIdentityGuest({ ...identityGuest, name: e.target.value })}
                  data-testid="identity-name-input"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Kimlik Tipi</Label>
                  <Select
                    value={identityGuest.id_type || 'national_id'}
                    onValueChange={(v) => setIdentityGuest({ ...identityGuest, id_type: v })}
                  >
                    <SelectTrigger data-testid="identity-type-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="national_id">TC Kimlik</SelectItem>
                      <SelectItem value="passport">Pasaport</SelectItem>
                      <SelectItem value="drivers_license">Ehliyet</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Kimlik No</Label>
                  <Input
                    value={identityGuest.id_number || ''}
                    onChange={(e) => setIdentityGuest({ ...identityGuest, id_number: e.target.value })}
                    placeholder="Kimlik/Pasaport No"
                    data-testid="identity-number-input"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Uyruk</Label>
                  <Input
                    value={identityGuest.nationality || ''}
                    onChange={(e) => setIdentityGuest({ ...identityGuest, nationality: e.target.value })}
                    placeholder="TR"
                    data-testid="identity-nationality-input"
                  />
                </div>
                <div>
                  <Label>Dogum Tarihi</Label>
                  <Input
                    type="date"
                    value={identityGuest.date_of_birth?.split('T')[0] || ''}
                    onChange={(e) => setIdentityGuest({ ...identityGuest, date_of_birth: e.target.value })}
                    data-testid="identity-dob-input"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t">
                <Button variant="outline" onClick={() => setIdentityDialog(false)}>Iptal</Button>
                <Button onClick={handleSaveIdentity} disabled={savingIdentity} data-testid="identity-save-btn">
                  {savingIdentity ? 'Kaydediliyor...' : 'Kaydet'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Checkout Balance Warning Dialog */}
      <Dialog open={checkoutDialog} onOpenChange={(o) => !o && setCheckoutDialog(false)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-700">
              <AlertTriangle className="w-5 h-5" />
              Acik Bakiye Uyarisi
            </DialogTitle>
            <DialogDescription>
              Misafirin acik bakiyesi bulunmaktadir
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
                Bakiyeyi sifirlamadan check-out yapilamaz. Lutfen once odeme aliniz.
              </p>
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  onClick={() => {
                    setCheckoutDialog(false);
                    onPayment?.(checkoutBooking.booking_id);
                  }}
                  data-testid="checkout-pay-btn"
                >
                  <CreditCard className="w-4 h-4 mr-1" />
                  Odeme Al
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

      {/* Dirty Room Check-in Warning Dialog */}
      <Dialog open={dirtyRoomDialog} onOpenChange={(o) => !o && setDirtyRoomDialog(false)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-700">
              <SprayCan className="w-5 h-5" />
              Kirli Oda Uyarisi
            </DialogTitle>
            <DialogDescription>
              Bu oda henuz temizlenmemis durumda
            </DialogDescription>
          </DialogHeader>
          {dirtyRoomInfo && (
            <div className="space-y-4">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium text-amber-900">Oda {dirtyRoomInfo.room.room_number}</span>
                  <Badge className="bg-yellow-100 text-yellow-800">{dirtyRoomInfo.room.status}</Badge>
                </div>
                <p className="text-sm text-amber-700 mt-1">{dirtyRoomInfo.guestInfo.guest_name}</p>
              </div>
              <p className="text-sm text-gray-600">
                Bu oda kirli durumda. Odayi temiz olarak isaretleyip check-in yapmak ister misiniz?
              </p>
              <div className="flex gap-2">
                <Button
                  className="flex-1 bg-green-600 hover:bg-green-700"
                  onClick={() => {
                    setDirtyRoomDialog(false);
                    handleCheckIn?.(dirtyRoomInfo.guestInfo.booking_id, true);
                  }}
                  data-testid="dirty-room-checkin-btn"
                >
                  <SprayCan className="w-4 h-4 mr-1" />
                  Temizle ve Check-in Yap
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setDirtyRoomDialog(false)}
                  data-testid="dirty-room-cancel-btn"
                >
                  Iptal
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RoomsTab;
