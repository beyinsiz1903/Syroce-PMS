import React, { memo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TabsContent } from '@/components/ui/tabs';
import { Home, Plus } from 'lucide-react';
import VirtualizedBookingList from '@/components/VirtualizedBookingList';
import LiteSetupBanner from '@/components/LiteSetupBanner';
import { useNavigate } from 'react-router-dom';

/**
 * Bookings tab content extracted from PMSModule.
 */
const BookingsTab = ({
  bookingStats,
  bookings,
  setOpenDialog,
  setSelectedBookingDetail,
  loadBookingFolios,
  toast,
  isLite,
  roomsCount,
  activeTab,
}) => {
  const navigate = useNavigate();
  return (
    <TabsContent value="bookings" className="space-y-4">
      {isLite && roomsCount === 0 && activeTab === 'bookings' && (
        <LiteSetupBanner
          title="Rezervasyon için önce odaları ekleyin"
          desc="Önce odaları ekleyin, ardından rezervasyon oluşturabilirsiniz."
          actionLabel="Odalara Git"
          onAction={() => navigate('/app/pms#rooms')}
        />
      )}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold">Bookings ({bookingStats?.total ?? 0})</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setOpenDialog('findroom')}>
            <Home className="w-4 h-4 mr-2" />
            Find Available Rooms
          </Button>
          <Button onClick={() => setOpenDialog('booking')}>
            <Plus className="w-4 h-4 mr-2" />
            New Booking
          </Button>
        </div>
      </div>

      {/* Booking Stats */}
      <div className="grid grid-cols-5 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">Total Bookings</div>
            <div className="text-2xl font-bold">{bookingStats?.total ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">Confirmed</div>
            <div className="text-2xl font-bold text-blue-600">
              {bookingStats?.confirmed ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">Checked In</div>
            <div className="text-2xl font-bold text-green-600">
              {bookingStats?.checkedIn ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">Total Revenue</div>
            <div className="text-2xl font-bold text-green-600">
              ${(bookingStats?.totalRevenue ?? 0).toFixed(0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">Avg ADR</div>
            <div className="text-2xl font-bold text-purple-600">
              ${(bookingStats?.avgAdr ?? 0).toFixed(0)}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <VirtualizedBookingList
          bookings={bookings}
          onSelectBooking={(booking) => {
            setSelectedBookingDetail(booking);
            setOpenDialog('bookingDetail');
            toast.info('Opening booking details...');
          }}
          height={600}
        />
      </div>
    </TabsContent>
  );
};

export default memo(BookingsTab);
