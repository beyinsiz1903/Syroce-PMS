import React, { useCallback } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
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
  webCenter,
} from '../../src/components/ui';
import { KpiCard } from '../../src/components/KpiCard';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  Booking,
  getInHouse,
  getNoShowRisk,
  getTodayArrivals,
  getTodayDepartures,
} from '../../src/api/bookings';
import { formatCurrency, formatTime } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';
import { ROUTES } from '../../src/navigation/routes';

type IoniconName = keyof typeof Ionicons.glyphMap;

const todayISO = () => new Date().toISOString().slice(0, 10);

// A large, thumb-friendly quick-action tile: tinted icon disc over a bold
// label inside a premium card. Pressed state mirrors the kit Button (scale +
// fade) so the dashboard feels of-a-piece.
function QuickAction({
  icon,
  label,
  tone,
  onPress,
  testID,
}: {
  icon: IoniconName;
  label: string;
  tone: string;
  onPress: () => void;
  testID?: string;
}) {
  const c = useTheme();
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => ({
        width: '48%',
        opacity: pressed ? 0.9 : 1,
        transform: [{ scale: pressed ? 0.98 : 1 }],
      })}
    >
      <Card style={{ minHeight: 100, justifyContent: 'space-between' }}>
        <View
          style={{
            width: 44,
            height: 44,
            borderRadius: radius.pill,
            backgroundColor: tone + '1f',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Ionicons name={icon} size={22} color={tone} />
        </View>
        <Text
          style={{ color: c.text, fontSize: 15, fontWeight: '700', marginTop: spacing.md }}
          numberOfLines={1}
        >
          {label}
        </Text>
      </Card>
    </Pressable>
  );
}

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
  const inhouse = useQuery({ queryKey: ['inhouse'], queryFn: getInHouse });
  const noshows = useQuery({ queryKey: ['noshow-today'], queryFn: getNoShowRisk });

  const refreshing = arrivals.isFetching && !arrivals.isLoading;
  const onRefresh = useCallback(() => {
    arrivals.refetch();
    departures.refetch();
    inhouse.refetch();
    noshows.refetch();
  }, [arrivals, departures, inhouse, noshows]);

  const offline = arrivals.isError && isOffline(arrivals.error);
  // Surface non-offline load failures so the operator never reads empty
  // sections / zeroed KPIs as "nothing today" when the data simply failed.
  const anyError =
    !offline &&
    (arrivals.isError || departures.isError || inhouse.isError || noshows.isError);

  const arrivalsData = arrivals.data || [];
  const departuresData = departures.data || [];
  const inhouseData = inhouse.data || [];
  const noshowsData = noshows.data || [];

  // Walk-in summary = today's walk-ins, derived from real in-house data
  // (walk-ins auto-check-in and are tagged source==='walk_in' server-side).
  const today = todayISO();
  const walkinCount = inhouseData.filter(
    (b) => (b.source || '').toLowerCase() === 'walk_in' && (b.check_in || '').slice(0, 10) === today,
  ).length;

  const summary: {
    label: string;
    value: number;
    tone: 'info' | 'default' | 'success' | 'danger' | 'warning';
    icon: IoniconName;
  }[] = [
    { label: tr.today.summaryArrivals, value: arrivalsData.length, tone: 'info', icon: 'log-in-outline' },
    { label: tr.today.summaryDepartures, value: departuresData.length, tone: 'default', icon: 'log-out-outline' },
    { label: tr.today.summaryInhouse, value: inhouseData.length, tone: 'success', icon: 'bed-outline' },
    {
      label: tr.today.summaryNoShow,
      value: noshowsData.length,
      tone: noshowsData.length > 0 ? 'danger' : 'success',
      icon: 'alert-circle-outline',
    },
    { label: tr.today.summaryWalkin, value: walkinCount, tone: 'warning', icon: 'person-add-outline' },
  ];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.md }, webCenter]}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />

        <H1>{tr.today.title}</H1>

        {anyError ? (
          <Card accent={c.danger}>
            <Muted>{tr.today.loadError}</Muted>
            <View style={{ height: spacing.sm }} />
            <Button
              title={tr.app.retry}
              icon="refresh"
              variant="outline"
              onPress={onRefresh}
              fullWidth
            />
          </Card>
        ) : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md }}>
          {summary.map((s) => (
            <View key={s.label} style={{ width: '48%' }}>
              <KpiCard label={s.label} value={String(s.value)} tone={s.tone} icon={s.icon} />
            </View>
          ))}
        </View>

        <SectionTitle title={tr.today.quickActions} />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md }}>
          <QuickAction
            icon="enter-outline"
            label={tr.today.actionCheckin}
            tone={c.success}
            onPress={() => router.push(ROUTES.checkin)}
            testID="smoke-today-quick-checkin"
          />
          <QuickAction
            icon="exit-outline"
            label={tr.today.actionCheckout}
            tone={c.info}
            onPress={() => router.push(ROUTES.checkout)}
          />
          <QuickAction
            icon="calendar-number-outline"
            label={tr.calendar.openCta}
            tone={c.vip}
            onPress={() => router.push(ROUTES.reservationCalendar)}
            testID="smoke-today-quick-calendar"
          />
          <QuickAction
            icon="calendar-outline"
            label={tr.today.actionNewReservation}
            tone={c.primary}
            onPress={() => router.push(ROUTES.reservations)}
          />
          <QuickAction
            icon="person-add-outline"
            label={tr.today.actionWalkin}
            tone={c.warning}
            onPress={() => router.push(ROUTES.walkin)}
          />
          <QuickAction
            icon="search-outline"
            label={tr.today.actionGuestSearch}
            tone={c.vip}
            onPress={() => router.push(ROUTES.frontdeskGuests)}
          />
        </View>

        <SectionTitle title={tr.today.arrivals} />
        {arrivals.isLoading ? (
          <SkeletonCard />
        ) : arrivals.isError && !offline ? (
          <Card accent={c.danger}>
            <Muted>{tr.today.loadError}</Muted>
          </Card>
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
        ) : departures.isError && !offline ? (
          <Card accent={c.danger}>
            <Muted>{tr.today.loadError}</Muted>
          </Card>
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
    </View>
  );
}
