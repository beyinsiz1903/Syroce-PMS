import React, { useState, useCallback, useRef, useEffect } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Plus, Trash2, User, Search, UserCheck, UserPlus } from 'lucide-react';

const BookingDialog = ({
  open,
  onClose,
  guests,
  rooms,
  companies,
  ratePlans,
  packages,
  newBooking,
  setNewBooking,
  multiRoomBooking,
  handleCreateBooking,
  handleCompanySelect,
  handleContractedRateSelect,
  handleChildrenChange,
  handleChildAgeChange,
  addRoomToMultiBooking,
  removeRoomFromMultiBooking,
  updateMultiRoomField,
  updateMultiRoomChildrenAges,
  updateMultiRoomChildAge,
  isLite,
  setOpenDialog,
}) => {
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
    setNewBooking(prev => ({ ...prev, guest_id: '' }));

    if (guestSearchTimerRef.current) clearTimeout(guestSearchTimerRef.current);

    if (query.trim().length < 2) {
      setGuestSearchResults([]);
      setShowGuestDropdown(false);
      return;
    }

    setGuestSearchLoading(true);
    guestSearchTimerRef.current = setTimeout(async () => {
      try {
        const res = await axios.get(`/pms/guests/search?q=${encodeURIComponent(query.trim())}&limit=10`);
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
    setNewBooking(prev => ({ ...prev, guest_id: guest.id }));
  }, [setNewBooking]);

  // Clear selected guest
  const handleClearGuest = useCallback(() => {
    setSelectedGuest(null);
    setGuestSearchQuery('');
    setGuestSearchResults([]);
    setShowGuestDropdown(false);
    setNewBooking(prev => ({ ...prev, guest_id: '' }));
  }, [setNewBooking]);

  return (
<Dialog open={open} onOpenChange={(o) => !o && onClose()}>
  <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
    <DialogHeader>
      <DialogTitle>Yeni Rezervasyon Olustur</DialogTitle>
      <DialogDescription>Rezervasyon bilgilerini asagiya girin</DialogDescription>
    </DialogHeader>
    <form onSubmit={handleCreateBooking} className="space-y-6">
      {/* Guest search */}
      <div className="grid grid-cols-2 gap-4 items-end">
        <div>
          <Label>Misafir *</Label>
          {selectedGuest ? (
            <div className="mt-1 flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-md p-2.5" data-testid="booking-dialog-selected-guest">
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
                data-testid="booking-dialog-clear-guest"
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
                  placeholder="Misafir ara (isim, e-posta, telefon)..."
                  className="pl-9"
                  data-testid="booking-dialog-guest-search"
                />
                {guestSearchLoading && (
                  <span className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                )}
              </div>

              {/* Search results dropdown */}
              {showGuestDropdown && guestSearchResults.length > 0 && (
                <div
                  className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto"
                  data-testid="booking-dialog-guest-dropdown"
                >
                  {guestSearchResults.map((g) => (
                    <button
                      key={g.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-blue-50 border-b border-gray-50 last:border-b-0 transition-colors"
                      onClick={() => handleSelectGuest(g)}
                      data-testid={`booking-dialog-guest-option-${g.id}`}
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

              {/* No results hint */}
              {guestSearchQuery.trim().length >= 2 && !guestSearchLoading && showGuestDropdown && guestSearchResults.length === 0 && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg px-3 py-2">
                  <div className="flex items-center gap-2 text-gray-500">
                    <UserPlus className="w-3.5 h-3.5" />
                    <span className="text-sm">Sonuc bulunamadi. Yeni misafir kaydedin.</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setOpenDialog('guest')}
            data-testid="booking-dialog-register-guest"
          >
            Yeni Misafir Kaydet
          </Button>
        </div>
      </div>

      {/* Multi-room rooms list */}
      <div className="mt-4 border rounded-lg p-4 space-y-4 bg-slate-50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-sm">Rooms in this Booking</h3>
            <p className="text-xs text-slate-500">You can add multiple rooms under one reservation (family, small group, etc.).</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={addRoomToMultiBooking}>
            <Plus className="w-4 h-4 mr-1" /> Add Room
          </Button>
        </div>

        <div className="space-y-3">
          {multiRoomBooking.map((room, index) => (
            <div key={index} className="border rounded-md bg-white p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div className="font-medium text-sm">Room #{index + 1}</div>
                {multiRoomBooking.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-red-500 hover:text-red-700 hover:bg-red-50"
                    onClick={() => removeRoomFromMultiBooking(index)}
                  >
                    Remove
                  </Button>
                )}
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Room *</Label>
                  <Select
                    value={room.room_id}
                    onValueChange={(v) => updateMultiRoomField(index, 'room_id', v)}
                  >
                    <SelectTrigger><SelectValue placeholder="Select room" /></SelectTrigger>
                    <SelectContent>
                      {rooms.filter(r => r.status === 'available').map(r => (
                        <SelectItem key={r.id} value={r.id}>
                          Room {r.room_number} - {r.room_type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Adults</Label>
                  <Input
                    type="number"
                    min="1"
                    value={room.adults}
                    onChange={(e) => updateMultiRoomField(index, 'adults', e.target.value)}
                  />
                </div>
                <div>
                  <Label className="text-xs">Children</Label>
                  <Input
                    type="number"
                    min="0"
                    value={room.children}
                    onChange={(e) => updateMultiRoomChildrenAges(index, e.target.value)}
                  />
                </div>
              </div>

              {room.children > 0 && (
                <div>
                  <Label className="text-xs">Children Ages</Label>
                  <div className="grid grid-cols-4 gap-2 mt-1">
                    {Array.from({ length: room.children }).map((_, ageIndex) => (
                      <Input
                        key={ageIndex}
                        type="number"
                        min="0"
                        max="17"
                        placeholder={`Child ${ageIndex + 1}`}
                        value={room.children_ages?.[ageIndex] ?? ''}
                        onChange={(e) => updateMultiRoomChildAge(index, ageIndex, e.target.value)}
                      />
                    ))}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3 pt-2 border-t mt-2">
                <div>
                  <Label className="text-xs">Rate Plan</Label>
                  <Select
                    value={room.rate_plan || ''}
                    onValueChange={(v) => {
                      // Set rate plan and suggest base rate from selected plan
                      const selected = ratePlans.find(rp => rp.code === v || rp.id === v);
                      updateMultiRoomField(index, 'rate_plan', v);
                      if (selected && selected.base_price) {
                        updateMultiRoomField(index, 'base_rate', selected.base_price);
                        if (!room.total_amount || room.total_amount === 0) {
                          updateMultiRoomField(index, 'total_amount', selected.base_price);
                        }
                      }
                    }}
                  >
                    <SelectTrigger><SelectValue placeholder="Select rate plan" /></SelectTrigger>
                    <SelectContent>
                      {ratePlans.map(rp => (
                        <SelectItem key={rp.id} value={rp.code || rp.id}>
                          {rp.name} ({rp.code}) - {rp.currency} {rp.base_price}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Package</Label>
                  <Select
                    value={room.package_code || ''}
                    onValueChange={(v) => updateMultiRoomField(index, 'package_code', v)}
                  >
                    <SelectTrigger><SelectValue placeholder="No package" /></SelectTrigger>
                    <SelectContent>
                      {packages.map(pkg => (
                        <SelectItem key={pkg.id} value={pkg.code}>
                          {pkg.name} ({pkg.code})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2">
                <div>
                  <Label className="text-xs">Base Rate</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={room.base_rate === 0 ? '' : room.base_rate}
                    onChange={(e) => updateMultiRoomField(index, 'base_rate', e.target.value)}
                  />
                </div>
                <div>
                  <Label className="text-xs">Total Amount *</Label>
                  <Input
                    type="number"
                    step="0.01"
                    value={room.total_amount === 0 ? '' : room.total_amount}
                    onChange={(e) => updateMultiRoomField(index, 'total_amount', e.target.value)}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Check-in and Check-out */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label>Check-in *</Label>
          <Input type="date" value={newBooking.check_in} onChange={(e) => setNewBooking({...newBooking, check_in: e.target.value})} required />
        </div>
        <div>
          <Label>Check-out *</Label>
          <Input type="date" value={newBooking.check_out} onChange={(e) => setNewBooking({...newBooking, check_out: e.target.value})} required />
        </div>
      </div>

      {/* Adults and Children for summary (kept for compatibility but hidden) */}
      <div className="hidden">
        <Input 
          type="number" 
          min="1" 
          value={newBooking.adults} 
          onChange={(e) => {
            const adults = parseInt(e.target.value) || 1;
            setNewBooking({...newBooking, adults, guests_count: adults + newBooking.children});
          }} 
        />
        <Input 
          type="number" 
          min="0" 
          value={newBooking.children} 
          onChange={(e) => handleChildrenChange(e.target.value)} 
        />
      </div>

      {/* Children Ages - Show only if children > 0 */}
      {newBooking.children > 0 && (
        <div>
          <Label>Children Ages</Label>
          <div className="grid grid-cols-4 gap-2 mt-2">
            {Array.from({ length: newBooking.children }).map((_, index) => (
              <Input
                key={index}
                type="number"
                min="0"
                max="17"
                placeholder={`Child ${index + 1} age`}
                value={newBooking.children_ages[index] || ''}
                onChange={(e) => handleChildAgeChange(index, e.target.value)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Company Selection */}
      <div>
        <div className="flex justify-between items-center mb-2">
          <Label>Company (Optional)</Label>
          <Button 
            type="button" 
            variant="outline" 
            size="sm" 
            onClick={() => setOpenDialog('company')}
          >
            <Plus className="w-4 h-4 mr-1" />
            New Company
          </Button>
        </div>
        <Select value={newBooking.company_id || "none"} onValueChange={handleCompanySelect}>
          <SelectTrigger><SelectValue placeholder="Select company (optional)" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">None</SelectItem>
            {companies.filter(c => c.status === 'active').map(c => (
              <SelectItem key={c.id} value={c.id}>{c.name} - {c.corporate_code}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Contracted Rate */}
      {newBooking.company_id && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Contracted Rate</Label>
            <Select value={newBooking.contracted_rate} onValueChange={handleContractedRateSelect}>
              <SelectTrigger><SelectValue placeholder="Select rate" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="corp_std">Standard Corporate</SelectItem>
                <SelectItem value="corp_pref">Preferred Corporate</SelectItem>
                <SelectItem value="gov">Government Rate</SelectItem>
                <SelectItem value="ta">Travel Agent Rate</SelectItem>
                <SelectItem value="crew">Airline Crew Rate</SelectItem>
                <SelectItem value="mice">Event/Conference Rate</SelectItem>
                <SelectItem value="lts">Long Stay/Project Rate</SelectItem>
                <SelectItem value="tou">Tour Operator Rate</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Rate Type</Label>
            <Select value={newBooking.rate_type} onValueChange={(v) => setNewBooking({...newBooking, rate_type: v})}>
              <SelectTrigger><SelectValue placeholder="Select type" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="bar">BAR / Rack Rate</SelectItem>
                <SelectItem value="corporate">Corporate Rate</SelectItem>
                <SelectItem value="government">Government Rate</SelectItem>
                <SelectItem value="wholesale">Wholesale Rate</SelectItem>
                <SelectItem value="package">Package Rate</SelectItem>
                <SelectItem value="promotional">Promotional Rate</SelectItem>
                <SelectItem value="non_refundable">Non-Refundable</SelectItem>
                <SelectItem value="long_stay">Long Stay Rate</SelectItem>
                <SelectItem value="day_use">Day Use Rate</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Market Segment and Cancellation Policy */}
      {newBooking.company_id && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Market Segment</Label>
            <Select value={newBooking.market_segment} onValueChange={(v) => setNewBooking({...newBooking, market_segment: v})}>
              <SelectTrigger><SelectValue placeholder="Select segment" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="corporate">Corporate</SelectItem>
                <SelectItem value="leisure">Leisure</SelectItem>
                <SelectItem value="group">Group</SelectItem>
                <SelectItem value="mice">MICE/Event</SelectItem>
                <SelectItem value="government">Government</SelectItem>
                <SelectItem value="crew">Airline Crew</SelectItem>
                <SelectItem value="wholesale">Wholesale</SelectItem>
                <SelectItem value="long_stay">Long Stay</SelectItem>
                <SelectItem value="complimentary">Complimentary</SelectItem>
                <SelectItem value="other">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Cancellation Policy</Label>
            <Select value={newBooking.cancellation_policy} onValueChange={(v) => setNewBooking({...newBooking, cancellation_policy: v})}>
              <SelectTrigger><SelectValue placeholder="Select policy" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="same_day">Same Day (18:00)</SelectItem>
                <SelectItem value="h24">24 Hours</SelectItem>
                <SelectItem value="h48">48 Hours</SelectItem>
                <SelectItem value="h72">72 Hours</SelectItem>
                <SelectItem value="d7">7 Days</SelectItem>
                <SelectItem value="d14">14 Days</SelectItem>
                <SelectItem value="non_refundable">Non-Refundable</SelectItem>
                <SelectItem value="flexible">Flexible</SelectItem>
                <SelectItem value="special_event">Special Event</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {/* Billing Information */}
      {newBooking.company_id && (
        <div className="space-y-4 border-t pt-4">
          <h3 className="font-semibold">Billing Information</h3>
          <div>
            <Label>Billing Address</Label>
            <Textarea 
              value={newBooking.billing_address} 
              onChange={(e) => setNewBooking({...newBooking, billing_address: e.target.value})}
              rows={2}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Tax Number</Label>
              <Input 
                value={newBooking.billing_tax_number} 
                onChange={(e) => setNewBooking({...newBooking, billing_tax_number: e.target.value})}


              />

      {/* Multi-room section placeholder: future enhancement */}

            </div>
            <div>
              <Label>Contact Person</Label>
              <Input 
                value={newBooking.billing_contact_person} 
                onChange={(e) => setNewBooking({...newBooking, billing_contact_person: e.target.value})}
              />
            </div>
          </div>
        </div>
      )}

      {/* Channel selection (rate details managed per-room above) */}
      <div className="grid grid-cols-3 gap-4 border-t pt-4">
        <div className="col-span-2 text-xs text-gray-500 flex items-center">
          Per-room base rate and total amount are managed in the multi-room section above.
        </div>
        <div>
          <Label>Channel</Label>
          <Select value={newBooking.channel} onValueChange={(v) => setNewBooking({...newBooking, channel: v})}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="direct">Direct</SelectItem>
              <SelectItem value="booking_com">Booking.com</SelectItem>
              <SelectItem value="expedia">Expedia</SelectItem>
              <SelectItem value="airbnb">Airbnb</SelectItem>
              <SelectItem value="agoda">Agoda</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Override Reason - Show if rate is different from base */}
      {false && newBooking.base_rate > 0 && newBooking.base_rate !== newBooking.total_amount && (
        <div className="bg-yellow-50 border border-yellow-200 p-4 rounded">
          <Label className="text-yellow-800">Override Reason * (Required for rate change)</Label>
          <Textarea 
            value={newBooking.override_reason} 
            onChange={(e) => setNewBooking({...newBooking, override_reason: e.target.value})}
            placeholder="Explain why the rate is different from the base rate..."
            className="mt-2"
            required
          />
        </div>
      )}

      <Button type="submit" className="w-full">Create Booking</Button>
    </form>
  </DialogContent>
</Dialog>

  );
};

export default BookingDialog;
