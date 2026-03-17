import { X, User, Calendar, DollarSign, Clock, Building2, FileText, Home, Award, AlertCircle, Info, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const ReservationSidebar = ({ 
  booking, 
  folio, 
  room, 
  onClose, 
  getSegmentColor, 
  getStatusLabel,
  getRateTypeInfo,
  onViewFolio,
  onEditReservation,
  onSendConfirmation
}) => {
  if (!booking) return null;

  const nights = Math.ceil((new Date(booking.check_out) - new Date(booking.check_in)) / (1000 * 60 * 60 * 24));
  const adr = booking.total_amount / nights;

  return (
    <div 
      className="fixed right-0 top-16 bottom-0 w-[480px] bg-white shadow-xl z-50 overflow-hidden flex flex-col animate-slide-in-right rounded-l-2xl"
      style={{ 
        boxShadow: '0 0 60px rgba(0, 0, 0, 0.15), 0 0 20px rgba(59, 130, 246, 0.1)',
        borderLeft: '1px solid rgba(59, 130, 246, 0.2)'
      }}
    >
      {/* Header */}
      <div className="bg-gradient-to-br from-blue-500 via-blue-600 to-indigo-600 text-white p-6 shadow-lg">
        <div className="flex justify-between items-start mb-6">
          <div className="flex-1">
            <h2 className="text-2xl font-bold mb-2 tracking-tight">{booking.guest_name || 'Guest'}</h2>
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className={`${getSegmentColor(booking.market_segment)} backdrop-blur-sm bg-opacity-90 transition-all hover:scale-105`}>
                {booking.market_segment || 'Standard'}
              </Badge>
              <Badge className="bg-white/90 text-blue-700 backdrop-blur-sm transition-all hover:scale-105 font-medium">
                {getStatusLabel(booking.status)}
              </Badge>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-white hover:bg-white/20 rounded-full p-2 transition-all duration-200 hover:rotate-90 backdrop-blur-sm"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {/* Quick Stats - Modern Cards */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white/15 backdrop-blur-md rounded-xl p-3 transition-all duration-300 hover:bg-white/25 hover:scale-105 border border-white/20">
            <div className="text-xs font-medium opacity-90 mb-1">Nights</div>
            <div className="text-2xl font-bold">{nights}</div>
          </div>
          <div className="bg-white/15 backdrop-blur-md rounded-xl p-3 transition-all duration-300 hover:bg-white/25 hover:scale-105 border border-white/20">
            <div className="text-xs font-medium opacity-90 mb-1">ADR</div>
            <div className="text-2xl font-bold">${adr.toFixed(0)}</div>
          </div>
          <div className="bg-white/15 backdrop-blur-md rounded-xl p-3 transition-all duration-300 hover:bg-white/25 hover:scale-105 border border-white/20">
            <div className="text-xs font-medium opacity-90 mb-1">Total</div>
            <div className="text-2xl font-bold">${booking.total_amount}</div>
          </div>
        </div>
      </div>

      {/* Content - Scrollable */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-gradient-to-b from-gray-50 to-white">
        
        {/* Guest Information */}
        <Card className="border-none shadow-md hover:shadow-lg transition-shadow duration-300 rounded-xl">
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              <User className="w-5 h-5 text-blue-600 mr-3 transition-transform group-hover:scale-110" />
              <h3 className="font-bold text-lg">Guest Information</h3>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-600">Name:</span>
                <span className="font-semibold">{booking.guest_name}</span>
              </div>
              {booking.guest_email && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Email:</span>
                  <span className="font-semibold text-sm">{booking.guest_email}</span>
                </div>
              )}

              {booking.guest_phone && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Phone:</span>
                  <span className="font-semibold">{booking.guest_phone}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-600">Adults:</span>
                <span className="font-semibold">{booking.adults}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Children:</span>
                <span className="font-semibold">{booking.children || 0}</span>
              </div>
            </div>

          </CardContent>
        </Card>

        {/* Group summary for this booking (if part of a group) */}
        {booking.group_booking_id && booking._group_summary && (
          <>
            {(() => {
              const groupSummary = booking._group_summary;
              return (
                <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl bg-blue-50/60 border border-blue-200">
                  <CardContent className="pt-6">
                    <div className="flex items-center mb-4">
                      <Users className="w-5 h-5 text-blue-600 mr-2" />
                      <h3 className="font-bold text-lg">Group</h3>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600">Group ID:</span>
                        <span className="font-mono text-xs bg-white px-2 py-0.5 rounded border border-blue-100">
                          {booking.group_booking_id?.slice(0, 8)}…
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Rooms in Group:</span>
                        <span className="font-semibold">{groupSummary.totalRooms}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Group Revenue:</span>
                        <span className="font-semibold">${groupSummary.totalAmount}</span>
                      </div>
                    </div>

                    <div className="mt-4 space-y-2">
                      <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Other rooms in this group</div>
                      <div className="space-y-1 max-h-40 overflow-y-auto">
                        {groupSummary.bookings
                          .filter(b => b.id !== booking.id)
                          .map(b => (
                            <div
                              key={b.id}
                              className="flex justify-between items-center text-xs bg-white px-2 py-1 rounded border border-blue-100"
                            >
                              <div>
                                <div className="font-medium">
                                  Room {b.room_number || '?'}
                                </div>
                                <div className="text-[11px] text-gray-500">
                                  {b.adults} adults{b.children ? `, ${b.children} children` : ''}
                                </div>
                              </div>
                              <div className="text-right">
                                <div className="font-semibold">${b.total_amount}</div>
                                <div className="text-[10px] text-gray-500">{getStatusLabel(b.status)}</div>
                              </div>
                            </div>
                          ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })()}
          </>
        )}

        {/* Stay Information */}
        <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              <Calendar className="w-5 h-5 text-green-600 mr-2" />
              <h3 className="font-bold text-lg">Stay Information</h3>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-600">Room:</span>
                <span className="font-semibold">{room?.room_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Room Type:</span>
                <span className="font-semibold capitalize">{room?.room_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Check-in:</span>
                <span className="font-semibold">{booking.check_in}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Check-out:</span>
                <span className="font-semibold">{booking.check_out}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Nights:</span>
                <span className="font-semibold">{nights}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Status:</span>
                <Badge className={`${booking.status === 'checked_in' ? 'bg-green-500' : 'bg-blue-500'}`}>
                  {getStatusLabel(booking.status)}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Rate Information */}
        <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              <DollarSign className="w-5 h-5 text-purple-600 mr-2" />
              <h3 className="font-bold text-lg">Rate Information</h3>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-600">ADR:</span>
                <span className="text-2xl font-bold text-purple-600">${adr.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Total Amount:</span>
                <span className="font-semibold">${booking.total_amount}</span>
              </div>
              {booking.rate_type && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Rate Code:</span>
                  <span className={`font-semibold ${getRateTypeInfo(booking).color}`}>
                    {getRateTypeInfo(booking).label}
                  </span>
                </div>
              )}
              {booking.market_segment && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Segment:</span>
                  <Badge className={getSegmentColor(booking.market_segment)}>
                    {booking.market_segment}
                  </Badge>
                </div>
              )}
              {booking.contracted_rate && (
                <div className="bg-green-50 border border-green-200 rounded p-2 text-sm text-green-800">
                  ✓ Contracted Rate Applied
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Folio Balance */}
        {folio && (
          <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
            <CardContent className="pt-6">
              <div className="flex items-center mb-4">
                <FileText className="w-5 h-5 text-orange-600 mr-2" />
                <h3 className="font-bold text-lg">Folio Balance</h3>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">Folio Number:</span>
                  <span className="font-semibold">{folio.folio_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Charges:</span>
                  <span className="font-semibold">${folio.total_charges || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Payments:</span>
                  <span className="font-semibold text-green-600">${folio.total_payments || 0}</span>
                </div>
                <div className="flex justify-between items-center pt-2 border-t">
                  <span className="text-gray-700 font-semibold">Balance:</span>
                  <span className={`text-xl font-bold ${folio.balance > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    ${folio.balance || 0}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Status:</span>
                  <Badge className={folio.status === 'open' ? 'bg-yellow-500' : 'bg-gray-500'}>
                    {folio.status}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Company Information */}
        {booking.company_name && (
          <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
            <CardContent className="pt-6">
              <div className="flex items-center mb-4">
                <Building2 className="w-5 h-5 text-indigo-600 mr-2" />
                <h3 className="font-bold text-lg">Company</h3>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-600">Company:</span>
                  <span className="font-semibold">{booking.company_name}</span>
                </div>
                {booking.corporate_code && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Code:</span>
                    <span className="font-semibold">{booking.corporate_code}</span>
                  </div>
                )}
                {booking.payment_terms && (
                  <div className="flex justify-between">
                    <span className="text-gray-600">Payment Terms:</span>
                    <span className="font-semibold">{booking.payment_terms}</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Housekeeping Status */}
        <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              <Home className="w-5 h-5 text-teal-600 mr-2" />
              <h3 className="font-bold text-lg">Housekeeping</h3>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-600">Room Status:</span>
                <Badge className={
                  room?.status === 'available' ? 'bg-green-500' :
                  room?.status === 'occupied' ? 'bg-blue-500' :
                  room?.status === 'dirty' ? 'bg-red-500' :
                  'bg-gray-500'
                }>
                  {room?.status || 'Unknown'}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Last Cleaned:</span>
                <span className="font-semibold">Today, 10:30 AM</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Turndown Service:</span>
                <span className="font-semibold">✓ Completed</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Room Move History */}
        {booking.room_moves && booking.room_moves.length > 0 && (
          <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
            <CardContent className="pt-6">
              <div className="flex items-center mb-4">
                <Clock className="w-5 h-5 text-gray-600 mr-2" />
                <h3 className="font-bold text-lg">Room Move History</h3>
              </div>
              <div className="space-y-2">
                {booking.room_moves.map((move, idx) => (
                  <div key={idx} className="bg-gray-50 border border-gray-200 rounded p-3">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-sm">
                        {move.old_room} → {move.new_room}
                      </span>
                      <span className="text-xs text-gray-500">
                        {new Date(move.timestamp).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="text-xs text-gray-600">
                      <div>Reason: {move.reason}</div>
                      <div>By: {move.moved_by}</div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Loyalty Points */}
        <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              <Award className="w-5 h-5 text-yellow-600 mr-2" />
              <h3 className="font-bold text-lg">Loyalty Program</h3>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-600">Member Status:</span>
                <Badge className="bg-yellow-500">Gold Member</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Points Balance:</span>
                <span className="font-semibold">2,450 pts</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Points from Stay:</span>
                <span className="font-semibold text-green-600">+{Math.floor(booking.total_amount / 10)} pts</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Notes */}
        <Card className="border-none shadow-md hover:shadow-lg transition-all duration-300 rounded-xl backdrop-blur-sm">
          <CardContent className="pt-6">
            <div className="flex items-center mb-4">
              <Info className="w-5 h-5 text-blue-600 mr-3 transition-transform group-hover:scale-110" />
              <h3 className="font-bold text-lg">Special Notes</h3>
            </div>
            <div className="space-y-2">
              {booking.special_requests ? (
                <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm">
                  <AlertCircle className="w-4 h-4 inline mr-2 text-yellow-600" />
                  {booking.special_requests}
                </div>
              ) : (
                <div className="text-gray-500 text-sm italic">No special requests</div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Action Buttons */}
        <div className="space-y-2 pb-6">
          <Button 
            data-testid="view-folio-btn"
            className="w-full" 
            size="lg"
            onClick={() => {
              if (onViewFolio) {
                onViewFolio(booking.id);
              }
            }}
          >
            Folyo'yu Görüntüle
          </Button>
          <Button 
            variant="outline" 
            className="w-full"
            onClick={() => {
              if (onEditReservation) {
                onEditReservation(booking);
              } else {
                console.log('Edit reservation:', booking.id);
              }
            }}
          >
            Edit Reservation
          </Button>
          <Button 
            variant="outline" 
            className="w-full"
            onClick={() => {
              if (onSendConfirmation) {
                onSendConfirmation(booking);
              } else {
                console.log('Send confirmation for:', booking.id);
              }
            }}
          >
            Send Confirmation
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ReservationSidebar;
