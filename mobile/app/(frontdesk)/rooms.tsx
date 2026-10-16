import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Badge, Body, Button, Card, EmptyState, Field, H1, Muted, SkeletonCard, webCenter } from '../../src/components/ui';
import { KpiPill } from '../../src/components/KpiCard';
import { FilterChips, FilterChipOption } from '../../src/components/FilterChips';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, roomStatusColor, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { listRooms, listRoomTasks, Room, RoomTask } from '../../src/api/rooms';
import { Booking, getInHouse } from '../../src/api/bookings';
import { reservationAmountLabel, reservationCurrency } from '../../src/utils/reservationPresentation';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { ROUTES } from '../../src/navigation/routes';
import { asArray } from '../../src/utils/queryData';
import { useOnline } from '../../src/hooks/useOnline';
import {
  effectiveRoomStatus,
  indexBookingsByRoomNumber,
  roomNumberKey,
  roomPresentation,
  RoomCleaning,
} from '../../src/utils/roomPresentation';

type StatusTone = 'success' | 'primary' | 'warning' | 'info' | 'danger' | 'default';

function statusLabel(status?: string): string {
  switch ((status || '').toLowerCase()) {
    case 'available':
      return tr.rooms.statusAvailable;
    case 'clean':
    case 'inspection':
      return tr.rooms.statusInspection;
    case 'inspected':
      return tr.rooms.statusInspected;
    case 'occupied':
      return tr.rooms.statusOccupied;
    case 'dirty':
      return tr.rooms.statusDirty;
    case 'cleaning':
      return tr.rooms.statusCleaning;
    case 'maintenance':
      return tr.rooms.statusMaintenance;
    case 'out_of_order':
      return tr.rooms.statusOutOfOrder;
    default:
      return tr.rooms.statusUnknown;
  }
}

const CLEANING_LABELS: Record<RoomCleaning, string> = {
  dirty: tr.rooms.statusDirty, cleaning: tr.rooms.statusCleaning, inspection: tr.rooms.statusInspection,
  inspected: tr.rooms.statusInspected, ready: tr.rooms.statusReady, blocked: tr.rooms.statusBlocked, unknown: tr.rooms.statusUnknown,
};

// Whole nights between two ISO dates; null when either side is missing/invalid.
function nightsBetween(checkIn?: string, checkOut?: string): number | null {
  if (!checkIn || !checkOut) return null;
  const a = new Date(checkIn).getTime();
  const b = new Date(checkOut).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  const n = Math.round((b - a) / 86400000);
  return n > 0 ? n : null;
}

const STATUS_FILTERS: FilterChipOption[] = [
  { value: '', label: tr.rooms.statusAll },
  { value: 'vacant', label: tr.rooms.vacant },
  { value: 'occupied', label: tr.rooms.statusOccupied },
  { value: 'blocked', label: tr.rooms.statusBlocked },
];
const CLEANING_FILTERS: FilterChipOption[] = [
  { value: '', label: tr.rooms.statusAll },
  { value: 'dirty', label: tr.rooms.statusDirty },
  { value: 'cleaning', label: tr.rooms.statusCleaning },
  { value: 'inspection', label: tr.rooms.statusInspection },
  { value: 'ready', label: tr.rooms.statusReady },
];

function RoomCard({
  room,
  booking,
  taskCount,
  tasks,
  occupancyKnown,
  onPress,
}: {
  room: Room;
  booking?: Booking;
  taskCount: number;
  tasks: RoomTask[];
  occupancyKnown: boolean;
  onPress?: () => void;
}) {
  const c = useTheme();
  const effectiveStatus = effectiveRoomStatus(room.status, !!booking);
  const state = roomPresentation(room, !!booking, tasks);
  const accent = state.blockedStatus ? c.danger : roomStatusColor(effectiveStatus, c);
  const occupied = state.occupancy === 'occupied';
  const occupancyLabel = state.occupancy === 'blocked' ? tr.rooms.statusBlocked : occupied ? tr.rooms.statusOccupied
    : occupancyKnown && state.occupancy === 'vacant' ? tr.rooms.vacant : tr.rooms.statusUnknown;
  const cleaning = state.isReady && !occupancyKnown ? 'inspected' : state.cleaning;
  const guest = booking?.guest_name || room.guest_name;
  const balance = booking?.balance;
  const nights = nightsBetween(booking?.check_in, booking?.check_out);

  const content = (
    <Card accent={accent}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md }}>
        {/* Left: identity */}
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
            <Ionicons name="bed-outline" size={18} color={accent} />
            <Text style={{ color: c.text, fontSize: 20, fontWeight: '800', letterSpacing: -0.5 }} numberOfLines={1}>
              {room.room_number}
            </Text>
            {room.floor !== undefined && room.floor !== null && room.floor !== '' ? (
              <Muted style={{ fontSize: 12 }}>
                {tr.rooms.floor} {String(room.floor)}
              </Muted>
            ) : null}
          </View>
          {room.room_type ? (
            <Muted style={{ marginTop: 2 }} numberOfLines={1}>
              {room.room_type}
            </Muted>
          ) : null}
          <Body style={{ color: c.textMuted, fontSize: 13, marginTop: spacing.xs }} numberOfLines={1}>
            {occupied ? guest || tr.rooms.statusOccupied : occupancyLabel}
          </Body>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.sm }}>
            <Badge label={`${tr.rooms.occupancyLabel}: ${occupancyLabel}`} tone={state.occupancy === 'blocked' ? 'danger' : occupied ? 'primary' : 'default'} />
            <Badge label={`${tr.rooms.cleaningLabel}: ${state.blockedStatus ? statusLabel(state.blockedStatus) : CLEANING_LABELS[cleaning]}`} tone={state.blockedStatus ? 'danger' : cleaning === 'ready' ? 'success' : cleaning === 'dirty' || cleaning === 'inspection' ? 'warning' : 'info'} />
            {taskCount > 0 ? (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 4,
                  paddingHorizontal: spacing.sm,
                  paddingVertical: 3,
                  borderRadius: radius.pill,
                  backgroundColor: c.info + '1f',
                }}
              >
                <Ionicons name="construct-outline" size={12} color={c.info} />
                <Text style={{ color: c.info, fontSize: 11, fontWeight: '700' }}>
                  {taskCount} {tr.rooms.tasks}
                </Text>
              </View>
            ) : null}
          </View>
        </View>

        {/* Right: stay & balance (real in-house data) */}
        {occupied && (balance !== undefined || nights !== null) ? (
          <View style={{ alignItems: 'flex-end', gap: spacing.xs, maxWidth: '45%' }}>
            {balance !== undefined ? (
              <>
                <Muted style={{ fontSize: 11 }}>{tr.rooms.balance}</Muted>
                <Text
                  testID={`room-booking-balance-${room.id}`}
                  style={{
                    color: balance > 0 ? c.warning : c.text,
                    fontSize: 16,
                    fontWeight: '800',
                    textAlign: 'right',
                  }}
                  numberOfLines={3}
                >
                  {reservationAmountLabel(balance, reservationCurrency(booking?.currency))}
                </Text>
              </>
            ) : null}
            {nights !== null ? (
              <Badge label={`${nights} ${tr.rooms.nights}`} tone="info" />
            ) : null}
          </View>
        ) : null}
      </View>
      {onPress ? (
        <Button title={booking ? tr.rooms.openStay : tr.rooms.availableToReserve}
          variant="secondary" icon={booking ? 'arrow-forward-outline' : 'add-outline'}
          accessibilityLabel={`${tr.rooms.title} ${room.room_number} · ${booking ? tr.rooms.openStay : tr.rooms.availableToReserve}`}
          onPress={onPress} testID="smoke-room-card" fullWidth style={{ marginTop: spacing.md, minHeight: 48 }} />
      ) : null}
    </Card>
  );

  return content;
}

export default function RoomsScreen() {
  const c = useTheme();
  const router = useRouter();
  const online = useOnline();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [cleaningFilter, setCleaningFilter] = useState('');
  const [floor, setFloor] = useState('');

  const roomsQ = useQuery({ queryKey: ['frontdesk-rooms'], queryFn: listRooms });
  const tasksQ = useQuery({ queryKey: ['frontdesk-room-tasks'], queryFn: listRoomTasks });
  const inhouseQ = useQuery({ queryKey: ['frontdesk-inhouse-rooms'], queryFn: getInHouse });

  const allRooms = asArray<Room>(roomsQ.data);
  const tasks = asArray<RoomTask>(tasksQ.data);
  const inhouse = asArray<Booking>(inhouseQ.data);

  const taskCountByRoom = useMemo(() => {
    const map: Record<string, number> = {};
    for (const t of tasks as RoomTask[]) {
      if (t.room_id) map[t.room_id] = (map[t.room_id] || 0) + 1;
    }
    return map;
  }, [tasks]);

  const tasksByRoom = useMemo(() => {
    const map: Record<string, RoomTask[]> = {};
    for (const task of tasks) if (task.room_id) (map[task.room_id] ||= []).push(task);
    return map;
  }, [tasks]);

  // Join in-house bookings (which carry balance + stay dates) to rooms by
  // room number — the only shared key between the two backend sources.
  const bookingByRoomNo = useMemo(() => indexBookingsByRoomNumber(inhouse), [inhouse]);

  const floorOptions = useMemo<FilterChipOption[]>(() => {
    const floors = Array.from(
      new Set(
        allRooms
          .map((r) => (r.floor === undefined || r.floor === null || r.floor === '' ? null : String(r.floor)))
          .filter((f): f is string => f !== null),
      ),
    ).sort((a, b) => Number(a) - Number(b) || a.localeCompare(b));
    return [
      { value: '', label: tr.rooms.floorAll },
      ...floors.map((f) => ({ value: f, label: `${tr.rooms.floor} ${f}` })),
    ];
  }, [allRooms]);

  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of allRooms) {
      const booking = bookingByRoomNo[roomNumberKey(r.room_number)];
      const presentation = roomPresentation(r, !!booking, tasksByRoom[r.id] || []);
      const cat = presentation.blockedStatus ? 'maintenance' : presentation.occupancy === 'occupied' ? 'occupied' : presentation.occupancy === 'vacant' ? 'available' : 'other';
      m[cat] = (m[cat] || 0) + 1;
      if (presentation.cleaning === 'dirty') m.dirty = (m.dirty || 0) + 1;
      if (presentation.cleaning === 'cleaning') m.cleaning = (m.cleaning || 0) + 1;
    }
    return m;
  }, [allRooms, bookingByRoomNo, tasksByRoom]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRooms.filter((r) => {
      const b = bookingByRoomNo[roomNumberKey(r.room_number)];
      const presentation = roomPresentation(r, !!b, tasksByRoom[r.id] || []);
      if (status && presentation.occupancy !== status) return false;
      if (cleaningFilter && presentation.cleaning !== cleaningFilter) return false;
      if (cleaningFilter === 'ready' && (!inhouseQ.isSuccess || !tasksQ.isSuccess)) return false;
      if (floor && String(r.floor ?? '') !== floor) return false;
      if (q) {
        const hay = `${r.room_number || ''} ${r.guest_name || ''} ${b?.guest_name || ''} ${r.room_type || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [allRooms, search, status, cleaningFilter, floor, bookingByRoomNo, tasksByRoom, inhouseQ.isSuccess, tasksQ.isSuccess]);

  const refreshing = roomsQ.isFetching && !roomsQ.isLoading;
  const offline = !online || roomsQ.fetchStatus === 'paused' || (roomsQ.isError && isOffline(roomsQ.error));
  const hasFilters = !!(search || status || cleaningFilter || floor);

  const onRefresh = () => {
    roomsQ.refetch();
    tasksQ.refetch();
    inhouseQ.refetch();
  };

  const clearFilters = () => {
    setSearch('');
    setStatus('');
    setCleaningFilter('');
    setFloor('');
  };

  // Occupied rooms carry an in-house booking (joined by room number); tapping
  // the card opens the reservation detail prefilled from the booking so it
  // renders instantly while the enhanced data loads by id.
  const openBooking = (b: Booking) => {
    router.push({
      pathname: ROUTES.reservationDetail,
      params: {
        id: b.id,
        guest_name: b.guest_name || '',
        room_number: b.room_number || '',
        room_type: b.room_type || '',
        check_in: b.check_in || '',
        check_out: b.check_out || '',
        status: b.status || '',
        total_amount: b.total_amount != null ? String(b.total_amount) : '',
        paid_amount: b.paid_amount != null ? String(b.paid_amount) : '',
        balance: b.balance != null ? String(b.balance) : '',
      },
    });
  };

  const openNewReservation = (room: Room) => {
    router.push({
      pathname: ROUTES.newReservation,
      params: {
        room_id: room.id,
        room_number: room.room_number || '',
        room_type: room.room_type || '',
      },
    });
  };

  const summaryPills: { cat: string; label: string; tone: StatusTone }[] = [
    { cat: 'available', label: tr.rooms.vacant, tone: 'default' },
    { cat: 'occupied', label: tr.rooms.statusOccupied, tone: 'primary' },
    { cat: 'dirty', label: tr.rooms.statusDirty, tone: 'warning' },
    { cat: 'cleaning', label: tr.rooms.statusCleaning, tone: 'info' },
    { cat: 'maintenance', label: tr.rooms.statusMaintenance, tone: 'danger' },
  ];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <View style={[{ flex: 1, padding: spacing.lg }, webCenter]}>
      <H1>{tr.rooms.title}</H1>
      <Muted style={{ marginTop: spacing.xs }}>{tr.rooms.subtitle}</Muted>
      <View style={{ height: spacing.sm }} />

      {allRooms.length > 0 ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
          {summaryPills
            .filter((p) => (counts[p.cat] || 0) > 0 && (p.cat !== 'available' || inhouseQ.isSuccess))
            .map((p) => (
              <KpiPill key={p.cat} label={`${p.label} ${counts[p.cat] || 0}`} tone={p.tone === 'primary' ? 'default' : p.tone} />
            ))}
        </View>
      ) : null}

      <Field
        placeholder={tr.rooms.search}
        value={search}
        onChangeText={setSearch}
        autoCapitalize="none"
        testID="smoke-rooms-search"
      />
      <View style={{ height: spacing.sm }} />
      <Muted style={{ marginBottom: spacing.xs }}>{tr.rooms.occupancyLabel}</Muted>
      <FilterChips options={STATUS_FILTERS} value={status} onChange={setStatus} />
      <Muted style={{ marginTop: spacing.sm, marginBottom: spacing.xs }}>{tr.rooms.cleaningLabel}</Muted>
      <FilterChips options={CLEANING_FILTERS} value={cleaningFilter} onChange={setCleaningFilter} />
      {floorOptions.length > 1 ? (
        <View style={{ marginTop: spacing.xs }}>
          <FilterChips options={floorOptions} value={floor} onChange={setFloor} />
        </View>
      ) : null}
      {hasFilters ? (
        <Pressable onPress={clearFilters} accessibilityRole="button" accessibilityLabel={tr.rooms.clearFilters} style={{ paddingVertical: spacing.sm, minHeight: 48, justifyContent: 'center' }}>
          <Muted style={{ color: c.primary }}>{tr.rooms.clearFilters}</Muted>
        </Pressable>
      ) : (
        <View style={{ height: spacing.sm }} />
      )}

      <OfflineBanner visible={offline} />

      {inhouseQ.isError || tasksQ.isError ? (
        <Card accent={c.warning} style={{ marginBottom: spacing.sm }}>
          <Muted>{inhouseQ.isError ? tr.rooms.inhouseLoadError : tr.rooms.tasksLoadError}</Muted>
          <Button title={tr.app.retry} variant="ghost" onPress={onRefresh} />
        </Card>
      ) : null}

      {offline && !roomsQ.data ? (
        <Card accent={c.warning}>
          <Muted>{tr.app.offline}</Muted>
          <Button title={tr.app.retry} icon="refresh" variant="outline" onPress={onRefresh} fullWidth />
        </Card>
      ) : roomsQ.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : roomsQ.isError && !offline ? (
        <Card accent={c.danger}>
          <Muted>{errorMessage(roomsQ.error, tr.rooms.loadError)}</Muted>
          <View style={{ height: spacing.sm }} />
          <Button
            title={tr.app.retry}
            icon="refresh"
            variant="outline"
            onPress={() => roomsQ.refetch()}
            fullWidth
          />
        </Card>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(r) => r.id}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
          contentContainerStyle={{ paddingBottom: spacing.xxl }}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
          }
          ListEmptyComponent={
            <EmptyState
              icon="bed-outline"
              title={allRooms.length === 0 ? tr.rooms.noRooms : tr.rooms.noResults}
            />
          }
          renderItem={({ item }) => {
            const booking = bookingByRoomNo[roomNumberKey(item.room_number)];
            const state = roomPresentation(item, !!booking, tasksByRoom[item.id] || []);
            return (
              <RoomCard
                room={item}
                booking={booking}
                taskCount={taskCountByRoom[item.id] || 0}
                tasks={tasksByRoom[item.id] || []}
                occupancyKnown={inhouseQ.isSuccess && tasksQ.isSuccess}
                onPress={booking?.id ? () => openBooking(booking) : inhouseQ.isSuccess && state.occupancy === 'vacant' ? () => openNewReservation(item) : undefined}
              />
            );
          }}
        />
      )}
      </View>
    </View>
  );
}
