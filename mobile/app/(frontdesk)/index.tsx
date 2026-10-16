import React, { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Button, Card, H1, Muted, SectionTitle, SkeletonCard, webCenter } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { lightTheme, radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { Booking, getInHouse, getNoShowRisk, getTodayArrivals, getTodayDepartures } from '../../src/api/bookings';
import { getToday } from '../../src/api/hub';
import { useOnline } from '../../src/hooks/useOnline';
import { isOffline } from '../../src/utils/errors';
import { asArray } from '../../src/utils/queryData';
import { reservationStatusLabel } from '../../src/utils/reservationPresentation';
import { countLocalWalkIns, localDayISO, sortTodayBookings, todayBookingBalance, todayBookingTime, todayCountLabel, todayOccupancy } from '../../src/utils/todayPresentation';
import { ROUTES } from '../../src/navigation/routes';

type IoniconName = keyof typeof Ionicons.glyphMap;

function QuickAction({ icon, label, hint, tone, primary, onPress, testID }: {
  icon: IoniconName;
  label: string;
  hint?: string;
  tone: string;
  primary?: boolean;
  onPress: () => void;
  testID?: string;
}) {
  const c = useTheme();
  const color = primary ? c.primaryText : c.text;
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      style={({ pressed }) => ({ flexBasis: '45%', flexGrow: 1, opacity: pressed ? 0.86 : 1 })}
    >
      <Card style={{ flex: 1, minHeight: hint ? 116 : 92, backgroundColor: primary ? c.primary : c.surface, borderColor: primary ? c.primary : c.border }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Ionicons name={icon} size={26} color={primary ? c.primaryText : tone} />
          <Ionicons name="arrow-forward" size={18} color={primary ? c.primaryText : c.textMuted} />
        </View>
        <Body style={{ color, fontWeight: '700', marginTop: spacing.md }}>{label}</Body>
        {hint ? <Text style={{ color, fontSize: 12, marginTop: spacing.xs, opacity: 0.85 }}>{hint}</Text> : null}
      </Card>
    </Pressable>
  );
}

function BookingRow({ b, onPress, showCheckIn, last }: {
  b: Booking;
  onPress: () => void;
  showCheckIn: boolean;
  last: boolean;
}) {
  const c = useTheme();
  const time = todayBookingTime(showCheckIn ? b.check_in : b.check_out);
  const action = showCheckIn ? tr.today.startCheckin : tr.today.startCheckout;
  const room = b.room_number ? `${tr.today.room} ${b.room_number}` : tr.today.roomUnassigned;
  const initials = String(b.guest_name || '').trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('tr-TR') || '—';
  const balance = todayBookingBalance(b);
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={[b.guest_name || '—', room, b.vip_status ? tr.guests.vip : null, time, balance?.label, action].filter(Boolean).join('. ')}
      testID={showCheckIn ? 'today-arrival-row' : 'today-departure-row'}
      style={({ pressed }) => ({
        flexDirection: 'row', alignItems: 'center', gap: spacing.md,
        minHeight: 88, padding: spacing.lg, opacity: pressed ? 0.75 : 1,
        borderBottomWidth: last ? 0 : 1, borderBottomColor: c.border,
      })}
    >
      <View style={{ width: 40, height: 44, borderRadius: radius.md, backgroundColor: c.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ color: c.primary, fontSize: 13, fontWeight: '700' }}>{initials}</Text>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs }}>
          <Body style={{ flexShrink: 1, fontWeight: '700' }} numberOfLines={1}>{b.guest_name || '—'}</Body>
          {b.vip_status ? <Ionicons name="star" size={14} color={c.vip} accessibilityLabel={tr.guests.vip} /> : null}
        </View>
        <Muted numberOfLines={1}>{[room, b.room_type].filter(Boolean).join(' · ')}</Muted>
        {balance ? <Muted testID="today-booking-balance" style={{ color: c.warning, fontWeight: '600' }}>{balance.label}</Muted> : null}
      </View>
      <View style={{ alignItems: 'flex-end', gap: spacing.xs, maxWidth: 110 }}>
        {time ? <Body style={{ fontWeight: '700' }}>{time}</Body> : null}
        {b.status ? <Muted style={{ fontSize: 11 }} numberOfLines={1}>{reservationStatusLabel(b.status)}</Muted> : null}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
          <Text style={{ color: c.primary, fontSize: 11, fontWeight: '700' }}>{showCheckIn ? tr.today.actionCheckin : tr.today.actionCheckout}</Text>
          <Ionicons name="chevron-forward" size={14} color={c.primary} />
        </View>
      </View>
    </Pressable>
  );
}

function BookingSection({ title, hint, empty, data, rawData, loading, failed, showCheckIn, onPress }: {
  title: string;
  hint: string;
  empty: string;
  data: Booking[];
  rawData: unknown;
  loading: boolean;
  failed: boolean;
  showCheckIn: boolean;
  onPress: (booking: Booking) => void;
}) {
  const c = useTheme();
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? data : data.slice(0, 3);
  const unavailable = failed || !Array.isArray(rawData);
  return (
    <View>
      <SectionTitle title={title} right={<Muted>{todayCountLabel(rawData, loading || failed)}</Muted>} />
      <Muted style={{ marginBottom: spacing.md }}>{hint}</Muted>
      {loading ? <SkeletonCard /> : unavailable && !data.length ? (
        <Card accent={c.warning}><Muted>{tr.today.dataUnavailable}</Muted></Card>
      ) : !data.length ? (
        <Card>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
            <Ionicons name="checkmark-circle-outline" size={20} color={c.success} />
            <Muted style={{ flex: 1 }}>{empty}</Muted>
          </View>
        </Card>
      ) : (
        <Card padded={false}>
          {failed ? <Muted style={{ padding: spacing.lg, paddingBottom: 0, color: c.warning }}>{tr.today.cachedData}</Muted> : null}
          {visible.map((booking, index) => <BookingRow key={booking.id} b={booking} showCheckIn={showCheckIn} last={index === visible.length - 1 && data.length <= 3} onPress={() => onPress(booking)} />)}
          {data.length > 3 ? (
            <Pressable
              onPress={() => setExpanded((value) => !value)}
              accessibilityRole="button"
              accessibilityLabel={`${expanded ? tr.today.showLess : tr.today.viewAll} · ${title}`}
              accessibilityState={{ expanded }}
              style={({ pressed }) => ({ minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs, opacity: pressed ? 0.7 : 1 })}
            >
              <Body style={{ color: c.primary, fontSize: 13, fontWeight: '700' }}>{expanded ? tr.today.showLess : `${tr.today.viewAll} (${data.length})`}</Body>
              <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={c.primary} />
            </Pressable>
          ) : null}
        </Card>
      )}
    </View>
  );
}

export default function TodayScreen() {
  const c = useTheme();
  const router = useRouter();
  const online = useOnline();
  const [allRisks, setAllRisks] = useState(false);
  const arrivals = useQuery({ queryKey: ['arrivals-today'], queryFn: getTodayArrivals });
  const departures = useQuery({ queryKey: ['departures-today'], queryFn: getTodayDepartures });
  const inhouse = useQuery({ queryKey: ['inhouse'], queryFn: getInHouse });
  const noshows = useQuery({ queryKey: ['noshow-today'], queryFn: getNoShowRisk });
  // The header already uses this staff-safe digest. Reuse the same cache for
  // the person's urgent tasks and any executive occupancy fields supplied by RBAC.
  const digest = useQuery({ queryKey: ['hub-today'], queryFn: getToday, staleTime: 5 * 60 * 1000 });
  const queries = [arrivals, departures, inhouse, noshows, digest];
  const refreshing = queries.some((query) => query.isFetching && !query.isPending);
  const offline = !online || queries.some((query) => query.fetchStatus === 'paused' || (query.isError && isOffline(query.error)));
  const anyError = queries.some((query) => query.isError || query.fetchStatus === 'paused');
  const onRefresh = useCallback(() => {
    void arrivals.refetch();
    void departures.refetch();
    void inhouse.refetch();
    void noshows.refetch();
    void digest.refetch();
  }, [arrivals.refetch, departures.refetch, inhouse.refetch, noshows.refetch, digest.refetch]);

  const arrivalsData = sortTodayBookings<Booking>(arrivals.data, 'check_in');
  const departuresData = sortTodayBookings<Booking>(departures.data, 'check_out');
  const noshowsData = asArray<Awaited<ReturnType<typeof getNoShowRisk>>[number]>(noshows.data).filter((risk) => !!risk?.booking_id);
  const visibleRisks = allRisks ? noshowsData : noshowsData.slice(0, 2);
  const walkinCount = todayCountLabel(inhouse.data, inhouse.isPending || inhouse.isError) === '—'
    ? '—' : String(countLocalWalkIns(inhouse.data, localDayISO()));
  const riskCount = todayCountLabel(noshows.data, noshows.isPending || noshows.isError);
  const occupancy = todayOccupancy(digest.data, !online || digest.isPending || digest.isError || digest.isPlaceholderData || digest.fetchStatus === 'paused');
  const urgentTasks = !digest.isError && !digest.isPending && typeof digest.data?.urgent_tasks === 'number'
    ? digest.data.urgent_tasks : 0;
  const summary = [
    { label: tr.today.summaryArrivals, value: todayCountLabel(arrivals.data, arrivals.isPending || arrivals.isError), icon: 'log-in-outline' as const, color: c.primary },
    { label: tr.today.summaryDepartures, value: todayCountLabel(departures.data, departures.isPending || departures.isError), icon: 'log-out-outline' as const, color: c.info },
    { label: tr.today.summaryInhouse, value: todayCountLabel(inhouse.data, inhouse.isPending || inhouse.isError), icon: 'bed-outline' as const, color: c.success },
  ];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.lg }, webCenter]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />}
      >
        <OfflineBanner visible={offline} />
        <View style={{ gap: spacing.xs }}>
          <Muted>{new Date().toLocaleDateString('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' })}</Muted>
          <H1>{tr.today.title}</H1>
          <Muted>{tr.today.overview}</Muted>
        </View>

        {anyError ? (
          <Card accent={c.warning}>
            <Muted accessibilityLiveRegion="polite">{tr.today.loadError}</Muted>
            <Button title={tr.app.retry} icon="refresh" variant="outline" onPress={onRefresh} style={{ marginTop: spacing.sm }} />
          </Card>
        ) : null}

        {occupancy ? (
          <Card
            testID="today-occupancy"
            accessible
            accessibilityLabel={`${tr.today.occupancy}: %${occupancy.percentage.toLocaleString('tr-TR')}. ${occupancy.occupied} / ${occupancy.total} ${tr.today.roomCountUnit}`}
            style={{ backgroundColor: lightTheme.text, borderColor: lightTheme.text, gap: spacing.md }}
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.md }}>
              <View style={{ flex: 1 }}>
                <Muted style={{ color: c.primaryText, opacity: 0.8, fontWeight: '600' }}>{tr.today.occupancy}</Muted>
                <Text style={{ color: c.primaryText, fontSize: 34, fontWeight: '800', letterSpacing: -1, marginTop: spacing.xs }}>
                  %{occupancy.percentage.toLocaleString('tr-TR', { maximumFractionDigits: 1 })}
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
                <Ionicons name="bed-outline" size={24} color={c.primaryText} />
                <Body style={{ color: c.primaryText, fontWeight: '600' }}>{occupancy.occupied.toLocaleString('tr-TR')} / {occupancy.total.toLocaleString('tr-TR')} {tr.today.roomCountUnit}</Body>
              </View>
            </View>
            <View importantForAccessibility="no-hide-descendants" style={{ height: 6, borderRadius: radius.pill, overflow: 'hidden', backgroundColor: 'rgba(255,255,255,0.16)' }}>
              <View style={{ height: '100%', width: `${occupancy.percentage}%`, borderRadius: radius.pill, backgroundColor: c.primary }} />
            </View>
          </Card>
        ) : null}

        <View style={{ gap: spacing.md }}>
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            {summary.map((item, index) => (
              <Card key={item.label} style={{ flex: 1, padding: spacing.md, minHeight: 112 }} accessibilityLabel={`${item.label}: ${item.value}`} testID={`today-summary-${index}`}>
                <Ionicons name={item.icon} size={20} color={item.color} />
                <Text style={{ color: c.text, fontSize: 30, fontWeight: '800', letterSpacing: -1, marginTop: spacing.sm }} numberOfLines={1} adjustsFontSizeToFit>{item.value}</Text>
                <Muted style={{ fontSize: 11, fontWeight: '600' }}>{item.label}</Muted>
              </Card>
            ))}
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', gap: spacing.sm }}>
            <Muted>{tr.today.summaryNoShow} <Text style={{ color: noshowsData.length ? c.warning : c.text, fontWeight: '700' }}>{riskCount}</Text></Muted>
            <Muted>{tr.today.summaryWalkin} <Text style={{ color: c.text, fontWeight: '700' }}>{walkinCount}</Text></Muted>
          </View>
        </View>

        {noshowsData.length > 0 || urgentTasks > 0 ? (
          <View>
            <SectionTitle title={tr.today.priorities} />
            <Card accent={c.warning} style={{ gap: spacing.md }}>
              {urgentTasks > 0 ? (
                <Pressable onPress={() => router.push(ROUTES.frontdeskTasks)} accessibilityRole="button" accessibilityLabel={`${urgentTasks} ${tr.today.urgentTasks}. ${tr.today.reviewTasks}`} style={({ pressed }) => ({ minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: spacing.sm, opacity: pressed ? 0.75 : 1 })}>
                  <Ionicons name="flash-outline" size={22} color={c.warning} />
                  <Body style={{ flex: 1, fontWeight: '700' }}>{urgentTasks} {tr.today.urgentTasks}</Body>
                  <Ionicons name="chevron-forward" size={20} color={c.textMuted} />
                </Pressable>
              ) : null}
              {noshowsData.length > 0 ? (
                <>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
                    <Ionicons name="alert-circle-outline" size={20} color={c.warning} />
                    <Body style={{ flex: 1, fontWeight: '700' }}>{tr.today.noShowRisk}</Body>
                    <Muted>{riskCount}</Muted>
                  </View>
                  {noshows.isError ? <Muted style={{ color: c.warning }}>{tr.today.cachedData}</Muted> : null}
                  {visibleRisks.map((risk) => (
                    <Pressable key={risk.booking_id} accessibilityRole="button" accessibilityLabel={`${risk.guest_name || '—'}. ${tr.today.reviewBooking}`} onPress={() => router.push({ pathname: ROUTES.reservationDetail, params: { id: risk.booking_id } })} style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, minHeight: 48, opacity: pressed ? 0.75 : 1 })}>
                      <View style={{ flex: 1 }}>
                        <Body style={{ fontWeight: '600' }} numberOfLines={1}>{risk.guest_name || '—'}</Body>
                        <Muted>{risk.room_number ? `${tr.today.room} ${risk.room_number}` : tr.today.roomUnassigned}</Muted>
                      </View>
                      <Badge label={risk.level === 'high' ? tr.today.riskHigh : risk.level === 'medium' ? tr.today.riskMedium : tr.today.noShowRisk} tone={risk.level === 'high' ? 'danger' : 'warning'} />
                      <Ionicons name="chevron-forward" size={16} color={c.textMuted} />
                    </Pressable>
                  ))}
                  {noshowsData.length > 2 ? <Button title={allRisks ? tr.today.showLess : `${tr.today.viewAll} (${noshowsData.length})`} variant="ghost" onPress={() => setAllRisks((value) => !value)} /> : null}
                </>
              ) : null}
            </Card>
          </View>
        ) : null}

        <View>
          <SectionTitle title={tr.today.quickActions} />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md }}>
            <QuickAction icon="scan-outline" label={tr.today.quickCheckin} hint={tr.today.startCheckin} tone={c.primary} primary onPress={() => router.push(ROUTES.checkin)} testID="smoke-today-quick-checkin" />
            <QuickAction icon="log-out-outline" label={tr.today.quickCheckout} hint={tr.today.startCheckout} tone={c.info} onPress={() => router.push(ROUTES.checkout)} />
          </View>
        </View>

        <BookingSection title={tr.today.arrivals} hint={tr.today.arrivalsHint} empty={tr.today.noArrivals} data={arrivalsData} rawData={arrivals.data} loading={arrivals.isPending} failed={arrivals.isError} showCheckIn onPress={(booking) => router.push({ pathname: ROUTES.checkin, params: { bookingId: booking.id } })} />
        <BookingSection title={tr.today.departures} hint={tr.today.departuresHint} empty={tr.today.noDepartures} data={departuresData} rawData={departures.data} loading={departures.isPending} failed={departures.isError} showCheckIn={false} onPress={(booking) => router.push({ pathname: ROUTES.checkout, params: { bookingId: booking.id } })} />

        <View>
          <SectionTitle title={tr.today.otherActions} />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md }}>
            <QuickAction icon="add-circle-outline" label={tr.today.actionNewReservation} tone={c.primary} onPress={() => router.push(ROUTES.newReservation)} />
            <QuickAction icon="person-add-outline" label={tr.today.actionWalkin} tone={c.success} onPress={() => router.push(ROUTES.walkin)} />
            <QuickAction icon="calendar-outline" label={tr.calendar.openCta} tone={c.info} onPress={() => router.push(ROUTES.reservationCalendar)} testID="smoke-today-quick-calendar" />
            <QuickAction icon="construct-outline" label={tr.today.actionReportFault} tone={c.warning} onPress={() => router.push(ROUTES.frontdeskFault)} />
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
