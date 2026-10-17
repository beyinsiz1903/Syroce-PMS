import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, TextInput, View } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Button, Card, EmptyState, H1, Muted, SkeletonCard, webCenter } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { getRoomRequestAccess, getRoomRequests, getRoomRequestThread, markRoomRequestsRead, replyToRoomRequest } from '../../src/api/guestRequests';
import { useAuthStore } from '../../src/state/authStore';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { errorMessage, errorStatus, isOffline } from '../../src/utils/errors';
import { formatDate, formatTime } from '../../src/utils/format';
import { filterRoomRequests, roomRequestCategory, type RoomRequestMessage, type RoomRequestSummary } from '../../src/utils/guestRequests';

// Both staff shells use the same room/QR request stream as the web PMS.
function useVisibleScreen() {
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(AppState.currentState === 'active');
  useFocusEffect(useCallback(() => {
    setFocused(true);
    return () => setFocused(false);
  }, []));
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => setActive(state === 'active'));
    return () => subscription.remove();
  }, []);
  return focused && active;
}

function ErrorCard({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const c = useTheme();
  const denied = errorStatus(error) === 403;
  return <Card testID="guest-requests-error">
    <Body style={{ fontWeight: '700', color: denied ? c.text : c.danger }}>
      {denied ? tr.hub.guestRequestsNoAccess : tr.hub.guestRequestsLoadError}
    </Body>
    <Muted style={{ marginTop: spacing.xs }}>{denied ? tr.hub.guestRequestsAccessHint : errorMessage(error, tr.hub.loadError)}</Muted>
    <Button title="Yeniden dene" variant="outline" onPress={onRetry} style={{ marginTop: spacing.md }} />
  </Card>;
}

function RequestBubble({ message }: { message: RoomRequestMessage }) {
  const c = useTheme();
  const staff = message.sender_type === 'staff';
  return <View style={{ alignSelf: staff ? 'flex-end' : 'flex-start', maxWidth: '90%', marginBottom: spacing.md }}>
    <View style={{ padding: spacing.md, borderRadius: radius.lg, backgroundColor: staff ? c.primary : c.surface, borderWidth: staff ? 0 : 1, borderColor: c.border }}>
      {!staff && (message.category || message.request_id) ? <View style={{ marginBottom: spacing.sm, flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
        <Badge label={roomRequestCategory(message.category)} tone="info" />
        {['high', 'urgent', 'critical'].includes(message.priority || '') ? <Badge label="Acil" tone="danger" /> : null}
      </View> : null}
      <Body style={{ color: staff ? c.primaryText : c.text }}>{message.body}</Body>
    </View>
    <Muted style={{ marginTop: 4, fontSize: 12, alignSelf: staff ? 'flex-end' : 'flex-start' }}>
      {staff ? message.sender_name || 'Otel' : 'Misafir'} · {formatDate(message.created_at)} {formatTime(message.created_at)}
    </Muted>
  </View>;
}

function RoomThread({ room, scope, visible, onBack }: {
  room: RoomRequestSummary; scope: string[]; visible: boolean; onBack: () => void;
}) {
  const c = useTheme();
  const qc = useQueryClient();
  const [draft, setDraft] = useState('');
  const [readError, setReadError] = useState(false);
  const scroll = useRef<ScrollView>(null);
  const thread = useQuery({
    queryKey: [...scope, 'thread', room.room_id], queryFn: () => getRoomRequestThread(room.room_id),
    enabled: visible, refetchInterval: visible ? 15000 : false, retry: false,
  });
  const messages = thread.data?.messages ?? [];
  useEffect(() => {
    // Do not acknowledge unseen messages after a failed thread fetch.
    if (!visible || !thread.data || thread.isError || thread.isFetching
      || !thread.data.messages.some(message => message.sender_type === 'guest' && !message.read)) return;
    let mounted = true;
    markRoomRequestsRead(room.room_id).then(() => {
      if (mounted) setReadError(false);
      void qc.invalidateQueries({ queryKey: [...scope, 'list'] });
    }).catch(() => { if (mounted) setReadError(true); });
    return () => { mounted = false; };
  }, [visible, thread.data, thread.isError, thread.isFetching, room.room_id, qc, scope]);
  const send = useMutation({
    mutationFn: (text: string) => replyToRoomRequest(room.room_id, text), retry: false,
    onSuccess: () => {
      setDraft('');
      void qc.invalidateQueries({ queryKey: [...scope, 'thread', room.room_id] });
      void qc.invalidateQueries({ queryKey: [...scope, 'list'] });
    },
  });
  const blocked = thread.isError || !thread.data || !visible;
  const roomNumber = thread.isError ? room.room_number : thread.data?.room_number || room.room_number;
  return <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} testID="guest-request-thread">
    <View style={[{ padding: spacing.lg, gap: spacing.xs }, webCenter]}>
      <Button title="← Misafir talepleri" variant="ghost" onPress={onBack} />
      <H1>{roomNumber ? `Oda ${roomNumber}` : 'Oda talebi'}</H1>
      <Muted>{tr.hub.guestRequestsReplyHint}</Muted>
    </View>
    <ScrollView ref={scroll} contentContainerStyle={[{ paddingHorizontal: spacing.lg, paddingBottom: spacing.md }, webCenter]}
      onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}
      refreshControl={<RefreshControl refreshing={thread.isFetching && !thread.isLoading} onRefresh={() => { void thread.refetch(); }} tintColor={c.primary} />}>
      <OfflineBanner visible={thread.isError && isOffline(thread.error)} />
      {!thread.isError && messages.length === 300 ? <Muted style={{ marginBottom: spacing.sm }}>Bu odanın en güncel 300 mesajı gösteriliyor.</Muted> : null}
      {thread.isLoading || !thread.data && !thread.isError ? <SkeletonCard /> : thread.isError ? <ErrorCard error={thread.error} onRetry={() => { void thread.refetch(); }} />
        : messages.length ? messages.map(message => <RequestBubble key={message.id} message={message} />)
          : <EmptyState icon="chatbubble-ellipses-outline" title={tr.hub.messagesThreadEmpty} message={tr.hub.messagesThreadEmptyHint} />}
    </ScrollView>
    {readError ? <Muted style={{ paddingHorizontal: spacing.lg }}>{tr.hub.markReadError}</Muted> : null}
    {send.isError ? <Body accessibilityRole="alert" style={{ color: c.danger, paddingHorizontal: spacing.lg }} testID="guest-request-send-error">{errorMessage(send.error, tr.hub.messageSendError)}</Body> : null}
    <View style={[{ padding: spacing.md, borderTopWidth: 1, borderTopColor: c.border, gap: spacing.sm }, webCenter]}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: spacing.sm }}>
        <TextInput value={draft} onChangeText={setDraft} multiline maxLength={2000} editable={!send.isPending && !blocked}
          placeholder={tr.hub.messageInputPlaceholder} placeholderTextColor={c.textMuted} accessibilityLabel={tr.hub.messageInputPlaceholder}
          testID="guest-request-reply" style={{ flex: 1, minHeight: 48, maxHeight: 140, padding: spacing.md, color: c.text, backgroundColor: c.surface, borderWidth: 1, borderColor: c.border, borderRadius: radius.md }} />
        <Button title={tr.hub.messageSend} icon="send-outline" loading={send.isPending} disabled={blocked || !draft.trim() || send.isPending}
          testID="guest-request-send" onPress={() => { if (!blocked && draft.trim() && !send.isPending) send.mutate(draft.trim()); }} />
      </View>
      <Muted style={{ fontSize: 12 }}>{tr.hub.guestRequestsComposerHint}</Muted>
    </View>
  </KeyboardAvoidingView>;
}

function GuestRequestsInbox({ scope }: { scope: string[] }) {
  const c = useTheme();
  const visible = useVisibleScreen();
  const [selected, setSelected] = useState<RoomRequestSummary | null>(null);
  const [search, setSearch] = useState('');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const access = useQuery({
    queryKey: [...scope, 'access'], queryFn: getRoomRequestAccess, enabled: visible,
    refetchInterval: visible ? 30000 : false, retry: false,
  });
  const canView = access.data?.can_view === true && !access.isError;
  const list = useQuery({
    queryKey: [...scope, 'list'], queryFn: getRoomRequests, enabled: visible && canView,
    refetchInterval: visible && canView ? 15000 : false, retry: false,
  });
  const denied = access.data?.can_view === false || errorStatus(access.error) === 403 || errorStatus(list.error) === 403;
  const rows = filterRoomRequests(list.data?.threads ?? [], search, unreadOnly);
  const refresh = () => { void access.refetch(); if (canView) void list.refetch(); };
  return <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-messages">
    {selected && canView && !denied ? <RoomThread key={selected.room_id} room={selected} scope={scope} visible={visible} onBack={() => setSelected(null)} />
      : <ScrollView contentContainerStyle={[{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }, webCenter]}
        refreshControl={<RefreshControl refreshing={access.isFetching && !access.isLoading || list.isFetching && !list.isLoading} onRefresh={refresh} tintColor={c.primary} />}>
        <View><H1>{tr.hub.messagesTitle}</H1><Muted style={{ marginTop: spacing.xs }}>{tr.hub.guestRequestsIntro}</Muted></View>
        <OfflineBanner visible={isOffline(access.error) || isOffline(list.error)} />
        {denied ? <Card testID="guest-requests-no-access"><Body style={{ fontWeight: '700' }}>{tr.hub.guestRequestsNoAccess}</Body><Muted style={{ marginTop: spacing.sm }}>{tr.hub.guestRequestsAccessHint}</Muted></Card>
          : access.isError ? <ErrorCard error={access.error} onRetry={refresh} />
            : access.isLoading || !canView && access.data === undefined || list.isLoading ? <><SkeletonCard /><SkeletonCard /></>
              : list.isError ? <ErrorCard error={list.error} onRetry={refresh} /> : <>
                <Card>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Body style={{ fontWeight: '700' }}>{list.data?.threads.length ?? 0} oda görüşmesi</Body>
                    <Badge label={`${list.data?.total_unread ?? 0} okunmamış`} tone={list.data?.total_unread ? 'info' : 'default'} />
                  </View>
                  <TextInput value={search} onChangeText={setSearch} placeholder="Oda veya talep ara" accessibilityLabel="Oda veya talep ara"
                    placeholderTextColor={c.textMuted} style={{ marginTop: spacing.md, minHeight: 48, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, color: c.text }} />
                  <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
                    {[false, true].map(value => <Pressable key={String(value)} accessibilityRole="button" accessibilityState={{ selected: unreadOnly === value }}
                      onPress={() => setUnreadOnly(value)} style={{ minHeight: 44, padding: spacing.sm, borderRadius: radius.pill, backgroundColor: unreadOnly === value ? c.surfaceAlt : undefined }}>
                      <Body style={{ color: unreadOnly === value ? c.primary : c.textMuted }}>{value ? 'Okunmamış' : 'Tümü'}</Body>
                    </Pressable>)}
                  </View>
                </Card>
                {!rows.length ? <EmptyState icon="chatbubbles-outline" title={search || unreadOnly ? 'Bu filtrede talep yok' : tr.hub.messagesEmpty}
                  message={search || unreadOnly ? 'Oda aramasını veya okunmamış filtresini değiştirebilirsiniz.' : tr.hub.messagesEmptyHint} />
                  : rows.map(room => <Pressable key={room.room_id} testID={`guest-request-room-${room.room_id}`} accessibilityRole="button"
                    accessibilityLabel={`${room.room_number ? `Oda ${room.room_number}` : 'Oda talebi'}, ${room.unread} okunmamış mesaj`}
                    onPress={() => setSelected(room)} style={({ pressed }) => ({ opacity: pressed ? 0.8 : 1 })}>
                    <Card accent={room.unread ? c.primary : undefined}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
                        <View style={{ width: 48, height: 48, backgroundColor: c.surfaceAlt, alignItems: 'center', justifyContent: 'center', borderRadius: radius.md }}><Ionicons name="bed-outline" size={24} color={c.primary} /></View>
                        <View style={{ flex: 1, gap: 3 }}>
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
                            <Body style={{ fontWeight: '700' }}>{room.room_number ? `Oda ${room.room_number}` : 'Oda talebi'}</Body>
                            {room.unread ? <Badge label={String(room.unread)} tone="info" /> : null}
                          </View>
                          <Muted>{roomRequestCategory(room.last_category)}</Muted>
                          <Body numberOfLines={2}>{room.last_sender_type === 'staff' ? 'Otel: ' : ''}{room.last_body || 'Misafir talebi'}</Body>
                          <Muted style={{ fontSize: 12 }}>{formatDate(room.last_created_at)} · {formatTime(room.last_created_at)}</Muted>
                        </View>
                      </View>
                    </Card>
                  </Pressable>)}
              </>}
      </ScrollView>}
  </View>;
}

export default function MessagesScreen() {
  const user = useAuthStore(state => state.user);
  const tenant = user?.tenant_id || user?.hotel_id || '';
  const userId = user?.id || user?.user_id || '';
  const scope = React.useMemo(() => ['room-guest-requests', tenant, userId], [tenant, userId]);
  if (!tenant || !userId) return null;
  return <GuestRequestsInbox key={`${tenant}:${userId}`} scope={scope} />;
}
