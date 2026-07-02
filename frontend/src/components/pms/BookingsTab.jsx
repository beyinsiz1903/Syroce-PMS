import React, { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TabsContent } from '@/components/ui/tabs';
import { Home, Plus } from 'lucide-react';
import VirtualizedBookingList from '@/components/VirtualizedBookingList';
import LiteSetupBanner from '@/components/LiteSetupBanner';
import { useNavigate } from 'react-router-dom';

const BookingsTab = ({
  bookingStats,
  bookings,
  setOpenDialog,
  setSelectedBookingDetail,
  loadBookingFolios,
  isLite,
  roomsCount,
  activeTab,
  setReservationDetailId,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const tc = (k) => t(`pmsComponents.bookings.${k}`);
  const cur = t('pmsComponents.common.currency');

  return (
    <TabsContent value="bookings" className="space-y-4">
      {isLite && roomsCount === 0 && activeTab === 'bookings' && (
        <LiteSetupBanner
          title={tc('addRoomsFirst')}
          desc={tc('addRoomsDesc')}
          actionLabel={tc('goToRooms')}
          onAction={() => navigate('/app/pms#rooms')}
        />
      )}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold">{tc('title')} ({bookingStats?.total ?? 0})</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setOpenDialog('findroom')}>
            <Home className="w-4 h-4 mr-2" />
            {tc('findRoom')}
          </Button>
          <Button onClick={() => setOpenDialog('booking')}>
            <Plus className="w-4 h-4 mr-2" />
            {tc('newBooking')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('totalBookings')}</div>
            <div className="text-2xl font-bold">{bookingStats?.total ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('confirmed')}</div>
            <div className="text-2xl font-bold text-blue-600">
              {bookingStats?.confirmed ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('checkedIn')}</div>
            <div className="text-2xl font-bold text-green-600">
              {bookingStats?.checkedIn ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('totalRevenue')}</div>
            <div className="text-2xl font-bold text-green-600">
              {cur}{(bookingStats?.totalRevenue ?? 0).toFixed(0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('avgAdr')}</div>
            <div className="text-2xl font-bold text-indigo-600">
              {cur}{(bookingStats?.avgAdr ?? 0).toFixed(0)}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <VirtualizedBookingList
          bookings={bookings}
          onSelectBooking={(booking) => {
            if (setReservationDetailId) {
              setReservationDetailId(booking.id);
            } else {
              setSelectedBookingDetail(booking);
              setOpenDialog('bookingDetail');
            }
          }}
          height={600}
        />
      </div>
    </TabsContent>
  );
};

export default memo(BookingsTab);
