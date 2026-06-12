import React, { useCallback } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Button, Card, H1, Muted, SkeletonCard } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { isOffline } from '../../src/utils/errors';
import { FeedItem, getFeed, markFeedRead } from '../../src/api/hub';

function priorityTone(priority: string): 'danger' | 'warning' | 'default' {
  if (priority === 'urgent') return 'danger';
  if (priority === 'high') return 'warning';
  return 'default';
}

function FeedRow({ item }: { item: FeedItem }) {
  const c = useTheme();
  const queryClient = useQueryClient();
  const mark = useMutation({
    mutationFn: () => markFeedRead(item.source, item.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['hub-feed'] });
      queryClient.invalidateQueries({ queryKey: ['hub-today'] });
    },
  });

  return (
    <Card
      style={{
        marginBottom: spacing.sm,
        borderLeftWidth: item.read ? 1 : 3,
        borderLeftColor: item.read ? c.border : c.primary,
      }}
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: item.read ? '400' : '600' }}>{item.title || '—'}</Body>
        {item.priority && item.priority !== 'normal' ? (
          <Badge label={item.priority} tone={priorityTone(item.priority)} />
        ) : null}
      </View>
      {item.message ? (
        <Muted style={{ marginTop: spacing.xs }} numberOfLines={3}>
          {item.message}
        </Muted>
      ) : null}
      {!item.read ? (
        <View style={{ marginTop: spacing.sm }}>
          <Button
            title={tr.hub.markRead}
            variant="secondary"
            loading={mark.isPending}
            onPress={() => mark.mutate()}
          />
        </View>
      ) : null}
      {mark.isError ? (
        <Muted style={{ marginTop: spacing.xs, color: c.danger }}>{tr.hub.markReadError}</Muted>
      ) : null}
    </Card>
  );
}

export default function NotificationsScreen() {
  const c = useTheme();
  const feed = useQuery({ queryKey: ['hub-feed'], queryFn: () => getFeed({ limit: 50 }) });

  const refreshing = feed.isFetching && !feed.isLoading;
  const onRefresh = useCallback(() => {
    feed.refetch();
  }, [feed]);

  const offline = feed.isError && isOffline(feed.error);
  const items = feed.data?.items ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-notifications">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.notificationsTitle}</H1>
        {feed.data ? (
          <Muted>
            {feed.data.unread_count} {tr.hub.unread}
          </Muted>
        ) : null}

        {feed.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : feed.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : items.length === 0 ? (
          <Card>
            <Muted>{tr.hub.notificationsEmpty}</Muted>
          </Card>
        ) : (
          items.map((item) => <FeedRow key={`${item.source}-${item.id}`} item={item} />)
        )}
      </ScrollView>
    </View>
  );
}
