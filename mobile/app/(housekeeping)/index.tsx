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
import { haptic } from '../../src/hooks/useHaptic';
import { isOffline } from '../../src/utils/errors';

// Animasyon native driver yalniz native'de; Expo Web'de false (RN web kurali).
const USE_NATIVE_DRIVER = Platform.OS !== 'web';

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

// Lifecycle buckets — every room lands in exactly one section so the screen is
// a complete worklist (no room silently hidden) and a housekeeper can read it
// top-to-bottom: ne yapilacak → ne yapiliyor → ne bitti.
type SectionKey = 'todo' | 'progress' | 'done';
function bucketForRoom(status: string | undefined): SectionKey {
  const s = (status || '').toLowerCase();
  if (s === 'cleaning' || s === 'inspection') return 'progress';
  if (s === 'inspected' || s === 'clean' || s === 'available') return 'done';
  return 'todo'; // dirty, occupied, maintenance, out_of_order, bilinmeyen
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

// "Temizlik suresi": en eski acik gorevin olusturuldugu andan bu yana gecen
// gercek sure (task.created_at backend verisi). Gorev yoksa null (rozet cizilmez).
function elapsedFromTasks(tasks: RoomTask[]): number | null {
  let oldest = Number.POSITIVE_INFINITY;
  for (const t of tasks) {
    if (!t.created_at) continue;
    const ts = Date.parse(t.created_at);
    if (!Number.isNaN(ts) && ts < oldest) oldest = ts;
  }
  if (!Number.isFinite(oldest)) return null;
  const mins = Math.max(0, Math.round((Date.now() - oldest) / 60000));
  return mins;
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
// SADECE backend 200 dondukten SONRA yesil + onay animasyonu oynatir (sahte
// basari yok); animasyon bitince kart optimistik olarak "Tamamlananlar"a tasinir.
const RoomCard: React.FC<{
  room: Room;
  openCount: number;
  durationMin: number | null;
  priority: string | null;
  showActions: boolean;
  onOpenTasks: (r: Room) => void;
  onStatus: (r: Room) => void;
  onAssign: (r: Room) => void;
  onMarkClean: (r: Room) => Promise<boolean>;
  onCommitClean: (r: Room) => void;
  onReport: (r: Room, kind: 'minibar' | 'fault') => Promise<boolean>;
  onDamage: (r: Room) => void;
}> = ({
  room,
  openCount,
  durationMin,
  priority,
  showActions,
  onOpenTasks,
  onStatus,
  onAssign,
  onMarkClean,
  onCommitClean,
  onReport,
  onDamage,
}) => {
  const c = useTheme();
  const accent = roomStatusColor(room.status, c);
  const key = (room.status || '').toLowerCase() as keyof typeof tr.housekeeping.statuses;
  const label = tr.housekeeping.statuses[key] || room.status || '—';

  const [busy, setBusy] = useState<null | 'clean' | 'minibar' | 'fault'>(null);
  const [confirm, setConfirm] = useState<null | 'minibar' | 'fault'>(null);
  const [error, setError] = useState(false);
  const [celebrate, setCelebrate] = useState(false);
  const overlay = useRef(new Animated.Value(0)).current;

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
    if (busy || celebrate) return;
    setError(false);
    setBusy('clean');
    const ok = await onMarkClean(room);
    setBusy(null);
    if (ok) {
      haptic.success();
      setCelebrate(true);
      // Onay animasyonu gorunur kalsin, sonra kart bolumler arasi tasinsin.
      setTimeout(() => onCommitClean(room), 950);
    } else {
      haptic.error();
      setError(true);
    }
  };

  const handleReport = async (kind: 'minibar' | 'fault') => {
    if (busy || celebrate) return;
    setError(false);
    setBusy(kind);
    const ok = await onReport(room, kind);
    setBusy(null);
    if (ok) {
      haptic.success();
      setConfirm(kind);
      setTimeout(() => setConfirm(null), 2500);
    } else {
      haptic.error();
      setError(true);
    }
  };

  return (
    <View style={{ marginBottom: spacing.sm }}>
      <Pressable
        onPress={() => onOpenTasks(room)}
        accessibilityLabel={
          `Oda ${room.room_number}, durum ${label}` +
          (openCount ? `, ${openCount} ${tr.housekeeping.openTasks}` : '')
        }
        accessibilityHint={tr.housekeeping.viewTasks}
        style={({ pressed }) => ({ opacity: pressed ? 0.92 : 1 })}
      >
        <Card style={{ borderLeftWidth: 4, borderLeftColor: accent }}>
          {/* Baslik: oda + durum */}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <View style={{ flex: 1, paddingRight: spacing.sm }}>
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
            <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
              <Badge label={label} tone={roomStatusTone(room.status)} />
              {openCount > 0 ? (
                <Badge label={`${openCount} ${tr.housekeeping.openTasks}`} tone="info" />
              ) : null}
            </View>
          </View>

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
                    {tr.housekeeping.durationLabel}: {formatDuration(durationMin)}
                  </Muted>
                </View>
              ) : null}
            </View>
          ) : null}

          {/* Tek dokunus aksiyonlari */}
          {showActions ? (
            <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
              <Button
                title={tr.housekeeping.markClean}
                variant="success"
                icon="checkmark-circle"
                fullWidth
                loading={busy === 'clean'}
                disabled={busy !== null || celebrate}
                onPress={handleClean}
                testID="hk-room-clean"
                style={{ minHeight: 56 }}
              />
              <View style={{ flexDirection: 'row', gap: spacing.sm }}>
                <Button
                  title={tr.housekeeping.minibarMissing}
                  variant="secondary"
                  icon="wine-outline"
                  loading={busy === 'minibar'}
                  disabled={busy !== null || celebrate}
                  onPress={() => void handleReport('minibar')}
                  testID="hk-room-minibar"
                  style={{ flex: 1 }}
                />
                <Button
                  title={tr.housekeeping.reportFault}
                  variant="secondary"
                  icon="construct-outline"
                  loading={busy === 'fault'}
                  disabled={busy !== null || celebrate}
                  onPress={() => void handleReport('fault')}
                  testID="hk-room-fault"
                  style={{ flex: 1 }}
                />
              </View>
              <Button
                title={tr.housekeeping.reportDamage}
                variant="outline"
                icon="alert-circle-outline"
                fullWidth
                disabled={busy !== null || celebrate}
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
              <Muted>{tr.housekeeping.statuses.inspected}</Muted>
            </View>
          )}

          {/* İkincil: durum + gorev (e2e affordance + guc kullanicilari) */}
          <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
            <Button
              title={tr.housekeeping.changeStatus}
              variant="ghost"
              onPress={() => onStatus(room)}
              testID="hk-room-status"
              style={{ flex: 1, minHeight: 40, paddingVertical: spacing.xs }}
            />
            <Button
              title={tr.housekeeping.assignTask}
              variant="ghost"
              onPress={() => onAssign(room)}
              testID="hk-room-assign"
              style={{ flex: 1, minHeight: 40, paddingVertical: spacing.xs }}
            />
          </View>
        </Card>
      </Pressable>

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

  // ── Sheet state ──────────────────────────────────────────────────────────
  const [tasksRoom, setTasksRoom] = useState<Room | null>(null);
  const [statusRoom, setStatusRoom] = useState<Room | null>(null);
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
    haptic.tap();
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
    if (!staffSel) return;
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
    const buckets: Record<SectionKey, Room[]> = { todo: [], progress: [], done: [] };
    for (const r of filtered) buckets[bucketForRoom(r.status)].push(r);
    (Object.keys(buckets) as SectionKey[]).forEach((k) => buckets[k].sort(sortByUrgency));
    return [
      { key: 'todo' as const, title: tr.housekeeping.sectionTodo, data: buckets.todo },
      { key: 'progress' as const, title: tr.housekeeping.sectionProgress, data: buckets.progress },
      { key: 'done' as const, title: tr.housekeeping.sectionDone, data: buckets.done },
    ];
  }, [filtered, sortByUrgency]);

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

  // ── One-tap "Temizlendi" — PUT first, celebrate only on a real 200 ───────
  // Returns success so the card can gate its green/check animation on the
  // backend response (no fake success). The cross-section move (cache flip) is
  // committed by `commitClean` AFTER the celebration plays.
  const markClean = async (r: Room): Promise<boolean> => {
    try {
      await updateRoomStatus(r.id, 'inspected');
      return true;
    } catch {
      return false;
    }
  };
  const commitClean = (r: Room) => {
    qc.setQueryData<Room[]>(['rooms'], (data) =>
      (data || []).map((x) => (x.id === r.id ? { ...x, status: 'inspected' } : x)),
    );
    qc.invalidateQueries({ queryKey: ['rooms'] });
    qc.invalidateQueries({ queryKey: ['room-tasks'] });
    qc.invalidateQueries({ queryKey: ['my-tasks'] });
  };

  // Minibar Eksik / Ariza Bildir → gercek "report-issue" kaydi. Ariza türü
  // backend'de ek bir muhendislik gorevi de acar. Basari yaniti await edilir.
  const reportQuick = async (r: Room, kind: 'minibar' | 'fault'): Promise<boolean> => {
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

  // Status flips are applied straight from the status sheet (optimistic + PUT).
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

  const tasksRoomList: RoomTask[] = tasksRoom ? tasksByRoom.get(tasksRoom.id) || [] : [];

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
      <View style={{ height: spacing.sm }} />

      {rooms.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </View>
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
          renderItem={({ item, section }) => (
            <RoomCard
              room={item}
              openCount={(tasksByRoom.get(item.id) || []).length}
              durationMin={elapsedFromTasks(tasksByRoom.get(item.id) || [])}
              priority={topPriority(tasksByRoom.get(item.id) || [])}
              showActions={section.key !== 'done'}
              onOpenTasks={openTasks}
              onStatus={openStatus}
              onAssign={openAssign}
              onMarkClean={markClean}
              onCommitClean={commitClean}
              onReport={reportQuick}
              onDamage={goDamage}
            />
          )}
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
