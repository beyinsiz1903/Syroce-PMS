import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { isOffline } from '../../src/utils/errors';
import { ApprovalItem, getApprovals } from '../../src/api/hub';

function priorityTone(priority: string): 'danger' | 'warning' | 'default' {
  if (priority === 'urgent') return 'danger';
  if (priority === 'high') return 'warning';
  return 'default';
}

function ApprovalRow({ item }: { item: ApprovalItem }) {
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: '600' }}>{item.title}</Body>
        {item.priority && item.priority !== 'normal' ? (
          <Badge label={item.priority} tone={priorityTone(item.priority)} />
        ) : null}
      </View>
      {item.requested_by ? (
        <Muted style={{ marginTop: spacing.xs }}>
          {tr.hub.requestedBy}: {item.requested_by}
        </Muted>
      ) : null}
    </Card>
  );
}

export default function ApprovalsScreen() {
  const c = useTheme();
  const approvals = useQuery({ queryKey: ['hub-approvals'], queryFn: getApprovals });

  const refreshing = approvals.isFetching && !approvals.isLoading;
  const onRefresh = useCallback(() => {
    approvals.refetch();
  }, [approvals]);

  const offline = approvals.isError && isOffline(approvals.error);
  const categories = approvals.data?.categories ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.approvalsTitle}</H1>

        {approvals.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : approvals.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : categories.length === 0 ? (
          <Card>
            <Muted>{tr.hub.approvalsEmpty}</Muted>
          </Card>
        ) : (
          categories.map((cat) => (
            <View key={cat.key} style={{ gap: spacing.sm }}>
              <H2>
                {cat.label} ({cat.count})
              </H2>
              {cat.items.length === 0 ? (
                <Card>
                  <Muted>{tr.hub.approvalsEmpty}</Muted>
                </Card>
              ) : (
                cat.items.map((item) => <ApprovalRow key={`${cat.key}-${item.id}`} item={item} />)
              )}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}
