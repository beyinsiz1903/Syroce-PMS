import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  View,
  useWindowDimensions,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { GestureDetector, Gesture, GestureHandlerRootView } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

import { ActionSheet, Badge, Body, Button, EmptyState, FadeInView, H1, H2, Muted } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { useOnline } from '../../src/hooks/useOnline';
import { DatePicker } from '../../src/components/DatePicker';
import { FilterChips, type FilterChipOption } from '../../src/components/FilterChips';
import { cardShadow, radius, spacing, useTheme, type ThemeColors } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { listRooms, type Room } from '../../src/api/rooms';
import {
  updateReservation,
  type Reservation,
} from '../../src/api/reservations';
import { getCalendarReservations } from '../../src/api/reservationCalendar';
import { getRoomBlocks } from '../../src/api/availability';
import { blockCoversDay } from '../../src/utils/availabilityGrid';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { formatDate } from '../../src/utils/format';
import { localDayISO } from '../../src/utils/todayPresentation';
import { calendarDataReady } from '../../src/utils/calendarData';
import { haptic } from '../../src/hooks/useHaptic';
import { ROUTES } from '../../src/navigation/routes';
import {
  ROOM_COL_WIDTH,
  ROW_HEIGHT,
  VIEW_PRESETS,
  addDaysISO,
  buildDayList,
  computeDropTarget,
  diffDays,
  distinctRoomTypes,
  filterCalendarRooms,
  hasMove,
  nextViewFromZoom,
  placeReservations,
  planMove,
  roomCalStatus,
  calendarCellStatus,
  toDateOnly,
  type CalendarView,
  type OccupancyFilter,
  type PlacedBar,
  type RoomCalStatus,
} from '../../src/utils/reservationCalendar';
import {
  reservationStatusLabel,
  reservationStatusTone,
  reservationAmountLabel,
} from '../../src/utils/reservationPresentation';

const USE_NATIVE_DRIVER = Platform.OS !== 'web';

function todayISO(): string {
  return localDayISO();
}

// Cell / bar palette. The five operator statuses map to the theme's status
// tokens; "blocked" gets the neutral slate so it reads as a hold, not an alarm.
function statusColor(status: RoomCalStatus, c: ThemeColors): string {
  switch (status) {
    case 'available':
      return c.success;
    case 'occupied':
      return c.primary;
    case 'cleaning':
      return c.warning;
    case 'out_of_order':
      return c.danger;
    case 'blocked':
      return c.textMuted;
  }
}

function shortDay(iso: string): { dow: string; dom: string } {
  try {
    const d = new Date(`${iso}T00:00:00`);
    return {
      dow: d.toLocaleDateString('tr-TR', { weekday: 'short' }),
      dom: d.toLocaleDateString('tr-TR', { day: '2-digit' }),
    };
  } catch {
    return { dow: '', dom: iso.slice(8) };
  }
}

type Toast = { msg: string; tone: 'success' | 'danger' };

// ── Draggable reservation bar ───────────────────────────────────────────────
// Lives in a single absolute overlay spanning the whole grid so it can be
// dragged across rooms (Y) and days (X). A long-press arms the pan so quick
// scrolls/taps are not hijacked; a tap opens the detail bubble. The grid math
// is delegated to the tested pure helpers; this component only renders + wires
// the gesture to those helpers and the backend mutation.
function ReservationBar({
  bar,
  roomIndex,
  dayWidth,
  dayCount,
  roomCount,
  compact,
  moving,
  canMove,
  c,
  onTap,
  onDrop,
}: {
  bar: PlacedBar;
  roomIndex: number;
  dayWidth: number;
  dayCount: number;
  roomCount: number;
  compact: boolean;
  moving: boolean;
  canMove: boolean;
  c: ThemeColors;
  onTap: (bar: PlacedBar) => void;
  onDrop: (bar: PlacedBar, dx: number, dy: number, reset: () => void) => void;
}) {
  const tx = useSharedValue(0);
  const ty = useSharedValue(0);
  const lifted = useSharedValue(0);

  const reset = useCallback(() => {
    tx.value = withSpring(0, { damping: 18, stiffness: 180 });
    ty.value = withSpring(0, { damping: 18, stiffness: 180 });
  }, [tx, ty]);

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: tx.value },
      { translateY: ty.value },
      { scale: 1 + lifted.value * 0.04 },
    ],
    zIndex: lifted.value > 0 ? 50 : 1,
    shadowOpacity: 0.25 + lifted.value * 0.3,
  }));

  const pan = Gesture.Pan()
    .enabled(canMove && !bar.clippedStart && !bar.clippedEnd && bar.reservation.status !== 'checked_out')
    .activateAfterLongPress(160)
    .onStart(() => {
      lifted.value = withTiming(1, { duration: 120 });
      runOnJS(haptic.tap)();
    })
    .onUpdate((e) => {
      tx.value = e.translationX;
      ty.value = e.translationY;
    })
    .onEnd((e, success) => {
      lifted.value = withTiming(0, { duration: 160 });
      if (success) runOnJS(onDrop)(bar, e.translationX, e.translationY, reset);
      else runOnJS(reset)();
    })
    .onFinalize((_e, success) => {
      lifted.value = withTiming(0, { duration: 160 });
      if (!success) runOnJS(reset)();
    });

  const tap = Gesture.Tap()
    .maxDuration(250)
    .onEnd((_e, success) => {
      if (success) runOnJS(onTap)(bar);
    });

  const gesture = Gesture.Race(pan, tap);

  // Every reservation is blue, consistently with the "Dolu" legend. Green
  // means free inventory, never an already checked-in reservation. Lifecycle
  // remains explicit in the accessible label and the detail sheet.
  const color = c.primary;
  const left = bar.startOffset * dayWidth;
  const width = Math.max(bar.nights * dayWidth - 4, dayWidth - 4);
  const top = roomIndex * ROW_HEIGHT;
  const name = bar.reservation.guest_name || tr.calendar.guest;

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View
        testID={`calendar-bar-${bar.reservation.id}`}
        accessibilityRole="button"
        accessibilityLabel={`${name} · ${reservationStatusLabel(bar.reservation.status)} · ${tr.calendar.openDetail}`}
        onAccessibilityTap={() => onTap(bar)}
        style={[
          {
            position: 'absolute',
            left: left + 2,
            top: top + 6,
            width,
            height: ROW_HEIGHT - 12,
            backgroundColor: color,
            borderRadius: radius.md,
            paddingHorizontal: compact ? 4 : spacing.sm,
            justifyContent: 'center',
            borderTopLeftRadius: bar.clippedStart ? 2 : radius.md,
            borderBottomLeftRadius: bar.clippedStart ? 2 : radius.md,
            borderTopRightRadius: bar.clippedEnd ? 2 : radius.md,
            borderBottomRightRadius: bar.clippedEnd ? 2 : radius.md,
            borderWidth: bar.reservation.vip_status ? 1.5 : 0,
            borderColor: c.vip,
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 3 },
            shadowRadius: 6,
            elevation: 4,
          },
          animStyle,
        ]}
      >
        {compact ? (
          <Text numberOfLines={1} style={{ color: '#fff', fontSize: 10, fontWeight: '700' }}>
            {name}
          </Text>
        ) : (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              {bar.reservation.vip_status ? (
                <Ionicons name="star" size={10} color={c.vip} />
              ) : null}
              <Text
                numberOfLines={1}
                style={{ color: '#fff', fontSize: 12, fontWeight: '700', flex: 1 }}
              >
                {name}
              </Text>
            </View>
            <Text numberOfLines={1} style={{ color: '#ffffffcc', fontSize: 10, fontWeight: '600' }}>
              {bar.totalNights} {tr.calendar.nights}
              {moving ? ` · ${tr.calendar.moving}` : ''}
            </Text>
          </>
        )}
      </Animated.View>
    </GestureDetector>
  );
}

export default function ReservationCalendarScreen() {
  const c = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const queryClient = useQueryClient();
  const online = useOnline();
  const { width: screenWidth } = useWindowDimensions();

  const [view, setView] = useState<CalendarView>('week');
  const [startDate, setStartDate] = useState<string>(todayISO());
  const [selected, setSelected] = useState<PlacedBar | null>(null);
  const [movingId, setMovingId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [roomTypeFilter, setRoomTypeFilter] = useState<string>('all');
  const [occupancyFilter, setOccupancyFilter] = useState<OccupancyFilter>('all');
  const [pendingMove, setPendingMove] = useState<{ label: string; apply: () => void } | null>(null);
  const moveInFlight = useRef(false);
  const [showTools, setShowTools] = useState(false);

  const headerScrollRef = useRef<ScrollView>(null);

  const preset = VIEW_PRESETS[view];
  const dayWidth = view === 'week' ? Math.max(52, (screenWidth - spacing.lg * 2 - ROOM_COL_WIDTH) / 5) : preset.dayWidth;
  const dayCount = preset.days;
  const dayList = useMemo(() => buildDayList(startDate, dayCount), [startDate, dayCount]);
  const endExclusive = useMemo(() => addDaysISO(startDate, dayCount), [startDate, dayCount]);

  const roomsQuery = useQuery({ queryKey: ['calendar', 'rooms'], queryFn: listRooms });
  const reservationsQuery = useQuery({
    queryKey: ['calendar', 'reservations', startDate, endExclusive],
    queryFn: () => getCalendarReservations(startDate, endExclusive),
  });
  const blocksQuery = useQuery({
    queryKey: ['calendar', 'blocks', startDate, endExclusive],
    queryFn: () => getRoomBlocks(startDate, endExclusive),
  });
  const dataReady = calendarDataReady(online, [roomsQuery, reservationsQuery, blocksQuery]);

  const rooms = useMemo<Room[]>(() => {
    const list = roomsQuery.data ?? [];
    return [...list].sort((a, b) =>
      (a.room_number || a.id).localeCompare(b.room_number || b.id, 'tr', { numeric: true }),
    );
  }, [roomsQuery.data]);

  // Resolve every reservation to a real room row (prefer room_id, fall back to
  // matching room_number) so a bar always lands on the right line. Built from
  // the FULL room set so resolution is independent of the active filter.
  const numberToId = useMemo(() => {
    const m = new Map<string, string>();
    rooms.forEach((r) => {
      if (r.room_number) m.set(r.room_number, r.id);
    });
    return m;
  }, [rooms]);

  const fullRoomIds = useMemo(() => new Set(rooms.map((r) => r.id)), [rooms]);

  // All bars across every room in the window — the basis for both occupancy
  // detection (which rooms to keep under the "Dolu/Müsait" chip) and the drawn
  // bars after row filtering.
  const allBars = useMemo(() => {
    const resolved: Reservation[] = (reservationsQuery.data ?? []).map((r) => {
      if (r.room_id && fullRoomIds.has(r.room_id)) return r;
      if (r.room_number && numberToId.has(r.room_number)) {
        return { ...r, room_id: numberToId.get(r.room_number) };
      }
      return r;
    });
    return placeReservations(resolved, dayList).filter((b) => fullRoomIds.has(b.roomId));
  }, [reservationsQuery.data, dayList, fullRoomIds, numberToId]);

  // Rooms with at least one reservation bar anywhere in the visible window.
  const occupiedRoomIds = useMemo(() => {
    const s = new Set<string>();
    allBars.forEach((b) => s.add(b.roomId));
    return s;
  }, [allBars]);

  // Distinct room types → filter chip options (locale-sorted, plus "Tümü").
  const roomTypeOptions = useMemo<FilterChipOption[]>(
    () => [
      { value: 'all', label: tr.calendar.filterAll },
      ...distinctRoomTypes(rooms).map((t) => ({ value: t, label: t })),
    ],
    [rooms],
  );

  const occupancyOptions = useMemo<FilterChipOption[]>(
    () => [
      { value: 'all', label: tr.calendar.filterAll },
      { value: 'occupied', label: tr.calendar.filterOccupied },
      { value: 'available', label: tr.calendar.filterAvailable },
    ],
    [],
  );

  // Visible rows after applying the type + occupancy chips. The filter only
  // narrows what is drawn; the backend query is untouched.
  const visibleRooms = useMemo(
    () => filterCalendarRooms(rooms, occupiedRoomIds, roomTypeFilter, occupancyFilter),
    [rooms, occupiedRoomIds, roomTypeFilter, occupancyFilter],
  );

  const roomIdToIndex = useMemo(() => {
    const m = new Map<string, number>();
    visibleRooms.forEach((r, i) => m.set(r.id, i));
    return m;
  }, [visibleRooms]);

  const bars = useMemo(
    () => allBars.filter((b) => roomIdToIndex.has(b.roomId)),
    [allBars, roomIdToIndex],
  );

  // Per-(room,day) occupancy from the drawn bars — used so an empty cell can
  // tell "müsait" from "dolu" without re-deriving the overlap.
  const occupied = useMemo(() => {
    const s = new Set<string>();
    bars.forEach((b) => {
      for (let i = 0; i < b.nights; i += 1) s.add(`${b.roomId}|${b.startOffset + i}`);
    });
    return s;
  }, [bars]);

  const blockedCell = useCallback(
    (roomId: string, day: string): boolean => {
      const blocks = blocksQuery.data ?? [];
      return blocks.some((bl) => bl.room_id === roomId && blockCoversDay(bl, day));
    },
    [blocksQuery.data],
  );

  const cellStatus = useCallback(
    (room: Room, dayIdx: number): RoomCalStatus => {
      const day = dayList[dayIdx];
      return calendarCellStatus({
        statuses: [room.status, room.room_status, room.hk_status, room.housekeeping_status],
        occupied: occupied.has(`${room.id}|${dayIdx}`),
        blocked: blockedCell(room.id, day),
        isToday: day === todayISO(),
      });
    },
    [dayList, occupied, blockedCell],
  );

  const flashToast = useCallback((t: Toast) => {
    setToast(t);
    setTimeout(() => setToast(null), 2600);
  }, []);

  const handleDrop = useCallback(
    (bar: PlacedBar, dx: number, dy: number, reset: () => void) => {
      // Never mutate from a stale/offline/partial grid or from a clipped stay:
      // its visible start is not necessarily the actual check-in date.
      if (!dataReady || movingId || bar.clippedStart || bar.clippedEnd || bar.reservation.status === 'checked_out') {
        reset();
        return;
      }
      const startRoomIndex = roomIdToIndex.get(bar.roomId) ?? 0;
      const target = computeDropTarget({
        startOffset: bar.startOffset,
        startRoomIndex,
        dx,
        dy,
        dayWidth,
        rowHeight: ROW_HEIGHT,
        dayCount,
        roomCount: visibleRooms.length,
        nights: bar.nights,
      });
      const targetRoom = visibleRooms[target.roomIndex];
      const plan = planMove({
        changedRoom: target.changedRoom,
        changedDay: target.changedDay,
        targetRoomId: targetRoom?.id,
        newCheckIn: dayList[target.dayOffset],
        nights: bar.totalNights,
      });

      if (!hasMove(plan)) {
        reset();
        return;
      }

      const resync = () => Promise.all([
        ['calendar'], ['frontdesk-rooms'], ['frontdesk-inhouse-rooms'],
        ['rooms'], ['hk-inhouse'], ['arrivals-today'], ['departures-today'],
        ['inhouse'], ['hub-today'], ['noshow-today'], ['reservations-search'],
        ['reservation-full', bar.reservation.id], ['reservation-enhanced', bar.reservation.id],
        ['reservation-ota', bar.reservation.id],
      ].map((queryKey) => queryClient.invalidateQueries({ queryKey })));

      const apply = async () => {
        if (moveInFlight.current) return;
        moveInFlight.current = true;
        setMovingId(bar.reservation.id);
        // The common reservation service validates the effective room + dates
        // together and reserves its nights atomically. The legacy assign-room
        // shortcut does not perform date-overlap validation.
        try {
          await updateReservation(bar.reservation.id, {
            ...(plan.assignRoomId ? { room_id: plan.assignRoomId } : {}),
            ...(plan.newCheckIn ? { check_in: plan.newCheckIn, check_out: plan.newCheckOut } : {}),
          });
          haptic.success();
          flashToast({
            msg:
              plan.assignRoomId && plan.newCheckIn
                ? tr.calendar.moveSuccess
                : plan.assignRoomId
                  ? tr.calendar.moveRoom
                  : tr.calendar.moveDates,
            tone: 'success',
          });
          await resync();
        } catch (e) {
          // A lost response is not proof of rollback. Refetch truth and never
          // claim that the original room/date has been restored.
          haptic.error();
          await resync();
          flashToast({
            msg: isOffline(e) ? errorMessage(e, tr.calendar.moveFailed) : tr.calendar.moveFailed,
            tone: 'danger',
          });
        } finally {
          moveInFlight.current = false;
          setMovingId(null);
        }
      };
      reset();
      setPendingMove({
        label: `${bar.reservation.guest_name || tr.calendar.guest} · ${targetRoom?.room_number || '—'}\n${formatDate(plan.newCheckIn || bar.reservation.check_in)} – ${formatDate(plan.newCheckOut || bar.reservation.check_out)}`,
        apply: () => { setPendingMove(null); void apply(); },
      });
    },
    [roomIdToIndex, dayWidth, dayCount, visibleRooms, dayList, queryClient, flashToast, dataReady, movingId],
  );

  const onBodyScroll = useCallback((e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const x = e.nativeEvent.contentOffset.x;
    headerScrollRef.current?.scrollTo({ x, animated: false });
  }, []);

  const pinch = useMemo(
    () =>
      Gesture.Pinch().onEnd((e, success) => {
        if (success) runOnJS(setView)(nextViewFromZoom(view, e.scale));
      }),
    [view],
  );

  const loading = roomsQuery.isPending || reservationsQuery.isPending || blocksQuery.isPending;
  const errored = roomsQuery.isError || reservationsQuery.isError || blocksQuery.isError;
  const reload = () => { roomsQuery.refetch(); reservationsQuery.refetch(); blocksQuery.refetch(); };
  const gridWidth = dayCount * dayWidth;
  const gridHeight = visibleRooms.length * ROW_HEIGHT;
  const filtered = roomTypeFilter !== 'all' || occupancyFilter !== 'all';
  const compact = view === 'month';

  const shiftWindow = (dir: number) => setStartDate(addDaysISO(startDate, dir * dayCount));

  const openReservationForCell = useCallback(
    (room: Room, day: string) => {
      haptic.tap();
      router.push({
        pathname: ROUTES.newReservation,
        params: {
          room_id: room.id,
          room_number: room.room_number || '',
          room_type: room.room_type || '',
          check_in: day,
          check_out: addDaysISO(day, 1),
        },
      });
    },
    [router],
  );

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: c.bg }}>
      <View
        testID="calendar-screen"
        style={{ flex: 1, paddingTop: spacing.md, paddingBottom: insets.bottom }}
      >
        <View style={{ paddingHorizontal: spacing.lg }}>
          <OfflineBanner visible={!online} />
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm }}>
            <H1 style={{ flex: 1 }}>{tr.calendar.openCta}</H1>
            <Pressable
              testID="calendar-tools"
              accessibilityRole="button"
              accessibilityLabel={tr.calendar.tools}
              accessibilityState={{ expanded: showTools }}
              onPress={() => setShowTools((value) => !value)}
              style={{ width: 48, height: 48, borderRadius: radius.md, backgroundColor: showTools ? c.primarySoft : c.surface, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: c.border }}
            >
              <Ionicons name="options-outline" size={24} color={c.primary} />
            </Pressable>
            <Pressable
              testID="calendar-new-reservation"
              accessibilityRole="button"
              accessibilityLabel={tr.reservations.newReservation}
              onPress={() => router.push(ROUTES.newReservation)}
              style={{ width: 48, height: 48, borderRadius: radius.md, backgroundColor: c.primary, alignItems: 'center', justifyContent: 'center' }}
            >
              <Ionicons name="add" size={28} color={c.primaryText} />
            </Pressable>
          </View>
          <Muted style={{ marginTop: 2 }}>{tr.calendar.subtitle}</Muted>
        </View>

        {/* View toggle */}
        <View style={{ flexDirection: 'row', gap: spacing.sm, paddingHorizontal: spacing.lg, marginTop: spacing.md }}>
          {(['day', 'week', 'month'] as CalendarView[]).map((v) => {
            const active = v === view;
            const label =
              v === 'day' ? tr.calendar.viewDay : v === 'week' ? tr.calendar.viewWeek : tr.calendar.viewMonth;
            return (
              <Pressable
                key={v}
                testID={`calendar-view-${v}`}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                // react-native-web 0.19 drops accessibilityState.selected on web
                // (it only emits the direct aria-* props), so the active view tab
                // exposed no aria-selected to screen readers or e2e. Emit it
                // explicitly; on native RN 0.74 aria-selected maps back to
                // accessibilityState.selected, so there is no native regression.
                aria-selected={active}
                onPress={() => {
                  haptic.tap();
                  setView(v);
                }}
                style={{
                  flex: 1,
                  minHeight: 48,
                  justifyContent: 'center',
                  paddingVertical: spacing.sm,
                  borderRadius: radius.md,
                  alignItems: 'center',
                  backgroundColor: active ? c.primary : c.surfaceAlt,
                  borderWidth: 1,
                  borderColor: active ? c.primary : c.border,
                }}
              >
                <Text style={{ color: active ? c.primaryText : c.text, fontWeight: '700', fontSize: 13 }}>
                  {label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {/* Date navigation */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingHorizontal: spacing.lg,
            marginTop: spacing.sm,
          }}
        >
          <Pressable
            testID="calendar-nav-prev"
            accessibilityRole="button"
            accessibilityLabel={tr.calendar.prev}
            onPress={() => {
              haptic.tap();
              shiftWindow(-1);
            }}
            style={{ width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}
          >
            <Ionicons name="chevron-back" size={22} color={c.text} />
          </Pressable>
          <Pressable
            testID="calendar-nav-today"
            accessibilityRole="button"
            onPress={() => {
              haptic.tap();
              setStartDate(todayISO());
            }}
            style={{ flex: 1, minHeight: 48, alignItems: 'center', justifyContent: 'center' }}
          >
            <Body style={{ fontWeight: '700' }}>
              {formatDate(dayList[0])} – {formatDate(dayList[dayList.length - 1])}
            </Body>
            <Muted style={{ fontSize: 11 }}>{tr.calendar.today}</Muted>
          </Pressable>
          <Pressable
            testID="calendar-nav-next"
            accessibilityRole="button"
            accessibilityLabel={tr.calendar.next}
            onPress={() => {
              haptic.tap();
              shiftWindow(1);
            }}
            style={{ width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}
          >
            <Ionicons name="chevron-forward" size={22} color={c.text} />
          </Pressable>
        </View>

        {/* Jump to an arbitrary date (besides the Today shortcut above) */}
        {showTools ? <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.sm }}>
          <DatePicker
            testID="calendar-jump-date"
            value={startDate}
            placeholder={tr.calendar.jumpToDate}
            onChange={(iso) => {
              if (!iso) return;
              haptic.tap();
              setStartDate(iso);
            }}
          />
        </View> : null}

        {/* Legend */}
        <View
          testID="calendar-legend"
          style={{
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: spacing.sm,
            paddingHorizontal: spacing.lg,
            marginTop: spacing.sm,
          }}
        >
          {(
            [
              ['available', tr.calendar.statusAvailable],
              ['occupied', tr.calendar.statusOccupied],
              ['cleaning', tr.calendar.statusCleaning],
              ['out_of_order', tr.calendar.statusOutOfOrder],
              ['blocked', tr.calendar.statusBlocked],
            ] as [RoomCalStatus, string][]
          ).map(([s, label]) => (
            <View key={s} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: statusColor(s, c) }} />
              <Muted style={{ fontSize: 11 }}>{label}</Muted>
            </View>
          ))}
        </View>

        {/* Visible-grid filters (room type + occupancy). These only narrow the
            drawn rows; the backend search is never re-issued. */}
        {!loading && !errored && rooms.length > 0 ? (
          <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.sm, gap: spacing.xs }}>
            {roomTypeOptions.length > 2 ? (
              <FilterChips
                testID="calendar-filter-roomtype"
                options={roomTypeOptions}
                value={roomTypeFilter}
                onChange={setRoomTypeFilter}
              />
            ) : null}
            {showTools ? <FilterChips
              testID="calendar-filter-occupancy"
              options={occupancyOptions}
              value={occupancyFilter}
              onChange={(v) => setOccupancyFilter(v as OccupancyFilter)}
            /> : null}
          </View>
        ) : null}

        <View style={{ height: spacing.sm }} />

        {/* Grid */}
        {!online && loading ? (
          <EmptyState icon="cloud-offline-outline" title={tr.app.offline} />
        ) : loading ? (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
            <ActivityIndicator color={c.primary} />
          </View>
        ) : errored ? (
          <View style={{ padding: spacing.lg, gap: spacing.md }}>
            <EmptyState testID="calendar-error" icon="alert-circle-outline" title={tr.calendar.loadError} />
            <Button title={tr.app.retry} onPress={reload} disabled={!online} icon="refresh" fullWidth />
          </View>
        ) : rooms.length === 0 ? (
          <EmptyState testID="calendar-empty" icon="bed-outline" title={tr.calendar.empty} />
        ) : visibleRooms.length === 0 ? (
          <EmptyState
            testID="calendar-filter-empty"
            icon="filter-outline"
            title={tr.calendar.filterNoMatch}
          />
        ) : (
          <View style={{ flex: 1 }}>
            {/* Sticky header row: corner + day columns (synced to body scroll) */}
            <View style={{ flexDirection: 'row', paddingLeft: spacing.lg }}>
              <View
                style={{
                  width: ROOM_COL_WIDTH,
                  justifyContent: 'flex-end',
                  paddingBottom: 4,
                }}
              >
                <Muted style={{ fontSize: 11, fontWeight: '700' }}>
                  {visibleRooms.length}
                  {filtered ? `/${rooms.length}` : ''} {tr.calendar.rooms}
                </Muted>
              </View>
              <ScrollView
                ref={headerScrollRef}
                horizontal
                scrollEnabled={false}
                showsHorizontalScrollIndicator={false}
              >
                <View style={{ flexDirection: 'row', width: gridWidth }}>
                  {dayList.map((d, i) => {
                    const sd = shortDay(d);
                    const isToday = d === todayISO();
                    return (
                      <View
                        key={d}
                        testID={`calendar-daycol-${i}`}
                        style={{
                          width: dayWidth,
                          alignItems: 'center',
                          paddingVertical: 4,
                          borderTopLeftRadius: radius.sm,
                          borderTopRightRadius: radius.sm,
                          backgroundColor: isToday ? c.primarySoft : 'transparent',
                        }}
                      >
                        <Muted style={{ fontSize: 10 }}>{sd.dow}</Muted>
                        <Text
                          style={{
                            color: isToday ? c.primary : c.text,
                            fontWeight: '700',
                            fontSize: compact ? 11 : 13,
                          }}
                        >
                          {sd.dom}
                        </Text>
                      </View>
                    );
                  })}
                </View>
              </ScrollView>
            </View>

            {/* Body: vertical scroll wrapping [room column | horizontal grid] */}
            <GestureDetector gesture={pinch}>
              <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingLeft: spacing.lg, paddingBottom: spacing.xl }}>
                <View style={{ flexDirection: 'row' }}>
                  {/* Room label column (scrolls vertically with the grid) */}
                  <View style={{ width: ROOM_COL_WIDTH }}>
                    {visibleRooms.map((room, idx) => (
                      <FadeInView
                        key={room.id}
                        delay={Math.min(idx * 18, 240)}
                        style={{
                          height: ROW_HEIGHT,
                          justifyContent: 'center',
                          paddingRight: spacing.sm,
                          borderBottomWidth: 1,
                          borderBottomColor: c.border,
                        }}
                      >
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <View
                            style={{
                              width: 8,
                              height: 8,
                              borderRadius: 2,
                              backgroundColor: statusColor(roomCalStatus(room.status, false), c),
                            }}
                          />
                          <Text style={{ color: c.text, fontWeight: '700', fontSize: 13 }} numberOfLines={1}>
                            {room.room_number}
                          </Text>
                        </View>
                        {room.room_type ? (
                          <Muted style={{ fontSize: 10 }} numberOfLines={1}>
                            {room.room_type}
                          </Muted>
                        ) : null}
                      </FadeInView>
                    ))}
                  </View>

                  {/* Day grid + draggable bars overlay */}
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    scrollEventThrottle={16}
                    onScroll={onBodyScroll}
                    testID="calendar-grid"
                  >
                    <View style={{ width: gridWidth, height: gridHeight }}>
                      {/* Background cells */}
                      {visibleRooms.map((room, ri) => (
                        <View
                          key={room.id}
                          style={{
                            flexDirection: 'row',
                            height: ROW_HEIGHT,
                            borderBottomWidth: 1,
                            borderBottomColor: c.border,
                          }}
                        >
                          {dayList.map((d, di) => {
                            const st = cellStatus(room, di);
                            const isToday = d === todayISO();
                            return (
                              <Pressable
                                key={d}
                                disabled={st !== 'available' || !dataReady}
                                onPress={() => openReservationForCell(room, d)}
                                accessibilityRole={st === 'available' ? 'button' : undefined}
                                accessibilityLabel={
                                  st === 'available'
                                    ? `${room.room_number} · ${formatDate(d)} · ${tr.reservations.newReservation}`
                                    : undefined
                                }
                                testID={`calendar-cell-${room.id}-${d}`}
                                style={{
                                  width: dayWidth,
                                  height: ROW_HEIGHT,
                                  borderRightWidth: 1,
                                  borderRightColor: c.border,
                                  backgroundColor:
                                    st === 'available'
                                      ? isToday
                                        ? c.primarySoft
                                        : 'transparent'
                                      : statusColor(st, c) + '1f',
                                }}
                              />
                            );
                          })}
                        </View>
                      ))}

                      {/* Reservation bars */}
                      {bars.map((bar) => {
                        const ri = roomIdToIndex.get(bar.roomId) ?? 0;
                        return (
                          <ReservationBar
                            key={bar.reservation.id}
                            bar={bar}
                            roomIndex={ri}
                            dayWidth={dayWidth}
                            dayCount={dayCount}
                            roomCount={rooms.length}
                            compact={compact}
                            moving={movingId === bar.reservation.id}
                            canMove={dataReady && !movingId && !pendingMove}
                            c={c}
                            onTap={setSelected}
                            onDrop={handleDrop}
                          />
                        );
                      })}
                    </View>
                  </ScrollView>
                </View>

                <Muted style={{ marginTop: spacing.md, fontSize: 11 }}>
                  {tr.calendar.dragHint}
                </Muted>
              </ScrollView>
            </GestureDetector>
          </View>
        )}

        {/* Toast */}
        {toast ? (
          <FadeInView
            style={{
              position: 'absolute',
              left: spacing.lg,
              right: spacing.lg,
              bottom: insets.bottom + spacing.lg,
            }}
          >
            <View
              testID="calendar-toast"
              style={{
                backgroundColor: toast.tone === 'success' ? c.success : c.danger,
                borderRadius: radius.md,
                paddingVertical: spacing.md,
                paddingHorizontal: spacing.lg,
                ...cardShadow,
              }}
            >
              <Text style={{ color: '#fff', fontWeight: '700' }}>{toast.msg}</Text>
            </View>
          </FadeInView>
        ) : null}
      </View>

      <ActionSheet
        visible={!!pendingMove}
        onClose={() => setPendingMove(null)}
        title={tr.calendar.moveConfirmTitle}
        testID="calendar-move-confirm"
      >
        <Body>{pendingMove?.label}</Body>
        <Muted>{tr.calendar.moveConfirmHint}</Muted>
        <Button title={tr.calendar.moveConfirm} onPress={() => pendingMove?.apply()} disabled={!dataReady || !!movingId} fullWidth />
        <Button title={tr.app.cancel} variant="outline" onPress={() => setPendingMove(null)} fullWidth />
      </ActionSheet>

      {/* Detail bubble */}
      <Modal visible={!!selected} transparent animationType={USE_NATIVE_DRIVER ? 'slide' : 'fade'} onRequestClose={() => setSelected(null)}>
        <Pressable
          style={{ flex: 1, backgroundColor: '#0009', justifyContent: 'flex-end' }}
          onPress={() => setSelected(null)}
        >
          <Pressable
            testID="calendar-detail"
            onPress={(e) => e.stopPropagation()}
            style={{
              backgroundColor: c.surface,
              borderTopLeftRadius: radius.xl,
              borderTopRightRadius: radius.xl,
              padding: spacing.lg,
              paddingBottom: insets.bottom + spacing.lg,
              borderTopWidth: 1,
              borderColor: c.border,
            }}
          >
            {selected ? (
              <DetailBody
                bar={selected}
                c={c}
                onClose={() => setSelected(null)}
                onOpen={() => {
                  const r = selected.reservation;
                  setSelected(null);
                  router.push({
                    pathname: ROUTES.reservationDetail,
                    params: {
                      id: r.id,
                      guest_name: r.guest_name || '',
                      room_number: r.room_number || '',
                      room_type: r.room_type || '',
                      check_in: r.check_in || '',
                      check_out: r.check_out || '',
                      status: r.status || '',
                      total_amount: r.total_amount != null ? String(r.total_amount) : '',
                      paid_amount: r.paid_amount != null ? String(r.paid_amount) : '',
                      balance: r.balance != null ? String(r.balance) : '',
                      currency: r.currency || '',
                    },
                  });
                }}
              />
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
    </GestureHandlerRootView>
  );
}

function DetailBody({
  bar,
  c,
  onClose,
  onOpen,
}: {
  bar: PlacedBar;
  c: ThemeColors;
  onClose: () => void;
  onOpen: () => void;
}) {
  const r = bar.reservation;
  const ci = toDateOnly(r.check_in);
  const co = toDateOnly(r.check_out);
  const nights = ci && co ? Math.max(1, diffDays(ci, co)) : bar.nights;
  const tone = reservationStatusTone(r.status);

  return (
    <View style={{ gap: spacing.sm }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <H2>{r.guest_name || tr.calendar.guest}</H2>
        <Pressable testID="calendar-detail-close" onPress={onClose} accessibilityRole="button" accessibilityLabel={tr.calendar.close} style={{ width: 48, height: 48, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="close" size={24} color={c.textMuted} />
        </Pressable>
      </View>
      <View style={{ flexDirection: 'row', gap: spacing.xs, flexWrap: 'wrap' }}>
        <Badge label={reservationStatusLabel(r.status)} tone={tone} />
        {r.vip_status ? <Badge label={tr.calendar.vip} tone="vip" icon="star" /> : null}
      </View>

      <Row label={tr.calendar.room} value={r.room_number || tr.calendar.noRoom} c={c} />
      <Row
        label={tr.calendar.stay}
        value={`${formatDate(r.check_in)} – ${formatDate(r.check_out)} · ${nights} ${tr.calendar.nights}`}
        c={c}
      />
      <Row label={tr.calendar.price} value={reservationAmountLabel(r.total_amount, r.currency)} c={c} />
      <Button
        title={tr.calendar.openDetail}
        icon="open-outline"
        onPress={onOpen}
        fullWidth
      />
    </View>
  );
}

function Row({ label, value, c }: { label: string; value: string; c: ThemeColors }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 }}>
      <Text style={{ color: c.textMuted, fontSize: 13 }}>{label}</Text>
      <Text style={{ color: c.text, fontSize: 14, fontWeight: '600', flexShrink: 1, textAlign: 'right' }}>
        {value}
      </Text>
    </View>
  );
}
