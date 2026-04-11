/**
 * Virtualized Booking List
 * Efficiently renders large lists using react-window
 */
import React, { memo } from 'react';
import { FixedSizeList as List } from 'react-window';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Calendar, User, DollarSign, Eye } from 'lucide-react';

const BookingRow = memo(({ index, style, data }) => {
  const { bookings, onSelectBooking } = data;
  const booking = bookings[index];

  if (!booking) return null;

  const getStatusColor = (status) => {
    switch (status) {
      case 'confirmed': return 'bg-blue-100 text-blue-800';
      case 'checked_in': return 'bg-green-100 text-green-800';
      case 'checked_out': return 'bg-gray-100 text-gray-800';
      case 'cancelled': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div style={style} className="px-2">
      <Card className="p-3 mb-2 hover:shadow-md transition-shadow">
        <div className="flex items-center justify-between">
          <div className="flex-1 grid grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-500">Guest</div>
              <div className="font-medium flex items-center gap-1">
                <User className="w-3 h-3" />
                {booking.guest_name || booking.guest_id}
              </div>
            </div>
            
            <div>
              <div className="text-xs text-gray-500">Room</div>
              <div className="font-medium">
                {booking.room_number || `Room ${booking.room_id}`}
              </div>
            </div>
            
            <div>
              <div className="text-xs text-gray-500">Check-in / Check-out</div>
              <div className="text-sm flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {new Date(booking.check_in).toLocaleDateString()} - 
                {new Date(booking.check_out).toLocaleDateString()}
              </div>
            </div>
            
            <div>
              <div className="text-xs text-gray-500">Amount</div>
              <div className="font-medium flex items-center gap-1">
                <DollarSign className="w-3 h-3" />
                ${booking.total_amount?.toFixed(2) || '0.00'}
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <Badge className={getStatusColor(booking.status)}>
              {booking.status}
            </Badge>
            <Button 
              size="sm" 
              variant="outline"
              onClick={() => onSelectBooking(booking)}
            >
              <Eye className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
});

BookingRow.displayName = 'BookingRow';

const VirtualizedBookingList = ({ bookings, onSelectBooking, height = 600 }) => {
  if (!bookings || bookings.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        No bookings found
      </div>
    );
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <List
        height={height}
        itemCount={bookings.length}
        itemSize={90}
        width="100%"
        itemData={{
          bookings,
          onSelectBooking,
        }}
      >
        {BookingRow}
      </List>
      
      <div className="p-2 bg-gray-50 border-t text-sm text-gray-600 text-center">
        Showing {bookings.length} bookings (virtualized for performance)
      </div>
    </div>
  );
};

export default memo(VirtualizedBookingList);
