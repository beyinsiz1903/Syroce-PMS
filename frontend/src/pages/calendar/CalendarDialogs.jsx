import React, { useState, useCallback, useRef, useEffect } from "react";
import axios from "axios";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Search, CheckCircle, AlertCircle, Clock, UserCheck, UserPlus } from "lucide-react";
import { getSegmentColor, getStatusColor, getStatusLabel } from "./calendarHelpers";

// New Booking Dialog
export const NewBookingDialog = ({
  open, onOpenChange, newBooking, setNewBooking,
  selectedRoom, guests, rooms, onSubmit, minDate,
}) => {
  const roomTypes = rooms ? [...new Set(rooms.map(r => r.room_type).filter(Boolean))] : [];
  const effectiveMinDate = minDate || new Date().toISOString().split('T')[0];

  // Guest search state
  const [guestSearchQuery, setGuestSearchQuery] = useState('');
  const [guestSearchResults, setGuestSearchResults] = useState([]);
  const [guestSearchLoading, setGuestSearchLoading] = useState(false);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [showGuestDropdown, setShowGuestDropdown] = useState(false);
  const guestSearchTimerRef = useRef(null);

  // Reset guest search state when dialog opens/closes
  useEffect(() => {
    if (!open) {
      setGuestSearchQuery('');
      setGuestSearchResults([]);
      setSelectedGuest(null);
      setShowGuestDropdown(false);
    }
  }, [open]);

  // Guest search with debounce
  const handleGuestSearch = useCallback((query) => {
    setGuestSearchQuery(query);
    setSelectedGuest(null);
    // Also update newBooking for new guest creation fallback
    setNewBooking(prev => ({ ...prev, guest_id: '', guest_name: query }));

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
  }, [setNewBooking]);

  // Select an existing guest from search results
  const handleSelectGuest = useCallback((guest) => {
    setSelectedGuest(guest);
    setGuestSearchQuery(guest.name);
    setShowGuestDropdown(false);
    setGuestSearchResults([]);
    setNewBooking(prev => ({ ...prev, guest_id: guest.id, guest_name: guest.name }));
  }, [setNewBooking]);

  // Clear selected guest
  const handleClearGuest = useCallback(() => {
    setSelectedGuest(null);
    setGuestSearchQuery('');
    setGuestSearchResults([]);
    setShowGuestDropdown(false);
    setNewBooking(prev => ({ ...prev, guest_id: '', guest_name: '' }));
  }, [setNewBooking]);

  return (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-2xl">
      <DialogHeader>
        <DialogTitle>Hizli Rezervasyon</DialogTitle>
      </DialogHeader>
      <form onSubmit={onSubmit} className="space-y-4">
        {selectedRoom ? (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3" data-testid="selected-room-info">
            <div className="text-xs text-blue-600 font-medium mb-1">Secilen Oda</div>
            <div className="font-bold text-lg text-gray-900">
              Oda {selectedRoom.room_number}
              <span className="text-sm font-normal text-gray-500 ml-2">
                {selectedRoom.room_type} - Kat {selectedRoom.floor}
              </span>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Oda Tipi</Label>
              <select
                className="w-full border rounded-md p-2"
                value={newBooking.room_type || ''}
                onChange={(e) => {
                  setNewBooking({...newBooking, room_type: e.target.value, room_id: ''});
                }}
                data-testid="new-booking-room-type"
              >
                <option value="">Oda tipi seçin...</option>
                {roomTypes.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <Label>Oda</Label>
              <select
                className="w-full border rounded-md p-2"
                value={newBooking.room_id || ''}
                onChange={(e) => setNewBooking({...newBooking, room_id: e.target.value})}
                data-testid="new-booking-room-select"
              >
                <option value="">Oda seçin...</option>
                {(rooms || [])
                  .filter(r => !newBooking.room_type || r.room_type === newBooking.room_type)
                  .map(r => (
                    <option key={r.id} value={r.id}>{r.room_number} - {r.room_type} (Kat: {r.floor})</option>
                  ))
                }
              </select>
            </div>
          </div>
        )}

        {/* Guest search field */}
        <div>
          <Label>Misafir *</Label>
          {selectedGuest ? (
            <div className="mt-1 flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-md p-2.5" data-testid="new-booking-selected-guest">
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
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-blue-400 hover:text-blue-600 hover:bg-blue-100"
                onClick={handleClearGuest}
                data-testid="new-booking-clear-guest"
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
                  data-testid="new-booking-guest-search"
                />
                {guestSearchLoading && (
                  <span className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                )}
              </div>

              {/* Search results dropdown */}
              {showGuestDropdown && guestSearchResults.length > 0 && (
                <div
                  className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto"
                  data-testid="new-booking-guest-dropdown"
                >
                  {guestSearchResults.map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-blue-50 border-b border-gray-50 last:border-b-0 transition-colors"
                      onClick={() => handleSelectGuest(g)}
                      data-testid={`new-booking-guest-option-${g.id}`}
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

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Check-in</Label>
            <Input
              type="date"
              value={newBooking.check_in}
              min={effectiveMinDate}
              onChange={(e) => {
                const newCi = e.target.value;
                const updates = {...newBooking, check_in: newCi};
                if (newCi && (!newBooking.check_out || newBooking.check_out <= newCi)) {
                  const nextDay = new Date(newCi + 'T00:00:00');
                  nextDay.setDate(nextDay.getDate() + 1);
                  updates.check_out = nextDay.toISOString().split('T')[0];
                }
                setNewBooking(updates);
              }}
              required
              data-testid="new-booking-checkin"
            />
          </div>
          <div>
            <Label>Check-out</Label>
            <Input
              type="date"
              value={newBooking.check_out}
              min={newBooking.check_in || effectiveMinDate}
              onChange={(e) => setNewBooking({...newBooking, check_out: e.target.value})}
              required
              data-testid="new-booking-checkout"
            />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <Label>Yetiskin</Label>
            <Input
              type="number"
              min="1"
              value={newBooking.adults}
              onChange={(e) => setNewBooking({
                ...newBooking,
                adults: Number(e.target.value),
                guests_count: Number(e.target.value) + newBooking.children
              })}
            />
          </div>
          <div>
            <Label>Cocuk</Label>
            <Input
              type="number"
              min="0"
              value={newBooking.children}
              onChange={(e) => setNewBooking({
                ...newBooking,
                children: Number(e.target.value),
                guests_count: newBooking.adults + Number(e.target.value)
              })}
            />
          </div>
          <div>
            <Label>Toplam Tutar</Label>
            <Input
              type="number"
              step="0.01"
              value={newBooking.total_amount}
              onChange={(e) => setNewBooking({...newBooking, total_amount: Number(e.target.value)})}
            />
          </div>
        </div>
        <div>
          <Label>Durum</Label>
          <select
            className="w-full border rounded-md p-2"
            value={newBooking.status}
            onChange={(e) => setNewBooking({...newBooking, status: e.target.value})}
          >
            <option value="confirmed">Onaylandi</option>
            <option value="guaranteed">Garantili</option>
            <option value="checked_in">Giris Yapildi</option>
          </select>
        </div>
        <div className="flex space-x-2 pt-4">
          <Button type="submit" className="flex-1" data-testid="new-booking-submit">Rezervasyon Olustur</Button>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>İptal</Button>
        </div>
      </form>
    </DialogContent>
  </Dialog>
  );
};

// Inline room-change panel used inside BookingDetailsDialog.
// Loads availability for this booking's date range, lets the user pick
// a new room (same or different type), and — when the type changes —
// asks whether to keep the current price or enter a new one.
const RoomChangePanel = ({ booking, onMoved, onClose }) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [available, setAvailable] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [keepPrice, setKeepPrice] = useState(true);
  const [newPrice, setNewPrice] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const nights = Math.max(
    1,
    Math.ceil((new Date(booking.check_out) - new Date(booking.check_in)) / (1000 * 60 * 60 * 24)),
  );
  const currentRate = booking.total_amount ? booking.total_amount / nights : 0;

  const loadAvailable = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/pms/bookings/${booking.id}/available-rooms`);
      const data = Array.isArray(res.data) ? res.data : (res.data?.rooms || []);
      data.sort((a, b) => (b.is_same_type ? 1 : 0) - (a.is_same_type ? 1 : 0));
      setAvailable(data);
    } catch (err) {
      console.error('available-rooms error', err);
      setAvailable([]);
    } finally {
      setLoading(false);
    }
  }, [booking.id]);

  const togglePanel = () => {
    const next = !open;
    setOpen(next);
    if (next && available.length === 0 && !loading) loadAvailable();
  };

  const handleSelect = (room) => {
    setSelectedRoom(room);
    if (room.is_same_type) {
      setKeepPrice(true);
      setNewPrice('');
    } else {
      setKeepPrice(true);
      setNewPrice(String(((room.price_per_night || 0) * nights).toFixed(2)));
    }
  };

  const handleConfirm = async () => {
    if (!selectedRoom) return;
    if (!reason.trim()) { alert('Lütfen oda değişim nedenini seçin'); return; }
    const sameType = selectedRoom.is_same_type;
    const useNewPrice = !sameType && !keepPrice;
    const payload = {
      room_id: selectedRoom.id,
      room_type: selectedRoom.room_type,
      room_change_reason: reason,
    };
    if (useNewPrice) {
      const amount = parseFloat(newPrice);
      if (Number.isNaN(amount) || amount < 0) { alert('Geçerli bir fiyat girin'); return; }
      payload.total_amount = amount;
    }
    setSubmitting(true);
    try {
      const idemKey = globalThis.crypto?.randomUUID?.() || `room-change-${Date.now()}`;
      await axios.put(`/pms/bookings/${booking.id}`, payload, {
        headers: { 'Idempotency-Key': idemKey },
      });
      await axios.post('/pms/room-move-history', {
        booking_id: booking.id,
        old_room: booking.room_number || booking.room_id,
        new_room: selectedRoom.room_number,
        to_room_id: selectedRoom.id,
        reason,
        timestamp: new Date().toISOString(),
      }).catch(() => {});
      if (onMoved) onMoved();
      if (onClose) onClose();
    } catch (err) {
      console.error('room change error', err);
      alert(err.response?.data?.detail || 'Oda değiştirilemedi');
    } finally {
      setSubmitting(false);
    }
  };

  const sameType = available.filter((r) => r.is_same_type);
  const otherType = available.filter((r) => !r.is_same_type);

  return (
    <div className="border rounded-lg bg-amber-50 border-amber-200">
      <button
        type="button"
        onClick={togglePanel}
        className="w-full text-left px-3 py-2 text-sm font-semibold text-amber-900 flex items-center justify-between"
        data-testid="toggle-room-change"
      >
        <span>Oda Değiştir / Move Room</span>
        <span className="text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-3">
          {loading && <div className="text-sm text-gray-600">Müsait odalar yükleniyor...</div>}
          {!loading && available.length === 0 && (
            <div className="text-sm text-gray-600">Bu tarih aralığı için müsait oda bulunamadı.</div>
          )}
          {!loading && sameType.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-700 mb-1">Aynı oda tipi</div>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {sameType.map((r) => (
                  <button
                    type="button"
                    key={r.id}
                    onClick={() => handleSelect(r)}
                    className={`w-full text-left px-2 py-1.5 text-sm rounded border ${
                      selectedRoom?.id === r.id ? 'bg-blue-100 border-blue-400' : 'bg-white border-gray-200 hover:bg-gray-50'
                    }`}
                    data-testid={`pick-room-${r.room_number}`}
                  >
                    <span className="font-semibold">Oda {r.room_number}</span>
                    <span className="text-gray-500 ml-2">{r.room_type} · Kat {r.floor}</span>
                    <span className="text-gray-500 ml-2">${r.price_per_night}/gece</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {!loading && otherType.length > 0 && (
            <div>
              <div className="text-xs font-semibold text-gray-700 mb-1">Farklı oda tipi</div>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {otherType.map((r) => (
                  <button
                    type="button"
                    key={r.id}
                    onClick={() => handleSelect(r)}
                    className={`w-full text-left px-2 py-1.5 text-sm rounded border ${
                      selectedRoom?.id === r.id ? 'bg-blue-100 border-blue-400' : 'bg-white border-gray-200 hover:bg-gray-50'
                    }`}
                    data-testid={`pick-room-${r.room_number}`}
                  >
                    <span className="font-semibold">Oda {r.room_number}</span>
                    <span className="text-gray-500 ml-2">{r.room_type} · Kat {r.floor}</span>
                    <span className="text-gray-500 ml-2">${r.price_per_night}/gece</span>
                    {r.is_upgrade && <Badge className="ml-2 bg-purple-100 text-purple-800">Upgrade</Badge>}
                  </button>
                ))}
              </div>
            </div>
          )}

          {selectedRoom && !selectedRoom.is_same_type && (
            <div className="bg-white border rounded p-2 space-y-2">
              <div className="text-xs font-semibold text-gray-700">Fiyat değişikliği</div>
              <label className="flex items-center text-sm gap-2">
                <input type="radio" checked={keepPrice} onChange={() => setKeepPrice(true)} />
                Mevcut fiyatı koru (${currentRate.toFixed(2)}/gece · ${booking.total_amount})
              </label>
              <label className="flex items-center text-sm gap-2">
                <input type="radio" checked={!keepPrice} onChange={() => setKeepPrice(false)} />
                Yeni toplam fiyat gir
              </label>
              {!keepPrice && (
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={newPrice}
                  onChange={(e) => setNewPrice(e.target.value)}
                  placeholder="Toplam tutar"
                  data-testid="room-change-price"
                />
              )}
            </div>
          )}

          {selectedRoom && (
            <div>
              <Label className="text-xs">Değişim Nedeni *</Label>
              <select
                className="w-full border rounded-md p-1.5 text-sm"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                data-testid="room-change-reason"
              >
                <option value="">Seçin...</option>
                <option value="Guest Request">Misafir Talebi</option>
                <option value="Room Maintenance">Oda Bakımı</option>
                <option value="Upgrade">Upgrade</option>
                <option value="Downgrade">Downgrade</option>
                <option value="Overbooking">Overbooking Çözümü</option>
                <option value="VIP Guest">VIP Misafir</option>
                <option value="Room Issue">Oda Sorunu</option>
                <option value="Operational">Operasyonel</option>
              </select>
            </div>
          )}

          {selectedRoom && (
            <Button
              onClick={handleConfirm}
              disabled={submitting || !reason}
              className="w-full"
              data-testid="confirm-room-change"
            >
              {submitting ? 'Kaydediliyor...' : `Oda ${selectedRoom.room_number}'a Taşı`}
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

// Booking Details Dialog
export const BookingDetailsDialog = ({
  open, onOpenChange, selectedBooking, rooms, onEdit, onMoved,
}) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle>Booking Details</DialogTitle>
      </DialogHeader>
      {selectedBooking && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-gray-600">Guest Name</div>
              <div className="text-lg font-semibold">{selectedBooking.guest_name}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Status</div>
              <div className="flex items-center space-x-2">
                <Badge className={getSegmentColor(selectedBooking.market_segment)}>
                  {selectedBooking.market_segment || 'Standard'}
                </Badge>
                <Badge className={getStatusColor(selectedBooking.status)}>
                  {getStatusLabel(selectedBooking.status)}
                </Badge>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-gray-600">Check-in</div>
              <div className="font-semibold">{selectedBooking.check_in}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Check-out</div>
              <div className="font-semibold">{selectedBooking.check_out}</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-gray-600">Room</div>
              <div className="font-semibold">
                {rooms.find(r => r.id === selectedBooking.room_id)?.room_number}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Total Amount</div>
              <div className="font-semibold">${selectedBooking.total_amount}</div>
            </div>
          </div>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
            <div className="text-sm font-semibold text-blue-900 mb-2">Rate Details</div>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-gray-600">ADR</div>
                <div className="font-bold text-lg">
                  ${selectedBooking.total_amount ?
                    (selectedBooking.total_amount /
                    Math.ceil((new Date(selectedBooking.check_out) - new Date(selectedBooking.check_in)) / (1000 * 60 * 60 * 24))).toFixed(2)
                    : '0.00'}
                </div>
              </div>
              {selectedBooking.rate_type && (
                <div>
                  <div className="text-gray-600">Rate Code</div>
                  <div className="font-semibold text-blue-600 uppercase">{selectedBooking.rate_type}</div>
                </div>
              )}
              {selectedBooking.market_segment && (
                <div>
                  <div className="text-gray-600">Segment</div>
                  <div className="font-semibold text-blue-600 capitalize">{selectedBooking.market_segment}</div>
                </div>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-gray-600">Adults</div>
              <div className="font-semibold">{selectedBooking.adults}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Children</div>
              <div className="font-semibold">{selectedBooking.children}</div>
            </div>
          </div>
          {selectedBooking.company_name && (
            <div>
              <div className="text-sm text-gray-600">Company</div>
              <div className="font-semibold">{selectedBooking.company_name}</div>
            </div>
          )}
          <div className="border-t pt-4">
            <div className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
              <Clock className="w-4 h-4 mr-2" />
              Room Move History
            </div>
            {selectedBooking.room_moves && selectedBooking.room_moves.length > 0 ? (
              <div className="space-y-2">
                {selectedBooking.room_moves.map((move, idx) => (
                  <div key={idx} className="bg-gray-50 border border-gray-200 rounded p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-semibold">Room {move.old_room}</span>
                        <span className="mx-2 text-gray-400">-&gt;</span>
                        <span className="font-semibold">Room {move.new_room}</span>
                      </div>
                      <div className="text-xs text-gray-500">
                        {new Date(move.timestamp).toLocaleString()}
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-gray-600"><strong>Reason:</strong> {move.reason}</div>
                    <div className="mt-1 text-xs text-gray-500">Moved by: {move.moved_by}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-500 italic">No room moves recorded</div>
            )}
          </div>
          <RoomChangePanel
            booking={selectedBooking}
            onMoved={onMoved}
            onClose={() => onOpenChange(false)}
          />
          <div className="flex space-x-2 pt-4 border-t">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
            <Button
              variant="outline"
              onClick={() => {
                onOpenChange(false);
                if (onEdit) onEdit(selectedBooking);
              }}
            >
              Düzenle
            </Button>
          </div>
        </div>
      )}
    </DialogContent>
  </Dialog>
);

// Room Move Reason Dialog
export const MoveReasonDialog = ({
  open, onOpenChange, moveData, moveReason, setMoveReason, onConfirmMove,
}) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Room Move - Reason Required</DialogTitle>
      </DialogHeader>
      {moveData && (
        <div className="space-y-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="text-sm text-blue-900">
              <div className="font-semibold mb-2">Moving Booking:</div>
              <div>Guest: <strong>{moveData.booking.guest_name}</strong></div>
              <div>From: <strong>Room {moveData.oldRoom}</strong> -&gt; <strong>Room {moveData.newRoom}</strong></div>
              <div>Dates: <strong>{moveData.newCheckIn}</strong> to <strong>{moveData.newCheckOut}</strong></div>
            </div>
          </div>
          <div>
            <Label>Reason for Move *</Label>
            <select
              className="w-full border rounded-md p-2 mb-2"
              value={moveReason}
              onChange={(e) => setMoveReason(e.target.value)}
            >
              <option value="">Select reason...</option>
              <option value="Guest Request">Guest Request</option>
              <option value="Room Maintenance">Room Maintenance</option>
              <option value="Upgrade">Room Upgrade</option>
              <option value="Downgrade">Room Downgrade</option>
              <option value="Overbooking">Overbooking Resolution</option>
              <option value="VIP Guest">VIP Guest Priority</option>
              <option value="Room Issue">Room Issue / Complaint</option>
              <option value="Operational">Operational Reasons</option>
              <option value="Other">Other</option>
            </select>
            {moveReason === 'Other' && (
              <Input placeholder="Please specify..." onChange={(e) => setMoveReason(e.target.value)} />
            )}
          </div>
          <div className="text-xs text-gray-600 bg-gray-50 p-3 rounded">
            <strong>Note:</strong> This move will be recorded in the room move history.
          </div>
          <div className="flex space-x-2">
            <Button onClick={onConfirmMove} className="flex-1">Confirm Move</Button>
            <Button variant="outline" onClick={() => {
              onOpenChange(false);
              setMoveReason('');
            }}>Cancel</Button>
          </div>
        </div>
      )}
    </DialogContent>
  </Dialog>
);

// Find Room Dialog
export const FindRoomDialog = ({
  open, onOpenChange, findRoomCriteria, setFindRoomCriteria,
  availableRooms, rooms, onFindRoom, onSelectRoom,
}) => {
  const roomTypes = rooms ? [...new Set(rooms.map(r => r.room_type).filter(Boolean))] : [];

  return (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-3xl">
      <DialogHeader>
        <DialogTitle>Müsaitlik Kontrolu</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-4">
          <div>
            <Label>Check-in</Label>
            <Input
              type="date"
              value={findRoomCriteria.check_in}
              min={new Date().toISOString().split('T')[0]}
              onChange={(e) => {
                const newCi = e.target.value;
                const updates = { ...findRoomCriteria, check_in: newCi };
                if (newCi && (!findRoomCriteria.check_out || findRoomCriteria.check_out <= newCi)) {
                  const nextDay = new Date(newCi + 'T00:00:00');
                  nextDay.setDate(nextDay.getDate() + 1);
                  updates.check_out = nextDay.toISOString().split('T')[0];
                }
                setFindRoomCriteria(updates);
              }}
              data-testid="find-room-checkin"
            />
          </div>
          <div>
            <Label>Check-out</Label>
            <Input
              type="date"
              value={findRoomCriteria.check_out}
              min={findRoomCriteria.check_in || undefined}
              onChange={(e) => setFindRoomCriteria({...findRoomCriteria, check_out: e.target.value})}
              data-testid="find-room-checkout"
            />
          </div>
          <div>
            <Label>Oda Tipi</Label>
            <select
              className="w-full border rounded-md p-2"
              value={findRoomCriteria.room_type}
              onChange={(e) => setFindRoomCriteria({...findRoomCriteria, room_type: e.target.value})}
              data-testid="find-room-type"
            >
              <option value="all">Tum Tipler</option>
              {roomTypes.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <Label>Misafir Sayisi</Label>
            <Input
              type="number"
              min="1"
              value={findRoomCriteria.guests_count}
              onChange={(e) => setFindRoomCriteria({...findRoomCriteria, guests_count: Number(e.target.value)})}
            />
          </div>
        </div>
        <Button onClick={onFindRoom} className="w-full" data-testid="find-room-search-btn">
          <Search className="w-4 h-4 mr-2" />
          Müsait Odalari Ara
        </Button>
        {availableRooms.length > 0 && (
          <div className="border rounded-lg p-4 max-h-96 overflow-y-auto">
            <h3 className="font-semibold mb-3 flex items-center">
              <CheckCircle className="w-5 h-5 text-green-600 mr-2" />
              {availableRooms.length} Müsait Oda
            </h3>
            <div className="space-y-2">
              {availableRooms.map(room => (
                <div key={room.id} className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded">
                  <div>
                    <div className="font-semibold">Oda {room.room_number}</div>
                    <div className="text-sm text-gray-600 capitalize">
                      {room.room_type} - Kat {room.floor} - Kapasite: {room.capacity}
                    </div>
                    <div className="text-sm font-semibold text-green-600">{(room.base_price || 0).toLocaleString('tr-TR')} TL/gece</div>
                  </div>
                  <Button size="sm" onClick={() => onSelectRoom(room)}>Rezerve Et</Button>
                </div>
              ))}
            </div>
          </div>
        )}
        {findRoomCriteria.check_in && findRoomCriteria.check_out && availableRooms.length === 0 && (
          <div className="text-center py-8 text-red-600">
            <AlertCircle className="w-12 h-12 mx-auto mb-3" />
            <p className="font-semibold">Seçilen tarihler için müsait oda bulunamadı</p>
            <p className="text-sm">Farkli tarih veya oda tipi deneyin</p>
          </div>
        )}
      </div>
    </DialogContent>
  </Dialog>
  );
};
