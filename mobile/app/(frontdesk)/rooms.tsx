import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, EmptyState, Field, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiPill } from '../../src/components/KpiCard';
import { FilterChips, FilterChipOption } from '../../src/components/FilterChips';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, roomStatusColor, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { listRooms, listRoomTasks, Room, RoomTask } from '../../src/api/rooms';
import { Booking, getInHouse } from '../../src/api/bookings';
import { formatCurrency } from '../../src/utils/format';
import { errorMessage, isOffline } from '../../src/utils/errors';

type StatusTone = 'success' | 'primary' | 'warning' | 'info' | 'danger' | 'default';

const CATEGORY: Record<string, string[]> = {
  available: ['available', 'clean', 'inspected'],
  occupied: ['occupied'],
  dirty: ['dirty'],
  cleaning: ['cleaning', 'inspection'],
  maintenance: ['maintenance', 'out_of_order'],
};

function statusCategory(status?: string): string {
  const s = (status || '').toLowerCase();
  for (const [cat, list] of Object.entries(CATEGORY)) {
    if (list.includes(s)) return cat;
  }
  return 'other';
}

function statusTone(status?: string): StatusTone {
  switch (statusCategory(status)) {
    case 'available':
      return 'success';
    case 'occupied':
      return 'primary';
    case 'dirty':
      return 'warning';
    case 'cleaning':
      return 'info';
    case 'maintenance':
      return 'danger';
    default:
      return 'default';
  }
}

function statusLabel(status?: string): string {
  switch ((status || '').toLowerCase()) {
    case 'available':
    case 'clean':
      return tr.rooms.statusAvailable;
    case 'inspected':
      return tr.rooms.statusInspected;
    case 'occupied':
      return tr.rooms.statusOccupied;
    case 'dirty':
      return tr.rooms.statusDirty;
    case 'cleaning':
    case 'inspection':
      return tr.rooms.statusCleaning;
    case 'maintenance':
      return tr.rooms.statusMaintenance;
    case 'out_of_order':
      return tr.rooms.statusOutOfOrder;
    default:
      return status || '—';
  }
}

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
  { value: 'available', label: tr.rooms.statusAvailable },
  { value: 'occupied', label: tr.rooms.statusOccupied },
  { value: 'dirty', label: tr.rooms.statusDirty },
  { value: 'cleaning', label: tr.rooms.statusCleaning },
  { value: 'maintenance', label: tr.rooms.statusMaintenance },
];

function RoomCard({
  room,
  booking,
  taskCount,
}: {
  room: Room;
  booking?: Booking;
  taskCount: number;
}) {
  const c = useTheme();
  const accent = roomStatusColor(room.status, c);
  const occupied = statusCategory(room.status) === 'occupied';
  const guest = booking?.guest_name || room.guest_name;
  const balance = booking?.balance;
  const nights = nightsBetween(booking?.check_in, booking?.check_out);

  return (
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
            {occupied ? guest || '—' : tr.rooms.vacant}
          </Body>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.sm }}>
            <Badge label={statusLabel(room.status)} tone={statusTone(room.status)} />
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
          <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
            {balance !== undefined ? (
              <>
                <Muted style={{ fontSize: 11 }}>{tr.rooms.balance}</Muted>
                <Text
                  style={{
                    color: balance > 0 ? c.warning : c.text,
                    fontSize: 16,
                    fontWeight: '800',
                  }}
                  numberOfLines={1}
                >
                  {formatCurrency(balance)}
                </Text>
              </>
            ) : null}
            {nights !== null ? (
              <Badge label={`${nights} ${tr.rooms.nights}`} tone="info" />
            ) : null}
          </View>
        ) : null}
      </View>
    </Card>
  );
}

export default function RoomsScreen() {
  const c = useTheme();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [floor, setFloor] = useState('');

  const roomsQ = useQuery({ queryKey: ['frontdesk-rooms'], queryFn: listRooms });
  const tasksQ = useQuery({ queryKey: ['frontdesk-room-tasks'], queryFn: listRoomTasks });
  const inhouseQ = useQuery({ queryKey: ['frontdesk-inhouse-rooms'], queryFn: getInHouse });

  const allRooms = roomsQ.data || [];
  const tasks = tasksQ.data || [];
  const inhouse = inhouseQ.data || [];

  const taskCountByRoom = useMemo(() => {
    const map: Record<string, number> = {};
    for (const t of tasks as RoomTask[]) {
      if (t.room_id) map[t.room_id] = (map[t.room_id] || 0) + 1;
    }
    return map;
  }, [tasks]);

  // Join in-house bookings (which carry balance + stay dates) to rooms by
  // room number — the only shared key between the two backend sources.
  const bookingByRoomNo = useMemo(() => {
    const map: Record<string, Booking> = {};
    for (const b of inhouse) {
      const key = String(b.room_number ?? '').trim();
      if (key) map[key] = b;
    }
    return map;
  }, [inhouse]);

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
      const cat = statusCategory(r.status);
      m[cat] = (m[cat] || 0) + 1;
    }
    return m;
  }, [allRooms]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRooms.filter((r) => {
      if (status && statusCategory(r.status) !== status) return false;
      if (floor && String(r.floor ?? '') !== floor) return false;
      if (q) {
        const b = bookingByRoomNo[String(r.room_number ?? '').trim()];
        const hay = `${r.room_number || ''} ${r.guest_name || ''} ${b?.guest_name || ''} ${r.room_type || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [allRooms, search, status, floor, bookingByRoomNo]);

  const refreshing = roomsQ.isFetching && !roomsQ.isLoading;
  const offline = roomsQ.isError && isOffline(roomsQ.error);
  const hasFilters = !!(search || status || floor);

  const onRefresh = () => {
    roomsQ.refetch();
    tasksQ.refetch();
    inhouseQ.refetch();
  };

  const clearFilters = () => {
    setSearch('');
    setStatus('');
    setFloor('');
  };

  const summaryPills: { cat: string; label: string; tone: StatusTone }[] = [
    { cat: 'available', label: tr.rooms.statusAvailable, tone: 'success' },
    { cat: 'occupied', label: tr.rooms.statusOccupied, tone: 'primary' },
    { cat: 'dirty', label: tr.rooms.statusDirty, tone: 'warning' },
    { cat: 'cleaning', label: tr.rooms.statusCleaning, tone: 'info' },
    { cat: 'maintenance', label: tr.rooms.statusMaintenance, tone: 'danger' },
  ];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }}>
      <H1>{tr.rooms.title}</H1>
      <View style={{ height: spacing.sm }} />

      {allRooms.length > 0 ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginBottom: spacing.sm }}>
          {summaryPills
            .filter((p) => (counts[p.cat] || 0) > 0)
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
      <FilterChips options={STATUS_FILTERS} value={status} onChange={setStatus} />
      {floorOptions.length > 1 ? (
        <View style={{ marginTop: spacing.xs }}>
          <FilterChips options={floorOptions} value={floor} onChange={setFloor} />
        </View>
      ) : null}
      {hasFilters ? (
        <Pressable onPress={clearFilters} style={{ paddingVertical: spacing.sm }}>
          <Muted style={{ color: c.primary }}>{tr.rooms.clearFilters}</Muted>
        </Pressable>
      ) : (
        <View style={{ height: spacing.sm }} />
      )}

      <OfflineBanner visible={offline} />

      {roomsQ.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : roomsQ.isError && !offline ? (
        <Card>
          <Muted>{errorMessage(roomsQ.error, tr.rooms.loadError)}</Muted>
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
          renderItem={({ item }) => (
            <RoomCard
              room={item}
              booking={bookingByRoomNo[String(item.room_number ?? '').trim()]}
              taskCount={taskCountByRoom[item.id] || 0}
            />
          )}
        />
      )}
    </View>
  );
}
