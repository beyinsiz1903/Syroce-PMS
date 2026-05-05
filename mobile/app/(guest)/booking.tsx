import React, { useMemo } from 'react';
import { ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Button, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getGuestBookings } from '../../src/api/guestBookings';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';
import { ROUTES } from '../../src/navigation/routes';

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
      <View style={{ flex: 1, padding: spacing.lg, backgroundColor: c.bg, gap: spacing.md }}>
        <Muted>{tr.guest.noBookings}</Muted>
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
      <H1>{booking.hotel?.property_name || 'Otel'}</H1>
      <Muted>{booking.hotel?.address || ''}</Muted>

      <Card>
        <H2>Konaklama</H2>
        <Body>
          {formatDate(booking.check_in)} {formatTime(booking.check_in)} →{' '}
          {formatDate(booking.check_out)} {formatTime(booking.check_out)}
        </Body>
        <Muted>
          Oda {booking.room?.room_number || 'TBA'} · {booking.room?.room_type || ''}
        </Muted>
        <Muted>
          {booking.guests_count || 1} {tr.guest.guests}
        </Muted>
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
          <Badge label={booking.status || '—'} tone="info" />
          {booking.confirmation_number ? (
            <Badge label={`#${booking.confirmation_number}`} tone="default" />
          ) : null}
        </View>
      </Card>

      <Card>
        <H2>{tr.checkout.folio} özeti</H2>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Muted>Toplam</Muted>
          <Body>{formatCurrency(booking.total_amount || 0)}</Body>
        </View>
      </Card>

      <View style={{ gap: spacing.sm }}>
        {checkInOpen && !isCheckedIn ? (
          <Button
            title={tr.guest.onlineCheckinTitle}
            onPress={() =>
              router.push({ pathname: ROUTES.guestOnlineCheckin, params: { bookingId: booking.id } })
            }
            fullWidth
          />
        ) : null}
        {isCheckedIn ? (
          <Button
            title={tr.guest.digitalKeyOpen}
            onPress={() =>
              router.push({ pathname: ROUTES.guestDigitalKey, params: { id: booking.id } })
            }
            fullWidth
          />
        ) : null}
        <Button
          title={tr.guest.earlyLateTitle}
          variant="secondary"
          onPress={() =>
            router.push({ pathname: ROUTES.guestEarlyLate, params: { bookingId: booking.id } })
          }
          fullWidth
        />
        {isCheckedIn ? (
          <Button
            title={tr.guest.roomServiceTitle}
            variant="secondary"
            onPress={() => router.push(ROUTES.guestRoomService)}
            fullWidth
          />
        ) : null}
        <Button
          title={tr.guest.messagesTitle}
          variant="ghost"
          onPress={() => router.push(ROUTES.guestMessages)}
          fullWidth
        />
      </View>
    </ScrollView>
  );
}
