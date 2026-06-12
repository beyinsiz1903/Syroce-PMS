import React, { useMemo } from 'react';
import { ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Button,
  Card,
  DetailHeader,
  DetailRow,
  EmptyState,
  ListGroup,
  ListRow,
  SectionTitle,
  SkeletonCard,
} from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getGuestBookings } from '../../src/api/guestBookings';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';
import { ROUTES } from '../../src/navigation/routes';

function statusTone(status?: string): 'success' | 'warning' | 'info' | 'default' {
  switch ((status || '').toLowerCase()) {
    case 'checked_in':
      return 'success';
    case 'confirmed':
    case 'guaranteed':
      return 'info';
    case 'checked_out':
      return 'default';
    default:
      return 'warning';
  }
}

function statusLabel(status?: string): string {
  switch ((status || '').toLowerCase()) {
    case 'checked_in':
      return 'Konaklıyor';
    case 'confirmed':
      return 'Onaylı';
    case 'guaranteed':
      return 'Garantili';
    case 'checked_out':
      return 'Tamamlandı';
    case 'cancelled':
      return 'İptal';
    default:
      return status || '—';
  }
}

export default function GuestBookingDetail() {
  const c = useTheme();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });

  const booking = useMemo(() => {
    const all = [...(q.data?.active_bookings || []), ...(q.data?.past_bookings || [])];
    return all.find((b) => b.id === id) || null;
  }, [q.data, id]);

  if (q.isLoading) {
    return (
      <ScrollView contentContainerStyle={{ padding: spacing.lg, backgroundColor: c.bg }}>
        <SkeletonCard />
      </ScrollView>
    );
  }
  if (!booking) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <EmptyState
          icon="bed-outline"
          title={tr.guest.noBookings}
          message={tr.guest.noBookingsMessage}
        />
      </View>
    );
  }

  const checkInOpen = !!booking.can_checkin;
  const isCheckedIn = booking.status === 'checked_in';

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
    >
      <DetailHeader
        title={booking.hotel?.property_name || 'Otel'}
        subtitle={booking.hotel?.address || undefined}
        badges={
          <>
            <Badge label={statusLabel(booking.status)} tone={statusTone(booking.status)} />
            {booking.confirmation_number ? (
              <Badge label={`#${booking.confirmation_number}`} tone="default" />
            ) : null}
          </>
        }
      />

      <Card>
        <DetailRow
          label={tr.guest.stayLabel}
          value={`${formatDate(booking.check_in)} ${formatTime(booking.check_in)} → ${formatDate(
            booking.check_out,
          )} ${formatTime(booking.check_out)}`}
        />
        <DetailRow
          label="Oda"
          value={`${booking.room?.room_number || 'TBA'}${
            booking.room?.room_type ? ` · ${booking.room.room_type}` : ''
          }`}
        />
        <DetailRow label={tr.guest.guests} value={`${booking.guests_count || 1}`} />
      </Card>

      <Card>
        <DetailRow
          label={tr.guest.folioSummary}
          value={formatCurrency(booking.total_amount || 0)}
        />
      </Card>

      {checkInOpen && !isCheckedIn ? (
        <Button
          title={tr.guest.onlineCheckinTitle}
          icon="create-outline"
          onPress={() =>
            router.push({ pathname: ROUTES.guestOnlineCheckin, params: { bookingId: booking.id } })
          }
          fullWidth
        />
      ) : null}
      {isCheckedIn ? (
        <Button
          title={tr.guest.digitalKeyOpen}
          icon="key-outline"
          onPress={() =>
            router.push({ pathname: ROUTES.guestDigitalKey, params: { id: booking.id } })
          }
          fullWidth
        />
      ) : null}

      <SectionTitle title={tr.guest.quickActions} />
      <ListGroup>
        <ListRow
          icon="time-outline"
          label={tr.guest.earlyLateTitle}
          onPress={() =>
            router.push({ pathname: ROUTES.guestEarlyLate, params: { bookingId: booking.id } })
          }
        />
        {isCheckedIn ? (
          <ListRow
            icon="restaurant-outline"
            label={tr.guest.roomServiceTitle}
            onPress={() => router.push(ROUTES.guestRoomService)}
          />
        ) : null}
        <ListRow
          icon="chatbubbles-outline"
          label={tr.guest.messagesTitle}
          onPress={() => router.push(ROUTES.guestMessages)}
          last
        />
      </ListGroup>
    </ScrollView>
  );
}
