import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Body, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { isOffline } from '../../src/utils/errors';
import { getToday } from '../../src/api/hub';

export default function TodayScreen() {
  const c = useTheme();
  const { user, approvalsAccess, allAccess } = useAuthStore();
  const today = useQuery({ queryKey: ['hub-today'], queryFn: getToday });

  const refreshing = today.isFetching && !today.isLoading;
  const onRefresh = useCallback(() => {
    today.refetch();
  }, [today]);

  const offline = today.isError && isOffline(today.error);
  const data = today.data;
  const preview = data?.tasks_preview ?? [];

  // Role-aware framing line: approvers (managers) are steered to pending
  // approvals first, everyone else to their open tasks. Falls back to an
  // all-clear note. Cosmetic only — no query/RBAC change, backend still gates.
  const canApprove = approvalsAccess || allAccess;
  const pendingApprovals = data?.pending_approvals ?? 0;
  const openTasks = data?.open_tasks ?? 0;
  const focusLine =
    canApprove && pendingApprovals > 0
      ? tr.hub.focusApprovals
      : openTasks > 0
        ? tr.hub.focusTasks
        : tr.hub.focusAllClear;

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-today">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.todayTitle}</H1>
        <Muted>{user?.name || user?.username || user?.email}</Muted>
        {data ? (
          <Body style={{ color: c.primary, fontWeight: '600' }}>{focusLine}</Body>
        ) : null}

        {today.isLoading ? (
          <>
            <KpiRow>
              <SkeletonCard />
              <SkeletonCard />
            </KpiRow>
            <KpiRow>
              <SkeletonCard />
              <SkeletonCard />
            </KpiRow>
          </>
        ) : today.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : (
          <>
            <KpiRow>
              <KpiCard
                testID="hub-open-tasks"
                label={tr.hub.openTasks}
                value={String(data?.open_tasks ?? 0)}
                tone={(data?.open_tasks ?? 0) > 0 ? 'info' : 'default'}
              />
              <KpiCard
                testID="hub-urgent-tasks"
                label={tr.hub.urgentTasks}
                value={String(data?.urgent_tasks ?? 0)}
                tone={(data?.urgent_tasks ?? 0) > 0 ? 'danger' : 'default'}
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="hub-unread-feed"
                label={tr.hub.unreadFeed}
                value={String(data?.unread_feed ?? 0)}
                tone={(data?.unread_feed ?? 0) > 0 ? 'warning' : 'default'}
              />
              <KpiCard
                testID="hub-pending-approvals"
                label={tr.hub.pendingApprovals}
                value={String(data?.pending_approvals ?? 0)}
                tone={(data?.pending_approvals ?? 0) > 0 ? 'warning' : 'default'}
              />
            </KpiRow>

            <H2 style={{ marginTop: spacing.sm }}>{tr.hub.upcomingTasks}</H2>
            {preview.length === 0 ? (
              <Card>
                <Muted>{tr.hub.tasksEmpty}</Muted>
              </Card>
            ) : (
              preview.map((task) => (
                <Card key={task.id} style={{ marginBottom: spacing.sm }}>
                  <Body style={{ fontWeight: '600' }}>{task.title}</Body>
                  <Muted style={{ marginTop: spacing.xs }}>
                    {task.room_number ? `${tr.hub.room} ${task.room_number} · ` : ''}
                    {task.status}
                  </Muted>
                </Card>
              ))
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}
