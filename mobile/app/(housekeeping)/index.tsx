import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  Platform,
  Pressable,
  RefreshControl,
  SectionList,
  Text,
  View,
} from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
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
  SuccessCheck,
  webCenter,
} from '../../src/components/ui';
import { FilterChips } from '../../src/components/FilterChips';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, radius, motion, useTheme, roomStatusColor } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { ROUTES } from '../../src/navigation/routes';
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
import { completeTask, reportIssue, startTask } from '../../src/api/housekeeping';
import { getInHouse } from '../../src/api/bookings';
import { haptic } from '../../src/hooks/useHaptic';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { useAuthStore } from '../../src/state/authStore';
import { mobileOperationAllowed } from '../../src/state/roleAccess';
import { useOnline } from '../../src/hooks/useOnline';
import { canConfirmRoomInspection, cleaningElapsedMinutes, indexBookingsByRoomNumber, roomNumberKey, roomPresentation, RoomPresentation } from '../../src/utils/roomPresentation';

// Animasyon native driver yalniz native'de; Expo Web'de false (RN web kurali).
const USE_NATIVE_DRIVER = Platform.OS !== 'web';

// Valid backend room statuses (housekeeping room/status endpoint):
// available, occupied, dirty, cleaning, inspected, maintenance, out_of_order.
// We expose the ones a housekeeper flips by hand.
const STATUS_OPTIONS = [
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

// Lifecycle buckets — every room lands in exactly one section so the screen is
// a complete worklist (no room silently hidden) and a housekeeper can read it
// top-to-bottom: ne yapilacak → ne yapiliyor → ne bitti.
type SectionKey = 'todo' | 'progress' | 'done' | 'blocked';
function bucketForRoom(state: RoomPresentation): SectionKey {
  if (state.blockedStatus) return 'blocked';
  if (state.isReady) return 'done';
  if (state.cleaning === 'cleaning' || state.cleaning === 'inspection') return 'progress';
  return 'todo';
}

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

function formatDuration(mins: number): string {
  if (mins < 60) return `${mins} ${tr.housekeeping.minutesShort}`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0
    ? `${h} ${tr.housekeeping.hoursShort}`
    : `${h} ${tr.housekeeping.hoursShort} ${m} ${tr.housekeeping.minutesShort}`;
}

// En yuksek oncelik (urgent > high > normal) acik gorevlerden turetilir.
function topPriority(tasks: RoomTask[]): string | null {
  let rank = 0;
  let label: string | null = null;
  for (const t of tasks) {
    const p = (t.priority || '').toLowerCase();
    const r = p === 'urgent' ? 3 : p === 'high' ? 2 : p === 'normal' ? 1 : 0;
    if (r > rank) {
      rank = r;
      label = p;
    }
  }
  return label;
}

function priorityText(p?: string | null): string {
  switch ((p || '').toLowerCase()) {
    case 'high':
      return tr.housekeeping.priorityHigh;
    case 'urgent':
      return tr.housekeeping.priorityUrgent;
    default:
      return tr.housekeeping.priorityNormal;
  }
}
function priorityTone(p?: string | null): BadgeTone {
  switch ((p || '').toLowerCase()) {
    case 'urgent':
      return 'danger';
    case 'high':
      return 'warning';
    default:
      return 'default';
  }
}

// ── Room card ───────────────────────────────────────────────────────────────
// Tek dokunusla calisan, buyuk dokunma alanli (>=48px) kart. "Temizlendi"
// Basari animasyonu sadece gercek gorev tamamlanmasindan sonra oynatilir.
// Temizligin bitmesi odanin son kontrolunun tamamlandigi anlamina gelmez.
const RoomCard: React.FC<{
  room: Room;
  presentation: RoomPresentation;
  occupancyKnown: boolean;
  actionsDisabled: boolean;
  canCompleteCleaning: boolean;
  assignee: string;
  openCount: number;
  durationMin: number | null;
  priority: string | null;
  showActions: boolean;
  onOpenTasks: (r: Room) => void;
  onStatus: (r: Room) => void;
  onAssign: (r: Room) => void;
  onMarkClean: (r: Room) => Promise<boolean>;
  onReport: (r: Room, kind: 'minibar' | 'fault') => Promise<boolean>;
  onDamage: (r: Room) => void;
}> = ({
  room,
  presentation,
  occupancyKnown,
  actionsDisabled,
  canCompleteCleaning,
  assignee,
  openCount,
  durationMin,
  priority,
  showActions,
  onOpenTasks,
  onStatus,
  onAssign,
  onMarkClean,
  onReport,
  onDamage,
}) => {
  const c = useTheme();
  const user = useAuthStore((s) => s.user);
  const canUpdate = mobileOperationAllowed(user, 'update_room_status');
  const canAssign = mobileOperationAllowed(user, 'assign_task');
  const accent = presentation.blockedStatus ? c.danger : roomStatusColor(room.status, c);
  const key = presentation.blockedStatus || (presentation.cleaning === 'ready' ? 'inspected' : presentation.cleaning);
  const label = key === 'unknown' || key === 'blocked' ? tr.housekeeping.statusUnknown : tr.housekeeping.statuses[key];
  const occupancyLabel = presentation.occupancy === 'blocked' ? tr.housekeeping.statusBlocked
    : presentation.occupancy === 'occupied' ? tr.housekeeping.statuses.occupied
    : occupancyKnown && presentation.occupancy === 'vacant' ? tr.housekeeping.statuses.available : tr.housekeeping.statusUnknown;

  const [busy, setBusy] = useState<null | 'clean' | 'minibar' | 'fault'>(null);
  const [confirm, setConfirm] = useState<null | 'minibar' | 'fault'>(null);
  const [error, setError] = useState(false);
  const [celebrate, setCelebrate] = useState(false);
  const [cleanConfirm, setCleanConfirm] = useState(false);
  const overlay = useRef(new Animated.Value(0)).current;
  const actionPending = useRef(false);
  const celebrationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reportTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (celebrationTimer.current) clearTimeout(celebrationTimer.current);
    if (reportTimer.current) clearTimeout(reportTimer.current);
  }, []);

  useEffect(() => {
    if (!celebrate) return;
    const anim = Animated.timing(overlay, {
      toValue: 1,
      duration: motion.base,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: USE_NATIVE_DRIVER,
    });
    anim.start();
    return () => anim.stop();
  }, [celebrate, overlay]);

  const handleClean = async () => {
    if (actionPending.current || busy || celebrate) return;
    if (!canCompleteCleaning || actionsDisabled) return;
    actionPending.current = true;
    setCleanConfirm(false);
    setError(false);
    setBusy('clean');
    const ok = await onMarkClean(room);
    actionPending.current = false;
    setBusy(null);
    if (ok) {
      haptic.success();
      setCelebrate(true);
      // Onay animasyonu gorunur kalsin, sonra kart bolumler arasi tasinsin.
      celebrationTimer.current = setTimeout(() => {
        setCelebrate(false);
        overlay.setValue(0);
      }, 950);
    } else {
      haptic.error();
      setError(true);
    }
  };

  const handleReport = async (kind: 'minibar' | 'fault') => {
    if (actionPending.current || busy || celebrate || actionsDisabled) return;
    actionPending.current = true;
    setError(false);
    setBusy(kind);
    const ok = await onReport(room, kind);
    actionPending.current = false;
    setBusy(null);
    if (ok) {
      haptic.success();
      setConfirm(kind);
      if (reportTimer.current) clearTimeout(reportTimer.current);
      reportTimer.current = setTimeout(() => setConfirm(null), 2500);
    } else {
      haptic.error();
      setError(true);
    }
  };

  return (
    <View style={{ marginBottom: spacing.sm }}>
        <Card style={{ borderLeftWidth: 4, borderLeftColor: accent }}>
          {/* Baslik: oda + durum */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: spacing.sm }}>
            <View style={{ flex: 1, minWidth: 110, paddingRight: spacing.sm }}>
              <H2>Oda {room.room_number}</H2>
              <Muted>
                {room.room_type || '—'} · {tr.housekeeping.floor} {room.floor ?? '—'}
              </Muted>
              {room.guest_name ? (
                <Muted numberOfLines={1} style={{ marginTop: 2 }}>
                  {tr.housekeeping.guest}: {room.guest_name}
                </Muted>
              ) : null}
            </View>
            <View style={{ alignItems: 'flex-end', gap: spacing.xs, flexShrink: 1 }}>
              <Badge label={`${tr.rooms.occupancyLabel}: ${occupancyLabel}`} tone={presentation.occupancy === 'blocked' ? 'danger' : presentation.occupancy === 'occupied' ? 'primary' : 'default'} />
              <Badge label={`${tr.rooms.cleaningLabel}: ${presentation.isReady && occupancyKnown ? tr.rooms.statusReady : label}`} tone={presentation.isReady && occupancyKnown ? 'success' : roomStatusTone(key)} />
              {openCount > 0 ? (
                <Badge label={`${openCount} ${tr.housekeeping.openTasks}`} tone="info" />
              ) : null}
            </View>
          </View>

          {assignee ? (
            <View style={{ flexDirection: 'row', gap: spacing.xs, alignItems: 'center', marginTop: spacing.sm }}>
              <Ionicons name="person-outline" size={15} color={c.textMuted} />
              <Muted>{tr.housekeeping.assignee}: {assignee}</Muted>
            </View>
          ) : null}

          {/* Bilgi seridi: oncelik + temizlik suresi */}
          {priority || durationMin !== null ? (
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: spacing.sm,
                marginTop: spacing.sm,
              }}
            >
              {priority ? (
                <Badge label={priorityText(priority)} tone={priorityTone(priority)} />
              ) : null}
              {durationMin !== null ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <Ionicons name="time-outline" size={14} color={c.textMuted} />
                  <Muted>
                    {room.housekeeping?.task_type === 'cleaning' ? tr.housekeeping.durationLabel : tr.housekeeping.taskDurationLabel}: {formatDuration(durationMin)}
                  </Muted>
                </View>
              ) : null}
            </View>
          ) : null}

          {/* Tek dokunus aksiyonlari */}
          {showActions ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              {canCompleteCleaning ? <Button
                title={tr.housekeeping.markClean}
                variant="success"
                icon="checkmark-circle"
                fullWidth
                loading={busy === 'clean'}
                disabled={busy !== null || celebrate || actionsDisabled}
                onPress={() => setCleanConfirm(true)}
                testID="hk-room-clean"
                style={{ minHeight: 56 }}
              /> : null}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
                <Button
                  title={tr.housekeeping.minibarMissing}
                  variant="secondary"
                  icon="wine-outline"
                  loading={busy === 'minibar'}
                  disabled={busy !== null || celebrate || actionsDisabled}
                  onPress={() => void handleReport('minibar')}
                  testID="hk-room-minibar"
                  style={{ flex: 1, minWidth: 150 }}
                />
                <Button
                  title={tr.housekeeping.reportFault}
                  variant="secondary"
                  icon="construct-outline"
                  loading={busy === 'fault'}
                  disabled={busy !== null || celebrate || actionsDisabled}
                  onPress={() => void handleReport('fault')}
                  testID="hk-room-fault"
                  style={{ flex: 1, minWidth: 150 }}
                />
              </View>
              <Button
                title={tr.housekeeping.reportDamage}
                variant="outline"
                icon="alert-circle-outline"
                fullWidth
                disabled={busy !== null || celebrate || !canUpdate}
                onPress={() => onDamage(room)}
                testID="hk-room-damage"
              />
              {confirm ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.xs }}>
                  <Ionicons name="checkmark-circle" size={16} color={c.success} />
                  <Text style={{ color: c.success, fontWeight: '700' }}>
                    {tr.housekeeping.reported}
                  </Text>
                </View>
              ) : null}
              {error ? (
                <Text style={{ color: c.danger, fontWeight: '600' }}>
                  {tr.housekeeping.actionError}
                </Text>
              ) : null}
            </View>
          ) : (
            <View style={{ marginTop: spacing.md, flexDirection: 'row', alignItems: 'center', gap: spacing.xs }}>
              <Ionicons name="checkmark-done-circle" size={18} color={c.success} />
              <Muted>{tr.rooms.statusReady}</Muted>
            </View>
          )}

          {/* İkincil: durum + gorev (e2e affordance + guc kullanicilari) */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm }}>
            <Button
              title={tr.housekeeping.changeStatus}
              variant="ghost"
              onPress={() => onStatus(room)}
              testID="hk-room-status"
              disabled={busy !== null || celebrate || !occupancyKnown || actionsDisabled || !canUpdate}
              style={{ flex: 1, minWidth: 150, minHeight: 48 }}
            />
            <Button
              title={tr.housekeeping.assignTask}
              variant="ghost"
              onPress={() => onAssign(room)}
              testID="hk-room-assign"
              disabled={busy !== null || celebrate || actionsDisabled || !canAssign}
              style={{ flex: 1, minWidth: 150, minHeight: 48 }}
            />
          </View>
          <Button title={tr.housekeeping.viewTasks} icon="list-outline" variant="secondary" fullWidth
            onPress={() => onOpenTasks(room)} disabled={busy !== null || celebrate} style={{ marginTop: spacing.sm }} />
        </Card>

      <ActionSheet visible={cleanConfirm} onClose={() => setCleanConfirm(false)} title={`${tr.housekeeping.confirmComplete} · ${room.room_number}`}>
        <Muted>{tr.housekeeping.confirmCompleteHint}</Muted>
        <Button title={tr.housekeeping.completeTask} onPress={() => void handleClean()} fullWidth />
        <Button title={tr.app.cancel} variant="secondary" onPress={() => setCleanConfirm(false)} fullWidth />
      </ActionSheet>

      {/* Basari katmani: backend onayindan SONRA yesile doner + onay isareti */}
      {celebrate ? (
        <Animated.View
          pointerEvents="none"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            borderRadius: radius.xl,
            backgroundColor: c.success + 'F2',
            alignItems: 'center',
            justifyContent: 'center',
            opacity: overlay,
          }}
        >
          <SuccessCheck label={tr.housekeeping.markCleanCelebrate} testID="hk-room-clean-success" />
        </Animated.View>
      ) : null}
    </View>
  );
};

export default function RoomsScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const online = useOnline();
  const userName = useAuthStore((state) => state.user?.name);
  const user = useAuthStore((state) => state.user);
  const canUpdate = mobileOperationAllowed(user, 'update_room_status');
  const canAssign = mobileOperationAllowed(user, 'assign_task');
  const [floor, setFloor] = useState<string>('all');
  const rooms = useQuery({ queryKey: ['rooms'], queryFn: listRooms });
  const roomTasks = useQuery({ queryKey: ['room-tasks'], queryFn: listRoomTasks });
  const inhouse = useQuery({ queryKey: ['hk-inhouse'], queryFn: getInHouse });
  const bookingByRoomNo = useMemo(() => indexBookingsByRoomNumber(inhouse.data || []), [inhouse.data]);
  const occupancyKnown = inhouse.isSuccess && !inhouse.isError;

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

  // ── Sheet state ──────────────────────────────────────────────────────────
  const [tasksRoom, setTasksRoom] = useState<Room | null>(null);
  const [statusRoom, setStatusRoom] = useState<Room | null>(null);
  const [statusSelection, setStatusSelection] = useState<StatusOption | null>(null);
  const [statusPending, setStatusPending] = useState(false);
  const statusRequestPending = useRef(false);
  const [statusError, setStatusError] = useState(false);
  const [completeConfirm, setCompleteConfirm] = useState<RoomTask | null>(null);
  const [assignRoom, setAssignRoom] = useState<Room | null>(null);
  const [staffSel, setStaffSel] = useState<HkStaff | null>(null);
  const [taskType, setTaskType] = useState<TaskType>('cleaning');
  const [priority, setPriority] = useState<Priority>('normal');
  const [submitting, setSubmitting] = useState(false);
  const [assignError, setAssignError] = useState(false);
  const staff = useQuery({
    queryKey: ['hk-staff'],
    queryFn: listHousekeepingStaff,
    enabled: assignRoom !== null,
  });

  const openAssign = (r: Room) => {
    if (!canAssign) return;
    haptic.tap();
    setAssignRoom(r);
    setStaffSel(null);
    setTaskType('cleaning');
    setPriority('normal');
    setAssignError(false);
  };
  const closeAssign = () => {
    if (submitting) return;
    setAssignRoom(null);
  };

  const submitAssign = async () => {
    if (!canAssign || !assignRoom || submitting || !online) return;
    if (!staffSel) return;
    setSubmitting(true);
    setAssignError(false);
    try {
      await createQuickTask({
        room_id: assignRoom.id,
        task_type: taskType,
        priority,
        assigned_to: staffSel.name,
      });
      haptic.success();
      setAssignRoom(null);
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['my-tasks'] });
      qc.invalidateQueries({ queryKey: ['room-tasks'] });
    } catch {
      haptic.error();
      setAssignError(true);
    } finally {
      setSubmitting(false);
    }
  };

  // ── One-tap start / complete with optimistic ['room-tasks'] cache update ──
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
    onMutate: () => { haptic.tap(); },
    onError: () => haptic.error(),
    onSuccess: () => { haptic.success(); setCompleteConfirm(null); },
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
    return list;
  }, [rooms.data, floor]);

  // Urgency-first ordering inside each section so the rooms that need action
  // surface at the top (urgent/high open tasks, then dirty/out-of-order).
  const sortByUrgency = useMemo(() => {
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
    return (a: Room, b: Room) => {
      const d = urgency(b) - urgency(a);
      if (d !== 0) return d;
      return a.room_number.localeCompare(b.room_number, 'tr', { numeric: true });
    };
  }, [tasksByRoom]);

  const sections = useMemo(() => {
    const buckets: Record<SectionKey, Room[]> = { todo: [], progress: [], done: [], blocked: [] };
    for (const r of filtered) {
      const state = roomPresentation(r, !!bookingByRoomNo[roomNumberKey(r.room_number)], tasksByRoom.get(r.id) || []);
      const bucket = (!occupancyKnown || !roomTasks.isSuccess) && state.isReady ? 'todo' : bucketForRoom(state);
      buckets[bucket].push(r);
    }
    (Object.keys(buckets) as SectionKey[]).forEach((k) => buckets[k].sort(sortByUrgency));
    return [
      { key: 'todo' as const, title: tr.housekeeping.sectionTodo, data: buckets.todo },
      { key: 'progress' as const, title: tr.housekeeping.sectionProgress, data: buckets.progress },
      { key: 'blocked' as const, title: tr.housekeeping.sectionBlocked, data: buckets.blocked },
      { key: 'done' as const, title: tr.housekeeping.sectionDone, data: buckets.done },
    ];
  }, [filtered, sortByUrgency, bookingByRoomNo, tasksByRoom, occupancyKnown, roomTasks.isSuccess]);

  // Ready requires a completed inspection, known vacancy, and no open task.
  const readyCount = useMemo(
    () =>
      occupancyKnown && roomTasks.isSuccess ? (rooms.data || []).filter((r) =>
        roomPresentation(r, !!bookingByRoomNo[roomNumberKey(r.room_number)], tasksByRoom.get(r.id) || []).isReady,
      ).length : 0,
    [rooms.data, bookingByRoomNo, tasksByRoom, occupancyKnown, roomTasks.isSuccess],
  );
  const totalCount = (rooms.data || []).length;
  const readyPct = totalCount > 0 ? Math.round((readyCount / totalCount) * 100) : 0;

  const offline = !online || rooms.fetchStatus === 'paused' || (rooms.isError && isOffline(rooms.error));

  // Complete only the caller's active cleaning task. Never promote cleaning
  // directly to inspected or overwrite the room's occupancy status.
  const markClean = async (r: Room): Promise<boolean> => {
    if (!canUpdate) return false;
    const presentation = roomPresentation(r, !!bookingByRoomNo[roomNumberKey(r.room_number)], tasksByRoom.get(r.id) || []);
    const task = (tasksByRoom.get(r.id) || []).find((item) => item.task_type === 'cleaning' && item.status === 'in_progress' && item.assigned_to === userName);
    if (!task || presentation.blockedStatus || !occupancyKnown || !online) return false;
    try {
      await completeTask(task.id);
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['room-tasks'] });
      qc.invalidateQueries({ queryKey: ['my-tasks'] });
      qc.invalidateQueries({ queryKey: ['frontdesk-rooms'] });
      return true;
    } catch {
      return false;
    }
  };
  // Minibar Eksik / Ariza Bildir → gercek "report-issue" kaydi. Ariza türü
  // backend'de ek bir muhendislik gorevi de acar. Basari yaniti await edilir.
  const reportQuick = async (r: Room, kind: 'minibar' | 'fault'): Promise<boolean> => {
    if (!canUpdate) return false;
    try {
      await reportIssue({
        room_id: r.id,
        issue_type: kind === 'minibar' ? 'minibar' : 'maintenance',
        description:
          kind === 'minibar'
            ? `Oda ${r.room_number}: ${tr.housekeeping.minibarMissing}`
            : `Oda ${r.room_number}: ${tr.housekeeping.reportFault}`,
        priority: kind === 'fault' ? 'high' : 'normal',
      });
      qc.invalidateQueries({ queryKey: ['room-tasks'] });
      qc.invalidateQueries({ queryKey: ['my-tasks'] });
      qc.invalidateQueries({ queryKey: ['rooms'] });
      return true;
    } catch {
      return false;
    }
  };

  // Hasar Bildir → zengin fotografli form (damage ekranina odayi onceden doldur).
  const goDamage = (r: Room) => {
    haptic.tap();
    router.push({
      pathname: ROUTES.hkDamage,
      params: { roomId: r.id, roomNumber: r.room_number },
    });
  };

  const statusesForRoom = (room: Room, hasBooking: boolean, tasks: RoomTask[]): StatusOption[] => {
    const state = roomPresentation(room, hasBooking, tasks);
    if (state.blockedStatus || state.occupancy === 'occupied') return ['maintenance', 'out_of_order'];
    if (state.occupancy === 'unknown') return [];
    return STATUS_OPTIONS.filter((status) => status !== 'inspected' || canConfirmRoomInspection(room, hasBooking, tasks));
  };
  const allowedStatuses = (room: Room): StatusOption[] => {
    if (!canUpdate || !occupancyKnown || !roomTasks.isSuccess || !online) return [];
    const current = (rooms.data || []).find((item) => item.id === room.id);
    return current ? statusesForRoom(current, !!bookingByRoomNo[roomNumberKey(current.room_number)], tasksByRoom.get(current.id) || []) : [];
  };

  // Only commit after confirmation and the server response; a failed update
  // leaves the sheet open with an explicit retryable error.
  const applyStatus = async (r: Room, s: StatusOption) => {
    if (statusRequestPending.current || !allowedStatuses(r).includes(s)) return;
    statusRequestPending.current = true;
    setStatusPending(true);
    setStatusError(false);
    try {
      // The room may have been occupied or blocked while the confirmation
      // sheet was open. Validate fresh room, occupancy and task data together.
      const [currentRooms, currentBookings, currentTasks] = await Promise.all([listRooms(), getInHouse(), listRoomTasks()]);
      qc.setQueryData(['rooms'], currentRooms);
      qc.setQueryData(['hk-inhouse'], currentBookings);
      qc.setQueryData(['room-tasks'], currentTasks);
      const current = currentRooms.find((item) => item.id === r.id);
      const currentBookingByRoom = indexBookingsByRoomNumber(currentBookings);
      if (!current || !statusesForRoom(current, !!currentBookingByRoom[roomNumberKey(current.room_number)], currentTasks.filter((task) => task.room_id === r.id)).includes(s)) {
        throw new Error(tr.housekeeping.roomActionBlocked);
      }
      await updateRoomStatus(r.id, s);
      haptic.success();
      setStatusRoom(null);
      setStatusSelection(null);
      qc.invalidateQueries({ queryKey: ['rooms'] });
      qc.invalidateQueries({ queryKey: ['frontdesk-rooms'] });
    } catch {
      haptic.error();
      setStatusError(true);
    } finally {
      statusRequestPending.current = false;
      setStatusPending(false);
    }
  };

  const openStatus = (r: Room) => {
    haptic.tap();
    setStatusRoom(r);
    setStatusSelection(null);
    setStatusError(false);
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
        return tr.housekeeping.taskOther;
    }
  };

  const tasksRoomList: RoomTask[] = tasksRoom ? tasksByRoom.get(tasksRoom.id) || [] : [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <View style={[{ flex: 1, padding: spacing.lg }, webCenter]}>
      <H1>{tr.housekeeping.title}</H1>
      <Muted>{tr.housekeeping.longPressHint}</Muted>
      <View style={{ height: spacing.md }} />
      <OfflineBanner visible={!!offline} />

      {totalCount > 0 && occupancyKnown && roomTasks.isSuccess ? (
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
      <View style={{ height: spacing.sm }} />

      {/* Room data loads fine but task fetch failed: surface it instead of
          silently showing rooms with no task badges. */}
      {inhouse.isError ? (
        <Card accent={c.warning}>
          <Muted>{tr.housekeeping.occupancyUnavailable}</Muted>
          <Button title={tr.app.retry} variant="outline" onPress={() => inhouse.refetch()} fullWidth />
        </Card>
      ) : null}
      {roomTasks.isError && !rooms.isError ? (
        <Card accent={c.danger}>
          <Muted>{tr.housekeeping.tasksLoadError}</Muted>
          <View style={{ height: spacing.sm }} />
          <Button
            title={tr.app.retry}
            icon="refresh"
            variant="outline"
            onPress={() => roomTasks.refetch()}
            fullWidth
          />
        </Card>
      ) : null}

      {offline && !rooms.data ? (
        <Card accent={c.warning}>
          <Muted>{tr.app.offline}</Muted>
          <Button title={tr.app.retry} variant="outline" onPress={() => { rooms.refetch(); roomTasks.refetch(); inhouse.refetch(); }} fullWidth />
        </Card>
      ) : rooms.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : rooms.isError && !offline ? (
        <Card accent={c.danger}>
          <Muted>{errorMessage(rooms.error, tr.rooms.loadError)}</Muted>
          <View style={{ height: spacing.sm }} />
          <Button
            title={tr.app.retry}
            icon="refresh"
            variant="outline"
            onPress={() => {
              rooms.refetch();
              roomTasks.refetch();
            }}
            fullWidth
          />
        </Card>
      ) : totalCount === 0 ? (
        <EmptyState icon="bed-outline" title={tr.app.empty} />
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(r) => r.id}
          stickySectionHeadersEnabled={false}
          renderSectionHeader={({ section }) => (
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginTop: spacing.md,
                marginBottom: spacing.xs,
              }}
            >
              <H2>{section.title}</H2>
              <Badge label={String(section.data.length)} tone="default" />
            </View>
          )}
          renderSectionFooter={({ section }) =>
            section.data.length === 0 ? (
              <Muted style={{ marginBottom: spacing.sm }}>{tr.housekeeping.sectionEmpty}</Muted>
            ) : null
          }
          renderItem={({ item, section }) => {
            const tasks = tasksByRoom.get(item.id) || [];
            const presentation = roomPresentation(item, !!bookingByRoomNo[roomNumberKey(item.room_number)], tasks);
            const assignee = item.housekeeping?.assigned_to_name || Array.from(new Set(tasks.map((task) => task.assigned_to).filter(Boolean))).join(', ');
            return (
            <RoomCard
              room={item}
              presentation={presentation}
              occupancyKnown={occupancyKnown && roomTasks.isSuccess}
              actionsDisabled={offline || !canUpdate}
              canCompleteCleaning={occupancyKnown && roomTasks.isSuccess && !presentation.blockedStatus && tasks.some((task) => task.task_type === 'cleaning' && task.status === 'in_progress' && task.assigned_to === userName)}
              assignee={assignee}
              openCount={(tasksByRoom.get(item.id) || []).length}
              durationMin={cleaningElapsedMinutes(item.housekeeping?.elapsed_minutes)}
              priority={topPriority(tasksByRoom.get(item.id) || [])}
              showActions={section.key !== 'done'}
              onOpenTasks={openTasks}
              onStatus={openStatus}
              onAssign={openAssign}
              onMarkClean={markClean}
              onReport={reportQuick}
              onDamage={goDamage}
            />
          ); }}
          contentContainerStyle={{ paddingBottom: spacing.xxl }}
          refreshControl={
            <RefreshControl
              refreshing={
                (rooms.isFetching && !rooms.isLoading) ||
                (roomTasks.isFetching && !roomTasks.isLoading)
                || (inhouse.isFetching && !inhouse.isLoading)
              }
              onRefresh={() => {
                rooms.refetch();
                roomTasks.refetch();
                inhouse.refetch();
              }}
              tintColor={c.primary}
            />
          }
        />
      )}
      </View>

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
            const owned = !!userName && t.assigned_to === userName;
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
                {!owned ? <Muted style={{ marginTop: spacing.sm }}>{tr.housekeeping.onlyOwnTasks}</Muted> : null}
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
                        disabled={!canUpdate || !owned || offline || startMut.isPending || completeMut.isPending}
                      />
                    ) : null}
                    <ActionButton
                      testID={`hk-task-complete-${t.id}`}
                      label={tr.housekeeping.completeTask}
                      icon="checkmark-done"
                      onPress={() => { completeMut.reset(); setCompleteConfirm(t); }}
                      bg={c.success}
                      fg="#ffffff"
                      loading={finishing}
                      disabled={!canUpdate || !owned || offline || !inProgress || startMut.isPending || completeMut.isPending}
                    />
                  </SegmentedActions>
                </View>
              </Card>
            );
          })
        )}
        {startMut.isError ? <Text accessibilityRole="alert" style={{ color: c.danger }}>{tr.housekeeping.taskActionError}</Text> : null}

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

      <ActionSheet visible={completeConfirm !== null} onClose={() => { if (!completeMut.isPending) setCompleteConfirm(null); }} title={tr.housekeeping.confirmComplete}>
        <Muted>{tr.housekeeping.confirmCompleteHint}</Muted>
        {completeMut.isError ? <Text accessibilityRole="alert" style={{ color: c.danger }}>{tr.housekeeping.taskActionError}</Text> : null}
        <Button title={tr.housekeeping.completeTask} loading={completeMut.isPending} disabled={offline} fullWidth onPress={() => {
          if (completeConfirm && !completeMut.isPending && completeConfirm.assigned_to === userName) completeMut.mutate(completeConfirm.id);
        }} />
        <Button title={tr.app.cancel} variant="secondary" disabled={completeMut.isPending} fullWidth onPress={() => setCompleteConfirm(null)} />
      </ActionSheet>

      {/* ── Status-change sheet ───────────────────────────────────────────── */}
      <ActionSheet
        visible={statusRoom !== null}
        onClose={() => { if (!statusPending) setStatusRoom(null); }}
        title={
          tr.housekeeping.changeStatus + (statusRoom ? ` · Oda ${statusRoom.room_number}` : '')
        }
        testID="hk-status-modal"
      >
        <Muted>{tr.housekeeping.roomActionBlocked}</Muted>
        {(statusRoom ? allowedStatuses(statusRoom) : []).map((s) => {
          const active = statusSelection === s;
          return (
            <Button
              key={s}
              title={s === 'inspected' ? tr.housekeeping.inspectionConfirm : tr.housekeeping.statuses[s]}
              variant={active ? 'primary' : 'secondary'}
              onPress={() => setStatusSelection(s)}
              disabled={statusPending}
              testID={`hk-status-option-${s}`}
              fullWidth
            />
          );
        })}
        {statusSelection ? (
          <View style={{ gap: spacing.sm, marginTop: spacing.md }}>
            <Muted>{statusSelection === 'inspected' ? tr.housekeeping.confirmInspection : tr.housekeeping.confirmStatusHint}</Muted>
            <Button title={tr.app.confirm} loading={statusPending} fullWidth onPress={() => {
              if (statusRoom && statusSelection) void applyStatus(statusRoom, statusSelection);
            }} />
          </View>
        ) : null}
        {statusError ? <Text accessibilityRole="alert" style={{ color: c.danger }}>{tr.housekeeping.actionError}</Text> : null}
        <View style={{ marginTop: spacing.sm }}>
          <Button
            title={tr.app.cancel}
            variant="secondary"
            onPress={() => setStatusRoom(null)}
            disabled={statusPending}
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
        ) : staff.isError ? (
          <Card accent={c.danger} testID="hk-staff-error">
            <Muted>{errorMessage(staff.error, tr.housekeeping.staffLoadError)}</Muted>
            <View style={{ height: spacing.sm }} />
            <Button
              title={tr.app.retry}
              icon="refresh"
              variant="outline"
              onPress={() => staff.refetch()}
              fullWidth
            />
          </Card>
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
                  accessibilityRole="radio"
                  accessibilityLabel={s.name}
                  accessibilityState={{ selected: sel, disabled: submitting }}
                  disabled={submitting}
                  testID="hk-staff-option"
                  style={{
                    borderWidth: 1,
                    borderColor: sel ? c.primary : c.border,
                    backgroundColor: sel ? c.primary : c.surface,
                    borderRadius: radius.md,
                    paddingVertical: spacing.md,
                    minHeight: 48,
                    paddingHorizontal: spacing.md,
                  }}
                >
                  <Text style={{ color: sel ? c.primaryText : c.text, fontWeight: '600' }}>
                    {s.name}
                  </Text>
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
              disabled={submitting}
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
              disabled={submitting}
              testID={`hk-priority-${p}`}
              style={{ flexShrink: 0 }}
            />
          ))}
        </View>
        {assignError ? <Text accessibilityRole="alert" style={{ color: c.danger, marginTop: spacing.sm }}>{tr.housekeeping.assignError}</Text> : null}

        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.lg }}>
          <Button
            title={tr.app.cancel}
            variant="secondary"
            onPress={closeAssign}
            disabled={submitting}
            testID="hk-assign-cancel"
            style={{ flex: 1 }}
          />
          <Button
            title={tr.housekeeping.assignSubmit}
            variant="primary"
            onPress={() => void submitAssign()}
            disabled={submitting || !staffSel || offline}
            loading={submitting}
            testID="hk-assign-submit"
            style={{ flex: 1 }}
          />
        </View>
      </ActionSheet>
    </View>
  );
}
