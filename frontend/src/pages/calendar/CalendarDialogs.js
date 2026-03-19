import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Search, CheckCircle, AlertCircle, Clock } from "lucide-react";
import { getSegmentColor, getStatusColor, getStatusLabel } from "./calendarHelpers";

// New Booking Dialog
export const NewBookingDialog = ({
  open, onOpenChange, newBooking, setNewBooking,
  selectedRoom, guests, rooms, onSubmit,
}) => {
  const roomTypes = rooms ? [...new Set(rooms.map(r => r.room_type).filter(Boolean))] : [];

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
                <option value="">Oda tipi secin...</option>
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
                <option value="">Oda secin...</option>
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
        <div>
          <Label>Misafir *</Label>
          <div className="flex gap-2">
            <select
              className="flex-1 border rounded-md p-2"
              value={newBooking.guest_id}
              onChange={(e) => {
                if (e.target.value === 'NEW') {
                  setNewBooking({...newBooking, guest_id: '', guest_name: '', guest_email: '', guest_phone: ''});
                } else {
                  setNewBooking({...newBooking, guest_id: e.target.value});
                }
              }}
            >
              <option value="">Misafir secin...</option>
              <option value="NEW" className="font-bold text-blue-600">+ Yeni Misafir Ekle</option>
              {guests.map(guest => (
                <option key={guest.id} value={guest.id}>{guest.name}</option>
              ))}
            </select>
          </div>
          {newBooking.guest_id === '' && newBooking.guest_name !== undefined && (
            <div className="mt-3 p-3 border rounded-md bg-blue-50 space-y-2">
              <div className="text-sm font-semibold text-blue-900 mb-2">Yeni Misafir Bilgileri</div>
              <Input
                placeholder="Isim Soyisim *"
                value={newBooking.guest_name || ''}
                onChange={(e) => setNewBooking({...newBooking, guest_name: e.target.value})}
                required
              />
              <Input
                type="email"
                placeholder="E-posta"
                value={newBooking.guest_email || ''}
                onChange={(e) => setNewBooking({...newBooking, guest_email: e.target.value})}
              />
              <Input
                type="tel"
                placeholder="Telefon"
                value={newBooking.guest_phone || ''}
                onChange={(e) => setNewBooking({...newBooking, guest_phone: e.target.value})}
              />
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Check-in</Label>
            <Input
              type="date"
              value={newBooking.check_in}
              onChange={(e) => setNewBooking({...newBooking, check_in: e.target.value})}
              required
            />
          </div>
          <div>
            <Label>Check-out</Label>
            <Input
              type="date"
              value={newBooking.check_out}
              min={newBooking.check_in || undefined}
              onChange={(e) => setNewBooking({...newBooking, check_out: e.target.value})}
              required
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
          <Button type="submit" className="flex-1">Rezervasyon Olustur</Button>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Iptal</Button>
        </div>
      </form>
    </DialogContent>
  </Dialog>
  );
};

// Booking Details Dialog
export const BookingDetailsDialog = ({
  open, onOpenChange, selectedBooking, rooms,
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
          <div className="flex space-x-2 pt-4 border-t">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
            <Button variant="outline" onClick={() => onOpenChange(false)}>Edit Booking</Button>
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
        <DialogTitle>Musaitlik Kontrolu</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-4">
          <div>
            <Label>Check-in</Label>
            <Input
              type="date"
              value={findRoomCriteria.check_in}
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
          Musait Odalari Ara
        </Button>
        {availableRooms.length > 0 && (
          <div className="border rounded-lg p-4 max-h-96 overflow-y-auto">
            <h3 className="font-semibold mb-3 flex items-center">
              <CheckCircle className="w-5 h-5 text-green-600 mr-2" />
              {availableRooms.length} Musait Oda
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
            <p className="font-semibold">Secilen tarihler icin musait oda bulunamadi</p>
            <p className="text-sm">Farkli tarih veya oda tipi deneyin</p>
          </div>
        )}
      </div>
    </DialogContent>
  </Dialog>
  );
};
