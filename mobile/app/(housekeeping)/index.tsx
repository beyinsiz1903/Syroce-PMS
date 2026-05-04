import React, { useMemo, useState } from 'react';
import {
  Alert,
  AlertButton,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  View,
} from 'react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Badge,
  Button,
  Card,
  H1,
  H2,
  Muted,
  SkeletonCard,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme, roomStatusColor } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { listRooms, Room, updateRoomStatus } from '../../src/api/rooms';
import { haptic } from '../../src/hooks/useHaptic';
import { isOffline } from '../../src/utils/errors';

const STATUS_OPTIONS = ['clean', 'dirty', 'inspection', 'out_of_order'] as const;
type StatusOption = (typeof STATUS_OPTIONS)[number];

export default function RoomsScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const [floor, setFloor] = useState<string>('all');
  const rooms = useQuery({ queryKey: ['rooms'], queryFn: listRooms });

  const floors = useMemo(() => {
    const set = new Set<string>();
    (rooms.data || []).forEach((r) => {
      if (r.floor !== undefined && r.floor !== null) set.add(String(r.floor));
    });
    return Array.from(set).sort();
  }, [rooms.data]);

  const filtered = useMemo(() => {
    const list = rooms.data || [];
    if (floor === 'all') return list;
    return list.filter((r) => String(r.floor) === floor);
  }, [rooms.data, floor]);

  const offline = rooms.isError && isOffline(rooms.error);

  const applyStatus = async (r: Room, s: StatusOption) => {
    const prev = qc.getQueryData<Room[]>(['rooms']) || [];
    qc.setQueryData<Room[]>(['rooms'], (data) =>
      (data || []).map((x) => (x.id === r.id ? { ...x, status: s } : x)),
    );
    try {
      await updateRoomStatus(r.id, s);
      haptic.success();
      Alert.alert(tr.app.success, tr.housekeeping.statusUpdated);
    } catch {
      qc.setQueryData<Room[]>(['rooms'], prev);
      haptic.error();
      Alert.alert(tr.app.error, tr.errors.generic);
    }
  };

  const onLongPress = (r: Room) => {
    haptic.tap();
    const buttons: AlertButton[] = STATUS_OPTIONS.map((s) => ({
      text: tr.housekeeping.statuses[s] || s,
      onPress: () => {
        void applyStatus(r, s);
      },
    }));
    buttons.push({ text: tr.app.cancel, style: 'cancel' });
    Alert.alert(`Oda ${r.room_number}`, tr.housekeeping.longPressHint, buttons);
  };

  const renderRoom = ({ item: r }: { item: Room }) => {
    const color = roomStatusColor(r.status, c);
    const key = (r.status || '').toLowerCase() as keyof typeof tr.housekeeping.statuses;
    const label = tr.housekeeping.statuses[key] || r.status || '—';
    return (
      <Pressable
        onLongPress={() => onLongPress(r)}
        delayLongPress={350}
        accessibilityLabel={`Oda ${r.room_number}, durum ${label}`}
        accessibilityHint={tr.housekeeping.longPressHint}
        style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1, marginBottom: spacing.sm })}
      >
        <Card style={{ borderLeftWidth: 4, borderLeftColor: color }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <View>
              <H2>Oda {r.room_number}</H2>
              <Muted>
                {r.room_type || '—'} · Kat {r.floor ?? '—'}
              </Muted>
            </View>
            <Badge label={label} tone="info" />
          </View>
        </Card>
      </Pressable>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }}>
      <H1>{tr.housekeeping.title}</H1>
      <Muted>{tr.housekeeping.longPressHint}</Muted>
      <View style={{ height: spacing.md }} />
      <OfflineBanner visible={!!offline} />

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, paddingBottom: spacing.sm }}
      >
        <Button
          title={tr.housekeeping.all}
          variant={floor === 'all' ? 'primary' : 'secondary'}
          onPress={() => setFloor('all')}
        />
        {floors.map((f) => (
          <Button
            key={f}
            title={`${tr.housekeeping.floor} ${f}`}
            variant={floor === f ? 'primary' : 'secondary'}
            onPress={() => setFloor(f)}
          />
        ))}
      </ScrollView>

      {rooms.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(r) => r.id}
          renderItem={renderRoom}
          refreshControl={
            <RefreshControl
              refreshing={rooms.isFetching && !rooms.isLoading}
              onRefresh={() => rooms.refetch()}
              tintColor={c.primary}
            />
          }
          ListEmptyComponent={
            <Card>
              <Muted>{tr.app.empty}</Muted>
            </Card>
          }
        />
      )}
    </View>
  );
}
