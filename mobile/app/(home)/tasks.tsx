import React, { useCallback, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, EmptyState, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { FilterChips } from '../../src/components/FilterChips';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { isOffline } from '../../src/utils/errors';
import { MyTask, MyTaskKind, getMyTasks } from '../../src/api/hub';

function priorityTone(priority: string): 'danger' | 'warning' | 'default' {
  if (priority === 'urgent') return 'danger';
  if (priority === 'high') return 'warning';
  return 'default';
}

// Status drives the card's left accent + the status badge tone so a housekeeper
// or technician reads the state of each row at a glance. Statuses arrive raw
// from the backend (housekeeping + maintenance use different vocabularies), so
// we keyword-match rather than enumerate.
function statusTone(status: string): 'success' | 'warning' | 'info' | 'danger' | 'default' {
  const s = (status || '').toLowerCase();
  if (s.includes('complet') || s.includes('done') || s.includes('clean') || s.includes('tamam'))
    return 'success';
  if (s.includes('progress') || s.includes('start') || s.includes('assigned') || s.includes('devam'))
    return 'info';
  if (s.includes('wait') || s.includes('pending') || s.includes('hold') || s.includes('bekle'))
    return 'warning';
  if (s.includes('cancel') || s.includes('block') || s.includes('iptal')) return 'danger';
  return 'default';
}

function priorityLabel(priority: string): string {
  if (priority === 'urgent') return tr.hub.priorityUrgent;
  if (priority === 'high') return tr.hub.priorityHigh;
  return tr.hub.priorityNormal;
}

function TaskRow({ task }: { task: MyTask }) {
  const c = useTheme();
  const kindLabel = task.kind === 'housekeeping' ? tr.hub.housekeeping : tr.hub.maintenance;
  const tone = statusTone(task.status);
  const accentMap: Record<string, string> = {
    danger: c.danger,
    warning: c.warning,
    info: c.info,
    success: c.success,
    default: c.border,
  };
  // Urgency wins the accent if the task is flagged; otherwise the status colour.
  const accent =
    task.priority === 'urgent'
      ? c.danger
      : task.priority === 'high'
        ? c.warning
        : accentMap[tone];

  return (
    <Card accent={accent} style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: '600' }}>{task.title}</Body>
        {task.priority && task.priority !== 'normal' ? (
          <Badge label={priorityLabel(task.priority)} tone={priorityTone(task.priority)} />
        ) : null}
      </View>
      <View
        style={{
          marginTop: spacing.sm,
          flexDirection: 'row',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: spacing.sm,
        }}
      >
        <Badge label={task.status} tone={tone} />
        <Muted>
          {kindLabel}
          {task.room_number ? ` · ${tr.hub.room} ${task.room_number}` : ''}
        </Muted>
      </View>
      {task.notes ? (
        <Muted style={{ marginTop: spacing.xs }} numberOfLines={2}>
          {task.notes}
        </Muted>
      ) : null}
    </Card>
  );
}

type KindFilter = 'all' | MyTaskKind;

export default function MyTasksScreen() {
  const c = useTheme();
  const [kind, setKind] = useState<KindFilter>('all');
  const tasks = useQuery({ queryKey: ['hub-my-tasks'], queryFn: getMyTasks });

  const refreshing = tasks.isFetching && !tasks.isLoading;
  const onRefresh = useCallback(() => {
    tasks.refetch();
  }, [tasks]);

  const offline = tasks.isError && isOffline(tasks.error);
  const rows = tasks.data?.tasks ?? [];

  const filtered = useMemo(
    () => (kind === 'all' ? rows : rows.filter((t) => t.kind === kind)),
    [rows, kind],
  );

  const byKind = tasks.data?.by_kind;
  const filterOptions = useMemo(
    () => [
      { value: 'all', label: `${tr.hub.filterAll}${byKind ? ` (${rows.length})` : ''}` },
      {
        value: 'housekeeping',
        label: `${tr.hub.housekeeping}${byKind ? ` (${byKind.housekeeping})` : ''}`,
      },
      {
        value: 'maintenance',
        label: `${tr.hub.maintenance}${byKind ? ` (${byKind.maintenance})` : ''}`,
      },
    ],
    [byKind, rows.length],
  );

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-tasks">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.myTasksTitle}</H1>

        {rows.length > 0 ? (
          <FilterChips
            options={filterOptions}
            value={kind}
            onChange={(v) => setKind(v as KindFilter)}
            testID="hub-tasks-filter"
          />
        ) : null}

        {tasks.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : tasks.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : rows.length === 0 ? (
          <EmptyState
            icon="checkmark-done-circle-outline"
            title={tr.hub.tasksEmpty}
            message={tr.hub.tasksEmptyHint}
          />
        ) : filtered.length === 0 ? (
          <EmptyState icon="filter-outline" title={tr.hub.tasksFilterEmpty} />
        ) : (
          filtered.map((task) => <TaskRow key={task.id} task={task} />)
        )}
      </ScrollView>
    </View>
  );
}
