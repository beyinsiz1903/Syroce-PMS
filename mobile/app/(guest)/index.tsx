import React, { useCallback, useMemo } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Card,
  EmptyState,
  H1,
  H2,
  ListGroup,
  ListRow,
  Muted,
  SectionTitle,
  SkeletonCard,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { GuestBooking, getGuestBookings } from '../../src/api/guestBookings';
import { formatDate, formatCurrency } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';
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

function BookingCard({ b, onPress }: { b: GuestBooking; onPress: () => void }) {
  const c = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${b.hotel?.property_name || 'Otel'} ${b.room?.room_number || ''}`}
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
    >
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <H2>{b.hotel?.property_name || b.hotel?.hotel_name || 'Otel'}</H2>
            <Muted>
              Oda {b.room?.room_number || 'TBA'} · {b.room?.room_type || ''}
            </Muted>
            <Body style={{ color: c.text, marginTop: 4 }}>
              {formatDate(b.check_in)} → {formatDate(b.check_out)}
            </Body>
            <Muted>
              {tr.guest.confirmation}: {b.confirmation_number || '—'}
            </Muted>
          </View>
          <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
            <Badge label={statusLabel(b.status)} tone={statusTone(b.status)} />
            {typeof b.total_amount === 'number' ? (
              <Body style={{ color: c.textMuted, fontSize: 13 }}>
                {formatCurrency(b.total_amount)}
              </Body>
            ) : null}
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

export default function GuestBookingsScreen() {
  const c = useTheme();
  const router = useRouter();
  const q = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });

  const refreshing = q.isFetching && !q.isLoading;
  const onRefresh = useCallback(() => {
    q.refetch();
  }, [q]);
  const offline = q.isError && isOffline(q.error);

  const active = q.data?.active_bookings || [];
  const past = q.data?.past_bookings || [];

  // En alakali rezervasyon: once konaklayan (checked_in), yoksa ilk aktif.
  // Ust kisimdaki ozet + hizli aksiyonlar bu rezervasyona gore kurulur.
  const focus = useMemo<GuestBooking | null>(() => {
    return active.find((b) => b.status === 'checked_in') || active[0] || null;
  }, [active]);

  const isCheckedIn = focus?.status === 'checked_in';
  const checkinOpen = !!focus?.can_checkin && !isCheckedIn;

  const noBookings = !q.isLoading && active.length === 0 && past.length === 0;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
      }
    >
      <OfflineBanner visible={offline} />
      <H1>{tr.guest.bookingsTitle}</H1>

      {q.isLoading ? (
        <SkeletonCard />
      ) : noBookings ? (
        <Card padded={false}>
          <EmptyState
            icon="bed-outline"
            title={tr.guest.noBookings}
            message={tr.guest.noBookingsMessage}
          />
        </Card>
      ) : (
        <>
          {focus ? (
            <>
              <Card accent={statusTone(focus.status) === 'success' ? c.success : c.primary}>
                <View
                  style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    gap: spacing.sm,
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Muted>{tr.guest.currentStay}</Muted>
                    <H2 style={{ marginTop: 2 }}>
                      {focus.hotel?.property_name || focus.hotel?.hotel_name || 'Otel'}
                    </H2>
                    <Body style={{ color: c.text, marginTop: spacing.xs }}>
                      {formatDate(focus.check_in)} → {formatDate(focus.check_out)}
                    </Body>
                    <Muted>
                      Oda {focus.room?.room_number || 'TBA'}
                      {focus.room?.room_type ? ` · ${focus.room.room_type}` : ''}
                    </Muted>
                  </View>
                  <Badge label={statusLabel(focus.status)} tone={statusTone(focus.status)} />
                </View>
              </Card>

              <ListGroup title={tr.guest.quickActions}>
                {checkinOpen ? (
                  <ListRow
                    icon="create-outline"
                    label={tr.guest.onlineCheckinTitle}
                    onPress={() =>
                      router.push({
                        pathname: ROUTES.guestOnlineCheckin,
                        params: { bookingId: focus.id },
                      })
                    }
                  />
                ) : null}
                {isCheckedIn ? (
                  <ListRow
                    icon="key-outline"
                    label={tr.guest.digitalKeyTitle}
                    onPress={() =>
                      router.push({ pathname: ROUTES.guestDigitalKey, params: { id: focus.id } })
                    }
                  />
                ) : null}
                {isCheckedIn ? (
                  <ListRow
                    icon="restaurant-outline"
                    label={tr.guest.roomServiceTitle}
                    onPress={() => router.push(ROUTES.guestRoomService)}
                  />
                ) : null}
                <ListRow
                  icon="time-outline"
                  label={tr.guest.earlyLateTitle}
                  onPress={() =>
                    router.push({ pathname: ROUTES.guestEarlyLate, params: { bookingId: focus.id } })
                  }
                />
                <ListRow
                  icon="chatbubbles-outline"
                  label={tr.guest.messagesTitle}
                  onPress={() => router.push(ROUTES.guestMessages)}
                />
                <ListRow
                  icon="receipt-outline"
                  label={tr.guest.viewBookingDetail}
                  onPress={() =>
                    router.push({ pathname: ROUTES.guestBookingDetail, params: { id: focus.id } })
                  }
                  last
                />
              </ListGroup>
            </>
          ) : null}

          {active.length > 0 ? (
            <>
              <SectionTitle title={tr.guest.activeBookings} />
              {active.map((b) => (
                <View key={b.id} style={{ marginBottom: spacing.sm }}>
                  <BookingCard
                    b={b}
                    onPress={() =>
                      router.push({ pathname: ROUTES.guestBookingDetail, params: { id: b.id } })
                    }
                  />
                </View>
              ))}
            </>
          ) : null}

          {past.length > 0 ? (
            <>
              <SectionTitle title={tr.guest.pastBookings} />
              {past.map((b) => (
                <View key={b.id} style={{ marginBottom: spacing.sm }}>
                  <BookingCard
                    b={b}
                    onPress={() =>
                      router.push({ pathname: ROUTES.guestBookingDetail, params: { id: b.id } })
                    }
                  />
                </View>
              ))}
            </>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}
