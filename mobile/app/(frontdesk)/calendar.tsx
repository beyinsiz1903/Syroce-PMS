import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
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

import { Badge, Body, EmptyState, FadeInView, H1, H2, Muted } from '../../src/components/ui';
import { cardShadow, radius, spacing, useTheme, type ThemeColors } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { listRooms, type Room } from '../../src/api/rooms';
import { assignRoom } from '../../src/api/bookings';
import {
  searchReservations,
  updateReservation,
  type Reservation,
} from '../../src/api/reservations';
import { getRoomBlocks } from '../../src/api/availability';
import { blockCoversDay } from '../../src/utils/availabilityGrid';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { formatCurrency, formatDate } from '../../src/utils/format';
import { haptic } from '../../src/hooks/useHaptic';
import {
  ROOM_COL_WIDTH,
  ROW_HEIGHT,
  VIEW_PRESETS,
  addDaysISO,
  buildDayList,
  computeDropTarget,
  diffDays,
  hasMove,
  nextViewFromZoom,
  placeReservations,
  planMove,
  roomCalStatus,
  toDateOnly,
  type CalendarView,
  type PlacedBar,
  type RoomCalStatus,
} from '../../src/utils/reservationCalendar';

const USE_NATIVE_DRIVER = Platform.OS !== 'web';

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
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

// A reservation bar is coloured by its OWN lifecycle status (checked-in guests
// read green, upcoming confirmed blue, departed muted) — distinct from the
// room-condition cell tint underneath.
function barColor(status: string | undefined, c: ThemeColors): string {
  switch ((status || '').toLowerCase()) {
    case 'checked_in':
      return c.success;
    case 'confirmed':
    case 'guaranteed':
      return c.primary;
    case 'checked_out':
      return c.textMuted;
    default:
      return c.warning;
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
    .activateAfterLongPress(160)
    .onStart(() => {
      lifted.value = withTiming(1, { duration: 120 });
      runOnJS(haptic.tap)();
    })
    .onUpdate((e) => {
      tx.value = e.translationX;
      ty.value = e.translationY;
    })
    .onEnd((e) => {
      lifted.value = withTiming(0, { duration: 160 });
      runOnJS(onDrop)(bar, e.translationX, e.translationY, reset);
    })
    .onFinalize(() => {
      lifted.value = withTiming(0, { duration: 160 });
    });

  const tap = Gesture.Tap()
    .maxDuration(250)
    .onEnd(() => {
      runOnJS(onTap)(bar);
    });

  const gesture = Gesture.Race(pan, tap);

  const color = barColor(bar.reservation.status, c);
  const left = bar.startOffset * dayWidth;
  const width = Math.max(bar.nights * dayWidth - 4, dayWidth - 4);
  const top = roomIndex * ROW_HEIGHT;
  const name = bar.reservation.guest_name || tr.calendar.guest;

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View
        testID={`calendar-bar-${bar.reservation.id}`}
        accessibilityRole="button"
        accessibilityLabel={`${name} ${tr.calendar.openDetail}`}
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
              {bar.nights} {tr.calendar.nights}
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
  const insets = useSafeAreaInsets();
  const queryClient = useQueryClient();

  const [view, setView] = useState<CalendarView>('week');
  const [startDate, setStartDate] = useState<string>(todayISO());
  const [selected, setSelected] = useState<PlacedBar | null>(null);
  const [movingId, setMovingId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  const headerScrollRef = useRef<ScrollView>(null);

  const preset = VIEW_PRESETS[view];
  const dayWidth = preset.dayWidth;
  const dayCount = preset.days;
  const dayList = useMemo(() => buildDayList(startDate, dayCount), [startDate, dayCount]);
  const endExclusive = useMemo(() => addDaysISO(startDate, dayCount), [startDate, dayCount]);

  const roomsQuery = useQuery({ queryKey: ['calendar', 'rooms'], queryFn: listRooms });
  const reservationsQuery = useQuery({
    queryKey: ['calendar', 'reservations'],
    queryFn: () => searchReservations({}),
  });
  const blocksQuery = useQuery({
    queryKey: ['calendar', 'blocks', startDate, endExclusive],
    queryFn: () => getRoomBlocks(startDate, endExclusive),
  });

  const rooms = useMemo<Room[]>(() => {
    const list = roomsQuery.data ?? [];
    return [...list].sort((a, b) =>
      (a.room_number || a.id).localeCompare(b.room_number || b.id, 'tr', { numeric: true }),
    );
  }, [roomsQuery.data]);

  // Resolve every reservation to a real room row (prefer room_id, fall back to
  // matching room_number) so a bar always lands on the right line.
  const numberToId = useMemo(() => {
    const m = new Map<string, string>();
    rooms.forEach((r) => {
      if (r.room_number) m.set(r.room_number, r.id);
    });
    return m;
  }, [rooms]);

  const roomIdToIndex = useMemo(() => {
    const m = new Map<string, number>();
    rooms.forEach((r, i) => m.set(r.id, i));
    return m;
  }, [rooms]);

  const bars = useMemo(() => {
    const resolved: Reservation[] = (reservationsQuery.data ?? []).map((r) => {
      if (r.room_id && roomIdToIndex.has(r.room_id)) return r;
      if (r.room_number && numberToId.has(r.room_number)) {
        return { ...r, room_id: numberToId.get(r.room_number) };
      }
      return r;
    });
    return placeReservations(resolved, dayList).filter((b) => roomIdToIndex.has(b.roomId));
  }, [reservationsQuery.data, dayList, roomIdToIndex, numberToId]);

  // Per-(room,day) occupancy from the placed bars — used so an empty cell can
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
      if (occupied.has(`${room.id}|${dayIdx}`)) return 'occupied';
      if (blockedCell(room.id, day)) return 'blocked';
      return roomCalStatus(room.status, false);
    },
    [dayList, occupied, blockedCell],
  );

  const flashToast = useCallback((t: Toast) => {
    setToast(t);
    setTimeout(() => setToast(null), 2600);
  }, []);

  const handleDrop = useCallback(
    (bar: PlacedBar, dx: number, dy: number, reset: () => void) => {
      const startRoomIndex = roomIdToIndex.get(bar.roomId) ?? 0;
      const target = computeDropTarget({
        startOffset: bar.startOffset,
        startRoomIndex,
        dx,
        dy,
        dayWidth,
        rowHeight: ROW_HEIGHT,
        dayCount,
        roomCount: rooms.length,
        nights: bar.nights,
      });
      const trueNights = (() => {
        const ci = toDateOnly(bar.reservation.check_in);
        const co = toDateOnly(bar.reservation.check_out);
        if (ci && co) return Math.max(1, diffDays(ci, co));
        return bar.nights;
      })();
      const targetRoom = rooms[target.roomIndex];
      const plan = planMove({
        changedRoom: target.changedRoom,
        changedDay: target.changedDay,
        targetRoomId: targetRoom?.id,
        newCheckIn: dayList[target.dayOffset],
        nights: trueNights,
      });

      if (!hasMove(plan)) {
        reset();
        return;
      }

      setMovingId(bar.reservation.id);
      const resync = () =>
        Promise.all([
          queryClient.invalidateQueries({ queryKey: ['calendar', 'reservations'] }),
          queryClient.invalidateQueries({ queryKey: ['calendar', 'rooms'] }),
          queryClient.invalidateQueries({ queryKey: ['calendar', 'blocks'] }),
        ]);

      (async () => {
        // assign-room and date-update are two separate backend calls with no
        // single atomic endpoint, so track each step. A failure AFTER a prior
        // step succeeded is a real partial mutation — we must NOT spring the
        // card back (that would be a fake rollback); instead refetch server
        // truth so the grid shows exactly what the backend now holds.
        let committed = false;
        try {
          if (plan.assignRoomId) {
            await assignRoom(bar.reservation.id, plan.assignRoomId);
            committed = true;
          }
          if (plan.newCheckIn && plan.newCheckOut) {
            await updateReservation(bar.reservation.id, {
              check_in: plan.newCheckIn,
              check_out: plan.newCheckOut,
            });
            committed = true;
          }
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
          if (committed) {
            // Partial mutation already landed on the backend. Be honest: don't
            // claim full failure and don't fake a rollback — show partial and
            // re-sync so the card sits where the server actually placed it.
            haptic.warning();
            await resync();
            flashToast({ msg: tr.calendar.movePartial, tone: 'danger' });
          } else {
            // Nothing changed on the backend: safe to snap the card back, then
            // re-sync to reflect server truth (which still equals the origin).
            haptic.error();
            reset();
            await resync();
            flashToast({
              msg: isOffline(e) ? errorMessage(e, tr.calendar.moveFailed) : tr.calendar.moveFailed,
              tone: 'danger',
            });
          }
        } finally {
          setMovingId(null);
        }
      })();
    },
    [roomIdToIndex, dayWidth, dayCount, rooms, dayList, queryClient, flashToast],
  );

  const onBodyScroll = useCallback((e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const x = e.nativeEvent.contentOffset.x;
    headerScrollRef.current?.scrollTo({ x, animated: false });
  }, []);

  const pinch = useMemo(
    () =>
      Gesture.Pinch().onEnd((e) => {
        runOnJS(setView)(nextViewFromZoom(view, e.scale));
      }),
    [view],
  );

  const loading = roomsQuery.isLoading || reservationsQuery.isLoading;
  const errored = roomsQuery.isError || reservationsQuery.isError;
  const gridWidth = dayCount * dayWidth;
  const gridHeight = rooms.length * ROW_HEIGHT;
  const compact = view === 'month';

  const shiftWindow = (dir: number) => setStartDate(addDaysISO(startDate, dir * dayCount));

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: c.bg }}>
      <View
        testID="calendar-screen"
        style={{ flex: 1, paddingTop: spacing.md, paddingBottom: insets.bottom }}
      >
        <View style={{ paddingHorizontal: spacing.lg }}>
          <H1>{tr.calendar.title}</H1>
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
                onPress={() => {
                  haptic.tap();
                  setView(v);
                }}
                style={{
                  flex: 1,
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
            style={{ padding: spacing.sm }}
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
            style={{ flex: 1, alignItems: 'center' }}
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
            style={{ padding: spacing.sm }}
          >
            <Ionicons name="chevron-forward" size={22} color={c.text} />
          </Pressable>
        </View>

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

        <View style={{ height: spacing.sm }} />

        {/* Grid */}
        {loading ? (
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
            <ActivityIndicator color={c.primary} />
          </View>
        ) : errored ? (
          <EmptyState
            testID="calendar-error"
            icon="alert-circle-outline"
            title={tr.calendar.loadError}
          />
        ) : rooms.length === 0 ? (
          <EmptyState testID="calendar-empty" icon="bed-outline" title={tr.calendar.empty} />
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
                  {rooms.length} {tr.calendar.rooms}
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
                    {rooms.map((room, idx) => (
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
                      {rooms.map((room, ri) => (
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
                              <View
                                key={d}
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
              <DetailBody bar={selected} c={c} onClose={() => setSelected(null)} />
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
    </GestureHandlerRootView>
  );
}

function DetailBody({ bar, c, onClose }: { bar: PlacedBar; c: ThemeColors; onClose: () => void }) {
  const r = bar.reservation;
  const ci = toDateOnly(r.check_in);
  const co = toDateOnly(r.check_out);
  const nights = ci && co ? Math.max(1, diffDays(ci, co)) : bar.nights;
  const tone = (() => {
    switch ((r.status || '').toLowerCase()) {
      case 'checked_in':
        return 'success' as const;
      case 'confirmed':
      case 'guaranteed':
        return 'info' as const;
      case 'checked_out':
        return 'default' as const;
      default:
        return 'warning' as const;
    }
  })();

  return (
    <View style={{ gap: spacing.sm }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <H2>{r.guest_name || tr.calendar.guest}</H2>
        <Pressable testID="calendar-detail-close" onPress={onClose} accessibilityRole="button" accessibilityLabel={tr.calendar.close}>
          <Ionicons name="close" size={24} color={c.textMuted} />
        </Pressable>
      </View>
      <View style={{ flexDirection: 'row', gap: spacing.xs, flexWrap: 'wrap' }}>
        <Badge label={r.status || '—'} tone={tone} />
        {r.vip_status ? <Badge label={tr.calendar.vip} tone="vip" icon="star" /> : null}
      </View>

      <Row label={tr.calendar.room} value={r.room_number || tr.calendar.noRoom} c={c} />
      <Row
        label={tr.calendar.stay}
        value={`${formatDate(r.check_in)} – ${formatDate(r.check_out)} · ${nights} ${tr.calendar.nights}`}
        c={c}
      />
      <Row label={tr.calendar.price} value={formatCurrency(r.total_amount)} c={c} />
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
