import React, { useCallback } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Button,
  Card,
  H1,
  H2,
  Muted,
  SkeletonCard,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  Booking,
  getNoShowRisk,
  getTodayArrivals,
  getTodayDepartures,
} from '../../src/api/bookings';
import { formatTime } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';
import { ROUTES } from '../../src/navigation/routes';

function BookingRow({
  b,
  onPress,
  showCheckIn,
}: {
  b: Booking;
  onPress: () => void;
  showCheckIn?: boolean;
}) {
  const c = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1, marginBottom: spacing.sm })}
    >
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', gap: spacing.sm, alignItems: 'center' }}>
              <H2>{b.guest_name || '—'}</H2>
              {b.vip_status ? <Badge label="VIP" tone="vip" /> : null}
            </View>
            <Muted>
              Oda {b.room_number || '—'} · {b.room_type || ''}
            </Muted>
            <Muted>{showCheckIn ? formatTime(b.check_in) : formatTime(b.check_out)}</Muted>
          </View>
          <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
            {b.balance && b.balance > 0 ? (
              <Badge label={`${b.balance.toFixed(0)} ₺`} tone="warning" />
            ) : null}
            <Body style={{ color: c.textMuted, fontSize: 12 }}>{b.status}</Body>
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

export default function TodayScreen() {
  const c = useTheme();
  const router = useRouter();

  const arrivals = useQuery({ queryKey: ['arrivals-today'], queryFn: getTodayArrivals });
  const departures = useQuery({ queryKey: ['departures-today'], queryFn: getTodayDepartures });
  const noshows = useQuery({ queryKey: ['noshow-today'], queryFn: getNoShowRisk });

  const refreshing = arrivals.isFetching && !arrivals.isLoading;
  const onRefresh = useCallback(() => {
    arrivals.refetch();
    departures.refetch();
    noshows.refetch();
  }, [arrivals, departures, noshows]);

  const offline = arrivals.isError && isOffline(arrivals.error);

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />

        <H1>{tr.today.title}</H1>

        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <Button
              title={tr.today.quickCheckin}
              onPress={() => router.push(ROUTES.checkin)}
              testID="smoke-today-quick-checkin"
              fullWidth
            />
          </View>
          <View style={{ flex: 1 }}>
            <Button
              title={tr.today.quickCheckout}
              variant="secondary"
              onPress={() => router.push(ROUTES.checkout)}
              fullWidth
            />
          </View>
        </View>

        <H2>{tr.today.arrivals}</H2>
        {arrivals.isLoading ? (
          <SkeletonCard />
        ) : (arrivals.data || []).length === 0 ? (
          <Card>
            <Muted>{tr.today.nothingToday}</Muted>
          </Card>
        ) : (
          (arrivals.data || []).map((b) => (
            <BookingRow
              key={b.id}
              b={b}
              showCheckIn
              onPress={() =>
                router.push({ pathname: ROUTES.checkin, params: { bookingId: b.id } })
              }
            />
          ))
        )}

        <H2>{tr.today.departures}</H2>
        {departures.isLoading ? (
          <SkeletonCard />
        ) : (departures.data || []).length === 0 ? (
          <Card>
            <Muted>{tr.today.nothingToday}</Muted>
          </Card>
        ) : (
          (departures.data || []).map((b) => (
            <BookingRow
              key={b.id}
              b={b}
              onPress={() =>
                router.push({ pathname: ROUTES.checkout, params: { bookingId: b.id } })
              }
            />
          ))
        )}

        {(noshows.data || []).length > 0 ? (
          <>
            <H2>{tr.today.noShowRisk}</H2>
            {(noshows.data || []).map((r) => (
              <Pressable
                key={r.booking_id}
                onPress={() =>
                  router.push({ pathname: ROUTES.checkin, params: { bookingId: r.booking_id } })
                }
                style={({ pressed }) => ({
                  opacity: pressed ? 0.85 : 1,
                  marginBottom: spacing.sm,
                })}
              >
                <Card>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <View>
                      <H2>{r.guest_name || '—'}</H2>
                      <Muted>Oda {r.room_number || '—'}</Muted>
                    </View>
                    <Badge
                      label={`${tr.today.noShowRisk} · ${Math.round(r.score)}`}
                      tone={r.level === 'high' ? 'danger' : 'warning'}
                    />
                  </View>
                </Card>
              </Pressable>
            ))}
          </>
        ) : null}
      </ScrollView>

      <View style={{ position: 'absolute', right: spacing.lg, bottom: spacing.xl }}>
        <Button title={tr.today.walkin} onPress={() => router.push(ROUTES.walkin)} />
      </View>
    </View>
  );
}
