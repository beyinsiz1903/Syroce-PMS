import React, { useRef, useState } from 'react';
import {
  Dimensions,
  Image,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  ScrollView,
  View,
} from 'react-native';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { Body, Muted, Badge } from './ui';
import { radius, spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';
import { formatDate } from '../utils/format';
import type { WorkOrder } from '../api/maintenance';

// Trello/Linear-style maintenance kanban (Task #511). Faults (work orders) are
// bucketed into four columns and dragged between them. A drop calls back to the
// caller, which performs the backend status PATCH; on failure the card simply
// stays where it was (no optimistic move, so there is no fake success — the
// card "returns" to its old column because the data never changed).

type ColumnStatus = 'open' | 'in_progress' | 'on_hold' | 'completed';

// Canonical drop status per column + the raw statuses that bucket into it.
const COLUMNS: { status: ColumnStatus; match: string[] }[] = [
  { status: 'open', match: ['open', '', 'new'] },
  { status: 'in_progress', match: ['in_progress', 'started'] },
  { status: 'on_hold', match: ['on_hold', 'needs_parts', 'waiting'] },
  { status: 'completed', match: ['completed'] },
];

const screenW = Dimensions.get('window').width;
const COLUMN_WIDTH = Math.min(300, Math.max(240, screenW * 0.78));
const COLUMN_GAP = spacing.md;
const SLOT = COLUMN_WIDTH + COLUMN_GAP;

function columnIndexForStatus(status?: string): number {
  const s = (status || '').toLowerCase();
  const idx = COLUMNS.findIndex((col) => col.match.includes(s));
  return idx >= 0 ? idx : 0;
}

function issueTypeLabel(t?: string): string {
  const map = tr.departments.maintenance.issueTypes as Record<string, string>;
  return (t && map[t]) || t || '—';
}

function priorityLabel(p?: string): string {
  const map = tr.departments.maintenance.priorities as Record<string, string>;
  return (p && map[p]) || p || '—';
}

function priorityTone(p?: string): 'default' | 'warning' | 'danger' | 'info' {
  switch (p) {
    case 'urgent':
      return 'danger';
    case 'high':
      return 'warning';
    case 'low':
      return 'info';
    default:
      return 'default';
  }
}

function workOrderPhoto(w: WorkOrder): string | null {
  if (w.photo_url) return w.photo_url;
  if (w.photos && w.photos.length > 0) return w.photos[0];
  return null;
}

// A single draggable card. Long-press activates the drag so a quick horizontal
// swipe still scrolls the board (web-safe — uses pointer events on RN-Web).
const KanbanCard: React.FC<{
  workOrder: WorkOrder;
  accent: string;
  pending: boolean;
  onDrop: (workOrder: WorkOrder, dropX: number) => void;
  onDragStart: () => void;
  onDragEnd: () => void;
}> = ({ workOrder: w, accent, pending, onDrop, onDragStart, onDragEnd }) => {
  const c = useTheme();
  const tx = useSharedValue(0);
  const ty = useSharedValue(0);
  const lift = useSharedValue(0);

  const pan = Gesture.Pan()
    .activateAfterLongPress(180)
    .onStart(() => {
      lift.value = withTiming(1, { duration: 120 });
      runOnJS(onDragStart)();
    })
    .onUpdate((e) => {
      tx.value = e.translationX;
      ty.value = e.translationY;
    })
    .onEnd((e) => {
      runOnJS(onDrop)(w, e.absoluteX);
    })
    .onFinalize(() => {
      tx.value = withSpring(0, { damping: 18, stiffness: 180 });
      ty.value = withSpring(0, { damping: 18, stiffness: 180 });
      lift.value = withTiming(0, { duration: 160 });
      runOnJS(onDragEnd)();
    });

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: tx.value },
      { translateY: ty.value },
      { scale: 1 + lift.value * 0.04 },
    ],
    zIndex: lift.value > 0 ? 1000 : 1,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 8 + lift.value * 8 },
    shadowOpacity: 0.18 + lift.value * 0.22,
    shadowRadius: 14 + lift.value * 12,
    elevation: 4 + lift.value * 10,
  }));

  const photo = workOrderPhoto(w);
  const assignee = w.assigned_to_name || w.assigned_to || null;

  return (
    <GestureDetector gesture={pan}>
      <Animated.View
        testID={`maint-card-${w.id}`}
        accessibilityRole="button"
        accessibilityLabel={`${issueTypeLabel(w.issue_type)} ${
          w.room_number ? tr.departments.maintenance.room + ' ' + w.room_number : ''
        }`}
        style={[
          {
            backgroundColor: c.surface,
            borderRadius: radius.lg,
            borderWidth: 1,
            borderColor: c.border,
            borderLeftWidth: 4,
            borderLeftColor: accent,
            padding: spacing.md,
            marginBottom: spacing.sm,
            opacity: pending ? 0.55 : 1,
          },
          animStyle,
        ]}
      >
        {/* Glass top highlight for the premium card feel. */}
        <View
          pointerEvents="none"
          style={{
            position: 'absolute',
            top: 0,
            left: 4,
            right: 0,
            height: 1,
            backgroundColor: c.glassHighlight,
            borderTopRightRadius: radius.lg,
          }}
        />
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Body style={{ fontWeight: '700', flex: 1, paddingRight: spacing.sm }}>
            {issueTypeLabel(w.issue_type)}
          </Body>
          <Badge label={priorityLabel(w.priority)} tone={priorityTone(w.priority)} />
        </View>

        {w.room_number ? (
          <Muted style={{ marginTop: spacing.xs }}>
            {tr.departments.maintenance.room}: {w.room_number}
          </Muted>
        ) : null}

        {w.description ? (
          <Body style={{ marginTop: spacing.xs, fontSize: 13, color: c.textMuted }} numberOfLines={2}>
            {w.description}
          </Body>
        ) : null}

        {photo ? (
          <Image
            source={{ uri: photo }}
            accessibilityLabel={tr.departments.maintenance.photoAlt}
            resizeMode="cover"
            style={{
              marginTop: spacing.sm,
              width: '100%',
              height: 120,
              borderRadius: radius.md,
              backgroundColor: c.surfaceAlt,
            }}
          />
        ) : null}

        <View
          style={{
            marginTop: spacing.sm,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: spacing.sm,
          }}
        >
          <Muted style={{ flex: 1 }} numberOfLines={1}>
            {tr.departments.maintenance.assigned}:{' '}
            <Body style={{ fontSize: 13, color: assignee ? c.text : c.textMuted }}>
              {assignee || tr.departments.maintenance.unassigned}
            </Body>
          </Muted>
          {w.created_at ? <Muted style={{ fontSize: 12 }}>{formatDate(w.created_at)}</Muted> : null}
        </View>
      </Animated.View>
    </GestureDetector>
  );
};

export const MaintenanceKanban: React.FC<{
  workOrders: WorkOrder[];
  // Returns true when the backend confirmed the status change.
  onMove: (workOrder: WorkOrder, targetStatus: ColumnStatus) => Promise<boolean>;
}> = ({ workOrders, onMove }) => {
  const c = useTheme();

  // Geometry used to resolve which column a card was dropped over. The board's
  // window x-offset is captured on layout; the horizontal scroll offset is
  // tracked live. column screen-x = boardWinX + i*SLOT - scrollX.
  const boardWinX = useRef(0);
  const scrollX = useRef(0);
  const boardRef = useRef<View>(null);

  const [pendingId, setPendingId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const accents: Record<ColumnStatus, string> = {
    open: c.primary,
    in_progress: c.info,
    on_hold: c.warning,
    completed: c.success,
  };

  const buckets: WorkOrder[][] = COLUMNS.map(() => []);
  for (const w of workOrders) {
    const s = (w.status || '').toLowerCase();
    if (s === 'cancelled' || s === 'canceled') continue; // terminal — off-board
    buckets[columnIndexForStatus(w.status)].push(w);
  }

  const measureBoard = () => {
    boardRef.current?.measureInWindow((x) => {
      boardWinX.current = x;
    });
  };

  const onBoardLayout = (_e: LayoutChangeEvent) => measureBoard();

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    scrollX.current = e.nativeEvent.contentOffset.x;
  };

  const handleDrop = async (w: WorkOrder, dropX: number) => {
    const localX = dropX - boardWinX.current + scrollX.current;
    const idx = Math.max(0, Math.min(COLUMNS.length - 1, Math.floor(localX / SLOT)));
    const target = COLUMNS[idx].status;
    const sourceIdx = columnIndexForStatus(w.status);
    if (idx === sourceIdx) return; // dropped back onto its own column

    setPendingId(w.id);
    try {
      await onMove(w, target);
    } finally {
      setPendingId(null);
    }
  };

  return (
    <View ref={boardRef} onLayout={onBoardLayout} style={{ position: 'relative' }} testID="maint-kanban">
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        scrollEnabled={!dragging}
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={{ paddingRight: spacing.lg, gap: COLUMN_GAP }}
      >
        {COLUMNS.map((col, i) => {
          const items = buckets[i];
          return (
            <View
              key={col.status}
              testID={`maint-col-${col.status}`}
              style={{ width: COLUMN_WIDTH }}
            >
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingVertical: spacing.sm,
                  paddingHorizontal: spacing.xs,
                  marginBottom: spacing.xs,
                  borderBottomWidth: 2,
                  borderBottomColor: accents[col.status],
                }}
              >
                <Body style={{ fontWeight: '700' }}>
                  {tr.departments.maintenance.columns[col.status]}
                </Body>
                <View
                  style={{
                    minWidth: 24,
                    paddingHorizontal: spacing.xs,
                    height: 22,
                    borderRadius: radius.pill,
                    backgroundColor: c.surfaceAlt,
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Muted style={{ fontSize: 12, fontWeight: '700' }}>{items.length}</Muted>
                </View>
              </View>

              {items.length === 0 ? (
                <View
                  style={{
                    borderWidth: 1,
                    borderColor: c.border,
                    borderStyle: 'dashed',
                    borderRadius: radius.lg,
                    paddingVertical: spacing.xl,
                    alignItems: 'center',
                  }}
                >
                  <Muted>{tr.departments.maintenance.kanban.empty}</Muted>
                </View>
              ) : (
                items.map((w) => (
                  <KanbanCard
                    key={w.id}
                    workOrder={w}
                    accent={accents[col.status]}
                    pending={pendingId === w.id}
                    onDrop={handleDrop}
                    onDragStart={() => setDragging(true)}
                    onDragEnd={() => setDragging(false)}
                  />
                ))
              )}
            </View>
          );
        })}
      </ScrollView>
      <Muted style={{ marginTop: spacing.sm }}>{tr.departments.maintenance.kanban.dragHint}</Muted>
    </View>
  );
};
