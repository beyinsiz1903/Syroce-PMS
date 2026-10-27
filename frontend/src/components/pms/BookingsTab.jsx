import React, { memo, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TabsContent } from '@/components/ui/tabs';
import { AlertTriangle, Home, Plus } from 'lucide-react';
import VirtualizedBookingList from '@/components/VirtualizedBookingList';
import LiteSetupBanner from '@/components/LiteSetupBanner';
import { useNavigate } from 'react-router-dom';
import { currencyBreakdownEntries, formatCurrencyBreakdown } from '@/lib/reportCurrency';
import { sortBookingsByStay } from '@/lib/bookingStaySort';

const CurrencySummary = ({ breakdown, className }) => {
  const entries = currencyBreakdownEntries(breakdown);
  return entries.length ? (
    <dl className={`mt-2 space-y-1 text-sm tabular-nums ${className}`}>
      {entries.map(({ currency, formatted }) => (
        <div key={currency} className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
          <dt className="text-xs font-medium text-slate-500">{currency}</dt>
          <dd className="min-w-0 break-words font-semibold">{formatted}</dd>
        </div>
      ))}
    </dl>
  ) : <div className={`mt-2 break-words text-sm font-semibold tabular-nums ${className}`}>{formatCurrencyBreakdown(breakdown)}</div>;
};

const BookingsTab = ({
  bookingStats,
  bookings,
  businessDate,
  setOpenDialog,
  setSelectedBookingDetail,
  loadBookingFolios,
  isLite,
  roomsCount,
  activeTab,
  setReservationDetailId,
  historyLoading = false,
  historyError = null,
  retryHistory,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [listFilter, setListFilter] = useState('all');
  const [stayOrder, setStayOrder] = useState('nearest');
  const tc = (k) => t(`pmsComponents.bookings.${k}`);
  const unassignedBookings = useMemo(() => bookings.filter(item => (
    !item.room_id && !['cancelled', 'checked_out', 'no_show'].includes(item.status)
  )), [bookings]);
  const visibleBookings = useMemo(() => sortBookingsByStay(
    listFilter === 'unassigned' ? unassignedBookings : bookings, businessDate, stayOrder,
  ), [listFilter, unassignedBookings, bookings, businessDate, stayOrder]);

  return (
    <TabsContent value="bookings" className="space-y-4">
      {historyLoading && <p role="status" className="text-sm text-slate-600">Tüm rezervasyonlar doğrulanıyor; görünen sayılar henüz nihai değil.</p>}
      {historyError && <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
        <p>{historyError}</p>
        <Button size="sm" variant="outline" onClick={retryHistory} disabled={historyLoading} className="mt-2">Tam listeyi yeniden yükle</Button>
      </div>}
      {isLite && roomsCount === 0 && activeTab === 'bookings' && (
        <LiteSetupBanner
          title={tc('addRoomsFirst')}
          desc={tc('addRoomsDesc')}
          actionLabel={tc('goToRooms')}
          onAction={() => navigate('/app/pms#rooms')}
        />
      )}
      <div className="flex flex-wrap justify-between items-center gap-3">
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

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5 [&>*]:min-w-0">
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
        <Card data-testid="booking-revenue-summary">
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('totalRevenue')}</div>
            <CurrencySummary breakdown={bookingStats?.revenueByCurrency} className="text-green-700" />
          </CardContent>
        </Card>
        <Card data-testid="booking-adr-summary">
          <CardContent className="p-4">
            <div className="text-xs text-gray-600">{tc('avgAdr')}</div>
            <CurrencySummary breakdown={bookingStats?.adrByCurrency} className="text-indigo-600" />
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-white p-3">
          <div>
            <div className="font-medium text-slate-900">Rezervasyon görünümü</div>
            <div className="text-xs text-slate-500">{businessDate
              ? `Konaklama tarihleri otelin ${businessDate} iş gününe yakınlığına göre sıralanır.`
              : 'İş günü yüklenene kadar konaklama tarihine göre sıralanır.'}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-600">
              Sıralama
              <select className="h-9 rounded-md border bg-white px-2 text-sm text-slate-900" value={stayOrder} onChange={event => setStayOrder(event.target.value)}>
                <option value="nearest">En yakın konaklama</option>
                <option value="farthest">En uzak konaklama</option>
              </select>
            </label>
            <div className="flex gap-2" role="group" aria-label="Rezervasyon listesi filtresi">
              <Button size="sm" variant={listFilter === 'all' ? 'default' : 'outline'} onClick={() => setListFilter('all')}>
                Tümü ({bookings.length})
              </Button>
              <Button size="sm" variant={listFilter === 'unassigned' ? 'default' : 'outline'} onClick={() => setListFilter('unassigned')} className={listFilter !== 'unassigned' && unassignedBookings.length ? 'border-amber-300 text-amber-800' : ''}>
                <AlertTriangle className="mr-1.5 h-4 w-4" /> Atanmamış ({unassignedBookings.length})
              </Button>
            </div>
          </div>
        </div>
        <VirtualizedBookingList
          key={`${listFilter}-${stayOrder}-${businessDate || ''}`}
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
