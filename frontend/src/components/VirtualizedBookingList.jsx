/**
 * Virtualized Booking List
 * Efficiently renders large lists using react-window
 */
import React, { memo } from 'react';
import { FixedSizeList as List } from 'react-window';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Calendar, User, Eye, Radio, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { roomLabel } from '@/utils/displayIdentifiers';
import { statusLabel } from '@/pages/reservation-detail/helpers';

export const formatBookingAmount = (amount, currency = 'TRY') => new Intl.NumberFormat('tr-TR', {
  style: 'currency',
  currency: String(currency || 'TRY').toUpperCase() === 'TL' ? 'TRY' : String(currency).toUpperCase(),
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
}).format(Number(amount) || 0);

export const bookingSourceLabel = (booking = {}) => {
  const source = booking.source && typeof booking.source === 'object' ? booking.source : {};
  const primitiveSource = typeof booking.source === 'string' ? booking.source : '';
  const raw = booking.channel || booking.booking_source || booking.source_system
    || booking.provider || source.provider || source.channel || source.name || primitiveSource;
  const normalized = String(raw || '').trim().toLocaleLowerCase('tr-TR');
  const labels = {
    direct: 'Doğrudan', walkin: 'Walk-in', 'walk-in': 'Walk-in', phone: 'Telefon',
    online: 'Online', etstur: 'Etstur', ets: 'Etstur', hotelrunner: 'HotelRunner',
    exely: 'Exely', expedia: 'Expedia', agoda: 'Agoda', booking: 'Booking.com',
    'booking.com': 'Booking.com', jolly: 'Jolly', tatilbudur: 'Tatilbudur',
  };
  return labels[normalized] || (String(raw || '').trim() || 'Belirtilmemiş');
};

export const assignmentReasonLabel = (booking = {}) => {
  if (booking.room_id) return '';
  if (!booking.room_type && !booking.room_type_id) return 'Oda tipi bilgisi bulunmuyor';
  const reasons = {
    no_available_room: 'İçe aktarıldığı anda uygun oda bulunamadı',
    concurrent_room_conflict: 'Eş zamanlı rezervasyon oda müsaitliğini aldı',
    pending_mapping: 'Kanal oda tipi PMS oda tipiyle eşleştirilmemiş',
    unmapped_room_type: 'Kanal oda tipi PMS oda tipiyle eşleştirilmemiş',
  };
  return reasons[booking.auto_assignment_reason]
    || reasons[booking.assignment_reason]
    || 'Oda ataması bekliyor';
};

const BookingRow = memo(({ index, style, data }) => {
  const { t } = useTranslation();
  const { bookings, onSelectBooking } = data;
  const booking = bookings[index];

  if (!booking) return null;
  const assignmentReason = assignmentReasonLabel(booking);

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
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1 grid grid-cols-2 xl:grid-cols-5 gap-x-4 gap-y-2">
            <div>
              <div className="text-xs text-gray-500">{t('cm.components_VirtualizedBookingList.misafir')}</div>
              <div className="font-medium flex items-center gap-1 min-w-0 truncate">
                <User className="w-3 h-3" />
                {booking.guest_name || (booking.guest_id ? `Walk-in Misafir #${booking.guest_id.replace(/-/g,'').slice(-4).toUpperCase()}` : 'Bilinmiyor')}
              </div>
            </div>
            
            <div>
              <div className="text-xs text-gray-500">{t('cm.components_VirtualizedBookingList.oda')}</div>
              <div className="font-medium">
                {roomLabel(booking)}
              </div>
            </div>
            
            <div>
              <div className="text-xs text-gray-500">{t('cm.components_VirtualizedBookingList.giris_cikis')}</div>
              <div className="text-sm flex items-center gap-1 whitespace-nowrap">
                <Calendar className="w-3 h-3" />
                {new Date(booking.check_in).toLocaleDateString('tr-TR')} - 
                {new Date(booking.check_out).toLocaleDateString('tr-TR')}
              </div>
            </div>
            
            <div>
              <div className="text-xs text-gray-500">{t('cm.components_VirtualizedBookingList.tutar')}</div>
              <div className="font-semibold tabular-nums">
                {formatBookingAmount(booking.total_amount, booking.currency || booking.currency_code || 'TRY')}
              </div>
            </div>

            <div>
              <div className="text-xs text-gray-500">Rezervasyon kaynağı</div>
              <div className="text-sm font-medium flex items-center gap-1 truncate" title={bookingSourceLabel(booking)}>
                <Radio className="w-3 h-3 shrink-0" />
                {bookingSourceLabel(booking)}
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <Badge className={getStatusColor(booking.status)}>
              {statusLabel(booking.status)}
            </Badge>
            <Button 
              size="sm" 
              variant="outline"
              onClick={() => onSelectBooking(booking)}
              aria-label={`${booking.guest_name || 'Rezervasyon'} detayını aç`}
            >
              <Eye className="w-4 h-4" />
            </Button>
          </div>
        </div>
        {assignmentReason && (
          <div className="mt-1.5 flex items-center gap-1 text-xs font-medium text-amber-700" data-testid={`assignment-reason-${booking.id}`}>
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            Atanmama nedeni: {assignmentReason}
          </div>
        )}
      </Card>
    </div>
  );
});

BookingRow.displayName = 'BookingRow';

const VirtualizedBookingList = ({ bookings, onSelectBooking, height = 600 }) => {
  const { t } = useTranslation();
  if (!bookings || bookings.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        {t('cm.components_VirtualizedBookingList.rezervasyon_bulunamadi')}
      </div>
    );
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <List
        height={height}
        itemCount={bookings.length}
        itemSize={116}
        width="100%"
        itemData={{
          bookings,
          onSelectBooking,
        }}
      >
        {BookingRow}
      </List>
      
      <div className="p-2 bg-gray-50 border-t text-sm text-gray-600 text-center">
        {bookings.length} rezervasyon listelendi · Tüm kayıtlar için liste içinde kaydırın
      </div>
    </div>
  );
};

export default memo(VirtualizedBookingList);
