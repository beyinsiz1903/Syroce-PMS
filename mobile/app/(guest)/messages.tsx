import React from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, EmptyState, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getGuestMessages } from '../../src/api/guestMessaging';
import { formatTime, formatDate } from '../../src/utils/format';

const ROUTE_THREAD = '/(guest)/messageThread' as const;

export default function MessagesListScreen() {
  const c = useTheme();
  const router = useRouter();
  const q = useQuery({
    queryKey: ['guest-messages'],
    queryFn: getGuestMessages,
    refetchInterval: 15_000,
  });

  const conversations = q.data?.conversations || [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.xxl }}
      refreshControl={
        <RefreshControl
          refreshing={q.isFetching && !q.isLoading}
          onRefresh={() => q.refetch()}
          tintColor={c.primary}
        />
      }
    >
      <H1>{tr.guest.messagesTitle}</H1>
      {q.isLoading ? (
        <SkeletonCard />
      ) : conversations.length === 0 ? (
        <Card padded={false}>
          <EmptyState
            icon="chatbubbles-outline"
            title={tr.guest.noMessages}
            message={tr.guest.noMessagesMessage}
          />
        </Card>
      ) : (
        conversations.map((conv) => {
          const lastMsg = conv.messages?.[0];
          const key = conv.booking_id || conv.guest_user_id || lastMsg?.id || Math.random().toString();
          return (
            <Pressable
              key={key}
              onPress={() =>
                router.push({
                  pathname: ROUTE_THREAD,
                  params: { bookingId: conv.booking_id || '', title: conv.guest_name || '' },
                })
              }
              accessibilityRole="button"
              accessibilityLabel={`${conv.guest_name || 'Misafir'}, ${conv.unread_count} okunmamış mesaj`}
              style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
            >
              <Card>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <H2>{conv.guest_name || 'Otel'}</H2>
                    {conv.room_number ? <Muted>Oda {conv.room_number}</Muted> : null}
                    {lastMsg ? (
                      <Body
                        numberOfLines={2}
                        style={{ color: c.textMuted, marginTop: spacing.xs }}
                      >
                        {lastMsg.sender === 'guest' ? `${tr.guest.sentBy}: ` : ''}
                        {lastMsg.message}
                      </Body>
                    ) : null}
                  </View>
                  <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
                    {conv.unread_count > 0 ? (
                      <Badge label={String(conv.unread_count)} tone="primary" />
                    ) : null}
                    <Muted style={{ fontSize: 11 }}>
                      {conv.last_message_at ? formatDate(conv.last_message_at) : ''}{' '}
                      {conv.last_message_at ? formatTime(conv.last_message_at) : ''}
                    </Muted>
                  </View>
                </View>
              </Card>
            </Pressable>
          );
        })
      )}
    </ScrollView>
  );
}
