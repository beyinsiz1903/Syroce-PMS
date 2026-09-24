import React, { memo, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TabsContent } from '@/components/ui/tabs';
import { AlertTriangle, Home, Plus } from 'lucide-react';
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
  const [listFilter, setListFilter] = useState('all');
  const tc = (k) => t(`pmsComponents.bookings.${k}`);
  const listCurrency = bookings.find(item => item.currency || item.currency_code)?.currency
    || bookings.find(item => item.currency || item.currency_code)?.currency_code
    || 'TRY';
  const money = value => new Intl.NumberFormat('tr-TR', {
    style: 'currency', currency: listCurrency === 'TL' ? 'TRY' : listCurrency,
    maximumFractionDigits: 0,
  }).format(Number(value) || 0);
  const unassignedBookings = useMemo(() => bookings.filter(item => (
    !item.room_id && !['cancelled', 'checked_out', 'no_show'].includes(item.status)
  )), [bookings]);
  const visibleBookings = listFilter === 'unassigned' ? unassignedBookings : bookings;

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
              {money(bookingStats?.totalRevenue)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('avgAdr')}</div>
            <div className="text-2xl font-bold text-indigo-600">
              {money(bookingStats?.avgAdr)}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-white p-3">
          <div>
            <div className="font-medium text-slate-900">Rezervasyon görünümü</div>
            <div className="text-xs text-slate-500">Tüm tarihlerdeki oda atamalarını tek listeden kontrol edin.</div>
          </div>
          <div className="flex gap-2" role="group" aria-label="Rezervasyon listesi filtresi">
            <Button size="sm" variant={listFilter === 'all' ? 'default' : 'outline'} onClick={() => setListFilter('all')}>
              Tümü ({bookings.length})
            </Button>
            <Button size="sm" variant={listFilter === 'unassigned' ? 'default' : 'outline'} onClick={() => setListFilter('unassigned')} className={listFilter !== 'unassigned' && unassignedBookings.length ? 'border-amber-300 text-amber-800' : ''}>
              <AlertTriangle className="mr-1.5 h-4 w-4" /> Atanmamış ({unassignedBookings.length})
            </Button>
          </div>
        </div>
        <VirtualizedBookingList
          bookings={visibleBookings}
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
