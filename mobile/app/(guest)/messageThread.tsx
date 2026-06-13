import React, { useEffect, useMemo, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  TextInput,
  View,
} from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Body, EmptyState, H1, Muted, SkeletonCard, webCenter } from '../../src/components/ui';
import { spacing, useTheme, radius } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  getGuestMessages,
  markAllRead,
  sendGuestMessage,
} from '../../src/api/guestMessaging';
import { formatTime } from '../../src/utils/format';
import { errorMessage } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';

export default function MessageThreadScreen() {
  const c = useTheme();
  const params = useLocalSearchParams<{ bookingId?: string; title?: string }>();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['guest-messages'],
    queryFn: getGuestMessages,
    refetchInterval: 8_000,
  });

  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const conv = useMemo(() => {
    const cs = q.data?.conversations || [];
    if (params.bookingId) return cs.find((c0) => c0.booking_id === params.bookingId) || null;
    return cs[0] || null;
  }, [q.data, params.bookingId]);

  const messages = useMemo(() => {
    const list = [...(conv?.messages || [])];
    list.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
    return list;
  }, [conv]);

  useEffect(() => {
    if (conv && conv.unread_count > 0) {
      markAllRead(conv.booking_id || undefined).then(() =>
        qc.invalidateQueries({ queryKey: ['guest-messages'] }),
      );
    }
  }, [conv, qc]);

  const onSend = async () => {
    const msg = text.trim();
    if (!msg) return;
    setSending(true);
    setError(null);
    try {
      await sendGuestMessage(msg, conv?.booking_id || params.bookingId || undefined, 'general');
      setText('');
      haptic.success();
      await qc.invalidateQueries({ queryKey: ['guest-messages'] });
    } catch (e) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setSending(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: c.bg }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={[{ padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.lg }, webCenter]}
        refreshControl={
          <RefreshControl
            refreshing={q.isFetching && !q.isLoading}
            onRefresh={() => q.refetch()}
            tintColor={c.primary}
          />
        }
      >
        <H1>{params.title || conv?.guest_name || tr.guest.messagesTitle}</H1>
        {q.isLoading ? (
          <SkeletonCard />
        ) : messages.length === 0 ? (
          <EmptyState
            icon="chatbubble-ellipses-outline"
            title={tr.guest.noMessages}
            message={tr.guest.noMessagesMessage}
          />
        ) : (
          messages.map((m) => {
            const isMe = m.sender === 'guest';
            return (
              <View
                key={m.id}
                style={{
                  alignSelf: isMe ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  backgroundColor: isMe ? c.primary : c.surface,
                  borderColor: isMe ? c.primary : c.border,
                  borderWidth: 1,
                  borderRadius: radius.md,
                  padding: spacing.sm,
                }}
              >
                <Body style={{ color: isMe ? c.primaryText : c.text }}>{m.message}</Body>
                <Muted
                  style={{
                    color: isMe ? c.primaryText : c.textMuted,
                    marginTop: 2,
                    fontSize: 11,
                  }}
                >
                  {isMe ? tr.guest.sentBy : m.sender_name || tr.guest.sentByStaff} ·{' '}
                  {formatTime(m.created_at)}
                  {m.read && isMe ? ' · okundu' : ''}
                </Muted>
              </View>
            );
          })
        )}
      </ScrollView>
      {error ? (
        <Body style={{ color: c.danger, paddingHorizontal: spacing.lg }}>{error}</Body>
      ) : null}
      <View
        style={{
          flexDirection: 'row',
          gap: spacing.sm,
          padding: spacing.md,
          borderTopColor: c.border,
          borderTopWidth: 1,
          backgroundColor: c.surface,
        }}
      >
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder={tr.guest.typeMessage}
          placeholderTextColor={c.textMuted}
          accessibilityLabel={tr.guest.typeMessage}
          multiline
          style={{
            flex: 1,
            minHeight: 44,
            maxHeight: 120,
            color: c.text,
            backgroundColor: c.bg,
            borderColor: c.border,
            borderWidth: 1,
            borderRadius: radius.md,
            paddingHorizontal: spacing.md,
            paddingVertical: spacing.sm,
          }}
        />
        <Pressable
          onPress={onSend}
          disabled={sending || !text.trim()}
          accessibilityRole="button"
          accessibilityLabel={tr.app.send}
          style={({ pressed }) => ({
            backgroundColor: c.primary,
            paddingHorizontal: spacing.lg,
            justifyContent: 'center',
            borderRadius: radius.md,
            opacity: !text.trim() || sending ? 0.5 : pressed ? 0.85 : 1,
          })}
        >
          <Body style={{ color: c.primaryText, fontWeight: '600' }}>{tr.app.send}</Body>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}
