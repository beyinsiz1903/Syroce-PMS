import React, { useMemo, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Body, Card, Field, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { FilterChips } from '../../src/components/FilterChips';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { CellStatus, getAvailabilityGrid } from '../../src/api/availability';
import { errorMessage, isOffline } from '../../src/utils/errors';

const DAY_OPTIONS = [
  { value: '7', label: `7 ${tr.availability.days}` },
  { value: '14', label: `14 ${tr.availability.days}` },
  { value: '30', label: `30 ${tr.availability.days}` },
];

const ROOM_COL_WIDTH = 92;
const CELL_WIDTH = 40;
const CELL_HEIGHT = 32;

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function toISODate(input: string): string | undefined {
  const v = input.trim();
  if (!v) return undefined;
  const dm = v.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (dm) {
    const [, d, m, y] = dm;
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  return undefined;
}

function dayHeaderLabel(iso: string): { dow: string; dom: string } {
  const d = new Date(`${iso}T00:00:00`);
  return {
    dow: d.toLocaleDateString('tr-TR', { weekday: 'short' }),
    dom: d.toLocaleDateString('tr-TR', { day: '2-digit' }),
  };
}

function useCellColors() {
  const c = useTheme();
  return (status: CellStatus): string => {
    switch (status) {
      case 'free':
        return c.success;
      case 'occupied':
        return c.primary;
      case 'blocked':
        return c.danger;
      default:
        return c.surfaceAlt;
    }
  };
}

function Legend() {
  const colorFor = useCellColors();
  const items: { status: CellStatus; label: string }[] = [
    { status: 'free', label: tr.availability.free },
    { status: 'occupied', label: tr.availability.occupied },
    { status: 'blocked', label: tr.availability.blocked },
  ];
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md }}>
      {items.map((it) => (
        <View key={it.status} style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs }}>
          <View
            style={{
              width: 14,
              height: 14,
              borderRadius: radius.sm,
              backgroundColor: colorFor(it.status),
            }}
          />
          <Muted>{it.label}</Muted>
        </View>
      ))}
    </View>
  );
}

export default function AvailabilityScreen() {
  const c = useTheme();
  const colorFor = useCellColors();

  const [startInput, setStartInput] = useState('');
  const [days, setDays] = useState('7');

  const startDate = toISODate(startInput) || todayISO();
  const dayCount = Number(days) || 7;

  const q = useQuery({
    queryKey: ['availability-grid', startDate, dayCount],
    queryFn: () => getAvailabilityGrid(startDate, dayCount),
    staleTime: 30_000,
  });

  const grid = q.data;
  const offline = q.isError && isOffline(q.error);

  const dayHeaders = useMemo(() => (grid?.days || []).map(dayHeaderLabel), [grid?.days]);

  return (
    <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }}>
      <H1>{tr.availability.title}</H1>
      <View style={{ height: spacing.sm }} />
      <Field
        placeholder={tr.availability.startDate}
        value={startInput}
        onChangeText={setStartInput}
        autoCapitalize="none"
        keyboardType="numbers-and-punctuation"
        testID="smoke-availability-start"
      />
      <View style={{ height: spacing.sm }} />
      <FilterChips options={DAY_OPTIONS} value={days} onChange={setDays} />
      <View style={{ height: spacing.sm }} />
      <Legend />
      <View style={{ height: spacing.md }} />

      <OfflineBanner visible={offline} />

      {q.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : q.isError && !offline ? (
        <Card>
          <Muted>{errorMessage(q.error, tr.availability.loadError)}</Muted>
        </Card>
      ) : !grid || grid.rooms.length === 0 ? (
        <Card>
          <Muted>{tr.availability.noRooms}</Muted>
        </Card>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator>
          <View>
            {/* Header row */}
            <View style={{ flexDirection: 'row' }}>
              <View
                style={{
                  width: ROOM_COL_WIDTH,
                  height: CELL_HEIGHT + 8,
                  justifyContent: 'center',
                  paddingLeft: spacing.xs,
                }}
              >
                <Muted style={{ fontWeight: '600' }}>{tr.availability.room}</Muted>
              </View>
              {dayHeaders.map((h, i) => (
                <View
                  key={grid.days[i]}
                  style={{
                    width: CELL_WIDTH,
                    height: CELL_HEIGHT + 8,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Muted style={{ fontSize: 10 }}>{h.dow}</Muted>
                  <Body style={{ fontSize: 12, fontWeight: '600' }}>{h.dom}</Body>
                </View>
              ))}
            </View>

            {/* Body rows */}
            <ScrollView style={{ maxHeight: 9999 }} contentContainerStyle={{ paddingBottom: spacing.xxl }}>
              {grid.rooms.map((room) => (
                <View key={room.id} style={{ flexDirection: 'row', marginBottom: 4 }}>
                  <View
                    style={{
                      width: ROOM_COL_WIDTH,
                      height: CELL_HEIGHT,
                      justifyContent: 'center',
                      paddingLeft: spacing.xs,
                    }}
                  >
                    <Body style={{ fontSize: 13, fontWeight: '600' }}>{room.room_number}</Body>
                    {room.room_type ? (
                      <Muted style={{ fontSize: 10 }} numberOfLines={1}>
                        {room.room_type}
                      </Muted>
                    ) : null}
                  </View>
                  {grid.days.map((day) => {
                    const status = room.cells[day] || 'free';
                    return (
                      <View
                        key={day}
                        style={{ width: CELL_WIDTH, height: CELL_HEIGHT, padding: 2 }}
                      >
                        <View
                          accessibilityLabel={`${room.room_number} ${day} ${tr.availability[status]}`}
                          style={{
                            flex: 1,
                            borderRadius: radius.sm,
                            backgroundColor: colorFor(status) + '33',
                            borderWidth: 1,
                            borderColor: colorFor(status),
                          }}
                        />
                      </View>
                    );
                  })}
                </View>
              ))}
            </ScrollView>
          </View>
        </ScrollView>
      )}
    </View>
  );
}
