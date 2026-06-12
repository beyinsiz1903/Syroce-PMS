import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionButton,
  ActionSheet,
  Badge,
  Button,
  Card,
  EmptyState,
  H1,
  H2,
  Muted,
  SegmentedActions,
  SkeletonCard,
} from '../../src/components/ui';
import { FilterChips } from '../../src/components/FilterChips';
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
import { completeTask, startTask } from '../../src/api/housekeeping';
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

// Status filter chips — some chips fold several backend statuses into one
// scannable bucket (ready = sellable, attention = needs an engineer).
const STATUS_FILTERS = [
  { value: 'all', label: tr.housekeeping.all },
  { value: 'dirty', label: tr.housekeeping.statuses.dirty },
  { value: 'cleaning', label: tr.housekeeping.statuses.cleaning },
  { value: 'ready', label: tr.housekeeping.filterReady },
  { value: 'occupied', label: tr.housekeeping.statuses.occupied },
  { value: 'attention', label: tr.housekeeping.filterAttention },
];

function statusMatches(room: Room, filter: string): boolean {
  const s = (room.status || '').toLowerCase();
  switch (filter) {
    case 'all':
      return true;
    case 'ready':
      return ['available', 'inspected', 'clean'].includes(s);
    case 'attention':
      return ['maintenance', 'out_of_order'].includes(s);
    default:
      return s === filter;
  }
}

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
  const [statusFilter, setStatusFilter] = useState<string>('all');
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

  // ── Status-change sheet state ────────────────────────────────────────────
  const [statusRoom, setStatusRoom] = useState<Room | null>(null);

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
    } catch {
      haptic.error();
    } finally {
      setSubmitting(false);
    }
  };

  // ── One-tap start / complete with optimistic ['room-tasks'] cache update ──
  // Start flips the task → in_progress in-place; complete drops it from the
  // open list (a completed task is no longer "open"). Both roll back on error
  // and re-sync rooms + the shared hub feed on settle.
  const startMut = useMutation({
    mutationFn: (taskId: string) => startTask(taskId),
    onMutate: async (taskId: string) => {
      haptic.tap();
      await qc.cancelQueries({ queryKey: ['room-tasks'] });
      const prev = qc.getQueryData<RoomTask[]>(['room-tasks']);
      qc.setQueryData<RoomTask[]>(['room-tasks'], (data) =>
        (data || []).map((t) => (t.id === taskId ? { ...t, status: 'in_progress' } : t)),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['room-tasks'], ctx.prev);
      haptic.error();
    },
    onSuccess: () => haptic.success(),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['room-tasks'] });
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['my-tasks'] });
    },
  });

  const completeMut = useMutation({
    mutationFn: (taskId: string) => completeTask(taskId),
    onMutate: async (taskId: string) => {
      haptic.tap();
      await qc.cancelQueries({ queryKey: ['room-tasks'] });
      const prev = qc.getQueryData<RoomTask[]>(['room-tasks']);
      qc.setQueryData<RoomTask[]>(['room-tasks'], (data) =>
        (data || []).filter((t) => t.id !== taskId),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(['room-tasks'], ctx.prev);
      haptic.error();
    },
    onSuccess: () => haptic.success(),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['room-tasks'] });
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['my-tasks'] });
    },
  });

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

  const floorFilters = useMemo(
    () => [
      { value: 'all', label: tr.housekeeping.all },
      ...floors.map((f) => ({ value: f, label: `${tr.housekeeping.floor} ${f}` })),
    ],
    [floors],
  );

  const filtered = useMemo(() => {
    let list = rooms.data || [];
    if (floor !== 'all') list = list.filter((r) => String(r.floor) === floor);
    if (statusFilter !== 'all') list = list.filter((r) => statusMatches(r, statusFilter));
    return list;
  }, [rooms.data, floor, statusFilter]);

  // Urgency-first ordering so the rooms that need action surface at the top
  // (urgent/high open tasks, then dirty/out-of-order, then the rest). Within an
  // equal bucket we keep a stable natural room-number order.
  const sortedRooms = useMemo(() => {
    const urgency = (r: Room): number => {
      const tasks = tasksByRoom.get(r.id) || [];
      let score = tasks.reduce((acc, t) => {
        const p = (t.priority || '').toLowerCase();
        return acc + (p === 'urgent' ? 100 : p === 'high' ? 40 : 10);
      }, 0);
      const s = (r.status || '').toLowerCase();
      if (s === 'dirty') score += 30;
      else if (s === 'out_of_order' || s === 'maintenance') score += 20;
      else if (s === 'cleaning' || s === 'inspection') score += 10;
      return score;
    };
    return [...filtered].sort((a, b) => {
      const d = urgency(b) - urgency(a);
      if (d !== 0) return d;
      return a.room_number.localeCompare(b.room_number, 'tr', { numeric: true });
    });
  }, [filtered, tasksByRoom]);

  // Ready = sellable/clean rooms across the whole property (not floor-filtered)
  // so the progress hero reflects the full picture.
  const readyCount = useMemo(
    () =>
      (rooms.data || []).filter((r) =>
        ['available', 'inspected', 'clean'].includes((r.status || '').toLowerCase()),
      ).length,
    [rooms.data],
  );
  const totalCount = (rooms.data || []).length;
  const readyPct = totalCount > 0 ? Math.round((readyCount / totalCount) * 100) : 0;

  const offline = rooms.isError && isOffline(rooms.error);

  // Status flips are applied straight from the status sheet. The deterministic
  // cross-platform signal is the optimistic cache update + the PUT round-trip
  // itself + the sheet closing — so the flow is fully usable and testable on
  // web (no reliance on the native success Alert).
  const applyStatus = async (r: Room, s: StatusOption) => {
    const prev = qc.getQueryData<Room[]>(['rooms']) || [];
    qc.setQueryData<Room[]>(['rooms'], (data) =>
      (data || []).map((x) => (x.id === r.id ? { ...x, status: s } : x)),
    );
    setStatusRoom(null);
    try {
      await updateRoomStatus(r.id, s);
      haptic.success();
      qc.invalidateQueries({ queryKey: ['rooms'] });
    } catch {
      qc.setQueryData<Room[]>(['rooms'], prev);
      haptic.error();
    }
  };

  const openStatus = (r: Room) => {
    haptic.tap();
    setStatusRoom(r);
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

  const tasksRoomList: RoomTask[] = tasksRoom ? tasksByRoom.get(tasksRoom.id) || [] : [];

  const renderRoom = ({ item: r }: { item: Room }) => {
    const color = roomStatusColor(r.status, c);
    const key = (r.status || '').toLowerCase() as keyof typeof tr.housekeeping.statuses;
    const label = tr.housekeeping.statuses[key] || r.status || '—';
    const openCount = (tasksByRoom.get(r.id) || []).length;
    return (
      <Pressable
        onPress={() => openTasks(r)}
        accessibilityLabel={
          `Oda ${r.room_number}, durum ${label}` +
          (openCount ? `, ${openCount} ${tr.housekeeping.openTasks}` : '')
        }
        accessibilityHint={tr.housekeeping.viewTasks}
        style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1, marginBottom: spacing.sm })}
      >
        <Card style={{ borderLeftWidth: 4, borderLeftColor: color }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <View style={{ flex: 1 }}>
              <H2>Oda {r.room_number}</H2>
              <Muted>
                {r.room_type || '—'} · Kat {r.floor ?? '—'}
              </Muted>
              {r.guest_name ? (
                <Muted numberOfLines={1}>
                  {tr.housekeeping.guest}: {r.guest_name}
                </Muted>
              ) : null}
            </View>
            <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
              <Badge label={label} tone={roomStatusTone(r.status)} />
              {openCount > 0 ? (
                <Badge label={`${openCount} ${tr.housekeeping.openTasks}`} tone="info" />
              ) : null}
              {/* Tap-twin of a swipe-to-clean gesture: dirty rooms get a single
                  thumb-zone action to flip straight to "Temizleniyor" without
                  opening the status sheet. */}
              {(r.status || '').toLowerCase() === 'dirty' ? (
                <Button
                  title={tr.housekeeping.quickClean}
                  variant="success"
                  icon="sparkles"
                  onPress={() => void applyStatus(r, 'cleaning')}
                  testID="hk-quick-clean"
                  style={{
                    paddingVertical: spacing.xs,
                    paddingHorizontal: spacing.sm,
                    minHeight: 0,
                  }}
                />
              ) : null}
              {/* Direct tap entries to the status + assign sheets — discoverable
                  on every platform and a stable e2e affordance to open each
                  sheet. */}
              <Button
                title={tr.housekeeping.changeStatus}
                variant="secondary"
                onPress={() => openStatus(r)}
                testID="hk-room-status"
                style={{
                  paddingVertical: spacing.xs,
                  paddingHorizontal: spacing.sm,
                  minHeight: 0,
                }}
              />
              <Button
                title={tr.housekeeping.assignTask}
                variant="secondary"
                onPress={() => openAssign(r)}
                testID="hk-room-assign"
                style={{
                  paddingVertical: spacing.xs,
                  paddingHorizontal: spacing.sm,
                  minHeight: 0,
                }}
              />
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

      {totalCount > 0 ? (
        <Card accent={c.primary} style={{ marginBottom: spacing.sm }}>
          <View
            style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}
          >
            <H2>
              {readyCount} / {totalCount} {tr.housekeeping.roomsReadyProgress}
            </H2>
            <Badge
              label={`%${readyPct}`}
              tone={readyPct >= 80 ? 'success' : readyPct >= 50 ? 'warning' : 'danger'}
            />
          </View>
          <View
            style={{
              height: 8,
              borderRadius: radius.pill,
              backgroundColor: c.surfaceAlt,
              marginTop: spacing.sm,
              overflow: 'hidden',
            }}
          >
            <View
              style={{
                height: 8,
                width: `${readyPct}%`,
                backgroundColor: c.success,
                borderRadius: radius.pill,
              }}
            />
          </View>
        </Card>
      ) : null}

      <FilterChips options={floorFilters} value={floor} onChange={setFloor} />
      <FilterChips options={STATUS_FILTERS} value={statusFilter} onChange={setStatusFilter} />
      <View style={{ height: spacing.sm }} />

      {rooms.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : (
        <FlatList
          data={sortedRooms}
          keyExtractor={(r) => r.id}
          renderItem={renderRoom}
          contentContainerStyle={{ paddingBottom: spacing.xxl }}
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
          ListEmptyComponent={<EmptyState icon="bed-outline" title={tr.app.empty} />}
        />
      )}

      {/* ── Open-tasks viewer + one-tap start/complete ────────────────────── */}
      <ActionSheet
        visible={tasksRoom !== null}
        onClose={() => setTasksRoom(null)}
        title={
          tr.housekeeping.openTasksTitle + (tasksRoom ? ` · Oda ${tasksRoom.room_number}` : '')
        }
        testID="hk-tasks-modal"
      >
        {tasksRoomList.length === 0 ? (
          <EmptyState icon="checkmark-done-circle-outline" title={tr.housekeeping.noOpenTasks} />
        ) : (
          tasksRoomList.map((t) => {
            const inProgress = (t.status || '').toLowerCase() === 'in_progress';
            const pending = startMut.isPending && startMut.variables === t.id;
            const finishing = completeMut.isPending && completeMut.variables === t.id;
            return (
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
                  {inProgress ? (
                    <Badge label={tr.housekeeping.taskInProgress} tone="info" />
                  ) : (
                    <Badge label={priorityText(t.priority)} tone={priorityTone(t.priority)} />
                  )}
                </View>
                <Muted style={{ marginTop: spacing.xs }}>
                  {t.assigned_to || tr.housekeeping.unassigned}
                </Muted>
                {t.notes ? (
                  <Muted style={{ marginTop: spacing.xs }} numberOfLines={3}>
                    {t.notes}
                  </Muted>
                ) : null}
                <View style={{ marginTop: spacing.sm }}>
                  <SegmentedActions>
                    {!inProgress ? (
                      <ActionButton
                        testID={`hk-task-start-${t.id}`}
                        label={tr.housekeeping.startTask}
                        icon="play"
                        onPress={() => startMut.mutate(t.id)}
                        bg={c.primary}
                        fg={c.primaryText}
                        loading={pending}
                        disabled={finishing}
                      />
                    ) : null}
                    <ActionButton
                      testID={`hk-task-complete-${t.id}`}
                      label={tr.housekeeping.completeTask}
                      icon="checkmark-done"
                      onPress={() => completeMut.mutate(t.id)}
                      bg={c.success}
                      fg="#ffffff"
                      loading={finishing}
                      disabled={pending}
                    />
                  </SegmentedActions>
                </View>
              </Card>
            );
          })
        )}

        <View style={{ marginTop: spacing.sm }}>
          <Button
            title={tr.housekeeping.assignTask}
            variant="secondary"
            onPress={() => {
              const r = tasksRoom;
              setTasksRoom(null);
              if (r) openAssign(r);
            }}
            fullWidth
          />
        </View>
      </ActionSheet>

      {/* ── Status-change sheet ───────────────────────────────────────────── */}
      <ActionSheet
        visible={statusRoom !== null}
        onClose={() => setStatusRoom(null)}
        title={
          tr.housekeeping.changeStatus + (statusRoom ? ` · Oda ${statusRoom.room_number}` : '')
        }
        testID="hk-status-modal"
      >
        {STATUS_OPTIONS.map((s) => {
          const active = (statusRoom?.status || '').toLowerCase() === s;
          return (
            <Button
              key={s}
              title={tr.housekeeping.statuses[s] || s}
              variant={active ? 'primary' : 'secondary'}
              onPress={() => {
                const r = statusRoom;
                if (r) void applyStatus(r, s);
              }}
              testID={`hk-status-option-${s}`}
              fullWidth
            />
          );
        })}
        <View style={{ marginTop: spacing.sm }}>
          <Button
            title={tr.app.cancel}
            variant="secondary"
            onPress={() => setStatusRoom(null)}
            testID="hk-status-cancel"
            fullWidth
          />
        </View>
      </ActionSheet>

      {/* ── Task assignment sheet ─────────────────────────────────────────── */}
      <ActionSheet
        visible={assignRoom !== null}
        onClose={closeAssign}
        title={tr.housekeeping.assignTitle + (assignRoom ? ` · Oda ${assignRoom.room_number}` : '')}
        testID="hk-assign-modal"
      >
        <Muted>{tr.housekeeping.selectStaff}</Muted>
        {staff.isLoading ? (
          <SkeletonCard />
        ) : (staff.data || []).length === 0 ? (
          <Card testID="hk-no-staff">
            <Muted>{tr.housekeeping.noStaff}</Muted>
          </Card>
        ) : (
          <View style={{ gap: spacing.xs }}>
            {(staff.data || []).map((s, idx) => {
              const keyVal = s.id || s.name;
              const sel = (staffSel?.id || staffSel?.name) === keyVal;
              return (
                <Pressable
                  key={`${keyVal}-${idx}`}
                  onPress={() => setStaffSel(s)}
                  testID="hk-staff-option"
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
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
          {TASK_TYPES.map((t) => (
            <Button
              key={t}
              title={taskTypeLabel(t)}
              variant={taskType === t ? 'primary' : 'secondary'}
              onPress={() => setTaskType(t)}
              testID={`hk-task-type-${t}`}
              style={{ flexShrink: 0 }}
            />
          ))}
        </View>

        <Muted style={{ marginTop: spacing.md }}>{tr.housekeeping.priority}</Muted>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
          {PRIORITIES.map((p) => (
            <Button
              key={p}
              title={priorityLabel(p)}
              variant={priority === p ? 'primary' : 'secondary'}
              onPress={() => setPriority(p)}
              testID={`hk-priority-${p}`}
              style={{ flexShrink: 0 }}
            />
          ))}
        </View>

        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg }}>
          <Button
            title={tr.app.cancel}
            variant="secondary"
            onPress={closeAssign}
            testID="hk-assign-cancel"
            style={{ flex: 1 }}
          />
          <Button
            title={tr.housekeeping.assignSubmit}
            variant="primary"
            onPress={() => void submitAssign()}
            disabled={submitting || !staffSel}
            testID="hk-assign-submit"
            style={{ flex: 1 }}
          />
        </View>
      </ActionSheet>
    </View>
  );
}
