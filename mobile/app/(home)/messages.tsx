import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  TextInput,
  View,
} from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  H1,
  Muted,
  SkeletonCard,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { isOffline } from '../../src/utils/errors';
import {
  Conversation,
  ThreadMessage,
  getConversationThread,
  getConversations,
  markConversationRead,
  sendInternalMessage,
} from '../../src/api/hub';

// Staff-to-staff messaging (Task #333). Built on the existing internal-messaging
// backend. The tab toggles between a conversation list and a single thread view;
// no navigation route is added so the bottom-tab backbone stays unchanged.

// Derive 1–2 letter initials for the conversation avatar (mirrors the Profile
// avatar treatment) so the list scans like a familiar inbox.
function initialsFor(name: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '—';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function Avatar({ name, unread }: { name: string; unread: boolean }) {
  const c = useTheme();
  const tint = unread ? c.primary : c.textMuted;
  return (
    <View
      style={{
        width: 44,
        height: 44,
        borderRadius: radius.pill,
        backgroundColor: tint + '1f',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Body style={{ color: tint, fontWeight: '700' }}>{initialsFor(name)}</Body>
    </View>
  );
}

function ConversationRow({
  item,
  onPress,
}: {
  item: Conversation;
  onPress: (item: Conversation) => void;
}) {
  const c = useTheme();
  const preview = item.last_deleted ? tr.hub.messageDeleted : item.last_message;
  const unread = item.unread_count > 0;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={item.user_name}
      onPress={() => onPress(item)}
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1, marginBottom: spacing.sm })}
    >
      <Card accent={unread ? c.primary : undefined}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
          <Avatar name={item.user_name} unread={unread} />
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
              <Body style={{ flex: 1, fontWeight: unread ? '700' : '600' }} numberOfLines={1}>
                {item.user_name}
              </Body>
              {item.time_ago ? (
                <Muted style={{ color: c.textMuted }}>{item.time_ago}</Muted>
              ) : null}
            </View>
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: spacing.sm,
                marginTop: spacing.xs,
              }}
            >
              <Muted
                style={{ flex: 1, color: unread ? c.text : c.textMuted }}
                numberOfLines={1}
              >
                {item.last_from_me ? '↗ ' : ''}
                {preview}
              </Muted>
              {unread ? <Badge label={String(item.unread_count)} tone="info" /> : null}
            </View>
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

function MessageBubble({ msg }: { msg: ThreadMessage }) {
  const c = useTheme();
  const mine = msg.is_from_me;
  return (
    <View
      style={{
        alignSelf: mine ? 'flex-end' : 'flex-start',
        maxWidth: '82%',
        marginBottom: spacing.sm,
      }}
    >
      <View
        style={{
          backgroundColor: mine ? c.primary : c.surfaceAlt,
          borderColor: c.border,
          borderWidth: mine ? 0 : 1,
          borderRadius: radius.md,
          paddingVertical: spacing.sm,
          paddingHorizontal: spacing.md,
        }}
      >
        <Body style={{ color: mine ? c.primaryText : c.text }}>
          {msg.deleted ? tr.hub.messageDeleted : msg.message}
        </Body>
      </View>
      <Muted style={{ marginTop: 2, alignSelf: mine ? 'flex-end' : 'flex-start' }}>
        {msg.time_ago}
        {msg.edited ? ` · ${tr.hub.messageEdited}` : ''}
        {mine && msg.read && !msg.deleted ? ' · ✓✓' : ''}
      </Muted>
    </View>
  );
}

function ThreadView({ partner, onBack }: { partner: Conversation; onBack: () => void }) {
  const c = useTheme();
  const qc = useQueryClient();
  const [draft, setDraft] = useState('');
  const scrollRef = useRef<ScrollView>(null);

  const thread = useQuery({
    queryKey: ['hub-thread', partner.user_id],
    queryFn: () => getConversationThread(partner.user_id),
    refetchInterval: 15000,
  });

  // Mark the thread read once when opened (best-effort) and refresh the list badge.
  useEffect(() => {
    markConversationRead(partner.user_id)
      .then(() => qc.invalidateQueries({ queryKey: ['hub-conversations'] }))
      .catch(() => {});
  }, [partner.user_id, qc]);

  const send = useMutation({
    mutationFn: (text: string) => sendInternalMessage(partner.user_id, text),
    onSuccess: () => {
      setDraft('');
      thread.refetch();
      qc.invalidateQueries({ queryKey: ['hub-conversations'] });
    },
  });

  const messages = thread.data?.messages ?? [];
  const offline = thread.isError && isOffline(thread.error);

  const onSend = useCallback(() => {
    const text = draft.trim();
    if (!text || send.isPending) return;
    send.mutate(text);
  }, [draft, send]);

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: c.bg }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={{ padding: spacing.lg, paddingBottom: spacing.sm, gap: spacing.xs }}>
        <Button title={`← ${tr.hub.messageBack}`} variant="ghost" onPress={onBack} />
        <H1>{partner.user_name}</H1>
      </View>
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.md }}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: false })}
      >
        <OfflineBanner visible={offline} />
        {thread.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : thread.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : messages.length === 0 ? (
          <EmptyState
            icon="chatbubble-ellipses-outline"
            title={tr.hub.messagesThreadEmpty}
            message={tr.hub.messagesThreadEmptyHint}
          />
        ) : (
          messages.map((m) => <MessageBubble key={m.id} msg={m} />)
        )}
      </ScrollView>
      <View
        style={{
          flexDirection: 'row',
          gap: spacing.sm,
          padding: spacing.lg,
          paddingBottom: spacing.xl,
          borderTopColor: c.border,
          borderTopWidth: 1,
          alignItems: 'flex-end',
        }}
      >
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder={tr.hub.messageInputPlaceholder}
          placeholderTextColor={c.textMuted}
          multiline
          style={{
            flex: 1,
            backgroundColor: c.surface,
            color: c.text,
            borderColor: c.border,
            borderWidth: 1,
            borderRadius: radius.md,
            paddingHorizontal: spacing.md,
            paddingVertical: spacing.sm,
            fontSize: 16,
            maxHeight: 120,
            minHeight: 48,
          }}
        />
        <Button
          title={tr.hub.messageSend}
          onPress={onSend}
          loading={send.isPending}
          disabled={!draft.trim()}
        />
      </View>
      {send.isError ? (
        <Muted style={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, color: c.danger }}>
          {tr.hub.messageSendError}
        </Muted>
      ) : null}
    </KeyboardAvoidingView>
  );
}

export default function MessagesScreen() {
  const c = useTheme();
  const [active, setActive] = useState<Conversation | null>(null);

  const convos = useQuery({ queryKey: ['hub-conversations'], queryFn: getConversations });

  const refreshing = convos.isFetching && !convos.isLoading;
  const onRefresh = useCallback(() => {
    convos.refetch();
  }, [convos]);

  const offline = convos.isError && isOffline(convos.error);
  const rows = convos.data?.conversations ?? [];

  if (active) {
    return <ThreadView partner={active} onBack={() => setActive(null)} />;
  }

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-messages">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.messagesTitle}</H1>

        {convos.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : convos.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : rows.length === 0 ? (
          <EmptyState
            icon="chatbubbles-outline"
            title={tr.hub.messagesEmpty}
            message={tr.hub.messagesEmptyHint}
          />
        ) : (
          rows.map((item) => (
            <ConversationRow key={item.user_id} item={item} onPress={setActive} />
          ))
        )}
      </ScrollView>
    </View>
  );
}
