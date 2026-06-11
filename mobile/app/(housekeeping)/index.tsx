import React, { useMemo, useState } from 'react';
import {
  Alert,
  AlertButton,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
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
import { spacing, radius, useTheme, roomStatusColor } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  createQuickTask,
  HkStaff,
  listHousekeepingStaff,
  listRoomTasks,
  listRooms,
  Room,
  RoomTask,
  updateRoomStatus,
} from '../../src/api/rooms';
import { haptic } from '../../src/hooks/useHaptic';
import { isOffline } from '../../src/utils/errors';

// Valid backend room statuses (housekeeping room/status endpoint):
// available, occupied, dirty, cleaning, inspected, maintenance, out_of_order.
// We expose the ones a housekeeper flips by hand.
const STATUS_OPTIONS = [
  'available',
  'dirty',
  'cleaning',
  'inspected',
  'maintenance',
  'out_of_order',
] as const;
type StatusOption = (typeof STATUS_OPTIONS)[number];

const TASK_TYPES = ['cleaning', 'inspection', 'maintenance'] as const;
type TaskType = (typeof TASK_TYPES)[number];
const PRIORITIES = ['normal', 'high', 'urgent'] as const;
type Priority = (typeof PRIORITIES)[number];

type BadgeTone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'primary';

function roomStatusTone(status: string | undefined): BadgeTone {
  switch ((status || '').toLowerCase()) {
    case 'clean':
    case 'available':
    case 'inspected':
      return 'success';
    case 'dirty':
      return 'warning';
    case 'cleaning':
    case 'inspection':
      return 'info';
    case 'out_of_order':
    case 'maintenance':
      return 'danger';
    case 'occupied':
      return 'primary';
    default:
      return 'default';
  }
}

export default function RoomsScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const [floor, setFloor] = useState<string>('all');
  const rooms = useQuery({ queryKey: ['rooms'], queryFn: listRooms });
  const roomTasks = useQuery({ queryKey: ['room-tasks'], queryFn: listRoomTasks });

  // Open tasks grouped by room_id → powers the per-card badge + detail sheet.
  const tasksByRoom = useMemo(() => {
    const map = new Map<string, RoomTask[]>();
    (roomTasks.data || []).forEach((t) => {
      if (!t.room_id) return;
      const list = map.get(t.room_id);
      if (list) list.push(t);
      else map.set(t.room_id, [t]);
    });
    return map;
  }, [roomTasks.data]);

  // ── Open-tasks viewer sheet state ────────────────────────────────────────
  const [tasksRoom, setTasksRoom] = useState<Room | null>(null);

  // ── Task assignment sheet state ──────────────────────────────────────────
  const [assignRoom, setAssignRoom] = useState<Room | null>(null);
  const [staffSel, setStaffSel] = useState<HkStaff | null>(null);
  const [taskType, setTaskType] = useState<TaskType>('cleaning');
  const [priority, setPriority] = useState<Priority>('normal');
  const [submitting, setSubmitting] = useState(false);
  const staff = useQuery({
    queryKey: ['hk-staff'],
    queryFn: listHousekeepingStaff,
    enabled: assignRoom !== null,
  });

  const openAssign = (r: Room) => {
    setAssignRoom(r);
    setStaffSel(null);
    setTaskType('cleaning');
    setPriority('normal');
  };
  const closeAssign = () => {
    if (submitting) return;
    setAssignRoom(null);
  };

  const submitAssign = async () => {
    if (!assignRoom) return;
    if (!staffSel) {
      Alert.alert(tr.app.error, tr.housekeeping.assignNeedStaff);
      return;
    }
    setSubmitting(true);
    try {
      await createQuickTask({
        room_id: assignRoom.id,
        task_type: taskType,
        priority,
        assigned_to: staffSel.name,
      });
      haptic.success();
      setAssignRoom(null);
      // Refresh rooms (cleaning assignment may flip room → cleaning) + the
      // shared "Görevlerim" hub feed so the new task appears immediately.
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['my-tasks'] });
      qc.invalidateQueries({ queryKey: ['room-tasks'] });
      Alert.alert(tr.app.success, tr.housekeeping.assignSuccess);
    } catch {
      haptic.error();
      Alert.alert(tr.app.error, tr.errors.generic);
    } finally {
      setSubmitting(false);
    }
  };

  const taskTypeLabel = (t: TaskType): string =>
    t === 'cleaning'
      ? tr.housekeeping.taskCleaning
      : t === 'inspection'
        ? tr.housekeeping.taskInspection
        : tr.housekeeping.taskMaintenance;
  const priorityLabel = (p: Priority): string =>
    p === 'normal'
      ? tr.housekeeping.priorityNormal
      : p === 'high'
        ? tr.housekeeping.priorityHigh
        : tr.housekeeping.priorityUrgent;

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

  const promptStatus = (r: Room) => {
    const buttons: AlertButton[] = STATUS_OPTIONS.map((s) => ({
      text: tr.housekeeping.statuses[s] || s,
      onPress: () => {
        void applyStatus(r, s);
      },
    }));
    buttons.push({ text: tr.app.cancel, style: 'cancel' });
    Alert.alert(`Oda ${r.room_number}`, tr.housekeeping.changeStatus, buttons);
  };

  const onLongPress = (r: Room) => {
    haptic.tap();
    Alert.alert(`Oda ${r.room_number}`, tr.housekeeping.longPressHint, [
      { text: tr.housekeeping.changeStatus, onPress: () => promptStatus(r) },
      { text: tr.housekeeping.assignTask, onPress: () => openAssign(r) },
      { text: tr.app.cancel, style: 'cancel' },
    ]);
  };

  const openTasks = (r: Room) => {
    haptic.tap();
    setTasksRoom(r);
  };

  const taskTypeText = (t?: string): string => {
    switch ((t || '').toLowerCase()) {
      case 'cleaning':
        return tr.housekeeping.taskCleaning;
      case 'inspection':
        return tr.housekeeping.taskInspection;
      case 'maintenance':
        return tr.housekeeping.taskMaintenance;
      default:
        return t || tr.housekeeping.taskCleaning;
    }
  };
  const priorityText = (p?: string): string => {
    switch ((p || '').toLowerCase()) {
      case 'high':
        return tr.housekeeping.priorityHigh;
      case 'urgent':
        return tr.housekeeping.priorityUrgent;
      default:
        return tr.housekeeping.priorityNormal;
    }
  };
  const priorityTone = (p?: string): BadgeTone => {
    switch ((p || '').toLowerCase()) {
      case 'urgent':
        return 'danger';
      case 'high':
        return 'warning';
      default:
        return 'default';
    }
  };

  const tasksRoomList: RoomTask[] = tasksRoom
    ? tasksByRoom.get(tasksRoom.id) || []
    : [];

  const renderRoom = ({ item: r }: { item: Room }) => {
    const color = roomStatusColor(r.status, c);
    const key = (r.status || '').toLowerCase() as keyof typeof tr.housekeeping.statuses;
    const label = tr.housekeeping.statuses[key] || r.status || '—';
    const openCount = (tasksByRoom.get(r.id) || []).length;
    return (
      <Pressable
        onPress={() => openTasks(r)}
        onLongPress={() => onLongPress(r)}
        delayLongPress={350}
        accessibilityLabel={
          `Oda ${r.room_number}, durum ${label}` +
          (openCount ? `, ${openCount} ${tr.housekeeping.openTasks}` : '')
        }
        accessibilityHint={tr.housekeeping.viewTasks}
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
            <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
              <Badge label={label} tone={roomStatusTone(r.status)} />
              {openCount > 0 ? (
                <Badge label={`${openCount} ${tr.housekeeping.openTasks}`} tone="info" />
              ) : null}
            </View>
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
          style={{ flexShrink: 0 }}
        />
        {floors.map((f) => (
          <Button
            key={f}
            title={`${tr.housekeeping.floor} ${f}`}
            variant={floor === f ? 'primary' : 'secondary'}
            onPress={() => setFloor(f)}
            style={{ flexShrink: 0 }}
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
              refreshing={
                (rooms.isFetching && !rooms.isLoading) ||
                (roomTasks.isFetching && !roomTasks.isLoading)
              }
              onRefresh={() => {
                rooms.refetch();
                roomTasks.refetch();
              }}
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

      <Modal
        visible={tasksRoom !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setTasksRoom(null)}
      >
        <Pressable
          onPress={() => setTasksRoom(null)}
          style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}
        >
          <Pressable
            onPress={() => {}}
            style={{
              backgroundColor: c.bg,
              borderTopLeftRadius: radius.lg,
              borderTopRightRadius: radius.lg,
              padding: spacing.lg,
              maxHeight: '85%',
            }}
          >
            <H2>
              {tr.housekeeping.openTasksTitle}
              {tasksRoom ? ` · Oda ${tasksRoom.room_number}` : ''}
            </H2>

            <ScrollView style={{ marginTop: spacing.md }}>
              {tasksRoomList.length === 0 ? (
                <Card>
                  <Muted>{tr.housekeeping.noOpenTasks}</Muted>
                </Card>
              ) : (
                <View style={{ gap: spacing.sm }}>
                  {tasksRoomList.map((t) => (
                    <Card key={t.id}>
                      <View
                        style={{
                          flexDirection: 'row',
                          justifyContent: 'space-between',
                          gap: spacing.sm,
                        }}
                      >
                        <Text style={{ color: c.text, fontWeight: '600', flex: 1 }}>
                          {taskTypeText(t.task_type)}
                        </Text>
                        <Badge label={priorityText(t.priority)} tone={priorityTone(t.priority)} />
                      </View>
                      <Muted style={{ marginTop: spacing.xs }}>
                        {t.assigned_to || tr.housekeeping.unassigned}
                      </Muted>
                      {t.notes ? (
                        <Muted style={{ marginTop: spacing.xs }} numberOfLines={3}>
                          {t.notes}
                        </Muted>
                      ) : null}
                    </Card>
                  ))}
                </View>
              )}
            </ScrollView>

            <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg }}>
              <Button
                title={tr.housekeeping.assignTask}
                variant="secondary"
                onPress={() => {
                  const r = tasksRoom;
                  setTasksRoom(null);
                  if (r) openAssign(r);
                }}
                style={{ flex: 1 }}
              />
              <Button
                title={tr.app.close}
                variant="primary"
                onPress={() => setTasksRoom(null)}
                style={{ flex: 1 }}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal
        visible={assignRoom !== null}
        transparent
        animationType="slide"
        onRequestClose={closeAssign}
      >
        <Pressable
          onPress={closeAssign}
          style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}
        >
          <Pressable
            onPress={() => {}}
            style={{
              backgroundColor: c.bg,
              borderTopLeftRadius: radius.lg,
              borderTopRightRadius: radius.lg,
              padding: spacing.lg,
              maxHeight: '85%',
            }}
          >
            <H2>
              {tr.housekeeping.assignTitle}
              {assignRoom ? ` · Oda ${assignRoom.room_number}` : ''}
            </H2>

            <ScrollView style={{ marginTop: spacing.md }}>
              <Muted>{tr.housekeeping.selectStaff}</Muted>
              {staff.isLoading ? (
                <SkeletonCard />
              ) : (staff.data || []).length === 0 ? (
                <Card>
                  <Muted>{tr.housekeeping.noStaff}</Muted>
                </Card>
              ) : (
                <View style={{ gap: spacing.xs, marginTop: spacing.xs }}>
                  {(staff.data || []).map((s, idx) => {
                    const keyVal = s.id || s.name;
                    const sel = (staffSel?.id || staffSel?.name) === keyVal;
                    return (
                      <Pressable
                        key={`${keyVal}-${idx}`}
                        onPress={() => setStaffSel(s)}
                        style={{
                          borderWidth: 1,
                          borderColor: sel ? c.primary : c.border,
                          backgroundColor: sel ? c.primary : c.surface,
                          borderRadius: radius.md,
                          paddingVertical: spacing.sm,
                          paddingHorizontal: spacing.md,
                        }}
                      >
                        <Text style={{ color: sel ? c.primaryText : c.text, fontWeight: '600' }}>
                          {s.name}
                        </Text>
                        {s.role ? (
                          <Text style={{ color: sel ? c.primaryText : c.textMuted, fontSize: 12 }}>
                            {s.role}
                          </Text>
                        ) : null}
                      </Pressable>
                    );
                  })}
                </View>
              )}

              <Muted style={{ marginTop: spacing.md }}>{tr.housekeeping.taskType}</Muted>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs }}>
                {TASK_TYPES.map((t) => (
                  <Button
                    key={t}
                    title={taskTypeLabel(t)}
                    variant={taskType === t ? 'primary' : 'secondary'}
                    onPress={() => setTaskType(t)}
                    style={{ flexShrink: 0 }}
                  />
                ))}
              </View>

              <Muted style={{ marginTop: spacing.md }}>{tr.housekeeping.priority}</Muted>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs }}>
                {PRIORITIES.map((p) => (
                  <Button
                    key={p}
                    title={priorityLabel(p)}
                    variant={priority === p ? 'primary' : 'secondary'}
                    onPress={() => setPriority(p)}
                    style={{ flexShrink: 0 }}
                  />
                ))}
              </View>
            </ScrollView>

            <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg }}>
              <Button
                title={tr.app.cancel}
                variant="secondary"
                onPress={closeAssign}
                style={{ flex: 1 }}
              />
              <Button
                title={tr.housekeeping.assignSubmit}
                variant="primary"
                onPress={() => void submitAssign()}
                disabled={submitting || !staffSel}
                style={{ flex: 1 }}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}
