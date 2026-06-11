import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { isOffline } from '../../src/utils/errors';
import { MyTask, getMyTasks } from '../../src/api/hub';

function priorityTone(priority: string): 'danger' | 'warning' | 'default' {
  if (priority === 'urgent') return 'danger';
  if (priority === 'high') return 'warning';
  return 'default';
}

function TaskRow({ task }: { task: MyTask }) {
  const kindLabel = task.kind === 'housekeeping' ? tr.hub.housekeeping : tr.hub.maintenance;
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: '600' }}>{task.title}</Body>
        {task.priority && task.priority !== 'normal' ? (
          <Badge label={task.priority} tone={priorityTone(task.priority)} />
        ) : null}
      </View>
      <Muted style={{ marginTop: spacing.xs }}>
        {kindLabel}
        {task.room_number ? ` · ${tr.hub.room} ${task.room_number}` : ''} · {task.status}
      </Muted>
      {task.notes ? (
        <Muted style={{ marginTop: spacing.xs }} numberOfLines={2}>
          {task.notes}
        </Muted>
      ) : null}
    </Card>
  );
}

export default function MyTasksScreen() {
  const c = useTheme();
  const tasks = useQuery({ queryKey: ['hub-my-tasks'], queryFn: getMyTasks });

  const refreshing = tasks.isFetching && !tasks.isLoading;
  const onRefresh = useCallback(() => {
    tasks.refetch();
  }, [tasks]);

  const offline = tasks.isError && isOffline(tasks.error);
  const rows = tasks.data?.tasks ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.myTasksTitle}</H1>
        {tasks.data ? (
          <Muted>
            {tasks.data.by_kind.housekeeping} {tr.hub.housekeeping} ·{' '}
            {tasks.data.by_kind.maintenance} {tr.hub.maintenance}
          </Muted>
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
          <Card>
            <Muted>{tr.hub.tasksEmpty}</Muted>
          </Card>
        ) : (
          rows.map((task) => <TaskRow key={task.id} task={task} />)
        )}
      </ScrollView>
    </View>
  );
}
