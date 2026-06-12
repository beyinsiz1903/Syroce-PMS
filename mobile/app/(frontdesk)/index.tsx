import React, { useCallback } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  H1,
  Muted,
  SectionTitle,
  SkeletonCard,
} from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  Booking,
  getNoShowRisk,
  getTodayArrivals,
  getTodayDepartures,
} from '../../src/api/bookings';
import { formatCurrency, formatTime } from '../../src/utils/format';
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
  const hasBalance = !!b.balance && b.balance > 0;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${b.guest_name || ''} ${b.room_number || ''}`}
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1, marginBottom: spacing.sm })}
    >
      <Card accent={showCheckIn ? c.info : c.primary}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', gap: spacing.sm, alignItems: 'center' }}>
              <Body style={{ fontWeight: '700', flexShrink: 1 }}>{b.guest_name || '—'}</Body>
              {b.vip_status ? <Badge label={tr.guests.vip} tone="vip" icon="star" /> : null}
            </View>
            <Muted>
              {tr.today.room} {b.room_number || '—'} · {b.room_type || ''}
            </Muted>
            <Muted style={{ marginTop: 2 }}>
              {showCheckIn ? formatTime(b.check_in) : formatTime(b.check_out)}
            </Muted>
          </View>
          <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
            {hasBalance ? (
              <Badge label={formatCurrency(b.balance)} tone="warning" />
            ) : null}
            {b.status ? (
              <Body style={{ color: c.textMuted, fontSize: 12 }}>{b.status}</Body>
            ) : null}
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

  const arrivalsData = arrivals.data || [];
  const departuresData = departures.data || [];
  const noshowsData = noshows.data || [];

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

        <KpiRow>
          <KpiCard
            label={tr.today.summaryArrivals}
            value={String(arrivalsData.length)}
            tone="info"
            icon="log-in-outline"
          />
          <KpiCard
            label={tr.today.summaryDepartures}
            value={String(departuresData.length)}
            tone="default"
            icon="log-out-outline"
          />
          <KpiCard
            label={tr.today.summaryNoShow}
            value={String(noshowsData.length)}
            tone={noshowsData.length > 0 ? 'danger' : 'success'}
            icon="alert-circle-outline"
          />
        </KpiRow>

        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <Button
              title={tr.today.quickCheckin}
              icon="enter-outline"
              onPress={() => router.push(ROUTES.checkin)}
              testID="smoke-today-quick-checkin"
              fullWidth
            />
          </View>
          <View style={{ flex: 1 }}>
            <Button
              title={tr.today.quickCheckout}
              icon="exit-outline"
              variant="secondary"
              onPress={() => router.push(ROUTES.checkout)}
              fullWidth
            />
          </View>
        </View>

        <SectionTitle title={tr.today.arrivals} />
        {arrivals.isLoading ? (
          <SkeletonCard />
        ) : arrivalsData.length === 0 ? (
          <EmptyState icon="bed-outline" title={tr.today.noArrivals} />
        ) : (
          arrivalsData.map((b) => (
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

        <SectionTitle title={tr.today.departures} />
        {departures.isLoading ? (
          <SkeletonCard />
        ) : departuresData.length === 0 ? (
          <EmptyState icon="walk-outline" title={tr.today.noDepartures} />
        ) : (
          departuresData.map((b) => (
            <BookingRow
              key={b.id}
              b={b}
              onPress={() =>
                router.push({ pathname: ROUTES.checkout, params: { bookingId: b.id } })
              }
            />
          ))
        )}

        {noshowsData.length > 0 ? (
          <>
            <SectionTitle title={tr.today.noShowRisk} />
            {noshowsData.map((r) => (
              <Pressable
                key={r.booking_id}
                accessibilityRole="button"
                onPress={() =>
                  router.push({ pathname: ROUTES.checkin, params: { bookingId: r.booking_id } })
                }
                style={({ pressed }) => ({
                  opacity: pressed ? 0.85 : 1,
                  marginBottom: spacing.sm,
                })}
              >
                <Card accent={r.level === 'high' ? c.danger : c.warning}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <View style={{ flex: 1 }}>
                      <Body style={{ fontWeight: '700' }}>{r.guest_name || '—'}</Body>
                      <Muted>
                        {tr.today.room} {r.room_number || '—'}
                      </Muted>
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
        <Button title={tr.today.walkin} icon="person-add-outline" onPress={() => router.push(ROUTES.walkin)} />
      </View>
    </View>
  );
}
